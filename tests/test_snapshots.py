"""
Snapshot berversi: satu id untuk satu isi, dan daftar yang bisa ditelusuri.

Yang dijaga: id tidak berubah karena folder dipindah atau berkas disentuh, dan
berubah begitu isinya berubah.
"""

from __future__ import annotations

import json
import shutil

from horus_graph.api import datasets
from horus_graph.contract.models import DateRange, GeneratorInfo, Manifest
from horus_graph.contract.snapshot import snapshot_id


def _manifest(dataset_id: str = "uji", sha: str = "a" * 64) -> Manifest:
    return Manifest(
        contract_version="1.1.0",
        dataset_id=dataset_id,
        snapshot_at="2026-01-01T00:00:00Z",
        date_range=DateRange(start="2021-01-01", end="2026-01-01"),
        counts={"entities": 3, "articles": 10, "mentions": 12},
        file_sha256={"entities": sha},
        generator=GeneratorInfo(name="tests", version="1"),
    )


def test_snapshot_id_mengikuti_isi_bukan_nama():
    assert snapshot_id(_manifest()) == snapshot_id(_manifest())
    assert snapshot_id(_manifest(dataset_id="lain")) != snapshot_id(_manifest())
    assert snapshot_id(_manifest(sha="b" * 64)) != snapshot_id(_manifest())


def test_snapshot_id_berbentuk_heksadesimal_pendek():
    """16 karakter: cukup untuk membedakan, cukup pendek untuk nama berkas."""
    value = snapshot_id(_manifest())

    assert len(value) == 16
    assert all(char in "0123456789abcdef" for char in value)
    # Manifest yang dibaca dari JSON (bukan dibuat di memori) memberi id sama.
    lewat_json = Manifest(**json.loads(_manifest().model_dump_json()))
    assert snapshot_id(lewat_json) == value


def test_loader_mengisi_snapshot_id(tmp_path, bundle_factory):
    from horus_graph.io.bundle import load_bundle
    from tests.test_api import _write_bundle

    root = _write_bundle(tmp_path / "b", bundle_factory)
    bundle = load_bundle(root)

    assert bundle.manifest.snapshot_id
    assert len(bundle.manifest.snapshot_id) == 16


def test_snapshot_id_tidak_berubah_setelah_folder_dipindah(tmp_path, bundle_factory):
    from horus_graph.io.bundle import load_bundle
    from tests.test_api import _write_bundle

    root = _write_bundle(tmp_path / "asli", bundle_factory)
    pindah = tmp_path / "pindahan"
    shutil.copytree(root, pindah)

    assert load_bundle(root).manifest.snapshot_id == load_bundle(pindah).manifest.snapshot_id


def test_snapshot_yang_ditulis_pipeline_tidak_ditimpa(tmp_path, bundle_factory):
    from horus_graph.io.bundle import load_bundle
    from tests.test_api import _write_bundle

    root = _write_bundle(tmp_path / "b", bundle_factory)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["snapshot_id"] = "dari-pipeline"
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert load_bundle(root).manifest.snapshot_id == "dari-pipeline"


def test_daftar_snapshot_melewati_folder_arsip(tmp_path, bundle_factory):
    from tests.test_api import _write_bundle

    _write_bundle(tmp_path / "satu", bundle_factory)
    _write_bundle(tmp_path / "dua", bundle_factory)
    _write_bundle(tmp_path / "_arsip", bundle_factory)

    entries = datasets.list_snapshots(tmp_path)
    assert sorted(item["folder"] for item in entries) == ["dua", "satu"]


def test_index_menyimpan_riwayat_saat_folder_hilang(tmp_path, bundle_factory):
    from tests.test_api import _write_bundle

    root = _write_bundle(tmp_path / "satu", bundle_factory)
    entries = datasets.list_snapshots(tmp_path)
    path = datasets.update_index(tmp_path, entries)
    assert path is not None and path.is_file()

    shutil.rmtree(root)
    # Pemindaian berikutnya (saat server start) menandai yang hilang, tapi
    # tidak menghapus riwayatnya.
    datasets.update_index(tmp_path, datasets.list_snapshots(tmp_path))

    riwayat = datasets.read_index(tmp_path)
    assert len(riwayat) == 1
    assert riwayat[0]["present"] is False
    assert riwayat[0]["last_seen"]


def test_endpoint_datasets_menandai_yang_aktif(tmp_path, bundle_factory):
    from fastapi.testclient import TestClient

    from horus_graph.api.app import create_app
    from tests.test_api import _write_bundle

    root = _write_bundle(tmp_path / "bundle-a", bundle_factory)
    client = TestClient(create_app(root))

    payload = client.get("/api/datasets").json()
    assert payload["active"]
    assert payload["datasets"][0]["snapshot_id"] == payload["active"]
    assert payload["datasets"][0]["counts"]

    health = client.get("/api/health").json()
    assert health["snapshot_id"] == payload["active"]
