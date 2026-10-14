"""Companies page: network grouped by organization (UX pages)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import add_manual_contact, companies_summary, connect, init_db
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "co.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def _seed() -> None:
    conn = connect()
    try:
        add_manual_contact(
            conn, {"first_name": "A", "last_name": "1", "company": "Acme", "seniority": "C-Level"}
        )
        add_manual_contact(
            conn, {"first_name": "B", "last_name": "2", "company": "Acme", "seniority": "Manager"}
        )
        add_manual_contact(
            conn,
            {"first_name": "C", "last_name": "3", "company": "Globex", "seniority": "Director"},
        )
    finally:
        conn.close()


def test_summary_groups_by_company() -> None:
    _seed()
    conn = connect()
    try:
        rows = {r["name"]: r for r in companies_summary(conn)}
    finally:
        conn.close()
    assert rows["Acme"]["contacts"] == 2
    assert rows["Acme"]["senior"] == 1  # one C-Level, one Manager
    assert rows["Globex"]["contacts"] == 1


def test_companies_page_renders_with_nav() -> None:
    _seed()
    r = TestClient(app).get("/companies")
    assert r.status_code == 200
    assert "Companies" in r.text and "Acme" in r.text
    assert 'href="/companies"' in r.text  # persistent nav present
