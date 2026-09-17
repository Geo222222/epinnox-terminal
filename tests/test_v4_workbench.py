from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v4_workbench_assets_present_on_initial_page():
    js = (ROOT / "web" / "v4-workbench.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "v4-workbench.css").read_text(encoding="utf-8")
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    shell = (ROOT / "web" / "v4-shell.js").read_text(encoding="utf-8")

    for token in ["Pin result", "Compare", "Trades CSV", "Equity CSV", "setVisibleRange", "epinnox.v4.pins.v1"]:
        assert token in js
    assert "/static/v4-workbench.css" in index
    assert "/static/v4-workbench.js" in index
    assert "v4-workbench" not in shell
    assert ".wb-compare" in css
    assert ".wb-selected-trade" in css
