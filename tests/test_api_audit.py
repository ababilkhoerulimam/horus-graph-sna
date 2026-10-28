"""
Jejak audit tidak boleh menggagalkan permintaan yang sudah berhasil.

Yang dijaga di sini bukan "audit menulis berkas", melainkan dua hal yang lebih
sulit: kegagalan menulis tidak menghilangkan jejaknya (barisnya masuk log
server dan penghitung), dan tindakan yang tidak bisa diulang tanpa efek ganda
dibatalkan sebelum terjadi, bukan sesudah.
"""

from __future__ import annotations

import json
import logging

import pytest

from horus_graph.api import audit, observability
from horus_graph.api.app import create_app

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402
from test_api import _write_bundle  # noqa: E402


@pytest.fixture()
def client(tmp_path, bundle_factory, monkeypatch) -> TestClient:
    # Catatan disimpan di luar bundle; tanpa env ini, tes menulis ke data/
    # milik repo dan saling mewarisi isi.
    monkeypatch.setenv("HORUS_ANNOTATIONS_DIR", str(tmp_path / "annotations"))
    root = _write_bundle(tmp_path / "bundle", bundle_factory)
    return TestClient(create_app(root))


@pytest.fixture()
def audit_file(tmp_path, monkeypatch):
    path = tmp_path / "audit" / "jejak.jsonl"
    monkeypatch.setenv("HORUS_AUDIT_LOG", str(path))
    audit.reset_failures()
    observability.reset_metrics()
    return path


@pytest.fixture()
def broken_audit(tmp_path, monkeypatch):
    """Path audit yang parent-nya berkas, jadi penulisan selalu gagal."""
    blocker = tmp_path / "blocked"
    blocker.write_text("bukan folder", encoding="utf-8")
    monkeypatch.setenv("HORUS_AUDIT_LOG", str(blocker / "jejak.jsonl"))
    audit.reset_failures()
    observability.reset_metrics()
    return blocker


def _catat(client: TestClient, text: str = "Catatan uji") -> dict:
    response = client.post(
        "/api/annotations",
        json={"target_type": "node", "target_id": "A", "text": text},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_audit_gagal_tidak_menggagalkan_penyimpanan(client, broken_audit) -> None:
    response = client.post(
        "/api/annotations",
        json={"target_type": "node", "target_id": "A", "text": "Catatan uji"},
    )

    assert response.status_code == 200
    assert response.headers.get("X-Audit-Status") == "failed"
    assert audit.failures() == 1
    # Catatan tetap tersimpan: menyimpannya idempoten, jadi tidak perlu dibatalkan.
    daftar = client.get("/api/annotations").json()["annotations"]
    assert len(daftar) == 1


def test_ekspor_tetap_berhasil_saat_audit_gagal(client, broken_audit) -> None:
    response = client.get("/api/export/graphml")

    assert response.status_code == 200
    assert response.headers.get("X-Audit-Status") == "failed"
    assert "<graphml" in response.text


def test_laporan_tetap_berhasil_saat_audit_gagal(client, broken_audit) -> None:
    response = client.post("/api/report", json={"svg": None})

    assert response.status_code == 200
    assert response.headers.get("X-Audit-Status") == "failed"
    assert "<!DOCTYPE html>" in response.text


def test_bootstrap_menandai_audit_gagal_lewat_header(client, broken_audit) -> None:
    response = client.get("/api/bootstrap")

    assert response.status_code == 200
    assert response.headers.get("X-Audit-Status") == "failed"


def test_hapus_anotasi_dibatalkan_saat_audit_gagal(client, broken_audit) -> None:
    catatan = _catat(client)
    audit.reset_failures()

    response = client.delete(f"/api/annotations/{catatan['annotation']['id']}")

    assert response.status_code == 503
    # Penghapusan tidak terjadi: pembaca tidak boleh melihat catatan hilang
    # tanpa jejak siapa yang menghapusnya.
    daftar = client.get("/api/annotations").json()["annotations"]
    assert [item["id"] for item in daftar] == [catatan["annotation"]["id"]]


def test_kegagalan_audit_menulis_baris_utuh_ke_log(client, broken_audit, caplog) -> None:
    with caplog.at_level(logging.ERROR, logger="horus_graph.api.audit"):
        _catat(client, "Catatan yang jejaknya gagal")

    pesan = [record.getMessage() for record in caplog.records if "audit.write_failed" in record.getMessage()]
    assert pesan, "kegagalan audit tidak tercatat di log"
    baris = json.loads(pesan[0].split("audit.write_failed ", 1)[1])
    assert baris["action"] == "annotation.create"
    assert baris["actor"] == "local"
    assert baris["role"] == "admin"


def test_kegagalan_audit_menaikkan_penghitung_metrik(client, broken_audit) -> None:
    _catat(client)

    assert observability.audit_failures() == 1
    assert "horus_audit_write_failures_total 1" in observability.metrics_text()


def test_audit_sukses_menulis_tepat_satu_baris(client, audit_file) -> None:
    _catat(client)

    baris = [line for line in audit_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(baris) == 1
    assert json.loads(baris[0])["action"] == "annotation.create"


def test_simpan_dua_kali_tidak_menggandakan_baris(client, audit_file) -> None:
    _catat(client, "Catatan yang sama")
    _catat(client, "Catatan yang sama")

    assert len(client.get("/api/annotations").json()["annotations"]) == 1
    baris = [line for line in audit_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Dua permintaan, dua baris: jejak mencatat permintaan, bukan keadaan.
    assert len(baris) == 2


def test_tanpa_path_audit_bukan_kegagalan(client, monkeypatch) -> None:
    monkeypatch.delenv("HORUS_AUDIT_LOG", raising=False)
    audit.reset_failures()

    response = client.get("/api/bootstrap")

    assert response.status_code == 200
    assert "X-Audit-Status" not in response.headers
    assert audit.failures() == 0
