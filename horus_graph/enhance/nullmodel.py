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
from typing import Any, Callable, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np
from scipy import sparse

from .._coerce import to_number
from ..core import metrics
from ..core.backbone import select_edges
from ..core.build import NetworkBundle
from ..core.cooccurrence import from_incidence, graph_from_cooccurrence
from . import stats

# Dua pertanyaan, dua null:
# - `topology_null`: apakah susunan tepi proyeksi wajar, dengan derajat tetap?
# - `association_null`: apakah NPMI sebesar ini wajar, dengan margin insidensi
#   (artikel dan entitas) tetap?
METRICS = ("modularity", "transitivity", "assortativity")
ASSOCIATION_METRICS = ("edges", "density", "modularity", "transitivity", "assortativity")


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
    method: str = "degree_preserving_double_edge_swap"
    sweeps: int = 0

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
            "sweeps": self.sweeps,
            "method": self.method,
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
        return _empty(resamples, seed, swaps_per_edge)

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
        return _empty(resamples, seed, swaps_per_edge)

    return NullModelResult(
        observed={name: _round(observed[name]) for name in METRICS},
        null_mean={name: _round(_nan_reduce(draws[name], np.nanmean)) for name in METRICS},
        null_sd={
            name: _round(_nan_reduce(draws[name], lambda data: np.nanstd(data, ddof=1)))
            for name in METRICS
        },
        z={name: _round(stats.z_score(observed[name], draws[name])) for name in METRICS},
        p_value={name: _p_value(observed[name], draws[name]) for name in METRICS},
        resamples=used,
        seed=seed,
        swaps_per_edge=swaps_per_edge,
    )


def _p_value(observed: float, draws: list) -> Optional[float]:
    """
    p hanya ada bila metriknya terdefinisi.

    `empirical_p_value` mengembalikan 1.0 untuk observasi NaN agar perbandingan
    yang seluruhnya False tidak berubah menjadi "sangat signifikan". Untuk
    laporan, 1.0 tetap salah: itu angka yang dibaca sebagai "sudah diuji, tidak
    signifikan", padahal metriknya tidak terukur sama sekali.
    """
    if not np.isfinite(observed):
        return None
    return _round(stats.two_sided_p_value(observed, draws))


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
    return to_number(value, 4)


def _empty(
    resamples: int,
    seed: int,
    swaps_per_edge: int,
    names: Tuple[str, ...] = METRICS,
    method: str = "degree_preserving_double_edge_swap",
    sweeps: int = 0,
) -> NullModelResult:
    """
    Tidak ada yang bisa diuji.

    `p_value` sengaja None, bukan 1.0: p = 1.0 adalah hasil uji, sedangkan di
    sini tidak ada uji yang berjalan. `seed` diteruskan apa adanya supaya
    pembaca bisa melihat parameter yang diminta, bukan angka 0 yang tidak
    pernah dipakai.
    """
    return NullModelResult(
        observed={name: None for name in names},
        null_mean={name: None for name in names},
        null_sd={name: None for name in names},
        z={name: None for name in names},
        p_value={name: None for name in names},
        resamples=0,
        seed=seed,
        swaps_per_edge=swaps_per_edge,
        method=method,
        sweeps=sweeps,
    )


def association_null(
    network: NetworkBundle,
    resamples: int = 200,
    seed: int = 42,
    sweeps: int = 5,
) -> NullModelResult:
    """
    Null untuk NPMI: acak matriks insidensi, bukan proyeksi.

    NPMI didefinisikan pada margin insidensi (`support/total` versus
    `node_articles/total`), jadi hanya null yang menjaga derajat artikel dan
    entitas yang membuat sebaran NPMI sebanding dengan nilai teramati. Setiap
    draw menjalankan pipeline seleksi yang sama dengan graf nyata, termasuk
    gerbang q bila aktif.
    """
    cooc = network.cooccurrence
    matrix = cooc.counting_matrix
    if matrix.shape[0] < 2 or cooc.pair_count == 0:
        return _empty(
            resamples,
            seed,
            0,
            ASSOCIATION_METRICS,
            "bipartite_incidence_permutation",
            sweeps,
        )

    graph = network.graph
    observed = {
        "edges": float(graph.number_of_edges()),
        "density": metrics.density(graph.number_of_edges(), graph.number_of_nodes()),
        "modularity": _modularity(graph),
        "transitivity": _transitivity(graph),
        "assortativity": _assortativity(graph),
    }

    config = network.backbone.config()
    rng = np.random.default_rng(seed)
    draws: Dict[str, list] = {name: [] for name in ASSOCIATION_METRICS}
    for _ in range(resamples):
        permuted = _curveball(matrix, rng, sweeps)
        null_cooc = from_incidence(permuted, cooc.entity_ids, total=int(permuted.shape[0]))
        selected, _, _ = select_edges(null_cooc, config)
        null_graph = graph_from_cooccurrence(null_cooc, selected)
        edges = null_graph.number_of_edges()
        draws["edges"].append(float(edges))
        draws["density"].append(metrics.density(edges, null_graph.number_of_nodes()))
        draws["modularity"].append(_modularity(null_graph))
        draws["transitivity"].append(_transitivity(null_graph))
        draws["assortativity"].append(_assortativity(null_graph))

    return NullModelResult(
        observed={name: _round(observed[name]) for name in ASSOCIATION_METRICS},
        null_mean={
            name: _round(_nan_reduce(draws[name], np.nanmean)) for name in ASSOCIATION_METRICS
        },
        null_sd={
            name: _round(_nan_reduce(draws[name], lambda data: np.nanstd(data, ddof=1)))
            for name in ASSOCIATION_METRICS
        },
        z={name: _round(stats.z_score(observed[name], draws[name])) for name in ASSOCIATION_METRICS},
        p_value={name: _p_value(observed[name], draws[name]) for name in ASSOCIATION_METRICS},
        resamples=resamples,
        seed=seed,
        swaps_per_edge=0,
        method="bipartite_incidence_permutation",
        sweeps=sweeps,
    )


def _curveball(
    matrix: sparse.csr_matrix, rng: np.random.Generator, sweeps: int
) -> sparse.csr_matrix:
    """
    Curveball: tukar isi dua baris pada gabungan kolomnya.

    Kedua margin terjaga persis — jumlah artikel per entitas dan jumlah entitas
    per artikel tidak berubah — sehingga perbedaan hasil hanya berasal dari
    susunan keanggotaan, bukan dari derajat yang ikut bergeser.
    """
    row_count = int(matrix.shape[0])
    rows = [
        set(matrix.indices[matrix.indptr[i] : matrix.indptr[i + 1]].tolist())
        for i in range(row_count)
    ]
    trades = max(1, row_count * max(1, sweeps))
    for _ in range(trades):
        first = int(rng.integers(0, row_count))
        second = int(rng.integers(0, row_count))
        if first == second:
            continue
        # Hanya kolom yang berbeda yang boleh ditukar; kolom bersama tetap di
        # kedua baris. Menukar seluruh gabungan akan menghapus kolom bersama
        # dari baris kedua dan menggeser marginnya.
        first_set = rows[first]
        second_set = rows[second]
        common = first_set & second_set
        pool = sorted((first_set | second_set) - common)
        keep = len(first_set) - len(common)
        if len(pool) < 2 or keep == 0 or keep == len(pool):
            continue
        shuffled = [int(value) for value in rng.permutation(np.asarray(pool))]
        rows[first] = common | set(shuffled[:keep])
        rows[second] = common | set(shuffled[keep:])

    indices: List[int] = []
    indptr = [0]
    for row in rows:
        indices.extend(sorted(row))
        indptr.append(len(indices))
    return sparse.csr_matrix(
        (
            np.ones(len(indices), dtype=np.float64),
            np.asarray(indices, dtype=np.int32),
            np.asarray(indptr, dtype=np.int32),
        ),
        shape=matrix.shape,
    )


# Nama lama: pertanyaan "apakah susunan tepi proyeksi wajar" tetap sah, dan
# artefak yang sudah ditulis memakai nama ini.
topology_null = degree_preserving_null

