"""
Catatan analis per snapshot.

Anotasi adalah satu-satunya tulisan manusia di sistem ini: semuanya yang lain
dihitung dari bundle. Karena itu ia disimpan **di luar** folder bundle, dengan
nama berkas `snapshot_id` — bukan nama dataset atau stempel waktu. Dua akibat
yang diinginkan:

1. Menghapus atau menyunting anotasi tidak pernah menyentuh berkas bundle.
2. Anotasi menempel pada isi, bukan pada folder. Bundle yang dipindah atau
   ditulis ulang dengan isi sama tetap menemukan catatannya; satu baris yang
   berubah menghasilkan `snapshot_id` baru, dan anotasi lama tidak lagi
   diklaim sebagai miliknya.

Id catatan diturunkan dari isinya sendiri (target + teks), sehingga menekan
tombol simpan dua kali tidak menghasilkan catatan ganda.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

DIR_ENV = "HORUS_ANNOTATIONS_DIR"
DEFAULT_DIR = Path("data") / "annotations"
TARGET_TYPES = ("node", "edge", "graph")
TEXT_MAX_CHARS = 2000
ID_LENGTH = 12

_LOCK = threading.Lock()


class AnnotationError(ValueError):
    """Masukan tidak sah; pesannya aman ditampilkan ke pengguna."""


@dataclass(frozen=True)
class Annotation:
    id: str
    snapshot_id: str
    target_type: str
    target_id: str
    text: str
    created_at: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "snapshot_id": self.snapshot_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "text": self.text,
            "created_at": self.created_at,
        }


def store_dir() -> Path:
    """Folder anotasi; dapat dipindah lewat env tanpa menyentuh kode."""
    override = os.environ.get(DIR_ENV)
    return Path(override) if override else DEFAULT_DIR


def path_for(snapshot_id: str) -> Path:
    # `snapshot_id` datang dari manifest, bukan dari klien, tetapi tetap
    # disaring: nama berkas yang mengandung pemisah path akan menulis ke luar
    # folder ini.
    if not snapshot_id or "/" in snapshot_id or "\\" in snapshot_id or ".." in snapshot_id:
        raise AnnotationError("snapshot_id tidak sah")
    return store_dir() / f"{snapshot_id}.json"


def load(snapshot_id: str) -> List[Annotation]:
    path = path_for(snapshot_id)
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        # Berkas rusak bukan alasan menjatuhkan panel; anggap belum ada catatan.
        return []
    items = payload.get("annotations") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        try:
            result.append(
                Annotation(
                    id=str(item["id"]),
                    snapshot_id=str(item.get("snapshot_id", snapshot_id)),
                    target_type=str(item["target_type"]),
                    target_id=str(item["target_id"]),
                    text=str(item["text"]),
                    created_at=str(item["created_at"]),
                )
            )
        except (KeyError, TypeError):
            continue
    return result


def add(snapshot_id: str, target_type: str, target_id: str, text: str) -> Annotation:
    """Tambah satu catatan. Idempoten: isi yang sama tidak menambah baris baru."""
    if target_type not in TARGET_TYPES:
        raise AnnotationError(f"target_type harus salah satu dari: {', '.join(TARGET_TYPES)}")
    body = (text or "").strip()
    if not body:
        raise AnnotationError("catatan tidak boleh kosong")
    if len(body) > TEXT_MAX_CHARS:
        raise AnnotationError(f"catatan melebihi {TEXT_MAX_CHARS} karakter")
    if target_type != "graph" and not (target_id or "").strip():
        raise AnnotationError("target_id wajib untuk catatan per simpul/sisi")

    clean_target = (target_id or "").strip()
    identifier = _identifier(target_type, clean_target, body)

    with _LOCK:
        existing = load(snapshot_id)
        for item in existing:
            if item.id == identifier:
                return item
        record = Annotation(
            id=identifier,
            snapshot_id=snapshot_id,
            target_type=target_type,
            target_id=clean_target,
            text=body,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        _write(snapshot_id, [*existing, record])
    return record


def remove(snapshot_id: str, annotation_id: str) -> bool:
    """Hapus satu catatan. False bila id tidak ada."""
    with _LOCK:
        existing = load(snapshot_id)
        remaining = [item for item in existing if item.id != annotation_id]
        if len(remaining) == len(existing):
            return False
        _write(snapshot_id, remaining)
    return True


def _identifier(target_type: str, target_id: str, text: str) -> str:
    blob = f"{target_type}\x00{target_id}\x00{text}".encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:ID_LENGTH]


def _write(snapshot_id: str, items: List[Annotation]) -> None:
    """Tulis atomik: berkas sementara di folder yang sama, lalu `replace`."""
    path = path_for(snapshot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "annotations": [item.as_dict() for item in items],
    }
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def summarise(items: List[Annotation]) -> Dict[str, Any]:
    """Ringkasan untuk laporan: jumlah per target, tanpa menyalin isinya."""
    counts: Dict[str, int] = {}
    for item in items:
        counts[item.target_type] = counts.get(item.target_type, 0) + 1
    return {"total": len(items), "by_target": counts}
