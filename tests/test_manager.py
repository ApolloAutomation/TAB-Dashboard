"""Tests for the dashboard manager."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.apollo_tab import manager as manager_module

from .conftest import setup_integration

TAB_CONFIG: dict[str, Any] = {
    "apollo_tab": {"version": 1, "theme": "midnight"},
    "views": [
        {
            "type": "sections",
            "path": "home",
            "title": "Home",
            "max_columns": 3,
            "sections": [
                {
                    "type": "grid",
                    "cards": [
                        {
                            "type": "custom:apollo-tab-card",
                            "component": "apollo/light-tile",
                            "params": {"entity": "light.kitchen"},
                        }
                    ],
                }
            ],
        }
    ],
}

WARM_CONFIG: dict[str, Any] = {
    **TAB_CONFIG,
    "apollo_tab": {"version": 1, "theme": "warm"},
}

PLAIN_CONFIG: dict[str, Any] = {
    "views": [
        {
            "type": "sections",
            "path": "home",
            "title": "Home",
            "cards": [{"type": "markdown", "content": "Hello"}],
        }
    ],
}


async def _save_config(client: Any, msg_id: int, config: dict) -> None:
    """Save a dashboard config over the websocket."""
    await client.send_json(
        {
            "id": msg_id,
            "type": "lovelace/config/save",
            "url_path": "tab-1",
            "config": config,
        }
    )
    response = await client.receive_json()
    assert response["id"] == msg_id
    assert response["success"]


async def test_converts_tab_dashboard_on_save(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """Saving a TAB-1 dashboard stores a converted layout."""
    await setup_integration(hass, config_entry)
    await tab_dashboard(TAB_CONFIG)
    await hass.async_block_till_done()
    manager = config_entry.runtime_data.manager
    assert "tab-1" in manager.layouts
    entry = manager.layouts["tab-1"]
    assert entry["title"] == "TAB-1"
    assert entry["mode"] == "storage"
    assert entry["theme"] == "midnight"
    assert entry["layout"]["theme"]["id"] == "midnight"
    assert entry["layout"]["hash"]
    assert entry["bindings"]["slots"]


async def test_reconverts_on_change(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """Saving again re-converts and changes the layout hash."""
    await setup_integration(hass, config_entry)
    client = await tab_dashboard(TAB_CONFIG)
    manager = config_entry.runtime_data.manager
    first = manager.layouts["tab-1"]["layout"]["hash"]
    await _save_config(client, 5, WARM_CONFIG)
    await hass.async_block_till_done()
    assert manager.layouts["tab-1"]["layout"]["hash"] != first
    assert manager.layouts["tab-1"]["theme"] == "warm"


async def test_ignores_other_dashboards(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """Dashboards without the TAB-1 marker are ignored."""
    await setup_integration(hass, config_entry)
    await tab_dashboard(PLAIN_CONFIG)
    await hass.async_block_till_done()
    manager = config_entry.runtime_data.manager
    assert manager.layouts == {}


async def test_removed_when_marker_removed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """Removing the TAB-1 marker removes the stored layout."""
    await setup_integration(hass, config_entry)
    client = await tab_dashboard(TAB_CONFIG)
    manager = config_entry.runtime_data.manager
    assert "tab-1" in manager.layouts
    events: list[tuple[str, str]] = []
    manager.async_listen(lambda kind, path: events.append((kind, path)))
    await _save_config(client, 5, PLAIN_CONFIG)
    await hass.async_block_till_done()
    assert "tab-1" not in manager.layouts
    assert ("removed", "tab-1") in events


async def test_removed_when_dashboard_deleted(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """Deleting the dashboard removes the stored layout."""
    await setup_integration(hass, config_entry)
    client = await tab_dashboard(TAB_CONFIG)
    manager = config_entry.runtime_data.manager
    assert "tab-1" in manager.layouts
    events: list[tuple[str, str]] = []
    manager.async_listen(lambda kind, path: events.append((kind, path)))
    await client.send_json(
        {"id": 5, "type": "lovelace/dashboards/delete", "dashboard_id": "tab_1"}
    )
    response = await client.receive_json()
    assert response["success"]
    await hass.async_block_till_done()
    assert "tab-1" not in manager.layouts
    assert ("removed", "tab-1") in events


async def test_library_change_reconverts(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """Reloading the library converts all dashboards again."""
    await setup_integration(hass, config_entry)
    await tab_dashboard(TAB_CONFIG)
    manager = config_entry.runtime_data.manager
    assert "tab-1" in manager.layouts
    events: list[tuple[str, str]] = []
    manager.async_listen(lambda kind, path: events.append((kind, path)))
    await config_entry.runtime_data.library.async_load()
    await hass.async_block_till_done()
    assert ("converted", "tab-1") in events


async def test_theme_for(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """The theme comes from the stored layout with a default fallback."""
    await setup_integration(hass, config_entry)
    client = await tab_dashboard(TAB_CONFIG)
    manager = config_entry.runtime_data.manager
    assert manager.theme_for("tab-1") == "midnight"
    assert manager.theme_for("unknown") == "midnight"
    assert manager.theme_for(None) == "midnight"
    await _save_config(client, 5, WARM_CONFIG)
    await hass.async_block_till_done()
    assert manager.theme_for("tab-1") == "warm"


async def test_layout_persisted_to_store(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
    hass_storage: dict[str, Any],
) -> None:
    """Converted layouts are written to storage after a short delay."""
    await setup_integration(hass, config_entry)
    await tab_dashboard(TAB_CONFIG)
    manager = config_entry.runtime_data.manager
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
    await hass.async_block_till_done()
    stored = hass_storage["apollo_tab.layouts"]["data"]
    assert stored["tab-1"]["layout"] == manager.layouts["tab-1"]["layout"]
    assert "warnings" in stored["tab-1"]
    assert "bindings" not in stored["tab-1"]


async def test_values_snapshot(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """Slots are evaluated once and returned keyed by their slot number."""
    await setup_integration(hass, config_entry)
    hass.states.async_set("light.kitchen", "on")
    await tab_dashboard(TAB_CONFIG)
    manager = config_entry.runtime_data.manager
    values = await manager.async_values("tab-1")
    assert values
    slots = manager.layouts["tab-1"]["bindings"]["slots"]
    assert set(values) == {str(slot["n"]) for slot in slots}
    assert "on" in values.values()
    assert await manager.async_values("unknown") == {}


async def test_yaml_dashboard_with_future_mtime_finishes(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tmp_path: Path,
) -> None:
    """A YAML dashboard file with a future mtime converts once and finishes."""
    hass.config.config_dir = str(tmp_path)
    path = tmp_path / "tab.yaml"
    path.write_text("apollo_tab: {}\nviews: []\n", encoding="utf-8")
    dashboard_cfg = {"mode": "yaml", "filename": "tab.yaml", "title": "T"}
    lovelace_cfg = {"lovelace": {"dashboards": {"tab-yaml": dashboard_cfg}}}
    assert await async_setup_component(hass, "lovelace", lovelace_cfg)
    await setup_integration(hass, config_entry)
    manager = config_entry.runtime_data.manager
    future = time.time() + 60
    os.utime(path, (future, future))
    real_convert = manager_module.convert_dashboard
    calls = 0

    def counting(*args: Any, **kwargs: Any) -> Any:
        """Count the call and run the real conversion."""
        nonlocal calls
        calls += 1
        return real_convert(*args, **kwargs)

    with patch.object(manager_module, "convert_dashboard", counting):
        convert_task = hass.async_create_task(manager.async_convert("tab-yaml"))
        await asyncio.sleep(0.5)
        try:
            assert convert_task.done()
            await convert_task
        finally:
            convert_task.cancel()
    assert calls <= 2
    assert "tab-yaml" in manager.layouts


async def test_external_lovelace_event_still_converts(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """A lovelace_updated event from outside still triggers a conversion."""
    await setup_integration(hass, config_entry)
    await tab_dashboard(TAB_CONFIG)
    await hass.async_block_till_done()
    manager = config_entry.runtime_data.manager
    events: list[tuple[str, str]] = []
    manager.async_listen(lambda kind, path: events.append((kind, path)))
    hass.bus.async_fire("lovelace_updated", {"url_path": "tab-1"})
    await hass.async_block_till_done()
    assert ("converted", "tab-1") in events


async def test_yaml_future_mtime_browser_load_does_not_loop(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tmp_path: Path,
    hass_ws_client: Callable[..., Awaitable[Any]],
) -> None:
    """An edited YAML file with a future time converts once per browser load."""
    hass.config.config_dir = str(tmp_path)
    path = tmp_path / "tab.yaml"
    path.write_text(
        "apollo_tab: {version: 1}\nviews:\n  - type: sections\n    max_columns: 3\n"
        "    path: home\n    sections:\n      - type: grid\n        cards:\n"
        "          - {type: heading, heading: One}\n",
        encoding="utf-8",
    )
    dashboard_cfg = {"mode": "yaml", "filename": "tab.yaml", "title": "T"}
    lovelace_cfg = {"lovelace": {"dashboards": {"tab-yaml": dashboard_cfg}}}
    assert await async_setup_component(hass, "lovelace", lovelace_cfg)
    await setup_integration(hass, config_entry)
    manager = config_entry.runtime_data.manager
    await manager.async_convert_all()
    await hass.async_block_till_done()
    first = manager.layouts["tab-yaml"]["layout"]["hash"]
    path.write_text(path.read_text().replace("One", "Two"), encoding="utf-8")
    future = time.time() + 60
    os.utime(path, (future, future))
    loads = 0
    real_load = manager_module.compat.async_load_dashboard_config

    async def counting(*args: Any, **kwargs: Any) -> Any:
        """Count the load and run the real one."""
        nonlocal loads
        loads += 1
        return await real_load(*args, **kwargs)

    client = await hass_ws_client(hass)
    with patch.object(manager_module.compat, "async_load_dashboard_config", counting):
        await client.send_json_auto_id(
            {"type": "lovelace/config", "url_path": "tab-yaml"}
        )
        assert (await client.receive_json())["success"]
        for _ in range(5):
            await hass.async_block_till_done()
            await asyncio.sleep(0.05)
    assert manager.layouts["tab-yaml"]["layout"]["hash"] != first
    assert loads <= 2
