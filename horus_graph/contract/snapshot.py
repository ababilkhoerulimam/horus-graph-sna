"""
Identitas snapshot: satu hash untuk satu isi bundle.

`schema.snapshot_id` tidak memakai path, mtime, atau urutan penulisan. Yang
di-hash adalah fakta yang menentukan angka di layar: dataset_id, versi kontrak,
rentang tanggal, jumlah baris, dan sha256 tiap berkas. Dua folder berisi bundle
yang sama menghasilkan id yang sama; satu baris yang berubah menghasilkan id
yang berbeda.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from .models import Manifest

# Panjang 16 heksadesimal (64 bit). Cukup untuk membedakan snapshot dalam satu
# instalasi, cukup pendek untuk ditulis di UI dan nama berkas.
SNAPSHOT_LENGTH = 16


def snapshot_id(manifest: Manifest) -> str:
    """Hash isi, bukan hash berkas manifest (yang memuat mtime tidak stabil)."""
    payload: Dict[str, Any] = {
        "dataset_id": manifest.dataset_id,
        "contract_version": manifest.contract_version,
        "date_range": [manifest.date_range.start.isoformat(), manifest.date_range.end.isoformat()],
        "counts": dict(sorted(manifest.counts.items())),
        "file_sha256": dict(sorted(manifest.file_sha256.items())),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:SNAPSHOT_LENGTH]
