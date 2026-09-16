from app.models import BacktestRequest
from app.presets import params_for, STRATEGIES
from app.backtest import run_backtest
from app.strategies import build_entry_model
import pandas as pd


def candles(n=300):
    out=[]
    px=2500.0
    for i in range(n):
        drift = 3.0 if (i//25)%2==0 else -2.5
        op=px; cl=max(100.0,px+drift); hi=max(op,cl)+4; lo=min(op,cl)-4
        out.append({"ts_ms":1_700_000_000_000+i*60_000,"open":op,"high":hi,"low":lo,"close":cl,"volume":100+i%7})
        px=cl
    return out


def test_preset_matches_pine_supertrend_1m():
    assert params_for("1m","Supertrend") == {"atr":7,"factor":2.0}


def test_all_fifteen_strategies_build_and_backtest():
    for name in STRATEGIES:
        req=BacktestRequest(strategy=name,timeframe="1m",starting_balance=1000,leverage=2,allocation_pct=5)
        result=run_backtest(candles(),req)
        assert result["strategy"]==name
        assert result["entry_model"]["policy"]=="Single"
        assert result["backtest_profile"]=="TradingView Parity"
        assert result["simulation"]["liquidation_enabled"] is False
        assert "metrics" in result
        assert "overlays" in result
        assert "panes" in result


def test_fee_target_and_trade_ledger_fields_exist():
    req=BacktestRequest(strategy="Supertrend",timeframe="1m",starting_balance=1000,leverage=2,allocation_pct=5)
    result=run_backtest(candles(),req)
    if result["trades"]:
        row=result["trades"][0]
        for key in ("entry_fee","exit_fee","total_fee","referral_commission","mae_pct","mfe_pct","exit_reason","entry_confirmation","exit_receipt"):
            assert key in row


def test_parity_mode_disables_liquidation_even_at_high_leverage():
    req=BacktestRequest(
        strategy="Supertrend",
        timeframe="1m",
        starting_balance=1000,
        leverage=200,
        allocation_pct=5,
        backtest_profile="TradingView Parity",
    )
    result=run_backtest(candles(500),req)
    assert result["simulation"]["liquidation_enabled"] is False
    assert result["metrics"]["liquidation_exits"] == 0
    assert all(t["exit_reason"] != "liquidation" for t in result["trades"])


def test_simplified_liquidation_adds_audit_receipt_when_triggered():
    data=[]
    px=2500.0
    for i in range(120):
        op=px
        cl=px + (3.0 if i < 40 else -2.0)
        hi=max(op,cl)+3
        lo=min(op,cl)-3
        data.append({"ts_ms":1_700_000_000_000+i*60_000,"open":op,"high":hi,"low":lo,"close":cl,"volume":100})
        px=cl
    req=BacktestRequest(
        strategy="EMA Crossover",
        timeframe="1m",
        starting_balance=1000,
        leverage=200,
        allocation_pct=5,
        backtest_profile="Simplified Isolated",
        manual_params={"fast":2,"slow":5},
    )
    result=run_backtest(data,req)
    for trade in result["trades"]:
        if trade["exit_reason"]=="liquidation":
            receipt=trade["exit_receipt"]
            assert receipt["model"]=="Simplified isolated estimate"
            assert "estimated_liquidation_price" in receipt
            assert "candle_low" in receipt
            assert "candle_high" in receipt
            break


def test_composite_primary_plus_states_runs_with_three_strategies():
    req=BacktestRequest(
        strategy="Stochastic Reversal",
        confirmations=["Supertrend","ADX Trend"],
        confirmation_policy="Primary + All States",
        timeframe="1m",
        starting_balance=1000,
        leverage=2,
        allocation_pct=5,
    )
    result=run_backtest(candles(500),req)
    assert result["entry_model"]["primary"]=="Stochastic Reversal"
    assert result["entry_model"]["confirmations"]==["Supertrend","ADX Trend"]
    assert result["entry_model"]["policy"]=="Primary + All States"
    assert "Supertrend · Supertrend" in result["overlays"]
    assert "ADX Trend · ADX" in result["panes"]


def test_recent_event_quorum_emits_one_edge_per_confirmation_cluster():
    df=pd.DataFrame(candles(500))
    model=build_entry_model(
        df,
        "EMA Crossover",
        "1m",
        confirmations=["SMA Crossover","MACD"],
        policy="Quorum Recent Events",
        required=2,
        window_bars=5,
    )
    for series in (model["long"],model["short"]):
        assert not bool((series & series.shift(1,fill_value=False)).any())


def test_confirmation_required_cannot_exceed_selected_strategies():
    try:
        BacktestRequest(
            strategy="Supertrend",
            confirmations=["ADX Trend"],
            confirmation_policy="Quorum Recent Events",
            confirmation_required=3,
        )
        assert False, "expected validation error"
    except ValueError:
        pass


def test_invalid_explicit_window_is_rejected():
    try:
        BacktestRequest(start_ts_ms=2000,end_ts_ms=1000)
        assert False, "expected validation error"
    except ValueError:
        pass
