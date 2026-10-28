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


def test_graf_lengkap_tidak_lebih_padat_dari_null(bundle_factory) -> None:
    """
    Semua artikel menyebut ketiganya: tidak ada susunan yang lebih padat.

    Null insidensi tetap berjalan di sini (tidak seperti swap pada proyeksi
    yang menyerah pada graf lengkap), dan hasilnya justru lebih jujur: p = 1
    karena tidak ada struktur yang melebihi derajat.
    """
    bundle = bundle_factory(
        ["A", "B", "C"],
        [(f"art{i:03d}", e, 1) for i in range(0, 12) for e in ("A", "B", "C")],
        articles=12,
        ego="A",
    )
    payload = artifact.compute(bundle, build_network(bundle), SMALL)
    null = payload["inference"]["null_model"]

    assert null["method"] == "bipartite_incidence_permutation"
    assert null["p_value"]["edges"] > 0.1


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
    params = artifact.InferenceParams(
        resamples=50, bootstrap_resamples=50, seed=42, ci=90.0
    )
    fresh = {"params": params.as_dict()}
    assert not artifact.stale(fresh, params)

    # Parameter berbeda: angka 50 resampling bukan jawaban untuk 5 resampling.
    assert artifact.stale(fresh, SMALL)

    # Versi metode lama basi walau parameternya sama: arti null_model berubah.
    old = {"params": {**params.as_dict(), "method_version": 1}}
    assert artifact.stale(old, params)


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


# --- artefak terikat snapshot ----------------------------------------------


def test_artefak_tanpa_snapshot_dianggap_basi() -> None:
    """Tanpa snapshot_id tidak ada cara membuktikan artefak ini milik bundle mana."""
    payload = {"method_version": 1, "params": SMALL.as_dict(), "inference": {}}

    assert artifact.stale(payload, SMALL, "snap-baru") is True


def test_artefak_snapshot_lain_dianggap_basi() -> None:
    payload = {
        "method_version": 1,
        "params": SMALL.as_dict(),
        "inference": {},
        "snapshot_id": "snap-lama",
    }

    assert artifact.stale(payload, SMALL, "snap-baru") is True


def test_artefak_snapshot_sama_tidak_basi() -> None:
    payload = {
        "method_version": 1,
        "params": SMALL.as_dict(),
        "inference": {},
        "snapshot_id": "snap-sama",
    }

    assert artifact.stale(payload, SMALL, "snap-sama") is False


def test_artefak_hasil_perhitungan_membawa_snapshot(client) -> None:
    client.get("/api/inference")
    payload = _wait(client)

    assert payload["status"] == "ready"
    key = payload["snapshot_id"]
    tersimpan = artifact.read_artifact(client.app.state.bundle_path)
    if tersimpan is not None:
        assert tersimpan["snapshot_id"] == key


def test_job_berjalan_dijawab_202(client, monkeypatch) -> None:
    """202 untuk semua "belum ada hasil"; 200 akan terbaca sebagai sudah siap."""
    from horus_graph.analysis import inference as modul

    monkeypatch.setattr(
        modul.InferenceJobs,
        "start",
        lambda self, key, work, on_done=None: False,
    )

    response = client.get("/api/inference")

    assert response.status_code == 202
    assert response.json()["status"] == "computing"


def test_kegagalan_bisa_diulang_setelah_jeda(client, monkeypatch) -> None:
    """Status failed tidak boleh mengunci panel sampai server di-restart."""
    import time

    from horus_graph.api import routes

    def meledak(*args, **kwargs):
        raise RuntimeError("gagal dihitung")

    monkeypatch.setattr(routes.inference_artifact, "compute", meledak)
    client.get("/api/inference")

    gagal = _wait(client)
    assert gagal["status"] == "failed"
    assert gagal["retry_after_seconds"] > 0

    # Setelah jeda, percobaan baru diizinkan: waktu kegagalan digeser ke masa lalu.
    jobs = client.app.state.inference_jobs
    jobs._failed_at[gagal["snapshot_id"]] = time.monotonic() - routes.INFERENCE_RETRY_SECONDS - 1

    ulang = client.get("/api/inference")

    assert ulang.status_code == 202
    assert ulang.json()["status"] == "computing"


def test_edge_significance_melaporkan_keluarga_dan_sisi(bundle_factory) -> None:
    bundle = _sparse(bundle_factory)
    network = build_network(bundle)

    block = artifact.compute(bundle, network, SMALL)["inference"]["edge_significance"]

    assert block["family"] == "all_observed_pairs"
    assert block["tested"] >= block["significant"]
    assert block["q_threshold"] == 0.05
    # Rincian sepanjang jumlah sisi backbone: satu baris per sisi, bukan per pasangan.
    assert len(block["u"]) == len(block["v"]) == len(block["q"])
    assert len(block["u"]) == network.graph.number_of_edges()


def test_edge_significance_memakai_indeks_simpul_yang_sah(bundle_factory) -> None:
    bundle = _sparse(bundle_factory)
    network = build_network(bundle)

    block = artifact.compute(bundle, network, SMALL)["inference"]["edge_significance"]
    ids = network.cooccurrence.entity_ids

    for u, v in zip(block["u"], block["v"], strict=True):
        assert 0 <= u < len(ids) and 0 <= v < len(ids)
        assert ids[u] in network.graph and ids[v] in network.graph


def test_rincian_edge_dibuang_di_atas_batas(bundle_factory, monkeypatch) -> None:
    bundle = _sparse(bundle_factory)
    network = build_network(bundle)
    monkeypatch.setattr(artifact, "EDGE_DETAIL_LIMIT", 0)

    block = artifact.compute(bundle, network, SMALL)["inference"]["edge_significance"]

    assert block["detail"] == "omitted"
    assert "u" not in block
    assert block["tested"] >= block["significant"]
