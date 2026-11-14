"""Tests for maker/features.py: what a device can do (cards spec C.2.4)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from custom_components.apollo_tab.maker import features
from custom_components.apollo_tab.maker.features import (
    ALL,
    card_facts,
    dashboard_facts,
    entities_of,
    facts_named,
    facts_of,
    project,
)
from custom_components.apollo_tab.maker.schema import validate_component

HERE = Path(__file__).parent
LIGHT = validate_component(
    yaml.safe_load((HERE / "cards2" / "light.yaml").read_text(encoding="utf-8"))
)


def _registry(caps: dict | None = None, feats: list | None = None, **meta) -> dict:
    """Return the registry part of a raw entity."""
    return {
        "capabilities": caps or {},
        "features": feats or [],
        "device_class": meta.get("device_class"),
        "icon": meta.get("icon"),
        "unit": meta.get("unit"),
    }


def _state(attributes: dict | None = None, feats: list | None = None) -> dict:
    """Return the state part of a raw entity."""
    return {"attributes": attributes or {}, "features": feats or []}


# What each domain's device that can do everything reports, as registry
# capabilities, state attributes and feature names, and the facts that
# follow. The state carries what the registry does not hold.
DOMAINS = {
    "light": (
        {
            "supported_color_modes": ["color_temp", "hs"],
            "min_color_temp_kelvin": 2200,
            "max_color_temp_kelvin": 6500,
            "effect_list": ["None", "Rainbow", "Fire"],
        },
        {},
        ["EFFECT", "TRANSITION"],
        {
            "brightness": True,
            "colour": True,
            "temperature": True,
            "effects": True,
            "min_kelvin": 2200,
            "max_kelvin": 6500,
            "effect_list": ["Rainbow", "Fire"],
        },
    ),
    "cover": (
        {},
        {"device_class": "garage"},
        ["OPEN", "CLOSE", "SET_POSITION", "STOP", "SET_TILT_POSITION"],
        {"position": True, "stop": True, "tilt": True, "asks": True},
    ),
    "climate": (
        {
            "hvac_modes": ["off", "heat", "cool"],
            "preset_modes": ["eco", "away"],
            "fan_modes": ["auto", "low"],
            "min_temp": 5,
            "max_temp": 30,
            "target_temp_step": 0.5,
        },
        {},
        ["TARGET_TEMPERATURE", "TARGET_TEMPERATURE_RANGE"],
        {
            "target": True,
            "range": True,
            "off": True,
            "modes": ["off", "heat", "cool"],
            "presets": ["eco", "away"],
            "fan_modes": ["auto", "low"],
            "min": 5,
            "max": 30,
            "step": 0.5,
        },
    ),
    "fan": (
        {"preset_modes": ["sleep"]},
        {"percentage_step": 33.33},
        ["SET_SPEED", "OSCILLATE", "DIRECTION", "PRESET_MODE"],
        {
            "speed": True,
            "oscillate": True,
            "direction": True,
            "presets": ["sleep"],
            "step": 33.33,
        },
    ),
    "media_player": (
        {"source_list": ["TV", "Radio"]},
        {},
        [
            "PAUSE",
            "PREVIOUS_TRACK",
            "NEXT_TRACK",
            "VOLUME_SET",
            "VOLUME_MUTE",
            "SEEK",
            "TURN_OFF",
            "SHUFFLE_SET",
            "REPEAT_SET",
            "GROUPING",
        ],
        {
            "pause": True,
            "previous": True,
            "next": True,
            "volume": True,
            "mute": True,
            "seek": True,
            "power": True,
            "shuffle": True,
            "repeat": True,
            "group": True,
            "sources": ["TV", "Radio"],
        },
    ),
    "alarm_control_panel": (
        {},
        {"code_format": "number"},
        ["ARM_HOME", "ARM_AWAY", "ARM_NIGHT", "ARM_VACATION"],
        {
            "home": True,
            "away": True,
            "night": True,
            "vacation": True,
            "needs_code": True,
        },
    ),
    "lock": ({}, {}, ["OPEN"], {"open": True}),
    "select": ({"options": ["a", "b"]}, {}, [], {"options": ["a", "b"]}),
    "input_select": ({}, {"options": ["x", "y"]}, [], {"options": ["x", "y"]}),
    "number": (
        {"min": 10, "max": 20, "step": 0.5},
        {"unit_of_measurement": "°C"},
        [],
        {"min": 10, "max": 20, "step": 0.5, "unit": "°C"},
    ),
    "input_number": (
        {},
        {"min": 1, "max": 9, "step": 2, "unit_of_measurement": "%"},
        [],
        {"min": 1, "max": 9, "step": 2, "unit": "%"},
    ),
    "vacuum": (
        {"fan_speed_list": ["quiet", "max"]},
        {},
        ["START", "PAUSE", "STOP", "RETURN_HOME", "LOCATE", "FAN_SPEED"],
        {
            "start": True,
            "pause": True,
            "stop": True,
            "dock": True,
            "locate": True,
            "fan_speeds": ["quiet", "max"],
        },
    ),
}

# What each domain gives when nothing is known of the device.
LEAST = {
    "light": {
        "brightness": False,
        "colour": False,
        "temperature": False,
        "effects": False,
        "min_kelvin": 2000,
        "max_kelvin": 6500,
        "effect_list": [],
    },
    "cover": {"position": False, "stop": False, "tilt": False, "asks": False},
    "climate": {
        "target": False,
        "range": False,
        "off": False,
        "modes": [],
        "presets": [],
        "fan_modes": [],
        "min": 7,
        "max": 35,
        "step": 0.5,
    },
    "fan": {
        "speed": False,
        "oscillate": False,
        "direction": False,
        "presets": [],
        "step": 1,
    },
    "media_player": {
        **dict.fromkeys(
            (
                "pause",
                "previous",
                "next",
                "volume",
                "mute",
                "seek",
                "power",
                "shuffle",
                "repeat",
                "group",
            ),
            False,
        ),
        "sources": [],
    },
    "alarm_control_panel": {
        "home": False,
        "away": False,
        "night": False,
        "vacation": False,
        "needs_code": False,
    },
    "lock": {"open": False},
    "select": {"options": []},
    "input_select": {"options": []},
    "number": {"min": 0, "max": 100, "step": 1, "unit": ""},
    "input_number": {"min": 0, "max": 100, "step": 1, "unit": ""},
    "vacuum": {
        "start": False,
        "pause": False,
        "stop": False,
        "dock": False,
        "locate": False,
        "fan_speeds": [],
    },
}


def _without_any(facts: dict) -> dict:
    """Return the facts of a domain's own row."""
    return {k: v for k, v in facts.items() if k not in features.ANY_FACTS}


def test_the_table_covers_every_domain_of_the_spec() -> None:
    """Every row of C.2.4 has a test row, and every fact of it is given."""
    assert set(DOMAINS) == set(features.FACTS) == set(LEAST)
    for domain, (bools, lists, numbers) in features.FACTS.items():
        names = {*bools, *lists, *numbers}
        assert set(DOMAINS[domain][3]) == names, domain
        assert set(LEAST[domain]) == names, domain


@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_facts_from_a_registry_entry_and_a_state(domain: str) -> None:
    """Registry capabilities and the state's attributes together give all."""
    caps, attrs, feats, expected = DOMAINS[domain]
    raw = {
        "domain": domain,
        "registry": _registry(caps, feats),
        "state": _state(attrs),
    }
    assert _without_any(facts_of(raw)) == expected


# Facts that the test devices above report only in their state.
STATE_ONLY = {
    "cover": {"asks"},
    "fan": {"step"},
    "alarm_control_panel": {"needs_code"},
    "number": {"unit"},
    "input_select": {"options"},
    "input_number": {"min", "max", "step", "unit"},
}


@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_facts_from_a_registry_entry_alone(domain: str) -> None:
    """The registry entry alone gives what it holds, the rest is the least."""
    caps, _attrs, feats, expected = DOMAINS[domain]
    facts = facts_of({"domain": domain, "registry": _registry(caps, feats)})
    state_only = STATE_ONLY.get(domain, set())
    assert _without_any(facts) == {
        name: LEAST[domain][name] if name in state_only else value
        for name, value in expected.items()
    }


@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_facts_from_a_state_alone(domain: str) -> None:
    """A device with no registry entry is read from its state."""
    caps, attrs, feats, expected = DOMAINS[domain]
    raw = {"domain": domain, "state": _state({**caps, **attrs}, feats)}
    assert _without_any(facts_of(raw)) == expected


@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_facts_from_neither(domain: str) -> None:
    """Nothing known gives the least: no extras, empty lists, the defaults."""
    assert _without_any(facts_of({"domain": domain})) == LEAST[domain]
    # A registry entry without capabilities, a device just added.
    assert (
        _without_any(facts_of({"domain": domain, "registry": _registry()}))
        == LEAST[domain]
    )


def test_the_registry_comes_before_the_state() -> None:
    """A value in both is taken from the registry entry."""
    raw = {
        "domain": "light",
        "registry": _registry(
            {"supported_color_modes": ["brightness"], "min_color_temp_kelvin": 2200},
            ["EFFECT"],
            device_class="registry_class",
            icon="mdi:lamp",
        ),
        "state": _state(
            {
                "supported_color_modes": ["hs"],
                "min_color_temp_kelvin": 2700,
                "max_color_temp_kelvin": 6000,
                "effect_list": ["Fire"],
                "device_class": "state_class",
                "icon": "mdi:floor-lamp",
            },
            [],
        ),
    }
    facts = facts_of(raw)
    assert facts["brightness"] is True
    assert facts["colour"] is False
    # The registry's low end with the state's high end.
    assert (facts["min_kelvin"], facts["max_kelvin"]) == (2200, 6000)
    assert facts["effects"] is True
    assert facts["kind"] == "registry_class"
    assert facts["icon"] == "mdi:lamp"
    # An empty registry feature list falls back to the state's.
    raw["registry"]["features"] = []
    raw["state"]["features"] = ["EFFECT"]
    assert facts_of(raw)["effects"] is True
    raw["state"]["features"] = []
    assert facts_of(raw)["effects"] is False


def test_the_15_kelvin_lamp() -> None:
    """The owner's light.h1401 reports 15 K; the pair becomes 2000 to 6500."""
    raw = {
        "domain": "light",
        "registry": _registry(
            {
                "supported_color_modes": ["color_temp", "hs"],
                "min_color_temp_kelvin": 15,
                "max_color_temp_kelvin": 6535,
            }
        ),
    }
    facts = facts_of(raw)
    assert (facts["min_kelvin"], facts["max_kelvin"]) == (2000, 6500)
    assert facts["temperature"] is True


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        (1500, 10000, (1500, 10000)),
        (1499, 6500, (2000, 6500)),
        (2700, 10001, (2000, 6500)),
        (6500, 2700, (2000, 6500)),
        (3000, 3000, (2000, 6500)),
        (None, 6500, (2000, 6500)),
        (True, 6500, (2000, 6500)),
        (float("nan"), 6500, (2000, 6500)),
        ("2700", 6500, (2000, 6500)),
        (2700.5, 6499.4, (2701, 6499)),
    ],
)
def test_kelvin_limits_are_cleaned(low: object, high: object, expected: tuple) -> None:
    """A limit outside 1500 to 10000, or not low below high, gives 2000 to 6500."""
    raw = {
        "domain": "light",
        "state": _state({"min_color_temp_kelvin": low, "max_color_temp_kelvin": high}),
    }
    facts = facts_of(raw)
    assert (facts["min_kelvin"], facts["max_kelvin"]) == expected


def test_a_list_of_100_effects_is_cut_to_64() -> None:
    """Lists keep the first 64 entries, in the device's order."""
    effects = [f"Effect {n}" for n in range(100)]
    raw = {"domain": "light", "state": _state({"effect_list": effects}, ["EFFECT"])}
    assert facts_of(raw)["effect_list"] == effects[:64]


def test_an_effect_of_60_bytes_stays_whole() -> None:
    """Only the text written into a choice is cut; the fact keeps the whole name."""
    long_name = "Sunrise over the lake, " + "x" * 37
    assert len(long_name.encode()) == 60
    too_long = "y" * 256
    border = "z" * 255
    raw = {
        "domain": "light",
        "state": _state({"effect_list": [long_name, too_long, border]}, ["EFFECT"]),
    }
    assert facts_of(raw)["effect_list"] == [long_name, border]


def test_no_effect_names_are_taken_out() -> None:
    """None, none and off mean no effect and are left out of effect_list."""
    raw = {
        "domain": "light",
        "state": _state({"effect_list": ["None", "none", "off", "Off"]}, ["EFFECT"]),
    }
    facts = facts_of(raw)
    assert facts["effect_list"] == ["Off"]
    raw["state"]["attributes"]["effect_list"] = ["None", "off"]
    facts = facts_of(raw)
    assert facts["effect_list"] == []
    # A light that has the feature but no effect to pick has no effects.
    assert facts["effects"] is False


def test_list_entries_are_data() -> None:
    """A template in a device's list is kept as that very text."""
    hostile = "{{ states('alarm_control_panel.home') }}"
    raw = {
        "domain": "light",
        "state": _state({"effect_list": [hostile, "{% for x in range(9) %}"]}),
    }
    assert facts_of(raw)["effect_list"] == [hostile, "{% for x in range(9) %}"]


def test_odd_list_entries_are_left_out() -> None:
    """Non-texts, empty texts and repeats are left out; no list gives []."""
    raw = {
        "domain": "select",
        "state": _state({"options": ["a", 1, None, "", "a", ["b"], "b"]}),
    }
    assert facts_of(raw)["options"] == ["a", "b"]
    raw["state"]["attributes"]["options"] = "abc"
    assert facts_of(raw)["options"] == []


@pytest.mark.parametrize(
    ("caps", "expected"),
    [
        ({"min": 5, "max": 1, "step": 1}, (0, 100, 1)),
        ({"min": 0, "max": 10, "step": 0}, (0, 10, 1)),
        ({"min": 0, "max": 10, "step": -2}, (0, 10, 1)),
        ({"min": float("inf"), "max": 10}, (0, 100, 1)),
        ({"min": 0.0, "max": 10.0, "step": 2.0}, (0, 10, 2)),
    ],
)
def test_numbers_are_cleaned(caps: dict, expected: tuple) -> None:
    """A range must be low below high and a step above 0."""
    facts = facts_of({"domain": "number", "registry": _registry(caps)})
    assert (facts["min"], facts["max"], facts["step"]) == expected
    assert all(type(v) is int for v in (facts["min"], facts["max"], facts["step"]))


def test_a_fan_step_above_100_is_the_default() -> None:
    """A fan's step is a share of 100."""
    facts = facts_of({"domain": "fan", "state": _state({"percentage_step": 250})})
    assert facts["step"] == 1


def test_light_colour_modes() -> None:
    """An on/off lamp, a dim-only lamp, a white lamp and a colour lamp."""

    def modes(*names: str) -> dict:
        return facts_of(
            {"domain": "light", "state": _state({"supported_color_modes": names})}
        )

    assert not modes("onoff")["brightness"]
    assert not modes("unknown")["brightness"]
    assert modes("brightness")["brightness"]
    assert not modes("brightness")["colour"]
    assert modes("color_temp")["temperature"]
    assert not modes("color_temp")["colour"]
    for mode in ("hs", "xy", "rgb", "rgbw", "rgbww"):
        assert modes(mode)["colour"], mode
        assert modes(mode)["brightness"], mode
    assert not modes("white")["colour"]


def test_climate_off_from_modes_or_feature() -> None:
    """A climate device can be turned off by mode or by its feature."""
    by_mode = facts_of({"domain": "climate", "state": _state({"hvac_modes": ["off"]})})
    by_feature = facts_of({"domain": "climate", "state": _state({}, ["TURN_OFF"])})
    assert by_mode["off"] and by_feature["off"]


@pytest.mark.parametrize("kind", ["garage", "gate", "door"])
def test_covers_that_ask(kind: str) -> None:
    """A garage door, a gate and a door ask before they move."""
    raw = {"domain": "cover", "registry": _registry(device_class=kind)}
    assert facts_of(raw)["asks"] is True
    raw["registry"]["device_class"] = "blind"
    assert facts_of(raw)["asks"] is False


def test_any_entity() -> None:
    """toggle, icon and kind for every domain."""
    switch = facts_of({"domain": "switch"})
    assert switch == {"toggle": True, "icon": "mdi:toggle-switch", "kind": None}
    sensor = facts_of(
        {"domain": "sensor", "state": _state({"device_class": "temperature"})}
    )
    assert sensor == {"toggle": False, "icon": "mdi:thermometer", "kind": "temperature"}
    assert facts_of({"domain": "lock"})["toggle"] is False
    assert facts_of({"domain": "cover"})["toggle"] is True
    assert facts_of({"domain": "light"})["icon"] == "mdi:lightbulb"
    assert facts_of({"domain": "nothing"}) == {
        "toggle": False,
        "icon": None,
        "kind": None,
    }
    # The entity's own icon first; a text that is no icon is not taken.
    own = facts_of({"domain": "light", "state": _state({"icon": "mdi:desk-lamp"})})
    assert own["icon"] == "mdi:desk-lamp"
    bad = facts_of({"domain": "light", "state": _state({"icon": "{{ 1 }}"})})
    assert bad["icon"] == "mdi:lightbulb"


def test_every_default_icon_is_in_the_contract_set() -> None:
    """The icons the facts fall back to are names of the contract's icon set."""
    import json

    icons = json.loads(
        (
            HERE.parent / "custom_components" / "apollo_tab" / "contract" / "icons.json"
        ).read_text()
    )["icons"]
    for icon in [
        *features._DEFAULT_ICONS.values(),
        *features._DEFAULT_CLASS_ICONS.values(),
    ]:
        assert icon in icons, icon


def test_odd_input_gives_the_least() -> None:
    """Shapes that are not mappings are read as nothing."""
    assert facts_of({"domain": 5}) == {"toggle": False, "icon": None, "kind": None}
    raw = {"domain": "light", "registry": "x", "state": ["y"]}
    assert _without_any(facts_of(raw)) == LEAST["light"]
    raw = {
        "domain": "light",
        "registry": {"capabilities": "x", "features": "EFFECT"},
        "state": {"attributes": 5},
    }
    assert _without_any(facts_of(raw)) == LEAST["light"]


# ---------------------------------------------------------------- cards

ROOM = {
    "schema": 2,
    "params": {
        "page": {"kind": "page", "optional": True},
        "temperature": {"kind": "entity", "multiple": False},
        "humidity": {"kind": "entity", "multiple": False, "optional": True},
        "lights": {"kind": "entity", "multiple": True},
        "extra": {"kind": "entity", "multiple": False, "optional": True},
    },
}


def test_the_light_card_names_its_facts() -> None:
    """The facts the light card of D.1 names, for its one device."""
    assert facts_named(LIGHT) == {
        "": frozenset(
            {
                "icon",
                "brightness",
                "colour",
                "temperature",
                "effects",
                "effect_list",
                "min_kelvin",
                "max_kelvin",
            }
        )
    }


def test_a_schema_1_card_names_no_fact() -> None:
    """Schema 1 cards do not read facts."""
    assert facts_named({"schema": 1, "params": {"entity": {"kind": "entity"}}}) == {}
    assert facts_named({"params": {}}) == {}


def test_facts_named_by_every_form() -> None:
    """when, needs, from, lookups, loops, param facts and templates."""
    card = {
        **ROOM,
        "options": {
            "a": {"needs": "can.brightness", "when": ["!can.lights.colour"]},
            "b": {"from": "can.humidity.options", "when": ["can.speed=low|high"]},
        },
        "variants": {
            "tile": {
                "layout": [
                    {"min": {"form": "lookup", "name": "can", "key": "min"}},
                    {"loop": {"kind": "fact", "name": "can.modes"}},
                    {"text": {"form": "lookup", "name": "light_can", "key": "kind"}},
                    {"when": ["can.extra"]},
                    {"label": "can.decoration"},
                ]
            }
        },
        # The editor's example facts are no names.
        "preview": {"can": {"zzz": True}, "x": "can.zzz"},
    }
    named = facts_named(card)
    assert named[""] == {"icon", "brightness", "speed", "min", "modes", "decoration"}
    assert named["lights"] == {"colour", "kind"}
    assert named["humidity"] == {"options"}
    assert named["extra"] == {ALL}
    assert "temperature" not in named


def test_a_template_that_reads_can_names_every_fact() -> None:
    """A template sees all of can, so every fact of every device counts."""
    card = {
        **ROOM,
        "inputs": {"x": "{{ can.lights | length }}"},
    }
    named = facts_named(card)
    assert all(named[p] == {ALL} | ({"icon"} if p == "" else set()) for p in named)
    assert set(named) == {"", "temperature", "humidity", "lights", "extra"}
    loop_card = {**ROOM, "inputs": {"x": "{{ light_can.brightness }}"}}
    assert ALL in facts_named(loop_card)["lights"]
    # Words in a plain text and a template without can name nothing.
    plain = {
        **ROOM,
        "notes": [{"text": "This light can not be dimmed"}],
        "inputs": {"x": "{{ cancel }}", "y": "{{ 'scan' }}"},
    }
    assert facts_named(plain) == {"": {"icon"}}


def test_card_facts_for_one_light() -> None:
    """The answer of card/facts for the light card and the owner's lamp (C.7)."""
    lamp = facts_of(
        {
            "domain": "light",
            "registry": _registry(
                {
                    "supported_color_modes": ["color_temp", "hs"],
                    "min_color_temp_kelvin": 15,
                    "max_color_temp_kelvin": 6535,
                }
            ),
        }
    )
    answer = card_facts(LIGHT, {"entity": "light.h1401"}, {"light.h1401": lamp})
    expected_top = {
        "brightness": True,
        "colour": True,
        "temperature": True,
        "effects": False,
        "min_kelvin": 2000,
        "max_kelvin": 6500,
        "effect_list": [],
        "icon": "mdi:lightbulb",
    }
    assert {k: answer["can"][k] for k in expected_top} == expected_top
    assert answer["can"]["entity"] == lamp
    assert answer["has"] == {"entity": True}


def test_card_facts_for_two_params_and_a_list() -> None:
    """The first entity param with a value is at the top; a list keeps its order."""
    facts = {
        "sensor.living_temp": facts_of(
            {"domain": "sensor", "state": _state({"device_class": "temperature"})}
        ),
        "light.a": facts_of(
            {"domain": "light", "state": _state({"supported_color_modes": ["hs"]})}
        ),
    }
    params = {
        "temperature": "sensor.living_temp",
        "lights": ["light.a", "light.b"],
    }
    answer = card_facts(ROOM, params, facts)
    can = answer["can"]
    assert (can["icon"], can["kind"], can["toggle"]) == (
        "mdi:thermometer",
        "temperature",
        False,
    )
    assert can["temperature"] == facts["sensor.living_temp"]
    assert [d["colour"] for d in can["lights"]] == [True, False]
    # A device nothing is known of gives the least of its domain.
    assert can["lights"][1] == facts_of({"domain": "light"})
    assert answer["has"] == {
        "page": False,
        "temperature": True,
        "humidity": False,
        "lights": True,
        "extra": False,
    }
    # With the temperature left out, the lights' first device is at the top.
    answer = card_facts(ROOM, {"lights": ["light.a"], "page": "home"}, facts)
    assert answer["can"]["colour"] is True
    assert answer["has"]["page"] is True
    assert answer["has"]["temperature"] is False


def test_card_facts_ignores_values_that_are_no_entity() -> None:
    """A param value that is no entity id gives no facts and no has."""
    answer = card_facts(ROOM, {"temperature": "{{ x }}", "lights": ["light.a", 5]}, {})
    # The top holds the first light's facts; its `temperature` is the
    # light's yes or no, not the facts of a temperature param.
    assert answer["can"]["temperature"] is False
    assert answer["has"]["temperature"] is False
    assert len(answer["can"]["lights"]) == 1
    assert card_facts(ROOM, None, {})["can"] == {}


# ---------------------------------------------------------------- dashboards


def _dashboard(*cards: dict) -> dict:
    """Return a sections dashboard with the cards in one section."""
    return {"views": [{"type": "sections", "sections": [{"cards": list(cards)}]}]}


def test_entities_of_a_dashboard() -> None:
    """Only schema 2 cards need facts; every one of their devices is listed."""
    components = {
        "apollo/light": LIGHT,
        "me/room": ROOM,
        "apollo/light-tile": {"schema": 1, "params": {"entity": {"kind": "entity"}}},
    }
    config = _dashboard(
        {
            "type": "custom:apollo-tab-card",
            "component": "apollo/light",
            "params": {"entity": "light.h1401"},
        },
        {
            "type": "custom:apollo-tab-el-me-room",
            "params": {"temperature": "sensor.t", "lights": ["light.a", "light.b"]},
        },
        {
            "type": "custom:apollo-tab-card",
            "component": "apollo/light-tile",
            "params": {"entity": "light.old"},
        },
        {"type": "custom:apollo-tab-card", "component": "apollo/gone"},
        {"type": "heading", "heading": "x"},
        "not a card",
    )
    config["views"].append(
        {"type": "masonry", "cards": [{"type": "custom:apollo-tab-el-me-room"}]}
    )
    assert entities_of(config, components) == [
        "light.a",
        "light.b",
        "light.h1401",
        "sensor.t",
    ]
    named = dashboard_facts(config, components)
    assert "brightness" in named["light.h1401"]
    # The room card names only the icon of its first device.
    assert named["sensor.t"] == {"icon"}
    assert named["light.a"] == frozenset()
    assert entities_of({"views": "x"}, components) == []
    assert entities_of(None, components) == []


def test_project() -> None:
    """Only the named facts are compared; ALL compares them all."""
    facts = {"a": 1, "b": 2}
    assert project(facts, {"a"}) == {"a": 1}
    assert project(facts, {ALL}) == facts
    assert project(facts, {"c"}) == {"c": None}
    assert project(None, {"a"}) == {}
