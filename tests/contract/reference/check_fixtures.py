"""Check that the fixtures agree with the reference code. Run after gen_fixtures.py.

Also checks that gen_icons.py makes icons.json, from small fonts made here,
and the fixtures of version 2 (contract section 10).

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
    # 2 is a version both sides speak now: the case that is too new carries 3.
    newer = next(c for c in chunks["cases"] if c["name"] == "newer_layout_version")
    assert json.loads(newer["calls"][0]["data"])["v"] == 3 and newer["commit"] == "version"

    hello = load("hello.json")
    for case in hello["cases"]:
        got = tp.hello_steps(
            case["response"], stored_kid=case["stored_kid"], want_hash=case["want_hash"] or "x"
        )
        assert got["steps"] == case["expect"], case["name"]
        assert got["status"] == case.get("status", ""), case["name"]
    newest = next(c for c in hello["cases"] if c["name"] == "newer_tablet_protocol")
    assert newest["response"]["proto"] == [3, 4] and newest["reason"] == "tablet_new"
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
    version_2(contract)
    print("fixtures agree with the reference code")


def version_2(contract: dict) -> None:
    """The constants and fixtures of version 2."""
    # Every value of contract.json, byte for byte as gen_fixtures.py writes it.
    text = json.dumps(tp.contract_document(), indent=1) + "\n"
    assert (ROOT / "contract.json").read_text(encoding="utf-8") == text
    assert (contract["proto"], contract["proto_low"]) == (tp.PROTO, tp.PROTO_LOW) == (2, 1)
    assert contract["input_version"] == tp.INPUT_VERSION == 1
    assert contract["dl_version"] == tp.DL_VERSION == 2
    assert contract["caps_defaults"] == {"w": list(tp.WIDGET_KINDS), **tp.CAPS_DEFAULTS}
    assert contract["engine_caps"] == tp.ENGINE_CAPS
    assert contract["fonts"]["digits_glyphs"] == tp.DIGITS_GLYPHS
    assert contract["events"]["esphome.tab1_hello"]["d"] == "1|<mac>|<boot>"
    assert tp.parse_knock(tp.knock_data("aabbccddeeff", 3)) == ("aabbccddeeff", 3)
    assert tp.parse_knock("2|aabbccddeeff|3") is None
    levels = [level for _, level in ICONS["icons"].values()]
    assert ICONS["version"] == 2 and (levels.count(1), levels.count(2)) == (106, 91)

    kit_source = load("layout_v2_kit.source.json")
    for name in ("layout_v2_kit", "layout_v2_kit.nochoice"):
        meta = load(f"{name}.meta.json")
        data = (FIX / f"{name}.dl.json").read_bytes()
        compiled = tp.compile_device_layout_v2(kit_source["layout"], ICONS, meta["caps"])
        assert compiled["bytes"] == data, name
        assert tp.content_hash(data) == meta["hash"], name
        assert compiled["slots"] == meta["slots"], name
        assert compiled["dropped"] == meta["dropped"], name
        assert tp.canonical(json.loads(data)) == data, name
        assert tp.tablet_commit(data) == "", name
    kit = json.loads((FIX / "layout_v2_kit.dl.json").read_bytes())
    kit_meta = load("layout_v2_kit.meta.json")
    widgets = {}
    for page in kit["pages"]:
        for item in page["w"]:
            widgets[item["id"]] = item
            for widget in item.get("w", []):
                widgets[widget["id"]] = widget

    maths()

    events = load("input_v2.json")
    assert events["hash"] == kit_meta["hash"]
    default_sent = {d: v for d, v in events["sent"]}
    last = 0
    for case in events["cases"]:
        if "touch" in case:
            assert 0 <= case["page"] < len(kit["pages"]), case["name"]
            assert 0 <= case["end_page"] < len(kit["pages"]), case["name"]
            assert [d for d, _ in case["slots"]] == list(range(1, len(kit["slots"]) + 1))
            assert all(event[0] in widgets for event in case["events"]), case["name"]
        if "payload" not in case:
            continue
        verdict, parsed = tp.verify_input(
            case["payload"], mac=events["mac"], secret=bytes.fromhex(events["secret_hex"]),
            nonce=events["nonce"], last_counter=last, layouts=[events["hash"]],
        )
        assert verdict == case["verdict"], (case["name"], verdict)
        if verdict != "ok":
            assert case["run"] is None, case["name"]
            continue
        last = parsed["counter"]
        if "counter" in case:
            assert parsed["counter"] == case["counter"], case["name"]
        widget = widgets[parsed["widget"]]
        sent = {d: v for d, v in case["sent"]} if "sent" in case else default_sent
        if parsed["event"] == "tap":
            run = tp.check_tap(widget)
        else:
            run = tp.check_change(widget, parsed["value"], sent)
        assert run is case["run"], (case["name"], run)
        if "events" in case:
            first = case["events"][0]
            assert [first[0], first[1]] == [parsed["widget"], parsed["event"][0]], case["name"]

    state = load("state_v2.json")
    assert state["hash"] == kit_meta["hash"]
    for step in state["steps"]:
        for payload in step["payloads"]:
            assert len(payload.encode("utf-8")) <= tp.MAX_SET_BYTES
            assert tp.canonical(json.loads(payload)).decode("utf-8") == payload
            assert json.loads(payload)["h"] == state["hash"]
        assert all(show["id"] in widgets for show in step["show"]), step["note"]
    for value, roles, wire in state["colours"]:
        roles = {k: tp.colour(v) for k, v in roles.items()} if roles else None
        assert tp.to_colour(value, roles) == wire, (value, roles)
        if wire is not None:
            assert tp.coerce("n", value, ICONS, 2, "colour", roles) == wire

    hello = load("hello_v2.json")
    for case in hello["cases"]:
        want = hello["layouts"][case["want"]] if case["want"] else "x"
        got = tp.hello_steps(case["response"], stored_kid=case["stored_kid"], want_hash=want)
        assert got["steps"] == case["expect"], case["name"]
        assert got["status"] == case.get("status", ""), case["name"]
        assert got["reason"] == case.get("reason", ""), case["name"]
        assert got["dl"] == case["dl"], case["name"]
    assert hello["cases"][0]["response"]["caps"] == contract["engine_caps"]
    assert hello["layouts"]["2"] == kit_meta["hash"]

    commit = load("commit_v2.json")
    for case in commit["cases"]:
        raw = case["calls"][0]["data"].encode("utf-8")
        assert tp.content_hash(raw) == case["commit_hash"], case["name"]
        assert (tp.tablet_commit(raw) or "ok") == case["commit"], case["name"]
    for case in commit["ha"]:
        try:
            got = tp.compile_device_layout_v2(commit["source"], ICONS, case["caps"])["hash"]
            verdict = "ok"
        except tp.ContractError as error:
            got, verdict = None, error.code
        assert (verdict, got) == (case["expect"], case["hash"]), case["name"]
    cuts = tp.compile_device_layout_v2(commit["cuts_source"], ICONS, contract["engine_caps"])
    assert cuts["hash"] == commit["cuts"]["hash"]
    cut = commit["cuts"]["widgets"]
    for widget in json.loads(cuts["bytes"])["pages"][0]["w"][0]["w"]:
        assert widget == cut[str(widget["id"])], widget["id"]
    limits = contract["limits"]
    assert [len(cut[k]["track"]) for k in ("2", "3")] == [limits["max_track"]] * 2
    assert [len(cut[k][key]) for k in ("4", "5") for key in ("texts",)] == [limits["max_options"]] * 2
    assert all(len(cut["5"][key]) == limits["max_options"] for key in ("icons", "cols"))
    lengths = [len(text.encode("utf-8")) for text in cut["4"]["texts"] + cut["5"]["texts"] + cut["6"]["texts"]]
    assert max(lengths) == limits["max_option_text_bytes"] and cut["6"]["texts"][1] == "a" * 39


def maths() -> None:
    """Every vector of maths.json, worked out again by the reference code."""
    m = load("maths.json")
    assert m["linear"] == list(tp.LINEAR)
    for a, b, p, out in m["mix"]:
        assert tp.mix(a, b, p) == out, (a, b, p)
    for p, rows in m["mix_halves"].items():
        want = [[a, b] for a in range(256) for b in range(256) if (a * (100 - int(p)) + b * int(p)) % 100 == 50]
        assert [[a, b] for a, b, _ in rows] == want, p
        assert all(tp.mix(a, b, int(p)) == out for a, b, out in rows), p
    for c, value in m["lum"]:
        assert tp.lum(c) == value, c
    for a, b, value in m["contrast"]:
        assert tp.contrast(a, b) == value, (a, b)
    for c, out in m["readable"]:
        assert tp.readable(c) == out, c
    for c, b, t, out in m["legible"]:
        assert tp.legible(c, b, t) == out, (c, b, t)
    blend = m["blend"]
    for section in ("cases", "halves", "fused"):
        for a, b, out in blend[section]:
            assert tp.blend(a, b, blend["t"]) == out, (section, a, b)
    assert len(blend["fused"]) > 0
    themes, styles = m["themes"], m["styles"]
    for name, theme in themes.items():
        assert set(theme) == {*tp.THEME_COLOURS, *tp.RADII, "dark"}, name
    for case in m["card"]:
        tokens = tp.card_tokens(themes[case["theme"]], styles[case["style"]])
        assert case["tokens"] == {k: tokens[k] for k in ("ion", "onbg_pr", "bg")}, case
        got = tp.card_colours(tokens, bool(case["on"]), case["lit"], case["tint"])
        assert got == case["expect"], case
    for case in m["image"]:
        tokens = tp.card_tokens(themes[case["theme"]], {})
        card = tp.card_colours(tokens, bool(case["on"]), case["lit"], case["tint"])
        got = tp.image_look(
            tokens, card, bool(case["on"]), case["lit"], case["look"], case["w"], case["h"], case["c"]
        )
        assert got == case["expect"], case
    assert len(m["card"]) and len(m["image"])
    for case in m["label"]:
        assert tp.label_size(case["px"], case["text"], case["size"]) == case["expect"], case
    for case in m["clock"]:
        assert tp.clock_text(case["value"], case["age_s"], case["clk"]) == case["expect"], case
    for case in m["slider"]:
        for x, y, amount, value in case["presses"]:
            got = tp.slider_amount(case["rect"], case["look"], case["dir"], case["track"], case["r2"], x, y)
            assert got == amount, case
            run = tp.slider_length(case["rect"], case["look"], case["dir"], case["track"], case["r2"])
            assert tp.slider_value(got, case["min"], case["max"], case["step"], run) == value, case
        for shape in case["shapes"]:
            got = tp.slider_shape(
                case["rect"], case["look"], case["dir"], case["track"], case["r2"],
                shape["value"], case["min"], case["max"], bool(shape["change"]),
            )
            assert got == shape["expect"], (case, shape)
    for case in m["track"]:
        assert tp.track_pieces(case["n"], case["x0"], case["x1"]) == case["expect"], case
    for case in m["choice"]:
        cells = tp.choice_cells(case["n"], case["rows"], case["w"], case["h"], case["look"])
        assert cells == case["cells"], case
        for x, y, index in case["presses"]:
            assert tp.choice_at(cells, x, y) == index, case
    for case in m["steps"]:
        points = tp.line_points(case["values"], case["w"], case["h"], 4)
        assert points == case["points"] and tp.step_rects(points) == case["expect"], case
    for case in m["bars"]:
        assert tp.bar_marks(case["n"], case["mark"]) == case["expect"], case


if __name__ == "__main__":
    main()
