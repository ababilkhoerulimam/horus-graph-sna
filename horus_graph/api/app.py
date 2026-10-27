"""
Aplikasi HTTP horus-graph.

Satu bundle per proses. Bundle dipilih saat start (argumen, `HORUS_BUNDLE`, atau
bundle terbaru di `data/bundles/`) sehingga tidak ada permintaan yang bisa
menukar dataset di tengah jalan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..copilot.ws import router as copilot_router
from .routes import router
from .state import resolve_bundle_path

# Visualizer statis. `index.html` memakai path relatif (`css/`, `js/`), jadi
# direktori `static` dipasang di akar, bukan `web/`.
WEB_DIR = Path(__file__).resolve().parents[1] / "web" / "static"

# Ambang 1 KB: cukup besar untuk melewati balasan kecil yang tidak untung
# dikompresi, cukup kecil untuk menangkap `/api/bootstrap` (140 KB) dan
# `index.html` (270 KB).
GZIP_MINIMUM_SIZE = 1024


def create_app(bundle: Optional[Path | str] = None) -> FastAPI:
    app = FastAPI(
        title="horus-graph",
        version=__version__,
        description="SNA engine: bundle masuk, jaringan keluar.",
    )
    # Payload bootstrap ~140 KB JSON dengan banyak kunci berulang; gzip
    # memotongnya menjadi ~20 KB tanpa mengubah isi.
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MINIMUM_SIZE)
    # Path diresolusi sekali di sini. Tanpa ini setiap permintaan memindai
    # `data/bundles/` dan memilih ulang "yang terbaru", sehingga menambah folder
    # saat server berjalan akan menukar dataset di tengah jalan.
    app.state.bundle_path = resolve_bundle_path(bundle)
    app.include_router(router)
    # Copilot selalu dipasang: jalur deterministiknya tidak butuh LLM, jadi
    # drawer tidak pernah menawarkan kanal yang tidak ada.
    app.include_router(copilot_router)
    _mount_web(app)
    return app


def _mount_web(app: FastAPI) -> None:
    """Visualizer statis, bila sudah dipasang. Tanpa itu API tetap jalan."""
    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


def run(
    bundle: Optional[Path | str] = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    import time

    import uvicorn

    from .state import BundleNotFound, get_state

    # Resolusi sekali saja: `get_state` di bawah dan `create_app` harus memakai
    # path yang sama, bukan memindai dua kali dan berpotensi memilih berbeda.
    resolved = resolve_bundle_path(bundle)

    # Bangun state sebelum server menerima permintaan: tanpa ini permintaan
    # pertama menunggu puluhan detik sementara browser sudah menampilkan UI.
    started = time.perf_counter()
    try:
        get_state(resolved)
    except BundleNotFound as exc:
        print(f"Peringatan: {exc}", flush=True)
    else:
        print(f"Bundle siap dalam {time.perf_counter() - started:.1f}s — {host}:{port}", flush=True)

    app = create_app(resolved)
    uvicorn.run(app, host=host, port=port, reload=reload)


app = create_app()
