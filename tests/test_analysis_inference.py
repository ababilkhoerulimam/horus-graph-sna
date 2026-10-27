"""
Inferensi sebagai artefak.

Yang dijaga: perhitungan mahal tidak pernah berjalan di dalam handler HTTP,
dan p-value yang ditampilkan selalu berasal dari uji yang benar-benar berjalan.
Keduanya mudah rusak tanpa terlihat: satu `p_value=1.0` pada graf kosong
terbaca sebagai "sudah diuji, tidak signifikan", dan satu perhitungan
sinkron membuat permintaan menggantung satu menit.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from horus_graph.analysis import inference as artifact
from horus_graph.contract import schema
from horus_graph.core.build import build_network
from horus_graph.enhance.nullmodel import degree_preserving_null
from horus_graph.io import write_bundle

SMALL = artifact.InferenceParams(resamples=5, bootstrap_resamples=5, seed=42)


def _pad(frame: pd.DataFrame, target: pa.Schema) -> pd.DataFrame:
    padded = frame.copy()
    for field in target:
        if field.name not in padded.columns:
            padded[field.name] = None
    return padded


def _write(root: Path, bundle_factory) -> Path:
    """Dua klik + satu jembatan: cukup untuk punya modularitas yang bisa diuji."""
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 12) for e in ("A", "B", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(12, 20) for e in ("C", "D", "E")]
    bundle = bundle_factory(["A", "B", "C", "D", "E"], rows, articles=20, ego="A")
    frames = {
        "entities": _pad(bundle.entities, schema.ENTITIES),
        "articles": _pad(bundle.articles, schema.ARTICLES),
        "mentions": _pad(bundle.mentions, schema.MENTIONS),
        "topics": _pad(bundle.topics, schema.TOPICS),
        "article_topics": _pad(bundle.article_topics, schema.ARTICLE_TOPICS),
    }
    write_bundle(
        root,
        frames=frames,
        domain=bundle.domain,
        dataset_id="synthetic",
        date_range=(date(2021, 1, 1), date(2026, 12, 31)),
        generator="tests/inference",
    )
    return root


def _sparse(bundle_factory):
    """
    Dua klik yang berbagi satu simpul, bukan klik penuh.

    Graf lengkap tidak bisa diacak dengan double-edge swap, sehingga null model
    tidak punya satu pun resample — dan p-value-nya memang tidak boleh muncul.
    """
    rows = [(f"art{i:03d}", e, 1) for i in range(0, 12) for e in ("A", "B", "C")]
    rows += [(f"art{i:03d}", e, 1) for i in range(12, 20) for e in ("C", "D", "E")]
    return bundle_factory(["A", "B", "C", "D", "E"], rows, articles=20, ego="A")


def test_compute_mengembalikan_dua_blok(bundle_factory) -> None:
    bundle = _sparse(bundle_factory)
    payload = artifact.compute(bundle, build_network(bundle), SMALL)

    assert "null_model" in payload["inference"]
    assert "bootstrap" in payload["inference"]
    assert payload["params"]["seed"] == 42


def test_resolusi_p_value_mengikuti_jumlah_resample(bundle_factory) -> None:
    bundle = _sparse(bundle_factory)
    payload = artifact.compute(bundle, build_network(bundle), SMALL)

    block = payload["inference"]
    used = block["null_model"]["resamples"]
    assert used > 0, "fixture harus bisa diacak"
    assert block["p_value_resolution"] == round(1.0 / (used + 1), 4)


def test_graf_tanpa_resample_tidak_punya_resolusi(bundle_factory) -> None:
    """Tidak ada resample berarti tidak ada uji, jadi tidak ada resolusi."""
    bundle = bundle_factory(
        ["A", "B", "C"],
        [(f"art{i:03d}", e, 1) for i in range(0, 12) for e in ("A", "B", "C")],
        articles=12,
        ego="A",
    )
    payload = artifact.compute(bundle, build_network(bundle), SMALL)

    assert payload["inference"]["null_model"]["resamples"] == 0
    assert payload["inference"]["p_value_resolution"] is None


def test_p_value_tidak_pernah_nol(bundle_factory) -> None:
    null = degree_preserving_null(build_network(_sparse(bundle_factory)), resamples=5, seed=1)

    for name, value in null.p_value.items():
        if value is None:
            continue
        assert value >= 1.0 / (null.resamples + 1), f"{name} di bawah resolusi"


def test_artefak_bolak_balik(tmp_path, bundle_factory) -> None:
    payload = {"method_version": 1, "params": SMALL.as_dict(),
               "inference": {"null_model": {"resamples": 5}}}

    path = artifact.write_artifact(tmp_path, payload)

    assert path.name == artifact.ARTIFACT_NAME
    assert artifact.read_artifact(tmp_path) == payload


def test_artefak_rusak_diperlakukan_sebagai_tidak_ada(tmp_path) -> None:
    (tmp_path / artifact.ARTIFACT_NAME).write_text("{bukan json", encoding="utf-8")

    assert artifact.read_artifact(tmp_path) is None


def test_artefak_tanpa_kunci_inference_ditolak(tmp_path) -> None:
    (tmp_path / artifact.ARTIFACT_NAME).write_text(
        json.dumps({"params": {}}), encoding="utf-8"
    )

    assert artifact.read_artifact(tmp_path) is None


def test_artefak_dengan_parameter_lain_dianggap_basi() -> None:
    payload = {"params": {"resamples": 50, "bootstrap_resamples": 50, "seed": 42,
                          "ci": 90.0, "method_version": 1}}

    assert artifact.stale(payload, SMALL)
    assert not artifact.stale(payload, artifact.InferenceParams(
        resamples=50, bootstrap_resamples=50, seed=42, ci=90.0
    ))


# --- endpoint -------------------------------------------------------------


@pytest.fixture()
def client(tmp_path, bundle_factory, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from horus_graph.api import routes

    root = _write(tmp_path / "bundle", bundle_factory)
    # Perhitungan diperkecil hanya untuk tes; parameter produksi tetap 200.
    monkeypatch.setattr(routes, "InferenceParams", lambda: SMALL)
    return TestClient(routes_app(root))


def routes_app(root):
    from horus_graph.api.app import create_app

    return create_app(root)


def _wait(client, limit: float = 30.0) -> dict:
    import time

    started = time.perf_counter()
    while time.perf_counter() - started < limit:
        payload = client.get("/api/inference").json()
        if payload["status"] != "computing":
            return payload
        time.sleep(0.05)
    raise AssertionError("inferensi tidak selesai dalam batas waktu")


def test_endpoint_tidak_menghitung_di_dalam_permintaan(client) -> None:
    response = client.get("/api/inference")

    assert response.status_code == 202
    assert response.json()["status"] == "computing"


def test_endpoint_akhirnya_ready_dan_menyimpan_artefak(client) -> None:
    client.get("/api/inference")
    payload = _wait(client)

    assert payload["status"] == "ready"
    # Artefak didahulukan bila sudah ada; keduanya sah selama angkanya berasal
    # dari perhitungan yang sama, bukan dari nilai bawaan.
    assert payload["source"] in {"artifact", "memory"}
    assert "null_model" in payload["inference"]


def test_panggilan_kedua_tidak_menghitung_ulang(client) -> None:
    client.get("/api/inference")
    _wait(client)

    import time

    started = time.perf_counter()
    payload = client.get("/api/inference").json()
    elapsed = time.perf_counter() - started

    assert payload["status"] == "ready"
    assert elapsed < 0.5, f"permintaan kedua memakan {elapsed:.2f}s"
