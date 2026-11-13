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
    "async_probe_dashboard",
]

# What async_probe_dashboard found.
PROBE_MISSING = "missing"
PROBE_EMPTY = "empty"
PROBE_ERROR = "error"
PROBE_OK = "ok"

_LOGGER = logging.getLogger(__name__)

_KEY_WARNED: HassKey[bool] = HassKey(f"{DOMAIN}.lovelace_warned")
_KEY_UNREADABLE: HassKey[set[str]] = HassKey(f"{DOMAIN}.lovelace_unreadable")


def _warn_unreadable(hass: HomeAssistant, url_path: str, err: OSError) -> None:
    """Log once per dashboard and run that its file could not be read.

    Home Assistant reads a YAML dashboard's file time outside its own error
    handling, so a file deleted while Home Assistant runs raises an OSError
    here instead of ConfigNotFound.
    """
    warned = hass.data.setdefault(_KEY_UNREADABLE, set())
    if url_path in warned:
        return
    warned.add(url_path)
    _LOGGER.warning("Dashboard %s could not be read: %s", url_path, type(err).__name__)


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
    except OSError as err:
        _warn_unreadable(hass, url_path, err)
        return None
    except AttributeError:
        _warn_once(hass)
        return None
    if not isinstance(config, dict):
        return None
    return config


async def async_probe_dashboard(
    hass: HomeAssistant, url_path: str
) -> tuple[str, dict | None]:
    """Load a dashboard and say why it has no config, when it has none.

    Returns (PROBE_OK, config), (PROBE_EMPTY, None) when the dashboard exists
    without a saved config, (PROBE_MISSING, None) when there is no dashboard
    with this url_path, and (PROBE_ERROR, None) when it could not be read,
    for example a YAML dashboard with an error. Tablets are only moved away
    from a missing dashboard or one that is not a TAB-1 dashboard, never
    from one that could not be read.
    """
    dashboards = _dashboards(hass)
    if dashboards is None:
        return PROBE_ERROR, None
    cfg = dashboards.get(url_path)
    if cfg is None:
        return PROBE_MISSING, None
    try:
        config = await cfg.async_load(False)
    except ConfigNotFound:
        return PROBE_EMPTY, None
    except HomeAssistantError:
        return PROBE_ERROR, None
    except OSError as err:
        # Unreadable, not gone: the dashboard is still registered.
        _warn_unreadable(hass, url_path, err)
        return PROBE_ERROR, None
    except AttributeError:
        _warn_once(hass)
        return PROBE_ERROR, None
    if not isinstance(config, dict):
        return PROBE_ERROR, None
    return PROBE_OK, config
