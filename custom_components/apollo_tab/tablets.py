"""Find Apollo TAB-1 tablets in the device registry."""

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import ESPHOME_DOMAIN, TABLET_MANUFACTURER, TABLET_MODEL


@callback
def async_tablet_mac(hass: HomeAssistant, device: dr.DeviceEntry) -> str | None:
    """Return the MAC address of a tablet, or None if the device is not one.

    A tablet is the main device of an ESPHome config entry whose manufacturer
    and model come from the TAB-1 firmware's project name.
    """
    if device.manufacturer != TABLET_MANUFACTURER or device.model != TABLET_MODEL:
        return None
    entry = hass.config_entries.async_get_entry(device.config_entry_id)
    if entry is None or entry.domain != ESPHOME_DOMAIN:
        return None
    # ESPHome sub-devices share the manufacturer and model but have no MAC.
    macs = sorted(
        value for kind, value in device.connections if kind == dr.CONNECTION_NETWORK_MAC
    )
    return macs[0] if macs else None


@callback
def async_get_tablets(hass: HomeAssistant) -> dict[str, dr.DeviceEntry]:
    """Return every tablet in the device registry, keyed by MAC address."""
    device_registry = dr.async_get(hass)
    tablets: dict[str, dr.DeviceEntry] = {}
    for entry in hass.config_entries.async_entries(ESPHOME_DOMAIN):
        for device in dr.async_entries_for_config_entry(
            device_registry, entry.entry_id
        ):
            if (mac := async_tablet_mac(hass, device)) is not None:
                tablets[mac] = device
    return tablets
