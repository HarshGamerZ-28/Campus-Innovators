from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..activity import record_activity, xp_threshold_for_level
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, get_optional_user
from ..email import send_password_reset_email
from ..models import AllowedEmail, Avatar, Habit, Notification, PasswordResetToken, Quest, RefreshSession, Skill, User
from ..rate_limit import enforce
from ..schemas import ForgotPasswordInput, LoginInput, RegisterInput, ResetPasswordInput
from ..security import (
    clear_refresh_cookie,
    decode_token,
    hash_password,
    issue_session,
    set_refresh_cookie,
    token_hash,
    verify_password,
)
from ..serializers import user_private

PASSWORD_RESET_TOKEN_MINUTES = 30

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_meta(request: Request) -> tuple[str, str]:
    user_agent = request.headers.get("user-agent", "")
    forwarded = request.headers.get("x-forwarded-for", "") if settings.trust_proxy_headers else ""
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")
    return user_agent, ip


def _avatar_for(db: Session, key: str, email: str) -> Avatar:
    avatar = db.scalar(select(Avatar).where(Avatar.key == key, Avatar.is_active.is_(True)))
    if avatar is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected avatar is unavailable")
    if avatar.reserved_email and avatar.reserved_email.lower() != email.lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="That avatar is reserved")
    return avatar


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return user


def _login_response(user: User, access_token: str) -> dict:
    return {"access_token": access_token, "token_type": "bearer", "expires_in": settings.access_token_minutes * 60, "user": user_private(user)}


@router.post("/login")
def login(payload: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    enforce(request, "login", 10, 300)
    user = authenticate(db, payload.email, payload.password)
    user.last_login_at = datetime.now(timezone.utc)
    record_activity(db, user.id)
    user_agent, ip = _client_meta(request)
    access_token = issue_session(db, user, response, user_agent, ip)
    db.commit()
    return _login_response(user, access_token)


@router.post("/token")
def oauth_token(
    response: Response,
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> dict:
    enforce(request, "oauth-token", 10, 300)
    user = authenticate(db, form.username, form.password)
    user.last_login_at = datetime.now(timezone.utc)
    user_agent, ip = _client_meta(request)
    access_token = issue_session(db, user, response, user_agent, ip)
    db.commit()
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterInput, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    enforce(request, "register", 5, 3600)
    email = payload.email.lower().strip()
    if email == settings.founder_email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Founder account must be created with the bootstrap command")
    if settings.allowed_email_domains and email.rsplit("@", 1)[-1] not in settings.allowed_email_domains:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please register with an approved college email address")
    is_allowlisted = db.scalar(select(AllowedEmail.id).where(AllowedEmail.email == email)) is not None
    if not is_allowlisted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your email isn't approved yet. Contact an admin for access.")
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    if db.scalar(select(User.id).where(User.username == payload.username)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is already taken")

    avatar = _avatar_for(db, payload.avatar_key, email)
    user = User(
        name=payload.name.strip(),
        username=payload.username,
        email=email,
        hashed_password=hash_password(payload.password),
        department=payload.department.strip(),
        year=payload.year.strip(),
        avatar_key=avatar.key,
        avatar_url=avatar.image_url,
        hero_avatar_url=avatar.hero_image_url,
        level=1,
        xp=0,
        next_xp=xp_threshold_for_level(1),
        coins=100,
        streak=0,
    )
    db.add(user)
    db.flush()
    db.add_all([
        Skill(user_id=user.id, name="Communication", progress=20, tone="blue"),
        Skill(user_id=user.id, name="Problem Solving", progress=15, tone="purple"),
        Skill(user_id=user.id, name="Project Building", progress=10, tone="green"),
        Habit(user_id=user.id, label="Study", complete=False, streak=0, tone="blue"),
        Habit(user_id=user.id, label="Code", complete=False, streak=0, tone="green"),
        Habit(user_id=user.id, label="Read", complete=False, streak=0, tone="gold"),
        Quest(user_id=user.id, title="Complete Your Profile", current=0, target=1, reward_xp=40),
        Quest(user_id=user.id, title="Ask Your First Question", current=0, target=1, reward_xp=30),
        Quest(user_id=user.id, title="Join a Project", current=0, target=1, reward_xp=30),
        Notification(user_id=user.id, message="Welcome to Campus Innovators. Complete your profile to start earning XP.", kind="welcome"),
    ])
    record_activity(db, user.id)
    user_agent, ip = _client_meta(request)
    access_token = issue_session(db, user, response, user_agent, ip)
    db.commit()
    db.refresh(user)
    return _login_response(user, access_token)


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordInput, request: Request, db: Session = Depends(get_db)) -> dict:
    enforce(request, "forgot-password", 3, 3600)
    generic_response = {"message": "If that email is registered, a reset link has been sent."}

    email = payload.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        # Always return the same response so we never leak whether an email is registered.
        return generic_response

    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash(raw_token),
            expires_at=now + timedelta(minutes=PASSWORD_RESET_TOKEN_MINUTES),
        )
    )
    db.commit()

    reset_link = f"{settings.frontend_url}/reset-password?token={raw_token}"
    send_password_reset_email(user.email, reset_link)
    return generic_response


@router.post("/reset-password")
def reset_password(payload: ResetPasswordInput, request: Request, db: Session = Depends(get_db)) -> dict:
    enforce(request, "reset-password", 10, 3600)
    now = datetime.now(timezone.utc)
    hashed = token_hash(payload.token)
    reset_token = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hashed))

    expires_at = reset_token.expires_at if reset_token is not None else now
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if reset_token is None or reset_token.used_at is not None or expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This reset link is invalid or has expired")

    user = db.get(User, reset_token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This reset link is invalid or has expired")

    user.hashed_password = hash_password(payload.new_password)
    reset_token.used_at = now
    # Force logout everywhere: revoke every existing refresh session for this user.
    for session in db.scalars(select(RefreshSession).where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))):
        session.revoked_at = now
    db.commit()
    return {"message": "Your password has been reset. Please sign in again."}


@router.post("/refresh")
def refresh_session(
    response: Response,
    request: Request,
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
    db: Session = Depends(get_db),
) -> dict:
    enforce(request, "refresh", 120, 60)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    payload = decode_token(refresh_token, "refresh")
    session = db.scalar(select(RefreshSession).where(RefreshSession.jti == payload.get("jti")))
    now = datetime.now(timezone.utc)
    expires_at = session.expires_at if session is not None else now
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if session is None or session.revoked_at is not None or expires_at <= now or session.token_hash != token_hash(refresh_token):
        clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is unavailable")

    session.revoked_at = now
    user_agent, ip = _client_meta(request)
    new_access = issue_session(db, user, response, user_agent, ip)
    newest = db.scalar(select(RefreshSession).where(RefreshSession.user_id == user.id).order_by(RefreshSession.id.desc()))
    if newest:
        session.replaced_by_jti = newest.jti
    db.commit()
    return _login_response(user, new_access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
    db: Session = Depends(get_db),
) -> Response:
    if refresh_token:
        try:
            payload = decode_token(refresh_token, "refresh")
            session = db.scalar(select(RefreshSession).where(RefreshSession.jti == payload.get("jti")))
            if session and session.revoked_at is None:
                session.revoked_at = datetime.now(timezone.utc)
                db.commit()
        except HTTPException:
            pass
    clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me")
def me(current_user: User = Depends(get_current_user)) -> dict:
    return user_private(current_user)


@router.get("/avatars")
def avatars(current_user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)) -> list[dict]:
    items = db.scalars(select(Avatar).where(Avatar.is_active.is_(True)).order_by(Avatar.sort_order, Avatar.id)).all()
    email = current_user.email.lower() if current_user else None
    return [
        {
            "key": item.key,
            "label": item.label,
            "image_url": item.image_url,
            "hero_image_url": item.hero_image_url,
            "reserved": bool(item.reserved_email),
        }
        for item in items
        if not item.reserved_email or item.reserved_email.lower() == email
    ]
