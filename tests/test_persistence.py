from pathlib import Path

from app.settings import load_settings
from app.storage import RuntimeStore


def test_settings_schema_and_defaults_are_available():
    settings = load_settings()
    assert settings["schema_version"] == 1
    assert settings["terminal"]["default_backtest_profile"] == "TradingView Parity"
    assert settings["features"]["workspace_persistence"] is True


def test_runtime_store_round_trips_paper_session_events_and_presets(tmp_path: Path):
    store = RuntimeStore(tmp_path / "terminal.db")
    request = {"symbol": "ETH/USDT:USDT", "timeframe": "1m", "strategy": "Supertrend"}
    store.save_session(
        "session-1",
        status="RUNNING",
        request=request,
        started_at_ms=100,
        last_bar_ts_ms=200,
        last_error=None,
        last_signal={"side": "long"},
        position={"side": "long", "entry_price": 2500},
        layers=1,
        bars_in_position=3,
        pending_intent=None,
        recovered_count=0,
    )
    loaded = store.load_active_session()
    assert loaded is not None
    assert loaded["session_id"] == "session-1"
    assert loaded["request"] == request
    assert loaded["layers"] == 1

    store.add_event("session-1", 300, "checkpoint", "saved", {"bar": 9})
    events = store.recent_events("session-1")
    assert events[-1]["kind"] == "checkpoint"
    assert events[-1]["bar"] == 9

    saved = store.save_preset("ETH 1m Supertrend", {"strategy": "Supertrend", "timeframe": "1m"})
    assert saved["name"] == "ETH 1m Supertrend"
    assert store.list_presets()[0]["payload"]["timeframe"] == "1m"
    assert store.delete_preset("ETH 1m Supertrend") is True


def test_supersede_prevents_stale_recovery(tmp_path: Path):
    store = RuntimeStore(tmp_path / "terminal.db")
    store.save_session(
        "old",
        status="RECOVERY_REQUIRED",
        request={"symbol": "ETH/USDT:USDT"},
        started_at_ms=1,
        last_bar_ts_ms=None,
        last_error="old",
        last_signal=None,
        position=None,
        layers=0,
        bars_in_position=0,
        pending_intent=None,
    )
    assert store.load_active_session() is not None
    assert store.supersede_active_sessions() == 1
    assert store.load_active_session() is None
