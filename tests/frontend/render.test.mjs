import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  cardTokens,
  loadTabletFont,
  renderCard,
  renderPage,
  tabletImageIconSize,
  tabletThermostatSize,
  tabletThermostatTextWidth,
  thermostatFit,
  thermostatText,
} from "../../custom_components/apollo_tab/frontend/render.js";
import { cardColours, hexOf, legible, mix, readable } from "../../custom_components/apollo_tab/frontend/logic.js";
import { rendererStyles } from "../../custom_components/apollo_tab/frontend/styles.js";
import { FakeElement, installFakeDom } from "./fake-dom.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "../../custom_components/apollo_tab/frontend");

const midnight = {
  id: "midnight",
  wall: "#101418",
  card: "#181C23",
  card_pr: "#232833",
  card2: "#232833",
  card2_pr: "#303746",
  line: "#2A303A",
  tx: "#E8EAED",
  tx2: "#9AA0A8",
  acc: "#F5B547",
  accf: "#F5B547",
  accf_pr: "#D99A2B",
  acct: "#0E1116",
  acc2: "#6CB4FF",
  onbg: "#33291A",
  onbg_pr: "#4A3A20",
  ontx: "#F7E3BC",
  ion: "#F5B547",
  r: 16,
  r2: 10,
  bw: 0,
};

const mono = {
  id: "mono",
  wall: "#0A0A0A",
  card: "#0A0A0A",
  card2: "#202020",
  line: "#F0F4F0",
  tx: "#F0F4F0",
  tx2: "#A6A6A6",
  acc: "#F0F4F0",
  acct: "#0A0A0A",
  acc2: "#F0F4F0",
  onbg: "#F0F4F0",
  onbg_pr: "#C8CCC8",
  ontx: "#0A0A0A",
  ion: "#0A0A0A",
  r: 8,
  r2: 6,
  bw: 2,
};

test("cardTokens keeps the theme's on colours for a plain style", () => {
  const tokens = cardTokens(mono, {
    onbg: "#F0F4F0",
    acc: "#F0F4F0",
    ontx: "#0A0A0A",
    card2: "#202020",
  });

  assert.equal(tokens.ion, "#0A0A0A");
  assert.equal(tokens.onbg_pr, "#C8CCC8");
});

test("cardTokens works out on colours when an element uses another theme", () => {
  const tokens = cardTokens(midnight, {
    acc: "#F0F4F0",
    onbg: "#F0F4F0",
    ontx: "#0A0A0A",
    card2: "#202020",
  });

  assert.equal(tokens.ion, "#0A0A0A");
  assert.equal(tokens.onbg_pr, "#C7CAC7");
});

test("cardTokens keeps a readable accent as the on icon for a custom style", () => {
  const tokens = cardTokens(midnight, {
    acc: "#F5B547",
    onbg: "#433722",
    ontx: "#E8EAED",
  });

  assert.equal(tokens.ion, "#F5B547");
});

test("cardTokens returns the theme unchanged without a style", () => {
  assert.deepEqual(cardTokens(midnight), { ...midnight });
});

test("thermostatText keeps one decimal below 1000", () => {
  assert.equal(thermostatText(21.5), "21.5");
  assert.equal(thermostatText(21), "21");
  assert.equal(thermostatText(999.94), "999.9");
  assert.equal(thermostatText(-0.04), "0");
  assert.equal(thermostatText(0), "0");
});

test("thermostatText drops decimals from 1000 up", () => {
  assert.equal(thermostatText(1534.3), "1534");
  assert.equal(thermostatText(12345.6), "12346");
  assert.equal(thermostatText(2400), "2400");
  assert.equal(thermostatText(-1234.4), "-1234");
});

test("thermostatFit keeps the full size for short values", () => {
  const size = 212;
  const stroke = Math.max(8, size / 14);
  const fit = thermostatFit("21.5", size, stroke);

  assert.equal(fit.fontSize, size / 5);
});

test("thermostat value text stays inside the arc's inner circle", () => {
  // The energy gauge at its default size and one column wider, and the
  // bundled thermostat.
  const geometries = [
    { w: 152, h: 76 },
    { w: 168, h: 76 },
    { w: 344, h: 212 },
  ];
  const values = [0, 21.5, 999.9, 1534.3, 2400, 12345.6, 20000, 99999.9, -1234.4];
  const texts = [...values.map(thermostatText), "–"];

  const textEm = (text) => {
    let em = 0;
    for (const character of text) {
      em += ".,: ".includes(character) ? 0.32 : 0.62;
    }
    return em;
  };

  for (const geometry of geometries) {
    const size = Math.min(geometry.w, geometry.h);
    const stroke = Math.max(8, size / 14);

    for (const text of texts) {
      const fit = thermostatFit(text, size, stroke);
      const width = fit.fontSize * textEm(text);
      const height = fit.fontSize * 1.2;
      const where = `${geometry.w}x${geometry.h} ${text}`;

      assert.ok(Math.hypot(width, height) <= fit.innerDiameter, `${where} fits inside the circle`);
      assert.ok(width <= fit.maxWidth + 1e-9, `${where} fits within the maximum width`);
      assert.ok(fit.fontSize <= size / 5 + 1e-9, `${where} does not exceed the base size`);
    }
  }

  const size = 76;
  const stroke = Math.max(8, size / 14);
  assert.ok(thermostatFit("12346", size, stroke).fontSize >= 10);
});

test("the tablet's thermostat value has the tablet's fixed sizes (contract 4.7)", () => {
  // The largest of 48, 34, 20, 18, 14 not above thermostatFit; 48 only for
  // digits. Cases from the editor and journey dumps.
  const cases = [
    ["23.5", 212, 34], // fit 42.4
    ["20", 212, 34],
    ["–", 212, 34],
    ["1235", 76, 14], // fit 15.2
    ["21.5", 300, 48], // fit 60
    ["-5", 300, 48],
    ["–", 300, 34], // never 48: the digits font has no "–"
    ["21.5", 120, 20], // fit 24
    ["12346", 76, 14], // fit below 14 still gets 14
  ];
  for (const [text, side, size] of cases) {
    assert.equal(tabletThermostatSize(text, side), size, `${text} in ${side}`);
    const fit = thermostatFit(text, side, Math.max(8, side / 14)).fontSize;
    assert.ok(size <= Math.max(fit, 14), `${text} in ${side} is not above the fit`);
  }
});

test("the tablet's thermostat value steps down a size while it is wider than its box (contract 4.7)", () => {
  // advanceFor(px) is the width of one character at px; the tablet adds
  // whole pixels, so 31.4 px digits count 31 each.
  const em = (factor) => (px) => () => factor * px;
  const cases = [
    // [text, side, character width in em, size]
    ["4040", 248, 0.66, 34], // 4 x 32 = 128 px at 48 in a 125 px box; 4 x 22 at 34
    ["4040", 248, 31.4 / 48, 48], // 4 x 31 = 124 px: fits at 48
    ["21.5", 300, 0.62, 48], // as thermostatFit counts: fits
    ["–", 300, 0.62, 34], // never 48: the digits font has no "–"
    ["1234", 300, 1.5, 20], // 288 px at 48, 204 at 34, 120 at 20 in 147
    ["1234", 300, 3, 14], // too wide even at 14: 14, which is cut
    ["40000", 76, 0.66, 14], // first pick 14 already
  ];
  for (const [text, side, factor, size] of cases) {
    assert.equal(tabletThermostatSize(text, side, em(factor)), size, `${text} in ${side} at ${factor} em`);
  }
  // A size that cannot be measured stops the steps there.
  assert.equal(tabletThermostatSize("1234", 300, (px) => (px === 48 ? () => 72 : null)), 34);
  assert.equal(tabletThermostatSize("1234", 300, () => null), 48);
});

// ---- drawing a page, with a fake DOM ----------------------------------

const CARD = {
  id: 1,
  t: "card",
  r: [100, 20, 376, 248],
  w: [
    { id: 2, t: "switch", r: [116, 30, 64, 36], value: { s: 1 }, tap: { p: 0 } },
    { id: 3, t: "button", r: [200, 30, 100, 40], text: "Go", tap: { p: 1 } },
    { id: 4, t: "slider", r: [116, 80, 344, 40], value: { s: 2 }, min: 0, max: 100, step: 1 },
    { id: 5, t: "thermostat", r: [116, 120, 120, 120], value: { s: 3 }, min: 5, max: 30, step: 0.5 },
    { id: 6, t: "chart", r: [250, 120, 100, 50], value: { s: 4 }, kind: 0 },
    { id: 7, t: "image", r: [250, 180, 210, 60], value: { s: 5 } },
  ],
};

function layoutWith(theme = {}) {
  return {
    v: 1,
    screen: [1280, 800],
    theme: { ...midnight, bw: 3, ...theme },
    nav: [{ page: "home", title: "Home" }],
    pages: [{ id: "home", title: "Home", w: [CARD] }],
  };
}

function draw(values, options = {}, theme = {}) {
  const uninstall = installFakeDom();
  try {
    const host = document.createElement("div");
    renderPage(host, layoutWith(theme), 0, { values, errors: {} }, { sx: 1, sy: 1, ...options });
    return host;
  } finally {
    uninstall();
  }
}

function rule(selector) {
  const start = rendererStyles.indexOf(`${selector} {`);
  assert.ok(start >= 0, `no rule for ${selector}`);
  return rendererStyles.slice(start, rendererStyles.indexOf("}", start));
}

const ALL_VALUES = { 1: 1, 2: 40, 3: 21.5, 4: [1, 2, 3], 5: "mdi:cctv" };

test("card children sit at their absolute rectangles; the border does not move them", () => {
  const host = draw(ALL_VALUES);
  const [card] = host.querySelectorAll(".at-card");
  assert.equal(card.children.length, 1);
  const [body] = card.children;
  assert.ok(body.classList.contains("at-card-body"));
  // Offsets from the card's outer edge, as in the layout...
  const button = body.querySelector(".at-button");
  assert.equal(button.style.left, "100px");
  assert.equal(button.style.top, "10px");
  // ...and the layer starts at that outer edge, outside the border.
  assert.match(rule(".at-card-body"), /position: absolute;\s+inset: calc\(-1 \* var\(--at-bw, 0px\) \* var\(--at-f, 1\)\);/);
  assert.match(rule(".at-card"), /border: calc\(var\(--at-bw, 0px\) \* var\(--at-f, 1\)\) solid/);
  assert.equal(card.style.getPropertyValue("--at-bw"), "3px");
});

test("a switch, slider, thermostat, chart or image without a value is at 40% and takes no touch", () => {
  const kinds = [".at-switch", ".at-slider", ".at-thermostat", ".at-chart", ".at-image"];
  const full = draw(ALL_VALUES);
  for (const kind of kinds) {
    assert.ok(!full.querySelector(kind).classList.contains("at-none"), kind);
  }
  const empty = draw({ 1: null, 2: null });
  for (const kind of kinds) {
    assert.ok(empty.querySelector(kind).classList.contains("at-none"), kind);
  }
  // A button has no value to miss.
  assert.ok(!empty.querySelector(".at-button").classList.contains("at-none"));
  assert.match(rule(".at-none"), /opacity: 0\.4;\s+pointer-events: none;/);
});

// The at-none class stops the pointer only. A focused slider would still
// step from its lowest value on an arrow key, and Enter or Space would
// still press a switch.
test("a slider or switch without a value takes no key press", () => {
  const uninstall = installFakeDom();
  try {
    const card = {
      id: 1,
      t: "card",
      r: [0, 0, 376, 248],
      w: [
        { id: 2, t: "switch", r: [16, 30, 64, 36], value: { s: 1 }, tap: { p: 0 } },
        { id: 4, t: "slider", r: [16, 80, 344, 40], value: { s: 2 }, min: 0, max: 255, step: 1, change: { p: 1 } },
      ],
    };
    const sent = [];
    const state = (values, errors = {}, feedback = new Map()) => ({ values, errors, tokens: {}, feedback });
    const host = document.createElement("div");
    const renderer = renderCard(host, card, state({ 1: null, 2: null }), {
      sx: 1,
      sy: 1,
      interactive: true,
      onTap: (widget) => sent.push(["tap", widget.id]),
      onChange: (widget, value, final) => sent.push(["change", widget.id, value, final]),
    });
    const slider = host.querySelector(".at-slider");
    const toggle = host.querySelector(".at-switch");
    let prevented = 0;
    const press = (key) => {
      for (const listener of slider.listeners.get("keydown")) {
        listener({ key, preventDefault: () => (prevented += 1) });
      }
    };
    const off = (label) => {
      press("ArrowUp");
      press("ArrowDown");
      assert.deepEqual(sent, [], label);
      // The key is left to the page.
      assert.equal(prevented, 0, label);
      assert.equal(slider.tabIndex, -1, label);
      assert.equal(slider.getAttribute("aria-disabled"), "true", label);
    };

    off("no values");
    assert.equal(toggle.disabled, true);

    // Only the slider's value cannot be read.
    renderer.update(state({ 1: 1 }, { 2: "unavailable" }));
    off("an error for the slider's value");
    assert.equal(toggle.disabled, false);

    renderer.update(state({ 1: 1, 2: 40 }));
    assert.equal(slider.tabIndex, 0);
    assert.equal(slider.getAttribute("aria-disabled"), null);
    assert.equal(toggle.disabled, false);
    press("ArrowUp");
    assert.deepEqual(sent, [["change", 4, 41, true]]);
    assert.equal(prevented, 1);

    // A change that waits for its answer shows a value, so it stays in reach.
    sent.length = 0;
    const waiting = new Map([
      [2, { phase: "pending", value: "on", until: 0 }],
      [4, { phase: "pending", value: 41, until: 0 }],
    ]);
    renderer.update(state({ 1: null, 2: null }, {}, waiting));
    assert.equal(toggle.disabled, false);
    assert.equal(slider.tabIndex, 0);
    assert.equal(slider.getAttribute("aria-disabled"), null);
    press("ArrowUp");
    assert.deepEqual(sent, [["change", 4, 42, true]]);

    // A card that is only shown never takes a press, with or without values.
    const shown = document.createElement("div");
    renderCard(shown, card, state({ 1: 1, 2: 40 }), { sx: 1, sy: 1 });
    assert.equal(shown.querySelector(".at-switch").disabled, true);
    assert.equal(shown.querySelector(".at-slider").tabIndex, -1);
  } finally {
    uninstall();
  }
});

test("the chart's baseline fills pixel row h - 2, as on the tablet", () => {
  // Contract 4.7: a 1 px line one pixel above the bottom. The chart of CARD
  // is 50 tablet pixels high, so the line is row 48: from y 48 to y 49.
  for (const scale of [1, 0.5, 0.75]) {
    const host = draw(ALL_VALUES, { sx: scale, sy: scale });
    const line = host.querySelector(".at-chart-baseline");
    const y = Number(line.getAttribute("y1"));
    const width = Number(line.getAttribute("stroke-width"));
    assert.equal(line.getAttribute("y2"), line.getAttribute("y1"));
    assert.equal((y - width / 2) / scale, 48, `top of the line at scale ${scale}`);
    assert.equal((y + width / 2) / scale, 49, `bottom of the line at scale ${scale}`);
  }
  // The CSS does not set another width over it.
  assert.doesNotMatch(rule(".at-chart-baseline"), /stroke-width/);
});

test("the pulse uses accf, and a waiting outline on an on card uses ion", () => {
  const host = draw(ALL_VALUES, {}, { accf: "#123456", acc: "#F5B547" });
  const [card] = host.querySelectorAll(".at-card");
  assert.equal(card.style.getPropertyValue("--at-accf"), "#123456");
  assert.match(rule(".at-button.active"), /background: var\(--at-accf, var\(--at-acc\)\);/);
  assert.match(rule(".at-button.active"), /color: var\(--at-acct\);/);
  assert.match(
    rendererStyles,
    /\.at-card\.is-on \.at-button\.busy,\s*\.at-card\.is-on \.at-switch\.busy \{\s*outline-color: var\(--at-ion, var\(--at-acc\)\);/,
  );
});

test("the tablet preview draws the thermostat value at the tablet's size; the editor fits it", () => {
  // CARD's thermostat is 120 by 120: "21.5" fits 24 px, the tablet draws 20.
  for (const scale of [1, 0.5]) {
    const tablet = draw(ALL_VALUES, { sx: scale, sy: scale, tablet: true }).querySelector(".at-thermostat-value");
    assert.equal(tablet.style.fontSize, `${20 * scale}px`, `tablet at scale ${scale}`);
    const editor = draw(ALL_VALUES, { sx: scale, sy: scale }).querySelector(".at-thermostat-value");
    assert.equal(editor.style.fontSize, `${24 * scale}px`, `editor at scale ${scale}`);
  }
  // No value: the "–" at a text size too.
  const none = draw({ ...ALL_VALUES, 3: null }, { tablet: true }).querySelector(".at-thermostat-value");
  assert.equal(none.style.fontSize, "20px");
});

test("the tablet preview draws the image placeholder for a picture, at a tablet size", () => {
  const picture = { ...ALL_VALUES, 5: "/api/camera_proxy/camera.drive?token=1" };
  const editor = draw(picture);
  assert.equal(editor.querySelector(".at-image").querySelector("img").localName, "img");
  assert.ok(!editor.querySelector(".at-page").classList.contains("at-tablet"));

  const tablet = draw(picture, { tablet: true });
  const image = tablet.querySelector(".at-image");
  assert.equal(image.querySelector("img"), null);
  const [icon] = image.children;
  assert.equal(icon.icon, "mdi:image-outline");
  // min(210, 60) / 2 = 30: the largest tablet size not above it is 28.
  assert.equal(icon.style.width, "28px");
  // An icon stays an icon.
  const glyph = draw(ALL_VALUES, { tablet: true }).querySelector(".at-image").children[0];
  assert.equal(glyph.icon, "mdi:cctv");
  // No value: the placeholder, dimmed.
  const none = draw({ ...ALL_VALUES, 5: null }, { tablet: true }).querySelector(".at-image");
  assert.equal(none.children[0].icon, "mdi:image-outline");
  assert.ok(none.classList.contains("at-none"));
});

test("the tablet preview draws a box where the tablet has no glyph; the editor does not", () => {
  const box = "\u25a1";
  const layout = {
    v: 1,
    screen: [1280, 800],
    theme: midnight,
    nav: [],
    pages: [
      {
        id: "home",
        title: "Home",
        w: [
          { id: 1, t: "heading", r: [100, 0, 400, 40], text: "Küche Κουζίνα" },
          {
            id: 2,
            t: "card",
            r: [100, 40, 376, 248],
            hr: [116, 56, 344, 32],
            title: "Дом",
            w: [
              { id: 3, t: "label", r: [116, 100, 300, 28], text: "日本 ok", size: 1 },
              { id: 4, t: "button", r: [116, 140, 100, 40], text: "Go 😀", tap: { p: 1 } },
            ],
          },
        ],
      },
    ],
  };
  const drawLayout = (options) => {
    const uninstall = installFakeDom();
    try {
      const host = document.createElement("div");
      renderPage(host, layout, 0, { values: {}, errors: {} }, { sx: 1, sy: 1, ...options });
      return host;
    } finally {
      uninstall();
    }
  };
  const tablet = drawLayout({ tablet: true });
  assert.equal(tablet.querySelector(".at-heading").querySelector(".at-text").textContent, `Küche ${box.repeat(7)}`);
  assert.equal(tablet.querySelector(".at-label").querySelector(".at-text").textContent, `${box}${box} ok`);
  assert.equal(tablet.querySelector(".at-button-text").textContent, `Go ${box}`);
  const editor = drawLayout({});
  assert.equal(editor.querySelector(".at-heading").querySelector(".at-text").textContent, "Küche Κουζίνα");
  assert.equal(editor.querySelector(".at-label").querySelector(".at-text").textContent, "日本 ok");
  assert.equal(editor.querySelector(".at-button-text").textContent, "Go 😀");
});

test("tablet image icon sizes follow contract 4.7", () => {
  assert.equal(tabletImageIconSize(344, 116), 48);
  assert.equal(tabletImageIconSize(184, 184), 72);
  assert.equal(tabletImageIconSize(60, 60), 28);
  assert.equal(tabletImageIconSize(40, 40), 24);
});

test("the tablet preview uses the tablet's font, shipped with its licence", () => {
  const host = draw(ALL_VALUES, { tablet: true });
  assert.ok(host.querySelector(".at-page").classList.contains("at-tablet"));
  assert.match(rule(".at-tablet *"), /font-weight: 500;/);
  assert.match(rendererStyles, /"Apollo TAB-1 Montserrat"/);
  const font = fs.readFileSync(path.join(frontend, "fonts/Montserrat-Medium.ttf"));
  assert.ok(font.length > 100000);
  assert.match(fs.readFileSync(path.join(frontend, "fonts/Montserrat-OFL.txt"), "utf8"), /SIL Open Font License/);
  const render = fs.readFileSync(path.join(frontend, "render.js"), "utf8");
  assert.match(render, /new URL\("\.\/fonts\/Montserrat-Medium\.ttf", import\.meta\.url\)/);
});

test("the editor and the tablet preview ask for the tablet drawing", () => {
  for (const name of ["designer.js", "preview.js"]) {
    const source = fs.readFileSync(path.join(frontend, name), "utf8");
    assert.match(source, /tablet: true/, name);
  }
  const card = fs.readFileSync(path.join(frontend, "card.js"), "utf8");
  assert.doesNotMatch(card, /tablet: true/);
});

// ---- layout version 2: every new key, as the tablet draws it -----------

const MID = numberTheme(midnight);

function numberTheme(theme) {
  const out = {};
  for (const [key, value] of Object.entries(theme)) {
    out[key] = typeof value === "string" && value.startsWith("#") ? Number.parseInt(value.slice(1), 16) : value;
  }
  out.bg = out.card;
  return out;
}

// Draws one card of layout version 2 in a fake DOM. Returns the host, the
// renderer and what the card sent.
function drawCard2(card, values = {}, options = {}, tokens = midnight) {
  const uninstall = installFakeDom();
  try {
    const host = document.createElement("div");
    const sent = [];
    const state = (next, extra = {}) => ({
      values: next,
      errors: {},
      tokens: { ...tokens, bg: tokens.card },
      feedback: new Map(),
      ...extra,
    });
    const renderer = renderCard(host, { t: "card", r: [0, 0, 376, 248], ...card }, state(values, options.state), {
      sx: 1,
      sy: 1,
      interactive: Boolean(options.interactive),
      onTap: (widget) => sent.push(["tap", widget.id]),
      onChange: (widget, value, final) => sent.push(["change", widget.id, value, final]),
      onCardTap: () => sent.push(["card"]),
      onHold: (widget) => sent.push(["hold", widget ? widget.id : "card"]),
      ...options.render,
    });
    // update may make elements too, so it gets the fake DOM again.
    const update = (next) => {
      const again = installFakeDom();
      try {
        renderer.update(next);
      } finally {
        again();
      }
    };
    return { host, renderer: { update }, sent, state, card: host.querySelector(".at-card") };
  } finally {
    uninstall();
  }
}

const HEADER = { hr: [16, 16, 344, 24], icon: "mdi:lightbulb", title: "Lamp" };

test("v2 card: a tint makes the card's own accent and on colours", () => {
  const { card } = drawCard2({ ...HEADER, on: { s: 1 }, tint: { s: 2 } }, { 1: "on", 2: "#FF453A" });
  const expected = cardColours(MID, true, 0, 0xff453a);
  assert.ok(card.classList.contains("is-on"));
  assert.equal(card.style.getPropertyValue("--at-onbg"), hexOf(expected.F));
  assert.equal(card.style.getPropertyValue("--at-acc"), hexOf(expected.A));
  assert.equal(card.style.getPropertyValue("--at-ion"), hexOf(expected.FI));
  assert.equal(card.style.getPropertyValue("--at-onsm"), hexOf(expected.FS));
  // An HA colour as a list of three numbers is the same colour.
  const list = drawCard2({ ...HEADER, on: { s: 1 }, tint: { s: 2 } }, { 1: "on", 2: [255, 69, 58] });
  assert.equal(list.card.style.getPropertyValue("--at-onbg"), hexOf(expected.F));
  // No tint value: the theme's own colours.
  const plain = drawCard2({ ...HEADER, on: { s: 1 }, tint: { s: 2 } }, { 1: "on", 2: null });
  assert.equal(plain.card.style.getPropertyValue("--at-onbg"), "#33291A");
});

test("v2 card: lit 1 lights the icon, lit 2 adds an outline, lit 3 keeps the off look", () => {
  const one = drawCard2({ ...HEADER, on: { s: 1 }, lit: 1 }, { 1: 1 });
  assert.ok(!one.card.classList.contains("is-on"));
  assert.ok(one.card.classList.contains("is-lit"));
  assert.equal(one.card.querySelector("ha-icon").style.color, "#F5B547");
  const two = drawCard2({ ...HEADER, on: { s: 1 }, lit: 2 }, { 1: 1 });
  assert.ok(two.card.classList.contains("is-outline"));
  assert.equal(two.card.style.getPropertyValue("--at-bw"), "2px");
  assert.match(rule(".at-card.is-outline"), /border-color: var\(--at-acc/);
  const three = drawCard2({ ...HEADER, on: { s: 1 }, lit: 3 }, { 1: 1 });
  assert.ok(!three.card.classList.contains("is-on"));
  assert.ok(!three.card.classList.contains("is-lit"));
  assert.equal(three.card.querySelector("ha-icon").style.color, "#9AA0A8");
  // Off: lit does nothing.
  const off = drawCard2({ ...HEADER, on: { s: 1 }, lit: 2 }, { 1: 0 });
  assert.ok(!off.card.classList.contains("is-outline"));
});

test("v2 card: un dims the whole card once, at 40%", () => {
  const { card, renderer, state } = drawCard2({ ...HEADER, un: { s: 1 } }, { 1: 1 });
  assert.ok(card.classList.contains("is-un"));
  assert.match(rule(".at-card.is-un > .at-card-body"), /opacity: 0\.4;/);
  renderer.update(state({ 1: 0 }));
  assert.ok(!card.classList.contains("is-un"));
});

test("v2 card: ic replaces the header icon while it has an icon", () => {
  const { card, renderer, state } = drawCard2({ ...HEADER, ic: { s: 1 } }, { 1: "mdi:fan" });
  assert.equal(card.querySelector("ha-icon").icon, "mdi:fan");
  renderer.update(state({ 1: null }));
  assert.equal(card.querySelector("ha-icon").icon, "mdi:lightbulb");
});

test("v2 card: a tap on the card, a hold, and who gets a press", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const button = { id: 3, t: "button", r: [16, 60, 100, 40], text: "Go", tap: { p: 0 } };
  const label = { id: 4, t: "label", r: [16, 120, 100, 20], text: "Hi" };
  const { card, sent } = drawCard2({ tap: { p: 0 }, hold: { p: 1 }, w: [button, label] }, {}, { interactive: true });
  const fire = (type, target, x = 0, y = 0) => {
    for (const listener of card.listeners.get(type) || []) {
      listener({ button: 0, clientX: x, clientY: y, target, preventDefault() {} });
    }
  };
  const labelEl = card.querySelector(".at-label");
  const buttonEl = card.querySelector(".at-button");
  // A tap on a label is the card's.
  fire("pointerdown", labelEl);
  fire("pointerup", labelEl);
  assert.deepEqual(sent, [["card"]]);
  // A tap on a button is the button's own.
  sent.length = 0;
  fire("pointerdown", buttonEl);
  fire("pointerup", buttonEl);
  assert.deepEqual(sent, []);
  // A press that moved 12 px is neither.
  fire("pointerdown", labelEl, 0, 0);
  fire("pointermove", labelEl, 12, 0);
  fire("pointerup", labelEl, 12, 0);
  assert.deepEqual(sent, []);
  // Held 500 ms: a hold, and no tap after it.
  fire("pointerdown", labelEl);
  t.mock.timers.tick(499);
  assert.deepEqual(sent, []);
  t.mock.timers.tick(1);
  fire("pointerup", labelEl);
  assert.deepEqual(sent, [["hold", "card"]]);
  // A hold that begins on a button without its own hold is the card's.
  sent.length = 0;
  fire("pointerdown", buttonEl);
  t.mock.timers.tick(500);
  assert.deepEqual(sent, [["hold", "card"]]);
  // A right click is a hold.
  sent.length = 0;
  fire("contextmenu", labelEl);
  assert.deepEqual(sent, [["hold", "card"]]);
  // A card without tap does not take one.
  const still = drawCard2({ w: [label] }, {}, { interactive: true });
  assert.equal(still.card.listeners.get("pointerdown"), undefined);
});

test("v2 card: from the keyboard, Enter or Space taps the card and the menu key holds it", () => {
  const button = { id: 3, t: "button", r: [16, 60, 100, 40], text: "Go", tap: { p: 0 } };
  const { card, sent } = drawCard2(
    { tap: { p: 0 }, hold: { p: 1 }, w: [button] },
    {},
    { interactive: true, render: { label: "Lamp" } },
  );
  assert.equal(card.getAttribute("tabindex"), "0");
  assert.equal(card.getAttribute("role"), "button");
  assert.equal(card.getAttribute("aria-label"), "Lamp");
  const key = (keyName, target = card, extra = {}) => {
    let stopped = false;
    for (const listener of card.listeners.get("keydown") || []) {
      listener({ key: keyName, target, preventDefault() { stopped = true; }, ...extra });
    }
    return stopped;
  };
  assert.ok(key("Enter"));
  assert.ok(key(" "));
  assert.deepEqual(sent, [["card"], ["card"]]);
  sent.length = 0;
  assert.ok(key("ContextMenu"));
  assert.ok(key("F10", card, { shiftKey: true }));
  assert.deepEqual(sent, [["hold", "card"], ["hold", "card"]]);
  // Keys on a control inside the card are that control's, and a held key
  // does not tap again.
  sent.length = 0;
  assert.ok(!key("Enter", card.querySelector(".at-button")));
  assert.ok(!key("Enter", card, { repeat: true }));
  assert.ok(!key("F10"));
  assert.deepEqual(sent, []);
  // Hold only: Enter does nothing. Neither: the card is not a button at all.
  const holdOnly = drawCard2({ hold: { p: 1 }, w: [button] }, {}, { interactive: true });
  for (const listener of holdOnly.card.listeners.get("keydown")) {
    listener({ key: "Enter", target: holdOnly.card, preventDefault() {} });
  }
  assert.deepEqual(holdOnly.sent, []);
  const widgetHold = drawCard2({ w: [{ ...button, hold: { p: 1 } }] }, {}, { interactive: true });
  assert.equal(widgetHold.card.getAttribute("tabindex"), null);
  assert.equal(widgetHold.card.listeners.get("keydown"), undefined);
  // The editor's picture is not a button.
  const picture = drawCard2({ tap: { p: 0 }, w: [button] });
  assert.equal(picture.card.getAttribute("role"), null);
  assert.match(rule('.at-card[role="button"]:focus-visible'), /outline: calc\(2px \* var\(--at-f, 1\)\)/);
});

test("v2 card: pressed looks of buttons, choice cells and bare images in a browser card", () => {
  const plain = { id: 3, t: "button", r: [16, 60, 100, 40], text: "Go", tap: { p: 0 } };
  const chosen = { id: 4, t: "button", r: [16, 110, 100, 40], text: "On", tap: { p: 0 }, value: { s: 1 } };
  const swatch = { id: 5, t: "button", r: [16, 160, 100, 40], tap: { p: 0 }, c: 0xff0000 };
  const choice = { id: 6, t: "choice", r: [130, 60, 200, 40], texts: ["A", "B"], value: { s: 2 }, change: { p: 1 } };
  const { card } = drawCard2({ w: [plain, chosen, swatch, choice] }, { 1: 1, 2: 0 }, { interactive: true });
  // The card's own pressed colour for a control: card2_pr off, onbg_pr on.
  assert.equal(card.style.getPropertyValue("--at-wpr").toUpperCase(), midnight.card2_pr.toUpperCase());
  const [plainEl, chosenEl, swatchEl] = card.querySelectorAll(".at-button");
  assert.equal(plainEl.style.getPropertyValue("--at-bpr"), "");
  assert.ok(chosenEl.style.getPropertyValue("--at-bpr"));
  assert.ok(swatchEl.style.getPropertyValue("--at-bpr"));
  const faces = card.querySelectorAll(".at-choice-face");
  assert.ok(faces[0].style.getPropertyValue("--at-fpr"));
  assert.equal(faces[1].style.getPropertyValue("--at-fpr"), "");
  assert.match(rule(".at-button:not(:disabled):active"), /var\(--at-bpr, var\(--at-wpr/);
  assert.match(rule(".at-choice-cell:not(:disabled):active > .at-choice-face"), /var\(--at-fpr, var\(--at-wpr/);
  assert.match(rule(".at-image.bare.at-pressable:active"), /var\(--at-wpr/);
  const on = drawCard2({ on: { s: 1 }, w: [plain] }, { 1: 1 }, { interactive: true });
  assert.notEqual(on.card.style.getPropertyValue("--at-wpr"), card.style.getPropertyValue("--at-wpr"));
});

test("v2 label: px, al, c and clocks", () => {
  const label = (extra) => ({ id: 2, t: "label", r: [16, 16, 300, 120], text: "21", ...extra });
  const big = drawCard2({ w: [label({ px: 100 })] }).card.querySelector(".at-label");
  assert.equal(big.style.fontSize, "96px");
  const small = drawCard2({ w: [label({ px: 15, text: "Hall" })] }).card.querySelector(".at-label");
  assert.equal(small.style.fontSize, "15px");
  assert.ok(small.classList.contains("at-label-s"));
  assert.equal(small.style.color, "#9AA0A8");
  const right = drawCard2({ w: [label({ al: 2 })] }).card.querySelector(".at-label");
  assert.equal(right.style.justifyContent, "flex-end");
  const red = drawCard2({ w: [label({ c: { s: 1, roles: { bad: "#FF453A" } } })] }, { 1: "bad" });
  assert.equal(red.card.querySelector(".at-label").style.color, hexOf(legible(0xff453a, MID.card, MID.tx)));
  // A clock counts the age of its value.
  const clock = label({ clk: 1, value: { s: 1 }, text: undefined });
  let age = 0;
  const drawn = drawCard2({ w: [clock] }, { 1: 605.5 }, { state: { age: () => age } });
  assert.equal(drawn.card.querySelector(".at-text").textContent, "10:05");
  age = 60;
  drawn.renderer.update(drawn.state({ 1: 605.5 }, { age: () => age }));
  assert.equal(drawn.card.querySelector(".at-text").textContent, "10:06");
  const twelve = drawCard2({ w: [{ ...clock, clk: 2 }] }, { 1: 30 });
  assert.equal(twelve.card.querySelector(".at-text").textContent, "12:30");
  const none = drawCard2({ w: [clock] }, { 1: null });
  assert.equal(none.card.querySelector(".at-text").textContent, "--:--");
});

test("v2 button: value, c, shape, isz and ic", () => {
  const base = { id: 2, t: "button", r: [16, 16, 120, 120], icon: "mdi:power", text: "Go", tap: { p: 0 } };
  const selected = drawCard2({ w: [{ ...base, value: { s: 1 } }] }, { 1: 1 }).card.querySelector(".at-button");
  assert.ok(selected.classList.contains("selected"));
  assert.equal(selected.style.background, "#F5B547");
  assert.equal(selected.style.color, "#0E1116");
  assert.equal(selected.getAttribute("aria-pressed"), "true");
  const swatch = drawCard2({ w: [{ ...base, c: "#2050FF", value: { s: 1 } }] }, { 1: 1 }).card.querySelector(".at-button");
  assert.equal(swatch.style.background, "#2050FF");
  assert.equal(swatch.style.color, hexOf(readable(0x2050ff)));
  assert.equal(swatch.style.boxShadow, "inset 0 0 0 3px #E8EAED");
  const round = drawCard2({ w: [{ ...base, r: [16, 16, 120, 60], shape: 1 }] }).card.querySelector(".at-button");
  assert.ok(round.classList.contains("round"));
  assert.equal(round.style.width, "60px");
  assert.equal(round.style.left, "46px");
  assert.equal(round.querySelector(".at-button-text"), null);
  const bare = drawCard2({ w: [{ ...base, shape: 2 }] }).card.querySelector(".at-button");
  assert.ok(bare.classList.contains("bare"));
  const large = drawCard2({ w: [{ ...base, isz: 1 }] }).card.querySelector("ha-icon");
  assert.equal(large.style.getPropertyValue("--mdc-icon-size"), "48px");
  const own = drawCard2({ w: [{ ...base, ic: { s: 1 } }] }, { 1: "mdi:fan" }).card.querySelector("ha-icon");
  assert.equal(own.icon, "mdi:fan");
});

test("v2 switch: c colours the track at value 1", () => {
  const sw = { id: 2, t: "switch", r: [16, 16, 64, 36], value: { s: 1 }, c: "#30D158" };
  const on = drawCard2({ w: [sw] }, { 1: 1 }).card.querySelector(".at-switch");
  const track = legible(0x30d158, MID.card, MID.tx);
  assert.equal(on.style.background, hexOf(track));
  assert.equal(on.querySelector(".at-switch-knob").style.background, hexOf(readable(track)));
  const off = drawCard2({ w: [sw] }, { 1: 0 }).card.querySelector(".at-switch");
  assert.equal(off.style.background, undefined);
});

test("v2 slider: bar look along dir 1, its handle and icon, and c", () => {
  const bar = {
    id: 2,
    t: "slider",
    r: [16, 16, 60, 200],
    value: { s: 1 },
    min: 0,
    max: 100,
    step: 1,
    look: 1,
    dir: 1,
    icon: "mdi:brightness-6",
    c: "#FF9F0A",
    change: { p: 1 },
  };
  const { card } = drawCard2({ w: [bar] }, { 1: 50 });
  const slider = card.querySelector(".at-slider");
  assert.ok(slider.classList.contains("bar"));
  const fill = slider.querySelector(".at-slider-fill");
  // From the bottom edge, 100 long.
  assert.equal(fill.style.top, "100px");
  assert.equal(fill.style.height, "100px");
  assert.equal(fill.style.width, "60px");
  const fillColour = legible(0xff9f0a, MID.card2, MID.tx);
  assert.equal(fill.style.background, hexOf(fillColour));
  // The handle's far edge 8 before the end of the fill: rows 92 to 88 from
  // the start, so 108 to 112 from the top.
  const handle = slider.querySelector(".at-slider-handle");
  assert.equal(handle.style.top, "108px");
  assert.equal(handle.style.height, "4px");
  assert.equal(handle.style.background, hexOf(readable(fillColour)));
  const icon = slider.querySelector("ha-icon");
  assert.equal(icon.style.top, "164px");
  assert.equal(icon.style.color, hexOf(readable(fillColour)));
  assert.equal(slider.getAttribute("aria-orientation"), "vertical");
});

test("v2 slider: a track of colours with its mark", () => {
  const tracked = {
    id: 2,
    t: "slider",
    r: [16, 16, 200, 40],
    value: { s: 1 },
    min: 0,
    max: 100,
    track: ["#FF0000", "#00FF00", "#0000FF"],
  };
  const slider = drawCard2({ w: [tracked] }, { 1: 50 }).card.querySelector(".at-slider");
  const track = slider.querySelector(".at-slider-track");
  assert.match(track.style.background, /^linear-gradient\(to right, #FF0000 0px, #FF0000 7px, #FF0000 7px, #00FF00 100px, #00FF00 100px, #0000FF 193px, #0000FF 193px, #0000FF 200px\)$/);
  assert.equal(track.style.height, "14px");
  const mark = slider.querySelector(".at-slider-mark");
  assert.equal(mark.hidden, false);
  assert.equal(mark.style.left, "89px");
  assert.equal(mark.style.width, "22px");
  assert.equal(mark.style.background, "#FFFFFF");
  assert.equal(mark.style.borderColor, "#15181D");
  // No fill on a track.
  assert.equal(slider.querySelector(".at-slider-fill"), null);
});

test("v2 slider: nv keeps it at full strength with its track only; rate moves it", () => {
  const nv = { id: 2, t: "slider", r: [16, 16, 200, 40], value: { s: 1 }, min: 0, max: 100, nv: 1, change: { p: 1 } };
  const empty = drawCard2({ w: [nv] }, { 1: null }, { interactive: true }).card.querySelector(".at-slider");
  assert.ok(!empty.classList.contains("at-none"));
  assert.equal(empty.querySelector(".at-slider-fill").hidden, true);
  assert.equal(empty.querySelector(".at-slider-knob").hidden, true);
  assert.equal(empty.tabIndex, 0);
  const moving = { id: 2, t: "slider", r: [16, 16, 200, 40], value: { s: 1 }, rate: { s: 2 }, min: 0, max: 100 };
  const ages = { 1: 5 };
  const drawn = drawCard2({ w: [moving] }, { 1: 10, 2: 2 }, { state: { age: (slot) => ages[slot] ?? 0 } });
  const slider = drawn.card.querySelector(".at-slider");
  assert.equal(slider.getAttribute("aria-valuenow"), "20");
  // Clamped to max.
  ages[1] = 1000;
  drawn.renderer.update(drawn.state({ 1: 10, 2: 2 }, { age: (slot) => ages[slot] ?? 0 }));
  assert.equal(slider.getAttribute("aria-valuenow"), "100");
  // A rate without a value counts as 0.
  drawn.renderer.update(drawn.state({ 1: 10, 2: null }, { age: (slot) => ages[slot] ?? 0 }));
  assert.equal(slider.getAttribute("aria-valuenow"), "10");
});

test("v2 thermostat: c, mark and bs", () => {
  const thermo = {
    id: 2,
    t: "thermostat",
    r: [16, 16, 200, 200],
    value: { s: 1 },
    mark: { s: 2 },
    min: 10,
    max: 30,
    step: 0.5,
    c: "#FF453A",
    bs: 48,
    change: { p: 1 },
  };
  const { card } = drawCard2({ w: [thermo] }, { 1: 21, 2: 20 });
  assert.equal(card.querySelector(".at-arc-value").style.stroke, hexOf(legible(0xff453a, MID.card, MID.tx)));
  const dot = card.querySelector(".at-arc-mark");
  // 20 is halfway: 270 degrees, straight up.
  assert.ok(Math.abs(Number(dot.getAttribute("cx")) - 100) < 1e-9);
  assert.ok(Math.abs(Number(dot.getAttribute("cy")) - 28) < 1e-9);
  // Arc width 14.28 * 200 / 200; diameter max(6, w - 4).
  assert.ok(Math.abs(Number(dot.getAttribute("r")) - (200 / 14 - 4) / 2) < 1e-9);
  assert.equal(dot.style.fill, "#E8EAED");
  assert.equal(card.querySelector(".plus").style.width, "48px");
  // The mark shows while the value has none, and not outside min to max.
  const off = drawCard2({ w: [thermo] }, { 1: null, 2: 20 }).card;
  assert.equal(off.querySelector(".at-arc-mark").style.display, "");
  const outside = drawCard2({ w: [thermo] }, { 1: 21, 2: 40 }).card;
  assert.equal(outside.querySelector(".at-arc-mark").style.display, "none");
});

test("v2 chart: c, steps and the bar of now", () => {
  const steps = { id: 2, t: "chart", r: [16, 16, 100, 50], value: { s: 1 }, kind: "line", st: 1, c: "#30D158" };
  const card = drawCard2({ w: [steps] }, { 1: [1, 3, 2] }).card;
  const rects = card.querySelectorAll(".at-chart-step");
  assert.equal(rects.length, 4);
  assert.equal(rects[0].style.fill, hexOf(legible(0x30d158, MID.card, MID.tx)));
  assert.equal(rects[0].getAttribute("height"), "3");
  const bars = { id: 2, t: "chart", r: [16, 16, 100, 50], value: { s: 1 }, kind: "bars", mark: { s: 2 } };
  const marked = drawCard2({ w: [bars] }, { 1: [1, 2, 3, 4], 2: 1.4 }).card;
  const drawn = marked.querySelectorAll(".at-chart-bar").map((bar) => bar.getAttribute("class").split(" ").at(-1));
  assert.deepEqual(drawn, ["at-bar-acc2", "at-bar-acc", "at-bar-card2", "at-bar-card2"]);
  const past = drawCard2({ w: [bars] }, { 1: [1, 2, 3, 4], 2: 4 }).card;
  assert.ok(past.querySelectorAll(".at-chart-bar").every((bar) => bar.getAttribute("class").endsWith("at-bar-acc2")));
});

test("v2 image: badge and bare looks", () => {
  const image = { id: 2, t: "image", r: [16, 16, 120, 80], value: { s: 1 }, look: 1 };
  const plain = drawCard2({ on: { s: 2 }, w: [image] }, { 1: "mdi:fan", 2: 0 }).card.querySelector(".at-image");
  assert.ok(plain.classList.contains("badge"));
  assert.equal(plain.style.left, "36px");
  assert.equal(plain.style.width, "80px");
  assert.equal(plain.style.background, "#232833");
  assert.equal(plain.style.color, "#9AA0A8");
  assert.equal(plain.querySelector("ha-icon").style.getPropertyValue("--mdc-icon-size"), "48px");
  const filled = drawCard2({ on: { s: 2 }, w: [image] }, { 1: "mdi:fan", 2: 1 }).card.querySelector(".at-image");
  const colours = cardColours(MID, true, 0, null);
  const wash = mix(colours.FI, colours.background, 80);
  assert.equal(filled.style.background, hexOf(wash));
  assert.equal(filled.style.color, hexOf(legible(colours.FI, wash, colours.text)));
  const bare = drawCard2({ w: [{ ...image, look: 2 }] }, { 1: "mdi:fan" }).card.querySelector(".at-image");
  assert.ok(bare.classList.contains("bare"));
  assert.equal(bare.querySelector("ha-icon").style.getPropertyValue("--mdc-icon-size"), "72px");
});

test("v2 choice: cells, the selected option, swatches, dots and taps", () => {
  const choice = { id: 2, t: "choice", r: [16, 16, 200, 40], value: { s: 1 }, texts: ["A", "B", "C"], change: { p: 0 } };
  const { card, sent } = drawCard2({ w: [choice] }, { 1: 1 }, { interactive: true });
  const cells = card.querySelectorAll(".at-choice-cell");
  assert.equal(cells.length, 3);
  assert.deepEqual([cells[1].style.left, cells[1].style.width], ["69px", "61px"]);
  assert.equal(cells[1].getAttribute("aria-pressed"), "true");
  assert.equal(cells[1].querySelector(".at-choice-face").style.background, "#F5B547");
  assert.equal(cells[0].querySelector(".at-choice-face").style.background, "#232833");
  for (const listener of cells[2].listeners.get("click")) listener();
  assert.deepEqual(sent, [["change", 2, 2, true]]);
  // A fraction selects nothing.
  const none = drawCard2({ w: [choice] }, { 1: 1.5 }).card.querySelectorAll(".at-choice-cell");
  assert.ok(none.every((cell) => cell.getAttribute("aria-pressed") === "false"));
  const swatches = drawCard2({ w: [{ ...choice, texts: undefined, cols: ["#FF0000", "#00FF00"], look: 1 }] }, { 1: 0 }).card;
  const faces = swatches.querySelectorAll(".at-choice-face");
  assert.equal(faces[0].style.background, "#FF0000");
  assert.equal(faces[0].style.boxShadow, "inset 0 0 0 3px #E8EAED");
  assert.ok(faces[0].classList.contains("dot"));
  assert.equal(faces[0].style.width, "40px");
  // Two rows of cells below 1 px high are not drawn.
  const tiny = drawCard2({ w: [{ ...choice, r: [16, 16, 200, 8], rows: 2 }] }).card;
  assert.ok(tiny.querySelector(".at-choice").classList.contains("at-hidden"));
});

test("v2 vis: a widget with vis 0 or no value is not drawn", () => {
  const label = { id: 2, t: "label", r: [16, 16, 100, 20], text: "Hi", vis: { s: 1 } };
  const { card, renderer, state } = drawCard2({ w: [label] }, { 1: 1 });
  const element = card.querySelector(".at-label");
  assert.ok(!element.classList.contains("at-hidden"));
  renderer.update(state({ 1: 0 }));
  assert.ok(element.classList.contains("at-hidden"));
  renderer.update(state({ 1: null }));
  assert.ok(element.classList.contains("at-hidden"));
  assert.match(rule(".at-hidden"), /display: none/);
});

function drawLayout2(pageIndex) {
  const uninstall = installFakeDom();
  try {
    const host = document.createElement("div");
    const layout = {
      v: 2,
      screen: [1280, 800],
      theme: { ...midnight },
      nav: [
        { page: "home", icon: "mdi:home" },
        { page: "light", icon: "mdi:lightbulb" },
        { page: "more", icon: "mdi:cog" },
      ],
      pages: [
        { id: "home", w: [{ t: "heading", r: [120, 20, 300, 32], text: "Rooms", icon: "mdi:sofa", c: "#FF453A" }] },
        { id: "light", sub: 1, w: [] },
        { id: "more", theme: { wall: "#F2F2F7", card: "#FFFFFF" }, w: [] },
      ],
    };
    renderPage(host, layout, pageIndex, { values: {}, errors: {} }, { sx: 1, sy: 1 });
    return host;
  } finally {
    uninstall();
  }
}

test("v2 page: detail pages, the back entry, page themes and heading colour", () => {
  const home = drawLayout2(0);
  const buttons = home.querySelectorAll(".at-nav-button");
  // The detail page's entry is not drawn; the others keep their places.
  assert.equal(buttons.length, 2);
  assert.equal(buttons[1].style.top, "160px");
  assert.equal(home.querySelector(".at-heading").style.color, hexOf(legible(0xff453a, MID.wall, MID.tx)));
  const detail = drawLayout2(1);
  const [back] = detail.querySelectorAll(".at-nav-button");
  assert.equal(detail.querySelectorAll(".at-nav-button").length, 1);
  assert.ok(back.classList.contains("back"));
  assert.ok(back.classList.contains("active"));
  assert.equal(back.querySelector("ha-icon").icon, "mdi:arrow-left");
  assert.equal(back.style.top, "16px");
  const themed = drawLayout2(2);
  assert.equal(themed.querySelector(".at-page").style.getPropertyValue("--at-wall"), "#F2F2F7");
  assert.equal(themed.querySelector(".at-nav").style.getPropertyValue("--at-bg"), "#FFFFFF");
});

// Last in the file: it loads the tablet's font, which stays loaded for the
// rest of this module, and the tests above expect it not to be.
test("a fitted line is drawn in whole tablet pixels, no wider than its box", async () => {
  const uninstall = installFakeDom();
  const fontFaceBefore = globalThis.FontFace;
  try {
    // A browser's own width for each character is fractional (10.4 px), so
    // 15 of them drawn freely would be 156 px, wider than the 152 px box.
    globalThis.FontFace = class {
      load() {
        return Promise.resolve();
      }
    };
    document.fonts = { add() {} };
    const createElement = document.createElement;
    document.createElement = (tag) =>
      tag === "canvas"
        ? { getContext: () => ({ font: "", measureText: () => ({ width: 10.4 }) }) }
        : createElement(tag);
    loadTabletFont();
    await new Promise((resolve) => setImmediate(resolve));

    const layout = {
      v: 1,
      screen: [1280, 800],
      theme: midnight,
      nav: [{ page: "home", title: "Home" }],
      pages: [
        {
          id: "home",
          title: "Home",
          w: [
            {
              id: 1,
              t: "card",
              r: [100, 40, 376, 248],
              w: [{ id: 2, t: "label", r: [116, 100, 152, 28], text: "Front door: locked" }],
            },
          ],
        },
      ],
    };
    for (const scale of [1, 0.5]) {
      const host = document.createElement("div");
      renderPage(host, layout, 0, { values: {}, errors: {} }, { tablet: true, sx: scale, sy: scale });
      const text = host.querySelector(".at-label").querySelector(".at-text");
      assert.ok(text.classList.contains("at-fitted"), `scale ${scale}`);
      const glyphs = text.children;
      assert.ok(glyphs.every((glyph) => glyph.classList.contains("at-ch")), `scale ${scale}`);
      assert.equal(glyphs.map((glyph) => glyph.textContent).join(""), "Front door: lo…");
      const widths = glyphs.map((glyph) => Number.parseFloat(glyph.style.width) / scale);
      assert.ok(widths.every((width) => width === 10), `scale ${scale}: ${widths}`);
      const drawn = widths.reduce((sum, width) => sum + width, 0);
      assert.ok(drawn <= 152, `scale ${scale}: ${drawn} px in a 152 px box`);
    }
    assert.match(rule(".at-tablet .at-ch"), /display: inline-block;/);
    assert.match(rule(".at-tablet .at-fitted"), /font-kerning: none;/);
  } finally {
    globalThis.FontFace = fontFaceBefore;
    uninstall();
  }
});

// The tablet's font, measured: widths that grow with the size, with
// fractions as Montserrat's have. Each size gets its own canvas.
const FAKE_EM = (ch) => (/[0-9]/.test(ch) ? 0.66 : ch === "." ? 0.27 : ch === "…" ? 0.8 : 0.6);

function measuringCanvas(createElement) {
  return (tag) => {
    if (tag !== "canvas") {
      return createElement(tag);
    }
    const context = {
      font: "",
      measureText: (ch) => ({ width: FAKE_EM(ch) * Number.parseFloat(/([\d.]+)px/.exec(context.font)[1]) }),
    };
    return { getContext: () => context };
  };
}

async function withMeasuredFont(run) {
  const uninstall = installFakeDom();
  const fontFaceBefore = globalThis.FontFace;
  try {
    globalThis.FontFace = class {
      load() {
        return Promise.resolve();
      }
    };
    document.fonts = { add() {} };
    document.createElement = measuringCanvas(document.createElement);
    // A no-op when an earlier test loaded the font already.
    loadTabletFont();
    await new Promise((resolve) => setImmediate(resolve));
    await run();
  } finally {
    globalThis.FontFace = fontFaceBefore;
    uninstall();
  }
}

function oneCardLayout(widgets) {
  return {
    v: 1,
    screen: [1280, 800],
    theme: midnight,
    nav: [{ page: "home", title: "Home" }],
    pages: [{ id: "home", title: "Home", w: [{ id: 1, t: "card", r: [100, 20, 400, 340], w: widgets }] }],
  };
}

test("the tablet preview draws a thermostat value at the size the tablet steps down to", async () => {
  await withMeasuredFont(async () => {
    // [dial width, height, reading, first size, tablet size, what the
    // tablet draws]: the energy gauge on grids 9x6, 6x3 and 8x5. The first
    // size is the largest not above thermostatFit; while the value drawn at
    // a size is wider than the box, the tablet takes the next smaller one
    // (48, 34, 20, 18, 14). Only 14 px is cut, always with "…".
    const cases = [
      [248, 268, 4040, 48, 34, "4040"], // 128 px at 48 in a 125 px box, 88 at 34
      [248, 268, 8000, 48, 34, "8000"],
      [248, 268, 21.5, 48, 48, "21.5"], // 109 px at 48
      [76, 76, 40000, 14, 14, "400…"], // 45 px at 14 in a 41 px box: cut
      [204, 204, 40000, 34, 20, "40000"], // 110 px at 34 in a 105 px box, 65 at 20
    ];
    const advanceFor = (px) => (ch) => FAKE_EM(ch) * px;
    for (const [w, h, reading, first, px, shown] of cases) {
      const side = Math.min(w, h);
      // The engine's thermostat_text_width: (int) of 0.8 * inner diameter.
      const box = Math.trunc((0.8 * 2 * (72 - Math.max(8, side / 14) / 2) * side) / 200);
      assert.equal(tabletThermostatTextWidth(side), box);
      assert.equal(tabletThermostatSize(thermostatText(reading), side), first);
      assert.equal(tabletThermostatSize(thermostatText(reading), side, advanceFor), px);
      const dial = { id: 2, t: "thermostat", r: [116, 30, w, h], value: { s: 1 }, min: 0, max: 50000, step: 1 };
      for (const scale of [1, 0.5]) {
        const label = `${reading} in ${w}x${h} at scale ${scale}`;
        const host = document.createElement("div");
        renderPage(host, oneCardLayout([dial]), 0, { values: { 1: reading }, errors: {} }, { tablet: true, sx: scale, sy: scale });
        const value = host.querySelector(".at-thermostat-value");
        assert.equal(value.style.fontSize, `${px * scale}px`, label);
        const span = value.querySelector(".at-thermostat-text");
        assert.ok(span.classList.contains("at-fitted"), label);
        assert.equal(span.textContent, shown, label);
        assert.ok(!span.textContent.includes("..."), label);
        // Each character at the tablet's whole-pixel width, the line no
        // wider than the tablet's box.
        const widths = span.children.map((glyph) => Number.parseFloat(glyph.style.width) / scale);
        assert.ok(widths.every(Number.isInteger), `${label}: ${widths}`);
        assert.ok(widths.reduce((sum, width) => sum + width, 0) <= box, `${label}: ${widths} in ${box}`);
      }
      // The editor still fits the whole value.
      const host = document.createElement("div");
      renderPage(host, oneCardLayout([dial]), 0, { values: { 1: reading }, errors: {} }, { sx: 1, sy: 1 });
      const span = host.querySelector(".at-thermostat-text");
      assert.equal(span.textContent, thermostatText(reading));
      assert.ok(!span.classList.contains("at-fitted"));
    }
  });
});

test("a thermostat value drawn before the tablet's font is there gets its size again once it is", async () => {
  // A fresh copy of the renderer, whose font has not started loading.
  const fresh = await import("../../custom_components/apollo_tab/frontend/render.js?late-font");
  const uninstall = installFakeDom();
  const fontFaceBefore = globalThis.FontFace;
  let arrive;
  try {
    globalThis.FontFace = class {
      load() {
        return new Promise((resolve) => {
          arrive = resolve;
        });
      }
    };
    document.fonts = { add() {} };
    document.createElement = measuringCanvas(document.createElement);
    fresh.loadTabletFont();
    const dial = { id: 2, t: "thermostat", r: [116, 30, 248, 268], value: { s: 1 }, min: 0, max: 50000, step: 1 };
    const host = document.createElement("div");
    fresh.renderPage(host, oneCardLayout([dial]), 0, { values: { 1: 4040 }, errors: {} }, { tablet: true, sx: 1, sy: 1 });
    const value = host.querySelector(".at-thermostat-value");
    const span = value.querySelector(".at-thermostat-text");
    // Nothing to measure with yet: the first pick, the whole value.
    assert.equal(value.style.fontSize, "48px");
    assert.equal(span.textContent, "4040");
    assert.ok(!span.classList.contains("at-fitted"));
    arrive();
    await new Promise((resolve) => setImmediate(resolve));
    // Measured: 128 px at 48 does not fit the 125 px box, so 34, whole.
    assert.equal(value.style.fontSize, "34px");
    assert.ok(span.classList.contains("at-fitted"));
    assert.equal(span.textContent, "4040");
  } finally {
    globalThis.FontFace = fontFaceBefore;
    uninstall();
  }
});

test("the tablet preview's box for a missing character fills the room the tablet gives it", async () => {
  await withMeasuredFont(async () => {
    // A label at 18 px: the tablet's line is 22 px high and gives a missing
    // character 22 / 2 + 2 = 13 px, all of it inside LVGL's 1 px border.
    const label = { id: 2, t: "label", r: [116, 60, 300, 28], text: "Küche 中" };
    for (const scale of [1, 0.5]) {
      const host = document.createElement("div");
      renderPage(host, oneCardLayout([label]), 0, { values: {}, errors: {} }, { tablet: true, sx: scale, sy: scale });
      const [box] = host.querySelectorAll(".at-nobox");
      assert.ok(box, `scale ${scale}`);
      assert.equal(box.style.width, `${13 * scale}px`, `scale ${scale}`);
      assert.equal(box.style.height, `${22 * scale}px`, `scale ${scale}`);
      assert.ok(!box.style.marginRight, `scale ${scale}: ${box.style.marginRight}`);
    }
  });
});

// A page of tablet text: a heading, a label and a thermostat value.
function textLayout() {
  const label = { id: 2, t: "label", r: [116, 100, 152, 28], text: "Front door" };
  const dial = { id: 3, t: "thermostat", r: [116, 130, 120, 120], value: { s: 1 }, min: 5, max: 30, step: 1 };
  const layout = oneCardLayout([label, dial]);
  layout.pages[0].w.unshift({ id: 9, t: "heading", r: [100, 0, 300, 30], text: "Lights" });
  return layout;
}

// Counts the texts the renderer keeps to draw again once the tablet's font
// is there: its waiting list is a Map from the drawn element to a function.
async function countWaitingTexts(run) {
  const set = Map.prototype.set;
  let waiting = 0;
  Map.prototype.set = function countingSet(key, value) {
    if (key instanceof FakeElement && typeof value === "function") {
      waiting += 1;
    }
    return set.call(this, key, value);
  };
  try {
    await run(() => waiting);
  } finally {
    Map.prototype.set = set;
  }
}

// A font that never comes keeps no text waiting. Otherwise every draw of a
// tablet preview would keep its texts, for as long as the page stays open.
for (const [name, how] of [
  ["cannot be fetched", "rejects"],
  ["cannot be made", "throws"],
]) {
  test(`after the tablet's font ${name}, texts no longer wait for it`, async () => {
    // A fresh copy of the renderer, whose font has not started loading.
    const fresh = await import(`../../custom_components/apollo_tab/frontend/render.js?font-${how}`);
    const uninstall = installFakeDom();
    const fontFaceBefore = globalThis.FontFace;
    let faces = 0;
    let fail;
    try {
      globalThis.FontFace = class {
        constructor() {
          faces += 1;
          if (how === "throws") {
            throw new Error("no fonts here");
          }
        }

        load() {
          return new Promise((_resolve, reject) => {
            fail = reject;
          });
        }
      };
      document.fonts = { add() {} };
      const drawPage = () =>
        fresh.renderPage(document.createElement("div"), textLayout(), 0, { values: { 1: 21 }, errors: {} }, { tablet: true, sx: 1, sy: 1 });

      await countWaitingTexts(async (waiting) => {
        drawPage();
        if (how === "rejects") {
          // Still loading: the heading, the label and the value wait.
          assert.ok(waiting() >= 3, `${waiting()} texts wait while the font loads`);
          fail(new Error("404"));
        }
        await new Promise((resolve) => setImmediate(resolve));
        const before = waiting();
        for (let i = 0; i < 5; i += 1) {
          drawPage();
        }
        assert.equal(waiting() - before, 0);
      });
      // The font is not asked for again on every draw.
      assert.equal(faces, 1);
    } finally {
      globalThis.FontFace = fontFaceBefore;
      uninstall();
    }
  });
}

// A picture drawn smaller than the tablet keeps its proportions: corners,
// edges, outlines and the graph's line scale with it (--at-f is the scale;
// at 1 every value is what it was). Rules added later are held too.
test("the renderer's styles scale radius, border and outline with the picture", () => {
  assert.match(rule(".at-card"), /border: calc\(var\(--at-bw, 0px\) \* var\(--at-f, 1\)\) solid/);
  assert.match(rule(".at-card"), /border-radius: calc\(var\(--at-r, 16px\) \* var\(--at-f, 1\)\);/);
  assert.match(rule(".at-card-body"), /inset: calc\(-1 \* var\(--at-bw, 0px\) \* var\(--at-f, 1\)\);/);
  // The last rule of a selector is its own (the first may be a shared one).
  const own = (selector) => {
    const start = rendererStyles.lastIndexOf(`\n${selector} {`);
    return rendererStyles.slice(start, rendererStyles.indexOf("}", start));
  };
  for (const selector of [".at-button", ".at-image", ".at-nav-button"]) {
    assert.match(own(selector), /border-radius: calc\(var\(--at-r2(, 10px)?\) \* var\(--at-f, 1\)\);/, selector);
  }
  assert.match(rule(".at-button.busy,\n.at-switch.busy"), /outline: calc\(2px \* var\(--at-f, 1\)\) solid/);
  assert.match(rule(".at-chart-line"), /stroke-width: calc\(3px \* var\(--at-f, 1\)\);/);
  assert.match(rule(".at-nobox"), /border: calc\(1px \* var\(--at-f, 1\)\) solid/);
  // Every length of an edge, corner, outline or line in the whole string,
  // except none, a pill and a circle.
  const lengths = /^\s*(border(?:-[a-z]+)*|outline(?:-width)?|outline|stroke-width|inset|box-shadow):([^;]*);/gm;
  for (const [, property, value] of rendererStyles.matchAll(lengths)) {
    if (!/\dpx|var\(--at-(bw|r|r2)\b/.test(value)) continue;
    if (/^ ?(0|999px|50%|inherit)$/.test(value)) continue;
    assert.match(value, /var\(--at-f/, `${property}:${value} does not scale with the picture`);
  }
  // Paddings, gaps, margins, places and sizes scale too.
  const spacing =
    /^\s*(padding(?:-[a-z]+)*|margin(?:-[a-z]+)*|(?:row-|column-)?gap|top|left|right|bottom|width|height|font-size|outline-offset):([^;]*);/gm;
  let seen = 0;
  for (const [, property, value] of rendererStyles.matchAll(spacing)) {
    if (!/\dpx/.test(value)) continue;
    seen += 1;
    assert.match(value, /var\(--at-f/, `${property}:${value} does not scale with the picture`);
  }
  assert.ok(seen >= 8, `only ${seen} spacing lengths found`);
});

// Home Assistant's glyph is an inline box inside ha-icon. A flex host keeps
// it off a text line, so a small icon is not pushed down out of its badge.
test("an icon's glyph sits in the icon's own box", () => {
  const icons = rule(".at-card ha-icon,\n.at-page ha-icon,\n.at-heading ha-icon,\n.at-nav ha-icon");
  assert.match(icons, /display: inline-flex;/);
  assert.match(icons, /align-items: center;/);
  assert.match(icons, /justify-content: center;/);
});

test("every tablet picture is left to right", () => {
  const base = rule(".at-card,\n.at-page,\n.at-heading,\n.at-nav");
  for (const declaration of [
    "direction: ltr;", "unicode-bidi: isolate;", "text-size-adjust: 100%;", "-webkit-text-size-adjust: 100%;",
    // Grey-scale edges, as thin as the tablet's text (design review, round 2).
    "-webkit-font-smoothing: antialiased;", "-moz-osx-font-smoothing: grayscale;",
  ]) {
    assert.ok(base.includes(declaration), declaration);
  }
});
