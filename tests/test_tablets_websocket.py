"""Tests for the tablet websocket commands (design 4.6)."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.apollo_tab.sender import STATUS_ON_TABLET
from custom_components.apollo_tab.tablets import async_get_tablets

from .conftest import MakeTablet, SaveTabDashboard, setup_integration, until

MAC = "aa:bb:cc:dd:ee:01"
TABLET_KEYS = {
    "mac",
    "device_id",
    "name",
    "short_name",
    "model",
    "dashboard",
    "status",
    "reason",
    "retry",
    "engine",
    "paired",
    "input",
    "entity_id",
    "approved",
    "suggested",
    "reauth",
    "reauth_name",
}


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


async def command(client, message: dict) -> dict:
    """Send one command and return the response."""
    await client.send_json_auto_id(message)
    return await client.receive_json()


async def test_tablets_exact_shape(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    device_registry: dr.DeviceRegistry,
) -> None:
    """apollo_tab/tablets returns the Tablet shape and nothing else."""
    make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(), title="Home")
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    client = await hass_ws_client(hass)

    response = await command(client, {"type": "apollo_tab/tablets"})
    assert response["success"], response
    device = async_get_tablets(hass)[MAC]
    assert response["result"] == {
        "tablets": [
            {
                "mac": MAC,
                "device_id": device.id,
                "name": "Kitchen Tablet",
                "short_name": "Kitchen",
                "model": "TAB-1",
                "dashboard": "tab-home",
                "status": "on_tablet",
                "reason": "",
                "retry": False,
                "engine": "0.1.0",
                "paired": True,
                "input": "ok",
                "entity_id": "select.kitchen_tablet_dashboard",
                "approved": True,
                "suggested": None,
                "reauth": None,
                "reauth_name": None,
            }
        ]
    }
    assert "allow_sensitive" not in str(response)


async def test_tablet_names(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
) -> None:
    """The user's name wins, then "<area> tablet", then the device name."""
    make_tablet(mac="AA:BB:CC:DD:EE:01", name="Apollo TAB-1 0001")
    make_tablet(mac="AA:BB:CC:DD:EE:02", name="Apollo TAB-1 0002")
    make_tablet(mac="AA:BB:CC:DD:EE:03", name="Apollo TAB-1 0003")
    make_tablet(mac="AA:BB:CC:DD:EE:04", name="Apollo TAB-1 0004")
    hall = area_registry.async_create("Hall")
    devices = async_get_tablets(hass)
    device_registry.async_update_device(
        devices["aa:bb:cc:dd:ee:01"].id, name_by_user="Wall TABLET"
    )
    device_registry.async_update_device(
        devices["aa:bb:cc:dd:ee:02"].id, area_id=hall.id
    )
    device_registry.async_update_device(
        devices["aa:bb:cc:dd:ee:03"].id, area_id=hall.id
    )
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)

    response = await command(client, {"type": "apollo_tab/tablets"})
    names = {
        tablet["mac"]: (tablet["name"], tablet["short_name"])
        for tablet in response["result"]["tablets"]
    }
    assert names == {
        "aa:bb:cc:dd:ee:01": ("Wall TABLET", "Wall"),
        "aa:bb:cc:dd:ee:02": ("Hall tablet (ee02)", "Hall (ee02)"),
        "aa:bb:cc:dd:ee:03": ("Hall tablet (ee03)", "Hall (ee03)"),
        "aa:bb:cc:dd:ee:04": ("Apollo TAB-1 0004", "Apollo TAB-1 0004"),
    }
    # Sorted by name.
    assert [tablet["name"] for tablet in response["result"]["tablets"]] == [
        "Apollo TAB-1 0004",
        "Hall tablet (ee02)",
        "Hall tablet (ee03)",
        "Wall TABLET",
    ]


async def test_subscribe_sends_at_once_on_change_and_on_unload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """The first event comes at once, then one after changes, then not_loaded."""
    make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config("A"), title="A")
    await save_tab_dashboard("tab-b", tab_config("B"), title="B")
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    client = await hass_ws_client(hass)

    response = await command(client, {"type": "apollo_tab/tablets/subscribe"})
    assert response["success"], response
    subscription = response["id"]
    first = await client.receive_json()
    assert first["id"] == subscription
    assert first["event"]["type"] == "tablets"
    assert [tablet["dashboard"] for tablet in first["event"]["tablets"]] == ["tab-a"]

    await command(
        client, {"type": "apollo_tab/tablet/assign", "mac": MAC, "url_path": "tab-b"}
    )
    events = []
    while True:
        message = await client.receive_json()
        assert message["id"] == subscription
        events.append(message["event"])
        tablet = message["event"]["tablets"][0]
        if tablet["dashboard"] == "tab-b" and tablet["status"] == "on_tablet":
            break
    assert all(set(t) == TABLET_KEYS for e in events for t in e["tablets"])

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    message = await client.receive_json()
    while message["event"]["type"] == "tablets":
        message = await client.receive_json()
    assert message == {
        "id": subscription,
        "type": "event",
        "event": {"type": "not_loaded"},
    }


async def test_assign(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Assigning returns the tablet sending the new dashboard; errors are plain."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config("A"), title="A")
    await save_tab_dashboard("tab-b", tab_config("B"), title="B")
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    client = await hass_ws_client(hass)

    response = await command(
        client,
        {"type": "apollo_tab/tablet/assign", "mac": MAC.upper(), "url_path": "tab-b"},
    )
    assert response["success"], response
    assert response["result"]["tablet"]["dashboard"] == "tab-b"
    assert response["result"]["tablet"]["status"] == "sending"
    await until(
        hass,
        lambda: (
            session.status == STATUS_ON_TABLET
            and tablet.active == session.want.hash
            and session.want.url_path == "tab-b"
        ),
    )

    response = await command(
        client,
        {"type": "apollo_tab/tablet/assign", "mac": "aa:00", "url_path": "tab-b"},
    )
    assert response["error"] == {
        "code": "not_found",
        "message": "This tablet is not known",
    }
    response = await command(
        client,
        {"type": "apollo_tab/tablet/assign", "mac": MAC, "url_path": "nope"},
    )
    assert response["error"] == {
        "code": "unknown_dashboard",
        "message": "This dashboard does not exist",
    }
    assert config_entry.runtime_data.assignments.dashboard(MAC) == "tab-b"


async def test_pair(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Pairing makes a new secret (here at once: the last one is a minute old)."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config("A"))
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    old_secret = tablet.secret
    session._last_pair -= 61
    client = await hass_ws_client(hass)

    response = await command(client, {"type": "apollo_tab/tablet/pair", "mac": MAC})
    assert response["success"], response
    assert set(response["result"]["tablet"]) == TABLET_KEYS
    await until(hass, lambda: len(tablet.calls_of("tab_pair")) == 2)
    await until(hass, lambda: session.status == STATUS_ON_TABLET and session.paired)
    assert tablet.secret != old_secret
    assert tablet.secret == config_entry.runtime_data.assignments.secret(MAC)

    response = await command(client, {"type": "apollo_tab/tablet/pair", "mac": "x"})
    assert response["error"]["code"] == "not_found"


async def test_no_update_command(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """There is no per-tablet setting to change, so no update command."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    response = await command(
        client,
        {"type": "apollo_tab/tablet/update", "mac": MAC, "allow_sensitive": True},
    )
    assert response["error"]["code"] == "unknown_command"


async def test_dashboards_order_shown_on_and_sent(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Dashboards come in (title, url_path) order with the tablets on each."""
    make_tablet(mac="AA:BB:CC:DD:EE:01", name="Kitchen Tablet")
    make_tablet(mac="AA:BB:CC:DD:EE:02", name="Hall Tablet")
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-z", tab_config(), title="beta")
    await save_tab_dashboard("tab-b", tab_config(), title="Alpha")
    await save_tab_dashboard("tab-a", tab_config(), title="Alpha")
    sender = config_entry.runtime_data.sender
    await until(
        hass,
        lambda: all(s.status == STATUS_ON_TABLET for s in sender.sessions.values()),
    )
    client = await hass_ws_client(hass)

    response = await command(client, {"type": "apollo_tab/dashboards"})
    result = response["result"]
    assert [d["url_path"] for d in result["dashboards"]] == ["tab-a", "tab-b", "tab-z"]
    # The first dashboard created went to both tablets and stays there.
    assert [d["shown_on"] for d in result["dashboards"]] == [
        [],
        [],
        ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"],
    ]
    assert result["tablets"] == 2
    assert result["sent_to_tablets"] is True
    assert "has_sensitive" not in result["dashboards"][0]
