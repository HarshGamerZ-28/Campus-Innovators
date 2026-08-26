from __future__ import annotations

import os
import re

from sqlalchemy import select

from .config import settings
from .database import SessionLocal
from .models import Avatar, Habit, Quest, Skill, User
from .security import hash_password
from .seed import seed_avatars, seed_platform


def main() -> None:
    password = os.getenv("FOUNDER_PASSWORD", "")
    if len(password) < 12 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not any(c.isdigit() for c in password):
        raise SystemExit("Set FOUNDER_PASSWORD to at least 12 characters with uppercase, lowercase and a number.")
    username = os.getenv("FOUNDER_USERNAME", "campusinnovator").lower().strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,28}[a-z0-9]", username):
        raise SystemExit("FOUNDER_USERNAME is invalid.")

    with SessionLocal() as db:
        seed_avatars(db)
        seed_platform(db)
        avatar = db.scalar(select(Avatar).where(Avatar.key == "divine-archer"))
        user = db.scalar(select(User).where(User.email == settings.founder_email))
        if user is None:
            user = User(
                name=os.getenv("FOUNDER_NAME", "Campus Innovator"),
                username=username,
                email=settings.founder_email,
                hashed_password=hash_password(password),
                role="Founder",
                department=os.getenv("FOUNDER_DEPARTMENT", "Computer Science & Engineering"),
                year=os.getenv("FOUNDER_YEAR", "2nd Year"),
                bio=os.getenv("FOUNDER_BIO", "Building useful products and helping the campus community."),
                avatar_key=avatar.key,
                avatar_url=avatar.image_url,
                hero_avatar_url=avatar.hero_image_url,
                email_verified=True,
            )
            db.add(user)
            db.flush()
            db.add_all([
                Skill(user_id=user.id, name="React.js", progress=50, tone="blue", category="skill"),
                Skill(user_id=user.id, name="FastAPI", progress=50, tone="cyan", category="learning"),
                Habit(user_id=user.id, label="Study", complete=False, streak=0, tone="blue"),
                Habit(user_id=user.id, label="Code", complete=False, streak=0, tone="green"),
                Quest(user_id=user.id, title="Complete Your Profile", current=1, target=1, reward_xp=40),
            ])
            action = "created"
        else:
            user.hashed_password = hash_password(password)
            user.role = "Founder"
            user.avatar_key = avatar.key
            user.avatar_url = avatar.image_url
            user.hero_avatar_url = avatar.hero_image_url
            user.is_active = True
            user.email_verified = True
            action = "updated"
        db.commit()
        print(f"Founder account {action}: {settings.founder_email} (@{user.username})")


if __name__ == "__main__":
    main()
