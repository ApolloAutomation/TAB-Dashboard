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
