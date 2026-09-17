from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_universe_surface_is_live_flow_terminal():
    js = (WEB / "v4-universe.js").read_text(encoding="utf-8")
    css = (WEB / "v4-universe.css").read_text(encoding="utf-8")
    shell = (WEB / "v4-shell.js").read_text(encoding="utf-8")

    for token in [
        "MARKET UNIVERSE",
        "/api/live/universe",
        "/api/live/control",
        "LIVE UNIVERSE",
        "LIVE SCANNER",
        "NEW_YORK",
        "LONDON",
        "ASIA",
        "RELATIVE_FLOW",
        "FLOW_SURGES",
        "OI_EXPANSION",
        "scanner_score_components",
        "EVIDENCE DRAWER",
        "epinnox.universe.flow.v2",
        "animateReorder",
        "state-pulse",
        "epinnox:open-chart",
    ]:
        assert token in js

    assert "cytoscape" not in js.lower()
    assert "/api/scanner/runs?limit=1" not in js
    assert ".universe-workspace" in css
    assert ".u-row.state-pulse" in css
    assert "prefers-reduced-motion" in css
    assert "/static/v4-universe.js" in shell
    assert "/static/v4-universe.css" in shell
    assert "v4-universe-refine" not in shell
    assert "v4-universe-safety" not in shell


def test_universe_motion_is_event_driven_not_clock_decoration():
    js = (WEB / "v4-universe.js").read_text(encoding="utf-8")
    css = (WEB / "v4-universe.css").read_text(encoding="utf-8")

    assert "stateBefore!==stateNow" in js
    assert "tick-up" in js and "tick-down" in js
    assert "value-change" in js
    assert "requestAnimationFrame(()=>animateReorder" in js
    assert "@keyframes uPulse" in css
    assert "animation:uTickUp" in css
    assert "animation:uTickDown" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
