"""Calls of schema 2 cards (cards spec C.2.8, C.5, C.9 "Actions"; package I6).

The card below is compiled and converted as a dashboard would be, so every
call runs from the bindings a tablet's tap would use.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from homeassistant.core import Context, HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.apollo_tab.live import (
    CallError,
    async_run_output,
    output_confirm_text,
)
from custom_components.apollo_tab.maker.convert import convert_dashboard
from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.schema import validate_component
from custom_components.apollo_tab.maker.templates import check_component_templates
from custom_components.apollo_tab.sandbox import ComponentTemplate

HERE = Path(__file__).resolve().parent
ICONS = json.loads((HERE / "contract" / "icons.json").read_text(encoding="utf-8"))
LIBRARY = HERE.parent / "custom_components" / "apollo_tab" / "library"
THEMES = {
    theme["id"]: {k: v for k, v in theme.items() if k != "id"}
    for theme in json.loads((LIBRARY / "themes.json").read_text(encoding="utf-8"))
}

CALLS = """\
schema: 2
id: test/calls
version: 1.0.0
name: Calls
icon: mdi:lightbulb
params:
  entity: {domain: light}
  group: {domain: [light, switch, fan], multiple: true, optional: true}
  covers: {domain: cover, multiple: true, optional: true}
  pick: {domain: select, optional: true}
options:
  favourites: {type: colours, section: controls, label: Favourite colours, max: 8,
               default: ["#FF0000", "2700K"]}
  word: {type: text, section: shows, label: Word, default: hi}
inputs:
  sat: "{{ (state_attr(entity, 'hs_color') or [0, 0])[1] }}"
  muted: "{{ state_attr(entity, 'muted') }}"
  members: "{{ state_attr(entity, 'members') }}"
outputs:
  hue:     {action: light.turn_on, uses: {sat: number}, feedback: optimistic,
            data: {entity_id: "{{ entity }}",
                   hs_color: ["{{ value }}",
                              "{{ sat if sat is number and sat >= 10 else 100 }}"]}}
  fav:     {action: light.turn_on, feedback: pulse,
            data: {entity_id: "{{ entity }}", rgb_color: "{{ option.rgb }}",
                   color_temp_kelvin: "{{ option.kelvin }}"}}
  favword: {action: light.turn_on, feedback: pulse,
            data: {entity_id: "{{ entity }}", effect: "{{ option }}"}}
  quiet:   {action: light.turn_on, uses: {muted: bool}, feedback: pulse,
            data: {entity_id: "{{ entity }}", flash_on: "{{ muted }}",
                   transition: "{{ 3 if muted else 1 }}"}}
  loud:    {action: light.turn_on, uses: {muted: bool}, feedback: pulse,
            data: {entity_id: "{{ entity }}", flash: "{{ muted ~ '!' }}"}}
  all:     {action: light.turn_on, uses: {members: entities}, feedback: pulse,
            data: {entity_id: "{{ members }}"}}
  each:    {action: {light: light.toggle, switch: switch.toggle}, feedback: optimistic,
            data: {entity_id: "{{ group }}"}}
  open:    {action: cover.open_cover, feedback: progress,
            data: {entity_id: "{{ covers }}"}}
  choose:  {action: select.select_option, feedback: optimistic,
            data: {entity_id: "{{ pick }}", option: "{{ option }}"}}
  say:     {action: light.turn_on, feedback: pulse,
            data: {entity_id: "{{ entity }}", effect: "{{ word }}",
                   brightness: "{{ value | int }}", transition: "{{ '' }}",
                   white: "{{ value * 0 }}"}}
variants:
  all:
    name: All
    grid: [36, 12]
    header: none
    layout:
      - {type: slider, value: sat, min: 0, max: 360, on_change: hue}
      - {type: choice, options: favourites, on_change: fav}
      - {type: choice, options: favourites, on_change: favword}
      - type: row
        items:
          - {type: button, text: Quiet, on_tap: quiet}
          - {type: button, text: Loud, on_tap: loud}
          - {type: button, text: All, on_tap: all}
          - {type: button, text: Each, on_tap: each, when: [has.group]}
          - {type: button, text: Open, on_tap: open, when: [has.covers]}
      - {type: choice, options: can.pick.options, on_change: choose, when: [has.pick]}
      - {type: slider, value: sat, min: 0, max: 255, step: 0, on_change: say}
"""
COMPONENT = validate_component(yaml.safe_load(CALLS))
check_component_templates(COMPONENT)
LAMP = "light.a"
PARAMS = {
    "entity": LAMP,
    "group": ["light.b", "switch.c", "fan.d"],
    "covers": ["cover.blind", "cover.garage"],
    "pick": "select.mode",
}
FACTS = {
    LAMP: facts_of({"domain": "light"}),
    "select.mode": facts_of(
        {
            "domain": "select",
            "state": {"attributes": {"options": ["None", "12", "[1, 2]"]}},
        }
    ),
    "cover.blind": facts_of({"domain": "cover"}),
    "cover.garage": facts_of(
        {"domain": "cover", "registry": {"device_class": "garage"}}
    ),
}


def _bindings(params: dict | None = None, options: dict | None = None) -> dict:
    """Convert a dashboard with the card; return its actions by output name."""
    card = {
        "type": "custom:apollo-tab-card",
        "component": "test/calls",
        "params": PARAMS if params is None else params,
        "options": options or {},
        "grid_options": {"columns": "full", "rows": 12},
    }
    config = {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [
            {
                "type": "sections",
                "path": "home",
                "title": "Home",
                "max_columns": 1,
                "sections": [{"type": "grid", "cards": [card]}],
            }
        ],
    }
    result = convert_dashboard(
        config,
        components={"test/calls": COMPONENT},
        themes=THEMES,
        approved=set(),
        facts=FACTS,
        dl=2,
        icons=ICONS,
    )
    found = {}
    for key, action in result["bindings"]["actions"].items():
        found[action["output"]] = {**action, "key": key}
    return found


async def _run(
    hass: HomeAssistant,
    action: dict,
    *,
    event: str = "tap",
    value: Any = None,
    widget: dict | None = None,
    confirmed: bool = False,
    params: dict | None = None,
    component: dict | None = None,
) -> None:
    """Run one output from its binding, as a tablet's input would."""
    await async_run_output(
        hass,
        component=component or COMPONENT,
        action_ref=action,
        params=action["params"] if params is None else params,
        entities=action["entities"],
        widget=widget or {"t": "button"},
        event=event,
        value=value,
        confirmed=confirmed,
        context=Context(),
    )


def _lamp(hass: HomeAssistant, **attributes: Any) -> None:
    """Put the lamp into the state machine."""
    hass.states.async_set(LAMP, "on", {"friendly_name": "Lamp", **attributes})


def test_the_bindings_carry_what_a_call_reads() -> None:
    """Values (options and facts) and the slots of the inputs in uses."""
    actions = _bindings()
    hue = actions["hue"]
    assert hue["values"]["options"]["word"] == "hi"
    assert hue["values"]["can"]["toggle"] is True
    assert hue["uses"]["sat"]["type"] == "number"
    assert hue["uses"]["sat"]["slot"]["kind"] == "template"
    assert "sat" in hue["uses"]["sat"]["slot"]["template"]
    assert "uses" not in actions["fav"]
    assert len(actions["choose"]["options"]) == 3


async def test_a_list_with_an_input_in_data(hass: HomeAssistant) -> None:
    """hs_color: each entry typed on its own; sat from HA's own value."""
    calls = async_mock_service(hass, "light", "turn_on")
    _lamp(hass, hs_color=[30, 55])
    action = _bindings()["hue"]
    slider = {"t": "slider", "min": 0, "max": 360, "step": 1}
    await _run(hass, action, event="change", value=200, widget=slider)
    assert calls[-1].data == {"entity_id": LAMP, "hs_color": [200, 55]}
    _lamp(hass, hs_color=[30, 2])
    await _run(hass, action, event="change", value=10, widget=slider)
    assert calls[-1].data == {"entity_id": LAMP, "hs_color": [10, 100]}


async def test_an_input_in_uses_never_comes_from_the_message(
    hass: HomeAssistant,
) -> None:
    """A binding that names a value of its own for sat is not read."""
    calls = async_mock_service(hass, "light", "turn_on")
    _lamp(hass, hs_color=[30, 60])
    action = _bindings()["hue"]
    forged = {**action, "vars": {"sat": 1}}
    slider = {"t": "slider", "min": 0, "max": 360, "step": 1}
    await _run(hass, forged, event="change", value=5, widget=slider)
    assert calls[-1].data["hs_color"] == [5, 60]


async def test_a_bool_input_in_data_and_one_that_renders_to_text(
    hass: HomeAssistant,
) -> None:
    """A bool passes as yes or no; text from a template that names it is refused.

    C.2.8: a value whose template names a number or bool input must come out
    as a number or yes or no.
    """
    calls = async_mock_service(hass, "light", "turn_on")
    _lamp(hass, muted=True)
    actions = _bindings()
    await _run(hass, actions["quiet"])
    assert calls[-1].data == {"entity_id": LAMP, "flash_on": True, "transition": 3}
    with pytest.raises(CallError) as err:
        await _run(hass, actions["loud"])
    assert err.value.code == "not_allowed"
    assert len(calls) == 1


async def test_an_entities_input_as_entity_id(hass: HomeAssistant) -> None:
    """The group's lights: every one must be a device of the card."""
    calls = async_mock_service(hass, "light", "turn_on")
    action = _bindings()["all"]
    _lamp(hass, members=[LAMP, "light.b"])
    await _run(hass, action)
    assert calls[-1].data == {"entity_id": [LAMP, "light.b"]}
    # (An input's own result is parsed as HA parses any template result.)
    for members in ([LAMP, "light.stranger"], [], None, "light.a, light.b", {"a": 1}):
        _lamp(hass, members=members)
        with pytest.raises(CallError) as err:
            await _run(hass, action)
        assert err.value.code == "not_allowed", members
    assert len(calls) == 1
    # A bad list is refused whole, never cleaned and run on the rest; also
    # when every good entry is one of the card's devices.
    many = [f"light.l{i}" for i in range(17)]
    for members, entities in (
        (many, many),
        ([LAMP, ["light.b"]], action["entities"]),
        ([LAMP, "Not an id"], action["entities"]),
    ):
        _lamp(hass, members=members)
        with pytest.raises(CallError) as err:
            await _run(hass, {**action, "entities": entities})
        assert err.value.code == "not_allowed", members
    assert len(calls) == 1


async def test_a_plain_action_on_a_device_of_another_domain(
    hass: HomeAssistant,
) -> None:
    """entity_id must be of the service's domain: a switch for light.turn_on fails."""
    calls = async_mock_service(hass, "light", "turn_on")
    action = _bindings()["quiet"]
    with pytest.raises(CallError) as err:
        await _run(
            hass,
            {**action, "entities": [*action["entities"], "switch.c"]},
            params={**action["params"], "entity": "switch.c"},
        )
    assert err.value.code == "not_allowed"
    assert calls == []


async def test_what_the_loader_refuses_is_refused_again_at_the_call(
    hass: HomeAssistant,
) -> None:
    """A Component changed after loading is still refused at the call.

    A map whose key and service differ, a list outside the colour keys, and
    text from a template that names an input.
    """
    switches = async_mock_service(hass, "switch", "toggle")
    lights = async_mock_service(hass, "light", "turn_on")
    _lamp(hass, members=[LAMP])
    each = _bindings()["each"]
    foreign = json.loads(json.dumps(COMPONENT))
    foreign["outputs"]["each"]["actions"] = {"light": "switch.toggle"}
    with pytest.raises(CallError) as err:
        await _run(
            hass,
            each,
            component=foreign,
            params={**each["params"], "group": ["light.b"]},
        )
    assert err.value.code == "not_allowed"
    listed = json.loads(json.dumps(COMPONENT))
    listed["outputs"]["quiet"]["data"]["effect"] = [1, 2]
    with pytest.raises(CallError) as err:
        await _run(hass, _bindings()["quiet"], component=listed)
    assert err.value.code == "not_allowed"
    named = json.loads(json.dumps(COMPONENT))
    named["outputs"]["all"]["data"]["effect"] = "{{ members ~ '' }}"
    with pytest.raises(CallError) as err:
        await _run(hass, _bindings()["all"], component=named)
    assert err.value.code == "not_allowed"
    assert switches == []
    assert lights == []


@pytest.mark.parametrize(
    "bad",
    [[], None, "", "['light.b']", [["light.b"]], {"entity_id": "light.b"}],
    ids=["empty_list", "none", "empty_text", "list_text", "nested", "mapping"],
)
async def test_entity_id_that_is_not_one_or_more_devices(
    hass: HomeAssistant, bad: Any
) -> None:
    """Each is not_allowed, before any call."""
    calls = async_mock_service(hass, "light", "toggle")
    action = _bindings()["each"]
    with pytest.raises(CallError) as err:
        await _run(hass, action, params={**action["params"], "group": bad})
    assert err.value.code == "not_allowed"
    assert calls == []


async def test_several_devices_with_one_that_is_not_the_cards(
    hass: HomeAssistant,
) -> None:
    """A list that names a device the card was not set up with is refused whole."""
    calls = async_mock_service(hass, "light", "toggle")
    action = _bindings()["each"]
    params = {**action["params"], "group": ["light.b", "light.stranger"]}
    with pytest.raises(CallError) as err:
        await _run(hass, action, params=params)
    assert err.value.code == "not_allowed"
    assert calls == []


async def test_an_action_per_kind_is_one_call_per_kind(hass: HomeAssistant) -> None:
    """Light and switch get their own call; the fan has no entry and is left out."""
    lights = async_mock_service(hass, "light", "toggle")
    switches = async_mock_service(hass, "switch", "toggle")
    fans = async_mock_service(hass, "fan", "toggle")
    action = _bindings()["each"]
    await _run(hass, action)
    assert [call.data for call in lights] == [{"entity_id": ["light.b"]}]
    assert [call.data for call in switches] == [{"entity_id": ["switch.c"]}]
    assert fans == []
    with pytest.raises(CallError) as err:
        await _run(hass, action, params={**action["params"], "group": ["fan.d"]})
    assert err.value.code == "not_allowed"


async def test_a_cover_list_with_one_garage_door_asks(hass: HomeAssistant) -> None:
    """One entity that needs the question makes the whole call ask."""
    calls = async_mock_service(hass, "cover", "open_cover")
    hass.states.async_set("cover.blind", "closed", {"device_class": "blind"})
    hass.states.async_set(
        "cover.garage", "closed", {"device_class": "garage", "friendly_name": "Garage"}
    )
    action = _bindings()["open"]
    with pytest.raises(CallError) as err:
        await _run(hass, action)
    assert err.value.code == "confirm_required"
    assert calls == []
    await _run(hass, action, confirmed=True)
    assert calls[-1].data == {"entity_id": ["cover.blind", "cover.garage"]}
    # The question the layout carries looks over every entity too.
    text = output_confirm_text(
        hass, COMPONENT, action, action["params"], action["entities"]
    )
    assert text == "Open Garage?"


async def test_option_takes_the_servers_copy_by_index(hass: HomeAssistant) -> None:
    """At, above and below the range and a fraction; names reach the device as text."""
    calls = async_mock_service(hass, "select", "select_option")
    action = _bindings()["choose"]
    choice = {"t": "choice"}
    for index, name in enumerate(["None", "12", "[1, 2]"]):
        await _run(hass, action, event="change", value=index, widget=choice)
        assert calls[-1].data == {"entity_id": "select.mode", "option": name}
        assert isinstance(calls[-1].data["option"], str)
    for bad in (3, -1, 1.5, True):
        with pytest.raises(CallError) as err:
            await _run(hass, action, event="change", value=bad, widget=choice)
        assert err.value.code == "invalid_value"
    assert len(calls) == 3


async def test_a_key_left_out_and_a_list_from_an_option(hass: HomeAssistant) -> None:
    """A favourite colour sends rgb_color; a white sends only its kelvin."""
    calls = async_mock_service(hass, "light", "turn_on")
    action = _bindings()["fav"]
    choice = {"t": "choice"}
    await _run(hass, action, event="change", value=0, widget=choice)
    assert calls[-1].data == {"entity_id": LAMP, "rgb_color": [255, 0, 0]}
    await _run(hass, action, event="change", value=1, widget=choice)
    assert calls[-1].data == {"entity_id": LAMP, "color_temp_kelvin": 2700}


async def test_a_mapping_as_a_data_value_is_refused(hass: HomeAssistant) -> None:
    """effect: '{{ option }}' over colours would send a mapping."""
    calls = async_mock_service(hass, "light", "turn_on")
    action = _bindings()["favword"]
    with pytest.raises(CallError) as err:
        await _run(hass, action, event="change", value=0, widget={"t": "choice"})
    assert err.value.code == "not_allowed"
    assert calls == []


async def test_text_options_are_data_and_typing_keeps_types(
    hass: HomeAssistant,
) -> None:
    """A text option holding template source reaches the call as that text."""
    calls = async_mock_service(hass, "light", "turn_on")
    for word in ("{{ 1/0 }}", "{% for x in range(9) %}x{% endfor %}"):
        action = _bindings(options={"word": word})["say"]
        slider = {"t": "slider", "min": 0, "max": 255, "step": 0}
        await _run(hass, action, event="change", value=99.7, widget=slider)
        assert calls[-1].data == {
            "entity_id": LAMP,
            "effect": word,
            "brightness": 99,
            "white": 0.0,
        }


async def test_an_option_of_the_wrong_type_is_dropped_on_the_call_path(
    hass: HomeAssistant,
) -> None:
    """A stored value that fails its option takes the default when a call runs."""
    calls = async_mock_service(hass, "light", "turn_on")
    action = _bindings()["say"]
    forged = {
        **action,
        "values": {**action["values"], "options": {"word": "x" * 41}},
    }
    slider = {"t": "slider", "min": 0, "max": 255, "step": 0}
    await _run(hass, forged, event="change", value=1, widget=slider)
    assert calls[-1].data["effect"] == "hi"


@pytest.mark.parametrize(
    "service",
    ["scene.apply", "scene.create", "media_player.join", "light.reload"],
)
async def test_services_outside_the_list_are_refused_again_at_the_call(
    hass: HomeAssistant, service: str
) -> None:
    """A Component that reached the call with such a service still calls nothing."""
    domain = service.partition(".")[0]
    calls = async_mock_service(hass, domain, service.partition(".")[2])
    action = _bindings()["quiet"]
    bad = json.loads(json.dumps(COMPONENT))
    bad["outputs"]["quiet"]["action"] = service
    with pytest.raises(CallError) as err:
        await _run(hass, action, component=bad)
    assert err.value.code == "not_allowed"
    per_kind = json.loads(json.dumps(COMPONENT))
    per_kind["outputs"]["each"]["actions"] = {"light": service}
    with pytest.raises(CallError) as err:
        await _run(hass, _bindings()["each"], component=per_kind)
    assert err.value.code == "not_allowed"
    assert calls == []


@pytest.mark.parametrize(
    "data",
    [
        'hs_color: "{{ [value, 100] }}"',
        "effect: \"{{ '{7, 1, 2}' }}\"",
        'effect: "{{ \\"b\'abc\'\\" }}"',
        "effect: \"{{ '...' }}\"",
    ],
    ids=["list", "set", "bytes", "ellipsis"],
)
async def test_a_schema_1_call_that_renders_a_list_is_refused(
    hass: HomeAssistant, data: str
) -> None:
    """A schema 1 call sends a text, a number, yes or no: no list, set or bytes."""
    component = validate_component(
        yaml.safe_load(
            f"""\
id: me/list
version: 1.0.0
name: List
size: 1x1
params:
  entity: {{domain: light}}
outputs:
  go:
    action: light.turn_on
    data: {{entity_id: "{{{{ entity }}}}", {data}}}
    feedback: pulse
layout:
  - {{type: slider, value: "{{{{ 1 }}}}", min: 0, max: 360, on_change: go}}
"""
        )
    )
    calls = async_mock_service(hass, "light", "turn_on")
    with pytest.raises(CallError) as err:
        await async_run_output(
            hass,
            component=component,
            action_ref={"output": "go", "vars": {}},
            params={"entity": LAMP},
            entities=[LAMP],
            widget={"t": "slider", "min": 0, "max": 360},
            event="change",
            value=20,
            confirmed=False,
            context=Context(),
        )
    assert err.value.code == "not_allowed"
    assert calls == []


def _refused(text: str, code: str) -> MakerError:
    """Load a card file that must be refused with code."""
    with pytest.raises(MakerError) as err:
        component = validate_component(yaml.safe_load(text))
        check_component_templates(component)
    assert err.value.code == code, err.value
    return err.value


def test_load_refusals_of_the_actions_list() -> None:
    """C.9: an input not in uses, a map with a foreign service, a lock tap."""
    base = CALLS.replace("variants:", "variants:", 1)
    # A template that prints a list for a colour key (C.2.8).
    _refused(
        base.replace(
            'rgb_color: "{{ option.rgb }}"', 'rgb_color: "{{ [value, 100, 0] }}"'
        ),
        "bad_value",
    )
    _refused(
        base.replace(
            'transition: "{{ 3 if muted else 1 }}"',
            'transition: "{{ sat }}"',
        ),
        "bad_template",
    )
    _refused(
        base.replace(
            "{light: light.toggle, switch: switch.toggle}",
            "{light: switch.toggle, switch: switch.toggle}",
        ),
        "domain_mismatch",
    )
    _refused(
        base.replace(
            "{light: light.toggle, switch: switch.toggle}",
            "{light: light.toggle, lock: lock.unlock}",
        ),
        "confirm_required",
    )
    lock = """\
schema: 2
id: test/door
version: 1.0.0
name: Door
icon: mdi:lock
params:
  entity: {domain: [lock, switch]}
outputs:
  go: {action: {lock: lock.unlock, switch: switch.toggle}, feedback: confirm,
       data: {entity_id: "{{ entity }}"}}
tap:
  choices:
    go: {label: Opens it, output: go}
layout:
  - {type: label, text: Door}
size: 1x1
"""
    _refused(lock, "action_not_allowed")
    sensitive = validate_component(
        yaml.safe_load(
            lock.replace(
                "tap:\n  choices:\n    go: {label: Opens it, output: go}\n", ""
            )
        )
    )
    assert sensitive["sensitive"] is True
    _refused(
        lock.replace("feedback: confirm", "feedback: optimistic"), "confirm_required"
    )


def test_a_card_tap_on_a_garage_door_is_left_out_by_the_converter() -> None:
    """The class is known when the layout is made: no tap, and tap_left_out."""
    text = """\
schema: 2
id: test/gate
version: 1.0.0
name: Gate
icon: mdi:garage
params:
  entity: {domain: cover}
outputs:
  move: {action: cover.toggle, feedback: progress, data: {entity_id: "{{ entity }}"}}
tap:
  choices:
    move: {label: Moves it, output: move}
layout:
  - {type: button, text: Move, on_tap: move}
size: 1x1
"""
    component = validate_component(yaml.safe_load(text))

    def convert(entity: str, facts: dict) -> dict:
        config = {
            "apollo_tab": {"version": 1, "theme": "midnight"},
            "views": [
                {
                    "type": "sections",
                    "path": "home",
                    "title": "Home",
                    "sections": [
                        {
                            "type": "grid",
                            "cards": [
                                {
                                    "type": "custom:apollo-tab-card",
                                    "component": "test/gate",
                                    "params": {"entity": entity},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        return convert_dashboard(
            config,
            components={"test/gate": component},
            themes=THEMES,
            approved=set(),
            facts=facts,
            dl=2,
            icons=ICONS,
        )

    garage = convert(
        "cover.garage",
        {
            "cover.garage": facts_of(
                {"domain": "cover", "registry": {"device_class": "garage"}}
            )
        },
    )
    card = garage["layout"]["pages"][0]["w"][0]
    assert "tap" not in card
    assert "tap_left_out" in [w["code"] for w in garage["warnings"]]
    # The button still moves it, and asks there.
    assert any("tap" in widget for widget in card["w"])
    blind = convert("cover.blind", {"cover.blind": facts_of({"domain": "cover"})})
    assert blind["layout"]["pages"][0]["w"][0]["tap"] == {"policy": "progress"}
    assert "tap_left_out" not in [w["code"] for w in blind["warnings"]]


async def test_the_rgb_filter_in_a_data_template(hass: HomeAssistant) -> None:
    """The filter rgb is in the sandbox too, for a template that is no reference."""

    def render(text: str, colour: Any) -> str:
        return ComponentTemplate(text, hass).async_render(
            {"c": colour}, parse_result=False, limited=True
        )

    assert render("{{ (c | rgb) | join(',') }}", 0xFF8000) == "255,128,0"
    assert render("{{ (c | rgb) | join(',') }}", "#00ff80") == "0,255,128"
    assert render("{{ (c | rgb) is none }}", "red") == "True"
