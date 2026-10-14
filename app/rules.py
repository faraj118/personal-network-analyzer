"""Loaders for rule assets: scoring rubric + classification gazetteers (SPEC.md §6).

Kept separate from app/config.py so the deterministic rule layer has one clear home and
config.py stays focused on runtime settings. Cached; paths come from config (no hardcoding).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.config import get_config


@lru_cache(maxsize=1)
def get_rubric() -> dict:
    """Load config/rubric.yaml (weights, targets, enums, thresholds)."""
    cfg = get_config()
    path = cfg.resolve(cfg.paths.rubric)
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def get_gazetteers() -> dict[str, dict]:
    """Load every *.yaml in config/gazetteers/ keyed by filename stem (titles, industry, ...)."""
    cfg = get_config()
    gdir = cfg.resolve(cfg.paths.gazetteers)
    out: dict[str, dict] = {}
    for f in sorted(Path(gdir).glob("*.yaml")):
        with f.open(encoding="utf-8") as fh:
            out[f.stem] = yaml.safe_load(fh) or {}
    return out
