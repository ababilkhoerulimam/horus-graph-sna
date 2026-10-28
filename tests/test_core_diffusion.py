"""
Difusi di atas graf kecil yang jawabannya bisa dihitung tangan.

Yang dijaga:

1. Model berhenti saat tidak ada penularan baru — bukan berjalan selamanya
   atau berhenti setelah satu gelombang.
2. Peluang 0 dan 1 memberi dua kutub yang bisa diperiksa tanpa statistik:
   hanya penyebar, atau seluruh komponen.
3. Sebaran yang dikembalikan berjumlah 1, dan frekuensi per simpul berada di
   antara 0 dan 1.
4. Seed menentukan hasil: jalankan yang sama memberi sebaran yang sama persis.
5. Model ambang dengan ambang seragam deterministik, dan itu dinyatakan —
   bukan disamarkan sebagai hasil ukur ketidakpastian.
"""

from __future__ import annotations

import networkx as nx
import pytest

from horus_graph.core import diffusion


@pytest.fixture()
def rantai() -> nx.Graph:
    """A-B-C, lintasan tiga simpul."""
    graph = nx.Graph()
    graph.add_edges_from([("A", "B"), ("B", "C")])
    return graph


@pytest.fixture()
def bintang() -> nx.Graph:
    """Pusat A dengan tiga daun."""
    graph = nx.Graph()
    graph.add_edges_from([("A", "B"), ("A", "C"), ("A", "D")])
    return graph


def test_peluang_satu_menular_ke_seluruh_komponen(rantai: nx.Graph) -> None:
    hasil = diffusion.independent_cascade(rantai, ["A"], probability=1.0, runs=20, seed=1)

    assert hasil["status"] == "ready"
    assert hasil["mean"] == 3.0
    assert hasil["distribution"] == [{"adopted": 3, "count": 20, "share": 1.0}]
    assert hasil["p05"] == hasil["p95"] == 3


def test_peluang_nol_hanya_penyebar(rantai: nx.Graph) -> None:
    hasil = diffusion.independent_cascade(rantai, ["A"], probability=0.0, runs=20, seed=1)

    assert hasil["mean"] == 1.0
    frekuensi = {row["id"]: row["frequency"] for row in hasil["adoption_frequency"]}
    assert frekuensi == {"A": 1.0}
    # B tidak pernah tertular; ia tidak muncul sebagai nol.
    assert "B" not in frekuensi


def test_peluang_setengah_berada_di_antara_dua_kutub(bintang: nx.Graph) -> None:
    hasil = diffusion.independent_cascade(bintang, ["A"], probability=0.5, runs=400, seed=7)

    assert 1.0 < hasil["mean"] < 4.0
    assert hasil["p05"] < hasil["p95"]
    assert sum(point["share"] for point in hasil["distribution"]) == pytest.approx(1.0)


def test_sebaran_yang_sama_untuk_seed_yang_sama(bintang: nx.Graph) -> None:
    pertama = diffusion.independent_cascade(bintang, ["A"], probability=0.4, runs=50, seed=11)
    kedua = diffusion.independent_cascade(bintang, ["A"], probability=0.4, runs=50, seed=11)

    assert pertama["distribution"] == kedua["distribution"]
    assert pertama["adoption_frequency"] == kedua["adoption_frequency"]


def test_ambang_setengah_merambat_di_lintasan(rantai: nx.Graph) -> None:
    """B punya dua tetangga dan satu aktif: 0,5 mencapai ambang 0,5."""
    hasil = diffusion.linear_threshold(rantai, ["A"], threshold=0.5, runs=10, seed=1)

    assert hasil["mean"] == 3.0
    assert hasil["deterministic"] is True


def test_ambang_penuh_berhenti_di_penyebar(rantai: nx.Graph) -> None:
    """Tidak ada simpul yang seluruh tetangganya aktif pada gelombang pertama."""
    hasil = diffusion.linear_threshold(rantai, ["A"], threshold=1.0, runs=10, seed=1)

    assert hasil["mean"] == 1.0


def test_ambang_dinilai_serentak(bintang: nx.Graph) -> None:
    """
    Tiga daun tidak saling bertetangga, jadi ambang 0,5 dari pusat tidak
    membuat daun menular ke daun lain — hasilnya 4, bukan 4 berantai.
    """
    hasil = diffusion.linear_threshold(bintang, ["A"], threshold=0.5, runs=10, seed=1)

    assert hasil["mean"] == 4.0
    assert hasil["distribution"] == [{"adopted": 4, "count": 10, "share": 1.0}]


def test_beberapa_penyebar_dihitung_sekali(rantai: nx.Graph) -> None:
    hasil = diffusion.independent_cascade(rantai, ["A", "A", "C"], probability=1.0, runs=10, seed=1)

    assert hasil["params"]["seeds"] == ["A", "A", "C"]
    assert hasil["mean"] == 3.0


def test_jumlah_simulasi_di_luar_batas_ditolak(rantai: nx.Graph) -> None:
    with pytest.raises(ValueError):
        diffusion.independent_cascade(rantai, ["A"], probability=0.5, runs=5, seed=1)
    with pytest.raises(ValueError):
        diffusion.linear_threshold(rantai, ["A"], threshold=0.5, runs=5000, seed=1)


def test_penyebar_di_luar_graf_ditolak(rantai: nx.Graph) -> None:
    with pytest.raises(ValueError, match="tidak ada di graf"):
        diffusion.independent_cascade(rantai, ["Z"], probability=0.5, runs=10, seed=1)


def test_graf_tanpa_sisi_hanya_menyebarkan_ke_dirinya(rantai: nx.Graph) -> None:
    kosong = nx.Graph()
    kosong.add_nodes_from(["A", "B"])
    hasil = diffusion.independent_cascade(kosong, ["A"], probability=1.0, runs=10, seed=1)

    assert hasil["mean"] == 1.0
    assert hasil["edges"] == 0


def test_blok_menunggu_masukan_tidak_membawa_angka() -> None:
    blok = diffusion.awaiting("Graf tanpa sisi: tidak ada jalur penularan.")

    assert blok["status"] == "awaiting_input"
    assert blok["reason"]
    assert blok["mean"] is None
    assert blok["distribution"] == []
    assert blok["adoption_frequency"] == []
