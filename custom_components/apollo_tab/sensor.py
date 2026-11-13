"""Dashboard engine status sensor, one per tablet."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .sender import (
    ENGINE_NOT_INSTALLED,
    ENGINE_STATES,
    SIGNAL_TABLETS_UPDATED,
    TabletSender,
)
from .tablets import async_track_tablet_entities

if TYPE_CHECKING:
    from . import ApolloTabConfigEntry


def engine_unique_id(mac: str) -> str:
    """Return the unique ID of a tablet's dashboard engine sensor."""
    return f"{mac}_dashboard_engine"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ApolloTabConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a sensor for each tablet and follow device registry changes."""
    sender = entry.runtime_data.sender
    async_track_tablet_entities(
        hass,
        entry,
        "sensor",
        engine_unique_id,
        lambda mac, device, unique_id: DashboardEngineSensor(
            sender, mac, device, unique_id
        ),
        async_add_entities,
    )


class DashboardEngineSensor(SensorEntity, RestoreEntity):
    """Whether the tablet's firmware has the dashboard engine HA can talk to.

    not_installed: no engine found. ready: the engine speaks HA's protocol.
    update_needed: the engine and HA have no protocol version in common.
    The last known state stays while the tablet is offline, also across a
    restart of Home Assistant: until the tablet has answered again, the
    state from before the restart is shown. A tablet never reached shows
    not_installed.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_options = ENGINE_STATES
    _attr_should_poll = False
    _attr_translation_key = "dashboard_engine"

    def __init__(
        self, sender: TabletSender, mac: str, device: dr.DeviceEntry, unique_id: str
    ) -> None:
        """Attach the sensor to the tablet's existing ESPHome device."""
        self._sender = sender
        self._mac = mac
        self._attr_unique_id = unique_id
        self.device_entry = device
        # (state, engine version) from before a restart.
        self._restored: tuple[str, str | None] | None = None

    async def async_added_to_hass(self) -> None:
        """Take the state from before a restart, then follow the tablet."""
        last = await self.async_get_last_state()
        if last is not None and last.state in ENGINE_STATES:
            version = last.attributes.get("engine_version")
            self._restored = (
                last.state,
                version if isinstance(version, str) and version else None,
            )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_TABLETS_UPDATED, self._async_tablets_updated
            )
        )

    @callback
    def _async_tablets_updated(self) -> None:
        """Write the new state."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        """Return the engine state."""
        session = self._sender.session_for(self._mac)
        if session is not None and session.engine_known:
            return session.engine_state
        if self._restored is not None:
            return self._restored[0]
        return ENGINE_NOT_INSTALLED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the engine version the tablet reported, or None."""
        session = self._sender.session_for(self._mac)
        if session is not None and session.engine_known:
            return {"engine_version": session.engine or None}
        if self._restored is not None:
            return {"engine_version": self._restored[1]}
        return {"engine_version": None}
