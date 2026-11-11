"""Shared fixtures for the Apollo TAB Dashboard tests."""

from collections.abc import Callable

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apollo_tab.const import DOMAIN

type AddTablet = Callable[..., dr.DeviceEntry]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration from custom_components."""


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
