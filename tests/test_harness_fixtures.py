"""Tests for the committed harness fixtures file."""

import json
from pathlib import Path

import yaml

from custom_components.apollo_tab.maker.schema import validate_component
from tests.harness.build_fixtures import COMPONENTS_DIR, render_text

FIXTURES_FILE = Path(__file__).parent / "harness" / "fixtures.json"


def test_fixtures_file_is_current():
    """The committed fixtures file matches a fresh in-memory build."""
    assert FIXTURES_FILE.read_text(encoding="utf-8") == render_text()


def test_fixture_cards_cover_all_builtins():
    """The fixture cards list covers exactly the 16 bundled Components."""
    expected = set()
    for path in sorted(COMPONENTS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for entry in raw if isinstance(raw, list) else [raw]:
            expected.add(validate_component(entry)["id"])
    assert len(expected) == 16
    data = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    assert len(data["cards"]) == 16
    assert {card["id"] for card in data["cards"]} == expected
