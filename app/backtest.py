from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median
import numpy as np
import pandas as pd

from .models import BacktestRequest
from .strategies import build_strategy


@dataclass
class Layer:
    ts_ms: int
    price: float
    qty: float
    fee: float


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
    def __init__(self, df: pd.DataFrame, req: BacktestRequest):
        self.df = df.reset_index(drop=True)
        self.req = req
        self.logic = build_strategy(self.df, req.strategy, req.timeframe, req.manual_params)
        self.cash = req.starting_balance
        self.equity_peak = req.starting_balance
        self.max_drawdown = 0.0
        self.position: Position | None = None
        self.closed: list[dict] = []
        self.markers: list[dict] = []
        self.equity_curve: list[dict] = []
        self.open_snapshot: dict | None = None

    def _rates(self):
        return self.req.entry_fee_pct/100, self.req.exit_fee_pct/100, self.req.extra_cost_pct/100, self.req.desired_net_profit_pct/100

    def _target(self, p: Position) -> tuple[float, float]:
        entry_r, exit_r, extra_r, profit_r = self._rates()
        avg = p.avg
        if p.side == "long":
            be = avg * (1 + entry_r + extra_r) / max(1e-12, 1-exit_r)
            target = avg * (1 + entry_r + extra_r + profit_r) / max(1e-12, 1-exit_r)
        else:
            be = avg * (1 - entry_r - extra_r) / (1+exit_r)
            target = avg * (1 - entry_r - extra_r - profit_r) / (1+exit_r)
        return be, target

    def _liq(self, p: Position) -> float:
        # PAPER approximation only; live HTX liquidation must come from venue state.
        mm = self.req.maintenance_margin_pct / 100.0
        if p.side == "long":
            return max(0.0, p.avg * (1 - 1/self.req.leverage + mm))
        return p.avg * (1 + 1/self.req.leverage - mm)

    def _layer_notional(self, equity: float) -> float:
        return max(0.0, equity * self.req.leverage * (self.req.allocation_pct / 100.0))

    def _open_or_add(self, i: int, side: str, price: float):
        if self.position and self.position.side != side:
            return
        if self.position and len(self.position.layers) >= self.req.pyramiding:
            return
        equity = self._mark_equity(price)
        notional = self._layer_notional(equity)
        qty = notional / price if price > 0 else 0
        fee = notional * (self.req.entry_fee_pct/100)
        margin = notional / self.req.leverage
        if qty <= 0 or margin + fee > self.cash:
            return
        self.cash -= fee
        if not self.position:
            self.position = Position(side=side, entry_bar=i)
        self.position.layers.append(Layer(int(self.df.ts_ms.iloc[i]), price, qty, fee))
        self.markers.append({"ts_ms": int(self.df.ts_ms.iloc[i]), "price": price, "kind": "entry", "side": side, "text": f"{side.upper()} #{len(self.position.layers)}"})

    def _mark_equity(self, price: float) -> float:
        if not self.position:
            return self.cash
        p = self.position
        gross = (price-p.avg)*p.qty if p.side == "long" else (p.avg-price)*p.qty
        return self.cash + gross - p.funding

    def _close(self, i: int, price: float, reason: str):
        p = self.position
        if not p:
            return
        exit_notional = p.qty * price
        exit_fee = exit_notional * (self.req.exit_fee_pct/100)
        gross = (price-p.avg)*p.qty if p.side == "long" else (p.avg-price)*p.qty
        net = gross - p.entry_fees - exit_fee - p.funding
        # Entry fees were already debited from cash; realize gross and remaining close costs now.
        self.cash += gross - exit_fee - p.funding
        total_fee = p.entry_fees + exit_fee
        referral = total_fee * self.req.referral_share_pct/100
        bars = i - p.entry_bar
        trade = {
            "trade": len(self.closed)+1,
            "side": p.side,
            "entry_ts_ms": p.layers[0].ts_ms,
            "exit_ts_ms": int(self.df.ts_ms.iloc[i]),
            "entry_price": p.avg,
            "exit_price": price,
            "qty": p.qty,
            "layers": len(p.layers),
            "leverage": self.req.leverage,
            "margin": p.basis/self.req.leverage,
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
        }
        self.closed.append(trade)
        self.markers.append({"ts_ms": int(self.df.ts_ms.iloc[i]), "price": price, "kind": "exit", "side": p.side, "text": f"EXIT {reason}"})
        self.position = None

    def run(self) -> dict:
        tf_ms = {"1m":60000,"5m":300000,"15m":900000,"30m":1800000}[self.req.timeframe]
        funding_rate_per_ms = (self.req.funding_bps_per_8h/10000.0) / (8*60*60*1000)
        for i, row in self.df.iterrows():
            c = float(row.close)
            if self.position:
                p = self.position
                # Funding accrues on notional through elapsed bar time.
                p.funding += p.basis * funding_rate_per_ms * tf_ms
                adverse = ((p.avg-row.low)/p.avg*100) if p.side == "long" else ((row.high-p.avg)/p.avg*100)
                favorable = ((row.high-p.avg)/p.avg*100) if p.side == "long" else ((p.avg-row.low)/p.avg*100)
                p.mae_pct = max(p.mae_pct, float(adverse))
                p.mfe_pct = max(p.mfe_pct, float(favorable))
                be, target = self._target(p)
                liq = self._liq(p)
                liquidated = (p.side == "long" and row.low <= liq) or (p.side == "short" and row.high >= liq)
                stop_hit = False
                stop_price = None
                if self.req.stop_loss_pct:
                    x = self.req.stop_loss_pct/100
                    stop_price = p.avg*(1-x) if p.side == "long" else p.avg*(1+x)
                    stop_hit = (p.side == "long" and row.low <= stop_price) or (p.side == "short" and row.high >= stop_price)
                target_hit = (p.side == "long" and row.high >= target) or (p.side == "short" and row.low <= target)
                timed_out = self.req.max_bars_in_trade is not None and i-p.entry_bar >= self.req.max_bars_in_trade
                # Conservative intrabar precedence: liquidation/stop before profit when both occur in one OHLC bar.
                if liquidated:
                    self._close(i, liq, "liquidation")
                elif stop_hit and stop_price is not None:
                    self._close(i, stop_price, "stop")
                elif target_hit:
                    self._close(i, target, "target")
                elif timed_out:
                    self._close(i, c, "timeout")

            allow_long = self.req.direction in {"Both","Long Only"}
            allow_short = self.req.direction in {"Both","Short Only"}
            if self.position is None:
                if allow_long and bool(self.logic["long"].iloc[i]): self._open_or_add(i, "long", c)
                elif allow_short and bool(self.logic["short"].iloc[i]): self._open_or_add(i, "short", c)
            else:
                # Same-direction signal-qualified pyramiding.
                if self.position.side == "long" and allow_long and bool(self.logic["long"].iloc[i]): self._open_or_add(i, "long", c)
                elif self.position.side == "short" and allow_short and bool(self.logic["short"].iloc[i]): self._open_or_add(i, "short", c)

            eq = self._mark_equity(c)
            self.equity_peak = max(self.equity_peak, eq)
            dd = 0 if self.equity_peak <= 0 else (self.equity_peak-eq)/self.equity_peak*100
            self.max_drawdown = max(self.max_drawdown, dd)
            self.equity_curve.append({"ts_ms": int(row.ts_ms), "equity": eq})

        if self.position:
            p = self.position
            be, target = self._target(p)
            last = float(self.df.close.iloc[-1])
            self.open_snapshot = {"side":p.side,"avg_entry":p.avg,"qty":p.qty,"layers":len(p.layers),"break_even":be,"profit_target":target,"liquidation":self._liq(p),"open_pnl":self._mark_equity(last)-self.cash,"mae_pct":p.mae_pct,"mfe_pct":p.mfe_pct,"bars_held":len(self.df)-1-p.entry_bar}

        return self._result()

    def _result(self):
        wins = [t for t in self.closed if t["net_pnl"] > 0]
        losses = [t for t in self.closed if t["net_pnl"] < 0]
        gross_win = sum(t["net_pnl"] for t in wins)
        gross_loss = abs(sum(t["net_pnl"] for t in losses))
        total_fees = sum(t["total_fee"] for t in self.closed)
        referral = sum(t["referral_commission"] for t in self.closed)
        target_hits = sum(t["exit_reason"] == "target" for t in self.closed)
        days = max(1.0, (self.df.ts_ms.iloc[-1]-self.df.ts_ms.iloc[0])/(86400000)) if len(self.df)>1 else 1.0
        net_closed = sum(t["net_pnl"] for t in self.closed)
        last_eq = self.equity_curve[-1]["equity"] if self.equity_curve else self.req.starting_balance
        metrics = {
            "closed_trades": len(self.closed),
            "net_pnl_closed": net_closed,
            "total_equity_pnl": last_eq-self.req.starting_balance,
            "open_pnl": 0.0 if not self.open_snapshot else self.open_snapshot["open_pnl"],
            "win_rate_pct": (100*len(wins)/len(self.closed)) if self.closed else 0.0,
            "profit_factor": (gross_win/gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0),
            "max_drawdown_pct": self.max_drawdown,
            "target_hit_rate_pct": (100*target_hits/len(self.closed)) if self.closed else 0.0,
            "median_bars_to_exit": median([t["bars_held"] for t in self.closed]) if self.closed else 0,
            "fees_paid": total_fees,
            "referral_revenue": referral,
            "trades_per_day": len(self.closed)/days,
            "referral_revenue_per_day": referral/days,
        }
        def serial(series):
            out=[]
            for idx,v in series.items():
                if pd.notna(v): out.append({"ts_ms":int(self.df.ts_ms.iloc[idx]),"value":float(v)})
            return out
        return {
            "symbol": self.req.symbol,"timeframe":self.req.timeframe,"strategy":self.req.strategy,"params":self.logic["params"],
            "metrics":metrics,"trades":self.closed,"markers":self.markers,"equity_curve":self.equity_curve,"open_position":self.open_snapshot,
            "overlays":{k:serial(v) for k,v in self.logic["overlays"].items()},"panes":{k:serial(v) for k,v in self.logic["panes"].items()},
        }


def run_backtest(candles: list[dict], req: BacktestRequest) -> dict:
    df = pd.DataFrame(candles)
    if df.empty:
        raise ValueError("No candles")
    return Backtester(df, req).run()
