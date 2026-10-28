"""
Sensitivitas ambang backbone.

Pertanyaan yang dijawab: berapa banyak sisi yang bertahan bila ambang digeser?
Tanpa jawaban itu, "graf ini punya 475 sisi" hanya berarti "475 sisi pada ambang
yang kebetulan dipilih", dan pembaca tidak punya cara tahu apakah 474 atau 300
di antaranya akan hilang pada ambang yang sedikit berbeda.

Perhitungan di sini sengaja hanya menjalankan **seleksi edge**, bukan metrik
penuh. Sentralitas, komunitas, dan modularitas tidak dihitung ulang: harganya
jauh lebih mahal dan tidak dibutuhkan untuk menjawab pertanyaan ini.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from ..contract.models import BackboneSettings
from ..core.backbone import BackboneConfig, select_edges
from ..core.build import backbone_config
from ..core.cooccurrence import Cooccurrence, cooccurrence
from ..io.bundle import DataBundle

DEFAULT_POINTS = 12


def _measure(cooc: Cooccurrence, config: BackboneConfig) -> Dict[str, Any]:
    """
    Satu titik pada kurva.

    `passed` dan `rescued` dipisah karena `edges` (jumlahnya) tidak monoton:
    makin tinggi ambang, makin banyak simpul kehilangan seluruh sisinya, dan
    `rescue_isolated` menambahkan kembali sisi terkuat masing-masing. Tanpa
    pemisahan itu kurva terlihat naik-turun seperti kesalahan hitung.
    """
    selected, rescued, _report = select_edges(cooc, config)
    touched = set()
    for position in selected:
        touched.add(int(cooc.pair_u[position]))
        touched.add(int(cooc.pair_v[position]))
    rescued_count = int(sum(1 for flag in rescued if flag))
    return {
        "min_support": config.min_support,
        "min_npmi": round(config.min_npmi, 3),
        # q hidup di skala yang jauh lebih kecil dari NPMI; 3 desimal akan
        # menampilkan 0,0004 sebagai 0,0 — nilai yang bahkan tidak sah.
        "min_q": None if config.min_q is None else round(config.min_q, 6),
        "edges": int(len(selected)),
        "passed": int(len(selected)) - rescued_count,
        "rescued": rescued_count,
        "nodes": len(touched),
        "isolated": max(0, len(cooc.entity_ids) - len(touched)),
    }


def _grid(
    values: Any, points: int, must_include: float, *, integral: bool
) -> List[Any]:
    """
    Grid ambang dari sebaran nilai yang benar-benar ada pada data.

    Batas atas tetap (mis. 20) salah untuk korpus berekor panjang: pada bundle
    nyata support mencapai ribuan, sehingga sapuan 1..20 seluruhnya jatuh di
    wilayah datar dan kurvanya tampak "tidak sensitif" padahal hanya tidak
    terjangkau. Kuartil membuat setiap titik mewakili porsi pasangan yang sama,
    dan batas atas sebenarnya selalu ikut supaya titik keruntuhan terlihat.
    """
    array = np.asarray(list(values), dtype=float)
    if array.size == 0:
        return [round(must_include, 3) if not integral else int(must_include)]
    quantiles = np.linspace(0.0, 1.0, max(2, points))
    raw = [float(np.quantile(array, q)) for q in quantiles]
    raw.append(float(must_include))
    if integral:
        grid: List[Any] = sorted({max(1, int(round(value))) for value in raw})
    else:
        grid = sorted({round(max(0.0, value), 3) for value in raw})
    return grid


def sensitivity(
    bundle: DataBundle,
    *,
    points: int = DEFAULT_POINTS,
    active: Optional[BackboneConfig] = None,
) -> Dict[str, Any]:
    """
    Dua kurva: jumlah sisi terhadap `min_support`, dan terhadap `min_npmi`.

    Keduanya dihitung pada nilai ambang lain yang tetap, karena bidang dua
    dimensi tidak bisa ditampilkan sebagai satu kurva tanpa menyesatkan.
    """
    base = active or backbone_config(bundle)
    cooc = cooccurrence(bundle)

    support_curve = [
        _measure(cooc, BackboneConfig(min_support=value, min_npmi=base.min_npmi,
                                      rescue_isolated=base.rescue_isolated))
        for value in _grid(cooc.support, points, base.min_support, integral=True)
    ]

    npmi_curve = [
        _measure(cooc, BackboneConfig(min_support=base.min_support, min_npmi=value,
                                      rescue_isolated=base.rescue_isolated))
        for value in _grid(cooc.npmi, points, base.min_npmi, integral=False)
    ]

    # Kurva ketiga hanya ada bila q dihitung; ambang q nol tidak sah, jadi
    # grid dijepit ke nilai positif terkecil yang masih bermakna.
    q_curve: List[Dict[str, Any]] = []
    if cooc.q_value is not None:
        # Ambang q nol tidak sah, jadi grid dijepit ke nilai positif terkecil
        # yang masih bermakna; penjepitan bisa menyatukan beberapa titik.
        grid = sorted(
            {max(value, 1e-6)
             for value in _grid(cooc.q_value, points, base.min_q or 0.05, integral=False)}
        )
        q_curve = [
            _measure(
                cooc,
                BackboneConfig(
                    min_support=base.min_support,
                    min_npmi=base.min_npmi,
                    rescue_isolated=base.rescue_isolated,
                    min_q=value,
                ),
            )
            for value in grid
        ]

    return {
        "status": "ready",
        "candidate_pairs": int(cooc.pair_u.shape[0]),
        "active": {
            "min_support": base.min_support,
            "min_npmi": base.min_npmi,
            "min_q": base.min_q,
            "rescue_isolated": base.rescue_isolated,
        },
        "by_support": support_curve,
        "by_npmi": npmi_curve,
        "by_q": q_curve,
    }


def settings_from(block: Optional[Dict[str, Any]]) -> Optional[BackboneSettings]:
    """Validasi blok `manifest.backbone` sebelum dipakai; None bila tidak ada."""
    if not block:
        return None
    return BackboneSettings(**block)
