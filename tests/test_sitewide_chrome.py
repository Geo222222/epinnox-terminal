from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_primary_v4_shell_loads_sitewide_polish():
    shell = (WEB / "v4-shell.js").read_text(encoding="utf-8")
    assert "v4-final-chrome.js" in shell
    assert "v4-sitewide.js" in shell
    assert "v4-sitewide.css" in shell


def test_product_pages_share_command_center_chrome():
    for name in ("scanner.html", "sessions.html", "research.html", "strategies.html"):
        html = (WEB / name).read_text(encoding="utf-8")
        assert "/static/product-chrome.css" in html
        assert "/static/product-chrome.js" in html
        assert "EPINNOX TERMINAL" in html


def test_product_chrome_contains_live_market_navigation_and_runtime_surfaces():
    js = (WEB / "product-chrome.js").read_text(encoding="utf-8")
    for symbol in ("BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT"):
        assert symbol in js
    assert "/api/market" in js
    assert "/api/symbols" in js
    assert "/api/sessions" in js
    assert "/api/execution/status" in js
    assert "Evidence First" in js
    assert "Serve Benjamin" in js


def test_sitewide_surface_polish_covers_scanner_chart_universe_and_token_identity():
    js = (WEB / "v4-sitewide.js").read_text(encoding="utf-8")
    css = (WEB / "v4-sitewide.css").read_text(encoding="utf-8")
    assert "v4ScannerRows" in js
    assert "universeBottomBody" in js
    assert "siteMarketIcon" in js
    assert ".scanner-workspace-v4" in css
    assert ".chart-workspace" in css
    assert ".universe-workspace" in css
    assert ".site-token.eth" in css
