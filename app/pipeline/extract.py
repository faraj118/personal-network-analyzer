"""Field extraction (SPEC.md §6): deterministic-first, LLM fallback.

Deterministic regex/phonenumbers/email-validator handle email/phone/URL with high
reliability. Name/title/company/location come from the local LLM (§17) when it's
enabled — otherwise they're left for the (heavier) spaCy path or manual review (§16).
"""

from __future__ import annotations

import re

import phonenumbers
from email_validator import EmailNotValidError, validate_email

from app.llm.client import LlmUnavailable, OllamaClient
from app.llm.extractor import LlmExtractor
from app.models.schemas import ExtractionResult

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_RE = re.compile(r"(?:https?://|www\.)[^\s]+", re.IGNORECASE)
_DET_CONFIDENCE = 0.95  # regex/phone/email are high-reliability
# Owner's locale (config target_geographies includes Libya) — used to parse local numbers
# written without a country code. Override per call if needed.
_DEFAULT_REGION = "LY"


def extract_regex(raw_text: str, default_region: str = _DEFAULT_REGION) -> tuple[dict, dict]:
    """Deterministic email / phone(E.164) / URL extraction. Returns (fields, confidence)."""
    text = raw_text or ""
    fields: dict[str, str] = {}
    conf: dict[str, float] = {}

    m = _EMAIL_RE.search(text)
    if m:
        try:
            fields["email"] = validate_email(m.group(0), check_deliverability=False).normalized
            conf["email"] = _DET_CONFIDENCE
        except EmailNotValidError:
            pass

    for match in phonenumbers.PhoneNumberMatcher(text, default_region):
        if phonenumbers.is_valid_number(match.number):
            fields["phone"] = phonenumbers.format_number(
                match.number, phonenumbers.PhoneNumberFormat.E164
            )
            conf["phone"] = _DET_CONFIDENCE
            break

    u = _URL_RE.search(text)
    if u:
        fields["url"] = u.group(0)
        conf["url"] = _DET_CONFIDENCE

    return fields, conf


def extract_fields(
    raw_text: str,
    llm: OllamaClient | None = None,
    default_region: str = _DEFAULT_REGION,
) -> ExtractionResult:
    """Extract contact fields: deterministic wins; LLM fills what regex can't (§6)."""
    fields, conf = extract_regex(raw_text, default_region)

    client = llm or OllamaClient()
    if client.available():
        try:
            llm_res = LlmExtractor(client).extract(raw_text)
        except LlmUnavailable:
            llm_res = None
        if llm_res is not None:
            # LLM fills name/title/company/location (deterministic has none of these).
            for f in ("first_name", "last_name", "job_title", "company", "location"):
                v = getattr(llm_res, f)
                if v and not fields.get(f):
                    fields[f] = v
                    conf[f] = llm_res.confidence.get(f, 0.7)
            # Contact details: only fill if regex found none, at lower (unverified) confidence.
            for f in ("email", "phone"):
                v = getattr(llm_res, f)
                if v and not fields.get(f):
                    fields[f] = v
                    conf[f] = 0.6

    return ExtractionResult(**fields, confidence=conf)
