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


def candles() -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    base = 2400.0
    for i in range(180):
        px = base + (i % 20) * 1.25
        rows.append({
            "ts_ms": 1700000000000 + i * 60000,
            "open": px,
            "high": px + 4,
            "low": px - 4,
            "close": px + 1.5,
            "volume": 100 + i,
        })
    return rows


CANDLES = candles()


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
        body = {"generated_at_ms": 1700000000000, "runtime": {"controls": {"universe_enabled": True, "scanner_enabled": True}, "universe": {"state": "RUNNING", "generation": 4, "flow": {"quality": "VALID"}}, "scanner": {"state": "RUNNING", "cycle": 12}}, "summary": {"assets": 4, "active": 4, "high_participation": 1, "extreme": 0, "reported_notional_24h_total": 1000000000, "reported_notional_24h_spot": 400000000, "reported_notional_24h_derivatives": 600000000}, "categories": [{"name": "MAJOR", "count": 4}], "assets": [], "markets": [], "events": [], "source": "visual smoke", "selected_window": "8h"}
    elif "/api/market" in url:
        body = {"symbol": "ETH/USDT:USDT", "timeframe": "1m", "candles": CANDLES, "source": "visual smoke"}
    elif "/api/backtest" in url:
        body = {
            "symbol": "ETH/USDT:USDT", "timeframe": "5m", "strategy": "Supertrend", "backtest_profile": "TradingView Parity",
            "candles": CANDLES, "overlays": {}, "panes": {}, "markers": [], "trades": [], "open_position": None,
            "metrics": {"total_equity_pnl": 0, "open_pnl": 0, "profit_factor": 0, "win_rate_pct": 0, "max_drawdown_pct": 0, "target_hit_rate_pct": 0, "liquidation_exits": 0, "median_bars_to_exit": 0, "fees_paid": 0, "referral_revenue": 0, "trades_per_day": 0, "closed_trades": 0},
            "entry_model": {"label": "Supertrend", "policy": "Single"},
            "backtest_window": {"candles": len(CANDLES), "start_ts_ms": CANDLES[0]["ts_ms"], "end_ts_ms": CANDLES[-1]["ts_ms"]},
            "simulation": {"liquidation_model": "disabled"},
        }
    elif "/api/execution/accounts" in url:
        body = {"configured": False, "authenticated": False, "accounts": [], "active_account_id": None}
    else:
        route.continue_()
        return
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def shell_geometry(page) -> dict:
    def box(selector: str):
        return page.locator(selector).bounding_box() if page.locator(selector).count() else None
    return {
        "header": box("#epGlobalHeader"),
        "nav": box("#epGlobalNav"),
        "footer": box("#epGlobalFooter"),
        "workspace": box(".workspace"),
        "chart_stage": box(".chart-stage"),
        "drawing_toolbar": box("#drawingToolbar"),
        "scroll_width": page.evaluate("document.documentElement.scrollWidth"),
        "client_width": page.evaluate("document.documentElement.clientWidth"),
    }


def assert_shell(page, route_name: str) -> None:
    page.wait_for_selector("#epGlobalHeader", timeout=8000)
    page.wait_for_selector("#epGlobalNav", timeout=8000)
    page.wait_for_selector("#epGlobalFooter", timeout=8000)
    assert page.locator(".ep-nav-item").count() == 6, f"{route_name}: expected 6 global nav items"
    assert page.locator(".ep-nav-item.active").count() == 1, f"{route_name}: expected exactly one active nav item"
    assert page.locator("#epGlobalHeader").count() == 1, f"{route_name}: duplicate global header"
    assert page.locator("#epGlobalNav").count() == 1, f"{route_name}: duplicate global nav"
    assert page.locator("#epGlobalFooter").count() == 1, f"{route_name}: duplicate global footer"
    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 1, f"{route_name}: horizontal overflow {overflow}px"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {"failures": [], "captures": []}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
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
    failures: list[str] = []
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
                    label = f"{name}-{width}x{height}"
                    try:
                        page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
                        page.wait_for_timeout(700)
                        page.screenshot(path=str(OUT / f"{label}.png"), full_page=True)
                        assert_shell(page, name)
                        geometry = shell_geometry(page)
                        (OUT / f"{label}.json").write_text(json.dumps(geometry, indent=2), encoding="utf-8")
                        if name == "chart":
                            page.wait_for_selector("#drawingToolbar", timeout=8000)
                            nav_box = geometry["nav"]
                            stage_box = geometry["chart_stage"]
                            tool_box = geometry["drawing_toolbar"]
                            assert nav_box and stage_box and tool_box, "Chart shell geometry unavailable"
                            assert stage_box["x"] >= nav_box["x"] + nav_box["width"] - 1, "Chart stage overlaps global navigation"
                            assert tool_box["x"] >= stage_box["x"], "Chart drawing toolbar escapes chart stage"
                            assert tool_box["x"] >= nav_box["x"] + nav_box["width"] - 1, "Chart drawing toolbar overlaps global navigation"
                        summary["captures"].append(label)
                    except Exception as exc:
                        failures.append(f"{label}: {exc}")
                        summary["failures"].append(f"{label}: {exc}")
                        try:
                            page.screenshot(path=str(OUT / f"{label}-FAILED.png"), full_page=True)
                            (OUT / f"{label}-FAILED.json").write_text(json.dumps(shell_geometry(page), indent=2), encoding="utf-8")
                        except Exception:
                            pass
            browser.close()
        if console_errors:
            (OUT / "console-errors.txt").write_text("\n".join(console_errors), encoding="utf-8")
        summary["console_errors"] = console_errors
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if failures:
            raise AssertionError("\n".join(failures))
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
