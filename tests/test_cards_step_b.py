"""The fourteen cards of step B (cards spec D.2, D.5, C.9 "Every card"; package I10).

Every card is a built-in schema 2 file. Each variant fits its grid with
nothing clipped for a device that can do everything and for one that can do
nothing, with every option on; every icon it names is in the contract's set;
its version 1 form per variant has a working control for its main action, or
shows its value; each card's main controls send what D.2 says.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
import yaml
from homeassistant.core import Context, HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.apollo_tab.live import async_run_output
from custom_components.apollo_tab.maker import device
from custom_components.apollo_tab.maker.compile2 import (
    compile_card2,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.const import UPDATE_NOTE
from custom_components.apollo_tab.maker.features import FACT_NAMES, facts_of
from custom_components.apollo_tab.maker.schema import validate_component
from custom_components.apollo_tab.maker.schema2 import iter_items
from custom_components.apollo_tab.maker.templates import check_component_templates
from tests.test_cards_step_a import (
    COMPONENTS,
    EVERYTHING_RAW,
    ICON_LEVEL,
    ICONS,
    LEVEL1,
    LIBRARY,
    _all_on,
    _cards,
    _convert,
    _dashboard,
    _label,
    _param_values,
    _value,
)

STEP_B = {
    "apollo/light-group": "apollo-light-group.yaml",
    "apollo/climate": "apollo-climate.yaml",
    "apollo/fan-speed": "apollo-fan-speed.yaml",
    "apollo/cover": "apollo-cover.yaml",
    "apollo/door-lock": "apollo-door-lock.yaml",
    "apollo/alarm": "apollo-alarm.yaml",
    "apollo/media": "apollo-media.yaml",
    "apollo/volume": "apollo-volume.yaml",
    "apollo/dial": "apollo-dial.yaml",
    "apollo/readings": "apollo-readings.yaml",
    "apollo/room": "apollo-room.yaml",
    "apollo/people": "apollo-people.yaml",
    "apollo/clock": "apollo-clock.yaml",
    "apollo/appliance": "apollo-appliance.yaml",
}


# ---------------------------------------------------------------- devices

ALL_MEDIA = [
    "PAUSE",
    "PREVIOUS_TRACK",
    "NEXT_TRACK",
    "VOLUME_SET",
    "VOLUME_MUTE",
    "SEEK",
    "TURN_ON",
    "TURN_OFF",
    "SHUFFLE_SET",
    "REPEAT_SET",
    "GROUPING",
]
CLIMATE_RAW = {
    "domain": "climate",
    "registry": {
        "capabilities": {
            "hvac_modes": [
                "off",
                "heat",
                "cool",
                "heat_cool",
                "auto",
                "dry",
                "fan_only",
            ],
            "preset_modes": [
                "eco",
                "away",
                "boost",
                "comfort",
                "home",
                "sleep",
                "none",
            ],
            "fan_modes": ["auto", "low", "medium", "high", "top", "middle", "focus"],
            "min_temp": 7,
            "max_temp": 35,
            "target_temp_step": 0.5,
        },
        "features": ["TARGET_TEMPERATURE", "TARGET_TEMPERATURE_RANGE", "TURN_OFF"],
    },
}
FAN_RAW = {
    "domain": "fan",
    "registry": {
        "capabilities": {
            "preset_modes": [
                "auto",
                "smart",
                "sleep",
                "nature",
                "breeze",
                "turbo",
                "eco",
                "quiet",
            ],
            "percentage_step": 25,
        },
        "features": ["SET_SPEED", "OSCILLATE", "DIRECTION"],
    },
}
COVER_FEATURES = [
    "SET_POSITION",
    "STOP",
    "OPEN_TILT",
    "CLOSE_TILT",
    "SET_TILT_POSITION",
]
GARAGE_RAW = {
    "domain": "cover",
    "registry": {"device_class": "garage", "features": COVER_FEATURES},
}
BLIND_RAW = {"domain": "cover", "registry": {"features": ["SET_POSITION", "STOP"]}}
MEDIA_RAW = {
    "domain": "media_player",
    "registry": {
        "capabilities": {"source_list": [f"Source {n}" for n in range(12)]},
        "features": ALL_MEDIA,
    },
}
ALARM_RAW = {
    "domain": "alarm_control_panel",
    "registry": {"features": ["ARM_HOME", "ARM_AWAY", "ARM_NIGHT", "ARM_VACATION"]},
}
ALARM_CODE_RAW = copy.deepcopy(ALARM_RAW)
ALARM_CODE_RAW["registry"]["capabilities"] = {"code_format": "number"}
LOCK_RAW = {"domain": "lock", "registry": {"features": ["OPEN"]}}
# A device of each kind that can do everything its kind can.
EVERYTHING_B = {
    **EVERYTHING_RAW,
    "climate": CLIMATE_RAW,
    "fan": FAN_RAW,
    "cover": GARAGE_RAW,
    "media_player": MEDIA_RAW,
    "alarm_control_panel": ALARM_CODE_RAW,
    "lock": LOCK_RAW,
}


def _facts(domain: str, everything: bool) -> dict:
    """Return what a device of a kind can do: everything, or nothing."""
    if everything and domain in EVERYTHING_B:
        return facts_of(EVERYTHING_B[domain])
    return facts_of({"domain": domain})


def _compile(
    component: dict,
    variant: str,
    params: dict,
    options: dict,
    facts: dict,
    dl: int = 2,
) -> dict:
    """Compile one variant in its own grid (the detail variant as the detail copy)."""
    spec = component["variants"][variant]
    columns, rows = spec["grid"]
    raw = {
        "params": params,
        "options": options,
        "variant": variant,
        "grid_options": {"columns": columns, "rows": rows},
    }
    card = validate_card_config2(component, raw)
    return compile_card2(component, card, facts, dl, detail=not spec["picker"])


def _inside(result: dict, label: str, allowed: tuple = ()) -> None:
    """Every widget sits inside the card, within its padding."""
    assert [w for w in result["warnings"] if w not in allowed] == [], label
    for widget in result["widgets"]:
        x, y, width, height = widget["r"]
        assert x >= 16 and y >= 8, (label, widget)
        assert x + width <= result["w"] - 16, (label, widget)
        assert y + height <= result["h"] - 16, (label, widget)
        assert width >= 1 and height >= 1, (label, widget)


def _kinds(result: dict) -> list[str]:
    """Return the widget types of a compiled card, in order."""
    return [w["t"] for w in result["widgets"]]


# ---------------------------------------------------------------- the files


def test_the_fourteen_files_are_built_in_and_load() -> None:
    """Each card loads, passes the template checks and is schema 2."""
    for component_id, file_name in STEP_B.items():
        path = LIBRARY / "components" / file_name
        component = validate_component(yaml.safe_load(path.read_text("utf-8")))
        check_component_templates(component)
        assert component["id"] == component_id
        assert component["schema"] == 2
        assert component["version"] == "2.0.0"
        assert COMPONENTS[component_id]["source"] == "builtin"


@pytest.mark.parametrize("component_id", list(STEP_B))
def test_every_icon_a_card_names_is_in_the_contracts_set(component_id: str) -> None:
    """The file's icon is of level 1; every constant icon of an item is in the set."""
    component = COMPONENTS[component_id]
    assert ICON_LEVEL[component["icon"]] == 1
    names = []
    for _path, item in iter_items(component):
        for key in ("icon", "value"):
            mark = item.get(key)
            if isinstance(mark, dict) and mark.get("form") == "const":
                value = mark["value"]
                if isinstance(value, str) and value.startswith("mdi:"):
                    names.append(value)
    for name in names:
        assert name in ICON_LEVEL, (component_id, name)


def test_the_icons_a_template_names_are_in_the_contracts_set() -> None:
    """The icons written inside templates (play or pause, a person, a note)."""
    import re

    for component_id, file_name in STEP_B.items():
        text = (LIBRARY / "components" / file_name).read_text("utf-8")
        for name in re.findall(r"mdi:[a-z0-9-]+", text):
            assert name in ICON_LEVEL, (component_id, name)


def _fit_cases() -> list[tuple[str, str, bool]]:
    """List (card, variant, can do everything) to lay out."""
    return [
        (component_id, name, everything)
        for component_id in STEP_B
        for name in COMPONENTS[component_id]["variants"]
        for everything in (True, False)
    ]


@pytest.mark.parametrize(("component_id", "variant", "everything"), _fit_cases())
def test_every_variant_fits_its_grid_with_every_option_on(
    component_id: str, variant: str, everything: bool
) -> None:
    """Nothing clipped, for a device that can do everything or nothing.

    Four devices for a param that takes several. A garage door's card tap
    is left out by the converter whatever the file says (C.2.8): that is the
    one warning a garage door may give.
    """
    component = COMPONENTS[component_id]
    params, entities = _param_values(component, 4)
    facts = {entity: _facts(entity.split(".", 1)[0], everything) for entity in entities}
    first = facts[entities[0]] if entities else {}
    allowed = ("tap_left_out",) if first.get("asks") else ()
    for options in _all_on(component, first):
        result = _compile(component, variant, params, options, facts)
        _inside(result, f"{component_id} {variant} {options}", allowed)


def test_an_alarm_without_a_code_fits_every_button() -> None:
    """Four arm buttons in a row on Wide and Large, then Disarm."""
    component = COMPONENTS["apollo/alarm"]
    facts = {"alarm_control_panel.a": facts_of(ALARM_RAW)}
    options = {"modes": ["home", "away", "night", "vacation"]}
    for variant in ("wide", "large"):
        result = _compile(
            component, variant, {"entity": "alarm_control_panel.a"}, options, facts
        )
        _inside(result, variant)
        texts = [w.get("text") for w in result["widgets"] if w["t"] == "button"]
        assert texts == ["Home", "Away", "Night", "Holiday", "Disarm"], variant
        assert not any("needs a code" in str(w.get("text")) for w in result["widgets"])


def test_the_lists_hold_eight_on_their_large_variants() -> None:
    """Eight readings on Large and eight people on Tall; Wide holds four."""
    for component_id, variant in (
        ("apollo/readings", "large"),
        ("apollo/people", "tall"),
        ("apollo/readings", "wide"),
        ("apollo/people", "wide"),
    ):
        component = COMPONENTS[component_id]
        count = 4 if variant == "wide" else 8
        params, entities = _param_values(component, count)
        facts = {e: _facts(e.split(".", 1)[0], True) for e in entities}
        result = _compile(component, variant, params, {"show_place": True}, facts)
        _inside(result, f"{component_id} {variant}")
        if variant != "wide":
            assert _kinds(result).count("image") == 8


def test_sixteen_lights_fit_the_group() -> None:
    """The group card takes up to 16 lights; none of it is a loop."""
    component = COMPONENTS["apollo/light-group"]
    params, entities = _param_values(component, 16)
    facts = {e: _facts("light", True) for e in entities}
    for variant in component["variants"]:
        _inside(_compile(component, variant, params, {}, facts), variant)


def test_the_climate_controls_page_holds_every_row() -> None:
    """Thermostat, modes, presets, fan modes and the line, for a full device."""
    component = COMPONENTS["apollo/climate"]
    facts = {"climate.a": facts_of(CLIMATE_RAW)}
    options = {"modes_shown": facts["climate.a"]["modes"][:6], "show_presets": True}
    result = _compile(component, "full", {"entity": "climate.a"}, options, facts)
    _inside(result, "full")
    # L2: the line under the dial, then each group of choices under its word.
    # LOOK-NOTES decision 14: under the tile header's badge, name and state.
    assert _kinds(result) == [
        "image",
        "label",
        "label",
        "thermostat",
        "label",
        "label",
        "choice",
        "label",
        "choice",
        "label",
        "choice",
    ]


def test_the_example_cards_need_no_device() -> None:
    """Each card compiles as an example (no device picked), with nothing clipped."""
    for component_id in STEP_B:
        component = COMPONENTS[component_id]
        for name, variant in component["variants"].items():
            columns, rows = variant["grid"]
            raw = {"variant": name, "grid_options": {"columns": columns, "rows": rows}}
            card = validate_card_config2(component, copy.deepcopy(raw))
            result = compile_card2(component, card, {}, 2, detail=not variant["picker"])
            _inside(result, f"{component_id} {name}")


# ---------------------------------------------------------------- version 1 forms

# A device per card for the version 1 forms; and one that the old card's own
# checks refuse, where the card names an old card.
V1_DEVICES = {
    "apollo/light-group": {"lights": ["light.kitchen", "light.hall"]},
    "apollo/climate": {"entity": "climate.living"},
    "apollo/fan-speed": {"entity": "fan.ceiling"},
    "apollo/cover": {"entity": "cover.living"},
    "apollo/door-lock": {"entity": "lock.front"},
    "apollo/alarm": {"entity": "alarm_control_panel.home"},
    "apollo/media": {"entity": "media_player.kitchen"},
    "apollo/volume": {"entity": "media_player.kitchen"},
    "apollo/dial": {"entity": "sensor.power", "max": 4000},
    "apollo/readings": {"entities": ["sensor.a", "binary_sensor.b"]},
    "apollo/room": {
        "page": "home",
        "temperature_sensor": "sensor.t",
        "lights": ["light.kitchen"],
    },
    "apollo/people": {"people": ["person.anna", "person.ben"]},
    "apollo/clock": {},
    "apollo/appliance": {
        "state": "sensor.washer",
        "remaining": "sensor.washer_left",
        "progress": "sensor.washer_done",
        "start_button": "button.washer_start",
        "power_switch": "switch.washer",
    },
}
REFUSED_BY_OLD_CARD = {
    "apollo/dial": {"entity": "number.limit", "max": 4000},
}
V1_FACTS = {
    "climate.living": facts_of(CLIMATE_RAW),
    "fan.ceiling": facts_of(FAN_RAW),
    "cover.living": facts_of(BLIND_RAW),
    "cover.garage": facts_of(GARAGE_RAW),
    "media_player.kitchen": facts_of(MEDIA_RAW),
    "alarm_control_panel.home": facts_of(ALARM_RAW),
    "lock.front": facts_of(LOCK_RAW),
}
# Variants whose version 1 form is an old card (C.6, rule 1).
OLD_CARD = {
    ("apollo/climate", "large"): "apollo/thermostat",
    ("apollo/fan-speed", "tile"): "apollo/fan",
    ("apollo/fan-speed", "wide"): "apollo/fan",
    ("apollo/fan-speed", "large"): "apollo/fan",
    ("apollo/cover", "tall"): "apollo/blinds",
    ("apollo/cover", "window"): "apollo/blinds",
    ("apollo/door-lock", "tile"): "apollo/lock",
    ("apollo/door-lock", "wide"): "apollo/lock",
    ("apollo/door-lock", "tall"): "apollo/lock",
    ("apollo/alarm", "large"): "apollo/alarm-panel",
    ("apollo/media", "wide"): "apollo/media-player",
    ("apollo/media", "large"): "apollo/media-player",
    ("apollo/media", "hero"): "apollo/media-player",
    ("apollo/dial", "tile"): "community/energy-gauge",
    ("apollo/dial", "large"): "community/energy-gauge",
    ("apollo/people", "wide"): "community/presence-chips",
}
# Cards, or variants, that show a value only: their version 1 form must show it.
SHOWS_ONLY = {
    ("apollo/dial", None),
    ("apollo/readings", None),
    ("apollo/people", None),
    ("apollo/clock", None),
    ("apollo/appliance", "tile"),
}


def _shows_only(component_id: str, variant: str) -> bool:
    """Return whether a card's variant shows a value and has no control."""
    return (component_id, None) in SHOWS_ONLY or (component_id, variant) in SHOWS_ONLY


def _v1_cases() -> list[tuple[str, str, dict]]:
    """List (card, variant, params), with the refused devices too."""
    cases = []
    for component_id, params in V1_DEVICES.items():
        for name, variant in COMPONENTS[component_id]["variants"].items():
            if not variant["picker"]:
                continue
            if (component_id, name) == ("apollo/cover", "door"):
                # Offered only for a garage door, a gate or a door.
                cases.append((component_id, name, {"entity": "cover.garage"}))
                continue
            cases.append((component_id, name, params))
            if component_id in REFUSED_BY_OLD_CARD:
                cases.append((component_id, name, REFUSED_BY_OLD_CARD[component_id]))
    return cases


def _v1_card(component_id: str, variant: str, params: dict) -> tuple[dict, dict]:
    """Return the one card of a layout v1 and the conversion."""
    columns, rows = COMPONENTS[component_id]["variants"][variant]["grid"]
    card = {
        "type": "custom:apollo-tab-card",
        "component": component_id,
        "params": params,
        "variant": variant,
        "grid_options": {"columns": columns, "rows": rows},
    }
    if params.get("entity") == "cover.garage":
        # A garage door's card tap is left out anyway (C.2.8); say so.
        card["options"] = {"tap": "none"}
    config = _dashboard(card)
    if columns > 12:
        config["views"][0]["sections"][0]["column_span"] = 2
    config["views"].append(
        {
            "type": "sections",
            "path": "other",
            "title": "Other",
            "max_columns": 3,
            "sections": [],
        }
    )
    result = _convert(config, V1_FACTS, 1)
    [built] = _cards(result["layout"])
    return built, result


@pytest.mark.parametrize(("component_id", "variant", "params"), _v1_cases())
def test_the_version_1_form_of_every_variant(
    component_id: str, variant: str, params: dict
) -> None:
    """A working control for the main action, or the value it shows (C.6, C.9).

    No version 1 form holds an icon above level 1, and its device layout
    holds no fallback code point.
    """
    built, result = _v1_card(component_id, variant, params)
    layout = result["layout"]
    assert layout["v"] == 1
    assert result["warnings"] == [], result["warnings"]
    refused = REFUSED_BY_OLD_CARD.get(component_id) == params
    old = OLD_CARD.get((component_id, variant))
    if old is not None and not refused:
        assert built["component"] == old
    else:
        assert built["component"] == component_id
    texts = [w.get("text") for w in built["w"]]
    assert UPDATE_NOTE not in texts
    if _shows_only(component_id, variant):
        assert any(
            w["t"] in ("label", "slider", "arc")
            and isinstance(w.get("text", w.get("value")), dict)
            for w in built["w"]
        ), built
    else:
        assert any("tap" in w or "change" in w for w in built["w"]), built
    for widget in built["w"]:
        for key in ("icon", "value"):
            value = widget.get(key)
            if isinstance(value, str) and value.startswith("mdi:"):
                assert value in LEVEL1, (component_id, variant, widget)
    # A live icon could name one above level 1 at any time: none in a form of
    # the card's own. An old card is the old card as it was (C.6, rule 1); the
    # player's artwork is a picture, a placeholder on these tablets.
    if built["component"] == component_id:
        assert not any(
            w["t"] == "image" and isinstance(w.get("value"), dict) for w in built["w"]
        )
    header_icon = (built.get("header") or {}).get("icon")
    assert header_icon is None or header_icon in LEVEL1
    compiled = device.compile_device_layout(layout, ICONS)
    fallback = ICONS["icons"][ICONS["fallback"]][0]
    assert chr(fallback).encode() not in compiled["bytes"]


def test_the_old_tablet_gets_the_two_buttons_for_a_garage() -> None:
    """Tile and Door: "Open" and "Close" on a tablet with older software."""
    for variant in ("tile", "door"):
        built, _result = _v1_card("apollo/cover", variant, {"entity": "cover.garage"})
        buttons = [w.get("text") for w in built["w"] if w["t"] == "button"]
        assert buttons == ["Open", "Close"], variant


# ---------------------------------------------------------------- what controls send


def _bindings(component_id: str, params: dict, facts: dict, **card: Any) -> dict:
    """Convert a dashboard with one card; return its actions by output."""
    entry = {
        "type": "custom:apollo-tab-card",
        "component": component_id,
        "params": params,
        "grid_options": {"columns": "full", "rows": 12},
        **card,
    }
    config = _dashboard(entry)
    config["views"].append(
        {
            "type": "sections",
            "path": "other",
            "title": "Other",
            "max_columns": 3,
            "sections": [],
        }
    )
    result = _convert(config, facts, 2)
    assert result["warnings"] == []
    # The card first, then its detail copy.
    widgets = {}
    for built in reversed(_cards(result["layout"])):
        widgets.update({w["id"]: w for w in built["w"]})
        widgets[built["id"]] = built
    found: dict = {}
    for key, action in result["bindings"]["actions"].items():
        wid, _, event = key.partition(":")
        widget = widgets[int(wid)]
        found.setdefault(action["output"], {**action, "widget": widget, "event": event})
    return found


async def _run(
    hass: HomeAssistant, action: dict, value: Any = None, *, confirmed: bool = False
) -> None:
    """Run one output from its binding, as a tablet's input would."""
    widget = action["widget"]
    await async_run_output(
        hass,
        component=COMPONENTS[action["component"]],
        action_ref=action,
        params=action["params"],
        entities=action["entities"],
        widget=widget if widget["t"] != "card" else {"t": "card"},
        event="change" if action["event"] == "change" else "tap",
        value=value,
        confirmed=confirmed,
        context=Context(),
    )


async def test_the_group_turns_all_on_and_off_and_dims_those_on(
    hass: HomeAssistant,
) -> None:
    """All on and all off name every light; the bar dims the lights that are on."""
    lights = ["light.a", "light.b", "light.c"]
    on = async_mock_service(hass, "light", "turn_on")
    off = async_mock_service(hass, "light", "turn_off")
    actions = _bindings("apollo/light-group", {"lights": lights}, {}, variant="large")
    hass.states.async_set("light.a", "on", {"brightness": 255})
    hass.states.async_set("light.b", "off")
    hass.states.async_set("light.c", "on", {"brightness": 51})
    await _run(hass, actions["all_off"])
    assert off[-1].data == {"entity_id": lights}
    await _run(hass, actions["set_pct"], 40)
    assert on[-1].data == {"entity_id": ["light.a", "light.c"], "brightness_pct": 40}
    hass.states.async_set("light.a", "off")
    hass.states.async_set("light.c", "off")
    await _run(hass, actions["all_on"])
    assert on[-1].data == {"entity_id": lights}
    # None on: the bar dims them all.
    await _run(hass, actions["set_pct"], 70)
    assert on[-1].data == {"entity_id": lights, "brightness_pct": 70}
    every = _bindings(
        "apollo/light-group",
        {"lights": lights},
        {},
        variant="large",
        options={"bar_sets": "all"},
    )
    hass.states.async_set("light.a", "on", {"brightness": 255})
    await _run(hass, every["set_pct"], 30)
    assert on[-1].data == {"entity_id": lights, "brightness_pct": 30}


async def test_what_the_thermostat_sends(hass: HomeAssistant) -> None:
    """Temperature, mode, preset and fan mode by the name at the index."""
    entity = "climate.living"
    facts = {entity: facts_of(CLIMATE_RAW)}
    actions = _bindings(
        "apollo/climate",
        {"entity": entity},
        facts,
        variant="large",
        options={"modes_shown": ["heat", "cool", "off"], "show_presets": True},
    )
    temperature = async_mock_service(hass, "climate", "set_temperature")
    mode = async_mock_service(hass, "climate", "set_hvac_mode")
    preset = async_mock_service(hass, "climate", "set_preset_mode")
    fan = async_mock_service(hass, "climate", "set_fan_mode")
    dial = actions["set_temperature"]["widget"]
    assert (dial["min"], dial["max"], dial["step"]) == (7, 35, 0.5)
    await _run(hass, actions["set_temperature"], 21.5)
    assert temperature[-1].data == {"entity_id": entity, "temperature": 21.5}
    assert actions["set_mode"]["widget"]["texts"] == ["heat", "cool", "off"]
    await _run(hass, actions["set_mode"], 1)
    assert mode[-1].data == {"entity_id": entity, "hvac_mode": "cool"}
    await _run(hass, actions["set_preset"], 3)
    assert preset[-1].data == {"entity_id": entity, "preset_mode": "comfort"}
    # The fan modes are on the controls page.
    await _run(hass, actions["set_fan_mode"], 2)
    assert fan[-1].data == {"entity_id": entity, "fan_mode": "medium"}


async def test_what_the_fan_sends(hass: HomeAssistant) -> None:
    """Toggle, speed, preset, and turning flips what HA says."""
    entity = "fan.ceiling"
    facts = {entity: facts_of(FAN_RAW)}
    actions = _bindings("apollo/fan-speed", {"entity": entity}, facts, variant="large")
    toggle = async_mock_service(hass, "fan", "toggle")
    pct = async_mock_service(hass, "fan", "set_percentage")
    preset = async_mock_service(hass, "fan", "set_preset_mode")
    oscillate = async_mock_service(hass, "fan", "oscillate")
    assert actions["toggle"]["widget"]["t"] == "card"
    await _run(hass, actions["toggle"])
    assert toggle[-1].data == {"entity_id": entity}
    assert actions["set_pct"]["widget"]["step"] == 25
    await _run(hass, actions["set_pct"], 75)
    assert pct[-1].data == {"entity_id": entity, "percentage": 75}
    await _run(hass, actions["set_preset"], 4)
    assert preset[-1].data == {"entity_id": entity, "preset_mode": "breeze"}
    hass.states.async_set(entity, "on", {"oscillating": False})
    await _run(hass, actions["oscillate"])
    assert oscillate[-1].data == {"entity_id": entity, "oscillating": True}
    hass.states.async_set(entity, "on", {"oscillating": True})
    await _run(hass, actions["oscillate"])
    assert oscillate[-1].data == {"entity_id": entity, "oscillating": False}


async def test_what_the_blind_sends(hass: HomeAssistant) -> None:
    """Up, stop, down, and the hanging bar sets 100 minus how far it is closed."""
    entity = "cover.living"
    facts = {entity: facts_of(BLIND_RAW)}
    actions = _bindings("apollo/cover", {"entity": entity}, facts, variant="tall")
    services = {
        name: async_mock_service(hass, "cover", name)
        for name in (
            "open_cover",
            "close_cover",
            "stop_cover",
            "toggle",
            "set_cover_position",
        )
    }
    assert actions["toggle"]["widget"]["t"] == "card"
    for output, service in (
        ("open", "open_cover"),
        ("close", "close_cover"),
        ("stop", "stop_cover"),
        ("toggle", "toggle"),
    ):
        await _run(hass, actions[output])
        assert services[service][-1].data == {"entity_id": entity}
    await _run(hass, actions["set_closed"], 30)
    assert services["set_cover_position"][-1].data == {
        "entity_id": entity,
        "position": 70,
    }
    grows = _bindings(
        "apollo/cover",
        {"entity": entity},
        facts,
        variant="tall",
        options={"turn_round": True},
    )
    assert "set_closed" not in grows
    await _run(hass, grows["set_position"], 30)
    assert services["set_cover_position"][-1].data == {
        "entity_id": entity,
        "position": 30,
    }


def test_a_garage_door_has_no_card_tap_and_its_own_variant() -> None:
    """The converter leaves the tap out for a garage; Door is offered only to it."""
    component = COMPONENTS["apollo/cover"]
    garage = {"cover.g": facts_of(GARAGE_RAW)}
    result = _compile(component, "door", {"entity": "cover.g"}, {}, garage)
    assert "tap" not in result
    assert result["warnings"] == ["tap_left_out"]
    buttons = [w for w in result["widgets"] if w["t"] == "button"]
    assert [b["text"] for b in buttons] == ["Close", "Open"]
    assert result["widgets"][0]["t"] == "image"
    # A blind stored as Door gets the first variant that holds for it.
    blind = {"cover.b": facts_of(BLIND_RAW)}
    stored = _compile(component, "door", {"entity": "cover.b"}, {}, blind)
    tile = _compile(component, "tile", {"entity": "cover.b"}, {}, blind)
    assert _kinds(stored) == _kinds(tile)
    assert stored["tap"] == {"policy": "progress"}
    # The example of Door (no device picked yet) is a door, for the picker.
    example = _compile(component, "door", {}, {}, {})
    assert example["demo"] is True
    assert [w.get("text") for w in example["widgets"] if w["t"] == "button"] == [
        "Close",
        "Open",
    ]


async def test_the_lock_asks_before_it_locks_or_unlocks(hass: HomeAssistant) -> None:
    """Both outputs ask first; the card itself has no tap."""
    entity = "lock.front"
    facts = {entity: facts_of(LOCK_RAW)}
    actions = _bindings("apollo/door-lock", {"entity": entity}, facts, variant="tile")
    lock = async_mock_service(hass, "lock", "lock")
    unlock = async_mock_service(hass, "lock", "unlock")
    assert set(actions) == {"lock", "unlock"}
    for output, calls in (("lock", lock), ("unlock", unlock)):
        button = actions[output]["widget"]
        assert button["t"] == "button" and button.get("confirm"), button
        await _run(hass, actions[output], confirmed=True)
        assert calls[-1].data == {"entity_id": entity}
    result = _compile(
        COMPONENTS["apollo/door-lock"], "tile", {"entity": entity}, {}, facts
    )
    assert "tap" not in result and "hold" not in result


async def test_the_alarm_asks_before_each_mode(hass: HomeAssistant) -> None:
    """Arm home, away, night, holiday and disarm; no card tap."""
    entity = "alarm_control_panel.home"
    facts = {entity: facts_of(ALARM_RAW)}
    actions = _bindings(
        "apollo/alarm",
        {"entity": entity},
        facts,
        variant="large",
        options={"modes": ["home", "away", "night", "vacation"]},
    )
    assert set(actions) == {
        "arm_home",
        "arm_away",
        "arm_night",
        "arm_vacation",
        "disarm",
    }
    for output, service in (
        ("arm_home", "alarm_arm_home"),
        ("arm_away", "alarm_arm_away"),
        ("arm_night", "alarm_arm_night"),
        ("arm_vacation", "alarm_arm_vacation"),
        ("disarm", "alarm_disarm"),
    ):
        calls = async_mock_service(hass, "alarm_control_panel", service)
        assert actions[output]["widget"].get("confirm"), output
        await _run(hass, actions[output], confirmed=True)
        assert calls[-1].data == {"entity_id": entity}


def test_an_alarm_that_needs_a_code_has_no_buttons() -> None:
    """The line "This alarm needs a code. Use Home Assistant." instead."""
    component = COMPONENTS["apollo/alarm"]
    facts = {"alarm_control_panel.a": facts_of(ALARM_CODE_RAW)}
    for variant in ("wide", "large"):
        result = _compile(
            component, variant, {"entity": "alarm_control_panel.a"}, {}, facts
        )
        assert "button" not in _kinds(result)
        assert any(
            w.get("text") == "This alarm needs a code. Use Home Assistant."
            for w in result["widgets"]
        )
        assert "tap" not in result
    old = _compile(
        component, "wide", {"entity": "alarm_control_panel.a"}, {}, facts, dl=1
    )
    assert "button" not in _kinds(old)


def test_the_alarm_shows_only_the_modes_it_has_and_the_person_picked() -> None:
    """A mode the alarm cannot do has no button, even when picked."""
    component = COMPONENTS["apollo/alarm"]
    raw = {
        "domain": "alarm_control_panel",
        "registry": {"features": ["ARM_AWAY"]},
    }
    facts = {"alarm_control_panel.a": facts_of(raw)}
    result = _compile(
        component,
        "wide",
        {"entity": "alarm_control_panel.a"},
        {"modes": ["home", "away", "night", "vacation"]},
        facts,
    )
    texts = [w.get("text") for w in result["widgets"] if w["t"] == "button"]
    assert texts == ["Away", "Disarm"]


async def test_what_the_player_sends(hass: HomeAssistant) -> None:
    """Play or pause, skips, volume, mute, source, shuffle and power."""
    entity = "media_player.kitchen"
    facts = {entity: facts_of(MEDIA_RAW)}
    actions = _bindings(
        "apollo/media",
        {"entity": entity},
        facts,
        variant="large",
        options={"sources_shown": ["Source 0", "Source 3"]},
    )
    services = {
        name: async_mock_service(hass, "media_player", name)
        for name in (
            "media_play_pause",
            "media_next_track",
            "media_previous_track",
            "volume_set",
            "volume_mute",
            "select_source",
            "shuffle_set",
            "toggle",
        )
    }
    assert actions["play_pause"]["widget"]["t"] == "card"
    for output, service in (
        ("play_pause", "media_play_pause"),
        ("next", "media_next_track"),
        ("previous", "media_previous_track"),
        ("power", "toggle"),
    ):
        await _run(hass, actions[output])
        assert services[service][-1].data == {"entity_id": entity}
    await _run(hass, actions["set_volume"], 40)
    assert services["volume_set"][-1].data == {"entity_id": entity, "volume_level": 0.4}
    hass.states.async_set(
        entity, "playing", {"is_volume_muted": False, "shuffle": True}
    )
    await _run(hass, actions["mute"])
    assert services["volume_mute"][-1].data == {
        "entity_id": entity,
        "is_volume_muted": True,
    }
    await _run(hass, actions["shuffle"])
    assert services["shuffle_set"][-1].data == {"entity_id": entity, "shuffle": False}
    await _run(hass, actions["pick_source"], 1)
    assert services["select_source"][-1].data == {
        "entity_id": entity,
        "source": "Source 3",
    }


async def test_what_the_volume_sends(hass: HomeAssistant) -> None:
    """The bar sets the level from 0 to 1; the button flips mute."""
    entity = "media_player.kitchen"
    actions = _bindings("apollo/volume", {"entity": entity}, {}, variant="row")
    volume = async_mock_service(hass, "media_player", "volume_set")
    mute = async_mock_service(hass, "media_player", "volume_mute")
    await _run(hass, actions["set_volume"], 64)
    assert volume[-1].data == {"entity_id": entity, "volume_level": 0.64}
    hass.states.async_set(entity, "on", {"is_volume_muted": True})
    await _run(hass, actions["mute"])
    assert mute[-1].data == {"entity_id": entity, "is_volume_muted": False}


async def test_what_the_room_sends(hass: HomeAssistant) -> None:
    """A tap goes to the room's page; the swap turns its lights on or off."""
    lights = ["light.a", "light.b"]
    params = {"page": "other", "lights": lights, "temperature_sensor": "sensor.t"}
    actions = _bindings("apollo/room", params, {}, variant="room")
    entry = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/room",
        "params": params,
        "variant": "room",
        "grid_options": {"columns": 9, "rows": 5},
    }
    config = _dashboard(entry)
    config["views"].append(
        {
            "type": "sections",
            "path": "other",
            "title": "Other",
            "max_columns": 3,
            "sections": [],
        }
    )
    [built] = _cards(_convert(config, {}, 2)["layout"])
    assert built["tap"] == {"local": "go_to_page", "page": "other"}
    on = async_mock_service(hass, "light", "turn_on")
    off = async_mock_service(hass, "light", "turn_off")
    await _run(hass, actions["lights_on"])
    assert on[-1].data == {"entity_id": lights}
    await _run(hass, actions["lights_off"])
    assert off[-1].data == {"entity_id": lights}


def test_a_room_without_a_page_has_no_tap() -> None:
    """The page is optional; without one nothing goes anywhere."""
    component = COMPONENTS["apollo/room"]
    result = _compile(component, "tile", {"temperature_sensor": "sensor.t"}, {}, {})
    assert "tap" not in result
    old = _compile(component, "room", {"temperature_sensor": "sensor.t"}, {}, {}, dl=1)
    assert not any(w.get("text") == "View room" for w in old["widgets"])


async def test_what_the_appliance_sends(hass: HomeAssistant) -> None:
    """Start and pause press a button or run a script; power toggles the switch."""
    params = {
        "state": "sensor.washer",
        "start_button": "button.start",
        "pause_button": "script.pause",
        "power_switch": "input_boolean.washer",
    }
    actions = _bindings("apollo/appliance", params, {}, variant="large")
    press = async_mock_service(hass, "button", "press")
    script = async_mock_service(hass, "script", "turn_on")
    toggle = async_mock_service(hass, "input_boolean", "toggle")
    await _run(hass, actions["start"])
    assert press[-1].data == {"entity_id": "button.start"}
    await _run(hass, actions["pause"])
    assert script[-1].data == {"entity_id": "script.pause"}
    await _run(hass, actions["toggle"])
    assert toggle[-1].data == {"entity_id": "input_boolean.washer"}


def test_the_appliance_shows_only_the_buttons_it_was_given() -> None:
    """A button per device the person picked, none for the others."""
    component = COMPONENTS["apollo/appliance"]
    result = _compile(
        component,
        "large",
        {"state": "sensor.washer", "start_button": "button.start"},
        {},
        {},
    )
    assert [w.get("text") for w in result["widgets"] if w["t"] == "button"] == ["Start"]
    paused = _compile(
        component,
        "large",
        {"state": "sensor.washer", "pause_button": "script.pause"},
        {},
        {},
    )
    assert [w.get("text") for w in paused["widgets"] if w["t"] == "button"] == ["Pause"]


def test_the_cards_that_only_show_have_no_outputs() -> None:
    """Gauge, list, people and clock show; they call nothing."""
    for component_id in (
        "apollo/dial",
        "apollo/readings",
        "apollo/people",
        "apollo/clock",
    ):
        assert COMPONENTS[component_id]["outputs"] == {}, component_id
        assert COMPONENTS[component_id]["tap"] is None


# ---------------------------------------------------------------- words and places


def test_the_words_of_the_fourteen_cards() -> None:
    """Every card has a name, a description and labels; each choice is labelled."""
    for component_id in STEP_B:
        component = COMPONENTS[component_id]
        assert component["name"] and component["description"], component_id
        for name, spec in component["params"].items():
            assert spec.get("label"), (component_id, name)
        for name, option in component["options"].items():
            assert option["label"], (component_id, name)
        for variant in component["variants"].values():
            assert variant["name"]
        if component["tap"] is not None:
            assert all(choice["label"] for choice in component["tap"]["choices"])


def test_the_fourteen_cards_replace_what_d5_says() -> None:
    """Each takes the place of today's card in the picker (D.5)."""
    replaces = {
        component_id: COMPONENTS[component_id]["replaces"]
        for component_id in STEP_B
        if COMPONENTS[component_id]["replaces"]
    }
    assert replaces == {
        "apollo/fan-speed": ["apollo/fan"],
        "apollo/cover": ["apollo/blinds"],
        "apollo/climate": ["apollo/thermostat"],
        "apollo/door-lock": ["apollo/lock"],
        "apollo/alarm": ["apollo/alarm-panel"],
        "apollo/media": ["apollo/media-player"],
        "apollo/dial": ["community/energy-gauge"],
        "apollo/people": ["community/presence-chips"],
        "apollo/room": ["community/room-summary"],
    }


def test_no_device_param_takes_the_name_of_a_fact() -> None:
    """The room's sensors and the appliance's buttons got names of their own."""
    for component_id in STEP_B:
        for name, spec in COMPONENTS[component_id]["params"].items():
            if spec["kind"] == "entity":
                assert name not in FACT_NAMES, (component_id, name)
    assert set(COMPONENTS["apollo/room"]["params"]) == {
        "page",
        "temperature_sensor",
        "humidity_sensor",
        "lights",
        "extra",
    }
    assert set(COMPONENTS["apollo/appliance"]["params"]) == {
        "state",
        "remaining",
        "progress",
        "power_switch",
        "start_button",
        "pause_button",
        "programme",
    }


def test_the_lock_and_the_alarm_ask_and_are_never_a_card_tap() -> None:
    """Every output of the lock and the alarm asks first (C.2.8)."""
    for component_id in ("apollo/door-lock", "apollo/alarm"):
        component = COMPONENTS[component_id]
        assert component["tap"] is None
        for output in component["outputs"].values():
            assert output["feedback"] == "confirm"
            assert output["sensitive"] is True


# ---------------------------------------------------------------- live values


async def test_the_group_counts_and_dims(hass: HomeAssistant) -> None:
    """The count "2 of 3 on", the mean brightness of those on; gone when all are.

    L2: Large says the count once, large, and no line under the name; the
    line is on the smaller sizes. All gone: a dash and no button.
    """
    component = COMPONENTS["apollo/light-group"]
    lights = ["light.a", "light.b", "light.c"]
    tile = _compile(component, "tile", {"lights": lights}, {}, {})
    result = _compile(component, "large", {"lights": lights}, {}, {})
    hass.states.async_set("light.a", "on", {"brightness": 255})
    hass.states.async_set("light.b", "off")
    hass.states.async_set("light.c", "on", {"brightness": 51})
    labels = [
        w
        for w in result["widgets"]
        if w["t"] == "label" and isinstance(w["text"], dict)
    ]
    texts = [await _value(hass, result, w["text"]) for w in labels]
    assert "2 of 3 on" not in texts
    assert 2 in texts and "of 3 lights on" in texts
    assert await _value(hass, tile, _label(tile, "s")["text"]) == "2 of 3 on"
    [bar] = [w for w in result["widgets"] if w["t"] == "slider"]
    assert await _value(hass, result, bar["value"]) == 60
    assert await _value(hass, result, result["on"]) is True
    assert await _value(hass, result, result["un"]) is False
    for light in lights:
        hass.states.async_set(light, "unavailable")
    assert await _value(hass, result, result["un"]) is True
    texts = [await _value(hass, result, w["text"]) for w in labels]
    assert "—" in texts and "of 3 lights on" not in texts
    buttons = [w for w in result["widgets"] if w["t"] == "button"]
    assert [await _value(hass, result, b["vis"]) for b in buttons] == [False, False]
    # LOOK-NOTES decision 17: lower case, as every card (was "Unavailable").
    assert await _value(hass, tile, _label(tile, "s")["text"]) == "unavailable"


async def test_the_fan_and_cover_state_lines(hass: HomeAssistant) -> None:
    """A fan with speeds says "On · 50%"; a blind part open says "Open 60%"."""
    fan = _compile(
        COMPONENTS["apollo/fan-speed"],
        "tile",
        {"entity": "fan.a"},
        {},
        {"fan.a": facts_of(FAN_RAW)},
    )
    hass.states.async_set("fan.a", "on", {"percentage": 50})
    # LOOK-NOTES decision 17: joined with " · " as the lights (was "on, 50%").
    assert await _value(hass, fan, _label(fan, "s")["text"]) == "on · 50%"
    plain = _compile(
        COMPONENTS["apollo/fan-speed"], "tile", {"entity": "fan.a"}, {}, {}
    )
    assert await _value(hass, plain, _label(plain, "s")["text"]) == "on"
    cover = _compile(
        COMPONENTS["apollo/cover"],
        "tall",
        {"entity": "cover.b"},
        {},
        {"cover.b": facts_of(BLIND_RAW)},
    )
    hass.states.async_set("cover.b", "open", {"current_position": 60})
    assert await _value(hass, cover, _label(cover, "s")["text"]) == "open 60%"
    assert await _value(hass, cover, cover["on"]) is True
    [bar] = [w for w in cover["widgets"] if w["t"] == "slider"]
    assert await _value(hass, cover, bar["value"]) == 40
    hass.states.async_set("cover.b", "closed", {"current_position": 0})
    assert await _value(hass, cover, _label(cover, "s")["text"]) == "closed"
    assert await _value(hass, cover, cover["on"]) is False


async def test_the_lock_tone_and_highlight(hass: HomeAssistant) -> None:
    """Good while locked, warn while unlocked, bad when jammed; lit while open."""
    component = COMPONENTS["apollo/door-lock"]
    result = _compile(component, "tile", {"entity": "lock.f"}, {}, {})
    assert result["lit"] == 2  # outline
    for state, tone, lit in (
        ("locked", "good", False),
        ("unlocked", "warn", True),
        ("jammed", "bad", True),
    ):
        hass.states.async_set("lock.f", state)
        assert await _value(hass, result, result["tint"]) == tone, state
        assert await _value(hass, result, result["on"]) is lit, state
    quiet = _compile(component, "tile", {"entity": "lock.f"}, {"highlight": False}, {})
    hass.states.async_set("lock.f", "unlocked")
    assert await _value(hass, quiet, quiet["on"]) is False


async def test_the_alarm_is_on_while_armed(hass: HomeAssistant) -> None:
    """Armed in any mode lights the card; triggered is bad."""
    component = COMPONENTS["apollo/alarm"]
    result = _compile(component, "wide", {"entity": "alarm_control_panel.h"}, {}, {})
    hass.states.async_set("alarm_control_panel.h", "disarmed")
    assert await _value(hass, result, result["on"]) is False
    hass.states.async_set("alarm_control_panel.h", "armed_night")
    assert await _value(hass, result, result["on"]) is True
    assert await _value(hass, result, result["tint"]) == "good"
    hass.states.async_set("alarm_control_panel.h", "triggered")
    assert await _value(hass, result, result["tint"]) == "bad"


async def test_the_player_texts(hass: HomeAssistant) -> None:
    """The artist under the name, the length as minutes and seconds, the volume."""
    entity = "media_player.k"
    result = _compile(
        COMPONENTS["apollo/media"],
        "large",
        {"entity": entity},
        {},
        {entity: facts_of(MEDIA_RAW)},
    )
    hass.states.async_set(
        entity,
        "playing",
        {
            "media_title": "Song",
            "media_artist": "Band",
            "media_duration": 305,
            "volume_level": 0.25,
        },
    )
    assert await _value(hass, result, _label(result, "s", 2)["text"]) == "5:05"
    assert await _value(hass, result, result["on"]) is True
    sliders = [w for w in result["widgets"] if w["t"] == "slider"]
    volume = next(w for w in sliders if "change" in w)
    assert await _value(hass, result, volume["value"]) == 25


async def test_the_gauge_colours_by_its_limits(hass: HomeAssistant) -> None:
    """Above high: the high colour; below low: the low colour; a limit of 0 is off."""
    component = COMPONENTS["apollo/dial"]
    options = {"low": 100, "high": 3000, "high_colour": "bad", "unit": "W"}
    result = _compile(
        component, "tile", {"entity": "sensor.p", "max": 4000}, options, {}
    )
    [gauge] = [w for w in result["widgets"] if w["t"] == "thermostat"]
    assert gauge["min"] == 0
    assert await _value(hass, result, gauge["max"]) == 4000
    assert "change" not in gauge
    for state, tone in (("3500", "bad"), ("50", "info"), ("1000", None)):
        hass.states.async_set("sensor.p", state)
        assert await _value(hass, result, result["tint"]) == tone, state
    # L2: the dial shows the number once; Tile has no line under it, Large
    # the unit and the range.
    # LOOK-NOTES decision 14: the tile header's name is the one label.
    assert [w["r"][1] for w in result["widgets"] if w["t"] == "label"] == [16]
    large = _compile(
        component, "large", {"entity": "sensor.p", "max": 4000}, options, {}
    )
    hass.states.async_set("sensor.p", "1840")
    assert await _value(hass, large, _label(large, "m", 1)["text"]) == "0 to 4000 W"
    unset = _compile(component, "tile", {"entity": "sensor.p"}, {}, {})
    hass.states.async_set("sensor.p", "99999")
    assert await _value(hass, unset, unset["tint"]) is None


async def test_the_list_shows_name_and_value(hass: HomeAssistant) -> None:
    """One line per device: its name, its value with the unit at the right."""
    component = COMPONENTS["apollo/readings"]
    result = _compile(
        component, "large", {"entities": ["sensor.a", "sensor.b"]}, {}, {}
    )
    hass.states.async_set(
        "sensor.a", "21.5", {"friendly_name": "Kitchen", "unit_of_measurement": "°C"}
    )
    hass.states.async_set("sensor.b", "on", {"friendly_name": "Door"})
    labels = [w for w in result["widgets"] if w["t"] == "label"]
    texts = [await _value(hass, result, w["text"]) for w in labels]
    assert texts[-4:] == ["Kitchen", "21.5 °C", "Door", "on"]
    old = _compile(component, "large", {"entities": ["sensor.a"]}, {}, {}, dl=1)
    [line] = [w for w in old["widgets"] if w["t"] == "label"][-1:]
    assert await _value(hass, old, line["text"]) == "Kitchen: 21.5 °C"


async def test_the_room_line_and_count(hass: HomeAssistant) -> None:
    """The temperature once, large; the header line "46% · 1 of 2 on".

    L2: the header said the temperature that the card then showed large,
    and named the temperature sensor, not the room.
    """
    component = COMPONENTS["apollo/room"]
    params = {
        "temperature_sensor": "sensor.t",
        "humidity_sensor": "sensor.h",
        "lights": ["light.a", "light.b"],
    }
    result = _compile(component, "room", params, {}, {})
    hass.states.async_set("sensor.t", "21.5", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.h", "46")
    hass.states.async_set("light.a", "on")
    hass.states.async_set("light.b", "off")
    labels = [w for w in result["widgets"] if w["t"] == "label"]
    texts = [await _value(hass, result, w["text"]) for w in labels]
    # L4 round 2: value, space, unit, as on the reading cards.
    assert texts.count("21.5 °C") == 1
    assert "46% · 1 of 2 on" in texts
    assert "Room" in texts
    assert await _value(hass, result, result["on"]) is True


async def test_the_clock_texts(hass: HomeAssistant) -> None:
    """The clock is the tablet's own; the old tablet gets the time as text."""
    component = COMPONENTS["apollo/clock"]
    result = _compile(component, "wide", {}, {}, {})
    clock = next(w for w in result["widgets"] if w["t"] == "label")
    twelve = _compile(component, "wide", {}, {"hours": "12"}, {})
    clock12 = next(w for w in twelve["widgets"] if w["t"] == "label")
    assert (clock["clk"], clock12["clk"]) == (1, 2)
    assert clock["px"] == 96
    [slot] = [s for s in result["slots"] if s["n"] == clock["value"]["s"]]
    assert slot["kind"] == "clock"
    date = next(w for w in result["widgets"] if w["t"] == "label" and "text" in w)
    assert len((await _value(hass, result, date["text"])).split()) == 3
    old = _compile(component, "wide", {}, {}, {}, dl=1)
    text = await _value(
        hass, old, next(w for w in old["widgets"] if w["t"] == "label")["text"]
    )
    assert len(text) == 5 and text[2] == ":"


async def test_the_appliance_time_left(hass: HomeAssistant) -> None:
    """The time left, "42 min", from the sensor; nothing without one."""
    component = COMPONENTS["apollo/appliance"]
    params = {
        "state": "sensor.w",
        "remaining": "sensor.left",
        "progress": "sensor.done",
    }
    # L2: Tile shows the time left under the name, with no room for the
    # bar; Large shows both.
    tile = _compile(component, "tile", params, {}, {})
    result = _compile(component, "large", params, {}, {})
    hass.states.async_set("sensor.w", "running")
    hass.states.async_set("sensor.left", "41.6")
    hass.states.async_set("sensor.done", "60")
    assert await _value(hass, tile, tile["widgets"][-1]["text"]) == "42 min"
    assert await _value(hass, result, result["widgets"][3]["text"]) == "42 min"
    assert await _value(hass, result, result["on"]) is True
    [bar] = [w for w in result["widgets"] if w["t"] == "slider"]
    assert "change" not in bar
    assert await _value(hass, result, bar["value"]) == 60
    hass.states.async_set("sensor.w", "off")
    assert await _value(hass, result, result["on"]) is False
