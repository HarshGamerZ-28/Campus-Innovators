from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from .models import Answer, Habit, Project, Task, TaskStreak

# --- Badges -------------------------------------------------------------------
# Badge *definitions* are static/code-defined (name, icon, unlock rule) — not user
# data — so they live here as a plain registry rather than a database table, the
# same way TASK_CATEGORIES/TASK_PRIORITIES in models.py are Python constants, not
# rows. Only the unlock *state* is per-user, and that's computed on read, not stored.

# Streak Master reads Habit.streak (per-habit "did you do this again today"
# streak), not TaskStreak — that one now backs Consistency King below, so each
# badge has a distinct, non-overlapping signal.
STREAK_MASTER_TARGET = 7
PROBLEM_SOLVER_TARGET = 3
PROJECT_BUILDER_TARGET = 2
CONSISTENCY_KING_TARGET = 7
# Task.completed_at is stored as UTC (see models.utcnow) and there's no per-user
# timezone anywhere on User, so "before 9am" is really "before 9am UTC" — an
# approximation, not a true local-morning signal. Flagged, accepted as a known
# limitation rather than adding new tracking in this pass.
EARLY_BIRD_HOUR_CUTOFF = 9
EARLY_BIRD_TARGET = 5


@dataclass(frozen=True)
class BadgeDefinition:
    key: str
    name: str
    description: str
    icon: str
    tone: str
    # Returns (current_progress, target). unlocked is current >= target.
    progress_fn: Callable[[Session, int], tuple[int, int]]


def _problem_solver_progress(db: Session, user_id: int) -> tuple[int, int]:
    current = db.scalar(
        select(func.count(Answer.id)).where(Answer.author_id == user_id, Answer.is_accepted.is_(True))
    ) or 0
    return current, PROBLEM_SOLVER_TARGET


def _streak_master_progress(db: Session, user_id: int) -> tuple[int, int]:
    current = db.scalar(select(func.max(Habit.streak)).where(Habit.user_id == user_id)) or 0
    return current, STREAK_MASTER_TARGET


def _early_bird_progress(db: Session, user_id: int) -> tuple[int, int]:
    current = db.scalar(
        select(func.count(Task.id)).where(
            Task.user_id == user_id,
            Task.completed_at.is_not(None),
            extract("hour", Task.completed_at) < EARLY_BIRD_HOUR_CUTOFF,
        )
    ) or 0
    return current, EARLY_BIRD_TARGET


def _project_builder_progress(db: Session, user_id: int) -> tuple[int, int]:
    current = db.scalar(select(func.count(Project.id)).where(Project.owner_id == user_id)) or 0
    return current, PROJECT_BUILDER_TARGET


def _consistency_king_progress(db: Session, user_id: int) -> tuple[int, int]:
    streak = db.get(TaskStreak, user_id)
    current = streak.current_streak if streak else 0
    return current, CONSISTENCY_KING_TARGET


BADGE_REGISTRY: list[BadgeDefinition] = [
    BadgeDefinition(
        key="problem_solver",
        name="Problem Solver",
        description="Get 3 of your answers accepted on the Q&A board.",
        icon="award",
        tone="purple",
        progress_fn=_problem_solver_progress,
    ),
    BadgeDefinition(
        key="streak_master",
        name="Streak Master",
        description="Keep any single habit going for 7 days in a row.",
        icon="flame",
        tone="orange",
        progress_fn=_streak_master_progress,
    ),
    BadgeDefinition(
        key="early_bird",
        name="Early Bird",
        description="Complete 5 tasks before 9am.",
        icon="sparkles",
        tone="gold",
        progress_fn=_early_bird_progress,
    ),
    BadgeDefinition(
        key="project_builder",
        name="Project Builder",
        description="Create 2 projects.",
        icon="hammer",
        tone="blue",
        progress_fn=_project_builder_progress,
    ),
    BadgeDefinition(
        key="consistency_king",
        name="Consistency King",
        description="Complete at least one task every day for 7 days straight.",
        icon="target",
        tone="green",
        progress_fn=_consistency_king_progress,
    ),
]


def compute_badges(db: Session, user_id: int) -> list[dict]:
    """Return every badge definition with this user's computed unlock state.

    Locked badges are returned with their current/target progress (not just a
    locked flag) so the UI can render a progress-toward-unlock indicator.
    """
    results = []
    for badge in BADGE_REGISTRY:
        current, target = badge.progress_fn(db, user_id)
        current = min(current, target)
        results.append(
            {
                "key": badge.key,
                "name": badge.name,
                "description": badge.description,
                "icon": badge.icon,
                "tone": badge.tone,
                "unlocked": current >= target,
                "progress_current": current,
                "progress_target": target,
            }
        )
    return results
