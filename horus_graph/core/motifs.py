"""
Motif lokal: sensus triad dan koefisien rich-club.

Keduanya menjawab pertanyaan yang tidak dijawab modularitas. Modularitas
mengatakan jaringan terpecah menjadi gugus; sensus triad mengatakan apakah
gugus itu tersusun dari segitiga tertutup atau dari rantai terbuka. Rich-club
mengatakan apakah simpul berderajat tinggi saling terhubung lebih rapat
daripada yang diharapkan dari derajatnya saja.

Graf di engine ini tidak berarah, jadi sensus triad dijalankan pada salinan
berarah simetris. Konsekuensinya hanya empat dari enam belas kelas
Davis–Leinhardt yang mungkin muncul (003, 102, 201, 300), dan itu memang
seluruh isi sensus untuk graf tak berarah — bukan penyederhanaan yang
kehilangan informasi.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

import networkx as nx

TRIAD_METHOD = "undirected_triad_census_symmetric"
RICH_CLUB_METHOD = "rich_club_colizza2006_multi_null"
DEFAULT_RICH_CLUB_REPLICATES = 10
DEFAULT_SWAPS_PER_EDGE = 10
# Di bawah ini subgraf berderajat tinggi terlalu kecil untuk memberi rasio yang
# bisa dipercaya: pada graf emas, k=22 menyisakan 3 simpul dan rasionya
# melompat antara 1,3 dan 3,0 hanya karena ganti seed.
MIN_RICH_CLUB_NODES = 10

# Kelas yang mungkin pada graf tak berarah; sisanya selalu nol dan tidak
# dikirim, supaya pembaca tidak mengira nol itu hasil ukur.
UNDIRECTED_CLASSES = ("003", "102", "201", "300")


@dataclass(frozen=True)
class TriadCensus:
    """Sebaran triad: berapa triple yang kosong, bertepi satu, dua, tiga."""

    status: str
    counts: Mapping[str, int] = field(default_factory=dict)
    triples: int = 0
    reason: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.status == "ready"

    @property
    def triangles(self) -> Optional[int]:
        return None if not self.counts else self.counts.get("300", 0)

    @property
    def open_wedges(self) -> Optional[int]:
        return None if not self.counts else self.counts.get("201", 0)

    @property
    def closed_share(self) -> Optional[float]:
        """
        Proporsi triad bertepi ≥2 yang tertutup penuh.

        Bukan transitivitas global: transitivitas menghitung ulang setiap
        segitiga menjadi tiga triple terhubung, sedangkan angka ini hanya
        membandingkan 300 dengan 201. Keduanya dipakai berdampingan, bukan
        saling menggantikan.
        """
        if self.triangles is None or self.open_wedges is None:
            return None
        connected = self.triangles + self.open_wedges
        if connected == 0:
            return None
        return round(self.triangles / connected, 4)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "method": TRIAD_METHOD,
            "classes": dict(self.counts),
            "triples": self.triples if self.counts else None,
            "triangles": self.triangles,
            "open_wedges": self.open_wedges,
            "closed_share": self.closed_share,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RichClub:
    """
    Koefisien rich-club per ambang derajat.

    `ratio` hanya terisi bila pembanding acak dijalankan. Tanpa pembanding,
    kurva mentahnya naik secara konstruksi (semakin tinggi ambang derajat,
    semakin rapat sisa subgraf), sehingga tidak boleh dibaca sebagai bukti.
    """

    status: str
    normalized: bool
    replicates: int
    swaps_per_edge: int
    coefficients: Mapping[int, float] = field(default_factory=dict)
    ratio: Mapping[int, Optional[float]] = field(default_factory=dict)
    truncated: int = 0
    reason: Optional[str] = None

    @property
    def peak(self) -> Optional[Dict[str, Any]]:
        """
        Titik tertinggi kurva rasio, atau None bila belum dinormalisasi.

        Ambang derajat 0 dikeluarkan: rasionya selalu tepat 1,0 karena graf
        acak berderajat sama punya jumlah sisi yang sama, sehingga densitasnya
        identik. Angka itu tidak membawa informasi dan akan selalu "menang"
        pada graf tanpa efek rich-club.
        """
        values = {
            degree: value
            for degree, value in self.ratio.items()
            if degree > 0 and value is not None
        }
        if not values:
            return None
        degree = max(values, key=lambda key: (values[key], key))
        return {"degree": degree, "ratio": round(float(values[degree]), 4)}

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "method": RICH_CLUB_METHOD,
            "normalized": self.normalized,
            "replicates": self.replicates,
            "swaps_per_edge": self.swaps_per_edge,
            "coefficients": [
                {"degree": degree, "coefficient": round(float(value), 4)}
                for degree, value in sorted(self.coefficients.items())
            ],
            "ratio": [
                {"degree": degree, "ratio": None if value is None else round(float(value), 4)}
                for degree, value in sorted(self.ratio.items())
            ],
            "truncated_degrees": self.truncated,
            "peak": self.peak,
            "reason": self.reason,
        }


def triad_census(graph: nx.Graph) -> TriadCensus:
    """Sensus triad pada salinan berarah simetris; murah (0,1 detik pada 475 sisi)."""
    if graph.number_of_nodes() < 3:
        return TriadCensus(
            status="awaiting_input",
            reason="Butuh minimal tiga simpul untuk membentuk satu triad.",
        )
    if graph.number_of_edges() == 0:
        return TriadCensus(
            status="awaiting_input",
            reason="Graf tanpa sisi: semua triad pasti kosong, sehingga sebarannya tidak informatif.",
        )
    try:
        raw = nx.triadic_census(graph.to_directed())
    except Exception:  # noqa: BLE001 - census gagal bukan alasan menggagalkan build
        return TriadCensus(status="awaiting_input", reason="Sensus triad gagal dihitung.")

    counts = {name: int(raw.get(name, 0)) for name in UNDIRECTED_CLASSES}
    return TriadCensus(
        status="ready",
        counts=counts,
        triples=sum(counts.values()),
    )


def rich_club(
    graph: nx.Graph,
    *,
    normalize: bool = True,
    replicates: int = DEFAULT_RICH_CLUB_REPLICATES,
    swaps_per_edge: int = DEFAULT_SWAPS_PER_EDGE,
    min_nodes: int = MIN_RICH_CLUB_NODES,
    seed: int = 42,
) -> RichClub:
    """
    Kurva rich-club, dengan pembanding acak bila diminta.

    Pembandingnya **rata-rata beberapa graf acak berderajat sama**, bukan satu
    seperti `networkx.rich_club_coefficient(normalized=True)`. Perbedaan itu
    bukan gaya: fungsi itu memakai satu realisasi acak, sehingga puncak rasio
    pada graf emas melompat antara 1,3 dan 3,0 hanya karena ganti seed. Dengan
    sepuluh realisasi, nilai pada ambang derajat yang sama bergerak di kisaran
    1,07-1,11 — cukup sempit untuk dilaporkan sebagai satu angka.

    Kurva juga dipotong pada ambang derajat yang masih menyisakan `min_nodes`
    simpul. Di atas itu rasio dua bilangan kecil, dan angkanya bergerak liar
    tanpa memberi informasi.
    """
    if graph.number_of_edges() == 0:
        return RichClub(
            status="awaiting_input",
            normalized=False,
            replicates=0,
            swaps_per_edge=0,
            reason="Graf tanpa sisi: tidak ada subgraf berderajat untuk dibandingkan.",
        )
    try:
        observed = nx.rich_club_coefficient(graph, normalized=False)
    except Exception:  # noqa: BLE001
        return RichClub(
            status="awaiting_input",
            normalized=False,
            replicates=0,
            swaps_per_edge=0,
            reason="Koefisien rich-club tidak terdefinisi untuk graf ini.",
        )

    degrees = dict(graph.degree())
    kept = {
        int(degree): float(value)
        for degree, value in observed.items()
        if sum(1 for value_ in degrees.values() if value_ > degree) >= min_nodes
    }
    truncated = len(observed) - len(kept)
    if not kept:
        # Status "ready" dengan kurva kosong akan terbaca seperti "tidak ada
        # rich club", padahal yang terjadi adalah grafnya terlalu kecil.
        return RichClub(
            status="awaiting_input",
            normalized=False,
            replicates=0,
            swaps_per_edge=0,
            coefficients={},
            truncated=truncated,
            reason=(
                f"Tidak ada ambang derajat yang menyisakan {min_nodes} simpul; "
                "kurva rich-club tidak bisa dibaca pada graf sebesar ini."
            ),
        )

    if not normalize:
        return RichClub(
            status="ready",
            normalized=False,
            replicates=0,
            swaps_per_edge=0,
            coefficients=kept,
            truncated=truncated,
        )

    count = max(1, int(replicates))
    draws = max(1, int(swaps_per_edge))
    nulls = _null_curves(graph, count, draws, seed)
    if not nulls:
        return RichClub(
            status="awaiting_input",
            normalized=False,
            replicates=0,
            swaps_per_edge=0,
            coefficients=kept,
            truncated=truncated,
            reason="Graf acak berderajat sama gagal dibangun untuk graf ini.",
        )

    ratio: Dict[int, Optional[float]] = {}
    for degree, value in kept.items():
        column = [curve[degree] for curve in nulls if degree in curve]
        if not column:
            ratio[degree] = None
            continue
        average = statistics.fmean(column)
        ratio[degree] = None if average == 0 else value / average

    return RichClub(
        status="ready",
        normalized=True,
        replicates=len(nulls),
        swaps_per_edge=draws,
        coefficients=kept,
        ratio=ratio,
        truncated=truncated,
    )


def _null_curves(
    graph: nx.Graph, replicates: int, swaps_per_edge: int, seed: int
) -> List[Dict[int, float]]:
    """
    Kurva rich-club dari graf acak berderajat sama.

    Pengacakan memakai pertukaran sisi berganda; `swaps_per_edge` kali jumlah
    sisi sudah cukup membuat susunan sisi lepas dari susunan aslinya.
    """
    swaps = swaps_per_edge * graph.number_of_edges()
    rng = random.Random(seed)
    curves: List[Dict[int, float]] = []
    for _ in range(replicates):
        shuffled = graph.copy()
        try:
            nx.double_edge_swap(shuffled, nswap=swaps, max_tries=swaps * 10, seed=rng)
            curves.append(
                {int(k): float(v) for k, v in nx.rich_club_coefficient(shuffled, normalized=False).items()}
            )
        except Exception:  # noqa: BLE001 - satu realisasi gagal bukan alasan menyerah
            continue
    return curves


def motif_block(triads: TriadCensus, club: Optional[RichClub] = None) -> Dict[str, Any]:
    """Satu blok untuk `/api/bootstrap`, dengan status per bagian."""
    block: Dict[str, Any] = {"triads": triads.as_dict()}
    if club is None:
        block["rich_club"] = {
            "status": "awaiting_input",
            "method": RICH_CLUB_METHOD,
            "reason": (
                "Rich-club belum dihitung. Jalankan `horus-graph motifs <bundle> --write`; "
                "kurva mentahnya naik secara konstruksi sehingga tidak dikirim tanpa pembanding."
            ),
        }
    else:
        block["rich_club"] = club.as_dict()
    return block


def ranked_triads(counts: Mapping[str, int]) -> List[Dict[str, Any]]:
    """Kelas triad terbesar lebih dulu; nol tidak ikut dikirim."""
    pairs = [(name, int(count)) for name, count in counts.items() if int(count) > 0]
    pairs.sort(key=lambda item: (-item[1], item[0]))
    return [{"class": name, "count": count} for name, count in pairs]
