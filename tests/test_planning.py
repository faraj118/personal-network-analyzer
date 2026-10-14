"""Follow-up planning + .ics calendar export (crm-direction)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import add_manual_contact, connect, edit_contact, init_db
from app.main import app
from app.planning import planning_view, to_ics


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "plan.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def _seed_two() -> None:
    conn = connect()
    try:
        past = add_manual_contact(
            conn, {"first_name": "Old", "last_name": "Lead", "company": "PastCo"}
        )
        soon = add_manual_contact(
            conn, {"first_name": "New", "last_name": "Lead", "company": "SoonCo"}
        )
        edit_contact(conn, past, {"follow_up_date": "2020-01-01"})
        edit_contact(conn, soon, {"follow_up_date": "2999-01-01"})
    finally:
        conn.close()


def test_partitions_overdue_and_upcoming() -> None:
    _seed_two()
    v = planning_view(today=date(2026, 9, 23))
    assert v["count"] == 2
    assert [i["name"] for i in v["overdue"]] == ["Old Lead"]
    assert [i["name"] for i in v["upcoming"]] == ["New Lead"]
    assert v["overdue"][0]["days"] < 0


def test_ics_is_valid_vcalendar() -> None:
    ics = to_ics([{"id": "x1", "name": "Amina", "company": "Acme", "follow_up_date": "2026-10-05"}])
    assert ics.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VEVENT" in ics and "END:VCALENDAR" in ics
    assert "DTSTART;VALUE=DATE:20261005" in ics
    assert "SUMMARY:Follow up: Amina (Acme)" in ics


def test_planning_api_and_ics_download() -> None:
    _seed_two()
    client = TestClient(app)
    assert set(client.get("/planning").json()) == {"overdue", "upcoming", "count"}
    ics = client.get("/planning.ics")
    assert ics.status_code == 200
    assert ics.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VCALENDAR" in ics.text


def test_planning_page_renders() -> None:
    _seed_two()
    r = TestClient(app).get("/calendar")
    assert r.status_code == 200
    assert "Planning" in r.text and "Add to calendar" in r.text
    assert "✓ Done" in r.text and "Reschedule" in r.text  # actionable


def test_ics_has_dtend_and_method() -> None:
    ics = to_ics([{"id": "x", "name": "A", "company": "B", "follow_up_date": "2026-10-05"}])
    assert "METHOD:PUBLISH" in ics
    assert "DTEND;VALUE=DATE:20261006" in ics  # exclusive end = next day


def test_ics_folds_long_and_arabic_lines() -> None:
    long_name = "محمد " * 20 + "A" * 60  # mixed Arabic + ASCII, well over 75 octets
    ics = to_ics(
        [{"id": "x", "name": long_name, "company": "شركة", "follow_up_date": "2026-10-05"}]
    )
    # every physical line must be <= 75 octets (RFC 5545 §3.1)
    for line in ics.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, line
    ics.encode("utf-8")  # no broken code points from folding on a boundary


def test_reschedule_sets_date_and_redirects_to_calendar() -> None:
    _seed_two()
    client = TestClient(app)
    cid = planning_view()["overdue"][0]["id"]
    r = client.post(
        f"/ui/contact/{cid}/reschedule",
        data={"follow_up_date": "2030-06-01", "next": "/calendar"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].startswith("/calendar")
    conn = connect()
    try:
        from app.db import fetch_contact

        assert fetch_contact(conn, cid)["follow_up_date"] == "2030-06-01"
    finally:
        conn.close()


def test_quick_actions_honor_next_and_block_open_redirect() -> None:
    _seed_two()
    client = TestClient(app)
    cid = planning_view()["upcoming"][0]["id"]
    ok = client.post(
        f"/ui/contact/{cid}/snooze",
        data={"days": 7, "next": "/calendar"},
        follow_redirects=False,
    )
    assert ok.headers["location"].startswith("/calendar")
    evil = client.post(
        f"/ui/contact/{cid}/snooze",
        data={"days": 7, "next": "https://evil.example/x"},
        follow_redirects=False,
    )
    assert evil.headers["location"].startswith("/?")  # falls back to safe default
