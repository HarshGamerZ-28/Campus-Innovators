from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .activity import grant_xp, record_activity
from .daily_quests import record_daily_quest_progress
from .models import Habit, HabitLog, Task, TaskStreak, User, utcnow

HABIT_HISTORY_DAYS = 7

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


def _record_habit_log(db: Session, habit: Habit, log_date: date, completed: bool) -> None:
    """Upsert today's HabitLog row so it reflects the state the user last left
    the habit in. Called on every toggle (on AND off) — an un-check still
    writes a `completed=False` row rather than deleting it, so the 7-day
    history shows an explicit "not done" for that day rather than a gap.
    """
    log = db.scalar(select(HabitLog).where(HabitLog.habit_id == habit.id, HabitLog.log_date == log_date))
    if log is None:
        log = HabitLog(habit_id=habit.id, log_date=log_date, completed=completed)
        db.add(log)
    else:
        log.completed = completed


def get_habit_history(db: Session, habit_id: int, days: int = HABIT_HISTORY_DAYS) -> list[dict]:
    """Return the last `days` calendar days for a habit, oldest first, each as
    {"date": "YYYY-MM-DD", "completed": bool}. Days with no HabitLog row
    (never toggled, e.g. a brand-new habit) show completed=False rather than
    being omitted, so the result always has exactly `days` entries.
    """
    today = date.today()
    start = today - timedelta(days=days - 1)
    logs = db.scalars(
        select(HabitLog).where(HabitLog.habit_id == habit_id, HabitLog.log_date >= start, HabitLog.log_date <= today)
    ).all()
    completed_by_date = {log.log_date: log.completed for log in logs}
    return [
        {"date": (start + timedelta(days=offset)).isoformat(), "completed": completed_by_date.get(start + timedelta(days=offset), False)}
        for offset in range(days)
    ]


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
        _record_habit_log(db, habit, today, True)
    else:
        habit.complete = False
        habit.streak = max(habit.streak - 1, 0)
        _record_habit_log(db, habit, today, False)

    return granted


# --- Smart Task Management ---------------------------------------------------
# Task-specific XP/streak/progress logic, mirroring the habit flow above (its own
# XP constant, capped via grant_xp, same once-per-day-style guard via xp_awarded).

TASK_COMPLETE_XP = 15


def _get_or_create_task_streak(db: Session, user_id: int) -> TaskStreak:
    streak = db.get(TaskStreak, user_id)
    if streak is None:
        streak = TaskStreak(user_id=user_id, current_streak=0, longest_streak=0, last_completed_date=None)
        db.add(streak)
    return streak


def _bump_task_streak(db: Session, user_id: int) -> None:
    streak = _get_or_create_task_streak(db, user_id)
    today = date.today()
    if streak.last_completed_date == today:
        pass  # already counted today, no change
    elif streak.last_completed_date is not None and (today - streak.last_completed_date).days == 1:
        streak.current_streak += 1
    else:
        streak.current_streak = 1
    streak.longest_streak = max(streak.longest_streak, streak.current_streak)
    streak.last_completed_date = today


def _complete_task(db: Session, user: User, task: Task) -> int:
    """Mark `task` completed: sets completed_at, awards XP once, bumps the task streak.

    Returns the XP actually granted (0 if already awarded or the daily cap was hit).
    """
    task.completed_at = utcnow()
    granted = 0
    if not task.xp_awarded:
        granted = grant_xp(db, user, TASK_COMPLETE_XP)
        task.xp_awarded = True
    _bump_task_streak(db, user.id)
    return granted


def set_task_status(db: Session, user: User, task: Task, new_status: str) -> int:
    """Apply a status change to `task`, running completion side effects when the
    task newly transitions into "completed". Reverting away from "completed"
    intentionally does not revoke XP or decrement the streak (see spec)."""
    was_completed = task.status == "completed"
    task.status = new_status
    if new_status == "completed" and not was_completed:
        return _complete_task(db, user, task)
    return 0


def recalc_subtask_progress(db: Session, user: User, task: Task) -> int:
    """Recompute `task.progress_percentage` from its subtasks and auto-complete
    the task if every subtask is done. Returns any XP granted by that auto-completion.

    No-ops (leaves progress/status alone) when the task has no subtasks, since
    then progress is manually settable via status instead.
    """
    subtasks = list(task.subtasks)
    if not subtasks:
        return 0
    completed = sum(1 for s in subtasks if s.is_completed)
    task.progress_percentage = round((completed / len(subtasks)) * 100)
    if completed == len(subtasks) and task.status != "completed":
        return set_task_status(db, user, task, "completed")
    return 0


def task_stats(db: Session, user_id: int) -> dict:
    tasks = list(db.scalars(select(Task).where(Task.user_id == user_id)).all())
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == "completed")
    in_progress = sum(1 for t in tasks if t.status == "in_progress")
    todo = sum(1 for t in tasks if t.status == "todo")
    completion_rate = round((completed / total) * 100, 1) if total else 0.0
    streak = db.get(TaskStreak, user_id)
    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "todo": todo,
        "completion_rate": completion_rate,
        "current_streak": streak.current_streak if streak else 0,
        "longest_streak": streak.longest_streak if streak else 0,
    }
