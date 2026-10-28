"""
Ukur renderer graf pada graf sintetis berskala besar.

Kriteria terima V2.1 menyebut angka (10.000 simpul / 50.000 sisi tampil di
bawah 2 detik, pan/zoom minimal 30 fps), jadi angkanya harus diukur, bukan
dikira-kira. Skrip ini menyuntikkan graf sintetis ke halaman yang sedang
berjalan, memanggil jalur render yang sama dengan boot biasa, lalu melaporkan
waktu tampil pertama dan frame per detik selama simulasi berjalan.

Pemakaian:
    horus-graph serve --port 8021 &
    python tools/measure_render.py --url http://127.0.0.1:8021/ --nodes 10000 --edges 50000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict

CHROME = Path(r"C:/Users/Hi/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe")
PORT = 9334
REPO_ROOT = Path(__file__).resolve().parents[1]

MEASURE = """
async (payload) => {
  const t0 = performance.now();
  if (typeof simulation !== "undefined" && simulation) simulation.stop();
  allData = { nodes: payload.nodes, links: payload.edges, metadata: {} };
  allData.nodes.forEach(n => {
    n.color = colorForType(n.entity_type);
    n.node_radius = computeNodeRadius(n);
  });
  initNodeCoordinates();
  if (window.HorusCanvas && HorusCanvas.handles(allData.nodes.length)) {
    HorusCanvas.mount(allData);
  } else {
    buildNodeLayer();
    applyCombinedFilters();
    initForceSimulation();
  }
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const paint = performance.now() - t0;

  const canvasMode = !!(window.HorusCanvas && HorusCanvas.handles(allData.nodes.length));
  let fps;
  if (canvasMode) {
    // Pan/zoom diukur dengan menggambar ulang 60 kali pada zoom berbeda:
    // frame diam tidak mengukur apa pun kecuali compositor.
    const started = performance.now();
    for (let index = 0; index < 60; index += 1) {
      HorusCanvas.setView(0.5 + ((index % 12) * 0.05));
    }
    fps = Math.round(60000 / (performance.now() - started));
  } else {
    let frames = 0;
    const started = performance.now();
    await new Promise(resolve => {
      function tick() {
        frames += 1;
        if (performance.now() - started < 2000) requestAnimationFrame(tick);
        else resolve();
      }
      requestAnimationFrame(tick);
    });
    fps = Math.round(frames / ((performance.now() - started) / 1000));
  }
  return {
    paint_ms: Math.round(paint),
    fps: fps,
    heap_mb: window.performance && performance.memory
      ? Math.round(performance.memory.usedJSHeapSize / 1048576)
      : null,
    nodes: allData.nodes.length,
    edges: allData.links.length,
    renderer: canvasMode ? "canvas" : "svg"
  };
}
"""


async def measure(
    url: str,
    nodes: int,
    edges: int,
    timeout: float,
    width: int,
    height: int,
    screenshot: str | None = None,
) -> Dict[str, Any]:
    import websockets

    sys.path.insert(0, str(REPO_ROOT / "tests" / "fixtures"))
    from synthetic_scale import synthetic_graph  # noqa: PLC0415 - jalur lokal

    payload = synthetic_graph(nodes, edges)
    process = subprocess.Popen(
        [
            str(CHROME),
            "--headless=new",
            f"--remote-debugging-port={PORT}",
            f"--window-size={width},{height}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        target = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as response:
                    pages = json.load(response)
                target = next(item for item in pages if item["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        assert target is not None, "target CDP tidak ditemukan"

        async with websockets.connect(
            target["webSocketDebuggerUrl"], max_size=200 * 1024 * 1024
        ) as ws:
            counter = 0

            async def send(method: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
                nonlocal counter
                counter += 1
                await ws.send(json.dumps({"id": counter, "method": method, "params": params or {}}))
                while True:
                    message = json.loads(await ws.recv())
                    if message.get("id") == counter:
                        return message.get("result", {})

            await send("Page.enable")
            await send("Runtime.enable")
            await send(
                "Emulation.setDeviceMetricsOverride",
                {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
            )
            await send("Page.navigate", {"url": url})
            await asyncio.sleep(6)

            result = await asyncio.wait_for(
                send(
                    "Runtime.evaluate",
                    {
                        "expression": f"({MEASURE})({json.dumps(payload)})",
                        "returnByValue": True,
                        "awaitPromise": True,
                    },
                ),
                timeout=timeout,
            )
            value = result.get("result", {})
            if "value" not in value:
                raise RuntimeError(json.dumps(value, ensure_ascii=False)[:500])
            if screenshot:
                import base64

                shot = await send("Page.captureScreenshot", {"format": "png"})
                Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
                Path(screenshot).write_bytes(base64.b64decode(shot["data"]))
            return value["value"]
    finally:
        process.terminate()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ukur renderer graf pada skala besar")
    parser.add_argument("--url", default="http://127.0.0.1:8021/")
    parser.add_argument("--nodes", type=int, default=10_000)
    parser.add_argument("--edges", type=int, default=50_000)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--paint-budget-ms", type=float, default=2000.0)
    parser.add_argument("--fps-floor", type=float, default=30.0)
    parser.add_argument("--heap-budget-mb", type=float, default=500.0)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=950)
    parser.add_argument("--screenshot", default=None, help="Simpan tangkapan layar ke path ini")
    args = parser.parse_args()

    try:
        hasil = asyncio.run(
            measure(
                args.url,
                args.nodes,
                args.edges,
                args.timeout,
                args.width,
                args.height,
                args.screenshot,
            )
        )
    except asyncio.TimeoutError:
        print(
            json.dumps(
                {
                    "status": "timeout",
                    "nodes": args.nodes,
                    "edges": args.edges,
                    "detail": f"render tidak selesai dalam {args.timeout:.0f} detik",
                },
                ensure_ascii=False,
            )
        )
        return 2

    heap = hasil.get("heap_mb")
    lolos = (
        hasil["paint_ms"] <= args.paint_budget_ms
        and hasil["fps"] >= args.fps_floor
        and (heap is None or heap <= args.heap_budget_mb)
    )
    hasil["status"] = "lolos" if lolos else "gagal"
    hasil["budget_paint_ms"] = args.paint_budget_ms
    hasil["budget_fps"] = args.fps_floor
    hasil["budget_heap_mb"] = args.heap_budget_mb
    print(json.dumps(hasil, ensure_ascii=False, indent=2))
    return 0 if lolos else 1


if __name__ == "__main__":
    raise SystemExit(main())
