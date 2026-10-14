"""Review-queue routes (SPEC.md §10, §18). Accept/reject pending enrichment claims."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.enrichment.service import decide, review_queue

router = APIRouter(tags=["review"])


class Decision(BaseModel):
    decision: str  # "accept" | "reject"


@router.get("/review/queue")
def get_queue() -> dict:
    """Pending enrichment claims awaiting a human decision."""
    pending = review_queue()
    return {"count": len(pending), "pending": pending}


@router.get("/review/{item_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def review_item(item_id: str) -> dict:
    # Side-by-side card review lands with the OCR/card path.
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "card review: with the card path")


@router.post("/review/{item_id}")
def decide_review(item_id: str, body: Decision) -> dict:
    """Accept (promote to contact) or reject a pending enrichment claim (§18)."""
    if body.decision not in ("accept", "reject"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "decision must be accept|reject")
    updated = decide(item_id, accept=body.decision == "accept")
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "claim not found")
    return updated
