"""Tests for finding tablets in the device registry."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apollo_tab.tablets import async_get_tablets, async_tablet_mac

from .conftest import AddTablet


async def test_finds_tablet(hass: HomeAssistant, add_tablet: AddTablet) -> None:
    """An ESPHome device with the TAB-1 project name is a tablet."""
    device = add_tablet(mac="AA:BB:CC:DD:EE:01")

    assert async_tablet_mac(hass, device) == "aa:bb:cc:dd:ee:01"
    assert async_get_tablets(hass) == {"aa:bb:cc:dd:ee:01": device}


async def test_ignores_other_esphome_devices(
    hass: HomeAssistant, add_tablet: AddTablet
) -> None:
    """Other ESPHome projects and plain ESPHome devices are not tablets."""
    add_tablet(mac="AA:BB:CC:DD:EE:02", manufacturer="ApolloAutomation", model="MSR-2")
    add_tablet(mac="AA:BB:CC:DD:EE:03", manufacturer="espressif", model="esp32dev")
    add_tablet(mac="AA:BB:CC:DD:EE:04", manufacturer="Other", model="TAB-1")

    assert async_get_tablets(hass) == {}


async def test_ignores_other_integrations(
    hass: HomeAssistant, add_tablet: AddTablet
) -> None:
    """A device with the same manufacturer and model outside ESPHome is ignored."""
    other_entry = MockConfigEntry(domain="other")
    other_entry.add_to_hass(hass)
    device = add_tablet(other_entry)

    assert async_tablet_mac(hass, device) is None
    assert async_get_tablets(hass) == {}


async def test_ignores_devices_without_mac(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    esphome_entry: MockConfigEntry,
) -> None:
    """An ESPHome sub-device has identifiers but no MAC and is not a tablet."""
    device = device_registry.async_get_or_create(
        config_entry_id=esphome_entry.entry_id,
        identifiers={("esphome", "AA:BB:CC:DD:EE:01_1")},
        manufacturer="ApolloAutomation",
        model="TAB-1",
    )

    assert async_tablet_mac(hass, device) is None
    assert async_get_tablets(hass) == {}


async def test_keys_on_mac_connection_not_bluetooth(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    esphome_entry: MockConfigEntry,
) -> None:
    """A tablet with Bluetooth and MAC connections is keyed on the MAC.

    The Bluetooth address sorts before the MAC, so a check that accepted any
    connection type would return it instead of the MAC.
    """
    device = device_registry.async_get_or_create(
        config_entry_id=esphome_entry.entry_id,
        connections={
            (dr.CONNECTION_BLUETOOTH, "00:11:22:33:44:55"),
            (dr.CONNECTION_NETWORK_MAC, "AA:BB:CC:DD:EE:01"),
        },
        manufacturer="ApolloAutomation",
        model="TAB-1",
    )

    assert async_tablet_mac(hass, device) == "aa:bb:cc:dd:ee:01"
    assert async_get_tablets(hass) == {"aa:bb:cc:dd:ee:01": device}
