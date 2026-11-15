"""The look review of every card in every size, after its first check (L2).

A tester and a critic went through the pictures of package L2 again. Each
test here holds one of their findings fixed.
"""

from __future__ import annotations

import copy

import pytest
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse

from custom_components.apollo_tab.maker.compile import compile_card
from custom_components.apollo_tab.maker.compile2 import (
    NAME_W_SPARE,
    compile_card2,
    cut_middle,
    cut_to_fit,
    name_chars,
    name_width,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.compile2_v1 import compile_card2_v1
from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.geometry import TILE_V_NO_STATE_H, layout_card2
from custom_components.apollo_tab.maker.schema import (
    validate_card_config,
    validate_component,
)
from tests.test_cards_step_a import COMPONENTS, _value
from tests.test_cards_step_b import FAN_RAW, _compile, _inside
from tests.test_maker_schema2 import _doc

PEOPLE = [f"person.p{n}" for n in range(8)]
DEVICES = [f"sensor.s{n}" for n in range(8)]
SCENES = [f"scene.s{n}" for n in range(8)]


def _texts(result: dict) -> list:
    """Return the label texts of a compiled card, slots as they are."""
    return [w["text"] for w in result["widgets"] if w["t"] == "label"]


def _band(result: dict) -> int:
    """Return the tallest empty band above a widget, from the header down."""
    header = result["header"]
    reached = 16 if header is None else header["r"][1] + header["r"][3]
    band = 0
    for widget in sorted(result["widgets"], key=lambda w: w["r"][1]):
        band = max(band, widget["r"][1] - reached)
        reached = max(reached, widget["r"][1] + widget["r"][3])
    return band


# ---------------------------------------------------------------- gone


async def test_the_gauge_says_when_its_sensor_is_gone(hass: HomeAssistant) -> None:
    """Blocker: an unavailable power sensor read a plain 0 on the dial."""
    gauge = COMPONENTS["apollo/dial"]
    for variant in ("tile", "large"):
        result = _compile(gauge, variant, {"entity": "sensor.p"}, {}, {})
        _inside(result, variant)
        [dial] = [w for w in result["widgets"] if w["t"] == "thermostat"]
        hass.states.async_set("sensor.p", "unavailable")
        assert await _value(hass, result, dial["value"]) is None
        assert await _value(hass, result, result["un"]) is True
        texts = [await _value(hass, result, t) for t in _texts(result)]
        assert "0" not in " ".join(str(t) for t in texts), variant
        if variant == "large":
            assert texts == ["unavailable"]
        hass.states.async_set("sensor.p", "1840", {"unit_of_measurement": "W"})
        assert await _value(hass, result, dial["value"]) == 1840
        assert await _value(hass, result, result["un"]) is False
        texts = [await _value(hass, result, t) for t in _texts(result)]
        if variant == "large":
            assert texts == ["0 to 5000 W"]
    assert _texts(_compile(gauge, "tile", {"entity": "sensor.p"}, {}, {})) == []


async def test_the_room_is_honest_while_its_devices_are_gone(
    hass: HomeAssistant,
) -> None:
    """Major: "unavailable% · 0 of 3 on", a big "unavailable" and "Lights on"."""
    room = COMPONENTS["apollo/room"]
    lights = ["light.a", "light.b", "light.c"]
    params = {
        "temperature_sensor": "sensor.t",
        "humidity_sensor": "sensor.h",
        "lights": lights,
    }
    for variant in ("room", "tile"):
        result = _compile(room, variant, params, {}, {})
        _inside(result, variant)
        for entity in ("sensor.t", "sensor.h", *lights):
            hass.states.async_set(entity, "unavailable")
        texts = [await _value(hass, result, t) for t in _texts(result)]
        assert not [t for t in texts if "%" in str(t) or " on" in str(t)], texts
        assert "—" in texts, texts
        buttons = [w for w in result["widgets"] if w["t"] == "button"]
        assert [await _value(hass, result, b["vis"]) for b in buttons] == [False] * len(
            buttons
        )
        hass.states.async_set("sensor.t", "21.5", {"unit_of_measurement": "°C"})
        hass.states.async_set("sensor.h", "48")
        hass.states.async_set("light.a", "off")
        texts = [await _value(hass, result, t) for t in _texts(result)]
        assert "48% · 0 of 3 on" in texts and "21.5°C" in texts, texts
        if buttons:
            assert [await _value(hass, result, b["vis"]) for b in buttons] == [
                False,
                True,
            ]


async def test_the_weather_draws_no_day_without_a_forecast(
    hass: HomeAssistant,
) -> None:
    """Major: the days of a weather that is gone drew five broken pictures."""
    weather = _compile(
        COMPONENTS["apollo/forecast"], "large", {"entity": "weather.a"}, {}, {}
    )
    days = [w for w in weather["widgets"] if w["t"] == "image" and w["r"][3] == 32]
    assert len(days) == 5
    hass.states.async_set("weather.a", "unavailable")
    # No answer at all: the forecast call fails.
    assert [await _value(hass, weather, d["vis"]) for d in days] == [False] * 5

    async def forecasts(call: ServiceCall) -> dict:
        return {
            "weather.a": {
                "forecast": [{"datetime": "2026-11-15", "condition": "sunny"}]
            }
        }

    hass.services.async_register(
        "weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY
    )
    hass.states.async_set("weather.a", "sunny", {"temperature": 12})
    shown = [await _value(hass, weather, d["vis"]) for d in days]
    assert shown == [True, False, False, False, False]
    assert await _value(hass, weather, days[0]["value"]) == "mdi:weather-sunny"


async def test_the_fan_hides_its_presets_while_it_is_gone(hass: HomeAssistant) -> None:
    """Major: on Glass a gone fan's presets read as loose words."""
    fan = _compile(
        COMPONENTS["apollo/fan-speed"],
        "large",
        {"entity": "fan.a"},
        {},
        {"fan.a": facts_of(FAN_RAW)},
    )
    parts = [w for w in fan["widgets"] if w["t"] in ("choice", "button")]
    assert {w["t"] for w in parts} == {"choice", "button"}
    hass.states.async_set("fan.a", "unavailable")
    assert [await _value(hass, fan, w["vis"]) for w in parts] == [False, False]
    hass.states.async_set("fan.a", "on", {"percentage": 50})
    assert [await _value(hass, fan, w["vis"]) for w in parts] == [True, True]


# ---------------------------------------------------------------- bands


def test_the_cards_fill_their_default_size_too() -> None:
    """Decision 5 for the cards the first check named: Room, Link, Lock Tall."""
    cases = {
        ("apollo/room", "room"): {
            "temperature_sensor": "sensor.t",
            "lights": ["light.a"],
            "extra": "sensor.x",
        },
        ("apollo/page-link", "tile"): {"page": "home", "entity": "sensor.a"},
        ("apollo/page-link", "wide"): {"page": "home", "entity": "sensor.a"},
        ("apollo/door-lock", "tall"): {"entity": "lock.a"},
        ("apollo/door-lock", "tile"): {"entity": "lock.a"},
    }
    for (component_id, variant), params in cases.items():
        result = _compile(COMPONENTS[component_id], variant, params, {}, {})
        _inside(result, component_id)
        assert _band(result) <= 56, (component_id, variant, _band(result))


@pytest.mark.parametrize(
    ("component_id", "variant", "param", "entities"),
    [
        ("apollo/people", "tall", "people", PEOPLE[:3]),
        ("apollo/people", "tall", "people", PEOPLE),
        ("apollo/readings", "large", "entities", DEVICES[:4]),
        ("apollo/readings", "large", "entities", DEVICES),
    ],
)
def test_a_short_list_shares_the_height_of_its_card(
    component_id: str, variant: str, param: str, entities: list
) -> None:
    """Major: three lines under the title left 200 px empty at the foot."""
    result = _compile(COMPONENTS[component_id], variant, {param: entities}, {}, {})
    _inside(result, component_id)
    rows = sorted({w["r"][1] for w in result["widgets"]})
    assert len(rows) == len(entities)
    assert rows[0] == 16 + 32 + 8
    bottom = max(w["r"][1] + w["r"][3] for w in result["widgets"])
    assert result["h"] - 16 - bottom < 8
    assert {w["r"][3] for w in result["widgets"]} == {result["widgets"][0]["r"][3]}


def test_people_tall_keeps_a_short_name_whole() -> None:
    """Major: "Emma" was cut to "Em…" beside the place "Home"."""
    result = _compile(COMPONENTS["apollo/people"], "tall", {"people": PEOPLE}, {}, {})
    name, place = [w for w in result["widgets"] if w["t"] == "label"][:2]
    assert name["r"][2] * 10 >= name_width("Emma") + NAME_W_SPARE
    # "School" at 14 px is about 48 px wide.
    assert place["r"][2] >= 48


def test_a_list_value_has_the_room_of_a_value_and_the_name_the_rest() -> None:
    """Major: names were cut beside 60 px left empty in the value column."""
    for variant, value_w in (("large", 88), ("wide", 80)):
        result = _compile(
            COMPONENTS["apollo/readings"], variant, {"entities": DEVICES[:2]}, {}, {}
        )
        icon, name, value = result["widgets"][:3]
        assert value["r"][2] == value_w
        assert name["r"][0] + name["r"][2] + 8 == value["r"][0]
        assert value["r"][0] + value["r"][2] == result["w"] - 16


def test_a_chip_keeps_a_short_value_short() -> None:
    """Major: the Status chip cut its name while 70 px stayed empty.

    Round 4: 88, not 80. "unavailable" is 82 px wide and was cut.
    """
    parts = layout_card2([], 376, 56, "chip")["header"]
    assert parts["state"][2] == 88
    assert parts["name"][2] == 376 - 32 - 24 - 8 - 8 - 88
    narrow = layout_card2([], 184, 56, "chip")["header"]
    assert narrow["state"][2] == (184 - 32 - 24 - 8) // 3


# ---------------------------------------------------------------- names


@pytest.mark.parametrize(
    ("name", "width"),
    [
        ("Washing Machine", 152),
        ("Front Door Lock", 152),
        ("Front Door Lock", 100),
        ("Living Room Lamp 1", 152),
        ("Living Room Lamp 1", 100),
        ("Coffee Machine", 152),
        ("Living Room Temperature", 224),
        ("WWWWWWWW MMMMMMMM", 152),
    ],
)
def test_a_cut_name_fits_its_room_and_has_one_ellipsis(name: str, width: int) -> None:
    """Major: "Washin…Machi…": the cut name was too wide, the tablet cut again."""
    shown = cut_to_fit(name, name_chars(width), width)
    room = width * 10 - NAME_W_SPARE
    if name_width(name) <= room:
        assert shown == name
    elif shown != name:
        assert name_width(shown) <= room and shown.count("…") == 1
    else:
        # No middle cut is left: the tablet cuts the end, once.
        assert cut_middle(name, name_chars(width) - 1) == name or "…" not in shown
    assert cut_to_fit("Washing Machine", 14, 152) != "Washin…Machine"
    assert cut_to_fit("Front Door Lock", 14, 152) == "Front Door Lock"


async def test_the_live_name_cuts_as_cut_to_fit(hass: HomeAssistant) -> None:
    """The tile's name from Home Assistant gives what cut_to_fit gives."""
    lock = COMPONENTS["apollo/door-lock"]
    for variant in ("tile", "wide"):
        result = _compile(lock, variant, {"entity": "lock.a"}, {}, {})
        if variant == "wide":
            # Wide has no header: its name is a plain label.
            continue
        name = next(w for w in result["widgets"] if w["t"] == "label")
        width = name["r"][2]
        for full in (
            "Washing Machine",
            "Front Door Lock",
            "Living Room Lamp 1",
            "Kitchen Ceiling Light",
            "WWWWWWWW MMMMMMMM",
            "Hall",
        ):
            hass.states.async_set("lock.a", "locked", {"friendly_name": full})
            shown = await _value(hass, result, name["text"])
            assert shown == cut_to_fit(full, name_chars(width), width), full


# ---------------------------------------------------------------- headers


def test_a_tile_v_header_without_a_state_line_ends_under_the_name() -> None:
    """The stacked header of a card with no state line is 80 high, not 104."""
    laid = layout_card2(
        [
            {
                "kind": "row",
                "height": None,
                "cells": [{"type": "button", "control": True}],
            }
        ],
        184,
        184,
        "tile_v",
        None,
        state_line=False,
    )
    assert "state" not in laid["header"]
    assert laid["header"]["name"] == [16, 68, 152, 28]
    assert TILE_V_NO_STATE_H == 80
    [[[button]]] = laid["rects"]
    assert button[1] >= 16 + 80 + 8 and button[1] + button[3] == 184 - 16
    full = layout_card2([], 184, 184, "tile_v", None)["header"]
    assert "state" in full


async def test_the_small_and_tile_names_are_not_cut(hass: HomeAssistant) -> None:
    """Major: "Coffee M…", "Good Nig…" and "Fron…Lock" beside empty room."""
    for component_id, variant, entity in (
        ("apollo/switch", "small", "switch.coffee"),
        ("apollo/button", "small", "script.good_night"),
        ("apollo/door-lock", "tile", "lock.front"),
    ):
        result = _compile(COMPONENTS[component_id], variant, {"entity": entity}, {}, {})
        _inside(result, component_id)
        name = next(w for w in result["widgets"] if w["t"] == "label")
        assert name["r"][2] == 152, component_id
    lock = _compile(
        COMPONENTS["apollo/door-lock"], "tile", {"entity": "lock.f"}, {}, {}
    )
    state = next(w for w in lock["widgets"] if w["t"] == "label" and w.get("al") == 2)
    hass.states.async_set("lock.f", "locked")
    assert await _value(hass, lock, state["text"]) == "locked"
    switch = _compile(
        COMPONENTS["apollo/switch"], "small", {"entity": "switch.c"}, {}, {}
    )
    hass.states.async_set("switch.c", "unavailable")
    assert await _value(hass, switch, switch["un"]) is True


def test_lights_together_wide_has_a_bar_a_finger_can_hold() -> None:
    """Major: the Wide bar was 40 px high, under the 48 a finger needs."""
    group = _compile(
        COMPONENTS["apollo/light-group"],
        "wide",
        {"lights": ["light.a", "light.b"]},
        {},
        {},
    )
    _inside(group, "wide")
    [bar] = [w for w in group["widgets"] if w["t"] == "slider"]
    assert bar["r"][3] >= 56
    assert {w["r"][3] for w in group["widgets"] if w["t"] == "button"} == {48}


# ---------------------------------------------------------------- scenes


def test_up_to_four_scenes_share_two_rows_on_wide() -> None:
    """Major: "Movie Night" was cut to "Movie…" on four 80 px buttons."""
    scenes = COMPONENTS["apollo/scenes"]
    for count, widths in (
        (4, [168, 168, 168, 168]),
        (3, [168, 168, 344]),
        (2, [168, 168]),
        (6, [80, 80, 80, 80, 168, 168]),
    ):
        result = _compile(scenes, "wide", {"scenes": SCENES[:count]}, {}, {})
        _inside(result, str(count))
        assert [w["r"][2] for w in result["widgets"]] == widths, count


def test_two_rows_is_a_yes_or_no_of_a_loop() -> None:
    """`two_rows` takes true or false, and only on an item with `for_each`."""
    doc = _doc(
        params={
            "entity": {"domain": "light"},
            "lights": {"domain": "light", "multiple": True, "max": 16},
        },
        variants={
            "wide": {
                "name": "Wide",
                "grid": [12, 3],
                "header": "none",
                "layout": [
                    {
                        "type": "label",
                        "for_each": "lights",
                        "as": "l",
                        "per_row": 4,
                        "two_rows": True,
                        "text": "{{ l }}",
                    }
                ],
            }
        },
    )
    validate_component(copy.deepcopy(doc))
    bad = copy.deepcopy(doc)
    bad["variants"]["wide"]["layout"][0]["two_rows"] = "yes"
    with pytest.raises(MakerError, match="two_rows"):
        validate_component(bad)
    no_loop = copy.deepcopy(doc)
    for key in ("for_each", "as", "per_row"):
        no_loop["variants"]["wide"]["layout"][0].pop(key)
    with pytest.raises(MakerError):
        validate_component(no_loop)


def test_at_most_counts_against_the_widget_budget() -> None:
    """A loop's `at_most` keeps a card file inside the 48 widgets when it loads."""
    doc = _doc(
        params={
            "entity": {"domain": "light"},
            "lights": {"domain": "light", "multiple": True, "max": 16},
        },
        variants={
            "wide": {
                "name": "Wide",
                "grid": [12, 3],
                "header": "none",
                "layout": [
                    {
                        "type": "row",
                        "for_each": "lights",
                        "as": "l",
                        "at_most": 4,
                        "items": [
                            {"type": "label", "text": "{{ l }}"},
                            {"type": "label", "text": "a"},
                            {"type": "label", "text": "b"},
                            {"type": "label", "text": "c"},
                        ],
                    }
                ],
            }
        },
    )
    validate_component(copy.deepcopy(doc))
    uncapped = copy.deepcopy(doc)
    uncapped["variants"]["wide"]["layout"][0].pop("at_most")
    with pytest.raises(MakerError, match="widgets"):
        validate_component(uncapped)


# ---------------------------------------------------------------- the rest


def test_a_tiny_schema_1_card_shows_its_icon() -> None:
    """Major: Camera snapshot at 3x1 was an empty box."""
    camera = COMPONENTS["apollo/camera-snapshot"]
    card = validate_card_config(
        camera,
        {
            "type": "custom:apollo-tab-card",
            "component": "apollo/camera-snapshot",
            "params": {"entity": "camera.drive"},
            "grid_options": {"columns": 3, "rows": 1},
        },
    )
    result = compile_card(camera, card)
    [icon] = result["widgets"]
    assert (icon["t"], icon["value"]) == ("image", "mdi:cctv")
    assert icon["r"] == [32, 16, 24, 24]
    big = validate_card_config(
        camera,
        {
            "type": "custom:apollo-tab-card",
            "component": "apollo/camera-snapshot",
            "params": {"entity": "camera.drive"},
        },
    )
    assert [w["t"] for w in compile_card(camera, big)["widgets"]] == ["image", "label"]


def test_the_appliance_tile_keeps_its_old_look_on_an_old_tablet() -> None:
    """Minor: the version 1 tile's time left went from 44 px to 28 px."""
    appliance = COMPONENTS["apollo/appliance"]
    raw = {
        "params": {"state": "sensor.w", "remaining": "sensor.left"},
        "variant": "tile",
        "grid_options": {"columns": 6, "rows": 3},
    }
    card = validate_card_config2(appliance, raw)
    form = compile_card2_v1(appliance, card, {})
    assert form is not None
    sizes = [w["size"] for w in form["widgets"] if w["t"] == "label"]
    assert sizes == ["l"]
    new = compile_card2(appliance, card, {}, 2)
    assert [w.get("px") for w in new["widgets"] if w["t"] == "label"][-1] == 28
