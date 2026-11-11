"""Tests for the maker schema validators."""

from pathlib import Path

import pytest
import yaml

from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.schema import (
    is_allowed_action,
    is_tab_dashboard,
    validate_card_config,
    validate_component,
    validate_dashboard_options,
    validate_style,
)

COMPONENTS_DIR = (
    Path(__file__).parent.parent
    / "custom_components"
    / "apollo_tab"
    / "library"
    / "components"
)

EXPECTED_BUILTIN_IDS = {
    "apollo/alarm-panel",
    "apollo/blinds",
    "apollo/camera-snapshot",
    "apollo/fan",
    "apollo/light-slider",
    "apollo/light-tile",
    "apollo/lock",
    "apollo/media-player",
    "apollo/scene-row",
    "apollo/sensor-graph",
    "apollo/sensor-value",
    "apollo/thermostat",
    "apollo/weather",
    "community/energy-gauge",
    "community/presence-chips",
    "community/room-summary",
}


def _base(**overrides):
    """Return a minimal valid component document with overrides applied."""
    doc = {
        "id": "test/demo",
        "version": "1.0.0",
        "name": "Demo",
        "size": "1x1",
        "params": {"entity": {"domain": "light"}},
        "inputs": {"state": "{{ states(entity) }}"},
        "layout": [{"type": "label", "text": "{{ states(entity) }}"}],
    }
    doc.update(overrides)
    return doc


def _toggle_doc(**overrides):
    """Return a valid component with one action output and one button."""
    doc = {
        "action": "light.toggle",
        "data": {"entity_id": "{{ entity }}"},
        "feedback": "optimistic",
    }
    base = _base(
        outputs={"run": doc},
        layout=[{"type": "button", "text": "Go", "on_tap": "run"}],
    )
    base.update(overrides)
    return base


def _camera_doc(refresh):
    """Return a camera component document with the given snapshot refresh."""
    snap = {"source": "camera", "entity": "{{ entity }}"}
    if refresh is not None:
        snap["refresh"] = refresh
    return _base(
        params={"entity": {"domain": "camera"}},
        inputs={"snap": snap},
        layout=[{"type": "image", "value": "snap"}],
    )


def test_all_builtin_components_validate():
    """Validate all 16 bundled component files."""
    files = sorted(COMPONENTS_DIR.glob("*.yaml"))
    assert len(files) == 16
    seen = {}
    for path in files:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        component = validate_component(doc)
        seen[path.name] = component["id"]
    assert set(seen.values()) == EXPECTED_BUILTIN_IDS


def test_unknown_top_level_key_rejected():
    """Reject a component carrying a key the schema does not list."""
    with pytest.raises(MakerError) as excinfo:
        validate_component(_base(bogus=1))
    assert excinfo.value.code == "unknown_key"


def test_unknown_layout_key_rejected():
    """Reject a layout item carrying a key its type does not list."""
    doc = _base(layout=[{"type": "switch", "value": "state", "colour": "red"}])
    with pytest.raises(MakerError) as excinfo:
        validate_component(doc)
    assert excinfo.value.code == "unknown_key"


def test_bad_id_rejected():
    """Reject ids that break the id pattern or the length limit."""
    long_id = "a" * 40 + "/" + "b" * 40
    for bad in ("Test/demo", "test/", "test/d--mo", "test//demo", long_id):
        with pytest.raises(MakerError) as excinfo:
            validate_component(_base(id=bad))
        assert excinfo.value.code == "bad_id"


def test_size_out_of_range_rejected():
    """Reject sizes outside the 1..6 by 1..4 unit range."""
    for bad in ("0x1", "7x1", "1x5", "12x1", "1 x 1", 6):
        with pytest.raises(MakerError) as excinfo:
            validate_component(_base(size=bad))
        assert excinfo.value.code == "bad_value"


def test_name_collision_rejected():
    """Reject a param and an input sharing one name."""
    doc = _base(inputs={"entity": "{{ states('light.kitchen') }}"})
    with pytest.raises(MakerError) as excinfo:
        validate_component(doc)
    assert excinfo.value.code == "duplicate_name"


def test_reserved_names_rejected():
    """Reject the reserved names value, response and component_name."""
    for reserved in ("value", "response", "component_name"):
        with pytest.raises(MakerError) as excinfo:
            validate_component(_base(inputs={reserved: "{{ 1 }}"}))
        assert excinfo.value.code == "bad_name"
        with pytest.raises(MakerError) as excinfo:
            validate_component(_base(params={reserved: {"domain": "light"}}))
        assert excinfo.value.code == "bad_name"


def test_too_many_layout_items_rejected():
    """Reject more than sixteen layout items."""
    layout = [{"type": "label", "text": f"row {index}"} for index in range(17)]
    with pytest.raises(MakerError) as excinfo:
        validate_component(_base(layout=layout))
    assert excinfo.value.code == "too_many"


def test_string_too_long_rejected():
    """Reject strings that exceed their length limit."""
    with pytest.raises(MakerError) as excinfo:
        validate_component(_base(description="x" * 161))
    assert excinfo.value.code == "too_long"
    layout = [{"type": "label", "text": "y" * 1025}]
    with pytest.raises(MakerError) as excinfo:
        validate_component(_base(layout=layout))
    assert excinfo.value.code == "too_long"


def test_action_domain_not_allowed():
    """Reject outputs calling a domain outside the allow list."""
    doc = _toggle_doc(
        outputs={
            "run": {
                "action": "homeassistant.toggle",
                "data": {"entity_id": "{{ entity }}"},
                "feedback": "optimistic",
            }
        }
    )
    with pytest.raises(MakerError) as excinfo:
        validate_component(doc)
    assert excinfo.value.code == "action_not_allowed"


def test_action_must_target_param_entity():
    """Reject an entity_id reference that names no usable param or loop."""
    doc = _toggle_doc(
        outputs={
            "run": {
                "action": "light.toggle",
                "data": {"entity_id": "{{ ghost }}"},
                "feedback": "optimistic",
            }
        }
    )
    with pytest.raises(MakerError) as excinfo:
        validate_component(doc)
    assert excinfo.value.code == "unknown_param"


def test_action_domain_must_match_param():
    """Reject an output whose action domain differs from the param's domain."""
    doc = _toggle_doc(
        outputs={
            "run": {
                "action": "switch.toggle",
                "data": {"entity_id": "{{ entity }}"},
                "feedback": "optimistic",
            }
        }
    )
    with pytest.raises(MakerError) as excinfo:
        validate_component(doc)
    assert excinfo.value.code == "domain_mismatch"


def test_literal_entity_id_rejected():
    """Reject a literal entity id where a {{ name }} reference is required."""
    doc = _toggle_doc(
        outputs={
            "run": {
                "action": "light.toggle",
                "data": {"entity_id": "light.kitchen"},
                "feedback": "optimistic",
            }
        }
    )
    with pytest.raises(MakerError) as excinfo:
        validate_component(doc)
    assert excinfo.value.code == "bad_value"


def test_nested_data_rejected():
    """Reject lists and mappings inside action data."""
    for extra in ({"payload": {"a": 1}}, {"payload": [1, 2]}):
        doc = _toggle_doc(
            outputs={
                "run": {
                    "action": "light.toggle",
                    "data": {"entity_id": "{{ entity }}", **extra},
                    "feedback": "optimistic",
                }
            }
        )
        with pytest.raises(MakerError) as excinfo:
            validate_component(doc)
        assert excinfo.value.code == "bad_value"


def test_lock_output_requires_confirm():
    """Require confirm feedback for outputs in sensitive domains."""
    doc = _toggle_doc(
        params={"entity": {"domain": "lock"}},
        outputs={
            "unlock": {
                "action": "lock.unlock",
                "data": {"entity_id": "{{ entity }}"},
                "feedback": "optimistic",
            }
        },
        layout=[{"type": "button", "text": "Unlock", "on_tap": "unlock"}],
    )
    with pytest.raises(MakerError) as excinfo:
        validate_component(doc)
    assert excinfo.value.code == "confirm_required"


def test_sensitive_flag_set():
    """Mark components with sensitive outputs as sensitive."""
    doc = _toggle_doc(
        params={"entity": {"domain": "lock"}},
        outputs={
            "unlock": {
                "action": "lock.unlock",
                "data": {"entity_id": "{{ entity }}"},
                "feedback": "confirm",
            }
        },
        layout=[{"type": "button", "text": "Unlock", "on_tap": "unlock"}],
    )
    component = validate_component(doc)
    assert component["sensitive"] is True
    output = component["outputs"]["unlock"]
    assert output["entity_ref"] == "entity"
    assert output["data"]["entity_id"] == "{{ entity }}"
    assert validate_component(_base())["sensitive"] is False


def test_for_each_output_uses_loop_variable():
    """Resolve an output entity reference through the loop variable."""
    doc = _base(
        params={"scenes": {"domain": "scene", "multiple": True}},
        inputs={},
        outputs={
            "run": {
                "action": "scene.turn_on",
                "data": {"entity_id": "{{ scene }}"},
                "feedback": "optimistic",
            }
        },
        layout=[
            {
                "type": "button",
                "text": "Run",
                "on_tap": "run",
                "for_each": "scenes",
                "as": "scene",
            }
        ],
    )
    component = validate_component(doc)
    assert component["outputs"]["run"]["entity_ref"] == "scene"
    assert component["layout"][0]["for_each"] == "scenes"
    assert component["layout"][0]["as"] == "scene"
    bad = _base(
        layout=[{"type": "label", "text": "x", "for_each": "entity", "as": "e"}]
    )
    with pytest.raises(MakerError) as excinfo:
        validate_component(bad)
    assert excinfo.value.code == "unknown_param"


def test_read_action_allow_list():
    """Allow only listed read actions as inputs and normalise their shape."""
    good = _base(
        params={"entity": {"domain": "weather"}},
        inputs={
            "forecast": {
                "action": "weather.get_forecasts",
                "data": {"entity_id": "{{ entity }}", "type": "daily"},
                "result": "{{ response[entity].forecast | list }}",
            }
        },
        layout=[{"type": "chart", "value": "forecast"}],
    )
    component = validate_component(good)
    assert component["inputs"]["forecast"] == {
        "kind": "action",
        "action": "weather.get_forecasts",
        "param": "entity",
        "data": {"type": "daily"},
        "result": "{{ response[entity].forecast | list }}",
        "refresh": 1800,
    }
    bad = _base(
        params={"entity": {"domain": "weather"}},
        inputs={
            "forecast": {
                "action": "weather.reload",
                "data": {"entity_id": "{{ entity }}"},
                "result": "{{ response }}",
            }
        },
        layout=[{"type": "chart", "value": "forecast"}],
    )
    with pytest.raises(MakerError) as excinfo:
        validate_component(bad)
    assert excinfo.value.code == "action_not_allowed"


def test_history_input_only_feeds_chart():
    """Allow history inputs only as the bare value of a chart."""
    inputs = {"hist": {"source": "recorder", "entity": "{{ entity }}"}}
    good = _base(
        params={"entity": {"domain": "sensor"}},
        inputs=inputs,
        layout=[{"type": "chart", "value": "hist"}],
    )
    component = validate_component(good)
    assert component["inputs"]["hist"] == {
        "kind": "history",
        "param": "entity",
        "hours": 24,
    }
    bad = _base(
        params={"entity": {"domain": "sensor"}},
        inputs=inputs,
        layout=[{"type": "switch", "value": "hist"}],
    )
    with pytest.raises(MakerError) as excinfo:
        validate_component(bad)
    assert excinfo.value.code == "bad_value"


def test_duration_parsing():
    """Parse durations to seconds and enforce their allowed range."""
    component = validate_component(_camera_doc(None))
    assert component["inputs"]["snap"]["refresh"] == 10
    cases = {10: 10, "10s": 10, "30min": 1800, "1h": 3600, 3600: 3600}
    for raw, expected in cases.items():
        component = validate_component(_camera_doc(raw))
        assert component["inputs"]["snap"]["refresh"] == expected
    for bad in ("5m", "soon", 2, 4000, True, 3.5):
        with pytest.raises(MakerError) as excinfo:
            validate_component(_camera_doc(bad))
        assert excinfo.value.code == "bad_value"


def test_value_must_be_input_or_template():
    """Accept only an input name or a template as a control value."""
    doc = _base(layout=[{"type": "switch", "value": "state"}])
    component = validate_component(doc)
    assert component["layout"][0]["value"] == {"input": "state"}
    doc = _base(layout=[{"type": "switch", "value": "{{ states(entity) }}"}])
    component = validate_component(doc)
    assert component["layout"][0]["value"] == {"template": "{{ states(entity) }}"}
    for bad in ("mystery", 42, True):
        doc = _base(layout=[{"type": "switch", "value": bad}])
        with pytest.raises(MakerError) as excinfo:
            validate_component(doc)
        assert excinfo.value.code == "unknown_input"


def test_icon_must_be_mdi():
    """Require icons to be mdi references."""
    component = validate_component(_base(icon="mdi:lightbulb"))
    assert component["icon"] == "mdi:lightbulb"
    for bad in ("lightbulb", "mdi:Light", "mdi:", 12):
        with pytest.raises(MakerError) as excinfo:
            validate_component(_base(icon=bad))
        assert excinfo.value.code == "bad_value"
    doc = _toggle_doc(layout=[{"type": "button", "icon": "fire", "on_tap": "run"}])
    with pytest.raises(MakerError) as excinfo:
        validate_component(doc)
    assert excinfo.value.code == "bad_value"


def test_card_config_entity_domain_checked():
    """Check entity ids in card configs against the param domain."""
    component = validate_component(_base(size="2x1"))
    cfg = validate_card_config(component, {"params": {"entity": "light.kitchen"}})
    assert cfg["params"] == {"entity": "light.kitchen"}
    with pytest.raises(MakerError) as excinfo:
        validate_card_config(component, {"params": {"entity": "switch.kitchen"}})
    assert excinfo.value.code == "bad_value"
    with pytest.raises(MakerError) as excinfo:
        validate_card_config(component, {"params": {"ghost": "light.kitchen"}})
    assert excinfo.value.code == "unknown_param"


def test_card_config_missing_params_listed():
    """List absent entity params instead of raising."""
    doc = _base(
        params={
            "entity": {"domain": "light"},
            "scenes": {"domain": "scene", "multiple": True},
        }
    )
    component = validate_component(doc)
    cfg = validate_card_config(component, {})
    assert cfg["missing"] == ["entity", "scenes"]
    assert cfg["params"] == {}
    cfg = validate_card_config(
        component, {"params": {"entity": "light.kitchen", "scenes": "scene.movie"}}
    )
    assert cfg["missing"] == []
    assert cfg["params"]["scenes"] == ["scene.movie"]
    cfg = validate_card_config(
        component,
        {"params": {"entity": "light.kitchen", "scenes": ["scene.a", "scene.b"]}},
    )
    assert cfg["params"]["scenes"] == ["scene.a", "scene.b"]
    nine = [f"scene.s{index}" for index in range(9)]
    with pytest.raises(MakerError) as excinfo:
        validate_card_config(
            component, {"params": {"entity": "light.kitchen", "scenes": nine}}
        )
    assert excinfo.value.code == "bad_value"


def test_card_config_grid_defaults_from_size():
    """Derive grid size from the component size unless grid_options override."""
    component = validate_component(_base(size="2x1"))
    cfg = validate_card_config(component, {})
    assert (cfg["columns"], cfg["rows"]) == (12, 3)
    cfg = validate_card_config(component, {"grid_options": {"columns": 24, "rows": 6}})
    assert (cfg["columns"], cfg["rows"]) == (24, 6)
    cfg = validate_card_config(component, {"grid_options": {"columns": "full"}})
    assert (cfg["columns"], cfg["rows"]) == ("full", 3)
    cfg = validate_card_config(
        component, {"grid_options": {"columns": 99, "rows": True}}
    )
    assert (cfg["columns"], cfg["rows"]) == (12, 3)
    cfg = validate_card_config(component, {"grid_options": "wide"})
    assert (cfg["columns"], cfg["rows"]) == (12, 3)


def test_style_rejects_unknown_key():
    """Reject style keys outside the listed set."""
    with pytest.raises(MakerError) as excinfo:
        validate_style({"texture": "rough"})
    assert excinfo.value.code == "unknown_key"


def test_style_rejects_non_hex_colour():
    """Reject colours that are not #RRGGBB values."""
    for bad in ("red", "#12345", "#GGGGGG", "203040", 12):
        with pytest.raises(MakerError) as excinfo:
            validate_style({"color": bad})
        assert excinfo.value.code == "bad_value"
    assert validate_style({"color": "#a0b0c0"}) == {"color": "#A0B0C0"}


def test_style_rejects_angled_gradient():
    """Reject gradient directions other than vertical and horizontal."""
    with pytest.raises(MakerError) as excinfo:
        validate_style({"gradient": {"to": "#101820", "direction": "45deg"}})
    assert excinfo.value.code == "bad_value"
    style = validate_style({"gradient": {"to": "#101820"}})
    assert style == {"gradient": {"to": "#101820", "direction": "vertical"}}


def test_style_rejects_alpha_colour():
    """Reject colours carrying an alpha channel."""
    with pytest.raises(MakerError) as excinfo:
        validate_style({"color": "#20304080"})
    assert excinfo.value.code == "bad_value"


def test_style_transparency_range():
    """Accept transparency only as an integer from 0 to 100."""
    assert validate_style({"transparency": 20}) == {"transparency": 20}
    for bad in (-1, 101, 20.5, True, "20"):
        with pytest.raises(MakerError) as excinfo:
            validate_style({"transparency": bad})
        assert excinfo.value.code == "bad_value"


def test_dashboard_options_defaults():
    """Fill dashboard option defaults and reject bad values."""
    assert validate_dashboard_options({}) == {"version": 1, "theme": "midnight"}
    assert validate_dashboard_options({"theme": "warm"}) == {
        "version": 1,
        "theme": "warm",
    }
    with pytest.raises(MakerError) as excinfo:
        validate_dashboard_options({"version": 2})
    assert excinfo.value.code == "bad_value"
    with pytest.raises(MakerError) as excinfo:
        validate_dashboard_options({"theme": "neon"})
    assert excinfo.value.code == "bad_value"
    with pytest.raises(MakerError) as excinfo:
        validate_dashboard_options({"extra": 1})
    assert excinfo.value.code == "unknown_key"


def test_is_tab_dashboard():
    """Detect dashboards carrying an apollo_tab options mapping."""
    assert is_tab_dashboard({"apollo_tab": {}}) is True
    assert is_tab_dashboard({"apollo_tab": {"theme": "warm"}}) is True
    assert is_tab_dashboard({"apollo_tab": None}) is False
    assert is_tab_dashboard({"apollo_tab": "yes"}) is False
    assert is_tab_dashboard({}) is False
    assert is_tab_dashboard([]) is False


def test_script_output_limited_to_generic_services():
    """Allow script outputs only turn_on, turn_off and toggle."""
    for service in ("turn_on", "turn_off", "toggle"):
        doc = _toggle_doc(
            params={"entity": {"domain": "script"}},
            outputs={
                "run": {
                    "action": f"script.{service}",
                    "data": {"entity_id": "{{ entity }}"},
                    "feedback": "pulse",
                }
            },
        )
        component = validate_component(doc)
        assert component["outputs"]["run"]["action"] == f"script.{service}"
    for service in ("secret", "reload", "harmless"):
        doc = _toggle_doc(
            params={"entity": {"domain": "script"}},
            outputs={
                "run": {
                    "action": f"script.{service}",
                    "data": {"entity_id": "{{ entity }}"},
                    "feedback": "pulse",
                }
            },
        )
        with pytest.raises(MakerError) as excinfo:
            validate_component(doc)
        assert excinfo.value.code == "action_not_allowed"


def test_is_allowed_action():
    """Check the allowed domains and the per-domain service limits."""
    assert is_allowed_action("light.toggle") is True
    assert is_allowed_action("script.turn_on") is True
    assert is_allowed_action("script.turn_off") is True
    assert is_allowed_action("script.toggle") is True
    assert is_allowed_action("script.secret") is False
    assert is_allowed_action("script.reload") is False
    assert is_allowed_action("homeassistant.turn_on") is False
    assert is_allowed_action("notify.mobile") is False
