"""
Skala visual dari peringkat, bukan dari konstanta dataset.

Sebelum modul ini, `index.html` memetakan degree ke radius dengan
`(deg - 11) / (47 - 11)`, betweenness dengan `bw / 0.04`, dan volume dengan
rentang `2.2..3.85`. Ketiga angka itu berasal dari satu dataset. Pada dataset
lain, setiap simpul jatuh ke kelas bawah dan kanvas tetap tampak wajar — gagal
tanpa error, dan tidak ada yang tahu harus curiga.

Modul ini menggantinya dengan **peringkat persentil**, yang invarian terhadap
jumlah simpul dan bentuk distribusi. Untuk graf 6 simpul maupun 6.000 simpul,
skala yang dikirim selalu terisi penuh dari ujung ke ujung.

Semua nilai di sini adalah presentasi, bukan analisis: bobot komposit adalah
pilihan tampilan, bukan klaim ilmiah. Yang dijaga hanya satu hal — angka yang
sama menghasilkan gambar yang sama, di dataset mana pun.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

# Bobot komposit "prominence". Sama dengan bobot yang dulu ditulis di
# `index.html`, tetapi sekarang bekerja pada peringkat, bukan pada nilai mentah.
SIZE_WEIGHTS = {"degree": 0.45, "volume": 0.35, "betweenness": 0.20}
TIERS = 5
DECIMALS = 4


def _number(value: Any) -> Optional[float]:
    """Angka berhingga, atau None bila tidak terukur."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _order(values: Mapping[str, Optional[float]]) -> list[str]:
    """
    Urutan dari besar ke kecil; yang tidak terukur di belakang; seri diputus id.

    Pemutus seri bukan hiasan: tanpa itu, dua simpul dengan angka identik bisa
    bertukar peringkat antar proses, dan tier-nya ikut berubah.
    """
    def key(item: tuple[str, Optional[float]]) -> tuple[int, float, str]:
        name, raw = item
        number = _number(raw)
        if number is None:
            return (1, 0.0, name)
        return (0, -number, name)

    return [name for name, _ in sorted(values.items(), key=key)]


def _percentile(values: Mapping[str, Optional[float]]) -> Dict[str, float]:
    """Peringkat 0..1; 1.0 untuk yang tertinggi, 0.0 untuk yang terendah."""
    order = _order(values)
    total = len(order)
    if total == 0:
        return {}
    if total == 1:
        return {order[0]: 1.0}
    return {name: (total - 1 - index) / (total - 1) for index, name in enumerate(order)}


def encode(metrics: Mapping[str, Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Blok ukuran per simpul, siap dikirim ke visualizer.

    `radius_tier` 1..5 dipakai untuk label dan legenda; radius piksel dihitung
    UI dari `size_rank` (atau dari salah satu peringkat komponen bila pengguna
    memilih metrik ukuran lain).
    """
    if not metrics:
        return {}

    rank_degree = _percentile({key: row.get("degree") for key, row in metrics.items()})
    rank_volume = _percentile({key: row.get("articles") for key, row in metrics.items()})
    rank_betweenness = _percentile(
        {key: row.get("betweenness") for key, row in metrics.items()}
    )
    # Burt memakai effective size: constraint rendah = otonomi tinggi, dan
    # effective size sudah searah dengan "besar".
    rank_burt = _percentile({key: row.get("effective_size") for key, row in metrics.items()})

    composite = {
        key: (
            SIZE_WEIGHTS["degree"] * rank_degree.get(key, 0.0)
            + SIZE_WEIGHTS["volume"] * rank_volume.get(key, 0.0)
            + SIZE_WEIGHTS["betweenness"] * rank_betweenness.get(key, 0.0)
        )
        for key in metrics
    }

    order = _order(composite)
    total = len(order)
    encoded: Dict[str, Dict[str, Any]] = {}
    for index, name in enumerate(order):
        encoded[name] = {
            "size_rank": round(composite[name], DECIMALS),
            "rank_degree": round(rank_degree.get(name, 0.0), DECIMALS),
            "rank_volume": round(rank_volume.get(name, 0.0), DECIMALS),
            "rank_betweenness": round(rank_betweenness.get(name, 0.0), DECIMALS),
            "rank_burt": round(rank_burt.get(name, 0.0), DECIMALS),
            "radius_tier": min(TIERS, 1 + (index * TIERS) // total),
            "label_priority": index + 1,
        }
    return encoded
