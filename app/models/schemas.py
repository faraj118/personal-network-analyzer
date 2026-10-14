"""Pydantic boundary models (SPEC.md §14). Typed I/O for the pipeline stages."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Source(str, Enum):
    linkedin_export = "linkedin_export"
    facebook = "facebook"
    business_card = "business_card"


class Seniority(str, Enum):
    c_level = "C-Level"
    director = "Director"
    manager = "Manager"
    entry = "Entry"
    unknown = "Unknown"


class Opportunity(str, Enum):
    client = "Client"
    partner = "Partner"
    supplier = "Supplier"
    other = "Other"


class SourceRecordIn(BaseModel):
    """A normalized source record ready to persist (SPEC.md §4). Immutable, provenance."""

    id: str
    source: Source
    origin_file: str | None = None
    raw_text: str | None = None  # JSON of the original row / OCR blob
    image_path: str | None = None
    extracted_json: str | None = None  # JSON of mapped fields
    ocr_confidence: float | None = None
    ingested_at: str
    content_hash: str  # idempotency


class ExtractionResult(BaseModel):
    """Output of extract.py — each field carries a confidence (SPEC.md §6)."""

    first_name: str | None = None
    last_name: str | None = None
    job_title: str | None = None
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    url: str | None = None
    confidence: dict[str, float] = Field(default_factory=dict)


class Task(BaseModel):
    """A user-authored to-do / reminder (crm-direction). May link to a contact.

    Typed boundary (SPEC.md §14): app/tasks.py returns these, not raw dicts, so a
    mistyped field fails loudly at the edge instead of silently in a template.
    """

    id: str
    title: str
    due_date: str | None = None  # YYYY-MM-DD
    done: bool = False
    contact_id: str | None = None
    contact_name: str | None = None  # denormalized for display (join at read time)
    notes: str | None = None
    created_at: str | None = None
    completed_at: str | None = None


class Contact(BaseModel):
    """Canonical contact (mirror of the contacts table, SPEC.md §4)."""

    id: str
    first_name: str | None = None
    last_name: str | None = None
    job_title: str | None = None
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    industry: str | None = None
    seniority: Seniority = Seniority.unknown
    opportunity: Opportunity | None = None
    importance: int = 0
    sources: list[str] = Field(default_factory=list)
    needs_review: bool = False
    field_provenance: dict[str, str] = Field(default_factory=dict)
