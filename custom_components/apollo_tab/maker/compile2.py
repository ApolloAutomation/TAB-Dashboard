"""Compile a card of schema 2 (C.3 and C.4 of the cards spec).

Schema 1 cards keep compile.py, unedited. This module resolves a card's
options, picks its variant, applies `when`, expands loops, lays the card out
with `layout_card2` and binds every field by the form the loader marked on
it (schema2.py): a constant, a lookup, a template or an input. It never
looks into a value to decide whether it is a template, and it renders
nothing. Option values, facts, names a device reports, loop entries and
titles are data: they reach the layout as constants, or a template as
variables, never as template source.

The result is in the shape of layout v2 (contract 4.3, with source slots,
`#RRGGBB` colours and `mdi:` names). Two things are left to the converter,
which knows the dashboard: `{"local": "detail"}` in a tap or hold (the
card's detail page gets its id there), and the card's own tap action, kept
under "card:tap".
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .compile import ICON_ALONE, ICON_ALONE_MIN, _constant, _mentions, _prelude, _source
from .const import (
    COLOUR_ROLES,
    ENTITY_ID_RE,
    ICON_RE,
    KELVIN_RE,
    MAX_WIDGETS_2,
    PAGE_PATH_RE,
)
from .errors import MakerError
from .features import card_facts, facts_of
from .geometry import (
    LABEL_ROWS_2,
    PAD,
    button_text_alone,
    card_size_px,
    layout_card2,
    switch_fits_tile_header,
)
from .schema import (
    _as_mapping,
    _card_title,
    _validate_icon,
    validate_style,
)
from .schema2 import check_option_value
from .when import term_holds, truthy, when_holds

_ENTITY_ID = re.compile(ENTITY_ID_RE)
_ICON = re.compile(ICON_RE)
_KELVIN = re.compile(KELVIN_RE)
_PAGE_PATH = re.compile(PAGE_PATH_RE)
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Device names and numbers of the look keys (contract.json "v2").
LIT = ("fill", "icon", "outline", "none")
ALIGN = ("left", "centre", "right")
# A value that shows alone in a tiny card keeps this far from its sides.
VALUE_ALONE_PAD = 4
SHAPES = ("box", "round", "bare")
SLIDER_LOOKS = ("knob", "bar")
DIRS = ("right", "up", "down")
IMAGE_LOOKS = ("box", "badge", "bare")
CHOICE_LOOKS = ("cells", "dots")
# Label sizes: s, m and l are version 1's `size`; the others are `px`.
LABEL_PX = {"ml": 28, "xl": 48, "xxl": 96, "huge": 192}
MORE_ICON = "mdi:dots-horizontal"
MAX_ROW_WIDGETS = 8
MAX_COPIES = 16
TRACK_KELVIN_STEPS = 5

# The card's table of roles when the converter gives none: the midnight
# theme and the status colours of a dark theme (cards spec E.3).
DEFAULT_ROLES = {
    "accent": "#FFB347",
    "accent2": "#6CB4FF",
    "text": "#F2F4F7",
    "muted": "#9AA3AF",
    "good": "#4CC38A",
    "warn": "#F5B547",
    "bad": "#FF6B5E",
    "info": "#6CB4FF",
}
# Theme keys behind the roles that a theme entry holds.
THEME_ROLES = {"accent": "acc", "accent2": "acc2", "text": "tx", "muted": "tx2"}
STANDARD_DEFAULTS = {"icon": None, "tap": None, "tap_page": "", "hold": True}
# A character of a header name (label m) is about 10.5 px wide on average.
NAME_CHAR_W_X2 = 21
ELLIPSIS = "…"
# Widths of the header name's font (Montserrat Medium at 18 px, label m) in
# tenths of a pixel, for the characters " " to "~", and of "…". Any other
# character counts as NAME_W_OTHER.
_NAME_W_ASCII = (
    48, 48, 70, 127, 112, 152, 123, 38, 61, 61, 72, 105, 41, 69, 41, 63,
    120, 67, 103, 103, 120, 103, 111, 108, 116, 111, 41, 41, 105, 105, 105, 103,
    186, 132, 136, 130, 149, 121, 114, 139, 146, 56, 92, 129, 107, 172, 146, 151,
    130, 151, 131, 112, 106, 142, 128, 203, 121, 116, 118, 60, 63, 60, 105, 90,
    108, 108, 123, 103, 123, 110, 64, 124, 123, 50, 51, 111, 50, 190, 123, 114,
    123, 123, 74, 90, 75, 122, 101, 162, 99, 101, 94, 63, 54, 63, 105,
)  # fmt: skip
NAME_W = {chr(32 + i): w for i, w in enumerate(_NAME_W_ASCII)} | {ELLIPSIS: 124}
NAME_W_OTHER = 140
# A name cut to fit keeps this much room spare, in tenths of a pixel.
NAME_W_SPARE = 20


def name_width(text: str) -> int:
    """Return how wide a header name is drawn, in tenths of a pixel."""
    return sum(NAME_W.get(char, NAME_W_OTHER) for char in text)


def name_chars(width: int) -> int:
    """Return how many characters of a header name fit in a width."""
    return width * 2 // NAME_CHAR_W_X2


def cut_middle(name: str, chars: int) -> str:
    """Cut a long name in the middle, so its end stays.

    "Living Room Lamp 1" becomes "Living…Lamp 1", not "Living Room L…": names
    of lamps in one room often differ only at the end. The end kept is the
    last word, with the word before it when the last is shorter than 4. A
    name of one word, or an end longer than half the room, is left whole:
    the tablet cuts it at its end.
    """
    if len(name) <= chars:
        return name
    words = name.split(" ")
    tail = words[-1]
    if len(words) > 2 and len(tail) < 4:
        tail = words[-2] + " " + tail
    head = name[: chars - 1 - len(tail)].rstrip()
    if len(words) < 2 or len(tail) > chars // 2 or not head:
        return name
    return head + ELLIPSIS + tail


def cut_to_fit(name: str, chars: int, width: int) -> str:
    """Cut a name in the middle (cut_middle) so it fits a width in pixels.

    chars is a first guess from the average width of a character. A name
    that fits whole stays whole. A middle cut still too wide for its font
    is cut further; when no middle cut is left, the name stays whole and
    the tablet cuts it at its end. So the name never shows two "…".
    """
    room = width * 10 - NAME_W_SPARE
    if name_width(name) <= room:
        return name
    for k in range(chars, 0, -1):
        shown = cut_middle(name, k)
        if shown == name:
            return name
        if name_width(shown) <= room:
            return shown
    return name


def cut_to_fit_template(chars: int, width: int) -> str:
    """Return cut_to_fit as a template for the name `n`.

    It needs the variable `name_w` (NAME_W).
    """
    room = width * 10 - NAME_W_SPARE
    return (
        "{%- set w = n.split(' ') -%}"
        "{%- set t = (w[-2] ~ ' ' ~ w[-1]) if w | length > 2 and w[-1] | length < 4"
        " else w[-1] -%}"
        "{%- set m = namespace(w=0) -%}"
        "{%- for c in n -%}{%- set m.w = m.w + name_w.get(c, "
        + str(NAME_W_OTHER)
        + ") -%}{%- endfor -%}"
        "{%- set ns = namespace(out=n, done=m.w <= " + str(room) + ") -%}"
        "{%- for k in range(" + str(chars) + ", 0, -1) -%}{%- if not ns.done -%}"
        "{%- set h = n[:k - 1 - t | length].rstrip() -%}"
        "{%- set r = n if n | length <= k or w | length < 2 or t | length > k // 2"
        " or not h else h ~ '…' ~ t -%}"
        "{%- if r == n -%}{%- set ns.done = true -%}{%- else -%}"
        "{%- set m = namespace(w=0) -%}"
        "{%- for c in r -%}{%- set m.w = m.w + name_w.get(c, "
        + str(NAME_W_OTHER)
        + ") -%}{%- endfor -%}"
        "{%- if m.w <= " + str(room) + " -%}"
        "{%- set ns.out = r -%}{%- set ns.done = true -%}{%- endif -%}"
        "{%- endif -%}{%- endif -%}{%- endfor -%}{{- ns.out -}}"
    )


def role_table(
    theme: dict | None, status: dict | None = None, base: dict | None = None
) -> dict:
    """Return a card's table of roles from its theme and status colours.

    theme is the card's theme entry with its style on top; status maps
    good, warn, bad and info to colours. A role neither gives keeps base.
    """
    table = dict(base or DEFAULT_ROLES)
    for role, key in THEME_ROLES.items():
        value = (theme or {}).get(key)
        if isinstance(value, str) and _HEX.match(value):
            table[role] = value.upper()
    for role in ("good", "warn", "bad", "info"):
        value = (status or {}).get(role)
        if isinstance(value, str) and _HEX.match(value):
            table[role] = value.upper()
    return table


def kelvin_rgb(kelvin: float) -> list[int]:
    """Return [r, g, b] of a white of that warmth.

    Home Assistant's own `color_temperature_to_rgb` (T. Helland's fit),
    with halves rounded up.
    """
    temp = min(max(kelvin, 1000), 40000) / 100.0

    def clamp(value: float) -> float:
        return min(max(value, 0), 255)

    if temp <= 66:
        red = 255.0
        green = clamp(99.4708025861 * math.log(temp) - 161.1195681661)
    else:
        red = clamp(329.698727446 * math.pow(temp - 60, -0.1332047592))
        green = clamp(288.1221695283 * math.pow(temp - 60, -0.0755148492))
    if temp >= 66:
        blue = 255.0
    elif temp <= 19:
        blue = 0.0
    else:
        blue = clamp(138.5177312231 * math.log(temp - 10) - 305.0447927307)
    return [math.floor(part + 0.5) for part in (red, green, blue)]


def _hex(rgb: list[int]) -> str:
    """Return [r, g, b] as #RRGGBB."""
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def kelvin_track(low: float, high: float) -> list[str]:
    """Return five colours at equal steps from low to high kelvin."""
    steps = TRACK_KELVIN_STEPS - 1
    return [_hex(kelvin_rgb(low + (high - low) * i / steps)) for i in range(steps + 1)]


# ---------------------------------------------------------------- card config


def _note(notes: list, code: str, path: str) -> None:
    """Record something left out of a card's config."""
    notes.append({"code": code, "path": path})


def _entity_value(value: object, spec: dict, path: str) -> str:
    """Validate one entity id against an entity param's kinds."""
    if not isinstance(value, str) or not _ENTITY_ID.match(value):
        raise MakerError("bad_value", path, f"bad entity id {value!r}")
    kinds = spec["domains"]
    if kinds and value.split(".", 1)[0] not in kinds:
        raise MakerError("bad_value", path, f"expected one of {', '.join(kinds)}")
    return value


def _param_value(spec: dict, value: object, path: str) -> tuple[bool, object]:
    """Return (present, value) for one param of a schema 2 card config."""
    kind = spec["kind"]
    if kind == "entity":
        if value is None or value == "" or value == []:
            return False, None
        if spec["multiple"]:
            items = [value] if isinstance(value, str) else value
            if not isinstance(items, list):
                raise MakerError("bad_value", path, "expected a list of entity ids")
            if len(items) > spec["max"]:
                raise MakerError("bad_value", path, f"at most {spec['max']} entities")
            out = [_entity_value(item, spec, path) for item in items]
            if len(set(out)) != len(out):
                raise MakerError("bad_value", path, "an entity is listed twice")
            return True, out
        return True, _entity_value(value, spec, path)
    if kind == "number":
        if value is None:
            return True, spec["default"]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise MakerError("bad_value", path, "expected a number")
        number = float(value)
        if not math.isfinite(number):
            raise MakerError("bad_value", path, "expected a finite number")
        low, high = spec["min"], spec["max"]
        if (low is not None and number < low) or (high is not None and number > high):
            raise MakerError("bad_value", path, "number outside its allowed range")
        return True, number
    if value is None or value == "":
        return True, ""
    if not isinstance(value, str) or not _PAGE_PATH.match(value):
        raise MakerError("bad_value", path, f"bad page path {value!r}")
    return True, value


def _picker_variants(component: dict) -> list[str]:
    """Return the names of the variants the picker offers, in file order."""
    return [name for name, v in component["variants"].items() if v["picker"]]


def _standard(component: dict, raw: dict, notes: list) -> dict:
    """Validate the standard options; a bad one is dropped with a note."""
    out = dict(STANDARD_DEFAULTS)
    out["ask"] = False
    tap = component["tap"]
    keys = [choice["value"] for choice in tap["choices"]] + ["page"] if tap else []
    if tap is not None:
        out["tap"] = tap["default"]
    checks = {
        "icon": lambda v: _validate_icon(v, "options.icon"),
        "tap": lambda v: v if v in keys else _bad(),
        "tap_page": lambda v: (
            v if isinstance(v, str) and (_PAGE_PATH.match(v) or v == "") else _bad()
        ),
        "hold": lambda v: v if isinstance(v, bool) else _bad(),
        "ask": lambda v: v if isinstance(v, bool) else _bad(),
    }
    for name, check in checks.items():
        if name not in raw:
            continue
        try:
            out[name] = check(raw[name])
        except MakerError:
            _note(notes, "option_dropped", f"options.{name}")
    return out


def _bad() -> Any:
    """Raise the error a bad standard option gives."""
    raise MakerError("bad_value", "options", "bad value")


def validate_card_config2(component: dict, raw: object) -> dict:
    """Validate a stored config of a schema 2 card.

    Params stay strict, as in schema 1. An option the file no longer has is
    ignored with a note, and a value that fails its option's checks is
    dropped with a note, so its default counts (C.2.3). `from: can.<list>`
    values are checked against the device's list when the card is compiled.
    """
    cfg = _as_mapping(raw, "")
    notes: list = []
    raw_params = cfg.get("params")
    if raw_params is None:
        raw_params = {}
    if not isinstance(raw_params, dict):
        raise MakerError("not_a_mapping", "params", "params must be a mapping")
    for key in raw_params:
        if key not in component["params"]:
            raise MakerError("unknown_param", f"params.{key}", f"unknown param {key!r}")
    params: dict = {}
    missing: list = []
    for name, spec in component["params"].items():
        present, value = _param_value(spec, raw_params.get(name), f"params.{name}")
        if present:
            params[name] = value
        elif spec["kind"] == "entity" and not spec["optional"]:
            missing.append(name)
    raw_options = cfg.get("options")
    if raw_options is None:
        raw_options = {}
    if not isinstance(raw_options, dict):
        _note(notes, "option_dropped", "options")
        raw_options = {}
    options: dict = {}
    for name, value in raw_options.items():
        path = f"options.{name}"
        option = component["options"].get(name)
        if option is None:
            if name not in STANDARD_DEFAULTS and name != "ask":
                _note(notes, "option_unknown", path)
            continue
        try:
            options[name] = check_option_value(option, value, path)
        except MakerError, TypeError:
            _note(notes, "option_dropped", path)
    standard = _standard(component, raw_options, notes)
    variant = cfg.get("variant")
    if variant is not None and variant not in _picker_variants(component):
        _note(notes, "variant_unknown", "variant")
        variant = None
    style_raw = cfg.get("style")
    look: dict = {}
    if isinstance(style_raw, dict) and ({"lit", "tint"} & set(style_raw)):
        style_raw = dict(style_raw)
        lit = style_raw.pop("lit", None)
        tint = style_raw.pop("tint", None)
        if lit is not None:
            if lit in LIT:
                look["lit"] = lit
            else:
                _note(notes, "style_dropped", "style.lit")
        if tint is not None:
            if isinstance(tint, bool):
                look["tint"] = tint
            else:
                _note(notes, "style_dropped", "style.tint")
    grid_variant = component["variants"][variant or _picker_variants(component)[0]]
    columns, rows = grid_variant["grid"]
    grid = cfg.get("grid_options")
    if not isinstance(grid, dict):
        grid = {}
    raw_columns = grid.get("columns")
    if isinstance(raw_columns, int) and not isinstance(raw_columns, bool):
        if 1 <= raw_columns <= 36:
            columns = raw_columns
    elif raw_columns == "full":
        columns = "full"
    raw_rows = grid.get("rows")
    if (
        isinstance(raw_rows, int)
        and not isinstance(raw_rows, bool)
        and 1 <= raw_rows <= 12
    ):
        rows = raw_rows
    return {
        "params": params,
        "missing": missing,
        "title": _card_title(cfg),
        "style": validate_style(style_raw),
        "look": look,
        "options": options,
        "standard": standard,
        "variant": variant,
        "columns": columns,
        "rows": rows,
        "notes": notes,
    }


# ---------------------------------------------------------------- compiling


def compile_card2(
    component: dict,
    card: dict,
    facts: dict | None = None,
    dl: int = 2,
    *,
    roles: dict | None = None,
    detail: bool = False,
) -> dict:
    """Compile a validated schema 2 card config (validate_card_config2).

    facts maps an entity id to what it can do (maker/features.py). dl is the
    layout version it is made for; it sets `tablet.v2`. roles is the card's
    table of role colours (role_table). detail: compile the copy for the
    card's detail page, in its `detail` variant, with no card tap, no hold
    and no way to open the page it is on.
    """
    return _Compiler2(component, card, facts or {}, dl, roles, detail).run()


def _switch_stands_in(row: dict, trailing: tuple | None, toggle: str | None) -> bool:
    """Return whether a row left out only held buttons the header switch does.

    A Wide on/off lamp too low for its power button shows the header switch
    instead: nothing is lost, so it is not a clipped element.
    """
    if trailing is None or trailing[0] != "switch" or row["kind"] != "row":
        return False
    return toggle is not None and all(
        item["type"] == "button" and item.get("on_tap") == toggle
        for item, _names in row["cells"]
    )


class _Compiler2:
    """Hold the state for compiling one schema 2 card."""

    def __init__(
        self,
        component: dict,
        card: dict,
        facts: dict,
        dl: int,
        roles: dict | None,
        detail: bool,
    ) -> None:
        """Work out the card's facts, names and options."""
        self.component = component
        self.card = card
        self.dl = dl
        self.roles = dict(roles or DEFAULT_ROLES)
        self.detail_copy = detail
        self.notes: list = list(card.get("notes") or [])
        self.demo = bool(card["missing"])
        self.preview = component["preview"]
        if self.demo and not self.preview["params"] and not self.preview["inputs"]:
            raise MakerError(
                "params_incomplete",
                "params",
                "Card is missing params and the component has no preview values.",
            )
        self.param_vars = self._param_vars()
        self.facts = facts
        if self.demo:
            known = card_facts(component, self.param_vars, facts)
            self.can = {**known["can"], **self.preview["can"]}
            self.has = known["has"]
        else:
            known = card_facts(component, card["params"], facts)
            self.can = known["can"]
            self.has = known["has"]
        self.names = self._fact_names()
        self.options = self._options()
        self.names.update(self.options)
        self.standard = card["standard"]
        self._slot_keys: dict[str, int] = {}
        self.slots: list = []
        self.actions: dict = {}
        self.widgets: list = []
        self.cut = False
        self.opener = False
        self.tap_left_out = False
        self.uses: dict[int, dict] = {}

    # ------------------------------------------------------------ inputs

    def _param_vars(self) -> dict:
        """Map each param with a value to it, using previews when missing."""
        out = {}
        preview = self.preview["params"]
        for name in self.component["params"]:
            if name in self.card["params"]:
                out[name] = self.card["params"][name]
            elif self.demo and name in preview:
                out[name] = preview[name]
        return out

    def _entity_params(self) -> list[str]:
        """Return the entity params, in file order."""
        return [
            name
            for name, spec in self.component["params"].items()
            if spec["kind"] == "entity"
        ]

    def _fact_names(self) -> dict:
        """Return the names a `when` reads about facts, params and the tablet."""
        names: dict = {}
        entity_params = self._entity_params()
        for key, value in self.can.items():
            if key not in entity_params:
                names[f"can.{key}"] = value
        for param in entity_params:
            facts = self.can.get(param)
            if isinstance(facts, dict):
                for key, value in facts.items():
                    names[f"can.{param}.{key}"] = value
            elif isinstance(facts, list):
                keys = {
                    key for entry in facts if isinstance(entry, dict) for key in entry
                }
                for key in sorted(keys):
                    values = [
                        entry.get(key) for entry in facts if isinstance(entry, dict)
                    ]
                    held = [value for value in values if truthy(value)]
                    names[f"can.{param}.{key}"] = held[0] if held else values[0]
        for param, value in self.has.items():
            names[f"has.{param}"] = value
        names["tablet.v2"] = self.dl >= 2
        return names

    def _options(self) -> dict:
        """Resolve every option: the stored value, else its default; `needs`."""
        stored = self.card["options"]
        out = {}
        for name, option in self.component["options"].items():
            source = option.get("from")
            listed = self.names.get(source) if source else None
            listed = listed if isinstance(listed, list) else []
            if name in stored:
                value = stored[name]
                if source and not self._in_list(value, listed):
                    _note(self.notes, "option_dropped", f"options.{name}")
                    value = self._default(option, listed)
            else:
                value = self._default(option, listed)
            if option["needs"] and not term_holds(option["needs"], self.names):
                value = self._off(option)
            out[name] = value
        return out

    @staticmethod
    def _in_list(value: object, listed: list) -> bool:
        """Return whether a value of a `from` choice is in the device's list now."""
        values = value if isinstance(value, list) else [value]
        return all(entry in listed for entry in values)

    @staticmethod
    def _default(option: dict, listed: list) -> object:
        """Return an option's default; `default_first` takes the device's list."""
        if option.get("from"):
            if option["multiple"]:
                return list(listed[: option["default_first"]])
            return listed[0] if option["default_first"] and listed else None
        default = option["default"]
        return list(default) if isinstance(default, list) else default

    @staticmethod
    def _off(option: dict) -> object:
        """Return the value of an option whose `needs` fact is false."""
        otype = option["type"]
        if otype == "toggle":
            return False
        if otype == "choice":
            if option["multiple"] or option.get("from"):
                return [] if option["multiple"] else None
            return option["choices"][0]["value"]
        if otype == "colours":
            return []
        if otype == "text":
            return ""
        if otype in ("icon", "colour"):
            return None
        return option["default"]

    # ------------------------------------------------------------ the card

    def run(self) -> dict:
        """Compile the card and return the full server-side result."""
        variant_name = self._variant()
        variant = self.component["variants"][variant_name]
        self._variant_state = variant.get("state")
        columns = self.card["columns"]
        columns = 36 if columns == "full" else columns
        width, height = card_size_px(columns, self.card["rows"])
        body = self._expand(variant["layout"])
        header_form = variant["header"]
        trailing = self._trailing(variant)
        geo_body = [self._geo_row(row) for row in body]
        own = self._variant_state
        # No state line: a tile_v header ends under the name.
        state_line = (
            own["form"] != "none"
            if own is not None
            else self.component["state"] is not None
        )
        laid = layout_card2(
            geo_body,
            width,
            height,
            header_form,
            trailing[0] if trailing else None,
            # On a detail page the rows stack down from the header; the
            # converter then ends the card under them.
            self.detail_copy or variant["align"] == "top",
            state_line,
        )
        card_tap, toggle = self._card_tap()
        if (
            trailing is not None
            and trailing[0] == "switch"
            and self._button_runs(body, laid, toggle)
        ):
            # A button in the body already turns the device on and off: the
            # header shows no second switch for the same thing.
            trailing = None
            laid = layout_card2(
                geo_body,
                width,
                height,
                header_form,
                None,
                self.detail_copy or variant["align"] == "top",
                state_line,
            )
        self.on = self._bind(self.component["on"], {}, "bool")
        name_rect = laid["header"].get("name")
        title = self._title(None if name_rect is None else name_rect[2])
        icon = self._header_icon()
        ic = self._live_icon()
        tint = None
        if self.component["tint"] is not None and self.card["look"].get("tint", True):
            tint = self._bind(self.component["tint"], {}, "colour")
        header = None
        if header_form == "title" and "title" in laid["header"]:
            # A card too low for its title has no header: its icon alone
            # shows (_icon_alone).
            header = {"r": laid["header"]["title"]}
            if icon is not None:
                header["icon"] = icon
            header["title"] = title
        elif header_form != "title":
            self._header_widgets(
                header_form, laid["header"], trailing, title, icon, ic, tint, toggle
            )
        in_header = len(self.widgets)
        self._body_widgets(body, laid)
        if not self._value_alone(header, laid["header"], in_header, width, height):
            self._icon_alone(header, icon, ic, width, height)
        if self.on is None:
            self.on = next(
                (w["value"] for w in self.widgets if w["t"] == "switch"), None
            )
        out: dict = {
            "schema": 2,
            "component": self.component["id"],
            "name": self.component["name"],
            "variant": variant_name,
            "demo": self.demo,
            "w": width,
            "h": height,
            "entities": self._entities(),
            "header": header,
            "on": self.on,
            "lit": LIT.index(self.card["look"].get("lit", self.component["lit"])),
        }
        if tint is not None:
            out["tint"] = tint
        un = self._unavailable()
        if un is not None:
            out["un"] = un
        if ic is not None and header is not None and icon is not None:
            out["ic"] = ic
        if card_tap is not None:
            out["tap"] = card_tap["tap"]
            if card_tap.get("confirm"):
                out["confirm"] = card_tap["confirm"]
        hold = self._card_hold()
        if hold is not None:
            out["hold"] = hold
        left_out = [
            i
            for i in laid["clipped"]
            if not _switch_stands_in(body[i], trailing, toggle)
        ]
        # A card too narrow for its header switch: nothing is lost while a
        # tap on the card does the same.
        switch_lost = (
            trailing is not None
            and trailing[0] == "switch"
            and header_form == "tile"
            and not switch_fits_tile_header(width - 2 * PAD)
            and self.actions.get("card:tap", {}).get("output") != toggle
        )
        clipped = bool(left_out) or laid["dropped"] > 0 or self.cut or switch_lost
        warnings = ["element_clipped"] if clipped else []
        if self.tap_left_out:
            warnings.append("tap_left_out")
        out.update(
            {
                "widgets": self.widgets,
                "slots": self.slots,
                "actions": self.actions,
                "call": self._call(),
                "opener": self.opener,
                "warnings": warnings,
                "notes": self.notes,
            }
        )
        return out

    def _icon_alone(
        self, header: dict | None, icon: str | None, ic: Any, width: int, height: int
    ) -> None:
        """Draw the icon alone in a card too small for anything else.

        Without it such a card is an empty box, and a tap on it still acts.
        """
        if self.widgets or icon is None:
            return
        if header is not None and header["r"][2] > 0 and header["r"][3] > 0:
            return
        side = max(min(width, height, ICON_ALONE + 2 * PAD) - 2 * PAD, 0)
        if side < ICON_ALONE_MIN:
            return
        rect = [(width - side) // 2, (height - side) // 2, side, side]
        shown = ic if ic is not None else icon
        self._next({"t": "image", "r": rect, "value": shown, "look": 2})

    def _value_alone(
        self, header: dict | None, parts: dict, in_header: int, width: int, height: int
    ) -> bool:
        """Draw the card's `alone` text in a card too small for anything else.

        A card that exists to show a reading (the time, a temperature) shows
        it there instead of its icon. Only when nothing but icons would
        show: the header's icon or badge, a picture of the body. They go.
        """
        alone = self.component.get("alone")
        if alone is None:
            return False
        if any(w["t"] != "image" for w in self.widgets[in_header:]):
            return False
        if header is not None and header["r"][2] > 0 and header["r"][3] > 0:
            return False
        if set(parts) - {"icon", "badge"}:
            return False
        line = LABEL_ROWS_2["m"]
        if width - VALUE_ALONE_PAD * 2 < ICON_ALONE_MIN or height < line:
            return False
        del self.widgets[:]
        rect = [
            VALUE_ALONE_PAD,
            (height - line) // 2,
            width - VALUE_ALONE_PAD * 2,
            line,
        ]
        self._next(
            {
                "t": "label",
                "r": rect,
                "text": self._bind(alone, {}, "text"),
                "size": "m",
                "al": ALIGN.index("centre"),
            }
        )
        return True

    def _button_runs(self, body: list, laid: dict, output: str | None) -> bool:
        """Return whether a button with a place in the body taps this output."""
        if output is None:
            return False
        for row, rects in zip(body, laid["rects"], strict=True):
            if rects is None or row["kind"] == "space":
                continue
            members = row["cells"] if row["kind"] == "swap" else [row["cells"]]
            for member, member_rects in zip(members, rects, strict=True):
                for (item, names), rect in zip(member, member_rects, strict=True):
                    if (
                        rect is not None
                        and item["type"] == "button"
                        and item.get("on_tap") == output
                        and self._output_reaches(output, names)
                    ):
                        return True
        return False

    def _holds(self, name: str) -> bool:
        """Return whether the card's device can do what a variant needs."""
        needs = self.component["variants"][name].get("needs")
        return not needs or term_holds(needs, self.names)

    def _detail(self) -> str | None:
        """Return the detail variant, or None when there is none for this device.

        A detail variant whose `needs` does not hold makes no detail page,
        so nothing opens one: no hold, no tap choice, no `more`.
        """
        detail = self.component["detail"]
        return detail if detail and self._holds(detail) else None

    def _variant(self) -> str:
        """Pick the detail variant, the person's, else the largest that fits.

        Only variants whose `needs` holds count. A stored variant that does
        not hold gives the file's first picker variant that does. An example
        card (no device picked yet) is the picture of the variant it names,
        whatever the example's facts.
        """
        variants = self.component["variants"]
        if self.detail_copy and self._detail():
            return self.component["detail"]
        picker = [
            name for name in _picker_variants(self.component) if self._holds(name)
        ]
        if self.card["variant"] in variants:
            if self.demo or self._holds(self.card["variant"]):
                return self.card["variant"]
            return picker[0]
        columns = self.card["columns"]
        columns = 36 if columns == "full" else columns
        rows = self.card["rows"]

        def area(name: str) -> int:
            grid = variants[name]["grid"]
            return grid[0] * grid[1]

        fits = [
            name
            for name in picker
            if variants[name]["grid"][0] <= columns
            and variants[name]["grid"][1] <= rows
        ]
        if fits:
            return max(fits, key=lambda name: (area(name), -picker.index(name)))
        return min(picker, key=lambda name: (area(name), picker.index(name)))

    def _entities(self) -> list:
        """List the entity ids the person set, in param order."""
        out = []
        for name in self._entity_params():
            value = self.card["params"].get(name)
            if isinstance(value, list):
                out.extend(value)
            elif isinstance(value, str):
                out.append(value)
        return out

    def _first_entity(self) -> str | None:
        """Return the name of the first entity param that has a value."""
        for name in self._entity_params():
            if name in self.param_vars:
                return name
        return None

    def _title(self, width: int | None = None) -> Any:
        """Choose the title: the person's, the device's name, or the card's name.

        width: the room for the name of a tile or chip header, in pixels; a
        longer name is cut in the middle (cut_to_fit).
        """
        chars = None if width is None else name_chars(width)
        if self.card["title"] is not None:
            # Plain text from the browser: never a template.
            title = self.card["title"]
            return title if chars is None else cut_to_fit(title, chars, width)
        own = self.component.get("title_input")
        if own is not None and not self.demo:
            # The card's own title, from one of its inputs.
            if chars is None:
                return self._bind_input(own["input"], {}, "text")
            src = "{%- set n = (" + own["input"] + ") | string -%}"
            slot = self._template_slot(src + cut_to_fit_template(chars, width), {})
            slot["variables"]["name_w"] = dict(NAME_W)
            return {"s": self._add_slot(slot)}
        param = self._first_entity()
        spec = self.component["params"].get(param) if param else None
        if not self.demo and spec is not None and not spec["multiple"]:
            name = "state_attr(" + param + ", 'friendly_name') or component_name"
            if chars is None:
                src = "{{ " + name + " }}"
            else:
                src = "{%- set n = (" + name + ") | string -%}"
                src += cut_to_fit_template(chars, width)
            slot = self._template_slot(src, {})
            slot["variables"]["component_name"] = self.component["name"]
            if chars is not None:
                slot["variables"]["name_w"] = dict(NAME_W)
            return {"s": self._add_slot(slot)}
        name = self.component["name"]
        return name if chars is None else cut_to_fit(name, chars, width)

    def _header_icon(self) -> str | None:
        """Return the header icon: the person's, the device's, else the file's."""
        param = self._first_entity()
        spec = self.component["params"].get(param) if param else None
        # A card about several devices, or one that names itself after
        # something else (a room), is not drawn with the first device's icon.
        own = self.can.get("icon")
        if (spec is not None and spec["multiple"]) or self.component.get("title_input"):
            own = None
        for icon in (
            self.standard.get("icon"),
            own,
            self.component["icon"],
        ):
            if isinstance(icon, str) and _ICON.match(icon):
                return icon
        return None

    def _live_icon(self) -> Any:
        """Return the live icon of the card, from a state_icon input.

        Only when the person did not pick an icon: theirs stays.
        """
        if self.standard.get("icon"):
            return None
        first = self._first_entity()
        for name, spec in self.component["inputs"].items():
            if spec["kind"] == "state_icon" and spec["param"] == first:
                return self._bind_input(name, {}, "icon")
        return None

    def _unavailable(self) -> Any:
        """Return the card's `un`: the file's input, else the first device's state."""
        if self.component["unavailable"] is not None:
            return self._bind(self.component["unavailable"], {}, "bool")
        if self.demo:
            return None
        param = self._first_entity()
        if param is None:
            return None
        target = param + "[0]" if self.component["params"][param]["multiple"] else param
        src = "{{ states(" + target + ") in ['unavailable', 'unknown'] }}"
        return {"s": self._add_slot(self._template_slot(src, {}))}

    # ------------------------------------------------------------ taps

    def _offered(self, choice: dict) -> bool:
        """Return whether a tap choice is offered: its `needs` holds."""
        return not choice["needs"] or term_holds(choice["needs"], self.names)

    def _output_reaches(self, name: str, item_vars: dict) -> bool:
        """Return whether an output has an action for the devices it acts on.

        An action per kind leaves out a device whose kind has no entry
        (C.2.8). Devices an `entities` input gives are known only at the call.
        """
        output = self.component["outputs"][name]
        if output["kind"] != "action" or output["actions"] is None:
            return True
        target = self.param_vars.get(output["entity_ref"])
        if target is None:
            target = item_vars.get(output["entity_ref"])
        if target is None:
            return output["entity_ref"] in self.component["inputs"]
        ids = target if isinstance(target, list) else [target]
        return any(
            isinstance(entity, str) and entity.split(".", 1)[0] in output["actions"]
            for entity in ids
        )

    def _card_tap(self) -> tuple[dict | None, str | None]:
        """Return the card's tap, and the output a trailing switch runs."""
        tap = self.component["tap"]
        if tap is None:
            return None, None
        choices = [c for c in tap["choices"] if self._offered(c)]
        choices = [
            c
            for c in choices
            if "output" not in c or self._output_reaches(c["output"], {})
        ]
        toggle = None
        chosen_value = self.standard.get("tap")
        chosen = next((c for c in choices if c["value"] == chosen_value), None)
        for choice in ([chosen] + choices) if chosen else choices:
            output = choice.get("output")
            if output and self.component["outputs"][output]["kind"] == "action":
                toggle = output
                break
        if self.detail_copy:
            return None, toggle
        if chosen_value == "page":
            page = self.standard.get("tap_page")
            if not page:
                return None, toggle
            return {"tap": {"local": "go_to_page", "page": page}}, toggle
        if chosen is None or (chosen["value"] == "none" and "output" not in chosen):
            return None, toggle
        if "output" not in chosen:
            if chosen["value"] == "detail" and self._detail():
                self.opener = True
                return {"tap": {"local": "detail"}}, toggle
            return None, toggle
        if self._would_ask(chosen["output"]):
            # A wipe over a tile must never open a question (C.2.8).
            self.tap_left_out = True
            return None, toggle
        result = self._tap_of(chosen["output"], "card", {})
        if result is None:
            return None, toggle
        out: dict = {"tap": result}
        output = self.component["outputs"][chosen["output"]]
        if output["kind"] == "action" and self.standard.get("ask"):
            out["confirm"] = chosen["label"] + "?"
        return out, toggle

    def _would_ask(self, name: str) -> bool:
        """Return whether a card tap on this output would ask first.

        A cover of class garage, gate or door asks; the facts say which
        (`asks`). Devices an `entities` input gives are known only at the
        call, so a cover output fed by one counts as asking.
        """
        output = self.component["outputs"][name]
        if output["kind"] != "action":
            return False
        domains = (
            list(output["actions"])
            if output["actions"] is not None
            else [output["action"].split(".", 1)[0]]
        )
        target = self.param_vars.get(output["entity_ref"])
        if target is None:
            return "cover" in domains
        ids = target if isinstance(target, list) else [target]
        for entity in ids:
            if not isinstance(entity, str):
                continue
            domain = entity.split(".", 1)[0]
            if domain not in domains:
                continue
            known = self.facts.get(entity)
            if domain == "cover" and isinstance(known, dict) and known.get("asks"):
                return True
        return False

    def _card_hold(self) -> dict | None:
        """Return the card's hold: open its detail page, unless switched off."""
        if self.detail_copy or self.component["hold"] != "detail":
            return None
        if not self._detail() or not self.standard.get("hold", True):
            return None
        self.opener = True
        return {"local": "detail"}

    def _tap_of(self, name: str, key: str, item_vars: dict) -> dict | None:
        """Build the tap of an output, recording an action under key."""
        if name == "detail":
            if self.detail_copy or not self._detail():
                return None
            self.opener = True
            return {"local": "detail"}
        output = self.component["outputs"][name]
        if output["kind"] == "action":
            self.actions[f"{key}:tap"] = self._action(name, item_vars)
            return {"policy": output["feedback"]}
        local = output["local"]
        if local == "detail":
            if self.detail_copy or not self._detail():
                return None
            self.opener = True
            return {"local": "detail"}
        if local == "back":
            return {"local": "back"}
        tap: dict = {"local": local}
        if local in ("open_details", "open_live"):
            param = self._first_entity()
            value = self.param_vars.get(param) if param else None
            if isinstance(value, str):
                tap["entity"] = value
        elif local == "go_to_page":
            page = output["page"] or ""
            match = re.fullmatch(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}", page)
            if match:
                page = str(self.param_vars.get(match.group(1)) or "")
            if not page:
                return None
            tap["page"] = page
        return tap

    def _action(self, name: str, names: dict) -> dict:
        """Return what a call needs besides the output (C.2.8).

        vars: the item's loop names and `vars`. values: the options and the
        facts, which a data template may read. uses: per input the output
        lists, its type and the slot that gives Home Assistant's own last
        value; the call reads it from the slot hub, never from the message.
        All of it is data. values and uses reach the bindings through the
        compiled card's "call" entry, keyed like the actions.
        """
        output = self.component["outputs"][name]
        action: dict = {"output": name, "vars": dict(names)}
        if output["kind"] != "action":
            return action
        uses = {}
        for input_name, kind in (output.get("uses") or {}).items():
            uses[input_name] = {
                "type": kind,
                "slot": self._input_slot(input_name, names),
            }
        if uses:
            # Kept beside the action under the same key; see run().
            self.uses[id(action)] = uses
        return action

    def _call(self) -> dict:
        """Return what the calls of this card read besides the output."""
        return {
            "values": {"options": dict(self.options), "can": self.can},
            "uses": {
                key: self.uses[id(action)]
                for key, action in self.actions.items()
                if id(action) in self.uses
            },
        }

    def _input_slot(self, name: str, names: dict) -> dict | None:
        """Return the slot of an input without adding it to the card's slots."""
        spec = self.component["inputs"][name]
        source = spec["kind"]
        if self.demo:
            return None
        if source in ("template", "camera"):
            return self._template_slot("{{ " + name + " }}", names)
        if source == "clock":
            return {"kind": "clock"}
        entity = self._entity_of(spec["param"], names)
        if entity is None:
            return None
        if source == "action":
            # One slot per loop copy: the copy's names are among the
            # variables its result renders with. Slots with the same action
            # and data share one call in Home Assistant (C.2.8).
            return {
                "kind": "action",
                "action": spec["action"],
                "data": {**spec["data"], "entity_id": entity},
                "result": spec["result"],
                "variables": self._variables(names),
                "refresh": spec["refresh"],
            }
        if source == "history":
            return {"kind": "history", "entity": entity, "hours": spec["hours"]}
        if source == "colour":
            return {"kind": "colour", "entity": entity, "of": spec["of"]}
        if source == "statistics":
            return {
                "kind": "statistics",
                "entity": entity,
                **{k: v for k, v in spec.items() if k not in ("kind", "param")},
            }
        return {"kind": source, "entity": entity}

    # ------------------------------------------------------------ layout

    def _trailing(self, variant: dict) -> tuple[str, dict] | None:
        """Return what a tile header shows at its right, as geometry names it."""
        trailing = variant["trailing"]
        if trailing is None or variant["header"] not in ("tile", "tile_v"):
            return None
        form = trailing["form"]
        if form == "more" and (self.detail_copy or not self._detail()):
            return None
        if form == "input":
            return "text", trailing
        return form, trailing

    def _loop_entries(self, loop: dict) -> list[dict]:
        """Return the names each copy of a loop gets, at most its `at_most`."""
        return self._all_loop_entries(loop)[: loop.get("at_most", MAX_COPIES)]

    def _all_loop_entries(self, loop: dict) -> list[dict]:
        """Return the names each copy of a loop gets."""
        kind = loop["kind"]
        as_name = loop["as"]
        if kind == "param":
            value = self.param_vars.get(loop["name"])
            ids = value if isinstance(value, list) else []
            entries = []
            for entity in ids[:MAX_COPIES]:
                known = self.facts.get(entity)
                facts = dict(known) if isinstance(known, dict) else None
                if facts is None:
                    facts = facts_of({"domain": entity.split(".", 1)[0]})
                entries.append({as_name: entity, f"{as_name}_can": facts})
            return entries
        if kind == "fact":
            listed = self.names.get(loop["name"])
        elif kind == "option":
            listed = self.options.get(loop["name"])
        else:
            listed = loop["entries"]
        listed = listed if isinstance(listed, list) else []
        return [{as_name: entry} for entry in listed[:MAX_COPIES]]

    def _expand(self, layout: list) -> list[dict]:
        """Apply `when`, expand loops and return the card's rows.

        Each row is {"kind": "row" | "swap" | "space", "cells": ..., "height"}.
        A row's cells are (item, names) pairs; a swap's cells are members,
        each a list of such pairs. Widgets are counted as they come; the
        count stops at the limit.
        """
        rows: list[dict] = []
        self._count = 0
        for item in layout:
            if not when_holds(item.get("when"), self.names):
                continue
            kind = item["type"]
            if kind == "space":
                rows.append(
                    {"kind": "space", "cells": [], "height": item.get("height")}
                )
            elif kind == "swap":
                members = []
                for member in item["items"]:
                    if not when_holds(member.get("when"), self.names):
                        continue
                    if member["type"] == "row":
                        cells = self._row_cells(member, {})
                    else:
                        cells = self._take(self._widget_copies(member, {}))
                    if cells:
                        members.append(cells)
                if members:
                    rows.append(
                        {"kind": "swap", "cells": members, "height": item.get("height")}
                    )
            elif kind == "row":
                copies = self._loop_entries(item["loop"]) if "loop" in item else [{}]
                for names in copies:
                    cells = self._row_cells(item, names)
                    if cells:
                        rows.append(
                            {
                                "kind": "row",
                                "cells": cells,
                                "height": item.get("height"),
                            }
                        )
            else:
                copies = self._widget_copies(item, {})
                per_row = item["loop"]["per_row"] if "loop" in item else 1
                if item.get("loop", {}).get("two_rows") and 3 <= len(copies) <= per_row:
                    # Few copies: two rows of wider cells, not one row of
                    # narrow cells under an empty half.
                    per_row = -(-len(copies) // 2)
                for start in range(0, len(copies), per_row):
                    cells = self._take(copies[start : start + per_row])
                    if cells:
                        rows.append({"kind": "row", "cells": cells, "height": None})
        return rows

    def _row_cells(self, row: dict, names: dict) -> list:
        """Return the widgets of a row, with its loop names and its `visible`."""
        cells = []
        for child in row["items"]:
            if not when_holds(child.get("when"), self.names):
                continue
            for copy in self._widget_copies(child, names):
                if "visible" in row and "visible" not in copy[0]:
                    copy = ({**copy[0], "visible": row["visible"]}, copy[1])
                cells.append(copy)
        if len(cells) > MAX_ROW_WIDGETS:
            cells = cells[:MAX_ROW_WIDGETS]
            self.cut = True
        return self._take(cells)

    def _widget_copies(self, item: dict, names: dict) -> list:
        """Return a widget once, or once per entry of its loop."""
        base = {**names, **(item.get("vars") or {})}
        if "loop" not in item:
            return [(item, base)]
        return [(item, {**base, **entry}) for entry in self._loop_entries(item["loop"])]

    def _take(self, cells: list) -> list:
        """Count widgets against the limit of a card; cut what is over it."""
        room = MAX_WIDGETS_2 - self._count
        if len(cells) > room:
            cells = cells[: max(room, 0)]
            self.cut = True
        self._count += len(cells)
        return cells

    def _geo(self, item: dict, names: dict) -> dict:
        """Build the geometry input of one widget."""
        kind = item["type"]
        geo: dict = {"type": kind}
        for key in ("height", "grow", "width", "weight"):
            if item.get(key) is not None:
                geo[key] = item[key]
        if kind == "label":
            geo["size"] = item["size"]
        if item.get("look") is not None:
            geo["look"] = item["look"]
        if item.get("side"):
            geo["side"] = True
        if kind == "choice":
            geo["rows"] = item["rows"]
            geo["options"] = len(self._choice_list(item, names)["values"])
        geo["control"] = bool(
            kind == "button" or item.get("on_tap") or item.get("on_change")
        )
        return geo

    def _geo_row(self, row: dict) -> dict:
        """Build the geometry input of one row."""
        out = {"kind": row["kind"], "height": row.get("height")}
        if row["kind"] == "swap":
            out["cells"] = [
                [self._geo(i, n) for i, n in member] for member in row["cells"]
            ]
        else:
            out["cells"] = [self._geo(i, n) for i, n in row["cells"]]
        return out

    # ------------------------------------------------------------ widgets

    def _next(self, widget: dict) -> dict:
        """Give a widget its index and keep it."""
        widget["i"] = len(self.widgets)
        self.widgets.append(widget)
        return widget

    def _header_widgets(
        self,
        form: str,
        parts: dict,
        trailing: tuple | None,
        title: Any,
        icon: str | None,
        ic: Any,
        tint: Any,
        toggle: str | None,
    ) -> None:
        """Compile a chip, tile or tile_v header into ordinary widgets."""
        if form == "none":
            return
        shown = ic if ic is not None else icon
        if "icon" in parts:
            self._next({"t": "image", "r": parts["icon"], "value": shown, "look": 2})
        if "badge" in parts:
            badge = {"t": "image", "r": parts["badge"], "value": shown, "look": 1}
            if tint is not None:
                badge["c"] = tint
            self._next(badge)
        if "name" in parts:
            self._next({"t": "label", "r": parts["name"], "text": title, "size": "m"})
        own = self._variant_state
        if own is None:
            state = self._bind(self.component["state"], {}, "text")
        elif own["form"] == "none":
            state = None
        else:
            state = self._bind_input(own["input"], {}, "text")
        if "state" in parts and state is not None:
            state_label = {
                "t": "label",
                "r": parts["state"],
                "text": state,
                "size": "s",
            }
            if form == "chip":
                state_label["al"] = ALIGN.index("right")
            self._next(state_label)
        if trailing is None or "trailing" not in parts:
            return
        kind, spec = trailing
        rect = parts["trailing"]
        if kind == "switch":
            switch = {"t": "switch", "r": rect, "value": self.on}
            if toggle is not None:
                index = len(self.widgets)
                tap = self._tap_of(toggle, str(index), {})
                if tap is not None:
                    switch["tap"] = tap
            self._next(switch)
        elif kind == "more":
            self._next(
                {
                    "t": "button",
                    "r": rect,
                    "icon": MORE_ICON,
                    "shape": SHAPES.index("bare"),
                    "tap": {"local": "detail"},
                }
            )
            self.opener = True
        else:
            text = self._bind_input(spec["input"], {}, "text")
            self._next(
                {
                    "t": "label",
                    "r": rect,
                    "text": text,
                    "size": "s",
                    "al": ALIGN.index("right"),
                }
            )

    def _body_widgets(self, body: list, laid: dict) -> None:
        """Compile the widgets of every row that has a place."""
        for row, rects, rows in zip(body, laid["rects"], laid["rows"], strict=True):
            if rects is None or row["kind"] == "space":
                continue
            members = row["cells"] if row["kind"] == "swap" else [row["cells"]]
            for member, member_rects, member_rows in zip(
                members, rects, rows, strict=True
            ):
                for (item, names), rect, choice_rows in zip(
                    member, member_rects, member_rows, strict=True
                ):
                    if rect is None:
                        continue
                    self._widget(item, names, rect, choice_rows)

    def _widget(self, item: dict, names: dict, rect: list, rows: int | None) -> None:
        """Compile one widget of the body."""
        kind = item["type"]
        for trigger in ("on_tap", "on_change"):
            name = item.get(trigger)
            if name and name != "detail" and not self._output_reaches(name, names):
                return
        widget: dict = {"t": kind, "r": rect}
        build = getattr(self, f"_w_{kind}")
        if build(widget, item, names, rows) is False:
            return
        if "visible" in item:
            widget["vis"] = self._bind(item["visible"], names, "bool")
        if "colour" in item:
            colour = self._bind(item["colour"], names, "colour")
            if colour is not None:
                widget["c"] = colour
        index = len(self.widgets)
        on_tap = item.get("on_tap")
        if on_tap:
            tap = self._tap_of(on_tap, str(index), names)
            if tap is not None:
                widget["tap"] = tap
        on_change = item.get("on_change")
        if on_change:
            output = self.component["outputs"][on_change]
            widget["change"] = {"policy": output["feedback"]}
            action = self._action(on_change, names)
            if kind == "choice":
                action["options"] = self._choice_list(item, names)["values"]
            self.actions[f"{index}:change"] = action
        if item.get("confirm") is not None and ("tap" in widget or "change" in widget):
            widget["confirm"] = self._bind(item["confirm"], names, "text")
        if item.get("on_hold") == "detail" and not self.detail_copy and self._detail():
            widget["hold"] = {"local": "detail"}
            self.opener = True
        self._next(widget)

    def _w_label(self, widget: dict, item: dict, names: dict, rows) -> bool:
        size = item["size"]
        if size in LABEL_PX:
            widget["px"] = LABEL_PX[size]
        else:
            widget["size"] = size
        if "text" in item:
            widget["text"] = self._bind(item["text"], names, "text")
        if item.get("align") is not None:
            widget["al"] = ALIGN.index(item["align"])
        if item.get("clock") is not None:
            widget["clk"] = 1 if item["clock"] == 24 else 2
            widget["value"] = self._bind(item["value"], names, "number")
        return True

    def _w_button(self, widget: dict, item: dict, names: dict, rows) -> bool:
        if "text" in item:
            widget["text"] = self._bind(item["text"], names, "text")
        if "icon" in item:
            icon = self._bind(item["icon"], names, "icon")
            if icon is not None:
                widget["icon"] = icon
        if "text" not in widget and "icon" not in widget:
            return False
        if "icon_live" in item:
            widget["ic"] = self._bind(item["icon_live"], names, "icon")
        rect = widget["r"]
        if widget.get("text") is not None and button_text_alone(rect[2], rect[3]):
            # Beside the icon the text would be cut to a few letters.
            widget.pop("icon", None)
            widget.pop("ic", None)
        if "selected" in item:
            widget["value"] = self._bind(item["selected"], names, "bool")
        if item.get("shape") is not None:
            widget["shape"] = SHAPES.index(item["shape"])
        if item.get("big_icon"):
            widget["isz"] = 1
        return True

    def _w_switch(self, widget: dict, item: dict, names: dict, rows) -> bool:
        widget["value"] = self._bind(item["value"], names, "bool")
        return True

    def _ranged(self, widget: dict, item: dict, names: dict, step: float) -> None:
        widget["value"] = self._bind(item["value"], names, "number")
        for key in ("min", "max", "step"):
            value = self._bind(item[key], names, "number")
            if value is not None:
                widget[key] = value

    def _w_slider(self, widget: dict, item: dict, names: dict, rows) -> bool:
        self._ranged(widget, item, names, 1)
        if item.get("look") is not None:
            widget["look"] = SLIDER_LOOKS.index(item["look"])
        if item.get("direction") is not None:
            widget["dir"] = DIRS.index(item["direction"])
        if "track" in item:
            track = self._track(item["track"], names)
            if track:
                widget["track"] = track
        if "icon" in item:
            icon = self._bind(item["icon"], names, "icon")
            if icon is not None:
                widget["icon"] = icon
        if item.get("keep_active"):
            widget["nv"] = 1
        if "rate" in item:
            widget["rate"] = self._bind(item["rate"], names, "number")
        return True

    def _w_thermostat(self, widget: dict, item: dict, names: dict, rows) -> bool:
        self._ranged(widget, item, names, 0.5)
        if "mark" in item:
            widget["mark"] = self._bind(item["mark"], names, "number")
        if "buttons" in item:
            widget["bs"] = item["buttons"]
        return True

    def _w_chart(self, widget: dict, item: dict, names: dict, rows) -> bool:
        widget["value"] = self._bind(item["value"], names, "list")
        if item["kind"] == "steps":
            widget["kind"] = "line"
            widget["st"] = 1
        else:
            widget["kind"] = item["kind"]
        if "mark" in item:
            widget["mark"] = self._bind(item["mark"], names, "number")
        return True

    def _w_image(self, widget: dict, item: dict, names: dict, rows) -> bool:
        widget["value"] = self._bind(item["value"], names, "icon")
        if item.get("look") is not None:
            widget["look"] = IMAGE_LOOKS.index(item["look"])
        return True

    def _w_choice(self, widget: dict, item: dict, names: dict, rows) -> bool:
        options = self._choice_list(item, names)
        if not options["values"]:
            # HA never sends a choice with no option (contract 4.3).
            return False
        for key in ("texts", "icons", "cols"):
            if options[key] is not None:
                widget[key] = options[key]
        if item.get("value") is not None:
            widget["value"] = self._bind(item["value"], names, "number")
        widget["rows"] = rows or item["rows"]
        if item["look"] != "cells":
            widget["look"] = CHOICE_LOOKS.index(item["look"])
        return True

    def _track(self, track: dict, names: dict) -> list | None:
        """Return the colours of a slider's track, as constants."""
        if track["kind"] == "kelvin":
            low, high = (self._bind(end, names, "number") for end in track["kelvin"])
            if not isinstance(low, int | float) or not isinstance(high, int | float):
                return None
            if isinstance(low, bool) or isinstance(high, bool) or low >= high:
                return None
            return kelvin_track(low, high)
        return [self._colour_constant(colour) for colour in track["colours"]]

    def _choice_list(self, item: dict, names: dict) -> dict:
        """Return a choice's lists for the layout and its values for the server.

        The values are kept whole; the tablet's texts are cut to 40 bytes
        when the device layout is written.
        """
        spec = item["options"]
        texts = icons = cols = None
        values: list = []
        if spec["kind"] == "list":
            entries = spec["entries"]
            if any("text" in e for e in entries):
                texts = [
                    self._bind(e["text"], names, "text") if "text" in e else ""
                    for e in entries
                ]
            if any("icon" in e for e in entries):
                icons = [
                    (self._bind(e["icon"], names, "icon") or "") if "icon" in e else ""
                    for e in entries
                ]
            if any("colour" in e for e in entries):
                cols = [
                    self._colour_constant(e["colour"]["value"])
                    if "colour" in e
                    else self.roles["muted"]
                    for e in entries
                ]
            for index, entry in enumerate(entries):
                if "value" in entry:
                    values.append(entry["value"])
                elif (
                    texts is not None and isinstance(texts[index], str) and texts[index]
                ):
                    values.append(texts[index])
                else:
                    values.append(index)
        elif spec["kind"] == "fact":
            listed = self.names.get(spec["fact"])
            listed = listed if isinstance(listed, list) else []
            values = [entry for entry in listed[:MAX_COPIES] if isinstance(entry, str)]
            texts = list(values)
        else:
            option = self.component["options"][spec["option"]]
            chosen = self.options.get(spec["option"])
            chosen = chosen if isinstance(chosen, list) else []
            chosen = chosen[:MAX_COPIES]
            if option["type"] == "colours":
                cols = []
                for entry in chosen:
                    match = _KELVIN.match(entry)
                    if match:
                        kelvin = int(match.group(1))
                        cols.append(_hex(kelvin_rgb(kelvin)))
                        values.append({"rgb": None, "kelvin": kelvin})
                    else:
                        cols.append(entry.upper())
                        values.append(
                            {
                                "rgb": [int(entry[i : i + 2], 16) for i in (1, 3, 5)],
                                "kelvin": None,
                            }
                        )
            else:
                labels = {c["value"]: c["label"] for c in option.get("choices") or []}
                values = [entry for entry in chosen if isinstance(entry, str)]
                texts = [labels.get(entry, entry) for entry in values]
        return {"texts": texts, "icons": icons, "cols": cols, "values": values}

    # ------------------------------------------------------------ binding

    def _variables(self, names: dict) -> dict:
        """Return the variables a template of this card gets: all of it data."""
        return {
            **self.param_vars,
            **self.options,
            "can": self.can,
            "has": self.has,
            **names,
        }

    def _colour_constant(self, value: object) -> str | None:
        """Return a constant colour: #RRGGBB, with a role turned into its colour."""
        if isinstance(value, int) and not isinstance(value, bool):
            return (
                _hex([value >> 16, (value >> 8) & 255, value & 255])
                if (0 <= value <= 0xFFFFFF)
                else None
            )
        if isinstance(value, str):
            if value in COLOUR_ROLES:
                return self.roles.get(value)
            if _HEX.match(value):
                return value.upper()
        return None

    def _lookup(self, name: str, key: str | None, names: dict) -> Any:
        """Look a value up when the layout is made. No Jinja."""
        if name == "can":
            value: Any = self.can
        elif name in names:
            value = names[name]
        elif name in self.options:
            value = self.options[name]
        else:
            return None
        if key is None:
            return value
        return value.get(key) if isinstance(value, dict) else None

    def _typed(self, value: Any, kind: str) -> Any:
        """Turn a looked-up value into a constant of the field's type."""
        if kind == "text":
            if value is None:
                return ""
            if isinstance(value, bool):
                return "Yes" if value else "No"
            if isinstance(value, int | float):
                return str(_constant(value))
            return value if isinstance(value, str) else ""
        if kind == "number":
            if isinstance(value, bool) or not isinstance(value, int | float):
                return None
            return _constant(value) if math.isfinite(value) else None
        if kind == "bool":
            return truthy(value)
        if kind == "colour":
            return self._colour_constant(value)
        if kind == "icon":
            return value if isinstance(value, str) and _ICON.match(value) else None
        if kind == "list":
            if isinstance(value, list) and all(
                isinstance(v, int | float) and not isinstance(v, bool) for v in value
            ):
                return [_constant(v) for v in value]
            return []
        return value

    def _bind(self, mark: dict | None, names: dict, kind: str) -> Any:
        """Compile one marked field to a constant or a slot reference."""
        if mark is None:
            return None
        form = mark["form"]
        if form == "const":
            value = mark["value"]
            if kind == "colour":
                return self._colour_constant(value)
            if kind == "text" and not isinstance(value, str):
                return self._typed(value, "text")
            return _constant(value)
        if form == "lookup":
            return self._typed(self._lookup(mark["name"], mark["key"], names), kind)
        if form == "template":
            ref: dict = {
                "s": self._add_slot(self._template_slot(mark["template"], names))
            }
            if kind == "colour":
                ref["roles"] = dict(sorted(self.roles.items()))
            return ref
        return self._bind_input(mark["input"], names, kind)

    def _entity_of(self, param: str, names: dict) -> Any:
        """Return the entity id behind an input's param or loop name."""
        value = self.param_vars.get(param)
        if value is None:
            value = names.get(param)
        return value if isinstance(value, str) else None

    def _bind_input(self, name: str, names: dict, kind: str) -> Any:
        """Compile a reference to a declared input."""
        spec = self.component["inputs"][name]
        source = spec["kind"]
        if self.demo and name in self.preview["inputs"]:
            value = self.preview["inputs"][name]
            if kind == "colour":
                return self._colour_constant(value)
            return _constant(value)
        if source in ("template", "camera"):
            slot = self._template_slot("{{ " + name + " }}", names)
            ref: dict = {"s": self._add_slot(slot)}
            if kind == "colour" and source == "template":
                ref["roles"] = dict(sorted(self.roles.items()))
            return ref
        if self.demo:
            listed = source == "history" or (
                source == "statistics" and "buckets" in spec
            )
            return [] if listed else None
        slot = self._input_slot(name, names)
        if slot is None:
            return None
        return {"s": self._add_slot(slot)}

    def _template_slot(self, src: str, names: dict) -> dict:
        """Build a template slot, inlining the inputs the source mentions.

        src is always the card file's own text. Everything else reaches the
        template as a variable.
        """
        inputs = self.component["inputs"]
        preview = self.preview["inputs"] if self.demo else {}
        used = self._used_inputs(src, inputs, preview)
        template = "".join(_prelude(name, _source(inputs[name])) for name in used)
        template += src
        variables = self._variables(names)
        for name, value in preview.items():
            if _mentions(name, src) or any(
                _mentions(name, _source(inputs[other])) for other in used
            ):
                variables[name] = value
        slot: dict = {"kind": "template", "template": template, "variables": variables}
        feeds = {}
        for name in self._fed_inputs(src, used, preview):
            feed = self._input_slot(name, names)
            if feed is not None:
                feeds[name] = feed
        if feeds:
            # Fetched in Home Assistant and handed to the template as
            # variables (C.2.8): data, never template source.
            slot["inputs"] = feeds
        return slot

    def _fed_inputs(self, src: str, used: list, preview: dict) -> list:
        """Return the history, statistics and action inputs a template names.

        Named by the source itself or by a template input it uses, in
        declaration order. An example card shows their preview values.
        """
        inputs = self.component["inputs"]
        texts = [src, *(_source(inputs[name]) for name in used)]
        return [
            name
            for name, spec in inputs.items()
            if spec["kind"] in ("history", "statistics", "action")
            and name not in preview
            and any(_mentions(name, text) for text in texts)
        ]

    @staticmethod
    def _used_inputs(src: str, inputs: dict, preview: dict) -> list:
        """Collect mentioned template or camera inputs in declaration order."""
        found: set = set()
        queue = [src]
        while queue:
            text = queue.pop()
            for name, spec in inputs.items():
                if (
                    name in found
                    or name in preview
                    or spec["kind"] not in ("template", "camera")
                    or not _mentions(name, text)
                ):
                    continue
                found.add(name)
                queue.append(_source(spec))
        return [name for name in inputs if name in found]

    def _add_slot(self, slot: dict) -> int:
        """Return a slot's number, reusing the number of an identical one."""
        key = json.dumps(slot, sort_keys=True, default=str)
        if key in self._slot_keys:
            return self._slot_keys[key]
        number = len(self.slots) + 1
        self._slot_keys[key] = number
        self.slots.append({"n": number, **slot})
        return number
