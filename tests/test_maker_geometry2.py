"""Tests for the geometry of schema 2 cards (cards spec C.3)."""

import json
from pathlib import Path

import pytest

from custom_components.apollo_tab.maker import geometry
from custom_components.apollo_tab.maker.geometry import (
    LABEL_ROWS_2,
    card_size_px,
    layout_card2,
)

CONTRACT = json.loads(
    (
        Path(__file__).parent.parent
        / "custom_components"
        / "apollo_tab"
        / "contract"
        / "contract.json"
    ).read_text(encoding="utf-8")
)


def w(kind: str, **keys) -> dict:
    """Return the geometry input of one widget."""
    return {"type": kind, **keys}


def row(*cells: dict, height: int | None = None) -> dict:
    """Return a row of widgets side by side."""
    return {"kind": "row", "cells": list(cells), "height": height}


def swap(*members: list, height: int | None = None) -> dict:
    """Return a swap: members that share one place."""
    return {"kind": "swap", "cells": list(members), "height": height}


def space(height: int | None = None) -> dict:
    """Return a space."""
    return {"kind": "space", "cells": [], "height": height}


def rect(laid: dict, index: int, cell: int = 0, member: int = 0) -> list | None:
    """Return the rect of one widget of a laid-out body."""
    return laid["rects"][index][member][cell]


# ---------------------------------------------------------------- rows


def test_row_heights_per_kind() -> None:
    """Each kind asks for the row height C.3 names."""
    expected = [
        (w("label", size="s"), 22),
        (w("label", size="m"), 28),
        (w("label", size="ml"), 36),
        (w("label", size="l"), 44),
        (w("label", size="xl"), 60),
        (w("label", size="xxl"), 120),
        (w("label", size="huge"), 240),
        (w("button", control=True), 48),
        (w("slider", look="knob", control=True), 40),
        (w("slider", look="bar", control=True), 40),
        (w("slider", look="bar"), 8),
        (w("slider"), 40),
        (w("switch", control=True), 40),
        (w("choice", rows=1, options=2, control=True), 48),
        (w("choice", rows=1, options=2, look="dots", control=True), 44),
        (w("choice", rows=2, options=4, control=True), 48 + 8 + 48),
        (w("chart"), 48),
        (w("thermostat"), 48),
        (w("image"), 48),
    ]
    for geo, height in expected:
        # A card tall enough that nothing grows into spare height: the
        # body is exactly the row.
        laid = layout_card2([row(geo)], 376, height + 32, align_top=True)
        assert rect(laid, 0)[3] == height, geo


def test_the_digit_label_rows_are_the_contract_row_px() -> None:
    """xl, xxl and huge rows are fonts.row_px of contract.json."""
    row_px = CONTRACT["fonts"]["row_px"]
    assert LABEL_ROWS_2["xl"] == row_px["48"]
    assert LABEL_ROWS_2["xxl"] == row_px["96"]
    assert LABEL_ROWS_2["huge"] == row_px["192"]


def test_a_height_overrides_and_a_digit_label_is_raised_to_its_line() -> None:
    """`height` wins, except that a digit label is never lower than its line."""
    laid = layout_card2(
        [
            row(w("button", control=True, height=60)),
            row(w("label", size="m", height=20)),
            row(w("label", size="xxl", height=50)),
            row(w("label", size="xl", height=80)),
        ],
        376,
        800,
        align_top=True,
    )
    assert [rect(laid, i)[3] for i in range(4)] == [60, 20, 120, 80]


def test_padding_and_gaps() -> None:
    """16 padding, 8 between rows, 2 between two label rows that follow each other."""
    laid = layout_card2(
        [
            row(w("label", size="m")),
            row(w("label", size="s")),
            row(w("button", control=True)),
            row(w("label", size="s")),
        ],
        376,
        600,
        align_top=True,
    )
    ys = [rect(laid, i)[1] for i in range(4)]
    assert ys == [16, 16 + 28 + 2, 16 + 28 + 2 + 22 + 8, 16 + 28 + 2 + 22 + 8 + 48 + 8]
    assert rect(laid, 0)[0] == 16 and rect(laid, 0)[2] == 376 - 32


def test_leftover_height_sits_above_the_first_row() -> None:
    """Without anything that grows, the rows sit at the bottom."""
    laid = layout_card2([row(w("button", control=True))], 376, 200)
    assert rect(laid, 0) == [16, 200 - 16 - 48, 344, 48]


def test_align_top_puts_the_leftover_below() -> None:
    """A variant with `align: top` starts at the padding."""
    laid = layout_card2([row(w("button", control=True))], 376, 200, align_top=True)
    assert rect(laid, 0)[1] == 16


def test_flexible_widgets_grow_and_share_spare_height() -> None:
    """Charts, thermostats and images take spare height, shared between them."""
    laid = layout_card2(
        [row(w("chart")), row(w("button", control=True)), row(w("image"))], 376, 400
    )
    chart, button, image = (rect(laid, i) for i in range(3))
    assert button[3] == 48
    assert chart[3] == image[3]
    spare = 400 - 32 - 48 - 16 - 2 * 48
    assert chart[3] == 48 + spare // 2


def test_grow_and_space_take_spare_height() -> None:
    """`grow: true` grows any widget; a space takes spare height too."""
    laid = layout_card2(
        [row(w("label", size="s", grow=True)), space(), row(w("button", control=True))],
        376,
        300,
    )
    label = rect(laid, 0)
    button = rect(laid, 2)
    assert label[3] > 22
    # The space took its share: the button sits at the bottom, not under the label.
    assert button[1] == 300 - 16 - 48
    assert button[1] > label[1] + label[3] + 8


def test_a_widget_with_a_height_does_not_grow() -> None:
    """A height fixes a flexible widget."""
    laid = layout_card2([row(w("chart", height=70))], 376, 400, align_top=True)
    assert rect(laid, 0)[3] == 70


def test_rows_that_do_not_fit_are_dropped_from_the_end() -> None:
    """Layout order is priority."""
    body = [row(w("button", control=True)) for _ in range(5)]
    laid = layout_card2(body, 376, 184)
    # 152 inside: two buttons (48 + 8 + 48 = 104) and a third makes 160.
    assert laid["clipped"] == [2, 3, 4]
    assert laid["rects"][2] is None
    assert rect(laid, 1) is not None


# ---------------------------------------------------------------- rows of widgets


def test_a_row_shares_width_by_weight_after_fixed_widths() -> None:
    """Widgets 8 apart; `width` is fixed, the rest share by `weight`."""
    laid = layout_card2(
        [
            row(
                w("button", control=True, width=100),
                w("button", control=True),
                w("button", control=True, weight=2),
            )
        ],
        376,
        200,
    )
    first, second, third = (rect(laid, 0, i) for i in range(3))
    assert first[0] == 16 and first[2] == 100
    assert second[0] == 16 + 100 + 8
    free = 344 - 100 - 16
    assert second[2] == free // 3
    assert third[0] == second[0] + second[2] + 8
    assert third[0] + third[2] == 376 - 16


def test_a_row_is_as_high_as_its_tallest_widget() -> None:
    """The row's height is its own, else its tallest widget's."""
    laid = layout_card2(
        [row(w("label", size="s"), w("button", control=True))],
        376,
        200,
        align_top=True,
    )
    assert rect(laid, 0, 0)[3] == rect(laid, 0, 1)[3] == 48
    laid = layout_card2(
        [row(w("label", size="s"), w("button", control=True), height=60)],
        376,
        200,
        align_top=True,
    )
    assert rect(laid, 0, 1)[3] == 60


def test_a_swap_puts_its_members_on_one_place() -> None:
    """Members of a swap share the rectangle; a row member is laid out in it."""
    laid = layout_card2(
        [
            swap(
                [w("button", control=True)],
                [w("button", control=True), w("label", size="s")],
            )
        ],
        376,
        200,
    )
    alone = rect(laid, 0, 0, member=0)
    left = rect(laid, 0, 0, member=1)
    right = rect(laid, 0, 1, member=1)
    assert alone[1] == left[1] == right[1]
    assert alone[0] == left[0] and alone[2] == 344
    assert right[0] + right[2] == 376 - 16


def test_a_side_widget_becomes_a_square_column() -> None:
    """One flexible widget marked side goes to the left, as in schema 1."""
    laid = layout_card2(
        [row(w("button", control=True)), row(w("thermostat", side=True))], 568, 300
    )
    side = rect(laid, 1)
    assert side[0] == 16 and side[2] == side[3]
    assert rect(laid, 0)[0] == 16 + side[2] + 12


# ---------------------------------------------------------------- touch


def test_a_control_narrower_than_44_is_dropped() -> None:
    """No control is narrower than 44 px; a label of that width stays."""
    cells = [w("button", control=True) for _ in range(8)]
    laid = layout_card2([row(*cells)], 184, 200)
    # 152 wide, 8 buttons: 13 px each.
    assert all(rect(laid, 0, i) is None for i in range(8))
    assert laid["dropped"] == 8
    labels = [w("label", size="s") for _ in range(8)]
    laid = layout_card2([row(*labels)], 184, 200)
    assert all(rect(laid, 0, i) is not None for i in range(8))
    assert laid["dropped"] == 0


def test_a_control_lower_than_44_is_dropped() -> None:
    """A button made lower than 44 px by its height cannot be hit."""
    laid = layout_card2([row(w("button", control=True, height=30))], 376, 200)
    assert rect(laid, 0) is None and laid["dropped"] == 1


def test_a_dropped_widget_keeps_its_place_in_the_row() -> None:
    """The widgets after a dropped one stay where they were."""
    laid = layout_card2(
        [row(w("label", size="s"), w("button", control=True, width=20), w("label"))],
        376,
        200,
    )
    assert rect(laid, 0, 1) is None
    first, third = rect(laid, 0, 0), rect(laid, 0, 2)
    assert third[0] == first[0] + first[2] + 8 + 20 + 8


def test_a_choice_gets_more_rows_until_cells_are_44_wide() -> None:
    """Cells narrower than 44 px give the choice another row, up to 4."""
    laid = layout_card2(
        [row(w("choice", rows=1, options=8, control=True))], 184, 400, align_top=True
    )
    # 152 wide: 8 cells of 12; 2 rows: 4 of 32; 3 rows: 3 of 45.
    assert laid["rows"][0][0][0] == 3
    assert rect(laid, 0)[3] == 3 * 48 + 2 * 8


def test_a_choice_never_gets_more_rows_than_options() -> None:
    """Rows no option fills are left out; a fixed height keeps each row's height."""
    laid = layout_card2(
        [row(w("choice", rows=2, options=1, control=True, height=120))],
        376,
        400,
        align_top=True,
    )
    assert laid["rows"][0][0][0] == 1
    assert rect(laid, 0)[3] == 56
    laid = layout_card2(
        [row(w("choice", rows=3, options=2, control=True))], 376, 400, align_top=True
    )
    assert laid["rows"][0][0][0] == 2
    assert rect(laid, 0)[3] == 48 + 8 + 48


def test_a_grown_choice_is_no_row_of_pillars() -> None:
    """L1 round 2: four choices that take a Large card's height are 2 by 2.

    One row gave four cells of 80 by 304. A cell may be at most twice as tall
    as it is wide; rows keep at least their own height.
    """
    choice = w("choice", rows=1, options=4, control=True, grow=True)
    laid = layout_card2([row(choice)], 376, 336, align_top=True)
    assert rect(laid, 0) == [16, 16, 344, 304]
    assert laid["rows"][0][0][0] == 2  # cells of 168 by 148
    # Not as tall: one row of 80 by 112 stays.
    laid = layout_card2([row(choice)], 376, 144, align_top=True)
    assert laid["rows"][0][0][0] == 1
    # Eight already in 2 rows of 80 by 148 stay so.
    laid = layout_card2([row({**choice, "options": 8})], 376, 336, align_top=True)
    assert laid["rows"][0][0][0] == 2
    # A choice that does not grow keeps its rows, whatever its height.
    laid = layout_card2(
        [row({**choice, "grow": False, "height": 304})], 376, 336, align_top=True
    )
    assert laid["rows"][0][0][0] == 1
    # Never a row lower than a choice's row: cells of 44 by 100 stay one row.
    laid = layout_card2([row(choice)], 232, 132, align_top=True)
    assert rect(laid, 0)[2:] == [200, 100]
    assert laid["rows"][0][0][0] == 1


def test_a_narrow_button_shows_its_text_alone() -> None:
    """L1 round 2: side by side, an 80 px button left its text 3 letters."""
    assert geometry.button_text_alone(80, 52)
    assert not geometry.button_text_alone(80, 64)  # stacked: the text has 68
    assert not geometry.button_text_alone(90, 52)  # 48 for the text
    assert geometry.button_text_alone(89, 52)


def test_a_choice_that_4_rows_cannot_hold_is_dropped() -> None:
    """When 4 rows are not enough the item is left out."""
    laid = layout_card2([row(w("choice", rows=1, options=16, control=True))], 184, 400)
    assert rect(laid, 0) is None and laid["dropped"] == 1


# ---------------------------------------------------------------- headers


@pytest.mark.parametrize(
    ("form", "height"),
    [("title", 32), ("chip", 24), ("tile", 48), ("tile_v", 104), ("none", 0)],
)
def test_header_heights(form: str, height: int) -> None:
    """Each header form takes its height, then a gap of 8 before the rows."""
    laid = layout_card2([row(w("button", control=True))], 376, 400, form, None, True)
    gap = 8 if height else 0
    assert rect(laid, 0)[1] == 16 + height + gap


def test_tile_header_parts() -> None:
    """Badge 44, name over state, then the trailing switch at the right."""
    parts = layout_card2([], 376, 184, "tile", "switch")["header"]
    assert parts["badge"] == [16, 18, 44, 44]
    assert parts["name"][0] == parts["state"][0] == 16 + 44 + 8
    assert parts["name"][1] + parts["name"][3] == parts["state"][1]
    assert parts["state"][1] + parts["state"][3] == 16 + 48
    assert parts["trailing"][2:] == [64, 36]
    assert parts["trailing"][0] + 64 == 376 - 16
    assert parts["name"][0] + parts["name"][2] + 8 == parts["trailing"][0]


def test_a_narrow_tile_header_shows_the_name_not_the_switch() -> None:
    """L1 round 3: a switch never lies over the badge or cuts the name away.

    Under 48 px of name beside it the header shows no switch. Six columns
    (184 px) is too narrow; a card of 204 px is the first with the switch.
    """
    for width in (120, 184):
        parts = layout_card2([], width, 120, "tile", "switch")["header"]
        assert "trailing" not in parts
        assert parts["name"][0] == 16 + 44 + 8
        assert parts["name"][0] + parts["name"][2] == width - 16
    assert "trailing" not in layout_card2([], 203, 120, "tile", "switch")["header"]
    parts = layout_card2([], 204, 120, "tile", "switch")["header"]
    assert parts["trailing"][0] + 64 == 204 - 16
    assert parts["name"][2] == 48
    assert parts["badge"][0] + parts["badge"][2] <= parts["name"][0]
    assert parts["name"][0] + parts["name"][2] <= parts["trailing"][0]
    # Another trailing part is not a switch: it stays.
    assert "trailing" in layout_card2([], 184, 120, "tile", "more")["header"]


def test_tile_v_header_parts() -> None:
    """Badge at the top left, trailing at the top right, name and state under them."""
    parts = layout_card2([], 184, 184, "tile_v", "text")["header"]
    assert parts["badge"] == [16, 16, 44, 44]
    assert parts["name"] == [16, 16 + 44 + 8, 152, 28]
    assert parts["state"] == [16, 16 + 44 + 8 + 28 + 2, 152, 22]
    assert parts["trailing"][0] + parts["trailing"][2] == 184 - 16
    assert parts["trailing"][1] < 16 + 44


def test_chip_header_parts_fit_a_card_one_row_high() -> None:
    """A card one grid row high (56 px) has room for a chip."""
    width, height = card_size_px(12, 1)
    assert height == 56
    parts = layout_card2([], width, height, "chip")["header"]
    assert set(parts) == {"icon", "name", "state"}
    assert parts["icon"] == [16, 16, 24, 24]
    for part in parts.values():
        assert part[1] + part[3] <= height - 16


def test_more_is_a_44_px_square() -> None:
    """The trailing `more` button is big enough to hit."""
    parts = layout_card2([], 376, 184, "tile", "more")["header"]
    assert parts["trailing"][2:] == [44, 44]


def test_header_parts_that_do_not_fit_are_left_out() -> None:
    """A tile_v header in a card too low for it keeps only what fits."""
    parts = layout_card2([], 184, 120, "tile_v", None)["header"]
    assert "badge" in parts and "state" not in parts


def test_a_title_header_takes_a_switch_from_300_px() -> None:
    """As today: the first switch row moves into the header of a wide card."""
    laid = layout_card2(
        [row(w("switch", control=True)), row(w("button", control=True))],
        376,
        200,
        "title",
    )
    assert laid["header_switch"] == 0
    assert rect(laid, 0) == [376 - 16 - 64, 14, 64, 36]
    assert laid["header"]["title"][2] == 344 - 64 - 8
    narrow = layout_card2([row(w("switch", control=True))], 280, 200, "title")
    assert narrow["header_switch"] is None


def test_layout_card_of_schema_1_is_untouched() -> None:
    """The schema 1 function keeps its constants."""
    assert geometry.ROW_HEIGHTS == {
        "label_s": 22,
        "label_m": 28,
        "label_l": 44,
        "button": 48,
        "slider": 40,
        "switch": 40,
    }
    assert geometry.BUTTON_MAX_H == 96
