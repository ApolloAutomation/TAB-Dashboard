import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as model from "../../custom_components/apollo_tab/frontend/model.js";
import * as placement from "../../custom_components/apollo_tab/frontend/placement.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(fs.readFileSync(path.resolve(here, "../fixtures/placement_cases.json"), "utf8")).cases;

const LIGHT = { id: "apollo/light-tile", grid: { columns: 6, rows: 3 } };

function tile(entity, at, cols = 6, rows = 3) {
  const card = { type: model.CARD_TYPE, component: "apollo/light-tile", params: { entity }, grid_options: { columns: cols, rows } };
  if (at) {
    card.apollo_tab = at;
  }
  return card;
}

function dashboard(sections) {
  return { apollo_tab: { version: 1, theme: "midnight" }, views: [{ type: "sections", max_columns: 3, title: "Home", path: "home", sections }] };
}

function placedPage(cards) {
  return dashboard([{ type: "grid", column_span: 3, cards }]);
}

test("freeSlot gives the slot of every shared case, as place_free does", () => {
  for (const item of CASES) {
    const taken = new Set();
    for (const [page, col, row, cols, rows] of item.taken) {
      for (const cell of placement.cellsOf(page, col, row, cols, rows)) {
        taken.add(cell);
      }
    }
    const slot = placement.freeSlot(taken, ...item.size);
    assert.deepEqual([slot.page, slot.col, slot.row], item.slot, item.name);
  }
});

test("rectOfCell and cellOfRect mirror the converter's grid", () => {
  assert.deepEqual(placement.rectOfCell(0, 0, 6, 3), [100, 20, 184, 184]);
  assert.deepEqual(placement.rectOfCell(12, 1, 12, 3), [484, 84, 376, 184]);
  assert.deepEqual(placement.cellOfRect([484, 84, 376, 184]), { col: 12, row: 1, cols: 12, rows: 3 });
  assert.deepEqual(placement.cellOfRect([100, 20, 1144, 56]), { col: 0, row: 0, cols: 36, rows: 1 });
});

test("freezePage stamps the preview's places, merges the sections and turns titles into headings", () => {
  const config = dashboard([
    { type: "grid", title: "Lights", column_span: 1, cards: [tile("light.a"), tile("light.b")] },
    { type: "grid", column_span: 2, cards: [tile("light.c")] },
  ]);
  const preview = {
    layout: {
      pages: [
        { id: "home", view: 0, w: [{ id: 1, r: [100, 20, 376, 56] }, { id: 2, r: [100, 84, 184, 184] }, { id: 3, r: [292, 84, 184, 184] }] },
        { id: "home-2", view: 0, w: [{ id: 4, r: [484, 20, 184, 184] }] },
      ],
    },
    sources: { 1: [0, 0, null], 2: [0, 0, 0], 3: [0, 0, 1], 4: [0, 1, 0] },
    warnings: [],
  };
  const { config: frozen, sources } = placement.freezePage(config, 0, preview);
  const sections = frozen.views[0].sections;
  assert.equal(sections.length, 1);
  assert.equal(sections[0].column_span, 3);
  assert.deepEqual(sections[0].cards[0], {
    type: "heading",
    heading: "Lights",
    grid_options: { columns: 12 },
    apollo_tab: { page: 0, col: 0, row: 0 },
  });
  assert.deepEqual(sections[0].cards[1].apollo_tab, { page: 0, col: 0, row: 1 });
  assert.deepEqual(sections[0].cards[2].apollo_tab, { page: 0, col: 6, row: 1 });
  assert.deepEqual(sections[0].cards[3].apollo_tab, { page: 1, col: 12, row: 0 });
  assert.deepEqual(sections[0].cards[3].grid_options, { columns: 6, rows: 3 });
  assert.deepEqual(sources, { "0.0.t": [0, 0, 0], "0.0.0": [0, 0, 1], "0.0.1": [0, 0, 2], "0.1.0": [0, 0, 3] });
  assert.equal(placement.isPlaced(frozen, 0), true);
  // The draft itself is not touched.
  assert.equal(placement.isPlaced(config, 0), false);
});

test("freezePage leaves a card with no rectangle without a place", () => {
  const config = placedPage([tile("light.a"), tile("light.b")]);
  const preview = { layout: { pages: [{ id: "home", view: 0, w: [{ id: 1, r: [100, 20, 184, 184] }] }] }, sources: { 1: [0, 0, 0] } };
  const frozen = placement.freezePage(config, 0, preview).config;
  assert.ok(frozen.views[0].sections[0].cards[0].apollo_tab);
  assert.equal(Object.hasOwn(frozen.views[0].sections[0].cards[1], "apollo_tab"), false);
});

test("placeCard moves a card and refuses overlap and the grid's edge", () => {
  const config = placedPage([tile("light.a", { page: 0, col: 0, row: 0 }), tile("light.b", { page: 0, col: 6, row: 0 })]);
  const moved = placement.placeCard(config, [0, 0, 0], { page: 0, col: 12, row: 3 });
  assert.deepEqual(moved.views[0].sections[0].cards[0].apollo_tab, { page: 0, col: 12, row: 3 });
  assert.equal(placement.placeCard(config, [0, 0, 0], { page: 0, col: 3, row: 0 }), config, "overlap");
  assert.equal(placement.placeCard(config, [0, 0, 0], { page: 0, col: 33, row: 0 }), config, "right edge");
  assert.equal(placement.placeCard(config, [0, 0, 0], { page: 0, col: 0, row: 10 }), config, "bottom edge");
  assert.equal(placement.placeCard(config, [0, 0, 0], { page: 0, col: -3, row: 0 }), config, "left edge");
  // On another screen the other card is not in the way.
  assert.notEqual(placement.placeCard(config, [0, 0, 0], { page: 1, col: 6, row: 0 }), config);
});

test("sizeCard grows and shrinks, refuses overlap, the edge and the smallest size", () => {
  const card = tile("light.a", { page: 0, col: 0, row: 0 });
  card.variant = "small";
  const config = placedPage([card, tile("light.b", { page: 0, col: 12, row: 0 })]);
  const wider = placement.sizeCard(config, [0, 0, 0], 12, 4);
  assert.deepEqual(wider.views[0].sections[0].cards[0].grid_options, { columns: 12, rows: 4 });
  assert.equal(Object.hasOwn(wider.views[0].sections[0].cards[0], "variant"), false);
  assert.equal(placement.sizeCard(config, [0, 0, 0], 15, 3), config, "overlap");
  assert.equal(placement.sizeCard(config, [0, 0, 0], 6, 13), config, "edge");
  assert.equal(placement.sizeCard(config, [0, 0, 0], 3, 3), config, "too narrow");
  assert.equal(placement.sizeCard(config, [0, 0, 0], 6, 1), config, "too low");
});

test("snap steps are 3 columns and 1 row and stay on the grid", () => {
  const at = { page: 0, col: 6, row: 2 };
  assert.deepEqual(placement.snapMove(at, 6, 3, 100, 70), { page: 0, col: 9, row: 3 });
  assert.deepEqual(placement.snapMove(at, 6, 3, 40, 20), { page: 0, col: 6, row: 2 });
  assert.deepEqual(placement.snapMove(at, 6, 3, -5000, 5000), { page: 0, col: 0, row: 9 });
  assert.deepEqual(placement.snapSize(at, 6, 3, 200, 64), { cols: 12, rows: 4 });
  assert.deepEqual(placement.snapSize(at, 6, 3, -500, -500), { cols: 6, rows: 2 });
  assert.deepEqual(placement.snapSize(at, 6, 3, 5000, 0), { cols: 30, rows: 3 });
  assert.deepEqual(placement.snapSize(at, 12, 1, 0, 300, true), { cols: 12, rows: 1 });
});

test("addCard, duplicateCard and moveCardToPage stamp the first free slot on placed pages", () => {
  const config = placedPage([tile("light.a", { page: 0, col: 0, row: 0 })]);
  const added = model.addCard(config, 0, LIGHT, { entity: "light.b" });
  assert.deepEqual(model.getCard(added.config, added.source).apollo_tab, { page: 0, col: 6, row: 0 });
  const copy = model.duplicateCard(added.config, [0, 0, 0]);
  assert.deepEqual(model.getCard(copy.config, copy.source).apollo_tab, { page: 0, col: 12, row: 0 });
  // A new page is placed from its first card.
  const moved = model.moveCardToPage(copy.config, [0, 0, 2], "new", "Two");
  assert.deepEqual(model.getCard(moved.config, moved.source).apollo_tab, { page: 0, col: 0, row: 0 });
  // A card moved to a flowing page loses its place; one added there gets none.
  const flow = structuredClone(config);
  flow.views.push({ type: "sections", max_columns: 3, title: "Flow", path: "flow", sections: [{ type: "grid", cards: [tile("light.f")] }] });
  const toFlow = model.moveCardToPage(flow, [0, 0, 0], 1);
  assert.equal(Object.hasOwn(model.getCard(toFlow.config, toFlow.source), "apollo_tab"), false);
  const addedFlow = model.addCard(flow, 1, LIGHT, {});
  assert.equal(Object.hasOwn(model.getCard(addedFlow.config, addedFlow.source), "apollo_tab"), false);
  const copyFlow = model.duplicateCard(flow, [1, 0, 0]);
  assert.equal(Object.hasOwn(model.getCard(copyFlow.config, copyFlow.source), "apollo_tab"), false);
});

test("a placed page has no list moves and the whole width for sizes", () => {
  const config = placedPage([tile("light.a", { page: 0, col: 0, row: 0 }), tile("light.b", { page: 0, col: 6, row: 0 })]);
  assert.equal(model.canMove(config, [0, 0, 1], -1), false);
  assert.equal(model.canMove(config, [0, 0, 0], 1), false);
  assert.equal(model.maxUnitsWide(config, [0, 0, 0]), model.MAX_UNITS_WIDE);
  // updateCard carries a place and takes it away.
  const moved = model.updateCard(config, [0, 0, 0], { apollo_tab: { page: 0, col: 3, row: 6 } });
  assert.deepEqual(model.getCard(moved, [0, 0, 0]).apollo_tab, { page: 0, col: 3, row: 6 });
  const gone = model.updateCard(config, [0, 0, 0], { apollo_tab: undefined });
  assert.equal(Object.hasOwn(model.getCard(gone, [0, 0, 0]), "apollo_tab"), false);
});

test("readPosition takes whole numbers only", () => {
  assert.deepEqual(placement.readPosition({ apollo_tab: { col: 3, row: 2 } }), { page: 0, col: 3, row: 2 });
  for (const bad of [{ col: "3", row: 2 }, { col: 3, row: true }, { col: 3.5, row: 0 }, { page: -1, col: 0, row: 0 }, { page: 32, col: 0, row: 0 }, "x"]) {
    assert.equal(placement.readPosition({ apollo_tab: bad }), null, JSON.stringify(bad));
  }
});
