"""Compile a layout v1 into the device layout a TAB-1 tablet draws.

This follows contract section 4 (``contract/CONTRACT.md``). The bytes this
module makes are compared with the contract's golden fixtures, so a change
here is a change to the contract. Pure Python, no Home Assistant imports.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

DL_VERSION = 1

MAX_LAYOUT_BYTES = 262144
MAX_TEXT_BYTES = 255
MAX_LIST = 120
MAX_NUMBER = 1_000_000_000
MAX_PAGES = 20
MAX_NAV = 8
MAX_SLOTS = 1024
MAX_WIDGETS = 2048
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


def coerce(kind: str, value: Any, icons: dict, level: int) -> Any:
    """Turn an evaluated slot value into the wire value of a typed slot.

    None means "no value": the tablet draws the widget as unavailable.
    """
    if value is None:
        return None
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


# ---------------------------------------------------- device layout (DL v1)


class _Slots:
    """Give each (source slot, type) pair one device slot number."""

    def __init__(self) -> None:
        """Start with no slots."""
        self.plan: list[dict] = []
        self._index: dict[tuple[int, str], int] = {}

    def ref(self, source: int, kind: str) -> dict:
        """Return the reference to the device slot of this source and type."""
        key = (source, kind)
        if key not in self._index:
            self._index[key] = len(self.plan) + 1
            self.plan.append({"d": self._index[key], "src": source, "type": kind})
        return {"s": self._index[key]}


def _bound(value: Any, kind: str, slots: _Slots, icons: dict, level: int) -> Any:
    """Compile one bound field: a slot reference or a coerced constant."""
    if isinstance(value, dict) and "s" in value:
        return slots.ref(value["s"], kind)
    return coerce(kind, value, icons, level)


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


def _widget(
    widget: dict,
    slots: _Slots,
    icons: dict,
    level: int,
    page_index: dict[str, int],
    question: str | None = None,
) -> dict:
    """Compile one widget of a card.

    question: what the tablet asks before it sends, when HA wants a yes
    first (a garage, gate or door cover) and the card has no confirm text.
    """
    kind = widget["t"]
    out: dict[str, Any] = {"id": widget["id"], "t": kind, "r": widget["r"]}
    if kind == "label":
        out["text"] = _bound(widget.get("text", ""), "t", slots, icons, level)
        size = widget.get("size", "m")
        out["size"] = LABEL_SIZES.index(size) if size in LABEL_SIZES else 1
    elif kind == "button":
        if "text" in widget:
            out["text"] = _bound(widget["text"], "t", slots, icons, level)
        if widget.get("icon"):
            out["icon"] = _icon(widget["icon"], icons, level)
    elif kind == "switch":
        out["value"] = _bound(widget.get("value"), "b", slots, icons, level)
    elif kind in ("slider", "thermostat"):
        for key, default in (("value", None), ("min", 0), ("max", 100), ("step", 1)):
            raw = widget.get(key)
            compiled = _bound(raw, "n", slots, icons, level)
            if compiled is None and default is not None:
                compiled = default
            out[key] = compiled
    elif kind == "chart":
        out["value"] = _bound(widget.get("value"), "l", slots, icons, level)
        chart_kind = widget.get("kind", "line")
        out["kind"] = CHART_KINDS.index(chart_kind) if chart_kind in CHART_KINDS else 0
    elif kind == "image":
        out["value"] = _bound(widget.get("value"), "i", slots, icons, level)
    for key in ("tap", "change"):
        compiled = _tap(widget.get(key), page_index)
        if compiled is not None:
            out[key] = compiled
    action = out.get("tap") or out.get("change") or {}
    if "confirm" in widget:
        out["confirm"] = _bound(widget["confirm"], "t", slots, icons, level)
    elif question and "p" in action:
        out["confirm"] = coerce("t", question, icons, level)
    if "confirm" in out or action.get("p") == POLICIES.index("confirm"):
        out["cf"] = 1
    return out


def _theme(theme_in: dict) -> dict[str, Any]:
    """Compile the layout's theme into integers."""
    theme: dict[str, Any] = {"dark": 1 if theme_in.get("dark") else 0}
    for key in THEME_COLOURS:
        theme[key] = colour(theme_in.get(key, "#000000"))
    for key in RADII:
        theme[key] = int(theme_in.get(key, 0))
    return theme


def _style(style: dict) -> dict[str, Any]:
    """Compile one card's style overrides."""
    compiled: dict[str, Any] = {}
    for key in STYLE_COLOURS:
        if key in style:
            compiled[key] = colour(style[key])
    for key in RADII:
        if key in style:
            compiled[key] = int(style[key])
    if style.get("gd") in ("h", "v"):
        compiled["gd"] = 1 if style["gd"] == "h" else 0
    return compiled


def compile_device_layout(
    layout: dict,
    icons: dict,
    caps: dict | None = None,
    confirm: dict[int, str] | None = None,
) -> dict:
    """Compile a layout v1 (from convert.py) into the device layout.

    confirm maps widget ids to a question the tablet asks before it sends
    (contract 4.3 `confirm`, `cf`), for widgets whose action HA confirms.

    Returns {"bytes", "hash", "size", "slots", "dropped", "counts"}. slots is
    the plan that maps each device slot to its source slot number and type.
    dropped lists the widget ids left out because the tablet cannot draw
    their kind. counts holds pages, slots and widgets (every object with an
    id). Raises ContractError("too_big") when the bytes exceed the tablet's
    limit and ContractError("limits") when pages, slots or widgets do.
    """
    caps = {**CAPS_DEFAULTS, **(caps or {})}
    # A missing caps.w is the default list; an empty list is a tablet that
    # draws no widget kind inside a card. Headings and cards always stay.
    listed = caps.get("w")
    kinds = set(listed) if isinstance(listed, list) else set(WIDGET_KINDS)
    level = min(int(caps["icons"]), int(icons["version"]))
    limit = min(int(caps["max_layout"]), MAX_LAYOUT_BYTES)
    max_slots = min(int(caps["max_slots"]), MAX_SLOTS)
    max_widgets = min(int(caps["max_widgets"]), MAX_WIDGETS)
    slots = _Slots()
    dropped: list[int] = []
    page_index = {page["id"]: index for index, page in enumerate(layout["pages"])}

    nav = []
    for entry in layout.get("nav", []):
        if entry["page"] not in page_index:
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
                items.append(heading)
                continue
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
            style = source.get("style")
            if isinstance(style, dict):
                card["style"] = _style(style)
            widgets = []
            for widget in source.get("w", []):
                if widget.get("t") not in kinds or widget.get("t") not in WIDGET_KINDS:
                    dropped.append(widget["id"])
                    continue
                question = (confirm or {}).get(widget["id"])
                widgets.append(
                    _widget(widget, slots, icons, level, page_index, question)
                )
            card["w"] = widgets
            items.append(card)
        pages.append({"title": clip_text(page.get("title", ""), 40), "w": items})

    device = {
        "v": DL_VERSION,
        "screen": layout.get("screen", [1280, 800]),
        "theme": _theme(layout.get("theme", {})),
        "nav": nav,
        "pages": pages,
        "slots": "".join(entry["type"] for entry in slots.plan),
    }
    widget_count = sum(len(page["w"]) for page in pages) + sum(
        len(item.get("w", [])) for page in pages for item in page["w"]
    )
    counts = {"pages": len(pages), "slots": len(slots.plan), "widgets": widget_count}
    if len(pages) > MAX_PAGES:
        raise ContractError("limits", f"{len(pages)} pages, limit {MAX_PAGES}")
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
