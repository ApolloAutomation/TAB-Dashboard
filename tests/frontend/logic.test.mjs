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
