"""The look of the cards after round 3 of package L4.

Each test holds one change of round 3: names sized from the value shown
(chips and List rows), grown cards held together as one block, the
Thermostat Tile's two-line name, the Link card's fade, the search of a
middle cut, and the splice checks of name templates.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from custom_components.apollo_tab.maker.compile2 import (
    BUTTON_ICON_GAP,
    BUTTON_PX,
    BUTTON_TEXT_PAD,
    compile_card2,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.geometry import (
    GAP,
    ROW_ITEM_GAP,
    image_icon_px,
    layout_card2,
)
from custom_components.apollo_tab.maker.names import (
    NAME_W,
    NAME_W_SPARE,
    NAME_WIDTHS,
    cut_to_fit,
    cut_to_fit_template,
    name_chars,
    name_width,
    room_beside,
    room_beside_template,
)
from custom_components.apollo_tab.maker.schema import validate_component
from custom_components.apollo_tab.maker.templates import check_template
from tests.test_cards_look_l3 import _compile_at
from tests.test_cards_step_a import COMPONENTS, _value
from tests.test_cards_step_b import MEDIA_RAW, _compile

LONG_VALUE = "Washing machine running"

# ---------------------------------------------------------------- names beside a value


def _chip(result: dict) -> tuple[dict, dict]:
    """Return the name and the state label of a chip."""
    name = next(w for w in result["widgets"] if w["t"] == "label" and w["size"] == "m")
    state = next(w for w in result["widgets"] if w["t"] == "label" and w["size"] == "s")
    return name, state


async def test_a_chip_name_gets_what_its_value_leaves(hass: HomeAssistant) -> None:
    """Critic major: "Living R…Temperature" beside "21.4 °C" with 63 px free.

    The name's label spans the line, the state is drawn over its end, and
    the name gets the room the value shown leaves (decision 14). A value as
    wide as its column cuts the name as before.
    """
    result = _compile(
        COMPONENTS["apollo/reading"], "chip", {"entity": "sensor.t"}, {}, {}
    )
    name, state = _chip(result)
    assert state["al"] == 2
    assert name["r"][0] + name["r"][2] == state["r"][0] + state["r"][2]
    width = name["r"][2]
    attrs = {"friendly_name": "Living Room Temperature", "unit_of_measurement": "°C"}
    hass.states.async_set("sensor.t", "21.44", attrs)
    assert await _value(hass, result, state["text"]) == "21.4 °C"
    assert await _value(hass, result, name["text"]) == "Living Room Temperature"
    hass.states.async_set("sensor.t", LONG_VALUE, attrs)
    shown = await _value(hass, result, name["text"])
    room = room_beside(LONG_VALUE, 14, width, GAP, state["r"][2])
    assert shown == cut_to_fit(
        "Living Room Temperature", name_chars(width), width, room=room
    )
    assert "…" in shown and shown.endswith("Temperature")


async def test_a_chip_with_a_title_measures_its_value_too(hass: HomeAssistant) -> None:
    """The person's title beside a live value reaches the template as data."""
    raw = {
        "params": {"entity": "sensor.t"},
        "variant": "chip",
        "title": "Living Room Temperature {{ 7*7 }}",
        "grid_options": {"columns": 12, "rows": 1},
    }
    component = COMPONENTS["apollo/reading"]
    result = compile_card2(component, validate_card_config2(component, raw), {}, 2)
    name, _state = _chip(result)
    [slot] = [s for s in result["slots"] if s["n"] == name["text"]["s"]]
    assert "7*7" not in slot["template"]
    hass.states.async_set("sensor.t", "1", {"unit_of_measurement": "W"})
    shown = await _value(hass, result, name["text"])
    assert "49" not in shown and shown.startswith("Living") and "…" in shown


async def test_a_list_row_name_gets_what_its_value_leaves(hass: HomeAssistant) -> None:
    """Critic major: List Large rows cut a name that fits beside a short value."""
    result = _compile(
        COMPONENTS["apollo/readings"], "large", {"entities": ["sensor.a", "sensor.b"]},
        {}, {},
    )  # fmt: skip
    icon, name, value = result["widgets"][:3]
    assert icon["t"] == "image" and value["al"] == 2
    assert name["r"][0] + name["r"][2] == value["r"][0] + value["r"][2]
    width = name["r"][2]
    # 218 px at 18 px: over the 216 a fixed value column of 88 left it.
    long = "Bathroom Temperature"
    assert name_width(long) > (width - ROW_ITEM_GAP - value["r"][2]) * 10
    attrs = {"friendly_name": long, "unit_of_measurement": "°C"}
    hass.states.async_set("sensor.a", "21.4", attrs)
    assert await _value(hass, result, value["text"]) == "21.4 °C"
    assert await _value(hass, result, name["text"]) == long
    hass.states.async_set("sensor.a", LONG_VALUE, attrs)
    shown = await _value(hass, result, name["text"])
    room = room_beside(LONG_VALUE, 18, width, ROW_ITEM_GAP, value["r"][2])
    assert shown == cut_to_fit(long, name_chars(width), width, room=room)
    assert "…" in shown
    # A device gone: a dash, and the name has the line.
    hass.states.async_set("sensor.a", "unavailable", attrs)
    assert await _value(hass, result, name["text"]) == long


@pytest.mark.parametrize("width", [152, 216, 312])
async def test_the_room_beside_template_agrees_with_python(
    hass: HomeAssistant, width: int
) -> None:
    """room_beside_template sets what room_beside returns, for any value."""
    template = Template(
        room_beside_template("v", 14, width, 8, 88) + "{{ nroom }}", hass
    )
    for value in ("", "21.4 °C", "—", LONG_VALUE, "  On  ", None, 21.4):
        got = template.async_render(
            {"v": value, "value_w": dict(NAME_WIDTHS[14])}, parse_result=False
        )
        text = "" if value is None else str(value)
        assert int(got) == room_beside(text, 14, width, 8, 88), value
    assert room_beside("", 14, width, 8, 88) == width * 10 - NAME_W_SPARE


async def test_a_cut_beside_a_value_agrees_with_python(hass: HomeAssistant) -> None:
    """The live cut with a measured room gives what cut_to_fit gives."""
    width = 312
    template = Template(
        "{%- set n = name -%}"
        + room_beside_template("v", 14, width, 8, 88)
        + cut_to_fit_template(name_chars(width), width, beside=True),
        hass,
    )
    for name in ("Living Room Temperature", "Upstairs Guest Bedroom Window Sensor"):
        for value in ("21.4 °C", LONG_VALUE, ""):
            got = template.async_render(
                {"name": name, "v": value, "name_w": dict(NAME_W),
                 "value_w": dict(NAME_WIDTHS[14])},
                parse_result=False,
            )  # fmt: skip
            room = room_beside(value, 14, width, 8, 88)
            assert got == cut_to_fit(name, name_chars(width), width, room=room)


# ---------------------------------------------------------------- the middle cut


def test_a_cut_is_not_made_early_for_narrow_letters() -> None:
    """Critic minor: "Upstairs Guest…Left" left 50 px free before the switch.

    The search starts at twice the average guess, so a name of narrow
    letters keeps what fits.
    """
    name = "Upstairs Guest Bedroom Left"
    shown = cut_to_fit(name, name_chars(220), 220)
    assert shown == "Upstairs Guest Be…Left"
    assert name_width(shown) <= 220 * 10 - NAME_W_SPARE


async def test_the_live_cut_is_not_made_early_either(hass: HomeAssistant) -> None:
    """The template twin starts its search where cut_to_fit does."""
    template = Template(
        "{%- set n = name -%}" + cut_to_fit_template(name_chars(220), 220), hass
    )
    got = template.async_render(
        {"name": "Upstairs Guest Bedroom Left", "name_w": dict(NAME_W)},
        parse_result=False,
    )
    assert got == "Upstairs Guest Be…Left"


async def test_a_scene_name_leaves_its_icon_room(hass: HomeAssistant) -> None:
    """Tester minor: a name that fits only without the icon's room is cut."""
    result = _compile(
        COMPONENTS["apollo/scenes"], "large", {"scenes": ["scene.a", "scene.b"]}, {}, {}
    )
    button = next(w for w in result["widgets"] if w["t"] == "button" and "icon" in w)
    w, h = button["r"][2], button["r"][3]
    assert h < 64
    room = w - 2 * BUTTON_TEXT_PAD - image_icon_px(w, h) - BUTTON_ICON_GAP
    name = "Scene"
    while name_width(name, BUTTON_PX) <= room * 10 - NAME_W_SPARE:
        name += " x"
    assert name_width(name, BUTTON_PX) <= (w - 2 * BUTTON_TEXT_PAD) * 10 - NAME_W_SPARE
    hass.states.async_set("scene.a", "x", {"friendly_name": name})
    shown = await _value(hass, result, button["text"])
    assert shown != name and "…" in shown


async def test_now_playing_shows_the_player_name_without_a_title(
    hass: HomeAssistant,
) -> None:
    """Tester minor: with no track the large line is the player's name."""
    result = _compile(
        COMPONENTS["apollo/media"], "hero", {"entity": "media_player.a"}, {},
        {"media_player.a": facts_of(MEDIA_RAW)},
    )  # fmt: skip
    title, name = (w for w in result["widgets"] if w.get("size") == "l")
    hass.states.async_set("media_player.a", "idle", {"friendly_name": "Kitchen"})
    assert await _value(hass, result, name["vis"]) in (True, "True")
    assert await _value(hass, result, title["vis"]) in (False, "False")
    assert await _value(hass, result, name["text"]) == "Kitchen"


# ---------------------------------------------------------------- grown cards


@pytest.mark.parametrize("header", ["title", "tile", "tile_v"])
@pytest.mark.parametrize("height", [376, 568, 760])
def test_a_grown_card_keeps_its_rows_under_its_header(header: str, height: int) -> None:
    """Critic major: grown cards left 100 to 300 px between header and rows.

    The first row follows the header with the theme's gap, and the header
    and the rows sit together in the card's middle.
    """
    body = [
        {"kind": "row", "cells": [{"type": "button", "control": True}], "height": 48},
        {"kind": "row", "cells": [{"type": "label", "size": "m"}], "height": None},
    ]
    laid = layout_card2(body, 376, height, header, centre=True)
    head_bottom = max(r[1] + r[3] for r in laid["header"].values())
    first = laid["rects"][0][0][0]
    assert first[1] == head_bottom + GAP
    top = min(r[1] for r in laid["header"].values()) - 16
    last = laid["rects"][1][0][0]
    assert abs(top - (height - 16 - (last[1] + last[3]))) <= 1


@pytest.mark.parametrize(
    ("component_id", "variant", "columns", "rows", "params", "in_header"),
    [
        # badge, name
        ("apollo/reading", "tile", 12, 6, {"entity": "sensor.t"}, 2),
        # two lines of name
        ("apollo/page-link", "tile", 6, 6, {"page": "o", "entity": "sensor.t"}, 2),
        # badge, name (stacked, no state line)
        ("apollo/button", "tile", 6, 6, {"entity": "script.a"}, 2),
        # badge, name, state, switch
        ("apollo/light", "large", 12, 12, {"entity": "light.a"}, 4),
        ("apollo/door-lock", "tile", 12, 6, {"entity": "lock.a"}, 3),
    ],
)
def test_a_grown_card_value_stays_under_its_header(
    component_id: str,
    variant: str,
    columns: int,
    rows: int,
    params: dict,
    in_header: int,
) -> None:
    """Tester minor (item 2b): a grown tile kept a band under its header.

    A grown Status, Link or Button Tile's value now follows the header, and
    the two sit together in the card's middle.
    """
    facts = {}
    if component_id == "apollo/light":
        facts = {"light.a": facts_of({"domain": "light", "registry": {
            "capabilities": {"supported_color_modes": ["brightness"]}}})}  # fmt: skip
    result = _compile_at(component_id, variant, columns, rows, params, facts)
    header = result["widgets"][:in_header]
    body = result["widgets"][in_header:]
    header_bottom = max(w["r"][1] + w["r"][3] for w in header)
    # A badge beside one line sits 2 px down in its header of 48.
    assert GAP <= min(w["r"][1] for w in body) - header_bottom <= GAP + 2
    above = min(w["r"][1] for w in header) - 16
    below = result["h"] - 16 - max(w["r"][1] + w["r"][3] for w in body)
    assert above > 0 and abs(above - below) <= 2


# ---------------------------------------------------------------- thermostat


async def test_the_thermostat_tile_keeps_the_room_in_its_name(
    hass: HomeAssistant,
) -> None:
    """Critic major: "Liv…Thermostat" lost what tells two thermostats apart."""
    result = _compile(
        COMPONENTS["apollo/climate"], "tile", {"entity": "climate.a"}, {}, {}
    )
    assert result["warnings"] == []
    line1, line2 = (
        w for w in result["widgets"] if w.get("size") == "m" and w["r"][1] < 64
    )
    hass.states.async_set(
        "climate.a",
        "heat",
        {"friendly_name": "Living Room Thermostat", "temperature": 21.5,
         "current_temperature": 20.5},
    )  # fmt: skip
    assert await _value(hass, result, line1["text"]) == "Living Room"
    assert await _value(hass, result, line2["text"]) == "Thermostat"
    buttons = [w for w in result["widgets"] if w["t"] == "button"]
    assert {w["r"][3] for w in buttons} == {48}
    assert {w["r"][2] for w in buttons} == {72}


# ---------------------------------------------------------------- link fade


async def test_the_link_fades_when_its_reading_is_gone(hass: HomeAssistant) -> None:
    """Decision 3 (coordinator): a missing or unavailable reading fades the card.

    The tap still goes to the page (contract 4.7: a `go` works on `un`).
    Without a reading it never fades.
    """
    result = _compile(
        COMPONENTS["apollo/page-link"], "tile", {"page": "o", "entity": "sensor.t"},
        {}, {},
    )  # fmt: skip
    assert result["tap"] is not None
    assert await _value(hass, result, result["un"]) is True  # missing
    hass.states.async_set("sensor.t", "unavailable")
    assert await _value(hass, result, result["un"]) is True
    hass.states.async_set("sensor.t", "9")
    assert await _value(hass, result, result["un"]) is False
    bare = _compile(COMPONENTS["apollo/page-link"], "tile", {"page": "o"}, {}, {})
    assert await _value(hass, bare, bare["un"]) is False


# ---------------------------------------------------------------- spliced templates

EVIL = "{% macro m() %}MACRO-RAN{% endmacro %}{{ m() }}"
GUARD_SPLICE = (
    "{{ ' %}" + EVIL + "{%-endif-%}{%-if 0-%} if 1 ~' ~ e if e "
    "else state_attr(e, 'friendly_name') or e }}"
)
VALUE_SPLICE = "{{ ' %}" + EVIL + "{%- set q = 1 -%}' ~ e }}"


def _stranger(name_text: str, value_text: str | None = None) -> dict:
    items = [{"type": "label", "size": "s", "text": name_text}]
    if value_text is not None:
        items.append(
            {"type": "label", "size": "s", "align": "right", "width": 80,
             "text": value_text}
        )  # fmt: skip
    return validate_component(
        {
            "schema": 2,
            "id": "stranger/splice",
            "version": "1.0.0",
            "name": "Splice",
            "params": {"entity": {"domain": "sensor", "multiple": True, "max": 4}},
            "variants": {
                "main": {
                    "name": "Main",
                    "grid": [12, 3],
                    "header": "title",
                    "layout": [
                        {"type": "row", "for_each": "entity", "as": "e", "items": items}
                    ],
                }
            },
        }
    )


@pytest.mark.parametrize(
    ("name_text", "value_text"),
    [
        (GUARD_SPLICE, None),
        ("{{ state_attr(e, 'friendly_name') or e }}", VALUE_SPLICE),
    ],
)
def test_no_spliced_name_slot_holds_what_check_template_refuses(
    name_text: str, value_text: str | None
) -> None:
    """Security minor: a name slot made from pieces of a label held a macro.

    The label's own text passed check_template. The pieces must be plain
    expressions and what they make is checked again; else the label keeps
    its own text.
    """
    check_template(name_text, "probe")
    if value_text is not None:
        check_template(value_text, "probe")
    component = _stranger(name_text, value_text)
    raw = {
        "params": {"entity": ["sensor.a"]},
        "variant": "main",
        "grid_options": {"columns": 12, "rows": 3},
    }
    compiled = compile_card2(component, validate_card_config2(component, raw), {}, 2)
    for slot in compiled["slots"]:
        if slot.get("kind") == "template":
            try:
                check_template(slot["template"], "slot")
            except MakerError as err:  # pragma: no cover - the failure itself
                pytest.fail(f"{err}: {slot['template'][:120]}")


def test_a_grown_title_header_moves_its_switch_with_it() -> None:
    """The title's switch is part of the header: it moves down with it."""
    body = [
        {"kind": "row", "cells": [{"type": "switch", "control": True}], "height": None},
        {"kind": "row", "cells": [{"type": "button", "control": True}], "height": 48},
    ]
    top = layout_card2(body, 376, 568, "title")
    middle = layout_card2(body, 376, 568, "title", centre=True)
    assert top["header_switch"] == middle["header_switch"] == 0
    shift = middle["header"]["title"][1] - top["header"]["title"][1]
    assert shift > 0
    assert middle["rects"][0][0][0][1] == top["rects"][0][0][0][1] + shift
    assert middle["rects"][1][0][0][1] == top["rects"][1][0][0][1] + shift
