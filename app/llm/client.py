"""Ollama client wrapper (SPEC.md §17). Local-only, bounded, degrade-if-down.

The deterministic pipeline must keep working if Ollama is unreachable, so every call site
checks ``available()`` or handles ``LlmUnavailable``. Outputs are cached by a hash of
(model, prompt) so re-runs are reproducible and cheap.
"""

from __future__ import annotations

import hashlib

import httpx

from app.config import LlmConfig, get_config


class LlmUnavailable(RuntimeError):
    """Raised when Ollama is disabled or unreachable; callers fall back to rules."""


class OllamaClient:
    def __init__(self, cfg: LlmConfig | None = None) -> None:
        self.cfg = cfg or get_config().llm
        self._cache: dict[str, str] = {}

    def available(self) -> bool:
        """True only if the LLM is enabled AND the server answers. Never raises."""
        if not self.cfg.enabled:
            return False
        try:
            r = httpx.get(f"{self.cfg.base_url}/api/version", timeout=3.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def _key(self, prompt: str) -> str:
        return hashlib.sha256(f"{self.cfg.model}\x00{prompt}".encode()).hexdigest()

    def generate(self, prompt: str) -> str:
        """Single-shot completion. Enforces the input cap; caches by (model, prompt)."""
        if not self.cfg.enabled:
            raise LlmUnavailable("llm.enabled is false")
        prompt = prompt[: self.cfg.max_input_chars]
        key = self._key(prompt)
        if key in self._cache:
            return self._cache[key]
        try:
            resp = httpx.post(
                f"{self.cfg.base_url}/api/generate",
                json={"model": self.cfg.model, "prompt": prompt, "stream": False},
                timeout=self.cfg.timeout_s,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:  # unreachable / timeout / bad status
            raise LlmUnavailable(str(exc)) from exc
        text = resp.json().get("response", "")
        self._cache[key] = text
        return text
