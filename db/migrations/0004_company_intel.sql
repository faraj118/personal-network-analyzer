-- Company intelligence (scoring-v2-prominence). One row per company (deduped across
-- contacts), populated from Wikidata due-diligence. Feeds the org_tier scoring factor.
-- The contacts.org_tier column is added by app/db.py (_ensure_contact_columns).

CREATE TABLE IF NOT EXISTS company_intel (
  company_key TEXT PRIMARY KEY,   -- normalized (lower/trim) company name
  label       TEXT,               -- Wikidata label
  tier        TEXT NOT NULL,      -- global | established | verified_smb | unverified
  employees   INTEGER,
  is_public   INTEGER,
  qid         TEXT,
  source_url  TEXT,               -- Wikidata entity URL (provenance)
  fetched_at  TEXT NOT NULL
);
