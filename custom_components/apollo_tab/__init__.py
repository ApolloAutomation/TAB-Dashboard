"""The Apollo TAB Dashboard integration."""

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import websocket
from .const import DOMAIN
from .library import Library
from .live import SlotHub
from .manager import DashboardManager
from .web import async_add_frontend, async_register_static, async_remove_frontend

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SENSOR]


@dataclass
class ApolloTabData:
    """Runtime data of a loaded config entry."""

    library: Library
    manager: DashboardManager
    module_url: str
    slot_hub: SlotHub
    # Open websocket subscriptions, each with an async_unload() method.
    subscriptions: set[Any] = field(default_factory=set)


type ApolloTabConfigEntry = ConfigEntry[ApolloTabData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the websocket commands once for the whole integration."""
    websocket.async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ApolloTabConfigEntry) -> bool:
    """Set up the library, the manager, the frontend and the platforms."""
    module_url = await async_register_static(hass)
    library = Library(hass)
    await library.async_load()
    slot_hub = SlotHub(hass, library)
    manager = DashboardManager(hass, library)
    await manager.async_start()
    entry.runtime_data = ApolloTabData(
        library=library, manager=manager, module_url=module_url, slot_hub=slot_hub
    )
    await async_add_frontend(hass, module_url)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ApolloTabConfigEntry) -> bool:
    """Unload the platforms, subscriptions, manager and frontend."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = entry.runtime_data
        for subscription in list(data.subscriptions):
            subscription.async_unload()
        data.subscriptions.clear()
        data.slot_hub.async_stop()
        data.manager.async_stop()
        async_remove_frontend(hass, data.module_url)
    return unload_ok
