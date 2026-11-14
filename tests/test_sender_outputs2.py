"""Schema 2 cards on a tablet that speaks 2 (cards spec C.5, contract 7.3 and 8; I6).

Card taps, choices and changes run through the tablet path; clock and
position slots go around the changes-only filter; a rate travels with its
value.
"""

from __future__ import annotations

import json
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.apollo_tab import (
    library as library_module,
    sender as sender_module,
)
from custom_components.apollo_tab.sender import STATUS_ON_TABLET

from .conftest import MakeTablet, SaveTabDashboard, setup_integration, until
from .fake_tablet import ENGINE_V2
from .test_tablet_input import MAC, acked, tab_config

PLAYER = "media_player.den"
LAMP = "light.den"
LIVE = """\
schema: 2
id: test/live
version: 1.0.0
name: Live
icon: mdi:play
params:
  player: {domain: media_player}
  lamp: {domain: light}
options:
  speeds: {type: choice, multiple: true, max: 4, section: controls, label: Speeds,
           default: [a, b], choices: {a: Slow, b: Fast}}
inputs:
  pos: {source: media_position, entity: "{{ player }}"}
  rate: "{{ 1 if is_state(player, 'playing') else 0 }}"
  length: "{{ state_attr(player, 'media_duration') or 100 }}"
  lit: {source: colour, entity: "{{ lamp }}", of: rgb}
  top: "{{ state_attr(lamp, 'top') }}"
outputs:
  seek:   {action: media_player.media_seek, feedback: optimistic,
           data: {entity_id: "{{ player }}", seek_position: "{{ value }}"}}
  speed:  {action: light.turn_on, feedback: pulse,
           data: {entity_id: "{{ lamp }}", effect: "{{ option }}"}}
  level:  {action: light.turn_on, feedback: optimistic,
           data: {entity_id: "{{ lamp }}", brightness: "{{ value }}"}}
  toggle: {action: light.toggle, feedback: optimistic, data: {entity_id: "{{ lamp }}"}}
tap:
  default: toggle
  choices:
    toggle: {label: Turns it on or off, output: toggle}
variants:
  all:
    name: All
    grid: [12, 6]
    header: none
    layout:
      - {type: slider, value: pos, rate: rate, min: 0, max: "{{ length }}",
         on_change: seek}
      - {type: slider, value: top, min: 0, max: "{{ top }}", step: 5, on_change: level}
      - {type: choice, options: speeds, on_change: speed}
      - {type: label, text: Lamp, colour: lit}
"""
CARD = {
    "type": "custom:apollo-tab-card",
    "component": "test/live",
    "params": {"player": PLAYER, "lamp": LAMP},
}


@pytest.fixture(autouse=True)
def builtin_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Serve the built-in files plus the card above as a built-in."""
    folder = tmp_path / "builtin"
    shutil.copytree(library_module._BUILTIN_DIR, folder)
    (folder / "components" / "test-live.yaml").write_text(LIVE, encoding="utf-8")
    monkeypatch.setattr(library_module, "_BUILTIN_DIR", folder)
    return folder


def _player(hass: HomeAssistant, state: str, position: float, **extra: Any) -> None:
    """Set the player's state and position, updated now."""
    hass.states.async_set(
        PLAYER,
        state,
        {
            "media_position": position,
            "media_position_updated_at": dt_util.utcnow(),
            "media_duration": 300,
            **extra,
        },
    )


async def _on_tablet(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> tuple[Any, Any]:
    """Show the card on a tablet that speaks 2."""
    _player(hass, "paused", 12)
    hass.states.async_set(LAMP, "on", {"rgb_color": [255, 0, 0], "top": 100})
    fake = make_tablet(engine=ENGINE_V2)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(CARD))
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert session.dl == 2
    assert session.input == "ok"
    return fake, session


def _items(session) -> list[dict]:
    """Return the card and its widgets in the layout sent to the tablet."""
    layout = json.loads(session.want.data)
    card = layout["pages"][0]["w"][0]
    return [card, *card["w"]]


def _widget(session, kind: str, index: int = 0) -> dict:
    """Return the index-th widget of one kind."""
    return [item for item in _items(session) if item["t"] == kind][index]


def _device_slot(session, name: str) -> int:
    """Return the device slot of a number input by its slot kind or template."""
    for slot in session.want.bindings["slots"]:
        text = slot.get("template", "") + slot.get("kind", "")
        if name in text:
            number = session.live.number_slot(slot["n"])
            if number is not None:
                return number
    raise AssertionError(f"no slot for {name}")


async def test_a_card_tap_runs_on_the_tablet_path(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A t on the card runs the card's tap; a c on the card does nothing."""
    calls = async_mock_service(hass, "light", "toggle")
    fake, session = await _on_tablet(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    card = _items(session)[0]
    assert "p" in card["tap"]
    fake.tap(card["id"])
    await acked(hass, fake, 1)
    assert fake.acks[-1] == (1, True, "")
    assert [call.data for call in calls] == [{"entity_id": LAMP}]


async def test_a_choice_runs_with_the_servers_option(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """The index picks HA's own copy; an index past the list fails."""
    calls = async_mock_service(hass, "light", "turn_on")
    fake, session = await _on_tablet(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    choice = _widget(session, "choice")
    action = session.want.bindings["actions"][f"{choice['id']}:change"]
    fake.tap(choice["id"], event="c", value=1)
    await acked(hass, fake, 1)
    assert fake.acks[-1] == (1, True, "")
    assert calls[-1].data == {"entity_id": LAMP, "effect": action["options"][1]}
    fake.tap(choice["id"], event="c", value=2)
    await acked(hass, fake, 2)
    assert fake.acks[-1] == (2, False, "failed")
    assert len(calls) == 1


async def test_a_change_is_checked_against_the_live_limits(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Above the max last sent, off the step, and a t for a widget with change."""
    calls = async_mock_service(hass, "light", "turn_on")
    fake, session = await _on_tablet(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    slider = _widget(session, "slider", 1)
    assert isinstance(slider["max"], dict)
    fake.tap(slider["id"], event="c", value=40)
    await acked(hass, fake, 1)
    assert fake.acks[-1] == (1, True, "")
    assert calls[-1].data == {"entity_id": LAMP, "brightness": 40}
    count = 1
    for event, value in (("c", 105), ("c", 42), ("t", None)):
        fake.tap(slider["id"], event=event, value=value)
        count += 1
        await acked(hass, fake, count)
        assert fake.acks[-1][1] is False, (event, value)
    assert len(calls) == 1
    # The max the tablet holds is what counts, not HA's newest value.
    hass.states.async_set(LAMP, "on", {"rgb_color": [255, 0, 0], "top": 200})
    sent = session.live.sent
    await until(hass, lambda: fake.slot(_device_slot(session, "top")) == 200)
    assert sent is session.live.sent
    fake.tap(slider["id"], event="c", value=150)
    await acked(hass, fake, count + 1)
    assert fake.acks[-1] == (count + 1, True, "")


async def test_a_newer_max_that_has_not_gone_out_does_not_count(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HA knows a max of 200 the tablet does not hold yet: 150 is still refused."""
    calls = async_mock_service(hass, "light", "turn_on")
    fake, session = await _on_tablet(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    slider = _widget(session, "slider", 1)
    top = _device_slot(session, "top")
    # Keep the new value from going out.
    monkeypatch.setattr(session, "values_changed", lambda live: None)
    hass.states.async_set(LAMP, "on", {"rgb_color": [255, 0, 0], "top": 200})
    await until(hass, lambda: session.live.wire[top] == 200)
    assert session.live.sent[top] == 100
    assert fake.slot(top) == 100
    fake.tap(slider["id"], event="c", value=150)
    await acked(hass, fake, 1)
    assert fake.acks[-1][1] is False
    assert calls == []


async def test_a_colour_slot_takes_its_colour(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """The colour source reaches the label's colour slot, and follows the lamp."""
    fake, session = await _on_tablet(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    label = _widget(session, "label")
    slot = label["c"]["s"] if isinstance(label.get("c"), dict) else label["col"]["s"]
    assert fake.slot(slot) not in (None, "")
    first = fake.slot(slot)
    hass.states.async_set(LAMP, "on", {"rgb_color": [0, 0, 255], "top": 100})
    await until(hass, lambda: fake.slot(slot) != first)
    hass.states.async_set(LAMP, "off", {"top": 100})
    await until(hass, lambda: fake.slot(slot) is None)


async def test_a_position_is_sent_again_when_equal(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Paused at 12, then playing from 12: the 12 goes out again with rate 1."""
    fake, session = await _on_tablet(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    position = _device_slot(session, "media_position")
    rate = _device_slot(session, "playing")
    assert fake.slot(position) == 12
    assert fake.slot(rate) == 0
    before = len(fake.sets)
    _player(hass, "playing", 12)
    await until(hass, lambda: fake.slot(rate) == 1)
    new = fake.sets[before:]
    with_rate = [m for m in new if rate in [pair[0] for pair in m["v"]]]
    assert with_rate
    # The rate and a fresh value share one tab_set.
    assert all(position in [pair[0] for pair in m["v"]] for m in with_rate)
    assert fake.slot(position) == pytest.approx(12, abs=0.5)
    # An equal value of another slot is never sent again.
    before = len(fake.sets)
    hass.states.async_set(LAMP, "on", {"rgb_color": [255, 0, 0], "top": 100, "x": 1})
    _player(hass, "paused", 12)
    await until(hass, lambda: fake.slot(rate) == 0)
    numbers = [pair[0] for m in fake.sets[before:] for pair in m["v"]]
    assert _device_slot(session, "top") not in numbers
    # Paused again at 12, then the same position reported again: sent again.
    before = len(fake.sets)
    _player(hass, "paused", 12, media_title="next")
    _player(hass, "paused", 12, media_position_updated_at=dt_util.utcnow())
    await until(
        hass,
        lambda: any(
            position in [pair[0] for pair in m["v"]] for m in fake.sets[before:]
        ),
    )


async def test_a_clock_slot_is_sent_every_ten_minutes(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clock input is worked out again every 600 s and sent each time."""
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    clock_card = LIVE.replace(
        "      - {type: label, text: Lamp, colour: lit}",
        "      - {type: label, text: Lamp, colour: lit}\n"
        "      - {type: label, clock: 24, value: now}",
    ).replace("  top:", "  now: {source: clock}\n  top:")
    folder = library_module._BUILTIN_DIR
    (folder / "components" / "test-live.yaml").write_text(clock_card, encoding="utf-8")
    fake, session = await _on_tablet(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    clock = _device_slot(session, "clock")
    assert isinstance(fake.slot(clock), int | float)
    start = dt_util.utcnow()
    for turn in (1, 2):
        before = len(fake.sets)
        async_fire_time_changed(hass, start + timedelta(seconds=601 * turn))
        await until(
            hass,
            lambda before=before: any(
                clock in [pair[0] for pair in m["v"]] for m in fake.sets[before:]
            ),
        )


async def test_the_rate_and_its_value_share_a_part_of_a_split_snapshot(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With one pair per payload, the value and the rate still go together."""
    real_encode = sender_module.tp.encode_set

    def small_encode(layout, values, *, full, **kwargs):
        """Split at 60 bytes instead of 12000."""
        return real_encode(layout, values, full=full, limit=60, **kwargs)

    monkeypatch.setattr(sender_module.tp, "encode_set", small_encode)
    fake, session = await _on_tablet(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    position = _device_slot(session, "media_position")
    rate = _device_slot(session, "playing")
    full = next(i for i, m in enumerate(fake.sets) if m.get("f") == 1)
    parts = [fake.sets[full]]
    for message in fake.sets[full + 1 :]:
        if message.get("f") == 1:
            break
        parts.append(message)
    assert len(parts) > 2
    holding = [m for m in parts if {position, rate} & {pair[0] for pair in m["v"]}]
    assert len(holding) == 1
    assert {position, rate} <= {pair[0] for pair in holding[0]["v"]}
