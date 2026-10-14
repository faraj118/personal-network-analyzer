"""Type-B metrics (SPEC.md §8): centrality, communities, bridges, gaps, warm leads.

The flagship output is **bridges** — high-betweenness people linking otherwise-separate
clusters, i.e. strategic contacts you can't name from memory. All local, no scraping.
"""

from __future__ import annotations

from collections import Counter

import networkx as nx


def _norm(v: str | None) -> str:
    return (v or "").strip().lower()


def _node_info(g: nx.Graph, node: str, betweenness: dict, degree_raw: dict) -> dict:
    a = g.nodes[node]
    return {
        "id": node,
        "name": a.get("name"),
        "company": a.get("company"),
        "seniority": a.get("seniority"),
        "industry": a.get("industry"),
        "importance": a.get("importance"),
        "degree": degree_raw.get(node, 0),
        "betweenness": round(betweenness.get(node, 0.0), 4),
    }


def _gaps(g: nx.Graph, target_industries: list[str]) -> dict:
    targets = {_norm(t) for t in target_industries}
    by_industry = Counter(g.nodes[n].get("industry") for n in g if g.nodes[n].get("industry"))
    by_seniority = Counter(g.nodes[n].get("seniority") for n in g)
    senior = {"C-Level", "Director"}
    in_target = [n for n in g if _norm(g.nodes[n].get("industry")) in targets]
    return {
        "by_industry": dict(by_industry),
        "by_seniority": dict(by_seniority),
        "target_industry_total": len(in_target),
        "target_industry_senior": sum(
            1 for n in in_target if g.nodes[n].get("seniority") in senior
        ),
    }


def _warm_leads(g: nx.Graph, betweenness: dict, degree_raw: dict) -> list[dict]:
    """Contacts adjacent to a known Client/Partner but not themselves labelled (§8)."""
    anchors = {n for n in g if g.nodes[n].get("opportunity") in ("Client", "Partner")}
    seen: set[str] = set()
    leads: list[dict] = []
    for anchor in anchors:
        for nb in g.neighbors(anchor):
            if nb in anchors or nb in seen:
                continue
            seen.add(nb)
            info = _node_info(g, nb, betweenness, degree_raw)
            info["via"] = g.nodes[anchor].get("name")
            leads.append(info)
    return leads


def compute_metrics(
    g: nx.Graph, top_n: int = 10, target_industries: list[str] | None = None
) -> dict:
    """Return {hubs, communities, bridges, gaps, warm_leads} for the contact graph."""
    empty = {"hubs": [], "communities": [], "bridges": [], "gaps": {}, "warm_leads": []}
    if g.number_of_nodes() == 0:
        return empty

    degree_c = nx.degree_centrality(g)
    degree_raw = dict(g.degree())
    if g.number_of_edges():
        betweenness = nx.betweenness_centrality(g, weight="weight")
        communities = list(nx.community.greedy_modularity_communities(g, weight="weight"))
    else:
        betweenness = {n: 0.0 for n in g}
        communities = [{n} for n in g]

    hubs = sorted(g.nodes, key=lambda n: degree_c[n], reverse=True)[:top_n]
    # Bridges: highest betweenness = the connectors between clusters (§8).
    bridges = [
        n for n in sorted(g.nodes, key=lambda n: betweenness[n], reverse=True) if betweenness[n] > 0
    ][:top_n]

    def info(n: str) -> dict:
        return _node_info(g, n, betweenness, degree_raw)

    return {
        "hubs": [info(n) for n in hubs],
        "communities": [
            {"size": len(c), "members": [info(n) for n in c]}
            for c in sorted(communities, key=len, reverse=True)
        ],
        "bridges": [info(n) for n in bridges],
        "gaps": _gaps(g, target_industries or []),
        "warm_leads": _warm_leads(g, betweenness, degree_raw),
    }
