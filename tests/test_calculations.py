"""Unit tests for tiered and TOU calculation logic (no Home Assistant required)."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "gridmetrics"))

from calculations import calc_tiered_cost, get_current_tou_rate, get_cycle_bounds


# ---------------------------------------------------------------------------
# Tiered (increasing-block) tests – Aruba Elmar style
# ---------------------------------------------------------------------------

ARUBA_TIERS = [
    {"max_kwh": 500, "rate": 0.3431},
    {"max_kwh": 1000, "rate": 0.3531},
    {"max_kwh": 99999, "rate": 0.4645},
]


def test_tiered_zero():
    cost, marginal, tier = calc_tiered_cost(0, ARUBA_TIERS)
    assert cost == 0.0
    assert tier == "none"


def test_tiered_first_block():
    cost, marginal, tier = calc_tiered_cost(300, ARUBA_TIERS)
    assert abs(cost - 300 * 0.3431) < 0.001
    assert abs(marginal - 0.3431) < 0.0001
    assert tier == "tier_1"


def test_tiered_second_block():
    cost, marginal, tier = calc_tiered_cost(700, ARUBA_TIERS)
    expected = 500 * 0.3431 + 200 * 0.3531
    assert abs(cost - expected) < 0.01
    assert abs(marginal - 0.3531) < 0.0001
    assert tier == "tier_2"


def test_tiered_third_block():
    cost, marginal, tier = calc_tiered_cost(1200, ARUBA_TIERS)
    expected = 500 * 0.3431 + 500 * 0.3531 + 200 * 0.4645
    assert abs(cost - expected) < 0.01
    assert abs(marginal - 0.4645) < 0.0001
    assert tier.startswith("tier_3")


def test_tiered_empty():
    cost, marginal, tier = calc_tiered_cost(100, [])
    assert cost == 0.0
    assert tier == "none"


# ---------------------------------------------------------------------------
# Mexico CFE-style tiers
# ---------------------------------------------------------------------------

CFE_TIERS = [
    {"max_kwh": 75, "rate": 1.125},
    {"max_kwh": 140, "rate": 1.369},
    {"max_kwh": 99999, "rate": 4.004},
]


def test_cfe_basic():
    cost, marginal, _ = calc_tiered_cost(50, CFE_TIERS)
    assert abs(cost - 50 * 1.125) < 0.01
    assert abs(marginal - 1.125) < 0.001


def test_cfe_intermediate():
    cost, marginal, _ = calc_tiered_cost(100, CFE_TIERS)
    expected = 75 * 1.125 + 25 * 1.369
    assert abs(cost - expected) < 0.01
    assert abs(marginal - 1.369) < 0.001


def test_cfe_excess():
    cost, marginal, _ = calc_tiered_cost(200, CFE_TIERS)
    expected = 75 * 1.125 + 65 * 1.369 + 60 * 4.004
    assert abs(cost - expected) < 0.1
    assert abs(marginal - 4.004) < 0.001


# ---------------------------------------------------------------------------
# TOU tests – Jamaica JPS style
# ---------------------------------------------------------------------------

JPS_PERIODS = [
    {"name": "peak", "start": "18:00", "end": "22:00", "rate": 0.35, "weekdays_only": True},
    {"name": "partial", "start": "06:00", "end": "18:00", "rate": 0.28, "weekdays_only": True},
    {"name": "offpeak", "start": "22:00", "end": "06:00", "rate": 0.22, "weekdays_only": False},
]


def test_tou_weekday_peak():
    now = datetime(2026, 9, 2, 19, 0)  # Wed
    rate, name = get_current_tou_rate(JPS_PERIODS, now)
    assert name == "peak"
    assert abs(rate - 0.35) < 0.001


def test_tou_weekday_partial():
    now = datetime(2026, 9, 2, 12, 0)  # Wed noon
    rate, name = get_current_tou_rate(JPS_PERIODS, now)
    assert name == "partial"
    assert abs(rate - 0.28) < 0.001


def test_tou_weekday_offpeak_night():
    now = datetime(2026, 9, 2, 23, 30)  # Wed night
    rate, name = get_current_tou_rate(JPS_PERIODS, now)
    assert name == "offpeak"
    assert abs(rate - 0.22) < 0.001


def test_tou_weekend_ignores_weekday_only():
    now = datetime(2026, 9, 5, 19, 0)  # Sat
    rate, name = get_current_tou_rate(JPS_PERIODS, now)
    assert name == "offpeak"


# ---------------------------------------------------------------------------
# Cycle bounds
# ---------------------------------------------------------------------------

def test_cycle_bounds_mid_month():
    now = datetime(2026, 9, 15, 10, 0)
    start, end = get_cycle_bounds(1, now)
    assert start.day == 1
    assert start.month == 9
    assert end.month == 10
    assert end.day == 1


def test_cycle_bounds_before_billing_day():
    now = datetime(2026, 9, 3, 10, 0)
    start, end = get_cycle_bounds(10, now)
    assert start.month == 8
    assert start.day == 10
    assert end.month == 9
    assert end.day == 10


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed out of {len(tests)}")
    sys.exit(1 if failed else 0)
