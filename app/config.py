from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Campus Innovators API")
    environment: str = os.getenv("ENVIRONMENT", "development")
    api_prefix: str = os.getenv("API_PREFIX", "/api")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./campus_v2.db")
    secret_key: str = os.getenv("SECRET_KEY", "development-only-change-me-before-production")
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
    refresh_token_days: int = int(os.getenv("REFRESH_TOKEN_DAYS", "30"))
    refresh_cookie_name: str = os.getenv("REFRESH_COOKIE_NAME", "campus_refresh")
    cookie_secure: bool = _as_bool(os.getenv("COOKIE_SECURE"), False)
    cookie_samesite: str = os.getenv("COOKIE_SAMESITE", "lax")
    cookie_domain: str | None = os.getenv("COOKIE_DOMAIN") or None
    founder_email: str = os.getenv("FOUNDER_EMAIL", "campusinnovators07@gmail.com").lower().strip()
    founder_password: str = os.getenv("FOUNDER_PASSWORD", "UniqueGeca20")
    # Off by default everywhere. Turn this on only for a local/demo database —
    # it fills an EMPTY database with fictional sample members, posts,
    # projects, questions and events so the UI has something to show. It never
    # touches a database that already has real users, and it is hard-blocked
    # from running when ENVIRONMENT=production (see the check below).
    seed_demo_data: bool = _as_bool(os.getenv("SEED_DEMO_DATA"), False)
    intro_video_url: str = os.getenv("INTRO_VIDEO_URL", "")
    allowed_email_domains_raw: str = os.getenv("ALLOWED_EMAIL_DOMAINS", "")
    trust_proxy_headers: bool = _as_bool(os.getenv("TRUST_PROXY_HEADERS"), False)
    trusted_hosts_raw: str = os.getenv("TRUSTED_HOSTS", "localhost,127.0.0.1,testserver")
    cors_origins_raw: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://localhost:3000",
    )
    email_provider: str = os.getenv("EMAIL_PROVIDER", "console")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    redis_url: str | None = os.getenv("REDIS_URL") or None
    cloudinary_cloud_name: str | None = os.getenv("CLOUDINARY_CLOUD_NAME") or None
    cloudinary_api_key: str | None = os.getenv("CLOUDINARY_API_KEY") or None
    cloudinary_api_secret: str | None = os.getenv("CLOUDINARY_API_SECRET") or None

    @property
    def cloudinary_configured(self) -> bool:
        return bool(self.cloudinary_cloud_name and self.cloudinary_api_key and self.cloudinary_api_secret)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts_raw.split(",") if host.strip()]

    @property
    def allowed_email_domains(self) -> set[str]:
        return {domain.strip().lower().lstrip("@") for domain in self.allowed_email_domains_raw.split(",") if domain.strip()}

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


settings = Settings()

if settings.cookie_samesite.lower() not in {"lax", "strict", "none"}:
    raise RuntimeError("COOKIE_SAMESITE must be lax, strict or none")
if settings.is_production and (settings.secret_key.startswith("development-only") or len(settings.secret_key) < 48):
    raise RuntimeError("SECRET_KEY must be a long random value in production")
if settings.is_production and settings.seed_demo_data:
    raise RuntimeError(
        "SEED_DEMO_DATA must be false in production. Fictional demo members "
        "and posts are for local/demo databases only; the real, single "
        "predefined account for production is created separately with "
        "`python -m app.bootstrap_admin`."
    )
if settings.is_production:
    password_checks = [
        len(settings.founder_password) >= 12,
        any(c.isupper() for c in settings.founder_password),
        any(c.islower() for c in settings.founder_password),
        any(c.isdigit() for c in settings.founder_password),
    ]
    if not all(password_checks):
        raise RuntimeError("FOUNDER_PASSWORD must be at least 12 characters with uppercase, lowercase and a number")
    if settings.cookie_samesite.lower() == "none" and not settings.cookie_secure:
        raise RuntimeError("COOKIE_SECURE must be true when COOKIE_SAMESITE=none")
