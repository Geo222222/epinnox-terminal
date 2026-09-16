from __future__ import annotations

import pandas as pd
from . import indicators as I
from .presets import params_for


def build_strategy(df: pd.DataFrame, strategy: str, timeframe: str, manual_params: dict | None = None) -> dict:
    """Build one Pine-parity signal generator.

    Every generator exposes both discrete entry events (long/short) and a
    persistent directional state (state_long/state_short). Composite models can
    therefore use either recent event quorum or a primary trigger plus current
    confirmation state without changing the underlying indicator math.
    """
    p = params_for(timeframe, strategy, manual_params)
    close = df.close
    long = pd.Series(False, index=df.index)
    short = pd.Series(False, index=df.index)
    state_long = pd.Series(False, index=df.index)
    state_short = pd.Series(False, index=df.index)
    overlays: dict[str, pd.Series] = {}
    panes: dict[str, pd.Series] = {}

    if strategy == "RSI Mean Reversion":
        x = I.rsi(close, int(p["length"]))
        long = I.crossover(x, float(p["oversold"]))
        short = I.crossunder(x, float(p["overbought"]))
        state_long, state_short = x <= float(p["oversold"]), x >= float(p["overbought"])
        panes = {"RSI": x}
    elif strategy == "RSI Momentum":
        x = I.rsi(close, int(p["length"]))
        long = I.crossover(x, float(p["bull"]))
        short = I.crossunder(x, float(p["bear"]))
        state_long, state_short = x >= float(p["bull"]), x <= float(p["bear"])
        panes = {"RSI": x}
    elif strategy == "EMA Crossover":
        f, s = I.ema(close, int(p["fast"])), I.ema(close, int(p["slow"]))
        long, short = I.crossover(f, s), I.crossunder(f, s)
        state_long, state_short = f > s, f < s
        overlays = {"EMA Fast": f, "EMA Slow": s}
    elif strategy == "SMA Crossover":
        f, s = I.sma(close, int(p["fast"])), I.sma(close, int(p["slow"]))
        long, short = I.crossover(f, s), I.crossunder(f, s)
        state_long, state_short = f > s, f < s
        overlays = {"SMA Fast": f, "SMA Slow": s}
    elif strategy == "MACD":
        m, sig, hist = I.macd(close, int(p["fast"]), int(p["slow"]), int(p["signal"]))
        long, short = I.crossover(m, sig), I.crossunder(m, sig)
        state_long, state_short = m > sig, m < sig
        panes = {"MACD": m, "Signal": sig, "Histogram": hist}
    elif strategy.startswith("Bollinger"):
        basis, upper, lower = I.bollinger(close, int(p["length"]), float(p["mult"]))
        if strategy == "Bollinger Mean Reversion":
            long, short = I.crossover(close, lower), I.crossunder(close, upper)
            state_long, state_short = close < basis, close > basis
        else:
            long, short = I.crossover(close, upper), I.crossunder(close, lower)
            state_long, state_short = close > upper, close < lower
        overlays = {"BB Upper": upper, "BB Basis": basis, "BB Lower": lower}
    elif strategy == "Donchian Breakout":
        n = int(p["length"])
        upper, lower = df.high.rolling(n).max(), df.low.rolling(n).min()
        prev_upper, prev_lower = upper.shift(1), lower.shift(1)
        long, short = I.crossover(close, prev_upper), I.crossunder(close, prev_lower)
        mid = (upper + lower) / 2.0
        state_long, state_short = close > mid, close < mid
        overlays = {"Donchian Upper": upper, "Donchian Lower": lower}
    elif strategy == "Supertrend":
        st, direction = I.supertrend(df, int(p["atr"]), float(p["factor"]))
        long = (direction > 0) & (direction.shift(1) < 0)
        short = (direction < 0) & (direction.shift(1) > 0)
        state_long, state_short = direction > 0, direction < 0
        overlays = {"Supertrend": st}
    elif strategy == "Stochastic Reversal":
        k, d = I.stochastic(df, int(p["k"]), int(p["d"]))
        long = I.crossover(k, d) & (k < float(p["oversold"]))
        short = I.crossunder(k, d) & (k > float(p["overbought"]))
        state_long, state_short = (k > d) & (k < 50), (k < d) & (k > 50)
        panes = {"%K": k, "%D": d}
    elif strategy == "ADX Trend":
        plus, minus, adx = I.dmi_adx(df, int(p["length"]), int(p["smoothing"]))
        strong = adx > float(p["threshold"])
        long = strong & I.crossover(plus, minus)
        short = strong & I.crossover(minus, plus)
        state_long, state_short = strong & (plus > minus), strong & (minus > plus)
        panes = {"ADX": adx, "+DI": plus, "-DI": minus}
    elif strategy == "ATR Breakout":
        a = I.atr(df, int(p["atr"]))
        upper = close.shift(1) + a.shift(1) * float(p["mult"])
        lower = close.shift(1) - a.shift(1) * float(p["mult"])
        long, short = I.crossover(close, upper), I.crossunder(close, lower)
        state_long, state_short = close > upper, close < lower
        overlays = {"ATR Upper": upper, "ATR Lower": lower}
    elif strategy == "VWAP Deviation":
        v = I.session_vwap(df)
        dev = float(p["deviation_pct"]) / 100.0
        upper, lower = v * (1 + dev), v * (1 - dev)
        long, short = I.crossover(close, lower), I.crossunder(close, upper)
        state_long, state_short = close < v, close > v
        overlays = {"VWAP": v, "VWAP Upper": upper, "VWAP Lower": lower}
    elif strategy == "Momentum ROC":
        r = I.roc(close, int(p["length"]))
        long, short = I.crossover(r, 0.0), I.crossunder(r, 0.0)
        state_long, state_short = r > 0.0, r < 0.0
        panes = {"ROC": r}
    elif strategy == "Price Channel Trend":
        n = int(p["length"])
        upper, lower = df.high.rolling(n).max(), df.low.rolling(n).min()
        long, short = I.crossover(close, upper.shift(1)), I.crossunder(close, lower.shift(1))
        mid = (upper + lower) / 2.0
        state_long, state_short = close > mid, close < mid
        overlays = {"Channel Upper": upper, "Channel Lower": lower}
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    return {
        "long": long.fillna(False),
        "short": short.fillna(False),
        "state_long": state_long.fillna(False),
        "state_short": state_short.fillna(False),
        "overlays": overlays,
        "panes": panes,
        "params": p,
    }


def _recent(events: pd.Series, window: int) -> pd.Series:
    return events.astype(int).rolling(max(1, int(window)), min_periods=1).max().astype(bool)


def build_entry_model(
    df: pd.DataFrame,
    primary: str,
    timeframe: str,
    manual_params: dict | None = None,
    confirmations: list[str] | None = None,
    policy: str = "Single",
    required: int = 2,
    window_bars: int = 1,
) -> dict:
    """Combine signal generators into a deterministic entry model.

    Policies:
      Single: primary event only.
      All Recent Events: every selected strategy produced a same-direction event
        within the rolling confirmation window.
      Quorum Recent Events: at least `required` selected strategies produced a
        same-direction event within the rolling confirmation window.
      Primary + All States: primary must fire now and every confirmation must be
        in a same-direction persistent state on that bar.
    """
    names = [primary]
    for name in confirmations or []:
        if name and name not in names:
            names.append(name)

    parts: dict[str, dict] = {}
    for name in names:
        mp = manual_params if name == primary else None
        parts[name] = build_strategy(df, name, timeframe, mp)

    p0 = parts[primary]
    if policy == "Single" or len(names) == 1:
        long, short = p0["long"].copy(), p0["short"].copy()
    elif policy == "Primary + All States":
        long, short = p0["long"].copy(), p0["short"].copy()
        for name in names[1:]:
            long &= parts[name]["state_long"]
            short &= parts[name]["state_short"]
    else:
        long_votes = pd.Series(0, index=df.index, dtype=int)
        short_votes = pd.Series(0, index=df.index, dtype=int)
        for name in names:
            long_votes += _recent(parts[name]["long"], window_bars).astype(int)
            short_votes += _recent(parts[name]["short"], window_bars).astype(int)
        needed = len(names) if policy == "All Recent Events" else max(1, min(int(required), len(names)))
        long = long_votes >= needed
        short = short_votes >= needed
        # Conflicting quorums are intentionally neutral rather than arbitrarily
        # selecting a direction.
        conflict = long & short
        long &= ~conflict
        short &= ~conflict

    overlays: dict[str, pd.Series] = {}
    panes: dict[str, pd.Series] = {}
    for name, part in parts.items():
        prefix = "" if name == primary else f"{name} · "
        overlays.update({f"{prefix}{k}": v for k, v in part["overlays"].items()})
        panes.update({f"{prefix}{k}": v for k, v in part["panes"].items()})

    return {
        "long": long.fillna(False),
        "short": short.fillna(False),
        "overlays": overlays,
        "panes": panes,
        "params": {name: part["params"] for name, part in parts.items()},
        "components": names,
        "policy": policy,
        "required": required,
        "window_bars": window_bars,
        "parts": parts,
    }


def entry_receipt(model: dict, index: int, side: str) -> list[dict]:
    """Explain the evidence behind one composite entry at a specific bar."""
    want_long = side == "long"
    out: list[dict] = []
    primary = model["components"][0]
    policy = model["policy"]
    window = max(1, int(model["window_bars"]))
    for name in model["components"]:
        part = model["parts"][name]
        events = part["long"] if want_long else part["short"]
        states = part["state_long"] if want_long else part["state_short"]
        if policy == "Primary + All States" and name != primary:
            matched = bool(states.iloc[index])
            kind = "state"
            age = 0
        else:
            start = max(0, index - window + 1)
            hits = [j for j in range(start, index + 1) if bool(events.iloc[j])]
            matched = bool(hits)
            age = index - hits[-1] if hits else None
            kind = "trigger" if name == primary else "event"
        out.append({"strategy": name, "kind": kind, "matched": matched, "age_bars": age})
    return out
