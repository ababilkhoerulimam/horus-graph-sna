"""
Panel catatan analis dan tombol laporan di visualizer.

Dua hal yang mudah salah tanpa terlihat: catatan ditulis lewat `innerHTML`
(isi catatan adalah masukan manusia), dan "belum ada catatan" ditampilkan
sebelum daftarnya benar-benar dimuat.
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


def test_panel_catatan_ada_di_drawer(markup: str) -> None:
    assert 'id="drawer-note-list"' in markup
    assert 'id="drawer-note-input"' in markup
    assert 'id="btn-save-note"' in markup


def test_catatan_ditulis_lewat_textcontent(markup: str) -> None:
    badan = _badan(markup, "renderNodeNotes", 2600)
    assert "text.textContent = item.text" in badan
    # Tidak ada jalur yang menyisipkan teks catatan sebagai HTML.
    assert "innerHTML = item.text" not in markup


def test_belum_dimuat_bukan_berarti_kosong(markup: str) -> None:
    badan = _badan(markup, "renderNodeNotes", 2600)
    assert "ANNOTATIONS === null" in badan
    assert "Memuat catatan" in badan


def test_catatan_menempel_pada_simpul_yang_dipilih(markup: str) -> None:
    assert "currentNoteTarget = d.id" in markup
    badan = _badan(markup, "saveNote", 1400)
    assert "target_id: currentNoteTarget" in badan


def test_hapus_memakai_id_catatan(markup: str) -> None:
    badan = _badan(markup, "deleteNote", 700)
    assert "DELETE" in badan
    assert "encodeURIComponent(annotationId)" in badan


def test_tombol_laporan_mengirim_svg_kanvas(markup: str) -> None:
    assert 'id="btn-export-report"' in markup
    blok = markup[markup.find('id="btn-export-report"') :][:600]
    assert "Laporan HTML" in blok
    badan = markup[markup.find("btnExportReport.addEventListener") :][:1600]
    assert 'fetch("/api/report"' in badan
    assert "serializeToString" in badan
    assert "network-svg" in badan


def test_laporan_tidak_dibuat_di_klien(markup: str) -> None:
    """Provenance harus datang dari server, bukan disusun ulang di JS."""
    assert "limitations" not in _badan(markup, "loadAnnotations", 900)
