"""Company prominence scan (scoring-v2-prominence): Wikidata due-diligence over your orgs.

Manual/triggered pass: for each distinct company in your contacts, resolve a prominence tier
from Wikidata (free API), store it, then rebuild so contacts pick up org_tier and re-score.
Skips companies already scanned. `fetch` is injected for offline testing.
"""

from __future__ import annotations

from app.db import (
    company_intel_key_exists,
    connect,
    distinct_companies,
    rebuild_contacts,
    upsert_company_intel,
)
from app.enrichment.sources.wikidata import Fetch, _http_fetch, lookup_company


def scan_companies(
    limit: int | None = None, fetch: Fetch = _http_fetch, refresh: bool = False
) -> int:
    """Look up prominence for companies not yet scanned. Returns number scanned."""
    conn = connect()
    try:
        companies = distinct_companies(conn)
        if not refresh:
            companies = [c for c in companies if not company_intel_key_exists(conn, c)]
        if limit:
            companies = companies[:limit]
        for company in companies:
            info = lookup_company(company, fetch)
            upsert_company_intel(conn, company, info)
        scanned = len(companies)
        if scanned:
            rebuild_contacts(conn)  # attach org_tier + re-score
        return scanned
    finally:
        conn.close()
