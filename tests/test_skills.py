from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_rate_limit(monkeypatch):
    # Same isolation test_tasks.py/test_opportunities.py/test_events.py use: the
    # limiter backend is a module-level singleton shared by every test in the
    # process, so without this, logins from earlier tests count against this
    # file's login budget too.
    from app import rate_limit

    monkeypatch.setattr(rate_limit, "_backend", rate_limit._InMemoryLimiter())


def _login(client) -> str:
    login = client.post("/api/auth/login", json={"email": "campusinnovators07@gmail.com", "password": "UniqueGeca20"})
    assert login.status_code == 200
    return login.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_high_progress_skill_is_mastered(client):
    token = _login(client)
    created = client.post(
        "/api/skills",
        json={"name": "Rust", "category": "skill", "tone": "orange", "progress": 95},
        headers=_auth(token),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["progress"] == 95
    assert body["is_mastered"] is True

    listing = client.get("/api/skills", headers=_auth(token))
    assert listing.status_code == 200
    matches = [item for item in listing.json() if item["id"] == body["id"]]
    assert len(matches) == 1
    assert matches[0]["is_mastered"] is True


def test_mid_progress_skill_is_not_mastered(client):
    token = _login(client)
    created = client.post(
        "/api/skills",
        json={"name": "Go", "category": "skill", "tone": "cyan", "progress": 60},
        headers=_auth(token),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["progress"] == 60
    assert body["is_mastered"] is False


def test_update_crossing_threshold_flips_is_mastered(client):
    token = _login(client)
    created = client.post(
        "/api/skills",
        json={"name": "TypeScript", "category": "skill", "tone": "blue", "progress": 40},
        headers=_auth(token),
    )
    assert created.status_code == 201
    assert created.json()["is_mastered"] is False
    skill_id = created.json()["id"]

    updated = client.patch(f"/api/skills/{skill_id}", json={"progress": 92}, headers=_auth(token))
    assert updated.status_code == 200
    assert updated.json()["progress"] == 92
    assert updated.json()["is_mastered"] is True

    reverted = client.patch(f"/api/skills/{skill_id}", json={"progress": 89}, headers=_auth(token))
    assert reverted.status_code == 200
    assert reverted.json()["is_mastered"] is False


def test_existing_seeded_skills_are_correctly_flagged_without_a_migration(client):
    # is_mastered is a derived property, not a stored column, so pre-existing
    # rows (seeded here, but equally "rows created before this feature shipped"
    # in a real deployment) get the correct value with zero backfill needed.
    token = _login(client)
    listing = client.get("/api/skills", headers=_auth(token))
    assert listing.status_code == 200
    body = listing.json()
    assert len(body) >= 1
    for item in body:
        assert item["is_mastered"] == (item["progress"] >= 90)


def test_public_profile_and_members_expose_is_mastered(client):
    profile = client.get("/api/public/profiles/campusinnovator")
    assert profile.status_code == 200
    profile_skills = profile.json()["skills"]
    assert len(profile_skills) >= 1
    for item in profile_skills:
        assert "is_mastered" in item

    members = client.get("/api/public/members")
    assert members.status_code == 200
    member_with_skills = next((m for m in members.json()["members"] if m["top_skills"]), None)
    assert member_with_skills is not None
    for skill in member_with_skills["top_skills"]:
        assert "is_mastered" in skill
