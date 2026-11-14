// The form of a schema 2 card (cards spec C.7) built on the fake DOM: one
// row per kind of option, a greyed row with its reason, one line for a kind
// the panel does not know, and the named sizes in step with the picture.
import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadStrings } from "../../custom_components/apollo_tab/frontend/api.js";
import { buildCardForm2 } from "../../custom_components/apollo_tab/frontend/card-form.js";
import { installFakeDom } from "./fake-dom.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const strings = JSON.parse(
  fs.readFileSync(path.resolve(here, "../../custom_components/apollo_tab/library/strings.json"), "utf8"),
);
await loadStrings({ sendMessagePromise: async () => ({ strings }) });

const COMPONENT = {
  id: "me/every-option",
  schema: 2,
  name: "Every option",
  description: "A card with one option of each kind.",
  has_detail: true,
  params: { entity: { kind: "entity", domains: ["light"], domain: "light", multiple: false, label: "Light", help: "" } },
  variants: [
    { id: "small", name: "Small", grid: [6, 3], picker: true },
    { id: "big", name: "Big", grid: [12, 6], picker: true },
    { id: "page", name: "Controls", grid: [18, 11], picker: false },
  ],
  options: [
    { name: "dim", type: "toggle", section: "controls", label: "Brightness", help: "A bar to dim it.", default: true },
    {
      name: "level",
      type: "toggle",
      section: "controls",
      label: "Level line",
      default: true,
      needs: "can.brightness",
      needs_text: "This light cannot be dimmed",
    },
    {
      name: "mode",
      type: "choice",
      section: "controls",
      label: "Colour",
      default: "bar",
      choices: [
        { value: "none", label: "Off" },
        { value: "bar", label: "Colour bar" },
      ],
    },
    { name: "effects", type: "choice", multiple: true, max: 2, from: "can.effect_list", default_first: 1, section: "controls", label: "Effects" },
    { name: "favs", type: "colours", section: "controls", label: "Favourites", max: 3, default: ["#FF0000", "2700K"] },
    { name: "word", type: "text", section: "shows", label: "Word", default: "On", max: 20 },
    { name: "count", type: "number", section: "shows", label: "Count", default: 2, min: 0, max: 9 },
    { name: "tone", type: "colour", section: "look", label: "Tone", default: "accent" },
    { name: "badge", type: "icon", section: "look", label: "Badge", default: null },
    { name: "wobble", type: "slider", section: "controls", label: "Wobble" },
  ],
  standard: { title: true, icon: true, hold: true, lit: null, tint: false },
  tap: null,
  notes: [],
};

const FACTS = { has: { entity: true }, can: { brightness: false, effect_list: ["Rainbow", "Candle", "Fire"] } };

function config(card) {
  return { views: [{ type: "sections", max_columns: 3, sections: [{ type: "grid", cards: [card] }] }] };
}

function baseCtx(card, calls = []) {
  const ctx = {
    hass: { states: {} },
    config: config(card),
    card,
    component: COMPONENT,
    readOnly: false,
    facts: FACTS,
    newer: null,
    compact: false,
    themes: [],
    dashboardTheme: "midnight",
    maxWide: 6,
    canEarlier: false,
    canLater: false,
    pages: [],
  };
  for (const name of ["onSwap", "onOption", "onStandard", "onVariant", "onLook", "onParam", "onTitle", "onResize", "onStyle", "onMove", "onRemove", "onMoveToPage", "onWholeScreen"]) {
    ctx[name] = (...args) => calls.push([name, ...args]);
  }
  return ctx;
}

function build(card, calls = []) {
  return buildCardForm2(baseCtx(card, calls));
}

function withDom(run) {
  const uninstall = installFakeDom();
  globalThis.getComputedStyle ??= () => ({ getPropertyValue: () => "" });
  try {
    return run();
  } finally {
    uninstall();
  }
}

const rows = (form) => form.descendants().filter((node) => node.dataset.test === "option-row");
const row = (form, name) => rows(form).find((node) => node.dataset.option === name);
const text = (node) => node.textContent;
const fire = (node, type) => (node.listeners.get(type) || []).forEach((listener) => listener({ target: node }));

test("the form has a row for each kind of option it knows, in the file's order", () => {
  withDom(() => {
    const card = { type: "custom:apollo-tab-card", component: COMPONENT.id, params: { entity: "light.x" } };
    const form = build(card);
    assert.deepStrictEqual(
      rows(form).map((node) => node.dataset.option),
      ["word", "count", "dim", "level", "mode", "effects", "favs", "tone", "badge"],
    );
    // A toggle is a switch row with its help line.
    const dim = row(form, "dim");
    assert.ok(dim.classList.contains("option-switch"));
    assert.match(text(dim), /Brightness/);
    assert.match(text(dim), /A bar to dim it\./);
    // A multiple choice lists what the device offers.
    assert.match(text(row(form, "effects")), /Rainbow.*Candle.*Fire/);
    // Colours are swatches; a warm white is named under its swatch, so it
    // does not read as an orange.
    const favs = row(form, "favs");
    assert.equal(favs.descendants().filter((node) => node.dataset.test === "swatch").length, 2);
    assert.match(text(favs), /Warm white/);
    assert.match(text(favs), /Up to 3 colours\./);
  });
});

test("a row the device cannot use is greyed and off, with the file's reason", () => {
  withDom(() => {
    const card = { type: "custom:apollo-tab-card", component: COMPONENT.id, params: { entity: "light.x" }, options: { level: true } };
    const level = row(build(card), "level");
    assert.equal(level.dataset.usable, "false");
    assert.ok(level.classList.contains("unusable"));
    const input = level.descendants().find((node) => node.localName === "input");
    assert.equal(input.disabled, true);
    assert.equal(input.checked, false);
    assert.match(text(level), /This light cannot be dimmed\./);
    // The reason has its own line, which the switch names as its
    // description; the help line does not carry it.
    const reason = level.descendants().find((node) => node.dataset.test === "option-reason");
    assert.equal(reason.textContent, "This light cannot be dimmed.");
    assert.ok(input.getAttribute("aria-describedby").split(" ").includes(reason.id));
    const helpers = level.descendants().filter((node) => node.classList.contains("helper"));
    assert.ok(helpers.every((node) => !node.textContent.includes("cannot be dimmed")));
  });
});

test("the card's own rows come right after Size, then name and icon, then tap and hold", () => {
  withDom(() => {
    const card = { type: "custom:apollo-tab-card", component: COMPONENT.id, params: { entity: "light.x" } };
    const form = build(card);
    const parts = form.children.filter((node) => node.classList.contains("form-block")).map((node) => node.children[0]?.textContent);
    assert.deepStrictEqual(parts, [
      strings["form.device"],
      strings["form.size"],
      strings["form.shows"],
      strings["form.on_card"],
      strings["form.name_icon"],
      strings["form.touch"],
      strings["form.look"],
      strings["form.order"],
    ]);
    // The icon is one line with Change; the grid opens on request.
    const icons = form.descendants().find((node) => node.classList.contains("icon-choice"));
    assert.equal(icons.descendants().filter((node) => node.dataset.test === "card-icon").length, 0);
    fire(icons.descendants().find((node) => node.dataset.test === "icon-change"), "click");
    assert.ok(icons.descendants().filter((node) => node.dataset.test === "card-icon").length > 10);
  });
});

test("a row that shows only while another is on is indented under it", () => {
  withDom(() => {
    const component = {
      ...COMPONENT,
      options: [
        { name: "dim", type: "toggle", section: "controls", label: "Brightness", default: true },
        { name: "bar", type: "toggle", section: "controls", label: "Bar on the tile", default: true, when: ["dim", "can.brightness"] },
        { name: "plain", type: "toggle", section: "controls", label: "Plain", default: true, when: ["can.brightness"] },
      ],
    };
    const facts = { has: { entity: true }, can: { brightness: true } };
    const card = { type: "custom:apollo-tab-card", component: component.id, params: { entity: "light.x" } };
    const form = buildCardForm2({ ...baseCtx(card), component, facts });
    const dependent = Object.fromEntries(rows(form).map((node) => [node.dataset.option, node.classList.contains("option-dependent")]));
    assert.deepStrictEqual(dependent, { dim: false, bar: true, plain: false });
  });
});

test("Add a colour is hidden at the most the card can show", () => {
  withDom(() => {
    const card = { type: "custom:apollo-tab-card", component: COMPONENT.id, params: { entity: "light.x" }, options: { favs: ["#FF0000", "#00FF00", "#0000FF"] } };
    const add = row(build(card), "favs").descendants().find((node) => node.dataset.test === "swatch-add");
    assert.equal(add.hidden, true);
    assert.equal(add.disabled, true);
    const fewer = row(build({ ...card, options: undefined }), "favs").descendants().find((node) => node.dataset.test === "swatch-add");
    assert.equal(fewer.hidden, false);
  });
});

test("Width and Height wait behind Fine-tune while the card is at a named size", () => {
  withDom(() => {
    const calls = [];
    const card = { type: "custom:apollo-tab-card", component: COMPONENT.id, params: { entity: "light.fine" }, variant: "big", grid_options: { columns: 12, rows: 6 } };
    const form = build(card, calls);
    const find = (test) => form.descendants().find((node) => node.dataset.test === test);
    assert.equal(find("wider"), undefined);
    assert.equal(find("size-reset"), undefined);
    assert.ok(!form.descendants().some((node) => node.classList.contains("size-value")));
    fire(find("size-fine-tune"), "click");
    assert.ok(find("wider"));
    // At the size marked there is nothing to go back to.
    assert.equal(find("size-reset"), undefined);
    fire(find("narrower"), "click");
    assert.deepStrictEqual(calls.at(-1), ["onResize", 1, 2]);
    // Now it differs from Small, the size it shows: Back puts it there.
    fire(find("size-reset"), "click");
    assert.deepStrictEqual(calls.at(-1), ["onVariant", "small"]);
    // The steps stay open when the form is drawn again for the same card,
    // also after it moved; another card starts with them folded.
    assert.ok(build(card).descendants().some((node) => node.dataset.test === "wider"));
    const other = { ...card, params: { entity: "light.y" } };
    assert.ok(!build(other).descendants().some((node) => node.dataset.test === "wider"));
  });
});

test("a kind of option the panel does not know gives one quiet line", () => {
  withDom(() => {
    const card = { type: "custom:apollo-tab-card", component: COMPONENT.id, params: { entity: "light.x" } };
    const form = build(card);
    const lines = form.descendants().filter((node) => node.textContent === strings["form.option_unknown"]);
    assert.equal(lines.length, 1);
    assert.equal(row(form, "wobble"), undefined);
  });
});

test("the card's own controls sit under On the card, with the line about larger sizes", () => {
  withDom(() => {
    const card = { type: "custom:apollo-tab-card", component: COMPONENT.id, params: { entity: "light.x" } };
    const form = build(card);
    const note = form.descendants().find((node) => node.dataset.test === "on-card-note");
    assert.equal(note.textContent, strings["form.on_card_some"]);
    assert.ok(form.descendants().some((node) => node.textContent === strings["form.on_card"]));
  });
});

test("the size marked is the one the picture shows, and a press on it puts the card back", () => {
  withDom(() => {
    const calls = [];
    // No size picked and 12 x 3 on the grid: the largest size that fits is Small.
    const card = {
      type: "custom:apollo-tab-card",
      component: COMPONENT.id,
      params: { entity: "light.x" },
      grid_options: { columns: 12, rows: 3 },
    };
    const form = build(card, calls);
    const chips = form.descendants().filter((node) => node.dataset.test === "size-chip");
    assert.deepStrictEqual(chips.map((chip) => chip.dataset.variant), ["small", "big"]);
    const radio = (variant) => chips.find((chip) => chip.dataset.variant === variant).children[0];
    assert.equal(radio("small").checked, true);
    assert.equal(radio("big").checked, false);
    fire(radio("small"), "click");
    assert.deepStrictEqual(calls.filter(([name]) => name === "onVariant"), [["onVariant", "small"]]);
    // A click on a size not marked does nothing by itself; its change picks it.
    fire(radio("big"), "click");
    assert.equal(calls.filter(([name]) => name === "onVariant").length, 1);
    fire(radio("big"), "change");
    assert.deepStrictEqual(calls.at(-1), ["onVariant", "big"]);
  });
});

test("after Taller the marked size follows the grid", () => {
  withDom(() => {
    const calls = [];
    const card = { type: "custom:apollo-tab-card", component: COMPONENT.id, params: { entity: "light.x" }, variant: "small", grid_options: { columns: 12, rows: 3 } };
    const form = build(card, calls);
    const taller = form.descendants().find((node) => node.dataset.test === "taller");
    fire(taller, "click");
    assert.deepStrictEqual(calls.at(-1), ["onResize", 2, 2]);
    const chips = form.descendants().filter((node) => node.dataset.test === "size-chip");
    const marked = chips.filter((chip) => chip.children[0].checked).map((chip) => chip.dataset.variant);
    assert.deepStrictEqual(marked, ["big"]);
  });
});
