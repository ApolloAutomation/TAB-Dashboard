"""What a call may send and what a change may carry (C.2.8, C.5; contract 7.3).

Pure: no Home Assistant and no rendering. live.py renders the templates this
module says to render and hands each result back here to be typed. The rules:

- A data value that is exactly `{{ name }}` or `{{ name.key }}`, with at most
  one of the filters int, float, round and rgb, is a reference: the
  variable's value is passed with its own type, never printed and read back.
- Any other template is rendered to text. A plain decimal number becomes
  that number, True and False become yes and no, everything else stays
  text. Nothing is read back as a list, a mapping or none.
- A key whose value is none (a reference) or the empty text (a template) is
  left out of the call; never entity_id.
- entity_id is one text, or a list of 1 to 16 texts.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .const import COLOUR_DATA_KEYS, CONFIRM_COVER_CLASSES, SENSITIVE_DOMAINS
from .device import num

# The filters a reference may carry; each is worked out here, not by Jinja.
REF_FILTERS = ("int", "float", "round", "rgb")
_REFERENCE = re.compile(
    r"^\{\{\s*([a-z][a-z0-9_]*)(?:\.([a-z][a-z0-9_]*))?"
    r"\s*(?:\|\s*(int|float|round|rgb)\s*)?\}\}$"
)
_DECIMAL = re.compile(r"^-?[0-9]+(?:\.[0-9]+)?$")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ENTITY_ID = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
_WORD = r"(?<![A-Za-z0-9_]){}(?![A-Za-z0-9_])"

# entity_id holds at most this many devices.
MAX_CALL_ENTITIES = 16
# A value inside a `uses` number stays within this.
MAX_USES_NUMBER = 1e9
# A change is on the step grid when it is this close to min + k * step.
STEP_SLACK = 0.0015
# Defaults of a slider's or a thermostat's range (contract 4.3).
RANGE_DEFAULTS = {"min": 0, "max": 100, "step": 1}

# Left out of the call: what a reference gives as none, or a template as "".
LEFT_OUT = object()


class NotAllowed(Exception):
    """A value that may not be sent; live.py answers not_allowed."""


def reference(text: object) -> tuple[str, str | None, str | None] | None:
    """Return (name, key, filter) of a reference, else None."""
    if not isinstance(text, str):
        return None
    match = _REFERENCE.match(text)
    return match.groups() if match else None


def is_template(value: object) -> bool:
    """Return whether a data value is a template of the card file's own text."""
    return isinstance(value, str) and ("{{" in value or "{%" in value)


def mentions(name: str, text: str) -> bool:
    """Return whether a template text names this variable."""
    return re.search(_WORD.format(re.escape(name)), text) is not None


def lookup(variables: dict, name: str, key: str | None) -> Any:
    """Return a variable's value, or its key's; None when there is none."""
    value = variables.get(name)
    if key is None:
        return value
    return value.get(key) if isinstance(value, dict) else None


def _number(value: Any) -> float | None:
    """Return a finite number from a number or a plain decimal text."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str) and _DECIMAL.match(value.strip()):
        number = float(value.strip())
    else:
        return None
    return number if math.isfinite(number) else None


def rgb(value: Any) -> list[int] | None:
    """Return [r, g, b] of a colour number or a #RRGGBB text, else None."""
    if isinstance(value, int) and not isinstance(value, bool):
        if 0 <= value <= 0xFFFFFF:
            return [value >> 16, (value >> 8) & 255, value & 255]
        return None
    if isinstance(value, float) and value.is_integer():
        return rgb(int(value))
    if isinstance(value, str) and _HEX.match(value):
        return [int(value[i : i + 2], 16) for i in (1, 3, 5)]
    if (
        isinstance(value, list)
        and len(value) == 3
        and all(
            isinstance(part, int) and not isinstance(part, bool) and 0 <= part <= 255
            for part in value
        )
    ):
        return list(value)
    return None


def apply_filter(value: Any, name: str | None) -> Any:
    """Apply the one filter a reference may carry; none stays none."""
    if name is None or value is None:
        return value
    if name == "rgb":
        return rgb(value)
    number = _number(value)
    if number is None:
        return None
    if name == "int":
        return int(number)
    if name == "round":
        # Halves go up, so 2.5 is 3, as a person reads it.
        return math.floor(number + 0.5)
    return number


def typed_text(text: str) -> Any:
    """Type the text a template rendered to: a number, yes or no, or text."""
    stripped = text.strip()
    if _DECIMAL.match(stripped):
        number = float(stripped)
        if not math.isfinite(number):
            return text
        return int(stripped) if re.fullmatch(r"-?[0-9]+", stripped) else number
    if stripped == "True":
        return True
    if stripped == "False":
        return False
    return text


def uses_value(kind: str, value: Any) -> Any:
    """Type the last value of an input that an output lists in `uses`.

    number: finite and within 1e9, else none. bool: yes or no, else none.
    entities: the list as it is (a text is a list of one), else an empty
    list. Nothing is dropped or cut here: entity_list refuses the whole
    list when one entry is not an entity id or there are more than 16.
    """
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            number = _number(value) if isinstance(value, str) else None
        else:
            try:
                number = float(value) if math.isfinite(value) else None
            except OverflowError:
                # An integer too large for a float.
                number = None
        if number is None or abs(number) > MAX_USES_NUMBER:
            return None
        return int(number) if number.is_integer() else number
    if kind == "bool":
        if isinstance(value, bool):
            return value
        if value in ("True", "true", "on"):
            return True
        if value in ("False", "false", "off"):
            return False
        return None
    if isinstance(value, str):
        return [value]
    return list(value) if isinstance(value, list | tuple) else []


def scalar_or_colour(key: str, value: Any) -> Any:
    """Check one typed data value; return it or LEFT_OUT, or raise NotAllowed."""
    if value is None:
        return LEFT_OUT
    if isinstance(value, dict):
        raise NotAllowed(f"{key} may not hold a mapping")
    if isinstance(value, list | tuple):
        if key not in COLOUR_DATA_KEYS:
            raise NotAllowed(f"{key} may not hold a list")
        if not 1 <= len(value) <= 4 or not all(
            isinstance(entry, int | float)
            and not isinstance(entry, bool)
            and math.isfinite(entry)
            for entry in value
        ):
            raise NotAllowed(f"{key} must be a list of numbers")
        return list(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise NotAllowed(f"{key} is not a finite number")
    if isinstance(value, str | int | float | bool):
        return value
    raise NotAllowed(f"{key} holds a value that cannot be sent")


def colour_entry(key: str, value: Any) -> int | float:
    """Check one entry of a colour list: it must end as a number."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
    ):
        raise NotAllowed(f"every entry of {key} must be a number")
    return value


def entity_list(value: Any) -> tuple[list[str], bool] | None:
    """Return (entity ids, was a list) of a rendered entity_id, else None.

    One text, or a list of 1 to 16 texts. None, "", [], a list in a list, a
    mapping and a text that only reads like a list are refused.
    """
    if isinstance(value, str):
        return ([value], False) if _ENTITY_ID.match(value) else None
    if isinstance(value, list | tuple):
        if not 1 <= len(value) <= MAX_CALL_ENTITIES:
            return None
        if not all(isinstance(item, str) and _ENTITY_ID.match(item) for item in value):
            return None
        return list(value), True
    return None


def needs_question(feedback: str | None, domain: str, device_class: Any) -> bool:
    """Return whether a call on one entity asks first (C.2.8, "The question")."""
    if feedback == "confirm" or domain in SENSITIVE_DOMAINS:
        return True
    return domain == "cover" and device_class in CONFIRM_COVER_CLASSES


def check_choice(value: Any, count: int) -> bool:
    """Return whether a change of a choice names one of count options."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    if not math.isfinite(value) or value != math.floor(value):
        return False
    return 0 <= value < count


def check_change(widget: dict, value: Any, live) -> bool:
    """Return whether a change of a slider or a thermostat may run (contract 7.3).

    widget holds `min`, `max` and `step` as numbers or `{"s": n}`; live(n)
    returns the value last sent to the tablet for slot n, or None when none
    was sent. A step of 0 or less has no grid: only the range counts.
    Every limit counts in wire form (num), as the tablet holds it.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    if not math.isfinite(value):
        return False

    def limit(key: str) -> float | None:
        field = widget.get(key, RANGE_DEFAULTS[key])
        if isinstance(field, dict):
            field = live(field.get("s"))
        if isinstance(field, bool) or not isinstance(field, int | float):
            return None
        return num(field) if math.isfinite(field) else None

    low, high, step = limit("min"), limit("max"), limit("step")
    if low is None or high is None or step is None:
        return False
    if not low <= value <= high:
        return False
    if step <= 0 or value == high:
        return True
    steps = (value - low) / step
    if not math.isfinite(steps):
        return False
    count = math.floor(steps + 0.5)
    return abs(low + count * step - value) <= STEP_SLACK
