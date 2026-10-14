"""Phase-0 smoke tests: port always 8199, default host localhost, schema applies, health."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import init_db
from app.main import app


@pytest.fixture(autouse=True)
def _clear_config_cache():
    """get_config is lru_cached; reset it so per-test env changes take effect."""
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def test_port_is_always_8199(monkeypatch: pytest.MonkeyPatch) -> None:
    # Port comes solely from app.yaml and is never overridable by env.
    monkeypatch.setenv("PNCA_HOST", "0.0.0.0")  # deployment override present...
    cfg = get_config()
    assert cfg.server.port == 8199  # ...port unaffected. Never 8000.


def test_default_host_is_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    # With no deployment override, the file default binds localhost-only (§12).
    monkeypatch.delenv("PNCA_HOST", raising=False)
    assert get_config().server.host == "127.0.0.1"


def test_host_override_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PNCA_HOST", "0.0.0.0")
    assert get_config().server.host == "0.0.0.0"


def test_schema_applies_to_throwaway_db(tmp_path: Path) -> None:
    db = tmp_path / "throwaway.db"
    init_db(db)
    conn = sqlite3.connect(db)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"source_records", "contacts"} <= names


def test_health_route_reports_configured_port() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["bind"].endswith(":8199")
