"""Write the golden fixtures of contract v1.

Usage: python -B gen_fixtures.py <path to custom_components/apollo_tab> <contract dir>

Reads the integration's maker package and card library (nothing is written
there) and writes <contract dir>/contract.json and <contract dir>/fixtures/*.
Run it again only when the contract changes; both builds copy the output.
"""

import json
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
                    **whole({**device, "v": 2}),
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
                    "response": {**base, "proto": [2, 3]},
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
    (OUT / "contract.json").write_text(
        json.dumps(
            {
                "proto": tp.PROTO,
                "dl_version": tp.DL_VERSION,
                "limits": {
                    "chunk_bytes": tp.CHUNK_BYTES,
                    "max_layout_bytes": tp.MAX_LAYOUT_BYTES,
                    "max_set_bytes": tp.MAX_SET_BYTES,
                    "max_text_bytes": tp.MAX_TEXT_BYTES,
                    "max_list": tp.MAX_LIST,
                    "max_number": tp.MAX_NUMBER,
                    "max_pages": tp.MAX_PAGES,
                    "max_nav": tp.MAX_NAV,
                    "max_slots": tp.MAX_SLOTS,
                    "max_widgets": tp.MAX_WIDGETS,
                    "max_input_payload": 200,
                },
                "caps_defaults": {"w": list(tp.WIDGET_KINDS), **tp.CAPS_DEFAULTS},
                "fonts": {
                    "text_px": [14, 15, 16, 18, 20, 34],
                    "digits_px": [48],
                    "digits_glyphs": "0123456789.,-",
                    "icon_px": [24, 28, 48, 72],
                    # Code point ranges [first, last] of the text sizes: Latin,
                    # Latin-1, Latin Extended-A, dashes, quotes, bullet,
                    # ellipsis, euro. Any other character is an empty box.
                    "text_glyphs": [
                        [0x20, 0x7E],
                        [0xA0, 0x17F],
                        [0x2013, 0x2014],
                        [0x2018, 0x2019],
                        [0x201C, 0x201D],
                        [0x2022, 0x2022],
                        [0x2026, 0x2026],
                        [0x20AC, 0x20AC],
                    ],
                },
                "knock": {
                    "first_s": tp.KNOCK_FIRST_S,
                    "repeats": tp.KNOCK_REPEATS,
                    "max_s": tp.KNOCK_MAX_S,
                },
                "timing": {
                    "call_timeout_s": 10,
                    "status_poll_s": [0.15, 0.3, 0.5],
                    "status_poll_limit_s": 20,
                    "ack_timeout_s": 4,
                    "progress_timeout_s": 30,
                    "retry_s": [5, 15, 60, 300],
                    "repair_once_per_s": 60,
                },
                "widget_kinds": list(tp.WIDGET_KINDS),
                "slot_types": {
                    "t": "text",
                    "b": "bool as 0 or 1",
                    "n": "number",
                    "l": "list of numbers",
                    "i": "icon code point, 0 for the placeholder",
                },
                "policies": list(tp.POLICIES),
                "label_sizes": list(tp.LABEL_SIZES),
                "chart_kinds": list(tp.CHART_KINDS),
                "theme_colours": list(tp.THEME_COLOURS),
                "style_colours": list(tp.STYLE_COLOURS),
                "actions": {
                    "tab_hello": {
                        "args": {"nonce": "string", "auth": "string"},
                        "response": "only",
                    },
                    "tab_status": {"args": {}, "response": "only"},
                    "tab_pair": {
                        "args": {"nonce": "string", "wrapped": "string", "kid": "string"},
                        "response": "status",
                    },
                    "tab_layout": {
                        "args": {
                            "hash": "string",
                            "seq": "int",
                            "total": "int",
                            "size": "int",
                            "data": "string",
                        },
                        "response": "status",
                    },
                    "tab_commit": {
                        "args": {"hash": "string", "auth": "string"},
                        "response": "status",
                    },
                    "tab_set": {
                        "args": {"data": "string", "auth": "string"},
                        "response": "status",
                    },
                    "tab_ack": {
                        "args": {"n": "int", "ok": "bool", "code": "string", "auth": "string"},
                        "response": "none",
                    },
                    "tab_clear": {"args": {"auth": "string"}, "response": "status"},
                },
                "events": {
                    "esphome.tab1_hello": {"d": "1|<mac>|<boot>"},
                    "esphome.tab1_input": {"d": "<payload>", "s": "<signature>"},
                },
                "errors": {
                    "tab_pair": ["needs_encryption", "bad_key"],
                    "tab_layout": ["order", "size", "too_big", "memory"],
                    "tab_commit": [
                        "auth", "incomplete", "hash", "parse", "version", "limits", "memory",
                    ],
                    "tab_set": ["auth", "hash", "parse"],
                    "tab_clear": ["auth"],
                },
                "build_codes": ["", "memory", "build"],
                "deterministic_errors": list(tp.DETERMINISTIC_ERRORS),
                "ack_codes": ["", "confirm", "denied", "failed", "stale", "busy"],
                "labels": {
                    "kid": tp.KID_LABEL.decode(),
                    "wrap": tp.WRAP_LABEL,
                    "call": tp.CALL_LABEL,
                },
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
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
