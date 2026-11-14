"""Compile a layout v1 into a device layout of version 1.

This is today's compile path, moved here unedited from ``device.py``
(contract section 4.6, SPEC A.2 rule 1). A tablet whose ``proto`` does not
include 2 gets these bytes, and no key of version 2 can reach them. The
shared helpers, the error class and the defaults live in ``device.py``.
Pure Python, no Home Assistant imports.
"""

from __future__ import annotations

from typing import Any

from .device import (
    CAPS_DEFAULTS,
    CHART_KINDS,
    LABEL_SIZES,
    MAX_LAYOUT_BYTES,
    MAX_NAV,
    MAX_PAGES,
    MAX_SLOTS,
    MAX_WIDGETS,
    POLICIES,
    RADII,
    STYLE_COLOURS,
    THEME_COLOURS,
    WIDGET_KINDS,
    ContractError,
    _icon,
    _tap,
    canonical,
    clip_text,
    coerce,
    colour,
    content_hash,
)

# The version this file writes. device.DL_VERSION is the newest one.
DL_VERSION = 1


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
