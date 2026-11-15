"""The look review of every card in every size (package L2).

Two critics went through a picture of every card in every size. Each test
here holds one of their findings fixed: in the converter where the rule is
for every card, else in the card file.
"""

from __future__ import annotations

import copy

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
from tests.test_cards_step_a import COMPONENTS, OWNER_LAMP_RAW, _value
from tests.test_cards_step_b import (
    ALARM_RAW,
    BLIND_RAW,
    FAN_RAW,
    _compile,
    _inside,
    _kinds,
)
from tests.test_maker_schema2 import _doc

PEOPLE = [f"person.p{n}" for n in range(8)]
DEVICES = [f"sensor.s{n}" for n in range(8)]


def _at(component: dict, variant: str, columns: int, rows: int, params: dict) -> dict:
    """Compile a variant at a grid of its own."""
    raw = {
        "params": params,
        "variant": variant,
        "grid_options": {"columns": columns, "rows": rows},
    }
    return compile_card2(component, validate_card_config2(component, raw), {}, 2)


def _texts(result: dict) -> list:
    """Return the label texts of a compiled card, slots as they are."""
    return [w["text"] for w in result["widgets"] if w["t"] == "label"]


# ---------------------------------------------------------------- loops


def test_a_loop_makes_at_most_its_at_most_copies() -> None:
    """`at_most` keeps the first copies; the widget count counts no more."""
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
                        "at_most": 4,
                        "text": "{{ l }}",
                    }
                ],
            }
        },
    )
    component = validate_component(copy.deepcopy(doc))
    lights = [f"light.l{n}" for n in range(9)]
    result = _at(component, "wide", 12, 3, {"entity": "light.a", "lights": lights})
    assert _kinds(result) == ["label"] * 4
    assert result["warnings"] == []
    for bad in ({"at_most": 0}, {"at_most": 17}, {"at_most": "x"}):
        broken = copy.deepcopy(doc)
        broken["variants"]["wide"]["layout"][0].update(bad)
        with pytest.raises(MakerError):
            validate_component(broken)
    no_loop = copy.deepcopy(doc)
    item = no_loop["variants"]["wide"]["layout"][0]
    for key in ("for_each", "as", "per_row"):
        item.pop(key)
    with pytest.raises(MakerError, match="for_each"):
        validate_component(no_loop)


async def test_people_wide_holds_four_and_says_how_many_more(
    hass: HomeAssistant,
) -> None:
    """Blocker: with 8 people a second row of faces lay under the wrong names.

    One row of four; the fourth place says "+5 more".
    """
    people = COMPONENTS["apollo/people"]
    result = _compile(people, "wide", {"people": PEOPLE}, {}, {})
    _inside(result, "8 people")
    faces = [w for w in result["widgets"] if w["t"] == "image"]
    assert len(faces) == 4
    assert len({w["r"][1] for w in faces}) == 1
    for n, person in enumerate(PEOPLE):
        hass.states.async_set(person, "home", {"friendly_name": f"P{n}"})
    names = [await _value(hass, result, t) for t in _texts(result)[:4]]
    assert names == ["P0", "P1", "P2", "+5 more"]
    assert await _value(hass, result, faces[3]["value"]) == "mdi:account-multiple"
    four = _compile(people, "wide", {"people": PEOPLE[:4]}, {}, {})
    names = [await _value(hass, four, t) for t in _texts(four)[:4]]
    assert names == ["P0", "P1", "P2", "P3"]
    hass.states.async_set(PEOPLE[0], "unavailable", {"friendly_name": "P0"})
    places = _texts(four)[4:]
    assert await _value(hass, four, places[0]) == "—"


def test_people_tall_and_list_large_start_under_the_title() -> None:
    """Major: three rows sat at the foot of the card under a 200 px band."""
    for component_id, param, entities in (
        ("apollo/people", "people", PEOPLE[:3]),
        ("apollo/readings", "entities", DEVICES[:3]),
    ):
        variant = "tall" if component_id == "apollo/people" else "large"
        result = _compile(COMPONENTS[component_id], variant, {param: entities}, {}, {})
        first = min(w["r"][1] for w in result["widgets"] if w["t"] != "label")
        assert first == 16 + 32 + 8, component_id


async def test_list_wide_holds_four_and_says_how_many_more(hass: HomeAssistant) -> None:
    """Major: List Wide dropped four of eight devices without a word."""
    readings = COMPONENTS["apollo/readings"]
    result = _compile(readings, "wide", {"entities": DEVICES}, {}, {})
    _inside(result, "8 devices")
    for n, entity in enumerate(DEVICES):
        hass.states.async_set(entity, str(n), {"friendly_name": f"S{n}"})
    texts = [str(await _value(hass, result, t)) for t in _texts(result)]
    assert texts == ["S0", "0", "S1", "1", "S2", "2", "+5 more", ""]
    icons = [w for w in result["widgets"] if w["t"] == "image"]
    assert await _value(hass, result, icons[3]["vis"]) is False
    assert await _value(hass, result, icons[2]["vis"]) is True


def test_list_names_get_the_larger_share_of_a_line() -> None:
    """Major: names were cut at half the line while the value took 100 px less."""
    result = _compile(
        COMPONENTS["apollo/readings"], "large", {"entities": DEVICES[:2]}, {}, {}
    )
    name, value = [w for w in result["widgets"] if w["t"] == "label"][:2]
    assert name["r"][2] > value["r"][2] * 1.4


def test_a_card_about_several_devices_has_its_own_icon() -> None:
    """Minor: List and People showed the first device's icon in the header."""
    facts = {DEVICES[0]: facts_of({"domain": "sensor", "device_class": "temperature"})}
    readings = COMPONENTS["apollo/readings"]
    raw = {
        "params": {"entities": DEVICES[:2]},
        "variant": "large",
        "grid_options": {"columns": 12, "rows": 6},
    }
    result = compile_card2(readings, validate_card_config2(readings, raw), facts, 2)
    assert result["header"]["icon"] == readings["icon"]


# ---------------------------------------------------------------- headers


def test_a_variant_may_say_its_own_state_line() -> None:
    """`state` on a variant: an input or none; for chip, tile and title headers.

    L5: a title header shows it at its right (Dropdown Wide), so "title"
    left the bad list; a header of none still has no place for it.
    """
    base = _doc(
        inputs={"is_on": "{{ is_state(entity, 'on') }}", "words": "{{ 'Hi' }}"},
        state="is_on",
    )
    base["variants"]["tile"]["header"] = "tile"
    for value, shown in ((None, "is_on"), ("words", "words"), ("none", None)):
        doc = copy.deepcopy(base)
        if value is not None:
            doc["variants"]["tile"]["state"] = value
        component = validate_component(doc)
        result = _at(component, "tile", 6, 3, {"entity": "light.a"})
        states = [
            w for w in result["widgets"] if w["t"] == "label" and w["size"] == "s"
        ]
        if shown is None:
            assert states == []
        else:
            [state] = states
            [slot] = [s for s in result["slots"] if s["n"] == state["text"]["s"]]
            assert shown in slot["template"]
    for bad, header in (("nothing", "tile"), ("words", "none")):
        doc = copy.deepcopy(base)
        doc["variants"]["tile"].update({"state": bad, "header": header})
        with pytest.raises(MakerError, match="state"):
            validate_component(doc)


def test_a_card_may_name_itself_from_an_input() -> None:
    """Major: Room was titled with its temperature sensor's name."""
    base = _doc(inputs={"place": "{{ 'Kitchen' }}"}, title="place")
    component = validate_component(copy.deepcopy(base))
    result = _at(component, "tile", 6, 3, {"entity": "light.a"})
    [slot] = [s for s in result["slots"] if s["n"] == result["header"]["title"]["s"]]
    assert "Kitchen" in slot["template"]
    titled = validate_card_config2(
        component,
        {"params": {"entity": "light.a"}, "title": "Mine", "variant": "tile"},
    )
    assert compile_card2(component, titled, {}, 2)["header"]["title"] == "Mine"
    with pytest.raises(MakerError, match="title"):
        validate_component(_doc(title="{{ 'x' }}"))


async def test_the_room_is_named_after_its_area_and_says_the_rest(
    hass: HomeAssistant,
) -> None:
    """Room: its own name and icon, the header line without the temperature."""
    room = COMPONENTS["apollo/room"]
    params = {"temperature_sensor": "sensor.t", "lights": ["light.a"]}
    facts = {"sensor.t": facts_of({"domain": "sensor", "device_class": "temperature"})}
    result = compile_card2(
        room,
        validate_card_config2(room, {"params": params, "variant": "room"}),
        facts,
        2,
    )
    assert result["widgets"][0]["value"] == "mdi:sofa"
    hass.states.async_set("sensor.t", "21.5", {"unit_of_measurement": "°C"})
    hass.states.async_set("light.a", "on")
    texts = [await _value(hass, result, t) for t in _texts(result)]
    # L4 round 2: value, space, unit, as on the reading cards.
    assert texts[:3] == ["Room", "1 of 1 on", "21.5 °C"]


def test_a_chip_gives_the_name_two_thirds() -> None:
    """Major: the Status chip cut its name while the value had half the card."""
    parts = layout_card2([], 376, 56, "chip")["header"]
    assert parts["name"][2] > 2 * parts["state"][2] - 16
    assert parts["state"][0] + parts["state"][2] == 376 - 16


@pytest.mark.parametrize("form", ["chip", "tile"])
def test_a_header_too_narrow_for_a_name_shows_the_icon_alone(form: str) -> None:
    """Blocker: at 3x1 a name was drawn as "." and the state as "…"."""
    parts = layout_card2([], 88, 120, form)["header"]
    assert set(parts) == ({"icon"} if form == "chip" else {"badge"})
    [icon] = parts.values()
    assert icon[0] * 2 + icon[2] == 88


def test_every_card_at_the_smallest_grid_shows_its_icon() -> None:
    """Blocker: at the editor's smallest grid, 3x1, 14 cards were empty boxes.

    A card that names what it shows `alone` shows that value instead of
    its icon (round 4: a clock that showed a clock icon said nothing).
    """
    for component_id, component in COMPONENTS.items():
        if component.get("schema") != 2:
            continue
        smallest = min(
            (v for v in component["variants"].values() if v["picker"]),
            key=lambda v: v["grid"][0] * v["grid"][1],
        )
        name = next(k for k, v in component["variants"].items() if v is smallest)
        params = {}
        for key, spec in component["params"].items():
            if spec.get("kind") != "entity" or spec.get("optional"):
                continue
            kind = spec.get("domain") or (spec.get("domains") or ["sensor"])
            kind = kind[0] if isinstance(kind, list) else kind
            kind = "sensor" if kind == "any" else kind
            entity = f"{kind}.a"
            params[key] = [entity] if spec["multiple"] else entity
        for key, spec in component["params"].items():
            if spec.get("kind") == "page" and not spec.get("optional"):
                params[key] = "home"
        result = _at(component, name, 3, 1, params)
        drawn = result["widgets"] or (result["header"] and result["header"]["r"][2])
        assert drawn, component_id
        if not result["widgets"]:
            continue
        if component["alone"] is not None:
            [value] = result["widgets"]
            assert (value["t"], value["size"], value["al"]) == ("label", "m", 1)
            assert value["r"] == [4, 14, 80, 28], component_id
            continue
        images = [w for w in result["widgets"] if w["t"] == "image"]
        assert images, component_id
        assert all(w["t"] != "label" for w in result["widgets"]), component_id


def test_a_tiny_card_has_no_header_icon_beside_its_own() -> None:
    """A title header that does not fit is left out; the icon shows once.

    Round 4: the gauge shows its number there, and no icon beside it. A
    card with no value of its own keeps the one icon.
    """
    gauge = COMPONENTS["apollo/dial"]
    result = _at(gauge, "tile", 3, 1, {"entity": "sensor.p", "max": 10})
    assert result["header"] is None
    [value] = result["widgets"]
    assert (value["t"], value["r"]) == ("label", [4, 14, 80, 28])
    people = COMPONENTS["apollo/people"]
    result = _at(people, "tall", 3, 1, {"people": ["person.a"]})
    assert result["header"] is None
    [icon] = result["widgets"]
    assert (icon["t"], icon["r"]) == ("image", [32, 16, 24, 24])


# ---------------------------------------------------------------- choices


def test_three_choices_take_one_row_not_two_and_a_hole() -> None:
    """Minor: three presets in two rows left one alone beside a hole."""
    row = {
        "kind": "row",
        "height": None,
        "cells": [{"type": "choice", "rows": 2, "options": 3, "control": True}],
    }
    laid = layout_card2([row], 568, 400, align_top=True)
    assert laid["rows"][0][0][0] == 1
    five = {**row, "cells": [{**row["cells"][0], "options": 5}]}
    assert layout_card2([five], 568, 400, align_top=True)["rows"][0][0][0] == 2
    narrow = {**row, "cells": [{**row["cells"][0], "options": 7, "rows": 2}]}
    # Seven in one row would be 32 px each: the rows stay.
    assert layout_card2([narrow], 280, 400, align_top=True)["rows"][0][0][0] == 2


# ---------------------------------------------------------------- the cards


async def test_the_blind_bar_fills_as_it_opens(hass: HomeAssistant) -> None:
    """Blocker: "Open 60%" over a bar filled 40%; a drag to 80 opened it 20."""
    cover = COMPONENTS["apollo/cover"]
    facts = {"cover.b": facts_of(BLIND_RAW)}
    for variant in ("tile", "full"):
        result = _compile(cover, variant, {"entity": "cover.b"}, {}, facts)
        _inside(result, variant)
        [bar] = [w for w in result["widgets"] if w["t"] == "slider"]
        assert bar.get("dir", 0) == 0
        hass.states.async_set("cover.b", "open", {"current_position": 60})
        assert await _value(hass, result, bar["value"]) == 60
        action = result["actions"][f"{bar['i']}:change"]
        assert "100 - value" not in str(action)
    tall = _compile(cover, "tall", {"entity": "cover.b"}, {}, facts)
    [shade] = [w for w in tall["widgets"] if w["t"] == "slider"]
    assert shade["dir"] == 2 and shade["r"][3] > 150


def test_the_cards_fill_their_default_size() -> None:
    """Decision 5: no band over 56 px between the header and the controls."""
    cases = {
        ("apollo/appliance", "large"): {
            "state": "sensor.w",
            "remaining": "sensor.left",
            "progress": "sensor.done",
            "start_button": "button.go",
        },
        ("apollo/fan-speed", "large"): {"entity": "fan.a"},
        ("apollo/alarm", "large"): {"entity": "alarm_control_panel.a"},
        ("apollo/forecast", "large"): {"entity": "weather.a"},
        ("apollo/light-group", "large"): {"lights": ["light.a", "light.b"]},
        ("apollo/reading", "wide"): {"entity": "sensor.a"},
    }
    facts = {
        "fan.a": facts_of(FAN_RAW),
        "alarm_control_panel.a": facts_of(ALARM_RAW),
    }
    for (component_id, variant), params in cases.items():
        result = _compile(COMPONENTS[component_id], variant, params, {}, facts)
        _inside(result, component_id)
        header = result["header"]
        reached = 16 if header is None else header["r"][1] + header["r"][3]
        band = 0
        for widget in sorted(result["widgets"], key=lambda w: w["r"][1]):
            band = max(band, widget["r"][1] - reached)
            reached = max(reached, widget["r"][1] + widget["r"][3])
        assert band <= 56, (component_id, band)


async def test_the_lock_shows_no_button_while_it_is_gone(hass: HomeAssistant) -> None:
    """Major: an unavailable lock showed a closed padlock and a Lock button."""
    lock = COMPONENTS["apollo/door-lock"]
    result = _compile(lock, "wide", {"entity": "lock.a"}, {}, {})
    buttons = [w for w in result["widgets"] if w["t"] == "button"]
    hass.states.async_set("lock.a", "unavailable")
    assert [await _value(hass, result, b["vis"]) for b in buttons] == [False, False]
    hass.states.async_set("lock.a", "unlocked")
    assert [await _value(hass, result, b["vis"]) for b in buttons] == [False, True]
    tall = _compile(lock, "tall", {"entity": "lock.a"}, {}, {})
    # LOOK-NOTES decision 14: Lock Tall has the tile header; the large
    # badge sits under it.
    badge = max(
        (w for w in tall["widgets"] if w["t"] == "image"), key=lambda w: w["r"][3]
    )
    assert badge["r"][1] >= 16 + 48 + 8


async def test_media_shows_what_is_playing(hass: HomeAssistant) -> None:
    """Major: no size showed the track's title."""
    media = COMPONENTS["apollo/media"]
    hass.states.async_set(
        "media_player.a",
        "playing",
        {"media_title": "Harvest Moon", "media_artist": "Neil Young"},
    )
    wide = _compile(media, "wide", {"entity": "media_player.a"}, {}, {})
    assert await _value(hass, wide, _texts(wide)[1]) == "Harvest Moon · Neil Young"
    large = _compile(media, "large", {"entity": "media_player.a"}, {}, {})
    texts = [await _value(hass, large, t) for t in _texts(large)]
    assert texts[1:3] == ["Neil Young", "Harvest Moon"]
    hass.states.async_set("media_player.a", "off")
    assert await _value(hass, wide, _texts(wide)[1]) == "off"


async def test_volume_and_status_say_when_the_device_is_gone(
    hass: HomeAssistant,
) -> None:
    """Major: Volume read "0%" for a speaker that was gone; minor: one no-value look."""
    volume = _compile(
        COMPONENTS["apollo/volume"], "row", {"entity": "media_player.a"}, {}, {}
    )
    hass.states.async_set("media_player.a", "unavailable")
    assert await _value(hass, volume, _texts(volume)[1]) == "unavailable"
    [bar] = [w for w in volume["widgets"] if w["t"] == "slider"]
    assert bar["r"][3] == 48
    status = _compile(
        COMPONENTS["apollo/reading"], "wide", {"entity": "sensor.a"}, {}, {}
    )
    hass.states.async_set("sensor.a", "unavailable")
    texts = [await _value(hass, status, t) for t in _texts(status)]
    assert texts[1:] == ["unavailable", "—", "—"]
    hass.states.async_set("sensor.a", "21.4", {"unit_of_measurement": "°C"})
    texts = [await _value(hass, status, t) for t in _texts(status)]
    assert texts[1:] == ["", "21.4 °C", "21.4 °C"]


async def test_the_owners_lamp_says_its_brightness_and_white(
    hass: HomeAssistant,
) -> None:
    """Major: no readout of brightness or kelvin; a marker on both bars at once."""
    light = COMPONENTS["apollo/light"]
    facts = {"light.h1401": facts_of(OWNER_LAMP_RAW)}
    result = _compile(light, "full", {"entity": "light.h1401"}, {}, facts)
    hass.states.async_set(
        "light.h1401",
        "on",
        {
            "color_mode": "color_temp",
            "brightness": 140,
            "color_temp_kelvin": 3010,
            "hs_color": [27.8, 56.9],
        },
    )
    assert await _value(hass, result, _texts(result)[1]) == "on · 55% · 3000 K"
    hue = next(w for w in result["widgets"] if w.get("track") and w.get("max") == 360)
    assert await _value(hass, result, hue["value"]) is None
    hass.states.async_set(
        "light.h1401",
        "on",
        {"color_mode": "hs", "brightness": 255, "hs_color": [120, 80]},
    )
    assert await _value(hass, result, _texts(result)[1]) == "on · 100%"
    assert await _value(hass, result, hue["value"]) == 120


async def test_the_smaller_findings_hold(hass: HomeAssistant) -> None:
    """Minors and majors that each come down to one line of a card file."""
    # Weather: a day with no forecast shows no icon, not a broken one.
    weather = _compile(
        COMPONENTS["apollo/forecast"], "large", {"entity": "weather.a"}, {}, {}
    )
    # (The icon comes from a forecast call, so only the binding is checked.)
    days = [w for w in weather["widgets"] if w["t"] == "image" and w["r"][3] == 32]
    assert len(days) == 5 and all("vis" in w for w in days)
    # Fan: a tall speed bar, and words a person says.
    fan = _compile(
        COMPONENTS["apollo/fan-speed"],
        "large",
        {"entity": "fan.a"},
        {},
        {"fan.a": facts_of(FAN_RAW)},
    )
    [speed] = [w for w in fan["widgets"] if w["t"] == "slider"]
    assert speed["r"][3] == 96
    assert "Side to side" in [
        w.get("text") for w in fan["widgets"] if w["t"] == "button"
    ]
    # Alarm Large: the device in a tile header, the buttons 64 high.
    alarm = _compile(
        COMPONENTS["apollo/alarm"],
        "large",
        {"entity": "alarm_control_panel.a"},
        {},
        {"alarm_control_panel.a": facts_of(ALARM_RAW)},
    )
    assert alarm["header"] is None and alarm["widgets"][0]["r"][:2] == [16, 18]
    assert {w["r"][3] for w in alarm["widgets"] if w["t"] == "button"} == {64}
    # Row cards: bars a finger can hold (48, not 40).
    for component_id, entity in (
        ("apollo/number", "number.a"),
        ("apollo/screen", "light.a"),
    ):
        row = _compile(COMPONENTS[component_id], "row", {"entity": entity}, {}, {})
        assert [w["r"][3] for w in row["widgets"] if w["t"] == "slider"] == [48]
    # Lights together Tile: the bar takes the room under the header.
    group = _compile(
        COMPONENTS["apollo/light-group"],
        "tile",
        {"lights": ["light.a", "light.b"]},
        {},
        {},
    )
    [bar] = [w for w in group["widgets"] if w["t"] == "slider"]
    assert bar["r"][3] >= 56
