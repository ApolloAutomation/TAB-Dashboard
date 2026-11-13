import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  cardTokens,
  loadTabletFont,
  renderPage,
  tabletImageIconSize,
  tabletThermostatSize,
  tabletThermostatTextWidth,
  thermostatFit,
  thermostatText,
} from "../../custom_components/apollo_tab/frontend/render.js";
import { rendererStyles } from "../../custom_components/apollo_tab/frontend/styles.js";
import { installFakeDom } from "./fake-dom.mjs";

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
  assert.match(rule(".at-card-body"), /position: absolute;\s+inset: calc\(-1 \* var\(--at-bw, 0px\)\);/);
  assert.match(rule(".at-card"), /border: var\(--at-bw, 0px\) solid/);
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
