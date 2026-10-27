"""
Uji ujung-ke-ujung: bundle dengan lapisan ditulis, divalidasi, dibaca, dihitung.

Ini kontrak yang akan dipegang pipeline Kaggle: kalau tabel lapisan memenuhi
skema dan validator, engine langsung memakainya tanpa perubahan kode.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from horus_graph.analysis import entity_dossier, sentiment_ranking, trace_path
from horus_graph.contract import schema
from horus_graph.core import build_network
from horus_graph.io import load_bundle, write_bundle


def _pad(frame: pd.DataFrame, target: pa.Schema) -> pd.DataFrame:
    """Lengkapi kolom opsional yang tidak dipakai test dengan None."""
    padded = frame.copy()
    for field in target:
        if field.name not in padded.columns:
            padded[field.name] = None
    return padded


def _bundle_dir(bundle_factory, tmp_path: Path) -> Path:
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 8) for e in ("A", "B")]
    rows += [(f"art{i:03d}", e, 1) for i in range(8, 14) for e in ("B", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(14, 20) for e in ("A", "M2")]
    bundle = bundle_factory(
        ["A", "B", "C", "M1", "M2", "M3"],
        rows,
        articles=100,
        ego="A",
        topics=["T1"],
        article_topics=[("art000", "T1")],
    )

    transmission = pd.DataFrame(
        [
            ("M1", "M2", 0.5, 0.4, 0.6, 30.0, "hawkes_exp", 12, None, None),
            ("M2", "M3", 0.4, 0.3, 0.5, 60.0, "hawkes_exp", 8, None, None),
        ],
        columns=[field.name for field in schema.TRANSMISSION],
    )
    sentiment = pd.DataFrame(
        [("A", 60.0, 20.0, 20.0, "lexicon", 0.9, None, None)],
        columns=[field.name for field in schema.SENTIMENT],
    )

    frames = {
        "entities": _pad(bundle.entities, schema.ENTITIES),
        "articles": _pad(bundle.articles, schema.ARTICLES),
        "mentions": _pad(bundle.mentions, schema.MENTIONS),
        "topics": _pad(bundle.topics, schema.TOPICS),
        "article_topics": _pad(bundle.article_topics, schema.ARTICLE_TOPICS),
        "transmission": transmission,
        "sentiment": sentiment,
    }

    root = tmp_path / "bundle"
    write_bundle(
        root,
        frames=frames,
        domain=bundle.domain,
        dataset_id="synthetic",
        date_range=(date(2021, 1, 1), date(2026, 12, 31)),
        generator="tests/roundtrip",
    )
    return root


def test_bundle_berlapis_lolos_validasi_dan_dibaca_utuh(bundle_factory, tmp_path):
    root = _bundle_dir(bundle_factory, tmp_path)
    loaded = load_bundle(root)

    assert loaded.layer_status("transmission") == "ready"
    assert loaded.layer_status("sentiment") == "ready"
    assert loaded.counts()["transmission"] == 2
    assert loaded.counts()["sentiment"] == 1


def test_engine_memakai_lapisan_yang_sudah_ditulis(bundle_factory, tmp_path):
    network = build_network(load_bundle(_bundle_dir(bundle_factory, tmp_path)))

    assert network.transmission.n_edges == 2
    assert network.sentiment.scores["A"]["pos"] == 60.0

    route = trace_path(network, "M1", "M3")
    assert route["route"] == "wire"
    assert route["product_alpha"] == pytest.approx(0.2)
    assert route["total_lead_time_min"] == pytest.approx(90.0)

    assert entity_dossier(network, "A")["sentiment"]["status"] == "ready"
    assert sentiment_ranking(network)["status"] == "ready"


def test_manifest_mencatat_status_lapisan(bundle_factory, tmp_path):
    root = _bundle_dir(bundle_factory, tmp_path)
    manifest = load_bundle(root).manifest
    assert manifest.layers == {"transmission": "ready", "sentiment": "ready"}
