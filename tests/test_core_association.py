"""
Asosiasi pasangan: uji signifikansi dan koreksi uji berganda.

Yang dijaga: versi vektor memberi angka yang sama persis dengan versi skalar
(dua jalur untuk pertanyaan yang sama adalah cara termudah membuat laporan
saling bertentangan), dan q-value benar-benar hasil koreksi Benjamini-Hochberg
— bukan p-value yang diganti namanya.
"""

from __future__ import annotations

import numpy as np
import pytest

from horus_graph.core import association

CASES = (
    # (support, cu, cv, total)
    (3, 10, 12, 50),
    (1, 2, 3, 5),
    (40, 40, 45, 100),
    (10, 10, 50, 100),
    (0, 4, 5, 10),
    (5, 5, 5, 5),
)


def test_vektor_sama_dengan_skalar() -> None:
    for support, cu, cv, total in CASES:
        expected = association.hypergeometric_p(support, total, cu, cv)
        values = association.hypergeometric_p_array(
            np.array([support]), np.array([cu]), np.array([cv]), total
        )
        assert values[0] == pytest.approx(expected, abs=1e-12), (support, cu, cv, total)


def test_vektor_tanpa_pasangan_valid_mengembalikan_satu() -> None:
    values = association.hypergeometric_p_array(
        np.array([0, 0]), np.array([0, 4]), np.array([5, 0]), 10
    )

    assert np.array_equal(values, np.ones(2))


def test_benjamini_hochberg_jawaban_acuan() -> None:
    # p = 0,01 / 0,02 / 0,03 masing-masing tepat di garis 0,04; 0,5 tetap.
    q = association.benjamini_hochberg([0.01, 0.02, 0.03, 0.5])

    assert q == pytest.approx([0.04, 0.04, 0.04, 0.5])


def test_benjamini_hochberg_memakai_kumulatif_minimum() -> None:
    # p = 0,04 di peringkat 3 memberi 0,0533; peringkat 2 di bawahnya tidak
    # boleh naik melewatinya, dan q tidak pernah turun saat p naik.
    q = association.benjamini_hochberg([0.01, 0.04, 0.03, 0.5])

    assert q == pytest.approx([0.04, 0.0533, 0.0533, 0.5], abs=1e-4)


def test_q_tidak_pernah_di_bawah_p() -> None:
    p_values = [0.001, 0.02, 0.2, 0.9, 0.5]
    q_values = association.benjamini_hochberg(p_values)

    assert all(q >= p for p, q in zip(p_values, q_values, strict=True))
    assert all(q <= 1.0 for q in q_values)


def test_q_mengikuti_urutan_masukan() -> None:
    p_values = [0.5, 0.01, 0.3]
    q_values = association.benjamini_hochberg(p_values)

    assert q_values[1] < q_values[2] < q_values[0]


def test_benjamini_hochberg_kosong() -> None:
    assert association.benjamini_hochberg([]) == []
