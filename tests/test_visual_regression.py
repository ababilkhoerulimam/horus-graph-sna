"""
Pembanding piksel dan gerbang di `tools/visual_regression.py`, diuji tanpa peramban.

Tangkapan layar tidak bisa dijalankan di suite biasa (butuh Chromium dan server
hidup), tetapi dua bagian paling mudah salah diam-diam ada di sini: dekodernya
(salah menerapkan filter membuat setiap perbandingan mengembalikan "sama") dan
kode keluarnya (gerbang yang selalu hijau sama saja tidak ada). Keduanya diuji
tanpa jaringan.

PNG uji dirakit sendiri dengan `zlib` + `struct` untuk menutup kelima tipe
filter. Satu bidikan kecil diambil dari encoder lain — kanvas Chromium — karena
perakit dan dekoder yang berbagi kesalahpahaman akan saling membenarkan.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import struct
import zlib
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "tools" / "visual_regression.py"

CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}

# 3x2 RGBA, dibuat oleh canvas Chromium (Skia), bukan oleh dekoder di repo ini.
# Isinya sengaja warna pekat supaya harapan pikselnya bisa ditulis dari kode
# penggambar, bukan dari hasil dekode.
CHROMIUM_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAYAAACddGYaAAAAG0lEQVR4AWL6z8DwHwwZ/v9nYmSA8ASV"
    "TBgAAAAA///dMFnPAAAABklEQVQDAIEGCGUSC9ldAAAAAElFTkSuQmCC"
)
CHROMIUM_PIXELS = bytes(
    (255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 0, 0, 0, 255, 255, 255, 255, 255, 17, 34, 51, 255)
)


def _load():
    spec = importlib.util.spec_from_file_location("visual_regression", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


visual_regression = _load()


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    distance_left = abs(estimate - left)
    distance_up = abs(estimate - up)
    distance_up_left = abs(estimate - up_left)
    if distance_left <= distance_up and distance_left <= distance_up_left:
        return left
    if distance_up <= distance_up_left:
        return up
    return up_left


def _filter_row(row: bytes, previous: bytes, channels: int, kind: int) -> bytes:
    out = bytearray()
    for index, value in enumerate(row):
        left = row[index - channels] if index >= channels else 0
        up = previous[index] if previous else 0
        up_left = previous[index - channels] if previous and index >= channels else 0
        if kind == 0:
            predictor = 0
        elif kind == 1:
            predictor = left
        elif kind == 2:
            predictor = up
        elif kind == 3:
            predictor = (left + up) >> 1
        elif kind == 4:
            predictor = _paeth(left, up, up_left)
        else:
            raise AssertionError(f"filter {kind} tidak dikenal di perakit uji")
        out.append((value - predictor) & 0xFF)
    return bytes(out)


def _chunk(kind: bytes, body: bytes, crc: Optional[int] = None) -> bytes:
    checksum = zlib.crc32(kind + body) & 0xFFFFFFFF if crc is None else crc
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", checksum)


def _png(
    width: int,
    height: int,
    rows: Sequence[bytes],
    *,
    color_type: int = 2,
    filters: Optional[Sequence[int]] = None,
    depth: int = 8,
    interlace: int = 0,
    end: bool = True,
) -> bytes:
    channels = CHANNELS[color_type]
    raw = bytearray()
    previous = b""
    for y, row in enumerate(rows):
        assert len(row) == width * channels
        kind = filters[y] if filters else 0
        raw.append(kind)
        raw += _filter_row(row, previous, channels, kind)
        previous = row
    header = struct.pack(">IIBBBBB", width, height, depth, color_type, 0, 0, interlace)
    body = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    )
    return body + (_chunk(b"IEND", b"") if end else b"")


def _solid(width: int, height: int, pixel: Tuple[int, ...]) -> List[bytes]:
    return [bytes(pixel) * width for _ in range(height)]


def _image(width: int, height: int, pixel: Tuple[int, ...] = (10, 20, 30)):
    return visual_regression.decode_png(_png(width, height, _solid(width, height, pixel)))


# ------------------------------------------------------------------ dekoder


def test_png_dari_encoder_lain_terdekode_persis() -> None:
    """Oracle luar: perakit uji dan dekoder bisa salah bersama-sama."""
    image = visual_regression.decode_png(base64.b64decode(CHROMIUM_PNG))

    assert (image.width, image.height, image.channels) == (3, 2, 4)
    assert image.pixels == CHROMIUM_PIXELS


@pytest.mark.parametrize("kind", [0, 1, 2, 3, 4])
def test_kelima_filter_png_terdekode(kind: int) -> None:
    rows = [bytes((y * 7 + x * 3 + c) & 0xFF for x in range(4) for c in range(3)) for y in range(4)]
    image = visual_regression.decode_png(_png(4, 4, rows, filters=[kind] * 4))

    assert (image.width, image.height, image.channels) == (4, 4, 3)
    assert image.pixels == b"".join(rows)


def test_rgba_dan_grayscale_terdekode() -> None:
    rgba = visual_regression.decode_png(_png(2, 2, _solid(2, 2, (1, 2, 3, 4)), color_type=6))
    gray = visual_regression.decode_png(_png(2, 2, _solid(2, 2, (9,)), color_type=0))

    assert rgba.channels == 4
    assert rgba.pixels == bytes((1, 2, 3, 4)) * 4
    assert gray.channels == 1
    assert gray.pixels == bytes((9,)) * 4


def test_png_ter_interlace_ditolak() -> None:
    with pytest.raises(ValueError, match="interlace"):
        visual_regression.decode_png(_png(1, 1, _solid(1, 1, (0, 0, 0)), interlace=1))


def test_kedalaman_selain_delapan_ditolak() -> None:
    with pytest.raises(ValueError, match="kedalaman"):
        visual_regression.decode_png(_png(1, 1, _solid(1, 1, (0, 0, 0)), depth=16))


def test_bukan_png_ditolak() -> None:
    with pytest.raises(ValueError, match="bukan PNG"):
        visual_regression.decode_png(b"GIF89a")


def test_png_terpotong_ditolak() -> None:
    """Berkas yang terpotong di tengah potongan tidak boleh dipotong diam-diam."""
    data = _png(4, 4, _solid(4, 4, (1, 2, 3)))

    with pytest.raises(ValueError, match="terpotong"):
        visual_regression.decode_png(data[: data.find(b"IDAT") + 12])


def test_png_tanpa_iend_ditolak() -> None:
    with pytest.raises(ValueError, match="IEND"):
        visual_regression.decode_png(_png(2, 2, _solid(2, 2, (1, 2, 3)), end=False))


def test_crc_salah_ditolak() -> None:
    """CRC nol adalah bentuk kerusakan paling umum; menerimanya berarti diam."""
    data = _png(2, 2, _solid(2, 2, (1, 2, 3)))
    start = data.find(b"IDAT")
    (length,) = struct.unpack(">I", data[start - 4 : start])
    checksum = start + 4 + length
    broken = data[:checksum] + b"\x00\x00\x00\x00" + data[checksum + 4 :]
    assert broken != data

    with pytest.raises(ValueError, match="CRC"):
        visual_regression.decode_png(broken)


def test_png_berukuran_nol_ditolak() -> None:
    with pytest.raises(ValueError, match="nol"):
        visual_regression.decode_png(_png(0, 1, [], color_type=2))


# ---------------------------------------------------------------- pembanding


def test_gambar_identik_tidak_berbeda() -> None:
    diff = visual_regression.compare(_image(8, 8), _image(8, 8))

    assert diff.differing == 0
    assert diff.share == 0.0
    assert diff.passed


def test_selisih_di_bawah_ambang_kanal_diabaikan() -> None:
    """Delta 2 masih dianggap sama; ambangnya inklusif, bukan eksklusif."""
    diff = visual_regression.compare(_image(8, 8), _image(8, 8, (12, 22, 32)))

    assert diff.max_delta == 2
    assert diff.differing == 0
    assert diff.passed


def test_anggaran_dihitung_dalam_piksel_bukan_porsi() -> None:
    """Anggaran yang sama harus berlaku sama di lebar mana pun."""
    width = 400
    left = _image(width, 20)
    rows = [bytearray(row) for row in _solid(width, 20, (10, 20, 30))]
    for y in range(20):
        for x in range(12):
            rows[y][x * 3 : x * 3 + 3] = bytes((200, 20, 30))
    right = visual_regression.decode_png(_png(width, 20, [bytes(row) for row in rows]))

    diff = visual_regression.compare(left, right)

    assert diff.differing == 240
    assert diff.differing > visual_regression.BUDGET_PX
    assert not diff.passed
    assert diff.box == (0, 0, 11, 19)


def test_satu_piksel_tetap_lolos() -> None:
    left = _image(40, 40)
    pixels = bytearray(left.pixels)
    pixels[0:3] = bytes((13, 20, 30))
    right = left._replace(pixels=bytes(pixels))

    diff = visual_regression.compare(left, right)

    assert diff.differing == 1
    assert diff.passed
    assert diff.box == (0, 0, 0, 0)


def test_blok_besar_gagal_dan_kotaknya_dilaporkan() -> None:
    left = _image(100, 100)
    rows = [bytearray(row) for row in _solid(100, 100, (10, 20, 30))]
    for y in range(10, 30):
        for x in range(5, 25):
            rows[y][x * 3 : x * 3 + 3] = bytes((60, 20, 30))
    right = visual_regression.decode_png(_png(100, 100, [bytes(row) for row in rows]))

    diff = visual_regression.compare(left, right)

    assert diff.differing == 400
    assert not diff.passed
    assert diff.box == (5, 10, 24, 29)


def test_ukuran_berbeda_ditolak() -> None:
    with pytest.raises(ValueError, match="ukuran"):
        visual_regression.compare(_image(4, 4), _image(5, 4))


# ------------------------------------------------------------------ konfigurasi


def test_sembilan_bidikan_tiga_mode_kali_tiga_lebar() -> None:
    daftar = visual_regression.shots()

    assert len(daftar) == 9
    assert {mode for _, mode, _ in daftar} == {"actor_network", "topic_actor", "narrative_temporal"}
    assert {width for _, _, width in daftar} == {1024, 1280, 1600}


def test_penyaring_bidikan_cocok_persis() -> None:
    assert [name for name, _, _ in visual_regression.shots("topic_actor")] == [
        "topic_actor_1024",
        "topic_actor_1280",
        "topic_actor_1600",
    ]
    assert [name for name, _, _ in visual_regression.shots("1600")] == [
        "actor_network_1600",
        "topic_actor_1600",
        "narrative_temporal_1600",
    ]
    with pytest.raises(SystemExit):
        visual_regression.shots("tidak-ada")


def test_ambang_yang_dinyatakan_sama_dengan_yang_dipakai() -> None:
    """Angka di docstring adalah janji ke pembaca; tes ini menjaga keduanya sama."""
    doc = visual_regression.__doc__ or ""

    assert visual_regression.CHANNEL_TOLERANCE == 2
    assert visual_regression.BUDGET_PX == 120
    assert "CHANNEL_TOLERANCE = 2" in doc
    assert "BUDGET_PX = 120" in doc


# ------------------------------------------------------------------ gerbang


def _prepare(monkeypatch, tmp_path, *, manifest: bool = True) -> None:
    baseline = tmp_path / "baseline"
    current = tmp_path / "current"
    baseline.mkdir()
    current.mkdir()
    for name, _, _ in visual_regression.shots():
        (baseline / f"{name}.png").write_bytes(b"baseline")
        (current / f"{name}.png").write_bytes(b"current")
    marker = baseline / "manifest.json"
    if manifest:
        marker.write_text(
            json.dumps(
                {"widths": list(visual_regression.WIDTHS), "height": visual_regression.HEIGHT}
            ),
            encoding="utf-8",
        )
    monkeypatch.setattr(visual_regression, "BASELINE", baseline)
    monkeypatch.setattr(visual_regression, "CURRENT", current)
    monkeypatch.setattr(visual_regression, "MANIFEST", marker)
    monkeypatch.setattr(visual_regression, "_capture_all_sync", lambda url, chosen: [])
    monkeypatch.setattr(visual_regression, "_chrome_version", lambda: "stub")
    monkeypatch.setattr(
        visual_regression, "decode_png", lambda data: visual_regression.PngImage(1, 1, 3, b"")
    )


def _diff(differing: int) -> "visual_regression.Diff":
    return visual_regression.Diff(differing, 1_520_000, differing / 1_520_000, 9, None)


def test_gerbang_lulus_mengembalikan_nol(monkeypatch, tmp_path) -> None:
    _prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(visual_regression, "compare", lambda a, b: _diff(3))

    assert visual_regression.main(["--check"]) == 0


def test_gerbang_gagal_mengembalikan_satu(monkeypatch, tmp_path) -> None:
    """Angka 1 khusus regresi; tanpa tes ini, gerbang yang selalu hijau lolos."""
    _prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(visual_regression, "compare", lambda a, b: _diff(5000))

    assert visual_regression.main(["--check"]) == 1


def test_baseline_tanpa_manifest_mengembalikan_empat(monkeypatch, tmp_path) -> None:
    _prepare(monkeypatch, tmp_path, manifest=False)

    assert visual_regression.main(["--check"]) == 4


def test_baseline_hilang_mengembalikan_empat(monkeypatch, tmp_path) -> None:
    _prepare(monkeypatch, tmp_path)
    for name, _, _ in visual_regression.shots():
        (tmp_path / "baseline" / f"{name}.png").unlink()
    monkeypatch.setattr(visual_regression, "compare", lambda a, b: _diff(0))

    assert visual_regression.main(["--check"]) == 4


def test_kalibrasi_tidak_stabil_mengembalikan_tiga(monkeypatch, tmp_path) -> None:
    _prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(visual_regression, "compare", lambda a, b: _diff(5000))

    assert visual_regression.main(["--calibrate", "--only", "actor_network_1600"]) == 3


def test_kalibrasi_stabil_mengembalikan_nol(monkeypatch, tmp_path) -> None:
    _prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(visual_regression, "compare", lambda a, b: _diff(4))

    assert visual_regression.main(["--calibrate", "--only", "actor_network_1600"]) == 0


def test_tangkapan_gagal_mengembalikan_lima(monkeypatch, tmp_path) -> None:
    """Chromium yang tidak mau start bukan regresi tampilan."""

    def explode(url, chosen):
        raise RuntimeError("Chromium tidak menulis DevToolsActivePort")

    _prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(visual_regression, "_capture_all_sync", explode)

    assert visual_regression.main(["--update"]) == 5
