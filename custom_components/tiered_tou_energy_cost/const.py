"""Constants for the Tiered / TOU Electricity Rate Calculator."""

DOMAIN = "tiered_tou_energy_cost"
VERSION = "0.1.0"

CONF_SOURCE_SENSOR = "source_sensor"
CONF_CURRENCY = "currency"
CONF_BILLING_CYCLE_DAY = "billing_cycle_day"
CONF_FIXED_CHARGE = "fixed_charge"
CONF_TAX_PERCENT = "tax_percent"
CONF_RATE_MODE = "rate_mode"
CONF_TIERS = "tiers"
CONF_TOU_PERIODS = "tou_periods"
CONF_COMBINED = "combined"
CONF_PREPAID_ENABLED = "prepaid_enabled"
CONF_PREPAID_BALANCE = "prepaid_balance"
CONF_NAME = "name"

RATE_MODE_TIERED = "tiered"
RATE_MODE_TOU = "tou"
RATE_MODE_COMBINED = "combined"

ATTR_MARGINAL_RATE = "marginal_rate"
ATTR_CYCLE_CONSUMPTION = "cycle_consumption"
ATTR_ESTIMATED_BILL = "estimated_bill"
ATTR_FORECAST_BILL = "forecast_bill"
ATTR_CURRENT_TIER = "current_tier"
ATTR_CURRENT_PERIOD = "current_period"
ATTR_DAYS_IN_CYCLE = "days_in_cycle"
ATTR_DAYS_REMAINING = "days_remaining"

DEFAULT_CURRENCY = "USD"
DEFAULT_BILLING_CYCLE_DAY = 1
DEFAULT_FIXED_CHARGE = 0.0
DEFAULT_TAX_PERCENT = 0.0

# Future-ready keys (not fully used in v0.1 but schema-ready)
CONF_SEASONAL_PROFILES = "seasonal_profiles"
CONF_FUEL_CLAUSE = "fuel_clause"
CONF_DEMAND_CHARGE = "demand_charge"
CONF_PREPAID_LOW_BALANCE_THRESHOLD = "prepaid_low_balance_threshold"
