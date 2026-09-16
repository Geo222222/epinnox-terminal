from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "config" / "settings.json"
LAST_KNOWN_GOOD_PATH = ROOT / "data" / "settings.last-known-good.json"

FALLBACK_SETTINGS: dict[str, Any] = {
    "schema_version": 1,
    "terminal": {
        "default_symbol": "ETH/USDT:USDT",
        "default_timeframe": "5m",
        "default_mode": "BACKTEST",
        "default_backtest_profile": "TradingView Parity",
        "default_strategy": "Supertrend",
        "default_confirmation_policy": "Single",
    },
    "account_defaults": {"starting_balance": 100000.0,"leverage": 1.0,"allocation_pct": 5.0,"pyramiding": 1,"direction": "Both"},
    "economics_defaults": {"entry_fee_pct": 0.05,"exit_fee_pct": 0.05,"extra_cost_pct": 0.0,"desired_net_profit_pct": 0.01,"referral_share_pct": 30.0,"maintenance_margin_pct": 0.4},
    "backtest_defaults": {"history_bars": 1000,"max_range_bars": 50000,"funding_bps_per_8h": 0.0},
    "scanner_defaults": {"symbols": ["ETH/USDT:USDT", "BTC/USDT:USDT", "SOL/USDT:USDT"],"timeframes": ["1m", "5m"],"strategies": ["Supertrend", "Stochastic Reversal", "EMA Crossover", "Bollinger Mean Reversion"],"objective": "Capital Growth","history_bars": 2000,"target_buffers_pct": [0.0,0.005,0.01,0.02,0.04,0.08],"walk_forward_windows": 4,"min_sample_trades": 20,"min_walk_forward_pass_rate_pct": 60.0,"max_drawdown_pct": 5.0,"min_net_expectancy_usdt": 0.0},
    "features": {"paper_recovery": True,"named_presets": True,"workspace_persistence": True,"opportunity_scanner": True,"adaptive_target_model": False,"live_execution": False,"account_context_selector": True,"chart_drawing_toolkit": True},
    "specials": {},
}

def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out=deepcopy(base)
    for key,value in override.items():
        out[key]=_merge(out[key],value) if isinstance(value,dict) and isinstance(out.get(key),dict) else value
    return out

def _read_valid(path: Path) -> dict[str, Any] | None:
    try: raw=json.loads(path.read_text(encoding="utf-8"))
    except Exception: return None
    if not isinstance(raw,dict) or raw.get("schema_version")!=1: return None
    return _merge(FALLBACK_SETTINGS,raw)

def load_settings() -> dict[str, Any]:
    current=_read_valid(SETTINGS_PATH) if SETTINGS_PATH.exists() else None
    if current is not None:
        try:
            LAST_KNOWN_GOOD_PATH.parent.mkdir(parents=True,exist_ok=True)
            LAST_KNOWN_GOOD_PATH.write_text(json.dumps(current,indent=2,sort_keys=True),encoding="utf-8")
        except Exception: pass
        return current
    previous=_read_valid(LAST_KNOWN_GOOD_PATH) if LAST_KNOWN_GOOD_PATH.exists() else None
    return previous if previous is not None else deepcopy(FALLBACK_SETTINGS)

def public_settings() -> dict[str, Any]:
    return load_settings()
