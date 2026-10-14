"""Discovery API + Network page smoke tests (SPEC.md §8, §10)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import init_db
from app.main import app

# Two people share a company (-> an edge); a third is separate.
_CSV = (
    "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
    "Amina,Khalil,,,Acme Software,Chief Executive Officer,01 Jan 2024\n"
    "Bilal,Omar,,,Acme Software,Manager,02 Jan 2024\n"
    "Cala,Nour,,,Globex,Director,03 Jan 2024\n"
)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "disc.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def _seed(client: TestClient) -> None:
    client.post(
        "/ui/upload",
        files={"files": ("c.csv", _CSV.encode("utf-8"), "text/csv")},
        follow_redirects=True,
    )


def test_discovery_endpoint_shape() -> None:
    client = TestClient(app)
    _seed(client)
    d = client.get("/discovery").json()
    assert set(d) == {"hubs", "communities", "bridges", "gaps", "warm_leads"}
    assert d["gaps"]["by_seniority"]  # populated


def test_graph_endpoint_has_nodes_and_edge() -> None:
    client = TestClient(app)
    _seed(client)
    g = client.get("/graph").json()
    assert len(g["nodes"]) == 3
    assert len(g["edges"]) >= 1  # Amina & Bilal share Acme Software


def test_network_page_renders() -> None:
    client = TestClient(app)
    _seed(client)
    r = client.get("/network")
    assert r.status_code == 200
    assert "Your network map" in r.text
