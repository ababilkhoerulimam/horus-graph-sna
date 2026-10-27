"""
Stance: satu angka, satu rumus.

Sebelum modul ini ada empat tempat menghitung stance dengan dua penyebut
berbeda — tiga memakai `/ 100.0` dan satu memakai `/ (pos + neu + neg)`. Untuk
baris yang jumlahnya tepat 100 keduanya sama, tetapi validasi hanya menuntut
jumlah dalam toleransi, sehingga baris 99.7 menghasilkan dua angka berbeda dari
dua panel yang seharusnya menampilkan hal yang sama.

Penyebut yang dipakai di sini adalah jumlah skor baris itu sendiri, bukan
konstanta 100: rumusnya jadi benar untuk skala apa pun, dan `None` muncul ketika
totalnya nol — bukan pembagian dengan nol.
"""

from __future__ import annotations

from typing import Any, Optional

from .._coerce import to_float

STANCE_DECIMALS = 4


def stance_of(pos: Any, neu: Any, neg: Any) -> Optional[float]:
    """
    (positif - negatif) / total, dalam rentang -1..1.

    `None` bila salah satu komponen tidak terukur atau totalnya nol: stance dari
    baris tanpa data bukan "netral", melainkan tidak diketahui.
    """
    p, n, g = to_float(pos), to_float(neu), to_float(neg)
    if p is None or n is None or g is None:
        return None
    total = p + n + g
    if total <= 0:
        return None
    return round((p - g) / total, STANCE_DECIMALS)
