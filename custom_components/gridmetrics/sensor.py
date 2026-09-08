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
    VERSION,
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
    CONF_SOLAR_CAPACITY_KWP,
    CONF_INTERCONNECT_RATE,
    CONF_INTERCONNECT_FREE_KWP,
    RATE_MODE_TIERED,
    RATE_MODE_TOU,
    RATE_MODE_COMBINED,
    DEFAULT_EXPORT_RATE,
    DEFAULT_SOLAR_CAPACITY_KWP,
    DEFAULT_INTERCONNECT_RATE,
    DEFAULT_INTERCONNECT_FREE_KWP,
)
from .calculations import (
    calc_tiered_cost as _calc_tiered_cost,
    get_current_tou_rate as _get_current_tou_rate,
    get_cycle_bounds as _get_cycle_bounds,
    calc_interconnect_fee as _calc_interconnect_fee,
    calc_export_credit as _calc_export_credit,
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
    if config.get(CONF_SETUP_TYPE) == SETUP_SOLAR_GRID:
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
    """Estimate instantaneous power (W) from a cumulative kWh sensor."""
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
            "sw_version": VERSION,
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
        self._restored = False

    def _restore_from_store(self) -> None:
        if self._restored:
            return
        data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        if data is None:
            return
        key = f"accum_{self.__class__.__name__}"
        saved = data.get(key)
        if saved is not None:
            self._kwh = float(saved)
        self._restored = True

    def _persist(self) -> None:
        data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        if data is None:
            return
        key = f"accum_{self.__class__.__name__}"
        data[key] = self._kwh
        # Also expose the live totals used by cost sensors
        if isinstance(self, HomeConsumptionEnergySensor):
            data["home_consumption_kwh"] = self._kwh
        elif isinstance(self, GridImportEnergySensor):
            data["grid_import_kwh"] = self._kwh
        elif isinstance(self, GridExportEnergySensor):
            data["grid_export_kwh"] = self._kwh
        async_save_cycle_state(self.hass, self._entry.entry_id)

    def _accumulate(self, power_w: float) -> float:
        self._restore_from_store()
        now = dt_util.utcnow()
        if self._last_ts is not None and self._last_w is not None:
            hours = (now - self._last_ts).total_seconds() / 3600.0
            avg_w = (self._last_w + power_w) / 2.0
            self._kwh += max(0.0, avg_w) * hours / 1000.0
        self._last_w = power_w
        self._last_ts = now
        self._persist()
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
            "sw_version": VERSION,
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

    def _net_metered(self) -> bool:
        """True when this entry uses solar net-metering (import/export flows)."""
        return (
            self._config.get(CONF_SETUP_TYPE) == SETUP_SOLAR_GRID
            or self._source == "derived_home_consumption"
        )

    def _get_source_kwh(self) -> float | None:
        if self._net_metered():
            data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
            return data.get("home_consumption_kwh")
        return _safe_float(self.hass.states.get(self._source))

    def _get_net_and_flows(self) -> tuple[float, float, float]:
        """Return (net_billed_kwh, cycle_import_kwh, cycle_export_kwh).

        Solar / net-metered path
        ------------------------
        net = max(0, cycle_import - cycle_export)
        cycle_import / cycle_export are deltas from the cycle baseline.

        Grid-only path
        --------------
        net = delta of the configured source energy sensor for this cycle.
        cycle_import / cycle_export are returned as 0.0 so attributes never
        leak the utility meter's lifetime reading (Bug 2).
        """
        data = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        if data is None:
            return 0.0, 0.0, 0.0

        billing_day = self._config.get(CONF_BILLING_CYCLE_DAY, 1)
        cycle_start, _ = _get_cycle_bounds(billing_day, dt_util.now())
        last_reset = data.get("last_cycle_start")
        new_cycle = last_reset is None or last_reset < cycle_start

        if self._net_metered():
            # Live totals from energy accumulators (defaulted to 0.0 at setup
            # so a cost-sensor read that races the first accumulator tick still
            # stamps a true-zero baseline — Bug 1 fix).
            current_imp = float(data.get("grid_import_kwh") or 0.0)
            current_exp = float(data.get("grid_export_kwh") or 0.0)

            if new_cycle:
                data["cycle_start_import_kwh"] = current_imp
                data["cycle_start_export_kwh"] = current_exp
                data["last_cycle_start"] = cycle_start
                async_save_cycle_state(self.hass, self._entry.entry_id)
                return 0.0, 0.0, 0.0

            start_imp = float(data.get("cycle_start_import_kwh") or 0.0)
            start_exp = float(data.get("cycle_start_export_kwh") or 0.0)
            cycle_imp = max(0.0, current_imp - start_imp)
            cycle_exp = max(0.0, current_exp - start_exp)
            net = max(0.0, cycle_imp - cycle_exp)
            return net, cycle_imp, cycle_exp

        # ---- Grid-only ----
        current = self._get_source_kwh()
        if current is None:
            return 0.0, 0.0, 0.0

        if new_cycle:
            data["cycle_start_kwh"] = current
            data["last_cycle_start"] = cycle_start
            async_save_cycle_state(self.hass, self._entry.entry_id)
            return 0.0, 0.0, 0.0

        start_kwh = data.get("cycle_start_kwh")
        if start_kwh is None:
            data["cycle_start_kwh"] = current
            async_save_cycle_state(self.hass, self._entry.entry_id)
            return 0.0, 0.0, 0.0

        net = max(0.0, current - float(start_kwh))
        # Import/export attributes stay 0 for grid-only (no bogus lifetime leak)
        return net, 0.0, 0.0

    def _get_cycle_consumption(self) -> float:
        """Net billed consumption for the current cycle."""
        net, _, _ = self._get_net_and_flows()
        return net

    def _calc_bill_components(self, net_kwh: float, cycle_imp: float, cycle_exp: float) -> dict:
        """Shared bill math for Estimated + Forecast sensors."""
        mode = self._config.get(CONF_RATE_MODE, RATE_MODE_TIERED)
        fixed = float(self._config.get(CONF_FIXED_CHARGE, 0.0) or 0.0)
        tax_pct = float(self._config.get(CONF_TAX_PERCENT, 0.0) or 0.0)
        export_rate = float(self._config.get(CONF_EXPORT_RATE, DEFAULT_EXPORT_RATE) or 0.0)
        capacity = float(self._config.get(CONF_SOLAR_CAPACITY_KWP, DEFAULT_SOLAR_CAPACITY_KWP) or 0.0)
        ic_rate = float(self._config.get(CONF_INTERCONNECT_RATE, DEFAULT_INTERCONNECT_RATE) or 0.0)
        ic_free = float(self._config.get(CONF_INTERCONNECT_FREE_KWP, DEFAULT_INTERCONNECT_FREE_KWP) or 0.0)

        energy_cost = 0.0
        if mode == RATE_MODE_TIERED:
            energy_cost, _, _ = _calc_tiered_cost(net_kwh, self._config.get(CONF_TIERS, []))
        elif mode == RATE_MODE_TOU:
            rate, _ = _get_current_tou_rate(self._config.get(CONF_TOU_PERIODS, []))
            energy_cost = net_kwh * rate
        elif mode == RATE_MODE_COMBINED:
            energy_cost, _, _ = _calc_tiered_cost(net_kwh, self._config.get(CONF_TIERS, []))

        interconnect = _calc_interconnect_fee(capacity, ic_rate, ic_free)
        credit = _calc_export_credit(cycle_exp, cycle_imp, export_rate)

        subtotal = energy_cost + fixed + interconnect - credit
        total = subtotal * (1 + tax_pct / 100.0)

        return {
            "energy_cost": round(energy_cost, 4),
            "fixed": round(fixed, 4),
            "interconnect": round(interconnect, 4),
            "export_credit": round(credit, 4),
            "subtotal": round(subtotal, 4),
            "tax_pct": tax_pct,
            "total": round(total, 2),
            "net_kwh": round(net_kwh, 3),
            "cycle_import_kwh": round(cycle_imp, 3),
            "cycle_export_kwh": round(cycle_exp, 3),
            "capacity_kwp": capacity,
        }


class MarginalRateSensor(BaseCostSensor):
    _attr_name = "Marginal Rate"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:cash"

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
    """Running estimated bill – includes interconnect fee & export credit."""

    _attr_name = "Estimated Bill to Date"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:receipt-text"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_native_unit_of_measurement = self._config.get(CONF_CURRENCY, "USD")

    @property
    def native_value(self) -> float | None:
        try:
            net, imp, exp = self._get_net_and_flows()
            components = self._calc_bill_components(net, imp, exp)
            return components["total"]
        except Exception as err:
            _LOGGER.debug("Estimated bill calc error: %s", err)
            return 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        try:
            net, imp, exp = self._get_net_and_flows()
            return self._calc_bill_components(net, imp, exp)
        except Exception:
            return {}


class CycleConsumptionSensor(BaseCostSensor):
    _attr_name = "Cycle Consumption"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:lightning-bolt"

    @property
    def native_value(self) -> float | None:
        return round(self._get_cycle_consumption(), 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        net, imp, exp = self._get_net_and_flows()
        return {
            "cycle_import_kwh": round(imp, 3),
            "cycle_export_kwh": round(exp, 3),
            "net_kwh": round(net, 3),
        }


class ForecastBillSensor(BaseCostSensor):
    """Forecast bill – projects net kWh and applies same fee/credit structure."""

    _attr_name = "Forecast Bill"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_native_unit_of_measurement = self._config.get(CONF_CURRENCY, "USD")

    @property
    def native_value(self) -> float | None:
        try:
            billing_day = self._config.get(CONF_BILLING_CYCLE_DAY, 1)
            now = dt_util.now()
            start, end = _get_cycle_bounds(billing_day, now)
            days_elapsed = max(1.0, (now - start).total_seconds() / 86400)
            total_days = max(1.0, (end - start).total_seconds() / 86400)
            factor = total_days / days_elapsed

            net, imp, exp = self._get_net_and_flows()
            if self._net_metered():
                proj_imp = imp * factor
                proj_exp = exp * factor
                proj_net = max(0.0, proj_imp - proj_exp)
            else:
                proj_net = net * factor
                proj_imp, proj_exp = proj_net, 0.0

            components = self._calc_bill_components(proj_net, proj_imp, proj_exp)
            return components["total"]
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
