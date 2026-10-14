"""Discovery tests on a known small graph (SPEC.md §8, §13).

Topology: two company triangles (Acme: A,B,E — Globex: C,D,F) linked by a single
shared-location edge B–C (both in Tripoli). B and C are the bridges.
"""

from __future__ import annotations

from app.discovery.graph import build_graph
from app.discovery.metrics import compute_metrics


def _c(cid, first, company, location, seniority):
    return {
        "id": cid,
        "first_name": first,
        "last_name": "X",
        "company": company,
        "location": location,
        "seniority": seniority,
        "industry": "Tech",
        "opportunity": None,
        "importance": 50,
    }


CONTACTS = [
    _c("A", "Amina", "Acme", "Benghazi", "Director"),
    _c("B", "Bilal", "Acme", "Tripoli", "Director"),
    _c("E", "Esra", "Acme", "Benghazi", "Director"),
    _c("C", "Cala", "Globex", "Tripoli", "Manager"),
    _c("D", "Dana", "Globex", "Sabha", "Manager"),
    _c("F", "Fadi", "Globex", "Sabha", "Manager"),
]


def test_graph_nodes_edges_and_weights() -> None:
    g = build_graph(CONTACTS)
    assert g.number_of_nodes() == 6
    assert g.has_edge("B", "C")  # the bridge (shared location Tripoli)
    # A-B share company only (seniority is no longer an edge) -> weight 3.
    assert g["A"]["B"]["weight"] == 3.0
    assert g["A"]["B"]["via"] == ["company"]
    # B-C share only location -> weight 2.
    assert g["B"]["C"]["weight"] == 2.0
    assert g["B"]["C"]["via"] == ["location"]


def test_two_communities_and_bridges() -> None:
    g = build_graph(CONTACTS)
    m = compute_metrics(g, target_industries=["Tech"])
    assert len(m["communities"]) == 2
    top_bridges = {b["id"] for b in m["bridges"][:2]}
    assert top_bridges == {"B", "C"}  # the connectors have highest betweenness


def test_gaps_rollup() -> None:
    g = build_graph(CONTACTS)
    m = compute_metrics(g, target_industries=["Tech"])
    assert m["gaps"]["by_seniority"] == {"Director": 3, "Manager": 3}
    assert m["gaps"]["target_industry_total"] == 6  # all Tech
    assert m["gaps"]["target_industry_senior"] == 3  # the 3 Directors


def test_empty_graph_is_safe() -> None:
    m = compute_metrics(build_graph([]))
    assert m == {"hubs": [], "communities": [], "bridges": [], "gaps": {}, "warm_leads": []}
