"""GridMetrics for Home Assistant."""

from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_PREPAID_ENABLED,
    CONF_PREPAID_BALANCE,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

SERVICE_ADD_PREPAID = "add_prepaid_credit"
SERVICE_RESET_CYCLE = "reset_billing_cycle"
SERVICE_SET_BALANCE = "set_prepaid_balance"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GridMetrics from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "config": entry.data,
        "options": entry.options,
        "cycle_start_kwh": None,
        "prepaid_balance": entry.data.get(CONF_PREPAID_BALANCE, 0.0),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_PREPAID):
        async def handle_add_prepaid(call: ServiceCall) -> None:
            amount = call.data.get("amount", 0.0)
            entry_id = call.data.get("entry_id")
            if entry_id and entry_id in hass.data[DOMAIN]:
                data = hass.data[DOMAIN][entry_id]
                data["prepaid_balance"] = data.get("prepaid_balance", 0.0) + amount
                _LOGGER.info(
                    "Added %.2f to prepaid balance for %s. New balance: %.2f",
                    amount,
                    entry_id,
                    data["prepaid_balance"],
                )
                hass.bus.async_fire(
                    f"{DOMAIN}_prepaid_topup",
                    {
                        "entry_id": entry_id,
                        "amount": amount,
                        "new_balance": data["prepaid_balance"],
                    },
                )

        async def handle_reset_cycle(call: ServiceCall) -> None:
            entry_id = call.data.get("entry_id")
            if entry_id and entry_id in hass.data[DOMAIN]:
                hass.data[DOMAIN][entry_id]["cycle_start_kwh"] = None
                _LOGGER.info("Billing cycle reset for %s", entry_id)

        async def handle_set_balance(call: ServiceCall) -> None:
            amount = call.data.get("amount", 0.0)
            entry_id = call.data.get("entry_id")
            if entry_id and entry_id in hass.data[DOMAIN]:
                hass.data[DOMAIN][entry_id]["prepaid_balance"] = amount
                hass.bus.async_fire(
                    f"{DOMAIN}_prepaid_topup",
                    {
                        "entry_id": entry_id,
                        "amount": amount,
                        "new_balance": amount,
                        "set": True,
                    },
                )

        hass.services.async_register(
            DOMAIN,
            SERVICE_ADD_PREPAID,
            handle_add_prepaid,
            schema=vol.Schema(
                {
                    vol.Required("entry_id"): cv.string,
                    vol.Required("amount"): vol.Coerce(float),
                }
            ),
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESET_CYCLE,
            handle_reset_cycle,
            schema=vol.Schema({vol.Required("entry_id"): cv.string}),
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_BALANCE,
            handle_set_balance,
            schema=vol.Schema(
                {
                    vol.Required("entry_id"): cv.string,
                    vol.Required("amount"): vol.Coerce(float),
                }
            ),
        )

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry from older versions."""
    _LOGGER.info("Migrating GridMetrics config entry from version %s", entry.version)
    if entry.version < 2:
        hass.config_entries.async_update_entry(entry, version=2)
    return True
