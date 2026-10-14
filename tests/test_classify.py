"""Rule-classification tests (SPEC.md §6, §13)."""

from __future__ import annotations

from app.models.schemas import ExtractionResult
from app.pipeline.classify import classify


def test_c_level_and_tech() -> None:
    r = classify(ExtractionResult(job_title="Chief Executive Officer", company="Acme Software"))
    assert r["seniority"] == "C-Level"
    assert r["industry"] == "Tech"
    assert r["opportunity"] is None  # never guessed on a card


def test_manager_and_manufacturing() -> None:
    r = classify(ExtractionResult(job_title="Factory Manager", company="Globex Manufacturing"))
    assert r["seniority"] == "Manager"
    assert r["industry"] == "Manufacturing"


def test_unknown_when_no_match() -> None:
    r = classify(ExtractionResult(job_title="Wizard", company="Mystery"))
    assert r["seniority"] == "Unknown"
    assert r["industry"] is None


def test_director_beats_manager_priority() -> None:
    # 'General Manager' -> Director (its gazetteer entry) wins over the Manager bucket.
    r = classify(ExtractionResult(job_title="General Manager", company=""))
    assert r["seniority"] == "Director"


def test_empty_extraction_is_unknown() -> None:
    r = classify(ExtractionResult())
    assert r["seniority"] == "Unknown"
    assert r["industry"] is None


def test_media_production_not_manufacturing() -> None:
    # 'production' keyword removed -> a media/agri "…Production" no longer reads as Manufacturing.
    r = classify(ExtractionResult(job_title="Founder", company="Water Melon Production"))
    assert r["industry"] != "Manufacturing"
    assert r["seniority"] == "C-Level"  # Founder


def test_fintech_is_classified() -> None:
    r = classify(ExtractionResult(job_title="Analyst", company="Sadad Digital Payments"))
    assert r["industry"] == "Fintech"
