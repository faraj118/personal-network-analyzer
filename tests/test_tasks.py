"""Tasks / reminders — a Class-2 CRM entity (new table + typed module + UI)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import add_manual_contact, connect, init_db, soft_delete_contact
from app.main import app
from app.models.schemas import Task
from app.tasks import (
    create_task,
    list_tasks,
    open_task_summary,
    set_done,
    tasks_for_contact,
)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "tasks.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_create_list_and_typed_boundary() -> None:
    conn = connect()
    try:
        tid = create_task(conn, "  Send proposal  ", due_date="2030-01-01")
        assert tid
        assert create_task(conn, "   ") is None  # blank title rejected
        tasks = list_tasks(conn, done=False)
        assert len(tasks) == 1
        assert isinstance(tasks[0], Task)  # returns a typed model, not a dict
        assert tasks[0].title == "Send proposal"  # trimmed
    finally:
        conn.close()


def test_complete_reopen_flow_and_ordering() -> None:
    conn = connect()
    try:
        a = create_task(conn, "A", due_date="2030-03-01")
        create_task(conn, "B", due_date="2030-01-01")
        create_task(conn, "C")  # no due date -> sorts last among open
        assert [t.title for t in list_tasks(conn, done=False)] == ["B", "A", "C"]
        assert set_done(conn, a, True) is True
        open_titles = [t.title for t in list_tasks(conn, done=False)]
        done_titles = [t.title for t in list_tasks(conn, done=True)]
        assert "A" not in open_titles and done_titles == ["A"]
        assert set_done(conn, a, False) is True  # reopen
        assert "A" in [t.title for t in list_tasks(conn, done=False)]
    finally:
        conn.close()


def test_contact_link_denormalizes_name() -> None:
    conn = connect()
    try:
        cid = add_manual_contact(conn, {"first_name": "Amina", "last_name": "Khalil"})
        create_task(conn, "Call her", contact_id=cid)
        create_task(conn, "Standalone")
        linked = tasks_for_contact(conn, cid)
        assert [t.title for t in linked] == ["Call her"]
        assert linked[0].contact_name == "Amina Khalil"  # joined at read time
    finally:
        conn.close()


def test_delete_contact_cascades_its_tasks() -> None:
    conn = connect()
    try:
        cid = add_manual_contact(conn, {"first_name": "Erase", "last_name": "Me"})
        create_task(conn, "linked", contact_id=cid)
        create_task(conn, "standalone")
        assert len(tasks_for_contact(conn, cid)) == 1
        soft_delete_contact(conn, cid)
        assert tasks_for_contact(conn, cid) == []  # cascaded
        # the standalone task is untouched
        assert [t.title for t in list_tasks(conn)] == ["standalone"]
    finally:
        conn.close()


def test_open_summary_partitions_overdue_and_soon() -> None:
    conn = connect()
    try:
        create_task(conn, "old", due_date="2000-01-01")
        create_task(conn, "future", due_date="2999-01-01")
        create_task(conn, "no-date")
        s = open_task_summary(conn)
        assert [t.title for t in s["overdue"]] == ["old"]
        assert "future" in [t.title for t in s["due_soon"]]
        assert s["open_count"] == 3
    finally:
        conn.close()


def test_tasks_page_and_ui_round_trip() -> None:
    client = TestClient(app)
    r = client.get("/tasks")
    assert r.status_code == 200 and "No open tasks" in r.text
    client.post("/ui/tasks/add", data={"title": "Buy stamps", "due_date": "2030-02-02"})
    page = client.get("/tasks").text
    assert "Buy stamps" in page
    # it also surfaces on the dashboard Today panel
    assert "Buy stamps" in client.get("/").text
    # nav exposes it
    assert 'href="/tasks"' in page


def test_add_task_from_contact_page_links_it() -> None:
    conn = connect()
    try:
        cid = add_manual_contact(conn, {"first_name": "Omar", "last_name": "Saleh"})
    finally:
        conn.close()
    client = TestClient(app)
    client.post(
        "/ui/tasks/add",
        data={"title": "Follow up with Omar", "contact_id": cid, "next": f"/contact/{cid}"},
    )
    page = client.get(f"/contact/{cid}").text
    assert "Follow up with Omar" in page
