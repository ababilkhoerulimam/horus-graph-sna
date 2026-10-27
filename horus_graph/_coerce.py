"""
Satu jawaban untuk satu pertanyaan: apakah angka ini ada?

Sebelum modul ini, delapan tempat menjawab pertanyaan yang sama dengan cara
berbeda — ada yang menolak `None` saja, ada yang menolak `NaN`, ada yang tidak
memeriksa `inf`. Perbedaan itu tidak terlihat sampai satu panel menampilkan
`Infinity` sementara panel lain menampilkan `—`.

Aturan yang dipakai di sini, dan karenanya di seluruh engine:

- `None`, `NaN`, `pd.NA`, dan `inf` semuanya berarti **tidak terukur**.
- Tidak terukur dikembalikan sebagai `None`, tidak pernah sebagai `0`.
- List kosong bukan "tidak terukur"; ia nilai yang sah.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd


def is_missing(value: Any) -> bool:
    """True untuk None, NaN, pd.NA, dan NaT. List kosong bukan missing."""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        # pd.isna pada list/array mengembalikan array, bukan bool.
        return False


def to_float(value: Any) -> Optional[float]:
    """Angka berhingga, atau `None` bila nilainya tidak terukur."""
    if is_missing(value):
        return None
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def to_number(value: Any, digits: int) -> Optional[float]:
    """`to_float` yang dibulatkan; pembulatan tidak pernah mengubah `None`."""
    number = to_float(value)
    return None if number is None else round(number, digits)
