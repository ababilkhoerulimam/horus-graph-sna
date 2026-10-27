"""Alat statistik kecil yang dipakai beberapa modul enhance."""

from __future__ import annotations

from typing import Sequence

import numpy as np


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


def adjusted_rand_index(labels_a: Sequence, labels_b: Sequence) -> float:
    """
    Adjusted Rand Index antara dua partisi.

    Nilai 1 berarti partisi identik, 0 berarti setara acak. Dipakai untuk
    mengukur stabilitas komunitas antar resampling: tanpa ARI, "komunitas
    berubah" dan "label komunitas bergeser nomornya" tidak bisa dibedakan.
    """
    a = np.asarray(labels_a)
    b = np.asarray(labels_b)
    if a.shape != b.shape:
        raise ValueError("kedua partisi harus sepanjang sama")
    n = a.size
    if n < 2:
        return 1.0

    _, a_idx = np.unique(a, return_inverse=True)
    _, b_idx = np.unique(b, return_inverse=True)
    contingency = np.zeros((a_idx.max() + 1, b_idx.max() + 1), dtype=np.int64)
    np.add.at(contingency, (a_idx, b_idx), 1)

    def comb2(values: np.ndarray) -> np.ndarray:
        return values * (values - 1) / 2.0

    sum_comb = float(comb2(contingency).sum())
    sum_a = float(comb2(contingency.sum(axis=1)).sum())
    sum_b = float(comb2(contingency.sum(axis=0)).sum())
    total = n * (n - 1) / 2.0

    expected = sum_a * sum_b / total if total else 0.0
    maximum = 0.5 * (sum_a + sum_b)
    if maximum == expected:
        return 1.0
    return (sum_comb - expected) / (maximum - expected)
