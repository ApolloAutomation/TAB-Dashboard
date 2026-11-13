"""A simulated TAB-1 tablet: the tablet side of the contract in Python.

It sits behind MemoryTabletLink and follows CONTRACT.md: chunk rules, hash
check, typed slots, pairing, auth checks on signed calls, a staged build
that the test finishes when it wants, knocks and signed input.
"""

from __future__ import annotations

import json
from typing import Any

from homeassistant.core import HomeAssistant

from custom_components.apollo_tab import protocol as tp
from custom_components.apollo_tab.maker import device
from custom_components.apollo_tab.tablet_link import LinkError

SIGNED = ("tab_commit", "tab_set", "tab_ack", "tab_clear")
OPEN_WITHOUT_SESSION = ("tab_hello", "tab_status", "tab_pair", "tab_layout")
# Session nonces of this boot that a tab_hello may not use again (contract 3).
NONCE_RING = 16


class FakeTablet:
    """One simulated tablet with the engine."""

    def __init__(
        self,
        hass: HomeAssistant,
        mac: str,
        *,
        psk: bytes | None = bytes(range(32)),
        caps: dict | None = None,
        proto: tuple[int, int] = (1, 1),
        engine: str = "0.1.0",
        boot: int = 1,
    ) -> None:
        """Start empty: connected, with the engine, not paired, no layout."""
        self.hass = hass
        self.mac = mac
        self.hex = tp.mac_hex(mac)
        self.psk = psk
        # Whether its software can take an API key (ESPHome gives one to a
        # tablet that can and has none, then connects again with it).
        self.encryption_supported = True
        self.connected = True
        self.has_engine = True
        self.caps = {"w": list(device.WIDGET_KINDS), **device.CAPS_DEFAULTS}
        self.caps.update(caps or {})
        self.proto = list(proto)
        self.engine = engine
        self.boot = boot
        # Pairing and session.
        self.secret: bytes | None = None
        self.nonce: str | None = None
        self.used_nonces: list[str] = []
        self.last_n = 0
        self.counter = 0
        # Layouts.
        self.active = ""
        self.active_slots = ""
        self.values: dict[int, Any] = {}
        self.staged = ""
        self.staged_slots = ""
        self.staged_values: dict[int, Any] = {}
        self.build = ""
        self.transfer: dict[str, Any] | None = None
        self.stored = ""
        # Test controls.
        self.hold_build = False
        self.fail_build: str | None = None
        self.fail_next: dict[str, str] = {}
        self.timeout_next: set[str] = set()
        # What happened.
        self.calls: list[tuple[str, dict]] = []
        self.acks: list[tuple[int, bool, str]] = []
        self.sets: list[dict] = []
        self.refused: list[str] = []

    # ------------------------------------------------------------ helpers

    @property
    def paired(self) -> bool:
        """Return whether the tablet holds a secret."""
        return self.secret is not None

    @property
    def key(self) -> bytes | None:
        """Return the secret in use: none without an API key (contract 6.1)."""
        return self.secret if self.psk is not None else None

    def kid(self) -> str:
        """Return the id of the secret in use, or empty."""
        return tp.kid(self.key) if self.key is not None else ""

    def calls_of(self, action: str) -> list[dict]:
        """Return the arguments of every call of one action."""
        return [args for name, args in self.calls if name == action]

    def _auth(self, action: str, auth: Any, body: str) -> bool:
        """Check a signed call; remember the counter when it passes."""
        if self.key is None:
            return True
        if self.nonce is None:
            return False
        ok, last = tp.check_auth(
            auth,
            secret=self.key,
            mac=self.hex,
            nonce=self.nonce,
            last_n=self.last_n,
            action=action,
            body=body,
        )
        if ok:
            self.last_n = last
        return ok

    def _mem(self) -> dict:
        """Return a memory report."""
        return {"int": 61000, "psram": 28000000, "block": 16000000}

    # -------------------------------------------------------------- calls

    async def async_call(self, action: str, args: dict[str, Any]) -> dict | None:
        """Handle one call from HA."""
        self.calls.append((action, dict(args)))
        if action in self.timeout_next:
            self.timeout_next.discard(action)
            raise LinkError("timeout")
        if code := self.fail_next.pop(action, None):
            raise LinkError(code)
        handler = getattr(self, f"_on_{action}")
        return handler(**args)

    def _on_tab_hello(self, nonce: str, auth: str) -> dict:
        """Answer the handshake; start a session when allowed."""
        session = 0
        if (
            tp.is_hex(nonce, 32)
            and nonce not in self.used_nonces
            and (
                self.key is None
                or tp.check_auth(
                    auth,
                    secret=self.key,
                    mac=self.hex,
                    nonce=nonce,
                    last_n=0,
                    action="tab_hello",
                )[0]
            )
        ):
            self.nonce = nonce
            self.used_nonces = [*self.used_nonces, nonce][-NONCE_RING:]
            self.last_n = 0
            self.counter = 0
            session = 1
        return {
            "proto": list(self.proto),
            "engine": self.engine,
            "boot": self.boot,
            "layout": self.active,
            "kid": self.kid(),
            "enc": 1 if self.psk is not None else 0,
            "session": session,
            "caps": dict(self.caps),
            "mem": self._mem(),
        }

    def _on_tab_status(self) -> dict:
        """Report what is on screen; a build that is not held finishes now."""
        if self.staged and not self.hold_build:
            self.finish_build()
        return {
            "layout": self.active,
            "staged": self.staged,
            "build": self.build,
            "mem": self._mem(),
            "session": 1 if self.nonce is not None else 0,
        }

    def _on_tab_pair(self, nonce: str, wrapped: str, kid: str) -> dict:
        """Take a new secret wrapped under the API key."""
        if self.psk is None:
            raise LinkError("needs_encryption")
        if not (tp.is_hex(nonce, 32) and tp.is_hex(wrapped, 64) and tp.is_hex(kid, 16)):
            raise LinkError("bad_key")
        secret = tp.unwrap_secret(self.psk, self.hex, nonce, wrapped)
        if tp.kid(secret) != kid:
            raise LinkError("bad_key")
        self.secret = secret
        self.nonce = None
        return {}

    def _on_tab_layout(
        self, hash: str, seq: int, total: int, size: int, data: str
    ) -> dict:
        """Take one chunk."""
        if seq == 0:
            # A new transfer drops the unfinished one and any build.
            self.transfer = None
            self.staged = ""
            self.staged_slots = ""
            self.build = ""
            limit = min(self.caps["max_layout"], device.MAX_LAYOUT_BYTES)
            if size > limit:
                raise LinkError("too_big")
            self.transfer = {
                "hash": hash,
                "total": total,
                "size": size,
                "next": 0,
                "buf": b"",
            }
        transfer = self.transfer
        if (
            transfer is None
            or seq != transfer["next"]
            or (hash, total, size)
            != (transfer["hash"], transfer["total"], transfer["size"])
        ):
            self.transfer = None
            raise LinkError("order")
        raw = data.encode("utf-8")
        if len(transfer["buf"]) + len(raw) > transfer["size"]:
            self.transfer = None
            raise LinkError("size")
        transfer["buf"] += raw
        transfer["next"] += 1
        return {}

    def _on_tab_commit(self, hash: str, auth: str) -> dict:
        """Check the received layout and stage it."""
        if not self._auth("tab_commit", auth, hash):
            self.refused.append("tab_commit")
            raise LinkError("auth")
        if hash == self.active:
            # Already on screen: success, and nothing changes (contract 5).
            if self.transfer and self.transfer["hash"] == hash:
                self.transfer = None
            return {}
        transfer = self.transfer
        if (
            transfer is None
            or transfer["hash"] != hash
            or transfer["next"] != transfer["total"]
            or len(transfer["buf"]) != transfer["size"]
        ):
            raise LinkError("incomplete")
        data = transfer["buf"]
        if device.content_hash(data) != hash:
            raise LinkError("hash")
        try:
            layout = json.loads(data)
        except ValueError as err:
            raise LinkError("parse") from err
        if not isinstance(layout, dict) or not isinstance(layout.get("pages"), list):
            raise LinkError("parse")
        if layout.get("v") != 1:
            raise LinkError("version")
        slots = layout.get("slots", "")
        if len(layout["pages"]) > 20 or len(slots) > self.caps["max_slots"]:
            raise LinkError("limits")
        self.transfer = None
        self.staged = hash
        self.staged_slots = slots
        self.staged_values = dict.fromkeys(range(1, len(slots) + 1))
        self.build = ""
        return {}

    def _on_tab_set(self, data: str, auth: str) -> dict:
        """Apply slot values to the active or the staged layout."""
        if not self._auth("tab_set", auth, data):
            self.refused.append("tab_set")
            raise LinkError("auth")
        try:
            message = json.loads(data)
            pairs = message["v"]
            target = message["h"]
        except (ValueError, KeyError, TypeError) as err:
            raise LinkError("parse") from err
        if target and target == self.staged:
            values, types = self.staged_values, self.staged_slots
        elif target and target == self.active:
            values, types = self.values, self.active_slots
        else:
            raise LinkError("hash")
        if message.get("f") == 1:
            for slot in values:
                values[slot] = None
        for slot, value in pairs:
            if not isinstance(slot, int) or not 1 <= slot <= len(types):
                continue
            if value is not None and not _type_ok(types[slot - 1], value):
                continue
            values[slot] = value
        self.sets.append(message)
        return {}

    def _on_tab_ack(self, n: int, ok: bool, code: str, auth: str) -> None:
        """Record an ack; a refused one is ignored."""
        if not self._auth("tab_ack", auth, tp.ack_body(n, ok, code)):
            self.refused.append("tab_ack")
            return
        self.acks.append((n, ok, code))

    def _on_tab_clear(self, auth: str) -> dict:
        """Forget every layout and show the waiting screen."""
        if not self._auth("tab_clear", auth, ""):
            self.refused.append("tab_clear")
            raise LinkError("auth")
        self.active = ""
        self.active_slots = ""
        self.values = {}
        self.staged = ""
        self.transfer = None
        self.stored = ""
        return {}

    # ------------------------------------------------------ test controls

    def finish_build(self, code: str | None = None) -> None:
        """End the staged build: show it, or keep the old layout with code."""
        if not self.staged:
            return
        code = code if code is not None else self.fail_build
        if code:
            self.build = code
            self.staged = ""
            return
        self.active = self.staged
        self.active_slots = self.staged_slots
        self.values = self.staged_values
        self.staged = ""
        self.build = ""
        self.stored = self.active

    def reboot(self) -> None:
        """Start again with the stored layout, no values and no session."""
        self.boot += 1
        self.nonce = None
        self.used_nonces = []
        self.last_n = 0
        self.counter = 0
        self.staged = ""
        self.transfer = None
        self.active = self.stored
        self.values = dict.fromkeys(self.values)

    def slot(self, number: int) -> Any:
        """Return the active layout's value of one slot."""
        return self.values.get(number)

    def tap(
        self,
        widget: int,
        *,
        event: str = "t",
        confirmed: bool = False,
        value: float | None = None,
        layout: str | None = None,
        secret: bytes | None = None,
        nonce: str | None = None,
        counter: int | None = None,
    ) -> dict:
        """Fire a signed input event as the tablet would; return its data.

        It fires even when the tablet would send nothing (no API key), so a
        test can play a device that still signs.
        """
        if counter is None:
            self.counter += 1
            counter = self.counter
        payload = tp.input_payload(
            self.hex,
            nonce if nonce is not None else (self.nonce or ""),
            counter,
            layout if layout is not None else self.active,
            widget,
            event,
            confirmed,
            value,
        )
        key = secret if secret is not None else self.secret
        data = {"d": payload, "s": tp.sign(key or bytes(32), payload)}
        self.hass.bus.async_fire("esphome.tab1_input", {"device_id": "x", **data})
        return data

    def knock(self, *, mac: str | None = None, boot: int | None = None) -> None:
        """Fire the unsigned knock event."""
        payload = f"1|{mac or self.hex}|{self.boot if boot is None else boot}"
        self.hass.bus.async_fire("esphome.tab1_hello", {"device_id": "x", "d": payload})


def _type_ok(kind: str, value: Any) -> bool:
    """Return whether a wire value fits a slot type."""
    if kind == "t":
        return isinstance(value, str)
    if kind == "b":
        return value in (0, 1) and not isinstance(value, float)
    if kind in ("n", "i"):
        return isinstance(value, int | float) and not isinstance(value, bool)
    if kind == "l":
        return isinstance(value, list)
    return False
