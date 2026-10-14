"""Enrichment routes (SPEC.md §10, §18). Submit sourced claims (review-gated)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.enrichment.base import EnrichmentClaim
from app.enrichment.company_intel import scan_companies
from app.enrichment.service import contact_exists, submit_claims

router = APIRouter(tags=["enrich"])


class ClaimIn(BaseModel):
    """A sourced claim about a contact. source_url is mandatory (provenance, §18)."""

    field: str  # job_title | company | location | email | phone | bio | profile_url
    value: str
    source_url: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


@router.post("/enrich/{contact_id}", status_code=status.HTTP_201_CREATED)
def enrich_contact(contact_id: str, claim: ClaimIn) -> dict:
    """Record a sourced claim -> lands as 'pending' for review; never auto-writes contacts."""
    if not contact_exists(contact_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    ec = EnrichmentClaim(
        contact_id=contact_id,
        field=claim.field,
        value=claim.value,
        method="web_public",
        source_url=claim.source_url,
        confidence=claim.confidence,
    )
    inserted = submit_claims([ec])
    return {"status": "pending", "inserted": inserted}


@router.post("/company/scan")
def company_scan(limit: int | None = None) -> dict:
    """Score org prominence via Wikidata for your companies (due-diligence, §18). May be slow."""
    scanned = scan_companies(limit=limit)
    return {"companies_scanned": scanned}
