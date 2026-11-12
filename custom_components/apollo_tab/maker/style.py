"""Colour maths and style resolution for maker elements."""


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


def resolve_style(theme: dict, style: dict, wall: str) -> dict:
    """Resolve an element style against a theme into concrete paint tokens."""
    t = style.get("transparency", 0) / 100
    custom = "color" in style or "gradient" in style or style.get("transparency", 0) > 0
    bg = blend(style.get("color", theme["card"]), wall, t)
    fills = [bg]
    out = {"bg": bg}
    if "gradient" in style:
        out["bg2"] = blend(style["gradient"]["to"], wall, t)
        out["gd"] = "h" if style["gradient"]["direction"] == "horizontal" else "v"
        fills.append(out["bg2"])

    def _worst(colour: str) -> float:
        return min(contrast(colour, fill) for fill in fills)

    readable = max(("#FFFFFF", "#15181D"), key=_worst)
    tx = theme["tx"] if _worst(theme["tx"]) >= 4.5 else readable
    tx2 = (
        theme["tx2"]
        if not custom or _worst(theme["tx2"]) >= 3.0
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
    return out
