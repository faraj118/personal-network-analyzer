"""Interaction history (ux-direction): dated touchpoints, last-contacted, survives rebuild."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import (
    add_interaction,
    add_manual_contact,
    connect,
    fetch_interactions,
    init_db,
    last_contacted,
    rebuild_contacts,
)
from app.enrichment.profile import profile_for
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "ix.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def _seed() -> str:
    conn = connect()
    try:
        return add_manual_contact(
            conn, {"first_name": "Omar", "last_name": "S", "company": "Globex"}
        )
    finally:
        conn.close()


def test_log_last_contacted_and_survives_rebuild() -> None:
    cid = _seed()
    conn = connect()
    try:
        add_interaction(conn, cid, "2026-09-01", "call", "intro call")
        add_interaction(conn, cid, "2026-09-20", "email", "sent proposal")
        assert last_contacted(conn, cid) == "2026-09-20"
        rebuild_contacts(conn)  # interactions must survive (keyed by stable id)
        assert len(fetch_interactions(conn, cid)) == 2
        assert last_contacted(conn, cid) == "2026-09-20"
    finally:
        conn.close()


def test_profile_includes_interactions() -> None:
    cid = _seed()
    conn = connect()
    try:
        add_interaction(conn, cid, "2026-09-10", "met", "met at GITEX")
    finally:
        conn.close()
    d = profile_for(cid)
    assert d["last_contact"] == "2026-09-10"
    assert any(i["note"] == "met at GITEX" for i in d["interactions"])


def test_api_log_interaction_and_404() -> None:
    client = TestClient(app)
    cid = _seed()
    ok = client.post(f"/contacts/{cid}/interactions", json={"kind": "call", "note": "quick call"})
    assert ok.status_code == 201
    assert client.get(f"/contacts/{cid}/profile").json()["interactions"]
    missing = client.post("/contacts/nope/interactions", json={"kind": "call"})
    assert missing.status_code == 404
