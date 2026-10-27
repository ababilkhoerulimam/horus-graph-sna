"""
Null model yang mempertahankan derajat.

Pertanyaan yang dijawab: apakah modularitas/transitivitas/asortativitas yang
kita lihat lebih besar daripada yang wajar muncul dari graf acak dengan derajat
simpul yang sama? Tanpa pembanding ini, angka 0.3872 tidak berarti apa-apa —
graf acak pun bisa punya modularitas.

Pengacakan memakai double-edge swap, yang menjaga derajat setiap simpul persis
(bukan hanya harapannya seperti model konfigurasi), sehingga perbedaan hasil
hanya berasal dari susunan tepi.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import networkx as nx
import numpy as np

from ..core import metrics
from ..core.build import NetworkBundle
from . import stats

METRICS = ("modularity", "transitivity", "assortativity")


@dataclass(frozen=True)
class NullModelResult:
    observed: Dict[str, Optional[float]]
    null_mean: Dict[str, Optional[float]]
    null_sd: Dict[str, Optional[float]]
    z: Dict[str, Optional[float]]
    p_value: Dict[str, Optional[float]]
    resamples: int
    seed: int
    swaps_per_edge: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "observed": self.observed,
            "null_mean": self.null_mean,
            "null_sd": self.null_sd,
            "z": self.z,
            "p_value": self.p_value,
            "resamples": self.resamples,
            "seed": self.seed,
            "swaps_per_edge": self.swaps_per_edge,
            "method": "degree_preserving_double_edge_swap",
        }


def degree_preserving_null(
    network: NetworkBundle,
    resamples: int = 200,
    seed: int = 42,
    swaps_per_edge: int = 10,
) -> NullModelResult:
    """Bandingkan metrik graf dengan distribusi null yang derajatnya sama."""
    graph = network.graph
    if graph.number_of_edges() < 2:
        return _empty(graph)

    observed = {
        "modularity": _modularity(graph),
        "transitivity": _transitivity(graph),
        "assortativity": _assortativity(graph),
    }

    draws: Dict[str, list] = {name: [] for name in METRICS}
    n_swaps = max(1, graph.number_of_edges() * swaps_per_edge)

    for index in range(resamples):
        shuffled = graph.copy()
        try:
            nx.double_edge_swap(
                shuffled,
                nswap=n_swaps,
                max_tries=n_swaps * 10,
                seed=seed + index,
            )
        except (nx.NetworkXError, nx.NetworkXAlgorithmError):
            # Graf terlalu kecil/terlalu padat untuk ditukar; lewati resample ini.
            continue
        draws["modularity"].append(_modularity(shuffled))
        draws["transitivity"].append(_transitivity(shuffled))
        draws["assortativity"].append(_assortativity(shuffled))

    used = len(draws["modularity"])
    if used == 0:
        return _empty(graph)

    return NullModelResult(
        observed={name: _round(observed[name]) for name in METRICS},
        null_mean={name: _round(_nan_reduce(draws[name], np.nanmean)) for name in METRICS},
        null_sd={
            name: _round(_nan_reduce(draws[name], lambda data: np.nanstd(data, ddof=1)))
            for name in METRICS
        },
        z={name: _round(stats.z_score(observed[name], draws[name])) for name in METRICS},
        p_value={
            name: _round(stats.two_sided_p_value(observed[name], draws[name]))
            for name in METRICS
        },
        resamples=used,
        seed=seed,
        swaps_per_edge=swaps_per_edge,
    )


def _modularity(graph: nx.Graph) -> float:
    """Modularitas partisi Louvain graf itu sendiri (bukan partisi graf asal)."""
    communities = metrics.louvain(graph)
    value = metrics.modularity(graph, communities)
    return float("nan") if value is None else value


def _transitivity(graph: nx.Graph) -> float:
    try:
        return float(nx.transitivity(graph))
    except Exception:
        return float("nan")


def _assortativity(graph: nx.Graph) -> float:
    # Graf seragam-derajat membuat koefisien tidak terdefinisi; itu hasil yang
    # sah (dilaporkan sebagai None), bukan kondisi yang perlu berisik di log.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return float(nx.degree_assortativity_coefficient(graph))
    except Exception:
        return float("nan")


def _nan_reduce(values: list, func: Callable[[np.ndarray], float]) -> Optional[float]:
    """Reduksi yang mentoleransi kolom penuh NaN (metrik tak terdefinisi)."""
    data = np.asarray(values, dtype=float)
    if data.size == 0 or np.all(np.isnan(data)):
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return float(func(data))


def _round(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    number = float(value)
    if not np.isfinite(number):
        return None
    return round(number, 4)


def _empty(graph: nx.Graph) -> NullModelResult:
    return NullModelResult(
        observed={name: None for name in METRICS},
        null_mean={name: None for name in METRICS},
        null_sd={name: None for name in METRICS},
        z={name: None for name in METRICS},
        p_value={name: 1.0 for name in METRICS},
        resamples=0,
        seed=0,
        swaps_per_edge=0,
    )
