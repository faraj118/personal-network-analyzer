"""Tasks / reminders repository (crm-direction).

A worked example of the recommended structure (see the architecture review): a
feature-scoped module that owns its own SQL and returns **typed** ``Task`` models
rather than raw dicts, instead of piling onto the ``db.py`` god-module. It reuses
only ``connect()``/time helpers from ``app.db``; all task side-effects live here.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, date, datetime

from app.db import connect
from app.models.schemas import Task


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _today() -> date:
    return datetime.now(UTC).date()


def _row_to_task(r: sqlite3.Row) -> Task:
    d = dict(r)
    return Task(
        id=d["id"],
        title=d["title"],
        due_date=d.get("due_date") or None,
        done=bool(d.get("done")),
        contact_id=d.get("contact_id") or None,
        contact_name=(d.get("contact_name") or "").strip() or None,
        notes=d.get("notes") or None,
        created_at=d.get("created_at"),
        completed_at=d.get("completed_at"),
    )


# Read the contact's display name alongside the task in one query (no N+1).
_SELECT = """
    SELECT t.*,
           TRIM(COALESCE(c.first_name,'') || ' ' || COALESCE(c.last_name,'')) AS contact_name
    FROM tasks t
    LEFT JOIN contacts c ON c.id = t.contact_id
"""


def create_task(
    conn: sqlite3.Connection,
    title: str,
    due_date: str | None = None,
    contact_id: str | None = None,
    notes: str | None = None,
) -> str | None:
    """Add a task. Returns its id, or None if the title is blank."""
    title = (title or "").strip()
    if not title:
        return None
    task_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO tasks (id, title, due_date, done, contact_id, notes, created_at)
           VALUES (?, ?, ?, 0, ?, ?, ?)""",
        (
            task_id,
            title,
            (due_date or "").strip() or None,
            (contact_id or "").strip() or None,
            (notes or "").strip() or None,
            _now_iso(),
        ),
    )
    conn.commit()
    return task_id


def get_task(conn: sqlite3.Connection, task_id: str) -> Task | None:
    row = conn.execute(_SELECT + " WHERE t.id = ?", (task_id,)).fetchone()
    return _row_to_task(row) if row else None


def list_tasks(
    conn: sqlite3.Connection, *, done: bool | None = None, contact_id: str | None = None
) -> list[Task]:
    """List tasks, optionally filtered by done state and/or contact.

    Open tasks sort by due date (undated last, then by creation); done tasks show
    most-recently-completed first.
    """
    sql = _SELECT
    where: list[str] = []
    params: list = []
    if done is not None:
        where.append("t.done = ?")
        params.append(1 if done else 0)
    if contact_id:
        where.append("t.contact_id = ?")
        params.append(contact_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    # NULL due dates sort last for open tasks; done tasks by completion desc.
    sql += " ORDER BY t.done, (t.due_date IS NULL), t.due_date, t.completed_at DESC, t.created_at"
    return [_row_to_task(r) for r in conn.execute(sql, params).fetchall()]


def set_done(conn: sqlite3.Connection, task_id: str, done: bool) -> bool:
    """Mark a task done (stamps completed_at) or reopen it (clears it)."""
    if conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is None:
        return False
    conn.execute(
        "UPDATE tasks SET done = ?, completed_at = ? WHERE id = ?",
        (1 if done else 0, _now_iso() if done else None, task_id),
    )
    conn.commit()
    return True


def delete_task(conn: sqlite3.Connection, task_id: str) -> bool:
    cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    return cur.rowcount > 0


def tasks_for_contact(conn: sqlite3.Connection, contact_id: str) -> list[Task]:
    return list_tasks(conn, contact_id=contact_id)


def open_task_summary(conn: sqlite3.Connection, limit: int = 5) -> dict:
    """For the dashboard 'Today' panel: overdue + due-today/soon open tasks + a count."""
    today = _today().isoformat()
    open_tasks = list_tasks(conn, done=False)
    overdue = [t for t in open_tasks if t.due_date and t.due_date < today]
    due_soon = [t for t in open_tasks if t.due_date and t.due_date >= today][:limit]
    return {
        "overdue": overdue[:limit],
        "due_soon": due_soon,
        "open_count": len(open_tasks),
    }


def board_counts(conn: sqlite3.Connection | None = None) -> dict:
    """Small rollup (open/done) — opens its own connection if none is given."""
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute(
            "SELECT SUM(done = 0) AS open, SUM(done = 1) AS done FROM tasks"
        ).fetchone()
        return {"open": row["open"] or 0, "done": row["done"] or 0}
    finally:
        if own:
            conn.close()
