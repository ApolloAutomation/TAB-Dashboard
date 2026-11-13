"""Tests for the "Dashboard" select and the apollo_tab.show_dashboard action."""

import pytest
from homeassistant.auth.models import User
from homeassistant.const import EntityCategory
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.apollo_tab.sender import STATUS_ON_TABLET
from custom_components.apollo_tab.tablets import async_get_tablets

from .conftest import MakeTablet, SaveTabDashboard, setup_integration, until

MAC = "aa:bb:cc:dd:ee:01"
SELECT = "select.kitchen_tablet_dashboard"


def tab_config(title: str = "Home") -> dict:
    """Return a TAB-1 dashboard config with one light tile."""
    return {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [
            {
                "type": "sections",
                "path": "home",
                "title": title,
                "max_columns": 3,
                "sections": [
                    {
                        "type": "grid",
                        "cards": [
                            {
                                "type": "custom:apollo-tab-card",
                                "component": "apollo/light-tile",
                                "params": {"entity": "light.kitchen"},
                            }
                        ],
                    }
                ],
            }
        ],
    }


@pytest.fixture
async def family_user(hass: HomeAssistant) -> User:
    """Return a user who is not an admin but may control entities."""
    return await hass.auth.async_create_user("Family", group_ids=["system-users"])


async def two_dashboards(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save: SaveTabDashboard,
) -> None:
    """Set up one tablet and the dashboards Home (tab-home) and Bedroom."""
    make_tablet()
    await setup_integration(hass, entry)
    await save("tab-home", tab_config("Home"), title="Home")
    await save("tab-bed", tab_config("Bedroom"), title="Bedroom")
    session = entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)


async def test_options_stay_unique_when_a_title_equals_another_option(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A title equal to another dashboard's option text still picks its own."""
    make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("home-a", tab_config(), title="Home")
    await save_tab_dashboard("home-b", tab_config(), title="home")
    await save_tab_dashboard("x-c", tab_config(), title="Home (home-a)")
    await hass.async_block_till_done()
    options = hass.states.get(SELECT).attributes["options"]
    assert len({option.lower() for option in options}) == len(options) == 3
    assert "Home (home-a) (x-c)" in options
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": SELECT, "option": "Home (home-a) (x-c)"},
        blocking=True,
    )
    assert config_entry.runtime_data.assignments.dashboard(MAC) == "x-c"
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": SELECT, "option": "Home (home-a)"},
        blocking=True,
    )
    assert config_entry.runtime_data.assignments.dashboard(MAC) == "home-a"


async def test_select_entity(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """One select per tablet on its ESPHome device, options in the one order."""
    await two_dashboards(hass, config_entry, make_tablet, save_tab_dashboard)

    registered = entity_registry.async_get(SELECT)
    assert registered.unique_id == f"{MAC}_dashboard"
    assert registered.entity_category is EntityCategory.CONFIG
    assert registered.translation_key == "dashboard"
    assert registered.device_id == async_get_tablets(hass)[MAC].id
    state = hass.states.get(SELECT)
    assert state.state == "Home"
    assert state.attributes["options"] == ["Bedroom", "Home"]
    assert state.attributes["dashboard_id"] == "tab-home"
    assert state.attributes["friendly_name"] == "Kitchen Tablet Dashboard"


async def test_no_dashboards(
    hass: HomeAssistant, config_entry: MockConfigEntry, make_tablet: MakeTablet
) -> None:
    """Without dashboards the select has no options and no state."""
    make_tablet()
    await setup_integration(hass, config_entry)
    state = hass.states.get(SELECT)
    assert state.state == "unknown"
    assert state.attributes["options"] == []
    assert state.attributes["dashboard_id"] is None


async def test_admin_selects(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_admin_user: User,
) -> None:
    """An admin's choice is stored and sent."""
    await two_dashboards(hass, config_entry, make_tablet, save_tab_dashboard)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": SELECT, "option": "Bedroom"},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    session = config_entry.runtime_data.sender.sessions[MAC]
    assert session.dashboard == "tab-bed"
    await until(
        hass,
        lambda: (
            session.status == STATUS_ON_TABLET and session.want.url_path == "tab-bed"
        ),
    )
    state = hass.states.get(SELECT)
    assert state.state == "Bedroom"
    assert state.attributes["dashboard_id"] == "tab-bed"


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("select_option", {"option": "Bedroom"}),
        ("select_next", {}),
        ("select_previous", {}),
        ("select_first", {}),
        ("select_last", {}),
    ],
)
async def test_non_admin_is_refused(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    family_user: User,
    service: str,
    data: dict,
) -> None:
    """Every way of changing the select is refused for a non-admin user."""
    await two_dashboards(hass, config_entry, make_tablet, save_tab_dashboard)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "select",
            service,
            {"entity_id": SELECT, **data},
            blocking=True,
            context=Context(user_id=family_user.id),
        )
    assert config_entry.runtime_data.assignments.dashboard(MAC) == "tab-home"


async def test_automation_may_select(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A call without a user, as from an automation, is allowed."""
    await two_dashboards(hass, config_entry, make_tablet, save_tab_dashboard)
    await hass.services.async_call(
        "select", "select_next", {"entity_id": SELECT}, blocking=True
    )
    assert config_entry.runtime_data.assignments.dashboard(MAC) == "tab-bed"


async def test_rename_changes_options_not_assignment(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A rename changes the option text at once; the id keeps working."""
    await two_dashboards(hass, config_entry, make_tablet, save_tab_dashboard)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "lovelace/dashboards/list"})
    items = (await client.receive_json())["result"]
    home = next(item for item in items if item["url_path"] == "tab-home")
    await client.send_json_auto_id(
        {
            "type": "lovelace/dashboards/update",
            "dashboard_id": home["id"],
            "title": "Living room",
        }
    )
    assert (await client.receive_json())["success"]
    await hass.async_block_till_done()

    state = hass.states.get(SELECT)
    assert state.state == "Living room"
    assert state.attributes["options"] == ["Bedroom", "Living room"]
    assert config_entry.runtime_data.assignments.dashboard(MAC) == "tab-home"
    # The old title is no longer an option.
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": SELECT, "option": "Home"},
            blocking=True,
        )


async def test_duplicate_titles_get_the_id(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Two dashboards with one title are told apart by their id."""
    make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("home-2", tab_config(), title="Home")
    await save_tab_dashboard("home-1", tab_config(), title="Home")
    await hass.async_block_till_done()
    state = hass.states.get(SELECT)
    assert state.attributes["options"] == ["Home (home-1)", "Home (home-2)"]
    assert state.state == "Home (home-2)"
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": SELECT, "option": "Home (home-1)"},
        blocking=True,
    )
    assert config_entry.runtime_data.assignments.dashboard(MAC) == "home-1"


async def test_select_follows_the_device(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    make_tablet: MakeTablet,
    add_tablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Removed with the tablet; back on the new device with the same choice."""
    await two_dashboards(hass, config_entry, make_tablet, save_tab_dashboard)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": SELECT, "option": "Bedroom"},
        blocking=True,
    )
    device = async_get_tablets(hass)[MAC]
    esphome = hass.config_entries.async_get_entry(device.config_entry_id)
    device_registry.async_remove_device(device.id)
    await hass.async_block_till_done()
    assert (
        entity_registry.async_get_entity_id("select", "apollo_tab", f"{MAC}_dashboard")
        is None
    )
    assert MAC not in config_entry.runtime_data.sender.sessions

    # ESPHome registers it again under the same config entry.
    new_device = add_tablet(esphome)
    await hass.async_block_till_done()
    entity_id = entity_registry.async_get_entity_id(
        "select", "apollo_tab", f"{MAC}_dashboard"
    )
    assert entity_registry.async_get(entity_id).device_id == new_device.id
    # The assignment is keyed by MAC, so it survived.
    assert hass.states.get(entity_id).state == "Bedroom"


async def test_show_dashboard(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_admin_user: User,
    family_user: User,
    add_tablet,
) -> None:
    """The action takes ids, follows the admin rule and has plain errors."""
    await two_dashboards(hass, config_entry, make_tablet, save_tab_dashboard)
    device_id = async_get_tablets(hass)[MAC].id

    await hass.services.async_call(
        "apollo_tab",
        "show_dashboard",
        {"device_id": device_id, "dashboard": "tab-bed"},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    assert config_entry.runtime_data.assignments.dashboard(MAC) == "tab-bed"

    # An automation: no user.
    await hass.services.async_call(
        "apollo_tab",
        "show_dashboard",
        {"device_id": device_id, "dashboard": "tab-home"},
        blocking=True,
    )
    assert config_entry.runtime_data.assignments.dashboard(MAC) == "tab-home"

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "apollo_tab",
            "show_dashboard",
            {"device_id": device_id, "dashboard": "tab-bed"},
            blocking=True,
            context=Context(user_id=family_user.id),
        )
    assert config_entry.runtime_data.assignments.dashboard(MAC) == "tab-home"

    other = add_tablet(mac="AA:BB:CC:DD:EE:99", name="Plug", model="MSR-2")
    for device, dashboard, message in (
        ("nope", "tab-bed", "This tablet is not known"),
        (other.id, "tab-bed", "This tablet is not known"),
        (device_id, "nope", "This dashboard does not exist"),
    ):
        with pytest.raises(ServiceValidationError) as err:
            await hass.services.async_call(
                "apollo_tab",
                "show_dashboard",
                {"device_id": device, "dashboard": dashboard},
                blocking=True,
            )
        assert str(err.value) == message


async def test_show_dashboard_when_not_loaded(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """The action answers plainly while the integration is unloaded."""
    await setup_integration(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "apollo_tab",
            "show_dashboard",
            {"device_id": "x", "dashboard": "y"},
            blocking=True,
        )


async def test_dashboard_that_cannot_be_read_cannot_be_picked(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_ws_client: ClientSessionGenerator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The select keeps its name but refuses it, as the panel and action do.

    A tablet already on it may keep it.
    """
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.exceptions import HomeAssistantError

    make_tablet()
    hall = make_tablet(mac="AA:BB:CC:DD:EE:02", name="Hall Tablet")
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config("Alpha"), title="Alpha")
    await save_tab_dashboard("tab-b", tab_config("Beta"), title="Beta")
    data = config_entry.runtime_data
    kitchen = data.sender.sessions[MAC]
    await until(hass, lambda: kitchen.status == STATUS_ON_TABLET)
    data.assignments.async_assign("aa:bb:cc:dd:ee:02", "tab-b")
    await until(
        hass,
        lambda: data.sender.sessions["aa:bb:cc:dd:ee:02"].status == STATUS_ON_TABLET,
    )

    async def broken(force: bool) -> dict:
        """Act like a YAML file with an error."""
        raise HomeAssistantError("bad")

    dashboard = hass.data[LOVELACE_DATA].dashboards["tab-a"]
    monkeypatch.setattr(dashboard, "async_load", broken)
    hass.bus.async_fire("lovelace_updated", {"url_path": "tab-a"})
    await until(hass, lambda: kitchen.reason == "unreadable")
    hall_select = "select.hall_tablet_dashboard"
    assert hass.states.get(hall_select).attributes["options"] == ["Beta", "Alpha"]

    for service, extra in (
        ("select_option", {"option": "Alpha"}),
        ("select_next", {}),
        ("select_last", {}),
    ):
        with pytest.raises(ServiceValidationError) as err:
            await hass.services.async_call(
                "select", service, {"entity_id": hall_select, **extra}, blocking=True
            )
        assert str(err.value) == "This dashboard does not exist"
    assert data.assignments.dashboard("aa:bb:cc:dd:ee:02") == "tab-b"
    assert hall.active

    # The panel and the action refuse it the same way.
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "apollo_tab/tablet/assign",
            "mac": "aa:bb:cc:dd:ee:02",
            "url_path": "tab-a",
        }
    )
    response = await client.receive_json()
    assert response["error"]["code"] == "unknown_dashboard"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "apollo_tab",
            "show_dashboard",
            {
                "device_id": async_get_tablets(hass)["aa:bb:cc:dd:ee:02"].id,
                "dashboard": "tab-a",
            },
            blocking=True,
        )

    # The tablet on it keeps it: picking its own option changes nothing.
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": SELECT, "option": "Alpha"},
        blocking=True,
    )
    assert data.assignments.dashboard(MAC) == "tab-a"
    assert hass.states.get(SELECT).state == "Alpha"
