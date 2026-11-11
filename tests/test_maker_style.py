"""Tests for the maker style helpers."""

import json
import re
from pathlib import Path

from custom_components.apollo_tab.maker.const import THEME_IDS
from custom_components.apollo_tab.maker.schema import validate_style
from custom_components.apollo_tab.maker.style import blend, contrast, resolve_style

THEMES_PATH = (
    Path(__file__).parent.parent
    / "custom_components"
    / "apollo_tab"
    / "library"
    / "themes.json"
)

HEX_RE = re.compile(r"^#[0-9A-F]{6}$")


def _themes():
    """Load the theme file into an id-to-tokens mapping."""
    data = json.loads(THEMES_PATH.read_text(encoding="utf-8"))
    return {entry["id"]: entry for entry in data}


def test_empty_style_returns_theme_tokens():
    """Return the theme's own tokens for an empty style."""
    themes = _themes()
    for theme_id in THEME_IDS:
        theme = themes[theme_id]
        out = resolve_style(theme, {}, theme["wall"])
        assert out["bg"] == theme["card"]
        assert out["tx"] == theme["tx"]
        assert out["tx2"] == theme["tx2"]
        assert out["acc"] == theme["acc"]
        assert out["acc2"] == theme["acc2"]
        assert out["acct"] == theme["acct"]
        assert out["card2"] == theme["card2"]
        assert out["line"] == theme["line"]
        assert out["onbg"] == theme["onbg"]
        assert out["ontx"] == theme["ontx"]
        assert out["r"] == theme["r"]
        assert out["r2"] == theme["r2"]
        assert out["bw"] == theme["bw"]
        assert "bg2" not in out


def test_transparency_blends_with_wall():
    """Blend the card fill towards the wall as transparency rises."""
    theme = _themes()["midnight"]
    wall = theme["wall"]
    for pct in (0, 50, 100):
        out = resolve_style(theme, {"transparency": pct}, wall)
        assert out["bg"] == blend(theme["card"], wall, pct / 100)
    solid = resolve_style(theme, {"transparency": 0}, wall)
    assert solid["bg"] == theme["card"]
    ghost = resolve_style(theme, {"transparency": 100}, wall)
    assert ghost["bg"] == wall


def test_text_stays_readable_on_custom_colour():
    """Fall back to dark readable text on a white card."""
    theme = _themes()["midnight"]
    out = resolve_style(theme, {"color": "#FFFFFF"}, theme["wall"])
    assert out["bg"] == "#FFFFFF"
    assert out["tx"] == "#15181D"
    assert contrast(out["tx"], out["bg"]) >= 4.5


def test_accent_override():
    """Replace the theme accent and pick readable accent text."""
    theme = _themes()["midnight"]
    style = validate_style({"accent": "#ffb300"})
    out = resolve_style(theme, style, theme["wall"])
    assert out["acc"] == "#FFB300"
    assert out["acct"] in ("#FFFFFF", "#15181D")
    assert contrast(out["acct"], out["acc"]) >= 3.0
    assert out["onbg"] == blend("#FFB300", theme["card"], 0.80)


def test_gradient_keys():
    """Add bg2 and a direction code when a gradient is set."""
    theme = _themes()["midnight"]
    style = validate_style({"gradient": {"to": "#101820", "direction": "horizontal"}})
    out = resolve_style(theme, style, theme["wall"])
    assert out["bg2"] == "#101820"
    assert out["gd"] == "h"
    style = validate_style({"gradient": {"to": "#101820"}})
    out = resolve_style(theme, style, theme["wall"])
    assert out["bg2"] == "#101820"
    assert out["gd"] == "v"


def test_output_is_opaque_hex_only():
    """Emit only upper-case #RRGGBB colour strings."""
    theme = _themes()["midnight"]
    styles = [
        {},
        {"transparency": 40},
        {"color": "#203040"},
        {"gradient": {"to": "#101820", "direction": "horizontal"}},
        {"accent": "#FFB300"},
    ]
    for style in styles:
        out = resolve_style(theme, style, theme["wall"])
        for key, value in out.items():
            if key == "gd" or not isinstance(value, str):
                continue
            assert HEX_RE.match(value), f"{key}={value}"


def test_theme_ids_match_themes_file():
    """Match THEME_IDS to the themes file."""
    themes = _themes()
    assert len(THEME_IDS) == 6
    assert set(themes) == set(THEME_IDS)
