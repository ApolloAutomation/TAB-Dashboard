"""What the tablets list says about each tablet's layout (cards spec C.5; I13).

`apollo_tab/tablets` reports per tablet how many cards it shows simpler
(a version 1 form or the update note, because its software is older), how
many widgets are left out because it cannot draw their kind, and whether
its layout is too big to be kept when it restarts.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.apollo_tab.maker import device
from custom_components.apollo_tab.sender import STATUS_NO_DASHBOARD, STATUS_ON_TABLET

from .conftest import MakeTablet, SaveTabDashboard, setup_integration, until
from .fake_tablet import ENGINE_V2
from .test_sender_versions import CARD, _lamp
from .test_tablet_input import MAC, tab_config
from .test_tablet_shapes import check_tablet

SLIDER = {
    "type": "custom:apollo-tab-card",
    "component": "apollo/light-slider",
    "params": {"entity": "light.kitchen"},
}


async def _tablets(hass: HomeAssistant, hass_ws_client: WebSocketGenerator) -> dict:
    """Return the one tablet of apollo_tab/tablets, checked against the shapes."""
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "apollo_tab/tablets"})
    response = await client.receive_json()
    assert response["success"], response
    [tablet] = response["result"]["tablets"]
    check_tablet("tablet", tablet)
    return tablet


async def _show(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    *cards: dict,
    **tablet: Any,
) -> tuple[Any, Any]:
    """Send a dashboard with these cards to one tablet; return it and its session."""
    _lamp(hass)
    hass.states.async_set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    fake = make_tablet(**tablet)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(*cards))
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    return fake, session


async def test_an_older_tablet_says_how_many_cards_it_shows_simpler(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Engine 0.1.0: each new card is shown simpler; old cards are not counted."""
    _fake, session = await _show(
        hass, config_entry, make_tablet, save_tab_dashboard, CARD, CARD, SLIDER
    )
    assert session.dl == 1
    tablet = await _tablets(hass, hass_ws_client)
    assert (tablet["simpler"], tablet["dropped"], tablet["not_kept"]) == (2, 0, False)


async def test_a_newer_tablet_shows_no_card_simpler(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Engine 0.2.0 draws the new cards themselves."""
    _fake, session = await _show(
        hass,
        config_entry,
        make_tablet,
        save_tab_dashboard,
        CARD,
        CARD,
        engine=ENGINE_V2,
    )
    assert session.dl == 2
    tablet = await _tablets(hass, hass_ws_client)
    assert (tablet["simpler"], tablet["dropped"], tablet["not_kept"]) == (0, 0, False)


async def test_a_layout_too_big_to_keep_is_reported(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Above the tablet's caps.max_stored the layout is sent, and not_kept says so."""
    fake, session = await _show(
        hass,
        config_entry,
        make_tablet,
        save_tab_dashboard,
        CARD,
        engine=ENGINE_V2,
        caps={"max_stored": 100},
    )
    assert fake.active == session.want.hash
    assert len(session.want.data) > 100
    tablet = await _tablets(hass, hass_ws_client)
    assert tablet["not_kept"] is True


async def test_a_layout_of_exactly_max_stored_is_kept(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Only a layout above max_stored is not kept."""
    _fake, session = await _show(
        hass, config_entry, make_tablet, save_tab_dashboard, SLIDER
    )
    size = len(session.want.data)
    session.caps = {**session.caps, "max_stored": size}
    session._compile_cache = None
    assert session._compile("tab-home").not_kept is False
    session.caps = {**session.caps, "max_stored": size - 1}
    session._compile_cache = None
    assert session._compile("tab-home").not_kept is True


async def test_widgets_the_tablet_cannot_draw_are_counted(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A tablet without slider in caps.w gets the card without its slider."""
    kinds = [kind for kind in device.WIDGET_KINDS if kind != "slider"]
    _fake, session = await _show(
        hass,
        config_entry,
        make_tablet,
        save_tab_dashboard,
        SLIDER,
        SLIDER,
        caps={"w": kinds},
    )
    sliders = [
        widget
        for page in session.want.layout["pages"]
        for item in page["w"]
        for widget in item.get("w", [])
        if widget.get("t") == "slider"
    ]
    assert len(sliders) == 2
    tablet = await _tablets(hass, hass_ws_client)
    assert (tablet["simpler"], tablet["dropped"], tablet["not_kept"]) == (0, 2, False)


async def test_a_tablet_without_a_dashboard_reports_nothing_left_out(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a dashboard the counts of the layout it had are not reported.

    Also in the moment between losing the dashboard and the run that
    clears the tablet.
    """
    _fake, session = await _show(
        hass, config_entry, make_tablet, save_tab_dashboard, CARD
    )
    sender = config_entry.runtime_data.sender
    assert sender.tablet_json(session)["simpler"] == 1
    with monkeypatch.context() as patch:
        patch.setattr(type(session), "dashboard", property(lambda _self: None))
        assert session.simpler == 1
        tablet = sender.tablet_json(session)
        assert (tablet["simpler"], tablet["dropped"], tablet["not_kept"]) == (
            0,
            0,
            False,
        )

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "lovelace/dashboards/list"})
    items = (await client.receive_json())["result"]
    await client.send_json_auto_id(
        {"type": "lovelace/dashboards/delete", "dashboard_id": items[0]["id"]}
    )
    assert (await client.receive_json())["success"]
    await until(hass, lambda: session.status == STATUS_NO_DASHBOARD)
    assert session.simpler == 0
    tablet = await _tablets(hass, hass_ws_client)
    assert (tablet["simpler"], tablet["dropped"], tablet["not_kept"]) == (0, 0, False)


async def test_the_followers_hear_when_the_counts_change(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A new layout with other counts is sent to apollo_tab/tablets/subscribe.

    Also when the tablet's status stays the same.
    """
    _fake, session = await _show(
        hass, config_entry, make_tablet, save_tab_dashboard, CARD
    )
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "apollo_tab/tablets/subscribe"})
    assert (await client.receive_json())["success"]
    first = await client.receive_json()
    assert first["event"]["tablets"][0]["simpler"] == 1

    session._set_want(dataclasses.replace(session.want, simpler=3))
    event = await client.receive_json()
    assert event["event"]["tablets"][0]["simpler"] == 3
    assert session.status == STATUS_ON_TABLET


@pytest.mark.parametrize(
    ("change", "key", "value"),
    [({"not_kept": True}, "not_kept", True), ({"dropped": 2}, "dropped", 2)],
)
async def test_the_followers_hear_a_change_of_one_count_alone(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    change: dict,
    key: str,
    value: Any,
) -> None:
    """not_kept or dropped changing while simpler stays is sent too."""
    _fake, session = await _show(
        hass, config_entry, make_tablet, save_tab_dashboard, CARD
    )
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "apollo_tab/tablets/subscribe"})
    assert (await client.receive_json())["success"]
    first = await client.receive_json()
    assert first["event"]["tablets"][0][key] != value

    session._set_want(dataclasses.replace(session.want, **change))
    event = await client.receive_json()
    tablet = event["event"]["tablets"][0]
    assert tablet[key] == value
    assert tablet["simpler"] == first["event"]["tablets"][0]["simpler"]
