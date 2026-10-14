"""Opportunity pipeline: stage per contact, Kanban board (UX pages)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import (
    add_manual_contact,
    connect,
    edit_contact,
    init_db,
    pipeline_board,
    rebuild_contacts,
)
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "pipe.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_stage_groups_and_survives_rebuild() -> None:
    conn = connect()
    try:
        a = add_manual_contact(conn, {"first_name": "V", "last_name": "P", "company": "Visa"})
        edit_contact(conn, a, {"pipeline_stage": "Talking"})
        rebuild_contacts(conn)  # stage persists via overlay
        board = pipeline_board(conn)
    finally:
        conn.close()
    assert any(c["id"] == a for c in board["Talking"])
    assert board["Won"] == []


def test_pipeline_page_renders() -> None:
    conn = connect()
    try:
        a = add_manual_contact(conn, {"first_name": "Lena", "last_name": "F", "company": "Nova"})
        edit_contact(conn, a, {"pipeline_stage": "Proposal"})
    finally:
        conn.close()
    r = TestClient(app).get("/pipeline")
    assert r.status_code == 200
    assert "Pipeline" in r.text and "Proposal" in r.text and "Lena" in r.text
    assert 'href="/pipeline"' in r.text  # nav present


def test_api_patch_sets_stage() -> None:
    client = TestClient(app)
    created = client.post("/contacts", json={"first_name": "Z", "company": "Acme"})
    cid = created.json()["id"]
    r = client.patch(f"/contacts/{cid}", json={"pipeline_stage": "Won"})
    assert r.status_code == 200 and r.json()["pipeline_stage"] == "Won"
