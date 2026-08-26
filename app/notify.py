from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Notification, User


def notify_active_users(db: Session, *, message: str, kind: str, exclude_user_id: int | None = None) -> None:
    """Fan out one notification to every active user, e.g. for a new public
    Event/Meeting. Synchronous bulk insert — fine at this app's scale (a single
    campus club), so no queue/worker was introduced just for this.

    exclude_user_id skips the actor who caused the notification (they don't
    need to be told about the thing they just did).
    """
    user_ids = db.scalars(select(User.id).where(User.is_active.is_(True))).all()
    db.add_all(
        Notification(user_id=user_id, message=message, kind=kind)
        for user_id in user_ids
        if user_id != exclude_user_id
    )
