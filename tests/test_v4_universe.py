from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_universe_surface_is_live_flow_terminal():
    js = (WEB / "v4-universe.js").read_text(encoding="utf-8")
    css = (WEB / "v4-universe.css").read_text(encoding="utf-8")
    index = (WEB / "index.html").read_text(encoding="utf-8")
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
    assert "/static/v4-universe.js" in index
    assert "/static/v4-universe.css" in index
    assert "v4-universe" not in shell
    assert "v4-universe-refine" not in shell
    assert "v4-universe-safety" not in shell


def test_universe_selected_session_drives_backend_flow_baseline():
    js = (WEB / "v4-universe.js").read_text(encoding="utf-8")
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app" / "live_intelligence.py").read_text(encoding="utf-8")

    assert "windowKey=state.session==='LIVE'?'5m':state.session" in js
    assert "/api/live/universe?window=${encodeURIComponent(windowKey)}" in js
    assert "state.session=b.dataset.session;save();syncControls();refresh(true)" in js
    assert "f.selected_window===normalized" in js
    assert 'def live_universe(window: str = Query("8h"))' in main
    assert "live_intelligence.universe_snapshot(window)" in main
    assert 'def universe_snapshot(self, selected_window: str = "8h")' in runtime
    assert "market_flow.asset_snapshot(market, selected_window)" in runtime


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
