from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v5_chart_workspace_assets_are_part_of_initial_page_boot():
    index = read("web/index.html")
    shell = read("web/v4-shell.js")
    js = read("web/v5-chart-workspace.js")
    css = read("web/v5-chart-workspace.css")

    assert '/static/v5-chart-workspace.css' in index
    assert '/static/v5-chart-workspace.js' in index
    assert '<body class="v5-chart-active">' in index
    assert 'v5-chart-workspace' not in shell
    assert "v5QuickStrategy" in js
    assert "v5StrategyModal" in js
    assert "v5PositionDock" in js
    assert "v5-chart-active" in css


def test_v5_chart_is_chart_first_and_not_right_inspector_driven():
    css = read("web/v5-chart-workspace.css")
    js = read("web/v5-chart-workspace.js")
    assert "workspace>.inspector{display:none!important}" in css
    assert "host.appendChild(pos)" in js
    assert "appendChild(panel)" in js
    # Global workspace columns belong to product-chrome.css, never the Chart layer.
    assert "grid-template-columns:var(--v5-rail)" not in css
    assert ".session-rail" not in css
    assert ".rail-workspace" not in css


def test_v5_chart_host_has_measurable_height():
    css = read("web/v5-chart-workspace.css")
    assert "chart-stage{position:relative;grid-row:2;height:100%;min-height:0;display:grid;grid-template-rows:minmax(0,1fr) auto;overflow:hidden}" in css
    assert "#chart{height:100%!important;min-height:180px!important}" in css
    assert "#chart{height:auto!important" not in css


def test_v5_primary_strategy_remains_quickly_changeable():
    js = read("web/v5-chart-workspace.js")
    assert "source.value=quick.value" in js
    assert "source.dispatchEvent(new Event('change',{bubbles:true}))" in js
    assert "v5StrategySettings" in js


def test_v5_does_not_observe_or_mutate_global_shell_navigation():
    js = read("web/v5-chart-workspace.js")
    assert "bodyObserver" not in js
    assert "MutationObserver" in js  # strategy option synchronization is local and intentional
    assert "installRailIcons" not in js
    assert "navIcons" not in js
    assert "rail-primary" not in js
    assert "subtree:true" not in js


def test_v5_has_no_retired_takeover_compatibility_paths():
    js = read("web/v5-chart-workspace.js")
    assert "scanner-active" not in js
    assert "railScanner" not in js
    assert "installStyle" not in js
    assert "modalSnapshot" not in js
    assert "snapshotStrategy" not in js
    assert "strategyFields" not in js
    assert "bindLegacyStrategyEntrypoints" not in js


def test_icon_ownership_is_separated_between_shell_and_chart():
    chart_js = read("web/v5-chart-workspace.js")
    shell_js = read("web/product-chrome.js")

    # Chart workspace owns drawing/strategy icons only.
    for token in ["trend:'<svg", "settings:'<svg", "magnet:'<svg", "trash:'<svg"]:
        assert token in chart_js
    for token in ["chart:'<svg", "scanner:'<svg", "universe:'<svg"]:
        assert token not in chart_js

    # Global navigation belongs to the canonical shell.
    assert "const NAV=" in shell_js
    for name in ["Terminal", "Scanner", "Universe", "Sessions", "Research", "Strategies"]:
        assert name in shell_js
    assert "ep-nav-item" in shell_js
