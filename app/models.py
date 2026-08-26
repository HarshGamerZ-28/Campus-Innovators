from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


project_members = Table(
    "project_members",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    username: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(40), default="Student")
    department: Mapped[str] = mapped_column(String(120), default="Computer Science")
    year: Mapped[str] = mapped_column(String(40), default="1st Year")
    bio: Mapped[str] = mapped_column(Text, default="Building, learning and helping the campus community.")
    avatar_key: Mapped[str] = mapped_column(String(80), default="avatar-01")
    avatar_url: Mapped[str] = mapped_column(String(500), default="/assets/avatars/avatar-01.webp")
    hero_avatar_url: Mapped[str] = mapped_column(String(500), default="/assets/avatars/avatar-01.webp")
    level: Mapped[int] = mapped_column(Integer, default=1)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    next_xp: Mapped[int] = mapped_column(Integer, default=100)
    coins: Mapped[int] = mapped_column(Integer, default=100)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    posts: Mapped[list[Post]] = relationship(back_populates="author", cascade="all, delete-orphan")
    questions: Mapped[list[Question]] = relationship(back_populates="author", cascade="all, delete-orphan")
    answers: Mapped[list[Answer]] = relationship(back_populates="author", cascade="all, delete-orphan")
    owned_projects: Mapped[list[Project]] = relationship(back_populates="owner", foreign_keys="Project.owner_id")
    joined_projects: Mapped[list[Project]] = relationship(secondary=project_members, back_populates="members")
    refresh_sessions: Mapped[list[RefreshSession]] = relationship(back_populates="user", cascade="all, delete-orphan")
    activity_days: Mapped[list[ActivityDay]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Avatar(Base):
    __tablename__ = "avatars"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    image_url: Mapped[str] = mapped_column(String(500))
    hero_image_url: Mapped[str] = mapped_column(String(500))
    reserved_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class AllowedEmail(Base):
    __tablename__ = "allowed_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    added_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_jti: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    ip_address: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="refresh_sessions")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()


class ActivityDay(Base):
    __tablename__ = "activity_days"
    __table_args__ = (UniqueConstraint("user_id", "activity_date", name="uq_user_activity_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    activity_date: Mapped[date] = mapped_column(Date, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="activity_days")


class DailyXpLedger(Base):
    """Tracks XP earned per user per calendar day so `grant_xp` can enforce a daily cap.

    Without this, repeatable actions (posting, joining/leaving a project, asking
    questions) would let a script farm unlimited XP and dominate the leaderboard.
    """

    __tablename__ = "daily_xp_ledger"
    __table_args__ = (UniqueConstraint("user_id", "xp_date", name="uq_user_xp_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    xp_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship()


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    location: Mapped[str] = mapped_column(String(255), default="")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # When True (default), this meeting also appears on the public Events feed
    # (see routers/events.py) merged alongside real Event rows.
    visible_on_events: Mapped[bool] = mapped_column(Boolean, default=True)

    created_by: Mapped[User] = relationship()
    attendances: Mapped[list[MeetingAttendance]] = relationship(back_populates="meeting", cascade="all, delete-orphan")


class MeetingAttendance(Base):
    """Marks a user present at a meeting. Presence of a row == present.

    A user with no row for a given meeting is simply absent — we don't store
    "absent" rows, so `GET /admin/meetings/{id}/attendees` derives absence by
    left-joining all users against this table.
    """

    __tablename__ = "meeting_attendance"
    __table_args__ = (UniqueConstraint("meeting_id", "user_id", name="uq_meeting_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    meeting_id: Mapped[int] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    marked_present_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    meeting: Mapped[Meeting] = relationship(back_populates="attendances")
    user: Mapped[User] = relationship()


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(80), default="General")
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    author: Mapped[User] = relationship(back_populates="posts")
    likes: Mapped[list[PostLike]] = relationship(back_populates="post", cascade="all, delete-orphan")


class PostLike(Base):
    __tablename__ = "post_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_like"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    post: Mapped[Post] = relationship(back_populates="likes")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(220))
    body: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(String(500), default="")
    solved: Mapped[bool] = mapped_column(Boolean, default=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    author: Mapped[User] = relationship(back_populates="questions")
    answers: Mapped[list[Answer]] = relationship(back_populates="question", cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[str] = mapped_column(Text)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    author: Mapped[User] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship(back_populates="answers")


# --- Opportunity Board --------------------------------------------------------
# Plain strings (validated in schemas.py) rather than native SQL Enum columns,
# matching the rest of this file (see TASK_* constants, Skill.category above).
OPPORTUNITY_TYPES = ("internship", "hackathon", "scholarship", "workshop", "other")
OPPORTUNITY_STATUSES = ("pending", "approved", "rejected")


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str] = mapped_column(String(20), default="other")
    organization: Mapped[str] = mapped_column(String(100))
    external_link: Mapped[str] = mapped_column(String(500))
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Auto-set to "approved" at creation when the submitter is an admin/founder
    # (see routers/opportunities.py), otherwise starts "pending" for review.
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    subtitle: Mapped[str] = mapped_column(String(220))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(60), default="In Progress")
    image_url: Mapped[str] = mapped_column(String(500), default="/assets/project-campus.jpg")
    github_url: Mapped[str] = mapped_column(String(500), default="")
    demo_url: Mapped[str] = mapped_column(String(500), default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="owned_projects", foreign_keys=[owner_id])
    members: Mapped[list[User]] = relationship(secondary=project_members, back_populates="joined_projects")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    venue: Mapped[str] = mapped_column(String(180))
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    capacity: Mapped[int] = mapped_column(Integer, default=100)
    organizer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    organizer: Mapped[User] = relationship()
    registrations: Mapped[list[EventRegistration]] = relationship(back_populates="event", cascade="all, delete-orphan")


class EventRegistration(Base):
    __tablename__ = "event_registrations"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_registration"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    event: Mapped[Event] = relationship(back_populates="registrations")


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_skill"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    tone: Mapped[str] = mapped_column(String(40), default="purple")
    category: Mapped[str] = mapped_column(String(20), default="skill")

    MASTERY_THRESHOLD = 90

    @hybrid_property
    def is_mastered(self) -> bool:
        """True once self-assessed progress reaches the mastery threshold.

        Purely derived from `progress` — not a stored column, not client-settable.
        Works both on Python instances and in SQL (e.g. `.where(Skill.is_mastered)`)
        because hybrid_property compiles the same expression either way.
        """
        return self.progress >= Skill.MASTERY_THRESHOLD


class Habit(Base):
    __tablename__ = "habits"
    __table_args__ = (UniqueConstraint("user_id", "label", name="uq_user_habit"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    tone: Mapped[str] = mapped_column(String(40), default="purple")
    # Calendar date this habit was last ticked complete. Used to lazily reset
    # `complete` back to False once a new day starts (no cron job needed) and
    # to make sure a habit only grants XP once per day, however many times
    # it's toggled on and off.
    last_completed_on: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)


class HabitLog(Base):
    """One row per habit per calendar day, recording whether it was completed
    that day. Written on every toggle (on AND off) so a day's row always
    reflects the last state the user left it in — see toggle_habit in
    habits.py. This is what makes a 7-day history queryable; `Habit.streak`
    and `Habit.last_completed_on` alone can't reconstruct completion for a
    day once the streak has since reset.
    """

    __tablename__ = "habit_logs"
    __table_args__ = (UniqueConstraint("habit_id", "log_date", name="uq_habit_log_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"), index=True)
    log_date: Mapped[date] = mapped_column(Date, index=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class Quest(Base):
    __tablename__ = "quests"
    __table_args__ = (UniqueConstraint("user_id", "title", name="uq_user_quest"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    current: Mapped[int] = mapped_column(Integer, default=0)
    target: Mapped[int] = mapped_column(Integer, default=1)
    reward_xp: Mapped[int] = mapped_column(Integer, default=20)
    claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Daily-repeating quest support. A user has at most one is_daily row —
    # instead of inserting a new quest every day, that single row is rewritten
    # in place each day with the template for the current point in the 7-day
    # cycle (see app/daily_quests.py). One-time onboarding quests leave these
    # at their defaults and are unaffected.
    is_daily: Mapped[bool] = mapped_column(Boolean, default=False)
    cycle_index: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    assigned_on: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(String(400))
    kind: Mapped[str] = mapped_column(String(50), default="info")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# --- Smart Task Management ---------------------------------------------------
# Kept as plain strings (validated in schemas.py) rather than native SQL Enum
# columns, matching the rest of this file (see Skill.category, Habit fields
# above) — avoids enum-migration friction across sqlite/postgres.
TASK_CATEGORIES = ("academic", "project", "personal", "community", "hackathon")
TASK_PRIORITIES = ("low", "medium", "high")
TASK_STATUSES = ("todo", "in_progress", "completed")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(20), default="personal")
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="todo", index=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Auto-calculated from subtasks when the task has any (see habits.recalc_subtask_progress);
    # otherwise settable directly off the status (todo=0, in_progress=50, completed=100).
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0)
    # Prevents double XP if a task is flipped completed -> not -> completed again.
    xp_awarded: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    subtasks: Mapped[list[Subtask]] = relationship(back_populates="task", cascade="all, delete-orphan", order_by="Subtask.id")


class Subtask(Base):
    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped[Task] = relationship(back_populates="subtasks")


class TaskStreak(Base):
    """Per-user completion streak scoped to tasks (kept separate from Habit.streak,
    which tracks per-habit streaks, and User.streak, a general dashboard stat —
    no existing generic streak service covers cross-task completion tracking)."""

    __tablename__ = "task_streaks"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_completed_date: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
