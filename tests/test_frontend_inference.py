"""
Panel uji statistik di visualizer.

Aturan yang dijaga sama dengan premis repo, tetapi di sini paling mudah
dilanggar: p-value adalah angka yang paling ingin dilihat orang, jadi paling
mudah juga ditampilkan sebelum ada uji yang berjalan.
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


def _badan(markup: str, nama: str, panjang: int = 2600) -> str:
    index = markup.find(f"function {nama}(")
    assert index != -1, f"fungsi {nama} tidak ditemukan"
    return markup[index : index + panjang]


def test_panel_ada_dan_memakai_endpoint_inferensi(markup: str) -> None:
    assert 'id="inference-body"' in markup
    assert "function loadInference(" in markup
    assert 'fetch("/api/inference")' in markup


def test_panel_kosong_sampai_uji_selesai(markup: str) -> None:
    blok = markup[markup.find('id="inference-body"') :][:400]
    assert "Status uji" in blok or "dimuat" in blok


def test_p_value_tidak_pernah_ditulis_nol(markup: str) -> None:
    badan = _badan(markup, "pValueText", 900)
    # Nilai di bawah batas resolusi ditulis sebagai pertidaksamaan (<=).
    assert "\\u2264" in badan
    assert "floor" in badan
    # Tidak ada jalan yang mengembalikan "0" sebagai hasil uji.
    assert '"p = 0"' not in badan


def test_resolusi_ditampilkan_bersama_p_value(markup: str) -> None:
    badan = _badan(markup, "renderInference", 2600)
    assert "p_value_resolution" in badan
    assert "Resolusi uji" in badan


def test_metrik_tak_terdefinisi_ditulis_tidak_teruji(markup: str) -> None:
    badan = _badan(markup, "pValueText", 900)
    assert "tidak teruji" in badan


def test_status_computing_bukan_angka(markup: str) -> None:
    badan = _badan(markup, "renderInference", 2600)
    assert 'data.status === "computing"' in badan
    assert "latar belakang" in badan


def test_pemantauan_berhenti_saat_panel_ditutup(markup: str) -> None:
    assert "function stopInferencePoll(" in markup
    assert "INFERENCE_POLL_LIMIT" in markup
    # Penutupan modal menghentikan pemantauan.
    assert markup.count("stopInferencePoll()") >= 3


def test_pemantauan_tidak_tak_terbatas(markup: str) -> None:
    badan = _badan(markup, "loadInference", 1400)
    assert "INFERENCE_POLL_LIMIT" in badan
