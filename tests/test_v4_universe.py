from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_universe_surface_uses_cytoscape_and_scanner_evidence():
    js = (ROOT / "web" / "v4-universe.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "v4-universe.css").read_text(encoding="utf-8")
    shell = (ROOT / "web" / "v4-shell.js").read_text(encoding="utf-8")

    for token in [
        "UNIVERSE",
        "cytoscape@3.30.2",
        "/api/scanner/runs?limit=1",
        "response_correlation",
        "strategy_similarity",
        "Open in Backtest",
        "Strategy Heatmap",
        "Cluster Analysis",
        "epinnox.universe.v1",
    ]:
        assert token in js

    assert "Market Graph" not in js
    assert ".universe-workspace" in css
    assert ".universe-active" in css
    assert "/static/v4-universe.js" in shell
    assert "/static/v4-universe.css" in shell
