"""
Jejak audit tindakan yang mengubah atau mengekspos temuan.

Yang dicatat bukan setiap permintaan baca, melainkan tindakan yang membuat
sebuah temuan keluar dari server atau berubah di dalamnya: ekspor, laporan,
anotasi. Alasannya: log yang berisi semua hal sama tidak terpakainya dengan log
yang kosong.

Berkasnya append-only dalam arti tidak pernah ditulis ulang oleh aplikasi.
Rotasi dan penyimpanan jangka panjang bukan urusan modul ini; yang penting
setiap baris bisa dibaca mesin dan menyebut siapa, kapan, snapshot mana.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

AUDIT_ENV = "HORUS_AUDIT_LOG"


def audit_path() -> Optional[Path]:
    """Path berkas audit dari lingkungan; tanpa itu, audit tidak menulis apa pun."""
    raw = (os.environ.get(AUDIT_ENV) or "").strip()
    return Path(raw) if raw else None


def record(
    path: Optional[Path],
    *,
    actor: str,
    role: str,
    action: str,
    snapshot: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Tambahkan satu baris JSON.

    Kegagalan menulis tidak boleh menggagalkan permintaan yang sudah berhasil:
    pengguna tidak bisa memperbaiki disk penuh, dan menolak ekspor karena audit
    gagal justru mendorong orang mematikan audit. Kegagalannya dibiarkan naik
    ke log server lewat `OSError`, bukan ditelan.
    """
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "actor": actor,
            "role": role,
            "action": action,
            "snapshot": snapshot,
            "detail": detail or {},
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read(path: Path, limit: int = 50) -> List[Dict[str, Any]]:
    """Baris terakhir untuk diperiksa; dipakai tes dan pembacaan manual."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(line) for line in lines if line.strip()]
