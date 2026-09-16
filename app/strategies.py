from __future__ import annotations

import pandas as pd
from . import indicators as I
from .presets import params_for


def build_strategy(df: pd.DataFrame, strategy: str, timeframe: str, manual_params: dict | None = None) -> dict:
    p = params_for(timeframe, strategy, manual_params)
    close = df.close
    long = pd.Series(False, index=df.index)
    short = pd.Series(False, index=df.index)
    overlays: dict[str, pd.Series] = {}
    panes: dict[str, pd.Series] = {}

    if strategy == "RSI Mean Reversion":
        x = I.rsi(close, int(p["length"]))
        long = I.crossover(x, float(p["oversold"]))
        short = I.crossunder(x, float(p["overbought"]))
        panes = {"RSI": x}
    elif strategy == "RSI Momentum":
        x = I.rsi(close, int(p["length"]))
        long = I.crossover(x, float(p["bull"]))
        short = I.crossunder(x, float(p["bear"]))
        panes = {"RSI": x}
    elif strategy == "EMA Crossover":
        f, s = I.ema(close, int(p["fast"])), I.ema(close, int(p["slow"]))
        long, short = I.crossover(f, s), I.crossunder(f, s)
        overlays = {"EMA Fast": f, "EMA Slow": s}
    elif strategy == "SMA Crossover":
        f, s = I.sma(close, int(p["fast"])), I.sma(close, int(p["slow"]))
        long, short = I.crossover(f, s), I.crossunder(f, s)
        overlays = {"SMA Fast": f, "SMA Slow": s}
    elif strategy == "MACD":
        m, sig, hist = I.macd(close, int(p["fast"]), int(p["slow"]), int(p["signal"]))
        long, short = I.crossover(m, sig), I.crossunder(m, sig)
        panes = {"MACD": m, "Signal": sig, "Histogram": hist}
    elif strategy.startswith("Bollinger"):
        basis, upper, lower = I.bollinger(close, int(p["length"]), float(p["mult"]))
        if strategy == "Bollinger Mean Reversion":
            long, short = I.crossover(close, lower), I.crossunder(close, upper)
        else:
            long, short = I.crossover(close, upper), I.crossunder(close, lower)
        overlays = {"BB Upper": upper, "BB Basis": basis, "BB Lower": lower}
    elif strategy == "Donchian Breakout":
        n = int(p["length"])
        upper, lower = df.high.rolling(n).max(), df.low.rolling(n).min()
        long, short = I.crossover(close, upper.shift(1)), I.crossunder(close, lower.shift(1))
        overlays = {"Donchian Upper": upper, "Donchian Lower": lower}
    elif strategy == "Supertrend":
        st, direction = I.supertrend(df, int(p["atr"]), float(p["factor"]))
        long = (direction > 0) & (direction.shift(1) < 0)
        short = (direction < 0) & (direction.shift(1) > 0)
        overlays = {"Supertrend": st}
    elif strategy == "Stochastic Reversal":
        k, d = I.stochastic(df, int(p["k"]), int(p["d"]))
        long = I.crossover(k, d) & (k < float(p["oversold"]))
        short = I.crossunder(k, d) & (k > float(p["overbought"]))
        panes = {"%K": k, "%D": d}
    elif strategy == "ADX Trend":
        plus, minus, adx = I.dmi_adx(df, int(p["length"]), int(p["smoothing"]))
        long = (adx > float(p["threshold"])) & I.crossover(plus, minus)
        short = (adx > float(p["threshold"])) & I.crossover(minus, plus)
        panes = {"ADX": adx, "+DI": plus, "-DI": minus}
    elif strategy == "ATR Breakout":
        a = I.atr(df, int(p["atr"]))
        upper = close.shift(1) + a.shift(1) * float(p["mult"])
        lower = close.shift(1) - a.shift(1) * float(p["mult"])
        long, short = I.crossover(close, upper), I.crossunder(close, lower)
        overlays = {"ATR Upper": upper, "ATR Lower": lower}
    elif strategy == "VWAP Deviation":
        v = I.session_vwap(df)
        dev = float(p["deviation_pct"]) / 100.0
        upper, lower = v * (1 + dev), v * (1 - dev)
        long, short = I.crossover(close, lower), I.crossunder(close, upper)
        overlays = {"VWAP": v, "VWAP Upper": upper, "VWAP Lower": lower}
    elif strategy == "Momentum ROC":
        r = I.roc(close, int(p["length"]))
        long, short = I.crossover(r, 0.0), I.crossunder(r, 0.0)
        panes = {"ROC": r}
    elif strategy == "Price Channel Trend":
        n = int(p["length"])
        upper, lower = df.high.rolling(n).max(), df.low.rolling(n).min()
        long, short = I.crossover(close, upper.shift(1)), I.crossunder(close, lower.shift(1))
        overlays = {"Channel Upper": upper, "Channel Lower": lower}
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    return {"long": long.fillna(False), "short": short.fillna(False), "overlays": overlays, "panes": panes, "params": p}
