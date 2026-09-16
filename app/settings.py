from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "config" / "settings.json"

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
    "account_defaults": {
        "starting_balance": 100000.0,
        "leverage": 1.0,
        "allocation_pct": 5.0,
        "pyramiding": 1,
        "direction": "Both",
    },
    "economics_defaults": {
        "entry_fee_pct": 0.05,
        "exit_fee_pct": 0.05,
        "extra_cost_pct": 0.0,
        "desired_net_profit_pct": 0.01,
        "referral_share_pct": 30.0,
        "maintenance_margin_pct": 0.4,
    },
    "backtest_defaults": {
        "history_bars": 1000,
        "max_range_bars": 50000,
        "funding_bps_per_8h": 0.0,
    },
    "features": {
        "paper_recovery": True,
        "named_presets": True,
        "workspace_persistence": True,
        "live_execution": False,
    },
    "specials": {},
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return deepcopy(FALLBACK_SETTINGS)
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(FALLBACK_SETTINGS)
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        return deepcopy(FALLBACK_SETTINGS)
    return _merge(FALLBACK_SETTINGS, raw)


def public_settings() -> dict[str, Any]:
    return load_settings()
