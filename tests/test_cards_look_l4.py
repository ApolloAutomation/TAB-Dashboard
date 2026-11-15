"""The look of the cards after round L4 of LOOK-NOTES.

Each test holds one change of L4: tile headers, `most` caps, blinds buttons
of 48, middle name cuts, the thermostat's "Now", the camera fade, the rule
for large empty feet, and the coordinator's decisions (missing devices fade,
"Off" once, numbers step on their grid, Scenes rows of 56).
"""

from __future__ import annotations

import itertools

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.apollo_tab.maker.compile2 import (
    NAME_W,
    compile_card2,
    cut_middle,
    cut_to_fit,
    cut_to_fit_template,
    name_chars,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.geometry import (
    BUTTON_H_2,
    FOOT_CENTRE_MIN,
    ROW_ITEM_GAP,
    TIGHT_GAP,
    layout_card2,
)
from custom_components.apollo_tab.maker.names import room_beside
from tests.test_cards_look_l3 import (
    _body_centred,
    _body_room,
    _centred,
    _compile_at,
    _top,
)
from tests.test_cards_step_a import (
    COMPONENTS,
    DIM_LAMP_RAW,
    EVERYTHING_RAW,
    _value,
)
from tests.test_cards_step_b import BLIND_RAW, MEDIA_RAW, _bindings, _compile, _run
from tests.test_maker_convert2 import _cards, _convert, _dashboard

# ---------------------------------------------------------------- names


@pytest.mark.parametrize(
    ("name", "chars", "shown"),
    [
        # Narrow (under 12): the end may take all but three characters.
        ("Living Room Lamp 1", 9, "Li…Lamp 1"),
        ("Living Room Lamp 1", 11, "Livi…Lamp 1"),
        ("Kitchen Ceiling Light", 9, "Kit…Light"),
        # One word, or an end too long: cut by characters, never at the end.
        ("Superlongname", 9, "Supe…name"),
        ("Superlongnamewithoutspaces", 3, "S…s"),
        ("Lamp", 3, "L…p"),
        # Under 3 characters there is nothing to cut.
        ("Living Room Lamp 1", 2, "Living Room Lamp 1"),
    ],
)
def test_a_name_is_cut_in_the_middle_at_any_width(
    name: str, chars: int, shown: str
) -> None:
    """L4 d: the narrow cut keeps the end; a name never ends in "…"."""
    assert cut_middle(name, chars) == shown
    if shown != name:
        assert len(shown) <= chars
        assert not shown.endswith("…") and not shown.startswith("…")


def test_no_name_is_left_whole_when_it_is_too_long() -> None:
    """L4 d: from 3 characters up a long name is always cut, in its middle."""
    names = [
        "Living Room Lamp 1",
        "Superlongnamewithoutspaces",
        "A very long name of many words",
        "Hallway ceiling",
        "Ab Cdefghijklmnopqrstuvwxyz",
    ]
    for name in names:
        for chars in range(3, len(name)):
            shown = cut_middle(name, chars)
            assert shown != name and len(shown) <= chars, (name, chars, shown)
            assert "…" in shown[1:-1], (name, chars, shown)


async def test_the_name_template_cuts_as_cut_to_fit(hass: HomeAssistant) -> None:
    """L4 d: the live name gives cut_to_fit's text, narrow widths too."""
    names = [
        "Living Room Lamp 1",
        "Living Room Lamp 12",
        "Kitchen Ceiling Light",
        "Superlongnamewithoutspaces",
        "Living Room Chandelier",
        "Sofa lamp · Colour",
        "WWWWWWWWWWWW",
        "Hallway",
        "A B",
    ]
    for width in (40, 64, 88, 100, 116, 152, 216):
        chars = name_chars(width)
        template = Template(
            "{%- set n = name -%}" + cut_to_fit_template(chars, width), hass
        )
        for name in names:
            got = template.async_render(
                {"name": name, "name_w": dict(NAME_W)}, parse_result=False
            )
            assert got == cut_to_fit(name, chars, width), (width, name)


async def test_a_name_in_a_card_body_is_cut_in_the_middle(hass: HomeAssistant) -> None:
    """L4 d: List rows showed long names cut at their end by the tablet."""
    result = _compile(
        COMPONENTS["apollo/readings"], "large",
        {"entities": ["sensor.a", "sensor.b"]}, {}, {},
    )  # fmt: skip
    names = [
        w
        for w in result["widgets"]
        if w["t"] == "label" and w.get("size") == "m" and w.get("al", 0) == 0
    ]
    assert len(names) == 2
    width = names[0]["r"][2]
    long = "Living Room Temperature Sensor 2"
    hass.states.async_set("sensor.a", "21", {"friendly_name": long})
    shown = await _value(hass, result, names[0]["text"])
    # Round 3 (critic major, decision 14): the name's label spans the line
    # and the name gets what the value shown ("21") leaves of it.
    [value] = [
        w
        for w in result["widgets"]
        if w.get("al") == 2 and w["r"][1] == names[0]["r"][1]
    ]
    room = room_beside("21", 18, width, ROW_ITEM_GAP, value["r"][2])
    assert shown == cut_to_fit(long, name_chars(width), width, room=room)
    assert shown.endswith("Sensor 2") and "…" in shown
    hass.states.async_set("sensor.a", "21", {"friendly_name": "Hall"})
    assert await _value(hass, result, names[0]["text"]) == "Hall"


async def test_the_link_small_name_is_cut_in_the_middle(hass: HomeAssistant) -> None:
    """L4 d: the name is cut in the middle; round 2: on two lines first.

    "Outside Temperature" was "Outside…rature"; now it reads "Outside" over
    "Temperature", and only a longer rest is cut in its middle.
    """
    result = _compile(
        COMPONENTS["apollo/page-link"], "small",
        {"page": "other", "entity": "sensor.out"}, {}, {},
    )  # fmt: skip
    line1, line2 = (
        w for w in result["widgets"] if w.get("size") == "m" and w["r"][1] < 68
    )
    # Round 3: two lines of 24 (TILE_NAME_LINE2_H).
    assert (line1["r"], line2["r"]) == ([16, 16, 152, 24], [16, 40, 152, 24])
    hass.states.async_set("sensor.out", "9", {"friendly_name": "Outside Temperature"})
    assert await _value(hass, result, line1["text"]) == "Outside"
    assert await _value(hass, result, line2["text"]) == "Temperature"
    long = "Upstairs Guest Bedroom Reading Lamp"
    hass.states.async_set("sensor.out", "9", {"friendly_name": long})
    assert await _value(hass, result, line1["text"]) == "Upstairs Guest"
    rest = await _value(hass, result, line2["text"])
    assert rest == cut_to_fit("Bedroom Reading Lamp", 14, 152)
    assert rest.endswith("Lamp") and "…" in rest[1:-1]


# ---------------------------------------------------------------- tile headers


@pytest.mark.parametrize(
    ("component_id", "variant"),
    [
        ("apollo/reading", "tile"),
        ("apollo/appliance", "tile"),
        ("apollo/button", "small"),
        ("apollo/button", "tile"),
        ("apollo/switch", "small"),
        ("apollo/select", "large"),
    ],
)
def test_more_cards_have_the_tile_header(component_id: str, variant: str) -> None:
    """L4 a: the tile header where it fits."""
    assert COMPONENTS[component_id]["variants"][variant]["header"] == "tile"


def test_the_dropdown_wide_keeps_its_title() -> None:
    """L4 a, an exception: 8 choices need 104 px; under a tile header 96 are left."""
    assert COMPONENTS["apollo/select"]["variants"]["wide"]["header"] == "title"


async def test_the_status_tile_looks_like_the_link_tile(hass: HomeAssistant) -> None:
    """L4 a, round 2 (critic major): the name on two lines, then the value.

    Under an empty badge line the name was "Living…rature". Now it reads
    "Living Room" over "Temperature"; without a value a dash, and the line
    under it says why.
    """
    result = _compile(
        COMPONENTS["apollo/reading"], "tile", {"entity": "sensor.t"}, {}, {}
    )
    assert result["warnings"] == []
    assert not [w for w in result["widgets"] if w["t"] == "image"]
    line1, line2 = (w for w in result["widgets"] if w.get("size") == "m")
    # Round 3: two lines of 24 (TILE_NAME_LINE2_H), as the Thermostat Tile's.
    assert (line1["r"], line2["r"]) == ([16, 16, 152, 24], [16, 40, 152, 24])
    big, small, why = (w for w in result["widgets"] if w["r"][1] > 64)
    assert big["r"][1] == small["r"][1] == 16 + 48 + 8
    assert why["r"] == [16, 16 + 48 + 8 + 60 + 8, 152, 22]
    hass.states.async_set(
        "sensor.t",
        "21.44",
        {"friendly_name": "Living Room Temperature", "unit_of_measurement": "°C"},
    )
    assert await _value(hass, result, line1["text"]) == "Living Room"
    assert await _value(hass, result, line2["text"]) == "Temperature"
    assert await _value(hass, result, big["text"]) == "21.4 °C"
    assert await _value(hass, result, why["text"]) == ""
    hass.states.async_set("sensor.t", "unavailable", {})
    assert await _value(hass, result, small["text"]) == "—"
    assert await _value(hass, result, why["text"]) == "unavailable"


@pytest.mark.parametrize(
    ("component_id", "entity"),
    [("apollo/button", "script.a"), ("apollo/switch", "switch.a")],
)
def test_the_small_cards_show_badge_and_name(component_id: str, entity: str) -> None:
    """L4 a: Button Small and Switch Small have the badge over the name."""
    result = _compile(COMPONENTS[component_id], "small", {"entity": entity}, {}, {})
    assert result["warnings"] == []
    badge = next(w for w in result["widgets"] if w["t"] == "image")
    assert badge["r"] == [16, 16, 44, 44]
    name = next(w for w in result["widgets"] if w.get("size") == "m")
    assert name["r"] == [16, 62, 152, 26]


# ---------------------------------------------------------------- most


def test_the_link_tile_reading_stops_at_92() -> None:
    """L4 b: grown to 6x6 the reading was a block of the whole free height.

    Round 2: 92, what the tile leaves under a name of two lines (was 72
    under the badge and a name of one line).
    """
    result = _compile_at(
        "apollo/page-link", "tile", 6, 6, {"page": "other", "entity": "sensor.out"}, {}
    )
    reading = next(w for w in result["widgets"] if w.get("size") == "l")
    assert reading["r"][3] == 92


def test_the_button_tile_button_stops_at_120() -> None:
    """L4 b: grown to 6x6 the big button stops at 120, in the card's middle."""
    result = _compile_at("apollo/button", "tile", 6, 6, {"entity": "script.a"}, {})
    [button] = [w for w in result["widgets"] if w["t"] == "button"]
    assert button["r"][3] == 120
    # Round 2: the header stays at the top; the button is in the middle
    # of the room under it. Round 3 (critic major): the button follows the
    # header and the two sit in the card's middle together.
    assert _body_centred(result, 72)


def test_the_scenes_large_rows_stop_at_56() -> None:
    """Decision: Scenes Large rows are 56 px at most, not a block per scene."""
    result = _compile(
        COMPONENTS["apollo/scenes"], "large", {"scenes": ["scene.a", "scene.b"]}, {}, {}
    )
    buttons = [w for w in result["widgets"] if w["t"] == "button"]
    assert buttons and {w["r"][3] for w in buttons} == {56}


# ---------------------------------------------------------------- blinds


@pytest.mark.parametrize("variant", ["window", "tall"])
def test_the_blinds_buttons_are_48_wide(variant: str) -> None:
    """L4 c: up, stop and down were 45 px wide, 8 apart; now 48, 4 apart."""
    result = _compile(
        COMPONENTS["apollo/cover"], variant, {"entity": "cover.a"}, {},
        {"cover.a": facts_of(BLIND_RAW)},
    )  # fmt: skip
    assert result["warnings"] == []
    buttons = sorted(
        (w for w in result["widgets"] if w["t"] == "button"), key=lambda w: w["r"][0]
    )
    assert len(buttons) == 3
    assert min(w["r"][2] for w in buttons) >= BUTTON_H_2
    gaps = [b["r"][0] - a["r"][0] - a["r"][2] for a, b in itertools.pairwise(buttons)]
    assert gaps == [TIGHT_GAP, TIGHT_GAP]
    assert buttons[-1]["r"][0] + buttons[-1]["r"][2] == 184 - 16


def test_only_a_tight_row_of_buttons_closes_up() -> None:
    """L4 c: two buttons, or buttons beside a slider, keep the gap of 8."""

    def row(*types: str) -> list:
        cells = [{"type": t, "control": True} for t in types]
        return [{"kind": "row", "cells": cells, "height": 48}]

    def lefts(laid: dict) -> list[int]:
        return [rect[0] for rect in laid["rects"][0][0]]

    assert lefts(layout_card2(row("button", "button", "button"), 184, 184)) == [
        16, 16 + 48 + TIGHT_GAP, 16 + 2 * (48 + TIGHT_GAP),
    ]  # fmt: skip
    two = lefts(layout_card2(row("button", "button"), 184, 184))
    assert two[1] - two[0] == (152 - ROW_ITEM_GAP) // 2 + ROW_ITEM_GAP
    wide = lefts(layout_card2(row("button", "button", "button"), 376, 184))
    assert wide[1] - wide[0] == (344 - 2 * ROW_ITEM_GAP) // 3 + ROW_ITEM_GAP


# ---------------------------------------------------------------- thermostat


async def test_the_thermostat_tile_says_which_is_now(hass: HomeAssistant) -> None:
    """L4 e: the small line says "Now 20.5°"; the large number is the target."""
    # Round 3 (critic major on the name): the text stands small beside the
    # target, without "°" (six columns leave it 70 px beside "21.5°").
    template = COMPONENTS["apollo/climate"]["inputs"]["now_text"]["template"]
    assert "'Now '" in template
    result = _compile(
        COMPONENTS["apollo/climate"], "tile", {"entity": "climate.a"}, {}, {}
    )
    state = next(
        w for w in result["widgets"] if w["t"] == "label" and w.get("size") == "s"
    )
    hass.states.async_set(
        "climate.a", "cool", {"temperature": 22, "current_temperature": 24.5}
    )
    assert await _value(hass, result, state["text"]) == "Now 24.5"


# ---------------------------------------------------------------- camera


def _camera_card(dl: int) -> dict:
    result = _convert(
        _dashboard(
            {
                "type": "custom:apollo-tab-card",
                "component": "apollo/camera-snapshot",
                "params": {"entity": "camera.door"},
            }
        ),
        dl,
    )
    [card] = _cards(result["layout"])
    return {"card": card, "slots": result["bindings"]["slots"]}


async def test_a_gone_camera_fades_in_a_layout_v2(hass: HomeAssistant) -> None:
    """L4 f: the snapshot's placeholder looked live while the camera was gone."""
    from custom_components.apollo_tab.live import async_evaluate_slot

    built = _camera_card(2)
    ref = built["card"]["un"]
    [slot] = [s for s in built["slots"] if s["n"] == ref["s"]]
    hass.states.async_set("camera.door", "unavailable")
    assert await async_evaluate_slot(hass, slot) in (True, "True")
    hass.states.async_set("camera.door", "idle")
    assert await async_evaluate_slot(hass, slot) in (False, "False")
    # The layout v1 never sees it.
    assert "un" not in _camera_card(1)["card"]


# ---------------------------------------------------------------- empty feet


def test_a_grown_card_holds_its_content_in_the_middle() -> None:
    """L4 g: a foot over 56 px is shared above and under the rows.

    Round 2 (critic major): the header stays at the top, in line with the
    headers of the cards beside it; only the rows move. Round 3 (critic
    major): that left a band under the header; the header moves with the
    rows, so the card reads as one block.
    """
    body = [{"kind": "row", "cells": [{"type": "button", "control": True}],
             "height": 48}]  # fmt: skip
    top = layout_card2(body, 376, 376, "tile")
    middle = layout_card2(body, 376, 376, "tile", centre=True)
    foot = 376 - 16 - (top["rects"][0][0][0][1] + 48)
    assert foot > FOOT_CENTRE_MIN
    assert middle["rects"][0][0][0][1] == top["rects"][0][0][0][1] + foot // 2
    assert middle["header"] == {
        part: [x, y + foot // 2, w, h] for part, (x, y, w, h) in top["header"].items()
    }
    # A foot of 56 or less stays a foot.
    short = layout_card2(body, 376, 184, "tile", centre=True)
    assert (
        short["rects"][0][0][0]
        == layout_card2(body, 376, 184, "tile")["rects"][0][0][0]
    )


def test_the_owners_lamp_grown_sits_in_the_middle() -> None:
    """L4 g: the owner's lamp at 6x12 and 12x12 holds its bars in the middle."""
    facts = {
        "light.h1401": facts_of(
            {
                "domain": "light",
                "registry": {
                    "capabilities": {
                        "supported_color_modes": ["color_temp", "hs"],
                        "min_color_temp_kelvin": 2000,
                        "max_color_temp_kelvin": 6500,
                    }
                },
            }
        )
    }
    for columns in (6, 12):
        result = _compile_at(
            "apollo/light", "large", columns, 12, {"entity": "light.h1401"}, facts
        )
        # Round 2 (critic major): brightness first grows to 280; the header
        # stays at the top and the bars sit in the middle under it. Round 3
        # (critic major): that left a band under the header. Brightness
        # grows to 320, colour and white to 144: the bars fill the card
        # under the header, and the foot left is under 56.
        dim, *rest = (w for w in result["widgets"] if w["t"] == "slider")
        assert dim["r"][3] == 320, columns
        assert {w["r"][3] for w in rest} == {144}, columns
        head = 72 if columns == 6 else 48
        assert _top(result) == 0, columns
        assert _body_room(result, head)[0] == 0, columns
        assert _body_room(result, head)[1] <= FOOT_CENTRE_MIN, columns


def test_a_card_at_its_own_size_keeps_its_foot() -> None:
    """L4 g: only a grown card, or one with a picture column, is centred."""
    result = _compile(
        COMPONENTS["apollo/light"], "large", {"entity": "light.a"}, {},
        {"light.a": facts_of(DIM_LAMP_RAW)},
    )  # fmt: skip
    assert _top(result) == 0


def test_the_now_playing_card_centres_beside_its_picture() -> None:
    """L4 g: Media Hero at its default size left 172 px under its picture."""
    result = _compile(
        COMPONENTS["apollo/media"], "hero", {"entity": "media_player.a"}, {},
        {"media_player.a": facts_of(MEDIA_RAW)},
    )  # fmt: skip
    assert result["warnings"] == []
    [picture] = [w for w in result["widgets"] if w["t"] == "image"]
    assert picture["r"][2] > 300
    assert _top(result) > FOOT_CENTRE_MIN
    assert _centred(result)


def test_a_controls_page_is_not_centred() -> None:
    """L4 g: the detail copy fills its page from the top, as before."""
    component = COMPONENTS["apollo/light"]
    raw = {
        "params": {"entity": "light.a"},
        "options": {},
        "variant": "large",
        "grid_options": {"columns": 12, "rows": 12},
    }
    card = validate_card_config2(component, raw)
    facts = {"light.a": facts_of(DIM_LAMP_RAW)}
    detail = compile_card2(component, card, facts, 2, detail=True)
    grown = compile_card2(component, card, facts, 2)
    assert _top(detail) <= 2
    assert _body_room(detail, 48)[0] == 0
    # Round 3: the grown card moves its header down with its rows.
    assert _top(grown) > 0 and _body_room(grown, 48)[0] == 0


# ---------------------------------------------------------------- decisions


async def test_the_dim_only_lamp_says_off_once(hass: HomeAssistant) -> None:
    """Decision: off, the header says "Off" and the number is a dash."""
    result = _compile(
        COMPONENTS["apollo/light"], "large", {"entity": "light.a"}, {},
        {"light.a": facts_of(DIM_LAMP_RAW)},
    )  # fmt: skip
    number = next(w for w in result["widgets"] if w["t"] == "label" and w["r"][3] > 100)
    hass.states.async_set("light.a", "off", {})
    assert await _value(hass, result, number["text"]) == "—"
    hass.states.async_set("light.a", "on", {"brightness": 128})
    assert await _value(hass, result, number["text"]) != "—"


@pytest.mark.parametrize(
    ("now", "down", "up"),
    [("20.3", 20, 20.5), ("20.5", 20, 21), ("20.26", 20, 20.5), ("5.2", 5, 5.5)],
)
async def test_a_number_steps_onto_its_grid(
    hass: HomeAssistant, now: str, down: float, up: float
) -> None:
    """Decision: minus and plus round to the step: 20.3 goes to 20 or 20.5."""
    entity = "number.target"
    facts = {entity: facts_of(EVERYTHING_RAW["number"])}
    calls = async_mock_service(hass, "number", "set_value")
    buttons = _bindings(
        "apollo/number", {"entity": entity}, facts, variant="wide",
        options={"control": "buttons"},
    )  # fmt: skip
    hass.states.async_set(entity, now)
    await _run(hass, buttons["down"])
    assert calls[-1].data["value"] == down
    await _run(hass, buttons["up"])
    assert calls[-1].data["value"] == up


async def _gone(hass: HomeAssistant, component_id: str, variant: str, params: dict):
    result = _compile(COMPONENTS[component_id], variant, params, {}, {})
    return await _value(hass, result, result["un"]) in (True, "True")


@pytest.mark.parametrize(
    ("component_id", "variant", "params", "present"),
    [
        ("apollo/button", "tile", {"entity": "script.a"}, ["script.a"]),
        ("apollo/scenes", "large", {"scenes": ["scene.a", "scene.b"]}, ["scene.a"]),
        ("apollo/light-group", "tile", {"lights": ["light.a", "light.b"]}, ["light.a"]),
        (
            "apollo/readings",
            "large",
            {"entities": ["sensor.a", "sensor.b"]},
            ["sensor.a"],
        ),
    ],
)
async def test_a_card_whose_devices_are_missing_fades(
    hass: HomeAssistant, component_id: str, variant: str, params: dict, present: list
) -> None:
    """Decision: a device missing from Home Assistant looks unavailable."""
    assert await _gone(hass, component_id, variant, params)
    for entity in present:
        hass.states.async_set(entity, "on" if entity.startswith("light") else "1")
    assert not await _gone(hass, component_id, variant, params)


async def test_a_room_whose_lights_are_missing_has_no_count(
    hass: HomeAssistant,
) -> None:
    """Decision: no "0 of 2 lights on" and no button for missing lights."""
    from custom_components.apollo_tab.live import async_evaluate_slot

    result = _compile(
        COMPONENTS["apollo/room"], "room",
        {"page": "o", "temperature_sensor": "sensor.t",
         "lights": ["light.a", "light.b"]},
        {}, {},
    )  # fmt: skip
    on = next(w for w in result["widgets"] if w.get("text") == "Turn all on")
    [visible] = [s for s in result["slots"] if s["n"] == on["vis"]["s"]]
    assert await async_evaluate_slot(hass, visible) in (False, "False")
    hass.states.async_set("light.a", "off")
    assert await async_evaluate_slot(hass, visible) in (True, "True")


async def test_a_dropdown_with_no_choices_says_its_state(hass: HomeAssistant) -> None:
    """Decision: no list from Home Assistant: the state, not an empty box.

    L4 round 4 (critic minor): the card said "unknown" twice. The header
    line says the state; the large line is a dash.
    """
    result = _compile(
        COMPONENTS["apollo/select"], "large", {"entity": "select.m"}, {}, {}
    )
    assert not [w for w in result["widgets"] if w["t"] == "choice"]
    # Size ml is written as its pixel size.
    label = next(w for w in result["widgets"] if w.get("px") == 28)
    hass.states.async_set("select.m", "unavailable")
    assert label["text"] == "—"
    state = next(w for w in result["widgets"] if w.get("size") == "s")
    assert await _value(hass, result, state["text"]) == "unavailable"
    facts = {
        "select.m": facts_of(
            {"domain": "select", "state": {"attributes": {"options": ["A", "B"]}}}
        )
    }
    listed = _compile(
        COMPONENTS["apollo/select"], "large", {"entity": "select.m"}, {}, facts
    )
    assert [w for w in listed["widgets"] if w["t"] == "choice"]
    assert not [w for w in listed["widgets"] if w.get("px") == 28]
