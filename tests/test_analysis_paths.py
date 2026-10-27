"""Rute terkuat dan simulasi penghapusan simpul."""

from __future__ import annotations

import pytest

from horus_graph.analysis import simulate_removal, trace_path
from horus_graph.core import build_network


def _network(bundle_factory):
    # Rantai A-B-C-D plus cabang buntu A-E; 79 artikel tidak menyebut siapa pun.
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(8, 14) for e in ("B", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(14, 18) for e in ("C", "D")]
    rows += [(f"art{i:03d}", e, 1) for i in range(18, 21) for e in ("A", "E")]
    return build_network(
        bundle_factory(["A", "B", "C", "D", "E", "G"], rows, articles=100, ego="A")
    )


def test_rute_utama_mengikuti_bobot_tertinggi(bundle_factory):
    network = _network(bundle_factory)
    result = trace_path(network, "A", "D")

    assert result["success"] is True
    assert result["path"] == ["A", "B", "C", "D"]
    assert result["total_hops"] == 3
    assert result["critical_broker"] == "B"
    assert result["alternative_path"] is None
    assert result["has_hawkes"] is False
    assert result["product_alpha"] is None
    assert result["total_lead_time_min"] is None


def test_hop_memuat_bobot_dan_npmi(bundle_factory):
    network = _network(bundle_factory)
    result = trace_path(network, "A", "D")
    first = result["hops"][0]
    assert first["source"] == "A"
    assert first["target"] == "B"
    assert first["weight"] == 8
    assert 0 < first["npmi"] <= 1
    assert first["is_hawkes"] is False
    assert result["total_weight"] == 8 + 6 + 4


def test_sumber_sama_dengan_target_ditolak(bundle_factory):
    network = _network(bundle_factory)
    result = trace_path(network, "A", "a")
    assert result["success"] is False
    assert result["reason"] == "same_entity"


def test_entitas_tidak_dikenal_menjadi_kode_alasan(bundle_factory):
    network = _network(bundle_factory)
    assert trace_path(network, "tidak-ada", "A")["reason"] == "origin_not_found"
    assert trace_path(network, "A", "tidak-ada")["reason"] == "target_not_found"


def test_simpul_terisolasi_tidak_punya_jalur(bundle_factory):
    network = _network(bundle_factory)
    result = trace_path(network, "A", "G")
    assert result["success"] is False
    assert result["reason"] == "no_path"


def test_penghapusan_simpul_menghitung_selisih_densitas(bundle_factory):
    network = _network(bundle_factory)
    result = simulate_removal(network, "B")

    assert result["success"] is True
    assert result["removed"]["id"] == "B"
    assert result["baseline"] == {"nodes": 6, "edges": 4, "density": 0.2667}
    assert result["post"] == {"nodes": 5, "edges": 2, "density": 0.2}
    assert result["lost_edges"] == 2
    assert result["delta_density"] == pytest.approx(-0.0667, abs=1e-4)
    # G memang sudah terisolasi sebelum penghapusan; laporan menyebutnya apa adanya.
    assert result["isolated_nodes"] == ["G"]
    assert result["severed_causal_routes"] == 0
    assert result["lost_sentiment_impact"] is None


def test_simpul_ego_dilindungi(bundle_factory):
    network = _network(bundle_factory)
    result = simulate_removal(network, "A")
    assert result["success"] is False
    assert result["reason"] == "ego_protected"


def test_simpul_tidak_dikenal_ditolak(bundle_factory):
    network = _network(bundle_factory)
    result = simulate_removal(network, "tidak-ada")
    assert result["success"] is False
    assert result["reason"] == "not_found"


def test_penyerap_beban_diurutkan_menurut_delta(bundle_factory):
    network = _network(bundle_factory)
    result = simulate_removal(network, "B")
    deltas = [item["delta_betweenness"] for item in result["absorbing_brokers"]]
    assert deltas == sorted(deltas, reverse=True)
    assert all(item["id"] != network.domain.ego_id for item in result["absorbing_brokers"])
