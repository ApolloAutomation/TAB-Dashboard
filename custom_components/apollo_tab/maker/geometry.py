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
# No slider on a card is lower than this: a finger needs 48 (LOOK-NOTES
# decision 10). A row of favourite dots is as high.
SLIDER_H_2 = 48
LEVEL_H_2 = 8  # a bar that only shows
SWITCH_H_2 = 40
CHOICE_ROW_H = 48
CHOICE_DOTS_ROW_H = 48
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
# A row of buttons closes its gaps to this when that keeps every button at
# least BUTTON_H_2 wide: up, stop and down on a six column blind (L4).
TIGHT_GAP = 4
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
# A tile header too narrow for the name beside the badge stacks: the badge
# and the state in one line, the name across the card under them. With no
# state line the badge still leads when the rows leave it the room; a row
# that needs the height (a dial, a chart) gets the name alone across the
# card.
TILE_STACKED_H = 44 + LABEL_GAP + 26
TILE_NAME_ONLY_H = 26
# A name on two lines: each line 24 high, as tall as the name and the state
# line beside a badge (48), so the Thermostat Tile's target and buttons keep
# their rows under "Living Room" over "Thermostat" (L4 round 3).
TILE_NAME_LINE2_H = 24
# An empty foot taller than this (decision 5's band) is shared: the
# header and the rows sit in the card's vertical middle (L4).
FOOT_CENTRE_MIN = 56
# Beside the badge a name narrower than this is cut to a few letters
# ("Li…Lamp 1"): 12 characters of the name's font.
TILE_NAME_NARROW_W = 126
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


def _widths(cells: list[dict], width: int, gap: int = ROW_ITEM_GAP) -> list[int]:
    """Share a row's width: fixed widths first, the rest by weight, gap apart."""
    n = len(cells)
    free = width - gap * (n - 1)
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


def _cell_w(n: int, rows: int, width: int) -> int:
    """Return how wide each cell of n choices in this many rows is."""
    k = -(-n // rows)
    return (width - CHOICE_GAP * (k - 1)) // k


def _choice_rows(geo: dict, width: int) -> int | None:
    """Return the rows a choice needs so no cell is narrower than 44, or None.

    A choice with `text_w` (the cell width its widest text needs) takes
    more rows, up to one per option, while that makes its texts whole:
    three fan presets in a six column card go in two rows, not one row of
    "a…o", "s…p" (L5).
    """
    n = max(geo.get("options", 1), 1)
    rows = geo.get("rows", 1)
    need = geo.get("text_w") or 0
    if need > TOUCH_MIN and _cell_w(n, rows, width) < need:
        for more in range(rows + 1, min(n, CHOICE_MAX_ROWS) + 1):
            if _cell_w(n, more, width) >= need:
                return more
    while rows <= CHOICE_MAX_ROWS:
        if _cell_w(n, rows, width) >= TOUCH_MIN:
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
    row they fill it. Only while every cell stays wide enough to touch,
    and to show its text whole where it does (`text_w`).
    """
    n = max(geo.get("options", 1), 1)
    rows = geo["rows"]
    need = max(TOUCH_MIN, geo.get("text_w") or 0)
    if _cell_w(n, rows, width) < need:
        need = TOUCH_MIN  # its texts are cut anyway
    while _lone_cell(n, rows):
        if _cell_w(n, rows - 1, width) < need:
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


def image_icon_px(width: int, height: int) -> int:
    """Return the size of a big icon in a widget (contract 4.7).

    It is the largest of 72, 48, 28 and 24 not over half its shorter side.
    """
    half = min(width, height) // 2
    return next((px for px in (72, 48, 28) if px <= half), 24)


def button_text_alone(width: int, height: int) -> bool:
    """Return whether a button with an icon and a text shows only the text.

    Side by side, an icon in a narrow button leaves its text a few letters.
    """
    return height < BUTTON_STACK_H and width - BUTTON_SIDE_W < BUTTON_TEXT_MIN


def _row_gap(cells: list[dict], width: int) -> int:
    """Return the gap between a row's widgets: TIGHT_GAP for a tight row of buttons.

    Three buttons in a six column card are 45 px wide 8 apart; 4 apart they
    are 48, as wide as a finger needs.
    """
    if len(cells) < 2 or any(cell["type"] != "button" for cell in cells):
        return ROW_ITEM_GAP
    if min(_widths(cells, width)) >= BUTTON_H_2:
        return ROW_ITEM_GAP
    if min(_widths(cells, width, TIGHT_GAP)) >= BUTTON_H_2:
        return TIGHT_GAP
    return ROW_ITEM_GAP


def _fit_cells(cells: list[dict], width: int) -> list[dict]:
    """Work out each widget's width; a control too narrow to touch is dropped.

    Returns per widget {"w": width, "gap": the gap after it, "geo": geo
    with the rows a choice needs}, where geo is None for a widget that is
    dropped. Its width stays taken, so the widgets after it keep their
    places.
    """
    out: list[dict] = []
    gap = _row_gap(cells, width)
    for cell, cell_w in zip(cells, _widths(cells, width, gap), strict=True):
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
        out.append({"w": cell_w, "gap": gap, "geo": geo})
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
    stacked: bool = False,
    bare: bool = False,
    lines: int = 1,
) -> dict[str, list[int]]:
    """Place the parts of a header form; rects are relative to the card.

    state_line: False when the card shows no state line. A tile_v header
    then ends under the name; a tile header puts its one line of name
    beside the middle of the badge.
    stacked: a tile header with the badge and the state in one line and
    the name across the card under them (TILE_STACKED_H high).
    bare: a stacked header with nothing trailing is the name alone across
    the card (TILE_NAME_ONLY_H), on `lines` lines, with the state line
    under it when the card has one.
    """
    width = x1 - x0
    if form == "title":
        if state_line and width - TRAILING_TEXT_W - GAP >= TILE_NAME_NARROW_W:
            # A variant's own state at the title's right (Dropdown Wide's
            # choice when it is not among those shown).
            return {
                "title": [x0, y0, width - TRAILING_TEXT_W - GAP, HEADER_H_2["title"]],
                "state": [
                    x1 - TRAILING_TEXT_W,
                    y0 + (HEADER_H_2["title"] - 22) // 2,
                    TRAILING_TEXT_W,
                    22,
                ],
            }
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
        tx = x0 + BADGE + GAP
        if trailing == "switch" and not switch_fits_tile_header(width):
            # A narrow card: the switch would cut the name to a letter, or
            # lie over the badge. The name gets the room.
            trailing = None
            trail_w = 0
        tw = x1 - tx - (trail_w + GAP if trail_w else 0)
        if stacked and bare and not trailing:
            # The rows need the badge's height, or the card shows no badge:
            # the name alone, across the card, and the state line under it.
            line_h = TILE_NAME_LINE2_H if lines == 2 else TILE_NAME_ONLY_H
            parts["name"] = [x0, y0, width, line_h]
            y = y0 + line_h
            if lines == 2:
                parts["name2"] = [x0, y, width, line_h]
                y += line_h
            if state_line:
                parts["state"] = [x0, y, width, 22]
            return parts
        if stacked:
            parts["badge"] = [x0, y0, BADGE, BADGE]
            if state_line and tw >= NAME_SHOWN_MIN:
                parts["state"] = [tx, y0 + (BADGE - 22) // 2, tw, 22]
            parts["name"] = [x0, y0 + BADGE + LABEL_GAP, width, 26]
            mid = y0 + BADGE // 2
        else:
            parts["badge"] = [x0, y0 + 2, BADGE, BADGE]
            if tw < NAME_SHOWN_MIN:
                # No room for a name that can be read: the badge alone, in
                # the middle.
                return {"badge": [x0 + (width - BADGE) // 2, y0 + 2, BADGE, BADGE]}
            if state_line:
                parts["name"] = [tx, y0, tw, 26]
                parts["state"] = [tx, y0 + 26, tw, 22]
            else:
                # One line: beside the middle of the badge, not at its top.
                parts["name"] = [tx, y0 + (HEADER_H_2["tile"] - 26) // 2, tw, 26]
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
    if row["kind"] == "space" or row.get("grow"):
        return True
    return any(
        _grows(cell["geo"])
        for member in fitted
        for cell in member
        if cell["geo"] is not None
    )


def _round_width(fitted: list, row_w: int) -> int | None:
    """Return the widest a row's round widgets are drawn, or None.

    A thermostat widens with its row, up to the row's width. A row of
    badges only draws each as the circle of min(w, h) of its rect, so it
    is no wider than its widest badge. Any other row returns None.
    """
    cells = [cell for member in fitted for cell in member if cell["geo"] is not None]
    if any(cell["geo"]["type"] == "thermostat" for cell in cells):
        return row_w
    if cells and all(
        cell["geo"]["type"] == "image" and cell["geo"].get("look") == "badge"
        for cell in cells
    ):
        return max(cell["w"] for cell in cells)
    return None


# A bar that fills upward or downward (a blind) is meant to be taller than
# wide: it is never capped by its width (LOOK-NOTES decision 15).
UPRIGHT = ("up", "down")


def _bar_width(fitted: list) -> int | None:
    """Return the width of a row's widest bar a finger moves, or None.

    A row with an upright bar returns None: it takes the free height.
    """
    bars = [
        cell
        for member in fitted
        for cell in member
        if cell["geo"] is not None
        and cell["geo"]["type"] == "slider"
        and cell["geo"].get("control")
    ]
    if any(cell["geo"].get("direction") in UPRIGHT for cell in bars):
        return None
    return max(cell["w"] for cell in bars) if bars else None


def _row_drop(row: dict) -> int | None:
    """Return a row's `drop` number: it goes first when the rows do not fit."""
    if row.get("drop") is not None:
        return row["drop"]
    marks = [
        cell.get("drop")
        for member in (row["cells"] if row["kind"] == "swap" else [row["cells"]])
        for cell in member
        if cell.get("drop") is not None
    ]
    return min(marks) if marks else None


def _has_flex_row(body: list[dict]) -> bool:
    """Return whether a row holds a dial, a chart or a picture that grows."""
    return any(
        cell["type"] in FLEX_TYPES and cell.get("height") is None
        for row in body
        if row["kind"] != "space" and row.get("height") is None
        for member in (row["cells"] if row["kind"] == "swap" else [row["cells"]])
        for cell in member
    )


def _row_most(row: dict, grown: bool = False) -> int | None:
    """Return the most height a growing row takes, or None for no limit.

    grown: the card is drawn larger than its grid, where a row with
    `most_grown` takes up to that instead (a lamp's main row, L4).
    """
    for key in ("most_grown", "most") if grown else ("most",):
        if row.get(key) is not None:
            return row[key]
        marks = [
            cell.get(key)
            for member in (row["cells"] if row["kind"] == "swap" else [row["cells"]])
            for cell in member
            if cell.get(key) is not None
        ]
        if marks:
            return min(marks)
    return None


def _is_label_row(row: dict) -> bool:
    """Return whether a row holds labels only."""
    return row["kind"] == "row" and all(
        cell["type"] == "label" for cell in row["cells"]
    )


def _centre(
    rects: list,
    placed: list[int],
    side_column: int | None,
    bottom: int,
    y1: int,
    how: tuple[bool, bool],
) -> int:
    """Share a foot taller than FOOT_CENTRE_MIN above the header and under the body.

    how is (centre, beside) of layout_card2. Rows lower than a picture
    column at their side first sit in the middle of its height; then the
    header, the picture and the rows move down together, so the card reads
    as one block with the theme's gap under its header and equal room
    above and under it: in a card drawn larger than its grid, and in any
    card with a picture column (L4 round 3). Row rects change in place;
    returns how far the header moves.
    """
    whole, beside_picture = how

    def move(indexes: list[int], shift: int) -> None:
        for i in indexes:
            for member in rects[i]:
                for rect in member:
                    if rect is not None:
                        rect[1] += shift

    if side_column is not None:
        side = rects[side_column][0][0]
        under = side[1] + side[3] - bottom
        if beside_picture and under > FOOT_CENTRE_MIN:
            move(placed, under // 2)
            bottom += under // 2
        bottom = max(bottom, side[1] + side[3])
        whole = whole or beside_picture
    foot = y1 - bottom
    if not whole or foot <= FOOT_CENTRE_MIN:
        return 0
    move([*placed, *([side_column] if side_column is not None else [])], foot // 2)
    return foot // 2


def layout_card2(
    body: list[dict],
    w: int,
    h: int,
    header: str = "none",
    trailing: str | None = None,
    align_top: bool = False,
    state_line: bool = True,
    stack_name: bool = False,
    centre: bool = False,
    beside: bool = False,
    badge: bool = True,
    title_state: bool = False,
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
    title_state: a title header shows a state at its right, where the
    title keeps TILE_NAME_NARROW_W (a variant's own `state`).

    stack_name: a tile header whose name beside the badge would be cut to a
    few letters stacks (_header_parts) when the rows keep their places: a
    six column tile reads "Living…Lamp 1", not "Li…Lamp 1". With no state
    line and nothing trailing the badge keeps its line while every row
    keeps its place and no dial, chart or picture has to shrink for it;
    else the name alone takes the line (LOOK-NOTES decision 14).

    Rows stack down from the header and the spare height goes to the rows
    that grow; with none, it stays empty under the last row (LOOK-NOTES
    decision 12). align_top is kept for callers: it changes nothing now.

    beside: rows lower than a picture column at their side sit in the
    middle of its height when that leaves more than FOOT_CENTRE_MIN under
    them, and a foot under the picture is shared as below. centre (a card
    drawn larger than its size's grid): a foot taller than FOOT_CENTRE_MIN
    is shared above and under the content, so the header, the picture and
    the rows sit in the card's vertical middle with no band between them
    (L4). A controls page leaves both out: its card ends under its rows.

    A row with `most` grows to that height at most (List and People rows
    stop at 56); what is left stays at the foot. In a card drawn larger
    than its grid a bar a finger moves, with no `most` or `most_grown` of
    its own, grows to its width at most: left alone it would be taller
    than wide. An upright bar (direction up or down, a blind) is not
    capped: it takes the free height. A row with its own `most` keeps it:
    its file says how far it goes (the owner's lamp).

    When the rows do not fit, a row whose widgets have `drop` goes first,
    the lowest number first; then rows go from the end.

    Returns {"header": {part: rect}, "header_switch": row index or None,
    "rects": per row a list per member (a row has one member) of rect or
    None per widget, "rows": the same shape with the rows a choice got,
    "clipped": [row indexes left out], "let_go": [rows with `drop` left
    out: meant, so no warning], "dropped": widgets left out because a
    finger could not hit them}. A rect is [x, y, w, h].
    """
    if header == "title":
        state_line = title_state
    args = (body, w, h, header, trailing, align_top, state_line, (centre, beside))
    laid = _layout_card2_named(args, stack_name, badge)
    if any(_text_w_cells(body)):
        # Rows a choice takes for whole texts must not cost a row or a
        # widget: else the choice keeps the rows a finger needs.
        plain = [_without_text_w(row) for row in body]
        flat = _layout_card2_named((plain, *args[1:]), stack_name, badge)
        if any(len(_listed(laid[k])) > len(_listed(flat[k])) for k in LOST):
            return flat
    return laid


LOST = ("clipped", "let_go", "dropped")


def _listed(value: object) -> list:
    """Return a lost count as a list: `dropped` is a number."""
    return value if isinstance(value, list) else [None] * int(value)


def _text_w_cells(body: list[dict]) -> list:
    """Return the `text_w` of every choice of a body that has one."""
    return [
        cell["text_w"]
        for row in body
        if row["kind"] != "space"
        for member in (row["cells"] if row["kind"] == "swap" else [row["cells"]])
        for cell in member
        if cell.get("text_w")
    ]


def _without_text_w(row: dict) -> dict:
    """Return a row whose choices ask for no width for their texts."""
    if row["kind"] == "space":
        return row

    def plain(cells: list) -> list:
        return [{k: v for k, v in cell.items() if k != "text_w"} for cell in cells]

    if row["kind"] == "swap":
        return {**row, "cells": [plain(member) for member in row["cells"]]}
    return {**row, "cells": plain(row["cells"])}


def _layout_card2_named(args: tuple, stack_name: bool, badge: bool) -> dict:
    """Lay out a card, its tile header's name stacked where that is better."""
    body, header, trailing, state_line = args[0], args[3], args[4], args[6]
    if stack_name and header == "tile":
        flat = _layout_card2(*args)
        name = flat["header"].get("name")
        if name is None or name[2] < TILE_NAME_NARROW_W:
            if not badge and not trailing:
                alone = _name_alone(args, flat)
                if alone is not None:
                    return alone
            lone = not state_line and not trailing
            for bare in (False, True) if lone else (False,):
                if lone and not bare and _has_flex_row(body):
                    continue
                stacked = _layout_card2(*args, stacked=True, bare=bare)
                if "name" in stacked["header"] and all(
                    stacked[key] == flat[key]
                    for key in ("clipped", "let_go", "dropped")
                ):
                    return stacked
        return flat
    return _layout_card2(*args)


def _same_rows(a: dict, b: dict) -> bool:
    """Return whether two layouts keep the same rows, at the same heights."""
    if any(a[key] != b[key] for key in ("clipped", "let_go", "dropped")):
        return False

    def heights(laid: dict) -> list:
        return [
            None if rect is None else rect[3]
            for row in laid["rects"]
            if row is not None
            for member in row
            for rect in member
        ]

    return heights(a) == heights(b)


def _name_alone(args: tuple, flat: dict) -> dict | None:
    """Lay out a tile header that shows no badge (a variant's `badge: false`).

    The name takes the card's width, on two lines when every row keeps its
    place and its height, else on one; the state line goes under it. A
    tile whose body is a reading (Status, Link) reads "Living Room" over
    "Temperature", not "Living…rature" under an empty badge line. None
    when even one line loses a row the flat header keeps.
    """
    one = _layout_card2(*args, stacked=True, bare=True)
    if "name" not in one["header"] or any(
        one[key] != flat[key] for key in ("clipped", "let_go", "dropped")
    ):
        return None
    two = _layout_card2(*args, stacked=True, bare=True, lines=2)
    if "name2" in two["header"] and _same_rows(one, two):
        return two
    return one


def _share(heights: dict, growers: list, caps: dict, free: int) -> int:
    """Share free height between growing rows; return what is left.

    A row with a cap stops there; the others share what it leaves.
    Heights change in place.
    """
    growers = list(growers)
    while growers and free > 0:
        share = free // len(growers)
        full = [
            i for i in growers if caps[i] is not None and heights[i] + share >= caps[i]
        ]
        if not full:
            for i in growers:
                heights[i] += share
                free -= share
            break
        for i in full:
            grown = max(heights[i], caps[i])
            free -= grown - heights[i]
            heights[i] = grown
            growers.remove(i)
    return free


def _layout_card2(
    body: list[dict],
    w: int,
    h: int,
    header: str,
    trailing: str | None,
    align_top: bool,
    state_line: bool,
    centre: tuple[bool, bool] = (False, False),
    stacked: bool = False,
    bare: bool = False,
    lines: int = 1,
) -> dict:
    """Place a schema 2 card (layout_card2), its tile header stacked or not."""
    del align_top  # rows stack from the header on every card
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
    if stacked:
        parts = _header_parts(
            header, trailing, x0, y0, x1, state_line, True, bare, lines
        )
        head_h = max(rect[1] + rect[3] for rect in parts.values()) - y0
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
        header_rect = _header_parts(
            header, trailing, x0, y0, x1, state_line, stacked, bare, lines
        )
        if header == "title" and header_switch is not None:
            header_rect["title"][2] -= TRAILING_SWITCH[0] + GAP
        header_rect = {
            part: rect for part, rect in header_rect.items() if rect[1] + rect[3] <= y1
        }
        y0 += head_h + GAP

    # One flexible widget marked "side" becomes a square column on the left.
    side_column = None
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
            side_column = i
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
    let_go: list[int] = []
    avail = max(y1 - y0, 0)
    for i in sorted(
        (i for i in placed if _row_drop(body[i]) is not None),
        key=lambda i: (_row_drop(body[i]), -i),
    ):
        if used() <= avail:
            break
        placed.remove(i)
        let_go.append(i)
    while placed and used() > avail:
        clipped.insert(0, placed.pop())
    free = avail - used()
    growers = [i for i in placed if _row_grows(body[i], fitted[i])]
    caps = {i: _row_most(body[i], centre[0]) for i in growers}
    for i in growers:
        round_w = _round_width(fitted[i], x1 - x0)
        if round_w is not None:
            # A dial and a badge are round: a row higher than they are wide
            # would only put empty height above and under them (LOOK-NOTES
            # decision 12). The rows under them follow straight on.
            caps[i] = min(round_w, caps[i] if caps[i] is not None else round_w)
        elif centre[0] and caps[i] is None:
            # A bar fills from left to right: grown taller than it is wide
            # it reads as an upright fader that moves sideways. Without a
            # `most` of its own it stops at its width (L4 round 4).
            caps[i] = _bar_width(fitted[i])
    free = _share(heights, growers, caps, free)
    y = y0
    for k, i in enumerate(placed):
        y += gap_before(k)
        height = heights[i]
        row_rects = []
        row_rows = []
        for member in fitted[i]:
            member_rects = []
            member_rows = []
            x = x0
            dial_w = None
            if (
                len(member) == 1
                and member[0]["geo"] is not None
                and member[0]["geo"]["type"] == "thermostat"
                and member[0]["geo"].get("width") is not None
            ):
                # A thermostat narrower than its row sits in the middle:
                # its buttons come in to the foot of the arc. A grown row
                # makes it wider, up to its height: the dial's diameter
                # follows the free height (LOOK-NOTES decision 12).
                dial_w = min(x1 - x0, max(member[0]["w"], height))
                x += max(x1 - x0 - dial_w, 0) // 2
            for cell in member:
                geo = cell["geo"]
                if geo is None:
                    member_rects.append(None)
                    member_rows.append(None)
                else:
                    cell_w = cell["w"] if dial_w is None else dial_w
                    member_rects.append([x, y, cell_w, height])
                    if geo["type"] == "choice" and _grows(geo):
                        geo = {**geo, "rows": _taller_rows(geo, cell["w"], height)}
                    member_rows.append(
                        geo.get("rows") if geo["type"] == "choice" else None
                    )
                x += cell["w"] + cell["gap"]
            row_rects.append(member_rects)
            row_rows.append(member_rows)
        rects[i] = row_rects
        rows_out[i] = row_rows
        y += height
    if placed and any(centre):
        shift = _centre(rects, placed, side_column, y, y1, centre)
        for rect in header_rect.values():
            rect[1] += shift
        if header_switch is not None:
            rects[header_switch][0][0][1] += shift
    return {
        "header": header_rect,
        "header_switch": header_switch,
        "rects": rects,
        "rows": rows_out,
        "clipped": clipped,
        "let_go": sorted(let_go),
        "dropped": dropped,
    }
