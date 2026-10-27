"""
Simulasi kontrafaktual: apa yang berubah bila satu simpul hilang.

Yang dilaporkan hanya selisih yang bisa dihitung ulang dari graf: densitas,
beban perantara yang berpindah, dan simpul yang jadi terisolasi. Dampak
sentimen tetap `None` selama lapisan sentimen belum ada, bukan 0.0.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..core import metrics
from ..core.build import NetworkBundle
from .resolve import resolve_entity

ABSORBING_LIMIT = 5


def simulate_removal(network: NetworkBundle, target: str) -> Dict[str, Any]:
    """Hapus satu simpul di salinan graf dan ukur pergeseran topologi."""
    entity_id = resolve_entity(network, target)
    if entity_id is None:
        return _failure("not_found", f"Simpul '{target}' tidak ditemukan di katalog", network)

    if entity_id == network.domain.ego_id:
        return _failure(
            "ego_protected",
            f"Simpul ego '{entity_id}' tidak dapat dihapus dalam simulasi",
            network,
        )

    base = network.graph
    base_nodes = base.number_of_nodes()
    base_edges = base.number_of_edges()
    base_density = metrics.density(base_edges, base_nodes)
    base_betweenness = metrics.betweenness(base)

    incident = list(base.edges(entity_id))

    simulated = base.copy()
    simulated.remove_node(entity_id)

    post_nodes = simulated.number_of_nodes()
    post_edges = simulated.number_of_edges()
    post_density = metrics.density(post_edges, post_nodes)
    post_betweenness = metrics.betweenness(simulated)

    return {
        "success": True,
        "reason": None,
        "removed": {
            "id": entity_id,
            "label": network.label_of(entity_id),
            "entity_type": network.type_of(entity_id),
        },
        "baseline": {"nodes": base_nodes, "edges": base_edges, "density": base_density},
        "post": {"nodes": post_nodes, "edges": post_edges, "density": post_density},
        "delta_density": round(post_density - base_density, 5),
        "lost_edges": len(incident),
        "absorbing_brokers": _absorbing(
            network, base_betweenness, post_betweenness
        ),
        "isolated_nodes": sorted(
            node for node, degree in simulated.degree() if degree == 0
        ),
        "severed_causal_routes": (
            0 if network.transmission is None else network.transmission.severed_routes(entity_id)
        ),
        "lost_sentiment_impact": _lost_sentiment(network, entity_id),
    }


def _lost_sentiment(network: NetworkBundle, entity_id: str) -> Optional[float]:
    """Stance simpul yang hilang; `None` bila sentimennya belum terverifikasi."""
    if network.sentiment is None:
        return None
    record = network.sentiment.scores.get(entity_id)
    if not record:
        return None
    pos = float(record["pos"])
    neg = float(record["neg"])
    return round((pos - neg) / 100.0, 4)


def _failure(reason: str, message: str, network: NetworkBundle) -> Dict[str, Any]:
    nodes = network.graph.number_of_nodes()
    edges = network.graph.number_of_edges()
    return {
        "success": False,
        "reason": reason,
        "message": message,
        "removed": None,
        "baseline": {
            "nodes": nodes,
            "edges": edges,
            "density": metrics.density(edges, nodes),
        },
        "post": {
            "nodes": nodes,
            "edges": edges,
            "density": metrics.density(edges, nodes),
        },
        "delta_density": 0.0,
        "lost_edges": 0,
        "absorbing_brokers": [],
        "isolated_nodes": [],
        "severed_causal_routes": 0,
        "lost_sentiment_impact": None,
    }


def _absorbing(
    network: NetworkBundle,
    baseline: Dict[str, float],
    post: Dict[str, float],
) -> List[Dict[str, Any]]:
    """Simpul yang menyerap beban perantara setelah penghapusan."""
    rows: List[Dict[str, Any]] = []
    for node, value in post.items():
        if node == network.domain.ego_id:
            continue
        before = baseline.get(node, 0.0)
        delta = value - before
        if delta <= 0:
            continue
        rows.append(
            {
                "id": node,
                "label": network.label_of(node),
                "entity_type": network.type_of(node),
                "baseline_betweenness": round(before, 4),
                "post_betweenness": round(value, 4),
                "delta_betweenness": round(delta, 4),
                "pct_shift": round(delta / before * 100, 2) if before > 1e-4 else None,
            }
        )
    rows.sort(key=lambda item: (-item["delta_betweenness"], item["id"]))
    return rows[:ABSORBING_LIMIT]
