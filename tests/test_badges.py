from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_rate_limit(monkeypatch):
    # Same isolation test_tasks.py/test_skills.py/test_events.py use: the limiter
    # backend is a module-level singleton shared by every test in the process, so
    # without this, logins from earlier tests count against this file's budget.
    from app import rate_limit

    monkeypatch.setattr(rate_limit, "_backend", rate_limit._InMemoryLimiter())


def _login(client, email: str, password: str) -> str:
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return login.json()["access_token"]


def _login_admin(client) -> str:
    return _login(client, "campusinnovators07@gmail.com", "UniqueGeca20")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register_member(client, admin_token: str, *, email: str, username: str) -> str:
    """Register a brand-new member with no seeded demo data of their own.

    The seeded founder account already owns projects and has habit streaks well
    past every badge threshold (see seed.py), so badge tests always work through
    a freshly registered member instead — the only way to reliably exercise the
    locked (zero-progress) state and a controlled unlock.
    """
    allowlisted = client.post(
        "/api/admin/allowed-emails",
        json={"email": email, "note": "test"},
        headers=_auth(admin_token),
    )
    assert allowlisted.status_code == 201

    register = client.post(
        "/api/auth/register",
        json={
            "name": "Test Member",
            "username": username,
            "email": email,
            "password": "MemberPass1",
            "department": "Computer Science",
            "year": "1st Year",
            "avatar_key": "avatar-01",
        },
    )
    assert register.status_code == 201
    return _login(client, email, "MemberPass1")


def _badge(badges: list[dict], key: str) -> dict:
    return next(item for item in badges if item["key"] == key)


def test_fresh_member_has_all_badges_locked_with_zero_progress(client):
    admin_token = _login_admin(client)
    token = _register_member(client, admin_token, email="freshie@example.com", username="freshiemember")

    response = client.get("/api/badges", headers=_auth(token))
    assert response.status_code == 200
    badges = response.json()

    keys = {item["key"] for item in badges}
    assert {"problem_solver", "streak_master", "early_bird", "project_builder", "consistency_king"} <= keys
    for item in badges:
        assert item["unlocked"] is False
        assert item["progress_current"] == 0
        assert item["progress_target"] > 0

    dashboard = client.get("/api/dashboard", headers=_auth(token)).json()
    assert dashboard["achievements"] == []


def test_project_builder_unlocks_after_creating_two_projects(client):
    admin_token = _login_admin(client)
    token = _register_member(client, admin_token, email="builder@example.com", username="buildermember")

    before = _badge(client.get("/api/badges", headers=_auth(token)).json(), "project_builder")
    assert before["unlocked"] is False
    assert before["progress_current"] == 0
    assert before["progress_target"] == 2

    for name in ["Campus Navigator", "Study Buddy"]:
        created = client.post(
            "/api/projects",
            json={"name": name, "subtitle": "A project for the badge test"},
            headers=_auth(token),
        )
        assert created.status_code == 201

    after = _badge(client.get("/api/badges", headers=_auth(token)).json(), "project_builder")
    assert after["unlocked"] is True
    assert after["progress_current"] == 2

    dashboard = client.get("/api/dashboard", headers=_auth(token)).json()
    assert any(item["label"] == "Project Builder" for item in dashboard["achievements"])


def test_problem_solver_unlocks_after_three_accepted_answers(client):
    admin_token = _login_admin(client)
    solver_token = _register_member(client, admin_token, email="solver@example.com", username="solvermember")

    before = _badge(client.get("/api/badges", headers=_auth(solver_token)).json(), "problem_solver")
    assert before["unlocked"] is False
    assert before["progress_current"] == 0
    assert before["progress_target"] == 3

    for index in range(3):
        question = client.post(
            "/api/questions",
            json={"title": f"How do I debug issue {index}?", "body": "Been stuck on this for a while now.", "tags": []},
            headers=_auth(admin_token),
        )
        assert question.status_code == 201
        question_id = question.json()["id"]

        answer = client.post(
            f"/api/questions/{question_id}/answers",
            json={"body": "Here is a fix that should work for you."},
            headers=_auth(solver_token),
        )
        assert answer.status_code == 201
        answer_id = answer.json()["answers"][-1]["id"]

        accepted = client.patch(
            f"/api/questions/{question_id}/answers/{answer_id}/accept",
            headers=_auth(admin_token),
        )
        assert accepted.status_code == 200

    after = _badge(client.get("/api/badges", headers=_auth(solver_token)).json(), "problem_solver")
    assert after["unlocked"] is True
    assert after["progress_current"] == 3

    dashboard = client.get("/api/dashboard", headers=_auth(solver_token)).json()
    assert any(item["label"] == "Problem Solver" for item in dashboard["achievements"])
