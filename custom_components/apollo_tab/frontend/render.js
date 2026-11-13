import { t } from "./api.js";
import {
  arcPath,
  barRects,
  clampStep,
  fraction,
  isHex,
  isIcon,
  isOn,
  isSafeImagePath,
  linePoints,
  mapRect,
  resolveBound,
  TABLET_ELLIPSIS,
  TABLET_MISSING_GLYPH,
  tabletCharWidths,
  tabletFit,
  tabletLineHeight,
  tabletText,
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
  "acc2",
  "acct",
  "card2",
  "line",
  "onbg",
  "onbg_pr",
  "ontx",
  "ion",
];

const NUMBER_TOKENS = ["r", "r2", "bw"];

// The image widget's icon sizes on the tablet (contract 4.7), and the glyph
// it draws for a value that is not an icon.
const TABLET_IMAGE_ICON_SIZES = [72, 48, 28, 24];
const TABLET_IMAGE_PLACEHOLDER = "mdi:image-outline";

// The tablet's font (contract 4.7), for the tablet previews.
const TABLET_FONT_FAMILY = "Apollo TAB-1 Montserrat";
let tabletFontLoading = false;
let tabletFontReady = false;
// Texts drawn before the font was there, to be drawn again once it is.
const tabletFontWaiting = new Map();

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
      .catch(() => tabletFontWaiting.clear());
  } catch (_error) {
    // The preview then keeps Home Assistant's font.
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

function normalizeCard(compiled, options) {
  const layoutShape = Array.isArray(compiled?.w);
  const rawRect = layoutShape ? compiled.r : [0, 0, compiled.w, compiled.h];
  const origin = options.origin || (layoutShape ? [rawRect[0], rawRect[1]] : [0, 0]);
  const widgets = layoutShape ? compiled.w : compiled.widgets || [];

  return {
    width: layoutShape ? rawRect[2] : compiled.w,
    height: layoutShape ? rawRect[3] : compiled.h,
    origin,
    widgets,
    header: compiled.header,
    on: compiled.on,
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

// A switch, slider, thermostat, chart or image without a value is drawn at
// 40% and does not react to touch, as on the tablet (contract 4.7).
function markNoValue(element, bound, state, feedback) {
  element.classList.toggle("at-none", displayValue(bound, state, feedback, NO_VALUE) === NO_VALUE);
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

function rgb(value) {
  return [
    Number.parseInt(value.slice(1, 3), 16),
    Number.parseInt(value.slice(3, 5), 16),
    Number.parseInt(value.slice(5, 7), 16),
  ];
}

// t = 0 gives fg, t = 1 gives bg, as in the integration's style maths.
function blend(fg, bg, t) {
  const foreground = rgb(fg);
  const background = rgb(bg);
  const mixed = foreground.map((channel, index) =>
    Math.round(channel * (1 - t) + background[index] * t),
  );
  return `#${mixed.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`.toUpperCase();
}

// WCAG contrast ratio, from 1 to 21.
function contrast(a, b) {
  const linear = (channel) => {
    const value = channel / 255;
    return value <= 0.03928
      ? value / 12.92
      : ((value + 0.055) / 1.055) ** 2.4;
  };
  const luminance = (value) => {
    const [red, green, blue] = rgb(value).map(linear);
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  };
  const first = luminance(a);
  const second = luminance(b);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

export function cardTokens(theme = {}, style = {}) {
  const tokens = { ...theme, ...style };

  // The theme's ion and onbg_pr suit its own "on" fill. A style that changes
  // that fill (a custom colour, an accent, another theme) gets its own.
  if (
    isHex(style.onbg) &&
    isHex(theme.onbg) &&
    style.onbg.toLowerCase() !== theme.onbg.toLowerCase()
  ) {
    tokens.ion =
      isHex(tokens.acc) && contrast(tokens.acc, style.onbg) >= 3
        ? tokens.acc
        : tokens.ontx;
    if (isHex(tokens.ontx)) {
      tokens.onbg_pr = blend(tokens.ontx, style.onbg, 0.82);
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
    if (tabletFontLoading && !tabletFontReady) {
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

function makeHeader(card, normalized, sx, sy, scale, options, patches) {
  if (!normalized.header?.r) {
    return;
  }

  const header = html("div", "at-header");
  setRect(header, localRect(normalized.header.r, normalized.origin, sx, sy));
  header.style.gap = `${8 * scale}px`;

  const icon = iconElement(normalized.header.icon);
  if (icon) {
    sizeIcon(icon, 24 * scale);
    header.append(icon);
  }

  const title = html("span", "at-header-title");
  title.style.fontSize = `${16 * scale}px`;
  header.append(title);
  card.append(header);

  patches.push((state) => {
    const room = normalized.header.r[2] - (icon ? 32 : 0);
    setLineText(title, displayValue(normalized.header.title, state, null), options, 16, room, scale);
  });
}

function makeLabel(card, widget, rect, scale, options, patches) {
  const label = html("div", `at-label at-label-${widget.size || "m"}`);
  setRect(label, rect);
  const fontSize = widget.size === "l" ? 34 : widget.size === "s" ? 14 : 18;
  label.style.fontSize = `${fontSize * scale}px`;
  // Ellipsis needs a block box, which a flex container's text is not.
  const text = html("span", "at-text");
  label.append(text);
  card.append(label);

  patches.push((state) => {
    setLineText(text, displayValue(widget.text, state, null), options, fontSize, widget.r?.[2] ?? 0, scale);
  });
}

function makeButton(card, widget, rect, scale, options, patches) {
  const button = html("button", "at-button");
  button.type = "button";
  setRect(button, rect);
  button.style.fontSize = `${15 * scale}px`;

  const icon = iconElement(widget.icon);
  const text = html("span", "at-button-text");
  if (icon) {
    sizeIcon(icon, 24 * scale);
    button.append(icon);
  }
  if (widget.text !== undefined) {
    button.append(text);
  }
  if (icon && widget.text !== undefined && rect[3] >= 64 * scale) {
    button.classList.add("vertical");
  }

  if (options.interactive && widget.tap) {
    button.addEventListener("click", () => options.onTap?.(widget));
  } else {
    button.disabled = true;
  }

  card.append(button);
  patches.push((state) => {
    const value = widget.text === undefined ? "" : displayValue(widget.text, state, null);
    // The tablet's room for a button's words: 6 px each side, and beside an
    // icon (not below one) the icon and 6 px more.
    const [, , wide = 0, high = 0] = Array.isArray(widget.r) ? widget.r : [];
    const beside = icon && high < 64;
    setLineText(text, value, options, 15, wide - 12 - (beside ? 30 : 0), scale);
    button.setAttribute("aria-label", String(value || widget.icon || ""));
    const feedback = feedbackFor(state, widget);
    button.title = waitingTitle(widget, feedback);
    button.classList.toggle("active", feedback.phase === "pulse");
    button.classList.toggle(
      "busy",
      feedback.phase === "pending" || feedback.phase === "busy",
    );
  });
}

function makeSwitch(card, widget, rect, scale, options, patches) {
  const button = html("button", "at-switch");
  button.type = "button";
  button.setAttribute("role", "switch");
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

  if (options.interactive && widget.tap) {
    button.addEventListener("click", () => options.onTap?.(widget));
  } else {
    button.disabled = true;
  }

  card.append(button);
  patches.push((state) => {
    const feedback = feedbackFor(state, widget);
    const value = displayValue(widget.value, state, feedback);
    markNoValue(button, widget.value, state, feedback);
    const on = isOn(value);
    button.classList.toggle("on", on);
    button.classList.toggle(
      "busy",
      feedback.phase === "pending" || feedback.phase === "busy",
    );
    button.setAttribute("aria-checked", String(on));
    button.title = waitingTitle(widget, feedback);
  });
}

function makeSlider(card, widget, rect, scale, options, patches) {
  const slider = html("div", "at-slider");
  slider.tabIndex = options.interactive && widget.change ? 0 : -1;
  slider.setAttribute("role", "slider");
  setRect(slider, rect);

  const track = html("div", "at-slider-track");
  track.style.height = `${14 * scale}px`;
  track.style.borderRadius = `${7 * scale}px`;

  const fill = html("div", "at-slider-fill");
  const knob = html("div", "at-slider-knob");
  knob.style.width = `${22 * scale}px`;
  knob.style.height = `${22 * scale}px`;
  track.append(fill, knob);
  slider.append(track);
  card.append(slider);

  let dragging = false;
  let dragValue;
  let currentState = null;

  const limits = () => {
    const min = toNumber(resolveBound(widget.min, currentState?.values || {}), 0);
    const max = toNumber(resolveBound(widget.max, currentState?.values || {}), 100);
    const step = toNumber(resolveBound(widget.step, currentState?.values || {}), 1);
    return { min, max, step };
  };

  const valueFromPointer = (event) => {
    const bounds = slider.getBoundingClientRect();
    const amount = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
    const { min, max, step } = limits();
    return clampStep(min + amount * (max - min), min, max, step);
  };

  if (options.interactive && widget.change) {
    slider.addEventListener("pointerdown", (event) => {
      dragging = true;
      options.onDrag?.(true);
      slider.setPointerCapture(event.pointerId);
      dragValue = valueFromPointer(event);
      options.onChange?.(widget, dragValue, false);
      patch(currentState);
    });

    slider.addEventListener("pointermove", (event) => {
      if (!dragging) {
        return;
      }
      dragValue = valueFromPointer(event);
      options.onChange?.(widget, dragValue, false);
      patch(currentState);
    });

    const finish = (event) => {
      if (!dragging) {
        return;
      }
      dragging = false;
      options.onDrag?.(false);
      if (slider.hasPointerCapture(event.pointerId)) {
        slider.releasePointerCapture(event.pointerId);
      }
      options.onChange?.(widget, dragValue, true);
      patch(currentState);
    };

    slider.addEventListener("pointerup", finish);
    slider.addEventListener("pointercancel", finish);
    slider.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowDown", "ArrowRight", "ArrowUp"].includes(event.key)) {
        return;
      }
      event.preventDefault();
      if (!currentState) {
        return;
      }
      const { min, max, step } = limits();
      // Step from the value on screen, which may still be waiting for the server.
      const current = toNumber(
        displayValue(widget.value, currentState, feedbackFor(currentState, widget)),
        min,
      );
      const direction =
        event.key === "ArrowRight" || event.key === "ArrowUp" ? 1 : -1;
      const next = clampStep(current + direction * (step > 0 ? step : 1), min, max, step);
      options.onChange?.(widget, next, true);
    });
  }

  function patch(state) {
    if (!state) {
      return;
    }
    currentState = state;
    const feedback = feedbackFor(state, widget);
    const { min, max } = limits();
    const value = dragging
      ? dragValue
      : toNumber(displayValue(widget.value, state, feedback), min);
    const amount = fraction(value, min, max);
    if (!dragging) {
      markNoValue(slider, widget.value, state, feedback);
    }
    fill.style.width = `${amount * 100}%`;
    knob.style.left = `${amount * 100}%`;
    slider.setAttribute("aria-valuemin", String(min));
    slider.setAttribute("aria-valuemax", String(max));
    slider.setAttribute("aria-valuenow", String(value));
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
  track.setAttribute("class", "at-arc-track");
  valueArc.setAttribute("class", "at-arc-value");
  const stroke = Math.max(8, size / scale / 14);
  track.setAttribute("stroke-width", String(stroke));
  valueArc.setAttribute("stroke-width", String(stroke));
  track.setAttribute("d", arcPath(100, 100, 72, 135, 405));
  graphic.append(track, valueArc);

  // The text sits in its own span so its drawn width can be measured.
  const text = html("div", "at-thermostat-value");
  const textSpan = html("span", "at-thermostat-text");
  textSpan.style.whiteSpace = "nowrap";
  textSpan.style.lineHeight = "1.2";
  text.append(textSpan);
  wrap.append(graphic, text);

  if (widget.change) {
    for (const [direction, iconName] of [
      [-1, "mdi:minus"],
      [1, "mdi:plus"],
    ]) {
      const button = html("button", direction < 0 ? "minus" : "plus");
      button.type = "button";
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
    if (tabletFontLoading && !tabletFontReady) {
      tabletFontWaiting.set(textSpan, () => {
        if (lastText === value) {
          drawTabletValue(value);
        }
      });
    }
  };
  card.append(wrap);
  patches.push((state) => {
    wrap.__state = state;
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

  patches.push((state) => {
    [...graphic.querySelectorAll(".at-chart-data")].forEach((item) => item.remove());
    const raw = displayValue(widget.value, state, null, []);
    markNoValue(graphic, widget.value, state, null);
    const values = Array.isArray(raw) ? raw : [];

    if (widget.kind === "bars") {
      for (const bar of barRects(values, rect[2], rect[3] - 2 * scale, 4 * scale)) {
        const shape = svg("rect");
        shape.setAttribute("class", "at-chart-data at-chart-bar");
        shape.setAttribute("x", String(bar.x));
        shape.setAttribute("y", String(bar.y));
        shape.setAttribute("width", String(bar.w));
        shape.setAttribute("height", String(bar.h));
        shape.setAttribute("rx", String(Math.min(4 * scale, bar.w / 2)));
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
        graphic.append(polyline);
      }
    }
  });
}

function makeImage(card, widget, rect, scale, options, patches, timers) {
  const box = html("div", "at-image");
  setRect(box, rect);
  card.append(box);

  let lastValue;
  let refreshTimer = null;
  timers.push(() => {
    clearInterval(refreshTimer);
    refreshTimer = null;
  });

  function drawValue(value) {
    if (value === lastValue && box.childNodes.length) {
      return;
    }
    lastValue = value;
    box.replaceChildren();
    clearInterval(refreshTimer);
    refreshTimer = null;

    if (options.tablet) {
      // The tablet draws icons only; anything else gets the placeholder.
      const icon = iconElement(isIcon(value) ? value : TABLET_IMAGE_PLACEHOLDER);
      sizeIcon(icon, tabletImageIconSize(rect[2] / scale, rect[3] / scale) * scale);
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

  patches.push((state) => {
    drawValue(displayValue(widget.value, state, null, null));
    markNoValue(box, widget.value, state, null);
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

  const patches = [];
  const timers = [];
  makeHeader(body, normalized, sx, sy, scale, options, patches);

  for (const widget of normalized.widgets) {
    if (!Array.isArray(widget.r)) {
      continue;
    }
    const rect = localRect(widget.r, normalized.origin, sx, sy);

    if (widget.t === "label") {
      makeLabel(body, widget, rect, scale, options, patches);
    } else if (widget.t === "button") {
      makeButton(body, widget, rect, scale, options, patches);
    } else if (widget.t === "switch") {
      makeSwitch(body, widget, rect, scale, options, patches);
    } else if (widget.t === "slider") {
      makeSlider(body, widget, rect, scale, options, patches);
    } else if (widget.t === "thermostat") {
      makeThermostat(body, widget, rect, scale, options, patches);
    } else if (widget.t === "chart") {
      makeChart(body, widget, rect, scale, patches);
    } else if (widget.t === "image") {
      makeImage(body, widget, rect, scale, options, patches, timers);
    }
  }

  function update(nextState) {
    applyTokens(card, nextState.tokens || {});
    const on = isOn(resolveBound(normalized.on, nextState.values || {}));
    card.classList.toggle("is-on", on);
    for (const patch of patches) {
      patch(nextState);
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
  const text = html("span", "at-text");
  setLineText(text, heading.text ?? "", options, 20, heading.r[2] - (icon ? 32 : 0), Math.min(sx, sy));
  item.append(text);
  host.append(item);
}

export function renderPage(host, layout, pageIndex, state, options = {}) {
  host.__atCleanup?.();
  host.replaceChildren();
  host.style.position = "relative";
  host.style.overflow = "hidden";

  const sx = Number(options.sx) || 1;
  const sy = Number(options.sy) || 1;
  const page = layout.pages?.[pageIndex];
  const width = (layout.screen?.[0] || 1280) * sx;
  const height = (layout.screen?.[1] || 800) * sy;
  host.style.width = `${width}px`;
  host.style.height = `${height}px`;

  const wall = html("div", "at-page");
  setRect(wall, [0, 0, width, height]);
  applyTokens(wall, layout.theme || {});
  wall.style.setProperty("--at-f", String(Math.min(sx, sy)));
  if (options.tablet) {
    // The tablet preview: the tablet's font and its image placeholder.
    loadTabletFont();
    wall.classList.add("at-tablet");
  }
  host.append(wall);

  const nav = html("div", "at-nav");
  setRect(nav, [0, 0, 96 * sx, height]);
  applyTokens(nav, { bg: layout.theme?.card });
  wall.append(nav);

  for (const entry of layout.nav || []) {
    const button = html("button", "at-nav-button");
    button.type = "button";
    const pagePosition = (layout.nav || []).indexOf(entry);
    setRect(button, [16 * sx, (16 + pagePosition * 72) * sy, 64 * sx, 64 * sy]);
    button.classList.toggle("active", entry.page === page?.id);
    const icon = iconElement(isIcon(entry.icon) ? entry.icon : "mdi:view-dashboard");
    if (icon) {
      sizeIcon(icon, 28 * Math.min(sx, sy));
      button.append(icon);
    }
    button.disabled = !options.interactive;
    nav.append(button);
  }

  if (!page) {
    return;
  }

  const cleanup = [];
  for (const item of page.w || []) {
    if (item.t === "heading") {
      drawHeading(wall, item, sx, sy, layout.theme || {}, options);
      continue;
    }
    if (item.t !== "card") {
      continue;
    }

    const cardHost = html("div", "at-layout-card");
    setRect(cardHost, mapRect(item.r, sx, sy));
    wall.append(cardHost);
    const tokens = cardTokens(
      { ...(layout.theme || {}), bg: layout.theme?.card },
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
