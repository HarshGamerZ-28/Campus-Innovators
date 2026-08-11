from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .activity import grant_xp, record_activity
from .daily_quests import record_daily_quest_progress
from .models import Habit, User

# Reward for ticking a habit complete. Capped like everything else by
# activity.DAILY_XP_CAP, and only granted once per habit per day (see
# toggle_habit below) so re-checking the same box can't be farmed.
HABIT_COMPLETE_XP = 15


def sync_daily_habits(db: Session, user_id: int) -> list[Habit]:
    """Return the user's habits, lazily clearing any `complete` tick left over
    from a previous calendar day.

    There's no background job in this app, so instead of a midnight cron we
    just check the date every time habits are read: if a habit is still
    marked complete but that happened on an earlier day, it gets unticked
    right here before the caller sees it. `last_completed_on` itself is left
    alone, so streak/XP-once-per-day logic in toggle_habit still works.
    """
    today = date.today()
    habits = list(db.scalars(select(Habit).where(Habit.user_id == user_id).order_by(Habit.id)).all())
    changed = False
    for habit in habits:
        if habit.complete and habit.last_completed_on != today:
            habit.complete = False
            changed = True
    if changed:
        db.commit()
    return habits


def toggle_habit(db: Session, user: User, habit: Habit) -> int:
    """Flip a habit's complete state for today and return the XP granted (0 if none).

    Marking complete: ticks it on, bumps streak (reset to 1 if a day was
    missed, +1 if yesterday was completed), and grants XP — but only the
    first time this happens on a given calendar day, so toggling on/off
    repeatedly can't be used to farm XP or streak.
    Marking incomplete: just undoes today's tick and steps streak back down.
    Already-granted XP for today is not clawed back.
    """
    today = date.today()
    if habit.complete and habit.last_completed_on != today:
        habit.complete = False  # yesterday's tick doesn't carry over

    granted = 0
    if not habit.complete:
        already_credited_today = habit.last_completed_on == today
        habit.complete = True
        if not already_credited_today:
            consecutive = habit.last_completed_on is not None and (today - habit.last_completed_on).days == 1
            habit.streak = habit.streak + 1 if consecutive else 1
            habit.last_completed_on = today
            record_activity(db, user.id)
            granted = grant_xp(db, user, HABIT_COMPLETE_XP)
            record_daily_quest_progress(db, user, "habit")
    else:
        habit.complete = False
        habit.streak = max(habit.streak - 1, 0)

    return granted
