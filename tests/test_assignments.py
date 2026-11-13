"""Tests for which dashboard each tablet shows (design 4.1 to 4.3)."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.apollo_tab.assignments import (
    Assignments,
    dashboard_order,
    option_labels,
)
from custom_components.apollo_tab.compat import PROBE_ERROR, PROBE_MISSING
from custom_components.apollo_tab.sender import STATUS_ON_TABLET
from custom_components.apollo_tab.tablets import async_get_tablets

from .conftest import MakeTablet, SaveTabDashboard, setup_integration, until

KITCHEN = "aa:bb:cc:dd:ee:01"
HALL = "aa:bb:cc:dd:ee:02"
# The ESPHome config entry a tablet is approved under.
ENTRY = "esphome-entry-1"


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


PLAIN_CONFIG = {
    "views": [{"type": "sections", "path": "plain", "title": "Plain", "sections": []}]
}


class StubManager:
    """The parts of DashboardManager that Assignments uses."""

    def __init__(self, layouts: dict[str, str], ready: bool = True) -> None:
        """Hold {url_path: title}."""
        self.layouts = {path: {"title": title} for path, title in layouts.items()}
        self.ready = ready
        self.probe: tuple[str, dict | None] = (PROBE_MISSING, None)

    async def async_probe(self, url_path: str) -> tuple[str, dict | None]:
        """Return the prepared probe result."""
        return self.probe


async def delete_dashboard(client: Any, url_path: str) -> None:
    """Delete a storage dashboard by url_path."""
    await client.send_json_auto_id({"type": "lovelace/dashboards/list"})
    items = (await client.receive_json())["result"]
    dashboard_id = next(item["id"] for item in items if item["url_path"] == url_path)
    await client.send_json_auto_id(
        {"type": "lovelace/dashboards/delete", "dashboard_id": dashboard_id}
    )
    assert (await client.receive_json())["success"]


def test_one_order_everywhere() -> None:
    """(title in lower case, url_path) is the one order."""
    manager = StubManager(
        {"b-2": "home", "b-1": "Home", "c": "attic", "a": "Zoo", "d": "Äpfel"}
    )
    order = [item["url_path"] for item in dashboard_order(manager)]
    assert order == ["c", "b-1", "b-2", "a", "d"]


def test_option_labels_tell_equal_titles_apart() -> None:
    """Equal titles get the url_path added; others stay as they are."""
    labels = option_labels(
        [
            {"url_path": "home", "title": "Home"},
            {"url_path": "home-2", "title": "Home"},
            {"url_path": "bed", "title": "Bedroom"},
        ]
    )
    assert labels == {
        "home": "Home (home)",
        "home-2": "Home (home-2)",
        "bed": "Bedroom",
    }


@pytest.mark.parametrize(
    "case",
    json.loads((Path(__file__).parent / "label_cases.json").read_text())["cases"],
    ids=lambda case: case["name"],
)
def test_option_labels_are_unique_and_match_the_panel(case: dict) -> None:
    """Every option text is unique ignoring case; the panel uses the same cases."""
    labels = option_labels(case["rows"])
    assert labels == case["expect"]
    texts = [text.lower() for text in labels.values()]
    assert len(texts) == len(set(texts))


async def test_nothing_is_assigned_before_the_manager_is_ready(
    hass: HomeAssistant,
) -> None:
    """While HA starts, a new tablet waits and nobody is moved."""
    manager = StubManager({"tab-a": "A"}, ready=False)
    assignments = Assignments(hass, manager)
    await assignments.async_load()
    assignments.async_see({KITCHEN: ENTRY})
    assert assignments.dashboard(KITCHEN) is None
    assignments.async_fill()
    assert assignments.dashboard(KITCHEN) is None
    assert assignments.async_approve(KITCHEN, "tab-gone", ENTRY)
    await assignments.async_check_dashboard("tab-gone")
    assert assignments.dashboard(KITCHEN) == "tab-gone"

    manager.ready = True
    assignments.async_fill()
    assert assignments.dashboard(KITCHEN) == "tab-gone"
    await assignments.async_check_dashboard("tab-gone")
    assert assignments.dashboard(KITCHEN) == "tab-a"


async def test_unreadable_dashboard_keeps_its_tablets(hass: HomeAssistant) -> None:
    """A load error never moves a tablet; a later conversion clears the mark."""
    manager = StubManager({"tab-b": "B"})
    assignments = Assignments(hass, manager)
    assignments.async_see({KITCHEN: ENTRY})
    assignments.async_approve(KITCHEN, "tab-a", ENTRY)
    manager.probe = (PROBE_ERROR, None)
    await assignments.async_check_dashboard("tab-a")
    assert assignments.dashboard(KITCHEN) == "tab-a"
    assert assignments.unreadable == {"tab-a"}
    assignments.async_converted("tab-a")
    assert assignments.unreadable == set()


async def test_stopping_to_be_tab_dashboard_moves_tablets(
    hass: HomeAssistant,
) -> None:
    """A dashboard that loads without the apollo_tab key counts as deleted."""
    manager = StubManager({"tab-b": "B"})
    assignments = Assignments(hass, manager)
    assignments.async_see({KITCHEN: ENTRY, HALL: ENTRY})
    assignments.async_approve(KITCHEN, "tab-a", ENTRY)
    manager.probe = ("ok", PLAIN_CONFIG)
    await assignments.async_check_dashboard("tab-a")
    assert assignments.dashboard(KITCHEN) == "tab-b"
    # The hall tablet waits for an admin: it is not moved anywhere.
    assert assignments.dashboard(HALL) is None
    assert assignments.get(HALL)["dashboard"] is None


async def test_new_tablet_waits_and_keeps_the_admins_choice(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A new tablet gets no dashboard; the admin's pick stays when others come."""
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-m", tab_config(), title="Middle")
    await save_tab_dashboard("tab-z", tab_config(), title="Zoo")
    tablet = make_tablet(approved=False)
    await hass.async_block_till_done()
    assignments = config_entry.runtime_data.assignments
    session = config_entry.runtime_data.sender.sessions[KITCHEN]
    assert assignments.dashboard(KITCHEN) is None
    assert assignments.get(KITCHEN)["approved"] is False
    assert session.status == "new"
    assert tablet.calls == []

    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "apollo_tab/tablet/assign",
            "mac": KITCHEN,
            "url_path": "tab-z",
            "approve": True,
        }
    )
    assert (await client.receive_json())["success"]
    assert assignments.dashboard(KITCHEN) == "tab-z"
    await save_tab_dashboard("tab-a", tab_config(), title="Attic")
    assert assignments.dashboard(KITCHEN) == "tab-z"
    await until(hass, lambda: session.status == STATUS_ON_TABLET)


async def test_first_dashboard_goes_to_every_tablet_without_one(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """With no dashboards a tablet has none, until the first one is made."""
    kitchen = make_tablet(mac=KITCHEN.upper(), name="Kitchen Tablet")
    make_tablet(mac=HALL.upper(), name="Hall Tablet")
    await setup_integration(hass, config_entry)
    assignments = config_entry.runtime_data.assignments
    sessions = config_entry.runtime_data.sender.sessions
    await until(hass, lambda: sessions[KITCHEN].status == "no_dashboard")
    assert assignments.dashboard(KITCHEN) is None
    assert kitchen.calls_of("tab_layout") == []

    await save_tab_dashboard("tab-first", tab_config(), title="First")
    assert assignments.dashboard(KITCHEN) == "tab-first"
    assert assignments.dashboard(HALL) == "tab-first"
    await until(
        hass, lambda: all(s.status == STATUS_ON_TABLET for s in sessions.values())
    )


async def test_delete_moves_tablets_to_first_remaining(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_storage: dict,
) -> None:
    """Deleting a dashboard moves its tablets; others stay; it is stored."""
    make_tablet(mac=KITCHEN.upper(), name="Kitchen Tablet")
    make_tablet(mac=HALL.upper(), name="Hall Tablet")
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config("A"), title="A")
    await save_tab_dashboard("tab-b", tab_config("B"), title="B")
    await save_tab_dashboard("tab-c", tab_config("C"), title="C")
    assignments = config_entry.runtime_data.assignments
    assignments.async_assign(HALL, "tab-c")

    client = await hass_ws_client(hass)
    await delete_dashboard(client, "tab-a")
    await until(hass, lambda: assignments.dashboard(KITCHEN) == "tab-b")
    assert assignments.dashboard(HALL) == "tab-c"

    await delete_dashboard(client, "tab-b")
    await delete_dashboard(client, "tab-c")
    await until(
        hass,
        lambda: (
            assignments.dashboard(KITCHEN) is None
            and assignments.dashboard(HALL) is None
        ),
    )
    await assignments.async_flush()
    stored = hass_storage["apollo_tab.tablets"]["data"]["tablets"]
    assert stored[KITCHEN]["dashboard"] is None
    assert stored[HALL]["dashboard"] is None


async def test_dashboard_that_stops_being_tab_moves_tablets(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Saving a dashboard without the apollo_tab key moves its tablets."""
    make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config("A"), title="A")
    await save_tab_dashboard("tab-b", tab_config("B"), title="B")
    assignments = config_entry.runtime_data.assignments
    assert assignments.dashboard(KITCHEN) == "tab-a"

    await save_tab_dashboard("tab-a", PLAIN_CONFIG)
    await until(hass, lambda: assignments.dashboard(KITCHEN) == "tab-b")


async def test_assignment_survives_device_removal(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    make_tablet: MakeTablet,
    add_tablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A tablet added again under its ESPHome entry keeps what it had.

    Keyed by MAC: its approval, choice and secret stay.
    """
    esphome = MockConfigEntry(domain="esphome", title="Kitchen Tablet")
    esphome.add_to_hass(hass)
    make_tablet(entry=esphome)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config("A"), title="A")
    await save_tab_dashboard("tab-b", tab_config("B"), title="B")
    data = config_entry.runtime_data
    session = data.sender.sessions[KITCHEN]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    data.assignments.async_assign(KITCHEN, "tab-b")
    secret = data.assignments.secret(KITCHEN)

    device_registry.async_remove_device(async_get_tablets(hass)[KITCHEN].id)
    await hass.async_block_till_done()
    assert KITCHEN not in data.sender.sessions
    add_tablet(esphome)
    await hass.async_block_till_done()
    assert data.assignments.dashboard(KITCHEN) == "tab-b"
    assert data.assignments.secret(KITCHEN) == secret
    await until(hass, lambda: data.sender.sessions[KITCHEN].status == STATUS_ON_TABLET)


async def test_stored_records_load_back(hass: HomeAssistant, hass_storage) -> None:
    """A stored file loads back; damaged and older records are made safe.

    A record without "approved" (written before approval existed, or
    damaged) is a tablet that waits for an admin: no dashboard, no secret.
    """
    old = "aa:bb:cc:dd:ee:03"
    hass_storage["apollo_tab.tablets"] = {
        "version": 1,
        "key": "apollo_tab.tablets",
        "data": {
            "tablets": {
                KITCHEN: {
                    "dashboard": "tab-a",
                    "secret": "ab" * 32,
                    "kid": "c" * 16,
                    "approved": True,
                    "entry_id": ENTRY,
                },
                HALL: {
                    "dashboard": 5,
                    "secret": "zz",
                    "kid": None,
                    "approved": "yes",
                    "entry_id": 7,
                },
                old: {"dashboard": "tab-a", "secret": "ab" * 32, "kid": "c" * 16},
            }
        },
    }
    assignments = Assignments(
        hass, SimpleNamespace(layouts={"tab-a": {"title": "A"}}, ready=True)
    )
    await assignments.async_load()
    assert assignments.approved(KITCHEN)
    assert assignments.entry_id(KITCHEN) == ENTRY
    assert assignments.dashboard(KITCHEN) == "tab-a"
    assert assignments.secret(KITCHEN) == bytes.fromhex("ab" * 32)
    assert assignments.kid(KITCHEN) == "c" * 16
    assert assignments.get(KITCHEN) == {
        "dashboard": "tab-a",
        "secret": "ab" * 32,
        "kid": "c" * 16,
        "approved": True,
        "entry_id": ENTRY,
    }
    assert not assignments.approved(HALL)
    assert assignments.get(HALL) == {
        "dashboard": None,
        "secret": "zz",
        "kid": None,
        "approved": False,
        "entry_id": None,
    }
    assert assignments.dashboard(HALL) is None
    assert assignments.secret(HALL) is None
    # The older record waits: what it showed is only a suggestion, and its
    # secret is never used.
    assert not assignments.approved(old)
    assert assignments.dashboard(old) is None
    assert assignments.suggested(old) == "tab-a"
    assert assignments.secret(old) is None
    assert assignments.kid(old) is None
    assert assignments.shown_on("tab-a") == [KITCHEN]


async def test_delete_of_unreadable_dashboard_moves_its_tablets(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dashboard that cannot be read keeps its name; deleted, its tablets move.

    While it cannot be read it has no stored layout, so its deletion is not a
    "removed" layout. The tablets must still move to the first other one.
    """
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.exceptions import HomeAssistantError

    make_tablet(mac=KITCHEN)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(), title="Alpha")
    await save_tab_dashboard("tab-b", tab_config(), title="Beta")
    data = config_entry.runtime_data
    session = data.sender.sessions[KITCHEN]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert session.dashboard == "tab-a"
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "apollo_tab/layout/subscribe"})
    assert (await client.receive_json())["success"]

    async def broken(force: bool) -> dict:
        """Act like a YAML file with an error."""
        raise HomeAssistantError("bad")

    dashboard = hass.data[LOVELACE_DATA].dashboards["tab-a"]
    monkeypatch.setattr(dashboard, "async_load", broken)
    hass.bus.async_fire("lovelace_updated", {"url_path": "tab-a"})
    await until(hass, lambda: session.reason == "unreadable")
    assert session.dashboard == "tab-a"
    assert (await client.receive_json())["event"] == {
        "type": "removed",
        "url_path": "tab-a",
    }
    # It keeps its name: in the select, and for the panel.
    assert data.assignments.unreadable_dashboards() == [
        {"url_path": "tab-a", "title": "Alpha"}
    ]
    assert data.assignments.first_dashboard() == "tab-b"
    select = next(
        state
        for state in hass.states.async_all("select")
        if state.attributes.get("dashboard_id") == "tab-a"
    )
    assert select.state == "Alpha"
    assert select.attributes["options"] == ["Beta", "Alpha"]
    await client.send_json_auto_id({"type": "apollo_tab/dashboards"})
    result = (await client.receive_json())["result"]
    assert [row["url_path"] for row in result["dashboards"]] == ["tab-b"]
    assert result["unreadable"] == [{"url_path": "tab-a", "title": "Alpha"}]

    # Another look at it while it is still broken changes nothing, and the
    # panel is not told that a dashboard without a layout went away.
    hass.bus.async_fire("lovelace_updated", {"url_path": "tab-a"})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert session.dashboard == "tab-a"
    assert session.reason == "unreadable"

    await delete_dashboard(client, "tab-a")
    await until(hass, lambda: session.dashboard == "tab-b")
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert data.assignments.unreadable == set()
    assert data.assignments.unreadable_dashboards() == []
    select = hass.states.get(select.entity_id)
    assert select.state == "Beta"
    assert select.attributes["options"] == ["Beta"]


async def test_rename_tells_the_panel(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A rename in Home Assistant's settings reaches the layout subscribers."""
    make_tablet(mac=KITCHEN)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(), title="Alpha")
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "apollo_tab/layout/subscribe"})
    assert (await client.receive_json())["success"]
    await client.send_json_auto_id({"type": "lovelace/dashboards/list"})
    items = (await client.receive_json())["result"]
    await client.send_json_auto_id(
        {
            "type": "lovelace/dashboards/update",
            "dashboard_id": items[0]["id"],
            "title": "Bedroom",
        }
    )
    seen = [await client.receive_json(), await client.receive_json()]
    events = [message["event"] for message in seen if message["type"] == "event"]
    assert events == [{"type": "renamed", "url_path": "tab-a"}]
    assert config_entry.runtime_data.manager.layouts["tab-a"]["title"] == "Bedroom"
