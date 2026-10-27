"""Perputaran jaringan antar epos."""

from __future__ import annotations

from horus_graph.core import build_network  # noqa: F401  (dokumentasi ketergantungan)
from horus_graph.core.temporal import build_temporal
from horus_graph.enhance.turnover import epoch_turnover, turnover_summary


def _bundle(bundle_factory):
    # e1: A-B (8 artikel) + A-C (8 artikel). e2: A-B tetap, A-C hilang, A-D muncul.
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(8, 16) for e in ("A", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(24, 32) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(32, 40) for e in ("A", "D")]
    dates = ["2021-06-01"] * 24 + ["2023-06-01"] * 24
    return bundle_factory(
        ["A", "B", "C", "D"],
        rows,
        articles=48,
        dates=dates,
        epochs=[("e1", 2021, 2022), ("e2", 2023, 2024)],
    )


def test_perputaran_menghitung_tepi_masuk_dan_keluar(bundle_factory):
    temporal = build_temporal(_bundle(bundle_factory))
    frame = epoch_turnover(temporal)

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["from_epoch"] == "e1"
    assert row["to_epoch"] == "e2"
    assert row["edges_added"] == 1
    assert row["edges_removed"] == 1
    assert row["edges_from"] == 2
    assert row["edges_to"] == 2


def test_jaccard_tepi_setengah_untuk_satu_bertahan_satu_berganti(bundle_factory):
    temporal = build_temporal(_bundle(bundle_factory))
    row = epoch_turnover(temporal).iloc[0]
    # 1 tepi bertahan dari 3 tepi gabungan; simpul {A,B,C} vs {A,B,D} → 2/4.
    assert row["edge_jaccard"] == 0.3333
    assert row["node_jaccard"] == 0.5


def test_simpul_baru_dan_hilang_dilaporkan(bundle_factory):
    temporal = build_temporal(_bundle(bundle_factory))
    row = epoch_turnover(temporal).iloc[0]
    assert row["added_nodes"] == ["D"]
    assert row["removed_nodes"] == ["C"]


def test_ringkasan_mengabaikan_all_time(bundle_factory):
    temporal = build_temporal(_bundle(bundle_factory))
    summary = turnover_summary(temporal)
    assert summary["transitions"] == 1
    assert summary["mean_edge_jaccard"] == 0.3333
    assert summary["method"] == "consecutive_epoch_jaccard"


def test_satu_epos_tidak_punya_transisi(bundle_factory):
    bundle = bundle_factory(
        ["A", "B"],
        [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in ("A", "B")],
        articles=10,
        epochs=[("e1", 2021, 2022)],
    )
    temporal = build_temporal(bundle)
    assert epoch_turnover(temporal).empty
    assert turnover_summary(temporal)["transitions"] == 0
