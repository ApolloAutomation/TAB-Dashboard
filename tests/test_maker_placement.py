"""Tests for cards placed at their own position on the 36 x 12 grid."""

import copy
import json
from pathlib import Path

import pytest

from custom_components.apollo_tab.maker.convert import convert_dashboard
from custom_components.apollo_tab.maker.geometry import (
    card_rect,
    cells_of,
    place_free,
    rect_cell,
)
from tests.harness.build_fixtures import _sample_dashboard
from tests.test_maker_convert import load_builtins, load_themes

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "placement_cases.json").read_text("utf-8")
)["cases"]


@pytest.fixture(scope="module")
def components():
    """Return the built-in Components keyed by id."""
    return load_builtins()


@pytest.fixture(scope="module")
def themes():
    """Return the bundled themes keyed by id."""
    return load_themes()


def convert(config, components, themes):
    """Convert a dashboard with the built-in library."""
    return convert_dashboard(
        config, components=components, themes=themes, approved=set()
    )


def card(entity, col=None, row=None, page=None, cols=6, rows=3):
    """Build a light tile, placed when col and row are given."""
    out = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/light-tile",
        "params": {"entity": entity},
        "grid_options": {"columns": cols, "rows": rows},
    }
    if col is not None:
        out["apollo_tab"] = {"col": col, "row": row}
        if page is not None:
            out["apollo_tab"]["page"] = page
    return out


def placed(cards, sections=None):
    """Build a one-view dashboard, the cards in one whole width section."""
    return {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [
            {
                "type": "sections",
                "max_columns": 3,
                "path": "home",
                "sections": sections
                or [{"type": "grid", "column_span": 3, "cards": cards}],
            }
        ],
    }


def rects_by_source(result):
    """(page id, rect) of the first drawing of each source, by entity or text."""
    out = {}
    for page in result["layout"]["pages"]:
        for widget in page["w"]:
            source = result["sources"].get(str(widget["id"]))
            if source is not None:
                out.setdefault(tuple(source), (page["id"], widget["r"]))
    return out


def codes(result):
    """Return the warning codes of a result."""
    return [w["code"] for w in result["warnings"]]


def assert_no_overlap(result):
    """No two cards of a page share a cell."""
    for page in result["layout"]["pages"]:
        taken = set()
        for widget in page["w"]:
            cells = cells_of(0, *rect_cell(widget["r"]))
            assert not cells & taken, page["id"]
            taken |= cells


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_place_free_shared_cases(case):
    """place_free gives the slot the shared cases name (the panel reads them too)."""
    taken = set()
    for page, col, row, cols, rows in case["taken"]:
        taken |= cells_of(page, col, row, cols, rows)
    assert list(place_free(taken, *case["size"])) == case["slot"]


@pytest.mark.parametrize(
    ("col", "row", "cols", "rows"),
    [(0, 0, 36, 12), (3, 2, 6, 3), (35, 11, 1, 1), (12, 5, 18, 2)],
)
def test_rect_cell_inverts_card_rect(col, row, cols, rows):
    """rect_cell reads back what card_rect drew."""
    assert rect_cell(card_rect(0, 0, col, row, cols, rows)) == (col, row, cols, rows)


def test_explicit_positions_give_exact_rects(components, themes):
    """A placed card sits exactly at its cells; screen order is reading order."""
    result = convert(
        placed([card("light.b", 12, 4), card("light.a", 3, 1, cols=12)]),
        components,
        themes,
    )
    page = result["layout"]["pages"][0]
    assert [w["r"] for w in page["w"]] == [
        card_rect(0, 0, 3, 1, 12, 3),
        card_rect(0, 0, 12, 4, 6, 3),
    ]
    assert codes(result) == []


def test_overlap_is_flowed_with_a_warning(components, themes):
    """The second of two overlapping cards goes to the first free slot."""
    result = convert(
        placed([card("light.a", 0, 0), card("light.b", 3, 1)]), components, themes
    )
    assert codes(result) == ["position_adjusted"]
    warning = result["warnings"][0]
    assert (warning["view"], warning["section"], warning["card"]) == (0, 0, 1)
    rects = rects_by_source(result)
    assert rects[(0, 0, 0)][1] == card_rect(0, 0, 0, 0, 6, 3)
    assert rects[(0, 0, 1)][1] == card_rect(0, 0, 6, 0, 6, 3)
    assert_no_overlap(result)


def test_out_of_bounds_is_clamped_with_a_warning(components, themes):
    """A position past the edge is moved in; negatives go to 0."""
    result = convert(
        placed([card("light.a", 40, 20), card("light.b", -3, -1)]), components, themes
    )
    assert codes(result) == ["position_adjusted", "position_adjusted"]
    rects = rects_by_source(result)
    assert rects[(0, 0, 0)][1] == card_rect(0, 0, 30, 9, 6, 3)
    assert rects[(0, 0, 1)][1] == card_rect(0, 0, 0, 0, 6, 3)


def test_malformed_position_is_flowed_with_a_warning(components, themes):
    """A position that is not whole numbers counts as no position."""
    bad = card("light.b")
    bad["apollo_tab"] = {"col": "3", "row": True}
    result = convert(placed([card("light.a", 0, 0), bad]), components, themes)
    assert codes(result) == ["position_adjusted"]
    assert rects_by_source(result)[(0, 0, 1)][1] == card_rect(0, 0, 6, 0, 6, 3)


def test_only_malformed_positions_keep_the_flow(components, themes):
    """A view with no valid position flows as before, the key ignored."""
    bad = card("light.a")
    bad["apollo_tab"] = "here"
    flow = placed([card("light.a")])
    assert (
        convert(placed([bad]), components, themes)["layout"]
        == convert(flow, components, themes)["layout"]
    )


def test_mixed_placed_and_unplaced(components, themes):
    """Placed cards are taken first; unplaced ones fill from the top left."""
    result = convert(
        placed([card("light.a"), card("light.b", 0, 0), card("light.c")]),
        components,
        themes,
    )
    assert codes(result) == []
    rects = rects_by_source(result)
    assert rects[(0, 0, 1)][1] == card_rect(0, 0, 0, 0, 6, 3)
    assert rects[(0, 0, 0)][1] == card_rect(0, 0, 6, 0, 6, 3)
    assert rects[(0, 0, 2)][1] == card_rect(0, 0, 12, 0, 6, 3)


def test_second_screen_and_empty_screen_dropped(components, themes):
    """Page 1 is the second screen; an empty screen between is dropped."""
    result = convert(
        placed([card("light.a", 0, 0), card("light.b", 0, 0, page=3)]),
        components,
        themes,
    )
    pages = result["layout"]["pages"]
    assert [p["id"] for p in pages] == ["home", "home-2"]
    assert rects_by_source(result)[(0, 0, 1)] == ("home-2", card_rect(0, 0, 0, 0, 6, 3))


def test_full_screen_flows_to_the_next(components, themes):
    """An unplaced card that finds no room goes to a new screen."""
    result = convert(
        placed([card("light.a", 0, 0, cols=36, rows=12), card("light.b")]),
        components,
        themes,
    )
    assert rects_by_source(result)[(0, 0, 1)] == ("home-2", card_rect(0, 0, 0, 0, 6, 3))


def test_heading_card_with_a_position(components, themes):
    """A heading card takes its own width from grid_options.columns."""
    heading = {
        "type": "heading",
        "heading": "Lights",
        "grid_options": {"columns": 12},
        "apollo_tab": {"col": 6, "row": 0},
    }
    result = convert(placed([heading, card("light.a", 6, 1)]), components, themes)
    rects = rects_by_source(result)
    assert rects[(0, 0, 0)][1] == card_rect(0, 0, 6, 0, 12, 1)
    assert rects[(0, 0, 1)][1] == card_rect(0, 0, 6, 1, 6, 3)
    assert codes(result) == []


def test_all_grid_sections_on_one_grid(components, themes):
    """In a placed view section widths do not matter; titles flow unplaced."""
    sections = [
        {"type": "grid", "title": "Top", "cards": [card("light.a", 24, 6)]},
        {"type": "grid", "cards": [card("light.b", 30, 9)]},
    ]
    result = convert(placed([], sections), components, themes)
    rects = rects_by_source(result)
    assert rects[(0, 0, None)][1] == card_rect(0, 0, 0, 0, 36, 1)
    assert rects[(0, 0, 0)][1] == card_rect(0, 0, 24, 6, 6, 3)
    assert rects[(0, 1, 0)][1] == card_rect(0, 0, 30, 9, 6, 3)


def freeze(config, result, vi):
    """Stamp every drawn item of view vi with the place it is drawn at.

    The same steps as placement.js freezePage: section titles become heading
    cards, every grid section is merged into one whole width section.
    """
    config = copy.deepcopy(config)
    view = config["views"][vi]
    screens = [
        p
        for i, p in enumerate(result["layout"]["pages"])
        if p.get("view") == vi and not (i > 0 and p.get("sub") == 1)
    ]
    where = {}
    for ordinal, page in enumerate(screens):
        for widget in page["w"]:
            source = result["sources"].get(str(widget["id"]))
            if source is not None:
                where.setdefault(tuple(source), (ordinal, widget["r"]))
        for warning in result["warnings"]:
            if warning.get("page") == page["id"] and isinstance(warning.get("r"), list):
                key = (warning["view"], warning["section"], warning["card"])
                where.setdefault(key, (ordinal, warning["r"]))
    cards = []
    for si, section in enumerate(view["sections"]):
        if section.get("title"):
            heading = {"type": "heading", "heading": section["title"]}
            spot = where.get((vi, si, None))
            if spot:
                col, row, cols, _rows = rect_cell(spot[1])
                heading["grid_options"] = {"columns": cols}
                heading["apollo_tab"] = {"page": spot[0], "col": col, "row": row}
            cards.append(heading)
        for ci, raw in enumerate(section.get("cards", [])):
            out = copy.deepcopy(raw)
            spot = where.get((vi, si, ci))
            if spot:
                col, row, cols, rows = rect_cell(spot[1])
                grid = dict(out.get("grid_options") or {})
                grid["columns"] = cols
                if out.get("type") != "heading":
                    grid["rows"] = rows
                out["grid_options"] = grid
                out["apollo_tab"] = {"page": spot[0], "col": col, "row": row}
            cards.append(out)
    view["sections"] = [{"type": "grid", "column_span": 3, "cards": cards}]
    return config


def test_frozen_fixture_views_draw_the_same(components, themes):
    """A frozen copy of each view of the sample yields the same rectangles."""
    config = _sample_dashboard()
    before = convert(config, components, themes)
    for vi in range(len(config["views"])):
        frozen = freeze(config, before, vi)
        after = convert(frozen, components, themes)
        old = [
            (p["id"], sorted(w["r"] for w in p["w"]))
            for p in before["layout"]["pages"]
            if p.get("view") == vi and not p.get("sub")
        ]
        new = [
            (p["id"], sorted(w["r"] for w in p["w"]))
            for p in after["layout"]["pages"]
            if p.get("view") == vi and not p.get("sub")
        ]
        # A section title repeated over a split section is one heading card
        # after the freeze; every other rectangle stays where it was.
        for (old_id, old_rects), (new_id, new_rects) in zip(old, new, strict=True):
            assert old_id == new_id
            assert set(map(tuple, new_rects)) <= set(map(tuple, old_rects))
        assert "position_adjusted" not in codes(after)
        assert_no_overlap(after)
