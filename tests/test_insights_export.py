"""Insights rollup + CSV/JSON export (UX pages, data portability)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import add_manual_contact, connect, init_db, insights_summary
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "ins.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def _seed() -> None:
    conn = connect()
    try:
        add_manual_contact(
            conn,
            {
                "first_name": "A",
                "last_name": "T",
                "company": "Acme Software",
                "seniority": "C-Level",
                "email": "a@x.com",
            },
        )
        add_manual_contact(
            conn,
            {"first_name": "B", "last_name": "F", "company": "Sahara Bank", "seniority": "Manager"},
        )
    finally:
        conn.close()


def test_insights_summary_counts() -> None:
    _seed()
    conn = connect()
    try:
        s = insights_summary(conn)
    finally:
        conn.close()
    assert s["total"] == 2
    assert s["target_total"] >= 1  # Acme Software -> Tech (a target industry)
    assert s["target_senior"] >= 1  # the C-Level in Tech
    assert s["with_email"] == 1
    assert set(s["pipeline"]) == {"Idea", "Talking", "Proposal", "Won", "Lost"}


def test_insights_page_renders() -> None:
    _seed()
    r = TestClient(app).get("/insights")
    assert r.status_code == 200
    assert "Insights" in r.text and 'href="/insights"' in r.text


def test_export_csv_and_json() -> None:
    _seed()
    client = TestClient(app)
    csv_r = client.get("/export", params={"format": "csv"})
    assert csv_r.status_code == 200
    assert csv_r.headers["content-type"].startswith("text/csv")
    assert "first_name" in csv_r.text and "Acme Software" in csv_r.text

    json_r = client.get("/export", params={"format": "json"})
    assert json_r.status_code == 200
    assert json_r.headers["content-type"].startswith("application/json")
    assert len(json_r.json()) == 2
