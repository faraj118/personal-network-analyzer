"""LLM prep brief (assistant). Mocked client — no Ollama needed."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import add_manual_contact, connect, init_db
from app.llm.brief import build_brief_prompt, prep_brief
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
        "org_tier": "global",
    },
    "last_contact": "2026-02-01",
    "interactions": [{"occurred_on": "2026-02-01", "kind": "call", "note": "demo"}],
    "signals": [{"summary": "Globex raised Series A"}],
}


def test_prompt_has_context() -> None:
    p = build_brief_prompt(_PROFILE)
    assert "Omar Saleh" in p and "Globex" in p and "Series A" in p
    assert "talking points" in p.lower()


def test_brief_up_and_down() -> None:
    assert prep_brief(_PROFILE, client=FakeClient("Brief: ...")) == "Brief: ..."
    assert prep_brief(_PROFILE, client=FakeClient(up=False)) is None


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "brief.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_api_brief_degrades_and_404() -> None:
    client = TestClient(app)
    conn = connect()
    try:
        cid = add_manual_contact(conn, {"first_name": "Z", "company": "Acme"})
    finally:
        conn.close()
    r = client.post(f"/contacts/{cid}/brief")
    assert r.status_code == 200 and r.json() == {"brief": None, "llm_available": False}
    assert client.post("/contacts/nope/brief").status_code == 404
