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
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

AUDIT_ENV = "HORUS_AUDIT_LOG"

logger = logging.getLogger(__name__)

# Windows tidak menjamin append atomik untuk penulis bersamaan, dan dua baris
# yang saling menyisip membuat berkasnya tidak bisa dibaca mesin.
_LOCK = threading.Lock()
_FAILURES = 0


def audit_path() -> Optional[Path]:
    """Path berkas audit dari lingkungan; tanpa itu, audit tidak menulis apa pun."""
    raw = (os.environ.get(AUDIT_ENV) or "").strip()
    return Path(raw) if raw else None


def failures() -> int:
    """Berapa kali penulisan gagal sejak proses mulai. Dipakai tes dan metrik."""
    with _LOCK:
        return _FAILURES


def reset_failures() -> None:
    global _FAILURES
    with _LOCK:
        _FAILURES = 0


def _line(actor: str, role: str, action: str, snapshot: Optional[str], detail: Optional[Dict[str, Any]]) -> str:
    return json.dumps(
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


def _swallow(line: str, exc: OSError) -> None:
    """
    Kegagalan tulis tidak boleh menggagalkan permintaan yang sudah berhasil.

    Menolak ekspor karena disk penuh justru mendorong orang mematikan audit.
    Tapi kegagalannya juga tidak boleh hilang: baris yang seharusnya masuk
    berkas ditulis ke log server apa adanya, dan penghitungnya dinaikkan.
    """
    global _FAILURES
    with _LOCK:
        _FAILURES += 1
    logger.error("audit.write_failed %s", line, exc_info=exc)
    try:
        from .observability import record_audit_failure

        record_audit_failure()
    except Exception:  # pragma: no cover - metrik tidak boleh menjatuhkan audit
        logger.debug("audit.counter_failed", exc_info=True)


def record(
    path: Optional[Path],
    *,
    actor: str,
    role: str,
    action: str,
    snapshot: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Tambahkan satu baris JSON. True bila tertulis, False bila gagal.

    Pemanggil memutuskan arti kegagalan itu: untuk tindakan yang hanya membaca
    atau idempoten, permintaan tetap dijawab berhasil dengan penanda; untuk
    tindakan yang tidak bisa diulang tanpa efek ganda, audit ditulis lebih dulu
    dan kegagalannya membatalkan tindakan.
    """
    if path is None:
        return True
    line = _line(actor, role, action, snapshot, detail)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except OSError as exc:
        _swallow(line, exc)
        return False
    return True


def read(path: Path, limit: int = 50) -> List[Dict[str, Any]]:
    """Baris terakhir untuk diperiksa; dipakai tes dan pembacaan manual."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(line) for line in lines if line.strip()]
