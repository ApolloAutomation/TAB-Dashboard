import test from "node:test";
import assert from "node:assert";
import * as logic from "../../custom_components/apollo_tab/frontend/logic.js";

test("isHex accepts six digit colours", () => {
  assert.equal(logic.isHex("#A1b2C3"), true);
});

test("isHex rejects alpha and css functions", () => {
  assert.equal(logic.isHex("#AABBCCDD"), false);
  assert.equal(logic.isHex("rgb(1,2,3)"), false);
});

test("isIcon validates material icon names", () => {
  assert.equal(logic.isIcon("mdi:lightbulb-on"), true);
  assert.equal(logic.isIcon("mdi:Bad"), false);
});

test("isSafeImagePath rejects protocol-relative and absolute URLs", () => {
  assert.equal(logic.isSafeImagePath("//host/image"), false);
  assert.equal(logic.isSafeImagePath("https://host/image"), false);
  assert.equal(logic.isSafeImagePath("/local/image.png"), true);
});

test("format replaces known variables", () => {
  assert.equal(logic.format("Hello {name} {other}", { name: "Sam" }), "Hello Sam {other}");
});

test("resolveBound reads slots by string key", () => {
  assert.equal(logic.resolveBound({ s: 2 }, { "2": "on" }), "on");
  assert.equal(logic.resolveBound("fixed", {}), "fixed");
});

test("isOn accepts on/true/yes/1", () => {
  for (const value of ["on", "TRUE", "Yes", "1"]) {
    assert.equal(logic.isOn(value), true);
  }
  assert.equal(logic.isOn(2), true);
  assert.equal(logic.isOn("off"), false);
});

test("toNumber accepts finite numeric strings", () => {
  assert.equal(logic.toNumber("2.5", 0), 2.5);
  assert.equal(logic.toNumber("x", 7), 7);
});

test("clampStep snaps and clamps", () => {
  assert.equal(logic.clampStep(11, 0, 10, 3), 9);
  assert.equal(logic.clampStep(-2, 0, 10, 3), 0);
  assert.equal(logic.clampStep(10, 0, 10, 4), 10);
});

test("fraction returns a bounded ratio", () => {
  assert.equal(logic.fraction(5, 0, 10), 0.5);
  assert.equal(logic.fraction(20, 0, 10), 1);
  assert.equal(logic.fraction(1, 2, 2), 0);
});

test("mapRect scales x and y separately", () => {
  assert.deepEqual(logic.mapRect([1, 2, 3, 4], 2, 3), [2, 6, 6, 12]);
});

test("linePoints handles zero one and many values", () => {
  assert.deepEqual(logic.linePoints([], 100, 50, 5), []);
  assert.deepEqual(logic.linePoints([4], 100, 50, 5), [[5, 25], [95, 25]]);
  const points = logic.linePoints([0, 10], 100, 50, 5);
  assert.deepEqual(points, [[5, 45], [95, 5]]);
});

test("barRects creates bottom-rising bars", () => {
  assert.deepEqual(logic.barRects([], 100, 50, 4), []);
  const bars = logic.barRects([0, 10], 100, 50, 4);
  assert.equal(bars.length, 2);
  assert.equal(bars[1].h, 50);
  assert.equal(bars[1].y, 0);
});

test("arcPath sets the large arc and clockwise sweep", () => {
  const path = logic.arcPath(0, 0, 10, 0, 270);
  assert.match(path, /A 10 10 0 1 1/);
});

test("aliasTag replaces the namespace separator", () => {
  assert.equal(logic.aliasTag("apollo/light-tile"), "apollo-tab-el-apollo-light-tile");
});

test("dashboardFromPath finds the first path part", () => {
  assert.equal(logic.dashboardFromPath("/tab-1/home"), "tab-1");
  assert.equal(logic.dashboardFromPath("/"), null);
});

test("subscriptionKey ignores key order and unrelated keys", () => {
  const first = logic.subscriptionKey({
    component: "a/b",
    params: { b: 2, a: 1 },
    ignored: true,
  }, "tab-1");
  const second = logic.subscriptionKey({
    ignored: false,
    params: { a: 1, b: 2 },
    component: "a/b",
  }, "tab-1");
  assert.equal(first, second);
});

test("formToStyle drops empty parts", () => {
  assert.equal(logic.formToStyle({
    theme: "",
    use_color: false,
    gradient: "vertical",
    transparency: 0,
    use_accent: false,
  }), undefined);
});

test("formToStyle keeps transparency a whole number from 0 to 100", () => {
  const saved = (transparency) => logic.formToStyle({ transparency })?.transparency;

  assert.equal(saved(150), 100);
  assert.equal(saved(12.5), 13);
  assert.equal(saved("40"), 40);
  assert.equal(saved(-5), undefined);
  assert.equal(saved(0.2), undefined);
  assert.equal(saved(Number.NaN), undefined);
  assert.equal(logic.styleToForm({ transparency: 150 }).transparency, 100);
  assert.equal(logic.styleToForm({ transparency: -5 }).transparency, 0);
});

test("styleToForm and formToStyle round trip", () => {
  const style = {
    theme: "warm",
    color: "#203040",
    gradient: { to: "#101820", direction: "vertical" },
    transparency: 20,
    accent: "#FFB300",
  };
  assert.deepEqual(logic.formToStyle(logic.styleToForm(style)), style);
});

test("cleanConfig removes empty params and style", () => {
  assert.deepEqual(logic.cleanConfig({
    type: "custom:apollo-tab-card",
    component: "a/b",
    params: {},
    style: {},
    title: "",
    missing: undefined,
  }), {
    type: "custom:apollo-tab-card",
    component: "a/b",
  });
});

const idle = { phase: "idle", value: undefined, until: 0 };

test("feedbackReduce act optimistic with value becomes pending", () => {
  assert.deepEqual(logic.feedbackReduce(idle, {
    type: "act", policy: "optimistic", value: true, now: 10,
  }), { phase: "pending", value: true, until: 5010 });
});

test("feedbackReduce act optimistic without value pulses", () => {
  assert.deepEqual(logic.feedbackReduce(idle, {
    type: "act", policy: "optimistic", now: 10,
  }), { phase: "pulse", value: undefined, until: 610 });
});

test("feedbackReduce act pulse pulses", () => {
  assert.equal(logic.feedbackReduce(idle, {
    type: "act", policy: "pulse", now: 10,
  }).phase, "pulse");
});

test("feedbackReduce act progress waits for thirty seconds", () => {
  assert.deepEqual(logic.feedbackReduce(idle, {
    type: "act", policy: "progress", value: 4, now: 10,
  }), { phase: "pending", value: 4, until: 30010 });
});

test("feedbackReduce act confirm becomes busy", () => {
  assert.equal(logic.feedbackReduce(idle, {
    type: "act", policy: "confirm", now: 10,
  }).phase, "busy");
});

test("feedbackReduce ok clears only busy", () => {
  const busy = { phase: "busy", value: undefined, until: 10 };
  assert.deepEqual(logic.feedbackReduce(busy, { type: "ok", now: 2 }), idle);
  const pending = { phase: "pending", value: 2, until: 10 };
  assert.deepEqual(logic.feedbackReduce(pending, { type: "ok", now: 2 }), pending);
});

test("feedbackReduce fail becomes error", () => {
  assert.deepEqual(logic.feedbackReduce(idle, { type: "fail", now: 5 }), {
    phase: "error", value: undefined, until: 3005,
  });
});

test("feedbackReduce value clears pending", () => {
  const pending = { phase: "pending", value: 2, until: 10 };
  assert.deepEqual(logic.feedbackReduce(pending, { type: "value", now: 2 }), idle);
});

test("feedbackReduce tick expires feedback", () => {
  const pulse = { phase: "pulse", value: undefined, until: 10 };
  assert.deepEqual(logic.feedbackReduce(pulse, { type: "tick", now: 10 }), idle);
  assert.deepEqual(logic.feedbackReduce(pulse, { type: "tick", now: 9 }), pulse);
});

test("warningText falls back to the code", () => {
  assert.equal(logic.warningText({ code: "missing", detail: "" }, {}), "missing");
  assert.equal(
    logic.warningText({ code: "bad", detail: "x" }, { "warn.bad": "Problem {detail}" }),
    "Problem x",
  );
});

test("warningPlace reports the page and the card", () => {
  assert.equal(logic.warningPlace({ view: 0, section: 1, card: 2 }), "Page 1, card 3");
  assert.equal(logic.warningPlace({ view: 1, section: 0, card: null }), "Page 2");
  assert.equal(logic.warningPlace({ view: null, section: null, card: null }), "");
});

test("tabletText draws a box for each character the tablet font lacks", () => {
  const box = logic.TABLET_MISSING_GLYPH;
  assert.equal(logic.tabletText("Café 21.5°C – €3 “ok” …"), "Café 21.5°C – €3 “ok” …");
  assert.equal(logic.tabletText("Łódź Œuvre"), "Łódź Œuvre");
  assert.equal(logic.tabletText("Ψ"), box);
  assert.equal(logic.tabletText("Привет"), box.repeat(6));
  assert.equal(logic.tabletText("日本"), box.repeat(2));
  // One box per code point, also for an emoji outside the BMP.
  assert.equal(logic.tabletText("a😀b"), `a${box}b`);
  assert.equal(logic.tabletText(""), "");
  assert.equal(logic.tabletText(null), "");
  assert.equal(logic.tabletText(42), "42");
});

test("the tablet preview's glyphs are the contract's fonts.text_glyphs", async () => {
  const fs = await import("node:fs");
  const url = new URL("../../custom_components/apollo_tab/contract/contract.json", import.meta.url);
  const contract = JSON.parse(fs.readFileSync(url, "utf8"));
  assert.deepEqual(logic.TABLET_TEXT_GLYPHS, contract.fonts.text_glyphs);
});

test("tabletFit cuts a line where the tablet cuts it", () => {
  // Every character 10.4 px wide in the browser: the tablet counts 10 each.
  const advance = () => 10.4;
  // 15 characters are 150 px on the tablet and fit a 152 px box; the browser's
  // own sum (156 px) would have cut the line.
  assert.equal(logic.tabletFit("Front door: loc", 152, 18, advance), "Front door: loc");
  // Too wide: the longest start that fits with the "…" (also 10 px).
  assert.equal(logic.tabletFit("Front door: locked", 152, 18, advance), "Front door: lo…");
  assert.equal(logic.tabletFit("Front door: locked", 180, 18, advance), "Front door: locked");
  // Exactly full is not cut.
  assert.equal(logic.tabletFit("abcde", 50, 18, advance), "abcde");
  assert.equal(logic.tabletFit("abcdef", 50, 18, advance), "abcd…");
  // Spaces before the "…" go.
  assert.equal(logic.tabletFit("abc   defgh", 70, 18, advance), "abc…");
  // Nothing fits: only the "…".
  assert.equal(logic.tabletFit("abcdef", 5, 18, advance), "…");
  // No width: no cut. Control characters are spaces.
  assert.equal(logic.tabletFit("a\tb", 0, 18, advance), "a b");
  assert.equal(logic.tabletFit("", 100, 18, advance), "");
  assert.equal(logic.tabletFit(null, 100, 18, advance), "");
});

test("tabletFit ends a cut line with three dots in a font without the ellipsis", () => {
  // The thermostat's 48 px digits font has no "…": the tablet's set_text
  // ends the line with "..." and counts all three dots.
  const widths = { 4: 32.2, 0: 31.6, ".": 12.9 };
  const advance = (ch) => widths[ch];
  assert.equal(logic.TABLET_DIGITS_ELLIPSIS, "...");
  assert.equal(logic.TABLET_ELLIPSIS, "…");
  // 4040 is 128 px in a 125 px box: "40" (64) and "..." (39) fit, "404..." not.
  assert.equal(logic.tabletFit("4040", 125, 48, advance, "..."), "40...");
  assert.equal(logic.tabletFit("4040", 128, 48, advance, "..."), "4040");
  // The dots count as three characters: 64 + 39 = 103 fits 103, not 102.
  assert.equal(logic.tabletFit("40404", 103, 48, advance, "..."), "40...");
  assert.equal(logic.tabletFit("40404", 102, 48, advance, "..."), "4...");
});

test("a fitted line is drawn no wider than its box", () => {
  // Browser widths with fractions, as Montserrat has; the tablet rounds each.
  const widths = { " ": 4.9, ":": 4.3, "\u2026": 13.6, l: 4.6, o: 10.9, c: 9.7, k: 9.4, e: 10.2, d: 11.3 };
  const advance = (ch) => widths[ch] ?? 10.6;
  for (const [text, box] of [
    ["Front door: locked", 152],
    ["Sam: not_home", 144],
    ["Küche Κουζίνα", 100],
    ["abc", 300],
  ]) {
    for (let width = 20; width <= box; width += 1) {
      const line = logic.tabletFit(text, width, 18, advance);
      const placed = logic.tabletCharWidths(line, 18, advance);
      assert.equal(placed.map(([ch]) => ch).join(""), line);
      for (const [, w] of placed) {
        assert.ok(Number.isInteger(w), `${text} at ${width}: a width of ${w}`);
      }
      const drawn = placed.reduce((sum, [, w]) => sum + w, 0);
      assert.ok(drawn <= width, `${JSON.stringify(line)} is ${drawn} px in a ${width} px box`);
    }
  }
  // The browser's own sum would be wider than the box: the reason for it.
  const line = logic.tabletFit("Front door: locked", 152, 18, () => 10.4);
  assert.equal(line, "Front door: lo\u2026");
  assert.equal(logic.tabletCharWidths(line, 18, () => 10.4).reduce((sum, [, w]) => sum + w, 0), 150);
  assert.ok(line.length * 10.4 > 152);
  assert.deepEqual(logic.tabletCharWidths(logic.TABLET_MISSING_GLYPH, 18, () => 1), [[logic.TABLET_MISSING_GLYPH, 13]]);
  assert.deepEqual(logic.tabletCharWidths(null, 18, () => 1), []);
});

test("tabletFit gives a missing character the tablet's box width", () => {
  // At 18 px a line is 22 px high: the box is 11 wide and takes 13.
  assert.equal(logic.tabletLineHeight(18), 22);
  assert.equal(logic.tabletBoxAdvance(18), 13);
  assert.equal(logic.tabletBoxAdvance(34), 22);
  const box = logic.TABLET_MISSING_GLYPH;
  const asked = [];
  const advance = (ch) => {
    asked.push(ch);
    return 10;
  };
  // Two boxes (26 px) and "ab" (20 px) fit 46 px, not 45.
  assert.equal(logic.tabletFit("aΩb😀", 46, 18, advance), `a${box}b${box}`);
  assert.equal(logic.tabletFit("aΩb😀", 45, 18, advance), `a${box}b…`);
  // The box is never measured in the browser's font.
  assert.ok(!asked.includes(box) && !asked.includes("Ω"));
});

// The accent made readable (build plan 1.8). The themes are the harness
// page's: Home Assistant's default light and dark colours.
const hex = (text) => [1, 3, 5].map((start) => Number.parseInt(text.slice(start, start + 2), 16));
const toHex = (rgb) => `#${rgb.map((value) => value.toString(16).padStart(2, "0")).join("")}`;
const ratio = (a, b) => {
  const light = (rgb) => {
    const [r, g, bl] = rgb.map((value) => {
      const c = value / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [hi, lo] = [light(a), light(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const TONES = { ok: hex("#43a047"), warn: hex("#ffa600"), err: hex("#db4437"), info: hex("#039be5") };
const THEMES = {
  light: { surface: hex("#ffffff"), page: hex("#fafafa"), stage: hex("#e5e5e5"), text: hex("#141414") },
  dark: { surface: hex("#1c1c1c"), page: hex("#111111"), stage: hex("#282828"), text: hex("#e1e1e1") },
};
const grounds = (theme, accent) => logic.accentGrounds({ ...THEMES[theme], accent: hex(accent), tones: TONES });

test("parseCssColour reads rgb and color(srgb), clamps, and gives null for what it cannot read", () => {
  assert.deepEqual(logic.parseCssColour("rgb(0, 154, 199)"), [0, 154, 199]);
  assert.deepEqual(logic.parseCssColour("rgba(0, 154, 199, 1)"), [0, 154, 199]);
  assert.deepEqual(logic.parseCssColour("color(srgb 0 0.6 0.78)"), [0, 153, 199]);
  // A wide-gamut theme colour can come out a little past 0 or 1.
  assert.deepEqual(logic.parseCssColour("color(srgb 1.02 -0.01 0.5)"), [255, 0, 128]);
  assert.equal(logic.parseCssColour("rgba(0, 154, 199, 0.5)"), null);
  assert.equal(logic.parseCssColour("color(srgb 0 0.6 0.78 / 0.5)"), null);
  assert.equal(logic.parseCssColour("oklch(0.6 0.12 220)"), null);
  assert.equal(logic.parseCssColour("#009ac7"), null);
  assert.equal(logic.parseCssColour(""), null);
  assert.equal(logic.parseCssColour(undefined), null);
});

test("accentInk darkens a mid accent until white has 4.5 to 1", () => {
  const blue = logic.accentInk(hex("#009ac7"));
  assert.equal(toHex(blue.fill), "#007b9f");
  assert.equal(toHex(blue.ink), "#ffffff");
  assert.ok(ratio(blue.fill, blue.ink) >= 4.5);
  assert.equal(toHex(logic.accentInk(hex("#03a9f4")).fill), "#027ab0");
  const dark = logic.accentInk(hex("#1565c0"));
  assert.equal(toHex(dark.fill), "#1565c0");
  assert.equal(toHex(dark.ink), "#ffffff");
});

test("accentInk keeps a light accent and gives it dark ink", () => {
  for (const colour of ["#f5b547", "#ffeb3b"]) {
    const { fill, ink } = logic.accentInk(hex(colour));
    assert.equal(toHex(fill), colour);
    assert.equal(toHex(ink), "#111111");
    assert.ok(ratio(fill, ink) >= 4.5);
  }
});

test("accentText moves toward black on a light surface and toward white on a dark one", () => {
  const cases = [
    ["#009ac7", "light", "#006f8f"],
    ["#009ac7", "dark", "#14a2cb"],
    ["#f5b547", "light", "#7f5e25"],
    ["#f5b547", "dark", "#f5b547"],
    ["#1565c0", "light", "#1565c0"],
    ["#1565c0", "dark", "#699cd7"],
  ];
  for (const [accent, theme, expected] of cases) {
    assert.equal(toHex(logic.accentText(hex(accent), grounds(theme, accent))), expected, `${accent} in ${theme}`);
  }
  // The focus ring, on white.
  assert.equal(toHex(logic.accentText(hex("#009ac7"), [hex("#ffffff")])), "#007b9f");
  assert.equal(toHex(logic.accentText(hex("#f5b547"), [hex("#ffffff")])), "#936d2b");
});

test("the accent as text has 4.5 to 1 on every ground", () => {
  for (const accent of ["#009ac7", "#f5b547", "#1565c0", "#03a9f4", "#4caf50", "#e91e63"]) {
    for (const theme of ["light", "dark"]) {
      const list = grounds(theme, accent);
      // The surface, the page, the stage, accent-soft, tonal and four notices.
      assert.equal(list.length, 9);
      const text = logic.accentText(hex(accent), list);
      for (const ground of list) {
        assert.ok(ratio(text, ground) >= 4.5, `${accent} in ${theme}: ${toHex(text)} on ${toHex(ground)}`);
      }
    }
  }
});

test("a switch that is off has a knob lighter than its track in both themes", () => {
  // Home Assistant's default surfaces and text colours (tests/harness/index.html).
  const themes = [
    [hex("#ffffff"), hex("#141414")],
    [hex("#1c1c1c"), hex("#e1e1e1")],
  ];
  assert.equal(toHex(logic.switchKnob(...themes[0])), "#ffffff");
  assert.equal(toHex(logic.switchKnob(...themes[1])), "#e1e1e1");
  for (const [surface, text] of themes) {
    // The track is the text at 48 % over the surface (--tab-field-line).
    const track = surface.map((value, index) => Math.round(value + (text[index] - value) * 0.48));
    const knob = logic.switchKnob(surface, text);
    const light = (rgb) => rgb.reduce((sum, value) => sum + value, 0);
    assert.ok(light(knob) > light(track), `${toHex(knob)} on ${toHex(track)}`);
  }
});

test("layoutBand picks wide, medium, compact and short", () => {
  const cases = [
    [1280, 800, "wide"],
    [1160, 800, "wide"],
    [1159, 800, "medium"],
    [900, 800, "medium"],
    [899, 800, "compact"],
    [844, 390, "short"],
    [599, 390, "compact"],
    [1280, 559, "short"],
  ];
  for (const [width, height, band] of cases) {
    assert.equal(logic.layoutBand(width, height), band, `${width} x ${height}`);
  }
});

test("fitStage gives the table of the build plan", () => {
  // [availW, availH, picture width]; compact passes Infinity as the height.
  const rows = [
    [879.2, 584, 879],
    [796, 584, 796],
    [972, 600, 960],
    [1452, 864, 1280],
    [2092, 1224, 1280],
    [879.2, 504, 806],
    [942.8, 552, 883],
    [772, 584, 772],
    [848, 600, 848],
    [784, Infinity, 784],
    [354, Infinity, 354],
    [284, Infinity, 284],
    [470.4, 258, 412],
    [324, 268, 324],
  ];
  for (const [w, h, width] of rows) {
    assert.equal(logic.fitStage(w, h), width, `${w} x ${h}`);
  }
  // With the one line of page notices, 44 px less height.
  const withNotice = [
    [879.2, 584, 864],
    [942.8, 552, 812],
    [879.2, 504, 736],
    [972, 600, 889],
    [796, 584, 796],
    [772, 584, 772],
    [470.4, 258, 342],
  ];
  for (const [w, h, width] of withNotice) {
    assert.equal(logic.fitStage(w, h - 44), width, `${w} x ${h} with a notice`);
  }
  assert.equal(logic.fitStage(-5, 100), 0);
});

test("drawerShift keeps the card clear of the drawer and never moves it past the padding", () => {
  // Clear of the drawer already: no move.
  assert.equal(logic.drawerShift(100, 400, 704, 16), 0);
  assert.equal(logic.drawerShift(100, 688, 704, 16), 0);
  // Just under it: moved by what it needs, 16 px clear.
  assert.equal(logic.drawerShift(500, 800, 704, 16), 112);
  // Wider than the room beside the drawer: only until the left edge is at
  // the padding.
  assert.equal(logic.drawerShift(100, 900, 704, 16), 84);
  // Already at the padding: no move left.
  assert.equal(logic.drawerShift(16, 900, 704, 16), 0);
  assert.equal(logic.drawerShift(10, 900, 704, 16), 0);
});

test("shellHeight follows the keyboard and ignores a pinch zoom", () => {
  assert.equal(logic.shellHeight({ innerHeight: 800, visual: null, top: 56 }), 744);
  // The keyboard is up: the visible part is 500 high.
  assert.equal(logic.shellHeight({ innerHeight: 800, visual: { height: 500, offsetTop: 0, scale: 1 }, top: 0 }), 500);
  assert.equal(logic.shellHeight({ innerHeight: 800, visual: { height: 500, offsetTop: 40, scale: 1 }, top: 20 }), 520);
  // Pinch zoom at 2: the window's own height.
  assert.equal(logic.shellHeight({ innerHeight: 800, visual: { height: 400, offsetTop: 120, scale: 2 }, top: 10 }), 790);
  assert.equal(logic.shellHeight({ innerHeight: 800, visual: { height: 640.6, offsetTop: 0, scale: 1.005 }, top: 0.4 }), 640);
  assert.equal(logic.shellHeight({ innerHeight: 300, visual: null, top: 400 }), 0);
});
