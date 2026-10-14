"""Rule-dictionary classification (SPEC.md §6). Unknown, never guessed.

Deterministic keyword matching against the gazetteers. No LLM here — the LLM (§17) may
later *suggest* a class for ambiguous cases, but that path is review-gated and separate.
"""

from __future__ import annotations

import re

from app.models.schemas import ExtractionResult
from app.rules import get_gazetteers, get_rubric


def _match_gazetteer(text: str | None, gaz: dict) -> str | None:
    """Return the first label whose keyword matches text on WORD boundaries.

    Word boundaries (not substring) are essential: substring matching makes short keywords
    like 'cto' match 'faCTOry' or 'ai' match 'emAIl'. Dict order = priority.
    """
    t = (text or "").lower()
    if not t:
        return None
    for label, keywords in gaz.items():
        for kw in keywords or []:
            if re.search(rf"\b{re.escape(str(kw).lower())}\b", t):
                return label
    return None


def classify(
    extraction: ExtractionResult,
    gazetteers: dict[str, dict] | None = None,
    rubric: dict | None = None,
) -> dict:
    """Map an extraction to {seniority, industry, opportunity} using closed enums.

    seniority -> titles gazetteer (then seniority gazetteer fallback), else 'Unknown'.
    industry  -> industry gazetteer over company+title text, else None (no points).
    opportunity -> None: no reliable signal on a card; assigned deliberately by the user.
    """
    gazetteers = gazetteers if gazetteers is not None else get_gazetteers()
    _ = rubric if rubric is not None else get_rubric()  # reserved for future enum validation

    titles = gazetteers.get("titles", {})
    industries = gazetteers.get("industry", {})
    seniority_gaz = gazetteers.get("seniority", {})

    seniority = (
        _match_gazetteer(extraction.job_title, titles)
        or _match_gazetteer(extraction.job_title, seniority_gaz)
        or "Unknown"
    )

    industry_text = f"{extraction.company or ''} {extraction.job_title or ''}"
    industry = _match_gazetteer(industry_text, industries)

    return {"seniority": seniority, "industry": industry, "opportunity": None}
