"""Config flow for Tiered / TOU Electricity Rate Calculator."""

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
    RATE_MODE_TIERED,
    RATE_MODE_TOU,
    RATE_MODE_COMBINED,
    DEFAULT_CURRENCY,
    DEFAULT_BILLING_CYCLE_DAY,
    DEFAULT_FIXED_CHARGE,
    DEFAULT_TAX_PERCENT,
)


class TieredTouConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tiered TOU Energy Cost."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(self, user_input=None):
        """Initial step: basic info + rate mode."""
        errors = {}

        if user_input is not None:
            self._data.update(user_input)
            mode = user_input[CONF_RATE_MODE]
            if mode in (RATE_MODE_TIERED, RATE_MODE_COMBINED):
                return await self.async_step_tiers()
            return await self.async_step_tou()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Home Electricity"): str,
                vol.Required(CONF_SOURCE_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                ),
                vol.Required(CONF_RATE_MODE, default=RATE_MODE_TIERED): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": RATE_MODE_TIERED, "label": "Tiered (block rates)"},
                            {"value": RATE_MODE_TOU, "label": "Time-of-Use only"},
                            {"value": RATE_MODE_COMBINED, "label": "Combined Tiered + TOU"},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_CURRENCY, default=DEFAULT_CURRENCY): str,
                vol.Required(
                    CONF_BILLING_CYCLE_DAY, default=DEFAULT_BILLING_CYCLE_DAY
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=28)),
                vol.Optional(CONF_FIXED_CHARGE, default=DEFAULT_FIXED_CHARGE): vol.Coerce(float),
                vol.Optional(CONF_TAX_PERCENT, default=DEFAULT_TAX_PERCENT): vol.Coerce(float),
                vol.Optional(CONF_PREPAID_ENABLED, default=False): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_tiers(self, user_input=None):
        """Configure consumption tiers (increasing block)."""
        errors = {}

        if user_input is not None:
            # Parse simple tier string: "200:0.25,500:0.32,99999:0.41"
            try:
                tiers = []
                raw = user_input.get("tiers_raw", "").strip()
                for part in raw.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    max_kwh, rate = part.split(":")
                    tiers.append(
                        {"max_kwh": float(max_kwh.strip()), "rate": float(rate.strip())}
                    )
                if not tiers:
                    raise ValueError("No tiers defined")
                # Ensure sorted by max_kwh
                tiers.sort(key=lambda t: t["max_kwh"])
                self._data[CONF_TIERS] = tiers
            except Exception:
                errors["base"] = "invalid_tiers"
                return self.async_show_form(
                    step_id="tiers",
                    data_schema=self._tiers_schema(),
                    errors=errors,
                )

            if self._data[CONF_RATE_MODE] == RATE_MODE_COMBINED:
                return await self.async_step_tou()
            return await self._finish()

        return self.async_show_form(
            step_id="tiers", data_schema=self._tiers_schema(), errors=errors
        )

    def _tiers_schema(self):
        # Aruba example pre-filled as helpful default
        default = "500:0.3431,1000:0.3531,99999:0.4645"
        return vol.Schema(
            {
                vol.Required(
                    "tiers_raw",
                    default=default,
                    description={
                        "suggested_value": default,
                    },
                ): str,
            }
        )

    async def async_step_tou(self, user_input=None):
        """Configure TOU periods."""
        errors = {}

        if user_input is not None:
            try:
                periods = []
                raw = user_input.get("tou_raw", "").strip()
                for part in raw.split(";"):
                    part = part.strip()
                    if not part:
                        continue
                    # format: name|start|end|rate|weekdays_only
                    bits = [b.strip() for b in part.split("|")]
                    periods.append(
                        {
                            "name": bits[0],
                            "start": bits[1],
                            "end": bits[2],
                            "rate": float(bits[3]),
                            "weekdays_only": bits[4].lower() in ("1", "true", "yes")
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
        # Jamaica-style example
        default = (
            "peak|18:00|22:00|0.35|true;"
            "partial|06:00|18:00|0.28|true;"
            "offpeak|22:00|06:00|0.22|false"
        )
        return vol.Schema(
            {
                vol.Required("tou_raw", default=default): str,
            }
        )

    async def _finish(self):
        """Create the entry."""
        if self._data.get(CONF_PREPAID_ENABLED):
            self._data[CONF_PREPAID_BALANCE] = 0.0

        title = self._data.get(CONF_NAME, "Electricity Cost")
        return self.async_create_entry(title=title, data=self._data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TieredTouOptionsFlow(config_entry)


class TieredTouOptionsFlow(config_entries.OptionsFlow):
    """Handle options (edit rates without full re-setup)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data = self.config_entry.data
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
                    default=data.get(CONF_BILLING_CYCLE_DAY, DEFAULT_BILLING_CYCLE_DAY),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=28)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
