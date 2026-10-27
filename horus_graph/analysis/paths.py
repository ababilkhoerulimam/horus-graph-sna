"""
Penelusuran rute antara dua entitas.

Biaya tepi = 1/sqrt(bobot artikel), jadi jalur dengan dukungan artikel lebih
besar dianggap lebih "dekat". Rute alternatif dicari dengan menghukum simpul
perantara rute utama, supaya yang muncul benar-benar jalur lain — bukan jalur
yang sama dengan satu simpul ditukar.

Lapisan transmisi (alpha/lead time) belum tersedia di sini: bila bundle tidak
membawa `layers/transmission.parquet`, `has_hawkes` selalu False dan
`product_alpha` selalu None. Nilai nol akan berarti "transmisi terukur nol",
padahal artinya "belum ada data".
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import networkx as nx

from ..core.build import NetworkBundle
from .resolve import resolve_entity

ALTERNATIVE_PENALTY = 6.0


def trace_path(network: NetworkBundle, origin: str, target: str) -> Dict[str, Any]:
    """Rute terkuat beserta alternatifnya; `success=False` dengan alasan kode."""
    src = resolve_entity(network, origin)
    tgt = resolve_entity(network, target)

    if src is None:
        return _failure("origin_not_found", f"Entitas '{origin}' tidak ditemukan")
    if tgt is None:
        return _failure("target_not_found", f"Entitas '{target}' tidak ditemukan")
    if src == tgt:
        return _failure("same_entity", "Sumber dan target harus berbeda")

    graph = _cost_graph(network)
    if not graph.has_node(src) or not graph.has_node(tgt) or not nx.has_path(graph, src, tgt):
        return _failure("no_path", f"Tidak ada jalur antara {src} dan {tgt}")

    primary = nx.shortest_path(graph, source=src, target=tgt, weight="cost")
    alternative = _alternative(graph, primary, src, tgt)
    hops = _hops(network, primary)

    return {
        "success": True,
        "reason": None,
        "path": primary,
        "hops": hops,
        "total_hops": len(hops),
        "total_weight": sum(hop["weight"] for hop in hops),
        "average_npmi": round(sum(hop["npmi"] for hop in hops) / len(hops), 4) if hops else None,
        "critical_broker": primary[1] if len(primary) > 2 else None,
        "alternative_path": alternative,
        "has_hawkes": False,
        "product_alpha": None,
        "total_lead_time_min": None,
    }


def _failure(reason: str, message: str) -> Dict[str, Any]:
    return {
        "success": False,
        "reason": reason,
        "message": message,
        "path": [],
        "hops": [],
        "total_hops": 0,
        "total_weight": 0,
        "average_npmi": None,
        "critical_broker": None,
        "alternative_path": None,
        "has_hawkes": False,
        "product_alpha": None,
        "total_lead_time_min": None,
    }


def _cost_graph(network: NetworkBundle) -> nx.Graph:
    graph = nx.Graph()
    graph.add_nodes_from(network.graph.nodes)
    for u, v, data in network.graph.edges(data=True):
        weight = max(1, int(data.get("weight", 1)))
        graph.add_edge(u, v, cost=1.0 / math.sqrt(weight))
    return graph


def _alternative(
    graph: nx.Graph, primary: List[str], src: str, tgt: str
) -> Optional[List[str]]:
    """Jalur terpendek berikutnya setelah simpul perantara utama dihukum."""
    if len(primary) <= 2:
        return None

    penalized = graph.copy()
    blocked = set(primary[1:-1])
    for u, v, data in penalized.edges(data=True):
        if u in blocked or v in blocked:
            penalized[u][v]["cost"] = data["cost"] * ALTERNATIVE_PENALTY

    try:
        candidate = nx.shortest_path(penalized, source=src, target=tgt, weight="cost")
    except nx.NetworkXNoPath:
        return None
    return candidate if candidate != primary else None


def _hops(network: NetworkBundle, path: List[str]) -> List[Dict[str, Any]]:
    hops = []
    for u, v in zip(path, path[1:]):
        data = network.graph[u][v]
        hops.append(
            {
                "source": u,
                "target": v,
                "edge_category": "cooccurrence",
                "weight": int(data.get("weight", 0)),
                "npmi": round(float(data.get("npmi", 0.0)), 4),
                "rescued": bool(data.get("rescued", False)),
                "alpha": None,
                "lead_time_min": None,
                "is_hawkes": False,
            }
        )
    return hops
