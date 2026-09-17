from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_universe_has_one_runtime_surface_and_no_legacy_overlays():
    index = (WEB / "index.html").read_text(encoding="utf-8")
    shell = (WEB / "v4-shell.js").read_text(encoding="utf-8")
    assert index.count('href="/static/v4-universe.css"') == 1
    assert index.count('src="/static/v4-universe.js"') == 1
    assert "v4-universe" not in shell
    assert "v4-universe-refine" not in shell
    assert "v4-universe-safety" not in shell
    for obsolete in (
        "v4-universe-refine.css",
        "v4-universe-refine.js",
        "v4-universe-safety.css",
        "v4-universe-safety.js",
    ):
        assert not (WEB / obsolete).exists()


def test_live_pause_controls_are_backend_owned_and_selection_is_persistent():
    js = (WEB / "v4-universe.js").read_text(encoding="utf-8")
    assert "setLiveControl('universe_enabled'" in js
    assert "setLiveControl('scanner_enabled'" in js
    assert "/api/live/control" in js
    assert "state.selected=row.dataset.asset" in js
    assert "localStorage.setItem(STATE_KEY" in js
    assert "Never" not in js


def test_market_interpretation_is_exposed_as_evidence_backed_classification():
    js = (WEB / "v4-universe.js").read_text(encoding="utf-8")
    assert "MARKET-STATE CLASSIFICATION" in js
    assert "EVIDENCE, NOT FACT CLAIM" in js
    assert "EVIDENCE DRAWER" in js
    assert "baseline_median" in js
    assert "baseline_samples" in js
    assert "flow_price_state" in js
    assert "oi_context" in js
