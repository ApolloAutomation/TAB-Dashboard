"""Tests for maker.compile."""

from pathlib import Path

import pytest
import yaml

from custom_components.apollo_tab.maker.compile import compile_card, public_card
from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.schema import (
    validate_card_config,
    validate_component,
)

BRIGHTNESS_EXPR = "state_attr(entity, 'brightness') | int(0) * 100 // 255"
BRIGHTNESS_PRELUDE = "{% set brightness = (" + BRIGHTNESS_EXPR + ") %}"
LIBRARY = (
    Path(__file__).parent.parent
    / "custom_components"
    / "apollo_tab"
    / "library"
    / "components"
)


def make_component(**overrides: object) -> dict:
    """Build a small raw component and run it through validation."""
    raw = {
        "schema": 1,
        "id": "test/demo",
        "version": "1.0.0",
        "name": "Demo",
        "description": "Demo component.",
        "size": "1x1",
        "params": {"entity": {"domain": "light"}},
        "inputs": {},
        "outputs": {},
        "layout": [],
    }
    raw.update(overrides)
    return validate_component(raw)


def make_card(component: dict, raw: dict | None = None) -> dict:
    """Validate a card config and force a numeric column count."""
    card = validate_card_config(component, raw or {})
    if not isinstance(card["columns"], int):
        card["columns"] = 6
    return card


def toggle_output() -> dict:
    """Return a fresh raw toggle output definition."""
    return {
        "action": "light.toggle",
        "data": {"entity_id": "{{ entity }}"},
        "feedback": "optimistic",
    }


def test_light_slider_compiles() -> None:
    """Compile the built-in light slider against the documented example."""
    raw = yaml.safe_load(
        (LIBRARY / "apollo-light-slider.yaml").read_text(encoding="utf-8")
    )
    component = validate_component(raw)
    card = validate_card_config(
        component,
        {"params": {"entity": "light.kitchen"}, "columns": "full", "rows": 3},
    )
    card["columns"] = 12
    assert compile_card(component, card) == {
        "component": "apollo/light-slider",
        "name": "Light with slider",
        "demo": False,
        "w": 376,
        "h": 184,
        "entities": ["light.kitchen"],
        "header": {
            "r": [16, 16, 272, 32],
            "icon": "mdi:lightbulb-on",
            "title": {"s": 1},
        },
        "on": {"s": 2},
        "widgets": [
            {
                "i": 0,
                "t": "switch",
                "r": [296, 14, 64, 36],
                "value": {"s": 2},
                "tap": {"policy": "optimistic"},
            },
            {
                "i": 1,
                "t": "slider",
                "r": [16, 92, 344, 40],
                "value": {"s": 3},
                "min": 0,
                "max": 100,
                "step": 1,
                "change": {"policy": "optimistic"},
            },
            {
                "i": 2,
                "t": "label",
                "r": [16, 140, 344, 28],
                "text": {"s": 4},
                "size": "m",
            },
        ],
        "slots": [
            {
                "n": 1,
                "kind": "template",
                "template": (
                    "{{ state_attr(entity, 'friendly_name') or component_name }}"
                ),
                "variables": {
                    "entity": "light.kitchen",
                    "component_name": "Light with slider",
                },
            },
            {
                "n": 2,
                "kind": "template",
                "template": "{% set state = (states(entity)) %}{{ state }}",
                "variables": {"entity": "light.kitchen"},
            },
            {
                "n": 3,
                "kind": "template",
                "template": BRIGHTNESS_PRELUDE + "{{ brightness }}",
                "variables": {"entity": "light.kitchen"},
            },
            {
                "n": 4,
                "kind": "template",
                "template": BRIGHTNESS_PRELUDE + "{{ brightness }}%",
                "variables": {"entity": "light.kitchen"},
            },
        ],
        "actions": {
            "0:tap": {"output": "toggle", "vars": {}},
            "1:change": {"output": "set_brightness", "vars": {}},
        },
        "warnings": [],
    }


def test_prelude_single_expression_keeps_type() -> None:
    """Wrap a single-expression source in a typed set statement."""
    component = make_component(
        header=False,
        inputs={"brightness": "{{ state_attr(entity, 'brightness') | int(0) }}"},
        layout=[{"type": "label", "text": "{{ brightness }}"}],
    )
    card = make_card(component, {"params": {"entity": "light.kitchen"}})
    [slot] = compile_card(component, card)["slots"]
    assert slot["template"] == (
        "{% set brightness = (state_attr(entity, 'brightness') | int(0)) %}"
        "{{ brightness }}"
    )
    assert "{% endset %}" not in slot["template"]


def test_prelude_block_for_mixed_template() -> None:
    """Wrap a mixed source in a block set and trim the result."""
    component = make_component(
        header=False,
        inputs={"summary": "on: {{ states(entity) }}"},
        layout=[{"type": "label", "text": "{{ summary }}"}],
    )
    card = make_card(component, {"params": {"entity": "light.kitchen"}})
    [slot] = compile_card(component, card)["slots"]
    assert slot["template"] == (
        "{% set summary %}on: {{ states(entity) }}{% endset %}"
        "{% set summary = summary | trim %}{{ summary }}"
    )


def test_prelude_only_mentioned_inputs() -> None:
    """Inline only the inputs the source actually mentions."""
    component = make_component(
        header=False,
        inputs={
            "used": "{{ states(entity) }}",
            "unused": "{{ state_attr(entity, 'brightness') }}",
        },
        layout=[{"type": "label", "text": "{{ used }}"}],
    )
    card = make_card(component, {"params": {"entity": "light.kitchen"}})
    [slot] = compile_card(component, card)["slots"]
    assert slot["template"] == "{% set used = (states(entity)) %}{{ used }}"


def test_transitive_inputs_included() -> None:
    """Inline inputs mentioned by an already inlined input, in order."""
    component = make_component(
        header=False,
        inputs={
            "a": "{{ states(entity) }}",
            "b": "{{ a | float(0) + 1 }}",
        },
        layout=[{"type": "label", "text": "{{ b }}"}],
    )
    card = make_card(component, {"params": {"entity": "light.kitchen"}})
    [slot] = compile_card(component, card)["slots"]
    assert slot["template"] == (
        "{% set a = (states(entity)) %}{% set b = (a | float(0) + 1) %}{{ b }}"
    )


def test_identical_slots_shared() -> None:
    """Give two identical templates the same slot number."""
    component = make_component(
        header=False,
        inputs={"brightness": "{{ state_attr(entity, 'brightness') }}"},
        layout=[
            {"type": "label", "text": "{{ brightness }}%"},
            {"type": "label", "text": "{{ brightness }}%"},
        ],
    )
    card = make_card(component, {"params": {"entity": "light.kitchen"}})
    compiled = compile_card(component, card)
    assert len(compiled["slots"]) == 1
    assert compiled["widgets"][0]["text"] == {"s": 1}
    assert compiled["widgets"][1]["text"] == {"s": 1}


def test_for_each_expands_and_caps_at_eight() -> None:
    """Repeat a for_each item at most eight times."""
    component = make_component(
        header=False,
        size="2x4",
        params={"items": {"domain": "light", "multiple": True}},
        layout=[
            {
                "type": "label",
                "text": "{{ item }}",
                "for_each": "items",
                "as": "item",
            },
        ],
    )
    entities = [f"light.l{n}" for n in range(10)]
    # Validation allows eight entities, so go past it to reach the compiler's cap.
    card = make_card(component, {"params": {"items": entities[:8]}})
    card["params"]["items"] = entities
    compiled = compile_card(component, card)
    assert [widget["i"] for widget in compiled["widgets"]] == list(range(8))
    assert compiled["warnings"] == []
    for n, slot in enumerate(compiled["slots"]):
        assert slot["variables"]["item"] == f"light.l{n}"


def test_loop_variable_in_action_vars() -> None:
    """Record the loop variable in the action vars of each copy."""
    component = make_component(
        header=False,
        params={"items": {"domain": "light", "multiple": True}},
        inputs={"state": "{{ states(item) }}"},
        outputs={
            "toggle": {
                "action": "light.toggle",
                "data": {"entity_id": "{{ item }}"},
                "feedback": "optimistic",
            },
        },
        layout=[
            {
                "type": "switch",
                "value": "state",
                "on_tap": "toggle",
                "for_each": "items",
                "as": "item",
            },
        ],
    )
    card = make_card(component, {"params": {"items": ["light.one", "light.two"]}})
    compiled = compile_card(component, card)
    assert compiled["actions"] == {
        "0:tap": {"output": "toggle", "vars": {"item": "light.one"}},
        "1:tap": {"output": "toggle", "vars": {"item": "light.two"}},
    }


def test_title_from_card_then_entity_then_name() -> None:
    """Pick the title from the card, then the entity, then the name."""
    component = make_component(
        name="Demo Light",
        header=True,
        inputs={"state": "{{ states(entity) }}"},
        outputs={"toggle": toggle_output()},
        layout=[{"type": "switch", "value": "state", "on_tap": "toggle"}],
        preview={"inputs": {"state": "on"}},
    )
    titled = compile_card(
        component,
        make_card(
            component,
            {"params": {"entity": "light.kitchen"}, "title": "Kitchen"},
        ),
    )
    assert titled["header"]["title"] == "Kitchen"
    literal = compile_card(
        component,
        make_card(
            component,
            {"params": {"entity": "light.kitchen"}, "title": "{{ states('x') }}"},
        ),
    )
    assert literal["header"]["title"] == "{{ states('x') }}"
    named = compile_card(
        component, make_card(component, {"params": {"entity": "light.kitchen"}})
    )
    assert named["header"]["title"] == {"s": 1}
    assert named["slots"][0]["template"] == (
        "{{ state_attr(entity, 'friendly_name') or component_name }}"
    )
    assert named["slots"][0]["variables"] == {
        "entity": "light.kitchen",
        "component_name": "Demo Light",
    }
    demo = compile_card(component, make_card(component))
    assert demo["header"]["title"] == "Demo Light"


def test_on_binding_is_first_switch() -> None:
    """Take the on binding from the first switch widget, if any."""
    component = make_component(
        header=False,
        inputs={
            "a": "{{ states(entity) }}",
            "b": "{{ state_attr(entity, 'brightness') }}",
        },
        layout=[
            {"type": "switch", "value": "a"},
            {"type": "switch", "value": "b"},
        ],
    )
    card = make_card(component, {"params": {"entity": "light.kitchen"}})
    compiled = compile_card(component, card)
    assert compiled["on"] == {"s": 1}
    assert compiled["widgets"][1]["value"] == {"s": 2}
    plain = make_component(
        header=False,
        inputs={"state": "{{ states(entity) }}"},
        layout=[{"type": "label", "text": "{{ state }}"}],
    )
    card = make_card(plain, {"params": {"entity": "light.kitchen"}})
    assert compile_card(plain, card)["on"] is None


def test_example_mode_uses_preview_constants() -> None:
    """Fill missing params and listed inputs from the preview in demo mode."""
    component = make_component(
        header=False,
        inputs={
            "state": "{{ states(entity) }}",
            "brightness": "{{ state_attr(entity, 'brightness') }}",
        },
        layout=[
            {"type": "switch", "value": "state"},
            {"type": "label", "text": "{{ brightness }}%"},
        ],
        preview={
            "params": {"entity": "light.preview"},
            "inputs": {"state": "on", "brightness": 42},
        },
    )
    compiled = compile_card(component, make_card(component))
    assert compiled["demo"] is True
    assert compiled["entities"] == []
    assert compiled["widgets"][0]["value"] == "on"
    [slot] = compiled["slots"]
    assert compiled["widgets"][1]["text"] == {"s": 1}
    assert slot["template"] == "{{ brightness }}%"
    assert slot["variables"] == {"entity": "light.preview", "brightness": 42}


def test_example_mode_without_preview_raises() -> None:
    """Refuse a demo card when the component has no preview values."""
    component = make_component(
        inputs={"state": "{{ states(entity) }}"},
        layout=[{"type": "switch", "value": "state"}],
    )
    with pytest.raises(MakerError):
        compile_card(component, make_card(component))


def test_camera_input_becomes_template() -> None:
    """Compile a camera input to an entity_picture template slot."""
    component = make_component(
        header=False,
        size="2x2",
        params={"entity": {"domain": "camera"}},
        inputs={"cam": {"source": "camera", "entity": "{{ entity }}", "refresh": 10}},
        layout=[{"type": "image", "value": "cam"}],
    )
    card = make_card(component, {"params": {"entity": "camera.door"}})
    compiled = compile_card(component, card)
    [slot] = compiled["slots"]
    assert slot == {
        "n": 1,
        "kind": "template",
        "template": (
            "{% set cam = (state_attr(entity, 'entity_picture') or '') %}{{ cam }}"
        ),
        "variables": {"entity": "camera.door"},
    }
    assert compiled["widgets"][0]["refresh"] == 10


def test_history_slot() -> None:
    """Compile a history input to a history slot with the param entity."""
    component = make_component(
        header=False,
        params={"entity": {"domain": "sensor"}},
        inputs={"past": {"source": "recorder", "entity": "{{ entity }}", "hours": 24}},
        layout=[{"type": "chart", "value": "past", "kind": "line"}],
    )
    card = make_card(component, {"params": {"entity": "sensor.outside"}})
    compiled = compile_card(component, card)
    assert compiled["slots"] == [
        {"n": 1, "kind": "history", "entity": "sensor.outside", "hours": 24},
    ]
    assert compiled["widgets"][0]["value"] == {"s": 1}


def test_action_slot() -> None:
    """Compile an action input to a slot carrying entity_id and variables."""
    result = "{{ response[entity].forecast | map(attribute='temperature') | list }}"
    component = make_component(
        header=False,
        params={"entity": {"domain": "weather"}},
        inputs={
            "poll": {
                "action": "weather.get_forecasts",
                "data": {"entity_id": "{{ entity }}", "type": "daily"},
                "result": result,
                "refresh": 60,
            },
        },
        layout=[{"type": "chart", "value": "poll"}],
    )
    card = make_card(component, {"params": {"entity": "weather.home"}})
    compiled = compile_card(component, card)
    assert compiled["slots"] == [
        {
            "n": 1,
            "kind": "action",
            "action": "weather.get_forecasts",
            "data": {"entity_id": "weather.home", "type": "daily"},
            "result": result,
            "variables": {"entity": "weather.home"},
            "refresh": 60,
        },
    ]


def test_local_tap_carries_entity() -> None:
    """Attach the first single-entity param to a local details tap."""
    component = make_component(
        header=False,
        outputs={"details": {"local": "open_details"}},
        layout=[{"type": "button", "text": "More", "on_tap": "details"}],
    )
    card = make_card(component, {"params": {"entity": "light.kitchen"}})
    compiled = compile_card(component, card)
    assert compiled["widgets"][0]["tap"] == {
        "local": "open_details",
        "entity": "light.kitchen",
    }
    assert compiled["actions"] == {}


def test_public_card_strips_server_parts() -> None:
    """Remove slots and actions from the browser copy of a card."""
    component = make_component(
        header=False,
        inputs={"state": "{{ states(entity) }}"},
        outputs={"toggle": toggle_output()},
        layout=[{"type": "switch", "value": "state", "on_tap": "toggle"}],
    )
    card = make_card(component, {"params": {"entity": "light.kitchen"}})
    compiled = compile_card(component, card)
    public = public_card(compiled)
    assert "slots" in compiled and "actions" in compiled
    assert set(public) == set(compiled) - {"slots", "actions"}
    assert public["widgets"] == compiled["widgets"]


def test_compile_is_deterministic() -> None:
    """Compile the same inputs twice to the same result."""
    component = make_component(
        header=False,
        inputs={"state": "{{ states(entity) }}"},
        outputs={"toggle": toggle_output()},
        layout=[
            {"type": "switch", "value": "state", "on_tap": "toggle"},
            {"type": "label", "text": "{{ state }}"},
        ],
    )
    card = make_card(component, {"params": {"entity": "light.kitchen"}})
    assert compile_card(component, card) == compile_card(component, card)
