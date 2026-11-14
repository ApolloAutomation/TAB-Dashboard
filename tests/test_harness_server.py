"""Tests for the harness server's preview answers."""

import io
import json
from pathlib import Path

import pytest

from tests.harness.build_fixtures import _sample_dashboard
from tests.harness.server import (
    MAX_BODY,
    handle_facts_body,
    handle_preview_body,
    make_handler,
    preview_response,
)

HARNESS = Path(__file__).parent / "harness"


def test_preview_response_has_the_command_shape():
    """The answer matches apollo_tab/layout/preview and the fixtures."""
    answer = preview_response(_sample_dashboard())
    assert set(answer) == {"layout", "warnings", "values", "sources"}
    fixtures = json.loads((HARNESS / "fixtures.json").read_text(encoding="utf-8"))
    entry = fixtures["layout"]
    for key in ("layout", "warnings", "values", "sources"):
        assert answer[key] == entry[key], key
    for source in answer["sources"].values():
        assert len(source) == 3
    json.dumps(answer, allow_nan=False)


def test_preview_response_for_the_real_dashboard():
    """The owner's dashboard shows its heading and names the Bubble Card."""
    path = HARNESS / "real-dashboard.json"
    if not path.exists():
        pytest.skip("tests/harness/real-dashboard.json has not been added yet")
    answer = preview_response(json.loads(path.read_text(encoding="utf-8")))
    pages = answer["layout"]["pages"]
    assert [page["id"] for page in pages] == ["home"]
    assert [item["t"] for item in pages[0]["w"]] == ["heading"]
    assert answer["sources"] == {"1": [0, 0, 0]}
    [warning] = answer["warnings"]
    assert warning["code"] == "not_tab_element"
    assert (warning["view"], warning["section"], warning["card"]) == (0, 0, 1)
    assert warning["detail"] == "custom:bubble-card"


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not json",
        b"\xff\xfe\x00",
        b"[" * 100000,
        b"[]",
        b'"config"',
        b"{}",
        b'{"config": []}',
        b'{"config": "views: []"}',
        b'{"config": null}',
        b'{"config": {}, "padding": "' + b"x" * MAX_BODY + b'"}',
        b'{"config": {}, "dl": 3}',
        b'{"config": {}, "dl": true}',
        b'{"config": {}, "dl": "2"}',
    ],
)
def test_handle_preview_body_rejects_bad_input(body):
    """Bad JSON, a body over 1 MB or a config that is not an object give 400."""
    status, payload = handle_preview_body(body)
    assert status == 400
    assert isinstance(payload["error"], str)
    assert payload["error"]


def test_handle_preview_body_answers_a_good_request():
    """A config object is converted and answered with 200."""
    body = json.dumps({"config": _sample_dashboard()}).encode("utf-8")
    status, payload = handle_preview_body(body)
    assert status == 200
    assert payload == preview_response(_sample_dashboard())


def test_preview_asks_for_layout_version_2():
    """Asking for dl 2 makes layout version 2, as the editor asks for it."""
    body = json.dumps({"config": _sample_dashboard(), "dl": 2}).encode("utf-8")
    status, payload = handle_preview_body(body)
    assert status == 200
    assert payload["layout"]["v"] == 2
    assert preview_response(_sample_dashboard())["layout"]["v"] == 1


@pytest.mark.parametrize(("token", "expected"), [("run-1", [b"run-1"]), ("", [])])
def test_answers_carry_the_run_token(token, expected):
    """With a token every answer names it, so a run knows it reached its server."""
    handler = make_handler(token)
    request = handler.__new__(handler)
    request.request_version = "HTTP/1.1"
    request.wfile = io.BytesIO()
    request._headers_buffer = []
    request.end_headers()
    lines = request.wfile.getvalue().split(b"\r\n")
    assert b"Cache-Control: no-store" in lines
    prefix = b"X-Harness-Token: "
    found = [line[len(prefix) :] for line in lines if line.startswith(prefix)]
    assert found == expected


# The stand-in states of a colour lamp and an on/off lamp, as
# tests/harness/mock-hass.js gives them.
LAMPS = {
    "light.kitchen": {
        "state": "on",
        "attributes": {
            "supported_color_modes": ["hs", "color_temp"],
            "min_color_temp_kelvin": 2000,
            "max_color_temp_kelvin": 6535,
            "effect_list": ["Rainbow", "Candle"],
            "supported_features": 4,
        },
    },
    "light.living_room": {
        "state": "off",
        "attributes": {"supported_color_modes": ["onoff"]},
    },
}


def _facts(params, states=LAMPS):
    body = {"component": "apollo/light", "params": params, "states": states}
    return handle_facts_body(json.dumps(body).encode("utf-8"))


def test_facts_answer_reads_the_stand_in_states():
    """The facts of a lamp come from its state, as card/facts reads them."""
    status, payload = _facts({"entity": "light.kitchen"})
    assert status == 200
    can = payload["can"]
    assert (can["brightness"], can["colour"], can["temperature"]) == (True, True, True)
    assert (can["effects"], can["effect_list"]) == (True, ["Rainbow", "Candle"])
    assert payload["has"] == {"entity": True}
    status, payload = _facts({"entity": "light.living_room"})
    assert (payload["can"]["brightness"], payload["can"]["colour"]) == (False, False)
    # A device without a state, and no device at all.
    status, payload = _facts({"entity": "light.nowhere"})
    assert status == 200 and payload["can"]["brightness"] is False
    status, payload = _facts({})
    assert payload == {"can": {}, "has": {"entity": False}}


@pytest.mark.parametrize(
    "body",
    [
        b"[]",
        b'{"component": "apollo/nothing"}',
        b'{"component": "apollo/light", "params": {"other": "light.a"}}',
        b'{"component": "apollo/light", "params": []}',
        b'{"component": "apollo/light", "states": []}',
    ],
)
def test_facts_body_rejects_bad_input(body):
    """An unknown card or param, or a bad shape, gives 400."""
    status, payload = handle_facts_body(body)
    assert status == 400 and payload["error"]


def test_preview_reads_facts_from_the_states():
    """A colour lamp's card is drawn with its colour bar, an on/off lamp's not."""

    def tracks(entity):
        card = {
            "type": "custom:apollo-tab-card",
            "component": "apollo/light",
            "params": {"entity": entity},
            "variant": "wide",
            "grid_options": {"columns": 12, "rows": 3},
        }
        config = {
            "apollo_tab": {"version": 1},
            "views": [
                {
                    "title": "Home",
                    "type": "sections",
                    "sections": [{"type": "grid", "cards": [card]}],
                }
            ],
        }
        layout = preview_response(config, 2, LAMPS)["layout"]
        cards = layout["pages"][0]["w"]
        widgets = [w for card in cards for w in card.get("w", [])]
        return sum(1 for w in widgets if w.get("t") == "slider" and "track" in w)

    assert tracks("light.kitchen") == 1
    assert tracks("light.living_room") == 0
