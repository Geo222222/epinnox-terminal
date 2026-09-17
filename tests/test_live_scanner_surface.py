from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_scanner_is_continuous_runtime_workspace():
    html = (WEB / "scanner.html").read_text(encoding="utf-8")
    js = (WEB / "scanner.js").read_text(encoding="utf-8")
    css = (WEB / "scanner.css").read_text(encoding="utf-8")

    for token in [
        "Live Scanner",
        "SCANNER MANDATE",
        "LIVE CANDIDATE LEADERBOARD",
        "OPERATIONS",
        "RUNTIME EVENTS",
        'id="scannerLiveToggle"',
        'id="universeLiveToggle"',
        'id="pauseAll"',
    ]:
        assert token in html

    for token in [
        "/api/live/status",
        "/api/live/universe?window=8h",
        "/api/live/control",
        "/api/live/mandate",
        "Mandate accepted",
        "active_batch",
        "coverage_state",
        "qualification_state",
    ]:
        assert token in js

    assert "/api/scanner/run" not in js
    assert "runScan" not in js
    assert "Run opportunity scan" not in html
    assert ".runtime-strip" in css
    assert ".operations-grid" in css


def test_scanner_keeps_execution_boundary_explicit():
    html = (WEB / "scanner.html").read_text(encoding="utf-8")
    assert "Execution isolated" in html
    assert "Research never places orders" in html
