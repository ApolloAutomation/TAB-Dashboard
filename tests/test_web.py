"""Tests for static file serving and frontend registration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apollo_tab import web

from .conftest import setup_integration


async def test_static_served_with_cache_headers(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_client: Callable[..., Awaitable[Any]],
) -> None:
    """The entry module is served with far-future cache headers."""
    await setup_integration(hass, config_entry)
    module_url = config_entry.runtime_data.module_url
    assert module_url.startswith(f"{web.STATIC_URL_BASE}/")
    assert module_url.endswith("/apollo-tab.js")
    client = await hass_client()
    response = await client.get(module_url)
    assert response.status == 200
    assert response.headers["Cache-Control"] == "public, max-age=2678400"
    assert "javascript" in response.headers["Content-Type"]


def test_token_changes_with_content(tmp_path: Path) -> None:
    """The token reflects the folder content, not the folder itself."""
    folder_a = tmp_path / "a"
    folder_b = tmp_path / "b"
    for folder in (folder_a, folder_b):
        (folder / "sub").mkdir(parents=True)
        (folder / "apollo-tab.js").write_text("one", encoding="utf-8")
        (folder / "sub" / "extra.js").write_text("x", encoding="utf-8")
    token = web.compute_token(folder_a)
    assert len(token) == 12
    assert web.compute_token(folder_a) == token
    assert web.compute_token(folder_b) == token
    (folder_b / "apollo-tab.js").write_text("two", encoding="utf-8")
    assert web.compute_token(folder_b) != token
    (folder_b / "sub" / "extra.js").rename(folder_b / "sub" / "renamed.js")
    assert web.compute_token(folder_b) != token


async def test_module_and_panel_registered_when_frontend_loaded(
    hass: HomeAssistant,
) -> None:
    """The module is added and the panel registered when the frontend exists."""
    hass.config.components.update({"frontend"})
    hass.data[web.frontend.DATA_PANELS] = {web.PANEL_URL_PATH: object()}
    module_url = "/apollo_tab_static/0123456789ab/apollo-tab.js"
    with (
        patch.object(web.frontend, "add_extra_js_url") as mock_add,
        patch.object(web.frontend, "async_remove_panel") as mock_remove,
        patch.object(
            web.panel_custom, "async_register_panel", new=AsyncMock()
        ) as mock_register,
    ):
        await web.async_add_frontend(hass, module_url)
    mock_add.assert_called_once_with(hass, module_url)
    mock_remove.assert_called_once_with(hass, web.PANEL_URL_PATH, warn_if_unknown=False)
    mock_register.assert_awaited_once()
    kwargs = mock_register.await_args.kwargs
    assert kwargs["frontend_url_path"] == web.PANEL_URL_PATH
    assert kwargs["webcomponent_name"] == "apollo-tab-panel"
    assert kwargs["sidebar_title"] == "TAB-1"
    assert kwargs["sidebar_icon"] == "mdi:tablet-dashboard"
    assert kwargs["module_url"] == module_url
    assert kwargs["require_admin"] is True


async def test_panel_registered_without_panel_custom(hass: HomeAssistant) -> None:
    """The panel registers without the panel_custom integration being loaded."""
    hass.config.components.add("frontend")
    assert "panel_custom" not in hass.config.components
    module_url = "/apollo_tab_static/0123456789ab/apollo-tab.js"
    with patch.object(web.frontend, "add_extra_js_url"):
        await web.async_add_frontend(hass, module_url)
    panel = hass.data[web.frontend.DATA_PANELS][web.PANEL_URL_PATH]
    assert panel.component_name == "custom"
    assert panel.require_admin is True
    assert panel.sidebar_title == "TAB-1"
    assert panel.sidebar_icon == "mdi:tablet-dashboard"
    assert panel.config["_panel_custom"]["name"] == "apollo-tab-panel"
    assert panel.config["_panel_custom"]["module_url"] == module_url
    assert panel.config["_panel_custom"]["embed_iframe"] is False


async def test_setup_registers_panel_without_panel_custom(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Setting up the entry registers the panel without panel_custom loaded."""
    hass.config.components.add("frontend")
    with patch.object(web.frontend, "add_extra_js_url"):
        await setup_integration(hass, config_entry)
    panel = hass.data[web.frontend.DATA_PANELS][web.PANEL_URL_PATH]
    assert (
        panel.config["_panel_custom"]["module_url"]
        == config_entry.runtime_data.module_url
    )


async def test_nothing_registered_without_frontend(hass: HomeAssistant) -> None:
    """Without the frontend no module or panel is touched."""
    with (
        patch.object(web.frontend, "add_extra_js_url") as mock_add,
        patch.object(web.frontend, "remove_extra_js_url") as mock_remove_js,
        patch.object(web.frontend, "async_remove_panel") as mock_remove_panel,
        patch.object(
            web.panel_custom, "async_register_panel", new=AsyncMock()
        ) as mock_register,
    ):
        await web.async_add_frontend(hass, "/apollo_tab_static/x/apollo-tab.js")
        web.async_remove_frontend(hass, "/apollo_tab_static/x/apollo-tab.js")
    mock_add.assert_not_called()
    mock_remove_js.assert_not_called()
    mock_remove_panel.assert_not_called()
    mock_register.assert_not_called()


async def test_reload_does_not_register_static_twice(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_client: Callable[..., Awaitable[Any]],
) -> None:
    """The static path is registered only once per Home Assistant run."""
    await setup_integration(hass, config_entry)
    module_url = config_entry.runtime_data.module_url
    assert await web.async_register_static(hass) == module_url
    client = await hass_client()
    response = await client.get(module_url)
    assert response.status == 200


async def test_unload_removes_module_and_panel(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Unloading the entry removes the module URL and the panel."""
    hass.config.components.add("frontend")
    with (
        patch.object(web.frontend, "add_extra_js_url"),
        patch.object(web.frontend, "remove_extra_js_url") as mock_remove_js,
        patch.object(web.frontend, "async_remove_panel") as mock_remove_panel,
    ):
        await setup_integration(hass, config_entry)
        module_url = config_entry.runtime_data.module_url
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
    mock_remove_js.assert_called_once_with(hass, module_url)
    mock_remove_panel.assert_called_once_with(
        hass, web.PANEL_URL_PATH, warn_if_unknown=False
    )
