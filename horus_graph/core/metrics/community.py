"""
Deteksi komunitas deterministik, plus ukuran seberapa stabil tiap simpul.

Satu jalankan Louvain memberi satu partisi, tetapi tidak memberi tahu apakah
partisi itu pilihan yang kuat atau hanya satu dari beberapa pembagian yang
hampir sama baiknya. Karena itu partisi konsensus dibangun dari banyak jalankan
dengan seed berbeda, lalu setiap simpul diberi angka: seberapa sering ia duduk
bersama anggota komunitasnya sendiri.

Stabilitas sengaja **tidak** memakai jalankan acuan (medoid). Kalau ikut
dihitung, setiap simpul mendapat tambahan 1/runs yang bukan hasil ukur.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Dict, List, Mapping, Optional, Sequence

import networkx as nx

from .agreement import adjusted_rand_index

COMMUNITY_METHOD = "louvain_weighted_seed42"
CONSENSUS_METHOD = "coassociation_louvain"
DEFAULT_CONSENSUS_RUNS = 20
MIN_CONSENSUS_RUNS = 2
# Di bawah ambang ini simpul dianggap "batas": lebih sering berpindah sisi
# daripada bertahan. Ambang adalah pilihan analis, bukan hukum alam.
LOW_STABILITY = 0.75
LOW_STABILITY_LIMIT = 10


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


@dataclass(frozen=True)
class ConsensusResult:
    """
    Partisi konsensus dan stabilitas per simpul.

    `stability[node]` adalah rata-rata proporsi anggota komunitas konsensus yang
    ikut bersama simpul itu pada jalankan lain. `None` berarti tidak terukur:
    simpul tanpa tetangga, atau simpul yang sendirian di komunitasnya, tidak
    punya pasangan untuk dibandingkan — dan itu bukan nol.
    """

    status: str
    runs: int
    seed: int
    labels: Mapping[str, int] = field(default_factory=dict)
    stability: Mapping[str, Optional[float]] = field(default_factory=dict)
    agreement: Optional[float] = None
    reason: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.status == "ready"

    def unstable(self, limit: int = LOW_STABILITY_LIMIT) -> List[Dict[str, Any]]:
        """Simpul paling tidak stabil, untuk dibaca manusia."""
        ranked = [
            (node, value)
            for node, value in self.stability.items()
            if value is not None and value < LOW_STABILITY
        ]
        ranked.sort(key=lambda item: (item[1], item[0]))
        return [{"id": node, "stability": value} for node, value in ranked[:limit]]

    def as_dict(self) -> Dict[str, Any]:
        values = [value for value in self.stability.values() if value is not None]
        return {
            "status": self.status,
            "method": CONSENSUS_METHOD,
            "runs": self.runs,
            "seed": self.seed,
            "agreement": self.agreement,
            "communities": len(set(self.labels.values())),
            "stability_median": round(float(median(values)), 4) if values else None,
            # Nol berarti "tidak ada simpul batas", bukan "belum diukur".
            "unstable_count": (
                sum(1 for value in values if value < LOW_STABILITY)
                if self.status == "ready"
                else None
            ),
            "unstable": self.unstable(),
            "reason": self.reason,
        }


def consensus(
    graph: nx.Graph,
    runs: int = DEFAULT_CONSENSUS_RUNS,
    seed: int = 42,
) -> ConsensusResult:
    """
    Partisi konsensus dari `runs` jalankan Louvain dengan seed berbeda.

    Partisi acuan diambil dari jalankan yang paling dekat ke semua jalankan lain
    (ARI rata-rata tertinggi), karena partisi komunitas tidak punya urutan yang
    bisa dirata-ratakan. Stabilitas dihitung lewat tabel kontingensi, bukan
    matriks co-asosiasi n x n: hasilnya sama persis, tetapi biaya memorinya O(n)
    sehingga tetap terpakai pada graf besar.
    """
    nodes = sorted(graph.nodes)
    if not nodes:
        return ConsensusResult(
            status="awaiting_input",
            runs=0,
            seed=seed,
            reason="Graf kosong: tidak ada simpul untuk dipartisi.",
        )
    if graph.number_of_edges() == 0:
        return ConsensusResult(
            status="awaiting_input",
            runs=0,
            seed=seed,
            labels={node: 1 for node in nodes},
            stability={node: None for node in nodes},
            reason=(
                "Graf tanpa sisi: Louvain menempatkan semua simpul di satu komunitas, "
                "sehingga tidak ada perbedaan antar jalankan untuk diukur."
            ),
        )

    count = max(MIN_CONSENSUS_RUNS, int(runs))
    partitions = [louvain(graph, seed=seed + offset) for offset in range(count)]
    scores = _pairwise_ari(partitions, nodes)

    reference = max(range(count), key=lambda index: (sum(scores[index]) / count, -index))
    labels = partitions[reference]
    stability = _stability(partitions, labels, nodes, skip=reference)

    pairs = [
        scores[left][right]
        for left in range(count)
        for right in range(left + 1, count)
    ]
    agreement = round(sum(pairs) / len(pairs), 4) if pairs else None

    return ConsensusResult(
        status="ready",
        runs=count,
        seed=seed,
        labels=labels,
        stability=stability,
        agreement=agreement,
    )


def _pairwise_ari(partitions: Sequence[Mapping[str, int]], nodes: Sequence[str]) -> List[List[float]]:
    """ARI semua pasangan jalankan; diagonal 1.0 karena partisi identik dengan dirinya."""
    count = len(partitions)
    scores = [[1.0] * count for _ in range(count)]
    for left in range(count):
        left_labels = [partitions[left][node] for node in nodes]
        for right in range(left + 1, count):
            right_labels = [partitions[right][node] for node in nodes]
            value = float(adjusted_rand_index(left_labels, right_labels))
            scores[left][right] = value
            scores[right][left] = value
    return scores


def _stability(
    partitions: Sequence[Mapping[str, int]],
    labels: Mapping[str, int],
    nodes: Sequence[str],
    *,
    skip: int,
) -> Dict[str, Optional[float]]:
    """
    Rata-rata proporsi anggota komunitas acuan yang menemani tiap simpul.

    Untuk simpul `u` di komunitas acuan `C`, nilainya adalah rata-rata
    `|jalankan(u) ∩ C| - 1` dibagi `|C| - 1` atas semua jalankan selain jalankan
    acuan. Karena itu nilainya 0..1 dan `None` hanya muncul ketika penyebutnya 0.
    """
    sizes = Counter(labels.values())
    totals: Dict[str, float] = {node: 0.0 for node in nodes}
    used = 0

    for index, partition in enumerate(partitions):
        if index == skip:
            continue
        used += 1
        together: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for node in nodes:
            together[labels[node]][partition.get(node, 1)] += 1
        for node in nodes:
            community = labels[node]
            peers = sizes[community] - 1
            if peers <= 0:
                continue
            totals[node] += (together[community][partition.get(node, 1)] - 1) / peers

    result: Dict[str, Optional[float]] = {}
    for node in nodes:
        if sizes[labels[node]] <= 1 or used == 0:
            result[node] = None
        else:
            result[node] = round(totals[node] / used, 4)
    return result
