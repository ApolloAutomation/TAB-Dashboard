"""What a call may send and what a change may carry (cards spec C.2.8, C.5; I6).

The input checks of contract 7.3 (2) are checked against the HA cases of
input_v2.json; the rest are the typing rules of C.2.8.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.apollo_tab.maker import features, outputs
from custom_components.apollo_tab.maker.const import ALLOWED_SERVICES

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "contract" / "fixtures"
ICONS = json.loads((HERE / "contract" / "icons.json").read_text(encoding="utf-8"))
INPUT_V2 = json.loads((FIXTURES / "input_v2.json").read_text(encoding="utf-8"))
KIT = json.loads((FIXTURES / "layout_v2_kit.dl.json").read_text(encoding="utf-8"))


def _kit_widgets() -> dict[int, dict]:
    """Return every card and widget of the kit's device layout by id."""
    found = {}
    for page in KIT["pages"]:
        for item in page["w"]:
            found[item["id"]] = item
            for widget in item.get("w", []):
                found[widget["id"]] = widget
    return found


def _ha_cases() -> list[dict]:
    """Return the cases of input_v2.json that HA runs or refuses after 7.3."""
    return [
        case
        for case in INPUT_V2["cases"]
        if "payload" in case and case["verdict"] == "ok" and case["run"] is not None
    ]


def _event(case: dict) -> tuple[int, str, float | None]:
    """Return (widget id, event, value) of a case's payload."""
    fields = case["payload"]["d"].split("|")
    value = float(fields[8]) if fields[8] else None
    if value is not None and value.is_integer():
        value = int(value)
    return int(fields[5]), fields[6], value


@pytest.mark.parametrize("case", _ha_cases(), ids=lambda case: case["name"])
def test_the_input_checks_give_the_fixture_answer(case: dict) -> None:
    """Contract 7.3 (2): taps of cards, ranges, steps, live limits, choices."""
    widgets = _kit_widgets()
    widget_id, event, value = _event(case)
    widget = widgets[widget_id]
    sent = dict(case.get("sent", INPUT_V2["sent"]))
    if event == "t":
        # A t runs only for an item whose tap sends (HA keeps an action).
        run = isinstance(widget.get("tap"), dict) and "p" in widget["tap"]
    elif "change" not in widget:
        run = False
    elif widget["t"] == "choice":
        count = max(len(widget.get(key, [])) for key in ("texts", "icons", "cols"))
        run = outputs.check_choice(value, count)
    else:
        run = outputs.check_change(widget, value, sent.get)
    assert run is case["run"]


def test_every_rule_of_the_input_checks_has_a_case() -> None:
    """The fixture names the cases C.9 asks for; none is missing."""
    names = {case["name"] for case in _ha_cases()}
    assert {
        "card_without_tap",
        "change_for_a_widget_with_tap",
        "above_range",
        "below_range",
        "off_the_step",
        "step_0_between_steps",
        "live_step_never_sent",
        "below_live_min",
        "choice_index_past_the_options",
        "choice_index_fraction",
        "choice_index_below_0",
    } <= names


def test_check_change_never_divides_by_the_step() -> None:
    """A step of 0 or less means no grid; a live limit never sent refuses."""
    widget = {"min": 0, "max": 10, "step": 0}
    assert outputs.check_change(widget, 3.14159, lambda n: None) is True
    assert outputs.check_change({**widget, "step": -1}, 9.99, lambda n: None) is True
    assert outputs.check_change(widget, 10.5, lambda n: None) is False
    live = {"min": {"s": 4}, "max": 10, "step": 1}
    assert outputs.check_change(live, 5, lambda n: None) is False
    assert outputs.check_change(live, 5, {4: 2}.get) is True
    assert outputs.check_change(live, 1, {4: 2}.get) is False
    for bad in (float("nan"), float("inf"), True, "5", None):
        assert outputs.check_change(widget, bad, lambda n: None) is False
    # max itself always counts, also off the grid.
    assert outputs.check_change({"min": 0, "max": 9.5, "step": 2}, 9.5, None) is True


def test_constant_limits_count_as_the_tablet_holds_them() -> None:
    """A constant goes out with 3 decimals; that form is the one checked."""
    third = {"min": 0, "max": 10, "step": 1 / 3}
    # The tablet's grid is k * 0.333.
    assert outputs.check_change(third, 1.665, None) is True
    assert outputs.check_change(third, 9.99, None) is True
    assert outputs.check_change(third, 1.2, None) is False
    # A step too small for the wire goes out as 0: no grid, and no overflow.
    tiny = {"min": 0, "max": 10, "step": 1.0e-320}
    assert outputs.check_change(tiny, 3.14159, None) is True
    assert outputs.check_change(tiny, 11, None) is False


def test_check_choice() -> None:
    """A whole number from 0 to one below the number of options."""
    assert [outputs.check_choice(v, 3) for v in (0, 2, 2.0)] == [True] * 3
    for bad in (3, -1, 1.5, True, None, "1", float("nan")):
        assert outputs.check_choice(bad, 3) is False
    assert outputs.check_choice(0, 0) is False


def test_a_reference_takes_at_most_one_filter() -> None:
    """Exactly {{ name }} or {{ name.key }}, with int, float, round or rgb."""
    assert outputs.reference("{{ value }}") == ("value", None, None)
    assert outputs.reference("{{option.rgb}}") == ("option", "rgb", None)
    assert outputs.reference("{{ value | int }}") == ("value", None, "int")
    assert outputs.reference("{{ low_colour | rgb }}") == ("low_colour", None, "rgb")
    for text in (
        "{{ value | int | float }}",
        "{{ value | upper }}",
        "{{ value + 1 }}",
        "x{{ value }}",
        "{{ a.b.c }}",
        None,
    ):
        assert outputs.reference(text) is None


def test_filters_keep_types_and_never_read_text_back() -> None:
    """int, float, round and rgb are worked out here; none stays none."""
    assert outputs.apply_filter(41.7, "int") == 41
    assert outputs.apply_filter("12", "int") == 12
    assert outputs.apply_filter(2.5, "round") == 3
    assert outputs.apply_filter(3, "float") == 3.0
    assert outputs.apply_filter("abc", "int") is None
    assert outputs.apply_filter(None, "int") is None
    assert outputs.apply_filter(True, "int") is None
    assert outputs.apply_filter(0xFF8000, "rgb") == [255, 128, 0]
    assert outputs.apply_filter("#00ff80", "rgb") == [0, 255, 128]
    assert outputs.apply_filter([1, 2, 3], "rgb") == [1, 2, 3]
    for bad in ("red", -1, 0x1000000, [1, 2], [1, 2, 300], True):
        assert outputs.apply_filter(bad, "rgb") is None
    assert outputs.apply_filter({"a": 1}, None) == {"a": 1}


def test_rendered_text_is_typed_never_as_a_list_or_none() -> None:
    """A plain decimal is a number, True and False yes and no, the rest text."""
    assert outputs.typed_text("12") == 12
    assert outputs.typed_text(" -3.5 ") == -3.5
    assert outputs.typed_text("True") is True
    assert outputs.typed_text("False") is False
    for text in ("None", "[1, 2]", "{'a': 1}", "1e3", "12abc", "", "nan"):
        assert outputs.typed_text(text) == text


def test_uses_values_are_typed() -> None:
    """Number within 1e9, bool, entities; anything else is none or empty."""
    assert outputs.uses_value("number", 40) == 40
    assert outputs.uses_value("number", 40.5) == 40.5
    assert outputs.uses_value("number", "17") == 17
    for bad in (2e9, 10**400, float("inf"), "x", None, True, [1]):
        assert outputs.uses_value("number", bad) is None
    assert outputs.uses_value("bool", True) is True
    assert outputs.uses_value("bool", "off") is False
    assert outputs.uses_value("bool", 1) is None
    # entities: handed on whole, so entity_list refuses a bad list whole.
    for bad in (
        ["light.a", "x", 3],
        ["light.a", ["light.b"]],
        [f"light.l{i}" for i in range(17)],
    ):
        assert outputs.uses_value("entities", bad) == bad
        assert outputs.entity_list(outputs.uses_value("entities", bad)) is None
    assert outputs.uses_value("entities", "light.a") == ["light.a"]
    assert outputs.uses_value("entities", ("light.a",)) == ["light.a"]
    assert outputs.uses_value("entities", {"light.a": 1}) == []


def test_entity_id_is_one_text_or_a_list_of_1_to_16() -> None:
    """None, '', [], a list in a list, a mapping, list-like text: refused."""
    assert outputs.entity_list("light.a") == (["light.a"], False)
    assert outputs.entity_list(["light.a", "switch.b"]) == (
        ["light.a", "switch.b"],
        True,
    )
    for bad in (
        None,
        "",
        [],
        [["light.a"]],
        {"entity_id": "light.a"},
        "['light.a']",
        "light.a, light.b",
        [f"light.l{i}" for i in range(17)],
        ["light.a", None],
    ):
        assert outputs.entity_list(bad) is None, bad


def test_data_values_are_scalars_or_colour_lists() -> None:
    """A mapping never; a list only for a colour key, of numbers."""
    assert outputs.scalar_or_colour("brightness_pct", 40) == 40
    assert outputs.scalar_or_colour("effect", "None") == "None"
    assert outputs.scalar_or_colour("effect", None) is outputs.LEFT_OUT
    assert outputs.scalar_or_colour("rgb_color", [255, 0, 0]) == [255, 0, 0]
    with pytest.raises(outputs.NotAllowed):
        outputs.scalar_or_colour("effect", {"rgb": [1, 2, 3]})
    with pytest.raises(outputs.NotAllowed):
        outputs.scalar_or_colour("effect", [1, 2])
    with pytest.raises(outputs.NotAllowed):
        outputs.scalar_or_colour("rgb_color", [1, "2", 3])
    with pytest.raises(outputs.NotAllowed):
        outputs.colour_entry("hs_color", "100")
    with pytest.raises(outputs.NotAllowed):
        outputs.colour_entry("hs_color", None)


def test_the_question_per_entity() -> None:
    """A lock, an alarm, a garage, gate or door cover, or feedback confirm."""
    assert outputs.needs_question("optimistic", "lock", None) is True
    assert outputs.needs_question("optimistic", "alarm_control_panel", None) is True
    assert outputs.needs_question("optimistic", "cover", "garage") is True
    assert outputs.needs_question("optimistic", "cover", "blind") is False
    assert outputs.needs_question("confirm", "light", None) is True
    assert outputs.needs_question("pulse", "light", None) is False


def test_the_state_icon_table_holds_only_icons_of_the_contract() -> None:
    """Every icon state_icon can give is in icons.json."""
    names = set(ICONS["icons"])
    table = set(features._STATE_ICONS.values())
    table |= {icon for _limit, icon in features._BATTERY_ICONS} | {"mdi:battery"}
    table |= set(features._DEFAULT_ICONS.values())
    table |= set(features._DEFAULT_CLASS_ICONS.values())
    assert table <= names, table - names


def test_state_icon_by_kind_class_and_state() -> None:
    """The fixed table, then the kind's own icon; nothing a device reports."""
    assert features.state_icon("light", None, "on") == "mdi:lightbulb-on"
    assert features.state_icon("light", None, "off") == "mdi:lightbulb-outline"
    assert features.state_icon("light", None, "unavailable") == "mdi:lightbulb"
    assert features.state_icon("cover", "garage", "open") == "mdi:garage-open"
    assert features.state_icon("cover", "garage", "closed") == "mdi:garage"
    assert features.state_icon("cover", "curtain", "open") == "mdi:blinds-open"
    assert features.state_icon("lock", None, "jammed") == "mdi:lock-alert"
    # L2: a lock whose state is not known shows no padlock that says either.
    assert features.state_icon("lock", None, "unknown") == "mdi:lock-alert"
    assert features.state_icon("lock", None, "unavailable") == "mdi:lock-alert"
    assert features.state_icon("lock", None, "locking") == "mdi:lock-outline"
    assert features.state_icon("sensor", "battery", "8") == "mdi:battery-alert"
    assert features.state_icon("sensor", "battery", "55") == "mdi:battery-50"
    assert features.state_icon("sensor", "battery", "90") == "mdi:battery"
    assert features.state_icon("sensor", "battery", "x") == "mdi:battery"
    assert features.state_icon("weather", None, "pouring") == "mdi:weather-pouring"
    assert features.state_icon("nothing", None, "on") is None
    assert features.state_icon("light", "mdi:evil", "{{ 1 }}") == "mdi:lightbulb"


def test_schema_1_files_use_the_same_list_of_services() -> None:
    """The service list reaches schema 1 too; the 20 services of the 16 files pass."""
    from custom_components.apollo_tab.maker.schema import is_allowed_action

    for domain, services in ALLOWED_SERVICES.items():
        for service in services:
            assert is_allowed_action(f"{domain}.{service}")
    for action in (
        "scene.apply",
        "scene.create",
        "media_player.join",
        "media_player.play_media",
        "vacuum.send_command",
        "light.reload",
        "homeassistant.reload_all",
    ):
        assert is_allowed_action(action) is False
