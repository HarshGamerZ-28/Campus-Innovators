from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..activity import activity_payload
from ..config import settings
from ..dashboard_data import build_dashboard, platform_payload
from ..database import get_db
from ..models import Post, Project, Skill, User, project_members
from ..schemas import SearchResult
from ..serializers import post_public, project_public, user_summary

router = APIRouter(prefix="/public", tags=["Public"])


@router.get("/home")
def public_home(db: Session = Depends(get_db)) -> dict:
    founder = db.scalar(select(User).where(User.email == settings.founder_email))
    if founder is None:
        founder = db.scalar(select(User).where(User.is_public.is_(True)).order_by(User.id))
    if founder is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Public dashboard is not configured")
    payload = build_dashboard(db, founder, private=False)
    payload["guest_mode"] = True
    return payload


@router.get("/platform")
def public_platform(db: Session = Depends(get_db)) -> dict:
    return platform_payload(db)


@router.get("/profiles/{username}")
def public_profile(username: str, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.username == username.lower().strip(), User.is_public.is_(True), User.is_active.is_(True)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public profile not found")

    projects = db.scalars(
        select(Project)
        .options(selectinload(Project.owner), selectinload(Project.members))
        .join(project_members, project_members.c.project_id == Project.id, isouter=True)
        .where(
            Project.is_public.is_(True),
            (Project.owner_id == user.id) | (project_members.c.user_id == user.id),
        )
        .distinct()
        .order_by(Project.updated_at.desc())
    ).all()
    posts = db.scalars(
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.likes))
        .where(Post.author_id == user.id, Post.is_public.is_(True))
        .order_by(Post.created_at.desc())
        .limit(30)
    ).all()
    skills = db.scalars(select(Skill).where(Skill.user_id == user.id).order_by(Skill.progress.desc())).all()
    answer_count = len(user.answers)

    return {
        "user": user_summary(user),
        "activity": activity_payload(db, user.id),
        "projects": [project_public(item) for item in projects],
        "current_projects": [project_public(item) for item in projects if item.status.lower() not in {"completed", "archived"}],
        "past_projects": [project_public(item) for item in projects if item.status.lower() in {"completed", "archived"}],
        "posts": [post_public(item) for item in posts],
        "skills": [{"id": item.id, "name": item.name, "progress": item.progress, "tone": item.tone, "is_mastered": item.is_mastered} for item in skills],
        "impact": {"posts": len(posts), "projects": len(projects), "answers": answer_count, "xp": user.xp},
    }


@router.get("/members")
def public_members(
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    limit = max(1, min(limit, 50))
    offset = max(0, offset)

    query = select(User).where(User.is_public.is_(True), User.is_active.is_(True))
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(or_(User.name.ilike(term), User.username.ilike(term), User.department.ilike(term)))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    users = db.scalars(query.order_by(User.xp.desc()).offset(offset).limit(limit)).all()
    user_ids = [user.id for user in users]

    skills_by_user: dict[int, list[Skill]] = {user_id: [] for user_id in user_ids}
    if user_ids:
        skills = db.scalars(
            select(Skill).where(Skill.user_id.in_(user_ids)).order_by(Skill.progress.desc())
        ).all()
        for skill in skills:
            skills_by_user.setdefault(skill.user_id, []).append(skill)

    projects_by_user: dict[int, Project] = {}
    if user_ids:
        projects = db.scalars(
            select(Project)
            .options(selectinload(Project.owner), selectinload(Project.members))
            .join(project_members, project_members.c.project_id == Project.id, isouter=True)
            .where(
                Project.is_public.is_(True),
                (Project.owner_id.in_(user_ids)) | (project_members.c.user_id.in_(user_ids)),
            )
            .distinct()
            .order_by(Project.updated_at.desc())
        ).all()
        for project in projects:
            member_ids = {project.owner_id, *(member.id for member in project.members)}
            for user_id in member_ids & set(user_ids):
                if user_id not in projects_by_user:
                    projects_by_user[user_id] = project

    members = []
    for user in users:
        top_skills = sorted(skills_by_user.get(user.id, []), key=lambda item: item.progress, reverse=True)[:3]
        current_project = projects_by_user.get(user.id)
        members.append({
            **user_summary(user),
            "top_skills": [{"name": skill.name, "tone": skill.tone, "is_mastered": skill.is_mastered} for skill in top_skills],
            "current_project": (
                {"name": current_project.name, "subtitle": current_project.subtitle}
                if current_project is not None
                else None
            ),
        })

    return {"members": members, "total": total, "limit": limit, "offset": offset}


@router.get("/search", response_model=list[SearchResult])
def public_search(q: str, db: Session = Depends(get_db)) -> list[SearchResult]:
    query = q.strip()
    if len(query) < 2:
        return []
    term = f"%{query}%"
    results: list[SearchResult] = []
    users = db.scalars(
        select(User)
        .where(User.is_public.is_(True), User.is_active.is_(True), or_(User.name.ilike(term), User.username.ilike(term), User.department.ilike(term)))
        .limit(8)
    ).all()
    results.extend(
        SearchResult(type="student", id=user.id, title=user.name, subtitle=f"@{user.username} · {user.department}", username=user.username)
        for user in users
    )
    projects = db.scalars(
        select(Project).where(Project.is_public.is_(True), or_(Project.name.ilike(term), Project.subtitle.ilike(term))).limit(5)
    ).all()
    results.extend(SearchResult(type="project", id=item.id, title=item.name, subtitle=item.subtitle) for item in projects)
    return results[:12]
