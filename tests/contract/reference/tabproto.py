"""Reference implementation of the TAB-1 tablet contract, version 1.

Standard library only. The integration copies this logic into its own
modules; the firmware tests compare against the fixtures this file made.
CONTRACT.md is the specification. Where the two differ, CONTRACT.md wins and
this file has a bug.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from typing import Any

PROTO = 1
DL_VERSION = 1

CHUNK_BYTES = 16000
MAX_LAYOUT_BYTES = 262144
MAX_SET_BYTES = 12000
MAX_TEXT_BYTES = 255
MAX_LIST = 120
MAX_NUMBER = 1_000_000_000
MAX_PAGES = 20
MAX_NAV = 8
MAX_SLOTS = 1024
MAX_WIDGETS = 2048

# What a tablet has when tab_hello leaves a caps key out. Key names are the
# ones of the tab_hello response.
CAPS_DEFAULTS = {
    "icons": 1,
    "screen": [1280, 800],
    "max_layout": MAX_LAYOUT_BYTES,
    "max_chunk": CHUNK_BYTES,
    "max_slots": MAX_SLOTS,
    "max_widgets": MAX_WIDGETS,
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


def coerce(kind: str, value: Any, icons: dict, level: int) -> Any:
    """Turn an evaluated slot value into the wire value of a typed slot.

    None means "no value": the tablet draws the widget as unavailable.
    """
    if value is None:
        return None
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
    """Give each (source slot, type) pair one device slot number."""

    def __init__(self) -> None:
        self.plan: list[dict] = []
        self._index: dict[tuple[int, str], int] = {}

    def ref(self, source: int, kind: str) -> dict:
        key = (source, kind)
        if key not in self._index:
            self._index[key] = len(self.plan) + 1
            self.plan.append({"d": self._index[key], "src": source, "type": kind})
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
        "v": DL_VERSION,
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
            str(PROTO),
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
    if version != str(PROTO):
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
    """
    low, high = response.get("proto", [0, 0])
    if not low <= PROTO <= high:
        reason = "tablet_new" if low > PROTO else "tablet_old"
        return {"steps": [], "status": "unsupported", "reason": reason}
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
    return {"steps": steps, "status": "", "reason": reason}


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
