"""Convert per layout version (cards spec C.4, C.5, C.6; package I5)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from custom_components.apollo_tab.maker import convert as convert_module, device
from custom_components.apollo_tab.maker.compile2 import validate_card_config2
from custom_components.apollo_tab.maker.compile2_v1 import compile_card2_v1
from custom_components.apollo_tab.maker.const import UPDATE_NOTE
from custom_components.apollo_tab.maker.convert import convert_dashboard
from custom_components.apollo_tab.maker.schema import validate_component

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LIBRARY = ROOT / "custom_components" / "apollo_tab" / "library"
CONTRACT = HERE / "contract"
ICONS = json.loads((CONTRACT / "icons.json").read_text(encoding="utf-8"))
CONTRACT_JSON = json.loads((CONTRACT / "contract.json").read_text(encoding="utf-8"))
LIGHT_DOC = yaml.safe_load((HERE / "cards2" / "light.yaml").read_text("utf-8"))
LEVEL1 = frozenset(
    name for name, (_code, level) in ICONS["icons"].items() if level <= 1
)
LAMP = "light.h1401"
# What the owner's lamp can do (facts of maker/features.py).
LAMP_FACTS = {
    "domain": "light",
    "toggle": True,
    "brightness": True,
    "colour": True,
    "temperature": True,
    "min_kelvin": 2000,
    "max_kelvin": 6500,
    "effects": False,
    "effect_list": [],
    "icon": "mdi:lightbulb",
}
# Keys a layout v1 may hold (contract 4.3 version 1, in layout form).
V1_CARD_KEYS = {"id", "t", "r", "component", "header", "on", "style", "w"}
V1_WIDGET_KEYS = {
    "id",
    "t",
    "r",
    "value",
    "min",
    "max",
    "step",
    "text",
    "confirm",
    "size",
    "icon",
    "kind",
    "tap",
    "change",
    "refresh",
}

# A card whose one variant holds every kind of item C.6 talks about.
FORMS_DOC = {
    "schema": 2,
    "id": "test/forms",
    "version": "1.0.0",
    "name": "Forms",
    "icon": "mdi:air-conditioner",
    "params": {"entity": {"domain": "light"}},
    "options": {
        "cold": {
            "type": "icon",
            "section": "look",
            "label": "Cold",
            "default": "mdi:air-conditioner",
        },
        "warm": {
            "type": "icon",
            "section": "look",
            "label": "Warm",
            "default": "mdi:lightbulb",
        },
    },
    "inputs": {
        "is_on": "{{ is_state(entity, 'on') }}",
        "pct": "{{ state_attr(entity, 'brightness') }}",
        "now": {"source": "clock"},
        "state": "{{ states(entity) }}",
    },
    "outputs": {
        "toggle": {
            "action": "light.toggle",
            "data": {"entity_id": "{{ entity }}"},
            "feedback": "optimistic",
        },
        "set": {
            "action": "light.turn_on",
            "data": {"entity_id": "{{ entity }}", "brightness_pct": "{{ value }}"},
            "feedback": "optimistic",
        },
    },
    "on": "is_on",
    "state": "state",
    "tap": {
        "default": "toggle",
        "choices": {"toggle": {"label": "Toggle", "output": "toggle"}},
    },
    "variants": {
        "big": {
            "name": "Big",
            "grid": [12, 12],
            "header": "tile",
            "trailing": "switch",
            "layout": [
                {"type": "label", "text": "{{ state }}", "size": "huge"},
                {"type": "label", "text": "Words", "size": "ml"},
                {"type": "label", "clock": 24, "value": "now", "size": "xl"},
                {
                    "type": "choice",
                    "options": [{"text": "A"}, {"text": "B"}],
                    "on_change": "set",
                },
                {
                    "type": "swap",
                    "items": [
                        {
                            "type": "button",
                            "text": "On",
                            "on_tap": "toggle",
                            "visible": "is_on",
                        },
                        {
                            "type": "button",
                            "text": "Off",
                            "on_tap": "toggle",
                            "visible": "{{ not is_on }}",
                        },
                    ],
                },
                {
                    "type": "button",
                    "text": "Shown",
                    "on_tap": "toggle",
                    "visible": "is_on",
                },
                {
                    "type": "slider",
                    "value": "pct",
                    "min": 0,
                    "max": 100,
                    "track": "hue",
                },
                {
                    "type": "slider",
                    "value": "pct",
                    "min": 0,
                    "max": 100,
                    "direction": "up",
                },
                {
                    "type": "slider",
                    "value": "pct",
                    "min": 0,
                    "max": 100,
                    "keep_active": True,
                },
                {
                    "type": "slider",
                    "value": "pct",
                    "min": 0,
                    "max": 100,
                    "look": "bar",
                    "icon": "mdi:brightness-6",
                    "colour": "accent",
                    "on_change": "set",
                },
                {"type": "button", "icon": "mdi:air-conditioner", "on_tap": "toggle"},
                {
                    "type": "button",
                    "icon": "mdi:air-conditioner",
                    "text": "Cool",
                    "on_tap": "toggle",
                },
                {
                    "type": "row",
                    "items": [
                        {"type": "button", "text": "A", "on_tap": "toggle"},
                        {"type": "button", "text": "B", "on_tap": "toggle"},
                    ],
                },
                {
                    "type": "button",
                    "text": "Old only",
                    "on_tap": "toggle",
                    "when": ["!tablet.v2"],
                },
                {"type": "image", "value": "{{ cold }}", "height": 48},
                {"type": "image", "value": "{{ warm }}", "height": 48},
            ],
        },
        "chooser": {
            "name": "Chooser",
            "grid": [12, 3],
            "header": "tile",
            "layout": [
                {
                    "type": "choice",
                    "options": [{"text": "A"}, {"text": "B"}],
                    "on_change": "set",
                }
            ],
        },
        "told": {
            "name": "Told",
            "grid": [6, 3],
            "header": "tile_v",
            "v1": "note",
            "layout": [{"type": "switch", "value": "is_on", "on_tap": "toggle"}],
        },
    },
}


def _library() -> tuple[dict, dict]:
    """Return the built-in cards with the colour light, and the themes."""
    components: dict[str, dict] = {}
    for path in sorted((LIBRARY / "components").glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            component = validate_component(doc)
            component["source"] = "builtin"
            components[component["id"]] = component
    for doc in (LIGHT_DOC, FORMS_DOC):
        component = validate_component(copy.deepcopy(doc))
        component["source"] = "builtin"
        components[component["id"]] = component
    themes = {
        theme["id"]: {k: v for k, v in theme.items() if k != "id"}
        for theme in json.loads((LIBRARY / "themes.json").read_text(encoding="utf-8"))
    }
    return components, themes


COMPONENTS, THEMES = _library()


def _card(component: str = "apollo/light", **extra: Any) -> dict:
    """Return a dashboard card of a component, for the owner's lamp."""
    return {
        "type": "custom:apollo-tab-card",
        "component": component,
        "params": {"entity": LAMP},
        **extra,
    }


def _dashboard(*cards: dict, **view: Any) -> dict:
    """Return a dashboard with one page of cards."""
    return {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [
            {
                "type": "sections",
                "path": "home",
                "title": "Home",
                "max_columns": 3,
                "sections": [{"type": "grid", "cards": list(cards)}],
                **view,
            }
        ],
    }


def _convert(
    config: dict,
    dl: int,
    components: dict | None = None,
    approved: set | None = None,
    **kwargs: Any,
) -> dict:
    """Convert a dashboard for the owner's lamp."""
    return convert_dashboard(
        config,
        components=components or COMPONENTS,
        themes=THEMES,
        approved=approved or set(),
        facts={LAMP: LAMP_FACTS},
        dl=dl,
        icons=ICONS,
        **kwargs,
    )


def _cards(layout: dict) -> list[dict]:
    """Return every card of a layout, in page order."""
    return [
        item for page in layout["pages"] for item in page["w"] if item["t"] == "card"
    ]


def _codes(result: dict) -> list[str]:
    """Return the warning codes of a conversion."""
    return [warning["code"] for warning in result["warnings"]]


def _with(doc: dict, path: list, value: Any) -> dict:
    """Return a validated built-in copy of a card file with one value set."""
    doc = copy.deepcopy(doc)
    target = doc
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    component = validate_component(doc)
    component["source"] = "builtin"
    return component


def _v1_keys_only(layout: dict) -> None:
    """Assert that a layout holds only keys of version 1 and level 1 icons."""
    assert layout["v"] == 1
    for page in layout["pages"]:
        assert set(page) <= {"id", "title", "view", "w", "icon"}
        for card in page["w"]:
            if card["t"] == "heading":
                continue
            assert set(card) <= V1_CARD_KEYS, set(card) - V1_CARD_KEYS
            icon = (card.get("header") or {}).get("icon")
            assert icon is None or icon in LEVEL1, icon
            for widget in card["w"]:
                assert set(widget) <= V1_WIDGET_KEYS, set(widget) - V1_WIDGET_KEYS
                assert widget["t"] in device.WIDGET_KINDS
                for key in ("icon", "value"):
                    if widget["t"] in ("button", "image") and isinstance(
                        widget.get(key), str
                    ):
                        assert widget[key] in LEVEL1, widget


# ---------------------------------------------------------------- acceptance


def test_one_schema_2_card_gives_a_layout_v2_with_its_detail_page() -> None:
    """dl=2: the card, and its detail page after the normal pages (C.4)."""
    result = _convert(_dashboard(_card()), 2)
    layout = result["layout"]
    assert layout["v"] == 2
    assert [page["id"] for page in layout["pages"]] == ["home", "home~1"]
    detail = layout["pages"][1]
    assert (detail["sub"], detail["ttl"], detail["title"]) == (1, 60, "Light")
    assert "sub" not in layout["pages"][0]
    # No side bar entry is ever written for a detail page.
    assert [entry["page"] for entry in layout["nav"]] == ["home"]
    card = layout["pages"][0]["w"][0]
    assert card["component"] == "apollo/light"
    assert card["hold"] == {"local": "go_to_page", "page": "home~1"}
    assert card["tap"] == {"policy": "optimistic"}
    # LOOK-NOTES decision 1: no heading (the card's header names the
    # device); the controls variant as tall as its rows, centred in the
    # page, without tap or hold.
    [copy_card] = detail["w"]
    bottom = max(w["r"][1] + w["r"][3] for w in copy_card["w"])
    assert copy_card["r"] == [404, 272, 568, 256]
    assert bottom + 16 == copy_card["r"][1] + copy_card["r"][3]
    assert copy_card["r"][1] * 2 + copy_card["r"][3] == 800
    assert "tap" not in copy_card
    assert "hold" not in copy_card
    assert result["simpler"] == 0
    assert "invalid_card" not in _codes(result)
    compiled = device.compile_device_layout(layout, ICONS, device.ENGINE_CAPS_V2)
    data = json.loads(compiled["bytes"])
    assert data["v"] == 2
    assert data["pages"][1]["sub"] == 1
    assert data["pages"][1]["ttl"] == 60
    assert [entry["p"] for entry in data["nav"]] == [0]
    assert data["pages"][0]["w"][0]["hold"] == {"go": 1}
    assert compiled["counts"]["normal_pages"] == 1


def test_the_same_dashboard_gives_a_layout_v1_with_the_cards_version_1_form() -> None:
    """dl=1: the tile names apollo/light-tile, which takes the lamp (C.6 rule 1)."""
    result = _convert(_dashboard(_card()), 1)
    layout = result["layout"]
    _v1_keys_only(layout)
    assert [page["id"] for page in layout["pages"]] == ["home"]
    [card] = _cards(layout)
    assert card["component"] == "apollo/light-tile"
    assert result["simpler"] == 1
    # The binding carries the id of the card that was really compiled (C.5).
    actions = result["bindings"]["actions"]
    assert actions
    assert {action["component"] for action in actions.values()} == {"apollo/light-tile"}
    compiled = device.compile_device_layout(layout, ICONS)
    assert json.loads(compiled["bytes"])["v"] == 1


def test_dl_1_is_the_default_and_schema_1_cards_stay_as_they_were() -> None:
    """The default is dl=1, and a schema 1 card is the same in both versions."""
    config = _dashboard(_card("apollo/light-tile"))
    default = convert_dashboard(
        config, components=COMPONENTS, themes=THEMES, approved=set()
    )
    assert default["layout"]["v"] == 1
    assert default["simpler"] == 0
    v2 = _convert(config, 2)["layout"]
    assert v2["v"] == 2
    assert v2["pages"][0]["w"] == default["layout"]["pages"][0]["w"]


def test_the_layout_version_is_part_of_the_hash() -> None:
    """The same dashboard gives two hashes, one per layout version."""
    config = _dashboard(_card("apollo/light-tile"))
    assert (
        _convert(config, 1)["layout"]["hash"] != _convert(config, 2)["layout"]["hash"]
    )


# ---------------------------------------------------------------- C.6, rule 1


def _tile_names(target: str) -> dict:
    """Return the light's file with its tile naming another old card."""
    return {
        **COMPONENTS,
        "apollo/light": _with(LIGHT_DOC, ["variants", "tile", "v1"], target),
    }


def test_an_old_card_that_refuses_the_params_is_not_used() -> None:
    """A light does not pass apollo/sensor-value, whose param is a sensor."""
    result = _convert(_dashboard(_card()), 1, _tile_names("apollo/sensor-value"))
    [card] = _cards(result["layout"])
    assert card["component"] == "apollo/light"
    _v1_keys_only(result["layout"])


def test_an_old_card_that_does_not_fit_the_variant_is_not_used() -> None:
    """apollo/light-slider is 12 x 3 and does not go into the 6 x 3 tile."""
    result = _convert(_dashboard(_card()), 1, _tile_names("apollo/light-slider"))
    [card] = _cards(result["layout"])
    assert card["component"] == "apollo/light"


def test_an_old_card_that_fits_is_used_with_the_cards_title() -> None:
    """The wide variant names apollo/light-slider, which fits 12 x 3."""
    result = _convert(
        _dashboard(_card(variant="wide", title="Sofa", grid_options={"columns": 12})), 1
    )
    [card] = _cards(result["layout"])
    assert card["component"] == "apollo/light-slider"
    assert card["header"]["title"] == "Sofa"


def test_an_unapproved_sensitive_old_card_is_not_used() -> None:
    """A sensitive user file stands in only when it is approved under its id."""
    old = dict(COMPONENTS["apollo/light-tile"])
    old.update(id="me/tile", source="user", sensitive=True)
    components = {**_tile_names("me/tile"), "me/tile": old}
    refused = _convert(_dashboard(_card()), 1, components)
    assert _cards(refused["layout"])[0]["component"] == "apollo/light"
    allowed = _convert(_dashboard(_card()), 1, components, approved={"me/tile"})
    [card] = _cards(allowed["layout"])
    assert card["component"] == "me/tile"
    actions = allowed["bindings"]["actions"].values()
    assert {action["component"] for action in actions} == {"me/tile"}


# ---------------------------------------------------------------- C.6, rule 2


def _forms(variant: str, dl: int = 1, **options: Any) -> dict:
    """Return the one card of a dashboard with the forms card."""
    card = _card(
        "test/forms", variant=variant, grid_options={"columns": 12, "rows": 12}
    )
    if options:
        card["options"] = options
    result = _convert(_dashboard(card), dl)
    [built] = _cards(result["layout"])
    return built


def test_the_own_form_leaves_out_what_needs_version_2() -> None:
    """Choices, swaps, visible items, new sliders and clocks are left out."""
    card = _forms("big")
    kinds = [(widget["t"], widget.get("text")) for widget in card["w"]]
    assert kinds == [
        ("switch", None),
        ("label", kinds[1][1]),
        ("label", "Words"),
        ("slider", None),
        ("button", "Cool"),
        ("button", "A"),
        ("button", "B"),
        ("button", "Old only"),
        ("image", None),
    ]
    switch, state, words, slider, cool, first, second, _old, image = card["w"]
    # An image whose fixed icon is above level 1 would show nothing: left out.
    assert image["value"] == "mdi:lightbulb"
    # The trailing switch is at the top, in the header from 300 px width.
    assert switch["r"][1] < card["header"]["r"][1] + card["header"]["r"][3]
    assert switch["tap"] == {"policy": "optimistic"}
    # Labels above l are drawn as l, ml as m.
    assert (state["size"], words["size"]) == ("l", "m")
    assert isinstance(state["text"], dict)
    # Look keys are dropped; the slider still works.
    assert slider["change"] == {"policy": "optimistic"}
    # An icon above level 1 is left out; the button keeps its text.
    assert "icon" not in cool
    # Neighbouring buttons share a row, as today.
    assert first["r"][1] == second["r"][1]


def test_the_layout_v2_form_of_the_same_card_keeps_all_of_it() -> None:
    """dl=2 has the choice, the swap and the new sliders, and not the v1 stand-in."""
    card = _forms("big", 2)
    kinds = [widget["t"] for widget in card["w"]]
    assert "choice" in kinds
    assert sum(1 for widget in card["w"] if "vis" in widget) >= 3
    assert any("track" in widget for widget in card["w"])
    assert all(widget.get("text") != "Old only" for widget in card["w"])


def test_a_trailing_text_becomes_a_small_label_row() -> None:
    """The tile's "68%" at the top right is a label row of size s in v1."""
    components = {
        **COMPONENTS,
        "apollo/light": _with(LIGHT_DOC, ["variants", "tile", "v1"], None),
    }
    result = _convert(_dashboard(_card()), 1, components)
    [card] = _cards(result["layout"])
    assert card["component"] == "apollo/light"
    level, bar = card["w"]
    assert (level["t"], level["size"]) == ("label", "s")
    assert isinstance(level["text"], dict)
    slot = next(s for s in result["bindings"]["slots"] if s["n"] == level["text"]["s"])
    assert "level" in slot["template"]
    assert bar["t"] == "slider"
    assert bar["change"] == {"policy": "optimistic"}
    _v1_keys_only(result["layout"])


def test_the_header_icon_falls_back_to_one_of_level_1() -> None:
    """The person's icon, the device's, the file's: the first of level 1 (C.6)."""
    assert "mdi:air-conditioner" not in LEVEL1
    assert "mdi:lightbulb" in LEVEL1
    # The file's icon is above level 1; the lamp's own icon is used.
    assert _forms("big")["header"]["icon"] == "mdi:lightbulb"
    # The person's icon of level 1 comes first.
    assert _forms("big", icon="mdi:fan")["header"]["icon"] == "mdi:fan"
    # One above level 1 is passed over.
    assert _forms("big", icon="mdi:air-conditioner")["header"]["icon"] == (
        "mdi:lightbulb"
    )


def test_no_icon_at_all_when_none_is_of_level_1() -> None:
    """Without icons.json nothing is known to be of level 1, so none is written."""
    component = COMPONENTS["test/forms"]
    card = validate_card_config2(
        component, {"params": {"entity": LAMP}, "variant": "big"}
    )
    form = compile_card2_v1(component, card, {LAMP: LAMP_FACTS})
    assert "icon" not in form["header"]
    assert all("icon" not in widget for widget in form["widgets"])
    level1 = compile_card2_v1(component, card, {LAMP: LAMP_FACTS}, level1=LEVEL1)
    assert level1["header"]["icon"] == "mdi:lightbulb"


# ---------------------------------------------------------------- C.6, rule 3


def test_a_variant_that_keeps_nothing_is_the_note() -> None:
    """A variant with a choice only becomes the note."""
    card = _forms("chooser")
    assert card["component"] == "test/forms"
    assert [widget["text"] for widget in card["w"]] == [UPDATE_NOTE]
    assert card["header"]["title"] == "Forms"


def test_a_variant_that_says_note_is_the_note() -> None:
    """`v1: note` gives the note, although its switch would work."""
    card = _forms("told")
    assert [(widget["t"], widget["text"]) for widget in card["w"]] == [
        ("label", UPDATE_NOTE)
    ]


def test_the_note_fits_a_card_one_row_high() -> None:
    """A card 56 px high has no room for a header: the line alone."""
    doc = copy.deepcopy(FORMS_DOC)
    doc["variants"] = {
        "chip": {
            "name": "Chip",
            "grid": [12, 1],
            "header": "chip",
            "layout": [{"type": "space"}],
        }
    }
    component = validate_component(doc)
    component["source"] = "builtin"
    result = _convert(
        _dashboard(_card("test/forms", grid_options={"columns": 12, "rows": 1})),
        1,
        {**COMPONENTS, "test/forms": component},
    )
    [card] = _cards(result["layout"])
    assert "header" not in card
    assert [widget["text"] for widget in card["w"]] == [UPDATE_NOTE]


# ---------------------------------------------------------------- detail pages


def test_the_same_card_twice_has_one_detail_page() -> None:
    """One detail page per different card (file, params, options, style)."""
    layout = _convert(_dashboard(_card(), _card()), 2)["layout"]
    assert [page["id"] for page in layout["pages"]] == ["home", "home~1"]
    holds = [card["hold"] for card in _cards(layout)[:2]]
    assert holds == [{"local": "go_to_page", "page": "home~1"}] * 2


def test_different_cards_have_their_own_detail_pages_in_dashboard_order() -> None:
    """Ids are <page id>~<n>, after all normal pages."""
    config = _dashboard(_card(), _card(options={"show_white": False}))
    config["views"].append(
        {
            "type": "sections",
            "path": "away",
            "title": "Away",
            "max_columns": 3,
            "sections": [
                {
                    "type": "grid",
                    "cards": [
                        _card(title="Away lamp", options={"show_saturation": True})
                    ],
                }
            ],
        }
    )
    layout = _convert(config, 2)["layout"]
    ids = [page["id"] for page in layout["pages"]]
    assert ids == ["home", "away", "home~1", "home~2", "away~1"]
    assert layout["pages"][4]["title"] == "Away lamp"


def test_past_the_detail_limit_the_openers_are_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At most MAX_DETAIL_PAGES; the next card loses its hold, with a warning."""
    monkeypatch.setattr(convert_module, "MAX_DETAIL_PAGES", 1)
    result = _convert(
        _dashboard(_card(), _card(title="Second", options={"show_white": False})), 2
    )
    layout = result["layout"]
    assert [page["id"] for page in layout["pages"]] == ["home", "home~1"]
    first, second = _cards(layout)[:2]
    assert "hold" in first
    assert "hold" not in second
    [warning] = [w for w in result["warnings"] if w["code"] == "too_many_details"]
    assert (warning["detail"], warning["card"], warning["page"]) == (
        "Second",
        1,
        "home",
    )


def test_a_more_button_goes_with_its_detail_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A widget whose only work is to open the detail page is left out with it."""
    doc = copy.deepcopy(LIGHT_DOC)
    doc["variants"]["wide"]["trailing"] = "more"
    component = validate_component(doc)
    component["source"] = "builtin"
    components = {**COMPONENTS, "apollo/light": component}
    card = _card(variant="wide", grid_options={"columns": 12})
    with_page = _cards(_convert(_dashboard(card), 2, components)["layout"])[0]
    more = [w for w in with_page["w"] if w.get("icon") == "mdi:dots-horizontal"]
    assert more[0]["tap"] == {"local": "go_to_page", "page": "home~1"}
    monkeypatch.setattr(convert_module, "MAX_DETAIL_PAGES", 0)
    without = _cards(_convert(_dashboard(card), 2, components)["layout"])[0]
    assert all(w.get("icon") != "mdi:dots-horizontal" for w in without["w"])
    assert len(without["w"]) == len(with_page["w"]) - 1
    assert "hold" not in without


def test_the_card_tap_is_kept_under_the_cards_id() -> None:
    """The card's own tap action is bound to the card's id (C.4)."""
    result = _convert(_dashboard(_card()), 2)
    card = _cards(result["layout"])[0]
    action = result["bindings"]["actions"][f"{card['id']}:tap"]
    assert (action["component"], action["output"]) == ("apollo/light", "toggle")
    assert action["entities"] == [LAMP]


def test_a_choice_keeps_its_whole_option_values_server_side() -> None:
    """The favourites choice keeps each colour as a value, not as an index."""
    card = _card(
        variant="large",
        grid_options={"columns": 12, "rows": 6},
        options={"colour_control": "dots"},
    )
    result = _convert(_dashboard(card), 2)
    layout_card = _cards(result["layout"])[0]
    [choice] = [w for w in layout_card["w"] if w["t"] == "choice"]
    action = result["bindings"]["actions"][f"{choice['id']}:change"]
    assert action["output"] == "set_favourite"
    assert action["options"][0] == {"rgb": [255, 69, 58], "kelvin": None}
    assert action["options"][-1] == {"rgb": None, "kelvin": 2700}


def test_colour_slots_keep_their_roles_in_the_layout() -> None:
    """A colour from a template keeps the role table the device layout needs."""
    result = _convert(_dashboard(_card("test/forms", variant="big")), 2)
    slots = {slot["n"]: slot for slot in result["bindings"]["slots"]}
    for card in _cards(result["layout"]):
        for widget in card["w"]:
            value = widget.get("c")
            if isinstance(value, dict):
                assert value["s"] in slots


# ---------------------------------------------------------------- views


def _two_views(second: dict) -> dict:
    """Return a dashboard with a normal view and a second one."""
    config = _dashboard(_card("apollo/light-tile"))
    config["views"].append(
        {
            "type": "sections",
            "path": "more",
            "title": "More",
            "max_columns": 3,
            "sections": [{"type": "grid", "cards": [_card("apollo/light-tile")]}],
            **second,
        }
    )
    return config


def test_a_subview_is_a_detail_page_in_layout_v2_only() -> None:
    """subview: true gives sub 1 and ttl 0 and no side bar entry (C.4)."""
    config = _two_views({"subview": True})
    v2 = _convert(config, 2)["layout"]
    page = v2["pages"][1]
    assert (page["id"], page["sub"], page["ttl"]) == ("more", 1, 0)
    assert [entry["page"] for entry in v2["nav"]] == ["home"]
    v1 = _convert(config, 1)["layout"]
    assert "sub" not in v1["pages"][1]
    assert [entry["page"] for entry in v1["nav"]] == ["home", "more"]


def test_a_subview_that_comes_first_stays_a_normal_page() -> None:
    """Page 0 is never a detail page."""
    config = _dashboard(_card("apollo/light-tile"), subview=True)
    layout = _convert(config, 2)["layout"]
    assert "sub" not in layout["pages"][0]
    assert [entry["page"] for entry in layout["nav"]] == ["home"]


def test_a_view_theme_is_a_page_theme_in_layout_v2_only() -> None:
    """apollo_tab: {theme: daylight} on a view gives its page a theme."""
    config = _two_views({"apollo_tab": {"theme": "daylight"}})
    v2 = _convert(config, 2)["layout"]
    assert "theme" not in v2["pages"][0]
    assert v2["pages"][1]["theme"] == {"id": "daylight", **THEMES["daylight"]}
    data = json.loads(
        device.compile_device_layout(v2, ICONS, device.ENGINE_CAPS_V2)["bytes"]
    )
    assert data["pages"][1]["theme"]["wall"] == device.colour(
        THEMES["daylight"]["wall"]
    )
    v1 = _convert(config, 1)["layout"]
    assert all("theme" not in page for page in v1["pages"])


def test_an_unknown_view_theme_is_ignored() -> None:
    """A theme that is not there gives no page theme."""
    layout = _convert(_two_views({"apollo_tab": {"theme": "nope"}}), 2)["layout"]
    assert all("theme" not in page for page in layout["pages"])


# ---------------------------------------------------------------- budgets


def test_a_page_has_at_most_six_sliders_with_a_track() -> None:
    """The seventh slider with a track loses it, with a warning (C.3)."""
    # Four rows: two bars of 48 (LOOK-NOTES decision 10) under the header.
    card = _card(variant="wide", grid_options={"columns": 12, "rows": 4})
    config = _dashboard(*([card] * 4))
    config["views"][0]["sections"].append({"type": "grid", "cards": [card] * 3})
    result = _convert(config, 2)
    page = result["layout"]["pages"][0]
    tracks = [
        widget
        for item in page["w"]
        if item["t"] == "card"
        for widget in item["w"]
        if "track" in widget
    ]
    assert len(tracks) == 6
    sliders = [w for w in _cards(result["layout"])[6]["w"] if w["t"] == "slider"]
    assert len(sliders) == 2
    assert all("track" not in w for w in sliders)
    assert _codes(result).count("over_budget_tracks") == 1
    # Version 1 has no tracks, so no such warning.
    assert "over_budget_tracks" not in _codes(_convert(config, 1))


# ---------------------------------------------------------------- over a limit


def _widget_count(layout: dict) -> int:
    """Return the widgets of a layout as the tablet counts them."""
    return device.compile_device_layout(layout, ICONS, device.ENGINE_CAPS_V2)["counts"][
        "widgets"
    ]


def _two_lamps() -> dict:
    """Return a dashboard with two cards that each have a detail page."""
    return _dashboard(_card(), _card(title="Second", options={"show_white": False}))


def test_detail_pages_are_left_out_from_the_end_until_it_fits() -> None:
    """A dashboard over the widget limit only by its detail pages still goes."""
    full = _convert(_two_lamps(), 2)["layout"]
    assert len(full["pages"]) == 3
    caps = {**device.ENGINE_CAPS_V2, "max_widgets": _widget_count(full) - 1}
    result = _convert(_two_lamps(), 2, caps=caps)
    layout = result["layout"]
    assert [page["id"] for page in layout["pages"]] == ["home", "home~1"]
    first, second = _cards(layout)[:2]
    assert "hold" in first
    assert "hold" not in second
    assert _codes(result).count("too_many_details") == 1
    device.compile_device_layout(layout, ICONS, caps)


def test_then_whole_cards_from_the_end_of_the_last_page() -> None:
    """When the detail pages are not enough, cards are left out from the end."""
    plain = _convert(_two_lamps(), 2)["layout"]
    normal = {**plain, "pages": plain["pages"][:1]}
    caps = {**device.ENGINE_CAPS_V2, "max_widgets": _widget_count(normal) - 1}
    result = _convert(_two_lamps(), 2, caps=caps)
    layout = result["layout"]
    assert [page["id"] for page in layout["pages"]] == ["home"]
    assert len(_cards(layout)) == 1
    codes = _codes(result)
    # Both detail pages go first, then the last card.
    assert codes.count("too_many_details") == 2
    assert codes.count("card_left_out") == 1
    [left] = [w for w in result["warnings"] if w["code"] == "card_left_out"]
    assert (left["card"], left["page"]) == (1, "home")
    device.compile_device_layout(layout, ICONS, caps)


def test_a_layout_above_max_stored_is_sent_with_not_kept() -> None:
    """Too big to be kept across a restart: a warning, and it is still made."""
    caps = {**device.ENGINE_CAPS_V2, "max_stored": 100}
    result = _convert(_dashboard(_card()), 2, caps=caps)
    assert "not_kept" in _codes(result)
    assert len(result["layout"]["pages"]) == 2
    assert "not_kept" not in _codes(_convert(_dashboard(_card()), 2))


def test_the_dl_1_path_keeps_todays_behaviour() -> None:
    """dl=1 is not fitted: no detail pages, no warnings of the rule."""
    caps = {**device.ENGINE_CAPS_V2, "max_widgets": 1, "max_stored": 1}
    result = _convert(_two_lamps(), 1, caps=caps)
    assert len(_cards(result["layout"])) == 2
    assert not {"too_many_details", "card_left_out", "not_kept"} & set(_codes(result))


def test_without_icons_nothing_is_fitted() -> None:
    """The editor's preview without icons.json gets the whole layout."""
    caps = {**device.ENGINE_CAPS_V2, "max_widgets": 1}
    result = convert_dashboard(
        _two_lamps(),
        components=COMPONENTS,
        themes=THEMES,
        approved=set(),
        facts={LAMP: LAMP_FACTS},
        dl=2,
        caps=caps,
    )
    assert len(result["layout"]["pages"]) == 3
    assert "card_left_out" not in _codes(result)


def test_engine_caps_v2_are_the_contracts() -> None:
    """What the converter fits to when it is not told equals engine_caps."""
    assert CONTRACT_JSON["engine_caps"] == device.ENGINE_CAPS_V2
