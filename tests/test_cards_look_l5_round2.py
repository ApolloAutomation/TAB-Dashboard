"""The look of the cards after package L5's second round.

Each test holds one change made after L5's first verification: the off
copies past the page's track budget, a thermostat's "Now" never cut, a
Wide dropdown that says a choice it does not show, three fan presets in
two rows, and a `fits` width that never leaves its card.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.apollo_tab.maker.compile2 import (
    _Compiler2,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.convert import convert_dashboard
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.geometry import layout_card2
from custom_components.apollo_tab.maker.names import (
    NAME_W_SPARE,
    NUMBER_W,
    name_width,
    widest_number,
)
from tests.test_cards_look_l3 import _compile_at
from tests.test_cards_look_l5 import LAMP, OWNER, TUB
from tests.test_cards_step_a import COMPONENTS, _value
from tests.test_cards_step_b import _bindings, _run
from tests.test_maker_convert2 import ICONS, LAMP_FACTS, THEMES, _card, _dashboard


def _fan(presets: list[str]) -> dict:
    raw = {
        "domain": "fan",
        "registry": {
            "capabilities": {"preset_modes": presets, "percentage_step": 25},
            "features": ["SET_SPEED", "OSCILLATE", "DIRECTION", "PRESET_MODE"],
        },
    }
    return {"fan.a": facts_of(raw)}


def _inside(result: dict) -> bool:
    return all(
        w["r"][0] >= 0
        and w["r"][1] >= 0
        and w["r"][0] + w["r"][2] <= result["w"]
        and w["r"][1] + w["r"][3] <= result["h"]
        for w in result["widgets"]
    )


# ------------------------------------------------- the page's track budget


def _owner_page(count: int) -> dict:
    config = _dashboard(
        *[_card(variant="large", grid_options={"columns": 12, "rows": 6})] * count
    )
    config["views"][0]["max_columns"] = 4
    return convert_dashboard(
        config,
        components=COMPONENTS,
        themes=THEMES,
        approved=set(),
        facts={"light.h1401": LAMP_FACTS},
        dl=2,
        icons=ICONS,
    )


def test_a_bar_past_the_track_budget_shows_its_off_copy() -> None:
    """Critic major: the fourth owner's lamp drew a blank colour bar and a level.

    Its colour and white bars lose their tracks (six on a page). The copy
    with the palette and white icons shows instead, always; the bar that
    lost its colours never does, so it never reads as a second brightness.
    """
    result = _owner_page(4)
    cards = [
        item
        for page in result["layout"]["pages"][:1]
        for item in page["w"]
        if item["t"] == "card"
    ]
    assert len(cards) == 4
    last = [w for w in cards[3]["w"] if w["t"] == "slider"]
    # Brightness, then two copies each of colour and white.
    assert len(last) == 5
    for active, off in (last[1:3], last[3:5]):
        assert "track" not in active and active["vis"] is False
        assert off["r"] == active["r"] and "icon" in off and "vis" not in off
    for card in cards[:3]:
        assert sum("track" in w for w in card["w"]) == 2
    codes = [warning["code"] for warning in result["warnings"]]
    assert codes.count("over_budget_tracks") == 1


# ------------------------------------------------- the thermostat's "Now"


async def _tile_texts(
    hass: HomeAssistant, raw: dict, columns: int, rows: int, now: float
) -> list:
    params = {"entity": "climate.a"}
    result = _compile_at(
        "apollo/climate", "tile", columns, rows, params, {"climate.a": facts_of(raw)}
    )
    hass.states.async_set(
        "climate.a", "heat", {"temperature": 104.5, "current_temperature": now}
    )
    out = []
    for w in result["widgets"]:
        if w["t"] == "label" and w.get("size") == "s":
            text = w["text"]
            shown = await _value(hass, result, text) if isinstance(text, dict) else text
            out.append((w["r"][2], str(shown)))
    return out


@pytest.mark.parametrize(("columns", "rows"), [(6, 3), (6, 6), (6, 12), (12, 3)])
@pytest.mark.parametrize("now", [101.5, -18.5, 20])
async def test_the_temperature_now_is_never_cut(
    hass: HomeAssistant, columns: int, rows: int, now: float
) -> None:
    """Critic major: beside a whole "104.5°" the tile read "Now 1…".

    The text fits its label whole, or drops the word "Now", or shows
    nothing: never a cut number.
    """
    raw = {**TUB, "registry": {**TUB["registry"], "capabilities": {
        **TUB["registry"]["capabilities"], "min_temp": -30}}}  # fmt: skip
    [(width, text)] = await _tile_texts(hass, raw, columns, rows, now)
    number = f"{now:g}"
    assert text in (f"Now {number}", number, "")
    if text:
        assert name_width(text, 14) <= width * 10 - NAME_W_SPARE
    if columns == 12:
        assert text == f"Now {number}"


async def test_a_short_text_needs_a_template(hass: HomeAssistant) -> None:
    """`short` on a label with a fixed text changes nothing: it is bound as before."""
    compiler = _Compiler2(
        COMPONENTS["apollo/light"],
        validate_card_config2(COMPONENTS["apollo/light"], {"params": LAMP}),
        OWNER,
        2,
        None,
        False,
    )
    fixed = {"form": "const", "value": "Now"}
    short = {"form": "template", "template": "{{ 'N' }}"}
    assert compiler._short_text({"text": fixed, "short": short}, {}, 40, "s") is None


# ------------------------------------------------- the Wide dropdown's choice

PROGRAMMES = [f"Programme {n}" for n in range(1, 17)]
WASHER = {
    "select.m": facts_of(
        {"domain": "select", "registry": {"capabilities": {"options": PROGRAMMES}}}
    )
}


@pytest.mark.parametrize(
    ("state", "shown"), [("Programme 12", "Programme 12"), ("Programme 2", "")]
)
async def test_a_wide_dropdown_says_a_choice_it_does_not_show(
    hass: HomeAssistant, state: str, shown: str
) -> None:
    """Critic major: at "Programme 12" with the first 8 shown no cell was lit.

    The Wide says the choice at its title's right; while it is among the
    cells shown, the line is empty.
    """
    result = _compile_at("apollo/select", "wide", 12, 3, {"entity": "select.m"}, WASHER)
    assert result["variant"] == "wide"
    line = next(w for w in result["widgets"] if w["t"] == "label" and w.get("al") == 2)
    title = result["header"]["r"]
    assert line["r"][0] >= title[0] + title[2]
    assert line["r"][0] + line["r"][2] <= result["w"] - 16
    hass.states.async_set("select.m", state)
    assert await _value(hass, result, line["text"]) == shown


async def test_a_wide_dropdown_with_no_choices_says_its_state_once(
    hass: HomeAssistant,
) -> None:
    """With no choices the line under the title says it; the title's right is empty."""
    result = _compile_at("apollo/select", "wide", 12, 3, {"entity": "select.m"}, {})
    hass.states.async_set("select.m", "unavailable")
    texts = []
    for w in result["widgets"]:
        if w["t"] == "label" and isinstance(w.get("text"), dict):
            texts.append(await _value(hass, result, w["text"]))
    assert texts.count("unavailable") == 1


def test_a_narrow_title_keeps_its_room() -> None:
    """At six columns the title keeps the whole line: no state at its right."""
    laid = layout_card2([], 184, 184, "title", title_state=True)
    assert set(laid["header"]) == {"title"}
    laid = layout_card2([], 376, 184, "title", title_state=True)
    assert set(laid["header"]) == {"title", "state"}
    assert set(layout_card2([], 376, 184, "title")["header"]) == {"title"}


# ------------------------------------------------- three fan presets


def test_three_fan_presets_take_two_rows_in_six_columns() -> None:
    """Critic major: in six columns one row of three cut "breeze".

    Two rows show each preset whole. At twelve columns they keep one row.
    """
    params = {"entity": "fan.a"}
    three = _fan(["auto", "sleep", "breeze"])
    result = _compile_at("apollo/fan-speed", "large", 6, 12, params, three)
    [choice] = [w for w in result["widgets"] if w["t"] == "choice"]
    assert choice["rows"] == 2
    assert choice["texts"] == ["auto", "sleep", "breeze"]
    own = _compile_at("apollo/fan-speed", "large", 12, 6, params, three)
    [choice] = [w for w in own["widgets"] if w["t"] == "choice"]
    assert choice["rows"] == 1


def test_more_rows_for_whole_texts_never_cost_a_row() -> None:
    """Five presets at 6x6 would need three rows: the card keeps its rows.

    The presets stay in the rows a finger needs (cut).
    """
    params = {"entity": "fan.a"}
    five = _fan(["auto", "sleep", "breeze", "turbo", "night"])
    large = _compile_at("apollo/fan-speed", "large", 6, 6, params, five)
    assert "element_clipped" not in large["warnings"]
    [choice] = [w for w in large["widgets"] if w["t"] == "choice"]
    assert choice["rows"] == 2


# ------------------------------------------------- `fits` stays in the card


@pytest.mark.parametrize("high", [1e300, 3.4028e38, 1e9])
def test_a_huge_range_never_pushes_a_widget_out_of_its_card(high: float) -> None:
    """Security major: max_temp 1e300 made a target label 5133 px wide."""
    raw = {
        "domain": "climate",
        "registry": {
            "capabilities": {
                "hvac_modes": ["off", "heat"],
                "min_temp": 0,
                "max_temp": high,
                "target_temp_step": 0.1,
            },
            "features": ["TARGET_TEMPERATURE"],
        },
    }
    assert widest_number(0, high, 0.1, "°", 28) > 184
    for columns, rows in ((6, 3), (12, 3)):
        result = _compile_at(
            "apollo/climate", "tile", columns, rows, {"entity": "climate.a"},
            {"climate.a": facts_of(raw)},
        )  # fmt: skip
        assert result["variant"] == "tile"
        assert _inside(result), [w["r"] for w in result["widgets"]]


# ------------------------------------------------- the number's rounding


async def test_a_number_steps_down_from_just_over_a_step(hass: HomeAssistant) -> None:
    """Tester minor: 2.1 / 0.3 is 7.000000000000001; minus still gives 1.8.

    Without rounding to the grid it gave 2.1 again (the ceiling of 7.0...1
    is 8); without the last rounding 1.7999999999999998. Plus from 0.3 on
    a step of 0.1 (2.9999999999999996 steps) gives 0.4.
    """
    calls = async_mock_service(hass, "number", "set_value")
    for entity, step, now, way, expected in (
        ("number.a", 0.3, "2.1", "down", 1.8),
        ("number.b", 0.1, "0.3", "up", 0.4),
    ):
        raw = {
            "domain": "number",
            "registry": {"capabilities": {"min": 0, "max": 3, "step": step}},
        }
        buttons = _bindings(
            "apollo/number", {"entity": entity}, {entity: facts_of(raw)},
            variant="wide", options={"control": "buttons"},
        )  # fmt: skip
        hass.states.async_set(entity, now)
        await _run(hass, buttons[way])
        assert calls[-1].data["value"] == expected


# ------------------------------------------------- branches without a test


def test_a_choice_with_icons_leaves_its_text_less_room() -> None:
    """A cell's icon takes 24 + 6 px of its text's room (_cut_choice_texts)."""
    compiler = _Compiler2(
        COMPONENTS["apollo/light"],
        validate_card_config2(COMPONENTS["apollo/light"], {"params": LAMP}),
        OWNER,
        2,
        None,
        False,
    )
    widget = {"r": [0, 0, 100, 48], "rows": 1, "texts": ["Breakfast"]}
    assert compiler._cut_choice_texts(widget, 1) == ["Breakfast"]
    with_icon = {**widget, "icons": ["mdi:food"]}
    assert compiler._cut_choice_texts(with_icon, 1) != ["Breakfast"]


def test_a_range_across_zero_measures_minus_zero() -> None:
    """-0.5 is drawn "-0.5": -0.9 to 0.9 is as wide as its widest "-0.d"."""
    widest = max(sum(NUMBER_W[28][c] for c in f"-0.{d}") for d in range(1, 10))
    assert widest_number(-0.9, 0.9, 0.1, "", 28) == -(-(widest + NAME_W_SPARE) // 10)


def test_a_thermostat_tile_without_a_target_says_it_at_the_left() -> None:
    """Critic minor: "unavailable" was centred where the target starts at the left."""
    raw = {"climate.a": facts_of(TUB)}
    result = _compile_at("apollo/climate", "tile", 6, 3, {"entity": "climate.a"}, raw)
    target = next(w for w in result["widgets"] if w.get("px") == 28)
    state = next(
        w
        for w in result["widgets"]
        if w["t"] == "label" and w.get("size") == "m" and w["r"][1] == target["r"][1]
    )
    assert state.get("al", 0) == 0
    assert state["r"][0] == target["r"][0]
