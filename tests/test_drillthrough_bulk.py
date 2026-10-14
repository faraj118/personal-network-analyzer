"""Drill-through filters (Insights/Data-Health) + bulk actions on the list (UX track A)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import add_manual_contact, connect, fetch_contact, init_db
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "dt.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def _seed() -> tuple[str, str]:
    conn = connect()
    try:
        a = add_manual_contact(
            conn,
            {"first_name": "Amina", "last_name": "Khalil", "company": "Acme", "email": "a@acme.ly"},
        )
        b = add_manual_contact(
            conn, {"first_name": "Omar", "last_name": "Saleh"}
        )  # no email/company
    finally:
        conn.close()
    return a, b


def test_missing_email_filter_shows_only_incomplete() -> None:
    a, b = _seed()
    r = TestClient(app).get("/", params={"missing": "email"})
    assert r.status_code == 200
    # the bulk checkbox (value="<id>") renders only in the table, so it isolates the filter
    assert f'value="{b}"' in r.text  # Omar has no email -> in the table
    assert f'value="{a}"' not in r.text  # Amina has an email -> filtered out
    assert "no email" in r.text  # active-filter chip


def test_missing_company_filter() -> None:
    a, b = _seed()
    r = TestClient(app).get("/", params={"missing": "company"})
    assert f'value="{b}"' in r.text and f'value="{a}"' not in r.text


def test_data_health_and_insights_have_drillthrough_links() -> None:
    _seed()
    client = TestClient(app)
    dh = client.get("/data-health").text
    assert 'href="/?missing=email"' in dh
    assert 'href="/?missing=seniority"' in dh
    ins = client.get("/insights").text
    assert "/?seniority=" in ins  # distribution links


def test_bulk_add_tag_and_set_stage() -> None:
    a, b = _seed()
    client = TestClient(app)
    r = client.post(
        "/ui/contacts/bulk",
        data={"ids": [a, b], "action": "add_tag", "tag": "vip"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    conn = connect()
    try:
        assert "vip" in (fetch_contact(conn, a)["tags"] or "")
        assert "vip" in (fetch_contact(conn, b)["tags"] or "")
    finally:
        conn.close()
    client.post("/ui/contacts/bulk", data={"ids": [a], "action": "set_stage", "stage": "Talking"})
    conn = connect()
    try:
        assert fetch_contact(conn, a)["pipeline_stage"] == "Talking"
    finally:
        conn.close()


def test_bulk_set_and_clear_follow_up() -> None:
    a, _ = _seed()
    client = TestClient(app)
    client.post(
        "/ui/contacts/bulk",
        data={"ids": [a], "action": "set_follow_up", "follow_up_date": "2030-01-01"},
    )
    conn = connect()
    try:
        assert fetch_contact(conn, a)["follow_up_date"] == "2030-01-01"
    finally:
        conn.close()
    client.post("/ui/contacts/bulk", data={"ids": [a], "action": "clear_follow_up"})
    conn = connect()
    try:
        assert not fetch_contact(conn, a)["follow_up_date"]
    finally:
        conn.close()


def test_bulk_no_selection_is_safe() -> None:
    _seed()
    r = TestClient(app).post("/ui/contacts/bulk", data={"action": "add_tag", "tag": "x"})
    assert r.status_code in (200, 303)  # redirects with a 'select some' flash, no crash
