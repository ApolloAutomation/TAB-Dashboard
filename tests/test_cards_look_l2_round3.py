"""The look review of every card in every size, after its second check (L2).

A tester and a critic went through the pictures of package L2 a third time.
Each test here holds one of their findings fixed.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.geometry import (
    GAP,
    HEADER_H_2,
    PAD,
    layout_card2,
)
from tests.test_cards_step_a import COMPONENTS, EVERYTHING_RAW, _value
from tests.test_cards_step_b import (
    BLIND_RAW,
    CLIMATE_RAW,
    FAN_RAW,
    MEDIA_RAW,
    _compile,
    _inside,
)

SOURCES = [f"Source {n}" for n in range(8)]
CONTROLS_PAGES = [
    ("apollo/light", "light.a", EVERYTHING_RAW["light"], {}),
    ("apollo/fan-speed", "fan.a", FAN_RAW, {}),
    ("apollo/climate", "climate.a", CLIMATE_RAW, {}),
    ("apollo/media", "media_player.a", MEDIA_RAW, {"sources_shown": SOURCES}),
    ("apollo/cover", "cover.a", BLIND_RAW, {}),
]


def _labels(result: dict) -> list:
    """Return the label widgets of a compiled card."""
    return [w for w in result["widgets"] if w["t"] == "label"]


def _bottom(result: dict) -> int:
    """Return the lowest edge of anything the card draws."""
    edges = [w["r"][1] + w["r"][3] for w in result["widgets"]]
    if result["header"] is not None:
        edges.append(result["header"]["r"][1] + result["header"]["r"][3])
    return max(edges)


# ---------------------------------------------------------------- decision 1


@pytest.mark.parametrize(("component_id", "entity", "raw", "options"), CONTROLS_PAGES)
def test_every_row_a_finger_uses_on_a_controls_page_is_56_high(
    component_id: str, entity: str, raw: dict, options: dict
) -> None:
    """Major: Fan, Thermostat and Media controls pages had rows of 48.

    LOOK-NOTES decision 1: every row on a controls page is at least 56 high.
    A choice of several rows counts per row.
    """
    component = COMPONENTS[component_id]
    variant = component["detail"]
    result = _compile(
        component, variant, {"entity": entity}, options, {entity: facts_of(raw)}
    )
    _inside(result, component_id)
    form = component["variants"][variant]["header"]
    body_top = PAD + HEADER_H_2[form] + GAP
    controls = [
        w
        for w in result["widgets"]
        if ("tap" in w or "change" in w) and w["r"][1] >= body_top
    ]
    assert controls, component_id
    for widget in controls:
        rows = widget.get("rows", 1)
        line = (widget["r"][3] - GAP * (rows - 1)) // rows
        assert line >= 56, (component_id, widget["t"], widget["r"])


def test_the_fan_speed_bar_is_the_tallest_row_of_its_controls_page() -> None:
    """As the brightness bar of a lamp: the bar first and the tallest."""
    fan = _compile(
        COMPONENTS["apollo/fan-speed"],
        "full",
        {"entity": "fan.a"},
        {},
        {"fan.a": facts_of(FAN_RAW)},
    )
    body = [w for w in fan["widgets"] if w["r"][1] >= PAD + HEADER_H_2["tile"] + GAP]
    speed, presets, turning = body
    assert speed["t"] == "slider" and speed["r"][3] == 72
    assert presets["rows"] == 2 and presets["r"][3] == 2 * 56 + GAP
    assert turning["r"][3] == 56


def test_a_fixed_choice_that_needs_more_rows_keeps_each_row_high() -> None:
    """A choice of 56 that needs two rows to stay touchable gets two of 56.

    Before, its 56 were shared by the two rows: cells 24 high.
    """
    body = [
        {
            "kind": "row",
            "height": None,
            "cells": [
                {
                    "type": "choice",
                    "rows": 1,
                    "options": 12,
                    "height": 56,
                    "control": True,
                }
            ],
        }
    ]
    laid = layout_card2(body, 568, 696, "none", None, True)
    [[[rect]]] = laid["rects"]
    [[[rows]]] = laid["rows"]
    assert rows == 2
    assert rect[3] == 2 * 56 + GAP


def test_the_thermostat_buttons_sit_by_the_foot_of_its_arc() -> None:
    """Major: minus and plus were at the card's far corners, 236 px from the number.

    The dial of the controls page is a 360 wide rectangle in the middle of
    the card: the engine draws the buttons at its bottom corners, so they
    sit beside the open foot of the arc.
    """
    climate = _compile(
        COMPONENTS["apollo/climate"],
        "full",
        {"entity": "climate.a"},
        {},
        {"climate.a": facts_of(CLIMATE_RAW)},
    )
    _inside(climate, "climate")
    [dial] = [w for w in climate["widgets"] if w["t"] == "thermostat"]
    x, _y, width, height = dial["r"]
    assert width == 360 and dial["bs"] == 64
    assert x - PAD == climate["w"] - PAD - (x + width)
    # The arc's radius is 0.36 of the square's side: each button's inner
    # edge is within 100 px of the middle of the square.
    middle = x + width // 2
    assert middle - (x + 64) <= 0.36 * height + 20
    # Mode, preset and fan rows still fit under it.
    choices = [w for w in climate["widgets"] if w["t"] == "choice"]
    assert len(choices) == 3


def test_layout_centres_only_a_thermostat_with_its_own_width() -> None:
    """Other widgets with a width keep their place at the left."""
    for kind, x in (("thermostat", 16 + (536 - 200) // 2), ("image", 16)):
        cell = {"type": kind, "width": 200, "height": 200}
        laid = layout_card2(
            [{"kind": "row", "height": None, "cells": [cell]}], 568, 400, "none"
        )
        [[[rect]]] = laid["rects"]
        assert rect[0] == x, kind


# ---------------------------------------------------------------- gone


async def test_a_value_column_shows_a_dash_for_a_device_that_is_gone(
    hass: HomeAssistant,
) -> None:
    """Major: "unavail…" in every narrow value column; the card fades already."""
    for variant in ("large", "wide"):
        listing = _compile(
            COMPONENTS["apollo/readings"],
            variant,
            {"entities": ["sensor.a", "sensor.b"]},
            {},
            {},
        )
        values = [w for w in _labels(listing) if w.get("al") == 2]
        assert len(values) == 2, variant
        hass.states.async_set("sensor.a", "unavailable")
        hass.states.async_set("sensor.b", "21.4", {"unit_of_measurement": "°C"})
        shown = [await _value(hass, listing, w["text"]) for w in values]
        assert shown == ["—", "21.4 °C"], variant
    status = _compile(
        COMPONENTS["apollo/reading"], "chip", {"entity": "sensor.s"}, {}, {}
    )
    [state] = [w for w in _labels(status) if w.get("al") == 2]
    hass.states.async_set("sensor.s", "unavailable")
    assert await _value(hass, status, state["text"]) == "—"
    assert await _value(hass, status, status["un"]) is True
    hass.states.async_set("sensor.s", "21.44", {"unit_of_measurement": "°C"})
    assert await _value(hass, status, state["text"]) == "21.4 °C"
    number = _compile(
        COMPONENTS["apollo/number"],
        "row",
        {"entity": "input_number.n"},
        {},
        {"input_number.n": facts_of(EVERYTHING_RAW["input_number"])},
    )
    [state] = [w for w in _labels(number) if w.get("al") == 2]
    hass.states.async_set("input_number.n", "unavailable")
    assert await _value(hass, number, state["text"]) == "—"
    hass.states.async_set("input_number.n", "40", {"unit_of_measurement": "%"})
    assert await _value(hass, number, state["text"]) == "40 %"
    group = _compile(
        COMPONENTS["apollo/light-group"],
        "wide",
        {"lights": ["light.a", "light.b"]},
        {},
        {},
    )
    [state] = [w for w in _labels(group) if w.get("al") == 2]
    for light in ("light.a", "light.b"):
        hass.states.async_set(light, "unavailable")
    assert await _value(hass, group, state["text"]) == "—"
    hass.states.async_set("light.a", "on")
    assert await _value(hass, group, state["text"]) == "1 of 2 on"


async def test_number_and_graph_never_say_unavailable_with_a_unit(
    hass: HomeAssistant,
) -> None:
    """Minor: Number Wide read "unavailable °C", Graph Wide "unavailabl…"."""
    number = _compile(
        COMPONENTS["apollo/number"],
        "wide",
        {"entity": "input_number.n"},
        {},
        {"input_number.n": facts_of(EVERYTHING_RAW["input_number"])},
    )
    [line] = [w for w in _labels(number) if w["size"] == "s"]
    hass.states.async_set(
        "input_number.n", "unavailable", {"unit_of_measurement": "°C"}
    )
    assert await _value(hass, number, line["text"]) == "unavailable"
    hass.states.async_set("input_number.n", "21", {"unit_of_measurement": "°C"})
    assert await _value(hass, number, line["text"]) == "21 °C"
    graph = _compile(COMPONENTS["apollo/graph"], "wide", {"entity": "sensor.g"}, {}, {})
    big = next(w for w in _labels(graph) if w.get("px") == 28)
    hass.states.async_set("sensor.g", "unavailable", {"unit_of_measurement": "°C"})
    assert await _value(hass, graph, big["text"]) == "—"
    hass.states.async_set("sensor.g", "21.4", {"unit_of_measurement": "°C"})
    assert await _value(hass, graph, big["text"]) == "21.4 °C"


# ---------------------------------------------------------------- feet


@pytest.mark.parametrize(
    ("component_id", "variant", "params", "facts"),
    [
        (
            "apollo/room",
            "room",
            {
                "temperature_sensor": "sensor.t",
                "lights": ["light.a"],
                "extra": "sensor.x",
            },
            {},
        ),
        (
            "apollo/room",
            "room",
            {"temperature_sensor": "sensor.t", "lights": ["light.a"]},
            {},
        ),
        (
            "apollo/appliance",
            "large",
            {
                "state": "sensor.w",
                "remaining": "sensor.left",
                "progress": "sensor.done",
                "programme": "sensor.programme",
                "start_button": "button.start",
                "pause_button": "button.pause",
            },
            {},
        ),
        ("apollo/fan-speed", "large", {"entity": "fan.a"}, {"fan.a": FAN_RAW}),
        (
            "apollo/fan-speed",
            "large",
            {"entity": "fan.a"},
            {
                "fan.a": {
                    **FAN_RAW,
                    "registry": {
                        **FAN_RAW["registry"],
                        "capabilities": {
                            "preset_modes": ["auto", "sleep", "breeze"],
                            "percentage_step": 25,
                        },
                    },
                }
            },
        ),
    ],
)
def test_no_empty_foot_at_the_default_size(
    component_id: str, variant: str, params: dict, facts: dict
) -> None:
    """Major: the bands moved from the top to the foot of Room, Appliance, Fan."""
    result = _compile(
        COMPONENTS[component_id],
        variant,
        params,
        {},
        {entity: facts_of(raw) for entity, raw in facts.items()},
    )
    _inside(result, component_id)
    assert result["h"] - PAD - _bottom(result) <= 56, (component_id, params)


def test_the_room_and_the_appliance_have_their_new_default_size() -> None:
    """Room is 9x4, Appliance Large 12x5: the content fills them."""
    assert COMPONENTS["apollo/room"]["variants"]["room"]["grid"] == [9, 4]
    assert COMPONENTS["apollo/appliance"]["variants"]["large"]["grid"] == [12, 5]


# ---------------------------------------------------------------- the rest


def test_the_accent_marks_the_open_part_of_a_blind_on_every_size() -> None:
    """Major: Tall and Window coloured the closed part, Tile and the page the open part.

    The hanging blind is drawn in the muted colour; the accent is left for
    the open part, as on the Tile and the controls page.
    """
    facts = {"cover.a": facts_of(BLIND_RAW)}
    for variant in ("tall", "window"):
        result = _compile(
            COMPONENTS["apollo/cover"], variant, {"entity": "cover.a"}, {}, facts
        )
        [bar] = [w for w in result["widgets"] if w["t"] == "slider"]
        assert bar["c"] == "#9AA3AF", variant
        turned = _compile(
            COMPONENTS["apollo/cover"],
            variant,
            {"entity": "cover.a"},
            {"turn_round": True},
            facts,
        )
        [bar] = [w for w in turned["widgets"] if w["t"] == "slider"]
        assert "c" not in bar, variant
    for variant in ("tile", "full"):
        result = _compile(
            COMPONENTS["apollo/cover"], variant, {"entity": "cover.a"}, {}, facts
        )
        [bar] = [w for w in result["widgets"] if w["t"] == "slider"]
        assert "c" not in bar, variant


async def test_media_large_says_the_track_once(hass: HomeAssistant) -> None:
    """Minor: "Harvest Moon" over "Harvest Moon" when the album has its name."""
    media = _compile(
        COMPONENTS["apollo/media"], "large", {"entity": "media_player.m"}, {}, {}
    )
    track, album = [w for w in _labels(media) if w["r"][1] > PAD + HEADER_H_2["tile"]][
        :2
    ]
    hass.states.async_set(
        "media_player.m",
        "playing",
        {"media_title": "Harvest Moon", "media_album_name": "Harvest Moon"},
    )
    assert await _value(hass, media, track["text"]) == "Harvest Moon"
    assert await _value(hass, media, album["text"]) == ""
    hass.states.async_set(
        "media_player.m",
        "playing",
        {"media_title": "Harvest Moon", "media_album_name": "Harvest Moon (Deluxe)"},
    )
    assert await _value(hass, media, album["text"]) == "Harvest Moon (Deluxe)"
    # Now playing: title, artist, then the album only when it says more.
    hero = _compile(
        COMPONENTS["apollo/media"], "hero", {"entity": "media_player.m"}, {}, {}
    )
    texts = [await _value(hass, hero, w["text"]) for w in _labels(hero)]
    assert texts.count("Harvest Moon") == 1 and "Harvest Moon (Deluxe)" in texts
    hass.states.async_set(
        "media_player.m",
        "playing",
        {"media_title": "Harvest Moon", "media_album_name": "Harvest Moon"},
    )
    texts = [await _value(hass, hero, w["text"]) for w in _labels(hero)]
    assert texts.count("Harvest Moon") == 1
