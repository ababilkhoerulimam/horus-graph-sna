"""
Pagar autentikasi: token, bind, dan handshake WebSocket.

Yang diperiksa bukan kekuatan kriptografi (tidak ada yang perlu diuji di sana),
melainkan tiga keputusan yang gampang dibalik tanpa sadar: API terbuka saat
token kosong, API tertutup saat token disetel, dan WebSocket menolak halaman
asing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from horus_graph.api.app import create_app
from horus_graph.api.auth import TOKEN_ENV, ensure_bind_is_safe, token_ok


@pytest.fixture()
def app_client(tmp_path, bundle_factory):
    from tests.test_api import _write_bundle

    root = _write_bundle(tmp_path / "bundle-auth", bundle_factory)
    return TestClient(create_app(root))


def test_tanpa_token_api_terbuka(app_client, monkeypatch):
    """Alat lokal tetap bisa dipakai tanpa konfigurasi apa pun."""
    monkeypatch.delenv(TOKEN_ENV, raising=False)

    assert app_client.get("/api/health").status_code == 200


def test_token_wajib_saat_disetel(app_client, monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "rahasia-uji")

    assert app_client.get("/api/health").status_code == 401
    assert app_client.get("/api/health", headers={"Authorization": "Bearer salah"}).status_code == 401

    benar = {"Authorization": "Bearer rahasia-uji"}
    assert app_client.get("/api/health", headers=benar).status_code == 200


def test_token_di_query_ditolak(app_client, monkeypatch):
    """Token di URL masuk log akses dan riwayat, jadi jalur itu ditutup."""
    monkeypatch.setenv(TOKEN_ENV, "rahasia-uji")

    assert app_client.get("/api/health?token=rahasia-uji").status_code == 401


def test_metrics_ikut_dijaga(app_client, monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "rahasia-uji")

    assert app_client.get("/metrics").status_code == 401
    assert app_client.get("/metrics", headers={"Authorization": "Bearer rahasia-uji"}).status_code == 200


def test_websocket_menolak_origin_asing(app_client, monkeypatch):
    """WebSocket tidak tunduk pada same-origin policy; Origin harus diperiksa."""
    monkeypatch.delenv(TOKEN_ENV, raising=False)

    with pytest.raises(WebSocketDisconnect):
        with app_client.websocket_connect(
            "/ws/copilot", headers={"origin": "https://jahat.example"}
        ) as socket:
            socket.receive_json()


def test_websocket_menolak_tanpa_token(app_client, monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "rahasia-uji")

    with pytest.raises(WebSocketDisconnect):
        with app_client.websocket_connect("/ws/copilot") as socket:
            socket.receive_json()

    with app_client.websocket_connect("/ws/copilot?token=rahasia-uji") as socket:
        assert socket.receive_json()["type"] == "SYSTEM_CONNECTED"


def test_bind_non_loopback_ditolak_tanpa_token(monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)

    ensure_bind_is_safe("127.0.0.1")
    ensure_bind_is_safe("localhost")
    with pytest.raises(RuntimeError):
        ensure_bind_is_safe("0.0.0.0")

    monkeypatch.setenv(TOKEN_ENV, "rahasia-uji")
    ensure_bind_is_safe("0.0.0.0")


def test_token_kosong_berarti_tidak_dijaga(monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    assert token_ok("apa saja") is True

    monkeypatch.setenv(TOKEN_ENV, "rahasia-uji")
    assert token_ok("") is False
    assert token_ok("rahasia-uji") is True
