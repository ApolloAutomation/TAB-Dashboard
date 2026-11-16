// Free placement of cards on the tablet picture. A card's own place is
// apollo_tab {page, col, row} on the page grid of 36 columns by 12 rows;
// its size stays in grid_options. A page is "placed" once one of its cards
// has a place. The converter (maker/convert.py) reads the same keys, and
// firstFree here gives the slot place_free there gives (the shared cases in
// tests/fixtures/placement_cases.json hold both to it). Pure: no DOM.

export const GRID_COLS = 36;
export const GRID_ROWS = 12;
export const SNAP_COLS = 3;
export const SNAP_ROWS = 1;
export const MIN_COLS = 6;
export const MIN_ROWS = 2;
// The highest screen a place may name, as the converter reads it.
export const MAX_PAGE = 31;

const COL_W = 32;
const ROW_H = 64;
const ORIGIN_X = 96;
const ORIGIN_Y = 16;
const INSET = 4;

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isWhole(value) {
  return Number.isInteger(value) && typeof value === "number";
}

function isGrid(section) {
  return isObject(section) && !Object.hasOwn(section, "strategy") && (!Object.hasOwn(section, "type") || section.type === "grid");
}

function keyOf(vi, si, ci) {
  return `${vi}.${si}.${ci === null ? "t" : ci}`;
}

// The tablet's rectangle of a card at these cells, as card_rect draws it.
export function rectOfCell(col, row, cols, rows) {
  return [ORIGIN_X + col * COL_W + INSET, ORIGIN_Y + row * ROW_H + INSET, cols * COL_W - 2 * INSET, rows * ROW_H - 2 * INSET];
}

// The cells of a rectangle the tablet drew; rectOfCell reversed.
export function cellOfRect(rect) {
  const [x, y, w, h] = rect;
  return {
    col: Math.floor((x - ORIGIN_X - INSET) / COL_W),
    row: Math.floor((y - ORIGIN_Y - INSET) / ROW_H),
    cols: Math.floor((w + 2 * INSET) / COL_W),
    rows: Math.floor((h + 2 * INSET) / ROW_H),
  };
}

// A card's own place, or null when it has none or a malformed one.
export function readPosition(card) {
  const raw = isObject(card) ? card.apollo_tab : null;
  if (!isObject(raw)) {
    return null;
  }
  const page = Object.hasOwn(raw, "page") ? raw.page : 0;
  if (![page, raw.col, raw.row].every(isWhole) || page < 0 || page > MAX_PAGE) {
    return null;
  }
  return { page, col: raw.col, row: raw.row };
}

// A card's size in cells. A heading is one row high.
export function cardCells(card) {
  const grid = isObject(card) && isObject(card.grid_options) ? card.grid_options : {};
  const heading = isObject(card) && card.type === "heading";
  let cols = heading ? GRID_COLS : 6;
  if (isWhole(grid.columns) && grid.columns >= 1 && grid.columns <= GRID_COLS) {
    cols = grid.columns;
  } else if (grid.columns === "full") {
    cols = GRID_COLS;
  }
  let rows = heading ? 1 : 3;
  if (!heading && isWhole(grid.rows) && grid.rows >= 1 && grid.rows <= GRID_ROWS) {
    rows = grid.rows;
  }
  return { cols, rows };
}

// Every card of the view's grid sections: { source, card }.
function viewCards(config, vi) {
  const view = isObject(config) && Array.isArray(config.views) ? config.views[vi] : null;
  const out = [];
  if (!isObject(view) || !Array.isArray(view.sections)) {
    return out;
  }
  view.sections.forEach((section, si) => {
    if (!isGrid(section) || !Array.isArray(section.cards)) {
      return;
    }
    section.cards.forEach((card, ci) => {
      if (isObject(card)) {
        out.push({ source: [vi, si, ci], card });
      }
    });
  });
  return out;
}

function sameSource(a, b) {
  return Array.isArray(a) && Array.isArray(b) && a[0] === b[0] && a[1] === b[1] && a[2] === b[2];
}

export function isPlaced(config, vi) {
  return viewCards(config, vi).some(({ card }) => readPosition(card) !== null);
}

// True when the view has no card and no section title yet.
export function isEmptyPage(config, vi) {
  const view = isObject(config) && Array.isArray(config.views) ? config.views[vi] : null;
  const sections = isObject(view) && Array.isArray(view.sections) ? view.sections : [];
  return !sections.some(
    (section) =>
      isObject(section) &&
      ((typeof section.title === "string" && section.title.length > 0) ||
        (Array.isArray(section.cards) && section.cards.length > 0)),
  );
}

export function cellsOf(page, col, row, cols, rows) {
  const out = [];
  for (let dr = 0; dr < rows; dr += 1) {
    for (let dc = 0; dc < cols; dc += 1) {
      out.push(`${page},${col + dc},${row + dr}`);
    }
  }
  return out;
}

// The cells the placed cards of a view use, on one screen or (page null)
// on all of them; without the card at exceptSource. A place past the edge
// counts where the converter moves it.
export function occupied(config, vi, page = null, exceptSource = null) {
  const taken = new Set();
  for (const { source, card } of viewCards(config, vi)) {
    const at = readPosition(card);
    if (!at || sameSource(source, exceptSource) || (page !== null && at.page !== page)) {
      continue;
    }
    const { cols, rows } = cardCells(card);
    const col = Math.min(Math.max(at.col, 0), GRID_COLS - cols);
    const row = Math.min(Math.max(at.row, 0), GRID_ROWS - rows);
    for (const cell of cellsOf(at.page, col, row, cols, rows)) {
      taken.add(cell);
    }
  }
  return taken;
}

// Whether a card of that size fits at col, row of `page` with nothing under it.
export function canPlace(taken, page, col, row, cols, rows) {
  if (col < 0 || row < 0 || col + cols > GRID_COLS || row + rows > GRID_ROWS) {
    return false;
  }
  return cellsOf(page, col, row, cols, rows).every((cell) => !taken.has(cell));
}

// The first free slot, row by row from the top left of screen 0, then the
// next screen. Mirrors geometry.place_free.
export function freeSlot(taken, cols, rows) {
  const width = Math.min(Math.max(cols, 1), GRID_COLS);
  const height = Math.min(Math.max(rows, 1), GRID_ROWS);
  for (let page = 0; ; page += 1) {
    for (let row = 0; row + height <= GRID_ROWS; row += 1) {
      for (let col = 0; col + width <= GRID_COLS; col += 1) {
        if (canPlace(taken, page, col, row, width, height)) {
          return { page, col, row };
        }
      }
    }
  }
}

export function firstFree(config, vi, cols, rows, exceptSource = null) {
  return freeSlot(occupied(config, vi, null, exceptSource), cols, rows);
}

// The screens of a view in the preview: indexes into layout.pages.
function screensOf(preview, vi) {
  const pages = isObject(preview) && isObject(preview.layout) && Array.isArray(preview.layout.pages) ? preview.layout.pages : [];
  const out = [];
  pages.forEach((page, index) => {
    if (isObject(page) && page.view === vi && !(index > 0 && page.sub === 1)) {
      out.push(page);
    }
  });
  return out;
}

// Gives every item of the view the place and size the preview draws it at,
// so the page looks exactly the same afterwards: section titles become
// heading cards and all grid sections one whole width section. Returns
// { config, sources }, sources mapping each old source key to its new
// source. A card with no rectangle in the preview stays without a place;
// the converter flows it into the first free slot.
export function freezePage(config, vi, preview) {
  const next = structuredClone(config);
  const view = isObject(next) && Array.isArray(next.views) ? next.views[vi] : null;
  if (!isObject(view) || !Array.isArray(view.sections)) {
    return { config: next, sources: {} };
  }
  const where = new Map();
  const sourceMap = isObject(preview?.sources) ? preview.sources : {};
  const warnings = Array.isArray(preview?.warnings) ? preview.warnings : [];
  screensOf(preview, vi).forEach((page, ordinal) => {
    for (const item of Array.isArray(page.w) ? page.w : []) {
      const source = sourceMap[String(item?.id)];
      if (Array.isArray(source) && Array.isArray(item.r)) {
        const key = keyOf(...source);
        if (!where.has(key)) {
          where.set(key, { page: ordinal, rect: item.r });
        }
      }
    }
    for (const warning of warnings) {
      if (isObject(warning) && warning.page === page.id && Array.isArray(warning.r) && warning.r.length === 4) {
        const key = keyOf(warning.view, warning.section, warning.card);
        if (!where.has(key)) {
          where.set(key, { page: ordinal, rect: warning.r });
        }
      }
    }
  });
  const cards = [];
  const rest = [];
  const sources = {};
  const stamp = (card, spot) => {
    const { col, row, cols, rows } = cellOfRect(spot.rect);
    const grid = isObject(card.grid_options) ? { ...card.grid_options } : {};
    grid.columns = cols;
    if (card.type !== "heading") {
      grid.rows = rows;
    }
    card.grid_options = grid;
    card.apollo_tab = { page: spot.page, col, row };
  };
  view.sections.forEach((section, si) => {
    if (!isGrid(section)) {
      rest.push(section);
      return;
    }
    if (typeof section.title === "string" && section.title.length > 0) {
      const heading = { type: "heading", heading: section.title };
      const spot = where.get(keyOf(vi, si, null));
      if (spot) {
        stamp(heading, spot);
      }
      sources[keyOf(vi, si, null)] = [vi, 0, cards.length];
      cards.push(heading);
    }
    (Array.isArray(section.cards) ? section.cards : []).forEach((card, ci) => {
      const spot = where.get(keyOf(vi, si, ci));
      if (isObject(card) && spot) {
        stamp(card, spot);
      }
      sources[keyOf(vi, si, ci)] = [vi, 0, cards.length];
      cards.push(card);
    });
  });
  view.sections = [{ type: "grid", column_span: 3, cards }, ...rest];
  return { config: next, sources };
}

function cardRef(config, source) {
  const [vi, si, ci] = Array.isArray(source) ? source : [];
  const section = config?.views?.[vi]?.sections?.[si];
  return isGrid(section) && Array.isArray(section.cards) && isObject(section.cards[ci]) ? section.cards[ci] : null;
}

// Puts the card at `to` ({page, col, row}). The config comes back as it
// was (the same object) when the card would leave the grid or overlap.
export function placeCard(config, source, to) {
  const card = cardRef(config, source);
  if (!card || !to || ![to.page, to.col, to.row].every(isWhole) || to.page < 0 || to.page > MAX_PAGE) {
    return config;
  }
  const { cols, rows } = cardCells(card);
  if (!canPlace(occupied(config, source[0], to.page, source), to.page, to.col, to.row, cols, rows)) {
    return config;
  }
  const next = structuredClone(config);
  cardRef(next, source).apollo_tab = { page: to.page, col: to.col, row: to.row };
  return next;
}

// Gives the placed card a new size in cells. The same object comes back
// when it would leave the grid, overlap or go under the smallest size. A
// heading keeps its one row. A named size (variant) is dropped, as the
// size steps do.
export function sizeCard(config, source, cols, rows) {
  const card = cardRef(config, source);
  const at = readPosition(card);
  if (!card || !at || !isWhole(cols) || !isWhole(rows)) {
    return config;
  }
  const heading = card.type === "heading";
  const height = heading ? 1 : rows;
  if (cols < (heading ? SNAP_COLS : MIN_COLS) || height < (heading ? 1 : MIN_ROWS)) {
    return config;
  }
  if (!canPlace(occupied(config, source[0], at.page, source), at.page, at.col, at.row, cols, height)) {
    return config;
  }
  const next = structuredClone(config);
  const target = cardRef(next, source);
  target.grid_options = { ...(isObject(target.grid_options) ? target.grid_options : {}), columns: cols };
  if (!heading) {
    target.grid_options.rows = height;
    delete target.variant;
  }
  return next;
}

// Where a pointer moved by (dx, dy) tablet pixels takes a card at
// col, row: whole snap steps, kept inside the grid.
export function snapMove(at, cols, rows, dx, dy) {
  const col = at.col + Math.round(dx / (COL_W * SNAP_COLS)) * SNAP_COLS;
  const row = at.row + Math.round(dy / (ROW_H * SNAP_ROWS)) * SNAP_ROWS;
  return {
    page: at.page,
    col: Math.min(Math.max(col, 0), GRID_COLS - cols),
    row: Math.min(Math.max(row, 0), GRID_ROWS - rows),
  };
}

// The size a corner handle moved by (dx, dy) tablet pixels gives: whole
// snap steps, at least the smallest size, at most to the grid's edge.
export function snapSize(at, cols, rows, dx, dy, heading = false) {
  const minCols = heading ? SNAP_COLS : MIN_COLS;
  const width = cols + Math.round(dx / (COL_W * SNAP_COLS)) * SNAP_COLS;
  const height = heading ? 1 : rows + Math.round(dy / (ROW_H * SNAP_ROWS)) * SNAP_ROWS;
  return {
    cols: Math.min(Math.max(width, Math.min(minCols, cols)), GRID_COLS - at.col),
    rows: heading ? 1 : Math.min(Math.max(height, Math.min(MIN_ROWS, rows)), GRID_ROWS - at.row),
  };
}
