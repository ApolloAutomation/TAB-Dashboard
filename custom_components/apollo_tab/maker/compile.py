"""Compile validated card configurations into concrete cards."""

import json
import re
from typing import Any

from .const import FOR_EACH_MAX, MAX_WIDGETS
from .errors import MakerError
from .geometry import card_size_px, layout_card

_PARAM_REF = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")


def compile_card(component: dict, card: dict) -> dict:
    """Compile a validated card configuration into a concrete card."""
    return _Compiler(component, card).run()


def public_card(compiled: dict) -> dict:
    """Return a copy of a compiled card without the server-only parts."""
    return {
        key: value for key, value in compiled.items() if key not in ("slots", "actions")
    }


def _mentions(name: str, text: str) -> bool:
    """Return whether a template source mentions a variable name."""
    return re.search(rf"(?<![A-Za-z0-9_.]){name}(?![A-Za-z0-9_])", text) is not None


def _prelude(name: str, source: str) -> str:
    """Assign an input's source to its name, keeping the value's type."""
    inner = re.fullmatch(r"\{\{(.*)\}\}", source.strip(), re.DOTALL)
    if inner and not any(
        mark in inner[1] for mark in ("{{", "}}", "{%", "%}", "{#", "#}")
    ):
        return "{% set " + name + " = (" + inner[1].strip() + ") %}"
    block = "{% set " + name + " %}" + source + "{% endset %}"
    return block + "{% set " + name + " = " + name + " | trim %}"


def _source(spec: dict) -> str:
    """Return the template source behind a template or camera input."""
    if spec["kind"] == "camera":
        return "{{ state_attr(" + spec["param"] + ", 'entity_picture') or '' }}"
    return spec["template"]


def _constant(value: Any) -> Any:
    """Tidy a constant, writing floats with integer values as ints."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_constant(item) for item in value]
    return value


class _Compiler:
    """Hold the state for compiling one card."""

    def __init__(self, component: dict, card: dict) -> None:
        """Store the inputs and derive demo mode and param variables."""
        self.component = component
        self.card = card
        self.demo = bool(card["missing"])
        self.preview = component["preview"]
        if self.demo and not self.preview["params"] and not self.preview["inputs"]:
            raise MakerError(
                "params_incomplete",
                "params",
                "Card is missing params and the component has no preview values.",
            )
        self.param_vars = self._param_vars()
        self._slot_keys: dict[str, int] = {}
        self.slots: list = []
        self.actions: dict = {}
        self.on: Any = None

    def run(self) -> dict:
        """Compile the card and return the full server-side result."""
        width, height = card_size_px(self.card["columns"], self.card["rows"])
        expanded, cut = self._expand()
        geo_items = [self._geo_item(item, group) for item, _, group in expanded]
        laid = layout_card(geo_items, width, height, self.component["header"])
        header = self._header(laid["header"])
        widgets = self._widgets(expanded, laid["rects"])
        clipped = laid["clipped"] or any(rect is None for rect in laid["rects"])
        return {
            "component": self.component["id"],
            "name": self.component["name"],
            "demo": self.demo,
            "w": width,
            "h": height,
            "entities": self._entities(),
            "header": header,
            "on": self.on,
            "widgets": widgets,
            "slots": self.slots,
            "actions": self.actions,
            "warnings": ["element_clipped"] if cut or clipped else [],
        }

    def _param_vars(self) -> dict:
        """Map each param with a value to it, using previews when missing."""
        variables = {}
        preview = self.preview["params"]
        for name in self.component["params"]:
            if name in self.card["params"]:
                variables[name] = self.card["params"][name]
            elif self.demo and name in preview:
                variables[name] = preview[name]
        return variables

    def _expand(self) -> tuple[list, bool]:
        """Repeat for_each items and cap the result at MAX_WIDGETS."""
        expanded = []
        for index, item in enumerate(self.component["layout"]):
            for_each = item.get("for_each")
            if not for_each:
                expanded.append((item, {}, None))
                continue
            value = self.param_vars.get(for_each)
            if value is None:
                # A param without a value expands to zero copies.
                continue
            entities = value if isinstance(value, list) else [value]
            for entity in entities[:FOR_EACH_MAX]:
                names = {item["as"]: entity} if item.get("as") else {}
                expanded.append((item, names, index))
        cut = len(expanded) > MAX_WIDGETS
        return expanded[:MAX_WIDGETS], cut

    @staticmethod
    def _geo_item(item: dict, group: int | None) -> dict:
        """Build the geometry input for one expanded item."""
        geo = {"type": item["type"]}
        for key in ("size", "side"):
            if item.get(key) is not None:
                geo[key] = item[key]
        if group is not None:
            geo["group"] = group
        return geo

    def _header(self, rect: list | None) -> dict | None:
        """Build the header, binding its title before any widget."""
        if not self.component["header"]:
            return None
        header = {"r": rect}
        if self.component["icon"] is not None:
            header["icon"] = self.component["icon"]
        header["title"] = self._title()
        return header

    def _title(self) -> Any:
        """Choose the title: configured, entity friendly name, or name."""
        if self.card["title"] is not None:
            # Plain text: a card config comes from the browser, so it must
            # never become a template.
            return self.card["title"]
        param = self._first_single_entity_param()
        if not self.demo and param is not None:
            src = "{{ state_attr(" + param + ", 'friendly_name') or component_name }}"
            slot = self._template_slot(src, {})
            slot["variables"]["component_name"] = self.component["name"]
            return {"s": self._add_slot(slot)}
        return self.component["name"]

    def _first_single_entity_param(self) -> str | None:
        """Return the first param holding a single entity, if any."""
        for name, spec in self.component["params"].items():
            if spec["kind"] == "entity" and not spec["multiple"]:
                return name
        return None

    def _entities(self) -> list:
        """List the entity ids the user configured, in param order."""
        entities = []
        for name, spec in self.component["params"].items():
            if spec["kind"] != "entity" or name not in self.card["params"]:
                continue
            value = self.card["params"][name]
            if isinstance(value, list):
                entities.extend(value)
            else:
                entities.append(value)
        return entities

    def _widgets(self, expanded: list, rects: list) -> list:
        """Build the widgets that fit, in expanded order."""
        widgets = []
        pairs = zip(expanded, rects, strict=True)
        for i, ((item, item_vars, _group), rect) in enumerate(pairs):
            if rect is None:
                # Widgets that did not fit get no slots and no entry.
                continue
            widget = {"i": i, "t": item["type"], "r": rect}
            self._bind_keys(widget, item, item_vars)
            self._interactions(widget, item, item_vars, i)
            if item["type"] == "switch" and self.on is None:
                self.on = widget["value"]
            widgets.append(widget)
        return widgets

    def _bind_keys(self, widget: dict, item: dict, item_vars: dict) -> None:
        """Compile the type-specific bound fields of one widget."""
        kind = item["type"]
        if kind == "switch":
            widget["value"] = self._bind(item["value"], item_vars)
        elif kind in ("slider", "thermostat"):
            widget["value"] = self._bind(item["value"], item_vars)
            widget["min"] = self._bind(item["min"], item_vars)
            widget["max"] = self._bind(item["max"], item_vars)
            widget["step"] = self._bind(item["step"], item_vars)
        elif kind == "chart":
            widget["value"] = self._bind(item["value"], item_vars)
            widget["kind"] = item["kind"]
        elif kind == "button":
            if item["text"] is not None:
                widget["text"] = self._bind(item["text"], item_vars)
            if item["icon"] is not None:
                widget["icon"] = item["icon"]
        elif kind == "label":
            widget["text"] = self._bind(item["text"], item_vars)
            widget["size"] = item["size"]
        elif kind == "image":
            widget["value"] = self._bind(item["value"], item_vars)
            widget["refresh"] = self._image_refresh(item)

    def _image_refresh(self, item: dict) -> int:
        """Return the camera refresh seconds behind an image value, else 0."""
        value = item["value"]
        if isinstance(value, dict) and "input" in value:
            spec = self.component["inputs"].get(value["input"])
            if spec is not None and spec["kind"] == "camera":
                return spec["refresh"]
        return 0

    def _interactions(self, widget: dict, item: dict, item_vars: dict, i: int) -> None:
        """Add tap, change and confirm keys and record server actions."""
        on_tap = item.get("on_tap")
        if on_tap is not None:
            tap = self._tap(on_tap, i, item_vars)
            if tap is not None:
                widget["tap"] = tap
        on_change = item.get("on_change")
        if on_change is not None:
            output = self.component["outputs"][on_change]
            if output["kind"] == "action":
                widget["change"] = {"policy": output["feedback"]}
                self.actions[f"{i}:change"] = {
                    "output": on_change,
                    "vars": dict(item_vars),
                }
        confirm = item.get("confirm")
        if confirm is not None:
            widget["confirm"] = self._bind(confirm, item_vars)

    def _tap(self, name: str, i: int, item_vars: dict) -> dict | None:
        """Build the tap dict for an output, recording action outputs."""
        output = self.component["outputs"][name]
        if output["kind"] == "action":
            self.actions[f"{i}:tap"] = {"output": name, "vars": dict(item_vars)}
            return {"policy": output["feedback"]}
        tap = {"local": output["local"]}
        if output["local"] in ("open_details", "open_live"):
            param = self._first_single_entity_param()
            if param is not None and param in self.param_vars:
                tap["entity"] = self.param_vars[param]
        elif output["local"] == "go_to_page":
            page = self._page_value(output["page"])
            if not page:
                return None
            tap["page"] = page
        return tap

    def _page_value(self, page: str | None) -> str:
        """Resolve a local output page: a literal or a param reference."""
        if not page:
            return ""
        match = _PARAM_REF.fullmatch(page)
        if match:
            return str(self.param_vars.get(match.group(1)) or "")
        return page

    def _bind(self, field: Any, item_vars: dict) -> Any:
        """Compile one bound field to a constant or a slot reference."""
        if isinstance(field, dict):
            if "input" in field:
                return self._bind_input(field["input"], item_vars)
            field = field["template"]
        if isinstance(field, str) and ("{{" in field or "{%" in field):
            return {"s": self._add_slot(self._template_slot(field, item_vars))}
        return _constant(field)

    def _bind_input(self, name: str, item_vars: dict) -> Any:
        """Compile a reference to a declared input."""
        spec = self.component["inputs"][name]
        kind = spec["kind"]
        if self.demo and name in self.preview["inputs"]:
            return _constant(self.preview["inputs"][name])
        if kind in ("template", "camera"):
            slot = self._template_slot("{{ " + name + " }}", item_vars)
            return {"s": self._add_slot(slot)}
        if self.demo:
            # A history or action input without a preview value is empty.
            return []
        if kind == "history":
            slot = {
                "kind": "history",
                "entity": self.param_vars[spec["param"]],
                "hours": spec["hours"],
            }
        else:
            slot = {
                "kind": "action",
                "action": spec["action"],
                "data": {
                    **spec["data"],
                    "entity_id": self.param_vars[spec["param"]],
                },
                "result": spec["result"],
                "variables": dict(self.param_vars),
                "refresh": spec["refresh"],
            }
        return {"s": self._add_slot(slot)}

    def _template_slot(self, src: str, item_vars: dict) -> dict:
        """Build a template slot, inlining the inputs the source mentions."""
        inputs = self.component["inputs"]
        preview = self.preview["inputs"] if self.demo else {}
        used = self._used_inputs(src, inputs, preview)
        template = "".join(_prelude(name, _source(inputs[name])) for name in used)
        template += src
        variables = {**self.param_vars, **item_vars}
        for name, value in preview.items():
            if _mentions(name, src) or any(
                _mentions(name, _source(inputs[other])) for other in used
            ):
                variables[name] = value
        return {"kind": "template", "template": template, "variables": variables}

    @staticmethod
    def _used_inputs(src: str, inputs: dict, preview: dict) -> list:
        """Collect mentioned template or camera inputs in declaration order."""
        found = set()
        queue = [src]
        while queue:
            text = queue.pop()
            for name, spec in inputs.items():
                if (
                    name in found
                    or name in preview
                    or spec["kind"] not in ("template", "camera")
                    or not _mentions(name, text)
                ):
                    continue
                found.add(name)
                queue.append(_source(spec))
        return [name for name in inputs if name in found]

    def _add_slot(self, slot: dict) -> int:
        """Return a slot's number, reusing the number of an identical one."""
        key = json.dumps(slot, sort_keys=True)
        if key in self._slot_keys:
            return self._slot_keys[key]
        number = len(self.slots) + 1
        self._slot_keys[key] = number
        self.slots.append({"n": number, **slot})
        return number
