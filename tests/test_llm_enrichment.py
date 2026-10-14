"""Seam tests for LLM + enrichment (SPEC.md §7, §17, §18)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.config import get_config
from app.db import init_db
from app.enrichment.base import EnrichmentClaim
from app.llm.client import LlmUnavailable, OllamaClient


@pytest.fixture(autouse=True)
def _clear_cache():
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def test_enrichment_tables_exist(tmp_path: Path) -> None:
    db = tmp_path / "e.db"
    init_db(db)
    conn = sqlite3.connect(db)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"enrichment_records", "signals"} <= names


def test_config_has_llm_and_enrichment_defaults() -> None:
    cfg = get_config()
    assert cfg.llm.enabled is False  # deterministic path works without it
    assert cfg.enrichment.free_sources_only is True
    assert cfg.enrichment.stop_on_block is True
    assert cfg.enrichment.exclude_special_category is True


def test_llm_degrades_when_disabled() -> None:
    # enabled=False -> available() is False and generate() refuses (no crash, no network).
    client = OllamaClient(cfg=get_config().llm)
    assert client.available() is False
    with pytest.raises(LlmUnavailable):
        client.generate("hello")


def test_web_claim_requires_source_url() -> None:
    with pytest.raises(ValueError):
        EnrichmentClaim(contact_id="c1", field="job_title", value="CTO", method="web_public")
    ok = EnrichmentClaim(
        contact_id="c1",
        field="job_title",
        value="CTO",
        method="web_public",
        source_url="https://example.com/x",
        confidence=0.8,
    )
    assert ok.source_url is not None


def test_claim_confidence_bounds() -> None:
    with pytest.raises(ValueError):
        EnrichmentClaim(
            contact_id="c1",
            field="company",
            value="Acme",
            method="rss",
            source_url="https://x",
            confidence=1.5,
        )
