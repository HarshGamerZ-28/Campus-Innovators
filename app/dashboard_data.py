from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .activity import activity_payload
from .badges import compute_badges
from .config import settings
from .daily_quests import DAILY_QUEST_TEMPLATES, sync_daily_quest
from .habits import get_habit_history, sync_daily_habits
from .models import PlatformSetting, Post, Project, Quest, Skill, User, project_members
from .serializers import project_public, user_private, user_summary


def platform_payload(db: Session) -> dict:
    rows = db.scalars(select(PlatformSetting)).all()
    values = {item.key: item.value for item in rows}
    return {
        "intro_video_url": values.get("intro_video_url", settings.intro_video_url),
        "intro_video_title": values.get("intro_video_title", "Welcome to Campus Innovators"),
        "intro_video_description": values.get(
            "intro_video_description",
            "See how students learn, solve problems and build projects together.",
        ),
        # Club-wide social links (not per-user). Stored as "" when unset/cleared —
        # PlatformSetting.value is a non-nullable Text column, so empty string is
        # this table's existing convention for "no value" (same as intro_video_url
        # above); the public payload surfaces "" rather than null for the same reason.
        "club_instagram_url": values.get("club_instagram_url", ""),
        "club_linkedin_url": values.get("club_linkedin_url", ""),
    }


def build_dashboard(db: Session, user: User, private: bool = True) -> dict:
    projects = db.scalars(
        select(Project)
        .options(selectinload(Project.owner), selectinload(Project.members))
        .join(project_members, project_members.c.project_id == Project.id, isouter=True)
        .where((Project.owner_id == user.id) | (project_members.c.user_id == user.id))
        .distinct()
        .order_by(Project.updated_at.desc())
        .limit(3)
    ).all()
    skills = db.scalars(select(Skill).where(Skill.user_id == user.id).order_by(Skill.id)).all()
    habits = sync_daily_habits(db, user.id)
    sync_daily_quest(db, user)
    db.commit()
    quests = db.scalars(select(Quest).where(Quest.user_id == user.id).order_by(Quest.is_daily.desc(), Quest.id)).all()
    connections = db.scalar(select(func.count(User.id)).where(User.id != user.id, User.is_public.is_(True))) or 0
    rank = db.scalar(select(func.count(User.id)).where(User.xp > user.xp)) or 0
    contribution_count = db.scalar(select(func.count(Post.id)).where(Post.author_id == user.id)) or 0

    return {
        "user": user_private(user) if private else user_summary(user),
        "stats": [
            {"label": "Streak", "value": user.streak, "tone": "orange", "icon": "flame"},
            {"label": "Rank", "value": rank + 1, "prefix": "#", "tone": "gold", "icon": "trophy"},
            {"label": "Impact XP", "value": user.xp + contribution_count * 25, "tone": "purple", "icon": "target"},
            {"label": "Connections", "value": connections, "tone": "green", "icon": "users"},
        ],
        "quests": [
            {
                "id": item.id,
                "title": item.title,
                "current": item.current,
                "target": item.target,
                "reward_xp": item.reward_xp,
                "claimed": item.claimed,
                "is_daily": item.is_daily,
                "cycle_day": (item.cycle_index + 1) if item.is_daily and item.cycle_index is not None else None,
                "cycle_length": len(DAILY_QUEST_TEMPLATES) if item.is_daily else None,
            }
            for item in quests
        ],
        "skills": [{"id": item.id, "name": item.name, "progress": item.progress, "tone": item.tone, "category": item.category} for item in skills],
        "habits": [
            {
                "id": item.id,
                "label": item.label,
                "complete": item.complete,
                "streak": item.streak,
                "tone": item.tone,
                "last_7_days": get_habit_history(db, item.id),
            }
            for item in habits
        ],
        "projects": [project_public(project, user.id if private else None) for project in projects if private or project.is_public],
        # Dashboard "Achievements" panel only renders label/tone/icon with no locked
        # state today, so only genuinely unlocked badges are surfaced here. The full
        # per-badge unlocked/progress breakdown (including locked ones) is available
        # from GET /badges for a future progress-aware UI.
        "achievements": [
            {"label": item["name"], "tone": item["tone"], "icon": item["icon"]}
            for item in compute_badges(db, user.id)
            if item["unlocked"]
        ],
        "activity": activity_payload(db, user.id),
        "platform": platform_payload(db),
    }
