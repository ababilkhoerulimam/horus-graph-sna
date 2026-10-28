"""
Pengelompokan artikel sindikasi.

Satu rilis yang dimuat banyak portal adalah satu peristiwa, bukan banyak
dukungan. Kalau setiap salinan dihitung, `support` mengukur jumlah portal yang
menyalin, bukan kedekatan dua entitas — dan NPMI-nya ikut naik tanpa asosiasi
yang lebih nyata.

Engine tidak menebak kelompok: ia membaca kolom `dedupe_group` yang diisi
pipeline ingest. Tanpa kolom itu, atau bila seluruhnya kosong, setiap artikel
berdiri sendiri dan hasilnya identik dengan sebelum fitur ini ada.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from ..io.bundle import DataBundle

GROUP_COLUMN = "dedupe_group"


def _missing(value: object) -> bool:
    """True untuk None, NaN, dan string kosong — semuanya berarti tanpa grup."""
    if value is None:
        return True
    if isinstance(value, float) and np.isnan(value):
        return True
    return isinstance(value, str) and not value.strip()


def article_groups(bundle: DataBundle) -> Optional[np.ndarray]:
    """
    Posisi grup untuk setiap baris artikel, atau `None` bila tak ada grup.

    Artikel tanpa grup mendapat kunci sendiri, jadi ia tetap dihitung satu
    kali. Nilai kembalian `None` penting: pemanggil bisa membedakan
    "tidak ada dedup" dari "dedup yang kebetulan tidak menggabungkan apa pun".
    """
    articles = bundle.articles
    if GROUP_COLUMN not in articles.columns:
        return None
    values = articles[GROUP_COLUMN].tolist()
    if all(_missing(value) for value in values):
        return None

    positions = np.empty(len(values), dtype=np.int64)
    mapping: Dict[str, int] = {}
    for index, value in enumerate(values):
        # `str(nan)` menjadi "nan" dan akan menyatukan semua artikel tanpa
        # label menjadi satu grup — persis kebalikan dari yang diinginkan.
        key = "" if _missing(value) else str(value).strip()
        key = key or f"\x00{index}"
        positions[index] = mapping.setdefault(key, len(mapping))

    if len(mapping) == len(values):
        return None
    return positions


def summarise(bundle: DataBundle, positions: Optional[np.ndarray]) -> Dict[str, Any]:
    """Angka yang harus ikut dilaporkan supaya denominator bisa dibandingkan."""
    articles = len(bundle.articles)
    groups = articles if positions is None else int(positions.max()) + 1
    return {
        "applied": positions is not None,
        "articles": articles,
        "groups": groups,
        "collapsed": articles - groups,
    }

