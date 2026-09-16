# Scanner V2 — Holdout-First Qualification

Scanner V2 upgrades Opportunity Scanner from an in-sample ranking tool into a chronological validation engine.

## Validation topology

For each symbol × timeframe × strategy:

1. Build the causal strategy model once over the full history.
2. Reserve the newest configured fraction of history as an untouched chronological holdout (default 25%).
3. Run walk-forward validation only on the earlier calibration segment.
4. Sweep each target/economic configuration through the same prepared strategy signals.
5. Re-run each target on the holdout with entries disabled before the holdout boundary, while preserving indicator state from the preceding calibration history.
6. Qualify only when full-sample, walk-forward and holdout rules all pass.

Default holdout rules:

- holdout fraction: 25%
- minimum holdout trades: 5
- minimum holdout net expectancy: $0

## Qualification evidence

Each candidate now carries:

- full-history economics and risk;
- calibration walk-forward windows and pass rate;
- holdout trade count, net P&L, return, expectancy, PF, win rate, drawdown, target-hit rate, trades/day and referral/day;
- deterministic robustness score;
- explicit rejection reasons;
- parity semantics version used to generate its signals.

Rejected reasons can include `holdout_sample`, `holdout_expectancy`, and `holdout_trader_net_negative` in addition to the existing sample, expectancy, drawdown and walk-forward gates.

## Ranking

Capital Growth ranks qualified candidates by:

1. robustness score;
2. holdout return;
3. holdout profit factor;
4. walk-forward stability;
5. lower full-sample drawdown;
6. full-sample return.

Break-Even Throughput ranks qualified candidates by:

1. holdout trades/day;
2. robustness score;
3. holdout referral/day;
4. lower drawdown;
5. holdout expectancy.

Referral economics never override a negative holdout trader edge.

## Performance model

Target sweeps no longer rebuild indicators for every target and validation window. Scanner builds one causal strategy model per symbol × timeframe × strategy, slices that prepared model for walk-forward windows, and reuses it across economic simulations.

The response exposes `engine_stats` with strategy models built, simulations run, and strategy builds avoided so scanner cost is auditable.

## Limits

Scanner V2 still uses deterministic OHLC replay. It is not a tick simulator, and a qualified candidate is research evidence rather than a guarantee of future profitability.
