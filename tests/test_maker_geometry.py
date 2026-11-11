"""Tests for the maker geometry helpers."""

from pathlib import Path

import yaml

from custom_components.apollo_tab.maker.geometry import (
    CONTENT_X,
    GAP,
    PAD,
    PAGE_ROWS,
    PAGE_TOP,
    ROW_H,
    SCREEN_H,
    SCREEN_W,
    SECTION_COLUMNS,
    SECTION_W,
    card_rect,
    card_size_px,
    layout_card,
    paginate,
    place_section,
)
from custom_components.apollo_tab.maker.schema import validate_component

COMPONENTS_DIR = (
    Path(__file__).parent.parent
    / "custom_components"
    / "apollo_tab"
    / "library"
    / "components"
)


def _load_builtins():
    """Load and validate every bundled component."""
    components = []
    for path in sorted(COMPONENTS_DIR.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        components.append(validate_component(doc))
    return components


def _expand_items(component):
    """Expand for_each items into one copy per preview entity."""
    items = []
    for index, item in enumerate(component["layout"]):
        copies = 1
        if item["for_each"] is not None:
            copies = len(component["preview"]["params"][item["for_each"]])
        for _ in range(copies):
            entry = {"type": item["type"]}
            if item["type"] == "label":
                entry["size"] = item["size"]
            if item.get("side"):
                entry["side"] = True
            if item["for_each"] is not None:
                entry["group"] = index
            items.append(entry)
    return items


def test_card_size_px():
    """Convert grid columns and rows to pixel card sizes."""
    assert card_size_px(12, 3) == (376, 184)
    assert card_size_px(6, 6) == (184, 376)
    assert card_size_px(6, 3) == (184, 184)


def test_all_builtins_fit_their_size():
    """Lay out every bundled component with no clipped widget."""
    for component in _load_builtins():
        width_units, height_units = component["size"]
        w_px, h_px = card_size_px(width_units * 6, height_units * 3)
        result = layout_card(_expand_items(component), w_px, h_px, component["header"])
        assert result["clipped"] == [], component["id"]
        for rect in result["rects"]:
            if rect is None:
                continue
            x, y, w, h = rect
            assert x >= 0 and y >= 0, component["id"]
            assert x + w <= w_px and y + h <= h_px, component["id"]
        header = result["header"]
        if header is not None:
            assert header[0] >= 0, component["id"]
            assert header[0] + header[2] <= w_px, component["id"]


def test_switch_moves_to_header_on_wide_card():
    """Move the first switch into the header on cards at least 300 px wide."""
    wide_w, card_h = card_size_px(12, 3)
    wide = layout_card([{"type": "switch"}], wide_w, card_h, True)
    plain = layout_card([{"type": "label", "size": "m"}], wide_w, card_h, True)
    assert wide["rects"][0] == [wide_w - 16 - 64, 14, 64, 36]
    assert wide["header"][2] == plain["header"][2] - 72
    narrow_w, _ = card_size_px(6, 3)
    narrow = layout_card([{"type": "switch"}], narrow_w, card_h, True)
    assert narrow["rects"][0] != [narrow_w - 16 - 64, 14, 64, 36]


def test_side_image_column():
    """Place the first side item as a square column on the left."""
    items = [{"type": "image", "side": True}, {"type": "label", "size": "m"}]
    w_px, h_px = card_size_px(12, 3)
    result = layout_card(items, w_px, h_px, False)
    image, label = result["rects"]
    assert result["clipped"] == []
    assert image[2] == image[3]
    assert label[0] >= image[0] + image[2]


def test_buttons_share_a_row():
    """Pack neighbouring buttons into one shared row."""
    items = [{"type": "button"} for _ in range(3)]
    w_px, h_px = card_size_px(12, 3)
    result = layout_card(items, w_px, h_px, False)
    rects = result["rects"]
    assert result["clipped"] == []
    assert len({rect[1] for rect in rects}) == 1
    lefts = sorted(rect[0] for rect in rects)
    assert lefts[0] < lefts[1] < lefts[2]


def test_rows_dropped_when_too_small():
    """Drop trailing rows until the rest fits a small card."""
    items = [{"type": "label", "size": "m"} for _ in range(12)]
    w_px, h_px = card_size_px(6, 3)
    result = layout_card(items, w_px, h_px, False)
    clipped = result["clipped"]
    assert clipped
    for index, rect in enumerate(result["rects"]):
        if index in clipped:
            assert rect is None
        else:
            assert rect is not None
            assert rect[1] + rect[3] <= h_px


def test_place_section_sparse_flow():
    """Flow cards down two half-width lanes inside a section."""
    cards = [(12, 1), (6, 3), (6, 3), (12, 3), (6, 6), (6, 3), (6, 3)]
    positions, height = place_section(cards, 1)
    assert positions == [(0, 0), (0, 1), (6, 1), (0, 4), (0, 7), (6, 7), (6, 10)]
    assert height == 13


def test_paginate_rows_of_three():
    """Pack sections into rows of three section columns across pages."""
    sections = [(1, 7), (1, 10), (1, 4), (1, 6), (2, 6), (3, 12), (1, 3)]
    assert paginate(sections) == [
        (0, 0, 0),
        (0, 1, 0),
        (0, 2, 0),
        (1, 0, 0),
        (1, 1, 0),
        (2, 0, 0),
        (3, 0, 0),
    ]


def test_card_rect():
    """Place a card rect inside its section column and band."""
    assert card_rect(2, 0, 6, 1, 6, 3) == [1060, 84, 184, 184]


def test_page_fits_screen():
    """Fit the three section columns and twelve rows exactly on screen."""
    right = CONTENT_X + SECTION_COLUMNS * SECTION_W + (SECTION_COLUMNS - 1) * GAP
    assert right + PAD == SCREEN_W
    assert PAGE_TOP + PAGE_ROWS * ROW_H + PAD == SCREEN_H
