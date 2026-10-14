"""Ask-my-network (assistant): plain-English question -> deterministic contact filters.

The local LLM only *interprets* the question into a filter dict; the actual retrieval is
deterministic (db.fetch_contacts). Degrades to plain text search if the LLM is off — so the
box always works. LLM output is constrained to known filter keys.
"""

from __future__ import annotations

import json
import re

from app.llm.client import LlmUnavailable, OllamaClient

_INDUSTRIES = ["Tech", "Fintech", "Manufacturing", "Oil & Gas", "Finance", "Construction"]
_SENIORITIES = ["C-Level", "Director", "Manager", "Entry"]
_STR_KEYS = ("q", "industry", "seniority", "location", "tag", "pipeline_stage")


def build_ask_prompt(question: str) -> str:
    return (
        "Convert this question about my professional contacts into a JSON filter. Keys (all "
        "optional): q (name/company text), industry (one of "
        f"{_INDUSTRIES}), seniority (one of {_SENIORITIES}), location (city/country), tag, "
        "pipeline_stage, min_score (int). Omit keys you can't infer. Return ONLY the JSON.\n"
        f"Question: {question}"
    )


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def parse_query(question: str, client: OllamaClient | None = None) -> dict:
    """Return a filter dict for fetch_contacts. Falls back to {q: question} if LLM is off."""
    client = client or OllamaClient()
    if not client.available():
        return {"q": question, "_fallback": True}
    try:
        raw = client.generate(build_ask_prompt(question))
    except LlmUnavailable:
        return {"q": question, "_fallback": True}
    data = _parse_json(raw)
    out: dict = {}
    for k in _STR_KEYS:
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    if isinstance(data.get("min_score"), (int, float)):
        out["min_score"] = int(data["min_score"])
    return out or {"q": question}
