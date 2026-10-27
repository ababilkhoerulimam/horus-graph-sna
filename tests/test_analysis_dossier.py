"""Dossier entitas: angka dari jaringan, lintasan dari epos, sentimen shell."""

from __future__ import annotations

import pytest

from horus_graph.analysis import entity_dossier
from horus_graph.core import build_network
from horus_graph.core.temporal import build_temporal


def _network(bundle_factory):
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 6) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(10, 13) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(13, 16) for e in ("B", "C")]
    dates = (
        ["2021-06-01"] * 6
        + ["2021-09-01"] * 4
        + ["2023-06-01"] * 3
        + ["2023-07-01"] * 3
        + ["2024-03-01"] * 4
    )
    return bundle_factory(
        ["A", "B", "C"],
        rows,
        articles=20,
        dates=dates,
        epochs=[("e1", 2021, 2022), ("e2", 2023, 2024)],
    )


def test_dossier_memuat_metrik_dari_jaringan(bundle_factory):
    bundle = _network(bundle_factory)
    network = build_network(bundle)
    dossier = entity_dossier(network, "A")

    row = network.node_metrics.loc["A"]
    assert dossier["degree"] == int(row["degree"])
    assert dossier["betweenness"] == pytest.approx(float(row["betweenness"]))
    assert dossier["articles"] == int(row["articles"])
    assert dossier["community"] == int(row["louvain_community"])


def test_tetangga_diurutkan_menurut_bobot(bundle_factory):
    network = build_network(_network(bundle_factory))
    dossier = entity_dossier(network, "A")
    weights = [neighbor["weight"] for neighbor in dossier["neighbors"]]
    assert weights == sorted(weights, reverse=True)
    assert dossier["neighbors"][0]["id"] == "B"
    assert dossier["neighbors"][0]["weight"] == 9


def test_nama_tidak_dikenal_melempar_keyerror(bundle_factory):
    network = build_network(_network(bundle_factory))
    with pytest.raises(KeyError):
        entity_dossier(network, "tidak-ada")


def test_tanpa_temporal_lintasan_kosong_bukan_nol(bundle_factory):
    network = build_network(_network(bundle_factory))
    dossier = entity_dossier(network, "A")
    assert dossier["trajectory"] == []
    assert dossier["exposure"] == {
        "prior_articles": None,
        "recent_articles": None,
        "delta": None,
    }


def test_lintasan_mengikuti_subgraf_epos(bundle_factory):
    bundle = _network(bundle_factory)
    network = build_network(bundle)
    temporal = build_temporal(bundle)
    dossier = entity_dossier(network, "A", temporal=temporal)

    assert [point["epoch"] for point in dossier["trajectory"]] == ["e1", "e2"]
    first = dossier["trajectory"][0]
    assert first["articles"] == 6
    assert first["active"] is True
    assert dossier["exposure"]["prior_articles"] == 6
    assert dossier["exposure"]["recent_articles"] == 3
    assert dossier["exposure"]["delta"] == -3


def test_entitas_yang_tidak_aktif_di_epos_ditandai_nonaktif(bundle_factory):
    bundle = _network(bundle_factory)
    network = build_network(bundle)
    temporal = build_temporal(bundle)
    dossier = entity_dossier(network, "C", temporal=temporal)

    epochs = {point["epoch"]: point for point in dossier["trajectory"]}
    assert epochs["e1"]["active"] is False
    assert epochs["e1"]["degree"] == 0
    assert epochs["e1"]["betweenness"] is None


def test_sentimen_tanpa_lapisan_berstatus_awaiting_input(bundle_factory):
    network = build_network(_network(bundle_factory))
    sentiment = entity_dossier(network, "A")["sentiment"]
    assert sentiment["status"] == "awaiting_input"
    assert sentiment["stance"] is None
    assert sentiment["pos"] is None


def test_sentimen_siap_dihitung_menjadi_stance(bundle_factory):
    network = build_network(_network(bundle_factory))
    dossier = entity_dossier(
        network,
        "A",
        sentiment={"A": {"pos": 60.0, "neu": 20.0, "neg": 20.0, "confidence": 0.9, "method": "lexicon"}},
    )
    assert dossier["sentiment"]["status"] == "ready"
    assert dossier["sentiment"]["stance"] == 0.4
    assert dossier["sentiment"]["method"] == "lexicon"


def test_entitas_tanpa_skor_sentimen_ditandai_missing(bundle_factory):
    network = build_network(_network(bundle_factory))
    dossier = entity_dossier(
        network, "B", sentiment={"A": {"pos": 60.0, "neu": 20.0, "neg": 20.0}}
    )
    assert dossier["sentiment"]["status"] == "missing"
    assert dossier["sentiment"]["stance"] is None
