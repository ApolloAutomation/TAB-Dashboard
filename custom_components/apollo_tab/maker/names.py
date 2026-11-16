"""Cut a device's name to fit a width, in the middle, never at its end.

Pure Python, no imports from Home Assistant. Every function here has a twin
template (the `*_template` functions) that does the same on the live name,
so a name renamed in Home Assistant is cut the same way on the tablet.
"""

from __future__ import annotations

import math

ELLIPSIS = "…"
# A character of a name is about 10.5 px wide on average at 18 px.
NAME_CHAR_W_X2 = 21
NAME_PX = 18
# Widths of Montserrat Medium (the tablet's one text font) in tenths of a
# pixel, for the characters " " to "~", per text size a name is drawn at:
# 14 (label s), 15 (button), 16 (title header), 18 (label m, tile and chip
# names) and 34 (label l). Measured from fonts/Montserrat-Medium.ttf.
_W_ASCII = {
    14: (
        38, 38, 55, 98, 87, 118, 96, 29, 47, 47, 56, 81, 32, 54, 32, 49,
        93, 52, 80, 80, 94, 80, 86, 84, 90, 86, 32, 32, 81, 81, 81, 80,
        145, 102, 106, 101, 116, 94, 89, 108, 114, 43, 72, 101, 83, 134, 114, 118,
        101, 118, 102, 87, 82, 111, 100, 158, 94, 91, 92, 47, 49, 47, 82, 70,
        84, 84, 95, 80, 95, 86, 49, 97, 95, 39, 40, 86, 39, 148, 95, 89,
        95, 95, 57, 70, 58, 95, 78, 126, 77, 78, 73, 49, 42, 49, 81,
    ),
    15: (
        40, 40, 59, 105, 93, 126, 103, 32, 51, 51, 60, 87, 34, 58, 34, 53,
        100, 55, 86, 86, 100, 86, 92, 90, 97, 92, 34, 34, 87, 87, 87, 86,
        155, 110, 114, 108, 124, 100, 95, 116, 122, 47, 77, 108, 89, 143, 122, 126,
        108, 126, 109, 93, 88, 119, 107, 169, 101, 97, 99, 50, 53, 50, 88, 75,
        90, 90, 102, 86, 102, 92, 53, 103, 102, 42, 43, 92, 42, 159, 102, 95,
        102, 102, 62, 75, 62, 102, 84, 135, 83, 84, 78, 53, 45, 53, 87,
    ),
    16: (
        43, 43, 62, 112, 99, 135, 110, 34, 54, 54, 64, 93, 36, 61, 36, 56,
        107, 59, 92, 92, 107, 92, 99, 96, 103, 99, 36, 36, 93, 93, 93, 92,
        165, 117, 121, 116, 132, 107, 102, 124, 130, 50, 82, 115, 95, 153, 130, 134,
        115, 134, 116, 99, 94, 127, 114, 180, 108, 104, 105, 53, 56, 53, 93, 80,
        96, 96, 109, 91, 109, 98, 56, 110, 109, 45, 45, 99, 45, 169, 109, 102,
        109, 109, 66, 80, 66, 108, 89, 144, 88, 89, 83, 56, 48, 56, 93,
    ),
    18: (
        48, 48, 70, 127, 112, 152, 123, 38, 61, 61, 72, 105, 41, 69, 41, 63,
        120, 67, 103, 103, 120, 103, 111, 108, 116, 111, 41, 41, 105, 105, 105, 103,
        186, 132, 136, 130, 149, 121, 114, 139, 146, 56, 92, 129, 107, 172, 146, 151,
        130, 151, 131, 112, 106, 142, 128, 203, 121, 116, 118, 60, 63, 60, 105, 90,
        108, 108, 123, 103, 123, 110, 64, 124, 123, 50, 51, 111, 50, 190, 123, 114,
        123, 123, 74, 90, 75, 122, 101, 162, 99, 101, 94, 63, 54, 63, 105,
    ),
    34: (
        91, 91, 133, 239, 211, 287, 233, 71, 115, 115, 136, 198, 77, 130, 77, 120,
        227, 126, 195, 195, 228, 195, 210, 203, 219, 210, 77, 77, 198, 198, 198, 195,
        352, 249, 257, 246, 281, 228, 216, 262, 276, 105, 174, 245, 202, 325, 276, 286,
        245, 286, 247, 211, 200, 269, 242, 383, 229, 220, 223, 113, 120, 113, 198, 170,
        204, 203, 232, 194, 232, 208, 120, 235, 232, 95, 97, 209, 95, 359, 232, 216,
        232, 232, 139, 170, 141, 230, 190, 306, 188, 190, 177, 119, 102, 119, 198,
    ),
}  # fmt: skip
_W_ELLIPSIS = {14: 97, 15: 104, 16: 111, 18: 124, 34: 235}
# Per size: the width of each character, "…" included.
NAME_WIDTHS = {
    px: {chr(32 + i): w for i, w in enumerate(table)} | {ELLIPSIS: _W_ELLIPSIS[px]}
    for px, table in _W_ASCII.items()
}
NAME_W = NAME_WIDTHS[NAME_PX]
# Any other character counts as this wide: 14 px at 18 px.
NAME_W_OTHER = {px: (140 * px + NAME_PX // 2) // NAME_PX for px in _W_ASCII}
# Widths of a number's characters at 28 px (label ml), in tenths of a
# pixel, from the same font; and of the degree sign at every size above.
NUMBER_W = {
    28: dict(zip("0123456789.-° ", (187, 104, 161, 160, 187, 161, 173, 167, 180,
                                    173, 64, 107, 117, 75), strict=True)),
} | {
    px: NAME_WIDTHS[px] | {"°": (142 * px + 17) // 34} for px in _W_ASCII
}  # fmt: skip
# Most whole numbers measured for the widest of a range; past it the ends.
NUMBER_SPAN_MAX = 2000
# A name cut to fit keeps this much room spare, in tenths of a pixel.
NAME_W_SPARE = 20
# A name with room for fewer characters than this is narrow (a tile).
NARROW_CHARS = 12


def name_width(text: str, px: int = NAME_PX) -> int:
    """Return how wide a name is drawn at a text size, in tenths of a pixel."""
    widths, other = NAME_WIDTHS[px], NAME_W_OTHER[px]
    return sum(widths.get(char, other) for char in text)


def name_chars(width: int, px: int = NAME_PX) -> int:
    """Return how many characters of a name fit in a width, as a first guess."""
    return width * 2 * NAME_PX // (NAME_CHAR_W_X2 * px)


def cut_middle(name: str, chars: int) -> str:
    """Cut a long name in the middle, so its end stays.

    "Living Room Lamp 1" becomes "Living…Lamp 1", not "Living Room L…": names
    of lamps in one room often differ only at the end. The end kept is the
    last word, with the word before it when the last is shorter than 4.
    In a narrow header (under NARROW_CHARS) the end may take all but three
    characters: "Li…Lamp 1" on a tile still tells the owner's two lamps
    apart, "Living Ro…" does not; a wider header keeps three characters of
    the start ("Liv…Chandelier"). A name of one word, or an end longer
    than that, is cut in the middle by characters ("Superlo…spaces"): a
    name is never cut at its end (LOOK-NOTES L4). Under 3 characters there
    is nothing to cut. Spaces around the name do not count.
    """
    name = name.strip()
    if len(name) <= chars or chars < 3:
        return name
    words = name.split(" ")
    tail = words[-1]
    if len(words) > 2 and len(tail) < 4:
        tail = words[-2] + " " + tail
    head = name[: chars - 1 - len(tail)].rstrip()
    if len(words) > 1 and head and len(tail) <= _tail_room(chars):
        return head + ELLIPSIS + tail
    back = (chars - 1) // 2
    return name[: chars - 1 - back].rstrip() + ELLIPSIS + name[-back:].lstrip()


def _tail_room(chars: int) -> int:
    """Return how long the end of a name cut in the middle may be."""
    return chars - 4 if chars >= NARROW_CHARS else chars - 3


def room_beside(value: str, px: int, width: int, gap: int, most: int) -> int:
    """Return the room of a name that shares a line with a value, in tenths.

    width is the whole line the name and the value share, gap the gap
    between them, most the widest the value is drawn (its label's width)
    and px its text size. The name gets what the value leaves: "Living Room
    Temperature" stays whole beside "21.4 °C" where a fixed value column
    would cut it (LOOK-NOTES decision 14). An empty value leaves the line.
    """
    value = value.strip()
    taken = gap * 10 + min(name_width(value, px), most * 10) if value else 0
    return width * 10 - NAME_W_SPARE - taken


def cut_to_fit(
    name: str, chars: int, width: int, px: int = NAME_PX, room: int | None = None
) -> str:
    """Cut a name in the middle (cut_middle) so it fits a width in pixels.

    chars is a guess from the average width of a character; the search
    starts at twice it, so a name of narrow letters is not cut early
    ("Upstairs Guest…Left" where "Upstairs Guest Bed…Left" fits). A name
    that fits whole stays whole. A middle cut still too wide for its font
    is cut further; only a room under 3 characters leaves the name whole
    for the tablet to cut. So the name never shows two "…". room, in
    tenths of a pixel, replaces the width less NAME_W_SPARE (room_beside).
    """
    name = name.strip()
    if room is None:
        room = width * 10 - NAME_W_SPARE
    if name_width(name, px) <= room:
        return name
    for k in range(min(2 * chars, len(name) - 1), 0, -1):
        shown = cut_middle(name, k)
        if shown == name:
            return name
        if name_width(shown, px) <= room:
            return shown
    return name


def _decimals(step: float) -> int:
    """Return the decimals a value on a step's grid shows: 0, 1 or 2."""
    if step <= 0 or step >= 1 or float(step).is_integer():
        return 0
    return 1 if round(step * 10, 6).is_integer() else 2


def widest_number(low: float, high: float, step: float, unit: str, px: int) -> int:
    """Return how wide the widest value from low to high is drawn, in pixels.

    A value shows as Home Assistant gives it: a whole number without
    decimals ("21°"), else with the decimals of its step ("104.5°"), then
    the unit. Measured at a text size with a width table (28 for label
    ml), with NAME_W_SPARE to spare, so a label this wide never cuts it
    (LOOK-NOTES decision 16). 0 for a size without a table or no range.
    """
    widths = NUMBER_W.get(px)
    if widths is None or high < low:
        return 0
    other = NAME_W_OTHER.get(px, (140 * px + NAME_PX // 2) // NAME_PX)
    decimals = _decimals(step)
    tails = [""]
    if decimals == 1:
        tails += sorted(
            {"." + str(round(k * step * 10) % 10) for k in range(1, 11)} - {".0"}
        )
    elif decimals == 2:
        tails.append(".00")
    first, last = math.ceil(low), math.floor(high)
    wholes = (
        list(range(first, last + 1))
        if last - first <= NUMBER_SPAN_MAX
        else [first, last]
    )
    heads = [str(whole) for whole in wholes] or [str(math.floor(low))]
    if decimals and low < 0 and high > -1:
        heads.append("-0")  # -0.5
    widest = max(
        sum(widths.get(char, other) for char in head + tail + unit)
        for head in heads
        for tail in tails
    )
    return -(-(widest + NAME_W_SPARE) // 10)


def split_name(name: str, width: int, px: int = NAME_PX) -> tuple[str, str]:
    """Share a name over two lines of a width: whole words on the first.

    The first line takes as many words as fit; the rest goes on the second,
    cut in the middle when it is still too long ("Upstairs Guest" over
    "Bedroom…Lamp"). A name that fits one line leaves the second empty; a
    first word too long for a line is the whole name cut in the middle, on
    the first line.
    """
    name = name.strip()
    room = width * 10 - NAME_W_SPARE
    if name_width(name, px) <= room:
        return name, ""
    words = name.split(" ")
    take = 0
    while take < len(words) and name_width(" ".join(words[: take + 1]), px) <= room:
        take += 1
    if take == 0:
        return cut_to_fit(name, name_chars(width, px), width, px), ""
    rest = " ".join(words[take:])
    return " ".join(words[:take]), cut_to_fit(rest, name_chars(width, px), width, px)


# ---------------------------------------------------------------- templates


def _width_of(var: str, out: str, px: int, table: str = "name_w") -> str:
    """Return template source that sets namespace `out`.w to the width of var."""
    return (
        "{%- set " + out + " = namespace(w=0) -%}"
        "{%- for c in "
        + var
        + " -%}{%- set "
        + out
        + ".w = "
        + out
        + ".w + "
        + table
        + ".get(c, "
        + str(NAME_W_OTHER[px])
        + ") -%}{%- endfor -%}"
    )


def room_beside_template(value: str, px: int, width: int, gap: int, most: int) -> str:
    """Return room_beside as a template that sets `nroom` for the value `value`.

    value is an expression of the card file (an input's name, or the
    expression of a label's `{{ ... }}`). It needs the variable `value_w`:
    NAME_WIDTHS of px. A value with none counts as empty.
    """
    return (
        "{%- set nbv = '' if (" + value + ") is none else ((" + value + ")"
        " | string | trim) -%}" + _width_of("nbv", "nbw", px, "value_w") +
        "{%- set nroom = " + str(width * 10 - NAME_W_SPARE) + " - ((" + str(gap * 10)
        + " + [nbw.w, " + str(most * 10) + "] | min) if nbv else 0) -%}"
    )  # fmt: skip


def cut_to_fit_template(
    chars: int, width: int, px: int = NAME_PX, beside: bool = False
) -> str:
    """Return cut_to_fit as a template for the name `n`.

    It needs the variable `name_w`: NAME_WIDTHS of the same px. beside:
    the room is the variable `nroom` (room_beside_template), not the width.
    """
    room = "nroom" if beside else str(width * 10 - NAME_W_SPARE)
    return (
        "{%- set n = n | trim -%}"
        "{%- set w = n.split(' ') -%}"
        "{%- set t = (w[-2] ~ ' ' ~ w[-1]) if w | length > 2 and w[-1] | length < 4"
        " else w[-1] -%}" + _width_of("n", "m", px) + "{%- set ns = namespace(out=n, "
        "done=m.w <= " + room + ") -%}"
        "{%- for k in range(" + str(2 * chars) + ", 0, -1) -%}"
        "{%- if not ns.done and k < n | length -%}"
        "{%- set h = n[:k - 1 - t | length].rstrip() -%}"
        "{%- set b = (k - 1) // 2 -%}"
        "{%- if k < 3 -%}{%- set r = n -%}"
        "{%- elif w | length > 1 and h and t | length <= (k - 4"
        " if k >= " + str(NARROW_CHARS) + " else k - 3) -%}"
        "{%- set r = h ~ '…' ~ t -%}"
        "{%- else -%}"
        "{%- set r = n[:k - 1 - b].rstrip() ~ '…' ~ n[n | length - b:].lstrip() -%}"
        "{%- endif -%}"
        "{%- if r == n -%}{%- set ns.done = true -%}{%- else -%}"
        + _width_of("r", "m", px)
        + "{%- if m.w <= " + room + " -%}"
        "{%- set ns.out = r -%}{%- set ns.done = true -%}{%- endif -%}"
        "{%- endif -%}{%- endif -%}{%- endfor -%}{{- ns.out -}}"
    )  # fmt: skip


def split_name_template(line: int, width: int, px: int = NAME_PX) -> str:
    """Return line 1 or 2 of split_name as a template for the name `n`.

    It needs the variable `name_w`: NAME_WIDTHS of the same px.
    """
    room = width * 10 - NAME_W_SPARE
    space = str(NAME_W_OTHER[px])
    split = (
        "{%- set n = n | trim -%}"
        "{%- set sw = n.split(' ') -%}"
        "{%- set sp = namespace(k=0, w=0, stop=false) -%}"
        "{%- for x in sw -%}{%- if not sp.stop -%}"
        + _width_of("x", "sx", px)
        + "{%- set nw = sp.w + sx.w + (name_w.get(' ', " + space + ")"
        " if loop.index0 > 0 else 0) -%}"
        "{%- if nw <= " + str(room) + " -%}"
        "{%- set sp.w = nw -%}{%- set sp.k = loop.index -%}"
        "{%- else -%}{%- set sp.stop = true -%}{%- endif -%}"
        "{%- endif -%}{%- endfor -%}"
    )  # fmt: skip
    cut = cut_to_fit_template(name_chars(width, px), width, px)
    if line == 1:
        return (
            split + "{%- if sp.k == 0 -%}" + cut + "{%- elif sp.k < sw | length -%}"
            "{{- sw[:sp.k] | join(' ') -}}{%- else -%}{{- n -}}{%- endif -%}"
        )
    return (
        split + "{%- if 0 < sp.k < sw | length -%}"
        "{%- set n = sw[sp.k:] | join(' ') -%}" + cut + "{%- endif -%}"
    )
