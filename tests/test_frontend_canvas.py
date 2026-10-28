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


def test_berkas_kanvas_dimuat_sebelum_skrip_utama(markup: str) -> None:
    """Dimuat sesudah skrip utama berarti `HorusCanvas` belum ada saat dipakai."""
    tag = markup.find('src="js/graph_canvas.js"')
    main = markup.find("let allData = { nodes: [], links: [], metadata: {} }")

    assert tag != -1
    assert main != -1
    assert tag < main


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
