"""
Stabilitas komunitas di visualizer.

Angka stabilitas hanya berguna kalau ia terbaca di tempat orang melihat
komunitas. Yang dijaga di sini:

1. Nilainya dibaca dari payload (`community_stability`), tidak dihitung ulang
   di browser — dua tempat menghitung satu angka adalah cara termudah membuat
   panel dan laporan berbeda.
2. `null` tidak pernah tampil sebagai "1,00" atau "0,00"; simpul tanpa rekan
   komunitas memang tidak punya angka.
3. Bila stabilitas belum dihitung, panel mengatakannya alih-alih menampilkan
   "tidak ada simpul batas" yang terbaca seperti hasil ukur.
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


def test_metadata_membawa_blok_konsensus(markup: str) -> None:
    assert "consensus: payload.graph.consensus || null" in markup


def test_drawer_membaca_stabilitas_dari_payload(markup: str) -> None:
    blok = markup[markup.find('id="drawer-cluster-meta"') :][:200]
    assert "drawer-cluster-meta" in blok
    # Nilai dibaca dari simpul, bukan dihitung ulang dari tetangga.
    assert "d.community_stability" in markup
    assert "typeof d.community_stability === \"number\"" in markup


def test_stabilitas_kosong_tidak_menjadi_angka(markup: str) -> None:
    """`null` harus hilang dari teks, bukan menjadi 0,00."""
    index = markup.find("const stab = (typeof d.community_stability")
    assert index != -1
    blok = markup[index : index + 260]
    assert "toFixed(2)" in blok
    assert "|| 0" not in blok
    assert "?? 0" not in blok


def test_judul_komunitas_menyebut_stabilitas_median(markup: str) -> None:
    badan = _badan(markup, "renderArtifactFacts", 6600)
    assert "stabilitas median" in badan
    assert "consensus.stability_median" in badan


def test_panel_komunitas_menandai_simpul_batas(markup: str) -> None:
    badan = _badan(markup, "renderArtifactFacts", 6600)
    assert "Simpul batas" in badan
    assert "consensus.unstable_count" in badan
    assert "consensus.runs" in badan


def test_belum_dihitung_dikatakan_bukan_dikosongkan(markup: str) -> None:
    badan = _badan(markup, "renderArtifactFacts", 6600)
    assert 'consensus.status !== "ready"' in badan
    assert "belum dihitung" in badan
    # Alasan dari engine diteruskan apa adanya.
    assert "consensus.reason" in badan
