"""
Urutan graf per jendela waktu: siapa naik, siapa turun, seberapa bisa dipercaya.

Perbandingan dua epos menjawab "apa yang berubah antara dua titik". Yang tidak
terjawab: apakah perubahan itu satu lonjakan atau bagian dari arah yang
konsisten. Modul ini menyusun seri per simpul melintasi semua jendela, sehingga
pertanyaan yang bisa dijawab berubah dari "siapa broker di epos 2" menjadi
"apakah ia broker di semua epos, atau hanya sekali".

Dua hal yang dijaga:

1. Peringkat hanya dibandingkan di dalam jendelanya sendiri. Jumlah simpul dan
   kerapatan tiap jendela berbeda, jadi nilai mentah antar epos tidak sebanding;
   peringkat juga tidak, tetapi ia setidaknya menjawab urutan, bukan skala.
2. Simpul yang tidak muncul di sebuah jendela diberi null, bukan 0. Nol berarti
   "diukur, hasilnya nol"; null berarti "tidak ada di jendela itu" — dua hal
   yang berbeda dan tidak boleh tampil sama di UI.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .temporal import EpochSlice, TemporalBundle

SEQUENCE_METRICS = ("degree", "betweenness")
MIN_WINDOWS = 2
MOVERS_LIMIT = 5
ALL_TIME = "all_time"


def build_sequence(temporal: TemporalBundle, *, limit: int = MOVERS_LIMIT) -> Dict[str, Any]:
    """Seri sentralitas per simpul melintasi jendela epos, plus ringkasan gerak."""
    slices = [item for item in temporal.slices if item.window.id != ALL_TIME]
    if not slices:
        return awaiting("Dataset tanpa jendela epos: tidak ada urutan untuk dibandingkan.")
    if len(slices) < MIN_WINDOWS:
        return awaiting(
            f"Butuh minimal {MIN_WINDOWS} jendela epos untuk menyusun urutan; "
            f"bundle ini punya {len(slices)}."
        )

    windows = [item.window.id for item in slices]
    ranks, values = _per_window(slices)

    nodes = sorted({str(node) for item in slices for node in item.node_metrics.index})
    series = [_series_for(node, windows, ranks, values) for node in nodes]

    return {
        "status": "ready",
        "reason": None,
        "metrics": list(SEQUENCE_METRICS),
        "windows": windows,
        "nodes": len(nodes),
        "series": series,
        "movers": _movers(series, limit=limit),
        "rank_agreement": _agreement(ranks, windows),
    }


def awaiting(reason: str) -> Dict[str, Any]:
    """Blok hasil saat urutan belum bisa disusun, dengan alasannya."""
    return {
        "status": "awaiting_input",
        "reason": reason,
        "metrics": list(SEQUENCE_METRICS),
        "windows": [],
        "nodes": 0,
        "series": [],
        "movers": [],
        "rank_agreement": [],
    }


def _per_window(
    slices: Sequence[EpochSlice],
) -> Tuple[Dict[str, Dict[str, Dict[str, int]]], Dict[str, Dict[str, Dict[str, Optional[float]]]]]:
    """
    Peringkat dan nilai mentah per jendela.

    Peringkat 1 = tertinggi. Seri dipecah oleh id supaya dua simpul dengan nilai
    sama tidak bertukar tempat hanya karena urutan indeks berubah.
    """
    ranks: Dict[str, Dict[str, Dict[str, int]]] = {}
    values: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}
    for slice_ in slices:
        frame = slice_.node_metrics
        epoch = slice_.window.id
        ranks[epoch] = {}
        values[epoch] = {}
        for metric in SEQUENCE_METRICS:
            column = frame[metric] if metric in frame.columns else None
            ordered = (
                sorted(frame.index, key=lambda node: (-float(column.get(node, 0.0)), str(node)))
                if column is not None
                else []
            )
            ranks[epoch][metric] = {str(node): position + 1 for position, node in enumerate(ordered)}
            values[epoch][metric] = {
                str(node): (None if column is None else _number(column.get(node)))
                for node in frame.index
            }
    return ranks, values


def _number(value: Any) -> Optional[float]:
    """Nilai mentah sebagai float, atau None bila tidak terukur."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(number):
        return None
    return round(number, 6)


def _series_for(
    node: str,
    windows: Sequence[str],
    ranks: Dict[str, Dict[str, Dict[str, int]]],
    values: Dict[str, Dict[str, Dict[str, Optional[float]]]],
) -> Dict[str, Any]:
    """
    Satu simpul sebagai larik sejajar, bukan daftar objek per jendela.

    Urutannya sama dengan `windows` di blok induk. Larik dipakai karena nama
    kunci yang diulang 77 kali x 3 jendela menambah ~25 KB ke payload tanpa
    menambah satu pun informasi; yang kosong tetap null, jadi "tidak ada di
    jendela ini" tidak berubah menjadi 0.
    """
    degree = [values[epoch]["degree"].get(node) for epoch in windows]
    betweenness = [values[epoch]["betweenness"].get(node) for epoch in windows]
    degree_rank = [ranks[epoch]["degree"].get(node) for epoch in windows]
    betweenness_rank = [ranks[epoch]["betweenness"].get(node) for epoch in windows]

    return {
        "id": node,
        "degree": degree,
        "betweenness": betweenness,
        "degree_rank": degree_rank,
        "betweenness_rank": betweenness_rank,
        "betweenness_rank_shift": _shift(betweenness_rank[0], betweenness_rank[-1]),
        # Jumlah jendela tempat simpul ini muncul; pembaca perlu tahu apakah
        # serinya utuh atau berlubang sebelum menilai arahnya.
        "windows_present": sum(1 for value in degree_rank if value is not None),
    }


def _shift(first: Optional[int], last: Optional[int]) -> Optional[int]:
    """
    Perubahan peringkat dari jendela pertama ke terakhir.

    Positif berarti naik (peringkat mengecil). None bila salah satu ujungnya
    tidak ada — simpul yang baru muncul di jendela terakhir tidak punya arah.
    """
    if first is None or last is None:
        return None
    return int(first - last)


def _movers(series: Sequence[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
    rows = [
        {"id": row["id"], "betweenness_rank_shift": row["betweenness_rank_shift"]}
        for row in series
        if row["betweenness_rank_shift"] not in (None, 0)
    ]
    rows.sort(key=lambda row: (-abs(row["betweenness_rank_shift"]), row["id"]))
    return rows[:limit]


def _agreement(
    ranks: Dict[str, Dict[str, Dict[str, int]]],
    windows: Sequence[str],
) -> List[Dict[str, Any]]:
    """
    Korelasi peringkat antara jendela berurutan, pada simpul yang muncul di
    keduanya. Satu angka per pasangan, dengan jumlah simpul bersama supaya
    pembaca tahu dasarnya.
    """
    result: List[Dict[str, Any]] = []
    for left, right in zip(windows, windows[1:], strict=False):
        shared = [
            node for node in ranks[left]["betweenness"] if node in ranks[right]["betweenness"]
        ]
        result.append(
            {
                "left": left,
                "right": right,
                "shared_nodes": len(shared),
                "spearman": _spearman(
                    [ranks[left]["betweenness"][node] for node in shared],
                    [ranks[right]["betweenness"][node] for node in shared],
                ),
            }
        )
    return result


def _spearman(left: Sequence[int], right: Sequence[int]) -> Optional[float]:
    """
    Korelasi peringkat tanpa dependensi tambahan.

    Nilainya None bila kurang dari tiga simpul bersama atau bila salah satu sisi
    tidak punya variasi — dua kasus di mana koefisien tidak berarti apa-apa dan
    angka apa pun akan terbaca sebagai temuan.
    """
    if len(left) < 3:
        return None
    a = np.asarray(left, dtype=float)
    b = np.asarray(right, dtype=float)
    if a.std() == 0 or b.std() == 0:
        return None
    return round(float(np.corrcoef(a, b)[0, 1]), 4)
