"""The look of the cards after the round 2 decisions, and security minors (L3).

Each test holds one of LOOK-NOTES decisions 10 to 14, or one minor of the
security review of I10 and I11.
"""

from __future__ import annotations

from unittest.mock import patch

import jinja2
import pytest
from homeassistant.core import Context, HomeAssistant, ServiceCall, SupportsResponse
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.apollo_tab import live
from custom_components.apollo_tab.live import CallError, async_run_output
from custom_components.apollo_tab.maker.compile2 import (
    MAX_FETCHES_2,
    _Compiler2,
    compile_card2,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.geometry import (
    TILE_NAME_ONLY_H,
    TILE_STACKED_H,
    layout_card2,
)
from custom_components.apollo_tab.maker.schema import validate_component
from tests.test_cards_step_a import (
    COMPONENTS,
    DIM_LAMP_RAW,
    _all_on,
    _facts,
    _param_values,
    _value,
)
from tests.test_cards_step_b import (
    BLIND_RAW,
    FAN_RAW,
    MEDIA_RAW,
    _bindings,
    _compile,
    _run,
)
from tests.test_maker_schema import _toggle_doc
from tests.test_maker_schema2 import _doc

# The owner's lamp: brightness, colour and white from 2000 to 6500 K.
OWNERS_LAMP_RAW = {
    "domain": "light",
    "registry": {
        "capabilities": {
            "supported_color_modes": ["color_temp", "hs"],
            "min_color_temp_kelvin": 2000,
            "max_color_temp_kelvin": 6500,
        }
    },
    "state": {"attributes": {"supported_color_modes": ["color_temp", "hs"]}},
}
SENSORS = [f"sensor.s{n}" for n in range(8)]


def _bar(row: dict) -> dict:
    """Return a geometry row of one touch slider."""
    return {"kind": "row", "cells": [{"type": "slider", "control": True}], **row}


def _compile_at(
    component_id: str,
    variant: str,
    columns: int,
    rows: int,
    params: dict,
    facts: dict,
    options: dict | None = None,
) -> dict:
    """Compile a variant at a size of its grid other than its own."""
    component = COMPONENTS[component_id]
    raw = {
        "params": params,
        "options": options or {},
        "variant": variant,
        "grid_options": {"columns": columns, "rows": rows},
    }
    card = validate_card_config2(component, raw)
    return compile_card2(component, card, facts, 2)


def _bottom(result: dict) -> int:
    """Return the foot of the lowest widget of a card."""
    return max(w["r"][1] + w["r"][3] for w in result["widgets"])


def _top(result: dict) -> int:
    """Return the room above the highest widget of a card, inside its padding."""
    return min(w["r"][1] for w in result["widgets"]) - 16


def _centred(result: dict) -> bool:
    """Return whether a card's content sits in its vertical middle (L4)."""
    return abs(_top(result) - (result["h"] - 16 - _bottom(result))) <= 1


def _body_room(result: dict, head: int) -> tuple[int, int]:
    """Return the room above and under the body of a card under its header.

    head: the header's height. The body is every widget under the header's
    gap; the header starts at the highest widget (L4 round 3: it moves with
    the rows).
    """
    start = 16 + _top(result) + head + 8
    body = [w for w in result["widgets"] if w["r"][1] >= start]
    top = min(w["r"][1] for w in body)
    bottom = max(w["r"][1] + w["r"][3] for w in body)
    return top - start, result["h"] - 16 - bottom


def _body_centred(result: dict, head: int) -> bool:
    """Return whether header and body sit together in the card's middle.

    L4 round 2 kept the header at the top and left a band under it; round
    3 (critic major): the body follows the header with the theme's gap and
    the two move down together, with equal room above and under them.
    """
    return _body_room(result, head)[0] == 0 and _centred(result)


# ---------------------------------------------------------------- geometry


def test_rows_with_drop_go_first_and_say_nothing() -> None:
    """Decision 11: the dots go first, then saturation; no clipped warning."""
    body = [
        _bar({"height": 96}),
        _bar({"height": 48}),
        _bar({"height": 48, "drop": 2}),
        _bar({"height": 48}),
        _bar({"height": 48, "drop": 1}),
    ]
    laid = layout_card2(body, 376, 376, "tile")
    assert laid["let_go"] == [4]
    assert laid["clipped"] == []
    assert [rect is not None for rect in laid["rects"]] == [1, 1, 1, 1, 0]
    low = layout_card2(body, 376, 312, "tile")
    assert low["let_go"] == [2, 4]
    assert low["clipped"] == []


def test_a_row_with_most_stops_there() -> None:
    """Decision 12: List and People rows grow to 56 px at most."""
    body = [
        {"kind": "row", "cells": [{"type": "label", "size": "m", "grow": True}],
         "height": None, "most": 56}
        for _ in range(3)
    ]  # fmt: skip
    laid = layout_card2(body, 376, 376, "title")
    heights = [rect[0][0][3] for rect in laid["rects"]]
    assert heights == [56, 56, 56]
    # Without `most` the three rows share the whole card.
    for row in body:
        row.pop("most")
    shared = layout_card2(body, 376, 376, "title")
    assert [rect[0][0][3] for rect in shared["rects"]] != [56, 56, 56]


def test_the_dial_follows_the_free_height() -> None:
    """Decision 12: a thermostat that grows is as wide as the free height."""
    dial = {"type": "thermostat", "width": 152, "grow": True}
    laid = layout_card2(
        [{"kind": "row", "cells": [dial], "height": None}], 376, 376, "tile"
    )
    x, _y, w, h = laid["rects"][0][0][0]
    assert w == min(344, h) and w > 152
    assert x == 16 + (344 - w) // 2


# ---------------------------------------------------------------- tile sliders


@pytest.mark.parametrize(
    ("component_id", "entity", "raw"),
    [
        ("apollo/light", "light.a", DIM_LAMP_RAW),
        ("apollo/fan-speed", "fan.a", FAN_RAW),
        ("apollo/cover", "cover.a", BLIND_RAW),
    ],
)
def test_a_tile_has_the_tile_header_and_a_tall_bar(
    component_id: str, entity: str, raw: dict
) -> None:
    """Decision 10: header tile, then the bar takes the rest of the tile.

    On six columns the header stacks (the name across the tile), so the bar
    starts under 72 px of header, not 48.
    """
    result = _compile(
        COMPONENTS[component_id],
        "tile",
        {"entity": entity},
        {},
        {entity: facts_of(raw)},
    )
    assert COMPONENTS[component_id]["variants"]["tile"]["header"] == "tile"
    [bar] = [w for w in result["widgets"] if w["t"] == "slider"]
    top = 16 + TILE_STACKED_H + 8
    assert bar["r"] == [16, top, 152, 184 - 16 - top]


def test_the_cover_tile_has_the_tile_header() -> None:
    """Decision 10: Blinds and doors Tile takes the same layout."""
    variant = COMPONENTS["apollo/cover"]["variants"]["tile"]
    assert variant["header"] == "tile"


def test_no_touch_slider_is_under_48_px() -> None:
    """Decision 10: on any card, in any size, with any options."""
    low = []
    for component_id, component in COMPONENTS.items():
        if component.get("schema") != 2:
            continue
        for variant in component["variants"]:
            params, entities = _param_values(component, 4)
            facts = {e: _facts(e.split(".", 1)[0], True) for e in entities}
            first = facts[entities[0]] if entities else {}
            for options in _all_on(component, first):
                result = _compile(component, variant, params, options, facts)
                low.extend(
                    (component_id, variant, w["r"][3])
                    for w in result["widgets"]
                    if w["t"] == "slider" and "change" in w and w["r"][3] < 48
                )
    assert low == []


# ---------------------------------------------------------------- growth


def test_the_owners_lamp_keeps_its_three_bars_on_large() -> None:
    """Decision 11: brightness, colour and white, each at least 48 px."""
    facts = {"light.h1401": facts_of(OWNERS_LAMP_RAW)}
    result = _compile(
        COMPONENTS["apollo/light"], "large", {"entity": "light.h1401"}, {}, facts
    )
    bars = [w for w in result["widgets"] if w["t"] == "slider"]
    assert len(bars) >= 3
    assert all(w["r"][3] >= 48 for w in bars)
    assert result["warnings"] == []


def test_the_fan_presets_stop_at_56_and_leave_a_foot() -> None:
    """Decision 12: Fan has no row that grows."""
    variant = COMPONENTS["apollo/fan-speed"]["variants"]["large"]
    presets = [row for row in variant["layout"] if row.get("type") == "choice"]
    assert presets and all(row.get("height") == 56 for row in presets)
    assert "align" not in variant or variant["align"] != "top"


@pytest.mark.parametrize(
    ("component_id", "variant", "param"),
    [("apollo/readings", "large", "entities"), ("apollo/people", "tall", "people")],
)
def test_a_short_list_keeps_rows_of_56(
    component_id: str, variant: str, param: str
) -> None:
    """Decisions 12 and 14: three rows of 56, the rest at the foot."""
    entities = (
        SENSORS[:3] if param == "entities" else [f"person.p{n}" for n in range(3)]
    )
    result = _compile(COMPONENTS[component_id], variant, {param: entities}, {}, {})
    heights = {w["r"][3] for w in result["widgets"] if w["t"] == "label"}
    assert heights == {56}
    assert result["h"] - 16 - _bottom(result) > 56


def test_the_media_title_takes_the_free_height() -> None:
    """Decision 12: Media Large grows its title, up to 56.

    Grown to 12x12 the title does not float in 400 px: the controls stay
    under it. L4 round 2: the header stays at the top; the spare height is
    shared above and under the rows under it.
    """
    for rows in (6, 12):
        result = _compile_at(
            "apollo/media", "large", 12, rows, {"entity": "media_player.a"},
            {"media_player.a": facts_of(MEDIA_RAW)},
        )  # fmt: skip
        above, _below = _body_room(result, 48)
        top = 16 + _top(result) + 48 + 8 + above
        title = next(
            w for w in result["widgets"] if w["t"] == "label" and w["r"][1] >= top
        )
        assert title["r"][3] == 56, rows
        assert title["r"][1] == top
        [progress] = [
            w for w in result["widgets"] if w["t"] == "slider" and w["r"][3] == 8
        ]
        assert progress["r"][1] - top < 184 - 56, rows
    assert _top(result) > 150 and _body_centred(result, 48)


@pytest.mark.parametrize(
    ("component_id", "params"),
    [
        ("apollo/switch", {"entity": "switch.a"}),
        ("apollo/button", {"entity": "button.a"}),
        ("apollo/page-link", {"page": "home"}),
    ],
)
def test_the_tile_foot_is_used(component_id: str, params: dict) -> None:
    """Decision 14: Switch, Button and Link Tile reach the foot of the tile."""
    result = _compile(COMPONENTS[component_id], "tile", params, {}, {})
    assert result["warnings"] == []
    assert result["h"] - 16 - _bottom(result) < 8


def test_the_lock_tall_has_the_tile_header() -> None:
    """Decision 14: Lock Tall gets one; the badge takes the room under it.

    Six columns wide, the header stacks: "Front Door Lock" across the card.
    """
    assert COMPONENTS["apollo/door-lock"]["variants"]["tall"]["header"] == "tile"
    result = _compile(
        COMPONENTS["apollo/door-lock"], "tall", {"entity": "lock.a"}, {}, {}
    )
    badge = max(
        (w for w in result["widgets"] if w["t"] == "image"), key=lambda w: w["r"][3]
    )
    assert badge["r"][1] == 16 + TILE_STACKED_H + 8
    name = next(w for w in result["widgets"] if w["t"] == "label")
    assert name["r"][2] == 152


@pytest.mark.parametrize(
    ("component_id", "variant"),
    [
        ("apollo/dial", "tile"),
        ("apollo/dial", "large"),
        ("apollo/graph", "wide"),
        ("apollo/graph", "large"),
        ("apollo/climate", "tile"),
        ("apollo/climate", "large"),
    ],
)
def test_single_device_cards_have_the_tile_header(
    component_id: str, variant: str
) -> None:
    """Decision 14: header `tile` on every single-device card."""
    assert COMPONENTS[component_id]["variants"][variant]["header"] == "tile"


def test_the_thermostat_tile_buttons_are_48() -> None:
    """Decision 14: the Thermostat Tile buttons are 48 px.

    L3 round 3: the tile has no dial any more (its number was 12 px); its
    minus and plus are 48 high under the number, nowhere near an arc.
    """
    result = _compile(
        COMPONENTS["apollo/climate"], "tile", {"entity": "climate.a"}, {}, {}
    )
    buttons = [w for w in result["widgets"] if w["t"] == "button"]
    assert [w["icon"] for w in buttons] == ["mdi:minus", "mdi:plus"]
    assert {w["r"][3] for w in buttons} == {48}


# ---------------------------------------------------------------- decision 14


def test_a_stored_size_whose_needs_fail_draws_wide() -> None:
    """A stored Large for a lamp that only turns on and off: the Wide layout."""
    component = COMPONENTS["apollo/light"]
    raw = {
        "params": {"entity": "light.a"},
        "variant": "large",
        "grid_options": {"columns": 12, "rows": 6},
    }
    card = validate_card_config2(component, raw)
    facts = {"light.a": facts_of({"domain": "light"})}
    compiler = _Compiler2(component, card, facts, 2, None, False)
    assert compiler._variant() == "wide"


@pytest.mark.parametrize(
    ("count", "widths"),
    [(5, [109, 109, 110, 168, 168]), (3, [168, 168, 168])],
)
def test_the_scenes_grid_has_no_lone_full_width_button(
    count: int, widths: list
) -> None:
    """Five share 3 and 2, not 4 and 1; a lone last button keeps its column's width."""
    scenes = [f"scene.s{n}" for n in range(count)]
    result = _compile(COMPONENTS["apollo/scenes"], "wide", {"scenes": scenes}, {}, {})
    assert result["warnings"] == []
    assert [w["r"][2] for w in result["widgets"]] == widths


def test_the_room_caption_is_a_name_and_a_value() -> None:
    """The name is cut when it is long; the value at the right never is."""
    result = _compile(COMPONENTS["apollo/room"], "room", {"extra": "sensor.p"}, {}, {})
    labels = [w for w in result["widgets"] if w["t"] == "label" and w["r"][1] > 64]
    caption = [w for w in labels if w["r"][3] < 40]
    assert len(caption) == 2
    name, value = sorted(caption, key=lambda w: w["r"][0])
    assert name["r"][1] == value["r"][1]
    assert value["r"][2] == 112 and value["r"][0] + 112 == result["w"] - 16


# ---------------------------------------------------------------- security


def _loop_doc(var: str) -> dict:
    """Return a schema 2 file whose looped button has a var named `var`."""
    return _doc(
        params={
            "entity": {"domain": "light"},
            "lights": {"domain": "light", "multiple": True, "max": 4},
        },
        variants={
            "wide": {
                "name": "Wide",
                "grid": [12, 3],
                "header": "none",
                "layout": [
                    {"type": "button", "text": "Go", "for_each": "lights", "as": "l",
                     "on_tap": "toggle", "vars": {var: "light.stranger"}}
                ],
            }
        },
    )  # fmt: skip


@pytest.mark.parametrize("var", ["l", "l_can"])
def test_a_var_may_not_hide_a_loop_name(var: str) -> None:
    """A var named like the loop's entity would hand a stranger to the output."""
    with pytest.raises(MakerError):
        validate_component(_loop_doc(var))
    validate_component(_loop_doc("other"))


def _readings_compiler() -> _Compiler2:
    """Return the compiler of a List card set up with two sensors."""
    component = COMPONENTS["apollo/readings"]
    raw = {
        "params": {"entities": SENSORS[:2]},
        "variant": "large",
        "grid_options": {"columns": 12, "rows": 6},
    }
    card = validate_card_config2(component, raw)
    return _Compiler2(component, card, {}, 2, None, False)


def test_a_loop_name_gives_only_a_device_of_the_card() -> None:
    """A fetched input never reads a device the card was not set up with."""
    compiler = _readings_compiler()
    assert compiler._entity_of("e", {"e": SENSORS[1]}) == SENSORS[1]
    assert compiler._entity_of("e", {"e": "sensor.stranger"}) is None


def test_a_card_makes_at_most_16_different_reads() -> None:
    """The 17th different read is left out and the card says it is cut."""
    compiler = _readings_compiler()
    for hours in range(MAX_FETCHES_2):
        slot = {"kind": "history", "entity": SENSORS[0], "hours": hours + 1}
        assert compiler._fetch_allowed(slot)
    again = {"kind": "history", "entity": SENSORS[0], "hours": 1}
    assert compiler._fetch_allowed(again)
    assert not compiler.cut
    extra = {"kind": "history", "entity": SENSORS[1], "hours": 1}
    assert not compiler._fetch_allowed(extra)
    assert compiler.cut


async def test_one_history_read_serves_every_reader(hass: HomeAssistant) -> None:
    """Cards, copies and tablets asking for the same history share one read."""
    reads = []

    async def _read(_hass: HomeAssistant, entity: str, hours: int) -> list:
        reads.append((entity, hours))
        return [1.0, 2.0]

    slot = {"kind": "history", "entity": "sensor.a", "hours": 6}
    with patch.object(live, "async_fetch_history", _read):
        first = await live.async_fetch_value(hass, slot)
        second = await live.async_fetch_value(hass, dict(slot))
        await live.async_fetch_value(hass, {**slot, "hours": 12})
    assert first == second == [1.0, 2.0]
    assert reads == [("sensor.a", 6), ("sensor.a", 12)]


async def test_only_a_read_action_runs_as_a_fetched_input(hass: HomeAssistant) -> None:
    """The list of read actions is checked again at the call."""
    calls = []

    async def _answer(call: ServiceCall) -> dict:
        calls.append(call)
        return {"ok": True}

    hass.services.async_register(
        "light", "turn_on", _answer, supports_response=SupportsResponse.OPTIONAL
    )
    slot = {
        "kind": "action",
        "action": "light.turn_on",
        "data": {"entity_id": "light.a"},
        "refresh": 60,
        "result": "{{ response.ok }}",
        "variables": {},
    }
    assert await live.async_fetch_action(hass, slot) == []
    assert calls == []
    # The same slot with a read action runs.
    hass.services.async_register(
        "weather", "get_forecasts", _answer, supports_response=SupportsResponse.ONLY
    )
    read = {**slot, "action": "weather.get_forecasts"}
    assert await live.async_fetch_action(hass, read) is True
    assert len(calls) == 1


def test_a_code_is_refused_when_a_file_loads() -> None:
    """Schema 1 and 2: an output may not carry a lock or alarm code."""
    one = _toggle_doc(
        outputs={
            "run": {
                "action": "light.toggle",
                "data": {"entity_id": "{{ entity }}", "code": "1234"},
                "feedback": "optimistic",
            }
        }
    )
    with pytest.raises(MakerError):
        validate_component(one)
    two = _doc()
    two["outputs"]["toggle"]["data"]["code"] = "1234"
    with pytest.raises(MakerError):
        validate_component(two)


async def test_a_code_is_refused_at_the_call(hass: HomeAssistant) -> None:
    """Checked again when the output runs, for schema 1 and schema 2."""
    calls = async_mock_service(hass, "light", "toggle")
    component = {
        "outputs": {
            "run": {
                "action": "light.toggle",
                "data": {"entity_id": "{{ entity }}", "code": "1234"},
                "feedback": "optimistic",
            }
        }
    }
    with pytest.raises(CallError) as err:
        await async_run_output(
            hass,
            component=component,
            action_ref={"output": "run"},
            params={"entity": "light.a"},
            entities=["light.a"],
            widget={"id": 1, "t": "button"},
            event="tap",
            value=None,
            confirmed=False,
            context=Context(),
        )
    assert err.value.code == "not_allowed"
    with pytest.raises(CallError) as err:
        live._render_data2(hass, {"entity_id": "light.a", "code": "1234"}, {}, set())
    assert err.value.code == "not_allowed"
    assert calls == []


# ---------------------------------------------------------------- round 2


CLIMATE_RAW = {
    "domain": "climate",
    "registry": {
        "capabilities": {
            "hvac_modes": ["heat", "cool", "auto", "off"],
            "min_temp": 7,
            "max_temp": 35,
            "target_temp_step": 0.5,
        },
        "features": ["TARGET_TEMPERATURE"],
    },
}


def test_a_grown_dial_is_round_and_leaves_a_foot() -> None:
    """Decision 12: a thermostat row grows to its width, no higher.

    At 12x12 the dial was 344 wide in a row of 586: empty height above the
    arc and between its feet and the buttons. Now the row is square and
    the modes and the line follow under it.
    """
    dial = {"type": "thermostat", "width": 152, "grow": True}
    laid = layout_card2(
        [{"kind": "row", "cells": [dial], "height": None}], 376, 760, "tile"
    )
    assert laid["rects"][0][0][0] == [16, 16 + 48 + 8, 344, 344]
    result = _compile_at(
        "apollo/climate", "large", 12, 12, {"entity": "climate.a"},
        {"climate.a": facts_of(CLIMATE_RAW)},
    )  # fmt: skip
    [thermostat] = [w for w in result["widgets"] if w["t"] == "thermostat"]
    # L4 round 2: the header at the top, the rest in the middle under it.
    above, _below = _body_room(result, 48)
    top = 16 + _top(result) + 48 + 8 + above
    assert thermostat["r"] == [16, top, 344, 344]
    [modes] = [w for w in result["widgets"] if w["t"] == "choice"]
    assert modes["r"][1] == top + 344 + 8
    assert _top(result) > 100 and _body_centred(result, 48)


def test_a_row_with_most_leaves_its_share_to_the_others() -> None:
    """Rows that stop at `most` hand what is left to the rows that grow on."""
    body = [_bar({"grow": True}), _bar({"grow": True, "most": 72})]
    laid = layout_card2(body, 376, 376, "tile")
    heights = [rect[0][0][3] for rect in laid["rects"]]
    assert heights == [376 - 32 - 56 - 8 - 72, 72]


def test_the_owners_lamp_large_gives_brightness_the_spare_height() -> None:
    """Decision 12: colour and white stop at 72; brightness is the tallest."""
    facts = {"light.h1401": facts_of(OWNERS_LAMP_RAW)}
    result = _compile(
        COMPONENTS["apollo/light"], "large", {"entity": "light.h1401"}, {}, facts
    )
    bars = [w for w in result["widgets"] if w["t"] == "slider"]
    dim, *rest = bars
    assert {w["r"][3] for w in rest} == {72}
    assert dim["r"][3] == 376 - 32 - 56 - 2 * 8 - 2 * 72
    assert result["h"] - 16 - _bottom(result) == 0


def test_an_on_off_lamp_kept_at_large_has_no_block_of_light() -> None:
    """The fallback's power button stops at 120; the rest is the foot."""
    result = _compile_at(
        "apollo/light", "large", 12, 6, {"entity": "light.a"},
        {"light.a": facts_of({"domain": "light"})},
    )  # fmt: skip
    [power] = [w for w in result["widgets"] if w["t"] == "button"]
    # L4 round 2: drawn larger than the Wide grid, the main row goes to 160.
    assert power["r"][3] == 160
    # The Wide card it is drawn as is lower than that: its button fills it.
    wide = _compile_at(
        "apollo/light", "wide", 12, 3, {"entity": "light.a"},
        {"light.a": facts_of({"domain": "light"})},
    )  # fmt: skip
    [power] = [w for w in wide["widgets"] if w["t"] == "button"]
    assert power["r"][1] + power["r"][3] == 184 - 16


def test_the_alarm_buttons_fill_the_wide_card() -> None:
    """No empty foot under 48 px buttons: they grow, up to 96."""
    result = _compile(
        COMPONENTS["apollo/alarm"], "wide", {"entity": "alarm_control_panel.a"}, {},
        {"alarm_control_panel.a": facts_of(
            {"domain": "alarm_control_panel",
             "registry": {"features": ["ARM_HOME", "ARM_AWAY"]}})},
    )  # fmt: skip
    buttons = [w for w in result["widgets"] if w["t"] == "button"]
    assert len(buttons) == 3
    assert {w["r"][3] for w in buttons} == {96}
    assert result["h"] - 16 - _bottom(result) == 0
    # A Wide kept four rows high: the buttons stop at 96; L4: the 64 px left
    # over are shared above and under the content.
    taller = _compile_at(
        "apollo/alarm", "wide", 12, 4, {"entity": "alarm_control_panel.a"},
        {"alarm_control_panel.a": facts_of(
            {"domain": "alarm_control_panel",
             "registry": {"features": ["ARM_HOME", "ARM_AWAY"]}})},
    )  # fmt: skip
    assert {w["r"][3] for w in taller["widgets"] if w["t"] == "button"} == {96}
    # L4 round 2: the header stays at the top.
    # L4 round 3: the header moves down with the rows.
    assert _body_room(taller, 48) == (0, 32) and _top(taller) == 32
    assert _body_centred(taller, 48)


# ---------------------------------------------------------------- tile header


def _stack(width: int, height: int, body: list, **kw: object) -> dict:
    """Lay out a card whose tile header may stack."""
    return layout_card2(body, width, height, "tile", stack_name=True, **kw)


def test_a_narrow_tile_header_stacks_its_name() -> None:
    """Six columns: badge and state in one line, the name across the tile."""
    parts = _stack(184, 184, [_bar({"grow": True})])["header"]
    assert parts["badge"] == [16, 16, 44, 44]
    assert parts["state"] == [16 + 44 + 8, 16 + 11, 100, 22]
    assert parts["name"] == [16, 16 + 44 + 2, 152, 26]
    # Twelve columns have room beside the badge: no stacking.
    wide = _stack(376, 184, [_bar({"grow": True})])["header"]
    assert wide["name"] == [16 + 44 + 8, 16, 376 - 32 - 52, 26]
    # Without stack_name (schema 1 callers, the geometry tests) nothing moves.
    flat = layout_card2([], 184, 184, "tile")["header"]
    assert flat["name"][0] == 16 + 44 + 8


def test_a_tile_header_stacks_only_when_the_rows_keep_their_places() -> None:
    """A row the stacked header would push out keeps the flat header."""
    body = [_bar({"height": 48}), _bar({"height": 48})]
    # 248 high: 48 + 8 + 48 + 8 + 48 fits, 72 + 8 + 48 + 8 + 48 does too.
    assert _stack(184, 248, body)["header"]["name"][0] == 16
    # 208 high: only the flat header leaves room for both bars.
    laid = _stack(184, 208, body)
    assert laid["header"]["name"][0] == 16 + 44 + 8
    assert laid["clipped"] == []


def test_a_tile_header_with_no_state_keeps_the_badge_when_it_can() -> None:
    """No state line and nothing trailing: the badge, then the name.

    A dial, a chart or a picture needs the height: there the name alone
    takes one line across the tile. So does a row the badge would push out.
    """
    laid = _stack(184, 184, [_bar({"grow": True})], state_line=False)
    assert laid["header"] == {
        "badge": [16, 16, 44, 44],
        "name": [16, 16 + 44 + 2, 152, 26],
    }
    assert laid["rects"][0][0][0] == [16, 16 + TILE_STACKED_H + 8, 152, 72]
    dial = [{"kind": "row", "cells": [{"type": "thermostat"}]}]
    laid = _stack(184, 184, dial, state_line=False)
    assert laid["header"] == {"name": [16, 16, 152, TILE_NAME_ONLY_H]}
    assert laid["rects"][0][0][0][1] == 16 + TILE_NAME_ONLY_H + 8
    # Two bars of 48 in a card 208 high fit under the name alone, not under
    # the badge.
    body = [_bar({"height": 48}), _bar({"height": 48})]
    laid = _stack(184, 208, body, state_line=False)
    assert laid["header"] == {"name": [16, 16, 152, TILE_NAME_ONLY_H]}
    assert laid["clipped"] == []
    # Something trailing keeps the badge line.
    more = _stack(184, 184, [], trailing="more", state_line=False)["header"]
    assert set(more) == {"badge", "name", "trailing"}


def test_a_one_line_tile_name_sits_beside_the_badge_middle() -> None:
    """Critic minor: with no state line the name is centred on the badge."""
    parts = layout_card2([], 376, 184, "tile", state_line=False)["header"]
    badge, name = parts["badge"], parts["name"]
    assert "state" not in parts
    assert name[1] + name[3] // 2 == badge[1] + badge[3] // 2


def test_the_owners_lamp_tile_name_reads_whole_words() -> None:
    """Critic major: "Li…Lamp 1" on a tile becomes "Living…Lamp 1"."""
    facts = {"light.h1401": facts_of(OWNERS_LAMP_RAW)}
    result = _compile(
        COMPONENTS["apollo/light"], "tile", {"entity": "light.h1401"}, {}, facts
    )
    name = next(w for w in result["widgets"] if w["t"] == "label")
    assert name["r"][2] == 152
    raw = {
        "params": {"entity": "light.h1401"},
        "variant": "tile",
        "title": "Living Room Lamp 1",
        "grid_options": {"columns": 6, "rows": 3},
    }
    card = validate_card_config2(COMPONENTS["apollo/light"], raw)
    titled = compile_card2(COMPONENTS["apollo/light"], card, facts, 2)
    assert next(w for w in titled["widgets"] if w["t"] == "label")["text"] == (
        "Living…Lamp 1"
    )


async def test_the_switch_tile_says_unavailable(hass: HomeAssistant) -> None:
    """Tester minor: the Switch Tile kept no state line, so a gone device was mute."""
    result = _compile(
        COMPONENTS["apollo/switch"], "tile", {"entity": "switch.a"}, {}, {}
    )
    assert result["warnings"] == []
    labels = [w for w in result["widgets"] if w["t"] == "label"]
    state = next(w for w in labels if w["r"][1] < 16 + 44 and w["r"][0] > 16)
    hass.states.async_set("switch.a", "unavailable")
    assert await _value(hass, result, state["text"]) == "unavailable"
    hass.states.async_set("switch.a", "on")
    assert await _value(hass, result, state["text"]) == "On"
    assert result["h"] - 16 - _bottom(result) < 8


def test_the_thermostat_tile_shows_the_target_large() -> None:
    """Critic major (L3 round 2): the target was 12 px tall in an 88 px dial.

    The tile is the header (badge, name, "Now 20.5°"), the target at the
    large text size across the tile, then minus and plus: no dial, so no
    button can touch an arc, and the tile ends at its foot.
    """
    result = _compile(
        COMPONENTS["apollo/climate"], "tile", {"entity": "climate.a"}, {},
        {"climate.a": facts_of(CLIMATE_RAW)},
    )  # fmt: skip
    assert result["warnings"] == []
    assert not [w for w in result["widgets"] if w["t"] == "thermostat"]
    # L4 round 2 (critic major): no badge; the name across the tile, then
    # "Now 20.5°" under it. L4 round 3 (critic major): the name on two
    # lines of 24 ("Living Room" over "Thermostat"); "Now 20.5" stands
    # small beside the target, which is at 28 px so both fit six columns.
    assert not [w for w in result["widgets"] if w["t"] == "image"]
    line1, line2 = (w for w in result["widgets"] if w["r"][1] < 16 + 48)
    assert (line1["r"], line2["r"]) == ([16, 16, 152, 24], [16, 40, 152, 24])
    [number] = [w for w in result["widgets"] if w.get("px") == 28]
    assert number["r"] == [16, 16 + 48 + 8, 152 - 8 - 70, 40]
    [now] = [w for w in result["widgets"] if w.get("size") == "s"]
    assert now["r"] == [16 + 74 + 8, 16 + 48 + 8, 70, 40]
    minus, plus = (w for w in result["widgets"] if w["t"] == "button")
    assert minus["r"] == [16, 16 + 48 + 8 + 40 + 8, 72, 48]
    assert plus["r"][0] == 16 + 72 + 8
    assert result["h"] - 16 - _bottom(result) == 0


async def test_the_thermostat_tile_says_mode_and_now(hass: HomeAssistant) -> None:
    """The state line says the temperature now; the large number is the target.

    L4: "Now 20.5°", not "Heat · 20.5°": two bare temperatures did not say
    which was the target. Off, or with no reading, it says the state. A
    gone thermostat says so, and its number is a dash. L4 round 3: the
    text stands beside the target, without "°" (six columns leave it 70
    px beside "21.5°"); with no target the state takes the row.
    """
    result = _compile(
        COMPONENTS["apollo/climate"], "tile", {"entity": "climate.a"}, {},
        {"climate.a": facts_of(CLIMATE_RAW)},
    )  # fmt: skip
    state = next(
        w for w in result["widgets"] if w["t"] == "label" and w.get("size") == "s"
    )
    [number] = [w for w in result["widgets"] if w.get("px") == 28]
    [alone] = [w for w in result["widgets"] if w.get("size") == "m" and "vis" in w]
    hass.states.async_set(
        "climate.a", "heat", {"temperature": 21.5, "current_temperature": 20.5}
    )
    assert await _value(hass, result, state["text"]) == "Now 20.5"
    assert await _value(hass, result, number["text"]) == "21.5°"
    assert await _value(hass, result, alone["vis"]) is False
    # Home Assistant reports whole degrees as 21.0: the tile says 21.
    hass.states.async_set(
        "climate.a", "heat", {"temperature": 21.0, "current_temperature": 20.0}
    )
    assert await _value(hass, result, state["text"]) == "Now 20"
    assert await _value(hass, result, number["text"]) == "21°"
    # Without translations loaded the test's Home Assistant says "heat".
    hass.states.async_set("climate.a", "heat", {"temperature": 21.0})
    assert await _value(hass, result, state["text"]) == "heat"
    hass.states.async_set(
        "climate.a", "off", {"temperature": 21.0, "current_temperature": 20.0}
    )
    assert await _value(hass, result, state["text"]) == "off"
    hass.states.async_set("climate.a", "unavailable")
    assert await _value(hass, result, number["text"]) == "—"
    assert await _value(hass, result, alone["vis"]) is True
    assert await _value(hass, result, alone["text"]) == "unavailable"


async def test_the_thermostat_tile_steps_the_target(hass: HomeAssistant) -> None:
    """Minus and plus set the target one step away, kept within min and max."""
    entity = "climate.living"
    actions = _bindings(
        "apollo/climate", {"entity": entity}, {entity: facts_of(CLIMATE_RAW)},
        variant="tile", grid_options={"columns": 6, "rows": 3},
    )  # fmt: skip
    temperature = async_mock_service(hass, "climate", "set_temperature")
    hass.states.async_set(entity, "heat", {"temperature": 21})
    await _run(hass, actions["down"])
    assert temperature[-1].data == {"entity_id": entity, "temperature": 20.5}
    await _run(hass, actions["up"])
    assert temperature[-1].data == {"entity_id": entity, "temperature": 21.5}
    hass.states.async_set(entity, "heat", {"temperature": 35})
    await _run(hass, actions["up"])
    assert temperature[-1].data == {"entity_id": entity, "temperature": 35}
    hass.states.async_set(entity, "heat", {"temperature": 7})
    await _run(hass, actions["down"])
    assert temperature[-1].data == {"entity_id": entity, "temperature": 7}
    # No target (heat and cool with a range): the buttons do nothing.
    hass.states.async_set(entity, "heat_cool", {"target_temp_low": 19})
    calls = len(temperature)
    with pytest.raises(CallError):
        await _run(hass, actions["up"])
    assert len(temperature) == calls


async def test_an_idle_thermostat_is_not_drawn_as_cooling(hass: HomeAssistant) -> None:
    """Critic minor: heat mode and idle drew the arc blue, as cooling."""
    result = _compile(
        COMPONENTS["apollo/climate"], "large", {"entity": "climate.a"}, {},
        {"climate.a": facts_of(CLIMATE_RAW)},
    )  # fmt: skip
    [dial] = [w for w in result["widgets"] if w["t"] == "thermostat"]
    assert "muted" in dial["c"]["roles"]
    for action, tone in (
        ("heating", "warn"),
        ("cooling", "info"),
        ("idle", "muted"),
        (None, "muted"),
    ):
        hass.states.async_set("climate.a", "heat", {"hvac_action": action})
        assert await _value(hass, result, dial["c"]) == tone, action


# ---------------------------------------------------------------- untested paths


def test_a_row_marked_grow_takes_the_spare_height() -> None:
    """`grow` on a row, not on its widgets, makes the row grow."""
    label = {"type": "label", "size": "m"}
    body = [
        {"kind": "row", "cells": [dict(label)], "height": None, "grow": True},
        {"kind": "row", "cells": [dict(label)], "height": None},
    ]
    laid = layout_card2(body, 376, 376, "title")
    first, second = (rect[0][0][3] for rect in laid["rects"])
    assert second == 28
    # Two label rows are 2 apart.
    assert first == 376 - 32 - 32 - 8 - 2 - 28


def test_a_loop_name_wins_over_an_items_var() -> None:
    """The compiler's own order: a var never hands a stranger to a loop copy."""
    compiler = _readings_compiler()
    item = {"type": "button", "vars": {"e": "sensor.stranger", "word": "Go"}}
    [(_item, names)] = compiler._widget_copies(item, {"e": SENSORS[0]})
    assert names["e"] == SENSORS[0]
    assert names["word"] == "Go"


def test_a_var_named_like_a_later_loops_can_is_refused() -> None:
    """A var `l_can` on an earlier item, then a loop `as: l`."""
    doc = _loop_doc("other")
    layout = doc["variants"]["wide"]["layout"]
    layout.insert(
        0,
        {"type": "button", "text": "A", "on_tap": "toggle",
         "vars": {"l_can": "light.stranger"}},
    )  # fmt: skip
    with pytest.raises(MakerError):
        validate_component(doc)


def test_a_template_input_past_the_reads_sees_no_value() -> None:
    """The 16-read limit holds for inputs a template is fed, too."""
    component = COMPONENTS["apollo/graph"]

    def _compiler() -> _Compiler2:
        raw = {
            "params": {"entity": "sensor.a"},
            "variant": "large",
            "grid_options": {"columns": 12, "rows": 6},
        }
        card = validate_card_config2(component, raw)
        return _Compiler2(component, card, {}, 2, None, False)

    fresh = _compiler()
    slot = fresh._template_slot("{{ lo6 }}", {})
    assert "lo6" in slot["inputs"]
    full = _compiler()
    full._fetches = {("action", n, "{}") for n in range(MAX_FETCHES_2)}
    slot = full._template_slot("{{ lo6 }}", {})
    assert "inputs" not in slot
    assert slot["variables"]["lo6"] is None
    assert full.cut


# ---------------------------------------------------------------- L3 round 3


def test_a_grown_badge_row_is_no_taller_than_the_badge() -> None:
    """Tester major: a badge is the circle of min(w, h) of its rect.

    A badge row grown higher than wide only put empty height above and
    under the circle; capped at its width, the rows under it follow on.
    """
    badge = {"type": "image", "look": "badge"}
    button = {"type": "button", "control": True}
    body = [
        {"kind": "row", "cells": [badge], "height": None},
        {"kind": "row", "cells": [button], "height": 64},
    ]
    laid = layout_card2(body, 376, 760, "tile")
    assert laid["rects"][0][0][0] == [16, 72, 344, 344]
    assert laid["rects"][1][0][0][1] == 72 + 344 + 8
    # A box image is not round: it still takes the free height.
    body[0]["cells"] = [{"type": "image", "look": "box"}]
    assert layout_card2(body, 376, 760, "tile")["rects"][0][0][0][3] > 344


def test_the_alarm_large_grown_keeps_its_buttons_under_the_shield() -> None:
    """Decision 12 on Alarm Large at 12x12: shield, buttons, then the foot."""
    entity = "alarm_control_panel.a"
    facts = {entity: facts_of(
        {"domain": "alarm_control_panel",
         "registry": {"features": ["ARM_HOME", "ARM_AWAY"]}})}  # fmt: skip
    result = _compile_at("apollo/alarm", "large", 12, 12, {"entity": entity}, facts)
    shield = max(
        (w for w in result["widgets"] if w["t"] == "image"), key=lambda w: w["r"][3]
    )
    # L4 round 2: the header stays at the top; shield and buttons sit in the
    # middle of the room under it.
    above, _below = _body_room(result, 48)
    top = 16 + _top(result) + 48 + 8 + above
    assert shield["r"] == [16, top, 344, 344]
    buttons = [w for w in result["widgets"] if w["t"] == "button"]
    assert buttons and {w["r"][1] for w in buttons} == {top + 344 + 8}
    assert _top(result) > 100 and _body_centred(result, 48)


def test_the_lock_tall_grown_keeps_its_button_under_the_badge() -> None:
    """Decision 12 on Lock Tall at 6x12: no band of 180 px over Unlock."""
    result = _compile_at("apollo/door-lock", "tall", 6, 12, {"entity": "lock.a"}, {})
    badge = max(
        (w for w in result["widgets"] if w["t"] == "image"), key=lambda w: w["r"][3]
    )
    # L4 round 2: the header stays at the top; badge and button sit in the
    # middle of the room under it.
    above, _below = _body_room(result, TILE_STACKED_H)
    top = 16 + _top(result) + TILE_STACKED_H + 8 + above
    assert badge["r"] == [16, top, 152, 152]
    buttons = [w for w in result["widgets"] if w["t"] == "button"]
    assert {w["r"][1] for w in buttons} == {top + 152 + 8}
    assert _top(result) > 150 and _body_centred(result, TILE_STACKED_H)


def test_the_switch_tile_power_button_stops_at_120() -> None:
    """Tester minor: at 6x6 the power button was a block of 264 px."""
    result = _compile_at("apollo/switch", "tile", 6, 6, {"entity": "switch.a"}, {})
    [power] = [w for w in result["widgets"] if w["t"] == "button"]
    assert power["r"][3] == 120
    # At its own size it still reaches the foot of the tile.
    tile = _compile_at("apollo/switch", "tile", 6, 3, {"entity": "switch.a"}, {})
    assert tile["h"] - 16 - _bottom(tile) == 0


# L4: grown to 6 rows the 192 px left over are shared above and under the
# buttons; L4 round 2: the header stays at the top.
@pytest.mark.parametrize(("rows", "foot"), [(3, 0), (6, (376 - 16 - 72 - 96) // 2)])
def test_the_media_wide_buttons_fill_the_card(rows: int, foot: int) -> None:
    """Critic minor: buttons of 48 left a foot of 64; they grow, up to 96."""
    result = _compile_at(
        "apollo/media", "wide", 12, rows, {"entity": "media_player.a"},
        {"media_player.a": facts_of(MEDIA_RAW)},
    )  # fmt: skip
    buttons = [w for w in result["widgets"] if w["t"] == "button"]
    assert len(buttons) == 3
    assert {w["r"][3] for w in buttons} == {96}
    # L4 round 3: the header moves down with the rows.
    assert _body_room(result, 48) == (0, foot) and _top(result) == foot


async def test_the_media_title_of_a_gone_player_is_a_dash(
    hass: HomeAssistant,
) -> None:
    """Critic minor: "unavailable" in the header and again as the title."""
    result = _compile(
        COMPONENTS["apollo/media"], "large", {"entity": "media_player.a"}, {},
        {"media_player.a": facts_of(MEDIA_RAW)},
    )  # fmt: skip
    [title] = [w for w in result["widgets"] if w.get("px") == 28]
    hass.states.async_set("media_player.a", "unavailable")
    assert await _value(hass, result, title["text"]) == "—"
    hass.states.async_set("media_player.a", "idle")
    assert await _value(hass, result, title["text"]) == "idle"
    hass.states.async_set("media_player.a", "playing", {"media_title": "Harvest Moon"})
    assert await _value(hass, result, title["text"]) == "Harvest Moon"


@pytest.mark.parametrize(("columns", "rows"), [(12, 12), (24, 12)])
def test_the_owners_lamp_grown_keeps_brightness_at_192(columns: int, rows: int) -> None:
    """Critic minor: grown to 12x12 the brightness bar was a block of 448.

    L4 round 2 (critic major on item g): grown past its grid, brightness
    goes to 280, not 192 in empty bands; colour and white stay at 72.
    L4 round 3 (critic major): brightness 320, colour and white 144, so
    the owner's lamp fills the card: the foot is under 56 and the header
    stays at the top.
    """
    facts = {"light.h1401": facts_of(OWNERS_LAMP_RAW)}
    result = _compile_at(
        "apollo/light", "large", columns, rows, {"entity": "light.h1401"}, facts
    )
    dim, *rest = (w for w in result["widgets"] if w["t"] == "slider")
    assert dim["r"][3] == 320
    assert {w["r"][3] for w in rest} == {144}
    assert result["h"] - 16 - _bottom(result) <= 56
    assert _top(result) == 0


async def test_the_dim_only_lamp_large_has_a_two_line_header(
    hass: HomeAssistant,
) -> None:
    """Critic minor: its header line was empty, so the name sat at the top."""
    result = _compile(
        COMPONENTS["apollo/light"], "large", {"entity": "light.a"}, {},
        {"light.a": facts_of(DIM_LAMP_RAW)},
    )  # fmt: skip
    labels = [w for w in result["widgets"] if w["t"] == "label"]
    state = next(w for w in labels if w.get("size") == "s")
    for value, attrs in (("on", {"brightness": 102}), ("off", {})):
        hass.states.async_set("light.a", value, attrs)
        assert await _value(hass, result, state["text"]) == value


# ---------------------------------------------------------------- round 4


def _header_rects(result: dict) -> tuple[list, list]:
    """Return the badge's and the name's rectangle of a compiled tile."""
    badge = next(w for w in result["widgets"] if w["t"] == "image")
    name = next(w for w in result["widgets"] if w["t"] == "label" and w["r"][2] == 152)
    return badge["r"], name["r"]


def test_the_lock_tile_has_the_tile_header() -> None:
    """Decision 14: "Locked" sat at the right edge, far from its badge.

    As on the Fan Tile: the state beside the badge, the name under them,
    then the button.
    """
    result = _compile(
        COMPONENTS["apollo/door-lock"], "tile", {"entity": "lock.front"}, {}, {}
    )
    assert result["warnings"] == []
    badge, name = _header_rects(result)
    assert badge == [16, 16, 44, 44]
    assert name == [16, 62, 152, 26]
    state = next(w for w in result["widgets"] if w["t"] == "label" and w["r"][2] != 152)
    assert state["r"] == [68, 27, 100, 22]
    assert "al" not in state
    buttons = [w for w in result["widgets"] if w["t"] == "button"]
    assert {tuple(w["r"]) for w in buttons} == {(16, 96, 152, 48)}
    fan = _compile(
        COMPONENTS["apollo/fan-speed"], "tile", {"entity": "fan.a"}, {},
        {"fan.a": facts_of(FAN_RAW)},
    )  # fmt: skip
    assert _header_rects(fan) == (badge, name)


def test_the_link_tile_shows_its_name_on_two_lines() -> None:
    """Decision 14 gave the Link Tile a badge; L4 round 2 takes it away.

    Under an empty badge line the name was cut to "Outside…rature" (critic
    major). Now the name has two lines across the tile, and the reading the
    room under it. The Gauge Tile's dial needs the height: it keeps the
    name alone, on one line.
    """
    link = _compile(
        COMPONENTS["apollo/page-link"], "tile",
        {"page": "other", "entity": "sensor.out"}, {}, {},
    )  # fmt: skip
    assert link["warnings"] == []
    assert not [w for w in link["widgets"] if w["t"] == "image" and w["r"][1] < 60]
    names = [w for w in link["widgets"] if w.get("size") == "m"]
    # L4 round 3: two lines of 24 (TILE_NAME_LINE2_H), as the Thermostat
    # Tile's; the reading gains the 4 px.
    assert [w["r"] for w in names] == [[16, 16, 152, 24], [16, 40, 152, 24]]
    reading = next(w for w in link["widgets"] if w.get("size") == "l")
    assert reading["r"][1] == 16 + 48 + 8
    assert reading["r"][3] == 92
    # The small card has no room for the badge line: nothing is pushed out.
    small = _compile(
        COMPONENTS["apollo/page-link"], "small",
        {"page": "other", "entity": "sensor.out"}, {}, {},
    )  # fmt: skip
    assert small["warnings"] == []
    gauge = _compile(
        COMPONENTS["apollo/dial"], "tile", {"entity": "sensor.p", "max": 5000}, {}, {}
    )
    assert not [w for w in gauge["widgets"] if w["t"] == "image"]
    [dial] = [w for w in gauge["widgets"] if w["t"] == "thermostat"]
    assert dial["r"][1] == 16 + TILE_NAME_ONLY_H + 8


@pytest.mark.parametrize(
    ("rows", "bar_h", "foot"), [(6, 128, 0), (12, 320, (728 - 56 - 152 - 8 - 320) // 2)]
)
def test_the_dim_only_lamp_number_stops_at_152(
    rows: int, bar_h: int, foot: int
) -> None:
    """Critic minor: grown to 12x12 the number sat under 130 px of nothing.

    The number keeps the height it has at the default size; the bar follows
    it. L4: the height left over is shared above and under the content;
    L4 round 2: grown, the number goes to 240, and the header stays at the
    top. L4 round 4 (critic major): that left two bands of 95 px around the
    number. The number stops at 152 at every size, so no band is over 56;
    the bar takes the rest, up to 128, and up to 320 in a grown card.
    """
    result = _compile_at(
        "apollo/light", "large", 12, rows, {"entity": "light.a"},
        {"light.a": facts_of(DIM_LAMP_RAW)},
    )  # fmt: skip
    number = next(w for w in result["widgets"] if w["t"] == "label" and w["r"][3] > 100)
    [bar] = [w for w in result["widgets"] if w["t"] == "slider"]
    assert number["r"][3] == 152
    assert bar["r"][1] == number["r"][1] + 152 + 8
    assert bar["r"][3] == bar_h
    # L4 round 3: the header moves down with the rows.
    assert _body_room(result, 48) == (0, foot) and _top(result) == foot


def test_the_thermostat_tile_number_has_no_point_zero() -> None:
    """Tester minor: Home Assistant reports 21.0, and the tile said "21.0°"."""
    template = COMPONENTS["apollo/climate"]["inputs"]["target_text"]["template"]
    render = jinja2.Environment().from_string(template).render
    shown = [render(target=value) for value in (21, 21.0, 20.5, 7.2, None)]
    assert shown == ["21°", "21°", "20.5°", "7.2°", "—"]
