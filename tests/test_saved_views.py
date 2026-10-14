"""Segments / saved views + tag/pipeline filters (ux-direction)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import (
    add_manual_contact,
    connect,
    delete_view,
    edit_contact,
    fetch_contacts,
    fetch_views,
    init_db,
    save_view,
)
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "sv.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_tag_and_stage_filters() -> None:
    conn = connect()
    try:
        a = add_manual_contact(conn, {"first_name": "A", "last_name": "1", "company": "Acme"})
        edit_contact(conn, a, {"tags": "investor", "pipeline_stage": "Talking"})
        add_manual_contact(conn, {"first_name": "B", "last_name": "2", "company": "Globex"})
        assert [c["id"] for c in fetch_contacts(conn, tag="investor")] == [a]
        assert [c["id"] for c in fetch_contacts(conn, pipeline_stage="Talking")] == [a]
    finally:
        conn.close()


def test_save_list_delete_view_drops_empty_params() -> None:
    conn = connect()
    try:
        vid = save_view(conn, "Fintech GCC", {"industry": "Fintech", "seniority": ""})
        views = fetch_views(conn)
        assert any(v["name"] == "Fintech GCC" for v in views)
        assert views[0]["params"] == {"industry": "Fintech"}  # empty dropped
        delete_view(conn, vid)
        assert fetch_views(conn) == []
    finally:
        conn.close()


def test_ui_save_view_shows_on_home() -> None:
    client = TestClient(app)
    r = client.post(
        "/ui/views/save", data={"name": "My targets", "industry": "Fintech"}, follow_redirects=False
    )
    assert r.status_code == 303
    assert "My targets" in client.get("/").text
