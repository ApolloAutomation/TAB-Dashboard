"""Tests for the component library."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from homeassistant.core import HomeAssistant

from custom_components.apollo_tab.library import (
    PICKER_GROUPS,
    Library,
    picker_entry_problem,
    read_picker,
)
from custom_components.apollo_tab.maker.const import MAX_FILE_BYTES
from tests.harness.build_fixtures import build

SIMPLE_COMPONENT = """\
id: me/simple
version: 1.0.0
name: Simple
size: 1x1
params:
  entity: {domain: light}
inputs:
  state: "{{ states(entity) }}"
outputs:
  toggle:
    action: light.toggle
    data: {entity_id: "{{ entity }}"}
    feedback: optimistic
layout:
  - type: switch
    value: state
    on_tap: toggle
"""

SENSITIVE_COMPONENT = (
    SIMPLE_COMPONENT.replace("domain: light", "domain: lock")
    .replace("action: light.toggle", "action: lock.unlock")
    .replace("feedback: optimistic", "feedback: confirm")
)

INVALID_COMPONENT = SIMPLE_COMPONENT.replace("id: me/simple", "id: me/thing").replace(
    "feedback: optimistic", "foo: bar\n    feedback: optimistic"
)


async def test_builtins_load(hass: HomeAssistant) -> None:
    """All built-in Components load without errors."""
    library = Library(hass)
    await library.async_load()
    assert len(library.components) == 25
    assert library.errors == []
    assert library.themes
    assert "apollo/light-tile" in library.components
    assert all(
        component["source"] == "builtin" for component in library.components.values()
    )


async def test_user_component_loads(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """A valid user Component loads and is listed in the library dict."""
    user_components("simple.yaml", SIMPLE_COMPONENT)
    library = Library(hass)
    await library.async_load()
    assert "me/simple" in library.components
    component = library.components["me/simple"]
    assert component["source"] == "user"
    assert component["file"] == "simple.yaml"
    assert len(library.components) == 26
    assert library.errors == []
    listing = library.as_dict()
    assert listing["components_path"] == library.user_dir
    entry = next(item for item in listing["components"] if item["id"] == "me/simple")
    assert entry["tag"] == "apollo-tab-el-me-simple"
    assert entry["grid"] == {"columns": 6, "rows": 3}
    assert entry["sensitive"] is False
    assert entry["approved"] is True


async def test_invalid_file_reported_others_still_load(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """A broken document is reported while valid documents still load."""
    user_components("a-invalid.yaml", INVALID_COMPONENT)
    user_components("b-simple.yaml", SIMPLE_COMPONENT)
    library = Library(hass)
    await library.async_load()
    assert "me/simple" in library.components
    assert "me/thing" not in library.components
    assert len(library.errors) == 1
    error = library.errors[0]
    assert error["file"] == "a-invalid.yaml"
    assert error["index"] == 0
    assert error["id"] == "me/thing"
    assert error["code"] == "unknown_key"
    assert "unknown key" in error["message"]


async def test_yaml_error_reported(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """An unparseable file yields one yaml_error entry."""
    user_components("broken.yaml", "foo: [bar\n")
    library = Library(hass)
    await library.async_load()
    assert len(library.errors) == 1
    assert library.errors[0]["code"] == "yaml_error"
    assert library.errors[0]["file"] == "broken.yaml"
    assert len(library.components) == 25


async def test_python_tag_rejected(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """Python object tags are rejected as a yaml_error."""
    user_components("evil.yaml", 'x: !!python/object/apply:os.system ["echo hi"]\n')
    library = Library(hass)
    await library.async_load()
    assert len(library.errors) == 1
    assert library.errors[0]["code"] == "yaml_error"


async def test_include_tag_rejected(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """The YAML include tag is rejected as a yaml_error."""
    user_components("include.yaml", "config: !include other.yaml\n")
    library = Library(hass)
    await library.async_load()
    assert len(library.errors) == 1
    assert library.errors[0]["code"] == "yaml_error"


async def test_alias_rejected(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """Anchors and aliases are rejected as a yaml_error."""
    user_components("alias.yaml", "a: &x 1\nb: *x\n")
    library = Library(hass)
    await library.async_load()
    assert len(library.errors) == 1
    assert library.errors[0]["code"] == "yaml_error"


async def test_file_too_large_reported(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """A file over the size limit is not read and is reported."""
    user_components("big.yaml", "# " + "x" * MAX_FILE_BYTES)
    library = Library(hass)
    await library.async_load()
    assert len(library.errors) == 1
    assert library.errors[0]["code"] == "file_too_large"
    assert library.errors[0]["file"] == "big.yaml"
    assert len(library.components) == 25


async def test_reserved_namespace_rejected(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """User Components may not use the apollo/ namespace."""
    user_components(
        "reserved.yaml",
        SIMPLE_COMPONENT.replace("id: me/simple", "id: apollo/simple"),
    )
    library = Library(hass)
    await library.async_load()
    assert "apollo/simple" not in library.components
    assert len(library.errors) == 1
    assert library.errors[0]["code"] == "reserved_namespace"
    assert library.errors[0]["id"] == "apollo/simple"


async def test_duplicate_id_rejected(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """The second file using an id is rejected."""
    user_components("a.yaml", SIMPLE_COMPONENT)
    user_components("b.yaml", SIMPLE_COMPONENT)
    library = Library(hass)
    await library.async_load()
    assert "me/simple" in library.components
    assert len(library.errors) == 1
    assert library.errors[0]["code"] == "duplicate_id"
    assert library.errors[0]["file"] == "b.yaml"
    assert library.errors[0]["id"] == "me/simple"


async def test_bad_template_rejected(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """A Component with a broken template is rejected after parsing."""
    user_components(
        "bad.yaml",
        SIMPLE_COMPONENT.replace("{{ states(entity) }}", "{{ states(entity "),
    )
    library = Library(hass)
    await library.async_load()
    assert "me/simple" not in library.components
    assert len(library.errors) == 1
    assert library.errors[0]["code"] == "bad_template"
    assert library.errors[0]["id"] == "me/simple"


async def test_symlink_skipped(
    hass: HomeAssistant,
    tmp_path: Path,
    user_components: Callable[[str, str], Path],
) -> None:
    """Symlinks in the user folder are skipped silently."""
    target = tmp_path / "elsewhere.yaml"
    target.write_text(SIMPLE_COMPONENT, encoding="utf-8")
    folder = tmp_path / "apollo_tab" / "components"
    folder.mkdir(parents=True)
    (folder / "linked.yaml").symlink_to(target)
    library = Library(hass)
    await library.async_load()
    assert "me/simple" not in library.components
    assert library.errors == []


async def test_subfolder_ignored(
    hass: HomeAssistant,
    tmp_path: Path,
    user_components: Callable[[str, str], Path],
) -> None:
    """Files inside subfolders are ignored."""
    folder = tmp_path / "apollo_tab" / "components" / "nested.yaml"
    folder.mkdir(parents=True)
    (folder / "simple.yaml").write_text(SIMPLE_COMPONENT, encoding="utf-8")
    library = Library(hass)
    await library.async_load()
    assert "me/simple" not in library.components
    assert library.errors == []


async def test_reload_picks_up_new_file(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """Reloading picks up files written after the first load."""
    library = Library(hass)
    await library.async_load()
    assert "me/simple" not in library.components
    user_components("simple.yaml", SIMPLE_COMPONENT)
    await library.async_load()
    assert "me/simple" in library.components


async def test_sensitive_user_component_needs_approval(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """A sensitive user Component is usable only after explicit approval."""
    user_components("lock.yaml", SENSITIVE_COMPONENT)
    library = Library(hass)
    await library.async_load()
    assert "me/simple" in library.components
    assert not library.is_approved("me/simple")
    assert library.approved_ids() == set()
    entry = next(
        item for item in library.as_dict()["components"] if item["id"] == "me/simple"
    )
    assert entry["sensitive"] is True
    assert entry["approved"] is False
    calls = 0

    def _listener() -> None:
        """Count listener calls."""
        nonlocal calls
        calls += 1

    library.async_listen(_listener)
    await library.async_set_approved("me/simple", True)
    assert calls == 1
    assert library.is_approved("me/simple")
    assert library.approved_ids() == {"me/simple"}
    await library.async_set_approved("me/simple", False)
    assert calls == 2
    assert not library.is_approved("me/simple")
    with pytest.raises(KeyError):
        await library.async_set_approved("me/unknown", True)


async def test_approval_lapses_when_file_changes(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """Changing the file invalidates the stored approval."""
    user_components("lock.yaml", SENSITIVE_COMPONENT)
    library = Library(hass)
    await library.async_load()
    await library.async_set_approved("me/simple", True)
    assert library.is_approved("me/simple")
    user_components(
        "lock.yaml", SENSITIVE_COMPONENT.replace("name: Simple", "name: Lock")
    )
    await library.async_load()
    assert not library.is_approved("me/simple")
    assert library.approved_ids() == set()


async def test_user_folder_created(
    hass: HomeAssistant,
    tmp_path: Path,
    user_components: Callable[[str, str], Path],
) -> None:
    """The user folder is created when the library loads."""
    folder = tmp_path / "apollo_tab" / "components"
    assert not folder.exists()
    library = Library(hass)
    await library.async_load()
    assert folder.is_dir()


BUILTIN_DIR = (
    Path(__file__).parent.parent
    / "custom_components"
    / "apollo_tab"
    / "library"
    / "components"
)

# Words from Home Assistant's insides that the people choosing a card do not
# use, and names written with underscores.
JARGON = re.compile(
    r"\b(cover|covers|entity|entities|domain|domains|hvac|transport|component|"
    r"components)\b|\b[a-z0-9]+_[a-z0-9_]+\b",
    re.IGNORECASE,
)


def test_builtin_cards_are_described_in_plain_words() -> None:
    """The picker shows each built-in card's name and description as is."""
    offenders = []
    for path in sorted(BUILTIN_DIR.glob("*.yaml")):
        card = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key in ("name", "description"):
            text = card.get(key, "")
            if JARGON.search(text):
                offenders.append(f"{path.name} {key}: {text}")
    assert offenders == []


PICKER_FILE = BUILTIN_DIR.parent / "picker.json"


def test_picker_json_names_known_groups_and_plain_words(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """picker.json names groups that exist and plain short words."""
    data = json.loads(PICKER_FILE.read_text(encoding="utf-8"))
    builtin_ids = {
        yaml.safe_load(path.read_text(encoding="utf-8"))["id"]
        for path in BUILTIN_DIR.glob("*.yaml")
    }
    # Every bundled card has an entry, and every entry passes the checks.
    assert set(data) == builtin_ids
    assert set(PICKER_GROUPS) == {
        "lights",
        "climate",
        "covers",
        "security",
        "media",
        "sensors",
        "home",
        "more",
    }
    for card_id, entry in data.items():
        assert picker_entry_problem(entry) is None, card_id
        assert entry["keywords"], card_id
        for word in entry["keywords"]:
            assert not JARGON.search(word), f"{card_id}: {word}"
    assert read_picker() == data
    # A schema 2 file names its own group, which wins; picker.json says the
    # same, so the two never disagree.
    for path in BUILTIN_DIR.glob("*.yaml"):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if doc.get("schema") == 2:
            assert data[doc["id"]]["group"] == doc["group"], doc["id"]

    # A bad entry is left out and logged; the good ones still load.
    bad = {
        "me/good": {"group": "lights", "keywords": ["lamp"]},
        "me/group": {"group": "rooms", "keywords": []},
        "me/word": {"group": "media", "keywords": ["Media_Player"]},
        "me/long": {"group": "media", "keywords": ["a" * 25]},
        "me/many": {"group": "media", "keywords": [f"w{n}" for n in range(9)]},
        "me/twice": {"group": "media", "keywords": ["tv", "tv"]},
        "me/extra": {"group": "media", "keywords": [], "legacy": True},
        "me/list": ["lights"],
    }
    path = tmp_path / "picker.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    assert read_picker(path) == {"me/good": {"group": "lights", "keywords": ["lamp"]}}
    assert caplog.text.count("Built-in picker.json") == len(bad) - 1
    path.write_text("[]", encoding="utf-8")
    assert read_picker(path) == {}


async def test_as_dict_gives_every_card_its_group_and_words(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """as_dict gives every card its group and its search words."""
    user_components("simple.yaml", SIMPLE_COMPONENT)
    library = Library(hass)
    await library.async_load()
    data = json.loads(PICKER_FILE.read_text(encoding="utf-8"))
    entries = {item["id"]: item for item in library.as_dict()["components"]}
    # The 25 bundled cards (16 of schema 1, 9 of schema 2) and the person's.
    assert len(entries) == 26
    for card_id, entry in data.items():
        assert entries[card_id]["group"] == entry["group"], card_id
        assert entries[card_id]["keywords"] == entry["keywords"], card_id
    assert entries["apollo/blinds"]["group"] == "covers"
    assert entries["community/room-summary"]["group"] == "home"
    assert "tv" in entries["apollo/media-player"]["keywords"]
    assert entries["apollo/light"]["group"] == "lights"
    assert "lamp" in entries["apollo/light"]["keywords"]
    # A card with no entry gets no group, so the panel guesses one. The
    # form data's "more" is only a schema 2 file's own default.
    assert entries["me/simple"]["group"] == ""
    assert entries["me/simple"]["keywords"] == []

    # The card's own group and words win over picker.json, and an entry for
    # a card that is not there is never used.
    library.picker = {
        "me/simple": {"group": "lights", "keywords": ["lamp"]},
        "me/missing": {"group": "media", "keywords": ["tv"]},
    }
    library.components["me/simple"]["group"] = "home"
    library.components["me/simple"]["keywords"] = ["porch"]
    library.picker["apollo/light"] = {"group": "media", "keywords": ["glow"]}
    listing = library.as_dict()["components"]
    simple = next(item for item in listing if item["id"] == "me/simple")
    assert simple["group"] == "home"
    assert simple["keywords"] == ["porch"]
    assert "me/missing" not in {item["id"] for item in listing}
    # A schema 2 file always has its group; its words come from picker.json.
    light = next(item for item in listing if item["id"] == "apollo/light")
    assert light["group"] == "lights"
    assert light["keywords"] == ["glow"]

    # The harness fixtures give the panel the same answer: the schema 1
    # cards in its library, the schema 2 cards' form data in cards_v2.
    built = build()
    fixture = {item["id"]: item for item in built["library"]["components"]}
    fixture.update({item["id"]: item["form"] for item in built["cards_v2"]})
    assert set(fixture) == set(data)
    for card_id, entry in data.items():
        assert fixture[card_id]["group"] == entry["group"], card_id
        assert fixture[card_id]["keywords"] == entry["keywords"], card_id


def test_three_cards_say_what_the_tablet_shows() -> None:
    """The three cards with pictures say that the tablet shows an icon."""
    expected = {
        "apollo-camera-snapshot.yaml": (
            "A camera's name. The tablet cannot show the camera's picture yet, "
            "so it shows an icon in its place."
        ),
        "apollo-media-player.yaml": (
            "What is playing, with play, pause and skip buttons, and the volume. "
            "The tablet shows an icon, not the picture of what is playing."
        ),
        "community-presence-chips.yaml": (
            "Who is home. The tablet shows an icon for each person, not their photo."
        ),
    }
    for name, description in expected.items():
        card = yaml.safe_load((BUILTIN_DIR / name).read_text(encoding="utf-8"))
        assert card["description"] == description, name
        assert len(description) <= 160, name


# A Home Assistant id such as scene.movie, a raw state word written with an
# underscore such as armed_home, and the states a device has before it reports.
ENTITY_ID = re.compile(r"\b[a-z_]+\.[a-z0-9_]+\b")
RAW_STATE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b|\b(unknown|unavailable)\b")

# A line of text of n letters is about 0.6 n of its type size wide. The
# picker's tile shows the name in one line of 14 px type, in a tile at least
# 176 px wide with 12 px padding on each side. A card's header shows it in
# 16 px type, beside a 32 px icon.
LETTER_WIDTH = 0.6
PICKER_NAME_ROOM = 176 - 2 * 12

# Older cards still on offer whose examples are not friendly yet. They come
# from the cards' templates, so a friendlier example alone would promise what
# the card on the wall does not do. Their new cards fix them (cards spec D.1
# and D.2), and a card leaves this list when the picker stops offering it.
# The list may only get shorter.
NOT_FRIENDLY_YET = {
    "apollo/alarm-panel": "shows the raw state word armed_home",
    "apollo/scene-row": "shows each scene's id, such as scene.movie",
    "community/presence-chips": (
        "shows each person's id and raw state, such as person.alex: unknown"
    ),
}


def _texts(value: object) -> list[str]:
    """Return the strings inside an example value."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _texts(item)]
    return []


def test_cards_the_picker_offers_have_friendly_examples() -> None:
    """Cards the picker offers have friendly examples and names that fit."""
    fixtures = build()
    components = {item["id"]: item for item in fixtures["library"]["components"]}
    problems: dict[str, list[str]] = {}
    for card in fixtures["cards"]:
        component = components[card["id"]]
        if component.get("legacy"):
            continue
        found = []
        raw = yaml.safe_load(
            (BUILTIN_DIR / f"{card['id'].replace('/', '-')}.yaml").read_text(
                encoding="utf-8"
            )
        )
        # What the example picture shows: the example inputs and every value
        # the card's templates give with the example params.
        shown = _texts(list((raw.get("preview") or {}).get("inputs", {}).values()))
        shown += _texts(list(card["values"].values()))
        for text in shown:
            if ENTITY_ID.search(text):
                found.append(f"id in {text!r}")
            elif RAW_STATE.search(text):
                found.append(f"raw state in {text!r}")
        name = component["name"]
        if len(name) * LETTER_WIDTH * 14 > PICKER_NAME_ROOM:
            found.append(f"name {name!r} is too long for a picker tile")
        header = card["init"].get("header")
        if header:
            room = header["r"][2] - (32 if header.get("icon") else 0)
            if len(name) * LETTER_WIDTH * 16 > room:
                found.append(f"name {name!r} is cut in the card's header")
        if found:
            problems[card["id"]] = found
    assert len(fixtures["cards"]) == 16
    assert set(problems) == set(NOT_FRIENDLY_YET), problems
    assert len(NOT_FRIENDLY_YET) <= 3
