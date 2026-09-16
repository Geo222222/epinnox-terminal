from __future__ import annotations

import math
import time
import uuid
from statistics import mean
from typing import Any

import numpy as np
import pandas as pd

from . import indicators as I
from .backtest import Backtester
from .market import fetch_ohlcv_range
from .models import BacktestRequest, ScannerRequest
from .presets import STRATEGIES
from .strategies import build_entry_model


def fee_floor_pct(entry_fee_pct: float, exit_fee_pct: float, extra_cost_pct: float) -> dict[str, float]:
    entry_r = entry_fee_pct / 100.0
    exit_r = exit_fee_pct / 100.0
    extra_r = extra_cost_pct / 100.0
    long_ratio = (1 + entry_r + extra_r) / max(1e-12, 1 - exit_r)
    short_ratio = (1 - entry_r - extra_r) / (1 + exit_r)
    return {
        "long_pct": (long_ratio - 1.0) * 100.0,
        "short_pct": (1.0 - short_ratio) * 100.0,
    }


def _request(req: ScannerRequest, symbol: str, timeframe: str, strategy: str, target_buffer_pct: float) -> BacktestRequest:
    return BacktestRequest(
        symbol=symbol,
        timeframe=timeframe,
        strategy=strategy,
        confirmation_policy="Single",
        limit=req.history_bars,
        backtest_profile=req.backtest_profile,
        starting_balance=req.starting_balance,
        leverage=req.leverage,
        allocation_pct=req.allocation_pct,
        pyramiding=req.pyramiding,
        direction=req.direction,
        entry_fee_pct=req.entry_fee_pct,
        exit_fee_pct=req.exit_fee_pct,
        extra_cost_pct=req.extra_cost_pct,
        desired_net_profit_pct=target_buffer_pct,
        referral_share_pct=req.referral_share_pct,
        maintenance_margin_pct=req.maintenance_margin_pct,
        max_bars_in_trade=req.max_bars_in_trade,
        stop_loss_pct=req.stop_loss_pct,
        funding_bps_per_8h=0.0,
    )


def _days_between(start_ts_ms: int, end_ts_ms: int) -> float:
    if end_ts_ms <= start_ts_ms:
        return 1.0 / 24.0
    return max(1.0 / 24.0, (end_ts_ms - start_ts_ms) / 86_400_000.0)


def _recent_history(symbol: str, timeframe: str, bars: int) -> list[dict]:
    tf_ms = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000}[timeframe]
    end = int(time.time() * 1000)
    # Give the range pager room for the forming bar and sparse/missing candles.
    start = end - (bars + 50) * tf_ms
    candles = fetch_ohlcv_range(symbol, timeframe, start, end, max_bars=bars + 100)
    return candles[-bars:]


def _slice_series(series: pd.Series, end: int) -> pd.Series:
    return series.iloc[:end].reset_index(drop=True)


def _slice_part(part: dict[str, Any], end: int) -> dict[str, Any]:
    out = dict(part)
    for key in ("long", "short", "state_long", "state_short"):
        out[key] = _slice_series(part[key], end)
    out["overlays"] = {k: _slice_series(v, end) for k, v in part.get("overlays", {}).items()}
    out["panes"] = {k: _slice_series(v, end) for k, v in part.get("panes", {}).items()}
    return out


def _slice_logic(logic: dict[str, Any], end: int) -> dict[str, Any]:
    out = dict(logic)
    out["long"] = _slice_series(logic["long"], end)
    out["short"] = _slice_series(logic["short"], end)
    out["overlays"] = {k: _slice_series(v, end) for k, v in logic.get("overlays", {}).items()}
    out["panes"] = {k: _slice_series(v, end) for k, v in logic.get("panes", {}).items()}
    out["parts"] = {name: _slice_part(part, end) for name, part in logic.get("parts", {}).items()}
    return out


class _PreparedBacktester(Backtester):
    """Backtester initialized from a precomputed causal strategy model.

    Scanner target sweeps change economics, not entry signals. Reusing one
    strategy model per symbol/timeframe/strategy prevents every target and
    validation window from recalculating the same indicators.
    """

    def __init__(
        self,
        candles: list[dict],
        req: BacktestRequest,
        logic: dict[str, Any],
        trade_start_ts_ms: int | None = None,
    ) -> None:
        self.df = pd.DataFrame(candles).reset_index(drop=True)
        self.req = req
        self.logic = logic
        self.ts = self.df["ts_ms"].to_numpy(dtype=np.int64, copy=False)
        self.high = self.df["high"].to_numpy(dtype=np.float64, copy=False)
        self.low = self.df["low"].to_numpy(dtype=np.float64, copy=False)
        self.close = self.df["close"].to_numpy(dtype=np.float64, copy=False)
        self.long_signal = logic["long"].to_numpy(dtype=bool, copy=True)
        self.short_signal = logic["short"].to_numpy(dtype=bool, copy=True)
        if trade_start_ts_ms is not None:
            pre_validation = self.ts < int(trade_start_ts_ms)
            self.long_signal[pre_validation] = False
            self.short_signal[pre_validation] = False
        self.cash = req.starting_balance
        self.equity_peak = req.starting_balance
        self.max_drawdown = 0.0
        self.position = None
        self.closed: list[dict] = []
        self.markers: list[dict] = []
        self.equity_curve: list[dict] = []
        self.open_snapshot: dict | None = None


def _run_prepared(
    candles: list[dict],
    req: BacktestRequest,
    logic: dict[str, Any],
    *,
    trade_start_ts_ms: int | None = None,
    stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    if stats is not None:
        stats["simulations_run"] = stats.get("simulations_run", 0) + 1
    result = _PreparedBacktester(candles, req, logic, trade_start_ts_ms).run()
    if trade_start_ts_ms is not None and candles:
        days = _days_between(int(trade_start_ts_ms), int(candles[-1]["ts_ms"]))
        metrics = result["metrics"]
        metrics["trades_per_day"] = float(metrics["closed_trades"]) / days
        metrics["referral_revenue_per_day"] = float(metrics["referral_revenue"]) / days
        result["validation_start_ts_ms"] = int(trade_start_ts_ms)
    return result


def _metric_snapshot(result: dict[str, Any], starting_balance: float) -> dict[str, Any]:
    metrics = result["metrics"]
    trades = result["trades"]
    closed = int(metrics["closed_trades"])
    net = float(metrics["net_pnl_closed"])
    expectancy = net / closed if closed else 0.0
    return {
        "closed_trades": closed,
        "net_pnl": net,
        "net_return_pct": (net / starting_balance) * 100.0,
        "net_expectancy_usdt": expectancy,
        "profit_factor": metrics["profit_factor"],
        "win_rate_pct": float(metrics["win_rate_pct"]),
        "max_drawdown_pct": float(metrics["max_drawdown_pct"]),
        "target_hit_rate_pct": float(metrics["target_hit_rate_pct"]),
        "median_bars_to_exit": float(metrics["median_bars_to_exit"]),
        "fees_paid": float(metrics["fees_paid"]),
        "referral_revenue": float(metrics["referral_revenue"]),
        "trades_per_day": float(metrics["trades_per_day"]),
        "referral_revenue_per_day": float(metrics["referral_revenue_per_day"]),
        "liquidation_exits": int(metrics.get("liquidation_exits", 0)),
        "avg_mae_pct": mean(float(t["mae_pct"]) for t in trades) if trades else 0.0,
        "avg_mfe_pct": mean(float(t["mfe_pct"]) for t in trades) if trades else 0.0,
    }


def _walk_forward_prepared(
    candles: list[dict],
    calibration_end: int,
    bt_req: BacktestRequest,
    logic: dict[str, Any],
    windows: int,
    stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    if calibration_end < windows * 100:
        return {"windows": 0, "passed": 0, "pass_rate_pct": 0.0, "details": [], "insufficient_history": True}
    size = calibration_end // windows
    details: list[dict[str, Any]] = []
    for w in range(windows):
        start = w * size
        end = calibration_end if w == windows - 1 else (w + 1) * size
        if end - start < 100:
            continue
        context = candles[:end]
        context_logic = _slice_logic(logic, end)
        start_ts = int(candles[start]["ts_ms"])
        result = _run_prepared(context, bt_req, context_logic, trade_start_ts_ms=start_ts, stats=stats)
        metrics = _metric_snapshot(result, bt_req.starting_balance)
        passed = bool(metrics["closed_trades"] > 0 and metrics["net_expectancy_usdt"] >= 0.0)
        details.append({
            "window": w + 1,
            "start_ts_ms": start_ts,
            "end_ts_ms": int(candles[end - 1]["ts_ms"]),
            "closed_trades": metrics["closed_trades"],
            "net_pnl": metrics["net_pnl"],
            "net_expectancy_usdt": metrics["net_expectancy_usdt"],
            "max_drawdown_pct": metrics["max_drawdown_pct"],
            "passed": passed,
        })
    passed_count = sum(1 for x in details if x["passed"])
    rate = 100.0 * passed_count / len(details) if details else 0.0
    worst = min((float(x["net_pnl"]) for x in details), default=0.0)
    return {
        "windows": len(details),
        "passed": passed_count,
        "pass_rate_pct": rate,
        "worst_window_net_pnl": worst,
        "details": details,
        "insufficient_history": False,
    }


def _robustness_score(req: ScannerRequest, full: dict[str, Any], holdout: dict[str, Any], wf: dict[str, Any]) -> float:
    wf_score = max(0.0, min(1.0, float(wf["pass_rate_pct"]) / 100.0))
    sample_score = max(0.0, min(1.0, holdout["closed_trades"] / max(1.0, req.min_holdout_trades * 2.0)))
    dd_score = max(0.0, min(1.0, 1.0 - full["max_drawdown_pct"] / max(req.max_drawdown_pct, 1e-9)))
    pf = holdout["profit_factor"]
    if pf is None:
        pf_score = 1.0 if holdout["net_pnl"] > 0 else 0.0
    else:
        pf_score = max(0.0, min(1.0, float(pf) / 2.0))
    hit_score = max(0.0, min(1.0, holdout["target_hit_rate_pct"] / 100.0))
    return round(100.0 * (0.30 * wf_score + 0.20 * sample_score + 0.20 * dd_score + 0.20 * pf_score + 0.10 * hit_score), 2)


def _candidate_prepared(
    req: ScannerRequest,
    candles: list[dict],
    symbol: str,
    timeframe: str,
    strategy: str,
    target_buffer_pct: float,
    logic: dict[str, Any],
    calibration_end: int,
    stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    bt_req = _request(req, symbol, timeframe, strategy, target_buffer_pct)
    full_result = _run_prepared(candles, bt_req, logic, stats=stats)
    full = _metric_snapshot(full_result, req.starting_balance)

    holdout_start_ts = int(candles[calibration_end]["ts_ms"])
    holdout_result = _run_prepared(candles, bt_req, logic, trade_start_ts_ms=holdout_start_ts, stats=stats)
    holdout = _metric_snapshot(holdout_result, req.starting_balance)
    holdout.update({
        "start_ts_ms": holdout_start_ts,
        "end_ts_ms": int(candles[-1]["ts_ms"]),
        "bars": len(candles) - calibration_end,
    })

    wf = _walk_forward_prepared(candles, calibration_end, bt_req, logic, req.walk_forward_windows, stats)
    rejects: list[str] = []
    if full["closed_trades"] < req.min_sample_trades:
        rejects.append("insufficient_sample")
    if full["net_expectancy_usdt"] < req.min_net_expectancy_usdt:
        rejects.append("negative_expectancy")
    if full["max_drawdown_pct"] > req.max_drawdown_pct:
        rejects.append("drawdown")
    if wf["pass_rate_pct"] < req.min_walk_forward_pass_rate_pct:
        rejects.append("walk_forward")
    if holdout["closed_trades"] < req.min_holdout_trades:
        rejects.append("holdout_sample")
    if holdout["net_expectancy_usdt"] < req.min_holdout_expectancy_usdt:
        rejects.append("holdout_expectancy")
    if req.objective == "Break-Even Throughput" and holdout["net_pnl"] < 0:
        rejects.append("holdout_trader_net_negative")

    floors = fee_floor_pct(req.entry_fee_pct, req.exit_fee_pct, req.extra_cost_pct)
    robustness = _robustness_score(req, full, holdout, wf)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": strategy,
        "target_buffer_pct": target_buffer_pct,
        "fee_floor_long_pct": floors["long_pct"],
        "fee_floor_short_pct": floors["short_pct"],
        "qualified": not rejects,
        "reject_reasons": rejects,
        "robustness_score": robustness,
        "closed_trades": full["closed_trades"],
        "trades_per_day": full["trades_per_day"],
        "net_pnl": full["net_pnl"],
        "net_return_pct": full["net_return_pct"],
        "net_expectancy_usdt": full["net_expectancy_usdt"],
        "profit_factor": full["profit_factor"],
        "win_rate_pct": full["win_rate_pct"],
        "max_drawdown_pct": full["max_drawdown_pct"],
        "target_hit_rate_pct": full["target_hit_rate_pct"],
        "median_bars_to_exit": full["median_bars_to_exit"],
        "fees_paid": full["fees_paid"],
        "fees_per_day": full["fees_paid"] / _days_between(int(candles[0]["ts_ms"]), int(candles[-1]["ts_ms"])),
        "referral_revenue": full["referral_revenue"],
        "referral_revenue_per_day": full["referral_revenue_per_day"],
        "avg_mae_pct": full["avg_mae_pct"],
        "avg_mfe_pct": full["avg_mfe_pct"],
        "liquidation_exits": full["liquidation_exits"],
        "walk_forward": wf,
        "holdout": holdout,
        "validation": {
            "calibration_bars": calibration_end,
            "holdout_bars": len(candles) - calibration_end,
            "holdout_fraction": req.holdout_fraction,
            "selection_policy": "walk-forward calibration + untouched chronological holdout",
        },
        "load_payload": bt_req.model_dump(),
    }


def _candidate(req: ScannerRequest, candles: list[dict], symbol: str, timeframe: str, strategy: str, target_buffer_pct: float) -> dict[str, Any]:
    """Compatibility entry point used by focused tests and single-candidate research."""
    df = pd.DataFrame(candles).reset_index(drop=True)
    logic = build_entry_model(df, strategy, timeframe)
    calibration_end = max(1, min(len(candles) - 1, int(len(candles) * (1.0 - req.holdout_fraction))))
    return _candidate_prepared(req, candles, symbol, timeframe, strategy, target_buffer_pct, logic, calibration_end)


def _sort_key(objective: str, row: dict[str, Any]) -> tuple:
    qualified = 1 if row["qualified"] else 0
    holdout = row["holdout"]
    pf = holdout["profit_factor"]
    pf_value = float(pf) if pf is not None and math.isfinite(float(pf)) else 3.0 if holdout["net_pnl"] > 0 else 0.0
    if objective == "Break-Even Throughput":
        return (
            qualified,
            holdout["trades_per_day"],
            row["robustness_score"],
            holdout["referral_revenue_per_day"],
            -row["max_drawdown_pct"],
            holdout["net_expectancy_usdt"],
        )
    return (
        qualified,
        row["robustness_score"],
        holdout["net_return_pct"],
        pf_value,
        row["walk_forward"]["pass_rate_pct"],
        -row["max_drawdown_pct"],
        row["net_return_pct"],
    )


def run_scanner(req: ScannerRequest) -> dict[str, Any]:
    unknown = [s for s in req.strategies if s not in STRATEGIES]
    if unknown:
        raise ValueError(f"Unknown scanner strategies: {unknown}")
    started = int(time.time() * 1000)
    scan_id = str(uuid.uuid4())
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    engine_stats = {"strategy_models_built": 0, "simulations_run": 0}

    for symbol in req.symbols:
        for timeframe in req.timeframes:
            try:
                candles = _recent_history(symbol, timeframe, req.history_bars)
                if len(candles) < 600:
                    raise ValueError(f"only {len(candles)} candles returned; scanner v2 requires at least 600")
            except Exception as exc:
                errors.append({"symbol": symbol, "timeframe": timeframe, "error": str(exc)})
                continue

            calibration_end = max(1, min(len(candles) - 1, int(len(candles) * (1.0 - req.holdout_fraction))))
            df = pd.DataFrame(candles).reset_index(drop=True)
            for strategy in req.strategies:
                try:
                    logic = build_entry_model(df, strategy, timeframe)
                    engine_stats["strategy_models_built"] += 1
                except Exception as exc:
                    errors.append({"symbol": symbol, "timeframe": timeframe, "strategy": strategy, "error": str(exc)})
                    continue
                for target in req.target_buffers_pct:
                    try:
                        rows.append(
                            _candidate_prepared(
                                req,
                                candles,
                                symbol,
                                timeframe,
                                strategy,
                                target,
                                logic,
                                calibration_end,
                                engine_stats,
                            )
                        )
                    except Exception as exc:
                        errors.append({"symbol": symbol, "timeframe": timeframe, "strategy": strategy, "target": str(target), "error": str(exc)})

    rows.sort(key=lambda row: _sort_key(req.objective, row), reverse=True)
    qualified_seen = 0
    for index, row in enumerate(rows, start=1):
        row["objective_rank"] = index
        if row["qualified"]:
            qualified_seen += 1
            row["qualified_rank"] = qualified_seen
        else:
            row["qualified_rank"] = None

    qualified = [r for r in rows if r["qualified"]]
    completed = int(time.time() * 1000)
    engine_stats["strategy_builds_avoided"] = max(0, engine_stats["simulations_run"] - engine_stats["strategy_models_built"])
    return {
        "schema_version": 2,
        "scan_id": scan_id,
        "objective": req.objective,
        "started_at_ms": started,
        "completed_at_ms": completed,
        "duration_ms": completed - started,
        "request": req.model_dump(),
        "fee_floor": fee_floor_pct(req.entry_fee_pct, req.exit_fee_pct, req.extra_cost_pct),
        "parity_semantics_version": I.PARITY_SEMANTICS_VERSION,
        "validation_policy": {
            "type": "chronological_holdout_with_walk_forward_calibration",
            "holdout_fraction": req.holdout_fraction,
            "min_holdout_trades": req.min_holdout_trades,
            "min_holdout_expectancy_usdt": req.min_holdout_expectancy_usdt,
            "walk_forward_windows": req.walk_forward_windows,
            "note": "Ranking is holdout-first. Strategy indicators are built once causally per symbol/timeframe/strategy and reused across target simulations.",
        },
        "engine_stats": engine_stats,
        "summary": {
            "evaluated": len(rows),
            "qualified": len(qualified),
            "rejected": len(rows) - len(qualified),
            "market_errors": len(errors),
            "best_candidate": qualified[0] if qualified else None,
        },
        "results": rows,
        "errors": errors,
        "ranking_policy": (
            "Qualified first; then holdout trades/day, robustness, holdout referral/day, lower drawdown, holdout expectancy"
            if req.objective == "Break-Even Throughput"
            else "Qualified first; then robustness, holdout return, holdout profit factor, walk-forward stability, lower drawdown, full-sample return"
        ),
    }
