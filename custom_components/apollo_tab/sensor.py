"""Dashboard engine status sensor, one per tablet."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import EntityCategory
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .tablets import async_get_tablets

ENGINE_NOT_INSTALLED = "not_installed"


def engine_unique_id(mac: str) -> str:
    """Return the unique ID of a tablet's dashboard engine sensor."""
    return f"{mac}_dashboard_engine"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a sensor for each tablet and follow device registry changes."""
    entity_registry = er.async_get(hass)
    # Unique IDs of the sensors this platform has added. A unique ID holds the
    # MAC, so a tablet keeps one sensor even if its device ID changes.
    added: set[str] = set()

    @callback
    def reconcile() -> None:
        """Make the added sensors match the tablets in the device registry."""
        tablets = async_get_tablets(hass)
        wanted = {engine_unique_id(mac): device for mac, device in tablets.items()}

        for unique_id in added - wanted.keys():
            entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is not None:
                entity_registry.async_remove(entity_id)
            added.discard(unique_id)

        # A deferred call can run after unload, when the platform is gone.
        can_add = entry.state in (
            ConfigEntryState.SETUP_IN_PROGRESS,
            ConfigEntryState.LOADED,
        )
        for unique_id, device in wanted.items():
            if unique_id not in added:
                if can_add:
                    added.add(unique_id)
                    async_add_entities([DashboardEngineSensor(device, unique_id)])
                continue
            entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
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

        When a device is removed, the entity registry detaches the sensor from
        it within the same event, and the entity must process that update
        before its registry entry is touched. So every action is deferred.
        """
        hass.loop.call_soon(reconcile)

    # Drop sensors of tablets that were removed while the integration was not
    # loaded.
    current = {engine_unique_id(mac) for mac in async_get_tablets(hass)}
    for registered in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if registered.domain == "sensor" and registered.unique_id not in current:
            entity_registry.async_remove(registered.entity_id)

    reconcile()

    entry.async_on_unload(
        hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, device_registry_updated)
    )


class DashboardEngineSensor(SensorEntity):
    """Whether the tablet's firmware includes the dashboard engine.

    No firmware includes it yet, so the state is always "not_installed".
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_native_value = ENGINE_NOT_INSTALLED
    _attr_options = [ENGINE_NOT_INSTALLED]
    _attr_should_poll = False
    _attr_translation_key = "dashboard_engine"

    def __init__(self, device: dr.DeviceEntry, unique_id: str) -> None:
        """Attach the sensor to the tablet's existing ESPHome device."""
        self._attr_unique_id = unique_id
        self.device_entry = device
