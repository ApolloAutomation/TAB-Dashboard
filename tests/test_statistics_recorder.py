"""The `statistics` source against Home Assistant's own recorder (C.2.8, I11).

The recorder must be set up before Home Assistant's test instance, so this
module asks for it in its own autouse fixture.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.apollo_tab.live import async_evaluate_slot


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Any, enable_custom_integrations: None
) -> None:
    """Start the recorder first, then let Home Assistant load the integration."""


def _metadata(entity: str, *, has_sum: bool) -> dict:
    """Return the metadata of an imported statistic."""
    return {
        "mean_type": (
            StatisticMeanType.NONE if has_sum else StatisticMeanType.ARITHMETIC
        ),
        "has_sum": has_sum,
        "name": None,
        "source": "recorder",
        "statistic_id": entity,
        "unit_class": None,
        "unit_of_measurement": "kWh" if has_sum else "°C",
    }


async def test_one_statistic_from_the_recorder(hass: HomeAssistant) -> None:
    """min, max and mean over the last hours, from imported hourly rows."""
    hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    rows = [
        {
            "start": hour - timedelta(hours=k),
            "mean": 10.0 + k,
            "min": 9.0 + k,
            "max": 11.0 + k,
        }
        for k in range(1, 4)
    ]
    async_import_statistics(hass, _metadata("sensor.outside", has_sum=False), rows)
    await async_wait_recording_done(hass)
    slot = {"kind": "statistics", "entity": "sensor.outside", "hours": 5}
    assert await async_evaluate_slot(hass, {**slot, "stat": "max"}) == 14.0
    assert await async_evaluate_slot(hass, {**slot, "stat": "min"}) == 10.0
    assert await async_evaluate_slot(hass, {**slot, "stat": "mean"}) == 12.0
    nothing = {**slot, "entity": "sensor.none", "stat": "min"}
    assert await async_evaluate_slot(hass, nothing) is None


async def test_today_by_the_hour_from_the_recorder(hass: HomeAssistant) -> None:
    """The change of each hour of today so far, from imported sums."""
    now = dt_util.utcnow()
    midnight = dt_util.as_utc(dt_util.start_of_local_day())
    hour = now.replace(minute=0, second=0, microsecond=0)
    starts = []
    start = midnight
    while start < hour:
        starts.append(start)
        start += timedelta(hours=1)
    # A running total that grows by 1, 2, 3, ... each hour.
    rows = [
        {"start": start, "sum": sum(range(1, n + 2)), "state": 0}
        for n, start in enumerate(starts)
    ]
    before = {"start": midnight - timedelta(hours=1), "sum": 0, "state": 0}
    async_import_statistics(
        hass, _metadata("sensor.energy", has_sum=True), [before, *rows]
    )
    await async_wait_recording_done(hass)
    slot = {
        "kind": "statistics",
        "entity": "sensor.energy",
        "buckets": "hour",
        "period": "today",
        "stat": "sum",
    }
    value = await async_evaluate_slot(hass, slot)
    hours_done = len(starts)
    assert len(value) == dt_util.as_local(now).hour + 1
    assert value[:hours_done] == [float(n + 1) for n in range(hours_done)]
    # The running hour has no rows yet.
    assert value[-1] == 0.0
