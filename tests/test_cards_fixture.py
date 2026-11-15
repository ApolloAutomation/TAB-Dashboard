"""The cards fixture of the first release (cards spec G.3 I14a, A.5, C.6).

layout_v2_cards.* is the nine cards of step A as Home Assistant sends them
to a tablet with engine 0.2.0, and layout_v2_cards.v1.* the same dashboard
for a tablet with engine 0.1.0. Engine 0.2.0 must load both before it is
released. The files are the expected values here: the integration must make
them byte for byte, on the convert path, in its writer and in the sender.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.apollo_tab.facts import FactKeeper
from custom_components.apollo_tab.maker import device
from custom_components.apollo_tab.maker.convert import convert_dashboard
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.sender import STATUS_ON_TABLET

from . import cards_fixture
from .conftest import MakeTablet, SaveTabDashboard, setup_integration, until
from .fake_tablet import CAPS_V1, ENGINE_V2
from .test_tablet_input import MAC

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "tests" / "contract"
FIX = CONTRACT / "fixtures"
ICONS = json.loads((CONTRACT / "icons.json").read_text(encoding="utf-8"))
CONTRACT_JSON = json.loads((CONTRACT / "contract.json").read_text(encoding="utf-8"))
V1_RADII = ("r", "r2", "bw")
# The nine cards of the first release (package I9).
NINE = {
    "apollo/light",
    "apollo/switch",
    "apollo/button",
    "apollo/scenes",
    "apollo/reading",
    "apollo/number",
    "apollo/select",
    "apollo/screen",
    "apollo/page-link",
}


def load(name: str):
    """Return one fixture file as JSON."""
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def source() -> dict:
    """Return layout_v2_cards.source.json."""
    return load("layout_v2_cards.source.json")


def items_of(device_layout: dict):
    """Yield (item, card) for every heading, card and widget."""
    for page in device_layout["pages"]:
        for item in page["w"]:
            yield item, None
            for widget in item.get("w", []):
                yield widget, item


def version_1_problems(device_layout: dict) -> list[str]:
    """Return every key or kind of a device layout that is not version 1.

    It reads the key lists of contract.json: the kinds and colours of
    version 1, and everything its "v2" block adds.
    """
    v2 = CONTRACT_JSON["v2"]
    problems = []
    if device_layout.get("v") != 1:
        problems.append(f"v {device_layout.get('v')!r}")
    extra = set(device_layout) - {"v", "screen", "theme", "nav", "pages", "slots"}
    problems += [f"top key {key}" for key in sorted(extra)]
    theme_keys = {"dark", *CONTRACT_JSON["theme_colours"], *V1_RADII}
    problems += [
        f"theme key {key}" for key in sorted(set(device_layout["theme"]) - theme_keys)
    ]
    for index, page in enumerate(device_layout["pages"]):
        problems += [
            f"page {index} key {key}"
            for key in sorted(set(page) & set(v2["page_keys"]))
        ]
        problems += [
            f"page {index} key {key}" for key in sorted(set(page) - {"title", "w"})
        ]
    style_keys = {*CONTRACT_JSON["style_colours"], *V1_RADII, "gd"}
    for item, card in items_of(device_layout):
        kind = item.get("t")
        where = f"{kind} {item.get('id')}"
        if card is None:
            if kind not in ("heading", "card"):
                problems.append(f"item kind {where}")
            if kind == "card":
                problems += [
                    f"{where} key {k}" for k in sorted(set(item) & set(v2["card_keys"]))
                ]
                style = item.get("style", {})
                problems += [
                    f"{where} style {k}" for k in sorted(set(style) - style_keys)
                ]
                problems += [
                    f"{where} style {k}"
                    for k in sorted(set(style) & set(v2["style_colours"]))
                ]
            elif kind == "heading":
                problems += [
                    f"{where} key {k}"
                    for k in sorted(set(item) & set(v2["widget_keys"]["heading"]))
                ]
            continue
        if kind not in CONTRACT_JSON["widget_kinds"] or kind in v2["widget_kinds"]:
            problems.append(f"widget kind {where}")
            continue
        new = set(v2["widget_keys"].get(kind, ()))
        problems += [f"{where} key {k}" for k in sorted(set(item) & new)]
    return problems


def icon_values(device_layout: dict) -> list[int]:
    """Return every constant icon code point of a device layout v1."""
    found = [entry["icon"] for entry in device_layout["nav"] if "icon" in entry]
    for item, _card in items_of(device_layout):
        if isinstance(item.get("icon"), int):
            found.append(item["icon"])
        if item.get("t") == "image" and isinstance(item.get("value"), int):
            found.append(item["value"])
    return found


# ------------------------------------------------------------- the files


def test_the_generator_makes_the_five_files() -> None:
    """tests/cards_fixture.py makes the contract's files byte for byte."""
    built = cards_fixture.build()
    assert sorted(built) == sorted(cards_fixture.FILES)
    for name, data in built.items():
        assert (FIX / name).read_bytes() == data, name


@pytest.mark.parametrize("name", ["layout_v2_cards", "layout_v2_cards.v1"])
def test_the_writer_gives_the_bytes(name: str) -> None:
    """device.py gives the bytes, hash, slots and counts of both files."""
    meta = load(f"{name}.meta.json")
    layout = (
        source()["layout"] if name == "layout_v2_cards" else source()["v1"]["layout"]
    )
    expected = (FIX / f"{name}.dl.json").read_bytes()
    compiled = device.compile_device_layout(layout, ICONS, meta["caps"])
    assert compiled["bytes"] == expected
    assert compiled["hash"] == meta["hash"] == device.content_hash(expected)
    assert compiled["size"] == meta["size"] == len(expected)
    assert compiled["slots"] == meta["slots"]
    assert compiled["dropped"] == meta["dropped"] == []
    assert compiled["counts"] == meta["counts"]
    assert meta["source_hash"] == layout["hash"]
    assert device.canonical(json.loads(expected)) == expected


@pytest.mark.parametrize("dl", [2, 1])
def test_convert_makes_the_fixture_layouts(dl: int) -> None:
    """The dashboard and facts of the file convert to its layouts."""
    fixture = source()
    assert {e: facts_of(raw) for e, raw in fixture["devices"].items()} == fixture[
        "facts"
    ]
    want = fixture if dl == 2 else fixture["v1"]
    result = convert_dashboard(
        fixture["dashboard"],
        components=cards_fixture.load_library()[0],
        themes=cards_fixture.load_library()[1],
        approved=set(),
        facts=fixture["facts"],
        dl=dl,
        icons=ICONS,
        caps=CONTRACT_JSON["engine_caps"] if dl == 2 else None,
    )
    assert result["layout"] == want["layout"]
    assert result["bindings"] == want["bindings"]
    assert result["warnings"] == want["warnings"] == []
    if dl == 1:
        assert result["simpler"] == want["simpler"]


def test_the_caps_are_engine_0_2_0_and_engine_0_1_0() -> None:
    """The v2 file is for engine_caps, the v1 file for the caps of hello.json case 0."""
    assert load("layout_v2_cards.meta.json")["caps"] == CONTRACT_JSON["engine_caps"]
    field = load("hello.json")["cases"][0]["response"]
    assert field["engine"] == "0.1.0" and field["proto"] == [1, 1]
    assert load("layout_v2_cards.v1.meta.json")["caps"] == field["caps"] == CAPS_V1


# --------------------------------------------------------- what it holds


def test_the_nine_cards_on_two_pages_with_the_detail_pages() -> None:
    """Every card of the first release, 2 normal pages, a detail page per light.

    The on/off porch lamp has no hold and no detail page (LOOK-NOTES
    decisions 2 and 3): 4 detail pages for 5 light cards.
    """
    layout = source()["layout"]
    out = json.loads((FIX / "layout_v2_cards.dl.json").read_bytes())
    assert out["v"] == 2
    normal = [page for page in layout["pages"] if not page.get("sub")]
    details = [page for page in layout["pages"] if page.get("sub")]
    assert [page["id"] for page in normal] == ["home", "more"]
    cards = [item for page in normal for item in page["w"] if item["t"] == "card"]
    assert {card["component"] for card in cards} == NINE
    lights = [card for card in cards if card["component"] == "apollo/light"]
    assert len(lights) == 5
    bindings = source()["bindings"]["slots"]
    # The lamp of a card: the entity of the slot that says it is on.
    entities = {
        card["id"]: bindings[card["on"]["s"] - 1]["variables"]["entity"]
        for card in lights
    }
    porch = [card for card in lights if entities[card["id"]] == "light.porch"]
    assert len(porch) == 1 and "hold" not in porch[0]
    holders = [card for card in lights if card is not porch[0]]
    assert len(details) == len(holders) == 4
    # Each other light's hold opens its own detail page.
    pages = [page["id"] for page in layout["pages"]]
    holds = [card["hold"]["page"] for card in holders]
    assert sorted(holds) == sorted(page["id"] for page in details)
    assert all(pages.index(page) >= 2 for page in holds)
    on_device = [page for page in out["pages"] if page.get("sub") == 1]
    assert len(on_device) == 4 and out["pages"][0].get("sub") is None
    # LOOK-NOTES decision 1: a detail page holds the card only, no heading.
    assert all([w["t"] for w in page["w"]] == ["card"] for page in details)
    # Every picker variant of the nine but two (two pages hold no more).
    components = cards_fixture.load_library()[0]
    variants = {
        (component, name)
        for component in NINE
        for name, variant in components[component]["variants"].items()
        if variant["picker"]
    }
    shown = {
        (card["component"], card["variant"])
        for view in source()["dashboard"]["views"]
        for section in view["sections"]
        for card in section["cards"]
    }
    assert shown <= variants
    assert variants - shown == {
        ("apollo/page-link", "wide"),
        ("apollo/scenes", "large"),
    }
    kinds = {item["t"] for item, _card in items_of(out)}
    assert {"choice", "slider", "switch", "button", "label", "image"} <= kinds


def test_the_texts_are_english() -> None:
    """Section and page titles of the fixture (LOOK-NOTES decision 3)."""
    titles = [
        section["title"]
        for view in source()["dashboard"]["views"]
        for section in view["sections"]
    ]
    assert titles == [
        "Living room",
        "Sofa lamp · Colour",
        "House",
        "Desk",
        "Status",
        "Settings",
    ]
    assert b"Farbe" not in (FIX / "layout_v2_cards.dl.json").read_bytes()


def test_the_owners_lamp_has_colour_and_white() -> None:
    """The owner's RGB lamp: a hue track and a warm-to-cool track from 2000 K."""
    fixture = source()
    assert fixture["facts"]["light.sofa"]["colour"] is True
    out = json.loads((FIX / "layout_v2_cards.dl.json").read_bytes())
    tracks = [
        widget["track"]
        for widget, card in items_of(out)
        if card is not None and widget["t"] == "slider" and "track" in widget
    ]
    hue = [0xFF0000, 0xFFFF00, 0x00FF00, 0x00FFFF, 0x0000FF, 0xFF00FF, 0xFF0000]
    assert hue in tracks
    whites = [
        widget
        for widget, card in items_of(out)
        if card is not None and widget["t"] == "slider" and widget.get("min") == 2000
    ]
    assert whites and all(widget["max"] == 6500 for widget in whites)


def test_the_v1_file_holds_only_keys_of_version_1() -> None:
    """layout_v2_cards.v1.dl.json against the key lists of contract.json (C.6)."""
    out = json.loads((FIX / "layout_v2_cards.v1.dl.json").read_bytes())
    assert version_1_problems(out) == []
    assert len(out["pages"]) == 2
    assert {
        entry["type"] for entry in load("layout_v2_cards.v1.meta.json")["slots"]
    } <= set(CONTRACT_JSON["slot_types"])
    assert set(out["slots"]) <= set(CONTRACT_JSON["slot_types"])


def test_the_key_check_finds_keys_of_version_2() -> None:
    """The check passes today's version 1 fixture and finds the v2 file's keys."""
    for name in ("layout_all_cards", "layout_small", "layout_all_cards.nochart"):
        assert (
            version_1_problems(json.loads((FIX / f"{name}.dl.json").read_bytes())) == []
        )
    v2 = json.loads((FIX / "layout_v2_cards.dl.json").read_bytes())
    problems = version_1_problems(v2)
    assert "v 2" in problems
    for word in (
        "key sub",
        "key ttl",
        "key hold",
        "key tint",
        "key lit",
        "widget kind choice",
    ):
        assert any(word in problem for problem in problems), word
    kit = json.loads((FIX / "layout_v2_kit.dl.json").read_bytes())
    assert any("style card_pr" in problem for problem in version_1_problems(kit))
    assert any(
        "theme" in problem
        for problem in version_1_problems({**kit, "pages": [], "theme": {"x": 1}})
    )


def test_the_v1_file_has_no_icon_above_level_1_and_no_fallback() -> None:
    """Engine 0.1.0 holds the icons of level 1: none above, no fallback glyph (C.6)."""
    out = json.loads((FIX / "layout_v2_cards.v1.dl.json").read_bytes())
    level = {code: lvl for code, lvl in ICONS["icons"].values()}
    fallback = ICONS["icons"][ICONS["fallback"]][0]
    found = icon_values(out)
    assert found, "the v1 file holds no icon at all"
    assert all(level.get(code) == 1 for code in found), [
        code for code in found if level.get(code) != 1
    ]
    assert fallback not in found
    # No live icon either: a slot of type "i" could name any icon later.
    assert "i" not in out["slots"]
    # Nor in the source: every icon name of the layout v1 is of level 1.
    names = []

    def walk(value) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and value.startswith("mdi:"):
            names.append(value)

    walk(source()["v1"]["layout"]["pages"])
    assert names and all(ICONS["icons"][name][1] == 1 for name in names), names


def test_the_v2_file_names_icons_of_level_2() -> None:
    """The check above can fail: the v2 file holds icons of level 2."""
    out = json.loads((FIX / "layout_v2_cards.dl.json").read_bytes())
    level = {code: lvl for code, lvl in ICONS["icons"].values()}
    assert any(level.get(code) == 2 for code in icon_values(out))


def test_both_tablets_take_their_file() -> None:
    """The reference tablets answer ok, and the v2 file fits what a tablet keeps."""
    tp = cards_fixture.reference()
    data = (FIX / "layout_v2_cards.dl.json").read_bytes()
    data_v1 = (FIX / "layout_v2_cards.v1.dl.json").read_bytes()
    assert tp.tablet_commit(data, CONTRACT_JSON["engine_caps"]) == ""
    assert tp.tablet_commit(data_v1, CAPS_V1) == ""
    assert len(data) <= CONTRACT_JSON["limits"]["max_stored_bytes"]
    assert len(data_v1) < len(data)


# ------------------------------------------------------------ the sender


@pytest.fixture
def fixture_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every conversion the facts of the fixture."""
    facts = source()["facts"]
    monkeypatch.setattr(
        FactKeeper,
        "facts_for",
        lambda self, ids: {e: facts[e] for e in ids if e in facts},
    )


@pytest.mark.usefixtures("fixture_facts")
@pytest.mark.parametrize(
    ("engine", "name"), [(ENGINE_V2, "layout_v2_cards"), (None, "layout_v2_cards.v1")]
)
async def test_the_sender_sends_the_fixture(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
    engine: str | None,
    name: str,
) -> None:
    """Each tablet gets exactly the bytes of its file."""
    fake = make_tablet(**({"engine": engine} if engine else {}))
    await setup_integration(hass, config_entry)
    await save_tab_dashboard("tab-home", source()["dashboard"])
    session = config_entry.runtime_data.sender.sessions[MAC]
    await until(hass, lambda: session.status == STATUS_ON_TABLET)
    meta = load(f"{name}.meta.json")
    assert session.want.hash == meta["hash"]
    assert session.want.data == (FIX / f"{name}.dl.json").read_bytes()
    assert fake.active == meta["hash"]
    assert session.not_kept is False


# ------------------------------------------------------------------ CI


def test_ci_compares_the_contract_with_tab_1() -> None:
    """CI checks TAB-1 out and runs the folder comparison with TAB1_DIR set.

    With TAB1_DIR set, the comparison fails when the folder is missing
    instead of being skipped.
    """
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["test"]["steps"]
    [checkout] = [
        step
        for step in steps
        if step.get("with", {}).get("repository") == "ApolloAutomation/TAB-1"
    ]
    # Pinned to a commit, like every other action of the file.
    assert re.fullmatch(r"actions/checkout@[0-9a-f]{40}", checkout["uses"])
    assert checkout["with"]["persist-credentials"] is False
    folder = checkout["with"]["path"]
    after = steps[steps.index(checkout) + 1 :]
    [compare] = [step for step in after if step.get("env", {}).get("TAB1_DIR")]
    assert compare["env"]["TAB1_DIR"] == folder
    assert "the contract is the same as TAB-1" in compare["run"]
    assert "tests/frontend/tablet-screens.test.mjs" in compare["run"]
    script = (ROOT / "tests" / "frontend" / "tablet-screens.test.mjs").read_text(
        encoding="utf-8"
    )
    assert 'test(\n  "the contract is the same as TAB-1\'s copy"' in script
