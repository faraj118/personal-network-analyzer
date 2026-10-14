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


def test_search_form_with_empty_min_score() -> None:
    """The search form always submits every field; an empty min score must not 422."""
    client = TestClient(app)
    client.post(
        "/ui/upload", files={"files": ("Connections.csv", _CSV.encode("utf-8"), "text/csv")}
    )
    r = client.get("/?q=Khalil&industry=&seniority=&pipeline_stage=&tag=&min_score=")
    assert r.status_code == 200
    assert "Khalil" in r.text
    assert client.get("/?min_score=abc").status_code == 200  # junk is ignored, not an error
    assert client.get("/?min_score=101").status_code == 200


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
