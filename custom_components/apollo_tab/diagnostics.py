"""Diagnostics for the Apollo TAB Dashboard integration."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .sensor import engine_unique_id
from .tablets import async_get_tablets


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return the tablets found and their dashboard engine status.

    The output holds no full MAC address. A tablet with its default name ends
    in the last three MAC bytes, put there by the firmware's
    name_add_mac_suffix option. That part of the name is left in, as ESPHome's
    own diagnostics do.
    """
    entity_registry = er.async_get(hass)
    tablets: list[dict[str, Any]] = []
    for mac, device in async_get_tablets(hass).items():
        esphome_entry = hass.config_entries.async_get_entry(device.config_entry_id)
        entity_id = entity_registry.async_get_entity_id(
            "sensor", DOMAIN, engine_unique_id(mac)
        )
        state = hass.states.get(entity_id) if entity_id else None
        tablets.append(
            {
                "device_id": device.id,
                "name": device.name_by_user or device.name,
                "area_id": device.area_id,
                "sw_version": device.sw_version,
                "disabled": device.disabled,
                "esphome_entry_state": (
                    esphome_entry.state.value if esphome_entry else None
                ),
                "engine_entity_id": entity_id,
                "engine_status": state.state if state else None,
            }
        )
    tablets.sort(key=lambda tablet: tablet["device_id"])
    return {"tablet_count": len(tablets), "tablets": tablets}
