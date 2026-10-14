"""Deterministic scorer tests (SPEC.md §6, §13)."""

from __future__ import annotations

from app.pipeline.score import score_breakdown, score_contact
from app.rules import get_rubric

RUBRIC = get_rubric()


def test_top_tier_maxes_out() -> None:
    c = {
        "seniority": "C-Level",
        "industry": "Tech",
        "location": "Tripoli, Libya",
        "opportunity": "Client",
    }
    # 40 + 30 + 20 + 10 = 100
    assert score_contact(c, RUBRIC) == 100


def test_unknown_everything_scores_only_unknown_seniority() -> None:
    c = {"seniority": "Unknown", "industry": None, "location": None, "opportunity": None}
    assert score_contact(c, RUBRIC) == 8  # Unknown seniority weight


def test_non_target_industry_and_geo_use_other_weights() -> None:
    c = {
        "seniority": "Manager",
        "industry": "Retail",
        "location": "Cairo",
        "opportunity": "Partner",
    }
    # 15 + 3 (industry other) + 5 (location other) + 8 = 31
    assert score_contact(c, RUBRIC) == 31


def test_score_is_deterministic() -> None:
    c = {
        "seniority": "Director",
        "industry": "Manufacturing",
        "location": "GCC",
        "opportunity": "Supplier",
    }
    assert score_contact(c, RUBRIC) == score_contact(dict(c), RUBRIC)


def test_score_capped_at_100() -> None:
    c = {"seniority": "C-Level", "industry": "Tech", "location": "Libya", "opportunity": "Client"}
    assert score_contact(c, RUBRIC) <= 100


def test_missing_seniority_defaults_to_unknown_weight() -> None:
    assert score_contact({}, RUBRIC) == 8


def test_breakdown_explains_and_matches_total() -> None:
    c = {
        "seniority": "C-Level",
        "industry": "Fintech",
        "location": "Tripoli, Libya",
        "opportunity": "Client",
    }
    b = score_breakdown(c, RUBRIC)
    assert b["total"] == score_contact(c, RUBRIC)  # single source of truth
    assert sum(comp["points"] for comp in b["components"]) == b["raw"]
    factors = {comp["factor"] for comp in b["components"]}
    assert {"Seniority", "Industry", "Location", "Opportunity"} <= factors
    # Fintech is now a target industry -> target_match points
    ind = next(comp for comp in b["components"] if comp["factor"] == "Industry")
    assert ind["points"] == RUBRIC["weights"]["industry"]["target_match"]


def test_personal_relevance_boost() -> None:
    # A contact in the owner's field (payments/strategy) gets a Relevance component.
    rel = score_breakdown(
        {"seniority": "Director", "job_title": "Fintech Strategy Director"}, RUBRIC
    )
    comp = next((c for c in rel["components"] if c["factor"] == "Relevance"), None)
    assert comp is not None and comp["points"] == RUBRIC["weights"]["relevance"]["match"]
    # An unrelated contact gets no Relevance component.
    plain = score_breakdown(
        {"seniority": "Director", "job_title": "Plumber", "company": "Pipes Co"}, RUBRIC
    )
    assert all(c["factor"] != "Relevance" for c in plain["components"])


def test_geo_alias_credits_target_geography() -> None:
    # "Tripoli" is a Libya alias -> target_geo points (not 'other').
    b = score_breakdown({"seniority": "Manager", "location": "Tripoli"}, RUBRIC)
    loc = next(comp for comp in b["components"] if comp["factor"] == "Location")
    assert loc["points"] == RUBRIC["weights"]["location"]["target_geo"]
    assert "(target)" in loc["detail"]
