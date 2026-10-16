"""SQLite access + schema application. All DB side-effects live here (SPEC.md §14)."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import REPO_ROOT, get_config

if TYPE_CHECKING:
    from app.enrichment.base import EnrichmentClaim
    from app.models.schemas import SourceRecordIn

# Contact columns an accepted enrichment claim may write into (SPEC.md §18).
_ENRICHABLE_COLUMNS = {
    "first_name",
    "last_name",
    "job_title",
    "company",
    "email",
    "phone",
    "location",
    "industry",
    "seniority",
    "opportunity",
}
# Columns a user may edit via CRM overrides (enrichable + CRM-only fields).
_EDITABLE_COLUMNS = _ENRICHABLE_COLUMNS | {
    "notes",
    "tags",
    "follow_up_date",
    "website",
    "pipeline_stage",
}
# Identity fields that seed a manual contact's source_record (the rest become overrides).
_IDENTITY_FIELDS = {"first_name", "last_name", "job_title", "company", "email", "phone", "location"}
# Fields that affect the deterministic score -> trigger a re-score when edited.
_SCORING_FIELDS = {"seniority", "industry", "location", "opportunity"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with WAL + foreign keys enabled."""
    path = db_path or get_config().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# CRM contact columns added post-0001 (SQLite ALTER ADD COLUMN isn't re-runnable in SQL).
_CRM_COLUMNS = {
    "notes": "TEXT",
    "tags": "TEXT",
    "follow_up_date": "TEXT",
    "website": "TEXT",
    "org_tier": "TEXT",  # company prominence tier (from company_intel / Wikidata)
    "pipeline_stage": "TEXT",  # opportunity pipeline column
}

# Opportunity pipeline stages (ordered, left -> right).
PIPELINE_STAGES = ["Idea", "Talking", "Proposal", "Won", "Lost"]


def _ensure_contact_columns(conn: sqlite3.Connection) -> None:
    """Idempotently add CRM columns to contacts (checks PRAGMA table_info first)."""
    existing = {r[1] for r in conn.execute("PRAGMA table_info(contacts)")}
    for col, coltype in _CRM_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE contacts ADD COLUMN {col} {coltype}")
    conn.commit()


def apply_schema(conn: sqlite3.Connection) -> None:
    """Apply all migration scripts in lexical order. Idempotent (IF NOT EXISTS)."""
    for script in sorted(MIGRATIONS_DIR.glob("*.sql")):
        conn.executescript(script.read_text(encoding="utf-8"))
    _ensure_contact_columns(conn)
    conn.commit()


def init_db(db_path: Path | None = None) -> Path:
    """Create the DB file (if absent) and apply the schema. Returns the DB path."""
    path = db_path or get_config().db_path
    conn = connect(path)
    try:
        apply_schema(conn)
    finally:
        conn.close()
    # SPEC.md §12: DB is single-user, local; restrict to owner-only.
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # non-POSIX filesystem; best effort
    return path


def insert_source_records(conn: sqlite3.Connection, records: list[SourceRecordIn]) -> int:
    """Insert source records idempotently (skip duplicates by content_hash, §11).

    Returns the number of rows actually inserted (new, non-duplicate).
    """
    inserted = 0
    for r in records:
        cur = conn.execute(
            """INSERT OR IGNORE INTO source_records
               (id, source, origin_file, raw_text, image_path, extracted_json,
                ocr_confidence, ingested_at, content_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r.id,
                r.source.value,
                r.origin_file,
                r.raw_text,
                r.image_path,
                r.extracted_json,
                r.ocr_confidence,
                r.ingested_at,
                r.content_hash,
            ),
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted


def fetch_all_source_records(conn: sqlite3.Connection) -> list[dict]:
    """All source records ordered by ingestion time (deterministic rebuild order)."""
    rows = conn.execute("SELECT * FROM source_records ORDER BY ingested_at, id").fetchall()
    return [dict(r) for r in rows]


def rebuild_contacts(conn: sqlite3.Connection) -> int:
    """Rebuild the contacts table from all source_records (SPEC.md §11). Returns count.

    contacts is a derived, always-rebuildable view of source_records — so we clear and
    rebuild deterministically rather than mutate in place.
    """
    # Imported here to avoid a module-level app.pipeline dependency in db.py.
    from app.pipeline.build_contacts import build_contacts

    contacts = build_contacts(fetch_all_source_records(conn))
    conn.execute("DELETE FROM contacts")
    for c in contacts:
        conn.execute(
            """INSERT INTO contacts
               (id, first_name, last_name, job_title, company, email, phone, location,
                industry, seniority, opportunity, importance, sources, needs_review,
                field_provenance, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                c["id"],
                c.get("first_name"),
                c.get("last_name"),
                c.get("job_title"),
                c.get("company"),
                c.get("email"),
                c.get("phone"),
                c.get("location"),
                c.get("industry"),
                c.get("seniority"),
                c.get("opportunity"),
                c.get("importance", 0),
                json.dumps(c.get("sources", [])),
                int(c.get("needs_review", 0)),
                json.dumps(c.get("field_provenance", {})),
                c.get("created_at"),
                c.get("updated_at"),
            ),
        )
    # Re-apply user/enrichment data that lives outside source_records so it SURVIVES rebuild.
    _reapply_accepted_enrichment(conn)
    _apply_overlays(conn)
    _attach_org_tier(conn)
    # Final consistent re-score (reflects org_tier + any overlay changes).
    for row in conn.execute("SELECT id FROM contacts").fetchall():
        _rescore(conn, row["id"])
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]


def _attach_org_tier(conn: sqlite3.Connection) -> None:
    """Set each contact's org_tier from company_intel, matched on the SAME normalization
    used to store company_key (Python str.lower()) — SQLite's lower() is ASCII-only and would
    miss accented company names."""
    intel = {
        r["company_key"]: r["tier"]
        for r in conn.execute("SELECT company_key, tier FROM company_intel")
    }
    if not intel:
        return
    rows = conn.execute(
        "SELECT id, company FROM contacts WHERE company IS NOT NULL AND TRIM(company) != ''"
    ).fetchall()
    for r in rows:
        tier = intel.get((r["company"] or "").strip().lower())
        if tier:
            conn.execute("UPDATE contacts SET org_tier=? WHERE id=?", (tier, r["id"]))


def _reapply_accepted_enrichment(conn: sqlite3.Connection) -> None:
    """Promote accepted enrichment claims into contact columns after a rebuild (§18)."""
    for claim in conn.execute("SELECT * FROM enrichment_records WHERE status='accepted'"):
        _apply_claim_to_contact(conn, dict(claim))


def _rescore(conn: sqlite3.Connection, contact_id: str) -> None:
    """Recompute deterministic importance from the contact's current fields (§6)."""
    from app.pipeline.score import score_contact
    from app.rules import get_rubric

    row = fetch_contact(conn, contact_id)
    if row is not None:
        conn.execute(
            "UPDATE contacts SET importance=? WHERE id=?",
            (score_contact(row, get_rubric()), contact_id),
        )


def _apply_overlays(conn: sqlite3.Connection) -> None:
    """Apply user CRM overlay: soft-deletes suppress contacts; overrides win as corrections."""
    for row in conn.execute("SELECT * FROM contact_overlay").fetchall():
        o = dict(row)
        if o.get("deleted"):
            conn.execute("DELETE FROM contacts WHERE id=?", (o["contact_key"],))
            continue
        overrides = json.loads(o.get("overrides") or "{}")
        touched_score = False
        for field, value in overrides.items():
            if field not in _EDITABLE_COLUMNS:
                continue
            try:
                conn.execute(
                    f"UPDATE contacts SET {field}=?, updated_at=? WHERE id=?",
                    (value, _now_iso(), o["contact_key"]),
                )
            except sqlite3.IntegrityError:
                continue  # e.g. email already used by another contact — skip, don't crash
            touched_score = touched_score or field in _SCORING_FIELDS
        if touched_score:
            _rescore(conn, o["contact_key"])


def fetch_contacts(
    conn: sqlite3.Connection,
    q: str | None = None,
    industry: str | None = None,
    seniority: str | None = None,
    min_score: int | None = None,
    needs_review: bool | None = None,
    tag: str | None = None,
    pipeline_stage: str | None = None,
    location: str | None = None,
    missing: str | None = None,
) -> list[dict]:
    """List contacts with optional filters (SPEC.md §10)."""
    sql = "SELECT * FROM contacts WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (first_name LIKE ? OR last_name LIKE ? OR company LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    if industry:
        sql += " AND industry = ?"
        params.append(industry)
    if seniority:
        sql += " AND seniority = ?"
        params.append(seniority)
    if min_score is not None:
        sql += " AND importance >= ?"
        params.append(min_score)
    if needs_review is not None:
        sql += " AND needs_review = ?"
        params.append(1 if needs_review else 0)
    if tag:
        sql += " AND tags LIKE ?"
        params.append(f"%{tag}%")
    if pipeline_stage:
        sql += " AND pipeline_stage = ?"
        params.append(pipeline_stage)
    if location:
        sql += " AND location LIKE ?"
        params.append(f"%{location}%")
    if missing:
        # Drill-through from Data Health: contacts lacking a given field.
        _missing_cols = {
            "email": "email",
            "company": "company",
            "title": "job_title",
            "industry": "industry",
        }
        if missing == "seniority":
            sql += " AND (seniority IS NULL OR TRIM(seniority) = '' OR seniority = 'Unknown')"
        elif missing in _missing_cols:
            col = _missing_cols[missing]
            sql += f" AND ({col} IS NULL OR TRIM({col}) = '')"
    sql += " ORDER BY importance DESC, last_name"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def save_view(conn: sqlite3.Connection, name: str, params: dict) -> str:
    """Persist a named filter preset. Returns its id."""
    view_id = str(uuid.uuid4())
    clean = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    conn.execute(
        "INSERT INTO saved_views (id, name, params, created_at) VALUES (?, ?, ?, ?)",
        (view_id, name.strip() or "view", json.dumps(clean), _now_iso()),
    )
    conn.commit()
    return view_id


def fetch_views(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM saved_views ORDER BY created_at").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["params"] = json.loads(d["params"])
        except (ValueError, TypeError):
            d["params"] = {}
        out.append(d)
    return out


def delete_view(conn: sqlite3.Connection, view_id: str) -> None:
    conn.execute("DELETE FROM saved_views WHERE id=?", (view_id,))
    conn.commit()


def fetch_contact(conn: sqlite3.Connection, contact_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    return dict(row) if row else None


def fetch_source_kinds(conn: sqlite3.Connection, ids: list[str]) -> dict[str, str]:
    """source_record id -> its source ('linkedin_export', 'business_card', 'manual', ...)."""
    ids = [i for i in ids if isinstance(i, str)]
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT id, source FROM source_records WHERE id IN ({marks})", ids
    ).fetchall()
    return {r["id"]: r["source"] for r in rows}


def data_health_summary(conn: sqlite3.Connection) -> dict:
    """Data quality: missing key fields, flagged-for-review, and dormant-important counts."""
    contacts = fetch_contacts(conn)
    total = len(contacts)
    review = [
        {
            "id": c["id"],
            "name": f"{c.get('first_name') or ''} {c.get('last_name') or ''}".strip(),
            "company": c.get("company"),
        }
        for c in contacts
        if c.get("needs_review")
    ]
    return {
        "total": total,
        "missing_email": sum(1 for c in contacts if not c.get("email")),
        "missing_company": sum(1 for c in contacts if not c.get("company")),
        "missing_title": sum(1 for c in contacts if not c.get("job_title")),
        "unknown_seniority": sum(
            1 for c in contacts if (c.get("seniority") or "Unknown") == "Unknown"
        ),
        "unknown_industry": sum(1 for c in contacts if not c.get("industry")),
        "needs_review": review,
        "stale_important": len(
            reconnect_candidates(conn, days=180, limit=100000, min_importance=30)
        ),
    }


def insights_summary(conn: sqlite3.Connection) -> dict:
    """Strategic rollup: coverage vs targets, distributions, pipeline, data completeness."""
    from collections import Counter

    from app.rules import get_rubric

    contacts = fetch_contacts(conn)
    rubric = get_rubric()
    targets = {t.strip().lower() for t in rubric.get("target_industries", [])}
    senior = {"C-Level", "Director"}
    in_target = [c for c in contacts if (c.get("industry") or "").strip().lower() in targets]
    return {
        "total": len(contacts),
        "by_seniority": dict(Counter(c.get("seniority") or "Unknown" for c in contacts)),
        "by_industry": dict(Counter(c["industry"] for c in contacts if c.get("industry"))),
        "by_prominence": dict(Counter(c["org_tier"] for c in contacts if c.get("org_tier"))),
        "target_total": len(in_target),
        "target_senior": sum(1 for c in in_target if c.get("seniority") in senior),
        "with_email": sum(1 for c in contacts if c.get("email")),
        "with_phone": sum(1 for c in contacts if c.get("phone")),
        "needs_review": sum(1 for c in contacts if c.get("needs_review")),
        "pipeline": {s: len(v) for s, v in pipeline_board(conn).items()},
        "reconnect_due": len(reconnect_candidates(conn, days=90, limit=100000)),
        "target_industries": rubric.get("target_industries", []),
    }


def pipeline_board(conn: sqlite3.Connection) -> dict:
    """Contacts grouped by pipeline stage (Kanban columns), highest priority first."""
    board: dict[str, list[dict]] = {s: [] for s in PIPELINE_STAGES}
    rows = conn.execute("""SELECT * FROM contacts
           WHERE pipeline_stage IS NOT NULL AND TRIM(pipeline_stage) != ''
           ORDER BY importance DESC, last_name""").fetchall()
    for r in rows:
        d = dict(r)
        if d["pipeline_stage"] in board:
            board[d["pipeline_stage"]].append(d)
    return board


def companies_summary(conn: sqlite3.Connection, limit: int = 300) -> list[dict]:
    """Aggregate contacts by company: size, senior count, top priority, prominence tier."""
    rows = conn.execute(
        """SELECT company AS name,
                  COUNT(*) AS contacts,
                  SUM(CASE WHEN seniority IN ('C-Level','Director') THEN 1 ELSE 0 END) AS senior,
                  MAX(importance) AS top_importance,
                  MAX(org_tier) AS org_tier
           FROM contacts
           WHERE company IS NOT NULL AND TRIM(company) != ''
           GROUP BY lower(trim(company))
           ORDER BY contacts DESC, top_importance DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def reconnect_candidates(
    conn: sqlite3.Connection, days: int = 90, limit: int = 10, min_importance: int = 20
) -> list[dict]:
    """Important contacts gone cold: never contacted, or not in `days`. Sorted by priority."""
    cutoff = (datetime.now(UTC).date() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT c.*,
                  (SELECT MAX(occurred_on) FROM interactions i WHERE i.contact_id = c.id) AS last_contact
           FROM contacts c
           WHERE importance >= ?
           ORDER BY importance DESC, last_name""",
        (min_importance,),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        lc = d.get("last_contact")
        if lc is None or lc < cutoff:  # dormant
            out.append(d)
        if len(out) >= limit:
            break
    return out


# --- Enrichment (SPEC.md §18): provenance-first, review-gated ---


def _claim_hash(contact_id: str, field: str, value: str, source_url: str | None) -> str:
    return hashlib.sha256(
        f"{contact_id}\x00{field}\x00{value}\x00{source_url or ''}".encode()
    ).hexdigest()


def insert_enrichment_claims(conn: sqlite3.Connection, claims: list[EnrichmentClaim]) -> int:
    """Persist claims as 'pending' (idempotent by content_hash). Returns rows inserted."""
    inserted = 0
    for c in claims:
        h = _claim_hash(c.contact_id, c.field, c.value, c.source_url)
        cur = conn.execute(
            """INSERT OR IGNORE INTO enrichment_records
               (id, contact_id, field, value, source_url, method, model, confidence,
                fetched_at, content_hash, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (
                str(uuid.uuid4()),
                c.contact_id,
                c.field,
                c.value,
                c.source_url,
                c.method,
                c.model,
                c.confidence,
                _now_iso(),
                h,
            ),
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted


def fetch_pending_enrichment(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM enrichment_records WHERE status='pending' ORDER BY confidence DESC, fetched_at"
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_enrichment(conn: sqlite3.Connection, rec_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM enrichment_records WHERE id=?", (rec_id,)).fetchone()
    return dict(row) if row else None


def _apply_claim_to_contact(conn: sqlite3.Connection, claim: dict) -> bool:
    """Write an accepted claim into its contact column + provenance. Returns applied?"""
    field = claim["field"]
    if field not in _ENRICHABLE_COLUMNS:
        return False  # e.g. bio/profile_url: lives in enrichment_records only, not a column
    row = conn.execute(
        "SELECT field_provenance FROM contacts WHERE id=?", (claim["contact_id"],)
    ).fetchone()
    if row is None:
        return False
    prov = json.loads(row["field_provenance"] or "{}")
    prov[field] = claim.get("source_url") or claim.get("method")
    try:
        conn.execute(
            f"UPDATE contacts SET {field}=?, field_provenance=?, updated_at=? WHERE id=?",
            (claim["value"], json.dumps(prov), _now_iso(), claim["contact_id"]),
        )
    except sqlite3.IntegrityError:
        return False  # e.g. email collides with another contact — don't clobber
    return True


def decide_enrichment(conn: sqlite3.Connection, rec_id: str, accept: bool) -> dict | None:
    """Accept (promote to contact) or reject a pending claim. Returns the updated row."""
    claim = fetch_enrichment(conn, rec_id)
    if claim is None:
        return None
    if accept:
        _apply_claim_to_contact(conn, claim)
        status = "accepted"
    else:
        status = "rejected"
    conn.execute(
        "UPDATE enrichment_records SET status=?, reviewed_at=? WHERE id=?",
        (status, _now_iso(), rec_id),
    )
    conn.commit()
    return fetch_enrichment(conn, rec_id)


def insert_signals(conn: sqlite3.Connection, signals: list[dict]) -> int:
    """Persist opportunity signals idempotently (by content_hash). Returns rows inserted."""
    inserted = 0
    for s in signals:
        h = (
            s.get("content_hash")
            or hashlib.sha256(
                f"{s['contact_id']}\x00{s['kind']}\x00{s['source_url']}".encode()
            ).hexdigest()
        )
        cur = conn.execute(
            """INSERT OR IGNORE INTO signals
               (id, contact_id, kind, summary, source_url, detected_at, confidence, content_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                s["contact_id"],
                s["kind"],
                s["summary"],
                s["source_url"],
                s.get("detected_at") or _now_iso(),
                s.get("confidence", 0.5),
                h,
            ),
        )
        inserted += cur.rowcount
    conn.commit()
    return inserted


def fetch_signals(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM signals ORDER BY detected_at DESC").fetchall()
    return [dict(r) for r in rows]


def fetch_enrichment_for_contact(
    conn: sqlite3.Connection, contact_id: str, status: str | None = None
) -> list[dict]:
    """Enrichment claims for a contact, optionally filtered by status."""
    sql = "SELECT * FROM enrichment_records WHERE contact_id=?"
    params: list = [contact_id]
    if status:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY fetched_at DESC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def fetch_signals_for(conn: sqlite3.Connection, contact_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM signals WHERE contact_id=? ORDER BY detected_at DESC", (contact_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# --- Company intelligence / prominence (scoring-v2-prominence) ---


def distinct_companies(conn: sqlite3.Connection) -> list[str]:
    """Distinct non-empty company names across contacts (for a prominence scan)."""
    rows = conn.execute(
        "SELECT DISTINCT company FROM contacts WHERE company IS NOT NULL AND TRIM(company) != ''"
    ).fetchall()
    return [r[0] for r in rows]


def upsert_company_intel(conn: sqlite3.Connection, company: str, info: dict) -> None:
    """Store a company's prominence record (keyed by normalized name)."""
    key = (company or "").strip().lower()
    if not key:
        return
    conn.execute(
        """INSERT INTO company_intel
           (company_key, label, tier, employees, is_public, qid, source_url, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(company_key) DO UPDATE SET
             label=excluded.label, tier=excluded.tier, employees=excluded.employees,
             is_public=excluded.is_public, qid=excluded.qid, source_url=excluded.source_url,
             fetched_at=excluded.fetched_at""",
        (
            key,
            info.get("label"),
            info.get("tier", "unverified"),
            info.get("employees"),
            1 if info.get("is_public") else 0,
            info.get("qid"),
            info.get("source_url"),
            _now_iso(),
        ),
    )
    conn.commit()


def company_intel_key_exists(conn: sqlite3.Connection, company: str) -> bool:
    key = (company or "").strip().lower()
    return (
        conn.execute("SELECT 1 FROM company_intel WHERE company_key=?", (key,)).fetchone()
        is not None
    )


# --- Interaction history (ux-direction): dated touchpoints; survives rebuilds ---

_INTERACTION_KINDS = {"met", "call", "email", "message", "note", "intro"}


def add_interaction(
    conn: sqlite3.Connection, contact_id: str, occurred_on: str, kind: str, note: str = ""
) -> str | None:
    """Log a touchpoint. Returns the new id, or None if the contact doesn't exist."""
    if fetch_contact(conn, contact_id) is None:
        return None
    kind = kind if kind in _INTERACTION_KINDS else "note"
    rec_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO interactions (id, contact_id, occurred_on, kind, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (rec_id, contact_id, (occurred_on or _now_iso()[:10]), kind, note or None, _now_iso()),
    )
    conn.commit()
    return rec_id


def fetch_interactions(conn: sqlite3.Connection, contact_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM interactions WHERE contact_id=? ORDER BY occurred_on DESC, created_at DESC",
        (contact_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def last_contacted(conn: sqlite3.Connection, contact_id: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(occurred_on) FROM interactions WHERE contact_id=?", (contact_id,)
    ).fetchone()
    return row[0] if row and row[0] else None


# --- CRM overlay (crm-direction): user edits/deletes/adds that survive rebuild ---


def upsert_overlay(
    conn: sqlite3.Connection,
    contact_key: str,
    overrides_delta: dict | None = None,
    deleted: bool | None = None,
) -> None:
    """Merge an override delta / set deleted flag for a contact (persists across rebuild)."""
    row = conn.execute(
        "SELECT overrides, deleted FROM contact_overlay WHERE contact_key=?", (contact_key,)
    ).fetchone()
    overrides = json.loads(row["overrides"]) if row and row["overrides"] else {}
    is_deleted = row["deleted"] if row else 0
    if overrides_delta:
        overrides.update({k: v for k, v in overrides_delta.items() if k in _EDITABLE_COLUMNS})
    if deleted is not None:
        is_deleted = 1 if deleted else 0
    conn.execute(
        """INSERT INTO contact_overlay (contact_key, overrides, deleted, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(contact_key) DO UPDATE SET
             overrides=excluded.overrides, deleted=excluded.deleted, updated_at=excluded.updated_at""",
        (contact_key, json.dumps(overrides), is_deleted, _now_iso()),
    )
    conn.commit()


#: Sentinel a caller sends to explicitly CLEAR a field (distinct from "leave unchanged").
CLEAR = "__clear__"


def edit_contact(conn: sqlite3.Connection, contact_id: str, edits: dict) -> dict | None:
    """Apply user field corrections: record in overlay (survives rebuild) + update live row.

    A value of CLEAR ('__clear__') sets the field to NULL (so opportunity/stage/etc. can be
    un-set, not only changed). Blank/None values are ignored (= leave unchanged).
    """
    edits = {
        k: (None if v == CLEAR else v)
        for k, v in edits.items()
        if k in _EDITABLE_COLUMNS and (v == CLEAR or (v is not None and str(v).strip()))
    }
    if fetch_contact(conn, contact_id) is None:
        return None
    if edits:
        applied = {}
        for field, value in edits.items():
            try:
                conn.execute(
                    f"UPDATE contacts SET {field}=?, updated_at=? WHERE id=?",
                    (value, _now_iso(), contact_id),
                )
            except sqlite3.IntegrityError:
                continue  # e.g. email already used by another contact — skip that field
            applied[field] = value
        if applied:
            upsert_overlay(conn, contact_id, overrides_delta=applied)  # only persist what stuck
        if any(f in _SCORING_FIELDS for f in applied):
            _rescore(conn, contact_id)  # editing seniority/opportunity updates the score
        conn.commit()
    return fetch_contact(conn, contact_id)


def soft_delete_contact(conn: sqlite3.Connection, contact_id: str) -> bool:
    """Mark a contact deleted (suppressed on rebuild) and remove the live row.

    Erasure cascade (SPEC.md §12/§18): also purge the contact's enriched facts,
    signals, and interactions — all personal data keyed by contact_id. Without this
    they orphan in the DB, and because contact ids are stable, re-importing the same
    person would silently re-attach their old data. company_intel is keyed by company
    (shared) so it is intentionally left alone.
    """
    if fetch_contact(conn, contact_id) is None:
        return False
    upsert_overlay(conn, contact_id, deleted=True)
    conn.execute("DELETE FROM contacts WHERE id=?", (contact_id,))
    conn.execute("DELETE FROM enrichment_records WHERE contact_id=?", (contact_id,))
    conn.execute("DELETE FROM signals WHERE contact_id=?", (contact_id,))
    conn.execute("DELETE FROM interactions WHERE contact_id=?", (contact_id,))
    conn.execute("DELETE FROM tasks WHERE contact_id=?", (contact_id,))
    conn.commit()
    return True


def add_manual_contact(conn: sqlite3.Connection, fields: dict) -> str | None:
    """Add a contact as a source_record (source='manual') + rebuild. Returns its stable id."""
    from app.pipeline.build_contacts import _stable_key

    # Identity fields seed the source_record; everything else (seniority, website,
    # opportunity, industry, notes, tags, follow_up_date) becomes a user override.
    mapped = {
        k: str(v).strip() for k, v in fields.items() if k in _IDENTITY_FIELDS and str(v).strip()
    }
    if not mapped:
        return None
    payload = json.dumps(mapped, ensure_ascii=False)
    chash = hashlib.sha256(("manual\x00" + payload).encode()).hexdigest()
    conn.execute(
        """INSERT OR IGNORE INTO source_records
           (id, source, origin_file, raw_text, image_path, extracted_json,
            ocr_confidence, ingested_at, content_hash)
           VALUES (?, 'manual', NULL, ?, NULL, ?, NULL, ?, ?)""",
        (str(uuid.uuid4()), payload, payload, _now_iso(), chash),
    )
    conn.commit()
    rebuild_contacts(conn)
    cid = _stable_key(mapped)
    extras = {
        k: str(v).strip()
        for k, v in fields.items()
        if k in _EDITABLE_COLUMNS and k not in _IDENTITY_FIELDS and str(v).strip()
    }
    if extras:
        edit_contact(conn, cid, extras)  # persists as override + re-scores if needed
    return cid
