"""The nine cards of step A (cards spec D.1, D.2, C.9 "Every card"; package I9).

Every card is a built-in schema 2 file. Each variant must fit its grid with
nothing clipped for a device that can do everything and for one that can do
nothing, with every option on; every icon it names is in the contract's set;
its version 1 form per variant has a working control for its main action, or
is the note on purpose. The colour light of D.1 compiles to the picture of
D.1 for the owner's lamp, a lamp that only dims and a lamp that only turns on
and off. Each card's main controls send what D.1 and D.2 say.
"""

from __future__ import annotations

import copy
import itertools
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from homeassistant.core import Context, HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.apollo_tab.live import async_run_output
from custom_components.apollo_tab.maker import device
from custom_components.apollo_tab.maker.compile2 import (
    compile_card2,
    kelvin_track,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.const import UPDATE_NOTE
from custom_components.apollo_tab.maker.convert import convert_dashboard
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.schema import validate_component
from custom_components.apollo_tab.maker.schema2 import iter_items
from custom_components.apollo_tab.maker.templates import check_component_templates

HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parent / "custom_components" / "apollo_tab" / "library"
ICONS = json.loads((HERE / "contract" / "icons.json").read_text(encoding="utf-8"))
ICON_LEVEL = {name: level for name, (_code, level) in ICONS["icons"].items()}
LEVEL1 = frozenset(name for name, level in ICON_LEVEL.items() if level <= 1)
THEMES = {
    theme["id"]: {k: v for k, v in theme.items() if k != "id"}
    for theme in json.loads((LIBRARY / "themes.json").read_text(encoding="utf-8"))
}
D1_TEXT = (HERE / "cards2" / "light.yaml").read_text(encoding="utf-8")

STEP_A = {
    "apollo/light": "apollo-light.yaml",
    "apollo/switch": "apollo-switch.yaml",
    "apollo/button": "apollo-button.yaml",
    "apollo/scenes": "apollo-scenes.yaml",
    "apollo/reading": "apollo-reading.yaml",
    "apollo/number": "apollo-number.yaml",
    "apollo/select": "apollo-select.yaml",
    "apollo/screen": "apollo-screen.yaml",
    "apollo/page-link": "apollo-page-link.yaml",
}


def _load_library() -> dict[str, dict]:
    """Load every built-in file as the library does, marked built in."""
    components = {}
    for path in sorted((LIBRARY / "components").glob("*.yaml")):
        component = validate_component(yaml.safe_load(path.read_text("utf-8")))
        component["source"] = "builtin"
        components[component["id"]] = component
    return components


COMPONENTS = _load_library()


# ---------------------------------------------------------------- devices

# What the owner's lamp reports (light.h1401): colour modes color_temp, hs
# and xy, and a lowest white of 15 K. The highest is HA's usual 6535 K.
OWNER_LAMP_RAW = {
    "domain": "light",
    "registry": {
        "capabilities": {
            "supported_color_modes": ["color_temp", "hs", "xy"],
            "min_color_temp_kelvin": 15,
            "max_color_temp_kelvin": 6535,
        }
    },
}
DIM_LAMP_RAW = {
    "domain": "light",
    "registry": {"capabilities": {"supported_color_modes": ["brightness"]}},
}
ONOFF_LAMP_RAW = {
    "domain": "light",
    "registry": {"capabilities": {"supported_color_modes": ["onoff"]}},
}
EFFECTS = [f"Effect {n}" for n in range(12)]
# A device of each kind that can do everything its kind can.
EVERYTHING_RAW = {
    "light": {
        "domain": "light",
        "registry": {
            "capabilities": {
                "supported_color_modes": ["color_temp", "hs", "rgbww"],
                "min_color_temp_kelvin": 2200,
                "max_color_temp_kelvin": 6500,
                "effect_list": EFFECTS,
            },
            "features": ["EFFECT"],
        },
    },
    "select": {
        "domain": "select",
        "registry": {"capabilities": {"options": [f"Mode {n}" for n in range(20)]}},
    },
    "input_select": {
        "domain": "input_select",
        "state": {"attributes": {"options": [f"Mode {n}" for n in range(20)]}},
    },
    "number": {
        "domain": "number",
        "registry": {"capabilities": {"min": 5, "max": 30, "step": 0.5}},
    },
    "input_number": {
        "domain": "input_number",
        "state": {"attributes": {"min": 0, "max": 1000, "step": 10}},
    },
}


def _facts(domain: str, everything: bool) -> dict:
    """Return what a device of a kind can do: everything, or nothing."""
    if everything and domain in EVERYTHING_RAW:
        return facts_of(EVERYTHING_RAW[domain])
    return facts_of({"domain": domain})


def _param_values(component: dict, count: int) -> tuple[dict, list[str]]:
    """Give every param a device (count of them for a param with several)."""
    params: dict = {}
    entities: list[str] = []
    for name, spec in component["params"].items():
        if spec["kind"] == "page":
            params[name] = "other"
            continue
        if spec["kind"] != "entity":
            continue
        kinds = spec.get("domains") or ["sensor"]
        if spec.get("multiple"):
            ids = [f"{kinds[n % len(kinds)]}.{name}_{n}" for n in range(count)]
            params[name] = ids
            entities.extend(ids)
        else:
            params[name] = f"{kinds[0]}.{name}"
            entities.append(params[name])
    return params, entities


def _all_on(component: dict, facts: dict) -> list[dict]:
    """Return option sets with every option on: one set per choice value.

    Toggles are on, texts at their longest, numbers at their top, lists
    full; then each value of each single choice in turn.
    """
    base: dict = {}
    singles = []
    for name, option in component["options"].items():
        otype = option["type"]
        if otype == "toggle":
            base[name] = True
        elif otype == "text":
            base[name] = "W" * option["max"]
        elif otype == "number":
            base[name] = option["max"] if option["max"] is not None else 99
        elif otype == "colours":
            base[name] = ["#FF0000", "#00FF00", "#0000FF", "2700K", "6500K"][
                : option["max"]
            ] + ["#FFFFFF"] * max(0, option["max"] - 5)
        elif otype == "choice" and option["multiple"]:
            if option.get("from"):
                # The device's list, as many as the card shows by default.
                listed = facts.get(option["from"].split(".", 1)[1]) or []
                base[name] = list(listed[: option["default_first"]])
            else:
                base[name] = [c["value"] for c in option["choices"]][: option["max"]]
        elif otype == "choice" and "choices" in option:
            singles.append((name, [c["value"] for c in option["choices"]]))
        elif otype == "colour":
            base[name] = "accent"
    sets = [dict(base)]
    for name, values in singles:
        sets.extend({**base, name: value} for value in values)
    return sets


def _fit_cases() -> list[tuple[str, str, bool, int]]:
    """List (card, variant, can do everything, devices) to lay out."""
    cases = []
    for component_id in STEP_A:
        component = COMPONENTS[component_id]
        for name in component["variants"]:
            for everything in (True, False):
                cases.append((component_id, name, everything, 4))
    return cases


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


def _assert_inside(result: dict, label: str) -> None:
    """Every widget sits inside the card, within its padding."""
    assert result["warnings"] == [], label
    for widget in result["widgets"]:
        x, y, width, height = widget["r"]
        assert x >= 16 and y >= 8, (label, widget)
        assert x + width <= result["w"] - 16, (label, widget)
        assert y + height <= result["h"] - 16, (label, widget)
        assert width >= 1 and height >= 1, (label, widget)


# ---------------------------------------------------------------- the files


def test_the_nine_files_are_built_in_and_load() -> None:
    """Each of the nine cards loads, passes the template checks and is schema 2."""
    for component_id, file_name in STEP_A.items():
        path = LIBRARY / "components" / file_name
        component = validate_component(yaml.safe_load(path.read_text("utf-8")))
        check_component_templates(component)
        assert component["id"] == component_id
        assert component["schema"] == 2
        assert component["version"] == "2.0.0"


def test_the_shipped_light_is_the_light_of_d1() -> None:
    """apollo/light is the file of D.1, with its form note and two changes.

    `level` gives no text for a lamp that has no brightness, so the on/off
    lamp's tile shows "badge, name, state" as D.1 draws it, not "0%". The
    favourites are not on Wide: eight dots need two rows, which a wide card
    does not hold (the fit test decides, D: "a row that does not fit moves
    to the next larger variant").
    """
    shipped = yaml.safe_load(
        (LIBRARY / "components" / STEP_A["apollo/light"]).read_text("utf-8")
    )
    d1 = yaml.safe_load(D1_TEXT)
    assert shipped.pop("notes") == [
        {"text": "This light only turns on and off.", "when": ["!can.brightness"]}
    ]
    assert shipped["inputs"].pop("level") == (
        "{{ (pct ~ '%') if is_on and state_attr(entity, 'brightness') is not none"
        " else '' }}"
    )
    d1["inputs"].pop("level")
    wide = d1["variants"]["wide"]["layout"]
    assert wide.pop(2) == {"use": "dots", "when": ["can.colour", "colour_control=dots"]}
    assert shipped == d1


@pytest.mark.parametrize("component_id", list(STEP_A))
def test_every_icon_a_card_names_is_in_the_contracts_set(component_id: str) -> None:
    """The file's icon is of level 1; every constant icon of an item is in the set.

    A version 1 header falls back to the file's icon.
    """
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


@pytest.mark.parametrize(
    ("component_id", "variant", "everything", "count"), _fit_cases()
)
def test_every_variant_fits_its_grid_with_every_option_on(
    component_id: str, variant: str, everything: bool, count: int
) -> None:
    """Nothing clipped, for a device that can do everything or nothing."""
    component = COMPONENTS[component_id]
    params, entities = _param_values(component, count)
    facts = {entity: _facts(entity.split(".", 1)[0], everything) for entity in entities}
    first = facts[entities[0]] if entities else {}
    for options in _all_on(component, first):
        result = _compile(component, variant, params, options, facts)
        _assert_inside(result, f"{component_id} {variant} {options}")


@pytest.mark.parametrize("variant", ["wide", "large"])
def test_eight_scenes_fit_four_a_row(variant: str) -> None:
    """The most scenes a card takes, four a row on Wide and two on Large."""
    component = COMPONENTS["apollo/scenes"]
    params, entities = _param_values(component, 8)
    facts = {e: _facts(e.split(".", 1)[0], True) for e in entities}
    result = _compile(component, variant, params, {"per_row": "4"}, facts)
    _assert_inside(result, variant)
    assert sum(1 for w in result["widgets"] if w["t"] == "button") == 8
    if variant == "large":
        result = _compile(component, variant, params, {"per_row": "2"}, facts)
        _assert_inside(result, variant)


def test_a_dropdown_takes_eight_choices_wide_and_sixteen_large() -> None:
    """The choice gets as many rows as the 44 px rule needs (C.3)."""
    component = COMPONENTS["apollo/select"]
    facts = {"select.entity": _facts("select", True)}
    options = facts["select.entity"]["options"]
    params = {"entity": "select.entity"}
    wide = _compile(component, "wide", params, {"shown": options[:8]}, facts)
    _assert_inside(wide, "wide")
    large = _compile(component, "large", params, {"shown": options[:16]}, facts)
    _assert_inside(large, "large")
    [choice] = [w for w in large["widgets"] if w["t"] == "choice"]
    assert choice["texts"] == options[:16]
    assert choice["r"][3] >= 3 * 48


# ---------------------------------------------------------------- version 1 forms


def _dashboard(*cards: dict) -> dict:
    """Return a dashboard of one page with these cards."""
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


def _convert(config: dict, facts: dict, dl: int) -> dict:
    """Convert a dashboard with the whole built-in library."""
    return convert_dashboard(
        config,
        components=COMPONENTS,
        themes=THEMES,
        approved=set(),
        facts=facts,
        dl=dl,
        icons=ICONS,
    )


def _cards(layout: dict) -> list[dict]:
    """Return every card of a layout."""
    return [w for page in layout["pages"] for w in page["w"] if w["t"] == "card"]


# A device per card for the version 1 forms; and one that the old card's own
# checks refuse, where the card names an old card.
V1_DEVICES = {
    "apollo/light": {"entity": "light.h1401"},
    "apollo/switch": {"entity": "input_boolean.guest"},
    "apollo/button": {"entity": "script.night"},
    "apollo/scenes": {"scenes": ["scene.movie", "scene.dinner"]},
    "apollo/reading": {"entity": "sensor.temperature"},
    "apollo/number": {"entity": "input_number.target"},
    "apollo/select": {"entity": "select.mode"},
    "apollo/screen": {"entity": "light.backlight"},
    "apollo/page-link": {"page": "climate", "entity": "sensor.temperature"},
}
REFUSED_BY_OLD_CARD = {
    "apollo/scenes": {"scenes": ["scene.movie", "script.night"]},
    "apollo/reading": {"entity": "binary_sensor.door"},
}
V1_FACTS = {
    "light.h1401": facts_of(OWNER_LAMP_RAW),
    "light.backlight": facts_of(DIM_LAMP_RAW),
    "select.mode": facts_of(EVERYTHING_RAW["select"]),
    "input_number.target": facts_of(EVERYTHING_RAW["input_number"]),
}
# Variants whose version 1 form is the note on purpose: a card one grid row
# high has room for the title header only.
NOTE_ON_PURPOSE = {("apollo/button", "chip"), ("apollo/reading", "chip")}
# Variants whose version 1 form is an old card (C.6, rule 1).
OLD_CARD = {
    ("apollo/light", "tile"): "apollo/light-tile",
    ("apollo/light", "wide"): "apollo/light-slider",
    ("apollo/light", "large"): "apollo/light-slider",
    ("apollo/scenes", "wide"): "apollo/scene-row",
    ("apollo/scenes", "large"): "apollo/scene-row",
    ("apollo/reading", "tile"): "apollo/sensor-value",
    ("apollo/reading", "wide"): "apollo/sensor-value",
}
# Cards that show a value only: their version 1 form must show it.
SHOWS_ONLY = {"apollo/reading"}


def _v1_cases() -> list[tuple[str, str, dict]]:
    """List (card, variant, params), with the refused devices too."""
    cases = []
    for component_id, params in V1_DEVICES.items():
        for name, variant in COMPONENTS[component_id]["variants"].items():
            if not variant["picker"]:
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
    result = _convert(_dashboard(card), V1_FACTS, 1)
    [built] = _cards(result["layout"])
    return built, result


@pytest.mark.parametrize(("component_id", "variant", "params"), _v1_cases())
def test_the_version_1_form_of_every_variant(
    component_id: str, variant: str, params: dict
) -> None:
    """A working control for the main action, or the note on purpose (C.6, C.9).

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
    if (component_id, variant) in NOTE_ON_PURPOSE:
        assert texts == [UPDATE_NOTE]
        return
    assert UPDATE_NOTE not in texts
    if component_id in SHOWS_ONLY:
        assert any(
            w["t"] == "label" and isinstance(w.get("text"), dict) for w in built["w"]
        )
    else:
        assert any("tap" in w or "change" in w for w in built["w"]), built
    for widget in built["w"]:
        for key in ("icon", "value"):
            value = widget.get(key)
            if isinstance(value, str) and value.startswith("mdi:"):
                assert value in LEVEL1, (component_id, variant, widget)
    # A live icon could name one above level 1 at any time: none in a v1 form.
    assert not any(
        w["t"] == "image" and isinstance(w.get("value"), dict) for w in built["w"]
    )
    header_icon = (built.get("header") or {}).get("icon")
    assert header_icon is None or header_icon in LEVEL1
    compiled = device.compile_device_layout(layout, ICONS)
    fallback = ICONS["icons"][ICONS["fallback"]][0]
    assert chr(fallback).encode() not in compiled["bytes"]


# ---------------------------------------------------------------- the light of D.1


def _light_layout(raw_facts: dict, dl: int = 2, **card: Any) -> dict:
    """Convert a dashboard with the light card for one lamp."""
    entry = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/light",
        "params": {"entity": "light.h1401"},
        **card,
    }
    return _convert(_dashboard(entry), {"light.h1401": facts_of(raw_facts)}, dl)


def _light_card(raw_facts: dict, variant: str, columns: int, rows: int) -> dict:
    """Return the light's card on the page, and its detail copy if any."""
    result = _light_layout(
        raw_facts, variant=variant, grid_options={"columns": columns, "rows": rows}
    )
    assert result["warnings"] == []
    return result


def _shape(widget: dict) -> tuple:
    """Return what tells a part of D.1's picture from another."""
    kind = widget["t"]
    if kind == "slider":
        if "track" in widget:
            track = "hue" if len(widget["track"]) == 7 else "kelvin"
        else:
            track = "bar" if "change" in widget else "level"
        return ("slider", track)
    if kind == "image":
        return ("badge",) if widget.get("look") == 1 else ("image",)
    if kind == "label":
        return ("label", widget.get("size"), widget.get("al", 0))
    return (kind,)


def test_the_owners_lamp_reports_15_k_and_gets_2000_to_6500() -> None:
    """The cleaning rule of C.2.4 for light.h1401."""
    facts = facts_of(OWNER_LAMP_RAW)
    assert facts["brightness"] is True
    assert facts["colour"] is True
    assert facts["temperature"] is True
    assert facts["effects"] is False
    assert (facts["min_kelvin"], facts["max_kelvin"]) == (2000, 6500)


def test_the_owners_lamp_tile() -> None:
    """Badge with the lamp's colour, name, state, "68%" at the top right, the bar.

    The card is lit with the fill look and tinted; a tap toggles at once; a
    hold opens the controls.
    """
    result = _light_card(OWNER_LAMP_RAW, "tile", 6, 3)
    [card, detail] = _cards(result["layout"])
    shapes = [_shape(w) for w in card["w"]]
    assert shapes == [
        ("badge",),
        ("label", "m", 0),
        ("label", "s", 0),
        ("label", "s", 2),
        ("slider", "bar"),
    ]
    badge, _name, _state, level, bar = card["w"]
    assert card["tint"] == badge["c"] == bar["c"]
    assert card["lit"] == 0
    assert card["tap"] == {"policy": "optimistic"}
    assert card["hold"] == {"local": "go_to_page", "page": "home~1"}
    assert (bar["min"], bar["max"], bar["icon"]) == (1, 100, "mdi:brightness-6")
    assert bar["change"] == {"policy": "optimistic"}
    assert level["r"][0] + level["r"][2] == card["r"][0] + card["r"][2] - 16
    actions = result["bindings"]["actions"]
    assert actions[str(card["id"]) + ":tap"]["output"] == "toggle"
    assert actions[str(bar["id"]) + ":change"]["output"] == "set_brightness"
    page = result["layout"]["pages"][1]
    assert page["id"] == "home~1" and page["sub"] == 1 and page["ttl"] == 60
    assert "tap" not in detail and "hold" not in detail


def test_the_owners_lamp_wide_large_and_controls() -> None:
    """Wide: header with switch, bar, colour bar. Large: bar, colour, warm to cool.

    Controls: the same rows larger; no effects for a lamp that has none.
    """
    wide = _cards(_light_card(OWNER_LAMP_RAW, "wide", 12, 3)["layout"])[0]
    head = [("badge",), ("label", "m", 0), ("label", "s", 0), ("switch",)]
    assert [_shape(w) for w in wide["w"]] == [
        *head,
        ("slider", "bar"),
        ("slider", "hue"),
    ]
    hue = wide["w"][5]
    assert hue["track"] == [
        "#FF0000",
        "#FFFF00",
        "#00FF00",
        "#00FFFF",
        "#0000FF",
        "#FF00FF",
        "#FF0000",
    ]
    assert (hue["min"], hue["max"], hue["nv"]) == (0, 360, 1)
    large_result = _light_card(OWNER_LAMP_RAW, "large", 12, 6)
    large, detail = _cards(large_result["layout"])
    assert [_shape(w) for w in large["w"]] == [
        *head,
        ("slider", "bar"),
        ("slider", "hue"),
        ("slider", "kelvin"),
    ]
    white = large["w"][6]
    assert (white["min"], white["max"], white["step"]) == (2000, 6500, 50)
    assert white["track"] == kelvin_track(2000, 6500)
    assert white["nv"] == 1
    assert [_shape(w) for w in detail["w"]] == [
        *head,
        ("slider", "bar"),
        ("slider", "hue"),
        ("slider", "kelvin"),
    ]
    assert [w["r"][3] for w in detail["w"][4:]] == [56, 48, 48]
    assert detail["r"][2:] == [568, 696]


def test_the_owners_lamp_with_every_colour_control() -> None:
    """Large with both colour controls, the strength bar and the favourites."""
    result = _light_layout(
        OWNER_LAMP_RAW,
        variant="large",
        grid_options={"columns": 12, "rows": 6},
        options={"colour_control": "both", "show_saturation": True},
    )
    assert result["warnings"] == []
    large = _cards(result["layout"])[0]
    assert [_shape(w) for w in large["w"]][4:] == [
        ("slider", "bar"),
        ("slider", "hue"),
        ("slider", "bar"),
        ("slider", "kelvin"),
        ("choice",),
    ]
    dots = large["w"][8]
    assert dots["look"] == 1
    assert len(dots["cols"]) == 8


def test_a_lamp_that_only_dims() -> None:
    """Tile, Wide and Large have the bar and nothing for colour or white."""
    for variant, columns, rows in (("tile", 6, 3), ("wide", 12, 3), ("large", 12, 6)):
        card = _cards(_light_card(DIM_LAMP_RAW, variant, columns, rows)["layout"])[0]
        sliders = [_shape(w) for w in card["w"] if w["t"] == "slider"]
        assert sliders == [("slider", "bar")], variant
        assert not any(w["t"] == "choice" for w in card["w"])


def test_a_lamp_that_only_turns_on_and_off() -> None:
    """Tile: badge, name, state. Wide: header with switch. No bar anywhere."""
    tile = _cards(_light_card(ONOFF_LAMP_RAW, "tile", 6, 3)["layout"])[0]
    assert [_shape(w) for w in tile["w"]] == [
        ("badge",),
        ("label", "m", 0),
        ("label", "s", 0),
        ("label", "s", 2),
    ]
    assert tile["tap"] == {"policy": "optimistic"}
    wide = _cards(_light_card(ONOFF_LAMP_RAW, "wide", 12, 3)["layout"])[0]
    assert [_shape(w) for w in wide["w"]] == [
        ("badge",),
        ("label", "m", 0),
        ("label", "s", 0),
        ("switch",),
    ]
    assert wide["w"][3]["tap"] == {"policy": "optimistic"}


def test_the_form_note_of_an_on_off_lamp() -> None:
    """The note of C.7 is the light's own and holds only for an on/off lamp."""
    from custom_components.apollo_tab.maker.when import when_holds

    [note] = COMPONENTS["apollo/light"]["notes"]
    assert note["text"] == "This light only turns on and off."
    names = {"can.brightness": facts_of(ONOFF_LAMP_RAW)["brightness"]}
    assert when_holds(note["when"], names) is True
    names = {"can.brightness": facts_of(DIM_LAMP_RAW)["brightness"]}
    assert when_holds(note["when"], names) is False


def test_the_light_on_an_old_tablet() -> None:
    """Tile is apollo/light-tile, Wide and Large apollo/light-slider; no colour."""
    for variant, columns, rows, old in (
        ("tile", 6, 3, "apollo/light-tile"),
        ("wide", 12, 3, "apollo/light-slider"),
        ("large", 12, 6, "apollo/light-slider"),
    ):
        result = _light_layout(
            OWNER_LAMP_RAW,
            1,
            variant=variant,
            grid_options={"columns": columns, "rows": rows},
            title="Sofa lamp",
        )
        [card] = _cards(result["layout"])
        assert card["component"] == old
        assert card["header"]["title"] == "Sofa lamp"
        assert result["simpler"] == 1


# ---------------------------------------------------------------- what controls send


def _bindings(component_id: str, params: dict, facts: dict, **card: Any) -> dict:
    """Convert a dashboard with one card; return its actions, the card's tap first."""
    entry = {
        "type": "custom:apollo-tab-card",
        "component": component_id,
        "params": params,
        "grid_options": {"columns": "full", "rows": 12},
        **card,
    }
    result = _convert(_dashboard(entry), facts, 2)
    assert result["warnings"] == []
    # The card first, then its detail copy.
    widgets = {}
    for card in reversed(_cards(result["layout"])):
        widgets.update({w["id"]: w for w in card["w"]})
        widgets[card["id"]] = card
    found: dict = {}
    for key, action in result["bindings"]["actions"].items():
        wid, _, event = key.partition(":")
        widget = widgets[int(wid)]
        found.setdefault(action["output"], {**action, "widget": widget, "event": event})
    return found


async def _run(hass: HomeAssistant, action: dict, value: Any = None) -> None:
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
        confirmed=False,
        context=Context(),
    )


async def test_what_the_lights_controls_send(hass: HomeAssistant) -> None:
    """The table "What each control sends" of D.1."""
    lamp = "light.h1401"
    facts = {lamp: facts_of(OWNER_LAMP_RAW)}
    facts[lamp]["effects"] = True
    facts[lamp]["effect_list"] = ["Rainbow", "{{ 1/0 }}"]
    actions = _bindings(
        "apollo/light",
        {"entity": lamp},
        facts,
        variant="large",
        options={
            "colour_control": "both",
            "show_saturation": True,
            "effects_shown": ["Rainbow", "{{ 1/0 }}"],
        },
    )
    toggle = async_mock_service(hass, "light", "toggle")
    turn_on = async_mock_service(hass, "light", "turn_on")
    hass.states.async_set(lamp, "on", {"hs_color": [30, 58], "brightness": 128})
    await _run(hass, actions["toggle"])
    assert toggle[-1].data == {"entity_id": lamp}
    await _run(hass, actions["set_brightness"], 40)
    assert turn_on[-1].data == {"entity_id": lamp, "brightness_pct": 40}
    await _run(hass, actions["set_hue"], 200)
    assert turn_on[-1].data == {"entity_id": lamp, "hs_color": [200, 58]}
    hass.states.async_set(lamp, "on", {"hs_color": [30, 4]})
    await _run(hass, actions["set_hue"], 200)
    assert turn_on[-1].data == {"entity_id": lamp, "hs_color": [200, 100]}
    hass.states.async_set(lamp, "on", {"hs_color": [210, 4]})
    await _run(hass, actions["set_sat"], 70)
    assert turn_on[-1].data == {"entity_id": lamp, "hs_color": [210, 70]}
    await _run(hass, actions["set_white"], 2750)
    assert turn_on[-1].data == {"entity_id": lamp, "color_temp_kelvin": 2750}
    await _run(hass, actions["set_favourite"], 0)
    assert turn_on[-1].data == {"entity_id": lamp, "rgb_color": [255, 69, 58]}
    await _run(hass, actions["set_favourite"], 7)
    assert turn_on[-1].data == {"entity_id": lamp, "color_temp_kelvin": 2700}
    effects = actions["set_effect"]
    assert effects["widget"]["texts"] == ["Rainbow", "{{ 1/0 }}"]
    await _run(hass, effects, 1)
    assert turn_on[-1].data == {"entity_id": lamp, "effect": "{{ 1/0 }}"}


async def test_the_switch_toggles_each_kind(hass: HomeAssistant) -> None:
    """One output, a service per kind (D.2 apollo/switch)."""
    for domain in ("switch", "input_boolean", "siren", "fan", "light"):
        entity = f"{domain}.thing"
        calls = async_mock_service(hass, domain, "toggle")
        actions = _bindings("apollo/switch", {"entity": entity}, {}, variant="tile")
        assert actions["toggle"]["widget"]["t"] == "card"
        await _run(hass, actions["toggle"])
        assert calls[-1].data == {"entity_id": entity}


def test_the_switch_words_are_data() -> None:
    """The words of the state line reach the template as variables only."""
    component = COMPONENTS["apollo/switch"]
    result = _compile(
        component,
        "tile",
        {"entity": "switch.kettle"},
        {"word_on": "{{ 1/0 }}", "word_off": "Idle"},
        {},
    )
    templates = [s["template"] for s in result["slots"] if s.get("kind") == "template"]
    assert all("1/0" not in template for template in templates)
    variables = [s["variables"] for s in result["slots"] if s.get("kind") == "template"]
    assert any(v.get("word_on") == "{{ 1/0 }}" for v in variables)


async def test_the_button_presses_each_kind(hass: HomeAssistant) -> None:
    """button.press, input_button.press, script.turn_on, scene.turn_on, as a pulse."""
    for domain, service in (
        ("button", "press"),
        ("input_button", "press"),
        ("script", "turn_on"),
        ("scene", "turn_on"),
    ):
        entity = f"{domain}.thing"
        calls = async_mock_service(hass, domain, service)
        actions = _bindings("apollo/button", {"entity": entity}, {}, variant="tile")
        press = actions["press"]
        assert press["widget"]["t"] == "card"
        assert press["widget"]["tap"] == {"policy": "pulse"}
        await _run(hass, press)
        assert calls[-1].data == {"entity_id": entity}


def test_a_scene_button_is_not_faded_while_its_state_is_unknown() -> None:
    """Scenes and buttons are "unknown" until first used; that is not gone."""
    for component_id, params in (
        ("apollo/button", {"entity": "scene.movie"}),
        ("apollo/scenes", {"scenes": ["scene.movie"]}),
    ):
        result = _compile(
            COMPONENTS[component_id],
            list(COMPONENTS[component_id]["variants"])[-1],
            params,
            {},
            {},
        )
        un = result["un"]
        [slot] = [s for s in result["slots"] if s["n"] == un["s"]]
        assert "unavailable" in slot["template"]
        assert "unknown" not in slot["template"]


async def test_each_scene_runs_its_own_device(hass: HomeAssistant) -> None:
    """One button per scene or script; each runs the one it shows."""
    scene = async_mock_service(hass, "scene", "turn_on")
    script = async_mock_service(hass, "script", "turn_on")
    entry = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/scenes",
        "params": {"scenes": ["scene.movie", "script.night", "scene.dinner"]},
        "grid_options": {"columns": 12, "rows": 3},
    }
    result = _convert(_dashboard(entry), {}, 2)
    built = _cards(result["layout"])[0]
    buttons = [w for w in built["w"] if w["t"] == "button"]
    assert len(buttons) == 3
    assert [b["icon"] for b in buttons] == [
        "mdi:palette",
        "mdi:script-text-outline",
        "mdi:palette",
    ]
    for button, (calls, entity) in zip(
        buttons,
        [(scene, "scene.movie"), (script, "script.night"), (scene, "scene.dinner")],
        strict=True,
    ):
        action = {
            **result["bindings"]["actions"][f"{button['id']}:tap"],
            "widget": button,
            "event": "tap",
        }
        await _run(hass, action)
        assert calls[-1].data == {"entity_id": entity}


def test_the_reading_shows_its_value_and_highlights_by_its_marks() -> None:
    """The reading is the state line; `on` and the tint follow the highlight."""
    component = COMPONENTS["apollo/reading"]
    result = _compile(
        component,
        "wide",
        {"entity": "sensor.co2"},
        {"highlight": "above", "high": 1000, "high_colour": "bad"},
        {},
    )
    on = next(s for s in result["slots"] if s["n"] == result["on"]["s"])
    assert "highlight" in on["template"]
    assert on["variables"]["highlight"] == "above"
    assert on["variables"]["high"] == 1000
    tint = result["tint"]
    assert tint["roles"]["bad"] == result["tint"]["roles"]["bad"]
    assert result["lit"] == 1  # icon


def test_the_reading_tap_toggles_only_a_device_that_can() -> None:
    """Tap "Turns it on or off" needs can.toggle; a sensor has none."""
    component = COMPONENTS["apollo/reading"]
    switch = _compile(
        component,
        "tile",
        {"entity": "switch.kettle"},
        {},
        {"switch.kettle": facts_of({"domain": "switch"})},
    )
    assert "tap" not in switch
    raw = {
        "params": {"entity": "switch.kettle"},
        "options": {"tap": "toggle"},
        "variant": "tile",
        "grid_options": {"columns": 6, "rows": 3},
    }
    card = validate_card_config2(component, raw)
    tapped = compile_card2(
        component, card, {"switch.kettle": facts_of({"domain": "switch"})}
    )
    assert tapped["tap"] == {"policy": "optimistic"}
    raw["params"] = {"entity": "sensor.temperature"}
    card = validate_card_config2(component, raw)
    sensor = compile_card2(
        component, card, {"sensor.temperature": facts_of({"domain": "sensor"})}
    )
    assert "tap" not in sensor


async def test_the_number_sets_and_steps(hass: HomeAssistant) -> None:
    """The bar sends its value; minus and plus step from HA's value, within limits."""
    entity = "number.target"
    facts = {entity: facts_of(EVERYTHING_RAW["number"])}
    calls = async_mock_service(hass, "number", "set_value")
    actions = _bindings("apollo/number", {"entity": entity}, facts, variant="wide")
    bar = actions["set"]["widget"]
    assert (bar["min"], bar["max"], bar["step"]) == (5, 30, 0.5)
    await _run(hass, actions["set"], 21.5)
    assert calls[-1].data == {"entity_id": entity, "value": 21.5}
    buttons = _bindings(
        "apollo/number",
        {"entity": entity},
        facts,
        variant="wide",
        options={"control": "buttons"},
    )
    hass.states.async_set(entity, "20")
    await _run(hass, buttons["down"])
    assert calls[-1].data == {"entity_id": entity, "value": 19.5}
    await _run(hass, buttons["up"])
    assert calls[-1].data == {"entity_id": entity, "value": 20.5}
    hass.states.async_set(entity, "30")
    await _run(hass, buttons["up"])
    assert calls[-1].data == {"entity_id": entity, "value": 30}
    hass.states.async_set(entity, "5")
    await _run(hass, buttons["down"])
    assert calls[-1].data == {"entity_id": entity, "value": 5}


async def test_the_dropdown_sends_the_name_at_the_index(hass: HomeAssistant) -> None:
    """`option` is the whole name from the server's list, sent as text."""
    entity = "select.mode"
    facts = {
        entity: facts_of(
            {
                "domain": "select",
                "state": {"attributes": {"options": ["None", "12", "[1, 2]", "Eco"]}},
            }
        )
    }
    calls = async_mock_service(hass, "select", "select_option")
    actions = _bindings("apollo/select", {"entity": entity}, facts, variant="large")
    choice = actions["pick"]["widget"]
    assert choice["t"] == "choice"
    assert choice["texts"] == ["None", "12", "[1, 2]", "Eco"]
    for index, name in enumerate(["None", "12", "[1, 2]", "Eco"]):
        await _run(hass, actions["pick"], index)
        assert calls[-1].data == {"entity_id": entity, "option": name}


async def test_the_dropdown_on_an_old_tablet_steps(hass: HomeAssistant) -> None:
    """Previous and next call select_previous and select_next."""
    entity = "input_select.mode"
    entry = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/select",
        "params": {"entity": entity},
        "variant": "wide",
        "grid_options": {"columns": 12, "rows": 3},
    }
    result = _convert(_dashboard(entry), {}, 1)
    built = _cards(result["layout"])[0]
    outputs = {action["output"] for action in result["bindings"]["actions"].values()}
    assert outputs == {"previous", "next"}
    nxt = async_mock_service(hass, "input_select", "select_next")
    for key, action in result["bindings"]["actions"].items():
        if action["output"] == "next":
            widget = next(w for w in built["w"] if f"{w['id']}:tap" == key)
            await _run(hass, {**action, "widget": widget, "event": "tap"})
    assert nxt[-1].data == {"entity_id": entity}


async def test_the_screen_bar_starts_at_10(hass: HomeAssistant) -> None:
    """The backlight is never set below 10 %."""
    entity = "light.backlight"
    calls = async_mock_service(hass, "light", "turn_on")
    actions = _bindings(
        "apollo/screen",
        {"entity": entity},
        {entity: facts_of(DIM_LAMP_RAW)},
        variant="row",
    )
    bar = actions["set"]["widget"]
    assert (bar["min"], bar["max"]) == (10, 100)
    await _run(hass, actions["set"], 80)
    assert calls[-1].data == {"entity_id": entity, "brightness_pct": 80}


def test_the_link_goes_to_its_page() -> None:
    """A tap goes to the page; on an old tablet a button does."""
    entry = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/page-link",
        "params": {"page": "climate"},
        "variant": "tile",
        "grid_options": {"columns": 6, "rows": 3},
    }
    config = _dashboard(entry)
    config["views"].append(
        {"type": "sections", "path": "climate", "title": "Climate", "sections": []}
    )
    v2 = _cards(_convert(config, {}, 2)["layout"])[0]
    assert v2["tap"] == {"local": "go_to_page", "page": "climate"}
    assert not any(w["t"] == "label" and w.get("size") == "l" for w in v2["w"])
    v1 = _cards(_convert(config, {}, 1)["layout"])[0]
    [button] = [w for w in v1["w"] if w["t"] == "button"]
    assert button["tap"] == {"local": "go_to_page", "page": "climate"}


def test_the_link_shows_a_reading_when_it_has_a_device() -> None:
    """`has.entity` adds the reading at 34 px and the device's name."""
    component = COMPONENTS["apollo/page-link"]
    result = _compile(
        component, "tile", {"page": "climate", "entity": "sensor.temperature"}, {}, {}
    )
    labels = [w for w in result["widgets"] if w["t"] == "label"]
    assert [w["size"] for w in labels][-2:] == ["l", "s"]


# ---------------------------------------------------------------- words


def test_the_words_of_the_nine_cards() -> None:
    """Every card has a name, a description and labels; each choice is labelled."""
    for component_id in STEP_A:
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


def test_the_nine_cards_replace_only_what_d5_says() -> None:
    """apollo/light, apollo/scenes and apollo/reading take the old cards' places."""
    replaces = {
        component_id: COMPONENTS[component_id]["replaces"]
        for component_id in STEP_A
        if COMPONENTS[component_id]["replaces"]
    }
    assert replaces == {
        "apollo/light": ["apollo/light-tile", "apollo/light-slider"],
        "apollo/scenes": ["apollo/scene-row"],
        "apollo/reading": ["apollo/sensor-value"],
    }


def test_every_option_combination_of_the_light_fits_the_controls_page() -> None:
    """The detail copy holds every row at once for a lamp with effects."""
    component = COMPONENTS["apollo/light"]
    facts = {"light.a": _facts("light", True)}
    for control, saturation, white in itertools.product(
        ["none", "bar", "dots", "both"], [True, False], [True, False]
    ):
        options = {
            "colour_control": control,
            "show_saturation": saturation,
            "show_white": white,
            "effects_shown": EFFECTS[:8],
        }
        result = _compile(component, "full", {"entity": "light.a"}, options, facts)
        _assert_inside(result, str(options))
        assert any(len(w.get("texts", [])) == 8 for w in result["widgets"])


def test_the_example_cards_need_no_device() -> None:
    """Each card compiles as an example (no device picked), with nothing clipped."""
    for component_id in STEP_A:
        component = COMPONENTS[component_id]
        for name, variant in component["variants"].items():
            columns, rows = variant["grid"]
            raw = {"variant": name, "grid_options": {"columns": columns, "rows": rows}}
            card = validate_card_config2(component, copy.deepcopy(raw))
            result = compile_card2(component, card, {}, 2, detail=not variant["picker"])
            _assert_inside(result, f"{component_id} {name}")


# ---------------------------------------------------------------- live values


async def _value(hass: HomeAssistant, result: dict, ref: Any) -> Any:
    """Work out one slot of a compiled card as Home Assistant would."""
    from custom_components.apollo_tab.live import async_evaluate_slot

    assert isinstance(ref, dict) and "s" in ref, ref
    [slot] = [s for s in result["slots"] if s["n"] == ref["s"]]
    return await async_evaluate_slot(hass, slot)


def _label(result: dict, size: str, align: int = 0) -> dict:
    """Return the first label of a size and alignment."""
    return next(
        w
        for w in result["widgets"]
        if w["t"] == "label" and w.get("size") == size and w.get("al", 0) == align
    )


async def test_the_lights_level_and_state(hass: HomeAssistant) -> None:
    """68 % for a dimmed lamp; nothing while off or for a lamp without brightness."""
    component = COMPONENTS["apollo/light"]
    lamp = "light.h1401"
    result = _compile(
        component, "tile", {"entity": lamp}, {}, {lamp: facts_of(OWNER_LAMP_RAW)}
    )
    level = _label(result, "s", 2)["text"]
    hass.states.async_set(lamp, "on", {"brightness": 173, "friendly_name": "Sofa lamp"})
    assert await _value(hass, result, level) == "68%"
    assert await _value(hass, result, result["on"]) is True
    hass.states.async_set(lamp, "off", {"friendly_name": "Sofa lamp"})
    assert await _value(hass, result, level) == ""
    onoff = _compile(
        component, "tile", {"entity": lamp}, {}, {lamp: facts_of(ONOFF_LAMP_RAW)}
    )
    hass.states.async_set(lamp, "on", {"friendly_name": "Sofa lamp"})
    assert await _value(hass, onoff, _label(onoff, "s", 2)["text"]) == ""


async def test_the_switch_says_its_words(hass: HomeAssistant) -> None:
    """The person's words for on and off are the state line."""
    component = COMPONENTS["apollo/switch"]
    result = _compile(
        component,
        "chip",
        {"entity": "switch.kettle"},
        {"word_on": "Boiling", "word_off": "Cold"},
        {},
    )
    state = _label(result, "s", 2)["text"]
    hass.states.async_set("switch.kettle", "on")
    assert await _value(hass, result, state) == "Boiling"
    hass.states.async_set("switch.kettle", "off")
    assert await _value(hass, result, state) == "Cold"


async def test_the_button_is_gone_only_while_unavailable(hass: HomeAssistant) -> None:
    """A button that was never pressed reads "unknown" and is not faded."""
    component = COMPONENTS["apollo/button"]
    result = _compile(component, "tile", {"entity": "button.bell"}, {}, {})
    hass.states.async_set("button.bell", "unknown")
    assert await _value(hass, result, result["un"]) is False
    hass.states.async_set("button.bell", "unavailable")
    assert await _value(hass, result, result["un"]) is True


async def test_the_reading_line_and_its_highlight(hass: HomeAssistant) -> None:
    """Rounded to the decimals with the unit; words for on and off; the marks."""
    component = COMPONENTS["apollo/reading"]
    entity = "sensor.co2"
    options = {"decimals": 0, "highlight": "above", "high": 1000, "high_colour": "bad"}
    result = _compile(component, "chip", {"entity": entity}, options, {})
    line = _label(result, "s", 2)["text"]
    hass.states.async_set(entity, "1234.4", {"unit_of_measurement": "ppm"})
    assert await _value(hass, result, line) == "1234 ppm"
    assert await _value(hass, result, result["on"]) is True
    assert await _value(hass, result, result["tint"]) == "bad"
    hass.states.async_set(entity, "640", {"unit_of_measurement": "ppm"})
    assert await _value(hass, result, result["on"]) is False
    assert await _value(hass, result, result["tint"]) is None
    door = _compile(
        component,
        "chip",
        {"entity": "binary_sensor.door"},
        {"word_on": "Open", "highlight": "active"},
        {},
    )
    hass.states.async_set("binary_sensor.door", "on", {"device_class": "door"})
    assert await _value(hass, door, _label(door, "s", 2)["text"]) == "Open"
    assert await _value(hass, door, door["on"]) is True
    hass.states.async_set("binary_sensor.door", "off", {"device_class": "door"})
    # No word of the person's for off: Home Assistant's own word.
    assert await _value(hass, door, _label(door, "s", 2)["text"]) == "off"


async def test_the_number_and_dropdown_values(hass: HomeAssistant) -> None:
    """The number's value and text; the dropdown's place of its state."""
    number = _compile(
        COMPONENTS["apollo/number"],
        "row",
        {"entity": "number.target"},
        {},
        {"number.target": facts_of(EVERYTHING_RAW["number"])},
    )
    hass.states.async_set("number.target", "21.5", {"unit_of_measurement": "°C"})
    [bar] = [w for w in number["widgets"] if w["t"] == "slider"]
    assert await _value(hass, number, bar["value"]) == 21.5
    assert await _value(hass, number, _label(number, "s", 2)["text"]) == "21.5 °C"
    facts = facts_of(
        {
            "domain": "select",
            "state": {"attributes": {"options": ["Eco", "Comfort", "Away"]}},
        }
    )
    select = _compile(
        COMPONENTS["apollo/select"],
        "wide",
        {"entity": "select.mode"},
        {},
        {"select.mode": facts},
    )
    [choice] = [w for w in select["widgets"] if w["t"] == "choice"]
    hass.states.async_set("select.mode", "Comfort")
    assert await _value(hass, select, choice["value"]) == 1
    hass.states.async_set("select.mode", "Gone")
    assert await _value(hass, select, choice["value"]) is None


async def test_the_screen_and_link_texts(hass: HomeAssistant) -> None:
    """80 % for the screen; the link's reading with its unit and the device's name."""
    screen = _compile(
        COMPONENTS["apollo/screen"],
        "row",
        {"entity": "light.backlight"},
        {},
        {"light.backlight": facts_of(DIM_LAMP_RAW)},
    )
    hass.states.async_set("light.backlight", "on", {"brightness": 204})
    assert await _value(hass, screen, _label(screen, "s", 2)["text"]) == "80%"
    link = _compile(
        COMPONENTS["apollo/page-link"],
        "tile",
        {"page": "climate", "entity": "sensor.temperature"},
        {},
        {},
    )
    hass.states.async_set(
        "sensor.temperature",
        "21.4",
        {"unit_of_measurement": "°C", "friendly_name": "Living room"},
    )
    assert await _value(hass, link, _label(link, "l")["text"]) == "21.4 °C"
    assert await _value(hass, link, _label(link, "s")["text"]) == "Living room"


async def test_the_scenes_card_is_gone_only_when_every_scene_is(
    hass: HomeAssistant,
) -> None:
    """Scenes read "unknown" until first used; the card fades only when all are gone."""
    component = COMPONENTS["apollo/scenes"]
    result = _compile(component, "wide", {"scenes": ["scene.a", "script.b"]}, {}, {})
    hass.states.async_set("scene.a", "unknown")
    hass.states.async_set("script.b", "unavailable")
    assert await _value(hass, result, result["un"]) is False
    hass.states.async_set("scene.a", "unavailable")
    assert await _value(hass, result, result["un"]) is True
