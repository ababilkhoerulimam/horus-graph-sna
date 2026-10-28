"""
Penyaring SVG laporan.

Berkas ini menjaga satu hal: laporan yang dibagikan tidak menjalankan kode saat
dibuka. Setiap kasus di bawah pernah lolos dari penyaring berbasis regex, atau
merupakan bentuk yang paling sering dipakai untuk melewatinya. Yang diuji bukan
"polanya ada", melainkan "keluarannya bersih".
"""

from __future__ import annotations

import re

import pytest

from horus_graph.export.svg_sanitize import MAX_BYTES, MAX_ELEMENTS, sanitize_svg

# Sesudah xmlns dibuang, tidak satu pun pola ini boleh muncul di keluaran.
FORBIDDEN = re.compile(
    r"(?i)<\s*script|\son[a-z]+\s*=|javascript:|\sdata:|https?://|@import"
    r"|<image|<foreignobject|<iframe|<use\b|<object|<embed|<style|\bhref\s*=|\bsrc\s*="
)

ATTACKS = [
    ("script_berpasangan", '<svg><script>alert(1)</script></svg>'),
    ("script_tanpa_penutup", '<svg><script>alert(1)'),
    ("atribut_event_spasi", '<svg onload="alert(1)"></svg>'),
    ("atribut_event_tanpa_spasi", "<svg/onload=alert(1)>"),
    ("atribut_event_pada_rect", "<svg><rect/onclick=alert(1)></svg>"),
    ("gambar_eksternal", '<svg><image href="https://evil.example/x.png"/></svg>'),
    ("gambar_data_uri", '<svg><image href="data:image/svg+xml,<svg/>"/></svg>'),
    ("tautan_javascript", '<svg><a href="javascript:alert(1)"><text>ok</text></a></svg>'),
    ("tautan_entity_desimal", '<svg><a href="&#106;avascript:alert(1)"><text>ok</text></a></svg>'),
    ("tautan_entity_newline", '<svg><a href="java&#x0A;script:alert(1)"><text>ok</text></a></svg>'),
    ("tautan_entity_tab", '<svg><a href="java&Tab;script:alert(1)"><text>ok</text></a></svg>'),
    ("gaya_import", "<svg><style>@import url(https://evil.example/x.css);</style></svg>"),
    ("gaya_url_pada_rect", '<svg><rect style="fill:url(https://evil.example/x)"/></svg>'),
    ("cat_eksternal", '<svg><rect fill="url(https://evil.example/x#p)"/></svg>'),
    ("foreign_object", '<svg><foreignObject><body><img src="x" onerror="alert(1)"/></body></foreignObject></svg>'),
    ("desc_integrasi", '<svg><desc><img src="x" onerror="alert(1)"/></desc></svg>'),
    ("title_dengan_script", '<svg><title><script>alert(1)</script></title></svg>'),
    ("use_eksternal", '<svg><use href="https://evil.example/s.svg#a"/></svg>'),
    ("animate_href", '<svg><animate attributeName="href" values="javascript:alert(1)"/></svg>'),
    ("set_onload", '<svg><set attributeName="onload" to="alert(1)"/></svg>'),
    ("cdata", "<svg><![CDATA[<script>alert(1)</script>]]></svg>"),
    ("komentar_bersyarat", "<!--[if IE]><script>alert(1)</script><![endif]--><svg></svg>"),
    ("root_ganda", '</svg><script>alert(1)</script><svg></svg>'),
    ("marker_di_suntik", '<svg><path marker-end="url(https://evil.example/x#a)" d="M0,0L1,1"/></svg>'),
]


@pytest.mark.parametrize("name,payload", ATTACKS, ids=[a[0] for a in ATTACKS])
def test_korpus_serangan_dibersihkan(name: str, payload: str) -> None:
    cleaned = sanitize_svg(payload)

    body = cleaned.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert FORBIDDEN.search(body) is None, f"{name}: {cleaned}"
    assert cleaned.count("<svg") <= 1
    # Keluaran harus bisa diurai ulang: penyaring membangun pohon, bukan
    # memotong teks, jadi tidak boleh ada tag menggantung.
    assert cleaned == "" or cleaned.endswith(">")


def test_teks_yang_di_escape_tidak_berubah_menjadi_tag() -> None:
    cleaned = sanitize_svg("<svg><text>&lt;script&gt;alert(1)&lt;/script&gt;</text></svg>")

    assert "&lt;script&gt;" in cleaned
    assert "<script" not in cleaned


def test_ampersand_tidak_double_escape() -> None:
    cleaned = sanitize_svg("<svg><text>a &amp; b</text></svg>")

    assert "a &amp; b" in cleaned
    assert "&amp;amp;" not in cleaned


def test_svg_sah_dipertahankan_utuh() -> None:
    svg = (
        '<svg viewBox="0 0 100 100"><defs>'
        '<marker id="panah" markerWidth="2" refX="1"><path d="M0,0L1,1"/></marker>'
        "</defs><g transform=\"translate(1,2)\">"
        '<circle cx="10" cy="10" r="4" fill="#38BDF8" stroke="rgba(1,2,3,0.5)"/>'
        '<text x="4" y="8" font-size="11">Dewa United</text>'
        '<path d="M0,0L5,5" marker-end="url(#panah)"/>'
        "</g></svg>"
    )

    cleaned = sanitize_svg(svg)

    assert cleaned.count("<circle") == 1
    assert "<text x=\"4\" y=\"8\" font-size=\"11\">Dewa United</text>" in cleaned
    assert 'marker-end="url(#panah)"' in cleaned
    assert 'markerWidth="2"' in cleaned and 'refX="1"' in cleaned
    assert 'viewBox="0 0 100 100"' in cleaned


def test_display_none_dipetakan_ke_atribut() -> None:
    cleaned = sanitize_svg('<svg><g style="display:none;fill:url(https://x)"></g></svg>')

    assert 'display="none"' in cleaned
    assert "url(https" not in cleaned


def test_bukan_svg_ditolak() -> None:
    assert sanitize_svg("<div><script>alert(1)</script></div>") == ""
    assert sanitize_svg("teks biasa") == ""
    assert sanitize_svg("") == ""


def test_masukan_terlalu_besar_ditolak() -> None:
    assert sanitize_svg("<svg>" + "a" * (MAX_BYTES + 1) + "</svg>") == ""


def test_terlalu_banyak_elemen_ditolak() -> None:
    svg = "<svg>" + "<g></g>" * (MAX_ELEMENTS + 5) + "</svg>"

    assert sanitize_svg(svg) == ""


def test_nested_terlalu_dalam_ditolak() -> None:
    svg = "<svg>" + "<g>" * 40 + "</g>" * 40 + "</svg>"

    assert sanitize_svg(svg) == ""
