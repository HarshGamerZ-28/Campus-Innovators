from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def _isolated_rate_limit(monkeypatch):
    # Same isolation test_tasks.py/test_opportunities.py use: the limiter backend
    # is a module-level singleton shared by every test in the process, so without
    # this, logins from earlier tests in the run count against this file's budget.
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


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _create_meeting(client, admin_token: str, *, title: str, when: datetime, visible: bool) -> dict:
    payload = {
        "title": title,
        "description": "Weekly sync",
        "scheduled_at": _iso(when),
        "location": "Room 204",
        "visible_on_events": visible,
    }
    created = client.post("/api/admin/meetings", json=payload, headers=_auth(admin_token))
    assert created.status_code == 201
    return created.json()


def _create_event(client, token: str, *, title: str, when: datetime) -> dict:
    payload = {
        "title": title,
        "description": "Campus-wide happening",
        "venue": "Main Auditorium",
        "event_date": _iso(when),
        "capacity": 30,
    }
    created = client.post("/api/events", json=payload, headers=_auth(token))
    assert created.status_code == 201
    return created.json()


def test_visible_meeting_appears_on_events_feed(client):
    admin_token = _login_admin(client)
    when = datetime.now(timezone.utc) + timedelta(days=3)
    meeting = _create_meeting(client, admin_token, title="Open Club Sync", when=when, visible=True)

    listing = client.get("/api/events", headers=_auth(admin_token))
    assert listing.status_code == 200
    matches = [item for item in listing.json() if item["source"] == "meeting" and item["id"] == meeting["id"]]
    assert len(matches) == 1
    item = matches[0]
    assert item["title"] == "Open Club Sync"
    assert item["location"] == "Room 204"
    assert item["attendee_count"] == 0
    assert item["capacity"] is None
    assert item["registered_count"] is None


def test_hidden_meeting_does_not_appear_on_events_feed(client):
    admin_token = _login_admin(client)
    when = datetime.now(timezone.utc) + timedelta(days=3)
    meeting = _create_meeting(client, admin_token, title="Internal Admin Sync", when=when, visible=False)

    listing = client.get("/api/events", headers=_auth(admin_token))
    assert listing.status_code == 200
    assert all(not (item["source"] == "meeting" and item["id"] == meeting["id"]) for item in listing.json())

    # But it's still visible in the admin-only meetings list, untouched.
    admin_listing = client.get("/api/admin/meetings", headers=_auth(admin_token))
    assert admin_listing.status_code == 200
    assert any(item["id"] == meeting["id"] for item in admin_listing.json())


def test_real_events_still_appear_on_events_feed(client):
    student_token = _login_student(client)
    when = datetime.now(timezone.utc) + timedelta(days=5)
    event = _create_event(client, student_token, title="Hack Night", when=when)

    listing = client.get("/api/events", headers=_auth(student_token))
    assert listing.status_code == 200
    matches = [item for item in listing.json() if item["source"] == "event" and item["id"] == event["id"]]
    assert len(matches) == 1
    item = matches[0]
    assert item["title"] == "Hack Night"
    assert item["capacity"] == 30
    assert item["registered_count"] == 0
    assert item["attendee_count"] is None


def test_merged_feed_is_sorted_by_date(client):
    admin_token = _login_admin(client)
    student_token = _login_student(client)
    now = datetime.now(timezone.utc)

    later_event = _create_event(client, student_token, title="Later Event", when=now + timedelta(days=10))
    soonest_meeting = _create_meeting(
        client, admin_token, title="Soonest Meeting", when=now + timedelta(days=1), visible=True
    )
    middle_event = _create_event(client, student_token, title="Middle Event", when=now + timedelta(days=5))

    listing = client.get("/api/events", headers=_auth(student_token))
    assert listing.status_code == 200
    body = listing.json()

    ids_in_order = [(item["source"], item["id"]) for item in body]
    expected_order = [("meeting", soonest_meeting["id"]), ("event", middle_event["id"]), ("event", later_event["id"])]
    # Filter down to just the three items we created, preserving relative order.
    relevant = [entry for entry in ids_in_order if entry in expected_order]
    assert relevant == expected_order
