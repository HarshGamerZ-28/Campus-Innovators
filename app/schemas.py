from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_.-]{1,28}[a-z0-9])?$")


def _validate_password_strength(value: str) -> str:
    checks = [any(c.islower() for c in value), any(c.isupper() for c in value), any(c.isdigit() for c in value)]
    if not all(checks):
        raise ValueError("Password must include uppercase, lowercase and a number")
    return value


def _safe_public_url(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    if normalized.startswith(("https://", "http://")):
        return normalized
    if normalized.startswith("/") and not normalized.startswith("//"):
        return normalized
    raise ValueError("URL must use http(s) or be a root-relative application path")


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RegisterInput(LoginInput):
    name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=30)
    department: str = Field(default="Computer Science", max_length=120)
    year: str = Field(default="1st Year", max_length=40)
    avatar_key: str = Field(default="avatar-01", max_length=80)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = value.lower().strip()
        if not USERNAME_RE.fullmatch(normalized):
            raise ValueError("Username can use lowercase letters, numbers, dot, dash and underscore")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class ForgotPasswordInput(BaseModel):
    email: EmailStr


class ResetPasswordInput(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    year: str | None = Field(default=None, max_length=40)
    bio: str | None = Field(default=None, max_length=800)
    avatar_key: str | None = Field(default=None, max_length=80)
    is_public: bool | None = None


class PlatformUpdate(BaseModel):
    intro_video_url: str = Field(default="", max_length=1000)
    intro_video_title: str = Field(default="Welcome to Campus Innovators", max_length=180)
    intro_video_description: str = Field(default="See how students learn, collaborate and build together.", max_length=500)

    @field_validator("intro_video_url")
    @classmethod
    def validate_intro_video_url(cls, value: str) -> str:
        return _safe_public_url(value)


class AllowedEmailCreate(BaseModel):
    email: EmailStr
    note: str | None = Field(default=None, max_length=255)


class AllowedEmailOut(BaseModel):
    id: int
    email: str
    note: str | None = None
    added_at: datetime
    added_by_id: int

    model_config = {"from_attributes": True}


class AvatarCreate(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    image_url: str = Field(max_length=500)
    hero_image_url: str = Field(max_length=500)
    sort_order: int = Field(default=0)

    @field_validator("image_url", "hero_image_url")
    @classmethod
    def validate_avatar_urls(cls, value: str) -> str:
        return _safe_public_url(value)


class AvatarUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    image_url: str | None = Field(default=None, max_length=500)
    hero_image_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("image_url", "hero_image_url")
    @classmethod
    def validate_avatar_urls(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _safe_public_url(value)


class AvatarOut(BaseModel):
    id: int
    key: str
    label: str
    image_url: str
    hero_image_url: str
    reserved_email: str | None = None
    is_active: bool
    sort_order: int

    model_config = {"from_attributes": True}


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    scheduled_at: datetime
    location: str = Field(default="", max_length=255)


class MeetingOut(BaseModel):
    id: int
    title: str
    description: str
    scheduled_at: datetime
    location: str
    created_by_id: int
    created_at: datetime
    attendee_count: int = 0

    model_config = {"from_attributes": True}


class MeetingAttendeeOut(BaseModel):
    user_id: int
    name: str
    username: str
    avatar_url: str
    present: bool
    marked_present_at: datetime | None = None


class PostCreate(BaseModel):
    body: str = Field(min_length=2, max_length=3000)
    category: str = Field(default="General", max_length=80)


class QuestionCreate(BaseModel):
    title: str = Field(min_length=5, max_length=220)
    body: str = Field(min_length=10, max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=8)


class AnswerCreate(BaseModel):
    body: str = Field(min_length=2, max_length=5000)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    subtitle: str = Field(min_length=2, max_length=220)
    description: str = Field(default="", max_length=5000)
    image_url: str = Field(default="/assets/project-campus.jpg", max_length=500)
    github_url: str = Field(default="", max_length=500)
    demo_url: str = Field(default="", max_length=500)
    status: str = Field(default="In Progress", max_length=60)

    @field_validator("image_url", "github_url", "demo_url")
    @classmethod
    def validate_project_urls(cls, value: str) -> str:
        return _safe_public_url(value)


class EventCreate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    venue: str = Field(min_length=2, max_length=180)
    event_date: datetime
    capacity: int = Field(default=100, ge=1, le=5000)


class SkillUpdate(BaseModel):
    progress: int = Field(ge=0, le=100)


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="skill", max_length=20)
    tone: str = Field(default="purple", max_length=40)
    progress: int = Field(default=0, ge=0, le=100)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"skill", "learning"}:
            raise ValueError('category must be "skill" or "learning"')
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized


class HabitCreate(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    tone: str = Field(default="purple", max_length=40)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("label cannot be blank")
        return normalized


class SearchResult(BaseModel):
    type: str
    id: int
    title: str
    subtitle: str
    username: str | None = None
