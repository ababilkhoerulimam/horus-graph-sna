"""
Observability: satu baris log per permintaan, satu id yang bisa dicari.

Tiga hal yang dijaga modul ini:

1. Setiap log punya `request_id`, sehingga baris dari logger berbeda untuk satu
   permintaan bisa disatukan lagi.
2. Log ditulis sebagai JSON — bisa dibaca mata, bisa juga di-parse.
3. `/metrics` menyajikan hitungan dan durasi dalam format teks Prometheus,
   tanpa menambah dependensi.

Angka disimpan di proses ini saja. Untuk satu bundle satu proses, itu cukup;
kalau nanti ada beberapa worker, yang dibutuhkan adalah exporter, bukan
struktur data yang lebih rumit di sini.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from contextvars import ContextVar
from typing import Any, Dict, List, Tuple

REQUEST_ID_HEADER = "x-request-id"
REQUEST_ID_MAX = 64
# Header masuk tidak dipercaya: hanya karakter aman yang diteruskan.
_REQUEST_ID_SAFE = re.compile(r"[^A-Za-z0-9._-]")

# Bucket durasi (detik). Cukup rapat di bawah 100 ms karena endpoint di sini
# menjawab dari state yang sudah dibangun saat start.
BUCKETS: Tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_lock = threading.Lock()
_requests: Dict[Tuple[str, int], int] = {}
_duration_sum = 0.0
_duration_count = 0
_bucket_counts: List[int] = [0] * len(BUCKETS)


def current_request_id() -> str:
    return request_id_var.get()


def reset_metrics() -> None:
    """Kosongkan penghitung. Dipakai tes supaya angka tidak menumpuk."""
    global _duration_sum, _duration_count
    with _lock:
        _requests.clear()
        _duration_sum = 0.0
        _duration_count = 0
        for index in range(len(_bucket_counts)):
            _bucket_counts[index] = 0


def record(method: str, status: int, duration: float) -> None:
    global _duration_sum, _duration_count
    with _lock:
        key = (method, status)
        _requests[key] = _requests.get(key, 0) + 1
        _duration_sum += duration
        _duration_count += 1
        for index, edge in enumerate(BUCKETS):
            if duration <= edge:
                _bucket_counts[index] += 1


def metrics_text() -> str:
    """Format teks Prometheus 0.0.4."""
    with _lock:
        requests = dict(_requests)
        buckets = list(_bucket_counts)
        total = _duration_count
        total_sum = _duration_sum

    lines = [
        "# HELP horus_http_requests_total Jumlah permintaan HTTP menurut metode dan status.",
        "# TYPE horus_http_requests_total counter",
    ]
    for (method, status), count in sorted(requests.items()):
        lines.append(
            f'horus_http_requests_total{{method="{method}",status="{status}"}} {count}'
        )

    lines += [
        "# HELP horus_http_request_duration_seconds Durasi permintaan HTTP.",
        "# TYPE horus_http_request_duration_seconds histogram",
    ]
    for edge, count in zip(BUCKETS, buckets, strict=False):
        lines.append(
            f'horus_http_request_duration_seconds_bucket{{le="{edge}"}} {count}'
        )
    lines.append(f'horus_http_request_duration_seconds_bucket{{le="+Inf"}} {total}')
    lines.append(f"horus_http_request_duration_seconds_sum {total_sum:.6f}")
    lines.append(f"horus_http_request_duration_seconds_count {total}")
    return "\n".join(lines) + "\n"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or current_request_id(),
        }
        for key in ("method", "path", "status", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class _RequestIdFilter(logging.Filter):
    """Tempelkan `request_id` ke setiap record, termasuk milik uvicorn."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = current_request_id()
        return True


_configured = False


def configure_logging(level: int = logging.INFO) -> None:
    """Sekali per proses. Handler uvicorn diganti agar ikut berformat JSON."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False
    _configured = True


def sanitize_request_id(value: str) -> str:
    cleaned = _REQUEST_ID_SAFE.sub("", value or "")[:REQUEST_ID_MAX]
    return cleaned or ""


class RequestContextMiddleware:
    """Beri id, catat durasi, dan kembalikan id yang sama ke klien.

    Ditulis sebagai middleware ASGI murni, bukan `BaseHTTPMiddleware`, supaya
    tidak ada task tambahan per permintaan.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self.logger = logging.getLogger("horus_graph.api.request")

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = ""
        for name, value in scope.get("headers") or ():
            if name == REQUEST_ID_HEADER.encode():
                request_id = sanitize_request_id(value.decode("latin-1"))
                break
        if not request_id:
            request_id = f"{time.time_ns() & 0xFFFFFFFF:08x}"

        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Dict[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
                headers = list(message.get("headers") or [])
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            duration = time.perf_counter() - started
            record(scope.get("method", "-"), status, duration)
            self.logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": scope.get("method", "-"),
                    "path": scope.get("path", "-"),
                    "status": status,
                    "duration_ms": round(duration * 1000, 1),
                },
            )
            request_id_var.reset(token)
