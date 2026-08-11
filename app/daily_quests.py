from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Quest, User

# One themed quest per day of a 7-day cycle. `action` is the internal key
# other routers call `record_daily_quest_progress(db, user, action)` with —
# it's how a real action (asking a question, completing a habit, ...)
# is recognised as progress toward *today's* quest specifically.
DAILY_QUEST_TEMPLATES = [
    {"title": "Complete a habit today", "target": 1, "reward_xp": 25, "action": "habit"},
    {"title": "Ask a question in Ask Seniors", "target": 1, "reward_xp": 25, "action": "ask_question"},
    {"title": "Answer a question in Ask Seniors", "target": 1, "reward_xp": 25, "action": "answer_question"},
    {"title": "Share a post in Community", "target": 1, "reward_xp": 25, "action": "post"},
    {"title": "Join a project", "target": 1, "reward_xp": 25, "action": "join_project"},
    {"title": "Register for an event", "target": 1, "reward_xp": 25, "action": "register_event"},
    {"title": "Make progress on a skill", "target": 1, "reward_xp": 25, "action": "update_skill"},
]
CYCLE_LENGTH = len(DAILY_QUEST_TEMPLATES)

# Fixed anchor date the cycle counts from. Arbitrary — just needs to never
# change once set, so every user always lands on the same day-of-cycle and
# the 7 templates keep repeating in the same order forever.
CYCLE_EPOCH = date(2026, 1, 5)


def cycle_index_for(day: date) -> int:
    return (day - CYCLE_EPOCH).days % CYCLE_LENGTH


def sync_daily_quest(db: Session, user: User) -> Quest:
    """Get today's daily quest for `user`, creating or re-rolling it as needed.

    A user has exactly one `is_daily` quest row, ever — instead of inserting
    a new one each day, this rewrites it in place with today's template
    whenever `assigned_on` isn't today. That's what makes the cycle "repeat":
    day 7 rewrites the same row back to day 0's template, day 8 to day 1's,
    and so on indefinitely.
    """
    today = date.today()
    idx = cycle_index_for(today)
    template = DAILY_QUEST_TEMPLATES[idx]

    quest = db.scalar(select(Quest).where(Quest.user_id == user.id, Quest.is_daily.is_(True)))
    if quest is None:
        quest = Quest(
            user_id=user.id,
            is_daily=True,
            title=template["title"],
            current=0,
            target=template["target"],
            reward_xp=template["reward_xp"],
            claimed=False,
            cycle_index=idx,
            assigned_on=today,
        )
        db.add(quest)
        db.flush()
    elif quest.assigned_on != today:
        quest.title = template["title"]
        quest.target = template["target"]
        quest.reward_xp = template["reward_xp"]
        quest.cycle_index = idx
        quest.assigned_on = today
        quest.current = 0
        quest.claimed = False
    return quest


def record_daily_quest_progress(db: Session, user: User, action: str, amount: int = 1) -> None:
    """Bump today's daily quest if `action` matches what it's asking for.

    Safe to call from any router after a real action happens — it's a no-op
    if today's quest is for something else, already complete, or already
    claimed. Does not commit; the caller's existing db.commit() covers it.
    """
    quest = sync_daily_quest(db, user)
    if quest.claimed or quest.current >= quest.target:
        return
    template = DAILY_QUEST_TEMPLATES[quest.cycle_index]
    if template["action"] != action:
        return
    quest.current = min(quest.current + amount, quest.target)
