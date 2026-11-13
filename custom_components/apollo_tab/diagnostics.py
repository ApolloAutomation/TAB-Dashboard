"""Diagnostics for the Apollo TAB Dashboard integration."""

import copy
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .sensor import engine_unique_id
from .tablets import async_get_tablets

if TYPE_CHECKING:
    from . import ApolloTabData
    from .sender import TabletSender

REDACTED = "**REDACTED**"
WARNING_KEYS = ("code", "view", "section", "card", "page")


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return the tablets, the library and the dashboards.

    The output holds no full MAC address and no pairing secret. A tablet
    with its default name ends in the last three MAC bytes, put there by
    the firmware's name_add_mac_suffix option. That part of the name is
    left in, as ESPHome's own diagnostics do, so nothing else in the file
    may be worked out from the MAC: Home Assistant adds the integration's
    repair issues, and a waiting tablet's issue id holds its random device
    id (sender.new_tablet_issue_id). User-written dashboard text is
    redacted, because diagnostics get pasted into public issues.
    """
    entity_registry = er.async_get(hass)
    data = getattr(entry, "runtime_data", None)
    sender = data.sender if data is not None else None
    tablets: list[dict[str, Any]] = []
    for mac, device in async_get_tablets(hass).items():
        esphome_entry = hass.config_entries.async_get_entry(device.config_entry_id)
        entity_id = entity_registry.async_get_entity_id(
            "sensor", DOMAIN, engine_unique_id(mac)
        )
        state = hass.states.get(entity_id) if entity_id else None
        tablets.append(
            {
                "device_id": device.id,
                "name": device.name,
                "sw_version": device.sw_version,
                "disabled": device.disabled,
                "esphome_entry_state": (
                    esphome_entry.state.value if esphome_entry else None
                ),
                "engine_entity_id": entity_id,
                "engine_status": state.state if state else None,
                **_sender_diagnostics(sender, mac),
            }
        )
    tablets.sort(key=lambda tablet: tablet["device_id"])
    return {
        "tablet_count": len(tablets),
        "tablets": tablets,
        "sent_to_tablets": sender.any_on_tablet() if sender is not None else False,
        "unknown_inputs": sender.unknown_inputs if sender is not None else 0,
        "library": _library_diagnostics(data),
        "dashboards": _dashboards_diagnostics(data),
    }


def _sender_diagnostics(sender: TabletSender | None, mac: str) -> dict[str, Any]:
    """Return what the sender knows about one tablet, without its secret."""
    session = sender.session_for(mac) if sender is not None else None
    if session is None:
        return {
            "approved": False,
            "dashboard": None,
            "status": None,
            "reason": "",
            "retry": False,
            "engine": "",
            "paired": False,
            "input": None,
            "dropped_inputs": {},
        }
    return {
        "approved": session.approved,
        "dashboard": session.dashboard,
        "status": session.status,
        "reason": session.reason,
        "retry": session.retry,
        "engine": session.engine,
        "paired": session.paired,
        "input": session.input,
        "dropped_inputs": dict(sorted(session.dropped.items())),
    }


def _library_diagnostics(data: ApolloTabData | None) -> dict[str, Any]:
    """Return the library summary without messages or user text."""
    if data is None:
        return {"components": [], "errors": []}
    library = data.library
    components = [
        {
            "id": component_id,
            "version": component["version"],
            "source": component["source"],
            "sensitive": component["sensitive"],
            "approved": library.is_approved(component_id),
        }
        for component_id, component in library.components.items()
    ]
    components.sort(key=lambda component: component["id"])
    errors = [
        {"file": error["file"], "index": error["index"], "code": error["code"]}
        for error in library.errors
    ]
    return {"components": components, "errors": errors}


def _dashboards_diagnostics(data: ApolloTabData | None) -> list[dict[str, Any]]:
    """Return every stored layout with user-written text redacted."""
    if data is None:
        return []
    return [
        {
            "url_path": url_path,
            "mode": stored["mode"],
            "pages": len(stored["layout"]["pages"]),
            "hash": stored["layout"]["hash"],
            "warnings": [
                {key: warning.get(key) for key in WARNING_KEYS}
                for warning in stored["warnings"]
            ],
            "layout": _redact_layout(stored["layout"]),
        }
        for url_path, stored in sorted(data.manager.layouts.items())
    ]


def _redact_layout(layout: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy with titles and heading texts replaced."""
    redacted = copy.deepcopy(layout)
    for item in redacted.get("nav", []):
        if isinstance(item.get("title"), str):
            item["title"] = REDACTED
    for page in redacted.get("pages", []):
        if isinstance(page.get("title"), str):
            page["title"] = REDACTED
        for item in page.get("w", []):
            if item.get("t") == "heading" and isinstance(item.get("text"), str):
                item["text"] = REDACTED
            elif item.get("t") == "card":
                header = item.get("header") or {}
                if isinstance(header.get("title"), str):
                    header["title"] = REDACTED
    return redacted
