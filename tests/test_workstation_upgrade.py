import pytest

from app.market import TIMEFRAME_SPECS
from app.models import BacktestRequest, PaperLiveStartRequest
from app.presets import params_for, preset_source


def test_terminal_exposes_tradingview_style_timeframes():
    expected={"1m","5m","15m","30m","1h","2h","3h","4h","5h","8h","1d","5d","1w","1M"}
    assert expected.issubset(TIMEFRAME_SPECS)
    for tf in expected:
        req=BacktestRequest(timeframe=tf)
        assert req.timeframe==tf


def test_long_timeframes_have_explicit_preset_source():
    assert preset_source("1h")=="30m"
    assert preset_source("1M")=="30m"
    assert params_for("1h","Supertrend")==params_for("30m","Supertrend")


def test_paper_start_requires_account_identity():
    req=PaperLiveStartRequest(account_id="paper-account-1",strategy=BacktestRequest())
    assert req.account_id=="paper-account-1"
    with pytest.raises(Exception):
        PaperLiveStartRequest(account_id="",strategy=BacktestRequest())
