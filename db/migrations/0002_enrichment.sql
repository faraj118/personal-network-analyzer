-- PNCA enrichment schema (SPEC.md §4, §18). Provenance-first; never writes contacts directly.
-- Applied idempotently by app/db.py after 0001.

-- One row per enriched fact/claim about a contact. Immutable, fully sourced.
CREATE TABLE IF NOT EXISTS enrichment_records (
  id           TEXT PRIMARY KEY,
  contact_id   TEXT NOT NULL,           -- FK -> contacts.id
  field        TEXT NOT NULL,           -- job_title | company | location | bio | profile_url | ...
  value        TEXT NOT NULL,
  source_url   TEXT,                    -- exact page the claim came from (mandatory for web)
  method       TEXT NOT NULL,           -- rss | web_public | llm_extract
  model        TEXT,                    -- LLM model+version if the LLM was involved
  confidence   REAL NOT NULL,           -- 0..1
  fetched_at   TEXT NOT NULL,
  content_hash TEXT NOT NULL,           -- idempotency (contact_id+field+value+source_url)
  status       TEXT NOT NULL DEFAULT 'pending',  -- pending | accepted | rejected | superseded
  reviewed_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_enrich_hash ON enrichment_records(content_hash);
CREATE INDEX IF NOT EXISTS idx_enrich_contact ON enrichment_records(contact_id);
CREATE INDEX IF NOT EXISTS idx_enrich_status ON enrichment_records(status);

-- Opportunity signals (Tier-1): events about known contacts.
CREATE TABLE IF NOT EXISTS signals (
  id           TEXT PRIMARY KEY,
  contact_id   TEXT NOT NULL,           -- FK -> contacts.id
  kind         TEXT NOT NULL,           -- job_change | funding | promotion | company_news | mention
  summary      TEXT NOT NULL,
  source_url   TEXT NOT NULL,
  detected_at  TEXT NOT NULL,
  confidence   REAL NOT NULL,
  content_hash TEXT NOT NULL,           -- idempotency
  acknowledged INTEGER DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_hash ON signals(content_hash);
CREATE INDEX IF NOT EXISTS idx_signals_contact ON signals(contact_id);
