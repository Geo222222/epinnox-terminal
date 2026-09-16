from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class Candle(BaseModel):
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class BacktestRequest(BaseModel):
    symbol: str = "ETH/USDT:USDT"
    timeframe: Literal["1m", "5m", "15m", "30m"] = "1m"
    strategy: str = "Supertrend"
    limit: int = Field(1000, ge=100, le=5000)
    starting_balance: float = Field(100000.0, gt=0)
    leverage: float = Field(1.0, ge=1, le=200)
    allocation_pct: float = Field(5.0, gt=0, le=100)
    pyramiding: int = Field(1, ge=1, le=20)
    direction: Literal["Both", "Long Only", "Short Only"] = "Both"
    entry_fee_pct: float = Field(0.05, ge=0, le=5)
    exit_fee_pct: float = Field(0.05, ge=0, le=5)
    extra_cost_pct: float = Field(0.0, ge=0, le=5)
    desired_net_profit_pct: float = Field(0.01, ge=0, le=20)
    referral_share_pct: float = Field(30.0, ge=0, le=100)
    maintenance_margin_pct: float = Field(0.4, ge=0, le=20)
    max_bars_in_trade: int | None = Field(None, ge=1, le=100000)
    stop_loss_pct: float | None = Field(None, gt=0, le=99)
    funding_bps_per_8h: float = Field(0.0, ge=-1000, le=1000)
    manual_params: dict[str, float | int] | None = None


class MarketResponse(BaseModel):
    symbol: str
    timeframe: str
    candles: list[Candle]
    source: str
