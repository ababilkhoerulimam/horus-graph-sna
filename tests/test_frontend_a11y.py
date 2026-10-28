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

import frontend_source
import pytest

STATIC = Path(__file__).resolve().parents[1] / "horus_graph" / "web" / "static"
INDEX = STATIC / "index.html"
APP_CSS = STATIC / "css" / "app.css"
COPILOT_CSS = STATIC / "css" / "copilot.css"

# Batas bawah yang dipakai WCAG untuk teks normal, dan ukuran terkecil yang
# masih terbaca pada layar 1600x950 tanpa zoom.
MIN_FONT_PX = 11
MIN_TEXT_CONTRAST = 4.5


def _index() -> str:
    return frontend_source.source()


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
    for path in (INDEX, APP_CSS, COPILOT_CSS):
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
    for path in (INDEX, APP_CSS, COPILOT_CSS):
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


def test_drawer_copilot_adalah_dialog():
    markup = _index()
    drawer = re.search(r'<div[^>]*id="copilot-drawer"[^>]*>', markup)

    assert drawer is not None
    tag = drawer.group(0)
    assert 'role="dialog"' in tag
    assert 'aria-modal="true"' in tag
    assert 'aria-labelledby="copilot-title"' in tag
    assert 'id="copilot-title"' in markup


def test_drawer_menahan_fokus_dan_bisa_ditutup_escape():
    script = (STATIC / "js" / "copilot_ui.js").read_text(encoding="utf-8")

    assert 'event.key === "Escape"' in script
    # Fokus harus kembali ke tombol pembuka, bukan jatuh ke <body>.
    assert "toggleBtnEl.focus()" in script
    # Tab di ujung daftar harus berputar, bukan keluar dari dialog.
    assert "focusableItems" in script
    assert 'event.key !== "Tab"' in script


def test_simpul_graf_bisa_dijangkau_keyboard():
    markup = _index()

    assert '.attr("role", "button")' in markup
    assert '.attr("aria-label", d => nodeAriaLabel(d))' in markup
    # Roving tabindex: satu simpul di urutan Tab, sisanya lewat panah.
    assert '.attr("tabindex", (d, index) => (index === 0 ? 0 : -1))' in markup
    assert "function nodeAriaLabel(" in markup
    assert '<button type="button" class="sb-entity-row"' in markup


def test_toolbar_header_tiga_grup():
    """Sepuluh kontrol header dibagi ke tiga grup yang berlabel.

    Header setinggi 56px tidak punya tempat untuk judul grup yang ditulis
    panjang, jadi pengelompokan dinyatakan lewat pemisah dan atribut `title`.
    """
    markup = _index()
    controls = markup[markup.index('class="header-controls"') :]
    controls = controls[: controls.index("</header>")]

    grup = re.findall(r'data-group="([^"]+)"', controls)
    assert grup == ["Tampilan", "Filter", "Data"]

    # Setiap kontrol harus berada di dalam salah satu grup, bukan menempel
    # langsung di wadah tanpa pemisah.
    for control in ("dropdown-topic-wrap", "dropdown-color-mode-wrap", "dropdown-node-sizing-wrap",
                    "npmi-slider-group", "dropdown-edge-categories-wrap", "dropdown-media-lens-wrap",
                    "btn-header-filter", "btn-reset-view"):
        assert f'id="{control}"' in controls, control

    # Pemisah antar grup digambar CSS, jadi grup kedua dan ketiga butuh border.
    assert "border-left: 1px solid var(--border-subtle)" in markup


def test_kontrol_header_tidak_boleh_menyusut():
    """Label kontrol dipotong setengah lebih buruk daripada judul dipotong.

    Judul berasal dari metadata dan panjangnya tidak diketahui saat CSS ditulis,
    jadi blok judul yang menyusut (dengan elipsis); kontrol tidak.
    """
    markup = _index()
    block = markup[markup.index("/* Kontrol tidak boleh menyusut") :][:900]

    assert "flex: 0 0 auto" in block
    assert "text-overflow: ellipsis" in markup[
        markup.index(".header-title-block h1") : markup.index(".header-title-block h1") + 400
    ]
    for selector in (".dropdown-btn", ".sna-btn", ".mode-pill-btn"):
        start = markup.index(selector + " {")
        rule = markup[start : start + 600]
        assert "white-space: nowrap" in rule, selector


def _tanpa_komentar(markup: str) -> str:
    """Buang komentar dan baris log; keduanya bukan label yang dibaca pengguna.

    `//` hanya dibuang bila didahului spasi dan bukan bagian dari `://`, supaya
    URL di dalam skrip tidak ikut terpotong.
    """
    markup = re.sub(r"/\*.*?\*/", " ", markup, flags=re.S)
    markup = re.sub(r"<!--.*?-->", " ", markup, flags=re.S)
    markup = re.sub(r"(?m)\s//(?!/)[^\n]*", " ", markup)
    return "\n".join(baris for baris in markup.splitlines() if "console." not in baris)


def test_label_ui_satu_bahasa():
    """Label tampilan berbahasa Indonesia; istilah SNA tetap Inggris.

    Istilah teknis (degree, betweenness, Louvain, NPMI, epos) tidak diterjemahkan
    karena itulah nama metodenya di literatur. Yang dicek di sini adalah label
    antarmuka yang dulu tertinggal dalam bahasa Inggris.
    """
    markup = _tanpa_komentar(_index())
    skrip = " ".join(
        (STATIC / "js" / nama).read_text(encoding="utf-8")
        for nama in ("copilot_ui.js", "copilot_bridge.js")
    )
    terlarang = [
        "View Info", "Search Node", "Search entity", "Top 5", "All-Time",
        "Actor Network", "Live Connected", "Disconnected", "Reset View",
        "Export Image", "Compare", "Loading...",
    ]
    for frasa in terlarang:
        # Batas huruf: `localeCompare` bukan label, `>Compare<` iya.
        pola = re.compile(rf"(?<![A-Za-z]){re.escape(frasa)}(?![A-Za-z])")
        assert not pola.search(markup), f"label Inggris tersisa di index.html: {frasa}"
        assert not pola.search(skrip), f"label Inggris tersisa di skrip copilot: {frasa}"

    # Istilah SNA yang sengaja dipertahankan harus tetap ada.
    assert "Degree Centrality" in markup
    assert "Betweenness Centrality" in markup
