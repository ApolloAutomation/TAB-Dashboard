"""The Apollo TAB Dashboard integration."""

from dataclasses import dataclass, field
from typing import Any

import probatio
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    issue_registry as ir,
)
from homeassistant.helpers.typing import ConfigType

from . import websocket
from .assignments import Assignments, async_show_dashboard
from .const import DOMAIN
from .library import Library
from .live import SlotHub
from .manager import DashboardManager
from .protocol import load_contract
from .sender import TabletSender, async_clear_tablets, create_link
from .tablets import async_tablet_mac
from .web import async_add_frontend, async_register_static, async_remove_frontend

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SELECT, Platform.SENSOR]

SERVICE_SHOW_DASHBOARD = "show_dashboard"
SHOW_DASHBOARD_SCHEMA = probatio.Schema(
    {
        probatio.Required("device_id"): cv.string,
        probatio.Required("dashboard"): cv.string,
    }
)


@dataclass
class ApolloTabData:
    """Runtime data of a loaded config entry."""

    library: Library
    manager: DashboardManager
    module_url: str
    slot_hub: SlotHub
    assignments: Assignments
    sender: TabletSender
    # Open websocket subscriptions, each with an async_unload() method.
    subscriptions: set[Any] = field(default_factory=set)


type ApolloTabConfigEntry = ConfigEntry[ApolloTabData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the websocket commands and the action once."""
    websocket.async_register(hass)
    hass.services.async_register(
        DOMAIN,
        SERVICE_SHOW_DASHBOARD,
        _async_show_dashboard,
        schema=SHOW_DASHBOARD_SCHEMA,
    )
    return True


async def _async_show_dashboard(call: ServiceCall) -> None:
    """Show a dashboard on a tablet, both named by id so renames do not matter.

    Admins and automations switch an approved tablet. Only an admin user
    approves a new one, by picking its first dashboard.
    """
    hass = call.hass
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(
            "Apollo TAB Dashboard is not loaded",
            translation_domain=DOMAIN,
            translation_key="not_loaded",
        )
    data: ApolloTabData = entries[0].runtime_data
    device = dr.async_get(hass).async_get(call.data["device_id"])
    mac = async_tablet_mac(hass, device) if device is not None else None
    session = data.sender.session_for(mac) if mac is not None else None
    if session is None:
        raise ServiceValidationError(
            "This tablet is not known",
            translation_domain=DOMAIN,
            translation_key="unknown_tablet",
        )
    if call.data["dashboard"] not in data.manager.layouts:
        raise ServiceValidationError(
            "This dashboard does not exist",
            translation_domain=DOMAIN,
            translation_key="unknown_dashboard",
        )
    await async_show_dashboard(
        hass,
        data.assignments,
        session.mac,
        call.data["dashboard"],
        session.entry_id,
        call.context,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ApolloTabConfigEntry) -> bool:
    """Set up the library, the manager, the sender, the frontend and platforms."""
    module_url = await async_register_static(hass)
    library = Library(hass)
    await library.async_load()
    slot_hub = SlotHub(hass, library)
    manager = DashboardManager(hass, library)
    _contract, icons = await hass.async_add_executor_job(load_contract)
    assignments = Assignments(hass, manager)
    await assignments.async_load()
    sender = TabletSender(
        hass,
        manager=manager,
        library=library,
        slot_hub=slot_hub,
        assignments=assignments,
        link=create_link(hass),
        icons=icons,
    )
    await manager.async_start()
    entry.runtime_data = ApolloTabData(
        library=library,
        manager=manager,
        module_url=module_url,
        slot_hub=slot_hub,
        assignments=assignments,
        sender=sender,
    )
    await sender.async_start()
    await async_add_frontend(hass, module_url)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ApolloTabConfigEntry) -> bool:
    """Unload the platforms, subscriptions, sender, manager and frontend."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = entry.runtime_data
        for subscription in list(data.subscriptions):
            subscription.async_unload()
        data.subscriptions.clear()
        data.sender.async_stop()
        await data.assignments.async_flush()
        data.slot_hub.async_stop()
        data.manager.async_stop()
        async_remove_frontend(hass, data.module_url)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ApolloTabConfigEntry) -> None:
    """Blank the tablets it can reach, delete the stored secrets and issues."""
    await async_clear_tablets(hass)
    registry = ir.async_get(hass)
    for domain, issue_id in list(registry.issues):
        if domain == DOMAIN:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
