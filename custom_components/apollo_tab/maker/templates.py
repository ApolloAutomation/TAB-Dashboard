"""Check Component templates statically before Home Assistant compiles them.

The checks here give early, clear errors for syntax problems and for template
features that Components leave out, and they limit service data templates to
the card's own values. Cost is not predicted from expression shapes; the
runtime limits in sandbox.py bound steps, time and value sizes while the
template renders.
"""

from __future__ import annotations

from collections.abc import Iterator

from jinja2 import nodes
from jinja2.exceptions import TemplateSyntaxError
from jinja2.sandbox import ImmutableSandboxedEnvironment

from .const import (
    BLOCKED_TEXT_METHODS,
    DATA_TEMPLATE_FILTERS,
    DATA_TEMPLATE_TESTS,
    UNAVAILABLE_FILTERS,
    UNAVAILABLE_GLOBALS,
    UNAVAILABLE_TESTS,
)
from .errors import MakerError

# One environment shared for parsing only; parsing never evaluates anything,
# so a single instance is safe to share between threads. The extensions are
# the tag extensions Home Assistant adds; its other extensions only add
# functions and filters, which parsing does not need.
_PARSE_ENV = ImmutableSandboxedEnvironment(
    extensions=["jinja2.ext.loopcontrols", "jinja2.ext.do"]
)

_LAYOUT_KEYS = ("value", "min", "max", "step", "text", "confirm")


def _is_template(value: object) -> bool:
    """Return True when value is a string containing a template marker."""
    return isinstance(value, str) and ("{{" in value or "{%" in value)


def _iter_nodes(root: nodes.Node) -> Iterator[nodes.Node]:
    """Yield root and every descendant without recursion."""
    stack: list[nodes.Node] = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.iter_child_nodes())


def _parse(text: str, path: str) -> nodes.Template:
    """Parse the template, turning parser failures into MakerError."""
    try:
        return _PARSE_ENV.parse(text)
    except TemplateSyntaxError as err:
        raise MakerError(
            "bad_template", path, f"template syntax error: {err.message}"
        ) from None
    except RecursionError:
        raise MakerError("bad_template", path, "template nests too deeply") from None
    except Exception as err:
        raise MakerError("bad_template", path, f"{type(err).__name__}: {err}") from None


def _check_tree(tree: nodes.Template, path: str) -> None:
    """Walk the parsed template and reject features Components leave out."""
    for node in _iter_nodes(tree):
        if isinstance(
            node,
            nodes.Macro
            | nodes.CallBlock
            | nodes.Import
            | nodes.FromImport
            | nodes.Include
            | nodes.Extends
            | nodes.Block,
        ):
            raise MakerError(
                "bad_template",
                path,
                "macros, imports, includes and blocks are not available in Components",
            )
        if isinstance(node, nodes.For) and node.recursive:
            raise MakerError(
                "bad_template", path, "recursive loops are not available in Components"
            )
        if isinstance(node, nodes.Filter) and node.name in UNAVAILABLE_FILTERS:
            raise MakerError(
                "bad_template",
                path,
                f"the {node.name} filter is not available in Components",
            )
        if isinstance(node, nodes.Test) and node.name in UNAVAILABLE_TESTS:
            raise MakerError(
                "bad_template",
                path,
                f"the {node.name} test is not available in Components",
            )
        if (
            isinstance(node, nodes.Name)
            and node.ctx == "load"
            and node.name in UNAVAILABLE_GLOBALS
        ):
            raise MakerError(
                "bad_template", path, f"{node.name} is not available in Components"
            )
        if isinstance(node, nodes.Getattr) and node.attr in BLOCKED_TEXT_METHODS:
            raise MakerError(
                "bad_template",
                path,
                f"the {node.attr} method is not available in Components",
            )


def _check_data_tree(tree: nodes.Template, path: str, allowed_names: set[str]) -> None:
    """Limit a service data template to plain expressions over allowed names."""
    for node in _iter_nodes(tree):
        if isinstance(node, nodes.Stmt) and not isinstance(node, nodes.Output):
            raise MakerError(
                "bad_template",
                path,
                "service data templates may only use {{ }} expressions",
            )
        if isinstance(node, nodes.Name) and node.name not in allowed_names:
            raise MakerError(
                "bad_template",
                path,
                "service data templates may only use the card's params, "
                f"loop names and value, not {node.name!r}",
            )
        if isinstance(node, nodes.Filter) and node.name not in DATA_TEMPLATE_FILTERS:
            raise MakerError(
                "bad_template",
                path,
                f"the {node.name} filter is not allowed in service data",
            )
        if isinstance(node, nodes.Test) and node.name not in DATA_TEMPLATE_TESTS:
            raise MakerError(
                "bad_template",
                path,
                f"the {node.name} test is not allowed in service data",
            )
        if isinstance(node, nodes.Call):
            raise MakerError(
                "bad_template",
                path,
                "function calls are not allowed in service data",
            )


def check_template(text: str, path: str) -> None:
    """Raise MakerError for syntax errors or features Components leave out."""
    _check_tree(_parse(text, path), path)


def check_data_template(text: str, path: str, allowed_names: set[str]) -> None:
    """Run check_template, then limit a service data template to allowed names."""
    tree = _parse(text, path)
    _check_tree(tree, path)
    _check_data_tree(tree, path, allowed_names)


def check_component_templates(component: dict) -> None:
    """Check every template of a normalised Component; raise on the first failure."""
    for name, spec in component["inputs"].items():
        if spec["kind"] == "template":
            check_template(spec["template"], f"inputs.{name}")
        elif spec["kind"] == "action":
            check_template(spec["result"], f"inputs.{name}.result")
    data_templates: list[tuple[str, str]] = []
    for name, spec in component["outputs"].items():
        if spec["kind"] != "action":
            continue
        for key, value in spec["data"].items():
            if not _is_template(value):
                continue
            data_path = f"outputs.{name}.data.{key}"
            check_template(value, data_path)
            if key != "entity_id":
                data_templates.append((data_path, value))
    for index, item in enumerate(component["layout"]):
        for key in _LAYOUT_KEYS:
            value = item.get(key)
            if isinstance(value, dict):
                value = value.get("template")
            if _is_template(value):
                check_template(value, f"layout.{index}.{key}")
    allowed_names = set(component["params"])
    allowed_names.update(item["as"] for item in component["layout"] if item.get("as"))
    allowed_names.add("value")
    for data_path, text in data_templates:
        check_data_template(text, data_path, allowed_names)
