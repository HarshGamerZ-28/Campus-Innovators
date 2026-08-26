from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..activity import grant_xp, xp_threshold_for_level
from ..config import settings
from ..dashboard_data import platform_payload
from ..database import get_db
from ..deps import require_admin
from ..models import AllowedEmail, Avatar, Meeting, MeetingAttendance, PlatformSetting, User
from ..notify import notify_active_users
from ..schemas import (
    AllowedEmailCreate,
    AllowedEmailOut,
    AvatarCreate,
    AvatarOut,
    AvatarUpdate,
    ClubSocialLinksOut,
    ClubSocialLinksUpdate,
    MeetingAttendeeOut,
    MeetingCreate,
    MeetingOut,
    PlatformUpdate,
)

MEETING_ATTENDANCE_XP = 50


def _meeting_payload(meeting: Meeting, attendee_count: int) -> dict:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "description": meeting.description,
        "scheduled_at": meeting.scheduled_at,
        "location": meeting.location,
        "created_by_id": meeting.created_by_id,
        "created_at": meeting.created_at,
        "attendee_count": attendee_count,
        "visible_on_events": meeting.visible_on_events,
    }


def _attendee_payload(member: User, present: bool, marked_present_at) -> dict:
    return {
        "user_id": member.id,
        "name": member.name,
        "username": member.username,
        "avatar_url": member.avatar_url,
        "present": present,
        "marked_present_at": marked_present_at,
    }

logger = logging.getLogger("campus_innovators.admin")

router = APIRouter(prefix="/admin", tags=["Admin"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_UPLOAD_TYPES = {"image/png", "image/jpeg"}


@router.post("/uploads/image")
async def upload_image(
    file: UploadFile,
    current_user: User = Depends(require_admin),
) -> dict:
    if not settings.cloudinary_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image uploads aren't configured on this server yet. Set CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET, or paste an image URL instead.",
        )
    if file.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only PNG or JPEG images are allowed")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image must be under 5 MB")

    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )
    try:
        result = cloudinary.uploader.upload(contents, folder="campus-innovators/avatars", resource_type="image")
    except Exception as exc:  # noqa: BLE001 - surface a clean error instead of a 500
        logger.warning("Cloudinary upload failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Image upload failed. Please try again.") from exc

    return {"url": result["secure_url"]}


@router.patch("/platform")
def update_platform(
    payload: PlatformUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    for key, value in payload.model_dump().items():
        item = db.get(PlatformSetting, key)
        if item is None:
            db.add(PlatformSetting(key=key, value=value.strip()))
        else:
            item.value = value.strip()
    db.commit()
    return platform_payload(db)


@router.patch("/community-social-links", response_model=ClubSocialLinksOut)
def update_community_social_links(
    payload: ClubSocialLinksUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    # exclude_unset (not PlatformUpdate's full-replace pattern above) — a PATCH
    # that only sends instagram_url must leave linkedin_url untouched.
    field_to_key = {"instagram_url": "club_instagram_url", "linkedin_url": "club_linkedin_url"}
    for field, value in payload.model_dump(exclude_unset=True).items():
        key = field_to_key[field]
        item = db.get(PlatformSetting, key)
        if item is None:
            db.add(PlatformSetting(key=key, value=value))
        else:
            item.value = value
    db.commit()
    payload_out = platform_payload(db)
    return {"club_instagram_url": payload_out["club_instagram_url"], "club_linkedin_url": payload_out["club_linkedin_url"]}


@router.get("/allowed-emails", response_model=list[AllowedEmailOut])
def list_allowed_emails(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AllowedEmail]:
    return list(db.scalars(select(AllowedEmail).order_by(AllowedEmail.added_at.desc())).all())


@router.post("/allowed-emails", status_code=status.HTTP_201_CREATED, response_model=AllowedEmailOut)
def add_allowed_email(
    payload: AllowedEmailCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AllowedEmail:
    email = payload.email.lower().strip()
    existing = db.scalar(select(AllowedEmail).where(AllowedEmail.email == email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already on the allowlist")
    entry = AllowedEmail(email=email, added_by_id=current_user.id, note=(payload.note or "").strip() or None)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/allowed-emails/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_allowed_email(
    entry_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    entry = db.get(AllowedEmail, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Allowlist entry not found")
    matching_user = db.scalar(select(User).where(User.email == entry.email))
    if matching_user is not None:
        matching_user.is_active = False
    db.delete(entry)
    db.commit()
    return None


@router.get("/avatars", response_model=list[AvatarOut])
def list_avatars(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Avatar]:
    return list(db.scalars(select(Avatar).order_by(Avatar.sort_order, Avatar.id)).all())


@router.post("/avatars", status_code=status.HTTP_201_CREATED, response_model=AvatarOut)
def add_avatar(
    payload: AvatarCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Avatar:
    key = payload.key.strip()
    if db.scalar(select(Avatar).where(Avatar.key == key)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Avatar key already exists")
    avatar = Avatar(
        key=key,
        label=payload.label.strip(),
        image_url=payload.image_url,
        hero_image_url=payload.hero_image_url,
        reserved_email=None,
        is_active=True,
        sort_order=payload.sort_order,
    )
    db.add(avatar)
    db.commit()
    db.refresh(avatar)
    return avatar


@router.patch("/avatars/{avatar_id}", response_model=AvatarOut)
def update_avatar(
    avatar_id: int,
    payload: AvatarUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Avatar:
    avatar = db.get(Avatar, avatar_id)
    if avatar is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field == "label" and value is not None:
            value = value.strip()
        setattr(avatar, field, value)
    db.commit()
    db.refresh(avatar)
    return avatar


@router.post("/meetings", status_code=status.HTTP_201_CREATED, response_model=MeetingOut)
def create_meeting(
    payload: MeetingCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    meeting = Meeting(
        title=payload.title.strip(),
        description=payload.description.strip(),
        scheduled_at=payload.scheduled_at,
        location=payload.location.strip(),
        created_by_id=current_user.id,
        visible_on_events=payload.visible_on_events,
    )
    db.add(meeting)
    if meeting.visible_on_events:
        # Only meetings that opted into the public events feed are worth a
        # notification — an internal-only meeting shouldn't surface here.
        notify_active_users(db, message=f'New event: "{meeting.title}"', kind="event_created", exclude_user_id=current_user.id)
    db.commit()
    db.refresh(meeting)
    return _meeting_payload(meeting, attendee_count=0)


@router.get("/meetings", response_model=list[MeetingOut])
def list_meetings(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    meetings = list(db.scalars(select(Meeting).order_by(Meeting.scheduled_at.desc())).all())
    counts = dict(
        db.execute(
            select(MeetingAttendance.meeting_id, func.count(MeetingAttendance.id)).group_by(MeetingAttendance.meeting_id)
        ).all()
    )
    return [_meeting_payload(meeting, attendee_count=counts.get(meeting.id, 0)) for meeting in meetings]


@router.get("/meetings/{meeting_id}/attendees", response_model=list[MeetingAttendeeOut])
def list_meeting_attendees(
    meeting_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    present_by_user = {
        row.user_id: row.marked_present_at
        for row in db.scalars(select(MeetingAttendance).where(MeetingAttendance.meeting_id == meeting_id)).all()
    }
    members = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.name)).all())
    return [
        _attendee_payload(member, present=member.id in present_by_user, marked_present_at=present_by_user.get(member.id))
        for member in members
    ]


@router.post("/meetings/{meeting_id}/attendance/{user_id}", response_model=MeetingAttendeeOut)
def mark_attendance(
    meeting_id: int,
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    member = db.get(User, user_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = db.scalar(
        select(MeetingAttendance).where(MeetingAttendance.meeting_id == meeting_id, MeetingAttendance.user_id == user_id)
    )
    if existing is not None:
        # Already marked present earlier — return as-is, no second XP grant.
        return _attendee_payload(member, present=True, marked_present_at=existing.marked_present_at)

    attendance = MeetingAttendance(meeting_id=meeting_id, user_id=user_id)
    db.add(attendance)
    grant_xp(db, member, MEETING_ATTENDANCE_XP)
    db.commit()
    db.refresh(attendance)
    return _attendee_payload(member, present=True, marked_present_at=attendance.marked_present_at)


@router.delete("/meetings/{meeting_id}/attendance/{user_id}", response_model=MeetingAttendeeOut)
def unmark_attendance(
    meeting_id: int,
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Undo an accidental present-tick. XP already granted is left alone —
    reversing it reliably would need per-attendance XP tracking we don't have,
    and clawing back a reward a member has already seen is worse UX than a
    rare un-reversed grant."""
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    member = db.get(User, user_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = db.scalar(
        select(MeetingAttendance).where(MeetingAttendance.meeting_id == meeting_id, MeetingAttendance.user_id == user_id)
    )
    if existing is not None:
        db.delete(existing)
        db.commit()
    return _attendee_payload(member, present=False, marked_present_at=None)


@router.post("/recalc-levels")
def recalc_levels(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """One-off maintenance action: recompute every user's `level`/`next_xp`
    against the current LEVEL_XP_THRESHOLDS. Fixes accounts left with a stale
    next_xp from before thresholds were tuned. Safe to call more than once."""
    updated = []
    users = db.scalars(select(User)).all()
    for user in users:
        level = max(user.level, 1)
        while level > 1 and user.xp < xp_threshold_for_level(level - 1):
            level -= 1
        while user.xp >= xp_threshold_for_level(level):
            level += 1
        correct_next_xp = xp_threshold_for_level(level)
        if user.level != level or user.next_xp != correct_next_xp:
            updated.append({
                "user_id": user.id,
                "username": user.username,
                "old_level": user.level,
                "new_level": level,
                "old_next_xp": user.next_xp,
                "new_next_xp": correct_next_xp,
            })
            user.level = level
            user.next_xp = correct_next_xp
    db.commit()
    return {"updated_count": len(updated), "updated": updated}
