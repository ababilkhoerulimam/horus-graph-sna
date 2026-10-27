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
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..copilot.ws import router as copilot_router
from .routes import router

# Visualizer statis. `index.html` memakai path relatif (`css/`, `js/`), jadi
# direktori `static` dipasang di akar, bukan `web/`.
WEB_DIR = Path(__file__).resolve().parents[1] / "web" / "static"


def create_app(bundle: Optional[Path | str] = None) -> FastAPI:
    app = FastAPI(
        title="horus-graph",
        version=__version__,
        description="SNA engine: bundle masuk, jaringan keluar.",
    )
    app.state.bundle_path = bundle
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

    # Bangun state sebelum server menerima permintaan: tanpa ini permintaan
    # pertama menunggu puluhan detik sementara browser sudah menampilkan UI.
    started = time.perf_counter()
    try:
        get_state(bundle)
    except BundleNotFound as exc:
        print(f"Peringatan: {exc}", flush=True)
    else:
        print(f"Bundle siap dalam {time.perf_counter() - started:.1f}s — {host}:{port}", flush=True)

    app = create_app(bundle)
    uvicorn.run(app, host=host, port=port, reload=reload)


app = create_app()
