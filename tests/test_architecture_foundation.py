from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.economics import fee_aware_exit_levels
from app.indicators import supertrend
from app.market import clear_market_cache, fetch_ohlcv
from app.session_registry import PaperSessionRegistry, SessionConflict
from app.storage import RuntimeStore


def test_fee_aware_exit_levels_cover_costs():
    levels = fee_aware_exit_levels(
        2500.0,
        "long",
        entry_fee_pct=0.05,
        exit_fee_pct=0.05,
        extra_cost_pct=0.0,
        desired_net_profit_pct=0.01,
    )
    assert levels.break_even > 2500.0
    assert levels.target > levels.break_even


def test_numpy_supertrend_obeys_pine_direction_and_warmup_contract():
    close = np.array([100, 101, 102, 99, 98, 100, 103, 104, 102, 105, 107, 106, 108, 109, 107, 110, 111], dtype=float)
    df = pd.DataFrame({
        "high": close + 1.5,
        "low": close - 1.25,
        "close": close,
        "open": close - 0.2,
        "volume": np.ones(len(close)),
        "ts_ms": np.arange(len(close)) * 60_000,
    })
    st, direction = supertrend(df, 3, 2.0)

    # ATR/RMA length 3 publishes after its three-value SMA seed.
    assert st.iloc[:2].isna().all()
    assert st.iloc[2:].notna().all()
    assert direction.iloc[:2].isna().all()
    assert set(direction.dropna().unique()).issubset({-1.0, 1.0})

    # TradingView ta.supertrend convention: -1 is bullish (line below price),
    # +1 is bearish (line above price).
    bullish = direction == -1.0
    bearish = direction == 1.0
    assert (st[bullish] <= df.close[bullish]).all()
    assert (st[bearish] >= df.close[bearish]).all()


def test_latest_ohlcv_cache_avoids_duplicate_exchange_calls(monkeypatch):
    class FakeExchange:
        def __init__(self):
            self.calls = 0

        def fetch_ohlcv(self, symbol, timeframe, limit):
            self.calls += 1
            return [[i * 60_000, 1, 2, 0.5, 1.5, 10] for i in range(limit)]

    fake = FakeExchange()
    monkeypatch.setattr("app.market.exchange", lambda: fake)
    clear_market_cache()
    first = fetch_ohlcv("ETH/USDT:USDT", "1m", 100)
    second = fetch_ohlcv("ETH/USDT:USDT", "1m", 100)
    assert first == second
    assert fake.calls == 1


def _save_active(store: RuntimeStore, session_id: str, account_id: str, symbol: str):
    store.save_session(
        session_id,
        status="RUNNING",
        request={"symbol": symbol, "timeframe": "1m", "strategy": "Supertrend", "_terminal_account_id": account_id},
        started_at_ms=1,
        last_bar_ts_ms=None,
        last_error=None,
        last_signal=None,
        position=None,
        layers=0,
        bars_in_position=0,
        pending_intent=None,
    )


def test_registry_enforces_account_and_instrument_ownership(tmp_path: Path):
    store = RuntimeStore(tmp_path / "sessions.db")
    _save_active(store, "one", "acct-a", "ETH/USDT:USDT")
    registry = PaperSessionRegistry(store)

    # Same account may host independent instruments.
    registry._assert_available("acct-a", "SOL/USDT:USDT")

    with pytest.raises(SessionConflict, match="strategy owner"):
        registry._assert_available("acct-a", "ETH/USDT:USDT")

    with pytest.raises(SessionConflict, match="different Epinnox Online account"):
        registry._assert_available("acct-b", "SOL/USDT:USDT")


def test_runtime_store_lists_multiple_active_sessions(tmp_path: Path):
    store = RuntimeStore(tmp_path / "sessions.db")
    _save_active(store, "one", "acct-a", "ETH/USDT:USDT")
    _save_active(store, "two", "acct-a", "SOL/USDT:USDT")
    rows = store.load_active_sessions()
    assert {row["session_id"] for row in rows} == {"one", "two"}
