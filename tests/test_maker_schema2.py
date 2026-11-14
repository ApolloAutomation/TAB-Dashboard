"""Tests for the validator of schema 2 card files (cards spec C.2)."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from custom_components.apollo_tab.maker import (
    schema as schema_module,
    templates as templates_module,
)
from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.schema import (
    component_templates,
    validate_card_config,
    validate_component,
)
from custom_components.apollo_tab.maker.schema2 import (
    check_option_value,
    parse_when_term,
)
from custom_components.apollo_tab.maker.templates import check_component_templates

HERE = Path(__file__).parent
LIGHT = HERE / "cards2" / "light.yaml"
BUILTIN_DIR = (
    HERE.parent / "custom_components" / "apollo_tab" / "library" / "components"
)

# The 16 files of schema 1, normalised and hashed as the library does it.
# Taken before schema 2 was added: none of them may change. The camera,
# media and presence cards are pinned as their plain description lines left
# them (a description reaches no layout).
BUILTIN_HASHES = {
    "apollo/alarm-panel": (
        "1b0803db90cf315467a0317fc4234b4c1b2588c5f46c083a32f0edca15632fce"
    ),
    "apollo/blinds": (
        "8e517f1dea3c12044b7c38f63b3d223a9a117e0e44e51573394831e8b93c963e"
    ),
    "apollo/camera-snapshot": (
        "0dedff5df47e17eff92320125cb59d7adfc5fc4194b0413994e1bfdc1ed87847"
    ),
    "apollo/fan": ("a258756fc499d891e48ab67b50adc39b55ae320f74996edb134684935fb9236f"),
    "apollo/light-slider": (
        "f9d438c48cccd5d8ed565063c776ed38742ef2078b79f9cebea35ea8962a3a21"
    ),
    "apollo/light-tile": (
        "ca555c8024d5e8d35f630e08283ef3bfd86237f2cfb5b4b189b79dd6122ebef1"
    ),
    "apollo/lock": ("ab9f9c3b49fcabf1712c77fe4f290b59fb96233f9ffccf2da87e9cff1abf77fe"),
    "apollo/media-player": (
        "46e40c0d9a86fa406b0872e5e63547e3d95afc7c121f0dd6f93afb012b0e0d35"
    ),
    "apollo/scene-row": (
        "6cec8a5e23c91704ca2b20b9821c08a8395fec8c04b3026bcf18b287ac6baae9"
    ),
    "apollo/sensor-graph": (
        "fa0478f60bdd103c27ba514ff307045b5894500a78fd2b0862cbf6275bef2a82"
    ),
    "apollo/sensor-value": (
        "42fcfb25537c9f208691d796ef7c386a59dfe51308d543963c9917cf3f55230c"
    ),
    "apollo/thermostat": (
        "b4c961a293ad06f9800cbc413cc336bdc60ccea9eb71eacfc0dfcabba2a3661a"
    ),
    "apollo/weather": (
        "620048c0475cca04c9cedd73fd45fc9d77adf5c50abf883c68e314d4dad25189"
    ),
    "community/energy-gauge": (
        "ae753cd4acd53079f892195895112df5a5faf91a3802d753ff4753e4468ed6b1"
    ),
    "community/presence-chips": (
        "e85144c4a88fdbc98e4ee2efb7b6f2222717774508e53492d4221af580531de0"
    ),
    "community/room-summary": (
        "e2c2836bee05610c9749c3491f3bd92bbf7632ca9c946e4cda1c70658b4a22e8"
    ),
}


def _light() -> dict:
    """Return the colour light of spec D.1 as a fresh document."""
    return yaml.safe_load(LIGHT.read_text(encoding="utf-8"))


def _doc(**overrides) -> dict:
    """Return a small valid schema 2 document with overrides applied."""
    doc = {
        "schema": 2,
        "id": "test/two",
        "version": "1.0.0",
        "name": "Two",
        "params": {"entity": {"domain": "light"}},
        "options": {
            "show_bar": {
                "type": "toggle",
                "section": "controls",
                "label": "Bar",
                "default": True,
            },
            "word": {"type": "text", "section": "shows", "label": "Word"},
        },
        "inputs": {
            "is_on": "{{ is_state(entity, 'on') }}",
            "pct": "{{ state_attr(entity, 'brightness') }}",
        },
        "outputs": {
            "toggle": {
                "action": "light.toggle",
                "data": {"entity_id": "{{ entity }}"},
                "feedback": "optimistic",
            },
            "dim": {
                "action": "light.turn_on",
                "data": {"entity_id": "{{ entity }}", "brightness_pct": "{{ value }}"},
                "feedback": "optimistic",
            },
        },
        "variants": {
            "tile": {
                "name": "Tile",
                "grid": [6, 3],
                "layout": [{"type": "label", "text": "Hello"}],
            }
        },
    }
    doc.update(overrides)
    return doc


def _with_layout(*items, **overrides) -> dict:
    """Return the small document with one variant holding these items."""
    doc = _doc(**overrides)
    doc["variants"]["tile"]["layout"] = list(items)
    return doc


def _refused(doc: dict, code: str, path: str | None = None) -> MakerError:
    """Assert the document is refused with this code (and path)."""
    with pytest.raises(MakerError) as info:
        validate_component(doc)
    assert info.value.code == code, str(info.value)
    if path is not None:
        assert info.value.path == path, str(info.value)
    return info.value


def _check(doc: dict) -> dict:
    """Validate and template-check a document; return it normalised."""
    component = validate_component(doc)
    check_component_templates(component)
    return component


def _item(doc: dict, index: int = 0) -> dict:
    """Return one item of the first variant of a normalised document."""
    return validate_component(doc)["variants"]["tile"]["layout"][index]


# ---------------------------------------------------------------- the file


def test_builtin_files_keep_their_hashes():
    """The 16 schema 1 files load byte for byte as before schema 2."""
    found = {}
    for path in sorted(BUILTIN_DIR.glob("*.yaml")):
        component = validate_component(yaml.safe_load(path.read_text("utf-8")))
        if component.get("schema") == 2:
            continue
        digest = hashlib.sha256(json.dumps(component, sort_keys=True).encode())
        found[component["id"]] = digest.hexdigest()
    assert found == BUILTIN_HASHES


def test_the_light_of_d1_loads():
    """The reference card of spec D.1 loads and its templates pass."""
    component = _check(_light())
    assert component["schema"] == 2
    assert component["group"] == "lights"
    assert component["replaces"] == ["apollo/light-tile", "apollo/light-slider"]
    assert list(component["variants"]) == ["tile", "wide", "large", "full"]
    assert component["detail"] == "full"
    assert component["hold"] == "detail"
    assert component["on"] == {"form": "input", "input": "is_on"}
    assert component["tint"] == {"form": "input", "input": "colour"}
    assert component["size"] == [1, 1]
    assert component["sensitive"] is False
    assert component["uses_inputs"] is True
    assert [v["widgets"] for v in component["variants"].values()] == [2, 4, 5, 6]
    white = component["variants"]["full"]["layout"][3]
    assert white["part"] == "white"
    assert white["height"] == 48
    assert white["min"] == {"form": "lookup", "name": "can", "key": "min_kelvin"}
    assert white["track"]["kelvin"][1] == {
        "form": "lookup",
        "name": "can",
        "key": "max_kelvin",
    }
    tile = component["variants"]["tile"]
    assert tile["trailing"] == {"form": "input", "input": "level"}
    # A use line adds its when to the part's own.
    assert tile["layout"][0]["when"] == [
        "can.brightness",
        "show_brightness",
        "bar_on_tile",
    ]


def test_yaml_on_key_is_the_card_on():
    """YAML 1.1 reads `on:` as true; at the top it means the card's on."""
    doc = _doc()
    doc[True] = "is_on"
    component = validate_component(doc)
    assert component["on"] == {"form": "input", "input": "is_on"}
    doc["on"] = "is_on"
    _refused(doc, "duplicate_name", "on")


def test_unknown_schema_refused():
    """Only schemas 1 and 2 exist."""
    doc = {
        "schema": 3,
        "id": "test/three",
        "version": "1.0.0",
        "name": "Three",
        "size": "1x1",
        "layout": [{"type": "label", "text": "x"}],
    }
    _refused(doc, "bad_value", "schema")


def test_unknown_top_level_key_refused():
    """A key schema 2 does not know is refused."""
    _refused(_doc(colour="#FF0000"), "unknown_key", "colour")


def test_schema1_keys_are_not_schema2_keys():
    """Schema 1's header flag is not a key of a schema 2 file with variants."""
    _refused(_doc(header=True), "bad_value", "header")


def test_one_variant_at_the_top():
    """Layout and size at the top give one variant, default."""
    doc = _doc()
    del doc["variants"]
    doc.update(size="2x1", header="chip", layout=[{"type": "label", "text": "x"}])
    component = validate_component(doc)
    assert list(component["variants"]) == ["default"]
    variant = component["variants"]["default"]
    assert variant["grid"] == [12, 3]
    assert variant["name"] == "Two"
    assert variant["header"] == "chip"
    assert component["size"] == [2, 1]


def test_variants_or_layout():
    """A file has variants or a layout, not both and not neither."""
    _refused(_doc(layout=[]), "bad_value")
    doc = _doc()
    del doc["variants"]
    _refused(doc, "missing_key", "variants")
    doc["layout"] = [{"type": "label", "text": "x"}]
    _refused(doc, "missing_key", "size")


@pytest.mark.parametrize(
    ("key", "value", "code"),
    [
        ("group", "kitchen", "bad_value"),
        ("lit", "glow", "bad_value"),
        ("hold", "detail", "bad_value"),
        ("hold", "always", "bad_value"),
        ("detail", "huge", "bad_value"),
        ("v1", "not an id", "bad_id"),
        ("replaces", ["test/two"], "bad_value"),
        ("replaces", "apollo/light", "bad_value"),
        ("icon", "lightbulb", "bad_value"),
        ("name", "x" * 41, "too_long"),
    ],
)
def test_card_level_values_refused(key, value, code):
    """Card-level keys take only their own values."""
    _refused(_doc(**{key: value}), code)


def test_card_level_values_accepted():
    """group, lit, v1 note, replaces and notes load."""
    component = validate_component(
        _doc(
            group="climate",
            lit="outline",
            v1="note",
            replaces=["apollo/light-tile"],
            notes=[
                {"text": "This light only turns on and off.", "when": ["!show_bar"]}
            ],
        )
    )
    assert component["group"] == "climate"
    assert component["lit"] == "outline"
    assert component["v1"] == "note"
    assert component["replaces"] == ["apollo/light-tile"]
    assert component["notes"][0]["when"] == ["!show_bar"]
    assert component["hold"] is None
    assert component["tap"] is None


def test_live_card_fields_are_marked():
    """on, tint, state and unavailable are inputs or templates."""
    component = validate_component(
        _doc(on="is_on", state="{{ states(entity) }}", unavailable="is_on")
    )
    assert component["state"] == {
        "form": "template",
        "template": "{{ states(entity) }}",
    }
    assert component["unavailable"] == {"form": "input", "input": "is_on"}
    _refused(_doc(tint="nothing_here"), "unknown_input", "tint")


# ---------------------------------------------------------------- limits


def _many(count: int, make) -> dict:
    """Return a mapping of count generated entries."""
    return {f"n{index}": make(index) for index in range(count)}


def _option(index: int) -> dict:
    """Return a toggle option."""
    return {"type": "toggle", "section": "look", "label": "Thing"}


@pytest.mark.parametrize(
    ("key", "make", "limit"),
    [
        ("params", lambda i: {"domain": "light"}, 8),
        ("options", _option, 16),
        ("inputs", lambda i: "{{ 1 }}", 32),
        (
            "outputs",
            lambda i: {"local": "open_details"},
            16,
        ),
        ("parts", lambda i: {"type": "label", "text": "x"}, 32),
    ],
)
def test_section_limits(key, make, limit):
    """Each section has its limit per file."""
    base = _doc()
    base[key] = {**base.get(key, {}), **_many(limit, make)}
    base[key] = dict(list(base[key].items())[:limit])
    validate_component(copy.deepcopy(base))
    base[key]["zz"] = make(0)
    _refused(base, "too_many", key)


def test_variant_and_item_limits():
    """6 variants a file and 24 items a variant."""
    doc = _doc()
    variant = doc["variants"]["tile"]
    doc["variants"] = {f"v{index}": copy.deepcopy(variant) for index in range(6)}
    validate_component(copy.deepcopy(doc))
    doc["variants"]["v6"] = variant
    _refused(doc, "too_many", "variants")
    label = {"type": "label", "text": "x"}
    validate_component(_with_layout(*[label] * 24))
    _refused(_with_layout(*[label] * 25), "bad_value", "variants.tile.layout")


def test_widget_limit_counts_while_it_walks():
    """48 widgets a card after loops, counted as the walk goes."""
    params = {
        "entity": {"domain": "light"},
        "lights": {"domain": "light", "multiple": True, "max": 16},
    }
    row = {
        "type": "row",
        "for_each": "lights",
        "as": "one",
        "items": [{"type": "label", "text": "x"}] * 3,
    }
    # 3 widgets in 16 copies: 48 is the limit itself.
    component = validate_component(_with_layout(row, params=params))
    assert component["variants"]["tile"]["widgets"] == 48
    # One more widget after the loop passes it, and is refused right there.
    error = _refused(
        _with_layout(row, {"type": "label", "text": "y"}, params=params),
        "too_many",
    )
    assert error.path == "variants.tile.layout.1"
    # A fourth widget in the row: the loop alone passes it, before anything
    # after it is read.
    bigger = dict(row, items=[{"type": "label", "text": "x"}] * 4)
    error = _refused(
        _with_layout(bigger, {"type": "nothing"}, params=params), "too_many"
    )
    assert error.path == "variants.tile.layout.0"


def test_loop_copies_limit():
    """A list in the file makes at most 16 copies."""
    entries = [{"text": "a"}] * 16
    item = {"type": "label", "text": "{{ e.text }}", "for_each": entries, "as": "e"}
    assert _item(_with_layout(item))["text"]["form"] == "lookup"
    item["for_each"] = entries + [{"text": "b"}]
    _refused(_with_layout(item), "too_many")


def test_row_and_when_limits():
    """8 widgets a row; 6 terms a when."""
    label = {"type": "label", "text": "x"}
    validate_component(_with_layout({"type": "row", "items": [label] * 8}))
    _refused(_with_layout({"type": "row", "items": [label] * 9}), "bad_value")
    terms = ["show_bar"] * 6
    validate_component(_with_layout(dict(label, when=terms)))
    _refused(_with_layout(dict(label, when=[*terms, "word"])), "too_many")


# ---------------------------------------------------------------- nesting


def test_a_part_may_not_use_a_part():
    """A part cannot use another part, also inside a row."""
    parts = {
        "a": {"type": "label", "text": "x"},
        "b": {"use": "a"},
    }
    _refused(_doc(parts=parts), "bad_nesting", "parts.b.use")
    parts = {
        "a": {"type": "label", "text": "x"},
        "b": {"type": "row", "items": [{"use": "a"}]},
    }
    _refused(_doc(parts=parts), "bad_nesting", "parts.b.items.0.use")


def test_a_row_holds_widgets_only():
    """No row, swap or space in a row, also through a part."""
    label = {"type": "label", "text": "x"}
    inner = {"type": "row", "items": [label]}
    _refused(_with_layout({"type": "row", "items": [inner]}), "bad_nesting")
    swap = {"type": "swap", "items": [dict(label, visible="is_on")] * 2}
    _refused(_with_layout({"type": "row", "items": [swap]}), "bad_nesting")
    _refused(_with_layout({"type": "row", "items": [{"type": "space"}]}), "bad_nesting")
    _refused(
        _with_layout({"type": "row", "items": [{"use": "r"}]}, parts={"r": inner}),
        "bad_nesting",
    )


def test_a_swap_holds_widgets_or_rows_each_with_visible():
    """A swap holds widgets or rows, each with visible; nothing else nests."""
    on = {"type": "button", "text": "Off", "on_tap": "toggle", "visible": "is_on"}
    off = {"type": "row", "visible": "{{ not is_on }}", "items": [on]}
    swap = _item(_with_layout({"type": "swap", "items": [on, off]}))
    assert swap["items"][1]["visible"]["form"] == "template"
    _refused(
        _with_layout({"type": "swap", "items": [on, dict(on, visible=None)]}),
        "unknown_input",
    )
    bare = {k: v for k, v in on.items() if k != "visible"}
    _refused(
        _with_layout({"type": "swap", "items": [on, bare]}),
        "missing_key",
        "variants.tile.layout.0.items.1.visible",
    )
    nested = {"type": "swap", "items": [on, on]}
    _refused(_with_layout({"type": "swap", "items": [on, nested]}), "bad_nesting")
    _refused(_with_layout({"type": "swap", "items": [on]}), "bad_value")


def test_a_loop_may_not_hold_a_loop():
    """A looped row may not hold a loop, also through a part."""
    params = {"lights": {"domain": "light", "multiple": True}}
    inner = {"type": "label", "text": "x", "for_each": [1, 2], "as": "n"}
    row = {"type": "row", "for_each": "lights", "as": "one", "items": [inner]}
    _refused(_with_layout(row, params=params), "bad_nesting")
    row = {"type": "row", "for_each": "lights", "as": "one", "items": [{"use": "p"}]}
    _refused(_with_layout(row, params=params, parts={"p": inner}), "bad_nesting")


def test_use_adds_and_replaces_keys():
    """A use line may add or replace keys but not the type."""
    parts = {"dim": {"type": "slider", "value": "pct", "when": ["show_bar"]}}
    item = _item(
        _with_layout({"use": "dim", "height": 56, "look": "knob"}, parts=parts)
    )
    assert item["part"] == "dim"
    assert item["height"] == 56
    assert item["look"] == "knob"
    assert item["when"] == ["show_bar"]
    _refused(_with_layout({"use": "dim", "type": "label"}, parts=parts), "bad_value")
    _refused(_with_layout({"use": "nope"}, parts=parts), "unknown_part")


def test_size_keys():
    """Height or grow; width or weight only in a row."""
    label = {"type": "label", "text": "x"}
    assert _item(_with_layout(dict(label, grow=True)))["grow"] is True
    _refused(_with_layout(dict(label, height=40, grow=True)), "bad_value")
    _refused(_with_layout(dict(label, width=40)), "bad_value")
    row = _item(
        _with_layout(
            {"type": "row", "items": [dict(label, width=80), dict(label, weight=2)]}
        )
    )
    assert [row["items"][0]["width"], row["items"][1]["weight"]] == [80, 2]
    _refused(
        _with_layout({"type": "row", "items": [dict(label, width=8, weight=1)]}),
        "bad_value",
    )
    assert _item(_with_layout({"type": "space", "grow": True}))["type"] == "space"


# ---------------------------------------------------------------- names


@pytest.mark.parametrize(
    "name", ["can", "has", "tablet", "option", "value", "response"]
)
def test_reserved_names(name):
    """can, has, tablet, option, value and response are reserved."""
    _refused(_doc(params={name: {"domain": "light"}}), "bad_name")
    _refused(_doc(inputs={name: "{{ 1 }}"}), "bad_name")


@pytest.mark.parametrize("name", ["icon", "tap", "tap_page", "hold", "ask"])
def test_standard_option_names_reserved(name):
    """A file option may not take a standard option's name."""
    _refused(_doc(options={name: _option(0)}), "bad_name")


def test_names_are_unique_across_sections():
    """A param, an option and an input may not share a name."""
    _refused(_doc(inputs={"show_bar": "{{ 1 }}"}), "duplicate_name")
    _refused(_doc(options={"entity": _option(0)}), "duplicate_name")


def test_vars_may_not_hide_a_name():
    """A vars name may not equal a param, an option, an input or a reserved name."""
    button = {"type": "button", "text": "Go", "on_tap": "toggle"}
    for name in ("entity", "show_bar", "pct", "value"):
        _refused(_with_layout(dict(button, vars={name: 1})), "bad_name")
    _refused(_with_layout(dict(button, vars={"mode": "{{ x }}"})), "bad_value")
    item = _item(_with_layout(dict(button, vars={"mode": "heat"})))
    assert item["vars"] == {"mode": "heat"}


def test_output_names_detail_and_back_reserved():
    """Detail and back are what an item says to open or leave the detail page."""
    _refused(_doc(outputs={"detail": {"local": "open_details"}}), "bad_name")


# ---------------------------------------------------------------- params


def test_entity_param_fields():
    """Kinds, any, device classes, optional, several devices, words."""
    component = validate_component(
        _doc(
            params={
                "entity": {
                    "domain": ["switch", "input_boolean"],
                    "device_class": ["outlet"],
                    "optional": True,
                    "label": "Switch",
                    "help": "The plug to turn on and off.",
                },
                "any_one": {"domain": "any"},
                "lights": {"domain": "light", "multiple": True, "max": 16},
            },
            outputs={},
            options={},
        )
    )
    entity = component["params"]["entity"]
    assert entity["domains"] == ["switch", "input_boolean"]
    assert entity["domain"] is None
    assert entity["optional"] is True
    assert entity["device_class"] == ["outlet"]
    assert entity["label"] == "Switch"
    assert component["params"]["any_one"]["domains"] == []
    assert component["params"]["lights"]["max"] == 16


@pytest.mark.parametrize(
    "spec",
    [
        {"domain": "light", "max": 4},
        {"domain": "light", "multiple": True, "max": 17},
        {"domain": []},
        {"domain": ["light", "light"]},
        {"domain": "light", "label": "x" * 41},
        {"domain": "light", "help": "x" * 121},
        {"domain": "light", "optional": "yes"},
        {"domain": "light", "device_class": [1]},
        {"domain": "light", "colour": 1},
        {"type": "page", "domain": "light"},
    ],
)
def test_entity_param_refusals(spec):
    """Bad param fields are refused."""
    with pytest.raises(MakerError):
        validate_component(_doc(params={"entity": spec}))


# ---------------------------------------------------------------- options


def test_every_option_type_loads():
    """The seven option types with their fields (C.2.3)."""
    light = validate_component(_light())
    options = light["options"]
    assert options["show_brightness"]["default"] is True
    assert options["show_brightness"]["needs"] == "can.brightness"
    assert options["colour_control"]["choices"][0] == {"value": "none", "label": "Off"}
    assert options["colour_control"]["default"] == "bar"
    assert options["favourites"]["default"][-1] == "2700K"
    assert options["favourites"]["when"] == ["colour_control=dots|both"]
    assert options["effects_shown"]["from"] == "can.effect_list"
    assert options["effects_shown"]["default_first"] == 4
    more = validate_component(
        _doc(
            options={
                "count": {
                    "type": "number",
                    "section": "look",
                    "label": "Count",
                    "min": 0,
                    "max": 3,
                    "default": 1,
                },
                "word": {
                    "type": "text",
                    "section": "shows",
                    "label": "Word",
                    "max": 20,
                },
                "badge": {"type": "icon", "section": "look", "label": "Icon"},
                "tone": {
                    "type": "colour",
                    "section": "look",
                    "label": "Colour",
                    "default": "info",
                },
            }
        )
    )["options"]
    assert more["count"] == {
        "type": "number",
        "section": "look",
        "label": "Count",
        "help": "",
        "when": [],
        "needs": "",
        "needs_text": "",
        "min": 0.0,
        "max": 3.0,
        "step": 1.0,
        "unit": "",
        "default": 1.0,
    }
    assert more["word"]["default"] == ""
    assert more["badge"]["default"] is None
    assert more["tone"]["default"] == "info"


def _opt(otype: str, **fields) -> dict:
    """Return an options section with one option."""
    return {"thing": {"type": otype, "section": "look", "label": "Thing", **fields}}


@pytest.mark.parametrize(
    "options",
    [
        _opt("slider"),
        {"thing": {"type": "toggle", "section": "side", "label": "Thing"}},
        {"thing": {"type": "toggle", "section": "look"}},
        {"thing": {"type": "toggle", "section": "look", "label": ""}},
        _opt("toggle", default="yes"),
        _opt("toggle", needs_text="Cannot"),
        _opt("toggle", needs="brightness"),
        _opt("toggle", needs="can.nothere.brightness"),
        _opt("choice", choices={"a": "A"}),
        _opt("choice", choices={f"c{i}": "C" for i in range(9)}),
        _opt("choice", choices={"a": "A", "b": "B"}, default="c"),
        _opt("choice", choices={"a": "A", "B": "B"}),
        _opt("choice", choices={"a": "A", "b": "B"}, from_="can.x"),
        _opt("choice", choices={"a": "A", "b": "B"}, default_first=1),
        _opt("choice", **{"from": "can.effect_list", "default": "x"}),
        _opt("choice", **{"from": "effect_list"}),
        _opt("choice", choices={"a": "A", "b": "B"}, max=2),
        _opt("choice", choices={"a": "A", "b": "B"}, multiple=True, max=17),
        _opt("choice", choices={"a": "A", "b": "B"}, multiple=True, default=["a", "a"]),
        _opt("number", min=5, max=1),
        _opt("number", min=0, max=3, default=4),
        _opt("number", step=0),
        _opt("text", max=41),
        _opt("text", max=5, default="toolong"),
        _opt("icon", default="lightbulb"),
        _opt("colour", default="pink"),
        _opt("colours", max=9),
        _opt("colours", max=2, default=["#FF0000", "#00FF00", "#0000FF"]),
        _opt("colours", default=["900K"]),
        _opt("colours", default=["#FF00"]),
        _opt("toggle", unit="%"),
    ],
)
def test_option_refusals(options):
    """Bad option fields are refused at load."""
    for spec in options.values():
        if "from_" in spec:
            spec["from"] = spec.pop("from_")
    with pytest.raises(MakerError):
        validate_component(_doc(options=options))


def test_option_when_names_only_what_it_may():
    """When names options, can facts, has.<param> and tablet.v2."""
    good = ["show_bar", "!word", "can.colour", "can.entity.colour", "has.entity"]
    validate_component(_with_layout({"type": "label", "text": "x", "when": good}))
    validate_component(
        _with_layout({"type": "label", "text": "x", "when": ["tablet.v2"]})
    )
    for term in (
        "nothing",
        "pct",
        "can",
        "has.nothing",
        "tablet.v3",
        "can.nothere.colour",
        "has.entity=a",
        "!show_bar=a",
        "show_bar=A",
        "",
    ):
        with pytest.raises(MakerError):
            validate_component(
                _with_layout({"type": "label", "text": "x", "when": [term]})
            )


def test_when_values_must_be_choices():
    """A term with = names keys of the choice it reads."""
    light = _light()
    light["parts"]["hue"]["when"] = ["colour_control=bar|stripes"]
    _refused(light, "bad_value", "parts.hue.when.0")


def test_parse_when_term():
    """The four term forms."""
    assert parse_when_term("show", "p") == {
        "name": "show",
        "not": False,
        "op": None,
        "values": [],
    }
    assert parse_when_term("!can.colour", "p")["not"] is True
    assert parse_when_term("mode=a|b", "p")["values"] == ["a", "b"]
    assert parse_when_term("mode!=a", "p")["op"] == "!="


def test_check_option_value():
    """Stored values are checked by type, range, length and keys."""
    light = validate_component(_light())["options"]
    assert check_option_value(light["colour_control"], "dots", "o") == "dots"
    assert check_option_value(light["favourites"], ["#ff0000", "3000K"], "o") == [
        "#FF0000",
        "3000K",
    ]
    for option, value in (
        (light["colour_control"], "stripes"),
        (light["show_brightness"], 1),
        (light["favourites"], ["#FF0000"] * 9),
        (light["effects_shown"], "Rainbow"),
    ):
        with pytest.raises(MakerError):
            check_option_value(option, value, "o")
    # Entries of a list from the device keep their whole text here.
    long_name = "x" * 60
    assert check_option_value(light["effects_shown"], [long_name], "o") == [long_name]


# ---------------------------------------------------------------- inputs


def test_new_input_sources_load():
    """colour, state_icon, clock, media_position and statistics."""
    inputs = {
        "colour": {"source": "colour", "entity": "{{ entity }}", "of": "hue"},
        "glyph": {"source": "state_icon", "entity": "{{ entity }}"},
        "now": {"source": "clock"},
        "played": {"source": "media_position", "entity": "{{ entity }}"},
        "low": {"source": "statistics", "entity": "{{ entity }}", "stat": "min"},
        "hours": {
            "source": "statistics",
            "entity": "{{ entity }}",
            "buckets": "hour",
            "period": "today",
            "stat": "sum",
        },
    }
    component = validate_component(_doc(inputs=inputs))
    assert component["inputs"]["colour"] == {
        "kind": "colour",
        "param": "entity",
        "of": "hue",
    }
    assert component["inputs"]["now"] == {"kind": "clock"}
    assert component["inputs"]["low"]["hours"] == 24
    assert component["inputs"]["hours"]["buckets"] == "hour"


@pytest.mark.parametrize(
    "spec",
    [
        {"source": "colour", "entity": "{{ entity }}", "of": "hsv"},
        {"source": "colour", "entity": "light.kitchen"},
        {"source": "colour", "entity": "{{ entity }}", "x": 1},
        {"source": "clock", "entity": "{{ entity }}"},
        {"source": "statistics", "entity": "{{ entity }}", "stat": "median"},
        {"source": "statistics", "entity": "{{ entity }}", "hours": 200},
        {"source": "statistics", "entity": "{{ entity }}", "buckets": "day"},
        {"source": "weather"},
    ],
)
def test_new_input_sources_refused(spec):
    """Bad input sources are refused."""
    with pytest.raises(MakerError):
        validate_component(_doc(inputs={"thing": spec}))


def test_input_entity_of_a_loop_over_devices():
    """An input's entity may be a loop over devices, which the layout must have."""
    params = {"lights": {"domain": "light", "multiple": True}}
    inputs = {"tone": {"source": "colour", "entity": "{{ one }}"}}
    row = {
        "type": "row",
        "for_each": "lights",
        "as": "one",
        "items": [{"type": "label", "text": "x"}],
    }
    validate_component(_with_layout(row, params=params, inputs=inputs, outputs={}))
    _refused(
        _with_layout(
            {"type": "label", "text": "x"}, params=params, inputs=inputs, outputs={}
        ),
        "unknown_param",
        "inputs.tone.entity",
    )


def test_list_inputs_only_feed_a_chart():
    """History and hourly statistics feed charts only."""
    inputs = {"week": {"source": "recorder", "entity": "{{ entity }}"}}
    validate_component(_with_layout({"type": "chart", "value": "week"}, inputs=inputs))
    _refused(
        _with_layout(
            {"type": "label", "text": "x", "clock": 24, "value": "week"}, inputs=inputs
        ),
        "bad_value",
    )


# ---------------------------------------------------------------- outputs


def _out(**spec) -> dict:
    """Return an outputs section with one output named run."""
    return {
        "run": {"feedback": "optimistic", "data": {"entity_id": "{{ entity }}"}, **spec}
    }


@pytest.mark.parametrize(
    "action",
    [
        "scene.apply",
        "scene.create",
        "media_player.join",
        "media_player.play_media",
        "vacuum.send_command",
        "homeassistant.reload_all",
        "light.reload",
        "script.my_script",
    ],
)
def test_services_outside_the_list_refused(action):
    """Only the services of the list of C.2.8 load, also in a map."""
    domain = action.split(".", 1)[0]
    params = {"entity": {"domain": domain}}
    _refused(
        _doc(params=params, options={}, outputs=_out(action=action)),
        "action_not_allowed",
    )
    _refused(
        _doc(
            params={"entity": {"domain": "any"}},
            options={},
            outputs=_out(action={domain: action}),
        ),
        "action_not_allowed",
    )


def test_a_wildcard_is_no_service():
    """No wildcard: 'lock.*' is not even a service name."""
    params = {"entity": {"domain": "lock"}}
    _refused(
        _doc(params=params, options={}, outputs=_out(action="lock.*")),
        "bad_value",
        "outputs.run.action",
    )


def test_action_per_kind():
    """A per-kind map: each key a kind of the param and the service's domain."""
    params = {"entity": {"domain": ["switch", "input_boolean"]}}
    actions = {"switch": "switch.toggle", "input_boolean": "input_boolean.toggle"}
    output = validate_component(_doc(params=params, outputs=_out(action=actions)))[
        "outputs"
    ]["run"]
    assert output["action"] is None
    assert output["actions"] == actions
    _refused(
        _doc(params=params, outputs=_out(action={"switch": "light.toggle"})),
        "domain_mismatch",
    )
    _refused(
        _doc(params=params, outputs=_out(action={"light": "light.toggle"})),
        "domain_mismatch",
    )
    # A plain action on a param of several kinds must be one of them.
    _refused(
        _doc(params=params, outputs=_out(action="light.toggle")), "domain_mismatch"
    )
    any_param = {"entity": {"domain": "any"}}
    error = _refused(
        _doc(params=any_param, outputs=_out(action="switch.toggle")), "domain_mismatch"
    )
    assert "action per kind" in str(error)
    validate_component(
        _doc(params=any_param, outputs=_out(action={"fan": "fan.toggle"}))
    )


def test_locks_and_alarms_confirm_and_are_sensitive():
    """A lock or alarm service needs confirm, also in a map, and marks the file."""
    params = {"entity": {"domain": ["lock", "switch"]}}
    actions = {"lock": "lock.unlock", "switch": "switch.toggle"}
    _refused(_doc(params=params, outputs=_out(action=actions)), "confirm_required")
    component = validate_component(
        _doc(params=params, outputs=_out(action=actions, feedback="confirm"))
    )
    assert component["sensitive"] is True


def test_data_values():
    """Scalars; number lists for the colour keys only; never a mapping."""
    good = {
        "entity_id": "{{ entity }}",
        "hs_color": ["{{ value }}", 100],
        "flash": "short",
    }
    validate_component(_doc(outputs=_out(action="light.turn_on", data=good)))
    for data in (
        {"entity_id": "{{ entity }}", "brightness": [1, 2]},
        {"entity_id": "{{ entity }}", "hs_color": [[1, 2]]},
        {"entity_id": "{{ entity }}", "hs_color": [True, 2]},
        {"entity_id": "{{ entity }}", "hs_color": []},
        {"entity_id": "{{ entity }}", "rgb_color": {"r": 1}},
        {"entity_id": "{{ entity }}", "transition": {"seconds": 1}},
        {"entity_id": "{{ entity }}", "area_id": "kitchen"},
        {"entity_id": "light.kitchen"},
        {"entity_id": ["{{ entity }}"]},
        {"brightness": 5},
    ):
        with pytest.raises(MakerError):
            validate_component(_doc(outputs=_out(action="light.turn_on", data=data)))


def test_uses_and_entities():
    """Uses names inputs with a type; an entities input feeds entity_id only."""
    inputs = {"sat": "{{ 1 }}", "targets": "{{ [entity] }}"}
    data = {"entity_id": "{{ targets }}", "hs_color": ["{{ value }}", "{{ sat }}"]}
    component = _check(
        _doc(
            inputs=inputs,
            outputs=_out(
                action="light.turn_on",
                uses={"sat": "number", "targets": "entities"},
                data=data,
            ),
        )
    )
    assert component["outputs"]["run"]["entity_ref"] == "targets"
    _refused(
        _doc(inputs=inputs, outputs=_out(action="light.turn_on", uses={"x": "number"})),
        "unknown_input",
    )
    _refused(
        _doc(inputs=inputs, outputs=_out(action="light.turn_on", uses={"sat": "text"})),
        "bad_value",
    )
    # An entities input that is not listed cannot be the entity_id.
    _refused(
        _doc(
            inputs=inputs,
            outputs=_out(action="light.turn_on", data={"entity_id": "{{ targets }}"}),
        ),
        "unknown_param",
    )


def test_a_data_template_reads_only_inputs_in_uses():
    """A data template that names an input not in uses is refused at load."""
    inputs = {"sat": "{{ 1 }}", "targets": "{{ [entity] }}"}
    data = {"entity_id": "{{ entity }}", "hs_color": ["{{ value }}", "{{ sat }}"]}
    component = validate_component(
        _doc(inputs=inputs, outputs=_out(action="light.turn_on", data=data))
    )
    with pytest.raises(MakerError, match="uses"):
        check_component_templates(component)
    data = {"entity_id": "{{ entity }}", "brightness": "{{ targets | count }}"}
    component = validate_component(
        _doc(
            inputs=inputs,
            outputs=_out(
                action="light.turn_on", uses={"targets": "entities"}, data=data
            ),
        )
    )
    with pytest.raises(MakerError):
        check_component_templates(component)


def test_data_templates_see_options_can_vars_loops_and_option():
    """A data template may name params, options, can, vars, loops, value, option."""
    data = {
        "entity_id": "{{ entity }}",
        "effect": "{{ option }}",
        "transition": "{{ word ~ mode ~ can.x }}",
    }
    button = {"type": "button", "text": "Go", "on_tap": "run", "vars": {"mode": "heat"}}
    _check(_with_layout(button, outputs=_out(action="light.turn_on", data=data)))


def test_output_entity_through_a_loop():
    """entity_id may be a loop over devices; the loop's kinds are checked."""
    params = {"lights": {"domain": "light", "multiple": True}}
    data = {"entity_id": "{{ one }}"}
    row = {
        "type": "row",
        "for_each": "lights",
        "as": "one",
        "items": [{"type": "button", "text": "Go", "on_tap": "run"}],
    }
    validate_component(
        _with_layout(
            row,
            params=params,
            options={},
            inputs={},
            outputs=_out(action="light.toggle", data=data),
        )
    )
    _refused(
        _with_layout(
            row,
            params=params,
            options={},
            inputs={},
            outputs=_out(action="switch.toggle", data=data),
        ),
        "domain_mismatch",
    )
    _refused(
        _with_layout(
            {"type": "label", "text": "x"},
            params=params,
            options={},
            inputs={},
            outputs=_out(action="light.toggle", data=data),
        ),
        "unknown_param",
    )
    # A param with several devices may be the entity_id itself.
    validate_component(
        _doc(
            params=params,
            options={},
            inputs={},
            outputs=_out(action="light.toggle", data={"entity_id": "{{ lights }}"}),
        )
    )


def test_local_outputs():
    """Detail and back are local outputs of schema 2."""
    outputs = {"open": {"local": "detail"}, "leave": {"local": "back"}}
    component = validate_component(_doc(outputs=outputs))
    assert component["outputs"]["leave"] == {
        "kind": "local",
        "local": "back",
        "page": None,
    }
    _refused(_doc(outputs={"x": {"local": "fly"}}), "bad_value")
    _refused(_doc(outputs={"x": {"local": "back", "page": "home"}}), "bad_value")


# ---------------------------------------------------------------- tap and hold


def test_tap_choices():
    """The tap choices, their outputs and the detail page."""
    tap = _light()["tap"]
    component = validate_component(_light())
    assert component["tap"] == {
        "default": "toggle",
        "choices": [
            {
                "value": "toggle",
                "label": "Turns it on or off",
                "needs": "",
                "output": "toggle",
            },
            {"value": "detail", "label": "Opens its controls", "needs": ""},
            {"value": "none", "label": "Does nothing", "needs": ""},
        ],
    }
    for bad in (
        {"default": "fly", "choices": tap["choices"]},
        {"choices": {"page": {"label": "Page"}}},
        {"choices": {"other": {"label": "Other"}}},
        {"choices": {"toggle": {"label": "x", "output": "nothing"}}},
        {"choices": {"toggle": {"label": "x", "output": "toggle", "needs": "toggle"}}},
        {"choices": {}},
    ):
        doc = _light()
        doc["tap"] = bad
        with pytest.raises(MakerError):
            validate_component(doc)
    doc = _doc(tap={"choices": {"detail": {"label": "Opens"}}})
    _refused(doc, "bad_value", "tap.choices.detail")


def test_a_lock_may_not_be_a_card_tap():
    """An output on a lock or an alarm may not be a card tap, also through a map."""
    params = {"entity": {"domain": ["lock", "switch"]}}
    actions = {"lock": "lock.unlock", "switch": "switch.toggle"}
    outputs = _out(action=actions, feedback="confirm")
    tap = {"choices": {"toggle": {"label": "Toggles", "output": "run"}}}
    _refused(
        _doc(params=params, outputs=outputs, tap=tap),
        "action_not_allowed",
        "tap.choices.toggle.output",
    )


def test_hold_and_detail():
    """Hold is detail by default when the file has a detail variant."""
    doc = _doc(detail="tile")
    assert validate_component(doc)["hold"] == "detail"
    assert validate_component(_doc(detail="tile", hold="none"))["hold"] == "none"
    _refused(_doc(detail="large"), "bad_value", "detail")


# ---------------------------------------------------------------- variants


def test_variant_fields():
    """Header forms, trailing, picker, align and v1 per variant."""
    doc = _doc(on="is_on", detail="tile")
    doc["variants"]["tile"].update(
        header="tile", trailing="switch", align="top", v1="apollo/light-tile"
    )
    doc["variants"]["chip"] = {
        "name": "Chip",
        "grid": [12, 1],
        "header": "chip",
        "picker": False,
        "layout": [{"type": "label", "text": "x"}],
    }
    variants = validate_component(doc)["variants"]
    assert variants["tile"]["trailing"] == {"form": "switch"}
    assert variants["tile"]["align"] == "top"
    assert variants["tile"]["v1"] == "apollo/light-tile"
    assert variants["chip"]["picker"] is False


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"grid": [37, 3]}, "bad_value"),
        ({"grid": [6, 13]}, "bad_value"),
        ({"grid": [6]}, "bad_value"),
        ({"grid": [6, 1]}, "bad_value"),
        ({"header": "banner"}, "bad_value"),
        ({"trailing": "switch"}, "bad_value"),
        ({"header": "tile", "trailing": "switch"}, "bad_value"),
        ({"header": "tile", "trailing": "more"}, "bad_value"),
        ({"header": "tile", "trailing": "nothing"}, "bad_value"),
        ({"picker": False}, "bad_value"),
        ({"align": "bottom"}, "bad_value"),
        ({"v1": "Light"}, "bad_id"),
        ({"size": "1x1"}, "unknown_key"),
        ({"name": None}, "bad_value"),
    ],
)
def test_variant_refusals(change, code):
    """Bad variant fields are refused."""
    doc = _doc()
    doc["variants"]["tile"].update(change)
    _refused(doc, code)


def test_trailing_input_and_one_row_chip():
    """A trailing input on a tile header; a one-row card takes a chip."""
    doc = _doc()
    doc["variants"]["tile"].update(header="tile_v", trailing="pct")
    assert validate_component(doc)["variants"]["tile"]["trailing"] == {
        "form": "input",
        "input": "pct",
    }
    doc["variants"]["tile"] = {
        "name": "Chip",
        "grid": [12, 1],
        "header": "chip",
        "layout": [{"type": "label", "text": "x"}],
    }
    assert validate_component(doc)["size"] == [2, 1]


# ---------------------------------------------------------------- items


@pytest.mark.parametrize(
    ("item", "key", "expected"),
    [
        ({"type": "label", "text": "x", "size": "huge"}, "size", "huge"),
        ({"type": "label", "text": "x", "align": "centre"}, "align", "centre"),
        ({"type": "label", "clock": 24, "value": "pct"}, "clock", 24),
        (
            {"type": "label", "text": "x", "colour": "good"},
            "colour",
            {"form": "const", "value": "good"},
        ),
        (
            {"type": "label", "text": "x", "colour": "#ff453a"},
            "colour",
            {"form": "const", "value": "#FF453A"},
        ),
        (
            {"type": "label", "text": "x", "colour": "pct"},
            "colour",
            {"form": "input", "input": "pct"},
        ),
        (
            {"type": "label", "text": "x", "visible": "is_on"},
            "visible",
            {"form": "input", "input": "is_on"},
        ),
        ({"type": "label", "text": "x", "on_hold": "detail"}, "on_hold", "detail"),
        (
            {"type": "button", "text": "x", "on_tap": "toggle", "selected": "is_on"},
            "selected",
            {"form": "input", "input": "is_on"},
        ),
        (
            {
                "type": "button",
                "icon": "mdi:fire",
                "icon_live": "{{ 'mdi:fire' }}",
                "on_tap": "toggle",
            },
            "icon_live",
            {"form": "template", "template": "{{ 'mdi:fire' }}"},
        ),
        (
            {"type": "button", "text": "x", "on_tap": "toggle", "shape": "round"},
            "shape",
            "round",
        ),
        (
            {
                "type": "button",
                "icon": "mdi:fire",
                "on_tap": "toggle",
                "big_icon": True,
            },
            "big_icon",
            True,
        ),
        ({"type": "button", "text": "x", "on_tap": "detail"}, "on_tap", "detail"),
        (
            {"type": "switch", "value": "is_on", "colour": "accent"},
            "colour",
            {"form": "const", "value": "accent"},
        ),
        ({"type": "slider", "value": "pct", "look": "bar"}, "look", "bar"),
        ({"type": "slider", "value": "pct", "direction": "up"}, "direction", "up"),
        (
            {"type": "slider", "value": "pct", "track": ["#FF0000", "good"]},
            "track",
            {"kind": "colours", "colours": ["#FF0000", "good"]},
        ),
        (
            {"type": "slider", "value": "pct", "track": {"kelvin": [2000, 6500]}},
            "track",
            {
                "kind": "kelvin",
                "kelvin": [
                    {"form": "const", "value": 2000},
                    {"form": "const", "value": 6500},
                ],
            },
        ),
        (
            {"type": "slider", "value": "pct", "icon": "mdi:brightness-6"},
            "icon",
            {"form": "const", "value": "mdi:brightness-6"},
        ),
        ({"type": "slider", "value": "pct", "keep_active": True}, "keep_active", True),
        (
            {"type": "slider", "value": "pct", "rate": 1},
            "rate",
            {"form": "const", "value": 1.0},
        ),
        (
            {"type": "slider", "value": "pct", "rate": "pct"},
            "rate",
            {"form": "input", "input": "pct"},
        ),
        (
            {"type": "thermostat", "value": "pct", "colour": "warn"},
            "colour",
            {"form": "const", "value": "warn"},
        ),
        (
            {"type": "thermostat", "value": "pct", "mark": "pct"},
            "mark",
            {"form": "input", "input": "pct"},
        ),
        ({"type": "thermostat", "value": "pct", "buttons": 56}, "buttons", 56),
        ({"type": "chart", "value": "pct", "kind": "steps"}, "kind", "steps"),
        (
            {"type": "chart", "value": "pct", "mark": 20},
            "mark",
            {"form": "const", "value": 20.0},
        ),
        (
            {"type": "chart", "value": "pct", "colour": "info"},
            "colour",
            {"form": "const", "value": "info"},
        ),
        ({"type": "image", "value": "pct", "look": "badge"}, "look", "badge"),
        (
            {"type": "image", "value": "pct", "colour": "#000000"},
            "colour",
            {"form": "const", "value": "#000000"},
        ),
        (
            {"type": "choice", "options": "can.effect_list"},
            "options",
            {"kind": "fact", "fact": "can.effect_list"},
        ),
        (
            {"type": "choice", "options": "can.effect_list", "value": "pct"},
            "value",
            {"form": "input", "input": "pct"},
        ),
        ({"type": "choice", "options": "can.modes", "rows": 2}, "rows", 2),
        ({"type": "choice", "options": "can.modes", "look": "dots"}, "look", "dots"),
        (
            {
                "type": "choice",
                "options": "can.modes",
                "on_change": "dim",
                "confirm": "Sure?",
            },
            "confirm",
            {"form": "const", "value": "Sure?"},
        ),
    ],
)
def test_new_item_keys_accepted(item, key, expected):
    """Every new key of C.2.7 loads and is stored in its form."""
    doc = _with_layout(item, detail="tile")
    assert _item(doc)[key] == expected


def test_choice_options_forms():
    """A list of options, a list fact, or a colours or multiple-choice option."""
    entries = [
        {"value": "heat", "text": "Heat", "icon": "mdi:fire", "colour": "warn"},
        {"value": 2, "icon": "mdi:snowflake"},
        {"colour": "#00FF00"},
    ]
    item = _item(_with_layout({"type": "choice", "options": entries}))
    assert item["options"]["entries"][0] == {
        "value": "heat",
        "text": {"form": "const", "value": "Heat"},
        "icon": {"form": "const", "value": "mdi:fire"},
        "colour": {"form": "const", "value": "warn"},
    }
    light = validate_component(_light())
    assert light["parts"]["dots"]["options"] == {
        "kind": "option",
        "option": "favourites",
    }
    for bad in (
        "show_bar",
        "nothing",
        [],
        [{"value": "x"}],
        [{"text": "{{ states('sun.sun') }}"}],
        [{"value": "{{ x }}", "text": "x"}],
        [{"text": "x", "colour": "pink"}],
        [{"text": "x"}] * 17,
    ):
        with pytest.raises(MakerError):
            validate_component(_with_layout({"type": "choice", "options": bad}))


@pytest.mark.parametrize(
    "item",
    [
        {"type": "label", "text": "x", "size": "xs"},
        {"type": "label", "text": "x", "align": "middle"},
        {"type": "label", "text": "x", "clock": 13, "value": "pct"},
        {"type": "label", "clock": 24},
        {"type": "label", "text": "x", "value": "pct"},
        {"type": "label", "text": "x", "on_hold": "page"},
        {"type": "label", "text": "x", "colour": "pink"},
        {"type": "label", "text": "x", "visible": "nothing"},
        {"type": "button", "text": "x"},
        {"type": "button", "on_tap": "toggle", "icon_live": "pct"},
        {"type": "button", "text": "x", "on_tap": "toggle", "shape": "star"},
        {"type": "button", "text": "x", "on_tap": "toggle", "big_icon": 1},
        {
            "type": "button",
            "text": "x",
            "on_tap": "toggle",
            "icon": "{{ states('x') }}",
        },
        {"type": "button", "text": "x", "on_tap": "toggle", "icon": "pct"},
        {"type": "slider", "value": "pct", "on_hold": "detail"},
        {"type": "slider", "value": "pct", "look": "round"},
        {"type": "slider", "value": "pct", "direction": "left"},
        {"type": "slider", "value": "pct", "track": "rainbow"},
        {"type": "slider", "value": "pct", "track": ["#FF0000"]},
        {"type": "slider", "value": "pct", "track": ["#FF0000"] * 9},
        {"type": "slider", "value": "pct", "track": {"kelvin": [6500, 2000]}},
        {"type": "slider", "value": "pct", "track": {"kelvin": [2000, 60000]}},
        {
            "type": "slider",
            "value": "pct",
            "track": {"kelvin": ["{{ states('x') }}", 6500]},
        },
        {"type": "slider", "value": "pct", "keep_active": "yes"},
        {"type": "slider", "value": "pct", "on_change": "nothing"},
        {"type": "slider", "value": 5},
        {"type": "thermostat", "value": "pct", "buttons": 30},
        {"type": "thermostat", "value": "pct", "buttons": 65},
        {"type": "chart", "value": "pct", "kind": "pie"},
        {"type": "image", "value": "pct", "look": "round"},
        {"type": "choice", "options": "can.modes", "colour": "good"},
        {"type": "choice", "options": "can.modes", "rows": 5},
        {"type": "choice", "options": "can.modes", "look": "list"},
        {"type": "choice", "options": "can.modes", "confirm": "Sure?"},
        {"type": "choice"},
        {"type": "switch", "value": "is_on", "on_tap": "nothing"},
        {"type": "label", "text": "x", "for_each": "pct", "as": "x"},
        {"type": "label", "text": "x", "for_each": "word", "as": "x"},
        {"type": "label", "text": "x", "for_each": [1]},
        {"type": "label", "text": "x", "as": "x"},
        {"type": "label", "text": "x", "for_each": [{"a": {"b": 1}}], "as": "x"},
        {"type": "nothing"},
    ],
)
def test_item_refusals(item):
    """Bad values of the item keys are refused."""
    with pytest.raises(MakerError):
        validate_component(_with_layout(item))


def test_icon_live_needs_a_constant_icon():
    """A live icon is drawn over the constant one, which must be there."""
    _refused(
        _with_layout(
            {"type": "button", "text": "x", "on_tap": "toggle", "icon_live": "pct"}
        ),
        "missing_key",
        "variants.tile.layout.0.icon",
    )


def test_colour_role_that_is_also_an_input_is_refused():
    """A colour that is both a role name and an input is not guessed."""
    inputs = {"good": "{{ 1 }}"}
    _refused(
        _with_layout({"type": "label", "text": "x", "colour": "good"}, inputs=inputs),
        "bad_value",
    )


def test_on_tap_detail_needs_a_detail_variant():
    """An item that opens the detail page needs the file to have one."""
    _refused(
        _with_layout({"type": "button", "text": "x", "on_tap": "detail"}),
        "bad_value",
    )


# ---------------------------------------------------------------- field forms


def test_field_forms_are_marked_on_the_files_own_text():
    """Constant, lookup, template and input, decided once at load (C.2.7)."""
    entries = [{"icon": "mdi:fire", "text": "Heat"}]
    params = {"lights": {"domain": "light", "multiple": True}}
    layout = [
        {"type": "label", "text": "Plain {{ x"},
        {"type": "label", "text": "{{ word }}"},
        {"type": "label", "text": "{{ entity }}"},
        {"type": "label", "text": "{{ can.kind }}"},
        {"type": "label", "text": "{{ word | upper }}"},
        {"type": "label", "text": "{{ e.text }}", "for_each": entries, "as": "e"},
        {
            "type": "button",
            "text": "x",
            "icon": "{{ one_can.icon }}",
            "on_tap": "toggle",
            "for_each": "lights",
            "as": "one",
        },
        {
            "type": "button",
            "text": "{{ mode }}",
            "on_tap": "toggle",
            "vars": {"mode": "heat"},
        },
        {"type": "label", "text": "pct"},
    ]
    component = validate_component(_doc(params={**_doc()["params"], **params}))
    doc = _doc(params={**_doc()["params"], **params})
    doc["variants"]["tile"]["layout"] = layout
    items = validate_component(doc)["variants"]["tile"]["layout"]
    assert component
    forms = [item["text"] for item in items]
    assert forms[0] == {"form": "template", "template": "Plain {{ x"}
    assert forms[1] == {"form": "lookup", "name": "word", "key": None}
    assert forms[2] == {"form": "template", "template": "{{ entity }}"}
    assert forms[3] == {"form": "lookup", "name": "can", "key": "kind"}
    assert forms[4] == {"form": "template", "template": "{{ word | upper }}"}
    assert forms[5] == {"form": "lookup", "name": "e", "key": "text"}
    assert items[6]["icon"] == {"form": "lookup", "name": "one_can", "key": "icon"}
    assert forms[7] == {"form": "lookup", "name": "mode", "key": None}
    # Text is never an input by its name; that is for value-like keys.
    assert forms[8] == {"form": "const", "value": "pct"}


def test_can_needs_a_key():
    """{{ can }} alone is not a fact."""
    _refused(_with_layout({"type": "label", "text": "{{ can }}"}), "bad_value")


def test_a_loop_name_is_a_lookup_only_inside_its_loop():
    """Outside its loop a loop name is template text, rendered in the sandbox."""
    entries = [{"text": "a"}]
    layout = (
        {"type": "label", "text": "{{ e.text }}", "for_each": entries, "as": "e"},
        {"type": "label", "text": "{{ e.text }}"},
    )
    items = validate_component(_with_layout(*layout))["variants"]["tile"]["layout"]
    assert items[0]["text"]["form"] == "lookup"
    assert items[1]["text"]["form"] == "template"


# ---------------------------------------------------------------- template keys


NEW_TEMPLATE_KEYS = ("visible", "colour", "selected", "icon_live", "mark", "rate")


def test_both_template_key_lists_hold_the_new_keys():
    """schema.component_templates and templates._LAYOUT_KEYS read the same keys."""
    assert schema_module.TEMPLATE_ITEM_KEYS == templates_module._LAYOUT_KEYS
    assert set(NEW_TEMPLATE_KEYS) <= set(templates_module._LAYOUT_KEYS)
    assert schema_module.TEMPLATE_CARD_KEYS == templates_module._CARD_KEYS
    assert {"on", "tint", "unavailable"} <= set(templates_module._CARD_KEYS)


BROKEN = "{{ states( }}"


@pytest.mark.parametrize(
    "item",
    [
        {"type": "label", "text": "x", "visible": BROKEN},
        {"type": "label", "text": "x", "colour": BROKEN},
        {"type": "button", "text": "x", "on_tap": "toggle", "selected": BROKEN},
        {"type": "button", "icon": "mdi:fire", "on_tap": "toggle", "icon_live": BROKEN},
        {"type": "thermostat", "value": "pct", "mark": BROKEN},
        {"type": "slider", "value": "pct", "rate": BROKEN},
        {"type": "slider", "value": BROKEN},
        {"type": "slider", "value": "pct", "max": BROKEN},
        {"type": "label", "text": BROKEN},
        {"type": "button", "text": "x", "on_tap": "toggle", "confirm": BROKEN},
        {"type": "row", "items": [{"type": "label", "text": "x", "visible": BROKEN}]},
    ],
)
def test_templates_in_new_keys_are_checked(item):
    """A broken template in any templated key is found at load, also in a row."""
    component = validate_component(_with_layout(item))
    assert BROKEN in component_templates(component)
    with pytest.raises(MakerError) as info:
        check_component_templates(component)
    assert info.value.code == "bad_template"


@pytest.mark.parametrize("key", ["on", "tint", "state", "unavailable"])
def test_templates_in_card_keys_are_checked(key):
    """A broken template in a card-level key is found at load."""
    component = validate_component(_doc(**{key: BROKEN}))
    assert BROKEN in component_templates(component)
    with pytest.raises(MakerError):
        check_component_templates(component)


def test_templates_in_unused_parts_and_colour_lists_are_checked():
    """Parts that no variant uses and entries of a colour list are checked too."""
    component = validate_component(
        _doc(parts={"spare": {"type": "label", "text": BROKEN}})
    )
    with pytest.raises(MakerError):
        check_component_templates(component)
    data = {"entity_id": "{{ entity }}", "hs_color": ["{{ value }}", BROKEN]}
    component = validate_component(
        _doc(outputs=_out(action="light.turn_on", data=data))
    )
    assert BROKEN in component_templates(component)
    with pytest.raises(MakerError):
        check_component_templates(component)


def test_a_lookup_is_not_template_source():
    """A lookup field is never handed to the template checks."""
    component = validate_component(
        _with_layout({"type": "label", "text": "{{ word }}"})
    )
    assert "{{ word }}" not in component_templates(component)


# ---------------------------------------------------------------- preview


def test_preview():
    """Example values for params, options, facts and inputs, none included."""
    preview = validate_component(_light())["preview"]
    assert preview["can"]["min_kelvin"] == 2000
    assert preview["inputs"]["kelvin"] is None
    doc = _doc(preview={"options": {"word": "Hi"}, "params": {"entity": "light.a"}})
    assert validate_component(doc)["preview"]["options"] == {"word": "Hi"}
    for preview in (
        {"options": {"nothing": 1}},
        {"options": {"show_bar": "yes"}},
        {"inputs": {"nothing": 1}},
        {"params": {"entity": 5}},
        {"can": {"x": {"a": {"b": {"c": 1}}}}},
        {"style": {}},
    ):
        with pytest.raises(MakerError):
            validate_component(_doc(preview=preview))


# ---------------------------------------------------------------- the card path


def test_schema2_cards_wait_for_their_compiler():
    """Until the schema 2 compiler exists, such a card is left out with a reason."""
    component = validate_component(_light())
    with pytest.raises(MakerError) as info:
        validate_card_config(component, {"params": {"entity": "light.a"}})
    assert info.value.code == "not_supported"
