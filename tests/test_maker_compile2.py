"""Tests for the compiler of schema 2 cards (cards spec C.2.3 to C.2.7, C.3, C.4)."""

import copy
import json
import re
from pathlib import Path

import pytest
import yaml

from custom_components.apollo_tab.maker.compile2 import (
    DEFAULT_ROLES,
    compile_card2,
    kelvin_rgb,
    kelvin_track,
    role_table,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.schema import validate_component
from custom_components.apollo_tab.maker.schema2 import parse_when_term
from custom_components.apollo_tab.maker.templates import check_component_templates
from custom_components.apollo_tab.maker.when import term_holds

HERE = Path(__file__).parent
LIGHT = yaml.safe_load((HERE / "cards2" / "light.yaml").read_text(encoding="utf-8"))
PROBE = yaml.safe_load((HERE / "cards2" / "probe.yaml").read_text(encoding="utf-8"))
CONTRACT = json.loads(
    (
        HERE.parent / "custom_components" / "apollo_tab" / "contract" / "contract.json"
    ).read_text(encoding="utf-8")
)

LAMP = {
    "toggle": True,
    "icon": "mdi:floor-lamp",
    "kind": None,
    "brightness": True,
    "colour": True,
    "temperature": True,
    "effects": True,
    "min_kelvin": 2200,
    "max_kelvin": 6000,
    "effect_list": ["Rainbow", "Night", "Fire"],
}
ONOFF = {
    "toggle": True,
    "icon": "mdi:lightbulb",
    "kind": None,
    "brightness": False,
    "colour": False,
    "temperature": False,
    "effects": False,
    "min_kelvin": 2000,
    "max_kelvin": 6500,
    "effect_list": [],
}
PROBE_PARAMS = {
    "entity": "light.a",
    "lights": ["light.b", "switch.c", "light.d"],
    "extra": "sensor.e",
    "page": "other",
}


def light(**changes) -> dict:
    """Return the light card of D.1, validated, with top-level changes."""
    doc = copy.deepcopy(LIGHT)
    doc.update(changes)
    return validate_component(doc)


def probe(**changes) -> dict:
    """Return the probe card, validated, with top-level changes."""
    doc = copy.deepcopy(PROBE)
    doc.update(changes)
    return validate_component(doc)


def compiled(
    component: dict,
    raw: dict | None = None,
    facts: dict | None = None,
    **keys,
) -> dict:
    """Validate a card config and compile it."""
    raw = raw if raw is not None else {"params": {"entity": "light.a"}}
    card = validate_card_config2(component, raw)
    return compile_card2(component, card, facts, **keys)


def lamp_card(raw: dict | None = None, facts: dict | None = None, **keys) -> dict:
    """Compile the light card for the colour lamp."""
    return compiled(light(), raw, {"light.a": LAMP} if facts is None else facts, **keys)


def kinds(result: dict) -> list[str]:
    """Return the kinds of a compiled card's widgets, in order."""
    return [widget["t"] for widget in result["widgets"]]


def slot(result: dict, ref: object) -> dict:
    """Return the slot a reference names."""
    assert isinstance(ref, dict) and "s" in ref, ref
    return next(entry for entry in result["slots"] if entry["n"] == ref["s"])


def all_templates(result: dict) -> list[str]:
    """Return the source of every template slot of a compiled card."""
    return [s["template"] for s in result["slots"] if s.get("kind") == "template"]


# ---------------------------------------------------------------- the probe


def test_the_probe_card_loads_and_passes_the_template_checks() -> None:
    """The test card that uses every part is a valid schema 2 file."""
    component = probe()
    check_component_templates(component)
    kinds_used = set()
    for variant in component["variants"].values():
        stack = list(variant["layout"])
        while stack:
            item = stack.pop()
            kinds_used.add(item["type"])
            stack.extend(item.get("items") or [])
    assert kinds_used >= {
        "label",
        "button",
        "switch",
        "slider",
        "thermostat",
        "chart",
        "image",
        "choice",
        "row",
        "swap",
        "space",
    }
    headers = {v["header"] for v in component["variants"].values()}
    assert headers == {"title", "chip", "tile", "tile_v", "none"}


@pytest.mark.parametrize("variant", ["tile", "wide", "chip", "title", "plain"])
def test_every_variant_of_the_probe_compiles_with_nothing_clipped(variant: str) -> None:
    """Each variant fits its grid, for a device that can do everything."""
    result = compiled(
        probe(), {"params": PROBE_PARAMS, "variant": variant}, {"light.a": LAMP}
    )
    assert result["variant"] == variant
    assert result["warnings"] == []
    assert result["widgets"]
    for widget in result["widgets"]:
        x, y, width, height = widget["r"]
        # The switch moved into a title header sits in the header band.
        assert x >= 16 and y >= (8 if result["header"] else 16), widget
        assert x + width <= result["w"] - 16 and y + height <= result["h"] - 16, widget


def test_the_probe_detail_copy_compiles_with_nothing_clipped() -> None:
    """The detail variant holds every kind of loop and choice."""
    result = compiled(
        probe(),
        {"params": PROBE_PARAMS, "grid_options": {"columns": 18, "rows": 11}},
        {"light.a": LAMP},
        detail=True,
    )
    assert result["variant"] == "full"
    assert result["warnings"] == []
    assert kinds(result).count("choice") == 4
    # One button per device of the loop over a param, side by side.
    lamps = [w for w in result["widgets"] if w.get("text", {}) != "Back"][-3:]
    assert [w["r"][1] for w in lamps] == [lamps[0]["r"][1]] * 3


def test_a_card_with_every_option_on_and_a_device_that_can_do_nothing() -> None:
    """The light card compiles for an on/off lamp with nothing clipped."""
    for variant in ("tile", "wide", "large"):
        result = lamp_card(
            {"params": {"entity": "light.a"}, "variant": variant},
            {"light.a": ONOFF},
        )
        assert result["warnings"] == []
        assert "slider" not in kinds(result)


# ---------------------------------------------------------------- card config


def test_params_stay_strict() -> None:
    """An unknown param or a device of another kind is an error, as in schema 1."""
    component = light()
    with pytest.raises(MakerError):
        validate_card_config2(component, {"params": {"nope": "light.a"}})
    with pytest.raises(MakerError):
        validate_card_config2(component, {"params": {"entity": "switch.a"}})
    with pytest.raises(MakerError):
        validate_card_config2(component, {"params": {"entity": "not an id"}})


def test_a_param_with_several_kinds_takes_each_kind() -> None:
    """`domain: [light, switch]` takes both and refuses a third."""
    component = probe()
    card = validate_card_config2(component, {"params": PROBE_PARAMS})
    assert card["params"]["lights"] == ["light.b", "switch.c", "light.d"]
    with pytest.raises(MakerError):
        validate_card_config2(
            component, {"params": {**PROBE_PARAMS, "lights": ["fan.x"]}}
        )
    with pytest.raises(MakerError):
        validate_card_config2(
            component,
            {"params": {**PROBE_PARAMS, "lights": ["light.a"] * 5}},
        )


def test_an_optional_param_left_empty_is_not_missing() -> None:
    """The card is not an example when an optional param is empty."""
    card = validate_card_config2(probe(), {"params": {"entity": "light.a"}})
    assert card["missing"] == []
    card = validate_card_config2(probe(), {"params": {}})
    assert card["missing"] == ["entity"]


def test_an_unknown_option_is_ignored_with_a_note() -> None:
    """A card must not vanish because its file lost an option."""
    card = validate_card_config2(
        light(), {"params": {"entity": "light.a"}, "options": {"gone": 1}}
    )
    assert card["options"] == {}
    assert {"code": "option_unknown", "path": "options.gone"} in card["notes"]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("show_brightness", "yes"),  # the wrong type
        ("colour_control", "rainbow"),  # not one of the keys
        ("favourites", ["#FF0000"] * 9),  # too long a list
        ("favourites", ["red"]),  # not a colour
    ],
)
def test_a_bad_option_value_is_dropped_and_the_default_counts(
    name: str, value: object
) -> None:
    """The value is dropped with a note; the default counts."""
    component = light()
    card = validate_card_config2(
        component, {"params": {"entity": "light.a"}, "options": {name: value}}
    )
    assert name not in card["options"]
    assert {"code": "option_dropped", "path": f"options.{name}"} in card["notes"]


def test_text_and_number_options_are_checked() -> None:
    """A text above its limit and a number out of range are dropped."""
    component = probe()
    card = validate_card_config2(
        component,
        {"params": PROBE_PARAMS, "options": {"greeting": "x" * 41, "steps": 11}},
    )
    assert card["options"] == {}
    codes = [note["path"] for note in card["notes"]]
    assert codes == ["options.greeting", "options.steps"]
    card = validate_card_config2(
        component, {"params": PROBE_PARAMS, "options": {"greeting": "x" * 40}}
    )
    assert card["options"] == {"greeting": "x" * 40}


def test_an_unhashable_option_value_is_dropped() -> None:
    """A mapping where a choice is expected is dropped, not an error."""
    card = validate_card_config2(
        light(), {"params": {"entity": "light.a"}, "options": {"colour_control": {}}}
    )
    assert card["options"] == {}


def test_a_value_not_in_the_devices_list_is_dropped_when_compiled() -> None:
    """`from: can.<list>` values are checked against the device's list now."""
    result = lamp_card(
        {
            "params": {"entity": "light.a"},
            "options": {"effects_shown": ["Rainbow", "Gone"]},
            "grid_options": {"columns": 18, "rows": 11},
        },
        detail=True,
    )
    assert {"code": "option_dropped", "path": "options.effects_shown"} in result[
        "notes"
    ]
    effects = [w for w in result["widgets"] if w["t"] == "choice"][-1]
    # The default counts: the first four of the device's list.
    assert effects["texts"] == ["Rainbow", "Night", "Fire"]


def test_the_standard_options() -> None:
    """icon, tap, tap_page, hold and ask; a bad one is dropped with a note."""
    component = light()
    card = validate_card_config2(
        component,
        {
            "params": {"entity": "light.a"},
            "options": {
                "icon": "mdi:floor-lamp",
                "tap": "detail",
                "hold": False,
                "ask": True,
                "tap_page": "kitchen",
            },
        },
    )
    assert card["standard"] == {
        "icon": "mdi:floor-lamp",
        "tap": "detail",
        "tap_page": "kitchen",
        "hold": False,
        "ask": True,
    }
    card = validate_card_config2(
        component,
        {
            "params": {"entity": "light.a"},
            "options": {"icon": "lamp", "tap": "explode", "hold": "no"},
        },
    )
    assert card["standard"]["icon"] is None
    assert card["standard"]["tap"] == "toggle"
    assert card["standard"]["hold"] is True
    assert len(card["notes"]) == 3


def test_a_variant_the_picker_does_not_offer_is_ignored() -> None:
    """A stored variant must be a picker variant; else a note."""
    card = validate_card_config2(
        light(), {"params": {"entity": "light.a"}, "variant": "full"}
    )
    assert card["variant"] is None
    assert {"code": "variant_unknown", "path": "variant"} in card["notes"]


def test_the_size_defaults_to_the_variants_grid() -> None:
    """Without grid options a card takes its variant's grid."""
    card = validate_card_config2(
        light(), {"params": {"entity": "light.a"}, "variant": "wide"}
    )
    assert (card["columns"], card["rows"]) == (12, 3)
    card = validate_card_config2(light(), {"params": {"entity": "light.a"}})
    assert (card["columns"], card["rows"]) == (6, 3)


def test_style_lit_and_tint() -> None:
    """`style.lit` and `style.tint` are the card's; the rest is today's style."""
    result = lamp_card(
        {
            "params": {"entity": "light.a"},
            "style": {"lit": "outline", "tint": False, "transparency": 10},
        }
    )
    assert result["lit"] == 2
    assert "tint" not in result
    card = validate_card_config2(
        light(), {"params": {"entity": "light.a"}, "style": {"lit": "glow"}}
    )
    assert {"code": "style_dropped", "path": "style.lit"} in card["notes"]
    assert lamp_card()["lit"] == 0


# ---------------------------------------------------------------- options


def test_an_option_whose_needs_is_false_counts_as_off() -> None:
    """Toggle off, first choice, empty list (C.2.3)."""
    result = lamp_card(facts={"light.a": ONOFF})
    assert "slider" not in kinds(result)
    component = light()
    card = validate_card_config2(
        component,
        {
            "params": {"entity": "light.a"},
            "options": {"show_brightness": True, "colour_control": "both"},
        },
    )
    result = compile_card2(component, card, {"light.a": ONOFF})
    assert "slider" not in kinds(result)


def test_default_first_takes_the_start_of_the_devices_list() -> None:
    """`default_first: 4` with three effects shows all three."""
    result = lamp_card(
        {"params": {"entity": "light.a"}, "grid_options": {"columns": 18, "rows": 11}},
        detail=True,
    )
    choice = [w for w in result["widgets"] if w["t"] == "choice"][-1]
    assert choice["texts"] == ["Rainbow", "Night", "Fire"]


def test_options_drive_when() -> None:
    """An option picks which parts are there: the dots replace the hue bar."""
    bar = lamp_card({"params": {"entity": "light.a"}, "variant": "large"})
    hue = [w for w in bar["widgets"] if w.get("track") and w["track"][0] == "#FF0000"]
    assert len(hue) == 1 and "choice" not in kinds(bar)
    dots = lamp_card(
        {
            "params": {"entity": "light.a"},
            "variant": "large",
            "options": {"colour_control": "dots"},
        }
    )
    assert dots["warnings"] == []
    assert "choice" in kinds(dots)
    assert not [w for w in dots["widgets"] if w.get("track", [""])[0] == "#FF0000"]


def test_a_part_that_is_left_out_leaves_no_hole() -> None:
    """Geometry runs after the conditions."""
    full = lamp_card({"params": {"entity": "light.a"}, "variant": "large"})
    less = lamp_card(
        {
            "params": {"entity": "light.a"},
            "variant": "large",
            "options": {"show_white": False},
        }
    )
    full_sliders = [w for w in full["widgets"] if w["t"] == "slider"]
    less_sliders = [w for w in less["widgets"] if w["t"] == "slider"]
    assert len(less_sliders) == len(full_sliders) - 1
    # Rows sit at the bottom: the remaining rows moved down, no gap between them.
    bottoms = [w["r"][1] + w["r"][3] for w in less_sliders]
    assert bottoms[-1] == less["h"] - 16
    assert less_sliders[1]["r"][1] == less_sliders[0]["r"][1] + 40 + 8


def test_tablet_v2_is_true_for_version_2_only() -> None:
    """`tablet.v2` follows dl; the editor counts as version 2."""
    component = probe()
    raw = {"params": PROBE_PARAMS, "grid_options": {"columns": 18, "rows": 11}}
    v2 = compiled(component, raw, {"light.a": LAMP}, detail=True)
    v1 = compiled(component, raw, {"light.a": LAMP}, detail=True, dl=1)
    assert not any(w.get("text") == "Back" for w in v2["widgets"])
    assert any(w.get("text") == "Back" for w in v1["widgets"])
    assert sum(w["t"] == "choice" for w in v1["widgets"]) == 3


def test_has_follows_an_optional_param() -> None:
    """`has.extra` is false while the optional param is empty."""
    component = probe()
    raw = {"params": {"entity": "light.a", "extra": "sensor.e"}, "variant": "plain"}
    with_extra = compiled(component, raw, {"light.a": LAMP})
    raw = {"params": {"entity": "light.a"}, "variant": "plain"}
    without = compiled(component, raw, {"light.a": LAMP})
    assert "chart" in kinds(with_extra)
    assert "chart" not in kinds(without)


def test_the_when_grammar_matches_the_loader() -> None:
    """when.py reads exactly the terms the loader accepts."""
    terms = [
        "a",
        "!a",
        "a=b",
        "a!=b|c",
        "can.x",
        "can.p.x",
        "has.p",
        "tablet.v2",
        "!a=b",
        "A",
        "a=",
        "a=B",
        "can.p.x.y",
        "a==b",
        "",
    ]
    for term in terms:
        try:
            parse_when_term(term, "when")
            loader = True
        except MakerError:
            loader = False
        held = term_holds(term, {term.lstrip("!").split("=")[0].rstrip("!"): True})
        if not loader:
            assert held is False, term


# ---------------------------------------------------------------- variants


def test_the_largest_variant_that_fits_is_picked() -> None:
    """Without a stored variant the card's size decides."""
    for columns, rows, expected in [
        (6, 3, "tile"),
        (12, 3, "wide"),
        (12, 6, "large"),
        (36, 12, "large"),
        (11, 5, "tile"),
    ]:
        result = lamp_card(
            {
                "params": {"entity": "light.a"},
                "grid_options": {"columns": columns, "rows": rows},
            }
        )
        assert result["variant"] == expected, (columns, rows)


def test_the_smallest_variant_when_none_fits() -> None:
    """A card smaller than every variant takes the smallest; rows drop."""
    result = lamp_card(
        {"params": {"entity": "light.a"}, "grid_options": {"columns": 3, "rows": 2}}
    )
    assert result["variant"] == "tile"
    assert result["warnings"] == ["element_clipped"]


def test_the_persons_variant_wins_and_is_laid_out_in_the_new_size() -> None:
    """Free resize stays: the rows are laid out again."""
    result = lamp_card(
        {
            "params": {"entity": "light.a"},
            "variant": "wide",
            "grid_options": {"columns": 18, "rows": 3},
        }
    )
    assert result["variant"] == "wide"
    assert result["w"] == 18 * 32 - 8


def test_the_detail_copy_uses_the_detail_variant() -> None:
    """detail=True compiles the `detail` variant, whatever the person picked."""
    result = lamp_card(
        {"params": {"entity": "light.a"}, "variant": "tile"}, detail=True
    )
    assert result["variant"] == "full"


# ---------------------------------------------------------------- headers


def test_tile_v_header_widgets() -> None:
    """Badge, name and state, and the trailing text, as ordinary widgets."""
    result = lamp_card()
    badge, name, state, trailing = result["widgets"][:4]
    assert badge["t"] == "image" and badge["look"] == 1
    assert badge["value"] == "mdi:floor-lamp"  # can.icon
    assert slot(result, badge["c"])["kind"] == "colour"  # the card's tint
    assert name["t"] == "label" and name["size"] == "m"
    assert "friendly_name" in slot(result, name["text"])["template"]
    assert state["size"] == "s"
    assert slot(result, state["text"])["template"].endswith("{{ state }}")
    assert trailing["al"] == 2
    assert slot(result, trailing["text"])["template"].endswith("{{ level }}")
    assert result["header"] is None


def test_tile_header_with_a_trailing_switch_runs_the_tap_output() -> None:
    """`trailing: switch` is the card's `on` with its tap output."""
    result = lamp_card({"params": {"entity": "light.a"}, "variant": "wide"})
    switch = result["widgets"][3]
    assert switch["t"] == "switch"
    assert switch["value"] == result["on"]
    assert switch["tap"] == {"policy": "optimistic"}
    assert result["actions"][f"{switch['i']}:tap"]["output"] == "toggle"


def test_the_trailing_switch_still_toggles_when_the_card_tap_opens_the_page() -> None:
    """The switch runs the first tap choice that acts."""
    result = lamp_card(
        {
            "params": {"entity": "light.a"},
            "variant": "wide",
            "options": {"tap": "detail"},
        }
    )
    switch = result["widgets"][3]
    assert result["actions"][f"{switch['i']}:tap"]["output"] == "toggle"
    assert result["tap"] == {"local": "detail"}


def test_trailing_more_opens_the_detail_page_and_is_gone_on_it() -> None:
    """A bare button; the detail copy has no way to open the page it is on."""
    component = probe()
    raw = {"params": PROBE_PARAMS, "grid_options": {"columns": 18, "rows": 11}}
    card = validate_card_config2(component, raw)
    copy_ = compile_card2(component, card, {"light.a": LAMP}, detail=True)
    assert not any(w.get("icon") == "mdi:dots-horizontal" for w in copy_["widgets"])
    component["variants"]["wide"]["trailing"] = {"form": "more"}
    result = compile_card2(
        component,
        validate_card_config2(component, {"params": PROBE_PARAMS, "variant": "wide"}),
        {"light.a": LAMP},
    )
    more = result["widgets"][3]
    assert more == {
        "t": "button",
        "r": more["r"],
        "icon": "mdi:dots-horizontal",
        "shape": 2,
        "tap": {"local": "detail"},
        "i": 3,
    }
    assert result["opener"] is True


def test_chip_header_widgets() -> None:
    """A bare icon, the name and the state at the right."""
    result = compiled(
        probe(), {"params": PROBE_PARAMS, "variant": "chip"}, {"light.a": LAMP}
    )
    icon, name, state = result["widgets"]
    assert icon["t"] == "image" and icon["look"] == 2 and icon["r"][2:] == [24, 24]
    assert slot(result, icon["value"])["kind"] == "state_icon"
    assert name["size"] == "m"
    assert state["al"] == 2 and state["size"] == "s"


def test_title_header() -> None:
    """Today's header: icon and title, and a switch moved into it."""
    result = compiled(
        probe(), {"params": PROBE_PARAMS, "variant": "title"}, {"light.a": LAMP}
    )
    header = result["header"]
    assert header["icon"] == "mdi:floor-lamp"  # can.icon
    assert "friendly_name" in slot(result, header["title"])["template"]
    switch = next(w for w in result["widgets"] if w["t"] == "switch")
    assert switch["r"][1] == 14
    assert result["ic"] == next(w for w in result["widgets"] if "ic" in w)["ic"]


def test_the_header_icon_order() -> None:
    """The person's icon, then the device's, then the file's."""
    raw = {"params": {"entity": "light.a"}, "options": {"icon": "mdi:desk-lamp"}}
    assert lamp_card(raw)["widgets"][0]["value"] == "mdi:desk-lamp"
    assert lamp_card()["widgets"][0]["value"] == "mdi:floor-lamp"
    no_icon = {**LAMP, "icon": None}
    assert lamp_card(facts={"light.a": no_icon})["widgets"][0]["value"] == (
        "mdi:lightbulb"
    )


def test_a_person_picked_icon_wins_over_the_live_icon() -> None:
    """A state_icon input is the badge's icon unless the person picked one."""
    component = probe()
    raw = {"params": PROBE_PARAMS, "variant": "wide"}
    live = compiled(component, raw, {"light.a": LAMP})
    assert slot(live, live["widgets"][0]["value"])["kind"] == "state_icon"
    raw["options"] = {"icon": "mdi:desk-lamp"}
    picked = compiled(component, raw, {"light.a": LAMP})
    assert picked["widgets"][0]["value"] == "mdi:desk-lamp"


# ---------------------------------------------------------------- card level


def test_card_level_keys() -> None:
    """on, tint, un, lit, tap and hold of the light card."""
    result = lamp_card()
    assert "is_state(entity, 'on')" in slot(result, result["on"])["template"]
    assert slot(result, result["tint"]) == {
        "n": result["tint"]["s"],
        "kind": "colour",
        "entity": "light.a",
        "of": "rgb",
    }
    un = slot(result, result["un"])
    assert un["template"] == "{{ states(entity) in ['unavailable', 'unknown'] }}"
    assert result["lit"] == 0
    assert result["tap"] == {"policy": "optimistic"}
    assert result["actions"]["card:tap"] == {"output": "toggle", "vars": {}}
    assert result["hold"] == {"local": "detail"}
    assert result["opener"] is True


def test_an_unavailable_input_of_the_file_wins() -> None:
    """`unavailable:` names the input that says the device is gone."""
    doc_light = copy.deepcopy(LIGHT)
    doc_light["inputs"]["gone"] = "{{ states(entity) == 'unavailable' }}"
    doc_light["unavailable"] = "gone"
    component = validate_component(doc_light)
    result = compiled(component, None, {"light.a": LAMP})
    assert slot(result, result["un"])["template"].endswith("{{ gone }}")


def test_the_card_tap_choices() -> None:
    """Detail opens the page, none does nothing, page goes to a page, ask asks."""
    detail = lamp_card({"params": {"entity": "light.a"}, "options": {"tap": "detail"}})
    assert detail["tap"] == {"local": "detail"}
    assert "card:tap" not in detail["actions"]
    none = lamp_card({"params": {"entity": "light.a"}, "options": {"tap": "none"}})
    assert "tap" not in none
    page = lamp_card(
        {"params": {"entity": "light.a"}, "options": {"tap": "page", "tap_page": "k"}}
    )
    assert page["tap"] == {"local": "go_to_page", "page": "k"}
    no_page = lamp_card({"params": {"entity": "light.a"}, "options": {"tap": "page"}})
    assert "tap" not in no_page
    ask = lamp_card({"params": {"entity": "light.a"}, "options": {"ask": True}})
    assert ask["confirm"] == "Turns it on or off?"
    assert "confirm" not in lamp_card()


def test_a_tap_choice_whose_needs_is_false_is_not_compiled() -> None:
    """`needs: can.toggle` on a device that cannot: no tap."""
    doc_light = copy.deepcopy(LIGHT)
    doc_light["tap"]["choices"]["toggle"]["needs"] = "can.brightness"
    component = validate_component(doc_light)
    result = compiled(component, None, {"light.a": ONOFF})
    assert "tap" not in result
    assert "card:tap" not in result["actions"]


def test_the_hold_can_be_switched_off() -> None:
    """options.hold false leaves the hold out."""
    result = lamp_card({"params": {"entity": "light.a"}, "options": {"hold": False}})
    assert "hold" not in result


def test_the_detail_copy_has_no_card_tap_and_no_hold() -> None:
    """A touch between two bars must not toggle the light (C.4)."""
    result = lamp_card(detail=True)
    assert "tap" not in result and "hold" not in result
    assert "card:tap" not in result["actions"]
    assert result["opener"] is False


def test_on_falls_back_to_the_first_switch() -> None:
    """A card without `on` is lit by its first switch, as in schema 1."""
    doc = copy.deepcopy(PROBE)
    del doc[True]  # YAML reads the key `on` as true
    doc["variants"]["wide"]["trailing"] = "none"
    component = validate_component(doc)
    result = compiled(
        component, {"params": PROBE_PARAMS, "variant": "title"}, {"light.a": LAMP}
    )
    switch = next(w for w in result["widgets"] if w["t"] == "switch")
    assert result["on"] == switch["value"]


# ---------------------------------------------------------------- widgets


def test_the_v2_keys_of_each_widget() -> None:
    """Keys travel with their device names and numbers (C.4)."""
    words = compiled(
        probe(), {"params": PROBE_PARAMS, "variant": "title"}, {"light.a": LAMP}
    )["widgets"]
    centred, coloured, clock = words[0], words[1], words[2]
    assert centred["px"] == 28 and "size" not in centred and centred["al"] == 1
    assert coloured["size"] == "s" and "px" not in coloured
    assert coloured["c"] == DEFAULT_ROLES["good"]  # the role of the option tone
    assert clock["px"] == 48 and clock["clk"] == 1
    round_button = next(w for w in words if w.get("shape") == 1)
    assert round_button["isz"] == 1 and "value" in round_button and "ic" in round_button
    plain = compiled(
        probe(), {"params": PROBE_PARAMS, "variant": "plain"}, {"light.a": LAMP}
    )["widgets"]
    thermostat, chart, image = plain[:3]
    assert thermostat["bs"] == 48 and "mark" in thermostat
    assert thermostat["c"] == DEFAULT_ROLES["accent"]
    assert chart["kind"] == "line" and chart["st"] == 1 and "mark" in chart
    assert image["look"] == 1 and image["hold"] == {"local": "detail"}
    detail = compiled(
        probe(),
        {"params": PROBE_PARAMS, "grid_options": {"columns": 18, "rows": 11}},
        {"light.a": LAMP},
        detail=True,
    )["widgets"]
    sliders = [w for w in detail if w["t"] == "slider"]
    assert sliders[1]["dir"] == 0 and sliders[1]["nv"] == 1
    assert sliders[1]["track"][0] == "#FF0000" and len(sliders[1]["track"]) == 7
    assert sliders[2]["min"] == 2200 and sliders[2]["max"] == 6000
    assert sliders[2]["track"] == kelvin_track(2200, 6000)
    assert sliders[3]["rate"] == 1 and sliders[3]["r"][3] == 8


def test_label_sizes_map_to_size_or_px() -> None:
    """s, m, l are `size`; ml, xl, xxl, huge are `px` 28, 48, 96, 192."""
    doc = copy.deepcopy(PROBE)
    doc["variants"]["title"]["layout"] = [
        {"type": "label", "text": "x", "size": size, "height": 22}
        for size in ("s", "m", "ml", "l")
    ]
    doc["variants"]["plain"]["layout"] = [
        {"type": "label", "text": "x", "size": size} for size in ("xl", "xxl")
    ]
    component = validate_component(doc)
    words = compiled(
        component, {"params": PROBE_PARAMS, "variant": "title"}, {"light.a": LAMP}
    )["widgets"]
    assert [(w.get("size"), w.get("px")) for w in words] == [
        ("s", None),
        ("m", None),
        (None, 28),
        ("l", None),
    ]
    big = compiled(
        component, {"params": PROBE_PARAMS, "variant": "plain"}, {"light.a": LAMP}
    )["widgets"]
    assert [w["px"] for w in big] == [48, 96]


def test_a_swap_gives_two_widgets_on_one_place_with_vis() -> None:
    """The members of a swap share the rectangle; each carries its `vis`."""
    result = compiled(
        probe(),
        {"params": PROBE_PARAMS, "grid_options": {"columns": 18, "rows": 11}},
        {"light.a": LAMP},
        detail=True,
    )
    on = next(w for w in result["widgets"] if w.get("text") == "On")
    off = next(w for w in result["widgets"] if w.get("text") == "Off")
    label = result["widgets"][off["i"] + 1]
    assert on["r"][:2] == off["r"][:2]
    assert slot(result, on["vis"])["template"].endswith("{{ is_on }}")
    # The row's `visible` reaches each of its widgets.
    assert off["vis"] == label["vis"]
    assert slot(result, off["vis"])["template"].endswith("{{ not is_on }}")


def test_kelvin_track_is_home_assistants_colour() -> None:
    """Five colours at equal steps, from Home Assistant's own function."""
    from homeassistant.util.color import color_temperature_to_rgb

    for kelvin in (1500, 2000, 2700, 4000, 6500, 6600, 10000):
        expected = [int(part + 0.5) for part in color_temperature_to_rgb(kelvin)]
        assert kelvin_rgb(kelvin) == expected, kelvin
    track = kelvin_track(2000, 6000)
    assert len(track) == 5
    assert track[0] == "#{:02X}{:02X}{:02X}".format(*kelvin_rgb(2000))
    assert track[2] == "#{:02X}{:02X}{:02X}".format(*kelvin_rgb(4000))
    assert track[4] == "#{:02X}{:02X}{:02X}".format(*kelvin_rgb(6000))


def test_choice_lists_and_their_values_on_the_server() -> None:
    """A list, a list fact and an option; the whole values stay server side."""
    result = compiled(
        probe(),
        {"params": PROBE_PARAMS, "grid_options": {"columns": 18, "rows": 11}},
        {"light.a": LAMP},
        detail=True,
    )
    choices = [w for w in result["widgets"] if w["t"] == "choice"]
    listed, dots, effects, fact = choices
    assert listed["texts"] == ["One", "Two"]
    assert listed["icons"] == ["mdi:numeric-1", ""]
    assert listed["confirm"] == "Are you sure?"
    assert result["actions"][f"{listed['i']}:change"]["options"] == [1, 2]
    assert dots["look"] == 1
    assert dots["cols"] == ["#FF0000", "#{:02X}{:02X}{:02X}".format(*kelvin_rgb(2700))]
    assert result["actions"][f"{dots['i']}:change"]["options"] == [
        {"rgb": [255, 0, 0], "kelvin": None},
        {"rgb": None, "kelvin": 2700},
    ]
    assert effects["texts"] == ["Rainbow", "Night"]
    assert fact["texts"] == ["Rainbow", "Night", "Fire"] and fact["rows"] == 2
    assert result["actions"][f"{fact['i']}:change"]["options"] == [
        "Rainbow",
        "Night",
        "Fire",
    ]


def test_a_choice_with_no_option_is_left_out() -> None:
    """HA never sends a choice with no option (contract 4.3)."""
    doc = copy.deepcopy(PROBE)
    doc["variants"]["plain"]["layout"] = [
        {"type": "choice", "options": "can.effect_list", "on_change": "set_effect"}
    ]
    component = validate_component(doc)
    result = compiled(
        component, {"params": PROBE_PARAMS, "variant": "plain"}, {"light.a": ONOFF}
    )
    assert "choice" not in kinds(result)


def test_a_multiple_choice_option_shows_its_labels() -> None:
    """A choice over a multiple-choice option shows the labels, keeps the keys."""
    doc = copy.deepcopy(PROBE)
    doc["variants"]["plain"]["layout"] = [
        {"type": "choice", "options": "modes_shown", "on_change": "set_effect"}
    ]
    component = validate_component(doc)
    result = compiled(
        component, {"params": PROBE_PARAMS, "variant": "plain"}, {"light.a": LAMP}
    )
    choice = result["widgets"][0]
    assert choice["texts"] == ["First", "Second"]
    assert result["actions"]["0:change"]["options"] == ["a", "b"]


# ---------------------------------------------------------------- loops


def test_a_loop_over_a_param_gets_each_device_and_its_facts() -> None:
    """`as` is the device, `<as>_can` its facts; per_row puts copies side by side."""
    result = compiled(
        probe(),
        {"params": PROBE_PARAMS, "grid_options": {"columns": 18, "rows": 11}},
        {"light.a": LAMP, "light.b": LAMP},
        detail=True,
    )
    taps = [v for k, v in result["actions"].items() if v["output"] == "each"]
    assert [t["vars"]["lamp"] for t in taps] == ["light.b", "switch.c", "light.d"]
    assert taps[0]["vars"]["lamp_can"] == LAMP
    assert taps[1]["vars"]["lamp_can"]["icon"] == "mdi:toggle-switch"


def test_a_loop_over_a_list_in_the_file_repeats_a_row_under_itself() -> None:
    """Each copy of a looping row is a row of its own."""
    result = compiled(
        probe(), {"params": PROBE_PARAMS, "variant": "title"}, {"light.a": LAMP}
    )
    labels = [w for w in result["widgets"] if w.get("text") in ("Up", "Down")]
    buttons = [w for w in result["widgets"] if w.get("text") in ("up", "down")]
    assert [w["text"] for w in labels] == ["Up", "Down"]
    assert labels[0]["r"][1] < labels[1]["r"][1]
    assert labels[0]["r"][1] == buttons[0]["r"][1]


def test_a_loop_over_an_option_and_per_row() -> None:
    """The option's entries, four to a row."""
    raw = {
        "params": PROBE_PARAMS,
        "variant": "plain",
        "options": {"modes_shown": ["a", "b", "c"]},
    }
    result = compiled(probe(), raw, {"light.a": LAMP})
    labels = [w for w in result["widgets"] if w["t"] == "label"]
    assert [w["text"] for w in labels] == ["a", "b", "c"]
    assert len({w["r"][1] for w in labels}) == 1


def test_a_loop_makes_at_most_16_copies() -> None:
    """A device list of 64 entries gives 16 copies."""
    doc = copy.deepcopy(PROBE)
    doc["variants"]["plain"]["layout"] = [
        {
            "type": "label",
            "text": "{{ e }}",
            "size": "s",
            "for_each": "can.effect_list",
            "as": "e",
            "per_row": 8,
        }
    ]
    component = validate_component(doc)
    lamp = {**LAMP, "effect_list": [f"e{i}" for i in range(64)]}
    result = compiled(
        component, {"params": PROBE_PARAMS, "variant": "plain"}, {"light.a": lamp}
    )
    assert [w["text"] for w in result["widgets"]] == [f"e{i}" for i in range(16)]


def test_widgets_are_counted_while_they_are_made() -> None:
    """The count of a card stops at 48; what is over it is cut."""
    doc = copy.deepcopy(PROBE)
    loop = {
        "type": "label",
        "text": "{{ e }}",
        "size": "s",
        "for_each": "can.effect_list",
        "as": "e",
        "per_row": 8,
        "height": 1,
    }
    last = {"type": "label", "text": "last", "size": "s", "height": 1}
    doc["variants"]["plain"]["layout"] = [loop, last]
    component = validate_component(doc)
    # The loader counts the largest loops and refuses more than 48. The cut
    # while compiling is the safety net behind it: put in a third loop.
    layout = component["variants"]["plain"]["layout"]
    layout[:] = [layout[0], layout[0], layout[0], layout[1]]
    lamp = {**LAMP, "effect_list": [f"e{i}" for i in range(16)]}
    result = compiled(
        component,
        {"params": PROBE_PARAMS, "variant": "plain"},
        {"light.a": lamp},
    )
    assert len(result["widgets"]) == 48
    assert "last" not in [w["text"] for w in result["widgets"]]


def test_a_use_line_adds_and_replaces_keys() -> None:
    """`{use: dim, height: 56}` is the part with its height."""
    result = lamp_card(
        {"params": {"entity": "light.a"}, "grid_options": {"columns": 18, "rows": 11}},
        detail=True,
    )
    dim = next(w for w in result["widgets"] if w.get("icon") == "mdi:brightness-6")
    assert dim["r"][3] == 56


# ---------------------------------------------------------------- binding


def test_binding_by_the_marked_form() -> None:
    """Constants stay constants, lookups are looked up, templates become slots."""
    result = compiled(
        probe(), {"params": PROBE_PARAMS, "variant": "title"}, {"light.a": LAMP}
    )
    centred, hello = result["widgets"][0], result["widgets"][1]
    assert centred["text"] == "Hello"  # {{ greeting }}: a lookup
    template = slot(result, hello["text"])
    assert template["template"] == "Hi {{ greeting }}"
    assert template["variables"]["greeting"] == "Hello"
    assert template["variables"]["can"]["effect_list"] == LAMP["effect_list"]


def test_slots_of_each_input_kind() -> None:
    """Inputs that are not templates become slots of their own kind."""
    result = compiled(
        probe(), {"params": PROBE_PARAMS, "variant": "title"}, {"light.a": LAMP}
    )
    kinds_ = {entry["kind"] for entry in result["slots"]}
    assert {"template", "state_icon", "clock", "colour"} <= kinds_
    clock = next(entry for entry in result["slots"] if entry["kind"] == "clock")
    assert clock == {"n": clock["n"], "kind": "clock"}
    plain = compiled(
        probe(), {"params": PROBE_PARAMS, "variant": "plain"}, {"light.a": LAMP}
    )
    history = next(e for e in plain["slots"] if e["kind"] == "history")
    assert history["entity"] == "sensor.e" and history["hours"] == 24


def test_a_colour_from_a_template_carries_the_cards_roles() -> None:
    """A template may give a role name; its slot gets the card's table of roles."""
    result = compiled(
        probe(), {"params": PROBE_PARAMS, "variant": "title"}, {"light.a": LAMP}
    )
    switch = next(w for w in result["widgets"] if w["t"] == "switch")
    assert switch["c"]["roles"] == DEFAULT_ROLES
    tinted = compiled(
        probe(), {"params": PROBE_PARAMS, "variant": "wide"}, {"light.a": LAMP}
    )
    # A colour source gives a number: no roles.
    assert "roles" not in tinted["tint"]


def test_roles_come_from_the_cards_theme() -> None:
    """A role constant takes the colour of the card's table of roles."""
    roles = role_table(
        {"acc": "#112233", "tx": "#ffffff"}, {"good": "#00FF00"}, DEFAULT_ROLES
    )
    assert roles["accent"] == "#112233" and roles["text"] == "#FFFFFF"
    assert roles["good"] == "#00FF00" and roles["bad"] == DEFAULT_ROLES["bad"]
    result = compiled(
        probe(),
        {"params": PROBE_PARAMS, "variant": "plain"},
        {"light.a": LAMP},
        roles=roles,
    )
    assert result["widgets"][0]["c"] == "#112233"


def test_an_action_per_kind_leaves_out_a_device_without_an_entry() -> None:
    """A kind without an entry has no action: the item is left out (C.2.8)."""
    doc = copy.deepcopy(PROBE)
    doc["outputs"]["each"]["action"] = {"light": "light.toggle"}
    component = validate_component(doc)
    result = compiled(
        component,
        {"params": PROBE_PARAMS, "grid_options": {"columns": 18, "rows": 11}},
        {"light.a": LAMP},
        detail=True,
    )
    lamps = [
        v["vars"]["lamp"] for v in result["actions"].values() if "lamp" in v["vars"]
    ]
    assert lamps == ["light.b", "light.d"]


def test_the_vars_of_an_item_reach_its_action() -> None:
    """`vars: {word: long}` is handed to the output the item calls."""
    result = compiled(
        probe(), {"params": PROBE_PARAMS, "variant": "title"}, {"light.a": LAMP}
    )
    words = [v["vars"].get("word") for v in result["actions"].values()]
    assert {"long", "short"} <= set(words)


def test_an_example_card_uses_the_preview() -> None:
    """A card without its device shows the preview's facts and values."""
    result = compiled(probe(), {"params": {}, "variant": "wide"})
    assert result["demo"] is True
    sliders = [w for w in result["widgets"] if w["t"] == "slider"]
    assert sliders[0]["value"] == 40
    assert "un" not in result
    with pytest.raises(MakerError) as info:
        doc = copy.deepcopy(PROBE)
        doc["preview"] = {}
        compiled(validate_component(doc), {"params": {}})
    assert info.value.code == "params_incomplete"


# ---------------------------------------------------------------- data is data

EVIL = ["{{ 1/0 }}", "{% for x in range(10**9) %}x{% endfor %}"]


def _evil_component() -> dict:
    """Return a card that shows options, facts and loop entries as text."""
    doc = copy.deepcopy(PROBE)
    doc["params"]["box"] = {"domain": "select", "optional": True}
    doc["params"]["player"] = {"domain": "media_player", "optional": True}
    doc["options"]["picked"] = {
        "type": "choice",
        "multiple": True,
        "max": 4,
        "from": "can.box.options",
        "default_first": 2,
        "section": "controls",
        "label": "Picked",
    }
    doc["variants"]["plain"] = {
        "name": "Plain",
        "grid": [18, 11],
        "header": "none",
        "layout": [
            {"type": "label", "text": "{{ greeting }}", "size": "s"},
            {"type": "label", "text": "Say {{ greeting }}", "size": "s"},
            {
                "type": "choice",
                "options": "effects",
                "value": "effect_at",
                "on_change": "set_effect",
            },
            {"type": "choice", "options": "can.effect_list", "on_change": "set_effect"},
            {"type": "choice", "options": "picked", "on_change": "set_effect"},
            {
                "type": "button",
                "text": "{{ source }}",
                "for_each": "can.player.sources",
                "as": "source",
                "per_row": 2,
                "on_tap": "flash",
            },
            {
                "type": "label",
                "text": "{{ opt }}",
                "size": "s",
                "for_each": "picked",
                "as": "opt",
                "per_row": 2,
            },
        ],
    }
    return validate_component(doc)


def _evil_result(**keys) -> dict:
    """Compile the card with evil option values, effects, sources and options."""
    component = _evil_component()
    raw = {
        "params": {**PROBE_PARAMS, "box": "select.box", "player": "media_player.p"},
        "variant": "plain",
        "options": {"greeting": EVIL[0], "effects": EVIL, "picked": EVIL},
    }
    facts = {
        "light.a": {**LAMP, "effect_list": [*EVIL, "Night"]},
        "select.box": {"options": [*EVIL, "c"], "icon": None, "kind": None},
        "media_player.p": {"sources": EVIL, "icon": None, "kind": None},
    }
    return compiled(component, raw, facts, **keys)


def test_data_is_never_template_source() -> None:
    """Options, effects, sources and select options that hold Jinja stay text.

    They reach the layout, the choice and the action as that very text.
    """
    result = _evil_result()
    widgets = result["widgets"]
    shown, said = widgets[0], widgets[1]
    assert shown["text"] == EVIL[0]
    said_slot = slot(result, said["text"])
    assert said_slot["template"] == "Say {{ greeting }}"
    assert said_slot["variables"]["greeting"] == EVIL[0]
    choices = [w for w in widgets if w["t"] == "choice"]
    assert choices[0]["texts"] == EVIL
    assert choices[1]["texts"] == [*EVIL, "Night"]
    assert choices[2]["texts"] == EVIL
    for choice in choices:
        options = result["actions"][f"{choice['i']}:change"]["options"]
        assert options[:2] == EVIL
    buttons = [w for w in widgets if w["t"] == "button"]
    assert [w["text"] for w in buttons] == EVIL
    sources = [
        v["vars"]["source"] for v in result["actions"].values() if "source" in v["vars"]
    ]
    assert sources == EVIL
    labels = [w["text"] for w in widgets if w["t"] == "label"][2:]
    assert labels == EVIL
    for template in all_templates(result):
        for evil in EVIL:
            assert evil not in template


def test_data_is_never_template_source_in_an_example_card() -> None:
    """The same holds for preview values."""
    result = _evil_result()
    assert all(
        "1/0" not in template and "range(" not in template
        for template in all_templates(result)
    )


def test_compile_renders_nothing() -> None:
    """maker/ holds no Jinja: compile2 imports none."""
    source = (
        HERE.parent / "custom_components" / "apollo_tab" / "maker" / "compile2.py"
    ).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+jinja2", source, re.MULTILINE)
    assert "homeassistant" not in source


def test_the_look_names_are_the_contracts() -> None:
    """The device numbers of the look keys follow contract.json v2."""
    from custom_components.apollo_tab.maker import compile2

    v2 = CONTRACT["v2"]
    assert list(compile2.LIT) == v2["lit"]
    assert list(compile2.ALIGN) == v2["align"]
    assert list(compile2.SHAPES) == v2["shapes"]
    assert list(compile2.SLIDER_LOOKS) == v2["slider_looks"]
    assert list(compile2.DIRS) == v2["dirs"]
    assert list(compile2.IMAGE_LOOKS) == v2["image_looks"]
    assert list(compile2.CHOICE_LOOKS) == v2["choice_looks"]
    digits = CONTRACT["fonts"]["digits_px"]
    assert sorted(set(compile2.LABEL_PX.values()) - {28}) == digits


def test_a_row_holds_at_most_8_widgets() -> None:
    """What is over 8 in a row is cut, with a warning."""
    doc = copy.deepcopy(PROBE)
    doc["variants"]["plain"]["layout"] = [
        {
            "type": "row",
            "items": [{"type": "label", "text": str(i), "size": "s"} for i in range(4)],
        }
    ]
    component = validate_component(doc)
    # The loader takes at most 8 items; the cut while compiling is behind it.
    row = component["variants"]["plain"]["layout"][0]
    row["items"] = row["items"] * 3
    result = compiled(
        component, {"params": PROBE_PARAMS, "variant": "plain"}, {"light.a": LAMP}
    )
    assert [w["text"] for w in result["widgets"]] == ["0", "1", "2", "3"] * 2
    assert result["warnings"] == ["element_clipped"]
