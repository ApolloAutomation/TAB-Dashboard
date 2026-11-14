"""The graph and the weather card (cards spec D.2, C.9 "Every card"; package I11).

Both are built-in schema 2 files that need the richer inputs of C.2.8: the
graph reads the recorder's statistics, the weather card one call to
weather.get_forecasts for every day it shows.
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback

from custom_components.apollo_tab import live
from custom_components.apollo_tab.live import async_evaluate_slot
from custom_components.apollo_tab.maker import device
from custom_components.apollo_tab.maker.const import UPDATE_NOTE
from custom_components.apollo_tab.maker.schema import validate_component
from custom_components.apollo_tab.maker.schema2 import iter_items
from custom_components.apollo_tab.maker.templates import check_component_templates
from tests.test_cards_step_a import (
    COMPONENTS,
    ICON_LEVEL,
    ICONS,
    LEVEL1,
    LIBRARY,
    _all_on,
    _cards,
    _convert,
    _dashboard,
)
from tests.test_cards_step_b import _compile, _facts, _inside, _kinds

CARDS = {
    "apollo/graph": "apollo-graph.yaml",
    "apollo/forecast": "apollo-forecast.yaml",
}
DEVICES = {
    "apollo/graph": {"entity": "sensor.outside"},
    "apollo/forecast": {"entity": "weather.home"},
}


def _slot(result: dict, ref: Any) -> dict:
    """Return the slot a field refers to."""
    assert isinstance(ref, dict) and "s" in ref, ref
    [slot] = [s for s in result["slots"] if s["n"] == ref["s"]]
    return slot


async def _value(hass: HomeAssistant, result: dict, ref: Any) -> Any:
    """Work out one slot of a compiled card as Home Assistant would."""
    return await async_evaluate_slot(hass, _slot(result, ref))


# ---------------------------------------------------------------- the files


def test_the_two_files_are_built_in_and_load() -> None:
    """Each card loads, passes the template checks and is schema 2."""
    for component_id, file_name in CARDS.items():
        path = LIBRARY / "components" / file_name
        component = validate_component(yaml.safe_load(path.read_text("utf-8")))
        check_component_templates(component)
        assert component["id"] == component_id
        assert component["schema"] == 2
        assert component["version"] == "2.0.0"
        assert component["group"] == "sensors"
        assert COMPONENTS[component_id]["source"] == "builtin"


def test_they_replace_what_d5_says() -> None:
    """The graph takes the sensor graph's place, the weather card the weather's."""
    assert COMPONENTS["apollo/graph"]["replaces"] == ["apollo/sensor-graph"]
    assert COMPONENTS["apollo/forecast"]["replaces"] == ["apollo/weather"]


def test_the_options_of_d2() -> None:
    """The graph: kind, hours, range. The weather card: days, details."""
    graph = COMPONENTS["apollo/graph"]["options"]
    assert [c["value"] for c in graph["kind"]["choices"]] == [
        "line",
        "steps",
        "bars",
        "today",
    ]
    assert [c["value"] for c in graph["hours"]["choices"]] == ["6", "24", "72", "168"]
    assert graph["show_range"]["type"] == "toggle"
    forecast = COMPONENTS["apollo/forecast"]["options"]
    assert [c["value"] for c in forecast["days"]["choices"]] == ["3", "4", "5"]
    assert forecast["show_details"]["default"] is True
    assert COMPONENTS["apollo/graph"]["params"]["entity"]["domains"] == [
        "sensor",
        "number",
        "input_number",
    ]
    assert COMPONENTS["apollo/forecast"]["params"]["entity"]["domains"] == ["weather"]


def test_the_words_of_the_two_cards() -> None:
    """A name, a description and labels; each choice is labelled."""
    for component_id in CARDS:
        component = COMPONENTS[component_id]
        assert component["name"] and component["description"], component_id
        for name, spec in component["params"].items():
            assert spec.get("label"), (component_id, name)
        for name, option in component["options"].items():
            assert option["label"], (component_id, name)
            for choice in option.get("choices") or []:
                assert choice["label"], (component_id, name, choice)
        for variant in component["variants"].values():
            assert variant["name"]


def test_they_only_show() -> None:
    """Neither card calls anything or has a tap."""
    for component_id in CARDS:
        assert COMPONENTS[component_id]["outputs"] == {}
        assert COMPONENTS[component_id]["tap"] is None


@pytest.mark.parametrize("component_id", list(CARDS))
def test_every_icon_a_card_names_is_in_the_contracts_set(component_id: str) -> None:
    """The file's icon is of level 1; every icon in its text is in the set."""
    component = COMPONENTS[component_id]
    assert ICON_LEVEL[component["icon"]] == 1
    for _path, item in iter_items(component):
        for key in ("icon", "value"):
            mark = item.get(key)
            if isinstance(mark, dict) and mark.get("form") == "const":
                value = mark["value"]
                if isinstance(value, str) and value.startswith("mdi:"):
                    assert value in ICON_LEVEL, (component_id, value)
    text = (LIBRARY / "components" / CARDS[component_id]).read_text("utf-8")
    # "mdi:weather-" is the start of a name the day icon table finishes.
    for name in re.findall(r"mdi:[a-z0-9-]+", text):
        if name != "mdi:weather-":
            assert name in ICON_LEVEL, (component_id, name)


def test_every_weather_condition_has_an_icon_of_level_1() -> None:
    """The day icons are live, and a tablet with older software holds level 1."""
    text = (LIBRARY / "components" / "apollo-forecast.yaml").read_text("utf-8")
    table = re.search(r"\{% set icons = (\{.*?\}) %\}", text)
    assert table is not None
    names = re.findall(r"'([a-z-]+)': '([a-z-]+)'", table.group(1))
    conditions = {condition for condition, _ in names}
    assert conditions == {
        "clear-night",
        "cloudy",
        "exceptional",
        "fog",
        "hail",
        "lightning",
        "lightning-rainy",
        "partlycloudy",
        "pouring",
        "rainy",
        "snowy",
        "snowy-rainy",
        "sunny",
        "windy",
        "windy-variant",
    }
    for _, icon in names:
        assert ICON_LEVEL[f"mdi:weather-{icon}"] == 1
    assert ICON_LEVEL["mdi:weather-cloudy"] == 1


def _fit_cases() -> list[tuple[str, str, bool]]:
    """List (card, variant, can do everything) to lay out."""
    return [
        (component_id, name, everything)
        for component_id in CARDS
        for name in COMPONENTS[component_id]["variants"]
        for everything in (True, False)
    ]


@pytest.mark.parametrize(("component_id", "variant", "everything"), _fit_cases())
def test_every_variant_fits_its_grid_with_every_option_on(
    component_id: str, variant: str, everything: bool
) -> None:
    """Nothing clipped, for each kind, each number of hours and of days."""
    component = COMPONENTS[component_id]
    params = DEVICES[component_id]
    entity = params["entity"]
    facts = {entity: _facts(entity.split(".", 1)[0], everything)}
    for options in _all_on(component, facts[entity]):
        for hours in ("6", "24", "72", "168"):
            if component_id == "apollo/graph":
                options = {**options, "hours": hours}
            for dl in (2, 1):
                result = _compile(component, variant, params, options, facts, dl)
                _inside(result, f"{component_id} {variant} {options} dl {dl}")


def test_the_example_cards_need_no_device() -> None:
    """Each card compiles as an example, with nothing clipped and no slot."""
    import copy

    from custom_components.apollo_tab.maker.compile2 import (
        compile_card2,
        validate_card_config2,
    )

    for component_id in CARDS:
        component = COMPONENTS[component_id]
        for name, variant in component["variants"].items():
            columns, rows = variant["grid"]
            raw = {"variant": name, "grid_options": {"columns": columns, "rows": rows}}
            card = validate_card_config2(component, copy.deepcopy(raw))
            result = compile_card2(component, card, {}, 2, detail=not variant["picker"])
            _inside(result, f"{component_id} {name}")
            assert not any("inputs" in slot for slot in result["slots"])


# ---------------------------------------------------------------- the graph


def _graph(options: dict, variant: str = "large", entity: str = "sensor.outside"):
    """Compile the graph for a sensor."""
    return _compile(
        COMPONENTS["apollo/graph"], variant, {"entity": entity}, options, {}
    )


def _chart(result: dict) -> dict:
    """Return the one chart of a card."""
    [chart] = [w for w in result["widgets"] if w["t"] == "chart"]
    return chart


@pytest.mark.parametrize("hours", [6, 24, 72, 168])
@pytest.mark.parametrize(("kind", "drawn"), [("line", {}), ("steps", {"st": 1})])
def test_the_graph_draws_its_hours_as_a_line_or_steps(
    hours: int, kind: str, drawn: dict
) -> None:
    """The recorder's history over the hours picked."""
    result = _graph({"kind": kind, "hours": str(hours)})
    chart = _chart(result)
    assert chart["kind"] == "line"
    assert {k: chart[k] for k in ("st",) if k in chart} == drawn
    assert _slot(result, chart["value"]) == {
        "n": chart["value"]["s"],
        "kind": "history",
        "entity": "sensor.outside",
        "hours": hours,
    }
    assert "mark" not in chart


def test_the_graph_draws_bars_over_hours() -> None:
    """Bars of the history."""
    result = _graph({"kind": "bars", "hours": "72"})
    chart = _chart(result)
    assert chart["kind"] == "bars"
    assert _slot(result, chart["value"])["hours"] == 72


async def test_today_by_the_hour_marks_the_hour_that_runs_now(
    hass: HomeAssistant,
) -> None:
    """Bars of today's hourly means, with a mark on the hour of now."""
    result = _graph({"kind": "today"})
    chart = _chart(result)
    assert chart["kind"] == "bars"
    assert _slot(result, chart["value"]) == {
        "n": chart["value"]["s"],
        "kind": "statistics",
        "entity": "sensor.outside",
        "buckets": "hour",
        "period": "today",
        "stat": "mean",
    }
    from homeassistant.util import dt as dt_util

    assert await _value(hass, result, chart["mark"]) == dt_util.now().hour


async def test_the_graph_shows_its_reading_and_the_range_of_its_hours(
    hass: HomeAssistant,
) -> None:
    """The range is the lowest and highest of the recorder's statistics."""
    hass.states.async_set("sensor.outside", "47.5", {"unit_of_measurement": "W"})
    for variant in ("wide", "large"):
        result = _graph({"hours": "6"}, variant)
        labels = [w for w in result["widgets"] if w["t"] == "label"]
        reading, shown = labels[0], labels[-1]
        assert await _value(hass, result, reading["text"]) == "47.5 W"
        slot = _slot(result, shown["text"])
        assert slot["inputs"] == {
            "lo6": {
                "kind": "statistics",
                "entity": "sensor.outside",
                "stat": "min",
                "hours": 6,
            },
            "hi6": {
                "kind": "statistics",
                "entity": "sensor.outside",
                "stat": "max",
                "hours": 6,
            },
        }
        with patch.object(live, "async_feed_values", _range_feeds):
            assert await _value(hass, result, shown["text"]) == "41.0 to 52.0 W"
        # Without statistics (a number, say): no range.
        with patch.object(live, "async_feed_values", _none_feeds):
            assert await _value(hass, result, shown["text"]) == ""


async def _range_feeds(_hass: HomeAssistant, feeds: dict) -> dict:
    """Return the lowest and highest of the last 6 hours."""
    values = {"lo6": 41.04, "hi6": 52.0}
    return {name: values[name] for name in feeds}


async def _none_feeds(_hass: HomeAssistant, feeds: dict) -> dict:
    """Every fetched input empty."""
    return dict.fromkeys(feeds)


async def test_today_shows_the_range_of_today(hass: HomeAssistant) -> None:
    """From the hourly means of today."""
    hass.states.async_set("sensor.outside", "20", {"unit_of_measurement": "°C"})
    result = _graph({"kind": "today"})
    shown = [w for w in result["widgets"] if w["t"] == "label"][-1]
    slot = _slot(result, shown["text"])
    assert set(slot["inputs"]) == {"today"}

    async def _fake(_hass: HomeAssistant, feeds: dict) -> dict:
        return {"today": [18.6, 21.44, 19.0]}

    with patch.object(live, "async_feed_values", _fake):
        assert await _value(hass, result, shown["text"]) == "18.6 to 21.4 °C"


def test_the_range_can_be_switched_off() -> None:
    """Without show_range the card has the reading and the chart."""
    for variant in ("wide", "large"):
        result = _graph({"show_range": False}, variant)
        assert _kinds(result) == ["label", "chart"], variant


def test_only_the_inputs_the_graph_shows_are_slots() -> None:
    """Four histories and ten statistics in the file; one chart's worth is read."""
    result = _graph({"kind": "line", "hours": "24"})
    kinds = [slot["kind"] for slot in result["slots"]]
    assert kinds.count("history") == 1
    assert "statistics" not in kinds
    fed = [slot for slot in result["slots"] if slot.get("inputs")]
    assert [sorted(slot["inputs"]) for slot in fed] == [["hi24", "lo24"]]


# ---------------------------------------------------------------- the weather card


def _forecast(options: dict, variant: str = "large") -> dict:
    """Compile the weather card for a weather entity."""
    return _compile(
        COMPONENTS["apollo/forecast"],
        variant,
        {"entity": "weather.home"},
        options,
        {},
    )


FORECAST = [
    {
        "datetime": f"2026-11-{16 + n}T12:00:00+00:00",
        "condition": condition,
        "temperature": 10.4 + n,
        "templow": 2.6 + n,
    }
    for n, condition in enumerate(["sunny", "rainy", "partlycloudy", "snowy", "foggy"])
]


def _forecast_service(hass: HomeAssistant, forecast: list) -> list:
    """Register weather.get_forecasts; return the list of its calls."""
    calls: list[ServiceCall] = []

    @callback
    def handle(call: ServiceCall) -> dict:
        calls.append(call)
        return {"weather.home": {"forecast": forecast}}

    hass.services.async_register(
        "weather", "get_forecasts", handle, supports_response=SupportsResponse.ONLY
    )
    return calls


def _rows(result: dict) -> list[list[dict]]:
    """Return the day rows: name, icon, high and low cells by their top."""
    by_top: dict[int, list[dict]] = {}
    for widget in result["widgets"]:
        by_top.setdefault(widget["r"][1], []).append(widget)
    return [cells for _top, cells in sorted(by_top.items()) if len(cells) >= 3]


@pytest.mark.parametrize("days", [3, 4, 5])
def test_the_weather_card_shows_the_days_picked(days: int) -> None:
    """Four rows of as many cells as days: names, icons, highs, lows."""
    result = _forecast({"days": str(days)})
    rows = _rows(result)
    assert [len(row) for row in rows] == [days] * 4
    assert [[cell["t"] for cell in row][0] for row in rows] == [
        "label",
        "image",
        "label",
        "label",
    ]


async def test_one_call_serves_every_day(hass: HomeAssistant) -> None:
    """The cells' read actions have the same action and data: one call."""
    calls = _forecast_service(hass, FORECAST)
    result = _forecast({"days": "5"})
    names, icons, highs, lows = _rows(result)
    assert [await _value(hass, result, c["text"]) for c in names] == [
        "Mon",
        "Tue",
        "Wed",
        "Thu",
        "Fri",
    ]
    assert [await _value(hass, result, c["value"]) for c in icons] == [
        "mdi:weather-sunny",
        "mdi:weather-rainy",
        "mdi:weather-partly-cloudy",
        "mdi:weather-snowy",
        # A condition the table does not know.
        "mdi:weather-cloudy",
    ]
    assert [await _value(hass, result, c["text"]) for c in highs] == [
        "10°",
        "11°",
        "12°",
        "13°",
        "14°",
    ]
    assert [await _value(hass, result, c["text"]) for c in lows] == [
        "3°",
        "4°",
        "5°",
        "6°",
        "7°",
    ]
    assert len(calls) == 1
    assert calls[0].data == {"entity_id": "weather.home", "type": "daily"}


async def test_a_short_forecast_leaves_the_last_days_empty(hass: HomeAssistant) -> None:
    """Days the forecast does not hold show nothing, not an error."""
    _forecast_service(hass, FORECAST[:2])
    result = _forecast({"days": "4"})
    names, icons, highs, lows = _rows(result)
    assert [await _value(hass, result, c["text"]) for c in names] == [
        "Mon",
        "Tue",
        "",
        "",
    ]
    assert [await _value(hass, result, c["value"]) for c in icons][2:] == [None, None]
    assert [await _value(hass, result, c["text"]) for c in highs][2:] == ["", ""]
    assert [await _value(hass, result, c["text"]) for c in lows][2:] == ["", ""]


async def test_a_forecast_value_is_data_never_template_source(
    hass: HomeAssistant,
) -> None:
    """A provider's text with template marks reaches the cell as that text."""
    _forecast_service(
        hass,
        [{"datetime": "{{ 1/0 }}", "condition": "{% for %}", "temperature": "{{ 7 }}"}],
    )
    result = _forecast({"days": "3"})
    names, icons, highs, _lows = _rows(result)
    assert await _value(hass, result, names[0]["text"]) == ""
    assert await _value(hass, result, icons[0]["value"]) == "mdi:weather-cloudy"
    assert await _value(hass, result, highs[0]["text"]) == ""


async def test_the_weather_now(hass: HomeAssistant) -> None:
    """The temperature, the condition in Home Assistant's words, the details."""
    hass.states.async_set(
        "weather.home",
        "partlycloudy",
        {
            "temperature": 12.4,
            "apparent_temperature": 9.6,
            "wind_speed": 14.2,
            "wind_speed_unit": "km/h",
        },
    )
    result = _forecast({})
    labels = [w for w in result["widgets"] if w["t"] == "label"]
    temp, condition, details = labels[0], labels[1], labels[2]
    assert temp["px"] == 48
    assert await _value(hass, result, temp["text"]) == "12°"
    assert await _value(hass, result, condition["text"]) == "partlycloudy"
    assert await _value(hass, result, details["text"]) == (
        "Feels like 10° · Wind 14 km/h"
    )
    icon = next(w for w in result["widgets"] if w["t"] == "image")
    assert _slot(result, icon["value"])["kind"] == "state_icon"
    hass.states.async_set("weather.home", "sunny", {"wind_speed": 3})
    assert await _value(hass, result, details["text"]) == "Wind 3"
    assert await _value(hass, result, temp["text"]) == ""


def test_the_details_can_be_switched_off() -> None:
    """Without show_details the line is not there."""
    with_details = _forecast({"show_details": True})
    without = _forecast({"show_details": False})
    assert len(without["widgets"]) == len(with_details["widgets"]) - 1


def test_the_wide_weather_card() -> None:
    """The icon at the side, the temperature at 48 px, the condition."""
    result = _forecast({}, "wide")
    assert _kinds(result) == ["image", "label", "label"]
    image = result["widgets"][0]
    assert image["look"] == 2
    assert result["widgets"][1]["px"] == 48


# ---------------------------------------------------------------- version 1 forms


def _v1(component_id: str, variant: str, params: dict, options: dict) -> dict:
    """Return the one card of a layout v1, checked for level 1 icons only."""
    columns, rows = COMPONENTS[component_id]["variants"][variant]["grid"]
    card = {
        "type": "custom:apollo-tab-card",
        "component": component_id,
        "params": params,
        "options": options,
        "variant": variant,
        "grid_options": {"columns": columns, "rows": rows},
    }
    result = _convert(_dashboard(card), {}, 1)
    assert result["layout"]["v"] == 1
    assert result["warnings"] == [], result["warnings"]
    [built] = _cards(result["layout"])
    assert UPDATE_NOTE not in [w.get("text") for w in built["w"]]
    for widget in built["w"]:
        for key in ("icon", "value"):
            value = widget.get(key)
            if isinstance(value, str) and value.startswith("mdi:"):
                assert value in LEVEL1, widget
    header_icon = (built.get("header") or {}).get("icon")
    assert header_icon is None or header_icon in LEVEL1
    compiled = device.compile_device_layout(result["layout"], ICONS)
    fallback = ICONS["icons"][ICONS["fallback"]][0]
    assert chr(fallback).encode() not in compiled["bytes"]
    return built


@pytest.mark.parametrize("variant", ["wide", "large"])
def test_an_old_tablet_gets_the_sensor_graph_for_a_sensor(variant: str) -> None:
    """C.6 rule 1: the old card, for a sensor."""
    built = _v1("apollo/graph", variant, {"entity": "sensor.outside"}, {})
    assert built["component"] == "apollo/sensor-graph"


@pytest.mark.parametrize("variant", ["wide", "large"])
@pytest.mark.parametrize("kind", ["line", "steps", "bars", "today"])
def test_an_old_tablet_gets_the_reading_and_a_line_for_a_number(
    variant: str, kind: str
) -> None:
    """The old card takes only sensors: its own form, the reading and a line."""
    built = _v1("apollo/graph", variant, {"entity": "number.limit"}, {"kind": kind})
    assert built["component"] == "apollo/graph"
    kinds = [w["t"] for w in built["w"]]
    assert kinds[0] == "label" and isinstance(built["w"][0]["text"], dict)
    [chart] = [w for w in built["w"] if w["t"] == "chart"]
    assert chart.get("kind", "line") == "line"
    assert "st" not in chart and "mark" not in chart


@pytest.mark.parametrize("variant", ["wide", "large"])
def test_an_old_tablet_gets_the_old_weather_card(variant: str) -> None:
    """C.6 rule 1: the old weather card fits both variants."""
    built = _v1("apollo/forecast", variant, {"entity": "weather.home"}, {})
    assert built["component"] == "apollo/weather"


def test_the_cards_fit_a_layout_v2_with_their_slots() -> None:
    """A dashboard with both cards converts for a new tablet without warnings."""
    cards = [
        {
            "type": "custom:apollo-tab-card",
            "component": component_id,
            "params": DEVICES[component_id],
            "variant": "large",
            "grid_options": {"columns": 12, "rows": 6},
        }
        for component_id in CARDS
    ]
    result = _convert(_dashboard(*cards), {}, 2)
    assert result["warnings"] == []
    built = _cards(result["layout"])
    assert [card["component"] for card in built] == list(CARDS)
    device.compile_device_layout(result["layout"], ICONS)
    kinds = {slot["kind"] for slot in result["bindings"]["slots"]}
    assert {"history", "action", "template", "state_icon"} <= kinds
