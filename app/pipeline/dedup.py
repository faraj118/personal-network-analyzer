"""Entity resolution (SPEC.md §7): exact email/phone auto-merge; fuzzy -> review.

Pure decision function. Returns a decision dict; the caller performs the actual DB merge
(field_provenance + needs_review handling lives with the persistence layer, not here).
"""

from __future__ import annotations

from rapidfuzz import fuzz


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _norm_email(e: str | None) -> str | None:
    return _norm(e) or None


def _norm_phone(p: str | None) -> str | None:
    """Reduce to '+' and digits so differently-formatted E.164 numbers compare equal."""
    if not p:
        return None
    digits = "".join(ch for ch in p if ch.isdigit() or ch == "+")
    return digits or None


def resolve(candidate: dict, existing: list[dict]) -> dict:
    """Decide how a candidate relates to existing contacts (SPEC.md §7).

    Returns {"action": "merge"|"review"|"new", "target_id"?: str, "reason"?: str}.
    Tiers are evaluated in order; the first match wins.
    """
    # Tier 1: exact normalized email -> auto-merge.
    ce = _norm_email(candidate.get("email"))
    if ce:
        for e in existing:
            if _norm_email(e.get("email")) == ce:
                return {"action": "merge", "target_id": e.get("id"), "reason": "email"}

    # Tier 2: exact E.164 phone -> auto-merge.
    cp = _norm_phone(candidate.get("phone"))
    if cp:
        for e in existing:
            if _norm_phone(e.get("phone")) == cp:
                return {"action": "merge", "target_id": e.get("id"), "reason": "phone"}

    # Tier 3: fuzzy — last name exact AND (company token-set > 0.85 OR first name > 0.9)
    # -> review queue, never auto-merge.
    cln, cfn, cco = (
        _norm(candidate.get("last_name")),
        _norm(candidate.get("first_name")),
        _norm(candidate.get("company")),
    )
    if cln:
        for e in existing:
            if _norm(e.get("last_name")) != cln:
                continue
            company_score = (
                fuzz.token_set_ratio(cco, _norm(e.get("company")))
                if cco and e.get("company")
                else 0
            )
            first_score = (
                fuzz.ratio(cfn, _norm(e.get("first_name"))) if cfn and e.get("first_name") else 0
            )
            if company_score > 85 or first_score > 90:
                return {"action": "review", "target_id": e.get("id"), "reason": "fuzzy"}

    # Tier 4: new contact.
    return {"action": "new"}
