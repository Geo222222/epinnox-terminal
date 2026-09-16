from __future__ import annotations

import math
import time
import uuid
from statistics import mean
from typing import Any

from .backtest import run_backtest
from .market import fetch_ohlcv_range
from .models import BacktestRequest, ScannerRequest
from .presets import STRATEGIES


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


def _days(candles: list[dict]) -> float:
    if len(candles) < 2:
        return 1.0
    return max(1.0 / 24.0, (candles[-1]["ts_ms"] - candles[0]["ts_ms"]) / 86_400_000.0)


def _recent_history(symbol: str, timeframe: str, bars: int) -> list[dict]:
    tf_ms = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000}[timeframe]
    end = int(time.time() * 1000)
    # Give the range pager some room for the currently forming bar and sparse/missing bars.
    start = end - (bars + 50) * tf_ms
    candles = fetch_ohlcv_range(symbol, timeframe, start, end, max_bars=bars + 100)
    return candles[-bars:]


def _walk_forward(candles: list[dict], bt_req: BacktestRequest, windows: int) -> dict[str, Any]:
    # Sequential, non-overlapping validation windows. OTS-01 intentionally keeps
    # this deterministic; OTS-02 can add adaptive train/validation models later.
    if len(candles) < windows * 100:
        return {"windows": 0, "passed": 0, "pass_rate_pct": 0.0, "details": [], "insufficient_history": True}
    size = len(candles) // windows
    details: list[dict[str, Any]] = []
    for w in range(windows):
        start = w * size
        end = len(candles) if w == windows - 1 else (w + 1) * size
        chunk = candles[start:end]
        if len(chunk) < 100:
            continue
        result = run_backtest(chunk, bt_req)
        metrics = result["metrics"]
        closed = int(metrics["closed_trades"])
        net = float(metrics["net_pnl_closed"])
        details.append({
            "window": w + 1,
            "start_ts_ms": int(chunk[0]["ts_ms"]),
            "end_ts_ms": int(chunk[-1]["ts_ms"]),
            "closed_trades": closed,
            "net_pnl": net,
            "max_drawdown_pct": float(metrics["max_drawdown_pct"]),
            "passed": bool(closed > 0 and net >= 0.0),
        })
    passed = sum(1 for x in details if x["passed"])
    rate = 100.0 * passed / len(details) if details else 0.0
    return {"windows": len(details), "passed": passed, "pass_rate_pct": rate, "details": details, "insufficient_history": False}


def _candidate(req: ScannerRequest, candles: list[dict], symbol: str, timeframe: str, strategy: str, target_buffer_pct: float) -> dict[str, Any]:
    bt_req = _request(req, symbol, timeframe, strategy, target_buffer_pct)
    result = run_backtest(candles, bt_req)
    metrics = result["metrics"]
    trades = result["trades"]
    closed = int(metrics["closed_trades"])
    net = float(metrics["net_pnl_closed"])
    days = _days(candles)
    expectancy = net / closed if closed else 0.0
    net_return_pct = (net / req.starting_balance) * 100.0
    fees_per_day = float(metrics["fees_paid"]) / days
    referral_per_day = float(metrics["referral_revenue"]) / days
    mae = mean(float(t["mae_pct"]) for t in trades) if trades else 0.0
    mfe = mean(float(t["mfe_pct"]) for t in trades) if trades else 0.0
    wf = _walk_forward(candles, bt_req, req.walk_forward_windows)
    rejects: list[str] = []
    if closed < req.min_sample_trades:
        rejects.append("insufficient_sample")
    if expectancy < req.min_net_expectancy_usdt:
        rejects.append("negative_expectancy")
    if float(metrics["max_drawdown_pct"]) > req.max_drawdown_pct:
        rejects.append("drawdown")
    if wf["pass_rate_pct"] < req.min_walk_forward_pass_rate_pct:
        rejects.append("walk_forward")
    if req.objective == "Break-Even Throughput" and net < 0:
        rejects.append("trader_net_negative")
    floors = fee_floor_pct(req.entry_fee_pct, req.exit_fee_pct, req.extra_cost_pct)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": strategy,
        "target_buffer_pct": target_buffer_pct,
        "fee_floor_long_pct": floors["long_pct"],
        "fee_floor_short_pct": floors["short_pct"],
        "qualified": not rejects,
        "reject_reasons": rejects,
        "closed_trades": closed,
        "trades_per_day": float(metrics["trades_per_day"]),
        "net_pnl": net,
        "net_return_pct": net_return_pct,
        "net_expectancy_usdt": expectancy,
        "profit_factor": metrics["profit_factor"],
        "win_rate_pct": float(metrics["win_rate_pct"]),
        "max_drawdown_pct": float(metrics["max_drawdown_pct"]),
        "target_hit_rate_pct": float(metrics["target_hit_rate_pct"]),
        "median_bars_to_exit": float(metrics["median_bars_to_exit"]),
        "fees_paid": float(metrics["fees_paid"]),
        "fees_per_day": fees_per_day,
        "referral_revenue": float(metrics["referral_revenue"]),
        "referral_revenue_per_day": referral_per_day,
        "avg_mae_pct": mae,
        "avg_mfe_pct": mfe,
        "liquidation_exits": int(metrics.get("liquidation_exits", 0)),
        "walk_forward": wf,
        "load_payload": bt_req.model_dump(),
    }


def _sort_key(objective: str, row: dict[str, Any]) -> tuple:
    qualified = 1 if row["qualified"] else 0
    pf = row["profit_factor"]
    pf_value = float(pf) if pf is not None and math.isfinite(float(pf)) else 999.0 if row["net_pnl"] > 0 else 0.0
    stability = float(row["walk_forward"]["pass_rate_pct"])
    if objective == "Break-Even Throughput":
        return (qualified, row["trades_per_day"], row["referral_revenue_per_day"], stability, -row["max_drawdown_pct"], row["net_expectancy_usdt"])
    return (qualified, row["net_return_pct"], pf_value, stability, -row["max_drawdown_pct"], row["trades_per_day"])


def run_scanner(req: ScannerRequest) -> dict[str, Any]:
    unknown = [s for s in req.strategies if s not in STRATEGIES]
    if unknown:
        raise ValueError(f"Unknown scanner strategies: {unknown}")
    started = int(time.time() * 1000)
    scan_id = str(uuid.uuid4())
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for symbol in req.symbols:
        for timeframe in req.timeframes:
            try:
                candles = _recent_history(symbol, timeframe, req.history_bars)
                if len(candles) < 100:
                    raise ValueError(f"only {len(candles)} candles returned")
            except Exception as exc:
                errors.append({"symbol": symbol, "timeframe": timeframe, "error": str(exc)})
                continue
            for strategy in req.strategies:
                for target in req.target_buffers_pct:
                    try:
                        rows.append(_candidate(req, candles, symbol, timeframe, strategy, target))
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
    return {
        "schema_version": 1,
        "scan_id": scan_id,
        "objective": req.objective,
        "started_at_ms": started,
        "completed_at_ms": completed,
        "duration_ms": completed - started,
        "request": req.model_dump(),
        "fee_floor": fee_floor_pct(req.entry_fee_pct, req.exit_fee_pct, req.extra_cost_pct),
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
            "Qualified first; then trades/day, referral/day, walk-forward stability, lower drawdown, expectancy"
            if req.objective == "Break-Even Throughput"
            else "Qualified first; then net return, profit factor, walk-forward stability, lower drawdown, trades/day"
        ),
    }
