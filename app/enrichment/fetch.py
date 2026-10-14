"""Polite web fetch (SPEC.md §18). Carries the §9 no-evasion ethic to all HTTP access.

Respect robots.txt, real User-Agent (no spoofing), rate-limit with human-scale jitter, and
STOP on block (401/403/429/CAPTCHA) — never circumvent. Free public sources only.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib import robotparser
from urllib.parse import urlparse

import httpx

from app.config import EnrichmentConfig, get_config

_BLOCK_STATUSES = {401, 403, 429}


class Blocked(RuntimeError):
    """Raised on 401/403/429/CAPTCHA/robots-disallow. Callers stop; they do not retry-evade."""


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    fetched_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


class PoliteFetcher:
    def __init__(self, cfg: EnrichmentConfig | None = None) -> None:
        self.cfg = cfg or get_config().enrichment
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        """robots.txt check (honored when cfg.respect_robots). Unknown robots => allow."""
        if not self.cfg.respect_robots:
            return True
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots:
            rp = robotparser.RobotFileParser()
            rp.set_url(f"{base}/robots.txt")
            try:
                rp.read()
                self._robots[base] = rp
            except OSError:  # robots unreachable (URLError etc.) — don't fabricate a rule
                self._robots[base] = None
        rp = self._robots[base]
        return True if rp is None else rp.can_fetch(self.cfg.user_agent, url)

    def _sleep(self) -> None:
        lo, hi = self.cfg.min_delay_seconds, self.cfg.max_delay_seconds
        if hi > 0:
            time.sleep(random.uniform(lo, hi))  # human-scale jitter

    def get(self, url: str, client: httpx.Client | None = None) -> FetchResult:
        """Rate-limited GET. Raises Blocked on robots-disallow or a block status."""
        if not self.allowed(url):
            raise Blocked(f"robots.txt disallows {url}")
        self._sleep()
        owns = client is None
        client = client or httpx.Client(follow_redirects=True, timeout=15.0)
        try:
            resp = client.get(url, headers={"User-Agent": self.cfg.user_agent})
        finally:
            if owns:
                client.close()
        if self.cfg.stop_on_block and resp.status_code in _BLOCK_STATUSES:
            raise Blocked(f"blocked ({resp.status_code}) at {url} — stopping, not circumventing")
        return FetchResult(url=url, status=resp.status_code, text=resp.text, fetched_at=_now())
