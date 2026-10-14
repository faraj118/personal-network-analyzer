"""Tier-3 profile assembly (SPEC.md §18).

Compose a per-contact profile from the base contact + ACCEPTED sourced claims + signals.
No invented content: every enriched line traces to a source_url. Pending claims are surfaced
separately (they haven't been accepted, so they are not part of the profile yet).
"""

from __future__ import annotations

from app.db import (
    connect,
    fetch_contact,
    fetch_enrichment_for_contact,
    fetch_interactions,
    fetch_signals_for,
    last_contacted,
)

_BASE_FIELDS = (
    "first_name",
    "last_name",
    "job_title",
    "company",
    "email",
    "phone",
    "location",
    "industry",
    "seniority",
    "opportunity",
    "importance",
    "website",
    "org_tier",
    "notes",
    "tags",
    "follow_up_date",
    "pipeline_stage",
)


def assemble_profile(
    contact: dict,
    claims: list[dict],
    signals: list[dict],
    score: dict | None = None,
    interactions: list[dict] | None = None,
    last_contact: str | None = None,
) -> dict:
    """Pure assembly. `claims` are enrichment_records for this contact (any status)."""
    accepted = [c for c in claims if c.get("status") == "accepted"]
    pending = [c for c in claims if c.get("status") == "pending"]
    return {
        "contact": {f: contact.get(f) for f in _BASE_FIELDS} | {"id": contact["id"]},
        "provenance": contact.get("field_provenance") or {},
        "score": score
        or {},  # {total, components:[{factor, detail, points}]} — "why this priority"
        "accepted_claims": accepted,  # sourced extras (incl. bio/profile_url not in contacts)
        "pending_claims": pending,  # awaiting review — NOT part of the profile yet
        "signals": signals,
        "interactions": interactions or [],  # dated touchpoint history
        "last_contact": last_contact,  # most recent touchpoint date (or None)
        "sources_count": len({c.get("source_url") for c in accepted if c.get("source_url")}),
    }


def profile_for(contact_id: str) -> dict | None:
    """Load a contact + its claims/signals and assemble the profile. None if no contact."""
    conn = connect()
    try:
        contact = fetch_contact(conn, contact_id)
        if contact is None:
            return None
        claims = fetch_enrichment_for_contact(conn, contact_id)
        signals = fetch_signals_for(conn, contact_id)
        interactions = fetch_interactions(conn, contact_id)
        last_contact = last_contacted(conn, contact_id)
    finally:
        conn.close()
    from app.pipeline.score import score_breakdown
    from app.rules import get_rubric

    score = score_breakdown(contact, get_rubric())
    # field_provenance is stored as JSON text — decode for the assembler.
    import json

    if isinstance(contact.get("field_provenance"), str):
        try:
            contact["field_provenance"] = json.loads(contact["field_provenance"])
        except (ValueError, TypeError):
            contact["field_provenance"] = {}
    return assemble_profile(
        contact, claims, signals, score=score, interactions=interactions, last_contact=last_contact
    )
