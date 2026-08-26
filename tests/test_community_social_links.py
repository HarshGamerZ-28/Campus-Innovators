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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register_non_admin(client, admin_token: str, *, email: str, username: str) -> str:
    allowlisted = client.post(
        "/api/admin/allowed-emails",
        json={"email": email, "note": "test"},
        headers=_auth(admin_token),
    )
    assert allowlisted.status_code == 201

    register = client.post(
        "/api/auth/register",
        json={
            "name": "Regular Member",
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


def test_public_platform_defaults_to_empty_social_links(client):
    response = client.get("/api/public/platform")
    assert response.status_code == 200
    body = response.json()
    assert body["club_instagram_url"] == ""
    assert body["club_linkedin_url"] == ""


def test_admin_can_set_both_links_and_public_get_reflects_it(client):
    token = _login_admin(client)

    updated = client.patch(
        "/api/admin/community-social-links",
        json={
            "instagram_url": "https://instagram.com/campusinnovators",
            "linkedin_url": "https://linkedin.com/company/campusinnovators",
        },
        headers=_auth(token),
    )
    assert updated.status_code == 200
    assert updated.json()["club_instagram_url"] == "https://instagram.com/campusinnovators"
    assert updated.json()["club_linkedin_url"] == "https://linkedin.com/company/campusinnovators"

    public = client.get("/api/public/platform")
    assert public.status_code == 200
    assert public.json()["club_instagram_url"] == "https://instagram.com/campusinnovators"
    assert public.json()["club_linkedin_url"] == "https://linkedin.com/company/campusinnovators"


def test_patch_only_touches_the_field_that_was_sent(client):
    token = _login_admin(client)

    client.patch(
        "/api/admin/community-social-links",
        json={"instagram_url": "https://instagram.com/campusinnovators", "linkedin_url": "https://linkedin.com/company/campusinnovators"},
        headers=_auth(token),
    )

    instagram_only = client.patch(
        "/api/admin/community-social-links",
        json={"instagram_url": "https://instagram.com/new_handle"},
        headers=_auth(token),
    )
    assert instagram_only.status_code == 200
    assert instagram_only.json()["club_instagram_url"] == "https://instagram.com/new_handle"
    # linkedin_url was never sent in this PATCH, so it must be untouched.
    assert instagram_only.json()["club_linkedin_url"] == "https://linkedin.com/company/campusinnovators"


def test_non_admin_patch_is_forbidden(client):
    admin_token = _login_admin(client)
    member_token = _register_non_admin(client, admin_token, email="member@example.com", username="regularmember")

    response = client.patch(
        "/api/admin/community-social-links",
        json={"instagram_url": "https://instagram.com/campusinnovators"},
        headers=_auth(member_token),
    )
    assert response.status_code == 403


def test_invalid_url_format_is_rejected(client):
    token = _login_admin(client)

    response = client.patch(
        "/api/admin/community-social-links",
        json={"instagram_url": "not-a-url"},
        headers=_auth(token),
    )
    assert response.status_code == 422


def test_clearing_a_link_to_empty_works(client):
    token = _login_admin(client)

    client.patch(
        "/api/admin/community-social-links",
        json={"instagram_url": "https://instagram.com/campusinnovators", "linkedin_url": "https://linkedin.com/company/campusinnovators"},
        headers=_auth(token),
    )

    cleared = client.patch(
        "/api/admin/community-social-links",
        json={"instagram_url": ""},
        headers=_auth(token),
    )
    assert cleared.status_code == 200
    assert cleared.json()["club_instagram_url"] == ""
    assert cleared.json()["club_linkedin_url"] == "https://linkedin.com/company/campusinnovators"

    public = client.get("/api/public/platform")
    assert public.json()["club_instagram_url"] == ""
