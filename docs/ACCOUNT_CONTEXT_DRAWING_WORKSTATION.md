# Account Context + Chart Workstation Upgrade

This upgrade makes Epinnox Terminal account-aware for PAPER/LIVE operation and adds a persistent TradingView-style chart drawing workstation.

## Account context

- BACKTEST remains synthetic and never requires an execution account.
- PAPER lists only paper accounts from the authenticated `epinnox-online` session.
- LIVE lists only live accounts. Account selection is available, but live order routing remains deliberately unarmed.
- The selected PAPER account is activated upstream before use and the paper runner is bound to that immutable account id.
- Before every paper mutation and each live-candle evaluation cycle, the runner verifies that the same account is still active and still a paper account. A context change fails closed.
- Browser credentials are never persisted by Terminal. Authentication authority remains `epinnox-online`.

## Timeframes

The chart workspace exposes 1m, 5m, 15m, 30m, 1h, 2h, 3h, 4h, 5h, 8h, D, 5D, W and M. Native venue intervals are used where available; custom intervals are deterministically aggregated from smaller HTX candles. Longer strategy intervals currently reuse the qualified 30m strategy parameter set and expose that fact through config rather than pretending a distinct preset was qualified.

## Drawing workstation

The left chart rail includes cursor/select, trend line, horizontal line, vertical line, channel, path, Fibonacci retracement, text notes, ruler, zoom mode, magnet/snap, keep-drawing, lock, hide, undo, redo and delete/clear controls.

Drawing geometry is stored as market coordinates (`timestamp`, `price`) in local storage by symbol. Rendering converts those market coordinates through Lightweight Charts on each visible-range change, so drawings remain anchored as the chart pans, zooms and resizes.

## Safety boundary

This milestone does not arm LIVE execution. It prepares account selection and visual workstation behavior while preserving the existing live safety boundary owned by `epinnox-online`.
