"""Tests for the last guards around turning a tablet on (design 10.9).

Only the panel's "Turn on with this dashboard" turns a new tablet on, and
only an admin who is a person can press it. An approval holds for the
ESPHome entry it was given under, also for a call that was already waiting.
The panel also says when Home Assistant waits for an admin to confirm an
erased tablet in Repairs.
"""

import asyncio
from typing import Any

import pytest
from homeassistant.auth.models import TOKEN_TYPE_SYSTEM, User
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, Context, HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    mock_config_flow,
    mock_integration,
    mock_platform,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.apollo_tab.assignments import (
    APPROVAL_NEEDED,
    async_show_dashboard,
)
from custom_components.apollo_tab.sender import (
    ESPHOME_ERASED_STEP,
    REAUTH_ERASED,
    REAUTH_KEY,
    STATUS_NEW,
    STATUS_ON_TABLET,
)
from custom_components.apollo_tab.tablet_link import LinkError
from custom_components.apollo_tab.tablets import async_get_tablets
from custom_components.apollo_tab.websocket import NOT_APPROVED

from .conftest import MakeTablet, SaveTabDashboard, setup_integration, until
from .test_approval import (
    NEW,
    REAL,
    addon_user,  # noqa: F401 (a fixture)
    approved_and_new,
    command,
    issue,
    issue_of,
)
from .test_tablet_input import LIGHT_CARD, tab_config
from .test_tablet_shapes import check_tablet


def assign(mac: str, url_path: str, **extra: Any) -> dict[str, Any]:
    """Return the panel's assign command."""
    command = {"type": "apollo_tab/tablet/assign", "mac": mac, "url_path": url_path}
    return command | extra


async def token_of(hass: HomeAssistant, user: User) -> str:
    """Return an access token of a system-generated user, as add-ons get."""
    refresh = await hass.auth.async_create_refresh_token(
        user, token_type=TOKEN_TYPE_SYSTEM
    )
    return hass.auth.async_create_access_token(refresh)


# ------------------------------------------------- the panel's explicit approval


async def test_only_turn_on_approves_a_new_tablet(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """A plain assign is refused for a new tablet; approve true turns it on.

    An approved tablet switches with or without the flag.
    """
    _kitchen, porch = await approved_and_new(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    sender = config_entry.runtime_data.sender
    assignments = config_entry.runtime_data.assignments
    client = await hass_ws_client(hass)

    for message in (assign(NEW, "tab-home"), assign(NEW, "tab-home", approve=False)):
        response = await command(client, message)
        assert response["error"] == {"code": "not_approved", "message": NOT_APPROVED}
    # Refused before the dashboard is looked at.
    response = await command(client, assign(NEW, "nope"))
    assert response["error"]["code"] == "not_approved"
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not assignments.approved(NEW)
    assert assignments.get(NEW)["dashboard"] is None
    assert sender.sessions[NEW].status == STATUS_NEW
    assert issue(hass, issue_of(hass, NEW)) is not None
    assert porch.calls == []

    response = await command(client, assign(NEW, "tab-home", approve=True))
    assert response["success"], response
    assert response["result"]["tablet"]["approved"] is True
    await until(hass, lambda: sender.sessions[NEW].status == STATUS_ON_TABLET)
    assert issue(hass, issue_of(hass, NEW)) is None

    # Turned on: a plain assign switches it, and so does one with the flag.
    response = await command(client, assign(NEW, "tab-bed"))
    assert response["success"], response
    assert assignments.dashboard(NEW) == "tab-bed"
    response = await command(client, assign(REAL, "tab-bed", approve=True))
    assert response["success"], response
    assert assignments.dashboard(REAL) == "tab-bed"


async def test_a_switch_from_a_stale_screen_does_not_turn_a_tablet_on(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_ws_client: ClientSessionGenerator,
) -> None:
    """A turned-on tablet becomes new; a screen that still shows it on switches.

    The editor's "Show this dashboard" and a turned-on row's list send the
    plain assign. It is refused, so the tablet stays new and hears nothing.
    """
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet(mac=REAL.upper())
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD), title="Home")
    await save_tab_dashboard("tab-bed", tab_config(LIGHT_CARD), title="Bedroom")
    sender = config_entry.runtime_data.sender
    session = sender.sessions[REAL]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)

    other = MockConfigEntry(domain="esphome", title="Kitchen Tablet")
    other.add_to_hass(hass)
    device_registry.async_update_device(
        async_get_tablets(hass)[REAL].id, new_config_entry_id=other.entry_id
    )
    await until(hass, lambda: session.status == STATUS_NEW)
    await hass.async_block_till_done(wait_background_tasks=True)
    calls = len(tablet.calls)

    client = await hass_ws_client(hass)
    response = await command(client, assign(REAL, "tab-bed"))
    assert response["error"] == {"code": "not_approved", "message": NOT_APPROVED}
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not session.approved
    assert session.status == STATUS_NEW
    assert sender.tablet_json(session)["approved"] is False
    assert tablet.calls[calls:] == []


# ------------------------------------------------------------- who approves


async def test_an_add_on_cannot_turn_on_a_new_tablet_from_the_panel_command(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_ws_client: ClientSessionGenerator,
    addon_user: User,  # noqa: F811
) -> None:
    """The panel's command, sent with the Supervisor's token and approve true.

    Add-ons such as Node-RED or AppDaemon call Home Assistant as that
    system-generated admin. HA's own admin check lets it through, so the
    command needs the integration's person check. It may still switch a
    tablet that is on, like an automation.
    """
    _kitchen, porch = await approved_and_new(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    assignments = config_entry.runtime_data.assignments
    client = await hass_ws_client(hass, access_token=await token_of(hass, addon_user))
    response = await command(client, assign(NEW, "tab-home", approve=True))
    assert response["error"] == {"code": "approval_needed", "message": APPROVAL_NEEDED}
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not assignments.approved(NEW)
    assert config_entry.runtime_data.sender.sessions[NEW].status == STATUS_NEW
    assert porch.calls == []

    response = await command(client, assign(REAL, "tab-bed"))
    assert response["success"], response
    assert assignments.dashboard(REAL) == "tab-bed"


async def test_an_approval_under_another_entry_is_not_trusted(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """An approval stored under an ESPHome entry the device no longer has.

    For example one a caller read just before the device moved. The
    record says approved, but the tablet is not trusted: it stays new and
    hears nothing.
    """
    _kitchen, porch = await approved_and_new(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    admin = await hass.auth.async_create_user("Admin", group_ids=["system-admin"])
    assignments = config_entry.runtime_data.assignments
    sender = config_entry.runtime_data.sender
    session = sender.sessions[NEW]
    await async_show_dashboard(
        hass, assignments, NEW, "tab-home", "stale-entry", Context(user_id=admin.id)
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert assignments.approved(NEW)
    assert assignments.entry_id(NEW) == "stale-entry"
    assert not session.approved
    assert session.status == STATUS_NEW
    assert session.dashboard is None
    assert sender.tablet_json(session)["approved"] is False
    assert porch.calls == []


# ---------------------------------------------- a call that was already waiting


async def test_a_waiting_call_is_not_sent_after_the_tablet_moved_entry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A call queued behind another one when the device moves to another entry.

    It waited for the call before it to end. By the time it may go, the
    tablet is new again: nothing is sent (without the check it went out
    unsigned to the re-adopted device), and the session is forgotten.
    """
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet(mac=REAL.upper())
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD), title="Home")
    session = config_entry.runtime_data.sender.sessions[REAL]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert session.nonce is not None
    assert session.live is not None
    calls = len(tablet.calls)

    await session._lock.acquire()  # noqa: SLF001 (the call before it)
    try:
        waiting = asyncio.create_task(
            session._call("tab_clear", {}, body="")  # noqa: SLF001
        )
        for _ in range(5):
            await asyncio.sleep(0)
        assert not waiting.done()
        other = MockConfigEntry(domain="esphome", title="Kitchen Tablet")
        other.add_to_hass(hass)
        device_registry.async_update_device(
            async_get_tablets(hass)[REAL].id, new_config_entry_id=other.entry_id
        )
        await until(hass, lambda: not session.approved)
    finally:
        session._lock.release()  # noqa: SLF001
    with pytest.raises(LinkError) as err:
        await waiting
    assert err.value.code == "not_approved"
    await hass.async_block_till_done(wait_background_tasks=True)

    assert tablet.calls[calls:] == []
    assert session.status == STATUS_NEW
    assert session.nonce is None
    assert session.live is None
    assert session.want is None
    assert session.kept == {}


# ------------------------------------------------- an erased tablet waits in HA


class FakeEsphomeFlow(ConfigFlow):
    """ESPHome's reauth as Home Assistant 2026.11 runs it, without a device.

    `first` is the step it shows: ESPHome shows "encryption removed" for a
    device that came back without its key, and asks for a key otherwise.
    """

    VERSION = 1
    first = ESPHOME_ERASED_STEP

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Show the step the device's state leads to."""
        return self.async_show_form(step_id=self.first)

    async def async_step_reauth_encryption_removed_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Finish: the admin confirmed."""
        return self.async_abort(reason="reauth_successful")

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Finish: the admin gave a key."""
        return self.async_abort(reason="reauth_successful")


async def _async_entry_ok(hass: HomeAssistant, entry: Any) -> bool:
    """Set up or unload a stand-in ESPHome entry: nothing to do."""
    return True


@pytest.fixture
def esphome_flows(hass: HomeAssistant) -> Any:
    """Let ESPHome entries start their reauth flow, with FakeEsphomeFlow.

    Its entries can be reloaded, as from their menu in Settings > Devices &
    services > ESPHome.
    """
    mock_integration(
        hass,
        MockModule(
            "esphome",
            async_setup_entry=_async_entry_ok,
            async_unload_entry=_async_entry_ok,
        ),
    )
    mock_platform(hass, "esphome.config_flow", None)
    with mock_config_flow("esphome", FakeEsphomeFlow):
        yield FakeEsphomeFlow
    FakeEsphomeFlow.first = ESPHOME_ERASED_STEP


async def test_the_panel_says_when_an_erased_tablet_waits_for_an_admin(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_ws_client: ClientSessionGenerator,
    esphome_flows: Any,
) -> None:
    """After a hold-to-erase, HA waits for its reauth to be confirmed.

    The tablet's row learns it at once (reauth "erased" and the name Repairs
    uses), and again when the admin confirmed. A flow that asks for a key
    reads "key". A tablet under another entry is not touched.
    """
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    erased = MockConfigEntry(domain="esphome", title="Apollo TAB-1 ddee01")
    erased.add_to_hass(hass)
    make_tablet(mac=REAL.upper(), entry=erased)
    make_tablet(mac=NEW.upper(), name="Porch Tablet")
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD), title="Home")
    sender = config_entry.runtime_data.sender
    await until(hass, lambda: sender.sessions[REAL].status == STATUS_ON_TABLET)

    client = await hass_ws_client(hass)
    response = await command(client, {"type": "apollo_tab/tablets/subscribe"})
    assert response["success"], response
    subscription = response["id"]

    async def next_list(want: Any) -> dict[str, dict[str, Any]]:
        """Return the first tablet list event for which want(list) holds."""
        async with asyncio.timeout(5):
            while True:
                message = await client.receive_json()
                assert message["id"] == subscription
                tablets = {t["mac"]: t for t in message["event"]["tablets"]}
                for index, tablet in enumerate(tablets.values()):
                    check_tablet(f"event[{index}]", tablet)
                if want(tablets):
                    return tablets

    first = await next_list(lambda tablets: True)
    assert (first[REAL]["reauth"], first[REAL]["reauth_name"]) == (None, None)

    # The tablet was erased: ESPHome's reauth and HA's Repairs issue.
    erased.async_start_reauth(hass)
    await hass.async_block_till_done()
    repair = ir.async_get(hass).async_get_issue(
        HOMEASSISTANT_DOMAIN, f"config_entry_reauth_esphome_{erased.entry_id}"
    )
    assert repair is not None
    assert repair.translation_placeholders == {"name": "Apollo TAB-1 ddee01"}
    tablets = await next_list(lambda tablets: tablets[REAL]["reauth"] is not None)
    assert tablets[REAL]["reauth"] == REAUTH_ERASED
    assert tablets[REAL]["reauth_name"] == "Apollo TAB-1 ddee01"
    assert tablets[NEW]["reauth"] is None
    listed = (await command(client, {"type": "apollo_tab/tablets"}))["result"]
    by_mac = {t["mac"]: t for t in listed["tablets"]}
    assert by_mac[REAL]["reauth"] == REAUTH_ERASED

    # The admin confirms in Repairs: the row says nothing more.
    (flow,) = hass.config_entries.flow.async_progress_by_handler("esphome")
    await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    await hass.async_block_till_done()
    tablets = await next_list(lambda tablets: tablets[REAL]["reauth"] is None)
    assert tablets[REAL]["reauth_name"] is None

    # A reauth that asks for a key.
    esphome_flows.first = "reauth_confirm"
    erased.async_start_reauth(hass)
    await hass.async_block_till_done()
    tablets = await next_list(lambda tablets: tablets[REAL]["reauth"] is not None)
    assert tablets[REAL]["reauth"] == REAUTH_KEY
    assert tablets[REAL]["reauth_name"] == "Apollo TAB-1 ddee01"


async def test_the_steps_for_a_key_lead_to_the_erased_question(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    hass_ws_client: ClientSessionGenerator,
    esphome_flows: Any,
) -> None:
    """The panel's steps for a key (round 8) work with this Home Assistant.

    While Home Assistant asks for a key, a tablet that comes back erased
    starts no new question: one runs already, and closing its dialog keeps
    it. Reloading the tablet's ESPHome entry ends it; the next connection
    then asks the erased question, which the panel's erased line explains.
    """
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    erased = MockConfigEntry(domain="esphome", title="Apollo TAB-1 ddee01")
    erased.add_to_hass(hass)
    make_tablet(mac=REAL.upper(), entry=erased)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD), title="Home")
    sender = config_entry.runtime_data.sender
    await until(hass, lambda: sender.sessions[REAL].status == STATUS_ON_TABLET)

    client = await hass_ws_client(hass)

    async def reauth() -> Any:
        """Return the tablet's reauth as the panel gets it."""
        await hass.async_block_till_done()
        listed = (await command(client, {"type": "apollo_tab/tablets"}))["result"]
        return {t["mac"]: t for t in listed["tablets"]}[REAL]["reauth"]

    def steps() -> list[str]:
        """Return the steps of the tablet's open questions."""
        return [
            flow["step_id"]
            for flow in hass.config_entries.flow.async_progress_by_handler("esphome")
        ]

    # Home Assistant met the erased tablet after its 15 minutes: it asks
    # for a key.
    esphome_flows.first = "reauth_confirm"
    erased.async_start_reauth(hass)
    assert await reauth() == REAUTH_KEY
    # The tablet restarts and comes back without its key, but the question
    # for a key stays: Home Assistant starts no second one.
    esphome_flows.first = ESPHOME_ERASED_STEP
    erased.async_start_reauth(hass)
    assert await reauth() == REAUTH_KEY
    assert steps() == ["reauth_confirm"]
    # Settings > Devices & services > ESPHome, the tablet's menu, Reload:
    # the question for a key ends.
    assert await hass.config_entries.async_reload(erased.entry_id)
    assert await reauth() is None
    assert steps() == []
    # Its next connection finds it without its key: the erased question.
    erased.async_start_reauth(hass)
    assert await reauth() == REAUTH_ERASED
    assert steps() == [ESPHOME_ERASED_STEP]
