from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_universe_safety_assets_are_loaded_after_global_chrome():
    shell = (WEB / "v4-shell.js").read_text(encoding="utf-8")
    for asset in (
        "v4-sitewide.css",
        "v4-sitewide.js",
        "v4-universe-refine.css",
        "v4-universe-safety.css",
        "v4-universe-refine.js",
        "v4-universe-safety.js",
    ):
        assert asset in shell
    assert shell.index("v4-sitewide.css") < shell.index("v4-universe-refine.css")
    assert shell.index("v4-universe-refine.css") < shell.index("v4-universe-safety.css")


def test_universe_mode_guard_is_fail_closed_and_exits_research_before_execution_context():
    js = (WEB / "v4-universe-safety.js").read_text(encoding="utf-8")
    assert "event.stopImmediatePropagation()" in js
    assert "mode.dataset.mode==='BACKTEST'" in js
    assert "leaveUniverseForMode" in js
    assert "requestAnimationFrame(()=>modeButton.click())" in js
    assert "aria-disabled" in js


def test_rejected_candidate_explains_scanner_qualification_evidence():
    js = (WEB / "v4-universe-safety.js").read_text(encoding="utf-8")
    css = (WEB / "v4-universe-safety.css").read_text(encoding="utf-8")
    assert "/api/scanner/runs?limit=12" in js
    assert "reject_reasons" in js
    assert "WHY THIS CANDIDATE FAILED" in js
    assert "Review scanner evidence" in js
    assert ".universe-reject-card" in css
    assert ".universe-reject-list" in css


def test_universe_research_handoff_remains_explicit():
    refine = (WEB / "v4-universe-refine.js").read_text(encoding="utf-8")
    research_html = (WEB / "research.html").read_text(encoding="utf-8")
    research_js = (WEB / "research.js").read_text(encoding="utf-8")
    assert "Paper qualification is blocked" in refine
    assert "Prepare Paper" in refine
    assert "UNIVERSE CANDIDATES" in research_html
    assert "/static/product-chrome.js" in research_html
    assert "epinnox.universe.saved.v1" in research_js
