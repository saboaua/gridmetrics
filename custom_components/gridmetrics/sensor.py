"""Sensors for GridMetrics."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from . import async_save_cycle_state
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
    CONF_SETUP_TYPE,
    SETUP_SOLAR_GRID,
    CONF_SOLAR_SENSOR,
    CONF_SOLAR_IS_ENERGY,
    CONF_GRID_SENSOR,
    CONF_GRID_IS_ENERGY,
    CONF_GRID_PHASES,
    CONF_GRID_SIGN,
    CONF_EXPORT_RATE,
    RATE_MODE_TIERED,
    RATE_MODE_TOU,
    RATE_MODE_COMBINED,
)
from .calculations import (
    calc_tiered_cost as _calc_tiered_cost,
    get_current_tou_rate as _get_current_tou_rate,
    get_cycle_bounds as _get_cycle_bounds,
)

_LOGGER = logging.getLogger(__name__)


def _safe_float(state) -> float | None:
    if state is None or state.state in ("unknown", "unavailable", None):
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GridMetrics sensors."""
    config = {**entry.data, **entry.options}
    name_prefix = entry.title or "GridMetrics"

    entities: list[SensorEntity] = [
        MarginalRateSensor(hass, entry, config, name_prefix),
        EstimatedBillSensor(hass, entry, config, name_prefix),
        CycleConsumptionSensor(hass, entry, config, name_prefix),
        ForecastBillSensor(hass, entry, config, name_prefix),
    ]

    if config.get(CONF_PREPAID_ENABLED):
        entities.append(PrepaidBalanceSensor(hass, entry, config, name_prefix))

    # Solar + grid derived sensors
    if config.get(CONF_SETUP_TYPE) == SETUP_SOLAR_GRID or config.get("has_solar"):
        entities.extend(
            [
                SolarProductionPowerSensor(hass, entry, config, name_prefix),
                GridImportPowerSensor(hass, entry, config, name_prefix),
                GridExportPowerSensor(hass, entry, config, name_prefix),
                HomeConsumptionPowerSensor(hass, entry, config, name_prefix),
                SolarProductionEnergySensor(hass, entry, config, name_prefix),
                GridImportEnergySensor(hass, entry, config, name_prefix),
                GridExportEnergySensor(hass, entry, config, name_prefix),
                HomeConsumptionEnergySensor(hass, entry, config, name_prefix),
            ]
        )

    async_add_entities(entities)


def _derive_power_w(
    hass: HomeAssistant, entry_id: str | None, entity_id: str, raw_kwh: float
) -> float:
    """Estimate instantaneous power (W) from a cumulative kWh sensor.

    Used when the solar/grid source is marked "cumulative kWh, not live
    Watts" (CONF_SOLAR_IS_ENERGY / CONF_GRID_IS_ENERGY). Previously that
    flag caused the reading to be discarded entirely (always 0) - this
    instead tracks the last value/timestamp per entity_id and reports
    the rate of change as watts, same as any energy-to-power estimate.
    A negative delta (counter reset/rollover) reports 0 for that tick
    rather than a bogus negative power.
    """
    if entry_id is None:
        return 0.0
    store = hass.data.get(DOMAIN, {}).get(entry_id)
    if store is None:
        return 0.0
    tracker = store.setdefault("energy_derive", {})
    now = dt_util.utcnow()
    last_kwh, last_ts = tracker.get(entity_id, (None, None))
    power = 0.0
    if last_kwh is not None and last_ts is not None:
        hours = (now - last_ts).total_seconds() / 3600.0
        if hours > 0:
            delta = raw_kwh - last_kwh
            if delta >= 0:
                power = (delta / hours) * 1000.0
    tracker[entity_id] = (raw_kwh, now)
    return max(0.0, power)


def _read_solar_power(
    hass: HomeAssistant, config: dict, entry_id: str | None = None
) -> float:
    entity_id = config.get(CONF_SOLAR_SENSOR)
    if not entity_id:
        return 0.0
    val = _safe_float(hass.states.get(entity_id))
    if val is None:
        return 0.0
    if config.get(CONF_SOLAR_IS_ENERGY):
        return _derive_power_w(hass, entry_id, entity_id, val)
    return max(0.0, val)


def _read_grid_power(
    hass: HomeAssistant, config: dict, entry_id: str | None = None
) -> float:
    """Signed grid power: positive = import, negative = export."""
    phases = config.get(CONF_GRID_PHASES) or []
    sign = config.get(CONF_GRID_SIGN, "positive_import")
    is_energy = config.get(CONF_GRID_IS_ENERGY)

    if phases:
        total = 0.0
        for eid in phases:
            val = _safe_float(hass.states.get(eid))
            if val is None:
                continue
            total += (
                _derive_power_w(hass, entry_id, eid, val) if is_energy else val
            )
        raw = total
    else:
        entity_id = config.get(CONF_GRID_SENSOR)
        if not entity_id:
            return 0.0
        val = _safe_float(hass.states.get(entity_id))
        if val is None:
            return 0.0
        raw = _derive_power_w(hass, entry_id, entity_id, val) if is_energy else val

    if sign == "positive_export":
        return -raw
    return raw


def _tracked_entities(config: dict) -> list[str]:
    entities = []
    if config.get(CONF_SOLAR_SENSOR):
        entities.append(config[CONF_SOLAR_SENSOR])
    if config.get(CONF_GRID_SENSOR):
        entities.append(config[CONF_GRID_SENSOR])
    for p in config.get(CONF_GRID_PHASES) or []:
        entities.append(p)
    src = config.get(CONF_SOURCE_SENSOR)
    if src and src != "derived_home_consumption":
        entities.append(src)
    return entities


class SolarBaseSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hass, entry, config, name_prefix):
        self.hass = hass
        self._entry = entry
        self._config = config
        self._attr_unique_id = f"{entry.entry_id}_{self.__class__.__name__}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": name_prefix,
            "manufacturer": "GridMetrics",
            "model": "solar_net_metering",
            "sw_version": "0.2.2",
        }
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        entities = _tracked_entities(self._config)
        if entities:
            self._unsub = async_track_state_change_event(
                self.hass, entities, self._handle_change
            )
        self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _handle_change(self, event) -> None:
        self.async_schedule_update_ha_state(True)


class SolarProductionPowerSensor(SolarBaseSensor):
    _attr_name = "Solar Production"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_icon = "mdi:solar-power"

    @property
    def native_value(self) -> float:
        return round(_read_solar_power(self.hass, self._config, self._entry.entry_id), 1)


class GridImportPowerSensor(SolarBaseSensor):
    _attr_name = "Grid Import"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_icon = "mdi:transmission-tower-import"

    @property
    def native_value(self) -> float:
        return round(max(0.0, _read_grid_power(self.hass, self._config, self._entry.entry_id)), 1)


class GridExportPowerSensor(SolarBaseSensor):
    _attr_name = "Grid Export"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_icon = "mdi:transmission-tower-export"

    @property
    def native_value(self) -> float:
        return round(max(0.0, -_read_grid_power(self.hass, self._config, self._entry.entry_id)), 1)


class HomeConsumptionPowerSensor(SolarBaseSensor):
    _attr_name = "Home Consumption"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_icon = "mdi:home-lightning-bolt"

    @property
    def native_value(self) -> float:
        solar = _read_solar_power(self.hass, self._config, self._entry.entry_id)
        grid = _read_grid_power(self.hass, self._config, self._entry.entry_id)
        return round(max(0.0, solar + grid), 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        solar = _read_solar_power(self.hass, self._config, self._entry.entry_id)
        grid = _read_grid_power(self.hass, self._config, self._entry.entry_id)
        return {
            "solar_w": round(solar, 1),
            "grid_signed_w": round(grid, 1),
            "formula": "solar + grid_import - grid_export",
        }


class _EnergyAccumulator(SolarBaseSensor):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._kwh = 0.0
        self._last_w = None
        self._last_ts = None

    def _accumulate(self, power_w: float) -> float:
        now = dt_util.utcnow()
        if self._last_ts is not None and self._last_w is not None:
            hours = (now - self._last_ts).total_seconds() / 3600.0
            avg_w = (self._last_w + power_w) / 2.0
            self._kwh += max(0.0, avg_w) * hours / 1000.0
        self._last_w = power_w
        self._last_ts = now
        # Persist for cost sensors
        data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        if data is not None and isinstance(self, HomeConsumptionEnergySensor):
            data["home_consumption_kwh"] = self._kwh
        return self._kwh


class SolarProductionEnergySensor(_EnergyAccumulator):
    _attr_name = "Solar Production Energy"
    _attr_icon = "mdi:solar-power"

    @property
    def native_value(self) -> float:
        return round(self._accumulate(_read_solar_power(self.hass, self._config, self._entry.entry_id)), 4)


class GridImportEnergySensor(_EnergyAccumulator):
    _attr_name = "Grid Import Energy"
    _attr_icon = "mdi:transmission-tower-import"

    @property
    def native_value(self) -> float:
        g = _read_grid_power(self.hass, self._config, self._entry.entry_id)
        return round(self._accumulate(max(0.0, g)), 4)


class GridExportEnergySensor(_EnergyAccumulator):
    _attr_name = "Grid Export Energy"
    _attr_icon = "mdi:transmission-tower-export"

    @property
    def native_value(self) -> float:
        g = _read_grid_power(self.hass, self._config, self._entry.entry_id)
        return round(self._accumulate(max(0.0, -g)), 4)


class HomeConsumptionEnergySensor(_EnergyAccumulator):
    _attr_name = "Home Consumption Energy"
    _attr_icon = "mdi:home-lightning-bolt"

    @property
    def native_value(self) -> float:
        solar = _read_solar_power(self.hass, self._config, self._entry.entry_id)
        grid = _read_grid_power(self.hass, self._config, self._entry.entry_id)
        return round(self._accumulate(max(0.0, solar + grid)), 4)


class BaseCostSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hass, entry, config, name_prefix):
        self.hass = hass
        self._entry = entry
        self._config = config
        self._attr_unique_id = f"{entry.entry_id}_{self.__class__.__name__}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": name_prefix,
            "manufacturer": "GridMetrics",
            "model": config.get(CONF_RATE_MODE, "tiered"),
            "sw_version": "0.2.2",
        }
        self._source = config.get(CONF_SOURCE_SENSOR)
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        entities = _tracked_entities(self._config)
        if self._source and self._source != "derived_home_consumption":
            entities.append(self._source)
        if entities:
            self._unsub = async_track_state_change_event(
                self.hass, list(set(entities)), self._handle_source_change
            )
        self.async_schedule_update_ha_state(True)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _handle_source_change(self, event) -> None:
        self.async_schedule_update_ha_state(True)

    def _get_source_kwh(self) -> float | None:
        if self._source == "derived_home_consumption" or self._config.get(
            CONF_SETUP_TYPE
        ) == SETUP_SOLAR_GRID:
            data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
            return data.get("home_consumption_kwh")
        return _safe_float(self.hass.states.get(self._source))

    def _get_cycle_consumption(self) -> float:
        current = self._get_source_kwh()
        if current is None:
            return 0.0

        data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        if data is None:
            # Entry is mid-reload (e.g. options were just saved) and
            # hasn't repopulated hass.data yet - report 0 instead of
            # raising, so a burst of source-sensor updates during the
            # reload window can't hammer the logger with KeyErrors.
            return 0.0
        start_kwh = data.get("cycle_start_kwh")
        billing_day = self._config.get(CONF_BILLING_CYCLE_DAY, 1)
        cycle_start, _ = _get_cycle_bounds(billing_day, dt_util.now())

        last_reset = data.get("last_cycle_start")
        if last_reset is None or last_reset < cycle_start:
            data["cycle_start_kwh"] = current
            data["last_cycle_start"] = cycle_start
            async_save_cycle_state(self.hass, self._entry.entry_id)
            return 0.0

        if start_kwh is None:
            data["cycle_start_kwh"] = current
            async_save_cycle_state(self.hass, self._entry.entry_id)
            return 0.0

        return max(0.0, current - start_kwh)


class MarginalRateSensor(BaseCostSensor):
    _attr_name = "Marginal Rate"
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
                tou_rate, _ = _get_current_tou_rate(
                    self._config.get(CONF_TOU_PERIODS, [])
                )
                return round(max(marginal, tou_rate), 6)
            return round(marginal, 6)
        return None


class EstimatedBillSensor(BaseCostSensor):
    """Running estimated bill - no MONETARY device_class (HA compatibility)."""

    _attr_name = "Estimated Bill to Date"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:receipt-text"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_native_unit_of_measurement = self._config.get(CONF_CURRENCY, "USD")

    @property
    def native_value(self) -> float | None:
        try:
            consumption = self._get_cycle_consumption()
            mode = self._config.get(CONF_RATE_MODE, RATE_MODE_TIERED)
            fixed = float(self._config.get(CONF_FIXED_CHARGE, 0.0) or 0.0)
            tax_pct = float(self._config.get(CONF_TAX_PERCENT, 0.0) or 0.0)

            energy_cost = 0.0
            if mode == RATE_MODE_TIERED:
                energy_cost, _, _ = _calc_tiered_cost(
                    consumption, self._config.get(CONF_TIERS, [])
                )
            elif mode == RATE_MODE_TOU:
                rate, _ = _get_current_tou_rate(self._config.get(CONF_TOU_PERIODS, []))
                energy_cost = consumption * rate
            elif mode == RATE_MODE_COMBINED:
                energy_cost, _, _ = _calc_tiered_cost(
                    consumption, self._config.get(CONF_TIERS, [])
                )

            subtotal = energy_cost + fixed
            return round(subtotal * (1 + tax_pct / 100.0), 2)
        except Exception as err:
            _LOGGER.debug("Estimated bill calc error: %s", err)
            return 0.0


class CycleConsumptionSensor(BaseCostSensor):
    _attr_name = "Cycle Consumption"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:lightning-bolt"

    @property
    def native_value(self) -> float | None:
        return round(self._get_cycle_consumption(), 3)


class ForecastBillSensor(BaseCostSensor):
    """Forecast bill - no MONETARY device_class (HA compatibility)."""

    _attr_name = "Forecast Bill"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_native_unit_of_measurement = self._config.get(CONF_CURRENCY, "USD")

    @property
    def native_value(self) -> float | None:
        try:
            consumption = self._get_cycle_consumption()
            billing_day = self._config.get(CONF_BILLING_CYCLE_DAY, 1)
            now = dt_util.now()
            start, end = _get_cycle_bounds(billing_day, now)
            days_elapsed = max(1.0, (now - start).total_seconds() / 86400)
            total_days = max(1.0, (end - start).total_seconds() / 86400)
            projected_kwh = consumption * (total_days / days_elapsed)

            mode = self._config.get(CONF_RATE_MODE, RATE_MODE_TIERED)
            fixed = float(self._config.get(CONF_FIXED_CHARGE, 0.0) or 0.0)
            tax_pct = float(self._config.get(CONF_TAX_PERCENT, 0.0) or 0.0)

            if mode in (RATE_MODE_TIERED, RATE_MODE_COMBINED):
                energy_cost, _, _ = _calc_tiered_cost(
                    projected_kwh, self._config.get(CONF_TIERS, [])
                )
            else:
                rate, _ = _get_current_tou_rate(self._config.get(CONF_TOU_PERIODS, []))
                energy_cost = projected_kwh * rate

            subtotal = energy_cost + fixed
            return round(subtotal * (1 + tax_pct / 100.0), 2)
        except Exception as err:
            _LOGGER.debug("Forecast bill calc error: %s", err)
            return 0.0


class PrepaidBalanceSensor(BaseCostSensor):
    _attr_name = "Prepaid Balance"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:wallet"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_native_unit_of_measurement = self._config.get(CONF_CURRENCY, "USD")

    @property
    def native_value(self) -> float | None:
        data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
        return round(data.get("prepaid_balance", 0.0), 2)
