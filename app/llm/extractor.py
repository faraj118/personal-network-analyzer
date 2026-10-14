"""LLM-backed extraction (SPEC.md §6, §17). Constrained to extract-from-provided-text.

Turns raw text (e.g. an OCR blob, notably Arabic where spaCy is weak, §16) into a typed
ExtractionResult. The prompt forbids invention; output is treated as a claim, not truth,
so LLM-provided fields get a modest confidence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.llm.client import OllamaClient
from app.models.schemas import ExtractionResult

_PROMPT_PATH = Path(__file__).parent / "prompts" / "extract.txt"
# LLM output is a claim, never ground truth (§16) — kept below deterministic confidence.
_LLM_FIELD_CONFIDENCE = 0.7
_FIELDS = ("first_name", "last_name", "job_title", "company", "email", "phone", "location")


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _parse_json(text: str) -> dict:
    """Extract the first JSON object from a model response (tolerates code fences/prose)."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


class LlmExtractor:
    """Extractor protocol impl backed by a local Ollama model."""

    def __init__(self, client: OllamaClient | None = None) -> None:
        self.client = client or OllamaClient()

    def extract(self, raw_text: str) -> ExtractionResult:
        """Prompt the model and parse a typed result. Raises LlmUnavailable if the LLM is down."""
        prompt = _load_prompt().replace("{text}", raw_text or "")
        raw = self.client.generate(prompt)
        data = _parse_json(raw)

        fields: dict[str, str] = {}
        confidence: dict[str, float] = {}
        for f in _FIELDS:
            v = data.get(f)
            if isinstance(v, str) and v.strip():
                fields[f] = v.strip()
                confidence[f] = _LLM_FIELD_CONFIDENCE
        return ExtractionResult(**fields, confidence=confidence)
