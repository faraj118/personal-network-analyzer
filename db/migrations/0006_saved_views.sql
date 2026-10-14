-- Saved views / segments (ux-direction): named filter presets over contacts.
-- User-authored; independent of contacts rebuilds. Applied idempotently.

CREATE TABLE IF NOT EXISTS saved_views (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  params     TEXT NOT NULL,   -- JSON of filter params (q, industry, seniority, tag, ...)
  created_at TEXT NOT NULL
);
