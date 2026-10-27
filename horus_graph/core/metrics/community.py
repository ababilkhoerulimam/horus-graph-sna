"""Deteksi komunitas deterministik."""

from __future__ import annotations

from typing import Dict, List, Optional

import networkx as nx

COMMUNITY_METHOD = "louvain_weighted_seed42"


def louvain(graph: nx.Graph, seed: int = 42) -> Dict[str, int]:
    """
    Louvain berbobot dengan indeks komunitas stabil.

    Louvain mengembalikan partisi tanpa urutan; indeks diurutkan menurut ukuran
    komunitas lalu nama simpul terkecil supaya nomor "Komunitas 1" tidak
    berpindah hanya karena urutan iterasi internal berubah.
    """
    if graph.number_of_nodes() == 0:
        return {}
    if graph.number_of_edges() == 0:
        return {node: 1 for node in graph.nodes}
    try:
        groups = nx.community.louvain_communities(graph, weight="weight", seed=seed)
    except Exception:
        return {node: 1 for node in graph.nodes}

    ordered: List[set] = sorted(groups, key=lambda group: (-len(group), sorted(group)[0]))
    mapping: Dict[str, int] = {}
    for index, group in enumerate(ordered, start=1):
        for node in group:
            mapping[node] = index
    return mapping


def modularity(graph: nx.Graph, communities: Dict[str, int]) -> Optional[float]:
    """Modularitas partisi; `None` bila tidak terdefinisi (graf tanpa edge)."""
    if graph.number_of_edges() == 0 or not communities:
        return None
    groups: Dict[int, List[str]] = {}
    for node, index in communities.items():
        groups.setdefault(index, []).append(node)
    try:
        return float(nx.community.modularity(graph, list(groups.values()), weight="weight"))
    except Exception:
        return None
