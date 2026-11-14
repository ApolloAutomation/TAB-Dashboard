"""Colour maths, themes and style resolution for maker elements."""

import re

from .const import BORDERS, CORNERS, OUTLINE_BW, STATUS_ROLES
from .linear import LINEAR

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
# Style keys that change the card's tablet keys (lit, tint), not its paint.
_LOOK_KEYS = ("lit", "tint")


def blend(fg: str, bg: str, t: float) -> str:
    """Mix two colours; t = 0 gives fg, t = 1 gives bg, channels rounded."""
    f_r, f_g, f_b = int(fg[1:3], 16), int(fg[3:5], 16), int(fg[5:7], 16)
    b_r, b_g, b_b = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
    red = round(f_r + (b_r - f_r) * t)
    green = round(f_g + (b_g - f_g) * t)
    blue = round(f_b + (b_b - f_b) * t)
    return f"#{red:02X}{green:02X}{blue:02X}"


def _linear(channel: float) -> float:
    """Return the linear-light value of an sRGB channel in 0..1."""
    if channel <= 0.03928:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _luminance(colour: str) -> float:
    """Return the WCAG relative luminance of a #RRGGBB colour."""
    red = int(colour[1:3], 16) / 255
    green = int(colour[3:5], 16) / 255
    blue = int(colour[5:7], 16) / 255
    return 0.2126 * _linear(red) + 0.7152 * _linear(green) + 0.0722 * _linear(blue)


def contrast(a: str, b: str) -> float:
    """Return the WCAG contrast ratio of two colours, from 1.0 to 21.0."""
    lum_a = _luminance(a)
    lum_b = _luminance(b)
    lighter = max(lum_a, lum_b)
    darker = min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def paints(style: dict) -> bool:
    """Return True when a style changes any colour, radius or border."""
    return any(key not in _LOOK_KEYS for key in style)


def resolve_style(theme: dict, style: dict, wall: str) -> dict:
    """Resolve an element style against a theme into concrete paint tokens.

    wall is the page's wall. The surfaces "outline" and "plain" put the card
    on the wall, so they take the place of a colour, a fade or see-through.
    """
    surfaced = style.get("surface", "card") != "card" and bool(_HEX.match(wall))
    t = 0 if surfaced else style.get("transparency", 0) / 100
    custom = not surfaced and (
        "color" in style or "gradient" in style or style.get("transparency", 0) > 0
    )
    bg = wall.upper() if surfaced else blend(style.get("color", theme["card"]), wall, t)
    fills = [bg]
    out = {"bg": bg}
    if "gradient" in style and not surfaced:
        out["bg2"] = blend(style["gradient"]["to"], wall, t)
        out["gd"] = "h" if style["gradient"]["direction"] == "horizontal" else "v"
        fills.append(out["bg2"])

    def _worst(colour: str) -> float:
        return min(contrast(colour, fill) for fill in fills)

    readable_tx = max(("#FFFFFF", "#15181D"), key=_worst)
    tx = theme["tx"] if _worst(theme["tx"]) >= 4.5 else readable_tx
    tx2 = (
        theme["tx2"]
        if not (custom or surfaced) or _worst(theme["tx2"]) >= 3.0
        else blend(tx, bg, 0.35)
    )
    acc = style.get("accent", theme["acc"])

    def _on_accent(colour: str) -> float:
        return contrast(colour, acc)

    acct = (
        theme["acct"]
        if "accent" not in style
        else max(("#FFFFFF", "#15181D"), key=_on_accent)
    )
    plain = not custom and "accent" not in style
    out.update(
        tx=tx,
        tx2=tx2,
        acc=acc,
        acc2=theme["acc2"],
        acct=acct,
        card2=theme["card2"] if not custom else blend(tx, bg, 0.88),
        line=theme["line"] if not custom else blend(tx, bg, 0.85),
        onbg=theme["onbg"] if plain else blend(acc, bg, 0.80),
        ontx=theme["ontx"] if plain else tx,
        r=theme["r"],
        r2=theme["r2"],
        bw=theme["bw"],
    )
    radius = CORNERS.get(style.get("corners", "theme"))
    if radius is not None:
        # r2 is round(r * 0.6) with halves rounded up (contract 4.7).
        out.update(r=radius, r2=(radius * 6 + 5) // 10)
    if surfaced:
        out["bw"] = OUTLINE_BW if style["surface"] == "outline" else 0
    width = BORDERS.get(style.get("border", "theme"))
    if width is not None:
        out["bw"] = width
    return out


# ------------------------------------------------- colours of contract 4.7
#
# Colours as whole numbers 0xRRGGBB. No colour is worked out in floating
# point; lum reads the table and adds in a fixed order. Python's round() is
# used in none of these (it rounds halves to even).

WHITE = 0xFFFFFF
INK = 0x15181D
BLACK = 0x000000


def to_int(colour: str) -> int:
    """Return '#RRGGBB' as 0xRRGGBB."""
    return int(colour[1:7], 16)


def to_hex(value: int) -> str:
    """Return 0xRRGGBB as '#RRGGBB' in upper case."""
    return f"#{value:06X}"


def mix(a: int, b: int, p: int) -> int:
    """Return per channel (a * (100 - p) + b * p + 50) div 100; p 0 gives a."""
    out = 0
    for shift in (16, 8, 0):
        x = a >> shift & 255
        y = b >> shift & 255
        out |= ((x * (100 - p) + y * p + 50) // 100) << shift
    return out


def lum(c: int) -> float:
    """Return (0.2126 * L[r] + 0.7152 * L[g]) + 0.0722 * L[b], step by step."""
    first = 0.2126 * LINEAR[c >> 16 & 255]
    second = 0.7152 * LINEAR[c >> 8 & 255]
    third = 0.0722 * LINEAR[c & 255]
    return (first + second) + third


def contrast_of(a: int, b: int) -> float:
    """Return (hi + 0.05) / (lo + 0.05) of the two luminances (contract 4.7)."""
    x = lum(a)
    y = lum(b)
    hi, lo = (x, y) if x >= y else (y, x)
    return (hi + 0.05) / (lo + 0.05)


def readable(c: int) -> int:
    """Return white or 0x15181D, whichever stands out more; white on a tie."""
    return WHITE if contrast_of(WHITE, c) >= contrast_of(INK, c) else INK


def legible(c: int, b: int, t: int) -> int:
    """Return c when it stands out on b, else c mixed half with t, else t."""
    if contrast_of(c, b) >= 3:
        return c
    half = mix(c, t, 50)
    if contrast_of(half, b) >= 3:
        return half
    return t


# --------------------------------------------------------------- themes

# What a theme is made from (E.2), and the order of the keys of an entry.
SEED_KEYS = (
    "id",
    "name",
    "description",
    "dark",
    "wall",
    "card",
    "card2",
    "line",
    "tx",
    "tx2",
    "acc",
    "acc2",
    "r",
    "r2",
    "bw",
)
ENTRY_KEYS = (
    "id",
    "name",
    "description",
    "dark",
    "wall",
    "card",
    "card_pr",
    "card2",
    "card2_pr",
    "line",
    "tx",
    "tx2",
    "acc",
    "accf",
    "accf_pr",
    "acct",
    "acc2",
    "onbg",
    "onbg_pr",
    "ontx",
    "ion",
    "r",
    "r2",
    "bw",
)
# A fill under a white text is darkened at most this many times.
_ACCF_STEPS = 64


def _on_roles(acc: int, card: int, tx: int, dark: bool) -> dict[str, int]:
    """Return onbg, onbg_pr and ontx for an accent on a card (E.2)."""
    onbg = mix(acc, card, 86 if dark else 88)
    ontx = mix(acc, tx, 70)
    if contrast_of(ontx, onbg) < 4.5:
        ontx = tx
    return {
        "onbg": onbg,
        "onbg_pr": mix(acc, card, 76 if dark else 78),
        "ontx": ontx,
    }


def derive_theme(seed: dict) -> dict:
    """Return a whole theme entry made from its seed by the rule of E.2.

    seed holds SEED_KEYS. A derived role the seed already holds is set by
    hand and kept (Contrast's pressed colours and its "on" fill).
    """
    known = {
        key: to_int(value)
        for key, value in seed.items()
        if key not in SEED_KEYS[:4] and isinstance(value, str)
    }
    dark = bool(seed["dark"])

    def role(name: str, value: int) -> int:
        known.setdefault(name, value)
        return known[name]

    role("card_pr", known["card2"])
    role("card2_pr", mix(known["tx"], known["card2"], 90))
    acct = role("acct", readable(known["acc"]))
    accf = known["acc"]
    toward = BLACK if acct == WHITE else WHITE
    for _ in range(_ACCF_STEPS):
        if contrast_of(acct, accf) >= 4.5:
            break
        accf = mix(toward, accf, 92)
    accf = role("accf", accf)
    role("accf_pr", mix(BLACK, accf, 88))
    on = _on_roles(known["acc"], known["card"], known["tx"], dark)
    onbg = role("onbg", on["onbg"])
    role("onbg_pr", on["onbg_pr"])
    ontx = role("ontx", on["ontx"])
    acc = known["acc"]
    role("ion", acc if contrast_of(acc, onbg) >= 3 else ontx)
    out: dict = {}
    for key in ENTRY_KEYS:
        if key in known:
            out[key] = to_hex(known[key])
        else:
            out[key] = bool(seed[key]) if key == "dark" else seed[key]
    return out


def with_accent(theme: dict, accent: str) -> dict:
    """Return a theme entry with a dashboard accent of one's own (E.1).

    acc, accf and ion are the colour; acct, accf_pr, onbg, onbg_pr and ontx
    follow the rule of E.2. The id and every other key stay.
    """
    acc = to_int(accent)
    out = dict(theme)
    on = _on_roles(acc, to_int(theme["card"]), to_int(theme["tx"]), bool(theme["dark"]))
    roles = {
        "acc": acc,
        "accf": acc,
        "accf_pr": mix(BLACK, acc, 88),
        "acct": readable(acc),
        "ion": acc,
        **on,
    }
    for key, value in roles.items():
        out[key] = to_hex(value)
    return out


def status_for(status: dict | None, theme_id: str | None, dark: bool) -> dict:
    """Return the status colours (good, warn, bad, info) a theme takes (E.3).

    A theme named under "themes" takes its own; else "dark" or "light" by
    its flag. An empty mapping without a status table.
    """
    if not isinstance(status, dict):
        return {}
    named = status.get("themes")
    table = named.get(theme_id) if isinstance(named, dict) and theme_id else None
    if not isinstance(table, dict):
        table = status.get("dark" if dark else "light")
    if not isinstance(table, dict):
        return {}
    return {
        role: table[role].upper()
        for role in STATUS_ROLES
        if isinstance(table.get(role), str) and _HEX.match(table[role])
    }
