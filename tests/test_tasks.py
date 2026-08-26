from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_rate_limit(monkeypatch):
    # Same isolation the existing rate-limit smoke test uses: the limiter backend is a
    # module-level singleton shared by every test in the process, so without this, logins
    # from earlier tests in the run count against this file's login budget too.
    from app import rate_limit

    monkeypatch.setattr(rate_limit, "_backend", rate_limit._InMemoryLimiter())


def _login(client) -> str:
    login = client.post("/api/auth/login", json={"email": "campusinnovators07@gmail.com", "password": "UniqueGeca20"})
    assert login.status_code == 200
    return login.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_create_list_update_delete_task(client):
    token = _login(client)

    created = client.post(
        "/api/tasks",
        json={"title": "Finish SIH report", "category": "hackathon", "priority": "high"},
        headers=_auth(token),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "todo"
    assert body["progress_percentage"] == 0
    assert body["subtasks"] == []
    task_id = body["id"]

    listed = client.get("/api/tasks", headers=_auth(token))
    assert listed.status_code == 200
    assert any(t["id"] == task_id for t in listed.json())

    filtered = client.get("/api/tasks", params={"category": "hackathon"}, headers=_auth(token))
    assert filtered.status_code == 200
    assert all(t["category"] == "hackathon" for t in filtered.json())

    updated = client.put(f"/api/tasks/{task_id}", json={"priority": "low"}, headers=_auth(token))
    assert updated.status_code == 200
    assert updated.json()["priority"] == "low"

    deleted = client.delete(f"/api/tasks/{task_id}", headers=_auth(token))
    assert deleted.status_code == 204
    assert client.get(f"/api/tasks/{task_id}", headers=_auth(token)).status_code == 404


def test_invalid_category_rejected(client):
    token = _login(client)
    response = client.post("/api/tasks", json={"title": "Bad task", "category": "nonsense"}, headers=_auth(token))
    assert response.status_code == 422


def test_status_completion_awards_xp_once_and_updates_streak(client):
    token = _login(client)
    dashboard_before = client.get("/api/dashboard", headers=_auth(token)).json()
    xp_before = dashboard_before["user"]["xp"]

    created = client.post("/api/tasks", json={"title": "Read a paper"}, headers=_auth(token))
    task_id = created.json()["id"]

    completed = client.patch(f"/api/tasks/{task_id}/status", json={"status": "completed"}, headers=_auth(token))
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None

    dashboard_after = client.get("/api/dashboard", headers=_auth(token)).json()
    assert dashboard_after["user"]["xp"] == xp_before + 15

    # Undo then re-complete: XP must not be awarded a second time.
    client.patch(f"/api/tasks/{task_id}/status", json={"status": "todo"}, headers=_auth(token))
    client.patch(f"/api/tasks/{task_id}/status", json={"status": "completed"}, headers=_auth(token))
    dashboard_final = client.get("/api/dashboard", headers=_auth(token)).json()
    assert dashboard_final["user"]["xp"] == xp_before + 15

    stats = client.get("/api/tasks/stats", headers=_auth(token))
    assert stats.status_code == 200
    assert stats.json()["current_streak"] == 1
    assert stats.json()["longest_streak"] == 1
    assert stats.json()["completed"] == 1


def test_subtasks_recalculate_progress_and_auto_complete(client):
    token = _login(client)
    created = client.post("/api/tasks", json={"title": "Ship feature"}, headers=_auth(token))
    task_id = created.json()["id"]

    sub1 = client.post(f"/api/tasks/{task_id}/subtasks", json={"title": "Write code"}, headers=_auth(token))
    assert sub1.status_code == 201
    sub2 = client.post(f"/api/tasks/{task_id}/subtasks", json={"title": "Write tests"}, headers=_auth(token))
    assert sub2.status_code == 201

    after_add = client.get(f"/api/tasks/{task_id}", headers=_auth(token)).json()
    assert after_add["progress_percentage"] == 0
    assert len(after_add["subtasks"]) == 2

    toggle1 = client.patch(f"/api/subtasks/{sub1.json()['id']}", headers=_auth(token))
    assert toggle1.status_code == 200
    assert toggle1.json()["is_completed"] is True

    mid = client.get(f"/api/tasks/{task_id}", headers=_auth(token)).json()
    assert mid["progress_percentage"] == 50
    assert mid["status"] == "todo"

    toggle2 = client.patch(f"/api/subtasks/{sub2.json()['id']}", headers=_auth(token))
    assert toggle2.status_code == 200

    done = client.get(f"/api/tasks/{task_id}", headers=_auth(token)).json()
    assert done["progress_percentage"] == 100
    assert done["status"] == "completed"

    # Deleting a subtask recalculates progress again.
    client.delete(f"/api/subtasks/{sub1.json()['id']}", headers=_auth(token))
    after_delete = client.get(f"/api/tasks/{task_id}", headers=_auth(token)).json()
    assert after_delete["progress_percentage"] == 100
    assert len(after_delete["subtasks"]) == 1


def test_task_ownership_is_enforced(client):
    token_a = _login(client)
    created = client.post("/api/tasks", json={"title": "Private task"}, headers=_auth(token_a))
    task_id = created.json()["id"]

    allowlisted = client.post(
        "/api/admin/allowed-emails",
        json={"email": "second.member@example.com", "note": "test"},
        headers=_auth(token_a),
    )
    assert allowlisted.status_code == 201

    register = client.post(
        "/api/auth/register",
        json={
            "name": "Second Member",
            "username": "secondmember",
            "email": "second.member@example.com",
            "password": "SecondPass1",
            "department": "Computer Science",
            "year": "1st Year",
            "avatar_key": "avatar-01",
        },
    )
    assert register.status_code == 201
    token_b = client.post("/api/auth/login", json={"email": "second.member@example.com", "password": "SecondPass1"}).json()["access_token"]

    forbidden = client.get(f"/api/tasks/{task_id}", headers=_auth(token_b))
    assert forbidden.status_code == 403
