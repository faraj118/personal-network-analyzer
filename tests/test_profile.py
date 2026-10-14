"""Profile assembly (SPEC.md §18 Tier-3): compose profile from sourced claims + signals."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import init_db
from app.enrichment.profile import assemble_profile
from app.main import app

_CSV = (
    "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
    "Amina,Khalil,,,Acme Software,Chief Executive Officer,01 Jan 2024\n"
)


def test_assemble_partitions_and_counts_sources() -> None:
    contact = {
        "id": "c1",
        "first_name": "A",
        "last_name": "B",
        "job_title": "CEO",
        "company": "Acme",
        "importance": 70,
        "field_provenance": {"job_title": "csv"},
    }
    claims = [
        {"field": "bio", "value": "Founder", "source_url": "https://x", "status": "accepted"},
        {"field": "job_title", "value": "CEO", "source_url": "https://y", "status": "pending"},
    ]
    signals = [{"kind": "company_news", "summary": "raised $1M", "source_url": "https://z"}]
    d = assemble_profile(contact, claims, signals)
    assert [c["field"] for c in d["accepted_claims"]] == ["bio"]
    assert [c["field"] for c in d["pending_claims"]] == ["job_title"]
    assert d["sources_count"] == 1  # one accepted source_url
    assert d["contact"]["job_title"] == "CEO"
    assert d["provenance"]["job_title"] == "csv"


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "dos.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def _seed(client: TestClient) -> str:
    client.post(
        "/ui/upload",
        files={"files": ("c.csv", _CSV.encode("utf-8"), "text/csv")},
        follow_redirects=True,
    )
    return client.get("/contacts").json()["contacts"][0]["id"]


def test_profile_endpoint_and_page() -> None:
    client = TestClient(app)
    cid = _seed(client)
    d = client.get(f"/contacts/{cid}/profile").json()
    assert set(d) >= {"contact", "accepted_claims", "pending_claims", "signals", "sources_count"}
    page = client.get(f"/contact/{cid}")
    assert page.status_code == 200 and "Khalil" in page.text


def test_add_claim_via_detail_then_accept_shows_in_profile() -> None:
    client = TestClient(app)
    cid = _seed(client)
    # add a sourced claim from the detail page (form-encoded)
    r = client.post(
        f"/ui/contact/{cid}/claim",
        data={
            "field": "profile_url",
            "value": "https://li/amina",
            "source_url": "https://li/amina",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert client.get(f"/contacts/{cid}/profile").json()["pending_claims"]  # now pending

    rec_id = client.get("/review/queue").json()["pending"][0]["id"]
    client.post(f"/ui/review/{rec_id}/accept")
    accepted = client.get(f"/contacts/{cid}/profile").json()["accepted_claims"]
    assert any(c["field"] == "profile_url" for c in accepted)
