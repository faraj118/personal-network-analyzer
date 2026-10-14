"""News-source signals + Review UI (SPEC.md §18 Tier-1). No live network — fetch mocked."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import init_db
from app.enrichment.fetch import Blocked, FetchResult
from app.enrichment.signals import scan_signals
from app.enrichment.sources.news_rss import scan_contact, signals_from_feed
from app.main import app

_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Acme raises $10M Series A</title><link>https://news.example/acme-a</link></item>
<item><title>Acme hires new VP of Sales</title><link>https://news.example/acme-vp</link></item>
</channel></rss>"""

_CSV = (
    "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
    "Amina,Khalil,,,Acme Software,Manager,01 Jan 2024\n"
)


class _FeedFetcher:
    def __init__(self, xml: str, status: int = 200) -> None:
        self._xml, self._status = xml, status

    def get(self, url: str) -> FetchResult:
        return FetchResult(url=url, status=self._status, text=self._xml, fetched_at="now")


class _BlockedFetcher:
    def get(self, url: str) -> FetchResult:
        raise Blocked("robots/429")


# --- pure parsing / scan (no DB) ---


def test_feed_parses_to_signals() -> None:
    sigs = signals_from_feed(_RSS, "c1")
    assert len(sigs) == 2
    assert sigs[0]["kind"] == "company_news"
    assert sigs[0]["summary"].startswith("Acme raises")
    assert sigs[0]["source_url"] == "https://news.example/acme-a"


def test_feed_tolerates_garbage() -> None:
    assert signals_from_feed("not xml", "c1") == []


def test_scan_contact_needs_company_and_stops_on_block() -> None:
    assert scan_contact({"id": "c1", "company": ""}, _FeedFetcher(_RSS)) == []
    assert scan_contact({"id": "c1", "company": "Acme"}, _BlockedFetcher()) == []
    assert len(scan_contact({"id": "c1", "company": "Acme"}, _FeedFetcher(_RSS))) == 2


# --- orchestration + Review UI (isolated DB) ---


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "sig.db"))
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


def test_scan_stores_signals_and_is_idempotent() -> None:
    client = TestClient(app)
    _seed(client)
    first = scan_signals(fetcher=_FeedFetcher(_RSS))
    second = scan_signals(fetcher=_FeedFetcher(_RSS))  # same links -> deduped
    assert first == 2
    assert second == 0
    assert client.get("/signals").json()["count"] == 2


def test_review_page_shows_pending_and_accept_flow() -> None:
    client = TestClient(app)
    _seed(client)
    cid = client.get("/contacts").json()["contacts"][0]["id"]
    client.post(
        f"/enrich/{cid}",
        json={"field": "job_title", "value": "VP Sales", "source_url": "https://co/team"},
    )
    page = client.get("/review")
    assert page.status_code == 200
    assert "VP Sales" in page.text and "Review" in page.text

    rec_id = client.get("/review/queue").json()["pending"][0]["id"]
    r = client.post(f"/ui/review/{rec_id}/accept", follow_redirects=False)
    assert r.status_code == 303
    assert client.get(f"/contacts/{cid}").json()["job_title"] == "VP Sales"
