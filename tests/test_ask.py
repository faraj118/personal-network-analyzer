"""Ask-my-network: NL -> filters (LLM mocked) + location filter + page fallback."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import add_manual_contact, connect, edit_contact, fetch_contacts, init_db
from app.llm.ask import parse_query
from app.main import app


class _LLM:
    def __init__(self, response: str = "", up: bool = True) -> None:
        self._r, self._up = response, up

    def available(self) -> bool:
        return self._up

    def generate(self, prompt: str) -> str:
        return self._r


def test_parse_keeps_allowed_keys_only() -> None:
    q = parse_query("x", client=_LLM('{"industry":"Fintech","seniority":"Director","junk":"z"}'))
    assert q == {"industry": "Fintech", "seniority": "Director"}


def test_parse_falls_back_when_llm_off() -> None:
    assert parse_query("who in fintech", client=_LLM(up=False)) == {
        "q": "who in fintech",
        "_fallback": True,
    }


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "ask.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_location_filter() -> None:
    conn = connect()
    try:
        a = add_manual_contact(conn, {"first_name": "Amina", "last_name": "K", "company": "Acme"})
        edit_contact(conn, a, {"location": "Tripoli, Libya"})
        add_manual_contact(conn, {"first_name": "Omar", "last_name": "S", "company": "Globex"})
        assert [c["id"] for c in fetch_contacts(conn, location="Tripoli")] == [a]
    finally:
        conn.close()


def test_ask_page_fallback_search() -> None:
    conn = connect()
    try:
        add_manual_contact(conn, {"first_name": "Amina", "last_name": "K", "company": "Acme"})
    finally:
        conn.close()
    # LLM off by default -> fallback plain search on the question text.
    r = TestClient(app).get("/ask", params={"question": "Amina"})
    assert r.status_code == 200
    assert "Amina" in r.text and "plain text search" in r.text
