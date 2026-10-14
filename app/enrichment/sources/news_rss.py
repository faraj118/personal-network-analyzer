"""First free source: news RSS -> opportunity signals (SPEC.md §18 Tier-1).

Given a contact's company, query a public news RSS endpoint and turn recent items into
'company_news' signals. Parsed with stdlib xml.etree (no heavy dep). All fetches go through
PoliteFetcher, so robots/rate-limit/stop-on-block apply. Free public source only.
"""

from __future__ import annotations

import hashlib
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

from app.enrichment.fetch import Blocked

# Public Google News RSS search. Configurable target could move to config later.
_SEARCH_TEMPLATE = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
_MAX_ITEMS = 5


def build_query_url(company: str) -> str:
    return _SEARCH_TEMPLATE.format(q=quote_plus(f'"{company}"'))


def signals_from_feed(xml_text: str, contact_id: str, limit: int = _MAX_ITEMS) -> list[dict]:
    """Parse RSS XML into signal dicts. Tolerant of malformed input (returns [])."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    signals: list[dict] = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        signals.append(
            {
                "contact_id": contact_id,
                "kind": "company_news",
                "summary": title,
                "source_url": link,
                "confidence": 0.5,
                "content_hash": hashlib.sha256(f"{contact_id}\x00{link}".encode()).hexdigest(),
            }
        )
    return signals


def scan_contact(contact: dict, fetcher) -> list[dict]:
    """Fetch news for a contact's company -> signals. Blocked/no-company -> [] (compliant)."""
    company = (contact.get("company") or "").strip()
    if not company:
        return []
    try:
        res = fetcher.get(build_query_url(company))
    except Blocked:
        return []  # robots/rate-limit block -> stop, no circumvention (§18)
    if res.status != 200:
        return []
    return signals_from_feed(res.text, contact["id"])
