from app.models import BacktestRequest
from app.presets import params_for, STRATEGIES
from app.backtest import run_backtest


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
        assert "metrics" in result
        assert "overlays" in result
        assert "panes" in result


def test_fee_target_and_trade_ledger_fields_exist():
    req=BacktestRequest(strategy="Supertrend",timeframe="1m",starting_balance=1000,leverage=2,allocation_pct=5)
    result=run_backtest(candles(),req)
    if result["trades"]:
        row=result["trades"][0]
        for key in ("entry_fee","exit_fee","total_fee","referral_commission","mae_pct","mfe_pct","exit_reason"):
            assert key in row
