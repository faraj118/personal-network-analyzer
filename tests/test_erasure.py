"""Erasure cascade: deleting a contact must purge its personal data (SPEC.md §12/§18)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_config
from app.db import (
    add_interaction,
    add_manual_contact,
    connect,
    fetch_interactions,
    fetch_signals_for,
    init_db,
    insert_enrichment_claims,
    insert_signals,
    soft_delete_contact,
)
from app.enrichment.base import EnrichmentClaim


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "erase.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def _pending_count(conn, contact_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM enrichment_records WHERE contact_id=?", (contact_id,)
    ).fetchone()[0]


def test_delete_cascades_enrichment_signals_interactions() -> None:
    conn = connect()
    try:
        cid = add_manual_contact(conn, {"first_name": "Erase", "last_name": "Me"})
        add_interaction(conn, cid, "2026-01-01", "call", "spoke")
        insert_signals(
            conn,
            [
                {
                    "contact_id": cid,
                    "kind": "job_change",
                    "summary": "moved",
                    "source_url": "https://x/1",
                }
            ],
        )
        insert_enrichment_claims(
            conn,
            [
                EnrichmentClaim(
                    contact_id=cid,
                    field="bio",
                    value="v",
                    method="web_public",
                    source_url="https://x/2",
                    confidence=0.5,
                )
            ],
        )
        # sanity: the personal data is there
        assert fetch_interactions(conn, cid) and fetch_signals_for(conn, cid)
        assert _pending_count(conn, cid) == 1

        assert soft_delete_contact(conn, cid) is True

        # ...and now fully gone — nothing orphaned to re-attach on a future re-import
        assert fetch_interactions(conn, cid) == []
        assert fetch_signals_for(conn, cid) == []
        assert _pending_count(conn, cid) == 0
    finally:
        conn.close()


def test_delete_missing_contact_returns_false() -> None:
    conn = connect()
    try:
        assert soft_delete_contact(conn, "does-not-exist") is False
    finally:
        conn.close()
