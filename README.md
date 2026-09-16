# Epinnox Terminal

TradingView-style strategy research and execution terminal for Epinnox.

The terminal reproduces the Pine Script experience in Python and extends it with deterministic multi-strategy confirmation:

- HTX USDT-margined futures market data via CCXT
- 15 selectable strategy signal generators
- single-strategy or composite entry models
- `All Recent Events`, `Quorum Recent Events`, and `Primary + All States` confirmation policies
- automatic 1m / 5m / 15m / 30m presets
- fill-aware, fee-aware break-even and profit exits
- signal-qualified pyramiding
- sequential candle replay backtesting
- fees, referral economics, MAE/MFE, drawdown, liquidation approximation, bars/time held
- TradingView-like candlestick chart, volume, strategy overlays, indicator panes, entry/exit markers
- per-entry confirmation receipts in the trade ledger
- fail-closed PAPER live runner using live HTX candles and `epinnox-online` paper execution
- persistent browser workspaces, durable named presets, versioned defaults and SQLite paper-runtime recovery
- LIVE mode deliberately remains unarmed in this repository

## Run locally

Run `epinnox-online` first if you want PAPER live execution, then start the terminal:

```bash
cd epinnox-terminal
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt

# Windows PowerShell example
$env:EPINNOX_ONLINE_BASE_URL="http://localhost:8000"

uvicorn app.main:app --reload --port 8010
```

Open <http://localhost:8010>.

## Persistent workspace and settings

Epinnox Terminal separates convenience state, application defaults and execution state instead of treating all persistence as one settings blob.

- `localStorage` keeps the browser workspace across reloads and browser restarts: symbol, timeframe, strategy/composite model, backtest profile/window, sizing, fees, exits and operating mode.
- `sessionStorage` keeps per-tab UI state such as the open inspector tab, bottom dock tab and indicator-pane visibility.
- `config/settings.json` is the versioned application settings file for global defaults, feature flags and named special configurations.
- `data/settings.last-known-good.json` is generated locally after a valid settings load and is used as a fallback if the primary settings file becomes invalid.
- `data/epinnox_terminal.db` is the local SQLite runtime database for durable paper sessions, checkpoints, event history and named workspace presets.

The generated runtime files under `data/` are ignored by Git.

Named workspace presets can be saved, applied and deleted from the Strategy inspector. Browser autosave and server-side named presets are separate: autosave remembers the current workstation state, while named presets are intentional reusable configurations.

The terminal also keeps lightweight metadata for the most recent backtest in browser storage so a reload does not erase the identity of the current experiment.

## Composite entries

The Primary strategy is the timing source. Up to two confirmations can be selected in the UI.

Policies:

- `Single` — primary event only; Pine-parity baseline.
- `Primary + All States` — the primary event must fire now and every confirmation strategy must currently agree directionally.
- `All Recent Events` — every selected strategy must have produced a same-direction event inside the confirmation window.
- `Quorum Recent Events` — at least the configured number of selected strategies must have produced a same-direction event inside the confirmation window.

Recent-event policies emit one entry event when a confirmation cluster first becomes valid; they do not repeatedly pyramid from the same stale rolling window.

A useful first three-strategy experiment is:

```text
Primary:       Stochastic Reversal
Confirmation:  Supertrend
Confirmation:  ADX Trend
Policy:        Primary + All States
```

Each entry stores a receipt showing which strategies matched and, for recent-event policies, the age of each confirming event.

## Example $50 / 200x sizing

The terminal uses the policy discussed during the Pine experiment:

```text
account equity       = $50
leverage             = 200x
effective capacity   = $10,000
allocation per layer = 5%
notional per entry   = $500
margin per entry     = $2.50
```

Pyramiding adds another layer only on a new qualifying composite entry event, up to the configured maximum.

## Backtest timing

The Python engine replays candles sequentially. Signals are evaluated at a completed candle and market entries fill at that candle close, matching the Pine experiment's `process_orders_on_close=true` intent. Profit targets are eligible from the next candle onward, so movement that occurred before the entry cannot manufacture a historical target fill.

When a later OHLC bar touches both a risk boundary and profit target, liquidation/stop receives conservative precedence because OHLC alone does not establish intrabar path.

## PAPER live mode

`epinnox-online` remains execution authority. The terminal does not store HTX API credentials.

PAPER mode:

1. evaluates the same Python entry model on the latest completed HTX candle;
2. forwards the current Epinnox session cookie server-to-server;
3. calls `/api/account/paper-state` before every mutation;
4. refuses to trade unless the active upstream account is a paper profile;
5. submits market entries through `/api/orders`;
6. reads the authoritative paper position from `/api/positions`;
7. recalculates the fee-aware target from actual paper average entry;
8. arms take-profit / optional stop through `/api/positions/sl-tp`;
9. supports configured maximum-bars timeout through `/api/positions/close`.

### Paper restart recovery

The paper runner checkpoints its strategy request, session id, last processed candle, latest signal, layer count, position snapshot, pending intent and event history to SQLite. On a Terminal server restart it does **not** trust that local position snapshot as truth. It first re-checks the upstream paper account and `/api/positions`, reconciles the actual position, then resumes from the last completed candle.

Order client ids are deterministic per paper session, completed candle, side and layer. A pending intent is persisted before submission so a restart can detect an ambiguous pre-crash mutation rather than blindly creating a duplicate order.

If recovery cannot prove the upstream PAPER state, the runner enters `RECOVERY_REQUIRED` and stays fail-closed. The Position inspector exposes a Recover action so the current browser session can re-attempt reconciliation without persisting browser credentials or cookies to disk.

A normal server shutdown writes a restart checkpoint and leaves the durable session recoverable. An explicit **Stop** changes the durable runner state to `STOPPED`; it still does not forcibly close an existing upstream paper position.

## LIVE mode

LIVE is intentionally not armed here. `epinnox-online` already owns credentials, venue mutation safety, confirmations, position reconciliation and HTX execution. A separate qualification milestone should wire autonomous live strategy intents through those existing controls rather than bypassing them.

## Runtime verification

Repository-level tests are followed by a real-process HTTP smoke gate:

```bash
python scripts/runtime_smoke.py
```

The script boots FastAPI through Uvicorn, verifies the canonical pages, health/config contracts, Scanner persistence endpoint, and the final V4/Universe/visual-QA assets, then shuts the process down. It does not request live market data or perform execution mutations.

See [`docs/RUNTIME_VALIDATION.md`](docs/RUNTIME_VALIDATION.md) for the complete automated and manual browser validation sequence and definition of done.

## Tests

```bash
pytest -q
```

Tests cover all 15 single strategies, composite three-strategy and recent-event-quorum behavior, settings loading, SQLite runtime checkpoints, durable events, named presets and stale-session supersession.
