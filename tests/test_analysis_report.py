"""Peringkat broker, lubang struktural, dan briefing eksekutif."""

from __future__ import annotations

import pytest

from horus_graph.analysis import (
    executive_briefing,
    structural_holes,
    top_brokers,
)
from horus_graph.core import build_network
from horus_graph.core.anomaly import detect_anomalies
from horus_graph.core.bipartite import build_bipartite
from horus_graph.core.metrics import structural_hole_role
from horus_graph.core.temporal import build_temporal


def _network(bundle_factory):
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(8, 14) for e in ("B", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(14, 18) for e in ("C", "D")]
    rows += [(f"art{i:03d}", e, 1) for i in range(18, 21) for e in ("A", "E")]
    return build_network(
        bundle_factory(
            ["A", "B", "C", "D", "E"],
            rows,
            articles=100,
            ego="A",
            entity_types=["Organization", "Person", "Person", "Location", "Person"],
        )
    )


def test_broker_diurutkan_menurut_betweenness(bundle_factory):
    network = _network(bundle_factory)
    ranking = top_brokers(network, limit=3)
    assert [item["rank"] for item in ranking] == [1, 2, 3]
    values = [item["betweenness"] for item in ranking]
    assert values == sorted(values, reverse=True)
    assert ranking[0]["id"] == "B"


def test_broker_bisa_disaring_menurut_tipe(bundle_factory):
    network = _network(bundle_factory)
    ranking = top_brokers(network, entity_type="person", limit=10)
    assert {item["id"] for item in ranking} == {"B", "C", "E"}


def test_lubang_struktural_otonomi_naik_dari_constraint_terendah(bundle_factory):
    network = _network(bundle_factory)
    result = structural_holes(network, mode="high_autonomy", limit=2)
    values = [item["burt_constraint"] for item in result["ranking"]]
    assert values == sorted(values)
    for item in result["ranking"]:
        assert item["role"] == structural_hole_role(item["burt_constraint"])


def test_lubang_struktural_keterkekangan_membalik_urutan(bundle_factory):
    network = _network(bundle_factory)
    autonomy = structural_holes(network, mode="high_autonomy", limit=2)["ranking"]
    embedded = structural_holes(network, mode="high_constraint", limit=2)["ranking"]
    assert autonomy[0]["id"] != embedded[0]["id"]
    assert embedded[0]["burt_constraint"] >= embedded[1]["burt_constraint"]


def test_mode_tidak_dikenal_ditolak(bundle_factory):
    network = _network(bundle_factory)
    with pytest.raises(ValueError):
        structural_holes(network, mode="tertinggi")


def test_briefing_tanpa_lapisan_opsional_tetap_lengkap(bundle_factory):
    network = _network(bundle_factory)
    briefing = executive_briefing(network)

    assert briefing["dataset"]["ego_id"] == "A"
    assert briefing["macro"]["nodes"] == 5
    assert briefing["macro"]["edges"] == 4
    assert briefing["critical_broker"]["id"] == "B"
    assert briefing["epochs"] == []
    assert briefing["anomaly"] is None
    assert briefing["topics"] is None
    assert briefing["layers"] == {
        "transmission": "awaiting_input",
        "sentiment": "awaiting_input",
    }


def test_briefing_memuat_temporal_bipartit_dan_anomali(bundle_factory):
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in ("A", "B")]
    bundle = bundle_factory(
        ["A", "B"],
        rows,
        articles=100,
        ego="A",
        dates=["2023-01-31"] * 50 + ["2024-01-31"] * 50,
        epochs=[("e1", 2023, 2023), ("e2", 2024, 2024)],
        topics=["T1"],
        article_topics=[("art000", "T1"), ("art001", "T1")],
    )
    network = build_network(bundle)

    briefing = executive_briefing(
        network,
        temporal=build_temporal(bundle),
        anomaly=detect_anomalies(bundle),
        bipartite=build_bipartite(bundle),
    )
    assert [epoch["id"] for epoch in briefing["epochs"]] == ["e1", "e2", "all_time"]
    assert briefing["anomaly"]["months"] == 13
    assert briefing["topics"]["topics"] == 1
    assert briefing["layers"]["sentiment"] == "awaiting_input"
