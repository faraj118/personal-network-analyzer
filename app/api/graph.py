"""Graph route — nodes/edges for visualization (SPEC.md §10)."""

from __future__ import annotations

from fastapi import APIRouter

from app.discovery.service import graph_payload

router = APIRouter(tags=["graph"])


@router.get("/graph")
def graph() -> dict:
    """Contact graph as nodes + weighted edges (shared company/location/seniority)."""
    return graph_payload()
