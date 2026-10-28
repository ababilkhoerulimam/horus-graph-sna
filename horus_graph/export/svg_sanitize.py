"""
Penyaring SVG untuk laporan HTML.

Laporan dibagikan, dan SVG-nya datang dari klien, jadi ia diperlakukan sebagai
masukan tidak tepercaya. Yang dipakai bukan daftar larangan melainkan daftar
izin: elemen dan atribut yang tidak disebut di sini tidak pernah ditulis, dan
keluarannya dibangun ulang dari nol, bukan disaring dari teks masukan.

Tokenizer yang dipakai adalah html.parser -- sama dengan yang dipakai browser
saat laporan dibuka. Itu bukan detail: penyaring berbasis regex mencocokkan
teks, sedangkan browser mencocokkan token. Entitas numerik pada skema URL dan
atribut yang dipisah garis miring lolos dari regex karena perbedaan itu, bukan
karena polanya kurang panjang.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

MAX_BYTES = 2_000_000
MAX_ELEMENTS = 20_000
MAX_DEPTH = 32
MAX_ATTRS = 24

SVG_NS = "http://www.w3.org/2000/svg"

# Elemen yang isinya dibuang seluruhnya: bisa menjalankan kode, memuat aset
# eksternal, atau menjadi titik integrasi HTML (foreignObject, desc, title)
# tempat markup di dalam SVG ditafsirkan dengan aturan yang berbeda.
DROP = frozenset(
    {
        "script",
        "style",
        "foreignobject",
        "desc",
        "title",
        "image",
        "use",
        "iframe",
        "object",
        "embed",
        "animate",
        "set",
        "animatetransform",
        "animatemotion",
        "handler",
        "switch",
        "symbol",
        "filter",
        "mask",
        "pattern",
    }
)

_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_NUM = re.compile(rf"^{_NUMBER}$")
_NUMS = re.compile(rf"^{_NUMBER}(?:\s*[, ]\s*{_NUMBER})*$")
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_RGB = re.compile(
    rf"^rgba?\(\s*{_NUMBER}\s*,\s*{_NUMBER}\s*,\s*{_NUMBER}\s*(?:,\s*{_NUMBER}\s*)?\)$"
)
_NAMED = re.compile(r"^[a-zA-Z]{3,20}$")
_LOCAL_URL = re.compile(r"^url\(\s*#[A-Za-z_][\w:.-]*\s*\)$")
_IDENT = re.compile(r"^[A-Za-z_][\w:.-]*$")
_CLASS = re.compile(r"^[A-Za-z_][\w\- ]*$")
_FONT = re.compile(r"^[A-Za-z0-9 _,'\"-]{1,120}$")
_PATH = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9.,\-+eE\s]*$")
_TRANSFORM = re.compile(
    r"^(?:(?:translate|scale|rotate|skewX|skewY|matrix)\s*\([^()]*\)\s*,?\s*)+$"
)
_TRANSFORM_ARGS = re.compile(rf"^[\s,]*(?:{_NUMBER}[\s,]*)*$")

# Nama kanonik: html.parser menurunkan semua huruf, sedangkan SVG membedakan
# besar-kecil. Tanpa pemulihan ini viewBox menjadi viewbox dan berkasnya rusak
# bila dibuka sebagai SVG mandiri.
CANONICAL = {
    "viewbox": "viewBox",
    "preserveaspectratio": "preserveAspectRatio",
    "refx": "refX",
    "refy": "refY",
    "markerwidth": "markerWidth",
    "markerheight": "markerHeight",
    "markerunits": "markerUnits",
    "gradientunits": "gradientUnits",
    "gradienttransform": "gradientTransform",
    "clippathunits": "clipPathUnits",
    "spreadmethod": "spreadMethod",
    "startoffset": "startOffset",
    "textlength": "textLength",
    "lengthadjust": "lengthAdjust",
    "pathlength": "pathLength",
}

PAINT = {"fill", "stroke", "stop-color", "flood-color", "color"}
NUMBER = {
    "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "width", "height", "dx", "dy", "font-size", "font-weight", "stroke-width",
    "stroke-opacity", "fill-opacity", "opacity", "stop-opacity",
    "letter-spacing", "offset", "pathlength",
}
NUMBER_LIST = {"viewbox", "points", "stroke-dasharray"}
LOCAL_ONLY = {"marker-start", "marker-mid", "marker-end"}

ELEMENTS: Dict[str, frozenset] = {
    "svg": frozenset(
        {"viewbox", "preserveaspectratio", "width", "height", "id", "class", "version"}
    ),
    "g": frozenset({"transform", "id", "class"}),
    "defs": frozenset({"id"}),
    "marker": frozenset(
        {"id", "viewbox", "refx", "refy", "markerwidth", "markerheight", "markerunits", "orient"}
    ),
    "clippath": frozenset({"id", "clippathunits"}),
    "lineargradient": frozenset(
        {"id", "gradientunits", "gradienttransform", "x1", "y1", "x2", "y2"}
    ),
    "radialgradient": frozenset({"id", "gradientunits", "gradienttransform", "cx", "cy", "r"}),
    "stop": frozenset({"offset", "stop-color", "stop-opacity"}),
    "path": frozenset({"d", "pathlength"}),
    "circle": frozenset({"cx", "cy", "r"}),
    "rect": frozenset({"x", "y", "width", "height", "rx", "ry"}),
    "line": frozenset({"x1", "y1", "x2", "y2"}),
    "polyline": frozenset({"points"}),
    "polygon": frozenset({"points"}),
    "ellipse": frozenset({"cx", "cy", "rx", "ry"}),
    "text": frozenset(
        {
            "x", "y", "dx", "dy", "font-size", "font-weight", "font-family",
            "text-anchor", "dominant-baseline", "letter-spacing", "textlength",
            "lengthadjust",
        }
    ),
    "tspan": frozenset({"x", "y", "dx", "dy"}),
}

COMMON = frozenset(
    {
        "id", "class", "transform", "fill", "fill-opacity", "stroke",
        "stroke-width", "stroke-opacity", "stroke-dasharray", "stroke-linecap",
        "stroke-linejoin", "opacity", "paint-order", "vector-effect", "display",
        "marker-start", "marker-mid", "marker-end",
    }
)

ALIGN = {"text-anchor": {"start", "middle", "end"},
         "dominant-baseline": {"auto", "middle", "central", "hanging", "text-bottom", "text-top"}}


def _paint(value: str) -> bool:
    return bool(
        value in {"none", "currentColor", "transparent", "inherit"}
        or _HEX_COLOR.match(value)
        or _RGB.match(value)
        or _NAMED.match(value)
        or _LOCAL_URL.match(value)
    )


def _transform(value: str) -> bool:
    if not _TRANSFORM.match(value):
        return False
    for body in re.findall(r"\(([^()]*)\)", value):
        if not _TRANSFORM_ARGS.match(body):
            return False
    return True


def _valid(name: str, value: str) -> bool:
    """Nilai atribut lolos bentuk yang diharapkan untuk namanya."""
    if name in PAINT:
        return _paint(value)
    if name in LOCAL_ONLY:
        return bool(_LOCAL_URL.match(value))
    if name in NUMBER:
        return bool(_NUM.match(value))
    if name in NUMBER_LIST:
        return bool(_NUMS.match(value))
    if name == "d":
        return bool(_PATH.match(value))
    if name in {"transform", "gradienttransform"}:
        return _transform(value)
    if name == "id":
        return bool(_IDENT.match(value))
    if name == "class":
        return bool(_CLASS.match(value))
    if name in ALIGN:
        return value in ALIGN[name]
    if name in {"stroke-linecap", "stroke-linejoin"}:
        return value in {"butt", "round", "square", "miter", "bevel", "arcs"}
    if name == "vector-effect":
        return value in {"none", "non-scaling-stroke"}
    if name == "orient":
        return value == "auto" or bool(_NUM.match(value))
    if name == "spreadmethod":
        return value in {"pad", "reflect", "repeat"}
    if name == "markerunits":
        return value in {"strokeWidth", "userSpaceOnUse"}
    if name == "preserveaspectratio":
        return bool(
            re.match(
                r"^(?:none|x(?:Min|Mid|Max)Y(?:Min|Mid|Max))(?:\s+(?:meet|slice))?$", value
            )
        )
    if name == "lengthadjust":
        return value in {"spacing", "spacingAndGlyphs"}
    if name == "version":
        return bool(re.match(r"^[0-9.]+$", value))
    return bool(_FONT.match(value))


def _style_to_attributes(value: str) -> List[Tuple[str, str]]:
    """
    Atribut style tidak pernah diteruskan apa adanya.

    Dua properti yang benar-benar dipakai kanvas dipetakan ke atribut
    presentasi; sisanya dibuang. Dengan begitu tidak ada CSS yang perlu
    diurai, termasuk url() dan @import.
    """
    out: List[Tuple[str, str]] = []
    for chunk in value.split(";"):
        if ":" not in chunk:
            continue
        key, _, raw = chunk.partition(":")
        key = key.strip().lower()
        raw = raw.strip()
        if key == "display" and raw == "none":
            out.append(("display", "none"))
        elif key == "opacity" and _NUM.match(raw):
            out.append(("opacity", raw))
    return out


class _Rebuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.stack: List[Tuple[str, bool]] = []
        self.root_seen = False
        self.closed = False
        self.failed = False
        self.elements = 0
        self.dropping = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self._open(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self._open(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.failed or self.closed:
            return
        if self.dropping:
            self.dropping -= 1
            return
        if tag not in [name for name, _ in self.stack]:
            return
        while self.stack:
            name, emitted = self.stack.pop()
            if emitted:
                self.out.append(f"</{name}>")
            if name == tag:
                break
        if not self.stack and self.root_seen:
            self.closed = True

    def handle_data(self, data: str) -> None:
        if self.failed or self.closed or self.dropping or not self.stack:
            return
        self.out.append(html.escape(data, quote=False))

    def handle_comment(self, data: str) -> None:
        return

    def handle_decl(self, decl: str) -> None:
        return

    def handle_pi(self, data: str) -> None:
        return

    def unknown_decl(self, data: str) -> None:
        return

    def _open(
        self, tag: str, attrs: List[Tuple[str, Optional[str]]], *, self_closing: bool
    ) -> None:
        tag = tag.lower()
        if self.failed or self.closed:
            return
        if self.dropping:
            if not self_closing:
                self.dropping += 1
            return
        if tag in DROP:
            if not self_closing:
                self.dropping = 1
            return
        if not self.root_seen:
            if tag != "svg":
                self.failed = True
                return
            self.root_seen = True
        self.elements += 1
        if self.elements > MAX_ELEMENTS or len(self.stack) >= MAX_DEPTH:
            self.failed = True
            return
        if tag not in ELEMENTS:
            # Elemen tak dikenal tidak dibuang isinya, hanya dibuka: anak-anaknya
            # tetap diperiksa dengan aturan yang sama.
            if not self_closing:
                self.stack.append((tag, False))
            return
        if len(attrs) > MAX_ATTRS:
            self.failed = True
            return
        self.out.append(self._render(tag, attrs, self_closing))
        if not self_closing:
            self.stack.append((tag, True))
        elif tag == "svg" and not self.stack:
            self.closed = True

    def _render(
        self, tag: str, attrs: List[Tuple[str, Optional[str]]], self_closing: bool
    ) -> str:
        allowed = ELEMENTS[tag] | COMMON
        pieces: List[str] = []
        if tag == "svg":
            pieces.append(f'xmlns="{SVG_NS}"')
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = raw_value or ""
            if name == "style":
                for key, mapped in _style_to_attributes(value):
                    if key in allowed or key in COMMON:
                        pieces.append(
                            f'{CANONICAL.get(key, key)}="{html.escape(mapped, quote=True)}"'
                        )
                continue
            if name not in allowed:
                continue
            canonical = CANONICAL.get(name, name)
            if not _valid(name, value):
                continue
            pieces.append(f'{canonical}="{html.escape(value, quote=True)}"')
        body = " ".join(pieces)
        closing = "/>" if self_closing else ">"
        return f"<{tag} {body}{closing}" if body else f"<{tag}{closing}"


def sanitize_svg(svg: str) -> str:
    """
    Kembalikan SVG yang hanya memuat elemen dan atribut yang diizinkan.

    String kosong berarti masukan ditolak: bukan SVG, melewati batas, atau
    tokenizer gagal. Pemanggil menuliskannya sebagai keterangan, bukan sebagai
    gambar separuh.
    """
    if not svg:
        return ""
    if len(svg.encode("utf-8", "ignore")) > MAX_BYTES:
        return ""
    parser = _Rebuilder()
    try:
        parser.feed(svg)
        parser.close()
    except Exception:
        return ""
    if parser.failed or not parser.root_seen:
        return ""
    # Tutup elemen yang tidak ditutup masukan, supaya keluarannya well-formed.
    while parser.stack:
        name, emitted = parser.stack.pop()
        if emitted:
            parser.out.append(f"</{name}>")
    return "".join(parser.out)
