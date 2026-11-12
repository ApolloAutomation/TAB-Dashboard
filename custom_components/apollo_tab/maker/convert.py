"""Convert a sections dashboard into a tablet layout and its bindings."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Set
from typing import Any

from .compile import compile_card
from .const import (
    DEFAULT_THEME,
    ICON_RE,
    MAX_ARCS_PER_PAGE,
    MAX_CHARTS_PER_PAGE,
    MAX_H_GRADIENTS_PER_PAGE,
    MAX_NAV,
    MAX_PAGES,
)
from .errors import MakerError
from .geometry import (
    PAGE_ROWS,
    SCREEN_H,
    SCREEN_W,
    card_rect,
    paginate,
    place_section,
)
from .schema import validate_card_config, validate_dashboard_options
from .style import resolve_style

_ICON = re.compile(ICON_RE)
_PATH = re.compile(r"^[a-z0-9_-]{1,32}$")
_PREVIEW_TAG = "custom:apollo-tab-preview"
_CARD_TAG = "custom:apollo-tab-card"
_BOUND_FIELDS = ("value", "min", "max", "step", "text", "confirm")
_TAP_KEYS = ("policy", "local", "page")
_VIEW_EXTRAS = ("header", "sidebar", "footer")


def alias_tag(component_id: str) -> str:
    """Return the dashboard card tag that stands in for a Component."""
    return "apollo-tab-el-" + component_id.replace("/", "-")


def layout_hash(layout: dict) -> str:
    """Return a stable content hash of a layout, ignoring any stored hash."""
    body = {key: value for key, value in layout.items() if key != "hash"}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def convert_dashboard(
    config: dict,
    *,
    components: Mapping[str, dict],
    themes: Mapping[str, dict],
    approved: Set[str],
) -> dict:
    """Return {"layout": ..., "bindings": ..., "warnings": [...], "sources": {...}}.

    sources maps the id of every heading and card drawn on a page, as a
    string, to the [view, section, card] it came from. Never raises for bad
    dashboards.
    """
    if not isinstance(config, dict):
        config = {}
    warnings: list[dict] = []
    sources: dict[str, list] = {}
    options = _options(config, warnings)
    theme_id = options.get("theme", DEFAULT_THEME)
    theme = themes.get(theme_id) or themes.get(DEFAULT_THEME) or {}
    bindings: dict[str, Any] = {"slots": [], "actions": {}}
    pages: list[dict] = []
    nav: list[dict] = []
    if "strategy" in config:
        warnings.append(_warning("strategy_not_supported"))
    else:
        env = {
            "components": components,
            "themes": themes,
            "approved": approved,
            "theme_id": theme_id,
            "wall": theme.get("wall", "#000000"),
            "warnings": warnings,
        }
        views = config.get("views")
        if not isinstance(views, list):
            views = []
        used_bases: set[str] = set()
        for vi, view in enumerate(views):
            view_pages = _convert_view(vi, view, env, used_bases)
            if not view_pages:
                continue
            first = view_pages[0]
            entry = {"page": first["id"], "title": first["title"]}
            if "icon" in first:
                entry["icon"] = first["icon"]
            nav.append(entry)
            pages.extend(view_pages)
        for page in pages:
            _apply_caps(page, warnings)
        if len(pages) > MAX_PAGES:
            del pages[MAX_PAGES:]
            warnings.append(_warning("too_many_pages"))
        kept_ids = {page["id"] for page in pages}
        nav = [entry for entry in nav if entry["page"] in kept_ids]
        if len(nav) > MAX_NAV:
            del nav[MAX_NAV:]
            warnings.append(_warning("too_many_nav"))
    layout: dict[str, Any] = {
        "v": 1,
        "screen": [SCREEN_W, SCREEN_H],
        "theme": {"id": theme_id, **theme},
        "nav": nav,
        "pages": _number_pages(pages, bindings, sources),
    }
    layout["hash"] = layout_hash(layout)
    return {
        "layout": layout,
        "bindings": bindings,
        "warnings": warnings,
        "sources": sources,
    }


def _options(config: dict, warnings: list[dict]) -> dict:
    """Return validated dashboard options, falling back to the defaults."""
    try:
        return validate_dashboard_options(config.get("apollo_tab"))
    except MakerError:
        warnings.append(_warning("invalid_options"))
        return {"version": 1, "theme": DEFAULT_THEME}


def _warning(
    code: str,
    view: int | None = None,
    section: int | None = None,
    card: int | None = None,
    *,
    page: str | None = None,
    rect: list[int] | None = None,
    detail: str = "",
) -> dict:
    """Build one warning record in the shape the panel expects."""
    return {
        "code": code,
        "view": view,
        "section": section,
        "card": card,
        "page": page,
        "r": rect,
        "detail": detail,
    }


def _convert_view(vi: int, view: object, env: dict, used_bases: set[str]) -> list[dict]:
    """Convert one view into a list of placed, not yet numbered pages."""
    warnings = env["warnings"]
    if not isinstance(view, dict):
        return []
    if "strategy" in view:
        warnings.append(_warning("strategy_not_supported", view=vi))
        return []
    if view.get("type") != "sections":
        if not _is_preview_view(view):
            warnings.append(_warning("view_not_sections", view=vi))
        return []
    if view.get("badges") or any(key in view for key in _VIEW_EXTRAS):
        warnings.append(_warning("view_extras_ignored", view=vi))
    if view.get("max_columns", 4) != 3:
        warnings.append(_warning("columns_differ", view=vi))
    sections = view.get("sections")
    if not isinstance(sections, list):
        sections = []
    parts: list[tuple[int, list[dict]]] = []
    for si, section in enumerate(sections):
        for span, items in _convert_section(vi, si, section, env):
            if items:
                parts.append((span, items))
    if not parts:
        return []
    placed = paginate([(span, _height(items, span)) for span, items in parts])
    base = _page_base(view, vi, used_bases)
    title = view.get("title")
    if not (isinstance(title, str) and title):
        title = base
    icon = view.get("icon")
    if not (isinstance(icon, str) and _ICON.match(icon)):
        icon = None
    by_page: dict[int, list] = {}
    for part, (page_index, section_col, band_row) in zip(parts, placed, strict=True):
        by_page.setdefault(page_index, []).append((part, section_col, band_row))
    pages = []
    for page_index in sorted(by_page):
        number = page_index + 1
        page: dict[str, Any] = {
            "id": base if number == 1 else f"{base}-{number}",
            "title": title if number == 1 else f"{title} ({number})",
            "view": vi,
            "items": [],
        }
        if icon:
            page["icon"] = icon
        for (span, items), section_col, band_row in by_page[page_index]:
            positions, _ = place_section(
                [(item["cols"], item["rows"]) for item in items], span
            )
            for item, (col, row) in zip(items, positions, strict=True):
                rect = card_rect(
                    section_col, band_row, col, row, item["cols"], item["rows"]
                )
                page["items"].append({**item, "rect": rect})
        pages.append(page)
    return pages


def _is_preview_view(view: dict) -> bool:
    """Return True when every card of the view is a preview placeholder."""
    cards = view.get("cards")
    if not isinstance(cards, list) or not cards:
        return False
    return all(
        isinstance(card, dict) and card.get("type") == _PREVIEW_TAG for card in cards
    )


def _page_base(view: dict, vi: int, used_bases: set[str]) -> str:
    """Return the base page id for a view, preferring a fresh valid path."""
    path = view.get("path")
    valid = isinstance(path, str) and _PATH.match(path) and path not in used_bases
    base = path if valid else f"view-{vi}"
    used_bases.add(base)
    return base


def _convert_section(
    vi: int, si: int, section: object, env: dict
) -> list[tuple[int, list[dict]]]:
    """Convert one section into a list of (span, items) parts."""
    warnings = env["warnings"]
    if not isinstance(section, dict):
        return []
    if "strategy" in section:
        warnings.append(_warning("strategy_not_supported", vi, si))
        return []
    if "type" in section and section["type"] != "grid":
        warnings.append(_warning("section_not_grid", vi, si))
        return []
    if "sections" in section:
        warnings.append(_warning("nested_section_ignored", vi, si))
    if section.get("visibility"):
        warnings.append(_warning("visibility_ignored", vi, si))
    span = _span(section.get("column_span"))
    items: list[dict] = []
    title = section.get("title")
    if isinstance(title, str) and title:
        items.append(_heading_item(title, span, vi, si, None))
    cards = section.get("cards")
    if not isinstance(cards, list):
        cards = []
    for ci, card in enumerate(cards):
        heading_first = bool(items) and items[0]["kind"] == "heading"
        row_limit = PAGE_ROWS - 1 if heading_first else PAGE_ROWS
        item = _convert_card(vi, si, ci, card, span, row_limit, env)
        if item is not None:
            items.append(item)
    if not items:
        return []
    if _height(items, span) <= PAGE_ROWS:
        return [(span, items)]
    warnings.append(_warning("section_split", vi, si))
    return [(span, part) for part in _split_items(items, span) if part]


def _split_items(items: list[dict], span: int) -> list[list[dict]]:
    """Split items into parts that each fit in PAGE_ROWS rows."""
    heading = items[0] if items[0]["kind"] == "heading" else None
    parts: list[list[dict]] = []
    current: list[dict] = []
    for item in items:
        if current and _height([*current, item], span) > PAGE_ROWS:
            parts.append(current)
            # Later parts repeat the heading so the page stays labelled.
            current = [dict(heading)] if heading is not None else []
            if current and _height([*current, item], span) > PAGE_ROWS:
                parts.append(current)
                current = []
        current = [*current, item]
    if current:
        parts.append(current)
    return parts


def _span(raw: object) -> int:
    """Clamp a raw column_span value to the 1..3 range."""
    try:
        return min(max(int(raw or 1), 1), 3)
    except TypeError, ValueError, OverflowError:
        # int() raises OverflowError for infinity, which YAML can express.
        return 1


def _height(items: list[dict], span: int) -> int:
    """Return the height in rows of the given items in one section column."""
    sizes = [(item["cols"], item["rows"]) for item in items]
    return place_section(sizes, span)[1]


def _heading_item(
    text: object, span: int, vi: int, si: int, ci: int | None, icon: object = None
) -> dict:
    """Build a heading item from a section title or a heading card."""
    item: dict[str, Any] = {
        "kind": "heading",
        "cols": 12 * span,
        "rows": 1,
        "text": str(text or "")[:80],
        "vi": vi,
        "si": si,
        "ci": ci,
    }
    if isinstance(icon, str) and _ICON.match(icon):
        item["icon"] = icon
    return item


def _convert_card(
    vi: int, si: int, ci: int, card: object, span: int, row_limit: int, env: dict
) -> dict | None:
    """Convert one card config into an item, or None when it is left out."""
    warnings = env["warnings"]
    components = env["components"]
    if not isinstance(card, dict):
        warnings.append(_warning("not_tab_element", vi, si, ci))
        return None
    ctype = card.get("type")
    if ctype == "heading":
        if card.get("visibility"):
            warnings.append(_warning("visibility_ignored", vi, si, ci))
        return _heading_item(card.get("heading"), span, vi, si, ci, card.get("icon"))
    if ctype == _PREVIEW_TAG:
        return None
    is_element, component_id = _element_component(ctype, card, components)
    if not is_element:
        detail = ctype if isinstance(ctype, str) else ""
        warnings.append(_warning("not_tab_element", vi, si, ci, detail=detail))
        return None
    if not isinstance(component_id, str) or component_id not in components:
        detail = component_id if isinstance(component_id, str) else ""
        warnings.append(_warning("unknown_component", vi, si, ci, detail=detail))
        return None
    component = components[component_id]
    if (
        component.get("source") == "user"
        and component.get("sensitive")
        and component_id not in env["approved"]
    ):
        warnings.append(_warning("needs_approval", vi, si, ci, detail=component_id))
        return None
    try:
        card_config = validate_card_config(component, card)
    except MakerError as err:
        warnings.append(_warning("invalid_card", vi, si, ci, detail=str(err)))
        return None
    limit = 12 * span
    columns = card_config["columns"]
    if columns == "full":
        columns = limit
    elif columns > limit:
        warnings.append(_warning("card_too_wide", vi, si, ci))
        columns = limit
    rows = card_config["rows"]
    if rows > row_limit:
        warnings.append(_warning("card_too_tall", vi, si, ci))
        rows = row_limit
    card_config = {**card_config, "columns": columns, "rows": rows}
    try:
        compiled = compile_card(component, card_config)
    except MakerError as err:
        if err.code == "params_incomplete":
            warnings.append(_warning("params_incomplete", vi, si, ci))
        else:
            warnings.append(_warning("invalid_card", vi, si, ci, detail=str(err)))
        return None
    if compiled.get("demo"):
        warnings.append(_warning("params_incomplete", vi, si, ci))
    if "element_clipped" in (compiled.get("warnings") or []):
        warnings.append(_warning("element_clipped", vi, si, ci))
    if card.get("visibility"):
        warnings.append(_warning("visibility_ignored", vi, si, ci))
    style = card_config.get("style") or {}
    resolved = None
    if style:
        themes = env["themes"]
        element_theme = style.get("theme", env["theme_id"])
        element = themes.get(element_theme) or themes.get(env["theme_id"]) or {}
        resolved = resolve_style(element, style, env["wall"])
    return {
        "kind": "card",
        "cols": columns,
        "rows": rows,
        "compiled": compiled,
        "component_id": component_id,
        "params": card_config.get("params") or {},
        "style": resolved,
        "vi": vi,
        "si": si,
        "ci": ci,
    }


def _element_component(
    ctype: object, card: dict, components: Mapping[str, dict]
) -> tuple[bool, object]:
    """Return (is_element, component_id) for a card type string."""
    if ctype == _CARD_TAG:
        return True, card.get("component")
    if isinstance(ctype, str) and ctype.startswith("custom:"):
        tag = ctype[len("custom:") :]
        for candidate in components:
            if alias_tag(candidate) == tag:
                return True, candidate
    return False, None


def _apply_caps(page: dict, warnings: list[dict]) -> None:
    """Enforce the per-page chart, arc and gradient budgets on one page."""
    charts = 0
    arcs = 0
    gradients = 0
    kept = []
    for item in page["items"]:
        if item["kind"] != "card":
            kept.append(item)
            continue
        widgets = item["compiled"].get("widgets") or []
        n_charts = sum(
            1 for w in widgets if isinstance(w, dict) and w.get("t") == "chart"
        )
        n_arcs = sum(
            1 for w in widgets if isinstance(w, dict) and w.get("t") == "thermostat"
        )
        if charts + n_charts > MAX_CHARTS_PER_PAGE:
            warnings.append(
                _warning(
                    "over_budget_charts",
                    item["vi"],
                    item["si"],
                    item["ci"],
                    page=page["id"],
                    rect=item["rect"],
                )
            )
            continue
        if arcs + n_arcs > MAX_ARCS_PER_PAGE:
            warnings.append(
                _warning(
                    "over_budget_arcs",
                    item["vi"],
                    item["si"],
                    item["ci"],
                    page=page["id"],
                    rect=item["rect"],
                )
            )
            continue
        charts += n_charts
        arcs += n_arcs
        style = item.get("style")
        if style and style.get("gd") == "h":
            if gradients >= MAX_H_GRADIENTS_PER_PAGE:
                # Flat styles stay readable; the space is already reserved.
                item = {
                    **item,
                    "style": {
                        key: value
                        for key, value in style.items()
                        if key not in ("bg2", "gd")
                    },
                }
                warnings.append(
                    _warning(
                        "over_budget_gradients",
                        item["vi"],
                        item["si"],
                        item["ci"],
                        page=page["id"],
                        rect=item["rect"],
                    )
                )
            else:
                gradients += 1
        kept.append(item)
    page["items"] = kept


def _number_pages(
    pages: list[dict], bindings: dict, sources: dict[str, list]
) -> list[dict]:
    """Assign widget ids and slot numbers, returning the layout pages.

    Records in sources where each numbered heading and card came from, so
    the layout itself does not need to carry that.
    """
    slot_numbers: dict[str, int] = {}
    out_pages = []
    next_id = 1
    for page in pages:
        widgets = []
        for item in page["items"]:
            sources[str(next_id)] = [item["vi"], item["si"], item["ci"]]
            if item["kind"] == "heading":
                built: dict[str, Any] = {
                    "id": next_id,
                    "t": "heading",
                    "r": item["rect"],
                    "text": item["text"],
                }
                next_id += 1
                if item.get("icon"):
                    built["icon"] = item["icon"]
                widgets.append(built)
                continue
            card_out, next_id = _build_card(item, next_id, bindings, slot_numbers)
            widgets.append(card_out)
        out: dict[str, Any] = {
            "id": page["id"],
            "title": page["title"],
            "view": page["view"],
            "w": widgets,
        }
        if page.get("icon"):
            out["icon"] = page["icon"]
        out_pages.append(out)
    return out_pages


def _build_card(
    item: dict, first_id: int, bindings: dict, slot_numbers: dict[str, int]
) -> tuple[dict, int]:
    """Build the layout dict for one card, numbering widgets and slots."""
    compiled = item["compiled"]
    x, y = item["rect"][0], item["rect"][1]
    by_n = {
        slot["n"]: slot
        for slot in compiled.get("slots") or []
        if isinstance(slot, dict) and "n" in slot
    }
    ctx = {"by_n": by_n, "numbers": slot_numbers, "out": bindings["slots"]}
    out: dict[str, Any] = {
        "id": first_id,
        "t": "card",
        "r": item["rect"],
        "component": item["component_id"],
    }
    header = compiled.get("header")
    if isinstance(header, dict):
        hrect = header.get("r") or [0, 0, 0, 0]
        built_header: dict[str, Any] = {
            "r": [hrect[0] + x, hrect[1] + y, hrect[2], hrect[3]]
        }
        if header.get("icon"):
            built_header["icon"] = header["icon"]
        if "title" in header:
            built_header["title"] = _renumber(header["title"], ctx)
        out["header"] = built_header
    if compiled.get("on") is not None:
        out["on"] = _renumber(compiled["on"], ctx)
    if item.get("style"):
        out["style"] = item["style"]
    widget_ids: dict[int, int] = {}
    widgets = []
    next_id = first_id + 1
    for widget in compiled.get("widgets") or []:
        if not isinstance(widget, dict):
            continue
        built_widget = _build_widget(widget, next_id, x, y, ctx)
        widget_ids[widget.get("i", -1)] = next_id
        widgets.append(built_widget)
        next_id += 1
    out["w"] = widgets
    _bind_actions(item, widget_ids, bindings["actions"])
    return out, next_id


def _build_widget(widget: dict, widget_id: int, x: int, y: int, ctx: dict) -> dict:
    """Build the layout dict for one compiled widget with an absolute rect."""
    rect = widget.get("r") or [0, 0, 0, 0]
    built: dict[str, Any] = {
        "id": widget_id,
        "t": widget.get("t"),
        "r": [rect[0] + x, rect[1] + y, rect[2], rect[3]],
    }
    for key in _BOUND_FIELDS:
        if key in widget:
            built[key] = _renumber(widget[key], ctx)
    for key, value in widget.items():
        if key in ("i", "t", "r") or key in _BOUND_FIELDS:
            continue
        if key in ("tap", "change"):
            if isinstance(value, dict):
                filtered = {k: v for k, v in value.items() if k in _TAP_KEYS}
                if filtered:
                    built[key] = filtered
            continue
        built[key] = value
    return built


def _renumber(value: object, ctx: dict) -> object:
    """Map a bound field to its global slot number, registering new slots."""
    if not (isinstance(value, dict) and "s" in value):
        return value
    slot = ctx["by_n"].get(value["s"])
    if slot is None:
        return value
    # Two slots are the same when everything but their number matches.
    identity = json.dumps(
        {key: val for key, val in slot.items() if key != "n"}, sort_keys=True
    )
    if identity not in ctx["numbers"]:
        ctx["numbers"][identity] = len(ctx["out"]) + 1
        ctx["out"].append({**slot, "n": ctx["numbers"][identity]})
    return {"s": ctx["numbers"][identity]}


def _bind_actions(item: dict, widget_ids: dict[int, int], actions_out: dict) -> None:
    """Copy the card's actions into bindings, keyed by the new widget ids."""
    for key, action in (item["compiled"].get("actions") or {}).items():
        if not isinstance(action, dict):
            continue
        index, _, kind = str(key).partition(":")
        try:
            widget_id = widget_ids[int(index)]
        except KeyError, ValueError:
            continue
        actions_out[f"{widget_id}:{kind}"] = {
            "component": item["component_id"],
            "output": action.get("output"),
            "vars": action.get("vars") or {},
            "params": item["params"],
        }
