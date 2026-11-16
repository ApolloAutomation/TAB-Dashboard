"""Collect, keep and watch what the devices of the dashboards can do.

maker/features.py turns what Home Assistant knows of an entity into facts.
This module reads that input (the entity registry entry first, then the
state) and keeps the facts the saved dashboards were converted with:

- They are stored, so the first conversion after a restart gives the hash
  the tablet already holds while a device is still away.
- Only the conversion of a saved dashboard writes them, never the editor's
  `card/facts`, `card/subscribe` or a preview.
- A change of a fact that a card of a dashboard names converts that
  dashboard again, after QUIET_S of quiet and at most once in MIN_GAP_S.
- A device whose facts keep changing is held still: after HOLD_CHANGES
  changes in HOLD_WINDOW_S its last facts are kept for an hour, then for
  six, and a repair note names it.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from enum import IntFlag
from functools import partial
from typing import Any

from homeassistant.components.alarm_control_panel.const import (
    AlarmControlPanelEntityFeature,
)
from homeassistant.components.climate.const import ClimateEntityFeature
from homeassistant.components.cover.const import CoverEntityFeature
from homeassistant.components.fan.const import FanEntityFeature
from homeassistant.components.light.const import LightEntityFeature
from homeassistant.components.lock.const import LockEntityFeature
from homeassistant.components.media_player.const import MediaPlayerEntityFeature
from homeassistant.components.vacuum.const import VacuumEntityFeature
from homeassistant.const import ATTR_FRIENDLY_NAME, STATE_UNAVAILABLE
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_entity_registry_updated_event,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .maker.features import facts_of, project

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
STORE_KEY = f"{DOMAIN}.facts"
SAVE_DELAY_S = 10
# The store holds at most this many devices and this many bytes of JSON.
MAX_STORED = 500
MAX_STORED_BYTES = 1_000_000

# A dashboard is converted again after this much quiet ...
QUIET_S = 10.0
# ... and at most once in this time.
MIN_GAP_S = 60.0
# This many changes of named facts within HOLD_WINDOW_S hold a device.
HOLD_CHANGES = 3
HOLD_WINDOW_S = 3600.0
HOLD_FIRST_S = 3600.0
HOLD_LATER_S = 6 * 3600.0

HELD_ISSUE = "facts_held"

# The feature enum of each domain; bits are read through these, never as
# numbers.
_FEATURE_ENUMS: dict[str, type[IntFlag]] = {
    "alarm_control_panel": AlarmControlPanelEntityFeature,
    "climate": ClimateEntityFeature,
    "cover": CoverEntityFeature,
    "fan": FanEntityFeature,
    "light": LightEntityFeature,
    "lock": LockEntityFeature,
    "media_player": MediaPlayerEntityFeature,
    "vacuum": VacuumEntityFeature,
}


def held_issue_id(entity_id: str) -> str:
    """Return the repair note's id for a held device."""
    return f"{HELD_ISSUE}_{entity_id}"


def _feature_names(domain: str, bits: object) -> list[str]:
    """Return the names of the domain's feature flags that bits holds."""
    flags = _FEATURE_ENUMS.get(domain)
    if flags is None or isinstance(bits, bool) or not isinstance(bits, int):
        return []
    try:
        present = flags(bits)
    except ValueError:
        return []
    return sorted(member.name for member in flags if member.name and member in present)


def _plain(value: Any, depth: int = 0) -> Any:
    """Return a copy of registry or state data made of plain JSON types."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, str):
        return str.__str__(value)
    if isinstance(value, int | float):
        return value
    if depth >= 3:
        return None
    if isinstance(value, Mapping):
        return {
            str(key): _plain(item, depth + 1)
            for key, item in value.items()
            if isinstance(key, str)
        }
    if isinstance(value, list | tuple | set | frozenset):
        return [_plain(item, depth + 1) for item in value]
    return None


def raw_of(hass: HomeAssistant, entity_id: str) -> dict:
    """Return what Home Assistant knows of an entity, as features.py reads it."""
    domain = entity_id.split(".", 1)[0]
    raw: dict[str, Any] = {"domain": domain, "registry": None, "state": None}
    entry = er.async_get(hass).async_get(entity_id)
    if entry is not None:
        raw["registry"] = {
            "capabilities": _plain(dict(entry.capabilities or {})),
            "features": _feature_names(domain, entry.supported_features),
            "device_class": entry.device_class or entry.original_device_class,
            "icon": entry.icon or entry.original_icon,
            "unit": entry.unit_of_measurement,
        }
    state = hass.states.get(entity_id)
    if state is not None:
        attributes = dict(state.attributes)
        raw["state"] = {
            "attributes": _plain(attributes),
            "features": _feature_names(domain, attributes.get("supported_features")),
        }
    return raw


def _entry_print(raw: Mapping) -> str:
    """Return a short print of the registry part of what is known of an entity."""
    text = json.dumps(raw.get("registry"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def live_facts(hass: HomeAssistant, entity_id: str) -> dict:
    """Return an entity's facts as Home Assistant reports them now."""
    return facts_of(raw_of(hass, entity_id))


def _known(hass: HomeAssistant, entity_id: str) -> bool:
    """Return True when the entity's state is there and not unavailable."""
    state = hass.states.get(entity_id)
    return state is not None and state.state != STATE_UNAVAILABLE


class FactKeeper:
    """Keep the facts the saved dashboards use, and watch them change."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise an empty keeper; async_load reads the store."""
        self._hass = hass
        self._store: Store[dict] = Store(hass, STORE_VERSION, STORE_KEY)
        # Seconds on a steady clock.
        self.clock: Callable[[], float] = hass.loop.time
        # Facts each saved dashboard was converted with, per device, and a
        # print of the registry entry they were made with.
        self.stored: dict[str, dict] = {}
        self._entries: dict[str, str] = {}
        self._dashboards: dict[str, dict] = {}
        self._seen: dict[str, dict] = {}
        self._changes: dict[str, list[float]] = {}
        self._held: dict[str, dict] = {}
        self._was_held: set[str] = set()
        self._timers: dict[str, CALLBACK_TYPE] = {}
        self._next_allowed: dict[str, float] = {}
        self._watched: frozenset[str] = frozenset()
        self._unsubscribers: list[CALLBACK_TYPE] = []
        self._listeners: list[Callable[[str], None]] = []
        self._dirty = False

    async def async_load(self) -> None:
        """Read the stored facts."""
        data = await self._store.async_load()
        if not isinstance(data, dict):
            return
        facts = data.get("facts")
        entries = data.get("entries")
        if not isinstance(facts, dict) or not isinstance(entries, dict):
            return
        for entity_id, value in facts.items():
            entry = entries.get(entity_id)
            if isinstance(value, dict) and isinstance(entry, str):
                self.stored[entity_id] = value
                self._entries[entity_id] = entry

    @callback
    def async_listen(self, listener: Callable[[str], None]) -> Callable[[], None]:
        """Run listener(url_path) when a dashboard must be converted again."""
        self._listeners.append(listener)

        def _remove() -> None:
            """Remove the listener."""
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    # ------------------------------------------------------------ reading

    def facts_for(self, entity_ids: Iterable[str]) -> dict[str, dict]:
        """Return the facts a conversion uses now for each entity.

        A held device gives its held facts. A device that is away gives
        the facts it was last converted with, when there are any. This
        reads only; nothing is stored.
        """
        return {entity_id: self._current(entity_id) for entity_id in entity_ids}

    def _current(self, entity_id: str) -> dict:
        """Return the facts of one entity, the hold first."""
        held = self._held.get(entity_id)
        if held is not None:
            return held["facts"]
        return self._observed(entity_id)

    def _observed(self, entity_id: str) -> dict:
        """Return the live facts, or the stored ones while the device is away.

        Stored facts stand only while the registry entry is the one they
        were made with: an entry that fills while the device is away (one
        just added) gives its new facts.
        """
        raw = raw_of(self._hass, entity_id)
        if (
            entity_id in self.stored
            and not _known(self._hass, entity_id)
            and self._entries.get(entity_id) == _entry_print(raw)
        ):
            return self.stored[entity_id]
        return facts_of(raw)

    def is_held(self, entity_id: str) -> bool:
        """Return True while a device's facts are held still."""
        return entity_id in self._held

    # ------------------------------------------------------------ writing

    @callback
    def async_converted(
        self, url_path: str, named: Mapping[str, frozenset], used: Mapping[str, dict]
    ) -> None:
        """Note a saved dashboard's conversion: what it names and what it used.

        This is the only writer of the store.
        """
        self._dashboards[url_path] = {
            "named": {entity_id: frozenset(n) for entity_id, n in named.items() if n},
            "used": {entity_id: dict(facts) for entity_id, facts in used.items()},
        }
        for entity_id, facts in used.items():
            self._seen.setdefault(entity_id, dict(facts))
            entry = _entry_print(raw_of(self._hass, entity_id))
            if (
                self.stored.get(entity_id) != facts
                or self._entries.get(entity_id) != entry
            ):
                self.stored[entity_id] = dict(facts)
                self._entries[entity_id] = entry
                self._dirty = True
        self._async_watch()
        if self._dirty:
            self._async_save()

    @callback
    def async_forget(self, url_path: str) -> None:
        """Forget a dashboard that is gone, and the devices only it used."""
        if self._dashboards.pop(url_path, None) is None:
            return
        self._cancel_timer(url_path)
        self._next_allowed.pop(url_path, None)
        self.async_prune()

    @callback
    def async_prune(self) -> None:
        """Drop stored devices that no saved dashboard uses."""
        used = self._used_entities()
        for entity_id in list(self.stored):
            if entity_id not in used:
                del self.stored[entity_id]
                self._entries.pop(entity_id, None)
                self._dirty = True
        for entity_id in list(self._seen):
            if entity_id not in used:
                del self._seen[entity_id]
        self._async_watch()
        if self._dirty:
            self._async_save()

    def _used_entities(self) -> set[str]:
        """Return every device a saved dashboard uses."""
        used: set[str] = set()
        for dashboard in self._dashboards.values():
            used.update(dashboard["used"])
        return used

    def _data(self) -> dict:
        """Return the store's data within its caps."""
        self._dirty = False
        facts: dict[str, dict] = {}
        entries: dict[str, str] = {}
        size = 0
        for entity_id in sorted(self.stored):
            if len(facts) >= MAX_STORED:
                break
            value = self.stored[entity_id]
            cost = len(json.dumps(value, ensure_ascii=False)) + 2 * len(entity_id) + 40
            if size + cost > MAX_STORED_BYTES:
                continue
            facts[entity_id] = value
            entries[entity_id] = self._entries[entity_id]
            size += cost
        return {"facts": facts, "entries": entries}

    @callback
    def _async_save(self) -> None:
        """Save the store after SAVE_DELAY_S."""
        self._store.async_delay_save(self._data, SAVE_DELAY_S)

    async def async_flush(self) -> None:
        """Write a pending save at once."""
        if self._dirty:
            await self._store.async_save(self._data())

    # ------------------------------------------------------------ watching

    def _names(self, entity_id: str) -> set[str]:
        """Return every fact of a device that a dashboard names."""
        names: set[str] = set()
        for dashboard in self._dashboards.values():
            names.update(dashboard["named"].get(entity_id, ()))
        return names

    @callback
    def _async_watch(self) -> None:
        """Follow the state and registry entry of every named device."""
        watched = frozenset(
            entity_id
            for dashboard in self._dashboards.values()
            for entity_id in dashboard["named"]
        )
        if watched == self._watched:
            return
        self._unwatch()
        self._watched = watched
        if not watched:
            return
        entity_ids = sorted(watched)
        self._unsubscribers.append(
            async_track_state_change_event(self._hass, entity_ids, self._handle_event)
        )
        self._unsubscribers.append(
            async_track_entity_registry_updated_event(
                self._hass, entity_ids, self._handle_event
            )
        )

    def _unwatch(self) -> None:
        """Stop following devices."""
        while self._unsubscribers:
            self._unsubscribers.pop()()

    @callback
    def _handle_event(self, event: Event) -> None:
        """Look at a device again after its state or registry entry changed."""
        entity_id = event.data.get("entity_id")
        if not isinstance(entity_id, str) or entity_id in self._held:
            return
        if entity_id not in self._watched:
            return
        self._async_check(entity_id, self._observed(entity_id))

    @callback
    def _async_check(self, entity_id: str, new: dict) -> None:
        """Count a change of named facts, hold the device or convert again."""
        names = self._names(entity_id)
        old = self._seen.get(entity_id)
        if old is not None and project(new, names) == project(old, names):
            self._seen[entity_id] = new
            return
        now = self.clock()
        times = [t for t in self._changes.get(entity_id, []) if now - t < HOLD_WINDOW_S]
        times.append(now)
        if len(times) >= HOLD_CHANGES and old is not None:
            self._changes.pop(entity_id, None)
            self._async_hold(entity_id, old)
            return
        self._changes[entity_id] = times
        self._seen[entity_id] = new
        for url_path, dashboard in self._dashboards.items():
            named = dashboard["named"].get(entity_id)
            if not named:
                continue
            if project(new, named) != project(dashboard["used"].get(entity_id), named):
                self._async_schedule(url_path)

    @callback
    def _async_hold(self, entity_id: str, facts: dict) -> None:
        """Keep a device's last facts still and raise the repair note."""
        hours = HOLD_LATER_S if entity_id in self._was_held else HOLD_FIRST_S
        self._was_held.add(entity_id)
        cancel = async_call_later(
            self._hass, hours, partial(self._async_release_later, entity_id)
        )
        self._held[entity_id] = {"facts": facts, "cancel": cancel}
        _LOGGER.warning(
            "%s keeps changing what it can do; its dashboards keep its last "
            "abilities for %d hours",
            entity_id,
            hours // 3600,
        )
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            held_issue_id(entity_id),
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=HELD_ISSUE,
            translation_placeholders={
                "device": self._device_name(entity_id),
                "entity_id": entity_id,
                "hours": str(int(hours // 3600)),
            },
        )

    @callback
    def _async_release_later(self, entity_id: str, _now: Any) -> None:
        """End a hold when its time is up."""
        self._async_release(entity_id)

    @callback
    def _async_release(self, entity_id: str) -> None:
        """End a hold and look at the device again."""
        held = self._held.pop(entity_id, None)
        if held is None:
            return
        ir.async_delete_issue(self._hass, DOMAIN, held_issue_id(entity_id))
        self._seen[entity_id] = held["facts"]
        if entity_id in self._watched:
            self._async_check(entity_id, self._observed(entity_id))

    def _device_name(self, entity_id: str) -> str:
        """Return the name of the device of an entity, for the repair note."""
        entry = er.async_get(self._hass).async_get(entity_id)
        if entry is not None and entry.device_id is not None:
            device = dr.async_get(self._hass).async_get(entry.device_id)
            if device is not None and (device.name_by_user or device.name):
                return str(device.name_by_user or device.name)
        state = self._hass.states.get(entity_id)
        if state is not None and isinstance(
            name := state.attributes.get(ATTR_FRIENDLY_NAME), str
        ):
            return name
        return entity_id

    @callback
    def _async_schedule(self, url_path: str) -> None:
        """Convert a dashboard again after QUIET_S of quiet, MIN_GAP_S apart."""
        self._cancel_timer(url_path)
        delay = max(QUIET_S, self._next_allowed.get(url_path, 0.0) - self.clock())
        self._timers[url_path] = async_call_later(
            self._hass, delay, partial(self._async_fire, url_path)
        )

    def _cancel_timer(self, url_path: str) -> None:
        """Cancel a dashboard's waiting conversion."""
        cancel = self._timers.pop(url_path, None)
        if cancel is not None:
            cancel()

    @callback
    def _async_fire(self, url_path: str, _now: Any = None) -> None:
        """Ask for the dashboard's conversion."""
        self._timers.pop(url_path, None)
        if url_path not in self._dashboards:
            return
        self._next_allowed[url_path] = self.clock() + MIN_GAP_S
        for listener in list(self._listeners):
            listener(url_path)

    @callback
    def async_stop(self) -> None:
        """Stop watching, cancel the timers and end every hold."""
        self._unwatch()
        self._watched = frozenset()
        for url_path in list(self._timers):
            self._cancel_timer(url_path)
        for entity_id, held in list(self._held.items()):
            held["cancel"]()
            ir.async_delete_issue(self._hass, DOMAIN, held_issue_id(entity_id))
        self._held.clear()
