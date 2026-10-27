"""
Tabel diff epos di visualizer.

Yang dijaga: tabel ini menjawab "siapa naik", jadi angka yang tidak punya dua
pengukuran tidak boleh tampil sebagai nol, dan label komunitas tidak boleh
dibandingkan mentah-mentah — penomorannya berubah antar jalankan Louvain.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC = REPO_ROOT / "horus_graph" / "web" / "static"


@pytest.fixture(scope="module")
def markup() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


def _badan(markup: str, nama: str, panjang: int = 2600) -> str:
    index = markup.find(f"function {nama}(")
    assert index != -1, f"fungsi {nama} tidak ditemukan"
    return markup[index : index + panjang]


def test_modal_dan_renderer_ada(markup: str) -> None:
    assert 'id="modal-epoch-diff"' in markup
    assert 'id="epoch-diff-body"' in markup
    assert "function renderEpochDiff(" in markup


def test_delta_kosong_bukan_nol(markup: str) -> None:
    badan = _badan(markup, "deltaText", 500)
    assert "\\u2014" in badan
    # Nilai nol tetap ditulis "0.0000", bukan dianggap kosong.
    assert "toFixed" in badan


def test_komunitas_dibaca_lewat_penanda_pindah(markup: str) -> None:
    badan = _badan(markup, "communityCell", 900)
    assert "community_shifted" in badan
    # Tidak ada pengurangan label komunitas: penomorannya tidak bermakna.
    assert "delta_community" not in markup


def test_tabel_memuat_dua_arah_dan_sisi(markup: str) -> None:
    badan = _badan(markup, "renderEpochDiff", 2600)
    assert "top_gainers" in badan and "top_losers" in badan
    assert "edges_gained" in badan and "edges_lost" in badan
    assert "community_agreement" in badan


def test_tombol_diff_tidak_membuka_panel_kosong(markup: str) -> None:
    blok = markup[markup.find('id="btn-show-diff"') :][:200]
    assert "Lihat Diff" in blok
    assert 'dataset.filled === "1"' in markup


def test_label_simpul_dipakai_bukan_id(markup: str) -> None:
    assert "function entityLabel(" in markup
    badan = _badan(markup, "epochTable", 1800)
    assert "entityLabel(row.id)" in badan
