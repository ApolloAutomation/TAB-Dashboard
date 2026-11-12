"""Tests for the apollo_tab websocket commands."""

from homeassistant.auth.models import Group, User
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from .conftest import SaveDashboard, setup_integration

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

PLAIN_CONFIG = {
    "views": [{"type": "sections", "path": "plain", "title": "Plain", "sections": []}]
}

BROKEN_COMPONENT = """\
id: me/broken
version: 1.0.0
name: Broken
size: 1x1
params:
  entity: {domain: light}
inputs:
  state: "{{ states(entity) }}"
outputs:
  toggle:
    action: light.toggle
    data: {entity_id: "{{ entity }}"}
    feedback: optimistic
    bogus: true
layout:
  - type: switch
    value: state
    on_tap: toggle
"""


async def test_strings(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """The strings command returns the library strings."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "apollo_tab/strings"})
    response = await client.receive_json()
    assert response["success"], response
    assert response["result"] == {"strings": config_entry.runtime_data.library.strings}


async def test_library_requires_admin(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    hass_read_only_access_token: str,
) -> None:
    """The library command is admin only."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json_auto_id({"type": "apollo_tab/library"})
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "unauthorized"


async def test_library_lists_components_and_errors(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    user_components,
) -> None:
    """The library lists builtin components and user file errors."""
    user_components("broken.yaml", BROKEN_COMPONENT)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "apollo_tab/library"})
    response = await client.receive_json()
    assert response["success"], response
    result = response["result"]
    components = {component["id"]: component for component in result["components"]}
    tile = components["apollo/light-tile"]
    assert tile["source"] == "builtin"
    assert tile["sensitive"] is False
    assert tile["approved"] is True
    assert tile["size"] == [1, 1]
    broken = [error for error in result["errors"] if error["file"] == "broken.yaml"]
    assert len(broken) == 1
    assert broken[0]["code"] == "unknown_key"
    assert any(theme["id"] == "midnight" for theme in result["themes"])
    assert result["components_path"].endswith("apollo_tab/components")


async def test_reload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """Reloading the library returns the component and error counts."""
    await setup_integration(hass, config_entry)
    library = config_entry.runtime_data.library
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "apollo_tab/library/reload"})
    response = await client.receive_json()
    assert response["success"], response
    assert response["result"] == {
        "components": len(library.components),
        "errors": len(library.errors),
    }
    assert response["result"]["errors"] == 0


async def test_approve_requires_admin(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    hass_read_only_access_token: str,
) -> None:
    """Approving a component is admin only."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json_auto_id(
        {
            "type": "apollo_tab/library/approve",
            "component_id": "apollo/lock",
            "approved": True,
        }
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "unauthorized"


async def test_approve_unknown_component(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """Approving an unknown component gives not_found."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "apollo_tab/library/approve",
            "component_id": "me/nope",
            "approved": True,
        }
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "not_found"


async def test_dashboards_lists_only_tab_dashboards(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: SaveDashboard,
) -> None:
    """Only dashboards with apollo_tab config are listed."""
    await setup_integration(hass, config_entry)
    client = await tab_dashboard(TAB_CONFIG)
    await tab_dashboard(PLAIN_CONFIG, url_path="plain-view")
    await client.send_json_auto_id({"type": "apollo_tab/dashboards"})
    response = await client.receive_json()
    assert response["success"], response
    result = response["result"]
    assert result["tablets"] == 0
    assert result["sent_to_tablets"] is False
    assert [dashboard["url_path"] for dashboard in result["dashboards"]] == ["tab-1"]
    dashboard = result["dashboards"][0]
    assert dashboard["title"] == "TAB-1"
    assert dashboard["mode"] == "storage"
    assert dashboard["theme"] == "midnight"
    assert dashboard["pages"] == 1
    assert dashboard["warnings"] == 0
    await client.send_json_auto_id(
        {"type": "apollo_tab/layout/get", "url_path": "tab-1"}
    )
    layout = await client.receive_json()
    assert dashboard["hash"] == layout["result"]["layout"]["hash"]


async def test_layout_get(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: SaveDashboard,
) -> None:
    """layout/get returns the stored layout and current values."""
    hass.states.async_set("light.kitchen", "on")
    await setup_integration(hass, config_entry)
    client = await tab_dashboard(TAB_CONFIG)
    await client.send_json_auto_id(
        {"type": "apollo_tab/layout/get", "url_path": "tab-1"}
    )
    response = await client.receive_json()
    assert response["success"], response
    result = response["result"]
    assert result["url_path"] == "tab-1"
    texts = [
        item.get("text") for page in result["layout"]["pages"] for item in page["w"]
    ]
    assert "Lights" in texts
    assert result["warnings"] == []
    assert "on" in result["values"].values()


async def test_layout_get_not_found(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """An unknown dashboard gives not_found."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "apollo_tab/layout/get", "url_path": "nope"}
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "not_found"


async def test_layout_requires_admin(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    hass_read_only_access_token: str,
) -> None:
    """layout/get is admin only."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json_auto_id(
        {"type": "apollo_tab/layout/get", "url_path": "tab-1"}
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "unauthorized"


async def test_every_admin_command_requires_admin(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    hass_read_only_access_token: str,
) -> None:
    """A user who is not an administrator gets unauthorized from each one."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    commands = [
        {"type": "apollo_tab/library"},
        {"type": "apollo_tab/library/subscribe"},
        {"type": "apollo_tab/library/reload"},
        {
            "type": "apollo_tab/library/approve",
            "component_id": "apollo/lock",
            "approved": True,
        },
        {"type": "apollo_tab/dashboards"},
        {"type": "apollo_tab/layout/get", "url_path": "tab-1"},
        {"type": "apollo_tab/layout/subscribe"},
    ]
    for command in commands:
        await client.send_json_auto_id(command)
        response = await client.receive_json()
        assert not response["success"], command
        assert response["error"]["code"] == "unauthorized", command
    assert config_entry.runtime_data.subscriptions == set()
    await client.send_json_auto_id({"type": "apollo_tab/strings"})
    response = await client.receive_json()
    assert response["success"], response


async def test_card_needs_read_permission_on_its_entity(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    hass_admin_user: User,
) -> None:
    """A user who may not read the card's entity cannot subscribe or call."""
    hass.states.async_set("light.kitchen", "on")
    hass.states.async_set("light.other", "on")
    calls = async_mock_service(hass, "light", "toggle")
    await setup_integration(hass, config_entry)
    hass_admin_user.groups = [
        Group(
            name="Limited", policy={"entities": {"entity_ids": {"light.other": True}}}
        )
    ]
    client = await hass_ws_client(hass)

    def _card(entity_id: str) -> dict:
        """Return a light tile card for one entity."""
        return {
            "type": "custom:apollo-tab-card",
            "component": "apollo/light-tile",
            "params": {"entity": entity_id},
        }

    await client.send_json_auto_id(
        {"type": "apollo_tab/card/subscribe", "card": _card("light.kitchen")}
    )
    response = await client.receive_json()
    assert response["success"], response
    event = await client.receive_json()
    assert event["event"] == {
        "type": "error",
        "code": "unauthorized",
        "message": "Not allowed to read light.kitchen",
    }
    assert len(config_entry.runtime_data.slot_hub) == 0

    await client.send_json_auto_id(
        {
            "type": "apollo_tab/card/call",
            "card": _card("light.kitchen"),
            "widget": 0,
            "event": "tap",
        }
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "unauthorized"
    assert calls == []

    # The entity the user may read works.
    await client.send_json_auto_id(
        {"type": "apollo_tab/card/subscribe", "card": _card("light.other")}
    )
    response = await client.receive_json()
    assert response["success"], response
    event = await client.receive_json()
    assert event["event"]["type"] == "init"


async def test_layout_subscribe_event_on_save(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    tab_dashboard: SaveDashboard,
) -> None:
    """Saving a dashboard pushes a converted event to subscribers."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "apollo_tab/layout/subscribe"})
    response = await client.receive_json()
    assert response["success"], response
    assert response["result"] is None
    msg_id = response["id"]
    await tab_dashboard(TAB_CONFIG)
    message = await client.receive_json()
    assert message["id"] == msg_id
    event = message["event"]
    assert event["type"] == "converted"
    assert event["url_path"] == "tab-1"
    assert len(event["hash"]) == 16
    assert event["warnings"] == 0


async def test_card_subscribe_as_non_admin(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    hass_read_only_access_token: str,
) -> None:
    """Card subscriptions are available to read-only users."""
    hass.states.async_set("light.kitchen", "on")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json_auto_id(
        {
            "type": "apollo_tab/card/subscribe",
            "card": {
                "component": "apollo/light-tile",
                "params": {"entity": "light.kitchen"},
            },
        }
    )
    response = await client.receive_json()
    assert response["success"], response
    assert response["result"] is None
    msg_id = response["id"]
    init = await client.receive_json()
    assert init["id"] == msg_id
    assert init["event"]["type"] == "init"
    values = await client.receive_json()
    assert values["id"] == msg_id
    assert values["event"]["type"] == "values"


async def test_commands_report_not_loaded(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """Every command answers not_loaded while the entry is unloaded."""
    await setup_integration(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)
    commands = [
        {"type": "apollo_tab/strings"},
        {"type": "apollo_tab/library"},
        {"type": "apollo_tab/library/subscribe"},
        {"type": "apollo_tab/library/reload"},
        {
            "type": "apollo_tab/library/approve",
            "component_id": "apollo/lock",
            "approved": True,
        },
        {"type": "apollo_tab/card/subscribe", "card": {}},
        {
            "type": "apollo_tab/card/call",
            "card": {},
            "widget": 0,
            "event": "tap",
        },
        {"type": "apollo_tab/dashboards"},
        {"type": "apollo_tab/layout/get", "url_path": "tab-1"},
        {"type": "apollo_tab/layout/subscribe"},
    ]
    for command in commands:
        await client.send_json_auto_id(command)
        response = await client.receive_json()
        assert not response["success"], command
        assert response["error"]["code"] == "not_loaded", command
