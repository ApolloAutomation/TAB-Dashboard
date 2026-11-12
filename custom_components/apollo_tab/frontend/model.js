import { cleanConfig, isIcon } from "./logic.js";

export const CARD_TYPE = "custom:apollo-tab-card";
export const PREVIEW_TYPE = "custom:apollo-tab-preview";
export const ALIAS_PREFIX = "custom:apollo-tab-el-";
export const UNIT_COLUMNS = 6;
export const UNIT_ROWS = 3;
export const MAX_UNITS_HIGH = 4;
// A card as wide as the screen: three columns of two units each.
export const MAX_UNITS_WIDE = 6;
export const MAX_ENTITIES = 8;
export const HISTORY_LIMIT = 50;
export const DEFAULT_THEME = "midnight";
export const GROUP_IDS = [
  "lights",
  "climate",
  "media",
  "security",
  "sensors",
  "rooms",
  "more",
];
export const PAGE_ICONS = [
  "mdi:home",
  "mdi:sofa",
  "mdi:bed",
  "mdi:silverware-fork-knife",
  "mdi:shower",
  "mdi:lightbulb",
  "mdi:thermometer",
  "mdi:shield-home",
  "mdi:speaker",
  "mdi:television",
  "mdi:garage",
  "mdi:flower",
  "mdi:desk",
  "mdi:baby-face-outline",
  "mdi:washing-machine",
  "mdi:weather-partly-cloudy",
  "mdi:cctv",
  "mdi:lightning-bolt",
  "mdi:music",
  "mdi:star",
  "mdi:view-dashboard",
];
// The plain name of each page icon (a key in strings.json). The icon picker
// uses it as the button's name and tooltip, so nobody has to guess what a
// picture stands for or hear its icon id read out.
export const PAGE_ICON_NAMES = {
  "mdi:home": "page.icon_name.home",
  "mdi:sofa": "page.icon_name.living",
  "mdi:bed": "page.icon_name.bedroom",
  "mdi:silverware-fork-knife": "page.icon_name.kitchen",
  "mdi:shower": "page.icon_name.bathroom",
  "mdi:lightbulb": "page.icon_name.lights",
  "mdi:thermometer": "page.icon_name.temperature",
  "mdi:shield-home": "page.icon_name.security",
  "mdi:speaker": "page.icon_name.speakers",
  "mdi:television": "page.icon_name.tv",
  "mdi:garage": "page.icon_name.garage",
  "mdi:flower": "page.icon_name.garden",
  "mdi:desk": "page.icon_name.office",
  "mdi:baby-face-outline": "page.icon_name.baby",
  "mdi:washing-machine": "page.icon_name.laundry",
  "mdi:weather-partly-cloudy": "page.icon_name.weather",
  "mdi:cctv": "page.icon_name.cameras",
  "mdi:lightning-bolt": "page.icon_name.energy",
  "mdi:music": "page.icon_name.music",
  "mdi:star": "page.icon_name.favourites",
  "mdi:view-dashboard": "page.icon_name.overview",
};

const ITEM_REASON_CODES = new Set([
  "needs_approval",
  "invalid_card",
  "over_budget_charts",
  "over_budget_arcs",
  "unknown_component",
]);

const ITEM_NOTE_CODES = new Set([
  "params_incomplete",
  "element_clipped",
  "card_too_wide",
  "card_too_tall",
  "over_budget_gradients",
  "visibility_ignored",
]);

const PAGE_NOTE_CODES = new Set([
  "view_extras_ignored",
  "section_not_grid",
  "nested_section_ignored",
  "strategy_not_supported",
  "visibility_ignored",
]);

const DASHBOARD_NOTE_CODES = new Set([
  "invalid_options",
  "strategy_not_supported",
  "too_many_pages",
  "too_many_nav",
]);

// Kinds of card the tablet can never draw, whatever their settings.
const NEVER_SHOWN_KINDS = new Set([
  "other",
  "old_preview",
  "tab_missing",
]);

const ENTITY_ID_RE = /^[a-z0-9_]+\.[a-z0-9_]+$/;

const LIGHT_DOMAINS = new Set([
  "light",
  "switch",
  "scene",
  "input_boolean",
]);

const CLIMATE_DOMAINS = new Set([
  "climate",
  "fan",
  "cover",
  "humidifier",
  "water_heater",
  "valve",
]);

const SECURITY_DOMAINS = new Set([
  "lock",
  "alarm_control_panel",
  "camera",
  "siren",
]);

const SENSOR_DOMAINS = new Set([
  "sensor",
  "binary_sensor",
  "weather",
  "number",
  "input_number",
]);

const ROOM_DOMAINS = new Set([
  "person",
  "device_tracker",
  "zone",
]);

function isPlainObject(value) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value);
}

function stableValue(value, inArray = false) {
  if (value === undefined) {
    return inArray ? null : undefined;
  }

  if (Array.isArray(value)) {
    return value.map((item) => stableValue(item, true));
  }

  if (isPlainObject(value)) {
    const result = {};
    for (const key of Object.keys(value).sort()) {
      const item = stableValue(value[key], false);
      if (item !== undefined) {
        result[key] = item;
      }
    }
    return result;
  }

  return value;
}

function clampInteger(value, min, max) {
  const rounded = Number.isFinite(value) ? Math.round(value) : min;
  return Math.min(max, Math.max(min, rounded));
}

function configViews(config) {
  return isPlainObject(config) && Array.isArray(config.views)
    ? config.views
    : [];
}

function sourceParts(source) {
  if (!Array.isArray(source) || source.length !== 3) {
    return null;
  }

  const [vi, si, ci] = source;
  if (!Number.isInteger(vi) || !Number.isInteger(si)) {
    return null;
  }
  if (ci !== null && !Number.isInteger(ci)) {
    return null;
  }

  return [vi, si, ci];
}

function sectionAt(config, vi, si) {
  const views = configViews(config);
  const view = views[vi];
  if (!isPlainObject(view) || !Array.isArray(view.sections)) {
    return null;
  }

  return isPlainObject(view.sections[si]) ? view.sections[si] : null;
}

function cardAt(config, source) {
  const parts = sourceParts(source);
  if (parts === null || parts[2] === null) {
    return null;
  }

  const [vi, si, ci] = parts;
  const section = sectionAt(config, vi, si);
  if (!section || !Array.isArray(section.cards)) {
    return null;
  }

  return ci >= 0 && ci < section.cards.length
    ? section.cards[ci]
    : null;
}

function sameSource(a, b) {
  return Array.isArray(a)
    && Array.isArray(b)
    && a.length === 3
    && b.length === 3
    && a[0] === b[0]
    && a[1] === b[1]
    && a[2] === b[2];
}

function warningAt(warning, vi, si, ci) {
  return isPlainObject(warning)
    && warning.view === vi
    && warning.section === si
    && warning.card === ci;
}

function warningList(preview) {
  return isPlainObject(preview) && Array.isArray(preview.warnings)
    ? preview.warnings
    : [];
}

function componentGridValue(component, key, sizeIndex, fallback) {
  if (isPlainObject(component) && isPlainObject(component.grid)) {
    return component.grid[key];
  }

  if (
    isPlainObject(component)
    && Array.isArray(component.size)
    && Number.isFinite(component.size[sizeIndex])
  ) {
    const multiplier = key === "columns" ? UNIT_COLUMNS : UNIT_ROWS;
    return component.size[sizeIndex] * multiplier;
  }

  return fallback;
}

function uniqueWarningCodes(warnings, predicate) {
  const result = [];
  const seen = new Set();

  for (const warning of warnings) {
    if (
      isPlainObject(warning)
      && typeof warning.code === "string"
      && predicate(warning)
      && !seen.has(warning.code)
    ) {
      seen.add(warning.code);
      result.push(warning.code);
    }
  }

  return result;
}

export function stableStringify(value) {
  const result = JSON.stringify(stableValue(value));
  return result === undefined ? "null" : result;
}

export function sameConfig(a, b) {
  return stableStringify(a) === stableStringify(b);
}

export function sourceKey(source) {
  const parts = sourceParts(source);
  if (parts === null) {
    return "";
  }

  const [vi, si, ci] = parts;
  return `${vi}.${si}.${ci === null ? "t" : ci}`;
}

export function parseSourceKey(key) {
  const parts = String(key).split(".");
  return [
    Number(parts[0]),
    Number(parts[1]),
    parts[2] === "t" ? null : Number(parts[2]),
  ];
}

export function slugPath(title, takenPaths) {
  let base = String(title ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32)
    .replace(/-+$/g, "");

  if (base === "") {
    base = "page";
  }

  const taken = new Set(Array.isArray(takenPaths) ? takenPaths : []);
  if (!taken.has(base)) {
    return base;
  }

  for (let number = 2; ; number += 1) {
    const suffix = `-${number}`;
    const prefix = base
      .slice(0, 32 - suffix.length)
      .replace(/-+$/g, "");
    const candidate = `${prefix || "page"}${suffix}`.slice(0, 32);
    if (!taken.has(candidate)) {
      return candidate;
    }
  }
}

export function newDashboardConfig(pageTitle = "Home") {
  return {
    apollo_tab: {
      version: 1,
      theme: DEFAULT_THEME,
    },
    views: [
      newPage(pageTitle, [], "mdi:home"),
    ],
  };
}

export function newPage(
  title,
  takenPaths,
  icon = "mdi:view-dashboard",
) {
  return {
    type: "sections",
    title,
    path: slugPath(title, takenPaths),
    icon,
    max_columns: 3,
    sections: [
      {
        type: "grid",
        column_span: 3,
        cards: [],
      },
    ],
  };
}

export function nextDashboardPath(paths) {
  const taken = new Set(Array.isArray(paths) ? paths : []);
  if (!taken.has("tab-1")) {
    return "tab-1";
  }

  for (let number = 2; ; number += 1) {
    const candidate = `tab-1-${number}`;
    if (!taken.has(candidate)) {
      return candidate;
    }
  }
}

export function nextDashboardTitle(titles, base) {
  const taken = new Set(Array.isArray(titles) ? titles : []);
  if (!taken.has(base)) {
    return base;
  }

  for (let number = 2; ; number += 1) {
    const candidate = `${base} ${number}`;
    if (!taken.has(candidate)) {
      return candidate;
    }
  }
}

// Rows for the Home list. `configs` maps a url_path to that dashboard's
// Lovelace config, and "pages" counts the page tabs the editor shows for it,
// including pages the tablet does not show: the row says how many of those
// there are next to it, so both numbers agree with the editor.
// The "pages" of apollo_tab/dashboards are not used: they count the tablet's
// screens, so an empty page gives none and a long page gives several. A
// dashboard whose config is not known gets pages: null.
export function mergeDashboards(tabList, haList, configs = {}) {
  const tabs = Array.isArray(tabList) ? tabList : [];
  const dashboards = Array.isArray(haList) ? haList : [];
  const known = isPlainObject(configs) ? configs : {};
  const byPath = new Map();

  for (const dashboard of dashboards) {
    if (
      isPlainObject(dashboard)
      && typeof dashboard.url_path === "string"
    ) {
      byPath.set(dashboard.url_path, dashboard);
    }
  }

  return tabs.map((tab) => {
    const safeTab = isPlainObject(tab) ? tab : {};
    const dashboard = byPath.get(safeTab.url_path);
    const id = isPlainObject(dashboard)
      && typeof dashboard.id === "string"
      ? dashboard.id
      : null;
    const config = typeof safeTab.url_path === "string"
      && Object.hasOwn(known, safeTab.url_path)
      ? known[safeTab.url_path]
      : null;

    return {
      url_path: safeTab.url_path,
      title: isPlainObject(dashboard)
        ? dashboard.title
        : safeTab.title,
      id,
      mode: safeTab.mode,
      show_in_sidebar: isPlainObject(dashboard)
        ? dashboard.show_in_sidebar === true
        : false,
      pages: isPlainObject(config) ? pageList(config).length : null,
      editable: safeTab.mode === "storage" && typeof id === "string",
    };
  });
}

export function isGridSection(section) {
  return isPlainObject(section)
    && !Object.prototype.hasOwnProperty.call(section, "strategy")
    && (
      !Object.prototype.hasOwnProperty.call(section, "type")
      || section.type === "grid"
    );
}

// Reads column_span the way the converter does (Python's int(raw or 1)),
// so the editor and the tablet agree on how wide a section is.
export function sectionSpan(section) {
  const raw = isPlainObject(section) ? section.column_span : undefined;
  let span = 1;
  if (typeof raw === "number" && Number.isFinite(raw) && raw !== 0) {
    span = Math.trunc(raw);
  } else if (typeof raw === "string" && /^\s*[+-]?\d+\s*$/.test(raw)) {
    span = Number.parseInt(raw, 10);
  }
  return Math.min(3, Math.max(1, span));
}

export function pageKind(view) {
  if (
    isPlainObject(view)
    && view.type === "sections"
    && !Object.prototype.hasOwnProperty.call(view, "strategy")
  ) {
    return "page";
  }

  if (
    isPlainObject(view)
    && Array.isArray(view.cards)
    && view.cards.length > 0
    && view.cards.every(
      (card) => isPlainObject(card) && card.type === PREVIEW_TYPE,
    )
  ) {
    return "old_preview";
  }

  return "other";
}

export function pageList(config) {
  return configViews(config).map((view, index) => {
    const safeView = isPlainObject(view) ? view : {};
    const title = typeof safeView.title === "string"
      && safeView.title.length > 0
      ? safeView.title
      : typeof safeView.path === "string"
        ? safeView.path
        : "";

    const result = {
      view: index,
      title,
      kind: pageKind(view),
    };

    if (isIcon(safeView.icon)) {
      result.icon = safeView.icon;
    }

    return result;
  });
}

export function componentOf(card, library) {
  if (!isPlainObject(card)) {
    return null;
  }

  const components = isPlainObject(library)
    && Array.isArray(library.components)
    ? library.components
    : [];

  if (card.type === CARD_TYPE) {
    return components.find(
      (component) => (
        isPlainObject(component)
        && component.id === card.component
      ),
    ) ?? null;
  }

  return components.find(
    (component) => (
      isPlainObject(component)
      && typeof component.tag === "string"
      && card.type === `custom:${component.tag}`
    ),
  ) ?? null;
}

export function cardKind(card, library) {
  if (!isPlainObject(card)) {
    return "other";
  }

  if (card.type === "heading") {
    return "heading";
  }

  if (card.type === PREVIEW_TYPE) {
    return "old_preview";
  }

  if (componentOf(card, library) !== null) {
    return "tab";
  }

  if (
    card.type === CARD_TYPE
    || (
      typeof card.type === "string"
      && card.type.startsWith(ALIAS_PREFIX)
    )
  ) {
    return "tab_missing";
  }

  return "other";
}

export function isAllowed(component) {
  return !(
    isPlainObject(component)
    && component.source === "user"
    && component.sensitive === true
    && component.approved !== true
  );
}

export function cardEntities(card, component) {
  if (!isPlainObject(card) || !isPlainObject(component)) {
    return [];
  }

  const specs = isPlainObject(component.params) ? component.params : {};
  const params = isPlainObject(card.params) ? card.params : {};
  const entities = [];

  for (const [name, spec] of Object.entries(specs)) {
    if (!isPlainObject(spec) || spec.kind !== "entity") {
      continue;
    }

    const value = params[name];
    if (typeof value === "string") {
      entities.push(value);
    } else if (Array.isArray(value)) {
      for (const entityId of value) {
        if (typeof entityId === "string") {
          entities.push(entityId);
        }
      }
    }
  }

  return entities;
}

// The devices a card the tablet cannot draw was set up for, so the person
// knows what to add back with a TAB-1 card after removing it. Home
// Assistant's own cards keep them in `entity` and in an `entities` list of
// ids or {entity} objects; a TAB-1 card that is not installed keeps them in
// its params. Only values shaped like an entity id are taken.
export function otherEntities(card) {
  if (!isPlainObject(card)) {
    return [];
  }
  const found = [];
  const add = (value) => {
    const id = isPlainObject(value) ? value.entity : value;
    if (typeof id === "string" && ENTITY_ID_RE.test(id) && !found.includes(id)) {
      found.push(id);
    }
  };
  add(card.entity);
  if (Array.isArray(card.entities)) {
    card.entities.forEach(add);
  }
  if (isPlainObject(card.params)) {
    for (const value of Object.values(card.params)) {
      if (Array.isArray(value)) {
        value.forEach(add);
      } else {
        add(value);
      }
    }
  }
  return found.slice(0, MAX_ENTITIES);
}

export function getCard(config, source) {
  const parts = sourceParts(source);
  if (parts === null) {
    return null;
  }

  const [vi, si, ci] = parts;
  const section = sectionAt(config, vi, si);
  if (!section) {
    return null;
  }

  if (ci === null) {
    return typeof section.title === "string" && section.title.length > 0
      ? {
        type: "heading",
        heading: section.title,
      }
      : null;
  }

  if (
    !Array.isArray(section.cards)
    || ci < 0
    || ci >= section.cards.length
    || !isPlainObject(section.cards[ci])
  ) {
    return null;
  }

  return structuredClone(section.cards[ci]);
}

export function usesWholeScreen(config, vi) {
  const views = configViews(config);
  const view = views[vi];

  if (!isPlainObject(view) || !Array.isArray(view.sections)) {
    return false;
  }

  if (view.sections.length !== 1) {
    return false;
  }

  const section = view.sections[0];
  return isGridSection(section)
    && section.column_span === 3
    && !(
      typeof section.title === "string"
      && section.title.length > 0
    );
}

export function pageScreens(preview, vi) {
  if (
    !isPlainObject(preview)
    || !isPlainObject(preview.layout)
    || !Array.isArray(preview.layout.pages)
  ) {
    return [];
  }

  const result = [];
  preview.layout.pages.forEach((page, index) => {
    if (isPlainObject(page) && page.view === vi) {
      result.push(index);
    }
  });
  return result;
}

export function pageItems(config, vi, library, preview) {
  const views = configViews(config);
  const view = views[vi];
  const sections = isPlainObject(view) && Array.isArray(view.sections)
    ? view.sections
    : [];
  const hasPreview = isPlainObject(preview);
  const warnings = hasPreview ? warningList(preview) : [];
  const sources = hasPreview
    && isPlainObject(preview.sources)
    ? preview.sources
    : {};
  const pages = hasPreview
    && isPlainObject(preview.layout)
    && Array.isArray(preview.layout.pages)
    ? preview.layout.pages
    : [];

  // Where each drawn item sits, by its id, so a row finds its widgets fast.
  const drawn = new Map();
  pages.forEach((page, screen) => {
    if (!isPlainObject(page) || !Array.isArray(page.w)) {
      return;
    }
    for (const widget of page.w) {
      if (!isPlainObject(widget)) {
        continue;
      }
      const id = String(widget.id);
      if (!drawn.has(id)) {
        drawn.set(id, []);
      }
      drawn.get(id).push({ screen, id: widget.id, r: structuredClone(widget.r) });
    }
  });

  const rows = [];

  const createRow = (card, si, ci, sectionHeading = false) => {
    const source = [vi, si, ci];
    const key = sourceKey(source);
    const kind = sectionHeading ? "heading" : cardKind(card, library);
    const component = kind === "tab"
      ? componentOf(card, library)
      : null;
    const type = sectionHeading
      ? "heading"
      : isPlainObject(card) && typeof card.type === "string"
        ? card.type
        : "";
    const title = kind === "tab"
      ? (
        isPlainObject(card) && typeof card.title === "string"
          ? card.title
          : ""
      )
      : kind === "heading"
        ? (
          isPlainObject(card) && typeof card.heading === "string"
            ? card.heading
            : ""
        )
        : "";
    let entities = [];
    if (kind === "tab") {
      entities = cardEntities(card, component);
    } else if (kind === "other" || kind === "tab_missing") {
      entities = otherEntities(card);
    }
    const widgets = [];

    if (hasPreview) {
      for (const [itemId, itemSource] of Object.entries(sources)) {
        if (sameSource(itemSource, source)) {
          widgets.push(...(drawn.get(itemId) || []));
        }
      }
      widgets.sort((a, b) => a.screen - b.screen);
    }

    const shown = widgets.length > 0;
    let reason = null;
    let detail = "";
    let notes = [];

    if (hasPreview) {
      const addressWarnings = warnings.filter(
        (warning) => warningAt(warning, vi, si, ci),
      );

      notes = uniqueWarningCodes(
        addressWarnings,
        (warning) => ITEM_NOTE_CODES.has(warning.code),
      );

      if (!shown) {
        if (kind === "other") {
          reason = "not_tab_element";
        } else if (kind === "old_preview") {
          reason = "old_preview";
        } else if (kind === "tab_missing") {
          reason = "unknown_component";
        } else {
          const warning = addressWarnings.find(
            (item) => ITEM_REASON_CODES.has(item.code),
          );
          reason = warning ? warning.code : "left_out";
        }

        const matchingWarning = addressWarnings.find(
          (warning) => warning.code === reason,
        );

        if (matchingWarning) {
          detail = matchingWarning.detail ?? "";
        } else if (
          reason === "not_tab_element"
          || reason === "old_preview"
        ) {
          detail = type;
        } else if (reason === "unknown_component") {
          detail = isPlainObject(card)
            && typeof card.component === "string"
            ? card.component
            : type;
        }
      }
    }

    return {
      source,
      key,
      kind,
      type,
      component,
      title,
      entities,
      widgets,
      shown,
      reason,
      detail,
      notes,
    };
  };

  sections.forEach((section, si) => {
    if (!isPlainObject(section)) {
      return;
    }

    if (
      typeof section.title === "string"
      && section.title.length > 0
    ) {
      rows.push(createRow(
        {
          type: "heading",
          heading: section.title,
        },
        si,
        null,
        true,
      ));
    }

    if (Array.isArray(section.cards)) {
      section.cards.forEach((card, ci) => {
        rows.push(createRow(card, si, ci));
      });
    }
  });

  return rows;
}

export function pageNotes(preview, vi) {
  return uniqueWarningCodes(
    warningList(preview),
    (warning) => (
      warning.view === vi
      && warning.card == null
      && PAGE_NOTE_CODES.has(warning.code)
    ),
  );
}

export function dashboardNotes(preview) {
  return uniqueWarningCodes(
    warningList(preview),
    (warning) => (
      warning.view == null
      && DASHBOARD_NOTE_CODES.has(warning.code)
    ),
  );
}

// What the editor marks "Not shown on the tablet" in a whole dashboard, for
// its row on Home: the pages the tablet cannot show, and the cards and
// headings on the other pages that the preview did not draw. Without a
// preview, only cards the tablet can never draw are counted.
export function notShownCounts(config, library, preview) {
  const drawn = isPlainObject(preview);
  let cards = 0;
  let pages = 0;
  for (const page of pageList(config)) {
    if (page.kind !== "page") {
      pages += 1;
      continue;
    }
    for (const row of pageItems(config, page.view, library, preview)) {
      if (drawn ? !row.shown : NEVER_SHOWN_KINDS.has(row.kind)) {
        cards += 1;
      }
    }
  }
  return { cards, pages };
}

export function addPage(config, title, icon) {
  const next = structuredClone(config);
  if (!Array.isArray(next.views)) {
    next.views = [];
  }

  const paths = next.views
    .filter((view) => isPlainObject(view))
    .map((view) => view.path)
    .filter((path) => typeof path === "string");

  next.views.push(newPage(title, paths, icon));
  return {
    config: next,
    view: next.views.length - 1,
  };
}

export function renamePage(config, vi, title) {
  const next = structuredClone(config);
  if (
    !Array.isArray(next.views)
    || !isPlainObject(next.views[vi])
  ) {
    return next;
  }

  next.views[vi].title = title;
  return next;
}

export function setPageIcon(config, vi, icon) {
  const next = structuredClone(config);
  if (
    !isIcon(icon)
    || !Array.isArray(next.views)
    || !isPlainObject(next.views[vi])
  ) {
    return next;
  }

  next.views[vi].icon = icon;
  return next;
}

export function movePage(config, vi, delta) {
  const next = structuredClone(config);
  if (
    !Array.isArray(next.views)
    || !Number.isInteger(vi)
    || (delta !== -1 && delta !== 1)
  ) {
    return {
      config: next,
      view: vi,
    };
  }

  const target = vi + delta;
  if (
    vi < 0
    || vi >= next.views.length
    || target < 0
    || target >= next.views.length
  ) {
    return {
      config: next,
      view: vi,
    };
  }

  [next.views[vi], next.views[target]] = [
    next.views[target],
    next.views[vi],
  ];

  return {
    config: next,
    view: target,
  };
}

export function removePage(config, vi) {
  const next = structuredClone(config);
  if (
    !Array.isArray(next.views)
    || next.views.length <= 1
    || vi < 0
    || vi >= next.views.length
  ) {
    return {
      config: next,
      view: vi,
    };
  }

  next.views.splice(vi, 1);
  return {
    config: next,
    view: Math.min(vi, next.views.length - 1),
  };
}

export function addCard(config, vi, component, params) {
  const next = structuredClone(config);
  if (
    !Array.isArray(next.views)
    || pageKind(next.views[vi]) !== "page"
    || !isPlainObject(component)
  ) {
    return {
      config: next,
      source: null,
    };
  }

  const view = next.views[vi];
  if (!Array.isArray(view.sections)) {
    view.sections = [];
  }

  let si = -1;
  for (let index = view.sections.length - 1; index >= 0; index -= 1) {
    if (isGridSection(view.sections[index])) {
      si = index;
      break;
    }
  }

  if (si === -1) {
    view.sections.push({
      type: "grid",
      column_span: 3,
      cards: [],
    });
    si = view.sections.length - 1;
  }

  const section = view.sections[si];
  if (!Array.isArray(section.cards)) {
    section.cards = [];
  }

  const span = sectionSpan(section);
  const columns = componentGridValue(
    component,
    "columns",
    0,
    UNIT_COLUMNS,
  );
  const rows = componentGridValue(
    component,
    "rows",
    1,
    UNIT_ROWS,
  );

  const card = cleanConfig({
    type: CARD_TYPE,
    component: component.id,
    params: isPlainObject(params) ? structuredClone(params) : {},
    grid_options: {
      columns: Math.min(columns, 12 * span),
      rows,
    },
  });

  section.cards.push(card);

  return {
    config: next,
    source: [vi, si, section.cards.length - 1],
  };
}

export function updateCard(config, source, changes) {
  const next = structuredClone(config);
  const parts = sourceParts(source);
  if (
    parts === null
    || parts[2] === null
    || !isPlainObject(changes)
  ) {
    return next;
  }

  const [vi, si, ci] = parts;
  const section = sectionAt(next, vi, si);
  if (
    !section
    || !Array.isArray(section.cards)
    || ci < 0
    || ci >= section.cards.length
    || !isPlainObject(section.cards[ci])
  ) {
    return next;
  }

  const card = {
    ...section.cards[ci],
  };

  for (const key of [
    "params",
    "title",
    "style",
    "grid_options",
  ]) {
    if (!Object.prototype.hasOwnProperty.call(changes, key)) {
      continue;
    }

    if (changes[key] === undefined) {
      delete card[key];
    } else {
      card[key] = structuredClone(changes[key]);
    }
  }

  section.cards[ci] = cleanConfig(card);
  return next;
}

export function cardSize(card, component) {
  const gridOptions = isPlainObject(card)
    && isPlainObject(card.grid_options)
    ? card.grid_options
    : {};
  const componentGrid = isPlainObject(component)
    && isPlainObject(component.grid)
    ? component.grid
    : {};

  let columns;
  let columnsExact = true;

  if (
    Number.isInteger(gridOptions.columns)
    && gridOptions.columns >= 1
    && gridOptions.columns <= 36
  ) {
    columns = gridOptions.columns;
  } else if (gridOptions.columns === "full") {
    columns = 36;
    columnsExact = false;
  } else if (Number.isFinite(componentGrid.columns)) {
    columns = componentGrid.columns;
  } else {
    columns = UNIT_COLUMNS;
  }

  let rows;
  if (
    Number.isInteger(gridOptions.rows)
    && gridOptions.rows >= 1
    && gridOptions.rows <= 12
  ) {
    rows = gridOptions.rows;
  } else if (Number.isFinite(componentGrid.rows)) {
    rows = componentGrid.rows;
  } else {
    rows = UNIT_ROWS;
  }

  const rawWidth = columns / UNIT_COLUMNS;
  const rawHeight = rows / UNIT_ROWS;
  const exact = columnsExact
    && Number.isInteger(rawWidth)
    && Number.isInteger(rawHeight);

  return {
    w: exact ? rawWidth : Math.max(1, Math.round(rawWidth)),
    h: exact ? rawHeight : Math.max(1, Math.round(rawHeight)),
    exact,
  };
}

export function maxUnitsWide(config, source) {
  const parts = sourceParts(source);
  if (parts === null) {
    return 2;
  }

  const section = sectionAt(config, parts[0], parts[1]);
  return section ? 2 * sectionSpan(section) : 2;
}

export function resizeCard(config, source, w, h) {
  const next = structuredClone(config);
  const parts = sourceParts(source);
  if (parts === null || parts[2] === null) {
    return next;
  }

  const [vi, si, ci] = parts;
  const section = sectionAt(next, vi, si);
  if (
    !section
    || !Array.isArray(section.cards)
    || ci < 0
    || ci >= section.cards.length
    || !isPlainObject(section.cards[ci])
  ) {
    return next;
  }

  const width = clampInteger(
    w,
    1,
    maxUnitsWide(next, source),
  );
  const height = clampInteger(h, 1, MAX_UNITS_HIGH);
  const oldOptions = isPlainObject(section.cards[ci].grid_options)
    ? section.cards[ci].grid_options
    : {};

  section.cards[ci].grid_options = {
    ...oldOptions,
    columns: width * UNIT_COLUMNS,
    rows: height * UNIT_ROWS,
  };

  return next;
}

export function moveItem(config, source, delta) {
  const next = structuredClone(config);
  const parts = sourceParts(source);

  if (
    parts === null
    || parts[2] === null
    || (delta !== -1 && delta !== 1)
  ) {
    return {
      config: next,
      source: structuredClone(source),
    };
  }

  const [vi, si, ci] = parts;
  const views = configViews(next);
  const view = views[vi];

  if (
    !isPlainObject(view)
    || !Array.isArray(view.sections)
    || !isPlainObject(view.sections[si])
    || !Array.isArray(view.sections[si].cards)
    || ci < 0
    || ci >= view.sections[si].cards.length
  ) {
    return {
      config: next,
      source: structuredClone(source),
    };
  }

  const cards = view.sections[si].cards;
  const targetIndex = ci + delta;

  if (targetIndex >= 0 && targetIndex < cards.length) {
    [cards[ci], cards[targetIndex]] = [
      cards[targetIndex],
      cards[ci],
    ];
    return {
      config: next,
      source: [vi, si, targetIndex],
    };
  }

  let targetSection = si + delta;
  while (
    targetSection >= 0
    && targetSection < view.sections.length
    && !isGridSection(view.sections[targetSection])
  ) {
    targetSection += delta;
  }

  if (
    targetSection < 0
    || targetSection >= view.sections.length
  ) {
    return {
      config: next,
      source: structuredClone(source),
    };
  }

  const [card] = cards.splice(ci, 1);
  const destination = view.sections[targetSection];
  if (!Array.isArray(destination.cards)) {
    destination.cards = [];
  }

  if (delta === -1) {
    destination.cards.push(card);
    return {
      config: next,
      source: [
        vi,
        targetSection,
        destination.cards.length - 1,
      ],
    };
  }

  destination.cards.unshift(card);
  return {
    config: next,
    source: [vi, targetSection, 0],
  };
}

export function canMove(config, source, delta) {
  const result = moveItem(config, source, delta);
  return !sameSource(result.source, source);
}

// Moves the card at `source` to the end of page `target`, with everything
// it holds: device, name, look and size. target "new" first adds a page
// called `title`. The card goes into the page's last grid, as a new card
// would, and is made no wider than that grid. Returns {config, source,
// view}; source is null when nothing moved.
export function moveCardToPage(config, source, target, title = "") {
  const parts = sourceParts(source);
  const unchanged = {
    config: structuredClone(config),
    source: null,
    view: parts ? parts[0] : 0,
  };
  if (parts === null || parts[2] === null || (target !== "new" && target === parts[0])) {
    return unchanged;
  }
  const [vi, si, ci] = parts;
  const card = getCard(config, parts);
  if (!isPlainObject(card)) {
    return unchanged;
  }
  let next = config;
  let view = target;
  if (target === "new") {
    const added = addPage(config, title);
    next = added.config;
    view = added.view;
  }
  next = structuredClone(next);
  const page = configViews(next)[view];
  if (!Number.isInteger(view) || pageKind(page) !== "page") {
    return unchanged;
  }
  sectionAt(next, vi, si).cards.splice(ci, 1);
  if (!Array.isArray(page.sections)) {
    page.sections = [];
  }
  let grid = -1;
  for (let index = page.sections.length - 1; index >= 0; index -= 1) {
    if (isGridSection(page.sections[index])) {
      grid = index;
      break;
    }
  }
  if (grid === -1) {
    page.sections.push({ type: "grid", column_span: 3, cards: [] });
    grid = page.sections.length - 1;
  }
  const section = page.sections[grid];
  if (!Array.isArray(section.cards)) {
    section.cards = [];
  }
  const moved = structuredClone(card);
  const widest = 12 * sectionSpan(section);
  if (isPlainObject(moved.grid_options) && Number(moved.grid_options.columns) > widest) {
    moved.grid_options = { ...moved.grid_options, columns: widest };
  }
  section.cards.push(moved);
  return { config: next, source: [view, grid, section.cards.length - 1], view };
}

// The addresses of one page's cards in order, or of its section titles when
// `titles` is true.
function pageAddresses(config, vi, titles) {
  const view = configViews(config)[vi];
  const result = [];
  if (!isPlainObject(view) || !Array.isArray(view.sections)) {
    return result;
  }
  view.sections.forEach((section, si) => {
    if (!isPlainObject(section)) {
      return;
    }
    if (titles) {
      if (typeof section.title === "string" && section.title.length > 0) {
        result.push([vi, si, null]);
      }
    } else if (Array.isArray(section.cards)) {
      section.cards.forEach((_card, ci) => result.push([vi, si, ci]));
    }
  });
  return result;
}

// A copy of `config` with the item at `source` blanked out.
function withoutItem(config, source) {
  const next = structuredClone(config);
  const [vi, si, ci] = source;
  const section = sectionAt(next, vi, si);
  if (section && ci === null) {
    delete section.title;
  } else if (section && Array.isArray(section.cards)) {
    section.cards[ci] = null;
  }
  return next;
}

// Where the item at `source` in `before` is in `after`, so a selection stays
// on the card the person picked when undo, redo or a version saved
// somewhere else replaces the whole draft. The item keeps its address when
// it is still there or was only edited in place (nothing else differs).
// Otherwise the identical item on the same page nearest to its old place is
// taken; between two equally near, the one that is the same copy counting
// from the top. Returns null when the item is gone.
export function followItem(before, after, source) {
  const parts = sourceParts(source);
  const item = parts === null ? null : getCard(before, parts);
  if (item === null) {
    return null;
  }
  const [vi, , ci] = parts;
  const wanted = stableStringify(item);
  const here = getCard(after, parts);
  if (
    here !== null
    && (
      stableStringify(here) === wanted
      || sameConfig(withoutItem(before, parts), withoutItem(after, parts))
    )
  ) {
    return [...parts];
  }

  const titles = ci === null;
  const copies = (config) => pageAddresses(config, vi, titles)
    .map((address, index) => ({ address, index }))
    .filter(({ address }) => stableStringify(getCard(config, address)) === wanted);
  const old = copies(before);
  const mine = old.find(({ address }) => sameSource(address, parts));
  const rank = old.indexOf(mine);
  let best = null;
  copies(after).forEach((copy, copyRank) => {
    const distance = Math.abs(copy.index - mine.index);
    const sameRank = copyRank === rank ? 0 : 1;
    if (
      best === null
      || distance < best.distance
      || (distance === best.distance && sameRank < best.sameRank)
    ) {
      best = { address: copy.address, distance, sameRank };
    }
  });
  return best ? [...best.address] : null;
}

export function removeItem(config, source) {
  const next = structuredClone(config);
  const parts = sourceParts(source);
  if (parts === null) {
    return next;
  }

  const [vi, si, ci] = parts;
  const section = sectionAt(next, vi, si);
  if (!section) {
    return next;
  }

  if (ci === null) {
    if (
      typeof section.title === "string"
      && section.title.length > 0
    ) {
      delete section.title;
    }
    return next;
  }

  if (
    Array.isArray(section.cards)
    && ci >= 0
    && ci < section.cards.length
  ) {
    section.cards.splice(ci, 1);
  }

  return next;
}

export function setHeadingText(config, source, text) {
  const next = structuredClone(config);
  const parts = sourceParts(source);
  if (parts === null) {
    return next;
  }

  const value = String(text ?? "").slice(0, 80);
  const [vi, si, ci] = parts;
  const section = sectionAt(next, vi, si);
  if (!section) {
    return next;
  }

  if (ci === null) {
    if (value === "") {
      delete section.title;
    } else {
      section.title = value;
    }
    return next;
  }

  if (
    Array.isArray(section.cards)
    && ci >= 0
    && ci < section.cards.length
    && isPlainObject(section.cards[ci])
    && section.cards[ci].type === "heading"
  ) {
    section.cards[ci].heading = value;
  }

  return next;
}

export function setTheme(config, themeId) {
  const next = structuredClone(config);
  const options = isPlainObject(next.apollo_tab)
    ? next.apollo_tab
    : {};

  next.apollo_tab = {
    ...options,
    version: 1,
    theme: themeId,
  };

  return next;
}

export function useWholeScreen(config, vi) {
  const next = structuredClone(config);
  if (
    !Array.isArray(next.views)
    || !isPlainObject(next.views[vi])
  ) {
    return next;
  }

  const view = next.views[vi];
  const sections = Array.isArray(view.sections)
    ? view.sections
    : [];
  const cards = [];
  const remaining = [];

  for (const section of sections) {
    if (!isGridSection(section)) {
      remaining.push(section);
      continue;
    }

    if (
      typeof section.title === "string"
      && section.title.length > 0
    ) {
      cards.push({
        type: "heading",
        heading: section.title,
      });
    }

    if (Array.isArray(section.cards)) {
      cards.push(...section.cards);
    }
  }

  view.sections = [
    {
      type: "grid",
      column_span: 3,
      cards,
    },
    ...remaining,
  ];
  view.max_columns = 3;

  return next;
}

export function groupOf(component) {
  const params = isPlainObject(component)
    && isPlainObject(component.params)
    ? component.params
    : {};

  for (const spec of Object.values(params)) {
    if (isPlainObject(spec) && spec.kind === "page") {
      return "rooms";
    }
  }

  let domain = null;
  for (const spec of Object.values(params)) {
    if (isPlainObject(spec) && spec.kind === "entity") {
      domain = spec.domain;
      break;
    }
  }

  if (LIGHT_DOMAINS.has(domain)) {
    return "lights";
  }
  if (CLIMATE_DOMAINS.has(domain)) {
    return "climate";
  }
  if (domain === "media_player") {
    return "media";
  }
  if (SECURITY_DOMAINS.has(domain)) {
    return "security";
  }
  if (SENSOR_DOMAINS.has(domain)) {
    return "sensors";
  }
  if (ROOM_DOMAINS.has(domain)) {
    return "rooms";
  }

  return "more";
}

function searchWords(text) {
  return String(text ?? "")
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean);
}

// Each word of `query` has to start a word of the card's name, its
// description, the kinds of device it controls ("media_player" gives
// "media" and "player"), or the extra words describe(component, group)
// gives: the picker passes the group's title and the device question.
// Matching the start of words keeps "ac" from finding "Scene" or "Lock".
export function pickerGroups(library, query = "", describe = null) {
  const components = isPlainObject(library)
    && Array.isArray(library.components)
    ? library.components
    : [];
  const words = searchWords(query);
  const grouped = new Map(
    GROUP_IDS.map((id) => [id, []]),
  );

  for (const component of components) {
    if (!isPlainObject(component)) {
      continue;
    }

    const group = groupOf(component);
    if (words.length) {
      const domains = paramFields(component)
        .filter((field) => field.kind === "entity" && typeof field.domain === "string")
        .map((field) => field.domain);
      const known = searchWords([
        component.name,
        component.description,
        ...domains,
        typeof describe === "function" ? describe(component, group) : "",
      ].join(" "));
      if (!words.every((word) => known.some((start) => start.startsWith(word)))) {
        continue;
      }
    }

    grouped.get(group).push(component);
  }

  return GROUP_IDS
    .filter((id) => grouped.get(id).length > 0)
    .map((id) => ({
      id,
      cards: grouped.get(id),
    }));
}

export function paramFields(component) {
  const params = isPlainObject(component)
    && isPlainObject(component.params)
    ? component.params
    : {};

  return Object.entries(params).map(([name, spec]) => {
    const safeSpec = isPlainObject(spec) ? spec : {};

    return {
      name,
      kind: safeSpec.kind,
      domain: safeSpec.kind === "entity"
        ? safeSpec.domain
        : undefined,
      multiple: safeSpec.kind === "entity"
        ? safeSpec.multiple === true
        : undefined,
      min: safeSpec.kind === "number"
        ? safeSpec.min
        : undefined,
      max: safeSpec.kind === "number"
        ? safeSpec.max
        : undefined,
      default: safeSpec.kind === "number"
        ? safeSpec.default
        : undefined,
    };
  });
}

export function singleEntityParam(component) {
  const params = isPlainObject(component)
    && isPlainObject(component.params)
    ? Object.entries(component.params)
    : [];

  if (params.length !== 1) {
    return null;
  }

  const [name, spec] = params[0];
  return isPlainObject(spec)
    && spec.kind === "entity"
    && spec.multiple !== true
    ? name
    : null;
}

// The device fields of `component` that can take one of `entityIds`, each
// with the devices that fit it: [[param name, [entity id, ...]], ...].
function fittingFields(component, entityIds) {
  const params = isPlainObject(component)
    && isPlainObject(component.params)
    ? Object.entries(component.params)
    : [];
  const ids = Array.isArray(entityIds)
    ? entityIds.filter((id) => typeof id === "string")
    : [];
  const fields = [];

  for (const [name, spec] of params) {
    if (
      !isPlainObject(spec)
      || spec.kind !== "entity"
      || typeof spec.domain !== "string"
    ) {
      continue;
    }
    const fit = ids.filter((id) => id.startsWith(`${spec.domain}.`));
    if (fit.length > 0) {
      fields.push([name, fit]);
    }
  }

  return fields;
}

// True when `component` has a device field that can take one of the
// devices a removed card controlled, so it can stand in for that card.
export function fitsDevices(component, entityIds) {
  return fittingFields(component, entityIds).length > 0;
}

// Fills the device fields of `component` that fit those devices: a field
// for several devices gets all that fit, and a field for one device gets
// the first that no earlier such field took.
export function presetParams(component, entityIds) {
  const params = {};
  const specs = isPlainObject(component?.params) ? component.params : {};
  const taken = new Set();

  for (const [name, fit] of fittingFields(component, entityIds)) {
    if (specs[name].multiple === true) {
      params[name] = [...fit];
      continue;
    }
    const free = fit.find((id) => !taken.has(id));
    if (free) {
      params[name] = free;
      taken.add(free);
    }
  }

  return params;
}

export function entityChoices(hass, spec, query = "") {
  const safeHass = isPlainObject(hass) ? hass : {};
  const states = isPlainObject(safeHass.states)
    ? safeHass.states
    : {};
  const entities = isPlainObject(safeHass.entities)
    ? safeHass.entities
    : {};
  const devices = isPlainObject(safeHass.devices)
    ? safeHass.devices
    : {};
  const areas = isPlainObject(safeHass.areas)
    ? safeHass.areas
    : {};
  const domain = isPlainObject(spec) && typeof spec.domain === "string"
    ? spec.domain
    : "";
  const prefix = `${domain}.`;
  const words = String(query)
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
  const choices = [];

  for (const [entityId, state] of Object.entries(states)) {
    if (!entityId.startsWith(prefix)) {
      continue;
    }

    const entity = isPlainObject(entities[entityId])
      ? entities[entityId]
      : {};
    if (entity.hidden === true) {
      continue;
    }

    const attributes = isPlainObject(state)
      && isPlainObject(state.attributes)
      ? state.attributes
      : {};
    const name = typeof attributes.friendly_name === "string"
      && attributes.friendly_name.length > 0
      ? attributes.friendly_name
      : entityId;

    let areaId = typeof entity.area_id === "string"
      ? entity.area_id
      : "";

    if (
      areaId === ""
      && typeof entity.device_id === "string"
      && isPlainObject(devices[entity.device_id])
      && typeof devices[entity.device_id].area_id === "string"
    ) {
      areaId = devices[entity.device_id].area_id;
    }

    const area = areaId !== ""
      && isPlainObject(areas[areaId])
      && typeof areas[areaId].name === "string"
      ? areas[areaId].name
      : "";

    const searchable = `${name} ${area} ${entityId}`.toLowerCase();
    if (!words.every((word) => searchable.includes(word))) {
      continue;
    }

    choices.push({
      entity_id: entityId,
      name,
      area,
    });
  }

  choices.sort((a, b) => {
    const nameOrder = a.name.localeCompare(
      b.name,
      undefined,
      {
        sensitivity: "base",
      },
    );

    return nameOrder !== 0
      ? nameOrder
      : a.entity_id.localeCompare(b.entity_id);
  });

  return choices;
}

export function paramsComplete(component, params) {
  const specs = isPlainObject(component)
    && isPlainObject(component.params)
    ? component.params
    : {};
  const values = isPlainObject(params) ? params : {};

  for (const [name, spec] of Object.entries(specs)) {
    if (!isPlainObject(spec) || spec.kind !== "entity") {
      continue;
    }

    const value = values[name];
    if (spec.multiple === true) {
      if (!Array.isArray(value) || value.length === 0) {
        return false;
      }
    } else if (
      typeof value !== "string"
      || value.length === 0
    ) {
      return false;
    }
  }

  return true;
}

export function pageChoices(config) {
  const pages = pageList(config);
  const views = configViews(config);
  const result = [];

  views.forEach((view, index) => {
    if (
      pageKind(view) === "page"
      && isPlainObject(view)
      && typeof view.path === "string"
      && /^[a-z0-9_-]{1,64}$/.test(view.path)
    ) {
      result.push({
        path: view.path,
        title: pages[index].title,
      });
    }
  });

  return result;
}

export function hexToRgb(value) {
  if (
    typeof value !== "string"
    || !/^#[0-9a-fA-F]{6}$/.test(value)
  ) {
    return null;
  }

  return [
    Number.parseInt(value.slice(1, 3), 16),
    Number.parseInt(value.slice(3, 5), 16),
    Number.parseInt(value.slice(5, 7), 16),
  ];
}

export function styleDefaults(data, theme) {
  const result = structuredClone(data);
  if (!isPlainObject(theme)) {
    return result;
  }

  if (
    result.use_color
    && result.color === undefined
    && typeof theme.card === "string"
    && /^#[0-9a-fA-F]{6}$/.test(theme.card)
  ) {
    result.color = hexToRgb(theme.card);
  }

  if (
    result.use_accent
    && result.accent === undefined
    && typeof theme.acc === "string"
    && /^#[0-9a-fA-F]{6}$/.test(theme.acc)
  ) {
    result.accent = hexToRgb(theme.acc);
  }

  if (
    result.gradient !== "none"
    && result.gradient_to === undefined
    && typeof theme.card2 === "string"
    && /^#[0-9a-fA-F]{6}$/.test(theme.card2)
  ) {
    result.gradient_to = hexToRgb(theme.card2);
  }

  return result;
}

export function createHistory(config) {
  return {
    past: [],
    present: config,
    future: [],
    key: null,
    at: 0,
  };
}

export function historyPush(
  history,
  config,
  {
    key = null,
    now = 0,
  } = {},
) {
  if (sameConfig(config, history.present)) {
    return history;
  }

  if (
    key !== null
    && key === history.key
    && now - history.at < 1000
  ) {
    return {
      ...history,
      present: config,
      future: [],
      key,
      at: now,
    };
  }

  return {
    past: [
      ...history.past,
      history.present,
    ].slice(-HISTORY_LIMIT),
    present: config,
    future: [],
    key,
    at: now,
  };
}

export function historyUndo(history) {
  if (!Array.isArray(history.past) || history.past.length === 0) {
    return history;
  }

  const present = history.past[history.past.length - 1];
  return {
    ...history,
    past: history.past.slice(0, -1),
    present,
    future: [
      history.present,
      ...history.future,
    ],
    key: null,
  };
}

export function historyRedo(history) {
  if (
    !Array.isArray(history.future)
    || history.future.length === 0
  ) {
    return history;
  }

  const [present, ...future] = history.future;
  return {
    ...history,
    past: [
      ...history.past,
      history.present,
    ].slice(-HISTORY_LIMIT),
    present,
    future,
    key: null,
  };
}

export function canUndo(history) {
  return Array.isArray(history.past) && history.past.length > 0;
}

export function canRedo(history) {
  return Array.isArray(history.future) && history.future.length > 0;
}

// How a save that first read Home Assistant's version ended when it did not
// save: the queue was paused or reset while reading, or Home Assistant held
// a version saved somewhere else.
const NOT_SENT = Symbol("not sent");

class StoredElsewhere {
  constructor(config, kind) {
    this.config = config;
    this.kind = kind;
  }
}

// read, when given, fetches the version Home Assistant holds; it is called
// just before each save (see _checkThenSave). onChanged gets that version,
// and what classifyRemote made of it, when it was saved somewhere else (or
// may have been) and the queue has paused instead of saving over it.
export class SaveQueue {
  constructor({
    save,
    read = null,
    onChanged = () => {},
    delay = 400,
    onState = () => {},
    setTimer = setTimeout,
    clearTimer = clearTimeout,
  }) {
    this._save = save;
    this._read = read;
    this._onChanged = onChanged;
    this._delay = delay;
    this._onState = onState;
    // Browsers refuse window.setTimeout called as a method of another
    // object ("Illegal invocation"), so always call the timers unbound.
    this._setTimer = (callback, ms) => setTimer(callback, ms);
    this._clearTimer = (id) => clearTimer(id);

    this.state = "saved";
    this.saved = null;
    this.inflight = null;
    this.error = null;

    // Versions Home Assistant may hold, though which one is not known: our
    // saves that were still running at reset(), landed during a pause or
    // failed without a clear answer, and the version reset() was told about.
    this.outdated = [];

    // The versions above that reset() named rather than this queue saving
    // them, and whether they are in doubt (see doubt()).
    this.told = [];
    this.doubted = false;

    this._draft = null;
    this._timer = null;
    this._generation = 0;
    this._landedPaused = false;
    this._waiters = [];
  }

  _changeState(state, force = false) {
    const changed = this.state !== state;
    this.state = state;

    if (changed || force) {
      this._onState(this.state, this.error);
    }

    this._settleWaiters();
  }

  _cancelTimer() {
    if (this._timer !== null) {
      this._clearTimer(this._timer);
      this._timer = null;
    }
  }

  _schedule() {
    this._cancelTimer();
    this._timer = this._setTimer(() => {
      this._timer = null;
      this._startSave();
    }, this._delay);
  }

  _settleWaiters() {
    const settled = this.inflight === null
      && (
        this._draft === null
        || this.state === "error"
        || this.state === "paused"
      );

    if (!settled || this._waiters.length === 0) {
      return;
    }

    const waiters = this._waiters;
    this._waiters = [];
    for (const resolve of waiters) {
      resolve();
    }
  }

  _startSave() {
    this._cancelTimer();

    if (
      this.state === "paused"
      || this.inflight !== null
      || this._draft === null
    ) {
      this._settleWaiters();
      return;
    }

    if (this.saved !== null && sameConfig(this._draft, this.saved)) {
      this._draft = null;
      this.error = null;
      this._changeState("saved");
      return;
    }

    const config = this._draft;
    const generation = this._generation;
    this._draft = null;
    this.inflight = config;
    this._changeState("saving");

    let result;
    try {
      result = this._read ? this._checkThenSave(config, generation) : this._save(config);
    } catch (error) {
      result = Promise.reject(error);
    }

    Promise.resolve(result).then(
      (outcome) => {
        this.inflight = null;

        if (generation !== this._generation) {
          this._afterOutdatedSave();
          return;
        }

        if (outcome === NOT_SENT || outcome instanceof StoredElsewhere) {
          // Nothing was saved, so the change waits, unless a newer one
          // has replaced it meanwhile.
          if (this._draft === null) {
            this._draft = config;
          }
          if (outcome === NOT_SENT) {
            this._settleWaiters();
            return;
          }
          this.error = null;
          this._changeState("paused");
          this._onChanged(outcome.config, outcome.kind);
          return;
        }

        this.saved = config;
        this.error = null;
        this.outdated = [];
        this.told = [];

        if (this.state === "paused") {
          this._landedPaused = true;
          this._settleWaiters();
        } else if (this._draft !== null) {
          this._startSave();
        } else {
          this._changeState("saved");
        }
      },
      (error) => {
        this.inflight = null;

        if (generation !== this._generation) {
          this._afterOutdatedSave();
          return;
        }

        this.error = error;
        if (this._draft === null) {
          this._draft = config;
        }
        // A save whose answer was lost, for example when the connection
        // dropped, may still have reached Home Assistant.
        if (!this.outdated.includes(config)) {
          this.outdated = [...this.outdated, config];
        }

        if (this.state === "paused") {
          this._settleWaiters();
        } else {
          this._changeState("error", true);
        }
      },
    );
  }

  // Saves `config` only while Home Assistant still holds one of the queue's
  // own versions. Home Assistant tells only the browsers connected at the
  // time about a save, so a version saved while this one was offline or
  // asleep may be unknown here; saving over it would lose it without a word.
  async _checkThenSave(config, generation) {
    const stored = await this._read();
    if (generation !== this._generation || this.state === "paused") {
      return NOT_SENT;
    }
    const kind = classifyRemote(stored, this);
    if (kind !== "ours") {
      return new StoredElsewhere(stored, kind);
    }
    return this._save(config);
  }

  // A save that started before reset() has ended. reset() left the version
  // to keep as the draft, so it is saved after this one, as is any newer
  // draft pushed since.
  _afterOutdatedSave() {
    if (this._draft !== null && this.state !== "paused") {
      this._startSave();
    } else {
      this._settleWaiters();
    }
  }

  // Tells the queue that Home Assistant holds `config`. That is only certain
  // when none of our saves could have been stored around the same time. If
  // one is still running, or landed during a pause, either version may be
  // the stored one, so `config` is saved again to make sure.
  reset(config) {
    this._cancelTimer();
    this.error = null;
    // What Home Assistant holds is known again.
    this.doubted = false;

    const landed = this._landedPaused ? this.saved : null;
    this._landedPaused = false;

    if (this.inflight === null && landed === null) {
      this._draft = null;
      this.saved = config;
      this.outdated = [];
      this.told = [config];
      this._changeState("saved");
      return;
    }

    this.outdated = [
      ...this.outdated,
      ...[this.inflight, landed].filter((own) => own !== null),
      config,
    ];
    this.told = [...this.told, config];
    this._generation += 1;
    this.saved = null;
    this._draft = config;

    if (this.inflight !== null) {
      this._changeState("saving");
      return;
    }

    this._changeState("pending");
    this._schedule();
  }

  push(config) {
    this._draft = config;

    if (this.state === "paused") {
      this._settleWaiters();
      return;
    }

    if (
      this.inflight === null
      && this.saved !== null
      && sameConfig(config, this.saved)
    ) {
      this._draft = null;
      this._cancelTimer();
      this.error = null;
      this._changeState("saved");
      return;
    }

    if (this.inflight !== null) {
      this._cancelTimer();
      this._changeState("saving");
      return;
    }

    this._changeState("pending");
    this._schedule();
  }

  flush() {
    this._cancelTimer();
    this._startSave();

    const settled = this.inflight === null
      && (
        this._draft === null
        || this.state === "error"
        || this.state === "paused"
      );

    if (settled) {
      return Promise.resolve();
    }

    return new Promise((resolve) => {
      this._waiters.push(resolve);
      this._settleWaiters();
    });
  }

  retry() {
    if (this._draft === null) {
      return;
    }

    this._startSave();
  }

  pause() {
    this._cancelTimer();
    this._changeState("paused");
  }

  // The connection to Home Assistant was lost and has come back, so events
  // about the dashboard may have been missed: it may even have been deleted
  // and made again at the same address with the same content. Until reset()
  // names what is stored again, a version the queue was only told about no
  // longer shows that the dashboard is still the one it was editing.
  doubt() {
    this.doubted = true;
  }

  resume() {
    if (this.state !== "paused") {
      return;
    }

    this._landedPaused = false;

    if (this.inflight !== null) {
      this._changeState("saving");
      return;
    }

    if (this._draft !== null) {
      this._changeState("pending");
      this.flush();
      return;
    }

    this._changeState("saved");
  }

  get dirty() {
    return this.state !== "saved";
  }
}

// "ours" when `remote` is one of the queue's own versions, "changed" when it
// is not, and "unsure" when it only matches a version the queue was told
// about while those are in doubt (see SaveQueue.doubt).
export function classifyRemote(remote, { saved, inflight, outdated = [], told = [], doubted = false }) {
  const matches = [saved, inflight, ...outdated].filter(
    (config) => config != null && sameConfig(remote, config),
  );
  if (!matches.length) {
    return "changed";
  }
  if (!doubted) {
    return "ours";
  }
  return matches.some((config) => !told.includes(config)) ? "ours" : "unsure";
}

// The devices of `entityIds` that no field in `params` uses, in their order.
export function devicesLeft(entityIds, params) {
  const used = new Set();
  for (const value of Object.values(isPlainObject(params) ? params : {})) {
    for (const id of Array.isArray(value) ? value : [value]) {
      if (typeof id === "string") {
        used.add(id);
      }
    }
  }
  return (Array.isArray(entityIds) ? entityIds : []).filter(
    (id) => typeof id === "string" && !used.has(id),
  );
}
