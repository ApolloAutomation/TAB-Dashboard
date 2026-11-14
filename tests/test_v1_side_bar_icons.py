"""Side bar and heading icons in a layout v1 (coordinator's decision 12, I13).

Engine 0.1.0 holds the icons of level 1 and draws the fallback glyph for
any other (contract 4.5). So in a layout v1 a side bar icon above level 1
is left out, and the tablet draws the icon a page without one gets; a
heading's icon above level 1 is left out. Never the fallback code point.
A layout v2 keeps them: engine 0.2.0 holds level 2.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.apollo_tab.maker import device
from custom_components.apollo_tab.maker.convert import convert_dashboard

from .test_contract import FIX, ICONS, library, load

__all__ = ["library"]  # the fixture of the version 1 fixtures

LEVEL = {name: level for name, (_code, level) in ICONS["icons"].items()}
HIGH = "mdi:air-conditioner"
LOW = "mdi:account"
FALLBACK = ICONS["icons"][ICONS["fallback"]][0]
LIBRARY = Path(__file__).resolve().parent.parent / "custom_components" / "apollo_tab"


def test_the_two_icons_are_of_the_levels_the_tests_need() -> None:
    """One icon of level 2 and one of level 1, neither of them the fallback."""
    assert LEVEL[HIGH] == 2
    assert LEVEL[LOW] == 1
    assert FALLBACK not in (ICONS["icons"][HIGH][0], ICONS["icons"][LOW][0])


def _codes(value: object) -> list[int]:
    """Return every icon code point of a device layout, at any depth."""
    if isinstance(value, list):
        return [code for entry in value for code in _codes(entry)]
    if not isinstance(value, dict):
        return []
    found = [value["icon"]] if isinstance(value.get("icon"), int) else []
    return found + [code for entry in value.values() for code in _codes(entry)]


def _dashboard() -> dict:
    """Return two views, each with a heading card, one of each icon level."""

    def view(path: str, icon: str) -> dict:
        return {
            "type": "sections",
            "path": path,
            "title": path.title(),
            "icon": icon,
            "sections": [
                {
                    "type": "grid",
                    "cards": [{"type": "heading", "heading": "Top", "icon": icon}],
                }
            ],
        }

    return {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [view("cool", HIGH), view("people", LOW)],
    }


def _convert(dl: int, icons: dict | None = ICONS) -> dict:
    """Convert the dashboard without any card file."""
    themes = json.loads((LIBRARY / "library" / "themes.json").read_text("utf-8"))
    return convert_dashboard(
        _dashboard(),
        components={},
        themes={theme["id"]: theme for theme in themes},
        approved=set(),
        dl=dl,
        icons=icons,
    )["layout"]


def _headings(layout: dict) -> list[dict]:
    """Return every heading of every page, in order."""
    return [item for page in layout["pages"] for item in page["w"]]


def test_a_layout_v1_leaves_out_icons_above_level_1() -> None:
    """The side bar entry and the heading lose the level 2 icon only."""
    layout = _convert(1)
    assert [entry.get("icon") for entry in layout["nav"]] == [None, LOW]
    assert "icon" not in layout["nav"][0]
    assert [item.get("icon") for item in _headings(layout)] == [None, LOW]
    assert [item["text"] for item in _headings(layout)] == ["Top", "Top"]
    # The page keeps the person's pick; only what the tablet draws changes.
    assert [page.get("icon") for page in layout["pages"]] == [HIGH, LOW]


def test_a_layout_v1_holds_no_fallback_code_point() -> None:
    """The device layout of version 1 never carries the question mark glyph."""
    data = json.loads(device.compile_device_layout(_convert(1), ICONS)["bytes"])
    assert FALLBACK not in _codes(data)
    assert "icon" not in data["nav"][0]
    assert data["nav"][1]["icon"] == ICONS["icons"][LOW][0]
    assert _codes(data) == [ICONS["icons"][LOW][0]] * 2
    # Kept, the level 2 icons would be the fallback on engine 0.1.0.
    kept = device.compile_device_layout(_convert(1, icons=None), ICONS)
    assert _codes(json.loads(kept["bytes"])).count(FALLBACK) == 2


def test_a_layout_v2_keeps_icons_of_level_2() -> None:
    """Engine 0.2.0 holds level 2, so the version 2 layout keeps them."""
    layout = _convert(2)
    assert [entry.get("icon") for entry in layout["nav"]] == [HIGH, LOW]
    assert [item.get("icon") for item in _headings(layout)] == [HIGH, LOW]


@pytest.mark.parametrize(
    "name", ["layout_small", "layout_all_cards", "layout_all_cards.nochart"]
)
def test_the_version_1_fixtures_keep_their_bytes_with_the_icon_set(
    name: str, library
) -> None:
    """The three version 1 fixtures convert to the same bytes with icons given."""
    components, themes = library
    source = load(f"{name.split('.')[0]}.source.json")
    result = convert_dashboard(
        source["dashboard"],
        components=components,
        themes=themes,
        approved=set(),
        icons=ICONS,
    )
    assert result["layout"] == source["layout"]
    caps = None
    if name.endswith("nochart"):
        caps = load(f"{name}.meta.json")["caps"]
    compiled = device.compile_device_layout(result["layout"], ICONS, caps)
    assert compiled["bytes"] == (FIX / f"{name}.dl.json").read_bytes()
