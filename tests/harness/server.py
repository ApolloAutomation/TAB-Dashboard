"""Serve the browser harness and convert dashboard drafts like the integration.

Run from the repository root with the test environment's Python, because the
converter is imported from the integration package:

    python -B tests/harness/server.py [--port 8765] [--bind 127.0.0.1] [--token T]

GET serves files from the repository. POST /api/preview with {"config": {...}}
answers with what apollo_tab/layout/preview would send, using the bundled
cards and one card as from the user's folder (FIVE_GRAPHS), no approved cards
and stand-in values instead of real states.

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

from custom_components.apollo_tab.maker.convert import convert_dashboard  # noqa: E402
from custom_components.apollo_tab.maker.schema import validate_component  # noqa: E402
from tests.harness.build_fixtures import (  # noqa: E402
    load_components,
    load_theme_entries,
    render_slots,
    renderer,
)

MAX_BODY = 1024 * 1024
PREVIEW_PATH = "/api/preview"
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


def preview_response(config: dict) -> dict:
    """Convert a dashboard config and return the preview command's answer."""
    components, themes = _library()
    result = convert_dashboard(
        config, components=components, themes=themes, approved=set()
    )
    return {
        "layout": result["layout"],
        "warnings": result["warnings"],
        "values": render_slots(result["bindings"]["slots"], renderer()),
        "sources": result["sources"],
    }


def handle_preview_body(body: bytes) -> tuple[int, dict]:
    """Return the HTTP status and JSON answer for one preview request body."""
    if len(body) > MAX_BODY:
        return HTTPStatus.BAD_REQUEST, {"error": TOO_LARGE}
    try:
        data = json.loads(body)
    except ValueError, RecursionError:
        return HTTPStatus.BAD_REQUEST, {"error": "The request is not valid JSON"}
    if not isinstance(data, dict) or not isinstance(data.get("config"), dict):
        return HTTPStatus.BAD_REQUEST, {"error": "config must be a JSON object"}
    try:
        return HTTPStatus.OK, preview_response(data["config"])
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
        """Answer POST /api/preview; every other path is not found."""
        if urllib.parse.urlsplit(self.path).path != PREVIEW_PATH:
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
        status, payload = handle_preview_body(self.rfile.read(length))
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
