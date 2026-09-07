"""Tiered / Time-of-Use Electricity Rate Calculator for Home Assistant."""

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
    CONFIG_ENTRY_VERSION,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

SERVICE_ADD_PREPAID = "add_prepaid_credit"
SERVICE_RESET_CYCLE = "reset_billing_cycle"
SERVICE_SET_BALANCE = "set_prepaid_balance"


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry to the current version.

    No stored data fields have changed between versions to date, so
    this only needs to bump the stamped version number. Keep this
    function around (and add real field migrations here) any time
    VERSION is bumped in config_flow.py, so existing entries never
    get stuck showing the "higher than current version" repair error.
    """
    if entry.version > CONFIG_ENTRY_VERSION:
        # Entry is newer than this installed code supports; refuse cleanly.
        _LOGGER.error(
            "GridMetrics entry '%s' has version %s, newer than supported version %s. "
            "Update the integration before loading this entry.",
            entry.title,
            entry.version,
            CONFIG_ENTRY_VERSION,
        )
        return False

    if entry.version < CONFIG_ENTRY_VERSION:
        _LOGGER.info(
            "Migrating GridMetrics entry '%s' from version %s to %s",
            entry.title,
            entry.version,
            CONFIG_ENTRY_VERSION,
        )
        hass.config_entries.async_update_entry(
            entry, data={**entry.data}, version=CONFIG_ENTRY_VERSION
        )

    return True


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

    # Register services once
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_PREPAID):
        async def handle_add_prepaid(call: ServiceCall) -> None:
            """Add credit to prepaid balance (Aruba / Caribbean style)."""
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
                # Fire event for notifications / automations
                hass.bus.async_fire(
                    f"{DOMAIN}_prepaid_topup",
                    {
                        "entry_id": entry_id,
                        "amount": amount,
                        "new_balance": data["prepaid_balance"],
                    },
                )

        async def handle_reset_cycle(call: ServiceCall) -> None:
            """Manually reset the billing cycle tracking."""
            entry_id = call.data.get("entry_id")
            if entry_id and entry_id in hass.data[DOMAIN]:
                hass.data[DOMAIN][entry_id]["cycle_start_kwh"] = None
                _LOGGER.info("Billing cycle reset for %s", entry_id)

        async def handle_set_balance(call: ServiceCall) -> None:
            """Set absolute prepaid balance (after buying power)."""
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
    else:
        _LOGGER.error(
            "GridMetrics entry '%s' failed to unload cleanly; refusing to "
            "re-setup to avoid a duplicate-platform crash loop",
            entry.title,
        )
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change.

    Uses hass.config_entries.async_reload() rather than a hand-rolled
    unload-then-setup: the built-in helper holds a per-entry lock so an
    options save can't overlap with another in-flight reload, and it
    won't call async_setup_entry again if unload didn't actually
    succeed. Calling async_setup_entry after a failed unload is what
    was driving the "options save spins forever" symptom - the sensor
    platform was still registered from the previous load, so forwarding
    entry setup a second time raised, and the frontend never got a
    completion response for the options dialog.
    """
    await hass.config_entries.async_reload(entry.entry_id)
