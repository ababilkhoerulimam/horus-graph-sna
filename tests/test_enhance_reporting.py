"""Blok pelaporan wajib: populasi, parameter, dan batasan yang tidak boleh hilang."""

from __future__ import annotations

from horus_graph.core import build_network
from horus_graph.enhance.reporting import reporting_block


def _bundle(bundle_factory, **kwargs):
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(8, 14) for e in ("B", "C")]
    return bundle_factory(["A", "B", "C"], rows, articles=100, ego="A", **kwargs)


def _dense_bundle(bundle_factory):
    # Rantai empat segitiga: 9 tepi, cukup bebas untuk pengacakan derajat.
    groups = [("A", "B", "C"), ("B", "C", "D"), ("C", "D", "E"), ("D", "E", "F")]
    rows = []
    for start, group in zip(range(0, 40, 10), groups, strict=False):
        rows += [(f"art{i:03d}", e, 1) for i in range(start, start + 10) for e in group]
    return bundle_factory(list("ABCDEF"), rows, articles=60, ego="A")


def test_blok_memuat_populasi_dan_parameter(bundle_factory):
    bundle = _bundle(bundle_factory)
    block = reporting_block(bundle, build_network(bundle))

    assert block["population"] == {
        "articles": 100,
        "entities": 3,
        "mentions": 28,
        "dropped_mentions": 0,
        "entities_with_mentions": 3,
    }
    assert block["parameters"]["min_support"] == 3
    assert block["parameters"]["min_npmi"] == 0.2
    assert block["parameters"]["seed"] == 42


def test_blok_memuat_versi_kontrak_dan_metode(bundle_factory):
    bundle = _bundle(bundle_factory)
    block = reporting_block(bundle, build_network(bundle))

    assert block["contract"]["version"] == "1.0.0"
    assert block["contract"]["dataset_id"] == "synthetic"
    assert block["metrics"]["betweenness"] == "freeman_betweenness_unweighted_normalized"
    assert block["software"]["name"] == "horus-graph"


def test_batasan_menyebut_lapisan_yang_belum_ada(bundle_factory):
    bundle = _bundle(bundle_factory)
    block = reporting_block(bundle, build_network(bundle))
    text = " ".join(block["limitations"])

    assert "transmisi belum tersedia" in text
    assert "sentimen belum tersedia" in text
    assert "bukan hubungan kausal" in text


def test_batasan_tidak_menyebut_lapisan_yang_sudah_ada(bundle_factory):
    import pandas as pd

    from horus_graph.contract import schema

    transmission = pd.DataFrame(
        [("A", "B", 0.5, 0.4, 0.6, 30.0, "hawkes_exp", 5, None, None)],
        columns=[field.name for field in schema.TRANSMISSION],
    )
    sentiment = pd.DataFrame(
        [("A", 60.0, 20.0, 20.0, "lexicon", 0.9, None, None)],
        columns=[field.name for field in schema.SENTIMENT],
    )
    bundle = _bundle(bundle_factory, transmission=transmission, sentiment=sentiment)
    block = reporting_block(bundle, build_network(bundle))
    text = " ".join(block["limitations"])

    assert "transmisi belum tersedia" not in text
    assert "sentimen belum tersedia" not in text


def test_edge_penyelamat_disebut_dalam_batasan(bundle_factory):
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in ("A", "B")]
    rows += [("art008", "A", 1), ("art008", "C", 1)]
    bundle = bundle_factory(["A", "B", "C"], rows, articles=40)
    block = reporting_block(bundle, build_network(bundle))

    assert block["parameters"]["rescued_edges"] == 1
    assert "rescued" in " ".join(block["limitations"])


def test_inferensi_muncul_hanya_bila_diberikan(bundle_factory):
    bundle = _dense_bundle(bundle_factory)
    network = build_network(bundle)
    assert "inference" not in reporting_block(bundle, network)

    from horus_graph.enhance.bootstrap import bootstrap_network
    from horus_graph.enhance.nullmodel import degree_preserving_null

    block = reporting_block(
        bundle,
        network,
        null=degree_preserving_null(network, resamples=10),
        bootstrap=bootstrap_network(network, resamples=10),
    )
    assert block["inference"]["p_value_resolution"] == round(1 / 11, 4)
    assert "bootstrap" in block["inference"]
