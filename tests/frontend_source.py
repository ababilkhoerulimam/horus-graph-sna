"""
Sumber frontend gabungan: markup dan modul skrip.

UI ini dulu satu berkas; V2.2 memindahkan CSS dan skrip ke berkas sendiri.
Tes yang memeriksa isi skrip harus membaca keduanya — kalau hanya index.html,
pagar yang menjaga panel tetap jujur akan lolos hanya karena fungsinya sudah
pindah berkas, dan itu kegagalan yang tidak terlihat.
"""

from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "horus_graph" / "web" / "static"

# Urutan mengikuti urutan pemuatan di index.html.
STYLES = ("css/app.css",)
APP_CHUNKS = tuple(sorted(f"js/app_{index:02d}.js" for index in range(1, 11)))
SCRIPTS = ("js/graph_canvas.js",) + APP_CHUNKS + ("js/copilot_ui.js", "js/copilot_bridge.js")


def read(relative: str) -> str:
    return (STATIC / relative).read_text(encoding="utf-8")


def source() -> str:
    """Markup, lalu CSS, lalu semua skrip; digabung dengan satu baris baru.

    Digabung karena tes memeriksa perilaku, bukan letak berkas: memindahkan
    sebuah aturan dari index.html ke css/app.css tidak boleh membuat pagar
    aksesibilitas lolos hanya karena teksnya tidak ditemukan lagi.
    """
    parts = [read("index.html")]
    parts.extend(read(name) for name in STYLES)
    parts.extend(read(name) for name in SCRIPTS)
    return "\n".join(parts)
