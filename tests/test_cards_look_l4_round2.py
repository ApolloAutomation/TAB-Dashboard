"""The look of the cards after round 2 of L4 (the findings of its checks).

Each test holds one fix: names cut in the middle everywhere they are drawn
(title headers, Scenes buttons, labels of sizes s and l, the camera's
caption), names on two lines in tiles without a badge, the main row of a
grown card capped by `most_grown`, Dropdown Wide with too many choices,
missing devices named by their id, Room's unit spacing and the camera input
of a schema 1 card.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from custom_components.apollo_tab.maker.compile import add_unavailable
from custom_components.apollo_tab.maker.features import facts_of
from custom_components.apollo_tab.maker.names import (
    NAME_WIDTHS,
    cut_middle,
    cut_to_fit,
    cut_to_fit_template,
    name_chars,
    room_beside,
    split_name,
    split_name_template,
)
from custom_components.apollo_tab.maker.schema import validate_component
from tests.test_cards_look_l4 import _camera_card
from tests.test_cards_step_a import COMPONENTS, _value
from tests.test_cards_step_b import MEDIA_RAW, _compile
from tests.test_maker_schema2 import _doc, _refused

NAMES = [
    "Living Room Lamp 1",
    "Outside Temperature",
    "Upstairs Guest Bedroom Reading Lamp",
    "Superlongnamewithoutspaces",
    "Kitchen",
    "A B C D E F G H I J K L M N O P",
    "WWWWWWWW WWWWWWWW",
    "  Hallway ceiling  ",
    " Sofa lamp · Colour",
    "",
]


# ---------------------------------------------------------------- names


@pytest.mark.parametrize("px", [14, 15, 16, 18, 34])
async def test_the_two_line_template_splits_as_split_name(
    hass: HomeAssistant, px: int
) -> None:
    """Round 2: a tile name without a badge takes two lines, live as here."""
    for width in (64, 100, 152, 216, 344):
        lines = [
            Template(
                "{%- set n = name -%}" + split_name_template(line, width, px), hass
            )
            for line in (1, 2)
        ]
        for name in NAMES:
            got = tuple(
                t.async_render(
                    {"name": name, "name_w": dict(NAME_WIDTHS[px])}, parse_result=False
                )
                for t in lines
            )
            assert got == split_name(name, width, px), (px, width, name)


def test_a_name_on_two_lines_breaks_between_words() -> None:
    """Round 2: the first line takes whole words; only the rest is cut."""
    assert split_name("Outside Temperature", 152) == ("Outside", "Temperature")
    assert split_name("Kitchen", 152) == ("Kitchen", "")
    first, rest = split_name("Upstairs Guest Bedroom Reading Lamp", 152)
    assert first == "Upstairs Guest"
    assert rest == cut_to_fit("Bedroom Reading Lamp", name_chars(152), 152)
    assert "…" in rest[1:-1]
    # One word too long for a line is cut on the first line alone.
    word = "Superlongnamewithoutspacesatall"
    assert split_name(word, 100) == (cut_to_fit(word, name_chars(100), 100), "")


@pytest.mark.parametrize("px", [14, 16, 18])
async def test_spaces_around_a_name_are_not_counted(
    hass: HomeAssistant, px: int
) -> None:
    """Minor: "  Hallway  " was cut although "Hallway" fits."""
    width = 100
    padded = "   Hallway ceiling   "
    assert cut_middle(padded, 40) == "Hallway ceiling"
    assert cut_to_fit(padded, name_chars(width, px), width, px) == cut_to_fit(
        "Hallway ceiling", name_chars(width, px), width, px
    )
    template = Template(
        "{%- set n = name -%}" + cut_to_fit_template(name_chars(width, px), width, px),
        hass,
    )
    got = template.async_render(
        {"name": padded, "name_w": dict(NAME_WIDTHS[px])}, parse_result=False
    )
    assert got == cut_to_fit("Hallway ceiling", name_chars(width, px), width, px)


def test_each_text_size_has_its_own_widths() -> None:
    """Item d: a 14 px name has more room than an 18 px one, a 34 px less."""
    name = "Living Room Temperature Sensor"
    shown = {px: cut_to_fit(name, name_chars(250, px), 250, px) for px in (14, 18, 34)}
    assert shown[14] == name
    assert len(shown[18]) < len(name) and "…" in shown[18]
    assert len(shown[34]) < len(shown[18]) and "…" in shown[34]


async def test_the_title_header_cuts_at_its_own_size(hass: HomeAssistant) -> None:
    """Item d: the 16 px title beside its icon is cut in its middle."""
    opts = ["A", "B"]
    facts = {
        "select.a": facts_of(
            {"domain": "select", "state": {"attributes": {"options": opts}}}
        )
    }
    result = _compile(
        COMPONENTS["apollo/select"], "wide", {"entity": "select.a"}, {}, facts
    )
    head = result["header"]
    assert "icon" in head
    width = head["r"][2] - 32
    long = "Upstairs Guest Bedroom Air Purifier Fan Speed Mode Choice"
    hass.states.async_set("select.a", "A", {"friendly_name": long})
    shown = await _value(hass, result, head["title"])
    assert shown == cut_to_fit(long, name_chars(width, 16), width, 16)
    assert shown.endswith("Choice") and "…" in shown
    hass.states.async_set("select.a", "A", {"friendly_name": "Fan mode"})
    assert await _value(hass, result, head["title"]) == "Fan mode"


async def test_a_scene_button_cuts_its_name_in_the_middle(hass: HomeAssistant) -> None:
    """Item d: Scenes buttons were cut at their end by the tablet."""
    result = _compile(
        COMPONENTS["apollo/scenes"], "large", {"scenes": ["scene.a", "scene.b"]}, {}, {}
    )
    button = next(w for w in result["widgets"] if w["t"] == "button")
    [slot] = [s for s in result["slots"] if s["n"] == button["text"]["s"]]
    assert slot["variables"]["name_w"] == NAME_WIDTHS[15]
    hass.states.async_set("scene.a", "x", {"friendly_name": "Good Morning Everyone"})
    shown = await _value(hass, result, button["text"])
    assert shown != "Good Morning Everyone"
    assert shown.endswith("Everyone") and "…" in shown
    hass.states.async_set("scene.a", "x", {"friendly_name": "Movie"})
    assert await _value(hass, result, button["text"]) == "Movie"


async def test_the_list_wide_names_are_cut_in_the_middle(hass: HomeAssistant) -> None:
    """Item d: List Wide's 14 px names, and its "+2 more" line, stay right."""
    entities = [f"sensor.s{i}" for i in range(5)]
    result = _compile(
        COMPONENTS["apollo/readings"], "wide", {"entities": entities}, {}, {}
    )
    names = [w for w in result["widgets"] if w["t"] == "label" and "al" not in w]
    assert len(names) == 4
    width = names[0]["r"][2]
    long = "Upstairs Guest Bedroom Temperature Sensor Number 2"
    hass.states.async_set("sensor.s0", "21", {"friendly_name": long})
    shown = await _value(hass, result, names[0]["text"])
    # Round 3 (critic major, decision 14): the name gets what the value
    # shown ("21", 14 px, in a column of 80) leaves of the line.
    room = room_beside("21", 14, width, 8, 80)
    assert shown == cut_to_fit(long, name_chars(width, 14), width, 14, room)
    assert "…" in shown
    assert await _value(hass, result, names[3]["text"]) == "+2 more"


async def test_the_room_extra_name_is_cut_in_the_middle(hass: HomeAssistant) -> None:
    """Item d: the Room's extra device's name, size s."""
    result = _compile(
        COMPONENTS["apollo/room"], "room",
        {"page": "o", "temperature_sensor": "sensor.t", "extra": "sensor.x"},
        {"show_extra": True}, {},
    )  # fmt: skip
    long = "Upstairs Guest Bedroom Window Contact Sensor"
    hass.states.async_set("sensor.x", "on", {"friendly_name": long})
    found = []
    for widget in result["widgets"]:
        if (
            widget["t"] == "label"
            and isinstance(widget.get("text"), dict)
            and (await _value(hass, result, widget["text"])).endswith("Sensor")
        ):
            found.append(widget)
    [label] = found
    width = label["r"][2]
    # Round 3 (critic major, decision 14): the name gets what the value
    # shown at its right leaves of the line.
    [value] = [
        w
        for w in result["widgets"]
        if w["t"] == "label" and w.get("al") == 2 and w["r"][1] == label["r"][1]
    ]
    shown = await _value(hass, result, value["text"])
    px = {"s": 14, "m": 18}[value["size"]]
    room = room_beside(shown, px, width, 8, value["r"][2])
    assert await _value(hass, result, label["text"]) == cut_to_fit(
        long, name_chars(width, 14), width, 14, room
    )


async def test_the_media_hero_without_a_title_cuts_its_name(
    hass: HomeAssistant,
) -> None:
    """Item d: with nothing playing the 34 px title is the player's name."""
    result = _compile(
        COMPONENTS["apollo/media"], "hero", {"entity": "media_player.a"}, {},
        {"media_player.a": facts_of(MEDIA_RAW)},
    )  # fmt: skip
    long = "Living Room Speaker Group"
    hass.states.async_set("media_player.a", "idle", {"friendly_name": long})
    big = [w for w in result["widgets"] if w.get("size") == "l"]
    assert len(big) == 2
    width = big[1]["r"][2]
    assert await _value(hass, result, big[1]["text"]) == cut_to_fit(
        long, name_chars(width, 34), width, 34
    )
    hass.states.async_set(
        "media_player.a", "playing", {"friendly_name": long, "media_title": "Song"}
    )
    assert await _value(hass, result, big[0]["text"]) == "Song"
    assert await _value(hass, result, big[0]["vis"]) in (True, "True")
    assert await _value(hass, result, big[1]["vis"]) in (False, "False")


async def test_the_camera_caption_is_cut_in_a_layout_v2(hass: HomeAssistant) -> None:
    """Item d: the schema 1 camera's caption read "Driveway Cam…"."""
    from custom_components.apollo_tab.live import async_evaluate_slot

    built = _camera_card(2)
    [caption] = [w for w in built["card"]["w"] if w["t"] == "label"]
    [slot] = [s for s in built["slots"] if s["n"] == caption["text"]["s"]]
    width = caption["r"][2]
    long = "Driveway Camera Over The Garage Door Number 2"
    hass.states.async_set("camera.door", "idle", {"friendly_name": long})
    shown = await async_evaluate_slot(hass, slot)
    assert shown == cut_to_fit(long, name_chars(width), width)
    assert "…" in shown
    # The layout v1 keeps its own text.
    old = _camera_card(1)
    [caption1] = [w for w in old["card"]["w"] if w["t"] == "label"]
    [slot1] = [s for s in old["slots"] if s["n"] == caption1["text"]["s"]]
    assert "name_w" not in slot1.get("variables", {})


def test_a_camera_card_fades_by_its_camera_param() -> None:
    """Minor (security): the fade reads the param the camera input names."""
    component = {"inputs": {"cam": {"kind": "camera", "param": "camera_entity"}}}
    card = {"params": {"camera_entity": "camera.x"}}
    compiled = {"slots": []}
    add_unavailable(component, card, compiled)
    [slot] = compiled["slots"]
    assert compiled["un"] == {"s": slot["n"]}
    assert slot["variables"] == {"camera_entity": "camera.x"}
    assert "states(camera_entity)" in slot["template"]


async def test_a_missing_device_is_named_by_its_id(hass: HomeAssistant) -> None:
    """Minor: a person Home Assistant does not know showed person.david_smith."""
    result = _compile(
        COMPONENTS["apollo/people"], "wide", {"people": ["person.david_smith"]}, {}, {}
    )
    texts = [
        await _value(hass, result, w["text"])
        for w in result["widgets"]
        if w["t"] == "label" and isinstance(w.get("text"), dict)
    ]
    assert "David smith" in texts
    assert not [t for t in texts if "person." in str(t)]


# ---------------------------------------------------------------- dropdown


async def test_a_dropdown_with_too_many_choices_says_its_state(
    hass: HomeAssistant,
) -> None:
    """Minor: Dropdown Wide with 16 choices shown had an empty body."""
    opts = [f"Choice {i}" for i in range(16)]
    facts = {
        "select.a": facts_of(
            {"domain": "select", "state": {"attributes": {"options": opts}}}
        )
    }
    result = _compile(
        COMPONENTS["apollo/select"], "wide", {"entity": "select.a"},
        {"shown": opts}, facts,
    )  # fmt: skip
    assert "element_clipped" in result["warnings"]
    assert not [w for w in result["widgets"] if w["t"] == "choice"]
    [label] = [w for w in result["widgets"] if w.get("px") == 28]
    hass.states.async_set("select.a", "Choice 9", {"options": opts})
    assert await _value(hass, result, label["text"]) == "Choice 9"


# ---------------------------------------------------------------- room


async def test_the_room_temperature_has_a_space_before_its_unit(
    hass: HomeAssistant,
) -> None:
    """Minor: the Room read "21.4°C" where every other card reads "21.4 °C"."""
    result = _compile(
        COMPONENTS["apollo/room"], "tile",
        {"page": "o", "temperature_sensor": "sensor.t"}, {}, {},
    )  # fmt: skip
    big = next(w for w in result["widgets"] if w.get("px") == 28)
    hass.states.async_set("sensor.t", "21.4", {"unit_of_measurement": "°C"})
    assert await _value(hass, result, big["text"]) == "21.4 °C"
    hass.states.async_set("sensor.t", "21.4", {})
    assert str(await _value(hass, result, big["text"])) == "21.4"


# ---------------------------------------------------------------- schema


def _tile_doc(**variant) -> dict:
    doc = _doc()
    doc["variants"]["tile"].update(variant)
    return doc


def test_badge_false_is_for_the_tile_header() -> None:
    """Round 2: `badge: false` drops the badge of a tile header only."""
    assert (
        validate_component(_tile_doc(header="tile", badge=False))["variants"]["tile"][
            "badge"
        ]
        is False
    )
    assert validate_component(_tile_doc(header="tile"))["variants"]["tile"]["badge"]
    _refused(_tile_doc(header="title", badge=False), "bad_value", "variants.tile.badge")
    _refused(_tile_doc(header="tile", badge="no"), "bad_value", "variants.tile.badge")


def test_most_grown_needs_most_and_is_not_under_it() -> None:
    """Item g: a grown card's main row grows to `most_grown`, never less."""
    label = {"type": "label", "text": "Hello"}
    doc = _doc()
    doc["variants"]["tile"]["layout"] = [{**label, "most": 40, "most_grown": 120}]
    item = validate_component(doc)["variants"]["tile"]["layout"][0]
    assert (item["most"], item["most_grown"]) == (40, 120)
    doc["variants"]["tile"]["layout"] = [{**label, "most_grown": 120}]
    _refused(doc, "bad_value", "variants.tile.layout.0.most_grown")
    doc["variants"]["tile"]["layout"] = [{**label, "most": 40, "most_grown": 30}]
    _refused(doc, "bad_value", "variants.tile.layout.0.most_grown")
