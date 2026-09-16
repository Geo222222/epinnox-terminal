from __future__ import annotations

PRESETS: dict[str, dict[str, dict[str, float | int]]] = {
    "1m": {
        "RSI Mean Reversion": {"length": 7, "oversold": 25, "overbought": 75},
        "RSI Momentum": {"length": 7, "bull": 60, "bear": 40},
        "EMA Crossover": {"fast": 5, "slow": 13},
        "SMA Crossover": {"fast": 9, "slow": 21},
        "MACD": {"fast": 5, "slow": 13, "signal": 4},
        "Bollinger Mean Reversion": {"length": 14, "mult": 2.0},
        "Bollinger Breakout": {"length": 14, "mult": 2.0},
        "Donchian Breakout": {"length": 12},
        "Supertrend": {"atr": 7, "factor": 2.0},
        "Stochastic Reversal": {"k": 9, "d": 3, "oversold": 20, "overbought": 80},
        "ADX Trend": {"length": 7, "smoothing": 7, "threshold": 22},
        "ATR Breakout": {"atr": 7, "mult": 1.2},
        "VWAP Deviation": {"deviation_pct": 0.15},
        "Momentum ROC": {"length": 5},
        "Price Channel Trend": {"length": 12},
    },
    "5m": {
        "RSI Mean Reversion": {"length": 9, "oversold": 30, "overbought": 70},
        "RSI Momentum": {"length": 9, "bull": 58, "bear": 42},
        "EMA Crossover": {"fast": 8, "slow": 21},
        "SMA Crossover": {"fast": 10, "slow": 30},
        "MACD": {"fast": 8, "slow": 21, "signal": 5},
        "Bollinger Mean Reversion": {"length": 20, "mult": 2.0},
        "Bollinger Breakout": {"length": 20, "mult": 2.0},
        "Donchian Breakout": {"length": 20},
        "Supertrend": {"atr": 10, "factor": 2.5},
        "Stochastic Reversal": {"k": 14, "d": 3, "oversold": 20, "overbought": 80},
        "ADX Trend": {"length": 10, "smoothing": 10, "threshold": 20},
        "ATR Breakout": {"atr": 10, "mult": 1.4},
        "VWAP Deviation": {"deviation_pct": 0.25},
        "Momentum ROC": {"length": 8},
        "Price Channel Trend": {"length": 20},
    },
    "15m": {
        "RSI Mean Reversion": {"length": 14, "oversold": 30, "overbought": 70},
        "RSI Momentum": {"length": 14, "bull": 55, "bear": 45},
        "EMA Crossover": {"fast": 12, "slow": 26},
        "SMA Crossover": {"fast": 20, "slow": 50},
        "MACD": {"fast": 12, "slow": 26, "signal": 9},
        "Bollinger Mean Reversion": {"length": 20, "mult": 2.0},
        "Bollinger Breakout": {"length": 20, "mult": 2.0},
        "Donchian Breakout": {"length": 24},
        "Supertrend": {"atr": 10, "factor": 3.0},
        "Stochastic Reversal": {"k": 14, "d": 3, "oversold": 20, "overbought": 80},
        "ADX Trend": {"length": 14, "smoothing": 14, "threshold": 22},
        "ATR Breakout": {"atr": 14, "mult": 1.5},
        "VWAP Deviation": {"deviation_pct": 0.40},
        "Momentum ROC": {"length": 10},
        "Price Channel Trend": {"length": 30},
    },
    "30m": {
        "RSI Mean Reversion": {"length": 14, "oversold": 30, "overbought": 70},
        "RSI Momentum": {"length": 14, "bull": 55, "bear": 45},
        "EMA Crossover": {"fast": 20, "slow": 50},
        "SMA Crossover": {"fast": 20, "slow": 50},
        "MACD": {"fast": 12, "slow": 26, "signal": 9},
        "Bollinger Mean Reversion": {"length": 20, "mult": 2.1},
        "Bollinger Breakout": {"length": 20, "mult": 2.1},
        "Donchian Breakout": {"length": 30},
        "Supertrend": {"atr": 14, "factor": 3.0},
        "Stochastic Reversal": {"k": 14, "d": 3, "oversold": 20, "overbought": 80},
        "ADX Trend": {"length": 14, "smoothing": 14, "threshold": 25},
        "ATR Breakout": {"atr": 14, "mult": 1.8},
        "VWAP Deviation": {"deviation_pct": 0.60},
        "Momentum ROC": {"length": 14},
        "Price Channel Trend": {"length": 50},
    },
}

STRATEGIES = list(PRESETS["1m"].keys())
LONG_TIMEFRAME_PRESET_SOURCE = {
    "1h": "30m", "2h": "30m", "3h": "30m", "4h": "30m", "5h": "30m", "8h": "30m",
    "1d": "30m", "5d": "30m", "1w": "30m", "1M": "30m",
}


def preset_source(timeframe: str) -> str:
    """Return the parameter set used by a chart interval.

    1m-30m have separately qualified presets. Longer chart intervals currently
    reuse the 30m parameter set deterministically until their own qualification
    work is completed; the UI exposes this source instead of implying otherwise.
    """
    if timeframe in PRESETS:
        return timeframe
    try:
        return LONG_TIMEFRAME_PRESET_SOURCE[timeframe]
    except KeyError as exc:
        raise ValueError(f"Unsupported timeframe preset: {timeframe}") from exc


def params_for(timeframe: str, strategy: str, manual: dict | None = None) -> dict:
    if manual:
        return dict(manual)
    return dict(PRESETS[preset_source(timeframe)][strategy])
