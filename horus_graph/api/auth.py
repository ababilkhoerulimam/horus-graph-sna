"""
Autentikasi minimum: satu token, satu pemeriksaan, satu penjaga bind.

Repo ini alat satu pengguna. Yang dijaga di sini bukan multi-tenant, melainkan
tiga kesalahan yang mudah terjadi saat alat lokal dipindah ke server:

1. Server di-bind ke `0.0.0.0` tanpa sadar, lalu seluruh API terbuka di jaringan.
2. WebSocket dibuka dari halaman asing (cross-site WebSocket hijacking), karena
   handshake WS tidak tunduk pada same-origin policy.
3. Token diperiksa dengan `==`, yang membocorkan panjang lewat waktu.

Tanpa `HORUS_API_TOKEN`, perilakunya tetap seperti sebelumnya **selama** bind
hanya ke loopback. Begitu host bukan loopback, server menolak start.
"""

from __future__ import annotations

import os
import secrets
from urllib.parse import urlparse

from fastapi import HTTPException, Request, WebSocket

TOKEN_ENV = "HORUS_API_TOKEN"
HEADER = "authorization"
WS_QUERY = "token"

# Host yang dianggap lokal. `0.0.0.0` dan `::` sengaja tidak termasuk: keduanya
# membuka soket ke seluruh antarmuka jaringan.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def api_token() -> str:
    return (os.environ.get(TOKEN_ENV) or "").strip()


def token_ok(candidate: str) -> bool:
    """Bandingkan konstan-waktu. Tanpa token yang disetel, semuanya lolos."""
    expected = api_token()
    if not expected:
        return True
    return secrets.compare_digest((candidate or "").strip(), expected)


def _bearer(header_value: str) -> str:
    value = (header_value or "").strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def request_token(request: Request) -> str:
    header = _bearer(request.headers.get(HEADER, ""))
    return header or (request.query_params.get(WS_QUERY) or "")


def websocket_token(websocket: WebSocket) -> str:
    header = _bearer(websocket.headers.get(HEADER, ""))
    return header or (websocket.query_params.get(WS_QUERY) or "")


def require_token(request: Request) -> None:
    """Dependency FastAPI. 401 bila token tidak ada atau salah."""
    if token_ok(request_token(request)):
        return
    raise HTTPException(
        status_code=401,
        detail="Token tidak valid.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def origin_matches_host(websocket: WebSocket) -> bool:
    """Tolak handshake dari origin lain.

    Browser selalu mengirim `Origin`; klien non-browser tidak. Yang tidak
    mengirim dibiarkan lewat — tanpa browser, tidak ada halaman asing yang
    menumpang kredensial pengguna.
    """
    origin = (websocket.headers.get("origin") or "").strip()
    if not origin:
        return True
    host = (websocket.headers.get("host") or "").strip().lower()
    return urlparse(origin).netloc.lower() == host


def ensure_bind_is_safe(host: str) -> None:
    """Gagal cepat sebelum soket dibuka, bukan setelah data terbaca."""
    if host in LOOPBACK_HOSTS or api_token():
        return
    raise RuntimeError(
        f"Menolak bind ke {host!r} tanpa {TOKEN_ENV}. "
        f"Setel {TOKEN_ENV}=<rahasia> atau bind ke 127.0.0.1."
    )
