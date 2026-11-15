"""Fact names, param names and `needs` on a variant (coordinator's decisions 2, 9).

Decision 2: an entity param of a schema 2 file may not take the name of a
fact of the fixed table, and `can.<x>` must name a fact of the table or an
entity param of the same file. Anything else is refused at load.

Decision 9: a variant, the detail variant too, may carry `needs:` (a fact,
as an option's `needs`) and `needs_text`. Where it does not hold for the
card's device the form does not offer the variant, a stored card that names
it gets the file's first variant that holds, and a detail variant that does
not hold makes no detail page: the card gets no hold and nothing else that
opens one. `apollo/light` uses it for Large.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from custom_components.apollo_tab.library import form_entry
from custom_components.apollo_tab.maker.compile2 import (
    compile_card2,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.compile2_v1 import variant_of
from custom_components.apollo_tab.maker.convert import convert_dashboard
from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.features import FACT_NAMES, FACTS, facts_of
from custom_components.apollo_tab.maker.geometry import card_size_px
from custom_components.apollo_tab.maker.schema import validate_component

HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parent / "custom_components" / "apollo_tab" / "library"
ICONS = json.loads((HERE / "contract" / "icons.json").read_text(encoding="utf-8"))
THEMES = {
    theme["id"]: {k: v for k, v in theme.items() if k != "id"}
    for theme in json.loads((LIBRARY / "themes.json").read_text(encoding="utf-8"))
}

COLOUR_LAMP = facts_of(
    {
        "domain": "light",
        "registry": {
            "capabilities": {
                "supported_color_modes": ["color_temp", "hs", "xy"],
                "min_color_temp_kelvin": 15,
                "max_color_temp_kelvin": 6535,
            }
        },
    }
)
DIM_LAMP = facts_of(
    {
        "domain": "light",
        "registry": {"capabilities": {"supported_color_modes": ["brightness"]}},
    }
)
ONOFF_LAMP = facts_of(
    {
        "domain": "light",
        "registry": {"capabilities": {"supported_color_modes": ["onoff"]}},
    }
)


def _doc(**overrides) -> dict:
    """Return a small valid schema 2 file with two device params."""
    doc = {
        "schema": 2,
        "id": "test/facts",
        "version": "1.0.0",
        "name": "Facts",
        "params": {
            "entity": {"domain": "light"},
            "lamps": {"domain": "light", "multiple": True, "optional": True},
        },
        "options": {
            "bar": {"type": "toggle", "section": "controls", "label": "Bar"},
        },
        "inputs": {"is_on": "{{ is_state(entity, 'on') }}"},
        "outputs": {
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


def _with(*items, **overrides) -> dict:
    """Return the small file with these items in its one variant."""
    doc = _doc(**overrides)
    doc["variants"]["tile"]["layout"] = list(items)
    return doc


def _refused(doc: dict, code: str, path: str | None = None) -> None:
    """Assert the file is refused at load with this code (and path)."""
    with pytest.raises(MakerError) as info:
        validate_component(doc)
    assert info.value.code == code, str(info.value)
    if path is not None:
        assert info.value.path == path, str(info.value)


# ---------------------------------------------------------------- decision 2


def test_the_fact_names_are_the_fixed_table() -> None:
    """Every fact of every domain, and the three every entity has."""
    names = {"toggle", "icon", "kind"}
    for row in FACTS.values():
        for group in row:
            names.update(group)
    assert names == FACT_NAMES
    assert {"temperature", "group", "power", "start", "pause", "min"} <= FACT_NAMES


@pytest.mark.parametrize("name", ["temperature", "group", "power", "start", "icon"])
def test_a_device_param_may_not_take_a_facts_name(name: str) -> None:
    """`can.temperature` would mean both a light's fact and the device."""
    doc = _doc()
    doc["params"][name] = {"domain": "sensor", "optional": True}
    _refused(doc, "bad_name", f"params.{name}")


def test_a_page_param_may_take_any_name() -> None:
    """Only device params are in `can`; a page param named like a fact is fine."""
    doc = _doc()
    doc["params"]["start"] = {"type": "page", "optional": True}
    assert validate_component(doc)["params"]["start"]["kind"] == "page"


def test_can_names_a_fact_or_a_device_param() -> None:
    """Facts of the table, a device param whole, a fact of a device param."""
    doc = _with(
        {"type": "label", "text": "a", "when": ["can.brightness"]},
        {"type": "label", "text": "b", "when": ["can.lamps"]},
        {"type": "label", "text": "c", "when": ["can.lamps.colour", "!can.kind"]},
        {"type": "label", "text": "{{ can.min_kelvin }}"},
        {"type": "label", "text": "{{ can.effect_list | count }}"},
        {"type": "label", "text": "{{ can.effect_list.index('x') }}"},
        {"type": "label", "text": "{{ can.lamps[0].brightness }}"},
        {"type": "label", "text": "{{ s_can.whatever }}"},
    )
    doc["options"]["bar"]["needs"] = "can.brightness"
    doc["options"]["effects"] = {
        "type": "choice",
        "section": "controls",
        "label": "Effects",
        "multiple": True,
        "from": "can.effect_list",
    }
    component = validate_component(doc)
    assert component["options"]["bar"]["needs"] == "can.brightness"


@pytest.mark.parametrize(
    "item",
    [
        {"type": "label", "text": "x", "when": ["can.dimmable"]},
        {"type": "label", "text": "x", "when": ["!can.dimmable"]},
        {"type": "label", "text": "x", "when": ["can.lamps.dimmable"]},
        {"type": "label", "text": "{{ can.dimmable }}"},
        {"type": "label", "text": "{{ 'on' if can.dimmable else 'off' }}"},
        {"type": "label", "text": "{{ can.lamps.dimmable }}"},
        {"type": "label", "text": "x", "visible": "{{ can.dimmable }}"},
        {"type": "button", "for_each": "can.effect_lists", "as": "e", "text": "x"},
        {"type": "choice", "options": "can.effect_lists", "on_change": "dim"},
    ],
)
def test_can_naming_anything_else_is_refused(item: dict) -> None:
    """A word that is no fact of the table and no device of this card."""
    _refused(_with(item), "unknown_fact")


def test_can_in_a_data_template_or_an_input_is_checked() -> None:
    """Data templates and input templates read `can` too."""
    doc = _doc()
    doc["outputs"]["dim"]["data"]["transition"] = "{{ can.speedy }}"
    _refused(doc, "unknown_fact", "outputs.dim.data.transition")
    doc = _doc()
    doc["inputs"]["fast"] = "{{ can.speedy and is_on }}"
    _refused(doc, "unknown_fact", "inputs.fast")


def test_a_needs_or_a_list_option_naming_no_fact_is_refused() -> None:
    """An option's `needs` and `from` name a fact of the table."""
    doc = _doc()
    doc["options"]["bar"]["needs"] = "can.dimmable"
    _refused(doc, "unknown_fact", "options.bar.needs")
    doc = _doc()
    doc["options"]["effects"] = {
        "type": "choice",
        "section": "controls",
        "label": "Effects",
        "multiple": True,
        "from": "can.effects_list",
    }
    _refused(doc, "unknown_fact", "options.effects.from")


def test_one_devices_facts_in_a_loop_name_a_fact() -> None:
    """`{{ <as>_can.<x> }}` of a loop over devices looks up a fact of the table."""
    row = {
        "type": "button",
        "for_each": "lamps",
        "as": "one",
        "icon": "{{ one_can.icon }}",
        "text": "x",
        "on_tap": "dim",
    }
    assert validate_component(_with(row))
    _refused(_with({**row, "icon": "{{ one_can.picture }}"}), "unknown_fact")


def test_no_built_in_card_names_a_device_like_a_fact() -> None:
    """The built-in files load under the rule (a colliding one was renamed)."""
    for path in sorted((LIBRARY / "components").glob("*.yaml")):
        component = validate_component(yaml.safe_load(path.read_text("utf-8")))
        if component.get("schema") != 2:
            continue
        for name, spec in component["params"].items():
            if spec["kind"] == "entity":
                assert name not in FACT_NAMES, (component["id"], name)


# ---------------------------------------------------------------- decision 9


def _needs_doc() -> dict:
    """Return a card whose Large variant and controls page need facts."""
    doc = _doc(
        on="is_on",
        tap={
            "default": "detail",
            "choices": {
                "detail": {"label": "Opens its controls"},
                "none": {"label": "Does nothing"},
            },
        },
        hold="detail",
        detail="full",
    )
    doc["variants"] = {
        "tile": {
            "name": "Tile",
            "grid": [6, 3],
            "header": "tile",
            "trailing": "more",
            "layout": [
                {"type": "label", "text": "Hold", "on_hold": "detail"},
                {"type": "button", "text": "Open", "on_tap": "detail"},
            ],
        },
        "large": {
            "name": "Large",
            "grid": [12, 6],
            "needs": "can.brightness",
            "needs_text": "This light cannot be dimmed",
            "layout": [{"type": "slider", "value": "is_on", "on_change": "dim"}],
        },
        "full": {
            "name": "Controls",
            "grid": [18, 11],
            "picker": False,
            "needs": "can.colour",
            "layout": [{"type": "slider", "value": "is_on", "on_change": "dim"}],
        },
    }
    return doc


def test_a_variant_carries_needs_and_needs_text() -> None:
    """Both are kept, normalised as for an option; left out they are empty."""
    variants = validate_component(_needs_doc())["variants"]
    assert (variants["large"]["needs"], variants["large"]["needs_text"]) == (
        "can.brightness",
        "This light cannot be dimmed",
    )
    assert (variants["full"]["needs"], variants["full"]["needs_text"]) == (
        "can.colour",
        "",
    )
    assert (variants["tile"]["needs"], variants["tile"]["needs_text"]) == ("", "")


def test_a_variants_needs_is_checked_at_load() -> None:
    """A fact of the table; needs_text needs needs; one picker variant needs nothing."""
    doc = _needs_doc()
    doc["variants"]["large"]["needs"] = "can.dimmable"
    _refused(doc, "unknown_fact", "variants.large.needs")
    doc = _needs_doc()
    doc["variants"]["large"]["needs"] = "brightness"
    _refused(doc, "bad_value", "variants.large.needs")
    doc = _needs_doc()
    del doc["variants"]["large"]["needs"]
    _refused(doc, "bad_value", "variants.large.needs_text")
    doc = _needs_doc()
    doc["variants"]["tile"]["needs"] = "can.toggle"
    _refused(doc, "bad_value", "variants")


def _compile(doc_or_component: dict, facts: dict, **card) -> dict:
    """Compile a card of the needs file for one lamp."""
    component = (
        doc_or_component
        if "widgets" in next(iter(doc_or_component["variants"].values()))
        else validate_component(doc_or_component)
    )
    raw = {"params": {"entity": "light.lamp"}, **card}
    cfg = validate_card_config2(component, raw)
    return compile_card2(component, cfg, {"light.lamp": facts})


def test_a_stored_variant_that_does_not_hold_gives_the_first_that_does() -> None:
    """Large for a lamp that cannot dim is drawn as the Tile, in its own size."""
    grid = {"columns": 12, "rows": 6}
    stored = {"variant": "large", "grid_options": grid}
    assert _compile(_needs_doc(), DIM_LAMP, **stored)["variant"] == "large"
    assert _compile(_needs_doc(), ONOFF_LAMP, **stored)["variant"] == "tile"
    # No variant stored: the largest that fits and holds.
    assert _compile(_needs_doc(), DIM_LAMP, grid_options=grid)["variant"] == "large"
    assert _compile(_needs_doc(), ONOFF_LAMP, grid_options=grid)["variant"] == "tile"


def test_a_detail_variant_that_holds_makes_its_openers() -> None:
    """A colour lamp: the hold, the tap, the `more` button and an item's hold."""
    result = _compile(_needs_doc(), COLOUR_LAMP, grid_options={"columns": 6, "rows": 3})
    assert result["hold"] == {"local": "detail"}
    assert result["tap"] == {"local": "detail"}
    assert result["opener"] is True
    holds = [w for w in result["widgets"] if w.get("hold") == {"local": "detail"}]
    more = [w for w in result["widgets"] if w.get("tap") == {"local": "detail"}]
    # The `more` button and the item that opens the controls.
    assert len(holds) == 1 and len(more) == 2


def test_a_detail_variant_that_does_not_hold_opens_nothing() -> None:
    """A lamp without colour: no hold, no tap choice, no `more`, no item hold."""
    result = _compile(_needs_doc(), DIM_LAMP, grid_options={"columns": 6, "rows": 3})
    assert "hold" not in result
    assert "tap" not in result
    assert result["opener"] is False
    assert not any("hold" in w for w in result["widgets"])
    assert not any(w.get("tap") == {"local": "detail"} for w in result["widgets"])
    # A stored tap that opens the controls does nothing for this device.
    result = _compile(
        _needs_doc(),
        DIM_LAMP,
        options={"tap": "detail"},
        grid_options={"columns": 6, "rows": 3},
    )
    assert "tap" not in result


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


def _convert(component: dict, facts: dict, dl: int = 2, **card) -> dict:
    """Convert a dashboard with one card of a component."""
    components = {component["id"]: {**component, "source": "builtin"}}
    for path in sorted((LIBRARY / "components").glob("*.yaml")):
        builtin = validate_component(yaml.safe_load(path.read_text("utf-8")))
        components.setdefault(builtin["id"], {**builtin, "source": "builtin"})
    entry = {
        "type": "custom:apollo-tab-card",
        "component": component["id"],
        "params": {"entity": "light.lamp"},
        **card,
    }
    return convert_dashboard(
        _dashboard(entry),
        components=components,
        themes=THEMES,
        approved=set(),
        facts={"light.lamp": facts},
        dl=dl,
        icons=ICONS,
    )


def test_no_detail_page_where_the_detail_variant_does_not_hold() -> None:
    """The converter makes the controls page only for a device that has them."""
    component = validate_component(_needs_doc())
    grid = {"grid_options": {"columns": 6, "rows": 3}}
    with_page = _convert(component, COLOUR_LAMP, **grid)
    assert [p["id"] for p in with_page["layout"]["pages"]] == ["home", "home~1"]
    without = _convert(component, DIM_LAMP, **grid)
    assert [p["id"] for p in without["layout"]["pages"]] == ["home"]
    assert without["warnings"] == []


def test_a_controls_page_gives_its_card_the_whole_page() -> None:
    """With no heading a detail variant may be 12 rows high (LOOK-NOTES decision 1)."""
    doc = _needs_doc()
    doc["variants"]["full"]["grid"] = [18, 12]
    doc["variants"]["full"]["layout"][0]["grow"] = True
    component = validate_component(doc)
    grid = {"grid_options": {"columns": 6, "rows": 3}}
    [card] = _convert(component, COLOUR_LAMP, **grid)["layout"]["pages"][1]["w"]
    assert card["r"][1:] == [20, 568, card_size_px(18, 12)[1]]


# ---------------------------------------------------------------- the light


LIGHT = validate_component(
    yaml.safe_load((LIBRARY / "components" / "apollo-light.yaml").read_text("utf-8"))
)


def test_the_light_offers_large_only_for_a_lamp_that_dims() -> None:
    """The form data says why: as_dict gives `needs` and `needs_text` (C.7)."""
    entry = form_entry(LIGHT, False)
    large = next(v for v in entry["variants"] if v["id"] == "large")
    assert large["needs"] == "can.brightness"
    assert large["needs_text"] == "This light only turns on and off"
    tile = next(v for v in entry["variants"] if v["id"] == "tile")
    assert "needs" not in tile and "needs_text" not in tile


@pytest.mark.parametrize(
    ("facts", "variant"),
    [(COLOUR_LAMP, "large"), (DIM_LAMP, "large"), (ONOFF_LAMP, "wide")],
)
def test_a_stored_large_light(facts: dict, variant: str) -> None:
    """The colour lamp and the dim-only lamp keep Large; the on/off lamp gets Wide.

    Wide is the largest size that holds and fits 12 x 6 (LOOK-NOTES decision
    14; it was Tile, the first size of the picker).
    """
    stored = {"variant": "large", "grid_options": {"columns": 12, "rows": 6}}
    result = _compile(LIGHT, facts, **stored)
    assert result["variant"] == variant
    assert result["warnings"] == []


@pytest.mark.parametrize(
    ("facts", "variant"),
    [(COLOUR_LAMP, "large"), (DIM_LAMP, "large"), (ONOFF_LAMP, "wide")],
)
def test_a_large_light_card_with_no_variant_stored(facts: dict, variant: str) -> None:
    """In 12 x 6 the light is Large where it can dim, else Wide."""
    result = _compile(LIGHT, facts, grid_options={"columns": 12, "rows": 6})
    assert result["variant"] == variant


def test_the_version_1_form_reads_the_facts_for_the_variant() -> None:
    """Large stored for an on/off lamp gives the Wide's old card (C.6, decision 14)."""
    stored = {"variant": "large", "grid_options": {"columns": 12, "rows": 6}}
    cfg = validate_card_config2(LIGHT, {"params": {"entity": "light.lamp"}, **stored})
    assert variant_of(LIGHT, cfg, {"light.lamp": COLOUR_LAMP}) == "large"
    assert variant_of(LIGHT, cfg, {"light.lamp": ONOFF_LAMP}) == "wide"
    colour = _convert(LIGHT, COLOUR_LAMP, 1, **stored)
    onoff = _convert(LIGHT, ONOFF_LAMP, 1, **stored)
    [colour_card] = [w for w in colour["layout"]["pages"][0]["w"] if w["t"] == "card"]
    [onoff_card] = [w for w in onoff["layout"]["pages"][0]["w"] if w["t"] == "card"]
    assert colour_card["component"] == "apollo/light-slider"
    assert onoff_card["component"] == "apollo/light-slider"


def test_the_light_needs_brightness_for_large_and_its_controls() -> None:
    """Tile and Wide carry no needs; Large and the controls page need brightness.

    The controls page's needs is LOOK-NOTES decision 2 (it was "" before).
    """
    assert {name: v["needs"] for name, v in LIGHT["variants"].items()} == {
        "tile": "",
        "wide": "",
        "large": "can.brightness",
        "full": "can.brightness",
    }
    doc = copy.deepcopy(LIGHT)
    assert doc["detail"] == "full"


@pytest.mark.parametrize(
    ("variant", "columns", "rows"), [("tile", 6, 3), ("wide", 12, 3)]
)
def test_the_light_opens_its_controls_only_for_a_lamp_that_dims(
    variant: str, columns: int, rows: int
) -> None:
    """An on/off lamp: no hold, no controls page (LOOK-NOTES decision 2)."""
    grid = {"variant": variant, "grid_options": {"columns": columns, "rows": rows}}
    for facts in (COLOUR_LAMP, DIM_LAMP):
        assert _compile(LIGHT, facts, **grid)["hold"] == {"local": "detail"}
        pages = _convert(LIGHT, facts, **grid)["layout"]["pages"]
        assert [p["id"] for p in pages] == ["home", "home~1"]
    result = _compile(LIGHT, ONOFF_LAMP, **grid)
    assert "hold" not in result and result["opener"] is False
    without = _convert(LIGHT, ONOFF_LAMP, **grid)
    assert [p["id"] for p in without["layout"]["pages"]] == ["home"]
    assert without["warnings"] == []
