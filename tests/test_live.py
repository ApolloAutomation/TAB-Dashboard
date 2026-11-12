"""Tests for live card values and card calls."""

import asyncio
import logging

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockUser,
    async_mock_service,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.apollo_tab.live import (
    async_fetch_history,
    decimate,
    jsonable,
)

from .conftest import WriteComponent, setup_integration

LIGHT_TILE_CARD = {
    "component": "apollo/light-tile",
    "params": {"entity": "light.kitchen"},
}
LIGHT_SLIDER_CARD = {
    "component": "apollo/light-slider",
    "params": {"entity": "light.kitchen"},
}
LOCK_CARD = {
    "component": "apollo/lock",
    "params": {"entity": "lock.front_door"},
}
BLINDS_CARD = {
    "component": "apollo/blinds",
    "params": {"entity": "cover.garage"},
}
SENSOR_CARD = {
    "component": "apollo/sensor-value",
    "params": {"entity": "sensor.temperature"},
}
SIMPLE_CARD = {
    "component": "me/simple",
    "params": {"entity": "light.kitchen"},
}
VAULT_CARD = {
    "component": "me/vault",
    "params": {"entity": "lock.front_door"},
}

SIMPLE_COMPONENT = """\
id: me/simple
version: 1.0.0
name: Simple
size: 1x1
params:
  entity: {domain: light}
inputs:
  bad: "{{ undefined_thing.foo.bar }}"
outputs:
  toggle:
    action: light.toggle
    data: {entity_id: "{{ entity }}"}
    feedback: optimistic
layout:
  - type: switch
    value: bad
    on_tap: toggle
"""

VAULT_COMPONENT = """\
id: me/vault
version: 1.0.0
name: Vault
size: 1x1
params:
  entity: {domain: lock}
inputs:
  state: "{{ states(entity) }}"
outputs:
  unlock:
    action: lock.unlock
    data: {entity_id: "{{ entity }}"}
    feedback: confirm
layout:
  - type: button
    icon: mdi:lock-open
    on_tap: unlock
"""


async def _subscribe(client, card: dict) -> int:
    """Subscribe to a card and return the message id."""
    await client.send_json_auto_id(
        {"type": "apollo_tab/card/subscribe", "card": card, "dashboard": None}
    )
    response = await client.receive_json()
    assert response["success"], response
    assert response["result"] is None
    return response["id"]


async def _next_event(client, msg_id: int) -> dict:
    """Return the next event of the subscription."""
    message = await client.receive_json()
    assert message["id"] == msg_id
    assert message["type"] == "event"
    return message["event"]


async def _call(
    client,
    card: dict,
    widget: int,
    event: str = "tap",
    value: object = None,
    confirmed: bool = False,
) -> dict:
    """Send a card call and return the response."""
    message = {
        "type": "apollo_tab/card/call",
        "card": card,
        "widget": widget,
        "event": event,
        "confirmed": confirmed,
    }
    if value is not None:
        message["value"] = value
    await client.send_json_auto_id(message)
    return await client.receive_json()


def test_jsonable() -> None:
    """Template results are reduced to what the websocket API allows."""
    assert jsonable(None) is None
    assert jsonable(True) is True
    assert jsonable(7) == 7
    assert jsonable(1.5) == 1.5
    assert jsonable("abc") == "abc"
    assert jsonable("x" * 600) == "x" * 512
    assert jsonable([1, 2.5, -3]) == [1, 2.5, -3]
    assert jsonable(list(range(200))) == list(range(120))
    assert jsonable((1, 2)) == [1, 2]
    assert jsonable([1, "two"]) == "[1, 'two']"
    assert jsonable({"a": 1}) == "{'a': 1}"


def test_decimate() -> None:
    """History values are averaged into near-equal buckets."""
    values = [float(index) for index in range(100)]
    assert decimate(values, 120) == values
    result = decimate([float(index) for index in range(240)], 120)
    assert len(result) == 120
    assert result[0] == 0.5
    assert result[-1] == 238.5
    assert decimate([1.0, 2.0, 4.0], 1) == [2.33]


async def test_history_empty_without_recorder(hass: HomeAssistant) -> None:
    """Without the recorder the history slot is an empty list."""
    assert await async_fetch_history(hass, "sensor.temperature", 24) == []


async def test_subscribe_sends_init_then_values(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """A subscribe answers with init, then one values event with every slot."""
    hass.states.async_set("light.kitchen", "on", {"brightness": 128})
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    msg_id = await _subscribe(client, LIGHT_TILE_CARD)
    init = await _next_event(client, msg_id)
    assert init["type"] == "init"
    assert init["card"]["component"] == "apollo/light-tile"
    assert init["card"]["demo"] is False
    assert "slots" not in init["card"]
    assert "actions" not in init["card"]
    assert init["theme"]["id"] == "midnight"
    assert isinstance(init["style"], dict)
    values = await _next_event(client, msg_id)
    assert values["type"] == "values"
    assert "on" in values["values"].values()
    assert values["errors"] == {}


async def test_for_each_slots_each_get_their_own_value(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """Slots that share template text but not variables all report a value."""
    hass.states.async_set("scene.movie", "scening", {"friendly_name": "Movie"})
    hass.states.async_set("scene.dinner", "scening", {"friendly_name": "Dinner"})
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    msg_id = await _subscribe(
        client,
        {
            "component": "apollo/scene-row",
            "params": {"scenes": ["scene.movie", "scene.dinner"]},
        },
    )
    init = await _next_event(client, msg_id)
    values = await _next_event(client, msg_id)
    texts = [values["values"][str(w["text"]["s"])] for w in init["card"]["widgets"]]
    assert texts == ["Movie", "Dinner"]
    assert values["errors"] == {}


async def test_values_update_when_state_changes(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """Only the changed slots are pushed after a state change."""
    hass.states.async_set("light.kitchen", "on")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    msg_id = await _subscribe(client, LIGHT_SLIDER_CARD)
    assert (await _next_event(client, msg_id))["type"] == "init"
    first = await _next_event(client, msg_id)
    assert "0%" in first["values"].values()
    hass.states.async_set("light.kitchen", "on", {"brightness": 204})
    await hass.async_block_till_done()
    update = await _next_event(client, msg_id)
    assert update["type"] == "values"
    assert set(update["values"].values()) == {80, "80%"}


async def test_missing_entity_renders_unknown(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """A missing entity renders as unknown, not as an error."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    msg_id = await _subscribe(client, LIGHT_SLIDER_CARD)
    assert (await _next_event(client, msg_id))["type"] == "init"
    values = await _next_event(client, msg_id)
    assert "unknown" in values["values"].values()
    assert values["errors"] == {}


async def test_template_error_reported_per_slot(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    user_components: WriteComponent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing slot lands in errors, and nothing is logged."""
    user_components("simple.yaml", SIMPLE_COMPONENT)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    msg_id = await _subscribe(client, SIMPLE_CARD)
    assert (await _next_event(client, msg_id))["type"] == "init"
    values = await _next_event(client, msg_id)
    # The header title comes from the Component's name, so only the switch fails.
    assert values["values"] == {"1": "Simple"}
    assert list(values["errors"]) == ["2"]
    text = next(iter(values["errors"].values()))
    assert text.startswith("UndefinedError:")
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


async def test_unsubscribe_removes_trackers(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """After unsubscribing, state changes produce no more events."""
    hass.states.async_set("light.kitchen", "on")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    msg_id = await _subscribe(client, LIGHT_SLIDER_CARD)
    assert (await _next_event(client, msg_id))["type"] == "init"
    await _next_event(client, msg_id)
    await client.send_json_auto_id(
        {"type": "unsubscribe_events", "subscription": msg_id}
    )
    response = await client.receive_json()
    assert response["success"], response
    hass.states.async_set("light.kitchen", "off")
    await hass.async_block_till_done()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.1):
            await client.receive_json()


async def test_unknown_component_error_event(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """An unknown component gives an error event, and stays subscribed."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    msg_id = await _subscribe(client, {"component": "apollo/nope", "params": {}})
    event = await _next_event(client, msg_id)
    assert event["type"] == "error"
    assert event["code"] == "unknown_component"


async def test_component_that_is_not_text_error_event(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """A component given as a list gives the same error event, not a crash."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    msg_id = await _subscribe(client, {"component": ["apollo/light-tile"]})
    event = await _next_event(client, msg_id)
    assert event["type"] == "error"
    assert event["code"] == "unknown_component"


async def test_reinit_after_library_reload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    user_components: WriteComponent,
) -> None:
    """A library reload recompiles the subscribed cards."""
    user_components("simple.yaml", SIMPLE_COMPONENT)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    msg_id = await _subscribe(client, SIMPLE_CARD)
    init = await _next_event(client, msg_id)
    assert init["type"] == "init"
    assert init["card"]["name"] == "Simple"
    await _next_event(client, msg_id)
    user_components(
        "simple.yaml", SIMPLE_COMPONENT.replace("name: Simple", "name: Renamed")
    )
    await client.send_json_auto_id({"type": "apollo_tab/library/reload"})
    # The recompiled init and values can arrive before the reload's own result.
    messages = [await client.receive_json() for _ in range(3)]
    result = next(message for message in messages if message["type"] == "result")
    assert result["success"], result
    events = [message for message in messages if message["type"] == "event"]
    assert all(message["id"] == msg_id for message in events)
    assert [message["event"]["type"] for message in events] == ["init", "values"]
    assert events[0]["event"]["card"]["name"] == "Renamed"


async def test_call_toggles_light(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
) -> None:
    """A tap on the switch toggles the light as the connected user."""
    hass.states.async_set("light.kitchen", "off")
    calls = async_mock_service(hass, "light", "toggle")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    response = await _call(client, LIGHT_TILE_CARD, 0)
    assert response["success"], response
    assert response["result"] == {"ok": True}
    assert len(calls) == 1
    assert calls[0].data["entity_id"] == "light.kitchen"
    assert calls[0].context.user_id == hass_admin_user.id


async def test_call_slider_value_rendered(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """A slider change renders the value into the service data."""
    hass.states.async_set("light.kitchen", "on", {"brightness": 128})
    calls = async_mock_service(hass, "light", "turn_on")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    response = await _call(client, LIGHT_SLIDER_CARD, 1, event="change", value=42)
    assert response["success"], response
    assert len(calls) == 1
    assert calls[0].data["entity_id"] == "light.kitchen"
    assert calls[0].data["brightness_pct"] == 42


async def test_call_value_out_of_range(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """Values outside the widget range, and booleans, are refused."""
    hass.states.async_set("light.kitchen", "on")
    calls = async_mock_service(hass, "light", "turn_on")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    response = await _call(client, LIGHT_SLIDER_CARD, 1, event="change", value=150)
    assert not response["success"]
    assert response["error"]["code"] == "invalid_value"
    response = await _call(client, LIGHT_SLIDER_CARD, 1, event="change", value=-1)
    assert response["error"]["code"] == "invalid_value"
    response = await _call(client, LIGHT_SLIDER_CARD, 1, event="change", value=True)
    assert response["error"]["code"] == "invalid_value"
    assert not calls


async def test_call_confirm_required_for_lock(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """A lock action with confirm feedback asks for confirmation first."""
    hass.states.async_set("lock.front_door", "locked")
    calls = async_mock_service(hass, "lock", "unlock")
    await setup_integration(hass, config_entry)
    await config_entry.runtime_data.library.async_set_approved("apollo/lock", True)
    client = await hass_ws_client(hass)
    response = await _call(client, LOCK_CARD, 1)
    assert not response["success"]
    assert response["error"]["code"] == "confirm_required"
    assert not calls


async def test_call_confirmed_lock(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """A confirmed lock action runs the service."""
    hass.states.async_set("lock.front_door", "locked")
    calls = async_mock_service(hass, "lock", "unlock")
    await setup_integration(hass, config_entry)
    await config_entry.runtime_data.library.async_set_approved("apollo/lock", True)
    client = await hass_ws_client(hass)
    response = await _call(client, LOCK_CARD, 1, confirmed=True)
    assert response["success"], response
    assert len(calls) == 1
    assert calls[0].data["entity_id"] == "lock.front_door"


async def test_call_garage_cover_needs_confirmation(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """A garage door needs confirmation because of its device class."""
    hass.states.async_set("cover.garage", "closed", {"device_class": "garage"})
    calls = async_mock_service(hass, "cover", "open_cover")
    await setup_integration(hass, config_entry)
    await config_entry.runtime_data.library.async_set_approved("apollo/blinds", True)
    client = await hass_ws_client(hass)
    response = await _call(client, BLINDS_CARD, 0)
    assert not response["success"]
    assert response["error"]["code"] == "confirm_required"
    assert not calls
    response = await _call(client, BLINDS_CARD, 0, confirmed=True)
    assert response["success"], response
    assert len(calls) == 1
    assert calls[0].data["entity_id"] == "cover.garage"


async def test_call_demo_card_refused(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """Calls on a card in example mode are refused."""
    hass.states.async_set("light.kitchen", "on")
    calls = async_mock_service(hass, "light", "toggle")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    response = await _call(client, {"component": "apollo/light-tile"}, 0)
    assert not response["success"]
    assert response["error"]["code"] == "demo"
    assert not calls


async def test_call_unapproved_refused(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    user_components: WriteComponent,
) -> None:
    """A sensitive component that was never approved cannot run."""
    user_components("vault.yaml", VAULT_COMPONENT)
    hass.states.async_set("lock.front_door", "locked")
    calls = async_mock_service(hass, "lock", "unlock")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    response = await _call(client, VAULT_CARD, 0, confirmed=True)
    assert not response["success"]
    assert response["error"]["code"] == "needs_approval"
    assert not calls


async def test_call_local_output_refused(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """Local outputs are handled in the browser, not over this command."""
    hass.states.async_set("sensor.temperature", "21.5")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    response = await _call(client, SENSOR_CARD, 0)
    assert not response["success"]
    assert response["error"]["code"] == "local_action"


async def test_call_service_error_reported(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """A failing service is reported as service_error with its message."""
    hass.states.async_set("light.kitchen", "off")

    def _boom(call: ServiceCall) -> None:
        """Raise the error the test asserts on."""
        raise HomeAssistantError("boom")

    hass.services.async_register("light", "toggle", _boom)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    response = await _call(client, LIGHT_TILE_CARD, 0)
    assert not response["success"]
    assert response["error"]["code"] == "service_error"
    assert "boom" in response["error"]["message"]


RUNNER_CARD = {
    "component": "me/runner",
    "params": {"entity": "script.harmless"},
}

RUNNER_COMPONENT = """\
id: me/runner
version: 1.0.0
name: Runner
size: 1x1
params:
  entity: {domain: script}
outputs:
  run:
    action: script.turn_on
    data: {entity_id: "{{ entity }}"}
    feedback: pulse
layout:
  - type: button
    icon: mdi:play
    on_tap: run
"""


async def test_call_script_turn_on_runs_picked_script(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    user_components: WriteComponent,
) -> None:
    """A script.turn_on output runs the script the card picked."""
    user_components("runner.yaml", RUNNER_COMPONENT)
    hass.states.async_set("script.harmless", "off")
    calls = async_mock_service(hass, "script", "turn_on")
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    response = await _call(client, RUNNER_CARD, 0)
    assert response["success"], response
    assert len(calls) == 1
    assert calls[0].data["entity_id"] == "script.harmless"


async def test_call_refuses_script_service_by_name(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    user_components: WriteComponent,
) -> None:
    """A script.<name> action that slipped past validation is still refused."""
    user_components("runner.yaml", RUNNER_COMPONENT)
    hass.states.async_set("script.harmless", "off")
    hass.states.async_set("script.secret", "off")
    secret_calls = async_mock_service(hass, "script", "secret")
    turn_on_calls = async_mock_service(hass, "script", "turn_on")
    await setup_integration(hass, config_entry)
    outputs = config_entry.runtime_data.library.components["me/runner"]["outputs"]
    outputs["run"]["action"] = "script.secret"
    client = await hass_ws_client(hass)
    response = await _call(client, RUNNER_CARD, 0)
    assert not response["success"]
    assert response["error"]["code"] == "not_allowed"
    assert not secret_calls
    assert not turn_on_calls
