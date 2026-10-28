"""
Pagar integritas frontend.

Premis repo: yang belum diukur tampil kosong, bukan angka netral. Engine sudah
memegang aturan itu, tetapi berkas visualizer adalah JavaScript bebas yang tidak
punya tipe: satu `|| 0.5` cukup untuk mengubah "belum ada data" menjadi "hasil
ukur 0,5" tanpa ada tes Python yang gagal.

Berkas ini menutup celah itu dengan memeriksa teks sumber. Aturannya sengaja
berbasis pola, bukan berbasis pemahaman semantik: yang dijaga adalah bentuk
kesalahan yang sudah pernah terjadi di repo ini.
"""

from __future__ import annotations

import re
from pathlib import Path

import frontend_source
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC = REPO_ROOT / "horus_graph" / "web" / "static"

# Berkas tampilan yang boleh memuat angka: markup, logika visualizer, jembatan
# copilot. Pustaka pihak ketiga (d3) dikecualikan karena bukan kode kita dan
# sudah diminifikasi, sehingga pola di atas tidak bermakna di dalamnya.
VENDORED = {"d3.v7.min.js"}
FRONTEND_FILES = [
    path
    for path in [STATIC / "index.html", *sorted((STATIC / "js").glob("*.js"))]
    if path.name not in VENDORED
]

# Ternary yang memakai angka sebagai cabang "tidak ada data". Bentuk inilah yang
# dulu menghasilkan Pos 14% / Neu 83% / Neg 3% pada bundle tanpa lapisan
# sentimen.
NUMERIC_TERNARY = re.compile(r"!==\s*(?:undefined|null)\s*\?[^:\n]*:\s*[\"']?-?\d")

# Bentuk cerminnya: `x === null ? 0 : x`. Ini yang membuat simpul tanpa
# komunitas masuk ke komunitas 0.
NUMERIC_TERNARY_REVERSED = re.compile(r"===\s*(?:undefined|null)\s*\?\s*[\"']?-?\d")

# `|| <angka>` dan `?? <angka>` pada baris yang menulis ke layar. Penulisan ke
# layar dikenali dari beberapa bentuk, karena `textContent` bukan satu-satunya
# jalan: `innerText`, `insertAdjacentHTML`, dan `setAttribute` juga menulis.
NUMERIC_OR = re.compile(r"\|\|\s*-?\d+(?:\.\d+)?\b")
NUMERIC_NULLISH = re.compile(r"\?\?\s*-?\d+(?:\.\d+)?\b")
WRITES_TO_SCREEN = re.compile(
    r"\.textContent\s*=|\.innerText\s*=|\.innerHTML\s*=|\.text\s*\("
    r"|insertAdjacentHTML|\.setAttribute\s*\("
)

# Nilai status yang dulu ditulis mati di markup dan terbaca sebagai hasil
# analisis sebelum satu simpul pun dipilih.
FABRICATED_MARKUP = (
    "high_brokerage_entity",
    "+0.28 Stance",
    "13.789",
    "PR: 0.0864",
    "Tertius Gaudens Broker: Memiliki otonomi tinggi",
)


def _sources() -> list[tuple[Path, list[str]]]:
    return [(path, path.read_text(encoding="utf-8").splitlines()) for path in FRONTEND_FILES]


def test_tidak_ada_angka_sebagai_cabang_tidak_ada_data():
    offenders = []
    for path, lines in _sources():
        for number, line in enumerate(lines, 1):
            if NUMERIC_TERNARY.search(line) or NUMERIC_TERNARY_REVERSED.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()[:120]}")

    assert offenders == [], (
        "Angka tidak boleh menjadi nilai cadangan pada ternary. "
        "Kembalikan null dan biarkan panel menampilkan status kosong:\n"
        + "\n".join(offenders)
    )


def test_tidak_ada_angka_cadangan_pada_baris_yang_menulis_ke_layar():
    offenders = []
    for path, lines in _sources():
        for number, line in enumerate(lines, 1):
            if not WRITES_TO_SCREEN.search(line):
                continue
            if NUMERIC_OR.search(line) or NUMERIC_NULLISH.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()[:120]}")

    assert offenders == [], (
        "Baris yang menulis ke layar tidak boleh memakai `|| <angka>` atau "
        "`?? <angka>`: nilai kosong harus tampil kosong:\n"
        + "\n".join(offenders)
    )


@pytest.mark.parametrize("needle", FABRICATED_MARKUP)
def test_markup_tidak_membawa_hasil_analisis_bawaan(needle):
    offenders = [
        f"{path.name}:{number}"
        for path, lines in _sources()
        for number, line in enumerate(lines, 1)
        if needle in line
    ]

    assert offenders == [], (
        f"Markup tidak boleh memuat nilai jadi {needle!r}; "
        "panel harus kosong sampai simpul dipilih:\n" + "\n".join(offenders)
    )


def test_panel_status_memakai_satu_pembaca_sentimen():
    """Sentimen dibaca lewat nodeSentiment(), bukan dari field datar."""
    index = frontend_source.source()

    assert "function nodeSentiment(" in index
    # Field datar ini tidak pernah dikirim serializer; membacanya berarti
    # mengarang angka.
    for forbidden in ("sentiment_pos", "sentiment_neg", "sentiment_neu", "sentiment_stance"):
        assert forbidden not in index, f"{forbidden} dibaca padahal tidak pernah dikirim API"


def test_bootstrap_menyatakan_status_lapisan():
    """UI bercabang pada status manifest, bukan pada ada-tidaknya field."""
    index = frontend_source.source()

    assert "function sentimentLayerStatus(" in index
    assert "dataset.layers" in index


# Kata kunci yang tidak boleh dipakai sebagai nama variabel. Satu pelanggaran
# membuat seluruh blok <script> gagal di-parse, dan gejalanya menyesatkan:
# halaman tetap tampil, tetapi semua data berhenti dimuat tanpa error di UI.
RESERVED_BINDING = re.compile(
    r"\b(?:const|let|var)\s+"
    r"(null|true|false|undefined|this|super|new|typeof|void|delete|instanceof|in|of"
    r"|class|function|return|if|else|for|while|do|switch|case|break|continue"
    r"|throw|try|catch|finally|with|debugger|yield|await|export|import|extends)\s*="
)


def test_tidak_ada_kata_kunci_dipakai_sebagai_nama_variabel():
    offenders = [
        f"{path.name}:{number}: {line.strip()[:100]}"
        for path, lines in _sources()
        for number, line in enumerate(lines, 1)
        if RESERVED_BINDING.search(line)
    ]

    assert offenders == [], (
        "Nama variabel tidak boleh berupa kata kunci JavaScript: satu pelanggaran "
        "membuat seluruh skrip gagal di-parse dan data berhenti dimuat:\n"
        + "\n".join(offenders)
    )
