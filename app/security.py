from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import HTTPException, Response, status
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from .config import settings
from .models import RefreshSession, User

ALGORITHM = "HS256"
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=64)
    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N,
        SCRYPT_R,
        SCRYPT_P,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _jwt(payload: dict, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({**payload, "iat": now, "exp": now + expires_delta}, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user: User) -> str:
    return _jwt(
        {"sub": str(user.id), "type": "access", "role": user.role, "jti": uuid4().hex},
        timedelta(minutes=settings.access_token_minutes),
    )


def create_refresh_token(user: User, jti: str) -> str:
    return _jwt(
        {"sub": str(user.id), "type": "refresh", "jti": jti},
        timedelta(days=settings.refresh_token_days),
    )


def decode_token(token: str, expected_type: str) -> dict:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        if payload.get("type") != expected_type or not payload.get("sub"):
            raise credentials_error
        return payload
    except (InvalidTokenError, ValueError, TypeError) as exc:
        raise credentials_error from exc


def decode_access_token(token: str) -> int:
    return int(decode_token(token, "access")["sub"])


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path=f"{settings.api_prefix}/auth",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path=f"{settings.api_prefix}/auth",
    )


def issue_session(
    db: Session,
    user: User,
    response: Response,
    user_agent: str = "",
    ip_address: str = "",
) -> str:
    jti = uuid4().hex
    refresh_token = create_refresh_token(user, jti)
    db.add(
        RefreshSession(
            jti=jti,
            token_hash=token_hash(refresh_token),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days),
            user_agent=user_agent[:500],
            ip_address=ip_address[:100],
        )
    )
    set_refresh_cookie(response, refresh_token)
    return create_access_token(user)
