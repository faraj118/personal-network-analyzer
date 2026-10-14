"""Settings control-center page (UX pages)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import add_manual_contact, connect, init_db
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "set.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_settings_page_renders() -> None:
    conn = connect()
    try:
        add_manual_contact(conn, {"first_name": "A", "last_name": "B", "company": "Acme"})
    finally:
        conn.close()
    r = TestClient(app).get("/settings")
    assert r.status_code == 200
    assert "Settings" in r.text
    assert "Target industries" in r.text and "Local AI" in r.text
    assert 'href="/settings"' in r.text  # nav present


def test_settings_rebuild_action() -> None:
    client = TestClient(app)
    r = client.post("/ui/settings/rebuild", follow_redirects=False)
    assert r.status_code == 303
