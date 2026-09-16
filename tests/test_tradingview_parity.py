import math

import pandas as pd

from app import indicators as I
from app.strategies import build_strategy


def test_pine_ema_seeds_from_first_observation():
    s=pd.Series([1.0,2.0,3.0,4.0])
    got=I.ema(s,3).tolist()
    expected=[1.0,1.5,2.25,3.125]
    for a,b in zip(got,expected):
        assert abs(a-b)<1e-12


def test_pine_rma_uses_sma_seed_then_wilder_recursion():
    s=pd.Series([1.0,2.0,3.0,4.0,5.0])
    got=I.rma(s,3).tolist()
    assert math.isnan(got[0]) and math.isnan(got[1])
    assert abs(got[2]-2.0)<1e-12
    assert abs(got[3]-(8.0/3.0))<1e-12
    assert abs(got[4]-(31.0/9.0))<1e-12


def test_rsi_matches_wilder_seed_and_keeps_warmup_na():
    close=pd.Series([1.0,2.0,3.0,4.0,3.0,2.0,3.0])
    got=I.rsi(close,3).tolist()
    assert all(math.isnan(got[i]) for i in range(3))
    assert abs(got[3]-100.0)<1e-9
    assert abs(got[4]-(200.0/3.0))<1e-9
    assert abs(got[5]-(400.0/9.0))<1e-9
    assert abs(got[6]-(1700.0/27.0))<1e-9


def test_atr_uses_rma_of_true_range():
    df=pd.DataFrame({
        "high":[11.0,12.0,13.0,14.0],
        "low":[9.0,10.0,11.0,12.0],
        "close":[10.0,11.0,12.0,13.0],
    })
    got=I.atr(df,3).tolist()
    assert math.isnan(got[0]) and math.isnan(got[1])
    assert got[2]==2.0 and got[3]==2.0


def test_supertrend_uses_tradingview_direction_sign_convention():
    rows=[]
    px=100.0
    for i in range(80):
        drift=2.0 if i<40 else -2.4
        op=px
        cl=px+drift
        rows.append({"ts_ms":1_700_000_000_000+i*60_000,"open":op,"high":max(op,cl)+0.6,"low":min(op,cl)-0.6,"close":cl,"volume":100.0})
        px=cl
    df=pd.DataFrame(rows)
    st,direction=I.supertrend(df,7,2.0)
    valid=direction.dropna()
    assert valid.iloc[0]==1.0
    assert (valid==-1.0).any()
    assert (valid==1.0).any()
    bullish=direction==-1.0
    bearish=direction==1.0
    assert (st[bullish] <= df.close[bullish]).all()
    assert (st[bearish] >= df.close[bearish]).all()

    strategy=build_strategy(df,"Supertrend","1m")
    expected_long=(direction<0)&(direction.shift(1)>0)
    expected_short=(direction>0)&(direction.shift(1)<0)
    assert strategy["long"].equals(expected_long.fillna(False))
    assert strategy["short"].equals(expected_short.fillna(False))


def test_parity_semantics_version_is_explicit():
    assert I.PARITY_SEMANTICS_VERSION=="pine-v2-rma-supertrend"
