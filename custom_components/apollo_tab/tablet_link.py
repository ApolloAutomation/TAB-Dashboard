"""How the sender reaches tablets: the ESPHome connection, or a fake.

``EsphomeTabletLink`` is the only code in this integration that touches the
ESPHome integration's internals. It keeps no ``runtime_data`` and no client:
ESPHome makes new ones on every entry setup and reloads the entry on key
provisioning, reauth and address changes. Both are looked up from the
config entry on every use.

Calls go straight to the ESPHome client, not through Home Assistant's
service registry, so neither layouts nor values end up in the recorder.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from collections.abc import Callable
from contextlib import suppress
from functools import partial
from typing import Any, Protocol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Link states of one tablet.
LINK_OFFLINE = "offline"  # ESPHome entry not loaded, or not connected
LINK_CHECKING = "checking"  # connected; looking for the engine's actions
LINK_READY = "ready"  # connected and tab_hello is there
LINK_NO_ENGINE = "no_engine"  # connected, no tab_hello
LINK_UNSUPPORTED = "unsupported"  # ESPHome internals are not as expected

CALL_TIMEOUT = 10
# Seconds after a connection at which the action list is checked.
CHECK_AT = (0.2, 1.0, 3.0)

# How each action answers: True data, False status only, None nothing.
RESPONSE_MODES: dict[str, bool | None] = {
    "tab_hello": True,
    "tab_status": True,
    "tab_pair": False,
    "tab_layout": False,
    "tab_commit": False,
    "tab_set": False,
    "tab_clear": False,
    "tab_ack": None,
}

ISSUE_ID = "esphome_internals"

type LinkListener = Callable[[str, str], None]


class LinkError(HomeAssistantError):
    """A call that did not succeed.

    code is a contract error code or one of offline, no_engine, timeout,
    ha_version, bad_response, failed. The sender adds no_session: a call it
    did not send because it had no session to sign it with.
    """

    def __init__(self, code: str) -> None:
        """Store the code."""
        super().__init__(code)
        self.code = code


class TabletLink:
    """The interface the sender talks to. Tablets are keyed by registry MAC."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Store hass; the listener is set by the sender."""
        self.hass = hass
        self._listener: LinkListener | None = None

    @callback
    def async_set_listener(self, listener: LinkListener | None) -> None:
        """Set the function told about every state change: listener(mac, state).

        Every change into LINK_READY is a new connection: the sender drops
        its session and greets the tablet.
        """
        self._listener = listener

    def _notify(self, mac: str, state: str) -> None:
        """Tell the listener."""
        if self._listener is not None:
            self._listener(mac, state)

    @callback
    def async_watch(self, mac: str, entry_id: str) -> None:
        """Start following one tablet's ESPHome entry."""
        raise NotImplementedError

    @callback
    def async_unwatch(self, mac: str) -> None:
        """Stop following a tablet."""
        raise NotImplementedError

    def state(self, mac: str) -> str:
        """Return the tablet's link state."""
        raise NotImplementedError

    async def async_call(
        self, mac: str, action: str, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Call one action and return its data. Raises LinkError."""
        raise NotImplementedError

    def api_key(self, mac: str) -> bytes | None:
        """Return the tablet's 32-byte API encryption key, or None."""
        raise NotImplementedError

    def encryption_supported(self, mac: str) -> bool:
        """Return whether the tablet's software can take an API key.

        False only when the tablet says it cannot (built without
        encryption); True when it can or when that is not known yet.
        """
        raise NotImplementedError

    @callback
    def async_recheck(self, mac: str) -> None:
        """Read the tablet's action list again (after a knock or a timeout)."""
        raise NotImplementedError

    @callback
    def async_stop(self) -> None:
        """Stop following every tablet."""
        raise NotImplementedError


class _Watch:
    """What the ESPHome link follows for one tablet."""

    def __init__(self, mac: str, entry_id: str) -> None:
        """Start offline."""
        self.mac = mac
        self.entry_id = entry_id
        self.state = LINK_OFFLINE
        self.remove_state: CALLBACK_TYPE | None = None
        self.remove_device: CALLBACK_TYPE | None = None
        self.cancel_checks: list[CALLBACK_TYPE] = []
        self.checks_left = 0


def _decode_key(value: Any) -> bytes | None:
    """Return the 32 bytes of a base64 noise_psk, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        key = base64.b64decode(value, validate=True)
    except binascii.Error, ValueError:
        return None
    return key if len(key) == 32 else None


def _has_internals(runtime_data: Any) -> bool:
    """Return whether ESPHome's runtime data has everything the link uses."""
    client = getattr(runtime_data, "client", None)
    return (
        runtime_data is not None
        and hasattr(runtime_data, "available")
        and isinstance(getattr(runtime_data, "services", None), dict)
        and callable(getattr(runtime_data, "async_subscribe_device_updated", None))
        and callable(getattr(client, "execute_service", None))
    )


class EsphomeTabletLink(TabletLink):
    """Reach tablets through the ESPHome integration's API client."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Start with nothing watched."""
        super().__init__(hass)
        self._watches: dict[str, _Watch] = {}

    # ---------------------------------------------------------- watching

    @callback
    def async_watch(self, mac: str, entry_id: str) -> None:
        """Follow the ESPHome entry of a tablet: its state and its device."""
        current = self._watches.get(mac)
        if current is not None and current.entry_id == entry_id:
            return
        if current is not None:
            self.async_unwatch(mac)
        watch = _Watch(mac, entry_id)
        self._watches[mac] = watch
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is not None:
            watch.remove_state = entry.async_on_state_change(
                lambda: self._entry_changed(mac)
            )
        self._entry_changed(mac)

    @callback
    def async_unwatch(self, mac: str) -> None:
        """Stop following a tablet."""
        watch = self._watches.pop(mac, None)
        if watch is None:
            return
        self._drop_device(watch)
        if watch.remove_state is not None:
            with suppress(ValueError):
                watch.remove_state()
            watch.remove_state = None

    @callback
    def async_stop(self) -> None:
        """Stop following every tablet."""
        for mac in list(self._watches):
            self.async_unwatch(mac)
        self._listener = None

    def state(self, mac: str) -> str:
        """Return the tablet's link state."""
        watch = self._watches.get(mac)
        return watch.state if watch else LINK_OFFLINE

    def _runtime_data(self, watch: _Watch) -> Any:
        """Return the loaded entry's runtime data, or None. Never kept."""
        entry = self.hass.config_entries.async_get_entry(watch.entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            return None
        return getattr(entry, "runtime_data", None)

    def _set_state(self, watch: _Watch, state: str) -> None:
        """Change the state and tell the sender."""
        if watch.state == state:
            return
        watch.state = state
        if state == LINK_UNSUPPORTED:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_ID,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_ID,
            )
        self._notify(watch.mac, state)

    def _drop_device(self, watch: _Watch) -> None:
        """Stop the device subscription and any pending check."""
        for cancel in watch.cancel_checks:
            cancel()
        watch.cancel_checks.clear()
        watch.checks_left = 0
        if watch.remove_device is not None:
            # The set can belong to runtime data that is gone already.
            with suppress(KeyError, ValueError):
                watch.remove_device()
            watch.remove_device = None

    @callback
    def _entry_changed(self, mac: str) -> None:
        """Follow the ESPHome entry: subscribe on load, go offline otherwise."""
        watch = self._watches.get(mac)
        if watch is None:
            return
        entry = self.hass.config_entries.async_get_entry(watch.entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            self._drop_device(watch)
            self._set_state(watch, LINK_OFFLINE)
            return
        runtime_data = getattr(entry, "runtime_data", None)
        if not _has_internals(runtime_data):
            self._drop_device(watch)
            _LOGGER.warning(
                "The ESPHome integration of this Home Assistant version cannot be "
                "used to reach TAB-1 tablets"
            )
            self._set_state(watch, LINK_UNSUPPORTED)
            return
        ir.async_delete_issue(self.hass, DOMAIN, ISSUE_ID)
        if watch.remove_device is None:
            # Every load has new runtime data, so subscribe again.
            watch.remove_device = runtime_data.async_subscribe_device_updated(
                lambda: self._device_updated(mac)
            )
        self._device_updated(mac)

    @callback
    def _device_updated(self, mac: str) -> None:
        """Look for the engine when connected; go offline when not."""
        watch = self._watches.get(mac)
        if watch is None:
            return
        runtime_data = self._runtime_data(watch)
        if runtime_data is None or not runtime_data.available:
            for cancel in watch.cancel_checks:
                cancel()
            watch.cancel_checks.clear()
            watch.checks_left = 0
            self._set_state(watch, LINK_OFFLINE)
            return
        if watch.state in (LINK_READY, LINK_NO_ENGINE) or watch.checks_left:
            # Same connection; nothing new.
            return
        self._set_state(watch, LINK_CHECKING)
        self._start_checks(watch)

    def _start_checks(self, watch: _Watch) -> None:
        """Look for tab_hello after 0.2 s, 1 s and 3 s.

        ESPHome tells about the connection before it has the device's real
        action list, and fills the list from its store until then.
        """
        for cancel in watch.cancel_checks:
            cancel()
        # A callback job: a plain function would run in a worker thread,
        # and everything the check sets off belongs on the event loop.
        job = HassJob(partial(self._check_later, watch.mac), "apollo_tab check")
        watch.cancel_checks = [
            async_call_later(self.hass, delay, job) for delay in CHECK_AT
        ]
        watch.checks_left = len(CHECK_AT)

    @callback
    def _check_later(self, mac: str, _now: Any) -> None:
        """Run one scheduled check (async_call_later passes the time)."""
        self._check(mac)

    @callback
    def _check(self, mac: str) -> None:
        """One scheduled look at the action list."""
        watch = self._watches.get(mac)
        if watch is None or not watch.checks_left:
            return
        watch.checks_left -= 1
        runtime_data = self._runtime_data(watch)
        if runtime_data is None or not runtime_data.available:
            return
        if self._find(runtime_data, "tab_hello") is not None:
            for cancel in watch.cancel_checks:
                cancel()
            watch.cancel_checks.clear()
            watch.checks_left = 0
            self._set_state(watch, LINK_READY)
        elif not watch.checks_left:
            watch.cancel_checks.clear()
            self._set_state(watch, LINK_NO_ENGINE)

    @callback
    def async_recheck(self, mac: str) -> None:
        """Read the action list again. Gone: no_engine. There: ready."""
        watch = self._watches.get(mac)
        if watch is None:
            return
        runtime_data = self._runtime_data(watch)
        if runtime_data is None or not _has_internals(runtime_data):
            return
        if not runtime_data.available:
            self._set_state(watch, LINK_OFFLINE)
            return
        found = self._find(runtime_data, "tab_hello") is not None
        if watch.checks_left and not found:
            # The scheduled checks are still running.
            return
        self._set_state(watch, LINK_READY if found else LINK_NO_ENGINE)

    @staticmethod
    def _find(runtime_data: Any, name: str) -> Any:
        """Return the device action with this name, or None."""
        for service in list(runtime_data.services.values()):
            if getattr(service, "name", None) == name:
                return service
        return None

    # ------------------------------------------------------------- calls

    def api_key(self, mac: str) -> bytes | None:
        """Return the API encryption key from the ESPHome entry, read fresh."""
        watch = self._watches.get(mac)
        if watch is None:
            return None
        entry = self.hass.config_entries.async_get_entry(watch.entry_id)
        if entry is None:
            return None
        return _decode_key(entry.data.get("noise_psk"))

    def encryption_supported(self, mac: str) -> bool:
        """Return False only when the connected tablet says it takes no key.

        ESPHome gives a key to every tablet that can take one and has none,
        then connects again with it (its dynamic encryption key).
        """
        watch = self._watches.get(mac)
        runtime_data = self._runtime_data(watch) if watch is not None else None
        device_info = getattr(runtime_data, "device_info", None)
        return getattr(device_info, "api_encryption_supported", True) is not False

    async def async_call(
        self, mac: str, action: str, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Call one tab_* action through the ESPHome client."""
        watch = self._watches.get(mac)
        if watch is None:
            raise LinkError("offline")
        runtime_data = self._runtime_data(watch)
        if runtime_data is None:
            raise LinkError("offline")
        if not _has_internals(runtime_data):
            raise LinkError("ha_version")
        if not runtime_data.available:
            raise LinkError("offline")
        service = self._find(runtime_data, action)
        if service is None:
            raise LinkError("no_engine")
        mode = RESPONSE_MODES[action]
        client = runtime_data.client
        try:
            if mode is None:
                await client.execute_service(service, args)
                return None
            response = await client.execute_service(
                service, args, return_response=mode, timeout=CALL_TIMEOUT
            )
        except TimeoutError as err:
            self.hass.loop.call_soon(self.async_recheck, mac)
            raise LinkError("timeout") from err
        except Exception as err:
            # aioesphomeapi raises its own connection errors.
            _LOGGER.debug("Call %s to %s failed: %s", action, mac, type(err).__name__)
            raise LinkError("offline") from err
        if response is None:
            raise LinkError("timeout")
        if not getattr(response, "success", False):
            raise LinkError(str(getattr(response, "error_message", "")) or "failed")
        if not mode:
            return {}
        try:
            data = json.loads(getattr(response, "response_data", b"") or b"{}")
        except ValueError as err:
            raise LinkError("bad_response") from err
        if not isinstance(data, dict):
            raise LinkError("bad_response")
        return data


class SimulatedTablet(Protocol):
    """What MemoryTabletLink needs from a simulated tablet."""

    connected: bool
    has_engine: bool
    psk: bytes | None
    encryption_supported: bool

    async def async_call(
        self, action: str, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handle one call; raise LinkError(code) for an error answer."""


class MemoryTabletLink(TabletLink):
    """Reach simulated tablets held in memory. Used by the tests."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Start with no tablets."""
        super().__init__(hass)
        self.tablets: dict[str, SimulatedTablet] = {}
        self.watched: dict[str, str] = {}
        self._states: dict[str, str] = {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    @callback
    def async_add(self, mac: str, tablet: SimulatedTablet) -> None:
        """Plug in a simulated tablet."""
        self.tablets[mac] = tablet
        self.async_refresh(mac)

    @callback
    def async_refresh(self, mac: str) -> None:
        """Work out the state again after the tablet changed."""
        if mac not in self.watched:
            return
        tablet = self.tablets.get(mac)
        if tablet is None or not tablet.connected:
            state = LINK_OFFLINE
        elif not tablet.has_engine:
            state = LINK_NO_ENGINE
        else:
            state = LINK_READY
        if self._states.get(mac) != state:
            self._states[mac] = state
            self._notify(mac, state)

    @callback
    def async_reconnect(self, mac: str) -> None:
        """Simulate a dropped and new connection (or an ESPHome reload)."""
        if mac not in self.watched:
            return
        self._states[mac] = LINK_OFFLINE
        self._notify(mac, LINK_OFFLINE)
        self.async_refresh(mac)

    @callback
    def async_watch(self, mac: str, entry_id: str) -> None:
        """Follow a tablet."""
        self.watched[mac] = entry_id
        self.async_refresh(mac)

    @callback
    def async_unwatch(self, mac: str) -> None:
        """Stop following a tablet."""
        self.watched.pop(mac, None)
        self._states.pop(mac, None)

    @callback
    def async_stop(self) -> None:
        """Stop following every tablet."""
        self.watched.clear()
        self._states.clear()
        self._listener = None

    def state(self, mac: str) -> str:
        """Return the tablet's state."""
        return self._states.get(mac, LINK_OFFLINE)

    def api_key(self, mac: str) -> bytes | None:
        """Return the simulated tablet's API key."""
        tablet = self.tablets.get(mac)
        return tablet.psk if tablet is not None else None

    def encryption_supported(self, mac: str) -> bool:
        """Return whether the simulated tablet can take an API key."""
        return getattr(self.tablets.get(mac), "encryption_supported", True) is not False

    @callback
    def async_recheck(self, mac: str) -> None:
        """Work out the state again."""
        self.async_refresh(mac)

    async def async_call(
        self, mac: str, action: str, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Hand the call to the simulated tablet."""
        tablet = self.tablets.get(mac)
        if mac not in self.watched or tablet is None or not tablet.connected:
            raise LinkError("offline")
        if not tablet.has_engine:
            raise LinkError("no_engine")
        self.calls.append((mac, action, dict(args)))
        return await tablet.async_call(action, args)
