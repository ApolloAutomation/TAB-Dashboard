"""Live card values: subscriptions, history, actions and calls."""

import asyncio
import json
import math
from collections.abc import Callable, Collection
from datetime import datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any

import probatio
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.components.recorder import history, statistics
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, TemplateError, Unauthorized
from homeassistant.helpers.event import (
    TrackTemplate,
    TrackTemplateResult,
    async_call_later,
    async_track_state_change_event,
    async_track_template_result,
    async_track_time_interval,
)
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .maker import outputs as out2
from .maker.compile import compile_card, public_card
from .maker.const import (
    COLOUR_DATA_KEYS,
    CONFIRM_COVER_CLASSES,
    SENSITIVE_DOMAINS,
    TARGET_KEYS,
)
from .maker.errors import MakerError
from .maker.schema import is_allowed_action, validate_card_config
from .maker.schema2 import check_option_value
from .maker.style import resolve_style
from .sandbox import ComponentTemplate, limit_error
from .sources import (
    CLOCK_RESEND_S,
    SOURCE_KINDS,
    position_key,
    source_value,
)

if TYPE_CHECKING:
    from . import ApolloTabData
    from .library import Library

HISTORY_POINTS = 120
HISTORY_REFRESH_SECONDS = 300
# A statistics input is read again no sooner than this (C.2.8). Its timer
# runs a little slower, so each tick finds the shared value due.
STATISTICS_MIN_AGE_S = 300
STATISTICS_REFRESH_SECONDS = STATISTICS_MIN_AGE_S + 10
# Inputs whose value Home Assistant fetches instead of tracking. In a
# schema 2 card they may feed a template as well as a field (C.2.8).
FETCHED_KINDS = frozenset({"history", "action", "statistics"})
MAX_SHARED_FETCHES = 256
_SHARED_FETCHES = f"{DOMAIN}_shared_fetches"
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


class SharedFetches:
    """Share fetched values between slots, so many readers make one call.

    A value is kept with the moment it was fetched and is handed out again
    while it is younger than the age the caller allows. Two callers that
    ask at the same time wait for the same call. A call that fails is not
    kept.
    """

    def __init__(self) -> None:
        """Start empty."""
        self._values: dict[str, tuple[datetime, Any]] = {}
        self._running: dict[str, asyncio.Task] = {}

    async def async_get(
        self, key: str, max_age_s: float, fetch: Callable[[], Any]
    ) -> Any:
        """Return the kept value for key, or fetch it once for every caller."""
        kept = self._values.get(key)
        if kept is not None and dt_util.utcnow() - kept[0] < timedelta(
            seconds=max_age_s
        ):
            return kept[1]
        task = self._running.get(key)
        if task is None:
            task = asyncio.get_running_loop().create_task(self._async_run(key, fetch))
            self._running[key] = task
        # A caller that is cancelled must not cancel the call of the others.
        return await asyncio.shield(task)

    async def _async_run(self, key: str, fetch: Callable[[], Any]) -> Any:
        """Run one fetch and keep its value."""
        try:
            value = await fetch()
        finally:
            self._running.pop(key, None)
        self._values.pop(key, None)
        self._values[key] = (dt_util.utcnow(), value)
        while len(self._values) > MAX_SHARED_FETCHES:
            # The oldest value goes first.
            del self._values[next(iter(self._values))]
        return value

    def __len__(self) -> int:
        """Return the number of kept values."""
        return len(self._values)


def shared_fetches(hass: HomeAssistant) -> SharedFetches:
    """Return the fetches every card and tablet of this Home Assistant share."""
    shared = hass.data.get(_SHARED_FETCHES)
    if shared is None:
        shared = hass.data[_SHARED_FETCHES] = SharedFetches()
    return shared


def _fetch_key(*parts: Any) -> str:
    """Return the key of a shared fetch."""
    return json.dumps(parts, sort_keys=True, default=str)


async def async_fetch_action(hass: HomeAssistant, slot: dict) -> Any:
    """Run a read-only action slot and render its result template.

    Slots with the same action and data share one call (C.2.8): the copies
    of a loop each render their own result from the one response. A kept
    response is used for half the slot's refresh time, so each slot's own
    timer still finds it due.
    """
    domain, _, service = slot["action"].partition(".")
    try:
        response = await shared_fetches(hass).async_get(
            _fetch_key("action", slot["action"], slot["data"]),
            slot["refresh"] / 2,
            partial(
                hass.services.async_call,
                domain,
                service,
                slot["data"],
                blocking=True,
                return_response=True,
            ),
        )
        return await async_render_limited(
            hass, slot["result"], {**slot["variables"], "response": response}
        )
    except Exception:  # a broken slot must not break the rest of the card
        return []


def _statistic_number(value: Any) -> float | None:
    """Return a finite statistic, or None."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def hour_buckets(
    rows: list[dict], current: Any, kind: str, now: datetime
) -> list[float]:
    """Return one number per local hour of today, up to the hour that runs now.

    rows are the recorder's hourly rows (start as a UTC timestamp), current
    is the value of the hour that runs now. Hours still to come are left
    out (C.2.8). Two rows of one local hour (the hour that repeats when the
    clocks go back) are joined: means are averaged, changes added. An hour
    without a row takes 0 for a change and the hour before for a mean (the
    first known hour for the hours before it). Without any value the list
    is empty.
    """
    count = dt_util.as_local(now).hour + 1
    found: dict[int, list[float]] = {}
    for row in rows:
        start = row.get("start")
        number = _statistic_number(row.get(kind))
        if not isinstance(start, int | float) or number is None:
            continue
        hour = dt_util.as_local(dt_util.utc_from_timestamp(start)).hour
        if hour < count:
            found.setdefault(hour, []).append(number)
    if (number := _statistic_number(current)) is not None:
        found.setdefault(count - 1, []).append(number)
    if not found:
        return []
    joined = {
        hour: (sum(values) if kind == "change" else sum(values) / len(values))
        for hour, values in found.items()
    }
    if kind == "change":
        return [round(joined.get(hour, 0.0), 2) for hour in range(count)]
    last = joined[min(joined)]
    out = []
    for hour in range(count):
        last = joined.get(hour, last)
        out.append(round(last, 2))
    return out


async def _async_read_statistics(hass: HomeAssistant, slot: dict) -> Any:
    """Read one statistics slot from the recorder (in its executor)."""
    instance = get_instance(hass)
    entity = slot["entity"]
    now = dt_util.utcnow()
    if slot.get("buckets") != "hour":
        stat = slot["stat"]
        result = await instance.async_add_executor_job(
            statistics.statistic_during_period,
            hass,
            now - timedelta(hours=slot["hours"]),
            None,
            entity,
            {stat},
            None,
        )
        return _statistic_number(result.get(stat))
    kind = "change" if slot["stat"] == "sum" else "mean"
    midnight = dt_util.as_utc(dt_util.start_of_local_day())
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    rows = await instance.async_add_executor_job(
        statistics.statistics_during_period,
        hass,
        midnight,
        hour_start,
        {entity},
        "hour",
        None,
        {kind},
    )
    current = await instance.async_add_executor_job(
        statistics.statistic_during_period,
        hass,
        max(hour_start, midnight),
        None,
        entity,
        {kind},
        None,
    )
    return hour_buckets(rows.get(entity, []), current.get(kind), kind, now)


async def async_fetch_statistics(hass: HomeAssistant, slot: dict) -> Any:
    """Return a statistics slot's value: one number, or a number per hour.

    From the recorder's statistics, read again no sooner than every
    STATISTICS_MIN_AGE_S for every card and tablet together. Without the
    recorder, or for an entity without statistics: None, or an empty list.
    """
    listed = slot.get("buckets") == "hour"
    empty: Any = [] if listed else None
    if "recorder" not in hass.config.components:
        return empty
    key = _fetch_key(
        "statistics",
        {k: v for k, v in slot.items() if k in ("entity", "stat", "hours", "buckets")},
    )
    try:
        return await shared_fetches(hass).async_get(
            key, STATISTICS_MIN_AGE_S, partial(_async_read_statistics, hass, slot)
        )
    except Exception:  # a broken slot must not break the rest of the card
        return empty


async def async_fetch_value(hass: HomeAssistant, slot: dict) -> Any:
    """Fetch one history, action or statistics slot."""
    if slot["kind"] == "history":
        return await async_fetch_history(hass, slot["entity"], slot["hours"])
    if slot["kind"] == "statistics":
        return await async_fetch_statistics(hass, slot)
    return await async_fetch_action(hass, slot)


def fetch_interval(slot: dict) -> float:
    """Return how often a fetched slot is fetched again, in seconds."""
    if slot["kind"] == "action":
        return slot["refresh"]
    if slot["kind"] == "statistics":
        return STATISTICS_REFRESH_SECONDS
    return HISTORY_REFRESH_SECONDS


async def async_feed_values(hass: HomeAssistant, feeds: dict) -> dict[str, Any]:
    """Return the value of each fetched input a template names (C.2.8).

    The values reach the template as variables: data, never template
    source. A fetch that fails gives None.
    """
    values: dict[str, Any] = {}
    for name, feed in feeds.items():
        try:
            values[name] = await async_fetch_value(hass, feed)
        except HomeAssistantError:
            values[name] = None
    return values


async def async_evaluate_slot(hass: HomeAssistant, slot: dict) -> Any:
    """Evaluate one slot once, raising TemplateError or HomeAssistantError."""
    if slot["kind"] == "template":
        variables = slot["variables"]
        if slot.get("inputs"):
            variables = {**variables, **await async_feed_values(hass, slot["inputs"])}
        return jsonable(await async_render_limited(hass, slot["template"], variables))
    if slot["kind"] not in FETCHED_KINDS:
        raise HomeAssistantError(f"no value for a {slot['kind']} slot yet")
    return jsonable(await async_fetch_value(hass, slot))


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
        self.hass.data.pop(_SHARED_FETCHES, None)

    def __len__(self) -> int:
        """Return the number of shared slots currently tracked."""
        return len(self._slots)

    def last_result(self, slot: dict) -> tuple[bool, Any]:
        """Return (True, value) when a tracked template slot has a value.

        The value is Home Assistant's own last result of that template, as
        every card and tablet that shows it got it.
        """
        key = json.dumps(
            [slot.get("template"), slot.get("variables")], sort_keys=True, default=str
        )
        shared = self._slots.get(key)
        if shared is None or not shared.has_result:
            return False, None
        if isinstance(shared.result, Exception):
            return True, None
        return True, shared.result


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


class SlotTracker:
    """Track a list of slots and report every fresh result.

    Template slots share their tracker through the SlotHub. History, action
    and statistics slots are fetched once at start and again on their
    interval; a template that names such inputs gets their values.
    on_result gets the slot and its value, or the exception it raised. Card
    subscriptions and tablet sessions both use it.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        slot_hub: SlotHub,
        slots: list[dict],
        on_result: Callable[[dict, Any], None],
    ) -> None:
        """Store the slots and the result callback."""
        self.hass = hass
        self._hub = slot_hub
        self._slots = slots
        self._on_result = on_result
        self._removers: list[Callable[[], None]] = []
        self._stopped = False

    async def async_start(self) -> None:
        """Subscribe every slot; return after the first results arrived."""
        first_fetches = []
        for slot in self._slots:
            if self._stopped:
                return
            if slot["kind"] == "template" and slot.get("inputs"):
                first_fetches.append(self._async_start_fed(slot))
                continue
            if slot["kind"] == "template":
                self._removers.append(
                    self._hub.async_subscribe(slot, partial(self._deliver, slot))
                )
                continue
            if slot["kind"] in SOURCE_KINDS:
                self._start_source(slot)
                continue
            if slot["kind"] not in FETCHED_KINDS:
                continue
            first_fetches.append(self._async_fetch(slot))
            self._removers.append(
                async_track_time_interval(
                    self.hass,
                    partial(self._async_refresh, slot),
                    timedelta(seconds=fetch_interval(slot)),
                )
            )
        if first_fetches:
            await asyncio.gather(*first_fetches)

    async def _async_start_fed(self, slot: dict) -> None:
        """Track a template that names fetched inputs (C.2.8).

        Each fetched input is fetched on its own interval. Once every one
        has a value, the template is tracked through the slot hub with the
        values among its variables; a changed value tracks it again with
        the new variables. The values are data, never template source.
        """
        feeds: dict = slot["inputs"]
        values: dict[str, Any] = {}
        current: dict[str, Any] = {"key": None, "remove": None}

        def track() -> None:
            """Track the template with the values fetched so far."""
            if self._stopped or len(values) < len(feeds):
                return
            variables = {**slot["variables"], **values}
            key = _fetch_key(variables)
            if key == current["key"]:
                return
            current["key"] = key
            if current["remove"] is not None:
                current["remove"]()
            fed = {
                "kind": "template",
                "template": slot["template"],
                "variables": variables,
            }
            current["remove"] = self._hub.async_subscribe(
                fed, partial(self._deliver, slot)
            )

        def untrack() -> None:
            """Stop tracking the template."""
            if current["remove"] is not None:
                current["remove"]()
                current["remove"] = None

        self._removers.append(untrack)

        async def fetch(name: str, feed: dict, _now: datetime | None = None) -> None:
            """Fetch one input and track the template again."""
            try:
                values[name] = await async_fetch_value(self.hass, feed)
            except HomeAssistantError:
                values[name] = None
            track()

        for name, feed in feeds.items():
            self._removers.append(
                async_track_time_interval(
                    self.hass,
                    partial(fetch, name, feed),
                    timedelta(seconds=fetch_interval(feed)),
                )
            )
        await asyncio.gather(*(fetch(name, feed) for name, feed in feeds.items()))

    def _start_source(self, slot: dict) -> None:
        """Follow a colour, state_icon, clock or media_position slot.

        clock is delivered at start and every CLOCK_RESEND_S. The others
        follow their entity; a position only when the player's state or its
        position changed, not at every attribute change.
        """
        self._deliver(slot, source_value(self.hass, slot))
        if slot["kind"] == "clock":

            @callback
            def tick(_now: datetime) -> None:
                """Deliver the clock again; on the event loop, not in a thread."""
                self._deliver(slot, source_value(self.hass, slot))

            self._removers.append(
                async_track_time_interval(
                    self.hass, tick, timedelta(seconds=CLOCK_RESEND_S)
                )
            )
            return
        entity = slot.get("entity")
        if not isinstance(entity, str):
            return
        last = [position_key(self.hass.states.get(entity))]

        @callback
        def changed(event: Event) -> None:
            """Deliver the source's value after a change of its entity."""
            if slot["kind"] == "media_position":
                key = position_key(event.data.get("new_state"))
                if key == last[0]:
                    return
                last[0] = key
            self._deliver(slot, source_value(self.hass, slot))

        self._removers.append(
            async_track_state_change_event(self.hass, [entity], changed)
        )

    @callback
    def async_stop(self) -> None:
        """Remove every tracker and timer, at most once."""
        self._stopped = True
        while self._removers:
            self._removers.pop()()

    @callback
    def _deliver(self, slot: dict, result: Any) -> None:
        """Pass one result on unless the tracker was stopped."""
        if not self._stopped:
            self._on_result(slot, result)

    async def _async_fetch(self, slot: dict) -> None:
        """Fetch one history, action or statistics slot and pass the outcome on."""
        try:
            result: Any = await async_fetch_value(self.hass, slot)
        except HomeAssistantError as err:
            result = err
        self._deliver(slot, result)

    async def _async_refresh(self, slot: dict, now: datetime) -> None:
        """Fetch one slot again when its interval fires."""
        await self._async_fetch(slot)


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
        tracker = SlotTracker(
            self.hass,
            self.data.slot_hub,
            compiled.get("slots", []),
            partial(self._on_slot_result, generation),
        )
        self._trackers.append(tracker.async_stop)
        await tracker.async_start()
        self._send_first_values(generation)

    @callback
    def _on_slot_result(self, generation: int, slot: dict, result: Any) -> None:
        """Record one slot's result and push the change."""
        if generation != self._generation:
            return
        if isinstance(result, Exception):
            self._record_error(slot["n"], result)
        else:
            self._record_value(slot["n"], result)
        if slot["kind"] != "template":
            self._flush(generation)
        elif self._first_sent and not self._flush_scheduled:
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


_COVER_VERBS = {
    "open_cover": "Open",
    "close_cover": "Close",
    "stop_cover": "Stop",
    "toggle": "Open or close",
}


def output_confirm_text(
    hass: HomeAssistant,
    component: dict,
    action_ref: dict,
    params: dict,
    entities: Collection[str],
) -> str | None:
    """Return the question a tablet asks before this output, or None.

    Only a garage, gate or door cover gets one, for example "Open Garage?".
    The tablet then asks before it sends, with no round trip. It is a help,
    not the guard: async_run_output still checks every call.
    """
    output = component.get("outputs", {}).get(action_ref.get("output"))
    if not isinstance(output, dict):
        return None
    if component.get("schema") == 2:
        return _confirm_text2(hass, output, action_ref, params, entities)
    domain, _, service = str(output.get("action", "")).partition(".")
    if domain != "cover":
        return None
    variables = {**params, **action_ref.get("vars", {}), "value": None}
    try:
        rendered = _render_data(hass, output.get("data") or {}, variables)
    except CallError:
        return None
    entity_id = rendered.get("entity_id")
    if not isinstance(entity_id, str) or entity_id not in entities:
        return None
    if not _needs_confirmation(hass, {}, domain, entity_id):
        return None
    state = hass.states.get(entity_id)
    name = state.name if state is not None else entity_id
    return f"{_COVER_VERBS.get(service, 'Move')} {name}?"


def cover_questions(
    hass: HomeAssistant, components: dict[str, dict], bindings: object
) -> dict[int, str]:
    """Return the questions for the widgets and cards that move a cover.

    Keyed by widget or card id, from a layout's bindings. The tablet asks
    them before it sends (cf), so a tap needs no round trip for HA's
    confirm answer; HA still checks every call. The sender writes them into
    the device layout, and the converter counts their bytes when it fits a
    layout to a tablet (C.4).
    """
    questions: dict[int, str] = {}
    actions = bindings.get("actions") if isinstance(bindings, dict) else None
    if not isinstance(actions, dict):
        return questions
    for key, action in actions.items():
        if not isinstance(action, dict) or action.get("demo"):
            continue
        component_id = action.get("component")
        component = (
            components.get(component_id) if isinstance(component_id, str) else None
        )
        widget_id, _, _event = str(key).partition(":")
        if component is None or not widget_id.isdigit():
            continue
        text = output_confirm_text(
            hass,
            component,
            action,
            action.get("params") or {},
            action.get("entities") or [],
        )
        if text:
            questions.setdefault(int(widget_id), text)
    return questions


def _confirm_text2(
    hass: HomeAssistant,
    output: dict,
    action_ref: dict,
    params: dict,
    entities: Collection[str],
) -> str | None:
    """Return the question of a schema 2 output: over every entity it could reach.

    Devices that an `entities` input gives are known only at the call,
    which asks for them.
    """
    if output.get("kind") != "action":
        return None
    ref = out2.reference(output.get("data", {}).get("entity_id"))
    if ref is None:
        return None
    found = out2.entity_list(
        out2.lookup({**params, **(action_ref.get("vars") or {})}, ref[0], None)
    )
    if found is None:
        return None
    for entity_id in found[0]:
        if entity_id not in entities:
            continue
        service = _service_for(output, entity_id)
        if service is None or not service.startswith("cover."):
            continue
        if not _needs_confirmation(hass, {}, "cover", entity_id):
            continue
        state = hass.states.get(entity_id)
        name = state.name if state is not None else entity_id
        verb = _COVER_VERBS.get(service.partition(".")[2], "Move")
        return f"{verb} {name}?"
    return None


def _service_for(output: dict, entity_id: str) -> str | None:
    """Return the service a schema 2 output calls for one entity, or None.

    The service must be of the entity's domain, in a per-kind map too: the
    loader checks the map's keys, and this checks again at the call.
    """
    domain = entity_id.partition(".")[0]
    if output.get("actions") is not None:
        service = output["actions"].get(domain)
    else:
        service = output.get("action")
    if not isinstance(service, str) or service.partition(".")[0] != domain:
        return None
    return service


_MISSING = object()


async def async_input_value(
    hass: HomeAssistant, slot_hub: SlotHub | None, slot: dict | None
) -> Any:
    """Return Home Assistant's own last value of an input (C.2.8, `uses`).

    From the slot hub when a card or a tablet tracks it, else worked out
    once now. Never from a browser's or a tablet's message. The result is
    left as it is (a list of entity ids stays a list); uses_value types it.
    """
    if not isinstance(slot, dict):
        return None
    kind = slot.get("kind")
    try:
        if kind == "template":
            if slot.get("inputs"):
                feeds = await async_feed_values(hass, slot["inputs"])
                slot = {**slot, "variables": {**slot["variables"], **feeds}}
            if slot_hub is not None:
                found, value = slot_hub.last_result(slot)
                if found:
                    return value
            return await async_render_limited(hass, slot["template"], slot["variables"])
        if kind in SOURCE_KINDS:
            return source_value(hass, slot)
        if kind in FETCHED_KINDS:
            return await async_evaluate_slot(hass, slot)
    except HomeAssistantError, TemplateError:
        return None
    return None


def _option_values(component: dict, stored: object) -> dict:
    """Check the options again when a call runs (C.2.3); a bad one takes its default."""
    stored = stored if isinstance(stored, dict) else {}
    values = {}
    for name, option in component.get("options", {}).items():
        if name not in stored:
            continue
        value = stored[name]
        if option.get("from"):
            # The device's list was checked when the layout was made; the
            # entries stay text.
            ok = (
                value is None
                or isinstance(value, str)
                or (isinstance(value, list) and all(isinstance(v, str) for v in value))
            )
            values[name] = value if ok else None
            continue
        try:
            values[name] = check_option_value(option, value, f"options.{name}")
        except MakerError, TypeError:
            values[name] = option.get("default")
    return values


def _typed_data_value(
    hass: HomeAssistant, raw: Any, variables: dict, uses_names: Collection[str]
) -> Any:
    """Type one data value of a schema 2 output (C.2.8, how a value gets its type)."""
    if not out2.is_template(raw):
        return raw
    ref = out2.reference(raw)
    if ref is not None:
        name, key, name_filter = ref
        return out2.apply_filter(out2.lookup(variables, name, key), name_filter)
    try:
        # Limited: a data template cannot read states (C.2.8).
        text = ComponentTemplate(raw, hass).async_render(
            variables, parse_result=False, limited=True
        )
    except TemplateError as err:
        raise CallError("service_error", str(err)) from err
    text = text if isinstance(text, str) else str(text)
    if text == "":
        return None
    typed = out2.typed_text(text)
    if isinstance(typed, str) and any(out2.mentions(n, raw) for n in uses_names):
        raise CallError("not_allowed", "An input in service data must give a number")
    return typed


def _render_data2(
    hass: HomeAssistant, data: dict, variables: dict, uses_names: Collection[str]
) -> dict:
    """Render and type the service data of a schema 2 output, all but entity_id."""
    rendered: dict = {}
    try:
        for key, raw in data.items():
            if key == "entity_id":
                continue
            if isinstance(raw, list):
                # Checked at load too: a list only for a colour key, 1 to 4.
                if key not in COLOUR_DATA_KEYS:
                    raise out2.NotAllowed(f"{key} may not hold a list")
                if not 1 <= len(raw) <= 4:
                    raise out2.NotAllowed(f"{key} must be a list of 1 to 4 numbers")
                rendered[key] = [
                    out2.colour_entry(
                        key, _typed_data_value(hass, entry, variables, uses_names)
                    )
                    for entry in raw
                ]
                continue
            value = out2.scalar_or_colour(
                key, _typed_data_value(hass, raw, variables, uses_names)
            )
            if value is out2.LEFT_OUT:
                continue
            if key in COLOUR_DATA_KEYS and not isinstance(value, list):
                # A template that prints a list is refused in schema 2.
                raise out2.NotAllowed(f"{key} must be a list of numbers")
            rendered[key] = value
    except out2.NotAllowed as err:
        raise CallError("not_allowed", str(err)) from err
    if target_keys := TARGET_KEYS & rendered.keys():
        raise CallError(
            "not_allowed",
            f"Output data may not target {', '.join(sorted(target_keys))}",
        )
    return rendered


async def _async_run_output2(
    hass: HomeAssistant,
    *,
    component: dict,
    output: dict,
    action_ref: dict,
    params: dict,
    entities: Collection[str],
    widget: dict,
    event: str,
    value: Any,
    confirmed: bool,
    context: Context,
    slot_hub: SlotHub | None,
) -> None:
    """Run one output of a schema 2 card (C.2.8, C.5). Raises CallError."""
    if output.get("kind") != "action":
        raise CallError("local_action", "Local outputs run on the screen")
    services = (
        list(output["actions"].values())
        if output.get("actions") is not None
        else [output.get("action") or ""]
    )
    for service in services:
        if not is_allowed_action(service):
            raise CallError("not_allowed", f"{service} is not allowed")
    option = None
    if event == "change" and widget.get("t") == "choice":
        options = action_ref.get("options")
        options = options if isinstance(options, list) else []
        if not out2.check_choice(value, len(options)):
            raise CallError("invalid_value", "No such option")
        value = int(value)
        # The server's own copy of the list; the tablet never names one.
        option = options[value]
    elif event == "change":
        value = _checked_change_value(widget, value)
    else:
        value = None
    stored = (
        action_ref.get("values") if isinstance(action_ref.get("values"), dict) else {}
    )
    variables: dict = {
        **params,
        **_option_values(component, stored.get("options")),
        "can": stored.get("can") if isinstance(stored.get("can"), dict) else {},
        **(action_ref.get("vars") or {}),
        "value": value,
        "option": option,
    }
    # Text from a template that names any input in uses is refused; an
    # entities input may not be in data at all (refused at load).
    uses_names = []
    uses = action_ref.get("uses") if isinstance(action_ref.get("uses"), dict) else {}
    for name, kind in (output.get("uses") or {}).items():
        entry = uses.get(name) if isinstance(uses.get(name), dict) else {}
        raw = await async_input_value(hass, slot_hub, entry.get("slot"))
        variables[name] = out2.uses_value(kind, raw)
        uses_names.append(name)
    # entity_id: one text or a list of 1 to 16, each one of the card's
    # devices and of the domain of the service it gets.
    ref = out2.reference(output["data"].get("entity_id"))
    found = out2.entity_list(out2.lookup(variables, ref[0], None)) if ref else None
    if found is None:
        raise CallError("not_allowed", "entity_id must name the card's devices")
    targets, as_list = found
    calls: dict[str, list[str]] = {}
    for entity_id in targets:
        if entity_id not in entities:
            raise CallError("not_allowed", f"{entity_id} is not a device of this card")
        service = _service_for(output, entity_id)
        if service is None:
            if output.get("actions") is not None:
                # A kind without an entry has no action (C.2.8).
                continue
            raise CallError("not_allowed", f"{entity_id} is not a {services[0]} entity")
        calls.setdefault(service, []).append(entity_id)
    if not calls:
        raise CallError("not_allowed", "No device of this card takes this action")
    service_data = _render_data2(hass, output["data"], variables, uses_names)
    if not confirmed:
        for service, ids in calls.items():
            for entity_id in ids:
                state = hass.states.get(entity_id)
                device_class = (
                    state.attributes.get("device_class") if state is not None else None
                )
                if out2.needs_question(
                    output.get("feedback"), service.partition(".")[0], device_class
                ):
                    raise CallError(
                        "confirm_required", f"{service} needs a confirmation"
                    )
    for service, ids in calls.items():
        domain, _, name = service.partition(".")
        try:
            await hass.services.async_call(
                domain,
                name,
                {**service_data, "entity_id": ids if as_list else ids[0]},
                blocking=True,
                context=context,
            )
        except Unauthorized as err:
            raise CallError("unauthorized", str(err)) from err
        except (HomeAssistantError, probatio.Invalid, ValueError) as err:
            raise CallError("service_error", str(err)) from err


async def async_run_output(
    hass: HomeAssistant,
    *,
    component: dict,
    action_ref: dict,
    params: dict,
    entities: Collection[str],
    widget: dict,
    event: str,
    value: Any,
    confirmed: bool,
    context: Context,
    slot_hub: SlotHub | None = None,
) -> None:
    """Run one output of a compiled card. Raises CallError(code, message).

    The connection-free core of a card call, used by the browser and by
    tablets. action_ref is the card's action entry ({"output", "vars"}),
    entities the entities the card was set up with, widget the widget that
    was used. slot_hub gives the last values of the inputs a schema 2
    output lists in `uses`.
    """
    output = component.get("outputs", {}).get(action_ref.get("output"))
    if output is None:
        raise CallError("unknown_widget", "The card has no such output")
    if component.get("schema") == 2:
        await _async_run_output2(
            hass,
            component=component,
            output=output,
            action_ref=action_ref,
            params=params,
            entities=entities,
            widget=widget,
            event=event,
            value=value,
            confirmed=confirmed,
            context=context,
            slot_hub=slot_hub,
        )
        return
    # The library checks actions when it loads a file; check again here so a
    # card can never reach a service outside the allow lists, such as a
    # script.<name> service that runs a script the user did not pick.
    if not is_allowed_action(output["action"]):
        raise CallError("not_allowed", f"{output['action']} is not allowed")
    value = _checked_change_value(widget, value) if event == "change" else None
    variables = {**params, **action_ref.get("vars", {}), "value": value}
    service_data = _render_data(hass, output["data"], variables)
    # Rendered data may not widen the call beyond the picked entity.
    if target_keys := TARGET_KEYS & service_data.keys():
        raise CallError(
            "not_allowed",
            f"Output data may not target {', '.join(sorted(target_keys))}",
        )
    # No rendered value is a list or a mapping (C.2.8), for schema 1 too:
    # only a text, a number, yes or no, or none goes out (no set, no bytes).
    for key, item in service_data.items():
        if key != "entity_id" and not (
            item is None or isinstance(item, str | int | float | bool)
        ):
            raise CallError("not_allowed", f"{key} may only hold a text or a number")
    domain, _, service = output["action"].partition(".")
    entity_id = service_data.get("entity_id")
    if (
        not isinstance(entity_id, str)
        or entity_id not in entities
        or entity_id.partition(".")[0] != domain
    ):
        raise CallError(
            "not_allowed", f"{entity_id} is not a {domain} entity of this card"
        )
    if not confirmed and _needs_confirmation(hass, output, domain, entity_id):
        raise CallError("confirm_required", f"{output['action']} needs a confirmation")
    try:
        await hass.services.async_call(
            domain,
            service,
            service_data,
            blocking=True,
            context=context,
        )
    except Unauthorized as err:
        raise CallError("unauthorized", str(err)) from err
    except (HomeAssistantError, probatio.Invalid, ValueError) as err:
        raise CallError("service_error", str(err)) from err


async def async_call_output(
    hass: HomeAssistant,
    data: ApolloTabData,
    connection: ActiveConnection,
    msg: dict,
) -> None:
    """Run a card's output for the browser. Raises CallError(code, message)."""
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
    await async_run_output(
        hass,
        component=component,
        action_ref=action_ref,
        params=card["params"],
        entities=compiled["entities"],
        widget=widget,
        event=msg["event"],
        value=msg.get("value"),
        confirmed=msg["confirmed"],
        context=connection.context(msg),
    )
