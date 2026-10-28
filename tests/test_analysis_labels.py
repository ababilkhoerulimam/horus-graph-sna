"""Evaluasi label eksternal: precision@k dan recall@k pada JSONL."""

from __future__ import annotations

import json
import os

import pytest

from horus_graph.analysis.labels import ENV_VAR, evaluate, evaluate_from_env, load_labels
from horus_graph.analysis.ranking import top_brokers
from horus_graph.core import build_network


def _network(bundle_factory):
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 6) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(6, 9) for e in ("B", "C")]
    return build_network(bundle_factory(["A", "B", "C"], rows, articles=12))


def _write(tmp_path, rows):
    path = tmp_path / "labels.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


def test_precision_at_k_sempurna_pada_label_tertanam(tmp_path, bundle_factory):
    network = _network(bundle_factory)
    top_two = [row["id"] for row in top_brokers(network, limit=2)]
    path = _write(tmp_path, [{"ranking": "brokers", "expected": top_two}])

    result = evaluate(network, load_labels(path), k=2)

    assert result["status"] == "ready"
    assert result["precision_at_k"] == 1.0
    assert result["recall_at_k"] == 1.0
    assert result["coverage"] == 1.0


def test_label_entitas_tak_dikenal_dilewati_dan_dihitung(tmp_path, bundle_factory):
    network = _network(bundle_factory)
    path = _write(
        tmp_path,
        [
            {"ranking": "brokers", "expected": ["A"]},
            {"ranking": "brokers", "expected": ["entitas-hantu"]},
            {"ranking": "tidak-ada", "expected": ["A"]},
        ],
    )

    result = evaluate(network, load_labels(path), k=3)

    assert result["labelled"] == 3
    assert result["evaluated"] == 1
    assert result["coverage"] == pytest.approx(1 / 3, abs=1e-4)
    assert len(result["skipped"]) == 2


def test_baris_rusak_dilewati(tmp_path):
    path = tmp_path / "labels.jsonl"
    path.write_text('{"ranking": "brokers"}\n{bukan json\n\n', encoding="utf-8")

    assert len(load_labels(path)) == 1


def test_tanpa_env_status_menyatakan_itu(bundle_factory, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)

    result = evaluate_from_env(_network(bundle_factory))

    assert result["status"] == "no_labels"
    assert result["precision_at_k"] is None


@pytest.mark.skipif(
    not os.environ.get(ENV_VAR),
    reason=f"{ENV_VAR} tidak diset: tidak ada label eksternal",
)
def test_label_eksternal_dari_env(bundle_factory):
    result = evaluate_from_env(_network(bundle_factory), k=5)

    assert result["status"] in {"ready", "insufficient"}