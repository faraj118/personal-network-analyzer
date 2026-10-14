-- Tasks / reminders (crm-direction). A first-class Class-2 entity: user-authored to-dos
-- that may stand alone OR link to a contact (one contact -> many tasks). Like interactions,
-- keyed by the STABLE contact id with no enforced FK (contacts are rebuilt; this table is
-- not), so tasks SURVIVE rebuilds. Applied idempotently.

CREATE TABLE IF NOT EXISTS tasks (
  id           TEXT PRIMARY KEY,
  title        TEXT NOT NULL,
  due_date     TEXT,                 -- YYYY-MM-DD, optional
  done         INTEGER NOT NULL DEFAULT 0,
  contact_id   TEXT,                 -- optional link to a stable contacts.id
  notes        TEXT,
  created_at   TEXT NOT NULL,
  completed_at TEXT                  -- set when marked done
);
CREATE INDEX IF NOT EXISTS idx_tasks_open ON tasks(done, due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_contact ON tasks(contact_id);
