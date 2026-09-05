"""Constants for the Tiered / TOU Electricity Rate Calculator."""

DOMAIN = "tiered_tou_energy_cost"
VERSION = "0.2.0"

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

# Solar / net-metering
CONF_HAS_SOLAR = "has_solar"
CONF_SOLAR_SENSOR = "solar_sensor"
CONF_SOLAR_IS_ENERGY = "solar_is_energy"
CONF_GRID_SENSOR = "grid_sensor"
CONF_GRID_IS_ENERGY = "grid_is_energy"
CONF_GRID_PHASES = "grid_phases"
CONF_GRID_SIGN = "grid_sign"
CONF_EXPORT_RATE = "export_rate"

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
DEFAULT_EXPORT_RATE = 0.0

CURRENCY_OPTIONS = [
    {"value": "USD", "label": "USD – US Dollar"},
    {"value": "AWG", "label": "AWG – Aruban Florin"},
    {"value": "MXN", "label": "MXN – Mexican Peso"},
    {"value": "JMD", "label": "JMD – Jamaican Dollar"},
    {"value": "BBD", "label": "BBD – Barbadian Dollar"},
    {"value": "TTD", "label": "TTD – Trinidad & Tobago Dollar"},
    {"value": "CAD", "label": "CAD – Canadian Dollar"},
    {"value": "BRL", "label": "BRL – Brazilian Real"},
    {"value": "COP", "label": "COP – Colombian Peso"},
    {"value": "ARS", "label": "ARS – Argentine Peso"},
    {"value": "CLP", "label": "CLP – Chilean Peso"},
    {"value": "PEN", "label": "PEN – Peruvian Sol"},
    {"value": "INR", "label": "INR – Indian Rupee"},
    {"value": "ZAR", "label": "ZAR – South African Rand"},
    {"value": "NGN", "label": "NGN – Nigerian Naira"},
    {"value": "KES", "label": "KES – Kenyan Shilling"},
    {"value": "PHP", "label": "PHP – Philippine Peso"},
    {"value": "THB", "label": "THB – Thai Baht"},
    {"value": "EUR", "label": "EUR – Euro"},
    {"value": "GBP", "label": "GBP – British Pound"},
    {"value": "OTHER", "label": "Other (enter code later)"},
]

CONF_SEASONAL_PROFILES = "seasonal_profiles"
CONF_FUEL_CLAUSE = "fuel_clause"
CONF_DEMAND_CHARGE = "demand_charge"
CONF_PREPAID_LOW_BALANCE_THRESHOLD = "prepaid_low_balance_threshold"
