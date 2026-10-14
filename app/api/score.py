"""Scoring route (SPEC.md §10). Phase-0 stub."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["score"])


@router.post("/score/rebuild", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def rebuild_scores() -> dict:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "score: implemented in Phase 2")
