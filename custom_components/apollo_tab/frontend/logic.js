export const HEX_RE = /^#[0-9A-Fa-f]{6}$/;
export const ICON_RE = /^mdi:[a-z0-9-]+$/;

export function isHex(value) {
  return typeof value === "string" && HEX_RE.test(value);
}

export function isIcon(value) {
  return typeof value === "string" && ICON_RE.test(value);
}

export function isSafeImagePath(value) {
  if (
    typeof value !== "string" ||
    value.length < 1 ||
    value.length > 2048 ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\")
  ) {
    return false;
  }
  for (const character of value) {
    if (character.codePointAt(0) < 0x20) {
      return false;
    }
  }
  return true;
}

export function format(text, vars = {}) {
  return String(text).replace(/\{([^{}]+)\}/g, (match, name) =>
    Object.hasOwn(vars, name) ? String(vars[name]) : match,
  );
}

// Words that live in one string each, under this prefix. Every other
// sentence names one by the rest of its key in braces: the word for turning
// a new tablet on (tablets.word.*) is written once and put in everywhere.
const WORD_PREFIX = "tablets.word.";

// The strings with those words put in. Other braces, such as {tablet},
// stay for format(). A new object; `strings` stays as it was.
export function fillWords(strings) {
  const source = strings && typeof strings === "object" ? strings : {};
  const words = new Map();
  for (const [key, value] of Object.entries(source)) {
    if (key.startsWith(WORD_PREFIX) && typeof value === "string") {
      words.set(key.slice(WORD_PREFIX.length), value);
    }
  }
  const filled = {};
  for (const [key, value] of Object.entries(source)) {
    filled[key] =
      typeof value === "string" ? value.replace(/\{([a-z_]+)\}/g, (match, name) => words.get(name) ?? match) : value;
  }
  return filled;
}

export function resolveBound(bound, values = {}) {
  if (
    bound &&
    typeof bound === "object" &&
    !Array.isArray(bound) &&
    Object.hasOwn(bound, "s")
  ) {
    return values[String(bound.s)];
  }
  return bound;
}

export function isOn(value) {
  if (value === true) {
    return true;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) && value !== 0;
  }
  if (typeof value === "string") {
    return ["on", "true", "yes", "1"].includes(value.toLowerCase());
  }
  return false;
}

export function toNumber(value, fallback) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const number = Number(value);
    if (Number.isFinite(number)) {
      return number;
    }
  }
  return fallback;
}

export function clampStep(value, min, max, step) {
  const low = toNumber(min, 0);
  const high = toNumber(max, low);
  let result = Math.min(high, Math.max(low, toNumber(value, low)));
  const increment = toNumber(step, 0);

  if (increment > 0) {
    result = low + Math.round((result - low) / increment) * increment;
    result = Math.min(high, Math.max(low, result));
  }

  return Math.round(result * 1_000_000) / 1_000_000;
}

export function fraction(value, min, max) {
  const low = toNumber(min, 0);
  const high = toNumber(max, low);
  if (high <= low) {
    return 0;
  }
  return Math.min(1, Math.max(0, (toNumber(value, low) - low) / (high - low)));
}

// The characters the tablet's text sizes hold: contract.json
// fonts.text_glyphs, as [first, last] code points. The tablet draws an empty
// box for any other character, so the tablet preview does too.
export const TABLET_TEXT_GLYPHS = [
  [0x20, 0x7e],
  [0xa0, 0x17f],
  [0x2013, 0x2014],
  [0x2018, 0x2019],
  [0x201c, 0x201d],
  [0x2022, 0x2022],
  [0x2026, 0x2026],
  [0x20ac, 0x20ac],
];
export const TABLET_MISSING_GLYPH = "\u25a1";

// The text as the tablet draws it: each character it has no glyph for
// becomes a box. Control characters are left alone.
export function tabletText(text) {
  let out = "";
  for (const ch of String(text ?? "")) {
    const cp = ch.codePointAt(0);
    const known = cp < 0x20 || TABLET_TEXT_GLYPHS.some(([lo, hi]) => cp >= lo && cp <= hi);
    out += known ? ch : TABLET_MISSING_GLYPH;
  }
  return out;
}

// The tablet's line height for a text size: Montserrat's ascender (968) and
// descender (251) of 1000 units.
export function tabletLineHeight(px) {
  return Math.round(px * 1.219);
}

// The room the tablet gives a character it has no glyph for: a box half a
// line wide and a line high, then 2 px.
export function tabletBoxAdvance(px) {
  return Math.floor(tabletLineHeight(px) / 2) + 2;
}

// The whole-pixel width the tablet gives one character of a fitted line.
function tabletCharWidth(ch, px, advance) {
  return ch === TABLET_MISSING_GLYPH ? tabletBoxAdvance(px) : Math.round(advance(ch));
}

// Where the tablet puts each character of a line tabletFit gave: [char,
// whole-pixel width] in tablet pixels. Drawing each character in a box of
// that width places it where the tablet does, so the line is never wider
// than the sum tabletFit checked; a browser's own fractional widths and
// kerning can make it a few pixels wider.
export function tabletCharWidths(line, px, advance) {
  return [...String(line ?? "")].map((ch) => [ch, tabletCharWidth(ch, px, advance)]);
}

// One line of text as the tablet draws it in a box `width` px wide at text
// size `px`: boxes for characters it lacks, spaces for control characters,
// and when the line is too wide, the longest start that fits together with
// the ellipsis. The tablet adds up whole-pixel widths, one per character,
// so this does too: advance(ch) is the width of one character the tablet
// has, and it is rounded here. A browser's own cut adds fractions and can
// end one character earlier or later. The ellipsis is "\u2026", or "..." in a
// font without that character, as the tablet's set_text picks it. Every
// text size has "\u2026"; the thermostat's 48 px digits font (only
// 0123456789.,-) does not, but a thermostat value is never cut at 48 px: it
// steps down a size first (contract 4.7, render.js tabletThermostatSize).
export const TABLET_ELLIPSIS = "\u2026";
export const TABLET_DIGITS_ELLIPSIS = "...";

export function tabletFit(text, width, px, advance, ellipsis = TABLET_ELLIPSIS) {
  const chars = [...tabletText(text)].map((ch) => (ch.codePointAt(0) < 0x20 ? " " : ch));
  const widthOf = (ch) => tabletCharWidth(ch, px, advance);
  if (!(width > 0)) {
    return chars.join("");
  }
  let total = 0;
  for (const ch of chars) {
    total += widthOf(ch);
  }
  if (total <= width) {
    return chars.join("");
  }
  let dots = 0;
  for (const ch of ellipsis) {
    dots += widthOf(ch);
  }
  let keep = 0;
  let used = 0;
  while (keep < chars.length && used + widthOf(chars[keep]) + dots <= width) {
    used += widthOf(chars[keep]);
    keep += 1;
  }
  while (keep > 0 && chars[keep - 1] === " ") {
    keep -= 1;
  }
  return `${chars.slice(0, keep).join("")}${ellipsis}`;
}

export function mapRect(rect, sx, sy) {
  return [
    rect[0] * sx,
    rect[1] * sy,
    rect[2] * sx,
    rect[3] * sy,
  ];
}

export function linePoints(values, width, height, pad) {
  if (!Array.isArray(values) || values.length === 0) {
    return [];
  }

  const numbers = values.map((value) => toNumber(value, 0));
  const low = Math.min(...numbers);
  const high = Math.max(...numbers);
  const middle = height / 2;

  if (numbers.length === 1) {
    return [
      [pad, middle],
      [width - pad, middle],
    ];
  }

  return numbers.map((value, index) => {
    const x = pad + (index / (numbers.length - 1)) * (width - pad * 2);
    const y =
      high === low
        ? middle
        : height - pad - ((value - low) / (high - low)) * (height - pad * 2);
    return [x, y];
  });
}

export function barRects(values, width, height, gap) {
  if (!Array.isArray(values) || values.length === 0) {
    return [];
  }

  const numbers = values.map((value) => toNumber(value, 0));
  const low = Math.min(0, ...numbers);
  const high = Math.max(...numbers);
  const span = high - low || 1;
  const count = numbers.length;
  const barWidth = Math.max(0, (width - gap * (count - 1)) / count);

  return numbers.map((value, index) => {
    const scaled = ((value - low) / span) * height;
    const barHeight = Math.min(height, Math.max(2, scaled));
    return {
      x: index * (barWidth + gap),
      y: height - barHeight,
      w: barWidth,
      h: barHeight,
    };
  });
}

export function arcPath(cx, cy, radius, fromDeg, toDeg) {
  const radians = (degrees) => (degrees * Math.PI) / 180;
  const start = radians(fromDeg);
  const end = radians(toDeg);
  const x1 = cx + radius * Math.cos(start);
  const y1 = cy + radius * Math.sin(start);
  const x2 = cx + radius * Math.cos(end);
  const y2 = cy + radius * Math.sin(end);
  const span = Math.abs(toDeg - fromDeg);
  const largeArc = span > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}`;
}

export function aliasTag(id) {
  return `apollo-tab-el-${String(id).replace("/", "-")}`;
}

export function dashboardFromPath(pathname) {
  const part = String(pathname || "").split("/").filter(Boolean)[0];
  return part || null;
}

function stable(value) {
  if (Array.isArray(value)) {
    return value.map(stable);
  }
  if (value && typeof value === "object") {
    const result = {};
    for (const key of Object.keys(value).sort()) {
      if (value[key] !== undefined) {
        result[key] = stable(value[key]);
      }
    }
    return result;
  }
  return value;
}

export function subscriptionKey(card, dashboard) {
  const source = card || {};
  return JSON.stringify(
    stable({
      component: source.component,
      params: source.params,
      style: source.style,
      title: source.title,
      grid_options: source.grid_options,
      dashboard: dashboard ?? null,
    }),
  );
}

function hexToRgb(hex) {
  return [
    Number.parseInt(hex.slice(1, 3), 16),
    Number.parseInt(hex.slice(3, 5), 16),
    Number.parseInt(hex.slice(5, 7), 16),
  ];
}

function rgbToHex(rgb) {
  if (!Array.isArray(rgb) || rgb.length !== 3) {
    return undefined;
  }
  const parts = rgb.map((value) => {
    const number = Math.max(0, Math.min(255, Math.round(Number(value))));
    return Number.isFinite(number)
      ? number.toString(16).padStart(2, "0")
      : "00";
  });
  return `#${parts.join("").toUpperCase()}`;
}

export function styleToForm(style = {}) {
  return {
    theme: style.theme || "",
    use_color: isHex(style.color),
    ...(isHex(style.color) ? { color: hexToRgb(style.color) } : {}),
    gradient: style.gradient?.direction || "none",
    ...(isHex(style.gradient?.to)
      ? { gradient_to: hexToRgb(style.gradient.to) }
      : {}),
    transparency: wholePercent(style.transparency),
    use_accent: isHex(style.accent),
    ...(isHex(style.accent) ? { accent: hexToRgb(style.accent) } : {}),
  };
}

// A saved transparency must be a whole number from 0 to 100, but the number
// box next to the slider lets any number through.
function wholePercent(value) {
  return Math.min(100, Math.max(0, Math.round(toNumber(value, 0))));
}

export function formToStyle(data = {}) {
  const style = {};

  if (data.theme) {
    style.theme = data.theme;
  }

  const color = rgbToHex(data.color);
  if (data.use_color && isHex(color)) {
    style.color = color;
  }

  const gradientTo = rgbToHex(data.gradient_to);
  if (
    (data.gradient === "vertical" || data.gradient === "horizontal") &&
    isHex(gradientTo)
  ) {
    style.gradient = {
      to: gradientTo,
      direction: data.gradient,
    };
  }

  const transparency = wholePercent(data.transparency);
  if (transparency !== 0) {
    style.transparency = transparency;
  }

  const accent = rgbToHex(data.accent);
  if (data.use_accent && isHex(accent)) {
    style.accent = accent;
  }

  return Object.keys(style).length ? style : undefined;
}

function removeUndefined(value) {
  if (Array.isArray(value)) {
    return value.map(removeUndefined);
  }
  if (value && typeof value === "object") {
    const result = {};
    for (const [key, item] of Object.entries(value)) {
      if (item !== undefined) {
        result[key] = removeUndefined(item);
      }
    }
    return result;
  }
  return value;
}

export function cleanConfig(config) {
  const result = removeUndefined(config || {});
  if (!Object.keys(result.params || {}).length) {
    delete result.params;
  }
  if (!Object.keys(result.style || {}).length) {
    delete result.style;
  }
  if (result.title === "") {
    delete result.title;
  }
  return result;
}

export function feedbackReduce(state, event) {
  const current = { ...state };

  if (event.type === "act") {
    if (event.policy === "optimistic") {
      return event.value === undefined
        ? { phase: "pulse", value: undefined, until: event.now + 600 }
        : { phase: "pending", value: event.value, until: event.now + 5000 };
    }
    if (event.policy === "pulse") {
      return { phase: "pulse", value: event.value, until: event.now + 600 };
    }
    if (event.policy === "progress") {
      return { phase: "pending", value: event.value, until: event.now + 30000 };
    }
    if (event.policy === "confirm") {
      return { phase: "busy", value: current.value, until: event.now + 10000 };
    }
    return current;
  }

  if (event.type === "ok") {
    return current.phase === "busy"
      ? { phase: "idle", value: undefined, until: 0 }
      : current;
  }

  if (event.type === "fail") {
    return { phase: "error", value: current.value, until: event.now + 3000 };
  }

  if (event.type === "value") {
    return current.phase === "pending"
      ? { phase: "idle", value: undefined, until: 0 }
      : current;
  }

  if (event.type === "tick" && current.phase !== "idle" && current.until <= event.now) {
    return { phase: "idle", value: undefined, until: 0 };
  }

  return current;
}

export function warningText(warning, strings) {
  const key = `warn.${warning.code}`;
  return format(strings?.[key] ?? warning.code, {
    detail: warning.detail || "",
  });
}

// Where a warning applies, in the words the panel uses: pages and cards.
export function warningPlace(warning) {
  const parts = [];
  if (warning.view !== null && warning.view !== undefined) {
    parts.push(`Page ${warning.view + 1}`);
  }
  if (warning.card !== null && warning.card !== undefined) {
    parts.push(parts.length ? `card ${warning.card + 1}` : `Card ${warning.card + 1}`);
  }
  return parts.join(", ");
}

const WARNING_BOX_KINDS = Object.freeze({
  over_budget_charts: "omitted",
  over_budget_arcs: "omitted",
  over_budget_gradients: "flat",
});

// Which mark the tablet preview draws for a warning:
//   "omitted": the card was left out of the page (hatched box)
//   "flat": the card is kept but its gradient is drawn as a plain colour (outline only)
//   null: nothing is drawn on the page
export function warningBoxKind(warning) {
  if (
    !warning ||
    typeof warning !== "object" ||
    !Array.isArray(warning.r) ||
    warning.r.length !== 4 ||
    !warning.r.every(
      (value) => typeof value === "number" && Number.isFinite(value),
    ) ||
    !Object.hasOwn(WARNING_BOX_KINDS, warning.code)
  ) {
    return null;
  }

  return WARNING_BOX_KINDS[warning.code];
}

// ---- the accent colour, made readable --------------------------------
// Home Assistant's accent is a mid colour: white words on the default
// #009ac7 have only 3.26:1. These pick a fill, its words and a text colour
// from the theme's own colours, so each has 4.5:1 where it is drawn.

// "rgb(0, 154, 199)" or "color(srgb 0 0.6 0.78)" -> [r, g, b] (0..255, each
// channel clamped and rounded). null for anything else, and for a colour
// that is not fully opaque.
export function parseCssColour(text) {
  if (typeof text !== "string") {
    return null;
  }
  const value = text.trim();
  let parts = null;
  let scale = 1;
  let match = /^rgba?\(([^)]*)\)$/i.exec(value);
  if (match) {
    parts = match[1].split(/[\s,/]+/).filter(Boolean);
  } else {
    match = /^color\(\s*srgb\s+([^)]*)\)$/i.exec(value);
    if (!match) {
      return null;
    }
    parts = match[1].split(/[\s/]+/).filter(Boolean);
    scale = 255;
  }
  if (parts.length !== 3 && parts.length !== 4) {
    return null;
  }
  const numbers = parts.map((part) => (part.endsWith("%") ? Number(part.slice(0, -1)) / 100 : Number(part)));
  if (!numbers.every(Number.isFinite)) {
    return null;
  }
  if (parts.length === 4) {
    // A percentage alpha is already a share; a number may be one too.
    if (numbers[3] < 1) {
      return null;
    }
  }
  return numbers.slice(0, 3).map((channel, index) => {
    const share = parts[index].endsWith("%") ? channel * 255 : channel * scale;
    return Math.max(0, Math.min(255, Math.round(share)));
  });
}

// Relative luminance as WCAG 2 defines it.
function luminance(rgb) {
  const [r, g, b] = rgb.map((value) => {
    const c = value / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// Moves each channel `share` of the way from a to b, halves rounded up.
function mix(a, b, share) {
  return a.map((value, index) => Math.floor(value + (b[index] - value) * share + 0.5));
}

const BLACK = [0, 0, 0];
const WHITE = [255, 255, 255];
const DARK_INK = [17, 17, 17];

// The filled button for an accent: { fill: [r, g, b], ink: [r, g, b] }.
export function accentInk(colour) {
  if (luminance(colour) > 0.4 && contrast(DARK_INK, colour) >= 4.5) {
    return { fill: [...colour], ink: DARK_INK };
  }
  for (let step = 0; step <= 25; step += 1) {
    const fill = mix(colour, BLACK, 0.04 * step);
    if (contrast(WHITE, fill) >= 4.5) {
      return { fill, ink: WHITE };
    }
  }
  return { fill: BLACK, ink: WHITE };
}

// The grounds a link or a text button can sit on, from the theme's colours:
// [surface, page, stage, accent-soft, tonal, and the four notice grounds],
// each [r, g, b]. The surface is first. A colour that is missing is left
// out, and so is every ground made from it.
export function accentGrounds({ surface, page, stage, text, accent, tones = {} }) {
  const grounds = [surface, page, stage];
  if (accent) {
    grounds.push(mix(surface, accent, 0.14));
  }
  if (text) {
    grounds.push(mix(surface, text, 0.08));
  }
  for (const tone of [tones.ok, tones.warn, tones.err, tones.info]) {
    if (tone) {
      grounds.push(mix(surface, tone, 0.12));
    }
  }
  return grounds.filter(Boolean);
}

// The knob of a switch that is off: the surface on a light theme, the text
// colour on a dark one, so it is lighter than its track in both and never
// reads as a hole. [r, g, b].
export function switchKnob(surface, text) {
  return luminance(surface) > 0.4 ? [...surface] : [...text];
}

// The accent as text that has 4.5:1 on every ground: [r, g, b]. It moves
// toward black on a light surface and toward white on a dark one.
export function accentText(colour, grounds) {
  const target = luminance(grounds[0]) > 0.4 ? BLACK : WHITE;
  for (let step = 0; step <= 25; step += 1) {
    const text = mix(colour, target, 0.04 * step);
    if (grounds.every((ground) => contrast(text, ground) >= 4.5)) {
      return text;
    }
  }
  return target;
}

// ---- the editor's layout ------------------------------------------------

// The editor's layout for its own width and the window's height (both in
// px): "wide" (the inspector docked on the right), "medium" (the inspector a
// drawer over the picture), "compact" (one column) or "short" (two columns
// in a low window, such as a phone on its side).
export function layoutBand(width, height) {
  if (height < 560) {
    return width >= 600 ? "short" : "compact";
  }
  if (width >= 1160) {
    return "wide";
  }
  return width >= 900 ? "medium" : "compact";
}

// The height of the editor's shell in px. `visual` is the browser's
// visualViewport ({ height, offsetTop, scale }) or null; `top` is the
// root's top edge in the window. Above a phone's on-screen keyboard it ends
// where the visible part ends; pinch zoom does not make it smaller.
export function shellHeight({ innerHeight, visual, top }) {
  const zoomed = visual && Math.abs(visual.scale - 1) > 0.01;
  const bottom = visual && !zoomed ? visual.height + visual.offsetTop : innerHeight;
  return Math.max(0, Math.floor(bottom - top));
}

// The picture's width in px for the free space around it: as large as fits,
// never above the tablet's own 1280 x 800.
export function fitStage(availW, availH) {
  return Math.max(0, Math.floor(Math.min(availW, availH * 1.6, 1280)));
}

// How far (px) the picture moves left so the card clears the drawer.
// All four are x positions on screen. The card never moves past minLeft.
export function drawerShift(cardLeft, cardRight, drawerLeft, minLeft) {
  const need = cardRight + 16 - drawerLeft;
  if (need <= 0) {
    return 0;
  }
  return Math.min(need, Math.max(0, cardLeft - minLeft));
}

// Where a pop-up of `size` ({ width, height }) goes beside its opener
// (`anchor`, a box with left, top, right and bottom), inside `bounds` (the
// same kind of box): under the opener, lined up with its start edge, or
// above it when only there is room. Moved to stay inside the bounds; when
// it is larger than they are, its start edge and top stay inside. Returns
// { left, top } in px. rtl: lined up with the opener's right edge.
export function placeBeside(anchor, size, bounds, { rtl = false, gap = 4 } = {}) {
  const width = Math.max(0, size.width);
  const height = Math.max(0, size.height);
  let top = anchor.bottom + gap;
  const roomBelow = bounds.bottom - anchor.bottom - gap;
  const roomAbove = anchor.top - gap - bounds.top;
  if (height > roomBelow && roomAbove > roomBelow) {
    top = anchor.top - gap - height;
  }
  top = Math.max(bounds.top, Math.min(top, bounds.bottom - height));
  let left = rtl ? anchor.right - width : anchor.left;
  left = Math.min(left, bounds.right - width);
  left = Math.max(bounds.left, left);
  if (rtl && width > bounds.right - bounds.left) {
    left = bounds.right - width;
  }
  return { left: Math.round(left), top: Math.round(top) };
}
