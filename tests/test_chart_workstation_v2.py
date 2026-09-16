from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_chart_workstation_assets_are_loaded_before_app_runtime():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'href="/static/chart-workstation-v2.css"' in html
    assert 'src="/static/chart-workstation-v2.js"' in html
    assert html.index('src="/static/chart-workstation-v2.js"') < html.index('src="/static/v4-shell.js"')
    assert html.index('src="/static/chart-workstation-v2.js"') < html.index('src="/static/app.js"')


def test_chart_workstation_has_density_layers_and_indicator_management():
    js = (WEB / "chart-workstation-v2.js").read_text(encoding="utf-8")
    assert "EpinnoxChartRuntime" in js
    assert "rightOffset:16" in js
    assert "cwLayersButton" in js
    assert "cwIndicatorsPopover" in js
    assert "cwExecutionLayer" in js
    assert "cwSeriesGutter" in js
    assert "rows.length<=28" in js
    assert "rows.length<=85" in js
    assert "openMarkerTrade" in js
    assert "compactDrawingToolbar" in js
    assert "prefs.hiddenStudies" in js


def test_chart_workstation_css_keeps_drawing_rail_compact():
    css = (WEB / "chart-workstation-v2.css").read_text(encoding="utf-8")
    assert ".drawing-toolbar.cw-drawing-toolbar" in css
    assert "max-height:none" in css
    assert ".cw-tool-flyout" in css
    assert ".cw-series-gutter" in css
    assert ".cw-marker-tooltip" in css
    assert ".cw-fullscreen" in css
