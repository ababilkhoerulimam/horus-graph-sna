"""
Seleksi backbone: dari semua pasangan co-occurrence ke himpunan edge yang layak.

Ambang `min_support` + `min_npmi` saja menghasilkan graf terputus: entitas yang
jarang muncul (pelatih baru, sponsor kecil) tidak pernah lolos ambang, padahal
kehadirannya di korpus nyata. Langkah konektivitas menambahkan tepat satu edge
terbaik per entitas yatim, dan edge itu dicatat terpisah supaya pembaca tahu
mana yang lolos ambang dan mana yang diselamatkan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np

from .cooccurrence import Cooccurrence


@dataclass(frozen=True)
class BackboneConfig:
    """Ambang seleksi edge. Default mengikuti artefak acuan horus-agent."""

    min_support: int = 3
    min_npmi: float = 0.2
    rescue_isolated: bool = True
    # Gerbang signifikansi. `None` berarti perilaku lama: hanya support dan
    # NPMI yang menyaring, sehingga "signifikan" tidak pernah diklaim.
    min_q: Optional[float] = None

    def __post_init__(self) -> None:
        if self.min_support < 1:
            raise ValueError("min_support minimal 1")
        if not -1.0 <= self.min_npmi <= 1.0:
            raise ValueError("min_npmi harus di rentang [-1, 1]")
        if self.min_q is not None and not 0.0 < self.min_q <= 1.0:
            raise ValueError("min_q harus di rentang (0, 1]")


@dataclass(frozen=True)
class BackboneReport:
    """Jejak audit seleksi: berapa kandidat, berapa lolos, berapa diselamatkan."""

    candidate_pairs: int
    above_threshold: int
    added_for_support: int
    entities_below_threshold: Tuple[str, ...]
    still_isolated: Tuple[str, ...]
    min_support: int
    min_npmi: float
    rescue_isolated: bool = True
    min_q: Optional[float] = None
    tested_pairs: int = 0
    significant_pairs: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "candidate_pairs": self.candidate_pairs,
            "above_threshold": self.above_threshold,
            "added_for_support": self.added_for_support,
            "entities_below_threshold": list(self.entities_below_threshold),
            "still_isolated": list(self.still_isolated),
            "min_support": self.min_support,
            "min_npmi": self.min_npmi,
            "rescue_isolated": self.rescue_isolated,
            # Keluarga uji ikut dilaporkan: q-value tanpa jumlah uji tidak bisa
            # ditafsirkan.
            "min_q": self.min_q,
            "tested_pairs": self.tested_pairs,
            "significant_pairs": self.significant_pairs,
        }

    def config(self) -> "BackboneConfig":
        """Konfigurasi yang menghasilkan laporan ini, untuk dijalankan ulang."""
        return BackboneConfig(
            min_support=self.min_support,
            min_npmi=self.min_npmi,
            rescue_isolated=self.rescue_isolated,
            min_q=self.min_q,
        )


def select_edges(
    cooc: Cooccurrence, config: BackboneConfig
) -> Tuple[np.ndarray, np.ndarray, BackboneReport]:
    """
    Kembalikan (posisi edge terpilih, mask `rescued`, laporan).

    Mask sejajar dengan posisi terpilih sehingga pemanggil bisa menandai edge
    mana yang lolos ambang dan mana yang hanya diselamatkan demi konektivitas.
    """
    support = cooc.support
    values = cooc.npmi

    scored = np.flatnonzero(np.isfinite(values))
    passing = (
        (support[scored] >= config.min_support) & (values[scored] >= config.min_npmi)
    )
    significant = 0
    blocked = np.zeros(cooc.support.size, dtype=bool)
    if config.min_q is not None:
        if cooc.q_value is None:
            raise ValueError("min_q butuh q_value; bangun Cooccurrence lewat from_incidence")
        significant_mask = cooc.q_value[scored] <= config.min_q
        blocked[scored] = ~significant_mask
        passing = passing & significant_mask
        significant = int(significant_mask.sum())
    selected = scored[passing]
    rescued_count = 0

    if config.rescue_isolated:
        # Penyelamatan tidak boleh menghidupkan lagi edge yang gagal gerbang q:
        # itu mengembalikan tepat edge yang diminta dibuang, tanpa jejak.
        selected, rescued_count = _rescue(cooc, selected, blocked=blocked)

    rescued = np.zeros(selected.size, dtype=bool)
    if rescued_count:
        rescued[-rescued_count:] = True

    order = _sort_order(selected, support, cooc.pair_u, cooc.pair_v)
    selected = selected[order]
    rescued = rescued[order]

    touched = np.zeros(len(cooc.entity_ids), dtype=bool)
    touched[cooc.pair_u[selected]] = True
    touched[cooc.pair_v[selected]] = True

    before = np.zeros(len(cooc.entity_ids), dtype=bool)
    before[cooc.pair_u[scored[passing]]] = True
    before[cooc.pair_v[scored[passing]]] = True
    isolated = [cooc.entity_ids[i] for i in np.flatnonzero(~before)]

    report = BackboneReport(
        candidate_pairs=int(scored.size),
        above_threshold=int(passing.sum()),
        added_for_support=rescued_count,
        entities_below_threshold=tuple(isolated),
        still_isolated=tuple(cooc.entity_ids[i] for i in np.flatnonzero(~touched)),
        min_support=config.min_support,
        min_npmi=config.min_npmi,
        rescue_isolated=config.rescue_isolated,
        min_q=config.min_q,
        tested_pairs=int(scored.size),
        significant_pairs=significant,
    )
    return selected, rescued, report


def _rescue(
    cooc: Cooccurrence,
    selected: np.ndarray,
    blocked: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, int]:
    """
    Tambah satu edge NPMI tertinggi untuk tiap entitas yang belum tersentuh.

    `blocked` menandai pasangan yang sudah ditolak gerbang signifikansi;
    penyelamatan hanya untuk konektivitas, bukan jalan memutar melewati ambang.
    """
    chosen = set(int(i) for i in selected)
    touched = np.zeros(len(cooc.entity_ids), dtype=bool)
    touched[cooc.pair_u[selected]] = True
    touched[cooc.pair_v[selected]] = True

    incident: Dict[int, list[int]] = {}
    for position in np.flatnonzero(np.isfinite(cooc.npmi)):
        incident.setdefault(int(cooc.pair_u[position]), []).append(int(position))
        incident.setdefault(int(cooc.pair_v[position]), []).append(int(position))

    added: list[int] = []
    for node in np.flatnonzero(~touched):
        pool = [
            p
            for p in incident.get(int(node), [])
            if p not in chosen and (blocked is None or not blocked[p])
        ]
        if not pool:
            continue
        best = max(pool, key=lambda p: cooc.npmi[p])
        chosen.add(best)
        added.append(best)

    if not added:
        return selected, 0
    return np.concatenate([selected, np.asarray(added, dtype=selected.dtype)]), len(added)


def _sort_order(
    selected: np.ndarray, support: np.ndarray, pair_u: np.ndarray, pair_v: np.ndarray
) -> np.ndarray:
    """Permutasi urutan deterministik: support turun, lalu indeks simpul naik."""
    if selected.size == 0:
        return np.zeros(0, dtype=np.int64)
    return np.lexsort(
        (pair_v[selected], pair_u[selected], -support[selected].astype(np.int64))
    )
