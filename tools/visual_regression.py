"""Regresi visual frontend: 3 mode x 3 lebar, dibandingkan tanpa Pillow.

Kriteria terima V2.2 meminta "tangkapan layar identik dengan toleransi piksel
yang dinyatakan". `Pillow` tidak terpasang, dan menambahkannya berarti
menambah dependensi untuk satu skrip; jadi dekoder PNG-nya ditulis di sini
dengan `zlib` + `struct` saja. Yang didukung: PNG 8-bit non-interlaced
(grayscale, RGB, RGBA) — bentuk yang dikeluarkan `Page.captureScreenshot`.

Dua angka toleransi, keduanya diukur:

- `CHANNEL_TOLERANCE = 2` — selisih kanal maksimum yang masih dianggap sama.
  Nilai 1-2 muncul dari pembulatan subpiksel pada tepi teks.
- `BUDGET_PX = 120` — jumlah piksel berbeda yang masih dimaafkan per bidikan.
  Angkanya absolut, bukan porsi: anggaran berbasis porsi membuat cacat yang
  sama lolos di 1600 dan gagal di 1024, karena penyebutnya ikut mengecil.
  `--calibrate` mengukur selisih-diri 18 piksel pada kode yang tidak berubah,
  jadi 120 memberi margin 6,6 kali — dan tetap menangkap kotak 11x11.

Bila selisih-diri melewati anggaran, bidikan itu dilaporkan `unstable` (kode
keluar 3), bukan `regressed` (kode keluar 1): dua kegagalan yang berbeda
penyebabnya. Kegagalan infrastruktur (Chromium tidak mau start, halaman tidak
siap, ukuran bidikan berubah) memakai kode 5, supaya pemanggil tidak mengira
lingkungan rusak sebagai tampilan yang berubah.

Baseline tinggal di `.shots/baseline/` dan tidak masuk git: tangkapan layar
bergantung pada font dan versi Chromium mesin ini, jadi PNG yang di-commit
tidak akan pernah lolos di mesin lain. Gerbang ini membandingkan "mesin ini,
sebelum vs sesudah perubahan", bukan antar mesin. Karena itu gerbangnya manual:
jalankan `make visual` sebelum menggabungkan perubahan yang menyentuh
`web/static`.

Pemakaian:
    horus-graph serve --bundle data/bundles/horus-agent-2026-10-27 --port 8021 &
    python tools/visual_regression.py --url http://127.0.0.1:8021/ --update
    python tools/visual_regression.py --url http://127.0.0.1:8021/ --check
    python tools/visual_regression.py --url http://127.0.0.1:8021/ --calibrate
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

# Peramban dicari saat dijalankan, bukan dipatok: path milik satu mesin membuat
# alat bukti ini tidak bisa dipakai di mesin lain atau di CI.
_CHROME: Optional[Path] = None
CHROME_NAMES = ("chrome", "chrome.exe", "chromium", "chromium-browser", "msedge", "msedge.exe")
REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / ".shots" / "baseline"
CURRENT = REPO_ROOT / ".shots" / "current"
MANIFEST = BASELINE / "manifest.json"

MODES = ("actor_network", "topic_actor", "narrative_temporal")
WIDTHS = (1024, 1280, 1600)
HEIGHT = 950

CHANNEL_TOLERANCE = 2
BUDGET_PX = 120
CALIBRATION_PAIRS = 3

# Mode dipilih lewat keadaan tampilan di URL, bukan dengan memanggil
# switchAppMode dari Runtime.evaluate: fungsi itu global hanya karena
# kebetulan skrip klasik, dan ia kembali lebih awal saat data belum siap.
# Kameranya sengaja tidak ikut di tautan: setiap mode punya skala tata letak
# sendiri, jadi kamera tetap (z=1) membuat mode 03 tampil sebesar koin.
VIEW_HASH = "v=1&m={mode}"

EXIT_OK = 0
EXIT_REGRESSED = 1
EXIT_UNSTABLE = 3
EXIT_NO_BASELINE = 4
EXIT_INFRA = 5

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS_BY_COLOR_TYPE = {0: 1, 2: 3, 4: 2, 6: 4}


class PngImage(NamedTuple):
    width: int
    height: int
    channels: int
    pixels: bytes


class Diff(NamedTuple):
    differing: int
    total: int
    share: float
    max_delta: int
    box: Optional[Tuple[int, int, int, int]]

    @property
    def passed(self) -> bool:
        return self.differing <= BUDGET_PX


def decode_png(data: bytes) -> PngImage:
    """Dekode PNG 8-bit non-interlaced. Bentuk lain ditolak dengan ValueError."""
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("bukan PNG: tanda tangan tidak cocok")

    offset = len(PNG_SIGNATURE)
    header: Optional[Tuple[int, int, int, int, int, int, int]] = None
    payload = bytearray()
    saw_end = False

    while offset + 8 <= len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        kind = data[offset + 4 : offset + 8]
        end = offset + 12 + length
        # Potongan yang melewati akhir berkas harus ditolak, bukan dipotong
        # diam-diam: berkas yang rusak di batas potongan tetap terdekode.
        if end > len(data):
            raise ValueError(f"potongan {kind!r} terpotong")
        body = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : end])[0]
        if zlib.crc32(kind + body) & 0xFFFFFFFF != expected_crc:
            raise ValueError(f"CRC potongan {kind!r} tidak cocok")
        offset = end

        if kind == b"IHDR":
            if header is not None:
                raise ValueError("PNG dengan dua IHDR")
            if length != 13:
                raise ValueError("IHDR tidak berukuran 13 byte")
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            payload += body
        elif kind == b"IEND":
            saw_end = True
            break

    if not saw_end:
        raise ValueError("PNG tanpa IEND")
    if header is None:
        raise ValueError("PNG tanpa IHDR")

    width, height, depth, color_type, compression, filter_method, interlace = header
    if depth != 8:
        raise ValueError(f"kedalaman bit {depth} tidak didukung (hanya 8)")
    if compression != 0 or filter_method != 0:
        raise ValueError("metode kompresi/filter tidak didukung")
    if interlace != 0:
        raise ValueError("PNG ter-interlace tidak didukung")
    if width == 0 or height == 0:
        raise ValueError("PNG berukuran nol")
    channels = CHANNELS_BY_COLOR_TYPE.get(color_type)
    if channels is None:
        raise ValueError(f"tipe warna {color_type} tidak didukung")

    stride = width * channels
    expected = height * (stride + 1)
    # Batas atas sebelum dekompresi: IDAT kecil yang mengembang jadi ratusan
    # megabyte tidak boleh sempat mengalokasikan memorinya.
    inflater = zlib.decompressobj()
    raw = inflater.decompress(bytes(payload), expected + 1)
    if len(raw) != expected:
        raise ValueError(f"panjang data {len(raw)} tidak sama dengan {expected}")

    pixels = bytearray(height * stride)
    previous = bytearray(stride)
    for row in range(height):
        start = row * (stride + 1)
        kind_filter = raw[start]
        line = bytearray(raw[start + 1 : start + 1 + stride])
        if kind_filter == 0:
            pass
        elif kind_filter == 1:
            for index in range(channels, stride):
                line[index] = (line[index] + line[index - channels]) & 0xFF
        elif kind_filter == 2:
            for index in range(stride):
                line[index] = (line[index] + previous[index]) & 0xFF
        elif kind_filter == 3:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                line[index] = (line[index] + ((left + previous[index]) >> 1)) & 0xFF
        elif kind_filter == 4:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                up = previous[index]
                up_left = previous[index - channels] if index >= channels else 0
                line[index] = (line[index] + _paeth(left, up, up_left)) & 0xFF
        else:
            raise ValueError(f"tipe filter {kind_filter} tidak dikenal")
        pixels[row * stride : (row + 1) * stride] = line
        previous = line

    return PngImage(width, height, channels, bytes(pixels))


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


def compare(left: PngImage, right: PngImage) -> Diff:
    """Bandingkan dua gambar. Piksel berbeda bila satu kanal melewati ambang."""
    if (left.width, left.height) != (right.width, right.height):
        raise ValueError(
            f"ukuran tidak sama: {left.width}x{left.height} vs {right.width}x{right.height}"
        )
    if left.channels != right.channels:
        raise ValueError(f"jumlah kanal tidak sama: {left.channels} vs {right.channels}")

    channels = left.channels
    stride = left.width * channels
    total = left.width * left.height
    left_px = left.pixels
    right_px = right.pixels

    # Jalan pintas: perbandingan byte di C untuk seluruh gambar, lalu per baris.
    # Tanpa ini, sembilan bidikan 1,5 juta piksel menghabiskan 6-13 detik hanya
    # untuk membuktikan dua gambar yang sama itu sama.
    if left_px == right_px:
        return Diff(0, total, 0.0, 0, None)

    differing = 0
    max_delta = 0
    box: Optional[Tuple[int, int, int, int]] = None

    for row in range(left.height):
        start = row * stride
        end = start + stride
        if left_px[start:end] == right_px[start:end]:
            continue
        for offset in range(start, end, channels):
            delta = 0
            for channel in range(channels):
                step = abs(left_px[offset + channel] - right_px[offset + channel])
                if step > delta:
                    delta = step
            if delta > max_delta:
                max_delta = delta
            if delta > CHANNEL_TOLERANCE:
                differing += 1
                x = (offset - start) // channels
                if box is None:
                    box = (x, row, x, row)
                else:
                    box = (min(box[0], x), min(box[1], row), max(box[2], x), max(box[3], row))

    return Diff(differing, total, differing / total if total else 0.0, max_delta, box)


def shots(only: Optional[str] = None) -> List[Tuple[str, str, int]]:
    """(nama, mode, lebar) untuk 3 mode x 3 lebar, dengan penyaring opsional."""
    chosen = []
    for mode in MODES:
        for width in WIDTHS:
            name = f"{mode}_{width}"
            if only and only not in (name, mode, str(width)):
                continue
            chosen.append((name, mode, width))
    if not chosen:
        raise SystemExit(f"tidak ada bidikan yang cocok dengan --only {only!r}")
    return chosen


# ---------------------------------------------------------------- tangkapan

READY_JS = """
(async () => {
  if (document.readyState !== "complete") return { ready: false, why: "document" };
  if (document.fonts && document.fonts.ready) {
    try { await document.fonts.ready; } catch (err) { /* diabaikan */ }
  }
  const bootstrapped = typeof BOOTSTRAP !== "undefined" && BOOTSTRAP !== null;
  const text = document.body ? document.body.innerText : "";
  const loading = text.includes("Memuat Jaringan Bipartite") ||
                  text.includes("Memuat bukti kutipan");
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  // `viewStateFlushed` baru benar setelah tautan diterapkan, dan mode di
  // tautan baru berpindah setelah itu — bukan saat BOOTSTRAP terisi.
  const flushed = typeof viewStateFlushed !== "undefined" && viewStateFlushed === true;
  return {
    ready: bootstrapped && !loading && flushed,
    why: !bootstrapped ? "bootstrap" : (loading ? "memuat" : (flushed ? "" : "tautan")),
    mode: typeof currentMode !== "undefined" ? currentMode : null,
    nodes: document.querySelectorAll("g.node-item").length
  };
})()
"""

# Mode narasi-temporal membuka panel diff epos begitu dipilih. Panel itu
# menutupi seluruh kanvas, jadi kalau dibiarkan yang dibandingkan hanya
# modalnya dan renderer mode 03 tidak pernah ikut diuji. Ditutup lewat tombol
# tutup milik aplikasi sendiri, bukan dengan menyembunyikan elemen dari luar.
DISMISS_JS = """
(() => {
  const open = document.querySelectorAll(".analytics-modal.open .modal-close-btn");
  open.forEach(button => button.click());
  return open.length;
})()
"""

FREEZE_JS = """
(() => {
  const style = document.createElement("style");
  style.textContent = "*,*::before,*::after{transition:none!important;" +
                      "animation:none!important;caret-color:transparent!important}";
  document.head.appendChild(style);
  // Bingkai dihitung sendiri, bukan lewat resetGraphView: fungsi itu memakai
  // viewBox sebagai skala, dan halaman ini mengisi viewBox 4600x3800 sehingga
  // hasilnya selalu identitas. Mode 02 juga menggambar di lapisan bipartit yang
  // tidak ikut dibingkai ulang saat mode berganti.
  //
  // Semua dihitung di ruang pengguna svg: getBBox sudah termasuk transform
  // lapisan, d3.zoomTransform bekerja di ruang itu, dan matriks layar svg
  // (viewBox) dipakai untuk bolak-balik ke piksel.
  const layer = (typeof currentMode !== "undefined" && currentMode === "topic_actor")
    ? bipartiteLayer : nodeLayer;
  const target = layer && layer.node ? layer.node() : null;
  const canvas = svg.node();
  if (target && canvas && typeof d3 !== "undefined") {
    const box = target.getBBox();
    const view = canvas.getBoundingClientRect();
    const viewMatrix = canvas.getScreenCTM();
    if (box.width > 1 && box.height > 1 && viewMatrix) {
      // Ruang yang benar-benar terlihat: sidebar kiri dan bilah bawah menutupi
      // svg, jadi memusatkan ke kotak svg menaruh isi di bawah sidebar.
      const insets = (typeof canvasInsets === "function")
        ? canvasInsets(view) : { left: 0, right: 0, top: 0, bottom: 0 };
      const roomW = view.width - insets.left - insets.right;
      const roomH = view.height - insets.top - insets.bottom;
      const layerMatrix = target.getScreenCTM();
      if (layerMatrix) {
        const zoomNow = d3.zoomTransform(canvas);
        const spanX = Math.abs(box.width * layerMatrix.a);
        const spanY = Math.abs(box.height * layerMatrix.d);
        const factor = Math.min(roomW / spanX, roomH / spanY) * 0.9;
        const inverse = viewMatrix.inverse();
        const centre = new DOMPoint(box.x + box.width / 2, box.y + box.height / 2)
          .matrixTransform(layerMatrix)
          .matrixTransform(inverse);
        const middle = new DOMPoint(
          view.left + insets.left + roomW / 2,
          view.top + insets.top + roomH / 2
        ).matrixTransform(inverse);
        const scale = zoomNow.k * factor;
        svg.call(
          zoom.transform,
          d3.zoomIdentity
            .translate(middle.x - scale * centre.x, middle.y - scale * centre.y)
            .scale(scale)
        );
      }
    }
  }
  // Semua simpul sudah dipaku lewat fx/fy dari initNodeCoordinates, jadi
  // menghentikan simulasi tidak menggeser apa pun — hanya menghentikan redraw.
  if (typeof simulation !== "undefined" && simulation) simulation.stop();
  return true;
})()
"""


class Cdp:
    """Klien CDP minimum: kirim perintah, catat permintaan jaringan berjalan."""

    def __init__(self, ws: Any) -> None:
        self._ws = ws
        self._next = 0
        self._pending: Dict[int, Tuple[str, Any]] = {}
        self._inflight: set = set()
        self._pump: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._pump = asyncio.create_task(self._drain())

    async def close(self) -> None:
        if self._pump is not None:
            self._pump.cancel()
            try:
                await self._pump
            except (asyncio.CancelledError, Exception):
                pass

    async def _drain(self) -> None:
        try:
            while True:
                try:
                    raw = await self._ws.recv()
                except Exception:
                    # Koneksi ditutup saat Chromium dimatikan; itu akhir yang wajar.
                    return
                try:
                    message = json.loads(raw)
                except ValueError:
                    # Satu frame rusak tidak boleh mematikan pompa selamanya.
                    continue
                if "id" in message:
                    entry = self._pending.pop(message["id"], None)
                    if entry is None:
                        continue
                    method, future = entry
                    if future.done():
                        continue
                    if "error" in message:
                        future.set_exception(RuntimeError(f"{method}: {message['error']}"))
                    else:
                        future.set_result(message.get("result", {}))
                    continue
                self._on_event(message)
        finally:
            # Future yang menunggu tidak boleh menggantung sampai timeout 60 detik.
            for method, future in list(self._pending.values()):
                if not future.done():
                    future.set_exception(RuntimeError(f"{method}: koneksi CDP tertutup"))
            self._pending.clear()

    def _on_event(self, message: Dict[str, Any]) -> None:
        method = message.get("method")
        params = message.get("params") or {}
        if method == "Page.frameStartedLoading":
            # Navigasi baru membatalkan permintaan lama; hitungan yang tersisa
            # dari bidikan sebelumnya akan menahan bidikan berikutnya.
            self._inflight.clear()
        elif method == "Network.requestWillBeSent":
            self._inflight.add(params.get("requestId"))
        elif method in ("Network.loadingFinished", "Network.loadingFailed"):
            self._inflight.discard(params.get("requestId"))

    @property
    def inflight(self) -> int:
        return len(self._inflight)

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._next += 1
        ident = self._next
        future = asyncio.get_running_loop().create_future()
        self._pending[ident] = (method, future)
        try:
            await self._ws.send(json.dumps({"id": ident, "method": method, "params": params or {}}))
        except Exception:
            self._pending.pop(ident, None)
            raise
        return await asyncio.wait_for(future, timeout=60)

    async def evaluate(self, expression: str) -> Any:
        result = await self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        # Skrip yang melempar tidak boleh lolos diam-diam: bidikan tanpa
        # pembingkaian tetap terlihat "berhasil" dan baseline-nya menipu.
        failure = result.get("exceptionDetails")
        if failure:
            detail = (failure.get("exception") or {}).get("description") or failure.get("text")
            raise RuntimeError(f"skrip di halaman gagal: {detail}")
        return (result.get("result") or {}).get("value")


async def _wait_ready(cdp: Cdp, mode: str, timeout: float = 40.0) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = await cdp.evaluate(READY_JS) or {}
        if last.get("ready") and last.get("mode") == mode and cdp.inflight == 0:
            return last
        await asyncio.sleep(0.25)
    raise RuntimeError(f"halaman tidak siap setelah {timeout:.0f} detik: {last}")


def chrome_path(explicit: Optional[str] = None) -> Optional[Path]:
    """
    Cari Chromium: argumen, lalu HORUS_CHROME, lalu PATH, lalu cache Playwright.

    None berarti tidak ditemukan; pemanggil menuliskannya sebagai kegagalan
    infrastruktur dengan petunjuk, bukan traceback.
    """
    if explicit:
        candidate = Path(explicit)
        return candidate if candidate.exists() else None
    env = (os.environ.get("HORUS_CHROME") or "").strip()
    if env:
        candidate = Path(env)
        return candidate if candidate.exists() else None
    for name in CHROME_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)
    cache = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache") / "ms-playwright"
    for pattern in ("chromium-*/chrome-win64/chrome.exe", "chromium-*/chrome-linux/chrome"):
        for candidate in sorted(cache.glob(pattern), reverse=True):
            return candidate
    return None


def _launch_chrome(profile: Path) -> subprocess.Popen:
    # Port 0 + profil sendiri: membaca port dari DevToolsActivePort di profil
    # itu. Port tetap membuat skrip menempel ke peramban milik orang lain bila
    # port tersebut sudah dipakai.
    if _CHROME is None:  # pragma: no cover - dijaga main()
        raise RuntimeError("Chromium belum ditentukan; jalankan dengan --chrome atau HORUS_CHROME")
    return subprocess.Popen(
        [
            str(_CHROME),
            "--headless=new",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-color-profile=srgb",
            "--disable-lcd-text",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _devtools_port(profile: Path, timeout: float = 30.0) -> int:
    marker = profile / "DevToolsActivePort"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists():
            text = marker.read_text(encoding="utf-8", errors="ignore").splitlines()
            if text and text[0].strip().isdigit():
                return int(text[0].strip())
        time.sleep(0.2)
    raise RuntimeError("Chromium tidak menulis DevToolsActivePort; gagal start?")


def _target(port: int, timeout: float = 30.0) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list") as response:
                pages = json.load(response)
            return next(item for item in pages if item["type"] == "page")
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f"target CDP tidak ditemukan di port {port}")


async def _capture_all(
    url: str, chosen: Sequence[Tuple[str, str, int]]
) -> List[Tuple[str, Path, Dict[str, Any]]]:
    import websockets

    CURRENT.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix="horus-visual-"))
    process = _launch_chrome(profile)
    written: List[Tuple[str, Path, Dict[str, Any]]] = []
    try:
        port = _devtools_port(profile)
        target = _target(port)
        async with websockets.connect(
            target["webSocketDebuggerUrl"], max_size=80 * 1024 * 1024
        ) as ws:
            cdp = Cdp(ws)
            await cdp.start()
            await cdp.send("Page.enable")
            await cdp.send("Runtime.enable")
            await cdp.send("Network.enable")
            await cdp.send(
                "Emulation.setEmulatedMedia",
                {
                    "features": [
                        {"name": "prefers-reduced-motion", "value": "reduce"},
                        {"name": "prefers-color-scheme", "value": "dark"},
                    ]
                },
            )
            for name, mode, width in chosen:
                await cdp.send(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": HEIGHT,
                        "deviceScaleFactor": 1,
                        "mobile": False,
                    },
                )
                # Ganti hash saja tidak memuat ulang dokumen, dan keadaan tampilan
                # hanya dibaca sekali saat boot. Tanpa perantara ini bidikan kedua
                # tetap menampilkan mode pertama.
                await cdp.send("Page.navigate", {"url": "about:blank"})
                await asyncio.sleep(0.2)
                await cdp.send("Page.navigate", {"url": f"{url}#{VIEW_HASH.format(mode=mode)}"})
                state = await _wait_ready(cdp, mode)
                if not state.get("nodes"):
                    raise RuntimeError(
                        f"{name}: halaman siap tapi tidak menggambar satu simpul pun"
                    )
                await cdp.evaluate(DISMISS_JS)
                await cdp.evaluate(FREEZE_JS)
                await asyncio.sleep(0.4)
                shot = await cdp.send(
                    "Page.captureScreenshot",
                    {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
                )
                path = CURRENT / f"{name}.png"
                path.write_bytes(base64.b64decode(shot["data"]))
                written.append((name, path, state))
                print(f"  {name:32s} {width}px  simpul {state.get('nodes')}")
            await cdp.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)
    return written


def _chrome_version() -> str:
    try:
        result = subprocess.run(
            [str(CHROME), "--version"], capture_output=True, text=True, timeout=20
        )
        return (result.stdout or result.stderr).strip() or "tidak diketahui"
    except Exception:
        return "tidak diketahui"


# ---------------------------------------------------------------- perintah


def _report(name: str, diff: Diff) -> None:
    status = "ok" if diff.passed else "BEDA"
    print(
        f"  {name:32s} {status:4s} {diff.differing:6d} piksel  "
        f"({diff.share * 100:.4f}%, anggaran {BUDGET_PX})  delta maks {diff.max_delta}"
    )
    if not diff.passed and diff.box is not None:
        print(
            f"    kotak perbedaan: x {diff.box[0]}..{diff.box[2]}, y {diff.box[1]}..{diff.box[3]}"
        )


def _write_manifest() -> None:
    MANIFEST.write_text(
        json.dumps(
            {
                "chrome": _chrome_version(),
                "widths": list(WIDTHS),
                "height": HEIGHT,
                "channel_tolerance": CHANNEL_TOLERANCE,
                "budget_px": BUDGET_PX,
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _check_manifest() -> Optional[int]:
    """None bila baseline boleh dipakai; kode keluar bila tidak."""
    if not MANIFEST.exists():
        print(f"baseline tanpa manifest: {MANIFEST} — jalankan --update")
        return EXIT_NO_BASELINE
    try:
        recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except ValueError:
        print(f"manifest rusak: {MANIFEST} — jalankan --update")
        return EXIT_NO_BASELINE
    if recorded.get("widths") != list(WIDTHS) or recorded.get("height") != HEIGHT:
        print(
            "baseline diambil pada ukuran lain "
            f"({recorded.get('widths')}x{recorded.get('height')}); jalankan --update"
        )
        return EXIT_NO_BASELINE
    # Toleransi ikut dibandingkan: melonggarkan ambang di kode lalu memakai
    # baseline lama membuat gerbangnya berubah jadi karet stempel tanpa jejak.
    for key, now in (("channel_tolerance", CHANNEL_TOLERANCE), ("budget_px", BUDGET_PX)):
        recorded_value = recorded.get(key)
        if recorded_value is not None and recorded_value != now:
            print(
                f"toleransi {key} berubah ({recorded_value} -> {now}); "
                f"jalankan --update supaya baseline dan gerbang sejalan"
            )
            return EXIT_NO_BASELINE
    current = _chrome_version()
    if recorded.get("chrome") != current:
        print(
            f"peringatan: baseline dari {recorded.get('chrome')!r}, sekarang {current!r}; "
            "selisih kecil bisa berasal dari peramban, bukan dari kode"
        )
    return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8021/")
    parser.add_argument("--only", default=None, help="saring bidikan: nama, mode, atau lebar")
    parser.add_argument(
        "--chrome",
        default=None,
        help="path Chromium/Chrome; tanpa ini dicari lewat HORUS_CHROME, PATH, lalu cache Playwright",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--update", action="store_true", help="tulis baseline dari tangkapan sekarang"
    )
    group.add_argument("--check", action="store_true", help="bandingkan tangkapan dengan baseline")
    group.add_argument("--calibrate", action="store_true", help="ukur selisih-diri tiap bidikan")
    args = parser.parse_args(argv)

    global _CHROME
    _CHROME = chrome_path(args.chrome)
    if _CHROME is None:
        print(
            "Chromium tidak ditemukan. Setel --chrome <path> atau HORUS_CHROME=<path>; "
            "tanpa peramban, gerbang ini tidak bisa membandingkan apa pun."
        )
        return EXIT_INFRA

    chosen = shots(args.only)

    if args.check:
        blocked = _check_manifest()
        if blocked is not None:
            return blocked
        missing = [name for name, _, _ in chosen if not (BASELINE / f"{name}.png").exists()]
        if missing:
            print("baseline belum ada: " + ", ".join(missing))
            print(f"jalankan --update lebih dulu (folder {BASELINE})")
            return EXIT_NO_BASELINE

    try:
        if args.calibrate:
            return _calibrate(args.url, chosen)
        print(f"menangkap {len(chosen)} bidikan dari {args.url}")
        _capture_all_sync(args.url, chosen)
    except (RuntimeError, ValueError, KeyError, OSError, asyncio.TimeoutError) as failure:
        # Lingkungan rusak bukan regresi tampilan; jangan pakai kode keluar 1.
        print(f"gagal menangkap: {failure}")
        return EXIT_INFRA

    if args.update:
        BASELINE.mkdir(parents=True, exist_ok=True)
        for name, _, _ in chosen:
            (BASELINE / f"{name}.png").write_bytes((CURRENT / f"{name}.png").read_bytes())
            print(f"  baseline ditulis: {BASELINE / (name + '.png')}")
        _write_manifest()
        return EXIT_OK

    failed = []
    for name, _, _ in chosen:
        try:
            diff = compare(
                decode_png((BASELINE / f"{name}.png").read_bytes()),
                decode_png((CURRENT / f"{name}.png").read_bytes()),
            )
        except ValueError as failure:
            print(f"  {name:32s} tidak bisa dibandingkan: {failure}")
            print("  ukuran bidikan berubah; jalankan --update bila perubahan itu disengaja")
            return EXIT_INFRA
        _report(name, diff)
        if not diff.passed:
            failed.append(name)

    if failed:
        print(f"regresi visual pada {len(failed)} bidikan: " + ", ".join(failed))
        return EXIT_REGRESSED
    print(f"tidak ada regresi pada {len(chosen)} bidikan (anggaran {BUDGET_PX} piksel)")
    return EXIT_OK


def _capture_all_sync(
    url: str, chosen: Sequence[Tuple[str, str, int]]
) -> List[Tuple[str, Path, Dict[str, Any]]]:
    return asyncio.run(_capture_all(url, chosen))


def _calibrate(url: str, chosen: Sequence[Tuple[str, str, int]]) -> int:
    """Tangkap berulang pada kode yang tidak berubah, laporkan selisih-diri."""
    print(f"kalibrasi: {CALIBRATION_PAIRS} pasang tangkapan per bidikan, kode tidak berubah")
    shares: Dict[str, List[float]] = {name: [] for name, _, _ in chosen}
    previous: Dict[str, bytes] = {}
    for attempt in range(CALIBRATION_PAIRS + 1):
        _capture_all_sync(url, chosen)
        snapshot = {name: (CURRENT / f"{name}.png").read_bytes() for name, _, _ in chosen}
        if attempt == 0:
            previous = snapshot
            continue
        for name, _, _ in chosen:
            diff = compare(decode_png(previous[name]), decode_png(snapshot[name]))
            shares[name].append(diff.share)
            _report(name, diff)
        previous = snapshot

    worst = max((max(values) for values in shares.values() if values), default=0.0)
    worst_px = round(worst * WIDTHS[-1] * HEIGHT)
    margin = BUDGET_PX / worst_px if worst_px else float("inf")
    verdict = "stabil" if worst_px <= BUDGET_PX else "TIDAK STABIL"
    print(
        f"selisih-diri terburuk {worst * 100:.4f}% (~{worst_px} piksel pada lebar terbesar), "
        f"anggaran {BUDGET_PX} piksel — margin {margin:.1f}x — {verdict}"
    )
    return EXIT_OK if worst_px <= BUDGET_PX else EXIT_UNSTABLE


if __name__ == "__main__":
    sys.exit(main())
