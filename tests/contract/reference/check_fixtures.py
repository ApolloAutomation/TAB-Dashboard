"""Check that the fixtures agree with the reference code. Run after gen_fixtures.py.

Also checks that gen_icons.py makes icons.json, from small fonts made here.

Usage: python -B reference/check_fixtures.py   (from the contract folder)
"""

import contextlib
import io
import json
import struct
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gen_icons  # noqa: E402
import tabproto as tp  # noqa: E402

ROOT = HERE.parent
FIX = ROOT / "fixtures"
ICONS = json.loads((ROOT / "icons.json").read_text(encoding="utf-8"))


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def icon_font(glyphs):
    """Return a font with only the two tables gen_icons.py reads.

    glyphs lists (code point, name) for glyph 1 and up; glyph 0 is .notdef.
    A name that is a number is stored as that standard Macintosh index, a
    text as a string of the font's own ('post' format 2).
    """
    index, strings = [0], []
    for _, name in glyphs:
        if isinstance(name, int):
            index.append(name)
        else:
            index.append(258 + len(strings))
            strings.append(bytes([len(name)]) + name.encode("latin1"))
    post = struct.pack(f">I28xH{len(index)}H", 0x00020000, len(index), *index)
    post += b"".join(strings)
    groups = b"".join(
        struct.pack(">III", code, code, glyph) for glyph, (code, _) in enumerate(glyphs, 1)
    )
    cmap = struct.pack(">HHHHI", 0, 1, 3, 10, 12)
    cmap += struct.pack(">HHIII", 12, 0, 16 + len(groups), 0, len(glyphs)) + groups
    font = struct.pack(">IH6x", 0x00010000, 2)
    font += struct.pack(">4sIII", b"cmap", 0, 44, len(cmap))
    font += struct.pack(">4sIII", b"post", 0, 44 + len(cmap), len(post))
    return font + cmap + post


def make_icons(font):
    """Run gen_icons.py on a font. Return (the file it wrote or None, its error)."""
    with tempfile.TemporaryDirectory() as folder:
        source, out = Path(folder, "font.ttf"), Path(folder, "icons.json")
        source.write_bytes(font)
        argv, sys.argv = sys.argv, ["gen_icons.py", str(source), str(out)]
        error = ""
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                gen_icons.main()
        except SystemExit as stop:
            error = str(stop)
        finally:
            sys.argv = argv
        return (out.read_bytes() if out.exists() else None), error


def icons() -> None:
    """gen_icons.py makes icons.json from a font, however it names its glyphs."""
    names = gen_icons.MAC_GLYPHS
    assert len(names) == 258 and len(set(names)) == 258
    assert (names[0], names[14], names[239], names[257]) == (
        ".notdef", "plus", "minus", "dcroat",
    )
    committed = (ROOT / "icons.json").read_bytes()
    glyphs = [(code, name.removeprefix("mdi:")) for name, (code, _) in ICONS["icons"].items()]
    assert make_icons(icon_font(glyphs)) == (committed, "")
    # A font may name plus and minus by their standard index, 14 and 239.
    standard = [(code, {"plus": 14, "minus": 239}.get(name, name)) for code, name in glyphs]
    assert make_icons(icon_font(standard)) == (committed, "")
    # A name the font lacks stops the script, and nothing is written.
    for font in (glyphs, standard):
        lacking = [(code, name) for code, name in font if name not in ("minus", 239)]
        assert make_icons(icon_font(lacking)) == (None, "not in the font: minus")


def main() -> None:
    for name in ("layout_small", "layout_all_cards"):
        source = load(f"{name}.source.json")
        meta = load(f"{name}.meta.json")
        data = (FIX / f"{name}.dl.json").read_bytes()
        compiled = tp.compile_device_layout(source["layout"], ICONS)
        assert compiled["bytes"] == data, name
        assert tp.content_hash(data) == meta["hash"], name
        assert compiled["slots"] == meta["slots"], name
        assert tp.canonical(json.loads(data)) == data, name

    chunks = load("chunks.json")
    good = chunks["cases"][0]
    joined = "".join(call["data"] for call in good["calls"]).encode("utf-8")
    assert tp.content_hash(joined) == chunks["hash"]
    assert all(len(call["data"].encode("utf-8")) <= 3000 for call in good["calls"])

    events = load("input_events.json")
    last = 0
    for case in events["cases"]:
        verdict, parsed = tp.verify_input(
            case["data"],
            mac=events["mac"],
            secret=bytes.fromhex(events["secret_hex"]),
            nonce=events["nonce"],
            last_counter=last,
            layouts=case.get("kept", [events["hash"]]),
        )
        assert verdict == case["expect"], (case["name"], verdict)
        if verdict in ("ok", "stale_layout"):
            last = parsed["counter"]

    pair = load("pair.json")
    case = pair["cases"][0]["call"]
    secret = tp.unwrap_secret(
        bytes.fromhex(pair["psk_hex"]), pair["mac"], case["nonce"], case["wrapped"]
    )
    assert secret.hex() == pair["secret_hex"] and tp.kid(secret) == case["kid"]

    for case in chunks["cases"]:
        for call in case["calls"]:
            assert len(call["data"].encode("utf-8")) <= tp.CHUNK_BYTES
    for name in ("not_json", "wrong_shape", "newer_layout_version", "too_many_pages"):
        case = next(c for c in chunks["cases"] if c["name"] == name)
        raw = case["calls"][0]["data"].encode("utf-8")
        assert tp.content_hash(raw) == case["commit_hash"], name

    hello = load("hello.json")
    for case in hello["cases"]:
        got = tp.hello_steps(
            case["response"], stored_kid=case["stored_kid"], want_hash=case["want_hash"] or "x"
        )
        assert got["steps"] == case["expect"], case["name"]
        assert got["status"] == case.get("status", ""), case["name"]
    ok, _ = tp.check_auth(
        hello["call"]["auth"], secret=bytes.fromhex(hello["secret_hex"]), mac=hello["mac"],
        nonce=hello["call"]["nonce"], last_n=5, action="tab_hello",
    )
    assert ok

    status = load("status.json")
    for case in status["cases"]:
        assert tp.status_verdict(case["response"], status["want_hash"]) == case["expect"]
        assert case["response"]["session"] in (0, 1), case["name"]
    for case in status["knock"]:
        got = tp.knock_step(session=case["session"], status=case["status"])
        assert got == case["expect"], case["name"]
    upper = next(c for c in chunks["cases"] if c["name"] == "header_hash_not_lower_case_hex")
    assert upper["calls"][0]["hash"] != chunks["hash"]

    auth = load("auth.json")
    secret = bytes.fromhex(auth["secret_hex"])
    last = 0
    for case in auth["paired"]:
        ok, last = tp.check_auth(
            case["auth"], secret=secret, mac=auth["mac"], nonce=auth["nonce"],
            last_n=last, action=case["action"], body=case["body"],
        )
        assert ("ok" if ok else "auth") == case["expect"], case["name"]
    for case in auth["unpaired"]:
        ok, _ = tp.check_auth(
            case["auth"], secret=None, mac=auth["mac"], nonce=auth["nonce"],
            last_n=0, action=case["action"], body=case["body"],
        )
        assert ok, case["name"]
    for key, want in (("auth", True), ("bad_auth", False)):
        ok, _ = tp.check_auth(
            auth["hello"][key], secret=secret, mac=auth["mac"],
            nonce=auth["hello"]["nonce"], last_n=3, action="tab_hello",
        )
        assert ok is want, key
    no_key = auth["no_api_key"]
    assert no_key["hello"]["expect_kid"] == "" and no_key["hello"]["expect_enc"] == 0
    for case in no_key["calls"]:
        ok, _ = tp.check_auth(
            case["auth"], secret=None, mac=auth["mac"], nonce=auth["nonce"],
            last_n=0, action=case["action"], body=case["body"],
        )
        assert ok and case["expect"] == "ok", case["name"]

    contract = json.loads((ROOT / "contract.json").read_text(encoding="utf-8"))
    assert contract["caps_defaults"]["max_slots"] == tp.MAX_SLOTS
    assert tp.knock_times(40) == [3, 6, 9, 12, 15, 21, 33]

    stream = load("state_stream.json")
    meta = load("layout_all_cards.meta.json")
    for entry in meta["slots"]:
        raw = stream["raw_values_by_source_slot"][str(entry["src"])]
        wire = tp.coerce(entry["type"], raw, ICONS, ICONS["version"])
        assert wire == stream["wire_values_by_device_slot"][str(entry["d"])], entry
    for step in stream["steps"]:
        for payload in step["payloads"]:
            assert len(payload.encode("utf-8")) <= tp.MAX_SET_BYTES
            assert tp.canonical(json.loads(payload)).decode("utf-8") == payload

    icons()
    print("fixtures agree with the reference code")


if __name__ == "__main__":
    main()
