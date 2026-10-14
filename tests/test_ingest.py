"""Phase 1a: LinkedIn CSV ingest -> source_records (mapping, idempotency, endpoint)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import connect, init_db, insert_source_records
from app.main import app
from app.pipeline.ingest_csv import ingest_linkedin_csv

# Real LinkedIn exports prepend a "Notes:" preamble before the header row.
_CSV = (
    "Notes:\n"
    '"When exporting, some fields may be blank."\n'
    "\n"
    "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
    "Amina,Khalil,https://lnkd.in/a,amina@example.com,Acme,CTO,01 Jan 2024\n"
    "Omar,Saleh,https://lnkd.in/b,,Globex,Manager,15 Feb 2024\n"
    ",,,,,,\n"  # blank row -> skipped
)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the app DB at a temp file so tests never touch data/pnca.db."""
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "test.db"))
    get_config.cache_clear()
    init_db()  # TestClient(app) w/o a context manager doesn't run lifespan; init explicitly
    yield
    get_config.cache_clear()


def test_parses_and_maps_with_preamble() -> None:
    recs = ingest_linkedin_csv(_CSV.encode("utf-8"), origin_file="Connections.csv")
    assert len(recs) == 2  # blank row skipped
    assert all(r.source.value == "linkedin_export" for r in recs)
    assert all(r.origin_file == "Connections.csv" for r in recs)
    # content_hash is deterministic and unique per distinct row
    assert len({r.content_hash for r in recs}) == 2


def test_ingest_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "i.db"
    init_db(db)
    conn = connect(db)
    try:
        first = insert_source_records(conn, ingest_linkedin_csv(_CSV.encode("utf-8")))
        # Re-parse: fresh UUID ids, identical content_hash -> hash index must dedupe.
        second = insert_source_records(conn, ingest_linkedin_csv(_CSV.encode("utf-8")))
        total = conn.execute("SELECT COUNT(*) FROM source_records").fetchone()[0]
    finally:
        conn.close()
    assert first == 2
    assert second == 0  # duplicates skipped by content_hash
    assert total == 2


def test_ingest_endpoint_rejects_non_csv() -> None:
    client = TestClient(app)
    resp = client.post("/ingest", files={"files": ("notes.txt", b"hello", "text/plain")})
    assert resp.status_code == 415


def test_ingest_endpoint_accepts_csv() -> None:
    client = TestClient(app)
    resp = client.post(
        "/ingest", files={"files": ("Connections.csv", _CSV.encode("utf-8"), "text/csv")}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["files"][0]["parsed"] == 2
    assert body["files"][0]["inserted"] == 2  # fresh isolated DB
