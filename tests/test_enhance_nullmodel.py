"""Null model: derajat terjaga, metrik teramati dibanding distribusi acak."""

from __future__ import annotations

import networkx as nx
import numpy as np
from scipy import sparse

from horus_graph.core import build_network
from horus_graph.enhance.nullmodel import (
    ASSOCIATION_METRICS,
    _curveball,
    association_null,
    degree_preserving_null,
)


def _cliques(bundle_factory):
    # Dua klik 5 simpul tanpa jembatan. Kepadatan ini penting: graf kecil membuat
    # double-edge swap hanya punya sedikit susunan berbeda, sehingga distribusi
    # null-nya terlalu sempit untuk bisa dibedakan dari nilai teramati.
    entities = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in entities[:5]]
    rows += [(f"art{i:03d}", e, 1) for i in range(8, 16) for e in entities[5:]]
    return build_network(bundle_factory(entities, rows, articles=40))


def test_metrik_teramati_lebih_tinggi_dari_null(bundle_factory):
    network = _cliques(bundle_factory)
    result = degree_preserving_null(network, resamples=40, seed=7)

    assert result.observed["modularity"] > result.null_mean["modularity"]
    assert result.observed["transitivity"] > result.null_mean["transitivity"]
    assert result.z["modularity"] > 2
    assert result.p_value["modularity"] < 0.1
    assert result.resamples == 40


def test_pengacakan_menjaga_derajat(bundle_factory):
    network = _cliques(bundle_factory)
    graph = network.graph.copy()
    before = sorted(degree for _, degree in graph.degree())
    nx.double_edge_swap(graph, nswap=20, max_tries=200, seed=1)
    assert sorted(degree for _, degree in graph.degree()) == before


def test_graf_tanpa_edge_mengembalikan_none(bundle_factory):
    bundle = bundle_factory(["A", "B"], [("art000", "A", 1)], articles=5)
    result = degree_preserving_null(build_network(bundle), resamples=10, seed=7)
    assert result.resamples == 0
    assert result.observed["modularity"] is None
    # p = 1.0 adalah hasil uji; di sini tidak ada uji yang berjalan.
    assert result.p_value["modularity"] is None
    # Parameter yang diminta tetap terbaca, bukan diganti nol.
    assert result.seed == 7


def test_hasil_deterministik_dengan_seed_sama(bundle_factory):
    network = _cliques(bundle_factory)
    first = degree_preserving_null(network, resamples=10, seed=3)
    second = degree_preserving_null(network, resamples=10, seed=3)
    assert first.null_mean == second.null_mean


def test_dict_hasil_memuat_metode(bundle_factory):
    network = _cliques(bundle_factory)
    payload = degree_preserving_null(network, resamples=10).as_dict()
    assert payload["method"] == "degree_preserving_double_edge_swap"
    assert set(payload["observed"]) == {"modularity", "transitivity", "assortativity"}
    assert payload["null_mean"]["transitivity"] >= 0


# --- null asosiasi (insidensi) -------------------------------------------


def test_curveball_menjaga_kedua_margin() -> None:
    matrix = sparse.csr_matrix(
        np.array(
            [
                [1, 1, 0, 1],
                [0, 1, 1, 1],
                [1, 0, 1, 0],
                [1, 1, 1, 1],
            ],
            dtype=float,
        )
    )
    rng = np.random.default_rng(5)

    for _ in range(5):
        permuted = _curveball(matrix, rng, sweeps=3)
        assert np.array_equal(
            np.asarray(permuted.sum(axis=0)).ravel(),
            np.asarray(matrix.sum(axis=0)).ravel(),
        )
        assert np.array_equal(
            np.asarray(permuted.sum(axis=1)).ravel(),
            np.asarray(matrix.sum(axis=1)).ravel(),
        )


def test_null_asosiasi_melaporkan_metode_dan_sweeps(bundle_factory) -> None:
    network = _cliques(bundle_factory)

    result = association_null(network, resamples=10, seed=7, sweeps=3)

    assert result.method == "bipartite_incidence_permutation"
    assert result.sweeps == 3
    assert result.resamples == 10
    assert set(result.observed) == set(ASSOCIATION_METRICS)


def test_null_asosiasi_deterministik_dengan_seed_sama(bundle_factory) -> None:
    network = _cliques(bundle_factory)

    first = association_null(network, resamples=10, seed=3)
    second = association_null(network, resamples=10, seed=3)

    assert first.null_mean == second.null_mean


def test_dua_klik_lebih_termodel_dari_null_asosiasi(bundle_factory) -> None:
    network = _cliques(bundle_factory)

    result = association_null(network, resamples=20, seed=7)

    assert result.observed["modularity"] > result.null_mean["modularity"]
    assert result.p_value["modularity"] < 0.15


def test_pengacakan_insidensi_justru_membuat_proyeksi_lebih_padat(bundle_factory) -> None:
    """
    Dua klik terpisah: tidak ada pasangan lintas klik sama sekali.

    Setelah margin diacak, entitas tersebar antarartikel sehingga banyak
    pasangan lintas klik mendapat support cukup dan lolos ambang. Karena itu
    jumlah sisi bukan statistik yang tepat untuk null ini — modularitas yang
    membedakan struktur nyata dari sebaran acak.
    """
    network = _cliques(bundle_factory)

    result = association_null(network, resamples=20, seed=7)

    assert result.observed["edges"] < result.null_mean["edges"]


def test_null_asosiasi_tanpa_pasangan_tidak_mengarang_p_value(bundle_factory) -> None:
    bundle = bundle_factory(["A", "B"], [("art000", "A", 1)], articles=5)

    result = association_null(build_network(bundle), resamples=10, seed=7)

    assert result.resamples == 0
    assert result.method == "bipartite_incidence_permutation"
    assert all(value is None for value in result.p_value.values())
