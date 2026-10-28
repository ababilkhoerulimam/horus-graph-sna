"""
Selang kepercayaan pergeseran peringkat antar-epos.

Delta peringkat dari dua irisan epos adalah selisih dua angka yang keduanya
punya ketidakpastian. Melaporkan "naik 4 peringkat" tanpa selang membuat
pergeseran satu-dua peringkat terbaca sebagai temuan, padahal itu bisa hilang
bila satu artikel berbeda masuk sampel.

Resampling berpasangan: setiap draw mengambil ulang artikel di kedua epos
dengan indeks yang sama, lalu kedua jaringan dihitung ulang dari nol. Unit
resampling adalah artikel (atau grup sindikasi bila dedup aktif) — sama dengan
bootstrap sentralitas, supaya kedua selang berbicara tentang populasi yang sama.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import networkx as nx
import numpy as np

from ..core.backbone import select_edges
from ..core.build import NetworkBundle, build_network
from ..core.cooccurrence import from_incidence, graph_from_cooccurrence
from ..core.temporal import article_years
from ..io.bundle import DataBundle

# Di atas ambang ini betweenness eksak terlalu mahal untuk 200 draw; sampel
# simpul tetap memberi peringkat yang bisa dibandingkan, dan pemakaiannya
# ditandai di keluaran.
EXACT_NODE_LIMIT = 500
APPROX_SAMPLES = 200


def rank_shift_interval(
    bundle: DataBundle,
    left_id: str,
    right_id: str,
    *,
    resamples: int = 200,
    seed: int = 42,
    ci: float = 90.0,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Selisih peringkat betweenness (target − baseline) beserta selangnya.

    Peringkat 1 = betweenness tertinggi. Positif berarti peringkatnya turun
    (angka peringkat membesar), dan itu ditulis apa adanya supaya tidak perlu
    diingat saat membaca keluaran.
    """
    windows = {epoch.id: epoch for epoch in bundle.domain.epochs}
    for epoch_id in (left_id, right_id):
        if epoch_id not in windows:
            raise KeyError(f"epos '{epoch_id}' tidak ada di domain")

    years = article_years(bundle)
    article_ids = bundle.articles["article_id"].astype(str).to_numpy()
    networks: Dict[str, NetworkBundle] = {}
    for epoch_id in (left_id, right_id):
        window = windows[epoch_id]
        mask = (years >= window.start_year) & (years <= window.end_year)
        subset = bundle.subset(article_ids[mask])
        if len(subset.articles) < 2:
            return _insufficient(
                epoch_id, len(subset.articles), left_id, right_id, resamples, seed, ci
            )
        networks[epoch_id] = build_network(subset)

    left = networks[left_id]
    right = networks[right_id]
    shared = [
        entity_id
        for entity_id in left.cooccurrence.entity_ids
        if entity_id in set(right.cooccurrence.entity_ids)
    ]
    if not shared:
        return _insufficient(
            "bersama", 0, left_id, right_id, resamples, seed, ci,
            reason="tidak ada entitas yang muncul di kedua epos",
        )

    baseline = _ranks(_betweenness(left.graph, APPROX_SAMPLES), shared)
    target = _ranks(_betweenness(right.graph, APPROX_SAMPLES), shared)

    rng = np.random.default_rng(seed)
    draws: Dict[str, List[int]] = {entity_id: [] for entity_id in shared}
    used = 0
    for _ in range(resamples):
        left_values = _draw(left, rng)
        right_values = _draw(right, rng)
        if left_values is None or right_values is None:
            continue
        left_ranks = _ranks(left_values, shared)
        right_ranks = _ranks(right_values, shared)
        for entity_id in shared:
            draws[entity_id].append(right_ranks[entity_id] - left_ranks[entity_id])
        used += 1

    low = (100.0 - ci) / 2.0
    high = 100.0 - low
    rows: List[Dict[str, Any]] = []
    for entity_id in shared:
        values = np.asarray(draws[entity_id], dtype=float)
        if values.size == 0:
            continue
        rows.append(
            {
                "id": entity_id,
                "baseline_rank": baseline[entity_id],
                "target_rank": target[entity_id],
                "delta_rank": target[entity_id] - baseline[entity_id],
                "median_shift": float(np.median(values)),
                "ci_low": float(np.percentile(values, low)),
                "ci_high": float(np.percentile(values, high)),
                "excludes_zero": bool(
                    np.percentile(values, low) > 0 or np.percentile(values, high) < 0
                ),
            }
        )

    rows.sort(key=lambda row: (-abs(row["median_shift"]), row["id"]))
    return {
        "status": "ready",
        "reason": None,
        "baseline_period": left_id,
        "target_period": right_id,
        "resamples": used,
        "seed": seed,
        "ci": ci,
        "betweenness_approx": bool(
            left.graph.number_of_nodes() > EXACT_NODE_LIMIT
            or right.graph.number_of_nodes() > EXACT_NODE_LIMIT
        ),
        "evaluated": len(rows),
        "entities": rows[: max(0, limit)],
    }


def _insufficient(
    epoch_id: str,
    articles: int,
    left_id: str,
    right_id: str,
    resamples: int,
    seed: int,
    ci: float,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Tidak ada yang bisa diresample: alasan ditulis, angka tidak dikarang."""
    return {
        "status": "insufficient",
        "reason": reason or f"epos {epoch_id} hanya {articles} artikel",
        "baseline_period": left_id,
        "target_period": right_id,
        "resamples": 0,
        "seed": seed,
        "ci": ci,
        "betweenness_approx": False,
        "evaluated": 0,
        "entities": [],
    }


def _draw(network: NetworkBundle, rng: np.random.Generator) -> Optional[Dict[str, float]]:
    """Satu resample artikel: bangun ulang backbone, lalu betweenness."""
    cooc = network.cooccurrence
    matrix = cooc.counting_matrix
    rows = int(matrix.shape[0])
    if rows < 2:
        return None
    sample = rng.integers(0, rows, size=rows)
    sampled = from_incidence(matrix[sample], cooc.entity_ids, total=rows)
    selected, _, _ = select_edges(sampled, network.backbone.config())
    graph = graph_from_cooccurrence(sampled, selected)
    if graph.number_of_edges() == 0:
        return {}
    return _betweenness(graph, APPROX_SAMPLES)


def _betweenness(graph: nx.Graph, samples: int) -> Dict[str, float]:
    if graph.number_of_nodes() > EXACT_NODE_LIMIT:
        return dict(
            nx.betweenness_centrality(
                graph, k=min(samples, graph.number_of_nodes()), seed=0, normalized=True
            )
        )
    return dict(nx.betweenness_centrality(graph, normalized=True))


def _ranks(values: Dict[str, float], ids: List[str]) -> Dict[str, int]:
    """Peringkat 1 = nilai tertinggi; seri dipecah oleh id supaya deterministik."""
    ordered = sorted(ids, key=lambda entity_id: (-float(values.get(entity_id, 0.0)), entity_id))
    return {entity_id: position + 1 for position, entity_id in enumerate(ordered)}