"""Load and track built-in and user Components, themes and strings."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .maker.const import (
    CARD_GROUPS,
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

# The groups of the card picker, the same as a schema 2 file's `group`.
# The panel gives each its title.
PICKER_GROUPS = CARD_GROUPS
MAX_KEYWORDS = 8
MAX_KEYWORD_LENGTH = 24
# A search word: lower-case words of letters and digits, with single spaces,
# hyphens or apostrophes between them.
_KEYWORD = re.compile(r"[a-z0-9]+(?:[ '-][a-z0-9]+)*")


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


def _read_status() -> dict[str, Any]:
    """Read the built-in status colours (good, warn, bad, info) per theme."""
    data = _read_json(_BUILTIN_DIR / "status.json")
    if not isinstance(data, dict):
        _LOGGER.error("Built-in status.json is missing or not an object")
        return {}
    return data


def _read_strings() -> dict[str, str]:
    """Read the built-in UI strings."""
    data = _read_json(_BUILTIN_DIR / "strings.json")
    if not isinstance(data, dict):
        _LOGGER.error("Built-in strings.json is missing or not an object")
        return {}
    return {key: value for key, value in data.items() if isinstance(value, str)}


def picker_entry_problem(entry: Any) -> str | None:
    """Return why an entry of picker.json cannot be used, or None."""
    if not isinstance(entry, dict):
        return "the entry is not an object"
    unknown = set(entry) - {"group", "keywords"}
    if unknown:
        return f"unknown key {sorted(unknown)[0]!r}"
    if entry.get("group") not in PICKER_GROUPS:
        return f"unknown group {entry.get('group')!r}"
    keywords = entry.get("keywords", [])
    if not isinstance(keywords, list) or len(keywords) > MAX_KEYWORDS:
        return f"keywords must be a list of at most {MAX_KEYWORDS} words"
    for word in keywords:
        if (
            not isinstance(word, str)
            or len(word) > MAX_KEYWORD_LENGTH
            or not _KEYWORD.fullmatch(word)
        ):
            return f"{word!r} is not a short plain search word"
    if len(set(keywords)) != len(keywords):
        return "a search word is listed twice"
    return None


def read_picker(path: Path | None = None) -> dict[str, dict]:
    """Read picker.json: a group and search words per built-in card id.

    An entry that fails the checks is left out and logged, because the file
    ships with the integration. An entry for a card that is not there is
    never used.
    """
    data = _read_json(path or _BUILTIN_DIR / "picker.json")
    if not isinstance(data, dict):
        _LOGGER.error("Built-in picker.json is missing or not an object")
        return {}
    entries: dict[str, dict] = {}
    for card_id, entry in data.items():
        problem = picker_entry_problem(entry)
        if problem is not None:
            _LOGGER.error("Built-in picker.json, %s: %s", card_id, problem)
            continue
        entries[card_id] = {
            "group": entry["group"],
            "keywords": list(entry.get("keywords", [])),
        }
    return entries


def picker_fields(component: dict, picker: dict[str, dict]) -> dict[str, Any]:
    """Return the picker's group and search words for one card.

    The card file's own win; else the card's entry in picker.json. A card
    with neither has an empty group, and the panel guesses one.
    """
    entry = picker.get(component.get("id"), {})
    return {
        "group": component.get("group") or entry.get("group", ""),
        "keywords": list(component.get("keywords") or entry.get("keywords", [])),
    }


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


def _v1_targets(component: dict) -> list[str]:
    """Return the ids a schema 2 card names for version 1 tablets."""
    if component.get("schema") != 2:
        return []
    names = [component.get("v1")]
    names.extend(variant.get("v1") for variant in component["variants"].values())
    return [name for name in names if name not in (None, "note")]


def _drop_unknown_v1(candidates: list[dict], errors: list[dict]) -> list[dict]:
    """Refuse schema 2 cards whose v1 is not a loaded schema 1 card."""
    schema1 = {
        candidate["component"]["id"]
        for candidate in candidates
        if candidate["component"].get("schema", 1) == 1
    }
    kept = []
    for candidate in candidates:
        component = candidate["component"]
        missing = [name for name in _v1_targets(component) if name not in schema1]
        if missing:
            errors.append(
                _error(
                    candidate["file"],
                    candidate["index"],
                    component["id"],
                    "unknown_v1",
                    f"v1 names {missing[0]}, which is not a loaded schema 1 card",
                )
            )
            continue
        kept.append(candidate)
    return kept


def _param_entry(spec: dict) -> dict:
    """Return one param as the form reads it (C.7), for both schemas."""
    if spec.get("kind") != "entity":
        return {
            **spec,
            "optional": spec.get("optional", False),
            "label": spec.get("label", ""),
            "help": spec.get("help", ""),
        }
    domains = spec.get("domains")
    if domains is None:
        domains = [spec["domain"]] if spec.get("domain") else []
    entry = {
        "kind": "entity",
        "domains": list(domains),
        "multiple": spec.get("multiple", False),
        "optional": spec.get("optional", False),
        "device_class": spec.get("device_class"),
        "label": spec.get("label", ""),
        "help": spec.get("help", ""),
    }
    if len(domains) == 1:
        # Today's text; the panel reads it where a param has one kind.
        entry["domain"] = domains[0]
    if entry["multiple"]:
        entry["max"] = spec.get("max", 8)
    return entry


def _variant_entries(component: dict) -> list[dict]:
    """Return the variants as the picker reads them."""
    if component.get("schema") != 2:
        size = component.get("size", [1, 1])
        return [
            {
                "id": "default",
                "name": component.get("name", ""),
                "grid": [size[0] * 6, size[1] * 3],
                "picker": True,
                "needs_v2": False,
            }
        ]
    default_v1 = component.get("v1")
    entries = []
    for name, variant in component["variants"].items():
        v1 = variant.get("v1") or default_v1
        entries.append(
            {
                "id": name,
                "name": variant["name"],
                "grid": list(variant["grid"]),
                "picker": variant["picker"],
                # Known from the file alone; the converter also shows the note
                # when a variant's own version 1 form keeps nothing (C.6).
                "needs_v2": v1 == "note",
            }
        )
    return entries


def _option_entries(component: dict) -> list[dict]:
    """Return the options in file order, each with its name (C.7)."""
    return [
        {"name": name, **spec} for name, spec in component.get("options", {}).items()
    ]


def _standard(component: dict) -> dict:
    """Return which standard options a card offers (C.2.3)."""
    if component.get("schema") != 2:
        return {"title": True, "icon": False, "hold": False, "lit": None, "tint": False}
    return {
        "title": any(
            variant["header"] != "none" for variant in component["variants"].values()
        ),
        "icon": True,
        "hold": component.get("detail") is not None,
        "lit": component.get("lit"),
        "tint": component.get("tint") is not None,
    }


def _tap_entry(component: dict) -> dict | None:
    """Return the tap choices, with the standard "Goes to a page" before none."""
    tap = component.get("tap")
    if tap is None:
        return None
    choices = [
        {"value": choice["value"], "label": choice["label"], "needs": choice["needs"]}
        for choice in tap["choices"]
    ]
    page = {"value": "page", "label": "Goes to a page", "needs": ""}
    at = next(
        (i for i, choice in enumerate(choices) if choice["value"] == "none"),
        len(choices),
    )
    choices.insert(at, page)
    return {"default": tap["default"], "choices": choices}


def form_entry(component: dict, legacy: bool) -> dict:
    """Return the static fields of one card for the form and picker (C.7)."""
    variants = _variant_entries(component)
    first = next(variant for variant in variants if variant["picker"])
    columns, rows = first["grid"]
    picker = [variant for variant in variants if variant["picker"]]
    return {
        "schema": component.get("schema", 1),
        "group": component.get("group", "more"),
        "legacy": legacy,
        "replaces": list(component.get("replaces", [])),
        "needs_v2": all(variant["needs_v2"] for variant in picker),
        "size": [max(1, min(6, -(-columns // 6))), max(1, min(4, -(-rows // 3)))],
        "grid": {"columns": columns, "rows": rows},
        "variants": variants,
        "has_detail": component.get("detail") is not None,
        "params": {
            name: _param_entry(spec)
            for name, spec in component.get("params", {}).items()
        },
        "options": _option_entries(component),
        "standard": _standard(component),
        "tap": _tap_entry(component),
        "notes": [dict(note) for note in component.get("notes", [])],
    }


class Library:
    """Hold the Components, themes and strings offered to dashboards."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise an empty library."""
        self._hass = hass
        self.components: dict[str, dict] = {}
        self.errors: list[dict] = []
        self.themes: dict[str, dict] = {}
        self.status: dict[str, Any] = {}
        self.strings: dict[str, str] = {}
        self.picker: dict[str, dict] = {}
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
        self.status = result["status"]
        self.strings = result["strings"]
        self.picker = result["picker"]
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
        status = _read_status()
        strings = _read_strings()
        picker = read_picker()
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
        candidates = _drop_unknown_v1(candidates, errors)
        return {
            "themes": themes,
            "status": status,
            "strings": strings,
            "picker": picker,
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
                if source == "user" and component.get("replaces"):
                    # A stranger's file could otherwise hide the built-in
                    # cards in the picker and take their place.
                    errors.append(
                        _error(
                            path.name,
                            index,
                            component_id,
                            "replaces_not_allowed",
                            "only built-in cards may replace other cards",
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
                if source == "user" and component.get("uses_inputs"):
                    # Service data that reads an input can carry house state
                    # out; a person's own file needs an admin's approval.
                    component["sensitive"] = True
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

    def replaced_ids(self) -> set[str]:
        """Return the ids that a built-in schema 2 card names in replaces.

        `replaces` is read from built-in files only (C.2.1); a person's file
        that carries it is refused when it loads.
        """
        return {
            replaced
            for component in self.components.values()
            if component.get("source") == "builtin"
            for replaced in component.get("replaces", [])
        }

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
        replaced = self.replaced_ids()
        for component in self.components.values():
            entry = {
                "id": component["id"],
                "tag": alias_tag(component["id"]),
                "name": component.get("name", ""),
                "description": component.get("description", ""),
                "icon": component.get("icon", ""),
                "version": component.get("version", ""),
                "source": component.get("source", "user"),
                "sensitive": component.get("sensitive", False),
                "approved": self.is_approved(component["id"]),
            }
            entry.update(form_entry(component, component["id"] in replaced))
            # The picker's group and search words: a schema 2 file's own
            # group, else picker.json's entry, else none (the panel guesses).
            entry.update(picker_fields(component, self.picker))
            components.append(entry)
        components.sort(key=lambda item: (item["source"] != "builtin", item["name"]))
        return {
            "components": components,
            "errors": self.errors,
            "themes": list(self.themes.values()),
            "status": self.status,
            "components_path": self.user_dir,
        }
