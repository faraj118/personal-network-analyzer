-- PNCA CRM overlay (crm-direction). User-authored data that must SURVIVE contact rebuilds.
-- contacts is derived/rebuilt from source_records (§11); this overlay is re-applied on every
-- rebuild, keyed by the STABLE contact id. Applied idempotently.
--
-- New contact columns (notes/tags/follow_up_date) are added by a Python column-check in
-- app/db.py (SQLite ALTER ADD COLUMN is not re-runnable), not here.

CREATE TABLE IF NOT EXISTS contact_overlay (
  contact_key TEXT PRIMARY KEY,   -- = stable contacts.id
  overrides   TEXT,               -- JSON: {field: value} user corrections (highest priority)
  deleted     INTEGER DEFAULT 0,  -- soft delete: suppressed from rebuilt contacts
  updated_at  TEXT
);
