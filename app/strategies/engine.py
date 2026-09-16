from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models import Candle
from app.strategies import indicators as ind
from app.strategies.presets import get_preset


@dataclass
class PreparedStrategy:
    strategy: str
    timeframe: str
    params: dict[str, float | int]
    long_signals: list[bool]
    short_signals: list[bool]
    overlays: dict[str, tuple[str, list[float | None]]]
    panes: dict[str, tuple[str, list[float | None]]]


def _signal_arrays(n: int) -> tuple[list[bool], list[bool]]:
    return [False] * n, [False] * n


def prepare_strategy(candles: list[Candle], timeframe: str, strategy: str, overrides: dict[str, float | int] | None = None) -> PreparedStrategy:
    params = get_preset(timeframe, strategy, overrides)
    n = len(candles)
    long_signal, short_signal = _signal_arrays(n)
    overlays: dict[str, tuple[str, list[float | None]]] = {}
    panes: dict[str, tuple[str, list[float | None]]] = {}
    ts = [c.ts_ms for c in candles]
    close = [c.close for c in candles]
    high = [c.high for c in candles]
    low = [c.low for c in candles]
    volume = [c.volume for c in candles]

    if strategy == "RSI Mean Reversion":
        r = ind.rsi(close, int(params["length"]))
        panes["RSI"] = ("line", r)
        for i in range(1, n):
            long_signal[i] = ind.crosses_over(r, float(params["oversold"]), i)
            short_signal[i] = ind.crosses_under(r, float(params["overbought"]), i)
    elif strategy == "RSI Momentum":
        r = ind.rsi(close, int(params["length"]))
        panes["RSI"] = ("line", r)
        for i in range(1, n):
            long_signal[i] = ind.crosses_over(r, float(params["bull"]), i)
            short_signal[i] = ind.crosses_under(r, float(params["bear"]), i)
    elif strategy == "EMA Crossover":
        fast = ind.ema(close, int(params["fast"]))
        slow = ind.ema(close, int(params["slow"]))
        overlays["EMA Fast"] = ("line", fast)
        overlays["EMA Slow"] = ("line", slow)
        for i in range(1, n):
            long_signal[i] = ind.crosses_over(fast, slow, i)
            short_signal[i] = ind.crosses_under(fast, slow, i)
    elif strategy == "SMA Crossover":
        fast = ind.sma(close, int(params["fast"]))
        slow = ind.sma(close, int(params["slow"]))
        overlays["SMA Fast"] = ("line", fast)
        overlays["SMA Slow"] = ("line", slow)
        for i in range(1, n):
            long_signal[i] = ind.crosses_over(fast, slow, i)
            short_signal[i] = ind.crosses_under(fast, slow, i)
    elif strategy == "MACD":
        line, signal, hist = ind.macd(close, int(params["fast"]), int(params["slow"]), int(params["signal"]))
        panes["MACD"] = ("line", line)
        panes["MACD Signal"] = ("line", signal)
        panes["MACD Histogram"] = ("histogram", hist)
        for i in range(1, n):
            long_signal[i] = ind.crosses_over(line, signal, i)
            short_signal[i] = ind.crosses_under(line, signal, i)
    elif strategy in {"Bollinger Mean Reversion", "Bollinger Breakout"}:
        length = int(params["length"]); mult = float(params["mult"])
        basis = ind.sma(close, length); sd = ind.rolling_std(close, length)
        upper = [None if basis[i] is None or sd[i] is None else float(basis[i]) + mult * float(sd[i]) for i in range(n)]
        lower = [None if basis[i] is None or sd[i] is None else float(basis[i]) - mult * float(sd[i]) for i in range(n)]
        overlays["Bollinger Upper"] = ("line", upper); overlays["Bollinger Basis"] = ("line", basis); overlays["Bollinger Lower"] = ("line", lower)
        for i in range(1, n):
            if strategy == "Bollinger Mean Reversion":
                long_signal[i] = ind.crosses_over(close, lower, i); short_signal[i] = ind.crosses_under(close, upper, i)
            else:
                long_signal[i] = ind.crosses_over(close, upper, i); short_signal[i] = ind.crosses_under(close, lower, i)
    elif strategy == "Donchian Breakout":
        upper = ind.highest(high, int(params["length"])); lower = ind.lowest(low, int(params["length"]))
        overlays["Donchian Upper"] = ("line", upper); overlays["Donchian Lower"] = ("line", lower)
        prev_upper = [None] + upper[:-1]; prev_lower = [None] + lower[:-1]
        for i in range(1, n):
            long_signal[i] = ind.crosses_over(close, prev_upper, i); short_signal[i] = ind.crosses_under(close, prev_lower, i)
    elif strategy == "Supertrend":
        line, direction = ind.supertrend(high, low, close, int(params["atr_length"]), float(params["factor"]))
        overlays["Supertrend"] = ("line", line)
        for i in range(1, n):
            if direction[i] is not None and direction[i - 1] is not None:
                long_signal[i] = int(direction[i]) < 0 and int(direction[i - 1]) > 0
                short_signal[i] = int(direction[i]) > 0 and int(direction[i - 1]) < 0
    elif strategy == "Stochastic Reversal":
        k, d = ind.stochastic(close, high, low, int(params["k_length"]), int(params["d_length"]))
        panes["Stoch %K"] = ("line", k); panes["Stoch %D"] = ("line", d)
        for i in range(1, n):
            long_signal[i] = ind.crosses_over(k, d, i) and k[i] is not None and float(k[i]) < float(params["oversold"])
            short_signal[i] = ind.crosses_under(k, d, i) and k[i] is not None and float(k[i]) > float(params["overbought"])
    elif strategy == "ADX Trend":
        plus_di, minus_di, adx = ind.dmi_adx(high, low, close, int(params["di_length"]), int(params["smoothing"]))
        panes["+DI"] = ("line", plus_di); panes["-DI"] = ("line", minus_di); panes["ADX"] = ("line", adx)
        threshold = float(params["threshold"])
        for i in range(1, n):
            strong = adx[i] is not None and float(adx[i]) > threshold
            long_signal[i] = strong and ind.crosses_over(plus_di, minus_di, i); short_signal[i] = strong and ind.crosses_over(minus_di, plus_di, i)
    elif strategy == "ATR Breakout":
        a = ind.atr(high, low, close, int(params["atr_length"])); mult = float(params["mult"])
        upper: list[float | None] = [None] * n; lower: list[float | None] = [None] * n
        for i in range(1, n):
            if a[i - 1] is not None:
                upper[i] = close[i - 1] + float(a[i - 1]) * mult; lower[i] = close[i - 1] - float(a[i - 1]) * mult
        overlays["ATR Upper Trigger"] = ("line", upper); overlays["ATR Lower Trigger"] = ("line", lower)
        for i in range(1, n):
            long_signal[i] = ind.crosses_over(close, upper, i); short_signal[i] = ind.crosses_under(close, lower, i)
    elif strategy == "VWAP Deviation":
        vwap = ind.session_vwap(ts, high, low, close, volume); dev = float(params["deviation_pct"]) / 100.0
        upper = [None if x is None else float(x) * (1.0 + dev) for x in vwap]; lower = [None if x is None else float(x) * (1.0 - dev) for x in vwap]
        overlays["VWAP"] = ("line", vwap); overlays["VWAP Upper"] = ("line", upper); overlays["VWAP Lower"] = ("line", lower)
        for i in range(1, n):
            long_signal[i] = ind.crosses_over(close, lower, i); short_signal[i] = ind.crosses_under(close, upper, i)
    elif strategy == "Momentum ROC":
        r = ind.roc(close, int(params["length"])); panes["ROC"] = ("line", r)
        for i in range(1, n):
            long_signal[i] = ind.crosses_over(r, 0.0, i); short_signal[i] = ind.crosses_under(r, 0.0, i)
    elif strategy == "Price Channel Trend":
        upper = ind.highest(high, int(params["length"])); lower = ind.lowest(low, int(params["length"]))
        overlays["Price Channel Upper"] = ("line", upper); overlays["Price Channel Lower"] = ("line", lower)
        prev_upper = [None] + upper[:-1]; prev_lower = [None] + lower[:-1]
        for i in range(1, n):
            long_signal[i] = ind.crosses_over(close, prev_upper, i); short_signal[i] = ind.crosses_under(close, prev_lower, i)
    else:
        raise ValueError(f"Unsupported strategy: {strategy}")

    return PreparedStrategy(strategy, timeframe, params, long_signal, short_signal, overlays, panes)


def to_chart_series(candles: list[Candle], series: dict[str, tuple[str, list[float | None]]]) -> list[dict[str, Any]]:
    payload = []
    for name, (kind, values) in series.items():
        pts = [{"time": int(candle.ts_ms // 1000), "value": float(value)} for candle, value in zip(candles, values) if value is not None]
        payload.append({"name": name, "kind": kind, "values": pts})
    return payload


def raw_signal_markers(candles: list[Candle], prepared: PreparedStrategy) -> list[dict[str, Any]]:
    markers = []
    for i, candle in enumerate(candles):
        if prepared.long_signals[i]: markers.append({"time": candle.ts_ms // 1000, "position": "belowBar", "shape": "arrowUp", "text": "L", "kind": "long"})
        if prepared.short_signals[i]: markers.append({"time": candle.ts_ms // 1000, "position": "aboveBar", "shape": "arrowDown", "text": "S", "kind": "short"})
    return markers
