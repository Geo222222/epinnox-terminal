from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v5_chart_workspace_assets_exist_and_are_loaded():
    shell = read("web/v4-shell.js")
    js = read("web/v5-chart-workspace.js")
    css = read("web/v5-chart-workspace.css")
    assert "v5-chart-workspace.js" in shell
    assert "v5-chart-workspace.css" in shell
    assert "v5QuickStrategy" in js
    assert "v5StrategyModal" in js
    assert "v5PositionDock" in js
    assert "v5-chart-active" in css


def test_v5_chart_is_chart_first_and_not_right_inspector_driven():
    css = read("web/v5-chart-workspace.css")
    js = read("web/v5-chart-workspace.js")
    assert "workspace>.inspector{display:none!important}" in css
    assert "grid-template-columns:var(--v5-rail) minmax(0,1fr)" in css
    assert "host.appendChild(pos)" in js
    assert "appendChild(panel)" in js


def test_v5_primary_strategy_remains_quickly_changeable():
    js = read("web/v5-chart-workspace.js")
    assert "source.value=quick.value" in js
    assert "source.dispatchEvent(new Event('change',{bubbles:true}))" in js
    assert "v5StrategySettings" in js


def test_v5_uses_scoped_body_class_observer_only():
    js = read("web/v5-chart-workspace.js")
    assert "bodyObserver.observe(document.body,{attributes:true,attributeFilter:['class']})" in js
    assert "subtree:true" not in js


def test_v5_drawing_and_navigation_controls_use_svg_icons():
    js = read("web/v5-chart-workspace.js")
    for token in ["chart:'<svg", "scanner:'<svg", "universe:'<svg", "trend:'<svg", "settings:'<svg"]:
        assert token in js
