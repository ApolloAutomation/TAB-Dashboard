"""The sender picks the layout version per tablet (cards spec C.4, C.5; I5)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.apollo_tab import library as library_module
from custom_components.apollo_tab.sender import STATUS_ON_TABLET

from .conftest import MakeTablet, SaveTabDashboard, setup_integration, until
from .fake_tablet import ENGINE_V2
from .test_tablet_input import MAC, tab_config

HERE = Path(__file__).resolve().parent
LIGHT = (HERE / "cards2" / "light.yaml").read_text(encoding="utf-8")
LAMP = "light.h1401"
CARD = {
    "type": "custom:apollo-tab-card",
    "component": "apollo/light",
    "params": {"entity": LAMP},
}


@pytest.fixture
def builtin_light(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Serve the built-in files plus the colour light of D.1 as built-ins."""
    folder = tmp_path / "builtin"
    shutil.copytree(library_module._BUILTIN_DIR, folder)
    (folder / "components" / "apollo-light.yaml").write_text(LIGHT, encoding="utf-8")
    monkeypatch.setattr(library_module, "_BUILTIN_DIR", folder)
    return folder


def _lamp(hass: HomeAssistant) -> None:
    """Put the owner's colour lamp into the state machine."""
    hass.states.async_set(
        LAMP,
        "on",
        {
            "friendly_name": "Sofa lamp",
            "supported_color_modes": ["hs", "color_temp"],
            "color_mode": "hs",
            "brightness": 128,
            "hs_color": [30, 50],
            "min_color_temp_kelvin": 2000,
            "max_color_temp_kelvin": 6500,
        },
    )


async def _on_tablet(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    **tablet: Any,
) -> tuple[Any, Any]:
    """Send a dashboard with the colour light to one tablet."""
    _lamp(hass)
    fake = make_tablet(**tablet)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(CARD))
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    return fake, session


@pytest.mark.usefixtures("builtin_light")
async def test_a_tablet_that_speaks_2_gets_a_layout_v2_with_the_detail_page(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Engine 0.2.0: the colour light, and its controls on a detail page."""
    fake, session = await _on_tablet(
        hass, config_entry, make_tablet, save_tab_dashboard, engine=ENGINE_V2
    )
    assert session.dl == 2
    layout = session.want.layout
    assert layout["v"] == 2
    assert [page["id"] for page in layout["pages"]] == ["home", "home~1"]
    card = layout["pages"][0]["w"][0]
    assert card["component"] == "apollo/light"
    assert fake.active == session.want.hash
    assert session.simpler == 0
    assert session.not_kept is False
    # The stored layout, which the editor reads, is still the version 1 one.
    manager = config_entry.runtime_data.manager
    assert manager.layouts["tab-home"]["layout"]["v"] == 1
    # The version 2 layout is made once and kept for the next look.
    assert manager.layout_for("tab-home", 2, session.caps) is manager.layout_for(
        "tab-home", 2, session.caps
    )


@pytest.mark.usefixtures("builtin_light")
async def test_a_tablet_that_speaks_1_gets_the_version_1_form(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Engine 0.1.0: the tile's old card, and the card counts as shown simpler."""
    fake, session = await _on_tablet(
        hass, config_entry, make_tablet, save_tab_dashboard
    )
    assert session.dl == 1
    layout = session.want.layout
    assert layout["v"] == 1
    assert [page["id"] for page in layout["pages"]] == ["home"]
    assert layout["pages"][0]["w"][0]["component"] == "apollo/light-tile"
    assert fake.active == session.want.hash
    assert session.simpler == 1


@pytest.mark.usefixtures("builtin_light")
async def test_the_version_2_layout_is_made_again_after_a_conversion(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A new conversion drops the kept version 2 layout; the tablet follows."""
    fake, session = await _on_tablet(
        hass, config_entry, make_tablet, save_tab_dashboard, engine=ENGINE_V2
    )
    first = session.want.hash
    await save_tab_dashboard("tab-home", tab_config(CARD, CARD))
    await until(
        hass,
        lambda: session.status == STATUS_ON_TABLET and session.want.hash != first,
    )
    layout = session.want.layout
    assert layout["v"] == 2
    assert sum(1 for item in layout["pages"][0]["w"] if item["t"] == "card") == 2
    assert fake.active == session.want.hash


@pytest.mark.usefixtures("builtin_light")
async def test_a_tablet_that_keeps_less_hears_not_kept(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """A layout above the tablet's max_stored is sent, and marked not kept."""
    _lamp(hass)
    fake = make_tablet(engine=ENGINE_V2)
    fake.caps["max_stored"] = 100
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(CARD))
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert session.not_kept is True
    assert fake.active == session.want.hash
    stored = config_entry.runtime_data.manager.layout_for("tab-home", 2, session.caps)
    assert "not_kept" in [warning["code"] for warning in stored["warnings"]]


@pytest.mark.usefixtures("builtin_light")
async def test_the_preview_makes_either_version(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """apollo_tab/layout/preview takes dl; 1 stays the default."""
    _lamp(hass)
    await setup_integration(hass, config_entry)
    client = await hass_ws_client(hass)
    for dl, pages in ((None, ["home"]), (1, ["home"]), (2, ["home", "home~1"])):
        message: dict[str, Any] = {
            "type": "apollo_tab/layout/preview",
            "config": tab_config(CARD),
        }
        if dl is not None:
            message["dl"] = dl
        await client.send_json_auto_id(message)
        response = await client.receive_json()
        assert response["success"], response
        layout = response["result"]["layout"]
        assert layout["v"] == (dl or 1)
        assert [page["id"] for page in layout["pages"]] == pages
    await client.send_json_auto_id(
        {"type": "apollo_tab/layout/preview", "config": tab_config(CARD), "dl": 3}
    )
    assert not (await client.receive_json())["success"]
