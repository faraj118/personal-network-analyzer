"""Enrichment contracts (SPEC.md §18). Provenance is mandatory, not optional.

Every enricher yields ``EnrichmentClaim``s — a value about a contact WITH its source, method,
and confidence. Claims land in ``enrichment_records`` as ``pending`` and are review-gated
before touching ``contacts``. No enricher may return a value it cannot source.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field, field_validator


class EnrichmentClaim(BaseModel):
    """A single sourced claim about a contact. Provenance fields are required."""

    contact_id: str
    field: str  # job_title | company | location | bio | profile_url | ...
    value: str
    method: str  # rss | web_public | llm_extract
    # NOTE: source_url must be declared AFTER method so the validator below can read the
    # already-validated method from info.data (Pydantic validates in declaration order).
    source_url: str | None = None  # required for web methods (validated below)
    model: str | None = None  # LLM model+version if the LLM was involved
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("value")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("claim value must be non-empty")
        return v

    @field_validator("source_url")
    @classmethod
    def _web_needs_source(cls, v: str | None, info) -> str | None:
        method = info.data.get("method")
        if method in {"rss", "web_public"} and not v:
            raise ValueError(f"method={method} requires source_url (§18 provenance)")
        return v


class Enricher(Protocol):
    """Yields sourced claims for a contact from ONE free public source."""

    def enrich(self, contact: dict) -> list[EnrichmentClaim]: ...
