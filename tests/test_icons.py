"""Tests for the icon and translation files."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.apollo_tab.select import DashboardSelect
from custom_components.apollo_tab.sensor import DashboardEngineSensor

COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "apollo_tab"


def test_icons_match_sensor_translation_key() -> None:
    """The sensor's translation key has an icon and a translation."""
    icons = json.loads((COMPONENT_DIR / "icons.json").read_text(encoding="utf-8"))
    translations = json.loads(
        (COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8")
    )
    sensor = DashboardEngineSensor(MagicMock(), "mac", MagicMock(), "unique-id")
    expected = {sensor.translation_key}
    assert set(icons["entity"]["sensor"]) == expected
    assert expected <= set(translations["entity"]["sensor"])


def test_select_translation_key_has_a_name() -> None:
    """The select's translation key has a translated name."""
    translations = json.loads(
        (COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8")
    )
    select = DashboardSelect(MagicMock(), "mac", MagicMock(), "unique-id")
    assert translations["entity"]["select"][select.translation_key] == {
        "name": "Dashboard"
    }
