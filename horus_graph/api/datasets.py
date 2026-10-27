"""
Daftar snapshot yang ada di disk.

Server ini menyajikan satu bundle per proses, jadi `/api/datasets` tidak untuk
menukar dataset di tengah jalan. Yang ditawarkan adalah daftar read-only: apa
saja yang tersedia di folder induk, dan mana yang sedang dipakai. Riwayat di
`.index.json` mencatat snapshot yang pernah dilihat, termasuk yang foldernya
sudah tidak ada — supaya angka lama tetap bisa ditelusuri asalnya.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..contract import schema
from ..contract.models import Manifest
from ..contract.snapshot import snapshot_id

INDEX_NAME = ".index.json"


def describe(root: Path) -> Optional[Dict[str, Any]]:
    """Ringkasan satu folder bundle; `None` bila manifest tidak terbaca."""
    manifest_path = root / schema.MANIFEST
    if not manifest_path.is_file():
        return None
    try:
        manifest = Manifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
    except Exception:  # manifest rusak: lewati, jangan gagalkan seluruh daftar
        return None

    presentation = manifest.presentation
    return {
        "snapshot_id": manifest.snapshot_id or snapshot_id(manifest),
        "dataset_id": manifest.dataset_id,
        "folder": root.name,
        "snapshot_at": manifest.snapshot_at.isoformat(),
        "counts": dict(manifest.counts),
        "title": presentation.title if presentation else None,
    }


def list_snapshots(parent: Path) -> List[Dict[str, Any]]:
    """Semua bundle di `parent`, terbaru dulu. Folder `_`/`.` dilewati."""
    if not parent.is_dir():
        return []

    entries: List[Dict[str, Any]] = []
    for child in sorted(parent.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        described = describe(child)
        if described is not None:
            entries.append(described)

    entries.sort(key=lambda item: item["snapshot_at"], reverse=True)
    return entries


def read_index(parent: Path) -> List[Dict[str, Any]]:
    path = parent / INDEX_NAME
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = payload.get("snapshots") if isinstance(payload, dict) else None
    return entries if isinstance(entries, list) else []


def update_index(parent: Path, entries: List[Dict[str, Any]]) -> Optional[Path]:
    """Gabungkan snapshot yang terlihat sekarang ke riwayat.

    Tulis lewat berkas sementara lalu `os.replace`, supaya proses yang mati di
    tengah penulisan tidak meninggalkan JSON setengah jadi.
    """
    if not parent.is_dir():
        return None

    now = datetime.now(timezone.utc).isoformat()
    riwayat: Dict[str, Dict[str, Any]] = {}
    for item in read_index(parent):
        snapshot = item.get("snapshot_id")
        if isinstance(snapshot, str) and snapshot:
            riwayat[snapshot] = dict(item)
    for entry in entries:
        snapshot = entry["snapshot_id"]
        merged = dict(riwayat.get(snapshot, {}))
        merged.update(entry)
        merged["present"] = True
        merged["last_seen"] = now
        riwayat[snapshot] = merged
    for snapshot, item in riwayat.items():
        if snapshot not in {entry["snapshot_id"] for entry in entries}:
            item["present"] = False

    ordered = sorted(
        riwayat.values(), key=lambda item: item.get("snapshot_at") or "", reverse=True
    )
    path = parent / INDEX_NAME
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=parent, delete=False, suffix=".tmp"
        ) as handle:
            json.dump({"snapshots": ordered}, handle, indent=2, ensure_ascii=False)
            temp_name = handle.name
        os.replace(temp_name, path)
    except OSError:
        return None
    return path
