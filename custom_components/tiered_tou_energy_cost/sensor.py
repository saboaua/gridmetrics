"""Sensors for Tiered / TOU Electricity Rate Calculator."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

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
    RATE_MODE_TIERED,
    RATE_MODE_TOU,
    RATE_MODE_COMBINED,
    ATTR_MARGINAL_RATE,
    ATTR_CYCLE_CONSUMPTION,
    ATTR_ESTIMATED_BILL,
    ATTR_FORECAST_BILL,
    ATTR_CURRENT_TIER,
    ATTR_CURRENT_PERIOD,
    ATTR_DAYS_IN_CYCLE,
    ATTR_DAYS_REMAINING,
)

from .calculations import (
    calc_tiered_cost as _calc_tiered_cost,
    get_current_tou_rate as _get_current_tou_rate,
    get_cycle_bounds as _get_cycle_bounds,
)



_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    config = {**entry.data, **entry.options}
    source = config[CONF_SOURCE_SENSOR]
    name_prefix = entry.title or "Electricity"

    entities = [
        MarginalRateSensor(hass, entry, config, name_prefix),
        EstimatedBillSensor(hass, entry, config, name_prefix),
        CycleConsumptionSensor(hass, entry, config, name_prefix),
        ForecastBillSensor(hass, entry, config, name_prefix),
    ]

    if config.get(CONF_PREPAID_ENABLED):
        entities.append(PrepaidBalanceSensor(hass, entry, config, name_prefix))

    async_add_entities(entities)


class BaseCostSensor(SensorEntity):
    """Base class for cost sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        config: dict,
        name_prefix: str,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._config = config
        self._attr_unique_id = f"{entry.entry_id}_{self.__class__.__name__}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": name_prefix,
            "manufacturer": "Tiered TOU Energy Cost",
            "model": config.get(CONF_RATE_MODE, "tiered"),
            "sw_version": "0.1.0",
        }
        self._source = config[CONF_SOURCE_SENSOR]
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        """Register state listener on the energy source."""
        self._unsub = async_track_state_change_event(
            self.hass, [self._source], self._handle_source_change
        )
        # Initial update
        self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _handle_source_change(self, event) -> None:
        self.async_schedule_update_ha_state(True)

    def _get_source_kwh(self) -> float | None:
        state = self.hass.states.get(self._source)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _get_cycle_consumption(self) -> float:
        """Return kWh used in the current billing cycle.

        Uses a simple delta from the stored cycle-start reading.
        On first run or after reset the current reading becomes the baseline.
        """
        current = self._get_source_kwh()
        if current is None:
            return 0.0

        data = self.hass.data[DOMAIN][self._entry.entry_id]
        start_kwh = data.get("cycle_start_kwh")

        billing_day = self._config.get(CONF_BILLING_CYCLE_DAY, 1)
        cycle_start, _ = _get_cycle_bounds(billing_day)

        # Auto-reset when we cross into a new cycle
        last_reset = data.get("last_cycle_start")
        if last_reset is None or last_reset < cycle_start:
            data["cycle_start_kwh"] = current
            data["last_cycle_start"] = cycle_start
            return 0.0

        if start_kwh is None:
            data["cycle_start_kwh"] = current
            return 0.0

        return max(0.0, current - start_kwh)


class MarginalRateSensor(BaseCostSensor):
    """Current marginal (next-kWh) rate."""

    _attr_name = "Marginal Rate"
    _attr_native_unit_of_measurement = None  # set dynamically
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:currency-usd"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        currency = self._config.get(CONF_CURRENCY, "USD")
        self._attr_native_unit_of_measurement = f"{currency}/kWh"

    @property
    def native_value(self) -> float | None:
        mode = self._config.get(CONF_RATE_MODE, RATE_MODE_TIERED)
        consumption = self._get_cycle_consumption()

        if mode == RATE_MODE_TOU:
            rate, _ = _get_current_tou_rate(self._config.get(CONF_TOU_PERIODS, []))
            return round(rate, 6)

        if mode in (RATE_MODE_TIERED, RATE_MODE_COMBINED):
            _, marginal, _ = _calc_tiered_cost(
                consumption, self._config.get(CONF_TIERS, [])
            )
            if mode == RATE_MODE_COMBINED:
                # Combined: tier rate is the base; TOU can be a multiplier or overlay.
                # For v0.1 we use the higher of the two (conservative).
                tou_rate, _ = _get_current_tou_rate(
                    self._config.get(CONF_TOU_PERIODS, [])
                )
                return round(max(marginal, tou_rate), 6)
            return round(marginal, 6)

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        mode = self._config.get(CONF_RATE_MODE, RATE_MODE_TIERED)
        attrs = {"rate_mode": mode}
        if mode in (RATE_MODE_TIERED, RATE_MODE_COMBINED):
            _, _, tier = _calc_tiered_cost(
                self._get_cycle_consumption(), self._config.get(CONF_TIERS, [])
            )
            attrs[ATTR_CURRENT_TIER] = tier
        if mode in (RATE_MODE_TOU, RATE_MODE_COMBINED):
            _, period = _get_current_tou_rate(self._config.get(CONF_TOU_PERIODS, []))
            attrs[ATTR_CURRENT_PERIOD] = period
        return attrs


class EstimatedBillSensor(BaseCostSensor):
    """Running estimated bill for the current cycle (energy + fixed + tax)."""

    _attr_name = "Estimated Bill to Date"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:receipt-text"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_native_unit_of_measurement = self._config.get(CONF_CURRENCY, "USD")

    @property
    def native_value(self) -> float | None:
        consumption = self._get_cycle_consumption()
        mode = self._config.get(CONF_RATE_MODE, RATE_MODE_TIERED)
        fixed = float(self._config.get(CONF_FIXED_CHARGE, 0.0))
        tax_pct = float(self._config.get(CONF_TAX_PERCENT, 0.0))

        energy_cost = 0.0
        if mode == RATE_MODE_TIERED:
            energy_cost, _, _ = _calc_tiered_cost(
                consumption, self._config.get(CONF_TIERS, [])
            )
        elif mode == RATE_MODE_TOU:
            # Approximate: use current rate * total (better would be period-split tracking)
            rate, _ = _get_current_tou_rate(self._config.get(CONF_TOU_PERIODS, []))
            energy_cost = consumption * rate
        elif mode == RATE_MODE_COMBINED:
            energy_cost, _, _ = _calc_tiered_cost(
                consumption, self._config.get(CONF_TIERS, [])
            )

        subtotal = energy_cost + fixed
        total = subtotal * (1 + tax_pct / 100.0)
        return round(total, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        consumption = self._get_cycle_consumption()
        billing_day = self._config.get(CONF_BILLING_CYCLE_DAY, 1)
        start, end = _get_cycle_bounds(billing_day)
        now = dt_util.now()
        days_in = max(1, (now - start).days + 1)
        days_left = max(0, (end - now).days)
        return {
            ATTR_CYCLE_CONSUMPTION: round(consumption, 3),
            ATTR_DAYS_IN_CYCLE: days_in,
            ATTR_DAYS_REMAINING: days_left,
            "fixed_charge": self._config.get(CONF_FIXED_CHARGE, 0.0),
            "tax_percent": self._config.get(CONF_TAX_PERCENT, 0.0),
        }


class CycleConsumptionSensor(BaseCostSensor):
    """kWh consumed in the current billing cycle."""

    _attr_name = "Cycle Consumption"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:lightning-bolt"

    @property
    def native_value(self) -> float | None:
        return round(self._get_cycle_consumption(), 3)


class ForecastBillSensor(BaseCostSensor):
    """Simple linear forecast of bill at cycle end."""

    _attr_name = "Forecast Bill"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_native_unit_of_measurement = self._config.get(CONF_CURRENCY, "USD")

    @property
    def native_value(self) -> float | None:
        consumption = self._get_cycle_consumption()
        billing_day = self._config.get(CONF_BILLING_CYCLE_DAY, 1)
        start, end = _get_cycle_bounds(billing_day)
        now = dt_util.now()
        days_elapsed = max(1, (now - start).total_seconds() / 86400)
        total_days = max(1, (end - start).total_seconds() / 86400)

        # Linear extrapolation of consumption
        projected_kwh = consumption * (total_days / days_elapsed)

        mode = self._config.get(CONF_RATE_MODE, RATE_MODE_TIERED)
        fixed = float(self._config.get(CONF_FIXED_CHARGE, 0.0))
        tax_pct = float(self._config.get(CONF_TAX_PERCENT, 0.0))

        if mode in (RATE_MODE_TIERED, RATE_MODE_COMBINED):
            energy_cost, _, _ = _calc_tiered_cost(
                projected_kwh, self._config.get(CONF_TIERS, [])
            )
        else:
            rate, _ = _get_current_tou_rate(self._config.get(CONF_TOU_PERIODS, []))
            energy_cost = projected_kwh * rate

        subtotal = energy_cost + fixed
        return round(subtotal * (1 + tax_pct / 100.0), 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        billing_day = self._config.get(CONF_BILLING_CYCLE_DAY, 1)
        start, end = _get_cycle_bounds(billing_day)
        now = dt_util.now()
        return {
            "cycle_start": start.isoformat(),
            "cycle_end": end.isoformat(),
            "days_elapsed": round((now - start).total_seconds() / 86400, 1),
            "method": "linear_extrapolation",
        }


class PrepaidBalanceSensor(BaseCostSensor):
    """Track prepaid meter balance (Aruba / Caribbean / many African & Asian utilities)."""

    _attr_name = "Prepaid Balance"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:wallet"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_native_unit_of_measurement = self._config.get(CONF_CURRENCY, "USD")

    @property
    def native_value(self) -> float | None:
        data = self.hass.data[DOMAIN][self._entry.entry_id]
        return round(data.get("prepaid_balance", 0.0), 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "note": "Use service tiered_tou_energy_cost.set_prepaid_balance or add_prepaid_credit after buying power",
            "low_balance_event": f"{DOMAIN}_prepaid_low",
        }
