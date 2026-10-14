"""Tier-1 signal scanning (SPEC.md §18): free news over KNOWN contacts.

Manual/triggered pass only (no unattended looping). Each contact's company is queried via
the news_rss source through PoliteFetcher; results are deduped and stored as `signals`.
"""

from __future__ import annotations

from app.db import connect, fetch_contacts, insert_signals
from app.enrichment.fetch import PoliteFetcher
from app.enrichment.sources.news_rss import scan_contact


def scan_signals(limit_contacts: int | None = None, fetcher: PoliteFetcher | None = None) -> int:
    """Scan (a slice of) contacts for news signals. Returns number of new signals stored."""
    conn = connect()
    try:
        contacts = fetch_contacts(conn)
    finally:
        conn.close()
    if limit_contacts:
        contacts = contacts[:limit_contacts]

    fetcher = fetcher or PoliteFetcher()
    found: list[dict] = []
    for c in contacts:
        found.extend(scan_contact(c, fetcher))
    if not found:
        return 0

    conn = connect()
    try:
        return insert_signals(conn, found)
    finally:
        conn.close()
