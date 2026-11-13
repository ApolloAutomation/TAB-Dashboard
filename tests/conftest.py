"""Shared fixtures for the Apollo TAB Dashboard tests."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.apollo_tab import sender
from custom_components.apollo_tab.assignments import STORE_KEY, STORE_VERSION
from custom_components.apollo_tab.const import DOMAIN
from custom_components.apollo_tab.sender import LINK_FACTORY
from custom_components.apollo_tab.tablet_link import MemoryTabletLink

from .fake_tablet import FakeTablet

type AddTablet = Callable[..., dr.DeviceEntry]
type WriteComponent = Callable[[str, str], Path]
type SaveDashboard = Callable[..., Awaitable[Any]]

# No websocket answer or event takes this long; a test that waits for one
# that never comes fails instead of hanging.
RECEIVE_TIMEOUT = 10


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration from custom_components."""


@pytest.fixture
def hass_ws_client(hass_ws_client: ClientSessionGenerator) -> ClientSessionGenerator:
    """Return websocket clients whose every receive has a time limit."""

    async def _create(*args: Any, **kwargs: Any) -> Any:
        """Create one client and put the time limit around receive_json."""
        client = await hass_ws_client(*args, **kwargs)
        receive_json = client.receive_json

        async def _receive_json(*receive_args: Any, **receive_kwargs: Any) -> Any:
            """Receive one message or raise TimeoutError."""
            async with asyncio.timeout(RECEIVE_TIMEOUT):
                return await receive_json(*receive_args, **receive_kwargs)

        client.receive_json = _receive_json
        return client

    return _create


@pytest.fixture
def esphome_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return an ESPHome config entry that owns one tablet. It is never set up."""
    entry = MockConfigEntry(domain="esphome", title="Kitchen Tablet")
    entry.add_to_hass(hass)
    return entry


def approve_earlier(
    hass: HomeAssistant, hass_storage: dict[str, Any], mac: str, entry_id: str
) -> None:
    """Record that an admin approved a tablet before the test began.

    Written to the stored file when the integration is not loaded, or into
    the loaded integration's records (before the device registry change
    reaches it).
    """
    mac = mac.lower()
    loaded = hass.config_entries.async_loaded_entries(DOMAIN)
    if loaded:
        tablets = loaded[0].runtime_data.assignments._tablets
    else:
        stored = hass_storage.setdefault(
            STORE_KEY,
            {"version": STORE_VERSION, "key": STORE_KEY, "data": {"tablets": {}}},
        )
        tablets = stored["data"].setdefault("tablets", {})
    record = tablets.setdefault(mac, {"dashboard": None, "secret": None, "kid": None})
    record.update(approved=True, entry_id=entry_id)


def has_record(hass: HomeAssistant, hass_storage: dict[str, Any], mac: str) -> bool:
    """Return whether the integration holds a record for this MAC."""
    mac = mac.lower()
    loaded = hass.config_entries.async_loaded_entries(DOMAIN)
    if loaded:
        return loaded[0].runtime_data.assignments.get(mac) is not None
    stored = hass_storage.get(STORE_KEY, {}).get("data", {}).get("tablets", {})
    return mac in stored


@pytest.fixture
def add_tablet(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    hass_storage: dict[str, Any],
) -> AddTablet:
    """Return a function that registers a device the way ESPHome does.

    approved: True records that an admin approved the tablet under this
    ESPHome entry before the test began; False leaves it new, so it waits
    for an admin. None (the default) approves a MAC the integration holds
    no record for, and leaves a known MAC as it is: a tablet added again
    under another entry then has to be approved again.
    """

    def _add_tablet(
        entry: MockConfigEntry | None = None,
        *,
        mac: str = "AA:BB:CC:DD:EE:01",
        name: str = "Kitchen Tablet",
        manufacturer: str = "ApolloAutomation",
        model: str = "TAB-1",
        approved: bool | None = None,
    ) -> dr.DeviceEntry:
        if entry is None:
            entry = MockConfigEntry(domain="esphome", title=name)
            entry.add_to_hass(hass)
        if approved is None:
            approved = not has_record(hass, hass_storage, mac)
        if approved:
            approve_earlier(hass, hass_storage, mac, entry.entry_id)
        return device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            connections={(dr.CONNECTION_NETWORK_MAC, mac)},
            name=name,
            manufacturer=manufacturer,
            model=model,
            sw_version="26.11.0 (ESPHome 2026.10.3)",
        )

    return _add_tablet


@pytest.fixture
async def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return the integration's config entry, not yet set up."""
    entry = MockConfigEntry(domain=DOMAIN, title="Apollo TAB Dashboard", data={})
    entry.add_to_hass(hass)
    return entry


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the integration and wait until it has finished."""
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
def user_components(hass: HomeAssistant, tmp_path: Path) -> WriteComponent:
    """Point the config dir at tmp_path and return a component file writer."""
    hass.config.config_dir = str(tmp_path)

    def _write(file_name: str, text: str) -> Path:
        """Write one component file, creating the folder on first use."""
        folder = tmp_path / "apollo_tab" / "components"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / file_name
        path.write_text(text)
        return path

    return _write


@pytest.fixture
async def tab_dashboard(
    hass: HomeAssistant, hass_ws_client: ClientSessionGenerator
) -> SaveDashboard:
    """Return a function that saves a TAB-1 dashboard over the websocket.

    The integration must be set up before the function is used, because the
    first client freezes the router.
    """

    async def _save(config: dict, url_path: str = "tab-1") -> Any:
        """Create and save the dashboard and return the websocket client."""
        client = await hass_ws_client(hass)
        await client.send_json_auto_id(
            {
                "type": "lovelace/dashboards/create",
                "url_path": url_path,
                "title": "TAB-1",
                "icon": "mdi:tablet-dashboard",
                "mode": "storage",
                "require_admin": False,
                "show_in_sidebar": True,
            }
        )
        response = await client.receive_json()
        assert response["success"], response
        await client.send_json_auto_id(
            {
                "type": "lovelace/config/save",
                "url_path": url_path,
                "config": config,
            }
        )
        response = await client.receive_json()
        assert response["success"], response
        await hass.async_block_till_done()
        return client

    return _save


# ------------------------------------------------------------------ tablets

type MakeTablet = Callable[..., FakeTablet]
type SaveTabDashboard = Callable[..., Awaitable[None]]

# How long a test waits for the sender to reach a state.
UNTIL_TIMEOUT = 5


async def until(hass: HomeAssistant, condition: Callable[[], Any]) -> None:
    """Wait until condition() is true, letting tasks and short timers run.

    The sender's own tasks are background tasks, which can wait on a held
    build, so this does not wait for them to end.
    """
    async with asyncio.timeout(UNTIL_TIMEOUT):
        while True:
            await hass.async_block_till_done()
            if condition():
                return
            await asyncio.sleep(0.005)


@pytest.fixture
def fast_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shorten the sender's waits so the tests run in real time."""
    monkeypatch.setattr(sender, "DEBOUNCE_S", 0.02)
    monkeypatch.setattr(sender, "DEBOUNCE_MAX_S", 0.06)
    monkeypatch.setattr(sender, "STATUS_POLL_S", (0.005, 0.005, 0.01))
    monkeypatch.setattr(sender, "STATUS_POLL_LIMIT_S", 2.0)
    monkeypatch.setattr(sender, "VALUE_BATCH_S", 0.01)
    monkeypatch.setattr(sender, "SET_RETRY_S", 0.02)


@pytest.fixture
def memory_link(hass: HomeAssistant, fast_sender: None) -> MemoryTabletLink:
    """Make the integration reach simulated tablets instead of ESPHome."""
    link = MemoryTabletLink(hass)
    hass.data[LINK_FACTORY] = lambda _hass: link
    return link


@pytest.fixture
def make_tablet(
    hass: HomeAssistant, memory_link: MemoryTabletLink, add_tablet: AddTablet
) -> MakeTablet:
    """Return a function that registers a tablet and plugs in its simulation."""

    def _make(
        *,
        mac: str = "AA:BB:CC:DD:EE:01",
        name: str = "Kitchen Tablet",
        entry: MockConfigEntry | None = None,
        approved: bool | None = None,
        **kwargs: Any,
    ) -> FakeTablet:
        """Register the device and connect a FakeTablet for it."""
        add_tablet(entry, mac=mac, name=name, approved=approved)
        tablet = FakeTablet(hass, mac.lower(), **kwargs)
        memory_link.async_add(mac.lower(), tablet)
        return tablet

    return _make


@pytest.fixture
async def save_tab_dashboard(
    hass: HomeAssistant, hass_ws_client: ClientSessionGenerator
) -> SaveTabDashboard:
    """Return a function that creates or saves a TAB-1 dashboard by url_path.

    The integration must be set up before the function is used.
    """
    clients: list[Any] = []
    created: set[str] = set()

    async def _save(url_path: str, config: dict, title: str | None = None) -> None:
        """Create the dashboard on first use, then save its config."""
        if not clients:
            clients.append(await hass_ws_client(hass))
        client = clients[0]
        if url_path not in created:
            await client.send_json_auto_id(
                {
                    "type": "lovelace/dashboards/create",
                    "url_path": url_path,
                    "title": title or url_path,
                    "mode": "storage",
                    "require_admin": False,
                    "show_in_sidebar": True,
                }
            )
            response = await client.receive_json()
            assert response["success"], response
            created.add(url_path)
        await client.send_json_auto_id(
            {"type": "lovelace/config/save", "url_path": url_path, "config": config}
        )
        response = await client.receive_json()
        assert response["success"], response
        await hass.async_block_till_done()

    return _save
