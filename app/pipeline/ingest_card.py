"""Business-card image -> source_record (SPEC.md §5, §6 card path).

image (JPG/PNG) -> OCR (en+ar) -> deterministic + LLM field extraction -> a
business_card source_record. OCR is injectable so the pipeline is testable without
Tesseract; the real path uses app.pipeline.ocr.run_ocr. Below-threshold OCR is kept for
review, never silently trusted (§6).
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.models.schemas import Source, SourceRecordIn
from app.pipeline.extract import _URL_RE, extract_fields

_CARD_FIELDS = ("first_name", "last_name", "job_title", "company", "email", "phone", "location")

_TITLE_HINTS = re.compile(
    r"\b(ceo|cto|cfo|coo|founder|co-?founder|president|vp|vice[ -]?president|director|"
    r"manager|head|chief|officer|engineer|consultant|analyst|specialist|lead|partner|"
    r"owner|sales|marketing|architect|advisor|executive)\b",
    re.IGNORECASE,
)
_COMPANY_HINTS = re.compile(
    r"\b(inc|llc|ltd|co|company|corp|corporation|group|holdings?|technolog(?:y|ies)|"
    r"solutions?|systems?|bank|services?|gmbh|plc|labs?|studio|agency|consulting)\b",
    re.IGNORECASE,
)


def _is_contact_line(s: str) -> bool:
    """Line that's an email / URL / mostly-digits (phone) — not a name/company."""
    if "@" in s or _URL_RE.search(s):
        return True
    digits = sum(c.isdigit() for c in s)
    return digits >= max(5, len(s) // 2)


def guess_card_fields(text: str) -> dict[str, str]:
    """Heuristic name/title/company from OCR lines — a prefill for review (§6).

    Deliberately rough: the LLM (§17) does this better when enabled, but with it off a
    card would otherwise produce a nameless contact. The user confirms/edits before save,
    so a wrong guess costs nothing.
    """
    lines = [ln.strip(" \t|•·—-") for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln]
    text_lines = [ln for ln in lines if not _is_contact_line(ln)]
    guess: dict[str, str] = {}

    for ln in text_lines:
        if _TITLE_HINTS.search(ln):
            guess["job_title"] = ln
            break
    for ln in text_lines:
        if ln == guess.get("job_title"):
            continue
        if _COMPANY_HINTS.search(ln):
            guess["company"] = ln
            break
    for ln in text_lines:
        if ln in (guess.get("job_title"), guess.get("company")):
            continue
        words = ln.split()
        if (
            1 < len(words) <= 4
            and not any(c.isdigit() for c in ln)
            and all(any(c.isalpha() for c in w) for w in words)
        ):
            guess["first_name"] = words[0]
            guess["last_name"] = " ".join(words[1:])
            break
    return guess


def card_to_source_record(
    image_bytes: bytes,
    origin_file: str | None = None,
    ocr_fn: Callable[[bytes], tuple[str, float]] | None = None,
    llm=None,
) -> SourceRecordIn | None:
    """OCR a card image and produce a normalized source_record. None if OCR yields nothing."""
    if ocr_fn is None:
        from app.pipeline.ocr import run_ocr

        ocr_fn = run_ocr
    text, confidence = ocr_fn(image_bytes)
    if not (text or "").strip():
        return None

    result = extract_fields(text, llm=llm)  # regex (email/phone/url) + LLM (name/title/…)
    mapped = {f: v for f, v in result.model_dump().items() if f in _CARD_FIELDS and v}
    return card_source_record_from_fields(mapped, text, confidence, origin_file)


def read_card(
    image_bytes: bytes,
    origin_file: str | None = None,
    ocr_fn: Callable[[bytes], tuple[str, float]] | None = None,
    llm=None,
) -> dict | None:
    """OCR + extract a card for the review screen (§6): user confirms before it's saved.

    Returns {origin_file, raw_text, confidence, fields}. Heuristic guesses fill any gaps
    the extractor left so the review form is prefilled even with the LLM off. None if OCR
    yields nothing.
    """
    if ocr_fn is None:
        from app.pipeline.ocr import run_ocr

        ocr_fn = run_ocr
    text, confidence = ocr_fn(image_bytes)
    if not (text or "").strip():
        return None
    result = extract_fields(text, llm=llm)
    fields = {f: v for f, v in result.model_dump().items() if f in _CARD_FIELDS and v}
    for k, v in guess_card_fields(text).items():
        fields.setdefault(k, v)
    return {
        "origin_file": origin_file,
        "raw_text": text,
        "confidence": confidence,
        "fields": fields,
    }


def card_source_record_from_fields(
    fields: dict,
    raw_text: str,
    confidence: float | None,
    origin_file: str | None = None,
) -> SourceRecordIn:
    """Build a business_card source_record from confirmed fields (post-review save)."""
    mapped = {f: v for f, v in (fields or {}).items() if f in _CARD_FIELDS and v}
    chash = hashlib.sha256(("business_card\x00" + (raw_text or "")).encode("utf-8")).hexdigest()
    return SourceRecordIn(
        id=str(uuid.uuid4()),
        source=Source.business_card,
        origin_file=origin_file,
        raw_text=raw_text,
        extracted_json=json.dumps(mapped, ensure_ascii=False),
        ocr_confidence=confidence,
        ingested_at=datetime.now(UTC).isoformat(),
        content_hash=chash,
    )
