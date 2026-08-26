from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_rate_limit(monkeypatch):
    # Same isolation the other test files use: the limiter backend is a
    # module-level singleton shared by every test in the process.
    from app import rate_limit

    monkeypatch.setattr(rate_limit, "_backend", rate_limit._InMemoryLimiter())


def _login(client, email: str, password: str) -> str:
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return login.json()["access_token"]


def _login_admin(client) -> str:
    return _login(client, "campusinnovators07@gmail.com", "UniqueGeca20")


def _login_student(client) -> str:
    return _login(client, "aarav@campusinnovators.in", "Campus@123")


def _login_other_student(client) -> str:
    return _login(client, "nisha@campusinnovators.in", "Campus@123")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _submit_opportunity(client, token: str, *, title: str) -> int:
    created = client.post(
        "/api/opportunities",
        json={
            "title": title,
            "description": "Work on applied ML projects for 8 weeks.",
            "type": "internship",
            "organization": "Acme Labs",
            "external_link": "https://acme.example.com/apply",
        },
        headers=_auth(token),
    )
    assert created.status_code == 201
    assert created.json()["status"] == "pending"
    return created.json()["id"]


def test_notifications_are_user_scoped(client):
    admin_token = _login_admin(client)
    student_token = _login_student(client)

    admin_items = client.get("/api/notifications", headers=_auth(admin_token)).json()
    student_items = client.get("/api/notifications", headers=_auth(student_token)).json()

    admin_ids = {item["id"] for item in admin_items}
    student_ids = {item["id"] for item in student_items}
    assert admin_ids.isdisjoint(student_ids)


def test_opportunity_approval_notifies_submitter(client):
    admin_token = _login_admin(client)
    student_token = _login_student(client)

    opportunity_id = _submit_opportunity(client, student_token, title="Summer AI Internship")

    reviewed = client.patch(
        f"/api/opportunities/{opportunity_id}/review",
        json={"action": "approve"},
        headers=_auth(admin_token),
    )
    assert reviewed.status_code == 200

    notifications = client.get("/api/notifications", headers=_auth(student_token)).json()
    assert any(
        item["kind"] == "opportunity_approved" and "Summer AI Internship" in item["message"]
        for item in notifications
    )


def test_opportunity_rejection_notifies_submitter(client):
    admin_token = _login_admin(client)
    student_token = _login_student(client)

    opportunity_id = _submit_opportunity(client, student_token, title="Unpaid Coffee Fetching")

    reviewed = client.patch(
        f"/api/opportunities/{opportunity_id}/review",
        json={"action": "reject", "rejection_reason": "Not a real opportunity"},
        headers=_auth(admin_token),
    )
    assert reviewed.status_code == 200

    notifications = client.get("/api/notifications", headers=_auth(student_token)).json()
    assert any(
        item["kind"] == "opportunity_rejected" and "Unpaid Coffee Fetching" in item["message"]
        for item in notifications
    )


def test_new_event_notifies_other_active_users_but_not_the_creator(client):
    student_token = _login_student(client)
    other_token = _login_other_student(client)

    created = client.post(
        "/api/events",
        json={
            "title": "Robotics Workshop",
            "description": "Hands-on robotics session.",
            "venue": "Lab 2",
            "event_date": "2027-01-15T10:00:00Z",
            "capacity": 30,
        },
        headers=_auth(student_token),
    )
    assert created.status_code == 201

    creator_notifications = client.get("/api/notifications", headers=_auth(student_token)).json()
    assert not any(
        item["kind"] == "event_created" and "Robotics Workshop" in item["message"]
        for item in creator_notifications
    )

    other_notifications = client.get("/api/notifications", headers=_auth(other_token)).json()
    assert any(
        item["kind"] == "event_created" and "Robotics Workshop" in item["message"]
        for item in other_notifications
    )


def test_unread_count_matches_unread_notifications(client):
    admin_token = _login_admin(client)

    items = client.get("/api/notifications", headers=_auth(admin_token)).json()
    expected_unread = sum(1 for item in items if not item["is_read"])

    unread = client.get("/api/notifications/unread-count", headers=_auth(admin_token))
    assert unread.status_code == 200
    assert unread.json()["count"] == expected_unread


def test_mark_single_notification_read(client):
    admin_token = _login_admin(client)
    student_token = _login_student(client)

    opportunity_id = _submit_opportunity(client, student_token, title="Frontend Internship")
    client.patch(
        f"/api/opportunities/{opportunity_id}/review",
        json={"action": "approve"},
        headers=_auth(admin_token),
    )

    items = client.get("/api/notifications", headers=_auth(student_token)).json()
    target = next(item for item in items if item["kind"] == "opportunity_approved")
    assert target["is_read"] is False

    marked = client.patch(f"/api/notifications/{target['id']}/read", headers=_auth(student_token))
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True

    refreshed = client.get("/api/notifications", headers=_auth(student_token)).json()
    refreshed_target = next(item for item in refreshed if item["id"] == target["id"])
    assert refreshed_target["is_read"] is True


def test_cannot_mark_another_users_notification_as_read(client):
    admin_token = _login_admin(client)
    student_token = _login_student(client)

    opportunity_id = _submit_opportunity(client, student_token, title="Backend Internship")
    client.patch(
        f"/api/opportunities/{opportunity_id}/review",
        json={"action": "approve"},
        headers=_auth(admin_token),
    )
    items = client.get("/api/notifications", headers=_auth(student_token)).json()
    target = next(item for item in items if item["kind"] == "opportunity_approved")

    response = client.patch(f"/api/notifications/{target['id']}/read", headers=_auth(admin_token))
    assert response.status_code == 404


def test_mark_all_read_only_touches_current_user(client):
    admin_token = _login_admin(client)
    student_token = _login_student(client)

    opportunity_id = _submit_opportunity(client, student_token, title="Data Science Internship")
    client.patch(
        f"/api/opportunities/{opportunity_id}/review",
        json={"action": "approve"},
        headers=_auth(admin_token),
    )

    before_admin_unread = client.get("/api/notifications/unread-count", headers=_auth(admin_token)).json()["count"]

    marked = client.patch("/api/notifications/read-all", headers=_auth(student_token))
    assert marked.status_code == 200
    assert marked.json()["updated"] >= 1

    student_unread = client.get("/api/notifications/unread-count", headers=_auth(student_token)).json()
    assert student_unread["count"] == 0

    admin_unread = client.get("/api/notifications/unread-count", headers=_auth(admin_token)).json()
    assert admin_unread["count"] == before_admin_unread


def test_read_all_also_works_over_post_for_deployed_frontend_compat(client):
    student_token = _login_student(client)
    marked = client.post("/api/notifications/read-all", headers=_auth(student_token))
    assert marked.status_code == 200


def test_notifications_list_is_paginated(client):
    admin_token = _login_admin(client)
    page = client.get("/api/notifications?limit=1&offset=0", headers=_auth(admin_token))
    assert page.status_code == 200
    assert len(page.json()) <= 1
