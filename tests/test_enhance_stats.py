"""Alat statistik: ARI, p-value empiris, dan z-score."""

from __future__ import annotations

import numpy as np
import pytest

from horus_graph.enhance.stats import (
    adjusted_rand_index,
    empirical_p_value,
    percentile_interval,
    two_sided_p_value,
    z_score,
)


def test_ari_partisi_identik_satu():
    assert adjusted_rand_index([1, 1, 2, 2], [5, 5, 9, 9]) == pytest.approx(1.0)


def test_ari_partisi_acak_mendekati_nol():
    rng = np.random.default_rng(0)
    left = rng.integers(0, 3, 500)
    right = rng.integers(0, 3, 500)
    assert abs(adjusted_rand_index(left, right)) < 0.05


def test_ari_partisi_terpisah_total_negatif():
    assert adjusted_rand_index([0, 0, 1, 1], [0, 1, 0, 1]) < 0


def test_ari_panjang_berbeda_ditolak():
    with pytest.raises(ValueError):
        adjusted_rand_index([0, 1], [0, 1, 1])


def test_p_value_empiris_memakai_koreksi_satu():
    null = [1.0, 2.0, 3.0, 4.0]
    assert empirical_p_value(10.0, null) == pytest.approx(1 / 5)
    assert empirical_p_value(0.0, null, tail="lower") == pytest.approx(1 / 5)


def test_p_value_dua_sisi_dibatasi_satu():
    null = list(np.linspace(0, 1, 50))
    assert two_sided_p_value(0.5, null) <= 1.0


def test_z_score_nol_saat_simpangan_nol():
    assert np.isnan(z_score(5.0, [3.0, 3.0, 3.0]))


def test_interval_persentil():
    low, high = percentile_interval(list(range(101)), 5, 95)
    assert (low, high) == (5.0, 95.0)
