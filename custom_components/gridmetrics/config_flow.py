"""Config flow for GridMetrics."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.const import CONF_NAME

from .const import (
    DOMAIN,
    CONF_SOURCE_SENSOR,
    CONF_CURRENCY,
    CONF_BILLING_CYCLE_DAY,
    CONF_FIXED_CHARGE,
    CONF_TAX_PERCENT,
    CONF_RATE_MODE,
    CONF_TIERS,
    CONF_TOU_PERIODS,
    CONF_PREPAID_ENABLED,
    CONF_PREPAID_BALANCE,
    CONF_SETUP_TYPE,
    SETUP_SOLAR_GRID,
    SETUP_GRID_ONLY,
    CONF_SOLAR_SENSOR,
    CONF_SOLAR_IS_ENERGY,
    CONF_GRID_SENSOR,
    CONF_GRID_IS_ENERGY,
    CONF_GRID_PHASES,
    CONF_GRID_SIGN,
    CONF_EXPORT_RATE,
    CONF_GRID_SETUP_TYPE,
    GRID_SETUP_SINGLE,
    GRID_SETUP_PHASES,
    RATE_MODE_TIERED,
    RATE_MODE_TOU,
    RATE_MODE_COMBINED,
    DEFAULT_CURRENCY,
    DEFAULT_BILLING_CYCLE_DAY,
    DEFAULT_FIXED_CHARGE,
    DEFAULT_TAX_PERCENT,
    DEFAULT_EXPORT_RATE,
    CURRENCY_OPTIONS,
)


class GridMetricsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for GridMetrics."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(self, user_input=None):
        """Step 1: choose Solar+Grid or Grid-only."""
        errors = {}

        if user_input is not None:
            self._data.update(user_input)
            if user_input.get(CONF_SETUP_TYPE) == SETUP_SOLAR_GRID:
                return await self.async_step_basics()
            return await self.async_step_basics_grid_only()

        schema = vol.Schema(
            {
                vol.Required(CONF_SETUP_TYPE, default=SETUP_SOLAR_GRID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": SETUP_SOLAR_GRID,
                                "label": "Solar + Grid (Enphase, Shelly 3EM, net metering)",
                            },
                            {
                                "value": SETUP_GRID_ONLY,
                                "label": "Grid only (no solar panels)",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_basics(self, user_input=None):
        """Basics for solar+grid path."""
        errors = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_solar_production()

        return self.async_show_form(
            step_id="basics",
            data_schema=self._basics_schema(),
            errors=errors,
        )

    async def async_step_basics_grid_only(self, user_input=None):
        """Basics for grid-only path."""
        errors = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_source()

        return self.async_show_form(
            step_id="basics_grid_only",
            data_schema=self._basics_schema(),
            errors=errors,
        )

    def _basics_schema(self):
        return vol.Schema(
            {
                vol.Required(CONF_NAME, default="Home Electricity"): str,
                vol.Required(CONF_RATE_MODE, default=RATE_MODE_TIERED): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": RATE_MODE_TIERED, "label": "Tiered / block rates"},
                            {"value": RATE_MODE_TOU, "label": "Time-of-Use only"},
                            {"value": RATE_MODE_COMBINED, "label": "Combined tiered + TOU"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_CURRENCY, default=DEFAULT_CURRENCY): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=CURRENCY_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_BILLING_CYCLE_DAY, default=DEFAULT_BILLING_CYCLE_DAY
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=28)),
                vol.Optional(CONF_FIXED_CHARGE, default=DEFAULT_FIXED_CHARGE): vol.Coerce(float),
                vol.Optional(CONF_TAX_PERCENT, default=DEFAULT_TAX_PERCENT): vol.Coerce(float),
                vol.Optional(CONF_PREPAID_ENABLED, default=False): bool,
            }
        )

    async def async_step_solar_production(self, user_input=None):
        """Pick solar production sensor."""
        errors = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_grid_type()

        schema = vol.Schema(
            {
                vol.Required(CONF_SOLAR_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_SOLAR_IS_ENERGY, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="solar_production", data_schema=schema, errors=errors
        )

    async def async_step_grid_type(self, user_input=None):
        """Single grid sensor or multi-phase?"""
        errors = {}
        if user_input is not None:
            self._data[CONF_GRID_SETUP_TYPE] = user_input[CONF_GRID_SETUP_TYPE]
            if user_input[CONF_GRID_SETUP_TYPE] == GRID_SETUP_PHASES:
                return await self.async_step_grid_phases()
            return await self.async_step_grid_single()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_GRID_SETUP_TYPE, default=GRID_SETUP_PHASES
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": GRID_SETUP_PHASES,
                                "label": "Multiple phases (Shelly 3EM / 3-phase meter)",
                            },
                            {
                                "value": GRID_SETUP_SINGLE,
                                "label": "One single grid sensor",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="grid_type", data_schema=schema, errors=errors)

    async def async_step_grid_phases(self, user_input=None):
        """Phase A / B / C entity pickers."""
        errors = {}
        if user_input is not None:
            phases = []
            for key in ("phase_a", "phase_b", "phase_c"):
                eid = user_input.get(key)
                if eid:
                    phases.append(eid)
            if not phases:
                errors["base"] = "need_one_phase"
                return self.async_show_form(
                    step_id="grid_phases",
                    data_schema=self._phases_schema(),
                    errors=errors,
                )
            self._data[CONF_GRID_PHASES] = phases
            self._data[CONF_GRID_SENSOR] = None
            self._data[CONF_GRID_IS_ENERGY] = user_input.get(CONF_GRID_IS_ENERGY, False)
            self._data[CONF_GRID_SIGN] = user_input.get(
                CONF_GRID_SIGN, "positive_import"
            )
            self._data[CONF_EXPORT_RATE] = user_input.get(
                CONF_EXPORT_RATE, DEFAULT_EXPORT_RATE
            )
            return await self._after_sensors()

        return self.async_show_form(
            step_id="grid_phases",
            data_schema=self._phases_schema(),
            errors=errors,
        )

    def _phases_schema(self):
        ent = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
        return vol.Schema(
            {
                vol.Optional("phase_a"): ent,
                vol.Optional("phase_b"): ent,
                vol.Optional("phase_c"): ent,
                vol.Required(CONF_GRID_IS_ENERGY, default=False): bool,
                vol.Required(
                    CONF_GRID_SIGN, default="positive_import"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "positive_import",
                                "label": "Positive = importing FROM the grid",
                            },
                            {
                                "value": "positive_export",
                                "label": "Positive = exporting TO the grid",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_EXPORT_RATE, default=DEFAULT_EXPORT_RATE): vol.Coerce(
                    float
                ),
            }
        )

    async def async_step_grid_single(self, user_input=None):
        """One net grid sensor."""
        errors = {}
        if user_input is not None:
            self._data[CONF_GRID_SENSOR] = user_input[CONF_GRID_SENSOR]
            self._data[CONF_GRID_PHASES] = []
            self._data[CONF_GRID_IS_ENERGY] = user_input.get(CONF_GRID_IS_ENERGY, False)
            self._data[CONF_GRID_SIGN] = user_input.get(
                CONF_GRID_SIGN, "positive_import"
            )
            self._data[CONF_EXPORT_RATE] = user_input.get(
                CONF_EXPORT_RATE, DEFAULT_EXPORT_RATE
            )
            return await self._after_sensors()

        schema = vol.Schema(
            {
                vol.Required(CONF_GRID_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_GRID_IS_ENERGY, default=False): bool,
                vol.Required(
                    CONF_GRID_SIGN, default="positive_import"
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": "positive_import",
                                "label": "Positive = importing FROM the grid",
                            },
                            {
                                "value": "positive_export",
                                "label": "Positive = exporting TO the grid",
                            },
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(CONF_EXPORT_RATE, default=DEFAULT_EXPORT_RATE): vol.Coerce(
                    float
                ),
            }
        )
        return self.async_show_form(
            step_id="grid_single", data_schema=schema, errors=errors
        )

    async def async_step_source(self, user_input=None):
        """Grid-only: billed energy sensor (kWh total)."""
        errors = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self._after_sensors()

        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCE_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )
        return self.async_show_form(step_id="source", data_schema=schema, errors=errors)

    async def _after_sensors(self):
        mode = self._data.get(CONF_RATE_MODE, RATE_MODE_TIERED)
        if mode in (RATE_MODE_TIERED, RATE_MODE_COMBINED):
            return await self.async_step_tiers()
        return await self.async_step_tou()

    async def async_step_tiers(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                tiers = []
                raw = user_input.get("tiers_raw", "").strip()
                for part in raw.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    max_kwh, rate = part.split(":")
                    tiers.append(
                        {
                            "max_kwh": float(max_kwh.strip()),
                            "rate": float(rate.strip()),
                        }
                    )
                if not tiers:
                    raise ValueError("empty")
                tiers.sort(key=lambda t: t["max_kwh"])
                self._data[CONF_TIERS] = tiers
            except Exception:
                errors["base"] = "invalid_tiers"
                return self.async_show_form(
                    step_id="tiers",
                    data_schema=self._tiers_schema(),
                    errors=errors,
                )
            if self._data.get(CONF_RATE_MODE) == RATE_MODE_COMBINED:
                return await self.async_step_tou()
            return await self._finish()

        return self.async_show_form(
            step_id="tiers", data_schema=self._tiers_schema(), errors=errors
        )

    def _tiers_schema(self):
        return vol.Schema(
            {
                vol.Required(
                    "tiers_raw", default="500:0.3431,1000:0.3531,99999:0.4645"
                ): str
            }
        )

    async def async_step_tou(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                periods = []
                raw = user_input.get("tou_raw", "").strip()
                for part in raw.split(";"):
                    part = part.strip()
                    if not part:
                        continue
                    bits = [b.strip() for b in part.split("|")]
                    periods.append(
                        {
                            "name": bits[0],
                            "start": bits[1],
                            "end": bits[2],
                            "rate": float(bits[3]),
                            "weekdays_only": bits[4].lower()
                            in ("1", "true", "yes")
                            if len(bits) > 4
                            else False,
                        }
                    )
                self._data[CONF_TOU_PERIODS] = periods
            except Exception:
                errors["base"] = "invalid_tou"
                return self.async_show_form(
                    step_id="tou",
                    data_schema=self._tou_schema(),
                    errors=errors,
                )
            return await self._finish()

        return self.async_show_form(
            step_id="tou", data_schema=self._tou_schema(), errors=errors
        )

    def _tou_schema(self):
        default = (
            "peak|18:00|22:00|0.35|true;"
            "partial|06:00|18:00|0.28|true;"
            "offpeak|22:00|06:00|0.22|false"
        )
        return vol.Schema({vol.Required("tou_raw", default=default): str})

    async def _finish(self):
        if self._data.get(CONF_PREPAID_ENABLED):
            self._data[CONF_PREPAID_BALANCE] = 0.0

        # Clean internal keys
        self._data.pop(CONF_GRID_SETUP_TYPE, None)

        if self._data.get(CONF_SETUP_TYPE) == SETUP_SOLAR_GRID:
            self._data[CONF_SOURCE_SENSOR] = "derived_home_consumption"

        title = self._data.get(CONF_NAME, "GridMetrics")
        return self.async_create_entry(title=title, data=self._data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GridMetricsOptionsFlow()


class GridMetricsOptionsFlow(config_entries.OptionsFlow):
    """Options flow (HA modern style - no config_entry in __init__)."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_FIXED_CHARGE,
                    default=data.get(CONF_FIXED_CHARGE, DEFAULT_FIXED_CHARGE),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_TAX_PERCENT,
                    default=data.get(CONF_TAX_PERCENT, DEFAULT_TAX_PERCENT),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_BILLING_CYCLE_DAY,
                    default=data.get(
                        CONF_BILLING_CYCLE_DAY, DEFAULT_BILLING_CYCLE_DAY
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=28)),
                vol.Optional(
                    CONF_EXPORT_RATE,
                    default=data.get(CONF_EXPORT_RATE, DEFAULT_EXPORT_RATE),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_CURRENCY,
                    default=data.get(CONF_CURRENCY, DEFAULT_CURRENCY),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=CURRENCY_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
