"""Write the golden fixtures of the contract, versions 1 and 2.

Usage: python -B gen_fixtures.py <path to custom_components/apollo_tab> <contract dir>

Reads the integration's maker package and card library (nothing is written
there) and writes <contract dir>/contract.json and <contract dir>/fixtures/*.
Run it again only when the contract changes; both builds copy the output.
"""

import json
import math
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
INTEGRATION = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(INTEGRATION))

import tabproto as tp  # noqa: E402
from maker.convert import convert_dashboard  # noqa: E402
from maker.schema import validate_component  # noqa: E402

FIX = OUT / "fixtures"
FIX.mkdir(parents=True, exist_ok=True)

ICONS = json.loads((OUT / "icons.json").read_text(encoding="utf-8"))
MAC = "aabbccddeeff"
PSK = bytes(range(32))
SECRET = bytes(range(100, 132))
NONCE = "0123456789abcdef0123456789abcdef"


def write(name: str, obj) -> None:
    path = FIX / name
    path.write_text(
        json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_library() -> tuple[dict, dict]:
    components = {}
    for path in sorted((INTEGRATION / "library" / "components").glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            component = validate_component(doc)
            component["source"] = "builtin"
            components[component["id"]] = component
    themes = {
        theme["id"]: {k: v for k, v in theme.items() if k != "id"}
        for theme in json.loads(
            (INTEGRATION / "library" / "themes.json").read_text(encoding="utf-8")
        )
    }
    return components, themes


def card(component: str, **params) -> dict:
    return {"type": "custom:apollo-tab-card", "component": component, "params": params}


SMALL = {
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
                    "title": "Kitchen",
                    "cards": [
                        card("apollo/light-tile", entity="light.kitchen"),
                        card("apollo/sensor-value", entity="sensor.kitchen_humidity"),
                    ],
                }
            ],
        }
    ],
}

ALL_CARDS = {
    "apollo_tab": {"version": 1, "theme": "warm"},
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
                        card("apollo/light-tile", entity="light.sofa"),
                        card("apollo/fan", entity="fan.ceiling"),
                        card("apollo/light-slider", entity="light.ceiling"),
                        card("apollo/blinds", entity="cover.blinds"),
                        card("apollo/sensor-value", entity="sensor.humidity"),
                    ],
                },
                {
                    "type": "grid",
                    "title": "Climate · Wärme",
                    "cards": [
                        card("apollo/thermostat", entity="climate.living"),
                        card("apollo/sensor-graph", entity="sensor.temperature"),
                        card("apollo/weather", entity="weather.home"),
                    ],
                },
                {
                    "type": "grid",
                    "cards": [
                        card(
                            "apollo/scene-row",
                            scenes=["scene.movie", "scene.dinner", "scene.all_off"],
                        ),
                        card("apollo/media-player", entity="media_player.living"),
                        card(
                            "community/room-summary",
                            temperature_sensor="sensor.temperature",
                            humidity_sensor="sensor.humidity",
                            lights=["light.sofa", "light.ceiling"],
                            page="security",
                        ),
                        {
                            **card(
                                "community/energy-gauge", entity="sensor.power", max=5000
                            ),
                            "style": {"color": "#203040", "accent": "#40C0FF"},
                        },
                    ],
                },
            ],
        },
        {
            "type": "sections",
            "title": "Security",
            "path": "security",
            "icon": "mdi:shield-home",
            "max_columns": 3,
            "sections": [
                {
                    "type": "grid",
                    "cards": [
                        {"type": "heading", "heading": "Doors", "icon": "mdi:lock"},
                        card("apollo/lock", entity="lock.front_door"),
                        card("apollo/alarm-panel", entity="alarm_control_panel.home"),
                        card("apollo/camera-snapshot", entity="camera.driveway"),
                        card(
                            "community/presence-chips",
                            people=["person.alex", "person.sam"],
                        ),
                    ],
                }
            ],
        },
    ],
}

# What Home Assistant would evaluate for the slots of ALL_CARDS, keyed by the
# last expression of the slot's template (the text after the input preludes).
NAMES = {
    "light.sofa": "Sofa lamp",
    "light.ceiling": "Ceiling light",
    "fan.ceiling": "Ceiling fan",
    "cover.blinds": "Blinds",
    "sensor.humidity": "Humidity",
    "climate.living": "Heating",
    "sensor.temperature": "Temperature",
    "weather.home": "Weather",
    "sensor.power": "Power",
    "alarm_control_panel.home": "Alarm",
    "scene.movie": "Movie",
    "scene.dinner": "Dinner",
    "scene.all_off": "All off",
    "person.alex": "Alex",
    "person.sam": "Sam",
}
RAW_BY_TAIL = {
    "{{ state }}": "on",
    "{{ brightness }}": 80,
    "{{ brightness }}%": "80%",
    "{{ position }}": 60,
    "{{ state }} · {{ position }}%": "open · 60%",
    "{{ reading }}{{ unit }}": "46%",
    "{{ reading }}": "21.4",
    "{{ target }}": 21.5,
    "{{ low }}": 7.0,
    "{{ high }}": 35.0,
    "{{ step }}": 0.5,
    "Now {{ current if current is not none else '–' }}° · {{ action }}": "Now 20.8° · heating",
    "{{ icon }}": "mdi:weather-partly-cloudy",
    "{{ temperature }}° · {{ condition }}": "12° · partlycloudy",
    "{{ artwork }}": "/api/media_player_proxy/media_player.living?token=x",
    "{{ title }} · {{ artist }}": "Soft focus · Mara Lind",
    "{{ volume }}": 35,
    "{{ temperature }}° · {{ humidity }}% · {{ lights_on }} lights on": "21.5° · 46% · 2 lights on",
    "{{ power }}": 2400.0,
    "{{ limit }}": 5000,
    "{{ power }} W": "2400.0 W",
    "Lock {{ name }}?": "Lock Front door?",
    "Unlock {{ name }}?": "Unlock Front door?",
    "{{ name }}: {{ state }}": "Front door: locked",
    "{{ snapshot }}": "/api/camera_proxy/camera.driveway?token=x",
    "{{ name }}": "Driveway",
}


def raw_value(slot: dict):
    if slot["kind"] == "history":
        return [19.2, 19.4, 19.36, 19.9, 20.4, 20.2, 20.9, 21.3, 21.1, 21.7, 21.9, 21.4]
    if slot["kind"] == "action":
        return [14, 11, 13, 15, 10]
    variables = slot["variables"]
    tail = slot["template"].rsplit("%}", 1)[-1]
    if tail in RAW_BY_TAIL:
        return RAW_BY_TAIL[tail]
    if "component_name" in tail:
        return NAMES.get(variables.get("entity"), variables["component_name"])
    if "or scene" in tail:
        return NAMES[variables["scene"]]
    if "'mdi:account'" in tail:
        return "mdi:account" if variables["person"] == "person.alex" else "/local/sam.jpg"
    if "or person" in tail:
        return NAMES[variables["person"]] + ": home"
    raise SystemExit("no sample value for " + tail)


def build(name: str, config: dict, components: dict, themes: dict) -> dict:
    result = convert_dashboard(
        config, components=components, themes=themes, approved=set()
    )
    layout = result["layout"]
    compiled = tp.compile_device_layout(layout, ICONS)
    write(
        f"{name}.source.json",
        {
            "dashboard": config,
            "layout": layout,
            "bindings": result["bindings"],
            "warnings": result["warnings"],
        },
    )
    # The exact bytes the tablet receives. No trailing newline.
    (FIX / f"{name}.dl.json").write_bytes(compiled["bytes"])
    write(
        f"{name}.meta.json",
        {
            "hash": compiled["hash"],
            "size": compiled["size"],
            "slots": compiled["slots"],
            "dropped": compiled["dropped"],
            "source_hash": layout["hash"],
        },
    )
    return {"result": result, "compiled": compiled}


def state_stream(built: dict) -> None:
    compiled = built["compiled"]
    by_source = {slot["n"]: slot for slot in built["result"]["bindings"]["slots"]}
    raw = {n: raw_value(slot) for n, slot in by_source.items()}
    level = ICONS["version"]
    wire = {
        entry["d"]: tp.coerce(entry["type"], raw[entry["src"]], ICONS, level)
        for entry in compiled["slots"]
    }
    layout_hash = compiled["hash"]
    steps = []
    current: dict[int, object] = {}

    def step(note, values, *, full=False, limit=tp.MAX_SET_BYTES, layout=layout_hash):
        payloads = tp.encode_set(layout, values, full=full, limit=limit)
        expect = "ok"
        if layout != layout_hash:
            expect = "hash"
        else:
            if full:
                current.clear()
                current.update({entry["d"]: None for entry in compiled["slots"]})
            current.update(values)
        steps.append(
            {
                "note": note,
                "payloads": payloads,
                "expect": expect,
                "after": {str(k): current[k] for k in sorted(current)},
            }
        )

    step("Full snapshot after the layout is on the tablet.", wire, full=True)
    by_type = {}
    for entry in compiled["slots"]:
        by_type.setdefault(entry["type"], []).append(entry["d"])
    step(
        "One light turns off: a bool slot and a text slot change.",
        {by_type["b"][0]: 0, by_type["t"][1]: "0%"},
    )
    step("A number moves by a fraction.", {by_type["n"][0]: 20.125})
    step("A graph gets new points.", {by_type["l"][0]: [1, 2.5, 3, -4.25]})
    step("An entity becomes unavailable: the slot has no value.", {by_type["t"][0]: None})
    step("An icon changes.", {by_type["i"][0]: ICONS["icons"]["mdi:weather-rainy"][0]})
    step(
        "Text with characters outside ASCII and JSON escapes.",
        {by_type["t"][2]: 'Küche "A"\\B · 21°\n2'},
    )
    step("A delta for another layout is refused.", {1: "x"}, layout="0" * 16)
    step("Full snapshot split over several calls (small limit).", wire, full=True, limit=400)
    write(
        "state_stream.json",
        {
            "layout": "layout_all_cards",
            "hash": layout_hash,
            "raw_values_by_source_slot": {str(k): raw[k] for k in sorted(raw)},
            "wire_values_by_device_slot": {str(k): wire[k] for k in sorted(wire)},
            "steps": steps,
        },
    )


def chunks(built: dict) -> None:
    data = built["compiled"]["bytes"]
    layout_hash = built["compiled"]["hash"]
    parts = tp.chunk_layout(data, 3000)
    assert "".join(parts).encode("utf-8") == data
    assert len(parts) >= 3

    def calls(items, total=None, size=None, layout=layout_hash):
        total = len(parts) if total is None else total
        size = len(data) if size is None else size
        return [
            {"hash": layout, "seq": seq, "total": total, "size": size, "data": text}
            for seq, text in items
        ]

    good = calls(list(enumerate(parts)))

    def whole(obj_or_bytes):
        """One-chunk transfer of some other bytes, with their own hash."""
        raw = obj_or_bytes if isinstance(obj_or_bytes, bytes) else tp.canonical(obj_or_bytes)
        return {
            "calls": [
                {
                    "hash": tp.content_hash(raw),
                    "seq": 0,
                    "total": 1,
                    "size": len(raw),
                    "data": raw.decode("utf-8"),
                }
            ],
            "expect": ["ok"],
            "commit_hash": tp.content_hash(raw),
        }

    device = json.loads(data)
    empty_page = {"title": "", "w": []}
    many_pages = {**device, "nav": [], "pages": [empty_page] * (tp.MAX_PAGES + 1), "slots": ""}
    many_slots = {**device, "nav": [], "pages": [empty_page], "slots": "t" * (tp.MAX_SLOTS + 1)}
    write(
        "chunks.json",
        {
            "note": (
                "Each case starts on a fresh tablet that is not paired, so the "
                "auth argument of tab_commit is empty. 'expect' lists the "
                "result of each tab_layout call; 'commit' is the result of "
                "tab_commit(commit_hash or the first call's hash). "
                "'platform.alloc_fails': no PSRAM block can be had. "
                "'platform.build_fails': the build that follows the commit "
                "ends with that code. 'after_commit' holds calls made right "
                "after that commit (after the failed build with build_fails), "
                "'building' whether a build runs after those calls, then "
                "tab_commit(commit_hash or their first hash). 'shown' is the "
                "hash on screen at the end (default: the hash when 'commit' is "
                "ok, else empty)."
            ),
            "layout": "layout_all_cards",
            "hash": layout_hash,
            "size": len(data),
            "chunk_bytes": 3000,
            "cases": [
                {
                    "name": "good",
                    "calls": good,
                    "expect": ["ok"] * len(good),
                    "commit": "ok",
                },
                {
                    "name": "restart_from_zero",
                    "note": "A transfer may be dropped and started again at seq 0.",
                    "calls": good[:2] + good,
                    "expect": ["ok"] * (len(good) + 2),
                    "commit": "ok",
                },
                {
                    "name": "out_of_order",
                    "calls": [good[0], good[2]],
                    "expect": ["ok", "order"],
                    "commit": "incomplete",
                },
                {
                    "name": "missing_last",
                    "calls": good[:-1],
                    "expect": ["ok"] * (len(good) - 1),
                    "commit": "incomplete",
                },
                {
                    "name": "wrong_hash",
                    "note": "All bytes arrive but they do not hash to the announced value.",
                    "calls": calls(list(enumerate(parts)), layout="f" * 16),
                    "expect": ["ok"] * len(good),
                    "commit": "hash",
                    "commit_hash": "f" * 16,
                },
                {
                    "name": "too_big",
                    "calls": calls([(0, parts[0])], size=tp.MAX_LAYOUT_BYTES + 1),
                    "expect": ["too_big"],
                    "commit": "incomplete",
                },
                {
                    "name": "size_mismatch",
                    "note": "More bytes than announced.",
                    "calls": calls(list(enumerate(parts)), size=len(data) - 10),
                    "expect": ["ok"] * (len(good) - 1) + ["size"],
                    "commit": "incomplete",
                },
                {
                    "name": "commit_other_hash",
                    "calls": good,
                    "expect": ["ok"] * len(good),
                    "commit": "incomplete",
                    "commit_hash": "1" * 16,
                },
                {
                    "name": "not_json",
                    "note": "The bytes hash correctly but are not a device layout.",
                    **whole(b'{"v":1,"pages":[{"title":"x","w":[}'),
                    "commit": "parse",
                },
                {
                    "name": "wrong_shape",
                    "note": "Valid JSON without pages.",
                    **whole({"v": 1, "screen": [1280, 800], "slots": ""}),
                    "commit": "parse",
                },
                {
                    "name": "newer_layout_version",
                    **whole({**device, "v": 3}),
                    "commit": "version",
                },
                {
                    "name": "too_many_pages",
                    **whole(many_pages),
                    "commit": "limits",
                },
                {
                    "name": "too_many_slots",
                    **whole(many_slots),
                    "commit": "limits",
                },
                {
                    "name": "no_memory",
                    "note": "The platform cannot give a block for the bytes.",
                    "platform": {"alloc_fails": True},
                    "calls": [good[0]],
                    "expect": ["memory"],
                    "commit": "incomplete",
                },
                {
                    "name": "new_transfer_during_build",
                    "note": (
                        "seq 0 never answers busy. It drops the build that is "
                        "still running; the old layout stays on screen. The "
                        "second transfer then commits normally."
                    ),
                    "calls": good,
                    "expect": ["ok"] * len(good),
                    "commit": "ok",
                    "after_commit": {
                        "calls": good,
                        "expect": ["ok"] * len(good),
                        "building": False,
                        "commit": "ok",
                    },
                    "shown": layout_hash,
                },
                {
                    "name": "header_too_big_first",
                    "note": "seq 0 checks too_big before the other header fields.",
                    "calls": [{"hash": "xyz", "seq": 0, "total": 0, "size": tp.MAX_LAYOUT_BYTES + 1, "data": parts[0]}],
                    "expect": ["too_big"],
                    "commit": "incomplete",
                    "commit_hash": layout_hash,
                },
                {
                    "name": "header_hash_not_lower_case_hex",
                    "calls": calls([(0, parts[0])], layout=layout_hash.upper()),
                    "expect": ["order"],
                    "commit": "incomplete",
                    "commit_hash": layout_hash,
                },
                {
                    "name": "header_total_zero",
                    "calls": calls([(0, parts[0])], total=0),
                    "expect": ["order"],
                    "commit": "incomplete",
                },
                {
                    "name": "header_size_zero",
                    "note": "order is checked before size.",
                    "calls": [{"hash": layout_hash, "seq": 0, "total": 1, "size": 0, "data": ""}],
                    "expect": ["size"],
                    "commit": "incomplete",
                },
                {
                    "name": "header_more_data_than_size",
                    "calls": [{"hash": layout_hash, "seq": 0, "total": 1, "size": 10, "data": "0123456789x"}],
                    "expect": ["size"],
                    "commit": "incomplete",
                },
                {
                    "name": "header_checked_before_memory",
                    "note": "size is checked before anything is allocated.",
                    "platform": {"alloc_fails": True},
                    "calls": [{"hash": layout_hash, "seq": 0, "total": 1, "size": 10, "data": "0123456789x"}],
                    "expect": ["size"],
                    "commit": "incomplete",
                },
                {
                    "name": "bad_header_drops_the_build",
                    "note": (
                        "A seq 0 call drops the unfinished transfer and any build "
                        "in progress first, also when its header is refused. "
                        "Nothing is left to commit."
                    ),
                    "calls": good,
                    "expect": ["ok"] * len(good),
                    "commit": "ok",
                    "after_commit": {
                        "calls": [{"hash": "bad", "seq": 0, "total": 1, "size": 10, "data": "0123456789"}],
                        "expect": ["order"],
                        "building": False,
                        "commit_hash": layout_hash,
                        "commit": "incomplete",
                    },
                    "shown": "",
                },
                {
                    "name": "repeated_commit_while_building",
                    "note": (
                        "HA lost the answer to tab_commit and commits the same "
                        "hash again: success, and the build carries on unchanged."
                    ),
                    "calls": good,
                    "expect": ["ok"] * len(good),
                    "commit": "ok",
                    "after_commit": {
                        "calls": [],
                        "expect": [],
                        "building": True,
                        "commit_hash": layout_hash,
                        "commit": "ok",
                    },
                    "shown": layout_hash,
                },
                {
                    "name": "repeated_commit_after_failed_build",
                    "note": (
                        "The build ran out of memory ('build_fails'), so the "
                        "staged layout is gone: a repeated commit answers "
                        "incomplete, and tab_status reports build 'memory'."
                    ),
                    "platform": {"build_fails": "memory"},
                    "calls": good,
                    "expect": ["ok"] * len(good),
                    "commit": "ok",
                    "after_commit": {
                        "calls": [],
                        "expect": [],
                        "building": False,
                        "commit_hash": layout_hash,
                        "commit": "incomplete",
                    },
                    "shown": "",
                },
            ],
        },
    )


def find_widget(built: dict, kind: str, key: str) -> dict:
    device = json.loads(built["compiled"]["bytes"])
    for page in device["pages"]:
        for item in page["w"]:
            for widget in item.get("w", []):
                if widget["t"] == kind and key in widget:
                    return widget
    raise SystemExit(f"no {kind} with {key}")


def input_events(built: dict) -> None:
    layout_hash = built["compiled"]["hash"]
    switch = find_widget(built, "switch", "tap")
    slider = find_widget(built, "slider", "change")
    locker = find_widget(built, "button", "cf")
    cases = []

    def case(name, expect, payload, signature=None, **extra):
        if signature is None:
            signature = tp.sign(SECRET, payload)
        data = {"d": payload, "s": signature}
        data.update(extra.pop("data", {}))
        cases.append({"name": name, "data": data, "expect": expect, **extra})

    def payload(counter, widget, event, confirmed=False, value=None, **over):
        return tp.input_payload(
            over.get("mac", MAC),
            over.get("nonce", NONCE),
            counter,
            over.get("layout", layout_hash),
            widget,
            event,
            confirmed,
            value,
        )

    case("tap_switch", "ok", payload(1, switch["id"], "t"), widget_rect=switch["r"])
    case(
        "change_slider",
        "ok",
        payload(2, slider["id"], "c", value=42),
        widget_rect=slider["r"],
    )
    case("change_fraction", "ok", payload(3, slider["id"], "c", value=42.5))
    case(
        "confirmed_lock",
        "ok",
        payload(4, locker["id"], "t", confirmed=True),
        widget_rect=locker["r"],
    )
    good = payload(5, switch["id"], "t")
    case("bad_signature", "bad_signature", good, "0" * 32)
    case("signature_of_other_payload", "bad_signature", good, tp.sign(SECRET, good + "x"))
    case("signed_with_other_secret", "bad_signature", good, tp.sign(bytes(32), good))
    case("unsigned", "malformed", good, data={"s": None})
    case("replay_same_counter", "replay", payload(4, switch["id"], "t"))
    case("replay_old_counter", "replay", payload(1, switch["id"], "t"))
    case("old_session", "stale_session", payload(9, switch["id"], "t", nonce="f" * 32))
    case("other_tablet", "wrong_tablet", payload(9, switch["id"], "t", mac="112233445566"))
    case("other_layout", "stale_layout", payload(9, switch["id"], "t", layout="0" * 16))
    case("wrong_field_count", "malformed", good + "|1")
    case("tap_with_value", "malformed", payload(10, switch["id"], "t", value=1))
    case("change_without_number", "malformed", payload(10, slider["id"], "c"))
    case("unknown_event", "malformed", payload(10, switch["id"], "x"))
    case("version_2", "version", "2" + good[1:])
    case("after_bad_ones_counter_goes_on", "ok", payload(10, switch["id"], "t"))
    case("signature_not_ascii", "malformed", good, "\u00e9" * 32)
    case("signature_upper_case", "malformed", good, tp.sign(SECRET, good).upper())
    case("signature_too_short", "malformed", good, tp.sign(SECRET, good)[:31])
    case("payload_not_ascii", "malformed", good.replace("|t|", "|\u00e9|"))
    case(
        "previous_layout_until_the_switch",
        "ok",
        payload(11, switch["id"], "t", layout="1" * 16),
        kept=[layout_hash, "1" * 16],
        note=(
            "While a new layout is being built the old one is still on screen. "
            "HA keeps the old bindings until tab_status confirms the switch."
        ),
    )
    write(
        "input_events.json",
        {
            "note": (
                "Feed the cases in order to one tablet session. last_counter "
                "starts at 0 and moves to the event's counter on 'ok' and on "
                "'stale_layout'. The hashes HA keeps bindings for are 'kept' of "
                "the case, or just 'hash'. 'ok' cases with widget_rect are also what the "
                "tablet must produce when that rectangle is pressed with the "
                "same secret, nonce and counter."
            ),
            "mac": MAC,
            "secret_hex": SECRET.hex(),
            "nonce": NONCE,
            "layout": "layout_all_cards",
            "hash": layout_hash,
            "cases": cases,
        },
    )


def pairing() -> None:
    nonce = "00112233445566778899aabbccddeeff"
    wrapped = tp.wrap_secret(PSK, MAC, nonce, SECRET)
    assert tp.unwrap_secret(PSK, MAC, nonce, wrapped) == SECRET
    write(
        "pair.json",
        {
            "mac": MAC,
            "psk_hex": PSK.hex(),
            "psk_base64": __import__("base64").b64encode(PSK).decode(),
            "secret_hex": SECRET.hex(),
            "cases": [
                {
                    "name": "good",
                    "call": {"nonce": nonce, "wrapped": wrapped, "kid": tp.kid(SECRET)},
                    "expect": "ok",
                    "stored_secret_hex": SECRET.hex(),
                },
                {
                    "name": "wrong_psk_on_tablet",
                    "note": "The tablet unwraps with another key; the kid does not match.",
                    "tablet_psk_hex": bytes(32).hex(),
                    "call": {"nonce": nonce, "wrapped": wrapped, "kid": tp.kid(SECRET)},
                    "expect": "bad_key",
                },
                {
                    "name": "no_encryption",
                    "note": "The tablet has no API encryption key.",
                    "tablet_psk_hex": None,
                    "call": {"nonce": nonce, "wrapped": wrapped, "kid": tp.kid(SECRET)},
                    "expect": "needs_encryption",
                },
                {
                    "name": "bad_shape",
                    "call": {"nonce": nonce, "wrapped": "abc", "kid": tp.kid(SECRET)},
                    "expect": "bad_key",
                },
            ],
        },
    )


def hello(small: dict) -> None:
    base = {
        "proto": [1, 1],
        "engine": "0.1.0",
        "boot": 3,
        "layout": small["compiled"]["hash"],
        "kid": tp.kid(SECRET),
        "enc": 1,
        "caps": {
            "w": list(tp.WIDGET_KINDS),
            "icons": 1,
            "screen": [1280, 800],
            "max_layout": tp.MAX_LAYOUT_BYTES,
            "max_chunk": tp.CHUNK_BYTES,
            "max_slots": 1024,
            "max_widgets": 2048,
        },
        "mem": {"int": 61000, "psram": 28000000, "block": 16000000},
        "session": 1,
    }
    want = small["compiled"]["hash"]
    nochart_caps = {**base["caps"], "w": [k for k in tp.WIDGET_KINDS if k != "chart"]}
    cases = hello_cases(base, want, nochart_caps)
    for case in cases:
        got = tp.hello_steps(
            case["response"], stored_kid=case["stored_kid"], want_hash=case["want_hash"] or "x"
        )
        assert got["steps"] == case["expect"], (case["name"], got)
        assert got["status"] == case.get("status", ""), (case["name"], got)
        assert got["reason"] == case.get("reason", ""), (case["name"], got)
    write(
        "hello.json",
        {
            "note": (
                "'expect' is what HA does next, in order. 'hello' means: call "
                "tab_hello again, because pairing ends the session. The tablet "
                "side: with the fixture secret stored, tab_hello(call.nonce, "
                "call.auth) must answer session 1, and any other auth session 0."
            ),
            "mac": MAC,
            "secret_hex": SECRET.hex(),
            "call": {
                "nonce": NONCE,
                "auth": tp.call_auth(SECRET, MAC, NONCE, 0, "tab_hello"),
            },
            "cases": cases,
        },
    )


def hello_cases(base: dict, want: str, nochart_caps: dict) -> list:
    small = {"compiled": {"hash": want}}
    return [
        *_hello_cases(base, small),
        {
            "name": "paired_with_another_home_assistant",
            "note": "The tablet holds a secret HA does not know. It refuses the session.",
            "response": {**base, "kid": "0123456789abcdef", "session": 0},
            "want_hash": want,
            "stored_kid": tp.kid(SECRET),
            "expect": ["pair", "hello", "send_state"],
        },
        {
            "name": "same_kid_refused_signature",
            "note": (
                "The tablet reports the kid HA stored but refused the signature "
                "(session 0): the two secrets differ, so HA pairs again."
            ),
            "response": {**base, "session": 0},
            "want_hash": want,
            "stored_kid": tp.kid(SECRET),
            "expect": ["pair", "hello", "send_state"],
        },
        {
            "name": "older_tablet_protocol",
            "response": {**base, "proto": [0, 0]},
            "want_hash": want,
            "stored_kid": None,
            "expect": [],
            "status": "unsupported",
            "reason": "tablet_old",
        },
    ]


def _hello_cases(base: dict, small: dict) -> list:
    return (
        (
            [
                {
                    "name": "up_to_date",
                    "response": base,
                    "want_hash": small["compiled"]["hash"],
                    "stored_kid": tp.kid(SECRET),
                    "expect": ["send_state"],
                },
                {
                    "name": "other_layout",
                    "response": {**base, "layout": "0" * 16},
                    "want_hash": small["compiled"]["hash"],
                    "stored_kid": tp.kid(SECRET),
                    "expect": ["send_layout", "send_state"],
                },
                {
                    "name": "empty_tablet",
                    "response": {**base, "layout": "", "kid": ""},
                    "want_hash": small["compiled"]["hash"],
                    "stored_kid": None,
                    "expect": ["pair", "hello", "send_layout", "send_state"],
                },
                {
                    "name": "tablet_was_reset",
                    "response": {**base, "kid": ""},
                    "want_hash": small["compiled"]["hash"],
                    "stored_kid": tp.kid(SECRET),
                    "expect": ["pair", "hello", "send_state"],
                },
                {
                    "name": "no_encryption",
                    "response": {**base, "enc": 0, "kid": ""},
                    "want_hash": small["compiled"]["hash"],
                    "stored_kid": None,
                    "expect": ["send_state"],
                    "reason": "needs_encryption",
                },
                {
                    "name": "newer_tablet_protocol",
                    "response": {**base, "proto": [3, 4]},
                    "want_hash": small["compiled"]["hash"],
                    "stored_kid": None,
                    "expect": [],
                    "status": "unsupported",
                    "reason": "tablet_new",
                },
                {
                    "name": "tablet_without_charts",
                    "note": "Down-levelling: chart widgets are left out and the hash differs.",
                    "response": {
                        **base,
                        "caps": {
                            **base["caps"],
                            "w": [k for k in tp.WIDGET_KINDS if k != "chart"],
                        },
                    },
                    "want_hash": None,
                    "stored_kid": tp.kid(SECRET),
                    "expect": ["send_layout", "send_state"],
                },
            ]
        )
    )


def status(small: dict, big: dict) -> None:
    old = small["compiled"]["hash"]
    new = big["compiled"]["hash"]
    mem = {"int": 60000, "psram": 27000000, "block": 16000000}
    cases = [
        ("still_building", {"layout": old, "staged": new, "build": ""}, "building"),
        ("shown", {"layout": new, "staged": "", "build": ""}, "shown"),
        ("build_ran_out_of_memory", {"layout": old, "staged": "", "build": "memory"}, "memory"),
        ("build_failed", {"layout": old, "staged": "", "build": "build"}, "build"),
        ("replaced_by_another_transfer", {"layout": old, "staged": "", "build": ""}, "replaced"),
        ("first_layout_still_building", {"layout": "", "staged": new, "build": ""}, "building"),
    ]
    out = []
    for name, response, verdict in cases:
        response = {**response, "mem": mem, "session": 1}
        assert tp.status_verdict(response, new) == verdict, name
        out.append({"name": name, "response": response, "expect": verdict})
    live = {"layout": new, "staged": "", "build": "", "mem": mem, "session": 1}
    knock = [
        {
            "name": "no_session",
            "note": "Nobody greeted the tablet on this connection.",
            "session": False,
            "status": None,
            "expect": "hello",
        },
        {
            "name": "session_read_status_first",
            "note": "A knock never resets a session by itself, whatever its boot number.",
            "session": True,
            "status": None,
            "expect": "status",
        },
        {
            "name": "session_live_spoofed_knock",
            "note": "Any ESPHome device can knock with the tablet's MAC. The tablet still has its session.",
            "session": True,
            "status": live,
            "expect": "ignore",
        },
        {
            "name": "session_lost_on_unseen_reconnect",
            "note": "The tablet lost its session on a reconnect HA did not see.",
            "session": True,
            "status": {**live, "session": 0},
            "expect": "hello",
        },
    ]
    for case in knock:
        got = tp.knock_step(session=case["session"], status=case["status"])
        assert got == case["expect"], case["name"]
    write(
        "status.json",
        {
            "note": (
                "tab_status responses after tab_commit(want_hash) and what HA "
                "concludes. 'building': ask again. 'shown': on the tablet. "
                "Anything else: the build ended without showing the layout. "
                "'knock': what HA does with a knock that passed the 2 s limit "
                "(knock_step in the reference code): 'session' is whether HA "
                "has a session with the tablet on the current connection, "
                "'status' the tab_status answer HA read for it, if any."
            ),
            "want_hash": new,
            "cases": out,
            "knock": knock,
        },
    )


def auth() -> None:
    other = bytes(range(32))
    layout_hash = "a9326c033e45f2f4"
    set_data = '{"h":"a9326c033e45f2f4","v":[[1,"Küche"]]}'

    def call(name, n, action, body, expect, *, auth=None, secret=SECRET, **extra):
        value = tp.call_auth(secret, MAC, NONCE, n, action, body) if auth is None else auth
        return {"name": name, "action": action, "body": body, "auth": value, "expect": expect, **extra}

    good_set = tp.call_auth(SECRET, MAC, NONCE, 2, "tab_set", set_data)
    paired = [
        call("commit", 1, "tab_commit", layout_hash, "ok"),
        call("set", 2, "tab_set", set_data, "ok"),
        call("same_call_again", 2, "tab_set", set_data, "auth", note="n must go up."),
        call("signature_for_other_body", 3, "tab_set", set_data, "auth",
             auth=tp.call_auth(SECRET, MAC, NONCE, 3, "tab_set", set_data + " ")),
        call("signature_for_other_action", 3, "tab_clear", "", "auth",
             auth=tp.call_auth(SECRET, MAC, NONCE, 3, "tab_commit", "")),
        call("other_secret", 3, "tab_set", set_data, "auth", secret=other),
        call("other_session", 3, "tab_set", set_data, "auth",
             auth=tp.call_auth(SECRET, MAC, "f" * 32, 3, "tab_set", set_data)),
        call("empty", 3, "tab_clear", "", "auth", auth=""),
        call("not_ascii", 3, "tab_clear", "", "auth", auth="3." + "\u00e9" * 32),
        call("no_counter", 3, "tab_clear", "", "auth", auth=good_set.partition(".")[2]),
        call("ack", 3, "tab_ack", tp.ack_body(7, True, ""), "ok",
             note="tab_ack(7, true, ''). A refused tab_ack is ignored without an answer."),
        call("gap_in_counter_is_fine", 9, "tab_set", set_data, "ok"),
        call("counter_below_last", 8, "tab_set", set_data, "auth"),
        call("clear", 10, "tab_clear", "", "ok"),
    ]
    last = 0
    for item in paired:
        ok, last = tp.check_auth(
            item["auth"], secret=SECRET, mac=MAC, nonce=NONCE, last_n=last,
            action=item["action"], body=item["body"],
        )
        assert ("ok" if ok else "auth") == item["expect"], item["name"]
    write(
        "auth.json",
        {
            "note": (
                "Signed calls from HA. 'paired': feed the cases in order to a "
                "tablet that holds secret_hex and whose session nonce is "
                "'nonce'; last n starts at 0. 'body' is the signed text of the "
                "call (see CONTRACT.md 6.2). 'expect' auth means the call "
                "answers the error 'auth' and changes nothing. 'unpaired': a "
                "tablet without a secret accepts every auth value."
            ),
            "mac": MAC,
            "secret_hex": SECRET.hex(),
            "nonce": NONCE,
            "hello": {
                "nonce": NONCE,
                "auth": tp.call_auth(SECRET, MAC, NONCE, 0, "tab_hello"),
                "expect_session": 1,
                "bad_auth": tp.call_auth(other, MAC, NONCE, 0, "tab_hello"),
                "bad_expect_session": 0,
                "repeat_expect_session": 0,
                "repeat_note": (
                    "The same nonce again on the same boot, with the same valid "
                    "auth: session 0. A nonce starts at most one session per boot."
                ),
            },
            "paired": paired,
            "unpaired": [
                {"name": "empty_auth", "action": "tab_commit", "body": layout_hash, "auth": "", "expect": "ok"},
                {"name": "any_auth", "action": "tab_clear", "body": "", "auth": "1.zz", "expect": "ok"},
            ],
            "no_api_key": {
                "note": (
                    "A tablet that holds secret_hex but has no API encryption key "
                    "ignores the secret and behaves as not paired: tab_hello "
                    "answers enc 0, kid empty and starts a session with any auth, "
                    "signed calls accept any auth, and the tablet sends no input."
                ),
                "hello": {"nonce": NONCE, "auth": "", "expect_session": 1, "expect_kid": "", "expect_enc": 0},
                "calls": [
                    {"name": "commit_without_auth", "action": "tab_commit", "body": layout_hash, "auth": "", "expect": "ok"},
                    {"name": "clear_without_auth", "action": "tab_clear", "body": "", "auth": "", "expect": "ok"},
                ],
            },
        },
    )


def downlevel(built: dict) -> None:
    layout = built["result"]["layout"]
    caps = {"w": [k for k in tp.WIDGET_KINDS if k != "chart"]}
    compiled = tp.compile_device_layout(layout, ICONS, caps)
    (FIX / "layout_all_cards.nochart.dl.json").write_bytes(compiled["bytes"])
    write(
        "layout_all_cards.nochart.meta.json",
        {
            "caps": caps,
            "hash": compiled["hash"],
            "size": compiled["size"],
            "slots": compiled["slots"],
            "dropped": compiled["dropped"],
        },
    )


def contract_json() -> None:
    text = json.dumps(tp.contract_document(), indent=1) + "\n"
    (OUT / "contract.json").write_text(text, encoding="utf-8")


# ------------------------------------------------------------- version 2
#
# Everything below uses tabproto.py and the standard library only: the kit is
# a layout v2 written out here, not made from card files.

MIDNIGHT = {
    "dark": True, "wall": "#101418", "card": "#181C23", "card_pr": "#232833",
    "card2": "#232833", "card2_pr": "#303746", "line": "#2A303A", "tx": "#E8EAED",
    "tx2": "#9AA0A8", "acc": "#F5B547", "accf": "#F5B547", "accf_pr": "#D99A2B",
    "acct": "#0E1116", "acc2": "#6CB4FF", "onbg": "#33291A", "onbg_pr": "#4A3A20",
    "ontx": "#F7E3BC", "ion": "#F5B547", "r": 16, "r2": 10, "bw": 0,
}  # fmt: skip
DAYLIGHT = {
    "dark": False, "wall": "#EEF0F3", "card": "#FFFFFF", "card_pr": "#E9ECF0",
    "card2": "#E2E6EC", "card2_pr": "#D2D7DE", "line": "#DDE1E6", "tx": "#15181D",
    "tx2": "#5D6570", "acc": "#B86E00", "accf": "#9C5C00", "accf_pr": "#7E4A00",
    "acct": "#FFFFFF", "acc2": "#1F6FD1", "onbg": "#FFF1D6", "onbg_pr": "#F2DFB8",
    "ontx": "#5A3600", "ion": "#B86E00", "r": 16, "r2": 10, "bw": 0,
}  # fmt: skip
STATUS_DARK = {"good": "#4CC38A", "warn": "#F5B547", "bad": "#FF6B5E", "info": "#6CB4FF"}
STATUS_LIGHT = {"good": "#1E8E5A", "warn": "#B86E00", "bad": "#C6392C", "info": "#1F6FD1"}
HUES = ["#FF0000", "#FFFF00", "#00FF00", "#00FFFF", "#0000FF", "#FF00FF", "#FF0000"]
WHITES = ["#FF8912", "#FFF9FD", "#CFE0FF"]

ENGINE_CAPS = tp.ENGINE_CAPS
NOCHOICE_CAPS = {**tp.ENGINE_CAPS, "w": [k for k in tp.ENGINE_CAPS["w"] if k != "choice"]}

OPTIMISTIC = {"policy": "optimistic"}
PULSE = {"policy": "pulse"}
PROGRESS = {"policy": "progress"}
CONFIRM = {"policy": "confirm"}


def go(page: str) -> dict:
    return {"local": "go_to_page", "page": page}


BACK = {"local": "back"}


def s(n: int, roles: dict | None = None) -> dict:
    """A source slot reference of a layout v2."""
    return {"s": n, "roles": roles} if roles else {"s": n}


# Source slots of the kit and what Home Assistant finds for each.
KIT_VALUES = {
    1: "Living room",
    2: "on",
    3: [255, 167, 87],
    4: "mdi:lightbulb-on",
    5: "On",
    6: "80%",
    7: 80,
    8: "off",
    9: 30,
    10: 2700,
    11: 60,
    12: 30,
    13: 1,
    14: 1,
    15: 0,
    16: "off",
    17: "mdi:fan-off",
    18: "#FF453A",
    19: "on",
    20: "good",
    21: "on",
    22: 20.8,
    23: 21.5,
    24: [19.2, 19.4, 20.1, 20.9, 21.3, 21.1],
    25: 4,
    26: [3, 5, 2, 6, 4, 1, 0],
    27: 615,
    28: "on",
    29: "off",
    31: 40,
    32: "on",
    33: "on",
    35: "off",
    36: 0,
    37: 100,
    38: 2000,
    39: 6535,
}


def kit_source() -> dict:
    """layout_v2_kit: every key and kind of version 2 at least once."""
    tile = {
        "header": {"r": None, "icon": "mdi:lightbulb", "title": s(1)},
        "on": s(2),
        "tap": OPTIMISTIC,
        "hold": go("light"),
        "tint": s(3),
        "ic": s(4),
    }

    def light_tile(card_id: int, x: int, lit: int, extra: dict) -> dict:
        return {
            **tile,
            **extra,
            "id": card_id,
            "t": "card",
            "r": [x, 84, 376, 248],
            "header": {**tile["header"], "r": [x + 16, 100, 344, 32]},
            "lit": lit,
            "w": [
                {"id": card_id + 1, "t": "image", "r": [x + 16, 140, 64, 64], "value": s(4), "look": 1},
                {"id": card_id + 2, "t": "label", "r": [x + 88, 140, 272, 28], "text": s(5), "size": "s", "al": 2},
                {"id": card_id + 3, "t": "label", "r": [x + 88, 172, 272, 36], "text": s(6), "px": 28},
                {
                    "id": card_id + 4, "t": "slider", "r": [x + 16, 268, 344, 48], "look": 1,
                    "value": s(7), "min": 0, "max": 100, "step": 1, "change": OPTIMISTIC,
                    "c": s(3), "icon": "mdi:brightness-6",
                },
            ],
        }  # fmt: skip

    kit_page = {
        "id": "kit",
        "title": "Kit",
        "w": [
            {"id": 1, "t": "heading", "r": [100, 20, 568, 56], "text": "Kit", "icon": "mdi:home", "c": "#4CC38A"},
            light_tile(2, 100, 0, {}),
            light_tile(7, 484, 2, {
                "un": s(8),
                "style": {
                    "card_pr": "#2A2F3A", "card2_pr": "#353C4B", "accf": "#FFC266",
                    "accf_pr": "#E0A040", "onbg_pr": "#4E3E22", "ion": "#FFC266",
                },
            }),
            {
                "id": 12, "t": "card", "r": [868, 84, 376, 400],
                "header": {"r": [884, 100, 344, 32], "icon": "mdi:palette", "title": "Sliders"},
                "w": [
                    {"id": 13, "t": "slider", "r": [884, 140, 344, 40], "value": s(9), "min": 0,
                     "max": 360, "step": 1, "change": OPTIMISTIC, "track": HUES, "nv": 1},
                    {"id": 14, "t": "slider", "r": [884, 188, 344, 40], "look": 1, "value": s(10),
                     "min": 2000, "max": 6500, "step": s(37), "change": OPTIMISTIC, "track": WHITES},
                    {"id": 15, "t": "slider", "r": [884, 236, 80, 200], "look": 1, "dir": 1,
                     "value": s(7), "min": 0, "max": 100, "step": 1, "change": OPTIMISTIC},
                    {"id": 16, "t": "slider", "r": [972, 236, 80, 200], "look": 1, "dir": 2,
                     "value": s(11), "min": 0, "max": 100, "step": 1},
                    {"id": 17, "t": "slider", "r": [884, 452, 344, 8], "look": 1, "value": s(12),
                     "min": 0, "max": 300, "step": 1, "rate": s(13)},
                ],
            },
            {
                "id": 18, "t": "card", "r": [100, 340, 568, 296],
                "header": {"r": [116, 356, 536, 32], "icon": "mdi:palette-outline", "title": "Choices"},
                "w": [
                    {"id": 19, "t": "choice", "r": [116, 396, 536, 48],
                     "texts": ["Off", "Low", "Medium", "High"], "value": s(14), "change": OPTIMISTIC},
                    {"id": 20, "t": "choice", "r": [116, 452, 536, 104], "rows": 2,
                     "icons": ["mdi:weather-sunny", "mdi:weather-night", "", "mdi:fan", "mdi:snowflake", "mdi:fire"],
                     "texts": ["Day", "Night", "Auto", "Fan", "Cool", "Heat"],
                     "value": s(15), "change": PROGRESS},
                    {"id": 21, "t": "choice", "r": [116, 564, 536, 56], "look": 1,
                     "cols": ["#FF453A", "#FF9F0A", "#FFD60A", "#30D158", "#0A84FF"],
                     "change": PULSE, "confirm": "Change the colour?"},
                ],
            },
            {
                "id": 22, "t": "card", "r": [676, 492, 568, 192],
                "header": {"r": [692, 508, 536, 32], "icon": "mdi:gesture-tap-button", "title": "Buttons"},
                "w": [
                    {"id": 23, "t": "button", "r": [692, 548, 128, 48], "text": "Party", "value": s(16), "tap": OPTIMISTIC},
                    {"id": 24, "t": "button", "r": [828, 548, 128, 48], "text": "Fan", "icon": "mdi:fan", "ic": s(17), "tap": PULSE},
                    {"id": 25, "t": "button", "r": [964, 548, 128, 48], "c": s(18), "value": s(19), "tap": OPTIMISTIC},
                    {"id": 26, "t": "button", "r": [1100, 548, 112, 112], "icon": "mdi:power", "shape": 1, "isz": 1, "tap": OPTIMISTIC},
                    {"id": 27, "t": "button", "r": [692, 604, 128, 48], "icon": "mdi:dots-horizontal", "shape": 2, "tap": PULSE},
                    {"id": 28, "t": "switch", "r": [828, 604, 128, 48], "value": s(21), "c": s(20, STATUS_DARK), "tap": OPTIMISTIC},
                    {"id": 29, "t": "image", "r": [964, 604, 64, 64], "value": "mdi:cog", "hold": go("more")},
                ],
            },
        ],
    }  # fmt: skip
    climate_page = {
        "id": "climate",
        "title": "Climate",
        "theme": DAYLIGHT,
        "w": [
            {"id": 30, "t": "heading", "r": [100, 20, 568, 56], "text": "Climate"},
            {
                "id": 31, "t": "card", "r": [100, 84, 280, 300],
                "header": {"r": [116, 100, 248, 32], "icon": "mdi:thermostat", "title": "Heating"},
                "w": [
                    {"id": 32, "t": "thermostat", "r": [116, 140, 248, 228], "value": s(23), "min": 7,
                     "max": 35, "step": 0.5, "change": OPTIMISTIC, "c": "#FF6B5E", "mark": s(22), "bs": 56},
                ],
            },
            {
                "id": 33, "t": "card", "r": [388, 84, 376, 300],
                "header": {"r": [404, 100, 344, 32], "icon": "mdi:chart-line", "title": "Charts"},
                "w": [
                    {"id": 34, "t": "chart", "r": [404, 140, 344, 104], "value": s(24), "kind": "line", "st": 1, "c": "#1F6FD1"},
                    {"id": 35, "t": "chart", "r": [404, 252, 344, 116], "value": s(26), "kind": "bars", "mark": s(25)},
                ],
            },
            {
                "id": 36, "t": "card", "r": [772, 84, 488, 300],
                "w": [{"id": 37, "t": "label", "r": [788, 114, 456, 240], "text": "21:05", "px": 192}],
            },
            {
                "id": 38, "t": "card", "r": [100, 392, 280, 208],
                "w": [
                    {"id": 39, "t": "label", "r": [116, 408, 248, 120], "clk": 1, "px": 96, "value": s(27)},
                    {"id": 40, "t": "label", "r": [116, 536, 248, 60], "clk": 2, "px": 48, "value": s(27)},
                ],
            },
            {
                "id": 41, "t": "card", "r": [388, 392, 184, 184], "tap": PULSE, "on": s(33), "lit": 1,
                "header": {"r": [404, 408, 152, 32], "icon": "mdi:water", "title": "Fountain"},
                "w": [
                    {"id": 42, "t": "label", "r": [404, 448, 152, 28], "text": "Pulse", "size": "s"},
                    {"id": 43, "t": "image", "r": [404, 496, 64, 64], "value": "mdi:water-pump", "look": 2,
                     "c": "#1F6FD1", "tap": go("more")},
                ],
            },
            {
                "id": 44, "t": "card", "r": [580, 392, 184, 184], "tap": CONFIRM, "on": s(33), "lit": 3,
                "confirm": "Turn the pump off?",
                "header": {"r": [596, 408, 152, 32], "icon": "mdi:power-plug", "title": "Pump"},
                "w": [{"id": 45, "t": "label", "r": [596, 448, 152, 28], "text": "Asks first", "size": "s"}],
            },
            {
                "id": 46, "t": "card", "r": [772, 392, 488, 268], "tap": OPTIMISTIC, "on": s(35),
                "hold": go("more"),
                "header": {"r": [788, 408, 456, 32], "icon": "mdi:gesture-tap-button", "title": "Routing"},
                "w": [
                    {"id": 47, "t": "thermostat", "r": [788, 448, 200, 196], "value": s(23), "min": 7,
                     "max": 35, "step": 0.5, "change": OPTIMISTIC},
                    {"id": 48, "t": "button", "r": [1004, 448, 240, 48], "text": "Arm", "vis": s(28), "tap": OPTIMISTIC},
                    {"id": 49, "t": "button", "r": [1004, 448, 240, 48], "text": "Disarm", "vis": s(29), "tap": OPTIMISTIC},
                    {"id": 50, "t": "label", "r": [1004, 504, 240, 28], "text": "Status", "c": s(20, STATUS_LIGHT)},
                    {"id": 51, "t": "label", "r": [1004, 540, 240, 28], "text": "Centre", "al": 1},
                    {"id": 52, "t": "slider", "r": [1004, 576, 240, 24], "look": 1, "value": s(31),
                     "min": 0, "max": 100, "step": 1},
                    {"id": 53, "t": "switch", "r": [1004, 608, 240, 40], "value": s(32), "tap": OPTIMISTIC},
                ],
            },
        ],
    }  # fmt: skip
    old_page = {
        "id": "old",
        "title": "Old",
        "w": [
            {"id": 54, "t": "heading", "r": [100, 20, 376, 56], "text": "Kitchen"},
            {
                "id": 55, "t": "card", "r": [100, 84, 184, 184], "on": s(2),
                "header": {"icon": "mdi:lightbulb", "r": [116, 100, 152, 32], "title": s(1)},
                "w": [
                    {"id": 56, "t": "switch", "r": [116, 176, 152, 40], "tap": OPTIMISTIC, "value": s(2)},
                    {"id": 57, "t": "label", "r": [116, 224, 152, 28], "size": "m", "text": s(6)},
                ],
            },
        ],
    }  # fmt: skip
    light_page = {
        "id": "light",
        "title": "Living room",
        "sub": 1,
        "ttl": 60,
        "w": [
            {"id": 58, "t": "heading", "r": [100, 20, 568, 56], "text": "Living room"},
            {
                "id": 59, "t": "card", "r": [100, 84, 568, 400],
                "header": {"r": [116, 100, 536, 32], "icon": "mdi:lightbulb", "title": s(1)},
                "w": [
                    {"id": 60, "t": "button", "r": [116, 140, 128, 48], "icon": "mdi:arrow-left", "text": "Back", "tap": BACK},
                    {"id": 61, "t": "choice", "r": [116, 196, 536, 104], "rows": 2,
                     "texts": ["None", "Rainbow", "Candle", "Party", "Fire", "Ocean"],
                     "value": s(36), "change": OPTIMISTIC},
                    {"id": 62, "t": "slider", "r": [116, 308, 536, 48], "look": 1, "value": s(7),
                     "min": 0, "max": 100, "step": 1, "change": OPTIMISTIC},
                    {"id": 63, "t": "slider", "r": [116, 364, 536, 48], "value": s(9), "min": 0,
                     "max": 360, "step": 0, "change": OPTIMISTIC, "track": HUES},
                    {"id": 64, "t": "slider", "r": [116, 420, 536, 48], "look": 1, "value": s(10),
                     "min": s(38), "max": s(39), "step": 100, "change": OPTIMISTIC, "track": WHITES},
                ],
            },
        ],
    }  # fmt: skip
    more_page = {
        "id": "more",
        "title": "More",
        "sub": 1,
        "ttl": 0,
        "w": [
            {"id": 65, "t": "heading", "r": [100, 20, 568, 56], "text": "More"},
            {
                "id": 66, "t": "card", "r": [100, 84, 376, 184],
                "header": {"r": [116, 100, 344, 32], "icon": "mdi:cog", "title": "Settings"},
                "w": [{"id": 67, "t": "label", "r": [116, 140, 344, 28], "text": "Opened by a hold"}],
            },
        ],
    }  # fmt: skip
    return {
        "v": 2,
        "screen": [1280, 800],
        "theme": MIDNIGHT,
        "nav": [
            {"page": "kit", "title": "Kit", "icon": "mdi:view-dashboard"},
            {"page": "climate", "title": "Climate", "icon": "mdi:thermostat"},
            {"page": "old", "title": "Old", "icon": "mdi:home"},
            {"page": "light", "title": "Living room", "icon": "mdi:lightbulb"},
        ],
        "pages": [kit_page, climate_page, old_page, light_page, more_page],
    }


def kit() -> dict:
    """Write layout_v2_kit.* and layout_v2_kit.nochoice.*."""
    source = kit_source()
    compiled = tp.compile_device_layout_v2(source, ICONS, ENGINE_CAPS)
    nochoice = tp.compile_device_layout_v2(source, ICONS, NOCHOICE_CAPS)
    assert not compiled["dropped"], compiled["dropped"]
    assert nochoice["dropped"] == [19, 20, 21, 61], nochoice["dropped"]
    write(
        "layout_v2_kit.source.json",
        {
            "note": (
                "A layout v2 written by hand in reference/gen_fixtures.py, with "
                "every key and kind of version 2 at least once. 'values' are "
                "what Home Assistant finds for each source slot."
            ),
            "layout": source,
            "values": {str(k): v for k, v in sorted(KIT_VALUES.items())},
        },
    )
    for name, built, caps in (
        ("layout_v2_kit", compiled, ENGINE_CAPS),
        ("layout_v2_kit.nochoice", nochoice, NOCHOICE_CAPS),
    ):
        (FIX / f"{name}.dl.json").write_bytes(built["bytes"])
        write(
            f"{name}.meta.json",
            {
                "caps": caps,
                "hash": built["hash"],
                "size": built["size"],
                "slots": built["slots"],
                "dropped": built["dropped"],
                "counts": built["counts"],
            },
        )
    return {"source": source, "compiled": compiled, "nochoice": nochoice}


def write_rows(name: str, obj) -> None:
    """Write a fixture with indent 1, but every list of plain values on one line."""

    def plain(value) -> bool:
        return not isinstance(value, (dict, list))

    def dump(value, depth: int) -> str:
        pad = " " * depth
        if isinstance(value, dict):
            if not value:
                return "{}"
            parts = [
                f"{pad} {json.dumps(key, ensure_ascii=False)}: {dump(value[key], depth + 1)}"
                for key in sorted(value)
            ]
            return "{\n" + ",\n".join(parts) + "\n" + pad + "}"
        if isinstance(value, list):
            if all(plain(item) for item in value):
                return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            parts = [f"{pad} {dump(item, depth + 1)}" for item in value]
            return "[\n" + ",\n".join(parts) + "\n" + pad + "]"
        return json.dumps(value, ensure_ascii=False)

    (FIX / name).write_text(dump(obj, 0) + "\n", encoding="utf-8")


def theme_ints(theme: dict) -> dict:
    """A theme entry in device form."""
    out = {key: tp.colour(theme[key]) for key in tp.THEME_COLOURS}
    out.update({key: theme[key] for key in tp.RADII})
    out["dark"] = 1 if theme["dark"] else 0
    return out


MIX_WEIGHTS = (50, 78, 80, 84, 85, 88, 90)
SAMPLE_COLOURS = (
    0x000000, 0xFFFFFF, 0x15181D, 0xFF0000, 0x00FF00, 0x0000FF, 0xFFA757, 0xFF8912,
    0x000080, 0x808080, 0x181C23, 0xFFFFFF, 0x33291A, 0xF5B547, 0x4CC38A, 0x1E8E5A,
    0xE8EAED, 0x9AA0A8, 0x5D6570, 0xFFF1D6, 0x7F7F7F, 0x010203,
)  # fmt: skip
TINTS = (None, 0xFF0000, 0xFFA757, 0x000080, 0xFFFFFF, 0x000000)
# Colours whose contrast on one of the legible backgrounds is the nearest
# above 3 and the nearest below 3 of all colours (no colour gives exactly 3).
LEGIBLE_EDGES = (
    0xB62595, 0x406F67, 0xE969A1, 0x989A30, 0xE5053C, 0xCA2F9F, 0xA68A16, 0xFF27BC, 0xFEFFFE,
)  # fmt: skip
# The nearest colours to a tie of readable(), one on each side. No colour
# ties exactly.
READABLE_EDGES = (0x068E4B, 0xD334BB)


def blend_fused_differs(a: int, b: int, t: float) -> bool:
    """Whether a fused multiply-add can give another channel than blend."""
    from fractions import Fraction

    def fma(x, y, z):
        return float(Fraction(x) * Fraction(y) + Fraction(z))

    u = 1 - t
    plain = math.floor((a * u + b * t) + 0.5)
    fused = {
        math.floor(fma(a, u, b * t) + 0.5),
        math.floor(fma(b, t, a * u) + 0.5),
        math.floor(fma(b, t, a * u + 0.5)),
        math.floor(fma(a, u, b * t + 0.5)),
    }
    return fused != {plain}


def maths() -> None:
    """Write maths.json: the vectors of contract 4.7."""
    mix_cases = [
        [a, b, p, tp.mix(a, b, p)]
        for a in SAMPLE_COLOURS[:12]
        for b in SAMPLE_COLOURS[:12]
        for p in (0, 50, 78, 84, 88, 90, 100)
    ]
    halves = {}
    for p in MIX_WEIGHTS:
        rows = []
        for a in range(256):
            for b in range(256):
                if (a * (100 - p) + b * p) % 100 == 50:
                    rows.append([a, b, tp.mix(a, b, p)])
        halves[str(p)] = rows
    blend_t = 0.82
    blend_halves = [
        [a, b, tp.blend(a, b, blend_t)]
        for a in range(256)
        for b in range(256)
        if (a * 18 + b * 82) % 100 == 50
    ]
    blend_fma = [
        [a, b, tp.blend(a, b, blend_t)]
        for a in range(256)
        for b in range(256)
        if blend_fused_differs(a, b, blend_t)
    ]
    pairs = [(a, b) for a in SAMPLE_COLOURS for b in SAMPLE_COLOURS[::3]]
    pairs += [(c, b) for c in LEGIBLE_EDGES for b in (0x181C23, 0xFFFFFF, 0x33291A, 0xFFF1D6)]
    pairs += [(c, b) for c in READABLE_EDGES for b in (0xFFFFFF, 0x15181D)]
    themes = {"midnight": theme_ints(MIDNIGHT), "daylight": theme_ints(DAYLIGHT)}
    styles = {
        "none": {},
        "own_onbg": {"onbg": 0x1E3A5F, "acc": 0x6CB4FF},
        "own_onbg_dim_acc": {"onbg": 0x6CB4FF, "acc": 0x7FA8D8},
        "light_card": {"bg": 0xF4F4F4, "tx": 0x15181D, "tx2": 0x5D6570},
        "whole_theme": {
            "bg": 0xFFFFFF, "tx": 0x15181D, "tx2": 0x5D6570, "acc": 0xB86E00, "acc2": 0x1F6FD1,
            "acct": 0xFFFFFF, "card2": 0xE2E6EC, "line": 0xDDE1E6, "onbg": 0xFFF1D6, "ontx": 0x5A3600,
            "card_pr": 0xE9ECF0, "card2_pr": 0xD2D7DE, "accf": 0x9C5C00, "accf_pr": 0x7E4A00,
            "onbg_pr": 0xF2DFB8, "ion": 0xB86E00,
        },
    }  # fmt: skip
    cards = []
    for theme_name, theme in themes.items():
        for style_name, style in styles.items():
            tints = TINTS if style_name == "none" else (None, 0xFF0000)
            for tint in tints:
                tokens = tp.card_tokens(theme, style)
                for on in (0, 1):
                    for lit in (0, 1, 2, 3):
                        cards.append(
                            {
                                "theme": theme_name,
                                "style": style_name,
                                "tint": tint,
                                "on": on,
                                "lit": lit,
                                "tokens": {k: tokens[k] for k in ("ion", "onbg_pr", "bg")},
                                "expect": tp.card_colours(tokens, bool(on), lit, tint),
                            }
                        )
    images = []
    for theme_name in themes:
        tokens = tp.card_tokens(themes[theme_name], {})
        for tint in (None, 0xFF0000):
            for state, on, lit in (
                ("plain", 0, 0), ("filled", 1, 0), ("lit_icon", 1, 1),
                ("lit_outline", 1, 2), ("lit_none", 1, 3),
            ):  # fmt: skip
                card = tp.card_colours(tokens, bool(on), lit, tint)
                for c in (None, 0x4CC38A):
                    for look in (0, 1, 2):
                        for w, h in ((64, 64), (44, 44), (120, 80), (0, 40), (1, 1)):
                            images.append(
                                {
                                    "theme": theme_name,
                                    "tint": tint,
                                    "state": state,
                                    "on": on,
                                    "lit": lit,
                                    "c": c,
                                    "look": look,
                                    "w": w,
                                    "h": h,
                                    "expect": tp.image_look(tokens, card, bool(on), lit, look, w, h, c),
                                }
                            )
    labels = [
        [None, "Hi", 0], [None, "Hi", 1], [None, "Hi", 2], [None, "21:05", 2],
        [10, "x", 1], [14, "x", 1], [15, "x", 1], [17, "x", 1], [27, "x", 1], [28, "x", 1],
        [33, "x", 1], [34, "x", 1], [40, "21:05", 1], [47, "21:05", 1], [48, "21:05", 1],
        [95, "21:05", 1], [96, "21:05", 1], [191, "21:05", 1], [192, "21:05", 1], [400, "21:05", 1],
        [96, "21°C", 1], [96, "21.5°", 1], [96, "+3%", 1], [96, "-12,5", 1], [192, "12 345", 1],
        [96, "", 1], [48, "−5", 1], [48, "10:15 am", 1], [192, "Küche", 1],
    ]  # fmt: skip
    label_cases = [
        {"px": px, "text": text, "size": size, "expect": tp.label_size(px, text, size)}
        for px, text, size in labels
    ]
    clocks = [
        [615, 0, 1], [615, 0, 2], [0, 0, 1], [0, 0, 2], [780, 0, 2], [779, 0, 2], [720, 0, 2],
        [1439, 0, 1], [1439, 60, 1], [1439.5, 30, 1], [615, 180, 1], [615, 179.999, 1],
        [12.75, 15, 1], [-1, 0, 1], [-1, 0, 2], [-0.5, 0, 1], [1e9, 0, 1], [-1e9, 0, 1],
        [0, 4320000, 1], [0, 4320059, 1], [0, 4320060, 1], [1440, 0, 1], [2880.25, 0, 2],
        [None, 0, 1], [None, 60, 2],
    ]  # fmt: skip
    clock_cases = [
        {"value": v, "age_s": age, "clk": form, "expect": tp.clock_text(v, age, form)}
        for v, age, form in clocks
    ]
    rects = {
        "wide": [0, 0, 200, 40],
        "tall": [0, 0, 40, 200],
        "zero": [0, 0, 0, 40],
        "zero_tall": [0, 0, 40, 0],
        "one": [0, 0, 1, 1],
        "short": [0, 0, 16, 40],
        "short_tall": [0, 0, 40, 16],
        "thin_8": [0, 0, 200, 8],
        "thin_9": [0, 0, 200, 9],
        "side_31": [0, 0, 200, 31],
        "side_32": [0, 0, 200, 32],
    }
    limits = {"percent": [0, 100, 1], "kelvin": [2000, 6500, 100], "free": [0, 360, 0], "equal": [5, 5, 1], "upside": [10, 0, 1]}
    sliders = []
    for look in (0, 1):
        for direction in (0, 1, 2):
            for track in (0, 2, 7, 8):
                for rect_name, rect in rects.items():
                    across = ("wide", "zero", "one", "short", "thin_8", "thin_9", "side_31", "side_32")
                    upright = ("tall", "zero_tall", "one", "short_tall")
                    if rect_name not in (across if direction == 0 else upright):
                        continue
                    length, _ = tp.slider_axis(rect, direction)
                    for limit_name, (low, high, step) in limits.items():
                        if rect_name not in ("wide", "tall") and limit_name not in ("percent", "equal"):
                            continue
                        presses = []
                        for along in sorted({-5, 0, 3, length // 4, length // 2, length - 3, length, length + 5}):
                            if direction == 0:
                                x, y = rect[0] + along, rect[1] + rect[3] // 2
                            elif direction == 1:
                                x, y = rect[0] + rect[2] // 2, rect[1] + rect[3] - along
                            else:
                                x, y = rect[0] + rect[2] // 2, rect[1] + along
                            amount = tp.slider_amount(rect, look, direction, track, 10, x, y)
                            run = tp.slider_length(rect, look, direction, track, 10)
                            presses.append([x, y, amount, tp.slider_value(amount, low, high, step, run)])
                        shapes = []
                        # 13.5, 14, 23.5 and 24 of 100 are fills of 27, 28, 47 and 48
                        # on a length of 200: the edges of the handle and the icon colour.
                        edges = (13.5, 14, 23.5, 24) if limit_name == "percent" and length == 200 else ()
                        for value in (None, low, (low + high) / 2, high, high + 1, *edges):
                            for change in (False, True):
                                if look == 0 and change:
                                    continue
                                shapes.append(
                                    {
                                        "value": value,
                                        "change": int(change),
                                        "expect": tp.slider_shape(
                                            rect, look, direction, track, 10, value, low, high, change
                                        ),
                                    }
                                )
                        sliders.append(
                            {
                                "look": look, "dir": direction, "track": track, "r2": 10,
                                "rect_name": rect_name, "rect": rect,
                                "min": low, "max": high, "step": step,
                                "presses": presses, "shapes": shapes,
                            }
                        )  # fmt: skip
    tracks = [
        {"n": n, "x0": x0, "x1": x1, "expect": tp.track_pieces(n, x0, x1)}
        for n in (1, 2, 3, 7, 8)
        for x0, x1 in ((7, 193), (10, 190), (10, 13), (10, 10), (10, 6), (7, 330))
    ]
    choices = []
    for n, rows, w, h, look in (
        (4, 1, 536, 48, 0), (6, 2, 536, 104, 0), (5, 1, 536, 56, 1), (16, 4, 536, 200, 0),
        (17, 1, 536, 48, 0), (3, 2, 300, 104, 1), (0, 1, 536, 48, 0), (4, 0, 536, 48, 0),
        (4, 5, 536, 200, 0), (4, 1, 32, 48, 0), (4, 1, 27, 48, 0), (4, 1, 28, 48, 0),
        (2, 2, 100, 9, 0), (2, 2, 100, 8, 0), (1, 1, 1, 1, 1), (3, 1, 0, 48, 0), (7, 3, 400, 150, 1),
    ):  # fmt: skip
        cells = tp.choice_cells(n, rows, w, h, look)
        points = [[0, 0], [w // 2, h // 2], [w - 1, h - 1], [w, h]]
        if cells:
            first = cells[0]
            points.append([first[2], first[3] // 2])
            points.append([first[2] + 7, first[3] // 2])
            points.append([first[2] + 8, first[3] // 2])
        choices.append(
            {
                "n": n, "rows": rows, "w": w, "h": h, "look": look, "cells": cells,
                "presses": [[x, y, tp.choice_at(cells, x, y)] for x, y in points],
            }
        )  # fmt: skip
    steps = []
    for values, w, h in (
        ([19.2, 19.4, 20.1, 20.9, 21.3, 21.1], 344, 104),
        ([1, 2, 3], 100, 40),
        ([5, 5, 5], 100, 40),
        ([3], 100, 40),
        ([], 100, 40),
        ([1, 3, 2], 0, 40),
        ([1, 3, 2], 9, 9),
    ):
        points = tp.line_points(values, w, h, 4)
        steps.append({"values": values, "w": w, "h": h, "points": points, "expect": tp.step_rects(points)})
    bars = [
        {"n": n, "mark": mark, "expect": tp.bar_marks(n, mark)}
        for n, mark in (
            (7, None), (7, 4), (7, 2.4), (7, 2.5), (7, -0.5), (7, -0.6), (7, 6), (7, 6.5),
            (7, 7), (7, -1), (7, 1e9), (0, 0), (1, 0),
        )
    ]
    write_rows(
        "maths.json",
        {
            "note": (
                "Vectors for the rules of contract 4.7, made by reference/tabproto.py. "
                "Colours are 0xRRGGBB as integers. 'linear' is the table of lum(): "
                "every side holds a copy and compares it bit for bit. 'mix': "
                "[a, b, p, mix(a, b, p)]; 'mix_halves': for each weight in use, "
                "every pair of channel values [a, b, out] where a * (100 - p) + b * p "
                "ends in exactly 50. 'blend': blend(a, b, 0.82) per channel, at every "
                "exact half and at every pair where a fused multiply-add may give "
                "another value. 'themes': the page themes the vectors use, in device "
                "form; 'styles': the card styles. 'card': card_colours() for a theme "
                "and a style of those, a tint, on and lit, with the card's tokens "
                "ion, onbg_pr and bg. 'image': image_look() for a card of a theme "
                "without a style (null: not drawn). 'label': label_size() before the width is checked; "
                "'smaller' are the sizes to try in turn while the text is wider than "
                "the rectangle. 'clock': clock_text(). 'slider': amounts and values "
                "under a finger ([x, y, amount, value]; value null: nothing is sent, "
                "for a slider whose track has no length or whose max is not above "
                "min), "
                "and slider_shape() for values, as distances from the start edge "
                "along the axis. 'track': track_pieces(). 'choice': choice_cells() "
                "from the rectangle's corner, null when nothing is drawn, and the "
                "option under a point (null: none). 'steps': linePoints and the "
                "steps' rectangles. 'bars': the colour of each bar with mark."
            ),
            "linear": list(tp.LINEAR),
            "mix": mix_cases,
            "mix_halves": halves,
            "lum": [[c, tp.lum(c)] for c in SAMPLE_COLOURS + LEGIBLE_EDGES + READABLE_EDGES],
            "contrast": [[a, b, tp.contrast(a, b)] for a, b in pairs],
            "readable": [[c, tp.readable(c)] for c in SAMPLE_COLOURS + READABLE_EDGES],
            "legible": [
                [c, b, t, tp.legible(c, b, t)]
                for c in SAMPLE_COLOURS + LEGIBLE_EDGES
                for b in (0x181C23, 0xFFFFFF, 0x33291A, 0xFFF1D6)
                for t in (0xE8EAED, 0x15181D)
            ],
            "blend": {
                "t": blend_t,
                "cases": [[a, b, tp.blend(a, b, blend_t)] for a, b in pairs],
                "halves": blend_halves,
                "fused": blend_fma,
            },
            "themes": themes,
            "styles": styles,
            "card": cards,
            "image": images,
            "label": label_cases,
            "clock": clock_cases,
            "slider": sliders,
            "track": tracks,
            "choice": choices,
            "steps": steps,
            "bars": bars,
        },
    )


def device_slot(built: dict, source: int, roles: dict | None = None) -> int:
    """The device slot of a source slot in the kit (a colour slot by its roles)."""
    want = {k: tp.colour(v) for k, v in roles.items()} if roles else None
    found = [
        entry["d"]
        for entry in built["compiled"]["slots"]
        if entry["src"] == source and entry.get("roles") == want
    ]
    assert len(found) == 1, (source, found)
    return found[0]


def kit_wire(built: dict) -> dict:
    """The wire value of every device slot of the kit, from KIT_VALUES."""
    level = ICONS["version"]
    out = {}
    for entry in built["compiled"]["slots"]:
        out[entry["d"]] = tp.coerce(
            entry["type"], KIT_VALUES[entry["src"]], ICONS, level,
            entry.get("coerce"), entry.get("roles"),
        )  # fmt: skip
    return out


def input_v2(built: dict) -> None:
    """Write input_v2.json. The expected events and pages are written by hand
    from the tables of contract 4.3 and 7.4, not worked out by code."""
    layout_hash = built["compiled"]["hash"]
    wire = kit_wire(built)
    on1 = device_slot(built, 2)
    un2 = device_slot(built, 8)
    arm, disarm = device_slot(built, 28), device_slot(built, 29)
    bar52 = device_slot(built, 31)
    switch53 = device_slot(built, 32)
    step14 = device_slot(built, 37)

    def slots(**over) -> list:
        values = dict(wire)
        for key, value in over.items():
            values[int(key[1:])] = value
        return [[d, values[d]] for d in sorted(values)]

    def tap(x: int, y: int, up: int = 100) -> list:
        return [[0, "down", x, y], [up, "up", x, y]]

    def press(**kw) -> dict:
        return kw

    counter = [0]

    def payload(widget: int, event: str, confirmed: bool = False, value=None, **over) -> dict:
        counter[0] += 1
        text = tp.input_payload(
            over.get("mac", MAC), NONCE, counter[0], over.get("layout", layout_hash),
            widget, event, confirmed, value,
        )  # fmt: skip
        if over.get("version"):
            text = over["version"] + text[1:]
        return {"d": text, "s": tp.sign(SECRET, text)}

    # Touch cases: (name, note, page, slots, touch, events, end page, question).
    cases = [
        press(
            name="card_tap", page=0, slots=slots(),
            note="Card 1, outside its widgets: the card's tap (4.3, last row).",
            touch=tap(300, 240), events=[[2, "t", 0, None]], end=0, question=0,
            counter=1, payload=payload(2, "t"), verdict="ok", run=True,
        ),
        press(
            name="card_tap_on_a_label", page=0, slots=slots(),
            note="A label only shows: the press is the card's.",
            touch=tap(300, 154), events=[[2, "t", 0, None]], end=0, question=0,
        ),
        press(
            name="card_tap_while_on_has_no_value", page=0, slots=slots(**{f"s{on1}": None}),
            note="A card tap needs no value (4.3).",
            touch=tap(300, 240), events=[[2, "t", 0, None]], end=0, question=0,
        ),
        press(
            name="card_tap_ack_not_ok", page=0, slots=slots(), acks=[[300, False, "failed"]],
            note="The ack changes the look only, not what was sent.",
            touch=tap(300, 240), events=[[2, "t", 0, None]], end=0, question=0,
        ),
        press(
            name="short_press_is_a_tap", page=0, slots=slots(),
            touch=tap(300, 240, 450), events=[[2, "t", 0, None]], end=0, question=0,
        ),
        press(
            name="drift_8_8_is_a_tap", page=0, slots=slots(),
            note="8 px sideways and 8 down is 11.3 px: still a tap.",
            touch=[[0, "down", 300, 240], [50, "move", 308, 248], [100, "up", 308, 248]],
            events=[[2, "t", 0, None]], end=0, question=0,
        ),
        press(
            name="drift_9_9_is_no_tap", page=0, slots=slots(),
            note="9 and 9 is 12.7 px: no card tap, no swipe.",
            touch=[[0, "down", 300, 240], [50, "move", 309, 249], [100, "up", 309, 249]],
            events=[], end=0, question=0,
        ),
        press(
            name="drift_20_is_no_tap", page=0, slots=slots(),
            touch=[[0, "down", 300, 240], [50, "move", 320, 240], [100, "up", 320, 240]],
            events=[], end=0, question=0,
        ),
        press(
            name="drift_13_and_back_is_no_tap", page=0, slots=slots(),
            note="Once 12 px are passed, coming back does not make the press a tap again.",
            touch=[[0, "down", 300, 240], [30, "move", 313, 240], [60, "move", 300, 240], [100, "up", 300, 240]],
            events=[], end=0, question=0,
        ),
        press(
            name="drift_13_and_back_is_no_hold", page=0, slots=slots(),
            note="The same press held 700 ms: the card's hold does not open page 3.",
            touch=[[0, "down", 300, 240], [30, "move", 313, 240], [60, "move", 300, 240], [700, "up", 300, 240]],
            events=[], end=0, question=0,
        ),
        press(
            name="slow_swipe_from_a_card", page=0, slots=slots(),
            note="100 px to the left over 2 s: a swipe (no time limit), no tap, no hold.",
            touch=[[0, "down", 300, 240], [50, "move", 288, 240], [500, "move", 250, 240],
                   [1500, "move", 200, 240], [2000, "up", 200, 240]],
            events=[], end=1, question=0,
        ),
        press(
            name="swipe_right_wraps", page=0, slots=slots(),
            note="From the first normal page to the last normal page; never a detail page.",
            touch=[[0, "down", 700, 760], [100, "move", 760, 760], [200, "move", 820, 760], [300, "up", 820, 760]],
            events=[], end=2, question=0,
        ),
        press(
            name="hold_opens_the_page", page=0, slots=slots(),
            note="500 ms: the card's hold opens page 3. Nothing is sent, the release is no tap.",
            touch=tap(300, 240, 700), events=[], end=3, question=0,
        ),
        press(
            name="bar_with_change", page=0, slots=slots(),
            note="Card 1's bar: the slider's, never the card's. Half way is 50.",
            touch=tap(288, 292), events=[[6, "c", 0, 50]], end=0, question=0,
        ),
        press(
            name="hold_on_a_slider_is_none", page=0, slots=slots(),
            note="No hold on a slider with change; its release sends.",
            touch=tap(288, 292, 600), events=[[6, "c", 0, 50]], end=0, question=0,
        ),
        press(
            name="unavailable_card_tap", page=0, slots=slots(**{f"s{un2}": 1}),
            note="Card 2 with un 1: nothing is sent.",
            touch=tap(684, 240), events=[], end=0, question=0,
        ),
        press(
            name="unavailable_card_hold", page=0, slots=slots(**{f"s{un2}": 1}),
            note="A go still works on an unavailable card.",
            touch=tap(684, 240, 700), events=[], end=3, question=0,
        ),
        press(
            name="unavailable_card_slider", page=0, slots=slots(**{f"s{un2}": 1}),
            note="Card 2's bar with un 1: the slider's press, and nothing is sent.",
            touch=tap(672, 292), events=[], end=0, question=0,
        ),
        press(
            name="unavailable_card_slider_hold", page=0, slots=slots(**{f"s{un2}": 1}),
            note="A slider with change has no hold, also in an unavailable card.",
            touch=tap(672, 292, 700), events=[], end=0, question=0,
        ),
        press(
            name="unavailable_card_label_tap", page=0, slots=slots(**{f"s{un2}": 1}),
            note="A label only shows: the press is the card's, and the card sends nothing.",
            touch=tap(708, 190), events=[], end=0, question=0,
        ),
        press(
            name="unavailable_card_label_hold", page=0, slots=slots(**{f"s{un2}": 1}),
            note="The card's hold, from its label: the go still works.",
            touch=tap(708, 190, 700), events=[], end=3, question=0,
        ),
        press(
            name="choice_cell", page=0, slots=slots(),
            note="Card 4, first choice: the third of four cells.",
            touch=tap(452, 420), events=[[19, "c", 0, 2]], end=0, question=0,
            counter=2, payload=payload(19, "c", value=2), verdict="ok", run=True,
        ),
        press(
            name="choice_gap", page=0, slots=slots(),
            note="Between the first two cells: nothing.",
            touch=tap(248, 420), events=[], end=0, question=0,
        ),
        press(
            name="choice_hold_is_none", page=0, slots=slots(),
            touch=tap(452, 420, 600), events=[[19, "c", 0, 2]], end=0, question=0,
        ),
        press(
            name="choice_released_in_another_cell", page=0, slots=slots(),
            note="Down in the first cell of the icon choice, up in the cell under it.",
            touch=[[0, "down", 200, 476], [50, "move", 200, 504], [100, "move", 200, 532], [150, "up", 200, 532]],
            events=[], end=0, question=0,
        ),
        press(
            name="choice_second_row", page=0, slots=slots(),
            touch=tap(383, 532), events=[[20, "c", 0, 4]], end=0, question=0,
        ),
        press(
            name="choice_asks_first", page=0, slots=slots(),
            note="The swatches have cf and a confirm text: the question opens, nothing is sent yet.",
            touch=tap(274, 592), events=[], end=0, question=1,
        ),
        press(
            name="upright_slider", page=0, slots=slots(),
            note="Bottom to top: 160 px of 200 from the bottom edge is 80. A press on a slider with change is never a swipe.",
            touch=[[0, "down", 924, 416], [50, "move", 924, 346], [100, "move", 924, 276], [150, "up", 924, 276]],
            events=[[15, "c", 0, 80]], end=0, question=0,
            counter=3, payload=payload(15, "c", value=80), verdict="ok", run=True,
        ),
        press(
            name="track_slider_is_never_a_swipe", page=0, slots=slots(),
            note="156 px to the left on the hue track: (16 - 7) / 330 of 360 is 9.8, on the step 10.",
            touch=[[0, "down", 1056, 160], [50, "move", 980, 160], [100, "move", 900, 160], [150, "up", 900, 160]],
            events=[[13, "c", 0, 10]], end=0, question=0,
        ),
        press(
            name="bar_track_half_rounds_up", page=0, slots=slots(),
            note="Half way on the white track is 4250; 22.5 steps of 100 round up to 4300.",
            touch=tap(1056, 208), events=[[14, "c", 0, 4300]], end=0, question=0,
        ),
        press(
            name="button_with_tap", page=0, slots=slots(),
            touch=tap(756, 572), events=[[23, "t", 0, None]], end=0, question=0,
        ),
        press(
            name="round_button", page=0, slots=slots(),
            touch=tap(1156, 604), events=[[26, "t", 0, None]], end=0, question=0,
        ),
        press(
            name="image_with_hold_tap", page=0, slots=slots(),
            note="A widget with hold and no tap: a tap is the card's, and card 5 has none.",
            touch=tap(996, 636), events=[], end=0, question=0,
        ),
        press(
            name="image_with_hold_hold", page=0, slots=slots(),
            touch=tap(996, 636, 600), events=[], end=4, question=0,
        ),
        press(
            name="child_tap_is_never_the_cards", page=1, slots=slots(),
            note="The switch of the Routing card.",
            touch=tap(1036, 628), events=[[53, "t", 0, None]], end=1, question=0,
            counter=4, payload=payload(53, "t"), verdict="ok", run=True,
        ),
        press(
            name="thermostat_body_is_the_cards", page=1, slots=slots(),
            touch=tap(888, 546), events=[[46, "t", 0, None]], end=1, question=0,
        ),
        press(
            name="thermostat_body_hold", page=1, slots=slots(),
            touch=tap(888, 546, 600), events=[], end=4, question=0,
        ),
        press(
            name="thermostat_plus", page=1, slots=slots(),
            note="21.5 and a step of 0.5.",
            touch=tap(970, 626), events=[[47, "c", 0, 22]], end=1, question=0,
            counter=5, payload=payload(47, "c", value=22), verdict="ok", run=True,
        ),
        press(
            name="thermostat_minus", page=1, slots=slots(),
            touch=tap(806, 626), events=[[47, "c", 0, 21]], end=1, question=0,
        ),
        press(
            name="thermostat_button_hold_is_none", page=1, slots=slots(),
            touch=tap(970, 626, 600), events=[[47, "c", 0, 22]], end=1, question=0,
        ),
        press(
            name="swap_shows_arm", page=1, slots=slots(),
            touch=tap(1124, 472), events=[[48, "t", 0, None]], end=1, question=0,
        ),
        press(
            name="swap_shows_disarm", page=1, slots=slots(**{f"s{arm}": 0, f"s{disarm}": 1}),
            touch=tap(1124, 472), events=[[49, "t", 0, None]], end=1, question=0,
        ),
        press(
            name="swap_both_hidden", page=1, slots=slots(**{f"s{arm}": None, f"s{disarm}": None}),
            note="vis without a value hides: the press goes to the card.",
            touch=tap(1124, 472), events=[[46, "t", 0, None]], end=1, question=0,
        ),
        press(
            name="hidden_while_the_finger_is_down", page=1, slots=slots(),
            note="Arm is pressed, then a tab_set swaps the two: the release sends nothing.",
            touch=tap(1124, 472), sets=[[50, [[arm, 0], [disarm, 1]]]],
            events=[], end=1, question=0,
        ),
        press(
            name="hold_on_a_child_with_tap", page=1, slots=slots(),
            note="Arm has a tap and no hold: the card's hold.",
            touch=tap(1124, 472, 600), events=[], end=4, question=0,
        ),
        press(
            name="label_with_colour_is_the_cards", page=1, slots=slots(),
            touch=tap(1124, 518), events=[[46, "t", 0, None]], end=1, question=0,
        ),
        press(
            name="faded_part_that_only_shows", page=1, slots=slots(**{f"s{bar52}": None}),
            note="The bar has no value and no change: the press is the card's.",
            touch=tap(1124, 588), events=[[46, "t", 0, None]], end=1, question=0,
        ),
        press(
            name="faded_control", page=1, slots=slots(**{f"s{switch53}": None}),
            note="The switch has no value: no input, and not the card's.",
            touch=tap(1036, 628), events=[], end=1, question=0,
        ),
        press(
            name="card_with_pulse", page=1, slots=slots(),
            touch=tap(520, 540), events=[[41, "t", 0, None]], end=1, question=0,
        ),
        press(
            name="bare_image_goes", page=1, slots=slots(),
            touch=tap(436, 528), events=[], end=4, question=0,
        ),
        press(
            name="card_asks_first", page=1, slots=slots(),
            touch=tap(672, 540), events=[], end=1, question=1,
        ),
        press(
            name="old_card_on_a_new_layout", page=2, slots=slots(),
            touch=tap(140, 196), events=[[56, "t", 0, None]], end=2, question=0,
        ),
        press(
            name="back_entry", page=0, slots=slots(),
            note="Hold to open page 3, then the side bar's back entry.",
            touch=[[0, "down", 300, 240], [700, "up", 300, 240], [900, "down", 48, 48], [1000, "up", 48, 48]],
            events=[], end=0, question=0,
        ),
        press(
            name="back_button", page=0, slots=slots(),
            touch=[[0, "down", 300, 240], [700, "up", 300, 240], [900, "down", 180, 164], [1000, "up", 180, 164]],
            events=[], end=0, question=0,
        ),
        press(
            name="detail_swipe_right_returns", page=0, slots=slots(),
            touch=[[0, "down", 300, 240], [700, "up", 300, 240], [900, "down", 400, 600],
                   [1000, "move", 460, 600], [1100, "move", 520, 600], [1200, "up", 520, 600]],
            events=[], end=0, question=0,
        ),
        press(
            name="detail_swipe_left_does_nothing", page=0, slots=slots(),
            touch=[[0, "down", 300, 240], [700, "up", 300, 240], [900, "down", 520, 600],
                   [1000, "move", 460, 600], [1100, "move", 400, 600], [1200, "up", 400, 600]],
            events=[], end=3, question=0,
        ),
    ]  # fmt: skip
    out_cases = []
    for case in cases:
        out = {
            "name": case["name"],
            "page": case["page"],
            "slots": case["slots"],
            "touch": case["touch"],
            "events": case["events"],
            "end_page": case["end"],
            "question": case["question"],
        }
        for key in ("note", "sets", "acks", "counter", "payload", "verdict", "run"):
            if key in case:
                out[key] = case[key]
        out_cases.append(out)

    # Home Assistant's own cases, fed in order after the touch cases above.
    sent = dict(wire)
    without_step = {d: v for d, v in wire.items() if d != step14}
    ha = [
        ("field_1_is_2", payload(2, "t", version="2"), "version", None, None),
        ("field_1_is_1", payload(2, "t"), "ok", True, None),
        ("tap_on_a_widget", payload(23, "t"), "ok", True, None),
        ("asked_card_confirmed", payload(44, "t", confirmed=True), "ok", True, None),
        ("card_without_tap", payload(12, "t"), "ok", False, None),
        ("change_for_a_widget_with_tap", payload(23, "c", value=1), "ok", False, None),
        ("tap_for_a_widget_with_change", payload(6, "t"), "ok", False, None),
        ("above_range", payload(6, "c", value=101), "ok", False, None),
        ("below_range", payload(6, "c", value=-1), "ok", False, None),
        ("on_the_step", payload(32, "c", value=21.5), "ok", True, None),
        ("off_the_step", payload(32, "c", value=21.3), "ok", False, None),
        ("within_0_0015_of_the_step", payload(32, "c", value=21.501), "ok", True, None),
        ("step_0_between_steps", payload(63, "c", value=12.34), "ok", True, None),
        ("live_step_never_sent", payload(14, "c", value=2100), "ok", False, without_step),
        ("live_step_sent", payload(14, "c", value=2100), "ok", True, None),
        ("live_limits", payload(64, "c", value=2700), "ok", True, None),
        ("below_live_min", payload(64, "c", value=1900), "ok", False, None),
        ("live_max_off_the_step", payload(64, "c", value=6535), "ok", True, None),
        ("choice_index", payload(19, "c", value=3), "ok", True, None),
        ("choice_index_past_the_options", payload(19, "c", value=4), "ok", False, None),
        ("choice_index_fraction", payload(19, "c", value=1.5), "ok", False, None),
        ("choice_index_below_0", payload(19, "c", value=-1), "ok", False, None),
        ("choice_without_value_key", payload(21, "c", value=4), "ok", True, None),
    ]  # fmt: skip
    for name, data, verdict, run, sent_here in ha:
        case = {"name": name, "payload": data, "verdict": verdict, "run": run}
        if sent_here is not None:
            case["sent"] = [[d, v] for d, v in sorted(sent_here.items())]
        out_cases.append(case)
    write(
        "input_v2.json",
        {
            "note": (
                "Presses on layout_v2_kit, for a tablet that speaks version 2, is "
                "paired with secret_hex, has a session with nonce and sends; each "
                "case starts on a fresh screen at least 60 s after power-on (no "
                "erase watch), on 'page', with the slot values 'slots' ([device "
                "slot, value]). 'touch': [ms, 'down' | 'move' | 'up', x, y]. "
                "'sets': [ms, [[slot, value], ...]], a tab_set that arrives while "
                "the finger is down. 'acks': [ms, ok, code]. Expected: 'events', "
                "each [widget id, event, confirmed, value], in order (value null "
                "for a tap); 'end_page', the page shown at the end; 'question', 1 "
                "when the question box is open at the end. These are written by "
                "hand from contract 4.3 and 7.4. A case with 'payload' and "
                "'verdict' is also input for HA: feed those cases in order "
                "(last_counter starts at 0 and moves on 'ok'); 'run' says whether "
                "HA runs the input after the checks of contract 7.3 (2), with "
                "'sent' (else the file's 'sent') as the values HA last sent this "
                "tablet. A touch case with 'counter' emits that 'payload' for its "
                "first event when the tablet's next counter is 'counter'."
            ),
            "layout": "layout_v2_kit",
            "hash": layout_hash,
            "mac": MAC,
            "secret_hex": SECRET.hex(),
            "nonce": NONCE,
            "sent": [[d, v] for d, v in sorted(sent.items())],
            "cases": out_cases,
        },
    )


def state_v2(built: dict) -> None:
    """Write state_v2.json. The expected looks are written by hand from
    contract 4.4 and 4.7; the colour samples by hand from 4.4."""
    layout_hash = built["compiled"]["hash"]
    wire = kit_wire(built)
    d = {name: device_slot(built, src) for name, src in (
        ("tint", 3), ("un", 8), ("pos", 12), ("rate", 13), ("speed", 14), ("mark", 22),
        ("target", 23), ("bar_mark", 25), ("clock", 27), ("arm", 28), ("disarm", 29),
    )}  # fmt: skip
    d["status"] = device_slot(built, 20, STATUS_LIGHT)
    steps = []

    def step(at: int, note: str, values: dict | None, show: list, *, full: bool = False) -> None:
        payloads = tp.encode_set(layout_hash, values, full=full) if values is not None else []
        steps.append({"at_ms": at, "note": note, "payloads": payloads, "show": show})

    step(0, "Full snapshot of every slot.", wire, [
        {"id": 39, "text": "10:15"}, {"id": 40, "text": "10:15"},
        {"id": 17, "value": 30, "faded": 0},
        {"id": 2, "tint": 0xFFA757}, {"id": 6, "colour": 0xFFA757}, {"id": 7, "tint": 0xFFA757, "un": 0},
        {"id": 19, "selected": 1}, {"id": 20, "selected": 0}, {"id": 21, "selected": None},
        {"id": 48, "vis": 1}, {"id": 49, "vis": 0},
        {"id": 32, "mark": 20.8, "faded": 0}, {"id": 35, "mark": 4},
        {"id": 50, "colour": 0x1E8E5A}, {"id": 28, "colour": 0x4CC38A},
    ], full=True)  # fmt: skip
    step(60000, "A minute later, with no call: the clock and the progress count on.", None, [
        {"id": 39, "text": "10:16"}, {"id": 40, "text": "10:16"}, {"id": 17, "value": 90},
    ])  # fmt: skip
    step(61000, "The clock gets the same value again: its age starts again.", {d["clock"]: 615}, [
        {"id": 39, "text": "10:15"}, {"id": 40, "text": "10:15"}, {"id": 17, "value": 91},
    ])  # fmt: skip
    step(70000, "A new rate without a value: the count goes on from the value's last write.",
         {d["rate"]: 2}, [{"id": 17, "value": 170}, {"id": 39, "text": "10:15"}])  # fmt: skip
    step(80000, "A new rate with a value, in one call.", {d["pos"]: 100, d["rate"]: 0.5},
         [{"id": 17, "value": 100}])  # fmt: skip
    step(90000, "Ten seconds later.", None, [{"id": 17, "value": 105}, {"id": 39, "text": "10:15"}])
    step(91000, "A rate without a value counts as 0.", {d["rate"]: None}, [{"id": 17, "value": 100}])
    step(92000, "Progress past the end is held to max.", {d["pos"]: 299, d["rate"]: 1}, [{"id": 17, "value": 299}])
    step(95000, "Three seconds later.", None, [{"id": 17, "value": 300}])
    for at, value, want, note in (
        (100000, 1e9, None, "A colour of 1e9 is out of range: no colour."),
        (101000, -1, None, "-1: no colour."),
        (102000, 0.5, None, "0.5: no colour."),
        (103000, 0xFFFFFF, 0xFFFFFF, "16777215 is the largest colour."),
        (104000, 0x1000000, None, "16777216: no colour."),
        (105000, 0xFF0000, 0xFF0000, "Red."),
    ):
        step(at, note, {d["tint"]: value}, [
            {"id": 2, "tint": want}, {"id": 6, "colour": want}, {"id": 7, "tint": want},
        ])  # fmt: skip
    step(110000, "The swap: Arm hidden, Disarm shown.", {d["arm"]: 0, d["disarm"]: 1},
         [{"id": 48, "vis": 0}, {"id": 49, "vis": 1}])  # fmt: skip
    step(111000, "vis without a value hides both.", {d["arm"]: None, d["disarm"]: None},
         [{"id": 48, "vis": 0}, {"id": 49, "vis": 0}])  # fmt: skip
    step(112000, "Card 2 becomes unavailable: header and widgets at 40%.", {d["un"]: 1}, [
        {"id": 7, "un": 1}, {"id": 8, "faded": 1}, {"id": 9, "faded": 1}, {"id": 10, "faded": 1},
        {"id": 11, "faded": 1}, {"id": 2, "un": 0}, {"id": 6, "faded": 0},
    ])  # fmt: skip
    step(113000, "un without a value counts as 0.", {d["un"]: None},
         [{"id": 7, "un": 0}, {"id": 8, "faded": 0}, {"id": 11, "faded": 0}])  # fmt: skip
    for at, value, want in ((114000, 1e9, None), (115000, -1, None), (116000, 0.5, None), (117000, 3, 3), (118000, 4, None)):
        step(at, f"The first choice gets {value!r}.", {d["speed"]: value}, [{"id": 19, "selected": want}])
    step(120000, "The thermostat has no target but a temperature: the mark is drawn, faded.",
         {d["target"]: None, d["mark"]: 21.5}, [
        {"id": 32, "faded": 1, "mark": 21.5}, {"id": 47, "faded": 1},
    ])  # fmt: skip
    for at, value, want in ((121000, 1e9, None), (122000, -1, None), (123000, 0.5, None), (124000, 7, 7), (125000, 35, 35), (126000, 35.5, None)):
        step(at, f"The thermostat's mark gets {value!r} (min 7, max 35).", {d["mark"]: value},
             [{"id": 32, "mark": want}])  # fmt: skip
    for at, value, want in ((130000, -1, None), (131000, 7, None), (132000, 6, 6), (133000, 0.5, 1), (134000, 1e9, None), (135000, None, None)):
        step(at, f"The bar chart's mark gets {value!r} (7 bars).", {d["bar_mark"]: value},
             [{"id": 35, "mark": want}])  # fmt: skip
    for at, value, want in ((140000, 0x123456, 0x123456), (141000, None, None), (142000, 0.5, None)):
        step(at, f"The label's colour slot gets {value!r}.", {d["status"]: value}, [{"id": 50, "colour": want}])
    step(150000, "A full snapshot with the clock only: every other slot has no value.",
         {d["clock"]: 900}, [
        {"id": 39, "text": "15:00"}, {"id": 40, "text": "3:00"},
        {"id": 17, "value": None, "faded": 1}, {"id": 13, "faded": 0}, {"id": 14, "faded": 1},
        {"id": 19, "selected": None}, {"id": 48, "vis": 0}, {"id": 49, "vis": 0},
        {"id": 2, "tint": None}, {"id": 32, "faded": 1, "mark": None},
    ], full=True)  # fmt: skip
    step(450000, "Five minutes later.", None, [{"id": 39, "text": "15:05"}, {"id": 40, "text": "3:05"}])
    step(451000, "No value for the clock.", {d["clock"]: None},
         [{"id": 39, "text": "--:--"}, {"id": 40, "text": "--:--"}])  # fmt: skip
    colours = [
        [[255, 0, 0], None, 0xFF0000],
        [[255.4, 0, 0], None, 0xFF0000],
        [[255.5, 0, 0], None, None],
        [[-0.4, 0, 0], None, 0x000000],
        [[-0.6, 0, 0], None, None],
        [[0, 127.5, 0], None, 0x008000],
        [[255, 0], None, None],
        [[255, 0, 0, 0], None, None],
        [[True, 0, 0], None, None],
        [["255", 0, 0], None, None],
        ["#ff8800", None, 0xFF8800],
        ["#FF8800", None, 0xFF8800],
        ["#FFF", None, None],
        ["FF8800", None, None],
        ["#FF880", None, None],
        ["#GG8800", None, None],
        [16711680, None, 0xFF0000],
        [16711680.0, None, 0xFF0000],
        [16711680.5, None, None],
        [0, None, 0x000000],
        [16777215, None, 0xFFFFFF],
        [16777216, None, None],
        [-1, None, None],
        ["16711680", None, None],
        [True, None, None],
        [None, None, None],
        ["good", STATUS_DARK, 0x4CC38A],
        ["good", STATUS_LIGHT, 0x1E8E5A],
        ["warn", STATUS_LIGHT, 0xB86E00],
        ["unknown", STATUS_DARK, None],
        ["good", None, None],
    ]
    write(
        "state_v2.json",
        {
            "note": (
                "A tab_set stream for layout_v2_kit on a tablet that speaks version "
                "2. Each step arrives at 'at_ms' (the tablet's clock, from the first "
                "step; a step without payloads only lets time pass) and must answer "
                "ok. 'show' is what a widget must show after the step, written by "
                "hand from contract 4.4 and 4.7: 'text' of a label; 'value' a slider "
                "shows (with rate: clamp(value + rate * age, min, max); null: no "
                "value); 'faded' 1 when drawn at 40%; 'vis' 0 when not drawn; "
                "'tint' of a card and 'colour' (the c of a widget) as the colour in "
                "force, null when there is none and the part keeps its usual colour; "
                "'un' of a card; 'selected' option of a choice (null: none); 'mark' "
                "of a thermostat (the value drawn as a dot, null: no mark) or of a "
                "bar chart (the index of the bar in acc, null: no mark). 'colours': "
                "[value as HA finds it, the roles HA knows for the card or null, "
                "the wire value or null] (contract 4.4, colour conversion)."
            ),
            "layout": "layout_v2_kit",
            "hash": layout_hash,
            "slots": {name: slot for name, slot in sorted(d.items())},
            "steps": steps,
            "colours": colours,
        },
    )


def hello_v2(built: dict, small: dict) -> None:
    """Write hello_v2.json: which version HA compiles, which hash it expects."""
    kit_hash = built["compiled"]["hash"]
    layouts = {
        "1": small["compiled"]["hash"],
        "2": kit_hash,
        "2_nochoice": built["nochoice"]["hash"],
    }
    base = {
        "proto": [1, 2],
        "engine": "0.2.0",
        "boot": 3,
        "layout": kit_hash,
        "kid": tp.kid(SECRET),
        "enc": 1,
        "caps": dict(tp.ENGINE_CAPS),
        "mem": {"int": 61000, "psram": 28000000, "block": 16000000},
        "session": 1,
    }
    no_pages = {k: v for k, v in base["caps"].items() if k != "max_pages"}
    cases = [
        {"name": "speaks_1_and_2", "response": base, "want": "2", "dl": 2,
         "stored_kid": tp.kid(SECRET), "expect": ["send_state"]},
        {"name": "speaks_1_only", "response": {**base, "proto": [1, 1], "layout": layouts["1"]},
         "want": "1", "dl": 1, "stored_kid": tp.kid(SECRET), "expect": ["send_state"]},
        {"name": "speaks_1_only_holds_a_version_2_layout", "response": {**base, "proto": [1, 1]},
         "want": "1", "dl": 1, "stored_kid": tp.kid(SECRET), "expect": ["send_layout", "send_state"]},
        {"name": "speaks_2_only", "response": {**base, "proto": [2, 2]}, "want": "2", "dl": 2,
         "stored_kid": tp.kid(SECRET), "expect": ["send_state"]},
        {"name": "speaks_2_and_3", "response": {**base, "proto": [2, 3]}, "want": "2", "dl": 2,
         "stored_kid": tp.kid(SECRET), "expect": ["send_state"]},
        {"name": "speaks_3_and_4", "response": {**base, "proto": [3, 4]}, "want": None, "dl": 0,
         "stored_kid": tp.kid(SECRET), "expect": [], "status": "unsupported", "reason": "tablet_new"},
        {"name": "without_choice", "response": {**base, "caps": NOCHOICE_CAPS}, "want": "2_nochoice",
         "dl": 2, "stored_kid": tp.kid(SECRET), "expect": ["send_layout", "send_state"]},
        {"name": "without_max_pages", "note": "HA sends at most 20 pages to this tablet.",
         "response": {**base, "caps": no_pages}, "want": "2", "dl": 2, "max_pages": 20,
         "stored_kid": tp.kid(SECRET), "expect": ["send_state"]},
        {"name": "without_encryption", "response": {**base, "enc": 0, "kid": "", "layout": ""},
         "want": "2", "dl": 2, "stored_kid": None, "expect": ["send_layout", "send_state"],
         "reason": "needs_encryption"},
    ]  # fmt: skip
    for case in cases:
        case.setdefault("max_pages", case["response"]["caps"].get("max_pages", 20) if case["dl"] else 0)
        want = layouts[case["want"]] if case["want"] else None
        got = tp.hello_steps(case["response"], stored_kid=case["stored_kid"], want_hash=want or "x")
        assert got["steps"] == case["expect"], (case["name"], got)
        assert got["status"] == case.get("status", ""), (case["name"], got)
        assert got["reason"] == case.get("reason", ""), (case["name"], got)
        assert got["dl"] == case["dl"], (case["name"], got)
    write(
        "hello_v2.json",
        {
            "note": (
                "tab_hello responses of tablets that may speak version 2, and what "
                "HA does next. 'dl': the device layout version HA compiles (0: "
                "none, unsupported). 'want': which of 'layouts' HA compiles for "
                "this tablet: '1' is layout_small (the dashboard of version 1), "
                "'2' layout_v2_kit, '2_nochoice' its form for a tablet without "
                "choice. 'max_pages': the most pages HA sends. 'expect': as in "
                "hello.json. The first case is what engine 0.2.0 answers (with "
                "TAB_PROTO_HIGH 2), caps equal to engine_caps of contract.json."
            ),
            "mac": MAC,
            "secret_hex": SECRET.hex(),
            "call": {"nonce": NONCE, "auth": tp.call_auth(SECRET, MAC, NONCE, 0, "tab_hello")},
            "layouts": layouts,
            "cases": cases,
        },
    )


# Texts at the 40-byte border of an option text: "é" is two bytes.
TEXT_40 = "a" * 38 + "é"
TEXT_41 = "a" * 39 + "é"
SEVENTEEN = [f"Option {k}" for k in range(1, 18)]
NINE_COLOURS = HUES[:6] + WHITES
# What the tablet test of commit_v2 "uncut_lists" puts back in place of HA's cuts.
CUT_RAW = {
    3: {"track": [tp.colour(c) for c in NINE_COLOURS]},
    5: {"texts": SEVENTEEN[:16] + [TEXT_41]},
}


def cut_source() -> dict:
    """A layout at the list limits of a widget, for commit_v2.json "cuts"."""
    widgets = [
        {"id": 2, "t": "slider", "r": [116, 140, 344, 40], "value": 50, "min": 0, "max": 100,
         "step": 1, "change": OPTIMISTIC, "track": NINE_COLOURS[:8]},
        {"id": 3, "t": "slider", "r": [116, 188, 344, 40], "value": 50, "min": 0, "max": 100,
         "step": 1, "change": OPTIMISTIC, "track": NINE_COLOURS},
        {"id": 4, "t": "choice", "r": [116, 236, 536, 200], "rows": 4, "value": 0,
         "texts": SEVENTEEN[:15] + [TEXT_40], "change": OPTIMISTIC},
        {"id": 5, "t": "choice", "r": [116, 444, 536, 200], "rows": 4, "value": 0,
         "texts": SEVENTEEN[:16] + [TEXT_41], "icons": ["mdi:fan"] * 17,
         "cols": ["#FF0000"] * 17, "change": OPTIMISTIC},
        {"id": 6, "t": "choice", "r": [116, 652, 536, 48], "texts": ["a", TEXT_41], "change": OPTIMISTIC},
    ]  # fmt: skip
    return {
        "v": 2,
        "screen": [1280, 800],
        "theme": MIDNIGHT,
        "nav": [],
        "pages": [
            {"id": "cuts", "title": "Cuts", "w": [
                {"id": 1, "t": "card", "r": [100, 84, 568, 640], "w": widgets},
            ]},
        ],
    }  # fmt: skip


def commit_v2(built: dict) -> None:
    """Write commit_v2.json: layouts at the page limits of version 2."""
    device = json.loads(built["compiled"]["bytes"])

    def page(sub=None) -> dict:
        out = {"title": "", "w": []}
        if sub is not None:
            out["sub"] = sub
        return out

    def layout(pages: list, v: int = 2) -> dict:
        return {**device, "v": v, "nav": [], "pages": pages, "slots": ""}

    def case(name: str, obj: dict, commit: str, note: str = "") -> dict:
        raw = tp.canonical(obj)
        out = {
            "name": name,
            "calls": [{"hash": tp.content_hash(raw), "seq": 0, "total": 1, "size": len(raw), "data": raw.decode("utf-8")}],
            "expect": ["ok"],
            "commit_hash": tp.content_hash(raw),
            "commit": commit,
        }  # fmt: skip
        if note:
            out = {"name": name, "note": note, **{k: v for k, v in out.items() if k != "name"}}
        assert (tp.tablet_commit(raw) or "ok") == commit, (name, tp.tablet_commit(raw))
        return out

    cases = [
        case("pages_64", layout([page()] + [page(1)] * 63), "ok"),
        case("pages_65", layout([page()] + [page(1)] * 64), "limits"),
        case("normal_20", layout([page()] * 20 + [page(1)] * 2), "ok"),
        case("normal_21", layout([page()] * 21), "limits"),
        case("normal_21_of_version_1", layout([page()] * 21, v=1), "limits"),
        case("sub_on_page_0_is_ignored", layout([page(1)] + [page()] * 20), "limits",
             "Page 0 with sub 1 is a normal page: 21 normal pages."),
        case("sub_on_page_0_and_19_more", layout([page(1)] + [page()] * 19 + [page(1)]), "ok"),
        case("sub_0_is_normal", layout([page()] * 20 + [page(0)]), "limits",
             "A page with \"sub\": 0 is normal: 21 normal pages."),
        case("sub_2_is_normal", layout([page()] * 20 + [page(2)]), "limits",
             "sub counts only when it is exactly 1."),
        case("detail_pages_of_version_1", layout([page()] + [page(1)] * 20, v=1), "limits",
             "A version 1 layout has at most 20 pages, whatever they say."),
        case("version_3", {**device, "v": 3}, "version"),
        case("kit", device, "ok"),
    ]  # fmt: skip
    source = kit_source()
    many = {
        **source,
        "nav": [],
        "pages": [source["pages"][0]] + [
            {"id": f"d{i}", "title": "", "sub": 1, "w": []} for i in range(20)
        ],
    }
    ha = []
    for name, caps, expect in (
        ("without_max_pages", {k: v for k, v in tp.ENGINE_CAPS.items() if k != "max_pages"}, "limits"),
        ("with_max_pages_64", tp.ENGINE_CAPS, "ok"),
        ("with_max_pages_21", {**tp.ENGINE_CAPS, "max_pages": 21}, "ok"),
        ("with_max_pages_20", {**tp.ENGINE_CAPS, "max_pages": 20}, "limits"),
    ):
        try:
            got = tp.compile_device_layout_v2(many, ICONS, caps)["hash"]
            verdict = "ok"
        except tp.ContractError as error:
            got, verdict = None, error.code
        assert verdict == expect, (name, verdict)
        ha.append({"name": name, "caps": caps, "expect": expect, "hash": got})
    cuts_source = cut_source()
    cuts = tp.compile_device_layout_v2(cuts_source, ICONS, ENGINE_CAPS)
    cut_widgets = {
        widget["id"]: widget
        for page in json.loads(cuts["bytes"])["pages"]
        for item in page["w"]
        for widget in item.get("w", [])
    }
    # The tablet's own reading of the same keys when they come uncut.
    raw_device = json.loads(cuts["bytes"])
    for widget in raw_device["pages"][0]["w"][0]["w"]:
        widget.update(CUT_RAW.get(widget["id"], {}))
    cases.append(case("uncut_lists", raw_device, "ok",
                      "A track of 9 colours, 17 options and a text of 41 bytes: the tablet "
                      "keeps the first 8 colours and 16 options and cuts the text to 40 "
                      "bytes at a character border, never parse (4.3)."))  # fmt: skip
    write(
        "commit_v2.json",
        {
            "note": (
                "Layouts at the page limits of version 2, for a tablet that speaks "
                "version 2 (caps as engine_caps). Each case is one transfer on a "
                "fresh tablet that is not paired, as in chunks.json; 'commit' is the "
                "answer of tab_commit(commit_hash). 'ha': what HA's compile does "
                "with 'source' (page 0 of the kit and 20 detail pages, 21 pages) "
                "for a tablet with these caps: 'limits', or 'ok' with the hash. "
                "'cuts': what HA's compile writes for 'cuts_source' (a track of 8 "
                "and of 9 colours, a choice of 16 and of 17 options, option texts "
                "of 40 and 41 bytes with a two-byte character on the border), with "
                "the hash and the compiled widgets by id."
            ),
            "cases": cases,
            "source": many,
            "ha": ha,
            "cuts_source": cuts_source,
            "cuts": {"hash": cuts["hash"], "widgets": {str(k): v for k, v in sorted(cut_widgets.items())}},
        },
    )


def main() -> None:
    components, themes = load_library()
    assert len(components) == 16, len(components)
    small = build("layout_small", SMALL, components, themes)
    big = build("layout_all_cards", ALL_CARDS, components, themes)
    used = {
        item["component"]
        for page in big["result"]["layout"]["pages"]
        for item in page["w"]
        if item["t"] == "card"
    }
    assert used == set(components), sorted(set(components) - used)
    assert not big["compiled"]["dropped"]
    kinds = {
        widget["t"]
        for page in json.loads(big["compiled"]["bytes"])["pages"]
        for item in page["w"]
        for widget in [item, *item.get("w", [])]
    }
    assert kinds == set(tp.WIDGET_KINDS), kinds
    state_stream(big)
    chunks(big)
    input_events(big)
    pairing()
    hello(small)
    status(small, big)
    auth()
    downlevel(big)
    contract_json()
    built = kit()
    maths()
    input_v2(built)
    state_v2(built)
    hello_v2(built, small)
    commit_v2(built)
    for name, built in (("small", small), ("all_cards", big)):
        print(
            name,
            built["compiled"]["hash"],
            built["compiled"]["size"],
            "bytes,",
            len(built["compiled"]["slots"]),
            "slots,",
            len(built["result"]["warnings"]),
            "warnings",
        )


if __name__ == "__main__":
    main()
