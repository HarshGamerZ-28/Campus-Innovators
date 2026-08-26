from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..activity import grant_xp, record_activity
from ..daily_quests import record_daily_quest_progress
from ..database import get_db
from ..deps import get_current_user
from ..models import Notification, Post, PostLike, User
from ..realtime import manager
from ..schemas import PostCreate
from ..serializers import post_public

router = APIRouter(prefix="/community", tags=["Community"])


@router.get("/posts")
def list_posts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    posts = db.scalars(
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.likes))
        .order_by(Post.created_at.desc())
        .limit(100)
    ).all()
    return [post_public(post, current_user.id) for post in posts]


@router.post("/posts", status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: PostCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    post = Post(body=payload.body.strip(), category=payload.category.strip(), author_id=current_user.id)
    db.add(post)
    record_activity(db, current_user.id, 2)
    grant_xp(db, current_user, 10)
    record_daily_quest_progress(db, current_user, "post")
    db.commit()
    post = db.scalar(
        select(Post).where(Post.id == post.id).options(selectinload(Post.author), selectinload(Post.likes))
    )
    await manager.broadcast({"type": "post.created", "message": f"{current_user.name} shared a new campus update."})
    return post_public(post, current_user.id)


@router.post("/posts/{post_id}/like")
def toggle_like(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    post = db.scalar(
        select(Post).where(Post.id == post_id).options(selectinload(Post.author), selectinload(Post.likes))
    )
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    like = db.scalar(select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == current_user.id))
    if like:
        db.delete(like)
        liked = False
    else:
        db.add(PostLike(post_id=post_id, user_id=current_user.id))
        liked = True
        if post.author_id != current_user.id:
            db.add(Notification(user_id=post.author_id, message=f"{current_user.name} liked your post.", kind="like"))
    db.commit()
    post = db.scalar(
        select(Post).where(Post.id == post_id).options(selectinload(Post.author), selectinload(Post.likes))
    )
    return {"liked": liked, "likes": len(post.likes)}
