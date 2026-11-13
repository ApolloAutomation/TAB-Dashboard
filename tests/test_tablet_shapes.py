"""The tablet websocket messages follow the shared shapes file.

tests/harness/tablet-shapes.json describes every websocket message about
tablets. This test checks the integration against it; the node test
tests/frontend/tablet-shapes.test.mjs checks the panel's stand-in Home
Assistant against the same file. A change on one side that the other side
does not make fails one of the two.
"""

import ast
import json
import re
from pathlib import Path
from typing import Any

import homeassistant
from homeassistant.components.websocket_api.const import DOMAIN as WS_DOMAIN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.apollo_tab import protocol as tp, sender as sender_module
from custom_components.apollo_tab.assignments import APPROVAL_NEEDED, ApprovalNeeded
from custom_components.apollo_tab.websocket import NOT_APPROVED

from .conftest import MakeTablet, SaveTabDashboard, setup_integration, until

SHAPES = json.loads(
    (Path(__file__).parent / "harness" / "tablet-shapes.json").read_text(
        encoding="utf-8"
    )
)
COMPONENT = Path(__file__).parent.parent / "custom_components" / "apollo_tab"
CONTRACT = json.loads(
    (COMPONENT / "contract" / "contract.json").read_text(encoding="utf-8")
)
TRANSLATIONS = json.loads(
    (COMPONENT / "translations" / "en.json").read_text(encoding="utf-8")
)
STRINGS = json.loads(
    (COMPONENT / "library" / "strings.json").read_text(encoding="utf-8")
)

LIGHT = {
    "type": "custom:apollo-tab-card",
    "component": "apollo/light-tile",
    "params": {"entity": "light.kitchen"},
}


def tab_config(title: str) -> dict:
    """Return a TAB-1 dashboard config with one light tile."""
    return {
        "apollo_tab": {"version": 1, "theme": "midnight"},
        "views": [
            {
                "type": "sections",
                "path": "home",
                "title": title,
                "max_columns": 3,
                "sections": [{"type": "grid", "cards": [LIGHT]}],
            }
        ],
    }


# ------------------------------------------------------------- the checks


def _type_ok(value: Any, name: str) -> bool:
    """Return whether value has the JSON type name."""
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    if name == "null":
        return value is None
    raise AssertionError(f"unknown type {name} in the shapes file")


def check_fields(where: str, value: Any, fields: dict) -> None:
    """Check exact keys, types, patterns and lists of values."""
    assert isinstance(value, dict), f"{where} is not an object: {value!r}"
    assert set(value) == set(fields), f"{where} has the keys {sorted(value)}"
    for key, rule in fields.items():
        item = value[key]
        types = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
        assert any(_type_ok(item, name) for name in types), f"{where}.{key}: {item!r}"
        if isinstance(item, str) and "pattern" in rule:
            assert re.search(rule["pattern"], item), f"{where}.{key}: {item!r}"
        if isinstance(item, str) and "values" in rule:
            assert item in SHAPES[rule["values"]], f"{where}.{key}: {item!r}"
        if isinstance(item, list) and rule.get("items") == "mac":
            for mac in item:
                assert isinstance(mac, str), f"{where}.{key}: {mac!r}"
                assert re.search(SHAPES["tablet"]["mac"]["pattern"], mac), mac


def short_names(name: str) -> set[str]:
    """Return the short names the rule allows for a name."""
    strip = SHAPES["short_name"]["strip"]

    def without(text: str) -> str:
        if text.lower().endswith(strip) and len(text) > len(strip):
            return text[: -len(strip)]
        return text

    allowed = {without(name)}
    if tag := re.search(SHAPES["short_name"]["tag"], name):
        allowed.add(without(name[: tag.start()]) + tag.group(0))
    return allowed


def check_tablet(where: str, tablet: Any) -> None:
    """Check one Tablet against every rule of the shapes file."""
    check_fields(where, tablet, SHAPES["tablet"])
    status, reason, retry = tablet["status"], tablet["reason"], tablet["retry"]
    reasons = SHAPES["reasons"].get(status)
    if reasons is None:
        assert reason == "", f"{where}: {status} with the reason {reason!r}"
    else:
        assert reason in reasons, f"{where}: {status} with the reason {reason!r}"
    if status != "failed" or reason in SHAPES["no_retry"]:
        assert retry is False, f"{where}: {status} {reason} with retry"
    if status == "no_dashboard":
        assert tablet["dashboard"] is None, where
    if tablet["approved"]:
        assert status != "new", where
        assert tablet["suggested"] is None, where
    else:
        assert status == "new", where
        assert tablet["dashboard"] is None, where
        assert tablet["paired"] is False, where
        assert tablet["input"] == "not_paired", where
    assert tablet["short_name"] in short_names(tablet["name"]), where
    assert (tablet["reauth"] is None) == (tablet["reauth_name"] is None), where


def check_tablet_list(where: str, tablets: Any) -> None:
    """Check a list of tablets: each one, the order, unique MACs."""
    assert isinstance(tablets, list), where
    for index, tablet in enumerate(tablets):
        check_tablet(f"{where}[{index}]", tablet)
    keys = [(tablet["name"].lower(), tablet["mac"]) for tablet in tablets]
    assert keys == sorted(keys), f"{where} is not in name order: {keys}"
    macs = [tablet["mac"] for tablet in tablets]
    assert len(set(macs)) == len(macs), where


def check_dashboards(where: str, result: Any, tablets: list[dict]) -> None:
    """Check apollo_tab/dashboards against the tablet list of the moment."""
    for index, dashboard in enumerate(result["dashboards"]):
        check_fields(f"{where}[{index}]", dashboard, SHAPES["dashboard"])
        shown = sorted(
            t["mac"] for t in tablets if t["dashboard"] == dashboard["url_path"]
        )
        assert dashboard["shown_on"] == shown, f"{where}[{index}].shown_on"
    keys = [(d["title"].lower(), d["url_path"]) for d in result["dashboards"]]
    assert keys == sorted(keys), f"{where} is not in title order: {keys}"
    assert result["tablets"] == len([t for t in tablets if t["approved"]])
    assert result["sent_to_tablets"] == any(t["status"] == "on_tablet" for t in tablets)


def check_value(where: str, kind: Any, value: Any) -> None:
    """Check a value named in the commands section."""
    if kind == "tablet":
        check_tablet(where, value)
    elif kind == "tablet_list":
        check_tablet_list(where, value)
    elif kind == "dashboard_list":
        assert isinstance(value, list), where
    elif kind in ("integer", "boolean", "string"):
        assert _type_ok(value, kind), f"{where}: {value!r}"
    elif isinstance(kind, str):
        assert value == kind, f"{where}: {value!r}"
    else:
        raise AssertionError(f"unknown kind {kind!r} in the shapes file")


def check_result(command: str, result: Any) -> None:
    """Check a command's result against the shapes file."""
    shape = SHAPES["commands"][command]["result"]
    if shape is None:
        assert result is None, command
        return
    assert isinstance(result, dict), command
    assert set(result) == set(shape), f"{command} result keys {sorted(result)}"
    for key, kind in shape.items():
        check_value(f"{command}.{key}", kind, result[key])


def check_event(command: str, event: Any) -> None:
    """Check one subscription event against the shapes file."""
    events = SHAPES["commands"][command]["events"]
    assert isinstance(event, dict), command
    shape = events.get(event.get("type"))
    assert shape is not None, f"{command} sent the event {event!r}"
    assert set(event) == set(shape), f"{command} event keys {sorted(event)}"
    for key, kind in shape.items():
        check_value(f"{command} event.{key}", kind, event[key])


# --------------------------------------------------------------- the tests


def test_the_shapes_file_matches_the_integration() -> None:
    """Every list in the shapes file is the integration's own list."""
    constants = vars(sender_module)
    statuses = {
        value
        for name, value in constants.items()
        if name.startswith("STATUS_") and isinstance(value, str)
    }
    inputs = {
        value
        for name, value in constants.items()
        if name.startswith("INPUT_") and isinstance(value, str)
    }
    assert set(SHAPES["statuses"]) == statuses
    assert len(SHAPES["statuses"]) == len(statuses)
    assert set(SHAPES["inputs"]) == inputs
    assert SHAPES["reauths"] == list(sender_module.REAUTH_KINDS)
    assert set(SHAPES["no_retry"]) == sender_module.NO_RETRY
    failed = set(SHAPES["reasons"]["failed"])
    for codes in CONTRACT["errors"].values():
        assert set(codes) <= failed
    assert {code for code in CONTRACT["build_codes"] if code} <= failed
    assert set(CONTRACT["deterministic_errors"]) <= set(SHAPES["no_retry"])
    assert set(SHAPES["no_retry"]) <= failed
    assert {"tablet_old", "tablet_new"} == {
        tp.proto_verdict({"proto": [0, 0]}),
        tp.proto_verdict({"proto": [99, 99]}),
    }
    assert set(SHAPES["reasons"]["unsupported"]) == {
        "tablet_old",
        "tablet_new",
        "ha_version",
    }
    check_tablet("example", SHAPES["example"])


# The agreed words (design 10.9 D4, round 8 D-f): the two steps, the
# button's name in quotes and a full stop, as the panel's own lines.
AGREED_APPROVAL_NEEDED = (
    "An admin must turn this tablet on first: in the TAB-1 panel, pick a "
    'dashboard for it, then press "Turn on with this dashboard".'
)
AGREED_NOT_APPROVED = (
    "This tablet is new. Pick a dashboard for it on the Home screen, then "
    'press "Turn on with this dashboard".'
)


def test_the_approval_answers_use_the_agreed_words() -> None:
    """APPROVAL_NEEDED and NOT_APPROVED are the agreed words, everywhere.

    APPROVAL_NEEDED is what add-ons get from the panel command and what the
    action's error says; NOT_APPROVED answers a change from an old screen.
    """
    assert APPROVAL_NEEDED == AGREED_APPROVAL_NEEDED
    assert NOT_APPROVED == AGREED_NOT_APPROVED
    assert TRANSLATIONS["exceptions"]["approval_needed"]["message"] == APPROVAL_NEEDED
    assert str(ApprovalNeeded()) == APPROVAL_NEEDED
    for name in ("apollo_tab/tablet/assign", "apollo_tab/tablet/pair"):
        assert SHAPES["commands"][name]["errors"]["not_approved"] == NOT_APPROVED
    ending = f'press "{STRINGS["tablets.turn_on"]}".'
    for text in (APPROVAL_NEEDED, NOT_APPROVED, STRINGS["editor.on_tablet_new"]):
        assert text.endswith(ending), text


def test_the_erased_line_says_what_home_assistant_asks() -> None:
    """The erased tablet's line and the guide name the question of this HA.

    ESPHome's step for a device that came back without its key asks to
    "remove the encryption key and allow unencrypted connections". The guide
    quotes it; the panel's line is short (round 9) and names the Repairs
    entry, "Authentication expired for <name>", which the link opens.
    """
    # Read from the installed Home Assistant without importing ESPHome.
    esphome_dir = Path(homeassistant.__file__).parent / "components" / "esphome"
    esphome = json.loads(
        (esphome_dir / "translations" / "en.json").read_text(encoding="utf-8")
    )
    steps = esphome["config"]["step"]
    question = steps[sender_module.ESPHOME_ERASED_STEP]["description"]
    words = "remove the encryption key and allow unencrypted connections"
    assert words in question
    guide = COMPONENT.parent.parent / "docs" / "tablets.md"
    docs = " ".join(guide.read_text(encoding="utf-8").split())
    assert f'"{words}"' in docs
    for key in ("tablets.reauth_erased", "tablets.reauth_key"):
        assert '"Authentication expired for {name}"' in STRINGS[key]
    # The question for a key has a key field: the panel says not to fill it,
    # to anyone, before any step (round 10).
    assert "noise_psk" in steps["reauth_confirm"]["data"]
    key_line = STRINGS["tablets.reauth_key"]
    assert "Do not enter a key." in key_line
    assert key_line.index("Do not enter a key.") < key_line.index("close the question")


def test_the_erased_line_checks_the_screen_an_erased_tablet_shows() -> None:
    """The panel and the guide name the tablet's own screens (round 11).

    The words come from the shared contract (tests/contract/screens.json,
    CONTRACT.md section 11), which TAB-1 checks against its firmware. After
    the hold-the-screen erase the tablet says "Confirm this tablet in Home
    Assistant" until it has a key again; only a tablet erased over USB says
    "Add this tablet in Home Assistant"; "Setup not finished" once its 15
    minutes ran out. A line that names another screen tells the admin not
    to confirm while the tablet tells them to.
    """
    screens = json.loads(
        (Path(__file__).parent / "contract" / "screens.json").read_text(
            encoding="utf-8"
        )
    )
    waiting = screens["waiting"]
    erased_screen = waiting["erased"]["headline"]
    add_screen = waiting["add"]["headline"]
    closed_screen = waiting["closed"]["headline"]
    erased = STRINGS["tablets.reauth_erased"]
    check = (
        f'its screen says "{erased_screen}" ("{add_screen}" after a USB erase): '
        'confirm "Authentication expired for {name}"'
    )
    assert check in erased
    assert f'"{closed_screen}": restart it first.' in erased
    assert f'its screen says "{closed_screen}"' in STRINGS["tablets.reauth_key"]
    guide = COMPONENT.parent.parent / "docs" / "tablets.md"
    docs = " ".join(
        re.sub(r"^> ", "", guide.read_text(encoding="utf-8"), flags=re.M).split()
    )
    assert (
        f'shows its waiting screen with its name, for example "Apollo TAB-1 '
        f'ddee01": "{waiting["hotspot"]["headline"]}" until it is on your '
        f'Wi-Fi, then "{erased_screen}".'
    ) in docs
    assert (
        f'once the tablet\'s screen says "{erased_screen}" (or "{add_screen}" '
        "after a USB erase)."
    ) in docs


def _function_source(path: Path, name: str) -> str:
    """Return the source of the function `name` in the Python file `path`."""
    source = path.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and (
            node.name == name
        ):
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"{name} is not in {path}")


def test_a_yes_after_an_erase_gives_back_the_kept_key() -> None:
    """The panel and the guide say what Home Assistant gives after a yes.

    Round 9: after the erased question is confirmed, ESPHome connects
    without a key and gives the tablet the key it kept for that device
    (`_handle_dynamic_encryption_key`): it makes a new one only when it
    kept none, and stores only a new one. The tablet gets its old key back,
    so a device that pretends to be the tablet would get that key; the words
    never promise a new one.
    """
    manager = Path(homeassistant.__file__).parent / "components" / "esphome"
    body = _function_source(manager / "manager.py", "_handle_dynamic_encryption_key")
    flat = " ".join(body.split())
    kept = flat.index("stored_key := await storage.async_get_key(self.entry.unique_id)")
    assert flat.index("new_key_str = stored_key") > kept
    assert flat.index("from_storage = True") > kept
    assert "if not from_storage: await storage.async_store_key(" in flat
    erased = STRINGS["tablets.reauth_erased"]
    assert '{name}"; it gets its old key back.' in erased
    guide = COMPONENT.parent.parent / "docs" / "tablets.md"
    docs = " ".join(guide.read_text(encoding="utf-8").split())
    assert (
        "Home Assistant then gives the tablet back the key it kept for it: the "
        "same key the tablet had before the erase, not a new one." in docs
    )
    for text in (erased, STRINGS["tablets.reauth_key"], docs):
        assert "new key" not in text


def test_the_action_says_what_the_panel_says() -> None:
    """The show_dashboard action and the websocket use the same plain words."""
    exceptions = TRANSLATIONS["exceptions"]
    errors = SHAPES["commands"]["apollo_tab/tablet/assign"]["errors"]
    assert exceptions["unknown_tablet"]["message"] == errors["not_found"]
    assert exceptions["unknown_dashboard"]["message"] == errors["unknown_dashboard"]
    # The action's field names the setting as the editor shows it.
    field = TRANSLATIONS["services"]["show_dashboard"]["fields"]["dashboard"]
    assert STRINGS["editor.on_tablet_name"] in field["description"]
    assert STRINGS["settings.heading"] in field["description"]


async def test_the_integration_sends_the_shared_shapes(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    hass_ws_client: ClientSessionGenerator,
    make_tablet: MakeTablet,
    save_tab_dashboard: SaveTabDashboard,
) -> None:
    """Every tablet command and event, in many states, has the shared shape."""
    hass.states.async_set("light.kitchen", "off", {"friendly_name": "Kitchen"})
    make_tablet(mac="AA:BB:CC:DD:EE:01", name="Kitchen Tablet")
    hall = make_tablet(mac="AA:BB:CC:DD:EE:02", name="Hall Tablet")
    bedroom = make_tablet(mac="AA:BB:CC:DD:EE:03", name="Bedroom Tablet")
    make_tablet(mac="AA:BB:CC:DD:EE:04", name="Den Tablet", psk=None)
    make_tablet(mac="AA:BB:CC:DD:EE:05", name="Office Tablet", proto=(0, 0))
    make_tablet(mac="AA:BB:CC:DD:EE:06", name="Garage Tablet", proto=(2, 3))
    make_tablet(mac="AA:BB:CC:DD:EE:07", name="Attic Tablet", caps={"max_layout": 200})
    make_tablet(mac="AA:BB:CC:DD:EE:08", name="Loft Tablet")
    make_tablet(mac="AA:BB:CC:DD:EE:09", name="Loft Tablet")
    porch = make_tablet(mac="AA:BB:CC:DD:EE:0A", name="Porch Tablet", approved=False)
    hall.connected = False
    bedroom.has_engine = False
    await setup_integration(hass, config_entry)
    sender = config_entry.runtime_data.sender
    client = await hass_ws_client(hass)
    commands = SHAPES["commands"]

    async def command(message: dict) -> dict:
        await client.send_json_auto_id(message)
        response = await client.receive_json()
        while response.get("type") == "event":
            events.append(response["event"])
            response = await client.receive_json()
        return response

    events: list[dict] = []
    response = await command({"type": "apollo_tab/tablets/subscribe"})
    assert response["success"], response
    check_result("apollo_tab/tablets/subscribe", response["result"])
    subscription = response["id"]

    def statuses() -> dict[str, tuple[str, str]]:
        return {
            mac[-2:]: (session.status, session.reason)
            for mac, session in sender.sessions.items()
        }

    # No dashboards yet.
    await until(
        hass,
        lambda: (
            statuses()
            == {
                "01": ("no_dashboard", ""),
                "02": ("offline", ""),
                "03": ("no_engine", ""),
                "04": ("no_dashboard", ""),
                "05": ("unsupported", "tablet_old"),
                "06": ("unsupported", "tablet_new"),
                "07": ("no_dashboard", ""),
                "08": ("no_dashboard", ""),
                "09": ("no_dashboard", ""),
                "0a": ("new", ""),
            }
        ),
    )
    response = await command({"type": "apollo_tab/tablets"})
    check_result("apollo_tab/tablets", response["result"])
    tablets = response["result"]["tablets"]
    names = {t["mac"][-2:]: (t["name"], t["short_name"]) for t in tablets}
    assert names["08"] == ("Loft Tablet (ee08)", "Loft (ee08)")
    assert names["01"] == ("Kitchen Tablet", "Kitchen")
    inputs = {t["mac"][-2:]: (t["input"], t["paired"]) for t in tablets}
    assert inputs["04"] == ("needs_encryption", False)
    assert inputs["01"] == ("ok", True)
    response = await command({"type": "apollo_tab/dashboards"})
    check_result("apollo_tab/dashboards", response["result"])
    check_dashboards("dashboards", response["result"], tablets)

    # Two dashboards; the first one made goes to every tablet.
    await save_tab_dashboard("tab-z-home", tab_config("Home"), title="Home")
    await save_tab_dashboard("tab-a-night", tab_config("Night"), title="Night")
    await until(
        hass,
        lambda: (
            statuses()
            == {
                "01": ("on_tablet", ""),
                "02": ("offline", ""),
                "03": ("no_engine", ""),
                "04": ("on_tablet", ""),
                "05": ("unsupported", "tablet_old"),
                "06": ("unsupported", "tablet_new"),
                "07": ("failed", "too_big"),
                "08": ("on_tablet", ""),
                "09": ("on_tablet", ""),
                "0a": ("new", ""),
            }
        ),
    )
    # The tablet nobody approved heard nothing at all.
    assert porch.calls == []
    response = await command({"type": "apollo_tab/tablets"})
    check_result("apollo_tab/tablets", response["result"])
    tablets = response["result"]["tablets"]
    response = await command({"type": "apollo_tab/dashboards"})
    check_result("apollo_tab/dashboards", response["result"])
    check_dashboards("dashboards", response["result"], tablets)
    assert [d["url_path"] for d in response["result"]["dashboards"]] == [
        "tab-z-home",
        "tab-a-night",
    ]
    assert len(response["result"]["dashboards"][0]["shown_on"]) == 9
    assert response["result"]["tablets"] == 9

    # Assign and pair, by either form of the MAC.
    response = await command(
        {
            "type": "apollo_tab/tablet/assign",
            "mac": "AA:BB:CC:DD:EE:01",
            "url_path": "tab-a-night",
        }
    )
    assert response["success"], response
    check_result("apollo_tab/tablet/assign", response["result"])
    assert response["result"]["tablet"]["dashboard"] == "tab-a-night"
    response = await command(
        {"type": "apollo_tab/tablet/pair", "mac": "aa:bb:cc:dd:ee:08"}
    )
    assert response["success"], response
    check_result("apollo_tab/tablet/pair", response["result"])

    # Errors: the codes and the plain messages.
    macs = {"not_found": "aa:00:00:00:00:00", "not_approved": "aa:bb:cc:dd:ee:0a"}
    for name, shape in commands.items():
        for code, text in shape.get("errors", {}).items():
            message = {
                "type": name,
                "mac": macs.get(code, "aa:bb:cc:dd:ee:01"),
                "url_path": "nope",
            }
            message = {key: message[key] for key in ["type", *shape["send"]]}
            response = await command(message)
            assert response["error"] == {"code": code, "message": text}, name
    assert porch.calls == []

    # The arguments are exactly those listed: one missing or one more fails,
    # and an optional one of another type fails.
    for name, shape in commands.items():
        full = {"mac": "aa:bb:cc:dd:ee:01", "url_path": "tab-z-home"}
        message = {"type": name, **{key: full[key] for key in shape["send"]}}
        response = await command({**message, "allow_sensitive": True})
        assert response["error"]["code"] == "invalid_format", name
        for key in shape["send"]:
            response = await command({k: v for k, v in message.items() if k != key})
            assert response["error"]["code"] == "invalid_format", (name, key)
        for key, kind in shape.get("optional", {}).items():
            assert kind == "boolean", (name, key)
            response = await command({**message, key: "yes"})
            assert response["error"]["code"] == "invalid_format", (name, key)
            response = await command({**message, key: False})
            assert response["success"], (name, key, response)

    # Removed commands are gone, and the integration has no tablet command
    # the shapes file does not list.
    for name in SHAPES["removed"]:
        response = await command({"type": name, "mac": "aa:bb:cc:dd:ee:01"})
        assert response["error"]["code"] == SHAPES["unknown_command"], name
    registered = {
        name for name in hass.data[WS_DOMAIN] if name.startswith("apollo_tab/tablet")
    }
    assert registered == {
        name for name in commands if name.startswith("apollo_tab/tablet")
    }

    # The admin picks a dashboard for the new tablet and presses Turn on:
    # that approves it.
    response = await command(
        {
            "type": "apollo_tab/tablet/assign",
            "mac": "aa:bb:cc:dd:ee:0a",
            "url_path": "tab-a-night",
            "approve": True,
        }
    )
    assert response["success"], response
    check_result("apollo_tab/tablet/assign", response["result"])
    assert response["result"]["tablet"]["approved"] is True
    assert response["result"]["tablet"]["dashboard"] == "tab-a-night"

    # Every event so far, then the last one at unload.
    await until(
        hass,
        lambda: (
            sender.sessions["aa:bb:cc:dd:ee:01"].status == "on_tablet"
            and sender.sessions["aa:bb:cc:dd:ee:0a"].status == "on_tablet"
            and porch.paired
        ),
    )
    response = await command({"type": "apollo_tab/tablets"})
    check_result("apollo_tab/tablets", response["result"])
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    while not events or events[-1].get("type") != "not_loaded":
        message = await client.receive_json()
        assert message["id"] == subscription
        events.append(message["event"])
    assert len(events) > 3
    for event in events:
        check_event("apollo_tab/tablets/subscribe", event)
    assert {event["type"] for event in events} == set(
        commands["apollo_tab/tablets/subscribe"]["events"]
    )
