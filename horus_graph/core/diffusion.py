"""
Difusi di atas graf: berapa banyak simpul yang akhirnya ikut terinfeksi.

Dua model, keduanya dijalankan pada graf tak berarah yang sama:

1. **Independent cascade** — tiap sisi yang menyentuh simpul aktif punya
   peluang tetap untuk menularkan, dan tiap sisi hanya dicoba sekali. Peluangnya
   seragam: bobot NPMI bukan peluang, jadi memakainya sebagai peluang akan
   mengarang arti yang tidak bisa dipertanggungjawabkan.
2. **Linear threshold** — simpul ikut aktif bila proporsi tetangganya yang
   aktif mencapai ambang. Dengan ambang seragam model ini deterministik, dan
   itu dilaporkan apa adanya lewat `deterministic: true` — sebaran satu batang
   bukan hasil ukur ketidakpastian.

Yang dikembalikan selalu sebaran, bukan satu angka: berapa kali tiap jumlah
pengadopsi muncul dari `runs` jalankan, plus frekuensi tiap simpul ikut
terinfeksi. Satu angka rata-rata menyembunyikan bentuk sebarannya, dan bentuk
itulah yang menentukan apakah sebuah simpul layak disebut penyebar.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Set

import networkx as nx
import numpy as np

IC_METHOD = "independent_cascade_uniform_probability"
THRESHOLD_METHOD = "linear_threshold_uniform_share"
DEFAULT_RUNS = 200
MIN_RUNS = 10
MAX_RUNS = 2000

Step = Callable[[np.random.Generator, Set[str], Sequence[str]], List[str]]


def independent_cascade(
    graph: nx.Graph,
    seeds: Sequence[str],
    *,
    probability: float,
    runs: int = DEFAULT_RUNS,
    seed: int = 42,
) -> Dict[str, Any]:
    """Sebaran jumlah pengadopsi akhir pada model independent cascade."""
    _check_inputs(graph, seeds, runs)

    def step(rng: np.random.Generator, active: Set[str], frontier: Sequence[str]) -> List[str]:
        return _cascade_step(graph, rng, active, frontier, probability)

    return _simulate(
        graph,
        seeds,
        runs=runs,
        seed=seed,
        method=IC_METHOD,
        params={"probability": probability},
        step=step,
        deterministic=probability in (0.0, 1.0),
    )


def linear_threshold(
    graph: nx.Graph,
    seeds: Sequence[str],
    *,
    threshold: float,
    runs: int = DEFAULT_RUNS,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Sebaran jumlah pengadopsi akhir pada model linear threshold.

    Ambangnya sama untuk semua simpul dan tidak diundi, sehingga setiap
    jalankan menghasilkan hasil yang sama. `runs` tetap dijalankan supaya
    bentuk keluarannya seragam dengan model pertama, dan blok hasilnya
    menyatakan `deterministic: true` supaya sebaran satu batang tidak terbaca
    sebagai ukuran ketidakpastian.
    """

    def step(_rng: np.random.Generator, active: Set[str], _frontier: Sequence[str]) -> List[str]:
        return _threshold_step(graph, active, threshold)

    _check_inputs(graph, seeds, runs)
    return _simulate(
        graph,
        seeds,
        runs=runs,
        seed=seed,
        method=THRESHOLD_METHOD,
        params={"threshold": threshold},
        step=step,
        deterministic=True,
    )


def _check_inputs(graph: nx.Graph, seeds: Sequence[str], runs: int) -> None:
    if not MIN_RUNS <= runs <= MAX_RUNS:
        raise ValueError(f"Jumlah simulasi harus antara {MIN_RUNS} dan {MAX_RUNS}, bukan {runs}.")
    missing = [entity for entity in seeds if entity not in graph]
    if missing:
        raise ValueError(f"Simpul penyebar tidak ada di graf: {', '.join(sorted(missing))}.")


def _cascade_step(
    graph: nx.Graph,
    rng: np.random.Generator,
    active: Set[str],
    frontier: Sequence[str],
    probability: float,
) -> List[str]:
    """
    Satu gelombang penularan.

    Simpul yang baru tertular langsung masuk `active`, sehingga sisi dari dua
    penyebar ke simpul yang sama tidak memberi dua kesempatan menular — itu
    yang membedakan cascade dari sekadar pengambilan sampel berulang.
    """
    infected: List[str] = []
    for node in frontier:
        for neighbour in graph.neighbors(node):
            if neighbour in active:
                continue
            if rng.random() < probability:
                active.add(neighbour)
                infected.append(neighbour)
    return infected


def _threshold_step(graph: nx.Graph, active: Set[str], threshold: float) -> List[str]:
    """Satu gelombang: semua simpul dinilai serentak terhadap keadaan sebelumnya."""
    adopted: List[str] = []
    for node in graph.nodes:
        if node in active:
            continue
        neighbours = list(graph.neighbors(node))
        if not neighbours:
            continue
        share = sum(1 for neighbour in neighbours if neighbour in active) / len(neighbours)
        if share >= threshold:
            adopted.append(node)
    active.update(adopted)
    return adopted


def _simulate(
    graph: nx.Graph,
    seeds: Sequence[str],
    *,
    runs: int,
    seed: int,
    method: str,
    params: Dict[str, Any],
    step: Step,
    deterministic: bool,
) -> Dict[str, Any]:
    order = list(graph.nodes)
    index = {node: position for position, node in enumerate(order)}
    adopted_counts = np.zeros(len(order), dtype=int)
    final_sizes = np.zeros(runs, dtype=int)
    rng = np.random.default_rng(seed)

    for run in range(runs):
        active: Set[str] = set(seeds)
        frontier: List[str] = list(seeds)
        while frontier:
            frontier = step(rng, active, frontier)
        final_sizes[run] = len(active)
        for node in active:
            adopted_counts[index[node]] += 1

    frequencies = adopted_counts / runs
    return {
        "status": "ready",
        "method": method,
        "reason": None,
        "deterministic": deterministic,
        "params": {"seeds": list(seeds), "runs": runs, "seed": seed, **params},
        "nodes": len(order),
        "edges": graph.number_of_edges(),
        "distribution": _distribution(final_sizes, runs),
        "mean": round(float(final_sizes.mean()), 3),
        "p05": int(np.percentile(final_sizes, 5)),
        "p50": int(np.percentile(final_sizes, 50)),
        "p95": int(np.percentile(final_sizes, 95)),
        "adoption_frequency": [
            {"id": node, "frequency": round(float(frequencies[index[node]]), 4)}
            for node in order
            if frequencies[index[node]] > 0
        ],
    }


def _distribution(final_sizes: np.ndarray, runs: int) -> List[Dict[str, Any]]:
    """Sebaran penuh, bukan hanya rata-rata: jumlah pengadopsi → berapa kali muncul."""
    values, counts = np.unique(final_sizes, return_counts=True)
    return [
        {"adopted": int(value), "count": int(count), "share": round(int(count) / runs, 4)}
        for value, count in zip(values, counts, strict=True)
    ]


def awaiting(reason: str, method: Optional[str] = None) -> Dict[str, Any]:
    """Blok hasil saat difusi belum bisa dihitung, dengan alasannya."""
    return {
        "status": "awaiting_input",
        "method": method,
        "reason": reason,
        "deterministic": None,
        "params": None,
        "nodes": None,
        "edges": None,
        "distribution": [],
        "mean": None,
        "p05": None,
        "p50": None,
        "p95": None,
        "adoption_frequency": [],
    }
