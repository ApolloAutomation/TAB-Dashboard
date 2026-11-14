"""The cards fixture of the first release: layout_v2_cards.* and its .v1 pair.

A dashboard with the nine cards of step A (package I9) on 2 normal pages,
with the detail pages of its lights. Home Assistant converts it for a tablet
with engine 0.2.0 (layout v2, the caps of contract.json "engine_caps") and
for one with engine 0.1.0 (layout v1, the caps of hello.json case 0), as the
manager and the sender do. The bytes come from the reference code
(reference/tabproto.py); tests/test_cards_fixture.py checks that the
integration's own writer gives the same.

Usage: python -B tests/cards_fixture.py <contract dir>
Writes only the five files of layout_v2_cards into <contract dir>/fixtures.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custom_components.apollo_tab.maker.convert import convert_dashboard  # noqa: E402
from custom_components.apollo_tab.maker.features import facts_of  # noqa: E402
from custom_components.apollo_tab.maker.schema import validate_component  # noqa: E402

LIBRARY = ROOT / "custom_components" / "apollo_tab" / "library"
CONTRACT = ROOT / "tests" / "contract"
NAME = "layout_v2_cards"
FILES = (
    f"{NAME}.source.json",
    f"{NAME}.dl.json",
    f"{NAME}.meta.json",
    f"{NAME}.v1.dl.json",
    f"{NAME}.v1.meta.json",
)
# The nine cards of the first release.
CARDS = (
    "apollo/light",
    "apollo/switch",
    "apollo/button",
    "apollo/scenes",
    "apollo/reading",
    "apollo/number",
    "apollo/select",
    "apollo/screen",
    "apollo/page-link",
)

# What engine 0.1.0 answers in tab_hello (hello.json, case 0): what tablets
# in the field have.
CAPS_V1 = {
    "w": [
        "heading", "card", "label", "button", "switch", "slider", "thermostat",
        "chart", "image",
    ],
    "icons": 1,
    "screen": [1280, 800],
    "max_layout": 262144,
    "max_chunk": 16000,
    "max_slots": 1024,
    "max_widgets": 2048,
}  # fmt: skip

# What Home Assistant knows of each device (maker/features.py reads it).
DEVICES = {
    # The owner's lamp: colour, colour temperature from 15 K, no effects.
    "light.sofa": {
        "domain": "light",
        "registry": {
            "capabilities": {
                "supported_color_modes": ["color_temp", "hs", "xy"],
                "min_color_temp_kelvin": 15,
                "max_color_temp_kelvin": 6535,
            }
        },
    },
    "light.ceiling": {
        "domain": "light",
        "registry": {"capabilities": {"supported_color_modes": ["brightness"]}},
    },
    "light.desk": {
        "domain": "light",
        "registry": {
            "capabilities": {
                "supported_color_modes": ["color_temp", "hs"],
                "min_color_temp_kelvin": 2200,
                "max_color_temp_kelvin": 6500,
                "effect_list": ["Candle", "Rainbow", "Party", "Night"],
            },
            "features": ["EFFECT"],
        },
    },
    "light.porch": {
        "domain": "light",
        "registry": {"capabilities": {"supported_color_modes": ["onoff"]}},
    },
    "light.backlight": {
        "domain": "light",
        "registry": {"capabilities": {"supported_color_modes": ["brightness"]}},
    },
    "switch.kettle": {"domain": "switch"},
    "input_boolean.guest": {"domain": "input_boolean"},
    "script.night": {"domain": "script"},
    "button.doorbell": {"domain": "button"},
    "scene.movie": {"domain": "scene"},
    "scene.dinner": {"domain": "scene"},
    "scene.all_off": {"domain": "scene"},
    "sensor.temperature": {
        "domain": "sensor",
        "registry": {"device_class": "temperature"},
    },
    "binary_sensor.door": {
        "domain": "binary_sensor",
        "registry": {"device_class": "door"},
    },
    "input_number.target": {
        "domain": "input_number",
        "state": {"attributes": {"min": 16, "max": 26, "step": 0.5}},
    },
    "select.mode": {
        "domain": "select",
        "registry": {"capabilities": {"options": ["Eco", "Comfort", "Away", "Boost"]}},
    },
}


def _card(component: str, variant: str, grid: tuple[int, int], **extra) -> dict:
    """Return one dashboard card of a built-in schema 2 file."""
    columns, rows = grid
    return {
        "type": "custom:apollo-tab-card",
        "component": component,
        "variant": variant,
        "grid_options": {"columns": columns, "rows": rows},
        **extra,
    }


DASHBOARD = {
    "apollo_tab": {"version": 1, "theme": "midnight"},
    "views": [
        {
            "type": "sections",
            "title": "Home",
            "path": "home",
            "icon": "mdi:home",
            "max_columns": 3,
            "sections": [
                {
                    "type": "grid",
                    "title": "Living room",
                    "cards": [
                        _card(
                            "apollo/light",
                            "tile",
                            (6, 3),
                            title="Sofa lamp",
                            params={"entity": "light.sofa"},
                        ),
                        _card(
                            "apollo/switch",
                            "tile",
                            (6, 3),
                            params={"entity": "switch.kettle"},
                        ),
                        _card(
                            "apollo/light",
                            "wide",
                            (12, 3),
                            params={"entity": "light.ceiling"},
                        ),
                        _card(
                            "apollo/scenes",
                            "wide",
                            (12, 3),
                            params={
                                "scenes": [
                                    "scene.movie",
                                    "scene.dinner",
                                    "scene.all_off",
                                ]
                            },
                        ),
                    ],
                },
                {
                    "type": "grid",
                    "title": "Sofa lamp · Farbe",
                    "cards": [
                        _card(
                            "apollo/light",
                            "large",
                            (12, 6),
                            title="Sofa lamp",
                            params={"entity": "light.sofa"},
                            options={
                                "colour_control": "both",
                                "show_saturation": True,
                            },
                        ),
                        _card(
                            "apollo/reading",
                            "tile",
                            (6, 3),
                            params={"entity": "sensor.temperature"},
                        ),
                        _card(
                            "apollo/page-link",
                            "tile",
                            (6, 3),
                            params={"page": "more", "entity": "sensor.temperature"},
                        ),
                    ],
                },
                {
                    "type": "grid",
                    "title": "House",
                    "cards": [
                        _card(
                            "apollo/number",
                            "wide",
                            (12, 3),
                            params={"entity": "input_number.target"},
                        ),
                        _card(
                            "apollo/select",
                            "wide",
                            (12, 3),
                            params={"entity": "select.mode"},
                        ),
                        _card(
                            "apollo/screen",
                            "row",
                            (12, 2),
                            params={"entity": "light.backlight"},
                        ),
                        _card(
                            "apollo/button",
                            "small",
                            (6, 2),
                            params={"entity": "script.night"},
                        ),
                        _card(
                            "apollo/page-link",
                            "small",
                            (6, 2),
                            params={"page": "more"},
                        ),
                    ],
                },
            ],
        },
        {
            "type": "sections",
            "title": "More",
            "path": "more",
            # Level 1: a view icon above it would be the fallback glyph in
            # the side bar of a tablet with engine 0.1.0.
            "icon": "mdi:cog",
            "max_columns": 3,
            "sections": [
                {
                    "type": "grid",
                    "title": "Desk",
                    "cards": [
                        _card(
                            "apollo/light",
                            "large",
                            (12, 6),
                            params={"entity": "light.desk"},
                            options={"colour_control": "dots"},
                        ),
                        _card(
                            "apollo/light",
                            "tile",
                            (6, 3),
                            params={"entity": "light.porch"},
                        ),
                        _card(
                            "apollo/button",
                            "tile",
                            (6, 3),
                            params={"entity": "button.doorbell"},
                        ),
                    ],
                },
                {
                    "type": "grid",
                    "title": "Status",
                    "cards": [
                        _card(
                            "apollo/reading",
                            "wide",
                            (12, 3),
                            params={"entity": "binary_sensor.door"},
                        ),
                        _card(
                            "apollo/reading",
                            "chip",
                            (12, 1),
                            params={"entity": "sensor.temperature"},
                        ),
                        _card(
                            "apollo/switch",
                            "chip",
                            (12, 1),
                            params={"entity": "input_boolean.guest"},
                        ),
                        _card(
                            "apollo/switch",
                            "small",
                            (6, 2),
                            params={"entity": "switch.kettle"},
                        ),
                        _card(
                            "apollo/button",
                            "chip",
                            (12, 1),
                            params={"entity": "script.night"},
                        ),
                    ],
                },
                {
                    "type": "grid",
                    "title": "Settings",
                    "cards": [
                        _card(
                            "apollo/select",
                            "large",
                            (12, 6),
                            params={"entity": "select.mode"},
                        ),
                        _card(
                            "apollo/number",
                            "row",
                            (12, 2),
                            params={"entity": "input_number.target"},
                        ),
                        _card(
                            "apollo/screen",
                            "wide",
                            (12, 3),
                            params={"entity": "light.backlight"},
                        ),
                    ],
                },
            ],
        },
    ],
}


def reference():
    """Return the contract's reference code, tabproto.py."""
    path = CONTRACT / "reference" / "tabproto.py"
    spec = importlib.util.spec_from_file_location("tab_reference_tabproto", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_library() -> tuple[dict, dict]:
    """Return the built-in components and themes, marked built in."""
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


def facts() -> dict:
    """Return the facts of every device, as the manager hands them over."""
    return {entity: facts_of(raw) for entity, raw in sorted(DEVICES.items())}


def convert(dashboard: dict, facts_in: dict, dl: int, icons: dict, caps) -> dict:
    """Convert as the manager does: version 1 stored, version 2 per tablet."""
    components, themes = load_library()
    return convert_dashboard(
        dashboard,
        components=components,
        themes=themes,
        approved=set(),
        facts=facts_in,
        dl=dl,
        icons=icons,
        caps=caps,
    )


def dump(obj) -> bytes:
    """Return a fixture's text as gen_fixtures.py writes it."""
    text = json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    return text.encode("utf-8")


def build(contract: Path = CONTRACT) -> dict[str, bytes]:
    """Return the five files, by name, for the contract folder."""
    tp = reference()
    icons = json.loads((contract / "icons.json").read_text(encoding="utf-8"))
    engine_caps = json.loads((contract / "contract.json").read_text(encoding="utf-8"))[
        "engine_caps"
    ]
    facts_in = facts()
    v2 = convert(DASHBOARD, facts_in, 2, icons, engine_caps)
    v1 = convert(DASHBOARD, facts_in, 1, icons, None)
    compiled = tp.compile_device_layout_v2(v2["layout"], icons, engine_caps)
    compiled_v1 = tp.compile_device_layout(v1["layout"], icons, CAPS_V1)
    source = {
        "note": (
            "The nine cards of the first version 2 library (package I9) on 2 "
            "normal pages, with the detail pages of the lights. Made by "
            "tests/cards_fixture.py in apollo_tab: 'dashboard' and 'facts' "
            "are what Home Assistant converts; 'layout' is the layout v2 for "
            "a tablet with the caps of contract.json 'engine_caps', 'v1' the "
            "layout v1 for a tablet with engine 0.1.0 (the caps of the .v1 "
            "meta file). 'devices' is what Home Assistant knows of each "
            "device, from which 'facts' are made."
        ),
        "dashboard": DASHBOARD,
        "devices": DEVICES,
        "facts": facts_in,
        "layout": v2["layout"],
        "bindings": v2["bindings"],
        "warnings": v2["warnings"],
        "v1": {
            "layout": v1["layout"],
            "bindings": v1["bindings"],
            "warnings": v1["warnings"],
            "simpler": v1["simpler"],
        },
    }
    return {
        f"{NAME}.source.json": dump(source),
        # The exact bytes the tablet receives. No trailing newline.
        f"{NAME}.dl.json": compiled["bytes"],
        f"{NAME}.meta.json": dump(
            {
                "caps": engine_caps,
                "hash": compiled["hash"],
                "size": compiled["size"],
                "slots": compiled["slots"],
                "dropped": compiled["dropped"],
                "counts": compiled["counts"],
                "source_hash": v2["layout"]["hash"],
            }
        ),
        f"{NAME}.v1.dl.json": compiled_v1["bytes"],
        f"{NAME}.v1.meta.json": dump(
            {
                "caps": CAPS_V1,
                "hash": compiled_v1["hash"],
                "size": compiled_v1["size"],
                "slots": compiled_v1["slots"],
                "dropped": compiled_v1["dropped"],
                "counts": compiled_v1["counts"],
                "source_hash": v1["layout"]["hash"],
            }
        ),
    }


def main() -> None:
    """Write the five files into the contract folder given."""
    contract = Path(sys.argv[1]).resolve()
    for name, data in build(contract).items():
        (contract / "fixtures" / name).write_bytes(data)
        print(name, len(data), "bytes")


if __name__ == "__main__":
    main()
