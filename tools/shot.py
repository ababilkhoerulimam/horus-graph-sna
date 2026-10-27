"""Tangkapan layar ad-hoc lewat CDP untuk verifikasi visual manual."""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CHROME = Path(r"C:/Users/Hi/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe")
PORT = 9333
OUT = Path(r"C:/Github/horus-graph/.shots")


async def main(url: str, script: str, name: str, width: int = 1600, height: int = 1100) -> None:
    import websockets

    OUT.mkdir(exist_ok=True)
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

        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=80 * 1024 * 1024) as ws:
            counter = 0

            async def send(method: str, params=None):
                nonlocal counter
                counter += 1
                await ws.send(json.dumps({"id": counter, "method": method, "params": params or {}}))
                while True:
                    message = json.loads(await ws.recv())
                    if message.get("id") == counter:
                        return message.get("result", {})

            await send("Page.enable")
            await send("Runtime.enable")
            await send("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
            })
            await send("Page.navigate", {"url": url})
            await asyncio.sleep(6)
            result = await send("Runtime.evaluate", {
                "expression": script, "returnByValue": True, "awaitPromise": True,
            })
            print(json.dumps(result.get("result", {}).get("value"), ensure_ascii=False, indent=2))
            await asyncio.sleep(1.2)
            shot = await send("Page.captureScreenshot", {"format": "png"})
            path = OUT / f"{name}.png"
            path.write_bytes(base64.b64decode(shot["data"]))
            print("tersimpan:", path)
    finally:
        process.terminate()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3]))
