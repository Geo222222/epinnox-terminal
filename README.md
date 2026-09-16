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

The default backtest remains ETH/USDT:USDT, 1m, Supertrend, 5% of leveraged capacity per entry.

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

Stopping the terminal paper runner does **not** forcibly close an existing paper position.

Because the paper runner uses the paper-state endpoint as a fail-closed gate, switching `epinnox-online` away from a paper profile prevents subsequent mutations rather than silently routing the strategy into a live account.

## LIVE mode

LIVE is intentionally not armed here. `epinnox-online` already owns credentials, venue mutation safety, confirmations, position reconciliation and HTX execution. A separate qualification milestone should wire autonomous live strategy intents through those existing controls rather than bypassing them.

## Tests

```bash
pytest -q
```

Tests cover all 15 single strategies plus composite three-strategy and recent-event-quorum behavior.
