"""
Panel sensitivitas ambang di visualizer.

Yang dijaga: kurva ini harus bisa dibaca sebagai "seberapa rapuh jumlah sisi
ini", bukan sebagai hiasan. Karena itu tiga hal diuji di sumber:

1. Panel membaca endpoint yang sama dengan yang dipakai CLI, bukan angka
   yang ditanam di markup.
2. Ambang aktif ditandai, dan penanda itu hanya muncul bila nilainya memang
   ada pada kurva — penanda hasil interpolasi akan berbohong tentang posisi.
3. Kegagalan memuat tampil sebagai tanda kosong, bukan "0 sisi".
"""

from __future__ import annotations

from pathlib import Path

import frontend_source
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC = REPO_ROOT / "horus_graph" / "web" / "static"


@pytest.fixture(scope="module")
def markup() -> str:
    return frontend_source.source()


def _badan(markup: str, nama: str, panjang: int = 2000) -> str:
    index = markup.find(f"function {nama}(")
    assert index != -1, f"fungsi {nama} tidak ditemukan"
    return markup[index : index + panjang]


def test_panel_ada_dan_memakai_endpoint_sensitivitas(markup: str) -> None:
    assert 'id="sensitivity-body"' in markup
    assert "function loadSensitivity(" in markup
    assert "/api/analysis/sensitivity" in markup


def test_kurva_tidak_menanam_angka_hasil(markup: str) -> None:
    """Panel kosong sampai endpoint menjawab."""
    blok = markup[markup.find('id="sensitivity-body"') :][:400]
    assert "Memuat" in blok or "dimuat" in blok
    # Tidak ada jumlah sisi yang ditulis mati di markup.
    assert "sisi</strong>" not in blok


def test_penanda_ambang_aktif_hanya_bila_nilainya_ada(markup: str) -> None:
    badan = _badan(markup, "sensitivityChart", 2400)
    assert "points.some(" in badan
    assert "Number(activeValue)" in badan
    # Garis putus-putus untuk total, garis penuh untuk yang lolos ambang:
    # tanpa pemisahan itu kurva naik-turun terbaca seperti salah hitung.
    assert 'line("edges")' in badan and 'line("passed")' in badan
    assert "stroke-dasharray=\"3,3\"" in badan


def test_legenda_menjelaskan_dua_garis(markup: str) -> None:
    badan = _badan(markup, "renderSensitivity", 2200)
    assert "lolos ambang" in badan
    assert "diselamatkan" in badan


def test_kegagalan_tampil_sebagai_tanda_kosong(markup: str) -> None:
    badan = _badan(markup, "loadSensitivity", 1400)
    assert "gagal dimuat" in badan
    assert "\\u2014" in badan


def test_jawaban_basi_tidak_menimpa_yang_baru(markup: str) -> None:
    badan = _badan(markup, "loadSensitivity", 1400)
    assert "sensitivityRequest" in badan
    assert badan.count("ticket !== sensitivityRequest") >= 2
