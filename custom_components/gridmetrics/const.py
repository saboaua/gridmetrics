"""Constants for GridMetrics."""

DOMAIN = "gridmetrics"
VERSION = "0.2.9"

# Config entry schema version (HA config_entries versioning, NOT the
# integration release version above). Bump this in lockstep with
# GridMetricsConfigFlow.VERSION in config_flow.py whenever the stored
# entry.data schema changes, and add a real migration step in
# __init__.async_migrate_entry for that bump.
CONFIG_ENTRY_VERSION = 3

CONF_SOURCE_SENSOR = "source_sensor"
CONF_CURRENCY = "currency"
CONF_BILLING_CYCLE_DAY = "billing_cycle_day"
CONF_FIXED_CHARGE = "fixed_charge"
CONF_TAX_PERCENT = "tax_percent"
CONF_RATE_MODE = "rate_mode"
CONF_TIERS = "tiers"
CONF_TOU_PERIODS = "tou_periods"
CONF_PREPAID_ENABLED = "prepaid_enabled"
CONF_PREPAID_BALANCE = "prepaid_balance"
CONF_NAME = "name"

# Setup path: solar_grid | grid_only
CONF_SETUP_TYPE = "setup_type"
SETUP_SOLAR_GRID = "solar_grid"
SETUP_GRID_ONLY = "grid_only"

# Solar / net-metering
CONF_SOLAR_SENSOR = "solar_sensor"
CONF_SOLAR_IS_ENERGY = "solar_is_energy"
CONF_GRID_SENSOR = "grid_sensor"
CONF_GRID_IS_ENERGY = "grid_is_energy"
CONF_GRID_PHASES = "grid_phases"
CONF_GRID_SIGN = "grid_sign"
CONF_EXPORT_RATE = "export_rate"
CONF_GRID_SETUP_TYPE = "grid_setup_type"
GRID_SETUP_SINGLE = "single"
GRID_SETUP_PHASES = "phases"

# Capacity-based interconnection / grid-usage fee (e.g. Elmar Aruba)
CONF_SOLAR_CAPACITY_KWP = "solar_capacity_kwp"
CONF_INTERCONNECT_RATE = "interconnect_rate"
CONF_INTERCONNECT_FREE_KWP = "interconnect_free_kwp"

RATE_MODE_TIERED = "tiered"
RATE_MODE_TOU = "tou"
RATE_MODE_COMBINED = "combined"

DEFAULT_CURRENCY = "USD"
DEFAULT_BILLING_CYCLE_DAY = 1
DEFAULT_FIXED_CHARGE = 0.0
DEFAULT_TAX_PERCENT = 0.0
DEFAULT_EXPORT_RATE = 0.0
DEFAULT_SOLAR_CAPACITY_KWP = 0.0
DEFAULT_INTERCONNECT_RATE = 15.0
DEFAULT_INTERCONNECT_FREE_KWP = 3.0

CURRENCY_OPTIONS = [
    {"value": "USD", "label": "USD - US Dollar"},
    {"value": "AWG", "label": "AWG - Aruban Florin"},
    {"value": "MXN", "label": "MXN - Mexican Peso"},
    {"value": "JMD", "label": "JMD - Jamaican Dollar"},
    {"value": "BBD", "label": "BBD - Barbadian Dollar"},
    {"value": "TTD", "label": "TTD - Trinidad and Tobago Dollar"},
    {"value": "CAD", "label": "CAD - Canadian Dollar"},
    {"value": "BRL", "label": "BRL - Brazilian Real"},
    {"value": "COP", "label": "COP - Colombian Peso"},
    {"value": "ARS", "label": "ARS - Argentine Peso"},
    {"value": "CLP", "label": "CLP - Chilean Peso"},
    {"value": "PEN", "label": "PEN - Peruvian Sol"},
    {"value": "INR", "label": "INR - Indian Rupee"},
    {"value": "ZAR", "label": "ZAR - South African Rand"},
    {"value": "NGN", "label": "NGN - Nigerian Naira"},
    {"value": "KES", "label": "KES - Kenyan Shilling"},
    {"value": "PHP", "label": "PHP - Philippine Peso"},
    {"value": "THB", "label": "THB - Thai Baht"},
    {"value": "EUR", "label": "EUR - Euro"},
    {"value": "GBP", "label": "GBP - British Pound"},
]
