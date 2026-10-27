"""
Inferensi sebagai artefak, bukan sebagai kerja per permintaan.

Null model dan bootstrap menjawab pertanyaan yang paling sering ditanyakan
penguji: "0,3872 itu tinggi atau tidak?". Keduanya juga mahal — pada bundle
77 simpul, 200 resampling null model memakan ~50 detik dan bootstrap artikel
~22 detik. Menjalankannya di dalam handler HTTP berarti satu permintaan
menggantung lebih dari satu menit, dan UI tidak punya cara membedakan
"sedang dihitung" dari "macet".

Karena itu hasilnya diperlakukan seperti artefak bundle lain:

1. Bila `inference.json` sudah ada di folder bundle, endpoint membacanya.
2. Bila belum, perhitungan dijalankan sekali di latar belakang dan endpoint
   langsung menjawab `computing`; UI memantau sampai `ready`.
3. `horus-graph inference --write` menghitung di luar server, supaya proses
   produksi tidak pernah membayar biayanya secara interaktif.

Seed tetap, karena angka yang berubah setiap kali panel dibuka bukan bukti.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.build import NetworkBundle
from ..enhance.bootstrap import bootstrap_network
from ..enhance.nullmodel import degree_preserving_null
from ..enhance.reporting import reporting_block
from ..io.bundle import DataBundle

ARTIFACT_NAME = "inference.json"
DEFAULT_RESAMPLES = 200
DEFAULT_BOOTSTRAP_RESAMPLES = 200
DEFAULT_SEED = 42
DEFAULT_CI = 90.0
METHOD_VERSION = 1


@dataclass(frozen=True)
class InferenceParams:
    """Parameter yang menentukan isi artefak; ikut disimpan agar bisa diulang."""

    resamples: int = DEFAULT_RESAMPLES
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES
    seed: int = DEFAULT_SEED
    ci: float = DEFAULT_CI
    method_version: int = METHOD_VERSION

    def as_dict(self) -> Dict[str, Any]:
        return {
            "resamples": self.resamples,
            "bootstrap_resamples": self.bootstrap_resamples,
            "seed": self.seed,
            "ci": self.ci,
            "method_version": self.method_version,
        }


def artifact_path(bundle_root: Path) -> Path:
    return Path(bundle_root) / ARTIFACT_NAME


def compute(
    bundle: DataBundle,
    network: NetworkBundle,
    params: Optional[InferenceParams] = None,
) -> Dict[str, Any]:
    """Hitung blok inferensi lengkap. Ini yang mahal; panggil di luar handler."""
    config = params or InferenceParams()
    null = degree_preserving_null(
        network, resamples=config.resamples, seed=config.seed
    )
    bootstrap = bootstrap_network(
        network, resamples=config.bootstrap_resamples, seed=config.seed, ci=config.ci
    )
    block = reporting_block(bundle, network, null=null, bootstrap=bootstrap, seed=config.seed)
    inference = dict(block.get("inference") or {})
    return {
        "method_version": config.method_version,
        "params": config.as_dict(),
        "inference": inference,
    }


def read_artifact(bundle_root: Path) -> Optional[Dict[str, Any]]:
    """
    Artefak yang ada di disk, atau None.

    Berkas yang tidak terbaca diperlakukan sebagai tidak ada: lebih baik panel
    menghitung ulang daripada menampilkan angka dari berkas yang rusak.
    """
    path = artifact_path(bundle_root)
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or "inference" not in payload:
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


def stale(payload: Dict[str, Any], params: InferenceParams) -> bool:
    """
    Artefak lama dengan parameter lain bukan jawaban untuk pertanyaan ini.

    Tanpa pemeriksaan ini, panel bisa menampilkan p-value dari 50 resampling
    sambil menuliskan resolusi 200 resampling.
    """
    stored = payload.get("params") or {}
    return any(stored.get(key) != value for key, value in params.as_dict().items())


class InferenceJobs:
    """
    Satu perhitungan latar belakang per kunci, tidak pernah dua.

    Tanpa penjaga ini, membuka panel dua kali berarti dua perhitungan 50 detik
    yang saling berebut CPU dan menulis artefak yang sama.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: Dict[str, threading.Thread] = {}
        self._results: Dict[str, Dict[str, Any]] = {}
        self._errors: Dict[str, str] = {}

    def status(self, key: str) -> str:
        with self._lock:
            if key in self._results:
                return "ready"
            if key in self._errors:
                return "failed"
            if key in self._running:
                return "computing"
            return "absent"

    def result(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._results.get(key)

    def error(self, key: str) -> Optional[str]:
        with self._lock:
            return self._errors.get(key)

    def forget(self, key: str) -> None:
        with self._lock:
            self._results.pop(key, None)
            self._errors.pop(key, None)

    def start(self, key: str, work, *, on_done=None) -> bool:
        """
        Jalankan `work()` di thread latar. False bila sudah berjalan.

        `on_done(payload)` dipanggil setelah sukses; kegagalan disimpan sebagai
        pesan, bukan dilempar, karena tidak ada pemanggil yang bisa menangkapnya.
        """
        with self._lock:
            if key in self._running:
                return False
            thread = threading.Thread(target=self._run, args=(key, work, on_done), daemon=True)
            self._running[key] = thread
        thread.start()
        return True

    def _run(self, key: str, work, on_done) -> None:
        try:
            payload = work()
        except Exception as exc:  # noqa: BLE001 - pesan diteruskan ke UI
            with self._lock:
                self._errors[key] = f"{type(exc).__name__}: {exc}"
                self._running.pop(key, None)
            return
        if on_done is not None:
            try:
                on_done(payload)
            except Exception:  # noqa: BLE001 - artefak gagal ditulis bukan alasan gagal
                pass
        with self._lock:
            self._results[key] = payload
            self._running.pop(key, None)

    def wait(self, key: str, timeout: float = 300.0) -> None:
        """Untuk tes: tunggu sampai perhitungan selesai."""
        with self._lock:
            thread = self._running.get(key)
        if thread is not None:
            thread.join(timeout)
