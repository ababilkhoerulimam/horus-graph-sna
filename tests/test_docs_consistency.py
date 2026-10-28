"""
Angka di dokumen harus berasal dari repo, bukan dari ingatan.

Klaim ukuran berkas cepat basi: satu berkas tumbuh, dokumennya tetap. Pembaca
lalu memakai angka yang salah tanpa ada yang tahu. Tes ini membaca angka dari
dokumen, menghitung ulang dari repo, dan gagal bila keduanya berbeda — jadi
dokumen yang tertinggal membuat suite merah, bukan pembaca yang salah paham.

Yang dijaga hanya klaim yang stabil: ukuran berkas. Jumlah tes dan jumlah
modul tidak dijaga karena berubah setiap commit; keduanya cukup disebut tanpa
angka.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "horus_graph" / "web" / "static"
DOC = REPO / "docs" / "planning" / "IMPROVEMENTS.md"


def _dokumen() -> str:
    return DOC.read_text(encoding="utf-8")


def _baris(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _ribuan(jumlah: int) -> str:
    """Pemisah ribuan dokumen memakai titik: 2.269, bukan 2,269."""
    return f"{jumlah:,}".replace(",", ".")


def test_ukuran_encoding_sama_dengan_berkas() -> None:
    ukuran = _baris(REPO / "horus_graph" / "api" / "encoding.py")

    assert f"encoding.py` ({ukuran} baris)" in _dokumen()


def test_ukuran_index_html_sama_dengan_berkas() -> None:
    ukuran = _baris(STATIC / "index.html")

    assert f"→ {ukuran} baris (batas 1.500)" in _dokumen()
    assert ukuran < 1500


def test_ukuran_css_sama_dengan_berkas() -> None:
    dokumen = _dokumen()

    for nama in ("app.css", "copilot.css"):
        ukuran = _baris(STATIC / "css" / nama)
        assert f"`css/{nama}` ({_ribuan(ukuran)})" in dokumen, f"{nama} tidak cocok"


def test_berkas_skrip_terbesar_disebut_dengan_benar() -> None:
    ukuran = {path.name: _baris(path) for path in (STATIC / "js").glob("app_*.js")}
    terbesar = max(ukuran, key=lambda nama: ukuran[nama])

    assert f"`{terbesar}` {ukuran[terbesar]} baris" in _dokumen()
    assert ukuran[terbesar] < 800


def test_tidak_ada_rujukan_baris_index_html_yang_mati() -> None:
    """
    index.html sekarang 923 baris; rujukan seperti baris 3766 menunjuk baris
    yang tidak ada lagi dan membuat pembaca membuka tempat yang salah.
    """
    panjang = _baris(STATIC / "index.html")
    mati = [
        temuan.group(0)
        for temuan in re.finditer(r"index\.html:(\d+)", _dokumen())
        if int(temuan.group(1)) > panjang
    ]

    assert mati == [], f"rujukan baris mati: {mati}"

def test_css_drawer_ikut_dibaca_tes_frontend() -> None:
    """Tanpa copilot.css, pagar aksesibilitas hanya memeriksa separuh tampilan."""
    import frontend_source

    assert "css/app.css" in frontend_source.STYLES
    assert "css/copilot.css" in frontend_source.STYLES
