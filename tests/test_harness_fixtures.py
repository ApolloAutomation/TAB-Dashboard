"""Tests for the committed harness fixtures file."""

import json
from pathlib import Path

import yaml

from custom_components.apollo_tab.maker.schema import validate_component
from tests.harness.build_fixtures import (
    COMPONENTS_DIR,
    _sample_dashboard,
    render_text,
)

FIXTURES_FILE = Path(__file__).parent / "harness" / "fixtures.json"


def test_fixtures_file_is_current():
    """The committed fixtures file matches a fresh in-memory build."""
    assert FIXTURES_FILE.read_text(encoding="utf-8") == render_text()


def test_fixture_cards_cover_all_builtins():
    """The fixture cards lists cover exactly the 39 bundled Components.

    The 16 schema 1 cards are in `cards` and the panel's library; the 23
    schema 2 cards of steps A and B are in `cards_v2`, which the panel does not
    read until the editor draws them (packages I7, I8).
    """
    expected = set()
    expected2 = set()
    for path in sorted(COMPONENTS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for entry in raw if isinstance(raw, list) else [raw]:
            component = validate_component(entry)
            target = expected2 if component.get("schema") == 2 else expected
            target.add(component["id"])
    assert len(expected) == 16
    assert len(expected2) == 23
    data = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    assert len(data["cards"]) == 16
    assert {card["id"] for card in data["cards"]} == expected
    assert {c["id"] for c in data["library"]["components"]} == expected
    assert {card["id"] for card in data["cards_v2"]} == expected2


def test_schema_2_fixture_cards_carry_form_data_and_examples():
    """Each schema 2 card has its form data and an example per variant."""
    data = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    for entry in data["cards_v2"]:
        assert entry["form"]["schema"] == 2, entry["id"]
        names = [variant["id"] for variant in entry["form"]["variants"]]
        assert list(entry["variants"]) == names, entry["id"]
        for name, variant in entry["variants"].items():
            init = variant["init"]
            assert init["schema"] == 2 and init["variant"] == name
            assert init["warnings"] == [], (entry["id"], name)
            assert "slots" not in init and "actions" not in init
    light = next(entry for entry in data["cards_v2"] if entry["id"] == "apollo/light")
    assert light["form"]["has_detail"] is True
    assert light["form"]["replaces"] == ["apollo/light-tile", "apollo/light-slider"]


def test_fixture_params_keep_the_yaml_order():
    """Each card's params are listed in the order of its YAML file.

    Home Assistant sends them in that order and the forms show the fields in
    it, so the harness must not sort them.
    """
    expected = {}
    for path in sorted(COMPONENTS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for entry in raw if isinstance(raw, list) else [raw]:
            expected[entry["id"]] = list(entry.get("params") or {})
    data = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    for component in data["library"]["components"]:
        assert list(component["params"]) == expected[component["id"]], component["id"]
    room = next(
        component
        for component in data["library"]["components"]
        if component["id"] == "community/room-summary"
    )
    assert list(room["params"]) == [
        "temperature_sensor",
        "humidity_sensor",
        "lights",
        "page",
    ]


def test_fixtures_have_no_strings_and_carry_sources():
    """The fixtures leave the strings to strings.json and carry sources."""
    data = json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))
    assert "strings" not in data
    assert data["sample_config"] == _sample_dashboard()
    entry = data["layout"]
    assert set(entry) == {"url_path", "layout", "warnings", "values", "sources"}
    ids = {str(item["id"]) for page in entry["layout"]["pages"] for item in page["w"]}
    assert set(entry["sources"]) == ids
    for source in entry["sources"].values():
        assert len(source) == 3
        assert all(isinstance(index, int) for index in source[:2])
        assert source[2] is None or isinstance(source[2], int)
