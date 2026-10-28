"""
Rich-club sebagai artefak.

Sensus triad murah (~0,1 detik) sehingga dihitung setiap build. Rich-club
berbeda: pembanding acak yang membuat angkanya bisa dibaca butuh ~1 detik pada
77 simpul (10 pembanding, 10 pertukaran sisi per sisi), dan pada graf 10 ribu
simpul biayanya menit. Karena itu hasilnya
disimpan seperti artefak bundle lain:

1. `horus-graph motifs <bundle> --write` menghitung di luar server.
2. `/api/bootstrap` membaca `motifs.json` saat bundle dimuat; tanpa berkas itu
   blok rich-club berstatus `awaiting_input` beserta alasannya.
3. Kurva mentah tidak pernah dikirim sendirian: ia naik secara konstruksi dan
   akan terbaca sebagai bukti klub orang kaya padahal bukan.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..core import motifs
from ..core.build import NetworkBundle

ARTIFACT_NAME = "motifs.json"
DEFAULT_REPLICATES = motifs.DEFAULT_RICH_CLUB_REPLICATES
DEFAULT_SWAPS_PER_EDGE = motifs.DEFAULT_SWAPS_PER_EDGE
DEFAULT_SEED = 42
METHOD_VERSION = 1


@dataclass(frozen=True)
class MotifParams:
    """Parameter yang menentukan isi artefak; ikut disimpan agar bisa diulang."""

    replicates: int = DEFAULT_REPLICATES
    swaps_per_edge: int = DEFAULT_SWAPS_PER_EDGE
    seed: int = DEFAULT_SEED
    method_version: int = METHOD_VERSION

    def as_dict(self) -> Dict[str, Any]:
        return {
            "replicates": self.replicates,
            "swaps_per_edge": self.swaps_per_edge,
            "seed": self.seed,
            "method_version": self.method_version,
        }


def artifact_path(bundle_root: Path) -> Path:
    return Path(bundle_root) / ARTIFACT_NAME


def compute(network: NetworkBundle, params: Optional[MotifParams] = None) -> Dict[str, Any]:
    """Hitung sensus triad dan rich-club ternormalisasi. Ini yang mahal."""
    config = params or MotifParams()
    triads = motifs.triad_census(network.graph)
    club = motifs.rich_club(
        network.graph,
        normalize=True,
        replicates=config.replicates,
        swaps_per_edge=config.swaps_per_edge,
        seed=config.seed,
    )
    return {
        "method_version": config.method_version,
        "params": config.as_dict(),
        "motifs": motifs.motif_block(triads, club),
    }


def read_artifact(bundle_root: Path) -> Optional[Dict[str, Any]]:
    """Artefak yang ada di disk, atau None. Berkas rusak diperlakukan tidak ada."""
    path = artifact_path(bundle_root)
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or "motifs" not in payload:
        return None
    return payload


def write_artifact(bundle_root: Path, payload: Dict[str, Any]) -> Path:
    """Tulis atomik: berkas sementara di folder yang sama, lalu `replace`."""
    path = artifact_path(bundle_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
    os.replace(temporary, path)
    return path


def stale(payload: Dict[str, Any], params: MotifParams) -> bool:
    """Artefak dengan parameter lain bukan jawaban untuk pertanyaan ini."""
    stored = payload.get("params") or {}
    return any(stored.get(key) != value for key, value in params.as_dict().items())
