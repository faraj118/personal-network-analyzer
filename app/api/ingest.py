"""Ingest routes (SPEC.md §10). Phase 1a: synchronous CSV ingest -> source_records."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.db import connect, insert_source_records, rebuild_contacts
from app.pipeline.ingest_card import card_to_source_record
from app.pipeline.ingest_csv import ingest_linkedin_csv

router = APIRouter(tags=["ingest"])

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")


@router.post("/ingest")
async def ingest(files: Annotated[list[UploadFile], File(...)]) -> dict:
    """Ingest one or more LinkedIn export CSVs. Idempotent by content_hash (§11)."""
    results: list[dict] = []
    conn = connect()
    try:
        for f in files:
            if not (f.filename or "").lower().endswith(".csv"):
                raise HTTPException(
                    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    f"{f.filename}: only .csv supported in Phase 1a",
                )
            records = ingest_linkedin_csv(await f.read(), origin_file=f.filename)
            inserted = insert_source_records(conn, records)
            results.append({"file": f.filename, "parsed": len(records), "inserted": inserted})
        # Rebuild the derived contacts view so upload -> contacts is one step (§11).
        contacts = rebuild_contacts(conn)
    finally:
        conn.close()
    return {"files": results, "contacts": contacts}


@router.post("/ingest/card")
async def ingest_card(files: Annotated[list[UploadFile], File(...)]) -> dict:
    """Ingest business-card images (JPG/PNG): OCR -> extract -> contact, review-gated (§6)."""
    results: list[dict] = []
    conn = connect()
    try:
        for f in files:
            if not (f.filename or "").lower().endswith(_IMAGE_EXTS):
                raise HTTPException(
                    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"{f.filename}: image files only"
                )
            sr = card_to_source_record(await f.read(), origin_file=f.filename)
            if sr is None:
                results.append({"file": f.filename, "ocr": "empty"})
                continue
            inserted = insert_source_records(conn, [sr])
            results.append(
                {"file": f.filename, "ocr_confidence": sr.ocr_confidence, "inserted": inserted}
            )
        contacts = rebuild_contacts(conn)
    finally:
        conn.close()
    return {"files": results, "contacts": contacts}


@router.get("/jobs/{job_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def job_status(job_id: str) -> dict:
    # Async job queue arrives with the OCR/card path (heavier work).
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "jobs: implemented with the card path")
