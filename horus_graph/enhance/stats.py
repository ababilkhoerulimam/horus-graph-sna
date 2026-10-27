"""Alat statistik kecil yang dipakai beberapa modul enhance."""

from __future__ import annotations

from typing import Sequence

import numpy as np

# ARI hidup di `core` karena dipakai juga oleh partisi konsensus, yang tidak
# boleh bergantung pada lapisan `enhance`. Nama lama tetap diekspor di sini
# supaya pemanggil `stats.adjusted_rand_index` tidak berubah.
from ..core.metrics.agreement import adjusted_rand_index as adjusted_rand_index


def empirical_p_value(observed: float, null: Sequence[float], tail: str = "upper") -> float:
    """
    p-value empiris dengan koreksi +1.

    Tanpa +1, 200 resampling tidak akan pernah menghasilkan p < 0.005, dan
    nilai 0.0 terbaca seolah mustahil — padahal itu batas resolusi, bukan hasil.
    """
    values = np.asarray(null, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0 or not np.isfinite(observed):
        # Metrik tak terdefinisi tidak bisa dibandingkan dengan apa pun; jangan
        # sampai NaN berubah menjadi p kecil hanya karena semua perbandingan False.
        return 1.0
    if tail == "upper":
        hits = int((values >= observed).sum())
    elif tail == "lower":
        hits = int((values <= observed).sum())
    else:
        raise ValueError("tail harus 'upper' atau 'lower'")
    return (hits + 1) / (values.size + 1)


def two_sided_p_value(observed: float, null: Sequence[float]) -> float:
    upper = empirical_p_value(observed, null, "upper")
    lower = empirical_p_value(observed, null, "lower")
    return min(1.0, 2.0 * min(upper, lower))


def z_score(observed: float, null: Sequence[float]) -> float:
    values = np.asarray(null, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return float("nan")
    sd = float(values.std(ddof=1))
    if sd == 0:
        return float("nan")
    return (observed - float(values.mean())) / sd


def percentile_interval(values: Sequence[float], low: float = 5.0, high: float = 95.0):
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data)]
    if data.size == 0:
        return (float("nan"), float("nan"))
    return (float(np.percentile(data, low)), float(np.percentile(data, high)))
