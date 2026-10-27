"""
Perputaran jaringan antar epos: siapa masuk, siapa keluar, berapa tepi bertahan.

Tanpa angka ini, "jaringan berubah" hanya kesan. Jaccard tepi memisahkan dua
hal yang sering tertukar: komposisi simpul berganti (aktor baru muncul) versus
relasi antar aktor yang sama benar-benar berubah.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from ..core.temporal import TemporalBundle


def epoch_turnover(temporal: TemporalBundle) -> pd.DataFrame:
    """Satu baris per pasangan epos berurutan (agregat all_time dilewati)."""
    slices = [item for item in temporal.slices if item.window.id != "all_time"]
    rows: List[Dict[str, Any]] = []

    for previous, current in zip(slices, slices[1:], strict=False):
        previous_nodes = set(previous.graph.nodes)
        current_nodes = set(current.graph.nodes)
        previous_edges = _edges(previous.graph)
        current_edges = _edges(current.graph)

        rows.append(
            {
                "from_epoch": previous.window.id,
                "to_epoch": current.window.id,
                "nodes_from": len(previous_nodes),
                "nodes_to": len(current_nodes),
                "nodes_added": len(current_nodes - previous_nodes),
                "nodes_removed": len(previous_nodes - current_nodes),
                "edges_from": len(previous_edges),
                "edges_to": len(current_edges),
                "edges_added": len(current_edges - previous_edges),
                "edges_removed": len(previous_edges - current_edges),
                "node_jaccard": _jaccard(previous_nodes, current_nodes),
                "edge_jaccard": _jaccard(previous_edges, current_edges),
                "added_nodes": sorted(current_nodes - previous_nodes),
                "removed_nodes": sorted(previous_nodes - current_nodes),
            }
        )

    return pd.DataFrame(rows)


def turnover_summary(temporal: TemporalBundle) -> Dict[str, Any]:
    frame = epoch_turnover(temporal)
    if frame.empty:
        return {"transitions": 0, "mean_edge_jaccard": None, "transitions_detail": []}
    return {
        "transitions": len(frame),
        "mean_edge_jaccard": round(float(frame["edge_jaccard"].mean()), 4),
        "mean_node_jaccard": round(float(frame["node_jaccard"].mean()), 4),
        "transitions_detail": frame.drop(columns=["added_nodes", "removed_nodes"]).to_dict(
            orient="records"
        ),
        "method": "consecutive_epoch_jaccard",
    }


def _edges(graph) -> set:
    return {frozenset((u, v)) for u, v in graph.edges()}


def _jaccard(left: set, right: set) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 1.0
    return round(len(left & right) / len(union), 4)
