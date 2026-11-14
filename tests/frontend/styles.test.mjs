// The panel's visual system: tokens, type, radii, states and logical sides
// (build plan, package 1). The tablet's own drawing (rendererStyles,
// canvasStyles, cardStyles, previewStyles) is checked in render.test.mjs.
import test from "node:test";
import assert from "node:assert";
import * as styles from "../../custom_components/apollo_tab/frontend/styles.js";
import { accentGrounds } from "../../custom_components/apollo_tab/frontend/logic.js";

const PANEL = ["panelStyles", "designerStyles", "formStyles", "pickerStyles", "confirmStyles", "editorStyles"];

// Every rule of a style string: its selector, the at-rules around it, and
// its declarations as [property, value].
function rules(css) {
  const text = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const found = [];
  const stack = [];
  let start = 0;
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] === "{") {
      stack.push(text.slice(start, index).trim());
      start = index + 1;
    } else if (text[index] === "}") {
      const prelude = stack.pop();
      if (!prelude.startsWith("@")) {
        const declarations = text
          .slice(start, index)
          .split(";")
          .map((part) => part.trim())
          .filter(Boolean)
          .map((part) => {
            const colon = part.indexOf(":");
            return [part.slice(0, colon).trim(), part.slice(colon + 1).trim().replace(/\s+/g, " ")];
          });
        found.push({ selector: prelude.replace(/\s+/g, " "), at: stack.filter((entry) => entry.startsWith("@")), declarations });
      }
      start = index + 1;
    }
  }
  assert.equal(stack.length, 0, "unbalanced braces");
  return found;
}

const panelRules = () => PANEL.flatMap((name) => rules(styles[name]).map((rule) => ({ ...rule, sheet: name })));

// The parts of a value outside brackets, split at spaces.
function parts(value) {
  const out = [];
  let depth = 0;
  let current = "";
  for (const char of value) {
    if (char === "(") depth += 1;
    if (char === ")") depth -= 1;
    if (char === " " && depth === 0) {
      if (current) out.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  if (current) out.push(current);
  return out;
}

test("the panel's styles use no app-header colour and no fixed blue", () => {
  for (const name of PANEL) {
    assert.doesNotMatch(styles[name], /--app-header-/, name);
    assert.doesNotMatch(styles[name], /#1565c0/i, name);
  }
});

test("every font size in the panel's styles is a token", () => {
  for (const rule of panelRules()) {
    for (const [property, value] of rule.declarations) {
      if (property !== "font-size") continue;
      const coarse = rule.at.some((at) => /pointer: coarse/.test(at));
      const ok = /^var\(--tab-fs-[a-z]+\)$/.test(value) || value === "inherit" || (coarse && value === "16px");
      assert.ok(ok, `${rule.sheet} ${rule.selector}: font-size ${value}`);
    }
  }
});

test("every radius in the panel's styles is a token", () => {
  for (const rule of panelRules()) {
    for (const [property, value] of rule.declarations) {
      if (!/radius$/.test(property)) continue;
      for (const part of parts(value)) {
        const ok =
          /^var\(--tab-r-[a-z]+\)$/.test(part) ||
          ["50%", "inherit", "0"].includes(part) ||
          (/(^|[ ,])\.hit\b/.test(rule.selector) && /^calc\(.*--at-r/.test(part));
        assert.ok(ok, `${rule.sheet} ${rule.selector}: ${property} ${value}`);
      }
    }
  }
});

test("buttons, tabs, rows and tiles have hover and pressed rules", () => {
  const selectors = panelRules().map((rule) => rule.selector);
  const has = (target, state) =>
    selectors.some((selector) =>
      selector.split(",").some((one) => {
        const plain = one.trim().replace(/:where\(([^)]*(?:\([^)]*\))?[^)]*)\)/g, "$1");
        return plain.includes(target) && plain.includes(state);
      }),
    );
  for (const target of ["button", ".tab", ".list-row", ".entity-option", ".tile", ".icon-grid button"]) {
    assert.ok(has(target, ":hover"), `${target} has no hover rule`);
    assert.ok(has(target, ":active"), `${target} has no pressed rule`);
  }
  // A layer over the background, so the state shows on every fill.
  assert.match(styles.panelStyles, /background-image: linear-gradient\(var\(--tab-hover\), var\(--tab-hover\)\);/);
  assert.match(styles.panelStyles, /background-image: linear-gradient\(var\(--tab-press\), var\(--tab-press\)\);/);
});

const TOKENS = [
  "--tab-bg", "--tab-surface", "--tab-text", "--tab-text-2", "--tab-line", "--tab-bar", "--tab-bar-text",
  "--tab-stage", "--tab-field-line", "--tab-accent", "--tab-accent-soft", "--tab-tonal", "--tab-hover",
  "--tab-press", "--tab-disabled", "--tab-ok", "--tab-warn", "--tab-err", "--tab-info", "--tab-ok-ink",
  "--tab-warn-ink", "--tab-err-ink", "--tab-info-ink", "--tab-bezel", "--tab-toast", "--tab-toast-text",
  "--tab-accent-fill", "--tab-accent-ink", "--tab-accent-text", "--tab-ring", "--tab-knob",
  "--tab-fs-title", "--tab-fs-head", "--tab-fs-body", "--tab-fs-small",
  "--tab-lh-title", "--tab-lh-head", "--tab-lh-body", "--tab-lh-small",
  "--tab-s1", "--tab-s2", "--tab-s3", "--tab-s4", "--tab-s5", "--tab-s6",
  "--tab-r-xs", "--tab-r-s", "--tab-r-m", "--tab-r-pill", "--tab-r-dialog", "--tab-r-bezel", "--tab-r-screen",
  "--tab-shadow", "--tab-shadow-dialog", "--tab-control", "--tab-control-s",
];

test("the token block names every token, and only three hosts declare it", () => {
  const declared = [...styles.tokens.matchAll(/(--tab-[a-z0-9-]+):/g)].map((match) => match[1]);
  assert.deepEqual([...declared].sort(), [...TOKENS].sort());
  assert.match(styles.tokens, /--tab-control: 40px;/);
  assert.match(styles.tokens, /--tab-control-s: 36px;/);

  const hostRule = (name) => rules(styles[name]).filter((rule) => rule.selector === ":host" && !rule.at.length);
  for (const name of ["panelStyles", "confirmStyles", "editorStyles"]) {
    const [host] = hostRule(name);
    assert.ok(host, `${name} has no :host rule`);
    const names = host.declarations.map(([property]) => property);
    for (const token of TOKENS) {
      assert.ok(names.includes(token), `${name} :host does not declare ${token}`);
    }
  }
  // The editor inherits the tokens from the panel; a block of its own would
  // undo what applyAccent set on the panel.
  for (const host of hostRule("designerStyles")) {
    assert.ok(!host.declarations.some(([property]) => property.startsWith("--tab-")), "designerStyles :host declares tokens");
  }
  for (const name of ["formStyles", "pickerStyles"]) {
    assert.ok(!rules(styles[name]).some((rule) => rule.selector.includes(":host")), `${name} has a :host rule`);
  }

  // 44 px controls: on every touch screen, in a panel under 900 px wide,
  // and in a confirm dialog on a window under 900 px wide. Nowhere else.
  const big = panelRules()
    .filter((rule) => rule.declarations.some(([property, value]) => /^--tab-control(-s)?$/.test(property) && value === "44px"))
    .map((rule) => `${rule.sheet} ${rule.at.join(" ")} ${rule.selector}`.replace(/\s+/g, " ").trim());
  assert.deepEqual(big.sort(), [
    "confirmStyles @media (max-width: 899px) :host",
    "confirmStyles @media (pointer: coarse) :host",
    "editorStyles @media (pointer: coarse) :host",
    "panelStyles :host(.compact)",
    "panelStyles @media (pointer: coarse) :host",
  ]);
  for (const rule of panelRules()) {
    for (const [property, value] of rule.declarations) {
      if (/^--tab-control(-s)?$/.test(property)) {
        assert.ok(rule.selector.startsWith(":host"), `${rule.sheet} ${rule.selector} sets ${property}: ${value}`);
      }
    }
  }

  // The shares the script uses for accentGrounds are the ones of the CSS.
  const share = (pattern) => Number(pattern.exec(styles.tokens + styles.panelStyles)[1]) / 100;
  const soft = share(/--tab-accent-soft: color-mix\(in srgb, var\(--tab-accent\) (\d+)%, var\(--tab-surface\)\)/);
  const tonal = share(/--tab-tonal: color-mix\(in srgb, var\(--tab-text\) (\d+)%, transparent\)/);
  const notice = share(/background: color-mix\(in srgb, var\(--tone\) (\d+)%, var\(--tab-surface\)\)/);
  const mix = (a, b, amount) => a.map((value, index) => Math.floor(value + (b[index] - value) * amount + 0.5));
  const white = [255, 255, 255];
  const accent = [0, 154, 199];
  const text = [20, 20, 20];
  const tone = [219, 68, 55];
  const grounds = accentGrounds({ surface: white, page: white, stage: white, text, accent, tones: { err: tone } });
  assert.deepEqual(grounds, [white, white, white, mix(white, accent, soft), mix(white, text, tonal), mix(white, tone, notice)]);
});

const BAR_TOKENS = [
  "--tab-surface", "--tab-text", "--tab-text-2", "--tab-line", "--tab-field-line", "--tab-tonal", "--tab-hover",
  "--tab-press", "--tab-disabled", "--tab-accent-soft", "--tab-ok-ink", "--tab-warn-ink", "--tab-err-ink", "--tab-info-ink",
];

test("everything in a bar takes the bar's own tokens", () => {
  const [bar] = rules(styles.barTokens);
  assert.equal(bar.selector, ".panel-header, .ed-header");
  const set = bar.declarations.map(([property]) => property).filter((property) => property.startsWith("--"));
  assert.deepEqual(set.sort(), [...BAR_TOKENS].sort());
  for (const [property, value] of bar.declarations) {
    if (property.startsWith("--") && property !== "--tab-surface" && property !== "--tab-text") {
      assert.match(value, /var\(--tab-bar(-text)?\)/, `${property} is not made from the bar's colours`);
    }
  }
  for (const name of ["panelStyles", "designerStyles"]) {
    assert.ok(styles[name].includes(styles.barTokens), `${name} does not hold the bar tokens`);
  }
  // No bar takes Home Assistant's app header colours.
  for (const name of ["panelStyles", "designerStyles"]) {
    const header = rules(styles[name]).find((rule) => rule.selector === ".panel-header" || rule.selector === ".ed-header");
    assert.ok(header.declarations.some(([property, value]) => property === "background" && value === "var(--tab-bar)"));
  }
});

test("an element that holds a tablet picture resets the line height", () => {
  for (const name of ["panelStyles", "designerStyles"]) {
    const reset = rules(styles[name]).find((rule) => rule.selector === ".page-host, .tile-preview, .tablet-pic");
    assert.ok(reset, `${name} has no reset`);
    assert.deepEqual(reset.declarations, [["line-height", "normal"]]);
  }
  assert.doesNotMatch(styles.rendererStyles, /line-height/);
  assert.doesNotMatch(styles.canvasStyles, /line-height/);
});

test("the panel's styles use logical properties", () => {
  for (const name of PANEL) {
    for (const pattern of [
      /margin-left/, /margin-right/, /padding-left/, /padding-right/, /border-left/, /border-right/,
      /text-align: left/, /text-align: right/,
    ]) {
      assert.doesNotMatch(styles[name], pattern, `${name}: ${pattern}`);
    }
  }
});

test("motion stops for reduced motion, and a chosen thing shows in forced colours", () => {
  // The panel, the editor (which also holds the form and picker styles) and
  // the confirm dialog each stop every transition and animation.
  for (const name of ["panelStyles", "designerStyles", "confirmStyles"]) {
    const still = rules(styles[name]).find(
      (rule) => rule.at.some((at) => /prefers-reduced-motion: reduce/.test(at)) && rule.selector.startsWith("*"),
    );
    assert.ok(still, `${name} does not stop motion`);
    assert.deepEqual(still.declarations, [["transition", "none !important"], ["animation", "none !important"]]);
    const forced = rules(styles[name]).find((rule) => rule.at.some((at) => /forced-colors: active/.test(at)));
    assert.ok(forced, `${name} has no forced-colours rule`);
    for (const chosen of ['.tab[aria-selected="true"]', '.list-row[aria-current="true"]',
      '.entity-option[aria-selected="true"]', '.icon-grid button[aria-pressed="true"]']) {
      assert.ok(forced.selector.includes(chosen), `${chosen} in forced colours`);
    }
    assert.ok(forced.declarations.some(([property, value]) => property === "outline" && value.includes("Highlight")));
  }
  for (const name of ["formStyles", "pickerStyles", "editorStyles"]) {
    assert.doesNotMatch(styles[name], /transition|animation/, `${name} moves outside the reduced-motion rule`);
  }
});

// The declarations of the first rule whose selector list holds `selector`.
function declarationsOf(sheet, selector) {
  const rule = rules(styles[sheet]).find(
    (entry) => entry.at.length === 0 && entry.selector.split(",").map((one) => one.trim()).includes(selector),
  );
  assert.ok(rule, `${sheet}: no rule for ${selector}`);
  return Object.fromEntries(rule.declarations);
}

test("chips, the segmented control and notices take their tone's colours", () => {
  for (const sheet of ["panelStyles", "designerStyles"]) {
    assert.equal(declarationsOf(sheet, ".chip")["--tone-ink"], "var(--tab-text-2)");
    assert.equal(declarationsOf(sheet, ".chip::before").background, "var(--tone-ink)");
    for (const tone of ["ok", "warn", "err", "info"]) {
      assert.equal(declarationsOf(sheet, `.chip[data-tone="${tone}"]`)["--tone-ink"], `var(--tab-${tone}-ink)`);
    }
    const segmented = declarationsOf(sheet, ".segmented");
    assert.equal(segmented["min-height"], "var(--tab-control-s)");
    assert.equal(segmented["border-radius"], "var(--tab-r-pill)");
    const chosen = declarationsOf(sheet, ".segmented label:has(input:checked)");
    assert.equal(chosen["background-color"], "var(--tab-accent-soft)");
    // A mark in the accent is drawn in the accent made readable (polish
    // decision 2), never the raw accent.
    assert.equal(chosen["box-shadow"], "inset 0 0 0 2px var(--tab-accent-text)");
    const notice = declarationsOf(sheet, ".notice");
    assert.equal(notice["--tone"], "var(--tab-info)");
    assert.equal(notice.background, "color-mix(in srgb, var(--tone) 12%, var(--tab-surface))");
    for (const tone of ["ok", "warn", "err"]) {
      const marked = declarationsOf(sheet, `.notice[data-tone="${tone}"]`);
      assert.equal(marked["--tone"], `var(--tab-${tone})`);
      assert.equal(marked["--tone-ink"], `var(--tab-${tone}-ink)`);
    }
  }
});

test("a slider draws a 4 px track and a 16 px knob in the accent", () => {
  for (const sheet of ["panelStyles", "designerStyles"]) {
    assert.equal(declarationsOf(sheet, 'input[type="range"]').appearance, "none");
    for (const track of ['input[type="range"]::-webkit-slider-runnable-track', 'input[type="range"]::-moz-range-track']) {
      const style = declarationsOf(sheet, track);
      assert.equal(style.height, "4px", track);
      assert.match(style.background, /var\(--tab-field-line\)/, track);
    }
    for (const knob of ['input[type="range"]::-webkit-slider-thumb', 'input[type="range"]::-moz-range-thumb']) {
      const style = declarationsOf(sheet, knob);
      assert.equal(style.width, "16px", knob);
      assert.equal(style.height, "16px", knob);
      assert.equal(style.background, "var(--tab-accent-fill)", knob);
    }
    assert.equal(declarationsOf(sheet, 'input[type="range"]::-moz-range-progress').background, "var(--tab-accent-fill)");
  }
});

test("a chosen row keeps its 2 px edge under the pointer", () => {
  for (const rule of panelRules()) {
    if (!rule.selector.includes(":hover")) continue;
    const shadow = rule.declarations.find(([property]) => property === "box-shadow");
    if (!shadow) continue;
    for (const one of rule.selector.split(",").map((entry) => entry.trim())) {
      if (one.startsWith(".list-row")) assert.match(one, /:not\(\[aria-current="true"\]\)/, `${rule.sheet} ${one}`);
      if (one.startsWith(".entity-option")) assert.match(one, /:not\(\[aria-selected="true"\]\)/, `${rule.sheet} ${one}`);
    }
  }
});

// Polish decisions 1 and 2: a focused field shows a 2 px edge and no ring
// outside it, and every mark in the accent (a chosen tab, row, option or
// icon, the chosen part of a segmented control, a field's focus edge) is
// the accent made readable, never the raw accent.
test("a chosen thing and a focused field are marked in the readable accent", () => {
  for (const sheet of ["panelStyles", "designerStyles", "confirmStyles"]) {
    const field = rules(styles[sheet]).find((rule) => !rule.at.length && rule.selector.includes("select:focus") &&
      !rule.selector.includes("focus-visible"));
    assert.ok(field, `${sheet}: no focus rule for fields`);
    const look = Object.fromEntries(field.declarations);
    assert.equal(look.outline, "none", sheet);
    assert.equal(look["border-color"], "var(--tab-accent-text)", sheet);
    assert.equal(look["box-shadow"], "inset 0 0 0 1px var(--tab-accent-text)", sheet);
    // The ring for buttons and links leaves fields out.
    const ring = rules(styles[sheet]).find((rule) => !rule.at.length && rule.selector.startsWith("button:focus-visible"));
    assert.ok(ring, `${sheet}: no focus ring`);
    assert.doesNotMatch(ring.selector, /(^|, )(select|textarea|input):focus-visible/, sheet);
  }
  for (const rule of panelRules()) {
    const marks = /aria-selected="true"|aria-current="true"|aria-pressed="true"|input:checked|:focus\b/;
    if (!marks.test(rule.selector) || /^\.hit|forced-colors/.test(rule.selector + rule.at.join(" "))) continue;
    for (const [property, value] of rule.declarations) {
      if (["box-shadow", "border-color", "outline", "outline-color"].includes(property)) {
        assert.doesNotMatch(value, /var\(--tab-accent\)/, `${rule.sheet} ${rule.selector}: ${property} ${value}`);
      }
    }
  }
});
