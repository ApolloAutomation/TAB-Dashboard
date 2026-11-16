"""The look of the cards after package L5 (LOOK-NOTES decisions 15 to 17).

Each test holds one change: upright bars take the free height (all that is
kept of decision 15), the Thermostat Tile's target is never cut, and the
minors of decision 17.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.apollo_tab.maker.compile2 import (
    _Compiler2,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.geometry import PAD, layout_card2
from custom_components.apollo_tab.maker.names import (
    NAME_W_SPARE,
    NUMBER_W,
    widest_number,
)
from custom_components.apollo_tab.maker.schema import validate_component
from tests.test_cards_look_l3 import OWNERS_LAMP_RAW, _compile_at
from tests.test_cards_step_a import (
    COMPONENTS,
    ONOFF_LAMP_RAW,
    _label,
    _value,
)
from tests.test_cards_step_b import _bindings, _run

CLIMATE_FILE = (
    Path(__file__).parent.parent
    / "custom_components/apollo_tab/library/components/apollo-climate.yaml"
)
OWNER = {"light.a": facts_of(OWNERS_LAMP_RAW)}
ONOFF = {"light.a": facts_of(ONOFF_LAMP_RAW)}
LAMP = {"entity": "light.a"}


def _kinds(result: dict) -> list[str]:
    return [w["t"] for w in result["widgets"]]


# ---------------------------------------------------------------- decision 15


def test_an_upright_bar_takes_the_free_height() -> None:
    """Decision 15: a blind is never capped by its width when grown."""
    row = {
        "kind": "row",
        "cells": [
            {
                "type": "slider",
                "look": "bar",
                "control": True,
                "grow": True,
                "direction": "down",
            }
        ],
        "height": None,
    }
    laid = layout_card2([row], 184, 760, "tile", centre=True)
    [[bar]] = laid["rects"][0]
    assert bar[3] == 760 - 2 * PAD - 48 - 8
    across = {**row, "cells": [{**row["cells"][0], "direction": "right"}]}
    [[bar]] = layout_card2([across], 184, 760, "tile", centre=True)["rects"][0]
    assert bar[3] == bar[2]


BLIND = {
    "cover.a": facts_of(
        {
            "domain": "cover",
            "registry": {
                "device_class": "blind",
                "features": ["OPEN", "CLOSE", "SET_POSITION", "STOP"],
            },
        }
    )
}


def _blind_height(variant: str, columns: int, rows: int) -> tuple[str, int]:
    result = _compile_at(
        "apollo/cover", variant, columns, rows, {"entity": "cover.a"}, BLIND
    )
    bars = [w for w in result["widgets"] if w["t"] == "slider"]
    return result["variant"], max(b["r"][3] for b in bars)


def test_a_grown_window_blind_takes_the_card_height() -> None:
    """Critic major: Window and Tall at 6x12 drew a 152 by 152 blind.

    At 6x12 the blind is taller than at 6x9, and a grown Tall's blind is
    taller than wide too. Each keeps its own size.
    """
    own = _blind_height("window", 6, 9)
    grown = _blind_height("window", 6, 12)
    assert own[0] == grown[0] == "window"
    assert grown[1] > own[1] > 152
    tall = _blind_height("tall", 6, 12)
    assert tall[0] == "tall"
    assert tall[1] > 152


# ---------------------------------------------------------------- decision 16

TUB = {
    "domain": "climate",
    "registry": {
        "capabilities": {
            "hvac_modes": ["off", "heat"],
            "min_temp": 50,
            "max_temp": 110,
            "target_temp_step": 0.5,
        },
        "features": ["TARGET_TEMPERATURE"],
    },
}
ROOM = {
    **TUB,
    "registry": {
        **TUB["registry"],
        "capabilities": {
            **TUB["registry"]["capabilities"],
            "min_temp": 7,
            "max_temp": 30,
        },
    },
}


def _drawn(text: str) -> int:
    """Return how wide a target is drawn at 28 px, in pixels, rounded up."""
    return -(-sum(NUMBER_W[28][char] for char in text) // 10)


@pytest.mark.parametrize(("columns", "rows"), [(6, 3), (12, 3)])
async def test_a_three_digit_target_is_never_cut(
    hass: HomeAssistant, columns: int, rows: int
) -> None:
    """Decision 16: a hot tub's "104.5°" showed "104...." in a label of 74."""
    params = {"entity": "climate.a"}
    result = _compile_at(
        "apollo/climate", "tile", columns, rows, params, {"climate.a": facts_of(TUB)}
    )
    assert result["variant"] == "tile"
    target = next(w for w in result["widgets"] if w.get("px") == 28)
    hass.states.async_set(
        "climate.a", "heat", {"temperature": 104.5, "current_temperature": 101.5}
    )
    assert await _value(hass, result, target["text"]) == "104.5°"
    for text in ("104.5°", "100.5°", "110°"):
        assert target["r"][2] * 10 >= _drawn(text) * 10 + NAME_W_SPARE
    now = next(
        w
        for w in result["widgets"]
        if w.get("size") == "s" and w["r"][1] == target["r"][1]
    )
    assert now["r"][0] == target["r"][0] + target["r"][2] + 8


def test_a_target_of_two_digits_keeps_its_74() -> None:
    """A room thermostat's widest target fits 74: "Now 20.5" keeps its 70."""
    result = _compile_at(
        "apollo/climate", "tile", 6, 3, {"entity": "climate.a"},
        {"climate.a": facts_of(ROOM)},
    )  # fmt: skip
    target = next(w for w in result["widgets"] if w.get("px") == 28)
    assert target["r"][2] == 74


@pytest.mark.parametrize(
    ("low", "high", "step", "widest"),
    [
        (50, 110, 0.5, "100.5°"),
        (7, 30, 0.5, "20.5°"),
        (7, 35, 1, "20°"),
        (-30, 0, 0.5, "-20.5°"),
        (45, 95, 0.1, "80.4°"),
    ],
)
def test_the_widest_number_of_a_range(
    low: float, high: float, step: float, widest: str
) -> None:
    """Whole numbers have no decimals; others the decimals of their step."""
    expected = -(-(sum(NUMBER_W[28][c] for c in widest) + NAME_W_SPARE) // 10)
    assert widest_number(low, high, step, "°", 28) == expected


def test_a_size_without_a_width_table_measures_nothing() -> None:
    """Size xl draws digits of 48 px, for which there is no table."""
    assert widest_number(0, 100, 1, "", 48) == 0
    assert widest_number(10, 0, 1, "", 28) == 0


@pytest.mark.parametrize(
    ("fits", "code"),
    [
        ({"min": 0}, "missing_key"),
        ({"min": 0, "max": 9, "colour": "#FFFFFF"}, "unknown_key"),
        ({"min": 0, "max": 9, "unit": "degrees Celsius"}, "bad_value"),
        ("0 to 9", "bad_value"),
    ],
)
def test_a_label_fits_range_is_checked(fits: object, code: str) -> None:
    """`fits` is {min, max, step, unit}, unit a short text."""
    doc = yaml.safe_load(CLIMATE_FILE.read_text(encoding="utf-8"))
    target = doc["variants"]["tile"]["layout"][0]["items"][0]["items"][0]
    assert "fits" in target
    validate_component(doc)
    target["fits"] = fits
    with pytest.raises(MakerError) as err:
        validate_component(doc)
    assert err.value.code == code


# ---------------------------------------------------------------- decision 17

APPLIANCE = {
    "state": "sensor.state",
    "remaining": "sensor.left",
    "progress": "sensor.progress",
    "programme": "sensor.programme",
    "start_button": "button.start",
}


async def test_an_unavailable_appliance_says_it_once(hass: HomeAssistant) -> None:
    """Decision 17: Large said "unavailable" twice, over an empty band."""
    result = _compile_at("apollo/appliance", "large", 12, 5, APPLIANCE, {})
    left = next(w for w in result["widgets"] if w.get("px") == 48)
    programme = next(
        w
        for w in result["widgets"]
        if w.get("size") == "s" and w["r"][1] > left["r"][1]
    )
    for entity in APPLIANCE.values():
        hass.states.async_set(entity, "unavailable")
    assert await _value(hass, result, left["text"]) == "—"
    assert await _value(hass, result, programme["text"]) == ""
    hass.states.async_set("sensor.left", "38")
    hass.states.async_set("sensor.programme", "Cotton 40°")
    assert await _value(hass, result, left["text"]) == "38 min"
    assert await _value(hass, result, programme["text"]) == "Cotton 40°"


@pytest.mark.parametrize("facts", [{}, {"select.m": facts_of({"domain": "select"})}])
async def test_a_wide_dropdown_with_no_choices_says_its_state(
    hass: HomeAssistant, facts: dict
) -> None:
    """Decision 17: Wide's title has no state line; it said only "—"."""
    result = _compile_at("apollo/select", "wide", 12, 3, {"entity": "select.m"}, facts)
    assert "choice" not in _kinds(result)
    line = next(w for w in result["widgets"] if w.get("px") == 28)
    hass.states.async_set("select.m", "unavailable")
    assert await _value(hass, result, line["text"]) == "unavailable"
    texts = [w.get("text") for w in result["widgets"] if w["t"] == "label"]
    assert "—" not in texts


def test_choice_texts_are_cut_in_the_middle() -> None:
    """Decision 17: "Programme N" in a Wide read "Progra…" eight times.

    The Wide's two rows of four cells are too narrow for them. (L5 round
    2: in a Large twelve columns wide eight of them now take four rows of
    two and show whole, so the Wide shows the cut.)
    """
    names = [f"Programme {n}" for n in range(1, 17)]
    facts = {
        "select.m": facts_of(
            {"domain": "select", "registry": {"capabilities": {"options": names}}}
        )
    }
    result = _compile_at(
        "apollo/select", "wide", 12, 3, {"entity": "select.m"}, facts,
        {"shown": names[4:12]},
    )  # fmt: skip
    [choice] = [w for w in result["widgets"] if w["t"] == "choice"]
    texts = choice["texts"]
    assert all("…" in text for text in texts)
    assert len(set(texts)) == len(texts)
    for text, name in zip(texts, names[4:12], strict=True):
        assert text.startswith("Pro") and text.endswith(name.split()[-1])
    large = _compile_at(
        "apollo/select", "large", 12, 6, {"entity": "select.m"}, facts,
        {"shown": names[4:12]},
    )  # fmt: skip
    [choice] = [w for w in large["widgets"] if w["t"] == "choice"]
    assert choice["texts"] == names[4:12]


async def test_the_owners_large_drops_the_white_before_cutting(
    hass: HomeAssistant,
) -> None:
    """Decision 17: at 6x12 "On · 68% · 2…" lost the white; it now reads "On · 68%"."""
    state = {
        "brightness": 173,
        "color_mode": "color_temp",
        "color_temp_kelvin": 2700,
    }
    narrow = _compile_at("apollo/light", "large", 6, 12, LAMP, OWNER)
    wide = _compile_at("apollo/light", "large", 12, 6, LAMP, OWNER)
    hass.states.async_set("light.a", "on", state)
    shown = await _value(hass, narrow, _label(narrow, "s")["text"])
    whole = await _value(hass, wide, _label(wide, "s")["text"])
    assert whole.endswith(" · 68% · 2700 K")
    assert shown == whole.removesuffix(" · 2700 K")


def test_a_state_line_with_no_parts_is_bound_as_before() -> None:
    """A state line that joins no " · " parts (a blind's) keeps its own slot."""
    result = _compile_at("apollo/cover", "tall", 6, 6, {"entity": "cover.a"}, BLIND)
    state = _label(result, "s")
    [slot] = [s for s in result["slots"] if s["n"] == state["text"]["s"]]
    assert "name_w" not in slot["variables"]


async def test_a_number_on_a_tenth_step_lands_on_its_grid(hass: HomeAssistant) -> None:
    """Tester minor: 0.1 is not exact in binary; minus and plus still land on it."""
    entity = "number.a"
    raw = {
        "domain": "number",
        "registry": {"capabilities": {"min": 0, "max": 1, "step": 0.1}},
    }
    calls = async_mock_service(hass, "number", "set_value")
    buttons = _bindings(
        "apollo/number", {"entity": entity}, {entity: facts_of(raw)},
        variant="wide", options={"control": "buttons"},
    )  # fmt: skip
    hass.states.async_set(entity, "0.3")
    await _run(hass, buttons["down"])
    assert calls[-1].data["value"] == 0.2
    await _run(hass, buttons["up"])
    assert calls[-1].data["value"] == 0.4


# ---------------------------------------------------------------- splice locks


def _compiler() -> _Compiler2:
    component = COMPONENTS["apollo/light"]
    card = validate_card_config2(component, {"params": LAMP})
    return _Compiler2(component, card, OWNER, 2, None, False)


@pytest.mark.parametrize(
    "template",
    [
        # Inner text with "}}": the marks lock refuses it.
        "{{ {'a': {'b': 1}} }}",
        # One expression that is not a template: the second check refuses it.
        "{{ 1 + }}",
    ],
)
def test_a_value_beside_a_name_is_spliced_only_when_safe(template: str) -> None:
    """Tester minor: each lock of _beside on its own."""
    mark = {"form": "template", "template": template}
    assert _compiler()._beside(mark, 14, 8, 88) is None
    plain = {"form": "template", "template": "{{ 21.5 }}"}
    assert _compiler()._beside(plain, 14, 8, 88) is not None


@pytest.mark.parametrize(
    "text",
    [
        "{{ '}}' if c else state_attr(entity, 'friendly_name') or entity }}",
        "{{ 1 + if c else state_attr(entity, 'friendly_name') or entity }}",
        "{{ 'x' if c } else state_attr(entity, 'friendly_name') or entity }}",
    ],
)
def test_a_guarded_name_is_spliced_only_when_safe(text: str) -> None:
    """Tester minor: each lock of the _title guard on its own."""
    item = {"text": {"form": "template", "template": text}}
    assert _compiler()._name_guard(item) is None
    plain = "{{ 'More' if c else state_attr(entity, 'friendly_name') or entity }}"
    assert _compiler()._name_guard({"text": {"form": "template", "template": plain}})
