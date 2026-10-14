-- Interaction history (ux-direction / crm-direction). Dated touchpoints per contact —
-- the heart of a relationship CRM. User-authored, keyed by stable contact id, so it
-- SURVIVES rebuilds (rebuild only rewrites the contacts table, never this). Applied idempotently.

CREATE TABLE IF NOT EXISTS interactions (
  id          TEXT PRIMARY KEY,
  contact_id  TEXT NOT NULL,        -- stable contacts.id
  occurred_on TEXT NOT NULL,        -- YYYY-MM-DD
  kind        TEXT NOT NULL,        -- met | call | email | message | note | intro
  note        TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_interactions_contact ON interactions(contact_id, occurred_on);
