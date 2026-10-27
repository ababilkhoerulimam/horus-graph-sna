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

import pytest

STATIC = Path(__file__).resolve().parents[1] / "horus_graph" / "web" / "static"
INDEX = STATIC / "index.html"
COPILOT_CSS = STATIC / "css" / "copilot.css"

# Batas bawah yang dipakai WCAG untuk teks normal, dan ukuran terkecil yang
# masih terbaca pada layar 1600x950 tanpa zoom.
MIN_FONT_PX = 11
MIN_TEXT_CONTRAST = 4.5


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


def test_tidak_ada_teks_di_bawah_sebelas_piksel():
    offenders = []
    for path in (INDEX, COPILOT_CSS):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"font-size:\s*(\d+(?:\.\d+)?)px", text):
            size = float(match.group(1))
            if size < MIN_FONT_PX:
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.name}:{line}: {size}px")

    assert offenders == [], (
        f"Tidak ada teks di bawah {MIN_FONT_PX}px; label sekunder pun harus terbaca:\n"
        + "\n".join(offenders)
    )


def _luminance(hex_colour: str) -> float:
    raw = hex_colour.lstrip("#")
    channels = [int(raw[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground: str, background: str) -> float:
    high, low = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize(
    "foreground,background",
    [
        ("#8A99AE", "#050505"),  # --text-dim di atas latar aplikasi
        ("#8A99AE", "#0E121B"),  # --text-dim di atas panel
        ("#8A99AE", "#131B2B"),  # --text-dim di atas kartu copilot
    ],
)
def test_teks_sekunder_lolos_kontras(foreground, background):
    assert _contrast(foreground, background) >= MIN_TEXT_CONTRAST


def test_tidak_ada_teks_dengan_warna_gagal_kontras():
    """`#64748B` hanya 3,94:1 di atas panel; dulu dipakai untuk 25 label."""
    offenders = []
    for path in (INDEX, COPILOT_CSS):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"color:\s*#64748B", text, re.I):
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.name}:{line}")

    assert offenders == [], (
        "Teks sekunder memakai #8A99AE (6,47:1), bukan #64748B (3,94:1):\n"
        + "\n".join(offenders)
    )


def test_kpi_tidak_ditulis_dua_kali():
    """
    Satu angka, satu tempat.

    Dulu kartu atas, bilah sidebar, dan lencana kanvas sama-sama menulis
    `stat-active-*`, dengan dua definisi densitas yang berbeda (0,160 vs 0,162).
    """
    markup = _index()

    assert "sb-stats-bar" not in markup
    for writer in ("stat-active-nodes", "stat-active-edges"):
        assert markup.count(f'setText("{writer}"') == 1, f"{writer} ditulis lebih dari sekali"


def test_kamera_graf_tidak_menempel_di_pojok():
    """
    `translate(0, 0)` menaruh pusat graf (0,0) di pojok kiri-atas SVG.

    Itu bentuk yang dipakai tiga kamera berbeda sebelum diperbaiki, dan
    penyebab graf hanya tampil sebagai satu busur di tepi kanvas.
    """
    markup = _index()

    assert "translate(0, 0)" not in markup
    assert "translate(0,0)" not in markup
    assert "function getCloseFitTransform(" in markup
    assert "viewBox" in markup[markup.index("function getCloseFitTransform(") :][:1600]
    # Fit dipanggil sekali setelah tata letak berhenti, bukan hanya saat mode pindah.
    assert '.on("end"' in markup


def test_satu_kontrol_waktu_di_bilah():
    """Pil epos dan slider adalah satu kontrol; penanda peristiwa bukan kontrol kedua."""
    markup = _index()
    bar = markup[markup.index('class="hud-timeline"') :]
    bar = bar[: bar.index("timeline-milestone-banner")]

    assert bar.count('type="range"') == 1
    assert 'id="epoch-pills-wrap"' in bar
    # Pin peristiwa harus di luar bilah, kalau tidak tahunnya terbaca sebagai
    # deret kontrol waktu kedua.
    assert "timeline-key-event-pins" not in bar
