"""Deterministic scoring (SPEC.md §6). Pure function: same input -> same score.

importance = min(100, Σ matched weights) from rubric.yaml. No model, no side effects.
"""

from __future__ import annotations


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _geo_terms(rubric: dict) -> set[str]:
    """Target geographies + their city/country aliases (only for active targets)."""
    geos = [_norm(x) for x in rubric.get("target_geographies", [])]
    terms = set(geos)
    for target, aliases in (rubric.get("geo_aliases") or {}).items():
        if _norm(target) in geos:
            terms.update(_norm(a) for a in (aliases or []))
    return terms


def score_breakdown(contact: dict, rubric: dict) -> dict:
    """Explainable score: the components that make up importance, plus the capped total.

    Returns {total, raw, capped, components:[{factor, detail, points}]}. This is the single
    source of truth; ``score_contact`` just returns its total, so they never diverge.
    """
    w = rubric["weights"]
    comps: list[dict] = []

    # Seniority — Unknown is an explicit, weighted bucket.
    seniority = contact.get("seniority") or "Unknown"
    comps.append(
        {
            "factor": "Seniority",
            "detail": seniority,
            "points": w["seniority"].get(seniority, w["seniority"].get("Unknown", 0)),
        }
    )

    # Industry — target vs other.
    industry = contact.get("industry")
    ind_norm = _norm(industry)
    targets = [_norm(x) for x in rubric.get("target_industries", [])]
    if ind_norm and ind_norm in targets:
        comps.append(
            {
                "factor": "Industry",
                "detail": f"{industry} (target)",
                "points": w["industry"]["target_match"],
            }
        )
    elif ind_norm:
        comps.append({"factor": "Industry", "detail": industry, "points": w["industry"]["other"]})
    else:
        comps.append({"factor": "Industry", "detail": "unknown", "points": 0})

    # Location — target geography appears anywhere in the location string.
    loc_raw = contact.get("location")
    loc = _norm(loc_raw)
    geo_terms = _geo_terms(rubric)  # includes city aliases (Tripoli -> Libya)
    if loc and any(g in loc for g in geo_terms):
        comps.append(
            {
                "factor": "Location",
                "detail": f"{loc_raw} (target)",
                "points": w["location"]["target_geo"],
            }
        )
    elif loc:
        comps.append({"factor": "Location", "detail": loc_raw, "points": w["location"]["other"]})
    else:
        comps.append({"factor": "Location", "detail": "unknown", "points": 0})

    # Opportunity — only when set (assigned deliberately, not guessed).
    opp = contact.get("opportunity")
    if opp:
        comps.append(
            {
                "factor": "Opportunity",
                "detail": opp,
                "points": w["opportunity"].get(opp, w["opportunity"].get("Other", 0)),
            }
        )

    # Organization prominence — from Wikidata due-diligence (only when the tier is known).
    org_tier = _norm(contact.get("org_tier"))
    prom = w.get("prominence", {})
    if org_tier and org_tier in prom:
        comps.append({"factor": "Organization", "detail": org_tier, "points": prom[org_tier]})

    # Personal relevance — contact's title/company/industry mentions one of the owner's foci.
    rel_pts = w.get("relevance", {}).get("match", 0)
    if rel_pts:
        text = " ".join(_norm(contact.get(f)) for f in ("job_title", "company", "industry"))
        matched = next((k for k in rubric.get("relevance_keywords", []) if _norm(k) in text), None)
        if matched:
            comps.append(
                {"factor": "Relevance", "detail": f"matches '{matched}'", "points": rel_pts}
            )

    raw = sum(c["points"] for c in comps)
    return {"total": min(100, raw), "raw": raw, "capped": raw > 100, "components": comps}


def score_contact(contact: dict, rubric: dict) -> int:
    """importance = min(100, Σ matched weights). Same input -> same score."""
    return score_breakdown(contact, rubric)["total"]
