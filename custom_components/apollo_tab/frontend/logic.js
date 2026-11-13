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
