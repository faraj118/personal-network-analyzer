"""Opportunity-signals routes (SPEC.md §10, §18 Tier-1)."""

from __future__ import annotations

from fastapi import APIRouter

from app.db import connect, fetch_signals
from app.enrichment.signals import scan_signals

router = APIRouter(tags=["signals"])


@router.get("/signals")
def list_signals() -> dict:
    """Opportunity signals detected over known contacts (job change, funding, ...)."""
    conn = connect()
    try:
        signals = fetch_signals(conn)
    finally:
        conn.close()
    return {"count": len(signals), "signals": signals}


@router.post("/signals/scan")
def scan(limit: int | None = None) -> dict:
    """Manually trigger ONE free-source news scan over contacts (§18). May be slow (rate-limited)."""
    stored = scan_signals(limit_contacts=limit)
    return {"new_signals": stored}
