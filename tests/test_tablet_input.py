"""Tests for taps from tablets: verify, run the card's action, ack (contract 7)."""

import asyncio
import json

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.apollo_tab import protocol as tp
from custom_components.apollo_tab.maker import schema
from custom_components.apollo_tab.sender import STATUS_ON_TABLET
from custom_components.apollo_tab.tablet_link import MemoryTabletLink

from .conftest import (
    MakeTablet,
    SaveTabDashboard,
    WriteComponent,
    setup_integration,
    until,
)
from .fake_tablet import FakeTablet

MAC = "aa:bb:cc:dd:ee:01"

LIGHT_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "apollo/light-tile",
    "params": {"entity": "light.kitchen"},
}
LOCK_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "apollo/lock",
    "params": {"entity": "lock.front_door"},
}
DEMO_LIGHT_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "apollo/light-tile",
    "params": {},
}

DOOR_COMPONENT = """\
id: me/door
version: 1.0.0
name: Door
size: 1x1
params:
  entity: {domain: lock}
outputs:
  open:
    action: lock.unlock
    data: {entity_id: "{{ entity }}"}
    feedback: confirm
layout:
  - type: button
    text: "Open"
    on_tap: open
    confirm: "Open the door?"
"""
DOOR_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "me/door",
    "params": {"entity": "lock.front_door"},
}

SWAP_COMPONENT = """\
id: me/swap
version: 1.0.0
name: Swap
size: 1x1
params:
  lamp: {domain: light}
outputs:
  go:
    action: light.turn_on
    data: {entity_id: "{{ lamp }}"}
    feedback: pulse
layout:
  - type: button
    text: "On"
    on_tap: go
"""
SWAP_CARD = {
    "type": "custom:apollo-tab-card",
    "component": "me/swap",
    "params": {"lamp": "light.kitchen"},
}

TWO_COMPONENT = """\
id: me/two
version: 1.0.0
name: Two
size: 1x1
params:
  lamp: {domain: light}
  other: {domain: light}
outputs:
  flip:
    action: light.toggle
    data: {entity_id: "{{ lamp }}"}
    feedback: pulse
layout:
  - type: button
    text: "Flip"
    on_tap: flip
preview:
  params:
    lamp: light.example
    other: light.example2
"""


def tab_config(*cards: dict, title: str = "Home") -> ConfigType:
    """Return a TAB-1 dashboard config with one page of cards."""
    return {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [
            {
                "type": "sections",
                "path": "home",
                "title": title,
                "max_columns": 3,
                "sections": [{"type": "grid", "cards": list(cards)}],
            }
        ],
    }


def widget_for(session, component: str, output: str, event: str = "tap") -> int:
    """Return the id of the widget whose event runs this output."""
    for key, action in session.want.bindings["actions"].items():
        widget, _, kind = key.partition(":")
        if (
            action["component"] == component
            and action["output"] == output
            and kind == event
        ):
            return int(widget)
    raise AssertionError(f"no {component} {output} {event} widget")


async def ready(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save: SaveTabDashboard,
    *cards: dict,
) -> tuple[FakeTablet, object]:
    """Set up one paired tablet showing the cards; return it and its session."""
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    hass.states.async_set("lock.front_door", "locked", {"friendly_name": "Door"})
    tablet = make_tablet()
    await setup_integration(hass, entry)
    await save("tab-home", tab_config(*cards))
    session = entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert session.input == "ok"
    return tablet, session


async def acked(hass: HomeAssistant, tablet: FakeTablet, count: int) -> None:
    """Wait for the count-th ack."""
    await until(hass, lambda: len(tablet.acks) >= count)


async def test_tap_runs_the_action_and_acks(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A good tap runs the card's action with a context without a user."""
    calls = async_mock_service(hass, "light", "toggle")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")

    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks == [(1, True, "")]
    assert len(calls) == 1
    assert calls[0].data == {"entity_id": "light.kitchen"}
    assert calls[0].context.user_id is None
    assert tablet.refused == []


async def test_change_value_is_checked_and_passed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A slider change carries its value; values outside the range fail."""
    calls = async_mock_service(hass, "light", "turn_on")
    slider = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/light-slider",
        "params": {"entity": "light.kitchen"},
    }
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, slider
    )
    widget = next(
        int(key.partition(":")[0])
        for key in session.want.bindings["actions"]
        if key.endswith(":change")
    )

    tablet.tap(widget, event="c", value=40)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, True, "")
    assert len(calls) == 1

    tablet.tap(widget, event="c", value=100000)
    await acked(hass, tablet, 2)
    assert tablet.acks[-1] == (2, False, "failed")
    assert len(calls) == 1


async def test_lock_tap_follows_the_confirmation_step(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A lock asks first: confirm without the flag, runs with it. Never denied."""
    calls = async_mock_service(hass, "lock", "unlock")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LOCK_CARD
    )
    widget = widget_for(session, "apollo/lock", "unlock")

    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, False, "confirm")
    assert calls == []

    tablet.tap(widget, confirmed=True)
    await acked(hass, tablet, 2)
    assert tablet.acks[-1] == (2, True, "")
    assert len(calls) == 1
    assert calls[0].data == {"entity_id": "lock.front_door"}
    assert calls[0].context.user_id is None
    assert all(code != "denied" for _n, _ok, code in tablet.acks)


async def test_alarm_tap_follows_the_confirmation_step(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """An alarm asks first like a lock; nothing is denied for being a tablet."""
    hass.states.async_set(
        "alarm_control_panel.home", "disarmed", {"friendly_name": "House alarm"}
    )
    calls = async_mock_service(hass, "alarm_control_panel", "alarm_arm_away")
    alarm = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/alarm-panel",
        "params": {"entity": "alarm_control_panel.home"},
    }
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, alarm
    )
    widget = widget_for(session, "apollo/alarm-panel", "arm_away")

    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, False, "confirm")
    assert calls == []

    tablet.tap(widget, confirmed=True)
    await acked(hass, tablet, 2)
    assert tablet.acks[-1] == (2, True, "")
    assert len(calls) == 1
    assert calls[0].data == {"entity_id": "alarm_control_panel.home"}


async def test_garage_cover_needs_confirmation(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A garage door cover asks first and then runs."""
    hass.states.async_set(
        "cover.garage", "closed", {"device_class": "garage", "friendly_name": "G"}
    )
    calls = async_mock_service(hass, "cover", "open_cover")
    blinds = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/blinds",
        "params": {"entity": "cover.garage"},
    }
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, blinds
    )
    widget = widget_for(session, "apollo/blinds", "open")

    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, False, "confirm")
    tablet.tap(widget, confirmed=True)
    await acked(hass, tablet, 2)
    assert tablet.acks[-1] == (2, True, "")
    assert len(calls) == 1


def _dl_widget(session, widget_id: int) -> dict:
    """Return one widget of the device layout HA sends to the tablet."""
    layout = json.loads(session.want.data)
    for page in layout["pages"]:
        for item in page["w"]:
            for widget in item.get("w", []):
                if widget["id"] == widget_id:
                    return widget
    raise AssertionError(f"no widget {widget_id}")


async def test_garage_cover_asks_on_the_tablet_first(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A garage cover's widgets carry cf and a question.

    The tablet asks before it sends, so its first input is already confirmed
    and runs. HA's own check stays the guard.
    """
    hass.states.async_set(
        "cover.garage",
        "closed",
        {"device_class": "garage", "friendly_name": "Garage"},
    )
    hass.states.async_set(
        "cover.blind", "closed", {"device_class": "shade", "friendly_name": "Blind"}
    )
    calls = async_mock_service(hass, "cover", "open_cover")
    garage = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/blinds",
        "params": {"entity": "cover.garage"},
    }
    blind = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/blinds",
        "params": {"entity": "cover.blind"},
    }
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, garage, blind
    )
    actions = session.want.bindings["actions"]
    by_entity: dict[tuple[str, str], int] = {}
    for key, action in actions.items():
        widget_id, _, event = key.partition(":")
        by_entity[(action["entities"][0], action["output"])] = int(widget_id)
    expected = {
        "open": "Open Garage?",
        "close": "Close Garage?",
        "stop": "Stop Garage?",
        "set_position": "Move Garage?",
    }
    for output, question in expected.items():
        widget = _dl_widget(session, by_entity[("cover.garage", output)])
        assert widget["cf"] == 1
        assert widget["confirm"] == question
        other = _dl_widget(session, by_entity[("cover.blind", output)])
        assert "cf" not in other
        assert "confirm" not in other

    # The tablet asked; its first input is confirmed and runs at once.
    open_garage = by_entity[("cover.garage", "open")]
    tablet.tap(open_garage, confirmed=True)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, True, "")
    assert len(calls) == 1
    # HA still checks: an input without the yes is answered "confirm".
    tablet.tap(open_garage)
    await acked(hass, tablet, 2)
    assert tablet.acks[-1] == (2, False, "confirm")
    assert len(calls) == 1


async def test_cover_class_change_changes_the_layout(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """The questions are part of the compiled layout, not cached past them."""
    hass.states.async_set(
        "cover.side", "closed", {"device_class": "shade", "friendly_name": "Side"}
    )
    card = {
        "type": "custom:apollo-tab-card",
        "component": "apollo/blinds",
        "params": {"entity": "cover.side"},
    }
    _tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, card
    )
    before = session._compile("tab-home")
    assert session._compile("tab-home") is before
    hass.states.async_set(
        "cover.side", "closed", {"device_class": "gate", "friendly_name": "Side"}
    )
    after = session._compile("tab-home")
    assert after.hash != before.hash
    widget_id = widget_for(session, "apollo/blinds", "open")
    layout = json.loads(after.data)
    widgets = [w for page in layout["pages"] for i in page["w"] for w in i.get("w", [])]
    assert next(w for w in widgets if w["id"] == widget_id)["confirm"] == "Open Side?"


async def test_unapproved_user_card_is_denied(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    user_components: WriteComponent,
) -> None:
    """Approval is checked again at tap time, also for the screen still shown."""
    user_components("door.yaml", DOOR_COMPONENT)
    calls = async_mock_service(hass, "lock", "unlock")
    hass.states.async_set("lock.front_door", "locked", {"friendly_name": "Door"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    library = config_entry.runtime_data.library
    await library.async_set_approved("me/door", True)
    await save_tab_dashboard("tab-home", tab_config(DOOR_CARD))
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    widget = widget_for(session, "me/door", "open")

    tablet.tap(widget, confirmed=True)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, True, "")
    assert len(calls) == 1

    # Take the approval back. The new layout leaves the card out, but the
    # tablet still shows the old one while it builds.
    tablet.hold_build = True
    shown = tablet.active
    await library.async_set_approved("me/door", False)
    await until(hass, lambda: tablet.staged not in ("", shown))
    assert shown in session.kept

    tablet.tap(widget, confirmed=True)
    await acked(hass, tablet, 2)
    assert tablet.acks[-1] == (2, False, "denied")
    assert len(calls) == 1


async def test_demo_card_cannot_act(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """An example card without an entity is denied."""
    calls = async_mock_service(hass, "light", "toggle")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, DEMO_LIGHT_CARD
    )
    actions = session.want.bindings["actions"]
    if not actions:
        pytest.skip("this card has no action without an entity")
    widget = int(next(iter(actions)).partition(":")[0])

    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, False, "denied")
    assert calls == []


async def test_half_set_user_card_is_a_demo_and_cannot_act(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    user_components: WriteComponent,
) -> None:
    """An approved user card with one of two entities set is still a demo card."""
    user_components("two.yaml", TWO_COMPONENT)
    calls = async_mock_service(hass, "light", "toggle")
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await config_entry.runtime_data.library.async_set_approved("me/two", True)
    half = {
        "type": "custom:apollo-tab-card",
        "component": "me/two",
        "params": {"lamp": "light.kitchen"},
    }
    await save_tab_dashboard("tab-home", tab_config(half))
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    widget = widget_for(session, "me/two", "flip")
    assert session.want.bindings["actions"][f"{widget}:tap"]["demo"] is True

    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, False, "denied")
    assert calls == []


@pytest.mark.parametrize(
    ("action", "data"),
    [
        # Rendered data that names an entity the card was not set up with.
        ("light.toggle", {"entity_id": "light.secret"}),
        # The card's own entity, but the action is in another domain.
        ("switch.toggle", {"entity_id": "{{ entity }}"}),
    ],
)
async def test_tap_reaches_only_the_cards_own_entity(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    action: str,
    data: dict,
) -> None:
    """The tablet path runs the same entity check as the browser."""
    lights = async_mock_service(hass, "light", "toggle")
    switches = async_mock_service(hass, "switch", "toggle")
    hass.states.async_set("light.secret", "off", {"friendly_name": "Secret"})
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    components = config_entry.runtime_data.library.components
    tile = components["apollo/light-tile"]
    output = {**tile["outputs"]["toggle"], "action": action, "data": data}
    components["apollo/light-tile"] = {
        **tile,
        "outputs": {**tile["outputs"], "toggle": output},
    }

    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, False, "denied")
    assert lights == []
    assert switches == []


async def test_input_is_dropped_after_encryption_is_removed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    memory_link: MemoryTabletLink,
) -> None:
    """A tablet reflashed without encryption keeps its old secret (contract 6.1).

    HA takes no input from it, even signed with that secret, and signs no
    call to it. Its software takes no API key, so none comes and it gets
    its dashboard unsigned.
    """
    calls = async_mock_service(hass, "light", "toggle")
    unlocks = async_mock_service(hass, "lock", "unlock")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD, LOCK_CARD
    )
    before = len(tablet.calls)
    tablet.psk = None
    tablet.encryption_supported = False
    memory_link.async_reconnect(MAC)
    await until(
        hass,
        lambda: (
            session.status == STATUS_ON_TABLET and session.input == "needs_encryption"
        ),
    )
    assert session.nonce is not None
    signed = [
        args["auth"]
        for name, args in tablet.calls[before:]
        if name in ("tab_set", "tab_commit", "tab_clear")
    ]
    assert signed
    assert set(signed) == {""}

    tablet.tap(widget_for(session, "apollo/light-tile", "toggle"))
    tablet.tap(widget_for(session, "apollo/lock", "unlock"), confirmed=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert tablet.acks == []
    assert calls == []
    assert unlocks == []
    assert session.dropped["not_paired"] == 2


async def test_previous_layout_taps_work_during_a_build(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A tap on the old screen during a build runs the old screen's action."""
    toggles = async_mock_service(hass, "light", "toggle")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    shown = tablet.active

    tablet.hold_build = True
    await save_tab_dashboard("tab-home", tab_config(LOCK_CARD))
    await until(hass, lambda: tablet.staged not in ("", shown))
    assert set(session.kept) == {shown, tablet.staged}

    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, True, "")
    assert len(toggles) == 1

    # Once the new layout is on screen, the old one is forgotten.
    tablet.finish_build()
    await until(hass, lambda: set(session.kept) == {tablet.active})
    tablet.tap(widget, layout=shown)
    await acked(hass, tablet, 2)
    assert tablet.acks[-1] == (2, False, "stale")
    assert len(toggles) == 1


async def test_old_screen_tap_after_a_component_change_is_stale(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    user_components: WriteComponent,
) -> None:
    """The old screen's button never runs a changed Component's new action.

    The bindings name an output, and the Component's file may give that
    name another action while the old screen is still up.
    """
    user_components("swap.yaml", SWAP_COMPONENT)
    on = async_mock_service(hass, "light", "turn_on")
    off = async_mock_service(hass, "light", "turn_off")
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    library = config_entry.runtime_data.library
    await save_tab_dashboard("tab-home", tab_config(SWAP_CARD))
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    widget = widget_for(session, "me/swap", "go")
    shown = tablet.active

    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, True, "")
    assert (len(on), len(off)) == (1, 0)

    # The button now says "Off" and turns the light off. The tablet still
    # shows "On" while the new layout builds.
    tablet.hold_build = True
    user_components(
        "swap.yaml",
        SWAP_COMPONENT.replace("light.turn_on", "light.turn_off").replace(
            '"On"', '"Off"'
        ),
    )
    await library.async_load()
    await until(hass, lambda: tablet.staged not in ("", shown))
    assert tablet.active == shown
    assert shown in session.kept

    tablet.tap(widget)
    await acked(hass, tablet, 2)
    assert tablet.acks[-1] == (2, False, "stale")
    assert (len(on), len(off)) == (1, 0)

    # The new screen's button runs the new action.
    tablet.finish_build()
    await until(
        hass,
        lambda: session.status == STATUS_ON_TABLET and tablet.active != shown,
    )
    tablet.tap(widget_for(session, "me/swap", "go"))
    await acked(hass, tablet, 3)
    assert tablet.acks[-1] == (3, True, "")
    assert (len(on), len(off)) == (1, 1)


async def test_tap_right_after_a_reload_without_changes_still_runs(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Reading the same Component files again leaves the screen's taps alone."""
    toggles = async_mock_service(hass, "light", "toggle")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    await config_entry.runtime_data.library.async_load()
    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, True, "")
    assert len(toggles) == 1


@pytest.mark.parametrize("missing", ["revision", "hash", "both"])
async def test_tap_without_a_component_revision_is_stale(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    missing: str,
) -> None:
    """A tap runs only when its Component is known to be the layout's one.

    A layout without a recorded revision for the Component, or a Component
    without a hash, cannot show that, so nothing runs.
    """
    calls = async_mock_service(hass, "light", "toggle")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    if missing in ("revision", "both"):
        session.kept[tablet.active].revisions = {}
    if missing in ("hash", "both"):
        components = config_entry.runtime_data.library.components
        tile = components["apollo/light-tile"]
        components["apollo/light-tile"] = {
            key: value for key, value in tile.items() if key != "hash"
        }

    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks == [(1, False, "stale")]
    assert calls == []


async def test_stale_layout_is_acked_stale(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A tap on a layout HA keeps no bindings for gets "stale"."""
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    tablet.tap(1, layout="0123456789abcdef")
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, False, "stale")


async def test_bad_input_is_dropped_without_ack(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Replays, bad signatures and strangers get no answer and run nothing."""
    calls = async_mock_service(hass, "light", "toggle")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    hellos = len(tablet.calls_of("tab_hello"))

    good = tablet.tap(widget)
    await acked(hass, tablet, 1)
    # The same event again: a replay.
    hass.bus.async_fire("esphome.tab1_input", good)
    # Signed with another key, as by a device that does not hold the secret.
    tablet.tap(widget, secret=bytes(32))
    # Not ASCII, wrong shapes, another protocol version.
    hass.bus.async_fire("esphome.tab1_input", {"d": "ä", "s": "0" * 32})
    hass.bus.async_fire("esphome.tab1_input", {"d": good["d"], "s": "XYZ"})
    hass.bus.async_fire(
        "esphome.tab1_input", {"d": "2" + good["d"][1:], "s": good["s"]}
    )
    # A device claiming another tablet's input with the tablet's MAC in a
    # payload it cannot sign.
    hass.bus.async_fire(
        "esphome.tab1_input",
        {"device_id": "other", "d": good["d"].replace("|1|", "|9|"), "s": good["s"]},
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert tablet.acks == [(1, True, "")]
    assert len(calls) == 1
    assert session.dropped["replay"] == 1
    assert session.dropped["bad_signature"] >= 2
    assert session.dropped["version"] == 1
    # A bad signature starts nothing: anyone can cause one.
    assert len(tablet.calls_of("tab_hello")) == hellos
    # One warning per tablet per minute, without the payload.
    warnings = [r for r in caplog.records if "input was dropped" in r.getMessage()]
    assert len(warnings) == 1
    assert good["d"] not in caplog.text


async def test_unknown_tablet_input_is_counted(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Input naming a MAC that is not a tablet is counted and dropped."""
    tablet, _session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    hass.bus.async_fire(
        "esphome.tab1_input", {"d": "1|0123456789ab|x|1|y|1|t|0|", "s": "0" * 32}
    )
    hass.bus.async_fire("esphome.tab1_input", {"d": 5})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert config_entry.runtime_data.sender.unknown_inputs == 2
    assert tablet.acks == []


async def test_unpaired_tablet_input_is_dropped(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Without a secret in HA, no input is trusted."""
    calls = async_mock_service(hass, "light", "toggle")
    tablet = make_tablet(psk=None)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD))
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert session.input == "needs_encryption"
    widget = widget_for(session, "apollo/light-tile", "toggle")

    tablet.tap(widget, secret=bytes(32))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert session.dropped["not_paired"] == 1
    assert calls == []
    assert tablet.acks == []


async def test_stale_session_starts_a_new_session_once(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A valid signature with an old nonce greets again, at most every 10 s."""
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    hellos = len(tablet.calls_of("tab_hello"))

    tablet.tap(widget, nonce="f" * 32)
    await until(hass, lambda: len(tablet.calls_of("tab_hello")) == hellos + 1)
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    tablet.tap(widget, nonce="e" * 32)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(tablet.calls_of("tab_hello")) == hellos + 1
    assert session.dropped["stale_session"] == 2
    assert tablet.acks == []


async def test_input_without_a_session_is_stale(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """While HA holds no session, no input is the session's and none runs.

    Not even input signed over an empty nonce field. The signature is the
    tablet's, so HA greets it again, as after any stale session.
    """
    calls = async_mock_service(hass, "light", "toggle")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    hellos = len(tablet.calls_of("tab_hello"))
    # As after the connection ended: no session, the secret and bindings stay.
    session.drop_session()
    assert session.input == "ok"

    tablet.tap(widget, nonce="", counter=1)
    # Signed over the session the tablet still believes in.
    tablet.tap(widget, counter=2)
    await until(hass, lambda: session.nonce is not None)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert calls == []
    assert tablet.calls_of("tab_ack") == []
    assert session.dropped["stale_session"] == 2
    assert len(tablet.calls_of("tab_hello")) == hellos + 1

    # In the new session the tablet's taps count again.
    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks == [(1, True, "")]
    assert len(calls) == 1


async def test_more_than_ten_inputs_a_second_are_busy(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """The eleventh input within a second gets "busy" and runs nothing."""
    calls = async_mock_service(hass, "light", "toggle")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    session._now = lambda: 1000.0  # every input in the same instant

    for _ in range(12):
        tablet.tap(widget)
    await acked(hass, tablet, 12)
    codes = [code for _n, _ok, code in sorted(tablet.acks)]
    assert codes.count("") == 10
    assert codes.count("busy") == 2
    assert len(calls) == 10


async def test_failing_action_acks_failed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """An action that raises acks "failed"."""
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    # light.toggle is not registered in the test instance, so it fails.
    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, False, "failed")


async def test_acks_are_signed_in_order(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Each ack carries a valid auth with a counter above the last call."""
    async_mock_service(hass, "light", "toggle")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    for _ in range(3):
        tablet.tap(widget)
        await asyncio.sleep(0)
    await acked(hass, tablet, 3)
    assert tablet.refused == []
    acks = tablet.calls_of("tab_ack")
    numbers = [int(args["auth"].partition(".")[0]) for args in acks]
    assert numbers == sorted(numbers)
    assert all(tp.is_hex(args["auth"].partition(".")[2], 32) for args in acks)


async def test_ack_of_an_ended_session_is_not_sent(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    memory_link: MemoryTabletLink,
) -> None:
    """An action that ends after a new session began is not answered there.

    Input counters start at 1 again in every session, so the new session's
    first input would take the old answer for its own.
    """
    release = asyncio.Event()
    started: list[ServiceCall] = []

    async def toggle(call: ServiceCall) -> None:
        """Wait and then fail the first time; succeed at once afterwards."""
        started.append(call)
        if len(started) == 1:
            await release.wait()
            raise ValueError("the first action fails late")

    hass.services.async_register("light", "toggle", toggle)
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")

    tablet.tap(widget)
    await until(hass, lambda: len(started) == 1)
    first = session.nonce

    memory_link.async_reconnect(MAC)
    await until(
        hass,
        lambda: (
            session.nonce not in (None, first) and session.status == STATUS_ON_TABLET
        ),
    )
    assert tablet.acks == []

    # Input 1 of the new session.
    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks == [(1, True, "")]

    release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert tablet.acks == [(1, True, "")]
    assert len(tablet.calls_of("tab_ack")) == 1
    assert tablet.refused == []


async def test_taps_work_after_a_restart_without_a_resend(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """After a reload the tablet keeps its layout and its taps work."""
    calls = async_mock_service(hass, "light", "toggle")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    chunks = len(tablet.calls_of("tab_layout"))

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert len(tablet.calls_of("tab_layout")) == chunks

    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks[-1] == (1, True, "")
    assert len(calls) == 1


async def test_non_ascii_signature_does_not_raise(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A signature with other characters is dropped as malformed."""
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    good = tablet.tap(widget)
    await acked(hass, tablet, 1)
    payload = good["d"].replace("|1|", "|2|", 1)
    for signature in ("é" * 32, "€" * 32, 5, None, "A" * 32):
        hass.bus.async_fire("esphome.tab1_input", {"d": payload, "s": signature})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert session.dropped["malformed"] == 5
    assert len(tablet.acks) == 1


async def test_action_off_the_allow_list_at_tap_time_is_denied(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The allow-list is checked again when the tap runs, not only at build.

    A layout built while an action was allowed cannot run it after the
    action left the allow-list.
    """
    calls = async_mock_service(hass, "light", "toggle")
    tablet, session = await ready(
        hass, config_entry, make_tablet, save_tab_dashboard, LIGHT_CARD
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    allowed = schema.ALLOWED_ACTION_DOMAINS - {"light"}
    monkeypatch.setattr(schema, "ALLOWED_ACTION_DOMAINS", allowed)

    tablet.tap(widget)
    await acked(hass, tablet, 1)
    assert tablet.acks == [(1, False, "denied")]
    assert calls == []
