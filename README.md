# Epinnox Terminal

TradingView-style strategy research and execution terminal for Epinnox.

Key workstation capabilities:

- HTX USDT-margined futures market data via CCXT
- 15 selectable strategy signal generators and composite confirmation models
- automatic backtest recalculation with Pine/TradingView parity controls
- 1m, 5m, 15m, 30m, 1h, 2h, 3h, 4h, 5h, 8h, D, 5D, W and M chart intervals
- fee-aware break-even/profit exits, pyramiding, MAE/MFE, drawdown and liquidation audit
- deterministic opportunity/throughput scanner
- authenticated `epinnox-online` PAPER/LIVE account selection
- fail-closed PAPER runner bound to the selected paper account
- TradingView-style persistent chart drawing toolkit using timestamp/price coordinates
- durable browser workspaces, named presets and SQLite paper-runtime recovery
- LIVE account context is selectable, while live order routing remains deliberately unarmed

## Run locally

Run `epinnox-online` first if you want PAPER account routing, then start Terminal:

```bash
cd epinnox-terminal
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
$env:EPINNOX_ONLINE_BASE_URL="http://localhost:8000"  # PowerShell
uvicorn app.main:app --reload --port 8010
```

Open <http://localhost:8010>.

## Execution account context

BACKTEST remains synthetic. PAPER and LIVE derive account identity from the authenticated `epinnox-online` session and never store exchange credentials in Terminal.

PAPER account selection activates the chosen upstream paper account before the strategy can start. The runner persists that account id with its durable checkpoint and verifies before each evaluation/mutation that the same account is still active and still a paper account. If the upstream context changes, execution fails closed instead of silently trading another profile.

LIVE account selection uses the same account context UX, but real order routing remains intentionally unarmed until a separate live qualification milestone.

## Chart drawings

The chart left rail contains cursor/select, trend, horizontal, vertical, channel, path, Fibonacci, text, ruler, zoom, magnet/snap, keep-drawing, lock, hide, undo/redo and delete controls. Drawings persist per symbol in browser storage as market coordinates (`timestamp`, `price`) and are reprojected through Lightweight Charts as the viewport changes.

## Composite entries

The Primary strategy is the timing source. Up to two confirmations can be selected in the UI. Policies include `Single`, `Primary + All States`, `All Recent Events`, and `Quorum Recent Events`.

## PAPER recovery

Paper sessions checkpoint strategy settings, last candle, position state, pending intent, event history and the bound account id. Recovery reconciles with `epinnox-online`; if the account binding cannot be proven, recovery enters `RECOVERY_REQUIRED` and remains fail-closed.

## Tests

```bash
pytest -q
```

CI also validates frontend JavaScript syntax and the workstation/account-context contract.
