"""Validator for card files of schema 2.

Schema 1 files keep their own validator in schema.py, unedited. A schema 2
file adds options, `when`, parts, variants, rows, swaps, loops over facts,
options and lists, and typed inputs in service data (C.2 of the cards spec).

Whether a field is a template is decided here, once, on the file's own
text. Each such field is stored with the form it was found in, and the
compiler binds by that mark, never by looking into a value:

- ``{"form": "const", "value": v}``: plain text, a number, yes or no.
- ``{"form": "lookup", "name": n, "key": k}``: exactly ``{{ name }}`` or
  ``{{ name.key }}`` where the name is ``can``, an option, a ``vars`` name,
  a loop over a fact, an option or a list in the file, or ``<as>_can`` of a
  loop over devices. It is looked up when the layout is made; no Jinja.
- ``{"form": "template", "template": t}``: any other text with ``{{`` or
  ``{%``. It is rendered in Home Assistant's sandbox.
- ``{"form": "input", "input": n}``: the name of an input; a live slot.

Nothing here renders, and nothing expands a loop: widgets are counted from
the largest number of copies each loop can make, as the walk goes, and the
walk stops at the limit.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator

from .const import (
    ACTION_RE,
    ALLOWED_SERVICES,
    CARD_GROUPS,
    CHOICE_KEY_RE,
    COLOUR_DATA_KEYS,
    COLOUR_ROLES,
    DATA_KEY_RE,
    DOMAIN_RE,
    FEEDBACK_MODES,
    HEADER_FORMS,
    ID_RE,
    KELVIN_RANGE,
    KELVIN_RE,
    LABEL_SIZES_2,
    LIT_LOOKS,
    LOCAL_ACTIONS_2,
    MAX_CHOICE_OPTIONS_2,
    MAX_CHOICES_2,
    MAX_COLOURS_2,
    MAX_DATA_KEYS,
    MAX_HELP_2,
    MAX_INPUTS_2,
    MAX_LABEL_2,
    MAX_LOOP_COPIES_2,
    MAX_MULTIPLE_2,
    MAX_NOTES_2,
    MAX_OPTIONS_2,
    MAX_OUTPUTS_2,
    MAX_PARAMS_2,
    MAX_PARTS_2,
    MAX_REPLACES_2,
    MAX_ROW_ITEMS_2,
    MAX_TEXT_OPTION_2,
    MAX_TRACK_2,
    MAX_VARIANT_ITEMS_2,
    MAX_VARIANTS_2,
    MAX_WHEN_TERMS,
    MAX_WIDGETS_2,
    NAME_RE,
    OPTION_SECTIONS,
    OPTION_TYPES,
    PAGE_PATH_RE,
    REF_RE,
    RESERVED_NAMES_2,
    SENSITIVE_DOMAINS,
    STANDARD_OPTIONS_2,
    TARGET_KEYS,
    USES_TYPES,
    VAR_RE,
    VERSION_RE,
    WHEN_VALUE_RE,
)
from .errors import MakerError
from .features import FACT_NAMES
from .outputs import reference
from .schema import (
    _as_mapping,
    _as_number,
    _check_text,
    _is_plain_number,
    _is_template,
    _reject_unknown_keys,
    _required,
    _validate_action_input as _schema1_action_input,
    _validate_camera_input,
    _validate_history_input,
    _validate_icon,
)

_ACTION = re.compile(ACTION_RE)
_CHOICE_KEY = re.compile(CHOICE_KEY_RE)
_DATA_KEY = re.compile(DATA_KEY_RE)
_DOMAIN = re.compile(DOMAIN_RE)
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ID = re.compile(ID_RE)
_KELVIN = re.compile(KELVIN_RE)
_NAME = re.compile(NAME_RE)
_PAGE_PATH = re.compile(PAGE_PATH_RE)
_REF = re.compile(REF_RE)
_VAR = re.compile(VAR_RE)
_VERSION = re.compile(VERSION_RE)
_WHEN_VALUE = re.compile(WHEN_VALUE_RE)
_FACT = re.compile(r"^can\.([a-z][a-z0-9_]*)(?:\.([a-z][a-z0-9_]*))?$")
_SIZE = re.compile(r"^([1-6])x([1-4])$")
_TERM = re.compile(
    r"^(!)?([a-z][a-z0-9_]*(?:\.[a-z0-9][a-z0-9_]*){0,2})"
    r"(?:(=|!=)([a-z0-9_]+(?:\|[a-z0-9_]+)*))?$"
)

_TOP_KEYS = {
    "schema",
    "id",
    "version",
    "name",
    "description",
    "icon",
    "group",
    "replaces",
    "v1",
    "params",
    "options",
    "inputs",
    "outputs",
    "on",
    "tint",
    "state",
    "unavailable",
    "lit",
    "tap",
    "hold",
    "parts",
    "variants",
    "detail",
    "preview",
    "notes",
    # One variant, "default", written at the top of the file.
    "layout",
    "size",
    "header",
    "trailing",
    "align",
}

# Keys every widget may carry, then the keys of each type. `colour` is not
# offered on a choice and `on_hold` only where contract v2 has `hold`.
_WIDGET_COMMON = {
    "type",
    "when",
    "visible",
    "vars",
    "height",
    "grow",
    "width",
    "weight",
    "for_each",
    "as",
    "per_row",
    "use",
}
_WIDGET_KEYS = {
    "label": {"text", "size", "align", "clock", "value", "on_tap", "confirm"},
    "button": {
        "text",
        "icon",
        "on_tap",
        "confirm",
        "selected",
        "icon_live",
        "shape",
        "big_icon",
    },
    "switch": {"value", "on_tap"},
    "slider": {
        "value",
        "min",
        "max",
        "step",
        "on_change",
        "look",
        "direction",
        "track",
        "icon",
        "keep_active",
        "rate",
    },
    "thermostat": {
        "value",
        "min",
        "max",
        "step",
        "on_change",
        "side",
        "mark",
        "buttons",
    },
    "chart": {"value", "kind", "side", "mark"},
    "image": {"value", "on_tap", "confirm", "side", "look"},
    "choice": {"value", "options", "rows", "look", "on_change", "confirm"},
}
_HOLD_TYPES = {"label", "button", "switch", "chart", "image"}
_COLOUR_TYPES = set(_WIDGET_KEYS) - {"choice"}
_CONTAINERS = {"row", "swap", "space"}
_LOOKS = {
    "slider": ("knob", "bar"),
    "image": ("box", "badge", "bare"),
    "choice": ("cells", "dots"),
}
_TRAILING_FORMS = ("switch", "more", "none")
_HUE_TRACK = (
    "#FF0000",
    "#FFFF00",
    "#00FF00",
    "#00FFFF",
    "#0000FF",
    "#FF00FF",
    "#FF0000",
)
# Output names an item uses for the detail page itself.
_ITEM_WORDS = frozenset({"detail", "back"})
_PAGE_CHOICE = {"value": "page", "label": "Goes to a page", "needs": ""}
_BAD_NESTING = "bad_nesting"


def _const(value: object) -> dict:
    """Return a constant mark."""
    return {"form": "const", "value": value}


def _text(value: object, path: str, limit: int) -> str:
    """Return a plain text of at most limit characters."""
    if not isinstance(value, str):
        raise MakerError("bad_value", path, "expected a string")
    if len(value) > limit:
        raise MakerError("too_long", path, f"at most {limit} characters")
    return value


def _bool(value: object, path: str) -> bool:
    """Return value when it is a boolean."""
    if not isinstance(value, bool):
        raise MakerError("bad_value", path, "expected true or false")
    return value


def _int(value: object, path: str, low: int, high: int) -> int:
    """Return value when it is a whole number in an inclusive range."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not low <= value <= high
    ):
        raise MakerError("bad_value", path, f"expected a whole number {low}..{high}")
    return value


def _name(name: object, path: str) -> str:
    """Validate a name of a schema 2 file and return it."""
    if not isinstance(name, str) or not _NAME.match(name):
        raise MakerError("bad_name", path, f"bad name {name!r}")
    if name in RESERVED_NAMES_2:
        raise MakerError("bad_name", path, f"name {name!r} is reserved")
    return name


def _component_id(value: object, path: str) -> str:
    """Validate a card id and return it."""
    if not isinstance(value, str) or len(value) > 64 or not _ID.match(value):
        raise MakerError("bad_id", path, f"bad id {value!r}")
    return value


def colour_constant(value: object, path: str) -> str:
    """Return a #RRGGBB colour in upper case, or a role name."""
    if isinstance(value, str):
        if _HEX.match(value):
            return value.upper()
        if value in COLOUR_ROLES:
            return value
    raise MakerError("bad_value", path, f"bad colour {value!r}")


def _colours_entry(value: object, path: str) -> str:
    """Return one entry of a colours list: #RRGGBB, or a white as '2700K'."""
    if isinstance(value, str):
        if _HEX.match(value):
            return value.upper()
        match = _KELVIN.match(value)
        if match is not None:
            low, high = KELVIN_RANGE
            if low <= int(match.group(1)) <= high:
                return value
    raise MakerError("bad_value", path, f"bad colour {value!r}")


def parse_when_term(term: object, path: str) -> dict:
    """Split one `when` term into its parts; raise on a bad shape."""
    if not isinstance(term, str):
        raise MakerError("bad_value", path, "a when term is text")
    match = _TERM.match(term)
    if match is None:
        raise MakerError("bad_value", path, f"bad when term {term!r}")
    negate, name, op, values = match.groups()
    if negate and op:
        raise MakerError("bad_value", path, f"bad when term {term!r}")
    return {
        "name": name,
        "not": bool(negate),
        "op": op,
        "values": values.split("|") if values else [],
    }


class _Ctx:
    """What a file has declared so far, and what the walk has counted."""

    def __init__(self) -> None:
        self.params: dict = {}
        self.options: dict = {}
        self.inputs: dict = {}
        self.outputs: dict = {}
        self.used: set = set()
        self.parts_raw: dict = {}
        self.has_detail = False
        self.loops: dict = {}
        self.vars_names: set = set()
        self.deferred: list = []
        self.widgets = 0


# ---------------------------------------------------------------- facts, when


def _fact(value: object, path: str, ctx: _Ctx) -> str:
    """Validate a fact name, `can.<what>` or `can.<param>.<what>`."""
    if not isinstance(value, str):
        raise MakerError("bad_value", path, "expected a fact like can.brightness")
    match = _FACT.match(value)
    if match is None:
        raise MakerError("bad_value", path, f"bad fact {value!r}")
    _fact_parts(match.group(1), match.group(2), path, ctx)
    return value


def _is_device_param(name: str, ctx: _Ctx) -> bool:
    """Return whether a name is an entity param of the file."""
    param = ctx.params.get(name)
    return param is not None and param["kind"] == "entity"


def _fact_parts(first: str, second: str | None, path: str, ctx: _Ctx) -> None:
    """Check `can.<first>` or `can.<first>.<second>` against the fixed table.

    One name: a fact of the table, or a device param of the file (all its
    facts). Two names: a device param, then a fact of the table.
    """
    if second is None:
        if first in FACT_NAMES or _is_device_param(first, ctx):
            return
        raise MakerError(
            "unknown_fact",
            path,
            f"can.{first} is neither a fact a device can have"
            " nor a device of this card",
        )
    if not _is_device_param(first, ctx):
        raise MakerError("unknown_param", path, f"no device param {first!r}")
    if second not in FACT_NAMES:
        raise MakerError(
            "unknown_fact", path, f"{second!r} is not a fact a device can have"
        )


# `can.<x>` or `can.<param>.<x>` inside a template's text.
_CAN_IN_TEMPLATE = re.compile(
    r"(?<![A-Za-z0-9_.])can\.([a-z][a-z0-9_]*)(?:\.([a-z][a-z0-9_]*))?"
)


def _check_template_facts(doc: dict, ctx: _Ctx) -> None:
    """Check every `can.<x>` a template of the file reads (decision 2).

    A second name is checked only after a device param: after a fact it is
    a method or a key of the fact's own value.
    """
    stack: list[tuple[str, object]] = [
        (key, value) for key, value in doc.items() if key != "preview"
    ]
    while stack:
        path, value = stack.pop()
        if isinstance(value, dict):
            stack.extend((f"{path}.{key}", inner) for key, inner in value.items())
        elif isinstance(value, list):
            stack.extend((f"{path}.{i}", inner) for i, inner in enumerate(value))
        elif isinstance(value, str) and _is_template(value):
            for match in _CAN_IN_TEMPLATE.finditer(value):
                first, second = match.groups()
                if not _is_device_param(first, ctx):
                    second = None
                _fact_parts(first, second, path, ctx)


def _when(raw: object, path: str, ctx: _Ctx) -> list:
    """Validate a `when` list and return its terms as written."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise MakerError("bad_value", path, "when is a list of terms")
    if len(raw) > MAX_WHEN_TERMS:
        raise MakerError("too_many", path, f"at most {MAX_WHEN_TERMS} terms")
    for index, term in enumerate(raw):
        _when_term(term, f"{path}.{index}", ctx)
    return list(raw)


def _when_term(term: object, path: str, ctx: _Ctx) -> None:
    """Check that a term names something a condition may read."""
    parsed = parse_when_term(term, path)
    name = parsed["name"]
    head, _, rest = name.partition(".")
    if head == "can":
        if not rest:
            raise MakerError("bad_value", path, "can needs a fact name")
        _fact(name, path, ctx)
        return
    if head == "has":
        param = ctx.params.get(rest)
        if param is None or "." in rest:
            raise MakerError("unknown_param", path, f"no param {rest!r}")
        if parsed["op"]:
            raise MakerError("bad_value", path, "has.<param> takes no value")
        return
    if head == "tablet":
        if rest != "v2" or parsed["op"]:
            raise MakerError("bad_value", path, "the tablet term is tablet.v2")
        return
    if rest:
        raise MakerError("bad_value", path, f"{name!r} is not a name a when may use")
    option = ctx.options.get(name)
    if option is None:
        raise MakerError(
            "unknown_option", path, f"{name!r} is not an option of this card"
        )
    choices = option.get("choices")
    if parsed["op"] and choices is not None:
        keys = {choice["value"] for choice in choices}
        for value in parsed["values"]:
            if value not in keys and value != "none":
                raise MakerError(
                    "bad_value", path, f"{value!r} is not a choice of {name!r}"
                )


# ---------------------------------------------------------------- params


def _validate_params(raw: object, ctx: _Ctx) -> None:
    """Validate the params section into ctx.params."""
    if raw is None:
        return
    params = _as_mapping(raw, "params")
    if len(params) > MAX_PARAMS_2:
        raise MakerError("too_many", "params", f"at most {MAX_PARAMS_2} params")
    for name, spec in params.items():
        path = f"params.{name}"
        _name(name, path)
        if name in ctx.used:
            raise MakerError("duplicate_name", path, f"duplicate name {name!r}")
        ctx.used.add(name)
        ctx.params[name] = _validate_param(spec, path)
        if ctx.params[name]["kind"] == "entity" and name in FACT_NAMES:
            # can.<name> would mean both the fact and this device.
            raise MakerError(
                "bad_name",
                path,
                f"{name!r} is the name of a fact (can.{name});"
                " give this device another name",
            )


def _words(spec: dict, path: str) -> tuple[str, str]:
    """Return the label and help of a param or option."""
    label = _text(spec.get("label", ""), f"{path}.label", MAX_LABEL_2)
    help_text = _text(spec.get("help", ""), f"{path}.help", MAX_HELP_2)
    return label, help_text


def _kinds(value: object, path: str) -> list:
    """Return a list of domains, or [] for any."""
    if value == "any":
        return []
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not items:
        raise MakerError("bad_value", path, "expected a domain, a list or any")
    out = []
    for item in items:
        if not isinstance(item, str) or not _DOMAIN.match(item) or item == "any":
            raise MakerError("bad_value", path, f"bad domain {item!r}")
        if item in out:
            raise MakerError("bad_value", path, f"domain {item!r} twice")
        out.append(item)
    if len(out) > 8:
        raise MakerError("too_many", path, "at most 8 domains")
    return out


def _device_classes(value: object, path: str) -> list | None:
    """Return the device classes a param is narrowed to, or None."""
    if value is None:
        return None
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not items or len(items) > 8:
        raise MakerError("bad_value", path, "expected 1 to 8 device classes")
    for item in items:
        if not isinstance(item, str) or not _DOMAIN.match(item):
            raise MakerError("bad_value", path, f"bad device class {item!r}")
    return list(items)


def _validate_param(spec: object, path: str) -> dict:
    """Validate one param definition and return it normalised."""
    spec = _as_mapping(spec, path)
    if "domain" in spec:
        _reject_unknown_keys(
            spec,
            {"domain", "multiple", "max", "optional", "device_class", "label", "help"},
            path,
        )
        domains = _kinds(spec["domain"], f"{path}.domain")
        multiple = _bool(spec.get("multiple", False), f"{path}.multiple")
        if "max" in spec and not multiple:
            raise MakerError("bad_value", f"{path}.max", "max needs multiple: true")
        limit = _int(spec.get("max", 8), f"{path}.max", 1, 16) if multiple else 1
        label, help_text = _words(spec, path)
        return {
            "kind": "entity",
            "domains": domains,
            # The one domain when there is exactly one, as schema 1 has it.
            "domain": domains[0] if len(domains) == 1 else None,
            "multiple": multiple,
            "max": limit,
            "optional": _bool(spec.get("optional", False), f"{path}.optional"),
            "device_class": _device_classes(
                spec.get("device_class"), f"{path}.device_class"
            ),
            "label": label,
            "help": help_text,
        }
    ptype = spec.get("type")
    if ptype == "page":
        _reject_unknown_keys(spec, {"type", "optional", "label", "help"}, path)
        label, help_text = _words(spec, path)
        return {
            "kind": "page",
            "optional": _bool(spec.get("optional", False), f"{path}.optional"),
            "label": label,
            "help": help_text,
        }
    if ptype == "number":
        _reject_unknown_keys(
            spec, {"type", "default", "min", "max", "label", "help"}, path
        )
        default = _as_number(_required(spec, "default", path), f"{path}.default")
        low, high = spec.get("min"), spec.get("max")
        label, help_text = _words(spec, path)
        return {
            "kind": "number",
            "default": default,
            "min": None if low is None else _as_number(low, f"{path}.min"),
            "max": None if high is None else _as_number(high, f"{path}.max"),
            "label": label,
            "help": help_text,
        }
    if "type" in spec:
        raise MakerError("bad_value", f"{path}.type", f"unknown param type {ptype!r}")
    raise MakerError("missing_key", path, "param needs 'domain' or 'type'")


# ---------------------------------------------------------------- options


def _validate_options(raw: object, ctx: _Ctx) -> None:
    """Validate the options section into ctx.options; `when` comes later."""
    if raw is None:
        return
    options = _as_mapping(raw, "options")
    if len(options) > MAX_OPTIONS_2:
        raise MakerError("too_many", "options", f"at most {MAX_OPTIONS_2} options")
    for name, spec in options.items():
        path = f"options.{name}"
        _name(name, path)
        if name in STANDARD_OPTIONS_2:
            raise MakerError("bad_name", path, f"{name!r} is a standard option")
        if name in ctx.used:
            raise MakerError("duplicate_name", path, f"duplicate name {name!r}")
        ctx.used.add(name)
        ctx.options[name] = _validate_option(spec, path, ctx)
    for name, spec in ctx.options.items():
        spec["when"] = _when(options[name].get("when"), f"options.{name}.when", ctx)


_OPTION_SHARED = {"type", "section", "label", "help", "default", "when", "needs"}
_OPTION_EXTRA = {
    "toggle": set(),
    "choice": {"choices", "from", "multiple", "max", "default_first"},
    "number": {"min", "max", "step", "unit"},
    "text": {"max"},
    "icon": set(),
    "colour": set(),
    "colours": {"max"},
}


def _validate_option(spec: object, path: str, ctx: _Ctx) -> dict:
    """Validate one option and return it normalised (C.7)."""
    spec = _as_mapping(spec, path)
    otype = _required(spec, "type", path)
    if otype not in OPTION_TYPES:
        raise MakerError("bad_value", f"{path}.type", f"unknown option type {otype!r}")
    _reject_unknown_keys(
        spec, _OPTION_SHARED | {"needs_text"} | _OPTION_EXTRA[otype], path
    )
    section = _required(spec, "section", path)
    if section not in OPTION_SECTIONS:
        raise MakerError(
            "bad_value", f"{path}.section", "section is shows, controls or look"
        )
    label = _text(_required(spec, "label", path), f"{path}.label", MAX_LABEL_2)
    if not label:
        raise MakerError("bad_value", f"{path}.label", "an option needs a label")
    help_text = _text(spec.get("help", ""), f"{path}.help", MAX_HELP_2)
    needs = spec.get("needs")
    needs = "" if needs is None else _fact(needs, f"{path}.needs", ctx)
    needs_text = _text(spec.get("needs_text", ""), f"{path}.needs_text", MAX_HELP_2)
    if needs_text and not needs:
        raise MakerError("bad_value", f"{path}.needs_text", "needs_text needs 'needs'")
    out = {
        "type": otype,
        "section": section,
        "label": label,
        "help": help_text,
        "when": [],
        "needs": needs,
        "needs_text": needs_text,
    }
    out.update(_OPTION_TYPE_CHECKS[otype](spec, path, ctx))
    if "default" in spec:
        out["default"] = _option_default(out, spec["default"], f"{path}.default")
    else:
        out["default"] = _implicit_default(out)
    return out


def _toggle_fields(spec: dict, path: str, ctx: _Ctx) -> dict:
    """Return the fields of a toggle option."""
    return {}


def _choice_fields(spec: dict, path: str, ctx: _Ctx) -> dict:
    """Return the fields of a choice option."""
    multiple = _bool(spec.get("multiple", False), f"{path}.multiple")
    if "max" in spec and not multiple:
        raise MakerError("bad_value", f"{path}.max", "max needs multiple: true")
    out: dict = {"multiple": multiple}
    if multiple:
        out["max"] = _int(spec.get("max", 8), f"{path}.max", 1, MAX_MULTIPLE_2)
    if ("choices" in spec) == ("from" in spec):
        raise MakerError("bad_value", path, "a choice needs 'choices' or 'from'")
    if "from" in spec:
        out["from"] = _fact(spec["from"], f"{path}.from", ctx)
        out["default_first"] = _int(
            spec.get("default_first", 0), f"{path}.default_first", 0, MAX_MULTIPLE_2
        )
        if "default" in spec:
            raise MakerError(
                "bad_value", f"{path}.default", "use default_first with 'from'"
            )
        return out
    if "default_first" in spec:
        raise MakerError(
            "bad_value", f"{path}.default_first", "default_first needs 'from'"
        )
    cpath = f"{path}.choices"
    choices = _as_mapping(spec["choices"], cpath)
    if not 2 <= len(choices) <= MAX_CHOICES_2:
        raise MakerError("bad_value", cpath, f"2 to {MAX_CHOICES_2} choices")
    out["choices"] = []
    for key, label in choices.items():
        if not isinstance(key, str) or not _CHOICE_KEY.match(key):
            raise MakerError("bad_value", f"{cpath}.{key}", f"bad choice key {key!r}")
        out["choices"].append(
            {"value": key, "label": _text(label, f"{cpath}.{key}", MAX_LABEL_2)}
        )
    return out


def _number_fields(spec: dict, path: str, ctx: _Ctx) -> dict:
    """Return the fields of a number option."""
    low = None if "min" not in spec else _as_number(spec["min"], f"{path}.min")
    high = None if "max" not in spec else _as_number(spec["max"], f"{path}.max")
    if low is not None and high is not None and low >= high:
        raise MakerError("bad_value", path, "min must be below max")
    step = _as_number(spec.get("step", 1), f"{path}.step")
    if step <= 0 or not math.isfinite(step):
        raise MakerError("bad_value", f"{path}.step", "step must be above 0")
    unit = _text(spec.get("unit", ""), f"{path}.unit", 8)
    return {"min": low, "max": high, "step": step, "unit": unit}


def _text_fields(spec: dict, path: str, ctx: _Ctx) -> dict:
    """Return the fields of a text option."""
    limit = MAX_TEXT_OPTION_2
    return {"max": _int(spec.get("max", limit), f"{path}.max", 1, limit)}


def _no_fields(spec: dict, path: str, ctx: _Ctx) -> dict:
    """Return the fields of an option type that has none."""
    return {}


def _colours_fields(spec: dict, path: str, ctx: _Ctx) -> dict:
    """Return the fields of a colours option."""
    limit = MAX_COLOURS_2
    return {"max": _int(spec.get("max", limit), f"{path}.max", 1, limit)}


_OPTION_TYPE_CHECKS = {
    "toggle": _toggle_fields,
    "choice": _choice_fields,
    "number": _number_fields,
    "text": _text_fields,
    "icon": _no_fields,
    "colour": _no_fields,
    "colours": _colours_fields,
}


def _implicit_default(option: dict) -> object:
    """Return the default of an option that does not say one."""
    otype = option["type"]
    if otype == "toggle":
        return False
    if otype == "choice":
        if option["multiple"] or "from" in option:
            return [] if option["multiple"] else None
        return option["choices"][0]["value"]
    if otype == "number":
        return option["min"] if option["min"] is not None else 0.0
    if otype == "text":
        return ""
    if otype == "colours":
        return []
    return None


def check_option_value(option: dict, value: object, path: str) -> object:
    """Return a stored option value checked against its option, or raise.

    `from: can.<list>` entries are checked against the device's list on
    the paths that know the facts; here only their shape is checked.
    """
    otype = option["type"]
    if otype == "toggle":
        return _bool(value, path)
    if otype == "choice":
        return _check_choice_value(option, value, path)
    if otype == "number":
        number = _as_number(value, path)
        if not math.isfinite(number):
            raise MakerError("bad_value", path, "expected a finite number")
        low, high = option["min"], option["max"]
        if (low is not None and number < low) or (high is not None and number > high):
            raise MakerError("bad_value", path, "number outside its allowed range")
        return number
    if otype == "text":
        return _text(value, path, option["max"])
    if otype == "icon":
        return _validate_icon(value, path)
    if otype == "colour":
        return colour_constant(value, path)
    if not isinstance(value, list) or len(value) > option["max"]:
        raise MakerError(
            "bad_value", path, f"a list of at most {option['max']} colours"
        )
    return [_colours_entry(item, f"{path}.{i}") for i, item in enumerate(value)]


def _check_choice_value(option: dict, value: object, path: str) -> object:
    """Return a choice value checked for its shape and keys."""
    keys = None
    if "choices" in option:
        keys = {choice["value"] for choice in option["choices"]}

    def _one(item: object, ipath: str) -> str:
        if not isinstance(item, str) or len(item.encode()) > 255:
            raise MakerError("bad_value", ipath, "expected a choice")
        if keys is not None and item not in keys:
            raise MakerError("bad_value", ipath, f"{item!r} is not a choice")
        return item

    if not option["multiple"]:
        return _one(value, path)
    if not isinstance(value, list) or len(value) > option["max"]:
        raise MakerError(
            "bad_value", path, f"a list of at most {option['max']} choices"
        )
    out = [_one(item, f"{path}.{i}") for i, item in enumerate(value)]
    if len(set(out)) != len(out):
        raise MakerError("bad_value", path, "a choice is listed twice")
    return out


def _option_default(option: dict, value: object, path: str) -> object:
    """Return the default an option file gives, checked by its type."""
    if option["type"] == "icon" and value is None:
        return None
    if option["type"] == "colour" and value is None:
        return None
    return check_option_value(option, value, path)


# ---------------------------------------------------------------- inputs


def _validate_inputs(raw: object, ctx: _Ctx) -> None:
    """Validate the inputs section into ctx.inputs."""
    if raw is None:
        return
    inputs = _as_mapping(raw, "inputs")
    if len(inputs) > MAX_INPUTS_2:
        raise MakerError("too_many", "inputs", f"at most {MAX_INPUTS_2} inputs")
    for name, spec in inputs.items():
        path = f"inputs.{name}"
        _name(name, path)
        if name in ctx.used:
            raise MakerError("duplicate_name", path, f"duplicate name {name!r}")
        ctx.used.add(name)
        ctx.inputs[name] = _validate_input(spec, path, ctx)


def _entity_ref(spec: dict, path: str, ctx: _Ctx) -> str:
    """Return the param or loop name of an input's `entity: '{{ name }}'`."""
    epath = f"{path}.entity"
    value = _required(spec, "entity", path)
    match = _VAR.match(value) if isinstance(value, str) else None
    if match is None:
        raise MakerError("bad_value", epath, "entity must be '{{ name }}'")
    name = match.group(1)
    param = ctx.params.get(name)
    if param is not None:
        if param["kind"] != "entity" or param["multiple"]:
            raise MakerError("unknown_param", epath, f"no single-device param {name!r}")
        return name
    # A loop over a param with several devices; checked once the layout is read.
    ctx.deferred.append(("loop_entity", name, epath))
    return name


def _validate_input(spec: object, path: str, ctx: _Ctx) -> dict:
    """Validate one input definition and return it normalised."""
    if isinstance(spec, str):
        return {"kind": "template", "template": _check_text(spec, path)}
    spec = _as_mapping(spec, path)
    if "action" in spec:
        return _validate_action_input(spec, path, ctx)
    source = spec.get("source")
    if source == "recorder":
        params = _with_loop_entity(spec.get("entity"), f"{path}.entity", ctx, None)
        return _validate_history_input(spec, path, params)
    if source == "camera":
        return _validate_camera_input(spec, path, ctx.params)
    if source == "colour":
        _reject_unknown_keys(spec, {"source", "entity", "of"}, path)
        of = spec.get("of", "rgb")
        if of not in ("rgb", "hue"):
            raise MakerError("bad_value", f"{path}.of", "of is rgb or hue")
        return {"kind": "colour", "param": _entity_ref(spec, path, ctx), "of": of}
    if source in ("state_icon", "media_position"):
        _reject_unknown_keys(spec, {"source", "entity"}, path)
        return {"kind": source, "param": _entity_ref(spec, path, ctx)}
    if source == "clock":
        _reject_unknown_keys(spec, {"source"}, path)
        return {"kind": "clock"}
    if source == "statistics":
        return _validate_statistics_input(spec, path, ctx)
    raise MakerError("bad_value", path, "unknown input source")


def _validate_action_input(spec: dict, path: str, ctx: _Ctx) -> dict:
    """Validate a read-action input; its param must have the action's domain.

    Its `entity_id` may also name a loop over a param with several devices
    of that domain (C.2.8); its `result` may name the loop's entry, so each
    copy renders its own value from the one shared call.
    """
    action = spec.get("action")
    domain = action.split(".", 1)[0] if isinstance(action, str) else None
    data = spec.get("data")
    entity = data.get("entity_id") if isinstance(data, dict) else None
    params = _with_loop_entity(entity, f"{path}.data.entity_id", ctx, domain)
    return _schema1_action_input(spec, path, params)


def _with_loop_entity(value: object, path: str, ctx: _Ctx, domain: str | None) -> dict:
    """Return the params, with a stand-in for a loop name an input's entity names.

    A schema 1 check then reads the loop name as a single-device param. The
    loop itself is checked once the layout is read: it must go over a param
    with several devices, and for a read action only over devices of the
    action's domain.
    """
    match = _VAR.match(value) if isinstance(value, str) else None
    if match is None or match.group(1) in ctx.params:
        return ctx.params
    name = match.group(1)
    ctx.deferred.append(("loop_entity", name, path, domain))
    stand_in = {"kind": "entity", "multiple": False, "domain": domain}
    return {**ctx.params, name: stand_in}


def _validate_statistics_input(spec: dict, path: str, ctx: _Ctx) -> dict:
    """Validate a statistics input: one number, or 24 hourly numbers."""
    if "buckets" in spec:
        _reject_unknown_keys(
            spec, {"source", "entity", "buckets", "period", "stat"}, path
        )
        if spec["buckets"] != "hour":
            raise MakerError("bad_value", f"{path}.buckets", "buckets is hour")
        if spec.get("period", "today") != "today":
            raise MakerError("bad_value", f"{path}.period", "period is today")
        stat = spec.get("stat", "mean")
        if stat not in ("mean", "sum"):
            raise MakerError("bad_value", f"{path}.stat", "stat is mean or sum")
        return {
            "kind": "statistics",
            "param": _entity_ref(spec, path, ctx),
            "buckets": "hour",
            "period": "today",
            "stat": stat,
        }
    _reject_unknown_keys(spec, {"source", "entity", "stat", "hours"}, path)
    stat = spec.get("stat", "mean")
    if stat not in ("min", "max", "mean"):
        raise MakerError("bad_value", f"{path}.stat", "stat is min, max or mean")
    return {
        "kind": "statistics",
        "param": _entity_ref(spec, path, ctx),
        "stat": stat,
        "hours": _int(spec.get("hours", 24), f"{path}.hours", 1, 168),
    }


# ---------------------------------------------------------------- outputs


def _validate_outputs(raw: object, ctx: _Ctx) -> None:
    """Validate the outputs section into ctx.outputs."""
    if raw is None:
        return
    outputs = _as_mapping(raw, "outputs")
    if len(outputs) > MAX_OUTPUTS_2:
        raise MakerError("too_many", "outputs", f"at most {MAX_OUTPUTS_2} outputs")
    for name, spec in outputs.items():
        path = f"outputs.{name}"
        _name(name, path)
        if name in _ITEM_WORDS:
            raise MakerError("bad_name", path, f"name {name!r} is reserved")
        ctx.outputs[name] = _validate_output(spec, path, ctx)


def _validate_output(spec: object, path: str, ctx: _Ctx) -> dict:
    """Validate one output and return it normalised."""
    spec = _as_mapping(spec, path)
    if "action" in spec and "local" in spec:
        raise MakerError("bad_value", path, "output cannot mix action and local")
    if "local" in spec:
        return _validate_local_output(spec, path, ctx)
    if "action" in spec:
        return _validate_action_output(spec, path, ctx)
    raise MakerError("missing_key", path, "output needs 'action' or 'local'")


def _validate_local_output(spec: dict, path: str, ctx: _Ctx) -> dict:
    """Validate a local output: the browser's or the tablet's own move."""
    _reject_unknown_keys(spec, {"local", "page"}, path)
    local = spec["local"]
    if local not in LOCAL_ACTIONS_2:
        raise MakerError("bad_value", f"{path}.local", f"bad local action {local!r}")
    page = spec.get("page")
    if local != "go_to_page":
        if page is not None:
            raise MakerError(
                "bad_value", f"{path}.page", "only go_to_page takes a page"
            )
        return {"kind": "local", "local": local, "page": None}
    ppath = f"{path}.page"
    page = _check_text(_required(spec, "page", path), ppath)
    match = _VAR.match(page)
    if match is not None:
        target = ctx.params.get(match.group(1))
        if target is None or target["kind"] != "page":
            raise MakerError("unknown_param", ppath, "no page param with that name")
    elif _PAGE_PATH.match(page) is None:
        raise MakerError("bad_value", ppath, f"bad page path {page!r}")
    return {"kind": "local", "local": local, "page": page}


def _service(action: object, path: str) -> str:
    """Return a <domain>.<service> that is in the list of allowed services."""
    if not isinstance(action, str) or not _ACTION.match(action):
        raise MakerError("bad_value", path, f"bad action {action!r}")
    domain, _, service = action.partition(".")
    if service not in ALLOWED_SERVICES.get(domain, ()):
        raise MakerError(
            "action_not_allowed",
            path,
            f"{action} is not in the list of allowed services",
        )
    return action


def _validate_action_output(spec: dict, path: str, ctx: _Ctx) -> dict:
    """Validate a service-call output: plain, or one action per kind."""
    _reject_unknown_keys(spec, {"action", "data", "feedback", "uses"}, path)
    apath = f"{path}.action"
    raw_action = spec["action"]
    action = None
    actions = None
    if isinstance(raw_action, dict):
        if not raw_action:
            raise MakerError("bad_value", apath, "an action per kind needs an entry")
        actions = {}
        for kind, service in raw_action.items():
            kpath = f"{apath}.{kind}"
            if not isinstance(kind, str) or not _DOMAIN.match(kind):
                raise MakerError("bad_value", kpath, f"bad kind {kind!r}")
            service = _service(service, kpath)
            if service.split(".", 1)[0] != kind:
                raise MakerError(
                    "domain_mismatch", kpath, f"a {kind} must call a {kind} service"
                )
            actions[kind] = service
        domains = list(actions)
    else:
        action = _service(raw_action, apath)
        domains = [action.split(".", 1)[0]]
    feedback = _required(spec, "feedback", path)
    if feedback not in FEEDBACK_MODES:
        raise MakerError("bad_value", f"{path}.feedback", f"bad feedback {feedback!r}")
    sensitive = any(domain in SENSITIVE_DOMAINS for domain in domains)
    if sensitive and feedback != "confirm":
        raise MakerError("confirm_required", path, "sensitive domains need confirm")
    uses = _validate_uses(spec.get("uses"), f"{path}.uses", ctx)
    data = _validate_data2(_required(spec, "data", path), f"{path}.data")
    ref = _output_entity_ref(data, uses, path, ctx)
    out = {
        "kind": "action",
        "action": action,
        "actions": actions,
        "data": data,
        "feedback": feedback,
        "uses": uses,
        "entity_ref": ref,
        "sensitive": sensitive,
    }
    _check_output_kinds(out, ctx.params.get(ref), f"{path}.data.entity_id")
    return out


def _validate_uses(raw: object, path: str, ctx: _Ctx) -> dict:
    """Validate the inputs an output's data may read, each with a type."""
    if raw is None:
        return {}
    uses = _as_mapping(raw, path)
    if len(uses) > 8:
        raise MakerError("too_many", path, "at most 8 inputs")
    for name, kind in uses.items():
        if name not in ctx.inputs:
            raise MakerError("unknown_input", f"{path}.{name}", f"no input {name!r}")
        if kind not in USES_TYPES:
            raise MakerError(
                "bad_value", f"{path}.{name}", "a use is number, bool or entities"
            )
    return dict(uses)


def _validate_data2(raw: object, path: str) -> dict:
    """Validate service data: scalars, and number lists for colour keys only."""
    data = _as_mapping(raw, path)
    extra = [key for key in data if key != "entity_id"]
    if len(extra) > MAX_DATA_KEYS:
        raise MakerError("too_many", path, f"at most {MAX_DATA_KEYS} data keys")
    for key, value in data.items():
        kpath = f"{path}.{key}"
        if not isinstance(key, str) or not _DATA_KEY.match(key):
            raise MakerError("bad_value", kpath, f"bad data key {key!r}")
        if key in TARGET_KEYS:
            raise MakerError(
                "bad_value", kpath, f"{key} would reach beyond the picked entity"
            )
        if isinstance(value, list):
            if key not in COLOUR_DATA_KEYS:
                raise MakerError(
                    "bad_value", kpath, "only the colour keys may hold a list"
                )
            if not 1 <= len(value) <= 4:
                raise MakerError("bad_value", kpath, "a colour list has 1 to 4 entries")
            for index, entry in enumerate(value):
                _data_scalar(entry, f"{kpath}.{index}", in_list=True)
            continue
        if key in COLOUR_DATA_KEYS and reference(value) is None:
            # A template that prints a list is refused in schema 2 (C.2.8):
            # a colour is a list, or a reference such as '{{ c | rgb }}'.
            raise MakerError(
                "bad_value", kpath, "a colour is a list of numbers or '{{ name }}'"
            )
        _data_scalar(value, kpath, in_list=False)
    return {
        key: list(value) if isinstance(value, list) else value
        for key, value in data.items()
    }


def _data_scalar(value: object, path: str, *, in_list: bool) -> None:
    """Check one data value: text, a number, yes or no; never a mapping."""
    if isinstance(value, bool):
        if in_list:
            raise MakerError("bad_value", path, "a colour list holds numbers")
        return
    if isinstance(value, int | float):
        return
    if isinstance(value, str):
        _check_text(value, path)
        return
    if isinstance(value, dict):
        raise MakerError("bad_value", path, "data may never hold a mapping")
    raise MakerError("bad_value", path, "data values must be scalar")


def _output_entity_ref(data: dict, uses: dict, path: str, ctx: _Ctx) -> str:
    """Return the name behind entity_id: a param, an entities input or a loop."""
    epath = f"{path}.data.entity_id"
    value = _required(data, "entity_id", f"{path}.data")
    match = _VAR.match(value) if isinstance(value, str) else None
    if match is None:
        raise MakerError("bad_value", epath, "entity_id must be '{{ name }}'")
    name = match.group(1)
    param = ctx.params.get(name)
    if param is not None:
        if param["kind"] != "entity":
            raise MakerError("unknown_param", epath, f"{name!r} is not a device param")
        return name
    if name in ctx.inputs:
        if uses.get(name) != "entities":
            raise MakerError(
                "unknown_param", epath, f"input {name!r} must be in uses as entities"
            )
        return name
    ctx.deferred.append(("output_entity", name, epath, path))
    return name


def _check_output_kinds(output: dict, param: dict | None, path: str) -> None:
    """Check a plain action or a per-kind map against the param's kinds."""
    if param is None or param["kind"] != "entity":
        return
    kinds = param["domains"]
    if output["actions"] is None:
        domain = output["action"].split(".", 1)[0]
        if not kinds:
            raise MakerError(
                "domain_mismatch", path, "a device of any kind needs an action per kind"
            )
        if domain not in kinds:
            raise MakerError("domain_mismatch", path, "param domain must match")
        return
    if kinds:
        for kind in output["actions"]:
            if kind not in kinds:
                raise MakerError(
                    "domain_mismatch", path, f"{kind!r} is not a kind of this param"
                )


# ---------------------------------------------------------------- fields


def _lookup_names(ctx: _Ctx, scope: dict, item_vars: dict) -> dict:
    """Return the names that a '{{ name }}' field looks up instead of rendering.

    The value is True when the name needs a key, as can does.
    """
    names: dict = {"can": True}
    names.update(dict.fromkeys(ctx.options, False))
    names.update(dict.fromkeys(item_vars, False))
    for as_name, loop in scope.items():
        if loop["kind"] == "param":
            names[f"{as_name}_can"] = True
        else:
            names[as_name] = False
    return names


def _mark(
    value: object,
    path: str,
    ctx: _Ctx,
    env: dict,
    *,
    inputs: bool = True,
    template: bool = True,
    const=None,
) -> dict:
    """Mark a field with the form it is written in (see the module text)."""
    if isinstance(value, str):
        match = _REF.match(value)
        if match is not None:
            name, key = match.groups()
            needs_key = env["lookups"].get(name)
            if needs_key is not None:
                if needs_key and key is None:
                    raise MakerError("bad_value", path, f"{name} needs a key")
                if needs_key and name != "can" and key not in FACT_NAMES:
                    # <as>_can of a loop over devices: one device's facts.
                    # (`{{ can.<x> }}` is checked with every template.)
                    raise MakerError(
                        "unknown_fact", path, f"{key!r} is not a fact a device can have"
                    )
                return {"form": "lookup", "name": name, "key": key}
        if _is_template(value):
            if not template:
                raise MakerError("bad_value", path, "a template is not allowed here")
            return {"form": "template", "template": _check_text(value, path)}
        if inputs and value in ctx.inputs:
            return {"form": "input", "input": value}
    if const is None:
        raise MakerError(
            "unknown_input", path, "expected an input, a template or a lookup"
        )
    return _const(const(value, path))


def _number_const(value: object, path: str) -> float:
    """Return a finite number."""
    number = _as_number(value, path)
    if not math.isfinite(number):
        raise MakerError("bad_value", path, "expected a finite number")
    return number


def _text_const(value: object, path: str) -> str:
    """Return a constant text."""
    return _check_text(value, path)


def _colour_field(value: object, path: str, ctx: _Ctx, env: dict) -> dict:
    """Mark a colour: #RRGGBB or a role, an input, a template or a lookup."""
    if isinstance(value, str) and value in COLOUR_ROLES and value in ctx.inputs:
        raise MakerError(
            "bad_value", path, f"{value!r} is both a colour role and an input"
        )
    if isinstance(value, str) and value in COLOUR_ROLES:
        return _const(value)
    return _mark(value, path, ctx, env, const=colour_constant)


def _icon_field(value: object, path: str, ctx: _Ctx, env: dict) -> dict:
    """Mark a constant icon: an mdi: name or a lookup, never a template."""
    return _mark(
        value, path, ctx, env, inputs=False, template=False, const=_validate_icon
    )


def _trigger(
    item: dict, key: str, path: str, ctx: _Ctx, *, action_only: bool = False
) -> str | None:
    """Validate on_tap / on_change: an output, or `detail` for on_tap."""
    raw = item.get(key)
    if raw is None:
        return None
    tpath = f"{path}.{key}"
    if key == "on_tap" and raw == "detail":
        if not ctx.has_detail:
            raise MakerError("bad_value", tpath, "the card has no detail variant")
        return raw
    if not isinstance(raw, str) or raw not in ctx.outputs:
        raise MakerError("unknown_output", tpath, f"no output named {raw!r}")
    if action_only and ctx.outputs[raw]["kind"] != "action":
        raise MakerError("bad_value", tpath, f"{key} needs an action output")
    return raw


def _track(value: object, path: str, ctx: _Ctx, env: dict) -> dict:
    """Validate a slider track: hue, a kelvin range, or a list of colours."""
    if value == "hue":
        return {"kind": "hue", "colours": list(_HUE_TRACK)}
    if isinstance(value, dict):
        _reject_unknown_keys(value, {"kelvin"}, path)
        pair = _required(value, "kelvin", path)
        if not isinstance(pair, list) or len(pair) != 2:
            raise MakerError("bad_value", f"{path}.kelvin", "kelvin is [low, high]")
        ends = [
            _mark(
                end,
                f"{path}.kelvin.{i}",
                ctx,
                env,
                inputs=False,
                template=False,
                const=_kelvin_const,
            )
            for i, end in enumerate(pair)
        ]
        low, high = ends
        if low["form"] == high["form"] == "const" and low["value"] >= high["value"]:
            raise MakerError("bad_value", f"{path}.kelvin", "low must be below high")
        return {"kind": "kelvin", "kelvin": ends}
    if isinstance(value, list):
        if not 2 <= len(value) <= MAX_TRACK_2:
            raise MakerError(
                "bad_value", path, f"a track has 2 to {MAX_TRACK_2} colours"
            )
        return {
            "kind": "colours",
            "colours": [colour_constant(c, f"{path}.{i}") for i, c in enumerate(value)],
        }
    raise MakerError(
        "bad_value", path, "track is hue, {kelvin: [low, high]} or colours"
    )


def _kelvin_const(value: object, path: str) -> int:
    """Return a kelvin value within the range Home Assistant draws."""
    low, high = KELVIN_RANGE
    return _int(value, path, low, high)


def _choice_options(value: object, path: str, ctx: _Ctx, env: dict) -> dict:
    """Validate the options of a choice: a list, a list fact or an option."""
    if isinstance(value, str):
        if value.startswith("can."):
            return {"kind": "fact", "fact": _fact(value, path, ctx)}
        option = ctx.options.get(value)
        if option is None:
            raise MakerError("unknown_option", path, f"no option {value!r}")
        if option["type"] != "colours" and not (
            option["type"] == "choice" and option["multiple"]
        ):
            raise MakerError(
                "bad_value",
                path,
                "options may name a colours or multiple-choice option",
            )
        return {"kind": "option", "option": value}
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_CHOICE_OPTIONS_2:
        raise MakerError(
            "bad_value", path, f"a choice has 1 to {MAX_CHOICE_OPTIONS_2} options"
        )
    entries = []
    for index, entry in enumerate(value):
        epath = f"{path}.{index}"
        entry = _as_mapping(entry, epath)
        _reject_unknown_keys(entry, {"value", "text", "icon", "colour"}, epath)
        out: dict = {}
        if "value" in entry:
            raw = entry["value"]
            if not isinstance(raw, str | int | float) or _is_template(raw):
                raise MakerError("bad_value", f"{epath}.value", "a value is a constant")
            out["value"] = raw
        if "text" in entry:
            out["text"] = _mark(
                entry["text"],
                f"{epath}.text",
                ctx,
                env,
                inputs=False,
                template=False,
                const=_text_const,
            )
        if "icon" in entry:
            out["icon"] = _icon_field(entry["icon"], f"{epath}.icon", ctx, env)
        if "colour" in entry:
            out["colour"] = _const(colour_constant(entry["colour"], f"{epath}.colour"))
        if not {"text", "icon", "colour"} & set(out):
            raise MakerError(
                "missing_key", epath, "an option needs text, icon or colour"
            )
        entries.append(out)
    return {"kind": "list", "entries": entries}


def _vars(raw: object, path: str, ctx: _Ctx) -> dict:
    """Validate an item's vars: names that hide nothing, constant values."""
    if raw is None:
        return {}
    values = _as_mapping(raw, path)
    if len(values) > 8:
        raise MakerError("too_many", path, "at most 8 vars")
    out = {}
    for name, value in values.items():
        vpath = f"{path}.{name}"
        _name(name, vpath)
        if name in ctx.used:
            raise MakerError("bad_name", vpath, f"{name!r} would hide another name")
        if not isinstance(value, str | int | float | bool) or _is_template(value):
            raise MakerError("bad_value", vpath, "a var is a constant")
        if isinstance(value, str):
            _check_text(value, vpath)
        out[name] = value
        ctx.vars_names.add(name)
    return out


# ---------------------------------------------------------------- loops


def _loop(item: dict, path: str, ctx: _Ctx, scope: dict) -> dict | None:
    """Validate for_each / as / per_row; return the loop or None."""
    for_each = item.get("for_each")
    as_name = item.get("as")
    if for_each is None:
        if as_name is not None or "per_row" in item:
            raise MakerError("bad_value", f"{path}.as", "'as' needs 'for_each'")
        return None
    if scope:
        raise MakerError(_BAD_NESTING, f"{path}.for_each", "a loop may not hold a loop")
    fpath = f"{path}.for_each"
    loop = _loop_source(for_each, fpath, ctx)
    if as_name is None:
        raise MakerError("missing_key", f"{path}.as", "for_each needs 'as'")
    _name(as_name, f"{path}.as")
    if as_name in ctx.used or as_name in ctx.vars_names:
        raise MakerError("duplicate_name", f"{path}.as", f"duplicate name {as_name!r}")
    if loop["kind"] == "param" and f"{as_name}_can" in ctx.used:
        raise MakerError("duplicate_name", f"{path}.as", f"{as_name}_can is taken")
    key = (loop["kind"], loop.get("name"), repr(loop.get("entries")))
    previous = ctx.loops.setdefault(as_name, {"key": key, "loop": loop})
    if previous["key"] != key:
        raise MakerError(
            "duplicate_name", f"{path}.as", f"name {as_name!r} already used"
        )
    loop["as"] = as_name
    loop["per_row"] = _int(item.get("per_row", 1), f"{path}.per_row", 1, 8)
    return loop


def _loop_source(value: object, path: str, ctx: _Ctx) -> dict:
    """Return what a loop goes over, with the most copies it can make."""
    if isinstance(value, list):
        if not 1 <= len(value) <= MAX_LOOP_COPIES_2:
            raise MakerError(
                "too_many", path, f"a loop makes 1 to {MAX_LOOP_COPIES_2} copies"
            )
        entries = [_loop_entry(entry, f"{path}.{i}") for i, entry in enumerate(value)]
        return {
            "kind": "list",
            "name": None,
            "entries": entries,
            "copies": len(entries),
        }
    if not isinstance(value, str):
        raise MakerError(
            "unknown_param", path, "for_each names a param, fact or option"
        )
    if value.startswith("can."):
        _fact(value, path, ctx)
        return {"kind": "fact", "name": value, "copies": MAX_LOOP_COPIES_2}
    param = ctx.params.get(value)
    if param is not None:
        if param["kind"] != "entity" or not param["multiple"]:
            raise MakerError(
                "unknown_param", path, f"no param with several devices {value!r}"
            )
        return {"kind": "param", "name": value, "copies": param["max"]}
    option = ctx.options.get(value)
    if option is not None:
        if option["type"] == "colours" or (
            option["type"] == "choice" and option["multiple"]
        ):
            copies = min(option["max"], MAX_LOOP_COPIES_2)
            return {"kind": "option", "name": value, "copies": copies}
        raise MakerError(
            "bad_value", path, "a loop over an option needs colours or multiple choice"
        )
    raise MakerError("unknown_param", path, f"nothing to loop over named {value!r}")


def _loop_entry(value: object, path: str) -> object:
    """Return one entry of a list in the file: a constant or a flat mapping."""
    if isinstance(value, str | int | float | bool):
        if _is_template(value):
            raise MakerError("bad_value", path, "a loop entry is a constant")
        return value
    entry = _as_mapping(value, path)
    if len(entry) > 8:
        raise MakerError("too_many", path, "at most 8 keys")
    for key, inner in entry.items():
        if not isinstance(key, str) or not _NAME.match(key):
            raise MakerError("bad_value", f"{path}.{key}", f"bad key {key!r}")
        if not isinstance(inner, str | int | float | bool) or _is_template(inner):
            raise MakerError("bad_value", f"{path}.{key}", "a loop entry is a constant")
    return dict(entry)


# ---------------------------------------------------------------- items


def _count(ctx: _Ctx, amount: int, path: str) -> None:
    """Add widgets to the card's count; stop at the limit."""
    ctx.widgets += amount
    if ctx.widgets > MAX_WIDGETS_2:
        raise MakerError(
            "too_many", path, f"a card may have at most {MAX_WIDGETS_2} widgets"
        )


def _resolve_use(item: dict, path: str, ctx: _Ctx, where: str) -> dict:
    """Return the item a `use` line puts in: the part with keys added."""
    if where == "part":
        raise MakerError(_BAD_NESTING, f"{path}.use", "a part may not hold use")
    name = item["use"]
    part = ctx.parts_raw.get(name) if isinstance(name, str) else None
    if part is None:
        raise MakerError("unknown_part", f"{path}.use", f"no part named {name!r}")
    if "type" in item:
        raise MakerError(
            "bad_value", f"{path}.type", "a use line keeps the part's type"
        )
    merged = {key: value for key, value in part.items() if key != "when"}
    merged.update({k: v for k, v in item.items() if k not in ("use", "when")})
    part_when = part.get("when") or []
    use_when = item.get("when") or []
    if not isinstance(part_when, list) or not isinstance(use_when, list):
        raise MakerError("bad_value", f"{path}.when", "when is a list of terms")
    when = list(part_when) + [term for term in use_when if term not in part_when]
    if when:
        merged["when"] = when
    merged["__part"] = name
    return merged


def _item(raw: object, path: str, ctx: _Ctx, where: str, scope: dict) -> dict:
    """Validate one layout item; `where` is top, row, swap or part."""
    item = _as_mapping(raw, path)
    part_name = None
    if "use" in item:
        item = _resolve_use(item, path, ctx, where)
        part_name = item.pop("__part")
    itype = item.get("type")
    if itype == "row":
        out = _row(item, path, ctx, where, scope)
    elif itype == "swap":
        out = _swap(item, path, ctx, where, scope)
    elif itype == "space":
        out = _space(item, path, ctx, where)
    elif isinstance(itype, str) and itype in _WIDGET_KEYS:
        out = _widget(item, itype, path, ctx, where, scope)
    else:
        raise MakerError("bad_value", f"{path}.type", f"unknown layout type {itype!r}")
    if part_name is not None:
        out["part"] = part_name
    return out


def _size_keys(item: dict, path: str, where: str) -> dict:
    """Validate height or grow, and width or weight inside a row."""
    out: dict = {}
    if "height" in item and "grow" in item:
        raise MakerError("bad_value", path, "height or grow, not both")
    if "height" in item:
        out["height"] = _int(item["height"], f"{path}.height", 1, 696)
    if "grow" in item:
        if item["grow"] is not True:
            raise MakerError("bad_value", f"{path}.grow", "grow is true")
        out["grow"] = True
    if "width" in item or "weight" in item:
        if where not in ("row", "part"):
            raise MakerError(
                "bad_value", path, "width and weight are for a row's items"
            )
        if "width" in item and "weight" in item:
            raise MakerError("bad_value", path, "width or weight, not both")
        if "width" in item:
            out["width"] = _int(item["width"], f"{path}.width", 1, 1160)
        if "weight" in item:
            out["weight"] = _int(item["weight"], f"{path}.weight", 1, 12)
    return out


def _row(item: dict, path: str, ctx: _Ctx, where: str, scope: dict) -> dict:
    """Validate a row: up to 8 widgets side by side."""
    _reject_unknown_keys(
        item,
        {"type", "items", "when", "visible", "height", "for_each", "as", "per_row"},
        path,
    )
    loop = _loop(item, path, ctx, scope)
    inner = dict(scope)
    if loop is not None:
        inner[loop["as"]] = loop
    env = {"lookups": _lookup_names(ctx, inner, {})}
    raw_items = _required(item, "items", path)
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= MAX_ROW_ITEMS_2:
        raise MakerError(
            "bad_value", f"{path}.items", f"a row has 1 to {MAX_ROW_ITEMS_2} items"
        )
    start = ctx.widgets
    items = []
    for index, child in enumerate(raw_items):
        cpath = f"{path}.items.{index}"
        child_map = _as_mapping(child, cpath)
        ctype = child_map.get("type")
        if "use" in child_map:
            part = (
                ctx.parts_raw.get(child_map["use"])
                if isinstance(child_map["use"], str)
                else None
            )
            ctype = part.get("type") if isinstance(part, dict) else ctype
        if ctype in _CONTAINERS:
            raise MakerError(_BAD_NESTING, cpath, "a row holds widgets only")
        items.append(_item(child, cpath, ctx, "row", inner))
    out: dict = {
        "type": "row",
        "when": _when(item.get("when"), f"{path}.when", ctx),
        "items": items,
    }
    if loop is not None:
        # The copies of the row's widgets, counted before they are made.
        _count(ctx, (ctx.widgets - start) * (loop["copies"] - 1), path)
        out["loop"] = loop
    if "visible" in item:
        out["visible"] = _mark(item["visible"], f"{path}.visible", ctx, env)
    out.update(_size_keys(item, path, "top"))
    return out


def _swap(item: dict, path: str, ctx: _Ctx, where: str, scope: dict) -> dict:
    """Validate a swap: items that share one place, each with visible."""
    if where in ("row", "swap"):
        raise MakerError(_BAD_NESTING, path, f"a {where} may not hold a swap")
    _reject_unknown_keys(item, {"type", "items", "when", "height"}, path)
    raw_items = _required(item, "items", path)
    if not isinstance(raw_items, list) or not 2 <= len(raw_items) <= MAX_ROW_ITEMS_2:
        raise MakerError(
            "bad_value", f"{path}.items", f"a swap has 2 to {MAX_ROW_ITEMS_2} items"
        )
    items = []
    for index, child in enumerate(raw_items):
        cpath = f"{path}.items.{index}"
        out_child = _item(child, cpath, ctx, "swap", scope)
        if out_child["type"] in ("swap", "space"):
            raise MakerError(_BAD_NESTING, cpath, "a swap holds widgets or rows")
        if "visible" not in out_child:
            raise MakerError(
                "missing_key", f"{cpath}.visible", "each item of a swap needs visible"
            )
        items.append(out_child)
    out = {
        "type": "swap",
        "when": _when(item.get("when"), f"{path}.when", ctx),
        "items": items,
    }
    out.update(_size_keys(item, path, "top"))
    return out


def _space(item: dict, path: str, ctx: _Ctx, where: str) -> dict:
    """Validate a space that takes spare height."""
    if where in ("row", "swap"):
        raise MakerError(_BAD_NESTING, path, f"a {where} may not hold a space")
    _reject_unknown_keys(item, {"type", "when", "height", "grow"}, path)
    out = {"type": "space", "when": _when(item.get("when"), f"{path}.when", ctx)}
    out.update(_size_keys(item, path, "top"))
    return out


def _widget(
    item: dict, itype: str, path: str, ctx: _Ctx, where: str, scope: dict
) -> dict:
    """Validate one widget of the eight kinds."""
    allowed = (_WIDGET_COMMON - {"use"}) | _WIDGET_KEYS[itype]
    if itype in _COLOUR_TYPES:
        allowed = allowed | {"colour"}
    if itype in _HOLD_TYPES:
        allowed = allowed | {"on_hold"}
    _reject_unknown_keys(item, allowed, path)
    loop = _loop(item, path, ctx, scope)
    inner = dict(scope)
    if loop is not None:
        inner[loop["as"]] = loop
    item_vars = _vars(item.get("vars"), f"{path}.vars", ctx)
    env = {"lookups": _lookup_names(ctx, inner, item_vars)}
    out: dict = {
        "type": itype,
        "when": _when(item.get("when"), f"{path}.when", ctx),
    }
    if item_vars:
        out["vars"] = item_vars
    if loop is not None:
        out["loop"] = loop
    if "visible" in item:
        out["visible"] = _mark(item["visible"], f"{path}.visible", ctx, env)
    if "colour" in item:
        out["colour"] = _colour_field(item["colour"], f"{path}.colour", ctx, env)
    if "on_hold" in item:
        if item["on_hold"] != "detail":
            raise MakerError("bad_value", f"{path}.on_hold", "on_hold is detail")
        if not ctx.has_detail:
            raise MakerError(
                "bad_value", f"{path}.on_hold", "the card has no detail variant"
            )
        out["on_hold"] = "detail"
    out.update(_size_keys(item, path, where))
    out.update(_WIDGET_BODIES[itype](item, path, ctx, env))
    _count(ctx, loop["copies"] if loop is not None else 1, path)
    return out


def _value(
    item: dict, path: str, ctx: _Ctx, env: dict, itype: str, *, required: bool = True
):
    """Mark a value field: an input, a template or a lookup."""
    if "value" not in item:
        if required:
            raise MakerError(
                "missing_key", f"{path}.value", "missing required key 'value'"
            )
        return None
    vpath = f"{path}.value"
    mark = _mark(item["value"], vpath, ctx, env)
    if mark["form"] == "input":
        spec = ctx.inputs[mark["input"]]
        lists = spec["kind"] == "history" or (
            spec["kind"] == "statistics" and "buckets" in spec
        )
        if lists and itype != "chart":
            raise MakerError(
                "bad_value", vpath, f"input {mark['input']!r} only feeds a chart"
            )
    return mark


def _bound(
    item: dict, key: str, default: float, path: str, ctx: _Ctx, env: dict
) -> dict:
    """Mark min, max or step: a number, a lookup or a template."""
    if key not in item:
        return _const(default)
    return _mark(
        item[key], f"{path}.{key}", ctx, env, inputs=False, const=_number_const
    )


def _confirm(
    item: dict, path: str, ctx: _Ctx, env: dict, trigger: str | None
) -> dict | None:
    """Mark the question asked before an output runs."""
    if "confirm" not in item:
        return None
    if trigger is None:
        raise MakerError("bad_value", f"{path}.confirm", "confirm needs an output")
    return _mark(
        item["confirm"], f"{path}.confirm", ctx, env, inputs=False, const=_text_const
    )


def _choose(item: dict, key: str, values: tuple, path: str, default: str | None = None):
    """Return a keyword from a fixed list."""
    value = item.get(key, default)
    if value is None:
        return None
    if value not in values:
        location = f"{path}.{key}" if path else key
        raise MakerError("bad_value", location, f"{key} is one of {', '.join(values)}")
    return value


def _label_body(item: dict, path: str, ctx: _Ctx, env: dict) -> dict:
    """Validate a label."""
    out: dict = {"size": _choose(item, "size", LABEL_SIZES_2, path, "m")}
    out["align"] = _choose(item, "align", ("left", "centre", "right"), path)
    if "clock" in item:
        if item["clock"] not in (12, 24) or isinstance(item["clock"], bool):
            raise MakerError("bad_value", f"{path}.clock", "clock is 24 or 12")
        out["clock"] = item["clock"]
        out["value"] = _value(item, path, ctx, env, "label")
    elif "value" in item:
        raise MakerError("bad_value", f"{path}.value", "a label takes value with clock")
    if "text" in item:
        out["text"] = _mark(
            item["text"], f"{path}.text", ctx, env, inputs=False, const=_text_const
        )
    elif "clock" not in item:
        raise MakerError("missing_key", f"{path}.text", "missing required key 'text'")
    on_tap = _trigger(item, "on_tap", path, ctx)
    out["on_tap"] = on_tap
    out["confirm"] = _confirm(item, path, ctx, env, on_tap)
    return out


def _button_body(item: dict, path: str, ctx: _Ctx, env: dict) -> dict:
    """Validate a button."""
    on_tap = _trigger(item, "on_tap", path, ctx)
    if on_tap is None:
        raise MakerError(
            "missing_key", f"{path}.on_tap", "missing required key 'on_tap'"
        )
    out: dict = {"on_tap": on_tap, "confirm": _confirm(item, path, ctx, env, on_tap)}
    if "text" in item:
        out["text"] = _mark(
            item["text"], f"{path}.text", ctx, env, inputs=False, const=_text_const
        )
    if "icon" in item:
        out["icon"] = _icon_field(item["icon"], f"{path}.icon", ctx, env)
    if "icon_live" in item:
        if "icon" not in item:
            raise MakerError(
                "missing_key", f"{path}.icon", "icon_live needs a constant icon"
            )
        out["icon_live"] = _mark(item["icon_live"], f"{path}.icon_live", ctx, env)
    if "text" not in out and "icon" not in out:
        raise MakerError("missing_key", path, "button needs 'text' or 'icon'")
    if "selected" in item:
        out["selected"] = _mark(item["selected"], f"{path}.selected", ctx, env)
    out["shape"] = _choose(item, "shape", ("box", "round", "bare"), path)
    out["big_icon"] = _bool(item.get("big_icon", False), f"{path}.big_icon")
    return out


def _switch_body(item: dict, path: str, ctx: _Ctx, env: dict) -> dict:
    """Validate a switch."""
    return {
        "value": _value(item, path, ctx, env, "switch"),
        "on_tap": _trigger(item, "on_tap", path, ctx),
    }


def _slider_body(item: dict, path: str, ctx: _Ctx, env: dict) -> dict:
    """Validate a slider."""
    out = _ranged(item, path, ctx, env, "slider", 1.0)
    out["look"] = _choose(item, "look", _LOOKS["slider"], path)
    out["direction"] = _choose(item, "direction", ("right", "up", "down"), path)
    if "track" in item:
        out["track"] = _track(item["track"], f"{path}.track", ctx, env)
    if "icon" in item:
        out["icon"] = _icon_field(item["icon"], f"{path}.icon", ctx, env)
    out["keep_active"] = _bool(item.get("keep_active", False), f"{path}.keep_active")
    if "rate" in item:
        out["rate"] = _mark(item["rate"], f"{path}.rate", ctx, env, const=_number_const)
    return out


def _ranged(
    item: dict, path: str, ctx: _Ctx, env: dict, itype: str, step: float
) -> dict:
    """Validate the value, range and change output of a slider or thermostat."""
    return {
        "value": _value(item, path, ctx, env, itype),
        "min": _bound(item, "min", 0.0, path, ctx, env),
        "max": _bound(item, "max", 100.0, path, ctx, env),
        "step": _bound(item, "step", step, path, ctx, env),
        "on_change": _trigger(item, "on_change", path, ctx, action_only=True),
    }


def _thermostat_body(item: dict, path: str, ctx: _Ctx, env: dict) -> dict:
    """Validate a thermostat."""
    out = _ranged(item, path, ctx, env, "thermostat", 0.5)
    out["side"] = _bool(item.get("side", False), f"{path}.side")
    if "mark" in item:
        out["mark"] = _mark(item["mark"], f"{path}.mark", ctx, env, const=_number_const)
    if "buttons" in item:
        out["buttons"] = _int(item["buttons"], f"{path}.buttons", 36, 64)
    return out


def _chart_body(item: dict, path: str, ctx: _Ctx, env: dict) -> dict:
    """Validate a chart."""
    out = {
        "value": _value(item, path, ctx, env, "chart"),
        "kind": _choose(item, "kind", ("line", "steps", "bars"), path, "line"),
        "side": _bool(item.get("side", False), f"{path}.side"),
    }
    if "mark" in item:
        out["mark"] = _mark(item["mark"], f"{path}.mark", ctx, env, const=_number_const)
    return out


def _image_body(item: dict, path: str, ctx: _Ctx, env: dict) -> dict:
    """Validate an image."""
    on_tap = _trigger(item, "on_tap", path, ctx)
    return {
        "value": _value(item, path, ctx, env, "image"),
        "on_tap": on_tap,
        "confirm": _confirm(item, path, ctx, env, on_tap),
        "side": _bool(item.get("side", False), f"{path}.side"),
        "look": _choose(item, "look", _LOOKS["image"], path),
    }


def _choice_body(item: dict, path: str, ctx: _Ctx, env: dict) -> dict:
    """Validate a choice: one of up to 16."""
    on_change = _trigger(item, "on_change", path, ctx, action_only=True)
    out = {
        "options": _choice_options(
            _required(item, "options", path), f"{path}.options", ctx, env
        ),
        "value": _value(item, path, ctx, env, "choice", required=False),
        "rows": _int(item.get("rows", 1), f"{path}.rows", 1, 4),
        "look": _choose(item, "look", _LOOKS["choice"], path, "cells"),
        "on_change": on_change,
        "confirm": _confirm(item, path, ctx, env, on_change),
    }
    return out


_WIDGET_BODIES = {
    "label": _label_body,
    "button": _button_body,
    "switch": _switch_body,
    "slider": _slider_body,
    "thermostat": _thermostat_body,
    "chart": _chart_body,
    "image": _image_body,
    "choice": _choice_body,
}


# ---------------------------------------------------------------- variants


def _validate_parts(raw: object, ctx: _Ctx) -> dict:
    """Validate the named parts; each is checked on its own and where used."""
    if raw is None:
        return {}
    parts = _as_mapping(raw, "parts")
    if len(parts) > MAX_PARTS_2:
        raise MakerError("too_many", "parts", f"at most {MAX_PARTS_2} parts")
    for name, part in parts.items():
        path = f"parts.{name}"
        if not isinstance(name, str) or not _NAME.match(name):
            raise MakerError("bad_name", path, f"bad name {name!r}")
        part = _as_mapping(part, path)
        _no_use_inside(part, path)
        ctx.parts_raw[name] = part
    out = {}
    for name, part in parts.items():
        counted = ctx.widgets
        out[name] = _item(part, f"parts.{name}", ctx, "part", {})
        # A part counts where a variant uses it, not here.
        ctx.widgets = counted
    return out


def _no_use_inside(part: dict, path: str) -> None:
    """Refuse a part that holds `use`, at any depth of its rows and swaps."""
    stack = [(part, path)]
    while stack:
        node, npath = stack.pop()
        if "use" in node:
            raise MakerError(_BAD_NESTING, f"{npath}.use", "a part may not hold use")
        children = node.get("items")
        if isinstance(children, list):
            for index, child in enumerate(children):
                if isinstance(child, dict):
                    stack.append((child, f"{npath}.items.{index}"))


def _validate_variants(doc: dict, ctx: _Ctx, card: dict) -> dict:
    """Validate the variants, or the one variant written at the top."""
    top = {"layout", "size", "header", "trailing", "align"} & set(doc)
    if "variants" in doc:
        if top:
            raise MakerError(
                "bad_value", sorted(top)[0], "use variants or layout and size, not both"
            )
        raw = _as_mapping(doc["variants"], "variants")
    elif "layout" in doc:
        size = _required(doc, "size", "")
        match = _SIZE.match(size) if isinstance(size, str) else None
        if match is None:
            raise MakerError("bad_value", "size", "size must be like '2x1'")
        raw = {
            "default": {
                key: doc[key] for key in ("header", "trailing", "align") if key in doc
            }
            | {
                "name": doc["name"],
                "grid": [int(match.group(1)) * 6, int(match.group(2)) * 3],
                "layout": doc["layout"],
            }
        }
    else:
        raise MakerError("missing_key", "variants", "a card needs variants or a layout")
    if not 1 <= len(raw) <= MAX_VARIANTS_2:
        raise MakerError("too_many", "variants", f"1 to {MAX_VARIANTS_2} variants")
    out = {}
    for name, spec in raw.items():
        path = "" if "variants" not in doc else f"variants.{name}"
        if not isinstance(name, str) or not _NAME.match(name):
            raise MakerError("bad_name", path, f"bad name {name!r}")
        out[name] = _variant(spec, path, ctx, card)
    if not any(variant["picker"] for variant in out.values()):
        raise MakerError("bad_value", "variants", "one variant must be in the picker")
    if not any(variant["picker"] and not variant["needs"] for variant in out.values()):
        # A card whose device can do nothing must still have a variant.
        raise MakerError(
            "bad_value", "variants", "one variant in the picker must have no needs"
        )
    return out


def _variant(spec: object, path: str, ctx: _Ctx, card: dict) -> dict:
    """Validate one variant and count its widgets."""
    spec = _as_mapping(spec, path)
    _reject_unknown_keys(
        spec,
        {
            "name",
            "grid",
            "header",
            "trailing",
            "layout",
            "v1",
            "picker",
            "align",
            "needs",
            "needs_text",
        },
        path,
    )
    prefix = f"{path}." if path else ""
    name = _text(_required(spec, "name", path), f"{prefix}name", MAX_LABEL_2)
    # What the device must be able to do for this variant, as for an option.
    needs = spec.get("needs")
    needs = "" if needs is None else _fact(needs, f"{prefix}needs", ctx)
    needs_text = _text(spec.get("needs_text", ""), f"{prefix}needs_text", MAX_HELP_2)
    if needs_text and not needs:
        raise MakerError("bad_value", f"{prefix}needs_text", "needs_text needs 'needs'")
    grid = _required(spec, "grid", path)
    if not isinstance(grid, list) or len(grid) != 2:
        raise MakerError("bad_value", f"{prefix}grid", "grid is [columns, rows]")
    columns = _int(grid[0], f"{prefix}grid.0", 1, 36)
    rows = _int(grid[1], f"{prefix}grid.1", 1, 12)
    header = _choose(spec, "header", HEADER_FORMS, path, "title")
    if rows == 1 and header not in ("chip", "none"):
        raise MakerError(
            "bad_value",
            f"{prefix}header",
            "a card one row high has room for a chip only",
        )
    trailing = _trailing(spec, prefix, header, ctx, card)
    out = {
        "name": name,
        "grid": [columns, rows],
        "header": header,
        "trailing": trailing,
        "picker": _bool(spec.get("picker", True), f"{prefix}picker"),
        "align": _choose(spec, "align", ("top",), path),
        "v1": _v1(spec.get("v1"), f"{prefix}v1"),
        "needs": needs,
        "needs_text": needs_text,
    }
    layout = _required(spec, "layout", path)
    lpath = f"{prefix}layout"
    if not isinstance(layout, list) or not 1 <= len(layout) <= MAX_VARIANT_ITEMS_2:
        raise MakerError(
            "bad_value", lpath, f"a layout has 1 to {MAX_VARIANT_ITEMS_2} items"
        )
    ctx.widgets = 0
    out["layout"] = [
        _item(item, f"{lpath}.{index}", ctx, "top", {})
        for index, item in enumerate(layout)
    ]
    out["widgets"] = ctx.widgets
    return out


def _trailing(
    spec: dict, prefix: str, header: str, ctx: _Ctx, card: dict
) -> dict | None:
    """Validate what a tile header shows at its right."""
    if "trailing" not in spec:
        return None
    tpath = f"{prefix}trailing"
    if header not in ("tile", "tile_v"):
        raise MakerError("bad_value", tpath, "trailing is for the tile headers")
    value = spec["trailing"]
    if value == "switch":
        if card["on"] is None:
            raise MakerError(
                "bad_value", tpath, "a trailing switch needs the card's on"
            )
        return {"form": "switch"}
    if value == "more":
        if not ctx.has_detail:
            raise MakerError("bad_value", tpath, "more needs a detail variant")
        return {"form": "more"}
    if value == "none":
        return None
    if isinstance(value, str) and value in ctx.inputs:
        return {"form": "input", "input": value}
    raise MakerError("bad_value", tpath, "trailing is switch, more, none or an input")


def _v1(value: object, path: str) -> str | None:
    """Validate what a version 1 tablet gets: a schema 1 card or the note."""
    if value is None:
        return None
    if value == "note":
        return value
    return _component_id(value, path)


# ---------------------------------------------------------------- card level


def _card_mark(doc: dict, key: str, ctx: _Ctx) -> dict | None:
    """Mark a card-level live field: an input or a template."""
    if key not in doc:
        return None
    env = {"lookups": _lookup_names(ctx, {}, {})}
    return _mark(doc[key], key, ctx, env)


def _validate_tap(raw: object, ctx: _Ctx) -> dict | None:
    """Validate what a tap on the card may do; the person picks one."""
    if raw is None:
        return None
    tap = _as_mapping(raw, "tap")
    _reject_unknown_keys(tap, {"default", "choices"}, "tap")
    choices = _as_mapping(_required(tap, "choices", "tap"), "tap.choices")
    if not 1 <= len(choices) <= 6:
        raise MakerError("bad_value", "tap.choices", "1 to 6 choices")
    out = []
    for key, spec in choices.items():
        path = f"tap.choices.{key}"
        if not isinstance(key, str) or not _CHOICE_KEY.match(key) or key == "page":
            raise MakerError("bad_value", path, f"bad tap choice {key!r}")
        spec = _as_mapping(spec, path)
        _reject_unknown_keys(spec, {"label", "output", "needs"}, path)
        label = _text(_required(spec, "label", path), f"{path}.label", MAX_LABEL_2)
        needs = spec.get("needs")
        needs = "" if needs is None else _fact(needs, f"{path}.needs", ctx)
        output = spec.get("output")
        if output is None:
            if key == "detail" and not ctx.has_detail:
                raise MakerError("bad_value", path, "the card has no detail variant")
            if key not in ("detail", "none"):
                raise MakerError(
                    "missing_key", f"{path}.output", "this choice needs an output"
                )
        else:
            target = ctx.outputs.get(output) if isinstance(output, str) else None
            if target is None:
                raise MakerError(
                    "unknown_output", f"{path}.output", f"no output named {output!r}"
                )
            if target["kind"] == "action" and target["sensitive"]:
                raise MakerError(
                    "action_not_allowed",
                    f"{path}.output",
                    "a lock or an alarm may not be a card tap",
                )
        entry = {"value": key, "label": label, "needs": needs}
        if output is not None:
            entry["output"] = output
        out.append(entry)
    keys = [entry["value"] for entry in out]
    default = tap.get("default", keys[0])
    if default not in keys:
        raise MakerError("bad_value", "tap.default", f"{default!r} is not a choice")
    return {"default": default, "choices": out}


def _validate_notes(raw: object, ctx: _Ctx) -> list:
    """Validate the notes the form shows at its top."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_NOTES_2:
        raise MakerError("bad_value", "notes", f"at most {MAX_NOTES_2} notes")
    out = []
    for index, note in enumerate(raw):
        path = f"notes.{index}"
        note = _as_mapping(note, path)
        _reject_unknown_keys(note, {"text", "when"}, path)
        out.append(
            {
                "text": _text(
                    _required(note, "text", path), f"{path}.text", MAX_HELP_2
                ),
                "when": _when(note.get("when"), f"{path}.when", ctx),
            }
        )
    return out


def _validate_replaces(raw: object, comp_id: str) -> list:
    """Validate the cards this one replaces in the picker."""
    if raw is None:
        return []
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_REPLACES_2:
        raise MakerError(
            "bad_value", "replaces", f"a list of 1 to {MAX_REPLACES_2} ids"
        )
    out = []
    for index, value in enumerate(raw):
        value = _component_id(value, f"replaces.{index}")
        if value == comp_id or value in out:
            raise MakerError(
                "bad_value", f"replaces.{index}", f"cannot replace {value!r}"
            )
        out.append(value)
    return out


def _preview_value(value: object, depth: int = 0) -> bool:
    """Return True for a scalar, none, or small lists and mappings of them."""
    if value is None or isinstance(value, str | bool | int | float):
        return True
    if depth >= 2:
        return False
    if isinstance(value, list):
        return len(value) <= 64 and all(_preview_value(v, depth + 1) for v in value)
    if isinstance(value, dict):
        return len(value) <= 64 and all(
            isinstance(k, str) and _preview_value(v, depth + 1)
            for k, v in value.items()
        )
    return False


def _validate_preview(raw: object, ctx: _Ctx) -> dict:
    """Validate the example values of the picker and the form."""
    out: dict = {"params": {}, "options": {}, "can": {}, "inputs": {}}
    if raw is None:
        return out
    preview = _as_mapping(raw, "preview")
    _reject_unknown_keys(preview, set(out), "preview")
    for name, value in _as_mapping(
        preview.get("params") or {}, "preview.params"
    ).items():
        path = f"preview.params.{name}"
        param = ctx.params.get(name)
        if param is None:
            raise MakerError("unknown_param", path, f"no param named {name!r}")
        if param["kind"] == "entity":
            ok = isinstance(value, str) or (
                param["multiple"]
                and isinstance(value, list)
                and all(isinstance(v, str) for v in value)
            )
        elif param["kind"] == "number":
            ok = _is_plain_number(value)
        else:
            ok = isinstance(value, str)
        if not ok:
            raise MakerError("bad_value", path, "bad preview value")
        out["params"][name] = value
    for name, value in _as_mapping(
        preview.get("options") or {}, "preview.options"
    ).items():
        path = f"preview.options.{name}"
        option = ctx.options.get(name)
        if option is None:
            raise MakerError("unknown_option", path, f"no option named {name!r}")
        out["options"][name] = check_option_value(option, value, path)
    can = _as_mapping(preview.get("can") or {}, "preview.can")
    for name, value in can.items():
        if (
            not isinstance(name, str)
            or not _NAME.match(name)
            or not _preview_value(value)
        ):
            raise MakerError("bad_value", f"preview.can.{name}", "bad preview fact")
    out["can"] = dict(can)
    for name, value in _as_mapping(
        preview.get("inputs") or {}, "preview.inputs"
    ).items():
        path = f"preview.inputs.{name}"
        if name not in ctx.inputs:
            raise MakerError("unknown_input", path, f"no input named {name!r}")
        if not _preview_value(value):
            raise MakerError("bad_value", path, "unsupported preview value")
        out["inputs"][name] = value
    return out


def _resolve_deferred(ctx: _Ctx) -> None:
    """Check names that only a loop of the layout can give."""
    for entry in ctx.deferred:
        kind, name, path = entry[0], entry[1], entry[2]
        loop = ctx.loops.get(name)
        if loop is None or loop["loop"]["kind"] != "param":
            raise MakerError(
                "unknown_param", path, f"no loop over devices named {name!r}"
            )
        param = ctx.params[loop["loop"]["name"]]
        domain = entry[3] if kind == "loop_entity" and len(entry) > 3 else None
        if domain is not None and param["domains"] != [domain]:
            raise MakerError(
                "domain_mismatch",
                path,
                "every device of the loop must match the action",
            )
        if kind == "output_entity":
            output_name = entry[3].split(".", 1)[1]
            _check_output_kinds(ctx.outputs[output_name], param, path)


# ---------------------------------------------------------------- the file


def validate_component2(doc: dict) -> dict:
    """Validate one schema 2 card file and return its normalised form."""
    if True in doc:
        # YAML 1.1 reads the key `on:` as true. At the top of a card file
        # it can only mean the card-level `on`.
        if "on" in doc:
            raise MakerError("duplicate_name", "on", "on is given twice")
        doc = {("on" if key is True else key): value for key, value in doc.items()}
    _reject_unknown_keys(doc, _TOP_KEYS, "")
    comp_id = _component_id(_required(doc, "id", ""), "id")
    version = _required(doc, "version", "")
    if not isinstance(version, str) or not _VERSION.match(version):
        raise MakerError("bad_value", "version", "version must be like '1.0.0'")
    name = _required(doc, "name", "")
    if not isinstance(name, str) or not name:
        raise MakerError("bad_value", "name", "name must be a non-empty string")
    _text(name, "name", MAX_LABEL_2)
    description = _text(doc.get("description", ""), "description", 160)
    icon = doc.get("icon")
    if icon is not None:
        icon = _validate_icon(icon, "icon")
    group = _choose(doc, "group", CARD_GROUPS, "", "more")
    ctx = _Ctx()
    detail = doc.get("detail")
    ctx.has_detail = detail is not None
    _validate_params(doc.get("params"), ctx)
    _validate_options(doc.get("options"), ctx)
    _validate_inputs(doc.get("inputs"), ctx)
    _validate_outputs(doc.get("outputs"), ctx)
    card = {
        key: _card_mark(doc, key, ctx) for key in ("on", "tint", "state", "unavailable")
    }
    lit = _choose(doc, "lit", LIT_LOOKS, "", "fill")
    tap = _validate_tap(doc.get("tap"), ctx)
    hold = doc.get("hold")
    if hold is not None:
        if hold not in ("detail", "none"):
            raise MakerError("bad_value", "hold", "hold is detail or none")
        if hold == "detail" and not ctx.has_detail:
            raise MakerError("bad_value", "hold", "the card has no detail variant")
    elif ctx.has_detail:
        hold = "detail"
    parts = _validate_parts(doc.get("parts"), ctx)
    variants = _validate_variants(doc, ctx, card)
    if detail is not None and detail not in variants:
        raise MakerError("bad_value", "detail", f"no variant named {detail!r}")
    _resolve_deferred(ctx)
    _check_template_facts(doc, ctx)
    notes = _validate_notes(doc.get("notes"), ctx)
    first = next(v for v in variants.values() if v["picker"])
    columns, rows = first["grid"]
    return {
        "schema": 2,
        "id": comp_id,
        "version": version,
        "name": name,
        "description": description,
        "icon": icon,
        "group": group,
        "replaces": _validate_replaces(doc.get("replaces"), comp_id),
        "v1": _v1(doc.get("v1"), "v1"),
        # The picker's size in today's units, from the first picker variant.
        "size": [min(6, math.ceil(columns / 6)), min(4, math.ceil(rows / 3))],
        "sensitive": any(
            spec["kind"] == "action" and spec["sensitive"]
            for spec in ctx.outputs.values()
        ),
        "uses_inputs": any(
            spec["kind"] == "action" and spec["uses"] for spec in ctx.outputs.values()
        ),
        "params": ctx.params,
        "options": ctx.options,
        "inputs": ctx.inputs,
        "outputs": ctx.outputs,
        **card,
        "lit": lit,
        "tap": tap,
        "hold": hold,
        "parts": parts,
        "variants": variants,
        "detail": detail,
        "notes": notes,
        "preview": _validate_preview(doc.get("preview"), ctx),
    }


def iter_items(component: dict) -> Iterator[tuple[str, dict]]:
    """Yield (path, item) for every item of the parts and variants, nested ones too."""
    stack: list[tuple[str, dict]] = []
    for name, part in component["parts"].items():
        stack.append((f"parts.{name}", part))
    for name, variant in component["variants"].items():
        for index, item in enumerate(variant["layout"]):
            stack.append((f"variants.{name}.layout.{index}", item))
    stack.reverse()
    while stack:
        path, item = stack.pop()
        yield path, item
        children = item.get("items") or []
        for index in range(len(children) - 1, -1, -1):
            stack.append((f"{path}.items.{index}", children[index]))


def data_template_names(component: dict, output: dict) -> set:
    """Return the names a data template of this output may use (C.2.8)."""
    names = set(component["params"]) | set(component["options"])
    names |= {"can", "value", "option"}
    for _path, item in iter_items(component):
        names.update(item.get("vars") or {})
        loop = item.get("loop")
        if loop is not None:
            names.add(loop["as"])
            if loop["kind"] == "param":
                names.add(f"{loop['as']}_can")
    names.update(
        name for name, kind in output.get("uses", {}).items() if kind != "entities"
    )
    return names
