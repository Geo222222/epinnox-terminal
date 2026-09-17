import numpy as np
import pandas as pd

from app.backtest import Backtester
from app.models import BacktestRequest


def make_candles(count=5):
    base = 1_700_000_000_000
    rows = []
    for i in range(count):
        close = 100.0 + i
        rows.append(
            {
                "ts_ms": base + i * 60_000,
                "open": close,
                "high": close + 0.1,
                "low": close - 0.1,
                "close": close,
                "volume": 100.0,
            }
        )
    return rows


def build_tester(candles, **overrides):
    values = {
        "strategy": "Supertrend",
        "timeframe": "1m",
        "starting_balance": 10_000,
        "leverage": 1,
        "allocation_pct": 5,
        "entry_fee_pct": 0,
        "exit_fee_pct": 0,
        "extra_cost_pct": 0,
        "desired_net_profit_pct": 20,
        "pyramiding": 1,
    }
    values.update(overrides)
    return Backtester(pd.DataFrame(candles), BacktestRequest(**values))


def test_target_exit_blocks_same_bar_reentry():
    candles = make_candles(3)
    candles[1]["high"] = 102.0
    tester = build_tester(candles, desired_net_profit_pct=0.5)
    tester.long_signal = np.array([True, True, False], dtype=bool)
    tester.short_signal = np.array([False, False, False], dtype=bool)

    result = tester.run()

    assert len(result["trades"]) == 1
    assert result["trades"][0]["exit_reason"] == "target"
    assert result["open_position"] is None
    assert sum(m["kind"] == "entry" for m in result["markers"]) == 1
    assert "blocks same-bar re-entry" in result["simulation"]["exit_timing"]


def test_target_exit_blocks_same_bar_reversal():
    candles = make_candles(3)
    candles[1]["high"] = 102.0
    tester = build_tester(candles, desired_net_profit_pct=0.5)
    tester.long_signal = np.array([True, False, False], dtype=bool)
    tester.short_signal = np.array([False, True, False], dtype=bool)

    result = tester.run()

    assert len(result["trades"]) == 1
    assert result["trades"][0]["side"] == "long"
    assert result["open_position"] is None
    assert not any(m["kind"] == "entry" and m["side"] == "short" for m in result["markers"])


def test_pyramiding_tracks_layers_and_level_history():
    candles = make_candles(4)
    tester = build_tester(candles, pyramiding=3)
    tester.long_signal = np.array([True, True, True, False], dtype=bool)
    tester.short_signal = np.zeros(4, dtype=bool)

    result = tester.run()
    position = result["open_position"]

    assert position is not None
    assert position["position_id"] == "bt-pos-1"
    assert position["layers"] == 3
    assert position["entry_ts_ms"] == candles[0]["ts_ms"]
    assert [x["layer_id"] for x in position["layer_ledger"]] == [
        "bt-pos-1-L1",
        "bt-pos-1-L2",
        "bt-pos-1-L3",
    ]
    assert len(position["level_history"]) == 3
    assert [x["layers"] for x in position["level_history"]] == [1, 2, 3]
    assert position["level_history"][0]["avg_entry"] != position["level_history"][-1]["avg_entry"]


def test_closed_pyramided_trade_preserves_full_lifecycle():
    candles = make_candles(5)
    tester = build_tester(candles, pyramiding=3, max_bars_in_trade=3)
    tester.long_signal = np.array([True, True, True, False, False], dtype=bool)
    tester.short_signal = np.zeros(5, dtype=bool)

    result = tester.run()
    trade = result["trades"][0]

    assert trade["position_id"] == "bt-pos-1"
    assert trade["layers"] == 3
    assert len(trade["layer_ledger"]) == 3
    assert len(trade["level_history"]) == 3
    assert trade["entry_ts_ms"] == candles[0]["ts_ms"]
    assert trade["exit_ts_ms"] == candles[3]["ts_ms"]
    assert trade["exit_reason"] == "timeout"
    assert trade["break_even"] == trade["level_history"][-1]["break_even"]
    assert trade["profit_target"] == trade["level_history"][-1]["profit_target"]
    assert result["open_position"] is None
