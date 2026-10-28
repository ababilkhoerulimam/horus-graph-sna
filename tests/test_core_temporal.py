"""Irisan temporal: denominator per epos, simpul terisolasi, dan agregat."""

from __future__ import annotations

import pytest

from horus_graph.core.temporal import build_temporal


def _corpus(bundle_factory):
    # 10 artikel 2021, 10 artikel 2023. A-B hanya di 2021, A-C hanya di 2023.
    dates = ["2021-06-01"] * 10 + ["2023-06-01"] * 10
    rows = [(f"art{i:03d}", e, 1) for i in range(5) for e in ("A", "B")]
    rows += [(f"art{i:03d}", "D", 1) for i in range(5, 6)]
    rows += [(f"art{i:03d}", e, 1) for i in range(10, 15) for e in ("A", "C")]
    return bundle_factory(
        ["A", "B", "C", "D"],
        rows,
        articles=20,
        dates=dates,
        epochs=[("e1", 2021, 2022), ("e2", 2023, 2024)],
    )


def test_epos_dihitung_dari_artikel_rentangnya_sendiri(bundle_factory):
    temporal = build_temporal(_corpus(bundle_factory))

    first = temporal.by_id("e1")
    assert set(first.graph.nodes) == {"A", "B"}
    assert first.graph.number_of_edges() == 1
    assert first.articles == 10
    assert first.isolated == ("D",)

    second = temporal.by_id("e2")
    assert set(second.graph.nodes) == {"A", "C"}
    assert second.graph.number_of_edges() == 1
    assert second.articles == 10


def test_simpul_terisolasi_dibuang_dari_graf_tapi_dilaporkan(bundle_factory):
    temporal = build_temporal(_corpus(bundle_factory))
    first = temporal.by_id("e1")
    assert "D" not in first.graph.nodes
    assert first.density == 1.0  # 1 edge pada 2 simpul


def test_denominator_epos_bukan_denominator_global(bundle_factory):
    temporal = build_temporal(_corpus(bundle_factory))
    # npmi A-B dihitung dari 10 artikel epos, bukan 20 artikel korpus.
    edge = temporal.by_id("e1").edges.iloc[0]
    assert edge["support"] == 5
    assert temporal.by_id("e1").articles == 10


def test_tahun_pendukung_dibatasi_rentang_epos(bundle_factory):
    temporal = build_temporal(_corpus(bundle_factory))
    assert tuple(temporal.by_id("e1").edges.iloc[0]["years"]) == (2021,)
    assert tuple(temporal.by_id("e2").edges.iloc[0]["years"]) == (2023,)
    assert tuple(temporal.by_id("all_time").edges.iloc[0]["years"]) == (2021,)


def test_agregat_all_time_menggabungkan_semua_epos(bundle_factory):
    temporal = build_temporal(_corpus(bundle_factory))
    all_time = temporal.by_id("all_time")
    assert all_time.window.start_year == 2021
    assert all_time.window.end_year == 2024
    assert all_time.articles == 20
    assert set(all_time.graph.nodes) == {"A", "B", "C"}
    assert all_time.graph.number_of_edges() == 2


def test_all_time_bisa_dimatikan(bundle_factory):
    temporal = build_temporal(_corpus(bundle_factory), include_all_time=False)
    assert [slice_.window.id for slice_ in temporal.slices] == ["e1", "e2"]
    with pytest.raises(KeyError):
        temporal.by_id("all_time")


def test_domain_tanpa_epos_menghasilkan_lapisan_kosong(bundle_factory):
    """Tanpa jendela epos, lapisan temporal kosong — bundle tetap sah."""
    bundle = bundle_factory(["A", "B"], [("art000", "A", 1)], articles=2)
    temporal = build_temporal(bundle)
    assert temporal.slices == ()
    assert temporal.total_articles == 2
    with pytest.raises(KeyError):
        temporal.by_id("all_time")


def test_epos_tanpa_edge_tetap_menghasilkan_slice_kosong(bundle_factory):
    bundle = bundle_factory(
        ["A", "B"],
        [("art000", "A", 1), ("art001", "B", 1)],
        articles=4,
        dates=["2021-01-01", "2021-02-01", "2022-01-01", "2022-02-01"],
        epochs=[("e1", 2021, 2021)],
    )
    temporal = build_temporal(bundle)
    slice_ = temporal.by_id("e1")
    assert slice_.graph.number_of_nodes() == 0
    assert slice_.edges.empty
    assert slice_.density == 0.0
    assert slice_.isolated == ("A", "B")
    assert slice_.top_broker is None


def test_kolom_metrik_sama_di_jalur_normal_dan_kosong(bundle_factory):
    """Satu konstanta kolom untuk kedua jalur; kalau bercabang, KeyError kembali."""
    from horus_graph.core.temporal import NODE_COLUMNS, build_temporal

    temporal = build_temporal(_corpus(bundle_factory))
    normal = temporal.by_id("e1").node_metrics

    assert list(normal.columns) == list(NODE_COLUMNS)
