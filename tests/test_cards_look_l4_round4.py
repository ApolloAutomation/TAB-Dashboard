"""The look of the cards after round 4 of package L4.

Each test holds one change of round 4: no bar of a grown card is taller
than it is wide, the grown lamp that only dims, the Thermostat Tile's
target under its name, a value written with marks that strip white space,
and the order in which a lamp's rows go.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.apollo_tab.maker.compile2 import (
    compile_card2,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.geometry import (
    FOOT_CENTRE_MIN,
    GAP,
    PAD,
    layout_card2,
)
from tests.test_cards_look_l3 import OWNERS_LAMP_RAW, _compile_at
from tests.test_cards_look_l4_round3 import _stranger
from tests.test_cards_step_a import DIM_LAMP_RAW, _value

# ---------------------------------------------------------------- grown bars

BAR = {"type": "slider", "look": "bar", "control": True, "grow": True}


def _bar_row(**marks: int) -> dict:
    return {"kind": "row", "cells": [{**BAR, **marks}], "height": None}


@pytest.mark.parametrize("width", [184, 376])
def test_a_grown_bar_is_never_taller_than_wide(width: int) -> None:
    """Critic major: the owner's Light Tile at 6x12 drew a bar 152 by 584.

    A bar fills from left to right, so taller than wide it read as an
    upright fader that moves sideways. In a card drawn larger than its grid
    a bar stops at its width; the foot is shared as for any grown card.
    """
    laid = layout_card2([_bar_row()], width, 696, "tile", centre=True)
    [[bar]] = laid["rects"][0]
    assert bar[2] == width - 2 * PAD and bar[3] == bar[2]
    head_bottom = max(r[1] + r[3] for r in laid["header"].values())
    assert bar[1] == head_bottom + GAP
    above = min(r[1] for r in laid["header"].values()) - PAD
    assert abs(above - (696 - PAD - (bar[1] + bar[3]))) <= 1


def test_a_bar_at_its_own_size_takes_the_height() -> None:
    """The rule is for grown cards: at its own size a card fills as before."""
    laid = layout_card2([_bar_row()], 184, 696, "tile")
    [[bar]] = laid["rects"][0]
    assert bar[3] == 696 - 2 * PAD - 48 - GAP


@pytest.mark.parametrize("most_grown", [120, 320])
def test_a_grown_bar_with_its_own_cap_keeps_it(most_grown: int) -> None:
    """A row's own `most_grown` holds: its file says how far it goes.

    The owner's lamp at 6x12 keeps brightness at 320 over colour and white.
    """
    row = _bar_row(most=96, most_grown=most_grown)
    laid = layout_card2([row], 184, 696, "tile", centre=True)
    assert laid["rects"][0][0][0][3] == most_grown


def test_a_grown_row_without_a_bar_is_not_held_to_its_width() -> None:
    """Only a bar a finger moves: a button row still grows as its file says."""
    row = {
        "kind": "row",
        "cells": [{"type": "button", "control": True, "grow": True}],
        "height": None,
    }
    laid = layout_card2([row], 184, 696, "tile", centre=True)
    assert laid["rects"][0][0][0][3] > 184


@pytest.mark.parametrize(
    ("component_id", "variant", "params", "raw"),
    [
        ("apollo/light", "tile", {"entity": "light.a"}, OWNERS_LAMP_RAW),
        ("apollo/light", "wide", {"entity": "light.a"}, OWNERS_LAMP_RAW),
        ("apollo/light", "tile", {"entity": "light.a"}, DIM_LAMP_RAW),
        ("apollo/light-group", "tile", {"lights": ["light.a", "light.b"]}, None),
        ("apollo/number", "wide", {"entity": "input_number.a"}, None),
        ("apollo/screen", "wide", {"entity": "light.a"}, None),
    ],
)
@pytest.mark.parametrize(("columns", "rows"), [(6, 6), (6, 12), (12, 12)])
def test_no_card_grows_a_bar_taller_than_wide(
    component_id: str,
    variant: str,
    params: dict,
    raw: dict | None,
    columns: int,
    rows: int,
) -> None:
    """Item g: the owner's Light Tile at 6x12, and every card with such a bar."""
    facts = {} if raw is None else {params["entity"]: facts_of(raw)}
    result = _compile_at(component_id, variant, columns, rows, params, facts)
    bars = [w for w in result["widgets"] if w["t"] == "slider"]
    assert bars
    for bar in bars:
        assert bar["r"][3] <= bar["r"][2], bar["r"]
    # Nothing between the header and the rows; the foot is shared.
    top = min(w["r"][1] for w in result["widgets"]) - PAD
    foot = result["h"] - PAD - max(w["r"][1] + w["r"][3] for w in result["widgets"])
    assert abs(top - foot) <= 1 or (top == 0 and foot <= FOOT_CENTRE_MIN)


# ---------------------------------------------------------------- dim only


@pytest.mark.parametrize("rows", [6, 8, 12])
def test_the_dim_only_lamp_has_no_band_over_56(rows: int) -> None:
    """Critic major: at 12x12 two bands of 95 px, above and under "40%".

    The number's row stops at 152 (its glyph is 68 high, so 42 above and
    under it) and the bar takes the height: no band inside the block is
    over 56, at the card's own size and grown.
    """
    result = _compile_at(
        "apollo/light", "large", 12, rows, {"entity": "light.a"},
        {"light.a": facts_of(DIM_LAMP_RAW)},
    )  # fmt: skip
    number = next(w for w in result["widgets"] if w["t"] == "label" and w["r"][3] > 100)
    [bar] = [w for w in result["widgets"] if w["t"] == "slider"]
    header_bottom = max(
        w["r"][1] + w["r"][3] for w in result["widgets"] if w["r"][1] < number["r"][1]
    )
    glyph = 68
    band = (number["r"][3] - glyph) // 2 + GAP
    assert number["r"][1] - header_bottom <= GAP + 2
    assert band <= FOOT_CENTRE_MIN
    assert bar["r"][1] == number["r"][1] + number["r"][3] + GAP
    assert bar["r"][3] == {6: 128, 8: 256, 12: 320}[rows]


# ---------------------------------------------------------------- thermostat


@pytest.mark.parametrize(("columns", "rows"), [(6, 3), (12, 6)])
async def test_the_thermostat_tile_target_starts_under_its_name(
    hass: HomeAssistant, columns: int, rows: int
) -> None:
    """Tester and critic minor: at 12x6 the target sat against the right edge.

    The target starts at the card's left edge, under the name, and "Now
    20.5" follows it, at every width.
    """
    result = _compile_at(
        "apollo/climate", "tile", columns, rows, {"entity": "climate.a"}, {}
    )
    target = next(w for w in result["widgets"] if w.get("px") == 28)
    assert target["r"][0] == PAD and target.get("al", 0) == 0
    now = next(
        w
        for w in result["widgets"]
        if w.get("size") == "s" and w["r"][1] == target["r"][1]
    )
    assert now["r"][0] == target["r"][0] + target["r"][2] + GAP
    assert now.get("al", 0) == 0 and now["r"][2] >= 70
    hass.states.async_set(
        "climate.a", "heat", {"temperature": 21.5, "current_temperature": 20.5}
    )
    assert await _value(hass, result, target["text"]) == "21.5°"
    assert await _value(hass, result, now["text"]) == "Now 20.5"


# ---------------------------------------------------------------- value splice


@pytest.mark.parametrize(
    "value_text",
    ["{{- states(e) }}", "{{ states(e) -}}", "{{- states(e) -}}", "{{ -1 }}"],
)
async def test_a_value_with_strip_marks_keeps_the_name(
    hass: HomeAssistant, value_text: str
) -> None:
    """Security minor: "{{- x }}" was spliced as "(- x)", and the name failed.

    The marks that strip white space are not part of the expression.
    """
    component = _stranger("{{ state_attr(e, 'friendly_name') or e }}", value_text)
    raw = {
        "params": {"entity": ["sensor.a"]},
        "variant": "main",
        "grid_options": {"columns": 12, "rows": 3},
    }
    result = compile_card2(component, validate_card_config2(component, raw), {}, 2)
    name = next(
        w for w in result["widgets"] if w["t"] == "label" and w.get("al", 0) == 0
        and isinstance(w.get("text"), dict)
    )  # fmt: skip
    # The name has the line to the value's end: its room is measured from
    # the value, so the value's expression was taken whole.
    value = next(w for w in result["widgets"] if w.get("al") == 2)
    assert name["r"][0] + name["r"][2] == value["r"][0] + value["r"][2]
    hass.states.async_set("sensor.a", "21.4", {"friendly_name": "Kitchen"})
    assert await _value(hass, result, name["text"]) == "Kitchen"


# ---------------------------------------------------------------- rows that go


def _bars(result: dict) -> list[str]:
    """Return what each bar of a lamp is, by its icon or its track."""
    names = []
    for widget in result["widgets"]:
        if widget["t"] != "slider":
            continue
        icon = widget.get("icon")
        if icon == "mdi:brightness-6":
            names.append("dim")
        elif icon == "mdi:palette-outline":
            names.append("sat")
        elif "track" in widget:
            names.append("hue" if widget["max"] == 360 else "white")
    return names


@pytest.mark.parametrize(
    ("rows", "bars", "dots"),
    [
        (9, ["dim", "hue", "sat", "white"], True),
        (5, ["dim", "hue", "sat", "white"], False),
        (4, ["dim", "hue", "white"], False),
    ],
)
def test_a_lamp_lets_go_of_dots_then_strength_and_keeps_white(
    rows: int, bars: list[str], dots: bool
) -> None:
    """Tester minor: decision 11's order had no test of what the card shows.

    The favourite dots go first, then colour strength; white stays.
    """
    result = _compile_at(
        "apollo/light", "large", 12, rows, {"entity": "light.a"},
        {"light.a": facts_of(OWNERS_LAMP_RAW)},
        {"show_saturation": True, "colour_control": "both"},
    )  # fmt: skip
    assert _bars(result) == bars
    assert bool([w for w in result["widgets"] if w["t"] == "choice"]) is dots
    assert result["warnings"] == []
