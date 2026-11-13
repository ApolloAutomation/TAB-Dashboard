"""Tests for approving new tablets (design 10.7).

Any ESPHome device can say it is a TAB-1: the model comes from its own
firmware. So a tablet seen for the first time gets nothing until an admin
picks its first dashboard: no dashboard, no pairing, no taps.
"""

import hashlib
import json
from datetime import timedelta
from typing import Any

import pytest
from homeassistant.auth.models import User
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.apollo_tab import protocol as tp
from custom_components.apollo_tab.assignments import (
    APPROVAL_NEEDED,
    STORE_KEY,
    ApprovalNeeded,
)
from custom_components.apollo_tab.const import DOMAIN
from custom_components.apollo_tab.diagnostics import async_get_config_entry_diagnostics
from custom_components.apollo_tab.sender import (
    STATUS_NEW,
    STATUS_NO_DASHBOARD,
    STATUS_ON_TABLET,
    new_tablet_issue_id,
)
from custom_components.apollo_tab.tablet_link import MemoryTabletLink
from custom_components.apollo_tab.tablets import async_get_tablets
from custom_components.apollo_tab.websocket import NOT_APPROVED

from .conftest import (
    AddTablet,
    MakeTablet,
    SaveTabDashboard,
    setup_integration,
    until,
)
from .test_tablet_input import LIGHT_CARD, LOCK_CARD, tab_config, widget_for

REAL = "aa:bb:cc:dd:ee:01"
FAKE = "11:22:33:44:55:66"
FAKE_KEY = bytes(range(100, 132))  # the fake device's own ESPHome API key
NEW = "aa:bb:cc:dd:ee:02"
NEW_SELECT = "select.porch_tablet_dashboard"


@pytest.fixture
async def family_user(hass: HomeAssistant) -> User:
    """Return a user who is not an admin but may control entities."""
    return await hass.auth.async_create_user("Family", group_ids=["system-users"])


@pytest.fixture
async def addon_user(hass: HomeAssistant) -> User:
    """Return the Supervisor's user, which add-ons call Home Assistant as.

    Node-RED, AppDaemon and other add-ons act as this user. It is
    system-generated and an admin, so HA's own admin checks let it through.
    """
    user = await hass.auth.async_create_system_user(
        "Supervisor", group_ids=["system-admin"]
    )
    assert user.is_admin
    assert user.system_generated
    return user


@pytest.fixture
async def inactive_admin(hass: HomeAssistant) -> User:
    """Return an admin whose account was turned off."""
    user = await hass.auth.async_create_user("Old admin", group_ids=["system-admin"])
    await hass.auth.async_deactivate_user(user)
    return user


def context_of(who: str, users: dict[str, User]) -> Context | None:
    """Return the context a change comes with: None for an automation."""
    return None if who == "automation" else Context(user_id=users[who].id)


def issue(hass: HomeAssistant, issue_id: str) -> ir.IssueEntry | None:
    """Return one of the integration's repair issues, or None."""
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id)


def issue_of(hass: HomeAssistant, mac: str) -> str:
    """Return the repair issue id of a waiting tablet: its random device id."""
    return new_tablet_issue_id(async_get_tablets(hass)[mac].id)


def our_issues(hass: HomeAssistant) -> list[str]:
    """Return the ids of the integration's repair issues, sorted."""
    return sorted(
        issue_id for domain, issue_id in ir.async_get(hass).issues if domain == DOMAIN
    )


async def command(client: Any, message: dict) -> dict:
    """Send one websocket command and return the response."""
    await client.send_json_auto_id(message)
    return await client.receive_json()


async def approved_and_new(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save: SaveTabDashboard,
) -> tuple[Any, Any]:
    """Set up an approved Kitchen tablet on Home and a new Porch tablet.

    There are two dashboards, Home (tab-home) and Bedroom (tab-bed).
    Returns the two simulated tablets.
    """
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    kitchen = make_tablet(mac=REAL.upper())
    porch = make_tablet(mac=NEW.upper(), name="Porch Tablet", approved=False)
    await setup_integration(hass, entry)
    await save("tab-home", tab_config(LIGHT_CARD, title="Home"), title="Home")
    await save("tab-bed", tab_config(LIGHT_CARD, title="Bedroom"), title="Bedroom")
    sender = entry.runtime_data.sender
    await until(hass, lambda: sender.sessions[REAL].status == STATUS_ON_TABLET)
    await hass.async_block_till_done(wait_background_tasks=True)
    return kitchen, porch


# ------------------------------------------------------------------ the probe


async def test_self_declared_tablet_gets_nothing_until_an_admin_picks(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """A device that only claims to be a TAB-1 cannot unlock the door.

    It plays a device adopted for something else (its own MAC and API key,
    which its firmware knows) that later reports the TAB-1 project. Without
    an admin it gets no dashboard, no pairing secret and no say. After an
    admin picks its dashboard in the panel it works like any tablet.
    """
    unlock = async_mock_service(hass, "lock", "unlock")
    hass.states.async_set("lock.front_door", "locked", {"friendly_name": "Door"})
    real = make_tablet(mac=REAL.upper())
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LOCK_CARD))
    sender = config_entry.runtime_data.sender
    assignments = config_entry.runtime_data.assignments
    real_session = sender.sessions[REAL]
    await until(hass, lambda: real_session.status == STATUS_ON_TABLET)
    assert our_issues(hass) == []

    fake = make_tablet(
        mac=FAKE.upper(), name="Garage Sensor", psk=FAKE_KEY, approved=False
    )
    await until(hass, lambda: FAKE in sender.sessions)
    await hass.async_block_till_done(wait_background_tasks=True)
    session = sender.sessions[FAKE]

    assert session.status == STATUS_NEW
    assert not session.approved
    assert session.dashboard is None
    assert assignments.dashboard(FAKE) is None
    assert assignments.secret(FAKE) is None
    assert assignments.get(FAKE)["secret"] is None
    assert not session.paired
    assert not fake.paired
    assert fake.calls == []
    assert sender.tablet_json(session)["approved"] is False
    assert sender.tablet_json(session)["input"] == "not_paired"

    # The admin is told, by name only.
    found = issue(hass, issue_of(hass, FAKE))
    assert found is not None
    assert found.translation_key == "new_tablet"
    assert found.translation_placeholders == {"name": "Garage Sensor"}
    assert found.severity == ir.IssueSeverity.WARNING
    assert not found.is_fixable
    assert found.is_persistent is False
    assert our_issues(hass) == [issue_of(hass, FAKE)]

    # Its knock is not answered and its taps run nothing, signed with any
    # key, on the real tablet's layout and session.
    fake.knock()
    widget = widget_for(real_session, "apollo/lock", "unlock")
    fake.tap(widget, confirmed=True, layout=real.active)
    fake.tap(widget, confirmed=True, layout=real.active, secret=FAKE_KEY)
    fake.tap(
        widget,
        confirmed=True,
        layout=real.active,
        secret=real.secret,
        nonce=real.nonce,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert fake.calls == []
    assert fake.acks == []
    assert unlock == []
    assert session.dropped["not_approved"] == 3
    assert real.acks == []

    # An admin picks its dashboard in the panel: now it is a tablet.
    client = await hass_ws_client(hass)
    response = await command(
        client,
        {
            "type": "apollo_tab/tablet/assign",
            "mac": FAKE,
            "url_path": "tab-home",
            "approve": True,
        },
    )
    assert response["success"], response
    await until(
        hass,
        lambda: session.status == STATUS_ON_TABLET and fake.active != "",
    )
    assert session.approved
    assert fake.paired
    assert fake.secret == assignments.secret(FAKE)
    assert assignments.entry_id(FAKE) == session.entry_id
    assert issue(hass, issue_of(hass, FAKE)) is None

    widget = widget_for(session, "apollo/lock", "unlock")
    fake.tap(widget, confirmed=True)
    await until(hass, lambda: len(fake.acks) == 1)
    assert fake.acks[-1][1:] == (True, "")
    assert len(unlock) == 1
    assert unlock[0].data == {"entity_id": "lock.front_door"}


# ------------------------------------------------------------- who approves


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("select_option", {"option": "Home"}),
        ("select_next", {}),
        ("select_previous", {}),
        ("select_first", {}),
        ("select_last", {}),
    ],
)
@pytest.mark.parametrize("who", ["automation", "family", "add-on", "inactive admin"])
async def test_select_cannot_approve_without_an_admin(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    family_user: User,
    addon_user: User,
    inactive_admin: User,
    service: str,
    data: dict,
    who: str,
) -> None:
    """No way of changing the select approves a tablet, but an admin's.

    An add-on calls as the Supervisor's user, an admin made by the system:
    it is an automation, not an admin who looked at the tablet.
    """
    _kitchen, porch = await approved_and_new(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    users = {
        "family": family_user,
        "add-on": addon_user,
        "inactive admin": inactive_admin,
    }
    context = context_of(who, users)
    with pytest.raises(ApprovalNeeded) as err:
        await hass.services.async_call(
            "select",
            service,
            {"entity_id": NEW_SELECT, **data},
            blocking=True,
            context=context,
        )
    assert str(err.value) == APPROVAL_NEEDED
    await hass.async_block_till_done(wait_background_tasks=True)
    assignments = config_entry.runtime_data.assignments
    assert not assignments.approved(NEW)
    assert assignments.get(NEW)["dashboard"] is None
    assert porch.calls == []
    assert hass.states.get(NEW_SELECT).state == "unknown"


@pytest.mark.parametrize("who", ["automation", "family", "add-on", "inactive admin"])
async def test_show_dashboard_cannot_approve_without_an_admin(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    family_user: User,
    addon_user: User,
    inactive_admin: User,
    who: str,
) -> None:
    """The action refuses a new tablet unless an admin user calls it."""
    _kitchen, porch = await approved_and_new(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    users = {
        "family": family_user,
        "add-on": addon_user,
        "inactive admin": inactive_admin,
    }
    context = context_of(who, users)
    with pytest.raises(ApprovalNeeded) as err:
        await hass.services.async_call(
            DOMAIN,
            "show_dashboard",
            {"device_id": async_get_tablets(hass)[NEW].id, "dashboard": "tab-bed"},
            blocking=True,
            context=context,
        )
    assert str(err.value) == APPROVAL_NEEDED
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not config_entry.runtime_data.assignments.approved(NEW)
    assert porch.calls == []


async def test_admin_approves_with_the_select_then_automations_switch(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_admin_user: User,
) -> None:
    """An admin's pick approves; after that an automation may switch it."""
    _kitchen, porch = await approved_and_new(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    sender = config_entry.runtime_data.sender
    session = sender.sessions[NEW]
    state = hass.states.get(NEW_SELECT)
    assert state.state == "unknown"
    assert state.attributes["options"] == ["Bedroom", "Home"]
    assert state.attributes["dashboard_id"] is None

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": NEW_SELECT, "option": "Bedroom"},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert porch.paired
    assert hass.states.get(NEW_SELECT).state == "Bedroom"
    assert issue(hass, issue_of(hass, NEW)) is None

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": NEW_SELECT, "option": "Home"},
        blocking=True,
    )
    await until(
        hass,
        lambda: (
            session.status == STATUS_ON_TABLET and session.want.url_path == "tab-home"
        ),
    )
    assert hass.states.get(NEW_SELECT).state == "Home"


async def test_admin_approves_with_show_dashboard(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_admin_user: User,
    family_user: User,
    addon_user: User,
) -> None:
    """The action approves for an admin; then it follows the usual rule."""
    _kitchen, porch = await approved_and_new(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    device_id = async_get_tablets(hass)[NEW].id
    session = config_entry.runtime_data.sender.sessions[NEW]
    await hass.services.async_call(
        DOMAIN,
        "show_dashboard",
        {"device_id": device_id, "dashboard": "tab-bed"},
        blocking=True,
        context=Context(user_id=hass_admin_user.id),
    )
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert session.dashboard == "tab-bed"
    assert porch.paired

    # Approved: automations switch it, non-admin users still cannot.
    await hass.services.async_call(
        DOMAIN,
        "show_dashboard",
        {"device_id": device_id, "dashboard": "tab-home"},
        blocking=True,
    )
    assert session.dashboard == "tab-home"
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "show_dashboard",
            {"device_id": device_id, "dashboard": "tab-bed"},
            blocking=True,
            context=Context(user_id=family_user.id),
        )
    assert session.dashboard == "tab-home"
    # An add-on switches it like any other automation.
    await hass.services.async_call(
        DOMAIN,
        "show_dashboard",
        {"device_id": device_id, "dashboard": "tab-bed"},
        blocking=True,
        context=Context(user_id=addon_user.id),
    )
    assert session.dashboard == "tab-bed"


async def test_panel_cannot_pair_a_new_tablet(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """The panel's Set up again is refused until the tablet has a dashboard."""
    _kitchen, porch = await approved_and_new(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    client = await hass_ws_client(hass)
    response = await command(client, {"type": "apollo_tab/tablet/pair", "mac": NEW})
    assert not response["success"]
    assert response["error"]["code"] == "not_approved"
    assert response["error"]["message"] == NOT_APPROVED
    await hass.async_block_till_done(wait_background_tasks=True)
    assert porch.calls == []


# ------------------------------------------------------------- re-adoption


async def test_adopted_again_under_another_entry_needs_approval_again(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    make_tablet: MakeTablet,
    add_tablet: AddTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """The same MAC under another ESPHome entry starts over as new.

    Its secret is dropped and nothing is sent; what it showed stays only as
    the panel's suggestion.
    """
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet(mac=REAL.upper())
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD), title="Home")
    await save_tab_dashboard("tab-bed", tab_config(LIGHT_CARD), title="Bedroom")
    sender = config_entry.runtime_data.sender
    assignments = config_entry.runtime_data.assignments
    await until(hass, lambda: sender.sessions[REAL].status == STATUS_ON_TABLET)
    client = await hass_ws_client(hass)
    response = await command(
        client,
        {"type": "apollo_tab/tablet/assign", "mac": REAL, "url_path": "tab-bed"},
    )
    assert response["success"], response
    await until(
        hass,
        lambda: (
            sender.sessions[REAL].status == STATUS_ON_TABLET
            and sender.sessions[REAL].want.url_path == "tab-bed"
        ),
    )
    old_secret = assignments.secret(REAL)
    assert old_secret is not None

    # The old ESPHome entry is gone and the device is adopted again.
    device_registry.async_remove_device(async_get_tablets(hass)[REAL].id)
    await hass.async_block_till_done()
    calls = len(tablet.calls)
    other = MockConfigEntry(domain="esphome", title="Kitchen Tablet")
    other.add_to_hass(hass)
    add_tablet(other, mac=REAL.upper())
    await until(hass, lambda: REAL in sender.sessions)
    await hass.async_block_till_done(wait_background_tasks=True)
    session = sender.sessions[REAL]

    assert session.status == STATUS_NEW
    assert not assignments.approved(REAL)
    assert assignments.secret(REAL) is None
    assert assignments.get(REAL)["secret"] is None
    assert assignments.get(REAL)["kid"] is None
    assert assignments.get(REAL)["entry_id"] is None
    assert assignments.dashboard(REAL) is None
    assert assignments.suggested(REAL) == "tab-bed"
    assert sender.tablet_json(session)["suggested"] == "tab-bed"
    assert len(tablet.calls) == calls
    assert issue(hass, issue_of(hass, REAL)) is not None
    assert assignments.shown_on("tab-bed") == []

    # An admin picks again: a new pairing secret under the new entry.
    response = await command(
        client,
        {
            "type": "apollo_tab/tablet/assign",
            "mac": REAL,
            "url_path": "tab-bed",
            "approve": True,
        },
    )
    assert response["success"], response
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert assignments.entry_id(REAL) == other.entry_id
    assert assignments.secret(REAL) not in (None, old_secret)
    assert tablet.secret == assignments.secret(REAL)
    assert sender.tablet_json(session)["suggested"] is None
    assert issue(hass, issue_of(hass, REAL)) is None


async def test_approved_tablet_pairs_again_after_an_esphome_reload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    memory_link: MemoryTabletLink,
    make_tablet: MakeTablet,
    add_tablet: AddTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Under the same ESPHome entry an approved tablet needs no admin.

    Not after a reload that lost its pairing, and not after its device was
    removed and registered again by the same entry.
    """
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet(mac=REAL.upper())
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD))
    sender = config_entry.runtime_data.sender
    session = sender.sessions[REAL]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert len(tablet.calls_of("tab_pair")) == 1

    # The tablet was flashed again: no secret, no session.
    session._last_pair -= 120
    tablet.secret = None
    tablet.nonce = None
    memory_link.async_reconnect(REAL)
    await until(
        hass,
        lambda: (
            len(tablet.calls_of("tab_pair")) == 2 and session.status == STATUS_ON_TABLET
        ),
    )
    assert tablet.secret == config_entry.runtime_data.assignments.secret(REAL)
    assert our_issues(hass) == []

    # Removed and registered again by the same ESPHome entry.
    device = async_get_tablets(hass)[REAL]
    esphome = hass.config_entries.async_get_entry(device.config_entry_id)
    device_registry.async_remove_device(device.id)
    await hass.async_block_till_done()
    add_tablet(esphome, mac=REAL.upper())
    await until(
        hass,
        lambda: (
            REAL in sender.sessions and sender.sessions[REAL].status == STATUS_ON_TABLET
        ),
    )
    assert sender.sessions[REAL].approved
    assert our_issues(hass) == []


# ------------------------------------------------------------- knocks, taps


async def test_knocks_and_taps_from_a_new_tablet_do_nothing(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    memory_link: MemoryTabletLink,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new tablet is not greeted, paired or answered, whatever it sends.

    A knock does not even make Home Assistant look at its connection again.
    """
    unlock = async_mock_service(hass, "lock", "unlock")
    toggle = async_mock_service(hass, "light", "toggle")
    hass.states.async_set("lock.front_door", "locked", {"friendly_name": "Door"})
    porch = make_tablet(mac=NEW.upper(), name="Porch Tablet", approved=False)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LOCK_CARD, LIGHT_CARD))
    sender = config_entry.runtime_data.sender
    session = sender.sessions[NEW]
    await hass.async_block_till_done(wait_background_tasks=True)
    rechecks: list[str] = []
    monkeypatch.setattr(memory_link, "async_recheck", rechecks.append)

    for boot in (1, 2, 3):
        porch.knock(boot=boot)
        await hass.async_block_till_done(wait_background_tasks=True)
    for widget in range(1, 6):
        porch.tap(widget, confirmed=True)
        porch.tap(widget, event="h")
    session.request_pair()
    session.kick()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert porch.calls == []
    assert porch.acks == []
    assert rechecks == []
    assert unlock == []
    assert toggle == []
    assert session.dropped["not_approved"] == 10
    assert session.status == STATUS_NEW
    assert session.input == "not_paired"
    assert sender.unknown_inputs == 0


async def test_new_wins_over_every_other_status(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    memory_link: MemoryTabletLink,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Offline, without the engine or without dashboards, it is "new"."""
    porch = make_tablet(mac=NEW.upper(), name="Porch Tablet", approved=False)
    porch.connected = False
    await setup_integration(hass, config_entry)
    sender = config_entry.runtime_data.sender
    session = sender.sessions[NEW]
    await hass.async_block_till_done(wait_background_tasks=True)
    assert session.status == STATUS_NEW
    assert session.reason == ""
    assert session.retry is False

    porch.connected = True
    porch.has_engine = False
    memory_link.async_refresh(NEW)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert session.status == STATUS_NEW
    assert sender.tablet_json(session)["status"] == STATUS_NEW

    porch.has_engine = True
    memory_link.async_refresh(NEW)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert session.status == STATUS_NEW
    assert porch.calls == []


# ------------------------------------------------------------ repair issues


async def test_repair_issue_follows_the_tablet(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """One issue per new tablet: renamed with it, gone when it is approved.

    It also goes when the device leaves Home Assistant or the integration
    unloads, and comes back on the next start while the tablet waits.
    """
    make_tablet(mac=NEW.upper(), name="Porch Tablet", approved=False)
    make_tablet(mac=FAKE.upper(), name="Garage Sensor", approved=False)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD))
    await hass.async_block_till_done()
    porch_issue = issue_of(hass, NEW)
    assert our_issues(hass) == sorted([issue_of(hass, FAKE), porch_issue])
    assert issue(hass, porch_issue).translation_placeholders == {"name": "Porch Tablet"}

    # Renamed by the user: the issue says the new name.
    device = async_get_tablets(hass)[NEW]
    device_registry.async_update_device(device.id, name_by_user="Front Door")
    await until(
        hass,
        lambda: (
            issue(hass, porch_issue).translation_placeholders == {"name": "Front Door"}
        ),
    )

    # Unload: no issues. Load: back for the tablets that still wait.
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert our_issues(hass) == []
    await setup_integration(hass, config_entry)
    await hass.async_block_till_done()
    assert our_issues(hass) == sorted([issue_of(hass, FAKE), issue_of(hass, NEW)])

    # The device leaves Home Assistant.
    device_registry.async_remove_device(async_get_tablets(hass)[FAKE].id)
    await until(hass, lambda: our_issues(hass) == [issue_of(hass, NEW)])

    # Approved in the panel.
    client = await hass_ws_client(hass)
    response = await command(
        client,
        {
            "type": "apollo_tab/tablet/assign",
            "mac": NEW,
            "url_path": "tab-home",
            "approve": True,
        },
    )
    assert response["success"], response
    await until(hass, lambda: our_issues(hass) == [])


async def test_no_repair_issue_for_a_tablet_whose_device_is_disabled(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    make_tablet: MakeTablet,
) -> None:
    """A waiting tablet whose device someone disabled raises no issue.

    It was turned off on purpose, so it waits for nobody. It stays new; once
    its device is enabled again the issue comes back. A tablet disabled
    while the integration was off gets none at start either.
    """
    make_tablet(mac=NEW.upper(), name="Porch Tablet", approved=False)
    await setup_integration(hass, config_entry)
    porch_issue = issue_of(hass, NEW)
    assert our_issues(hass) == [porch_issue]

    device_id = async_get_tablets(hass)[NEW].id
    device_registry.async_update_device(
        device_id, disabled_by=dr.DeviceEntryDisabler.USER
    )
    await until(hass, lambda: our_issues(hass) == [])
    sender = config_entry.runtime_data.sender
    assert sender.sessions[NEW].status == STATUS_NEW
    assert not config_entry.runtime_data.assignments.approved(NEW)

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    await setup_integration(hass, config_entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert NEW in config_entry.runtime_data.sender.sessions
    assert our_issues(hass) == []

    device_registry.async_update_device(device_id, disabled_by=None)
    await until(hass, lambda: our_issues(hass) == [porch_issue])


async def test_stale_issues_are_removed_at_start(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
) -> None:
    """An issue of a tablet that left while the integration was off goes.

    So do the waiting tablet's issues named the old ways, after its full MAC
    and after a hash of it: its issue is made again under its device id.
    """
    hashed = hashlib.sha256(f"{DOMAIN}|{tp.mac_hex(NEW)}".encode()).hexdigest()
    for issue_id in (
        "new_tablet_0123456789ab",
        f"new_tablet_{tp.mac_hex(NEW)}",
        f"new_tablet_{hashed[:12]}",
    ):
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="new_tablet",
            translation_placeholders={"name": "Gone"},
        )
    make_tablet(mac=NEW.upper(), name="Porch Tablet", approved=False)
    await setup_integration(hass, config_entry)
    await hass.async_block_till_done()
    assert our_issues(hass) == [issue_of(hass, NEW)]
    assert issue_of(hass, NEW) == f"new_tablet_{async_get_tablets(hass)[NEW].id}"


async def test_device_that_becomes_a_tablet_waits(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    memory_link: MemoryTabletLink,
    add_tablet: AddTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A device whose model changes to TAB-1 is a new tablet, with its issue."""
    device = add_tablet(
        mac=FAKE.upper(), name="Garage Sensor", model="MSR-2", approved=False
    )
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD))
    assignments = config_entry.runtime_data.assignments
    assert assignments.get(FAKE) is None
    assert our_issues(hass) == []

    device_registry.async_update_device(device.id, model="TAB-1")
    sender = config_entry.runtime_data.sender
    await until(hass, lambda: FAKE in sender.sessions)
    await hass.async_block_till_done()
    assert assignments.get(FAKE)["approved"] is False
    assert assignments.dashboard(FAKE) is None
    assert sender.sessions[FAKE].status == STATUS_NEW
    assert our_issues(hass) == [issue_of(hass, FAKE)]
    state = hass.states.get("select.garage_sensor_dashboard")
    assert state is not None
    assert state.state == "unknown"


# ------------------------------------------------- dashboards and removal


async def test_new_tablets_get_no_dashboard_made_later_or_moved(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """The first dashboard and a deleted dashboard's tablets: approved only."""
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    make_tablet(mac=REAL.upper())
    porch = make_tablet(mac=NEW.upper(), name="Porch Tablet", approved=False)
    await setup_integration(hass, config_entry)
    sender = config_entry.runtime_data.sender
    assignments = config_entry.runtime_data.assignments
    await until(hass, lambda: sender.sessions[REAL].status == STATUS_NO_DASHBOARD)

    # The first dashboard made later goes to the approved tablet only.
    await save_tab_dashboard("tab-a", tab_config(LIGHT_CARD), title="A")
    await save_tab_dashboard("tab-b", tab_config(LIGHT_CARD), title="B")
    await until(hass, lambda: sender.sessions[REAL].status == STATUS_ON_TABLET)
    assert assignments.dashboard(REAL) == "tab-a"
    assert assignments.get(NEW)["dashboard"] is None
    assert sender.sessions[NEW].status == STATUS_NEW

    # Counts and "shown on" leave the new tablet out.
    client = await hass_ws_client(hass)
    response = await command(client, {"type": "apollo_tab/dashboards"})
    assert response["success"], response
    shown = {
        item["url_path"]: item["shown_on"] for item in response["result"]["dashboards"]
    }
    assert shown == {"tab-a": [REAL], "tab-b": []}
    assert response["result"]["tablets"] == 1
    assert assignments.shown_on("tab-a") == [REAL]

    # Deleting a dashboard moves the approved tablet only.
    await client.send_json_auto_id({"type": "lovelace/dashboards/list"})
    items = (await client.receive_json())["result"]
    dashboard_id = next(item["id"] for item in items if item["url_path"] == "tab-a")
    response = await command(
        client, {"type": "lovelace/dashboards/delete", "dashboard_id": dashboard_id}
    )
    assert response["success"], response
    await until(hass, lambda: assignments.dashboard(REAL) == "tab-b")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert assignments.get(NEW)["dashboard"] is None
    assert porch.calls == []


async def test_removing_the_integration_leaves_new_tablets_alone(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Only approved tablets are blanked; the issues go with the integration."""
    kitchen, porch = await approved_and_new(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    assert our_issues(hass) == [issue_of(hass, NEW)]
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert len(kitchen.calls_of("tab_clear")) == 1
    assert porch.calls == []
    assert our_issues(hass) == []


async def test_removal_leaves_a_tablet_approved_under_another_entry_alone(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_storage: dict[str, Any],
) -> None:
    """Removing the integration clears a tablet only under its approved entry.

    The tablet was approved under one ESPHome entry, and its device moved to
    another while the integration was not loaded, so its stored record still
    says approved, with a secret. The device now belongs to an entry nobody
    approved: Home Assistant never talks to it, also not to clear it.
    """
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet(mac=REAL.upper())
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD), title="Home")
    session = config_entry.runtime_data.sender.sessions[REAL]
    await until(hass, lambda: session.status == STATUS_ON_TABLET and tablet.paired)
    old_entry = session.entry_id
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    record = hass_storage[STORE_KEY]["data"]["tablets"][REAL]
    assert record["approved"] is True
    assert record["entry_id"] == old_entry
    assert record["secret"] == tablet.secret.hex()

    other = MockConfigEntry(domain="esphome", title="Kitchen Tablet")
    other.add_to_hass(hass)
    device_registry.async_update_device(
        async_get_tablets(hass)[REAL].id, new_config_entry_id=other.entry_id
    )
    await hass.async_block_till_done()
    assert async_get_tablets(hass)[REAL].config_entry_id == other.entry_id
    calls = len(tablet.calls)
    shown = tablet.active
    assert shown

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert len(tablet.calls) == calls
    assert tablet.calls_of("tab_clear") == []
    assert tablet.active == shown
    assert STORE_KEY not in hass_storage


async def test_diagnostics_say_which_tablets_wait(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Each tablet shows whether an admin approved it."""
    await approved_and_new(hass, config_entry, make_tablet, save_tab_dashboard)
    result = await async_get_config_entry_diagnostics(hass, config_entry)
    by_name = {tablet["name"]: tablet for tablet in result["tablets"]}
    assert by_name["Kitchen Tablet"]["approved"] is True
    assert by_name["Porch Tablet"]["approved"] is False
    assert by_name["Porch Tablet"]["status"] == STATUS_NEW
    assert by_name["Porch Tablet"]["dashboard"] is None
    assert by_name["Porch Tablet"]["paired"] is False


# ------------------------------------------ suggestions and lost approvals


async def delete_dashboard(client: Any, url_path: str) -> None:
    """Delete a storage dashboard by url_path."""
    items = (await command(client, {"type": "lovelace/dashboards/list"}))["result"]
    dashboard_id = next(item["id"] for item in items if item["url_path"] == url_path)
    response = await command(
        client, {"type": "lovelace/dashboards/delete", "dashboard_id": dashboard_id}
    )
    assert response["success"], response


def suggest(
    hass: HomeAssistant, entry: MockConfigEntry, mac: str, url_path: str
) -> None:
    """Make a waiting tablet suggest a dashboard, as after it was adopted again.

    It was approved on url_path under an ESPHome entry it no longer has.
    """
    assignments = entry.runtime_data.assignments
    assert assignments.async_approve(mac, url_path, "an-old-esphome-entry")
    assignments.async_see({mac: async_get_tablets(hass)[mac].config_entry_id})
    assert not assignments.approved(mac)
    assert assignments.suggested(mac) == url_path


async def test_delete_does_not_move_a_waiting_tablets_suggestion(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A deleted dashboard moves approved tablets only.

    A waiting tablet that suggested it loses the suggestion. It does not get
    the dashboard the approved tablets move to: it never showed that one.
    """
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    make_tablet(mac=REAL.upper())
    porch = make_tablet(mac=NEW.upper(), name="Porch Tablet", approved=False)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD), title="Home")
    await save_tab_dashboard("tab-zed", tab_config(LIGHT_CARD), title="Zed")
    sender = config_entry.runtime_data.sender
    assignments = config_entry.runtime_data.assignments
    await until(hass, lambda: sender.sessions[REAL].status == STATUS_ON_TABLET)
    assert assignments.dashboard(REAL) == "tab-home"
    suggest(hass, config_entry, NEW, "tab-home")

    client = await hass_ws_client(hass)
    await delete_dashboard(client, "tab-home")
    await until(hass, lambda: assignments.dashboard(REAL) == "tab-zed")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert assignments.get(NEW)["dashboard"] is None
    assert assignments.suggested(NEW) is None
    assert not assignments.approved(NEW)
    assert porch.calls == []


async def test_suggestion_does_not_come_back_with_a_new_dashboard_of_that_name(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Deleted while only a waiting tablet named it, then made again.

    The new dashboard has the old url_path but is not what the tablet
    showed, so its list does not mark it "shown before".
    """
    porch = make_tablet(mac=NEW.upper(), name="Porch Tablet", approved=False)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD), title="Home")
    data = config_entry.runtime_data
    suggest(hass, config_entry, NEW, "tab-home")

    client = await hass_ws_client(hass)
    await delete_dashboard(client, "tab-home")
    await until(hass, lambda: data.assignments.get(NEW)["dashboard"] is None)
    response = await command(
        client,
        {
            "type": "lovelace/dashboards/create",
            "url_path": "tab-home",
            "title": "Other",
            "mode": "storage",
        },
    )
    assert response["success"], response
    response = await command(
        client,
        {
            "type": "lovelace/config/save",
            "url_path": "tab-home",
            "config": tab_config(LIGHT_CARD),
        },
    )
    assert response["success"], response
    await until(hass, lambda: "tab-home" in data.manager.layouts)
    assert data.assignments.suggested(NEW) is None
    response = await command(client, {"type": "apollo_tab/tablets"})
    assert response["result"]["tablets"][0]["suggested"] is None
    assert porch.calls == []


async def test_suggestion_deleted_while_home_assistant_was_off_is_dropped(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_storage: dict[str, Any],
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """At start a waiting tablet's suggestion of a dashboard that is gone goes."""
    hass_storage[STORE_KEY] = {
        "version": 1,
        "key": STORE_KEY,
        "data": {
            "tablets": {
                NEW: {
                    "dashboard": "tab-gone",
                    "secret": None,
                    "kid": None,
                    "approved": False,
                    "entry_id": None,
                }
            }
        },
    }
    porch = make_tablet(mac=NEW.upper(), name="Porch Tablet", approved=False)
    await setup_integration(hass, config_entry)
    assignments = config_entry.runtime_data.assignments
    await until(hass, lambda: assignments.get(NEW)["dashboard"] is None)
    await save_tab_dashboard("tab-gone", tab_config(LIGHT_CARD), title="New one")
    assert assignments.suggested(NEW) is None
    assert porch.calls == []


async def test_suggestion_that_cannot_be_read_is_no_choice_and_goes_when_deleted(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A waiting tablet's suggestion is offered only while it can be read.

    While it cannot be read it is no choice anywhere (only an approved
    tablet keeps a broken dashboard's name). It comes back once it can be
    read again, and goes for good when it is deleted.
    """
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.exceptions import HomeAssistantError

    porch = make_tablet(mac=NEW.upper(), name="Porch Tablet", approved=False)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-a", tab_config(LIGHT_CARD), title="Alpha")
    await save_tab_dashboard("tab-b", tab_config(LIGHT_CARD), title="Beta")
    data = config_entry.runtime_data
    suggest(hass, config_entry, NEW, "tab-a")

    async def broken(force: bool) -> dict:
        """Act like a YAML file with an error."""
        raise HomeAssistantError("bad")

    dashboard = hass.data[LOVELACE_DATA].dashboards["tab-a"]
    readable = dashboard.async_load
    monkeypatch.setattr(dashboard, "async_load", broken)
    hass.bus.async_fire("lovelace_updated", {"url_path": "tab-a"})
    await until(hass, lambda: "tab-a" not in data.manager.layouts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert data.assignments.suggested(NEW) is None
    assert data.assignments.get(NEW)["dashboard"] == "tab-a"
    assert data.assignments.unreadable == set()
    assert hass.states.get(NEW_SELECT).attributes["options"] == ["Beta"]

    monkeypatch.setattr(dashboard, "async_load", readable)
    hass.bus.async_fire("lovelace_updated", {"url_path": "tab-a"})
    await until(hass, lambda: data.assignments.suggested(NEW) == "tab-a")

    monkeypatch.setattr(dashboard, "async_load", broken)
    hass.bus.async_fire("lovelace_updated", {"url_path": "tab-a"})
    await until(hass, lambda: "tab-a" not in data.manager.layouts)
    client = await hass_ws_client(hass)
    await delete_dashboard(client, "tab-a")
    await until(hass, lambda: data.assignments.get(NEW)["dashboard"] is None)
    assert porch.calls == []


async def test_secret_stored_before_approval_is_never_used(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_storage: dict[str, Any],
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Approving drops a secret stored before; the tablet pairs with a new one.

    The tablet still holds the old secret, so keeping it would pair them
    without a new tab_pair.
    """
    old = bytes.fromhex("33" * 32)
    hass_storage[STORE_KEY] = {
        "version": 1,
        "key": STORE_KEY,
        "data": {
            "tablets": {
                REAL: {"dashboard": None, "secret": old.hex(), "kid": tp.kid(old)}
            }
        },
    }
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet(mac=REAL.upper(), approved=False)
    tablet.secret = old
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD), title="Home")
    assignments = config_entry.runtime_data.assignments
    session = config_entry.runtime_data.sender.sessions[REAL]
    assert assignments.secret(REAL) is None
    assert tablet.calls == []

    client = await hass_ws_client(hass)
    response = await command(
        client,
        {
            "type": "apollo_tab/tablet/assign",
            "mac": REAL,
            "url_path": "tab-home",
            "approve": True,
        },
    )
    assert response["success"], response
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert len(tablet.calls_of("tab_pair")) == 1
    assert tablet.secret not in (None, old)
    assert assignments.secret(REAL) == tablet.secret


async def test_tablet_moved_to_another_entry_forgets_what_it_was_trusted_with(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """The same device moved to another ESPHome entry waits again at once.

    Its session stays (same device, same MAC), but what came from trusting
    it goes: the values, the layouts its taps would run and the session.
    Nothing more is sent to it.
    """
    toggle = async_mock_service(hass, "light", "toggle")
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet(mac=REAL.upper())
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD), title="Home")
    sender = config_entry.runtime_data.sender
    session = sender.sessions[REAL]
    await until(
        hass,
        lambda: session.status == STATUS_ON_TABLET and session.live is not None,
    )
    widget = widget_for(session, "apollo/light-tile", "toggle")
    assert session.kept

    other = MockConfigEntry(domain="esphome", title="Kitchen Tablet")
    other.add_to_hass(hass)
    device_registry.async_update_device(
        async_get_tablets(hass)[REAL].id, new_config_entry_id=other.entry_id
    )
    await until(hass, lambda: session.status == STATUS_NEW and session.want is None)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert sender.sessions[REAL] is session
    assert session.kept == {}
    assert session.live is None
    assert session.nonce is None
    assert config_entry.runtime_data.assignments.secret(REAL) is None

    calls = len(tablet.calls)
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    tablet.tap(widget)
    tablet.knock()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(tablet.calls) == calls
    assert toggle == []
    assert tablet.acks == []


def mac_forms(mac: str) -> list[str]:
    """Return what an id worked out from this MAC alone could hold.

    The MAC in its forms, and the start of a SHA-256 of it (the id's form
    before, of "apollo_tab|<mac hex>", and of the bare MAC).
    """
    hexmac = tp.mac_hex(mac)
    hashes = [
        hashlib.sha256(text.encode()).hexdigest()[:8]
        for text in (f"{DOMAIN}|{hexmac}", hexmac, mac)
    ]
    return [mac, hexmac, mac.replace(":", "-"), *hashes]


async def test_diagnostics_download_holds_no_mac(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """The file Home Assistant hands out gives away no tablet's MAC.

    People paste this file into public issues. A tablet's default name ends
    in the last three bytes of its MAC (the firmware's name_add_mac_suffix),
    and that name is in the file. So nothing else in it may be worked out
    from the MAC, or trying the 2^24 possible first halves with that end
    finds it: Home Assistant adds the integration's repair issues, and a
    waiting tablet's issue id is its random device id.
    """
    assert await async_setup_component(hass, "diagnostics", {})
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    names = {
        REAL: "Apollo TAB-1 ddee01",
        "30:ed:a0:12:ee:0e": "Apollo TAB-1 12ee0e",
        FAKE: "Apollo TAB-1 445566",
    }
    waiting = ["30:ed:a0:12:ee:0e", FAKE]
    make_tablet(mac=REAL.upper(), name=names[REAL])
    for mac in waiting:
        make_tablet(mac=mac.upper(), name=names[mac], approved=False)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD), title="Home")
    await until(hass, lambda: len(our_issues(hass)) == len(waiting))
    client = await hass_client()
    response = await client.get(
        f"/api/diagnostics/config_entry/{config_entry.entry_id}"
    )
    assert response.status == 200
    text = (await response.text()).lower()
    body = json.loads(text)
    tablets = async_get_tablets(hass)
    issue_ids = sorted(item["issue_id"] for item in body["issues"])
    assert issue_ids == sorted(f"new_tablet_{tablets[mac].id}" for mac in waiting)
    # The default names are there, with the last three MAC bytes.
    assert sorted(tablet["name"] for tablet in body["data"]["tablets"]) == sorted(
        name.lower() for name in names.values()
    )
    for mac, name in names.items():
        end = name.rsplit(" ", 1)[1]
        for issue_id in issue_ids:
            # An id that held the MAC would hold its end.
            assert end not in issue_id, (issue_id, end)
            # Trying every first half finds the MAC if, and only if, the
            # id is worked out from it: try the real one.
            for form in mac_forms(mac):
                assert form not in issue_id, (issue_id, form)
        for form in mac_forms(mac)[:3]:
            assert form not in text, form


async def test_approved_again_after_a_move_in_place_stays_approved(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """A tablet moved in place to another ESPHome entry is approved for that one.

    The new approval is bound to the entry the device has now, so the next
    device registry event does not take it away again.
    """
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    make_tablet(mac=REAL.upper())
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD), title="Home")
    sender = config_entry.runtime_data.sender
    assignments = config_entry.runtime_data.assignments
    session = sender.sessions[REAL]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    other = MockConfigEntry(domain="esphome", title="Kitchen Tablet")
    other.add_to_hass(hass)
    device_id = async_get_tablets(hass)[REAL].id
    device_registry.async_update_device(device_id, new_config_entry_id=other.entry_id)
    await until(hass, lambda: session.status == STATUS_NEW)
    assert not assignments.approved(REAL)

    client = await hass_ws_client(hass)
    response = await command(
        client,
        {
            "type": "apollo_tab/tablet/assign",
            "mac": REAL,
            "url_path": "tab-home",
            "approve": True,
        },
    )
    assert response["success"], response
    await hass.async_block_till_done(wait_background_tasks=True)
    assert assignments.entry_id(REAL) == other.entry_id
    assert session.entry_id == other.entry_id
    assert session.approved

    device_registry.async_update_device(device_id, name_by_user="Kitchen wall")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert assignments.approved(REAL)
    assert assignments.entry_id(REAL) == other.entry_id
    assert session.approved
    assert session.status != STATUS_NEW
    # The pairing may wait for its next try; it then goes through.
    session._last_pair -= 61  # noqa: SLF001
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=62))
    await until(hass, lambda: session.status == STATUS_ON_TABLET)


async def test_waiting_tablets_select_shows_no_dashboard(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A tablet that waits for approval never shows a dashboard as chosen.

    What it showed before is only a suggestion in the stored record; its
    "Dashboard" control must not read it as the tablet's dashboard.
    """
    await approved_and_new(hass, config_entry, make_tablet, save_tab_dashboard)
    suggest(hass, config_entry, NEW, "tab-home")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert config_entry.runtime_data.assignments.suggested(NEW) == "tab-home"
    assert hass.states.get(NEW_SELECT).state == "unknown"
