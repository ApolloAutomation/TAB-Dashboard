"""Read dashboard information from Home Assistant's lovelace internals.

This is the only module that imports from the lovelace integration, so a
breaking change in its internals is contained in this single file.
"""

from __future__ import annotations

import logging

from homeassistant.const import EVENT_LOVELACE_UPDATED
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN

try:
    from homeassistant.components.lovelace.const import (
        LOVELACE_DATA,
        ConfigNotFound,
    )
except ImportError:
    LOVELACE_DATA = None
    ConfigNotFound = None

__all__ = [
    "EVENT_LOVELACE_UPDATED",
    "async_dashboard_info",
    "async_dashboard_paths",
    "async_load_dashboard_config",
]

_LOGGER = logging.getLogger(__name__)

_KEY_WARNED: HassKey[bool] = HassKey(f"{DOMAIN}.lovelace_warned")


def _warn_once(hass: HomeAssistant) -> None:
    """Log the degradation warning once per Home Assistant run."""
    if hass.data.get(_KEY_WARNED):
        return
    hass.data[_KEY_WARNED] = True
    _LOGGER.warning("Dashboards could not be read from this Home Assistant version")


def _dashboards(hass: HomeAssistant) -> dict | None:
    """Return the dashboards mapping, or None when it cannot be read."""
    if LOVELACE_DATA is None:
        _warn_once(hass)
        return None
    data = hass.data.get(LOVELACE_DATA)
    dashboards = getattr(data, "dashboards", None)
    if not isinstance(dashboards, dict):
        _warn_once(hass)
        return None
    return dashboards


@callback
def async_dashboard_paths(hass: HomeAssistant) -> list[str]:
    """Return the url_path of every dashboard, sorted."""
    dashboards = _dashboards(hass)
    if dashboards is None:
        return []
    # The legacy default dashboard is stored under the None key.
    return sorted(path for path in dashboards if path is not None)


@callback
def async_dashboard_info(hass: HomeAssistant, url_path: str) -> dict[str, str] | None:
    """Return {"title": ..., "mode": ...} for a dashboard, or None."""
    dashboards = _dashboards(hass)
    if dashboards is None:
        return None
    cfg = dashboards.get(url_path)
    if cfg is None:
        return None
    try:
        mode = cfg.mode
        config = cfg.config
    except AttributeError:
        _warn_once(hass)
        return None
    title = url_path
    if isinstance(config, dict) and config.get("title"):
        title = str(config["title"])
    return {"title": title, "mode": str(mode)}


async def async_load_dashboard_config(
    hass: HomeAssistant, url_path: str
) -> dict | None:
    """Return the dashboard's config, or None if it does not exist or has no config."""
    dashboards = _dashboards(hass)
    if dashboards is None:
        return None
    cfg = dashboards.get(url_path)
    if cfg is None:
        return None
    try:
        config = await cfg.async_load(False)
    except ConfigNotFound:
        return None
    except HomeAssistantError:
        return None
    except AttributeError:
        _warn_once(hass)
        return None
    if not isinstance(config, dict):
        return None
    return config
