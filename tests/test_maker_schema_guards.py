"""Tests for the maker schema targeting-key and layout-type guards."""

import pytest
import yaml

from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.schema import validate_component

BASE = """
id: me/toggle
version: 1.0.0
name: Toggle
size: 1x1
params:
  entity: {domain: input_boolean}
outputs:
  switch_on:
    action: input_boolean.turn_on
    data:
      entity_id: "{{ entity }}"
    feedback: pulse
layout:
  - type: button
    text: "On"
    on_tap: switch_on
"""

FORECAST = """
id: me/forecast
version: 1.0.0
name: Forecast
size: 1x1
params:
  entity: {domain: weather}
inputs:
  forecast:
    action: weather.get_forecasts
    data:
      entity_id: "{{ entity }}"
      type: daily
      area_id: kitchen
    result: "{{ response[entity].forecast | map(attribute='temperature') | list }}"
layout:
  - type: chart
    value: forecast
"""

LIGHT = """
id: me/dimmer
version: 1.0.0
name: Dimmer
size: 1x1
params:
  entity: {domain: light}
outputs:
  turn_on:
    action: light.turn_on
    data:
      entity_id: "{{ entity }}"
      brightness: "{{ value }}"
    feedback: pulse
layout:
  - type: button
    text: "On"
    on_tap: turn_on
"""

TARGETING_KEYS = ("area_id", "device_id", "floor_id", "label_id", "target")


def _load(text):
    """Parse YAML text and validate it as a component."""
    return validate_component(yaml.safe_load(text))


def test_base_component_validates():
    """Validate the base component unchanged."""
    component = _load(BASE)
    assert component["id"] == "me/toggle"


@pytest.mark.parametrize("key", TARGETING_KEYS)
@pytest.mark.parametrize("value", ["x", "{{ entity }}"])
def test_output_data_targeting_key_rejected(key, value):
    """Reject output data keys that widen a call beyond the picked entity."""
    doc = yaml.safe_load(BASE)
    doc["outputs"]["switch_on"]["data"][key] = value
    with pytest.raises(MakerError) as excinfo:
        validate_component(doc)
    assert excinfo.value.code == "bad_value"
    assert excinfo.value.path == f"outputs.switch_on.data.{key}"


def test_read_action_input_targeting_key_rejected():
    """Reject a targeting key on a read-action input."""
    with pytest.raises(MakerError) as excinfo:
        _load(FORECAST)
    assert excinfo.value.code == "bad_value"
    assert excinfo.value.path == "inputs.forecast.data.area_id"


def test_read_action_input_without_targeting_key_validates():
    """Validate the read-action input once the targeting key is removed."""
    doc = yaml.safe_load(FORECAST)
    del doc["inputs"]["forecast"]["data"]["area_id"]
    component = validate_component(doc)
    assert component["inputs"]["forecast"]["action"] == "weather.get_forecasts"


@pytest.mark.parametrize(
    "type_line",
    ["- type: [button]", "- type: {a: 1}", "- type: 3", "- type: null"],
)
def test_layout_type_must_be_a_string(type_line):
    """Reject non-string layout types with bad_value instead of TypeError."""
    text = BASE.replace("- type: button", type_line)
    with pytest.raises(MakerError) as excinfo:
        _load(text)
    assert excinfo.value.code == "bad_value"
    assert excinfo.value.path == "layout.0.type"


def test_ordinary_data_key_still_accepted():
    """Accept an ordinary data key such as brightness."""
    component = _load(LIGHT)
    assert component["outputs"]["turn_on"]["data"]["brightness"] == "{{ value }}"
