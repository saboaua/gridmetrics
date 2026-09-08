"""Unit tests for tiered, TOU, interconnect and export-credit logic (no Home Assistant required)."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "gridmetrics"))

from calculations import (
    calc_tiered_cost,
    get_current_tou_rate,
    get_cycle_bounds,
    calc_interconnect_fee,
    calc_export_credit,
)


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
    # Wednesday 19:00
    now = datetime(2024, 6, 5, 19, 0)
    rate, name = get_current_tou_rate(JPS_PERIODS, now)
    assert abs(rate - 0.35) < 0.001
    assert name == "peak"


def test_tou_weekday_partial():
    now = datetime(2024, 6, 5, 12, 0)
    rate, name = get_current_tou_rate(JPS_PERIODS, now)
    assert abs(rate - 0.28) < 0.001
    assert name == "partial"


def test_tou_weekend_offpeak():
    # Saturday 12:00 → offpeak (weekdays_only periods skipped)
    now = datetime(2024, 6, 8, 12, 0)
    rate, name = get_current_tou_rate(JPS_PERIODS, now)
    assert abs(rate - 0.22) < 0.001
    assert name == "offpeak"


# ---------------------------------------------------------------------------
# Cycle bounds
# ---------------------------------------------------------------------------

def test_cycle_bounds_after_day():
    now = datetime(2024, 6, 15, 10, 0)
    start, end = get_cycle_bounds(1, now)
    assert start.day == 1
    assert start.month == 6
    assert end.month == 7
    assert end.day == 1


def test_cycle_bounds_before_day():
    now = datetime(2024, 6, 5, 10, 0)
    start, end = get_cycle_bounds(10, now)
    assert start.day == 10
    assert start.month == 5
    assert end.day == 10
    assert end.month == 6


# ---------------------------------------------------------------------------
# Interconnection / grid-usage fee (Elmar Aruba)
# ---------------------------------------------------------------------------

def test_interconnect_under_free():
    # 2 kWp → fully covered by 3 kWp free allowance
    fee = calc_interconnect_fee(2.0, 15.0, 3.0)
    assert fee == 0.0


def test_interconnect_exact_free():
    fee = calc_interconnect_fee(3.0, 15.0, 3.0)
    assert fee == 0.0


def test_interconnect_6kwp():
    # User example: 6 kWp → (6-3)*15 = 45
    fee = calc_interconnect_fee(6.0, 15.0, 3.0)
    assert abs(fee - 45.0) < 0.001


def test_interconnect_10kwp():
    # User example: 10 kWp → (10-3)*15 = 105
    fee = calc_interconnect_fee(10.0, 15.0, 3.0)
    assert abs(fee - 105.0) < 0.001


def test_interconnect_zero_capacity():
    assert calc_interconnect_fee(0.0, 15.0, 3.0) == 0.0


def test_interconnect_no_free():
    fee = calc_interconnect_fee(5.0, 15.0, 0.0)
    assert abs(fee - 75.0) < 0.001


# ---------------------------------------------------------------------------
# Export / buy-back credit
# ---------------------------------------------------------------------------

def test_export_credit_basic():
    # User example: 900 export, 800 import → 100 * 0.2916
    credit = calc_export_credit(900.0, 800.0, 0.2916)
    assert abs(credit - 29.16) < 0.001


def test_export_credit_no_excess():
    credit = calc_export_credit(500.0, 600.0, 0.2916)
    assert credit == 0.0


def test_export_credit_zero_rate():
    credit = calc_export_credit(900.0, 800.0, 0.0)
    assert credit == 0.0


def test_export_credit_equal():
    credit = calc_export_credit(800.0, 800.0, 0.2916)
    assert credit == 0.0


# ---------------------------------------------------------------------------
# Full Aruba-style bill composition (unit-level)
# ---------------------------------------------------------------------------

def test_aruba_full_bill_example():
    """
    Realistic monthly numbers:
      - 6 kWp system → interconnect 45 AWG
      - fixed 12.50
      - net import 420 kWh (tiered)
      - excess export 100 kWh @ 0.2916
    """
    net_kwh = 420.0
    energy_cost, _, _ = calc_tiered_cost(net_kwh, ARUBA_TIERS)
    interconnect = calc_interconnect_fee(6.0, 15.0, 3.0)
    fixed = 12.50
    credit = calc_export_credit(900.0, 800.0, 0.2916)  # 100 excess
    tax_pct = 0.0

    subtotal = energy_cost + fixed + interconnect - credit
    bill = subtotal * (1 + tax_pct / 100.0)

    expected_energy = 420 * 0.3431
    expected = expected_energy + 12.50 + 45.0 - 29.16
    assert abs(bill - expected) < 0.02
