from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..activity import grant_xp, record_activity
from ..badges import compute_badges
from ..daily_quests import record_daily_quest_progress
from ..database import get_db
from ..deps import get_current_user
from ..habits import get_habit_history
from ..habits import toggle_habit as apply_habit_toggle
from ..habits import sync_daily_habits
from ..models import Avatar, Habit, Notification, Project, Quest, Question, Skill, User
from ..schemas import BadgeOut, HabitCreate, ProfileUpdate, SearchResult, SkillCreate, SkillUpdate
from ..serializers import user_private, user_summary

router = APIRouter(tags=["Account"])


def _select_avatar(db: Session, user: User, key: str) -> Avatar:
    avatar = db.scalar(select(Avatar).where(Avatar.key == key, Avatar.is_active.is_(True)))
    if avatar is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected avatar is unavailable")
    if avatar.reserved_email and avatar.reserved_email.lower() != user.email.lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="That avatar is reserved")
    return avatar


@router.patch("/profile")
def update_profile(payload: ProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    avatar_key = updates.pop("avatar_key", None)
    for field, value in updates.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(current_user, field, value)
    if avatar_key:
        avatar = _select_avatar(db, current_user, avatar_key)
        current_user.avatar_key = avatar.key
        current_user.avatar_url = avatar.image_url
        current_user.hero_avatar_url = avatar.hero_image_url
    onboarding = db.scalar(select(Quest).where(Quest.user_id == current_user.id, Quest.title == "Complete Your Profile"))
    if onboarding and current_user.name and current_user.department and current_user.bio:
        onboarding.current = onboarding.target
    record_activity(db, current_user.id)
    db.commit()
    db.refresh(current_user)
    return user_private(current_user)


@router.get("/skills")
def list_skills(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    skills = db.scalars(select(Skill).where(Skill.user_id == current_user.id).order_by(Skill.id)).all()
    return [{"id": item.id, "name": item.name, "progress": item.progress, "tone": item.tone, "category": item.category, "is_mastered": item.is_mastered} for item in skills]


@router.post("/skills", status_code=status.HTTP_201_CREATED)
def create_skill(payload: SkillCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    skill = Skill(user_id=current_user.id, name=payload.name, category=payload.category, tone=payload.tone, progress=payload.progress)
    db.add(skill)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You already have an entry with that name")
    record_activity(db, current_user.id)
    db.commit()
    return {"id": skill.id, "name": skill.name, "progress": skill.progress, "tone": skill.tone, "category": skill.category, "is_mastered": skill.is_mastered}


@router.patch("/skills/{skill_id}")
def update_skill(skill_id: int, payload: SkillUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    skill = db.scalar(select(Skill).where(Skill.id == skill_id, Skill.user_id == current_user.id))
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    skill.progress = payload.progress
    record_activity(db, current_user.id)
    record_daily_quest_progress(db, current_user, "update_skill")
    db.commit()
    return {"id": skill.id, "name": skill.name, "progress": skill.progress, "tone": skill.tone, "category": skill.category, "is_mastered": skill.is_mastered}


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(skill_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    skill = db.scalar(select(Skill).where(Skill.id == skill_id))
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    if skill.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot remove another member's entry")
    db.delete(skill)
    db.commit()


@router.get("/habits")
def list_habits(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    habits = sync_daily_habits(db, current_user.id)
    return [
        {
            "id": h.id,
            "label": h.label,
            "complete": h.complete,
            "streak": h.streak,
            "tone": h.tone,
            "last_7_days": get_habit_history(db, h.id),
        }
        for h in habits
    ]


@router.post("/habits", status_code=status.HTTP_201_CREATED)
def create_habit(payload: HabitCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    habit = Habit(user_id=current_user.id, label=payload.label, tone=payload.tone)
    db.add(habit)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You already have a habit with that name")
    record_activity(db, current_user.id)
    db.commit()
    return {
        "id": habit.id,
        "label": habit.label,
        "complete": habit.complete,
        "streak": habit.streak,
        "tone": habit.tone,
        "last_7_days": get_habit_history(db, habit.id),
    }


@router.delete("/habits/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_habit(habit_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    habit = db.scalar(select(Habit).where(Habit.id == habit_id))
    if habit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habit not found")
    if habit.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot remove another member's habit")
    db.delete(habit)
    db.commit()


@router.post("/habits/{habit_id}/toggle")
def toggle_habit_route(habit_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    habit = db.scalar(select(Habit).where(Habit.id == habit_id, Habit.user_id == current_user.id))
    if habit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habit not found")
    granted = apply_habit_toggle(db, current_user, habit)
    db.commit()
    db.refresh(current_user)
    return {
        "id": habit.id,
        "complete": habit.complete,
        "streak": habit.streak,
        "last_7_days": get_habit_history(db, habit.id),
        "xp_gained": granted,
        "xp": current_user.xp,
        "level": current_user.level,
        "next_xp": current_user.next_xp,
        "coins": current_user.coins,
    }


@router.post("/quests/{quest_id}/claim")
def claim_quest(quest_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    quest = db.scalar(select(Quest).where(Quest.id == quest_id, Quest.user_id == current_user.id))
    if quest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quest not found")
    if quest.claimed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reward already claimed")
    if quest.current < quest.target:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quest is not complete")
    quest.claimed = True
    grant_xp(db, current_user, quest.reward_xp)
    current_user.coins += max(quest.reward_xp // 2, 1)
    record_activity(db, current_user.id, 2)
    db.add(Notification(user_id=current_user.id, message=f"Quest reward claimed: +{quest.reward_xp} XP", kind="achievement"))
    db.commit()
    return {"claimed": True, "xp": current_user.xp, "coins": current_user.coins}


@router.get("/badges", response_model=list[BadgeOut])
def badges(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return compute_badges(db, current_user.id)


@router.get("/leaderboard")
def leaderboard(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    users = db.scalars(select(User).where(User.is_public.is_(True)).order_by(User.xp.desc(), User.created_at).limit(100)).all()
    return [{"rank": index + 1, **user_summary(user), "is_me": user.id == current_user.id} for index, user in enumerate(users)]


@router.get("/search", response_model=list[SearchResult])
def search(q: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SearchResult]:
    term_text = q.strip()
    if len(term_text) < 2:
        return []
    term = f"%{term_text}%"
    results: list[SearchResult] = []
    users = db.scalars(select(User).where(User.is_public.is_(True), or_(User.name.ilike(term), User.username.ilike(term), User.department.ilike(term))).limit(5)).all()
    results.extend(SearchResult(type="student", id=user.id, title=user.name, subtitle=f"@{user.username} · {user.department}", username=user.username) for user in users)
    projects = db.scalars(select(Project).where(Project.is_public.is_(True), or_(Project.name.ilike(term), Project.subtitle.ilike(term))).limit(5)).all()
    results.extend(SearchResult(type="project", id=item.id, title=item.name, subtitle=item.subtitle) for item in projects)
    questions = db.scalars(select(Question).where(or_(Question.title.ilike(term), Question.tags.ilike(term))).limit(5)).all()
    results.extend(SearchResult(type="question", id=item.id, title=item.title, subtitle="Ask Seniors") for item in questions)
    return results[:12]
