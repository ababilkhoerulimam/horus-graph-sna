"""
Pagar XSS frontend.

Sama seperti pagar lain di folder ini: yang diperiksa adalah teks sumber. Yang
dijaga di sini adalah jalur yang membawa data dari luar — jawaban model dan
judul sesi buatan pengguna — ke `innerHTML`.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "horus_graph" / "web" / "static"
COPILOT_JS = STATIC / "js" / "copilot_ui.js"


def _script() -> str:
    return COPILOT_JS.read_text(encoding="utf-8")


def test_markdown_disaring_sebelum_dirender():
    """`marked` meneruskan HTML mentah dari model; harus lewat allowlist."""
    script = _script()

    assert "function sanitizeHtml(" in script
    assert "ALLOWED_TAGS" in script and "ALLOWED_ATTRS" in script

    render = script[script.index("function renderMarkdownAndMath(") :]
    render = render[: render.index("function appendUserMessage(")]
    assert "sanitizeHtml(htmlOutput)" in render

    # Penyaringan harus terjadi sebelum token KaTeX diganti HTML jadi:
    # keluaran KaTeX (`trust: false`) tidak membawa HTML dari masukan, tapi
    # keluaran markdown membawa.
    posisi_saring = render.index("sanitizeHtml(htmlOutput)")
    posisi_katex = render.index("katex.renderToString")
    assert posisi_saring < posisi_katex


def test_sanitizer_membuang_skema_berbahaya():
    """Tautan `javascript:` dan atribut penangan event harus jatuh."""
    script = _script()

    assert "SAFE_HREF" in script
    assert "noopener noreferrer" in script
    # Atribut di luar daftar dibuang, bukan diperiksa satu per satu.
    assert "child.removeAttribute(attr.name)" in script


def test_fallback_markdown_meng_escape_masukan():
    """Jalur cadangan (tanpa `marked`) tidak boleh meloloskan tag mentah."""
    script = _script()
    fallback = script[script.index("function fallbackRegexMarkdown(") :]
    fallback = fallback[: fallback.index("function renderMarkdownAndMath(") if "function renderMarkdownAndMath(" in fallback else 800]

    assert "escapeHtml(txt)" in fallback
    # Escape harus jadi langkah pertama, bukan setelah tag buatan sendiri lahir.
    assert fallback.index("escapeHtml(txt)") < fallback.index("<h3>")


def test_judul_sesi_tidak_masuk_innerhtml():
    """Judul sesi berasal dari pesan pengguna: harus simpul teks."""
    script = _script()

    assert "titleEl.textContent = s.title" in script
    assert not re.search(r"innerHTML\s*=\s*`[^`]*\$\{\s*s\.title", script)
