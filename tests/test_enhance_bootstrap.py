"""Bootstrap artikel: selang betweenness dan stabilitas komunitas."""

from __future__ import annotations

import numpy as np
import pytest

from horus_graph.core import build_network
from horus_graph.enhance.bootstrap import bootstrap_network


def _network(bundle_factory):
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 10) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(10, 20) for e in ("B", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(20, 26) for e in ("C", "D")]
    return build_network(
        bundle_factory(["A", "B", "C", "D"], rows, articles=120, ego="A")
    )


def test_selang_mengapit_rata_rata(bundle_factory):
    result = bootstrap_network(_network(bundle_factory), resamples=30, seed=5)
    frame = result.betweenness

    assert set(frame.columns) == {
        "mean",
        "sd",
        "ci_low",
        "ci_high",
        "baseline",
        "stability",
    }
    assert (frame["ci_low"] <= frame["mean"] + 1e-9).all()
    assert (frame["mean"] <= frame["ci_high"] + 1e-9).all()
    assert (frame["sd"] >= 0).all()


def test_simpul_perantara_paling_stabil(bundle_factory):
    result = bootstrap_network(_network(bundle_factory), resamples=30, seed=5)
    # B ada di tengah rantai: hampir selalu punya betweenness > 0.
    assert result.betweenness.at["B", "stability"] >= 0.9
    assert result.betweenness.at["A", "stability"] <= 0.5


def test_ari_komunitas_dilaporkan(bundle_factory):
    result = bootstrap_network(_network(bundle_factory), resamples=20, seed=1)
    assert -1.0 <= result.ari["mean"] <= 1.0
    assert result.ari["p05"] <= result.ari["mean"] <= result.ari["p95"]


def test_komunitas_bootstrap_punya_modus_dan_konsistensi(bundle_factory):
    result = bootstrap_network(_network(bundle_factory), resamples=20, seed=1)
    frame = result.communities
    assert set(frame.columns) == {"baseline", "mode", "consistency"}
    assert (frame["consistency"] > 0).all()
    assert (frame["consistency"] <= 1).all()


def test_graf_kosong_mengembalikan_hasil_kosong(bundle_factory):
    bundle = bundle_factory(["A", "B"], [("art000", "A", 1)], articles=5)
    result = bootstrap_network(build_network(bundle), resamples=10)
    assert result.resamples == 0
    assert result.betweenness.empty
    assert result.ari["mean"] is None


def test_hasil_deterministik_dengan_seed_sama(bundle_factory):
    network = _network(bundle_factory)
    first = bootstrap_network(network, resamples=10, seed=11)
    second = bootstrap_network(network, resamples=10, seed=11)
    assert np.allclose(first.betweenness["mean"], second.betweenness["mean"])
    assert first.ari == second.ari
