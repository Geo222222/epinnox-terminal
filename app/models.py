from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator


class Candle(BaseModel):
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


Timeframe = Literal[
    "1m", "5m", "15m", "30m", "1h", "2h", "3h", "4h", "5h", "8h", "1d", "5d", "1w", "1M"
]

ConfirmationPolicy = Literal[
    "Single",
    "All Recent Events",
    "Quorum Recent Events",
    "Primary + All States",
]

BacktestProfile = Literal[
    "TradingView Parity",
    "Simplified Isolated",
]


class BacktestRequest(BaseModel):
    symbol: str = "ETH/USDT:USDT"
    timeframe: Timeframe = "1m"
    strategy: str = "Supertrend"
    confirmations: list[str] = Field(default_factory=list, max_length=8)
    confirmation_policy: ConfirmationPolicy = "Single"
    confirmation_required: int = Field(2, ge=1, le=9)
    confirmation_window_bars: int = Field(1, ge=1, le=100)
    limit: int = Field(1000, ge=100, le=50000)
    start_ts_ms: int | None = None
    end_ts_ms: int | None = None
    backtest_profile: BacktestProfile = "TradingView Parity"
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

    @model_validator(mode="after")
    def normalize_confirmation_model(self):
        self.confirmations = [x for x in self.confirmations if x and x != self.strategy]
        if self.confirmation_policy == "Single":
            self.confirmations = []
        selected = 1 + len(self.confirmations)
        if self.confirmation_policy == "Quorum Recent Events" and self.confirmation_required > selected:
            raise ValueError("confirmation_required cannot exceed the number of selected strategies")
        if self.start_ts_ms is not None and self.end_ts_ms is not None and self.start_ts_ms >= self.end_ts_ms:
            raise ValueError("start_ts_ms must be before end_ts_ms")
        return self


class PaperLiveStartRequest(BaseModel):
    account_id: str = Field(..., min_length=1, max_length=200)
    name: str | None = Field(None, max_length=80)
    strategy: BacktestRequest


ScannerObjective = Literal["Capital Growth", "Break-Even Throughput"]


class ScannerRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["ETH/USDT:USDT", "BTC/USDT:USDT", "SOL/USDT:USDT"], min_length=1, max_length=12)
    timeframes: list[Literal["1m", "5m", "15m", "30m"]] = Field(default_factory=lambda: ["1m", "5m"], min_length=1, max_length=4)
    strategies: list[str] = Field(default_factory=lambda: ["Supertrend", "Stochastic Reversal", "EMA Crossover", "Bollinger Mean Reversion"], min_length=1, max_length=15)
    objective: ScannerObjective = "Capital Growth"
    history_bars: int = Field(2000, ge=600, le=10000)
    target_buffers_pct: list[float] = Field(default_factory=lambda: [0.0, 0.005, 0.01, 0.02, 0.04, 0.08], min_length=1, max_length=12)
    walk_forward_windows: int = Field(4, ge=2, le=8)
    min_sample_trades: int = Field(20, ge=1, le=10000)
    min_walk_forward_pass_rate_pct: float = Field(60.0, ge=0, le=100)
    max_drawdown_pct: float = Field(5.0, gt=0, le=100)
    min_net_expectancy_usdt: float = Field(0.0, ge=-1000000, le=1000000)
    holdout_fraction: float = Field(0.25, ge=0.10, le=0.50)
    min_holdout_trades: int = Field(5, ge=1, le=10000)
    min_holdout_expectancy_usdt: float = Field(0.0, ge=-1000000, le=1000000)
    starting_balance: float = Field(100000.0, gt=0)
    leverage: float = Field(1.0, ge=1, le=200)
    allocation_pct: float = Field(5.0, gt=0, le=100)
    pyramiding: int = Field(1, ge=1, le=20)
    direction: Literal["Both", "Long Only", "Short Only"] = "Both"
    entry_fee_pct: float = Field(0.05, ge=0, le=5)
    exit_fee_pct: float = Field(0.05, ge=0, le=5)
    extra_cost_pct: float = Field(0.0, ge=0, le=5)
    referral_share_pct: float = Field(30.0, ge=0, le=100)
    maintenance_margin_pct: float = Field(0.4, ge=0, le=20)
    stop_loss_pct: float | None = Field(None, gt=0, le=99)
    max_bars_in_trade: int | None = Field(None, ge=1, le=100000)
    backtest_profile: BacktestProfile = "TradingView Parity"

    @model_validator(mode="after")
    def validate_scan(self):
        self.symbols = list(dict.fromkeys(x for x in self.symbols if x))
        self.timeframes = list(dict.fromkeys(self.timeframes))
        self.strategies = list(dict.fromkeys(x for x in self.strategies if x))
        self.target_buffers_pct = sorted(set(round(float(x), 6) for x in self.target_buffers_pct if x >= 0))
        if not self.symbols or not self.timeframes or not self.strategies or not self.target_buffers_pct:
            raise ValueError("scanner requires at least one symbol, timeframe, strategy, and target")
        evaluations = len(self.symbols) * len(self.timeframes) * len(self.strategies) * len(self.target_buffers_pct)
        estimated_simulations = evaluations * (2 + self.walk_forward_windows)
        if evaluations > 1200 or estimated_simulations > 6000:
            raise ValueError(
                "scanner request is too large; reduce symbols/timeframes/strategies/targets or validation windows "
                "so estimated simulations stay at or below 6000"
            )
        calibration_bars = int(self.history_bars * (1.0 - self.holdout_fraction))
        if calibration_bars < self.walk_forward_windows * 100:
            raise ValueError("scanner calibration segment is too small for the requested walk-forward windows")
        holdout_bars = self.history_bars - calibration_bars
        if holdout_bars < 100:
            raise ValueError("scanner holdout segment must contain at least 100 bars")
        return self


class MarketResponse(BaseModel):
    symbol: str
    timeframe: str
    candles: list[Candle]
    source: str
