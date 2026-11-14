"""Values of the schema 2 sources that need no template (cards spec C.2.8).

colour and state_icon follow the entity's state. clock and media_position
are worked out at the moment of every send (C.5): the tablet counts on from
the moment of a write (contract 4.4), so their slots are sent again even
when the value is the same.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.util import color as color_util, dt as dt_util

from .maker.features import state_icon

# Kinds of slot this module works out.
SOURCE_KINDS = frozenset({"colour", "state_icon", "clock", "media_position"})
# Kinds whose value is worked out at every send and sent even when equal.
TIMED_KINDS = frozenset({"clock", "media_position"})
# A clock slot is sent again this often (C.5).
CLOCK_RESEND_S = 600


def _rgb_number(rgb: Any) -> int | None:
    """Return [r, g, b] as one number 0xRRGGBB, or None."""
    if not isinstance(rgb, list | tuple) or len(rgb) != 3:
        return None
    parts = []
    for part in rgb:
        if isinstance(part, bool) or not isinstance(part, int | float):
            return None
        if not math.isfinite(part) or not 0 <= part <= 255:
            return None
        parts.append(math.floor(part + 0.5))
    return (parts[0] << 16) | (parts[1] << 8) | parts[2]


def _hue(state: State) -> float | None:
    """Return the hue of a light's colour, from hs_color or rgb_color."""
    hs = state.attributes.get("hs_color")
    if isinstance(hs, list | tuple) and len(hs) == 2:
        hue = hs[0]
        if isinstance(hue, int | float) and not isinstance(hue, bool):
            return float(hue) if math.isfinite(hue) else None
    number = _rgb_number(state.attributes.get("rgb_color"))
    if number is None:
        return None
    hue, _sat = color_util.color_RGB_to_hs(
        number >> 16, (number >> 8) & 255, number & 255
    )
    return hue


def colour_value(state: State | None, of: str) -> int | None:
    """Return a light's colour as one number, or None (off, or no colour).

    of "rgb": its rgb_color. of "hue": the colour of its hue at full
    strength.
    """
    if state is None or state.state != "on":
        return None
    if of == "hue":
        hue = _hue(state)
        if hue is None:
            return None
        return _rgb_number(list(color_util.color_hs_to_RGB(hue % 360, 100)))
    return _rgb_number(state.attributes.get("rgb_color"))


def state_icon_value(state: State | None, domain: str) -> str | None:
    """Return the icon for the entity's kind, device class and state."""
    if state is None:
        return state_icon(domain, None, None)
    return state_icon(domain, state.attributes.get("device_class"), state.state)


def clock_value(now: datetime | None = None) -> float:
    """Return the minutes after local midnight, with a fraction."""
    now = dt_util.as_local(now or dt_util.utcnow())
    seconds = now.second + now.microsecond / 1_000_000
    return round(now.hour * 60 + now.minute + seconds / 60, 4)


def _when(value: Any) -> datetime | None:
    """Return a moment from a datetime or an ISO text."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return dt_util.parse_datetime(value)
    return None


def position_value(state: State | None, now: datetime | None = None) -> float | None:
    """Return the seconds played now: position plus time since, while playing."""
    if state is None:
        return None
    position = state.attributes.get("media_position")
    if isinstance(position, bool) or not isinstance(position, int | float):
        return None
    if not math.isfinite(position):
        return None
    seconds = float(position)
    if state.state == "playing":
        updated = _when(state.attributes.get("media_position_updated_at"))
        if updated is not None:
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=dt_util.UTC)
            elapsed = ((now or dt_util.utcnow()) - updated).total_seconds()
            seconds += max(elapsed, 0.0)
    duration = state.attributes.get("media_duration")
    if (
        isinstance(duration, int | float)
        and not isinstance(duration, bool)
        and math.isfinite(duration)
        and duration > 0
    ):
        seconds = min(seconds, float(duration))
    return round(max(seconds, 0.0), 2)


def position_key(state: State | None) -> tuple:
    """Return what makes a position worth sending again: state and position."""
    if state is None:
        return (None, None, None)
    return (
        state.state,
        state.attributes.get("media_position"),
        str(state.attributes.get("media_position_updated_at")),
    )


def source_value(hass: HomeAssistant, slot: dict, now: datetime | None = None) -> Any:
    """Return the value of a colour, state_icon, clock or media_position slot."""
    kind = slot.get("kind")
    if kind == "clock":
        return clock_value(now)
    entity = slot.get("entity")
    if not isinstance(entity, str):
        return None
    state = hass.states.get(entity)
    if kind == "colour":
        return colour_value(state, slot.get("of", "rgb"))
    if kind == "state_icon":
        return state_icon_value(state, entity.split(".", 1)[0])
    if kind == "media_position":
        return position_value(state, now)
    return None
