"""
Partisi konsensus dan stabilitas per simpul.

Graf uji sengaja kecil dan jawabannya bisa dihitung tangan: dua segitiga yang
dihubungkan satu sisi tidak mungkin dipartisi selain "dua segitiga", sehingga
setiap simpul harus stabil 1,0. Siklus enam, sebaliknya, punya banyak
pembagian yang sama baiknya — di situlah stabilitas harus turun di bawah 1.
"""

from __future__ import annotations

import networkx as nx

from horus_graph.core import metrics
from horus_graph.core.metrics import community


def _two_triangles() -> nx.Graph:
    graph = nx.Graph()
    graph.add_edges_from(
        [("a", "b"), ("b", "c"), ("a", "c"), ("d", "e"), ("e", "f"), ("d", "f"), ("c", "d")]
    )
    return graph


def test_dua_segitiga_jembatan_semua_stabil():
    result = metrics.consensus(_two_triangles(), runs=20)

    assert result.status == "ready"
    assert result.labels["a"] == result.labels["b"] == result.labels["c"]
    assert result.labels["d"] == result.labels["e"] == result.labels["f"]
    assert result.labels["a"] != result.labels["d"]
    assert set(result.stability.values()) == {1.0}
    assert result.agreement == 1.0


def test_siklus_enam_punya_simpul_batas():
    result = metrics.consensus(nx.cycle_graph(6), runs=20)

    # Tidak ada simpul yang sepenuhnya stabil: setiap simpul bisa berpindah
    # sisi tanpa membuat modularitas jauh lebih buruk.
    assert all(value is not None and 0.0 < value < 1.0 for value in result.stability.values())
    assert result.agreement is not None and result.agreement < 1.0


def test_jalankan_acuan_tidak_ikut_dihitung():
    """
    Dengan dua jalankan, satu-satunya nilai yang boleh muncul adalah 0 atau 1.

    Kalau jalankan acuan ikut dirata-rata, setiap simpul otomatis mendapat
    0,5 dan angka itu bukan hasil ukur — ia hanya sisa dari cara menghitung.
    """
    result = metrics.consensus(nx.cycle_graph(6), runs=2)

    assert result.runs == 2
    assert set(result.stability.values()) <= {0.0, 1.0}


def test_simpul_terisolasi_tidak_punya_stabilitas():
    graph = _two_triangles()
    graph.add_node("sendiri")

    result = metrics.consensus(graph, runs=10)

    assert result.stability["sendiri"] is None
    assert result.stability["a"] == 1.0


def test_graf_kosong_menunggu_masukan():
    result = metrics.consensus(nx.Graph(), runs=10)

    assert result.status == "awaiting_input"
    assert result.available is False
    assert result.runs == 0
    assert result.stability == {}
    assert result.reason


def test_graf_tanpa_sisi_menunggu_masukan():
    graph = nx.Graph()
    graph.add_nodes_from(["a", "b", "c"])

    result = metrics.consensus(graph, runs=10)

    assert result.status == "awaiting_input"
    assert result.labels == {"a": 1, "b": 1, "c": 1}
    assert set(result.stability.values()) == {None}
    assert "tanpa sisi" in (result.reason or "")


def test_seed_sama_menghasilkan_angka_sama():
    first = metrics.consensus(nx.cycle_graph(8), runs=10, seed=7)
    second = metrics.consensus(nx.cycle_graph(8), runs=10, seed=7)

    assert first.stability == second.stability
    assert first.agreement == second.agreement
    assert dict(first.labels) == dict(second.labels)


def test_stabilitas_selalu_di_rentang_nol_satu():
    for graph in (nx.cycle_graph(6), nx.path_graph(7), nx.barbell_graph(4, 2)):
        result = metrics.consensus(graph, runs=10)
        for value in result.stability.values():
            if value is None:
                continue
            assert 0.0 <= value <= 1.0


def test_minimal_dua_jalankan():
    result = metrics.consensus(_two_triangles(), runs=1)

    assert result.runs == community.MIN_CONSENSUS_RUNS


def test_as_dict_memuat_metode_dan_simpul_batas():
    result = metrics.consensus(nx.cycle_graph(8), runs=20)
    payload = result.as_dict()

    assert payload["status"] == "ready"
    assert payload["method"] == community.CONSENSUS_METHOD
    assert payload["runs"] == 20
    assert payload["communities"] >= 2
    assert payload["stability_median"] is not None
    assert payload["unstable_count"] == len(payload["unstable"])
    assert payload["unstable_count"] > 0
    assert {"id", "stability"} <= set(payload["unstable"][0])


def test_as_dict_menyebut_alasan_saat_menunggu():
    payload = metrics.consensus(nx.Graph()).as_dict()

    assert payload["status"] == "awaiting_input"
    assert payload["stability_median"] is None
    assert payload["unstable"] == []
    assert payload["reason"]


def test_ari_tetap_diekspor_dari_enhance():
    """ARI pindah ke `core`, tetapi jalur lama harus tetap menjawab sama."""
    from horus_graph.enhance import stats

    assert stats.adjusted_rand_index([1, 1, 2, 2], [1, 1, 2, 2]) == 1.0
    assert stats.adjusted_rand_index([1, 1, 2, 2], [2, 2, 1, 1]) == 1.0
