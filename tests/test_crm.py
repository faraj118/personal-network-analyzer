"""CRM: stable ids + add/edit/delete that SURVIVE rebuilds (crm-direction, §11, §18)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import (
    add_manual_contact,
    connect,
    decide_enrichment,
    edit_contact,
    fetch_contact,
    fetch_contacts,
    fetch_pending_enrichment,
    init_db,
    insert_enrichment_claims,
    insert_source_records,
    rebuild_contacts,
    soft_delete_contact,
)
from app.enrichment.base import EnrichmentClaim
from app.main import app
from app.pipeline.build_contacts import build_contacts
from app.pipeline.ingest_csv import ingest_linkedin_csv

_CSV = (
    "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
    "Amina,Khalil,,,Acme Software,Manager,01 Jan 2024\n"
)


def _sr(sr_id: str, **f) -> dict:
    return {
        "id": sr_id,
        "source": "linkedin_export",
        "extracted_json": json.dumps(f),
        "ingested_at": "2024",
    }


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "crm.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_ids_are_stable_across_builds_and_keyed_by_email() -> None:
    recs = [_sr("s1", first_name="Amina", last_name="Khalil", company="Acme", email="a@x.com")]
    id_a = build_contacts(recs)[0]["id"]
    id_b = build_contacts(recs)[0]["id"]
    assert id_a == id_b  # deterministic
    # same email, different source row / company -> same stable id
    recs2 = [_sr("s9", first_name="A", last_name="K", company="Other", email="a@x.com")]
    assert build_contacts(recs2)[0]["id"] == id_a


def _seed_one() -> str:
    conn = connect()
    try:
        insert_source_records(conn, ingest_linkedin_csv(_CSV.encode()))
        rebuild_contacts(conn)
        return fetch_contacts(conn)[0]["id"]
    finally:
        conn.close()


def test_edit_persists_across_rebuild() -> None:
    cid = _seed_one()
    conn = connect()
    try:
        edit_contact(conn, cid, {"opportunity": "Client", "notes": "VIP intro"})
        rebuild_contacts(conn)  # the real test
        c = fetch_contact(conn, cid)
    finally:
        conn.close()
    assert c["opportunity"] == "Client"
    assert c["notes"] == "VIP intro"


def test_delete_persists_across_rebuild() -> None:
    cid = _seed_one()
    conn = connect()
    try:
        soft_delete_contact(conn, cid)
        assert fetch_contact(conn, cid) is None
        rebuild_contacts(conn)  # stays gone
        assert fetch_contact(conn, cid) is None
    finally:
        conn.close()


def test_manual_add_survives_rebuild() -> None:
    conn = connect()
    try:
        new_id = add_manual_contact(
            conn, {"first_name": "Sara", "last_name": "Nour", "company": "Umbrella"}
        )
        assert fetch_contact(conn, new_id) is not None
        rebuild_contacts(conn)
        assert fetch_contact(conn, new_id) is not None
    finally:
        conn.close()


def test_accepted_enrichment_survives_rebuild() -> None:
    cid = _seed_one()
    conn = connect()
    try:
        insert_enrichment_claims(
            conn,
            [
                EnrichmentClaim(
                    contact_id=cid,
                    field="job_title",
                    value="VP",
                    method="web_public",
                    source_url="https://s",
                    confidence=0.9,
                )
            ],
        )
        rec = fetch_pending_enrichment(conn)[0]["id"]
        decide_enrichment(conn, rec, accept=True)
        rebuild_contacts(conn)  # accepted claim must be re-applied
        assert fetch_contact(conn, cid)["job_title"] == "VP"
    finally:
        conn.close()


def test_api_add_edit_delete() -> None:
    client = TestClient(app)
    created = client.post("/contacts", json={"first_name": "Lena", "company": "Nova"})
    assert created.status_code == 201
    cid = created.json()["id"]

    patched = client.patch(f"/contacts/{cid}", json={"opportunity": "Partner"})
    assert patched.status_code == 200 and patched.json()["opportunity"] == "Partner"

    assert client.delete(f"/contacts/{cid}").status_code == 200
    assert client.get(f"/contacts/{cid}").status_code == 404


def test_add_with_seniority_and_website_survives_rebuild() -> None:
    conn = connect()
    try:
        cid = add_manual_contact(
            conn,
            {
                "first_name": "Nadia",
                "last_name": "Suleiman",
                "company": "Zephyr",
                "seniority": "Director",
                "website": "https://zephyr.example",
            },
        )
        c = fetch_contact(conn, cid)
        assert c["seniority"] == "Director" and c["website"] == "https://zephyr.example"
        rebuild_contacts(conn)
        c = fetch_contact(conn, cid)
        assert c["seniority"] == "Director" and c["website"] == "https://zephyr.example"
    finally:
        conn.close()


def test_editing_seniority_rescoring() -> None:
    conn = connect()
    try:
        cid = add_manual_contact(conn, {"first_name": "A", "last_name": "B", "company": "C"})
        before = fetch_contact(conn, cid)["importance"]  # Unknown seniority -> low
        edit_contact(conn, cid, {"seniority": "C-Level"})
        after = fetch_contact(conn, cid)["importance"]
        assert after > before  # score reflects the manual seniority edit
    finally:
        conn.close()


def test_edit_email_and_phone_persist_across_rebuild() -> None:
    cid = _seed_one()
    conn = connect()
    try:
        edit_contact(conn, cid, {"email": "amina@new.ly", "phone": "+218911111111"})
        rebuild_contacts(conn)
        c = fetch_contact(conn, cid)
    finally:
        conn.close()
    assert c["email"] == "amina@new.ly"
    assert c["phone"] == "+218911111111"


def test_edit_duplicate_email_is_skipped_not_crash() -> None:
    conn = connect()
    try:
        add_manual_contact(
            conn, {"first_name": "A", "last_name": "One", "company": "X", "email": "dup@x.com"}
        )
        b = add_manual_contact(conn, {"first_name": "B", "last_name": "Two", "company": "Y"})
        res = edit_contact(
            conn, b, {"email": "dup@x.com", "phone": "+218922222222"}
        )  # must not raise
        assert res is not None
        assert fetch_contact(conn, b)["email"] != "dup@x.com"  # duplicate skipped
        assert (
            fetch_contact(conn, b)["phone"] == "+218922222222"
        )  # non-conflicting field still applied
    finally:
        conn.close()
