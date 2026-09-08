"""Pure calculation helpers – no Home Assistant dependency."""

from __future__ import annotations

from datetime import datetime


def get_cycle_bounds(billing_day: int, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return (cycle_start, cycle_end) for the current billing period."""
    if now is None:
        now = datetime.now()
    if now.day >= billing_day:
        start = now.replace(day=billing_day, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    else:
        if now.month == 1:
            start = now.replace(
                year=now.year - 1, month=12, day=billing_day, hour=0, minute=0, second=0, microsecond=0
            )
        else:
            start = now.replace(
                month=now.month - 1, day=billing_day, hour=0, minute=0, second=0, microsecond=0
            )
        end = now.replace(day=billing_day, hour=0, minute=0, second=0, microsecond=0)
    return start, end


def calc_tiered_cost(consumption: float, tiers: list[dict]) -> tuple[float, float, str]:
    """
    Calculate cost for given consumption under increasing-block tiers.
    Returns (total_cost, marginal_rate, current_tier_name).
    """
    if not tiers or consumption <= 0:
        return 0.0, 0.0, "none"

    remaining = consumption
    prev_max = 0.0
    total = 0.0
    marginal = 0.0
    tier_name = "tier_1"

    for i, tier in enumerate(tiers):
        max_kwh = float(tier["max_kwh"])
        rate = float(tier["rate"])
        block_size = max_kwh - prev_max
        used_in_block = min(remaining, block_size)
        total += used_in_block * rate
        remaining -= used_in_block
        marginal = rate
        tier_name = f"tier_{i + 1}"
        prev_max = max_kwh
        if remaining <= 0:
            break

    if remaining > 0 and tiers:
        last_rate = float(tiers[-1]["rate"])
        total += remaining * last_rate
        marginal = last_rate
        tier_name = f"tier_{len(tiers)}_plus"

    return total, marginal, tier_name


def get_current_tou_rate(periods: list[dict], now: datetime | None = None) -> tuple[float, str]:
    """Return (rate, period_name) for the current time."""
    if now is None:
        now = datetime.now()
    current_time = now.time()
    is_weekday = now.weekday() < 5

    for period in periods:
        start_str = period["start"]
        end_str = period["end"]
        start_t = datetime.strptime(start_str, "%H:%M").time()
        end_t = datetime.strptime(end_str, "%H:%M").time()
        weekdays_only = period.get("weekdays_only", False)

        if weekdays_only and not is_weekday:
            continue

        if start_t <= end_t:
            in_period = start_t <= current_time < end_t
        else:
            in_period = current_time >= start_t or current_time < end_t

        if in_period:
            return float(period["rate"]), period["name"]

    if periods:
        return float(periods[-1]["rate"]), periods[-1]["name"]
    return 0.0, "unknown"


def calc_interconnect_fee(
    capacity_kwp: float,
    rate_per_kwp: float,
    free_kwp: float = 0.0,
) -> float:
    """
    Capacity-based monthly grid-usage / interconnection fee.

    Elmar Aruba residential example:
        capacity=6, rate=15, free=3  →  (6-3)*15 = 45 AWG
        capacity=10, rate=15, free=3 → (10-3)*15 = 105 AWG
        capacity=2, rate=15, free=3  → 0 (under free allowance)
    """
    if capacity_kwp <= 0 or rate_per_kwp <= 0:
        return 0.0
    billable = max(0.0, float(capacity_kwp) - float(free_kwp))
    return billable * float(rate_per_kwp)


def calc_export_credit(
    export_kwh: float,
    import_kwh: float,
    buyback_rate: float,
) -> float:
    """
    Credit for net excess export (after offsetting grid import).

    Example (user): exported 900, imported/used 800, rate 0.2916
        → max(0, 900-800) * 0.2916 = 29.16

    Matches Elmar-style net metering + surplus buy-back:
    self-consumption offsets 1:1; only the true monthly surplus is
    purchased at the reduced buy-back rate.
    """
    if buyback_rate <= 0:
        return 0.0
    excess = max(0.0, float(export_kwh) - float(import_kwh))
    return excess * float(buyback_rate)
