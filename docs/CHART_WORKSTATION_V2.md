# Epinnox Terminal Chart Workstation V2

This document defines the chart-workstation refinement layer for Epinnox Terminal. It is intentionally limited to presentation and interaction semantics. Strategy calculations, backtest economics, PAPER account ownership, and LIVE safety gates remain owned by their existing backend/runtime contracts.

## Purpose

The chart is the single-market inspection cockpit. It must prioritize price structure first, research evidence second, and execution context third without allowing overlays, fills, drawings, or controls to obscure the underlying market.

The V2 refinement introduces four operating principles:

1. **Visual layers are independently controllable.** Volume, indicators, backtest fills, and manual drawings can be hidden without changing strategy logic.
2. **Indicator labels belong in a reserved projection gutter.** Price-series labels no longer compete directly with the latest candles.
3. **Execution markers adapt to zoom density.** Dense views collapse to compact points, medium views keep directional shapes, and close views add concise labels.
4. **Chart evidence and tabular evidence are linked.** Clicking a chart fill opens the corresponding trade in the bottom workbench; the existing trade-table-to-chart navigation remains intact.

## Runtime ownership

`web/chart-workstation-v2.js` loads before `web/app.js` on the Terminal page. This ordering is deliberate. The refinement layer establishes two hooks before the chart module boots:

- a guarded `Response.prototype.json` wrapper captures backtest presentation data and removes native backtest markers before the base chart paints them;
- a configurable `window.EpinnoxChartRuntime` property captures each newly created Lightweight Charts runtime so the refinement layer can render its own marker and label overlays using market coordinates.

The underlying backtest response is not economically changed. Only presentation fields are filtered for the active visual layer state. Volume hiding zeroes the display copy of volume after the backend has already calculated the backtest; indicator hiding filters chart series from the display payload; native markers are replaced by the adaptive SVG fill layer.

## Chart header

The chart header remains compact and chart-specific:

- market + timeframe + strategy identity on the left;
- environment context (`HTX PERPETUAL · BACKTEST|PAPER|LIVE`);
- TradingView-parity profile badge;
- Fit;
- Indicators;
- Layers;
- fullscreen.

Global navigation and strategy configuration do not belong here.

## Indicator manager

The **Indicators** control lists all active price overlays and lower-pane studies returned by the current strategy. Each study can be hidden independently. Hidden-study state is local to the browser workstation and persists across reloads.

The lower indicator pane has an independent visibility switch. Disabling the entire Indicators layer suppresses both overlays and pane studies from the next visual rebuild.

## Projection gutter

The chart runtime uses a larger right time-scale offset to reserve projection space beyond the most recent candle. Active price overlays are labeled in a collision-aware HTML gutter aligned to their current visible value. Labels are vertically separated when multiple series converge, such as VWAP / VWAP Upper / VWAP Lower.

The gutter is presentation-only. It does not create or alter any price series.

## Backtest fill rendering

The base application still supplies authoritative backtest marker receipts. V2 captures those receipts and renders them separately from the candlestick series:

- accepted long entries: outlined upward triangle;
- accepted short entries: outlined downward triangle;
- exits: filled diamond with reason-aware color;
- selected trade: visible halo.

Density policy is based on the number of fills inside the current visible time range:

- **86+ visible fills:** compact points;
- **29–85 fills:** directional shapes without text;
- **0–28 fills:** shapes plus concise labels.

This policy is deliberately visual. No marker is removed from the underlying backtest result.

## Trade navigation

Chart fill → trade ledger:

1. resolve the marker to the corresponding backtest trade by entry/exit timestamp;
2. activate the Trades dock tab;
3. invoke the existing workbench row interaction;
4. scroll the selected trade into view.

Trade ledger → chart continues to be owned by `v4-workbench.js`, which centers the chart around the selected trade window.

## Drawing toolbar

The original drawing engine remains authoritative for drawing state and market-coordinate persistence. V2 only reorganizes its controls.

The vertical rail is compacted into:

- Cursor;
- Line tools flyout: trend, horizontal, vertical, channel, path;
- Fibonacci;
- Annotation flyout: text, ruler;
- Zoom;
- Magnet;
- Keep drawing;
- Hide/show drawings;
- Utility flyout: undo, redo, delete/clear.

The incomplete drawing-selection lock affordance is not exposed in the compact rail. Drawings continue to persist in `(timestamp, price)` coordinates through the existing application runtime.

## Persistence

V2 browser preferences are stored under:

`epinnox.chart.workstation.v2`

Persisted values include:

- layer visibility;
- hidden studies;
- lower indicator-pane visibility.

This is UI state only and is intentionally separate from named strategy presets and execution-account state.

## Definition of done

A Chart Workstation V2 release is complete only when:

- `chart-workstation-v2.js` loads before `app.js`;
- JavaScript syntax checks pass;
- the chart workstation contract tests pass;
- existing Python/backtest/scanner/session tests remain green;
- runtime HTTP smoke verification serves the new assets;
- canonical `main` passes CI after integration;
- browser QA confirms no candle/label overlap at the supported desktop widths;
- drawing flyouts, indicator/layer popovers, fullscreen, marker hover/click, and trade bidirectional navigation are manually verified on the running build.
