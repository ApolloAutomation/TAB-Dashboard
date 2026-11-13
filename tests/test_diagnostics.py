"""Tests for the Apollo TAB Dashboard diagnostics."""

import json

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apollo_tab.diagnostics import async_get_config_entry_diagnostics

from .conftest import AddTablet, SaveDashboard, setup_integration

TAB_CONFIG = {
    "apollo_tab": {"version": 1, "theme": "midnight"},
    "views": [
        {
            "type": "sections",
            "path": "home",
            "title": "Home",
            "max_columns": 3,
            "sections": [
                {
                    "type": "grid",
                    "cards": [
                        {"type": "heading", "heading": "Lights"},
                        {
                            "type": "custom:apollo-tab-card",
                            "component": "apollo/light-tile",
                            "params": {"entity": "light.kitchen"},
                        },
                    ],
                }
            ],
        }
    ],
}


# What the sender reports for a tablet whose ESPHome entry is not loaded.
OFFLINE = {
    "approved": True,
    "dashboard": None,
    "status": "offline",
    "reason": "",
    "retry": False,
    "engine": "",
    "paired": False,
    "input": "not_paired",
    "dropped_inputs": {},
}


async def test_diagnostics_two_tablets_exact_payload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    esphome_entry: MockConfigEntry,
    add_tablet: AddTablet,
    device_registry: dr.DeviceRegistry,
) -> None:
    """The payload is exactly the specified structure."""
    kitchen = add_tablet(esphome_entry, mac="AA:BB:CC:DD:EE:01", name="Kitchen Tablet")
    bedroom = add_tablet(mac="AA:BB:CC:DD:EE:02", name="Bedroom Tablet")
    device_registry.async_update_device(
        bedroom.id, disabled_by=dr.DeviceEntryDisabler.USER
    )
    await setup_integration(hass, config_entry)
    payload = await async_get_config_entry_diagnostics(hass, config_entry)
    library = config_entry.runtime_data.library
    components = [
        {
            "id": component_id,
            "version": component["version"],
            "source": component["source"],
            "sensitive": component["sensitive"],
            "approved": library.is_approved(component_id),
        }
        for component_id, component in library.components.items()
    ]
    components.sort(key=lambda component: component["id"])
    tablets = [
        {
            "device_id": kitchen.id,
            "name": "Kitchen Tablet",
            "sw_version": "26.11.0 (ESPHome 2026.10.3)",
            "disabled": False,
            "esphome_entry_state": "not_loaded",
            "engine_entity_id": "sensor.kitchen_tablet_dashboard_engine",
            "engine_status": "not_installed",
            **OFFLINE,
        },
        {
            "device_id": bedroom.id,
            "name": "Bedroom Tablet",
            "sw_version": "26.11.0 (ESPHome 2026.10.3)",
            "disabled": True,
            "esphome_entry_state": "not_loaded",
            "engine_entity_id": "sensor.bedroom_tablet_dashboard_engine",
            "engine_status": None,
            **OFFLINE,
        },
    ]
    tablets.sort(key=lambda tablet: tablet["device_id"])
    assert payload == {
        "tablet_count": 2,
        "tablets": tablets,
        "sent_to_tablets": False,
        "unknown_inputs": 0,
        "library": {"components": components, "errors": []},
        "dashboards": [],
    }


async def test_diagnostics_never_reports_user_name_or_area(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    esphome_entry: MockConfigEntry,
    add_tablet: AddTablet,
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
) -> None:
    """The user's own name and area for a tablet are left out."""
    area = area_registry.async_create("Hallway")
    device = add_tablet(esphome_entry)
    device_registry.async_update_device(
        device.id, name_by_user="My Wall Tablet", area_id=area.id
    )
    await setup_integration(hass, config_entry)
    payload = await async_get_config_entry_diagnostics(hass, config_entry)
    tablet = payload["tablets"][0]
    assert tablet["name"] == "Kitchen Tablet"
    assert "area_id" not in tablet
    output = json.dumps(payload)
    assert "My Wall Tablet" not in output
    assert '"area_id"' not in output


async def test_diagnostics_keeps_default_name_with_mac_suffix(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    esphome_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """The default name with its MAC suffix is reported unchanged."""
    add_tablet(esphome_entry, name="Apollo TAB-1 ddee01", mac="AA:BB:CC:DD:EE:01")
    await setup_integration(hass, config_entry)
    payload = await async_get_config_entry_diagnostics(hass, config_entry)
    tablet = payload["tablets"][0]
    assert tablet["name"] == "Apollo TAB-1 ddee01"
    assert tablet["engine_entity_id"] == "sensor.apollo_tab_1_ddee01_dashboard_engine"
    output = json.dumps(payload).lower()
    assert "aa:bb:cc:dd:ee:01" not in output
    assert "aabbccddee01" not in output


async def test_diagnostics_without_tablets(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Without tablets the tablet list is empty."""
    await setup_integration(hass, config_entry)
    payload = await async_get_config_entry_diagnostics(hass, config_entry)
    assert payload["tablet_count"] == 0
    assert payload["tablets"] == []
    assert payload["sent_to_tablets"] is False
    assert payload["library"]["components"] != []
    assert payload["library"]["errors"] == []
    assert payload["dashboards"] == []


async def test_diagnostics_includes_layout_with_user_text_redacted(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: SaveDashboard,
) -> None:
    """Dashboard layouts are included with user-written text redacted."""
    await setup_integration(hass, config_entry)
    await tab_dashboard(TAB_CONFIG)
    payload = await async_get_config_entry_diagnostics(hass, config_entry)
    assert len(payload["dashboards"]) == 1
    dashboard = payload["dashboards"][0]
    assert dashboard["url_path"] == "tab-1"
    assert dashboard["mode"] == "storage"
    assert dashboard["pages"] == 1
    assert len(dashboard["hash"]) == 16
    assert dashboard["warnings"] == []
    output = json.dumps(dashboard["layout"])
    assert "Lights" not in output
    assert "Home" not in output
    assert "**REDACTED**" in output


async def test_diagnostics_has_no_templates_or_entity_ids(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: SaveDashboard,
) -> None:
    """Bindings with templates and entity ids never reach diagnostics."""
    await setup_integration(hass, config_entry)
    await tab_dashboard(TAB_CONFIG)
    payload = await async_get_config_entry_diagnostics(hass, config_entry)
    output = json.dumps(payload)
    assert "light.kitchen" not in output
    assert "{{" not in output
