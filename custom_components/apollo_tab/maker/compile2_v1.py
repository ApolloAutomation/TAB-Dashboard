"""The version 1 form of a schema 2 card (C.6 of the cards spec, rule 2).

What a tablet with engine 0.1.0 shows for a schema 2 card when no old card
stands in for it: the variant itself, compiled with `tablet.v2` false and
laid out by today's `layout_card`, so that only keys of version 1 come out.
Look keys are dropped, items that cannot work without version 2 are left
out, and only icons of level 1 are kept, so no fallback glyph is ever
written. The result has the shape of compile.py's result, so the converter
builds it like a schema 1 card. When nothing is left that shows a value or
acts, there is no form and the converter writes the note (rule 3).
"""

from __future__ import annotations

from collections.abc import Set
from typing import Any

from .compile2 import _Compiler2, validate_card_config2
from .errors import MakerError
from .geometry import card_size_px, layout_card

# Label sizes of version 2 and the version 1 size each is drawn at.
LABEL_SIZE_V1 = {
    "s": "s",
    "m": "m",
    "ml": "m",
    "l": "l",
    "xl": "l",
    "xxl": "l",
    "huge": "l",
}
# Header forms that become today's title header.
TITLE_HEADERS = ("title", "chip", "tile", "tile_v")


def level1_names(icons: object) -> frozenset[str]:
    """Return the names of the icons of level 1 in the contract's icons.json.

    Engine 0.1.0 holds those. Anything that is not icons.json gives none.
    """
    table = icons.get("icons") if isinstance(icons, dict) else None
    if not isinstance(table, dict):
        return frozenset()
    return frozenset(
        name
        for name, entry in table.items()
        if isinstance(entry, list)
        and len(entry) == 2
        and isinstance(entry[1], int | float)
        and entry[1] <= 1
    )


def compile_card2_v1(
    component: dict,
    card: dict,
    facts: dict | None = None,
    *,
    level1: Set[str] = frozenset(),
) -> dict | None:
    """Return the version 1 form of a validated schema 2 card, or None.

    level1 holds the icon names of level 1; any other fixed icon is left
    out. None means the form keeps nothing that shows a value or acts, and
    the card is shown as the note.
    """
    return _V1Form(component, card, facts or {}, level1).form()


def keeps_nothing(component: dict, variant: str, level1: Set[str]) -> bool:
    """Return whether a variant's own version 1 form keeps nothing (C.6, rule 2).

    Made as the picker shows the card: the file's preview values (for a
    page or number param too, which a demo card does not read), the default
    options and the variant's own grid. True means a version 1 tablet gets
    the note for it, unless an old card stands in (rule 1). A card that
    cannot be made without its devices tells nothing: False.
    """
    preview = component["preview"]["params"]
    params = {
        name: value
        for name, value in preview.items()
        if component["params"][name]["kind"] != "entity"
    }
    try:
        card = validate_card_config2(component, {"params": params})
    except MakerError:
        return False
    columns, rows = component["variants"][variant]["grid"]
    card = {**card, "variant": variant, "columns": columns, "rows": rows}
    try:
        return compile_card2_v1(component, card, {}, level1=level1) is None
    except MakerError:
        return False


def variant_of(component: dict, card: dict) -> str:
    """Return the variant a card is drawn in (the person's, else the largest)."""
    return _Compiler2(component, card, {}, 2, None, False)._variant()


def note_card(component: dict, card: dict, text: str) -> dict:
    """Return the note a version 1 tablet shows for a card it cannot draw.

    A plain card with the card's name and one line of text, version 1
    widgets only, in the shape of compile.py's result.
    """
    columns = card["columns"]
    columns = 36 if columns == "full" else columns
    width, height = card_size_px(columns, card["rows"])
    laid = layout_card([{"type": "label", "size": "s"}], width, height, True)
    if laid["rects"][0] is None:
        # No room under a header (a card one row high): the line alone.
        laid = layout_card([{"type": "label", "size": "s"}], width, height, False)
    title = card["title"] if card["title"] is not None else component["name"]
    widgets = []
    if laid["rects"][0] is not None:
        widgets.append(
            {"i": 0, "t": "label", "r": laid["rects"][0], "text": text, "size": "s"}
        )
    header = {"r": laid["header"], "title": title} if laid["header"] else None
    return {
        "component": component["id"],
        "name": component["name"],
        "demo": bool(card["missing"]),
        "w": width,
        "h": height,
        "entities": [],
        "header": header,
        "on": None,
        "widgets": widgets,
        "slots": [],
        "actions": {},
        "warnings": [],
        "note": True,
    }


class _V1Form(_Compiler2):
    """Compile one schema 2 card into its version 1 form."""

    def __init__(
        self, component: dict, card: dict, facts: dict, level1: Set[str]
    ) -> None:
        """Work out the card's facts and options as a version 1 tablet sees them."""
        super().__init__(component, card, facts, 1, None, False)
        self.level1 = level1

    # ------------------------------------------------------------ the form

    def form(self) -> dict | None:
        """Compile the card; None when nothing shows a value or acts."""
        variant = self.component["variants"][self._variant()]
        columns = self.card["columns"]
        columns = 36 if columns == "full" else columns
        width, height = card_size_px(columns, self.card["rows"])
        header = variant["header"] in TITLE_HEADERS
        entries = self._entries(variant)
        geo = [self._geo_v1(item, group) for item, _names, group in entries]
        laid = layout_card(geo, width, height, header)
        title = self._title() if header else None
        built_header = None
        if header:
            built_header = {"r": laid["header"]}
            icon = self._v1_header_icon()
            if icon is not None:
                built_header["icon"] = icon
            built_header["title"] = title
        on = self._bind(self.component["on"], {}, "bool")
        widgets: list = []
        for (item, names, _group), rect in zip(entries, laid["rects"], strict=True):
            if rect is None:
                continue
            widget = self._widget_v1(item, names, rect, len(widgets), on)
            if widget is not None:
                widgets.append(widget)
        if not any(self._works(widget) for widget in widgets):
            return None
        if on is None:
            on = next((w["value"] for w in widgets if w["t"] == "switch"), None)
        clipped = bool(laid["clipped"]) or self.cut
        return {
            "component": self.component["id"],
            "name": self.component["name"],
            "demo": self.demo,
            "w": width,
            "h": height,
            "entities": self._entities(),
            "header": built_header,
            "on": on,
            "widgets": widgets,
            "slots": self.slots,
            "actions": self.actions,
            "call": self._call(),
            "warnings": ["element_clipped"] if clipped else [],
        }

    def _entries(self, variant: dict) -> list[tuple[dict, dict, int | None]]:
        """Return the widgets a version 1 tablet can show, in layout order.

        A trailing switch comes first, where today's geometry moves it into
        the header; a trailing text becomes a small label row. Swaps and
        items with `visible` are left out, and so is any item that cannot
        work without version 2. A row gives its widgets, in today's rows.
        """
        out: list[tuple[dict, dict, int | None]] = []
        trailing = variant["trailing"]
        if trailing is not None and variant["header"] in ("tile", "tile_v"):
            if trailing["form"] == "switch":
                out.append(({"type": "_trailing_switch"}, {}, None))
            elif trailing["form"] == "input":
                out.append(({"type": "_trailing_text", **trailing}, {}, None))
        for row in self._expand(variant["layout"]):
            if row["kind"] != "row":
                continue
            for item, names in row["cells"]:
                if self._keeps(item):
                    out.append((item, names, None))
        return out

    @staticmethod
    def _keeps(item: dict) -> bool:
        """Return whether an item can work on a version 1 tablet."""
        kind = item["type"]
        if kind == "choice" or "visible" in item:
            return False
        if kind == "slider" and (
            "track" in item
            or item.get("direction") in ("up", "down")
            or "rate" in item
            or item.get("keep_active")
        ):
            return False
        return not (kind == "label" and item.get("clock") is not None)

    @staticmethod
    def _geo_v1(item: dict, group: int | None) -> dict:
        """Build today's geometry input of one widget."""
        kind = item["type"]
        if kind == "_trailing_switch":
            return {"type": "switch"}
        if kind == "_trailing_text":
            return {"type": "label", "size": "s"}
        geo: dict = {"type": kind}
        if kind == "label":
            geo["size"] = LABEL_SIZE_V1.get(item.get("size"), "m")
        if item.get("side"):
            geo["side"] = True
        if group is not None:
            geo["group"] = group
        return geo

    # ------------------------------------------------------------ icons

    def _level1(self, icon: object) -> str | None:
        """Return a fixed icon when it is of level 1, else None."""
        if isinstance(icon, str) and icon in self.level1:
            return icon
        return None

    def _v1_header_icon(self) -> str | None:
        """Return the first of the card's icons that is of level 1 (C.6)."""
        for icon in (
            self.standard.get("icon"),
            self.can.get("icon"),
            self.component["icon"],
        ):
            if self._level1(icon) is not None:
                return icon
        return None

    def _fixed_icon(self, mark: dict | None, names: dict) -> tuple[bool, str | None]:
        """Return (fixed, icon) of an icon field; a live icon is not fixed."""
        if mark is None or mark["form"] not in ("const", "lookup"):
            return False, None
        return True, self._bind(mark, names, "icon")

    # ------------------------------------------------------------ widgets

    @staticmethod
    def _works(widget: dict) -> bool:
        """Return whether a widget shows a value or acts."""
        kind = widget["t"]
        if kind == "label":
            return isinstance(widget.get("text"), dict)
        if kind == "button":
            return "tap" in widget
        return True

    def _v1_tap(self, name: str, index: int, names: dict) -> dict | None | bool:
        """Build a version 1 tap; False when it would open a page v1 lacks."""
        if name == "detail":
            return False
        output = self.component["outputs"][name]
        if output["kind"] != "action" and output["local"] in ("detail", "back"):
            return False
        return self._tap_of(name, str(index), names)

    def _widget_v1(
        self, item: dict, names: dict, rect: list, index: int, on: Any
    ) -> dict | None:
        """Compile one widget with version 1 keys only; None leaves it out."""
        kind = item["type"]
        if kind == "_trailing_switch":
            return self._trailing_switch(rect, index, on)
        if kind == "_trailing_text":
            text = self._bind_input(item["input"], {}, "text")
            return {"i": index, "t": "label", "r": rect, "text": text, "size": "s"}
        for trigger in ("on_tap", "on_change"):
            name = item.get(trigger)
            if name and name != "detail" and not self._output_reaches(name, names):
                return None
        widget: dict = {"i": index, "t": kind, "r": rect}
        if kind == "button":
            fixed, icon = self._fixed_icon(item.get("icon"), names)
            icon = self._level1(icon) if fixed else None
            if icon is None and "text" not in item:
                return None
            on_tap = item.get("on_tap")
            if on_tap:
                tap = self._v1_tap(on_tap, index, names)
                if tap is False or tap is None:
                    # A button that would do nothing on this tablet.
                    return None
            if "text" in item:
                widget["text"] = self._bind(item["text"], names, "text")
            if icon is not None:
                widget["icon"] = icon
            if on_tap:
                widget["tap"] = tap
        elif kind == "image":
            fixed, icon = self._fixed_icon(item.get("value"), names)
            if fixed and self._level1(icon) is None:
                return None
            widget["value"] = (
                icon if fixed else self._bind(item["value"], names, "icon")
            )
            widget["refresh"] = self._refresh(item)
        elif kind == "label":
            if "text" in item:
                widget["text"] = self._bind(item["text"], names, "text")
            else:
                widget["text"] = ""
            widget["size"] = LABEL_SIZE_V1.get(item["size"], "m")
        elif kind == "switch":
            widget["value"] = self._bind(item["value"], names, "bool")
        elif kind in ("slider", "thermostat"):
            widget["value"] = self._bind(item["value"], names, "number")
            for key in ("min", "max", "step"):
                widget[key] = self._bind(item[key], names, "number")
        elif kind == "chart":
            widget["value"] = self._bind(item["value"], names, "list")
            widget["kind"] = "line" if item["kind"] == "steps" else item["kind"]
        if kind != "button" and item.get("on_tap"):
            tap = self._v1_tap(item["on_tap"], index, names)
            if isinstance(tap, dict):
                widget["tap"] = tap
        on_change = item.get("on_change")
        if on_change and kind in ("slider", "thermostat"):
            output = self.component["outputs"][on_change]
            widget["change"] = {"policy": output["feedback"]}
            self.actions[f"{index}:change"] = self._action(on_change, names)
        if item.get("confirm") is not None and ("tap" in widget or "change" in widget):
            widget["confirm"] = self._bind(item["confirm"], names, "text")
        return widget

    def _trailing_switch(self, rect: list, index: int, on: Any) -> dict:
        """Compile the tile header's switch as a switch at the top."""
        _tap, toggle = self._card_tap_v1()
        widget: dict = {"i": index, "t": "switch", "r": rect, "value": on}
        if toggle is not None:
            tap = self._tap_of(toggle, str(index), {})
            if tap is not None:
                widget["tap"] = tap
        return widget

    def _card_tap_v1(self) -> tuple[None, str | None]:
        """Return the output a trailing switch runs; the card tap is dropped."""
        tap = self.component["tap"]
        if tap is None:
            return None, None
        choices = [
            c
            for c in tap["choices"]
            if self._offered(c)
            and "output" in c
            and self._output_reaches(c["output"], {})
        ]
        chosen_value = self.standard.get("tap")
        chosen = next((c for c in choices if c["value"] == chosen_value), None)
        for choice in ([chosen] + choices) if chosen else choices:
            if self.component["outputs"][choice["output"]]["kind"] == "action":
                return None, choice["output"]
        return None, None

    def _refresh(self, item: dict) -> int:
        """Return the camera refresh seconds behind an image value, else 0."""
        mark = item.get("value")
        if isinstance(mark, dict) and mark.get("form") == "input":
            spec = self.component["inputs"].get(mark["input"])
            if spec is not None and spec["kind"] == "camera":
                return spec.get("refresh", 0)
        return 0
