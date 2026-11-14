"""What a device can do, as plain facts (C.2.4 of the cards spec).

Home Assistant's side (facts.py) hands in what it knows about one entity:

    {"domain": "light",
     "registry": {"capabilities": {...}, "features": ["EFFECT"],
                  "device_class": None, "icon": None, "unit": None} or None,
     "state": {"attributes": {...}, "features": ["EFFECT"]} or None}

The feature names are the member names of Home Assistant's own feature
enums; facts.py reads the bits through those enums. Each value is taken
from the registry entry first and from the state's attributes after, so a
layout does not change while a device is away.

Everything a device reports is data. Lists keep each entry's whole text;
nothing here or later treats an entry as template source. Nothing here
renders, and nothing imports Home Assistant.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping

from .const import ALLOWED_SERVICES, ENTITY_ID_RE, ICON_RE, KELVIN_RANGE

_ENTITY_ID = re.compile(ENTITY_ID_RE)
_ICON = re.compile(ICON_RE)

# Lists are cut to this many entries.
MAX_LIST = 64
# An entry longer than this, in UTF-8 bytes, is left out, never cut.
MAX_ENTRY_BYTES = 255
# A colour temperature limit outside KELVIN_RANGE, or a pair that is not
# low below high, gives this pair (the owner's lamp reports 15 K).
DEFAULT_KELVIN = (2000, 6500)
# Home Assistant's own defaults where a device says nothing.
DEFAULT_CLIMATE = (7, 35, 0.5)
DEFAULT_NUMBER = (0, 100, 1)
DEFAULT_FAN_STEP = 1
# Effect names that mean "no effect".
NO_EFFECT = frozenset({"None", "none", "off"})
# Stands for "every fact of this device" in a set of fact names.
ALL = "*"

_COLOUR_MODES = frozenset({"hs", "xy", "rgb", "rgbw", "rgbww"})
_NO_BRIGHTNESS_MODES = frozenset({"onoff", "unknown"})
_ASKING_COVERS = frozenset({"garage", "gate", "door"})

# The fixed table of facts per domain: yes or no facts, lists, numbers.
FACTS = {
    "light": (
        ("brightness", "colour", "temperature", "effects"),
        ("effect_list",),
        ("min_kelvin", "max_kelvin"),
    ),
    "cover": (("position", "stop", "tilt", "asks"), (), ()),
    "climate": (
        ("target", "range", "off"),
        ("modes", "presets", "fan_modes"),
        ("min", "max", "step"),
    ),
    "fan": (("speed", "oscillate", "direction"), ("presets",), ("step",)),
    "media_player": (
        (
            "pause",
            "previous",
            "next",
            "volume",
            "mute",
            "seek",
            "power",
            "shuffle",
            "repeat",
            "group",
        ),
        ("sources",),
        (),
    ),
    "alarm_control_panel": (
        ("home", "away", "night", "vacation", "needs_code"),
        (),
        (),
    ),
    "lock": (("open",), (), ()),
    "select": ((), ("options",), ()),
    "input_select": ((), ("options",), ()),
    "number": ((), (), ("min", "max", "step", "unit")),
    "input_number": ((), (), ("min", "max", "step", "unit")),
    "vacuum": (("start", "pause", "stop", "dock", "locate"), ("fan_speeds",), ()),
}
# Facts every entity has.
ANY_FACTS = ("toggle", "icon", "kind")

# Feature enum members, by name, that make a yes or no fact true.
_FEATURE_FACTS = {
    "cover": {
        "position": ("SET_POSITION",),
        "stop": ("STOP",),
        "tilt": ("OPEN_TILT", "CLOSE_TILT", "SET_TILT_POSITION"),
    },
    "climate": {
        "target": ("TARGET_TEMPERATURE",),
        "range": ("TARGET_TEMPERATURE_RANGE",),
    },
    "fan": {
        "speed": ("SET_SPEED",),
        "oscillate": ("OSCILLATE",),
        "direction": ("DIRECTION",),
    },
    "media_player": {
        "pause": ("PAUSE",),
        "previous": ("PREVIOUS_TRACK",),
        "next": ("NEXT_TRACK",),
        "volume": ("VOLUME_SET",),
        "mute": ("VOLUME_MUTE",),
        "seek": ("SEEK",),
        "power": ("TURN_ON", "TURN_OFF"),
        "shuffle": ("SHUFFLE_SET",),
        "repeat": ("REPEAT_SET",),
        "group": ("GROUPING",),
    },
    "alarm_control_panel": {
        "home": ("ARM_HOME",),
        "away": ("ARM_AWAY",),
        "night": ("ARM_NIGHT",),
        "vacation": ("ARM_VACATION",),
    },
    "lock": {"open": ("OPEN",)},
    "vacuum": {
        "start": ("START",),
        "pause": ("PAUSE",),
        "stop": ("STOP",),
        "dock": ("RETURN_HOME",),
        "locate": ("LOCATE",),
    },
}

# The icon of an entity that names none, by domain and device class. Only
# names of the contract's icon set.
_DEFAULT_ICONS = {
    "light": "mdi:lightbulb",
    "switch": "mdi:toggle-switch",
    "input_boolean": "mdi:toggle-switch",
    "fan": "mdi:fan",
    "cover": "mdi:blinds",
    "climate": "mdi:thermostat",
    "media_player": "mdi:speaker",
    "lock": "mdi:lock",
    "alarm_control_panel": "mdi:shield-home",
    "vacuum": "mdi:robot-vacuum",
    "sensor": "mdi:gauge",
    "number": "mdi:numeric",
    "input_number": "mdi:numeric",
    "select": "mdi:dots-horizontal",
    "input_select": "mdi:dots-horizontal",
    "scene": "mdi:palette",
    "script": "mdi:script-text-outline",
    "button": "mdi:gesture-tap-button",
    "input_button": "mdi:gesture-tap-button",
    "person": "mdi:account",
    "weather": "mdi:weather-partly-cloudy",
    "siren": "mdi:bell-ring",
    "humidifier": "mdi:air-humidifier",
    "water_heater": "mdi:water-boiler",
    "camera": "mdi:cctv",
    "valve": "mdi:water-pump",
}
_DEFAULT_CLASS_ICONS = {
    ("cover", "garage"): "mdi:garage",
    ("cover", "gate"): "mdi:gate",
    ("cover", "door"): "mdi:door",
    ("cover", "window"): "mdi:window-closed",
    ("cover", "shutter"): "mdi:window-shutter",
    ("media_player", "tv"): "mdi:television",
    ("sensor", "temperature"): "mdi:thermometer",
    ("sensor", "humidity"): "mdi:water-percent",
    ("sensor", "battery"): "mdi:battery",
    ("sensor", "power"): "mdi:lightning-bolt",
    ("sensor", "energy"): "mdi:lightning-bolt",
    ("sensor", "carbon_dioxide"): "mdi:molecule-co2",
    ("binary_sensor", "door"): "mdi:door",
    ("binary_sensor", "garage_door"): "mdi:garage",
    ("binary_sensor", "window"): "mdi:window-closed",
    ("binary_sensor", "motion"): "mdi:motion-sensor",
    ("binary_sensor", "occupancy"): "mdi:motion-sensor",
    ("binary_sensor", "smoke"): "mdi:smoke-detector",
    ("binary_sensor", "moisture"): "mdi:water",
}


# The icon of an entity by its state, for the source state_icon (C.2.8).
# Keyed (domain, device class, state); a class of None fits any class the
# table does not name, a state of None any state. Only names of the
# contract's icon set.
_STATE_ICONS = {
    ("light", None, "on"): "mdi:lightbulb-on",
    ("light", None, "off"): "mdi:lightbulb-outline",
    ("switch", None, "on"): "mdi:toggle-switch",
    ("switch", None, "off"): "mdi:toggle-switch-off",
    ("input_boolean", None, "on"): "mdi:toggle-switch",
    ("input_boolean", None, "off"): "mdi:toggle-switch-off",
    ("fan", None, "on"): "mdi:fan",
    ("fan", None, "off"): "mdi:fan-off",
    ("siren", None, "on"): "mdi:bell-ring",
    ("siren", None, "off"): "mdi:bell-off",
    ("cover", "garage", "open"): "mdi:garage-open",
    ("cover", "garage", "opening"): "mdi:garage-open",
    ("cover", "garage", "closing"): "mdi:garage-open",
    ("cover", "garage", "closed"): "mdi:garage",
    ("cover", "gate", "open"): "mdi:gate-open",
    ("cover", "gate", "opening"): "mdi:gate-open",
    ("cover", "gate", "closing"): "mdi:gate-open",
    ("cover", "gate", "closed"): "mdi:gate",
    ("cover", "door", "open"): "mdi:door-open",
    ("cover", "door", "opening"): "mdi:door-open",
    ("cover", "door", "closing"): "mdi:door-open",
    ("cover", "door", "closed"): "mdi:door-closed",
    ("cover", "window", "open"): "mdi:window-open",
    ("cover", "window", "closed"): "mdi:window-closed",
    ("cover", "shutter", "open"): "mdi:window-shutter-open",
    ("cover", "shutter", "closed"): "mdi:window-shutter",
    ("cover", None, "open"): "mdi:blinds-open",
    ("cover", None, "opening"): "mdi:blinds-open",
    ("cover", None, "closing"): "mdi:blinds-open",
    ("cover", None, "closed"): "mdi:blinds",
    ("lock", None, "locked"): "mdi:lock",
    ("lock", None, "unlocked"): "mdi:lock-open",
    ("lock", None, "open"): "mdi:lock-open",
    ("lock", None, "opening"): "mdi:lock-open",
    ("lock", None, "jammed"): "mdi:lock-alert",
    ("lock", None, None): "mdi:lock-outline",
    ("alarm_control_panel", None, "disarmed"): "mdi:shield-off",
    ("alarm_control_panel", None, "armed_home"): "mdi:shield-home",
    ("alarm_control_panel", None, "armed_away"): "mdi:shield-lock",
    ("alarm_control_panel", None, "armed_night"): "mdi:shield-lock",
    ("alarm_control_panel", None, "armed_vacation"): "mdi:shield-lock",
    ("alarm_control_panel", None, "armed_custom_bypass"): "mdi:shield-check",
    ("alarm_control_panel", None, "triggered"): "mdi:shield-alert",
    ("alarm_control_panel", None, None): "mdi:shield-outline",
    ("binary_sensor", "door", "on"): "mdi:door-open",
    ("binary_sensor", "door", "off"): "mdi:door-closed",
    ("binary_sensor", "garage_door", "on"): "mdi:garage-open",
    ("binary_sensor", "garage_door", "off"): "mdi:garage",
    ("binary_sensor", "window", "on"): "mdi:window-open",
    ("binary_sensor", "window", "off"): "mdi:window-closed",
    ("binary_sensor", "motion", "on"): "mdi:walk",
    ("binary_sensor", "occupancy", "on"): "mdi:walk",
    ("media_player", "tv", "playing"): "mdi:television-play",
    ("media_player", "tv", None): "mdi:television",
    ("media_player", None, "playing"): "mdi:music",
    ("media_player", None, "paused"): "mdi:pause",
    ("climate", None, "heat"): "mdi:fire",
    ("climate", None, "cool"): "mdi:snowflake",
    ("climate", None, "heat_cool"): "mdi:autorenew",
    ("climate", None, "auto"): "mdi:autorenew",
    ("climate", None, "dry"): "mdi:water-percent",
    ("climate", None, "fan_only"): "mdi:fan",
    ("climate", None, "off"): "mdi:power",
    ("person", None, "home"): "mdi:home",
    ("person", None, "not_home"): "mdi:home-export-outline",
    ("weather", None, "clear-night"): "mdi:weather-night",
    ("weather", None, "cloudy"): "mdi:weather-cloudy",
    ("weather", None, "exceptional"): "mdi:weather-cloudy-alert",
    ("weather", None, "fog"): "mdi:weather-fog",
    ("weather", None, "hail"): "mdi:weather-hail",
    ("weather", None, "lightning"): "mdi:weather-lightning",
    ("weather", None, "lightning-rainy"): "mdi:weather-lightning-rainy",
    ("weather", None, "partlycloudy"): "mdi:weather-partly-cloudy",
    ("weather", None, "pouring"): "mdi:weather-pouring",
    ("weather", None, "rainy"): "mdi:weather-rainy",
    ("weather", None, "snowy"): "mdi:weather-snowy",
    ("weather", None, "snowy-rainy"): "mdi:weather-snowy-rainy",
    ("weather", None, "sunny"): "mdi:weather-sunny",
    ("weather", None, "windy"): "mdi:weather-windy",
    ("weather", None, "windy-variant"): "mdi:weather-windy-variant",
}
# Battery levels, low to high, for a sensor of class battery.
_BATTERY_ICONS = (
    (10, "mdi:battery-alert"),
    (30, "mdi:battery-20"),
    (70, "mdi:battery-50"),
)


def state_icon(domain: str, device_class: object, state: object) -> str | None:
    """Return the icon for an entity's kind, device class and state (C.2.8).

    A fixed table; an unknown state gives the kind's own icon. Nothing the
    device reports is used as an icon name.
    """
    kind = device_class if isinstance(device_class, str) else None
    value = state if isinstance(state, str) else None
    if domain == "sensor" and kind == "battery" and value is not None:
        try:
            level = float(value)
        except ValueError:
            level = math.nan
        if math.isfinite(level):
            for limit, icon in _BATTERY_ICONS:
                if level <= limit:
                    return icon
            return "mdi:battery"
    for key in (
        (domain, kind, value),
        (domain, None, value),
        (domain, kind, None),
        (domain, None, None),
    ):
        icon = _STATE_ICONS.get(key)
        if icon is not None:
            return icon
    return _DEFAULT_CLASS_ICONS.get((domain, kind)) or _DEFAULT_ICONS.get(domain)


# ---------------------------------------------------------------- one entity


def facts_of(raw: Mapping) -> dict:
    """Return the facts of one entity from what Home Assistant knows of it.

    Every fact of the domain's row is there, so a missing device gives
    the least: no extras, empty lists and the default numbers.
    """
    domain = raw.get("domain") if isinstance(raw.get("domain"), str) else ""
    registry = raw.get("registry") if isinstance(raw.get("registry"), Mapping) else {}
    state = raw.get("state") if isinstance(raw.get("state"), Mapping) else {}
    caps = registry.get("capabilities")
    caps = caps if isinstance(caps, Mapping) else {}
    attrs = state.get("attributes")
    attrs = attrs if isinstance(attrs, Mapping) else {}

    def value(key: str) -> object:
        """Return the registry's value of a key, else the state's."""
        found = caps.get(key)
        return attrs.get(key) if found is None else found

    def meta(registry_key: str, attribute: str) -> object:
        """Return a registry field, else the state attribute."""
        found = registry.get(registry_key)
        return attrs.get(attribute) if found is None else found

    features = _names(registry.get("features")) or _names(state.get("features"))
    kind = _text(meta("device_class", "device_class"))
    out: dict = {
        "toggle": "toggle" in ALLOWED_SERVICES.get(domain, ()),
        "icon": _icon(meta("icon", "icon"), domain, kind),
        "kind": kind,
    }
    for fact, members in _FEATURE_FACTS.get(domain, {}).items():
        out[fact] = any(member in features for member in members)
    builder = _DOMAIN_FACTS.get(domain)
    if builder is not None:
        builder(out, value, meta, features, kind)
    return out


def _light(out: dict, value, meta, features: set, kind: str | None) -> None:
    """Add the facts of a light."""
    modes = set(_list(value("supported_color_modes")))
    effect_list = _list(value("effect_list"), drop=NO_EFFECT)
    out["brightness"] = bool(modes - _NO_BRIGHTNESS_MODES)
    out["colour"] = bool(modes & _COLOUR_MODES)
    out["temperature"] = "color_temp" in modes
    out["effects"] = "EFFECT" in features and bool(effect_list)
    out["min_kelvin"], out["max_kelvin"] = _kelvin_pair(
        value("min_color_temp_kelvin"), value("max_color_temp_kelvin")
    )
    out["effect_list"] = effect_list


def _cover(out: dict, value, meta, features: set, kind: str | None) -> None:
    """Add the facts of a cover."""
    out["asks"] = kind in _ASKING_COVERS


def _climate(out: dict, value, meta, features: set, kind: str | None) -> None:
    """Add the facts of a climate device."""
    modes = _list(value("hvac_modes"))
    out["off"] = "TURN_OFF" in features or "off" in modes
    out["modes"] = modes
    out["presets"] = _list(value("preset_modes"))
    out["fan_modes"] = _list(value("fan_modes"))
    low, high, step = DEFAULT_CLIMATE
    out["min"], out["max"] = _number_pair(
        value("min_temp"), value("max_temp"), (low, high)
    )
    out["step"] = _step(value("target_temp_step"), step)


def _fan(out: dict, value, meta, features: set, kind: str | None) -> None:
    """Add the facts of a fan."""
    out["presets"] = _list(value("preset_modes"))
    step = _step(value("percentage_step"), DEFAULT_FAN_STEP)
    out["step"] = step if step <= 100 else DEFAULT_FAN_STEP


def _media(out: dict, value, meta, features: set, kind: str | None) -> None:
    """Add the facts of a media player."""
    out["sources"] = _list(value("source_list"))


def _alarm(out: dict, value, meta, features: set, kind: str | None) -> None:
    """Add the facts of an alarm panel."""
    out["needs_code"] = value("code_format") is not None


def _options(out: dict, value, meta, features: set, kind: str | None) -> None:
    """Add the facts of a select."""
    out["options"] = _list(value("options"))


def _number(out: dict, value, meta, features: set, kind: str | None) -> None:
    """Add the facts of a number."""
    low, high, step = DEFAULT_NUMBER
    out["min"], out["max"] = _number_pair(value("min"), value("max"), (low, high))
    out["step"] = _step(value("step"), step)
    out["unit"] = _text(meta("unit", "unit_of_measurement")) or ""


def _vacuum(out: dict, value, meta, features: set, kind: str | None) -> None:
    """Add the facts of a vacuum."""
    out["fan_speeds"] = _list(value("fan_speed_list"))


_DOMAIN_FACTS = {
    "light": _light,
    "cover": _cover,
    "climate": _climate,
    "fan": _fan,
    "media_player": _media,
    "alarm_control_panel": _alarm,
    "select": _options,
    "input_select": _options,
    "number": _number,
    "input_number": _number,
    "vacuum": _vacuum,
}


# ---------------------------------------------------------------- cleaning


def _names(value: object) -> set:
    """Return a set of feature names."""
    if not isinstance(value, list | tuple | set | frozenset):
        return set()
    return {item for item in value if isinstance(item, str)}


def _fits(text: str) -> bool:
    """Return True for a text of at most MAX_ENTRY_BYTES bytes."""
    return len(text.encode("utf-8", "surrogatepass")) <= MAX_ENTRY_BYTES


def _text(value: object) -> str | None:
    """Return a short plain text, or None."""
    if not isinstance(value, str) or not value or not _fits(value):
        return None
    return str.__str__(value)


def _list(value: object, drop: frozenset = frozenset()) -> list:
    """Return up to MAX_LIST whole texts, each once, in the device's order."""
    if not isinstance(value, list | tuple):
        return []
    out: list = []
    for item in value:
        if not isinstance(item, str) or not item or item in drop:
            continue
        text = str.__str__(item)
        if not _fits(text) or text in out:
            continue
        out.append(text)
        if len(out) == MAX_LIST:
            break
    return out


def _real(value: object) -> float | None:
    """Return a finite number, never a yes or no."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(value):
        return None
    return value


def _whole(value: float) -> int | float:
    """Return a number as an int when it is whole."""
    return int(value) if float(value).is_integer() else value


def _kelvin_pair(low: object, high: object) -> tuple[int, int]:
    """Return a clean colour temperature range in whole kelvin."""
    limits_low, limits_high = KELVIN_RANGE
    pair = []
    for value in (low, high):
        number = _real(value)
        if number is None or not limits_low <= number <= limits_high:
            return DEFAULT_KELVIN
        pair.append(math.floor(number + 0.5))
    if pair[0] >= pair[1]:
        return DEFAULT_KELVIN
    return pair[0], pair[1]


def _number_pair(low: object, high: object, default: tuple) -> tuple:
    """Return a range with low below high, or the default pair."""
    low_n, high_n = _real(low), _real(high)
    if low_n is None or high_n is None or low_n >= high_n:
        return default
    return _whole(low_n), _whole(high_n)


def _step(value: object, default: float) -> int | float:
    """Return a step above 0, or the default."""
    number = _real(value)
    if number is None or number <= 0:
        return default
    return _whole(number)


def _icon(value: object, domain: str, kind: str | None) -> str | None:
    """Return the entity's own icon, else the default for its kind."""
    if isinstance(value, str) and _ICON.match(value) and _fits(value):
        return str.__str__(value)
    return _DEFAULT_CLASS_ICONS.get((domain, kind)) or _DEFAULT_ICONS.get(domain)


# ---------------------------------------------------------------- a card


def facts_named(component: Mapping) -> dict:
    """Return the facts a schema 2 card names, by entity param.

    The key "" stands for the first entity param that has a value (the
    `can.<name>` of the file). A set that holds ALL means every fact of
    that param's devices: a template sees all of `can`. A schema 1 card
    names none.
    """
    if component.get("schema") != 2:
        return {}
    params = component.get("params") or {}
    entity_params = [
        name for name, spec in params.items() if spec.get("kind") == "entity"
    ]
    if not entity_params:
        return {}
    several = [name for name in entity_params if params[name].get("multiple")]
    out: dict[str, set] = {"": {"icon"}}

    def add(param: str, fact: str) -> None:
        """Note one fact of one param."""
        out.setdefault(param, set()).add(fact)

    def name(text: str) -> None:
        """Note a `can.<what>` or `can.<param>.<what>`."""
        parts = text.split(".")
        if len(parts) == 3:
            add(parts[1], parts[2])
        elif parts[1] in entity_params:
            add(parts[1], ALL)
        else:
            add("", parts[1])

    def everything() -> None:
        """Note every fact of every device."""
        for param in ["", *entity_params]:
            add(param, ALL)

    stack: list = [
        value for key, value in component.items() if key not in ("preview", "params")
    ]
    while stack:
        value = stack.pop()
        if isinstance(value, Mapping):
            if value.get("form") == "lookup":
                looked = value.get("name")
                key = value.get("key")
                if looked == "can" and isinstance(key, str):
                    name(f"can.{key}")
                elif isinstance(looked, str) and looked.endswith("_can"):
                    for param in several:
                        add(param, key if isinstance(key, str) else ALL)
            stack.extend(value.values())
        elif isinstance(value, list | tuple):
            stack.extend(value)
        elif isinstance(value, str):
            match = _FACT_TERM.match(value)
            if match is not None:
                name(match.group(1))
            elif ("{{" in value or "{%" in value) and _CAN_WORD.search(value):
                everything()
    return {param: frozenset(facts) for param, facts in out.items()}


_FACT_TERM = re.compile(
    r"^!?(can\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?)(?:!?=[a-z0-9_|]+)?$"
)
# `can` or a loop's `<as>_can` read inside a template.
_CAN_WORD = re.compile(r"(?<![A-Za-z0-9_])can(?![A-Za-z0-9_])|_can(?![A-Za-z0-9_])")


def param_entities(component: Mapping, params: object) -> dict[str, list]:
    """Return the entity ids of each entity param with a value, in order."""
    out: dict[str, list] = {}
    if not isinstance(params, Mapping):
        return out
    for name, spec in (component.get("params") or {}).items():
        if spec.get("kind") != "entity":
            continue
        value = params.get(name)
        items = [value] if isinstance(value, str) else value
        if not isinstance(items, list):
            continue
        ids = [
            item for item in items if isinstance(item, str) and _ENTITY_ID.match(item)
        ]
        if ids:
            out[name] = ids
    return out


def _least(entity_id: str) -> dict:
    """Return the facts of an entity nothing is known of."""
    return facts_of({"domain": entity_id.split(".", 1)[0]})


def card_facts(component: Mapping, params: object, facts: Mapping) -> dict:
    """Return the `can` and `has` of one card (C.7).

    The facts of the first entity param that has a value sit at the top of
    `can`; every entity param with a value is also there under its own
    name, as a list in the param's order when it takes several devices.
    """
    entities = param_entities(component, params)
    can: dict = {}

    def of(entity_id: str) -> dict:
        """Return one device's facts."""
        found = facts.get(entity_id)
        return dict(found) if isinstance(found, Mapping) else _least(entity_id)

    if entities:
        can.update(of(next(iter(entities.values()))[0]))
    specs = component.get("params") or {}
    for name, ids in entities.items():
        if specs[name].get("multiple"):
            can[name] = [of(entity_id) for entity_id in ids]
        else:
            can[name] = of(ids[0])
    has = {}
    raw = params if isinstance(params, Mapping) else {}
    for name, spec in specs.items():
        if spec.get("kind") == "entity":
            has[name] = name in entities
        else:
            has[name] = raw.get(name) not in (None, "", [])
    return {"can": can, "has": has}


# ---------------------------------------------------------------- a dashboard

_CARD_TAG = "custom:apollo-tab-card"
_ALIAS_PREFIX = "custom:apollo-tab-el-"


def _cards(config: object) -> Iterable[dict]:
    """Yield every card of the sections views, as the converter reads them."""
    if not isinstance(config, Mapping):
        return
    views = config.get("views")
    for view in views if isinstance(views, list) else []:
        if not isinstance(view, Mapping) or view.get("type") != "sections":
            continue
        sections = view.get("sections")
        for section in sections if isinstance(sections, list) else []:
            if not isinstance(section, Mapping):
                continue
            cards = section.get("cards")
            for card in cards if isinstance(cards, list) else []:
                if isinstance(card, dict):
                    yield card


def _component_of(card: dict, components: Mapping) -> Mapping | None:
    """Return the card file a dashboard card uses, or None."""
    ctype = card.get("type")
    component_id = None
    if ctype == _CARD_TAG:
        component_id = card.get("component")
    elif isinstance(ctype, str) and ctype.startswith(_ALIAS_PREFIX):
        tag = ctype[len(_ALIAS_PREFIX) :]
        component_id = next(
            (cid for cid in components if cid.replace("/", "-") == tag), None
        )
    if not isinstance(component_id, str):
        return None
    return components.get(component_id)


def dashboard_facts(config: object, components: Mapping) -> dict[str, frozenset]:
    """Return, per entity, the facts the dashboard's cards name.

    Every entity of a schema 2 card's entity params is there, with an empty
    set when no card names a fact of it.
    """
    out: dict[str, set] = {}
    for card in _cards(config):
        component = _component_of(card, components)
        if component is None or component.get("schema") != 2:
            continue
        entities = param_entities(component, card.get("params"))
        named = facts_named(component)
        first = next(iter(entities.values()))[0] if entities else None
        for param, ids in entities.items():
            for entity_id in ids:
                out.setdefault(entity_id, set()).update(named.get(param, ()))
        if first is not None:
            out[first].update(named.get("", ()))
    return {entity_id: frozenset(names) for entity_id, names in out.items()}


def entities_of(config: object, components: Mapping) -> list[str]:
    """Return the entities a dashboard needs facts for, sorted."""
    return sorted(dashboard_facts(config, components))


def project(facts: Mapping | None, names: Iterable[str]) -> dict:
    """Return only the named facts; ALL keeps them all."""
    if facts is None:
        return {}
    names = set(names)
    if ALL in names:
        return dict(facts)
    return {name: facts.get(name) for name in sorted(names)}
