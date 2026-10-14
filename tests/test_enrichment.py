"""Enrichment backbone (SPEC.md §18): polite fetch + review-gated claim flow."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import EnrichmentConfig, get_config
from app.db import init_db
from app.enrichment.fetch import Blocked, PoliteFetcher
from app.main import app

_CSV = (
    "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
    "Amina,Khalil,,,Acme Software,Manager,01 Jan 2024\n"
)


# --- PoliteFetcher (no network: injected fake client, delays off, robots skipped) ---


class _Resp:
    def __init__(self, status: int, text: str = "") -> None:
        self.status_code = status
        self.text = text


class _FakeHttp:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp

    def get(self, url, headers=None):
        return self._resp

    def close(self):
        pass


def _fetcher() -> PoliteFetcher:
    cfg = EnrichmentConfig(min_delay_seconds=0, max_delay_seconds=0, respect_robots=False)
    return PoliteFetcher(cfg=cfg)


def test_fetch_ok() -> None:
    res = _fetcher().get("https://example.com/x", client=_FakeHttp(_Resp(200, "hello")))
    assert res.status == 200 and res.text == "hello"


def test_fetch_stops_on_block() -> None:
    for code in (401, 403, 429):
        with pytest.raises(Blocked):
            _fetcher().get("https://x/y", client=_FakeHttp(_Resp(code)))


# --- review-gated claim flow ---


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "enr.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def _seed_contact(client: TestClient) -> str:
    client.post(
        "/ui/upload",
        files={"files": ("c.csv", _CSV.encode("utf-8"), "text/csv")},
        follow_redirects=True,
    )
    return client.get("/contacts").json()["contacts"][0]["id"]


def test_claim_requires_source_url() -> None:
    client = TestClient(app)
    cid = _seed_contact(client)
    r = client.post(f"/enrich/{cid}", json={"field": "job_title", "value": "VP Sales"})
    assert r.status_code == 422  # source_url is mandatory (§18)


def test_enrich_unknown_contact_404() -> None:
    client = TestClient(app)
    r = client.post(
        "/enrich/nope", json={"field": "job_title", "value": "X", "source_url": "https://s"}
    )
    assert r.status_code == 404


def test_accept_promotes_claim_to_contact() -> None:
    client = TestClient(app)
    cid = _seed_contact(client)
    # submit a sourced claim -> pending
    r = client.post(
        f"/enrich/{cid}",
        json={"field": "job_title", "value": "VP Sales", "source_url": "https://co/team"},
    )
    assert r.status_code == 201 and r.json()["status"] == "pending"

    queue = client.get("/review/queue").json()
    assert queue["count"] == 1
    rec_id = queue["pending"][0]["id"]

    # accept -> promotes into the contact, with provenance
    dec = client.post(f"/review/{rec_id}", json={"decision": "accept"})
    assert dec.status_code == 200 and dec.json()["status"] == "accepted"

    contact = client.get(f"/contacts/{cid}").json()
    assert contact["job_title"] == "VP Sales"
    assert contact["field_provenance"]["job_title"] == "https://co/team"


def test_reject_leaves_contact_unchanged() -> None:
    client = TestClient(app)
    cid = _seed_contact(client)
    before = client.get(f"/contacts/{cid}").json()["job_title"]
    client.post(
        f"/enrich/{cid}",
        json={"field": "job_title", "value": "Ghost Title", "source_url": "https://s"},
    )
    rec_id = client.get("/review/queue").json()["pending"][0]["id"]
    client.post(f"/review/{rec_id}", json={"decision": "reject"})
    after = client.get(f"/contacts/{cid}").json()["job_title"]
    assert after == before  # rejected claim never touches the contact
