"""source_records -> contacts orchestration (SPEC.md §4, §6, §7, §11)."""

from __future__ import annotations

import json

from app.pipeline.build_contacts import build_contacts


def _sr(sr_id: str, **fields) -> dict:
    return {
        "id": sr_id,
        "source": "linkedin_export",
        "extracted_json": json.dumps(fields),
        "ingested_at": "2024-01-01T00:00:00Z",
    }


def test_builds_scored_classified_contact() -> None:
    recs = [
        _sr(
            "s1",
            first_name="Amina",
            last_name="Khalil",
            job_title="Chief Executive Officer",
            company="Acme Software",
            email="amina@acme.com",
        )
    ]
    contacts = build_contacts(recs)
    assert len(contacts) == 1
    c = contacts[0]
    assert c["seniority"] == "C-Level"
    assert c["industry"] == "Tech"
    assert c["importance"] > 0
    assert c["sources"] == ["s1"]
    assert c["field_provenance"]["job_title"] == "s1"


def test_dedup_merges_same_email_and_reclassifies() -> None:
    # s1 has no title (Unknown); s2 (same email) has CEO -> merged contact must upgrade.
    recs = [
        _sr("s1", first_name="Amina", last_name="Khalil", company="Acme", email="a@x.com"),
        _sr(
            "s2",
            first_name="Amina",
            last_name="Khalil",
            job_title="CEO",
            company="Acme",
            email="a@x.com",
        ),
    ]
    contacts = build_contacts(recs)
    assert len(contacts) == 1
    c = contacts[0]
    assert set(c["sources"]) == {"s1", "s2"}
    assert c["job_title"] == "CEO"  # filled from s2
    assert c["seniority"] == "C-Level"  # re-derived after merge, not stuck at Unknown


def test_fuzzy_match_flags_review_not_merge() -> None:
    # Same last name + near company, no shared email/phone -> separate contact, needs_review.
    recs = [
        _sr("s1", first_name="Amina", last_name="Khalil", company="Acme Corp"),
        _sr("s2", first_name="Aminah", last_name="Khalil", company="Acme Corporation"),
    ]
    contacts = build_contacts(recs)
    assert len(contacts) == 2  # not auto-merged (§7)
    assert any(c["needs_review"] for c in contacts)


def test_importance_is_deterministic() -> None:
    recs = [_sr("s1", first_name="A", last_name="B", job_title="Manager", company="Acme")]
    assert build_contacts(recs)[0]["importance"] == build_contacts(recs)[0]["importance"]
