"""
Golden test: engine baru harus mereproduksi artefak horus-agent persis.

Angka di bawah diambil dari `data/dewa_united_concentric_graph.json`
(commit 0d183dc). Kalau salah satu gagal, artinya migrasi mengubah definisi
metrik — bukan sekadar refactor.
"""

from __future__ import annotations

import numpy as np
import pytest

from horus_graph.core import build_network


@pytest.fixture(scope="module")
def network(golden_bundle):
    return build_network(golden_bundle)


def test_populasi_dan_backbone_sama(network):
    assert network.total_articles == 27407
    assert len(network.entity_ids) == 77
    assert network.backbone.candidate_pairs == 2698
    assert network.backbone.above_threshold == 467
    assert network.backbone.added_for_support == 8
    assert network.backbone.still_isolated == ()
    assert network.backbone.entities_below_threshold == (
        "Indonesia",
        "kompas-com",
        "tvonenews-com",
        "harianjogja-com",
        "viva-co-id",
        "jpnn-com",
        "idntimes-com",
        "republika-co-id",
    )


def test_ringkasan_makro_sama(network):
    summary = network.summary
    assert summary["nodes"] == 77
    assert summary["edges"] == 475
    assert summary["density"] == 0.1623
    assert summary["transitivity"] == 0.7352
    assert summary["diameter"] == 6
    assert summary["average_path_length"] == 2.6763
    assert summary["components"] == 1
    assert summary["isolated"] == 0
    assert summary["communities"]["count"] == 4
    assert summary["communities"]["sizes"] == [33, 26, 13, 5]
    assert summary["communities"]["modularity"] == 0.3872
    assert summary["communities"]["method"] == "louvain_weighted_seed42"


def test_rentang_npmi_edge_terpilih(network):
    values = np.array([data["npmi"] for _, _, data in network.graph.edges(data=True)])
    assert values.min() == pytest.approx(0.0822, abs=5e-5)
    assert values.max() == pytest.approx(0.7062, abs=5e-5)


def test_delapan_edge_diselamatkan_bertanda(network):
    rescued = [
        (u, v) for u, v, data in network.graph.edges(data=True) if data["rescued"]
    ]
    assert len(rescued) == 8
    assert ("Indonesia", "Dewa United FC") in rescued or any(
        "Indonesia" in pair for pair in rescued
    )


@pytest.mark.parametrize(
    "entity_id, degree, betweenness, pagerank, constraint, effective, community, articles",
    [
        ("Jan Olde Riekerink", 25, 0.063298, 0.0318, 0.1799, 18.11, 1, 2940),
        ("Egy Maulana Vikri", 22, 0.032489, 0.03073, 0.1861, 15.25, 1, 2954),
        ("Persib Bandung", 20, 0.020925, 0.03683, 0.1899, 12.75, 4, 7929),
        ("Liga 1", 14, 0.119803, 0.03231, 0.2285, 11.37, 4, 10537),
        ("Dewa United FC", 2, 0.0, 0.01375, 0.6311, 1.41, 4, 18541),
    ],
)
def test_metrik_simpul_sama(
    network, entity_id, degree, betweenness, pagerank, constraint, effective, community, articles
):
    row = network.node_metrics.loc[entity_id]
    assert int(row["degree"]) == degree
    assert float(row["betweenness"]) == pytest.approx(betweenness, abs=1e-6)
    assert float(row["pagerank"]) == pytest.approx(pagerank, abs=1e-5)
    assert float(row["burt_constraint"]) == pytest.approx(constraint, abs=1e-4)
    assert float(row["effective_size"]) == pytest.approx(effective, abs=0.01)
    assert int(row["louvain_community"]) == community
    assert int(row["articles"]) == articles


def test_provenance_menyebut_metode_setiap_angka(network):
    provenance = network.provenance()
    assert provenance["population"]["total_articles"] == 27407
    assert provenance["association"]["method"] == "npmi_bouma2009"
    assert provenance["backbone"]["min_support"] == 3
    assert provenance["backbone"]["min_npmi"] == 0.2
    for key in ("betweenness", "constraint", "effective_size", "pagerank", "closeness", "community"):
        assert provenance["metrics"][key]
