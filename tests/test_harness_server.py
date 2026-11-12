"""Tests for the harness server's preview answers."""

import io
import json
from pathlib import Path

import pytest

from tests.harness.build_fixtures import _sample_dashboard
from tests.harness.server import (
    MAX_BODY,
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
