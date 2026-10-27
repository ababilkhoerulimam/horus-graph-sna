"""
Penelusuran rute antara dua entitas.

Dua graf dipakai, dan pemilihannya bukan preferensi gaya:

  - `wire` (terarah, media -> media) bila lapisan transmisi tersedia. Di sini
    alpha Hawkes dan lead time benar-benar berarti, dan arah panahnya nyata.
  - ko-okurensi (tak berarah) untuk sisanya. Biaya tepi = 1/sqrt(bobot artikel),
    jadi jalur dengan dukungan artikel lebih besar dianggap lebih dekat.

Rute alternatif dicari dengan menghukum simpul perantara rute utama, supaya
yang muncul benar-benar jalur lain — bukan jalur yang sama dengan satu simpul
ditukar.

Tanpa lapisan transmisi, `has_hawkes` selalu False dan `product_alpha` selalu
`None`; nol akan berarti "transmisi terukur nol", padahal artinya belum ada
data.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import networkx as nx

from ..core.build import NetworkBundle
from .resolve import resolve_entity

ALTERNATIVE_PENALTY = 6.0
MIN_ALPHA = 0.01


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

    wire = network.transmission.graph if network.transmission else None
    if wire is not None and src in wire and tgt in wire:
        response = _trace_wire(wire, src, tgt)
        if response is not None:
            return response

    graph = _cost_graph(network)
    if not graph.has_node(src) or not graph.has_node(tgt) or not nx.has_path(graph, src, tgt):
        if wire is not None:
            bridged = _trace_wire_bridge(network, wire, src, tgt, graph)
            if bridged is not None:
                return bridged
        return _failure("no_path", f"Tidak ada jalur antara {src} dan {tgt}")

    primary = nx.shortest_path(graph, source=src, target=tgt, weight="cost")
    alternative = _alternative(graph, primary, src, tgt)
    hops = _hops(network, primary)

    return {
        "success": True,
        "reason": None,
        "route": "cooccurrence",
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
        "route": None,
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


def _trace_wire(wire: nx.DiGraph, src: str, tgt: str) -> Optional[Dict[str, Any]]:
    """Rute media -> media pada graf transmisi terarah."""
    if not nx.has_path(wire, src, tgt):
        return None

    def cost(u: str, v: str, data: Dict[str, Any]) -> float:
        return 1.0 / max(MIN_ALPHA, float(data.get("alpha") or 0.0))

    path = nx.shortest_path(wire, src, tgt, weight=cost)
    hops = [_wire_hop(wire, u, v) for u, v in zip(path, path[1:])]

    return _wire_response(
        path=path,
        hops=hops,
        route="wire",
        critical_broker=path[1] if len(path) > 2 else None,
        alternative=None,
        total_weight=sum(hop["weight"] for hop in hops),
        average_npmi=None,
    )


def _trace_wire_bridge(
    network: NetworkBundle, wire: nx.DiGraph, src: str, tgt: str, cooc: nx.Graph
) -> Optional[Dict[str, Any]]:
    """
    Sambungkan media ke entitas lewat satu hop kawat, lalu ko-okurensi.

    Hanya dipakai bila jalur ko-okurensi murni tidak ada, sehingga rute yang
    sudah terbukti tidak berubah hanya karena lapisan transmisi muncul.
    """
    if src not in wire or not cooc.has_node(tgt):
        return None

    best: Optional[tuple[float, str]] = None
    for _, mid, data in wire.out_edges(src, data=True):
        if not cooc.has_node(mid) or not nx.has_path(cooc, mid, tgt):
            continue
        alpha = float(data.get("alpha") or 0.0)
        if best is None or alpha > best[0]:
            best = (alpha, mid)

    if best is None:
        return None

    _, mid = best
    tail = nx.shortest_path(cooc, mid, tgt, weight="cost")
    path = [src, mid] + tail[1:]
    hops = [_wire_hop(wire, src, mid)] + _hops(network, tail)

    return _wire_response(
        path=path,
        hops=hops,
        route="wire_bridge",
        critical_broker=mid,
        alternative=None,
        total_weight=sum(hop["weight"] for hop in hops),
        average_npmi=round(
            sum(hop["npmi"] for hop in hops if hop["npmi"] is not None)
            / max(1, sum(1 for hop in hops if hop["npmi"] is not None)),
            4,
        ),
    )


def _wire_hop(wire: nx.DiGraph, u: str, v: str) -> Dict[str, Any]:
    data = wire[u][v]
    return {
        "source": u,
        "target": v,
        "edge_category": "transmission",
        "weight": int(data.get("n_events") or 0),
        "npmi": None,
        "rescued": False,
        "alpha": float(data["alpha"]),
        "lead_time_min": float(data["lead_time_min"]),
        "is_hawkes": True,
    }


def _wire_response(
    *,
    path: List[str],
    hops: List[Dict[str, Any]],
    route: str,
    critical_broker: Optional[str],
    alternative: Optional[List[str]],
    total_weight: int,
    average_npmi: Optional[float],
) -> Dict[str, Any]:
    hawkes = [hop for hop in hops if hop["is_hawkes"]]
    product_alpha = None
    total_lead = None
    if hawkes:
        product_alpha = 1.0
        for hop in hawkes:
            product_alpha *= float(hop["alpha"])
        product_alpha = round(product_alpha, 5)
        total_lead = round(sum(float(hop["lead_time_min"]) for hop in hawkes), 1)

    return {
        "success": True,
        "reason": None,
        "route": route,
        "path": path,
        "hops": hops,
        "total_hops": len(hops),
        "total_weight": total_weight,
        "average_npmi": average_npmi,
        "critical_broker": critical_broker,
        "alternative_path": alternative,
        "has_hawkes": bool(hawkes),
        "product_alpha": product_alpha,
        "total_lead_time_min": total_lead,
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
