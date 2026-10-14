"""Web UI smoke tests (SPEC.md §2 frontend)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import init_db
from app.main import app

_CSV = (
    "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
    "Amina,Khalil,https://x,amina@acme.com,Acme Software,Chief Executive Officer,01 Jan 2024\n"
)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "web.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_home_renders() -> None:
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "PNCA — Your Network" in r.text


def test_upload_then_home_shows_scored_contact() -> None:
    client = TestClient(app)
    up = client.post(
        "/ui/upload",
        files={"files": ("Connections.csv", _CSV.encode("utf-8"), "text/csv")},
        follow_redirects=True,
    )
    assert up.status_code == 200
    assert "Khalil" in up.text  # contact rendered
    assert "C-Level" in up.text  # classified
    assert "Acme Software" in up.text  # company
