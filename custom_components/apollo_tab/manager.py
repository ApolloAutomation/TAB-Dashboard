"""Keep TAB-1 dashboard layouts converted, persisted and evaluated."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import TemplateError

from . import compat, live
from .const import DOMAIN
from .facts import FactKeeper
from .library import Library
from .maker.const import DEFAULT_THEME
from .maker.convert import convert_dashboard
from .maker.features import dashboard_facts
from .maker.schema import is_tab_dashboard

_LOGGER = logging.getLogger(__name__)

# Seconds after an unchanged YAML load during which the next lovelace_updated
# for that dashboard is treated as the echo of that load.
_ECHO_WINDOW = 2.0


class DashboardManager:
    """Convert TAB-1 dashboards and serve their layouts and live values."""

    def __init__(
        self,
        hass: HomeAssistant,
        library: Library,
        facts: FactKeeper | None = None,
        icons: dict | None = None,
    ) -> None:
        """Initialise the manager.

        icons is the contract's icons.json: version 1 forms of schema 2
        cards keep only its icons of level 1, and a layout v2 is fitted to
        a tablet with it.
        """
        self._hass = hass
        self.library = library
        self.icons = icons
        # What the devices can do; only this manager's conversions of saved
        # dashboards write it.
        self.facts = facts if facts is not None else FactKeeper(hass)
        self.layouts: dict[str, dict] = {}
        # What each stored layout was made from, and the layouts v2 made
        # from the same for the tablets that take them, by their caps.
        self._made_from: dict[str, dict] = {}
        self._versions: dict[str, dict[str, dict]] = {}
        self._store: Store[dict] = Store(hass, 1, f"{DOMAIN}.layouts")
        self._listeners: list[Callable[[str, str], None]] = []
        self._unsubscribers: list[Callable[[], None]] = []
        self._converting: set[str] = set()
        self._pending: set[str] = set()
        self._loading: set[str] = set()
        self._sources: dict[str, dict] = {}
        self._quiet_until: dict[str, float] = {}
        self._event_driven: set[str] = set()
        # True once the first conversion of every dashboard has finished.
        # Nothing is reassigned or sent to a tablet before that.
        self.ready = False
        self._ready_listeners: list[Callable[[], None]] = []

    async def async_start(self) -> None:
        """Listen for dashboard and library changes and convert at start."""
        self._unsubscribers.append(
            self._hass.bus.async_listen(
                compat.EVENT_LOVELACE_UPDATED, self._handle_lovelace_updated
            )
        )
        self._unsubscribers.append(
            self.library.async_listen(self._handle_library_change)
        )
        self._unsubscribers.append(async_at_started(self._hass, self._async_started))
        self._unsubscribers.append(self.facts.async_listen(self._handle_facts_change))

    @callback
    def async_stop(self) -> None:
        """Remove the bus, library and start listeners."""
        while self._unsubscribers:
            self._unsubscribers.pop()()

    async def _async_started(self, hass: HomeAssistant) -> None:
        """Convert all dashboards once Home Assistant has started."""
        try:
            await self.async_convert_all()
            # Devices of dashboards that are gone since the last run.
            self.facts.async_prune()
        finally:
            self.ready = True
            for listener in list(self._ready_listeners):
                listener()

    @callback
    def async_when_ready(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Run listener once the first conversion has finished; return a remover.

        The listener runs at once when the manager is ready already.
        """
        if self.ready:
            listener()
            return lambda: None
        self._ready_listeners.append(listener)

        def _remove() -> None:
            """Remove the listener if it has not run."""
            if listener in self._ready_listeners:
                self._ready_listeners.remove(listener)

        return _remove

    async def async_probe(self, url_path: str) -> tuple[str, dict | None]:
        """Load a dashboard to learn whether it is gone, other, or unreadable.

        The lovelace_updated event that a YAML load may fire is ignored like
        the one of the manager's own loads.
        """
        self._loading.add(url_path)
        try:
            return await compat.async_probe_dashboard(self._hass, url_path)
        finally:
            self._loading.discard(url_path)

    @callback
    def async_refresh_titles(self) -> bool:
        """Read every stored dashboard's title again; return whether one changed.

        Renaming a dashboard fires no lovelace_updated event, so the title
        is read again when the panels change.
        """
        changed = False
        for url_path, stored in self.layouts.items():
            info = compat.async_dashboard_info(self._hass, url_path)
            if info is None:
                continue
            if stored.get("title") != info["title"]:
                stored["title"] = info["title"]
                changed = True
                # The panel lists dashboards by title; tell it to read again.
                self._notify("renamed", url_path)
        return changed

    @callback
    def _handle_lovelace_updated(self, event: Event) -> None:
        """Queue a conversion for the dashboard that fired the event."""
        url_path = event.data.get("url_path")
        if url_path is None or url_path in self._loading:
            return
        quiet_until = self._quiet_until.pop(url_path, None)
        if quiet_until is not None and self._hass.loop.time() < quiet_until:
            return
        self._event_driven.add(url_path)
        self._hass.async_create_task(self.async_convert(url_path))

    @callback
    def _handle_facts_change(self, url_path: str) -> None:
        """Convert a dashboard again after a fact one of its cards names changed."""
        self._hass.async_create_task(self.async_convert(url_path))

    @callback
    def _handle_library_change(self) -> None:
        """Convert everything again when the library changes."""
        self._hass.async_create_task(self.async_convert_all())

    async def async_convert(self, url_path: str) -> None:
        """Convert one dashboard, collapsing concurrent requests.

        A request arriving while a conversion runs is remembered and triggers
        exactly one more conversion. The lovelace_updated event fired by the
        manager's own dashboard load is ignored via the _loading set.
        """
        if url_path in self._converting:
            self._pending.add(url_path)
            return
        self._converting.add(url_path)
        try:
            await self._async_convert(url_path)
            while url_path in self._pending:
                self._pending.discard(url_path)
                await self._async_convert(url_path)
        finally:
            self._converting.discard(url_path)

    async def _async_convert(self, url_path: str) -> None:
        """Load and convert one dashboard."""
        # Loading a YAML dashboard fires lovelace_updated when its file mtime
        # is newer than the cached copy; flag the load so the event handler
        # ignores that self-inflicted event instead of converting forever.
        event_driven = url_path in self._event_driven
        self._event_driven.discard(url_path)
        self._loading.add(url_path)
        try:
            config = await compat.async_load_dashboard_config(self._hass, url_path)
        finally:
            self._loading.discard(url_path)
        if config is None or not is_tab_dashboard(config):
            self._sources.pop(url_path, None)
            self._drop(url_path)
            return
        info = compat.async_dashboard_info(self._hass, url_path) or {}
        # A YAML file whose time is ahead of the clock makes every load fire
        # lovelace_updated, and that event can arrive after _loading is
        # cleared. An event-driven load of an unchanged file means this load
        # was such an echo, so the next event shortly after is ignored instead
        # of loading again.
        if (
            event_driven
            and info.get("mode") == "yaml"
            and self._sources.get(url_path) == config
        ):
            self._quiet_until[url_path] = self._hass.loop.time() + _ECHO_WINDOW
        self._sources[url_path] = config
        components = self.library.components
        named = dashboard_facts(config, components)
        facts = self.facts.facts_for(named)
        approved = self.library.approved_ids()
        themes = self.library.themes
        status = self.library.status
        try:
            result = convert_dashboard(
                config,
                components=components,
                themes=themes,
                approved=approved,
                facts=facts,
                icons=self.icons,
                status=status,
            )
        except Exception:
            _LOGGER.exception("Conversion of dashboard %s failed", url_path)
            return
        self._made_from[url_path] = {
            "config": config,
            "components": components,
            "themes": themes,
            "status": status,
            "approved": approved,
            "facts": facts,
        }
        self._versions[url_path] = {}
        self.facts.async_converted(url_path, named, facts)
        layout: dict = result["layout"]
        theme = layout.get("theme", {}).get("id", DEFAULT_THEME)
        self.layouts[url_path] = {
            "layout": layout,
            "bindings": result["bindings"],
            # The Components this layout was made from, by their hashes: a
            # tap on a tablet runs only while its Component is still that one.
            "revisions": {
                component_id: component.get("hash")
                for component_id, component in components.items()
            },
            "warnings": result["warnings"],
            "title": info.get("title", url_path),
            "mode": info.get("mode", "storage"),
            "theme": theme,
            # Cards of schema 2 that a version 1 tablet shows simpler.
            "simpler": result.get("simpler", 0),
        }
        self._async_save()
        self._notify("converted", url_path)

    def layout_for(
        self, url_path: str, dl: int, caps: dict[str, Any] | None = None
    ) -> dict:
        """Return the stored layout of a dashboard for one layout version.

        Version 1 is the stored layout. Version 2 is made from the same
        dashboard, facts and library the first time a tablet that takes it
        asks, fitted to that tablet's caps, and kept until the dashboard is
        converted again (C.4: a second run happens only while a tablet of
        the other version is assigned). If that run fails, the version 1
        layout stands in: a tablet that takes version 2 takes version 1 too.
        Raises KeyError for a dashboard with no stored layout.
        """
        entry = self.layouts[url_path]
        made_from = self._made_from.get(url_path)
        if dl != 2 or made_from is None:
            return entry
        key = json.dumps(caps or {}, sort_keys=True, default=str)
        versions = self._versions.setdefault(url_path, {})
        if key in versions:
            return versions[key]
        try:
            result = convert_dashboard(
                made_from["config"],
                components=made_from["components"],
                themes=made_from["themes"],
                approved=made_from["approved"],
                facts=made_from["facts"],
                dl=2,
                icons=self.icons,
                caps=caps,
                status=made_from.get("status"),
                confirm=self._cover_questions,
            )
        except Exception:
            _LOGGER.exception(
                "Conversion of dashboard %s for version 2 failed", url_path
            )
            return entry
        versions[key] = {
            **entry,
            "layout": result["layout"],
            "bindings": result["bindings"],
            "warnings": result["warnings"],
            "simpler": 0,
            "dl": 2,
        }
        return versions[key]

    def _cover_questions(self, bindings: dict) -> dict[int, str]:
        """Return the cover questions the sender writes into a device layout."""
        return live.cover_questions(self._hass, self.library.components, bindings)

    async def async_convert_all(self) -> None:
        """Convert every dashboard and forget dashboards that are gone."""
        paths = compat.async_dashboard_paths(self._hass)
        for path in paths:
            await self.async_convert(path)
        for path in list(self.layouts):
            if path not in paths:
                self._drop(path)

    def theme_for(self, url_path: str | None) -> str:
        """Return the dashboard's theme id, or the default theme."""
        if url_path is None or url_path not in self.layouts:
            return DEFAULT_THEME
        return self.layouts[url_path].get("theme", DEFAULT_THEME)

    def async_listen(self, listener: Callable[[str, str], None]) -> Callable[[], None]:
        """Register a listener for layout changes and return its remover.

        The kinds are "converted", "removed" (a stored layout went away),
        "renamed" (the title changed) and "absent" (a dashboard that has no
        stored layout was looked at and still has none).
        """
        self._listeners.append(listener)

        def _remove() -> None:
            """Remove the listener."""
            self._listeners.remove(listener)

        return _remove

    async def async_values(self, url_path: str) -> dict[str, Any]:
        """Evaluate every slot of the dashboard once and return the values."""
        entry = self.layouts.get(url_path)
        if entry is None:
            return {}
        return await self._async_evaluate_slots(entry["bindings"])

    async def async_preview(self, config: dict, dl: int = 1) -> dict[str, Any]:
        """Convert a config that is not saved and evaluate its slots once.

        dl is the layout version to make (1 or 2). Nothing is stored and no
        listener is told.
        """
        components = self.library.components
        result = convert_dashboard(
            config,
            components=components,
            themes=self.library.themes,
            approved=self.library.approved_ids(),
            # Read only: a preview never writes the facts store.
            facts=self.facts.facts_for(dashboard_facts(config, components)),
            dl=dl,
            icons=self.icons,
            status=self.library.status,
            confirm=self._cover_questions,
        )
        return {
            "layout": result["layout"],
            "warnings": result["warnings"],
            "values": await self._async_evaluate_slots(result["bindings"]),
            "sources": result["sources"],
        }

    async def _async_evaluate_slots(self, bindings: dict) -> dict[str, Any]:
        """Evaluate every slot of some bindings once, keyed by slot number.

        A slot whose template or action fails is left out.
        """
        values: dict[str, Any] = {}
        for slot in bindings.get("slots", []):
            try:
                values[str(slot["n"])] = await live.async_evaluate_slot(
                    self._hass, slot
                )
            except HomeAssistantError, TemplateError:
                continue
        return values

    @callback
    def _async_save(self) -> None:
        """Persist the layouts to storage with a short delay."""

        def _data() -> dict[str, dict]:
            """Return the serialisable layout data."""
            return {
                path: {"layout": entry["layout"], "warnings": entry["warnings"]}
                for path, entry in self.layouts.items()
            }

        self._store.async_delay_save(_data, 5)

    @callback
    def _drop(self, url_path: str) -> None:
        """Remove a stored layout and tell the listeners.

        A dashboard without a stored layout gives "absent": it may be one
        that could not be read before and is deleted now, and its tablets
        must still move on.
        """
        self.facts.async_forget(url_path)
        if url_path not in self.layouts:
            self._notify("absent", url_path)
            return
        del self.layouts[url_path]
        self._made_from.pop(url_path, None)
        self._versions.pop(url_path, None)
        self._async_save()
        self._notify("removed", url_path)

    def _notify(self, kind: str, url_path: str) -> None:
        """Run every listener with the kind of change and the path."""
        for listener in list(self._listeners):
            listener(kind, url_path)
