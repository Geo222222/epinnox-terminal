# OTS-01 — Opportunity & Throughput Scanner

OTS-01 is the deterministic research layer that searches current `symbol × timeframe × strategy × target-buffer` combinations before any adaptive/ML target selector is introduced.

## Objectives

### Capital Growth

Qualification happens first. Qualified rows are then ordered deterministically by net return, profit factor, walk-forward stability, lower drawdown, and trade throughput. This is a transparent ordering policy rather than a learned score.

### Break-Even Throughput

Qualification requires non-negative modeled trader economics. Qualified rows are ordered by trades/day, eligible referral revenue/day, walk-forward stability, lower drawdown, and per-trade expectancy. Referral economics never override a negative trader result.

## Fee floor and target sweep

`target_buffer_pct = 0` means the backtester uses its exact fee-aware break-even target. Positive values add desired trader profit above that floor. OTS-01 reports the long and short fee-floor movement separately and sweeps configurable profit buffers above it.

The scanner records, per candidate:

- closed trades and trades/day
- net P&L, net return, and per-trade expectancy
- profit factor and win rate
- maximum drawdown
- target-hit rate and median bars-to-exit
- fee volume and referral revenue per day
- average MAE/MFE
- liquidation exits when a liquidation-enabled profile is used
- sequential walk-forward pass rate

## Walk-forward qualification

OTS-01 divides the fetched recent history into sequential non-overlapping validation windows. A window passes when it produces at least one closed trade and non-negative modeled net P&L. The minimum pass rate is configurable.

This deliberately simple validation contract establishes an auditable baseline. OTS-02 can later add expanding/rolling training windows, regime features, and adaptive target selection without changing the OTS-01 evidence ledger.

## Persistence

Every completed scan is stored in the existing local SQLite runtime database. Recent experiments can be reopened from the Scanner workspace. Loading a candidate writes its exact backtest configuration into the persisted Terminal workspace and returns to the chart.

## Safety boundary

OTS-01 is research-only. It does not submit orders, arm PAPER, or enable LIVE execution. PAPER and LIVE continue to use their existing execution boundaries.
