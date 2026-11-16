import { t } from "./api.js";
import {
  arcPath,
  barMarks,
  barRects,
  blendOf,
  cardColours,
  choiceAt,
  choiceCells,
  clampStep,
  clockText,
  colourOf,
  contrastOf,
  fraction,
  hexOf,
  imageLook,
  isHex,
  isIcon,
  isOn,
  isSafeImagePath,
  largestIcon,
  legible,
  linePoints,
  mapRect,
  mix,
  readable,
  resolveBound,
  sliderAmount,
  sliderGeometry,
  sliderLength,
  sliderValue,
  stepRects,
  TABLET_ELLIPSIS,
  TABLET_INK,
  TABLET_MISSING_GLYPH,
  TABLET_WHITE,
  tabletCharWidths,
  tabletFit,
  tabletLabelSize,
  tabletLineHeight,
  tabletText,
  toColour,
  toNumber,
} from "./logic.js";

const SVG_NS = "http://www.w3.org/2000/svg";

const COLOR_TOKENS = [
  "wall",
  "bg",
  "bg2",
  "tx",
  "tx2",
  "acc",
  "accf",
  "accf_pr",
  "acc2",
  "acct",
  "card2",
  "card2_pr",
  "card_pr",
  "line",
  "onbg",
  "onbg_pr",
  "ontx",
  "ion",
];

const NUMBER_TOKENS = ["r", "r2", "bw"];

// The colours a card falls back to where its theme has none: the CSS
// defaults, which are the Midnight theme's.
const DEFAULT_TOKENS = {
  bg: 0x181c23,
  card: 0x181c23,
  card_pr: 0x232833,
  card2: 0x232833,
  card2_pr: 0x303746,
  line: 0x2a303a,
  tx: 0xe8eaed,
  tx2: 0x9aa0a8,
  acc: 0xf5b547,
  accf: 0xf5b547,
  accf_pr: 0xd99a2b,
  acct: 0x0e1116,
  acc2: 0x6cb4ff,
  onbg: 0x33291a,
  onbg_pr: 0x4a3a20,
  ontx: 0xf7e3bc,
  ion: 0xf5b547,
  wall: 0x101418,
};

// The image widget's icon sizes on the tablet (contract 4.7), and the glyph
// it draws for a value that is not an icon.
const TABLET_IMAGE_ICON_SIZES = [72, 48, 28, 24];
const TABLET_IMAGE_PLACEHOLDER = "mdi:image-outline";

// A press held this long is a hold; one that moved this far is neither a
// tap of the card nor a hold (contract 4.3, "Who gets a press").
const HOLD_MS = 500;
const MOVE_PX = 12;
// The card's pressed look waits this long, so a swipe does not flash it.
const PRESSED_MS = 80;

// The tablet's font (contract 4.7), for the tablet previews.
const TABLET_FONT_FAMILY = "Apollo TAB-1 Montserrat";
let tabletFontLoading = false;
let tabletFontReady = false;
// The load ended without the font. It is not asked for again.
let tabletFontFailed = false;
// Texts drawn before the font was there, to be drawn again once it is.
const tabletFontWaiting = new Map();

// Whether a text drawn now has to be drawn again once the font is there.
function tabletFontPending() {
  return tabletFontLoading && !tabletFontReady && !tabletFontFailed;
}

// The preview then keeps Home Assistant's font, and nothing waits for it.
function tabletFontLost() {
  tabletFontFailed = true;
  tabletFontWaiting.clear();
}

export function loadTabletFont() {
  if (tabletFontLoading || typeof FontFace !== "function" || typeof document === "undefined" || !document.fonts) {
    return;
  }
  tabletFontLoading = true;
  try {
    const url = new URL("./fonts/Montserrat-Medium.ttf", import.meta.url).href;
    const face = new FontFace(TABLET_FONT_FAMILY, `url("${url}")`, { weight: "100 900", style: "normal" });
    document.fonts.add(face);
    face
      .load()
      .then(() => {
        tabletFontReady = true;
        const again = [...tabletFontWaiting.values()];
        tabletFontWaiting.clear();
        for (const draw of again) {
          draw();
        }
      })
      .catch(tabletFontLost);
  } catch (_error) {
    tabletFontLost();
  }
}

// The largest tablet size of the image icon that fits min(w, h) / 2.
export function tabletImageIconSize(width, height) {
  const room = Math.min(width, height) / 2;
  return TABLET_IMAGE_ICON_SIZES.find((size) => size <= room) ?? TABLET_IMAGE_ICON_SIZES.at(-1);
}

function html(tag, className) {
  const result = document.createElement(tag);
  if (className) {
    result.className = className;
  }
  return result;
}

function svg(tag) {
  return document.createElementNS(SVG_NS, tag);
}

function setRect(element, rect) {
  element.style.left = `${rect[0]}px`;
  element.style.top = `${rect[1]}px`;
  element.style.width = `${rect[2]}px`;
  element.style.height = `${rect[3]}px`;
}

function iconElement(name) {
  if (!isIcon(name)) {
    return null;
  }
  const icon = document.createElement("ha-icon");
  icon.icon = name;
  return icon;
}

// ha-icon draws its glyph at --mdc-icon-size; the box follows it.
function sizeIcon(icon, px) {
  icon.style.setProperty("--mdc-icon-size", `${Number(px)}px`);
  icon.style.width = `${Number(px)}px`;
  icon.style.height = `${Number(px)}px`;
}

function isBound(field) {
  return field !== null && typeof field === "object" && !Array.isArray(field) && Object.hasOwn(field, "s");
}

function normalizeCard(compiled, options) {
  const layoutShape = Array.isArray(compiled?.w);
  const rawRect = layoutShape ? compiled.r : [0, 0, compiled.w, compiled.h];
  const origin = options.origin || (layoutShape ? [rawRect[0], rawRect[1]] : [0, 0]);
  const widgets = layoutShape ? compiled.w : compiled.widgets || [];
  // A device layout names the header by hr, icon and title.
  const header =
    compiled.header ||
    (Array.isArray(compiled.hr) ? { r: compiled.hr, icon: compiled.icon, title: compiled.title } : undefined);

  return {
    width: layoutShape ? rawRect[2] : compiled.w,
    height: layoutShape ? rawRect[3] : compiled.h,
    origin,
    widgets,
    header,
    on: compiled.on,
    lit: compiled.lit,
    tint: compiled.tint,
    un: compiled.un,
    ic: compiled.ic,
    tap: compiled.tap,
    hold: compiled.hold,
    confirm: compiled.confirm,
    layoutShape,
  };
}

function localRect(rect, origin, sx, sy) {
  return mapRect(
    [rect[0] - origin[0], rect[1] - origin[1], rect[2], rect[3]],
    sx,
    sy,
  );
}

// What displayValue gives for no value, so a widget can be dimmed.
const NO_VALUE = Symbol("no value");

function hasNoValue(bound, state, feedback) {
  return displayValue(bound, state, feedback, NO_VALUE) === NO_VALUE;
}

// A switch, slider, thermostat, chart or image without a value is drawn at
// 40% and does not react to touch, as on the tablet (contract 4.7). Returns
// whether the value is missing: the class stops the pointer only, so a
// switch and a slider also turn the keyboard away.
function markNoValue(element, bound, state, feedback) {
  const none = hasNoValue(bound, state, feedback);
  element.classList.toggle("at-none", none);
  return none;
}

function displayValue(bound, state, feedback, fallback = "–") {
  if (feedback?.phase === "pending" && feedback.value !== undefined) {
    return feedback.value;
  }
  if (
    bound &&
    typeof bound === "object" &&
    Object.hasOwn(bound, "s") &&
    Object.hasOwn(state.errors || {}, String(bound.s))
  ) {
    return fallback;
  }
  const value = resolveBound(bound, state.values || {});
  return value === undefined || value === null ? fallback : value;
}

// A colour field as 0xRRGGBB, or null for no colour. A bound one may name
// the card's roles ("good", "warn" and so on).
function colourField(field, state) {
  if (field === undefined || field === null) {
    return null;
  }
  if (isBound(field)) {
    if (Object.hasOwn(state.errors || {}, String(field.s))) {
      return null;
    }
    return toColour((state.values || {})[String(field.s)], field.roles || null);
  }
  return toColour(field);
}

// A field that counts as a number: a constant, or a slot's value. null
// without one.
function numberField(field, state, fallback = null) {
  const value = isBound(field) ? displayValue(field, state, null, null) : field;
  return toNumber(value, fallback);
}

// The age of a slot in seconds (contract 4.4): the card in a browser
// counts it; the editor's picture shows the value as sent, age 0.
function ageOf(field, state) {
  if (!isBound(field) || typeof state.age !== "function") {
    return 0;
  }
  return Math.max(0, Number(state.age(String(field.s))) || 0);
}

function waitingTitle(widget, feedback) {
  const progress =
    widget.tap?.policy === "progress" || widget.change?.policy === "progress";
  return feedback.phase === "pending" && progress ? t("card.waiting") : "";
}

function keyFor(widget) {
  return widget.i ?? widget.id;
}

function feedbackFor(state, widget) {
  return state.feedback?.get?.(keyFor(widget)) || {
    phase: "idle",
    value: undefined,
    until: 0,
  };
}

// The theme and style colours of a card as numbers, with the defaults
// where they have none.
function numberTokens(tokens = {}) {
  const out = { ...DEFAULT_TOKENS };
  for (const [key, value] of Object.entries(tokens)) {
    const colour = colourOf(value);
    if (colour !== null) {
      out[key] = colour;
    }
  }
  if (!isHex(tokens.bg) && isHex(tokens.card)) {
    out.bg = colourOf(tokens.card);
  }
  out.bw = Number.isFinite(Number(tokens.bw)) ? Number(tokens.bw) : 0;
  out.r2 = Number.isFinite(Number(tokens.r2)) ? Number(tokens.r2) : 10;
  return out;
}

export function cardTokens(theme = {}, style = {}) {
  const tokens = { ...theme, ...style };

  // The theme's ion and onbg_pr suit its own "on" fill. A style that changes
  // that fill (a custom colour, an accent, another theme) gets its own
  // (contract 4.7), unless it brings its own.
  if (
    isHex(style.onbg) &&
    isHex(theme.onbg) &&
    style.onbg.toLowerCase() !== theme.onbg.toLowerCase()
  ) {
    const onbg = colourOf(style.onbg);
    if (!isHex(style.ion)) {
      tokens.ion =
        isHex(tokens.acc) && contrastOf(colourOf(tokens.acc), onbg) >= 3
          ? tokens.acc
          : tokens.ontx;
    }
    if (isHex(style.onbg_pr)) {
      tokens.onbg_pr = style.onbg_pr;
    } else if (isHex(tokens.ontx)) {
      tokens.onbg_pr = hexOf(blendOf(colourOf(tokens.ontx), onbg, 0.82));
    } else {
      delete tokens.onbg_pr;
    }
  }

  return tokens;
}

export function applyTokens(element, tokens = {}) {
  // A missing colour falls back to the parent's value or the CSS default.
  for (const name of COLOR_TOKENS) {
    const value = tokens[name];
    if (isHex(value)) {
      element.style.setProperty(`--at-${name}`, value);
    } else {
      element.style.removeProperty(`--at-${name}`);
    }
  }

  for (const name of NUMBER_TOKENS) {
    const value = Number(tokens[name]);
    if (Number.isFinite(value)) {
      element.style.setProperty(`--at-${name}`, `${value}px`);
    }
  }

  if (tokens.gd === "v" || tokens.gd === "h") {
    element.dataset.gradient = tokens.gd;
  } else {
    delete element.dataset.gradient;
  }
}

// What a card looks like now (contract 4.7, "Card colours"): its nine
// colours, whether it is filled or lit, and the background and text
// colour every widget rule reads.
function cardLook(normalized, state) {
  const tokens = numberTokens(state.tokens || {});
  const values = state.values || {};
  const on = isOn(state.cardOn !== undefined ? state.cardOn : resolveBound(normalized.on, values));
  const rawLit = toNumber(resolveBound(normalized.lit, values), 0);
  const lit = Math.min(3, Math.max(0, Math.round(rawLit)));
  const tint = colourField(normalized.tint, state);
  const colours = cardColours(tokens, on, lit, tint);
  const filled = Boolean(colours.filled);
  return {
    tokens,
    colours,
    on,
    lit,
    tint,
    filled,
    litOn: on && (lit === 1 || lit === 2),
    un: isOn(resolveBound(normalized.un, values)),
    bg: colours.background,
    tx: colours.text,
    // Small text: tx2, on a filled card the small text colour of the fill.
    small: filled ? colours.FS : tokens.tx2,
    // A track or the pressed look on the card's background now.
    track: filled ? colours.FP : tokens.card2,
  };
}

// The width of one character in the tablet's font at a text size, or null
// while that cannot be measured (the font is not loaded, or no canvas).
const tabletMeasures = new Map();
function tabletAdvance(px) {
  if (!tabletFontReady || typeof document === "undefined") {
    return null;
  }
  let measure = tabletMeasures.get(px);
  if (measure === undefined) {
    measure = null;
    try {
      const context = document.createElement("canvas").getContext?.("2d");
      if (context) {
        context.font = `500 ${px}px "${TABLET_FONT_FAMILY}"`;
        const known = new Map();
        measure = (ch) => {
          let width = known.get(ch);
          if (width === undefined) {
            width = context.measureText(ch).width;
            known.set(ch, width);
          }
          return width;
        };
      }
    } catch (_error) {
      measure = null;
    }
    tabletMeasures.set(px, measure);
  }
  return measure;
}

// The width the tablet gives a text at px, or null while it cannot be
// measured.
function tabletTextWidth(text, px) {
  const advance = tabletAdvance(px);
  if (!advance) {
    return null;
  }
  let total = 0;
  for (const [, width] of tabletCharWidths(tabletText(text), px, advance)) {
    total += width;
  }
  return total;
}

// Puts one line of text into its element. In the tablet preview the line is
// cut where the tablet cuts it (logic.js tabletFit: whole-pixel widths, in
// tablet pixels whatever the preview's size), and a character the tablet
// lacks is the tablet's box: a line high and as wide as the room the tablet
// gives it (half a line plus 2 px), because LVGL draws that box's 1 px
// border across the whole room. `px` and `width` are the tablet's text size
// and box width; `ellipsis` is what ends a cut line. Until the tablet's font
// can be measured, the browser cuts the line itself.
function setLineText(element, value, options, px, width, scale, ellipsis = TABLET_ELLIPSIS) {
  const text = String(value);
  if (!options?.tablet) {
    element.textContent = text;
    return;
  }
  const advance = tabletAdvance(px);
  if (!advance) {
    element.textContent = tabletText(text);
    if (tabletFontPending()) {
      tabletFontWaiting.set(element, () => setLineText(element, value, options, px, width, scale, ellipsis));
    }
    return;
  }
  const line = tabletFit(text, width, px, advance, ellipsis);
  element.classList.add("at-fitted");
  // Each character in a box of the tablet's whole-pixel width, so the line
  // is exactly as wide as on the tablet and its end is never cut off.
  const nodes = [];
  for (const [ch, chWidth] of tabletCharWidths(line, px, advance)) {
    if (ch === TABLET_MISSING_GLYPH) {
      const box = html("span", "at-nobox");
      box.style.width = `${chWidth * scale}px`;
      box.style.height = `${tabletLineHeight(px) * scale}px`;
      nodes.push(box);
      continue;
    }
    const glyph = html("span", "at-ch");
    glyph.textContent = ch;
    glyph.style.width = `${chWidth * scale}px`;
    nodes.push(glyph);
  }
  element.replaceChildren(...nodes);
}

// Marks who gets a press that begins on a widget (contract 4.3, "Who gets
// a press"): "own" when the widget takes taps itself, so the card does not;
// a hold is the widget's ("own"), nobody's ("none") or else the card's.
function markPress(element, widget) {
  if (widget.tap || (widget.change && widget.t !== "thermostat")) {
    element.dataset.press = "own";
  }
  if (widget.hold) {
    element.dataset.hold = "own";
  } else if (widget.change && (widget.t === "slider" || widget.t === "choice")) {
    element.dataset.hold = "none";
  }
}

// vis (contract 4.3): 0 or no value hides the widget, and it takes no press.
function patchVisible(element, widget, state) {
  if (widget.vis === undefined) {
    return true;
  }
  const shown = isOn(isBound(widget.vis) ? displayValue(widget.vis, state, null, null) : widget.vis);
  element.classList.toggle("at-hidden", !shown);
  return shown;
}

function makeHeader(card, normalized, sx, sy, scale, options, patches) {
  if (!normalized.header?.r) {
    return;
  }

  const header = html("div", "at-header");
  setRect(header, localRect(normalized.header.r, normalized.origin, sx, sy));
  header.style.gap = `${8 * scale}px`;

  const title = html("span", "at-header-title");
  title.style.fontSize = `${16 * scale}px`;
  header.append(title);
  card.append(header);

  let icon = null;
  let shownIcon;
  patches.push((state, look) => {
    // ic replaces the icon while it has a value that is an icon (4.3).
    const own = normalized.ic === undefined ? null : displayValue(normalized.ic, state, null, null);
    const name = normalized.header.icon ? (isIcon(own) ? own : normalized.header.icon) : null;
    if (name !== shownIcon) {
      shownIcon = name;
      icon?.remove();
      icon = iconElement(name);
      if (icon) {
        sizeIcon(icon, 24 * scale);
        header.prepend(icon);
      }
    }
    if (icon && look) {
      icon.style.color = hexOf(look.filled ? look.colours.FI : look.litOn ? look.colours.A : look.tokens.tx2);
    }
    const room = normalized.header.r[2] - (icon ? 32 : 0);
    setLineText(title, displayValue(normalized.header.title, state, null), options, 16, room, scale);
  });
}

// size as the layout names it: "s", "m", "l" or 0, 1, 2.
function labelSizeIndex(size) {
  if (size === "s" || size === 0) {
    return 0;
  }
  if (size === "l" || size === 2) {
    return 2;
  }
  return 1;
}

const ALIGN = ["flex-start", "center", "flex-end"];

function makeLabel(card, widget, rect, scale, options, patches) {
  const sizeIndex = labelSizeIndex(widget.size);
  const sizeName = ["s", "m", "l"][sizeIndex];
  const label = html("div", `at-label at-label-${sizeName}`);
  setRect(label, rect);
  markPress(label, widget);
  const fixed = widget.px === undefined && !widget.clk;
  const fontSize = [14, 18, 34][sizeIndex];
  label.style.fontSize = `${fontSize * scale}px`;
  const align = Math.min(2, Math.max(0, Math.round(toNumber(widget.al, 0))));
  if (align) {
    label.style.justifyContent = ALIGN[align];
  }
  // Ellipsis needs a block box, which a flex container's text is not.
  const text = html("span", "at-text");
  label.append(text);
  card.append(label);
  const [, , boxWidth = 0, boxHeight = 0] = Array.isArray(widget.r) ? widget.r : [];

  patches.push((state, look) => {
    if (!patchVisible(label, widget, state)) {
      return;
    }
    const clock = widget.clk === 1 || widget.clk === 2;
    let value;
    if (clock) {
      const minutes = numberField(widget.value, state);
      value = clockText(minutes, ageOf(widget.value, state), widget.clk);
    } else {
      value = displayValue(widget.text, state, null);
    }
    let px = fontSize;
    let small = sizeIndex === 0;
    if (!fixed) {
      const wanted = widget.px === undefined ? null : toNumber(widget.px, null);
      const widthAt = options.tablet ? (size) => tabletTextWidth(value, size) : null;
      const chosen = tabletLabelSize(wanted, String(value), boxWidth, widthAt, sizeIndex);
      px = chosen.px;
      small = Boolean(chosen.small);
      label.style.fontSize = `${px * scale}px`;
      label.classList.toggle("at-label-s", small);
      label.classList.toggle("at-label-m", !small && px < 34);
      label.classList.toggle("at-label-l", !small && px >= 34);
    }
    // A line higher than its box starts at the box's top (4.7).
    label.classList.toggle("at-tall", tabletLineHeight(px) > boxHeight);
    const colour = colourField(widget.c, state);
    if (look && colour !== null) {
      label.style.color = hexOf(legible(colour, look.bg, look.tx));
    } else if (look && (look.tint !== null || !fixed)) {
      label.style.color = hexOf(small ? look.small : look.tx);
    } else {
      label.style.removeProperty("color");
    }
    setLineText(text, value, options, px, boxWidth, scale);
  });
}

// The icon of a button or a choice's cell: its own, or `ic` while that has
// an icon for a value.
function buttonIconName(widget, state) {
  const own = widget.ic === undefined ? null : displayValue(widget.ic, state, null, null);
  return isIcon(own) ? own : widget.icon;
}

function makeButton(card, widget, rect, scale, options, patches) {
  const button = html("button", "at-button");
  button.type = "button";
  markPress(button, widget);
  const shape = Math.min(2, Math.max(0, Math.round(toNumber(widget.shape, 0))));
  const [, , wide = 0, high = 0] = Array.isArray(widget.r) ? widget.r : [];
  if (shape === 1) {
    // A circle of diameter min(w, h), centred in the rectangle; no text.
    const d = Math.min(rect[2], rect[3]);
    setRect(button, [rect[0] + (rect[2] - d) / 2, rect[1] + (rect[3] - d) / 2, d, d]);
    button.classList.add("round");
  } else {
    setRect(button, rect);
  }
  if (shape === 2) {
    button.classList.add("bare");
  }
  button.style.fontSize = `${15 * scale}px`;
  const iconPx = widget.isz === 1 ? largestIcon(Math.min(wide, high) / 2) : 24;
  const hasText = widget.text !== undefined && shape !== 1;

  const text = html("span", "at-button-text");
  let icon = null;
  let shownIcon;
  const placeIcon = (name) => {
    if (name === shownIcon) {
      return;
    }
    shownIcon = name;
    icon?.remove();
    icon = iconElement(name);
    if (icon) {
      sizeIcon(icon, iconPx * scale);
      button.prepend(icon);
    }
    button.classList.toggle("vertical", Boolean(icon) && hasText && rect[3] >= 64 * scale);
  };
  placeIcon(widget.icon);
  if (hasText) {
    button.append(text);
  }

  if (options.interactive && widget.tap) {
    button.addEventListener("click", () => options.onTap?.(widget));
  } else {
    button.disabled = true;
  }

  card.append(button);
  patches.push((state, look) => {
    if (!patchVisible(button, widget, state)) {
      return;
    }
    placeIcon(buttonIconName(widget, state));
    const value = hasText ? displayValue(widget.text, state, null) : "";
    // The tablet's room for a button's words: 6 px each side, and beside an
    // icon (not below one) the icon and 6 px more.
    const beside = icon && high < 64;
    setLineText(text, value, options, 15, wide - 12 - (beside ? iconPx + 6 : 0), scale);
    button.setAttribute("aria-label", String(value || widget.icon || ""));
    const feedback = feedbackFor(state, widget);
    button.title = waitingTitle(widget, feedback);
    button.classList.toggle("active", feedback.phase === "pulse");
    button.classList.toggle(
      "busy",
      feedback.phase === "pending" || feedback.phase === "busy",
    );
    const selected = widget.value !== undefined && isOn(displayValue(widget.value, state, feedback, null));
    button.classList.toggle("selected", selected);
    if (widget.value !== undefined) {
      button.setAttribute("aria-pressed", String(selected));
    }
    if (!look) {
      return;
    }
    const swatch = colourField(widget.c, state);
    const { colours } = look;
    let fill = null;
    let ink = null;
    let ring = "";
    if (swatch !== null) {
      fill = swatch;
      ink = readable(swatch);
      if (selected) {
        ring = `inset 0 0 0 ${3 * scale}px ${hexOf(look.tx)}`;
      }
    } else if (selected) {
      fill = colours.AF;
      ink = colours.AT;
      if (contrastOf(colours.AF, look.bg) < 1.3) {
        ring = `inset 0 0 0 ${2 * scale}px ${hexOf(colours.AT)}`;
      }
    }
    button.classList.toggle("swatch", swatch !== null);
    // Pressed: with c mix(readable(c), c, 85), selected accf_pr, else the
    // card's --at-wpr.
    if (swatch !== null) {
      button.style.setProperty("--at-bpr", hexOf(mix(readable(swatch), swatch, 85)));
    } else if (selected) {
      button.style.setProperty("--at-bpr", hexOf(colours.AP));
    } else {
      button.style.removeProperty("--at-bpr");
    }
    if (fill !== null) {
      button.style.background = hexOf(fill);
      button.style.color = hexOf(ink);
    } else {
      button.style.removeProperty("background");
      button.style.removeProperty("color");
    }
    if (ring) {
      button.style.boxShadow = ring;
    } else {
      button.style.removeProperty("box-shadow");
    }
  });
}

function makeSwitch(card, widget, rect, scale, options, patches) {
  const button = html("button", "at-switch");
  button.type = "button";
  button.setAttribute("role", "switch");
  markPress(button, widget);
  const width = Math.min(rect[2], 64 * scale);
  const height = Math.min(rect[3], 36 * scale);
  setRect(button, [
    rect[0],
    rect[1] + (rect[3] - height) / 2,
    width,
    height,
  ]);

  const knob = html("span", "at-switch-knob");
  knob.style.width = `${28 * scale}px`;
  knob.style.height = `${28 * scale}px`;
  button.append(knob);

  const live = Boolean(options.interactive && widget.tap);
  if (live) {
    button.addEventListener("click", () => options.onTap?.(widget));
  } else {
    button.disabled = true;
  }

  card.append(button);
  patches.push((state, look) => {
    if (!patchVisible(button, widget, state)) {
      return;
    }
    const feedback = feedbackFor(state, widget);
    const value = displayValue(widget.value, state, feedback);
    // Enter and Space press a button too, so without a value it is disabled.
    button.disabled = markNoValue(button, widget.value, state, feedback) || !live;
    const on = isOn(value);
    button.classList.toggle("on", on);
    button.classList.toggle(
      "busy",
      feedback.phase === "pending" || feedback.phase === "busy",
    );
    button.setAttribute("aria-checked", String(on));
    button.title = waitingTitle(widget, feedback);
    // c: the track at value 1, and the knob readable on it (4.7).
    const own = colourField(widget.c, state);
    if (look && own !== null && on) {
      const trackColour = legible(own, look.bg, look.tx);
      button.style.background = hexOf(trackColour);
      knob.style.background = hexOf(readable(trackColour));
    } else {
      button.style.removeProperty("background");
      knob.style.removeProperty("background");
    }
  });
}

// Places a part of a slider given along its axis (a0 to a1 from the start
// edge) and across it (c0 to c1), in tablet pixels, inside the slider's
// box. L is the length along the axis.
function placeAlong(element, dir, length, a0, a1, c0, c1, sx, sy) {
  if (dir === 1) {
    setRect(element, [c0 * sx, (length - a1) * sy, (c1 - c0) * sx, (a1 - a0) * sy]);
  } else if (dir === 2) {
    setRect(element, [c0 * sx, a0 * sy, (c1 - c0) * sx, (a1 - a0) * sy]);
  } else {
    setRect(element, [a0 * sx, c0 * sy, (a1 - a0) * sx, (c1 - c0) * sy]);
  }
}

const TRACK_TOWARD = ["to right", "to top", "to bottom"];

// A track of colours as one picture: the start cap in the first colour,
// the end cap in the last, and between them the pieces of trackPieces,
// each fading from one colour to the next (contract 4.7, "Slider, track").
function trackGradient(colours, geometry, dir, along) {
  const stops = [`${colours[0]} 0px`, `${colours[0]} ${geometry.caps[0][1] * along}px`];
  geometry.pieces.forEach((piece, index) => {
    stops.push(`${colours[index]} ${piece[0] * along}px`, `${colours[index + 1]} ${piece[1] * along}px`);
  });
  const last = colours.at(-1);
  stops.push(`${last} ${geometry.caps[1][0] * along}px`, `${last} ${geometry.L * along}px`);
  return `linear-gradient(${TRACK_TOWARD[dir] || TRACK_TOWARD[0]}, ${stops.join(", ")})`;
}

function makeSlider(card, widget, rect, scale, options, patches, sx, sy) {
  const slider = html("div", "at-slider");
  const live = Boolean(options.interactive && widget.change);
  const look = Math.min(1, Math.max(0, Math.round(toNumber(widget.look, 0))));
  const dir = Math.min(2, Math.max(0, Math.round(toNumber(widget.dir, 0))));
  const colours = (Array.isArray(widget.track) ? widget.track : [])
    .map((value) => toColour(value))
    .filter((value) => value !== null)
    .slice(0, 8)
    .map(hexOf);
  const track = colours.length >= 2 ? colours.length : 0;
  const tabletRect = Array.isArray(widget.r) ? widget.r : [0, 0, rect[2] / sx, rect[3] / sy];
  const along = dir === 0 ? sx : sy;
  slider.tabIndex = live ? 0 : -1;
  slider.setAttribute("role", "slider");
  if (dir) {
    slider.setAttribute("aria-orientation", "vertical");
  }
  slider.classList.add(look === 1 ? "bar" : "knob");
  slider.classList.toggle("tracked", Boolean(track));
  markPress(slider, widget);
  setRect(slider, rect);

  const trackEl = html("div", "at-slider-track");
  const fill = html("div", "at-slider-fill");
  const knob = html("div", "at-slider-knob");
  const handle = html("div", "at-slider-handle");
  const mark = html("div", "at-slider-mark");
  slider.append(trackEl);
  let icon = null;
  if (track) {
    slider.append(mark);
  } else if (look === 1) {
    slider.append(fill, handle);
    icon = iconElement(widget.icon);
    if (icon) {
      icon.classList.add("at-slider-icon");
      sizeIcon(icon, 24 * scale);
      slider.append(icon);
    }
  } else {
    slider.append(fill, knob);
  }
  card.append(slider);

  const [length, side] = [dir === 0 ? tabletRect[2] : tabletRect[3], dir === 0 ? tabletRect[3] : tabletRect[2]];
  let dragging = false;
  let dragValue;
  let currentState = null;
  let currentLook = null;

  const limits = () => {
    const min = numberField(widget.min, currentState || {}, 0);
    const max = numberField(widget.max, currentState || {}, 100);
    const step = numberField(widget.step, currentState || {}, 1);
    return { min, max, step };
  };
  const radius = () => Number(currentLook?.tokens.r2 ?? 10);

  const valueFromPointer = (event) => {
    const bounds = slider.getBoundingClientRect();
    const w = bounds.width || rect[2];
    const h = bounds.height || rect[3];
    // The pointer in tablet pixels, from the slider's own corner.
    const x = ((event.clientX - bounds.left) / w) * tabletRect[2];
    const y = ((event.clientY - bounds.top) / h) * tabletRect[3];
    const box = [0, 0, tabletRect[2], tabletRect[3]];
    const amount = sliderAmount(box, look, dir, track, radius(), x, y);
    const { min, max, step } = limits();
    return sliderValue(amount, min, max, step, sliderLength(box, look, dir, track, radius()));
  };

  if (live) {
    slider.addEventListener("pointerdown", (event) => {
      const value = valueFromPointer(event);
      if (value === null) {
        return;
      }
      dragging = true;
      options.onDrag?.(true);
      slider.setPointerCapture?.(event.pointerId);
      dragValue = value;
      options.onChange?.(widget, dragValue, false);
      patch(currentState, currentLook);
    });

    slider.addEventListener("pointermove", (event) => {
      if (!dragging) {
        return;
      }
      const value = valueFromPointer(event);
      if (value === null) {
        return;
      }
      dragValue = value;
      options.onChange?.(widget, dragValue, false);
      patch(currentState, currentLook);
    });

    const finish = (event) => {
      if (!dragging) {
        return;
      }
      dragging = false;
      options.onDrag?.(false);
      if (slider.hasPointerCapture?.(event.pointerId)) {
        slider.releasePointerCapture(event.pointerId);
      }
      options.onChange?.(widget, dragValue, true);
      patch(currentState, currentLook);
    };

    slider.addEventListener("pointerup", finish);
    slider.addEventListener("pointercancel", finish);
    slider.addEventListener("keydown", (event) => {
      const keys = dir === 2 ? ["ArrowLeft", "ArrowUp", "ArrowRight", "ArrowDown"] : ["ArrowLeft", "ArrowDown", "ArrowRight", "ArrowUp"];
      if (!keys.includes(event.key)) {
        return;
      }
      // Without a value there is nothing to step from, and the key is left
      // to the page. A slider with nv 1 steps from its lowest value.
      const nv = widget.nv === 1;
      if (!nv && currentState && hasNoValue(widget.value, currentState, feedbackFor(currentState, widget))) {
        return;
      }
      event.preventDefault();
      if (!currentState) {
        return;
      }
      const { min, max, step } = limits();
      if (!(max > min)) {
        return;
      }
      // Step from the value on screen, which may still be waiting for the server.
      const current = toNumber(
        displayValue(widget.value, currentState, feedbackFor(currentState, widget), null),
        min,
      );
      const direction = event.key === keys[2] || event.key === keys[3] ? 1 : -1;
      const next = clampStep(current + direction * (step > 0 ? step : 1), min, max, step);
      options.onChange?.(widget, next, true);
    });
  }

  function patch(state, cardState) {
    if (!state) {
      return;
    }
    currentState = state;
    currentLook = cardState || currentLook;
    if (!patchVisible(slider, widget, state)) {
      return;
    }
    const feedback = feedbackFor(state, widget);
    const { min, max } = limits();
    const raw = dragging ? dragValue : displayValue(widget.value, state, feedback, null);
    let value = raw === null ? null : toNumber(raw, null);
    // rate: a slider without change moves by itself, from the last write
    // of its value (4.7). The picture shows the value as sent.
    if (value !== null && !widget.change && widget.rate !== undefined) {
      const rate = numberField(widget.rate, state, 0) || 0;
      value = Math.min(max, Math.max(min, value + rate * ageOf(widget.value, state)));
    }
    const nv = widget.nv === 1;
    const none = value === null;
    if (!dragging) {
      // Without a value the keyboard does not reach it either, unless nv.
      const faded = none && !nv && markNoValue(slider, widget.value, state, feedback);
      if (nv) {
        slider.classList.remove("at-none");
      }
      slider.tabIndex = live && !faded ? 0 : -1;
      if (faded) {
        slider.setAttribute("aria-disabled", "true");
      } else {
        slider.removeAttribute("aria-disabled");
      }
    }
    const box = [0, 0, tabletRect[2], tabletRect[3]];
    const geometry = sliderGeometry(box, look, dir, track, radius(), value, min, max, Boolean(widget.change));
    const lookNow = currentLook;
    const trackColour = lookNow ? lookNow.track : DEFAULT_TOKENS.card2;
    const own = colourField(widget.c, state);
    let fillColour = null;
    if (lookNow) {
      fillColour = own !== null ? legible(own, trackColour, lookNow.tx) : lookNow.filled ? lookNow.colours.FI : lookNow.colours.A;
    }
    // Only an empty nv slider hides its fill, knob, handle and mark.
    const bare = none && nv;

    if (track) {
      const R = geometry.R;
      const thick = look === 1 ? side : Math.min(side, 14);
      const across = (side - thick) / 2;
      placeAlong(trackEl, dir, length, 0, length, across, across + thick, sx, sy);
      trackEl.style.borderRadius = `${R * scale}px`;
      trackEl.style.background = trackGradient(colours, geometry, dir, along);
      mark.hidden = bare || geometry.mark === null;
      if (geometry.mark !== null) {
        if (look === 1) {
          placeAlong(mark, dir, length, geometry.mark - 6, geometry.mark + 6, -2, side + 2, sx, sy);
          mark.style.borderRadius = `${6 * scale}px`;
        } else {
          placeAlong(mark, dir, length, geometry.mark - 11, geometry.mark + 11, side / 2 - 11, side / 2 + 11, sx, sy);
          mark.style.borderRadius = "50%";
        }
        mark.style.borderWidth = `${2 * scale}px`;
        mark.style.background = hexOf(TABLET_WHITE);
        mark.style.borderColor = hexOf(TABLET_INK);
      }
    } else if (look === 1) {
      const R = geometry.R;
      placeAlong(trackEl, dir, length, 0, length, 0, side, sx, sy);
      trackEl.style.borderRadius = `${R * scale}px`;
      trackEl.style.background = hexOf(trackColour);
      fill.hidden = bare || geometry.drawn <= 0;
      placeAlong(fill, dir, length, 0, geometry.drawn, 0, side, sx, sy);
      fill.style.borderRadius = `${R * scale}px`;
      if (fillColour !== null) {
        fill.style.background = hexOf(fillColour);
      }
      handle.hidden = bare || !geometry.handle;
      if (geometry.handle) {
        placeAlong(handle, dir, length, geometry.handle[0], geometry.handle[1], 8, side - 8, sx, sy);
        handle.style.borderRadius = `${2 * scale}px`;
        if (fillColour !== null) {
          handle.style.background = hexOf(readable(fillColour));
        }
      }
      if (icon) {
        icon.hidden = geometry.icon_centre === null;
        placeAlong(icon, dir, length, 12, 36, side / 2 - 12, side / 2 + 12, sx, sy);
        if (lookNow && fillColour !== null) {
          icon.style.color = hexOf(geometry.icon_on_fill ? readable(fillColour) : lookNow.filled ? lookNow.colours.FT : lookNow.tokens.tx2);
        }
      }
    } else {
      // The knob slider: a track 14 thick, radius 7, centred across.
      const thick = Math.min(side, 14);
      const across = (side - thick) / 2;
      placeAlong(trackEl, dir, length, 0, length, across, across + thick, sx, sy);
      trackEl.style.borderRadius = `${7 * scale}px`;
      if (lookNow) {
        trackEl.style.background = hexOf(trackColour);
      }
      const at = geometry.knob === null ? 0 : geometry.knob;
      fill.hidden = bare || geometry.knob === null;
      placeAlong(fill, dir, length, 0, at, across, across + thick, sx, sy);
      fill.style.borderRadius = `${7 * scale}px`;
      if (fillColour !== null) {
        fill.style.background = hexOf(fillColour);
      }
      knob.hidden = bare || (geometry.knob === null && !none);
      placeAlong(knob, dir, length, at - 11, at + 11, side / 2 - 11, side / 2 + 11, sx, sy);
      if (lookNow?.filled) {
        knob.style.background = hexOf(lookNow.colours.FT);
        knob.style.boxShadow = `0 0 0 ${2 * scale}px ${hexOf(lookNow.colours.F)}`;
      } else {
        knob.style.removeProperty("background");
        knob.style.removeProperty("box-shadow");
      }
    }
    slider.setAttribute("aria-valuemin", String(min));
    slider.setAttribute("aria-valuemax", String(max));
    slider.setAttribute("aria-valuenow", String(value === null ? min : value));
    slider.title = waitingTitle(widget, feedback);
  }

  patches.push(patch);
}

// The thermostat's text: no decimals from 1000 up, otherwise at most one.
export function thermostatText(value) {
  const rounded =
    Math.abs(value) >= 1000
      ? Math.round(value)
      : Math.round(value * 10) / 10;
  return Object.is(rounded, -0) ? "0" : String(rounded);
}

// Font size that keeps the value inside the arc's inner circle. size is the
// side of the square the arc is drawn in, stroke is in viewBox units. Each
// character is guessed wide (0.62 em) so the estimate errs on the small side.
export function thermostatFit(text, size, stroke) {
  const innerDiameter = 2 * (72 - stroke / 2) * size / 200;
  const maxWidth = 0.8 * innerDiameter;
  let em = 0;
  for (const character of String(text)) {
    em += ".,: ".includes(character) ? 0.32 : 0.62;
  }
  const fontSize = Math.min(size / 5, em > 0 ? maxWidth / em : size / 5);
  return { fontSize, maxWidth, innerDiameter };
}

// The thermostat value's size on the tablet (contract 4.7). First the
// largest of 48, 34, 20, 18 and 14 that is not above thermostatFit; 48 only
// for text of 0123456789.,- (the tablet's digits font), so the "–" for no
// value is 34 at most. thermostatFit counts 0.62 em a digit, but
// Montserrat's digits are up to 0.67 em, so the text can still be wider
// than its box: then the next smaller size, until it fits or the size is
// 14, the only size that is ever cut. side is min(w, h) in tablet pixels.
// advanceFor(px) gives the width of one character of the tablet's font at
// px (whole pixels are taken, as the tablet adds them), or null while it
// cannot be measured; without it the size stays at the first pick. The
// same rule as the engine's thermostat_font.
const TABLET_THERMOSTAT_SIZES = [48, 34, 20, 18, 14];

export function tabletThermostatSize(text, side, advanceFor = null) {
  const value = String(text);
  const fit = thermostatFit(value, side, Math.max(8, side / 14)).fontSize;
  const digits = /^[0-9.,-]*$/.test(value);
  let index = TABLET_THERMOSTAT_SIZES.findIndex((size) => size <= fit && (digits || size < 48));
  if (index < 0) {
    index = TABLET_THERMOSTAT_SIZES.length - 1;
  }
  const room = tabletThermostatTextWidth(side);
  while (index < TABLET_THERMOSTAT_SIZES.length - 1) {
    const px = TABLET_THERMOSTAT_SIZES[index];
    const advance = advanceFor?.(px);
    if (!advance) {
      break;
    }
    let drawn = 0;
    for (const [, width] of tabletCharWidths(tabletText(value), px, advance)) {
      drawn += width;
    }
    if (drawn <= room) {
      break;
    }
    index += 1;
  }
  return TABLET_THERMOSTAT_SIZES[index];
}

// The width of the box the tablet draws the thermostat value in, in whole
// pixels: thermostatFit's maxWidth, cut to an integer. The same sum in the
// same order as the engine's thermostat_text_width, so both round alike.
export function tabletThermostatTextWidth(side) {
  const stroke = Math.max(8, side / 14);
  return Math.trunc((0.8 * 2 * (72 - stroke / 2) * side) / 200);
}

function makeThermostat(card, widget, rect, scale, options, patches) {
  const wrap = html("div", "at-thermostat");
  setRect(wrap, rect);
  const size = Math.min(rect[2], rect[3]);
  // The same side in tablet pixels, as the tablet takes it: min(w, h).
  const side = Math.min(widget.r[2], widget.r[3]);
  const viewSize = 200;

  const graphic = svg("svg");
  graphic.setAttribute("viewBox", `0 0 ${viewSize} ${viewSize}`);
  const track = svg("path");
  const valueArc = svg("path");
  const dot = svg("circle");
  track.setAttribute("class", "at-arc-track");
  valueArc.setAttribute("class", "at-arc-value");
  dot.setAttribute("class", "at-arc-mark");
  const stroke = Math.max(8, size / scale / 14);
  track.setAttribute("stroke-width", String(stroke));
  valueArc.setAttribute("stroke-width", String(stroke));
  track.setAttribute("d", arcPath(100, 100, 72, 135, 405));
  graphic.append(track, valueArc);
  if (widget.mark !== undefined) {
    graphic.append(dot);
  }

  // The text sits in its own span so its drawn width can be measured.
  const text = html("div", "at-thermostat-value");
  const textSpan = html("span", "at-thermostat-text");
  textSpan.style.whiteSpace = "nowrap";
  textSpan.style.lineHeight = "1.2";
  text.append(textSpan);
  wrap.append(graphic, text);

  // bs: the side of the minus and plus buttons, 36 to 64 (4.3).
  const buttonSide = Math.min(64, Math.max(36, Math.round(toNumber(widget.bs, 36))));
  if (widget.change) {
    for (const [direction, iconName] of [
      [-1, "mdi:minus"],
      [1, "mdi:plus"],
    ]) {
      const button = html("button", direction < 0 ? "minus" : "plus");
      button.type = "button";
      button.dataset.press = "own";
      button.dataset.hold = "none";
      if (buttonSide !== 36) {
        button.style.width = `${buttonSide * scale}px`;
        button.style.height = `${buttonSide * scale}px`;
      }
      const icon = iconElement(iconName);
      if (icon) {
        sizeIcon(icon, 24 * scale);
        button.append(icon);
      }
      button.disabled = !options.interactive;
      button.addEventListener("click", () => {
        const state = wrap.__state;
        if (!state) {
          return;
        }
        const min = toNumber(resolveBound(widget.min, state.values), 0);
        const max = toNumber(resolveBound(widget.max, state.values), 100);
        const step = toNumber(resolveBound(widget.step, state.values), 1);
        // Step from the value on screen, so quick presses add up. With no
        // reading there is nothing to step from.
        const current = toNumber(
          displayValue(widget.value, state, feedbackFor(state, widget)),
          NaN,
        );
        if (!Number.isFinite(current)) {
          return;
        }
        options.onChange?.(
          widget,
          clampStep(current + direction * (step > 0 ? step : 1), min, max, step),
          true,
        );
      });
      wrap.append(button);
    }
  }

  let lastText;
  // The tablet preview draws the value as the tablet does: at the size
  // tabletThermostatSize steps down to, cut with "…" only at 14 px. Until
  // the tablet's font can be measured the first pick stands; once it is
  // there the size is worked out again, as it may step down.
  const drawTabletValue = (value) => {
    const px = tabletThermostatSize(value, side, tabletAdvance);
    text.style.fontSize = `${px * scale}px`;
    setLineText(textSpan, value, options, px, tabletThermostatTextWidth(side), scale);
    if (tabletFontPending()) {
      tabletFontWaiting.set(textSpan, () => {
        if (lastText === value) {
          drawTabletValue(value);
        }
      });
    }
  };
  card.append(wrap);
  patches.push((state, look) => {
    wrap.__state = state;
    if (!patchVisible(wrap, widget, state)) {
      return;
    }
    const feedback = feedbackFor(state, widget);
    const min = toNumber(resolveBound(widget.min, state.values), 0);
    const max = toNumber(resolveBound(widget.max, state.values), 100);
    const value = toNumber(displayValue(widget.value, state, feedback), NaN);
    markNoValue(wrap, widget.value, state, feedback);
    let nextText;
    if (Number.isFinite(value)) {
      const amount = fraction(value, min, max);
      valueArc.setAttribute("d", arcPath(100, 100, 72, 135, 135 + 270 * amount));
      nextText = thermostatText(value);
    } else {
      valueArc.removeAttribute("d");
      nextText = "–";
    }
    const own = colourField(widget.c, state);
    if (look && own !== null) {
      valueArc.style.stroke = hexOf(legible(own, look.bg, look.tx));
    } else {
      valueArc.style.removeProperty("stroke");
    }
    // mark: a dot on the arc's middle line, also while value has none.
    if (widget.mark !== undefined) {
      const m = numberField(widget.mark, state);
      const shown = m !== null && max > min && m >= min && m <= max;
      dot.style.display = shown ? "" : "none";
      if (shown) {
        const angle = ((135 + (270 * (m - min)) / (max - min)) * Math.PI) / 180;
        const widthPx = (stroke * side) / 200;
        const diameter = Math.max(6, widthPx - 4);
        dot.setAttribute("cx", String(100 + 72 * Math.cos(angle)));
        dot.setAttribute("cy", String(100 + 72 * Math.sin(angle)));
        dot.setAttribute("r", String(((diameter / 2) * 200) / side));
        if (look) {
          dot.style.fill = hexOf(look.tx);
        }
      }
    }
    if (nextText !== lastText) {
      lastText = nextText;
      if (options.tablet) {
        drawTabletValue(nextText);
      } else {
        // The editor fits the value. Fitting forces a layout, so it runs
        // only when the text changes; the estimate stands when the card is
        // not laid out yet (width 0).
        textSpan.textContent = nextText;
        const fit = thermostatFit(nextText, size, stroke);
        text.style.fontSize = `${Number(fit.fontSize)}px`;
        const measured = textSpan.getBoundingClientRect().width;
        if (measured > 0 && measured > fit.maxWidth) {
          text.style.fontSize = `${Number((fit.fontSize * fit.maxWidth) / measured)}px`;
        }
      }
    }
    wrap.title = waitingTitle(widget, feedback);
  });
}

function makeChart(card, widget, rect, scale, patches) {
  const graphic = svg("svg");
  graphic.setAttribute("class", "at-chart");
  graphic.setAttribute("viewBox", `0 0 ${rect[2]} ${rect[3]}`);
  setRect(graphic, rect);
  markPress(graphic, widget);
  const kindBars = widget.kind === "bars" || widget.kind === 1;
  const [, , tabletW = rect[2] / scale, tabletH = rect[3] / scale] = Array.isArray(widget.r) ? widget.r : [];

  // A 1 px line that fills pixel row h - 2, one pixel above the bottom, as
  // the tablet draws it (contract 4.7): centred half a pixel into that row,
  // one tablet pixel thick, so it is one sharp row and not two soft ones.
  const baseline = svg("line");
  baseline.setAttribute("class", "at-chart-baseline");
  baseline.setAttribute("x1", "0");
  baseline.setAttribute("x2", String(rect[2]));
  baseline.setAttribute("y1", String(rect[3] - 1.5 * scale));
  baseline.setAttribute("y2", String(rect[3] - 1.5 * scale));
  baseline.setAttribute("stroke-width", String(scale));
  graphic.append(baseline);
  card.append(graphic);

  patches.push((state, look) => {
    [...graphic.querySelectorAll(".at-chart-data")].forEach((item) => item.remove());
    if (!patchVisible(graphic, widget, state)) {
      return;
    }
    const raw = displayValue(widget.value, state, null, []);
    markNoValue(graphic, widget.value, state, null);
    const values = Array.isArray(raw) ? raw : [];
    const own = colourField(widget.c, state);
    const main = look && own !== null ? hexOf(legible(own, look.bg, look.tx)) : null;

    if (kindBars) {
      const marks = barMarks(values.length, widget.mark === undefined ? null : numberField(widget.mark, state));
      barRects(values, rect[2], rect[3] - 2 * scale, 4 * scale).forEach((bar, index) => {
        const shape = svg("rect");
        shape.setAttribute("class", `at-chart-data at-chart-bar at-bar-${marks[index]}`);
        shape.setAttribute("x", String(bar.x));
        shape.setAttribute("y", String(bar.y));
        shape.setAttribute("width", String(bar.w));
        shape.setAttribute("height", String(bar.h));
        shape.setAttribute("rx", String(Math.min(4 * scale, bar.w / 2)));
        if (marks[index] === "acc2" && main) {
          shape.style.fill = main;
        } else if (marks[index] === "acc" && look) {
          shape.style.fill = hexOf(look.colours.A);
        } else if (marks[index] === "card2" && look) {
          shape.style.fill = hexOf(look.tokens.card2);
        }
        graphic.append(shape);
      });
    } else if (widget.st === 1) {
      // Steps through the points, as filled runs 3 thick (4.7).
      const points = linePoints(values, tabletW, tabletH, 4);
      for (const [x, y, w, h] of stepRects(points)) {
        const shape = svg("rect");
        shape.setAttribute("class", "at-chart-data at-chart-step");
        shape.setAttribute("x", String(x * scale));
        shape.setAttribute("y", String(y * scale));
        shape.setAttribute("width", String(w * scale));
        shape.setAttribute("height", String(h * scale));
        shape.setAttribute("rx", String(1.5 * scale));
        if (main) {
          shape.style.fill = main;
        }
        graphic.append(shape);
      }
    } else {
      const points = linePoints(values, rect[2], rect[3], 4 * scale);
      if (points.length) {
        const polyline = svg("polyline");
        polyline.setAttribute("class", "at-chart-data at-chart-line");
        polyline.setAttribute(
          "points",
          points.map(([x, y]) => `${x},${y}`).join(" "),
        );
        if (main) {
          polyline.style.stroke = main;
        }
        graphic.append(polyline);
      }
    }
  });
}

function makeImage(card, widget, rect, scale, options, patches, timers) {
  const box = html("div", "at-image");
  setRect(box, rect);
  markPress(box, widget);
  card.append(box);
  const lookKind = Math.min(2, Math.max(0, Math.round(toNumber(widget.look, 0))));
  const [, , tabletW = rect[2] / scale, tabletH = rect[3] / scale] = Array.isArray(widget.r) ? widget.r : [];
  if (lookKind) {
    box.classList.add(lookKind === 1 ? "badge" : "bare");
  }
  if (options.interactive && widget.tap) {
    box.classList.add("at-pressable");
    box.addEventListener("click", () => options.onTap?.(widget));
  }

  let lastValue;
  let refreshTimer = null;
  timers.push(() => {
    clearInterval(refreshTimer);
    refreshTimer = null;
  });

  function iconSize() {
    if (!lookKind) {
      return tabletImageIconSize(tabletW, tabletH);
    }
    const side = Math.min(tabletW, tabletH);
    return lookKind === 1 ? largestIcon(0.6 * side) : largestIcon(side);
  }

  function drawValue(value) {
    if (value === lastValue && box.childNodes.length) {
      return;
    }
    lastValue = value;
    box.replaceChildren();
    clearInterval(refreshTimer);
    refreshTimer = null;

    if (options.tablet || lookKind) {
      // The tablet draws icons only; anything else gets the placeholder.
      const icon = iconElement(isIcon(value) ? value : TABLET_IMAGE_PLACEHOLDER);
      sizeIcon(icon, iconSize() * scale);
      box.append(icon);
      return;
    }

    if (isIcon(value)) {
      const icon = iconElement(value);
      sizeIcon(icon, Math.min(rect[2], rect[3]) / 2);
      box.append(icon);
      return;
    }

    if (isSafeImagePath(value)) {
      const image = document.createElement("img");
      image.alt = "";
      image.referrerPolicy = "no-referrer";
      image.loading = "lazy";
      const refreshes = Number(widget.refresh) > 0;
      const setSource = () => {
        const join = value.includes("?") ? "&" : "?";
        image.src = refreshes ? `${value}${join}_t=${Date.now()}` : value;
      };
      setSource();
      box.append(image);

      if (Number(widget.refresh) > 0) {
        refreshTimer = setInterval(setSource, Number(widget.refresh) * 1000);
      }
    }
  }

  patches.push((state, look) => {
    if (!patchVisible(box, widget, state)) {
      return;
    }
    drawValue(displayValue(widget.value, state, null, null));
    markNoValue(box, widget.value, state, null);
    const own = colourField(widget.c, state);
    if (!look || (!lookKind && own === null)) {
      box.style.removeProperty("color");
      return;
    }
    const drawn = imageLook(look.tokens, look.colours, look.on, look.lit, lookKind, tabletW, tabletH, own);
    if (!drawn) {
      return;
    }
    box.style.color = hexOf(drawn.icon);
    if (drawn.box) {
      const [x, y, w, h] = drawn.box;
      if (lookKind === 1) {
        setRect(box, [rect[0] + x * scale, rect[1] + y * scale, w * scale, h * scale]);
      }
      box.style.background = hexOf(drawn.fill);
    }
  });
}

// A choice (contract 4.7, "Choice"): one of up to 16 options as cells, or
// as dots with look 1. A cell shows an icon, a text or both, or is a swatch.
function makeChoice(card, widget, rect, scale, options, patches, sx, sy) {
  const wrap = html("div", "at-choice");
  setRect(wrap, rect);
  markPress(wrap, widget);
  card.append(wrap);
  const texts = Array.isArray(widget.texts) ? widget.texts : [];
  const icons = Array.isArray(widget.icons) ? widget.icons : [];
  const cols = Array.isArray(widget.cols) ? widget.cols : [];
  const count = Math.min(16, Math.max(texts.length, icons.length, cols.length));
  const rows = Math.min(4, Math.max(1, Math.round(toNumber(widget.rows, 1))));
  const lookKind = Math.min(1, Math.max(0, Math.round(toNumber(widget.look, 0))));
  const [, , tabletW = rect[2] / sx, tabletH = rect[3] / sy] = Array.isArray(widget.r) ? widget.r : [];
  const cells = choiceCells(count, rows, tabletW, tabletH, lookKind);
  if (!cells) {
    // Nothing to draw and nothing to press, like a hidden widget.
    wrap.classList.add("at-hidden");
    return;
  }
  const live = Boolean(options.interactive && widget.change);
  const parts = cells.map((cell, index) => {
    const button = html("button", "at-choice-cell");
    button.type = "button";
    button.dataset.option = String(index);
    const [x, y, w, h, dotRect] = cell;
    setRect(button, [x * sx, y * sy, w * sx, h * sy]);
    const face = html("span", "at-choice-face");
    if (lookKind === 1) {
      const [dx, dy, d] = dotRect;
      setRect(face, [(dx - x) * sx, (dy - y) * sy, d * sx, d * sy]);
      face.classList.add("dot");
    } else {
      setRect(face, [0, 0, w * sx, h * sy]);
      face.style.fontSize = `${15 * scale}px`;
      face.style.gap = `${6 * scale}px`;
      const iconName = icons[index];
      const icon = iconElement(typeof iconName === "string" ? iconName : null);
      const label = typeof texts[index] === "string" ? texts[index] : "";
      if (icon) {
        sizeIcon(icon, 24 * scale);
        face.append(icon);
      }
      if (label) {
        const text = html("span", "at-button-text");
        setLineText(text, label, options, 15, w - 12 - (icon && h < 64 ? 30 : 0), scale);
        face.append(text);
      }
      if (icon && label && h >= 64) {
        face.classList.add("vertical");
      }
      button.setAttribute("aria-label", label || (typeof iconName === "string" ? iconName : String(index + 1)));
    }
    if (lookKind === 1 || !button.getAttribute("aria-label")) {
      button.setAttribute("aria-label", String(texts[index] || index + 1));
    }
    button.append(face);
    if (live) {
      button.addEventListener("click", () => options.onChange?.(widget, index, true));
    } else {
      button.disabled = true;
    }
    wrap.append(button);
    return { button, face };
  });

  patches.push((state, look) => {
    if (!patchVisible(wrap, widget, state)) {
      return;
    }
    const feedback = feedbackFor(state, widget);
    const raw = toNumber(displayValue(widget.value, state, feedback, null), null);
    // A fraction or a number that is no index selects nothing (4.3).
    const selected = Number.isInteger(raw) && raw >= 0 && raw < count ? raw : null;
    wrap.classList.toggle(
      "busy",
      feedback.phase === "pending" || feedback.phase === "busy",
    );
    parts.forEach(({ button, face }, index) => {
      const chosen = index === selected;
      button.setAttribute("aria-pressed", String(chosen));
      if (!look) {
        return;
      }
      const swatch = index < cols.length ? toColour(cols[index]) : null;
      let fill = look.track;
      let ink = look.tx;
      let ring = "";
      if (swatch !== null) {
        fill = swatch;
        ink = readable(swatch);
        if (chosen) {
          ring = `inset 0 0 0 ${3 * scale}px ${hexOf(look.tx)}`;
        }
      } else if (chosen) {
        fill = look.colours.AF;
        ink = look.colours.AT;
      }
      face.style.background = hexOf(fill);
      face.style.color = hexOf(ink);
      // Pressed: the selected cell accf_pr, a colour cell keeps its colour,
      // others the card's --at-wpr.
      if (swatch !== null) {
        face.style.setProperty("--at-fpr", hexOf(swatch));
      } else if (chosen) {
        face.style.setProperty("--at-fpr", hexOf(look.colours.AP));
      } else {
        face.style.removeProperty("--at-fpr");
      }
      if (ring) {
        face.style.boxShadow = ring;
      } else {
        face.style.removeProperty("box-shadow");
      }
    });
  });
}

// The pressed look of a card: card_pr, on a filled card onbg_pr; a style
// with its own bg and no card_pr mixes its text into it (4.7).
function pressedColour(look, tokens) {
  if (look.filled) {
    return look.colours.FP;
  }
  if (isHex(tokens.bg) && !isHex(tokens.card_pr) && tokens.bg !== tokens.card) {
    return mix(look.tokens.tx, look.tokens.bg, 90);
  }
  return look.tokens.card_pr;
}

// The element a press began on, walked up to the widget that holds it.
function pressTarget(card, target) {
  let node = target;
  while (node && node !== card) {
    if (node.dataset && (node.dataset.press || node.dataset.hold)) {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}

// Taps and holds of the card itself, in a browser (contract 4.3, "Who gets
// a press"): a tap fires on release, a hold after 500 ms or on a right
// click. A press that moved 12 px or more is neither.
function wireCardPress(card, normalized, options) {
  const tap = normalized.tap;
  const hold = normalized.hold;
  const widgetHolds = normalized.widgets.some((widget) => widget.hold);
  if (!options.interactive || (!tap && !hold && !widgetHolds)) {
    return;
  }
  let press = null;
  const end = () => {
    if (press) {
      clearTimeout(press.holdTimer);
      clearTimeout(press.pressedTimer);
    }
    card.classList.remove("pressed");
    press = null;
  };
  card.addEventListener("pointerdown", (event) => {
    if (event.button !== undefined && event.button !== 0) {
      return;
    }
    end();
    const target = pressTarget(card, event.target);
    const own = target?.dataset.press === "own";
    const holdBy = target?.dataset.hold === "own" ? "widget" : target?.dataset.hold === "none" ? null : "card";
    press = { x: event.clientX, y: event.clientY, own, moved: false, held: false, target };
    if (!own && tap) {
      press.pressedTimer = setTimeout(() => {
        if (press && !press.moved) {
          card.classList.add("pressed");
        }
      }, PRESSED_MS);
    }
    const wantsHold = holdBy === "card" ? Boolean(hold) : holdBy === "widget";
    if (wantsHold) {
      press.holdTimer = setTimeout(() => {
        if (!press || press.moved) {
          return;
        }
        press.held = true;
        card.classList.remove("pressed");
        options.onHold?.(holdBy === "card" ? null : target.__atWidget);
      }, HOLD_MS);
    }
  });
  card.addEventListener("pointermove", (event) => {
    if (!press || press.moved) {
      return;
    }
    const dx = event.clientX - press.x;
    const dy = event.clientY - press.y;
    if (dx * dx + dy * dy >= MOVE_PX * MOVE_PX) {
      press.moved = true;
      clearTimeout(press.holdTimer);
      card.classList.remove("pressed");
    }
  });
  card.addEventListener("pointerup", () => {
    const done = press;
    end();
    if (!done || done.moved || done.held || done.own) {
      return;
    }
    if (tap) {
      options.onCardTap?.();
    }
  });
  card.addEventListener("pointercancel", end);
  card.addEventListener("pointerleave", end);
  // A right click is a hold.
  card.addEventListener("contextmenu", (event) => {
    const target = pressTarget(card, event.target);
    const holdBy = target?.dataset.hold === "own" ? "widget" : target?.dataset.hold === "none" ? null : "card";
    if (holdBy === "card" ? !hold : holdBy !== "widget") {
      return;
    }
    event.preventDefault?.();
    end();
    options.onHold?.(holdBy === "card" ? null : target.__atWidget);
  });
  if (!tap && !hold) {
    return;
  }
  // From the keyboard: Enter or Space is a tap, the menu key or Shift+F10 a
  // hold. Keys on a control inside the card stay that control's.
  card.setAttribute("tabindex", "0");
  card.setAttribute("role", "button");
  if (options.label) {
    card.setAttribute("aria-label", String(options.label));
  }
  card.addEventListener("keydown", (event) => {
    if (event.target !== card || event.repeat) {
      return;
    }
    if ((event.key === "Enter" || event.key === " ") && tap) {
      event.preventDefault?.();
      options.onCardTap?.();
    } else if ((event.key === "ContextMenu" || (event.key === "F10" && event.shiftKey)) && hold) {
      event.preventDefault?.();
      options.onHold?.(null);
    }
  });
}

export function renderCard(host, compiled, state, options = {}) {
  host.__atCleanup?.();
  host.replaceChildren();
  host.style.position = "relative";
  host.style.overflow = "hidden";

  const sx = Number(options.sx) || 1;
  const sy = Number(options.sy) || 1;
  const scale = Math.min(sx, sy);
  const normalized = normalizeCard(compiled, options);
  const card = html("div", "at-card");
  card.style.setProperty("--at-f", String(scale));
  setRect(card, [0, 0, normalized.width * sx, normalized.height * sy]);
  host.append(card);
  // Child rectangles are absolute (contract 4.3): the border does not move
  // them. Absolute children start inside the border, so they go in a layer
  // that starts at the card's outer edge.
  const body = html("div", "at-card-body");
  card.append(body);
  if (options.interactive && normalized.tap) {
    card.classList.add("at-pressable");
  }

  const patches = [];
  const timers = [];
  makeHeader(body, normalized, sx, sy, scale, options, patches);

  for (const widget of normalized.widgets) {
    if (!Array.isArray(widget.r)) {
      continue;
    }
    const rect = localRect(widget.r, normalized.origin, sx, sy);
    // A widget cut to no width or height is not drawn (4.3).
    if (!(widget.r[2] > 0) || !(widget.r[3] > 0)) {
      continue;
    }
    const before = body.children.length;

    if (widget.t === "label") {
      makeLabel(body, widget, rect, scale, options, patches);
    } else if (widget.t === "button") {
      makeButton(body, widget, rect, scale, options, patches);
    } else if (widget.t === "switch") {
      makeSwitch(body, widget, rect, scale, options, patches);
    } else if (widget.t === "slider") {
      makeSlider(body, widget, rect, scale, options, patches, sx, sy);
    } else if (widget.t === "thermostat") {
      makeThermostat(body, widget, rect, scale, options, patches);
    } else if (widget.t === "chart") {
      makeChart(body, widget, rect, scale, patches);
    } else if (widget.t === "image") {
      makeImage(body, widget, rect, scale, options, patches, timers);
    } else if (widget.t === "choice") {
      makeChoice(body, widget, rect, scale, options, patches, sx, sy);
    }
    for (const element of [...body.children].slice(before)) {
      element.__atWidget = widget;
    }
  }

  wireCardPress(card, normalized, options);

  function update(nextState) {
    applyTokens(card, nextState.tokens || {});
    const look = cardLook(normalized, nextState);
    card.classList.toggle("is-on", look.filled);
    card.classList.toggle("is-lit", look.litOn);
    card.classList.toggle("is-outline", look.on && look.lit === 2);
    card.classList.toggle("is-un", look.un);
    if (look.on && look.lit === 2) {
      // The outline is at least 2 wide; the children stay where they are.
      card.style.setProperty("--at-bw", `${Math.max(2, look.tokens.bw)}px`);
    } else if (!Number.isFinite(Number(nextState.tokens?.bw))) {
      card.style.removeProperty("--at-bw");
    }
    if (look.tint !== null) {
      // A tint makes the card's own accent and "on" colours (4.7).
      const { colours } = look;
      for (const [name, value] of [
        ["acc", colours.A],
        ["accf", colours.AF],
        ["acct", colours.AT],
        ["accf_pr", colours.AP],
        ["onbg", colours.F],
        ["ontx", colours.FT],
        ["ion", colours.FI],
        ["onbg_pr", colours.FP],
      ]) {
        card.style.setProperty(`--at-${name}`, hexOf(value));
      }
    }
    card.style.setProperty("--at-onsm", hexOf(look.colours.FS));
    card.style.setProperty("--at-press", hexOf(pressedColour(look, nextState.tokens || {})));
    // A pressed control on the card's background now: card2_pr (on: onbg_pr).
    card.style.setProperty("--at-wpr", hexOf(look.filled ? look.colours.FP : look.tokens.card2_pr));
    for (const patch of patches) {
      patch(nextState, look);
    }
  }

  host.__atCleanup = () => {
    timers.forEach((stop) => stop());
  };

  update(state);
  return { update };
}

function drawHeading(host, heading, sx, sy, tokens, options) {
  const item = html("div", "at-heading");
  setRect(item, mapRect(heading.r, sx, sy));
  applyTokens(item, tokens);
  const icon = iconElement(heading.icon);
  if (icon) {
    sizeIcon(icon, 24 * Math.min(sx, sy));
    item.append(icon);
  }
  // c: the icon and the text in legible(c, wall, tx) (4.7).
  const colour = toColour(heading.c);
  if (colour !== null) {
    const wall = colourOf(tokens.wall) ?? DEFAULT_TOKENS.wall;
    const tx = colourOf(tokens.tx) ?? DEFAULT_TOKENS.tx;
    item.style.color = hexOf(legible(colour, wall, tx));
  }
  const text = html("span", "at-text");
  setLineText(text, heading.text ?? "", options, 20, heading.r[2] - (icon ? 32 : 0), Math.min(sx, sy));
  item.append(text);
  host.append(item);
}

// A page is a detail page when its sub is 1 and it is not page 0 (4.8).
export function isDetailPage(layout, index) {
  return index > 0 && layout?.pages?.[index]?.sub === 1;
}

// The theme of a page: the layout's, with the page's own keys on top (4.8).
export function pageTheme(layout, index) {
  const page = layout?.pages?.[index];
  const own = page && typeof page.theme === "object" && page.theme ? page.theme : {};
  return { ...(layout?.theme || {}), ...own };
}

export function renderPage(host, layout, pageIndex, state, options = {}) {
  host.__atCleanup?.();
  host.replaceChildren();
  host.style.position = "relative";
  host.style.overflow = "hidden";

  const sx = Number(options.sx) || 1;
  const sy = Number(options.sy) || 1;
  const page = layout.pages?.[pageIndex];
  const theme = pageTheme(layout, pageIndex);
  const width = (layout.screen?.[0] || 1280) * sx;
  const height = (layout.screen?.[1] || 800) * sy;
  host.style.width = `${width}px`;
  host.style.height = `${height}px`;

  const wall = html("div", "at-page");
  setRect(wall, [0, 0, width, height]);
  applyTokens(wall, theme);
  wall.style.setProperty("--at-f", String(Math.min(sx, sy)));
  if (options.tablet) {
    // The tablet preview: the tablet's font and its image placeholder.
    loadTabletFont();
    wall.classList.add("at-tablet");
  }
  host.append(wall);

  // The side bar always uses the page's theme, never a card's.
  const nav = html("div", "at-nav");
  setRect(nav, [0, 0, 96 * sx, height]);
  applyTokens(nav, { bg: theme.card });
  wall.append(nav);

  const navButton = (place, iconName, active) => {
    const button = html("button", "at-nav-button");
    button.type = "button";
    setRect(button, [16 * sx, (16 + place * 72) * sy, 64 * sx, 64 * sy]);
    button.classList.toggle("active", active);
    const icon = iconElement(isIcon(iconName) ? iconName : "mdi:view-dashboard");
    if (icon) {
      sizeIcon(icon, 28 * Math.min(sx, sy));
      button.append(icon);
    }
    button.disabled = !options.interactive;
    nav.append(button);
    return button;
  };

  if (isDetailPage(layout, pageIndex)) {
    // A detail page: the one back entry, in the look of the page on screen.
    navButton(0, "mdi:arrow-left", true).classList.add("back");
  } else {
    const details = new Set(
      (layout.pages || []).filter((item, index) => isDetailPage(layout, index)).map((item) => item.id),
    );
    (layout.nav || []).forEach((entry, place) => {
      // An entry that names a detail page is not drawn; the others keep
      // their places.
      if (details.has(entry.page)) {
        return;
      }
      navButton(place, entry.icon, entry.page === page?.id);
    });
  }

  if (!page) {
    return;
  }

  const cleanup = [];
  for (const item of page.w || []) {
    if (item.t === "heading") {
      drawHeading(wall, item, sx, sy, theme, options);
      continue;
    }
    if (item.t !== "card") {
      continue;
    }

    const cardHost = html("div", "at-layout-card");
    setRect(cardHost, mapRect(item.r, sx, sy));
    wall.append(cardHost);
    const tokens = cardTokens(
      { ...theme, bg: theme.card },
      item.style || {},
    );
    renderCard(
      cardHost,
      item,
      {
        values: state.values || {},
        errors: state.errors || {},
        tokens,
        feedback: state.feedback || new Map(),
      },
      {
        sx,
        sy,
        origin: [item.r[0], item.r[1]],
        interactive: Boolean(options.interactive),
        tablet: Boolean(options.tablet),
        onTap: options.onTap,
        onChange: options.onChange,
      },
    );
    // renderCard makes its host relative; a layout card is placed absolutely.
    cardHost.style.position = "absolute";
    cleanup.push(() => cardHost.__atCleanup?.());
  }

  host.__atCleanup = () => cleanup.forEach((stop) => stop());
}
