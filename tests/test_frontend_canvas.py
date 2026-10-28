"""
Renderer canvas: kabelnya, bukan gambarnya.

Kanvas tidak bisa diuji dari Python, tetapi yang paling mudah rusak diam-diam
adalah sambungannya: berkas yang tidak lagi dimuat, ambang yang hilang, atau
jalur sisi yang kembali membuat satu elemen SVG per sisi. Yang dijaga di sini
adalah sambungan itu.
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


@pytest.fixture(scope="module")
def canvas_js() -> str:
    return (STATIC / "js" / "graph_canvas.js").read_text(encoding="utf-8")


def test_berkas_kanvas_dimuat_sebelum_skrip_utama() -> None:
    """
    Dimuat sesudah skrip utama berarti HorusCanvas belum ada saat dipakai.

    Urutan tag dibaca dari index.html, bukan dari sumber gabungan: di sumber
    gabungan, skrip utama selalu ditempel belakangan, jadi tesnya tidak mungkin
    gagal dan tidak menjaga apa pun.
    """
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    kanvas = html.find('src="js/graph_canvas.js"')
    utama = html.find('src="js/app_01.js"')

    assert kanvas != -1 and utama != -1
    assert kanvas < utama


def test_kanvas_setara_untuk_filter_cari_dan_fit(markup: str, canvas_js: str) -> None:
    """
    Di jalur kanvas tidak ada elemen per simpul, jadi setiap fungsi yang
    memanggil nodeG menjadi no-op tanpa error. Jalur setaranya harus ada.
    """
    for name in ("function setActive(", "function setQuery(", "function fit(", "function coverage("):
        assert name in canvas_js, f"kanvas tidak punya {name}"

    # Satu antarmuka untuk dua renderer, dan pemanggil memakai antarmuka itu.
    assert "const graphView = {" in markup
    assert "HorusCanvas.setActive(ids)" in markup
    assert "graphView.setActive(" in markup
    assert "graphView.setQuery(" in markup
    assert "graphView.fit()" in markup
    assert "graphView.refresh()" in markup


def test_kanvas_di_fit_saat_mount(canvas_js: str) -> None:
    """Skala 1:1 pada 10.000 simpul hanya menampilkan sekitar 7% luas graf."""
    badan = canvas_js[canvas_js.find("function mount(") :][:1600]

    assert "fit();" in badan


def test_ambang_kanvas_eksplisit(canvas_js: str) -> None:
    assert "const THRESHOLD = 2000;" in canvas_js
    assert "function handles(count)" in canvas_js


def test_sisi_didelegasikan_ke_kanvas_saat_aktif(markup: str) -> None:
    badan = markup[markup.find("function renderActiveEdges(") :][:400]
    assert "HorusCanvas.active" in badan
    assert "HorusCanvas.setEdges(edgeList)" in badan


def test_boot_memilih_satu_renderer(markup: str) -> None:
    badan = markup[markup.find("const canvasMode =") :][:1200]
    assert "HorusCanvas.mount(allData)" in badan
    # Simulasi gaya tidak dijalankan di jalur kanvas: 10.000 simpul butuh
    # puluhan detik dan hasilnya berbeda tiap muat.
    assert "if (!canvasMode) initForceSimulation();" in badan


def test_level_of_detail_ada(canvas_js: str) -> None:
    assert "EDGE_MIN_ZOOM" in canvas_js
    assert "LABEL_MIN_ZOOM" in canvas_js
    assert "LABEL_BUDGET" in canvas_js


def test_sisi_diarahkan_ke_objek_simpul(canvas_js: str) -> None:
    """
    Tanpa ini, sisi yang ujungnya masih berupa id dilewati diam-diam dan
    kanvas tampak kosong tanpa satu pun error.
    """
    assert "byId.get" in canvas_js
    assert "edge.source && edge.target" in canvas_js
