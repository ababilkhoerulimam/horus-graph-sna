"""Satu aturan untuk satu pertanyaan: apakah angka ini terukur?"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from horus_graph._coerce import is_missing, to_float, to_number


@pytest.mark.parametrize("nilai", [None, float("nan"), pd.NA, pd.NaT])
def test_nilai_hilang_dikenali(nilai: object) -> None:
    assert is_missing(nilai) is True


def test_nol_bukan_nilai_hilang() -> None:
    """Nol adalah hasil ukur yang sah; membedakannya dari None adalah inti modul ini."""
    assert is_missing(0) is False
    assert to_float(0) == 0.0
    assert to_number(0, 4) == 0.0


def test_list_kosong_bukan_nilai_hilang() -> None:
    assert is_missing([]) is False


@pytest.mark.parametrize("nilai", [None, float("nan"), float("inf"), float("-inf"), pd.NA])
def test_tak_terukur_jadi_none(nilai: object) -> None:
    assert to_float(nilai) is None
    assert to_number(nilai, 4) is None


def test_pembulatan_tidak_mengubah_none() -> None:
    assert to_number(None, 6) is None
    assert to_number(1.23456789, 4) == 1.2346


def test_angka_berhingga_dilewatkan() -> None:
    assert to_float("2.5") == 2.5
    assert math.isfinite(to_float(3) or 0.0)
