"""
Pagar skala visual dan tautan tampilan.

Dua janji yang dijaga di sini:

1. Tidak ada lagi konstanta yang hanya benar untuk satu dataset. Angka seperti
   `(deg - 11) / (47 - 11)` membuat dataset kedua tampil "wajar" padahal seluruh
   simpulnya jatuh ke kelas bawah — gagal tanpa error.
2. Tautan menyimpan keadaan tampilan, dan token tidak pernah ikut ke dalamnya.
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


def _badan(markup: str, nama: str, panjang: int = 1600) -> str:
    """Potongan teks mulai dari definisi fungsi sampai `panjang` karakter."""
    index = markup.find(f"function {nama}(")
    assert index != -1, f"fungsi {nama} tidak ditemukan"
    return markup[index : index + panjang]


def test_tidak_ada_konstanta_skala_milik_satu_dataset(markup: str) -> None:
    for literal in ("47 - 11", "/ 0.04", "3.85", "2.2) /"):
        assert literal not in markup, f"konstanta skala lama masih ada: {literal}"


def test_prominence_lama_sudah_hilang(markup: str) -> None:
    assert "assignNodeProminence" not in markup
    assert "prominence_tier" not in markup


def test_hanya_satu_fungsi_radius(markup: str) -> None:
    assert markup.count("function computeNodeRadius(") == 1


def test_radius_membaca_peringkat_dari_payload(markup: str) -> None:
    badan = _badan(markup, "computeNodeRadius", 400)
    assert "sizeRank(d)" in badan
    # Skala tunggal: satu rentang untuk semua metrik ukuran.
    assert "RADIUS_MIN" in badan and "RADIUS_MAX" in badan


def test_setiap_metrik_ukuran_menunjuk_ke_peringkat(markup: str) -> None:
    blok = markup[markup.find("const SIZE_RANK_FIELDS") : markup.find("const SIZE_RANK_FIELDS") + 400]
    for field in ("rank_degree", "rank_betweenness", "rank_burt", "rank_volume"):
        assert field in blok, f"metrik {field} tidak dipetakan"


def test_label_dibatasi_oleh_peringkat(markup: str) -> None:
    assert "function labelBudget(" in markup
    assert "label_priority <= labelBudget()" in markup
    # is_anchor adalah penanda data, bukan gerbang label: kalau ia ikut menentukan,
    # dataset yang semua simpulnya anchor membanjiri kanvas melewati anggaran.
    assert "isAnchorNode" not in markup
    assert "isAnchor ||" not in markup
    # Label yang bertabrakan disembunyikan, bukan ditumpuk.
    assert "function applyLabelBudget(" in markup
    assert "getBoundingClientRect()" in _badan(markup, "applyLabelBudget", 1200)


def test_tautan_menyimpan_keadaan_tampilan(markup: str) -> None:
    assert "VIEW_HASH_VERSION" in markup
    assert "function readViewState(" in markup
    assert "function applyViewState(" in markup
    # Diterapkan setelah tata letak selesai, bukan saat markup baru dimuat:
    # mode topik butuh render bipartit yang belum siap lebih awal.
    assert "pendingViewState = readViewState()" in markup
    assert "flushViewState()" in markup
    assert "if (!viewStateFlushed) resetGraphView();" in markup
    # Hash diperbarui otomatis setelah interaksi, bukan hanya saat boot.
    assert "syncViewStateToHash()" in markup


def test_field_tautan_dibatasi_daftar_pilihan(markup: str) -> None:
    blok = markup[markup.find("const VIEW_CHOICES") : markup.find("const VIEW_CHOICES") + 400]
    for kunci in ('m:', 'c:', 'k:'):
        assert kunci in blok
    assert "actor_network" in blok and "narrative_temporal" in blok
    # Nilai asing diabaikan: tanpa ini, hash rusak menghasilkan layar rusak.
    assert "indexOf(value) !== -1" in _badan(markup, "readViewState", 900)


def test_token_tidak_pernah_masuk_hash(markup: str) -> None:
    badan = _badan(markup, "viewStateHash", 1200)
    assert "token" not in badan.lower()
    assert 'params.set("token"' not in markup


def test_token_tidak_menghapus_hash_saat_dibersihkan(markup: str) -> None:
    """Skrip token di kepala halaman memakai replaceState; hash harus ikut."""
    baris = [
        line
        for line in markup.splitlines()
        if "replaceState" in line and "location.pathname" in line
    ]
    assert baris, "replaceState untuk token tidak ditemukan"
    assert any("location.hash" in line for line in baris)
