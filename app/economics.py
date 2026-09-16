from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExitLevels:
    break_even: float
    target: float


def fee_aware_exit_levels(
    avg_entry: float,
    side: str,
    *,
    entry_fee_pct: float,
    exit_fee_pct: float,
    extra_cost_pct: float,
    desired_net_profit_pct: float,
) -> ExitLevels:
    """Return deterministic break-even and target levels for a filled position."""
    entry_r = entry_fee_pct / 100.0
    exit_r = exit_fee_pct / 100.0
    extra_r = extra_cost_pct / 100.0
    profit_r = desired_net_profit_pct / 100.0
    if side == "long":
        be = avg_entry * (1 + entry_r + extra_r) / max(1e-12, 1 - exit_r)
        target = avg_entry * (1 + entry_r + extra_r + profit_r) / max(1e-12, 1 - exit_r)
    elif side == "short":
        be = avg_entry * (1 - entry_r - extra_r) / (1 + exit_r)
        target = avg_entry * (1 - entry_r - extra_r - profit_r) / (1 + exit_r)
    else:
        raise ValueError(f"Unsupported side: {side}")
    return ExitLevels(break_even=be, target=target)
