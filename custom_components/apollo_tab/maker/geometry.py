"""Reference geometry for schema v1. Pure Python, no imports from Home Assistant."""

SCREEN_W, SCREEN_H = 1280, 800
NAV_W = 96  # nav rail on the left
CONTENT_X = 96  # left edge of section column 0
SECTION_W = 384  # pitch of one section column
SECTION_COLUMNS = 3
COL_W = 32  # 384 / 12 sub-grid columns
ROW_H = 64  # row unit
PAGE_TOP = 16
PAGE_ROWS = 12  # 16 + 12 * 64 + 16 = 800
CELL_INSET = 4  # each side, so neighbours sit 8 px apart
UNIT_COLUMNS = 6  # a Component size of 1 wide
UNIT_ROWS = 3  # a Component size of 1 high

PAD = 16
GAP = 8
HEADER_H = 32
ROW_HEIGHTS = {
    "label_s": 22,
    "label_m": 28,
    "label_l": 44,
    "button": 48,
    "slider": 40,
    "switch": 40,
}
BUTTON_MAX_H = 96
FLEX_MIN_H = 48
FLEX_TYPES = ("chart", "thermostat", "image")
MAX_PER_ROW = 4
WIDE_CARD_W = 300  # from this width a switch moves into the header


def card_size_px(columns: int, rows: int) -> tuple[int, int]:
    """Pixel size of a card that spans the given sub-grid columns and rows."""
    return columns * COL_W - 2 * CELL_INSET, rows * ROW_H - 2 * CELL_INSET


def _row_kind(item: dict) -> str:
    if item["type"] == "label":
        return "label_" + item.get("size", "m")
    return item["type"]


def layout_card(items: list[dict], w: int, h: int, header: bool) -> dict:
    """Place a card's widgets. Coordinates are relative to the card's top-left.

    items: the expanded layout list (for_each already applied). Each item has
    "type", optional "size" (labels), optional "side" and optional "group"
    (the index of the for_each item that produced it).
    Returns {"header": rect|None, "rects": [rect|None per item], "clipped": [indexes]}.
    A rect is [x, y, w, h]. None means the widget did not fit.
    """
    rects: list = [None] * len(items)
    x0, y0, x1, y1 = PAD, PAD, w - PAD, h - PAD
    body = list(range(len(items)))
    header_rect = None
    if header:
        header_rect = [x0, y0, x1 - x0, HEADER_H]
        if w >= WIDE_CARD_W:
            for i in body:
                if items[i]["type"] == "switch":
                    rects[i] = [x1 - 64, y0 - 2, 64, 36]
                    header_rect = [x0, y0, x1 - x0 - 64 - GAP, HEADER_H]
                    body.remove(i)
                    break
        y0 += HEADER_H + GAP

    # One flexible widget marked "side" becomes a square column on the left.
    for i in body:
        if items[i].get("side") and items[i]["type"] in FLEX_TYPES:
            side = min(y1 - y0, (x1 - x0) // 2)
            rects[i] = [x0, y0, side, side]
            x0 += side + 12
            body.remove(i)
            break

    # Group into rows: neighbouring buttons share a row, and so do neighbours
    # that came from the same for_each item list.
    rows: list[list[int]] = []
    for i in body:
        it = items[i]
        prev = items[rows[-1][-1]] if rows else None
        same = (
            prev is not None
            and len(rows[-1]) < MAX_PER_ROW
            and prev["type"] == it["type"]
            and (
                it["type"] == "button"
                or (
                    it.get("group") is not None and it.get("group") == prev.get("group")
                )
            )
        )
        if same:
            rows[-1].append(i)
        else:
            rows.append([i])

    kinds = [_row_kind(items[r[0]]) for r in rows]
    flex = [k in FLEX_TYPES for k in kinds]
    heights = [
        FLEX_MIN_H if f else ROW_HEIGHTS[k] for k, f in zip(kinds, flex, strict=True)
    ]

    # Drop rows from the end until the rest fits.
    clipped: list[int] = []
    avail = y1 - y0
    while rows and sum(heights) + GAP * (len(rows) - 1) > avail:
        clipped = rows.pop() + clipped
        kinds.pop(), flex.pop(), heights.pop()

    free = avail - sum(heights) - GAP * max(len(rows) - 1, 0)
    if rows and free > 0:
        growers = [n for n, f in enumerate(flex) if f]
        cap = None
        if not growers:
            growers = [n for n, k in enumerate(kinds) if k == "button"]
            cap = BUTTON_MAX_H
        if growers:
            share = free // len(growers)
            for n in growers:
                add = share if cap is None else min(share, cap - heights[n])
                heights[n] += add
                free -= add

    y = y0 + max(free, 0)  # leftover space sits above the first row
    for row, height in zip(rows, heights, strict=True):
        n = len(row)
        cell = (x1 - x0 - GAP * (n - 1)) // n
        for k, i in enumerate(row):
            rects[i] = [x0 + k * (cell + GAP), y, cell, height]
        y += height + GAP
    return {"header": header_rect, "rects": rects, "clipped": clipped}


def place_section(
    cards: list[tuple[int, int]], span: int
) -> tuple[list[tuple[int, int]], int]:
    """Place cards the way a CSS grid with sparse row flow does.

    cards: (columns, rows) per card, already clamped to 1..12*span and >= 1.
    Returns ([(column, row) per card], section height in rows).
    """
    width = 12 * span
    taken: set[tuple[int, int]] = set()
    out = []
    cur_r, cur_c = 0, 0
    height = 0
    for cols, rws in cards:
        r, c = cur_r, cur_c
        while True:
            if c + cols > width:
                r, c = r + 1, 0
                continue
            if any(
                (r + dr, c + dc) in taken for dr in range(rws) for dc in range(cols)
            ):
                c += 1
                continue
            break
        for dr in range(rws):
            for dc in range(cols):
                taken.add((r + dr, c + dc))
        out.append((c, r))
        cur_r, cur_c = r, c + cols
        height = max(height, r + rws)
    return out, height


def card_rect(
    section_col: int, band_row: int, col: int, row: int, cols: int, rows: int
) -> list[int]:
    """Absolute pixel rectangle of a card on its page."""
    w, h = card_size_px(cols, rows)
    return [
        CONTENT_X + section_col * SECTION_W + col * COL_W + CELL_INSET,
        PAGE_TOP + (band_row + row) * ROW_H + CELL_INSET,
        w,
        h,
    ]


def paginate(sections: list[tuple[int, int]]) -> list[tuple[int, int, int]]:
    """Pack whole sections into pages, in order, in rows of three columns.

    sections: (span, height in rows) per section, each height <= PAGE_ROWS.
    Returns (page index, section column, band top row) per section.
    """
    out = []
    page = band_y = col = band_h = 0
    for span, h in sections:
        if col + span > SECTION_COLUMNS:  # this row of sections is full
            band_y, col, band_h = band_y + band_h, 0, 0
        if band_y + h > PAGE_ROWS:  # does not fit under what is already there
            page, band_y, col, band_h = page + 1, 0, 0, 0
        out.append((page, col, band_y))
        col += span
        band_h = max(band_h, h)
    return out


# ---------------------------------------------------------------- schema 2
#
# layout_card2 places the rows of a schema 2 card (C.3 of the cards spec).
# layout_card above stays as it was for schema 1.

LABEL_GAP = 2  # between two label rows that follow each other
# Row heights of a label per size. The three digit sizes are fonts.row_px of
# contract.json: a row lower than the line would push the text down.
LABEL_ROWS_2 = {
    "s": 22,
    "m": 28,
    "ml": 36,
    "l": 44,
    "xl": 60,
    "xxl": 120,
    "huge": 240,
}
ROW_PX_SIZES = ("xl", "xxl", "huge")
BUTTON_H_2 = 48
SLIDER_H_2 = 40
LEVEL_H_2 = 8  # a bar that only shows
SWITCH_H_2 = 40
CHOICE_ROW_H = 48
CHOICE_DOTS_ROW_H = 44
CHOICE_GAP = 8  # between cells and between rows, as contract 4.7 draws them
CHOICE_MAX_ROWS = 4
CHOICE_TALL = 2  # a grown choice's cell is at most this many times as tall as wide
TOUCH_MIN = 44  # no control narrower or lower than this
# A button draws its icon and text side by side when lower than this (contract
# 4.7), with padding 6, icon 24 and gap 6: BUTTON_SIDE_W of its width is not
# for the text. Below BUTTON_TEXT_MIN of text it shows the text alone.
BUTTON_STACK_H = 64
BUTTON_SIDE_W = 6 + 24 + 6 + 6
BUTTON_TEXT_MIN = 48
ROW_ITEM_GAP = 8  # between the widgets of a row
SIDE_GAP = 12

# Header forms: their height, and the parts they draw.
HEADER_H_2 = {
    "title": 32,
    "chip": 24,
    "tile": 48,
    "tile_v": 44 + GAP + 28 + LABEL_GAP + 22,
    "none": 0,
}
# A tile_v header with no state line under the name ends under the name.
TILE_V_NO_STATE_H = 44 + GAP + 28
BADGE = 44
CHIP_ICON = 24
TRAILING_SWITCH = (64, 36)
# A tile header's switch needs this much left for the name beside it.
HEADER_NAME_MIN = 48
# A name narrower than this would be a letter and "…": the header leaves it out.
NAME_SHOWN_MIN = 32
TRAILING_MORE = 44
TRAILING_TEXT_W = 88
# A chip's state is a short value ("21.4 °C", "unavailable"): at most this
# wide, so a long name keeps the rest of the line. "unavailable" is 82 px
# wide at the state's size: 80 cut it to "unavailab…".
CHIP_STATE_MAX_W = TRAILING_TEXT_W


def _natural_height(geo: dict) -> int:
    """Return the height a widget asks for before spare height is shared."""
    kind = geo["type"]
    height = geo.get("height")
    if kind == "label":
        size = geo.get("size", "m")
        if height is not None:
            if size in ROW_PX_SIZES:
                return max(height, LABEL_ROWS_2[size])
            return height
        return LABEL_ROWS_2[size]
    if height is not None:
        return height
    if kind == "button":
        return BUTTON_H_2
    if kind == "switch":
        return SWITCH_H_2
    if kind == "slider":
        if geo.get("look") == "bar" and not geo.get("control"):
            return LEVEL_H_2
        return SLIDER_H_2
    if kind == "choice":
        cell = CHOICE_DOTS_ROW_H if geo.get("look") == "dots" else CHOICE_ROW_H
        rows = geo.get("rows", 1)
        return rows * cell + CHOICE_GAP * (rows - 1)
    if kind in FLEX_TYPES:
        return FLEX_MIN_H
    return 0


def _grows(geo: dict) -> bool:
    """Return whether a widget takes spare height."""
    if geo.get("height") is not None:
        return False
    return bool(geo.get("grow")) or geo["type"] in FLEX_TYPES


def _widths(cells: list[dict], width: int) -> list[int]:
    """Share a row's width: fixed widths first, the rest by weight, 8 apart."""
    n = len(cells)
    free = width - ROW_ITEM_GAP * (n - 1)
    free -= sum(cell["width"] for cell in cells if cell.get("width") is not None)
    weighted = [i for i, cell in enumerate(cells) if cell.get("width") is None]
    total = sum(cells[i].get("weight", 1) for i in weighted)
    out = [0] * n
    given = 0
    for k, i in enumerate(weighted):
        if k == len(weighted) - 1:
            out[i] = max(free - given, 0)
        else:
            out[i] = max(free * cells[i].get("weight", 1) // total, 0)
            given += out[i]
    for i, cell in enumerate(cells):
        if cell.get("width") is not None:
            out[i] = cell["width"]
    return out


def _choice_rows(geo: dict, width: int) -> int | None:
    """Return the rows a choice needs so no cell is narrower than 44, or None."""
    n = max(geo.get("options", 1), 1)
    rows = geo.get("rows", 1)
    while rows <= CHOICE_MAX_ROWS:
        k = -(-n // rows)
        if (width - CHOICE_GAP * (k - 1)) // k >= TOUCH_MIN:
            return rows
        rows += 1
    return None


def _fewer_rows(geo: dict) -> dict:
    """Give a choice no more rows than it has options.

    A row that no option fills would be a hole. A fixed height loses the
    share of the rows that go, so each row keeps its height.
    """
    n = max(geo.get("options", 1), 1)
    rows = geo["rows"]
    if rows <= n:
        return geo
    return _rows_to(geo, n)


def _rows_to(geo: dict, target: int) -> dict:
    """Give a choice `target` rows; a fixed height keeps each row's height."""
    rows = geo.get("rows", 1)
    out = {**geo, "rows": target}
    if geo.get("height") is not None:
        each = (geo["height"] - CHOICE_GAP * (rows - 1)) // rows
        out["height"] = target * each + CHOICE_GAP * (target - 1)
    return out


def _lone_cell(n: int, rows: int) -> bool:
    """Return whether n cells in this many rows leave one alone in the last."""
    k = -(-n // rows)
    return rows > 1 and k > 1 and n - k * (rows - 1) == 1


def _no_lone_cell(geo: dict, width: int) -> dict:
    """Take one row away when the last row would hold a single cell.

    Three presets in two rows leave one alone with a hole beside it; in one
    row they fill it. Only while every cell stays wide enough to touch.
    """
    n = max(geo.get("options", 1), 1)
    rows = geo["rows"]
    while _lone_cell(n, rows):
        k = -(-n // (rows - 1))
        if (width - CHOICE_GAP * (k - 1)) // k < TOUCH_MIN:
            break
        geo = _rows_to(geo, rows - 1)
        rows -= 1
    return geo


def _taller_rows(geo: dict, width: int, height: int) -> int:
    """Return the rows of a grown choice, so no cell is a tall pillar.

    While a cell would be more than CHOICE_TALL times as tall as it is wide,
    one cell fewer goes in each row, as long as every row keeps its
    height and the rows stay within CHOICE_MAX_ROWS. A count that would
    leave one cell alone in the last row is passed over: three cells go
    from one row to three, never to two and a hole.
    """
    n = max(geo.get("options", 1), 1)
    rows = geo.get("rows", 1)
    line = CHOICE_DOTS_ROW_H if geo.get("look") == "dots" else CHOICE_ROW_H
    while rows < n:
        k = -(-n // rows)
        cell_w = (width - CHOICE_GAP * (k - 1)) // k
        cell_h = (height - CHOICE_GAP * (rows - 1)) // rows
        if cell_h <= CHOICE_TALL * cell_w:
            break
        more = None
        for per_row in range(k - 1, 0, -1):
            count = -(-n // per_row)
            if (
                count > CHOICE_MAX_ROWS
                or (height - CHOICE_GAP * (count - 1)) // count < line
            ):
                break
            if not _lone_cell(n, count):
                more = count
                break
        if more is None:
            break
        rows = more
    return rows


def button_text_alone(width: int, height: int) -> bool:
    """Return whether a button with an icon and a text shows only the text.

    Side by side, an icon in a narrow button leaves its text a few letters.
    """
    return height < BUTTON_STACK_H and width - BUTTON_SIDE_W < BUTTON_TEXT_MIN


def _fit_cells(cells: list[dict], width: int) -> list[dict]:
    """Work out each widget's width; a control too narrow to touch is dropped.

    Returns per widget {"w": width, "geo": geo with the rows a choice needs},
    where geo is None for a widget that is dropped. Its width stays taken,
    so the widgets after it keep their places.
    """
    out: list[dict] = []
    for cell, cell_w in zip(cells, _widths(cells, width), strict=True):
        geo: dict | None = cell
        if cell["type"] == "choice":
            rows = _choice_rows(cell, cell_w)
            # More rows than asked keep each row's height: a fixed height
            # is for one row as it is for two.
            geo = (
                None
                if rows is None
                else _no_lone_cell(_fewer_rows(_rows_to(cell, rows)), cell_w)
            )
        elif cell.get("control") and cell_w < TOUCH_MIN:
            geo = None
        if (
            geo is not None
            and geo["type"] in ("button", "choice")
            and _natural_height(geo) < TOUCH_MIN
        ):
            geo = None
        out.append({"w": cell_w, "geo": geo})
    return out


def switch_fits_tile_header(width: int) -> bool:
    """Return whether a tile header this wide has room for a trailing switch."""
    name_w = width - BADGE - GAP - TRAILING_SWITCH[0] - GAP
    return name_w >= HEADER_NAME_MIN


def _header_parts(
    form: str,
    trailing: str | None,
    x0: int,
    y0: int,
    x1: int,
    state_line: bool = True,
) -> dict[str, list[int]]:
    """Place the parts of a header form; rects are relative to the card.

    state_line: False when the card shows no state line (tile_v only).
    """
    width = x1 - x0
    if form == "title":
        return {"title": [x0, y0, width, HEADER_H_2["title"]]}
    if form == "chip":
        rest = width - CHIP_ICON - GAP
        if rest < NAME_SHOWN_MIN:
            # Too narrow for a name: the icon alone, in the middle.
            return {"icon": [x0 + (width - CHIP_ICON) // 2, y0, CHIP_ICON, CHIP_ICON]}
        # The name gets two thirds, and all but CHIP_STATE_MAX_W on a wide
        # chip: it is the longer text.
        state_w = min(rest // 3, CHIP_STATE_MAX_W)
        if rest - state_w - GAP < HEADER_NAME_MIN:
            return {
                "icon": [x0, y0, CHIP_ICON, CHIP_ICON],
                "name": [x0 + CHIP_ICON + GAP, y0, rest, 24],
            }
        return {
            "icon": [x0, y0, CHIP_ICON, CHIP_ICON],
            "name": [x0 + CHIP_ICON + GAP, y0, rest - state_w - GAP, 24],
            "state": [x1 - state_w, y0 + 1, state_w, 22],
        }
    parts: dict[str, list[int]] = {}
    trail_w = 0
    if trailing == "switch":
        trail_w = TRAILING_SWITCH[0]
    elif trailing == "more":
        trail_w = TRAILING_MORE
    elif trailing == "text":
        trail_w = TRAILING_TEXT_W
    if form == "tile":
        parts["badge"] = [x0, y0 + 2, BADGE, BADGE]
        tx = x0 + BADGE + GAP
        if trailing == "switch" and not switch_fits_tile_header(width):
            # A narrow card: the switch would cut the name to a letter, or
            # lie over the badge. The name gets the room.
            trailing = None
            trail_w = 0
        tw = x1 - tx - (trail_w + GAP if trail_w else 0)
        if tw < NAME_SHOWN_MIN:
            # No room for a name that can be read: the badge alone, in the
            # middle.
            return {"badge": [x0 + (width - BADGE) // 2, y0 + 2, BADGE, BADGE]}
        parts["name"] = [tx, y0, tw, 26]
        parts["state"] = [tx, y0 + 26, tw, 22]
        mid = y0 + HEADER_H_2["tile"] // 2
    else:  # tile_v
        parts["badge"] = [x0, y0, BADGE, BADGE]
        parts["name"] = [x0, y0 + BADGE + GAP, width, 28]
        if state_line:
            parts["state"] = [x0, y0 + BADGE + GAP + 28 + LABEL_GAP, width, 22]
        mid = y0 + BADGE // 2
    if trailing == "switch":
        sw, sh = TRAILING_SWITCH
        parts["trailing"] = [x1 - sw, mid - sh // 2, sw, sh]
    elif trailing == "more":
        parts["trailing"] = [
            x1 - TRAILING_MORE,
            mid - TRAILING_MORE // 2,
            TRAILING_MORE,
            TRAILING_MORE,
        ]
    elif trailing == "text":
        text_w = x1 - (x0 + BADGE + GAP) if form == "tile_v" else TRAILING_TEXT_W
        parts["trailing"] = [x1 - text_w, mid - 11, text_w, 22]
    return parts


def _row_height(row: dict, fitted: list) -> int:
    """Return a row's height: its own, else its tallest widget."""
    if row.get("height") is not None:
        return row["height"]
    heights = [0]
    for member in fitted:
        for cell in member:
            if cell["geo"] is not None:
                heights.append(_natural_height(cell["geo"]))
    return max(heights)


def _row_grows(row: dict, fitted: list) -> bool:
    """Return whether a row takes spare height."""
    if row.get("height") is not None:
        return False
    if row["kind"] == "space":
        return True
    return any(
        _grows(cell["geo"])
        for member in fitted
        for cell in member
        if cell["geo"] is not None
    )


def _is_label_row(row: dict) -> bool:
    """Return whether a row holds labels only."""
    return row["kind"] == "row" and all(
        cell["type"] == "label" for cell in row["cells"]
    )


def layout_card2(
    body: list[dict],
    w: int,
    h: int,
    header: str = "none",
    trailing: str | None = None,
    align_top: bool = False,
    state_line: bool = True,
) -> dict:
    """Place a schema 2 card. Coordinates are relative to the card's top-left.

    body: rows in layout order, each {"kind": "row" | "swap" | "space",
    "cells": [...], "height": px or None}. A row's cells are widgets side by
    side; a swap's cells are members that share one place, each a list of
    widgets side by side. A widget is {"type", and as it has them "size",
    "look", "control" (it takes a touch), "height", "grow", "width",
    "weight", "rows" and "options" (a choice), "side"}.

    header is a form of C.3 and trailing what a tile header shows at its
    right: "switch", "more", "text" or None. state_line False: the card
    shows no state line, so a tile_v header ends under the name.

    Returns {"header": {part: rect}, "header_switch": row index or None,
    "rects": per row a list per member (a row has one member) of rect or
    None per widget, "rows": the same shape with the rows a choice got,
    "clipped": [row indexes left out], "dropped": widgets left out because
    a finger could not hit them}. A rect is [x, y, w, h].
    """
    x0, y0, x1, y1 = PAD, PAD, w - PAD, h - PAD
    rects: list = [None] * len(body)
    rows_out: list = [None] * len(body)
    order = list(range(len(body)))
    header_rect: dict[str, list[int]] = {}
    header_switch = None
    dropped = 0
    head_h = HEADER_H_2[header]
    if header == "tile_v" and not state_line:
        head_h = TILE_V_NO_STATE_H
    if header == "title" and w >= WIDE_CARD_W:
        for i in order:
            row = body[i]
            if (
                row["kind"] == "row"
                and len(row["cells"]) == 1
                and row["cells"][0]["type"] == "switch"
            ):
                sw, sh = TRAILING_SWITCH
                rects[i] = [[[x1 - sw, y0 - 2, sw, sh]]]
                rows_out[i] = [[None]]
                header_switch = i
                order.remove(i)
                break
    if head_h:
        header_rect = _header_parts(header, trailing, x0, y0, x1, state_line)
        if header == "title" and header_switch is not None:
            header_rect["title"][2] -= TRAILING_SWITCH[0] + GAP
        header_rect = {
            part: rect for part, rect in header_rect.items() if rect[1] + rect[3] <= y1
        }
        y0 += head_h + GAP

    # One flexible widget marked "side" becomes a square column on the left.
    for i in order:
        row = body[i]
        if (
            row["kind"] == "row"
            and len(row["cells"]) == 1
            and row["cells"][0].get("side")
            and row["cells"][0]["type"] in FLEX_TYPES
        ):
            side = max(min(y1 - y0, (x1 - x0) // 2), 0)
            rects[i] = [[[x0, y0, side, side]]]
            rows_out[i] = [[None]]
            x0 += side + SIDE_GAP
            order.remove(i)
            break

    fitted: dict[int, list] = {}
    for i in order:
        row = body[i]
        if row["kind"] == "space":
            fitted[i] = []
        elif row["kind"] == "swap":
            fitted[i] = [_fit_cells(member, x1 - x0) for member in row["cells"]]
        else:
            fitted[i] = [_fit_cells(row["cells"], x1 - x0)]
        dropped += sum(cell["geo"] is None for member in fitted[i] for cell in member)

    placed = list(order)
    heights = {i: _row_height(body[i], fitted[i]) for i in placed}

    def gap_before(k: int) -> int:
        """Return the gap above the k-th placed row."""
        if k == 0:
            return 0
        both = _is_label_row(body[placed[k - 1]]) and _is_label_row(body[placed[k]])
        return LABEL_GAP if both else GAP

    def used() -> int:
        """Return the height the placed rows take with their gaps."""
        return sum(heights[i] + gap_before(k) for k, i in enumerate(placed))

    clipped: list[int] = []
    avail = max(y1 - y0, 0)
    while placed and used() > avail:
        clipped.insert(0, placed.pop())
    free = avail - used()
    growers = [i for i in placed if _row_grows(body[i], fitted[i])]
    if growers and free > 0:
        share = free // len(growers)
        for i in growers:
            heights[i] += share
            free -= share
    y = y0 if align_top else y0 + max(free, 0)
    for k, i in enumerate(placed):
        y += gap_before(k)
        height = heights[i]
        row_rects = []
        row_rows = []
        for member in fitted[i]:
            member_rects = []
            member_rows = []
            x = x0
            if (
                len(member) == 1
                and member[0]["geo"] is not None
                and member[0]["geo"]["type"] == "thermostat"
                and member[0]["geo"].get("width") is not None
            ):
                # A thermostat narrower than its row sits in the middle:
                # its buttons come in to the foot of the arc.
                x += max(x1 - x0 - member[0]["w"], 0) // 2
            for cell in member:
                geo = cell["geo"]
                if geo is None:
                    member_rects.append(None)
                    member_rows.append(None)
                else:
                    member_rects.append([x, y, cell["w"], height])
                    if geo["type"] == "choice" and _grows(geo):
                        geo = {**geo, "rows": _taller_rows(geo, cell["w"], height)}
                    member_rows.append(
                        geo.get("rows") if geo["type"] == "choice" else None
                    )
                x += cell["w"] + ROW_ITEM_GAP
            row_rects.append(member_rects)
            row_rows.append(member_rows)
        rects[i] = row_rects
        rows_out[i] = row_rows
        y += height
    return {
        "header": header_rect,
        "header_switch": header_switch,
        "rects": rects,
        "rows": rows_out,
        "clipped": clipped,
        "dropped": dropped,
    }
