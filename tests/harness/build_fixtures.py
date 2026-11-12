"""Build the committed panel fixtures from the bundled library."""

import json
import math
from contextlib import suppress
from pathlib import Path

import yaml
from jinja2.sandbox import SandboxedEnvironment

from custom_components.apollo_tab.maker.compile import compile_card, public_card
from custom_components.apollo_tab.maker.convert import alias_tag, convert_dashboard
from custom_components.apollo_tab.maker.schema import (
    validate_card_config,
    validate_component,
)

LIBRARY_DIR = (
    Path(__file__).resolve().parents[2] / "custom_components" / "apollo_tab" / "library"
)
COMPONENTS_DIR = LIBRARY_DIR / "components"
FIXTURES_FILE = Path(__file__).with_name("fixtures.json")

ERROR_SAMPLE = {
    "file": "my-card.yaml",
    "index": 0,
    "id": "me/thing",
    "code": "unknown_key",
    "message": "outputs.toggle: unknown key 'foo'",
}


def load_components():
    """Load and validate every built-in Component file."""
    components = {}
    for path in sorted(COMPONENTS_DIR.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for entry in raw if isinstance(raw, list) else [raw]:
            component = validate_component(entry)
            component["source"] = "builtin"
            components[component["id"]] = component
    return components


def _library(components, theme_entries):
    """Build the library object the panel would receive."""
    ordered = sorted(
        components.values(),
        key=lambda comp: (comp.get("source") != "builtin", comp.get("name", "")),
    )
    entries = [
        {
            "id": component["id"],
            "tag": alias_tag(component["id"]),
            "name": component.get("name", component["id"]),
            "description": component.get("description", ""),
            "icon": component.get("icon"),
            "version": component.get("version", "1.0.0"),
            "size": list(component.get("size", [1, 1])),
            "grid": {
                "columns": component["size"][0] * 6,
                "rows": component["size"][1] * 3,
            },
            "source": "builtin",
            "sensitive": bool(component.get("sensitive")),
            "approved": True,
            "params": component.get("params", {}),
        }
        for component in ordered
    ]
    return {
        "components": entries,
        "errors": [ERROR_SAMPLE],
        "themes": theme_entries,
        "components_path": "/config/apollo_tab/components",
    }


def _states(*_args):
    """Stand in for states(), always reporting 'unknown'."""
    return "unknown"


def _state_attr(*_args):
    """Stand in for state_attr(), always reporting None."""
    return None


def _expand(*_args):
    """Stand in for expand(), always returning an empty list."""
    return []


def _to_int(value, default=0):
    """Return value as an int, falling back to default."""
    try:
        return int(value)
    except TypeError, ValueError:
        return default


def _to_float(value, default=0.0):
    """Return value as a float, falling back to default."""
    try:
        return float(value)
    except TypeError, ValueError:
        return default


def renderer():
    """Return a sandboxed Jinja environment with Home Assistant stand-ins."""
    env = SandboxedEnvironment()
    env.globals["states"] = _states
    env.globals["state_attr"] = _state_attr
    env.globals["expand"] = _expand
    env.filters["int"] = _to_int
    env.filters["float"] = _to_float
    return env


def _coerce(text):
    """Coerce a rendered slot string to a number when it looks numeric."""
    with suppress(ValueError):
        return int(text)
    with suppress(ValueError):
        number = float(text)
        if math.isfinite(number):
            return number
    return text


def render_slots(slots, env):
    """Render every slot once into a values mapping keyed by slot number."""
    values = {}
    for slot in slots:
        if not isinstance(slot, dict) or "n" not in slot:
            continue
        if slot.get("kind") in ("history", "action"):
            values[str(slot["n"])] = []
            continue
        try:
            text = env.from_string(slot.get("template") or "").render(
                **slot.get("variables") or {}
            )
        except Exception:
            # A slot that fails to render is left out of the values.
            continue
        values[str(slot["n"])] = _coerce(text)
    return values


def _card(component_id, params):
    """Build a stored card config for a Component."""
    return {
        "type": "custom:apollo-tab-card",
        "component": component_id,
        "params": params,
    }


def _sample_dashboard():
    """Return the fixed two-view sample dashboard for the layout fixture."""
    graphs = [
        _card("apollo/sensor-graph", {"entity": f"sensor.graph_{n}"}) for n in range(5)
    ]
    home = {
        "type": "sections",
        "title": "Home",
        "path": "home",
        "icon": "mdi:home",
        "max_columns": 3,
        "sections": [
            {"title": "Energy", "column_span": 3, "cards": graphs},
            {
                "title": "Lights",
                "cards": [
                    _card("apollo/light-tile", {"entity": "light.kitchen"}),
                    _card("apollo/light-slider", {"entity": "light.living_room"}),
                    _card("apollo/fan", {"entity": "fan.bedroom"}),
                    _card(
                        "apollo/sensor-value",
                        {"entity": "sensor.indoor_temperature"},
                    ),
                    {"type": "tile", "entity": "light.porch"},
                ],
            },
            {
                "title": "Rooms",
                "cards": [
                    _card("apollo/media-player", {"entity": "media_player.den"}),
                    _card("apollo/weather", {"entity": "weather.home"}),
                    _card("apollo/camera-snapshot", {"entity": "camera.driveway"}),
                    _card("apollo/lock", {"entity": "lock.front_door"}),
                    _card(
                        "apollo/scene-row",
                        {"scenes": ["scene.movie", "scene.dinner"]},
                    ),
                ],
            },
        ],
    }
    climate = {
        "type": "sections",
        "title": "Climate",
        "path": "climate",
        "icon": "mdi:thermometer",
        "max_columns": 3,
        "sections": [
            {
                "title": "Climate",
                "cards": [
                    _card("apollo/thermostat", {"entity": "climate.hallway"}),
                    _card(
                        "apollo/alarm-panel",
                        {"entity": "alarm_control_panel.home"},
                    ),
                    _card("apollo/blinds", {"entity": "cover.lounge"}),
                ],
            }
        ],
    }
    return {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [home, climate],
    }


def load_theme_entries():
    """Load the bundled themes in file order."""
    return json.loads((LIBRARY_DIR / "themes.json").read_text(encoding="utf-8"))


def build() -> dict:
    """Build the whole fixtures payload as a dictionary.

    The UI strings are not included: the harness page reads strings.json
    itself, so changing a string never makes this file stale.
    """
    theme_entries = load_theme_entries()
    themes = {entry["id"]: entry for entry in theme_entries}
    components = load_components()
    library = _library(components, theme_entries)
    env = renderer()
    cards = []
    for entry in library["components"]:
        component = components[entry["id"]]
        card_config = {"type": "custom:apollo-tab-card", "component": entry["id"]}
        validated = validate_card_config(component, card_config)
        compiled = compile_card(component, validated)
        cards.append(
            {
                "id": entry["id"],
                "card": card_config,
                "init": public_card(compiled),
                "values": render_slots(compiled.get("slots") or [], env),
            }
        )
    sample = _sample_dashboard()
    result = convert_dashboard(
        sample, components=components, themes=themes, approved=set()
    )
    layout = result["layout"]
    layout_entry = {
        "url_path": "tab-1",
        "layout": layout,
        "warnings": result["warnings"],
        "values": render_slots(result["bindings"]["slots"], env),
        "sources": result["sources"],
    }
    dashboards = {
        "dashboards": [
            {
                "url_path": "tab-1",
                "title": "TAB-1",
                "mode": "storage",
                "theme": "midnight",
                "pages": len(layout["pages"]),
                "warnings": len(result["warnings"]),
                "hash": layout["hash"],
            }
        ],
        "tablets": 0,
        "sent_to_tablets": False,
    }
    return {
        "themes": theme_entries,
        "library": library,
        "cards": cards,
        "sample_config": sample,
        "layout": layout_entry,
        "dashboards": dashboards,
    }


def render_text() -> str:
    """Return the fixtures file content as deterministic JSON text.

    Keys keep the order they were built in, as Home Assistant's own JSON
    does: a card's params stay in the order of its YAML file, which is the
    order the forms show them in. The build is deterministic, so the text is
    too.
    """
    return json.dumps(build(), indent=1) + "\n"


def main() -> None:
    """Write the fixtures file next to this module."""
    FIXTURES_FILE.write_text(render_text(), encoding="utf-8")
    print(f"Wrote {FIXTURES_FILE}")


if __name__ == "__main__":
    main()
