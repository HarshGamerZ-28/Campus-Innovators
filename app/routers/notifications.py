from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Notification, User
from ..schemas import MarkReadOut, NotificationOut, UnreadCountOut

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _get_own_notification(db: Session, notification_id: int, user_id: int) -> Notification:
    """404 (not 403) for another user's notification — same "don't confirm it
    exists" posture as _get_opportunity-style lookups elsewhere, so a user
    can't probe notification ids that aren't theirs."""
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == current_user.id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    count = db.scalar(
        select(func.count(Notification.id)).where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
    ) or 0
    return {"count": count}


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Notification:
    notification = _get_own_notification(db, notification_id, current_user.id)
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


# Kept on both verbs: PATCH matches this feature's spec, POST matches the
# already-deployed frontend call — same handler, no client changes forced.
@router.api_route("/read-all", methods=["PATCH", "POST"], response_model=MarkReadOut)
def mark_all_read(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    items = db.scalars(
        select(Notification).where(Notification.user_id == current_user.id, Notification.is_read.is_(False))
    ).all()
    for item in items:
        item.is_read = True
    db.commit()
    return {"updated": len(items)}
