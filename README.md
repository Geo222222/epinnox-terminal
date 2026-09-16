# Epinnox Terminal

TradingView-style strategy research and execution terminal for Epinnox.

This first milestone reproduces the Pine Script experience we built together in Python:

- HTX USDT-margined futures market data via CCXT
- 15 selectable strategies
- automatic 1m / 5m / 15m / 30m presets
- fill-aware, fee-aware break-even and profit exits
- pyramiding
- sequential candle replay backtesting
- fees, referral economics, MAE/MFE, drawdown, liquidation approximation, bars/time held
- TradingView-like candlestick chart, volume, strategy overlays, indicator pane, entry/exit markers
- strategy tester metrics and trade ledger
- BACKTEST / PAPER / LIVE mode shell with an adapter boundary for `epinnox-online`

## Run locally

```bash
cd epinnox-terminal
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

Open <http://localhost:8010>.

The default experiment is ETH/USDT:USDT, 1m, Supertrend, 5% of leveraged capacity per entry.

## Example $50 / 200x sizing

The terminal uses the policy discussed during the Pine experiment:

```text
account equity      = $50
leverage            = 200x
effective capacity  = $10,000
allocation per layer= 5%
notional per entry  = $500
margin per entry    = $2.50
```

Pyramiding adds another layer only on a new qualifying signal, up to the configured maximum.

## Important parity rule

The Python engine intentionally replays candles sequentially. Entry signals are evaluated at a completed candle and market entries fill at that candle close, matching the Pine experiment's `process_orders_on_close=true` intent. Profit targets are eligible from the next candle onward, so the engine never uses price movement that happened earlier in the entry candle to manufacture a fill.

## epinnox-online integration boundary

`epinnox-online` remains the execution authority. It already owns HTX account routing, encrypted credentials, paper fills, live order submission, positions, liquidation fields, and market bootstrap semantics. The terminal does **not** duplicate stored exchange secrets.

Set:

```bash
EPINNOX_ONLINE_BASE_URL=http://localhost:8000
```

to expose the configured execution target in `/api/execution/status`. PAPER/LIVE automated routing is intentionally not armed in this first commit; backtesting is complete and isolated. The next integration milestone should authenticate through the existing Epinnox session boundary and route `OrderIntent` objects to the existing `/api/orders` and `/api/positions` APIs.

## Tests

```bash
pytest -q
```

## Repository lifecycle

Current implementation branch: `feature/pinescript-terminal-v1`
