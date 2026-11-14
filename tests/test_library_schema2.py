"""Tests for schema 2 card files in the library (cards spec C.2.1 and C.7)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from homeassistant.core import HomeAssistant

from custom_components.apollo_tab import library as library_module
from custom_components.apollo_tab.library import Library
from custom_components.apollo_tab.maker.convert import convert_dashboard

HERE = Path(__file__).parent
LIGHT = (HERE / "cards2" / "light.yaml").read_text(encoding="utf-8")
BUILTIN = library_module._BUILTIN_DIR

USER_CARD = """\
schema: 2
id: me/plug
version: 1.0.0
name: Plug
params:
  entity: {domain: [switch, input_boolean], label: Plug}
inputs:
  is_on: "{{ is_state(entity, 'on') }}"
outputs:
  toggle:
    action: {switch: switch.toggle, input_boolean: input_boolean.toggle}
    data: {entity_id: "{{ entity }}"}
    feedback: optimistic
on: is_on
tap:
  choices:
    toggle: {label: Turns it on or off, output: toggle}
    none: {label: Does nothing}
variants:
  chip:
    name: Chip
    grid: [12, 1]
    header: chip
    v1: note
    layout:
      - {type: switch, value: is_on, on_tap: toggle}
  tile:
    name: Tile
    grid: [6, 3]
    header: tile_v
    trailing: switch
    v1: apollo/light-tile
    layout:
      - {type: label, text: "{{ states(entity) }}", visible: is_on}
"""


@pytest.fixture
def builtin_light(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Serve the built-in files plus the colour light of D.1 as built-ins."""
    folder = tmp_path / "builtin"
    shutil.copytree(BUILTIN, folder)
    (folder / "components" / "apollo-light.yaml").write_text(LIGHT, encoding="utf-8")
    monkeypatch.setattr(library_module, "_BUILTIN_DIR", folder)
    return folder


def _entry(library: Library, component_id: str) -> dict:
    """Return one card of the library dict."""
    listing = library.as_dict()["components"]
    return next(item for item in listing if item["id"] == component_id)


async def test_a_user_card_of_schema_2_loads(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """A schema 2 file from the person's folder loads with its form data."""
    user_components("plug.yaml", USER_CARD)
    library = Library(hass)
    await library.async_load()
    assert library.errors == []
    entry = _entry(library, "me/plug")
    assert entry["schema"] == 2
    assert entry["legacy"] is False
    assert entry["group"] == "more"
    assert entry["sensitive"] is False
    assert entry["approved"] is True
    # The picker places the first variant it shows.
    assert entry["size"] == [2, 1]
    assert entry["grid"] == {"columns": 12, "rows": 1}
    assert entry["variants"] == [
        {
            "id": "chip",
            "name": "Chip",
            "grid": [12, 1],
            "picker": True,
            "needs_v2": True,
        },
        {
            "id": "tile",
            "name": "Tile",
            "grid": [6, 3],
            "picker": True,
            "needs_v2": False,
        },
    ]
    assert entry["needs_v2"] is False
    # A param with several kinds has no `domain`; the panel reads `domains`.
    assert entry["params"]["entity"] == {
        "kind": "entity",
        "domains": ["switch", "input_boolean"],
        "multiple": False,
        "optional": False,
        "device_class": None,
        "label": "Plug",
        "help": "",
    }
    assert entry["tap"] == {
        "default": "toggle",
        "choices": [
            {"value": "toggle", "label": "Turns it on or off", "needs": ""},
            {"value": "page", "label": "Goes to a page", "needs": ""},
            {"value": "none", "label": "Does nothing", "needs": ""},
        ],
    }
    assert entry["standard"] == {
        "title": True,
        "icon": True,
        "hold": False,
        "lit": "fill",
        "tint": False,
    }
    assert entry["has_detail"] is False
    json.dumps(entry)


async def test_replaces_in_a_user_file_is_refused(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """Only built-in files may carry replaces."""
    user_components(
        "plug.yaml",
        USER_CARD.replace(
            "name: Plug\n", "name: Plug\nreplaces: [apollo/light-tile]\n"
        ),
    )
    library = Library(hass)
    await library.async_load()
    assert "me/plug" not in library.components
    assert [error["code"] for error in library.errors] == ["replaces_not_allowed"]
    assert library.replaced_ids() == set()
    assert _entry(library, "apollo/light-tile")["legacy"] is False


async def test_a_v1_that_names_no_loaded_schema_1_card_is_refused(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """v1 must name a loaded schema 1 card, or the note."""
    user_components("plug.yaml", USER_CARD.replace("apollo/light-tile", "me/gone"))
    library = Library(hass)
    await library.async_load()
    assert "me/plug" not in library.components
    assert [error["code"] for error in library.errors] == ["unknown_v1"]
    assert library.errors[0]["id"] == "me/plug"
    assert "me/gone" in library.errors[0]["message"]


async def test_a_v1_may_not_name_a_schema_2_card(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """A version 1 tablet cannot draw a schema 2 card."""
    other = USER_CARD.replace("id: me/plug", "id: me/other").replace(
        "apollo/light-tile", "me/plug"
    )
    user_components("a-plug.yaml", USER_CARD)
    user_components("b-other.yaml", other)
    library = Library(hass)
    await library.async_load()
    assert "me/plug" in library.components
    assert "me/other" not in library.components
    assert [error["code"] for error in library.errors] == ["unknown_v1"]


async def test_a_user_file_with_uses_needs_approval(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """Service data that reads an input makes a person's file sensitive."""
    text = USER_CARD.replace(
        '    data: {entity_id: "{{ entity }}"}\n',
        '    uses: {is_on: bool}\n    data: {entity_id: "{{ entity }}"}\n',
        1,
    )
    user_components("plug.yaml", text)
    library = Library(hass)
    await library.async_load()
    assert library.errors == []
    assert library.components["me/plug"]["sensitive"] is True
    assert library.is_approved("me/plug") is False
    await library.async_set_approved("me/plug", True)
    assert library.is_approved("me/plug") is True


async def test_a_broken_template_in_a_new_key_is_refused(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """Home Assistant's own template check also sees the new keys."""
    user_components(
        "plug.yaml", USER_CARD.replace("visible: is_on", 'visible: "{{ is_on ( }}"')
    )
    library = Library(hass)
    await library.async_load()
    assert "me/plug" not in library.components
    assert [error["code"] for error in library.errors] == ["bad_template"]


async def test_built_in_cards_replace_the_old_ones(
    hass: HomeAssistant, builtin_light: Path
) -> None:
    """A built-in schema 2 card marks the cards it replaces as legacy."""
    library = Library(hass)
    await library.async_load()
    assert library.errors == []
    assert len(library.components) == 17
    assert library.replaced_ids() == {"apollo/light-tile", "apollo/light-slider"}
    assert _entry(library, "apollo/light-tile")["legacy"] is True
    assert _entry(library, "apollo/light-slider")["legacy"] is True
    assert _entry(library, "apollo/lock")["legacy"] is False
    assert _entry(library, "apollo/light")["legacy"] is False


async def test_replaces_counts_only_from_built_in_cards(
    hass: HomeAssistant, builtin_light: Path
) -> None:
    """A card that is not built in never hides another, however it got loaded."""
    library = Library(hass)
    await library.async_load()
    light = library.components["apollo/light"]
    library.components["apollo/light"] = {**light, "source": "user"}
    assert library.replaced_ids() == set()


async def test_the_form_data_of_the_light(
    hass: HomeAssistant, builtin_light: Path
) -> None:
    """The light's static form data has the shape of C.7."""
    library = Library(hass)
    await library.async_load()
    entry = _entry(library, "apollo/light")
    assert entry["schema"] == 2
    assert entry["group"] == "lights"
    assert entry["replaces"] == ["apollo/light-tile", "apollo/light-slider"]
    assert entry["needs_v2"] is False
    assert entry["size"] == [1, 1]
    assert entry["grid"] == {"columns": 6, "rows": 3}
    assert entry["variants"][0] == {
        "id": "tile",
        "name": "Tile",
        "grid": [6, 3],
        "picker": True,
        "needs_v2": False,
    }
    assert [v["id"] for v in entry["variants"]] == ["tile", "wide", "large", "full"]
    assert entry["variants"][3]["picker"] is False
    assert entry["has_detail"] is True
    assert entry["params"] == {
        "entity": {
            "kind": "entity",
            "domains": ["light"],
            "domain": "light",
            "multiple": False,
            "optional": False,
            "device_class": None,
            "label": "Light",
            "help": "",
        }
    }
    assert entry["options"][0] == {
        "name": "show_brightness",
        "type": "toggle",
        "section": "controls",
        "label": "Brightness",
        "help": "",
        "default": True,
        "when": [],
        "needs": "can.brightness",
        "needs_text": "This light cannot be dimmed",
    }
    colour = next(o for o in entry["options"] if o["name"] == "colour_control")
    assert colour["choices"][:2] == [
        {"value": "none", "label": "Off"},
        {"value": "bar", "label": "Colour bar"},
    ]
    assert colour["multiple"] is False
    assert colour["default"] == "bar"
    effects = next(o for o in entry["options"] if o["name"] == "effects_shown")
    assert effects["from"] == "can.effect_list"
    assert effects["multiple"] is True
    assert effects["max"] == 8
    assert effects["default_first"] == 4
    assert entry["standard"] == {
        "title": True,
        "icon": True,
        "hold": True,
        "lit": "fill",
        "tint": True,
    }
    assert entry["tap"] == {
        "default": "toggle",
        "choices": [
            {"value": "toggle", "label": "Turns it on or off", "needs": ""},
            {"value": "detail", "label": "Opens its controls", "needs": ""},
            {"value": "page", "label": "Goes to a page", "needs": ""},
            {"value": "none", "label": "Does nothing", "needs": ""},
        ],
    }
    assert entry["notes"] == []


async def test_a_schema_1_card_in_the_form_data(hass: HomeAssistant) -> None:
    """A schema 1 card gets schema 1, legacy, one variant and no options."""
    library = Library(hass)
    await library.async_load()
    entry = _entry(library, "apollo/light-slider")
    assert entry["schema"] == 1
    assert entry["legacy"] is False
    assert entry["variants"] == [
        {
            "id": "default",
            "name": entry["name"],
            "grid": [entry["grid"]["columns"], entry["grid"]["rows"]],
            "picker": True,
            "needs_v2": False,
        }
    ]
    assert entry["options"] == []
    assert entry["tap"] is None
    assert entry["notes"] == []
    assert entry["has_detail"] is False
    assert entry["params"]["entity"]["domain"] == "light"
    assert entry["params"]["entity"]["domains"] == ["light"]
    # The size and grid a schema 1 card had before.
    component = library.components["apollo/light-slider"]
    assert entry["size"] == component["size"]
    assert entry["grid"] == {
        "columns": component["size"][0] * 6,
        "rows": component["size"][1] * 3,
    }


def test_a_schema_2_card_is_left_out_of_a_layout_for_now() -> None:
    """Until its compiler exists, a schema 2 card on a dashboard is left out."""
    from custom_components.apollo_tab.maker.schema import validate_component

    component = validate_component(yaml.safe_load(LIGHT))
    themes = {
        entry["id"]: entry
        for entry in json.loads((BUILTIN / "themes.json").read_text("utf-8"))
    }
    config = {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [
            {
                "type": "sections",
                "title": "Home",
                "path": "home",
                "sections": [
                    {
                        "type": "grid",
                        "cards": [
                            {
                                "type": "custom:apollo-tab-card",
                                "component": "apollo/light",
                                "params": {"entity": "light.sofa"},
                            }
                        ],
                    }
                ],
            }
        ],
    }
    result = convert_dashboard(
        config,
        components={"apollo/light": component},
        themes=themes,
        approved=set(),
    )
    codes = [warning["code"] for warning in result["warnings"]]
    assert "invalid_card" in codes


def _schema2_files() -> list[tuple[str, dict]]:
    """Return the built-in schema 2 files, and the reference light of D.1."""
    files = [("light.yaml (D.1)", yaml.safe_load(LIGHT))]
    for path in sorted((BUILTIN / "components").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if doc.get("schema") == 2:
            files.append((path.name, doc))
    return files


def test_schema_2_words_are_plain() -> None:
    """Labels of options, params, variants and tap choices pass the plain-words test."""
    from tests.test_library import JARGON

    offenders = []
    for name, doc in _schema2_files():
        texts = [doc.get("name", ""), doc.get("description", "")]
        for section in ("params", "options"):
            for spec in (doc.get(section) or {}).values():
                texts.extend([spec.get("label", ""), spec.get("help", "")])
                texts.extend(
                    str(label) for label in (spec.get("choices") or {}).values()
                )
                texts.append(spec.get("needs_text", ""))
        texts.extend(v.get("name", "") for v in (doc.get("variants") or {}).values())
        for choice in ((doc.get("tap") or {}).get("choices") or {}).values():
            texts.append(choice.get("label", ""))
        texts.extend(note.get("text", "") for note in doc.get("notes") or [])
        offenders.extend(f"{name}: {text}" for text in texts if JARGON.search(text))
    assert offenders == []


def test_schema_2_card_icons_are_in_level_1() -> None:
    """The icon of a built-in schema 2 file is what a version 1 header falls back to."""
    icons = json.loads(
        (BUILTIN.parent / "contract" / "icons.json").read_text(encoding="utf-8")
    )["icons"]
    for name, doc in _schema2_files():
        assert icons[doc["icon"]][1] == 1, name
