"""Find Apollo TAB-1 tablets in the device registry."""

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, ESPHOME_DOMAIN, TABLET_MANUFACTURER, TABLET_MODEL


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


@callback
def async_track_tablet_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    platform: str,
    unique_id: Callable[[str], str],
    make_entity: Callable[[str, dr.DeviceEntry, str], Entity],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Keep one entity per tablet on a platform, following the device registry.

    Entities sit on the tablet's ESPHome device. A unique ID holds the MAC,
    so a tablet keeps its entity when its device ID changes. Entities of
    tablets that are gone are removed, also those removed while the
    integration was not loaded.
    """
    entity_registry = er.async_get(hass)
    # Unique IDs of the entities this platform has added.
    added: set[str] = set()
    unloaded = False

    @callback
    def mark_unloaded() -> None:
        """Block deferred reconciles from adding entities after unload."""
        nonlocal unloaded
        unloaded = True

    entry.async_on_unload(mark_unloaded)

    @callback
    def reconcile() -> None:
        """Make the added entities match the tablets in the device registry."""
        tablets = async_get_tablets(hass)
        wanted = {unique_id(mac): (mac, device) for mac, device in tablets.items()}

        for gone in added - wanted.keys():
            entity_id = entity_registry.async_get_entity_id(platform, DOMAIN, gone)
            if entity_id is not None:
                entity_registry.async_remove(entity_id)
            added.discard(gone)

        # A deferred call can run after this setup was unloaded, even when the
        # entry has been set up again since.
        can_add = not unloaded
        for wanted_id, (mac, device) in wanted.items():
            if wanted_id not in added:
                if can_add:
                    added.add(wanted_id)
                    async_add_entities([make_entity(mac, device, wanted_id)])
                continue
            entity_id = entity_registry.async_get_entity_id(platform, DOMAIN, wanted_id)
            if entity_id is None:
                # Adding is asynchronous, so the registry entry can lag behind.
                continue
            registered = entity_registry.async_get(entity_id)
            if registered is not None and registered.device_id != device.id:
                # The tablet was registered again under another device ID.
                entity_registry.async_update_entity(entity_id, device_id=device.id)

    @callback
    def device_registry_updated(
        event: Event[dr.EventDeviceRegistryUpdatedData],
    ) -> None:
        """Reconcile after the entity registry has handled the same change.

        When a device is removed, the entity registry detaches the entity from
        it within the same event, and the entity must process that update
        before its registry entry is touched. So every action is deferred.
        """
        hass.loop.call_soon(reconcile)

    # Drop entities of tablets that were removed while the integration was not
    # loaded.
    current = {unique_id(mac) for mac in async_get_tablets(hass)}
    for registered in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if registered.domain == platform and registered.unique_id not in current:
            entity_registry.async_remove(registered.entity_id)

    reconcile()

    entry.async_on_unload(
        hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, device_registry_updated)
    )
