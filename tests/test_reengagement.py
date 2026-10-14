"""Re-engagement nudges: important contacts gone quiet (ux-direction)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import add_interaction, add_manual_contact, connect, init_db, reconnect_candidates
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "re.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_reconnect_surfaces_dormant_important_only() -> None:
    conn = connect()
    try:
        a = add_manual_contact(
            conn, {"first_name": "A", "last_name": "Imp", "company": "Visa", "seniority": "C-Level"}
        )
        b = add_manual_contact(
            conn,
            {"first_name": "B", "last_name": "Fresh", "company": "Acme", "seniority": "C-Level"},
        )
        add_interaction(
            conn, b, datetime.now(UTC).date().isoformat(), "call", "just talked"
        )  # recent -> excluded
        add_manual_contact(
            conn, {"first_name": "C", "last_name": "Low"}
        )  # low importance -> excluded
        ids = {x["id"] for x in reconnect_candidates(conn, days=90, min_importance=20)}
    finally:
        conn.close()
    assert a in ids  # important + never contacted
    assert b not in ids  # contacted today


def test_home_shows_reconnect() -> None:
    conn = connect()
    try:
        add_manual_contact(
            conn,
            {"first_name": "Z", "last_name": "Cold", "company": "Visa", "seniority": "C-Level"},
        )
    finally:
        conn.close()
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "Reconnect" in r.text
