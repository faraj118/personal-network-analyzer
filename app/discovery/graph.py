"""Build the NetworkX graph from contacts (SPEC.md §8).

Nodes = contacts. Edges = a *real* shared tie: same company (you actually overlapped) or
same location. Seniority tier is deliberately NOT an edge: linking every "Manager" to every
other "Manager" produces a meaningless hairball (measured on real data: 74k noise edges vs
1.1k company edges) that swamps genuine structure. Seniority stays a node attribute (for
gaps/scoring). Edge weights accumulate when a pair shares several ties. 100% local; no LLM.

Note: LinkedIn exports carry no location, so export-only data yields company clusters with
no cross-company links — meaningful *bridges* need location or enriched ties (§16 risk #4).
"""

from __future__ import annotations

from itertools import combinations

import networkx as nx

# Attribute -> edge weight (specificity). Company is the strongest real tie; location next.
# Seniority is intentionally excluded (categorical tier -> giant cliques -> noise).
_ATTR_WEIGHTS = {"company": 3.0, "location": 2.0}
# Values too generic to form a meaningful cluster.
_SKIP_VALUES = {"", "unknown"}


def _norm(v: str | None) -> str:
    return (v or "").strip().lower()


def _display_name(c: dict) -> str:
    return f"{c.get('first_name') or ''} {c.get('last_name') or ''}".strip() or "(unnamed)"


def build_graph(contacts: list[dict]) -> nx.Graph:
    """Return a graph of contacts linked by shared company / location / seniority."""
    g = nx.Graph()
    for c in contacts:
        g.add_node(
            c["id"],
            name=_display_name(c),
            company=c.get("company"),
            location=c.get("location"),
            seniority=c.get("seniority"),
            industry=c.get("industry"),
            opportunity=c.get("opportunity"),
            importance=c.get("importance") or 0,
        )

    for attr, weight in _ATTR_WEIGHTS.items():
        groups: dict[str, list[str]] = {}
        for c in contacts:
            key = _norm(c.get(attr))
            if key in _SKIP_VALUES:
                continue
            groups.setdefault(key, []).append(c["id"])
        for members in groups.values():
            if len(members) < 2:
                continue
            for a, b in combinations(members, 2):
                if g.has_edge(a, b):
                    g[a][b]["weight"] += weight
                    g[a][b]["via"].append(attr)
                else:
                    g.add_edge(a, b, weight=weight, via=[attr])
    return g
