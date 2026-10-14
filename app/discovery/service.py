"""Discovery service: load contacts -> graph -> metrics/payloads (SPEC.md §8, §10)."""

from __future__ import annotations

import networkx as nx

from app.db import connect, fetch_contacts
from app.discovery.graph import build_graph
from app.discovery.metrics import compute_metrics
from app.rules import get_rubric

_NODE_ATTRS = ("name", "company", "seniority", "industry", "importance")


def _load_graph() -> nx.Graph:
    conn = connect()
    try:
        contacts = fetch_contacts(conn)
    finally:
        conn.close()
    return build_graph(contacts)


def discovery_payload(top_n: int = 10) -> dict:
    """Metrics: hubs, communities, bridges, gaps, warm leads."""
    targets = get_rubric().get("target_industries", [])
    return compute_metrics(_load_graph(), top_n=top_n, target_industries=targets)


def graph_payload() -> dict:
    """Raw nodes/edges for visualization (SPEC.md §10 GET /graph)."""
    g = _load_graph()
    nodes = [{"id": n, **{k: g.nodes[n].get(k) for k in _NODE_ATTRS}} for n in g]
    edges = [
        {"source": u, "target": v, "weight": d.get("weight"), "via": d.get("via")}
        for u, v, d in g.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edges}
