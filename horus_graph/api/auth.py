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

import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping
from urllib.parse import urlparse

from fastapi import HTTPException, Request, WebSocket

logger = logging.getLogger(__name__)

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
    """
    Token HTTP hanya dari header.

    Query string pernah diterima demi tautan yang bisa dibuka langsung, tetapi
    ia ikut tercatat di log akses, riwayat, dan referer. Halaman tetap bisa
    dibuka dengan ?token=... karena skrip di halaman memindahkannya ke
    sessionStorage lalu mengirimnya sebagai header.
    """
    return _bearer(request.headers.get(HEADER, ""))


def websocket_token(websocket: WebSocket) -> str:
    """
    Token WS dari header bila ada, selain itu dari query.

    WebSocket di browser tidak bisa menyetel header, jadi query adalah satu-
    satunya jalur yang tersedia tanpa menambah endpoint tiket. Itu batasan yang
    diakui, bukan pilihan: selama server hanya bind ke loopback, token di query
    hanya berguna dari mesin yang sama.
    """
    header = _bearer(websocket.headers.get(HEADER, ""))
    return header or (websocket.query_params.get(WS_QUERY) or "")


def require_token(request: Request) -> None:
    """Dependency FastAPI. 401 bila identitas tidak sah."""
    request.state.identity = identity(request)


# --- identitas dan peran ----------------------------------------------------

ROLES = ("viewer", "analyst", "admin")
ROLE_RANK = {"viewer": 0, "analyst": 1, "admin": 2}

TRUSTED_ENV = "HORUS_TRUSTED_HEADERS"
USER_HEADER = "x-forwarded-user"
GROUPS_HEADER = "x-forwarded-groups"
# Grup yang dipetakan ke peran. Nama grup adalah kontrak dengan reverse proxy,
# bukan dengan aplikasi ini; tanpa grup yang dikenal, pengguna jadi viewer.
ROLE_GROUPS = {"horus-admin": "admin", "horus-analyst": "analyst", "horus-viewer": "viewer"}
LOCAL_ACTOR = "local"
TOKEN_ACTOR = "token"


@dataclass(frozen=True)
class Identity:
    """Siapa yang meminta, dengan peran apa, dan dari jalur mana."""

    actor: str
    role: str
    source: str

    def allows(self, minimum: str) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[minimum]


def trusted_headers_enabled() -> bool:
    """
    Header SSO hanya dipercaya bila dinyatakan eksplisit.

    Tanpa gerbang ini, siapa pun yang bisa mengirim header bisa mengaku admin —
    header hanya bermakna di belakang proxy yang menuliskannya.
    """
    return (os.environ.get(TRUSTED_ENV) or "").strip() in {"1", "true", "yes"}


def role_from_groups(raw: str) -> str:
    """Peran tertinggi dari daftar grup, dipisah koma atau spasi."""
    roles = {
        ROLE_GROUPS[token.strip().lower()]
        for token in (raw or "").replace(";", ",").split(",")
        for token in token.split()
        if token.strip().lower() in ROLE_GROUPS
    }
    if not roles:
        return "viewer"
    return max(roles, key=lambda role: ROLE_RANK[role])


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def _clean_actor(value: str) -> str:
    """
    Buang karakter yang bisa memalsukan baris log.

    Nama aktor ikut ditulis ke berkas audit dan ke log; baris baru di dalamnya
    akan membuat satu tindakan terbaca sebagai dua.
    """
    cleaned = "".join(ch for ch in (value or "") if ch.isprintable() and ch not in "\r\n")
    return cleaned.strip()[:128]


def resolve_identity(headers: Mapping[str, str], token: str) -> Identity:
    """
    Identitas pemanggil: SSO lewat proxy, token tunggal, atau mode lokal.

    Urutannya tetap, tetapi ada satu invarian yang mengikat: mode lokal hanya
    sah bila gerbang SSO mati dan token kosong. Begitu gerbang menyala, server
    menyatakan ada proxy yang mengautentikasi — dan proxy yang mengautentikasi
    selalu mengisi header. Permintaan tanpa header berarti tidak melewati proxy
    itu, jadi ia tidak punya identitas: 401, bukan admin.
    """
    trusted = trusted_headers_enabled()
    if trusted:
        actor = _clean_actor(headers.get(USER_HEADER) or "")
        if actor:
            return Identity(actor, role_from_groups(headers.get(GROUPS_HEADER) or ""), "sso")

    if not token_ok(token):
        raise _unauthorized("Token tidak valid.")
    if api_token():
        return Identity(TOKEN_ACTOR, "admin", "token")
    if trusted:
        raise _unauthorized("Header identitas tidak ada; gerbang SSO menyala.")
    return Identity(LOCAL_ACTOR, "admin", "local")


def identity(request: Request) -> Identity:
    return resolve_identity(request.headers, request_token(request))


def websocket_identity(websocket: WebSocket) -> Identity:
    """Jalur WS memakai aturan yang sama; handshake tidak punya status code."""
    return resolve_identity(websocket.headers, websocket_token(websocket))


def require_role(minimum: str) -> Callable[[Request], Identity]:
    """Dependency: 401 bila belum terautentikasi, 403 bila perannya kurang."""

    def dependency(request: Request) -> Identity:
        who = getattr(request.state, "identity", None) or identity(request)
        if not who.allows(minimum):
            raise HTTPException(
                status_code=403,
                detail=f"Peran {who.role} tidak cukup untuk tindakan ini; butuh {minimum}.",
            )
        request.state.identity = who
        return who

    return dependency


# --- pembatas laju ----------------------------------------------------------

RATE_WINDOW_SECONDS = 60.0
RATE_LIMIT = 30
_buckets: Dict[str, List[float]] = {}
_bucket_lock = threading.Lock()


def reset_rate_limits() -> None:
    """Kosongkan hitungan; dipakai tes supaya urutan tes tidak saling mengunci."""
    with _bucket_lock:
        _buckets.clear()


def check_rate(
    who: Identity,
    *,
    bucket: str,
    limit: int = RATE_LIMIT,
    window: float = RATE_WINDOW_SECONDS,
) -> bool:
    """
    Batas sederhana per identitas dan per jenis tindakan. False bila terlampaui.

    Disimpan di memori proses: cukup untuk satu server, dan sengaja tidak
    berpura-pura terdistribusi. Yang dijaga adalah satu klien yang mengulang
    permintaan menulis, bukan penyerang dengan banyak koneksi.
    """
    now = time.monotonic()
    key = f"{who.actor}|{bucket}"
    with _bucket_lock:
        stamps = [stamp for stamp in _buckets.get(key, []) if now - stamp < window]
        if len(stamps) >= limit:
            _buckets[key] = stamps
            return False
        stamps.append(now)
        _buckets[key] = stamps
    return True


def enforce_rate_limit(
    who: Identity,
    *,
    bucket: str,
    limit: int = RATE_LIMIT,
    window: float = RATE_WINDOW_SECONDS,
) -> None:
    """Versi HTTP: 429 dengan Retry-After, bukan nilai balik."""
    if not check_rate(who, bucket=bucket, limit=limit, window=window):
        raise HTTPException(
            status_code=429,
            detail=f"Terlalu banyak permintaan {bucket}; coba lagi dalam {int(window)} detik.",
            headers={"Retry-After": str(int(window))},
        )


def rate_limited(bucket: str, *, limit: int = RATE_LIMIT) -> Callable[[Request], None]:
    """Dependency pembatas laju untuk endpoint yang menulis."""

    def dependency(request: Request) -> None:
        who = getattr(request.state, "identity", None) or identity(request)
        enforce_rate_limit(who, bucket=bucket, limit=limit)

    return dependency


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
    if host in LOOPBACK_HOSTS:
        return
    if trusted_headers_enabled():
        # Header menang atas token, jadi siapa pun yang bisa menjangkau port ini
        # bisa mengaku admin. Tidak ditutup di sini: penutupnya daftar IP proxy.
        logger.warning(
            "bind_non_loopback_trusted host=%s: %s menyala, jadi header identitas "
            "dipercaya dari siapa pun yang bisa menjangkau port ini.",
            host,
            TRUSTED_ENV,
        )
        return
    if api_token():
        return
    raise RuntimeError(
        f"Menolak bind ke {host!r} tanpa {TOKEN_ENV}. "
        f"Setel {TOKEN_ENV}=<rahasia> atau bind ke 127.0.0.1."
    )
