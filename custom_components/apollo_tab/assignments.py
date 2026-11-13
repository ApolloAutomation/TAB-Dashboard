"""Which dashboard each tablet shows, and each tablet's pairing secret.

Stored in ``.storage/apollo_tab.tablets``, keyed by the tablet's MAC address
from the device registry, so an assignment survives a device being removed
and added again. Dashboards are referenced by url_path; a rename changes the
title only.

A tablet is trusted only after an admin approved it, once: by picking its
first dashboard in the panel, the select or the show_dashboard action. Any
ESPHome device can call itself a TAB-1 (the model comes from its own
firmware), so a newly seen tablet gets no dashboard, no pairing and no say
until then. The approval holds for the ESPHome config entry it was given
under; the same MAC under another entry needs a new one.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.helpers.storage import Store

from .compat import PROBE_EMPTY, PROBE_MISSING, PROBE_OK, async_dashboard_info
from .const import DOMAIN
from .maker.schema import is_tab_dashboard

if TYPE_CHECKING:
    from .manager import DashboardManager

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
STORE_KEY = f"{DOMAIN}.tablets"
SAVE_DELAY = 1

APPROVAL_NEEDED = (
    "An admin must turn this tablet on first: in the TAB-1 panel, pick a "
    'dashboard for it, then press "Turn on with this dashboard".'
)


class ApprovalNeeded(HomeAssistantError):
    """A tablet nobody approved yet, changed by someone who cannot approve."""

    def __init__(self) -> None:
        """Say in plain words who can turn the tablet on."""
        super().__init__(
            APPROVAL_NEEDED,
            translation_domain=DOMAIN,
            translation_key="approval_needed",
        )


async def _async_user_is_admin(hass: HomeAssistant, context: Context | None) -> bool:
    """Return whether the context belongs to a user who is an admin."""
    if context is None or context.user_id is None:
        return False
    user = await hass.auth.async_get_user(context.user_id)
    return user is not None and user.is_admin


async def _async_user_can_approve(hass: HomeAssistant, context: Context | None) -> bool:
    """Return whether the context belongs to a person who may approve a tablet.

    An active admin who is a person. A system-generated user can be an
    admin too: the Supervisor's, which add-ons such as Node-RED or
    AppDaemon use when they call Home Assistant with their own access.
    Those are automations, and an automation never approves a tablet. An
    add-on set up with an admin's long-lived access token calls as that
    admin and approves like them: the token is the admin's choice.
    """
    if context is None or context.user_id is None:
        return False
    user = await hass.auth.async_get_user(context.user_id)
    return (
        user is not None
        and user.is_admin
        and user.is_active
        and not user.system_generated
    )


async def async_require_admin(hass: HomeAssistant, context: Context | None) -> None:
    """Refuse a change of a tablet's dashboard by a user who is not an admin.

    Automations have no user and are allowed. A script runs with the
    context of whoever started it, so a script started by a non-admin is
    refused.
    """
    if context is None or context.user_id is None:
        return
    if not await _async_user_is_admin(hass, context):
        raise Unauthorized(context=context)


async def async_show_dashboard(
    hass: HomeAssistant,
    assignments: Assignments,
    mac: str,
    url_path: str,
    entry_id: str,
    context: Context | None,
) -> None:
    """Show a dashboard on a tablet: the panel, the select and the action.

    An approved tablet: admins and automations (add-ons among them) may
    switch it. A tablet nobody approved yet: only an active admin who is a
    person approves it, by picking its first dashboard; entry_id is the
    ESPHome config entry it is approved under. Automations, add-ons with
    the Supervisor's access, scripts started by HA and non-admins cannot.
    """
    if not assignments.approved(mac):
        if not await _async_user_can_approve(hass, context):
            raise ApprovalNeeded
        assignments.async_approve(mac, url_path, entry_id)
        return
    await async_require_admin(hass, context)
    assignments.async_assign(mac, url_path)


def _text_or_none(value: Any) -> str | None:
    """Return a stored text, or None for anything else."""
    return value if isinstance(value, str) else None


def dashboard_order(manager: DashboardManager) -> list[dict[str, str]]:
    """Return the TAB-1 dashboards as [{"url_path", "title"}] in the one order.

    The order is (title in lower case, url_path) everywhere: the Home list,
    the select options, the drop-downs and "the first dashboard".
    """
    items = [
        {"url_path": url_path, "title": str(stored.get("title") or url_path)}
        for url_path, stored in manager.layouts.items()
    ]
    items.sort(key=lambda item: (item["title"].lower(), item["url_path"]))
    return items


def option_labels(dashboards: list[dict[str, str]]) -> dict[str, str]:
    """Return {url_path: option text}; every text is unique, ignoring case.

    A title that another dashboard's text also has (in any case) gets its
    url_path added, until no two texts are equal. A url_path holds no
    brackets or spaces, so two texts that end in their url_path never meet.
    The same rule is dashboardLabels in frontend/tablets.js
    (tests/label_cases.json).
    """
    labels = {item["url_path"]: item["title"] for item in dashboards}
    plain = set(labels)
    while True:
        counts = Counter(text.lower() for text in labels.values())
        clashing = [url for url in plain if counts[labels[url].lower()] > 1]
        if not clashing:
            return labels
        for url in clashing:
            labels[url] = f"{labels[url]} ({url})"
            plain.discard(url)


class Assignments:
    """Hold and store each tablet's dashboard and pairing secret."""

    def __init__(self, hass: HomeAssistant, manager: DashboardManager) -> None:
        """Create the store; call async_load before use."""
        self._hass = hass
        self._manager = manager
        self._store: Store[dict] = Store(hass, STORE_VERSION, STORE_KEY)
        self._tablets: dict[str, dict[str, Any]] = {}
        self._listeners: list[Callable[[str | None], None]] = []
        self._unsaved = False
        # Dashboards that exist but could not be read. Their tablets keep
        # their assignment and show their last layout.
        self.unreadable: set[str] = set()

    async def async_load(self) -> None:
        """Read the stored assignments. A missing file means none yet.

        A record without "approved" (or with anything but true) is a tablet
        nobody approved yet; one without "entry_id" was approved under no
        known entry, which async_see treats as another entry.
        """
        data = await self._store.async_load() or {}
        tablets = data.get("tablets")
        if not isinstance(tablets, dict):
            return
        for mac, record in tablets.items():
            if isinstance(mac, str) and isinstance(record, dict):
                self._tablets[mac] = {
                    "dashboard": _text_or_none(record.get("dashboard")),
                    "secret": _text_or_none(record.get("secret")),
                    "kid": _text_or_none(record.get("kid")),
                    "approved": record.get("approved") is True,
                    "entry_id": _text_or_none(record.get("entry_id")),
                }

    @callback
    def async_listen(
        self, listener: Callable[[str | None], None]
    ) -> Callable[[], None]:
        """Call listener(mac) after a tablet's record changed; None means many."""
        self._listeners.append(listener)

        def _remove() -> None:
            """Remove the listener."""
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    def _changed(self, mac: str | None) -> None:
        """Save and tell the listeners."""
        self._unsaved = True
        self._store.async_delay_save(self._data, SAVE_DELAY)
        for listener in list(self._listeners):
            listener(mac)

    def _data(self) -> dict:
        """Return the data to store."""
        self._unsaved = False
        return {"tablets": {mac: dict(record) for mac, record in self._tablets.items()}}

    async def async_flush(self) -> None:
        """Write pending changes now (on unload)."""
        if self._unsaved:
            await self._store.async_save(self._data())

    # ------------------------------------------------------------- reading

    def macs(self) -> list[str]:
        """Return the MACs of every stored tablet."""
        return list(self._tablets)

    def get(self, mac: str) -> dict[str, Any] | None:
        """Return a copy of a tablet's record, or None."""
        record = self._tablets.get(mac)
        return dict(record) if record is not None else None

    def approved(self, mac: str) -> bool:
        """Return whether an admin approved the tablet (and it was not re-adopted)."""
        record = self._tablets.get(mac)
        return bool(record and record["approved"])

    def entry_id(self, mac: str) -> str | None:
        """Return the ESPHome config entry the tablet was approved under."""
        record = self._tablets.get(mac)
        return record["entry_id"] if record and record["approved"] else None

    def dashboard(self, mac: str) -> str | None:
        """Return the url_path an approved tablet shows, or None.

        A tablet nobody approved shows nothing, whatever its record holds.
        """
        record = self._tablets.get(mac)
        return record["dashboard"] if record and record["approved"] else None

    def suggested(self, mac: str) -> str | None:
        """Return what a tablet that lost its approval showed before, or None.

        Only a suggestion for the panel's first choice, and only while that
        TAB-1 dashboard still exists.
        """
        record = self._tablets.get(mac)
        if not record or record["approved"]:
            return None
        url_path = record["dashboard"]
        return url_path if url_path in self._manager.layouts else None

    def secret(self, mac: str) -> bytes | None:
        """Return an approved tablet's pairing secret, or None."""
        record = self._tablets.get(mac)
        if not record or not record["approved"] or not record["secret"]:
            return None
        try:
            secret = bytes.fromhex(record["secret"])
        except ValueError:
            return None
        return secret if len(secret) == 32 else None

    def kid(self, mac: str) -> str | None:
        """Return the id of an approved tablet's pairing secret, or None."""
        record = self._tablets.get(mac)
        if not record or not record["approved"] or not record["secret"]:
            return None
        return record["kid"]

    def shown_on(self, url_path: str) -> list[str]:
        """Return the MACs of the approved tablets that show a dashboard, sorted."""
        return sorted(
            mac
            for mac, record in self._tablets.items()
            if record["approved"] and record["dashboard"] == url_path
        )

    def named(self) -> set[str]:
        """Return every dashboard a record names: shown, or a waiting suggestion."""
        return {
            record["dashboard"]
            for record in self._tablets.values()
            if record["dashboard"] is not None
        }

    def unreadable_dashboards(self) -> list[dict[str, str]]:
        """Return the dashboards that cannot be read, as [{"url_path", "title"}].

        The title is the one Home Assistant still has for the dashboard, so
        a tablet's row and its select keep the dashboard's name while its
        file is broken.
        """
        items = []
        for url_path in self.unreadable:
            if url_path in self._manager.layouts:
                continue
            info = async_dashboard_info(self._hass, url_path)
            title = str(info["title"]) if info else url_path
            items.append({"url_path": url_path, "title": title or url_path})
        items.sort(key=lambda item: (item["title"].lower(), item["url_path"]))
        return items

    def labels(self) -> dict[str, str]:
        """Return {url_path: option text} for the select and the panel.

        The TAB-1 dashboards in the one order, then the ones that cannot be
        read right now, so a tablet on one of those still has a name to show.
        """
        return option_labels(
            dashboard_order(self._manager) + self.unreadable_dashboards()
        )

    def first_dashboard(self, exclude: str | None = None) -> str | None:
        """Return the url_path of the first TAB-1 dashboard, or None."""
        for item in dashboard_order(self._manager):
            if item["url_path"] != exclude:
                return item["url_path"]
        return None

    # ------------------------------------------------------------- writing

    @callback
    def async_see(self, tablets: dict[str, str]) -> None:
        """Follow the tablets in the device registry: {mac: ESPHome entry id}.

        A tablet seen for the first time waits for an admin: no dashboard,
        not approved. An approved tablet that shows up under another ESPHome
        config entry (adopted again, or another device with its MAC) loses
        its approval and its pairing secret; what it showed is kept only as
        the panel's suggestion.
        """
        changed = False
        for mac, entry_id in tablets.items():
            record = self._tablets.get(mac)
            if record is None:
                self._tablets[mac] = {
                    "dashboard": None,
                    "secret": None,
                    "kid": None,
                    "approved": False,
                    "entry_id": None,
                }
                changed = True
            elif record["approved"] and record["entry_id"] != entry_id:
                _LOGGER.warning(
                    "A TAB-1 tablet came back under another ESPHome entry; "
                    "an admin must pick its dashboard again"
                )
                record.update(approved=False, secret=None, kid=None, entry_id=None)
                changed = True
        if changed:
            self._changed(None)

    @callback
    def async_fill(self) -> None:
        """Give the first dashboard to every approved tablet that has none."""
        if not self._manager.ready:
            return
        first = self.first_dashboard()
        if first is None:
            return
        changed = False
        for record in self._tablets.values():
            if record["approved"] and record["dashboard"] is None:
                record["dashboard"] = first
                changed = True
        if changed:
            self._changed(None)

    @callback
    def async_assign(self, mac: str, url_path: str | None) -> bool:
        """Set an approved tablet's dashboard.

        Returns False for an unknown tablet and for one nobody approved:
        that takes async_approve.
        """
        record = self._tablets.get(mac)
        if record is None or not record["approved"]:
            return False
        if record["dashboard"] != url_path:
            record["dashboard"] = url_path
            self._changed(mac)
        return True

    @callback
    def async_approve(self, mac: str, url_path: str, entry_id: str) -> bool:
        """Trust a tablet from now on, showing url_path (an admin picked it).

        entry_id is the ESPHome config entry the device has now. Returns
        False for an unknown tablet.
        """
        record = self._tablets.get(mac)
        if record is None:
            return False
        if not record["approved"]:
            # A secret from before the approval is never used.
            record.update(secret=None, kid=None)
        record.update(dashboard=url_path, approved=True, entry_id=entry_id)
        self._changed(mac)
        return True

    @callback
    def async_set_secret(self, mac: str, secret: bytes | None, kid: str | None) -> None:
        """Store an approved tablet's new pairing secret and its id."""
        record = self._tablets.get(mac)
        if record is None or not record["approved"]:
            return
        record["secret"] = secret.hex() if secret is not None else None
        record["kid"] = kid if secret is not None else None
        self._changed(mac)

    async def async_check_dashboard(self, url_path: str) -> None:
        """Move the tablets off a dashboard that is gone or no longer TAB-1.

        Called when the manager drops a dashboard, and for every dashboard a
        record names once the manager is ready. Approved tablets move to the
        first dashboard left; a waiting tablet loses it as its suggestion,
        so a new dashboard made later under the same url_path is never
        offered as what it showed before. A dashboard that cannot be read
        keeps its tablets; they show their last layout.
        """
        if not self._manager.ready or url_path in self._manager.layouts:
            self.unreadable.discard(url_path)
            return
        if url_path not in self.named():
            self.unreadable.discard(url_path)
            return
        result, config = await self._manager.async_probe(url_path)
        if url_path in self._manager.layouts:
            # Converted again while it was loaded.
            self.unreadable.discard(url_path)
            return
        gone = result in (PROBE_MISSING, PROBE_EMPTY) or (
            result == PROBE_OK and not is_tab_dashboard(config or {})
        )
        if not gone:
            if not self.shown_on(url_path):
                # Only a waiting tablet's suggestion: it stays, but is no
                # choice anywhere while the dashboard cannot be read.
                self.unreadable.discard(url_path)
            elif url_path not in self.unreadable:
                self.unreadable.add(url_path)
                self._changed(None)
            return
        self.unreadable.discard(url_path)
        target = self.first_dashboard(exclude=url_path)
        for record in self._tablets.values():
            if record["dashboard"] == url_path:
                # Approved tablets move; a waiting tablet loses the
                # suggestion, it never showed that dashboard here.
                record["dashboard"] = target if record["approved"] else None
        self._changed(None)

    @callback
    def async_converted(self, url_path: str) -> None:
        """Forget that a dashboard could not be read once it converts again."""
        if url_path in self.unreadable:
            self.unreadable.discard(url_path)
            self._changed(None)

    async def async_remove(self) -> None:
        """Delete the stored file with its secrets (integration removed)."""
        await self._store.async_remove()
