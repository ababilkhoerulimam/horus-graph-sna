"""Selang kepercayaan pergeseran peringkat antar-epos."""

from __future__ import annotations

from horus_graph.analysis.epoch_shift import rank_shift_interval


def _bundle(bundle_factory, articles=20):
    entities = ["A", "B", "C", "D"]
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 6) for e in entities]
    rows += [(f"art{i:03d}", e, 1) for i in range(6, 10) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(10, 14) for e in ("C", "D")]
    half = articles // 2
    dates = ["2021-06-01"] * half + ["2023-06-01"] * (articles - half)
    return bundle_factory(
        entities,
        rows,
        articles=articles,
        dates=dates,
        epochs=[("e1", 2021, 2022), ("e2", 2023, 2024)],
    )


def test_pergeseran_melaporkan_selang(bundle_factory):
    result = rank_shift_interval(_bundle(bundle_factory), "e1", "e2", resamples=10, seed=3)

    assert result["status"] == "ready"
    assert result["resamples"] == 10
    assert result["entities"], "harus ada entitas yang bertahan di kedua epos"
    for row in result["entities"]:
        assert row["ci_low"] <= row["median_shift"] <= row["ci_high"]
        assert row["delta_rank"] == row["target_rank"] - row["baseline_rank"]


def test_hasil_deterministik_dengan_seed_sama(bundle_factory):
    bundle = _bundle(bundle_factory)

    first = rank_shift_interval(bundle, "e1", "e2", resamples=8, seed=11)
    second = rank_shift_interval(bundle, "e1", "e2", resamples=8, seed=11)

    assert first["entities"] == second["entities"]


def test_epos_terlalu_kecil_tidak_mengarang_selang(bundle_factory):
    bundle = bundle_factory(
        ["A", "B"],
        [("art000", "A", 1), ("art001", "B", 1)],
        articles=4,
        # Epos pertama hanya satu artikel: tidak ada yang bisa diresample.
        dates=["2021-06-01", "2023-06-01", "2023-06-01", "2023-06-01"],
        epochs=[("e1", 2021, 2022), ("e2", 2023, 2024)],
    )

    result = rank_shift_interval(bundle, "e1", "e2", resamples=5, seed=1)

    assert result["status"] == "insufficient"
    assert "artikel" in (result["reason"] or "")
    assert result["entities"] == []
    assert result["resamples"] == 0


def test_epos_tidak_dikenal_ditolak(bundle_factory):
    bundle = _bundle(bundle_factory)

    try:
        rank_shift_interval(bundle, "e1", "tidak-ada", resamples=2)
    except KeyError as exc:
        assert "tidak-ada" in str(exc)
    else:
        raise AssertionError("epos yang tidak ada harus ditolak")