"""Compile a layout into the device layout a TAB-1 tablet draws.

This follows contract section 4 (``contract/CONTRACT.md``). The bytes this
module makes are compared with the contract's golden fixtures, so a change
here is a change to the contract. Pure Python, no Home Assistant imports.

``compile_device_layout`` picks the writer by the layout's ``v``: version 1
is today's path in ``device_v1.py``, left as it was; version 2 is written
here. This file also holds what both share: the error class, the defaults,
the wire encoding and the conversion of slot values.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

# The newest device layout version (contract.json dl_version). The version 1
# writer has its own constant.
DL_VERSION = 2

MAX_LAYOUT_BYTES = 262144
MAX_TEXT_BYTES = 255
MAX_LIST = 120
MAX_NUMBER = 1_000_000_000
# Version 1, and normal pages in version 2.
MAX_PAGES = 20
MAX_PAGES_V2 = 64
MAX_NAV = 8
MAX_SLOTS = 1024
MAX_WIDGETS = 2048
MAX_OPTIONS = 16
MAX_OPTION_TEXT_BYTES = 40
MAX_TRACK = 8
MAX_STORED_BYTES = 131072
CHUNK_BYTES = 16000

# What a tablet has when tab_hello leaves a caps key out. Key names are the
# ones of the tab_hello response.
CAPS_DEFAULTS: dict[str, Any] = {
    "icons": 1,
    "screen": [1280, 800],
    "max_layout": MAX_LAYOUT_BYTES,
    "max_chunk": CHUNK_BYTES,
    "max_slots": MAX_SLOTS,
    "max_widgets": MAX_WIDGETS,
    "max_pages": MAX_PAGES,
    "max_stored": MAX_STORED_BYTES,
}

WIDGET_KINDS = (
    "heading",
    "card",
    "label",
    "button",
    "switch",
    "slider",
    "thermostat",
    "chart",
    "image",
)
POLICIES = ("optimistic", "pulse", "progress", "confirm")
LABEL_SIZES = ("s", "m", "l")
CHART_KINDS = ("line", "bars")

THEME_COLOURS = (
    "wall",
    "card",
    "card_pr",
    "card2",
    "card2_pr",
    "line",
    "tx",
    "tx2",
    "acc",
    "accf",
    "accf_pr",
    "acct",
    "acc2",
    "onbg",
    "onbg_pr",
    "ontx",
    "ion",
)
STYLE_COLOURS = (
    "bg",
    "bg2",
    "tx",
    "tx2",
    "acc",
    "acc2",
    "acct",
    "card2",
    "line",
    "onbg",
    "ontx",
)
RADII = ("r", "r2", "bw")

# What version 2 adds (contract.json "v2"). The version 2 writer writes
# exactly these keys on top of the keys of version 1.
WIDGET_KINDS_V2 = ("choice",)
STYLE_COLOURS_V2 = ("card_pr", "card2_pr", "accf", "accf_pr", "onbg_pr", "ion")
CARD_KEYS_V2 = ("tap", "cf", "confirm", "hold", "ic", "tint", "lit", "un")
PAGE_KEYS_V2 = ("sub", "ttl", "theme")
WIDGET_KEYS_V2: dict[str, tuple[str, ...]] = {
    "heading": ("c",),
    "label": ("vis", "hold", "px", "al", "c", "clk", "value"),
    "button": ("vis", "hold", "value", "ic", "c", "shape", "isz"),
    "switch": ("vis", "hold", "c"),
    "slider": ("vis", "look", "dir", "track", "icon", "c", "nv", "rate"),
    "thermostat": ("vis", "c", "mark", "bs"),
    "chart": ("vis", "hold", "c", "mark", "st"),
    "image": ("vis", "hold", "look", "c"),
    "choice": ("vis", "texts", "icons", "cols", "value", "rows", "look"),
}
# Keys that only change the look: the tablet holds a value out of range to
# the nearest allowed one (contract 4.3).
LOOK_KEYS = (
    "px",
    "al",
    "shape",
    "isz",
    "look",
    "dir",
    "rows",
    "st",
    "bs",
    "lit",
    "ttl",
)
LIT = ("fill", "icon", "outline", "none")
ALIGN = ("left", "centre", "right")
SHAPES = ("box", "round", "bare")
SLIDER_LOOKS = ("knob", "bar")
DIRS = ("right", "up", "down")
IMAGE_LOOKS = ("box", "badge", "bare")
CHOICE_LOOKS = ("cells", "dots")

# How a number slot is converted when it holds a colour (slot plan "coerce").
COERCE_COLOUR = "colour"


class ContractError(Exception):
    """A value that the contract does not allow, with its error code."""

    def __init__(self, code: str, message: str = "") -> None:
        """Store the contract error code next to the message."""
        super().__init__(message or code)
        self.code = code


# ---------------------------------------------------------------- encoding


def num(value: float) -> int | float:
    """Return a number in wire form: clamped, at most 3 decimals, int if whole."""
    if isinstance(value, bool):
        return int(value)
    if not math.isfinite(value):
        raise ContractError("bad_number")
    value = max(-MAX_NUMBER, min(MAX_NUMBER, value))
    rounded = round(float(value), 3)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def canonical(obj: Any) -> bytes:
    """Return the canonical JSON bytes of a wire object."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def content_hash(data: bytes) -> str:
    """Return the 16 hex character hash of device layout bytes."""
    return hashlib.sha256(data).hexdigest()[:16]


def colour(text: str) -> int:
    """Return '#RRGGBB' as the integer 0xRRGGBB."""
    return int(text[1:7], 16)


def clip_text(text: str, limit: int = MAX_TEXT_BYTES) -> str:
    """Cut text to at most limit UTF-8 bytes without splitting a character."""
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    return raw[:limit].decode("utf-8", errors="ignore")


# ---------------------------------------------------------------- coercion


def is_on(value: Any) -> bool:
    """Mirror frontend/logic.js isOn."""
    if value is True:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return math.isfinite(value) and value != 0
    if isinstance(value, str):
        return value.lower() in ("on", "true", "yes", "1")
    return False


def to_number(value: Any) -> int | float | None:
    """Mirror frontend/logic.js toNumber, with None when there is no number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return num(value) if math.isfinite(value) else None
    if isinstance(value, str) and value.strip():
        try:
            number = float(value)
        except ValueError:
            return None
        return num(number) if math.isfinite(number) else None
    return None


def to_text(value: Any) -> str:
    """Return the text a label shows for a value."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(num(value)) if math.isfinite(value) else ""
    if isinstance(value, list | tuple):
        return clip_text(", ".join(to_text(item) for item in value))
    return clip_text(str(value))


def to_list(value: Any) -> list:
    """Return the finite numbers of a list value, at most MAX_LIST."""
    if not isinstance(value, list | tuple):
        return []
    out = []
    for item in value[:MAX_LIST]:
        number = to_number(item)
        if number is not None:
            out.append(number)
    return out


def to_icon(value: Any, icons: dict, level: int) -> int:
    """Return the glyph code point for an 'mdi:' name, or 0 for the placeholder."""
    if isinstance(value, str) and value in icons["icons"]:
        code, since = icons["icons"][value]
        if since <= level:
            return code
    return 0


_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def to_colour(value: Any, roles: dict[str, int] | None = None) -> int | None:
    """Return a colour as 0xRRGGBB, or None (contract 4.4, colour conversion).

    Taken: [r, g, b] with each part 0 to 255 after rounding halves up;
    "#RRGGBB" in either case; a whole number 0 to 16777215 (also written
    16711680.0); a role name of roles (name to 0xRRGGBB). Anything else,
    a bool or a fraction among it, is None.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        if roles and value in roles:
            return roles[value]
        if len(value) == 7 and value[0] == "#" and set(value[1:]) <= _HEX_DIGITS:
            return int(value[1:], 16)
        return None
    if isinstance(value, int | float):
        if not math.isfinite(value) or value != math.floor(value):
            return None
        whole = int(value)
        return whole if 0 <= whole <= 0xFFFFFF else None
    if isinstance(value, list | tuple) and len(value) == 3:
        out = 0
        for part in value:
            if isinstance(part, bool) or not isinstance(part, int | float):
                return None
            if not math.isfinite(part):
                return None
            channel = math.floor(part + 0.5)
            if not 0 <= channel <= 255:
                return None
            out = out << 8 | channel
        return out
    return None


def coerce(
    kind: str,
    value: Any,
    icons: dict,
    level: int,
    how: str | None = None,
    roles: dict[str, int] | None = None,
) -> Any:
    """Turn an evaluated slot value into the wire value of a typed slot.

    None means "no value": the tablet draws the widget as unavailable.
    how "colour" (a number slot that holds a colour) follows to_colour, with
    the role names of roles.
    """
    if value is None:
        return None
    if how == COERCE_COLOUR:
        return to_colour(value, roles)
    if kind == "b":
        return 1 if is_on(value) else 0
    if kind == "n":
        return to_number(value)
    if kind == "t":
        return to_text(value)
    if kind == "l":
        return to_list(value)
    if kind == "i":
        return to_icon(value, icons, level)
    raise ContractError("bad_slot_type", kind)


def icon_level(icons: dict, caps: dict | None) -> int:
    """Return the icon level HA uses for a tablet with these caps."""
    caps = {**CAPS_DEFAULTS, **(caps or {})}
    return min(int(caps["icons"]), int(icons["version"]))


def _icon(name: Any, icons: dict, level: int) -> int:
    """Return the code point of a fixed icon, or the fallback glyph."""
    code = to_icon(name, icons, level)
    if code:
        return code
    return icons["icons"][icons["fallback"]][0]


def _tap(tap: Any, page_index: dict[str, int]) -> dict | None:
    """Compile a tap or change dict."""
    if not isinstance(tap, dict):
        return None
    if tap.get("policy") in POLICIES:
        return {"p": POLICIES.index(tap["policy"])}
    if tap.get("local") == "go_to_page" and tap.get("page") in page_index:
        return {"go": page_index[tap["page"]]}
    return None


# ---------------------------------------------------------- either version


def compile_device_layout(
    layout: dict,
    icons: dict,
    caps: dict | None = None,
    confirm: dict[int, str] | None = None,
) -> dict:
    """Compile a layout into the device layout of the version it names.

    A layout without "v", or with "v": 1, goes through today's writer in
    device_v1.py; "v": 2 through the version 2 writer. Any other version
    raises ContractError("version"). Both return {"bytes", "hash", "size",
    "slots", "dropped", "counts"}; see compile_device_layout_v2.
    """
    version = layout.get("v", 1)
    if version == 2 and not isinstance(version, bool):
        return compile_device_layout_v2(layout, icons, caps, confirm)
    if version == 1 and not isinstance(version, bool):
        # Imported here: device_v1 imports its helpers from this module.
        from . import device_v1

        return device_v1.compile_device_layout(layout, icons, caps, confirm)
    raise ContractError("version", f"layout version {version!r}")


# ---------------------------------------------------- device layout (DL v2)
#
# Layout v2 is layout v1's shape with "v": 2 and the keys of contract 4.3
# under their device names and numbers. As in version 1, four things differ
# from the device layout: colours are "#RRGGBB" or {"s": n} (a colour slot
# may carry "roles": {name: "#RRGGBB"}), icons are "mdi:" names, slots are
# source slots, and tap, change and hold hold {"policy": name} or
# {"local": "go_to_page" | "back", "page": id}.


class _Slots:
    """Give each slot key one device slot number.

    The key is (source slot, type, coerce, roles). So one source used as a
    number and as a colour, or as a colour by two cards whose role colours
    differ, gets two device slots (contract 4.4).
    """

    def __init__(self) -> None:
        """Start with no slots."""
        self.plan: list[dict] = []
        self._index: dict[tuple, int] = {}

    def ref(
        self,
        source: int,
        kind: str,
        how: str | None = None,
        roles: dict[str, int] | None = None,
    ) -> dict:
        """Return the reference to the device slot of this slot key."""
        key = (source, kind, how, tuple(sorted(roles.items())) if roles else None)
        if key not in self._index:
            self._index[key] = len(self.plan) + 1
            entry: dict[str, Any] = {"d": self._index[key], "src": source, "type": kind}
            if how:
                entry["coerce"] = how
            if roles:
                entry["roles"] = dict(sorted(roles.items()))
            self.plan.append(entry)
        return {"s": self._index[key]}


def _bound(value: Any, kind: str, slots: _Slots, icons: dict, level: int) -> Any:
    """Compile one bound field: a slot reference or a coerced constant."""
    if isinstance(value, dict) and "s" in value:
        return slots.ref(value["s"], kind)
    return coerce(kind, value, icons, level)


def _colour_const(value: Any) -> int:
    """Compile a constant colour; one the contract does not take is an error."""
    out = to_colour(value)
    if out is None:
        raise ContractError("bad_colour", repr(value))
    return out


def _colour(value: Any, slots: _Slots) -> Any:
    """Compile a colour field: a colour slot reference or a constant."""
    if isinstance(value, dict) and "s" in value:
        roles = value.get("roles")
        names = {k: _colour_const(v) for k, v in roles.items()} if roles else None
        return slots.ref(value["s"], "n", COERCE_COLOUR, names)
    return _colour_const(value)


def _tap2(tap: Any, page_index: dict[str, int]) -> dict | None:
    """Compile a tap or change of version 2: version 1's forms and back."""
    if isinstance(tap, dict) and tap.get("local") == "back":
        return {"back": 1}
    return _tap(tap, page_index)


def _hold(hold: Any, page_index: dict[str, int]) -> dict | None:
    """Compile a hold: only a page to go to."""
    if (
        isinstance(hold, dict)
        and hold.get("local") == "go_to_page"
        and hold.get("page") in page_index
    ):
        return {"go": page_index[hold["page"]]}
    return None


def _theme2(theme_in: dict, keys_only: bool) -> dict[str, Any]:
    """Compile a theme entry. keys_only: only the keys it has (a page theme)."""
    theme: dict[str, Any] = {}
    if not keys_only or "dark" in theme_in:
        theme["dark"] = 1 if theme_in.get("dark") else 0
    for key in THEME_COLOURS:
        if not keys_only or key in theme_in:
            theme[key] = colour(theme_in.get(key, "#000000"))
    for key in RADII:
        if not keys_only or key in theme_in:
            theme[key] = int(theme_in.get(key, 0))
    return theme


def _style2(style: dict) -> dict[str, Any]:
    """Compile one card's style overrides, with the colours of version 2."""
    compiled: dict[str, Any] = {}
    for key in STYLE_COLOURS + STYLE_COLOURS_V2:
        if key in style:
            compiled[key] = colour(style[key])
    for key in RADII:
        if key in style:
            compiled[key] = int(style[key])
    if style.get("gd") in ("h", "v"):
        compiled["gd"] = 1 if style["gd"] == "h" else 0
    return compiled


def _ask(
    out: dict, question: str | None, slots: _Slots, icons: dict, level: int
) -> None:
    """Set the question and cf of an item that HA confirms (contract 4.3).

    An item with a confirm text, or with policy 3, asks first. HA's own
    question (a garage, gate or door cover) goes onto an item that sends and
    has no text of its own.
    """
    action = out.get("tap") or out.get("change") or {}
    if "confirm" not in out and question and "p" in action:
        out["confirm"] = coerce("t", question, icons, level)
    if "confirm" in out or action.get("p") == POLICIES.index("confirm"):
        out["cf"] = 1


def _widget2(
    widget: dict,
    slots: _Slots,
    icons: dict,
    level: int,
    page_index: dict[str, int],
    question: str | None = None,
) -> dict:
    """Compile one widget of a card, version 2.

    The keys of version 1 come first, as the version 1 writer makes them,
    then the keys of contract.json v2.widget_keys. Slot numbers follow the
    order in which fields are met, so this order is part of the bytes.
    """
    kind = widget["t"]
    out: dict[str, Any] = {"id": widget["id"], "t": kind, "r": widget["r"]}

    def bound(key: str, kind_char: str) -> None:
        """Compile a bound field when the widget has it."""
        if key in widget:
            out[key] = _bound(widget[key], kind_char, slots, icons, level)

    def whole(key: str) -> None:
        """Write a whole-number key when the widget has it."""
        if key in widget:
            out[key] = int(widget[key])

    # The keys of version 1.
    if kind == "label":
        out["text"] = _bound(widget.get("text", ""), "t", slots, icons, level)
        size = widget.get("size", "m")
        out["size"] = LABEL_SIZES.index(size) if size in LABEL_SIZES else 1
    elif kind == "button":
        bound("text", "t")
        if widget.get("icon"):
            out["icon"] = _icon(widget["icon"], icons, level)
    elif kind == "switch":
        out["value"] = _bound(widget.get("value"), "b", slots, icons, level)
    elif kind in ("slider", "thermostat"):
        for key, default in (("value", None), ("min", 0), ("max", 100), ("step", 1)):
            compiled = _bound(widget.get(key), "n", slots, icons, level)
            if compiled is None and default is not None:
                compiled = default
            out[key] = compiled
    elif kind == "chart":
        out["value"] = _bound(widget.get("value"), "l", slots, icons, level)
        chart_kind = widget.get("kind", "line")
        out["kind"] = CHART_KINDS.index(chart_kind) if chart_kind in CHART_KINDS else 0
    elif kind == "image":
        out["value"] = _bound(widget.get("value"), "i", slots, icons, level)
    if kind != "choice":
        bound("confirm", "t")

    # The keys of version 2.
    bound("vis", "b")
    if "c" in widget:
        out["c"] = _colour(widget["c"], slots)
    if kind == "label":
        for key in ("px", "al", "clk"):
            whole(key)
        if "clk" in widget:
            bound("value", "n")
    elif kind == "button":
        bound("value", "b")
        bound("ic", "i")
        whole("shape")
        whole("isz")
    elif kind == "slider":
        for key in ("look", "dir", "nv"):
            whole(key)
        if "track" in widget:
            out["track"] = [_colour_const(c) for c in widget["track"]][:MAX_TRACK]
        if widget.get("icon"):
            out["icon"] = _icon(widget["icon"], icons, level)
        bound("rate", "n")
    elif kind == "thermostat":
        bound("mark", "n")
        whole("bs")
    elif kind == "chart":
        bound("mark", "n")
        whole("st")
    elif kind == "image":
        whole("look")
    elif kind == "choice":
        if "texts" in widget:
            out["texts"] = [
                clip_text(text, MAX_OPTION_TEXT_BYTES)
                for text in widget["texts"][:MAX_OPTIONS]
            ]
        if "icons" in widget:
            out["icons"] = [
                _icon(name, icons, level) if name else 0
                for name in widget["icons"][:MAX_OPTIONS]
            ]
        if "cols" in widget:
            out["cols"] = [_colour_const(c) for c in widget["cols"][:MAX_OPTIONS]]
        bound("value", "n")
        whole("rows")
        whole("look")
    for key in ("tap", "change"):
        compiled = _tap2(widget.get(key), page_index)
        if compiled is not None:
            out[key] = compiled
    if kind not in ("slider", "thermostat", "choice"):
        hold = _hold(widget.get("hold"), page_index)
        if hold is not None:
            out["hold"] = hold
    if kind == "choice":
        bound("confirm", "t")
    _ask(out, question, slots, icons, level)
    return out


def _card2(
    source: dict,
    slots: _Slots,
    icons: dict,
    level: int,
    page_index: dict[str, int],
    question: str | None,
) -> dict:
    """Compile a card's own keys, version 2 (its widgets come after)."""
    card: dict[str, Any] = {"id": source["id"], "t": "card", "r": source["r"]}
    header = source.get("header")
    if isinstance(header, dict):
        card["hr"] = header["r"]
        if header.get("icon"):
            card["icon"] = _icon(header["icon"], icons, level)
        if "title" in header:
            card["title"] = _bound(header["title"], "t", slots, icons, level)
    if source.get("on") is not None:
        card["on"] = _bound(source["on"], "b", slots, icons, level)
    tap = _tap2(source.get("tap"), page_index)
    if tap is not None:
        card["tap"] = tap
    hold = _hold(source.get("hold"), page_index)
    if hold is not None:
        card["hold"] = hold
    if "confirm" in source:
        card["confirm"] = _bound(source["confirm"], "t", slots, icons, level)
    if "ic" in source:
        card["ic"] = _bound(source["ic"], "i", slots, icons, level)
    if "tint" in source:
        card["tint"] = _colour(source["tint"], slots)
    if "lit" in source:
        card["lit"] = int(source["lit"])
    if "un" in source:
        card["un"] = _bound(source["un"], "b", slots, icons, level)
    _ask(card, question, slots, icons, level)
    style = source.get("style")
    if isinstance(style, dict):
        card["style"] = _style2(style)
    return card


def compile_device_layout_v2(
    layout: dict,
    icons: dict,
    caps: dict | None = None,
    confirm: dict[int, str] | None = None,
) -> dict:
    """Compile a layout v2 into a device layout of version 2.

    confirm maps widget and card ids to a question the tablet asks before it
    sends, for items whose action HA confirms and that have no text of
    their own.

    Returns {"bytes", "hash", "size", "slots", "dropped", "counts"}. slots
    is the plan: each device slot with its source slot and type, and for a
    colour "coerce": "colour" and the role colours it knows. dropped lists
    the widget ids left out because the tablet cannot draw their kind.
    counts holds pages, normal pages, slots and widgets. Raises
    ContractError("limits") for more pages than min(caps.max_pages, 64),
    more than 20 normal pages, too many slots or widgets, and ("too_big")
    for more bytes than the tablet takes. A page is a detail page when its
    "sub" is set and it is not page 0; HA writes no nav entry for one.
    """
    caps = {**CAPS_DEFAULTS, **(caps or {})}
    listed = caps.get("w")
    kinds = set(listed) if isinstance(listed, list) else set(WIDGET_KINDS)
    known = set(WIDGET_KINDS) | set(WIDGET_KINDS_V2)
    level = min(int(caps["icons"]), int(icons["version"]))
    limit = min(int(caps["max_layout"]), MAX_LAYOUT_BYTES)
    max_slots = min(int(caps["max_slots"]), MAX_SLOTS)
    max_widgets = min(int(caps["max_widgets"]), MAX_WIDGETS)
    max_pages = min(int(caps["max_pages"]), MAX_PAGES_V2)
    questions = confirm or {}
    slots = _Slots()
    dropped: list[int] = []
    page_index = {page["id"]: index for index, page in enumerate(layout["pages"])}
    detail = {
        index
        for index, page in enumerate(layout["pages"])
        if index > 0 and page.get("sub")
    }

    nav = []
    for entry in layout.get("nav", []):
        if entry["page"] not in page_index or page_index[entry["page"]] in detail:
            continue
        item: dict[str, Any] = {
            "p": page_index[entry["page"]],
            "title": clip_text(entry.get("title", ""), 40),
        }
        if entry.get("icon"):
            item["icon"] = _icon(entry["icon"], icons, level)
        nav.append(item)
    nav = nav[:MAX_NAV]

    pages = []
    for page in layout["pages"]:
        items = []
        for source in page["w"]:
            if source["t"] == "heading":
                heading: dict[str, Any] = {
                    "id": source["id"],
                    "t": "heading",
                    "r": source["r"],
                    "text": clip_text(source.get("text", ""), 80),
                }
                if source.get("icon"):
                    heading["icon"] = _icon(source["icon"], icons, level)
                if "c" in source:
                    heading["c"] = _colour(source["c"], slots)
                items.append(heading)
                continue
            card = _card2(
                source, slots, icons, level, page_index, questions.get(source["id"])
            )
            widgets = []
            for widget in source.get("w", []):
                if widget.get("t") not in kinds or widget.get("t") not in known:
                    dropped.append(widget["id"])
                    continue
                widgets.append(
                    _widget2(
                        widget,
                        slots,
                        icons,
                        level,
                        page_index,
                        questions.get(widget["id"]),
                    )
                )
            card["w"] = widgets
            items.append(card)
        out_page: dict[str, Any] = {
            "title": clip_text(page.get("title", ""), 40),
            "w": items,
        }
        if page.get("sub"):
            out_page["sub"] = 1
        if "ttl" in page:
            out_page["ttl"] = int(page["ttl"])
        if isinstance(page.get("theme"), dict):
            out_page["theme"] = _theme2(page["theme"], True)
        pages.append(out_page)

    device = {
        "v": DL_VERSION,
        "screen": layout.get("screen", [1280, 800]),
        "theme": _theme2(layout.get("theme", {}), False),
        "nav": nav,
        "pages": pages,
        "slots": "".join(entry["type"] for entry in slots.plan),
    }
    widget_count = sum(len(page["w"]) for page in pages) + sum(
        len(item.get("w", [])) for page in pages for item in page["w"]
    )
    normal = len(pages) - len(detail)
    counts = {
        "pages": len(pages),
        "normal_pages": normal,
        "slots": len(slots.plan),
        "widgets": widget_count,
    }
    if len(pages) > max_pages:
        raise ContractError("limits", f"{len(pages)} pages, limit {max_pages}")
    if normal > MAX_PAGES:
        raise ContractError("limits", f"{normal} normal pages, limit {MAX_PAGES}")
    if len(slots.plan) > max_slots:
        raise ContractError("limits", f"{len(slots.plan)} slots, limit {max_slots}")
    if widget_count > max_widgets:
        raise ContractError("limits", f"{widget_count} widgets, limit {max_widgets}")
    data = canonical(device)
    if len(data) > limit:
        raise ContractError("too_big", f"{len(data)} bytes, limit {limit}")
    return {
        "bytes": data,
        "hash": content_hash(data),
        "size": len(data),
        "slots": slots.plan,
        "dropped": dropped,
        "counts": counts,
    }


def bindings_digest(bindings: dict, plan: list[dict]) -> str:
    """Return a digest of what feeds a device layout: its slots and actions.

    The device layout holds no entity ids, so its hash stays the same when a
    card is pointed at another entity. This digest changes then (contract
    section 4.4), which tells HA to rebuild the values and send them again.
    """
    by_number = {slot.get("n"): slot for slot in bindings.get("slots", [])}
    used = sorted({entry["src"] for entry in plan})
    body = {
        "slots": [by_number.get(number) for number in used],
        "plan": plan,
        "actions": bindings.get("actions", {}),
    }
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
