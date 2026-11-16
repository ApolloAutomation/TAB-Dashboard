"""Tests for the lovelace compatibility layer."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apollo_tab import compat

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


async def test_paths_and_info(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """Paths and info reflect the created dashboard."""
    await setup_integration(hass, config_entry)
    await tab_dashboard(TAB_CONFIG)
    assert compat.async_dashboard_paths(hass) == ["tab-1"]
    assert compat.async_dashboard_info(hass, "tab-1") == {
        "title": "TAB-1",
        "mode": "storage",
    }


async def test_load_config(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """The saved config is returned for an existing dashboard."""
    await setup_integration(hass, config_entry)
    await tab_dashboard(TAB_CONFIG)
    config = await compat.async_load_dashboard_config(hass, "tab-1")
    assert config is not None
    assert config["apollo_tab"] == {"version": 1, "theme": "midnight"}
    assert len(config["views"]) == 1


async def test_missing_dashboard_returns_none(hass: HomeAssistant) -> None:
    """Unknown dashboards yield empty results."""
    assert compat.async_dashboard_paths(hass) == []
    assert compat.async_dashboard_info(hass, "nope") is None
    assert await compat.async_load_dashboard_config(hass, "nope") is None


async def test_degrades_without_lovelace(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Without lovelace data the functions degrade and warn only once."""
    hass.data.pop(compat.LOVELACE_DATA, None)
    assert compat.async_dashboard_paths(hass) == []
    assert compat.async_dashboard_info(hass, "tab-1") is None
    assert await compat.async_load_dashboard_config(hass, "tab-1") is None
    matches = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and "Dashboards could not be read" in record.getMessage()
    ]
    assert len(matches) == 1


async def test_internals_shape(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """The lovelace internals used by the integration still exist."""
    await setup_integration(hass, config_entry)
    await tab_dashboard(TAB_CONFIG)
    assert compat.LOVELACE_DATA is not None
    data = hass.data[compat.LOVELACE_DATA]
    dashboards = data.dashboards
    assert isinstance(dashboards, dict)
    cfg = dashboards["tab-1"]
    assert callable(cfg.async_load)
    assert cfg.mode == "storage"
    assert isinstance(cfg.config, dict)


async def test_yaml_dashboard_file_deleted_while_running(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A YAML file removed after its first load is unreadable, not an error.

    Home Assistant reads the file time of a cached YAML dashboard outside its
    own error handling, so the removed file raises FileNotFoundError.
    """
    from homeassistant.components.lovelace.dashboard import LovelaceYAML

    await setup_integration(hass, config_entry)
    hass.config.config_dir = str(tmp_path)
    path = tmp_path / "tab-yaml.yaml"
    path.write_text("apollo_tab:\n  version: 1\nviews: []\n")
    dashboard = LovelaceYAML(
        hass,
        "tab-yaml",
        {"mode": "yaml", "filename": "tab-yaml.yaml", "title": "Yaml"},
    )
    hass.data[compat.LOVELACE_DATA].dashboards["tab-yaml"] = dashboard
    assert await compat.async_probe_dashboard(hass, "tab-yaml") == (
        compat.PROBE_OK,
        {"apollo_tab": {"version": 1}, "views": []},
    )

    path.unlink()
    assert await compat.async_probe_dashboard(hass, "tab-yaml") == (
        compat.PROBE_ERROR,
        None,
    )
    assert await compat.async_load_dashboard_config(hass, "tab-yaml") is None
    warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and "tab-yaml could not be read" in record.getMessage()
    ]
    assert len(warnings) == 1


async def test_yaml_dashboard_file_missing_before_first_load(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A YAML file that is missing at the first load is unreadable, not gone.

    Without a cached copy Home Assistant raises ConfigNotFound for it, as
    for a storage dashboard that was never saved. The YAML dashboard is
    still registered, so its tablets must stay on it.
    """
    from homeassistant.components.lovelace.dashboard import LovelaceYAML

    await setup_integration(hass, config_entry)
    hass.config.config_dir = str(tmp_path)
    dashboard = LovelaceYAML(
        hass,
        "tab-yaml",
        {"mode": "yaml", "filename": "tab-yaml.yaml", "title": "Yaml"},
    )
    hass.data[compat.LOVELACE_DATA].dashboards["tab-yaml"] = dashboard

    assert await compat.async_probe_dashboard(hass, "tab-yaml") == (
        compat.PROBE_ERROR,
        None,
    )
    assert await compat.async_probe_dashboard(hass, "tab-yaml") == (
        compat.PROBE_ERROR,
        None,
    )
    assert await compat.async_load_dashboard_config(hass, "tab-yaml") is None
    warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and "tab-yaml could not be read" in record.getMessage()
    ]
    assert len(warnings) == 1

    # Once the file is there, the dashboard reads as any other.
    (tmp_path / "tab-yaml.yaml").write_text("apollo_tab:\n  version: 1\nviews: []\n")
    assert await compat.async_probe_dashboard(hass, "tab-yaml") == (
        compat.PROBE_OK,
        {"apollo_tab": {"version": 1}, "views": []},
    )


async def test_storage_dashboard_without_config_is_empty(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client,
) -> None:
    """A storage dashboard that was never saved is empty; an unknown one is missing."""
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "lovelace/dashboards/create",
            "url_path": "tab-new",
            "title": "New",
            "mode": "storage",
        }
    )
    response = await client.receive_json()
    assert response["success"], response

    assert await compat.async_probe_dashboard(hass, "tab-new") == (
        compat.PROBE_EMPTY,
        None,
    )
    assert await compat.async_probe_dashboard(hass, "nope") == (
        compat.PROBE_MISSING,
        None,
    )
