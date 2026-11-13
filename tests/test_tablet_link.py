"""Tests for the link to tablets through the ESPHome integration.

Most tests use a stand-in for ESPHome's runtime data with exactly the
attributes the link uses, so they run without the ESPHome integration. One
test uses the real RuntimeEntryData. It needs the requirements of Home
Assistant's esphome and usb integrations, which are not in
requirements_test.txt: both CI workflows install them, and set
APOLLO_TAB_NEED_ESPHOME so that test fails there instead of skipping.
Locally it is skipped with the missing module named.
"""

import base64
import importlib
import json
import os
import threading
from collections.abc import Callable, Iterator
from datetime import timedelta
from types import ModuleType
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.apollo_tab import tablet_link
from custom_components.apollo_tab.const import DOMAIN
from custom_components.apollo_tab.sender import STATUS_OFFLINE, STATUS_ON_TABLET
from custom_components.apollo_tab.tablet_link import (
    LINK_CHECKING,
    LINK_NO_ENGINE,
    LINK_OFFLINE,
    LINK_READY,
    LINK_UNSUPPORTED,
    EsphomeTabletLink,
    LinkError,
)

from .conftest import setup_integration, until
from .fake_tablet import FakeTablet


def import_or_skip(name: str, why: str) -> ModuleType:
    """Import a module; skip without it, but fail where CI said it is there."""
    try:
        return importlib.import_module(name)
    except ImportError as err:
        reason = (
            f"{why} ({err}). CI installs them in the ESPHome step of "
            ".github/workflows/test.yml"
        )
        if os.environ.get("APOLLO_TAB_NEED_ESPHOME"):
            pytest.fail(reason)
        pytest.skip(reason, allow_module_level=True)


aioesphomeapi = import_or_skip(
    "aioesphomeapi",
    "aioesphomeapi, a requirement of the esphome integration, is missing",
)

MAC = "aa:bb:cc:dd:ee:01"
KEY = bytes(range(32))
TAB_CONFIG = {
    "apollo_tab": {"version": 1, "theme": "midnight"},
    "views": [
        {
            "type": "sections",
            "path": "home",
            "title": "Home",
            "max_columns": 3,
            "sections": [
                {
                    "type": "grid",
                    "cards": [
                        {
                            "type": "custom:apollo-tab-card",
                            "component": "apollo/light-tile",
                            "params": {"entity": "light.kitchen"},
                        }
                    ],
                }
            ],
        }
    ],
}


def service(name: str, key: int) -> Any:
    """Return an ESPHome user service as aioesphomeapi describes it."""
    return aioesphomeapi.UserService(name=name, key=key, args=[])


ENGINE_SERVICES = {
    key: service(name, key)
    for key, name in enumerate(tablet_link.RESPONSE_MODES, start=1)
}


class FakeClient:
    """The one APIClient method the link uses."""

    def __init__(self) -> None:
        """Answer every call with success and no data."""
        self.calls: list[tuple[str, dict, dict]] = []
        self.answer: Any = aioesphomeapi.ExecuteServiceResponse(success=True)
        self.raises: BaseException | None = None

    async def execute_service(self, service: Any, data: dict, **kwargs: Any) -> Any:
        """Record the call and return or raise what the test prepared."""
        self.calls.append((service.name, data, kwargs))
        if self.raises is not None:
            raise self.raises
        return self.answer


class FakeRuntimeData:
    """The attributes of ESPHome's RuntimeEntryData that the link uses."""

    def __init__(self, services: dict | None = None) -> None:
        """Start connected with the given action list."""
        self.available = True
        self.services: dict[int, Any] = dict(services or {})
        self.client = FakeClient()
        self.device_listeners: set[Callable[[], None]] = set()

    def async_subscribe_device_updated(
        self, listener: Callable[[], None]
    ) -> Callable[[], None]:
        """Add a listener and return its remover, like ESPHome does."""
        self.device_listeners.add(listener)
        return lambda: self.device_listeners.remove(listener)

    def device_updated(self) -> None:
        """Tell the listeners, as ESPHome does on connect and disconnect."""
        for listener in list(self.device_listeners):
            listener()


@pytest.fixture
def esphome_entry(hass: HomeAssistant) -> Iterator[MockConfigEntry]:
    """Return an ESPHome entry with an API encryption key.

    Its loaded state is only pretended, so it is put back before Home
    Assistant stops, which would otherwise try to unload it.
    """
    entry = MockConfigEntry(
        domain="esphome",
        title="Kitchen Tablet",
        data={"noise_psk": base64.b64encode(KEY).decode()},
    )
    entry.add_to_hass(hass)
    yield entry
    entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


def load(hass: HomeAssistant, entry: MockConfigEntry, runtime: Any) -> None:
    """Put the entry in the loaded state with this runtime data."""
    entry.runtime_data = runtime
    entry.mock_state(hass, ConfigEntryState.LOADED)


def later(hass: HomeAssistant, seconds: float) -> None:
    """Move the clock forward."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))


@pytest.fixture
def link(
    hass: HomeAssistant,
) -> Iterator[tuple[EsphomeTabletLink, list[tuple[str, str]]]]:
    """Return a link and the list of (mac, state) changes it reported."""
    changes: list[tuple[str, str]] = []
    esphome_link = EsphomeTabletLink(hass)
    esphome_link.async_set_listener(lambda mac, state: changes.append((mac, state)))
    yield esphome_link, changes
    esphome_link.async_stop()


async def test_not_loaded_is_offline(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """An ESPHome entry that is not loaded means offline."""
    esphome_link, changes = link
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    assert esphome_link.state(MAC) == LINK_OFFLINE
    with pytest.raises(LinkError) as err:
        await esphome_link.async_call(MAC, "tab_status", {})
    assert err.value.code == "offline"


async def test_finds_the_engine_after_the_action_list_arrives(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """ESPHome first fills the list from its store; checks at 0.2, 1 and 3 s."""
    esphome_link, changes = link
    runtime = FakeRuntimeData({})  # the stale list from the store
    load(hass, esphome_entry, runtime)
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    assert esphome_link.state(MAC) == LINK_CHECKING

    later(hass, 0.3)
    assert esphome_link.state(MAC) == LINK_CHECKING
    runtime.services = dict(ENGINE_SERVICES)  # the device's real list
    later(hass, 1.1)
    assert esphome_link.state(MAC) == LINK_READY
    assert changes == [(MAC, LINK_CHECKING), (MAC, LINK_READY)]


async def test_no_engine_after_three_seconds(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """No tab_hello after the last check: no engine."""
    esphome_link, changes = link
    load(hass, esphome_entry, FakeRuntimeData({1: service("restart", 1)}))
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    later(hass, 1.1)
    assert esphome_link.state(MAC) == LINK_CHECKING
    later(hass, 3.1)
    assert esphome_link.state(MAC) == LINK_NO_ENGINE
    with pytest.raises(LinkError) as err:
        await esphome_link.async_call(MAC, "tab_hello", {"nonce": "", "auth": ""})
    assert err.value.code == "no_engine"


async def test_checks_run_on_the_event_loop(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """The scheduled checks, and every state change they report, run on the loop.

    A plain function given to async_call_later would run in a worker thread,
    and the sender it tells touches the event loop's objects.
    """
    esphome_link, _changes = link
    loop_thread = threading.get_ident()
    seen: list[tuple[str, int]] = []
    esphome_link.async_set_listener(
        lambda _mac, state: seen.append((state, threading.get_ident()))
    )
    runtime = FakeRuntimeData({})
    load(hass, esphome_entry, runtime)
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    later(hass, 0.3)
    runtime.services = dict(ENGINE_SERVICES)
    later(hass, 1.1)
    await hass.async_block_till_done()
    assert [state for state, _thread in seen] == [LINK_CHECKING, LINK_READY]
    assert all(thread == loop_thread for _state, thread in seen)


async def test_disconnect_and_reconnect(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """Every new connection goes through checking to ready again."""
    esphome_link, changes = link
    runtime = FakeRuntimeData(ENGINE_SERVICES)
    load(hass, esphome_entry, runtime)
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    later(hass, 0.3)
    assert esphome_link.state(MAC) == LINK_READY

    runtime.available = False
    runtime.device_updated()
    assert esphome_link.state(MAC) == LINK_OFFLINE
    runtime.available = True
    runtime.device_updated()
    assert esphome_link.state(MAC) == LINK_CHECKING
    later(hass, 0.3)
    assert changes[-3:] == [
        (MAC, LINK_OFFLINE),
        (MAC, LINK_CHECKING),
        (MAC, LINK_READY),
    ]


async def test_entry_reload_uses_the_new_runtime_data(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """A reload makes new runtime data and a new client; the link follows."""
    esphome_link, changes = link
    first = FakeRuntimeData(ENGINE_SERVICES)
    load(hass, esphome_entry, first)
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    later(hass, 0.3)

    esphome_entry.mock_state(hass, ConfigEntryState.UNLOAD_IN_PROGRESS)
    assert esphome_link.state(MAC) == LINK_OFFLINE
    esphome_entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
    esphome_entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    second = FakeRuntimeData(ENGINE_SERVICES)
    load(hass, esphome_entry, second)
    later(hass, 0.3)
    assert esphome_link.state(MAC) == LINK_READY
    assert first.device_listeners == set()
    assert len(second.device_listeners) == 1

    await esphome_link.async_call(MAC, "tab_set", {"data": "{}", "auth": ""})
    assert first.client.calls == []
    assert second.client.calls[0][0] == "tab_set"


async def test_calls_and_response_modes(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """Data actions return parsed JSON; status actions return {}; ack nothing."""
    esphome_link, changes = link
    runtime = FakeRuntimeData(ENGINE_SERVICES)
    load(hass, esphome_entry, runtime)
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    later(hass, 0.3)
    client = runtime.client

    client.answer = aioesphomeapi.ExecuteServiceResponse(
        success=True, response_data=json.dumps({"layout": "x"}).encode()
    )
    assert await esphome_link.async_call(MAC, "tab_status", {}) == {"layout": "x"}
    assert client.calls[-1][2] == {
        "return_response": True,
        "timeout": tablet_link.CALL_TIMEOUT,
    }

    client.answer = aioesphomeapi.ExecuteServiceResponse(success=True)
    assert await esphome_link.async_call(MAC, "tab_commit", {"hash": "h"}) == {}
    assert client.calls[-1][2]["return_response"] is False

    client.answer = None
    assert await esphome_link.async_call(MAC, "tab_ack", {"n": 1}) is None
    assert client.calls[-1][2] == {}


@pytest.mark.parametrize(
    ("answer", "raises", "code"),
    [
        ("error:too_big", None, "too_big"),
        ("error:", None, "failed"),
        ("data:[1]", None, "bad_response"),
        ("data:{bad", None, "bad_response"),
        (None, None, "timeout"),
        ("ok", TimeoutError(), "timeout"),
        ("ok", ConnectionError(), "offline"),
    ],
)
async def test_call_errors(
    hass: HomeAssistant,
    esphome_entry: MockConfigEntry,
    link,
    answer: str | None,
    raises: BaseException | None,
    code: str,
) -> None:
    """Every failure becomes one LinkError code."""
    esphome_link, changes = link
    runtime = FakeRuntimeData(ENGINE_SERVICES)
    load(hass, esphome_entry, runtime)
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    later(hass, 0.3)
    if answer is None:
        runtime.client.answer = None
    elif answer.startswith("error:"):
        runtime.client.answer = aioesphomeapi.ExecuteServiceResponse(
            success=False, error_message=answer[6:]
        )
    elif answer.startswith("data:"):
        runtime.client.answer = aioesphomeapi.ExecuteServiceResponse(
            success=True, response_data=answer[5:].encode()
        )
    runtime.client.raises = raises
    with pytest.raises(LinkError) as err:
        await esphome_link.async_call(MAC, "tab_hello", {"nonce": "n", "auth": ""})
    assert err.value.code == code


async def test_timeout_reads_the_action_list_again(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """After a timeout the link looks again: the engine may be gone."""
    esphome_link, changes = link
    runtime = FakeRuntimeData(ENGINE_SERVICES)
    load(hass, esphome_entry, runtime)
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    later(hass, 0.3)
    runtime.client.raises = TimeoutError()
    with pytest.raises(LinkError) as err:
        await esphome_link.async_call(MAC, "tab_status", {})
    assert err.value.code == "timeout"
    # The tablet came back with other firmware before the second look.
    runtime.services = {}
    await hass.async_block_till_done()
    assert esphome_link.state(MAC) == LINK_NO_ENGINE


async def test_missing_internals_raise_a_repair_issue(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """When ESPHome's internals change, the panel says so and a repair shows."""
    esphome_link, changes = link
    load(hass, esphome_entry, object())
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    assert esphome_link.state(MAC) == LINK_UNSUPPORTED
    assert ir.async_get(hass).async_get_issue(DOMAIN, tablet_link.ISSUE_ID)
    with pytest.raises(LinkError) as err:
        await esphome_link.async_call(MAC, "tab_status", {})
    assert err.value.code == "ha_version"


async def test_api_key(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """The key comes from the ESPHome entry, read fresh; bad keys are None."""
    esphome_link, changes = link
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    assert esphome_link.api_key(MAC) == KEY
    hass.config_entries.async_update_entry(esphome_entry, data={"noise_psk": "x"})
    assert esphome_link.api_key(MAC) is None
    hass.config_entries.async_update_entry(esphome_entry, data={})
    assert esphome_link.api_key(MAC) is None
    assert esphome_link.api_key("aa:00") is None


async def test_encryption_supported(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """Only a connected tablet that says it takes no key cannot take one."""
    esphome_link, changes = link
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    # Not loaded, not watched, or no device info yet: a key may come.
    assert esphome_link.encryption_supported(MAC) is True
    assert esphome_link.encryption_supported("aa:00") is True
    runtime = FakeRuntimeData(ENGINE_SERVICES)
    load(hass, esphome_entry, runtime)
    assert esphome_link.encryption_supported(MAC) is True
    runtime.device_info = aioesphomeapi.DeviceInfo(api_encryption_supported=True)
    assert esphome_link.encryption_supported(MAC) is True
    runtime.device_info = aioesphomeapi.DeviceInfo(api_encryption_supported=False)
    assert esphome_link.encryption_supported(MAC) is False


async def test_unwatch_removes_every_listener(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """Stopping leaves nothing behind in ESPHome's runtime data."""
    esphome_link, changes = link
    runtime = FakeRuntimeData({})
    load(hass, esphome_entry, runtime)
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    assert len(runtime.device_listeners) == 1
    esphome_link.async_unwatch(MAC)
    assert runtime.device_listeners == set()
    later(hass, 5)
    assert esphome_link.state(MAC) == LINK_OFFLINE
    assert esphome_entry._on_state_change in (None, [])


async def test_real_runtime_entry_data(
    hass: HomeAssistant, esphome_entry: MockConfigEntry, link
) -> None:
    """The link works with ESPHome's own RuntimeEntryData."""
    entry_data = import_or_skip(
        "homeassistant.components.esphome.entry_data",
        "Home Assistant's ESPHome integration cannot be imported here: the "
        "requirements of its esphome and usb integrations are not installed",
    )
    esphome_link, changes = link
    client = FakeClient()
    runtime = entry_data.RuntimeEntryData(
        entry_id=esphome_entry.entry_id,
        title="Kitchen Tablet",
        client=client,
        store=None,
    )
    runtime.available = True
    runtime.services = dict(ENGINE_SERVICES)
    load(hass, esphome_entry, runtime)
    esphome_link.async_watch(MAC, esphome_entry.entry_id)
    later(hass, 0.3)
    assert esphome_link.state(MAC) == LINK_READY
    await esphome_link.async_call(MAC, "tab_commit", {"hash": "h", "auth": ""})
    assert client.calls[0][0] == "tab_commit"
    runtime.available = False
    runtime.async_update_device_state()
    assert esphome_link.state(MAC) == LINK_OFFLINE


class TabletClient(FakeClient):
    """An APIClient stand-in that hands every call to a simulated tablet."""

    def __init__(self, tablet: Any) -> None:
        """Wrap the tablet."""
        super().__init__()
        self.tablet = tablet

    async def execute_service(self, service: Any, data: dict, **kwargs: Any) -> Any:
        """Answer like ESPHome: success, error_message, response_data."""
        self.calls.append((service.name, data, kwargs))
        try:
            result = await self.tablet.async_call(service.name, data)
        except LinkError as err:
            return aioesphomeapi.ExecuteServiceResponse(
                success=False, error_message=err.code
            )
        if kwargs.get("return_response") is None:
            return None
        return aioesphomeapi.ExecuteServiceResponse(
            success=True, response_data=json.dumps(result or {}).encode()
        )


async def test_entry_reload_is_followed_by_a_new_handshake(
    hass: HomeAssistant,
    esphome_entry: MockConfigEntry,
    config_entry: MockConfigEntry,
    add_tablet,
    save_tab_dashboard,
) -> None:
    """The sender over the real ESPHome link greets again after a reload."""
    add_tablet(esphome_entry)
    tablet = FakeTablet(hass, MAC, psk=KEY)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", TAB_CONFIG)
    session = config_entry.runtime_data.sender.sessions[MAC]
    assert session.status == STATUS_OFFLINE

    runtime = FakeRuntimeData(ENGINE_SERVICES)
    runtime.client = TabletClient(tablet)
    load(hass, esphome_entry, runtime)
    later(hass, 0.3)
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert session.paired
    assert tablet.active == session.want.hash
    hellos = len(tablet.calls_of("tab_hello"))
    chunks = len(tablet.calls_of("tab_layout"))

    # ESPHome reloads the entry, for example after a new encryption key.
    esphome_entry.mock_state(hass, ConfigEntryState.UNLOAD_IN_PROGRESS)
    esphome_entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
    await until(hass, lambda: session.status == STATUS_OFFLINE)
    second = FakeRuntimeData(ENGINE_SERVICES)
    second.client = TabletClient(tablet)
    load(hass, esphome_entry, second)
    later(hass, 0.3)
    await until(
        hass,
        lambda: (
            len(tablet.calls_of("tab_hello")) > hellos
            and session.status == STATUS_ON_TABLET
        ),
    )
    assert len(tablet.calls_of("tab_layout")) == chunks
    assert second.client.calls[0][0] == "tab_hello"
    assert tablet.refused == []
    assert await hass.config_entries.async_unload(config_entry.entry_id)
