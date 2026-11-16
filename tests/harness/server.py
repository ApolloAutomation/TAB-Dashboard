"""Serve the browser harness and convert dashboard drafts like the integration.

Run from the repository root with the test environment's Python, because the
converter is imported from the integration package:

    python -B tests/harness/server.py [--port 8765] [--bind 127.0.0.1] [--token T]

GET serves files from the repository. POST /api/preview with {"config": {...}}
answers with what apollo_tab/layout/preview would send, using the bundled
cards and one card as from the user's folder (FIVE_GRAPHS), no approved cards
and stand-in values instead of real states. POST /api/facts with
{"component", "params"} answers as apollo_tab/card/facts would. Both take
"states", the stand-in Home Assistant's states, and read what each device
can do from them as the integration reads it from Home Assistant.

--port 0 lets the system choose a free port; the first line printed names
it. With --token, every answer carries it in an X-Harness-Token header, so
the scripted browser run can tell this server from one left over from an
earlier run.
"""

import argparse
import functools
import json
import sys
import traceback
import urllib.parse
from contextlib import suppress
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The repository's own modules are imported below, so make them importable
# and keep Python from writing caches into the repository.
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custom_components.apollo_tab.facts import _feature_names  # noqa: E402
from custom_components.apollo_tab.library import _read_status  # noqa: E402
from custom_components.apollo_tab.maker.convert import convert_dashboard  # noqa: E402
from custom_components.apollo_tab.maker.features import (  # noqa: E402
    card_facts,
    entities_of,
    facts_of,
    param_entities,
)
from custom_components.apollo_tab.maker.schema import validate_component  # noqa: E402
from custom_components.apollo_tab.protocol import load_contract  # noqa: E402
from tests.harness.build_fixtures import (  # noqa: E402
    load_components,
    load_theme_entries,
    render_slots,
    renderer,
)

MAX_BODY = 1024 * 1024
PREVIEW_PATH = "/api/preview"
FACTS_PATH = "/api/facts"
TOKEN_HEADER = "X-Harness-Token"
TOO_LARGE = "The request is larger than 1 MB"

# A card as from the user's folder with five graphs, one more than a screen
# takes: the tablet leaves it out even when it is alone on its page. The
# stand-in Home Assistant lists it with graphs=1 (tests/harness/mock-hass.js).
FIVE_GRAPHS = {
    "id": "me/five-graphs",
    "name": "Five graphs",
    "description": "One sensor as five lines.",
    "icon": "mdi:chart-line",
    "version": "1.0.0",
    "size": "2x2",
    "params": {"entity": {"domain": "sensor"}},
    "inputs": {
        "history": {"source": "recorder", "entity": "{{ entity }}", "hours": 24}
    },
    "layout": [{"type": "chart", "value": "history"} for _ in range(5)],
}


@functools.cache
def _library() -> tuple[dict, dict]:
    """Return the cards and themes by id, loaded once."""
    themes = {entry["id"]: entry for entry in load_theme_entries()}
    components = load_components()
    five = validate_component(FIVE_GRAPHS)
    five["source"] = "user"
    components[five["id"]] = five
    return components, themes


@functools.cache
def _icons_and_status() -> tuple[dict, dict]:
    """Return the contract's icons and the status colours, loaded once."""
    return load_contract()[1], _read_status()


def harness_facts(entity_ids, states: dict | None) -> dict:
    """Return the facts of each device the stand-in states know.

    A state is read as facts.py::raw_of reads Home Assistant's: its
    attributes, and its supported_features as the names of the flags. A
    device without a state is left out, so it gets the least.
    """
    out = {}
    for entity_id in entity_ids:
        state = (states or {}).get(entity_id)
        if not isinstance(state, dict) or "." not in entity_id:
            continue
        attributes = state.get("attributes")
        attributes = attributes if isinstance(attributes, dict) else {}
        domain = entity_id.split(".", 1)[0]
        out[entity_id] = facts_of(
            {
                "domain": domain,
                "registry": None,
                "state": {
                    "attributes": attributes,
                    "features": _feature_names(
                        domain, attributes.get("supported_features")
                    ),
                },
            }
        )
    return out


def preview_response(config: dict, dl: int = 1, states: dict | None = None) -> dict:
    """Convert a dashboard config and return the preview command's answer.

    dl is the layout version to make, as apollo_tab/layout/preview takes it.
    states are the stand-in states the devices' facts are read from.
    """
    components, themes = _library()
    icons, status = _icons_and_status()
    result = convert_dashboard(
        config,
        components=components,
        themes=themes,
        approved=set(),
        facts=harness_facts(entities_of(config, components), states),
        dl=dl,
        icons=icons,
        status=status,
    )
    return {
        "layout": result["layout"],
        "warnings": result["warnings"],
        "values": render_slots(result["bindings"]["slots"], renderer()),
        "sources": result["sources"],
    }


def facts_response(component_id: str, params: dict, states: dict | None) -> dict:
    """Return what apollo_tab/card/facts answers for one card."""
    components, _themes = _library()
    component = components[component_id]
    entities = param_entities(component, params)
    entity_ids = list(dict.fromkeys(e for ids in entities.values() for e in ids))
    return card_facts(component, params, harness_facts(entity_ids, states))


def _read_body(body: bytes) -> tuple[int, dict] | dict:
    """Return the request's JSON object, or the error answer."""
    if len(body) > MAX_BODY:
        return HTTPStatus.BAD_REQUEST, {"error": TOO_LARGE}
    try:
        data = json.loads(body)
    except ValueError, RecursionError:
        return HTTPStatus.BAD_REQUEST, {"error": "The request is not valid JSON"}
    if not isinstance(data, dict):
        return HTTPStatus.BAD_REQUEST, {"error": "The request must be a JSON object"}
    states = data.get("states")
    if states is not None and not isinstance(states, dict):
        return HTTPStatus.BAD_REQUEST, {"error": "states must be a JSON object"}
    return data


def handle_facts_body(body: bytes) -> tuple[int, dict]:
    """Return the HTTP status and JSON answer for one facts request body."""
    data = _read_body(body)
    if isinstance(data, tuple):
        return data
    components, _themes = _library()
    component_id = data.get("component")
    params = data.get("params", {})
    if not isinstance(component_id, str) or component_id not in components:
        return HTTPStatus.BAD_REQUEST, {"error": "Unknown card"}
    if not isinstance(params, dict) or any(
        name not in components[component_id]["params"] for name in params
    ):
        return HTTPStatus.BAD_REQUEST, {"error": "Unknown param"}
    return HTTPStatus.OK, facts_response(component_id, params, data.get("states"))


def handle_preview_body(body: bytes) -> tuple[int, dict]:
    """Return the HTTP status and JSON answer for one preview request body."""
    data = _read_body(body)
    if isinstance(data, tuple):
        return data
    if not isinstance(data.get("config"), dict):
        return HTTPStatus.BAD_REQUEST, {"error": "config must be a JSON object"}
    dl = data.get("dl", 1)
    if dl not in (1, 2) or isinstance(dl, bool):
        return HTTPStatus.BAD_REQUEST, {"error": "dl must be 1 or 2"}
    try:
        return HTTPStatus.OK, preview_response(data["config"], dl, data.get("states"))
    except Exception:
        # The converter never raises for bad dashboards, so this is a bug;
        # print it and answer the way the integration would.
        traceback.print_exc()
        return HTTPStatus.INTERNAL_SERVER_ERROR, {
            "error": "The dashboard could not be converted"
        }


class HarnessHandler(SimpleHTTPRequestHandler):
    """Serve repository files without caching and answer preview requests."""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".json": "application/json",
    }

    token = ""

    def __init__(self, *args, **kwargs) -> None:
        """Serve from the repository root whatever the working directory."""
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        """Tell the browser never to cache, so edits show on reload."""
        self.send_header("Cache-Control", "no-store")
        if self.token:
            self.send_header(TOKEN_HEADER, self.token)
        super().end_headers()

    def list_directory(self, path):
        """Refuse directory listings; only files are served."""
        self.send_error(HTTPStatus.NOT_FOUND, "Directory listings are off")
        return None

    def log_request(self, code="-", size="-") -> None:
        """Stay quiet for answered requests; errors are still printed."""

    def do_POST(self) -> None:
        """Answer POST /api/preview and /api/facts; others are not found."""
        handlers = {PREVIEW_PATH: handle_preview_body, FACTS_PATH: handle_facts_body}
        handle = handlers.get(urllib.parse.urlsplit(self.path).path)
        if handle is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0:
            self.close_connection = True
            self._send_json(
                HTTPStatus.BAD_REQUEST, {"error": "Bad Content-Length header"}
            )
            return
        if length > MAX_BODY:
            # The body is not read, so the connection cannot be reused.
            self.close_connection = True
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": TOO_LARGE})
            return
        status, payload = handle(self.rfile.read(length))
        self._send_json(status, payload)

    def _send_json(self, status: int, payload: dict) -> None:
        """Send one JSON answer."""
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_handler(token: str = "") -> type[HarnessHandler]:
    """Return a handler class whose answers carry `token`, if one is given."""
    return type("TokenHandler", (HarnessHandler,), {"token": token})


def main(argv: list[str] | None = None) -> None:
    """Parse the arguments and serve until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--token", default="")
    args = parser.parse_args(argv)
    _library()
    server = ThreadingHTTPServer((args.bind, args.port), make_handler(args.token))
    host, port = server.server_address[:2]
    print(f"Serving {ROOT} on http://{host}:{port}/", flush=True)
    try:
        with suppress(KeyboardInterrupt):
            server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
