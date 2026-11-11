"""Serve the frontend files and register the module and the sidebar panel."""

from __future__ import annotations

import hashlib
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN

STATIC_URL_BASE = "/apollo_tab_static"
PANEL_URL_PATH = "apollo-tab"

_FRONTEND_DIR = Path(__file__).parent / "frontend"
_KEY_MODULE_URL: HassKey[str] = HassKey(f"{DOMAIN}.module_url")


def compute_token(folder: Path) -> str:
    """Return a short content hash of every file below the folder."""
    digest = hashlib.sha256()
    files = [path for path in folder.rglob("*") if path.is_file()]
    files.sort(key=lambda path: path.relative_to(folder).as_posix())
    for path in files:
        digest.update(path.relative_to(folder).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


async def async_register_static(hass: HomeAssistant) -> str:
    """Serve the frontend folder once per run and return the entry module URL."""
    # A registered static path cannot be removed, so register it only once.
    if module_url := hass.data.get(_KEY_MODULE_URL):
        return module_url
    token = await hass.async_add_executor_job(compute_token, _FRONTEND_DIR)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(f"{STATIC_URL_BASE}/{token}", str(_FRONTEND_DIR), True)]
    )
    module_url = f"{STATIC_URL_BASE}/{token}/apollo-tab.js"
    hass.data[_KEY_MODULE_URL] = module_url
    return module_url


async def async_add_frontend(hass: HomeAssistant, module_url: str) -> None:
    """Add the module URL and the sidebar panel when the frontend is loaded."""
    if "frontend" not in hass.config.components:
        return
    frontend.add_extra_js_url(hass, module_url)
    if PANEL_URL_PATH in hass.data.get(frontend.DATA_PANELS, {}):
        frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    # panel_custom.async_register_panel is a plain helper that only talks to
    # the frontend; it does not need the panel_custom integration set up.
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name="apollo-tab-panel",
        sidebar_title="TAB-1",
        sidebar_icon="mdi:tablet-dashboard",
        module_url=module_url,
        embed_iframe=False,
        require_admin=True,
        config={},
    )


@callback
def async_remove_frontend(hass: HomeAssistant, module_url: str) -> None:
    """Remove the module URL and the sidebar panel."""
    if "frontend" not in hass.config.components:
        return
    frontend.remove_extra_js_url(hass, module_url)
    frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
