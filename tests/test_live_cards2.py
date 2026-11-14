"""Schema 2 cards in a browser (cards spec C.8; I7).

card/subscribe and card/call make a schema 2 card as for layout version 2,
and every refusal of the tablet path holds for a browser too: the service
list, the card's own devices, typed values, the questions for locks,
covers and alarms, and the range, step and options of a change.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.apollo_tab import library as library_module, live as live_module

from .conftest import setup_integration

LAMP = "light.den"
LOCK = "lock.front"
DOOR = "cover.garage"
ALARM = "alarm_control_panel.home"

KIT = """\
schema: 2
id: test/kit
version: 1.0.0
name: Kit
icon: mdi:play
params:
  lamp: {domain: light}
  lock: {domain: lock}
  door: {domain: cover}
  alarm: {domain: alarm_control_panel}
options:
  speeds: {type: choice, multiple: true, max: 4, section: controls, label: Speeds,
           default: [a, b], choices: {a: Slow, b: Fast}}
inputs:
  top: "{{ state_attr(lamp, 'top') }}"
  level: "{{ state_attr(lamp, 'level') }}"
outputs:
  toggle: {action: light.toggle, feedback: optimistic, data: {entity_id: "{{ lamp }}"}}
  level:  {action: light.turn_on, feedback: optimistic,
           data: {entity_id: "{{ lamp }}", brightness: "{{ value }}"}}
  speed:  {action: light.turn_on, feedback: pulse,
           data: {entity_id: "{{ lamp }}", effect: "{{ option }}"}}
  unlock: {action: lock.unlock, feedback: confirm, data: {entity_id: "{{ lock }}"}}
  open:   {action: cover.open_cover, feedback: pulse, data: {entity_id: "{{ door }}"}}
  disarm: {action: alarm_control_panel.alarm_disarm, feedback: confirm,
           data: {entity_id: "{{ alarm }}"}}
tap:
  default: toggle
  choices:
    toggle: {label: Turns it on or off, output: toggle}
variants:
  all:
    name: All
    grid: [12, 6]
    header: none
    layout:
      - {type: slider, value: level, min: 0, max: "{{ top }}", step: 5,
         on_change: level}
      - {type: choice, options: speeds, on_change: speed}
      - {type: button, text: Unlock, on_tap: unlock}
      - {type: button, text: Open, on_tap: open}
      - {type: button, text: Disarm, on_tap: disarm}
"""

CARD = {
    "type": "custom:apollo-tab-card",
    "component": "test/kit",
    "params": {"lamp": LAMP, "lock": LOCK, "door": DOOR, "alarm": ALARM},
}

LIGHT_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "apollo/light",
    "variant": "tile",
    "params": {"entity": LAMP},
}


@pytest.fixture(autouse=True)
def builtin_kit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Serve the built-in files plus the card above as a built-in."""
    folder = tmp_path / "builtin"
    shutil.copytree(library_module._BUILTIN_DIR, folder)
    (folder / "components" / "test-kit.yaml").write_text(KIT, encoding="utf-8")
    monkeypatch.setattr(library_module, "_BUILTIN_DIR", folder)
    return folder


def _states(hass: HomeAssistant) -> None:
    """Give every device of the kit a state."""
    hass.states.async_set(
        LAMP,
        "on",
        {"top": 100, "level": 40, "brightness": 128, "rgb_color": [255, 179, 71]},
    )
    hass.states.async_set(LOCK, "locked")
    hass.states.async_set(DOOR, "closed", {"device_class": "garage"})
    hass.states.async_set(ALARM, "armed_home")


async def _event(client: Any) -> dict:
    """Receive one websocket message and return its event payload."""
    message = await client.receive_json()
    assert message["type"] == "event", message
    return message["event"]


async def _subscribe(client: Any, card: dict, **extra: Any) -> dict:
    """Subscribe to a card and return its init event (and read its values)."""
    await client.send_json_auto_id(
        {"type": "apollo_tab/card/subscribe", "card": card, **extra}
    )
    result = await client.receive_json()
    assert result["success"], result
    init = await _event(client)
    if init["type"] == "init":
        values = await _event(client)
        assert values["type"] == "values"
    return init


async def _call(client: Any, card: dict, widget: int, event: str, **extra: Any) -> dict:
    """Send a card call and return the result message."""
    await client.send_json_auto_id(
        {
            "type": "apollo_tab/card/call",
            "card": card,
            "widget": widget,
            "event": event,
            **extra,
        }
    )
    # Values events of the subscription may come first.
    while True:
        message = await client.receive_json()
        if message["type"] == "result":
            return message


def _widget(init: dict, kind: str, text: str | None = None) -> int:
    """Return the index of the card's first widget of a kind (and text)."""
    for widget in init["card"]["widgets"]:
        if widget["t"] == kind and (text is None or widget.get("text") == text):
            return widget["i"]
    raise AssertionError(f"no {kind} {text}")


async def _ready(hass, config_entry, hass_ws_client) -> tuple[Any, dict]:
    """Set the kit up, subscribe and return the client and the init event."""
    _states(hass)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    init = await _subscribe(client, CARD)
    assert init["type"] == "init", init
    await hass.async_block_till_done()
    return client, init


async def test_a_stored_light_card_is_drawn_in_a_browser(
    hass, config_entry, hass_ws_client
) -> None:
    """A stored apollo/light card no longer shows an error (C.8)."""
    _states(hass)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    init = await _subscribe(client, LIGHT_CARD)
    assert init["type"] == "init", init
    card = init["card"]
    assert card["schema"] == 2
    assert card["variant"] == "tile"
    assert card["hold"] == {"local": "detail"}
    # Made for layout version 2: the tablet's v2 look, as the editor draws it.
    assert any(widget.get("look") == 1 for widget in card["widgets"])
    # Server-side parts stay on the server.
    for key in ("slots", "actions", "call"):
        assert key not in card


async def test_the_detail_copy_is_made_on_request(
    hass, config_entry, hass_ws_client
) -> None:
    """The detail flag asks for the detail copy; a card without one is refused."""
    _states(hass)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    init = await _subscribe(client, LIGHT_CARD, detail=True)
    assert init["type"] == "init", init
    assert init["card"]["variant"] == "full"
    assert "hold" not in init["card"]
    refused = await _subscribe(client, CARD, detail=True)
    assert refused == {
        "type": "error",
        "code": "invalid_card",
        "message": "This card has no detail page",
    }


async def test_a_tap_on_the_card_runs_its_own_output(
    hass, config_entry, hass_ws_client
) -> None:
    """Widget -1 is the card itself: its tap runs the card's output."""
    client, _init = await _ready(hass, config_entry, hass_ws_client)
    calls = async_mock_service(hass, "light", "toggle")
    result = await _call(client, CARD, -1, "tap")
    assert result["success"], result
    assert [call.data for call in calls] == [{"entity_id": LAMP}]
    # The card itself takes no change.
    result = await _call(client, CARD, -1, "change", value=1)
    assert result["error"]["code"] == "unknown_widget"


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        (40, True),
        (100, True),
        (42, False),  # off the step of 5
        (105, False),  # above the live max
        (-5, False),
    ],
)
async def test_a_change_keeps_to_range_and_step(
    hass, config_entry, hass_ws_client, value, ok
) -> None:
    """A slider change is checked as a tablet's: live max and step (contract 7.3)."""
    client, init = await _ready(hass, config_entry, hass_ws_client)
    calls = async_mock_service(hass, "light", "turn_on")
    result = await _call(client, CARD, _widget(init, "slider"), "change", value=value)
    assert result["success"] is ok, result
    if ok:
        assert calls[-1].data == {"entity_id": LAMP, "brightness": value}
    else:
        assert result["error"]["code"] == "invalid_value"
        assert calls == []


async def test_a_live_limit_without_a_value_refuses_the_change(
    hass, config_entry, hass_ws_client
) -> None:
    """Without a value for the live max, nothing is let through."""
    client, init = await _ready(hass, config_entry, hass_ws_client)
    hass.states.async_set(LAMP, "on", {"level": 40})
    await hass.async_block_till_done()
    calls = async_mock_service(hass, "light", "turn_on")
    result = await _call(client, CARD, _widget(init, "slider"), "change", value=40)
    assert result["error"]["code"] == "invalid_value"
    assert calls == []


@pytest.mark.parametrize(
    ("value", "ok"), [(0, True), (1, True), (2, False), (0.5, False)]
)
async def test_a_choice_names_one_of_its_options(
    hass, config_entry, hass_ws_client, value, ok
) -> None:
    """A choice sends the server's own option for an index, and nothing else."""
    client, init = await _ready(hass, config_entry, hass_ws_client)
    calls = async_mock_service(hass, "light", "turn_on")
    result = await _call(client, CARD, _widget(init, "choice"), "change", value=value)
    assert result["success"] is ok, result
    if ok:
        assert calls[-1].data == {"entity_id": LAMP, "effect": ["a", "b"][value]}
    else:
        assert result["error"]["code"] == "invalid_value"
        assert calls == []


@pytest.mark.parametrize(
    ("text", "domain", "service"),
    [
        ("Unlock", "lock", "unlock"),
        ("Open", "cover", "open_cover"),
        ("Disarm", "alarm_control_panel", "alarm_disarm"),
    ],
)
async def test_locks_garages_and_alarms_ask_first(
    hass, config_entry, hass_ws_client, text, domain, service
) -> None:
    """A lock, a garage door and an alarm need confirmed, as on a tablet."""
    client, init = await _ready(hass, config_entry, hass_ws_client)
    # The domain asks by itself, whatever the file's feedback says.
    for output in config_entry.runtime_data.library.components["test/kit"][
        "outputs"
    ].values():
        output["feedback"] = "pulse"
    calls = async_mock_service(hass, domain, service)
    widget = _widget(init, "button", text)
    result = await _call(client, CARD, widget, "tap")
    assert result["error"]["code"] == "confirm_required"
    assert calls == []
    result = await _call(client, CARD, widget, "tap", confirmed=True)
    assert result["success"], result
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("change", "code"),
    [
        # A service outside the allow lists.
        ({"action": "shell_command.run"}, "not_allowed"),
        # A service of another domain than the card's device.
        ({"action": "switch.toggle"}, "not_allowed"),
        # A device that is not the card's.
        ({"data": {"entity_id": "{{ other }}"}}, "not_allowed"),
        ({"data": {"entity_id": "light.kitchen"}}, "not_allowed"),
        # Data that would widen the call.
        ({"data": {"entity_id": "{{ lamp }}", "area_id": "den"}}, "not_allowed"),
        # A colour key that is text, not a list of numbers.
        (
            {"data": {"entity_id": "{{ lamp }}", "rgb_color": "{{ 'red' }}"}},
            "not_allowed",
        ),
    ],
)
async def test_the_tablet_refusals_hold_in_a_browser(
    hass, config_entry, hass_ws_client, change, code
) -> None:
    """The service list, the card's devices and typed values are checked again."""
    client, _init = await _ready(hass, config_entry, hass_ws_client)
    component = config_entry.runtime_data.library.components["test/kit"]
    component["outputs"]["toggle"].update(change)
    lights = async_mock_service(hass, "light", "toggle")
    switches = async_mock_service(hass, "switch", "toggle")
    result = await _call(client, CARD, -1, "tap")
    assert not result["success"]
    assert result["error"]["code"] == code
    assert lights == []
    assert switches == []


async def test_an_example_card_calls_nothing(
    hass, config_entry, hass_ws_client
) -> None:
    """A card without its devices is an example and sends nothing."""
    client, _init = await _ready(hass, config_entry, hass_ws_client)
    calls = async_mock_service(hass, "light", "toggle")
    # The light has preview values, so without its device it is an example.
    example = {**LIGHT_CARD, "params": {}}
    result = await _call(client, example, -1, "tap")
    assert result["error"]["code"] == "demo"
    assert calls == []


COLOUR_LAMP = {
    "brightness": 128,
    "hs_color": [30, 40],
    "supported_color_modes": ["hs", "color_temp"],
    "color_mode": "hs",
    "min_color_temp_kelvin": 2000,
    "max_color_temp_kelvin": 6500,
}


async def test_a_hue_change_keeps_the_lamps_strength(
    hass, config_entry, hass_ws_client
) -> None:
    """set_hue uses sat: a browser sends the lamp's own strength, not 100."""
    hass.states.async_set(LAMP, "on", COLOUR_LAMP)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    card = {
        **LIGHT_CARD,
        "variant": "large",
        "options": {"colour_control": "both", "show_saturation": True},
    }
    init = await _subscribe(client, card)
    assert init["type"] == "init", init
    calls = async_mock_service(hass, "light", "turn_on")
    hue = next(
        widget
        for widget in init["card"]["widgets"]
        if widget["t"] == "slider" and widget.get("max") == 360
    )
    result = await _call(client, card, hue["i"], "change", value=120)
    assert result["success"], result
    assert list(calls[-1].data["hs_color"]) == [120, 40]
    # The default favourites: the eighth is a warm white.
    result = await _call(client, card, _widget(init, "choice"), "change", value=7)
    assert result["success"], result
    assert calls[-1].data["color_temp_kelvin"] == 2700


async def test_the_cards_own_favourites_are_sent(
    hass, config_entry, hass_ws_client
) -> None:
    """A favourites list of the card's own: each cell sends its own colour."""
    hass.states.async_set(LAMP, "on", COLOUR_LAMP)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    card = {
        **LIGHT_CARD,
        "variant": "large",
        "options": {"colour_control": "dots", "favourites": ["#00FF00", "3000K"]},
    }
    init = await _subscribe(client, card)
    assert init["type"] == "init", init
    choice = _widget(init, "choice")
    calls = async_mock_service(hass, "light", "turn_on")
    result = await _call(client, card, choice, "change", value=0)
    assert result["success"], result
    assert list(calls[-1].data["rgb_color"]) == [0, 255, 0]
    assert "color_temp_kelvin" not in calls[-1].data
    result = await _call(client, card, choice, "change", value=1)
    assert result["success"], result
    assert calls[-1].data["color_temp_kelvin"] == 3000
    # Only two cells: a third is refused.
    result = await _call(client, card, choice, "change", value=2)
    assert result["error"]["code"] == "invalid_value"


async def test_a_browser_call_reads_the_hubs_last_value(
    hass, config_entry, hass_ws_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The call takes the value the card was shown, from the slot hub (C.2.8)."""
    hass.states.async_set(LAMP, "on", COLOUR_LAMP)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    card = {
        **LIGHT_CARD,
        "variant": "large",
        "options": {"colour_control": "both", "show_saturation": True},
    }
    init = await _subscribe(client, card)
    assert init["type"] == "init", init
    await hass.async_block_till_done()
    # A fresh render now gives something else: only the hub has the right one.
    renders: list[str] = []

    async def fresh_render(_hass: HomeAssistant, text: str, _variables: dict) -> Any:
        renders.append(text)
        return 5

    monkeypatch.setattr(live_module, "async_render_limited", fresh_render)
    calls = async_mock_service(hass, "light", "turn_on")
    hue = next(
        widget
        for widget in init["card"]["widgets"]
        if widget["t"] == "slider" and widget.get("max") == 360
    )
    result = await _call(client, card, hue["i"], "change", value=120)
    assert result["success"], result
    assert list(calls[-1].data["hs_color"]) == [120, 40]
    assert renders == []
