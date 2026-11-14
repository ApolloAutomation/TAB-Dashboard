"""Convert a sections dashboard into a tablet layout and its bindings."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Set
from typing import Any

from .compile import compile_card
from .compile2 import compile_card2, role_table, validate_card_config2
from .compile2_v1 import compile_card2_v1, level1_names, note_card, variant_of
from .const import (
    DEFAULT_THEME,
    DETAIL_TTL_S,
    ICON_RE,
    MAX_ARCS_PER_PAGE,
    MAX_CHARTS_PER_PAGE,
    MAX_DETAIL_PAGES,
    MAX_H_GRADIENTS_PER_PAGE,
    MAX_NAV,
    MAX_PAGES,
    MAX_TRACKS_PER_PAGE,
    UPDATE_NOTE,
)
from .device import (
    CAPS_DEFAULTS,
    ENGINE_CAPS_V2,
    ContractError,
    compile_device_layout,
)
from .errors import MakerError
from .geometry import (
    CELL_INSET,
    COL_W,
    CONTENT_X,
    PAGE_ROWS,
    PAGE_TOP,
    ROW_H,
    SCREEN_H,
    SCREEN_W,
    card_rect,
    card_size_px,
    paginate,
    place_section,
)
from .schema import validate_card_config, validate_dashboard_options
from .style import paints, resolve_style, status_for, with_accent

_ICON = re.compile(ICON_RE)
_PATH = re.compile(r"^[a-z0-9_-]{1,32}$")
_PREVIEW_TAG = "custom:apollo-tab-preview"
_CARD_TAG = "custom:apollo-tab-card"
_BOUND_FIELDS = ("value", "min", "max", "step", "text", "confirm")
_TAP_KEYS = ("policy", "local", "page")
_VIEW_EXTRAS = ("header", "sidebar", "footer")
# The grid a detail page has for its card, under the heading row.
_DETAIL_COLUMNS = 36
_DETAIL_ROWS = PAGE_ROWS - 1
# Card-level keys of a schema 2 card that the layout v2 carries.
_CARD_KEYS2 = ("on", "tint", "un", "ic", "confirm", "lit")


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
    facts: Mapping[str, dict] | None = None,
    dl: int = 1,
    icons: dict | None = None,
    caps: Mapping[str, Any] | None = None,
    status: Mapping[str, Any] | None = None,
    confirm: Callable[[dict], Mapping[int, str]] | None = None,
) -> dict:
    """Return {"layout", "bindings", "warnings", "sources", "simpler"}.

    sources maps the id of every heading and card drawn on a page, as a
    string, to the [view, section, card] it came from. facts maps an entity
    id to what it can do (maker/features.py), as plain data; schema 1 cards
    do not read it. Never raises for bad dashboards.

    dl is the layout version to make. With 1 (the default) the result is
    today's, byte for byte, for schema 1 cards, and a schema 2 card is
    replaced by its version 1 form (C.6); simpler counts those cards. With
    2 the layout is version 2, with detail pages, subviews and page themes.
    icons is the contract's icons.json: version 1 forms keep only icons of
    level 1 (none without it), so do side bar entries and headings of a
    layout v1 (all are kept without it), and a layout v2 is fitted to caps (a
    tablet's, else what engine 0.2.0 answers) by leaving out detail pages
    and then cards (C.4). Without icons nothing is fitted. status is the
    library's status.json: the colours a card's roles good, warn, bad and
    info take on its theme (without it, those of a dark theme). confirm
    gives, for a layout's bindings, the questions the tablet asks before a
    cover moves, keyed by widget or card id: the sender writes them into the
    device layout, so the fit counts their bytes (C.4).
    """
    if not isinstance(config, dict):
        config = {}
    dl = 2 if dl == 2 else 1
    warnings: list[dict] = []
    options = _options(config, warnings)
    theme_id = options.get("theme", DEFAULT_THEME)
    theme = themes.get(theme_id) or themes.get(DEFAULT_THEME) or {}
    if "accent" in options and theme:
        theme = with_accent(theme, options["accent"])
    pages: list[dict] = []
    nav: list[dict] = []
    details: list[dict] = []
    simpler = [0]
    if "strategy" in config:
        warnings.append(_warning("strategy_not_supported"))
    else:
        env = {
            "components": components,
            "themes": themes,
            "approved": approved,
            "facts": facts or {},
            "theme_id": theme_id,
            "theme": theme,
            "wall": theme.get("wall", "#000000"),
            "status": status,
            "warnings": warnings,
            "dl": dl,
            "level1": level1_names(icons),
            "simpler": simpler,
        }
        views = config.get("views")
        if not isinstance(views, list):
            views = []
        used_bases: set[str] = set()
        for vi, view in enumerate(views):
            view_pages = _convert_view(vi, view, env, used_bases)
            if not view_pages:
                continue
            if dl == 2 and pages and _is_subview(view):
                # A detail page: no side bar entry, gone again at once.
                for page in view_pages:
                    page["sub"] = 1
                    page["ttl"] = 0
                pages.extend(view_pages)
                continue
            first = view_pages[0]
            entry = {"page": first["id"], "title": first["title"]}
            if "icon" in first:
                entry["icon"] = first["icon"]
            nav.append(entry)
            pages.extend(view_pages)
        for page in pages:
            _apply_caps(page, warnings, dl)
        normal = [page for page in pages if not page.get("sub")]
        if len(normal) > MAX_PAGES:
            cut = {page["id"] for page in normal[MAX_PAGES:]}
            pages = [page for page in pages if page["id"] not in cut]
            warnings.append(_warning("too_many_pages"))
        kept_ids = {page["id"] for page in pages}
        nav = [entry for entry in nav if entry["page"] in kept_ids]
        if len(nav) > MAX_NAV:
            del nav[MAX_NAV:]
            warnings.append(_warning("too_many_nav"))
        if dl == 2:
            subviews = sum(1 for page in pages if page.get("sub"))
            details = _detail_pages(pages, env, MAX_DETAIL_PAGES - subviews)
        elif icons is not None:
            _level1_icons_only(nav, pages, env["level1"])
    head = {
        "v": dl,
        "screen": [SCREEN_W, SCREEN_H],
        "theme": {"id": theme_id, **theme},
        "nav": nav,
    }
    if dl == 2 and icons is not None:
        layout, bindings, sources = _fit(
            head, pages, details, warnings, icons, caps, confirm
        )
    else:
        layout, bindings, sources = _assemble(head, pages, details)
    return {
        "layout": layout,
        "bindings": bindings,
        "warnings": warnings,
        "sources": sources,
        "simpler": simpler[0],
    }


def _level1_icons_only(nav: list[dict], pages: list[dict], level1: Set[str]) -> None:
    """Leave out side bar and heading icons a version 1 tablet does not hold.

    Engine 0.1.0 holds the icons of level 1 and draws the fallback glyph (a
    question mark) for any other. A side bar entry without its icon gets
    the icon a page without one gets; a heading shows its text alone. The
    page keeps the icon the person picked.
    """
    for entry in nav:
        if entry.get("icon") is not None and entry["icon"] not in level1:
            del entry["icon"]
    for page in pages:
        for item in page["items"]:
            if item["kind"] != "heading":
                continue
            if item.get("icon") is not None and item["icon"] not in level1:
                del item["icon"]


def _is_subview(view: object) -> bool:
    """Return whether a view is a Home Assistant subview."""
    return isinstance(view, dict) and view.get("subview") is True


def _assemble(
    head: dict, pages: list[dict], details: list[dict], kept: int | None = None
) -> tuple[dict, dict, dict]:
    """Return (layout, bindings, sources) with every page numbered.

    kept is how many of the detail pages stay, from the front; the openers
    of the others are left out.
    """
    bindings: dict[str, Any] = {"slots": [], "actions": {}}
    sources: dict[str, list] = {}
    live = _live_details(pages, details)
    if kept is not None:
        live = live[:kept]
    detail_ids = {detail["key"]: detail["page"]["id"] for detail in live}
    all_pages = [*pages, *(detail["page"] for detail in live)]
    layout: dict[str, Any] = {
        **head,
        "pages": _number_pages(all_pages, bindings, sources, detail_ids),
    }
    layout["hash"] = layout_hash(layout)
    return layout, bindings, sources


def _live_details(pages: list[dict], details: list[dict]) -> list[dict]:
    """Return the detail pages that still have an opener on a page."""
    keys = {
        item.get("detail_key")
        for page in pages
        for item in page["items"]
        if item.get("detail_key")
    }
    return [detail for detail in details if detail["key"] in keys]


def _fit(
    head: dict,
    pages: list[dict],
    details: list[dict],
    warnings: list[dict],
    icons: dict,
    caps: Mapping[str, Any] | None,
    confirm: Callable[[dict], Mapping[int, str]] | None = None,
) -> tuple[dict, dict, dict]:
    """Assemble a layout v2 that fits the tablet (the over-a-limit rule, C.4).

    Detail pages are left out from the end, with their openers, until the
    layout fits; if it still does not, whole cards from the end of the last
    page. Each step is found by halving, so a big dashboard is compiled a
    few times, not once per page.
    """
    caps = dict(caps) if caps is not None else dict(ENGINE_CAPS_V2)

    def fits(layout: dict, bindings: dict) -> dict | None:
        """Return the compiled device layout, or None when it is too big.

        With the questions the sender adds, so what fits here fits there.
        """
        questions = dict(confirm(bindings)) if confirm is not None else None
        try:
            return compile_device_layout(layout, icons, caps, confirm=questions)
        except ContractError as err:
            if err.code in ("limits", "too_big"):
                return None
            raise

    def attempt(kept: int | None, cut: int) -> tuple[tuple, dict | None]:
        trimmed = _without_last_cards(pages, cut)
        built = _assemble(head, trimmed, details, kept)
        try:
            return built, fits(built[0], built[1])
        except ContractError:
            # Not a matter of size: the sender reports it for the tablet.
            return built, {}

    built, device = attempt(None, 0)
    live = _live_details(pages, details)
    kept = len(live)
    cut = 0
    if device is None:
        low, high = 0, len(live) - 1
        best = None
        while low <= high:
            middle = (low + high) // 2
            trial, device = attempt(middle, 0)
            if device is not None:
                best = (middle, trial, device)
                low = middle + 1
            else:
                high = middle - 1
        if best is not None:
            kept, built, device = best
        else:
            kept = 0
            cards = sum(_card_count(page) for page in pages)
            low, high = 1, cards
            found = None
            while low <= high:
                middle = (low + high) // 2
                trial, device = attempt(0, middle)
                if device is not None:
                    found = (middle, trial, device)
                    high = middle - 1
                else:
                    low = middle + 1
            if found is not None:
                cut, built, device = found
            else:
                built, device = attempt(0, 0)
        for detail in live[kept:]:
            warnings.append(_detail_warning(detail))
        for page, item in _last_cards(pages, cut):
            warnings.append(
                _warning(
                    "card_left_out",
                    item["vi"],
                    item["si"],
                    item["ci"],
                    page=page["id"],
                    rect=item["rect"],
                )
            )
    # A tablet that leaves max_stored out keeps the contract's default.
    try:
        stored = int(caps.get("max_stored", CAPS_DEFAULTS["max_stored"]) or 0)
    except TypeError, ValueError, OverflowError:
        stored = 0
    if device and device.get("size", 0) > stored:
        warnings.append(
            _warning("not_kept", detail=f"{device['size']} bytes, kept up to {stored}")
        )
    return built


def _card_count(page: dict) -> int:
    """Return how many cards a page holds."""
    return sum(1 for item in page["items"] if item["kind"] == "card")


def _last_cards(pages: list[dict], count: int) -> list[tuple[dict, dict]]:
    """Return the last count cards of the normal pages, from the end."""
    out: list[tuple[dict, dict]] = []
    for page in reversed(pages):
        if page.get("sub"):
            continue
        for item in reversed(page["items"]):
            if len(out) >= count:
                return out
            if item["kind"] == "card":
                out.append((page, item))
    return out


def _without_last_cards(pages: list[dict], count: int) -> list[dict]:
    """Return the pages without their last count cards."""
    if count <= 0:
        return pages
    gone = {id(item) for _page, item in _last_cards(pages, count)}
    return [
        {**page, "items": [item for item in page["items"] if id(item) not in gone]}
        for page in pages
    ]


def _detail_warning(detail: dict) -> dict:
    """Return the warning for a detail page that is left out."""
    item = detail["opener"]
    return _warning(
        "too_many_details",
        item["vi"],
        item["si"],
        item["ci"],
        page=detail["from"],
        rect=item["rect"],
        detail=detail["name"],
    )


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
    page_theme = _page_theme(view, env)
    env["page_theme"] = page_theme
    parts: list[tuple[int, list[dict]]] = []
    for si, section in enumerate(sections):
        for span, items in _convert_section(vi, si, section, env):
            if items:
                parts.append((span, items))
    base = _page_base(view, vi, used_bases)
    title = view.get("title")
    if not (isinstance(title, str) and title):
        title = base
    icon = view.get("icon")
    if not (isinstance(icon, str) and _ICON.match(icon)):
        icon = None
    if not parts:
        # A page with no cards stays, with its side bar entry, so the tablet
        # has the same pages as the editor.
        page: dict[str, Any] = {"id": base, "title": title, "view": vi, "items": []}
        if icon:
            page["icon"] = icon
        if page_theme is not None:
            page["theme"] = page_theme
        return [page]
    placed = paginate([(span, _height(items, span)) for span, items in parts])
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
        if page_theme is not None:
            page["theme"] = page_theme
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


def _page_theme(view: dict, env: dict) -> dict | None:
    """Return the theme entry a view names for its pages (layout v2 only).

    A view that names the dashboard's own theme gets it with the
    dashboard's accent.
    """
    if env["dl"] != 2:
        return None
    options = view.get("apollo_tab")
    theme_id = options.get("theme") if isinstance(options, dict) else None
    entry = env["themes"].get(theme_id) if isinstance(theme_id, str) else None
    if not isinstance(entry, dict):
        return None
    if theme_id == env["theme_id"]:
        entry = env["theme"]
    return {"id": theme_id, **entry}


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
    if component.get("schema") == 2:
        return _convert_card2(
            (vi, si, ci), card, component_id, component, span, row_limit, env
        )
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
    if paints(style):
        resolved = resolve_style(_element_theme(style, env), style, _page_wall(env))
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


def _element_theme(style: dict, env: dict) -> dict:
    """Return the theme entry a card's style is resolved against.

    The style's own theme, else the page's (layout v2), else the dashboard's
    (with the dashboard's accent).
    """
    themes = env["themes"]
    page_theme = env.get("page_theme")
    if "theme" in style:
        named = themes.get(style["theme"])
        if named:
            return named
    elif page_theme is not None:
        return {key: value for key, value in page_theme.items() if key != "id"}
    return env["theme"]


def _element_status(style: dict, env: dict) -> dict:
    """Return the status colours of the theme a card's style is resolved against."""
    page_theme = env.get("page_theme")
    if "theme" in style and env["themes"].get(style["theme"]):
        theme_id = style["theme"]
    elif "theme" not in style and page_theme is not None:
        theme_id = page_theme["id"]
    else:
        theme_id = env["theme_id"]
    dark = bool(_element_theme(style, env).get("dark"))
    return status_for(env.get("status"), theme_id, dark)


def _page_wall(env: dict) -> str:
    """Return the wall of the page being made: its own theme's, else the layout's."""
    page_theme = env.get("page_theme")
    if page_theme is not None and isinstance(page_theme.get("wall"), str):
        return page_theme["wall"]
    return env["wall"]


def _card_size(
    where: tuple, cfg: dict, span: int, row_limit: int, warnings: list[dict]
) -> tuple[int, int]:
    """Clamp a card's grid size to its section, as for every card."""
    limit = 12 * span
    columns = cfg["columns"]
    if columns == "full":
        columns = limit
    elif columns > limit:
        warnings.append(_warning("card_too_wide", *where))
        columns = limit
    rows = cfg["rows"]
    if rows > row_limit:
        warnings.append(_warning("card_too_tall", *where))
        rows = row_limit
    return columns, rows


def _convert_card2(
    where: tuple,
    card: dict,
    component_id: str,
    component: dict,
    span: int,
    row_limit: int,
    env: dict,
) -> dict | None:
    """Convert one schema 2 card: its version 1 form, or itself for layout v2."""
    warnings = env["warnings"]
    try:
        cfg = validate_card_config2(component, card)
    except MakerError as err:
        warnings.append(_warning("invalid_card", *where, detail=str(err)))
        return None
    columns, rows = _card_size(where, cfg, span, row_limit, warnings)
    cfg = {**cfg, "columns": columns, "rows": rows}
    style = cfg.get("style") or {}
    element = _element_theme(style, env)
    resolved = resolve_style(element, style, _page_wall(env)) if paints(style) else None
    roles = role_table({**element, **(resolved or {})}, _element_status(style, env))
    item: dict[str, Any] = {
        "kind": "card",
        "cols": columns,
        "rows": rows,
        "component_id": component_id,
        "params": cfg["params"],
        "style": resolved,
        "vi": where[0],
        "si": where[1],
        "ci": where[2],
    }
    if env["dl"] == 1:
        env["simpler"][0] += 1
        compiled, used_id, params = _v1_form(component, cfg, card, env)
        item.update(component_id=used_id, params=params)
    else:
        try:
            compiled = compile_card2(component, cfg, env["facts"], 2, roles=roles)
        except MakerError as err:
            code = "params_incomplete" if err.code == "params_incomplete" else None
            warnings.append(
                _warning(
                    code or "invalid_card", *where, detail="" if code else str(err)
                )
            )
            return None
        item["schema"] = 2
        if compiled.get("opener") and component.get("detail"):
            item["detail_key"] = _detail_key(component_id, cfg)
            item["detail_source"] = {
                "component": component,
                "cfg": cfg,
                "roles": roles,
                "facts": env["facts"],
            }
    if compiled.get("demo"):
        warnings.append(_warning("params_incomplete", *where))
    if "element_clipped" in (compiled.get("warnings") or []):
        warnings.append(_warning("element_clipped", *where))
    if "tap_left_out" in (compiled.get("warnings") or []):
        warnings.append(_warning("tap_left_out", *where))
    if card.get("visibility"):
        warnings.append(_warning("visibility_ignored", *where))
    item["compiled"] = compiled
    return item


def _v1_form(
    component: dict, cfg: dict, card: dict, env: dict
) -> tuple[dict, str, dict]:
    """Return (compiled, component id, params) of a card's version 1 form (C.6).

    1. The old card the variant names, when it is there (and allowed), takes
       the card's params and fits the variant's grid.
    2. Else the variant itself, with version 1 keys only.
    3. Else, or when the variant says so, the note.
    """
    variant = component["variants"][variant_of(component, cfg)]
    target = variant.get("v1") or component.get("v1")
    if target == "note":
        return note_card(component, cfg, UPDATE_NOTE), component["id"], cfg["params"]
    if isinstance(target, str):
        old = _old_card(target, component, variant, cfg, card, env)
        if old is not None:
            return old
    try:
        form = compile_card2_v1(component, cfg, env["facts"], level1=env["level1"])
    except MakerError:
        form = None
    if form is None:
        return note_card(component, cfg, UPDATE_NOTE), component["id"], cfg["params"]
    return form, component["id"], cfg["params"]


def _old_card(
    target: str, component: dict, variant: dict, cfg: dict, card: dict, env: dict
) -> tuple[dict, str, dict] | None:
    """Compile the schema 1 card a variant names, when all three rules hold.

    A sensitive old card (a lock or an alarm, whoever wrote it) stands in
    only for a built-in card or an approved file from the person's folder:
    else a file without an action of its own could put Unlock on a version
    1 tablet with no admin's approval.
    """
    old = env["components"].get(target)
    if not isinstance(old, dict) or old.get("schema", 1) != 1:
        return None
    sensitive = old.get("source") == "user" and old.get("sensitive")
    if sensitive and target not in env["approved"]:
        return None
    if (
        old.get("sensitive")
        and component.get("source") == "user"
        and component["id"] not in env["approved"]
    ):
        return None
    size = old.get("size") or [1, 1]
    grid = variant["grid"]
    if size[0] * 6 > grid[0] or size[1] * 3 > grid[1]:
        return None
    params = {
        name: value for name, value in cfg["params"].items() if name in old["params"]
    }
    raw = {"params": params, "style": card.get("style")}
    if cfg["title"] is not None:
        raw["title"] = cfg["title"]
    if isinstance(raw["style"], dict):
        raw["style"] = {
            key: value
            for key, value in raw["style"].items()
            if key not in ("lit", "tint")
        }
    try:
        old_cfg = validate_card_config(old, raw)
        old_cfg = {**old_cfg, "columns": cfg["columns"], "rows": cfg["rows"]}
        compiled = compile_card(old, old_cfg)
    except MakerError:
        return None
    return compiled, target, old_cfg.get("params") or {}


def _detail_key(component_id: str, cfg: dict) -> str:
    """Return what makes two cards the same for their detail page."""
    body = {
        "component": component_id,
        "params": cfg["params"],
        "options": cfg["options"],
        "standard": cfg["standard"],
        "style": cfg["style"],
        "look": cfg["look"],
    }
    return json.dumps(body, sort_keys=True, default=str)


def _detail_pages(pages: list[dict], env: dict, limit: int) -> list[dict]:
    """Make one detail page for each different card that has an opener (C.4).

    Page ids are "<page id>~<n>", in dashboard order. Past limit the
    openers are left out with too_many_details.
    """
    warnings = env["warnings"]
    details: list[dict] = []
    seen: set[str] = set()
    counters: dict[str, int] = {}
    for page in pages:
        for item in page["items"]:
            key = item.get("detail_key")
            if not key or key in seen:
                continue
            seen.add(key)
            source = item.pop("detail_source")
            component = source["component"]
            cfg = source["cfg"]
            name = cfg["title"] if cfg["title"] is not None else component["name"]
            detail = {"key": key, "from": page["id"], "opener": item, "name": name}
            if len(details) >= max(limit, 0):
                warnings.append(_detail_warning(detail))
                continue
            built = _detail_page(page, item, source, name, counters)
            if built is None:
                continue
            _apply_caps(built, warnings, 2)
            detail["page"] = built
            details.append(detail)
    for page in pages:
        for item in page["items"]:
            item.pop("detail_source", None)
    return details


def _detail_page(
    page: dict, item: dict, source: dict, name: str, counters: dict[str, int]
) -> dict | None:
    """Build one detail page: a heading with the card's name, the card under it."""
    component = source["component"]
    variant = component["variants"][component["detail"]]
    columns = min(variant["grid"][0], _DETAIL_COLUMNS)
    rows = min(variant["grid"][1], _DETAIL_ROWS)
    cfg = {**source["cfg"], "columns": columns, "rows": rows}
    try:
        compiled = compile_card2(
            component, cfg, source["facts"], 2, roles=source["roles"], detail=True
        )
    except MakerError:
        return None
    counters[page["id"]] = counters.get(page["id"], 0) + 1
    width, height = card_size_px(columns, rows)
    left = CONTENT_X + (SCREEN_W - CONTENT_X - columns * COL_W) // 2 + CELL_INSET
    heading_h = ROW_H - 2 * CELL_INSET
    top = PAGE_TOP + CELL_INSET
    where = {"vi": item["vi"], "si": item["si"], "ci": item["ci"]}
    heading = {
        "kind": "heading",
        "text": name[:80],
        "rect": [left, top, width, heading_h],
        **where,
    }
    copy = {
        **item,
        "compiled": compiled,
        "rect": [left, top + ROW_H, width, height],
        "cols": columns,
        "rows": rows,
    }
    copy.pop("detail_key", None)
    return {
        "id": f"{page['id']}~{counters[page['id']]}",
        "title": name,
        "view": page["view"],
        "sub": 1,
        "ttl": DETAIL_TTL_S,
        "items": [heading, copy],
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


def _apply_caps(page: dict, warnings: list[dict], dl: int = 1) -> None:
    """Enforce the per-page chart, arc and gradient budgets on one page.

    In a layout v2 a page also has at most MAX_TRACKS_PER_PAGE sliders
    with a track; a slider past that loses its track (C.3).
    """
    charts = 0
    arcs = 0
    gradients = 0
    tracks = 0
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
        if dl == 2:
            item, tracks = _cap_tracks(page, item, tracks, warnings)
        kept.append(item)
    page["items"] = kept


def _cap_tracks(
    page: dict, item: dict, tracks: int, warnings: list[dict]
) -> tuple[dict, int]:
    """Take the track off the sliders of a card past the page's budget."""
    widgets = item["compiled"].get("widgets") or []
    over = False
    out = []
    for widget in widgets:
        if (
            isinstance(widget, dict)
            and widget.get("t") == "slider"
            and "track" in widget
        ):
            if tracks >= MAX_TRACKS_PER_PAGE:
                widget = {key: value for key, value in widget.items() if key != "track"}
                over = True
            else:
                tracks += 1
        out.append(widget)
    if not over:
        return item, tracks
    warnings.append(
        _warning(
            "over_budget_tracks",
            item["vi"],
            item["si"],
            item["ci"],
            page=page["id"],
            rect=item["rect"],
        )
    )
    return {**item, "compiled": {**item["compiled"], "widgets": out}}, tracks


def _number_pages(
    pages: list[dict],
    bindings: dict,
    sources: dict[str, list],
    detail_ids: dict[str, str] | None = None,
) -> list[dict]:
    """Assign widget ids and slot numbers, returning the layout pages.

    Records in sources where each numbered heading and card came from, so
    the layout itself does not need to carry that. detail_ids maps a
    card's detail key to the id of its detail page (layout v2).
    """
    detail_ids = detail_ids or {}
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
            if item.get("schema") == 2:
                card_out, next_id = _build_card2(
                    item, next_id, bindings, slot_numbers, detail_ids
                )
            else:
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
        for key in ("sub", "ttl", "theme"):
            if key in page:
                out[key] = page[key]
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
    """Copy the card's actions into bindings, keyed by the new widget ids.

    Each entry also carries the card's demo flag and its entities, so a tap
    from a tablet is checked like a call from the browser, which gets both
    from compiling the card.
    """
    compiled = item["compiled"]
    demo = bool(compiled.get("demo"))
    entities = [
        entity for entity in compiled.get("entities") or [] if isinstance(entity, str)
    ]
    for key, action in (compiled.get("actions") or {}).items():
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
            "demo": demo,
            "entities": list(entities),
        }
        _bind_call(compiled, key, actions_out[f"{widget_id}:{kind}"])


# ------------------------------------------------------------- layout v2


def _build_card2(
    item: dict,
    first_id: int,
    bindings: dict,
    slot_numbers: dict[str, int],
    detail_ids: dict[str, str],
) -> tuple[dict, int]:
    """Build the layout v2 dict of one schema 2 card, numbering widgets and slots.

    `{"local": "detail"}` becomes the way to the card's detail page, or is
    left out when the card has none; a widget that only opens it goes too.
    """
    compiled = item["compiled"]
    x, y = item["rect"][0], item["rect"][1]
    by_n = {
        slot["n"]: slot
        for slot in compiled.get("slots") or []
        if isinstance(slot, dict) and "n" in slot
    }
    ctx = {"by_n": by_n, "numbers": slot_numbers, "out": bindings["slots"]}
    page = detail_ids.get(item.get("detail_key") or "")
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
            built_header["title"] = _renumber2(header["title"], ctx)
        out["header"] = built_header
    for key in _CARD_KEYS2:
        if compiled.get(key) is not None:
            out[key] = _renumber2(compiled[key], ctx)
    tap = _local_tap(compiled.get("tap"), page)
    if tap is not None:
        out["tap"] = tap
    else:
        out.pop("confirm", None)
    hold = _local_tap(compiled.get("hold"), page)
    if hold is not None:
        out["hold"] = hold
    if item.get("style"):
        out["style"] = item["style"]
    widget_ids: dict[int, int] = {}
    widgets = []
    next_id = first_id + 1
    for widget in compiled.get("widgets") or []:
        if not isinstance(widget, dict):
            continue
        built_widget = _build_widget2(widget, next_id, x, y, ctx, page)
        if built_widget is None:
            continue
        widget_ids[widget.get("i", -1)] = next_id
        widgets.append(built_widget)
        next_id += 1
    out["w"] = widgets
    _bind_actions2(item, first_id, widget_ids, bindings["actions"])
    return out, next_id


def _local_tap(value: object, detail_page: str | None) -> dict | None:
    """Return a tap, change or hold as the layout keeps it.

    A detail opener goes to the card's detail page, or is None without one.
    """
    if not isinstance(value, dict):
        return None
    if value.get("local") == "detail":
        if detail_page is None:
            return None
        return {"local": "go_to_page", "page": detail_page}
    filtered = {k: v for k, v in value.items() if k in _TAP_KEYS}
    return filtered or None


def _build_widget2(
    widget: dict, widget_id: int, x: int, y: int, ctx: dict, page: str | None
) -> dict | None:
    """Build the layout v2 dict of one widget; None for an opener with no page."""
    rect = widget.get("r") or [0, 0, 0, 0]
    built: dict[str, Any] = {
        "id": widget_id,
        "t": widget.get("t"),
        "r": [rect[0] + x, rect[1] + y, rect[2], rect[3]],
    }
    for key, value in widget.items():
        if key in ("i", "t", "r"):
            continue
        if key in ("tap", "change", "hold"):
            local = _local_tap(value, page)
            if local is not None:
                built[key] = local
            elif key == "tap" and _opens_detail(value):
                # A widget whose only work is to open the detail page.
                return None
            continue
        built[key] = _renumber2(value, ctx)
    if "confirm" in built and "tap" not in built and "change" not in built:
        del built["confirm"]
    return built


def _opens_detail(value: object) -> bool:
    """Return whether a tap opens the card's detail page."""
    return isinstance(value, dict) and value.get("local") == "detail"


def _renumber2(value: object, ctx: dict) -> object:
    """Map a bound field to its global slot number; a colour keeps its roles."""
    if not (isinstance(value, dict) and "s" in value):
        return value
    slot = ctx["by_n"].get(value["s"])
    if slot is None:
        return value
    identity = json.dumps(
        {key: val for key, val in slot.items() if key != "n"},
        sort_keys=True,
        default=str,
    )
    if identity not in ctx["numbers"]:
        ctx["numbers"][identity] = len(ctx["out"]) + 1
        ctx["out"].append({**slot, "n": ctx["numbers"][identity]})
    return {**value, "s": ctx["numbers"][identity]}


def _bind_actions2(
    item: dict, card_id: int, widget_ids: dict[int, int], actions_out: dict
) -> None:
    """Copy a schema 2 card's actions into bindings, keyed by the new ids.

    The card's own tap is kept under the card's id. A choice keeps its
    whole option values, server side (C.4).
    """
    compiled = item["compiled"]
    demo = bool(compiled.get("demo"))
    entities = [
        entity for entity in compiled.get("entities") or [] if isinstance(entity, str)
    ]
    for key, action in (compiled.get("actions") or {}).items():
        if not isinstance(action, dict):
            continue
        index, _, kind = str(key).partition(":")
        if index == "card":
            target = card_id
        else:
            try:
                target = widget_ids[int(index)]
            except KeyError, ValueError:
                continue
        entry = {
            "component": item["component_id"],
            "output": action.get("output"),
            "vars": action.get("vars") or {},
            "params": item["params"],
            "demo": demo,
            "entities": list(entities),
        }
        if "options" in action:
            entry["options"] = action["options"]
        _bind_call(compiled, key, entry)
        actions_out[f"{target}:{kind}"] = entry


def _bind_call(compiled: dict, key: str, entry: dict) -> None:
    """Add what a schema 2 call reads to its binding (C.2.8).

    The options and facts a data template may read, and the slots of the
    inputs its output lists in `uses`; all of it data. A version 1 form of
    a schema 2 card has them too: its outputs run in Home Assistant alike.
    """
    call = compiled.get("call")
    if not isinstance(call, dict):
        return
    if "values" in call:
        entry["values"] = call["values"]
    if key in (call.get("uses") or {}):
        entry["uses"] = call["uses"][key]
