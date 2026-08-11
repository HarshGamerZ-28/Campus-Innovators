from sqlalchemy import select

from app import main
from app.models import PasswordResetToken, User


def test_public_dashboard_and_profile_do_not_expose_email(client):
    home = client.get("/api/public/home")
    assert home.status_code == 200
    assert home.json()["user"]["name"] == "Campus Innovator"
    assert "email" not in home.json()["user"]
    assert len(home.json()["activity"]) == 30

    profile = client.get("/api/public/profiles/campusinnovator")
    assert profile.status_code == 200
    assert "email" not in profile.json()["user"]
    assert "current_projects" in profile.json()
    assert "past_projects" in profile.json()


def test_public_members_lists_seeded_users_without_email(client):
    response = client.get("/api/public/members")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 4
    usernames = {member["username"] for member in payload["members"]}
    assert "campusinnovator" in usernames
    for member in payload["members"]:
        assert "email" not in member
        assert "top_skills" in member
        assert "current_project" in member


def test_login_dashboard_refresh_and_logout(client):
    login = client.post("/api/auth/login", json={"email": "campusinnovators07@gmail.com", "password": "UniqueGeca20"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert login.json()["user"]["avatar_key"] == "divine-archer"

    dashboard = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert dashboard.status_code == 200

    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]

    assert client.post("/api/auth/logout").status_code == 204
    assert client.post("/api/auth/refresh").status_code == 401


def test_special_avatar_is_not_selectable_by_other_accounts(client):
    avatars = client.get("/api/auth/avatars")
    assert avatars.status_code == 200
    assert all(item["key"] != "divine-archer" for item in avatars.json())

    blocked = client.post(
        "/api/auth/register",
        json={
            "name": "Avatar Test",
            "username": "avatartest",
            "email": "avatar-test@example.com",
            "password": "Testing123",
            "department": "CSE",
            "year": "1st Year",
            "avatar_key": "divine-archer",
        },
    )
    assert blocked.status_code == 403


def test_admin_allowlist_gates_registration(client):
    login = client.post("/api/auth/login", json={"email": "campusinnovators07@gmail.com", "password": "UniqueGeca20"})
    assert login.status_code == 200
    admin_token = login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    payload = {
        "name": "New Student",
        "username": "newstudent",
        "email": "newstudent@example.com",
        "password": "Testing123",
        "department": "CSE",
        "year": "1st Year",
        "avatar_key": "avatar-01",
    }

    blocked = client.post("/api/auth/register", json=payload)
    assert blocked.status_code == 403
    assert "isn't approved" in blocked.json()["detail"]

    added = client.post(
        "/api/admin/allowed-emails",
        json={"email": "newstudent@example.com", "note": "CSE batch 2025"},
        headers=admin_headers,
    )
    assert added.status_code == 201
    entry_id = added.json()["id"]

    listed = client.get("/api/admin/allowed-emails", headers=admin_headers)
    assert listed.status_code == 200
    assert any(item["email"] == "newstudent@example.com" for item in listed.json())

    allowed = client.post("/api/auth/register", json=payload)
    assert allowed.status_code == 201

    removed = client.delete(f"/api/admin/allowed-emails/{entry_id}", headers=admin_headers)
    assert removed.status_code == 204


def test_founder_email_registration_is_always_rejected(client):
    login = client.post("/api/auth/login", json={"email": "campusinnovators07@gmail.com", "password": "UniqueGeca20"})
    assert login.status_code == 200
    admin_token = login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    added = client.post(
        "/api/admin/allowed-emails",
        json={"email": "campusinnovators07@gmail.com", "note": "attempted allowlist bypass"},
        headers=admin_headers,
    )
    assert added.status_code == 201

    blocked = client.post(
        "/api/auth/register",
        json={
            "name": "Founder Impersonator",
            "username": "founderfake",
            "email": "campusinnovators07@gmail.com",
            "password": "Testing123",
            "department": "CSE",
            "year": "1st Year",
            "avatar_key": "avatar-01",
        },
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Founder account must be created with the bootstrap command"


def test_admin_avatar_management(client):
    login = client.post("/api/auth/login", json={"email": "campusinnovators07@gmail.com", "password": "UniqueGeca20"})
    admin_token = login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    created = client.post(
        "/api/admin/avatars",
        json={
            "key": "avatar-test-01",
            "label": "Test Avatar",
            "image_url": "/assets/avatars/avatar-01.webp",
            "hero_image_url": "/assets/avatars/avatar-01.webp",
            "sort_order": 50,
        },
        headers=admin_headers,
    )
    assert created.status_code == 201
    avatar_id = created.json()["id"]

    listed = client.get("/api/admin/avatars", headers=admin_headers)
    assert listed.status_code == 200
    assert any(item["key"] == "avatar-test-01" for item in listed.json())

    updated = client.patch(
        f"/api/admin/avatars/{avatar_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False


def test_skills_and_habits_create_delete_and_permissions(client):
    login = client.post("/api/auth/login", json={"email": "campusinnovators07@gmail.com", "password": "UniqueGeca20"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/skills",
        json={"name": "Docker", "category": "learning", "tone": "cyan", "progress": 10},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["category"] == "learning"
    skill_id = created.json()["id"]

    duplicate = client.post(
        "/api/skills",
        json={"name": "Docker", "category": "skill", "tone": "cyan"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    habit_created = client.post("/api/habits", json={"label": "Sketch", "tone": "gold"}, headers=headers)
    assert habit_created.status_code == 201
    habit_id = habit_created.json()["id"]

    habit_duplicate = client.post("/api/habits", json={"label": "Sketch", "tone": "gold"}, headers=headers)
    assert habit_duplicate.status_code == 409

    other_login = client.post("/api/auth/login", json={"email": "aarav@campusinnovators.in", "password": "Campus@123"})
    assert other_login.status_code == 200
    other_token = other_login.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    forbidden_skill = client.delete(f"/api/skills/{skill_id}", headers=other_headers)
    assert forbidden_skill.status_code == 403

    forbidden_habit = client.delete(f"/api/habits/{habit_id}", headers=other_headers)
    assert forbidden_habit.status_code == 403

    deleted_skill = client.delete(f"/api/skills/{skill_id}", headers=headers)
    assert deleted_skill.status_code == 204

    deleted_habit = client.delete(f"/api/habits/{habit_id}", headers=headers)
    assert deleted_habit.status_code == 204


def test_login_rate_limit_enforced_with_in_memory_backend(client, monkeypatch):
    from app import rate_limit

    # Isolate this test from rate-limit state accumulated by any other test in this run
    # (the limiter backend is a module-level singleton, same as it would be in production).
    monkeypatch.setattr(rate_limit, "_backend", rate_limit._InMemoryLimiter())

    payload = {"email": "campusinnovators07@gmail.com", "password": "definitely-wrong-password"}
    for _ in range(10):
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 401

    blocked = client.post("/api/auth/login", json=payload)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_forgot_password_does_not_leak_whether_email_exists(client):
    response = client.post("/api/auth/forgot-password", json={"email": "nobody-here@campusinnovators.in"})
    assert response.status_code == 200
    assert "message" in response.json()


def test_forgot_password_generates_usable_reset_token(client):
    response = client.post("/api/auth/forgot-password", json={"email": "campusinnovators07@gmail.com"})
    assert response.status_code == 200

    with main.SessionLocal() as db:
        tokens = db.scalars(select(PasswordResetToken)).all()
        assert len(tokens) == 1
        assert tokens[0].used_at is None


def test_reset_password_flow_and_token_single_use(client, monkeypatch):
    # The raw token is only ever sent via the (console-logged) email and is never stored,
    # so capture it here the way a real email provider would receive it.
    captured = {}

    def fake_send(to_email, reset_link):
        captured["reset_link"] = reset_link

    from app.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "send_password_reset_email", fake_send)

    forgot = client.post("/api/auth/forgot-password", json={"email": "campusinnovators07@gmail.com"})
    assert forgot.status_code == 200
    assert "reset_link" in captured
    raw_token = captured["reset_link"].split("token=", 1)[1]

    with main.SessionLocal() as db:
        stored = db.scalars(select(PasswordResetToken)).all()
        assert len(stored) == 1
        assert stored[0].used_at is None

    reset = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "NewPass123"},
    )
    assert reset.status_code == 200

    login = client.post("/api/auth/login", json={"email": "campusinnovators07@gmail.com", "password": "NewPass123"})
    assert login.status_code == 200

    reused = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "new_password": "AnotherPass123"},
    )
    assert reused.status_code == 400


def test_repeated_project_creation_is_capped_by_daily_xp_limit(client):
    # Creating a project pays +20 XP with no per-project uniqueness constraint, so it's
    # the easiest action to script repeatedly. This locks in that grant_xp's daily cap
    # (300) bounds the total no matter how many times the action fires in one day.
    login = client.post("/api/auth/login", json={"email": "aarav@campusinnovators.in", "password": "Campus@123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with main.SessionLocal() as db:
        starting_xp = db.scalar(select(User.xp).where(User.username == "aaravmehta"))

    for index in range(20):
        response = client.post(
            "/api/projects",
            json={"name": f"Farm Bot Project {index}", "subtitle": "xp farming attempt"},
            headers=headers,
        )
        assert response.status_code == 201

    with main.SessionLocal() as db:
        ending_xp = db.scalar(select(User.xp).where(User.username == "aaravmehta"))

    # 20 creations x 20 XP = 400 XP attempted; the daily cap must hold it to 300.
    assert ending_xp - starting_xp == 300
