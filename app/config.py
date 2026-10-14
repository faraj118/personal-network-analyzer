"""Config loader — the single source of truth for runtime settings.

Reads ``config/app.yaml``. Nothing in the codebase may hardcode host/port or
asset paths; they come from here so there is one place to change them.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

# Repo root = two levels up from this file (app/config.py -> app/ -> repo root).
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "app.yaml"


class ServerConfig(BaseModel):
    host: str
    port: int


class DatabaseConfig(BaseModel):
    path: str


class PathsConfig(BaseModel):
    rubric: str
    gazetteers: str
    uploads: str


class LlmConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://ollama:11434"
    model: str = "qwen2.5:1.5b"
    timeout_s: float = 60
    max_input_chars: int = 8000
    invoke_on: list[str] = Field(default_factory=lambda: ["arabic", "low_confidence"])


class EnrichmentConfig(BaseModel):
    enabled: bool = False
    free_sources_only: bool = True
    respect_robots: bool = True
    user_agent: str = "PNCA/0.0 (personal contact manager; single-user)"
    min_delay_seconds: float = 5
    max_delay_seconds: float = 15
    stop_on_block: bool = True
    auto_accept_confidence: float = 0.95
    exclude_special_category: bool = True


class AppConfig(BaseModel):
    server: ServerConfig
    database: DatabaseConfig
    paths: PathsConfig
    llm: LlmConfig = Field(default_factory=LlmConfig)
    enrichment: EnrichmentConfig = Field(default_factory=EnrichmentConfig)

    def resolve(self, rel: str) -> Path:
        """Resolve a config-relative path against the repo root (absolute passthrough)."""
        p = Path(rel)
        return p if p.is_absolute() else (REPO_ROOT / p)

    @property
    def db_path(self) -> Path:
        return self.resolve(self.database.path)


@lru_cache(maxsize=1)
def get_config(path: Path | None = None) -> AppConfig:
    """Load and cache the app config. Fails loud if the file is missing/invalid."""
    cfg_path = path or CONFIG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    cfg = AppConfig.model_validate(data)
    # Deployment-context override for the bind host ONLY (Docker needs 0.0.0.0, kept
    # localhost-only by a 127.0.0.1 host port mapping). Port stays sourced from app.yaml.
    host_override = os.environ.get("PNCA_HOST")
    if host_override:
        cfg.server.host = host_override
    # LLM base URL override (container vs bare-metal Ollama).
    llm_url_override = os.environ.get("PNCA_LLM_BASE_URL")
    if llm_url_override:
        cfg.llm.base_url = llm_url_override
    # DB path override (test isolation / alternate data dirs).
    db_override = os.environ.get("PNCA_DB_PATH")
    if db_override:
        cfg.database.path = db_override
    return cfg
