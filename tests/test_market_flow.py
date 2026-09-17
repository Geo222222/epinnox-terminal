from datetime import datetime, timezone
import time

from app.market_flow import (
    MarketFlowEngine,
    flow_price_state,
    oi_context,
    participation_state,
    session_window,
)


def ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).astimezone(timezone.utc).timestamp() * 1000)


def test_participation_state_thresholds_are_deterministic():
    assert participation_state(None) == "WARMING"
    assert participation_state(0) == "DORMANT"
    assert participation_state(24.99) == "DORMANT"
    assert participation_state(25) == "NORMAL"
    assert participation_state(64.99) == "NORMAL"
    assert participation_state(65) == "ACTIVE"
    assert participation_state(79.99) == "ACTIVE"
    assert participation_state(80) == "ELEVATED"
    assert participation_state(89.99) == "ELEVATED"
    assert participation_state(90) == "HIGH_PARTICIPATION"
    assert participation_state(97) == "HIGH_PARTICIPATION"
    assert participation_state(97.01) == "EXTREME"


def test_flow_price_classification_is_evidence_limited():
    assert flow_price_state(None, 2.0) == "INSUFFICIENT_EVIDENCE"
    assert flow_price_state(1.0, None) == "INSUFFICIENT_EVIDENCE"
    assert flow_price_state(2.0, 1.5) == "EXPANSION"
    assert flow_price_state(-2.0, 1.5) == "DISTRIBUTION_SELL_PRESSURE"
    assert flow_price_state(0.1, 1.5) == "COMPRESSION_POSITIONING"
    assert flow_price_state(2.0, 0.5) == "LOW_CONVICTION_ADVANCE"
    assert flow_price_state(-2.0, 0.5) == "LOW_PARTICIPATION_DECLINE"


def test_oi_context_uses_possibility_language():
    assert oi_context(2.0, True, 3.0) == "NEW_POSITIONING_EXPANSION"
    assert oi_context(2.0, True, -3.0) == "SHORT_COVERING_POSSIBILITY"
    assert oi_context(-2.0, True, 3.0) == "NEW_SHORT_POSITIONING_POSSIBILITY"
    assert oi_context(-2.0, True, -3.0) == "LONG_LIQUIDATION_DERISKING_POSSIBILITY"
    assert oi_context(-2.0, False, -3.0) == "INSUFFICIENT_EVIDENCE"


def test_new_york_session_uses_iana_timezone_across_dst():
    summer = session_window("NEW_YORK", ms("2026-07-15T14:00:00+00:00"))
    winter = session_window("NEW_YORK", ms("2026-01-15T15:00:00+00:00"))

    # 09:00 New York is 13:00 UTC in July and 14:00 UTC in January.
    assert summer.start_ms == ms("2026-07-15T13:00:00+00:00")
    assert summer.end_ms == ms("2026-07-15T21:00:00+00:00")
    assert summer.active is True
    assert winter.start_ms == ms("2026-01-15T14:00:00+00:00")
    assert winter.end_ms == ms("2026-01-15T22:00:00+00:00")
    assert winter.active is True


def test_london_and_asia_sessions_are_explicit_not_browser_local():
    london = session_window("LONDON", ms("2026-09-16T10:00:00+00:00"))
    asia = session_window("ASIA", ms("2026-09-16T03:00:00+00:00"))
    assert london.start_ms == ms("2026-09-16T07:00:00+00:00")  # BST
    assert london.end_ms == ms("2026-09-16T15:00:00+00:00")
    assert london.active is True
    assert asia.start_ms == ms("2026-09-16T01:00:00+00:00")
    assert asia.end_ms == ms("2026-09-16T09:00:00+00:00")
    assert asia.active is True


def test_perpetual_notional_uses_contract_size_and_cursor_survives_restart(tmp_path, monkeypatch):
    now = int(time.time() * 1000)

    class FakeExchange:
        has = {"fetchTrades": True}

        def fetch_trades(self, symbol, since=None, limit=None):
            return [{
                "timestamp": now,
                "price": 10_000.0,
                "amount": 2.0,
                "side": "buy",
            }]

    fake = FakeExchange()
    monkeypatch.setattr("app.market_flow.exchange", lambda: fake)
    market = {
        "symbol": "BTC/USDT:USDT",
        "base": "BTC",
        "contract_size": 0.001,
    }

    path = tmp_path / "flow.db"
    first = MarketFlowEngine(path)
    first._runtime_started_ms = now - 60_000
    first._collect_recent_trades(market)

    minute = now - now % 60_000
    observed = first._sum_flow("BTC", minute, minute + 60_000)
    assert observed["notional"] == 20.0  # 10,000 × 2 contracts × 0.001 BTC/contract
    assert observed["buy_notional"] == 20.0
    assert observed["trade_count"] == 1

    # A new process/runtime loads the persisted cursor. Even if an exchange
    # repeats the overlap trade, it must not be added to the minute twice.
    second = MarketFlowEngine(path)
    second._collect_recent_trades(market)
    observed_after_restart = second._sum_flow("BTC", minute, minute + 60_000)
    assert observed_after_restart["notional"] == 20.0
    assert observed_after_restart["trade_count"] == 1
