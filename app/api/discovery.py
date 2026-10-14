"""Discovery route — the flagship Type-B output (SPEC.md §8, §10)."""

from __future__ import annotations

from fastapi import APIRouter

from app.discovery.service import discovery_payload

router = APIRouter(tags=["discovery"])


@router.get("/discovery")
def discovery(top_n: int = 10) -> dict:
    """Centrality hubs, communities, bridges, gaps, and warm leads over your network."""
    return discovery_payload(top_n=top_n)
