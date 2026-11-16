"""Contract version 2 on the integration side: device layout v2, the handshake.

The fixtures of the contract folder are the expected values wherever they
cover a rule (layout_v2_kit, hello_v2, commit_v2, input_v2, state_v2).
"""

import copy
import json
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.apollo_tab import protocol as tp, sender as sender_module
from custom_components.apollo_tab.maker import device, device_v1
from custom_components.apollo_tab.sender import STATUS_ON_TABLET
from custom_components.apollo_tab.tablet_link import LinkError

from .conftest import MakeTablet, SaveTabDashboard, setup_integration, until
from .fake_tablet import CAPS_V1, CAPS_V2, ENGINE_V2, FakeTablet
from .test_tablet_input import LIGHT_CARD, MAC, tab_config, widget_for

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "tests" / "contract"
FIX = CONTRACT / "fixtures"
ICONS = json.loads((CONTRACT / "icons.json").read_text(encoding="utf-8"))
CONTRACT_JSON = json.loads((CONTRACT / "contract.json").read_text(encoding="utf-8"))

# The keys of version 1, per kind (contract 4.3 before the (2) marks).
V1_PAGE_KEYS = {"title", "w"}
V1_CARD_KEYS = {"id", "t", "r", "w", "hr", "icon", "title", "on", "style"}
V1_ACTION_KEYS = {"tap", "change", "cf", "confirm"}
V1_WIDGET_KEYS = {
    "heading": {"id", "t", "r", "text", "icon"},
    "label": {"id", "t", "r", "text", "size"} | V1_ACTION_KEYS,
    "button": {"id", "t", "r", "text", "icon"} | V1_ACTION_KEYS,
    "switch": {"id", "t", "r", "value"} | V1_ACTION_KEYS,
    "slider": {"id", "t", "r", "value", "min", "max", "step"} | V1_ACTION_KEYS,
    "thermostat": {"id", "t", "r", "value", "min", "max", "step"} | V1_ACTION_KEYS,
    "chart": {"id", "t", "r", "value", "kind"} | V1_ACTION_KEYS,
    "image": {"id", "t", "r", "value"} | V1_ACTION_KEYS,
    "choice": {"id", "t", "r"} | V1_ACTION_KEYS,
}
V1_STYLE_KEYS = {*device.STYLE_COLOURS, *device.RADII, "gd"}


def load(name: str):
    """Return one fixture file as JSON."""
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def kit_source() -> dict:
    """Return a fresh copy of the kit's layout v2."""
    return load("layout_v2_kit.source.json")["layout"]


def items_of(device_layout: dict):
    """Yield (page, item, card) for every heading, card and widget."""
    for page in device_layout["pages"]:
        for item in page["w"]:
            yield page, item, None
            for widget in item.get("w", []):
                yield page, widget, item


# ------------------------------------------------------------ the writer


@pytest.mark.parametrize("name", ["layout_v2_kit", "layout_v2_kit.nochoice"])
def test_kit_bytes_and_hash(name: str) -> None:
    """device.py gives the kit's bytes, hash, slots and drops for its caps."""
    meta = load(f"{name}.meta.json")
    expected = (FIX / f"{name}.dl.json").read_bytes()
    compiled = device.compile_device_layout(kit_source(), ICONS, meta["caps"])
    assert compiled["bytes"] == expected
    assert compiled["hash"] == meta["hash"] == device.content_hash(expected)
    assert compiled["size"] == meta["size"] == len(expected)
    assert compiled["slots"] == meta["slots"]
    assert compiled["dropped"] == meta["dropped"]
    assert compiled["counts"] == meta["counts"]


def test_the_writer_picks_by_version() -> None:
    """Version 1 or none: today's writer; 2: version 2; else: version."""
    source = load("layout_small.source.json")["layout"]
    expected = (FIX / "layout_small.dl.json").read_bytes()
    assert source["v"] == 1
    assert device.compile_device_layout(source, ICONS)["bytes"] == expected
    no_v = {k: v for k, v in source.items() if k != "v"}
    assert device.compile_device_layout(no_v, ICONS)["bytes"] == expected
    assert device_v1.compile_device_layout(source, ICONS)["bytes"] == expected
    assert json.loads(expected)["v"] == device_v1.DL_VERSION == 1
    assert device.DL_VERSION == 2
    for version in (0, 3, True, "2", None):
        with pytest.raises(device.ContractError) as err:
            device.compile_device_layout({**source, "v": version}, ICONS)
        assert err.value.code == "version", version


def test_no_key_of_version_2_reaches_version_1() -> None:
    """The kit written for version 1 holds the keys of version 1 only (A.2).

    The same layout with "v": 1 goes through today's writer: no choice, no
    colour, no detail page, no page theme, no colour slot.
    """
    source = {**kit_source(), "v": 1}
    compiled = device.compile_device_layout(source, ICONS, CONTRACT_JSON["engine_caps"])
    out = json.loads(compiled["bytes"])
    assert out["v"] == 1
    assert set(out["theme"]) == {*device.THEME_COLOURS, *device.RADII, "dark"}
    for page in out["pages"]:
        assert set(page) == V1_PAGE_KEYS
    for _page, item, card in items_of(out):
        if card is None and item["t"] == "card":
            assert set(item) <= V1_CARD_KEYS, item["id"]
            assert set(item.get("style", {})) <= V1_STYLE_KEYS, item["id"]
        else:
            assert item["t"] in device.WIDGET_KINDS, item["id"]
            assert set(item) <= V1_WIDGET_KEYS[item["t"]], item["id"]
    assert all(set(entry) == {"d", "src", "type"} for entry in compiled["slots"])
    assert set(compiled["counts"]) == {"pages", "slots", "widgets"}
    # The kit's choices are left out, as a kind the version 1 writer has not.
    choices = [
        widget["id"]
        for _p, widget, card in items_of(kit_source())
        if card is not None and widget["t"] == "choice"
    ]
    assert choices and set(choices) <= set(compiled["dropped"])


def test_the_writer_writes_only_contract_keys() -> None:
    """Every key of the kit and of the cut lists is in contract 4.3 (v2 block)."""
    v2 = CONTRACT_JSON["v2"]
    for name in ("layout_v2_kit",):
        meta = load(f"{name}.meta.json")
        out = json.loads(
            device.compile_device_layout(kit_source(), ICONS, meta["caps"])["bytes"]
        )
        cuts = load("commit_v2.json")["cuts_source"]
        outs = [
            out,
            json.loads(
                device.compile_device_layout(cuts, ICONS, meta["caps"])["bytes"]
            ),
        ]
    for layout in outs:
        assert layout["v"] == 2
        for page in layout["pages"]:
            assert set(page) <= V1_PAGE_KEYS | set(v2["page_keys"])
        for _page, item, card in items_of(layout):
            if card is None and item["t"] == "card":
                assert set(item) <= V1_CARD_KEYS | set(v2["card_keys"]), item["id"]
                allowed = V1_STYLE_KEYS | set(v2["style_colours"])
                assert set(item.get("style", {})) <= allowed
            else:
                extra = set(v2["widget_keys"].get(item["t"], ()))
                assert set(item) <= V1_WIDGET_KEYS[item["t"]] | extra, item["id"]


def test_page_rules_of_version_2() -> None:
    """commit_v2.json "ha": HA's compile at the page limits, by caps.max_pages."""
    commit = load("commit_v2.json")
    for case in commit["ha"]:
        try:
            got = device.compile_device_layout(commit["source"], ICONS, case["caps"])
            verdict, digest = "ok", got["hash"]
        except device.ContractError as err:
            verdict, digest = err.code, None
        assert (verdict, digest) == (case["expect"], case["hash"]), case["name"]
    # Without caps.max_pages the default of 20 holds (contract 3).
    assert tp.caps_of({"caps": {}})["max_pages"] == 20
    # 21 normal pages are too many even where the tablet takes 64.
    many = copy.deepcopy(commit["source"])
    for page in many["pages"][1:]:
        page.pop("sub")
    with pytest.raises(device.ContractError) as err:
        device.compile_device_layout(many, ICONS, CONTRACT_JSON["engine_caps"])
    assert err.value.code == "limits"
    # A detail page has no nav entry, and sub on page 0 counts for nothing.
    nav = copy.deepcopy(commit["source"])
    nav["nav"] = [{"page": "kit", "title": "Kit"}, {"page": "d0", "title": "D"}]
    nav["pages"][0]["sub"] = 1
    out = json.loads(
        device.compile_device_layout(nav, ICONS, CONTRACT_JSON["engine_caps"])["bytes"]
    )
    assert out["nav"] == [{"p": 0, "title": "Kit"}]
    assert out["pages"][0]["sub"] == 1
    assert device.compile_device_layout(nav, ICONS, CONTRACT_JSON["engine_caps"])[
        "counts"
    ] == {"pages": 21, "normal_pages": 1, "slots": 22, "widgets": 29}


def test_cut_lists() -> None:
    """commit_v2.json "cuts": tracks to 8, options to 16, texts to 40 bytes."""
    commit = load("commit_v2.json")
    compiled = device.compile_device_layout(
        commit["cuts_source"], ICONS, CONTRACT_JSON["engine_caps"]
    )
    assert compiled["hash"] == commit["cuts"]["hash"]
    widgets = json.loads(compiled["bytes"])["pages"][0]["w"][0]["w"]
    assert {str(w["id"]): w for w in widgets} == commit["cuts"]["widgets"]


def test_a_bad_constant_colour_is_refused() -> None:
    """A constant colour the contract does not take never reaches a tablet."""
    for bad in ("#FFF", "red", 16777216, -1, 1.5, True, [1, 2], None):
        layout = kit_source()
        layout["pages"][0]["w"][0]["c"] = bad
        with pytest.raises(device.ContractError) as err:
            device.compile_device_layout(layout, ICONS)
        assert err.value.code == "bad_colour", bad
    layout = kit_source()
    layout["pages"][0]["w"][0]["c"] = [255, 136, 0]
    out = json.loads(device.compile_device_layout(layout, ICONS)["bytes"])
    assert out["pages"][0]["w"][0]["c"] == 0xFF8800


def test_one_source_two_device_slots() -> None:
    """The slot key is (source, type, coerce, roles) (contract 4.4)."""
    good = {"good": "#4CC38A"}
    other = {"good": "#1E8E5A"}
    card = {
        "id": 1,
        "t": "card",
        "r": [100, 84, 376, 248],
        "w": [
            {"id": 2, "t": "label", "r": [116, 100, 200, 28], "text": {"s": 5}},
            {
                "id": 3,
                "t": "slider",
                "r": [116, 140, 200, 40],
                "value": {"s": 5},
                "c": {"s": 5},
            },
            {
                "id": 4,
                "t": "switch",
                "r": [116, 188, 64, 40],
                "c": {"s": 5, "roles": good},
            },
            {
                "id": 5,
                "t": "switch",
                "r": [196, 188, 64, 40],
                "c": {"s": 5, "roles": good},
            },
            {
                "id": 6,
                "t": "switch",
                "r": [276, 188, 64, 40],
                "c": {"s": 5, "roles": other},
            },
        ],
    }
    layout = {
        "v": 2,
        "screen": [1280, 800],
        "theme": kit_source()["theme"],
        "nav": [],
        "pages": [{"id": "p", "title": "P", "w": [card]}],
    }
    compiled = device.compile_device_layout(layout, ICONS)
    assert compiled["slots"] == [
        {"d": 1, "src": 5, "type": "t"},
        {"d": 2, "src": 5, "type": "n"},
        {"coerce": "colour", "d": 3, "src": 5, "type": "n"},
        {
            "coerce": "colour",
            "d": 4,
            "roles": {"good": 0x4CC38A},
            "src": 5,
            "type": "n",
        },
        {
            "coerce": "colour",
            "d": 5,
            "roles": {"good": 0x1E8E5A},
            "src": 5,
            "type": "n",
        },
    ]
    widgets = json.loads(compiled["bytes"])["pages"][0]["w"][0]["w"]
    assert [w.get("c") for w in widgets] == [
        None,
        {"s": 3},
        {"s": 4},
        {"s": 4},
        {"s": 5},
    ]
    assert json.loads(compiled["bytes"])["slots"] == "tnnnn"


def test_ha_question_on_version_2_items() -> None:
    """HA's own question goes onto a widget or a card that sends, with cf."""
    layout = kit_source()
    # Card 1 taps with policy 0; widget 23 is a button with policy 0.
    caps = CONTRACT_JSON["engine_caps"]
    compiled = device.compile_device_layout(
        layout, ICONS, caps, confirm={2: "Open the gate?", 23: "Open?", 3: "No"}
    )
    out = {item["id"]: item for _p, item, _c in items_of(json.loads(compiled["bytes"]))}
    assert (out[2]["confirm"], out[2]["cf"]) == ("Open the gate?", 1)
    assert (out[23]["confirm"], out[23]["cf"]) == ("Open?", 1)
    # An image without tap sends nothing: no question.
    assert "confirm" not in out[3] and "cf" not in out[3]
    # A text of the item's own wins.
    own = device.compile_device_layout(layout, ICONS, caps, confirm={21: "Other"})
    choice = next(
        i for _p, i, _c in items_of(json.loads(own["bytes"])) if i["id"] == 21
    )
    assert (choice["confirm"], choice["cf"]) == ("Change the colour?", 1)
    # Without questions the bytes are the fixture's.
    plain = device.compile_device_layout(layout, ICONS, caps, confirm={})
    assert plain["hash"] == load("layout_v2_kit.meta.json")["hash"]


# -------------------------------------------------------------- coercion


def test_colour_samples() -> None:
    """Every "colours" sample of state_v2.json: to_colour and coerce agree."""
    samples = load("state_v2.json")["colours"]
    assert samples
    for value, roles, wire in samples:
        names = {k: device.colour(v) for k, v in roles.items()} if roles else None
        assert device.to_colour(value, names) == wire, (value, roles)
        got = device.coerce("n", value, ICONS, 2, device.COERCE_COLOUR, names)
        assert got == wire, (value, roles)


def test_coerce_without_colour_is_unchanged() -> None:
    """A number slot that is not a colour still follows toNumber."""
    assert device.coerce("n", "#FF8800", ICONS, 2) is None
    assert device.coerce("n", [255, 0, 0], ICONS, 2) is None
    assert device.coerce("n", 16711680.5, ICONS, 2) == 16711680.5
    assert device.coerce("n", "good", ICONS, 2, None, {"good": 1}) is None


# ------------------------------------------------------------- constants


def test_version_2_constants_match_contract_json() -> None:
    """The v2 block, the new limits and defaults equal contract.json."""
    v2 = CONTRACT_JSON["v2"]
    assert list(device.WIDGET_KINDS_V2) == v2["widget_kinds"]
    assert list(device.STYLE_COLOURS_V2) == v2["style_colours"]
    assert list(device.CARD_KEYS_V2) == v2["card_keys"]
    assert list(device.PAGE_KEYS_V2) == v2["page_keys"]
    assert {k: list(v) for k, v in device.WIDGET_KEYS_V2.items()} == v2["widget_keys"]
    assert list(device.LOOK_KEYS) == v2["look_keys"]
    assert list(device.LIT) == v2["lit"]
    assert list(device.ALIGN) == v2["align"]
    assert list(device.SHAPES) == v2["shapes"]
    assert list(device.SLIDER_LOOKS) == v2["slider_looks"]
    assert list(device.DIRS) == v2["dirs"]
    assert list(device.IMAGE_LOOKS) == v2["image_looks"]
    assert list(device.CHOICE_LOOKS) == v2["choice_looks"]
    limits = CONTRACT_JSON["limits"]
    assert limits["max_pages_v2"] == device.MAX_PAGES_V2
    assert limits["max_options"] == device.MAX_OPTIONS
    assert limits["max_option_text_bytes"] == device.MAX_OPTION_TEXT_BYTES
    assert limits["max_track"] == device.MAX_TRACK
    assert limits["max_stored_bytes"] == device.MAX_STORED_BYTES
    assert CONTRACT_JSON["caps_defaults"]["max_pages"] == device.MAX_PAGES
    assert CONTRACT_JSON["proto_low"] == tp.PROTO_LOW
    assert CONTRACT_JSON["input_version"] == tp.INPUT_VERSION
    assert (CONTRACT_JSON["proto_low"], CONTRACT_JSON["proto"]) == tp.PROTO_RANGE
    assert CONTRACT_JSON["engine_caps"] == CAPS_V2


def test_status_poll_limit_matches_contract_json() -> None:
    """HA waits 60 s for a build (timing.status_poll_limit_s, contract 5)."""
    limit = CONTRACT_JSON["timing"]["status_poll_limit_s"]
    assert limit == 60
    assert limit == sender_module.STATUS_POLL_LIMIT_S


# ------------------------------------------------------------- handshake


@pytest.mark.parametrize(
    ("proto", "verdict", "dl"),
    [
        ((1, 1), "", 1),
        ((1, 2), "", 2),
        ((2, 2), "", 2),
        ((2, 3), "", 2),
        ((1, 9), "", 2),
        ((3, 4), "tablet_new", 0),
        ((0, 0), "tablet_old", 0),
        ((0, 1), "", 1),
    ],
)
def test_proto_by_overlap(proto: tuple[int, int], verdict: str, dl: int) -> None:
    """The ranges share a version, and HA speaks the highest one (contract 9)."""
    response = {"proto": list(proto)}
    assert tp.proto_verdict(response) == verdict
    assert tp.layout_version(response) == dl


@pytest.mark.parametrize("proto", [None, [], [1], [None, 2], ["a", 2], {"a": 1}])
def test_unreadable_proto(proto) -> None:
    """A proto HA cannot read is an old tablet, and gets no layout."""
    response = {} if proto is None else {"proto": proto}
    assert tp.proto_verdict(response) == "tablet_old"
    assert tp.layout_version(response) == 0
    assert tp.hello_steps(response, stored_kid=None, want_hash="x")["dl"] == 0


def test_hello_v2_cases() -> None:
    """hello_v2.json: steps, verdict, layout version, page limit and hash."""
    hello = load("hello_v2.json")
    small = load("layout_small.source.json")["layout"]
    for case in hello["cases"]:
        response = case["response"]
        want = hello["layouts"][case["want"]] if case["want"] else "x"
        got = tp.hello_steps(response, stored_kid=case["stored_kid"], want_hash=want)
        assert got["steps"] == case["expect"], case["name"]
        assert got["status"] == case.get("status", ""), case["name"]
        assert got["reason"] == case.get("reason", ""), case["name"]
        assert got["dl"] == case["dl"], case["name"]
        if not case["dl"]:
            continue
        caps = tp.caps_of(response)
        assert caps["max_pages"] == case["max_pages"], case["name"]
        # What HA compiles for this tablet hashes to the case's layout.
        source = kit_source() if case["dl"] == 2 else small
        assert device.compile_device_layout(source, ICONS, caps)["hash"] == want
    call = hello["call"]
    secret = bytes.fromhex(hello["secret_hex"])
    auth = tp.call_auth(secret, hello["mac"], call["nonce"], 0, "tab_hello")
    assert auth == call["auth"]


def test_hello_cases_of_version_1_compile_version_1() -> None:
    """Every hello.json tablet speaks [1, 1]: HA compiles version 1 for it."""
    for case in load("hello.json")["cases"]:
        got = tp.hello_steps(
            case["response"], stored_kid=case["stored_kid"], want_hash="x"
        )
        assert got["dl"] == (0 if case.get("status") else 1), case["name"]


# ------------------------------------------------------------------ input


def test_input_field_1_is_input_version() -> None:
    """Field 1 of an input and of the knock is 1, not PROTO (contract 9)."""
    assert tp.PROTO == 2
    assert tp.INPUT_VERSION == 1
    payload = tp.input_payload("aabbccddeeff", "0" * 32, 1, "h" * 16, 2, "t", False)
    assert payload.startswith("1|")
    assert tp.parse_knock({"d": "1|aabbccddeeff|3"}) == ("aabbccddeeff", 3)
    assert tp.parse_knock({"d": "2|aabbccddeeff|3"}) is None


def test_input_v2_verdicts() -> None:
    """input_v2.json HA cases, in order: field 1 is 2 is version, 1 is ok."""
    events = load("input_v2.json")
    secret = bytes.fromhex(events["secret_hex"])
    last = 0
    seen = set()
    for case in events["cases"]:
        if "payload" not in case:
            continue
        verdict, parsed = tp.verify_input(
            case["payload"],
            mac=events["mac"],
            secret=secret,
            nonce=events["nonce"],
            last_counter=last,
            layouts=[events["hash"]],
        )
        assert verdict == case["verdict"], case["name"]
        seen.add(case["name"])
        if verdict == "ok":
            last = parsed["counter"]
            assert parsed["layout"] == events["hash"]
    assert {"field_1_is_2", "field_1_is_1"} <= seen


# ------------------------------------------------------- simulated tablet


async def _commit(tablet: FakeTablet, case: dict) -> str:
    """Send one commit_v2.json transfer to the tablet; return its answer."""
    for call in case["calls"]:
        await tablet.async_call("tab_layout", call)
    try:
        await tablet.async_call("tab_commit", {"hash": case["commit_hash"], "auth": ""})
    except LinkError as err:
        return err.code
    return "ok"


async def test_simulated_tablets_at_the_page_limits(hass: HomeAssistant) -> None:
    """Engine 0.2.0 answers commit_v2.json; engine 0.1.0 takes version 1 only."""
    commit = load("commit_v2.json")
    assert commit["cases"]
    for case in commit["cases"]:
        new = FakeTablet(hass, "aa:bb:cc:dd:ee:ff", engine=ENGINE_V2)
        assert await _commit(new, case) == case["commit"], case["name"]
        old = FakeTablet(hass, "aa:bb:cc:dd:ee:ff")
        data = "".join(call["data"] for call in case["calls"])
        version = json.loads(data)["v"]
        expected = case["commit"] if version == 1 else "version"
        assert await _commit(old, case) == expected, case["name"]


async def test_simulated_tablet_modes(hass: HomeAssistant) -> None:
    """The two engines answer their own proto and caps in tab_hello."""
    old = FakeTablet(hass, "aa:bb:cc:dd:ee:01", psk=None)
    new = FakeTablet(hass, "aa:bb:cc:dd:ee:02", psk=None, engine=ENGINE_V2)
    first = await old.async_call("tab_hello", {"nonce": "0" * 32, "auth": ""})
    second = await new.async_call("tab_hello", {"nonce": "1" * 32, "auth": ""})
    assert (first["proto"], first["engine"]) == ([1, 1], "0.1.0")
    assert (second["proto"], second["engine"]) == ([1, 2], "0.2.0")
    assert (first["caps"], second["caps"]) == (CAPS_V1, CAPS_V2)
    assert first["caps"] == load("hello.json")["cases"][0]["response"]["caps"]
    assert second["caps"] == load("hello_v2.json")["cases"][0]["response"]["caps"]
    middle = FakeTablet(hass, "aa:bb:cc:dd:ee:03", engine=ENGINE_V2, proto=(1, 1))
    assert middle.proto == [1, 1]


async def test_a_tablet_that_speaks_2_shows_and_taps(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Engine 0.2.0: HA sends the dashboard, and an input with 1| runs."""
    calls = async_mock_service(hass, "light", "toggle")
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    tablet = make_tablet(engine=ENGINE_V2)
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", tab_config(LIGHT_CARD))
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    assert session.caps["max_pages"] == 64
    assert tablet.active == session.want.hash

    data = tablet.tap(widget_for(session, "apollo/light-tile", "toggle"))
    assert data["d"].startswith("1|")
    await until(hass, lambda: len(tablet.acks) >= 1)
    assert tablet.acks == [(1, True, "")]
    assert len(calls) == 1
    assert calls[0].data == {"entity_id": "light.kitchen"}
