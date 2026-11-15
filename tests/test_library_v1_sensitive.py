"""A `v1` that names a lock or alarm card makes a person's file sensitive (C.6).

A card file from the person's folder with no action of its own could name
the built-in Lock or Alarm card as its version 1 form, and a tablet with
engine 0.1.0 would then show Unlock or Disarm for it with no admin's
approval. Such a file needs approval like one that acts on a lock itself.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.apollo_tab import sender as sender_module
from custom_components.apollo_tab.library import Library
from custom_components.apollo_tab.maker.convert import convert_dashboard
from custom_components.apollo_tab.sender import STATUS_ON_TABLET
from tests.conftest import setup_integration, until
from tests.fake_tablet import ENGINE_V2

HERE = Path(__file__).parent
ICONS = json.loads((HERE / "contract" / "icons.json").read_text(encoding="utf-8"))
MAC = "aa:bb:cc:dd:ee:01"

DOOR_STATUS = """\
schema: 2
id: me/door-status
version: 1.0.0
name: Door status
icon: mdi:door
params:
  entity: {domain: lock, label: Door}
inputs:
  word: "{{ states(entity) }}"
state: word
v1: apollo/lock
variants:
  tile:
    name: Tile
    grid: [6, 3]
    header: tile
    layout:
      - {type: label, text: "{{ word }}", size: l}
"""
# The alarm card is named by a variant, not by the file.
ALARM_STATUS = """\
schema: 2
id: me/alarm-status
version: 1.0.0
name: Alarm status
icon: mdi:shield-home
params:
  entity: {domain: alarm_control_panel, label: Alarm}
inputs:
  word: "{{ states(entity) }}"
state: word
variants:
  big:
    name: Big
    grid: [12, 6]
    header: tile
    v1: apollo/alarm-panel
    layout:
      - {type: label, text: "{{ word }}", size: l}
"""
# Names a card that is not sensitive: nothing changes for it.
LIGHT_STATUS = """\
schema: 2
id: me/light-status
version: 1.0.0
name: Light status
params:
  entity: {domain: light, label: Light}
inputs:
  word: "{{ states(entity) }}"
state: word
v1: apollo/light-tile
variants:
  tile:
    name: Tile
    grid: [6, 3]
    header: tile
    layout:
      - {type: label, text: "{{ word }}", size: l}
"""


def _config(*cards: dict) -> dict:
    """Return a one-view dashboard with the given cards."""
    return {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [
            {
                "type": "sections",
                "path": "home",
                "title": "Home",
                "max_columns": 3,
                "sections": [{"type": "grid", "cards": list(cards)}],
            }
        ],
    }


def _card(component: str, entity: str) -> dict:
    """Return a card config of one component."""
    return {
        "type": "custom:apollo-tab-card",
        "component": component,
        "params": {"entity": entity},
    }


@pytest.fixture(autouse=True)
def no_input_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the test tap as fast as it likes."""
    monkeypatch.setattr(sender_module, "INPUTS_PER_SECOND", 10**6)


async def test_a_file_whose_v1_names_a_lock_or_alarm_card_needs_approval(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """The file is sensitive at load, whether the file or a variant names it."""
    user_components("door.yaml", DOOR_STATUS)
    user_components("alarm.yaml", ALARM_STATUS)
    user_components("light.yaml", LIGHT_STATUS)
    library = Library(hass)
    await library.async_load()
    assert library.errors == []
    listed = {item["id"]: item for item in library.as_dict()["components"]}
    for component_id in ("me/door-status", "me/alarm-status"):
        assert listed[component_id]["sensitive"] is True
        assert listed[component_id]["approved"] is False
    assert listed["me/light-status"]["sensitive"] is False
    assert listed["me/light-status"]["approved"] is True

    await library.async_set_approved("me/door-status", True)
    assert "me/door-status" in library.approved_ids()


@pytest.mark.parametrize("engine", ["0.1.0", ENGINE_V2])
async def test_no_tablet_gets_unlock_or_disarm_without_approval(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet,
    save_tab_dashboard,
    user_components: Callable[[str, str], Path],
    engine: str,
) -> None:
    """Both cards are left out with needs_approval; a tap runs nothing."""
    user_components("door.yaml", DOOR_STATUS)
    user_components("alarm.yaml", ALARM_STATUS)
    hass.states.async_set("lock.front_door", "locked")
    hass.states.async_set("alarm_control_panel.home", "armed_away")
    fake = make_tablet(engine=engine)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard(
        "tab-home",
        _config(
            _card("me/door-status", "lock.front_door"),
            _card("me/alarm-status", "alarm_control_panel.home"),
        ),
    )
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    unlocks = async_mock_service(hass, "lock", "unlock")
    disarms = async_mock_service(hass, "alarm_control_panel", "alarm_disarm")
    warnings = config_entry.runtime_data.manager.layouts["tab-home"]["warnings"]
    left_out = sorted(
        warning["detail"] for warning in warnings if warning["code"] == "needs_approval"
    )
    assert left_out == ["me/alarm-status", "me/door-status"]
    actions = session.want.bindings["actions"]
    assert actions == {}
    # A forged tap on any widget runs nothing.
    for widget in range(8):
        fake.tap(widget, confirmed=True)
    await hass.async_block_till_done()
    assert not unlocks
    assert not disarms


async def test_an_approved_file_gets_the_lock_card_on_an_old_tablet(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet,
    save_tab_dashboard,
    user_components: Callable[[str, str], Path],
) -> None:
    """After an admin's approval the old Lock card stands in, as C.6 says."""
    user_components("door.yaml", DOOR_STATUS)
    hass.states.async_set("lock.front_door", "locked")
    make_tablet(engine="0.1.0")
    await setup_integration(hass, config_entry)
    library = config_entry.runtime_data.library
    await library.async_set_approved("me/door-status", True)
    await save_tab_dashboard(
        "tab-home", _config(_card("me/door-status", "lock.front_door"))
    )
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    outputs = {
        (action["component"], action["output"])
        for action in session.want.bindings["actions"].values()
    }
    assert ("apollo/lock", "unlock") in outputs


async def test_the_converter_refuses_the_stand_in_for_an_unapproved_file(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """Also when a caller hands it a file the library did not mark."""
    user_components("door.yaml", DOOR_STATUS)
    library = Library(hass)
    await library.async_load()
    components = dict(library.components)
    unmarked = {**components["me/door-status"], "sensitive": False}
    components["me/door-status"] = unmarked
    config = _config(_card("me/door-status", "lock.front_door"))

    def outputs(approved: set[str]) -> set[tuple[str, str]]:
        result = convert_dashboard(
            config,
            components=components,
            themes=library.themes,
            approved=approved,
            icons=ICONS,
        )
        return {
            (action["component"], action["output"])
            for action in result["bindings"]["actions"].values()
        }

    assert not any(name == "apollo/lock" for name, _ in outputs(set()))
    assert ("apollo/lock", "unlock") in outputs({"me/door-status"})
