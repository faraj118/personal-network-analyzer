-- PNCA initial schema (SPEC.md §4).
-- source_records (immutable, provenance) -> contacts (canonical, rebuildable).
-- Applied idempotently by app/db.py.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source_records (
  id             TEXT PRIMARY KEY,
  source         TEXT NOT NULL,        -- linkedin_export | facebook | business_card
  origin_file    TEXT,
  raw_text       TEXT,                 -- OCR blob / CSV row (JSON) / captured fields (JSON)
  image_path     TEXT,
  extracted_json TEXT,
  ocr_confidence REAL,                 -- cards only
  ingested_at    TEXT NOT NULL,
  content_hash   TEXT NOT NULL         -- idempotency
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_content_hash ON source_records(content_hash);

CREATE TABLE IF NOT EXISTS contacts (
  id               TEXT PRIMARY KEY,
  first_name       TEXT,
  last_name        TEXT,
  job_title        TEXT,
  company          TEXT,
  email            TEXT,
  phone            TEXT,
  location         TEXT,
  industry         TEXT,
  seniority        TEXT,
  opportunity      TEXT,
  importance       INTEGER,            -- 0..100 deterministic
  sources          TEXT,               -- JSON array of source_record ids
  needs_review     INTEGER DEFAULT 0,
  field_provenance TEXT,               -- JSON: which source set each field
  created_at       TEXT,
  updated_at       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone) WHERE phone IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contacts_needs_review ON contacts(needs_review);
