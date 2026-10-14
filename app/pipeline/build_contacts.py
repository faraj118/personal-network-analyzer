"""Build canonical contacts from source_records (SPEC.md §4, §6, §7, §11).

Pure orchestration: source-record dicts in -> canonical contact dicts out. No DB here.
Because contacts are always rebuildable from source_records, this runs over the full set
and dedups as it goes. Deterministic: same source_records -> same contacts.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from app.models.schemas import ExtractionResult
from app.pipeline.classify import classify
from app.pipeline.dedup import resolve
from app.pipeline.score import score_contact
from app.rules import get_gazetteers, get_rubric

# Raw, source-provided fields (mergeable). Derived fields (seniority/industry) are
# RE-CLASSIFIED from these after a merge, never field-copied.
_RAW = ("first_name", "last_name", "job_title", "company", "email", "phone", "location")
_DERIVED = ("industry", "seniority", "opportunity")
_FIELDS = _RAW + _DERIVED


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _candidate(sr: dict, rubric: dict, gazetteers: dict) -> dict:
    """Map one source_record -> a scored, classified contact candidate."""
    data = json.loads(sr.get("extracted_json") or "{}")
    extraction = ExtractionResult(
        first_name=data.get("first_name") or None,
        last_name=data.get("last_name") or None,
        job_title=data.get("job_title") or None,
        company=data.get("company") or None,
        email=data.get("email") or None,
    )
    classified = classify(extraction, gazetteers, rubric)
    sr_id = sr["id"]
    c = {
        "id": str(uuid.uuid4()),
        "first_name": extraction.first_name,
        "last_name": extraction.last_name,
        "job_title": extraction.job_title,
        "company": extraction.company,
        "email": extraction.email,
        "phone": data.get("phone") or None,
        "location": data.get("location") or None,
        "industry": classified["industry"],
        "seniority": classified["seniority"],
        "opportunity": classified["opportunity"],
        "sources": [sr_id],
        "needs_review": 0,
        # provenance: which source_record set each present field
        "field_provenance": {f: sr_id for f in _FIELDS if data.get(f) or classified.get(f)},
    }
    c["importance"] = score_contact(c, rubric)
    return c


def _merge_into(target: dict, cand: dict, rubric: dict, gazetteers: dict) -> None:
    """Merge candidate into target: fill null raw fields; conflict -> keep both + review.

    Derived fields (seniority/industry) are re-classified from the merged raw fields so a
    filled-in title upgrades the classification instead of leaving a stale 'Unknown'.
    """
    for f in _RAW:
        tv, cv = target.get(f), cand.get(f)
        if cv and not tv:
            target[f] = cv
            target["field_provenance"][f] = cand["field_provenance"].get(f)
        elif tv and cv and tv != cv:
            # Conflicting hard fact -> don't silently pick; flag for human review.
            target["needs_review"] = 1
            target["field_provenance"].setdefault("_conflicts", {})[f] = [tv, cv]
    target["sources"].extend(cand["sources"])
    # Re-derive class from merged raw fields, then re-score.
    ext = ExtractionResult(
        first_name=target.get("first_name"),
        last_name=target.get("last_name"),
        job_title=target.get("job_title"),
        company=target.get("company"),
        email=target.get("email"),
    )
    cls = classify(ext, gazetteers, rubric)
    target["seniority"] = cls["seniority"]
    target["industry"] = cls["industry"]
    target["importance"] = score_contact(target, rubric)


def build_contacts(
    source_records: list[dict],
    rubric: dict | None = None,
    gazetteers: dict | None = None,
) -> list[dict]:
    """Return canonical contacts built from all source_records (dedup applied, §7)."""
    rubric = rubric if rubric is not None else get_rubric()
    gazetteers = gazetteers if gazetteers is not None else get_gazetteers()

    built: list[dict] = []
    for sr in source_records:
        cand = _candidate(sr, rubric, gazetteers)
        decision = resolve(cand, built)
        if decision["action"] == "merge":
            target = next(c for c in built if c["id"] == decision["target_id"])
            _merge_into(target, cand, rubric, gazetteers)
        elif decision["action"] == "review":
            # Fuzzy match: never auto-merge (§7). Keep as its own contact, flagged.
            cand["needs_review"] = 1
            cand["field_provenance"]["_review_of"] = decision["target_id"]
            built.append(cand)
        else:
            built.append(cand)
    now = _now()
    for c in built:
        c.setdefault("created_at", now)
        c["updated_at"] = now
    _assign_stable_ids(built)
    return built


def _stable_key(c: dict) -> str:
    """Deterministic identity: email if present, else name+company. Stable across rebuilds."""
    email = (c.get("email") or "").strip().lower()
    if email:
        base = "e:" + email
    else:
        base = "n:" + "|".join(
            (
                (c.get("first_name") or "").strip().lower(),
                (c.get("last_name") or "").strip().lower(),
                (c.get("company") or "").strip().lower(),
            )
        )
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def _assign_stable_ids(built: list[dict]) -> None:
    """Replace temp ids with stable keys so edits/enrichment survive rebuilds (deterministic).

    Collisions (distinct people with no email + identical name+company) get a deterministic
    suffix from the stable build order.
    """
    seen: dict[str, int] = {}
    for c in built:
        key = _stable_key(c)
        if key in seen:
            seen[key] += 1
            key = f"{key}-{seen[key]}"
        else:
            seen[key] = 1
        c["id"] = key
