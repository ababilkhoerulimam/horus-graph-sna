"""
Kesepakatan antar partisi.

Partisi komunitas tidak punya nomor yang bisa dibandingkan: "komunitas 2"
pada satu jalankan belum tentu komunitas yang sama pada jalankan berikutnya.
Satu-satunya cara mengukur kesamaan dua partisi adalah menghitung berapa banyak
pasangan simpul yang dipisah atau digabung secara sama, lalu mengoreksi angka
itu dengan peluang kesepakatan acak. Itulah Adjusted Rand Index.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


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
