"""
Sentralitas dan peran struktural.

Nilai yang gagal dihitung dikembalikan `None`, bukan 0.0: nol adalah klaim
("tidak ada jalur yang lewat sini"), sedangkan `None` adalah pengakuan bahwa
angkanya tidak tersedia. UI dan laporan wajib membedakan keduanya.
"""

from __future__ import annotations

import math
from typing import Dict, Optional

import networkx as nx

BETWEENNESS_METHOD = "freeman_betweenness_unweighted_normalized"
CONSTRAINT_METHOD = "burt_constraint_weighted"
EFFECTIVE_SIZE_METHOD = "burt_effective_size_weighted"
PAGERANK_METHOD = "networkx_pagerank_weighted"
CLOSENESS_METHOD = "networkx_closeness_distance_weighted"

BETWEENNESS_DECIMALS = 6


def betweenness(graph: nx.Graph, samples: Optional[int] = None) -> Dict[str, float]:
    """
    Freeman betweenness ternormalisasi.

    Bobot artikel sengaja diabaikan: sering muncul bersama bukan berarti jarak
    jauh. `samples` memakai aproksimasi pivot acak untuk graf besar; hasilnya
    tidak deterministik sehingga hanya dipakai di luar jalur golden test.
    """
    if graph.number_of_nodes() == 0:
        return {}
    if samples is not None and samples < graph.number_of_nodes():
        return nx.betweenness_centrality(
            graph, k=samples, weight=None, normalized=True, seed=42
        )
    return nx.betweenness_centrality(graph, weight=None, normalized=True)


def closeness(graph: nx.Graph) -> Dict[str, Optional[float]]:
    if graph.number_of_nodes() == 0:
        return {}
    try:
        return nx.closeness_centrality(graph)
    except Exception:
        return {node: None for node in graph.nodes}


def constraint(graph: nx.Graph) -> Dict[str, Optional[float]]:
    """Burt constraint; `None` untuk simpul yang tidak bisa dihitung."""
    if graph.number_of_nodes() == 0:
        return {}
    try:
        raw = nx.constraint(graph, weight="weight")
    except Exception:
        return {node: None for node in graph.nodes}
    return {node: _clean(value) for node, value in raw.items()}


def effective_size(graph: nx.Graph) -> Dict[str, Optional[float]]:
    """Burt effective size; `None` bila gagal dihitung (bukan degree karangan)."""
    if graph.number_of_nodes() == 0:
        return {}
    try:
        raw = nx.effective_size(graph, weight="weight")
    except Exception:
        return {node: None for node in graph.nodes}
    return {node: _clean(value) for node, value in raw.items()}


def pagerank(graph: nx.Graph) -> Dict[str, Optional[float]]:
    """PageRank berbobot; `None` bila perhitungan gagal."""
    if graph.number_of_nodes() == 0:
        return {}
    try:
        return nx.pagerank(graph, weight="weight", max_iter=200)
    except Exception:
        return {node: None for node in graph.nodes}


def structural_hole_role(value: Optional[float]) -> Optional[str]:
    """Label peran lubang struktural dari nilai constraint (Burt)."""
    if value is None:
        return None
    if value < 0.25:
        return "Low Constraint (High Autonomy Broker / Tertius Gaudens)"
    if value <= 0.45:
        return "Moderate Constraint (Balanced Bridge)"
    return "High Constraint (Embedded Clique)"


def _clean(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None
    return number
