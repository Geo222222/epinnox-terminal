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
        assert "metrics" in result
        assert "overlays" in result
        assert "panes" in result


def test_fee_target_and_trade_ledger_fields_exist():
    req=BacktestRequest(strategy="Supertrend",timeframe="1m",starting_balance=1000,leverage=2,allocation_pct=5)
    result=run_backtest(candles(),req)
    if result["trades"]:
        row=result["trades"][0]
        for key in ("entry_fee","exit_fee","total_fee","referral_commission","mae_pct","mfe_pct","exit_reason","entry_confirmation"):
            assert key in row


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
        # Composite events are rising edges; they cannot remain true on
        # consecutive bars just because the rolling confirmation window remains valid.
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
