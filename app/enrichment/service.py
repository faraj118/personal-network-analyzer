"""Enrichment service (SPEC.md §18): submit sourced claims, review-gate, promote.

Claims land as 'pending' and never touch contacts until accepted. Automated free-source
adapters (Phase 6) feed the same path; for now claims can also be entered manually with a
source URL — provenance is mandatory either way.
"""

from __future__ import annotations

from app.db import (
    connect,
    decide_enrichment,
    fetch_contact,
    fetch_pending_enrichment,
    insert_enrichment_claims,
)
from app.enrichment.base import EnrichmentClaim


def contact_exists(contact_id: str) -> bool:
    conn = connect()
    try:
        return fetch_contact(conn, contact_id) is not None
    finally:
        conn.close()


def submit_claims(claims: list[EnrichmentClaim]) -> int:
    conn = connect()
    try:
        return insert_enrichment_claims(conn, claims)
    finally:
        conn.close()


def review_queue() -> list[dict]:
    conn = connect()
    try:
        return fetch_pending_enrichment(conn)
    finally:
        conn.close()


def decide(rec_id: str, accept: bool) -> dict | None:
    conn = connect()
    try:
        return decide_enrichment(conn, rec_id, accept)
    finally:
        conn.close()
