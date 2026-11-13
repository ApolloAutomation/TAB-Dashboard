"""The "Dashboard" select: which dashboard a tablet shows. One per tablet."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .assignments import async_show_dashboard
from .const import DOMAIN
from .sender import SIGNAL_TABLETS_UPDATED
from .tablets import async_track_tablet_entities

if TYPE_CHECKING:
    from . import ApolloTabConfigEntry, ApolloTabData


def dashboard_unique_id(mac: str) -> str:
    """Return the unique ID of a tablet's dashboard select."""
    return f"{mac}_dashboard"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ApolloTabConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a select for each tablet and follow device registry changes."""
    data = entry.runtime_data
    async_track_tablet_entities(
        hass,
        entry,
        "select",
        dashboard_unique_id,
        lambda mac, device, unique_id: DashboardSelect(data, mac, device, unique_id),
        async_add_entities,
    )


class DashboardSelect(SelectEntity):
    """Pick the dashboard a tablet shows. Only admins and automations may."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "dashboard"

    def __init__(
        self, data: ApolloTabData, mac: str, device: dr.DeviceEntry, unique_id: str
    ) -> None:
        """Attach the select to the tablet's existing ESPHome device."""
        self._data = data
        self._mac = mac
        self._attr_unique_id = unique_id
        self.device_entry = device

    async def async_added_to_hass(self) -> None:
        """Follow assignments, dashboards and their titles."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_TABLETS_UPDATED, self._async_tablets_updated
            )
        )

    @callback
    def _async_tablets_updated(self) -> None:
        """Write the new state."""
        self.async_write_ha_state()

    def _labels(self) -> dict[str, str]:
        """Return {url_path: option} in the one dashboard order."""
        return self._data.assignments.labels()

    @property
    def options(self) -> list[str]:
        """Return the dashboard titles in the one order."""
        return list(self._labels().values())

    @property
    def current_option(self) -> str | None:
        """Return the title of the assigned dashboard, or None."""
        url_path = self._data.assignments.dashboard(self._mac)
        return self._labels().get(url_path) if url_path is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the assigned dashboard's id, for automations."""
        return {"dashboard_id": self._data.assignments.dashboard(self._mac)}

    async def async_select_option(self, option: str) -> None:
        """Show another dashboard on the tablet.

        Every way of changing the option (select_option, select_next,
        select_first and so on) comes through here, so the admin check is
        here too. Automations have no user and are allowed, once an admin
        approved the tablet by picking its first dashboard.

        A dashboard that cannot be read right now stays in the options, so
        the tablet showing it keeps a name, but it cannot be picked: the
        panel and the show_dashboard action refuse it too.
        """
        data = self._data
        assignments = data.assignments
        url_path = next(
            (path for path, label in self._labels().items() if label == option),
            None,
        )
        session = data.sender.session_for(self._mac)
        if session is None:
            raise ServiceValidationError(
                "This tablet is not known",
                translation_domain=DOMAIN,
                translation_key="unknown_tablet",
            )
        if url_path is None or (
            url_path not in data.manager.layouts
            and url_path != assignments.dashboard(self._mac)
        ):
            raise ServiceValidationError(
                "This dashboard does not exist",
                translation_domain=DOMAIN,
                translation_key="unknown_dashboard",
            )
        await async_show_dashboard(
            self.hass, assignments, self._mac, url_path, session.entry_id, self._context
        )
