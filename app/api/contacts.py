"""Contacts routes (SPEC.md §10)."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel

from app.db import (
    add_interaction,
    add_manual_contact,
    connect,
    edit_contact,
    fetch_contact,
    fetch_contacts,
    rebuild_contacts,
    soft_delete_contact,
)
from app.enrichment.profile import profile_for
from app.llm.brief import prep_brief
from app.llm.outreach import draft_outreach

router = APIRouter(tags=["contacts"])


class ContactEdit(BaseModel):
    """User corrections / CRM fields. Any subset; only editable columns are applied."""

    first_name: str | None = None
    last_name: str | None = None
    job_title: str | None = None
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    industry: str | None = None
    seniority: str | None = None
    opportunity: str | None = None
    website: str | None = None
    notes: str | None = None
    tags: str | None = None
    follow_up_date: str | None = None
    pipeline_stage: str | None = None


class ContactNew(ContactEdit):
    pass


class InteractionIn(BaseModel):
    occurred_on: str = ""  # YYYY-MM-DD; defaults to today
    kind: str = "note"  # met | call | email | message | note | intro
    note: str = ""


def _hydrate(row: dict) -> dict:
    """Decode JSON columns for the API response."""
    row = dict(row)
    for col in ("sources", "field_provenance"):
        if isinstance(row.get(col), str):
            try:
                row[col] = json.loads(row[col])
            except (ValueError, TypeError):
                pass
    row["needs_review"] = bool(row.get("needs_review"))
    return row


@router.get("/contacts")
def list_contacts(
    q: str | None = None,
    industry: str | None = None,
    seniority: str | None = None,
    min_score: int | None = None,
    needs_review: bool | None = None,
) -> dict:
    conn = connect()
    try:
        rows = fetch_contacts(conn, q, industry, seniority, min_score, needs_review)
    finally:
        conn.close()
    return {"count": len(rows), "contacts": [_hydrate(r) for r in rows]}


@router.get("/contacts/{contact_id}")
def get_contact(contact_id: str) -> dict:
    conn = connect()
    try:
        row = fetch_contact(conn, contact_id)
    finally:
        conn.close()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    return _hydrate(row)


@router.get("/contacts/{contact_id}/profile")
def get_profile(contact_id: str) -> dict:
    """Assembled profile: base + accepted sourced claims + signals (SPEC.md §18)."""
    d = profile_for(contact_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    return d


@router.post("/contacts/rebuild")
def rebuild() -> dict:
    """Rebuild contacts from all source_records (SPEC.md §11). Idempotent."""
    conn = connect()
    try:
        count = rebuild_contacts(conn)
    finally:
        conn.close()
    return {"contacts": count}


@router.post("/contacts", status_code=status.HTTP_201_CREATED)
def create_contact(new: ContactNew) -> dict:
    """Add a contact manually (stored as a source_record; survives rebuilds)."""
    conn = connect()
    try:
        cid = add_manual_contact(conn, new.model_dump(exclude_none=True))
        if cid is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no usable fields")
        row = fetch_contact(conn, cid)
    finally:
        conn.close()
    return _hydrate(row) if row else {"id": cid}


@router.patch("/contacts/{contact_id}")
def patch_contact(contact_id: str, edits: ContactEdit) -> dict:
    """Correct/manage a contact. Edits persist across rebuilds via the CRM overlay."""
    conn = connect()
    try:
        row = edit_contact(conn, contact_id, edits.model_dump(exclude_none=True))
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    return _hydrate(row)


@router.post("/contacts/{contact_id}/draft")
def draft_message(contact_id: str, intent: str = "reconnect") -> dict:
    """Draft an outreach message with the local LLM (null if the LLM is off/unreachable)."""
    d = profile_for(contact_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    text = draft_outreach(d, intent)
    return {"draft": text, "llm_available": text is not None}


@router.post("/contacts/{contact_id}/brief")
def brief_message(contact_id: str) -> dict:
    """Meeting/call prep brief via the local LLM (null if the LLM is off/unreachable)."""
    d = profile_for(contact_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    text = prep_brief(d)
    return {"brief": text, "llm_available": text is not None}


@router.post("/contacts/{contact_id}/interactions", status_code=status.HTTP_201_CREATED)
def log_interaction(contact_id: str, body: InteractionIn) -> dict:
    """Log a dated touchpoint (met/call/email/…). Survives rebuilds."""
    conn = connect()
    try:
        rec = add_interaction(conn, contact_id, body.occurred_on, body.kind, body.note)
    finally:
        conn.close()
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    return {"id": rec}


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: str) -> dict:
    """Delete a contact (soft — stays suppressed across rebuilds)."""
    conn = connect()
    try:
        ok = soft_delete_contact(conn, contact_id)
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact not found")
    return {"deleted": contact_id}


@router.get("/opportunities")
def opportunities(limit: int = 20) -> dict:
    """Top-N contacts by importance (SPEC.md §10)."""
    conn = connect()
    try:
        rows = fetch_contacts(conn)
    finally:
        conn.close()
    return {"opportunities": [_hydrate(r) for r in rows[:limit]]}


_EXPORT_COLUMNS = [
    "first_name",
    "last_name",
    "job_title",
    "company",
    "email",
    "phone",
    "location",
    "industry",
    "seniority",
    "opportunity",
    "org_tier",
    "importance",
    "pipeline_stage",
    "tags",
    "notes",
    "follow_up_date",
    "website",
]


@router.get("/export")
def export(format: str = "csv") -> Response:
    """Download all contacts as CSV or JSON (your data, portable)."""
    conn = connect()
    try:
        rows = fetch_contacts(conn)
    finally:
        conn.close()
    if format == "json":
        body = json.dumps([_hydrate(r) for r in rows], ensure_ascii=False, indent=2)
        return Response(
            body,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=pnca-contacts.json"},
        )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_EXPORT_COLUMNS)
    for r in rows:
        writer.writerow([r.get(c, "") if r.get(c) is not None else "" for c in _EXPORT_COLUMNS])
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=pnca-contacts.csv"},
    )
