"""
Berkas `.env` lokal tanpa dependensi.

Kredensial tidak boleh ditulis di kode atau di `pyproject.toml`, dan menambah
`python-dotenv` hanya untuk membaca `KEY=VALUE` tidak sepadan. Parser ini
sengaja kecil: satu baris satu pasangan, `#` untuk komentar, tanda kutip di ujung
nilai dibuang.

Variabel yang sudah ada di lingkungan **tidak** ditimpa. Urutannya penting:
nilai dari shell (atau dari Docker) selalu menang atas berkas lokal, sehingga
berkas ini tidak bisa diam-diam mengubah konfigurasi produksi.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_FILE = ".env.local"


def load_env_file(path: str | Path = DEFAULT_ENV_FILE) -> int:
    """Muat pasangan `KEY=VALUE` dari `path`; kembalikan jumlah variabel baru."""
    berkas = Path(path)
    if not berkas.is_file():
        return 0

    loaded = 0
    for baris in berkas.read_text(encoding="utf-8").splitlines():
        baris = baris.strip()
        if not baris or baris.startswith("#") or "=" not in baris:
            continue
        key, _, value = baris.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip("\"'")
        loaded += 1
    return loaded
