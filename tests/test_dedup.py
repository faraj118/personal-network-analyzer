"""Deduplication tests — all four tiers (SPEC.md §7, §13)."""

from __future__ import annotations

from app.pipeline.dedup import resolve

EXISTING = [
    {
        "id": "1",
        "first_name": "Amina",
        "last_name": "Khalil",
        "company": "Acme Corp",
        "email": "amina@example.com",
        "phone": "+218912345678",
    },
    {"id": "2", "first_name": "Omar", "last_name": "Saleh", "company": "Globex", "phone": None},
]


def test_tier1_exact_email_merges() -> None:
    d = resolve({"email": "AMINA@example.com"}, EXISTING)  # case-insensitive
    assert d == {"action": "merge", "target_id": "1", "reason": "email"}


def test_tier2_phone_merges_across_formatting() -> None:
    d = resolve({"phone": "+218 91 234 5678"}, EXISTING)  # spaces differ, digits match
    assert d["action"] == "merge"
    assert d["target_id"] == "1"
    assert d["reason"] == "phone"


def test_tier3_fuzzy_goes_to_review() -> None:
    # Same last name + near-identical company -> review, never auto-merge.
    d = resolve(
        {"first_name": "Aminah", "last_name": "Khalil", "company": "Acme Corporation"}, EXISTING
    )
    assert d["action"] == "review"
    assert d["target_id"] == "1"


def test_tier4_new_contact() -> None:
    d = resolve({"first_name": "Sara", "last_name": "Nouri", "company": "Umbrella"}, EXISTING)
    assert d == {"action": "new"}


def test_email_takes_priority_over_fuzzy() -> None:
    # Even with a different name, an exact email is a tier-1 auto-merge.
    d = resolve({"first_name": "X", "last_name": "Y", "email": "amina@example.com"}, EXISTING)
    assert d["reason"] == "email"
