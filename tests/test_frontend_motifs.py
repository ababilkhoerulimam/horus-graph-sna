"""
Motif lokal (sensus triad + rich-club) di visualizer.

Yang dijaga di sini, sama seperti panel komunitas:

1. Angka dibaca dari payload (`graph.motifs`), tidak dihitung ulang di browser.
2. Nilai yang tidak ada (`null`) tidak pernah tampil sebagai angka. Triad yang
   tidak bisa dihitung pada graf kecil tidak boleh terbaca sebagai 0%.
3. Rich-club hanya tampil bila artefaknya ada dan punya puncak. Kurva mentah
   naik secara konstruksi, jadi angka tanpa pembanding acak tidak dikirim.
4. Alasan ketiadaan diteruskan apa adanya dari engine, bukan dikosongkan.
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


def _panel(markup: str) -> str:
    index = markup.find('document.getElementById("motif-body")')
    assert index != -1, "panel motif tidak ditemukan"
    end = markup.find("// Disclosure korpus", index)
    assert end != -1, "batas akhir panel motif tidak ditemukan"
    return markup[index:end]


def test_metadata_membawa_blok_motif(markup: str) -> None:
    assert "motifs: payload.graph.motifs || null" in markup


def test_panel_membaca_motif_dari_payload(markup: str) -> None:
    panel = _panel(markup)
    # Nilai datang dari metadata, bukan dihitung ulang di browser.
    assert "meta.motifs" in panel
    assert "motifBlock.triads" in panel
    assert "motifBlock.rich_club" in panel


def test_closed_share_kosong_tidak_menjadi_nol(markup: str) -> None:
    """`null` harus jadi tanda kosong, bukan 0,0%."""
    panel = _panel(markup)
    assert "triads.closed_share === null" in panel
    assert "triads.closed_share === undefined" in panel
    assert '"—"' in panel
    # Tidak ada koersi diam-diam ke nol di blok ini.
    assert "|| 0" not in panel
    assert "?? 0" not in panel


def test_triad_belum_dihitung_dikatakan(markup: str) -> None:
    panel = _panel(markup)
    assert 'triads.status === "ready"' in panel
    assert "tidak diukur" in panel
    # Alasan dari engine diteruskan apa adanya.
    assert "triads.reason" in panel


def test_rich_club_hanya_bila_ada_puncak(markup: str) -> None:
    """Kurva mentah naik secara konstruksi; tanpa puncak ternormalisasi, tidak ada angka."""
    panel = _panel(markup)
    assert 'club.status === "ready" && club.peak' in panel
    assert "club.peak.ratio" in panel
    assert "club.peak.degree" in panel
    assert "club.replicates" in panel


def test_rich_club_belum_dihitung_menyebut_perintah(markup: str) -> None:
    panel = _panel(markup)
    assert "tidak diukur" in panel
    assert "club.reason" in panel
    assert "motifs --write" in panel


def test_ambang_terpotong_disebut(markup: str) -> None:
    """Derajat tertinggi yang subgrafnya terlalu kecil harus diakui, bukan disembunyikan."""
    panel = _panel(markup)
    assert "club.truncated_degrees" in panel
    assert "dipotong" in panel

def test_teks_engine_masuk_sebagai_teks(markup: str) -> None:
    """Alasan engine menyebut <bundle>; innerHTML akan menelannya sebagai tag."""
    panel = _panel(markup)
    assert "createTextNode(" in panel
    # Tidak ada template HTML untuk teks dinamis: label dibuat via createElement.
    assert "<strong>" not in panel
