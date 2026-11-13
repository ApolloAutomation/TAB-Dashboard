"""Send each tablet its dashboard, keep its values live and run its taps.

One TabletSender for the integration and one TabletSession per tablet. The
sender talks to tablets only through a TabletLink, so the tests swap in
simulated tablets. The rules are the contract's (CONTRACT.md sections 3, 5,
7 and 8).
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections import Counter, deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.frontend import EVENT_PANELS_UPDATED
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
    Context,
    Event,
    HomeAssistant,
    callback,
)
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util.hass_dict import HassKey

from . import protocol as tp
from .assignments import STORE_KEY, STORE_VERSION, Assignments
from .const import DOMAIN, TABLET_MODEL
from .live import (
    CallError,
    SlotTracker,
    async_run_output,
    jsonable,
    output_confirm_text,
)
from .maker.device import (
    CHUNK_BYTES,
    ContractError,
    bindings_digest,
    coerce,
    compile_device_layout,
    icon_level,
)
from .tablet_link import (
    LINK_CHECKING,
    LINK_NO_ENGINE,
    LINK_OFFLINE,
    LINK_READY,
    LINK_UNSUPPORTED,
    EsphomeTabletLink,
    LinkError,
    TabletLink,
)
from .tablets import async_get_tablets

if TYPE_CHECKING:
    from .library import Library
    from .live import SlotHub
    from .manager import DashboardManager

_LOGGER = logging.getLogger(__name__)

# Status of a tablet (design 4.5). "new" wins over every other one: a tablet
# no admin approved yet, which HA does not talk to.
STATUS_NEW = "new"
STATUS_NO_DASHBOARD = "no_dashboard"
STATUS_OFFLINE = "offline"
STATUS_NO_ENGINE = "no_engine"
STATUS_UNSUPPORTED = "unsupported"
STATUS_SENDING = "sending"
STATUS_ON_TABLET = "on_tablet"
STATUS_FAILED = "failed"

# Whether taps work.
INPUT_OK = "ok"
INPUT_NEEDS_ENCRYPTION = "needs_encryption"
INPUT_NOT_PAIRED = "not_paired"

# States of the "Dashboard engine" sensor.
ENGINE_NOT_INSTALLED = "not_installed"
ENGINE_READY = "ready"
ENGINE_UPDATE_NEEDED = "update_needed"
ENGINE_STATES = [ENGINE_NOT_INSTALLED, ENGINE_READY, ENGINE_UPDATE_NEEDED]

# Failures that cannot succeed until the dashboard or the tablet changes.
NO_RETRY = tp.DETERMINISTIC_ERRORS | {"unreadable"}

# Timings in seconds. Module constants, so the tests can shorten them.
DEBOUNCE_S = 0.7
DEBOUNCE_MAX_S = 2.0
STATUS_POLL_S = (0.15, 0.3, 0.5)
STATUS_POLL_LIMIT_S = 20.0
VALUE_BATCH_S = 0.1
# A tab_set that timed out or failed is sent again after this wait.
SET_RETRY_S = 1.0
RETRY_S = (5, 15, 60, 300)
PAIR_EVERY_S = 60.0
KNOCK_EVERY_S = 2.0
STALE_SESSION_EVERY_S = 10.0
WARN_EVERY_S = 60.0
INPUTS_PER_SECOND = 10

EVENT_INPUT = "esphome.tab1_input"
EVENT_KNOCK = "esphome.tab1_hello"

SIGNAL_TABLETS_UPDATED = f"{DOMAIN}_tablets_updated"

# One repair issue per tablet that waits for an admin (design 4.2).
NEW_TABLET_ISSUE = "new_tablet"

# What Home Assistant waits for from an admin about a tablet's ESPHome
# entry, under Settings > Repairs ("Authentication expired for <entry
# title>"): to confirm that the tablet was erased (it came back without its
# key), or, at any other step, a key.
REAUTH_ERASED = "erased"
REAUTH_KEY = "key"
REAUTH_KINDS = (REAUTH_ERASED, REAUTH_KEY)
# ESPHome's step for a device that dropped its key (HA 2026.11 esphome
# config_flow.async_step_reauth_encryption_removed_confirm).
ESPHOME_ERASED_STEP = "reauth_encryption_removed_confirm"
# The Repairs issue Home Assistant opens with every ESPHome reauth flow and
# deletes with it (config_entries.ConfigEntry._async_init_reauth).
REAUTH_ISSUE_PREFIX = "config_entry_reauth_esphome_"

# Lets the tests reach simulated tablets instead of ESPHome.
LINK_FACTORY: HassKey[Callable[[HomeAssistant], TabletLink]] = HassKey(
    f"{DOMAIN}.link_factory"
)

# What a tablet hears when a tap cannot run (contract 7.3).
ACK_FOR_ERROR = {
    "confirm_required": tp.ACK_CONFIRM,
    "demo": tp.ACK_DENIED,
    "not_allowed": tp.ACK_DENIED,
    "needs_approval": tp.ACK_DENIED,
    "unknown_component": tp.ACK_DENIED,
    "unauthorized": tp.ACK_DENIED,
}


def new_tablet_issue_id(device_id: str) -> str:
    """Return the repair issue id of a waiting tablet, from its device id.

    Home Assistant puts every issue id into the diagnostics download, which
    people paste into public issues. So the id holds nothing worked out
    from the MAC: the device registry's id is random. A hash of the MAC
    would not do, because a tablet's default name ends in the last three
    MAC bytes, which leaves only 2^24 MACs to try.
    """
    return f"{NEW_TABLET_ISSUE}_{device_id}"


@callback
def _is_esphome_reauth_issue(data: ir.EventIssueRegistryUpdatedData) -> bool:
    """Return whether an issue registry change is an ESPHome reauth's issue."""
    return data["domain"] == HOMEASSISTANT_DOMAIN and data["issue_id"].startswith(
        REAUTH_ISSUE_PREFIX
    )


def create_link(hass: HomeAssistant) -> TabletLink:
    """Return the link to the tablets: ESPHome, unless a test set another."""
    factory = hass.data.get(LINK_FACTORY)
    return factory(hass) if factory is not None else EsphomeTabletLink(hass)


@dataclass
class Compiled:
    """One dashboard compiled for one tablet's caps."""

    url_path: str
    hash: str
    data: bytes
    plan: list[dict]
    bindings: dict
    layout: dict
    digest: str
    level: int


def _find_widget(layout: dict, widget_id: int) -> dict | None:
    """Return the widget of a layout v1 with this id, or None."""
    for page in layout.get("pages", []):
        for item in page.get("w", []):
            if item.get("id") == widget_id:
                return item
            for widget in item.get("w", []):
                if widget.get("id") == widget_id:
                    return widget
    return None


class _Live:
    """The live values of one layout on one tablet."""

    def __init__(self, session: TabletSession, compiled: Compiled) -> None:
        """Work out which source slot feeds which device slot."""
        self.session = session
        self.hash = compiled.hash
        self.digest = compiled.digest
        self.level = compiled.level
        self.by_source: dict[int, list[tuple[int, str]]] = {}
        for entry in compiled.plan:
            self.by_source.setdefault(entry["src"], []).append(
                (entry["d"], entry["type"])
            )
        self.wire: dict[int, Any] = {entry["d"]: None for entry in compiled.plan}
        # What the tablet holds; None until the first snapshot went out.
        self.sent: dict[int, Any] | None = None
        slots = [
            slot
            for slot in compiled.bindings.get("slots", [])
            if slot.get("n") in self.by_source
        ]
        sender = session.sender
        self.tracker = SlotTracker(sender.hass, sender.slot_hub, slots, self._on_result)

    @callback
    def _on_result(self, slot: dict, result: Any) -> None:
        """Convert one fresh source value for each device slot it feeds."""
        value = None if isinstance(result, Exception) else jsonable(result)
        icons = self.session.sender.icons
        for number, kind in self.by_source.get(slot["n"], []):
            try:
                self.wire[number] = coerce(kind, value, icons, self.level)
            except ContractError:
                self.wire[number] = None
        self.session.values_changed(self)

    def changes(self) -> dict[int, Any]:
        """Return the device slots whose value the tablet does not have."""
        if self.sent is None:
            return {}
        missing = object()
        return {
            number: value
            for number, value in self.wire.items()
            if self.sent.get(number, missing) != value
        }


class TabletSession:
    """Everything HA knows and does for one tablet."""

    def __init__(
        self, sender: TabletSender, mac: str, device_id: str, entry_id: str
    ) -> None:
        """Start offline with no session."""
        self.sender = sender
        self.hass = sender.hass
        self.mac = mac
        self.hex = tp.mac_hex(mac)
        self.device_id = device_id
        self.entry_id = entry_id
        self.link_state = LINK_OFFLINE
        # What the sender last concluded; status, reason and retry read
        # "new" instead while the tablet waits for an admin.
        self._status = STATUS_OFFLINE
        self._reason = ""
        self._retry = False
        self.engine = ""
        self.engine_state = ENGINE_NOT_INSTALLED
        # Whether engine_state comes from the tablet since HA started: a
        # handshake, or a connection without the engine's actions.
        self.engine_known = False
        self.input = INPUT_NOT_PAIRED
        self.tablet_kid = ""
        # Whether the last tab_hello said the tablet has an API key.
        self.enc = False
        # The session on the current connection.
        self.nonce: str | None = None
        self.n = 0
        self.boot: int | None = None
        self.last_counter = 0
        self.caps: dict[str, Any] = {}
        self.shown: str | None = None
        # A hash HA committed that the tablet may still be building: neither
        # confirmed on screen nor reported as ended. Kept across connections,
        # because the tablet keeps building while HA is away.
        self.staged: str | None = None
        # Set when the tablet tapped a layout HA did not expect on screen:
        # the next run reads tab_status before it trusts `shown`.
        self._check_shown = False
        self.want: Compiled | None = None
        self.kept: dict[str, Compiled] = {}
        self.live: _Live | None = None
        self.snapshot_needed = False
        self.dropped: Counter[str] = Counter()
        self.sending = False
        self.watching = False
        self._task: asyncio.Task | None = None
        self._dirty = False
        self._stopped = False
        self._lock = asyncio.Lock()
        self._compile_cache: tuple[Any, str, dict, Compiled] | None = None
        self._dead: tuple[str, str] | None = None
        self._retry_index = 0
        self._cancel_retry: Callable[[], None] | None = None
        self._debounce: asyncio.TimerHandle | None = None
        self._debounce_first: float | None = None
        self._flush_handle: asyncio.TimerHandle | None = None
        self._flushing = False
        self._last_pair = -math.inf
        self._force_pair = False
        self._pair_timer: Callable[[], None] | None = None
        self._last_knock = -math.inf
        self._last_stale_session = -math.inf
        self._last_warning = -math.inf
        self._inputs: deque[float] = deque()
        self._hash_errors = 0

    # -------------------------------------------------------------- state

    @property
    def approved(self) -> bool:
        """Return whether an admin approved this tablet under its current entry.

        Until then HA never talks to it and ignores everything it sends.
        """
        assignments = self.sender.assignments
        return (
            assignments.approved(self.mac)
            and assignments.entry_id(self.mac) == self.entry_id
        )

    @property
    def issue_id(self) -> str:
        """Return the id of the repair issue while the tablet waits."""
        return new_tablet_issue_id(self.device_id)

    @property
    def status(self) -> str:
        """Return the status; "new" for a tablet that waits for an admin."""
        return self._status if self.approved else STATUS_NEW

    @property
    def reason(self) -> str:
        """Return the reason that goes with the status."""
        return self._reason if self.approved else ""

    @property
    def retry(self) -> bool:
        """Return whether HA tries again after a failure."""
        return self._retry if self.approved else False

    @property
    def dashboard(self) -> str | None:
        """Return the assigned dashboard; None until an admin approved it."""
        return self.sender.assignments.dashboard(self.mac) if self.approved else None

    @property
    def paired(self) -> bool:
        """Return whether HA and the tablet hold the same secret."""
        if not self.approved:
            return False
        stored = self.sender.assignments.kid(self.mac)
        return bool(stored) and stored == self.tablet_kid

    def _now(self) -> float:
        """Return the loop clock."""
        return self.hass.loop.time()

    def _set_status(self, status: str, reason: str = "", retry: bool = False) -> None:
        """Change the status and tell everyone who follows the tablets."""
        if (self._status, self._reason, self._retry) == (status, reason, retry):
            return
        self._status, self._reason, self._retry = status, reason, retry
        self.sender.notify()

    def kick(self) -> None:
        """Bring the tablet to what it should show, now or after the current run."""
        if self._stopped:
            return
        self._dirty = True
        if self._task is None or self._task.done():
            # Not eager: the run starts after the caller's callback returns.
            self._task = self.hass.async_create_background_task(
                self._async_run(), f"{DOMAIN} tablet {self.hex}", eager_start=False
            )

    @property
    def running(self) -> bool:
        """Return whether a run is going on."""
        return self._task is not None and not self._task.done()

    def drop_session(self) -> None:
        """Forget the session and the value trackers (the connection ended)."""
        self.nonce = None
        self.n = 0
        self.last_counter = 0
        self._stop_live()

    @callback
    def async_stop(self) -> None:
        """Stop everything for this tablet."""
        self._stopped = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None
        for handle in (self._debounce, self._flush_handle):
            if handle is not None:
                handle.cancel()
        self._debounce = self._flush_handle = None
        for cancel in (self._cancel_retry, self._pair_timer):
            if cancel is not None:
                cancel()
        self._cancel_retry = self._pair_timer = None
        self._stop_live()

    def _forget(self) -> None:
        """Drop everything that came from trusting the tablet.

        For a tablet that waits for an admin: no session, no values, no
        bindings for its taps, no timers that would greet it again. What it
        shows and builds stays known, for when it is approved again.
        """
        self.drop_session()
        self.want = None
        self.kept = {}
        self.input = INPUT_NOT_PAIRED
        self.tablet_kid = ""
        self._force_pair = False
        self._check_shown = False
        self._dead = None
        for cancel in (self._cancel_retry, self._pair_timer):
            if cancel is not None:
                cancel()
        self._cancel_retry = self._pair_timer = None

    def _stop_live(self) -> None:
        """Stop the value trackers."""
        if self.live is not None:
            self.live.tracker.async_stop()
            self.live = None
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None

    # ------------------------------------------------------------- events

    @callback
    def link_changed(self, state: str) -> None:
        """Follow the connection. Every new connection gets a new handshake."""
        self.link_state = state
        if state == LINK_READY:
            self.drop_session()
            self._retry_index = 0
            self._dead = None
            self._hash_errors = 0
            self.kick()
            return
        self.drop_session()
        if state == LINK_NO_ENGINE:
            self.engine_state = ENGINE_NOT_INSTALLED
            self.engine_known = True
            self.engine = ""
        self.kick()

    @callback
    def assignment_changed(self) -> None:
        """Send the newly assigned dashboard at once."""
        want = self.want.url_path if self.want else None
        if want != self.dashboard:
            self._dead = None
            if (
                self.link_state == LINK_READY
                and self.dashboard is not None
                and self.sender.manager.ready
            ):
                # Shown at once in the answer to the change.
                self._set_status(STATUS_SENDING)
        self.kick()

    @callback
    def converted(self) -> None:
        """Send the changed dashboard once the edits have settled.

        Waits 0.7 s after the last change, at most 2 s after the first.
        """
        now = self._now()
        if self._debounce_first is None:
            self._debounce_first = now
        if self._debounce is not None:
            self._debounce.cancel()
        delay = min(DEBOUNCE_S, max(0.0, self._debounce_first + DEBOUNCE_MAX_S - now))
        self._debounce = self.hass.loop.call_later(delay, self._debounced)

    @callback
    def _debounced(self) -> None:
        """Run after the edits have settled."""
        self._debounce = None
        self._debounce_first = None
        self._dead = None
        self.kick()

    @callback
    def knock(self, boot: int) -> None:
        """Answer a knock (contract 2.2), at most one every 2 s.

        Any ESPHome device can fire a knock with another tablet's MAC, so a
        knock never resets a session by itself: with a session, HA reads
        tab_status and greets again only when the tablet says it has none.
        The boot number does not matter. A tablet no admin approved is not
        answered at all.
        """
        if not self.approved:
            return
        now = self._now()
        if now - self._last_knock < KNOCK_EVERY_S:
            return
        self._last_knock = now
        if self.nonce is not None and self.link_state == LINK_READY:
            self.sender.spawn(self._async_check_knock(), f"{DOMAIN} knock {self.hex}")
            return
        self.sender.link.async_recheck(self.mac)
        if self.link_state == LINK_READY:
            self.drop_session()
            self.kick()

    async def _async_check_knock(self) -> None:
        """Greet again when the tablet lost the session HA still holds."""
        nonce = self.nonce
        try:
            response = await self._call("tab_status", {})
        except LinkError:
            # The connection rules take over; a lost connection greets again.
            return
        if self._stopped or nonce is None or self.nonce != nonce:
            return
        status = response if isinstance(response, dict) else {}
        if tp.knock_step(session=True, status=status) == "hello":
            self.drop_session()
            self.kick()

    # ---------------------------------------------------------------- run

    async def _async_run(self) -> None:
        """Run the sync until nothing new has come in."""
        while self._dirty and not self._stopped:
            self._dirty = False
            try:
                await self._async_sync()
            except LinkError as err:
                self._link_error(err)
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("Sending to a tablet failed")
                self._fail("failed", retry=True)

    async def _async_sync(self) -> None:
        """Bring the tablet to the wanted layout and values."""
        sender = self.sender
        if not self.approved:
            # Not one word to a tablet no admin approved: no hello, no
            # pairing, no layout, no values, no clear.
            self._forget()
            return
        if self.link_state != LINK_READY:
            self._status_from_link()
            return
        if not sender.manager.ready:
            # Nothing is sent before the manager's first run.
            self._set_status(STATUS_SENDING)
            return
        url_path = self.dashboard
        if self.nonce is None:
            if self._waits_for_key():
                self._wait_for_key()
                return
            if not await self._async_handshake(url_path):
                return
        if url_path is None:
            if self.shown or self.staged:
                await self._call("tab_clear", {}, body="")
                self.shown = ""
                self.staged = None
                self.kept = {}
                self._stop_live()
            self.want = None
            self._set_status(STATUS_NO_DASHBOARD)
            return
        if url_path in sender.assignments.unreadable:
            # The tablet keeps its last layout and its values.
            await self._async_keep_shown()
            self._fail("unreadable", retry=False)
            return
        if url_path not in sender.manager.layouts:
            # Not converted yet, or on its way out; an event follows.
            self._set_status(STATUS_SENDING)
            return
        try:
            compiled = self._compile(url_path)
        except ContractError as err:
            # Too big or too many for this tablet: checked before any chunk.
            await self._async_keep_shown()
            self._fail(err.code, retry=False)
            return
        if self._check_shown:
            await self._async_read_shown()
        self._set_want(compiled)
        # The wanted layout may be on screen while another one, committed
        # earlier, is still building and would replace it when done. Sending
        # the wanted one again drops that build (seq 0), and its commit
        # changes nothing on screen (contract 5).
        other_staged = self.staged is not None and self.staged != compiled.hash
        if self.shown != compiled.hash:
            if self._dead is not None and self._dead[0] == compiled.hash:
                await self._async_keep_shown()
                return
            if not await self._async_send_layout(compiled):
                return
        elif other_staged and not await self._async_send_layout(compiled):
            return
        await self._async_start_live(compiled)
        self._succeeded()

    async def _async_read_shown(self) -> None:
        """Ask the tablet which layout it shows and which one it builds."""
        self._check_shown = False
        response = await self._call("tab_status", {})
        status = response if isinstance(response, dict) else {}
        layout = status.get("layout")
        if isinstance(layout, str):
            self.shown = layout
        staged = status.get("staged")
        self.staged = staged if isinstance(staged, str) and staged else None

    async def _async_keep_shown(self) -> None:
        """Keep the values of the layout on screen live, when HA knows it."""
        shown = self.kept.get(self.shown or "")
        if shown is not None:
            await self._async_start_live(shown)
        else:
            self._stop_live()

    def _status_from_link(self) -> None:
        """Show what the connection says."""
        if self.link_state == LINK_NO_ENGINE:
            self._set_status(STATUS_NO_ENGINE)
        elif self.link_state == LINK_UNSUPPORTED:
            self._set_status(STATUS_UNSUPPORTED, "ha_version")
        elif self.link_state == LINK_CHECKING:
            self._set_status(STATUS_SENDING)
        else:
            self._set_status(STATUS_OFFLINE)

    def _compile(self, url_path: str) -> Compiled:
        """Compile the dashboard for this tablet's caps; cached per layout."""
        stored = self.sender.manager.layouts[url_path]
        layout = stored["layout"]
        caps_key = repr(sorted(self.caps.items()))
        confirm = self._cover_questions(stored["bindings"])
        cache = self._compile_cache
        if (
            cache is not None
            and cache[0] is layout
            and cache[1] == caps_key
            and cache[2] == confirm
            and cache[3].url_path == url_path
            and cache[3].bindings is stored["bindings"]
        ):
            return cache[3]
        icons = self.sender.icons
        result = compile_device_layout(layout, icons, self.caps, confirm=confirm)
        compiled = Compiled(
            url_path=url_path,
            hash=result["hash"],
            data=result["bytes"],
            plan=result["slots"],
            bindings=stored["bindings"],
            layout=layout,
            digest=bindings_digest(stored["bindings"], result["slots"]),
            level=icon_level(icons, self.caps),
        )
        self._compile_cache = (layout, caps_key, confirm, compiled)
        return compiled

    def _cover_questions(self, bindings: dict) -> dict[int, str]:
        """Questions for widgets that move a garage, gate or door cover.

        The tablet asks them before it sends (cf), so a tap needs no round
        trip for HA's confirm answer. HA still checks every call.
        """
        questions: dict[int, str] = {}
        actions = bindings.get("actions") if isinstance(bindings, dict) else None
        if not isinstance(actions, dict):
            return questions
        components = self.sender.library.components
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
                self.hass,
                component,
                action,
                action.get("params") or {},
                action.get("entities") or [],
            )
            if text:
                questions.setdefault(int(widget_id), text)
        return questions

    def _set_want(self, compiled: Compiled) -> None:
        """Keep bindings for the wanted layout and for the one on screen."""
        self.want = compiled
        kept = {compiled.hash: compiled}
        if self.shown and self.shown != compiled.hash and self.shown in self.kept:
            kept[self.shown] = self.kept[self.shown]
        self.kept = kept

    def _still_wanted(self, compiled: Compiled) -> bool:
        """Return whether a newer hash has replaced this one meanwhile."""
        if self._stopped:
            return False
        if not self._dirty:
            return True
        url_path = self.dashboard
        if url_path != compiled.url_path or url_path not in self.sender.manager.layouts:
            return False
        try:
            return self._compile(url_path).hash == compiled.hash
        except ContractError:
            return False

    def _succeeded(self) -> None:
        """Record that the wanted layout is on the tablet."""
        self._retry_index = 0
        self._hash_errors = 0
        self._dead = None
        if self._cancel_retry is not None:
            self._cancel_retry()
            self._cancel_retry = None
        self._set_status(STATUS_ON_TABLET)

    def _fail(self, code: str, *, retry: bool, sent: str | None = None) -> None:
        """Show a failure; try again later unless it cannot succeed.

        sent is the hash whose transfer failed. When the failure cannot
        succeed, that hash is not sent again until the dashboard or the
        connection changes.
        """
        retry = retry and code not in NO_RETRY
        if not retry and sent is not None:
            self._dead = (sent, code)
        self._set_status(STATUS_FAILED, code, retry)
        if retry:
            self._schedule_retry()

    def _schedule_retry(self) -> None:
        """Try again after 5 s, 15 s, 60 s, then every 5 minutes."""
        if self._cancel_retry is not None:
            self._cancel_retry()
        delay = RETRY_S[min(self._retry_index, len(RETRY_S) - 1)]
        self._retry_index += 1
        self._cancel_retry = async_call_later(self.hass, delay, self._retry_now)

    @callback
    def _retry_now(self, _now: Any) -> None:
        """Retry after a failure."""
        self._cancel_retry = None
        self.kick()

    def _link_error(self, err: LinkError) -> None:
        """Handle a call that did not succeed."""
        code = err.code
        if code == "not_approved":
            # Nothing was sent. The next run finds the tablet waiting.
            self._forget()
        elif code == "offline":
            self.drop_session()
            self._status_from_link()
            if self.link_state == LINK_READY:
                self._fail("offline", retry=True)
        elif code == "no_engine":
            self.drop_session()
            self.sender.link.async_recheck(self.mac)
            if self.link_state == LINK_READY:
                self._fail("no_engine", retry=True)
        elif code == "ha_version":
            self._set_status(STATUS_UNSUPPORTED, "ha_version")
        elif code == "auth":
            # The tablet refused a signed call: pair again and greet again.
            self.drop_session()
            self._force_pair = True
            if self._pair_allowed():
                self.kick()
            else:
                self._set_status(STATUS_FAILED, "auth", True)
                self._schedule_pair()
        elif code == "no_session":
            # Nothing was sent: the tablet needs signed calls and HA holds no
            # session to sign them with. Not a wrong secret, so no new one.
            if self.link_state != LINK_READY:
                self._status_from_link()
            elif not self._dirty:
                # The handshake could not start a session: pairing is due
                # and waits for its once-a-minute limit, or it failed. The
                # pairing timer greets again. (When the session was dropped
                # during this run, whatever dropped it started a new run.)
                self._set_status(STATUS_FAILED, "auth", True)
                self._schedule_pair()
        elif code == "hash":
            # tab_set for a layout the tablet does not hold: greet again.
            self.drop_session()
            self._hash_errors += 1
            if self._hash_errors <= 2:
                self.kick()
            else:
                self._fail("hash", retry=True)
        else:
            self._fail(code, retry=True, sent=self.want.hash if self.want else None)

    # -------------------------------------------------------------- calls

    async def _call(
        self,
        action: str,
        args: dict[str, Any],
        *,
        body: str | None = None,
        still: Callable[[], bool] | None = None,
    ) -> dict[str, Any] | None:
        """Write one call; signed calls get their auth here, in write order.

        Raises LinkError("no_session"), without sending anything, when the
        call must be signed and HA holds no session (it can end while the
        call waits for the one before it), or when still() says the call
        is no longer wanted. An unsigned call would only be refused, and
        that refusal would look like a wrong secret. Raises
        LinkError("not_approved"), without sending anything, for a tablet
        that waits for an admin.
        """
        async with self._lock:
            if not self.approved:
                # The approval went away while this call waited.
                raise LinkError("not_approved")
            if still is not None and not still():
                raise LinkError("no_session")
            if body is not None:
                secret = self.sender.assignments.secret(self.mac)
                # No signing without encryption (contract 6.1): such a
                # tablet ignores its secret and accepts any auth.
                if secret is not None and self.enc:
                    if self.nonce is None:
                        raise LinkError("no_session")
                    self.n += 1
                    auth = tp.call_auth(
                        secret, self.hex, self.nonce, self.n, action, body
                    )
                else:
                    auth = ""
                args = {**args, "auth": auth}
            return await self.sender.link.async_call(self.mac, action, args)

    async def _async_hello(self) -> dict[str, Any]:
        """Call tab_hello with a fresh nonce; keep the session if one started."""
        nonce = tp.new_nonce()
        secret = self.sender.assignments.secret(self.mac)
        if self.sender.link.api_key(self.mac) is None:
            # No API key: the connection is plain text, and the tablet
            # ignores its secret (contract 6.1). A signed hello sent there
            # could be recorded and played back after a reboot.
            secret = None
        auth = tp.call_auth(secret, self.hex, nonce, 0, "tab_hello")
        response = await self._call("tab_hello", {"nonce": nonce, "auth": auth})
        if not isinstance(response, dict):
            raise LinkError("bad_response")
        if response.get("session") == 1:
            self.nonce = nonce
            self.n = 0
            self.last_counter = 0
        else:
            self.nonce = None
        boot = response.get("boot")
        self.boot = boot if isinstance(boot, int) else None
        self.caps = tp.caps_of(response)
        layout = response.get("layout")
        self.shown = layout if isinstance(layout, str) else ""
        if self.staged is not None and self.staged == self.shown:
            self.staged = None
        tablet_kid = response.get("kid")
        self.tablet_kid = tablet_kid if isinstance(tablet_kid, str) else ""
        self.enc = response.get("enc") == 1
        self.engine = str(response.get("engine") or "")[:32]
        return response

    async def _async_handshake(self, url_path: str | None) -> bool:
        """Greet the tablet, pair it when needed. False: stop here."""
        self._set_status(STATUS_SENDING)
        response = await self._async_hello()
        want_hash = None
        if url_path is not None and url_path in self.sender.manager.layouts:
            try:
                want_hash = self._compile(url_path).hash
            except ContractError:
                want_hash = None
        assignments = self.sender.assignments
        steps = tp.hello_steps(
            response, stored_kid=assignments.kid(self.mac), want_hash=want_hash
        )
        if steps["status"] == "unsupported":
            self.nonce = None
            self.engine_state = ENGINE_UPDATE_NEEDED
            self.engine_known = True
            self._set_status(STATUS_UNSUPPORTED, steps["reason"])
            return False
        self.engine_state = ENGINE_READY
        self.engine_known = True
        if "pair" in steps["steps"] or (self._force_pair and response.get("enc") == 1):
            if self.tablet_kid and self.tablet_kid != assignments.kid(self.mac):
                _LOGGER.warning(
                    "A TAB-1 tablet holds a pairing key this Home Assistant did "
                    "not set; another Home Assistant may be using it"
                )
            if not self._pair_allowed():
                # At most one pairing a minute: pair as soon as it is allowed.
                self._schedule_pair()
            elif await self._async_pair():
                response = await self._async_hello()
        enc = response.get("enc") == 1
        if self._waits_for_key(enc=enc):
            self._wait_for_key()
            return False
        if not enc:
            self.input = INPUT_NEEDS_ENCRYPTION
        elif self.paired and self.nonce is not None:
            self.input = INPUT_OK
        else:
            self.input = INPUT_NOT_PAIRED
        if self.want is not None and self.shown == self.want.hash:
            self.kept = {self.want.hash: self.want}
        self.snapshot_needed = True
        self.sender.notify()
        return True

    def _waits_for_key(self, *, enc: bool = True) -> bool:
        """Return whether HA holds everything back until the tablet has its key.

        Holds for a tablet HA paired before that is now on a connection
        without an API key (or whose tab_hello says enc 0): it was erased
        or set up again, and ESPHome is about to give it its key and
        connect again with it. Until then HA sends it nothing, so neither
        its dashboard nor live values cross the network in plain text.
        A tablet whose software takes no key does not wait, because no key
        comes: as contract 6.1 allows, it gets its dashboard unsigned.
        """
        link = self.sender.link
        return (
            self.sender.assignments.secret(self.mac) is not None
            and link.encryption_supported(self.mac)
            and (link.api_key(self.mac) is None or not enc)
        )

    def _wait_for_key(self) -> None:
        """Send nothing more on this connection; the keyed one starts over."""
        self.nonce = None
        self._stop_live()
        self.input = INPUT_NOT_PAIRED
        self._set_status(STATUS_SENDING)
        self.sender.notify()

    async def _async_pair(self) -> bool:
        """Give the tablet a new secret, wrapped under its API key."""
        self._last_pair = self._now()
        psk = self.sender.link.api_key(self.mac)
        if psk is None:
            self.input = INPUT_NOT_PAIRED
            return False
        secret = tp.new_secret()
        nonce = tp.new_nonce()
        key_id = tp.kid(secret)
        try:
            await self._call(
                "tab_pair",
                {
                    "nonce": nonce,
                    "wrapped": tp.wrap_secret(psk, self.hex, nonce, secret),
                    "kid": key_id,
                },
            )
        except LinkError as err:
            if err.code == "needs_encryption":
                self.input = INPUT_NEEDS_ENCRYPTION
                return False
            if err.code == "bad_key":
                _LOGGER.warning("A TAB-1 tablet refused its new pairing key")
                return False
            raise
        self.sender.assignments.async_set_secret(self.mac, secret, key_id)
        self._force_pair = False
        if self._pair_timer is not None:
            self._pair_timer()
            self._pair_timer = None
        self.nonce = None
        return True

    def _pair_allowed(self) -> bool:
        """Return whether the once-a-minute pairing limit allows a pairing now."""
        return self._now() - self._last_pair >= PAIR_EVERY_S

    def _schedule_pair(self) -> None:
        """Pair as soon as the limit allows.

        A timer of its own, so a success or a retry in between does not
        cancel it, and the session and its values stay live until then.
        """
        if self._stopped:
            return
        if self._pair_timer is not None:
            self._pair_timer()
        wait = max(0.0, self._last_pair + PAIR_EVERY_S - self._now())
        self._pair_timer = async_call_later(self.hass, wait, self._pair_due)

    @callback
    def _pair_due(self, _now: Any) -> None:
        """Greet again so the handshake pairs, when a pairing is still wanted."""
        self._pair_timer = None
        if self._stopped:
            return
        if self._force_pair or self.input == INPUT_NOT_PAIRED:
            self.drop_session()
            self.kick()

    @callback
    def request_pair(self) -> None:
        """Make a new secret soon (an admin asked).

        Within a minute of the last pairing, the session stays (values keep
        flowing) until the pairing is allowed. A tablet no admin approved
        is never paired.
        """
        if not self.approved:
            return
        self._force_pair = True
        if self._pair_allowed():
            self.drop_session()
            self.kick()
        else:
            self._schedule_pair()

    async def _async_send_layout(self, compiled: Compiled) -> bool:
        """Send the layout, commit it and wait until it is on screen."""
        self._set_status(STATUS_SENDING)
        size = int(self.caps.get("max_chunk", CHUNK_BYTES) or CHUNK_BYTES)
        chunks = tp.chunk_layout(compiled.data, max(16, min(CHUNK_BYTES, size)))
        self.sending = True
        try:
            for seq, text in enumerate(chunks):
                if not self._still_wanted(compiled):
                    return False
                await self._call(
                    "tab_layout",
                    {
                        "hash": compiled.hash,
                        "seq": seq,
                        "total": len(chunks),
                        "size": len(compiled.data),
                        "data": text,
                    },
                )
                if seq == 0:
                    # seq 0 dropped any build the tablet had (contract 5).
                    self.staged = None
            if not self._still_wanted(compiled):
                return False
            try:
                await self._call(
                    "tab_commit", {"hash": compiled.hash}, body=compiled.hash
                )
            except LinkError as err:
                if err.code in ("timeout", "offline"):
                    # The tablet may have staged it without HA hearing so.
                    self.staged = compiled.hash
                raise
            self.staged = compiled.hash
        finally:
            self.sending = False
        self.watching = True
        try:
            # The staged layout takes values, so its first frame has them.
            await self._async_start_live(compiled, force=True)
            verdict = await self._async_watch_build(compiled)
        finally:
            self.watching = False
        if verdict not in (None, "timeout"):
            # The build ended: shown, or the old layout stayed.
            self.staged = None
        if verdict == "shown":
            self.shown = compiled.hash
            self.kept = {compiled.hash: compiled}
            return True
        previous = self.kept.get(self.shown or "")
        if previous is not None and previous is not compiled:
            await self._async_start_live(previous, force=True)
        else:
            self._stop_live()
        if verdict is not None:
            self._fail(verdict, retry=True, sent=compiled.hash)
        return False

    async def _async_watch_build(self, compiled: Compiled) -> str | None:
        """Ask tab_status until the build ends. None: a newer hash came."""
        waited = 0.0
        index = 0
        while waited < STATUS_POLL_LIMIT_S:
            delay = STATUS_POLL_S[min(index, len(STATUS_POLL_S) - 1)]
            index += 1
            await asyncio.sleep(delay)
            waited += delay
            if not self._still_wanted(compiled):
                return None
            response = await self._call("tab_status", {})
            verdict = tp.status_verdict(response or {}, compiled.hash)
            if verdict != "building":
                return verdict
        return "timeout"

    # ------------------------------------------------------------- values

    async def _async_start_live(
        self, compiled: Compiled, *, force: bool = False
    ) -> None:
        """Track the layout's values; send a full snapshot when one is due."""
        live = self.live
        if (
            live is None
            or live.hash != compiled.hash
            or live.digest != compiled.digest
            or force
        ):
            self._stop_live()
            live = _Live(self, compiled)
            self.live = live
            await live.tracker.async_start()
            if self.live is not live:
                return
            self.snapshot_needed = True
        if self.snapshot_needed:
            await self._async_snapshot(live)

    async def _async_snapshot(self, live: _Live) -> None:
        """Send every slot value, split when larger than one call allows."""
        values = dict(live.wire)
        for payload in tp.encode_set(live.hash, values, full=True):
            await self._call("tab_set", {"data": payload}, body=payload)
        if self.live is live:
            live.sent = values
            self.snapshot_needed = False
            if live.changes():
                self._schedule_flush()

    @callback
    def values_changed(self, live: _Live) -> None:
        """Send changed values after a short gathering wait."""
        if live is self.live and live.sent is not None:
            self._schedule_flush()

    def _schedule_flush(self, delay: float | None = None) -> None:
        """Send changes in 100 ms (or delay), one tab_set in flight."""
        if self._flush_handle is None and not self._flushing and not self._stopped:
            self._flush_handle = self.hass.loop.call_later(
                VALUE_BATCH_S if delay is None else delay, self._start_flush
            )

    @callback
    def _start_flush(self) -> None:
        """Start sending the gathered changes."""
        self._flush_handle = None
        if not self._stopped:
            self.sender.spawn(self._async_flush(), f"{DOMAIN} values {self.hex}")

    async def _async_flush(self) -> None:
        """Send the values that changed since the last call."""
        live = self.live
        if live is None or live.sent is None or self._flushing:
            return
        changes = live.changes()
        if not changes:
            return
        self._flushing = True
        failed = False
        try:
            for payload in tp.encode_set(live.hash, changes, full=False):
                await self._call(
                    "tab_set",
                    {"data": payload},
                    body=payload,
                    still=lambda: self.live is live,
                )
            live.sent.update(changes)
        except LinkError as err:
            if err.code in ("hash", "auth"):
                self._link_error(err)
                return
            if err.code in ("offline", "no_engine", "no_session", "not_approved"):
                # The connection rules take over; a new session sends all.
                # no_session: the session ended while the change waited for
                # the call before it; nothing was sent. not_approved: the
                # tablet waits for an admin; nothing was sent.
                return
            # A timeout or another failure: the changes are still owed, so
            # they are sent again after a wait.
            failed = True
        finally:
            self._flushing = False
        if self.live is live and live.changes():
            self._schedule_flush(SET_RETRY_S if failed else None)

    # -------------------------------------------------------------- input

    async def async_input(self, data: dict) -> None:
        """Check one input event, run its action and answer with tab_ack."""
        if not self.approved:
            # Nothing runs for a tablet no admin approved, and it hears nothing.
            self.dropped["not_approved"] += 1
            return
        assignments = self.sender.assignments
        # Input counts only from a tablet whose last handshake confirmed
        # encryption and pairing (contract 6.1, 7.3): otherwise not_paired.
        secret = assignments.secret(self.mac) if self.input == INPUT_OK else None
        verdict, parsed = tp.verify_input(
            data,
            mac=self.hex,
            secret=secret,
            nonce=self.nonce or "",
            last_counter=self.last_counter,
            layouts=tuple(self.kept),
        )
        if verdict not in ("ok", "stale_layout") or parsed is None:
            self._drop_input(verdict)
            return
        counter = parsed["counter"]
        self.last_counter = counter
        now = self._now()
        while self._inputs and now - self._inputs[0] >= 1.0:
            self._inputs.popleft()
        if len(self._inputs) >= INPUTS_PER_SECOND:
            await self._async_ack(counter, tp.ACK_BUSY)
            return
        self._inputs.append(now)
        if verdict == "stale_layout":
            await self._async_ack(counter, tp.ACK_STALE)
            # The tablet shows a layout HA keeps no bindings for: read what it
            # really shows before trusting `shown` again.
            self._check_shown = True
            if not self.running and not self.sending and not self.watching:
                self.kick()
            return
        code = await self._async_run_input(parsed)
        await self._async_ack(counter, code)

    def _drop_input(self, verdict: str) -> None:
        """Count a dropped input; no ack, so a stranger learns nothing."""
        self.dropped[verdict] += 1
        now = self._now()
        if now - self._last_warning >= WARN_EVERY_S:
            self._last_warning = now
            _LOGGER.warning("A TAB-1 tablet input was dropped: %s", verdict)
        if verdict == "stale_session" and (
            now - self._last_stale_session >= STALE_SESSION_EVERY_S
        ):
            # The signature was valid, so it is the real tablet.
            self._last_stale_session = now
            self.drop_session()
            self.kick()

    async def _async_run_input(self, parsed: dict) -> str:
        """Run the action of one tap or change; return the ack code."""
        compiled = self.kept.get(parsed["layout"])
        if compiled is None:
            return tp.ACK_STALE
        key = f"{parsed['widget']}:{parsed['event']}"
        action = compiled.bindings.get("actions", {}).get(key)
        widget = _find_widget(compiled.layout, parsed["widget"])
        if not isinstance(action, dict) or widget is None:
            return tp.ACK_FAILED
        library = self.sender.library
        component_id = action.get("component")
        component = (
            library.components.get(component_id)
            if isinstance(component_id, str)
            else None
        )
        if component is None or not library.is_approved(component_id):
            return tp.ACK_DENIED
        if action.get("demo"):
            return tp.ACK_DENIED
        try:
            await async_run_output(
                self.hass,
                component=component,
                action_ref=action,
                params=action.get("params") or {},
                entities=action.get("entities") or [],
                widget=widget,
                event=parsed["event"],
                value=parsed["value"],
                confirmed=parsed["confirmed"],
                # A tablet has no user: a fresh context without one.
                context=Context(),
            )
        except CallError as err:
            return ACK_FOR_ERROR.get(err.code, tp.ACK_FAILED)
        return tp.ACK_DONE

    async def _async_ack(self, counter: int, code: str) -> None:
        """Answer one input."""
        ok = code == tp.ACK_DONE
        try:
            await self._call(
                "tab_ack",
                {"n": counter, "ok": ok, "code": code},
                body=tp.ack_body(counter, ok, code),
            )
        except LinkError:
            return


class TabletSender:
    """Follow the tablets and send each one its assigned dashboard."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        manager: DashboardManager,
        library: Library,
        slot_hub: SlotHub,
        assignments: Assignments,
        link: TabletLink,
        icons: dict,
    ) -> None:
        """Store the parts; call async_start to begin."""
        self.hass = hass
        self.manager = manager
        self.library = library
        self.slot_hub = slot_hub
        self.assignments = assignments
        self.link = link
        self.icons = icons
        self.sessions: dict[str, TabletSession] = {}
        self._by_hex: dict[str, TabletSession] = {}
        self._listeners: list[Callable[[], None]] = []
        self._unsubscribers: list[Callable[[], None]] = []
        self._notify_scheduled = False
        self._stopped = False
        self._tasks: set[asyncio.Task] = set()
        self.unknown_inputs = 0
        # The new-tablet repair issues made: {issue id: tablet name}. None
        # until the first look at the issue registry.
        self._issues: dict[str, str] | None = None

    # ---------------------------------------------------------- lifecycle

    async def async_start(self) -> None:
        """Listen for everything that changes what a tablet shows."""
        hass = self.hass
        self.link.async_set_listener(self._link_changed)
        self._unsubscribers += [
            self.manager.async_listen(self._manager_changed),
            self.assignments.async_listen(self._assignment_changed),
            hass.bus.async_listen(
                dr.EVENT_DEVICE_REGISTRY_UPDATED, self._device_registry_updated
            ),
            hass.bus.async_listen(EVENT_PANELS_UPDATED, self._panels_updated),
            hass.bus.async_listen(EVENT_INPUT, self._handle_input),
            hass.bus.async_listen(EVENT_KNOCK, self._handle_knock),
            hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, self._names_changed),
            # A reauth of a tablet's ESPHome entry starts or ends: its row
            # says what Home Assistant waits for (reauth in the Tablet).
            hass.bus.async_listen(
                ir.EVENT_REPAIRS_ISSUE_REGISTRY_UPDATED,
                self._reauth_changed,
                event_filter=_is_esphome_reauth_issue,
            ),
        ]
        self._reconcile()
        self._unsubscribers.append(self.manager.async_when_ready(self._on_ready))

    @callback
    def spawn(self, target: Coroutine[Any, Any, Any], name: str) -> None:
        """Run a background task that async_stop cancels."""
        if self._stopped:
            target.close()
            return
        task = self.hass.async_create_background_task(target, name)
        if not task.done():
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    @callback
    def async_stop(self) -> None:
        """Stop every session, task, timer, listener and repair issue."""
        self._stopped = True
        self._delete_issues()
        while self._unsubscribers:
            self._unsubscribers.pop()()
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        for session in self.sessions.values():
            session.async_stop()
        self.sessions.clear()
        self._by_hex.clear()
        self.link.async_stop()
        self._listeners.clear()

    @callback
    def _on_ready(self) -> None:
        """Assign, check and send once the manager's first run is done."""
        if not self._stopped:
            self.spawn(self._async_ready(), f"{DOMAIN} tablets ready")

    async def _async_ready(self) -> None:
        """Fill empty assignments, move tablets off missing dashboards, send."""
        self.assignments.async_fill()
        # Shown dashboards and waiting tablets' suggestions alike: one that
        # went while HA was off moves its tablets and drops the suggestions.
        for url_path in sorted(self.assignments.named()):
            try:
                await self.assignments.async_check_dashboard(url_path)
            except Exception:
                # One dashboard must not stop the checks of the others.
                _LOGGER.exception("Checking dashboard %s failed", url_path)
        if self._stopped:
            return
        for session in self.sessions.values():
            session.kick()
        self.notify()

    # ------------------------------------------------------------ tablets

    @callback
    def _reconcile(self) -> None:
        """Make the sessions match the tablets in the device registry."""
        if self._stopped:
            return
        tablets = async_get_tablets(self.hass)
        for mac in list(self.sessions):
            if mac not in tablets:
                session = self.sessions.pop(mac)
                self._by_hex.pop(session.hex, None)
                session.async_stop()
                self.link.async_unwatch(mac)
        # New tablets wait for an admin; one under another ESPHome entry
        # than the one it was approved under waits again.
        self.assignments.async_see(
            {mac: tablets[mac].config_entry_id for mac in sorted(tablets)}
        )
        for mac, device in tablets.items():
            session = self.sessions.get(mac)
            if session is None:
                session = TabletSession(self, mac, device.id, device.config_entry_id)
                self.sessions[mac] = session
                self._by_hex[session.hex] = session
            else:
                session.device_id = device.id
                session.entry_id = device.config_entry_id
            self.link.async_watch(mac, device.config_entry_id)
        self.notify()

    @callback
    def _device_registry_updated(self, event: Event) -> None:
        """Reconcile after the registries have handled the change."""
        self.hass.loop.call_soon(self._reconcile)

    @callback
    def _names_changed(self, event: Event) -> None:
        """Tell the listeners: a renamed area can change tablet names."""
        self.notify()

    @callback
    def _reauth_changed(self, event: Event) -> None:
        """Tell the listeners: an ESPHome reauth started or ended."""
        self.notify()

    @callback
    def _link_changed(self, mac: str, state: str) -> None:
        """Pass a connection change to the tablet's session."""
        session = self.sessions.get(mac)
        if session is not None:
            session.link_changed(state)
            self.notify()

    @callback
    def _manager_changed(self, kind: str, url_path: str) -> None:
        """Send converted dashboards; move tablets off removed ones."""
        if kind == "converted":
            self.assignments.async_converted(url_path)
            for session in self.sessions.values():
                if session.dashboard == url_path:
                    session.converted()
            self.assignments.async_fill()
            self.notify()
        elif kind == "removed" or (
            kind == "absent"
            and (
                url_path in self.assignments.unreadable
                or url_path in self.assignments.named()
            )
        ):
            # "absent": a dashboard without a layout that a tablet is still
            # on or suggests, for example one that could not be read and is
            # deleted now.
            self.spawn(self._async_removed(url_path), f"{DOMAIN} dashboard removed")

    async def _async_removed(self, url_path: str) -> None:
        """Reassign the tablets of a dashboard that went away."""
        await self.assignments.async_check_dashboard(url_path)
        for session in self.sessions.values():
            if session.dashboard == url_path:
                session.kick()
        self.notify()

    @callback
    def _assignment_changed(self, mac: str | None) -> None:
        """Send to the tablets whose assignment changed."""
        sessions = (
            [self.sessions[mac]]
            if mac is not None and mac in self.sessions
            else list(self.sessions.values())
        )
        for session in sessions:
            session.assignment_changed()
        self.notify()

    @callback
    def _panels_updated(self, event: Event) -> None:
        """Read the titles again; a dashboard may have been renamed."""
        if self.manager.async_refresh_titles():
            self.notify()

    @callback
    def _handle_input(self, event: Event) -> None:
        """Route an input event to its tablet by the MAC inside the payload."""
        mac = tp.input_mac(event.data)
        session = self._by_hex.get(mac) if mac else None
        if session is None:
            self.unknown_inputs += 1
            return
        if not session.approved:
            # Runs nothing and is not answered (design 4.2).
            session.dropped["not_approved"] += 1
            return
        data = {"d": event.data.get("d"), "s": event.data.get("s")}
        self.spawn(session.async_input(data), f"{DOMAIN} input {session.hex}")

    @callback
    def _handle_knock(self, event: Event) -> None:
        """Answer a knock from a tablet nobody greeted.

        Knocks that name a tablet no admin approved are ignored.
        """
        parsed = tp.parse_knock(event.data)
        if parsed is None:
            return
        session = self._by_hex.get(parsed[0])
        if session is not None and session.approved:
            session.knock(parsed[1])

    # ------------------------------------------------------------ changes

    @callback
    def async_listen(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call listener after tablets changed; return its remover."""
        self._listeners.append(listener)

        def _remove() -> None:
            """Remove the listener."""
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    @callback
    def notify(self) -> None:
        """Tell the listeners once per loop iteration."""
        if self._notify_scheduled or self._stopped:
            return
        self._notify_scheduled = True
        self.hass.loop.call_soon(self._send_notify)

    @callback
    def _send_notify(self) -> None:
        """Run the listeners, update the entities and the repair issues."""
        self._notify_scheduled = False
        if self._stopped:
            return
        self._sync_issues()
        for listener in list(self._listeners):
            listener()
        async_dispatcher_send(self.hass, SIGNAL_TABLETS_UPDATED)

    @callback
    def _sync_issues(self) -> None:
        """Keep one repair issue per tablet that waits for an admin.

        It goes when the tablet is approved, its device leaves Home
        Assistant, or someone disables its device (on purpose: such a
        tablet is not waiting for anyone). It holds the tablet's name,
        nothing else about it.
        """
        device_registry = dr.async_get(self.hass)

        def _disabled(session: TabletSession) -> bool:
            """Return whether the tablet's device is disabled."""
            device = device_registry.async_get(session.device_id)
            return device is not None and device.disabled

        waiting = [
            session
            for session in self.sessions.values()
            if not session.approved and not _disabled(session)
        ]
        names = self._names() if waiting else {}
        wanted = {
            session.issue_id: names.get(session.mac, ("Tablet", "Tablet"))[0]
            for session in waiting
        }
        if self._issues is None:
            # The first look: issues of tablets that left Home Assistant or
            # were approved while this sender was not running, and ids in an
            # older form (the MAC, or a hash of it) go.
            self._issues = {
                issue_id: ""
                for domain, issue_id in ir.async_get(self.hass).issues
                if domain == DOMAIN and issue_id.startswith(f"{NEW_TABLET_ISSUE}_")
            }
        for issue_id in list(self._issues):
            if issue_id not in wanted:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
                del self._issues[issue_id]
        for issue_id, name in wanted.items():
            if self._issues.get(issue_id) == name:
                continue
            self._issues[issue_id] = name
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=NEW_TABLET_ISSUE,
                translation_placeholders={"name": name},
            )

    @callback
    def _delete_issues(self) -> None:
        """Delete the new-tablet issues (the integration stops)."""
        for issue_id in self._issues or {}:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        self._issues = None

    # ------------------------------------------------------------ actions

    def session_for(self, mac: str) -> TabletSession | None:
        """Return the session of a tablet, by either MAC form."""
        session = self.sessions.get(mac.lower())
        if session is None:
            session = self._by_hex.get(tp.mac_hex(mac))
        return session

    def any_on_tablet(self) -> bool:
        """Return whether any tablet shows its dashboard."""
        return any(s.status == STATUS_ON_TABLET for s in self.sessions.values())

    # --------------------------------------------------------------- JSON

    def tablets_json(self) -> list[dict[str, Any]]:
        """Return every tablet in the Tablet shape of the websocket API."""
        names = self._names()
        tablets = [
            self._tablet_json(session, names) for session in self.sessions.values()
        ]
        tablets.sort(key=lambda tablet: (tablet["name"].lower(), tablet["mac"]))
        return tablets

    def tablet_json(self, session: TabletSession) -> dict[str, Any]:
        """Return one tablet in the Tablet shape."""
        return self._tablet_json(session, self._names())

    def _names(self) -> dict[str, tuple[str, str]]:
        """Return {mac: (name, short_name)} with duplicates told apart."""
        device_registry = dr.async_get(self.hass)
        area_registry = ar.async_get(self.hass)
        base: dict[str, str] = {}
        for mac, session in self.sessions.items():
            device = device_registry.async_get(session.device_id)
            name = ""
            if device is not None:
                if device.name_by_user:
                    name = device.name_by_user
                elif device.area_id and (
                    area := area_registry.async_get_area(device.area_id)
                ):
                    name = f"{area.name} tablet"
                else:
                    name = device.name or ""
            base[mac] = name or "Tablet"
        counts = Counter(name.lower() for name in base.values())
        names: dict[str, tuple[str, str]] = {}
        for mac, name in base.items():
            short = (
                name[: -len(" tablet")] if name.lower().endswith(" tablet") else name
            )
            short = short or name
            if counts[name.lower()] > 1:
                suffix = f" ({tp.mac_hex(mac)[-4:]})"
                name, short = name + suffix, short + suffix
            names[mac] = (name, short)
        return names

    def _tablet_json(
        self, session: TabletSession, names: dict[str, tuple[str, str]]
    ) -> dict[str, Any]:
        """Build one Tablet."""
        entity_id = er.async_get(self.hass).async_get_entity_id(
            "select", DOMAIN, f"{session.mac}_dashboard"
        )
        name, short = names.get(session.mac, ("Tablet", "Tablet"))
        approved = session.approved
        device = dr.async_get(self.hass).async_get(session.device_id)
        reauth, reauth_name = self._reauth(session, name)
        return {
            "mac": session.mac,
            "device_id": session.device_id,
            "name": name,
            "short_name": short,
            # With the MAC's end and the device page, what lets an admin
            # tell which device is waiting: the name comes from the device.
            "model": (device.model if device is not None else None) or TABLET_MODEL,
            "dashboard": session.dashboard,
            "status": session.status,
            "reason": session.reason,
            "retry": session.retry,
            "engine": session.engine,
            "paired": session.paired,
            "input": session.input if approved else INPUT_NOT_PAIRED,
            "entity_id": entity_id,
            "approved": approved,
            # What a tablet that lost its approval showed before: the
            # panel's suggestion, never shown on it until an admin picks.
            "suggested": None if approved else self.assignments.suggested(session.mac),
            # What Home Assistant waits for from an admin before ESPHome
            # connects to the tablet again, and the name Repairs gives it.
            "reauth": reauth,
            "reauth_name": reauth_name,
        }

    def _reauth(
        self, session: TabletSession, fallback: str
    ) -> tuple[str | None, str | None]:
        """Return what a reauth of the tablet's ESPHome entry asks, and its name.

        After a hold-to-erase the tablet comes back without its key, and
        Home Assistant 2026.11 neither connects nor tries again until an
        admin confirms that in Repairs, where it reads "Authentication
        expired for <entry title>". (None, None) without such a flow.
        """
        flows = self.hass.config_entries.flow.async_progress_by_handler(
            "esphome",
            match_context={"source": SOURCE_REAUTH, "entry_id": session.entry_id},
        )
        if not flows:
            return None, None
        erased = any(flow.get("step_id") == ESPHOME_ERASED_STEP for flow in flows)
        entry = self.hass.config_entries.async_get_entry(session.entry_id)
        title = " ".join(str(entry.title or "").split()) if entry is not None else ""
        return (REAUTH_ERASED if erased else REAUTH_KEY), title or fallback


async def async_clear_tablets(hass: HomeAssistant) -> None:
    """Blank every reachable tablet and delete the stored secrets.

    Used when the integration is removed. Best effort: tablets that are
    offline keep their last layout. Only tablets an admin approved under
    the ESPHome entry they have now: HA never talks to the others.
    """
    store: Store[dict] = Store(hass, STORE_VERSION, STORE_KEY)
    data = await store.async_load() or {}
    records = data.get("tablets") if isinstance(data.get("tablets"), dict) else {}
    link = create_link(hass)

    def _trusted(mac: str, entry_id: str) -> bool:
        """Return whether the stored record approves this tablet here."""
        record = records.get(mac)
        return (
            isinstance(record, dict)
            and record.get("approved") is True
            and record.get("entry_id") == entry_id
        )

    async def _clear(mac: str, entry_id: str) -> None:
        """Greet one tablet and clear it."""
        record = records.get(mac) or {}
        try:
            secret = bytes.fromhex(record["secret"]) if record.get("secret") else None
        except ValueError:
            secret = None
        hexmac = tp.mac_hex(mac)
        link.async_watch(mac, entry_id)
        if link.api_key(mac) is None:
            # No signing over a plain connection (contract 6.1).
            secret = None
        nonce = tp.new_nonce()
        try:
            response = await link.async_call(
                mac,
                "tab_hello",
                {
                    "nonce": nonce,
                    "auth": tp.call_auth(secret, hexmac, nonce, 0, "tab_hello"),
                },
            )
            if (response or {}).get("session") != 1 and secret is not None:
                return
            await link.async_call(
                mac,
                "tab_clear",
                {"auth": tp.call_auth(secret, hexmac, nonce, 1, "tab_clear")},
            )
        except LinkError as err:
            _LOGGER.debug("A tablet could not be cleared: %s", err.code)

    try:
        await asyncio.gather(
            *(
                _clear(mac, device.config_entry_id)
                for mac, device in async_get_tablets(hass).items()
                if _trusted(mac, device.config_entry_id)
            )
        )
    finally:
        link.async_stop()
    await store.async_remove()
