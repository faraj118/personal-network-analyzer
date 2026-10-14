"""Data Health page: missing fields, review queue, backup (UX pages)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import add_manual_contact, connect, data_health_summary, init_db
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "dh.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def _seed() -> None:
    conn = connect()
    try:
        add_manual_contact(
            conn, {"first_name": "A", "last_name": "1", "company": "Acme"}
        )  # no email
        add_manual_contact(
            conn,
            {
                "first_name": "B",
                "last_name": "2",
                "company": "Acme Software",
                "email": "b@x.com",
                "seniority": "C-Level",
            },
        )
    finally:
        conn.close()


def test_summary_counts_missing() -> None:
    _seed()
    conn = connect()
    try:
        h = data_health_summary(conn)
    finally:
        conn.close()
    assert h["total"] == 2
    assert h["missing_email"] == 1  # only A lacks email
    assert "needs_review" in h and isinstance(h["needs_review"], list)


def test_data_health_page_renders() -> None:
    _seed()
    r = TestClient(app).get("/data-health")
    assert r.status_code == 200
    assert "Data Health" in r.text and 'href="/data-health"' in r.text
