"""Extraction tests (SPEC.md §6): deterministic regex + LLM fallback (mocked, no Ollama)."""

from __future__ import annotations

from app.llm.extractor import LlmExtractor
from app.pipeline.extract import extract_fields, extract_regex


class FakeClient:
    """Stand-in for OllamaClient: no network. `up` toggles availability."""

    def __init__(self, response: str = "", up: bool = True) -> None:
        self._response = response
        self._up = up

    def available(self) -> bool:
        return self._up

    def generate(self, prompt: str) -> str:
        return self._response


# --- deterministic layer ---


def test_regex_extracts_email_phone_url() -> None:
    text = "Amina Khalil\nCEO, Acme\nemail: amina@acme.com\nTel: +218 91 234 5678\nwww.acme.com"
    fields, conf = extract_regex(text)
    assert fields["email"] == "amina@acme.com"
    assert fields["phone"] == "+218912345678"  # normalized E.164
    assert fields["url"].startswith("www.acme.com")
    assert conf["email"] == 0.95


def test_regex_parses_local_number_with_default_region() -> None:
    fields, _ = extract_regex("Call 091-234-5678", default_region="LY")
    assert fields.get("phone") == "+218912345678"


# --- LLM extractor (mocked) ---


def test_llm_extractor_parses_fenced_json() -> None:
    resp = (
        '```json\n{"first_name":"Ahmed","last_name":"Al-Mansouri",'
        '"job_title":"المدير التنفيذي","company":"Sahara","email":null}\n```'
    )
    res = LlmExtractor(FakeClient(resp)).extract("irrelevant")
    assert res.first_name == "Ahmed"
    assert res.job_title == "المدير التنفيذي"  # Arabic preserved
    assert res.company == "Sahara"
    assert res.email is None  # null field stays null
    assert res.confidence["first_name"] == 0.7


def test_llm_extractor_tolerates_garbage() -> None:
    res = LlmExtractor(FakeClient("sorry, I cannot help")).extract("x")
    assert res.first_name is None and res.company is None


# --- orchestration ---


def test_deterministic_email_wins_over_llm() -> None:
    text = "amina@acme.com"
    llm = FakeClient('{"email":"wrong@evil.com","first_name":"Amina","company":"Acme"}')
    res = extract_fields(text, llm=llm)
    assert res.email == "amina@acme.com"  # regex value kept, not the LLM's
    assert res.first_name == "Amina"  # LLM fills what regex can't
    assert res.company == "Acme"


def test_degrades_without_llm() -> None:
    # LLM down -> deterministic-only, no crash.
    res = extract_fields("reach me at bob@x.io", llm=FakeClient(up=False))
    assert res.email == "bob@x.io"
    assert res.first_name is None
