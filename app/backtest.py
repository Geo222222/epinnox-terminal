from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

import numpy as np
import pandas as pd

from .economics import fee_aware_exit_levels
from .market import timeframe_ms
from .models import BacktestRequest
from .strategies import build_entry_model, entry_receipt


@dataclass
class Layer:
    ts_ms: int
    price: float
    qty: float
    fee: float
    receipt: list[dict] = field(default_factory=list)


@dataclass
class Position:
    side: str
    layers: list[Layer] = field(default_factory=list)
    entry_bar: int = 0
    mae_pct: float = 0.0
    mfe_pct: float = 0.0
    funding: float = 0.0

    @property
    def qty(self) -> float:
        return sum(x.qty for x in self.layers)

    @property
    def basis(self) -> float:
        return sum(x.qty * x.price for x in self.layers)

    @property
    def avg(self) -> float:
        return self.basis / self.qty if self.qty else 0.0

    @property
    def entry_fees(self) -> float:
        return sum(x.fee for x in self.layers)


class Backtester:
    """Sequential OHLC replay with Pine-style entry timing and auditable exits."""

    def __init__(self, df: pd.DataFrame, req: BacktestRequest):
        self.df = df.reset_index(drop=True)
        self.req = req
        self.logic = build_entry_model(
            self.df,
            req.strategy,
            req.timeframe,
            req.manual_params,
            req.confirmations,
            req.confirmation_policy,
            req.confirmation_required,
            req.confirmation_window_bars,
        )
        # The sequential simulator must preserve bar order, but it does not need
        # pandas Series/row objects in the hot loop. Keep contiguous numeric
        # arrays beside the DataFrame used by indicator/receipt rendering.
        self.ts = self.df["ts_ms"].to_numpy(dtype=np.int64, copy=False)
        self.high = self.df["high"].to_numpy(dtype=np.float64, copy=False)
        self.low = self.df["low"].to_numpy(dtype=np.float64, copy=False)
        self.close = self.df["close"].to_numpy(dtype=np.float64, copy=False)
        self.long_signal = self.logic["long"].to_numpy(dtype=bool, copy=False)
        self.short_signal = self.logic["short"].to_numpy(dtype=bool, copy=False)

        self.cash = req.starting_balance
        self.equity_peak = req.starting_balance
        self.max_drawdown = 0.0
        self.position: Position | None = None
        self.closed: list[dict] = []
        self.markers: list[dict] = []
        self.equity_curve: list[dict] = []
        self.open_snapshot: dict | None = None

    @property
    def parity_mode(self) -> bool:
        return self.req.backtest_profile == "TradingView Parity"

    @property
    def liquidation_enabled(self) -> bool:
        return self.req.backtest_profile == "Simplified Isolated"

    def _target(self, p: Position) -> tuple[float, float]:
        levels = fee_aware_exit_levels(
            p.avg,
            p.side,
            entry_fee_pct=self.req.entry_fee_pct,
            exit_fee_pct=self.req.exit_fee_pct,
            extra_cost_pct=self.req.extra_cost_pct,
            desired_net_profit_pct=self.req.desired_net_profit_pct,
        )
        return levels.break_even, levels.target

    def _liq(self, p: Position) -> float | None:
        if not self.liquidation_enabled:
            return None
        mm = self.req.maintenance_margin_pct / 100.0
        if p.side == "long":
            return max(0.0, p.avg * (1 - 1 / self.req.leverage + mm))
        return p.avg * (1 + 1 / self.req.leverage - mm)

    def _liquidation_receipt(self, p: Position, high: float, low: float, liq: float) -> dict:
        adverse_extreme = low if p.side == "long" else high
        distance_pct = abs(liq - p.avg) / p.avg * 100.0 if p.avg else 0.0
        return {
            "model": "Simplified isolated estimate",
            "entry_price": p.avg,
            "leverage": self.req.leverage,
            "maintenance_margin_pct": self.req.maintenance_margin_pct,
            "estimated_liquidation_price": liq,
            "candle_low": low,
            "candle_high": high,
            "adverse_extreme": adverse_extreme,
            "distance_from_entry_pct": distance_pct,
            "note": "Research approximation only; not an authoritative HTX liquidation price.",
        }

    def _layer_notional(self, equity: float) -> float:
        return max(0.0, equity * self.req.leverage * (self.req.allocation_pct / 100.0))

    def _used_margin(self) -> float:
        if not self.position:
            return 0.0
        return self.position.basis / self.req.leverage

    def _open_or_add(self, i: int, side: str, price: float) -> None:
        if self.position and self.position.side != side:
            return
        if self.position and len(self.position.layers) >= self.req.pyramiding:
            return
        equity = self._mark_equity(price)
        notional = self._layer_notional(equity)
        qty = notional / price if price > 0 else 0.0
        fee = notional * (self.req.entry_fee_pct / 100.0)
        margin = notional / self.req.leverage
        free_collateral = max(0.0, self.cash - self._used_margin())
        if qty <= 0 or margin + fee > free_collateral:
            return
        self.cash -= fee
        if not self.position:
            self.position = Position(side=side, entry_bar=i)
        receipt = entry_receipt(self.logic, i, side)
        self.position.layers.append(Layer(int(self.ts[i]), price, qty, fee, receipt))
        matched = sum(1 for x in receipt if x["matched"])
        self.markers.append(
            {
                "ts_ms": int(self.ts[i]),
                "price": price,
                "kind": "entry",
                "side": side,
                "text": f"{side.upper()} #{len(self.position.layers)} · {matched}/{len(receipt)}",
                "receipt": receipt,
            }
        )

    def _mark_equity(self, price: float) -> float:
        if not self.position:
            return self.cash
        p = self.position
        gross = (price - p.avg) * p.qty if p.side == "long" else (p.avg - price) * p.qty
        return self.cash + gross - p.funding

    def _close(self, i: int, price: float, reason: str, exit_receipt: dict | None = None) -> None:
        p = self.position
        if not p:
            return
        exit_notional = p.qty * price
        exit_fee = exit_notional * (self.req.exit_fee_pct / 100.0)
        gross = (price - p.avg) * p.qty if p.side == "long" else (p.avg - price) * p.qty
        net = gross - p.entry_fees - exit_fee - p.funding
        self.cash += gross - exit_fee - p.funding
        total_fee = p.entry_fees + exit_fee
        referral = total_fee * self.req.referral_share_pct / 100.0
        bars = i - p.entry_bar
        receipts = [layer.receipt for layer in p.layers]
        self.closed.append(
            {
                "trade": len(self.closed) + 1,
                "side": p.side,
                "entry_ts_ms": p.layers[0].ts_ms,
                "exit_ts_ms": int(self.ts[i]),
                "entry_price": p.avg,
                "exit_price": price,
                "qty": p.qty,
                "layers": len(p.layers),
                "leverage": self.req.leverage,
                "margin": p.basis / self.req.leverage,
                "entry_fee": p.entry_fees,
                "exit_fee": exit_fee,
                "total_fee": total_fee,
                "referral_commission": referral,
                "funding": p.funding,
                "gross_pnl": gross,
                "net_pnl": net,
                "mae_pct": p.mae_pct,
                "mfe_pct": p.mfe_pct,
                "bars_held": bars,
                "exit_reason": reason,
                "exit_receipt": exit_receipt,
                "entry_confirmation": receipts[0] if receipts else [],
                "layer_confirmations": receipts,
            }
        )
        self.markers.append(
            {
                "ts_ms": int(self.ts[i]),
                "price": price,
                "kind": "exit",
                "side": p.side,
                "text": f"EXIT {reason}",
            }
        )
        self.position = None

    def run(self) -> dict:
        tf_ms = timeframe_ms(self.req.timeframe)
        funding_bps = 0.0 if self.parity_mode else self.req.funding_bps_per_8h
        funding_rate_per_ms = (funding_bps / 10_000.0) / (8 * 60 * 60 * 1000)
        allow_long = self.req.direction in {"Both", "Long Only"}
        allow_short = self.req.direction in {"Both", "Short Only"}

        for i in range(len(self.ts)):
            close = float(self.close[i])
            high = float(self.high[i])
            low = float(self.low[i])

            if self.position:
                p = self.position
                p.funding += p.basis * funding_rate_per_ms * tf_ms
                adverse = ((p.avg - low) / p.avg * 100) if p.side == "long" else ((high - p.avg) / p.avg * 100)
                favorable = ((high - p.avg) / p.avg * 100) if p.side == "long" else ((p.avg - low) / p.avg * 100)
                p.mae_pct = max(p.mae_pct, adverse)
                p.mfe_pct = max(p.mfe_pct, favorable)
                _, target = self._target(p)
                liq = self._liq(p)
                liquidated = bool(liq is not None and ((p.side == "long" and low <= liq) or (p.side == "short" and high >= liq)))

                stop_hit = False
                stop_price = None
                if self.req.stop_loss_pct:
                    x = self.req.stop_loss_pct / 100.0
                    stop_price = p.avg * (1 - x) if p.side == "long" else p.avg * (1 + x)
                    stop_hit = (p.side == "long" and low <= stop_price) or (p.side == "short" and high >= stop_price)

                target_hit = (p.side == "long" and high >= target) or (p.side == "short" and low <= target)
                timed_out = self.req.max_bars_in_trade is not None and i - p.entry_bar >= self.req.max_bars_in_trade

                if liquidated and liq is not None:
                    self._close(i, liq, "liquidation", self._liquidation_receipt(p, high, low, liq))
                elif stop_hit and stop_price is not None:
                    self._close(i, stop_price, "stop")
                elif target_hit:
                    self._close(i, target, "target")
                elif timed_out:
                    self._close(i, close, "timeout")

            if self.position is None:
                if allow_long and self.long_signal[i]:
                    self._open_or_add(i, "long", close)
                elif allow_short and self.short_signal[i]:
                    self._open_or_add(i, "short", close)
            else:
                if self.position.side == "long" and allow_long and self.long_signal[i]:
                    self._open_or_add(i, "long", close)
                elif self.position.side == "short" and allow_short and self.short_signal[i]:
                    self._open_or_add(i, "short", close)

            equity = self._mark_equity(close)
            self.equity_peak = max(self.equity_peak, equity)
            drawdown = 0.0 if self.equity_peak <= 0 else (self.equity_peak - equity) / self.equity_peak * 100.0
            self.max_drawdown = max(self.max_drawdown, drawdown)
            self.equity_curve.append({"ts_ms": int(self.ts[i]), "equity": equity})

        if self.position:
            p = self.position
            be, target = self._target(p)
            last = float(self.close[-1])
            self.open_snapshot = {
                "side": p.side,
                "avg_entry": p.avg,
                "qty": p.qty,
                "layers": len(p.layers),
                "break_even": be,
                "profit_target": target,
                "liquidation": self._liq(p),
                "liquidation_model": "disabled" if not self.liquidation_enabled else "Simplified isolated estimate",
                "open_pnl": self._mark_equity(last) - self.cash,
                "mae_pct": p.mae_pct,
                "mfe_pct": p.mfe_pct,
                "bars_held": len(self.ts) - 1 - p.entry_bar,
                "used_margin": self._used_margin(),
                "free_collateral": max(0.0, self.cash - self._used_margin()),
                "entry_confirmation": p.layers[0].receipt if p.layers else [],
            }

        return self._result()

    def _result(self) -> dict:
        wins = [t for t in self.closed if t["net_pnl"] > 0]
        losses = [t for t in self.closed if t["net_pnl"] < 0]
        gross_win = sum(t["net_pnl"] for t in wins)
        gross_loss = abs(sum(t["net_pnl"] for t in losses))
        total_fees = sum(t["total_fee"] for t in self.closed)
        referral = sum(t["referral_commission"] for t in self.closed)
        target_hits = sum(t["exit_reason"] == "target" for t in self.closed)
        liquidation_exits = sum(t["exit_reason"] == "liquidation" for t in self.closed)
        days = max(1.0, (self.ts[-1] - self.ts[0]) / 86_400_000) if len(self.ts) > 1 else 1.0
        net_closed = sum(t["net_pnl"] for t in self.closed)
        last_eq = self.equity_curve[-1]["equity"] if self.equity_curve else self.req.starting_balance
        profit_factor = gross_win / gross_loss if gross_loss > 0 else None

        metrics = {
            "closed_trades": len(self.closed),
            "net_pnl_closed": net_closed,
            "total_equity_pnl": last_eq - self.req.starting_balance,
            "open_pnl": 0.0 if not self.open_snapshot else self.open_snapshot["open_pnl"],
            "win_rate_pct": (100 * len(wins) / len(self.closed)) if self.closed else 0.0,
            "profit_factor": profit_factor,
            "max_drawdown_pct": self.max_drawdown,
            "target_hit_rate_pct": (100 * target_hits / len(self.closed)) if self.closed else 0.0,
            "median_bars_to_exit": median([t["bars_held"] for t in self.closed]) if self.closed else 0,
            "fees_paid": total_fees,
            "referral_revenue": referral,
            "trades_per_day": len(self.closed) / days,
            "referral_revenue_per_day": referral / days,
            "liquidation_exits": liquidation_exits,
        }

        def serial(series: pd.Series) -> list[dict]:
            values = series.to_numpy(copy=False)
            mask = pd.notna(values)
            indexes = np.flatnonzero(mask)
            return [{"ts_ms": int(self.ts[i]), "value": float(values[i])} for i in indexes]

        model_label = self.req.strategy if self.req.confirmation_policy == "Single" else f"{self.req.strategy} + {' + '.join(self.req.confirmations)}"
        return {
            "symbol": self.req.symbol,
            "timeframe": self.req.timeframe,
            "strategy": self.req.strategy,
            "backtest_profile": self.req.backtest_profile,
            "backtest_window": {
                "start_ts_ms": int(self.ts[0]),
                "end_ts_ms": int(self.ts[-1]),
                "candles": len(self.ts),
            },
            "simulation": {
                "liquidation_enabled": self.liquidation_enabled,
                "liquidation_model": "Simplified isolated estimate" if self.liquidation_enabled else "Disabled for TradingView parity",
                "funding_bps_per_8h_effective": 0.0 if self.parity_mode else self.req.funding_bps_per_8h,
                "entry_timing": "signal evaluated on bar close; entry filled at that close",
                "exit_timing": "existing positions evaluate candle high/low before new close entries",
            },
            "entry_model": {
                "label": model_label,
                "primary": self.req.strategy,
                "confirmations": self.req.confirmations,
                "policy": self.req.confirmation_policy,
                "required": self.req.confirmation_required,
                "window_bars": self.req.confirmation_window_bars,
            },
            "params": self.logic["params"],
            "metrics": metrics,
            "trades": self.closed,
            "markers": self.markers,
            "equity_curve": self.equity_curve,
            "open_position": self.open_snapshot,
            "overlays": {k: serial(v) for k, v in self.logic["overlays"].items()},
            "panes": {k: serial(v) for k, v in self.logic["panes"].items()},
        }


def run_backtest(candles: list[dict], req: BacktestRequest) -> dict:
    df = pd.DataFrame(candles)
    if df.empty:
        raise ValueError("No candles")
    required = {"ts_ms", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing candle fields: {sorted(missing)}")
    return Backtester(df, req).run()
