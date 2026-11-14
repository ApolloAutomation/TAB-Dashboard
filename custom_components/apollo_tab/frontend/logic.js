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

export function subscriptionKey(card, dashboard, detail = false) {
  const source = card || {};
  return JSON.stringify(
    stable({
      component: source.component,
      params: source.params,
      style: source.style,
      title: source.title,
      grid_options: source.grid_options,
      // A schema 2 card: its look and settings make another card.
      variant: source.variant,
      options: source.options,
      dashboard: dashboard ?? null,
      ...(detail ? { detail: true } : {}),
    }),
  );
}

// The detail copy in a browser dialog: rows stack from the bottom, so a band
// that parts this device does not have leave empty is cut down to the gap
// between rows. Only gaps over 16 are cut; the card gets shorter.
export function compactCard(card, keep = 8, over = 16) {
  if (!card || Array.isArray(card.w) || !Number.isFinite(card.h) || !Array.isArray(card.widgets)) {
    return card;
  }
  const spans = [];
  const add = (rect) => {
    if (Array.isArray(rect) && rect[2] > 0 && rect[3] > 0) {
      spans.push([rect[1], rect[1] + rect[3]]);
    }
  };
  add(card.header?.r);
  card.widgets.forEach((widget) => add(widget.r));
  spans.sort((a, b) => a[0] - b[0]);
  const cuts = [];
  let end = spans[0]?.[1];
  for (const [top, bottom] of spans.slice(1)) {
    if (top - end > over) {
      cuts.push([end, top - end - keep]);
    }
    end = Math.max(end, bottom);
  }
  if (!cuts.length) {
    return card;
  }
  const shift = (y) => cuts.reduce((sum, [at, amount]) => (y >= at ? sum + amount : sum), 0);
  const move = (rect) => (Array.isArray(rect) ? [rect[0], rect[1] - shift(rect[1]), rect[2], rect[3]] : rect);
  return {
    ...card,
    h: card.h - cuts.reduce((sum, [, amount]) => sum + amount, 0),
    ...(card.header ? { header: { ...card.header, r: move(card.header.r) } } : {}),
    widgets: card.widgets.map((widget) => ({ ...widget, r: move(widget.r) })),
  };
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
function mixShare(a, b, share) {
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
    const fill = mixShare(colour, BLACK, 0.04 * step);
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
    grounds.push(mixShare(surface, accent, 0.14));
  }
  if (text) {
    grounds.push(mixShare(surface, text, 0.08));
  }
  for (const tone of [tones.ok, tones.warn, tones.err, tones.info]) {
    if (tone) {
      grounds.push(mixShare(surface, tone, 0.12));
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
    const text = mixShare(colour, target, 0.04 * step);
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

// ---- the tablet's rules, layout version 2 (contract 4.7) ---------------
// One function per rule, the same on the tablet, here and in Home
// Assistant (maker/style.py). Their vectors are in the contract's
// fixtures/maths.json. Colours are whole numbers 0xRRGGBB.

// The table "linear" of maths.json: the linear value of each channel
// value. Every side holds this copy and never works the values out.
export const LINEAR = Object.freeze([
  0.0, 0.0003035269835488375, 0.000607053967097675, 0.0009105809506465125,
  0.00121410793419535, 0.0015176349177441874, 0.001821161901293025, 0.0021246888848418626,
  0.0024282158683907, 0.0027317428519395373, 0.003035269835488375, 0.0033465357638991586,
  0.003676507324047435, 0.004024717018496304, 0.0043914420374102925, 0.0047769534806937275,
  0.005181516702338385, 0.005605391624202721, 0.006048833022857052, 0.006512090792594472,
  0.006995410187265385, 0.00749903204322617, 0.008023192985384993, 0.008568125618069302,
  0.009134058702220785, 0.009721217320237844, 0.010329823029626936, 0.01096009400648824,
  0.011612245179743881, 0.012286488356915867, 0.012983032342173007, 0.013702083047289683,
  0.014443843596092541, 0.015208514422912706, 0.015996293365509628, 0.016807375752887377,
  0.017641954488384078, 0.01850022012837969, 0.019382360956935723, 0.02028856305665239,
  0.021219010376003555, 0.022173884793387375, 0.023153366178110403, 0.02415763244850475,
  0.025186859627361623, 0.02624122189484989, 0.02732089163907489, 0.028426039504420787,
  0.029556834437808797, 0.03071344373299362, 0.03189603307301152, 0.03310476657088505,
  0.03433980680868216, 0.03560131487502032, 0.03688945040110002, 0.03820437159534648,
  0.03954623527673283, 0.04091519690685317, 0.042311410620809654, 0.04373502925697345,
  0.04518620438567554, 0.04666508633688008, 0.048171824226889405, 0.04970656598412722,
  0.051269458374043224, 0.05286064702318025, 0.054480276442442355, 0.05612849004960008,
  0.05780543019106721, 0.059511238162981185, 0.061246054231617594, 0.06301001765316766,
  0.06480326669290576, 0.06662593864377288, 0.06847816984440015, 0.07036009569659588,
  0.07227185068231748, 0.07421356838014961, 0.07618538148130781, 0.07818742180518633,
  0.08021982031446831, 0.0822827071298148, 0.08437621154414877, 0.08650046203654974,
  0.08865558628577294, 0.09084171118340768, 0.09305896284668742, 0.09530746663096466,
  0.09758734714186242, 0.09989872824711389, 0.10224173308810128, 0.10461648409110416,
  0.10702310297826759, 0.10946171077829933, 0.11193242783690557, 0.11443537382697372,
  0.11697066775851081, 0.1195384279883456, 0.12213877222960184, 0.12477181756095046,
  0.12743768043564743, 0.13013647669036427, 0.13286832155381792, 0.13563332965520564,
  0.13843161503245183, 0.14126329114027164, 0.14412847085805772, 0.14702726649759498,
  0.14995978981060853, 0.15292615199615014, 0.15592646370782734, 0.15896083506088035,
  0.162029375639111, 0.1651321945016676, 0.1682694001896907, 0.17144110073282254,
  0.17464740365558498, 0.17788841598362912, 0.18116424424986013, 0.1844749945004409,
  0.18782077230067779, 0.19120168274079136, 0.1946178304415757, 0.1980693195599488,
  0.20155625379439707, 0.2050787363903169, 0.20863687014525567, 0.2122307574140551,
  0.21586050011389915, 0.21952619972926918, 0.22322795731680842, 0.22696587351009834,
  0.23074004852434896, 0.23455058216100508, 0.23839757381227095, 0.24228112246555472,
  0.2462013267078354, 0.2501582847299533, 0.2541520943308267, 0.25818285292159576,
  0.262250657529696, 0.2663556048028623, 0.27049779101306576, 0.27467731206038454,
  0.27889426347681034, 0.28314874042999194, 0.2874408377269174, 0.29177064981753587,
  0.29613827079832095, 0.3005437944157764, 0.3049873140698861, 0.30946892281750843,
  0.3139887133757175, 0.31854677812509175, 0.3231432091129507, 0.32777809805654207,
  0.3324515363461792, 0.33716361504833026, 0.34191442490866075, 0.3467040563550295,
  0.3515325995004392, 0.3564001441459434, 0.36130677978350945, 0.3662525955988394,
  0.37123768047414896, 0.3762621229909062, 0.38132601143253, 0.3864294337870489,
  0.3915724777497231, 0.3967552307256268, 0.4019777798321956, 0.40724021190173665,
  0.4125426134839036, 0.41788507084813725, 0.4232676699860715, 0.42869049661390657,
  0.4341536361747488, 0.43965717384091874, 0.44520119451622775, 0.45078578283822335,
  0.4564110231804045, 0.46207699965440685, 0.4677837961121588, 0.4735314961480093,
  0.47932018310082664, 0.4851499400560704, 0.49102084984783545, 0.49693299506087035,
  0.5028864580325684, 0.5088813208549335, 0.5149176653765213, 0.5209955732043541,
  0.527115125705813, 0.533276404010505, 0.539479489012107, 0.5457244613701866,
  0.5520114015119999, 0.5583403896342677, 0.5647115057049289, 0.5711248294648729,
  0.5775804404296505, 0.584078417891164, 0.5906188409193368, 0.5972017883637631,
  0.6038273388553375, 0.6104955708078647, 0.6172065624196509, 0.6239603916750759,
  0.6307571363461467, 0.6375968739940324, 0.644479681970582, 0.6514056374198239,
  0.6583748172794482, 0.6653872982822719, 0.6724431569576873, 0.6795424696330937,
  0.6866853124353132, 0.6938717612919898, 0.7011018919329731, 0.7083757798916867,
  0.7156935005064805, 0.7230551289219689, 0.7304607400903533, 0.7379104087727307,
  0.7454042095403872, 0.7529422167760778, 0.7605245046752922, 0.7681511472475069,
  0.7758222183174234, 0.7835377915261932, 0.79129794033263, 0.7991027380144087,
  0.8069522576692514, 0.8148465722161011, 0.8227857543962833, 0.8307698767746545,
  0.8387990117407399, 0.8468732315098577, 0.8549926081242336, 0.863157213454102,
  0.8713671191987971, 0.8796223968878317, 0.8879231178819664, 0.8962693533742666,
  0.9046611743911491, 0.9130986517934189, 0.9215818562772945, 0.9301108583754234,
  0.9386857284578878, 0.9473065367331996, 0.955973353249286, 0.9646862478944651,
  0.9734452903984123, 0.982250550333117, 0.9911020971138297, 1.0,
]);

export const TABLET_WHITE = 0xffffff;
export const TABLET_INK = 0x15181d;

// round(x) of contract 4.7.
export function roundHalfUp(x) {
  return Math.floor(x + 0.5);
}

// "#RRGGBB" to 0xRRGGBB, or null.
export function colourOf(hex) {
  return isHex(hex) ? Number.parseInt(hex.slice(1), 16) : null;
}

// 0xRRGGBB to "#RRGGBB".
export function hexOf(colour) {
  return `#${(Number(colour) >>> 0).toString(16).padStart(6, "0").slice(-6).toUpperCase()}`;
}

function channels(c) {
  return [(c >> 16) & 255, (c >> 8) & 255, c & 255];
}

// Per channel (a * (100 - p) + b * p + 50) div 100, in whole numbers.
export function mix(a, b, p) {
  const x = channels(a);
  const y = channels(b);
  let out = 0;
  for (let i = 0; i < 3; i += 1) {
    out = out * 256 + Math.floor((x[i] * (100 - p) + y[i] * p + 50) / 100);
  }
  return out;
}

// (0.2126 * L[r] + 0.7152 * L[g]) + 0.0722 * L[b], each step on its own.
export function lum(c) {
  const [r, g, b] = channels(c);
  const first = 0.2126 * LINEAR[r];
  const second = 0.7152 * LINEAR[g];
  const third = 0.0722 * LINEAR[b];
  return first + second + third;
}

export function contrastOf(a, b) {
  const x = lum(a);
  const y = lum(b);
  const hi = x >= y ? x : y;
  const lo = x >= y ? y : x;
  return (hi + 0.05) / (lo + 0.05);
}

// White or 0x15181D, the one that stands out more on c; white on a tie.
export function readable(c) {
  return contrastOf(TABLET_WHITE, c) >= contrastOf(TABLET_INK, c) ? TABLET_WHITE : TABLET_INK;
}

// c when it stands out on b; else c mixed half with t if that does; else t.
export function legible(c, b, t) {
  if (contrastOf(c, b) >= 3) {
    return c;
  }
  const m = mix(c, t, 50);
  return contrastOf(m, b) >= 3 ? m : t;
}

// Version 1's blend, kept for the one rule that uses it (a card's ion and
// onbg_pr): per channel floor(a * (1 - t) + b * t + 0.5).
export function blendOf(a, b, t) {
  const x = channels(a);
  const y = channels(b);
  let out = 0;
  for (let i = 0; i < 3; i += 1) {
    const first = x[i] * (1 - t);
    const second = y[i] * t;
    out = out * 256 + Math.floor(first + second + 0.5);
  }
  return out;
}

const THEME_KEYS = [
  "wall", "card", "card_pr", "card2", "card2_pr", "line", "tx", "tx2", "acc",
  "accf", "accf_pr", "acct", "acc2", "onbg", "onbg_pr", "ontx", "ion",
];
const STYLE_KEYS = [
  "bg", "bg2", "tx", "tx2", "acc", "acc2", "acct", "card2", "line", "onbg", "ontx",
  "card_pr", "card2_pr", "accf", "accf_pr", "onbg_pr", "ion",
];

// A theme or style as numbers: "#RRGGBB" and whole numbers both count.
function asColour(value) {
  if (typeof value === "string") {
    return colourOf(value);
  }
  return Number.isInteger(value) && value >= 0 && value <= TABLET_WHITE ? value : null;
}

// The colours of a card: the page's theme with the card's style on top
// (contract 4.7). Both may hold "#RRGGBB" or numbers; the answer holds
// numbers. bg is the card's background.
export function cardColourTokens(theme = {}, style = {}) {
  const tokens = {};
  for (const key of THEME_KEYS) {
    const value = asColour(theme[key]);
    if (value !== null) {
      tokens[key] = value;
    }
  }
  if (tokens.card !== undefined) {
    tokens.bg = tokens.card;
  }
  for (const key of ["r", "r2", "bw"]) {
    tokens[key] = Number.isFinite(theme[key]) ? theme[key] : 0;
  }
  for (const key of STYLE_KEYS) {
    const value = asColour(style[key]);
    if (value !== null) {
      tokens[key] = value;
    }
  }
  for (const key of ["r", "r2", "bw"]) {
    if (Number.isFinite(style[key])) {
      tokens[key] = style[key];
    }
  }
  const ownOnbg = asColour(style.onbg);
  if (ownOnbg !== null && ownOnbg !== asColour(theme.onbg)) {
    if (asColour(style.ion) === null) {
      tokens.ion = contrastOf(tokens.acc, ownOnbg) >= 3 ? tokens.acc : tokens.ontx;
    }
    if (asColour(style.onbg_pr) === null) {
      tokens.onbg_pr = blendOf(tokens.ontx, ownOnbg, 0.82);
    }
  }
  return tokens;
}

// The nine colours of a card and what it shows now (contract 4.7, "Card
// colours"). tokens is cardColourTokens(); lit 0 fill, 1 icon, 2 outline,
// 3 no change; tint a colour or null.
export function cardColours(tokens, on, lit = 0, tint = null) {
  const { bg, tx, tx2 } = tokens;
  const dark = readable(bg) === TABLET_WHITE;
  let out;
  if (tint === null || tint === undefined) {
    out = {
      A: tokens.acc,
      AF: tokens.accf,
      AT: tokens.acct,
      AP: tokens.accf_pr,
      F: tokens.onbg,
      FT: tokens.ontx,
      FS: tokens.ontx,
      FI: tokens.ion,
      FP: tokens.onbg_pr,
    };
  } else {
    const a = legible(tint, bg, tx);
    const f = mix(tint, bg, dark ? 78 : 84);
    out = {
      A: a,
      AF: a,
      AT: readable(a),
      AP: mix(0x000000, a, 88),
      F: f,
      FT: tx,
      FS: contrastOf(tx2, f) >= 3 ? tx2 : tx,
      FI: legible(tint, f, tx),
      FP: mix(tx, f, 90),
    };
  }
  const filled = Boolean(on) && lit === 0;
  const litOn = Boolean(on) && (lit === 1 || lit === 2);
  out.dark = dark ? 1 : 0;
  out.filled = filled ? 1 : 0;
  out.background = filled ? out.F : bg;
  out.text = filled ? out.FT : tx;
  out.border = filled || (on && lit === 2) ? out.A : tokens.line;
  out.border_width = on && lit === 2 ? Math.max(2, tokens.bw) : tokens.bw;
  out.header_icon = filled ? out.FI : litOn ? out.A : tx2;
  return out;
}

// The spec's name for the two steps at once.
export function cardState(theme, style, on, lit = 0, tint = null) {
  return cardColours(cardColourTokens(theme, style), on, lit, tint);
}

// A value as a colour (contract 4.4): [r, g, b], "#RRGGBB", a whole number
// or a role name of roles. null for anything else.
export function toColour(value, roles = null) {
  if (value === null || value === undefined || typeof value === "boolean") {
    return null;
  }
  if (typeof value === "string") {
    if (roles && Object.hasOwn(roles, value)) {
      return asColour(roles[value]);
    }
    return /^#[0-9A-Fa-f]{6}$/.test(value) ? Number.parseInt(value.slice(1), 16) : null;
  }
  if (typeof value === "number") {
    return Number.isInteger(value) && value >= 0 && value <= TABLET_WHITE ? value : null;
  }
  if (Array.isArray(value) && value.length === 3) {
    let out = 0;
    for (const part of value) {
      if (typeof part !== "number" || !Number.isFinite(part)) {
        return null;
      }
      const channel = roundHalfUp(part);
      if (channel < 0 || channel > 255) {
        return null;
      }
      out = out * 256 + channel;
    }
    return out;
  }
  return null;
}

const ICON_SIZES = [72, 48, 28, 24];

// The largest of 72, 48, 28, 24 that is not above limit; 24 when none is.
export function largestIcon(limit) {
  return ICON_SIZES.find((px) => px <= limit) ?? 24;
}

// An image widget's look (contract 4.7, "Image"): its box or circle from
// the rectangle's corner, the icon size and the two colours. card is
// cardColours() of its card; c the widget's colour or null. null when the
// rectangle has no width or no height.
export function imageLook(tokens, card, on, lit, look, w, h, c) {
  if (w <= 0 || h <= 0) {
    return null;
  }
  const side = Math.min(w, h);
  if (!look) {
    return {
      box: [0, 0, w, h],
      fill: tokens.card2,
      icon_px: largestIcon(Math.floor(side / 2)),
      icon: c !== null && c !== undefined ? legible(c, tokens.card2, tokens.tx) : tokens.acc2,
    };
  }
  const filled = Boolean(on) && lit === 0;
  const litOn = Boolean(on) && (lit === 1 || lit === 2);
  const hasC = c !== null && c !== undefined;
  const plain = !hasC && !filled && !litOn;
  const k = hasC ? c : filled ? card.FI : litOn ? card.A : tokens.tx2;
  const b = card.background;
  const t = card.text;
  if (look === 1) {
    const x = roundHalfUp((w - side) / 2);
    const y = roundHalfUp((h - side) / 2);
    const iconPx = largestIcon(0.6 * side);
    if (plain) {
      return { box: [x, y, side, side], fill: tokens.card2, icon_px: iconPx, icon: tokens.tx2, plain: 1 };
    }
    const wash = mix(k, b, 80);
    return { box: [x, y, side, side], fill: wash, icon_px: iconPx, icon: legible(k, wash, t), plain: 0 };
  }
  return { box: null, fill: null, icon_px: largestIcon(side), icon: legible(k, b, t), plain: plain ? 1 : 0 };
}

const LABEL_PX = [14, 18, 34];
const TEXT_PX = [14, 15, 16, 18, 20, 28, 34];
const DIGITS_PX = [48, 96, 192];
const DIGITS_GLYPHS = "0123456789.,-:°%+ ";

// The size a label is drawn at before its width is checked (contract 4.7):
// {px, smaller: the sizes to try in turn while the text is wider than its
// rectangle, small: drawn in the small colour}. px null: size 0, 1 or 2.
export function labelSize(px, text, size = 1) {
  if (px === null || px === undefined) {
    const chosen = LABEL_PX[size] ?? 18;
    return { px: chosen, smaller: [], small: chosen === 14 ? 1 : 0 };
  }
  const digits = [...String(text ?? "")].every((ch) => DIGITS_GLYPHS.includes(ch));
  if (digits && px >= DIGITS_PX[0]) {
    const chosen = [...DIGITS_PX].reverse().find((d) => d <= px);
    const chain = [192, 96, 48, 34];
    return { px: chosen, smaller: chain.slice(chain.indexOf(chosen) + 1), small: 0 };
  }
  const fits = TEXT_PX.filter((t) => t <= px);
  const chosen = fits.length ? fits.at(-1) : TEXT_PX[0];
  return { px: chosen, smaller: [], small: chosen === 14 || chosen === 15 ? 1 : 0 };
}

// The size a label is drawn at once its width is checked: the first of
// labelSize's sizes whose text fits `width`. widthAt(px) gives the text's
// width at px, or null while it cannot be measured.
export function tabletLabelSize(px, text, width, widthAt = null, size = 1) {
  const first = labelSize(px, text, size);
  let chosen = first.px;
  for (const next of first.smaller) {
    const drawn = widthAt?.(chosen);
    if (drawn === null || drawn === undefined || drawn <= width) {
      break;
    }
    chosen = next;
  }
  return { px: chosen, small: chosen === 14 || chosen === 15 ? 1 : first.small };
}

// The text of a clock label: m = floor(v + age / 60) mod 1440, as HH:MM
// (form 1) or with the hour 12, 1 to 11 (form 2). No value: "--:--".
export function clockText(value, ageS, form) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "--:--";
  }
  const m = (((Math.floor(value + ageS / 60)) % 1440) + 1440) % 1440;
  const hour = Math.floor(m / 60);
  const minute = String(m % 60).padStart(2, "0");
  if (form === 2) {
    return `${hour % 12 || 12}:${minute}`;
  }
  return `${String(hour).padStart(2, "0")}:${minute}`;
}

// [L, S]: a slider's length along its axis and its other side.
export function sliderAxis(rect, dir) {
  const w = Math.max(0, rect[2]);
  const h = Math.max(0, rect[3]);
  return dir === 1 || dir === 2 ? [h, w] : [w, h];
}

// A point's distance from the slider's start edge, along the axis.
export function sliderAlong(rect, dir, x, y) {
  if (dir === 1) {
    return rect[1] + rect[3] - y;
  }
  if (dir === 2) {
    return y - rect[1];
  }
  return x - rect[0];
}

// R of a track: 7 for a knob slider, min(r2, S div 2) for a bar.
export function sliderRadius(look, rect, dir, r2) {
  const side = sliderAxis(rect, dir)[1];
  return look === 1 ? Math.min(r2, Math.floor(side / 2)) : 7;
}

// The amount under a finger, 0 to 1. track is the number of colours.
export function sliderAmount(rect, look, dir, track, r2, x, y) {
  const length = sliderAxis(rect, dir)[0];
  const along = sliderAlong(rect, dir, x, y);
  if (track >= 2) {
    const radius = sliderRadius(look, rect, dir, r2);
    const x0 = radius;
    const x1 = length - radius;
    if (x1 <= x0) {
      return 0;
    }
    return Math.min(1, Math.max(0, (along - x0) / (x1 - x0)));
  }
  if (length <= 0) {
    return 0;
  }
  return Math.min(1, Math.max(0, along / length));
}

// The length a finger moves over: x1 - x0 with a track, else L.
export function sliderLength(rect, look, dir, track, r2) {
  const length = sliderAxis(rect, dir)[0];
  return track >= 2 ? length - 2 * sliderRadius(look, rect, dir, r2) : length;
}

// The value a slider sends for an amount; null when it sends nothing (a
// track of no length, or max not above min).
export function sliderValue(amount, min, max, step, length) {
  if (length <= 0 || !(max > min)) {
    return null;
  }
  return clampStep(min + amount * (max - min), min, max, step);
}

// The n - 1 pieces of a track of n colours, [from, to] along the axis.
export function trackPieces(n, x0, x1) {
  if (n < 2 || x1 <= x0) {
    return [];
  }
  const pieces = [];
  for (let k = 0; k < n - 1; k += 1) {
    pieces.push([x0 + Math.floor((k * (x1 - x0)) / (n - 1)), x0 + Math.floor(((k + 1) * (x1 - x0)) / (n - 1))]);
  }
  return pieces;
}

// Where a value is drawn, as distances from the start edge (contract 4.7,
// "Slider"): the knob; or the bar's fill, handle and icon; or a track's
// caps, pieces and mark.
export function sliderGeometry(rect, look, dir, track, r2, value, min, max, change) {
  const [length, side] = sliderAxis(rect, dir);
  const has = value !== null && value !== undefined;
  const amount = has ? fraction(value, min, max) : 0;
  const out = { L: length, S: side };
  if (track >= 2) {
    const radius = sliderRadius(look, rect, dir, r2);
    const x0 = radius;
    const x1 = length - radius;
    out.R = radius;
    out.caps = [[0, Math.min(x0, length)], [x1 > x0 ? Math.max(x1, 0) : Math.max(x0, 0), length]];
    out.pieces = trackPieces(track, x0, x1);
    out.mark = x1 <= x0 || !has || !(max > min) ? null : roundHalfUp(x0 + amount * (x1 - x0));
    return out;
  }
  if (look !== 1) {
    out.knob = has ? roundHalfUp(amount * length) : null;
    return out;
  }
  const radius = sliderRadius(look, rect, dir, r2);
  const fill = has ? roundHalfUp(amount * length) : 0;
  out.R = radius;
  out.fill = fill;
  out.drawn = fill <= 0 ? 0 : Math.max(fill, 2 * radius);
  out.handle = change && fill >= 28 ? [fill - 12, fill - 8] : null;
  out.icon_centre = side >= 32 ? 24 : null;
  out.icon_on_fill = side >= 32 && fill >= 48 ? 1 : 0;
  return out;
}

// The cells of a choice, [x, y, w, h] from its rectangle's corner; with
// look 1 each cell also has its dot [x, y, d, d]. null when nothing is
// drawn: no option, or a cell below 1 px.
export function choiceCells(n, rows, w, h, look = 0) {
  const count = Math.min(n, 16);
  const lines = Math.min(4, Math.max(1, rows || 1));
  if (count <= 0) {
    return null;
  }
  const perRow = Math.ceil(count / lines);
  const cellW = Math.floor((w - 8 * (perRow - 1)) / perRow);
  const cellH = Math.floor((h - 8 * (lines - 1)) / lines);
  if (cellW < 1 || cellH < 1) {
    return null;
  }
  const cells = [];
  for (let index = 0; index < count; index += 1) {
    const row = Math.floor(index / perRow);
    const column = index % perRow;
    const cell = [column * (cellW + 8), row * (cellH + 8), cellW, cellH];
    if (look === 1) {
      const d = Math.min(cellW, cellH);
      cell.push([cell[0] + roundHalfUp((cellW - d) / 2), cell[1] + roundHalfUp((cellH - d) / 2), d, d]);
    }
    cells.push(cell);
  }
  return cells;
}

// The option under a point (from the rectangle's corner), or null.
export function choiceAt(cells, x, y) {
  const index = (cells || []).findIndex(
    (cell) => cell[0] <= x && x < cell[0] + cell[2] && cell[1] <= y && y < cell[1] + cell[3],
  );
  return index < 0 ? null : index;
}

// The steps of a line chart with st 1: filled rectangles 3 thick, [x, y,
// w, h], from linePoints.
export function stepRects(points) {
  const out = [];
  for (let i = 0; i + 1 < points.length; i += 1) {
    const [xa, ya] = points[i];
    const [xb, yb] = points[i + 1];
    const left = roundHalfUp(Math.min(xa, xb) - 1);
    const right = roundHalfUp(Math.max(xa, xb) + 1);
    out.push([left, roundHalfUp(ya - 1.5), right - left, 3]);
    if (ya !== yb) {
      const top = roundHalfUp(Math.min(ya, yb) - 1);
      const bottom = roundHalfUp(Math.max(ya, yb) + 1);
      out.push([roundHalfUp(xb - 1.5), top, 3, bottom - top]);
    }
  }
  return out;
}

// The colour role of each bar of a bar chart with mark: "acc2", "acc" for
// the bar of now, "card2" after it.
export function barMarks(n, mark) {
  const plainBars = Array.from({ length: n }, () => "acc2");
  if (mark === null || mark === undefined || !Number.isFinite(mark)) {
    return plainBars;
  }
  const k = roundHalfUp(mark);
  if (k < 0 || k >= n) {
    return plainBars;
  }
  return plainBars.map((role, index) => (index < k ? role : index === k ? "acc" : "card2"));
}

// ---- `when`: whether a part or a form row of a schema 2 card is there ----
// The twin of maker/when.py; both pass tests/fixtures/when_vectors.json.
// `names` is one flat map: an option by its name, a fact as can.<what> or
// can.<param>.<what>, has.<param>, and tablet.v2. A missing name is false.

const WHEN_TERM = /^(!)?([a-z][a-z0-9_]*(?:\.[a-z0-9][a-z0-9_]*){0,2})(?:(=|!=)([a-z0-9_]+(?:\|[a-z0-9_]+)*))?$/;

// Yes, a number that is not 0, a text that is not empty and not "none", a
// list or a map that is not empty.
export function whenTruthy(value) {
  if (value === null || value === undefined || value === false) {
    return false;
  }
  if (value === true) {
    return true;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    return value !== "" && value !== "none";
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object") {
    return Object.keys(value).length > 0;
  }
  return false;
}

function whenText(value) {
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "number") {
    return String(value);
  }
  return typeof value === "string" ? value : null;
}

// For a list one entry is enough; "none" also matches no value, an empty
// text and an empty list.
function whenEquals(value, wanted) {
  if (wanted.includes("none") && !whenTruthy(value)) {
    return true;
  }
  if (Array.isArray(value)) {
    return value.some((entry) => entry !== null && entry !== undefined && whenEquals(entry, wanted));
  }
  const text = whenText(value);
  return text !== null && wanted.includes(text);
}

// One term: name, !name, name=a|b or name!=a|b. A bad shape never holds.
export function termHolds(term, names) {
  const match = typeof term === "string" ? WHEN_TERM.exec(term) : null;
  if (!match) {
    return false;
  }
  const [, negate, name, op, values] = match;
  if (negate && op) {
    return false;
  }
  const map = names && typeof names === "object" ? names : {};
  const value = Object.hasOwn(map, name) ? map[name] : undefined;
  if (!op) {
    const held = whenTruthy(value);
    return negate ? !held : held;
  }
  const held = whenEquals(value, values.split("|"));
  return op === "=" ? held : !held;
}

// Every term of a `when` list holds. No terms: it holds.
export function whenHolds(terms, names) {
  return (Array.isArray(terms) ? terms : []).every((term) => termHolds(term, names));
}

// [r, g, b] of a white of that warmth: Home Assistant's own fit, as
// maker/compile2.py::kelvin_rgb gives it.
export function kelvinRgb(kelvin) {
  const temp = Math.min(Math.max(Number(kelvin) || 0, 1000), 40000) / 100;
  const clamp = (value) => Math.min(Math.max(value, 0), 255);
  let red;
  let green;
  let blue;
  if (temp <= 66) {
    red = 255;
    green = clamp(99.4708025861 * Math.log(temp) - 161.1195681661);
  } else {
    red = clamp(329.698727446 * Math.pow(temp - 60, -0.1332047592));
    green = clamp(288.1221695283 * Math.pow(temp - 60, -0.0755148492));
  }
  if (temp >= 66) {
    blue = 255;
  } else if (temp <= 19) {
    blue = 0;
  } else {
    blue = clamp(138.5177312231 * Math.log(temp - 10) - 305.0447927307);
  }
  return [red, green, blue].map((part) => Math.floor(part + 0.5));
}
