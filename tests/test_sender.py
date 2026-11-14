"""Tests for the sender against simulated tablets (contract sections 3 to 8)."""

import asyncio
import json
from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.apollo_tab import protocol as tp, sender as sender_module
from custom_components.apollo_tab.maker.device import content_hash
from custom_components.apollo_tab.sender import (
    STATUS_FAILED,
    STATUS_NO_DASHBOARD,
    STATUS_NO_ENGINE,
    STATUS_OFFLINE,
    STATUS_ON_TABLET,
    STATUS_SENDING,
    STATUS_UNSUPPORTED,
    TabletSender,
)
from custom_components.apollo_tab.tablet_link import LinkError, MemoryTabletLink
from custom_components.apollo_tab.tablets import async_get_tablets

from .conftest import MakeTablet, SaveTabDashboard, setup_integration, until
from .fake_tablet import FakeTablet

MAC = "aa:bb:cc:dd:ee:01"


def light_card(entity: str = "light.kitchen") -> dict:
    """Return a light tile card."""
    return {
        "type": "custom:apollo-tab-card",
        "component": "apollo/light-tile",
        "params": {"entity": entity},
    }


def tab_config(*cards: dict, title: str = "Home") -> dict:
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


def sender_of(entry: MockConfigEntry) -> TabletSender:
    """Return the loaded entry's sender."""
    return entry.runtime_data.sender


def session_of(entry: MockConfigEntry, mac: str = MAC):
    """Return a tablet's session."""
    return sender_of(entry).sessions[mac]


def layout_bytes(tablet: FakeTablet, hash_: str) -> bytes:
    """Return the bytes of the last complete transfer of one hash."""
    chunks = [args for args in tablet.calls_of("tab_layout") if args["hash"] == hash_]
    last_start = max(i for i, args in enumerate(chunks) if args["seq"] == 0)
    return "".join(args["data"] for args in chunks[last_start:]).encode()


async def on_tablet(hass: HomeAssistant, entry: MockConfigEntry, mac: str = MAC):
    """Wait until the tablet shows its dashboard; return the session."""
    session = session_of(entry, mac)
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    return session


async def test_first_send_pairs_sends_and_confirms(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A new tablet is paired, gets the dashboard in chunks and confirms it."""
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()), title="Home")

    session = await on_tablet(hass, config_entry)
    names = [name for name, _args in tablet.calls]
    # Greet, pair, greet again, then the layout and the signed commit.
    assert names[:3] == ["tab_hello", "tab_pair", "tab_hello"]
    assert "tab_layout" in names
    assert names.index("tab_commit") > names.index("tab_layout")
    assert tablet.active == session.want.hash == session.shown
    # The bytes on the tablet are the device layout HA compiled.
    assert content_hash(layout_bytes(tablet, tablet.active)) == tablet.active
    assert layout_bytes(tablet, tablet.active) == session.want.data
    # Paired: HA and the tablet hold the same secret.
    assert tablet.secret == config_entry.runtime_data.assignments.secret(MAC)
    assert session.paired is True
    assert session.input == "ok"
    assert tablet.refused == []
    # Every signed call after the hello counts up.
    numbers = [
        int(args["auth"].partition(".")[0])
        for name, args in tablet.calls
        if name in ("tab_commit", "tab_set")
    ]
    assert numbers == sorted(numbers)
    assert len(set(numbers)) == len(numbers)


async def test_on_tablet_only_after_the_tablet_confirms(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A successful commit alone is not enough: status waits for tab_status."""
    tablet = make_tablet()
    tablet.hold_build = True
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = session_of(config_entry)

    await until(hass, lambda: tablet.staged != "")
    await until(hass, lambda: len(tablet.calls_of("tab_status")) >= 3)
    assert session.status == STATUS_SENDING
    assert tablet.active == ""

    tablet.finish_build()
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert tablet.active == session.want.hash


async def test_values_snapshot_then_changes(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A full snapshot follows the commit; after that only changes go out."""
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)

    full = [message for message in tablet.sets if message.get("f") == 1]
    assert full, tablet.sets
    plan = session.want.plan
    assert {pair[0] for pair in full[-1]["v"]} == {entry["d"] for entry in plan}
    booleans = [entry["d"] for entry in plan if entry["type"] == "b"]
    assert booleans
    assert all(tablet.slot(number) == 1 for number in booleans)

    sent = len(tablet.sets)
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    await until(hass, lambda: all(tablet.slot(number) == 0 for number in booleans))
    changes = tablet.sets[sent:]
    assert changes
    assert all("f" not in message for message in changes)
    assert all(message["h"] == tablet.active for message in changes)


async def test_slot_error_sends_null(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A value that has no type-correct form is sent as no value."""
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)

    # A deleted entity renders as unknown: every value of the card is null
    # or text, never a value of the wrong type.
    hass.states.async_remove("light.kitchen")
    await until(hass, lambda: not session.live.changes())
    for entry in session.want.plan:
        value = tablet.slot(entry["d"])
        if entry["type"] in ("n", "b") and value is not None:
            assert isinstance(value, int | float)


async def test_debounce_under_rapid_autosave(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Several saves in a row end in one transfer of the last layout."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    commits = len(tablet.calls_of("tab_commit"))

    for title in ("One", "Two", "Three", "Four"):
        await save_tab_dashboard("tab-home", tab_config(light_card(), title=title))
    await until(
        hass,
        lambda: (
            session.status == STATUS_ON_TABLET
            and session.want.layout["pages"][0]["title"] == "Four"
            and tablet.active == session.want.hash
        ),
    )
    assert len(tablet.calls_of("tab_commit")) - commits <= 2


def test_debounce_waits_after_the_last_change_at_most_two_seconds() -> None:
    """0.7 s after the last change, but never later than 2 s after the first."""
    assert sender_module.DEBOUNCE_S == 0.7
    assert sender_module.DEBOUNCE_MAX_S == 2.0


async def test_debounce_timer_rules(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The send timer restarts on every change but keeps the first deadline."""
    monkeypatch.setattr(sender_module, "DEBOUNCE_S", 0.7)
    monkeypatch.setattr(sender_module, "DEBOUNCE_MAX_S", 2.0)
    make_tablet()
    await setup_integration(hass, config_entry)
    session = session_of(config_entry)
    loop = hass.loop
    start = loop.time()
    session.converted()
    assert session._debounce.when() - start == pytest.approx(0.7, abs=0.05)
    clock = [start]
    monkeypatch.setattr(session, "_now", lambda: clock[0])
    for later in (0.5, 1.0, 1.5):
        clock[0] = start + later
        session.converted()
    # The last change was 1.5 s after the first: 0.5 s are left of the 2 s.
    assert session._debounce.when() - loop.time() <= 0.55
    session._debounce.cancel()
    session._debounce = None


async def test_newer_hash_during_transfer_starts_over(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A change while a build runs starts again from seq 0 with the new hash."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    first = tablet.active

    tablet.hold_build = True
    await save_tab_dashboard("tab-home", tab_config(light_card(), title="Two"))
    await until(hass, lambda: tablet.staged not in ("", first))
    second = tablet.staged
    await save_tab_dashboard("tab-home", tab_config(light_card(), title="Three"))
    await until(hass, lambda: tablet.staged not in ("", first, second))
    third = tablet.staged
    # The tablet dropped the unfinished build of the second hash.
    assert tablet.active == first
    starts = [
        args["hash"] for args in tablet.calls_of("tab_layout") if args["seq"] == 0
    ]
    assert starts[-2:] == [second, third]

    tablet.hold_build = False
    await until(
        hass, lambda: session.status == STATUS_ON_TABLET and tablet.active == third
    )


async def test_build_failure_keeps_old_layout_and_retries(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A build that ends without showing the layout fails with the tablet's code."""
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    first = tablet.active

    tablet.fail_build = "memory"
    await save_tab_dashboard("tab-home", tab_config(light_card(), title="Two"))
    await until(hass, lambda: session.status == STATUS_FAILED)
    assert (session.reason, session.retry) == ("memory", True)
    assert tablet.active == first
    # The old screen keeps its values: a full snapshot went to it again.
    assert tablet.sets[-1]["h"] == first

    tablet.fail_build = None
    async_fire_time_changed(hass, dt_util.utcnow() + sender_module_timedelta(6))
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert tablet.active == session.want.hash != first


def sender_module_timedelta(seconds: float) -> timedelta:
    """Return a timedelta, for moving the clock past a retry."""
    return timedelta(seconds=seconds)


async def test_too_big_is_refused_before_any_chunk(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """HA checks the tablet's caps first; too_big is final, without a transfer."""
    tablet = make_tablet(caps={"max_layout": 200})
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = session_of(config_entry)

    await until(hass, lambda: session.status == STATUS_FAILED)
    assert (session.reason, session.retry) == ("too_big", False)
    assert tablet.calls_of("tab_layout") == []
    assert session._cancel_retry is None


async def test_deterministic_tablet_error_is_not_retried(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A version error from the tablet cannot succeed until something changes."""
    tablet = make_tablet()
    tablet.fail_next["tab_commit"] = "version"
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = session_of(config_entry)

    await until(hass, lambda: session.status == STATUS_FAILED)
    assert (session.reason, session.retry) == ("version", False)
    commits = len(tablet.calls_of("tab_commit"))
    async_fire_time_changed(hass, dt_util.utcnow() + sender_module_timedelta(400))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(tablet.calls_of("tab_commit")) == commits


async def test_dead_layout_is_not_sent_again_after_a_stale_tap(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A tap on a layout HA does not keep makes HA look, not send again.

    The layout failed for good (a version error), so the tap's check of
    what the tablet shows must not send it once more.
    """
    tablet = make_tablet()
    tablet.fail_next["tab_commit"] = "version"
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = session_of(config_entry)
    await until(hass, lambda: session.status == STATUS_FAILED)
    layouts = len(tablet.calls_of("tab_layout"))
    commits = len(tablet.calls_of("tab_commit"))
    statuses = len(tablet.calls_of("tab_status"))

    tablet.tap(1, layout="0123456789abcdef")
    await until(hass, lambda: len(tablet.acks) == 1)
    assert tablet.acks[0][2] == "stale"
    await until(hass, lambda: len(tablet.calls_of("tab_status")) > statuses)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(tablet.calls_of("tab_layout")) == layouts
    assert len(tablet.calls_of("tab_commit")) == commits
    assert (session.status, session.reason, session.retry) == (
        STATUS_FAILED,
        "version",
        False,
    )


async def test_entity_swap_with_same_hash_sends_a_snapshot(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Pointing a card at another entity keeps the hash but sends new values."""
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    hass.states.async_set("light.sofa", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card("light.kitchen")))
    session = await on_tablet(hass, config_entry)
    first = tablet.active
    booleans = [entry["d"] for entry in session.want.plan if entry["type"] == "b"]
    assert all(tablet.slot(number) == 1 for number in booleans)
    chunks = len(tablet.calls_of("tab_layout"))
    full = sum(1 for message in tablet.sets if message.get("f") == 1)

    await save_tab_dashboard("tab-home", tab_config(light_card("light.sofa")))
    await until(hass, lambda: all(tablet.slot(number) == 0 for number in booleans))
    assert tablet.active == first == session.want.hash
    assert len(tablet.calls_of("tab_layout")) == chunks
    assert sum(1 for message in tablet.sets if message.get("f") == 1) == full + 1
    # The swapped card's actions now name the new entity.
    actions = session.want.bindings["actions"].values()
    assert all(action["entities"] == ["light.sofa"] for action in actions)

    # Changes of the old entity no longer reach the tablet.
    sent = len(tablet.sets)
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(tablet.sets) == sent


async def test_offline_and_no_engine(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    memory_link: MemoryTabletLink,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    entity_registry: er.EntityRegistry,
) -> None:
    """The status follows the connection; the engine sensor follows the tablet."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    sensor = entity_registry.async_get_entity_id(
        "sensor", "apollo_tab", f"{MAC}_dashboard_engine"
    )
    await until(hass, lambda: hass.states.get(sensor).state == "ready")
    assert hass.states.get(sensor).attributes["engine_version"] == "0.1.0"

    tablet.connected = False
    memory_link.async_refresh(MAC)
    await until(hass, lambda: session.status == STATUS_OFFLINE)
    assert session.nonce is None
    assert session.live is None
    # The last known engine state stays while the tablet is offline.
    assert hass.states.get(sensor).state == "ready"

    tablet.connected = True
    tablet.has_engine = False
    memory_link.async_refresh(MAC)
    await until(hass, lambda: session.status == STATUS_NO_ENGINE)
    await until(hass, lambda: hass.states.get(sensor).state == "not_installed")


@pytest.mark.parametrize(
    ("proto", "reason"), [((0, 0), "tablet_old"), ((2, 3), "tablet_new")]
)
async def test_no_common_protocol(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    entity_registry: er.EntityRegistry,
    proto: tuple[int, int],
    reason: str,
) -> None:
    """A tablet with no protocol version in common gets nothing sent."""
    tablet = make_tablet(proto=proto)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = session_of(config_entry)

    await until(hass, lambda: session.status == STATUS_UNSUPPORTED)
    assert session.reason == reason
    assert tablet.calls_of("tab_layout") == []
    assert tablet.calls_of("tab_pair") == []
    sensor = entity_registry.async_get_entity_id(
        "sensor", "apollo_tab", f"{MAC}_dashboard_engine"
    )
    await until(hass, lambda: hass.states.get(sensor).state == "update_needed")


async def test_reconnect_after_reload_greets_and_sends_values_only(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    memory_link: MemoryTabletLink,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A new connection gets a handshake and a snapshot, not the same layout."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    chunks = len(tablet.calls_of("tab_layout"))
    hellos = len(tablet.calls_of("tab_hello"))
    full = sum(1 for message in tablet.sets if message.get("f") == 1)

    memory_link.async_reconnect(MAC)
    await until(
        hass,
        lambda: (
            len(tablet.calls_of("tab_hello")) > hellos
            and session.status == STATUS_ON_TABLET
            and sum(1 for message in tablet.sets if message.get("f") == 1) > full
        ),
    )
    assert len(tablet.calls_of("tab_layout")) == chunks
    assert tablet.calls_of("tab_pair") == tablet.calls_of("tab_pair")[:1]


async def test_tablet_reboot_knock_and_ignored_knocks(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A knock never resets a session by itself (contract 2.2).

    With a session HA reads tab_status first and greets again only when the
    tablet says it has none. The boot number does not matter.
    """
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    hellos = len(tablet.calls_of("tab_hello"))
    nonce = session.nonce

    # Any ESPHome device can fire a knock with the tablet's MAC and any boot.
    for boot in (tablet.boot, tablet.boot + 7):
        statuses = len(tablet.calls_of("tab_status"))
        session._last_knock -= sender_module.KNOCK_EVERY_S + 1
        tablet.knock(boot=boot)
        await until(
            hass, lambda before=statuses: len(tablet.calls_of("tab_status")) > before
        )
        await hass.async_block_till_done(wait_background_tasks=True)
        assert len(tablet.calls_of("tab_hello")) == hellos
        assert session.nonce == nonce == tablet.nonce

    # The tablet lost its session on a reconnect HA did not see.
    tablet.nonce = None
    session._last_knock -= sender_module.KNOCK_EVERY_S + 1
    tablet.knock()
    await until(hass, lambda: len(tablet.calls_of("tab_hello")) == hellos + 1)
    await until(
        hass,
        lambda: session.status == STATUS_ON_TABLET and session.nonce is not None,
    )
    assert session.nonce == tablet.nonce != nonce

    # A reboot HA did not see: the same, with a new boot number.
    tablet.reboot()
    session._last_knock -= sender_module.KNOCK_EVERY_S + 1
    tablet.knock()
    await until(hass, lambda: len(tablet.calls_of("tab_hello")) == hellos + 2)
    await until(
        hass,
        lambda: session.status == STATUS_ON_TABLET and session.nonce is not None,
    )
    assert session.boot == tablet.boot

    # A second knock within 2 s is not answered at all.
    statuses = len(tablet.calls_of("tab_status"))
    tablet.knock(boot=99)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(tablet.calls_of("tab_hello")) == hellos + 2
    assert len(tablet.calls_of("tab_status")) == statuses

    # Unparsable knocks and knocks for unknown tablets do nothing.
    session._last_knock -= sender_module.KNOCK_EVERY_S + 1
    hass.bus.async_fire("esphome.tab1_hello", {"d": "1|zz|1"})
    hass.bus.async_fire("esphome.tab1_hello", {"d": "1|0123456789ab|1"})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(tablet.calls_of("tab_hello")) == hellos + 2
    assert len(tablet.calls_of("tab_status")) == statuses


async def test_knock_without_a_session_greets(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Without a session on this connection a knock gets tab_hello at once."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    hellos = len(tablet.calls_of("tab_hello"))
    statuses = len(tablet.calls_of("tab_status"))
    session.drop_session()
    session._last_knock -= sender_module.KNOCK_EVERY_S + 1
    tablet.knock()
    await until(hass, lambda: len(tablet.calls_of("tab_hello")) == hellos + 1)
    await until(
        hass,
        lambda: session.status == STATUS_ON_TABLET and session.nonce is not None,
    )
    assert len(tablet.calls_of("tab_status")) == statuses


async def test_refused_signature_pairs_again(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A tablet that lost or changed its secret is paired again."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    session._last_pair -= 120  # the last pairing was more than a minute ago

    # Another secret on the tablet, as after another HA paired it away.
    tablet.secret = bytes(32)
    tablet.nonce = None
    await save_tab_dashboard("tab-home", tab_config(light_card(), title="Two"))
    await until(
        hass,
        lambda: (
            session.status == STATUS_ON_TABLET
            and tablet.active == session.want.hash
            and session.want.layout["pages"][0]["title"] == "Two"
        ),
    )
    assert len(tablet.calls_of("tab_pair")) == 2
    assert tablet.secret == config_entry.runtime_data.assignments.secret(MAC)
    assert session.paired


async def test_pairing_is_rate_limited(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """At most one pairing per minute per tablet."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    assert len(tablet.calls_of("tab_pair")) == 1

    session.request_pair()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(tablet.calls_of("tab_pair")) == 1

    # A minute later (the loop clock does not move in tests, so the last
    # pairing is moved back instead).
    session._last_pair -= 61
    async_fire_time_changed(hass, dt_util.utcnow() + sender_module_timedelta(61))
    await until(hass, lambda: len(tablet.calls_of("tab_pair")) == 2)
    await until(hass, lambda: session.status == STATUS_ON_TABLET)


@pytest.mark.parametrize("how", ["refused", "lost"])
async def test_failed_first_pairing_is_tried_again_after_a_minute(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    how: str,
) -> None:
    """A first pairing the tablet refused, or that got lost, is tried again.

    The tablet is not paired then and takes its dashboard unsigned, so the
    send succeeds and nothing else would greet it again.
    """
    tablet = make_tablet()
    if how == "refused":
        tablet.fail_next["tab_pair"] = "bad_key"
    else:
        tablet.timeout_next.add("tab_pair")
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    assert session.input == "not_paired"
    assert not tablet.paired
    assert len(tablet.calls_of("tab_pair")) == 1
    chunks = len(tablet.calls_of("tab_layout"))

    # A minute later (the loop clock does not move in tests, so the last
    # pairing is moved back instead).
    session._last_pair -= 61
    async_fire_time_changed(hass, dt_util.utcnow() + sender_module_timedelta(61))
    await until(hass, lambda: len(tablet.calls_of("tab_pair")) == 2)
    await until(
        hass, lambda: session.status == STATUS_ON_TABLET and session.input == "ok"
    )
    assert tablet.secret == config_entry.runtime_data.assignments.secret(MAC)
    # The dashboard on its screen is not sent again.
    assert len(tablet.calls_of("tab_layout")) == chunks
    assert tablet.refused == []


async def test_lost_pairing_of_an_erased_tablet_is_tried_again(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    memory_link: MemoryTabletLink,
) -> None:
    """A tablet paired before and erased, whose new pairing got lost.

    It holds no secret, so it takes every call and the send succeeds. Home
    Assistant says its taps do not work until the pairing a minute later.
    """
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    assert session.input == "ok"
    old = tablet.secret
    pairs = len(tablet.calls_of("tab_pair"))

    # Erased and set up again with its key: no secret, no session.
    tablet.secret = None
    tablet.nonce = None
    tablet.timeout_next.add("tab_pair")
    session._last_pair -= 61
    memory_link.async_reconnect(MAC)
    await until(hass, lambda: session.status == STATUS_FAILED)
    assert (session.reason, session.retry) == ("timeout", True)
    assert len(tablet.calls_of("tab_pair")) == pairs + 1
    assert session.input == "not_paired"

    # The retry after the failure greets again and sends as before.
    async_fire_time_changed(hass, dt_util.utcnow() + sender_module_timedelta(6))
    await on_tablet(hass, config_entry)
    assert not tablet.paired
    row = sender_of(config_entry).tablet_json(session)
    assert (row["input"], row["paired"]) == ("not_paired", False)
    assert len(tablet.calls_of("tab_pair")) == pairs + 1

    # A minute later (the last pairing is moved back, as in
    # test_pairing_is_rate_limited).
    session._last_pair -= 61
    async_fire_time_changed(hass, dt_util.utcnow() + sender_module_timedelta(61))
    await until(hass, lambda: len(tablet.calls_of("tab_pair")) == pairs + 2)
    await until(
        hass, lambda: session.status == STATUS_ON_TABLET and session.input == "ok"
    )
    assert tablet.secret not in (None, old)
    assert tablet.secret == config_entry.runtime_data.assignments.secret(MAC)
    assert tablet.refused == []


async def test_pairing_whose_answer_got_lost_is_tried_again(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """The tablet took the new secret, but its answer never arrived.

    Home Assistant still holds the old secret. It says the tablet's taps do
    not work, signs nothing the tablet would refuse, and pairs again a
    minute later.
    """
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    assignments = config_entry.runtime_data.assignments
    old = tablet.secret
    pairs = len(tablet.calls_of("tab_pair"))
    take_secret = tablet._on_tab_pair

    def answer_lost(**args: str) -> dict:
        """Take the secret; the answer does not reach Home Assistant."""
        tablet._on_tab_pair = take_secret
        take_secret(**args)
        raise LinkError("timeout")

    tablet._on_tab_pair = answer_lost
    session._last_pair -= 61
    session.request_pair()
    await until(hass, lambda: session.status == STATUS_FAILED)
    assert (session.reason, session.retry) == ("timeout", True)
    assert tablet.secret not in (old, assignments.secret(MAC))
    assert session.input == "not_paired"

    # The retry greets again; the tablet refuses the old secret's greeting.
    async_fire_time_changed(hass, dt_util.utcnow() + sender_module_timedelta(6))
    await until(hass, lambda: session.reason == "auth")
    assert (session.status, session.retry) == (STATUS_FAILED, True)
    row = sender_of(config_entry).tablet_json(session)
    assert (row["input"], row["paired"]) == ("not_paired", False)
    assert len(tablet.calls_of("tab_pair")) == pairs + 1
    assert tablet.refused == []

    session._last_pair -= 61
    async_fire_time_changed(hass, dt_util.utcnow() + sender_module_timedelta(61))
    await until(hass, lambda: len(tablet.calls_of("tab_pair")) == pairs + 2)
    await until(
        hass, lambda: session.status == STATUS_ON_TABLET and session.input == "ok"
    )
    assert tablet.secret == assignments.secret(MAC)
    assert tablet.refused == []


async def test_paired_tablet_that_lost_one_pairing_call_works_on(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A new secret an admin asked for, whose call never reached the tablet.

    The tablet still holds the old secret. The next greeting finds that out:
    its taps work again and its row asks nothing of the admin. The new
    secret follows a minute later.
    """
    toggles = async_mock_service(hass, "light", "toggle")
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    assignments = config_entry.runtime_data.assignments
    old = tablet.secret
    pairs = len(tablet.calls_of("tab_pair"))
    widget = next(
        int(key.partition(":")[0])
        for key, action in session.want.bindings["actions"].items()
        if action["output"] == "toggle"
    )

    tablet.timeout_next.add("tab_pair")
    session._last_pair -= 61
    session.request_pair()
    await until(hass, lambda: session.status == STATUS_FAILED)
    assert len(tablet.calls_of("tab_pair")) == pairs + 1
    # Home Assistant cannot tell which secret the tablet holds now.
    assert session.input == "not_paired"

    async_fire_time_changed(hass, dt_util.utcnow() + sender_module_timedelta(6))
    await until(
        hass, lambda: session.status == STATUS_ON_TABLET and session.input == "ok"
    )
    assert tablet.secret == old == assignments.secret(MAC)
    row = sender_of(config_entry).tablet_json(session)
    assert (row["status"], row["reason"]) == (STATUS_ON_TABLET, "")
    assert (row["approved"], row["paired"], row["input"]) == (True, True, "ok")
    assert row["reauth"] is None
    assert len(tablet.calls_of("tab_pair")) == pairs + 1
    tablet.tap(widget)
    await until(hass, lambda: tablet.acks == [(1, True, "")])
    assert len(toggles) == 1

    session._last_pair -= 61
    async_fire_time_changed(hass, dt_util.utcnow() + sender_module_timedelta(61))
    await until(hass, lambda: len(tablet.calls_of("tab_pair")) == pairs + 2)
    await until(
        hass, lambda: session.status == STATUS_ON_TABLET and session.input == "ok"
    )
    assert tablet.secret not in (None, old)
    assert tablet.secret == assignments.secret(MAC)
    assert tablet.refused == []


async def test_pair_request_waits_for_the_limit_and_keeps_the_session(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """An admin's pair request within a minute waits for the limit.

    Meanwhile the session stays and values keep flowing, and a send that
    succeeds in between does not cancel the request.
    """
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    old = tablet.secret
    nonce = session.nonce
    booleans = [e["d"] for e in session.want.plan if e["type"] == "b"]
    assert booleans
    assert all(tablet.slot(n) == 1 for n in booleans)

    session.request_pair()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(tablet.calls_of("tab_pair")) == 1
    assert session.nonce == nonce

    # Values keep flowing while the request waits.
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    await until(hass, lambda: all(tablet.slot(n) == 0 for n in booleans))

    # A new layout goes out in between and succeeds.
    await save_tab_dashboard("tab-home", tab_config(light_card(), title="Two"))
    await until(
        hass,
        lambda: (
            session.status == STATUS_ON_TABLET
            and session.want.layout["pages"][0]["title"] == "Two"
            and tablet.active == session.want.hash
        ),
    )

    # Half a minute later the limit still holds.
    async_fire_time_changed(hass, dt_util.utcnow() + sender_module_timedelta(30))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(tablet.calls_of("tab_pair")) == 1
    assert session.nonce == nonce

    # A minute after the last pairing (the last pairing is moved back, as in
    # test_pairing_is_rate_limited).
    session._last_pair -= 61
    async_fire_time_changed(hass, dt_util.utcnow() + sender_module_timedelta(61))
    await until(hass, lambda: len(tablet.calls_of("tab_pair")) == 2)
    await until(
        hass,
        lambda: session.status == STATUS_ON_TABLET and session.nonce is not None,
    )
    assert tablet.secret != old
    assert tablet.secret == config_entry.runtime_data.assignments.secret(MAC)
    assert session.input == "ok"


async def test_value_after_a_set_timeout_is_sent_again(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A tab_set that times out is sent again without a new change."""
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    booleans = [e["d"] for e in session.want.plan if e["type"] == "b"]
    assert booleans
    sets = len(tablet.calls_of("tab_set"))

    tablet.timeout_next.add("tab_set")
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    await until(hass, lambda: all(tablet.slot(n) == 0 for n in booleans))
    # The first try timed out; the second one went through.
    assert len(tablet.calls_of("tab_set")) - sets >= 2
    assert session.live.changes() == {}


async def test_wrong_hash_on_set_greets_again(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """tab_set answered with hash means the tablet has another layout."""
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    hellos = len(tablet.calls_of("tab_hello"))
    wanted = tablet.active

    # The tablet lost its layout without HA knowing.
    tablet.active = ""
    tablet.stored = ""
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    await until(
        hass,
        lambda: (
            len(tablet.calls_of("tab_hello")) > hellos
            and tablet.active == wanted
            and session.status == STATUS_ON_TABLET
        ),
    )


async def test_needs_encryption(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Without API encryption layouts and values work, taps do not."""
    tablet = make_tablet(psk=None)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)

    assert session.input == "needs_encryption"
    assert session.paired is False
    assert tablet.calls_of("tab_pair") == []
    assert tablet.active == session.want.hash


async def test_dashboard_removed_moves_tablet_and_sends(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Deleting the shown dashboard sends the first remaining one."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(light_card(), title="A"), title="A")
    await save_tab_dashboard("tab-b", tab_config(light_card(), title="B"), title="B")
    session = await on_tablet(hass, config_entry)
    assert session.dashboard == "tab-a"

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "lovelace/dashboards/list"})
    items = (await client.receive_json())["result"]
    dashboard_id = next(item["id"] for item in items if item["url_path"] == "tab-a")
    await client.send_json_auto_id(
        {"type": "lovelace/dashboards/delete", "dashboard_id": dashboard_id}
    )
    assert (await client.receive_json())["success"]
    await until(
        hass,
        lambda: (
            session.dashboard == "tab-b"
            and session.status == STATUS_ON_TABLET
            and tablet.active == session.want.hash
        ),
    )
    assert session.want.layout["pages"][0]["title"] == "B"


async def test_last_dashboard_removed_clears_the_tablet(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """With no dashboard left the tablet is cleared and shows nothing."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(light_card()), title="A")
    session = await on_tablet(hass, config_entry)

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "lovelace/dashboards/list"})
    items = (await client.receive_json())["result"]
    await client.send_json_auto_id(
        {"type": "lovelace/dashboards/delete", "dashboard_id": items[0]["id"]}
    )
    assert (await client.receive_json())["success"]
    await until(hass, lambda: session.status == STATUS_NO_DASHBOARD)
    assert session.dashboard is None
    assert len(tablet.calls_of("tab_clear")) == 1
    assert tablet.active == ""
    assert tablet.refused == []


async def test_unreadable_dashboard_keeps_layout(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dashboard that cannot be read keeps its tablets and their screen."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(light_card()), title="A")
    session = await on_tablet(hass, config_entry)
    shown = tablet.active
    data = config_entry.runtime_data

    async def unreadable(_hass, _url_path):
        """Act like a dashboard whose YAML has an error."""
        return "error", None

    monkeypatch.setattr(
        "custom_components.apollo_tab.compat.async_probe_dashboard", unreadable
    )
    data.manager._drop("tab-a")
    await until(hass, lambda: session.status == STATUS_FAILED)
    assert (session.reason, session.retry) == ("unreadable", False)
    assert session.dashboard == "tab-a"
    assert tablet.active == shown
    assert tablet.calls_of("tab_clear") == []


async def test_yaml_dashboard_without_its_file_keeps_its_tablets(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    tmp_path,
) -> None:
    """A YAML dashboard whose file is away after a restart keeps its tablets.

    Before its first load Home Assistant reports the missing file like a
    storage dashboard that was never saved. The tablets stay on it and get
    it again once the file is back.
    """
    from homeassistant.components.lovelace.dashboard import LovelaceYAML

    from custom_components.apollo_tab import compat

    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    hass.config.config_dir = str(tmp_path)
    data = config_entry.runtime_data
    path = tmp_path / "tab-yaml.yaml"
    path.write_text(json.dumps(tab_config(light_card())))
    dashboards = hass.data[compat.LOVELACE_DATA].dashboards
    yaml_config = {"mode": "yaml", "filename": "tab-yaml.yaml", "title": "Yaml"}
    dashboards["tab-yaml"] = LovelaceYAML(hass, "tab-yaml", yaml_config)
    await data.manager.async_convert("tab-yaml")
    session = await on_tablet(hass, config_entry)
    assert session.dashboard == "tab-yaml"
    shown = tablet.active
    # Another dashboard the tablet could be moved to.
    await save_tab_dashboard("tab-other", tab_config(light_card()), title="Other")
    assert session.dashboard == "tab-yaml"

    # As after a restart: no cached copy, and the file is not there.
    path.unlink()
    dashboards["tab-yaml"] = LovelaceYAML(hass, "tab-yaml", yaml_config)
    await data.manager.async_convert("tab-yaml")
    await until(hass, lambda: session.status == STATUS_FAILED)
    assert (session.reason, session.retry) == ("unreadable", False)
    assert session.dashboard == "tab-yaml"
    assert tablet.active == shown
    assert tablet.calls_of("tab_clear") == []

    path.write_text(json.dumps(tab_config(light_card())))
    await data.manager.async_convert("tab-yaml")
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert session.dashboard == "tab-yaml"


async def test_removed_tablet_stops_its_trackers(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A tablet that leaves Home Assistant stops following its entities."""
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    assert session.live is not None
    sets = len(tablet.sets)
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    await until(hass, lambda: len(tablet.sets) > sets)

    device_registry.async_remove_device(async_get_tablets(hass)[MAC].id)
    await until(hass, lambda: MAC not in sender_of(config_entry).sessions)
    assert session.live is None
    assert not session.running
    sets = len(tablet.sets)
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    await asyncio.sleep(0.05)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(tablet.sets) == sets


async def test_integration_removal_clears_tablets_and_secrets(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_storage: dict,
) -> None:
    """Removing the integration blanks reachable tablets and deletes secrets."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(light_card()))
    await on_tablet(hass, config_entry)
    assert tablet.active

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert tablet.active == ""
    assert len(tablet.calls_of("tab_clear")) == 1
    assert tablet.refused == []
    assert "apollo_tab.tablets" not in hass_storage


async def test_assignments_are_stored(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_storage: dict,
) -> None:
    """The store holds dashboard, secret, kid, approval and entry per MAC."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(light_card()))
    await on_tablet(hass, config_entry)
    entry_id = config_entry.runtime_data.sender.sessions[MAC].entry_id
    assert tablet.paired
    assert await hass.config_entries.async_unload(config_entry.entry_id)

    stored = hass_storage["apollo_tab.tablets"]
    assert stored["version"] == 1
    record = stored["data"]["tablets"][MAC]
    assert set(record) == {"dashboard", "secret", "kid", "approved", "entry_id"}
    assert record["approved"] is True
    assert record["entry_id"] == entry_id
    assert record["dashboard"] == "tab-a"
    secret = bytes.fromhex(record["secret"])
    assert record["kid"] == tp.kid(secret)
    assert json.dumps(stored).count(record["secret"]) == 1


async def test_restart_resends_nothing_when_tablet_has_layout(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """After a reload the tablet keeps its layout and gets values only."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(light_card()))
    await on_tablet(hass, config_entry)
    chunks = len(tablet.calls_of("tab_layout"))
    pairs = len(tablet.calls_of("tab_pair"))

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    session = await on_tablet(hass, config_entry)
    assert len(tablet.calls_of("tab_layout")) == chunks
    assert len(tablet.calls_of("tab_pair")) == pairs
    assert session.paired


async def test_ten_conversions_in_a_row_give_one_transfer(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Autosave fires "converted" for every edit; the tablet gets the last."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    monkeypatch.setattr(sender_module, "DEBOUNCE_S", 0.5)
    monkeypatch.setattr(sender_module, "DEBOUNCE_MAX_S", 2.0)
    commits = len(tablet.calls_of("tab_commit"))
    starts = len([a for a in tablet.calls_of("tab_layout") if a["seq"] == 0])

    for number in range(10):
        await save_tab_dashboard(
            "tab-home", tab_config(light_card(), title=f"Edit {number}")
        )
    await until(
        hass,
        lambda: (
            session.status == STATUS_ON_TABLET
            and session.want.layout["pages"][0]["title"] == "Edit 9"
            and tablet.active == session.want.hash
        ),
    )
    assert len(tablet.calls_of("tab_commit")) == commits + 1
    assert len([a for a in tablet.calls_of("tab_layout") if a["seq"] == 0]) == (
        starts + 1
    )


async def test_split_snapshot(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A big snapshot goes out in parts; only the first part clears the slots."""
    real_encode = tp.encode_set

    def small_encode(layout, values, *, full):
        """Split at 60 bytes instead of 12000."""
        return real_encode(layout, values, full=full, limit=60)

    monkeypatch.setattr(sender_module.tp, "encode_set", small_encode)
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard(
        "tab-home", tab_config(light_card(), light_card(), light_card())
    )
    session = await on_tablet(hass, config_entry)

    first_full = next(i for i, m in enumerate(tablet.sets) if m.get("f") == 1)
    parts = []
    for message in tablet.sets[first_full:]:
        if parts and message.get("f") == 1:
            break
        parts.append(message)
    assert len(parts) > 1
    assert all("f" not in message for message in parts[1:])
    assert all(len(json.dumps(message)) < 200 for message in parts)
    numbers = sorted(pair[0] for message in parts for pair in message["v"])
    assert numbers == sorted(entry["d"] for entry in session.want.plan)
    for entry in session.want.plan:
        assert tablet.slot(entry["d"]) == session.live.wire[entry["d"]]


async def test_failure_backs_off(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retries come after 5 s, 15 s, 60 s, then every 5 minutes."""
    make_tablet()
    await setup_integration(hass, config_entry)
    session = session_of(config_entry)
    delays: list[float] = []

    def record(_hass, delay, _action):
        """Record the delay instead of starting a timer."""
        delays.append(delay)
        return lambda: None

    monkeypatch.setattr(sender_module, "async_call_later", record)
    for _ in range(5):
        session._fail("memory", retry=True)
    assert delays == [5, 15, 60, 300, 300]
    session._succeeded()
    session._fail("memory", retry=True)
    assert delays[-1] == 5
    session._cancel_retry = None


async def test_unload_stops_everything(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    memory_link: MemoryTabletLink,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Unloading during a build stops the run, the values and the link."""
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    tablet.hold_build = True
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    sender = sender_of(config_entry)
    session = session_of(config_entry)
    await until(hass, lambda: tablet.staged != "")
    assert session.running

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert sender.sessions == {}
    assert not session.running
    assert session.live is None
    assert memory_link.watched == {}
    calls = len(tablet.calls)
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet.knock(boot=7)
    await hass.async_block_till_done()
    assert len(tablet.calls) == calls


async def test_switch_back_during_a_build_drops_that_build(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Back to the shown dashboard while another one builds: that build goes.

    A is on screen, B is committed and still building. Putting the tablet
    back on A must not leave B to replace A when its build ends: HA sends A
    again from seq 0, which drops B's build, and reports "on the tablet"
    only after the tablet confirms A (contract 5).
    """
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(light_card(), title="A"), title="A")
    await save_tab_dashboard("tab-b", tab_config(light_card(), title="B"), title="B")
    session = await on_tablet(hass, config_entry)
    assert session.dashboard == "tab-a"
    shown = tablet.active
    assignments = config_entry.runtime_data.assignments

    tablet.hold_build = True
    assignments.async_assign(MAC, "tab-b")
    await until(hass, lambda: tablet.staged not in ("", shown))
    other = tablet.staged
    commits = len(tablet.calls_of("tab_commit"))

    assignments.async_assign(MAC, "tab-a")
    await until(
        hass,
        lambda: (
            session.status == STATUS_ON_TABLET
            and session.want.url_path == "tab-a"
            and session.staged is None
        ),
    )
    # A went out again from seq 0, so the tablet no longer builds B.
    assert tablet.staged == ""
    starts = [
        args["hash"] for args in tablet.calls_of("tab_layout") if args["seq"] == 0
    ]
    assert starts[-2:] == [other, shown]
    assert [args["hash"] for args in tablet.calls_of("tab_commit")[commits:]] == [shown]
    tablet.hold_build = False
    tablet.finish_build()
    assert tablet.active == shown == session.shown
    assert session.reason == ""


async def test_tap_on_an_unexpected_layout_reads_what_the_tablet_shows(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A tap on a layout HA keeps no bindings for makes HA ask tab_status.

    HA does not trust what it last knew: the tablet shows something else,
    so the wanted layout is sent again.
    """
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(light_card(), title="A"), title="A")
    session = await on_tablet(hass, config_entry)
    wanted = tablet.active
    commits = len(tablet.calls_of("tab_commit"))

    # The tablet shows another layout without HA knowing (staged earlier,
    # its build ended while HA looked away).
    tablet.active = "0123456789abcdef"
    tablet.stored = tablet.active
    tablet.tap(1)
    await until(hass, lambda: len(tablet.acks) == 1)
    assert tablet.acks[0][2] == "stale"
    await until(
        hass,
        lambda: tablet.active == wanted and session.status == STATUS_ON_TABLET,
    )
    assert len(tablet.calls_of("tab_commit")) == commits + 1


async def test_newer_save_during_a_transfer_stops_the_old_commit(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A second save while a transfer is in flight: the old hash is never committed.

    The transfer stops at the next chunk, only the new hash is committed,
    and nothing waits for a timeout.
    """
    import asyncio

    tablet = make_tablet(caps={"max_chunk": 200})
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    first = tablet.active
    statuses: list[tuple[str, str]] = []
    sender_of(config_entry).async_listen(
        lambda: statuses.append((session.status, session.reason))
    )
    handle = tablet.async_call
    slowed: list[str] = []

    async def slow_first_chunk(action: str, args: dict) -> dict | None:
        """Hold the first chunk of a new hash, as a slow connection would."""
        new_hash = action == "tab_layout" and args["hash"] != first
        if new_hash and args["seq"] == 0 and not slowed:
            slowed.append(args["hash"])
            await asyncio.sleep(0.4)
        return await handle(action, args)

    tablet.async_call = slow_first_chunk
    await save_tab_dashboard("tab-home", tab_config(light_card(), title="Two"))
    await until(hass, lambda: slowed)
    await save_tab_dashboard("tab-home", tab_config(light_card(), title="Three"))
    await until(
        hass,
        lambda: (
            session.status == STATUS_ON_TABLET
            and session.want.layout["pages"][0]["title"] == "Three"
            and tablet.active == session.want.hash
        ),
    )
    old = slowed[0]
    committed = [args["hash"] for args in tablet.calls_of("tab_commit")]
    assert old not in committed
    assert committed[-1] == session.want.hash != old
    assert ("failed", "timeout") not in statuses
    # The old transfer stopped after its first chunk.
    assert [
        args["seq"] for args in tablet.calls_of("tab_layout") if args["hash"] == old
    ] == [0]


async def test_nothing_is_sent_before_the_manager_is_ready(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No call reaches a tablet before the manager's first conversion run."""
    from custom_components.apollo_tab import manager as manager_module

    started: list = []
    monkeypatch.setattr(
        manager_module,
        "async_at_started",
        lambda _hass, action: started.append(action) or (lambda: None),
    )
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = session_of(config_entry)
    data = config_entry.runtime_data
    assert not data.manager.ready
    # A connection change and a knock while the manager is not ready.
    session.link_changed("ready")
    session._last_knock -= sender_module.KNOCK_EVERY_S + 1
    tablet.knock()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert tablet.calls == []
    assert session.status == STATUS_SENDING

    await started[0](hass)
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert tablet.calls[0][0] == "tab_hello"
    assert tablet.active == session.want.hash


async def test_unsigned_set_is_never_sent_while_the_session_renews(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A value change while HA renews a lost session is not sent unsigned.

    The tablet lost its session on a reconnect HA did not see and knocks.
    HA asks tab_status, drops its session and greets again. A change that
    waited for tab_status must not go out without auth: the tablet would
    refuse it and HA would make a new secret for nothing.
    """
    import asyncio

    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    pairs = len(tablet.calls_of("tab_pair"))
    secret = tablet.secret
    booleans = [e["d"] for e in session.want.plan if e["type"] == "b"]
    handle = tablet.async_call

    async def slow_status(action: str, args: dict) -> dict | None:
        """Answer tab_status slowly, so a value change waits behind it."""
        if action == "tab_status":
            await asyncio.sleep(0.2)
        return await handle(action, args)

    tablet.async_call = slow_status
    tablet.nonce = None
    session._last_knock -= sender_module.KNOCK_EVERY_S + 1
    tablet.knock()
    await asyncio.sleep(0.05)
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    await until(
        hass,
        lambda: (
            session.status == STATUS_ON_TABLET
            and session.nonce is not None
            and tablet.nonce is not None
            and all(tablet.slot(n) == 1 for n in booleans)
        ),
    )
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()
    assert tablet.refused == []
    assert all(args["auth"] for args in tablet.calls_of("tab_set"))
    assert len(tablet.calls_of("tab_pair")) == pairs
    assert tablet.secret == secret
    assert session._force_pair is False


async def test_hello_is_not_signed_without_an_api_key(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    memory_link: MemoryTabletLink,
) -> None:
    """A paired tablet reflashed without encryption gets an unsigned tab_hello.

    The connection is plain text then; a signed hello could be recorded
    and played back after a reboot (contract 6.1). Its software takes no
    API key, so no key comes, and it gets its dashboard unsigned.
    """
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert config_entry.runtime_data.assignments.secret(MAC) is not None
    assert all(args["auth"] for args in tablet.calls_of("tab_hello")[1:])
    start = len(tablet.calls)

    tablet.psk = None
    tablet.encryption_supported = False
    memory_link.async_reconnect(MAC)
    await until(
        hass,
        lambda: (
            any(name == "tab_hello" for name, _args in tablet.calls[start:])
            and session.status == STATUS_ON_TABLET
        ),
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    after = tablet.calls[start:]
    assert [args["auth"] for name, args in after if name == "tab_hello"] == [""]
    assert session.input == "needs_encryption"
    assert all(args.get("auth", "") == "" for _name, args in after)


async def test_erased_tablet_gets_nothing_until_its_key_is_back(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    memory_link: MemoryTabletLink,
) -> None:
    """A paired tablet that was erased waits for its key before anything goes.

    After the erase the ESPHome entry connects without a key for a moment,
    until ESPHome gives the tablet its key and connects again with it. In
    that moment HA sends nothing: no hello, layout, values or pairing, so
    the dashboard and live values never cross the network in plain text.
    """
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    assignments = config_entry.runtime_data.assignments
    old_secret = assignments.secret(MAC)
    assert old_secret is not None

    # Erased: no key, no secret, no layout. ESPHome connects in plain text.
    tablet.psk = None
    tablet.secret = None
    tablet.nonce = None
    tablet.active = tablet.stored = ""
    tablet.values = {}
    start = len(tablet.calls)
    memory_link.async_reconnect(MAC)
    await until(
        hass,
        lambda: session.status == STATUS_SENDING and session.input == "not_paired",
    )
    # Values change, the tablet knocks, an admin asks to set it up again:
    # still not one call.
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet.knock()
    session.request_pair()
    await asyncio.sleep(0.05)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert tablet.calls[start:] == []
    assert session.status == STATUS_SENDING
    assert session.live is None
    assert session.nonce is None

    # ESPHome gave the tablet its key and connects again with it, more than
    # a minute after the last pairing.
    session._last_pair -= 120
    tablet.psk = bytes(range(1, 33))
    memory_link.async_reconnect(MAC)
    await until(
        hass,
        lambda: session.status == STATUS_ON_TABLET and session.input == "ok",
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    names = [name for name, _args in tablet.calls[start:]]
    assert names[:3] == ["tab_hello", "tab_pair", "tab_hello"]
    assert names.index("tab_layout") > names.index("tab_pair")
    assert tablet.active == session.want.hash
    assert tablet.secret == assignments.secret(MAC) != old_secret
    assert tablet.values
    assert all(args["auth"] for args in tablet.calls_of("tab_set"))


async def test_hello_without_encryption_holds_a_paired_tablet(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    memory_link: MemoryTabletLink,
) -> None:
    """A paired tablet whose tab_hello says enc 0 gets no layout or values."""
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    await hass.async_block_till_done(wait_background_tasks=True)

    answer = tablet._on_tab_hello

    def no_key_hello(nonce: str, auth: str) -> dict:
        """Answer as a tablet without an API key: enc 0, no kid."""
        return {**answer(nonce, auth), "enc": 0, "kid": ""}

    def no_key_pair(**_args: str) -> dict:
        """Refuse a secret, as a tablet without an API key does."""
        raise LinkError("needs_encryption")

    tablet._on_tab_hello = no_key_hello
    tablet._on_tab_pair = no_key_pair
    tablet.active = tablet.stored = ""
    start = len(tablet.calls)
    memory_link.async_reconnect(MAC)
    await until(
        hass,
        lambda: (
            any(name == "tab_hello" for name, _args in tablet.calls[start:])
            and session.status == STATUS_SENDING
            and session.input == "not_paired"
        ),
    )
    await asyncio.sleep(0.05)
    await hass.async_block_till_done(wait_background_tasks=True)
    names = {name for name, _args in tablet.calls[start:]}
    assert names <= {"tab_hello", "tab_pair"}
    assert session.nonce is None
    assert session.live is None


async def test_persistent_hash_error_does_not_loop(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A tablet that answers every tab_set with "hash" is greeted twice more.

    After that the status is failed/hash with a retry, not an endless run
    of handshakes.
    """
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    real = tablet.async_call

    async def broken(action: str, args: dict) -> dict | None:
        """Refuse every tab_set as for an unknown layout."""
        if action == "tab_set":
            tablet.calls.append((action, dict(args)))
            raise LinkError("hash")
        return await real(action, args)

    tablet.async_call = broken
    hellos = len(tablet.calls_of("tab_hello"))
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    await until(hass, lambda: session.status == STATUS_FAILED)
    for _ in range(20):
        await asyncio.sleep(0.02)
        await hass.async_block_till_done()
    assert (session.status, session.reason, session.retry) == (
        STATUS_FAILED,
        "hash",
        True,
    )
    assert len(tablet.calls_of("tab_hello")) - hellos == 2
    assert session._cancel_retry is not None


async def test_signed_call_waiting_when_the_session_ends_is_not_sent(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A signed call queued behind another is dropped when the session ends.

    Sent without a session it would go out unsigned, the tablet would
    refuse it, and that refusal would look like a wrong secret: a new
    pairing nobody needs.
    """
    tablet = make_tablet()
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(light_card()))
    session = await on_tablet(hass, config_entry)
    assert session.nonce is not None and session.enc
    assert config_entry.runtime_data.assignments.secret(MAC) is not None
    pairs = len(tablet.calls_of("tab_pair"))
    acks = len(tablet.calls_of("tab_ack"))
    body = "7|1|"
    async with session._lock:
        waiting = hass.async_create_task(
            session._call("tab_ack", {"counter": 7, "ok": True, "code": ""}, body=body)
        )
        await asyncio.sleep(0)
        session.drop_session()
    with pytest.raises(LinkError) as caught:
        await waiting
    assert caught.value.code == "no_session"
    assert len(tablet.calls_of("tab_ack")) == acks
    assert tablet.refused == []
    await hass.async_block_till_done()
    assert len(tablet.calls_of("tab_pair")) == pairs
    assert session._force_pair is False
