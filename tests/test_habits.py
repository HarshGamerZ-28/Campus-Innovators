from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_rate_limit(monkeypatch):
    # Same isolation test_skills.py/test_tasks.py/test_opportunities.py use: the
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


def _create_habit(client, token: str, label: str = "Read 20 pages") -> dict:
    created = client.post("/api/habits", json={"label": label, "tone": "purple"}, headers=_auth(token))
    assert created.status_code == 201
    return created.json()


def test_new_habit_has_seven_day_history_all_incomplete(client):
    token = _login(client)
    habit = _create_habit(client, token)

    assert "last_7_days" in habit
    assert len(habit["last_7_days"]) == 7
    assert all(day["completed"] is False for day in habit["last_7_days"])


def test_toggle_marks_today_complete_in_history(client):
    token = _login(client)
    habit = _create_habit(client, token)

    toggled = client.post(f"/api/habits/{habit['id']}/toggle", headers=_auth(token))
    assert toggled.status_code == 200
    body = toggled.json()

    assert len(body["last_7_days"]) == 7
    today_entry = body["last_7_days"][-1]
    assert today_entry["completed"] is True

    # Other six days remain untouched/incomplete for a brand-new habit.
    assert all(day["completed"] is False for day in body["last_7_days"][:-1])


def test_untoggle_keeps_row_but_marks_incomplete(client):
    token = _login(client)
    habit = _create_habit(client, token)

    first = client.post(f"/api/habits/{habit['id']}/toggle", headers=_auth(token))
    assert first.json()["last_7_days"][-1]["completed"] is True

    second = client.post(f"/api/habits/{habit['id']}/toggle", headers=_auth(token))
    assert second.status_code == 200
    body = second.json()
    assert body["complete"] is False
    # Row for today still exists in the 7-entry array (not deleted), just flipped back.
    assert len(body["last_7_days"]) == 7
    assert body["last_7_days"][-1]["completed"] is False


def test_list_habits_includes_seven_day_history(client):
    token = _login(client)
    habit = _create_habit(client, token)
    client.post(f"/api/habits/{habit['id']}/toggle", headers=_auth(token))

    listing = client.get("/api/habits", headers=_auth(token))
    assert listing.status_code == 200
    matches = [item for item in listing.json() if item["id"] == habit["id"]]
    assert len(matches) == 1
    assert len(matches[0]["last_7_days"]) == 7
    assert matches[0]["last_7_days"][-1]["completed"] is True


def test_history_dates_are_last_seven_consecutive_days_ending_today(client):
    from datetime import date, timedelta

    token = _login(client)
    habit = _create_habit(client, token)

    expected_dates = [(date.today() - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
    actual_dates = [day["date"] for day in habit["last_7_days"]]
    assert actual_dates == expected_dates
