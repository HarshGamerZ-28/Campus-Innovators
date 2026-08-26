from __future__ import annotations

from datetime import date, timedelta

import pytest


@pytest.fixture(autouse=True)
def _isolated_rate_limit(monkeypatch):
    # Same isolation test_tasks.py uses: the limiter backend is a module-level
    # singleton shared by every test in the process, so without this, logins
    # from earlier tests in the run count against this file's login budget too.
    from app import rate_limit

    monkeypatch.setattr(rate_limit, "_backend", rate_limit._InMemoryLimiter())


def _login_admin(client) -> str:
    login = client.post("/api/auth/login", json={"email": "campusinnovators07@gmail.com", "password": "UniqueGeca20"})
    assert login.status_code == 200
    return login.json()["access_token"]


def _login_student(client) -> str:
    login = client.post("/api/auth/login", json={"email": "aarav@campusinnovators.in", "password": "Campus@123"})
    assert login.status_code == 200
    return login.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _payload(**overrides) -> dict:
    base = {
        "title": "Summer AI Internship",
        "description": "Work on applied ML projects for 8 weeks.",
        "type": "internship",
        "organization": "Acme Labs",
        "external_link": "https://acme.example.com/apply",
        "location": "Remote",
    }
    base.update(overrides)
    return base


def test_student_submission_is_pending(client):
    token = _login_student(client)
    created = client.post("/api/opportunities", json=_payload(), headers=_auth(token))
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["reviewed_by"] is None

    # Not yet visible on the public/approved list.
    listing = client.get("/api/opportunities")
    assert listing.status_code == 200
    assert all(item["id"] != body["id"] for item in listing.json())

    # But visible under the submitter's own "mine" view.
    mine = client.get("/api/opportunities/mine", headers=_auth(token))
    assert mine.status_code == 200
    assert any(item["id"] == body["id"] for item in mine.json())


def test_admin_submission_is_auto_approved(client):
    token = _login_admin(client)
    created = client.post("/api/opportunities", json=_payload(title="Campus Hackathon 2026", type="hackathon"), headers=_auth(token))
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "approved"

    listing = client.get("/api/opportunities")
    assert listing.status_code == 200
    assert any(item["id"] == body["id"] for item in listing.json())


def test_approve_flow(client):
    student_token = _login_student(client)
    admin_token = _login_admin(client)

    created = client.post("/api/opportunities", json=_payload(), headers=_auth(student_token))
    opportunity_id = created.json()["id"]

    pending = client.get("/api/opportunities/pending", headers=_auth(admin_token))
    assert pending.status_code == 200
    assert any(item["id"] == opportunity_id for item in pending.json())

    reviewed = client.patch(f"/api/opportunities/{opportunity_id}/review", json={"action": "approve"}, headers=_auth(admin_token))
    assert reviewed.status_code == 200
    body = reviewed.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] is not None

    listing = client.get("/api/opportunities")
    assert any(item["id"] == opportunity_id for item in listing.json())


def test_reject_flow(client):
    student_token = _login_student(client)
    admin_token = _login_admin(client)

    created = client.post("/api/opportunities", json=_payload(), headers=_auth(student_token))
    opportunity_id = created.json()["id"]

    reviewed = client.patch(
        f"/api/opportunities/{opportunity_id}/review",
        json={"action": "reject", "rejection_reason": "Missing eligibility details"},
        headers=_auth(admin_token),
    )
    assert reviewed.status_code == 200
    body = reviewed.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "Missing eligibility details"

    listing = client.get("/api/opportunities")
    assert all(item["id"] != opportunity_id for item in listing.json())


def test_non_admin_cannot_review(client):
    student_token = _login_student(client)
    created = client.post("/api/opportunities", json=_payload(), headers=_auth(student_token))
    opportunity_id = created.json()["id"]

    forbidden = client.patch(f"/api/opportunities/{opportunity_id}/review", json={"action": "approve"}, headers=_auth(student_token))
    assert forbidden.status_code == 403


def test_non_owner_cannot_edit_pending(client):
    student_token = _login_student(client)
    other_token = _login_admin(client)  # a different account than the submitter

    created = client.post("/api/opportunities", json=_payload(), headers=_auth(student_token))
    opportunity_id = created.json()["id"]

    # Admin CAN edit (allowed by spec), so use a second non-admin, non-owner account instead.
    nisha_login = client.post("/api/auth/login", json={"email": "nisha@campusinnovators.in", "password": "Campus@123"})
    assert nisha_login.status_code == 200
    nisha_token = nisha_login.json()["access_token"]

    forbidden = client.put(
        f"/api/opportunities/{opportunity_id}",
        json={"title": "Hijacked title"},
        headers=_auth(nisha_token),
    )
    assert forbidden.status_code == 403

    forbidden_delete = client.delete(f"/api/opportunities/{opportunity_id}", headers=_auth(nisha_token))
    assert forbidden_delete.status_code == 403

    # Owner can still edit while pending.
    allowed = client.put(
        f"/api/opportunities/{opportunity_id}",
        json={"title": "Updated title"},
        headers=_auth(student_token),
    )
    assert allowed.status_code == 200
    assert allowed.json()["title"] == "Updated title"


def test_owner_cannot_edit_after_review(client):
    student_token = _login_student(client)
    admin_token = _login_admin(client)

    created = client.post("/api/opportunities", json=_payload(), headers=_auth(student_token))
    opportunity_id = created.json()["id"]
    client.patch(f"/api/opportunities/{opportunity_id}/review", json={"action": "approve"}, headers=_auth(admin_token))

    forbidden = client.put(
        f"/api/opportunities/{opportunity_id}",
        json={"title": "Too late"},
        headers=_auth(student_token),
    )
    assert forbidden.status_code == 403


def test_expired_excluded_from_default_list(client):
    admin_token = _login_admin(client)

    expired = client.post(
        "/api/opportunities",
        json=_payload(title="Expired Scholarship", type="scholarship", deadline=str(date.today() - timedelta(days=1))),
        headers=_auth(admin_token),
    )
    assert expired.status_code == 201
    expired_id = expired.json()["id"]

    active = client.post(
        "/api/opportunities",
        json=_payload(title="Active Scholarship", type="scholarship", deadline=str(date.today() + timedelta(days=10))),
        headers=_auth(admin_token),
    )
    assert active.status_code == 201
    active_id = active.json()["id"]

    default_listing = client.get("/api/opportunities")
    ids = [item["id"] for item in default_listing.json()]
    assert expired_id not in ids
    assert active_id in ids

    with_expired = client.get("/api/opportunities?include_expired=true")
    ids_with_expired = [item["id"] for item in with_expired.json()]
    assert expired_id in ids_with_expired
    assert active_id in ids_with_expired
