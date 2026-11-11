"""Tests for unloading the entry with open websocket subscriptions."""

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import setup_integration

LIGHT_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "apollo/light-slider",
    "params": {"entity": "light.kitchen"},
}


NEW_COMPONENT = """\
id: me/new
version: 1.0.0
name: New
size: 1x1
layout:
  - {type: label, text: Hi}
"""

TAB_CONFIG = {
    "apollo_tab": {"version": 1, "theme": "midnight"},
    "views": [
        {
            "type": "sections",
            "path": "home",
            "title": "Home",
            "sections": [{"type": "grid", "cards": [LIGHT_CARD]}],
        }
    ],
}


async def _flush_delayed_saves(hass: Any) -> None:
    """Let pending storage writes finish; each holds a bus listener."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done()


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


async def test_unload_stops_card_subscriptions(
    hass, config_entry, hass_ws_client
) -> None:
    """Unloading stops the trackers and sends the card a not_loaded event."""
    hass.states.async_set("light.kitchen", "on")
    await setup_integration(hass, config_entry)
    data = config_entry.runtime_data
    client = await hass_ws_client(hass)
    before = dict(hass.bus.async_listeners())
    await _subscribe_card(client, LIGHT_CARD)
    assert len(data.subscriptions) == 1
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    event = await _receive_event(client)
    assert event["type"] == "error"
    assert event["code"] == "not_loaded"
    hass.states.async_set("light.kitchen", "on", {"brightness": 10})
    await hass.async_block_till_done()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.2):
            await client.receive_json()
    for event_type, count in hass.bus.async_listeners().items():
        assert count <= before.get(event_type, 0)
    assert data.subscriptions == set()


async def test_unload_ends_listener_subscriptions(
    hass, config_entry, hass_ws_client
) -> None:
    """Unloading ends library and layout subscriptions with a last event."""
    await setup_integration(hass, config_entry)
    data = config_entry.runtime_data
    base_listeners = len(data.manager._listeners)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "apollo_tab/library/subscribe"})
    result = await client.receive_json()
    assert result["success"], result
    library_id = result["id"]
    await client.send_json_auto_id({"type": "apollo_tab/layout/subscribe"})
    result = await client.receive_json()
    assert result["success"], result
    layout_id = result["id"]
    assert len(data.subscriptions) == 2
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert data.subscriptions == set()
    assert len(data.manager._listeners) == base_listeners
    ended = [await client.receive_json(), await client.receive_json()]
    assert {message["id"] for message in ended} == {library_id, layout_id}
    assert all(message["event"] == {"type": "not_loaded"} for message in ended)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.2):
            await client.receive_json()
    for subscription_id in (library_id, layout_id):
        await client.send_json_auto_id(
            {"type": "unsubscribe_events", "subscription": subscription_id}
        )
        result = await client.receive_json()
        assert result["success"], result


async def test_library_subscription_can_follow_a_reload(
    hass, config_entry, hass_ws_client, user_components
) -> None:
    """A reload ends the library subscription; a new one hears later changes."""
    user_components("keep.yaml", "")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "apollo_tab/library/subscribe"})
    result = await client.receive_json()
    assert result["success"], result
    old_id = result["id"]
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    ended = await client.receive_json()
    assert ended["id"] == old_id
    assert ended["event"] == {"type": "not_loaded"}

    await client.send_json_auto_id({"type": "apollo_tab/library/subscribe"})
    result = await client.receive_json()
    assert result["success"], result
    new_id = result["id"]
    user_components("new.yaml", NEW_COMPONENT)
    await client.send_json_auto_id({"type": "apollo_tab/library/reload"})
    messages = [await client.receive_json(), await client.receive_json()]
    changed = [message for message in messages if message["type"] == "event"]
    assert [message["id"] for message in changed] == [new_id]
    assert changed[0]["event"] == {"type": "changed"}
    await client.send_json_auto_id({"type": "apollo_tab/library"})
    result = await client.receive_json()
    assert "me/new" in {item["id"] for item in result["result"]["components"]}


async def test_unload_leaves_no_listeners(
    hass, config_entry, hass_ws_client, tab_dashboard
) -> None:
    """A second setup and unload leaves no more bus listeners than the first."""
    hass.states.async_set("light.kitchen", "on")
    # Home Assistant itself adds listeners during the first setup and for the
    # open connection, so count after one full cycle with the client open.
    await setup_integration(hass, config_entry)
    client = await tab_dashboard(TAB_CONFIG)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await _flush_delayed_saves(hass)
    before = dict(hass.bus.async_listeners())

    await setup_integration(hass, config_entry)
    data = config_entry.runtime_data
    for command in (
        {"type": "apollo_tab/library/subscribe"},
        {"type": "apollo_tab/layout/subscribe"},
    ):
        await client.send_json_auto_id(command)
        result = await client.receive_json()
        assert result["success"], result
    await _subscribe_card(client, LIGHT_CARD)
    during = hass.bus.async_listeners()
    for event_type in ("lovelace_updated", "device_registry_updated"):
        assert during[event_type] > before.get(event_type, 0)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await _flush_delayed_saves(hass)
    assert hass.bus.async_listeners() == before
    assert data.subscriptions == set()
    assert len(data.slot_hub) == 0
    assert data.library._listeners == []
    assert data.manager._listeners == []


async def test_reload_notifies_card_subscriptions(
    hass, config_entry, hass_ws_client
) -> None:
    """Reloading fails the open subscription and serves new ones."""
    hass.states.async_set("light.kitchen", "on")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await _subscribe_card(client, LIGHT_CARD)
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    event = await _receive_event(client)
    assert event["type"] == "error"
    assert event["code"] == "not_loaded"
    await _subscribe_card(client, LIGHT_CARD)
