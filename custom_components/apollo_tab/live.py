"""Live card values: subscriptions, history, actions and calls."""

import asyncio
import json
import math
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any

import probatio
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.components.recorder import history
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, TemplateError, Unauthorized
from homeassistant.helpers.event import (
    TrackTemplate,
    TrackTemplateResult,
    async_call_later,
    async_track_template_result,
    async_track_time_interval,
)
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from .maker.compile import compile_card, public_card
from .maker.const import CONFIRM_COVER_CLASSES, SENSITIVE_DOMAINS, TARGET_KEYS
from .maker.errors import MakerError
from .maker.schema import is_allowed_action, validate_card_config
from .maker.style import resolve_style
from .sandbox import ComponentTemplate, limit_error

if TYPE_CHECKING:
    from . import ApolloTabData
    from .library import Library

HISTORY_POINTS = 120
HISTORY_REFRESH_SECONDS = 300
# A switched-off slot gets a fresh start after this long.
SWITCH_OFF_SECONDS = 300

MAX_TEXT_LENGTH = 512
MAX_LIST_VALUES = 120
MAX_SAFE_INTEGER = 2**53 - 1


def _int_text(value: int) -> str | None:
    """Return a big integer as capped text, or None when it cannot print."""
    try:
        return str(value)[:MAX_TEXT_LENGTH]
    except ValueError:
        # Python refuses to print integers with more than 4300 digits.
        return None


def _safe_number(value: int | float) -> int | float | str | None:
    """Reduce one number to a value the JSON encoder accepts."""
    if isinstance(value, int):
        if -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            return value
        return _int_text(value)
    if math.isfinite(value):
        return value
    return None


def _list_number(value: int | float) -> int | float | None:
    """Reduce one list number, keeping the list numeric for the card."""
    if isinstance(value, int):
        if -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER:
            return value
        try:
            as_float = float(value)
        except OverflowError:
            # The integer is too large for a float as well.
            return None
        return as_float if math.isfinite(as_float) else None
    if math.isfinite(value):
        return value
    return None


def jsonable(value: Any) -> Any:
    """Reduce a template result to what the websocket API allows."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return _safe_number(value)
    if isinstance(value, str):
        return value[:MAX_TEXT_LENGTH]
    if isinstance(value, list | tuple):
        items = list(value[:MAX_LIST_VALUES])
        if all(
            isinstance(item, int | float) and not isinstance(item, bool)
            for item in items
        ):
            return [_list_number(item) for item in items]
    try:
        return str(value)[:MAX_TEXT_LENGTH]
    except ValueError:
        # A huge integer inside the value cannot be printed either.
        return ""


def json_safe(value: Any) -> Any:
    """Make a stored structure safe for the JSON encoder, recursively."""
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, int | float):
        return _safe_number(value)
    return value


def decimate(values: list[float], points: int) -> list[float]:
    """Average values into at most points buckets of near-equal size."""
    count = len(values)
    if count <= points:
        return values
    averaged = []
    for index in range(points):
        bucket = values[index * count // points : (index + 1) * count // points]
        averaged.append(round(sum(bucket) / len(bucket), 2))
    return averaged


async def async_fetch_history(
    hass: HomeAssistant, entity_id: str, hours: int
) -> list[float]:
    """Return up to HISTORY_POINTS numeric states from the last hours."""
    if "recorder" not in hass.config.components:
        return []
    start = dt_util.utcnow() - timedelta(hours=hours)
    states = await get_instance(hass).async_add_executor_job(
        partial(
            history.state_changes_during_period,
            hass,
            start,
            None,
            entity_id,
            no_attributes=True,
        )
    )
    values = []
    for state in states.get(entity_id, []):
        try:
            number = float(state.state)
        except ValueError:
            continue
        if math.isfinite(number):
            values.append(number)
    return decimate(values, HISTORY_POINTS)


def _quiet_log(level: int, text: str) -> None:
    """Ignore render warnings from the template tracker."""


async def async_render_limited(hass: HomeAssistant, text: str, variables: dict) -> Any:
    """Render a Component template once; the sandbox bounds its cost."""
    return ComponentTemplate(text, hass).async_render(variables, parse_result=True)


async def async_fetch_action(hass: HomeAssistant, slot: dict) -> Any:
    """Run a read-only action slot and render its result template."""
    domain, _, service = slot["action"].partition(".")
    try:
        response = await hass.services.async_call(
            domain, service, slot["data"], blocking=True, return_response=True
        )
        return await async_render_limited(
            hass, slot["result"], {**slot["variables"], "response": response}
        )
    except Exception:  # a broken slot must not break the rest of the card
        return []


async def async_evaluate_slot(hass: HomeAssistant, slot: dict) -> Any:
    """Evaluate one slot once, raising TemplateError or HomeAssistantError."""
    if slot["kind"] == "template":
        return jsonable(
            await async_render_limited(hass, slot["template"], slot["variables"])
        )
    if slot["kind"] == "history":
        return jsonable(await async_fetch_history(hass, slot["entity"], slot["hours"]))
    return jsonable(await async_fetch_action(hass, slot))


class _SwitchedOff:
    """Remember one switched-off slot and the listeners waiting for it."""

    def __init__(self, slot: dict, message: str, cancel: Callable[[], None]) -> None:
        """Store the slot, the message and the canceller of the expiry timer."""
        self.slot = slot
        self.message = message
        self.cancel = cancel
        self.listeners: dict[object, Callable[[Any], None]] = {}


class SlotHub:
    """Share one template tracker per identical slot between all card subscriptions."""

    def __init__(self, hass: HomeAssistant, library: Library) -> None:
        """Store the context and listen for library reloads."""
        self.hass = hass
        self._slots: dict[str, _SharedSlot] = {}
        # Keyed like _slots, by template and variables: the same template
        # with another entity is another slot and stays on.
        self._switched_off: dict[str, _SwitchedOff] = {}
        self._remove_listener: Callable[[], None] | None = library.async_listen(
            self.async_reset
        )

    @callback
    def async_subscribe(
        self, slot: dict, listener: Callable[[Any], None]
    ) -> Callable[[], None]:
        """Register a listener for one slot and return its remover."""
        key = json.dumps(
            [slot["template"], slot["variables"]], sort_keys=True, default=str
        )
        token = object()

        @callback
        def remove() -> None:
            """Unregister the listener; calling it twice is harmless."""
            self._remove(key, token)

        if (record := self._switched_off.get(key)) is not None:
            # The slot stays off until it expires or the library reloads;
            # the listener waits in the record and is served again then.
            record.listeners[token] = listener
            listener(limit_error(record.message))
            return remove
        shared = self._slots.get(key)
        created = shared is None
        if created:
            shared = _SharedSlot(self, key, slot)
            self._slots[key] = shared
        shared.listeners[token] = listener
        if created:
            # The first render reaches the listeners before start returns.
            shared.start()
        elif shared.has_result:
            listener(shared.result)
        return remove

    @callback
    def _remove(self, key: str, token: object) -> None:
        """Drop one listener from its slot or from a switched-off record."""
        shared = self._slots.get(key)
        if shared is not None and token in shared.listeners:
            shared.remove_listener(token)
        elif (record := self._switched_off.get(key)) is not None:
            record.listeners.pop(token, None)

    @callback
    def _slot_switched_off(self, shared: _SharedSlot, message: str) -> None:
        """Record a switch-off, tell the listeners and stop the tracker."""
        key = shared.key
        current = self._slots.get(key)
        if key in self._switched_off or (current is not None and current is not shared):
            # Already recorded, or a newer slot replaced this one and is
            # judged by its own renders.
            return
        record = _SwitchedOff(
            shared.slot,
            message,
            async_call_later(self.hass, SWITCH_OFF_SECONDS, partial(self._expire, key)),
        )
        self._switched_off[key] = record
        if current is None:
            # Every listener left before the switch-off was reported.
            return
        del self._slots[key]
        shared.stop()
        record.listeners = shared.listeners
        error = limit_error(message)
        for listener in list(record.listeners.values()):
            listener(error)

    @callback
    def _expire(self, key: str, now: datetime) -> None:
        """Give a switched-off slot a fresh start for the cards still open."""
        record = self._switched_off.pop(key)
        if not record.listeners:
            return
        shared = _SharedSlot(self, key, record.slot)
        shared.listeners = record.listeners
        self._slots[key] = shared
        shared.start()

    @callback
    def async_reset(self) -> None:
        """Clear the switched-off records so edited Components start fresh."""
        # Every card subscribes again after a library change, which removes
        # the listeners that waited in the records.
        for record in self._switched_off.values():
            record.cancel()
        self._switched_off.clear()

    @callback
    def async_stop(self) -> None:
        """Remove the library listener and stop every shared slot."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        for shared in self._slots.values():
            shared.stop()
        self._slots.clear()
        self.async_reset()

    def __len__(self) -> int:
        """Return the number of shared slots currently tracked."""
        return len(self._slots)


class _SharedSlot:
    """Track one template for every listener of an identical slot."""

    def __init__(self, hub: SlotHub, key: str, slot: dict) -> None:
        """Build the template and store the shared state."""
        self._hub = hub
        self.key = key
        self.slot = slot
        self.template = ComponentTemplate(slot["template"], hub.hass)
        self.template.on_switched_off = self._on_switched_off
        self.variables = slot["variables"]
        self.listeners: dict[object, Callable[[Any], None]] = {}
        self.has_result = False
        self.result: Any = None
        self._remove: Callable[[], None] | None = None

    def start(self) -> None:
        """Start the tracker and deliver the first result."""
        # No rate_limit: it never applies to entities the template names
        # directly, and it would shorten the built-in all-states limit.
        try:
            info = async_track_template_result(
                self._hub.hass,
                [TrackTemplate(self.template, self.variables)],
                self._updated,
                log_fn=_quiet_log,
            )
        except TemplateError as err:
            self._deliver(err)
            return
        self._remove = info.async_remove
        info.async_refresh()

    @callback
    def _updated(self, event: Event | None, updates: list[TrackTemplateResult]) -> None:
        """Deliver every fresh result to the listeners."""
        for update in updates:
            self._deliver(update.result)

    def _deliver(self, result: Any) -> None:
        """Store the result and pass it to every listener."""
        self.result = result
        self.has_result = True
        for listener in list(self.listeners.values()):
            listener(result)

    @callback
    def _on_switched_off(self, message: str) -> None:
        """Hand the switch-off to the hub, which records it for this slot."""
        self._hub._slot_switched_off(self, message)

    def remove_listener(self, token: object) -> None:
        """Drop one listener and stop tracking when the last one leaves."""
        self.listeners.pop(token, None)
        if self.listeners:
            return
        self.stop()
        if self._hub._slots.get(self.key) is self:
            del self._hub._slots[self.key]

    def stop(self) -> None:
        """Remove the tracker, at most once."""
        if self._remove is not None:
            self._remove()
            self._remove = None


class CallError(HomeAssistantError):
    """A card failure with the websocket error code from the API."""

    def __init__(self, code: str, message: str) -> None:
        """Store the code next to the message."""
        super().__init__(message)
        self.code = code


def _param_entities(component: dict, params: dict) -> list[str]:
    """Return every entity id among the validated params."""
    entities: list[str] = []
    for name, definition in component.get("params", {}).items():
        if definition.get("kind") != "entity":
            continue
        value = params.get(name)
        if isinstance(value, str):
            entities.append(value)
        elif isinstance(value, list):
            entities.extend(item for item in value if isinstance(item, str))
    return entities


def _error_text(err: Exception) -> str:
    """Format an exception, unwrapping a wrapped cause when present."""
    shown = err.__cause__ if err.__cause__ is not None else err
    return f"{type(shown).__name__}: {shown}"


def _compile_card(
    data: ApolloTabData,
    connection: ActiveConnection,
    card_config: dict,
    dashboard: str | None,
) -> tuple[dict, dict, dict, dict, dict]:
    """Validate and compile a card for this connection.

    Raises CallError with the websocket error code from the API.
    """
    component_id = card_config.get("component")
    # A list or mapping here cannot be looked up at all.
    component = (
        data.library.components.get(component_id)
        if isinstance(component_id, str)
        else None
    )
    if component is None:
        raise CallError("unknown_component", f"Unknown component '{component_id}'")
    if not data.library.is_approved(component_id):
        raise CallError("needs_approval", f"Component '{component_id}' is not approved")
    try:
        card = validate_card_config(component, card_config)
    except MakerError as err:
        raise CallError("invalid_card", str(err)) from err
    if card["columns"] == "full":
        card["columns"] = 12
    for entity_id in _param_entities(component, card["params"]):
        if not connection.user.permissions.check_entity(entity_id, POLICY_READ):
            raise CallError("unauthorized", f"Not allowed to read {entity_id}")
    try:
        compiled = compile_card(component, card)
    except MakerError as err:
        raise CallError(err.code, str(err)) from err
    themes = data.library.themes
    dashboard_theme_id = data.manager.theme_for(dashboard)
    theme = themes.get(dashboard_theme_id, {})
    element_theme = themes.get(card["style"].get("theme", dashboard_theme_id), theme)
    style = resolve_style(element_theme, card["style"], theme.get("wall", ""))
    return component, card, compiled, theme, style


class CardSubscription:
    """Push a card's compiled form and live values to one connection."""

    def __init__(
        self,
        hass: HomeAssistant,
        data: ApolloTabData,
        connection: ActiveConnection,
        msg: dict,
    ) -> None:
        """Store the context and listen for library and dashboard changes."""
        self.hass = hass
        self.data = data
        self.connection = connection
        self.msg = msg
        self._generation = 0
        self._stopped = False
        self._trackers: list[Callable[[], None]] = []
        self._listeners: list[Callable[[], None]] = [
            data.library.async_listen(self._on_library_change),
            data.manager.async_listen(self._on_manager_change),
        ]
        self._values: dict[int, Any] = {}
        self._errors: dict[int, str] = {}
        self._sent_values: dict[int, Any] = {}
        self._sent_errors: dict[int, str] = {}
        self._first_sent = False
        self._flush_scheduled = False
        data.subscriptions.add(self)

    async def async_start(self) -> None:
        """Send init and the first values, or an error event."""
        if self._stopped:
            return
        self._generation += 1
        generation = self._generation
        self._values = {}
        self._errors = {}
        self._sent_values = {}
        self._sent_errors = {}
        self._first_sent = False
        try:
            _component, _card, compiled, theme, style = _compile_card(
                self.data,
                self.connection,
                self.msg["card"],
                self.msg.get("dashboard"),
            )
        except CallError as err:
            self._send({"type": "error", "code": err.code, "message": str(err)})
            return
        self._send(
            {
                "type": "init",
                "card": json_safe(public_card(compiled)),
                "theme": json_safe(theme),
                "style": json_safe(style),
            }
        )
        await self._async_track_slots(generation, compiled)

    @callback
    def async_stop(self) -> None:
        """Remove every tracker and listener, at most once."""
        if self._stopped:
            return
        self._stopped = True
        self._generation += 1
        self._stop_tracking()
        for remove in self._listeners:
            remove()
        self._listeners.clear()
        self.data.subscriptions.discard(self)

    @callback
    def async_unload(self) -> None:
        """Stop the subscription and tell the card the integration is gone."""
        if self._stopped:
            return
        self.async_stop()
        self._send(
            {
                "type": "error",
                "code": "not_loaded",
                "message": "The integration is not loaded",
            }
        )

    async def _async_track_slots(self, generation: int, compiled: dict) -> None:
        """Start tracking every slot and send the first values event."""
        first_fetches = []
        for slot in compiled.get("slots", []):
            if slot["kind"] == "template":
                self._trackers.append(
                    self.data.slot_hub.async_subscribe(
                        slot, partial(self._on_template_result, generation, slot["n"])
                    )
                )
                continue
            first_fetches.append(self._async_fetch_slot(generation, slot))
            seconds = (
                slot["refresh"] if slot["kind"] == "action" else HISTORY_REFRESH_SECONDS
            )
            self._trackers.append(
                async_track_time_interval(
                    self.hass,
                    partial(self._async_refresh_slot, generation, slot),
                    timedelta(seconds=seconds),
                )
            )
        if first_fetches:
            await asyncio.gather(*first_fetches)
        self._send_first_values(generation)

    @callback
    def _on_template_result(self, generation: int, number: int, result: Any) -> None:
        """Record a template slot's result and push the change."""
        if generation != self._generation:
            return
        if isinstance(result, Exception):
            self._record_error(number, result)
        else:
            self._record_value(number, result)
        if self._first_sent and not self._flush_scheduled:
            # Each slot has its own tracker; one state change notifies them
            # one after another, so send their results in one values event.
            self._flush_scheduled = True
            self.hass.loop.call_soon(self._scheduled_flush)

    @callback
    def _scheduled_flush(self) -> None:
        """Send the template results gathered during one loop iteration."""
        self._flush_scheduled = False
        if not self._stopped:
            self._flush(self._generation)

    async def _async_fetch_slot(self, generation: int, slot: dict) -> None:
        """Fetch one history or action slot and record the outcome."""
        try:
            if slot["kind"] == "history":
                result: Any = await async_fetch_history(
                    self.hass, slot["entity"], slot["hours"]
                )
            else:
                result = await async_fetch_action(self.hass, slot)
        except HomeAssistantError as err:
            result = err
        if generation != self._generation:
            return
        if isinstance(result, Exception):
            self._record_error(slot["n"], result)
        else:
            self._record_value(slot["n"], result)
        self._flush(generation)

    async def _async_refresh_slot(
        self, generation: int, slot: dict, now: datetime
    ) -> None:
        """Fetch one slot again when its interval fires."""
        await self._async_fetch_slot(generation, slot)

    def _record_value(self, number: int, result: Any) -> None:
        """Store a slot's value and clear its error."""
        self._errors.pop(number, None)
        self._values[number] = jsonable(result)

    def _record_error(self, number: int, err: Exception) -> None:
        """Store a slot's error and drop its value."""
        self._values.pop(number, None)
        self._errors[number] = _error_text(err)

    def _send_first_values(self, generation: int) -> None:
        """Send the values event that holds every slot."""
        if generation != self._generation:
            return
        self._first_sent = True
        self._sent_values = dict(self._values)
        self._sent_errors = dict(self._errors)
        self._send(self._payload(self._values, self._errors))

    def _flush(self, generation: int) -> None:
        """Send the slots that changed since the last values event."""
        if generation != self._generation or not self._first_sent:
            return
        values = {
            number: value
            for number, value in self._values.items()
            if number not in self._sent_values or self._sent_values[number] != value
        }
        errors = {
            number: text
            for number, text in self._errors.items()
            if self._sent_errors.get(number) != text
        }
        if not values and not errors:
            return
        self._sent_values = dict(self._values)
        self._sent_errors = dict(self._errors)
        self._send(self._payload(values, errors))

    @staticmethod
    def _payload(values: dict[int, Any], errors: dict[int, str]) -> dict:
        """Build a values event with the slot numbers as strings."""
        return {
            "type": "values",
            "values": {str(number): value for number, value in values.items()},
            "errors": {str(number): text for number, text in errors.items()},
        }

    @callback
    def _send(self, payload: dict) -> None:
        """Send one event message to the subscriber."""
        self.connection.send_message(
            websocket_api.event_message(self.msg["id"], payload)
        )

    @callback
    def _on_library_change(self) -> None:
        """Subscribe again after a library reload or approval change."""
        self._restart()

    @callback
    def _on_manager_change(self, kind: str, url_path: str) -> None:
        """Subscribe again when this card's dashboard is converted."""
        if kind == "converted" and url_path == self.msg.get("dashboard"):
            self._restart()

    @callback
    def _restart(self) -> None:
        """Stop tracking and run the subscribe steps again."""
        if self._stopped:
            return
        self._stop_tracking()
        self._generation += 1
        self.hass.async_create_task(self.async_start())

    def _stop_tracking(self) -> None:
        """Remove every slot tracker."""
        for remove in self._trackers:
            remove()
        self._trackers.clear()


def _checked_change_value(widget: dict, value: Any) -> int | float:
    """Validate a change value against the widget's range."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CallError("invalid_value", "A change event needs a number")
    low = widget.get("min")
    if isinstance(low, int | float) and not isinstance(low, bool) and value < low:
        raise CallError("invalid_value", f"{value} is below {low}")
    high = widget.get("max")
    if isinstance(high, int | float) and not isinstance(high, bool) and value > high:
        raise CallError("invalid_value", f"{value} is above {high}")
    return value


def _render_data(hass: HomeAssistant, data: dict, variables: dict) -> dict:
    """Render the template strings in an output's service data."""
    rendered = {}
    for key, item in data.items():
        if isinstance(item, str) and ("{{" in item or "{%" in item):
            try:
                # Limited templates cannot read states, so an output cannot
                # leak another entity's state into the service call.
                item = ComponentTemplate(item, hass).async_render(
                    variables, parse_result=True, limited=True
                )
            except TemplateError as err:
                raise CallError("service_error", str(err)) from err
        rendered[key] = item
    return rendered


def _needs_confirmation(
    hass: HomeAssistant, output: dict, domain: str, entity_id: str
) -> bool:
    """Return whether running this output asks for a confirmation."""
    if output.get("feedback") == "confirm" or domain in SENSITIVE_DOMAINS:
        return True
    if domain != "cover":
        return False
    state = hass.states.get(entity_id)
    return (
        state is not None
        and state.attributes.get("device_class") in CONFIRM_COVER_CLASSES
    )


async def async_call_output(
    hass: HomeAssistant,
    data: ApolloTabData,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Run a card's output. Raises CallError(code, message)."""
    component, card, compiled, _theme, _style = _compile_card(
        data, connection, msg["card"], msg.get("dashboard")
    )
    if compiled["demo"]:
        raise CallError("demo", "Example cards cannot call services")
    widget = next(
        (item for item in compiled["widgets"] if item["i"] == msg["widget"]), None
    )
    if widget is None:
        raise CallError("unknown_widget", f"Unknown widget {msg['widget']}")
    action_ref = compiled["actions"].get(f"{msg['widget']}:{msg['event']}")
    if action_ref is None:
        # The compiler records action outputs only, so a local tap has no entry.
        if msg["event"] == "tap" and "local" in widget.get("tap", {}):
            raise CallError("local_action", "Local outputs run in the browser")
        raise CallError(
            "unknown_widget",
            f"Widget {msg['widget']} has no {msg['event']} action",
        )
    output = component["outputs"][action_ref["output"]]
    # The library checks actions when it loads a file; check again here so a
    # card can never reach a service outside the allow lists, such as a
    # script.<name> service that runs a script the user did not pick.
    if not is_allowed_action(output["action"]):
        raise CallError("not_allowed", f"{output['action']} is not allowed")
    if msg["event"] == "change":
        value = _checked_change_value(widget, msg.get("value"))
    else:
        value = None
    variables = {**card["params"], **action_ref["vars"], "value": value}
    service_data = _render_data(hass, output["data"], variables)
    # Rendered data may not widen the call beyond the picked entity.
    if target_keys := TARGET_KEYS & service_data.keys():
        raise CallError(
            "not_allowed",
            f"Output data may not target {', '.join(sorted(target_keys))}",
        )
    domain, _, service = output["action"].partition(".")
    entity_id = service_data.get("entity_id")
    if (
        not isinstance(entity_id, str)
        or entity_id not in compiled["entities"]
        or entity_id.partition(".")[0] != domain
    ):
        raise CallError(
            "not_allowed", f"{entity_id} is not a {domain} entity of this card"
        )
    if not msg["confirmed"] and _needs_confirmation(hass, output, domain, entity_id):
        raise CallError("confirm_required", f"{output['action']} needs a confirmation")
    try:
        await hass.services.async_call(
            domain,
            service,
            service_data,
            blocking=True,
            context=connection.context(msg),
        )
    except Unauthorized as err:
        raise CallError("unauthorized", str(err)) from err
    except (HomeAssistantError, probatio.Invalid, ValueError) as err:
        raise CallError("service_error", str(err)) from err
