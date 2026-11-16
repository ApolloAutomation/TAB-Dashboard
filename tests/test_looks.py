"""Looks and themes in a layout (cards spec E; package I12)."""

from __future__ import annotations

import copy
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apollo_tab.library import Library
from custom_components.apollo_tab.maker import device
from custom_components.apollo_tab.maker.convert import convert_dashboard
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.schema import validate_component
from custom_components.apollo_tab.maker.style import with_accent

from .conftest import setup_integration

HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parent / "custom_components" / "apollo_tab" / "library"
THEMES = {
    entry["id"]: entry
    for entry in json.loads((LIBRARY / "themes.json").read_text(encoding="utf-8"))
}
STATUS = json.loads((LIBRARY / "status.json").read_text(encoding="utf-8"))
ICONS = json.loads((HERE / "contract" / "icons.json").read_text(encoding="utf-8"))
ACCENT = "#2F7FD0"


def _load_library() -> dict[str, dict]:
    """Load every built-in file as the library does, marked built in."""
    components = {}
    for path in sorted((LIBRARY / "components").glob("*.yaml")):
        component = validate_component(yaml.safe_load(path.read_text("utf-8")))
        component["source"] = "builtin"
        components[component["id"]] = component
    return components


COMPONENTS = _load_library()
FACTS = {"sensor.co2": facts_of({"domain": "sensor"})}
# A reading whose tint is a role name a template gives: the card carries
# its table of roles, and Home Assistant turns the name into the number.
READING = {
    "type": "custom:apollo-tab-card",
    "component": "apollo/reading",
    "params": {"entity": "sensor.co2"},
    "options": {"highlight": "above"},
    "variant": "tile",
}
LIGHT_TILE = {
    "type": "custom:apollo-tab-card",
    "component": "apollo/light-tile",
    "params": {"entity": "light.kitchen"},
}


def _view(path: str, cards: list[dict], theme: str | None = None) -> dict:
    """Return a sections view of one grid section."""
    view: dict[str, Any] = {
        "type": "sections",
        "path": path,
        "title": path.title(),
        "max_columns": 3,
        "sections": [{"type": "grid", "cards": cards}],
    }
    if theme is not None:
        view["apollo_tab"] = {"theme": theme}
    return view


def _dashboard(*views: dict, theme: str = "midnight", **options: Any) -> dict:
    """Return a dashboard with these views."""
    return {
        "apollo_tab": {"version": 1, "theme": theme, **options},
        "views": list(views),
    }


def _convert(config: dict, dl: int = 2, status: dict | None = STATUS) -> dict:
    """Convert with the whole built-in library."""
    return convert_dashboard(
        config,
        components=COMPONENTS,
        themes=THEMES,
        approved=set(),
        facts=FACTS,
        dl=dl,
        icons=ICONS,
        status=status,
    )


def _cards(layout: dict, page: int | None = None) -> list[dict]:
    """Return the cards of a layout, or of one of its pages."""
    pages = layout["pages"] if page is None else [layout["pages"][page]]
    return [w for p in pages for w in p["w"] if w["t"] == "card"]


def _roles(card: dict) -> dict:
    """Return the table of roles the card's tint carries."""
    return card["tint"]["roles"]


# ------------------------------------------------------------- the accent


def test_a_dashboard_accent_goes_into_the_layout_theme() -> None:
    """Both versions carry the theme with the accent; its id stays."""
    config = _dashboard(_view("home", [LIGHT_TILE]), theme="nord", accent=ACCENT)
    want = {"id": "nord", **with_accent(THEMES["nord"], ACCENT)}
    for dl in (1, 2):
        result = _convert(config, dl)
        assert result["warnings"] == []
        assert result["layout"]["theme"] == want
        dev = json.loads(device.compile_device_layout(result["layout"], ICONS)["bytes"])
        assert dev["v"] == dl
        assert dev["theme"]["acc"] == dev["theme"]["accf"] == 0x2F7FD0
        assert dev["theme"]["ion"] == 0x2F7FD0
    plain = _convert(_dashboard(_view("home", [LIGHT_TILE]), theme="nord"), 1)
    assert plain["layout"]["theme"] == {"id": "nord", **THEMES["nord"]}


def test_a_bad_accent_falls_back_to_the_default_options() -> None:
    """A colour that is not #RRGGBB makes the options invalid, as a bad theme."""
    result = _convert(_dashboard(_view("home", [LIGHT_TILE]), accent="blue"), 1)
    assert [w["code"] for w in result["warnings"]] == ["invalid_options"]
    assert result["layout"]["theme"] == {"id": "midnight", **THEMES["midnight"]}


def test_a_styled_card_is_resolved_against_the_accent() -> None:
    """A card style on the dashboard's theme takes the accent's colours."""
    card = {**LIGHT_TILE, "style": {"transparency": 20}}
    result = _convert(_dashboard(_view("home", [card]), accent=ACCENT), 1)
    [item] = _cards(result["layout"])
    assert item["style"]["acc"] == ACCENT
    named = {**LIGHT_TILE, "style": {"theme": "midnight", "transparency": 20}}
    result = _convert(_dashboard(_view("home", [named]), accent=ACCENT), 1)
    [item] = _cards(result["layout"])
    # A theme the card names is that theme as it is.
    assert item["style"]["acc"] == THEMES["midnight"]["acc"]


def test_the_accent_is_a_role_of_schema_2_cards() -> None:
    """The role `accent` of a card on the dashboard's theme is the accent."""
    result = _convert(_dashboard(_view("home", [READING]), accent=ACCENT))
    [card] = _cards(result["layout"])
    assert _roles(card)["accent"] == ACCENT


def test_a_page_of_the_dashboard_s_own_theme_keeps_the_accent() -> None:
    """A view naming the dashboard's theme gets it with the accent; others not."""
    config = _dashboard(
        _view("home", [LIGHT_TILE], theme="midnight"),
        _view("bed", [LIGHT_TILE], theme="night"),
        accent=ACCENT,
    )
    layout = _convert(config)["layout"]
    assert layout["pages"][0]["theme"]["acc"] == ACCENT
    assert layout["pages"][0]["theme"]["id"] == "midnight"
    assert layout["pages"][1]["theme"] == {"id": "night", **THEMES["night"]}


# ------------------------------------------------------------- page theme


def test_a_card_on_a_themed_page_sits_on_that_page_s_wall() -> None:
    """See-through and the plain surface use the page's wall in layout v2."""
    see_through = {**LIGHT_TILE, "style": {"transparency": 100}}
    plain = {**LIGHT_TILE, "style": {"surface": "plain"}}
    config = _dashboard(_view("home", [see_through, plain], theme="paper"))
    for card in _cards(_convert(config)["layout"]):
        assert card["style"]["bg"] == THEMES["paper"]["wall"]
    # Version 1 has no page themes: the layout's wall.
    for card in _cards(_convert(config, 1)["layout"]):
        assert card["style"]["bg"] == THEMES["midnight"]["wall"]


def test_a_page_theme_is_left_out_of_version_1() -> None:
    """Layout v1 has no page theme, and its cards no lit or tint."""
    card = {**READING, "style": {"lit": "outline", "tint": False}}
    config = _dashboard(_view("home", [card], theme="paper"))
    v2 = _convert(config)["layout"]
    assert v2["pages"][0]["theme"]["id"] == "paper"
    [item] = _cards(v2)
    assert item["lit"] == 2
    assert "tint" not in item
    v1 = _convert(config, 1)["layout"]
    assert "theme" not in v1["pages"][0]
    for item in _cards(v1):
        assert "lit" not in item and "tint" not in item


# ------------------------------------------------------------- status


def test_status_roles_follow_the_card_s_theme() -> None:
    """good, warn, bad and info of status.json: by flag, or the theme's own."""
    for theme_id, table in (
        ("midnight", STATUS["dark"]),
        ("paper", STATUS["light"]),
        ("night", STATUS["themes"]["night"]),
    ):
        result = _convert(_dashboard(_view("home", [READING]), theme=theme_id))
        [card] = _cards(result["layout"])
        for role in ("good", "warn", "bad", "info"):
            assert _roles(card)[role] == table[role], (theme_id, role)
        assert _roles(card)["accent"] == THEMES[theme_id]["acc"]


def test_status_roles_on_a_themed_page_and_a_styled_card() -> None:
    """The page's theme, else the theme the card's style names, decides."""
    styled = {**READING, "style": {"theme": "night"}}
    config = _dashboard(
        _view("home", [READING], theme="paper"),
        _view("other", [styled]),
    )
    layout = _convert(config)["layout"]
    [on_paper] = _cards(layout, 0)
    [on_night] = _cards(layout, 1)
    assert _roles(on_paper)["warn"] == STATUS["light"]["warn"]
    assert _roles(on_night)["warn"] == STATUS["themes"]["night"]["warn"]
    # A page of a theme that status.json names takes that theme's own.
    night_page = _dashboard(_view("bed", [READING], theme="night"))
    [card] = _cards(_convert(night_page)["layout"])
    assert _roles(card)["warn"] == STATUS["themes"]["night"]["warn"]


def test_without_status_the_dark_colours_stand() -> None:
    """A caller that hands no status table gets the colours of a dark theme."""
    result = _convert(_dashboard(_view("home", [READING]), theme="paper"), status=None)
    [card] = _cards(result["layout"])
    assert _roles(card)["warn"] == STATUS["dark"]["warn"]


def test_status_colours_reach_the_device_layout() -> None:
    """The role table of a colour slot becomes numbers in the slot plan."""
    result = _convert(_dashboard(_view("home", [READING]), theme="paper"))
    slots = device.compile_device_layout(result["layout"], ICONS)["slots"]
    [plan] = [slot for slot in slots if slot.get("coerce") == "colour"]
    for role in ("good", "warn", "bad", "info"):
        assert plan["roles"][role] == int(STATUS["light"][role][1:], 16)


# ------------------------------------------------------------- card looks


def test_a_style_of_only_lit_and_tint_paints_nothing() -> None:
    """A schema 1 card takes the new keys; lit and tint alone make no style."""
    card = {**LIGHT_TILE, "style": {"lit": "icon", "tint": False}}
    result = _convert(_dashboard(_view("home", [card])), 1)
    assert result["warnings"] == []
    [item] = _cards(result["layout"])
    assert "style" not in item


def test_surface_corners_and_border_work_in_version_1() -> None:
    """Version 1 styles carry bg, line, r, r2 and bw."""
    card = {
        **LIGHT_TILE,
        "style": {"surface": "outline", "corners": "square", "border": "bold"},
    }
    result = _convert(_dashboard(_view("home", [card]), theme="paper"), 1)
    dev = json.loads(device.compile_device_layout(result["layout"], ICONS)["bytes"])
    [item] = [w for w in dev["pages"][0]["w"] if w["t"] == "card"]
    paper = THEMES["paper"]
    assert item["style"]["bg"] == int(paper["wall"][1:], 16)
    assert item["style"]["line"] == int(paper["line"][1:], 16)
    assert (item["style"]["r"], item["style"]["r2"], item["style"]["bw"]) == (4, 2, 2)


def test_a_bad_look_makes_the_card_invalid() -> None:
    """A word that is not on the list is an invalid card, as a bad colour is."""
    card = {**LIGHT_TILE, "style": {"corners": "pointy"}}
    result = _convert(_dashboard(_view("home", [card])), 1)
    assert [w["code"] for w in result["warnings"]] == ["invalid_card"]


def test_the_theme_s_own_look_changes_no_byte() -> None:
    """The theme's own surface, corners and border give the unstyled layout."""
    own = {
        **LIGHT_TILE,
        "style": {"surface": "card", "corners": "theme", "border": "theme"},
    }
    plain = _convert(_dashboard(_view("home", [LIGHT_TILE])), 1)
    same = _convert(_dashboard(_view("home", [own])), 1)
    assert same["layout"] == plain["layout"]


# ------------------------------------------------------------- the library


async def test_the_library_hands_out_the_status_colours(hass: HomeAssistant) -> None:
    """status.json is read with the themes and is part of the panel's data."""
    library = Library(hass)
    await library.async_load()
    assert library.status == STATUS
    listing = library.as_dict()
    assert listing["status"] == STATUS
    assert [theme["id"] for theme in listing["themes"]] == list(THEMES)


async def test_the_manager_converts_with_the_status_colours(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    tab_dashboard: Callable[..., Awaitable[Any]],
) -> None:
    """Saved and previewed dashboards both use the library's status table."""
    await setup_integration(hass, config_entry)
    config = _dashboard(_view("home", [READING]), theme="paper")
    await tab_dashboard(copy.deepcopy(config))
    await hass.async_block_till_done()
    manager = config_entry.runtime_data.manager
    entry = manager.layout_for("tab-1", 2)
    [card] = _cards(entry["layout"])
    assert _roles(card)["warn"] == STATUS["light"]["warn"]
    preview = await manager.async_preview(copy.deepcopy(config), dl=2)
    [card] = _cards(preview["layout"])
    assert _roles(card)["warn"] == STATUS["light"]["warn"]


# ------------------------------------------------------------- writer checks


def test_the_version_2_writer_checks_theme_and_style_values() -> None:
    """A page theme or a card style the contract does not take is ContractError."""
    styled = {**LIGHT_TILE, "style": {"corners": "soft"}}
    config = _dashboard(_view("home", [styled], theme="paper"))
    layout = _convert(config)["layout"]
    device.compile_device_layout(layout, ICONS)
    for change in (
        lambda lay: lay["pages"][0]["theme"].update(acc="red"),
        lambda lay: lay["pages"][0]["theme"].update(r=14.5),
        lambda lay: lay["theme"].update(card=None),
        lambda lay: lay["theme"].update(bw=True),
        lambda lay: _cards(lay)[0]["style"].update(bg="#12345"),
        lambda lay: _cards(lay)[0]["style"].update(r="28"),
    ):
        broken = copy.deepcopy(layout)
        change(broken)
        with pytest.raises(device.ContractError):
            device.compile_device_layout(broken, ICONS)
