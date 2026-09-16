from __future__ import annotations

import numpy as np
import pandas as pd


PARITY_SEMANTICS_VERSION = "pine-v2-rma-supertrend"


def ema(s: pd.Series, n: int) -> pd.Series:
    """Pine-style EMA seeded from the first non-na observation.

    TradingView's ``ta.ema`` uses the recursive form directly instead of
    waiting for ``n`` bars before publishing a value. Keeping that behavior is
    important for early MACD/EMA crossover parity.
    """
    if n <= 0:
        raise ValueError("EMA length must be positive")
    values = s.to_numpy(dtype=np.float64, copy=False)
    out = np.full(len(values), np.nan, dtype=np.float64)
    alpha = 2.0 / (float(n) + 1.0)
    prev = np.nan
    for i, value in enumerate(values):
        if np.isnan(value):
            continue
        prev = value if np.isnan(prev) else alpha * value + (1.0 - alpha) * prev
        out[i] = prev
    return pd.Series(out, index=s.index)


def rma(s: pd.Series, n: int) -> pd.Series:
    """TradingView/Wilder RMA with an SMA seed over the first ``n`` values."""
    if n <= 0:
        raise ValueError("RMA length must be positive")
    values = s.to_numpy(dtype=np.float64, copy=False)
    out = np.full(len(values), np.nan, dtype=np.float64)
    seed: list[float] = []
    prev = np.nan
    seeded = False
    alpha = 1.0 / float(n)
    for i, value in enumerate(values):
        if np.isnan(value):
            continue
        if not seeded:
            seed.append(float(value))
            if len(seed) < n:
                continue
            prev = float(np.mean(seed[-n:]))
            seeded = True
        else:
            prev = alpha * float(value) + (1.0 - alpha) * prev
        out[i] = prev
    return pd.Series(out, index=s.index)


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def rsi(close: pd.Series, n: int) -> pd.Series:
    change = close.diff()
    gain = change.clip(lower=0.0)
    loss = -change.clip(upper=0.0)
    avg_gain = rma(gain, n)
    avg_loss = rma(loss, n)
    out = pd.Series(np.nan, index=close.index, dtype=float)
    ready = avg_gain.notna() & avg_loss.notna()
    zero_loss = ready & (avg_loss == 0)
    zero_gain = ready & (avg_gain == 0) & ~zero_loss
    normal = ready & ~zero_loss & ~zero_gain
    out.loc[zero_loss] = 100.0
    out.loc[zero_gain] = 0.0
    rs = avg_gain.loc[normal] / avg_loss.loc[normal]
    out.loc[normal] = 100.0 - (100.0 / (1.0 + rs))
    return out


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df.close.shift(1)
    return pd.concat(
        [(df.high - df.low).abs(), (df.high - pc).abs(), (df.low - pc).abs()],
        axis=1,
    ).max(axis=1, skipna=True)


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    return rma(true_range(df), n)


def macd(close: pd.Series, fast: int, slow: int, signal: int):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def bollinger(close: pd.Series, n: int, mult: float):
    basis = sma(close, n)
    # Pine ta.stdev defaults to the biased/population estimator.
    dev = close.rolling(n, min_periods=n).std(ddof=0) * mult
    return basis, basis + dev, basis - dev


def stochastic(df: pd.DataFrame, k_len: int, d_len: int):
    lo = df.low.rolling(k_len, min_periods=k_len).min()
    hi = df.high.rolling(k_len, min_periods=k_len).max()
    k = 100.0 * (df.close - lo) / (hi - lo).replace(0, np.nan)
    d = sma(k, d_len)
    return k, d


def dmi_adx(df: pd.DataFrame, n: int, smoothing: int):
    up = df.high.diff()
    down = -df.low.diff()
    plus_dm = pd.Series(np.nan, index=df.index, dtype=float)
    minus_dm = pd.Series(np.nan, index=df.index, dtype=float)
    valid = up.notna() & down.notna()
    plus_dm.loc[valid] = np.where((up.loc[valid] > down.loc[valid]) & (up.loc[valid] > 0), up.loc[valid], 0.0)
    minus_dm.loc[valid] = np.where((down.loc[valid] > up.loc[valid]) & (down.loc[valid] > 0), down.loc[valid], 0.0)

    tr_rma = rma(true_range(df), n)
    plus = 100.0 * rma(plus_dm, n) / tr_rma.replace(0, np.nan)
    minus = 100.0 * rma(minus_dm, n) / tr_rma.replace(0, np.nan)
    denom = (plus + minus).replace(0, np.nan)
    dx = 100.0 * (plus - minus).abs() / denom
    adx = rma(dx, smoothing)
    return plus, minus, adx


def roc(close: pd.Series, n: int) -> pd.Series:
    return close.pct_change(n) * 100.0


def session_vwap(df: pd.DataFrame) -> pd.Series:
    ts = pd.to_datetime(df.ts_ms, unit="ms", utc=True)
    day = ts.dt.floor("D")
    tp = (df.high + df.low + df.close) / 3.0
    pv = tp * df.volume
    return pv.groupby(day).cumsum() / df.volume.groupby(day).cumsum().replace(0, np.nan)


def supertrend(df: pd.DataFrame, n: int, factor: float):
    """TradingView-style ``ta.supertrend`` state machine.

    Direction follows TradingView's sign convention: ``-1`` is bullish/uptrend
    and ``+1`` is bearish/downtrend. This convention matters because Pine
    examples typically enter long on ``direction`` crossing below zero.
    """
    a = atr(df, n).to_numpy(dtype=np.float64, copy=False)
    high = df.high.to_numpy(dtype=np.float64, copy=False)
    low = df.low.to_numpy(dtype=np.float64, copy=False)
    close = df.close.to_numpy(dtype=np.float64, copy=False)
    hl2 = (high + low) / 2.0
    upper = hl2 + factor * a
    lower = hl2 - factor * a
    final_upper = upper.copy()
    final_lower = lower.copy()
    direction = np.full(len(df), np.nan, dtype=np.float64)
    st = np.full(len(df), np.nan, dtype=np.float64)

    for i in range(len(df)):
        if np.isnan(a[i]):
            continue
        if i > 0:
            prev_lower = final_lower[i - 1]
            prev_upper = final_upper[i - 1]
            if np.isnan(prev_lower):
                prev_lower = lower[i]
            if np.isnan(prev_upper):
                prev_upper = upper[i]
            final_lower[i] = lower[i] if (lower[i] > prev_lower or close[i - 1] < prev_lower) else prev_lower
            final_upper[i] = upper[i] if (upper[i] < prev_upper or close[i - 1] > prev_upper) else prev_upper

        if i == 0 or np.isnan(a[i - 1]):
            direction[i] = 1.0
        else:
            prev_st = st[i - 1]
            prev_upper = final_upper[i - 1]
            if not np.isnan(prev_st) and not np.isnan(prev_upper) and prev_st == prev_upper:
                direction[i] = -1.0 if close[i] > final_upper[i] else 1.0
            else:
                direction[i] = 1.0 if close[i] < final_lower[i] else -1.0
        st[i] = final_lower[i] if direction[i] < 0 else final_upper[i]

    return pd.Series(st, index=df.index), pd.Series(direction, index=df.index)


def crossover(a: pd.Series, b: pd.Series | float) -> pd.Series:
    bs = b if isinstance(b, pd.Series) else pd.Series(float(b), index=a.index)
    return (a > bs) & (a.shift(1) <= bs.shift(1))


def crossunder(a: pd.Series, b: pd.Series | float) -> pd.Series:
    bs = b if isinstance(b, pd.Series) else pd.Series(float(b), index=a.index)
    return (a < bs) & (a.shift(1) >= bs.shift(1))
