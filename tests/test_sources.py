"""The sources colour, state_icon, clock and media_position (C.2.8, C.5; I6)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from homeassistant.core import State
from homeassistant.util import dt as dt_util

from custom_components.apollo_tab import protocol as tp
from custom_components.apollo_tab.sources import (
    clock_value,
    colour_value,
    position_key,
    position_value,
    state_icon_value,
)

NOW = datetime(2026, 11, 14, 12, 0, 0, tzinfo=dt_util.UTC)


def test_colour_of_a_light() -> None:
    """rgb_color as one number; the hue at full strength; nothing when off."""
    on = State("light.a", "on", {"rgb_color": [255, 128, 0], "hs_color": [120, 30]})
    assert colour_value(on, "rgb") == 0xFF8000
    assert colour_value(on, "hue") == 0x00FF00
    assert (
        colour_value(State("light.a", "off", {"rgb_color": [1, 2, 3]}), "rgb") is None
    )
    assert colour_value(None, "rgb") is None
    for bad in ([255, 0], [256, 0, 0], ["1", 2, 3], [True, 0, 0], "red"):
        assert colour_value(State("light.a", "on", {"rgb_color": bad}), "rgb") is None
    # The hue from rgb_color when the light reports no hs_color.
    red = State("light.a", "on", {"rgb_color": [200, 0, 0]})
    assert colour_value(red, "hue") == 0xFF0000


def test_state_icon_of_an_entity() -> None:
    """By kind, device class and state; an entity HA does not know gets its kind's."""
    garage = State("cover.g", "open", {"device_class": "garage", "icon": "mdi:evil"})
    assert state_icon_value(garage, "cover") == "mdi:garage-open"
    assert state_icon_value(None, "light") == "mdi:lightbulb"


def test_the_clock_counts_minutes_after_local_midnight() -> None:
    """With the fraction of the minute."""
    local = dt_util.as_local(NOW)
    expected = local.hour * 60 + local.minute
    assert clock_value(NOW) == expected
    assert clock_value(NOW + timedelta(seconds=30)) == expected + 0.5


def test_the_position_counts_on_while_playing() -> None:
    """Position plus the time since its update; held at 0 and at the duration."""
    attrs = {
        "media_position": 10,
        "media_position_updated_at": NOW,
        "media_duration": 100,
    }
    playing = State("media_player.a", "playing", attrs)
    assert position_value(playing, NOW + timedelta(seconds=5)) == 15
    assert position_value(playing, NOW + timedelta(seconds=500)) == 100
    assert position_value(playing, NOW - timedelta(seconds=5)) == 10
    paused = State("media_player.a", "paused", attrs)
    assert position_value(paused, NOW + timedelta(seconds=5)) == 10
    text = State(
        "media_player.a",
        "playing",
        {**attrs, "media_position_updated_at": NOW.isoformat()},
    )
    assert position_value(text, NOW + timedelta(seconds=2.5)) == 12.5
    for bad in (None, "10", True, float("nan")):
        state = State("media_player.a", "playing", {"media_position": bad})
        assert position_value(state, NOW) is None
    assert position_value(None, NOW) is None


def test_a_position_is_sent_again_only_when_its_key_changes() -> None:
    """The state, the position and the moment of its update; not the title."""
    attrs = {"media_position": 10, "media_position_updated_at": NOW}
    one = State("media_player.a", "playing", attrs)
    other = State("media_player.a", "playing", {**attrs, "media_title": "x"})
    assert position_key(one) == position_key(other)
    paused = State("media_player.a", "paused", attrs)
    assert position_key(one) != position_key(paused)
    moved = State("media_player.a", "playing", {**attrs, "media_position": 11})
    assert position_key(one) != position_key(moved)


def test_encode_set_keeps_a_value_and_its_rate_in_one_payload() -> None:
    """together: one pair per payload still holds the pair; without it, as before."""
    values = {slot: slot * 10 for slot in range(1, 7)}
    plain = tp.encode_set("abc", values, full=True, limit=60)
    assert tp.encode_set("abc", values, full=True, limit=60, together=()) == plain
    assert len(plain) == 6
    paired = tp.encode_set("abc", values, full=True, limit=60, together=[(2, 5)])
    messages = [json.loads(payload) for payload in paired]
    assert [[pair[0] for pair in m["v"]] for m in messages] == [
        [1],
        [2, 5],
        [3],
        [4],
        [6],
    ]
    assert messages[0]["f"] == 1
    assert all("f" not in m for m in messages[1:])
    # A pair whose other slot is not being sent changes nothing.
    assert tp.encode_set(
        "abc", {2: 1, 3: 2}, full=False, limit=60, together=[(2, 9)]
    ) == (tp.encode_set("abc", {2: 1, 3: 2}, full=False, limit=60))
