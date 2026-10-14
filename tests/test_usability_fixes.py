"""Usability fixes: clear a field, org-tier accent-safe match, interactive pipeline move."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import (
    add_manual_contact,
    connect,
    edit_contact,
    fetch_contact,
    init_db,
    rebuild_contacts,
    upsert_company_intel,
)
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "u.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_clear_unsets_field_and_survives_rebuild() -> None:
    conn = connect()
    try:
        cid = add_manual_contact(conn, {"first_name": "A", "last_name": "B", "company": "Acme"})
        edit_contact(conn, cid, {"opportunity": "Client"})
        assert fetch_contact(conn, cid)["opportunity"] == "Client"
        edit_contact(conn, cid, {"opportunity": "__clear__"})  # explicit clear
        assert fetch_contact(conn, cid)["opportunity"] is None
        rebuild_contacts(conn)
        assert fetch_contact(conn, cid)["opportunity"] is None  # clear persists
    finally:
        conn.close()


def test_org_tier_matches_uppercase_accented_company() -> None:
    conn = connect()
    try:
        cid = add_manual_contact(
            conn, {"first_name": "A", "last_name": "B", "company": "CAFÉ CORP"}
        )
        upsert_company_intel(
            conn, "CAFÉ CORP", {"tier": "global", "label": "Café", "source_url": "x"}
        )
        rebuild_contacts(conn)  # Python-lower match (SQLite lower() would miss the É)
        assert fetch_contact(conn, cid)["org_tier"] == "global"
    finally:
        conn.close()


def test_pipeline_stage_move_and_remove_from_board() -> None:
    client = TestClient(app)
    conn = connect()
    try:
        cid = add_manual_contact(conn, {"first_name": "V", "last_name": "P", "company": "Visa"})
        edit_contact(conn, cid, {"pipeline_stage": "Idea"})
    finally:
        conn.close()
    client.post(f"/ui/contact/{cid}/stage", data={"stage": "Won"})
    conn = connect()
    try:
        assert fetch_contact(conn, cid)["pipeline_stage"] == "Won"
    finally:
        conn.close()
    client.post(f"/ui/contact/{cid}/stage", data={"stage": "__clear__"})
    conn = connect()
    try:
        assert fetch_contact(conn, cid)["pipeline_stage"] is None
    finally:
        conn.close()
