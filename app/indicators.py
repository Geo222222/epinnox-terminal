from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    down = -d.clip(upper=0.0)
    au = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    ad = down.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = au / ad.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50.0)


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df.close.shift(1)
    return pd.concat([(df.high-df.low).abs(), (df.high-pc).abs(), (df.low-pc).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    return true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def macd(close: pd.Series, fast: int, slow: int, signal: int):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def bollinger(close: pd.Series, n: int, mult: float):
    basis = sma(close, n)
    dev = close.rolling(n, min_periods=n).std(ddof=0) * mult
    return basis, basis + dev, basis - dev


def stochastic(df: pd.DataFrame, k_len: int, d_len: int):
    lo = df.low.rolling(k_len, min_periods=k_len).min()
    hi = df.high.rolling(k_len, min_periods=k_len).max()
    k = 100 * (df.close - lo) / (hi - lo).replace(0, np.nan)
    d = sma(k, d_len)
    return k, d


def dmi_adx(df: pd.DataFrame, n: int, smoothing: int):
    up = df.high.diff()
    dn = -df.low.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    tr = true_range(df)
    atr_s = tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    plus = 100 * plus_dm.ewm(alpha=1/n, adjust=False, min_periods=n).mean() / atr_s
    minus = 100 * minus_dm.ewm(alpha=1/n, adjust=False, min_periods=n).mean() / atr_s
    dx = 100 * (plus-minus).abs() / (plus+minus).replace(0, np.nan)
    adx = dx.ewm(alpha=1/smoothing, adjust=False, min_periods=smoothing).mean()
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
    """Supertrend with a tight NumPy state loop.

    The algorithm is inherently recursive, so replacing pandas ``iloc`` access
    with numeric arrays preserves the exact state machine while avoiding the
    dominant Python/pandas indexing overhead. A JIT layer can be added later
    only after parity benchmarks justify the dependency.
    """
    a = atr(df, n)
    a_values = a.to_numpy(dtype=np.float64, copy=False)
    high = df.high.to_numpy(dtype=np.float64, copy=False)
    low = df.low.to_numpy(dtype=np.float64, copy=False)
    close = df.close.to_numpy(dtype=np.float64, copy=False)
    hl2 = (high + low) / 2.0
    basic_u = hl2 + factor * a_values
    basic_l = hl2 - factor * a_values
    final_u = basic_u.copy()
    final_l = basic_l.copy()
    direction = np.ones(len(df), dtype=np.float64)
    st = np.full(len(df), np.nan, dtype=np.float64)

    for i in range(1, len(df)):
        if np.isnan(a_values[i]):
            direction[i] = 1.0
            continue
        prev_u = final_u[i - 1]
        prev_l = final_l[i - 1]
        final_u[i] = basic_u[i] if basic_u[i] < prev_u or close[i - 1] > prev_u else prev_u
        final_l[i] = basic_l[i] if basic_l[i] > prev_l or close[i - 1] < prev_l else prev_l
        prev_dir = direction[i - 1]
        if prev_dir < 0 and close[i] > final_u[i]:
            direction[i] = 1.0
        elif prev_dir > 0 and close[i] < final_l[i]:
            direction[i] = -1.0
        else:
            direction[i] = prev_dir
        st[i] = final_l[i] if direction[i] > 0 else final_u[i]

    return pd.Series(st, index=df.index), pd.Series(direction, index=df.index)


def crossover(a: pd.Series, b: pd.Series | float) -> pd.Series:
    bs = b if isinstance(b, pd.Series) else pd.Series(float(b), index=a.index)
    return (a > bs) & (a.shift(1) <= bs.shift(1))


def crossunder(a: pd.Series, b: pd.Series | float) -> pd.Series:
    bs = b if isinstance(b, pd.Series) else pd.Series(float(b), index=a.index)
    return (a < bs) & (a.shift(1) >= bs.shift(1))
