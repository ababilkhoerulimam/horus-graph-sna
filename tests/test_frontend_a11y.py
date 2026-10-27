"""
Pagar aksesibilitas frontend.

Sama seperti `test_frontend_integrity.py`: yang diperiksa adalah teks sumber,
bukan hasil render. Alasannya sama — berkas tampilan tidak punya tipe, dan satu
`<button>` tanpa nama aksesibel tidak akan menggagalkan tes Python mana pun.

Aturan yang dijaga di sini adalah yang punya kegagalan jelas dan murah dicek:
bahasa dokumen, nama aksesibel setiap tombol, pengumuman percakapan, dan
penghormatan pada permintaan mengurangi gerak.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "horus_graph" / "web" / "static"
INDEX = STATIC / "index.html"


def _index() -> str:
    return INDEX.read_text(encoding="utf-8")


def _buttons(markup: str) -> list[tuple[int, str, str]]:
    """(nomor baris, tag pembuka, isi) untuk setiap <button>."""
    found = []
    for match in re.finditer(r"<button\b[^>]*>(.*?)</button>", markup, re.S):
        line = markup[: match.start()].count("\n") + 1
        opening = match.group(0)[: match.group(0).index(">") + 1]
        found.append((line, opening, match.group(1)))
    return found


def test_dokumen_menyatakan_bahasa_indonesia():
    """`lang="en"` membuat pembaca layar memakai fonetika Inggris untuk teks Indonesia."""
    assert '<html lang="id">' in _index()


def test_permintaan_mengurangi_gerak_dihormati():
    markup = _index()

    assert "prefers-reduced-motion: reduce" in markup
    block = markup[markup.index("prefers-reduced-motion: reduce") :][:600]
    # Animasi berulang (denyut aura, garis putus-putus, spinner) harus berhenti,
    # bukan hanya dipercepat.
    assert "animation-iteration-count: 1" in block
    assert "animation-duration" in block


def test_semua_tombol_punya_nama_aksesibel():
    offenders = []
    for line, opening, inner in _buttons(_index()):
        if "aria-label=" in opening or "title=" in opening:
            continue
        if re.sub(r"<[^>]+>", "", inner).strip():
            continue  # teks tombol sendiri sudah menjadi nama
        offenders.append(f"index.html:{line}: {opening[:100]}")

    assert offenders == [], (
        "Tombol tanpa teks wajib punya aria-label atau title:\n" + "\n".join(offenders)
    )


def test_percakapan_diumumkan_ke_pembaca_layar():
    markup = _index()
    chat = re.search(r'<div[^>]*id="copilot-chat-body"[^>]*>', markup)

    assert chat is not None, "wadah percakapan tidak ditemukan"
    tag = chat.group(0)
    assert 'role="log"' in tag
    assert 'aria-live="polite"' in tag
    assert 'aria-relevant="additions"' in tag


def test_status_koneksi_diumumkan():
    markup = _index()
    status = re.search(r'<span[^>]*id="copilot-status-text"[^>]*>', markup)

    assert status is not None
    assert 'aria-live="polite"' in status.group(0)
