"""The guides name what a card file and the tablets list may hold (G.3, I13).

The keys are read from the loader itself, so a key added to the loader
without a word in docs/components.md fails here.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from custom_components.apollo_tab.maker.const import UPDATE_NOTE

ROOT = Path(__file__).resolve().parent.parent
SCHEMA2 = ROOT / "custom_components" / "apollo_tab" / "maker" / "schema2.py"
COMPONENTS = ROOT / "docs" / "components.md"
TABLETS = ROOT / "docs" / "tablets.md"
SHAPES = Path(__file__).parent / "harness" / "tablet-shapes.json"


def _module() -> ast.Module:
    return ast.parse(SCHEMA2.read_text(encoding="utf-8"))


def _constants(tree: ast.Module) -> dict[str, ast.expr]:
    """Return the module-level assignments by name."""
    found: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            found[node.target.id] = node.value
    return found


def _local(function: ast.AST, name: str) -> list[ast.expr]:
    """Return every value assigned to `name` inside one function."""
    values: list[ast.expr] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            values.append(node.value)
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == name and node.value:
                values.append(node.value)
    return values


def _strings(
    node: ast.AST, module: dict[str, ast.expr], function: ast.AST, seen: set[str]
) -> set[str]:
    """Return the key names an expression stands for, following names."""
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else set()
    if isinstance(node, ast.Name):
        if node.id in seen:
            return set()
        seen = seen | {node.id}
        values = _local(function, node.id) or (
            [module[node.id]] if node.id in module else []
        )
        return {s for value in values for s in _strings(value, module, function, seen)}
    if isinstance(node, ast.Dict):
        # A mapping of keys stands for its keys and, for sets, their members.
        found = {k.value for k in node.keys if isinstance(k, ast.Constant)}
        for value in node.values:
            if isinstance(value, ast.Set | ast.Call | ast.Name):
                found |= _strings(value, module, function, seen)
        return found
    if isinstance(node, ast.Subscript):
        # One entry of a mapping of key sets: the members of every entry.
        values = [node.value]
        if isinstance(node.value, ast.Name) and node.value.id in module:
            values = [module[node.value.id]]
        found = set()
        for value in values:
            if isinstance(value, ast.Dict):
                for entry in value.values:
                    found |= _strings(entry, module, function, seen)
            else:
                found |= _strings(value, module, function, seen)
        return found
    if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
        return set()
    found: set[str] = set()
    for child in ast.iter_child_nodes(node):
        if isinstance(node, ast.Call) and child is node.func:
            continue
        found |= _strings(child, module, function, seen)
    return found


def card_file_keys() -> set[str]:
    """Return every key the schema 2 loader accepts, at any level of a file."""
    tree = _module()
    module = _constants(tree)
    keys: set[str] = set()
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        for call in ast.walk(function):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "_reject_unknown_keys"
            ):
                keys |= _strings(call.args[1], module, function, set())
    return keys


def layout_types() -> set[str]:
    """Return the widget and container types of a layout."""
    module = _constants(_module())
    widgets = module["_WIDGET_KEYS"]
    assert isinstance(widgets, ast.Dict)
    types = {k.value for k in widgets.keys if isinstance(k, ast.Constant)}
    containers = module["_CONTAINERS"]
    assert isinstance(containers, ast.Set)
    return types | {e.value for e in containers.elts if isinstance(e, ast.Constant)}


def _names_key(doc: str, key: str) -> bool:
    """Return True when the guide shows `key` in code or as `key:` in YAML."""
    return f"`{key}`" in doc or re.search(rf"(?<![\w.-]){re.escape(key)}:", doc)


def test_the_loader_is_read_whole() -> None:
    """The collection sees the keys of each level, so the test below means something."""
    keys = card_file_keys()
    for key in (
        "schema",
        "variants",
        "needs_text",
        "default_first",
        "on_hold",
        "colour",
        "keep_active",
        "for_each",
        "uses",
        "feedback",
        "picker",
        "can",
        "stat",
        "kelvin",
    ):
        assert key in keys, key
    assert len(keys) >= 95
    assert {"label", "slider", "choice", "row", "swap", "space"} <= layout_types()


def test_the_card_guide_names_every_key_of_a_schema_2_file() -> None:
    """docs/components.md names each key the loader accepts (C.2)."""
    doc = COMPONENTS.read_text(encoding="utf-8")
    missing = sorted(key for key in card_file_keys() if not _names_key(doc, key))
    assert missing == []


def test_the_card_guide_names_every_layout_type() -> None:
    """Each widget and container type has its row or its `type: <name>`."""
    doc = COMPONENTS.read_text(encoding="utf-8")
    missing = sorted(
        kind
        for kind in layout_types()
        if f"| `{kind}` |" not in doc
        and not re.search(rf"type: {re.escape(kind)}\b", doc)
    )
    assert missing == []


def test_the_card_guide_says_outputs_see_inputs() -> None:
    """The old sentence that outputs do not see inputs holds for schema 1 only."""
    doc = COMPONENTS.read_text(encoding="utf-8")
    assert "## Schema 2 cards" in doc
    for line in doc.splitlines():
        if "do not see inputs" in line.lower():
            assert "schema 1" in line.lower(), line


def test_the_tablet_guide_names_what_the_tablets_list_reports() -> None:
    """docs/tablets.md names the three counts of an older tablet and the note."""
    doc = TABLETS.read_text(encoding="utf-8")
    shape = json.loads(SHAPES.read_text(encoding="utf-8"))
    text = json.dumps(shape)
    for key in ("simpler", "dropped", "not_kept"):
        assert f'"{key}"' in text, key
        assert f"| `{key}` |" in doc, key
    assert f'"{UPDATE_NOTE}"' in doc
    assert "`UPDATE_NOTE`" in doc
    assert "custom_components/apollo_tab/maker/const.py" in doc
