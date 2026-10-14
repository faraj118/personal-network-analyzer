"""Business-card OCR pipeline (Phase 1b). OCR injected — no Tesseract needed in CI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.db import init_db
from app.main import app
from app.pipeline.ingest_card import card_to_source_record

_CARD = "Amina Khalil\nChief Executive Officer\nAcme Software\namina@acme.com\n+218 91 234 5678"


def _ocr(text: str, conf: float = 0.9):
    return lambda _bytes: (text, conf)


class _FakeLLM:
    def available(self) -> bool:
        return True

    def generate(self, prompt: str) -> str:
        return '{"first_name":"Amina","last_name":"Khalil","company":"Acme Software"}'


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PNCA_DB_PATH", str(tmp_path / "card.db"))
    get_config.cache_clear()
    init_db()
    yield
    get_config.cache_clear()


def test_card_extracts_email_phone_deterministically() -> None:
    sr = card_to_source_record(b"img", origin_file="c.jpg", ocr_fn=_ocr(_CARD))
    assert sr is not None
    assert sr.source.value == "business_card"
    assert sr.ocr_confidence == 0.9
    data = json.loads(sr.extracted_json)
    assert data["email"] == "amina@acme.com"
    assert data["phone"].startswith("+218")  # normalized E.164


def test_card_llm_fills_name_and_company() -> None:
    sr = card_to_source_record(b"img", ocr_fn=_ocr(_CARD), llm=_FakeLLM())
    data = json.loads(sr.extracted_json)
    assert data["first_name"] == "Amina"
    assert data["company"] == "Acme Software"


def test_empty_ocr_returns_none() -> None:
    assert card_to_source_record(b"img", ocr_fn=_ocr("   ")) is None


def test_ingest_card_endpoint_rejects_non_image() -> None:
    client = TestClient(app)
    r = client.post("/ingest/card", files={"files": ("notes.csv", b"x", "text/csv")})
    assert r.status_code == 415
