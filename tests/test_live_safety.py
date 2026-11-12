"""Tests for the live-value safety limits."""

import asyncio
import contextlib
import logging
import time
from datetime import timedelta
from typing import Any

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.apollo_tab import live, sandbox, websocket
from custom_components.apollo_tab.live import json_safe, jsonable

from .conftest import setup_integration

BIG_STATE = "123456789012345678901234567890"

SENSOR_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "apollo/sensor-value",
    "params": {"entity": "sensor.serial"},
}

TAB_CONFIG = {
    "apollo_tab": {"version": 1, "theme": "midnight"},
    "views": [
        {
            "type": "sections",
            "path": "home",
            "title": "Home",
            "max_columns": 3,
            "sections": [
                {
                    "type": "grid",
                    "cards": [
                        {
                            "type": "custom:apollo-tab-card",
                            "component": "apollo/sensor-value",
                            "params": {"entity": "sensor.serial"},
                        }
                    ],
                }
            ],
        }
    ],
}

TOGGLE_COMPONENT = """\
id: me/toggle
version: 1.0.0
name: Toggle
size: 1x1
params:
  entity: {domain: light}
outputs:
  switch_on:
    action: light.turn_on
    data: {entity_id: "{{ entity }}"}
    feedback: pulse
layout:
  - type: button
    text: "On"
    on_tap: switch_on
"""

TOGGLE_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "me/toggle",
    "params": {"entity": "light.kitchen"},
}

# Nine hundred million loop steps without the step limit.
SLOW_INPUT = (
    "{% for i in range(30000) %}{% for j in range(30000) %}{% endfor %}{% endfor %}done"
)

SLOW_COMPONENT = f"""\
id: me/slow
version: 1.0.0
name: Slow
size: 1x1
params:
  entity: {{domain: light}}
inputs:
  slow: "{SLOW_INPUT}"
  state: "{{{{ states(entity) }}}}"
layout:
  - type: label
    text: "{{{{ slow }}}}"
  - type: label
    text: "{{{{ state }}}}"
"""

SLOW_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "me/slow",
    "params": {"entity": "light.kitchen"},
}

BOMB_COMPONENT = """\
id: me/bomb
version: 1.0.0
name: Bomb
size: 1x1
params:
  entity: {domain: light}
inputs:
  state: "{{ states(entity) }}"
layout:
  - type: label
    text: "{{ ('%9' ~ '99999999d') % 1 }}"
  - type: label
    text: "{{ 'x' | center(30000 * 30000) }}"
  - type: label
    text: "{{ state }}"
"""

BOMB_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "me/bomb",
    "params": {"entity": "light.kitchen"},
}

# The nested loops run only when input_boolean.trip turns on.
TRIP_INPUT = (
    "{% if is_state('input_boolean.trip','on') %}"
    "{% for i in range(100000) %}"
    "{% for j in range(1000) %}"
    "{% endfor %}{% endfor %}"
    "{% endif %}ok"
)

TRIP_COMPONENT = f"""\
id: me/trip
version: 1.0.0
name: Trip
size: 1x1
params:
  entity: {{domain: light}}
inputs:
  state: "{{{{ states(entity) }}}}"
layout:
  - type: label
    text: "{TRIP_INPUT}"
  - type: label
    text: "{{{{ state }}}}"
"""

TRIP_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "me/trip",
    "params": {"entity": "light.kitchen"},
}

# Same loop shape, but the ranges stay under the size limit.
TRIP_SLOW_INPUT = (
    "{% if is_state('input_boolean.trip','on') %}"
    "{% for i in range(30000) %}"
    "{% for j in range(30000) %}"
    "{% endfor %}{% endfor %}"
    "{% endif %}ok"
)

TRIP_SLOW_COMPONENT = f"""\
id: me/trip-slow
version: 1.0.0
name: Trip Slow
size: 1x1
params:
  entity: {{domain: light}}
inputs:
  state: "{{{{ states(entity) }}}}"
layout:
  - type: label
    text: "{TRIP_SLOW_INPUT}"
  - type: label
    text: "{{{{ state }}}}"
"""

TRIP_SLOW_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "me/trip-slow",
    "params": {"entity": "light.kitchen"},
}


async def _receive_event(client: Any) -> dict:
    """Receive one websocket message and return its event payload."""
    message = await client.receive_json()
    assert message["type"] == "event"
    return message["event"]


async def _subscribe_card(client: Any, card: dict) -> dict:
    """Subscribe to a card and return its first values event."""
    await client.send_json_auto_id({"type": "apollo_tab/card/subscribe", "card": card})
    result = await client.receive_json()
    assert result["success"], result
    init = await _receive_event(client)
    assert init["type"] == "init"
    values = await _receive_event(client)
    assert values["type"] == "values"
    return values


async def _subscribe_card_with_id(client: Any, card: dict) -> tuple[int, dict]:
    """Subscribe to a card and return the message id and first values event."""
    await client.send_json_auto_id({"type": "apollo_tab/card/subscribe", "card": card})
    result = await client.receive_json()
    assert result["success"], result
    init = await _receive_event(client)
    assert init["type"] == "init"
    values = await _receive_event(client)
    assert values["type"] == "values"
    return result["id"], values


async def _unsubscribe(client: Any, msg_id: int) -> None:
    """Unsubscribe a subscription and assert the success result."""
    await client.send_json_auto_id(
        {"type": "unsubscribe_events", "subscription": msg_id}
    )
    result = await client.receive_json()
    assert result["success"], result


async def _approve(client: Any, component_id: str) -> None:
    """Approve a user component so the card may use it."""
    await client.send_json_auto_id(
        {
            "type": "apollo_tab/library/approve",
            "component_id": component_id,
            "approved": True,
        }
    )
    result = await client.receive_json()
    assert result["success"], result


async def _call_card(client: Any, card: dict) -> dict:
    """Send a tap on widget 0 and return the result message."""
    await client.send_json_auto_id(
        {
            "type": "apollo_tab/card/call",
            "card": card,
            "widget": 0,
            "event": "tap",
            "confirmed": False,
        }
    )
    return await client.receive_json()


def test_jsonable_big_numbers() -> None:
    """Numbers that break the JSON encoder become text or None."""
    assert jsonable(7) == 7
    assert jsonable(1.5) == 1.5
    assert jsonable(True) is True
    assert jsonable(2**53 - 1) == 2**53 - 1
    assert jsonable(2**53) == "9007199254740992"
    assert jsonable(-(2**60)) == str(-(2**60))
    assert jsonable(float("nan")) is None
    assert jsonable(float("inf")) is None
    assert jsonable(float("-inf")) is None
    assert jsonable([1, 2**60, float("nan")]) == [1, float(2**60), None]


def test_jsonable_other_values() -> None:
    """Strings, lists and objects keep their established reductions."""
    assert jsonable("x" * 600) == "x" * 512
    assert jsonable(list(range(200))) == list(range(120))
    assert jsonable((1, 2)) == [1, 2]
    assert jsonable([1, "two"]) == "[1, 'two']"
    assert jsonable({"a": 1}) == "{'a': 1}"


def test_json_safe() -> None:
    """Nested structures are made safe for the JSON encoder."""
    value = {"a": [1, 2**70, {"b": float("inf")}], "c": "x", "t": (1, 2)}
    assert json_safe(value) == {
        "a": [1, str(2**70), {"b": None}],
        "c": "x",
        "t": [1, 2],
    }


async def test_big_number_state_delivered(
    hass, config_entry, hass_ws_client, caplog
) -> None:
    """A state that is a huge number is delivered to the card as text."""
    hass.states.async_set("sensor.serial", BIG_STATE)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    values = await _subscribe_card(client, SENSOR_CARD)
    assert BIG_STATE in values["values"].values()
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


async def test_layout_get_with_big_number(
    hass, config_entry, hass_ws_client, tab_dashboard
) -> None:
    """The layout command answers when a slot value is a huge number."""
    hass.states.async_set("sensor.serial", BIG_STATE)
    await setup_integration(hass, config_entry)
    await tab_dashboard(TAB_CONFIG, url_path="tab-1")
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "apollo_tab/layout/get", "url_path": "tab-1"}
    )
    result = await client.receive_json()
    assert result["success"], result
    assert BIG_STATE in result["result"]["values"].values()


async def test_slow_slot_is_reported_and_not_tracked(
    hass, config_entry, user_components, hass_ws_client
) -> None:
    """A too slow template slot gets an error and is not tracked."""
    user_components("slow.yaml", SLOW_COMPONENT)
    hass.states.async_set("light.kitchen", "on")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await _approve(client, "me/slow")
    start = time.perf_counter()
    values = await _subscribe_card(client, SLOW_CARD)
    assert time.perf_counter() - start < 5
    errors = values["errors"].values()
    assert any(
        "switched off: rendering needed more than" in text
        or "switched off: rendering took longer than" in text
        for text in errors
    )
    assert "on" in values["values"].values()
    await hass.async_block_till_done()
    # The header title and the state label stay tracked; the slow label does not.
    assert len(config_entry.runtime_data.slot_hub) == 2


async def test_target_keys_are_refused(
    hass, config_entry, user_components, hass_ws_client
) -> None:
    """An output may not add area, device, floor or label targets."""
    user_components("toggle.yaml", TOGGLE_COMPONENT)
    hass.states.async_set("light.kitchen", "off")
    await setup_integration(hass, config_entry)
    calls = async_mock_service(hass, "light", "turn_on")
    client = await hass_ws_client(hass)
    await _approve(client, "me/toggle")
    component = config_entry.runtime_data.library.components["me/toggle"]
    component["outputs"]["switch_on"]["data"]["area_id"] = "garage"
    result = await _call_card(client, TOGGLE_CARD)
    assert not result["success"]
    assert result["error"]["code"] == "not_allowed"
    assert calls == []


async def test_service_data_templates_are_limited(
    hass, config_entry, user_components, hass_ws_client
) -> None:
    """A service data template cannot read another entity's state."""
    user_components("toggle.yaml", TOGGLE_COMPONENT)
    hass.states.async_set("light.kitchen", "off")
    hass.states.async_set("sensor.door_code", "4711")
    await setup_integration(hass, config_entry)
    calls = async_mock_service(hass, "light", "turn_on")
    client = await hass_ws_client(hass)
    await _approve(client, "me/toggle")
    component = config_entry.runtime_data.library.components["me/toggle"]
    data = component["outputs"]["switch_on"]["data"]
    data["brightness"] = "{{ states('sensor.door_code') }}"
    result = await _call_card(client, TOGGLE_CARD)
    assert not result["success"]
    assert result["error"]["code"] == "service_error"
    assert calls == []


async def test_library_load_with_folding_templates_is_fast(
    hass, config_entry, user_components, hass_ws_client
) -> None:
    """A Component with folding templates loads fast and fails at render."""
    user_components("bomb.yaml", BOMB_COMPONENT)
    hass.states.async_set("light.kitchen", "on")
    start = time.perf_counter()
    await setup_integration(hass, config_entry)
    assert time.perf_counter() - start < 2
    library = config_entry.runtime_data.library
    assert "me/bomb" in library.components
    assert library.errors == []
    client = await hass_ws_client(hass)
    start = time.perf_counter()
    values = await _subscribe_card(client, BOMB_CARD)
    assert time.perf_counter() - start < 1
    errors = values["errors"].values()
    assert any("formatting text with % is not allowed" in text for text in errors)
    assert any(
        "a value grew beyond 32768 characters or items" in text for text in errors
    )
    assert "on" in values["values"].values()


async def test_trip_rerender_is_bounded_for_read_only_user(
    hass, config_entry, user_components, hass_ws_client, hass_read_only_access_token
) -> None:
    """A read-only user's re-render is bounded when the trip turns on."""
    user_components("trip.yaml", TRIP_COMPONENT)
    hass.states.async_set("input_boolean.trip", "off")
    hass.states.async_set("light.kitchen", "on")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    values = await _subscribe_card(client, TRIP_CARD)
    assert "ok" in values["values"].values()
    start = time.perf_counter()
    hass.states.async_set("input_boolean.trip", "on")
    await hass.async_block_till_done()
    assert time.perf_counter() - start < 0.5
    values = await _receive_event(client)
    assert values["type"] == "values"
    assert any("RenderLimitError" in text for text in values["errors"].values())


async def test_slow_rerender_switches_slot_off(
    hass, config_entry, user_components, hass_ws_client
) -> None:
    """A slow re-render switches the slot off and stops the tracker."""
    user_components("trip_slow.yaml", TRIP_SLOW_COMPONENT)
    hass.states.async_set("input_boolean.trip", "off")
    hass.states.async_set("light.kitchen", "on")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    values = await _subscribe_card(client, TRIP_SLOW_CARD)
    assert "ok" in values["values"].values()
    start = time.perf_counter()
    hass.states.async_set("input_boolean.trip", "on")
    await hass.async_block_till_done()
    assert time.perf_counter() - start < 1
    values = await _receive_event(client)
    assert values["type"] == "values"
    assert any("switched off" in text for text in values["errors"].values())
    await hass.async_block_till_done()
    for state in ("off", "on"):
        start = time.perf_counter()
        hass.states.async_set("input_boolean.trip", state)
        await hass.async_block_till_done()
        assert time.perf_counter() - start < 0.1
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.2):
            await client.receive_json()


async def test_identical_subscriptions_share_trackers(
    hass, config_entry, hass_ws_client
) -> None:
    """Two subscriptions to the same card share one set of trackers."""
    hass.states.async_set("sensor.serial", "1234")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    first_id, _ = await _subscribe_card_with_id(client, SENSOR_CARD)
    hub = config_entry.runtime_data.slot_hub
    slots = len(hub)
    assert slots > 0
    second_id, _ = await _subscribe_card_with_id(client, SENSOR_CARD)
    assert len(hub) == slots
    await _unsubscribe(client, first_id)
    await _unsubscribe(client, second_id)
    await hass.async_block_till_done()
    assert len(hub) == 0


async def test_card_subscriptions_are_capped_per_connection(
    hass, config_entry, hass_ws_client, monkeypatch
) -> None:
    """A connection may hold only a limited number of card subscriptions."""
    monkeypatch.setattr(websocket, "MAX_CARD_SUBSCRIPTIONS", 2)
    hass.states.async_set("sensor.serial", "1234")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    first_id, _ = await _subscribe_card_with_id(client, SENSOR_CARD)
    await _subscribe_card_with_id(client, SENSOR_CARD)
    await client.send_json_auto_id(
        {"type": "apollo_tab/card/subscribe", "card": SENSOR_CARD}
    )
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "too_many_subscriptions"
    await _unsubscribe(client, first_id)
    await _subscribe_card_with_id(client, SENSOR_CARD)


async def test_switched_off_template_is_remembered_until_reload(
    hass, config_entry, user_components, hass_ws_client
) -> None:
    """A switched-off template is remembered until the library reloads."""
    user_components("slow.yaml", SLOW_COMPONENT)
    hass.states.async_set("light.kitchen", "on")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await _approve(client, "me/slow")
    first_id, values = await _subscribe_card_with_id(client, SLOW_CARD)
    assert any("switched off" in text for text in values["errors"].values())
    await hass.async_block_till_done()
    await _unsubscribe(client, first_id)
    start = time.perf_counter()
    _, values = await _subscribe_card_with_id(client, SLOW_CARD)
    assert time.perf_counter() - start < 0.5
    assert any("switched off" in text for text in values["errors"].values())
    await config_entry.runtime_data.library.async_load()
    fresh = await hass_ws_client(hass)
    values = await _subscribe_card(fresh, SLOW_CARD)
    assert any("switched off" in text for text in values["errors"].values())


class _StallingClock:
    """Stand in for the time module and stall the next render when armed."""

    def __init__(self) -> None:
        """Start without a stall."""
        self.armed = False
        self.offset = 0.0

    def monotonic(self) -> float:
        """Return the real clock; an armed reading is followed by a stall."""
        now = time.monotonic() + self.offset
        if self.armed:
            # This reading starts a render; the later ones see the stall.
            self.armed = False
            self.offset += 0.5
        return now


def _light_tile(entity_id: str) -> dict:
    """Return a light tile card for one entity."""
    return {
        "type": "custom:apollo-tab-card",
        "component": "apollo/light-tile",
        "params": {"entity": entity_id},
    }


async def _events_for(client: Any, msg_id: int) -> list[dict]:
    """Collect the events of one subscription that arrive within 0.2 s."""
    events = []
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout(0.2):
            while True:
                message = await client.receive_json()
                if message["type"] == "event" and message["id"] == msg_id:
                    events.append(message["event"])
    return events


async def test_one_stalled_render_does_not_switch_a_slot_off(
    hass, config_entry, hass_ws_client, monkeypatch
) -> None:
    """One stall during a render leaves the card's values working."""
    hass.states.async_set("light.a", "on", {"friendly_name": "A"})
    await setup_integration(hass, config_entry)
    clock = _StallingClock()
    monkeypatch.setattr(sandbox, "time", clock)
    client = await hass_ws_client(hass)
    msg_id, values = await _subscribe_card_with_id(client, _light_tile("light.a"))
    assert values["errors"] == {}
    tracked = len(config_entry.runtime_data.slot_hub)

    clock.armed = True
    hass.states.async_set("light.a", "off", {"friendly_name": "Hall"})
    await hass.async_block_till_done()
    events = await _events_for(client, msg_id)
    assert not clock.armed
    assert events
    assert all(event["errors"] == {} for event in events)
    assert any("Hall" in event["values"].values() for event in events)
    assert len(config_entry.runtime_data.slot_hub) == tracked
    _, values = await _subscribe_card_with_id(client, _light_tile("light.a"))
    assert values["errors"] == {}


async def test_switch_off_is_per_entity_and_expires(
    hass, config_entry, hass_ws_client, monkeypatch
) -> None:
    """A switched-off slot leaves other entities alone and comes back later."""
    hass.states.async_set("light.a", "on", {"friendly_name": "A"})
    hass.states.async_set("light.b", "on", {"friendly_name": "B"})
    await setup_integration(hass, config_entry)
    hub = config_entry.runtime_data.slot_hub
    clock = _StallingClock()
    monkeypatch.setattr(sandbox, "time", clock)
    client = await hass_ws_client(hass)
    first_id, _ = await _subscribe_card_with_id(client, _light_tile("light.a"))
    tracked = len(hub)

    events = []
    for number in range(sandbox.OVERRUN_LIMIT):
        clock.armed = True
        hass.states.async_set("light.a", "on", {"friendly_name": f"A{number}"})
        await hass.async_block_till_done()
        events += await _events_for(client, first_id)
    switched_off = [
        text
        for event in events
        for text in event["errors"].values()
        if "switched off: rendering took 0.50 seconds" in text
    ]
    assert len(switched_off) == 1
    assert len(hub) == tracked - 1

    # The same element with another entity shares the template text only.
    _, values = await _subscribe_card_with_id(client, _light_tile("light.b"))
    assert values["errors"] == {}
    # A new card for the same entity is told at once, without a render.
    second_id, values = await _subscribe_card_with_id(client, _light_tile("light.a"))
    assert list(values["errors"].values()) == switched_off
    assert len(hub) == 2 * tracked - 1

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=live.SWITCH_OFF_SECONDS + 1)
    )
    await hass.async_block_till_done()
    assert len(hub) == 2 * tracked
    # Both open cards get the value again after the fresh start.
    for _ in (first_id, second_id):
        message = await client.receive_json()
        assert message["id"] in (first_id, second_id)
        assert message["event"]["errors"] == {}
        assert len(message["event"]["values"]) == 1
    await _unsubscribe(client, first_id)
    await _unsubscribe(client, second_id)
    await hass.async_block_till_done()
    assert len(hub) == tracked


async def test_unload_cancels_switch_off_timers(
    hass, config_entry, user_components, hass_ws_client
) -> None:
    """Unloading drops the switched-off records and their timers."""
    user_components("slow.yaml", SLOW_COMPONENT)
    hass.states.async_set("light.kitchen", "on")
    await setup_integration(hass, config_entry)
    hub = config_entry.runtime_data.slot_hub
    client = await hass_ws_client(hass)
    await _approve(client, "me/slow")
    values = await _subscribe_card(client, SLOW_CARD)
    assert any("switched off" in text for text in values["errors"].values())
    await hass.async_block_till_done()
    assert len(hub._switched_off) == 1
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hub._switched_off == {}
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=live.SWITCH_OFF_SECONDS + 1)
    )
    await hass.async_block_till_done()
    assert len(hub) == 0
