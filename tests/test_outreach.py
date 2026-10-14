"""LLM outreach drafting (assistant). Mocked client — no Ollama needed."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import add_manual_contact, connect, init_db
from app.llm.outreach import build_prompt, draft_outreach
from app.main import app


class FakeClient:
    def __init__(self, response: str = "", up: bool = True) -> None:
        self._r, self._up = response, up

    def available(self) -> bool:
        return self._up

    def generate(self, prompt: str) -> str:
        return self._r


_PROFILE = {
    "contact": {
        "first_name": "Omar",
        "last_name": "Saleh",
        "job_title": "CTO",
        "company": "Globex",
    },
    "last_contact": "2026-01-01",
    "signals": [{"summary": "Globex raised a Series A"}],
}


def test_prompt_includes_context() -> None:
    p = build_prompt(_PROFILE, "congratulate")
    assert "Omar Saleh" in p and "Globex" in p and "Series A" in p
    assert "congratulate" in p.lower()


def test_draft_returns_message_when_llm_up() -> None:
    out = draft_outreach(_PROFILE, "reconnect", client=FakeClient("Hi Omar, it's been a while!"))
    assert out == "Hi Omar, it's been a while!"


def test_draft_returns_none_when_llm_down() -> None:
    assert draft_outreach(_PROFILE, "reconnect", client=FakeClient(up=False)) is None


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "draft.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_api_draft_degrades_without_llm_and_404() -> None:
    client = TestClient(app)
    conn = connect()
    try:
        cid = add_manual_contact(conn, {"first_name": "Z", "last_name": "Q", "company": "Acme"})
    finally:
        conn.close()
    # LLM disabled by default -> graceful null, not a crash.
    r = client.post(f"/contacts/{cid}/draft")
    assert r.status_code == 200
    assert r.json() == {"draft": None, "llm_available": False}
    assert client.post("/contacts/nope/draft").status_code == 404
