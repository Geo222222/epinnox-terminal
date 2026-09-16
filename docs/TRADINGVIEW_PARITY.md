# TradingView Parity Contract

Epinnox Terminal treats TradingView parity as an evidence problem, not a label.

## Pine semantics implemented

Parity semantics version: `pine-v2-rma-supertrend`.

The Python indicator layer now follows the Pine/TradingView recurrence rules that materially affect strategy signals:

- EMA is recursively seeded from the first non-`na` observation.
- Wilder RMA is seeded with an SMA of the first `length` observations, then uses `alpha = 1 / length`.
- RSI uses Wilder RMA for gains/losses and preserves its warm-up `na` region.
- ATR is RMA of true range.
- DMI/ADX uses Wilder RMA rather than pandas' default EWM seed behavior.
- Bollinger standard deviation uses the population/biased estimator (`ddof=0`).
- Supertrend follows TradingView's direction convention: `-1` bullish/uptrend, `+1` bearish/downtrend.
- Strategy crossovers are evaluated on completed bars.

Regression tests lock these primitive behaviors with deterministic vectors.

## Simulator contract

`TradingView Parity` means:

- signal is evaluated on the completed candle;
- a market entry is filled at that candle close, matching the intended `process_orders_on_close=true` experiment;
- exits are eligible on later candles, so pre-entry movement cannot create a historical fill;
- when a later OHLC candle touches more than one boundary and intrabar path is unknown, the simulator uses conservative precedence;
- Terminal's custom liquidation estimate and synthetic funding are disabled in parity mode.

## What is not yet certified

`TradingView Parity` is **Pine-formula conformant**, but it is not yet described as export-certified TradingView equivalence.

The final certification gate is a fixture suite exported from TradingView/Pine for representative symbols, timeframes and strategies. That suite must compare, bar-for-bar and trade-for-trade:

1. indicator values after warm-up;
2. long/short signal timestamps;
3. entry timestamps and prices;
4. exit timestamps, reasons and prices;
5. closed-trade counts and net P&L under identical fee assumptions.

Until those fixtures pass, Epinnox should report `pine-v2-rma-supertrend` as its semantics version and avoid claiming tick-exact TradingView equivalence.

## Tiny-target limitation

OHLC candles do not reveal intrabar path. Very small profit targets can therefore differ from TradingView when TradingView has lower-timeframe/tick information or different broker-emulator assumptions. Lower-timeframe replay remains the next fidelity layer after export-fixture certification.
