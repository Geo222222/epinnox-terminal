from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def test_canonical_home_surfaces_own_their_visual_contracts():
    index = read("index.html")
    shell = read("v4-shell.js")
    universe_css = read("v4-universe.css")
    chart_css = read("v5-chart-workspace.css")

    assert "/static/v4-universe.css" in index
    assert "/static/v5-chart-workspace.css" in index
    assert "v4-visual-qa.css" not in index
    assert "v4-visual-qa" not in shell
    assert ".u-body" in universe_css
    assert ".u-table-shell" in universe_css
    assert ".u-inspector" in universe_css
    assert "prefers-reduced-motion" in universe_css
    assert "body.v5-chart-active .chart-workspace" in chart_css
    assert "#chart{height:100%!important;min-height:180px!important}" in chart_css


def test_obsolete_home_chrome_assets_are_gone():
    obsolete = [
        "v4-command-center.css",
        "v4-command-center.js",
        "v4-scanner-v2.js",
        "v4-final-chrome.css",
        "v4-final-chrome.js",
        "v4-sitewide.css",
        "v4-sitewide.js",
        "v4-visual-qa.css",
        "v4-universe-refine.css",
        "v4-universe-refine.js",
        "v4-universe-safety.css",
        "v4-universe-safety.js",
    ]
    for name in obsolete:
        assert not (WEB / name).exists(), name


def test_standalone_product_pages_share_visual_qa():
    for name in ["scanner.css", "sessions.css", "research.css", "strategies.css"]:
        assert "product-visual-qa.css" in read(name)
    css = read("product-visual-qa.css")
    for selector in [
        ".product-header.pc-header",
        ".product-sidebar",
        ".scanner-workbench",
        ".session-workbench",
        ".research-grid",
        ".strategy-layout",
        ".pc-footer",
    ]:
        assert selector in css
    assert "min-width:821px" in css
    assert "prefers-reduced-motion" in css
