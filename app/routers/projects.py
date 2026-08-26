from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..activity import grant_xp, record_activity
from ..daily_quests import record_daily_quest_progress
from ..database import get_db
from ..deps import get_current_user
from ..models import Project, Quest, User
from ..schemas import ProjectCreate
from ..serializers import project_public

router = APIRouter(prefix="/projects", tags=["Projects"])


def project_query():
    return select(Project).options(selectinload(Project.owner), selectinload(Project.members))


@router.get("")
def list_projects(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    projects = db.scalars(project_query().order_by(Project.created_at.desc())).all()
    return [project_public(project, current_user.id) for project in projects]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = Project(
        name=payload.name.strip(),
        subtitle=payload.subtitle.strip(),
        description=payload.description.strip(),
        image_url=payload.image_url.strip(),
        github_url=payload.github_url.strip(),
        demo_url=payload.demo_url.strip(),
        status=payload.status.strip(),
        owner_id=current_user.id,
    )
    project.members.append(current_user)
    db.add(project)
    quest = db.scalar(select(Quest).where(Quest.user_id == current_user.id, Quest.title == "Join a Project"))
    if quest:
        quest.current = quest.target
    grant_xp(db, current_user, 20)
    record_activity(db, current_user.id, 3)
    db.commit()
    project = db.scalar(project_query().where(Project.id == project.id))
    return project_public(project, current_user.id)


@router.post("/{project_id}/join")
def toggle_join(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = db.scalar(project_query().where(Project.id == project_id))
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    member = next((item for item in project.members if item.id == current_user.id), None)
    if member:
        if project.owner_id == current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project owner cannot leave the project")
        project.members.remove(member)
        joined = False
    else:
        project.members.append(current_user)
        joined = True
        quest = db.scalar(select(Quest).where(Quest.user_id == current_user.id, Quest.title == "Join a Project"))
        if quest:
            quest.current = quest.target
        # This endpoint toggles membership, so a user could join/leave/rejoin the same
        # project repeatedly. `grant_xp`'s daily cap bounds how much XP that loop can
        # yield instead of letting it farm the leaderboard without limit.
        grant_xp(db, current_user, 10)
        record_activity(db, current_user.id)
        record_daily_quest_progress(db, current_user, "join_project")
    db.commit()
    return {"joined": joined, "member_count": len(project.members)}
