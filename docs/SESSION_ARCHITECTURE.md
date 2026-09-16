# Epinnox Compute & Session Architecture

This foundation precedes the Terminal V4 and Scanner V2 interface overhaul.

## Compute boundary

Backtests and scanner runs are CPU/blocking research work. FastAPI routes submit them to a bounded workstation executor (`app/perf.py`) so the event loop remains available for account/session APIs. Market data uses a bounded in-process OHLCV cache: latest-window requests have a short TTL while explicit historical ranges use a longer TTL.

The sequential backtester keeps deterministic bar ordering but consumes NumPy arrays in the hot replay loop instead of `DataFrame.iterrows()`. Supertrend keeps the same recursive algorithm while removing repeated pandas `iloc` access. Shared fee-aware exit math lives in `app/economics.py` and is consumed by both backtest and paper execution code.

## Session as the operational unit

A PAPER session is now an independent durable runtime identified by `session_id` and bound to:

- Epinnox Online account id
- environment (`PAPER`)
- symbol/instrument
- timeframe
- strategy configuration snapshot
- runtime lifecycle/checkpoint state

`PaperSessionRegistry` owns the in-process runners while SQLite remains the durable source for session checkpoints and event history.

### Ownership rule

Only one active strategy session may own a given `account + instrument` pair. This prevents two strategies from silently fighting over the same net position.

### Current upstream account-context constraint

Epinnox Online currently routes paper mutations through the authenticated browser session's *active account*. Because the upstream order APIs are not yet account-scoped per request, Epinnox Terminal deliberately fails closed on concurrent sessions bound to different paper accounts.

Multiple PAPER sessions may run concurrently when they share the same active paper account and own different instruments. Multi-account concurrency becomes safe only when Epinnox Online accepts an explicit account id on authoritative execution mutations (or provides an equivalent isolated account-scoped execution context).

## Recovery

Browser cookies are never persisted. After a Terminal server restart, SQLite still contains every active session and its checkpoint. A user reconnects an individual session with the current authenticated Epinnox Online browser session through:

`POST /api/sessions/{session_id}/recover`

Recovery reconciles the authoritative upstream position before the runner resumes. Pending pre-restart intents remain fail-closed to prevent duplicate submissions.

## Session APIs

- `GET /api/sessions`
- `GET /api/sessions/{session_id}`
- `POST /api/sessions/paper/start`
- `POST /api/sessions/{session_id}/recover`
- `POST /api/sessions/{session_id}/stop`

The legacy `/api/paper-live/*` endpoints remain compatibility shims for the current UI. Terminal V4 should move to the session APIs directly.

## Next interface phases

1. Terminal V4 command-center shell: fixed-height tablet workspace, session rail, contextual inspector, compact bottom dock.
2. Backtest workbench: pinned experiments, side-by-side comparison, trade jump-to-chart, CSV/evidence exports, promote-to-paper.
3. Scanner V2: compact query builder, background progress, candidate leaderboard, evidence inspector, compare, paper qualification.
4. Realtime fabric: WebSocket market/runtime/order/fill events and incremental chart updates.
