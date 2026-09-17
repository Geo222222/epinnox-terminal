from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "visual-shell"
BASE = "http://127.0.0.1:8010"
VIEWPORTS = [(2560, 1440), (1920, 1080), (1440, 900), (1366, 768)]
ROUTES = [
    ("chart", "/"),
    ("scanner", "/scanner"),
    ("universe", "/?universe=1"),
    ("sessions", "/sessions"),
    ("research", "/research"),
    ("strategies", "/strategies"),
]


def wait_server(timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(f"{BASE}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("Epinnox server did not become ready")


def fulfill_api(route) -> None:
    url = route.request.url
    if "/api/symbols" in url:
        body = {"symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT"]}
    elif "/api/sessions" in url:
        body = {"schema_version": 1, "sessions": []}
    elif "/api/live/status" in url:
        body = {"controls": {"universe_enabled": True, "scanner_enabled": True}, "universe": {"state": "RUNNING", "generation": 4}, "scanner": {"state": "RUNNING", "cycle": 12, "active_batch": []}}
    elif "/api/live/universe" in url:
        body = {"generated_at_ms": 0, "runtime": {"controls": {"universe_enabled": True, "scanner_enabled": True}, "universe": {"state": "RUNNING", "generation": 4, "flow": {"quality": "VALID"}}, "scanner": {"state": "RUNNING", "cycle": 12}}, "summary": {"assets": 4, "active": 4, "high_participation": 1, "extreme": 0, "reported_notional_24h_total": 1000000000, "reported_notional_24h_spot": 400000000, "reported_notional_24h_derivatives": 600000000}, "categories": [{"name": "MAJOR", "count": 4}], "assets": [], "markets": [], "events": [], "source": "visual smoke", "selected_window": "8h"}
    elif "/api/market" in url:
        candles = []
        base = 2400.0
        for i in range(180):
            px = base + (i % 20) * 1.25
            candles.append([1700000000000 + i * 60000, px, px + 4, px - 4, px + 1.5, 100 + i])
        body = {"symbol": "ETH/USDT:USDT", "timeframe": "1m", "candles": candles, "source": "visual smoke"}
    elif "/api/execution/accounts" in url:
        body = {"configured": False, "authenticated": False, "accounts": [], "active_account_id": None}
    else:
        route.continue_()
        return
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def assert_shell(page, route_name: str) -> None:
    page.wait_for_selector("#epGlobalHeader", timeout=8000)
    page.wait_for_selector("#epGlobalNav", timeout=8000)
    page.wait_for_selector("#epGlobalFooter", timeout=8000)
    assert page.locator(".ep-nav-item").count() == 6, f"{route_name}: expected 6 global nav items"
    assert page.locator(".ep-nav-item.active").count() == 1, f"{route_name}: expected exactly one active nav item"
    assert page.locator("#epGlobalHeader").count() == 1
    assert page.locator("#epGlobalNav").count() == 1
    assert page.locator("#epGlobalFooter").count() == 1


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["EPINNOX_DISABLE_LIVE_INTELLIGENCE"] = "1"
    env["PYTHONPATH"] = str(ROOT)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_server()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            context.route("**/api/**", fulfill_api)
            page = context.new_page()
            console_errors: list[str] = []
            page.on("console", lambda msg: console_errors.append(f"{page.url}: {msg.text}") if msg.type == "error" else None)
            for width, height in VIEWPORTS:
                page.set_viewport_size({"width": width, "height": height})
                for name, path in ROUTES:
                    page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
                    assert_shell(page, name)
                    page.wait_for_timeout(650)
                    if name == "chart":
                        page.wait_for_selector("#drawingToolbar", timeout=8000)
                        nav_box = page.locator("#epGlobalNav").bounding_box()
                        tool_box = page.locator("#drawingToolbar").bounding_box()
                        assert nav_box and tool_box
                        assert tool_box["x"] >= nav_box["x"] + nav_box["width"] - 1, "Chart drawing toolbar overlaps global navigation"
                    page.screenshot(path=str(OUT / f"{name}-{width}x{height}.png"), full_page=True)
            browser.close()
        if console_errors:
            (OUT / "console-errors.txt").write_text("\n".join(console_errors), encoding="utf-8")
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
