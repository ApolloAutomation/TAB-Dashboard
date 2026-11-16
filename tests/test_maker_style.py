"""Tests for the maker style helpers."""

import hashlib
import json
import re
from pathlib import Path

import pytest

from custom_components.apollo_tab.maker.const import THEME_IDS
from custom_components.apollo_tab.maker.errors import MakerError
from custom_components.apollo_tab.maker.linear import LINEAR
from custom_components.apollo_tab.maker.schema import (
    validate_dashboard_options,
    validate_style,
)
from custom_components.apollo_tab.maker.style import (
    ENTRY_KEYS,
    INK,
    SEED_KEYS,
    WHITE,
    blend,
    contrast,
    contrast_of,
    derive_theme,
    legible,
    lum,
    mix,
    paints,
    readable,
    resolve_style,
    status_for,
    to_hex,
    to_int,
    with_accent,
)

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
    assert len(THEME_IDS) == 15
    assert set(themes) == set(THEME_IDS)


# ------------------------------------------------ looks and themes (I12)

STATUS_PATH = THEMES_PATH.parent / "status.json"
MATHS = json.loads(
    (Path(__file__).parent / "contract" / "fixtures" / "maths.json").read_text(
        encoding="utf-8"
    )
)
# The canonical JSON of the six entries of apollo_tab 0.4.0. They must not
# change: the layout carries a theme entry whole (cards spec C.1).
SIX_HASH = "82e77d51fe198f6028cb84a7b3ad5af158d978d15418799cc77c188f11e39ab6"
NEW_NINE = (
    "graphite",
    "nord",
    "forest",
    "ocean",
    "night",
    "paper",
    "sand",
    "rose",
    "contrast",
)
# Contrast's "on" fill is its accent with black on it, and its pressed
# colours are set by hand (cards spec E.2).
HAND_SET = {"contrast": ("card_pr", "card2_pr", "onbg", "onbg_pr", "ontx", "ion")}
# The contrast test of E.2: pairs of roles and the least contrast of each.
THEME_PAIRS = (
    ("tx", "card", 7),
    ("tx", "wall", 7),
    ("tx2", "card", 4.5),
    ("tx", "card2", 4.5),
    ("tx", "card2_pr", 4.5),
    ("tx2", "card2", 3),
    ("acc", "card", 3),
    ("acc2", "card", 3),
    ("acc2", "card2", 2.8),
    ("acct", "accf", 4.5),
    ("acct", "accf_pr", 3),
    ("ontx", "onbg", 4.5),
    ("ontx", "onbg_pr", 4.5),
    ("ion", "onbg", 3),
)


def _entries():
    """Load the theme file as a list, in file order."""
    return json.loads(THEMES_PATH.read_text(encoding="utf-8"))


def _c(a: str, b: str) -> float:
    """Return the table contrast of two #RRGGBB colours."""
    return contrast_of(to_int(a), to_int(b))


def test_the_six_old_entries_did_not_change():
    """The first six entries are those of 0.4.0, in their order."""
    six = _entries()[:6]
    text = json.dumps(six, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(text.encode()).hexdigest() == SIX_HASH
    assert [entry["id"] for entry in six] == list(THEME_IDS[:6])


def test_theme_ids_are_the_file_order():
    """THEME_IDS lists the 15 entries in file order, the nine new ones last."""
    assert tuple(entry["id"] for entry in _entries()) == THEME_IDS
    assert THEME_IDS[6:] == NEW_NINE
    for entry in _entries():
        assert tuple(entry) == ENTRY_KEYS, entry["id"]


def test_every_theme_passes_the_contrast_test():
    """All 15 themes pass every pair of E.2, with the table contrast."""
    failures = [
        (entry["id"], a, b, round(_c(entry[a], entry[b]), 2))
        for entry in _entries()
        for a, b, least in THEME_PAIRS
        if _c(entry[a], entry[b]) < least
    ]
    assert failures == []


def test_the_dark_flag_is_what_the_card_colour_says():
    """On every theme `dark` equals readable(card) being white (E.4)."""
    for entry in _entries():
        assert entry["dark"] == (readable(to_int(entry["card"])) == WHITE)


def test_the_nine_new_themes_are_what_the_rule_makes():
    """derive_theme with the whole-number mix gives each entry, role for role."""
    for entry in _entries()[6:]:
        seed = {key: entry[key] for key in SEED_KEYS}
        seed.update({key: entry[key] for key in HAND_SET.get(entry["id"], ())})
        assert derive_theme(seed) == entry, entry["id"]


def test_contrast_keeps_its_hand_set_colours():
    """Without them the rule gives other colours; what the seed holds stays."""
    entry = next(e for e in _entries() if e["id"] == "contrast")
    derived = derive_theme({key: entry[key] for key in SEED_KEYS})
    for key in HAND_SET["contrast"]:
        assert derived[key] != entry[key], key
    assert derived["acct"] == entry["acct"] == "#15181D"
    assert derived["accf_pr"] == entry["accf_pr"]


def _seed(**changes) -> dict:
    """Return a dark seed, Midnight's colours, with some changed."""
    seed = {key: _themes()["midnight"][key] for key in SEED_KEYS}
    seed.update(changes)
    return seed


def test_derive_theme_role_by_role():
    """Each derived role follows its line of the table of E.2."""
    seed = _seed()
    out = derive_theme(seed)
    card, card2, tx, acc = (to_int(seed[k]) for k in ("card", "card2", "tx", "acc"))
    assert out["card_pr"] == seed["card2"]
    assert out["card2_pr"] == to_hex(mix(tx, card2, 90))
    assert out["acct"] == to_hex(readable(acc))
    assert out["accf_pr"] == to_hex(mix(0, to_int(out["accf"]), 88))
    assert out["onbg"] == to_hex(mix(acc, card, 86))
    assert out["onbg_pr"] == to_hex(mix(acc, card, 76))
    light = derive_theme(_seed(dark=False))
    assert light["onbg"] == to_hex(mix(acc, card, 88))
    assert light["onbg_pr"] == to_hex(mix(acc, card, 78))
    assert light["dark"] is False


def test_the_accent_fill_is_darkened_under_white_text():
    """A grey accent with white text on it below 4.5 is mixed toward black."""
    out = derive_theme(_seed(acc="#777777"))
    assert out["acct"] == "#FFFFFF"
    assert _c("#FFFFFF", "#777777") < 4.5
    step = mix(0, 0x777777, 92)
    assert out["accf"] == to_hex(step)
    assert _c(out["acct"], out["accf"]) >= 4.5
    assert out["acc"] == "#777777"


def test_the_accent_fill_is_lightened_under_dark_text():
    """Under 0x15181D the fill is mixed toward white until it has 4.5."""
    out = derive_theme(_seed(acc="#2F7FD0"))
    assert out["acct"] == "#15181D"
    accf = 0x2F7FD0
    while contrast_of(INK, accf) < 4.5:
        accf = mix(WHITE, accf, 92)
    assert accf != 0x2F7FD0
    assert out["accf"] == to_hex(accf)


def test_ontx_falls_back_to_the_text_and_ion_to_ontx():
    """The text stands in for ontx below 4.5 on onbg; ontx for a dim ion."""
    seed = _seed(card="#404040", card2="#4A4A4A", tx="#909090", acc="#00FF00")
    onbg = mix(0x00FF00, 0x404040, 86)
    assert contrast_of(mix(0x00FF00, 0x909090, 70), onbg) < 4.5
    out = derive_theme(seed)
    assert out["ontx"] == "#909090"
    dim = derive_theme(_seed(acc="#303030"))
    assert dim["ion"] == dim["ontx"] != "#303030"
    assert derive_theme(_seed())["ion"] == _themes()["midnight"]["acc"]


def test_the_colour_table_is_the_contract_s():
    """The table `linear` of maker is the fixture's, number for number."""
    assert list(LINEAR) == MATHS["linear"]


def test_mix_lum_contrast_readable_legible_match_maths_json():
    """The five colour functions give every vector of maths.json."""
    for a, b, p, want in MATHS["mix"]:
        assert mix(a, b, p) == want, (a, b, p)
    for weight, pairs in MATHS["mix_halves"].items():
        for a, b, want in pairs:
            assert mix(a, b, int(weight)) == want, (a, b, weight)
    for c, want in MATHS["lum"]:
        assert lum(c) == want, c
    for a, b, want in MATHS["contrast"]:
        assert contrast_of(a, b) == want, (a, b)
    for c, want in MATHS["readable"]:
        assert readable(c) == want, c
    for c, b, t, want in MATHS["legible"]:
        assert legible(c, b, t) == want, (c, b, t)


def test_a_dashboard_accent_sets_its_roles():
    """acc, accf and ion are the colour; the rest follow the rule of E.2."""
    for theme_id in ("midnight", "paper"):
        theme = _themes()[theme_id]
        out = with_accent(theme, "#2F7FD0")
        card, tx = to_int(theme["card"]), to_int(theme["tx"])
        dark = theme["dark"]
        assert out["acc"] == out["accf"] == out["ion"] == "#2F7FD0"
        assert out["acct"] == to_hex(readable(0x2F7FD0))
        assert out["accf_pr"] == to_hex(mix(0, 0x2F7FD0, 88))
        assert out["onbg"] == to_hex(mix(0x2F7FD0, card, 86 if dark else 88))
        assert out["onbg_pr"] == to_hex(mix(0x2F7FD0, card, 76 if dark else 78))
        ontx = mix(0x2F7FD0, tx, 70)
        if contrast_of(ontx, to_int(out["onbg"])) < 4.5:
            ontx = tx
        assert out["ontx"] == to_hex(ontx)
        changed = {key for key in theme if out[key] != theme[key]}
        assert changed <= {
            "acc",
            "accf",
            "accf_pr",
            "acct",
            "ion",
            "onbg",
            "onbg_pr",
            "ontx",
        }
        assert out["id"] == theme_id
    assert _themes()["midnight"]["acc"] == "#F5B547"


def test_status_colours_by_theme():
    """A theme takes dark or light by its flag, unless the file names it."""
    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    assert status_for(status, "midnight", True) == status["dark"]
    assert status_for(status, "paper", False) == status["light"]
    assert status_for(status, "night", True) == status["themes"]["night"]
    assert status_for(None, "midnight", True) == {}
    assert status_for({"dark": {"good": "#4cc38a", "bad": "red"}}, "x", True) == {
        "good": "#4CC38A"
    }


def test_status_colours_stand_out_on_every_card():
    """Each status colour has 3 or more on every theme's card.

    E.3 says 3.5 or more; with the table contrast Glass's `bad` has 3.48,
    the one colour under 3.5. The tablet's `legible` covers it.
    """
    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    under = []
    for entry in _entries():
        for role, value in status_for(status, entry["id"], entry["dark"]).items():
            assert _c(value, entry["card"]) >= 3, (entry["id"], role)
            if _c(value, entry["card"]) < 3.5:
                under.append((entry["id"], role))
    assert under == [("glass", "bad")]
    assert set(status) == {"dark", "light", "themes"}
    for table in [status["dark"], status["light"], *status["themes"].values()]:
        assert set(table) == {"good", "warn", "bad", "info"}


def test_validate_style_takes_the_new_looks():
    """lit, tint, surface, corners and border; the theme's own look is no key."""
    style = validate_style(
        {
            "lit": "outline",
            "tint": False,
            "surface": "plain",
            "corners": "soft",
            "border": "bold",
        }
    )
    assert style == {
        "lit": "outline",
        "tint": False,
        "surface": "plain",
        "corners": "soft",
        "border": "bold",
    }
    own = {"surface": "card", "corners": "theme", "border": "theme"}
    assert validate_style(own) == {}
    for lit in ("fill", "icon", "outline", "none"):
        assert validate_style({"lit": lit}) == {"lit": lit}
    assert validate_style({"surface": "outline"}) == {"surface": "outline"}
    assert validate_style({"border": "none"}) == {"border": "none"}


@pytest.mark.parametrize(
    "style",
    [
        {"lit": "glow"},
        {"lit": 1},
        {"tint": "no"},
        {"tint": 0},
        {"surface": "glass"},
        {"surface": None},
        {"corners": 16},
        {"corners": "pointy"},
        {"border": "thick"},
        {"border": ["thin"]},
        {"shadow": True},
    ],
)
def test_validate_style_refuses_bad_looks(style):
    """A word that is not on the list, or a value of another type, is refused."""
    with pytest.raises(MakerError):
        validate_style(style)


def test_dashboard_options_take_an_accent():
    """apollo_tab.accent is a #RRGGBB colour, kept in upper case."""
    assert validate_dashboard_options({"theme": "nord", "accent": "#2f7fd0"}) == {
        "version": 1,
        "theme": "nord",
        "accent": "#2F7FD0",
    }
    assert validate_dashboard_options({"theme": "rose"}) == {
        "version": 1,
        "theme": "rose",
    }
    for bad in ("blue", "#12345", 0x2F7FD0, None):
        with pytest.raises(MakerError):
            validate_dashboard_options({"accent": bad})


def test_surface_outline_and_plain_put_the_card_on_the_wall():
    """outline: bg wall, bw 2, the theme's line; plain: bg wall, bw 0."""
    theme = _themes()["midnight"]
    outline = resolve_style(theme, {"surface": "outline"}, "#000000")
    assert outline["bg"] == "#000000"
    assert outline["bw"] == 2
    assert outline["line"] == theme["line"]
    assert outline["card2"] == theme["card2"]
    plain = resolve_style(theme, {"surface": "plain"}, theme["wall"])
    assert plain["bg"] == theme["wall"]
    assert plain["bw"] == 0
    # The surface takes the place of a colour, a fade and see-through.
    style = validate_style(
        {
            "surface": "plain",
            "color": "#FFFFFF",
            "transparency": 50,
            "gradient": {"to": "#FF0000"},
        }
    )
    out = resolve_style(theme, style, theme["wall"])
    assert out["bg"] == theme["wall"]
    assert "bg2" not in out and "gd" not in out
    assert out["tx"] == theme["tx"]


def test_a_light_card_on_a_dark_wall_keeps_readable_text():
    """A Daylight card that is plain on Glass's wall gets readable text."""
    daylight = _themes()["daylight"]
    out = resolve_style(daylight, {"surface": "plain"}, "#1A3E62")
    assert out["bg"] == "#1A3E62"
    assert out["tx"] == "#FFFFFF"
    assert contrast(daylight["tx2"], "#1A3E62") < 3.0
    assert contrast(out["tx2"], out["bg"]) >= 3.0
    assert out["tx2"] != daylight["tx2"]


def test_corners_and_border():
    """The radius is the number, r2 round(r * 0.6) halves up; bw by the border."""
    theme = _themes()["midnight"]
    for word, r, r2 in (("square", 4, 2), ("round", 16, 10), ("soft", 28, 17)):
        out = resolve_style(theme, {"corners": word}, theme["wall"])
        assert (out["r"], out["r2"]) == (r, r2)
        assert out["bw"] == theme["bw"]
    for word, bw in (("none", 0), ("thin", 1), ("bold", 2)):
        out = resolve_style(_themes()["warm"], {"border": word}, theme["wall"])
        assert out["bw"] == bw
        assert (out["r"], out["r2"]) == (18, 12)
    # An explicit border wins over the outline's own width.
    out = resolve_style(theme, {"surface": "outline", "border": "thin"}, "#000000")
    assert out["bw"] == 1


def test_lit_and_tint_do_not_paint():
    """The card keys lit and tint alone paint nothing."""
    theme = _themes()["midnight"]
    assert not paints({})
    assert not paints({"lit": "icon", "tint": False})
    assert paints({"lit": "icon", "corners": "soft"})
    assert resolve_style(theme, {"lit": "none", "tint": False}, theme["wall"]) == (
        resolve_style(theme, {}, theme["wall"])
    )
