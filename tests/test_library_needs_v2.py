"""`needs_v2` of the library covers an empty version 1 form (decision 5, I13).

A variant needs version 2 when a tablet with engine 0.1.0 would get the
note for it (C.6, C.7): its `v1` says `note`, or its own version 1 form
keeps nothing and no old card stands in for it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from homeassistant.core import HomeAssistant

from custom_components.apollo_tab import library as library_module
from custom_components.apollo_tab.library import Library
from custom_components.apollo_tab.maker.compile2_v1 import keeps_nothing
from custom_components.apollo_tab.maker.const import UPDATE_NOTE
from custom_components.apollo_tab.maker.convert import convert_dashboard
from custom_components.apollo_tab.maker.schema import validate_component

HERE = Path(__file__).parent
ICONS = json.loads((HERE / "contract" / "icons.json").read_text(encoding="utf-8"))
LEVEL1 = frozenset(
    name for name, (_code, level) in ICONS["icons"].items() if level <= 1
)

LOCK_TILE = """\
schema: 1
id: me/lock-tile
version: 1.0.0
name: Lock tile
size: 1x1
params:
  entity: {domain: lock}
inputs:
  state: "{{ states(entity) }}"
outputs:
  lock:
    action: lock.lock
    data: {entity_id: "{{ entity }}"}
    feedback: confirm
layout:
  - {type: label, text: "{{ state }}"}
"""

# The switch with `visible` is left out of a version 1 form (C.6), and the
# variants have no header, so a variant that holds only it keeps nothing.
FORMS = """\
schema: 2
id: me/forms
version: 1.0.0
name: Forms
params:
  entity: {domain: light}
inputs:
  is_on: "{{ is_state(entity, 'on') }}"
outputs:
  toggle:
    action: light.toggle
    data: {entity_id: "{{ entity }}"}
    feedback: optimistic
variants:
  hidden:
    name: Hidden
    grid: [6, 3]
    header: none
    layout:
      - {type: switch, value: is_on, on_tap: toggle, visible: is_on}
  plain:
    name: Plain
    grid: [6, 3]
    header: none
    layout:
      - {type: switch, value: is_on, on_tap: toggle}
  old_fits:
    name: Old fits
    grid: [6, 3]
    header: none
    v1: apollo/light-tile
    layout:
      - {type: switch, value: is_on, on_tap: toggle, visible: is_on}
  old_too_big:
    name: Old too big
    grid: [6, 3]
    header: none
    v1: apollo/light-slider
    layout:
      - {type: switch, value: is_on, on_tap: toggle, visible: is_on}
  old_not_allowed:
    name: Old not allowed
    grid: [6, 3]
    header: none
    v1: me/lock-tile
    layout:
      - {type: switch, value: is_on, on_tap: toggle, visible: is_on}
preview:
  params: {entity: light.kitchen}
  inputs: {is_on: true}
"""


def _entry(library: Library, component_id: str) -> dict:
    """Return one card of the library dict."""
    listing = library.as_dict()["components"]
    return next(item for item in listing if item["id"] == component_id)


def _flags(entry: dict) -> dict[str, bool]:
    """Return needs_v2 per variant."""
    return {variant["id"]: variant["needs_v2"] for variant in entry["variants"]}


async def test_an_empty_version_1_form_needs_version_2(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """Rule 2 keeps nothing: the note, unless an allowed old card fits."""
    user_components("lock.yaml", LOCK_TILE)
    user_components("forms.yaml", FORMS)
    library = Library(hass)
    await library.async_load()
    assert library.errors == []
    assert _flags(_entry(library, "me/forms")) == {
        "hidden": True,
        "plain": False,
        "old_fits": False,
        "old_too_big": True,
        "old_not_allowed": True,
    }
    assert _entry(library, "me/forms")["needs_v2"] is False

    # A file whose v1 names a sensitive card is sensitive itself (C.6 rule
    # 1), so the old card stands in only when both are allowed.
    assert _entry(library, "me/forms")["sensitive"] is True
    await library.async_set_approved("me/lock-tile", True)
    assert _flags(_entry(library, "me/forms"))["old_not_allowed"] is True
    await library.async_set_approved("me/forms", True)
    assert _flags(_entry(library, "me/forms"))["old_not_allowed"] is False


async def test_a_card_whose_variants_all_keep_nothing_needs_version_2(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """The card's own needs_v2 is true when every variant the picker shows is."""
    only = FORMS.split("  plain:")[0] + FORMS[FORMS.index("preview:") :]
    user_components("forms.yaml", only)
    library = Library(hass)
    await library.async_load()
    assert library.errors == []
    entry = _entry(library, "me/forms")
    assert _flags(entry) == {"hidden": True}
    assert entry["needs_v2"] is True


# An old 2x2 card is 12 x 6: as wide as a 12 x 3 variant but too tall.
TOO_TALL = """\
schema: 2
id: me/too-tall
version: 1.0.0
name: Too tall
params:
  entity: {domain: climate}
inputs:
  is_on: "{{ is_state(entity, 'heat') }}"
outputs:
  toggle:
    action: climate.toggle
    data: {entity_id: "{{ entity }}"}
    feedback: optimistic
variants:
  wide:
    name: Wide
    grid: [12, 3]
    header: none
    v1: apollo/thermostat
    layout:
      - {type: switch, value: is_on, on_tap: toggle, visible: is_on}
  big:
    name: Big
    grid: [12, 6]
    header: none
    v1: apollo/thermostat
    layout:
      - {type: switch, value: is_on, on_tap: toggle, visible: is_on}
preview:
  params: {entity: climate.hall}
  inputs: {is_on: true}
"""

# A button with only an icon: a version 1 form keeps it only when the icon
# is in level 1 (C.6, "Icons").
ICON_BUTTONS = """\
schema: 2
id: me/icon-buttons
version: 1.0.0
name: Icon buttons
params:
  entity: {domain: light}
outputs:
  toggle:
    action: light.toggle
    data: {entity_id: "{{ entity }}"}
    feedback: optimistic
variants:
  level1:
    name: Level 1
    grid: [6, 3]
    header: none
    layout:
      - {type: button, icon: "mdi:account", on_tap: toggle}
  level2:
    name: Level 2
    grid: [6, 3]
    header: none
    layout:
      - {type: button, icon: "mdi:air-conditioner", on_tap: toggle}
preview:
  params: {entity: light.kitchen}
"""


async def test_an_old_card_too_tall_for_the_variant_does_not_stand_in(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """The height counts as much as the width (C.6 rule 1)."""
    user_components("tall.yaml", TOO_TALL)
    library = Library(hass)
    await library.async_load()
    assert library.errors == []
    assert _flags(_entry(library, "me/too-tall")) == {"wide": True, "big": False}


async def test_only_level_1_icons_count_as_kept(
    hass: HomeAssistant, user_components: Callable[[str, str], Path]
) -> None:
    """The library reads the levels from the contract: level 2 is not level 1."""
    assert ICONS["icons"]["mdi:account"][1] == 1
    assert ICONS["icons"]["mdi:air-conditioner"][1] == 2
    user_components("buttons.yaml", ICON_BUTTONS)
    library = Library(hass)
    await library.async_load()
    assert library.errors == []
    assert _flags(_entry(library, "me/icon-buttons")) == {
        "level1": False,
        "level2": True,
    }


def test_a_card_without_example_values_tells_nothing() -> None:
    """Without preview values the form cannot be made, so it is not the note."""
    text = FORMS[: FORMS.index("preview:")]
    component = validate_component(yaml.safe_load(text))
    assert keeps_nothing(component, "hidden", LEVEL1) is False
    with_preview = validate_component(yaml.safe_load(FORMS))
    assert keeps_nothing(with_preview, "hidden", LEVEL1) is True
    assert keeps_nothing(with_preview, "plain", LEVEL1) is False


@pytest.fixture
async def builtins(hass: HomeAssistant) -> Library:
    """Return the library of the built-in files."""
    library = Library(hass)
    await library.async_load()
    assert library.errors == []
    return library


async def test_the_built_in_variants_that_get_the_note(builtins: Library) -> None:
    """A card one grid row high has room for the title header only (C.6, D.2)."""
    flagged = {
        (entry["id"], variant["id"])
        for entry in builtins.as_dict()["components"]
        for variant in entry["variants"]
        if variant["needs_v2"]
    }
    assert flagged == {("apollo/button", "chip"), ("apollo/reading", "chip")}
    for component_id in ("apollo/button", "apollo/reading"):
        assert _entry(builtins, component_id)["needs_v2"] is False


async def test_needs_v2_agrees_with_the_converter(builtins: Library) -> None:
    """For every built-in variant: needs_v2 exactly when the converter writes the note.

    Each card as the picker shows it (its example values) at its variant's
    grid, converted for a version 1 tablet.
    """
    assert builtins.components["apollo/page-link"]["preview"]["params"]
    themes = builtins.themes
    checked = 0
    for entry in builtins.as_dict()["components"]:
        if entry["schema"] != 2:
            continue
        for variant in entry["variants"]:
            if not variant["picker"]:
                continue
            columns, rows = variant["grid"]
            component = builtins.components[entry["id"]]
            card = {
                "type": "custom:apollo-tab-card",
                "component": entry["id"],
                # The example page or number; the devices stay examples.
                "params": {
                    name: value
                    for name, value in component["preview"]["params"].items()
                    if component["params"][name]["kind"] != "entity"
                },
                "variant": variant["id"],
                "grid_options": {"columns": columns, "rows": rows},
            }
            config = {
                "apollo_tab": {"version": 1, "theme": "midnight"},
                "views": [
                    {
                        "type": "sections",
                        "path": "home",
                        "sections": [{"type": "grid", "cards": [card]}],
                    }
                ],
            }
            layout = convert_dashboard(
                config,
                components=builtins.components,
                themes=themes,
                approved=builtins.approved_ids(),
                icons=ICONS,
            )["layout"]
            [built] = [
                item
                for page in layout["pages"]
                for item in page["w"]
                if item["t"] == "card"
            ]
            note = [w.get("text") for w in built["w"]] == [UPDATE_NOTE]
            assert variant["needs_v2"] is note, (entry["id"], variant["id"])
            checked += 1
    assert checked >= 20


async def test_a_failing_check_does_not_stop_the_library(
    hass: HomeAssistant,
    user_components: Callable[[str, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The load-time check runs outside the guard for each file; it has its own."""
    real = library_module.keeps_nothing

    def broken(component: dict, variant: str, level1: frozenset[str]) -> bool:
        if component["id"] == "me/forms":
            raise ValueError("odd file")
        return real(component, variant, level1)

    monkeypatch.setattr(library_module, "keeps_nothing", broken)
    user_components("lock.yaml", LOCK_TILE)
    user_components("forms.yaml", FORMS)
    library = Library(hass)
    await library.async_load()
    assert library.errors == []
    assert "apollo/light" in library.components
    # Counted as not empty, so only the old card rules decide.
    assert _flags(_entry(library, "me/forms"))["hidden"] is False
    assert _flags(_entry(library, "apollo/button"))["chip"] is True
