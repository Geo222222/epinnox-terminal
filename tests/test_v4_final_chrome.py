from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_final_chrome_assets_and_contract():
    js = (ROOT / "web" / "v4-final-chrome.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "v4-final-chrome.css").read_text(encoding="utf-8")
    shell = (ROOT / "web" / "v4-shell.js").read_text(encoding="utf-8")

    for token in [
        "chromeTickerDeck",
        "chromeSymbolSearch",
        "chromeFooterTickers",
        "inspectorAssetHero",
        "universeMarketCard",
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "XRP/USDT:USDT",
        "sparkline",
        "applySymbol",
    ]:
        assert token in js

    for token in [
        ".ticker-card:hover",
        ".asset-icon.eth",
        ".rail-workspace-polished.active",
        ".universe-market-card",
        ".chrome-footer",
    ]:
        assert token in css

    assert "/static/v4-final-chrome.js" in shell
    assert "/static/v4-final-chrome.css" in shell
