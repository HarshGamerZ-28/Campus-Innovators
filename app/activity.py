from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ActivityDay, DailyXpLedger, User

# Generous enough that normal daily use (a handful of posts, questions, answers,
# project actions, quest claims) never gets throttled, while still putting a hard
# ceiling on scripted farming of repeatable actions like joining/leaving a project.
DAILY_XP_CAP = 300

# Cumulative XP required to level up FROM the given level (i.e. `next_xp` for a
# user currently at that level). Kept low early on so new users feel level-ups
# quickly; grows by a flat +500 per level once past the explicitly tuned levels.
LEVEL_XP_THRESHOLDS = {1: 100, 2: 250, 3: 500, 4: 800, 5: 1200}
LEVEL_XP_STEP_AFTER_TUNED = 500


def xp_threshold_for_level(level: int) -> int:
    """Return the cumulative `xp` value at which a user at `level` levels up."""
    if level in LEVEL_XP_THRESHOLDS:
        return LEVEL_XP_THRESHOLDS[level]
    if level < 1:
        return LEVEL_XP_THRESHOLDS[1]
    highest_tuned_level = max(LEVEL_XP_THRESHOLDS)
    return LEVEL_XP_THRESHOLDS[highest_tuned_level] + LEVEL_XP_STEP_AFTER_TUNED * (level - highest_tuned_level)


def apply_level_up(user: User) -> None:
    """Bump `user.level`/`user.next_xp` for as long as `user.xp` clears the threshold.

    Looped (not a single if) so a big XP grant can carry a user across more than
    one level in one go without leaving them under-leveled.
    """
    while user.xp >= user.next_xp:
        user.level += 1
        user.next_xp = xp_threshold_for_level(user.level)


def record_activity(db: Session, user_id: int, amount: int = 1, on_date: date | None = None) -> None:
    day = on_date or date.today()
    item = db.scalar(select(ActivityDay).where(ActivityDay.user_id == user_id, ActivityDay.activity_date == day))
    if item is None:
        db.add(ActivityDay(user_id=user_id, activity_date=day, count=max(amount, 1)))
    else:
        item.count += max(amount, 1)


def grant_xp(db: Session, user: User, amount: int, on_date: date | None = None) -> int:
    """Award XP to `user`, capped at DAILY_XP_CAP earned per calendar day.

    Returns the amount actually granted, which may be less than `amount` (or 0)
    once the day's cap is reached. Callers should always add XP through this
    function rather than mutating `user.xp` directly, so no action can be
    repeated to farm unlimited XP.
    """
    if amount <= 0:
        return 0
    day = on_date or date.today()
    ledger = db.scalar(select(DailyXpLedger).where(DailyXpLedger.user_id == user.id, DailyXpLedger.xp_date == day))
    already_earned = ledger.amount if ledger is not None else 0
    granted = max(min(amount, DAILY_XP_CAP - already_earned), 0)
    if granted <= 0:
        return 0
    if ledger is None:
        db.add(DailyXpLedger(user_id=user.id, xp_date=day, amount=granted))
    else:
        ledger.amount += granted
    user.xp += granted
    apply_level_up(user)
    return granted


def activity_payload(db: Session, user_id: int, days: int = 30) -> list[dict]:
    end = date.today()
    start = end - timedelta(days=days - 1)
    rows = db.scalars(
        select(ActivityDay)
        .where(ActivityDay.user_id == user_id, ActivityDay.activity_date >= start, ActivityDay.activity_date <= end)
        .order_by(ActivityDay.activity_date)
    ).all()
    by_date = {row.activity_date: row.count for row in rows}
    return [
        {"date": (start + timedelta(days=index)).isoformat(), "count": by_date.get(start + timedelta(days=index), 0)}
        for index in range(days)
    ]
