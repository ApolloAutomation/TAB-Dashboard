"""Tests for the component library."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from homeassistant.core import HomeAssistant

from custom_components.apollo_tab.library import Library
from custom_components.apollo_tab.maker.const import MAX_FILE_BYTES

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
    assert len(library.components) == 16
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
    assert len(library.components) == 17
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
    assert len(library.components) == 16


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
    assert len(library.components) == 16


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
