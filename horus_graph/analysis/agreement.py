"""
Kesepakatan peringkat antar-varian metrik.

Enam varian dihitung dari satu graf yang sama. Bila semuanya sepakat, urutan
entitas tidak bergantung pada pilihan metrik dan laporan boleh menyebut "yang
paling menonjol" tanpa kualifikasi. Bila tidak, angka tunggal itu menyembunyikan
pilihan — dan pilihan itulah yang harus dibaca sebagai keputusan analis.

`betweenness_weighted` memakai jarak `1/support`, bukan `support`: bobot besar
berarti hubungan dekat, sedangkan algoritma lintasan terpendek membaca bobot
sebagai jarak. Memakai `support` langsung membalik artinya tanpa terlihat.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

import networkx as nx

from ..core.build import NetworkBundle

RANK_VARIANTS = (
    "degree",
    "betweenness",
    "betweenness_weighted",
    "closeness",
    "pagerank",
    "articles",
)
TOP_K = 10
MIN_COVERAGE = 0.5


def kendall_tau_b(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    """
    Tau-b Kendall: korelasi peringkat yang mengoreksi seri.

    Seri tidak bisa dihindari di sini — banyak entitas punya betweenness 0 — dan
    tau-a akan melaporkannya sebagai ketidaksepakatan padahal kedua varian
    sama-sama menempatkannya di dasar.
    """
    if len(x) != len(y) or len(x) < 3:
        return None
    if len(set(x)) == 1 or len(set(y)) == 1:
        # Satu varian datar: arah kesepakatan tidak terdefinisi, bukan nol.
        return None
    from scipy.stats import kendalltau

    value = float(kendalltau(list(x), list(y), variant="b").statistic)
    return None if math.isnan(value) else round(value, 4)


def jaccard_top(a: Sequence[str], b: Sequence[str], k: int = TOP_K) -> Optional[float]:
    """Porsi beririsan dari dua daftar top-k; `None` bila keduanya kosong."""
    top_a = set(list(a)[: max(0, k)])
    top_b = set(list(b)[: max(0, k)])
    union = top_a | top_b
    return None if not union else round(len(top_a & top_b) / len(union), 4)


def _betweenness_weighted(network: NetworkBundle) -> Dict[str, Optional[float]]:
    """Betweenness pada graf berjarak `1/support`."""
    graph = network.graph
    if graph.number_of_edges() == 0:
        return {}
    copy = graph.copy()
    for source, target, data in copy.edges(data=True):
        support = float(data.get("weight") or 1.0)
        copy[source][target]["distance"] = 1.0 / max(support, 1.0)
    return dict(nx.betweenness_centrality(copy, weight="distance", normalized=True))


def _values(network: NetworkBundle, variant: str) -> Dict[str, Optional[float]]:
    if variant == "betweenness_weighted":
        return _betweenness_weighted(network)
    column = network.node_metrics.get(variant)
    if column is None:
        return {}
    return {
        str(entity_id): (None if value is None else float(value))
        for entity_id, value in column.items()
    }


def _ordered(values: Mapping[str, Optional[float]]) -> List[str]:
    present = [(key, value) for key, value in values.items() if value is not None]
    present.sort(key=lambda item: (-float(item[1]), item[0]))
    return [key for key, _ in present]


def _matrix(
    names: Sequence[str],
    compute,
) -> Dict[str, Dict[str, Optional[float]]]:
    return {
        a: {b: (1.0 if a == b else compute(a, b)) for b in names}
        for a in names
    }


def rank_agreement(
    network: NetworkBundle,
    top_k: int = TOP_K,
    extra: Optional[Mapping[str, Mapping[str, Optional[float]]]] = None,
) -> Dict[str, Any]:
    """
    Matriks tau-b dan Jaccard top-k antar-varian, plus cakupan tiap varian.

    `extra` dipakai lapisan API untuk menambahkan varian yang bukan metrik
    analisis (mis. `prominence`, bobot ukuran simpul di UI) tanpa membuat
    modul ini bergantung pada pengaturan tampilan.
    """
    values: Dict[str, Dict[str, Optional[float]]] = {
        name: _values(network, name) for name in RANK_VARIANTS
    }
    for name, mapping in (extra or {}).items():
        values[name] = {str(key): value for key, value in mapping.items()}

    names = list(values)
    orders = {name: _ordered(values[name]) for name in names}
    total = int(len(network.entities.index))
    coverage = {
        name: (None if total == 0 else round(len(orders[name]) / total, 4))
        for name in names
    }

    def tau(a: str, b: str) -> Optional[float]:
        # `None` dibuang berpasangan: entitas yang tidak terukur di salah satu
        # varian tidak boleh menyumbang sebagai nol.
        pairs: List[tuple[float, float]] = []
        for key in sorted(set(values[a]) & set(values[b])):
            left = values[a][key]
            right = values[b][key]
            if left is None or right is None:
                continue
            pairs.append((float(left), float(right)))
        return kendall_tau_b([x for x, _ in pairs], [y for _, y in pairs])

    def overlap(a: str, b: str) -> Optional[float]:
        return jaccard_top(orders[a], orders[b], top_k)

    weakest = min((value for value in coverage.values() if value is not None), default=None)
    status = "empty" if total == 0 else "ready"
    reason: Optional[str] = None
    if status == "ready" and weakest is not None and weakest < MIN_COVERAGE:
        status = "insufficient"
        reason = (
            f"cakupan terendah {weakest:.2f} < {MIN_COVERAGE:.2f}: sebagian varian "
            "tidak terukur untuk sebagian besar entitas"
        )

    return {
        "status": status,
        "reason": reason,
        "variants": names,
        "top_k": int(top_k),
        "min_coverage": MIN_COVERAGE,
        "coverage": coverage,
        "tau": _matrix(names, tau),
        "jaccard": _matrix(names, overlap),
    }