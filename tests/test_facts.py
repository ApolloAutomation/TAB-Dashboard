"""Tests for facts.py: facts read, stored, watched and held (cards spec C.2.4)."""

from __future__ import annotations

import shutil
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.cover.const import CoverEntityFeature
from homeassistant.components.light.const import LightEntityFeature
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.apollo_tab import (
    facts as facts_module,
    library as library_module,
    manager as manager_module,
)
from custom_components.apollo_tab.const import DOMAIN
from custom_components.apollo_tab.facts import (
    FactKeeper,
    held_issue_id,
    live_facts,
    raw_of,
)
from custom_components.apollo_tab.maker.convert import layout_hash
from custom_components.apollo_tab.maker.features import facts_of

from .conftest import setup_integration

HERE = Path(__file__).parent
LIGHT = (HERE / "cards2" / "light.yaml").read_text(encoding="utf-8")

# A card that names one fact of its light: can.brightness.
DIMMER = """\
schema: 2
id: me/dimmer
version: 1.0.0
name: Dimmer
params:
  entity: {domain: light, label: Light}
inputs:
  is_on: "{{ is_state(entity, 'on') }}"
outputs:
  toggle:
    action: light.toggle
    data: {entity_id: "{{ entity }}"}
    feedback: optimistic
on: is_on
tap:
  choices:
    toggle: {label: Turns it on or off, output: toggle}
    none: {label: Does nothing}
variants:
  tile:
    name: Tile
    grid: [6, 3]
    header: tile_v
    v1: apollo/light-tile
    layout:
      - {type: switch, value: is_on, on_tap: toggle, when: [can.brightness]}
"""

LAMP_ATTRS = {
    "friendly_name": "Living Lamp",
    "supported_color_modes": ["color_temp", "hs"],
    "min_color_temp_kelvin": 15,
    "max_color_temp_kelvin": 6535,
    "effect_list": ["None", "Rainbow"],
    "supported_features": int(LightEntityFeature.EFFECT),
    "brightness": 128,
}


def _dashboard(component: str, entity_id: str = "light.h1401") -> dict:
    """Return a TAB-1 dashboard with one card of a component."""
    return {
        "apollo_tab": {"version": 1},
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
                                "component": component,
                                "params": {"entity": entity_id},
                            }
                        ],
                    }
                ],
            }
        ],
    }


@pytest.fixture
def builtin_light(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Serve the built-in files plus the colour light of D.1 as built-ins."""
    folder = tmp_path / "builtin"
    shutil.copytree(library_module._BUILTIN_DIR, folder)
    (folder / "components" / "apollo-light.yaml").write_text(LIGHT, encoding="utf-8")
    monkeypatch.setattr(library_module, "_BUILTIN_DIR", folder)
    return folder


class Clock:
    """Frozen time that the test moves, with the timers that follow it."""

    def __init__(self, hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
        """Start at 0."""
        self.hass = hass
        self.freezer = freezer
        self._now = 0.0

    @property
    def now(self) -> float:
        """Return the seconds since the start."""
        return self._now

    @now.setter
    def now(self, seconds: float) -> None:
        """Move to a time without running timers."""
        self.freezer.tick(timedelta(seconds=seconds - self._now))
        self._now = seconds

    async def to(self, seconds: float) -> None:
        """Move to a time and run the timers that are due by then."""
        self.now = seconds
        async_fire_time_changed(self.hass)
        await self.hass.async_block_till_done()


async def _keeper(hass: HomeAssistant) -> FactKeeper:
    """Return a loaded keeper."""
    keeper = FactKeeper(hass)
    await keeper.async_load()
    return keeper


def _set_lamp(hass: HomeAssistant, **changes: Any) -> None:
    """Set the lamp's state with some attributes changed."""
    hass.states.async_set("light.h1401", "on", {**LAMP_ATTRS, **changes})


def _track(keeper: FactKeeper, url_path: str, names: set[str]) -> list[str]:
    """Note one dashboard that names some facts of the lamp; return its calls."""
    named = {"light.h1401": frozenset(names)}
    keeper.async_converted(url_path, named, keeper.facts_for(named))
    calls: list[str] = []
    keeper.async_listen(calls.append)
    return calls


# ---------------------------------------------------------------- reading


async def test_raw_of_reads_feature_bits_through_the_enums(hass: HomeAssistant) -> None:
    """Registry and state features come out as the enum members' names."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "cover",
        "test",
        "garage",
        suggested_object_id="garage",
        supported_features=CoverEntityFeature.SET_POSITION | CoverEntityFeature.STOP,
        original_device_class="garage",
    )
    hass.states.async_set(
        "cover.garage",
        "closed",
        {"supported_features": int(CoverEntityFeature.OPEN_TILT)},
    )
    raw = raw_of(hass, "cover.garage")
    assert raw["registry"]["features"] == ["SET_POSITION", "STOP"]
    assert raw["state"]["features"] == ["OPEN_TILT"]
    facts = live_facts(hass, "cover.garage")
    # The registry's bits come first; the state's are not mixed in.
    assert (facts["position"], facts["stop"], facts["tilt"]) == (True, True, False)
    assert facts["asks"] is True
    # Bits no enum member has are ignored.
    hass.states.async_set("lock.door", "locked", {"supported_features": 1 | 64})
    assert raw_of(hass, "lock.door")["state"]["features"] == ["OPEN"]


async def test_facts_from_the_registry_alone_state_alone_and_neither(
    hass: HomeAssistant,
) -> None:
    """A device away keeps its registry facts; one with neither gives the least."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "light",
        "test",
        "h1401",
        suggested_object_id="h1401",
        capabilities={
            "supported_color_modes": ["color_temp", "hs"],
            "min_color_temp_kelvin": 15,
            "max_color_temp_kelvin": 6535,
            "effect_list": ["Rainbow"],
        },
        supported_features=LightEntityFeature.EFFECT,
    )
    hass.states.async_set("light.h1401", STATE_UNAVAILABLE, {})
    facts = live_facts(hass, "light.h1401")
    assert facts["colour"] and facts["temperature"] and facts["effects"]
    assert (facts["min_kelvin"], facts["max_kelvin"]) == (2000, 6500)
    hass.states.async_set("light.state_only", "on", LAMP_ATTRS)
    assert live_facts(hass, "light.state_only") == facts_of(
        {
            "domain": "light",
            "state": {"attributes": LAMP_ATTRS, "features": ["EFFECT"]},
        }
    )
    assert live_facts(hass, "light.state_only")["effect_list"] == ["Rainbow"]
    assert live_facts(hass, "light.nothing") == facts_of({"domain": "light"})


async def test_a_device_away_gives_its_stored_facts(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """While a device is unavailable, the facts it was converted with are used."""
    keeper = await _keeper(hass)
    _set_lamp(hass)
    calls = _track(keeper, "tab-1", {"effect_list"})
    before = keeper.facts_for(["light.h1401"])
    hass.states.async_set("light.h1401", STATE_UNAVAILABLE, {})
    await hass.async_block_till_done()
    assert keeper.facts_for(["light.h1401"]) == before
    # A device that was never converted gives what is known now.
    hass.states.async_set("light.other", STATE_UNAVAILABLE, {})
    assert keeper.facts_for(["light.other"])["light.other"] == facts_of(
        {"domain": "light"}
    )
    clock = Clock(hass, freezer)
    await clock.to(120)
    assert calls == []
    keeper.async_stop()


# ---------------------------------------------------------------- the store


async def test_only_a_conversion_writes_the_store(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Reading writes nothing; a noted conversion is saved after a delay."""
    keeper = await _keeper(hass)
    _set_lamp(hass)
    keeper.facts_for(["light.h1401"])
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done()
    assert "apollo_tab.facts" not in hass_storage
    assert keeper.stored == {}
    _track(keeper, "tab-1", {"effect_list"})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))
    await hass.async_block_till_done()
    assert "apollo_tab.facts" not in hass_storage
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    stored = hass_storage["apollo_tab.facts"]["data"]
    assert stored["facts"] == {"light.h1401": live_facts(hass, "light.h1401")}
    assert list(stored["entries"]) == ["light.h1401"]
    keeper.async_stop()


async def test_the_store_holds_only_devices_a_dashboard_uses(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A device no dashboard uses is dropped; the store has a size cap."""
    hass_storage["apollo_tab.facts"] = {
        "version": 1,
        "key": "apollo_tab.facts",
        "data": {
            "facts": {"light.gone": {"toggle": True}, "bad": 5, "light.x": {}},
            "entries": {"light.gone": "0123456789abcdef", "bad": "x"},
        },
    }
    keeper = await _keeper(hass)
    assert keeper.stored == {"light.gone": {"toggle": True}}
    for n in range(4):
        hass.states.async_set(f"light.l{n}", "on", LAMP_ATTRS)
    named = {f"light.l{n}": frozenset({"effect_list"}) for n in range(4)}
    keeper.async_converted("tab-1", named, keeper.facts_for(named))
    keeper.async_prune()
    assert set(keeper.stored) == set(named)
    monkeypatch.setattr(facts_module, "MAX_STORED", 3)
    await keeper.async_flush()
    saved = hass_storage["apollo_tab.facts"]["data"]["facts"]
    assert sorted(saved) == ["light.l0", "light.l1", "light.l2"]
    monkeypatch.setattr(facts_module, "MAX_STORED_BYTES", 1)
    keeper._dirty = True
    await keeper.async_flush()
    assert hass_storage["apollo_tab.facts"]["data"]["facts"] == {}
    keeper.async_forget("tab-1")
    assert keeper.stored == {}
    keeper.async_stop()


# ---------------------------------------------------------------- converting again


async def test_a_changed_fact_converts_once(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Changes inside the quiet time give one conversion, 10 s after the last."""
    keeper = await _keeper(hass)
    clock = Clock(hass, freezer)
    _set_lamp(hass)
    calls = _track(keeper, "tab-1", {"effect_list", "effects"})
    _set_lamp(hass, effect_list=["Rainbow", "Fire"])
    _set_lamp(hass, effect_list=["Rainbow", "Fire", "Snow"])
    await hass.async_block_till_done()
    await clock.to(9)
    assert calls == []
    await clock.to(11)
    assert calls == ["tab-1"]
    await clock.to(200)
    assert calls == ["tab-1"]
    keeper.async_stop()


async def test_a_fact_no_card_names_converts_nothing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A change of an attribute or of a fact no card names is ignored."""
    keeper = await _keeper(hass)
    clock = Clock(hass, freezer)
    _set_lamp(hass)
    calls = _track(keeper, "tab-1", {"brightness"})
    _set_lamp(hass, brightness=20, effect_list=["Fire"], friendly_name="Lamp")
    _set_lamp(hass, supported_color_modes=["color_temp", "rgb"])
    await hass.async_block_till_done()
    await clock.to(100)
    assert calls == []
    # The named fact itself converts.
    _set_lamp(hass, supported_color_modes=["onoff"])
    await hass.async_block_till_done()
    await clock.to(111)
    assert calls == ["tab-1"]
    keeper.async_stop()


async def test_a_change_back_before_the_conversion_converts_nothing(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A fact that changes and changes back is what the dashboard used."""
    keeper = await _keeper(hass)
    clock = Clock(hass, freezer)
    _set_lamp(hass)
    calls = _track(keeper, "tab-1", {"effect_list"})
    _set_lamp(hass, effect_list=["Fire"])
    await hass.async_block_till_done()
    _set_lamp(hass)
    await hass.async_block_till_done()
    await clock.to(30)
    # The second change found the used facts again; the first still asks.
    assert calls in ([], ["tab-1"])
    keeper.async_stop()


async def test_at_most_once_a_minute_per_dashboard(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """After a conversion the next waits until 60 s have passed."""
    keeper = await _keeper(hass)
    clock = Clock(hass, freezer)
    _set_lamp(hass)
    calls = _track(keeper, "tab-1", {"effect_list"})
    _set_lamp(hass, effect_list=["A"])
    await hass.async_block_till_done()
    await clock.to(10)
    assert calls == ["tab-1"]
    # The manager converts with the new facts.
    keeper.async_converted(
        "tab-1",
        {"light.h1401": frozenset({"effect_list"})},
        keeper.facts_for(["light.h1401"]),
    )
    clock.now = 15
    _set_lamp(hass, effect_list=["B"])
    await hass.async_block_till_done()
    await clock.to(26)
    assert calls == ["tab-1"]
    await clock.to(69)
    assert calls == ["tab-1"]
    await clock.to(71)
    assert calls == ["tab-1", "tab-1"]
    keeper.async_stop()


async def test_a_device_just_added_converts_again_when_its_entry_fills(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A registry entry without capabilities gives the least, then fills."""
    keeper = await _keeper(hass)
    clock = Clock(hass, freezer)
    registry = er.async_get(hass)
    registry.async_get_or_create("light", "test", "h1401", suggested_object_id="h1401")
    hass.states.async_set("light.h1401", STATE_UNAVAILABLE, {})
    calls = _track(keeper, "tab-1", {"colour"})
    assert keeper.facts_for(["light.h1401"])["light.h1401"]["colour"] is False
    registry.async_update_entity(
        "light.h1401", capabilities={"supported_color_modes": ["hs"]}
    )
    await hass.async_block_till_done()
    assert keeper.facts_for(["light.h1401"])["light.h1401"]["colour"] is True
    await clock.to(11)
    assert calls == ["tab-1"]
    keeper.async_stop()


# ---------------------------------------------------------------- the hold


async def test_a_device_that_keeps_changing_is_held(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Three changes in an hour hold the last facts for 1 h, then for 6 h."""
    keeper = await _keeper(hass)
    clock = Clock(hass, freezer)
    _set_lamp(hass)
    calls = _track(keeper, "tab-1", {"effect_list"})
    issues = ir.async_get(hass)
    issue_id = held_issue_id("light.h1401")
    # A source list that changes every minute.
    for minute in (1, 2):
        clock.now = minute * 60
        _set_lamp(hass, effect_list=[f"E{minute}"])
        await hass.async_block_till_done()
        await clock.to(minute * 60 + 11)
    assert calls == ["tab-1", "tab-1"]
    held = keeper.facts_for(["light.h1401"])["light.h1401"]
    assert held["effect_list"] == ["E2"]
    clock.now = 180
    _set_lamp(hass, effect_list=["E3"])
    await hass.async_block_till_done()
    assert keeper.is_held("light.h1401")
    assert keeper.facts_for(["light.h1401"])["light.h1401"] == held
    issue = issues.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "facts_held"
    assert issue.translation_placeholders == {
        "device": "Living Lamp",
        "entity_id": "light.h1401",
        "hours": "1",
    }
    # Held: later changes give no conversion.
    for minute in range(4, 30):
        clock.now = minute * 60
        _set_lamp(hass, effect_list=[f"E{minute}"])
        await hass.async_block_till_done()
    await clock.to(1800)
    assert calls == ["tab-1", "tab-1"]
    # After the hour the device is read again and converts once.
    await clock.to(180 + 3600 + 1)
    assert not keeper.is_held("light.h1401")
    assert issues.async_get_issue(DOMAIN, issue_id) is None
    assert keeper.facts_for(["light.h1401"])["light.h1401"]["effect_list"] == ["E29"]
    await clock.to(180 + 3600 + 12)
    assert calls == ["tab-1"] * 3
    # Two more changes make three in the hour again: six hours this time.
    start = 180 + 3600 + 100
    for n in (1, 2):
        clock.now = start + n
        _set_lamp(hass, effect_list=[f"F{n}"])
        await hass.async_block_till_done()
    assert keeper.is_held("light.h1401")
    issue = issues.async_get_issue(DOMAIN, issue_id)
    assert issue.translation_placeholders["hours"] == "6"
    await clock.to(start + 3600 + 10)
    assert keeper.is_held("light.h1401")
    await clock.to(start + 6 * 3600 + 10)
    assert not keeper.is_held("light.h1401")
    keeper.async_stop()


async def test_changes_an_hour_apart_hold_nothing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Only changes within one hour count toward the hold."""
    keeper = await _keeper(hass)
    clock = Clock(hass, freezer)
    _set_lamp(hass)
    _track(keeper, "tab-1", {"effect_list"})
    for n in range(5):
        clock.now = n * 1900
        _set_lamp(hass, effect_list=[f"E{n}"])
        await hass.async_block_till_done()
    assert not keeper.is_held("light.h1401")
    keeper.async_stop()


async def test_stopping_ends_the_holds(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Unloading takes the repair note away with the hold."""
    keeper = await _keeper(hass)
    clock = Clock(hass, freezer)
    _set_lamp(hass)
    _track(keeper, "tab-1", {"effect_list"})
    for n in range(3):
        clock.now = n
        _set_lamp(hass, effect_list=[f"E{n}"])
        await hass.async_block_till_done()
    assert keeper.is_held("light.h1401")
    keeper.async_stop()
    assert not keeper.is_held("light.h1401")
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, held_issue_id("light.h1401")) is None


# ---------------------------------------------------------------- the manager


async def test_the_manager_hands_facts_in_and_converts_again(
    hass: HomeAssistant,
    builtin_light: Path,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
    monkeypatch: pytest.MonkeyPatch,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A saved dashboard is converted with facts and again when one changes."""
    seen: list[dict] = []
    real = manager_module.convert_dashboard

    def recording(*args: Any, **kwargs: Any) -> dict:
        seen.append(kwargs.get("facts"))
        return real(*args, **kwargs)

    monkeypatch.setattr(manager_module, "convert_dashboard", recording)
    _set_lamp(hass)
    await setup_integration(hass, config_entry)
    keeper = config_entry.runtime_data.facts
    clock = Clock(hass, freezer)
    await tab_dashboard(_dashboard("apollo/light"))
    assert seen[-1] == {"light.h1401": live_facts(hass, "light.h1401")}
    assert keeper.stored == seen[-1]
    count = len(seen)
    _set_lamp(hass, brightness=1)
    await hass.async_block_till_done()
    await clock.to(30)
    assert len(seen) == count
    _set_lamp(hass, supported_color_modes=["onoff"])
    await hass.async_block_till_done()
    await clock.to(41)
    assert len(seen) == count + 1
    assert seen[-1]["light.h1401"]["colour"] is False
    # A schema 1 card names no fact; its dashboard is handed none.
    await tab_dashboard(_dashboard("apollo/light-tile"), "tab-2")
    assert seen[-1] == {}


async def test_a_restart_gives_the_same_layout_hash(
    hass: HomeAssistant,
    builtin_light: Path,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
    hass_storage: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the lamp away after a restart, the stored facts give the same hash.

    Schema 2 cards are compiled by a later package, so the facts are put
    into the layout here to make its hash depend on them.
    """
    real = manager_module.convert_dashboard

    def with_facts(*args: Any, **kwargs: Any) -> dict:
        result = real(*args, **kwargs)
        layout = result["layout"]
        layout["probe"] = kwargs.get("facts")
        layout["hash"] = layout_hash(layout)
        return result

    monkeypatch.setattr(manager_module, "convert_dashboard", with_facts)
    _set_lamp(hass)
    await setup_integration(hass, config_entry)
    await tab_dashboard(_dashboard("apollo/light"))
    manager = config_entry.runtime_data.manager
    before = manager.layouts["tab-1"]["layout"]["hash"]
    assert manager.layouts["tab-1"]["layout"]["probe"]["light.h1401"]["colour"]
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert "light.h1401" in hass_storage["apollo_tab.facts"]["data"]["facts"]
    # The lamp has not answered yet after the restart.
    hass.states.async_set("light.h1401", STATE_UNAVAILABLE, {})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    manager = config_entry.runtime_data.manager
    assert manager.layouts["tab-1"]["layout"]["hash"] == before
    # Without the store the same start gives another hash.
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    del hass_storage["apollo_tab.facts"]
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    manager = config_entry.runtime_data.manager
    assert manager.layouts["tab-1"]["layout"]["hash"] != before


async def test_devices_of_dashboards_gone_since_the_last_run_are_dropped(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    """After the first conversions, stored devices no dashboard uses go."""
    hass_storage["apollo_tab.facts"] = {
        "version": 1,
        "key": "apollo_tab.facts",
        "data": {
            "facts": {"light.gone": {"toggle": True}},
            "entries": {"light.gone": "0123456789abcdef"},
        },
    }
    await setup_integration(hass, config_entry)
    assert config_entry.runtime_data.manager.ready
    assert config_entry.runtime_data.facts.stored == {}


async def test_a_deleted_dashboard_forgets_its_devices(
    hass: HomeAssistant,
    builtin_light: Path,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """A dashboard that is no TAB-1 dashboard any more leaves the store."""
    _set_lamp(hass)
    await setup_integration(hass, config_entry)
    client = await tab_dashboard(_dashboard("apollo/light"))
    keeper = config_entry.runtime_data.facts
    assert "light.h1401" in keeper.stored
    await client.send_json_auto_id(
        {
            "type": "lovelace/config/save",
            "url_path": "tab-1",
            "config": {"views": []},
        }
    )
    assert (await client.receive_json())["success"]
    await hass.async_block_till_done()
    assert keeper.stored == {}


# ---------------------------------------------------------------- card/facts


async def test_card_facts_for_the_15_kelvin_lamp(
    hass: HomeAssistant,
    builtin_light: Path,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_storage: dict[str, Any],
) -> None:
    """card/facts answers for the owner's lamp and writes nothing (C.7)."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "light",
        "test",
        "h1401",
        suggested_object_id="h1401",
        capabilities={
            "supported_color_modes": ["color_temp", "hs"],
            "min_color_temp_kelvin": 15,
            "max_color_temp_kelvin": 6535,
        },
    )
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "apollo_tab/card/facts",
            "component": "apollo/light",
            "params": {"entity": "light.h1401"},
        }
    )
    response = await client.receive_json()
    assert response["success"], response
    can = response["result"]["can"]
    assert {
        key: can[key]
        for key in (
            "brightness",
            "colour",
            "temperature",
            "effects",
            "min_kelvin",
            "max_kelvin",
            "effect_list",
            "icon",
        )
    } == {
        "brightness": True,
        "colour": True,
        "temperature": True,
        "effects": False,
        "min_kelvin": 2000,
        "max_kelvin": 6500,
        "effect_list": [],
        "icon": "mdi:lightbulb",
    }
    assert response["result"]["has"] == {"entity": True}
    # Without a device: no facts, has false.
    await client.send_json_auto_id(
        {"type": "apollo_tab/card/facts", "component": "apollo/light"}
    )
    response = await client.receive_json()
    assert response["result"] == {"can": {}, "has": {"entity": False}}
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done()
    assert "apollo_tab.facts" not in hass_storage
    assert config_entry.runtime_data.facts.stored == {}


async def test_card_facts_refusals(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_read_only_access_token: str,
    user_components: Callable[[str, str], Path],
) -> None:
    """Unknown cards and params are refused; it is for admins only."""
    user_components("dimmer.yaml", DIMMER)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    for message, code in (
        ({"component": "me/nothing"}, "not_found"),
        ({"component": "me/dimmer", "params": {"other": "light.a"}}, "invalid_format"),
        (
            {
                "component": "me/dimmer",
                "params": {"entity": [f"light.l{n}" for n in range(65)]},
            },
            "invalid_format",
        ),
    ):
        await client.send_json_auto_id({"type": "apollo_tab/card/facts", **message})
        response = await client.receive_json()
        assert not response["success"], message
        assert response["error"]["code"] == code, message
    reader = await hass_ws_client(hass, hass_read_only_access_token)
    await reader.send_json_auto_id(
        {"type": "apollo_tab/card/facts", "component": "me/dimmer"}
    )
    response = await reader.receive_json()
    assert response["error"]["code"] == "unauthorized"


async def test_card_facts_keeps_device_names_as_data(
    hass: HomeAssistant,
    builtin_light: Path,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """An effect named like a template comes back as that very text."""
    hostile = "{{ states('alarm_control_panel.home') }}"
    _set_lamp(hass, effect_list=[hostile, "x" * 60])
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "apollo_tab/card/facts",
            "component": "apollo/light",
            "params": {"entity": "light.h1401"},
        }
    )
    response = await client.receive_json()
    assert response["result"]["can"]["effect_list"] == [hostile, "x" * 60]


async def test_subscribe_and_preview_write_no_store(
    hass: HomeAssistant,
    builtin_light: Path,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    hass_storage: dict[str, Any],
) -> None:
    """card/subscribe and a preview read facts but never store them."""
    _set_lamp(hass)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "apollo_tab/card/subscribe",
            "card": {
                "type": "custom:apollo-tab-card",
                "component": "apollo/light",
                "params": {"entity": "light.h1401"},
            },
        }
    )
    assert (await client.receive_json())["success"]
    await client.send_json_auto_id(
        {"type": "apollo_tab/layout/preview", "config": _dashboard("apollo/light")}
    )
    response = await client.receive_json()
    while response.get("type") == "event":
        response = await client.receive_json()
    assert response["success"], response
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done()
    assert "apollo_tab.facts" not in hass_storage
    assert config_entry.runtime_data.facts.stored == {}
