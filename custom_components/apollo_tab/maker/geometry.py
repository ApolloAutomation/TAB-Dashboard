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
