"""Hand-written validators for component, card, style and dashboard data."""

import re

from .const import (
    ACTION_RE,
    ALLOWED_ACTION_DOMAINS,
    ALLOWED_DOMAIN_SERVICES,
    COLOR_RE,
    DATA_KEY_RE,
    DEFAULT_THEME,
    DOMAIN_RE,
    DURATION_RE,
    DURATION_UNITS,
    ENTITY_ID_RE,
    FEEDBACK_MODES,
    FOR_EACH_MAX,
    ICON_RE,
    ID_RE,
    LOCAL_ACTIONS,
    MAX_DATA_KEYS,
    MAX_INPUTS,
    MAX_LAYOUT_ITEMS,
    MAX_OUTPUTS,
    MAX_PARAMS,
    MAX_STRING,
    NAME_RE,
    PAGE_PATH_RE,
    READ_ACTIONS,
    RESERVED_NAMES,
    SENSITIVE_DOMAINS,
    SIZE_RE,
    TARGET_KEYS,
    THEME_IDS,
    VAR_RE,
    VERSION_RE,
)
from .errors import MakerError

_ACTION = re.compile(ACTION_RE)
_COLOR = re.compile(COLOR_RE)
_DATA_KEY = re.compile(DATA_KEY_RE)
_DOMAIN = re.compile(DOMAIN_RE)
_DURATION = re.compile(DURATION_RE)
_ENTITY_ID = re.compile(ENTITY_ID_RE)
_ICON = re.compile(ICON_RE)
_ID = re.compile(ID_RE)
_NAME = re.compile(NAME_RE)
_PAGE_PATH = re.compile(PAGE_PATH_RE)
_SIZE = re.compile(SIZE_RE)
_VAR = re.compile(VAR_RE)
_VERSION = re.compile(VERSION_RE)

_TOP_KEYS = {
    "schema",
    "id",
    "version",
    "name",
    "description",
    "icon",
    "header",
    "size",
    "params",
    "inputs",
    "outputs",
    "layout",
    "preview",
}

_LAYOUT_KEYS = {
    "switch": {"type", "value", "on_tap", "for_each", "as"},
    "slider": {"type", "value", "min", "max", "step", "on_change", "for_each", "as"},
    "thermostat": {
        "type",
        "value",
        "min",
        "max",
        "step",
        "on_change",
        "side",
        "for_each",
        "as",
    },
    "chart": {"type", "value", "kind", "side", "for_each", "as"},
    "button": {"type", "on_tap", "text", "icon", "confirm", "for_each", "as"},
    "label": {"type", "text", "size", "on_tap", "confirm", "for_each", "as"},
    "image": {"type", "value", "on_tap", "confirm", "side", "for_each", "as"},
}

_STYLE_KEYS = {"theme", "color", "gradient", "transparency", "accent"}


def _is_template(value: object) -> bool:
    """Return True when value is a string containing a template marker."""
    return isinstance(value, str) and ("{{" in value or "{%" in value)


def _is_plain_number(value: object) -> bool:
    """Return True for ints and floats that are not booleans."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def _as_mapping(value: object, path: str) -> dict:
    """Return value as a dict or raise not_a_mapping."""
    if not isinstance(value, dict):
        raise MakerError("not_a_mapping", path, "expected a mapping")
    return value


def _reject_unknown_keys(mapping: dict, allowed: set, path: str) -> None:
    """Raise unknown_key on the first key not in the allowed set."""
    for key in mapping:
        if key not in allowed:
            location = f"{path}.{key}" if path else str(key)
            raise MakerError("unknown_key", location, f"unknown key {key!r}")


def _required(mapping: dict, key: str, path: str) -> object:
    """Return mapping[key] or raise missing_key."""
    if key not in mapping:
        location = f"{path}.{key}" if path else key
        raise MakerError("missing_key", location, f"missing required key {key!r}")
    return mapping[key]


def _check_text(value: object, path: str) -> str:
    """Return value as a string, enforcing the maximum string length."""
    if not isinstance(value, str):
        raise MakerError("bad_value", path, "expected a string")
    if len(value) > MAX_STRING:
        raise MakerError("too_long", path, f"strings may be {MAX_STRING} characters")
    return value


def _as_number(value: object, path: str) -> float:
    """Return value as a float; booleans do not count as numbers."""
    if not _is_plain_number(value):
        raise MakerError("bad_value", path, "expected a number")
    return float(value)


def _parse_duration(value: object, path: str, low: int, high: int) -> int:
    """Parse a duration into seconds and enforce an inclusive range."""
    if isinstance(value, bool):
        raise MakerError("bad_value", path, "expected a duration")
    if isinstance(value, int):
        seconds = value
    elif isinstance(value, str):
        match = _DURATION.match(value)
        if match is None:
            raise MakerError("bad_value", path, f"bad duration {value!r}")
        seconds = int(match.group(1)) * DURATION_UNITS[match.group(2)]
    else:
        raise MakerError("bad_value", path, "expected a duration")
    if not low <= seconds <= high:
        raise MakerError("bad_value", path, f"duration must be {low}..{high} seconds")
    return seconds


def _match_var(value: object, path: str) -> str:
    """Match a '{{ name }}' reference and return the referenced name."""
    if isinstance(value, str):
        match = _VAR.match(value)
        if match is not None:
            return match.group(1)
    raise MakerError("bad_value", path, f"expected '{{{{ name }}}}', got {value!r}")


def _check_name(name: object, path: str) -> str:
    """Validate a param, input, output or loop name and return it."""
    if not isinstance(name, str) or not _NAME.match(name):
        raise MakerError("bad_name", path, f"bad name {name!r}")
    if name in RESERVED_NAMES:
        raise MakerError("bad_name", path, f"name {name!r} is reserved")
    return name


def _validate_icon(value: object, path: str) -> str:
    """Validate an mdi icon reference and return it."""
    if not isinstance(value, str) or not _ICON.match(value):
        raise MakerError("bad_value", path, f"bad icon {value!r}")
    return value


def _require_single_entity_param(params: dict, name: str, path: str) -> dict:
    """Return the named single-entity param or raise unknown_param."""
    param = params.get(name)
    if param is None or param["kind"] != "entity" or param["multiple"]:
        raise MakerError("unknown_param", path, f"no single-entity param {name!r}")
    return param


def _validate_data(data: object, path: str, *, allow_templates: bool) -> dict:
    """Validate an action data mapping and return it unchanged."""
    data = _as_mapping(data, path)
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
        if isinstance(value, bool | int | float):
            continue
        if isinstance(value, str):
            _check_text(value, kpath)
            if key != "entity_id" and not allow_templates and _is_template(value):
                raise MakerError("bad_value", kpath, "templates are not allowed here")
            continue
        raise MakerError("bad_value", kpath, "data values must be scalar")
    return data


def _validate_params(raw: object, used: set) -> dict:
    """Validate the params section and return it normalised."""
    if raw is None:
        return {}
    params = _as_mapping(raw, "params")
    if len(params) > MAX_PARAMS:
        raise MakerError("too_many", "params", f"at most {MAX_PARAMS} params")
    out = {}
    for name, spec in params.items():
        path = f"params.{name}"
        _check_name(name, path)
        if name in used:
            raise MakerError("duplicate_name", path, f"duplicate name {name!r}")
        used.add(name)
        out[name] = _validate_param(spec, path)
    return out


def _validate_param(spec: object, path: str) -> dict:
    """Validate one param definition and return it normalised."""
    spec = _as_mapping(spec, path)
    if "domain" in spec:
        _reject_unknown_keys(spec, {"domain", "multiple"}, path)
        domain = spec["domain"]
        if not isinstance(domain, str) or not _DOMAIN.match(domain):
            raise MakerError("bad_value", f"{path}.domain", f"bad domain {domain!r}")
        multiple = spec.get("multiple", False)
        if not isinstance(multiple, bool):
            raise MakerError("bad_value", f"{path}.multiple", "expected a boolean")
        return {"kind": "entity", "domain": domain, "multiple": multiple}
    if "type" in spec:
        ptype = spec["type"]
        if ptype == "page":
            _reject_unknown_keys(spec, {"type"}, path)
            return {"kind": "page"}
        if ptype == "number":
            _reject_unknown_keys(spec, {"type", "default", "min", "max"}, path)
            default = _as_number(_required(spec, "default", path), f"{path}.default")
            low, high = spec.get("min"), spec.get("max")
            return {
                "kind": "number",
                "default": default,
                "min": None if low is None else _as_number(low, f"{path}.min"),
                "max": None if high is None else _as_number(high, f"{path}.max"),
            }
        raise MakerError("bad_value", f"{path}.type", f"unknown param type {ptype!r}")
    raise MakerError("missing_key", path, "param needs 'domain' or 'type'")


def _validate_inputs(raw: object, used: set, params: dict) -> dict:
    """Validate the inputs section and return it normalised."""
    if raw is None:
        return {}
    inputs = _as_mapping(raw, "inputs")
    if len(inputs) > MAX_INPUTS:
        raise MakerError("too_many", "inputs", f"at most {MAX_INPUTS} inputs")
    out = {}
    for name, spec in inputs.items():
        path = f"inputs.{name}"
        _check_name(name, path)
        if name in used:
            raise MakerError("duplicate_name", path, f"duplicate name {name!r}")
        used.add(name)
        out[name] = _validate_input(spec, path, params)
    return out


def _validate_input(spec: object, path: str, params: dict) -> dict:
    """Validate one input definition and return it normalised."""
    if isinstance(spec, str):
        return {"kind": "template", "template": _check_text(spec, path)}
    spec = _as_mapping(spec, path)
    if "action" in spec:
        return _validate_action_input(spec, path, params)
    source = spec.get("source")
    if source == "recorder":
        return _validate_history_input(spec, path, params)
    if source == "camera":
        return _validate_camera_input(spec, path, params)
    raise MakerError("bad_value", path, "unknown input source")


def _validate_history_input(spec: dict, path: str, params: dict) -> dict:
    """Validate a recorder history input and return it normalised."""
    _reject_unknown_keys(spec, {"source", "entity", "hours"}, path)
    epath = f"{path}.entity"
    name = _match_var(_required(spec, "entity", path), epath)
    _require_single_entity_param(params, name, epath)
    hours = spec.get("hours", 24)
    if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= 168:
        raise MakerError("bad_value", f"{path}.hours", "hours must be 1..168")
    return {"kind": "history", "param": name, "hours": hours}


def _validate_camera_input(spec: dict, path: str, params: dict) -> dict:
    """Validate a camera snapshot input and return it normalised."""
    _reject_unknown_keys(spec, {"source", "entity", "refresh"}, path)
    epath = f"{path}.entity"
    name = _match_var(_required(spec, "entity", path), epath)
    _require_single_entity_param(params, name, epath)
    refresh = _parse_duration(spec.get("refresh", 10), f"{path}.refresh", 5, 3600)
    return {"kind": "camera", "param": name, "refresh": refresh}


def _validate_action_input(spec: dict, path: str, params: dict) -> dict:
    """Validate a read-action input and return it normalised."""
    _reject_unknown_keys(spec, {"action", "data", "result", "refresh"}, path)
    action = _required(spec, "action", path)
    apath = f"{path}.action"
    if not isinstance(action, str):
        raise MakerError("bad_value", apath, "action must be a string")
    if action not in READ_ACTIONS:
        raise MakerError(
            "action_not_allowed", apath, f"action {action!r} is not read-only"
        )
    data = _validate_data(
        _required(spec, "data", path), f"{path}.data", allow_templates=False
    )
    epath = f"{path}.data.entity_id"
    name = _match_var(_required(data, "entity_id", f"{path}.data"), epath)
    param = _require_single_entity_param(params, name, epath)
    if param["domain"] != action.split(".", 1)[0]:
        raise MakerError("domain_mismatch", epath, "param domain must match action")
    result = _check_text(_required(spec, "result", path), f"{path}.result")
    refresh = _parse_duration(spec.get("refresh", 1800), f"{path}.refresh", 60, 86400)
    rest = {key: value for key, value in data.items() if key != "entity_id"}
    return {
        "kind": "action",
        "action": action,
        "param": name,
        "data": rest,
        "result": result,
        "refresh": refresh,
    }


def _validate_outputs(raw: object, params: dict) -> tuple[dict, list]:
    """Validate the outputs section; also collect deferred entity references."""
    if raw is None:
        return {}, []
    outputs = _as_mapping(raw, "outputs")
    if len(outputs) > MAX_OUTPUTS:
        raise MakerError("too_many", "outputs", f"at most {MAX_OUTPUTS} outputs")
    out = {}
    pending = []
    for name, spec in outputs.items():
        path = f"outputs.{name}"
        _check_name(name, path)
        normalised, deferred = _validate_output(spec, path, params)
        out[name] = normalised
        if deferred is not None:
            pending.append((name, deferred, f"{path}.data.entity_id"))
    return out, pending


def _validate_output(spec: object, path: str, params: dict) -> tuple[dict, str | None]:
    """Validate one output; return it and any deferred entity reference."""
    spec = _as_mapping(spec, path)
    if "action" in spec:
        if "local" in spec:
            raise MakerError("bad_value", path, "output cannot mix action and local")
        return _validate_action_output(spec, path, params)
    if "local" in spec:
        return _validate_local_output(spec, path, params), None
    raise MakerError("missing_key", path, "output needs 'action' or 'local'")


def is_allowed_action(action: str) -> bool:
    """Return True when an output may call this <domain>.<service> action."""
    domain, _, service = action.partition(".")
    if domain not in ALLOWED_ACTION_DOMAINS:
        return False
    services = ALLOWED_DOMAIN_SERVICES.get(domain)
    return services is None or service in services


def _validate_action_output(
    spec: dict, path: str, params: dict
) -> tuple[dict, str | None]:
    """Validate a service-call output and return it with any deferred reference."""
    _reject_unknown_keys(spec, {"action", "data", "feedback"}, path)
    action = _required(spec, "action", path)
    apath = f"{path}.action"
    if not isinstance(action, str) or not _ACTION.match(action):
        raise MakerError("bad_value", apath, f"bad action {action!r}")
    domain = action.split(".", 1)[0]
    if domain not in ALLOWED_ACTION_DOMAINS:
        raise MakerError(
            "action_not_allowed", apath, f"domain {domain!r} is not allowed"
        )
    if not is_allowed_action(action):
        services = ", ".join(sorted(ALLOWED_DOMAIN_SERVICES[domain]))
        raise MakerError(
            "action_not_allowed", apath, f"{domain} outputs may use only {services}"
        )
    feedback = _required(spec, "feedback", path)
    if feedback not in FEEDBACK_MODES:
        raise MakerError("bad_value", f"{path}.feedback", f"bad feedback {feedback!r}")
    if domain in SENSITIVE_DOMAINS and feedback != "confirm":
        raise MakerError("confirm_required", path, "sensitive domains need confirm")
    data = _validate_data(
        _required(spec, "data", path), f"{path}.data", allow_templates=True
    )
    epath = f"{path}.data.entity_id"
    ref = _match_var(_required(data, "entity_id", f"{path}.data"), epath)
    param = params.get(ref)
    deferred = None
    if param is not None and param["kind"] == "entity" and not param["multiple"]:
        if param["domain"] != domain:
            raise MakerError("domain_mismatch", epath, "param domain must match")
    else:
        # The name may be a loop variable declared by a layout item; resolve
        # it once the layout is parsed.
        deferred = ref
    normalised = {
        "kind": "action",
        "action": action,
        "data": dict(data),
        "feedback": feedback,
        "entity_ref": ref,
    }
    return normalised, deferred


def _validate_local_output(spec: dict, path: str, params: dict) -> dict:
    """Validate a local (frontend) output and return it normalised."""
    _reject_unknown_keys(spec, {"local", "page"}, path)
    local = _required(spec, "local", path)
    if local not in LOCAL_ACTIONS:
        raise MakerError("bad_value", f"{path}.local", f"bad local action {local!r}")
    page = spec.get("page")
    if local != "go_to_page":
        if page is not None:
            raise MakerError(
                "bad_value", f"{path}.page", "only go_to_page takes a page"
            )
        return {"kind": "local", "local": local, "page": None}
    if page is None:
        raise MakerError("missing_key", f"{path}.page", "go_to_page needs 'page'")
    ppath = f"{path}.page"
    page = _check_text(page, ppath)
    match = _VAR.match(page)
    if match is not None:
        target = params.get(match.group(1))
        if target is None or target["kind"] != "page":
            raise MakerError("unknown_param", ppath, "no page param with that name")
    elif _PAGE_PATH.match(page) is None:
        raise MakerError("bad_value", ppath, f"bad page path {page!r}")
    return {"kind": "local", "local": local, "page": page}


def _validate_layout(
    raw: object, params: dict, inputs: dict, outputs: dict, used: set
) -> list:
    """Validate the layout list and return it normalised."""
    if not isinstance(raw, list):
        raise MakerError("bad_value", "layout", "layout must be a list")
    if not raw:
        raise MakerError("bad_value", "layout", "layout needs at least one item")
    if len(raw) > MAX_LAYOUT_ITEMS:
        raise MakerError("too_many", "layout", f"at most {MAX_LAYOUT_ITEMS} items")
    as_loops: dict = {}
    return [
        _validate_layout_item(item, index, params, inputs, outputs, used, as_loops)
        for index, item in enumerate(raw)
    ]


def _validate_layout_item(
    item: object,
    index: int,
    params: dict,
    inputs: dict,
    outputs: dict,
    used: set,
    as_loops: dict,
) -> dict:
    """Validate one layout item and return it normalised with defaults filled."""
    path = f"layout.{index}"
    item = _as_mapping(item, path)
    itype = item.get("type")
    if not isinstance(itype, str) or itype not in _LAYOUT_KEYS:
        raise MakerError("bad_value", f"{path}.type", f"unknown layout type {itype!r}")
    _reject_unknown_keys(item, _LAYOUT_KEYS[itype], path)
    for_each, as_name = _validate_loop(item, path, params, used, as_loops)
    body = _validate_item_body(item, itype, path, inputs, outputs)
    body["for_each"] = for_each
    body["as"] = as_name
    return body


def _validate_loop(
    item: dict, path: str, params: dict, used: set, as_loops: dict
) -> tuple[str | None, str | None]:
    """Validate the for_each/as pair of a layout item."""
    for_each = item.get("for_each")
    as_name = item.get("as")
    if for_each is None:
        if as_name is not None:
            raise MakerError("bad_value", f"{path}.as", "'as' needs 'for_each'")
        return None, None
    if not isinstance(for_each, str):
        raise MakerError(
            "unknown_param", f"{path}.for_each", "for_each must name a param"
        )
    param = params.get(for_each)
    if param is None or param["kind"] != "entity" or not param["multiple"]:
        raise MakerError(
            "unknown_param",
            f"{path}.for_each",
            f"no multiple-entity param {for_each!r}",
        )
    if as_name is None:
        raise MakerError("missing_key", f"{path}.as", "for_each needs 'as'")
    _check_name(as_name, f"{path}.as")
    if as_name in used:
        raise MakerError("duplicate_name", f"{path}.as", f"duplicate name {as_name!r}")
    previous = as_loops.setdefault(as_name, for_each)
    if previous != for_each:
        raise MakerError(
            "duplicate_name", f"{path}.as", f"name {as_name!r} already used"
        )
    return for_each, as_name


def _validate_item_body(
    item: dict, itype: str, path: str, inputs: dict, outputs: dict
) -> dict:
    """Validate the type-specific body of a layout item."""
    if itype == "switch":
        return {
            "type": "switch",
            "value": _item_value(item, path, itype, inputs),
            "on_tap": _item_trigger(item, "on_tap", path, outputs, required=False),
        }
    if itype in ("slider", "thermostat"):
        on_change = _item_trigger(item, "on_change", path, outputs, required=False)
        if on_change is not None and outputs[on_change]["kind"] != "action":
            raise MakerError(
                "bad_value", f"{path}.on_change", "on_change needs an action output"
            )
        body = {
            "type": itype,
            "value": _item_value(item, path, itype, inputs),
            "min": _item_bound(item, "min", 0.0, path),
            "max": _item_bound(item, "max", 100.0, path),
            "step": _item_bound(item, "step", 1.0 if itype == "slider" else 0.5, path),
            "on_change": on_change,
        }
        if itype == "thermostat":
            body["side"] = _item_side(item, path)
        return body
    if itype == "chart":
        kind = item.get("kind", "line")
        if kind not in ("line", "bars"):
            raise MakerError("bad_value", f"{path}.kind", "kind must be line or bars")
        return {
            "type": "chart",
            "value": _item_value(item, path, itype, inputs),
            "kind": kind,
            "side": _item_side(item, path),
        }
    if itype == "button":
        on_tap = _item_trigger(item, "on_tap", path, outputs, required=True)
        text = _item_text(item, "text", path)
        icon = item.get("icon")
        if icon is not None:
            icon = _validate_icon(icon, f"{path}.icon")
        if text is None and icon is None:
            raise MakerError("missing_key", path, "button needs 'text' or 'icon'")
        return {
            "type": "button",
            "on_tap": on_tap,
            "text": text,
            "icon": icon,
            "confirm": _item_confirm(item, path, on_tap),
        }
    if itype == "label":
        text = _check_text(_required(item, "text", path), f"{path}.text")
        size = item.get("size", "m")
        if size not in ("s", "m", "l"):
            raise MakerError("bad_value", f"{path}.size", "size must be s, m or l")
        on_tap = _item_trigger(item, "on_tap", path, outputs, required=False)
        return {
            "type": "label",
            "text": text,
            "size": size,
            "on_tap": on_tap,
            "confirm": _item_confirm(item, path, on_tap),
        }
    if itype == "image":
        on_tap = _item_trigger(item, "on_tap", path, outputs, required=False)
        return {
            "type": "image",
            "value": _item_value(item, path, itype, inputs),
            "on_tap": on_tap,
            "confirm": _item_confirm(item, path, on_tap),
            "side": _item_side(item, path),
        }
    raise MakerError("bad_value", f"{path}.type", f"unknown layout type {itype!r}")


def _item_value(item: dict, path: str, itype: str, inputs: dict) -> dict:
    """Validate the value key of a layout item."""
    value = _required(item, "value", path)
    vpath = f"{path}.value"
    if isinstance(value, str):
        if value in inputs:
            kind = inputs[value]["kind"]
            if kind in ("history", "action") and itype != "chart":
                raise MakerError(
                    "bad_value", vpath, f"input {value!r} only feeds a chart"
                )
            return {"input": value}
        if _is_template(value):
            return {"template": _check_text(value, vpath)}
    raise MakerError(
        "unknown_input", vpath, "value must name an input or be a template"
    )


def _item_bound(item: dict, key: str, default: float, path: str) -> object:
    """Validate a numeric or template min/max/step key."""
    value = item.get(key)
    if value is None:
        return default
    bpath = f"{path}.{key}"
    if _is_plain_number(value):
        return float(value)
    if isinstance(value, str) and _is_template(value):
        return {"template": _check_text(value, bpath)}
    raise MakerError("bad_value", bpath, "expected a number or template")


def _item_trigger(
    item: dict, key: str, path: str, outputs: dict, *, required: bool
) -> str | None:
    """Validate an on_tap/on_change output reference."""
    raw = item.get(key)
    tpath = f"{path}.{key}"
    if raw is None:
        if required:
            raise MakerError("missing_key", tpath, f"missing required key {key!r}")
        return None
    if not isinstance(raw, str) or raw not in outputs:
        raise MakerError("unknown_output", tpath, f"no output named {raw!r}")
    return raw


def _item_text(item: dict, key: str, path: str) -> str | None:
    """Validate an optional literal-or-template text key."""
    if key not in item:
        return None
    return _check_text(item[key], f"{path}.{key}")


def _item_confirm(item: dict, path: str, on_tap: str | None) -> str | None:
    """Validate the confirm message, which requires on_tap."""
    confirm = _item_text(item, "confirm", path)
    if confirm is not None and on_tap is None:
        raise MakerError("bad_value", f"{path}.confirm", "confirm needs on_tap")
    return confirm


def _item_side(item: dict, path: str) -> bool:
    """Validate the optional side flag."""
    side = item.get("side", False)
    if not isinstance(side, bool):
        raise MakerError("bad_value", f"{path}.side", "side must be a boolean")
    return side


def _resolve_pending(pending: list, outputs: dict, params: dict, layout: list) -> None:
    """Resolve deferred output entity references through layout loop variables."""
    for out_name, ref, path in pending:
        domain = outputs[out_name]["action"].split(".", 1)[0]
        users = [
            item
            for item in layout
            if out_name in (item.get("on_tap"), item.get("on_change"))
        ]
        if not users:
            raise MakerError("unknown_param", path, f"no loop variable {ref!r}")
        for item in users:
            if item["as"] != ref:
                raise MakerError("unknown_param", path, f"no loop variable {ref!r}")
            if params[item["for_each"]]["domain"] != domain:
                raise MakerError("domain_mismatch", path, f"{ref!r} is not a {domain}")


def _is_sensitive(outputs: dict) -> bool:
    """Return True when any output targets a sensitive domain."""
    return any(
        spec["kind"] == "action"
        and spec["action"].split(".", 1)[0] in SENSITIVE_DOMAINS
        for spec in outputs.values()
    )


def _is_entity_preview(value: object, multiple: bool) -> bool:
    """Return True when a preview value matches an entity param's shape."""
    if multiple:
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return isinstance(value, str)


def _is_preview_value(value: object) -> bool:
    """Return True for a string, number, boolean or list of numbers."""
    if isinstance(value, str | bool | int | float):
        return True
    return isinstance(value, list) and all(_is_plain_number(item) for item in value)


def _validate_preview(raw: object, params: dict, inputs: dict) -> dict:
    """Validate the optional preview block of example values."""
    if raw is None:
        return {"params": {}, "inputs": {}}
    preview = _as_mapping(raw, "preview")
    _reject_unknown_keys(preview, {"params", "inputs"}, "preview")
    return {
        "params": _validate_preview_params(preview.get("params"), params),
        "inputs": _validate_preview_inputs(preview.get("inputs"), inputs),
    }


def _validate_preview_params(raw: object, params: dict) -> dict:
    """Validate preview example values for params."""
    if raw is None:
        return {}
    values = _as_mapping(raw, "preview.params")
    out = {}
    for name, value in values.items():
        path = f"preview.params.{name}"
        param = params.get(name)
        if param is None:
            raise MakerError("unknown_param", path, f"no param named {name!r}")
        kind = param["kind"]
        if kind == "entity" and not _is_entity_preview(value, param["multiple"]):
            raise MakerError("bad_value", path, "bad entity preview value")
        if kind == "number" and not _is_plain_number(value):
            raise MakerError("bad_value", path, "expected a number")
        if kind == "page" and not isinstance(value, str):
            raise MakerError("bad_value", path, "expected a page path")
        out[name] = value
    return out


def _validate_preview_inputs(raw: object, inputs: dict) -> dict:
    """Validate preview example values for inputs."""
    if raw is None:
        return {}
    values = _as_mapping(raw, "preview.inputs")
    out = {}
    for name, value in values.items():
        path = f"preview.inputs.{name}"
        if name not in inputs:
            raise MakerError("unknown_input", path, f"no input named {name!r}")
        if not _is_preview_value(value):
            raise MakerError("bad_value", path, "unsupported preview value")
        out[name] = value
    return out


def _validate_colour(value: object, path: str) -> str:
    """Validate a #RRGGBB colour and return it in upper case."""
    if not isinstance(value, str) or not _COLOR.match(value):
        raise MakerError("bad_value", path, f"bad colour {value!r}")
    return value.upper()


def _validate_gradient(raw: object) -> dict:
    """Validate a gradient block and fill in its default direction."""
    path = "style.gradient"
    gradient = _as_mapping(raw, path)
    _reject_unknown_keys(gradient, {"to", "direction"}, path)
    to = _validate_colour(_required(gradient, "to", path), f"{path}.to")
    direction = gradient.get("direction", "vertical")
    if direction not in ("vertical", "horizontal"):
        raise MakerError(
            "bad_value", f"{path}.direction", "direction must be vertical or horizontal"
        )
    return {"to": to, "direction": direction}


def validate_component(raw: object) -> dict:
    """Validate one component document and return its normalised form."""
    doc = _as_mapping(raw, "")
    _reject_unknown_keys(doc, _TOP_KEYS, "")
    schema_version = doc.get("schema", 1)
    if isinstance(schema_version, bool) or schema_version != 1:
        raise MakerError("bad_value", "schema", "schema must be 1")
    comp_id = _required(doc, "id", "")
    if not isinstance(comp_id, str) or len(comp_id) > 64 or not _ID.match(comp_id):
        raise MakerError("bad_id", "id", f"bad id {comp_id!r}")
    version = _required(doc, "version", "")
    if not isinstance(version, str) or not _VERSION.match(version):
        raise MakerError("bad_value", "version", "version must be like '1.0.0'")
    name = _required(doc, "name", "")
    if not isinstance(name, str) or not name:
        raise MakerError("bad_value", "name", "name must be a non-empty string")
    if len(name) > 40:
        raise MakerError("too_long", "name", "name is too long")
    description = doc.get("description", "")
    if not isinstance(description, str):
        raise MakerError("bad_value", "description", "description must be a string")
    if len(description) > 160:
        raise MakerError("too_long", "description", "description is too long")
    icon = doc.get("icon")
    if icon is not None:
        icon = _validate_icon(icon, "icon")
    header = doc.get("header", True)
    if not isinstance(header, bool):
        raise MakerError("bad_value", "header", "header must be a boolean")
    size_raw = _required(doc, "size", "")
    if not isinstance(size_raw, str) or not _SIZE.match(size_raw):
        raise MakerError("bad_value", "size", "size must be like '2x1'")
    used: set = set()
    params = _validate_params(doc.get("params"), used)
    inputs = _validate_inputs(doc.get("inputs"), used, params)
    outputs, pending = _validate_outputs(doc.get("outputs"), params)
    layout = _validate_layout(
        _required(doc, "layout", ""), params, inputs, outputs, used
    )
    _resolve_pending(pending, outputs, params, layout)
    preview = _validate_preview(doc.get("preview"), params, inputs)
    return {
        "schema": 1,
        "id": comp_id,
        "version": version,
        "name": name,
        "description": description,
        "icon": icon,
        "header": header,
        "size": [int(size_raw[0]), int(size_raw[2])],
        "sensitive": _is_sensitive(outputs),
        "params": params,
        "inputs": inputs,
        "outputs": outputs,
        "layout": layout,
        "preview": preview,
    }


def _entity_config_value(value: object, spec: dict, path: str) -> str:
    """Validate one entity id against an entity param's domain."""
    if not isinstance(value, str) or not _ENTITY_ID.match(value):
        raise MakerError("bad_value", path, f"bad entity id {value!r}")
    if value.split(".", 1)[0] != spec["domain"]:
        raise MakerError("bad_value", path, f"expected a {spec['domain']} entity")
    return value


def _card_param_value(spec: dict, value: object, path: str) -> tuple[bool, object]:
    """Return (present, value) for one card config param."""
    kind = spec["kind"]
    if kind == "entity":
        if spec["multiple"]:
            if value is None or value == "" or value == []:
                return False, None
            items = [value] if isinstance(value, str) else value
            if not isinstance(items, list) or not items:
                raise MakerError("bad_value", path, "expected a list of entity ids")
            if len(items) > FOR_EACH_MAX:
                raise MakerError("bad_value", path, f"at most {FOR_EACH_MAX} entities")
            return True, [_entity_config_value(item, spec, path) for item in items]
        if value is None or value == "":
            return False, None
        return True, _entity_config_value(value, spec, path)
    if kind == "number":
        if value is None:
            return True, spec["default"]
        number = _as_number(value, path)
        low, high = spec["min"], spec["max"]
        too_low = low is not None and number < low
        too_high = high is not None and number > high
        if too_low or too_high:
            raise MakerError("bad_value", path, "number outside its allowed range")
        return True, number
    if value is None or value == "":
        return True, ""
    if not isinstance(value, str) or not _PAGE_PATH.match(value):
        raise MakerError("bad_value", path, f"bad page path {value!r}")
    return True, value


def _card_title(cfg: dict) -> str | None:
    """Validate the optional card title."""
    title = cfg.get("title")
    if title is None:
        return None
    if not isinstance(title, str):
        raise MakerError("bad_value", "title", "title must be a string")
    if len(title) > 60:
        raise MakerError("too_long", "title", "title is too long")
    return title or None


def _grid_columns(grid: dict, size: list) -> int | str:
    """Resolve the card width in grid columns."""
    columns = grid.get("columns")
    if isinstance(columns, bool):
        columns = None
    if isinstance(columns, int) and 1 <= columns <= 36:
        return columns
    if columns == "full":
        return "full"
    return size[0] * 6


def _grid_rows(grid: dict, size: list) -> int:
    """Resolve the card height in grid rows."""
    rows = grid.get("rows")
    if isinstance(rows, bool):
        rows = None
    if isinstance(rows, int) and 1 <= rows <= 12:
        return rows
    return size[1] * 3


def validate_card_config(component: dict, raw: object) -> dict:
    """Validate a stored card config against its component definition."""
    cfg = _as_mapping(raw, "")
    raw_params = cfg.get("params")
    if raw_params is None:
        raw_params = {}
    if not isinstance(raw_params, dict):
        raise MakerError("not_a_mapping", "params", "params must be a mapping")
    comp_params = component["params"]
    for key in raw_params:
        if key not in comp_params:
            raise MakerError("unknown_param", f"params.{key}", f"unknown param {key!r}")
    params: dict = {}
    missing: list = []
    for pname, spec in comp_params.items():
        present, parsed = _card_param_value(
            spec, raw_params.get(pname), f"params.{pname}"
        )
        if present:
            params[pname] = parsed
        elif spec["kind"] == "entity":
            missing.append(pname)
    grid = cfg.get("grid_options")
    if not isinstance(grid, dict):
        grid = {}
    return {
        "params": params,
        "missing": missing,
        "title": _card_title(cfg),
        "style": validate_style(cfg.get("style")),
        "columns": _grid_columns(grid, component["size"]),
        "rows": _grid_rows(grid, component["size"]),
    }


def validate_style(raw: object) -> dict:
    """Validate an element style block and return it normalised."""
    if raw is None:
        return {}
    style = _as_mapping(raw, "style")
    _reject_unknown_keys(style, _STYLE_KEYS, "style")
    out = {}
    if "theme" in style:
        theme = style["theme"]
        if theme not in THEME_IDS:
            raise MakerError("bad_value", "style.theme", f"unknown theme {theme!r}")
        out["theme"] = theme
    if "color" in style:
        out["color"] = _validate_colour(style["color"], "style.color")
    if "gradient" in style:
        out["gradient"] = _validate_gradient(style["gradient"])
    if "transparency" in style:
        transparency = style["transparency"]
        if (
            isinstance(transparency, bool)
            or not isinstance(transparency, int)
            or not 0 <= transparency <= 100
        ):
            raise MakerError("bad_value", "style.transparency", "expected 0..100")
        out["transparency"] = transparency
    if "accent" in style:
        out["accent"] = _validate_colour(style["accent"], "style.accent")
    return out


def validate_dashboard_options(raw: object) -> dict:
    """Validate the apollo_tab block of a dashboard configuration."""
    options = _as_mapping(raw, "apollo_tab")
    _reject_unknown_keys(options, {"version", "theme"}, "apollo_tab")
    version = options.get("version", 1)
    if isinstance(version, bool) or version != 1:
        raise MakerError("bad_value", "apollo_tab.version", "version must be 1")
    theme = options.get("theme", DEFAULT_THEME)
    if theme not in THEME_IDS:
        raise MakerError("bad_value", "apollo_tab.theme", f"unknown theme {theme!r}")
    return {"version": 1, "theme": theme}


def is_tab_dashboard(config: object) -> bool:
    """Return True when config carries an apollo_tab options mapping."""
    return isinstance(config, dict) and isinstance(config.get("apollo_tab"), dict)


def component_templates(component: dict) -> list[str]:
    """Collect every template string that must pass a syntax check."""
    templates: list[str] = []
    for spec in component["inputs"].values():
        if spec["kind"] == "template":
            templates.append(spec["template"])
        elif spec["kind"] == "action":
            templates.append(spec["result"])
    for spec in component["outputs"].values():
        if spec["kind"] != "action":
            continue
        for value in spec["data"].values():
            if _is_template(value):
                templates.append(value)
    for item in component["layout"]:
        for key in ("value", "min", "max", "step", "text", "confirm"):
            value = item.get(key)
            if isinstance(value, dict):
                value = value.get("template")
            if _is_template(value):
                templates.append(value)
    return templates
