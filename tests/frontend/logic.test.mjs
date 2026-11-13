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
