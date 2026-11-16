"""Reference implementation of the TAB-1 tablet contract, version 2.

Standard library only. The integration copies this logic into its own
modules; the firmware tests compare against the fixtures this file made.
CONTRACT.md is the specification. Where the two differ, CONTRACT.md wins and
this file has a bug.
"""

from __future__ import annotations

import decimal
import hashlib
import hmac
import json
import math
from typing import Any

# The handshake range HA speaks (contract section 9).
PROTO_LOW = 1
PROTO = 2
# Field 1 of the input payload and of the knock. It is not PROTO.
INPUT_VERSION = 1
# The newest device layout version, and the one the version 1 writer writes.
DL_VERSION = 2
DL_V1 = 1

CHUNK_BYTES = 16000
MAX_LAYOUT_BYTES = 262144
MAX_SET_BYTES = 12000
MAX_TEXT_BYTES = 255
MAX_LIST = 120
MAX_NUMBER = 1_000_000_000
# Version 1, and normal pages in version 2.
MAX_PAGES = 20
MAX_PAGES_V2 = 64
MAX_NAV = 8
MAX_SLOTS = 1024
MAX_WIDGETS = 2048
MAX_OPTIONS = 16
MAX_OPTION_TEXT_BYTES = 40
MAX_TRACK = 8
MAX_STORED_BYTES = 131072
# What the tablet draws on one page, and what HA sends (HA's own choice).
PAGE_CHARTS, PAGE_ARCS, PAGE_TRACKS = 8, 8, 12
SEND_CHARTS, SEND_ARCS, SEND_TRACKS = 4, 4, 6

# What a tablet has when tab_hello leaves a caps key out. Key names are the
# ones of the tab_hello response.
CAPS_DEFAULTS = {
    "icons": 1,
    "screen": [1280, 800],
    "max_layout": MAX_LAYOUT_BYTES,
    "max_chunk": CHUNK_BYTES,
    "max_slots": MAX_SLOTS,
    "max_widgets": MAX_WIDGETS,
    "max_pages": MAX_PAGES,
    "max_stored": MAX_STORED_BYTES,
}

# Error codes that cannot succeed on a retry with the same layout and caps.
DETERMINISTIC_ERRORS = ("too_big", "limits", "version", "parse")

WIDGET_KINDS = (
    "heading",
    "card",
    "label",
    "button",
    "switch",
    "slider",
    "thermostat",
    "chart",
    "image",
)
POLICIES = ("optimistic", "pulse", "progress", "confirm")
LABEL_SIZES = ("s", "m", "l")
CHART_KINDS = ("line", "bars")

THEME_COLOURS = (
    "wall", "card", "card_pr", "card2", "card2_pr", "line", "tx", "tx2", "acc",
    "accf", "accf_pr", "acct", "acc2", "onbg", "onbg_pr", "ontx", "ion",
)  # fmt: skip
STYLE_COLOURS = (
    "bg", "bg2", "tx", "tx2", "acc", "acc2", "acct", "card2", "line", "onbg", "ontx",
)  # fmt: skip
RADII = ("r", "r2", "bw")

# What version 2 adds (contract.json "v2").
WIDGET_KINDS_V2 = ("choice",)
STYLE_COLOURS_V2 = ("card_pr", "card2_pr", "accf", "accf_pr", "onbg_pr", "ion")
CARD_KEYS_V2 = ("tap", "cf", "confirm", "hold", "ic", "tint", "lit", "un")
PAGE_KEYS_V2 = ("sub", "ttl", "theme")
WIDGET_KEYS_V2 = {
    "heading": ("c",),
    "label": ("vis", "hold", "px", "al", "c", "clk", "value"),
    "button": ("vis", "hold", "value", "ic", "c", "shape", "isz"),
    "switch": ("vis", "hold", "c"),
    "slider": ("vis", "look", "dir", "track", "icon", "c", "nv", "rate"),
    "thermostat": ("vis", "c", "mark", "bs"),
    "chart": ("vis", "hold", "c", "mark", "st"),
    "image": ("vis", "hold", "look", "c"),
    "choice": ("vis", "texts", "icons", "cols", "value", "rows", "look"),
}
LOOK_KEYS = ("px", "al", "shape", "isz", "look", "dir", "rows", "st", "bs", "lit", "ttl")
LIT = ("fill", "icon", "outline", "none")
ALIGN = ("left", "centre", "right")
SHAPES = ("box", "round", "bare")
SLIDER_LOOKS = ("knob", "bar")
DIRS = ("right", "up", "down")
IMAGE_LOOKS = ("box", "badge", "bare")
CHOICE_LOOKS = ("cells", "dots")

# What the newest engine answers in tab_hello (contract.json "engine_caps").
ENGINE_CAPS = {
    "w": list(WIDGET_KINDS) + list(WIDGET_KINDS_V2),
    "icons": 2,
    "screen": [1280, 800],
    "max_pages": MAX_PAGES_V2,
    "max_layout": MAX_LAYOUT_BYTES,
    "max_stored": MAX_STORED_BYTES,
    "max_chunk": CHUNK_BYTES,
    "max_slots": MAX_SLOTS,
    "max_widgets": MAX_WIDGETS,
}

KID_LABEL = b"apollo-tab1 kid v1"
WRAP_LABEL = "apollo-tab1 wrap v1"
CALL_LABEL = "apollo-tab1 call v1"

# Knock schedule of the tablet, in seconds after the API connection opens.
KNOCK_FIRST_S = 3
KNOCK_REPEATS = 5
KNOCK_MAX_S = 300


class ContractError(Exception):
    """A value that the contract does not allow."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


# ---------------------------------------------------------------- encoding


def num(value: float | int) -> int | float:
    """Return a number in wire form: clamped, at most 3 decimals, int if whole."""
    if isinstance(value, bool):
        return int(value)
    if not math.isfinite(value):
        raise ContractError("bad_number")
    value = max(-MAX_NUMBER, min(MAX_NUMBER, value))
    rounded = round(float(value), 3)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def canonical(obj: Any) -> bytes:
    """Return the canonical JSON bytes of a wire object."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def content_hash(data: bytes) -> str:
    """Return the 16 hex character hash of device layout bytes."""
    return hashlib.sha256(data).hexdigest()[:16]


def colour(text: str) -> int:
    """Return '#RRGGBB' as the integer 0xRRGGBB."""
    return int(text[1:7], 16)


def clip_text(text: str, limit: int = MAX_TEXT_BYTES) -> str:
    """Cut text to at most limit UTF-8 bytes without splitting a character."""
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    return raw[:limit].decode("utf-8", errors="ignore")


# ---------------------------------------------------------------- coercion


def is_on(value: Any) -> bool:
    """Mirror frontend/logic.js isOn."""
    if value is True:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value) and value != 0
    if isinstance(value, str):
        return value.lower() in ("on", "true", "yes", "1")
    return False


def to_number(value: Any) -> int | float | None:
    """Mirror frontend/logic.js toNumber, with None when there is no number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return num(value) if math.isfinite(value) else None
    if isinstance(value, str) and value.strip():
        try:
            number = float(value)
        except ValueError:
            return None
        return num(number) if math.isfinite(number) else None
    return None


def to_text(value: Any) -> str:
    """Return the text a label shows for a value."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(num(value)) if math.isfinite(value) else ""
    if isinstance(value, (list, tuple)):
        return clip_text(", ".join(to_text(item) for item in value))
    return clip_text(str(value))


def to_list(value: Any) -> list:
    """Return the finite numbers of a list value, at most MAX_LIST."""
    if not isinstance(value, (list, tuple)):
        return []
    out = []
    for item in value[:MAX_LIST]:
        number = to_number(item)
        if number is not None:
            out.append(number)
    return out


def to_icon(value: Any, icons: dict, level: int) -> int:
    """Return the glyph code point for an 'mdi:' name, or 0 for the placeholder."""
    if isinstance(value, str) and value in icons["icons"]:
        code, since = icons["icons"][value]
        if since <= level:
            return code
    return 0


def to_colour(value: Any, roles: dict | None = None) -> int | None:
    """Return a colour as 0xRRGGBB, or None (contract 4.4, colour conversion).

    [r, g, b] with each part 0 to 255 after rounding; "#RRGGBB" in either
    case; a whole number 0 to 16777215 (also written 16711680.0); a role
    name of roles (name to 0xRRGGBB). Anything else is None.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        if roles and value in roles:
            return roles[value]
        if len(value) == 7 and value[0] == "#" and all(c in HEX_ANY for c in value[1:]):
            return int(value[1:], 16)
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(value) or value != math.floor(value):
            return None
        whole = int(value)
        return whole if 0 <= whole <= 0xFFFFFF else None
    if isinstance(value, (list, tuple)) and len(value) == 3:
        out = 0
        for part in value:
            if isinstance(part, bool) or not isinstance(part, (int, float)):
                return None
            if not math.isfinite(part):
                return None
            channel = round_half_up(part)
            if not 0 <= channel <= 255:
                return None
            out = out << 8 | channel
        return out
    return None


HEX_ANY = frozenset("0123456789abcdefABCDEF")


def coerce(
    kind: str,
    value: Any,
    icons: dict,
    level: int,
    how: str | None = None,
    roles: dict | None = None,
) -> Any:
    """Turn an evaluated slot value into the wire value of a typed slot.

    None means "no value": the tablet draws the widget as unavailable.
    how "colour" (a number slot that holds a colour) follows to_colour.
    """
    if value is None:
        return None
    if how == "colour":
        return to_colour(value, roles)
    if kind == "b":
        return 1 if is_on(value) else 0
    if kind == "n":
        return to_number(value)
    if kind == "t":
        return to_text(value)
    if kind == "l":
        return to_list(value)
    if kind == "i":
        return to_icon(value, icons, level)
    raise ContractError("bad_slot_type", kind)


# ---------------------------------------------------- device layout (DL v1)


class _Slots:
    """Give each slot key one device slot number.

    The key is (source slot, type, coerce, roles). Version 1 has neither
    coerce nor roles, so there it is (source slot, type).
    """

    def __init__(self) -> None:
        self.plan: list[dict] = []
        self._index: dict[tuple, int] = {}

    def ref(
        self, source: int, kind: str, how: str | None = None, roles: dict | None = None
    ) -> dict:
        key = (source, kind, how, tuple(sorted(roles.items())) if roles else None)
        if key not in self._index:
            self._index[key] = len(self.plan) + 1
            entry: dict[str, Any] = {"d": self._index[key], "src": source, "type": kind}
            if how:
                entry["coerce"] = how
            if roles:
                entry["roles"] = dict(sorted(roles.items()))
            self.plan.append(entry)
        return {"s": self._index[key]}


def _bound(value: Any, kind: str, slots: _Slots, icons: dict, level: int) -> Any:
    """Compile one bound field: a slot reference or a coerced constant."""
    if isinstance(value, dict) and "s" in value:
        return slots.ref(value["s"], kind)
    return coerce(kind, value, icons, level)


def _icon(name: Any, icons: dict, level: int) -> int:
    """Return the code point of a fixed icon, or the fallback glyph."""
    code = to_icon(name, icons, level)
    if code:
        return code
    return icons["icons"][icons["fallback"]][0]


def _tap(tap: Any, page_index: dict[str, int]) -> dict | None:
    """Compile a tap or change dict."""
    if not isinstance(tap, dict):
        return None
    if tap.get("policy") in POLICIES:
        return {"p": POLICIES.index(tap["policy"])}
    if tap.get("local") == "go_to_page" and tap.get("page") in page_index:
        return {"go": page_index[tap["page"]]}
    return None


def _widget(
    widget: dict, slots: _Slots, icons: dict, level: int, page_index: dict[str, int]
) -> dict:
    """Compile one widget of a card."""
    kind = widget["t"]
    out: dict[str, Any] = {"id": widget["id"], "t": kind, "r": widget["r"]}
    if kind == "label":
        out["text"] = _bound(widget.get("text", ""), "t", slots, icons, level)
        size = widget.get("size", "m")
        out["size"] = LABEL_SIZES.index(size) if size in LABEL_SIZES else 1
    elif kind == "button":
        if "text" in widget:
            out["text"] = _bound(widget["text"], "t", slots, icons, level)
        if widget.get("icon"):
            out["icon"] = _icon(widget["icon"], icons, level)
    elif kind == "switch":
        out["value"] = _bound(widget.get("value"), "b", slots, icons, level)
    elif kind in ("slider", "thermostat"):
        for key, default in (("value", None), ("min", 0), ("max", 100), ("step", 1)):
            raw = widget.get(key)
            compiled = _bound(raw, "n", slots, icons, level)
            if compiled is None and default is not None:
                compiled = default
            out[key] = compiled
    elif kind == "chart":
        out["value"] = _bound(widget.get("value"), "l", slots, icons, level)
        chart_kind = widget.get("kind", "line")
        out["kind"] = CHART_KINDS.index(chart_kind) if chart_kind in CHART_KINDS else 0
    elif kind == "image":
        out["value"] = _bound(widget.get("value"), "i", slots, icons, level)
    for key in ("tap", "change"):
        compiled = _tap(widget.get(key), page_index)
        if compiled is not None:
            out[key] = compiled
    if "confirm" in widget:
        out["confirm"] = _bound(widget["confirm"], "t", slots, icons, level)
    action = out.get("tap") or out.get("change") or {}
    if "confirm" in out or action.get("p") == POLICIES.index("confirm"):
        out["cf"] = 1
    return out


def compile_device_layout(layout: dict, icons: dict, caps: dict | None = None) -> dict:
    """Compile a layout v1 (from convert.py) into the device layout.

    Returns {"bytes", "hash", "size", "slots", "dropped"}. slots is the plan
    that maps each device slot to its source slot number and type. dropped
    lists the widget ids left out because the tablet cannot draw their kind.
    counts holds pages, slots and widgets (every object with an id).
    Raises ContractError("too_big") when the bytes exceed the tablet's limit
    and ContractError("limits") when pages, slots or widgets do. HA checks
    these before it sends anything.
    """
    caps = {**CAPS_DEFAULTS, **(caps or {})}
    # A missing caps.w is the default list; an empty list is a tablet that
    # draws no widget kind inside a card. Headings and cards always stay.
    listed = caps.get("w")
    kinds = set(listed) if isinstance(listed, list) else set(WIDGET_KINDS)
    level = min(int(caps["icons"]), int(icons["version"]))
    limit = min(int(caps["max_layout"]), MAX_LAYOUT_BYTES)
    max_slots = min(int(caps["max_slots"]), MAX_SLOTS)
    max_widgets = min(int(caps["max_widgets"]), MAX_WIDGETS)
    slots = _Slots()
    dropped: list[int] = []
    page_index = {page["id"]: index for index, page in enumerate(layout["pages"])}

    theme_in = layout.get("theme", {})
    theme: dict[str, Any] = {"dark": 1 if theme_in.get("dark") else 0}
    for key in THEME_COLOURS:
        theme[key] = colour(theme_in.get(key, "#000000"))
    for key in RADII:
        theme[key] = int(theme_in.get(key, 0))

    nav = []
    for entry in layout.get("nav", []):
        if entry["page"] not in page_index:
            continue
        item: dict[str, Any] = {
            "p": page_index[entry["page"]],
            "title": clip_text(entry.get("title", ""), 40),
        }
        if entry.get("icon"):
            item["icon"] = _icon(entry["icon"], icons, level)
        nav.append(item)
    nav = nav[:MAX_NAV]

    pages = []
    for page in layout["pages"]:
        items = []
        for source in page["w"]:
            if source["t"] == "heading":
                heading: dict[str, Any] = {
                    "id": source["id"],
                    "t": "heading",
                    "r": source["r"],
                    "text": clip_text(source.get("text", ""), 80),
                }
                if source.get("icon"):
                    heading["icon"] = _icon(source["icon"], icons, level)
                items.append(heading)
                continue
            card: dict[str, Any] = {"id": source["id"], "t": "card", "r": source["r"]}
            header = source.get("header")
            if isinstance(header, dict):
                card["hr"] = header["r"]
                if header.get("icon"):
                    card["icon"] = _icon(header["icon"], icons, level)
                if "title" in header:
                    card["title"] = _bound(header["title"], "t", slots, icons, level)
            if source.get("on") is not None:
                card["on"] = _bound(source["on"], "b", slots, icons, level)
            style = source.get("style")
            if isinstance(style, dict):
                compiled_style: dict[str, Any] = {}
                for key in STYLE_COLOURS:
                    if key in style:
                        compiled_style[key] = colour(style[key])
                for key in RADII:
                    if key in style:
                        compiled_style[key] = int(style[key])
                if style.get("gd") in ("h", "v"):
                    compiled_style["gd"] = 1 if style["gd"] == "h" else 0
                card["style"] = compiled_style
            widgets = []
            for widget in source.get("w", []):
                if widget.get("t") not in kinds or widget.get("t") not in WIDGET_KINDS:
                    dropped.append(widget["id"])
                    continue
                widgets.append(_widget(widget, slots, icons, level, page_index))
            card["w"] = widgets
            items.append(card)
        pages.append({"title": clip_text(page.get("title", ""), 40), "w": items})

    device = {
        "v": DL_V1,
        "screen": layout.get("screen", [1280, 800]),
        "theme": theme,
        "nav": nav,
        "pages": pages,
        "slots": "".join(entry["type"] for entry in slots.plan),
    }
    widget_count = sum(len(page["w"]) for page in pages) + sum(
        len(item.get("w", [])) for page in pages for item in page["w"]
    )
    counts = {"pages": len(pages), "slots": len(slots.plan), "widgets": widget_count}
    if len(pages) > MAX_PAGES:
        raise ContractError("limits", f"{len(pages)} pages, limit {MAX_PAGES}")
    if len(slots.plan) > max_slots:
        raise ContractError("limits", f"{len(slots.plan)} slots, limit {max_slots}")
    if widget_count > max_widgets:
        raise ContractError("limits", f"{widget_count} widgets, limit {max_widgets}")
    data = canonical(device)
    if len(data) > limit:
        raise ContractError("too_big", f"{len(data)} bytes, limit {limit}")
    return {
        "bytes": data,
        "hash": content_hash(data),
        "size": len(data),
        "slots": slots.plan,
        "dropped": dropped,
        "counts": counts,
    }


# ----------------------------------------------------------------- chunks


def chunk_layout(data: bytes, chunk_bytes: int = CHUNK_BYTES) -> list[str]:
    """Split layout bytes into text chunks of at most chunk_bytes UTF-8 bytes.

    A chunk never ends inside a multi-byte character, so each chunk is valid
    text on its own. Joining the chunks' UTF-8 bytes gives data back.
    """
    if not 16 <= chunk_bytes <= CHUNK_BYTES:
        raise ContractError("bad_chunk_size")
    chunks = []
    start = 0
    while start < len(data):
        end = min(start + chunk_bytes, len(data))
        while end < len(data) and (data[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(data[start:end].decode("utf-8"))
        start = end
    return chunks or [""]


# ------------------------------------------------------------------ state


def encode_set(
    layout: str, values: dict[int, Any], *, full: bool, limit: int = MAX_SET_BYTES
) -> list[str]:
    """Encode slot values as one or more tab_set payloads.

    values maps device slot numbers to wire values (already coerced). With
    full=True the first payload carries "f":1, which tells the tablet to set
    every slot to "no value" before applying the pairs.
    """
    pairs = [[slot, values[slot]] for slot in sorted(values)]
    payloads: list[str] = []
    batch: list[list] = []

    def flush() -> None:
        message: dict[str, Any] = {"h": layout, "v": batch.copy()}
        if full and not payloads:
            message["f"] = 1
        payloads.append(canonical(message).decode("utf-8"))
        batch.clear()

    size = 64
    for pair in pairs:
        pair_size = len(canonical(pair)) + 1
        if batch and size + pair_size > limit:
            flush()
            size = 64
        batch.append(pair)
        size += pair_size
    if batch or not payloads:
        flush()
    return payloads


# ---------------------------------------------------------------- pairing


def kid(secret: bytes) -> str:
    """Return the public 16 hex character id of a pairing secret."""
    return hmac.new(secret, KID_LABEL, hashlib.sha256).hexdigest()[:16]


def wrap_secret(psk: bytes, mac: str, nonce: str, secret: bytes) -> str:
    """Hide a 32-byte pairing secret under the tablet's API encryption key."""
    label = f"{WRAP_LABEL}|{mac}|{nonce}".encode()
    pad = hmac.new(psk, label, hashlib.sha256).digest()
    return bytes(a ^ b for a, b in zip(secret, pad, strict=True)).hex()


def unwrap_secret(psk: bytes, mac: str, nonce: str, wrapped: str) -> bytes:
    """Undo wrap_secret (the XOR pad is its own inverse)."""
    return bytes.fromhex(wrap_secret(psk, mac, nonce, bytes.fromhex(wrapped)))


# ------------------------------------------------- signed calls from HA

HEX = frozenset("0123456789abcdef")


def is_hex(text: Any, length: int) -> bool:
    """Return whether text is exactly length lower-case hex characters."""
    return isinstance(text, str) and len(text) == length and set(text) <= HEX


def call_auth(
    secret: bytes | None, mac: str, nonce: str, n: int, action: str, body: str = ""
) -> str:
    """Return the auth argument of one call from HA to a paired tablet.

    "<n>.<32 hex>". n is 0 for tab_hello (nonce is then the new session's
    nonce). For every other call n starts at 1 after tab_hello and goes up by
    one per signed call. body is: the hash for tab_commit, the data text for
    tab_set, "<n>|<0 or 1>|<code>" for tab_ack, empty for tab_hello and
    tab_clear. Without a secret (tablet not paired) the auth is empty.
    """
    if secret is None:
        return ""
    message = f"{CALL_LABEL}|{mac}|{nonce}|{n}|{action}|{body}".encode("utf-8")
    return f"{n}.{hmac.new(secret, message, hashlib.sha256).hexdigest()[:32]}"


def check_auth(
    auth: Any,
    *,
    secret: bytes | None,
    mac: str,
    nonce: str,
    last_n: int,
    action: str,
    body: str = "",
) -> tuple[bool, int]:
    """Tablet side: check one auth argument. Returns (accepted, new last_n).

    A tablet without a secret accepts everything. A paired tablet needs a
    correct signature and, except for tab_hello, an n above the last accepted
    one.
    """
    if secret is None:
        return True, last_n
    if not isinstance(auth, str) or not auth.isascii() or "." not in auth:
        return False, last_n
    head, _, sig = auth.partition(".")
    if not (head.isdigit() and len(head) <= 9 and is_hex(sig, 32)):
        return False, last_n
    n = int(head)
    if action == "tab_hello":
        if n != 0:
            return False, last_n
    elif n <= last_n:
        return False, last_n
    expected = call_auth(secret, mac, nonce, n, action, body)
    if not hmac.compare_digest(expected, auth):
        return False, last_n
    return True, (0 if action == "tab_hello" else n)


def ack_body(n: int, ok: bool, code: str) -> str:
    """Return the signed body of a tab_ack call."""
    return f"{n}|{1 if ok else 0}|{code}"


# ------------------------------------------------------------------ input

INPUT_FIELDS = 9


def input_value(value: int | float | None) -> str:
    """Return a change value as payload text; empty for a tap."""
    if value is None:
        return ""
    return str(num(value))


def input_payload(
    mac: str,
    nonce: str,
    counter: int,
    layout: str,
    widget: int,
    event: str,
    confirmed: bool,
    value: int | float | None = None,
) -> str:
    """Build the signed text of one input event."""
    return "|".join(
        [
            str(INPUT_VERSION),
            mac,
            nonce,
            str(counter),
            layout,
            str(widget),
            event,
            "1" if confirmed else "0",
            input_value(value),
        ]
    )


def sign(secret: bytes, payload: str) -> str:
    """Return the 32 hex character signature of an input payload."""
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def verify_input(
    data: dict,
    *,
    mac: str,
    secret: bytes | None,
    nonce: str,
    last_counter: int,
    layouts: tuple[str, ...] | list[str],
) -> tuple[str, dict | None]:
    """Check one esphome.tab1_input event.

    layouts holds the hashes HA keeps bindings for on this tablet: the wanted
    one, and the one before it until the tablet confirms the switch.

    Returns (verdict, parsed). verdict is "ok" or the reason it is dropped:
    malformed, version, wrong_tablet, not_paired, bad_signature, stale_session,
    replay, stale_layout.
    """
    payload = data.get("d")
    signature = data.get("s")
    if not isinstance(payload, str) or not payload.isascii():
        return "malformed", None
    if not is_hex(signature, 32):
        return "malformed", None
    parts = payload.split("|")
    if len(parts) != INPUT_FIELDS or len(payload) > 200:
        return "malformed", None
    version, p_mac, p_nonce, p_counter, p_layout, p_widget, event, conf, value = parts
    if version != str(INPUT_VERSION):
        return "version", None
    if p_mac != mac:
        return "wrong_tablet", None
    if secret is None:
        return "not_paired", None
    if not hmac.compare_digest(sign(secret, payload), signature):
        return "bad_signature", None
    if p_nonce != nonce:
        return "stale_session", None
    if not (p_counter.isdigit() and p_widget.isdigit()):
        return "malformed", None
    if event not in ("t", "c") or conf not in ("0", "1"):
        return "malformed", None
    parsed: dict[str, Any] = {
        "counter": int(p_counter),
        "widget": int(p_widget),
        "event": "tap" if event == "t" else "change",
        "confirmed": conf == "1",
        "value": None,
    }
    if event == "c":
        try:
            parsed["value"] = num(float(value))
        except (ValueError, ContractError):
            return "malformed", None
    elif value:
        return "malformed", None
    if parsed["counter"] <= last_counter:
        return "replay", None
    if p_layout not in layouts:
        return "stale_layout", parsed
    return "ok", parsed


# ------------------------------------------------------- decisions in HA


def knock_times(limit: float) -> list[int]:
    """Return the seconds after connect at which the tablet knocks, up to limit."""
    times = []
    at = 0
    gap = KNOCK_FIRST_S
    while True:
        at += gap
        if at > limit:
            return times
        times.append(at)
        if len(times) >= KNOCK_REPEATS:
            gap = min(gap * 2, KNOCK_MAX_S)


def hello_steps(response: dict, *, stored_kid: str | None, want_hash: str | None) -> dict:
    """Return what HA does after a tab_hello response.

    steps is a list of: "pair", "hello" (greet again, a pairing ends the
    session), "send_layout", "send_state". status is "" or "unsupported".
    dl is the device layout version HA compiles: the highest version both
    ranges share (0 when they share none).
    """
    low, high = response.get("proto", [0, 0])
    dl = layout_version(response)
    if not dl:
        reason = "tablet_new" if low > PROTO else "tablet_old"
        return {"steps": [], "status": "unsupported", "reason": reason, "dl": 0}
    steps: list[str] = []
    reason = ""
    if response.get("enc") == 1:
        if not stored_kid or response.get("kid") != stored_kid:
            steps += ["pair", "hello"]
        elif response.get("session") != 1:
            # Same kid but the signature was refused: the secrets differ.
            steps += ["pair", "hello"]
    else:
        reason = "needs_encryption"
    if want_hash is not None:
        if response.get("layout") != want_hash:
            steps.append("send_layout")
        steps.append("send_state")
    return {"steps": steps, "status": "", "reason": reason, "dl": dl}


def layout_version(response: dict) -> int:
    """Return the device layout version for a tab_hello response, 0 for none.

    HA and the tablet can talk when the ranges [low, high] and
    [PROTO_LOW, PROTO] overlap; HA speaks the highest version they share.
    Version 2 is the only one with device layout version 2.
    """
    low, high = response.get("proto", [0, 0])
    shared = min(high, PROTO)
    if shared < max(low, PROTO_LOW):
        return 0
    return 2 if shared >= 2 else 1


def knock_data(mac: str, boot: int) -> str:
    """Return the d text of the knock (contract 2.2)."""
    return f"{INPUT_VERSION}|{mac}|{boot}"


def parse_knock(data: Any) -> tuple[str, int] | None:
    """Return (mac, boot) of a knock, or None when it is not one."""
    if not isinstance(data, str) or not data.isascii():
        return None
    parts = data.split("|")
    if len(parts) != 3 or parts[0] != str(INPUT_VERSION):
        return None
    if not (is_hex(parts[1], 12) and parts[2].isdigit()):
        return None
    return parts[1], int(parts[2])


def knock_step(*, session: bool, status: dict | None = None) -> str:
    """Return what HA does with a knock that passed the 2 s limit.

    session: HA has a session with this tablet on the current connection.
    Without one: "hello". With one, a knock never resets it by itself: HA
    reads tab_status first ("status"), and with that response greets again
    ("hello") only when the tablet reports "session":0, else "ignore".
    """
    if not session:
        return "hello"
    if status is None:
        return "status"
    return "hello" if status.get("session") == 0 else "ignore"


def status_verdict(response: dict, want_hash: str) -> str:
    """Return what a tab_status response means after tab_commit(want_hash).

    "building": ask again. "shown": the layout is on screen. Anything else is
    the reason the build ended without showing it.
    """
    if response.get("layout") == want_hash:
        return "shown"
    if response.get("staged") == want_hash:
        return "building"
    return response.get("build") or "replaced"


# ---------------------------------------------------- device layout (DL v2)
#
# Layout v2 is layout v1's shape with "v": 2 and the keys of contract 4.3
# under their device names and numbers. As in version 1, four things differ
# from the device layout: colours are "#RRGGBB" or {"s": n} (a colour slot
# may carry "roles": {name: "#RRGGBB"}), icons are "mdi:" names, slots are
# source slots, and tap, change and hold hold {"policy": name} or
# {"local": "go_to_page" | "back", "page": id}.


def _colour_const(value: Any) -> int:
    """Compile a constant colour of a layout v2; a bad one is an error."""
    out = to_colour(value)
    if out is None:
        raise ContractError("bad_colour", repr(value))
    return out


def _colour_field(value: Any, slots: _Slots) -> Any:
    """Compile a colour field: a colour slot reference or a constant."""
    if isinstance(value, dict) and "s" in value:
        roles = value.get("roles")
        roles = {k: _colour_const(v) for k, v in roles.items()} if roles else None
        return slots.ref(value["s"], "n", "colour", roles)
    return _colour_const(value)


def _tap2(tap: Any, page_index: dict[str, int]) -> dict | None:
    """Compile a tap or change of version 2: version 1's forms and back."""
    if isinstance(tap, dict) and tap.get("local") == "back":
        return {"back": 1}
    return _tap(tap, page_index)


def _hold(hold: Any, page_index: dict[str, int]) -> dict | None:
    """Compile a hold: only a page to go to."""
    if isinstance(hold, dict) and hold.get("local") == "go_to_page":
        if hold.get("page") in page_index:
            return {"go": page_index[hold["page"]]}
    return None


def _theme(theme_in: dict, keys_only: bool) -> dict:
    """Compile a theme entry. keys_only: only the keys it has (a page theme)."""
    theme: dict[str, Any] = {}
    if not keys_only or "dark" in theme_in:
        theme["dark"] = 1 if theme_in.get("dark") else 0
    for key in THEME_COLOURS:
        if not keys_only or key in theme_in:
            theme[key] = colour(theme_in.get(key, "#000000"))
    for key in RADII:
        if not keys_only or key in theme_in:
            theme[key] = int(theme_in.get(key, 0))
    return theme


def _cf(out: dict) -> None:
    """Set cf when the item asks first (a confirm text or policy 3)."""
    action = out.get("tap") or out.get("change") or {}
    if "confirm" in out or action.get("p") == POLICIES.index("confirm"):
        out["cf"] = 1


def _widget2(
    widget: dict, slots: _Slots, icons: dict, level: int, page_index: dict[str, int]
) -> dict:
    """Compile one widget of a card, version 2."""
    kind = widget["t"]
    if kind == "choice":
        out: dict[str, Any] = {"id": widget["id"], "t": kind, "r": widget["r"]}
    else:
        out = _widget({**widget, "tap": None, "change": None}, slots, icons, level, page_index)
        out.pop("cf", None)
    get = widget.get

    def bound(key: str, kind_char: str) -> None:
        if key in widget:
            out[key] = _bound(widget[key], kind_char, slots, icons, level)

    def whole(key: str) -> None:
        if key in widget:
            out[key] = int(widget[key])

    if "vis" in widget:
        bound("vis", "b")
    if "c" in widget:
        out["c"] = _colour_field(widget["c"], slots)
    if kind == "label":
        for key in ("px", "al", "clk"):
            whole(key)
        if "clk" in widget:
            bound("value", "n")
    elif kind == "button":
        bound("value", "b")
        bound("ic", "i")
        whole("shape")
        whole("isz")
    elif kind == "slider":
        for key in ("look", "dir", "nv"):
            whole(key)
        if "track" in widget:
            out["track"] = [_colour_const(c) for c in widget["track"]][:MAX_TRACK]
        if get("icon"):
            out["icon"] = _icon(widget["icon"], icons, level)
        bound("rate", "n")
    elif kind == "thermostat":
        bound("mark", "n")
        whole("bs")
    elif kind == "chart":
        bound("mark", "n")
        whole("st")
    elif kind == "image":
        whole("look")
    elif kind == "choice":
        if "texts" in widget:
            out["texts"] = [
                clip_text(text, MAX_OPTION_TEXT_BYTES) for text in widget["texts"][:MAX_OPTIONS]
            ]
        if "icons" in widget:
            out["icons"] = [
                _icon(name, icons, level) if name else 0 for name in widget["icons"][:MAX_OPTIONS]
            ]
        if "cols" in widget:
            out["cols"] = [_colour_const(c) for c in widget["cols"][:MAX_OPTIONS]]
        bound("value", "n")
        whole("rows")
        whole("look")
    for key in ("tap", "change"):
        compiled = _tap2(widget.get(key), page_index)
        if compiled is not None:
            out[key] = compiled
    if kind not in ("slider", "thermostat", "choice"):
        hold = _hold(widget.get("hold"), page_index)
        if hold is not None:
            out["hold"] = hold
    if "confirm" in widget and "confirm" not in out:
        out["confirm"] = _bound(widget["confirm"], "t", slots, icons, level)
    _cf(out)
    return out


def compile_device_layout_v2(layout: dict, icons: dict, caps: dict | None = None) -> dict:
    """Compile a layout v2 into a device layout of version 2.

    Returns what compile_device_layout returns. Raises ContractError
    ("limits") for more pages than min(caps.max_pages, 64), more than 20
    normal pages, too many slots or widgets, and ("too_big") as version 1.
    """
    caps = {**CAPS_DEFAULTS, **(caps or {})}
    listed = caps.get("w")
    kinds = set(listed) if isinstance(listed, list) else set(WIDGET_KINDS)
    known = set(WIDGET_KINDS) | set(WIDGET_KINDS_V2)
    level = min(int(caps["icons"]), int(icons["version"]))
    limit = min(int(caps["max_layout"]), MAX_LAYOUT_BYTES)
    max_slots = min(int(caps["max_slots"]), MAX_SLOTS)
    max_widgets = min(int(caps["max_widgets"]), MAX_WIDGETS)
    max_pages = min(int(caps["max_pages"]), MAX_PAGES_V2)
    slots = _Slots()
    dropped: list[int] = []
    page_index = {page["id"]: index for index, page in enumerate(layout["pages"])}
    detail = {
        index for index, page in enumerate(layout["pages"]) if index > 0 and page.get("sub")
    }

    nav = []
    for entry in layout.get("nav", []):
        if entry["page"] not in page_index or page_index[entry["page"]] in detail:
            continue
        item: dict[str, Any] = {
            "p": page_index[entry["page"]],
            "title": clip_text(entry.get("title", ""), 40),
        }
        if entry.get("icon"):
            item["icon"] = _icon(entry["icon"], icons, level)
        nav.append(item)
    nav = nav[:MAX_NAV]

    pages = []
    for page in layout["pages"]:
        items = []
        for source in page["w"]:
            if source["t"] == "heading":
                heading: dict[str, Any] = {
                    "id": source["id"],
                    "t": "heading",
                    "r": source["r"],
                    "text": clip_text(source.get("text", ""), 80),
                }
                if source.get("icon"):
                    heading["icon"] = _icon(source["icon"], icons, level)
                if "c" in source:
                    heading["c"] = _colour_field(source["c"], slots)
                items.append(heading)
                continue
            card: dict[str, Any] = {"id": source["id"], "t": "card", "r": source["r"]}
            header = source.get("header")
            if isinstance(header, dict):
                card["hr"] = header["r"]
                if header.get("icon"):
                    card["icon"] = _icon(header["icon"], icons, level)
                if "title" in header:
                    card["title"] = _bound(header["title"], "t", slots, icons, level)
            if source.get("on") is not None:
                card["on"] = _bound(source["on"], "b", slots, icons, level)
            for key in ("tap",):
                compiled = _tap2(source.get(key), page_index)
                if compiled is not None:
                    card[key] = compiled
            hold = _hold(source.get("hold"), page_index)
            if hold is not None:
                card["hold"] = hold
            if "confirm" in source:
                card["confirm"] = _bound(source["confirm"], "t", slots, icons, level)
            if "ic" in source:
                card["ic"] = _bound(source["ic"], "i", slots, icons, level)
            if "tint" in source:
                card["tint"] = _colour_field(source["tint"], slots)
            if "lit" in source:
                card["lit"] = int(source["lit"])
            if "un" in source:
                card["un"] = _bound(source["un"], "b", slots, icons, level)
            _cf(card)
            style = source.get("style")
            if isinstance(style, dict):
                compiled_style: dict[str, Any] = {}
                for key in STYLE_COLOURS + STYLE_COLOURS_V2:
                    if key in style:
                        compiled_style[key] = colour(style[key])
                for key in RADII:
                    if key in style:
                        compiled_style[key] = int(style[key])
                if style.get("gd") in ("h", "v"):
                    compiled_style["gd"] = 1 if style["gd"] == "h" else 0
                card["style"] = compiled_style
            widgets = []
            for widget in source.get("w", []):
                if widget.get("t") not in kinds or widget.get("t") not in known:
                    dropped.append(widget["id"])
                    continue
                widgets.append(_widget2(widget, slots, icons, level, page_index))
            card["w"] = widgets
            items.append(card)
        out_page: dict[str, Any] = {"title": clip_text(page.get("title", ""), 40), "w": items}
        if page.get("sub"):
            out_page["sub"] = 1
        if "ttl" in page:
            out_page["ttl"] = int(page["ttl"])
        if isinstance(page.get("theme"), dict):
            out_page["theme"] = _theme(page["theme"], True)
        pages.append(out_page)

    device = {
        "v": DL_VERSION,
        "screen": layout.get("screen", [1280, 800]),
        "theme": _theme(layout.get("theme", {}), False),
        "nav": nav,
        "pages": pages,
        "slots": "".join(entry["type"] for entry in slots.plan),
    }
    widget_count = sum(len(page["w"]) for page in pages) + sum(
        len(item.get("w", [])) for page in pages for item in page["w"]
    )
    normal = len(pages) - len(detail)
    counts = {
        "pages": len(pages),
        "normal_pages": normal,
        "slots": len(slots.plan),
        "widgets": widget_count,
    }
    if len(pages) > max_pages:
        raise ContractError("limits", f"{len(pages)} pages, limit {max_pages}")
    if normal > MAX_PAGES:
        raise ContractError("limits", f"{normal} normal pages, limit {MAX_PAGES}")
    if len(slots.plan) > max_slots:
        raise ContractError("limits", f"{len(slots.plan)} slots, limit {max_slots}")
    if widget_count > max_widgets:
        raise ContractError("limits", f"{widget_count} widgets, limit {max_widgets}")
    data = canonical(device)
    if len(data) > limit:
        raise ContractError("too_big", f"{len(data)} bytes, limit {limit}")
    return {
        "bytes": data,
        "hash": content_hash(data),
        "size": len(data),
        "slots": slots.plan,
        "dropped": dropped,
        "counts": counts,
    }


def compile_layout(layout: dict, icons: dict, caps: dict | None = None) -> dict:
    """Compile a layout of either version, by its "v"."""
    if layout.get("v", 1) == 2:
        return compile_device_layout_v2(layout, icons, caps)
    return compile_device_layout(layout, icons, caps)


def tablet_commit(data: bytes, caps: dict | None = None) -> str:
    """What a tablet that speaks version 2 answers to tab_commit of these bytes.

    Only the checks after the hash: "" (ok), "parse", "version" or "limits".
    It reads the page rules of contract 4.2; it does not check every key.
    """
    caps = {**ENGINE_CAPS, **(caps or {})}
    try:
        device = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return "parse"
    if not isinstance(device, dict) or not isinstance(device.get("pages"), list):
        return "parse"
    if device.get("v") not in (1, 2) or isinstance(device.get("v"), bool):
        return "version"
    pages = device["pages"]
    if device["v"] == 1:
        if len(pages) > MAX_PAGES:
            return "limits"
    else:
        normal = sum(
            1 for index, page in enumerate(pages) if not (index > 0 and page.get("sub") == 1)
        )
        if len(pages) > min(int(caps["max_pages"]), MAX_PAGES_V2) or normal > MAX_PAGES:
            return "limits"
    if len(device.get("slots", "")) > MAX_SLOTS:
        return "limits"
    return ""


# ------------------------------------------------------------- drawing maths
#
# The rules of contract 4.7 that both sides must compute alike, with the
# vectors of fixtures/maths.json. No colour is worked out in floating point,
# except lum and blend, in a fixed order and without fused multiply-add.
# Python's round() rounds halves to even, so it is used in none of these.

WHITE = 0xFFFFFF
INK = 0x15181D
TEXT_PX = (14, 15, 16, 18, 20, 28, 34)
DIGITS_PX = (48, 96, 192)
DIGITS_GLYPHS = "0123456789.,-:°%+ "
ICON_SIZES = (72, 48, 28, 24)
LABEL_SIZE_PX = (14, 18, 34)
GAP = 8


def round_half_up(x: float) -> int:
    """round(x) of contract 4.7: floor(x + 0.5)."""
    return math.floor(x + 0.5)


def _linear(value: int) -> float:
    """The linear value of one channel, worked out once for the table.

    Decimal arithmetic at 60 digits, then the nearest double, so the table
    is the same on every machine.
    """
    context = decimal.Context(prec=60)
    v = context.divide(decimal.Decimal(value), decimal.Decimal(255))
    if v <= decimal.Decimal("0.03928"):
        out = context.divide(v, decimal.Decimal("12.92"))
    else:
        base = context.divide(context.add(v, decimal.Decimal("0.055")), decimal.Decimal("1.055"))
        out = context.power(base, decimal.Decimal("2.4"))
    return float(out)


# The table "linear" of maths.json: the linear value of each channel value.
LINEAR = tuple(_linear(value) for value in range(256))


def _channels(c: int) -> tuple[int, int, int]:
    return c >> 16 & 255, c >> 8 & 255, c & 255


def mix(a: int, b: int, p: int) -> int:
    """Per channel (a * (100 - p) + b * p + 50) div 100. p 0 gives a."""
    out = 0
    for x, y in zip(_channels(a), _channels(b), strict=True):
        out = out << 8 | (x * (100 - p) + y * p + 50) // 100
    return out


def lum(c: int) -> float:
    """(0.2126 * L[r] + 0.7152 * L[g]) + 0.0722 * L[b], each step on its own."""
    r, g, b = _channels(c)
    first = 0.2126 * LINEAR[r]
    second = 0.7152 * LINEAR[g]
    third = 0.0722 * LINEAR[b]
    return (first + second) + third


def contrast(a: int, b: int) -> float:
    """(hi + 0.05) / (lo + 0.05) of the two luminances."""
    x, y = lum(a), lum(b)
    hi, lo = (x, y) if x >= y else (y, x)
    return (hi + 0.05) / (lo + 0.05)


def readable(c: int) -> int:
    """White or 0x15181D, the one with the higher contrast; white on a tie."""
    return WHITE if contrast(WHITE, c) >= contrast(INK, c) else INK


def legible(c: int, b: int, t: int) -> int:
    """c when it stands out on b; else c mixed half with t if that does; else t."""
    if contrast(c, b) >= 3:
        return c
    m = mix(c, t, 50)
    if contrast(m, b) >= 3:
        return m
    return t


def blend(a: int, b: int, t: float) -> int:
    """Version 1's blend: per channel floor(a * (1 - t) + b * t + 0.5)."""
    out = 0
    for x, y in zip(_channels(a), _channels(b), strict=True):
        first = x * (1 - t)
        second = y * t
        out = out << 8 | math.floor((first + second) + 0.5)
    return out


def card_tokens(theme: dict, style: dict | None = None) -> dict:
    """The colours of a card: the page's theme with the card's style on top.

    theme and style are device form (integers). ion and onbg_pr: the
    style's own; else, when the style's onbg differs from the theme's, ion
    is acc when contrast(acc, onbg) >= 3 and ontx otherwise, and onbg_pr is
    blend(ontx, onbg, 0.82); else the theme's.
    """
    style = style or {}
    tokens = {key: theme[key] for key in THEME_COLOURS}
    tokens["bg"] = theme["card"]
    for key in RADII:
        tokens[key] = theme.get(key, 0)
    for key in STYLE_COLOURS + STYLE_COLOURS_V2 + RADII:
        if key in style:
            tokens[key] = style[key]
    if "onbg" in style and style["onbg"] != theme["onbg"]:
        if "ion" not in style:
            tokens["ion"] = tokens["acc"] if contrast(tokens["acc"], style["onbg"]) >= 3 else tokens["ontx"]
        if "onbg_pr" not in style:
            tokens["onbg_pr"] = blend(tokens["ontx"], style["onbg"], 0.82)
    return tokens


def card_colours(tokens: dict, on: bool, lit: int = 0, tint: int | None = None) -> dict:
    """The nine colours of contract 4.7 and what the card shows now.

    on: the card's on is 1. lit 0 fill, 1 icon, 2 outline, 3 none.
    """
    bg, tx, tx2 = tokens["bg"], tokens["tx"], tokens["tx2"]
    dark = readable(bg) == WHITE
    if tint is None:
        out = {
            "A": tokens["acc"],
            "AF": tokens["accf"],
            "AT": tokens["acct"],
            "AP": tokens["accf_pr"],
            "F": tokens["onbg"],
            "FT": tokens["ontx"],
            "FS": tokens["ontx"],
            "FI": tokens["ion"],
            "FP": tokens["onbg_pr"],
        }
    else:
        a = legible(tint, bg, tx)
        f = mix(tint, bg, 78 if dark else 84)
        out = {
            "A": a,
            "AF": a,
            "AT": readable(a),
            "AP": mix(0x000000, a, 88),
            "F": f,
            "FT": tx,
            "FS": tx2 if contrast(tx2, f) >= 3 else tx,
            "FI": legible(tint, f, tx),
            "FP": mix(tx, f, 90),
        }
    filled = bool(on) and lit == 0
    lit_on = bool(on) and lit in (1, 2)
    out["dark"] = 1 if dark else 0
    out["filled"] = 1 if filled else 0
    out["background"] = out["F"] if filled else bg
    out["text"] = out["FT"] if filled else tx
    out["border"] = out["A"] if filled or (on and lit == 2) else tokens["line"]
    out["border_width"] = max(2, tokens["bw"]) if on and lit == 2 else tokens["bw"]
    out["header_icon"] = out["FI"] if filled else out["A"] if lit_on else tx2
    return out


def largest_icon(limit: float) -> int:
    """The largest of 72, 48, 28, 24 that is not above limit; 24 when none is."""
    for px in ICON_SIZES:
        if px <= limit:
            return px
    return ICON_SIZES[-1]


def image_look(
    tokens: dict, card: dict, on: bool, lit: int, look: int, w: int, h: int, c: int | None
) -> dict:
    """An image widget: its box or circle, the icon size and the two colours.

    card is card_colours() of its card. look 0 box, 1 badge, 2 bare. c is
    the widget's colour, or None for no value. None when the rectangle has
    no width or no height: the widget is not drawn (4.3).
    """
    if w <= 0 or h <= 0:
        return None
    side = min(w, h)
    if look == 0:
        icon = legible(c, tokens["card2"], tokens["tx"]) if c is not None else tokens["acc2"]
        return {"box": [0, 0, max(0, w), max(0, h)], "fill": tokens["card2"],
                "icon_px": largest_icon(side // 2), "icon": icon}
    filled = bool(on) and lit == 0
    lit_on = bool(on) and lit in (1, 2)
    plain = c is None and not filled and not lit_on
    if c is not None:
        k = c
    elif filled:
        k = card["FI"]
    elif lit_on:
        k = card["A"]
    else:
        k = tokens["tx2"]
    b, t = card["background"], card["text"]
    if look == 1:
        x = round_half_up((w - side) / 2)
        y = round_half_up((h - side) / 2)
        icon_px = largest_icon(0.6 * side)
        if plain:
            return {"box": [x, y, side, side], "fill": tokens["card2"],
                    "icon_px": icon_px, "icon": tokens["tx2"], "plain": 1}
        wash = mix(k, b, 80)
        return {"box": [x, y, side, side], "fill": wash, "icon_px": icon_px,
                "icon": legible(k, wash, t), "plain": 0}
    return {"box": None, "fill": None, "icon_px": largest_icon(side),
            "icon": legible(k, b, t), "plain": 1 if plain else 0}


def label_size(px: int | None, text: str, size: int = 1) -> dict:
    """The size a label is drawn at, before its width is checked.

    Returns {"px": size, "smaller": the sizes to try in turn while the
    text is wider than the rectangle, "small": drawn in the small colour}.
    Without px: size 0, 1 or 2 gives 14, 18 or 34. A digit size is used
    only when every character of the text is in fonts.digits_glyphs.
    """
    if px is None:
        chosen = LABEL_SIZE_PX[size]
        return {"px": chosen, "smaller": [], "small": 1 if chosen == 14 else 0}
    digits = all(char in DIGITS_GLYPHS for char in text)
    if digits and px >= DIGITS_PX[0]:
        chosen = max(d for d in DIGITS_PX if d <= px)
        chain = [192, 96, 48, 34]
        return {"px": chosen, "smaller": chain[chain.index(chosen) + 1:], "small": 0}
    fits = [t for t in TEXT_PX if t <= px]
    chosen = fits[-1] if fits else TEXT_PX[0]
    return {"px": chosen, "smaller": [], "small": 1 if chosen in (14, 15) else 0}


def clock_text(value: float | None, age_s: float, form: int) -> str:
    """The text of a clock label: m = floor(v + age / 60) mod 1440."""
    if value is None:
        return "--:--"
    m = math.floor(value + age_s / 60) % 1440
    hour, minute = divmod(m, 60)
    if form == 2:
        return f"{hour % 12 or 12}:{minute:02d}"
    return f"{hour:02d}:{minute:02d}"


def clamp_step(value: float, low: float, high: float, step: float) -> float:
    """logic.js clampStep: clamp, snap to the step from low, 6 decimals."""
    result = low if value < low else value
    if result > high:
        result = high
    if step > 0:
        result = low + round_half_up((result - low) / step) * step
        if result < low:
            result = low
        if result > high:
            result = high
    return round_half_up(result * 1000000.0) / 1000000.0


def fraction(value: float, low: float, high: float) -> float:
    """logic.js fraction: where value lies from low to high, 0 to 1."""
    if not high > low:
        return 0.0
    f = (value - low) / (high - low)
    return 0.0 if not f > 0 else 1.0 if f > 1 else f


def slider_axis(rect: list, direction: int) -> tuple[int, int]:
    """(L, S): the length along the axis and the other side."""
    w, h = max(0, rect[2]), max(0, rect[3])
    return (w, h) if direction == 0 else (h, w)


def slider_along(rect: list, direction: int, x: float, y: float) -> float:
    """A point's distance from the start edge, along the axis."""
    if direction == 0:
        return x - rect[0]
    if direction == 1:
        return rect[1] + rect[3] - y
    return y - rect[1]


def slider_radius(look: int, rect: list, direction: int, r2: int) -> int:
    """R of a track: 7 for a knob slider, min(r2, S div 2) for a bar."""
    _, side = slider_axis(rect, direction)
    return 7 if look == 0 else min(r2, side // 2)


def slider_amount(
    rect: list, look: int, direction: int, track: int, r2: int, x: float, y: float
) -> float:
    """The amount under a finger, 0 to 1. track is the number of colours."""
    length, _ = slider_axis(rect, direction)
    along = slider_along(rect, direction, x, y)
    if track >= 2:
        radius = slider_radius(look, rect, direction, r2)
        x0, x1 = radius, length - radius
        if x1 <= x0:
            return 0.0
        return min(1.0, max(0.0, (along - x0) / (x1 - x0)))
    if length <= 0:
        return 0.0
    return min(1.0, max(0.0, along / length))


def slider_length(rect: list, look: int, direction: int, track: int, r2: int) -> int:
    """The length a finger moves over: x1 - x0 with a track, else L."""
    length, _ = slider_axis(rect, direction)
    if track >= 2:
        radius = slider_radius(look, rect, direction, r2)
        return length - 2 * radius
    return length


def slider_value(
    amount: float, low: float, high: float, step: float, length: int
) -> float | None:
    """The value a slider sends for an amount; None when it sends nothing.

    length is slider_length(): a slider without one sends nothing, nor
    does one whose max is not above min.
    """
    if length <= 0 or not high > low:
        return None
    return clamp_step(low + amount * (high - low), low, high, step)


def track_pieces(n: int, x0: int, x1: int) -> list:
    """The n - 1 pieces of a track of n colours, [from, to] along the axis."""
    if n < 2 or x1 <= x0:
        return []
    return [
        [x0 + (k * (x1 - x0)) // (n - 1), x0 + ((k + 1) * (x1 - x0)) // (n - 1)]
        for k in range(n - 1)
    ]


def slider_shape(
    rect: list, look: int, direction: int, track: int, r2: int,
    value: float | None, low: float, high: float, change: bool,
) -> dict:
    """Where a value is drawn, as distances from the start edge.

    look 0 without a track: knob centre at round(amount * L). look 1
    without a track: fill length, the drawn fill, the handle and the icon.
    With a track: the caps, the pieces and the mark centre.
    """
    length, side = slider_axis(rect, direction)
    amount = fraction(value, low, high) if value is not None else 0.0
    out: dict[str, Any] = {"L": length, "S": side}
    if track >= 2:
        radius = slider_radius(look, rect, direction, r2)
        x0, x1 = radius, length - radius
        out["R"] = radius
        out["caps"] = [[0, min(x0, length)], [max(x1, 0) if x1 > x0 else max(x0, 0), length]]
        out["pieces"] = track_pieces(track, x0, x1)
        if x1 <= x0 or value is None or not high > low:
            out["mark"] = None
        else:
            out["mark"] = round_half_up(x0 + amount * (x1 - x0))
        return out
    if look == 0:
        out["knob"] = round_half_up(amount * length) if value is not None else None
        return out
    radius = slider_radius(look, rect, direction, r2)
    fill = round_half_up(amount * length) if value is not None else 0
    out["R"] = radius
    out["fill"] = fill
    out["drawn"] = 0 if fill <= 0 else max(fill, 2 * radius)
    out["handle"] = [fill - 12, fill - 8] if change and fill >= 28 else None
    out["icon_centre"] = 24 if side >= 32 else None
    out["icon_on_fill"] = 1 if side >= 32 and fill >= 48 else 0
    return out


def choice_cells(n: int, rows: int, w: int, h: int, look: int = 0) -> list | None:
    """The cells of a choice, [x, y, w, h] from its rectangle's corner.

    None when nothing is drawn: no option, or a cell below 1 px. With look
    1 each cell also has its dot: [x, y, d, d], centred.
    """
    n = min(n, MAX_OPTIONS)
    rows = min(4, max(1, rows))
    if n <= 0:
        return None
    per_row = -(-n // rows)
    cell_w = (w - GAP * (per_row - 1)) // per_row
    cell_h = (h - GAP * (rows - 1)) // rows
    if cell_w < 1 or cell_h < 1:
        return None
    cells = []
    for index in range(n):
        row, column = divmod(index, per_row)
        cell = [column * (cell_w + GAP), row * (cell_h + GAP), cell_w, cell_h]
        if look == 1:
            d = min(cell_w, cell_h)
            cell.append(
                [cell[0] + round_half_up((cell_w - d) / 2), cell[1] + round_half_up((cell_h - d) / 2), d, d]
            )
        cells.append(cell)
    return cells


def choice_at(cells: list | None, x: int, y: int) -> int | None:
    """The option under a point (from the rectangle's corner), or None."""
    for index, cell in enumerate(cells or []):
        if cell[0] <= x < cell[0] + cell[2] and cell[1] <= y < cell[1] + cell[3]:
            return index
    return None


def line_points(values: list, width: float, height: float, pad: float) -> list:
    """logic.js linePoints."""
    if not values:
        return []
    low, high = min(values), max(values)
    middle = height / 2
    if len(values) == 1:
        return [[pad, middle], [width - pad, middle]]
    out = []
    for index, value in enumerate(values):
        x = pad + (index / (len(values) - 1)) * (width - pad * 2)
        y = middle if high == low else height - pad - ((value - low) / (high - low)) * (height - pad * 2)
        out.append([x, y])
    return out


def step_rects(points: list) -> list:
    """The steps of a line chart with st 1: filled rectangles, 3 thick.

    For each point below the last: a flat run from x_i to x_(i+1) at y_i,
    then an upright run at x_(i+1) from y_i to y_(i+1) (none when the two
    are equal). Each run is 3 thick, centred on its line and 1 longer at
    both ends, with coordinates rounded: [x, y, w, h].
    """
    out = []
    for (xa, ya), (xb, yb) in zip(points, points[1:]):
        left, right = round_half_up(min(xa, xb) - 1), round_half_up(max(xa, xb) + 1)
        top = round_half_up(ya - 1.5)
        out.append([left, top, right - left, 3])
        if ya != yb:
            top, bottom = round_half_up(min(ya, yb) - 1), round_half_up(max(ya, yb) + 1)
            left = round_half_up(xb - 1.5)
            out.append([left, top, 3, bottom - top])
    return out


def bar_marks(n: int, mark: float | None) -> list:
    """The colour role of each bar of a bar chart with mark."""
    if mark is None:
        return ["acc2"] * n
    k = round_half_up(mark)
    if not 0 <= k < n:
        return ["acc2"] * n
    return ["acc2"] * k + ["acc"] + ["card2"] * (n - k - 1)


# ------------------------------------------------------------ input, v2


def check_change(widget: dict, value: float, sent: dict[int, Any]) -> bool:
    """Whether HA runs a c event with this value (contract 7.3, version 2).

    widget is the compiled widget of HA's copy of the layout. sent maps
    device slots to the values HA last sent this tablet.
    """
    if "change" not in widget or not math.isfinite(value):
        return False
    if widget["t"] == "choice":
        count = max(len(widget.get(key, [])) for key in ("texts", "icons", "cols"))
        count = min(count, MAX_OPTIONS)
        return value == math.floor(value) and 0 <= value < count

    def limit(key: str, default: float) -> float | None:
        field = widget.get(key, default)
        if isinstance(field, dict):
            got = sent.get(field["s"])
            if isinstance(got, bool) or not isinstance(got, (int, float)):
                return None
            return got
        return field

    low, high, step = limit("min", 0), limit("max", 100), limit("step", 1)
    if low is None or high is None or step is None:
        return False
    if not low <= value <= high:
        return False
    if step <= 0 or value == high:
        return True
    k = round_half_up((value - low) / step)
    return abs(low + k * step - value) <= 0.0015


def check_tap(item: dict) -> bool:
    """Whether HA runs a t event for this item: it has a tap that sends."""
    tap = item.get("tap")
    return isinstance(tap, dict) and "p" in tap


# ------------------------------------------------------------ contract.json


def contract_document() -> dict:
    """The whole of contract.json. gen_fixtures.py writes it with indent 1;
    check_fixtures.py compares the file with it byte for byte."""
    return {
        "proto": PROTO,
        "proto_low": PROTO_LOW,
        "input_version": INPUT_VERSION,
        "dl_version": DL_VERSION,
        "limits": {
            "chunk_bytes": CHUNK_BYTES,
            "max_layout_bytes": MAX_LAYOUT_BYTES,
            "max_set_bytes": MAX_SET_BYTES,
            "max_text_bytes": MAX_TEXT_BYTES,
            "max_list": MAX_LIST,
            "max_number": MAX_NUMBER,
            "max_pages": MAX_PAGES,
            "max_nav": MAX_NAV,
            "max_slots": MAX_SLOTS,
            "max_widgets": MAX_WIDGETS,
            "max_input_payload": 200,
            "max_pages_v2": MAX_PAGES_V2,
            "max_options": MAX_OPTIONS,
            "max_option_text_bytes": MAX_OPTION_TEXT_BYTES,
            "max_track": MAX_TRACK,
            "max_stored_bytes": MAX_STORED_BYTES,
            "page_charts": PAGE_CHARTS,
            "page_arcs": PAGE_ARCS,
            "page_tracks": PAGE_TRACKS,
            "send_charts": SEND_CHARTS,
            "send_arcs": SEND_ARCS,
            "send_tracks": SEND_TRACKS,
        },
        "caps_defaults": {"w": list(WIDGET_KINDS), **CAPS_DEFAULTS},
        "engine_caps": ENGINE_CAPS,
        "fonts": {
            "text_px": list(TEXT_PX),
            "digits_px": list(DIGITS_PX),
            "digits_glyphs": DIGITS_GLYPHS,
            "icon_px": [24, 28, 48, 72],
            # The lowest rectangle HA gives a label of a digit size.
            "row_px": {"48": 60, "96": 120, "192": 240},
            # Code point ranges [first, last] of the text sizes: Latin,
            # Latin-1, Latin Extended-A, dashes, quotes, bullet,
            # ellipsis, euro. Any other character is an empty box.
            "text_glyphs": [
                [0x20, 0x7E],
                [0xA0, 0x17F],
                [0x2013, 0x2014],
                [0x2018, 0x2019],
                [0x201C, 0x201D],
                [0x2022, 0x2022],
                [0x2026, 0x2026],
                [0x20AC, 0x20AC],
            ],
        },
        "knock": {
            "first_s": KNOCK_FIRST_S,
            "repeats": KNOCK_REPEATS,
            "max_s": KNOCK_MAX_S,
        },
        "timing": {
            "call_timeout_s": 10,
            "status_poll_s": [0.15, 0.3, 0.5],
            "status_poll_limit_s": 60,
            "ack_timeout_s": 4,
            "progress_timeout_s": 30,
            "retry_s": [5, 15, 60, 300],
            "repair_once_per_s": 60,
            "hold_ms": 500,
            "hold_move_px": 12,
            "swipe_px": 48,
            "card_press_ms": 80,
            "sub_ttl_s": 60,
            "cache_bucket": 12,
            "cache_refill_s": 7200,
        },
        "widget_kinds": list(WIDGET_KINDS),
        "slot_types": {
            "t": "text",
            "b": "bool as 0 or 1",
            "n": "number",
            "l": "list of numbers",
            "i": "icon code point, 0 for the placeholder",
        },
        "policies": list(POLICIES),
        "label_sizes": list(LABEL_SIZES),
        "chart_kinds": list(CHART_KINDS),
        "theme_colours": list(THEME_COLOURS),
        "style_colours": list(STYLE_COLOURS),
        "actions": {
            "tab_hello": {
                "args": {"nonce": "string", "auth": "string"},
                "response": "only",
            },
            "tab_status": {"args": {}, "response": "only"},
            "tab_pair": {
                "args": {"nonce": "string", "wrapped": "string", "kid": "string"},
                "response": "status",
            },
            "tab_layout": {
                "args": {
                    "hash": "string",
                    "seq": "int",
                    "total": "int",
                    "size": "int",
                    "data": "string",
                },
                "response": "status",
            },
            "tab_commit": {
                "args": {"hash": "string", "auth": "string"},
                "response": "status",
            },
            "tab_set": {
                "args": {"data": "string", "auth": "string"},
                "response": "status",
            },
            "tab_ack": {
                "args": {"n": "int", "ok": "bool", "code": "string", "auth": "string"},
                "response": "none",
            },
            "tab_clear": {"args": {"auth": "string"}, "response": "status"},
        },
        "events": {
            "esphome.tab1_hello": {"d": knock_data("<mac>", "<boot>")},
            "esphome.tab1_input": {"d": "<payload>", "s": "<signature>"},
        },
        "errors": {
            "tab_pair": ["needs_encryption", "bad_key"],
            "tab_layout": ["order", "size", "too_big", "memory"],
            "tab_commit": [
                "auth", "incomplete", "hash", "parse", "version", "limits", "memory",
            ],
            "tab_set": ["auth", "hash", "parse"],
            "tab_clear": ["auth"],
        },
        "build_codes": ["", "memory", "build"],
        "deterministic_errors": list(DETERMINISTIC_ERRORS),
        "ack_codes": ["", "confirm", "denied", "failed", "stale", "busy"],
        "labels": {
            "kid": KID_LABEL.decode(),
            "wrap": WRAP_LABEL,
            "call": CALL_LABEL,
        },
        "v2": {
            "widget_kinds": list(WIDGET_KINDS_V2),
            "style_colours": list(STYLE_COLOURS_V2),
            "card_keys": list(CARD_KEYS_V2),
            "page_keys": list(PAGE_KEYS_V2),
            "widget_keys": {k: list(v) for k, v in WIDGET_KEYS_V2.items()},
            "look_keys": list(LOOK_KEYS),
            "lit": list(LIT),
            "align": list(ALIGN),
            "shapes": list(SHAPES),
            "slider_looks": list(SLIDER_LOOKS),
            "dirs": list(DIRS),
            "image_looks": list(IMAGE_LOOKS),
            "choice_looks": list(CHOICE_LOOKS),
        },
    }
