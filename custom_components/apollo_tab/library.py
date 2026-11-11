"""Load and track built-in and user Components, themes and strings."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .maker.const import (
    MAX_COMPONENTS,
    MAX_DOCS_PER_FILE,
    MAX_FILE_BYTES,
    MAX_USER_FILES,
)
from .maker.convert import alias_tag
from .maker.errors import MakerError
from .maker.schema import component_templates, validate_component
from .maker.templates import check_component_templates
from .sandbox import ComponentTemplate

_LOGGER = logging.getLogger(__name__)

# The folder holds data files only; the .library module import keeps working
# because the folder has no __init__.py.
_BUILTIN_DIR = Path(__file__).parent / "library"

# Bound a load so a pathological file cannot stall startup or reload.
LOAD_TIMEOUT_SECONDS = 30


class _ComponentLoader(yaml.SafeLoader):
    """SafeLoader that also refuses anchors and aliases."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        """Reject aliases and anchored nodes before composing the node."""
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("aliases are not allowed")
        event = self.peek_event()
        if getattr(event, "anchor", None) is not None:
            raise yaml.YAMLError("anchors are not allowed")
        return super().compose_node(parent, index)


def _error(file: str, index: int, component_id: str, code: str, message: str) -> dict:
    """Build one entry for the errors list."""
    return {
        "file": file,
        "index": index,
        "id": component_id,
        "code": code,
        "message": message,
    }


def _read_json(path: Path) -> Any:
    """Read a JSON file, returning None on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None


def _read_themes() -> dict[str, dict]:
    """Read the built-in themes, keyed by id in file order."""
    data = _read_json(_BUILTIN_DIR / "themes.json")
    themes: dict[str, dict] = {}
    if not isinstance(data, list):
        _LOGGER.error("Built-in themes.json is missing or not a list")
        return themes
    for entry in data:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            themes[entry["id"]] = entry
    return themes


def _read_strings() -> dict[str, str]:
    """Read the built-in UI strings."""
    data = _read_json(_BUILTIN_DIR / "strings.json")
    if not isinstance(data, dict):
        _LOGGER.error("Built-in strings.json is missing or not an object")
        return {}
    return {key: value for key, value in data.items() if isinstance(value, str)}


def _builtin_component_files() -> list[Path]:
    """Return the built-in component files, sorted by name."""
    folder = _BUILTIN_DIR / "components"
    try:
        files = [
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix == ".yaml"
        ]
    except OSError:
        _LOGGER.error("Built-in component folder %s cannot be read", folder)
        return []
    return sorted(files, key=lambda path: path.name)


def _read_documents(path: Path) -> tuple[list | None, dict | None]:
    """Read and parse one component file, returning documents or one error."""
    name = path.name
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None, _error(
                name, 0, "", "file_too_large", f"file exceeds {MAX_FILE_BYTES} bytes"
            )
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as err:
        return None, _error(name, 0, "", "yaml_error", str(err))
    try:
        # Any parser or constructor failure must not stop the other files.
        docs = list(yaml.load_all(text, Loader=_ComponentLoader))
    except RecursionError:
        return None, _error(name, 0, "", "yaml_error", "the file nests too deeply")
    except Exception as err:
        return None, _error(name, 0, "", "yaml_error", str(err) or type(err).__name__)
    if len(docs) > MAX_DOCS_PER_FILE:
        return None, _error(
            name,
            0,
            "",
            "too_many_documents",
            f"more than {MAX_DOCS_PER_FILE} documents in one file",
        )
    return docs, None


class Library:
    """Hold the Components, themes and strings offered to dashboards."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise an empty library."""
        self._hass = hass
        self.components: dict[str, dict] = {}
        self.errors: list[dict] = []
        self.themes: dict[str, dict] = {}
        self.strings: dict[str, str] = {}
        self.user_dir: str = hass.config.path(DOMAIN, "components")
        self._store: Store[dict] = Store(hass, 1, f"{DOMAIN}.approvals")
        self._approved: dict[str, str] = {}
        self._store_loaded = False
        self._listeners: list[Callable[[], None]] = []

    async def async_load(self) -> None:
        """Load or reload all files and notify the listeners."""
        if not self._store_loaded:
            self._store_loaded = True
            stored = await self._store.async_load()
            if isinstance(stored, dict) and isinstance(stored.get("approved"), dict):
                self._approved = dict(stored["approved"])
        try:
            async with asyncio.timeout(LOAD_TIMEOUT_SECONDS):
                result = await self._hass.async_add_executor_job(self._load_files)
            components: dict[str, dict] = {}
            errors: list[dict] = list(result["errors"])
            for candidate in result["candidates"]:
                component = candidate["component"]
                component["source"] = candidate["source"]
                component["file"] = candidate["file"]
                component["hash"] = candidate["hash"]
                components[component["id"]] = component
        except TimeoutError:
            _LOGGER.error(
                "Loading Components took longer than %s seconds; "
                "keeping the previous library",
                LOAD_TIMEOUT_SECONDS,
            )
            return
        except Exception:
            _LOGGER.exception("Loading Components failed; keeping the previous library")
            return
        # A failing built-in file is a bug in the integration, not user error.
        for error in errors:
            if error["file"] in result["builtin_files"]:
                _LOGGER.error(
                    "Built-in component %s failed: %s",
                    error["file"],
                    error["message"],
                )
        self.components = components
        self.errors = errors
        self.themes = result["themes"]
        self.strings = result["strings"]
        self._notify()

    def _check_templates(self, component: dict) -> str | None:
        """Return an error message when one of the templates is invalid."""
        for text in component_templates(component):
            try:
                ComponentTemplate(text, self._hass).ensure_valid()
            except RecursionError:
                return "template nests too deeply"
            except Exception as err:
                return str(err) or f"invalid template: {text}"
        return None

    def _user_files(self) -> list[Path]:
        """Return the eligible user component files, sorted by name."""
        try:
            os.makedirs(self.user_dir, exist_ok=True)
            entries = list(os.scandir(self.user_dir))
        except OSError as err:
            _LOGGER.error(
                "User component folder %s cannot be read: %s", self.user_dir, err
            )
            return []
        base = os.path.realpath(self.user_dir)
        files = []
        for entry in entries:
            if not entry.name.endswith((".yaml", ".yml")):
                continue
            try:
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    continue
                if os.path.dirname(os.path.realpath(entry.path)) != base:
                    continue
            except OSError:
                continue
            files.append(Path(entry.path))
        files.sort(key=lambda path: path.name)
        return files[:MAX_USER_FILES]

    def _load_files(self) -> dict[str, Any]:
        """Read, validate and check all files; runs in the executor."""
        themes = _read_themes()
        strings = _read_strings()
        files: list[tuple[Path, str]] = [
            (path, "builtin") for path in _builtin_component_files()
        ]
        files.extend((path, "user") for path in self._user_files())
        candidates: list[dict] = []
        errors: list[dict] = []
        seen: set[str] = set()
        for path, source in files:
            try:
                self._load_component_file(path, source, seen, candidates, errors)
            except Exception as err:
                # One broken file must never stop the others.
                errors.append(
                    _error(
                        path.name,
                        0,
                        "",
                        "invalid_component",
                        f"{type(err).__name__}: {err}",
                    )
                )
        return {
            "themes": themes,
            "strings": strings,
            "candidates": candidates,
            "errors": errors,
            "builtin_files": {
                path.name for path, source in files if source == "builtin"
            },
        }

    def _load_component_file(
        self,
        path: Path,
        source: str,
        seen: set[str],
        candidates: list[dict],
        errors: list[dict],
    ) -> None:
        """Read one file; validate and template-check every document in it."""
        docs, error = _read_documents(path)
        if error is not None:
            errors.append(error)
            return
        for index, doc in enumerate(docs):
            raw_id = doc.get("id") if isinstance(doc, dict) else ""
            doc_id = raw_id if isinstance(raw_id, str) else ""
            try:
                component = validate_component(doc)
                component_id = component["id"]
                if source == "user" and component_id.startswith("apollo/"):
                    errors.append(
                        _error(
                            path.name,
                            index,
                            component_id,
                            "reserved_namespace",
                            f"the apollo/ namespace is reserved: {component_id}",
                        )
                    )
                    continue
                if component_id in seen:
                    errors.append(
                        _error(
                            path.name,
                            index,
                            component_id,
                            "duplicate_id",
                            f"duplicate id: {component_id}",
                        )
                    )
                    continue
                if len(seen) >= MAX_COMPONENTS:
                    errors.append(
                        _error(
                            path.name,
                            index,
                            component_id,
                            "too_many",
                            f"more than {MAX_COMPONENTS} components",
                        )
                    )
                    continue
                seen.add(component_id)
                check_component_templates(component)
                template_error = self._check_templates(component)
                if template_error is not None:
                    errors.append(
                        _error(
                            path.name,
                            index,
                            component_id,
                            "bad_template",
                            template_error,
                        )
                    )
                    continue
                digest = hashlib.sha256(
                    json.dumps(component, sort_keys=True).encode()
                ).hexdigest()
                candidates.append(
                    {
                        "component": component,
                        "source": source,
                        "file": path.name,
                        "index": index,
                        "hash": digest,
                    }
                )
            except MakerError as err:
                errors.append(_error(path.name, index, doc_id, err.code, str(err)))
            except Exception as err:
                # Any other failure of one document leaves the rest alone.
                errors.append(
                    _error(
                        path.name,
                        index,
                        doc_id,
                        "invalid_component",
                        f"{type(err).__name__}: {err}",
                    )
                )

    def approved_ids(self) -> set[str]:
        """Return ids of sensitive user Components whose stored hash matches."""
        return {
            component_id
            for component_id, component in self.components.items()
            if component.get("source") == "user"
            and component.get("sensitive")
            and self._approved.get(component_id) == component.get("hash")
        }

    def is_approved(self, component_id: str) -> bool:
        """Return True unless this is a sensitive user Component without approval."""
        component = self.components.get(component_id)
        if component is None:
            return False
        if component.get("source") != "user" or not component.get("sensitive"):
            return True
        return self._approved.get(component_id) == component.get("hash")

    async def async_set_approved(self, component_id: str, approved: bool) -> None:
        """Store or remove an approval and notify the listeners."""
        component = self.components.get(component_id)
        if component is None:
            raise KeyError(component_id)
        if approved:
            self._approved[component_id] = component["hash"]
        else:
            self._approved.pop(component_id, None)
        await self._store.async_save({"approved": dict(self._approved)})
        self._notify()

    def async_listen(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a listener and return a function that removes it."""
        self._listeners.append(listener)

        def _remove() -> None:
            """Remove the listener."""
            self._listeners.remove(listener)

        return _remove

    def _notify(self) -> None:
        """Run every listener."""
        for listener in list(self._listeners):
            listener()

    def as_dict(self) -> dict[str, Any]:
        """Return the library as a JSON-able dict for the frontend."""
        components = []
        for component in self.components.values():
            size = component.get("size", [1, 1])
            components.append(
                {
                    "id": component["id"],
                    "tag": alias_tag(component["id"]),
                    "name": component.get("name", ""),
                    "description": component.get("description", ""),
                    "icon": component.get("icon", ""),
                    "version": component.get("version", ""),
                    "size": size,
                    "grid": {"columns": size[0] * 6, "rows": size[1] * 3},
                    "source": component.get("source", "user"),
                    "sensitive": component.get("sensitive", False),
                    "approved": self.is_approved(component["id"]),
                    "params": component.get("params", {}),
                }
            )
        components.sort(key=lambda item: (item["source"] != "builtin", item["name"]))
        return {
            "components": components,
            "errors": self.errors,
            "themes": list(self.themes.values()),
            "components_path": self.user_dir,
        }
