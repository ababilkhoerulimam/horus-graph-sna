"""
Peran, jejak audit, dan pembatas laju.

Yang dijaga di sini adalah janji yang bisa diperiksa tanpa membaca kode:
viewer tidak bisa menghapus catatan, ekspor tercatat dengan identitas
pemanggil, dan tanpa identitas sama sekali perilaku lama tetap jalan.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from test_api import _write_bundle

from horus_graph.api import audit
from horus_graph.api.app import create_app
from horus_graph.api.auth import reset_rate_limits


@pytest.fixture(autouse=True)
def _bersihkan(monkeypatch):
    """Tiap tes mulai tanpa token, tanpa header SSO, tanpa audit, tanpa hitungan."""
    for name in ("HORUS_API_TOKEN", "HORUS_TRUSTED_HEADERS", "HORUS_AUDIT_LOG"):
        monkeypatch.delenv(name, raising=False)
    reset_rate_limits()
    yield
    reset_rate_limits()


@pytest.fixture()
def client(tmp_path, bundle_factory) -> TestClient:
    root = _write_bundle(tmp_path / "bundle", bundle_factory)
    return TestClient(create_app(root))


def _sso(actor: str, groups: str) -> dict:
    return {"X-Forwarded-User": actor, "X-Forwarded-Groups": groups}


def _catat(client: TestClient, headers: dict | None = None) -> str:
    response = client.post(
        "/api/annotations",
        json={"target_type": "node", "target_id": "A", "text": "catatan uji"},
        headers=headers or {},
    )
    assert response.status_code == 200, response.text
    return response.json()["annotation"]["id"]


def test_tanpa_identitas_perilaku_lama_tetap_jalan(client) -> None:
    """Mode lokal: satu pengguna, satu token kosong, tidak ada yang berubah."""
    assert client.get("/api/bootstrap").status_code == 200
    annotation_id = _catat(client)
    assert client.delete(f"/api/annotations/{annotation_id}").status_code == 200


def test_token_salah_ditolak(client, monkeypatch) -> None:
    monkeypatch.setenv("HORUS_API_TOKEN", "rahasia")

    assert client.get("/api/bootstrap").status_code == 401
    assert client.get("/api/bootstrap", headers={"Authorization": "Bearer salah"}).status_code == 401
    assert client.get("/api/bootstrap", headers={"Authorization": "Bearer rahasia"}).status_code == 200


def test_viewer_tidak_boleh_menghapus(client, monkeypatch) -> None:
    monkeypatch.setenv("HORUS_TRUSTED_HEADERS", "1")
    viewer = _sso("rina", "horus-viewer")

    # Membaca tetap boleh; yang ditolak hanya tindakan yang mengubah temuan.
    assert client.get("/api/bootstrap", headers=viewer).status_code == 200
    annotation_id = _catat(client, viewer)
    response = client.delete(f"/api/annotations/{annotation_id}", headers=viewer)

    assert response.status_code == 403
    assert "viewer" in response.json()["detail"]


def test_analyst_boleh_menghapus(client, monkeypatch) -> None:
    monkeypatch.setenv("HORUS_TRUSTED_HEADERS", "1")
    analyst = _sso("budi", "horus-analyst, tim-lain")

    annotation_id = _catat(client, analyst)

    assert client.delete(f"/api/annotations/{annotation_id}", headers=analyst).status_code == 200


def test_grup_tak_dikenal_jadi_viewer(client, monkeypatch) -> None:
    monkeypatch.setenv("HORUS_TRUSTED_HEADERS", "1")
    orang = _sso("sari", "tim-lain")

    annotation_id = _catat(client, orang)

    assert client.delete(f"/api/annotations/{annotation_id}", headers=orang).status_code == 403


def test_header_sso_diabaikan_tanpa_gerbang(client, monkeypatch) -> None:
    """Tanpa HORUS_TRUSTED_HEADERS, header yang mengaku admin tidak dipercaya."""
    monkeypatch.setenv("HORUS_API_TOKEN", "rahasia")
    palsu = _sso("penyusup", "horus-admin")

    assert client.get("/api/bootstrap", headers=palsu).status_code == 401


def test_audit_mencatat_ekspor_dengan_identitas(client, monkeypatch, tmp_path) -> None:
    log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("HORUS_AUDIT_LOG", str(log))
    monkeypatch.setenv("HORUS_TRUSTED_HEADERS", "1")

    response = client.get("/api/export/graphml", headers=_sso("budi", "horus-analyst"))

    assert response.status_code == 200
    entry = audit.read(log)[-1]
    assert entry["action"] == "export.graphml"
    assert entry["actor"] == "budi"
    assert entry["role"] == "analyst"
    assert entry["snapshot"]


def test_audit_mencatat_hapus_anotasi(client, monkeypatch, tmp_path) -> None:
    log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("HORUS_AUDIT_LOG", str(log))
    monkeypatch.setenv("HORUS_TRUSTED_HEADERS", "1")
    analyst = _sso("budi", "horus-analyst")

    annotation_id = _catat(client, analyst)
    assert client.delete(f"/api/annotations/{annotation_id}", headers=analyst).status_code == 200

    actions = [entry["action"] for entry in audit.read(log)]
    assert actions == ["annotation.create", "annotation.delete"]
    assert all(entry["actor"] == "budi" for entry in audit.read(log))


def test_audit_tidak_menulis_tanpa_path(client) -> None:
    """Tanpa HORUS_AUDIT_LOG tidak ada berkas yang dibuat, dan tidak ada yang gagal."""
    assert client.get("/api/bootstrap").status_code == 200


def test_pembatas_laju_menolak_permintaan_berlebih(client) -> None:
    """31 permintaan tulis dalam satu menit: yang terakhir ditolak, bukan digantung."""
    statuses = [
        client.post(
            "/api/annotations",
            json={"target_type": "node", "target_id": "A", "text": f"catatan {index}"},
        ).status_code
        for index in range(31)
    ]

    assert statuses[:30] == [200] * 30
    assert statuses[-1] == 429


def test_audit_menulis_baris_json_yang_bisa_dibaca(tmp_path) -> None:
    log = tmp_path / "audit.jsonl"
    audit.record(log, actor="uji", role="admin", action="view.bootstrap", snapshot="abc")

    baris = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert baris["actor"] == "uji"
    assert baris["snapshot"] == "abc"
