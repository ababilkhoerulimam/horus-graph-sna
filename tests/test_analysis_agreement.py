"""Kesepakatan peringkat: tau-b, Jaccard top-k, dan cakupan varian."""

from __future__ import annotations

import pytest

from horus_graph.analysis.agreement import (
    MIN_COVERAGE,
    RANK_VARIANTS,
    jaccard_top,
    kendall_tau_b,
    rank_agreement,
)
from horus_graph.core import build_network


def _network(bundle_factory, entities=("A", "B", "C", "D", "E")):
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 6) for e in entities[:3]]
    rows += [(f"art{i:03d}", e, 1) for i in range(6, 9) for e in entities[2:]]
    return build_network(bundle_factory(list(entities), rows, articles=20))


def test_tau_b_jawaban_acuan() -> None:
    # 8 pasangan konkordan, 2 diskordan dari 10: (8 - 2) / 10 = 0,6.
    assert kendall_tau_b([1, 2, 3, 4, 5], [1, 2, 4, 5, 3]) == pytest.approx(0.6)


def test_tau_b_identik_dan_terbalik() -> None:
    values = [1, 2, 3, 4, 5]

    assert kendall_tau_b(values, values) == pytest.approx(1.0)
    assert kendall_tau_b(values, list(reversed(values))) == pytest.approx(-1.0)


def test_tau_b_mengoreksi_seri() -> None:
    # Satu seri di y: penyebut menyusut, bukan dihitung sebagai diskordan.
    assert kendall_tau_b([1, 2, 3, 4], [1, 2, 2, 3]) == pytest.approx(0.9129, abs=1e-4)


def test_tau_b_tidak_terdefinisi_bila_datar() -> None:
    assert kendall_tau_b([1, 1, 1], [1, 2, 3]) is None
    assert kendall_tau_b([1, 2], [1, 2]) is None


def test_jaccard_top_menghitung_irisan() -> None:
    assert jaccard_top(["a", "b", "c"], ["a", "b", "c"], 3) == 1.0
    assert jaccard_top(["a", "b"], ["c", "d"], 2) == 0.0
    assert jaccard_top(["a", "b", "c"], ["a", "b", "d"], 3) == pytest.approx(0.5)
    assert jaccard_top([], [], 3) is None


def test_matriks_simetris_dan_diagonal_satu(bundle_factory) -> None:
    result = rank_agreement(_network(bundle_factory))

    assert result["status"] == "ready"
    assert result["variants"] == list(RANK_VARIANTS)
    for name in RANK_VARIANTS:
        assert result["tau"][name][name] == 1.0
        assert result["jaccard"][name][name] == 1.0
    for a in RANK_VARIANTS:
        for b in RANK_VARIANTS:
            assert result["tau"][a][b] == result["tau"][b][a]
            assert result["jaccard"][a][b] == result["jaccard"][b][a]


def test_cakupan_penuh_pada_graf_kecil(bundle_factory) -> None:
    result = rank_agreement(_network(bundle_factory))

    assert all(value == 1.0 for value in result["coverage"].values())


def test_cakupan_rendah_menjadi_insufficient(bundle_factory) -> None:
    network = _network(bundle_factory)

    result = rank_agreement(network, extra={"prominence": {"A": 1.0}})

    assert result["status"] == "insufficient"
    assert result["coverage"]["prominence"] < MIN_COVERAGE
    assert "cakupan" in (result["reason"] or "")


def test_varian_tambahan_masuk_matriks(bundle_factory) -> None:
    network = _network(bundle_factory)
    values = {entity_id: float(index) for index, entity_id in enumerate(network.entities.index)}

    result = rank_agreement(network, extra={"prominence": values})

    assert "prominence" in result["variants"]
    assert result["tau"]["prominence"]["prominence"] == 1.0
    assert result["tau"]["degree"]["prominence"] == result["tau"]["prominence"]["degree"]