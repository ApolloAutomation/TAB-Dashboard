"""The TAB-1 tablet contract, version 1: chunks, state, pairing, signatures.

``contract/CONTRACT.md`` in the tests is the specification; the device
layout itself is compiled in ``maker/device.py``. Everything here is pure
Python and is checked byte for byte against the contract's fixtures.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from pathlib import Path
from typing import Any

from .maker.device import (
    CAPS_DEFAULTS,
    CHUNK_BYTES,
    ContractError,
    canonical,
    num,
)

__all__ = ["CAPS_DEFAULTS", "ContractError"]

PROTO = 1
# The contract versions this integration speaks, lowest first.
PROTO_RANGE = (1, 1)

MAX_SET_BYTES = 12000
MAX_INPUT_PAYLOAD = 200
INPUT_FIELDS = 9

KID_LABEL = b"apollo-tab1 kid v1"
WRAP_LABEL = "apollo-tab1 wrap v1"
CALL_LABEL = "apollo-tab1 call v1"

# Knock schedule of the tablet, in seconds after the API connection opens.
KNOCK_FIRST_S = 3
KNOCK_REPEATS = 5
KNOCK_MAX_S = 300

# Error codes that cannot succeed on a retry with the same layout and caps.
DETERMINISTIC_ERRORS = frozenset({"too_big", "limits", "version", "parse"})

# Ack codes (contract 7.3).
ACK_DONE = ""
ACK_CONFIRM = "confirm"
ACK_DENIED = "denied"
ACK_FAILED = "failed"
ACK_STALE = "stale"
ACK_BUSY = "busy"

HEX = frozenset("0123456789abcdef")

CONTRACT_DIR = Path(__file__).parent / "contract"


def load_contract() -> tuple[dict, dict]:
    """Return (contract.json, icons.json) from the runtime copy.

    Reads files, so call it from an executor job.
    """
    contract = json.loads((CONTRACT_DIR / "contract.json").read_text("utf-8"))
    icons = json.loads((CONTRACT_DIR / "icons.json").read_text("utf-8"))
    return contract, icons


def new_nonce() -> str:
    """Return 32 lower-case hex characters from a secure random source."""
    return secrets.token_hex(16)


def new_secret() -> bytes:
    """Return a fresh 32-byte pairing secret."""
    return secrets.token_bytes(32)


def is_hex(text: Any, length: int) -> bool:
    """Return whether text is exactly length lower-case hex characters."""
    return isinstance(text, str) and len(text) == length and set(text) <= HEX


def mac_hex(mac: str) -> str:
    """Return a MAC as the contract writes it: 12 lower-case hex, no separators."""
    return mac.replace(":", "").replace("-", "").lower()


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
        """Write the gathered pairs as one payload."""
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


def call_auth(
    secret: bytes | None, mac: str, nonce: str, n: int, action: str, body: str = ""
) -> str:
    """Return the auth argument of one call from HA to a paired tablet.

    "<n>.<32 hex>". n is 0 for tab_hello (nonce is then the new session's
    nonce). For every other call n starts at 1 after tab_hello and goes up
    with every signed call. body is: the hash for tab_commit, the data text
    for tab_set, "<n>|<0 or 1>|<code>" for tab_ack, empty for tab_hello and
    tab_clear. Without a secret (tablet not paired) the auth is empty.
    """
    if secret is None:
        return ""
    message = f"{CALL_LABEL}|{mac}|{nonce}|{n}|{action}|{body}".encode()
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
    one. Used by the simulated tablet in the tests.
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


def input_value(value: float | None) -> str:
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
    value: float | None = None,
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


def input_mac(data: Any) -> str | None:
    """Return the MAC named inside an input or knock payload, or None.

    HA finds the tablet by this MAC and never by the event's device_id
    (contract 2.2). Nothing else of the payload is trusted here.
    """
    if not isinstance(data, dict):
        return None
    payload = data.get("d")
    if not isinstance(payload, str) or not payload.isascii():
        return None
    parts = payload.split("|")
    if len(parts) < 2 or not is_hex(parts[1], 12):
        return None
    return parts[1]


def verify_input(
    data: dict,
    *,
    mac: str,
    secret: bytes | None,
    nonce: str | None,
    last_counter: int,
    layouts: tuple[str, ...] | list[str] | set[str],
) -> tuple[str, dict | None]:
    """Check one esphome.tab1_input event (contract 7.3).

    nonce is the current session's, or None while HA holds no session: then
    no input is the current session's, not even one with an empty nonce.

    layouts holds the hashes HA keeps bindings for on this tablet: the
    wanted one, and the one before it until the tablet confirms the switch.

    Returns (verdict, parsed). verdict is "ok" or the reason it is dropped:
    malformed, version, wrong_tablet, not_paired, bad_signature,
    stale_session, replay, stale_layout.
    """
    payload = data.get("d")
    signature = data.get("s")
    if not isinstance(payload, str) or not payload.isascii():
        return "malformed", None
    if not is_hex(signature, 32):
        return "malformed", None
    parts = payload.split("|")
    if len(parts) != INPUT_FIELDS or len(payload) > MAX_INPUT_PAYLOAD:
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
    if nonce is None or p_nonce != nonce:
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
        "layout": p_layout,
    }
    if event == "c":
        try:
            parsed["value"] = num(float(value))
        except ValueError, ContractError:
            return "malformed", None
    elif value:
        return "malformed", None
    if parsed["counter"] <= last_counter:
        return "replay", None
    if p_layout not in layouts:
        return "stale_layout", parsed
    return "ok", parsed


def parse_knock(data: Any) -> tuple[str, int] | None:
    """Return (mac, boot) of an esphome.tab1_hello knock, or None."""
    if not isinstance(data, dict):
        return None
    payload = data.get("d")
    if not isinstance(payload, str) or not payload.isascii() or len(payload) > 64:
        return None
    parts = payload.split("|")
    if len(parts) != 3 or parts[0] != str(PROTO) or not is_hex(parts[1], 12):
        return None
    if not parts[2].isdigit() or len(parts[2]) > 10:
        return None
    return parts[1], int(parts[2])


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


def proto_verdict(response: dict) -> str:
    """Return "" when HA speaks the tablet's range, else tablet_old or tablet_new."""
    proto = response.get("proto")
    try:
        low, high = int(proto[0]), int(proto[1])  # type: ignore[index]
    except TypeError, ValueError, IndexError, KeyError:
        return "tablet_old"
    if high < PROTO_RANGE[0]:
        return "tablet_old"
    if low > PROTO_RANGE[1]:
        return "tablet_new"
    if not low <= PROTO <= high:
        return "tablet_old" if high < PROTO else "tablet_new"
    return ""


def hello_steps(
    response: dict, *, stored_kid: str | None, want_hash: str | None
) -> dict:
    """Return what HA does after a tab_hello response.

    steps is a list of: "pair", "hello" (greet again, a pairing ends the
    session), "send_layout", "send_state". status is "" or "unsupported".
    """
    reason = proto_verdict(response)
    if reason:
        return {"steps": [], "status": "unsupported", "reason": reason}
    steps: list[str] = []
    if response.get("enc") == 1:
        if (
            not stored_kid
            or response.get("kid") != stored_kid
            or response.get("session") != 1
        ):
            # Another kid, none, or the same kid with a refused signature:
            # the secrets differ.
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

    "building": ask again. "shown": the layout is on screen. Anything else
    is the reason the build ended without showing it.
    """
    if response.get("layout") == want_hash:
        return "shown"
    if response.get("staged") == want_hash:
        return "building"
    build = response.get("build")
    return build if isinstance(build, str) and build else "replaced"


def caps_of(response: dict) -> dict[str, Any]:
    """Return the tablet's caps with the contract defaults for missing keys."""
    caps = response.get("caps")
    if not isinstance(caps, dict):
        caps = {}
    merged = {"w": None, **CAPS_DEFAULTS}
    for key, value in caps.items():
        if key in merged:
            merged[key] = value
    if merged["w"] is None:
        merged.pop("w")
    return merged
