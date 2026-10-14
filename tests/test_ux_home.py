"""Dashboard: 'Today' action section + search/filter (ux-direction)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import add_manual_contact, connect, edit_contact, init_db
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "ux.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def _seed() -> None:
    conn = connect()
    try:
        a = add_manual_contact(
            conn,
            {
                "first_name": "Amina",
                "last_name": "Khalil",
                "company": "Acme",
                "opportunity": "Client",
            },
        )
        edit_contact(conn, a, {"follow_up_date": "2020-01-01"})  # overdue
        add_manual_contact(conn, {"first_name": "Omar", "last_name": "Saleh", "company": "Globex"})
    finally:
        conn.close()


def test_home_shows_today_and_overdue() -> None:
    _seed()
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "Today — who to reach out to" in r.text
    assert "Amina" in r.text  # overdue follow-up + top opportunity


def test_search_filters_table() -> None:
    _seed()
    client = TestClient(app)
    assert "Omar" in client.get("/", params={"q": "Omar"}).text
    assert "No matches" in client.get("/", params={"q": "Zzximpossible"}).text


def test_home_has_slim_nav_and_add_tabs() -> None:
    _seed()
    r = TestClient(app).get("/")
    # slimmed primary nav + collapsed "More" menu
    assert "More ▾" in r.text
    assert 'href="/settings"' in r.text  # still reachable, now under More
    # single tabbed "Add contacts" area replaces the three stacked forms
    assert "➕ Add contacts" in r.text
    for panel in ("LinkedIn export", "Business card", "Type it in"):
        assert panel in r.text
    # stats moved below the list and drill through
    assert 'href="/review"' in r.text
