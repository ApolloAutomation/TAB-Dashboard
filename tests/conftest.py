"""Shared fixtures for the Apollo TAB Dashboard tests."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.apollo_tab.const import DOMAIN

type AddTablet = Callable[..., dr.DeviceEntry]
type WriteComponent = Callable[[str, str], Path]
type SaveDashboard = Callable[..., Awaitable[Any]]

# No websocket answer or event takes this long; a test that waits for one
# that never comes fails instead of hanging.
RECEIVE_TIMEOUT = 10


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration from custom_components."""


@pytest.fixture
def hass_ws_client(hass_ws_client: ClientSessionGenerator) -> ClientSessionGenerator:
    """Return websocket clients whose every receive has a time limit."""

    async def _create(*args: Any, **kwargs: Any) -> Any:
        """Create one client and put the time limit around receive_json."""
        client = await hass_ws_client(*args, **kwargs)
        receive_json = client.receive_json

        async def _receive_json(*receive_args: Any, **receive_kwargs: Any) -> Any:
            """Receive one message or raise TimeoutError."""
            async with asyncio.timeout(RECEIVE_TIMEOUT):
                return await receive_json(*receive_args, **receive_kwargs)

        client.receive_json = _receive_json
        return client

    return _create


@pytest.fixture
def esphome_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return an ESPHome config entry that owns one tablet. It is never set up."""
    entry = MockConfigEntry(domain="esphome", title="Kitchen Tablet")
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def add_tablet(hass: HomeAssistant, device_registry: dr.DeviceRegistry) -> AddTablet:
    """Return a function that registers a device the way ESPHome does."""

    def _add_tablet(
        entry: MockConfigEntry | None = None,
        *,
        mac: str = "AA:BB:CC:DD:EE:01",
        name: str = "Kitchen Tablet",
        manufacturer: str = "ApolloAutomation",
        model: str = "TAB-1",
    ) -> dr.DeviceEntry:
        if entry is None:
            entry = MockConfigEntry(domain="esphome", title=name)
            entry.add_to_hass(hass)
        return device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={(dr.CONNECTION_NETWORK_MAC, mac)},
            name=name,
            manufacturer=manufacturer,
            model=model,
            sw_version="26.11.0 (ESPHome 2026.10.3)",
        )

    return _add_tablet


@pytest.fixture
async def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return the integration's config entry, not yet set up."""
    entry = MockConfigEntry(domain=DOMAIN, title="Apollo TAB Dashboard", data={})
    entry.add_to_hass(hass)
    return entry


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the integration and wait until it has finished."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
def user_components(hass: HomeAssistant, tmp_path: Path) -> WriteComponent:
    """Point the config dir at tmp_path and return a component file writer."""
    hass.config.config_dir = str(tmp_path)

    def _write(file_name: str, text: str) -> Path:
        """Write one component file, creating the folder on first use."""
        folder = tmp_path / "apollo_tab" / "components"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / file_name
        path.write_text(text)
        return path

    return _write


@pytest.fixture
async def tab_dashboard(
    hass: HomeAssistant, hass_ws_client: ClientSessionGenerator
) -> SaveDashboard:
    """Return a function that saves a TAB-1 dashboard over the websocket.

    The integration must be set up before the function is used, because the
    first client freezes the router.
    """

    async def _save(config: dict, url_path: str = "tab-1") -> Any:
        """Create and save the dashboard and return the websocket client."""
        client = await hass_ws_client(hass)
        await client.send_json_auto_id(
            {
                "type": "lovelace/dashboards/create",
                "url_path": url_path,
                "title": "TAB-1",
                "icon": "mdi:tablet-dashboard",
                "mode": "storage",
                "require_admin": False,
                "show_in_sidebar": True,
            }
        )
        response = await client.receive_json()
        assert response["success"], response
        await client.send_json_auto_id(
            {
                "type": "lovelace/config/save",
                "url_path": url_path,
                "config": config,
            }
        )
        response = await client.receive_json()
        assert response["success"], response
        await hass.async_block_till_done()
        return client

    return _save
