"""The look review of every card in every size, after its third check (L2).

Each test here holds one finding of the third tester and critic fixed.
"""

from __future__ import annotations

import copy
import re

import pytest
from homeassistant.core import HomeAssistant

from custom_components.apollo_tab.maker.compile2 import (
    compile_card2,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.geometry import layout_card2
from custom_components.apollo_tab.maker.schema import validate_component
from tests.test_cards_step_a import COMPONENTS, DIM_LAMP_RAW, _value
from tests.test_cards_step_b import ALARM_RAW, CLIMATE_RAW, FAN_RAW, MEDIA_RAW, _compile
from tests.test_maker_schema2 import _doc

# "unavailable" at the size of a state line, as the tablet's font draws it.
UNAVAILABLE_W = 82
GONE = ("unavailable", "unknown")


def _at(
    component: dict,
    variant: str,
    columns: int,
    rows: int,
    params: dict,
    facts: dict | None = None,
) -> dict:
    """Compile a variant at a grid of its own."""
    raw = {
        "params": params,
        "variant": variant,
        "grid_options": {"columns": columns, "rows": rows},
    }
    return compile_card2(
        component, validate_card_config2(component, raw), facts or {}, 2
    )


def _lone(options: int, rows: int) -> bool:
    """Return whether the last row of a choice holds one cell beside a hole."""
    per_row = -(-options // rows)
    return rows > 1 and per_row > 1 and options - per_row * (rows - 1) == 1


def _cell_w(options: int, rows: int, width: int) -> int:
    """Return the width of a choice's cells in this many rows."""
    per_row = -(-options // rows)
    return (width - 8 * (per_row - 1)) // per_row


# ---------------------------------------------------------------- choices


@pytest.mark.parametrize("options", range(2, 13))
@pytest.mark.parametrize("first_rows", [1, 2])
def test_a_grown_choice_never_leaves_a_cell_alone(
    options: int, first_rows: int
) -> None:
    """Major: a choice that grows put the lone cell back (3 cells as 2 and 1).

    The rule against tall pillars ran after the rule against a lone cell.
    """
    cell = {
        "type": "choice",
        "rows": first_rows,
        "options": options,
        "grow": True,
        "control": True,
    }
    row = {"kind": "row", "height": None, "cells": [cell]}
    for width in (184, 376, 568, 760):
        for height in range(120, 800, 40):
            laid = layout_card2([row], width, height, align_top=True)
            if laid["rows"][0] is None or laid["rows"][0][0][0] is None:
                continue  # no room for the choice at all
            rows = laid["rows"][0][0][0]
            if not _lone(options, rows):
                continue
            # One cell alone only where every other count of rows would
            # make the cells too narrow for a finger, or does not fit.
            others = [
                count
                for count in range(1, 5)
                if not _lone(options, count)
                and _cell_w(options, count, width - 32) >= 44
                and count * 48 + 8 * (count - 1) <= height - 32
            ]
            assert not others, (options, width, height, rows, others)


def test_three_grown_cells_go_from_one_row_to_three() -> None:
    """Three cells too tall for one row stand under each other, not 2 and 1."""
    cell = {"type": "choice", "rows": 1, "options": 3, "grow": True, "control": True}
    row = {"kind": "row", "height": None, "cells": [cell]}
    assert layout_card2([row], 376, 200, align_top=True)["rows"][0][0][0] == 1
    assert layout_card2([row], 376, 376, align_top=True)["rows"][0][0][0] == 3
    five = {**row, "cells": [{**cell, "options": 5}]}
    # 3 and 2, never 2, 2 and 1.
    assert layout_card2([five], 376, 760, align_top=True)["rows"][0][0][0] in (2, 5)


def test_a_dropdown_and_a_fan_with_three_choices_leave_no_hole() -> None:
    """The tester's cases: Dropdown Large, Fan Large at 12x8 and 12x12."""
    three = {"domain": "select", "registry": {"capabilities": {"options": list("abc")}}}
    select = _at(
        COMPONENTS["apollo/select"],
        "large",
        12,
        6,
        {"entity": "select.a"},
        {"select.a": facts_of(three)},
    )
    [choice] = [w for w in select["widgets"] if w["t"] == "choice"]
    assert not _lone(3, choice.get("rows", 1)), choice
    for presets, grids in ((3, ((12, 6), (12, 8), (12, 12))), (5, ((12, 12),))):
        raw = copy.deepcopy(FAN_RAW)
        modes = raw["registry"]["capabilities"]["preset_modes"][:presets]
        raw["registry"]["capabilities"]["preset_modes"] = modes
        for columns, rows in grids:
            fan = _at(
                COMPONENTS["apollo/fan-speed"],
                "large",
                columns,
                rows,
                {"entity": "fan.a"},
                {"fan.a": facts_of(raw)},
            )
            [choice] = [w for w in fan["widgets"] if w["t"] == "choice"]
            assert not _lone(presets, choice.get("rows", 1)), (presets, rows, choice)


# ---------------------------------------------------------------- unavailable


def test_a_chip_has_room_for_the_word_unavailable() -> None:
    """Major: Switch chip, Screen row and Volume row cut it to "unavailab…".

    The chip's state had 80 px; the word is 82 px wide.
    """
    assert layout_card2([], 376, 56, "chip")["header"]["state"][2] >= UNAVAILABLE_W
    cards = [
        ("apollo/switch", "chip", "switch.a", {}),
        ("apollo/screen", "row", "light.a", {"light.a": facts_of(DIM_LAMP_RAW)}),
        ("apollo/volume", "row", "media_player.a", {}),
    ]
    for component_id, variant, entity, facts in cards:
        result = _compile(
            COMPONENTS[component_id], variant, {"entity": entity}, {}, facts
        )
        state = next(
            w for w in result["widgets"] if w["t"] == "label" and w.get("al", 0) == 2
        )
        assert state["r"][2] >= UNAVAILABLE_W, component_id
        assert state["r"][0] + state["r"][2] == result["w"] - 16, component_id


async def test_the_room_caption_has_no_unit_while_its_device_is_gone(
    hass: HomeAssistant,
) -> None:
    """Major: "House Power: unavailable W"."""
    room = COMPONENTS["apollo/room"]
    result = _compile(room, "room", {"extra": "sensor.p"}, {}, {})
    labels = [w for w in result["widgets"] if w["t"] == "label"]
    attributes = {"friendly_name": "House Power", "unit_of_measurement": "W"}

    async def caption() -> str:
        texts = [
            await _value(hass, result, w["text"])
            for w in labels
            if isinstance(w["text"], dict)
        ]
        # LOOK-NOTES decision 14: the name and the value are two labels
        # side by side; the value is never cut.
        start = next(i for i, t in enumerate(texts) if str(t) == "House Power")
        return ": ".join(str(t) for t in texts[start : start + 2])

    hass.states.async_set("sensor.p", "1840", attributes)
    assert await caption() == "House Power: 1840 W"
    for state in GONE:
        hass.states.async_set("sensor.p", state, attributes)
        assert await caption() == "House Power: —"


async def test_the_alarm_has_no_button_while_it_is_gone(hass: HomeAssistant) -> None:
    """Minor: "Disarm" stayed on a panel that was gone; the lock hid its button."""
    alarm = COMPONENTS["apollo/alarm"]
    for variant in ("wide", "large"):
        result = _compile(
            alarm,
            variant,
            {"entity": "alarm_control_panel.a"},
            {},
            {"alarm_control_panel.a": facts_of(ALARM_RAW)},
        )
        shown = [
            w["vis"]
            for w in result["widgets"]
            if "vis" in w and (w["t"] == "button" or "tap" in w)
        ]
        assert shown, variant
        for state in GONE:
            hass.states.async_set("alarm_control_panel.a", state)
            assert [await _value(hass, result, v) for v in shown] == [False] * len(
                shown
            ), (variant, state)
        hass.states.async_set("alarm_control_panel.a", "armed_away")
        assert True in [await _value(hass, result, v) for v in shown], variant
        hass.states.async_set("alarm_control_panel.a", "triggered")
        assert True in [await _value(hass, result, v) for v in shown], variant


# ---------------------------------------------------------------- 3 by 1

ALONE = {
    "apollo/clock": ("wide", {}),
    "apollo/dial": ("tile", {"entity": "sensor.a", "max": 5000}),
    "apollo/forecast": ("wide", {"entity": "weather.a"}),
    "apollo/graph": ("wide", {"entity": "sensor.a"}),
    "apollo/number": ("row", {"entity": "number.a"}),
    "apollo/reading": ("chip", {"entity": "sensor.a"}),
    "apollo/volume": ("row", {"entity": "media_player.a"}),
}


def test_the_cards_that_show_a_value_alone() -> None:
    """Exactly the cards whose purpose is a reading name one."""
    named = {
        component_id
        for component_id, component in COMPONENTS.items()
        if component.get("schema") == 2 and component["alone"] is not None
    }
    assert named == set(ALONE)


async def test_a_reading_card_at_3_by_1_shows_its_value(hass: HomeAssistant) -> None:
    """Major: at 3x1 a clock showed a clock icon, a sensor card a thermometer.

    The value alone, in the middle, and a dash while the device is gone.
    """
    hass.states.async_set("sensor.a", "1840", {"unit_of_measurement": "W"})
    hass.states.async_set("number.a", "21", {"unit_of_measurement": "°C"})
    hass.states.async_set("weather.a", "sunny", {"temperature": 17.6})
    hass.states.async_set("media_player.a", "playing", {"volume_level": 0.64})
    want = {
        "apollo/dial": "1840",
        "apollo/forecast": "18°",
        "apollo/graph": "1840 W",
        "apollo/number": "21 °C",
        "apollo/reading": "1840.0 W",
        "apollo/volume": "64%",
    }
    results = {}
    for component_id, (variant, params) in ALONE.items():
        result = _at(COMPONENTS[component_id], variant, 3, 1, params)
        results[component_id] = result
        assert result["header"] is None, component_id
        assert result["warnings"] in ([], ["element_clipped"]), component_id
        [value] = result["widgets"]
        assert (value["t"], value["size"], value["al"]) == ("label", "m", 1)
        x, y, width, height = value["r"]
        assert (x * 2 + width, y * 2 + height) == (result["w"], result["h"])
        text = await _value(hass, result, value["text"])
        if component_id == "apollo/clock":
            assert re.fullmatch(r"\d\d:\d\d", text), text
        else:
            assert str(text) == want[component_id], component_id
    for entity in ("sensor.a", "number.a", "weather.a", "media_player.a"):
        hass.states.async_set(entity, "unavailable")
    for component_id, result in results.items():
        if component_id == "apollo/clock":
            continue
        [value] = result["widgets"]
        assert await _value(hass, result, value["text"]) == "—", component_id


def test_a_card_with_room_for_more_does_not_show_its_value_alone() -> None:
    """One step larger than 3x1 the card is as it was: `alone` is the last resort."""
    for component_id, (variant, params) in ALONE.items():
        component = COMPONENTS[component_id]
        columns, rows = component["variants"][variant]["grid"]
        result = _at(component, variant, columns, rows, params)
        drawn = len(result["widgets"]) + (result["header"] is not None)
        assert drawn > 1, component_id


def test_alone_is_an_input_or_a_template() -> None:
    """The card file's `alone` is checked like `state`."""
    doc = _doc(inputs={"shown": "{{ states(entity) }}"}, alone="shown")
    assert validate_component(doc)["alone"] is not None
    assert validate_component(_doc())["alone"] is None
    with pytest.raises(MakerError):
        validate_component(_doc(alone=["shown"]))


# ---------------------------------------------------------------- minors


def test_the_large_thermostat_has_its_buttons_at_the_foot_of_the_arc() -> None:
    """Minor: on Large the - and + sat in the card's corners, 90 px off the arc."""
    result = _compile(
        COMPONENTS["apollo/climate"],
        "large",
        {"entity": "climate.a"},
        {},
        {"climate.a": facts_of(CLIMATE_RAW)},
    )
    [dial] = [w for w in result["widgets"] if w["t"] == "thermostat"]
    x, _y, width, height = dial["r"]
    assert x * 2 + width == result["w"]
    assert width <= 264 and width <= height * 2


def test_shuffle_has_an_icon_as_power_has() -> None:
    """Minor: two buttons in one row, one with an icon and one without."""
    result = _compile(
        COMPONENTS["apollo/media"],
        "full",
        {"entity": "media_player.a"},
        {},
        {"media_player.a": facts_of(MEDIA_RAW)},
    )
    buttons = {w.get("text"): w for w in result["widgets"] if w["t"] == "button"}
    assert buttons["Shuffle"]["icon"] == "mdi:shuffle"
    assert buttons["Power"]["icon"] == "mdi:power"


def test_the_room_button_says_what_a_tap_does() -> None:
    """Minor: "Lights off" under "2 of 3 on" read as a state, not an action."""
    room = COMPONENTS["apollo/room"]
    result = _compile(room, "room", {"lights": ["light.a", "light.b"]}, {}, {})
    texts = [w["text"] for w in result["widgets"] if w["t"] == "button"]
    assert texts == ["Turn all off", "Turn all on"]
