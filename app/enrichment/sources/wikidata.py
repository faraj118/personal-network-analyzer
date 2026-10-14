"""Company prominence via Wikidata (free public API) — due-diligence signal (§18).

Given a company name, resolve a Wikidata entity and derive a DETERMINISTIC prominence tier
from public facts: is it an organization, employee count, publicly traded. No paid brokers;
Wikidata is free and API-friendly. `fetch` is injected so this is fully testable offline.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import quote

import httpx

_API = "https://www.wikidata.org/w/api.php"
_UA = "PNCA/0.0 (personal contact manager; single-user; local app)"
# instance-of (P31) targets that count as an organization/company.
_ORG_QIDS = {
    "Q4830453",  # business
    "Q6881511",  # enterprise
    "Q783794",  # company
    "Q891723",  # public company
    "Q43229",  # organization
    "Q161726",  # multinational corporation
}

Fetch = Callable[[str], dict]


def _http_fetch(url: str) -> dict:
    r = httpx.get(url, headers={"User-Agent": _UA}, timeout=10.0)
    r.raise_for_status()
    return r.json()


def _claim_target_id(claim: dict) -> str | None:
    try:
        return claim["mainsnak"]["datavalue"]["value"]["id"]
    except (KeyError, TypeError):
        return None


def _latest_employee_count(claims: list | None) -> int | None:
    best: int | None = None
    for c in claims or []:
        try:
            amount = int(float(c["mainsnak"]["datavalue"]["value"]["amount"]))
        except (KeyError, TypeError, ValueError):
            continue
        best = amount if best is None else max(best, amount)
    return best


def search_entity(name: str, fetch: Fetch = _http_fetch) -> str | None:
    url = (
        f"{_API}?action=wbsearchentities&search={quote(name)}"
        "&language=en&type=item&format=json&limit=1"
    )
    hits = fetch(url).get("search") or []
    return hits[0]["id"] if hits else None


def get_signals(qid: str, fetch: Fetch = _http_fetch) -> dict:
    url = f"{_API}?action=wbgetentities&ids={qid}&props=claims|labels&languages=en&format=json"
    ent = (fetch(url).get("entities") or {}).get(qid) or {}
    claims = ent.get("claims") or {}
    label = ((ent.get("labels") or {}).get("en") or {}).get("value")
    p31 = [_claim_target_id(c) for c in claims.get("P31", [])]
    return {
        "qid": qid,
        "label": label,
        "is_org": any(q in _ORG_QIDS for q in p31),
        "employees": _latest_employee_count(claims.get("P1128")),
        "is_public": bool(claims.get("P414")),  # stock exchange -> publicly traded
    }


def prominence_tier(sig: dict | None) -> str:
    """Deterministic tier from signals: global / established / verified_smb / unverified."""
    if not sig or not sig.get("is_org"):
        return "unverified"
    emp = sig.get("employees") or 0
    if sig.get("is_public") or emp >= 10000:
        return "global"
    if emp >= 200:
        return "established"
    return "verified_smb"


def lookup_company(name: str, fetch: Fetch = _http_fetch) -> dict:
    """Resolve a company -> {tier, label, qid, employees, is_public, source_url}."""
    if not (name or "").strip():
        return {"tier": "unverified", "label": None, "qid": None, "source_url": None}
    qid = search_entity(name, fetch)
    if not qid:
        return {"tier": "unverified", "label": None, "qid": None, "source_url": None}
    sig = get_signals(qid, fetch)
    return {
        "tier": prominence_tier(sig),
        "label": sig.get("label"),
        "qid": qid,
        "employees": sig.get("employees"),
        "is_public": sig.get("is_public"),
        "source_url": f"https://www.wikidata.org/wiki/{qid}",
    }
