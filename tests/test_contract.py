"""The integration reproduces every fixture of the TAB-1 contract byte for byte."""

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from custom_components.apollo_tab import protocol as tp
from custom_components.apollo_tab.maker import device
from custom_components.apollo_tab.maker.convert import convert_dashboard
from custom_components.apollo_tab.maker.schema import validate_component

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "tests" / "contract"
FIX = CONTRACT / "fixtures"
RUNTIME = ROOT / "custom_components" / "apollo_tab" / "contract"
LIBRARY = ROOT / "custom_components" / "apollo_tab" / "library"
ICONS = json.loads((CONTRACT / "icons.json").read_text(encoding="utf-8"))
CONTRACT_JSON = json.loads((CONTRACT / "contract.json").read_text(encoding="utf-8"))


def load(name: str):
    """Return one fixture file as JSON."""
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def library() -> tuple[dict, dict]:
    """Return the built-in components and themes, as the fixtures were made."""
    components = {}
    for path in sorted((LIBRARY / "components").glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            component = validate_component(doc)
            component["source"] = "builtin"
            components[component["id"]] = component
    themes = {
        theme["id"]: {k: v for k, v in theme.items() if k != "id"}
        for theme in json.loads((LIBRARY / "themes.json").read_text(encoding="utf-8"))
    }
    return components, themes


def test_runtime_copy_matches_the_contract() -> None:
    """The runtime icons.json and contract.json are the contract's files."""
    for name in ("icons.json", "contract.json"):
        assert (RUNTIME / name).read_bytes() == (CONTRACT / name).read_bytes()
    contract, icons = tp.load_contract()
    assert contract == CONTRACT_JSON
    assert icons == ICONS


def test_reference_check_passes() -> None:
    """The contract copy agrees with its own reference code."""
    spec = importlib.util.spec_from_file_location(
        "tab_check_fixtures", CONTRACT / "reference" / "check_fixtures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


def test_constants_match_contract_json() -> None:
    """Limits, defaults and labels equal contract.json."""
    limits = CONTRACT_JSON["limits"]
    assert limits["chunk_bytes"] == device.CHUNK_BYTES
    assert limits["max_layout_bytes"] == device.MAX_LAYOUT_BYTES
    assert limits["max_set_bytes"] == tp.MAX_SET_BYTES
    assert limits["max_text_bytes"] == device.MAX_TEXT_BYTES
    assert limits["max_list"] == device.MAX_LIST
    assert limits["max_number"] == device.MAX_NUMBER
    assert limits["max_pages"] == device.MAX_PAGES
    assert limits["max_nav"] == device.MAX_NAV
    assert limits["max_slots"] == device.MAX_SLOTS
    assert limits["max_widgets"] == device.MAX_WIDGETS
    assert limits["max_input_payload"] == tp.MAX_INPUT_PAYLOAD
    assert CONTRACT_JSON["proto"] == tp.PROTO
    assert CONTRACT_JSON["dl_version"] == device.DL_VERSION
    assert CONTRACT_JSON["caps_defaults"] == {
        "w": list(device.WIDGET_KINDS),
        **device.CAPS_DEFAULTS,
    }
    assert CONTRACT_JSON["widget_kinds"] == list(device.WIDGET_KINDS)
    assert CONTRACT_JSON["policies"] == list(device.POLICIES)
    assert CONTRACT_JSON["label_sizes"] == list(device.LABEL_SIZES)
    assert CONTRACT_JSON["chart_kinds"] == list(device.CHART_KINDS)
    assert CONTRACT_JSON["theme_colours"] == list(device.THEME_COLOURS)
    assert CONTRACT_JSON["style_colours"] == list(device.STYLE_COLOURS)
    assert set(CONTRACT_JSON["deterministic_errors"]) == tp.DETERMINISTIC_ERRORS
    assert CONTRACT_JSON["labels"] == {
        "kid": tp.KID_LABEL.decode(),
        "wrap": tp.WRAP_LABEL,
        "call": tp.CALL_LABEL,
    }
    assert CONTRACT_JSON["knock"] == {
        "first_s": tp.KNOCK_FIRST_S,
        "repeats": tp.KNOCK_REPEATS,
        "max_s": tp.KNOCK_MAX_S,
    }
    assert CONTRACT_JSON["ack_codes"] == [
        tp.ACK_DONE,
        tp.ACK_CONFIRM,
        tp.ACK_DENIED,
        tp.ACK_FAILED,
        tp.ACK_STALE,
        tp.ACK_BUSY,
    ]


@pytest.mark.parametrize("name", ["layout_small", "layout_all_cards"])
def test_device_layout_bytes_and_hash(name: str, library) -> None:
    """Both fixture layouts compile to the exact device layout bytes."""
    source = load(f"{name}.source.json")
    meta = load(f"{name}.meta.json")
    expected = (FIX / f"{name}.dl.json").read_bytes()
    compiled = device.compile_device_layout(source["layout"], ICONS)
    assert compiled["bytes"] == expected
    assert compiled["hash"] == meta["hash"] == device.content_hash(expected)
    assert compiled["size"] == meta["size"] == len(expected)
    assert compiled["slots"] == meta["slots"]
    assert compiled["dropped"] == meta["dropped"]


@pytest.mark.parametrize("name", ["layout_small", "layout_all_cards"])
def test_convert_still_makes_the_fixture_layout(name: str, library) -> None:
    """Converting the fixture dashboard gives the fixture layout and slots."""
    components, themes = library
    source = load(f"{name}.source.json")
    result = convert_dashboard(
        source["dashboard"], components=components, themes=themes, approved=set()
    )
    assert result["layout"] == source["layout"]
    assert result["bindings"]["slots"] == source["bindings"]["slots"]
    assert result["warnings"] == source["warnings"]
    # Every action entry, with what the tablet path needs (demo, entities).
    assert result["bindings"]["actions"] == source["bindings"]["actions"]
    for action in source["bindings"]["actions"].values():
        assert action["demo"] is False
        assert all(isinstance(entity, str) for entity in action["entities"])
    compiled = device.compile_device_layout(result["layout"], ICONS)
    assert compiled["bytes"] == (FIX / f"{name}.dl.json").read_bytes()


def test_down_levelled_layout() -> None:
    """A tablet without charts gets the nochart bytes and hash."""
    source = load("layout_all_cards.source.json")
    meta = load("layout_all_cards.nochart.meta.json")
    compiled = device.compile_device_layout(source["layout"], ICONS, meta["caps"])
    assert compiled["bytes"] == (FIX / "layout_all_cards.nochart.dl.json").read_bytes()
    assert compiled["hash"] == meta["hash"]
    assert compiled["size"] == meta["size"]
    assert compiled["slots"] == meta["slots"]
    assert compiled["dropped"] == meta["dropped"]
    assert meta["dropped"]


def test_coercion_table() -> None:
    """Every sample raw value turns into the fixture's wire value."""
    stream = load("state_stream.json")
    meta = load("layout_all_cards.meta.json")
    for entry in meta["slots"]:
        raw = stream["raw_values_by_source_slot"][str(entry["src"])]
        wire = device.coerce(entry["type"], raw, ICONS, ICONS["version"])
        assert wire == stream["wire_values_by_device_slot"][str(entry["d"])], entry


@pytest.mark.parametrize(
    ("kind", "raw", "wire"),
    [
        ("b", "on", 1),
        ("b", "off", 0),
        ("b", "unavailable", 0),
        ("b", 2, 1),
        ("b", 0.0, 0),
        ("b", True, 1),
        ("b", None, None),
        ("n", "21.45678", 21.457),
        ("n", "x", None),
        ("n", True, None),
        ("n", 5e12, 1_000_000_000),
        ("n", float("nan"), None),
        ("t", 21.0, "21"),
        ("t", True, "true"),
        ("t", [1, "a"], "1, a"),
        ("t", "é" * 200, "é" * 127),
        ("l", [1, "2", "x", None, 3.33333], [1, 2, 3.333]),
        ("l", "1,2", []),
        ("i", "mdi:lightbulb", 983861),
        ("i", "mdi:no-such-icon", 0),
        ("i", "/local/a.jpg", 0),
    ],
)
def test_coerce_rules(kind: str, raw, wire) -> None:
    """Conversion follows isOn, toNumber, the text cut and the icon set."""
    assert device.coerce(kind, raw, ICONS, 1) == wire


def test_icon_above_the_tablet_level_is_the_placeholder() -> None:
    """A tablet with icon level 0 gets 0 for every bound icon."""
    assert device.coerce("i", "mdi:lightbulb", ICONS, 0) == 0


def test_chunks_fixture() -> None:
    """Chunking the all-cards layout at 3000 bytes gives the fixture's chunks."""
    chunks = load("chunks.json")
    data = (FIX / "layout_all_cards.dl.json").read_bytes()
    good = chunks["cases"][0]
    assert good["name"] == "good"
    parts = tp.chunk_layout(data, chunks["chunk_bytes"])
    assert parts == [call["data"] for call in good["calls"]]
    assert [call["seq"] for call in good["calls"]] == list(range(len(parts)))
    assert all(call["total"] == len(parts) for call in good["calls"])
    assert all(call["size"] == len(data) for call in good["calls"])
    assert all(call["hash"] == chunks["hash"] for call in good["calls"])


def test_chunks_never_split_a_character() -> None:
    """A chunk border never falls inside a multi-byte character."""
    data = ("aé€😀" * 50).encode("utf-8")
    for size in (16, 17, 18, 19, 20, 33):
        parts = tp.chunk_layout(data, size)
        assert "".join(parts).encode("utf-8") == data
        assert all(len(part.encode("utf-8")) <= size for part in parts)
    assert tp.chunk_layout(b"", 16000) == [""]
    with pytest.raises(tp.ContractError):
        tp.chunk_layout(data, 16001)


def test_limit_checks() -> None:
    """Too many slots, widgets or bytes are refused before anything is sent."""
    source = load("layout_all_cards.source.json")["layout"]
    with pytest.raises(device.ContractError) as err:
        device.compile_device_layout(source, ICONS, {"max_slots": 10})
    assert err.value.code == "limits"
    with pytest.raises(device.ContractError) as err:
        device.compile_device_layout(source, ICONS, {"max_widgets": 10})
    assert err.value.code == "limits"
    with pytest.raises(device.ContractError) as err:
        device.compile_device_layout(source, ICONS, {"max_layout": 1000})
    assert err.value.code == "too_big"
    many = {**source, "nav": [], "pages": [{"id": "p", "title": "", "w": []}] * 21}
    with pytest.raises(device.ContractError) as err:
        device.compile_device_layout(many, ICONS)
    assert err.value.code == "limits"
    # The tablet's limit never raises HA's own.
    assert device.compile_device_layout(source, ICONS, {"max_slots": 99999})


def test_state_stream_payloads() -> None:
    """tab_set payloads are encoded exactly as the stream fixture shows."""
    stream = load("state_stream.json")
    wire = {int(k): v for k, v in stream["wire_values_by_device_slot"].items()}
    steps = stream["steps"]
    assert tp.encode_set(stream["hash"], wire, full=True) == steps[0]["payloads"]
    assert (
        tp.encode_set(stream["hash"], wire, full=True, limit=400)
        == steps[-1]["payloads"]
    )
    assert len(steps[-1]["payloads"]) > 1
    for step in steps:
        first = json.loads(step["payloads"][0])
        values = {}
        for payload in step["payloads"]:
            values.update({slot: value for slot, value in json.loads(payload)["v"]})
        limit = 400 if len(step["payloads"]) > 1 else tp.MAX_SET_BYTES
        again = tp.encode_set(first["h"], values, full="f" in first, limit=limit)
        assert again == step["payloads"], step["note"]
        for payload in step["payloads"]:
            assert len(payload.encode("utf-8")) <= tp.MAX_SET_BYTES


def test_input_events_in_order() -> None:
    """verify_input gives the fixture's verdict for all 24 cases, in order."""
    events = load("input_events.json")
    assert len(events["cases"]) == 24
    last = 0
    secret = bytes.fromhex(events["secret_hex"])
    for case in events["cases"]:
        verdict, parsed = tp.verify_input(
            case["data"],
            mac=events["mac"],
            secret=secret,
            nonce=events["nonce"],
            last_counter=last,
            layouts=case.get("kept", [events["hash"]]),
        )
        assert verdict == case["expect"], case["name"]
        if verdict in ("ok", "stale_layout"):
            last = parsed["counter"]
        if "widget_rect" in case:
            fields = case["data"]["d"].split("|")
            again = tp.input_payload(
                events["mac"],
                events["nonce"],
                int(fields[3]),
                fields[4],
                int(fields[5]),
                fields[6],
                fields[7] == "1",
                float(fields[8]) if fields[8] else None,
            )
            assert again == case["data"]["d"]
            assert tp.sign(secret, again) == case["data"]["s"]


def test_unpaired_tablet_input_is_refused() -> None:
    """Without a secret no input is accepted."""
    events = load("input_events.json")
    verdict, _ = tp.verify_input(
        events["cases"][0]["data"],
        mac=events["mac"],
        secret=None,
        nonce=events["nonce"],
        last_counter=0,
        layouts=[events["hash"]],
    )
    assert verdict == "not_paired"


def test_input_mac_and_knock() -> None:
    """The MAC comes from the payload; knocks parse or are ignored."""
    events = load("input_events.json")
    assert tp.input_mac(events["cases"][0]["data"]) == events["mac"]
    assert tp.input_mac({"d": "1|zz|x"}) is None
    assert tp.input_mac({"d": 5}) is None
    assert tp.input_mac("x") is None
    assert tp.parse_knock({"d": "1|aabbccddeeff|3"}) == ("aabbccddeeff", 3)
    for bad in ("2|aabbccddeeff|3", "1|AABBCCDDEEFF|3", "1|aabbccddeeff|x", "1|a|1"):
        assert tp.parse_knock({"d": bad}) is None
    assert tp.parse_knock({"d": "1|aabbccddeeff|3|4"}) is None
    assert tp.parse_knock(None) is None


def test_pair_vectors() -> None:
    """Wrapping and kid match the pairing fixture."""
    pair = load("pair.json")
    psk = bytes.fromhex(pair["psk_hex"])
    secret = bytes.fromhex(pair["secret_hex"])
    good = pair["cases"][0]
    assert good["name"] == "good"
    call = good["call"]
    assert tp.wrap_secret(psk, pair["mac"], call["nonce"], secret) == call["wrapped"]
    assert tp.kid(secret) == call["kid"]
    assert tp.unwrap_secret(psk, pair["mac"], call["nonce"], call["wrapped"]) == secret
    other = next(c for c in pair["cases"] if c["name"] == "wrong_psk_on_tablet")
    wrong = tp.unwrap_secret(
        bytes.fromhex(other["tablet_psk_hex"]),
        pair["mac"],
        other["call"]["nonce"],
        other["call"]["wrapped"],
    )
    assert tp.kid(wrong) != other["call"]["kid"]


def test_auth_vectors() -> None:
    """Signed call vectors: HA makes the good ones, the tablet check agrees."""
    auth = load("auth.json")
    secret = bytes.fromhex(auth["secret_hex"])
    last = 0
    for case in auth["paired"]:
        if case["expect"] == "ok":
            n = int(case["auth"].partition(".")[0])
            assert (
                tp.call_auth(
                    secret, auth["mac"], auth["nonce"], n, case["action"], case["body"]
                )
                == case["auth"]
            ), case["name"]
        ok, last = tp.check_auth(
            case["auth"],
            secret=secret,
            mac=auth["mac"],
            nonce=auth["nonce"],
            last_n=last,
            action=case["action"],
            body=case["body"],
        )
        assert ("ok" if ok else "auth") == case["expect"], case["name"]
    for case in auth["unpaired"]:
        ok, _ = tp.check_auth(
            case["auth"],
            secret=None,
            mac=auth["mac"],
            nonce=auth["nonce"],
            last_n=0,
            action=case["action"],
            body=case["body"],
        )
        assert ok, case["name"]
    hello = auth["hello"]
    assert (
        tp.call_auth(secret, auth["mac"], hello["nonce"], 0, "tab_hello")
        == hello["auth"]
    )
    assert tp.call_auth(None, auth["mac"], hello["nonce"], 0, "tab_hello") == ""
    ack = next(c for c in auth["paired"] if c["action"] == "tab_ack")
    assert ack["body"] == tp.ack_body(7, True, "")


def test_hello_cases() -> None:
    """HA's next steps after each tab_hello response match the fixture."""
    hello = load("hello.json")
    assert len(hello["cases"]) == 10
    for case in hello["cases"]:
        got = tp.hello_steps(
            case["response"],
            stored_kid=case["stored_kid"],
            want_hash=case["want_hash"] or "x",
        )
        assert got["steps"] == case["expect"], case["name"]
        assert got["status"] == case.get("status", ""), case["name"]
        assert got["reason"] == case.get("reason", ""), case["name"]
    secret = bytes.fromhex(hello["secret_hex"])
    call = hello["call"]
    assert (
        tp.call_auth(secret, hello["mac"], call["nonce"], 0, "tab_hello")
        == call["auth"]
    )


def test_hello_down_levelling_changes_the_hash() -> None:
    """The tablet_without_charts case: HA compiles for its caps and resends."""
    hello = load("hello.json")
    case = next(c for c in hello["cases"] if c["name"] == "tablet_without_charts")
    caps = tp.caps_of(case["response"])
    source = load("layout_all_cards.source.json")["layout"]
    compiled = device.compile_device_layout(source, ICONS, caps)
    assert compiled["hash"] == load("layout_all_cards.nochart.meta.json")["hash"]
    got = tp.hello_steps(
        case["response"], stored_kid=case["stored_kid"], want_hash=compiled["hash"]
    )
    assert got["steps"] == case["expect"]


def test_caps_w_edges() -> None:
    """Contract 4.6: a missing caps.w is every kind, an empty list is none.

    Headings and cards always stay, whatever caps.w lists. The reference
    code does the same.
    """
    from .contract.reference import tabproto

    source = load("layout_all_cards.source.json")["layout"]
    full = device.compile_device_layout(source, ICONS, {})
    assert full["hash"] == load("layout_all_cards.meta.json")["hash"]
    assert (
        device.compile_device_layout(source, ICONS, {"w": None})["hash"]
        == (full["hash"])
    )
    none = device.compile_device_layout(source, ICONS, {"w": []})
    assert none["hash"] != full["hash"]
    kinds = set()

    def walk(items: list) -> None:
        """Collect every widget kind."""
        for item in items:
            kinds.add(item["t"])
            walk(item.get("w", []))

    for page in json.loads(none["bytes"])["pages"]:
        walk(page["w"])
    assert kinds == {"heading", "card"}
    assert none["dropped"]
    only_label = device.compile_device_layout(source, ICONS, {"w": ["label"]})
    kinds.clear()
    for page in json.loads(only_label["bytes"])["pages"]:
        walk(page["w"])
    assert kinds == {"heading", "card", "label"}
    for caps in ({}, {"w": []}, {"w": ["label"]}):
        assert (
            tabproto.compile_device_layout(source, ICONS, caps)["hash"]
            == device.compile_device_layout(source, ICONS, caps)["hash"]
        )


def test_caps_defaults() -> None:
    """Missing caps keys take the contract defaults; unknown keys are ignored."""
    assert tp.caps_of({}) == device.CAPS_DEFAULTS
    caps = tp.caps_of({"caps": {"max_slots": 5, "other": 1, "w": ["card"]}})
    assert caps["max_slots"] == 5
    assert caps["w"] == ["card"]
    assert "other" not in caps


def test_status_cases() -> None:
    """HA's reading of each tab_status response matches the fixture."""
    status = load("status.json")
    for case in status["cases"]:
        assert (
            tp.status_verdict(case["response"], status["want_hash"]) == case["expect"]
        ), case["name"]
        assert case["response"]["session"] == 1, case["name"]


def test_knock_cases() -> None:
    """A knock never resets a session by itself (contract 2.2)."""
    cases = load("status.json")["knock"]
    assert [case["expect"] for case in cases] == ["hello", "status", "ignore", "hello"]
    for case in cases:
        got = tp.knock_step(session=case["session"], status=case["status"])
        assert got == case["expect"], case["name"]
    # An answer without the session key never greets again.
    assert tp.knock_step(session=True, status={}) == "ignore"


def test_no_api_key_vectors() -> None:
    """A tablet without an API key behaves as not paired (contract 6.1)."""
    auth = load("auth.json")
    no_key = auth["no_api_key"]
    assert no_key["hello"]["expect_kid"] == ""
    assert no_key["hello"]["expect_enc"] == 0
    assert no_key["hello"]["expect_session"] == 1
    for case in no_key["calls"]:
        ok, _ = tp.check_auth(
            case["auth"],
            secret=None,
            mac=auth["mac"],
            nonce=auth["nonce"],
            last_n=0,
            action=case["action"],
            body=case["body"],
        )
        assert ok and case["expect"] == "ok", case["name"]
    assert auth["hello"]["repeat_expect_session"] == 0


def test_knock_times() -> None:
    """The knock schedule backs off as the contract says."""
    assert tp.knock_times(40) == [3, 6, 9, 12, 15, 21, 33]
    times = tp.knock_times(86400)
    gaps = {b - a for a, b in zip(times, times[1:], strict=False)}
    assert max(gaps) == tp.KNOCK_MAX_S
    assert len(times) < 300


def test_mac_hex() -> None:
    """Registry MACs become the contract's 12 hex characters."""
    assert tp.mac_hex("AA:BB:CC:DD:EE:01") == "aabbccddee01"
    assert tp.is_hex(tp.new_nonce(), 32)
    assert len(tp.new_secret()) == 32


def test_bindings_digest_sees_an_entity_swap(library) -> None:
    """Same bytes, other entity: the hash stays and the digest changes."""
    components, themes = library
    source = load("layout_small.source.json")
    dashboard = json.loads(json.dumps(source["dashboard"]))
    first = convert_dashboard(
        dashboard, components=components, themes=themes, approved=set()
    )
    dashboard["views"][0]["sections"][0]["cards"][0]["params"]["entity"] = "light.sofa"
    second = convert_dashboard(
        dashboard, components=components, themes=themes, approved=set()
    )
    one = device.compile_device_layout(first["layout"], ICONS)
    two = device.compile_device_layout(second["layout"], ICONS)
    assert one["hash"] == two["hash"]
    assert device.bindings_digest(
        first["bindings"], one["slots"]
    ) != device.bindings_digest(second["bindings"], two["slots"])
