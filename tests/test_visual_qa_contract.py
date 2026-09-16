from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def test_v4_qa_asset_is_loaded_after_universe_safety():
    shell = read("v4-shell.js")
    assert "/static/v4-visual-qa.css" in shell
    assert shell.index("/static/v4-visual-qa.css") > shell.index("/static/v4-universe-safety.css")


def test_v4_qa_covers_reference_viewports_and_surfaces():
    css = read("v4-visual-qa.css")
    assert "min-width:1700px" in css
    assert "min-width:1360px" in css
    assert "min-width:981px" in css
    for selector in [
        ".chart-workspace",
        ".scanner-workspace-v4",
        ".universe-workspace",
        ".universe-main",
        ".bottom-dock",
        ".inspector",
    ]:
        assert selector in css
    assert "prefers-reduced-motion" in css


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
