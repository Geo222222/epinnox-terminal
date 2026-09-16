from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _family(strategy: str) -> str:
    s = strategy.lower()
    if any(x in s for x in ("mean reversion", "vwap", "stochastic reversal")):
        return "MEAN REVERSION"
    if "bollinger" in s and "breakout" not in s:
        return "MEAN REVERSION"
    if any(x in s for x in ("breakout", "donchian")):
        return "BREAKOUT"
    if any(x in s for x in ("supertrend", "ema", "sma", "adx", "momentum", "macd", "price channel", "rsi momentum")):
        return "TREND / MOMENTUM"
    return "MIXED"


def _norm(value: float, values: list[float], *, invert: bool = False) -> float:
    if not values:
        return 0.5
    lo, hi = min(values), max(values)
    score = 0.5 if hi <= lo else (value - lo) / (hi - lo)
    return 1.0 - score if invert else score


def _pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or len(a) < 3:
        return None
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    da = [x - ma for x in a]
    db = [x - mb for x in b]
    den = math.sqrt(sum(x * x for x in da) * sum(x * x for x in db))
    if den <= 1e-12:
        return None
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(da, db)) / den))


def build_universe_snapshot(
    scan: dict[str, Any],
    *,
    strategy: str | None = None,
    timeframe: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Project persisted scanner evidence into a bounded symbol relationship graph.

    The graph never invents market facts. Nodes are scanner candidates. Correlation
    edges are Pearson correlations of common strategy/target expectancy response
    vectors inside the same persisted scan; they are not raw-price correlations.
    """
    results = list(scan.get("results") or [])
    strategy = (strategy or "").strip()
    timeframe = (timeframe or "").strip()
    strict = [
        r for r in results
        if (not strategy or str(r.get("strategy")) == strategy)
        and (not timeframe or str(r.get("timeframe")) == timeframe)
    ]
    working = strict or results

    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in working:
        symbol = str(row.get("symbol") or "").strip()
        if symbol:
            by_symbol[symbol].append(row)

    def row_rank(row: dict[str, Any]) -> tuple[int, float]:
        return (0 if row.get("qualified") else 1, _f(row.get("objective_rank"), 1e9))

    chosen: list[dict[str, Any]] = []
    for symbol, rows in by_symbol.items():
        chosen.append(min(rows, key=row_rank))
    chosen.sort(key=row_rank)
    chosen = chosen[: max(1, min(int(limit), 60))]

    pf_values = [_f(r.get("profit_factor")) for r in chosen]
    trade_values = [_f(r.get("trades_per_day")) for r in chosen]
    win_values = [_f(r.get("win_rate_pct")) for r in chosen]
    wf_values = [_f((r.get("walk_forward") or {}).get("pass_rate_pct")) for r in chosen]
    dd_values = [_f(r.get("max_drawdown_pct")) for r in chosen]
    target_values = [_f(r.get("target_hit_rate_pct")) for r in chosen]
    pnl_values = [_f(r.get("net_pnl")) for r in chosen]

    nodes: list[dict[str, Any]] = []
    selected_symbols = {str(r.get("symbol")) for r in chosen}
    full_rows_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        if str(r.get("symbol")) in selected_symbols and (not timeframe or str(r.get("timeframe")) == timeframe):
            full_rows_by_symbol[str(r.get("symbol"))].append(r)

    for row in chosen:
        symbol = str(row.get("symbol"))
        pf = _f(row.get("profit_factor"))
        trades = _f(row.get("trades_per_day"))
        win = _f(row.get("win_rate_pct"))
        wf = _f((row.get("walk_forward") or {}).get("pass_rate_pct"))
        dd = _f(row.get("max_drawdown_pct"))
        target = _f(row.get("target_hit_rate_pct"))
        score = 100.0 * (
            0.24 * _norm(pf, pf_values)
            + 0.18 * _norm(trades, trade_values)
            + 0.14 * _norm(win, win_values)
            + 0.24 * _norm(wf, wf_values)
            + 0.10 * _norm(dd, dd_values, invert=True)
            + 0.10 * _norm(target, target_values)
        )
        matrix: dict[str, dict[str, Any]] = {}
        for item in full_rows_by_symbol[symbol]:
            name = str(item.get("strategy") or "")
            current = matrix.get(name)
            if current is None or row_rank(item) < row_rank(current):
                matrix[name] = item
        top_strategies = sorted(matrix.values(), key=row_rank)[:6]
        nodes.append({
            "id": symbol,
            "label": symbol.split("/", 1)[0],
            "qualified": bool(row.get("qualified")),
            "cluster": _family(str(row.get("strategy") or "")),
            "opportunity_score": round(score, 2),
            "strategy": row.get("strategy"),
            "timeframe": row.get("timeframe"),
            "target_buffer_pct": row.get("target_buffer_pct"),
            "metrics": {
                "profit_factor": row.get("profit_factor"),
                "net_pnl": row.get("net_pnl"),
                "net_expectancy_usdt": row.get("net_expectancy_usdt"),
                "trades_per_day": row.get("trades_per_day"),
                "win_rate_pct": row.get("win_rate_pct"),
                "max_drawdown_pct": row.get("max_drawdown_pct"),
                "target_hit_rate_pct": row.get("target_hit_rate_pct"),
                "walk_forward_pass_rate_pct": (row.get("walk_forward") or {}).get("pass_rate_pct"),
                "median_bars_to_exit": row.get("median_bars_to_exit"),
                "fees_per_day": row.get("fees_per_day"),
                "referral_revenue_per_day": row.get("referral_revenue_per_day"),
            },
            "load_payload": row.get("load_payload"),
            "strategies": [{
                "strategy": x.get("strategy"),
                "qualified": bool(x.get("qualified")),
                "profit_factor": x.get("profit_factor"),
                "net_pnl": x.get("net_pnl"),
                "trades_per_day": x.get("trades_per_day"),
                "walk_forward_pass_rate_pct": (x.get("walk_forward") or {}).get("pass_rate_pct"),
            } for x in top_strategies],
        })

    # A symbol's response vector is its expectancy across common strategy/timeframe/target points.
    response_vectors: dict[str, dict[tuple[str, str, float], float]] = defaultdict(dict)
    for r in results:
        symbol = str(r.get("symbol") or "")
        if symbol not in selected_symbols:
            continue
        key = (str(r.get("strategy") or ""), str(r.get("timeframe") or ""), round(_f(r.get("target_buffer_pct")), 8))
        response_vectors[symbol][key] = _f(r.get("net_expectancy_usdt"))

    node_map = {n["id"]: n for n in nodes}
    edges: list[dict[str, Any]] = []
    symbols = list(node_map)
    for i, left in enumerate(symbols):
        for right in symbols[i + 1:]:
            common = sorted(set(response_vectors[left]) & set(response_vectors[right]))
            corr = _pearson([response_vectors[left][k] for k in common], [response_vectors[right][k] for k in common])
            lm, rm = node_map[left]["metrics"], node_map[right]["metrics"]
            components = []
            for key, scale in (("profit_factor", 2.0), ("win_rate_pct", 100.0), ("walk_forward_pass_rate_pct", 100.0), ("max_drawdown_pct", 10.0), ("trades_per_day", max(max(trade_values or [1.0]), 1.0))):
                components.append(min(abs(_f(lm.get(key)) - _f(rm.get(key))) / scale, 1.0))
            similarity = max(0.0, 1.0 - sum(components) / len(components))
            if corr is not None and corr >= 0.65:
                edges.append({"id": f"{left}|{right}|corr", "source": left, "target": right, "type": "response_correlation", "weight": round(corr, 4), "label": round(corr, 2), "sample_points": len(common)})
            elif corr is not None and corr <= -0.45:
                edges.append({"id": f"{left}|{right}|div", "source": left, "target": right, "type": "diverging", "weight": round(abs(corr), 4), "label": round(corr, 2), "sample_points": len(common)})
            elif similarity >= 0.78:
                edges.append({"id": f"{left}|{right}|sim", "source": left, "target": right, "type": "strategy_similarity", "weight": round(similarity, 4), "label": round(similarity, 2), "sample_points": len(common)})

    edges.sort(key=lambda e: e["weight"], reverse=True)
    # Bound visual density: enough structure to read without turning into a hairball.
    edges = edges[: max(12, min(len(nodes) * 3, 90))]
    nodes.sort(key=lambda x: (not x["qualified"], -x["opportunity_score"]))
    best = nodes[0] if nodes else None
    return {
        "schema_version": 1,
        "source": "opportunity_scanner",
        "scan_id": scan.get("scan_id"),
        "objective": scan.get("objective"),
        "completed_at_ms": scan.get("completed_at_ms"),
        "requested_strategy": strategy or None,
        "requested_timeframe": timeframe or None,
        "filter_matched": bool(strict),
        "score_note": "Opportunity score is a visual ranking heuristic over scanner evidence, not a trading authorization.",
        "edge_note": "Correlation edges compare scanner expectancy response vectors, not raw market-price returns.",
        "nodes": nodes,
        "edges": edges,
        "clusters": sorted({n["cluster"] for n in nodes}),
        "summary": {
            "symbols": len(nodes),
            "edges": len(edges),
            "qualified": sum(1 for n in nodes if n["qualified"]),
            "strategies_analyzed": len({str(r.get("strategy")) for r in results}),
            "timeframes_analyzed": len({str(r.get("timeframe")) for r in results}),
            "best": best,
        },
    }
