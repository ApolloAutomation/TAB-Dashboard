"""Tests for config entry diagnostics."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apollo_tab.diagnostics import async_get_config_entry_diagnostics

from .conftest import AddTablet, setup_integration


async def test_diagnostics_lists_tablets(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """Diagnostics list each tablet with its engine status and no full MAC address."""
    device = add_tablet()
    await setup_integration(hass, config_entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert diagnostics == {
        "tablet_count": 1,
        "tablets": [
            {
                "device_id": device.id,
                "name": "Kitchen Tablet",
                "area_id": None,
                "sw_version": "26.11.0 (ESPHome 2026.10.3)",
                "disabled": False,
                "esphome_entry_state": "not_loaded",
                "engine_entity_id": "sensor.kitchen_tablet_dashboard_engine",
                "engine_status": "not_installed",
            }
        ],
    }
    assert "aa:bb:cc:dd:ee:01" not in str(diagnostics)


async def test_diagnostics_reports_name_by_user(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """A tablet renamed by the user is reported under the name they gave it."""
    device = add_tablet()
    await setup_integration(hass, config_entry)
    device_registry.async_update_device(device.id, name_by_user="Hallway Panel")
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    assert diagnostics["tablets"][0]["name"] == "Hallway Panel"


async def test_diagnostics_keeps_default_name_with_mac_suffix(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """A default name holds the last three MAC bytes and is reported as is.

    No full MAC address appears anywhere in the output.
    """
    add_tablet(name="Apollo TAB-1 ddee01", mac="AA:BB:CC:DD:EE:01")
    await setup_integration(hass, config_entry)

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

    expected_entity_id = "sensor.apollo_tab_1_ddee01_dashboard_engine"
    tablet = diagnostics["tablets"][0]
    assert tablet["name"] == "Apollo TAB-1 ddee01"
    assert tablet["engine_entity_id"] == expected_entity_id
    assert "aa:bb:cc:dd:ee:01" not in str(diagnostics).lower()
    assert "aabbccddee01" not in str(diagnostics).lower()


async def test_diagnostics_without_tablets(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Diagnostics work when no tablet has been found."""
    await setup_integration(hass, config_entry)

    assert await async_get_config_entry_diagnostics(hass, config_entry) == {
        "tablet_count": 0,
        "tablets": [],
    }
