from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .activity import xp_threshold_for_level
from .config import settings
from .models import (
    ActivityDay,
    Answer,
    Avatar,
    Event,
    EventRegistration,
    Habit,
    Notification,
    PlatformSetting,
    Post,
    PostLike,
    Project,
    Quest,
    Question,
    Skill,
    User,
)
from .security import hash_password


def seed_avatars(db: Session) -> None:
    specs = [
        {
            "key": f"avatar-{index:02d}",
            "label": f"Campus Hero {index:02d}",
            "image_url": f"/assets/avatars/avatar-{index:02d}.webp",
            "hero_image_url": f"/assets/avatars/avatar-{index:02d}.webp",
            "reserved_email": None,
            "sort_order": index,
        }
        for index in range(1, 14)
    ]
    specs.append(
        {
            "key": "divine-archer",
            "label": "Divine Archer",
            "image_url": "/assets/avatars/divine-archer.webp",
            "hero_image_url": "/assets/avatars/divine-archer-hero.webp",
            "reserved_email": settings.founder_email,
            "sort_order": 999,
        }
    )
    for spec in specs:
        avatar = db.scalar(select(Avatar).where(Avatar.key == spec["key"]))
        if avatar is None:
            db.add(Avatar(**spec))
            continue
        for field, value in spec.items():
            setattr(avatar, field, value)
        avatar.is_active = True
    db.flush()


def seed_platform(db: Session) -> None:
    defaults = {
        "intro_video_url": settings.intro_video_url,
        "intro_video_title": "Welcome to Campus Innovators",
        "intro_video_description": "See how students learn, ask seniors, collaborate and turn ideas into real projects.",
    }
    for key, value in defaults.items():
        if db.get(PlatformSetting, key) is None:
            db.add(PlatformSetting(key=key, value=value))


def seed_activity(db: Session, user_id: int, intensity: int = 1) -> None:
    today = date.today()
    for offset in range(0, 365):
        # Deterministic but natural-looking contribution history.
        if (offset * 7 + user_id * 11) % 13 in {0, 1, 3, 5, 8}:
            count = 1 + ((offset + user_id) % (4 + intensity))
            db.add(ActivityDay(user_id=user_id, activity_date=today - timedelta(days=offset), count=count))


def seed_database(db: Session) -> None:
    """Seed avatars/platform settings always; seed fictional demo members only
    when explicitly opted in via SEED_DEMO_DATA, on a database that has zero
    users, and never in production (enforced in config.py at startup).

    Everything below this point — the four users, their projects, posts,
    questions and events — is sample/demo content only. It exists so a local
    checkout or a public demo deployment has something to look at. A real
    production deployment should leave SEED_DEMO_DATA unset (false) and
    create its one real account with `python -m app.bootstrap_admin` instead.
    """
    seed_avatars(db)
    seed_platform(db)
    if (db.scalar(select(func.count(User.id))) or 0) > 0:
        db.commit()
        return
    if not settings.seed_demo_data:
        db.commit()
        return

    # --- Demo dataset starts here: fictional members, not real people. ---
    founder = User(
        name="Campus Innovator",
        username="campusinnovator",
        email=settings.founder_email,
        hashed_password=hash_password(settings.founder_password),
        role="Founder",
        department="Computer Science & Engineering",
        year="2nd Year",
        bio="Building useful products, learning full-stack development and helping other students solve problems.",
        avatar_key="divine-archer",
        avatar_url="/assets/avatars/divine-archer.webp",
        hero_avatar_url="/assets/avatars/divine-archer-hero.webp",
        level=14,
        xp=2580,
        next_xp=xp_threshold_for_level(14),
        coins=620,
        streak=48,
        email_verified=True,
    )
    aarav = User(
        name="Aarav Mehta",
        username="aaravmehta",
        email="aarav@campusinnovators.in",
        hashed_password=hash_password("Campus@123"),
        role="Senior Mentor",
        department="Computer Science & Engineering",
        year="4th Year",
        bio="DSA mentor and competitive programmer.",
        avatar_key="avatar-02",
        avatar_url="/assets/avatars/avatar-02.webp",
        hero_avatar_url="/assets/avatars/avatar-02.webp",
        level=18,
        xp=8120,
        next_xp=xp_threshold_for_level(18),
        coins=940,
        streak=62,
        email_verified=True,
    )
    nisha = User(
        name="Nisha Sharma",
        username="nishasharma",
        email="nisha@campusinnovators.in",
        hashed_password=hash_password("Campus@123"),
        role="Club Lead",
        department="Electronics & Communication",
        year="3rd Year",
        bio="Robotics club lead and embedded systems enthusiast.",
        avatar_key="avatar-07",
        avatar_url="/assets/avatars/avatar-07.webp",
        hero_avatar_url="/assets/avatars/avatar-07.webp",
        level=16,
        xp=6320,
        next_xp=xp_threshold_for_level(16),
        coins=780,
        streak=39,
        email_verified=True,
    )
    rohan = User(
        name="Rohan Kapoor",
        username="rohankapoor",
        email="rohan@campusinnovators.in",
        hashed_password=hash_password("Campus@123"),
        role="Designer",
        department="Information Technology",
        year="3rd Year",
        bio="UI/UX designer and frontend developer.",
        avatar_key="avatar-10",
        avatar_url="/assets/avatars/avatar-10.webp",
        hero_avatar_url="/assets/avatars/avatar-10.webp",
        level=13,
        xp=4200,
        next_xp=xp_threshold_for_level(13),
        coins=560,
        streak=27,
        email_verified=True,
    )
    db.add_all([founder, aarav, nisha, rohan])
    db.flush()

    for user, intensity in [(founder, 4), (aarav, 5), (nisha, 3), (rohan, 2)]:
        seed_activity(db, user.id, intensity)

    for name, progress, tone, category in [
        ("React.js", 75, "blue", "skill"),
        ("FastAPI", 68, "cyan", "skill"),
        ("PostgreSQL", 44, "green", "learning"),
        ("System Design", 30, "purple", "learning"),
    ]:
        db.add(Skill(user_id=founder.id, name=name, progress=progress, tone=tone, category=category))

    for label, complete, streak, tone in [
        ("Study", True, 48, "blue"),
        ("Code", True, 45, "green"),
        ("Workout", True, 21, "purple"),
        ("Read", True, 32, "gold"),
        ("Mentor", False, 8, "red"),
    ]:
        db.add(Habit(user_id=founder.id, label=label, complete=complete, streak=streak, tone=tone))

    for title, current, target, reward, claimed in [
        ("Solve 2 Student Queries", 2, 2, 40, False),
        ("Study for 2 Hours", 1, 2, 30, False),
        ("Read 20 Pages", 20, 20, 25, True),
        ("Attend Club Meetup", 0, 1, 20, False),
    ]:
        db.add(Quest(user_id=founder.id, title=title, current=current, target=target, reward_xp=reward, claimed=claimed))

    projects = [
        Project(
            name="Campus Connect",
            subtitle="College Networking Platform",
            description="A single place for student updates, mentoring, clubs, opportunities and project collaboration.",
            status="In Progress",
            image_url="/assets/project-campus.jpg",
            github_url="https://github.com/campusinnovators",
            owner_id=founder.id,
        ),
        Project(
            name="AI Study Buddy",
            subtitle="AI-powered study assistant",
            description="Turns notes into quizzes, summaries and revision plans for college students.",
            status="In Progress",
            image_url="/assets/project-ai.jpg",
            owner_id=aarav.id,
        ),
        Project(
            name="Portfolio Website",
            subtitle="Personal developer portfolio",
            description="A responsive portfolio showcasing projects, skills and achievements.",
            status="Completed",
            image_url="/assets/project-portfolio.jpg",
            owner_id=founder.id,
        ),
        Project(
            name="Smart Attendance",
            subtitle="QR and analytics based attendance",
            description="A faculty-friendly attendance system with student analytics.",
            status="Planning",
            image_url="/assets/project-campus.jpg",
            owner_id=nisha.id,
        ),
    ]
    projects[0].members.extend([founder, aarav, nisha])
    projects[1].members.extend([aarav, founder, rohan])
    projects[2].members.extend([founder, rohan])
    projects[3].members.extend([nisha])
    db.add_all(projects)

    posts = [
        Post(body="Robotics Club registrations are open until Friday. Beginners are welcome; we will start with Arduino and basic sensors.", category="Clubs", author_id=nisha.id),
        Post(body="I uploaded a clean DSA roadmap for second-year students. Start with arrays, hashing, two pointers and recursion before jumping to dynamic programming.", category="Resources", author_id=aarav.id),
        Post(body="Looking for one backend developer and one designer for Campus Connect. We are building the first usable version this month.", category="Projects", author_id=founder.id),
        Post(body="We completed the first responsive profile page and contribution graph prototype today.", category="Build Log", author_id=founder.id),
    ]
    db.add_all(posts)
    db.flush()
    db.add_all([
        PostLike(post_id=posts[0].id, user_id=founder.id),
        PostLike(post_id=posts[0].id, user_id=aarav.id),
        PostLike(post_id=posts[1].id, user_id=founder.id),
    ])

    questions = [
        Question(title="How should I start DSA in second year?", body="I know basic C++ but I am confused between sheets, courses and random practice. Please suggest a practical weekly roadmap.", tags="dsa,c++,roadmap", author_id=founder.id),
        Question(title="Which sensor is best for a line follower robot?", body="We are making a low-cost line follower for the club. Is an IR array enough or should we use a camera?", tags="robotics,arduino,sensors", author_id=rohan.id, solved=True),
    ]
    db.add_all(questions)
    db.flush()
    db.add_all([
        Answer(body="Use one structured sheet, solve 3–4 problems daily, and keep a mistake notebook. Every Sunday, redo the questions you could not solve without hints.", question_id=questions[0].id, author_id=aarav.id),
        Answer(body="For a first version, a 5-channel IR sensor array is inexpensive and much easier to tune. A camera is useful only when the track conditions are complex.", question_id=questions[1].id, author_id=nisha.id, is_accepted=True),
    ])

    now = datetime.now(timezone.utc)
    events = [
        Event(title="Campus Hackathon Orientation", description="Team formation, problem statements, judging criteria and starter resources.", venue="Seminar Hall A", event_date=now + timedelta(days=2, hours=16), capacity=180, organizer_id=aarav.id),
        Event(title="Robotics Club Open Lab", description="Hands-on Arduino, sensors, motors and project demonstrations.", venue="Innovation Lab", event_date=now + timedelta(days=5, hours=15), capacity=60, organizer_id=nisha.id),
        Event(title="Placement Resume Review", description="One-to-one resume feedback from seniors and alumni volunteers.", venue="Training & Placement Cell", event_date=now + timedelta(days=8, hours=11), capacity=80, organizer_id=aarav.id),
    ]
    db.add_all(events)
    db.flush()
    db.add(EventRegistration(event_id=events[0].id, user_id=founder.id))

    db.add_all([
        Notification(user_id=founder.id, message="Nisha shared a new Robotics Club update.", kind="community"),
        Notification(user_id=founder.id, message="Aarav answered your DSA question.", kind="answer"),
        Notification(user_id=founder.id, message="Hackathon orientation starts in two days.", kind="event"),
    ])
    db.commit()
