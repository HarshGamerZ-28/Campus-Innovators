from __future__ import annotations

from .models import Event, Post, Project, Question, User


def user_summary(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "role": user.role,
        "department": user.department,
        "year": user.year,
        "bio": user.bio,
        "avatar_key": user.avatar_key,
        "avatar_url": user.avatar_url,
        "hero_avatar_url": user.hero_avatar_url,
        "level": user.level,
        "xp": user.xp,
        "next_xp": user.next_xp,
        "coins": user.coins,
        "streak": user.streak,
        "is_public": user.is_public,
        "created_at": user.created_at,
    }


def user_private(user: User) -> dict:
    return {
        **user_summary(user),
        "email": user.email,
        "email_verified": user.email_verified,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at,
    }


def post_public(post: Post, current_user_id: int | None = None) -> dict:
    return {
        "id": post.id,
        "body": post.body,
        "category": post.category,
        "created_at": post.created_at,
        "author": user_summary(post.author),
        "likes": len(post.likes),
        "liked_by_me": current_user_id is not None and any(like.user_id == current_user_id for like in post.likes),
    }


def question_public(question: Question, include_answers: bool = False) -> dict:
    payload = {
        "id": question.id,
        "title": question.title,
        "body": question.body,
        "tags": [tag for tag in question.tags.split(",") if tag],
        "solved": question.solved,
        "created_at": question.created_at,
        "author": user_summary(question.author),
        "answer_count": len(question.answers),
    }
    if include_answers:
        payload["answers"] = [
            {
                "id": answer.id,
                "body": answer.body,
                "is_accepted": answer.is_accepted,
                "created_at": answer.created_at,
                "author": user_summary(answer.author),
            }
            for answer in sorted(question.answers, key=lambda item: item.created_at)
        ]
    return payload


def project_public(project: Project, current_user_id: int | None = None) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "subtitle": project.subtitle,
        "description": project.description,
        "status": project.status,
        "image_url": project.image_url,
        "github_url": project.github_url,
        "demo_url": project.demo_url,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "owner": user_summary(project.owner),
        "member_count": len(project.members),
        "joined": current_user_id is not None and any(member.id == current_user_id for member in project.members),
    }


def event_public(event: Event, current_user_id: int | None = None) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "venue": event.venue,
        "event_date": event.event_date,
        "capacity": event.capacity,
        "registered_count": len(event.registrations),
        "registered": current_user_id is not None and any(item.user_id == current_user_id for item in event.registrations),
        "organizer": user_summary(event.organizer),
    }
