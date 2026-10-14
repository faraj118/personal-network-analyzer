"""Org prominence via Wikidata (scoring-v2-prominence). Fetch mocked — no live calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_config
from app.db import add_manual_contact, connect, fetch_contact, init_db
from app.enrichment.company_intel import scan_companies
from app.enrichment.sources.wikidata import lookup_company, prominence_tier
from app.pipeline.score import score_breakdown
from app.rules import get_rubric


def _fake(search: dict, entity: dict):
    def f(url: str) -> dict:
        return search if "wbsearchentities" in url else entity

    return f


_PUBLIC_ENTITY = {
    "entities": {
        "Q1": {
            "labels": {"en": {"value": "Visa Inc."}},
            "claims": {
                "P31": [
                    {"mainsnak": {"datavalue": {"value": {"id": "Q891723"}}}}
                ],  # public company
                "P414": [{"x": 1}],  # listed on a stock exchange -> public
            },
        }
    }
}


def test_prominence_tiers() -> None:
    assert prominence_tier({"is_org": True, "is_public": True}) == "global"
    assert prominence_tier({"is_org": True, "employees": 50000}) == "global"
    assert prominence_tier({"is_org": True, "employees": 500}) == "established"
    assert prominence_tier({"is_org": True, "employees": 10}) == "verified_smb"
    assert prominence_tier({"is_org": False}) == "unverified"
    assert prominence_tier(None) == "unverified"


def test_lookup_public_company_is_global() -> None:
    info = lookup_company("Visa", _fake({"search": [{"id": "Q1"}]}, _PUBLIC_ENTITY))
    assert info["tier"] == "global"
    assert info["qid"] == "Q1"
    assert info["source_url"].endswith("Q1")


def test_lookup_unknown_is_unverified() -> None:
    info = lookup_company("Water Melon Production", _fake({"search": []}, {}))
    assert info["tier"] == "unverified"
    assert info["qid"] is None


def test_score_includes_org_prominence() -> None:
    b = score_breakdown({"seniority": "Director", "org_tier": "global"}, get_rubric())
    org = next(c for c in b["components"] if c["factor"] == "Organization")
    assert org["points"] == get_rubric()["weights"]["prominence"]["global"]


@pytest.fixture()
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "prom.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_scan_attaches_org_tier_and_lifts_score(_isolated_db) -> None:
    conn = connect()
    try:
        visa = add_manual_contact(
            conn, {"first_name": "V", "last_name": "P", "company": "Visa", "seniority": "Director"}
        )
        melon = add_manual_contact(
            conn,
            {
                "first_name": "M",
                "last_name": "A",
                "company": "Water Melon Production",
                "seniority": "Director",
            },
        )
        before = fetch_contact(conn, visa)["importance"]
    finally:
        conn.close()

    def scan_fetch(url: str) -> dict:
        if "wbsearchentities" in url:
            return {"search": [{"id": "Q1"}]} if "Visa" in url else {"search": []}
        return _PUBLIC_ENTITY

    assert scan_companies(fetch=scan_fetch) == 2

    conn = connect()
    try:
        v = fetch_contact(conn, visa)
        m = fetch_contact(conn, melon)
    finally:
        conn.close()
    assert v["org_tier"] == "global"
    assert v["importance"] > before  # Visa gains prominence points
    assert m["org_tier"] == "unverified"  # watermelon media -> no boost
