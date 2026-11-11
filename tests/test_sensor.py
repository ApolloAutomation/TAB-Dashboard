"""Tests for the dashboard engine sensor and device registry tracking."""

import logging
from unittest.mock import patch

import pytest
from homeassistant.const import EntityCategory
from homeassistant.core import EventBus, HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.translation import async_get_translations
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.apollo_tab.const import DOMAIN

from .conftest import AddTablet, setup_integration

UNIQUE_ID = "aa:bb:cc:dd:ee:01_dashboard_engine"


def engine_entity_id(entity_registry: er.EntityRegistry, unique_id: str) -> str | None:
    """Return the entity ID of the sensor with this unique ID."""
    return entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)


async def test_sensor_for_existing_tablet(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """A tablet present at setup gets a sensor on its ESPHome device."""
    device = add_tablet()
    await setup_integration(hass, config_entry)

    entity_id = engine_entity_id(entity_registry, UNIQUE_ID)
    assert entity_id == "sensor.kitchen_tablet_dashboard_engine"
    registered = entity_registry.async_get(entity_id)
    assert registered.device_id == device.id
    assert registered.config_entry_id == config_entry.entry_id
    assert registered.entity_category is EntityCategory.DIAGNOSTIC
    assert registered.translation_key == "dashboard_engine"

    state = hass.states.get(entity_id)
    assert state.state == "not_installed"
    assert state.attributes["options"] == ["not_installed"]
    assert state.attributes["friendly_name"] == "Kitchen Tablet Dashboard engine"


async def test_setup_does_not_claim_the_device(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    config_entry: MockConfigEntry,
    esphome_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """The device stays owned by ESPHome and no second device is created."""
    device = add_tablet(esphome_entry)
    await setup_integration(hass, config_entry)

    assert device_registry.async_get(device.id).config_entry_id == (
        esphome_entry.entry_id
    )
    assert (
        dr.async_entries_for_config_entry(device_registry, config_entry.entry_id) == []
    )
    assert len(list(device_registry.devices)) == 1


async def test_no_tablets(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Setup succeeds with no tablets and adds no entities."""
    await setup_integration(hass, config_entry)

    assert hass.states.async_entity_ids("sensor") == []


async def test_tablet_added_after_setup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """A tablet adopted in ESPHome later gets a sensor without a restart."""
    await setup_integration(hass, config_entry)

    add_tablet()
    await hass.async_block_till_done()

    entity_id = engine_entity_id(entity_registry, UNIQUE_ID)
    assert hass.states.get(entity_id).state == "not_installed"


async def test_child_device_created_and_removed(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    config_entry: MockConfigEntry,
    esphome_entry: MockConfigEntry,
    add_tablet: AddTablet,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A child device created and removed on a tablet's entry changes nothing."""
    device = add_tablet(esphome_entry)
    await setup_integration(hass, config_entry)
    sensor_ids = hass.states.async_entity_ids("sensor")

    child = device_registry.async_get_or_create_child(
        config_entry_id=esphome_entry.entry_id,
        parent_device_id=device.id,
        identifiers={("esphome", "AA:BB:CC:DD:EE:01_1")},
        name="child",
    )
    await hass.async_block_till_done()
    device_registry.async_remove_device(child.id)
    await hass.async_block_till_done()

    assert hass.states.async_entity_ids("sensor") == sensor_ids
    for record in caplog.records:
        # The http dependency warns when it has no fast zlib in this environment.
        if record.levelno < logging.WARNING or record.name == "aiohttp_fast_zlib":
            continue
        assert "has not been tested by Home Assistant" in record.getMessage()


async def test_device_becomes_tablet_after_firmware_change(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """A device counts as a tablet once ESPHome reports the TAB-1 project name."""
    device = add_tablet(manufacturer="espressif", model="esp32dev")
    await setup_integration(hass, config_entry)
    assert engine_entity_id(entity_registry, UNIQUE_ID) is None

    device_registry.async_update_device(
        device.id, manufacturer="ApolloAutomation", model="TAB-1"
    )
    await hass.async_block_till_done()
    assert engine_entity_id(entity_registry, UNIQUE_ID) is not None

    device_registry.async_update_device(device.id, model="MSR-2")
    await hass.async_block_till_done()
    assert engine_entity_id(entity_registry, UNIQUE_ID) is None
    assert hass.states.async_entity_ids("sensor") == []


async def test_tablet_removed(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """Removing the ESPHome device removes the sensor and its registry entry."""
    device = add_tablet()
    await setup_integration(hass, config_entry)

    device_registry.async_remove_device(device.id)
    await hass.async_block_till_done()

    assert engine_entity_id(entity_registry, UNIQUE_ID) is None
    assert hass.states.async_entity_ids("sensor") == []


async def test_tablet_removed_then_added_again(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    esphome_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """A tablet that comes back gets its sensor back under the same unique ID."""
    device = add_tablet(esphome_entry)
    await setup_integration(hass, config_entry)
    device_registry.async_remove_device(device.id)
    await hass.async_block_till_done()

    add_tablet(esphome_entry)
    await hass.async_block_till_done()

    entity_id = engine_entity_id(entity_registry, UNIQUE_ID)
    assert hass.states.get(entity_id).state == "not_installed"


async def test_tablet_readded_under_new_device_id(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    esphome_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """A tablet registered again under a new device ID keeps its sensor.

    The sensor is re-linked to the new device instead of being removed.
    """
    device = add_tablet(esphome_entry)
    await setup_integration(hass, config_entry)

    device_registry.async_remove_device(device.id)
    other_entry = MockConfigEntry(domain="esphome", title="Replacement")
    other_entry.add_to_hass(hass)
    new_device = add_tablet(other_entry)
    await hass.async_block_till_done()

    assert new_device.id != device.id
    entity_id = engine_entity_id(entity_registry, UNIQUE_ID)
    assert hass.states.get(entity_id).state == "not_installed"
    assert entity_registry.async_get(entity_id).device_id == new_device.id


async def test_tablet_readded_with_same_device_id(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    esphome_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """A tablet registered again with its old device ID keeps its sensor.

    The registry restores the device ID, and the sensor is re-linked to it.
    """
    device = add_tablet(esphome_entry)
    await setup_integration(hass, config_entry)

    device_registry.async_remove_device(device.id)
    new_device = add_tablet(esphome_entry)
    await hass.async_block_till_done()

    assert new_device.id == device.id
    entity_id = engine_entity_id(entity_registry, UNIQUE_ID)
    assert hass.states.get(entity_id).state == "not_installed"
    assert entity_registry.async_get(entity_id).device_id == new_device.id


async def test_two_esphome_entries_with_same_mac(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    esphome_entry: MockConfigEntry,
    add_tablet: AddTablet,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two ESPHome entries sharing one MAC get a single sensor.

    Removing the duplicate device must not remove the sensor.
    """
    device = add_tablet(esphome_entry)
    await setup_integration(hass, config_entry)

    duplicate_entry = MockConfigEntry(domain="esphome", title="Duplicate")
    duplicate_entry.add_to_hass(hass)
    duplicate = add_tablet(duplicate_entry)
    await hass.async_block_till_done()

    entries = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    assert len(entries) == 1
    assert "does not generate unique IDs" not in caplog.text

    device_registry.async_remove_device(duplicate.id)
    await hass.async_block_till_done()

    entity_id = engine_entity_id(entity_registry, UNIQUE_ID)
    assert hass.states.get(entity_id).state == "not_installed"
    assert entity_registry.async_get(entity_id).device_id == device.id


async def test_tablet_renamed(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """Renaming a tablet keeps the same entity and updates its friendly name."""
    device = add_tablet()
    await setup_integration(hass, config_entry)
    entity_id = engine_entity_id(entity_registry, UNIQUE_ID)

    device_registry.async_update_device(device.id, name_by_user="Hallway Panel")
    await hass.async_block_till_done()

    assert engine_entity_id(entity_registry, UNIQUE_ID) == entity_id
    assert len(hass.states.async_entity_ids("sensor")) == 1
    state = hass.states.get(entity_id)
    assert state.attributes["friendly_name"] == "Hallway Panel Dashboard engine"


async def test_tablet_moved_to_another_area(
    hass: HomeAssistant,
    area_registry: ar.AreaRegistry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """Moving a tablet to another area keeps its sensor on the device."""
    device = add_tablet()
    await setup_integration(hass, config_entry)
    entity_id = engine_entity_id(entity_registry, UNIQUE_ID)

    area = area_registry.async_create("Hallway")
    device_registry.async_update_device(device.id, area_id=area.id)
    await hass.async_block_till_done()

    registered = entity_registry.async_get(entity_id)
    assert registered.device_id == device.id
    # The entity has no area of its own, so it follows the device.
    assert registered.area_id is None
    assert hass.states.get(entity_id).state == "not_installed"


async def test_two_tablets(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """Each tablet gets its own sensor under the one config entry."""
    add_tablet(mac="AA:BB:CC:DD:EE:01", name="Kitchen Tablet")
    add_tablet(mac="AA:BB:CC:DD:EE:02", name="Bedroom Tablet")
    await setup_integration(hass, config_entry)

    assert sorted(hass.states.async_entity_ids("sensor")) == [
        "sensor.bedroom_tablet_dashboard_engine",
        "sensor.kitchen_tablet_dashboard_engine",
    ]
    entries = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    assert {entry.unique_id for entry in entries} == {
        "aa:bb:cc:dd:ee:01_dashboard_engine",
        "aa:bb:cc:dd:ee:02_dashboard_engine",
    }


async def test_stale_sensor_removed_at_setup(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """A tablet removed while the integration was unloaded leaves no sensor."""
    device = add_tablet()
    await setup_integration(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    device_registry.async_remove_device(device.id)
    await hass.async_block_till_done()
    # The registry entry outlives the device because another entry owns the device.
    assert engine_entity_id(entity_registry, UNIQUE_ID) is not None

    await setup_integration(hass, config_entry)
    assert engine_entity_id(entity_registry, UNIQUE_ID) is None


async def test_reload_keeps_registry_entry(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """Reloading with a live tablet keeps the same entity registry entry."""
    add_tablet()
    await setup_integration(hass, config_entry)
    entity_id = engine_entity_id(entity_registry, UNIQUE_ID)
    registry_entry_id = entity_registry.async_get(entity_id).id

    events = async_capture_events(hass, er.EVENT_ENTITY_REGISTRY_UPDATED)
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert "remove" not in [event.data["action"] for event in events]
    assert entity_registry.async_get(entity_id).id == registry_entry_id
    assert hass.states.get(entity_id).state == "not_installed"


async def test_unload_stops_tracking(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """After unload, new tablets are ignored and existing sensors go unavailable."""
    add_tablet(mac="AA:BB:CC:DD:EE:01")
    await setup_integration(hass, config_entry)
    entity_id = engine_entity_id(entity_registry, UNIQUE_ID)

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"

    add_tablet(mac="AA:BB:CC:DD:EE:02", name="Bedroom Tablet")
    await hass.async_block_till_done()
    assert (
        engine_entity_id(entity_registry, "aa:bb:cc:dd:ee:02_dashboard_engine") is None
    )


async def test_tablet_added_just_before_unload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """A tablet found just before unload does not leave a live sensor behind."""
    await setup_integration(hass, config_entry)

    add_tablet()
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.async_entity_ids("sensor") == []


async def test_removing_entry_leaves_esphome_device(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
) -> None:
    """Deleting the integration removes its sensors but not the tablet device."""
    device = add_tablet()
    await setup_integration(hass, config_entry)

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    assert engine_entity_id(entity_registry, UNIQUE_ID) is None
    assert device_registry.async_get(device.id) is not None


async def test_not_installed_state_translation(hass: HomeAssistant) -> None:
    """The not_installed state is translated to "Not installed" in English."""
    key = "component.apollo_tab.entity.sensor.dashboard_engine.state.not_installed"
    translations = await async_get_translations(hass, "en", "entity", {DOMAIN})
    assert translations[key] == "Not installed"


async def test_stale_reconcile_after_reload_adds_nothing(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    config_entry: MockConfigEntry,
    add_tablet: AddTablet,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A deferred reconcile from before a reload must not add sensors again."""
    add_tablet()
    captured = []
    real_listen = EventBus.async_listen

    def spy(self, event_type, listener, *args, **kwargs):
        if event_type == dr.EVENT_DEVICE_REGISTRY_UPDATED and getattr(
            listener, "__module__", ""
        ).endswith("apollo_tab.sensor"):
            captured.append(listener)
        return real_listen(self, event_type, listener, *args, **kwargs)

    with patch.object(EventBus, "async_listen", spy):
        await setup_integration(hass, config_entry)
    assert len(captured) == 1

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    add_tablet(mac="AA:BB:CC:DD:EE:02", name="Hall Tablet")
    await setup_integration(hass, config_entry)

    caplog.clear()
    captured[0](None)  # the old setup's listener, as if its event arrived late
    await hass.async_block_till_done()

    assert "does not generate unique IDs" not in caplog.text
