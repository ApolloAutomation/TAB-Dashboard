"""Tests for maker.convert: dashboard to layout conversion."""

import json
from pathlib import Path

import pytest
import yaml

from custom_components.apollo_tab.maker.convert import (
    _span,
    alias_tag,
    convert_dashboard,
    layout_hash,
)
from custom_components.apollo_tab.maker.geometry import SCREEN_H, SCREEN_W
from custom_components.apollo_tab.maker.schema import validate_component

LIBRARY = (
    Path(__file__).resolve().parents[1] / "custom_components" / "apollo_tab" / "library"
)

SENSITIVE_RAW = {
    "id": "me/vault-lock",
    "name": "Vault lock",
    "description": "A lock that must be approved before use.",
    "icon": "mdi:lock",
    "version": "1.0.0",
    "size": "1x1",
    "params": {"entity": {"domain": "lock"}},
    "outputs": {
        "lock": {
            "action": "lock.lock",
            "data": {"entity_id": "{{ entity }}"},
            "feedback": "confirm",
        }
    },
    "layout": [{"type": "button", "icon": "mdi:lock", "on_tap": "lock"}],
}


def load_builtins():
    """Load every built-in Component as an id -> component mapping."""
    mapping = {}
    for path in sorted((LIBRARY / "components").glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for entry in raw if isinstance(raw, list) else [raw]:
            component = validate_component(entry)
            component["source"] = "builtin"
            mapping[component["id"]] = component
    return mapping


def load_themes():
    """Load the bundled themes as an id -> theme mapping."""
    entries = json.loads((LIBRARY / "themes.json").read_text(encoding="utf-8"))
    return {entry["id"]: entry for entry in entries}


@pytest.fixture(scope="module")
def components():
    """Return the built-in Components keyed by id."""
    return load_builtins()


@pytest.fixture(scope="module")
def themes():
    """Return the bundled themes keyed by id."""
    return load_themes()


@pytest.fixture
def sensitive():
    """Return a user Component whose lock output makes it sensitive."""
    component = validate_component(SENSITIVE_RAW)
    component["source"] = "user"
    return component


def make_dashboard(sections, **view_kwargs):
    """Build a one-view, max_columns 3 sections dashboard with the sections."""
    view = {"type": "sections", "max_columns": 3, "sections": sections}
    view.update(view_kwargs)
    return {"apollo_tab": {"version": 1, "theme": "midnight"}, "views": [view]}


def tab_card(component_id, **extra):
    """Build a card config for a Component with the given extras."""
    card = {"type": "custom:apollo-tab-card", "component": component_id}
    card.update(extra)
    return card


def convert(config, components, themes, approved=None):
    """Convert a dashboard with the given library and approvals."""
    return convert_dashboard(
        config,
        components=components,
        themes=themes,
        approved=set(approved or ()),
    )


def iter_rects(layout):
    """Yield every rectangle in a layout, including card internals."""
    for page in layout["pages"]:
        for widget in page["w"]:
            yield widget["r"]
            if widget["t"] == "card":
                if "header" in widget:
                    yield widget["header"]["r"]
                for inner in widget["w"]:
                    yield inner["r"]


def test_starter_dashboard_one_page(components, themes):
    """A simple dashboard converts to a single page without warnings."""
    config = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/light-tile",
                        params={"entity": "light.kitchen"},
                    ),
                    tab_card(
                        "apollo/sensor-value",
                        params={"entity": "sensor.outside_temperature"},
                    ),
                ]
            }
        ],
        path="home",
        title="Home",
        icon="mdi:home",
    )
    result = convert(config, components, themes)
    assert result["warnings"] == []
    layout = result["layout"]
    assert layout["v"] == 1
    assert layout["screen"] == [1280, 800]
    assert layout["theme"]["id"] == "midnight"
    assert len(layout["pages"]) == 1
    page = layout["pages"][0]
    assert page["id"] == "home"
    assert page["title"] == "Home"
    assert page["icon"] == "mdi:home"
    assert layout["nav"] == [{"page": "home", "title": "Home", "icon": "mdi:home"}]
    assert len(page["w"]) == 2
    assert layout["hash"]


def test_absolute_rects_and_ids(components, themes):
    """The layout example of spec 5.7 is reproduced exactly."""
    config = make_dashboard(
        [
            {
                "cards": [
                    {
                        "type": "heading",
                        "heading": "Lights",
                        "icon": "mdi:lightbulb",
                    },
                    tab_card(
                        "apollo/light-tile",
                        params={"entity": "light.kitchen"},
                    ),
                ]
            }
        ],
        path="home",
        title="Home",
        icon="mdi:home",
    )
    layout = convert(config, components, themes)["layout"]
    assert layout["pages"][0]["w"] == [
        {
            "id": 1,
            "t": "heading",
            "r": [100, 20, 376, 56],
            "text": "Lights",
            "icon": "mdi:lightbulb",
        },
        {
            "id": 2,
            "t": "card",
            "r": [100, 84, 184, 184],
            "component": "apollo/light-tile",
            "header": {
                "r": [116, 100, 152, 32],
                "icon": "mdi:lightbulb",
                "title": {"s": 1},
            },
            "on": {"s": 2},
            "w": [
                {
                    "id": 3,
                    "t": "switch",
                    "r": [116, 176, 152, 40],
                    "value": {"s": 2},
                    "tap": {"policy": "optimistic"},
                },
                {
                    "id": 4,
                    "t": "label",
                    "r": [116, 224, 152, 28],
                    "text": {"s": 3},
                    "size": "m",
                },
            ],
        },
    ]


def test_non_tab_card_left_out_with_warning(components, themes):
    """A plain Home Assistant card is left out with not_tab_element."""
    config = make_dashboard([{"cards": [{"type": "tile", "entity": "light.kitchen"}]}])
    result = convert(config, components, themes)
    assert result["layout"]["pages"] == []
    assert result["layout"]["nav"] == []
    assert result["warnings"] == [
        {
            "code": "not_tab_element",
            "view": 0,
            "section": 0,
            "card": 0,
            "page": None,
            "r": None,
            "detail": "tile",
        }
    ]


def test_unknown_component_warning(components, themes):
    """A card for an unknown Component is left out with unknown_component."""
    config = make_dashboard(
        [{"cards": [tab_card("apollo/no-such-thing", params={"entity": "light.k"})]}]
    )
    result = convert(config, components, themes)
    assert result["layout"]["pages"] == []
    [warning] = result["warnings"]
    assert warning["code"] == "unknown_component"
    assert warning["detail"] == "apollo/no-such-thing"
    assert warning["card"] == 0


def test_invalid_card_warning(components, themes):
    """A card whose config fails validation is left out with invalid_card."""
    config = make_dashboard(
        [{"cards": [tab_card("apollo/light-tile", params="not-a-mapping")]}]
    )
    result = convert(config, components, themes)
    assert result["layout"]["pages"] == []
    [warning] = result["warnings"]
    assert warning["code"] == "invalid_card"
    assert warning["detail"]


def test_unapproved_sensitive_left_out(components, themes, sensitive):
    """A sensitive user Component needs approval before it is converted."""
    all_components = {**components, sensitive["id"]: sensitive}
    config = make_dashboard(
        [{"cards": [tab_card(sensitive["id"], params={"entity": "lock.vault"})]}]
    )
    denied = convert(config, all_components, themes)
    assert denied["layout"]["pages"] == []
    [warning] = denied["warnings"]
    assert warning["code"] == "needs_approval"
    assert warning["detail"] == sensitive["id"]
    tag_card = {
        "type": f"custom:{alias_tag(sensitive['id'])}",
        "params": {"entity": "lock.vault"},
    }
    tagged = make_dashboard([{"cards": [tag_card]}])
    allowed = convert(tagged, all_components, themes, approved={sensitive["id"]})
    assert allowed["warnings"] == []
    assert len(allowed["layout"]["pages"]) == 1


def test_preview_view_skipped_silently(components, themes):
    """A view holding only preview cards is skipped without a warning."""
    config = {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [
            {
                "type": "masonry",
                "cards": [
                    {"type": "custom:apollo-tab-preview"},
                    {"type": "custom:apollo-tab-preview"},
                ],
            }
        ],
    }
    result = convert(config, components, themes)
    assert result["warnings"] == []
    assert result["layout"]["pages"] == []
    assert result["layout"]["nav"] == []


def test_non_sections_view_warning(components, themes):
    """A non-sections view with real cards warns view_not_sections."""
    config = {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [
            {"type": "masonry", "cards": [{"type": "tile"}]},
            {"cards": [{"type": "custom:apollo-tab-preview"}, {"type": "tile"}]},
        ],
    }
    result = convert(config, components, themes)
    assert [w["code"] for w in result["warnings"]] == [
        "view_not_sections",
        "view_not_sections",
    ]
    assert result["layout"]["pages"] == []


def test_strategy_dashboard(components, themes):
    """A strategy dashboard converts to zero pages with one warning."""
    config = {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "strategy": {"type": "custom:whatever"},
        "views": [{"type": "sections", "max_columns": 3, "sections": []}],
    }
    result = convert(config, components, themes)
    assert result["layout"]["pages"] == []
    assert result["layout"]["nav"] == []
    assert result["bindings"] == {"slots": [], "actions": {}}
    assert result["warnings"] == [
        {
            "code": "strategy_not_supported",
            "view": None,
            "section": None,
            "card": None,
            "page": None,
            "r": None,
            "detail": "",
        }
    ]


def test_column_span_and_full_width(components, themes):
    """A full-width card spans all twelve grid columns of its section."""
    config = make_dashboard(
        [
            {
                "column_span": 2,
                "cards": [
                    tab_card(
                        "apollo/light-slider",
                        params={"entity": "light.living_room"},
                        grid_options={"columns": "full"},
                    )
                ],
            }
        ]
    )
    result = convert(config, components, themes)
    assert result["warnings"] == []
    card = result["layout"]["pages"][0]["w"][0]
    assert card["r"][2] == 2 * 376 + 8


def test_card_too_wide_clamped(components, themes):
    """A card wider than its section is clamped with card_too_wide."""
    config = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/light-tile",
                        params={"entity": "light.kitchen"},
                        grid_options={"columns": 24},
                    )
                ]
            }
        ]
    )
    result = convert(config, components, themes)
    assert [w["code"] for w in result["warnings"]] == ["card_too_wide"]
    card = result["layout"]["pages"][0]["w"][0]
    assert card["r"][2] == 376


def test_section_wraps_to_next_band(components, themes):
    """Cards that do not fit side by side wrap to the next band."""
    config = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/light-slider",
                        params={"entity": f"light.room_{n}"},
                    )
                    for n in range(3)
                ]
            }
        ]
    )
    result = convert(config, components, themes)
    assert result["warnings"] == []
    widgets = result["layout"]["pages"][0]["w"]
    assert len(widgets) == 3
    assert len({w["r"][0] for w in widgets}) == 1
    ys = [w["r"][1] for w in widgets]
    assert ys == sorted(ys)
    assert len(set(ys)) == 3


def test_sections_overflow_to_next_page(components, themes):
    """Sections that do not fit on one page continue on the next page."""
    sections = [
        {
            "cards": [
                tab_card(
                    "apollo/light-slider",
                    params={"entity": f"light.room_{n}"},
                )
                for n in range(4)
            ]
        }
        for _ in range(4)
    ]
    config = make_dashboard(sections, path="home", title="Home")
    result = convert(config, components, themes)
    pages = result["layout"]["pages"]
    assert [p["id"] for p in pages] == ["home", "home-2"]
    assert pages[1]["title"] == "Home (2)"
    assert result["layout"]["nav"] == [{"page": "home", "title": "Home"}]


def test_tall_section_split_repeats_heading(components, themes):
    """A tall section is split and every later part repeats the heading."""
    config = make_dashboard(
        [
            {
                "title": "Lights",
                "cards": [
                    tab_card(
                        "apollo/light-slider",
                        params={"entity": f"light.room_{n}"},
                    )
                    for n in range(5)
                ],
            }
        ]
    )
    result = convert(config, components, themes)
    assert [w["code"] for w in result["warnings"]] == ["section_split"]
    widgets = [widget for page in result["layout"]["pages"] for widget in page["w"]]
    headings = [w for w in widgets if w["t"] == "heading"]
    assert len(headings) == 2
    assert {h["text"] for h in headings} == {"Lights"}


def test_page_ids_titles_and_nav(components, themes):
    """Page ids come from unique paths, falling back to view-<n>."""

    def section(n):
        """Build a one-card section."""
        return {
            "cards": [tab_card("apollo/light-tile", params={"entity": f"light.l{n}"})]
        }

    tall = [
        {
            "cards": [
                tab_card("apollo/light-slider", params={"entity": f"light.t{n}"})
                for n in range(4)
            ]
        }
        for _ in range(4)
    ]
    config = {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [
            {
                "type": "sections",
                "max_columns": 3,
                "path": "home",
                "title": "Home",
                "icon": "mdi:home",
                "sections": [section(0)],
            },
            {
                "type": "sections",
                "max_columns": 3,
                "path": "home",
                "sections": [section(1)],
            },
            {"type": "sections", "max_columns": 3, "sections": [section(2)]},
            {"type": "sections", "max_columns": 3, "sections": tall},
            {"type": "sections", "max_columns": 3, "sections": []},
        ],
    }
    result = convert(config, components, themes)
    pages = result["layout"]["pages"]
    assert [p["id"] for p in pages] == [
        "home",
        "view-1",
        "view-2",
        "view-3",
        "view-3-2",
    ]
    assert pages[0]["title"] == "Home"
    assert pages[1]["title"] == "view-1"
    assert pages[3]["title"] == "view-3"
    assert pages[4]["title"] == "view-3 (2)"
    assert [e["page"] for e in result["layout"]["nav"]] == [
        "home",
        "view-1",
        "view-2",
        "view-3",
    ]


def test_chart_cap_leaves_card_out(components, themes):
    """The fifth chart card on a page is left out with over_budget_charts."""
    config = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/sensor-graph",
                        params={"entity": f"sensor.graph_{n}"},
                    )
                ]
            }
            for n in range(5)
        ]
    )
    result = convert(config, components, themes)
    pages = result["layout"]["pages"]
    assert len(pages) == 1
    assert len(pages[0]["w"]) == 4
    [warning] = result["warnings"]
    assert warning["code"] == "over_budget_charts"
    assert warning["page"] == pages[0]["id"]
    assert warning["r"] is not None
    assert warning["section"] == 4
    assert warning["card"] == 0


def test_arc_cap_leaves_card_out(components, themes):
    """The fifth thermostat card on a page is left out with over_budget_arcs."""
    config = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/thermostat",
                        params={"entity": f"climate.room_{n}"},
                    )
                ]
            }
            for n in range(5)
        ]
    )
    result = convert(config, components, themes)
    pages = result["layout"]["pages"]
    assert len(pages) == 1
    assert len(pages[0]["w"]) == 4
    [warning] = result["warnings"]
    assert warning["code"] == "over_budget_arcs"
    assert warning["page"] == pages[0]["id"]
    assert warning["r"] is not None
    assert warning["section"] == 4


def test_horizontal_gradient_cap_flattens(components, themes):
    """The fifth horizontal gradient on a page is drawn flat."""
    style = {"gradient": {"to": "#22303C", "direction": "horizontal"}}
    config = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/light-tile",
                        params={"entity": f"light.l{n}"},
                        style=dict(style),
                    )
                    for n in range(5)
                ]
            }
        ]
    )
    result = convert(config, components, themes)
    page = result["layout"]["pages"][0]
    assert len(page["w"]) == 5
    assert page["w"][0]["style"]["gd"] == "h"
    assert "bg2" in page["w"][0]["style"]
    flattened = page["w"][4]["style"]
    assert "bg2" not in flattened
    assert "gd" not in flattened
    [warning] = result["warnings"]
    assert warning["code"] == "over_budget_gradients"
    assert warning["page"] == page["id"]
    assert warning["r"] == page["w"][4]["r"]


def test_page_cap(components, themes):
    """Pages past twenty and nav entries past eight are dropped once each."""
    views = [
        {
            "type": "sections",
            "max_columns": 3,
            "sections": [
                {
                    "cards": [
                        tab_card(
                            "apollo/light-tile",
                            params={"entity": f"light.l{n}"},
                        )
                    ]
                }
            ],
        }
        for n in range(21)
    ]
    config = {"apollo_tab": {"version": 1, "theme": "midnight"}, "views": views}
    result = convert(config, components, themes)
    assert len(result["layout"]["pages"]) == 20
    assert len(result["layout"]["nav"]) == 8
    codes = [w["code"] for w in result["warnings"]]
    assert codes.count("too_many_pages") == 1
    assert codes.count("too_many_nav") == 1


def test_slots_shared_across_cards_and_numbered_in_order(components, themes):
    """Identical slots are shared and numbered in order of first use."""
    config = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/light-tile",
                        params={"entity": "light.kitchen"},
                    ),
                    tab_card(
                        "apollo/light-tile",
                        params={"entity": "light.kitchen"},
                    ),
                ]
            }
        ]
    )
    result = convert(config, components, themes)
    slots = result["bindings"]["slots"]
    assert [slot["n"] for slot in slots] == [1, 2, 3]
    first, second = result["layout"]["pages"][0]["w"]
    assert first["header"]["title"] == {"s": 1}
    assert second["header"]["title"] == {"s": 1}
    assert first["on"] == {"s": 2}
    assert second["on"] == {"s": 2}
    assert first["w"][0]["value"] == {"s": 2}
    assert first["w"][1]["text"] == {"s": 3}
    assert second["w"][0]["value"] == {"s": 2}
    assert second["w"][1]["text"] == {"s": 3}


def test_bindings_actions_keyed_by_widget_id(components, themes):
    """Binding actions are keyed by <widget id>:<tap|change>."""
    config = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/light-tile",
                        params={"entity": "light.kitchen"},
                    )
                ]
            }
        ]
    )
    result = convert(config, components, themes)
    assert result["bindings"]["actions"] == {
        "2:tap": {
            "component": "apollo/light-tile",
            "output": "toggle",
            "vars": {},
            "params": {"entity": "light.kitchen"},
        }
    }


def test_layout_has_no_entity_ids_or_templates(components, themes):
    """The layout JSON carries no entity ids and no templates."""
    config = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/light-tile",
                        params={"entity": "light.kitchen"},
                    ),
                    tab_card(
                        "apollo/thermostat",
                        params={"entity": "climate.living_room"},
                    ),
                ]
            }
        ]
    )
    text = json.dumps(convert(config, components, themes)["layout"])
    assert "light.kitchen" not in text
    assert "climate.living_room" not in text
    assert "{{" not in text


def test_hash_is_stable_and_changes_with_layout(components, themes):
    """The hash is stable for identical input and changes with the layout."""
    config = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/light-tile",
                        params={"entity": "light.kitchen"},
                    )
                ]
            }
        ]
    )
    first = convert(config, components, themes)["layout"]["hash"]
    second = convert(config, components, themes)["layout"]["hash"]
    assert first == second
    changed = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/light-tile",
                        params={"entity": "light.kitchen"},
                    ),
                    tab_card(
                        "apollo/sensor-value",
                        params={"entity": "sensor.temperature"},
                    ),
                ]
            }
        ]
    )
    assert convert(changed, components, themes)["layout"]["hash"] != first


def test_hash_ignores_hash_key(components, themes):
    """layout_hash ignores any existing hash key."""
    layout = convert(make_dashboard([{"cards": []}]), components, themes)["layout"]
    again = {**layout, "hash": "0" * 16}
    assert layout_hash(layout) == layout_hash(again)
    assert layout["hash"] == layout_hash(layout)


def test_every_rect_inside_screen(components, themes):
    """Every rectangle of a busy layout fits inside the screen."""
    config = make_dashboard(
        [
            {
                "title": "Busy",
                "cards": [
                    tab_card(
                        "apollo/light-slider",
                        params={"entity": f"light.l{n}"},
                    )
                    for n in range(5)
                ],
            },
            {
                "cards": [
                    {"type": "heading", "heading": "Sensors"},
                    tab_card(
                        "apollo/sensor-graph",
                        params={"entity": "sensor.temperature"},
                    ),
                    tab_card(
                        "apollo/thermostat",
                        params={"entity": "climate.hallway"},
                    ),
                ],
            },
        ]
    )
    result = convert(config, components, themes)
    for x, y, w, h in iter_rects(result["layout"]):
        assert 0 <= x < SCREEN_W
        assert 0 <= y < SCREEN_H
        assert 0 < w <= SCREEN_W - x
        assert 0 < h <= SCREEN_H - y
    for warning in result["warnings"]:
        if warning["r"] is not None:
            x, y, w, h = warning["r"]
            assert x >= 0
            assert y >= 0
            assert x + w <= SCREEN_W
            assert y + h <= SCREEN_H


def test_style_only_when_overridden(components, themes):
    """The style key appears only on cards with a non-empty style."""
    config = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/light-tile",
                        params={"entity": "light.kitchen"},
                    ),
                    tab_card(
                        "apollo/light-slider",
                        params={"entity": "light.living_room"},
                        style={"color": "#123456"},
                    ),
                ]
            }
        ]
    )
    page = convert(config, components, themes)["layout"]["pages"][0]
    plain, styled = page["w"]
    assert "style" not in plain
    assert styled["style"]["bg"] == "#123456"
    expected = (
        "tx",
        "tx2",
        "acc",
        "acc2",
        "acct",
        "card2",
        "line",
        "onbg",
        "ontx",
        "r",
        "r2",
        "bw",
    )
    for key in expected:
        assert key in styled["style"]


def test_invalid_options_fall_back(components, themes):
    """Bad apollo_tab options fall back to defaults with invalid_options."""
    config = make_dashboard(
        [
            {
                "cards": [
                    tab_card(
                        "apollo/light-tile",
                        params={"entity": "light.kitchen"},
                    )
                ]
            }
        ]
    )
    config["apollo_tab"] = {"version": 99, "theme": "midnight"}
    result = convert(config, components, themes)
    assert [w["code"] for w in result["warnings"]] == ["invalid_options"]
    assert result["layout"]["theme"]["id"] == "midnight"
    assert len(result["layout"]["pages"]) == 1


def test_convert_never_raises_on_garbage(components, themes):
    """Garbage anywhere in the config yields warnings, never exceptions."""
    config = {
        "apollo_tab": 42,
        "views": [
            "not-a-view",
            42,
            None,
            {"strategy": {"type": "custom:auto-entities"}},
            {"type": "sections", "max_columns": 3, "sections": "nope"},
            {
                "type": "sections",
                "max_columns": 3,
                "sections": [
                    "not-a-section",
                    {"strategy": {}},
                    {"type": "horizontal-stack", "cards": []},
                    {"column_span": "banana", "cards": "nope"},
                    {"sections": [{"cards": []}], "visibility": [{"cond": 1}]},
                    {
                        "cards": [
                            "string-card",
                            3.14,
                            {"type": 42},
                            {"type": "custom:some-other-card"},
                            {"type": "heading", "heading": 123, "visibility": [1]},
                            {"type": "custom:apollo-tab-preview"},
                            tab_card("apollo/light-tile"),
                        ]
                    },
                ],
            },
        ],
    }
    result = convert(config, components, themes)
    layout = result["layout"]
    codes = [w["code"] for w in result["warnings"]]
    assert "invalid_options" in codes
    assert "strategy_not_supported" in codes
    assert "section_not_grid" in codes
    assert "nested_section_ignored" in codes
    assert "visibility_ignored" in codes
    assert "not_tab_element" in codes
    assert "params_incomplete" in codes
    assert len(layout["pages"]) == 1
    texts = [w.get("text") for w in layout["pages"][0]["w"]]
    assert "123" in texts
    assert layout["hash"]


def test_infinite_column_span_is_one_column() -> None:
    """A column_span of infinity, which YAML can express, counts as one."""
    assert _span(float("inf")) == 1
    assert _span(float("-inf")) == 1
    assert _span(float("nan")) == 1
