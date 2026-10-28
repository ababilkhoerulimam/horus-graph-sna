"""
Status aplikasi: satu bundle dimuat sekali, satu jaringan dibangun sekali.

Semua endpoint membaca objek yang sama, sehingga angka di UI tidak mungkin
berbeda antar panel — perbedaan seperti itu biasanya berasal dari dua proses
build yang berjalan pada waktu berbeda.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from ..analysis import motifs as motif_artifact
from ..core.anomaly import AnomalyReport, detect_anomalies
from ..core.bipartite import TopicActorBundle, build_bipartite
from ..core.build import NetworkBundle, build_network
from ..core.sequence import build_sequence
from ..core.temporal import TemporalBundle, build_temporal
from ..io.bundle import DataBundle, load_bundle
from ..presentation import Presentation, resolve_presentation

BUNDLE_ENV = "HORUS_BUNDLE"
DEFAULT_BUNDLE_DIR = Path("data") / "bundles"


class BundleNotFound(RuntimeError):
    """Tidak ada bundle yang bisa dipakai; UI harus menampilkan empty state."""


@dataclass(frozen=True)
class AppState:
    root: Path
    bundle: DataBundle
    presentation: Presentation
    network: NetworkBundle
    temporal: TemporalBundle
    bipartite: TopicActorBundle
    anomaly: AnomalyReport
    build_seconds: float
    # Artefak rich-club, bila sudah dihitung di luar server. Dibaca sekali saat
    # bundle dimuat: ini langkah build, bukan kerja per permintaan.
    motifs: Optional[Dict[str, Any]] = None
    # Seri sentralitas lintas jendela epos. Dihitung sekali saat muat: peringkat
    # atas beberapa jendela tidak berubah selama bundle tidak berubah.
    sequence: Optional[Dict[str, Any]] = None


def resolve_bundle_path(explicit: Optional[Path | str] = None) -> Optional[Path]:
    """
    Urutan: argumen eksplisit → `HORUS_BUNDLE` → bundle terbaru di data/bundles/.

    Folder yang diawali garis bawah dilewati supaya arsip tidak pernah terpilih.
    """
    if explicit:
        return Path(explicit)
    env = os.environ.get(BUNDLE_ENV)
    if env:
        return Path(env)
    if not DEFAULT_BUNDLE_DIR.is_dir():
        return None

    candidates = [
        path
        for path in DEFAULT_BUNDLE_DIR.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    ]
    if not candidates:
        return None
    return max(candidates, key=_modified)


def _modified(path: Path) -> float:
    manifest = path / "manifest.json"
    return manifest.stat().st_mtime if manifest.exists() else path.stat().st_mtime


@lru_cache(maxsize=2)
def load_state(path: str) -> AppState:
    """Muat dan hitung semuanya. Hasil di-cache per path."""
    started = time.perf_counter()
    root = Path(path)
    bundle = load_bundle(root)
    temporal = build_temporal(bundle)
    state = AppState(
        root=root,
        bundle=bundle,
        presentation=resolve_presentation(bundle),
        network=build_network(bundle),
        temporal=temporal,
        bipartite=build_bipartite(bundle),
        anomaly=detect_anomalies(bundle),
        build_seconds=round(time.perf_counter() - started, 3),
        motifs=motif_artifact.read_artifact(root),
        sequence=build_sequence(temporal),
    )
    return state


def get_state(explicit: Optional[Path | str] = None) -> AppState:
    """State untuk satu bundle.

    `explicit` sebaiknya sudah berupa path hasil `resolve_bundle_path`, seperti
    yang disimpan `create_app` di `app.state.bundle_path`. Bila None, pemindaian
    `data/bundles/` hanya terjadi ketika server memang start tanpa bundle —
    bukan pada setiap permintaan.
    """
    path = resolve_bundle_path(explicit)
    if path is None:
        raise BundleNotFound(
            "Belum ada bundle. Letakkan di data/bundles/ atau set HORUS_BUNDLE."
        )
    if not path.exists():
        # Hanya nama folder: pesan ini ikut terkirim ke klien sebagai 503.
        raise BundleNotFound(f"Bundle tidak ditemukan: {path.name}")
    return load_state(str(path))
