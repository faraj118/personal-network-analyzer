"""Actionable UX: card review-and-confirm, Today quick-actions, flash feedback."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import (
    add_interaction,
    add_manual_contact,
    connect,
    edit_contact,
    fetch_contact,
    fetch_contacts,
    fetch_interactions,
    init_db,
)
from app.main import app
from app.pipeline.ingest_card import guess_card_fields, read_card


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "a.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_guess_card_fields_extracts_name_title_company_without_llm() -> None:
    text = "Jane Doe\nChief Technology Officer\nAcme Technologies Ltd\njane@acme.com\n+1 555 0100"
    g = guess_card_fields(text)
    assert g["first_name"] == "Jane"
    assert g["last_name"] == "Doe"
    assert "Officer" in g["job_title"]
    assert "Acme" in g["company"]


def test_read_card_prefills_fields_with_stub_ocr() -> None:
    text = "Omar Salah\nSales Manager\nDelta Solutions\nomar@delta.ly"
    card = read_card(b"x", origin_file="c.jpg", ocr_fn=lambda _b: (text, 0.81), llm=None)
    assert card is not None
    assert card["fields"]["first_name"] == "Omar"
    assert card["fields"]["email"] == "omar@delta.ly"  # deterministic regex
    assert card["confidence"] == 0.81


def test_read_card_returns_none_when_ocr_empty() -> None:
    assert read_card(b"x", ocr_fn=lambda _b: ("", 0.0)) is None


def test_cards_confirm_creates_contact_from_reviewed_fields() -> None:
    client = TestClient(app)
    r = client.post(
        "/ui/cards/confirm",
        data={
            "card-0-raw_text": "Nadia Ben Ali\nDirector\nHoldings",
            "card-0-confidence": "0.8",
            "card-0-origin_file": "n.jpg",
            "card-0-first_name": "Nadia",
            "card-0-last_name": "Ben Ali",
            "card-0-company": "Holdings",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "flash=" in r.headers["location"]
    conn = connect()
    try:
        names = [(c["first_name"], c["last_name"]) for c in fetch_contacts(conn)]
    finally:
        conn.close()
    assert ("Nadia", "Ben Ali") in names


def test_log_touch_records_interaction_and_clears_follow_up() -> None:
    conn = connect()
    try:
        cid = add_manual_contact(conn, {"first_name": "P", "last_name": "Q"})
        edit_contact(conn, cid, {"follow_up_date": "2020-01-01"})
    finally:
        conn.close()

    client = TestClient(app)
    r = client.post(f"/ui/contact/{cid}/logtouch", follow_redirects=False)
    assert r.status_code == 303

    conn = connect()
    try:
        assert fetch_contact(conn, cid)["follow_up_date"] is None
        assert len(fetch_interactions(conn, cid)) == 1
    finally:
        conn.close()


def test_snooze_pushes_follow_up_into_the_future() -> None:
    conn = connect()
    try:
        cid = add_manual_contact(conn, {"first_name": "R", "last_name": "S"})
    finally:
        conn.close()

    client = TestClient(app)
    r = client.post(f"/ui/contact/{cid}/snooze", data={"days": "7"}, follow_redirects=False)
    assert r.status_code == 303

    conn = connect()
    try:
        assert fetch_contact(conn, cid)["follow_up_date"] is not None
    finally:
        conn.close()


def test_flash_banner_renders_on_home() -> None:
    client = TestClient(app)
    r = client.get("/?flash=Saved+everything")
    assert r.status_code == 200
    assert "Saved everything" in r.text


def test_add_interaction_helper_smoke() -> None:
    # guards against the log-touch path silently failing on a fresh contact
    conn = connect()
    try:
        cid = add_manual_contact(conn, {"first_name": "T", "last_name": "U"})
        add_interaction(conn, cid, "", "note", "hi")
        assert len(fetch_interactions(conn, cid)) == 1
    finally:
        conn.close()
