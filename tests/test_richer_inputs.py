"""Richer inputs (cards spec C.2.8; package I11).

The `statistics` source, read actions whose result names a loop entry (one
value per copy, one call for all of them), and history, statistics and
read-action inputs that feed a template (a label, an image, a number field)
as well as a field. The values a template gets are data, never template
source.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.apollo_tab import live
from custom_components.apollo_tab.live import (
    STATISTICS_MIN_AGE_S,
    STATISTICS_REFRESH_SECONDS,
    SlotTracker,
    async_evaluate_slot,
    async_fetch_action,
    async_fetch_statistics,
    async_input_value,
    hour_buckets,
    shared_fetches,
)
from custom_components.apollo_tab.maker.compile2 import (
    compile_card2,
    validate_card_config2,
)
from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.schema import validate_component

# ---------------------------------------------------------------- helpers


def _card_file(**overrides: Any) -> dict:
    """Return a small schema 2 card file with overrides applied."""
    doc: dict = {
        "schema": 2,
        "id": "test/inputs",
        "version": "1.0.0",
        "name": "Inputs",
        "icon": "mdi:information-outline",
        "params": {"entity": {"domain": "sensor"}},
        "inputs": {
            "low": {
                "source": "statistics",
                "entity": "{{ entity }}",
                "stat": "min",
                "hours": 24,
            },
            "high": {
                "source": "statistics",
                "entity": "{{ entity }}",
                "stat": "max",
                "hours": 24,
            },
            "range": "{{ low }} to {{ high }}",
        },
        "layout": [{"type": "label", "text": "{{ range }}"}],
        "size": "2x1",
    }
    doc.update(overrides)
    return doc


def _compile(doc: dict, params: dict | None = None, dl: int = 2) -> dict:
    """Load a card file and compile its first variant for a device."""
    component = validate_component(copy.deepcopy(doc))
    raw: dict = {"params": params if params is not None else {"entity": "sensor.t"}}
    card = validate_card_config2(component, raw)
    return compile_card2(component, card, {}, dl)


def _slot(result: dict, ref: Any) -> dict:
    """Return the slot a field refers to."""
    assert isinstance(ref, dict) and "s" in ref, ref
    [slot] = [s for s in result["slots"] if s["n"] == ref["s"]]
    return slot


def _refused(doc: dict, code: str) -> MakerError:
    """Assert that a card file is refused with a code."""
    with pytest.raises(MakerError) as excinfo:
        validate_component(copy.deepcopy(doc))
    assert excinfo.value.code == code, excinfo.value
    return excinfo.value


FORECAST = [
    {
        "datetime": f"2026-11-{14 + n}T12:00:00+00:00",
        "condition": condition,
        "temperature": 10 + n,
        "templow": 2 + n,
    }
    for n, condition in enumerate(["sunny", "rainy", "partlycloudy", "snowy"])
]


def _forecast_service(hass: HomeAssistant, forecast: list | None = None) -> list:
    """Register weather.get_forecasts; return the list of its calls."""
    calls: list[ServiceCall] = []

    @callback
    def handle(call: ServiceCall) -> dict:
        """Answer every entity with the forecast."""
        calls.append(call)
        entities = call.data["entity_id"]
        if isinstance(entities, str):
            entities = [entities]
        return {
            entity: {"forecast": FORECAST if forecast is None else forecast}
            for entity in entities
        }

    hass.services.async_register(
        "weather",
        "get_forecasts",
        handle,
        supports_response=SupportsResponse.ONLY,
    )
    return calls


class _Statistics:
    """Stand in for the recorder's two statistics functions."""

    def __init__(self) -> None:
        """Start with no rows."""
        self.single: dict[str, float | None] = {}
        self.rows: list[dict] = []
        self.current: dict[str, float | None] = {}
        self.calls: list[tuple] = []

    def statistic_during_period(
        self, hass, start, end, statistic_id, types, units
    ) -> dict:
        """Return one value per type."""
        self.calls.append(("one", start, end, statistic_id, set(types)))
        # A test sets the running hour or the one value, not both.
        source = self.current or self.single
        return {kind: source.get(kind) for kind in types if kind in source}

    def statistics_during_period(
        self, hass, start, end, ids, period, units, types
    ) -> dict:
        """Return the hourly rows."""
        self.calls.append(("rows", start, end, set(ids), period, set(types)))
        entity = next(iter(ids))
        return {entity: list(self.rows)} if self.rows else {}


@pytest.fixture
def stats(hass: HomeAssistant) -> _Statistics:
    """Give the live module a recorder whose statistics this test writes."""
    fake = _Statistics()
    hass.config.components.add("recorder")

    class _Instance:
        async def async_add_executor_job(self, func, *args):
            return func(*args)

    with (
        patch.object(live, "get_instance", return_value=_Instance()),
        patch.object(
            live.statistics, "statistic_during_period", fake.statistic_during_period
        ),
        patch.object(
            live.statistics, "statistics_during_period", fake.statistics_during_period
        ),
    ):
        yield fake


# ---------------------------------------------------------------- loader


def test_a_read_action_may_name_a_loop_over_devices_of_its_domain() -> None:
    """Its entity is a loop entry; each copy reads its own device (C.2.8)."""
    doc = _card_file(
        params={"places": {"domain": "weather", "multiple": True, "max": 4}},
        inputs={
            "high": {
                "action": "weather.get_forecasts",
                "data": {"entity_id": "{{ place }}", "type": "daily"},
                "result": "{{ response[place].forecast[0].temperature }}",
            }
        },
        layout=[
            {
                "type": "label",
                "text": "{{ high }}",
                "for_each": "places",
                "as": "place",
            }
        ],
    )
    component = validate_component(copy.deepcopy(doc))
    assert component["inputs"]["high"]["param"] == "place"
    card = validate_card_config2(
        component, {"params": {"places": ["weather.home", "weather.cabin"]}}
    )
    result = compile_card2(component, card, {}, 2)
    feeds = [_slot(result, w["text"])["inputs"]["high"] for w in result["widgets"]]
    assert [feed["data"]["entity_id"] for feed in feeds] == [
        "weather.home",
        "weather.cabin",
    ]


def test_a_read_action_over_a_loop_of_other_devices_is_refused() -> None:
    """Every device the loop can give must be of the action's domain."""
    doc = _card_file(
        params={"places": {"domain": ["weather", "sensor"], "multiple": True}},
        inputs={
            "high": {
                "action": "weather.get_forecasts",
                "data": {"entity_id": "{{ place }}", "type": "daily"},
                "result": "{{ 1 }}",
            }
        },
        layout=[
            {"type": "label", "text": "{{ high }}", "for_each": "places", "as": "place"}
        ],
    )
    _refused(doc, "domain_mismatch")


def test_a_read_action_naming_neither_a_param_nor_a_loop_is_refused() -> None:
    """A name that no loop gives is no device."""
    doc = _card_file(
        params={"entity": {"domain": "weather"}},
        inputs={
            "high": {
                "action": "weather.get_forecasts",
                "data": {"entity_id": "{{ nowhere }}", "type": "daily"},
                "result": "{{ 1 }}",
            }
        },
        layout=[{"type": "label", "text": "{{ high }}"}],
    )
    _refused(doc, "unknown_param")


def test_a_history_input_may_name_a_loop_over_devices() -> None:
    """One history per device of the loop."""
    doc = _card_file(
        params={"sensors": {"domain": "sensor", "multiple": True}},
        inputs={"past": {"source": "recorder", "entity": "{{ s }}", "hours": 6}},
        layout=[{"type": "chart", "value": "past", "for_each": "sensors", "as": "s"}],
    )
    component = validate_component(copy.deepcopy(doc))
    card = validate_card_config2(
        component, {"params": {"sensors": ["sensor.a", "sensor.b"]}}
    )
    result = compile_card2(component, card, {}, 2)
    entities = [_slot(result, w["value"])["entity"] for w in result["widgets"]]
    assert entities == ["sensor.a", "sensor.b"]


def test_a_list_input_still_feeds_only_a_chart_value() -> None:
    """A history or an hourly statistics list is not a number field."""
    doc = _card_file(
        inputs={
            "hours": {
                "source": "statistics",
                "entity": "{{ entity }}",
                "buckets": "hour",
                "stat": "mean",
            }
        },
        layout=[{"type": "slider", "value": "hours"}],
    )
    _refused(doc, "bad_value")


# ---------------------------------------------------------------- compile


def test_a_template_that_names_statistics_carries_their_slots() -> None:
    """The label's template names `range`, which names two statistics."""
    result = _compile(_card_file())
    [label] = result["widgets"]
    slot = _slot(result, label["text"])
    assert slot["kind"] == "template"
    assert slot["inputs"] == {
        "low": {"kind": "statistics", "entity": "sensor.t", "stat": "min", "hours": 24},
        "high": {
            "kind": "statistics",
            "entity": "sensor.t",
            "stat": "max",
            "hours": 24,
        },
    }
    # The inputs are variables at render time, never part of the source.
    assert "statistics" not in slot["template"]


def test_a_template_without_fetched_inputs_has_none() -> None:
    """Only history, statistics and action inputs are fed."""
    doc = _card_file(layout=[{"type": "label", "text": "{{ states(entity) }}"}])
    result = _compile(doc)
    assert "inputs" not in _slot(result, result["widgets"][0]["text"])


def test_an_example_card_shows_the_preview_values() -> None:
    """No device: the preview values are variables, nothing is fetched."""
    doc = _card_file(preview={"inputs": {"low": 3, "high": 9}})
    component = validate_component(copy.deepcopy(doc))
    card = validate_card_config2(component, {})
    result = compile_card2(component, card, {}, 2)
    slot = _slot(result, result["widgets"][0]["text"])
    assert "inputs" not in slot
    assert slot["variables"]["low"] == 3 and slot["variables"]["high"] == 9


def _per_day_doc(cells: list) -> dict:
    """Return a weather card whose read actions name the day `d`."""
    return _card_file(
        params={"entity": {"domain": "weather"}},
        inputs={
            "high": {
                "action": "weather.get_forecasts",
                "data": {"entity_id": "{{ entity }}", "type": "daily"},
                "result": "{{ response[entity].forecast[d].temperature }}",
            },
            "day_icon": {
                "action": "weather.get_forecasts",
                "data": {"entity_id": "{{ entity }}", "type": "daily"},
                "result": "mdi:weather-{{ response[entity].forecast[d].condition }}",
            },
        },
        layout=cells,
    )


def test_a_read_action_gives_one_slot_per_loop_copy() -> None:
    """The copies differ only in their loop entry; the call is the same."""
    doc = _per_day_doc(
        [
            {
                "type": "image",
                "value": "day_icon",
                "for_each": [0, 1, 2],
                "as": "d",
                "per_row": 3,
            }
        ]
    )
    result = _compile(doc, {"entity": "weather.home"})
    slots = [_slot(result, w["value"]) for w in result["widgets"]]
    assert [slot["variables"]["d"] for slot in slots] == [0, 1, 2]
    assert {slot["kind"] for slot in slots} == {"action"}
    assert {(slot["action"], str(slot["data"])) for slot in slots} == {
        ("weather.get_forecasts", str({"type": "daily", "entity_id": "weather.home"}))
    }


def test_a_read_action_gives_one_slot_per_item_vars() -> None:
    """`vars: {d: n}` on a cell gives the day as well."""
    doc = _per_day_doc(
        [
            {
                "type": "row",
                "items": [
                    {"type": "label", "text": "{{ high }}°", "vars": {"d": n}}
                    for n in range(3)
                ],
            }
        ]
    )
    result = _compile(doc, {"entity": "weather.home"})
    feeds = [_slot(result, w["text"])["inputs"]["high"] for w in result["widgets"]]
    assert [feed["variables"]["d"] for feed in feeds] == [0, 1, 2]


def test_a_read_action_without_its_device_is_no_slot() -> None:
    """An optional weather param left empty: no call with no entity."""
    doc = _per_day_doc([{"type": "image", "value": "day_icon", "vars": {"d": 0}}])
    doc["params"] = {
        "other": {"domain": "sensor"},
        "entity": {"domain": "weather", "optional": True},
    }
    result = _compile(doc, {"other": "sensor.t"})
    [image] = result["widgets"]
    assert image.get("value") is None
    assert not any(slot["kind"] == "action" for slot in result["slots"])


# ---------------------------------------------------------------- statistics


def test_hour_buckets_leave_out_the_hours_still_to_come(hass: HomeAssistant) -> None:
    """One number per local hour up to now; the running hour comes last."""
    midnight = dt_util.start_of_local_day(datetime(2026, 11, 14, 12))
    now = midnight + timedelta(hours=3, minutes=20)
    rows = [
        {"start": (midnight + timedelta(hours=h)).timestamp(), "mean": 10.0 + h}
        for h in range(3)
    ]
    assert hour_buckets(rows, 20.0, "mean", now) == [10.0, 11.0, 12.0, 20.0]
    assert hour_buckets(rows, None, "mean", now) == [10.0, 11.0, 12.0, 12.0]


def test_hour_buckets_fill_gaps(hass: HomeAssistant) -> None:
    """A change takes 0; a mean the hour before, and at the start the first."""
    midnight = dt_util.start_of_local_day(datetime(2026, 11, 14, 12))
    now = midnight + timedelta(hours=4, minutes=5)
    rows = [
        {
            "start": (midnight + timedelta(hours=1)).timestamp(),
            "mean": 5.0,
            "change": 2,
        },
        {
            "start": (midnight + timedelta(hours=3)).timestamp(),
            "mean": 7.0,
            "change": 1,
        },
    ]
    assert hour_buckets(rows, None, "mean", now) == [5.0, 5.0, 5.0, 7.0, 7.0]
    assert hour_buckets(rows, 0.5, "change", now) == [0.0, 2.0, 0.0, 1.0, 0.5]
    assert hour_buckets([], None, "mean", now) == []
    assert hour_buckets([], None, "change", now) == []


async def test_hour_buckets_join_an_hour_that_comes_twice(hass: HomeAssistant) -> None:
    """When the clocks go back, one local hour has two rows."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    # 2026-10-25: 02:00 to 03:00 local comes twice (00:00 and 01:00 UTC).
    first = dt_util.parse_datetime("2026-10-25T00:00:00+00:00")
    now = dt_util.parse_datetime("2026-10-25T02:30:00+00:00")
    rows = [
        {"start": first.timestamp(), "mean": 4.0, "change": 1.0},
        {"start": (first + timedelta(hours=1)).timestamp(), "mean": 6.0, "change": 2.0},
    ]
    means = hour_buckets(rows, None, "mean", now)
    changes = hour_buckets(rows, None, "change", now)
    assert len(means) == dt_util.as_local(now).hour + 1 == 4
    assert means[2] == 5.0
    assert changes[2] == 3.0


def test_hour_buckets_skip_values_that_are_no_numbers(hass: HomeAssistant) -> None:
    """None, yes or no, and an infinite value are no statistics."""
    midnight = dt_util.start_of_local_day(datetime(2026, 11, 14, 12))
    now = midnight + timedelta(hours=1, minutes=1)
    rows = [
        {"start": midnight.timestamp(), "mean": None},
        {"start": midnight.timestamp(), "mean": True},
        {"start": midnight.timestamp(), "mean": float("inf")},
        {"start": "noon", "mean": 3.0},
    ]
    assert hour_buckets(rows, None, "mean", now) == []


async def test_statistics_without_the_recorder(hass: HomeAssistant) -> None:
    """None for one number, an empty list for the hours."""
    one = {"kind": "statistics", "entity": "sensor.t", "stat": "max", "hours": 24}
    hours = {
        "kind": "statistics",
        "entity": "sensor.t",
        "buckets": "hour",
        "period": "today",
        "stat": "mean",
    }
    assert await async_fetch_statistics(hass, one) is None
    assert await async_fetch_statistics(hass, hours) == []
    assert await async_evaluate_slot(hass, hours) == []


async def test_one_statistic_over_the_hours(
    hass: HomeAssistant, stats: _Statistics, freezer: FrozenDateTimeFactory
) -> None:
    """min, max or mean over the last `hours`, from the recorder."""
    freezer.move_to("2026-11-14T10:20:00+00:00")
    stats.single = {"max": 52.25}
    slot = {"kind": "statistics", "entity": "sensor.t", "stat": "max", "hours": 6}
    assert await async_evaluate_slot(hass, slot) == 52.25
    [call] = stats.calls
    assert call[0] == "one" and call[3] == "sensor.t" and call[4] == {"max"}
    assert call[1] == dt_util.utcnow() - timedelta(hours=6)
    assert call[2] is None


async def test_a_statistic_that_is_no_number_gives_none(
    hass: HomeAssistant, stats: _Statistics
) -> None:
    """An entity without statistics has no value."""
    slot = {"kind": "statistics", "entity": "sensor.t", "stat": "min", "hours": 24}
    assert await async_evaluate_slot(hass, slot) is None
    stats.single = {"min": float("nan")}
    shared_fetches(hass).__init__()
    assert await async_evaluate_slot(hass, slot) is None


async def test_today_by_the_hour_reads_the_hours_and_the_running_hour(
    hass: HomeAssistant, stats: _Statistics, freezer: FrozenDateTimeFactory
) -> None:
    """Hourly rows from midnight, then the hour that runs now from 5 minutes."""
    await hass.config.async_set_time_zone("UTC")
    freezer.move_to("2026-11-14T02:40:00+00:00")
    midnight = dt_util.parse_datetime("2026-11-14T00:00:00+00:00")
    stats.rows = [
        {"start": midnight.timestamp(), "change": 1.5},
        {"start": (midnight + timedelta(hours=1)).timestamp(), "change": 2.0},
    ]
    stats.current = {"change": 0.25}
    slot = {
        "kind": "statistics",
        "entity": "sensor.energy",
        "buckets": "hour",
        "period": "today",
        "stat": "sum",
    }
    assert await async_evaluate_slot(hass, slot) == [1.5, 2.0, 0.25]
    rows_call = next(call for call in stats.calls if call[0] == "rows")
    assert rows_call[1] == midnight
    assert rows_call[2] == midnight + timedelta(hours=2)
    assert rows_call[4] == "hour" and rows_call[5] == {"change"}


async def test_statistics_are_read_again_no_sooner_than_every_300_s(
    hass: HomeAssistant, stats: _Statistics, freezer: FrozenDateTimeFactory
) -> None:
    """Every card and tablet together: one read per 300 s (C.2.8)."""
    stats.single = {"mean": 20.0}
    slot = {"kind": "statistics", "entity": "sensor.t", "stat": "mean", "hours": 24}
    other_reader = {**slot, "n": 7}
    assert await async_evaluate_slot(hass, slot) == 20.0
    stats.single = {"mean": 21.0}
    assert STATISTICS_MIN_AGE_S >= 300
    freezer.tick(299)
    assert await async_evaluate_slot(hass, other_reader) == 20.0
    assert len(stats.calls) == 1
    freezer.tick(1)
    assert await async_evaluate_slot(hass, slot) == 21.0
    assert len(stats.calls) == 2
    # Another number of hours is another read.
    await async_evaluate_slot(hass, {**slot, "hours": 6})
    assert len(stats.calls) == 3


async def test_a_failed_statistics_read_is_not_kept(
    hass: HomeAssistant, stats: _Statistics
) -> None:
    """The next reader tries again."""
    slot = {"kind": "statistics", "entity": "sensor.t", "stat": "mean", "hours": 24}
    with patch.object(
        live.statistics, "statistic_during_period", side_effect=RuntimeError("db")
    ):
        assert await async_evaluate_slot(hass, slot) is None
    stats.single = {"mean": 4.0}
    assert await async_evaluate_slot(hass, slot) == 4.0


async def test_the_tracker_delivers_statistics_and_reads_them_again(
    hass: HomeAssistant, stats: _Statistics, freezer: FrozenDateTimeFactory
) -> None:
    """A statistics slot gets its value at start and after its interval."""
    stats.single = {"max": 30.0}
    slot = {
        "n": 1,
        "kind": "statistics",
        "entity": "sensor.t",
        "stat": "max",
        "hours": 24,
    }
    got: list = []
    tracker = SlotTracker(
        hass,
        hass.data.setdefault("hub", _hub(hass)),
        [slot],
        lambda s, v: got.append(v),
    )
    await tracker.async_start()
    assert got == [30.0]
    stats.single = {"max": 31.0}
    await _later(hass, freezer, STATISTICS_REFRESH_SECONDS)
    assert got == [30.0, 31.0]
    tracker.async_stop()


async def _later(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Move the clock on and run the timers that are due by then.

    Interval timers run their jobs in the background.
    """
    freezer.tick(seconds)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done(wait_background_tasks=True)


def _hub(hass: HomeAssistant) -> live.SlotHub:
    """Return a slot hub without a library."""

    class _Library:
        def async_listen(self, _listener):
            return lambda: None

    return live.SlotHub(hass, _Library())


# ---------------------------------------------------------------- read actions


def _action_slot(d: int, entity: str = "weather.home", refresh: int = 1800) -> dict:
    """Return a read-action slot for day d."""
    return {
        "kind": "action",
        "action": "weather.get_forecasts",
        "data": {"type": "daily", "entity_id": entity},
        "result": "{{ response[entity].forecast[d].temperature }}",
        "variables": {"entity": entity, "d": d},
        "refresh": refresh,
    }


async def test_the_copies_of_a_loop_share_one_call(hass: HomeAssistant) -> None:
    """Same action and data: one call, each copy its own result."""
    calls = _forecast_service(hass)
    values = [await async_evaluate_slot(hass, _action_slot(d)) for d in range(3)]
    assert values == [10, 11, 12]
    assert len(calls) == 1


async def test_readers_at_the_same_moment_wait_for_one_call(
    hass: HomeAssistant,
) -> None:
    """Started together, they still make one call."""
    import asyncio

    calls = _forecast_service(hass)
    values = await asyncio.gather(
        *(async_fetch_action(hass, _action_slot(d)) for d in range(4))
    )
    assert values == [10, 11, 12, 13]
    assert len(calls) == 1


async def test_other_data_is_another_call(hass: HomeAssistant) -> None:
    """Another device is another call."""
    calls = _forecast_service(hass)
    await async_evaluate_slot(hass, _action_slot(0))
    await async_evaluate_slot(hass, _action_slot(0, "weather.cabin"))
    assert len(calls) == 2


async def test_a_kept_response_serves_half_the_refresh(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """So each slot's own timer still finds it due."""
    calls = _forecast_service(hass)
    await async_evaluate_slot(hass, _action_slot(0, refresh=600))
    freezer.tick(299)
    await async_evaluate_slot(hass, _action_slot(1, refresh=600))
    assert len(calls) == 1
    freezer.tick(1)
    await async_evaluate_slot(hass, _action_slot(1, refresh=600))
    assert len(calls) == 2


async def test_a_failed_call_is_not_kept(hass: HomeAssistant) -> None:
    """A slot whose call failed gives an empty list; the next one calls again."""
    assert await async_evaluate_slot(hass, _action_slot(0)) == []
    calls = _forecast_service(hass)
    assert await async_evaluate_slot(hass, _action_slot(0)) == 10
    assert len(calls) == 1


async def test_shared_values_are_capped(hass: HomeAssistant) -> None:
    """The oldest kept value goes first."""
    shared = shared_fetches(hass)

    async def _value() -> int:
        return 1

    for n in range(live.MAX_SHARED_FETCHES + 5):
        await shared.async_get(f"k{n}", 60, _value)
    assert len(shared) == live.MAX_SHARED_FETCHES


async def test_the_shared_values_go_with_the_hub(hass: HomeAssistant) -> None:
    """Stopping the hub drops them."""
    hub = _hub(hass)
    shared_fetches(hass)
    hub.async_stop()
    assert live._SHARED_FETCHES not in hass.data


# ---------------------------------------------------------------- fed templates


def _fed_slot() -> dict:
    """Return a template slot fed by two statistics and a read action."""
    return {
        "n": 1,
        "kind": "template",
        "template": "{{ low }} to {{ high }} · {{ first }}",
        "variables": {"entity": "sensor.t"},
        "inputs": {
            "low": {
                "kind": "statistics",
                "entity": "sensor.t",
                "stat": "min",
                "hours": 24,
            },
            "high": {
                "kind": "statistics",
                "entity": "sensor.t",
                "stat": "max",
                "hours": 24,
            },
            "first": _action_slot(0),
        },
    }


async def test_a_fed_template_renders_with_the_fetched_values(
    hass: HomeAssistant, stats: _Statistics
) -> None:
    """Evaluated once (preview, values, `uses`)."""
    _forecast_service(hass)
    stats.single = {"min": 41.0, "max": 52.0}
    assert await async_evaluate_slot(hass, _fed_slot()) == "41.0 to 52.0 · 10"
    assert await async_input_value(hass, None, _fed_slot()) == "41.0 to 52.0 · 10"


async def test_a_fetched_value_is_data_never_template_source(
    hass: HomeAssistant,
) -> None:
    """A forecast that holds template text reaches the label as that text."""
    forecast = [{"datetime": "x", "condition": "{{ 1/0 }}", "temperature": "{% for %}"}]
    _forecast_service(hass, forecast)
    slot = {
        "n": 1,
        "kind": "template",
        "template": "{{ first }}",
        "variables": {"entity": "weather.home"},
        "inputs": {"first": _action_slot(0)},
    }
    assert await async_evaluate_slot(hass, slot) == "{% for %}"


async def test_the_tracker_follows_a_fed_template(
    hass: HomeAssistant, stats: _Statistics, freezer: FrozenDateTimeFactory
) -> None:
    """The template is tracked again when a fetched value changes."""
    _forecast_service(hass)
    stats.single = {"min": 41.0, "max": 52.0}
    hub = _hub(hass)
    got: list = []
    tracker = SlotTracker(hass, hub, [_fed_slot()], lambda s, v: got.append(v))
    await tracker.async_start()
    assert got == ["41.0 to 52.0 · 10"]
    stats.single = {"min": 40.0, "max": 52.0}
    await _later(hass, freezer, STATISTICS_REFRESH_SECONDS)
    assert got[-1] == "40.0 to 52.0 · 10"
    assert len(hub) == 1
    tracker.async_stop()
    assert len(hub) == 0


async def test_a_fed_template_still_follows_states(
    hass: HomeAssistant, stats: _Statistics
) -> None:
    """The fetched values join the variables; the state stays tracked."""
    stats.single = {"max": 52.0}
    hass.states.async_set("sensor.t", "47")
    slot = {
        "n": 1,
        "kind": "template",
        "template": "{{ states(entity) }} of {{ high }}",
        "variables": {"entity": "sensor.t"},
        "inputs": {
            "high": {
                "kind": "statistics",
                "entity": "sensor.t",
                "stat": "max",
                "hours": 24,
            }
        },
    }
    got: list = []
    tracker = SlotTracker(hass, _hub(hass), [slot], lambda s, v: got.append(v))
    await tracker.async_start()
    hass.states.async_set("sensor.t", "48")
    await hass.async_block_till_done()
    assert got == ["47 of 52.0", "48 of 52.0"]
    tracker.async_stop()


async def test_a_failed_feed_gives_none(
    hass: HomeAssistant, stats: _Statistics
) -> None:
    """A fetch that raises leaves the input empty, the template still renders."""
    slot = {
        "n": 1,
        "kind": "template",
        "template": "{{ high is none }}",
        "variables": {},
        "inputs": {"high": {"kind": "history", "entity": "sensor.t", "hours": 24}},
    }
    with patch.object(
        live, "async_fetch_history", side_effect=live.HomeAssistantError("no")
    ):
        assert await async_evaluate_slot(hass, slot) is True
        got: list = []
        tracker = SlotTracker(hass, _hub(hass), [slot], lambda s, v: got.append(v))
        await tracker.async_start()
        assert got == [True]
        tracker.async_stop()


async def test_a_compiled_card_label_shows_the_statistics(
    hass: HomeAssistant, stats: _Statistics
) -> None:
    """From the card file to the label's text, as a tablet gets it."""
    stats.single = {"min": 41, "max": 52}
    result = _compile(_card_file())
    slot = _slot(result, result["widgets"][0]["text"])
    assert await async_evaluate_slot(hass, slot) == "41.0 to 52.0"
