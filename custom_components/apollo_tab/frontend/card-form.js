import { t } from "./api.js";
import {
  accentGrounds,
  accentInk,
  accentText,
  formToStyle,
  isHex,
  isIcon,
  kelvinRgb,
  parseCssColour,
  styleToForm,
  switchKnob,
} from "./logic.js";
import {
  MAX_ENTITIES,
  MAX_UNITS_HIGH,
  MAX_UNITS_WIDE,
  PAGE_ICONS,
  PAGE_ICON_NAMES,
  UNIT_COLUMNS,
  UNIT_ROWS,
  activeVariant,
  cardForm,
  cardSize,
  entityChoices,
  optionDefault,
  pageChoices,
  paramFields,
  styleDefaults,
} from "./model.js";

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

let nextId = 0;

export function uid(prefix) {
  nextId += 1;
  return `${prefix}-${nextId}`;
}

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined && text !== null) {
    node.textContent = text;
  }
  return node;
}

// The kinds of button besides the plain (tonal) one. Each only sets a
// class; "primary" is the filled one.
const BUTTON_KINDS = ["primary", "tonal", "text", "link", "icon", "danger"];

// data-focus names a control so it can get focus back after its region is
// drawn again; data-test is what the scripted browser run looks for. kind
// is one of BUTTON_KINDS; a danger button gets a bin icon before its words.
// A link button's words are in a span, which takes its focus ring.
export function makeButton(label, options = {}) {
  const button = el("button", options.className);
  button.type = "button";
  if (BUTTON_KINDS.includes(options.kind)) {
    button.classList.add(options.kind);
  }
  if (label !== undefined && label !== null && button.classList.contains("link")) {
    button.append(el("span", null, label));
  } else if (label !== undefined && label !== null) {
    button.textContent = label;
  }
  if (options.kind === "danger") {
    button.prepend(icon("mdi:trash-can-outline"));
  }
  if (options.test) {
    button.dataset.test = options.test;
  }
  if (options.focus) {
    button.dataset.focus = options.focus;
  }
  if (options.focusAlt) {
    button.dataset.focusAlt = options.focusAlt;
  }
  if (options.ariaLabel) {
    button.setAttribute("aria-label", options.ariaLabel);
  }
  if (options.disabled) {
    button.disabled = true;
  }
  if (options.onClick) {
    button.addEventListener("click", options.onClick);
  }
  return button;
}

export function icon(name) {
  const node = document.createElement("ha-icon");
  node.setAttribute("aria-hidden", "true");
  if (isIcon(name)) {
    node.icon = name;
  }
  return node;
}

export function entityName(hass, entityId) {
  return hass?.states?.[entityId]?.attributes?.friendly_name || entityId;
}

export function deviceText(hass, entities) {
  return (entities || []).map((id) => entityName(hass, id)).join(", ");
}

export function labelForName(name) {
  const text = String(name).replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function whichLabel(domain) {
  const key = `pick.which.${domain}`;
  const text = t(key);
  return text === key ? t("pick.which.other") : text;
}

// The fields of a card's form. When two device fields would ask the same
// question (a room card wants a temperature sensor and a humidity sensor),
// each is named after what it is for instead, so they can be told apart.
export function formFields(component) {
  const fields = paramFields(component);
  const entities = fields.filter((field) => field.kind === "entity");
  return fields.map((field) => {
    if (field.kind !== "entity") {
      return field;
    }
    // A field for several kinds of device, or any kind, asks with the card
    // file's own words when it has them.
    if (!field.domain && field.label) {
      return field;
    }
    const question = whichLabel(field.domain);
    const shared = entities.some(
      (other) => other !== field && whichLabel(other.domain) === question,
    );
    return { ...field, label: shared ? labelForName(field.name) : question };
  });
}

function rgbToHex(rgb) {
  if (!Array.isArray(rgb) || rgb.length !== 3) {
    return "#000000";
  }
  return `#${rgb
    .map((part) => Math.max(0, Math.min(255, Math.round(Number(part) || 0))))
    .map((part) => part.toString(16).padStart(2, "0"))
    .join("")}`;
}

function hexToRgbList(hex) {
  return [1, 3, 5].map((start) => Number.parseInt(hex.slice(start, start + 2), 16));
}

function textInput({ label, value, maxLength, test, focus, helper, onInput }) {
  const field = el("label", "field");
  const input = document.createElement("input");
  input.type = "text";
  input.value = value || "";
  input.maxLength = maxLength;
  input.autocomplete = "off";
  if (test) {
    input.dataset.test = test;
  }
  input.dataset.focus = focus || test || label;
  input.addEventListener("input", () => onInput(input.value));
  field.append(el("span", "field-label", label), input);
  if (helper) {
    field.append(el("span", "helper", helper));
  }
  return { field, input };
}

// A yes or no setting, drawn as a switch at the end of a row of words.
// The helper line, when there is one, goes right after the row; the switch
// names it as its description.
export function switchRow({ label, help, checked, disabled, focus, test, onChange }) {
  const field = el("label", "check");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.setAttribute("role", "switch");
  input.checked = Boolean(checked);
  input.disabled = Boolean(disabled);
  if (focus) {
    input.dataset.focus = focus;
  }
  if (test) {
    input.dataset.test = test;
  }
  input.addEventListener("change", () => onChange(input.checked));
  field.append(el("span", null, label), input);
  let helper = null;
  if (help) {
    helper = el("p", "helper", help);
    helper.id = uid("switch-help");
    input.setAttribute("aria-describedby", helper.id);
  }
  return { field, input, helper };
}

// Reads a colour token of the host as numbers. A custom property's own
// value is its text as written, which may be a name or a color-mix(); an
// element's colour always comes back as numbers, so the token is mixed with
// itself into the colour of a hidden span.
function readColour(probe, token) {
  probe.style.color = `color-mix(in srgb, var(${token}), var(${token}))`;
  return parseCssColour(getComputedStyle(probe).color);
}

const toCss = (rgb) => `rgb(${rgb.join(", ")})`;

// Sets the four accent values on the host (a filled button, its words, the
// accent as text and the focus ring of the picture), each made readable on
// the theme's own colours, and the knob of a switch that is off. When the
// accent or the surface cannot be read, the token block's fallbacks hold.
export function applyAccent(host) {
  const root = host?.shadowRoot;
  if (!root || typeof getComputedStyle !== "function") {
    return;
  }
  const names = ["--tab-accent-fill", "--tab-accent-ink", "--tab-accent-text", "--tab-ring", "--tab-knob"];
  const probe = document.createElement("span");
  probe.hidden = true;
  root.append(probe);
  try {
    const accent = readColour(probe, "--tab-accent");
    const surface = readColour(probe, "--tab-surface");
    if (!accent || !surface) {
      for (const name of names) {
        host.style.removeProperty(name);
      }
      return;
    }
    const text = readColour(probe, "--tab-text");
    const grounds = accentGrounds({
      surface,
      page: readColour(probe, "--tab-bg"),
      stage: readColour(probe, "--tab-stage"),
      text,
      accent,
      tones: {
        ok: readColour(probe, "--tab-ok"),
        warn: readColour(probe, "--tab-warn"),
        err: readColour(probe, "--tab-err"),
        info: readColour(probe, "--tab-info"),
      },
    });
    const { fill, ink } = accentInk(accent);
    host.style.setProperty("--tab-accent-fill", toCss(fill));
    host.style.setProperty("--tab-accent-ink", toCss(ink));
    host.style.setProperty("--tab-accent-text", toCss(accentText(accent, grounds)));
    host.style.setProperty("--tab-ring", toCss(accentText(accent, [[255, 255, 255]])));
    if (text) {
      host.style.setProperty("--tab-knob", toCss(switchKnob(surface, text)));
    } else {
      host.style.removeProperty("--tab-knob");
    }
  } finally {
    probe.remove();
  }
}

function select({ label, options, value, focus, test, onChange }) {
  const field = el("label", "field");
  const control = document.createElement("select");
  for (const [optionValue, optionLabel] of options) {
    const option = el("option", null, optionLabel);
    option.value = optionValue;
    control.append(option);
  }
  control.value = value;
  control.dataset.focus = focus;
  if (test) {
    control.dataset.test = test;
  }
  control.addEventListener("change", () => onChange(control.value));
  field.append(el("span", "field-label", label), control);
  return { field, control };
}

// Gives focus to the control named `key` in `container`, which was just
// drawn again. A control that is now disabled (Wider at the largest size,
// Move page right on the last page) cannot hold focus, so the control its
// data-focus-alt names gets it, or else the nearest control that can take
// it; focus then never drops to the page, where the next Tab would start
// again from the top. A control that is gone hands its focus to the one
// whose data-focus-takes starts its name (a folded list's Change button
// takes it for every choice in the list). Returns whether a control got
// focus.
export function restoreFocus(container, key) {
  if (!key) {
    return false;
  }
  const nodes = [...container.querySelectorAll("[data-focus]")];
  const target = nodes.find((node) => node.dataset.focus === key);
  if (!target) {
    const heir = nodes.find((node) => node.dataset.focusTakes && key.startsWith(node.dataset.focusTakes) && !node.disabled);
    heir?.focus();
    return Boolean(heir);
  }
  if (!target.disabled) {
    target.focus();
    return true;
  }
  const usable = (node) => Boolean(node) && !node.disabled && node.getClientRects().length > 0;
  const partners = (target.dataset.focusAlt || "")
    .split(" ")
    .filter(Boolean)
    .map((name) => nodes.find((node) => node.dataset.focus === name));
  const index = nodes.indexOf(target);
  const next =
    partners.find(usable) ||
    nodes.slice(index + 1).find(usable) ||
    nodes.slice(0, index).reverse().find(usable);
  next?.focus();
  return Boolean(next);
}

// True when nothing on the page has focus, as after the focused control was
// taken off the page along with the screen it was on.
export function focusLost() {
  const active = document.activeElement;
  return !active || active === document.body;
}

// The heading of one of the panel's screens. It takes focus from script
// when the person moves to that screen, so the keyboard and screen readers
// start there; it is not a stop for the Tab key.
export function screenHeading(text) {
  const heading = el("h1", "screen-heading", text);
  heading.tabIndex = -1;
  heading.dataset.focus = "heading";
  return heading;
}

// Draws a region again and gives focus back to the control that had it.
function redraw(container, draw) {
  const active = container.getRootNode().activeElement;
  const key = active && container.contains(active) ? active.dataset.focus : null;
  container.replaceChildren();
  draw();
  restoreFocus(container, key);
}

// The icon of a kind of device, for the device rows and the list.
const DOMAIN_ICONS = {
  light: "mdi:lightbulb",
  switch: "mdi:toggle-switch",
  scene: "mdi:palette",
  script: "mdi:script-text",
  climate: "mdi:thermostat",
  fan: "mdi:fan",
  cover: "mdi:blinds",
  media_player: "mdi:speaker",
  lock: "mdi:lock",
  alarm_control_panel: "mdi:shield-home",
  camera: "mdi:cctv",
  sensor: "mdi:eye",
  binary_sensor: "mdi:checkbox-blank-circle-outline",
  weather: "mdi:weather-partly-cloudy",
  person: "mdi:account",
};

function deviceIcon(hass, entityId) {
  const own = hass?.states?.[entityId]?.attributes?.icon;
  if (isIcon(own)) {
    return own;
  }
  return DOMAIN_ICONS[String(entityId).split(".", 1)[0]] || "mdi:devices";
}

// The room a device is in, as the list shows it.
function deviceRoom(hass, entityId) {
  return entityChoices(hass, { kind: "entity", domains: [] }, "").find((choice) => choice.entity_id === entityId)?.area || "";
}

// A device's icon in a tinted circle, as the device rows and the list draw it.
function deviceBadge(name) {
  const badge = el("span", "device-badge");
  badge.append(icon(name));
  return badge;
}

// Returns a DOM node. onChange(value) gets the new param value (string,
// string[], number or undefined). In the card form (collapsed) a device
// field shows the chosen device as one row and opens its list on request;
// in the picker the list is open from the start.
export function buildParamField({
  hass,
  field,
  value,
  config,
  compact = false,
  collapsed = false,
  onChange,
}) {
  if (field.kind === "entity") {
    return entityField({ hass, field, value, collapsed, compact, onChange });
  }
  if (field.kind === "number") {
    return numberField({ field, value, onChange });
  }
  if (field.kind === "page") {
    return pageField({ field, value, config, onChange });
  }
  return el("div");
}

// A device field. The list is a combobox: the search field is the one Tab
// stop, Down and Up move the active choice, Enter picks it, and Escape
// first empties the search, then closes the list (in the card form). The
// number of matches is read out politely.
function entityField({ hass, field, value, collapsed, compact, onChange }) {
  const wrap = el("div", "field device-field");
  wrap.dataset.param = field.name;
  const label = field.label || whichLabel(field.domain);
  let chosen = field.multiple
    ? (Array.isArray(value) ? value : []).filter((id) => typeof id === "string").slice(0, MAX_ENTITIES)
    : typeof value === "string"
      ? value
      : "";
  let query = "";

  const chosenNames = () =>
    field.multiple
      ? chosen.map((id) => entityName(hass, id)).join(", ")
      : chosen
        ? entityName(hass, chosen)
        : "";

  const drawClosed = () => {
    wrap.classList.remove("choosing");
    wrap.replaceChildren();
    const row = el("div", "chosen");
    const names = chosenNames();
    const first = field.multiple ? chosen[0] : chosen;
    if (names) {
      row.append(deviceBadge(deviceIcon(hass, first)));
    }
    const words = el("span", "chosen-words");
    words.append(el("span", "chosen-name", names || t("form.none_chosen")));
    const room = names && !field.multiple ? deviceRoom(hass, first) : "";
    if (room) {
      words.append(el("span", "small", room));
    }
    row.append(words);
    // "Change" would suggest something is chosen already.
    const action = names ? t("form.change_device") : t("form.choose_device");
    row.append(
      makeButton(action, {
        kind: names ? "text" : "tonal",
        test: "change-device",
        focus: `change-device:${field.name}`,
        ariaLabel: `${action}: ${label}`,
        onClick: () => drawOpen(true),
      }),
    );
    wrap.append(el("span", "field-label", label), row);
  };

  const drawOpen = (focusSearch) => {
    wrap.replaceChildren();
    // On a phone the open list takes the whole edit mode (see styles).
    wrap.classList.toggle("choosing", collapsed && compact);
    const listId = uid("entities");
    const labelId = uid("entities-label");
    const searchField = el("label", "field");
    const labelNode = el("span", "field-label", label);
    labelNode.id = labelId;
    const search = document.createElement("input");
    search.type = "search";
    search.value = query;
    search.placeholder = t("pick.search");
    search.autocomplete = "off";
    search.dataset.test = "entity-search";
    search.dataset.focus = `entity-search:${field.name}`;
    search.setAttribute("role", "combobox");
    search.setAttribute("aria-autocomplete", "list");
    search.setAttribute("aria-expanded", "true");
    search.setAttribute("aria-controls", listId);
    searchField.append(labelNode, search);
    wrap.append(searchField);

    let counter = null;
    if (field.multiple) {
      counter = el("p", "helper", t("pick.chosen", { count: chosen.length }));
      counter.setAttribute("aria-live", "polite");
      wrap.append(el("p", "helper", t("pick.many_hint", { max: MAX_ENTITIES })), counter);
    }
    // How many devices match, for screen readers.
    const matches = el("p", "sr-only");
    matches.setAttribute("aria-live", "polite");
    matches.dataset.test = "entity-matches";

    const list = el("div", "entity-list");
    list.id = listId;
    list.setAttribute("role", "listbox");
    list.setAttribute("aria-label", label);
    if (field.multiple) {
      list.setAttribute("aria-multiselectable", "true");
    }
    const message = el("div", "field");
    wrap.append(list, matches, message);

    let options = [];
    let active = -1;
    const setActive = (index) => {
      options.forEach((option) => option.classList.remove("active"));
      active = options.length ? Math.max(0, Math.min(options.length - 1, index)) : -1;
      if (active < 0) {
        search.removeAttribute("aria-activedescendant");
        return;
      }
      const option = options[active];
      option.classList.add("active");
      search.setAttribute("aria-activedescendant", option.id);
      option.scrollIntoView?.({ block: "nearest" });
    };

    const pick = (entityId) => {
      if (field.multiple) {
        const keep = active;
        chosen = chosen.includes(entityId) ? chosen.filter((id) => id !== entityId) : [...chosen, entityId];
        counter.textContent = t("pick.chosen", { count: chosen.length });
        fill();
        setActive(keep);
        onChange(chosen.length ? [...chosen] : undefined);
        return;
      }
      chosen = entityId;
      if (collapsed) {
        drawClosed();
        wrap.querySelector("button")?.focus();
      } else {
        fill();
      }
      onChange(entityId || undefined);
    };

    const fill = () => {
      list.replaceChildren();
      message.replaceChildren();
      options = [];
      active = -1;
      search.removeAttribute("aria-activedescendant");

      if (!entityChoices(hass, field, "").length) {
        list.hidden = true;
        matches.textContent = "";
        message.append(el("strong", null, t("pick.none_title")), el("p", "helper", t("pick.none_text")));
        return;
      }
      const choices = entityChoices(hass, field, query);
      list.hidden = !choices.length;
      matches.textContent = t("pick.matches", { count: choices.length });
      if (!choices.length) {
        message.append(el("p", "helper", t("pick.no_match", { query: query.trim() })));
        return;
      }
      // Two devices with the same name show their address too.
      const counts = new Map();
      for (const choice of choices) {
        counts.set(choice.name, (counts.get(choice.name) || 0) + 1);
      }
      const rows = [...choices];
      // An optional device can be left out again.
      if (field.optional && !field.multiple && !query.trim()) {
        rows.unshift({ entity_id: "", name: t("form.device_none"), area: "" });
      }
      for (const choice of rows) {
        const selected = field.multiple ? chosen.includes(choice.entity_id) : chosen === choice.entity_id;
        const option = el("div", "entity-option");
        option.id = uid("entity");
        option.dataset.test = "entity";
        option.dataset.entity = choice.entity_id;
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", String(selected));
        if (choice.entity_id) {
          option.title = choice.entity_id;
          option.append(deviceBadge(deviceIcon(hass, choice.entity_id)));
        }
        const words = el("span", "entity-words");
        const name = el("span", "entity-name");
        if (selected) {
          name.append(el("span", "entity-check", "✓ "));
        }
        name.append(choice.name);
        words.append(name);
        const second = [choice.area, counts.get(choice.name) > 1 ? choice.entity_id : ""].filter(Boolean).join(" · ");
        if (second) {
          words.append(el("small", null, second));
        }
        option.append(words);
        const full = field.multiple && !selected && chosen.length >= MAX_ENTITIES;
        if (full) {
          option.setAttribute("aria-disabled", "true");
        }
        // A press on a row keeps focus in the search field.
        option.addEventListener("mousedown", (event) => event.preventDefault());
        option.addEventListener("click", () => {
          if (!full) {
            pick(choice.entity_id);
          }
        });
        options.push(option);
        list.append(option);
      }
    };

    search.addEventListener("input", () => {
      query = search.value;
      fill();
    });
    search.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const step = event.key === "ArrowDown" ? 1 : -1;
        setActive(active < 0 ? (step > 0 ? 0 : options.length - 1) : active + step);
      } else if (event.key === "Home" && active >= 0) {
        event.preventDefault();
        setActive(0);
      } else if (event.key === "End" && active >= 0) {
        event.preventDefault();
        setActive(options.length - 1);
      } else if (event.key === "Enter") {
        if (active >= 0 && options[active].getAttribute("aria-disabled") !== "true") {
          event.preventDefault();
          pick(options[active].dataset.entity);
        }
      } else if (event.key === "Escape") {
        // First the search, then the list; then Escape goes on to the form.
        if (search.value) {
          event.preventDefault();
          event.stopPropagation();
          query = "";
          search.value = "";
          fill();
        } else if (collapsed) {
          event.preventDefault();
          event.stopPropagation();
          drawClosed();
          wrap.querySelector("button")?.focus();
        }
      }
    });
    fill();
    if (focusSearch) {
      search.focus();
    }
  };

  if (collapsed) {
    drawClosed();
  } else {
    drawOpen(false);
  }
  return wrap;
}

function numberField({ field, value, onChange }) {
  const wrap = el("label", "field");
  wrap.dataset.param = field.name;
  const input = document.createElement("input");
  input.type = "number";
  input.step = "any";
  input.dataset.focus = `param:${field.name}`;
  if (field.min !== null && field.min !== undefined) {
    input.min = String(field.min);
  }
  if (field.max !== null && field.max !== undefined) {
    input.max = String(field.max);
  }
  if (field.default !== null && field.default !== undefined) {
    input.placeholder = String(field.default);
  }
  input.value = typeof value === "number" && Number.isFinite(value) ? String(value) : "";
  input.addEventListener("input", () => {
    const raw = input.value.trim();
    if (!raw) {
      onChange(undefined);
      return;
    }
    const number = Number(raw);
    if (Number.isFinite(number)) {
      onChange(number);
    }
  });
  wrap.append(el("span", "field-label", field.label || labelForName(field.name)), input);
  // Empty keeps the card file's own number.
  if (field.default !== null && field.default !== undefined) {
    wrap.append(el("span", "helper", t("form.number_default", { value: field.default })));
  }
  return wrap;
}

function pageField({ field, value, config, onChange }) {
  const { field: wrap } = select({
    label: field.label || t("pick.page"),
    options: [
      ["", t("pick.page_none")],
      ...pageChoices(config).map((page) => [page.path, page.title || page.path]),
    ],
    value: typeof value === "string" ? value : "",
    focus: `param:${field.name}`,
    onChange: (next) => onChange(next || undefined),
  });
  wrap.dataset.param = field.name;
  return wrap;
}

// The lines under an item's heading: notes for a card the tablet shows, or
// the reason it is left out. Filled again whenever a new preview arrives.
// onBigger, when given, puts "Make the card bigger" on the line that says
// part of the card does not fit.
export function fillItemNotes(container, row, { onOpenAdvanced, onBigger } = {}) {
  if (!container) {
    return;
  }
  container.replaceChildren();
  if (!row) {
    return;
  }
  for (const code of row.notes || []) {
    const line = el("p", "note-line", t(`warn.${code}`, { detail: row.detail || "" }));
    container.append(line);
    if (code === "element_clipped" && onBigger) {
      line.classList.add("with-button");
      line.append(makeButton(t("form.bigger"), { kind: "text", test: "card-bigger", focus: "card-bigger", onClick: onBigger }));
    }
  }
  if (row.reason) {
    const line = el("p", "note-line problem", t(`warn.${row.reason}`, { detail: row.detail || "" }));
    container.append(line);
    if (row.reason === "needs_approval" && onOpenAdvanced) {
      container.append(
        makeButton(t("advanced.open"), { kind: "link", test: "open-advanced", onClick: onOpenAdvanced }),
      );
    }
  }
}

function itemHeading(text) {
  const heading = el("h2", "side-title", text);
  heading.tabIndex = -1;
  heading.dataset.test = "side-title";
  heading.dataset.focus = "side-title";
  return heading;
}

// ---- the inspector: a header that stays, then parts that fold ----

// Which parts are open, per part and not per card, while the editor is
// open. Only what the person opened or closed is kept; the rest follow
// each card's first-time rule.
const partOpen = new Map();

export function resetParts() {
  partOpen.clear();
}

// Opens a part from outside, as "Move to page" in the list does.
export function showPart(id) {
  partOpen.set(id, true);
}

// One part: a details element with a 48 px summary row (chevron, title, a
// one-line summary) and the rows under it.
function part(id, title, summary, open, nodes) {
  const details = el("details", "part");
  details.dataset.test = `part-${id}`;
  details.dataset.part = id;
  details.open = partOpen.has(id) ? partOpen.get(id) : open;
  const head = el("summary", "part-summary");
  head.dataset.focus = `part:${id}`;
  const chevron = icon("mdi:chevron-right");
  chevron.classList.add("part-chevron");
  const sum = el("span", "part-sum", summary || "");
  sum.dataset.test = "part-summary";
  head.append(chevron, el("span", "part-title", title), sum);
  // A press on the summary toggles the part after this; Enter and Space
  // press it too.
  head.addEventListener("click", () => partOpen.set(id, !details.open));
  const body = el("div", "part-body");
  body.append(...nodes);
  details.append(head, body);
  return details;
}

// The header: the card's icon in a circle, its name and its type, and the
// buttons. ctx.compact gives Done its word.
function inspectorHead({ iconName, name, type, buttons }) {
  const head = el("div", "inspector-head");
  head.dataset.test = "side-head";
  const badge = el("span", "head-icon");
  badge.append(icon(iconName || "mdi:card-outline"));
  const words = el("div", "head-words");
  words.append(itemHeading(name));
  if (type) {
    const line = el("span", "small head-type", type);
    line.dataset.test = "side-type";
    words.append(line);
  }
  const actions = el("div", "head-buttons");
  actions.append(...buttons.filter(Boolean));
  head.append(badge, words, actions);
  return head;
}

function headButton(name, words, test, onClick, className = "") {
  const button = makeButton(null, {
    kind: "icon",
    className,
    test,
    focus: test,
    ariaLabel: words,
    onClick,
  });
  button.title = words;
  button.append(icon(name));
  return button;
}

// Done, with its word: it lets the card go (on a phone it closes the edit
// mode).
function doneButton(ctx) {
  if (!ctx.onDone) {
    return null;
  }
  const button = makeButton(null, { className: "sheet-close", test: "close-panel", focus: "close-panel", onClick: ctx.onDone });
  button.append(icon("mdi:check"), el("span", null, t("editor.close_panel")));
  return button;
}

function removeButton(test, words, onClick) {
  return headButton("mdi:trash-can-outline", words, test, onClick, "head-remove");
}

// The inspector's two halves: the header that stays in view and the body
// that scrolls. The editor places them.
function inspector(head, body) {
  const node = el("div", "inspector");
  node.append(head, body);
  return node;
}

// The name a card goes by: the name on the card, else its device's name,
// else the card's own name.
function cardTitle(ctx) {
  const { card, component } = ctx;
  if (typeof card.title === "string" && card.title.trim()) {
    return card.title.trim();
  }
  const names = formFields(component)
    .filter((field) => field.kind === "entity")
    .flatMap((field) => {
      const value = card.params?.[field.name];
      return (Array.isArray(value) ? value : [value]).filter((id) => typeof id === "string" && id);
    })
    .map((id) => entityName(ctx.hass, id));
  return names.length ? names.slice(0, 2).join(", ") + (names.length > 2 ? ", …" : "") : "";
}

// The summary of the Device part: the chosen devices, or "Nothing chosen
// yet".
function deviceSummary(ctx, fields) {
  const names = fields
    .filter((field) => field.kind === "entity")
    .flatMap((field) => {
      const value = ctx.card.params?.[field.name];
      return (Array.isArray(value) ? value : [value]).filter((id) => typeof id === "string" && id);
    })
    .map((id) => entityName(ctx.hass, id));
  if (names.length) {
    return names.join(", ");
  }
  return fields.some((field) => field.kind === "entity") ? t("form.none_chosen") : "";
}

// Size and place: the named sizes, the steppers with their words, the size
// grid for a pointer, the place and Move to page. `form` is the card's form
// data (cardForm) or null for a card of the first schema.
function placePart(ctx, form) {
  const block = el("div", "place-rows");
  let size = cardSize(ctx.card, ctx.component);
  // The card as the steps leave it, for the named sizes: the steps drop
  // the picked size (designer.js onResize), so the size follows the grid.
  let card = ctx.card;
  const named = Boolean(form) && form.sizes.length > 1;

  const resize = (w, h) => {
    const width = Math.min(ctx.maxWide, Math.max(1, w));
    const height = Math.min(MAX_UNITS_HIGH, Math.max(1, h));
    if (width === size.w && height === size.h && size.exact) {
      return;
    }
    size = { w: width, h: height, exact: true };
    card = { ...card, variant: undefined, grid_options: { ...card.grid_options, columns: width * UNIT_COLUMNS, rows: height * UNIT_ROWS } };
    ctx.onResize(width, height);
    redraw(block, draw);
  };

  const stepper = (label, value, less, more) => {
    const row = el("div", "stepper");
    const words = el("span", "stepper-label", label);
    const number = el("span", "stepper-value", String(value));
    number.setAttribute("aria-hidden", "true");
    const lessButton = makeButton(null, { kind: "icon", ...less });
    lessButton.append(icon("mdi:minus"));
    lessButton.title = less.ariaLabel;
    const moreButton = makeButton(null, { kind: "icon", ...more });
    moreButton.append(icon("mdi:plus"));
    moreButton.title = more.ariaLabel;
    row.append(words, lessButton, number, moreButton);
    return row;
  };

  const draw = () => {
    let shown = null;
    let tuned = false;
    if (named) {
      sizeChips(form, ctx)(block, card);
      const id = activeVariant(card, ctx.component, form.sizes);
      shown = form.sizes.find((entry) => entry.id === id) || null;
      tuned = Boolean(shown)
        && (!size.exact || size.w * UNIT_COLUMNS !== shown.grid[0] || size.h * UNIT_ROWS !== shown.grid[1]);
    }
    const value = el("p", "size-value", t("form.size_value", { w: size.w, h: size.h, wide: MAX_UNITS_WIDE, high: MAX_UNITS_HIGH }));
    value.dataset.test = "size-words";
    value.setAttribute("aria-live", "polite");
    const width = stepper(
      t("form.width"),
      size.w,
      { test: "narrower", focus: "narrower", focusAlt: "wider", ariaLabel: t("form.narrower"), disabled: size.w <= 1, onClick: () => resize(size.w - 1, size.h) },
      { test: "wider", focus: "wider", focusAlt: "narrower", ariaLabel: t("form.wider"), disabled: size.w >= ctx.maxWide, onClick: () => resize(size.w + 1, size.h) },
    );
    // Wider stops early on a page still arranged in narrow columns. Say why
    // beside it, with the action that lifts the limit.
    let columns = null;
    if (ctx.maxWide < MAX_UNITS_WIDE && size.w >= ctx.maxWide && ctx.onWholeScreen) {
      columns = el("div", "size-note");
      columns.dataset.test = "size-columns";
      columns.append(
        el("p", "helper", t("form.size_columns", { max: ctx.maxWide })),
        makeButton(t("editor.columns_fix"), {
          test: "card-whole-screen",
          focus: "card-whole-screen",
          onClick: ctx.onWholeScreen,
        }),
      );
    }
    const height = stepper(
      t("form.height"),
      size.h,
      { test: "shorter", focus: "shorter", focusAlt: "taller", ariaLabel: t("form.shorter"), disabled: size.h <= 1, onClick: () => resize(size.w, size.h - 1) },
      { test: "taller", focus: "taller", focusAlt: "shorter", ariaLabel: t("form.taller"), disabled: size.h >= MAX_UNITS_HIGH, onClick: () => resize(size.w, size.h + 1) },
    );
    block.append(width);
    if (columns) {
      block.append(columns);
    }
    block.append(height, value);
    // Back to the card's own size, only while the size differs.
    if (named && tuned) {
      block.append(
        makeButton(t("form.size_back", { size: shown.name }), {
          kind: "text",
          test: "size-reset",
          focus: "size-reset",
          onClick: () => ctx.onVariant(shown.id),
        }),
      );
    } else if (!named) {
      const own = ownSize(ctx);
      if (!size.exact || size.w !== own[0] || size.h !== own[1]) {
        block.append(
          makeButton(t("form.size_reset"), {
            kind: "text",
            test: "size-reset",
            focus: "size-reset",
            focusAlt: "wider narrower",
            onClick: () => resize(own[0], own[1]),
          }),
        );
      }
    }
    block.append(sizeGrid(size, ctx.maxWide, resize));
    if (!size.exact) {
      block.append(el("p", "helper", t("form.size_odd")));
    }
  };

  draw();
  const nodes = [block];
  if (ctx.onMove) {
    nodes.push(positionBlock(ctx));
  }
  return nodes;
}

// The size a card of the first schema is made with.
function ownSize(ctx) {
  const own = Array.isArray(ctx.component.size) ? ctx.component.size : [1, 1];
  return [Number(own[0]) || 1, Number(own[1]) || 1];
}

// The quick way to a size with a pointer: 6 x 4 cells; moving over them
// paints a rectangle from the top left, a press sets that size, and cells
// the card cannot reach are dimmed. Hidden from assistive technology; the
// steppers are the accessible way.
function sizeGrid(size, maxWide, resize) {
  const grid = el("div", "size-grid");
  grid.dataset.test = "size-grid";
  grid.setAttribute("aria-hidden", "true");
  const cells = [];
  const paint = (w, h) => {
    for (const cell of cells) {
      cell.classList.toggle("painted", cell.__w <= w && cell.__h <= h);
    }
  };
  for (let h = 1; h <= MAX_UNITS_HIGH; h += 1) {
    for (let w = 1; w <= MAX_UNITS_WIDE; w += 1) {
      const cell = el("div", "size-cell");
      cell.__w = w;
      cell.__h = h;
      cell.dataset.w = String(w);
      cell.dataset.h = String(h);
      const reach = w <= maxWide;
      cell.classList.toggle("out", !reach);
      cell.classList.toggle("on", w <= size.w && h <= size.h);
      if (reach) {
        cell.addEventListener("pointerenter", () => paint(w, h));
        cell.addEventListener("click", () => resize(w, h));
      }
      cells.push(cell);
      grid.append(cell);
    }
  }
  grid.addEventListener("pointerleave", () => paint(0, 0));
  return grid;
}

// Moves the card to another page, or to a new one. The page is chosen first
// and the move made with its own button, so going through the choices with
// the keyboard moves nothing.
function moveToPageBlock({ pages, onMoveToPage }) {
  const block = el("div", "move-page");
  const options = [
    ...(Array.isArray(pages) ? pages : []).map((page) => [String(page.view), page.title || String(page.view + 1)]),
    ["new", t("form.move_to_page_new")],
  ];
  const { field, control } = select({
    label: t("form.move_to_page"),
    options,
    value: options[0][0],
    focus: "move-page",
    test: "move-page",
    onChange: () => {},
  });
  const go = makeButton(t("form.move_to_page_go"), {
    test: "move-page-go",
    focus: "move-page-go",
    onClick: () => onMoveToPage(control.value === "new" ? "new" : Number(control.value)),
  });
  block.append(field, go);
  return block;
}

// The place: [<] 3 of 10 [>], the line about how cards fill the screen,
// and Move to page.
function positionBlock({ canEarlier, canLater, onMove, place, pages, onMoveToPage }) {
  const block = el("div", "place-block");
  const row = el("div", "stepper place-stepper");
  const earlier = makeButton(null, {
    kind: "icon",
    test: "move-earlier",
    focus: "move-earlier",
    focusAlt: "move-later",
    ariaLabel: t("form.move_earlier"),
    disabled: !canEarlier,
    onClick: () => onMove(-1),
  });
  earlier.title = t("form.move_earlier");
  earlier.append(icon("mdi:chevron-left"));
  const later = makeButton(null, {
    kind: "icon",
    test: "move-later",
    focus: "move-later",
    focusAlt: "move-earlier",
    ariaLabel: t("form.move_later"),
    disabled: !canLater,
    onClick: () => onMove(1),
  });
  later.title = t("form.move_later");
  later.append(icon("mdi:chevron-right"));
  const where = el("span", "stepper-value place-value", place ? t("form.place_of", { n: place.n, count: place.count }) : "");
  where.dataset.test = "place-words";
  row.append(el("span", "stepper-label", t("form.order")), earlier, where, later);
  block.append(row, el("p", "helper", t("form.order_helper")));
  if (onMoveToPage) {
    block.append(moveToPageBlock({ pages, onMoveToPage }));
  }
  return block;
}

// The words for the Size and place summary: "Wide, 3 of 10".
function placeSummary(ctx, form) {
  const size = cardSize(ctx.card, ctx.component);
  let name = t("form.size_short", { w: size.w, h: size.h });
  if (form && form.sizes.length > 1) {
    const id = activeVariant(ctx.card, ctx.component, form.sizes);
    const shown = form.sizes.find((entry) => entry.id === id);
    const exact = shown && size.exact && size.w * UNIT_COLUMNS === shown.grid[0] && size.h * UNIT_ROWS === shown.grid[1];
    if (exact) {
      name = shown.name;
    }
  }
  return ctx.place ? t("form.place_summary", { size: name, n: ctx.place.n, count: ctx.place.count }) : name;
}

// ---- Look: swatches, samples and the card's own look rows ----

// A row of swatches as one radio group: each has its colour's name as its
// label and the chosen one a tick. `own` adds the colour field itself,
// drawn as one more swatch, for a colour of one's own.
function swatchGroup({ label, test, entries, value, own, focus, onPick, onOwn }) {
  const field = el("div", "field");
  const labelNode = el("span", "field-label", label);
  labelNode.id = uid("swatch-label");
  const group = el("div", "swatch-row");
  group.setAttribute("role", "radiogroup");
  group.setAttribute("aria-labelledby", labelNode.id);
  if (test) {
    group.dataset.test = test;
  }
  const buttons = [];
  const hex = (text) => (typeof text === "string" ? text.toUpperCase() : "");
  const chosen = entries.findIndex((entry) => hex(entry.value) === hex(value) || (entry.value === null && !value));
  entries.forEach((entry, index) => {
    const button = makeButton(null, {
      className: "swatch-choice",
      test: "swatch-choice",
      focus: `${focus}:${index}`,
      ariaLabel: entry.name,
      onClick: () => onPick(entry.value),
    });
    button.title = entry.name;
    button.dataset.value = entry.value === null ? "" : entry.value;
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(index === chosen));
    button.tabIndex = index === (chosen >= 0 ? chosen : 0) ? 0 : -1;
    const fill = el("span", entry.value === null ? "swatch-fill none" : "swatch-fill");
    fill.setAttribute("aria-hidden", "true");
    if (entry.value !== null) {
      fill.style.backgroundColor = entry.fill || entry.value;
    }
    button.append(fill);
    button.addEventListener("keydown", (event) =>
      radioKeys(event, buttons, index, buttons.length, (next) => onPick(entries[next].value)),
    );
    buttons.push(button);
    group.append(button);
  });
  if (own) {
    const mine = el("label", "swatch-own");
    const custom = chosen < 0 && isHex(value);
    mine.classList.toggle("chosen", custom);
    const input = document.createElement("input");
    input.type = "color";
    input.value = isHex(value) ? value.toLowerCase() : "#ffffff";
    input.dataset.focus = `${focus}:own`;
    input.dataset.test = `${test || focus}-own`;
    input.setAttribute("aria-label", t("form.role_own"));
    input.title = t("form.role_own");
    input.addEventListener("input", () => onOwn(input.value.toUpperCase(), true));
    input.addEventListener("change", () => onOwn(input.value.toUpperCase(), false));
    const plus = icon("mdi:plus");
    plus.classList.add("swatch-plus");
    mine.append(input, plus);
    group.append(mine);
  }
  field.append(labelNode, group);
  return field;
}

// A segmented control for a few choices: [value, words] pairs.
function segmented({ label, choices, value, focus, test, disabled = false, onChange }) {
  const field = el("div", "field");
  const labelNode = el("span", "field-label", label);
  labelNode.id = uid("seg-label");
  const group = el("div", "segmented");
  group.setAttribute("role", "radiogroup");
  group.setAttribute("aria-labelledby", labelNode.id);
  if (test) {
    group.dataset.test = test;
  }
  group.dataset.value = value ?? "";
  const name = uid("seg");
  for (const [choice, words] of choices) {
    const option = el("label");
    option.dataset.value = String(choice);
    const input = el("input");
    input.type = "radio";
    input.name = name;
    input.value = String(choice);
    input.checked = !disabled && String(value) === String(choice);
    input.disabled = disabled;
    input.dataset.focus = `${focus}:${choice}`;
    input.addEventListener("change", () => onChange(String(choice)));
    option.append(input, el("span", null, words));
    group.append(option);
  }
  field.append(labelNode, group);
  return field;
}

// The colours a card background may take: the active theme's own, a few
// neutrals; "none" first.
function backgroundSwatches(theme) {
  const list = [{ value: null, name: t("form.swatch_none") }];
  const add = (value, key) => {
    if (isHex(value) && !list.some((entry) => entry.value && entry.value.toUpperCase() === value.toUpperCase())) {
      list.push({ value: value.toUpperCase(), name: t(key) });
    }
  };
  add(theme.card2, "form.swatch_raised");
  add(theme.acc, "form.role_accent");
  add(theme.acc2, "form.role_accent2");
  add(theme.onbg, "form.swatch_on");
  add("#FFFFFF", "form.swatch_white");
  add("#9AA0A8", "form.swatch_grey");
  add("#000000", "form.swatch_black");
  return list;
}

// The highlight colours: the theme's own first, then a few others.
function accentSwatches(theme) {
  const list = [{ value: null, name: t("form.accent_theme") }];
  for (const [value, key] of [
    [theme.acc2, "form.role_accent2"],
    ["#F5B547", "form.swatch_amber"],
    ["#32D74B", "form.role_good"],
    ["#0A84FF", "form.swatch_blue"],
    ["#BF5AF2", "form.swatch_purple"],
    ["#FF453A", "form.swatch_red"],
  ]) {
    if (isHex(value) && !list.some((entry) => entry.value && entry.value.toUpperCase() === value.toUpperCase())) {
      list.push({ value: value.toUpperCase(), name: t(key) });
    }
  }
  return list;
}

const SURFACES = [
  ["card", "form.surface_card"],
  ["outline", "form.surface_outline"],
  ["plain", "form.surface_plain"],
];
const CORNERS = [
  ["theme", "form.look_theme"],
  ["square", "form.corners_square"],
  ["round", "form.corners_round"],
  ["soft", "form.corners_soft"],
];
const BORDERS = [
  ["theme", "form.look_theme"],
  ["none", "form.border_none"],
  ["thin", "form.border_thin"],
  ["bold", "form.border_bold"],
];

// The theme for this card as swatch tiles, "Same as the dashboard" first.
function themeTiles(ctx, value, onPick) {
  const themes = Array.isArray(ctx.themes) ? ctx.themes : [];
  const field = el("div", "field");
  const labelNode = el("span", "field-label", t("form.theme"));
  labelNode.id = uid("card-theme");
  const group = el("div", "theme-grid card-themes");
  group.setAttribute("role", "radiogroup");
  group.setAttribute("aria-labelledby", labelNode.id);
  group.dataset.test = "card-theme";
  group.dataset.value = value || "";
  const dashboard = themes.find((theme) => theme.id === ctx.dashboardTheme) || themes[0] || {};
  const entries = [{ id: "", name: t("form.theme_dashboard"), theme: dashboard }, ...themes.map((theme) => ({ id: theme.id, name: theme.name || theme.id, theme }))];
  const tiles = [];
  const chosen = Math.max(0, entries.findIndex((entry) => entry.id === (value || "")));
  entries.forEach((entry, index) => {
    const tile = makeButton(null, {
      className: "theme-tile",
      test: "card-theme-tile",
      focus: `card-theme:${entry.id || "dashboard"}`,
      onClick: () => onPick(entry.id),
    });
    tile.dataset.theme = entry.id;
    tile.setAttribute("role", "radio");
    tile.setAttribute("aria-checked", String(index === chosen));
    tile.tabIndex = index === chosen ? 0 : -1;
    tile.append(themeSwatch(entry.theme), el("span", "theme-label", entry.name));
    tile.addEventListener("keydown", (event) => radioKeys(event, tiles, index, 3, (next) => onPick(entries[next].id)));
    tiles.push(tile);
    group.append(tile);
  });
  field.append(labelNode, group, el("span", "helper", t("form.theme_helper")));
  return field;
}

// A theme painted small: its wall, a card, the accent and the text.
function themeSwatch(theme = {}) {
  const swatch = el("span", "theme-swatch");
  swatch.setAttribute("aria-hidden", "true");
  const colour = (value, fallback) => (isHex(value) ? value : fallback);
  swatch.style.backgroundColor = colour(theme.wall, "#101418");
  const card = el("span", "swatch-card");
  card.style.backgroundColor = colour(theme.card, "#181c23");
  const dot = el("span", "swatch-dot");
  dot.style.backgroundColor = colour(theme.acc, "#f5b547");
  const bar = el("span", "swatch-bar");
  bar.style.backgroundColor = colour(theme.tx, "#e8eaed");
  card.append(dot, bar);
  swatch.append(card);
  return swatch;
}

// What a sub-part of Look keeps: open or closed while the editor is open.
function subPart(id, title, open, nodes) {
  const details = el("details", "subpart");
  details.dataset.test = `part-${id}`;
  details.open = partOpen.has(id) ? partOpen.get(id) : open;
  const head = el("summary", "subpart-summary");
  head.dataset.focus = `part:${id}`;
  const chevron = icon("mdi:chevron-right");
  chevron.classList.add("part-chevron");
  head.append(chevron, el("span", "part-title", title));
  head.addEventListener("click", () => partOpen.set(id, !details.open));
  const body = el("div", "part-body");
  body.append(...nodes);
  details.append(head, body);
  return details;
}

// Look (spec 6.4): the card's look rows, its own options with section
// look, then Colours (today's five settings) and Reset look.
function lookPart(ctx, form, extraRows = []) {
  const block = el("div", "look-rows");
  const style = isObject(ctx.card.style) ? ctx.card.style : {};
  let data = styleToForm(style);
  const themes = Array.isArray(ctx.themes) ? ctx.themes : [];
  const themeFor = () =>
    themes.find((theme) => theme.id === (data.theme || ctx.dashboardTheme)) || themes[0] || {};

  const change = (patch, field, continuous = false) => {
    data = styleDefaults({ ...data, ...patch }, themeFor());
    ctx.onStyle(formToStyle(data), field, continuous);
  };
  const hexOf = (rgb) => (Array.isArray(rgb) && rgb.length === 3 ? rgbToHex(rgb).toUpperCase() : null);

  const nodes = [];
  // While it is on and the device's colour: only for a card that has them.
  if (form && form.lit !== null) {
    const lit = segmented({
      label: t("form.lit"),
      choices: Object.entries(LIT_LOOKS).map(([look, key]) => [look, t(key)]),
      value: form.lit,
      focus: "card-lit",
      test: "card-lit",
      onChange: (value) => ctx.onLook("lit", value === ctx.component.standard?.lit ? undefined : value),
    });
    lit.append(el("span", "helper", t("form.lit_helper")));
    nodes.push(lit);
  }
  if (form && form.tint !== null) {
    // Greyed and off for a device with no colour; what is stored stays.
    const { field, helper } = switchRow({
      label: t("form.tint"),
      help: form.tintUsable ? "" : t("form.tint_no_colour"),
      checked: form.tintUsable && form.tint,
      disabled: !form.tintUsable,
      focus: "card-tint",
      test: "card-tint",
      onChange: (checked) => ctx.onLook("tint", checked ? undefined : false),
    });
    const row = el("div", "option-switch option-row");
    row.classList.toggle("unusable", !form.tintUsable);
    row.append(field);
    if (helper) {
      row.append(helper);
    }
    nodes.push(row);
  }
  // Surface, corners and border, for every card (A19).
  if (ctx.onLook) {
    nodes.push(
      segmented({
        label: t("form.surface"),
        choices: SURFACES.map(([value, key]) => [value, t(key)]),
        value: typeof style.surface === "string" ? style.surface : "card",
        focus: "look-surface",
        test: "look-surface",
        onChange: (value) => ctx.onLook("surface", value === "card" ? undefined : value),
      }),
      segmented({
        label: t("form.corners"),
        choices: CORNERS.map(([value, key]) => [value, t(key)]),
        value: typeof style.corners === "string" ? style.corners : "theme",
        focus: "look-corners",
        test: "look-corners",
        onChange: (value) => ctx.onLook("corners", value === "theme" ? undefined : value),
      }),
      segmented({
        label: t("form.border"),
        choices: BORDERS.map(([value, key]) => [value, t(key)]),
        value: typeof style.border === "string" ? style.border : "theme",
        focus: "look-border",
        test: "look-border",
        onChange: (value) => ctx.onLook("border", value === "theme" ? undefined : value),
      }),
    );
  }
  nodes.push(...extraRows);

  // Colours: today's five settings, closed at first.
  const colours = [];
  colours.push(themeTiles(ctx, data.theme, (id) => change({ theme: id }, "theme")));
  const theme = themeFor();
  colours.push(
    swatchGroup({
      label: t("form.color"),
      test: "look-background",
      entries: backgroundSwatches(theme),
      value: data.use_color ? hexOf(data.color) : null,
      own: true,
      focus: "look-color",
      onPick: (value) => change(value ? { use_color: true, color: hexToRgbList(value) } : { use_color: false }, "color"),
      onOwn: (value, continuous) => change({ use_color: true, color: hexToRgbList(value) }, "color", continuous),
    }),
  );
  const fade = segmented({
    label: t("form.gradient"),
    choices: [
      ["none", t("form.gradient_none")],
      ["vertical", t("form.gradient_vertical")],
      ["horizontal", t("form.gradient_horizontal")],
    ],
    value: data.gradient || "none",
    focus: "look-gradient",
    test: "look-gradient",
    onChange: (value) => change({ gradient: value }, "gradient"),
  });
  // A card that lights up shows its fade while it is off.
  if (form && form.lit !== null) {
    fade.append(el("span", "helper", t("form.gradient_helper")));
  }
  colours.push(fade);
  if (data.gradient && data.gradient !== "none") {
    colours.push(
      swatchGroup({
        label: t("form.gradient_to"),
        test: "look-gradient-to",
        entries: backgroundSwatches(theme).filter((entry) => entry.value !== null),
        value: hexOf(data.gradient_to),
        own: true,
        focus: "look-gradient-to",
        onPick: (value) => change({ gradient_to: hexToRgbList(value) }, "gradient_to"),
        onOwn: (value, continuous) => change({ gradient_to: hexToRgbList(value) }, "gradient_to", continuous),
      }),
    );
  }

  const transparency = el("label", "field");
  const row = el("div", "range-row");
  const range = document.createElement("input");
  range.type = "range";
  range.min = "0";
  range.max = "100";
  range.step = "5";
  range.value = String(data.transparency || 0);
  range.dataset.focus = "look-transparency";
  range.dataset.test = "look-transparency";
  const output = el("output", null, `${range.value} %`);
  // The track is filled up to the knob (see input[type="range"] in styles.js).
  const fill = () => range.style.setProperty("--tab-range-fill", String(Number(range.value) / 100));
  fill();
  range.addEventListener("input", () => {
    output.textContent = `${range.value} %`;
    fill();
    change({ transparency: Number(range.value) }, "transparency", true);
  });
  row.append(range, output);
  transparency.append(
    el("span", "field-label", t("form.transparency")),
    row,
    el("span", "helper", t("form.transparency_helper")),
  );
  colours.push(transparency);

  // What the highlight colour changes on the tablet (see resolve_style in
  // maker/style.py and the "is-on" rules of the card styles).
  const accent = swatchGroup({
    label: t("form.accent"),
    test: "look-accent",
    entries: accentSwatches(theme),
    value: data.use_accent ? hexOf(data.accent) : null,
    own: true,
    focus: "look-accent",
    onPick: (value) => change(value ? { use_accent: true, accent: hexToRgbList(value) } : { use_accent: false }, "accent"),
    onOwn: (value, continuous) => change({ use_accent: true, accent: hexToRgbList(value) }, "accent", continuous),
  });
  const accentHelper = el("p", "helper", t("form.accent_helper"));
  accentHelper.dataset.test = "accent-helper";
  accentHelper.id = uid("accent-helper");
  accent.children[1].setAttribute("aria-describedby", accentHelper.id);
  accent.append(accentHelper);
  colours.push(accent);
  nodes.push(subPart("colours", t("form.colours"), false, colours));

  // Reset look, while anything is set.
  if (Object.keys(style).length) {
    nodes.push(
      makeButton(t("form.look_reset"), {
        kind: "text",
        test: "look-reset",
        focus: "look-reset",
        onClick: () => ctx.onStyleReset?.(),
      }),
    );
  }
  block.append(...nodes);
  return block;
}

// The form for a TAB-1 card: the header, the notices, then the parts
// Device, What it shows, Controls, Look, and Size and place (spec 6.2).
// The callbacks receive plain values; the editor turns them into config
// changes. continuous is true for typing and dragging, which are saved as
// one undo step. A card of the first schema has no options and one size.
export function buildCardForm(ctx) {
  const { card, component, readOnly } = ctx;
  const schema2 = component.schema === 2;
  const form = schema2 ? cardForm(component, card, ctx.facts) : null;
  if (form) {
    // The value the form shows when nothing is stored, for "store only what
    // differs" (model.js::setOption).
    for (const row of form.rows) {
      row.fallback = row.usable ? optionDefault(row.option, row.listed) : row.value;
    }
  }
  const title = cardTitle(ctx);
  const head = inspectorHead({
    iconName: form && isIcon(form.icon) ? form.icon : component.icon,
    name: title || component.name,
    type: title ? component.name : t("list.no_device"),
    buttons: readOnly
      ? [doneButton(ctx)]
      : [
          ctx.onDuplicate ? headButton("mdi:content-copy", t("form.duplicate"), "duplicate-card", ctx.onDuplicate) : null,
          removeButton("remove-card", t("form.remove"), ctx.onRemove),
          doneButton(ctx),
        ],
  });
  const body = el("div", "inspector-body");
  body.append(el("div", "item-notes"));
  if (readOnly) {
    if (component.description) {
      body.append(el("p", "helper", component.description));
    }
    return inspector(head, body);
  }
  // Notices under the header: an older card, the card file's own notes,
  // older tablet software.
  if (ctx.newer) {
    body.append(newerCardNotice(ctx));
  }
  for (const text of form ? form.notes : []) {
    const note = el("p", "note-line", text);
    note.dataset.test = "card-note";
    body.append(note);
  }
  if (form && ctx.olderTablets?.length) {
    const note = el("p", "note-line", t("form.older_tablet", { tablet: ctx.olderTablets.join(", ") }));
    note.dataset.test = "older-tablet";
    body.append(note);
  }

  // Device: one row per device field, then the number and page fields.
  const fields = formFields(component);
  const deviceNodes = fields.map((field) =>
    buildParamField({
      hass: ctx.hass,
      field,
      value: card.params?.[field.name],
      config: ctx.config,
      compact: ctx.compact,
      collapsed: true,
      // A list of several devices stays open while devices are ticked.
      onChange: (value) => ctx.onParam(field.name, value, field.kind === "number" || Boolean(field.multiple)),
    }),
  );
  const optionNames = form ? form.rows.map((entry) => entry.name) : [];

  // What it shows: the name on the card, the icon, the card's own rows.
  const showsNodes = [];
  if (!form || form.title) {
    const { field } = textInput({
      label: t("form.name"),
      value: typeof card.title === "string" ? card.title : "",
      maxLength: 60,
      test: "form-name",
      helper: t("form.name_helper"),
      onInput: (text) => ctx.onTitle(text),
    });
    showsNodes.push(field);
  }
  if (form && form.icon !== undefined) {
    showsNodes.push(
      iconChoice({
        label: t("form.icon"),
        value: form.icon,
        own: isIcon(form.names["can.icon"]) ? form.names["can.icon"] : component.icon,
        focus: "card-icon",
        onChange: (name) => ctx.onStandard("icon", name),
      }),
    );
  }
  if (form) {
    showsNodes.push(...optionRows(form, "shows", ctx, optionNames));
  }

  // Controls: a tap, a hold, then the card's own rows.
  const controlNodes = [];
  if (form?.tap) {
    const { field } = select({
      label: t("form.tap"),
      options: form.tap.choices.map((choice) => [choice.value, choice.label]),
      value: form.tap.value,
      focus: "card-tap",
      test: "card-tap",
      onChange: (value) => ctx.onStandard("tap", value),
    });
    if (form.tap.dropped) {
      field.append(el("span", "helper", t("form.tap_not_offered")));
    }
    controlNodes.push(field);
    if (form.tap.value === "page") {
      const pages = pageChoices(ctx.config);
      const { field: pageField } = select({
        label: t("form.tap_page"),
        options: [["", t("pick.page_none")], ...pages.map((page) => [page.path, page.title || page.path])],
        value: form.tap.page,
        focus: "card-tap-page",
        test: "card-tap-page",
        onChange: (value) => ctx.onStandard("tap_page", value || undefined),
      });
      controlNodes.push(pageField);
    }
  }
  if (form && form.hold !== null) {
    const { field } = switchRow({
      label: t("form.hold"),
      checked: form.hold,
      focus: "card-hold",
      test: "card-hold",
      onChange: (checked) => ctx.onStandard("hold", checked ? undefined : false),
    });
    const row = el("div", "option-switch");
    row.append(field);
    controlNodes.push(row);
  }
  const ownControls = form ? optionRows(form, "controls", ctx, optionNames) : [];
  if (ownControls.length) {
    // Some rows are drawn only on the larger sizes or on the controls page.
    const larger = form.sizes.length > 1;
    const detail = component.has_detail === true;
    let note = "";
    if (larger && detail) {
      note = t("form.on_card_some");
    } else if (larger) {
      note = t("form.on_card_larger");
    } else if (detail) {
      note = t("form.on_card_detail");
    }
    if (note) {
      const line = el("p", "helper", note);
      line.dataset.test = "on-card-note";
      controlNodes.push(line);
    }
    controlNodes.push(...ownControls);
  }

  const parts = [];
  if (deviceNodes.length) {
    parts.push(part("device", t("form.part_device"), deviceSummary(ctx, fields), true, deviceNodes));
  }
  if (showsNodes.length) {
    const named = typeof card.title === "string" && card.title.trim();
    parts.push(
      part("shows", t("form.shows"), named ? card.title.trim() : t("form.sum_device_name"), !controlNodes.length, showsNodes),
    );
  }
  if (controlNodes.length) {
    parts.push(part("controls", t("form.part_controls"), controlsSummary(form), true, controlNodes));
  }
  const lookExtra = form ? optionRows(form, "look", ctx, optionNames) : [];
  const ownLook = isObject(card.style) && Object.keys(card.style).length > 0;
  parts.push(
    part("look", t("form.look"), ownLook ? t("form.sum_own_look") : t("form.theme_dashboard"), false, [lookPart(ctx, form, lookExtra)]),
  );
  parts.push(part("place", t("form.part_place"), placeSummary(ctx, form), false, placePart(ctx, form)));
  body.append(...parts);
  return inspector(head, body);
}

// A schema 2 card has the same form (cards spec C.7).
export const buildCardForm2 = buildCardForm;

// "3 of 4 on": the switches of Controls that the device can use, and how
// many of them are on.
function controlsSummary(form) {
  if (!form) {
    return "";
  }
  const switches = form.rows.filter((row) => row.option.section === "controls" && row.shown && row.usable && row.option.type === "toggle");
  let on = switches.filter((row) => row.value === true).length;
  let count = switches.length;
  if (form.hold !== null) {
    count += 1;
    on += form.hold ? 1 : 0;
  }
  return count ? t("form.sum_on", { on, count }) : "";
}

// A heading card or a section title. Section titles have no position of
// their own: they always sit at the top of their section.
export function buildHeadingForm(ctx) {
  const head = inspectorHead({
    iconName: "mdi:format-header-1",
    name: t("form.heading_title"),
    type: ctx.text || "",
    buttons: ctx.readOnly ? [doneButton(ctx)] : [removeButton("remove-heading", t("form.remove_heading"), ctx.onRemove), doneButton(ctx)],
  });
  const body = el("div", "inspector-body");
  body.append(el("div", "item-notes"));
  if (ctx.readOnly) {
    body.append(el("p", null, ctx.text));
    return inspector(head, body);
  }
  const { field } = textInput({
    label: t("form.heading_text"),
    value: ctx.text,
    maxLength: 80,
    test: "heading-text",
    onInput: (text) => ctx.onText(text),
  });
  body.append(field);
  if (ctx.isCard) {
    body.append(positionBlock(ctx));
  }
  return inspector(head, body);
}

// Anything the tablet cannot draw: what it is, why it is left out, and a
// way to remove it.
export function buildOtherForm(ctx) {
  const head = inspectorHead({
    iconName: "mdi:card-off-outline",
    name: t("form.other_title"),
    type: ctx.name || "",
    buttons: ctx.readOnly ? [doneButton(ctx)] : [removeButton("remove-item", t("list.remove"), ctx.onRemove), doneButton(ctx)],
  });
  const body = el("div", "inspector-body");
  // The device it was set up for, which a TAB-1 card can take over.
  if (ctx.device) {
    const line = el("p", null, t("form.other_device", { device: ctx.device }));
    line.dataset.test = "other-device";
    body.append(line);
  }
  body.append(el("div", "item-notes"));
  return inspector(head, body);
}

// The title of a pop-up. It takes focus when the pop-up opens on a touch
// screen, where a text field would bring the keyboard up unasked.
function popTitle(text) {
  const heading = el("h2", "pop-title", text);
  heading.tabIndex = -1;
  heading.dataset.focus = "pop-title";
  return heading;
}

// Arrow keys, Home and End move through a grid of radio buttons drawn as
// buttons, `columns` to a row, and choose the one they land on, as a group
// of radio buttons does.
function radioKeys(event, buttons, index, columns, choose) {
  const moves = {
    ArrowRight: 1,
    ArrowLeft: -1,
    ArrowDown: columns,
    ArrowUp: -columns,
  };
  let next = null;
  if (Object.hasOwn(moves, event.key)) {
    // Right to left, the arrows follow the page.
    const flip = getComputedStyle(event.currentTarget).direction === "rtl" && Math.abs(moves[event.key]) === 1;
    next = index + (flip ? -moves[event.key] : moves[event.key]);
  } else if (event.key === "Home") {
    next = 0;
  } else if (event.key === "End") {
    next = buttons.length - 1;
  }
  if (next === null) {
    return;
  }
  event.preventDefault();
  next = Math.max(0, Math.min(buttons.length - 1, next));
  if (next !== index && !buttons[next].disabled) {
    buttons[next].focus();
    choose(next);
  }
}

// The page pop-up: the page's name, the icon of its button on the tablet
// (a radio group of 7 to a row, with the name of the icon under it), the
// moves and Delete.
export function buildPageSettings(ctx) {
  const block = el("section", "form-block pop-form");
  block.append(popTitle(t("page.heading")));

  const { field } = textInput({
    label: t("page.name"),
    value: ctx.title,
    maxLength: 40,
    test: "page-name",
    onInput: (text) => ctx.onRename(text),
  });
  block.append(field);

  const icons = el("div", "field");
  const iconsLabel = el("span", "field-label", t("page.icon"));
  iconsLabel.id = uid("page-icon");
  const grid = el("div", "icon-grid");
  grid.setAttribute("role", "radiogroup");
  grid.setAttribute("aria-labelledby", iconsLabel.id);
  // "Icon: Security", for the icon that is hovered, has focus or is chosen.
  const line = el("p", "small icon-line");
  line.dataset.test = "page-icon-line";
  const chosenName = PAGE_ICONS.includes(ctx.icon) ? t(PAGE_ICON_NAMES[ctx.icon]) : "";
  const showName = (name) => {
    line.textContent = name ? t("page.icon_line", { name }) : t("page.icon_none");
  };
  showName(chosenName);
  const buttons = [];
  const chosen = PAGE_ICONS.indexOf(ctx.icon);
  for (const [index, name] of PAGE_ICONS.entries()) {
    // A plain name, read out and shown as a tooltip.
    const plain = t(PAGE_ICON_NAMES[name]);
    const button = makeButton(null, {
      ariaLabel: plain,
      focus: `icon:${name}`,
      test: "page-icon",
      onClick: () => ctx.onIcon(name),
    });
    button.title = plain;
    button.dataset.icon = name;
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(ctx.icon === name));
    // One stop for the Tab key: the chosen icon, or the first.
    button.tabIndex = index === (chosen >= 0 ? chosen : 0) ? 0 : -1;
    button.append(icon(name));
    button.addEventListener("pointerenter", () => showName(plain));
    button.addEventListener("pointerleave", () => showName(grid.contains(grid.getRootNode().activeElement) ? null : chosenName));
    button.addEventListener("focus", () => showName(plain));
    button.addEventListener("blur", () => showName(chosenName));
    button.addEventListener("keydown", (event) =>
      radioKeys(event, buttons, index, 7, (next) => ctx.onIcon(PAGE_ICONS[next])),
    );
    buttons.push(button);
    grid.append(button);
  }
  icons.append(iconsLabel, grid, line);
  block.append(icons);

  const moves = el("div", "row-buttons");
  const earlier = makeButton(t("page.move_left"), {
    test: "page-left",
    focus: "page-left",
    focusAlt: "page-right",
    disabled: ctx.index <= 0,
    onClick: () => ctx.onMove(-1),
  });
  earlier.prepend(icon("mdi:arrow-left"));
  const later = makeButton(t("page.move_right"), {
    test: "page-right",
    focus: "page-right",
    focusAlt: "page-left",
    disabled: ctx.index >= ctx.count - 1,
    onClick: () => ctx.onMove(1),
  });
  later.prepend(icon("mdi:arrow-right"));
  moves.append(earlier, later);
  block.append(moves);

  block.append(
    makeButton(t("page.delete"), {
      kind: "danger",
      test: "page-delete",
      focus: "page-delete",
      disabled: ctx.count <= 1,
      onClick: ctx.onDelete,
    }),
  );
  if (ctx.count <= 1) {
    block.append(el("p", "helper", t("page.only_one")));
  }
  return block;
}

// The theme gallery: a radio group of swatch tiles painted from each
// theme's own colours (the wall, a card, the accent and the text), the
// chosen theme's description under it. ctx: { themes, themeId, readOnly,
// preview (the ids tagged "Preview"), onTheme(id) }.
export function buildThemeGallery(ctx) {
  const block = el("section", "form-block pop-form");
  block.append(popTitle(t("settings.theme")));
  const themes = (Array.isArray(ctx.themes) ? ctx.themes : []).filter((theme) => theme && typeof theme.id === "string");
  const group = el("div", "theme-grid");
  group.setAttribute("role", "radiogroup");
  group.setAttribute("aria-label", t("settings.theme"));
  group.dataset.test = "theme";
  group.dataset.value = ctx.themeId || "";
  // With more than nine themes, the dark ones and the light ones each
  // under a heading.
  const split = themes.length > 9;
  const ordered = split ? [...themes.filter((theme) => theme.dark), ...themes.filter((theme) => !theme.dark)] : themes;
  const tiles = [];
  const chosen = ordered.findIndex((theme) => theme.id === ctx.themeId);
  let heading = null;
  for (const [index, theme] of ordered.entries()) {
    if (split && heading !== Boolean(theme.dark)) {
      heading = Boolean(theme.dark);
      group.append(el("p", "theme-heading", t(heading ? "editor.theme_dark" : "editor.theme_light")));
    }
    const tile = makeButton(null, {
      className: "theme-tile",
      test: "theme-tile",
      focus: `theme:${theme.id}`,
      onClick: () => {
        if (!ctx.readOnly) {
          ctx.onTheme(theme.id);
        }
      },
    });
    tile.dataset.theme = theme.id;
    tile.setAttribute("role", "radio");
    tile.setAttribute("aria-checked", String(theme.id === ctx.themeId));
    if (ctx.readOnly) {
      tile.setAttribute("aria-disabled", "true");
    }
    tile.tabIndex = index === (chosen >= 0 ? chosen : 0) ? 0 : -1;
    const swatch = el("span", "theme-swatch");
    swatch.setAttribute("aria-hidden", "true");
    const colour = (value, fallback) => (isHex(value) ? value : fallback);
    swatch.style.backgroundColor = colour(theme.wall, "#101418");
    const card = el("span", "swatch-card");
    card.style.backgroundColor = colour(theme.card, "#181c23");
    const dot = el("span", "swatch-dot");
    dot.style.backgroundColor = colour(theme.acc, "#f5b547");
    const bar = el("span", "swatch-bar");
    bar.style.backgroundColor = colour(theme.tx, "#e8eaed");
    card.append(dot, bar);
    swatch.append(card);
    const title = typeof theme.name === "string" && theme.name ? theme.name : theme.id;
    // The name's line, with "Preview" after the name where it applies.
    const label = el("span", "theme-label");
    label.append(el("span", "theme-name", title));
    tile.append(swatch, label);
    if ((ctx.preview || []).includes(theme.id)) {
      // The tag is read after the name with a pause: "Glass, Preview".
      label.append(el("span", "tag theme-preview", t("editor.theme_preview")));
      tile.setAttribute("aria-label", `${title}, ${t("editor.theme_preview")}`);
    }
    tile.addEventListener("keydown", (event) =>
      radioKeys(event, tiles, index, 3, (next) => {
        if (!ctx.readOnly) {
          ctx.onTheme(ordered[next].id);
        }
      }),
    );
    tiles.push(tile);
    group.append(tile);
  }
  block.append(group);
  const current = themes.find((theme) => theme.id === ctx.themeId);
  if (current && typeof current.description === "string" && current.description) {
    const text = el("p", "theme-description", current.description);
    text.dataset.test = "theme-description";
    block.append(text);
  }
  block.append(el("p", "helper", t("settings.theme_helper")));
  return block;
}

// The menu of the top bar: Home Assistant's sidebar, the name for
// automations with a copy button, and Delete. Name, sidebar and delete are
// stored by Home Assistant itself, so a failure puts the control back and
// says so next to it. ctx.extra: controls that go first (Rename and Theme
// on a phone, the picture's size on a short screen).
export function buildDashboardSettings(ctx) {
  const block = el("section", "form-block pop-form");
  block.append(popTitle(t("settings.heading")));
  if (Array.isArray(ctx.extra) && ctx.extra.length) {
    const first = el("div", "menu-items");
    first.append(...ctx.extra);
    block.append(first);
  }

  const failure = (line, error) => {
    line.textContent = t("settings.failed", { message: error?.message || error?.code || "" });
  };

  if (!ctx.readOnly) {
    const sidebarAlert = el("p", "alert");
    sidebarAlert.setAttribute("role", "alert");
    const {
      field: sidebarField,
      input: sidebarInput,
      helper: sidebarHelper,
    } = switchRow({
      label: t("settings.sidebar"),
      help: t("settings.sidebar_helper"),
      checked: ctx.showInSidebar,
      focus: "dashboard-sidebar",
      test: "sidebar-checkbox",
      onChange: async (checked) => {
        try {
          await ctx.onSidebar(checked);
          sidebarAlert.textContent = "";
        } catch (error) {
          sidebarInput.checked = !checked;
          failure(sidebarAlert, error);
        }
      },
    });
    block.append(sidebarField, sidebarHelper, sidebarAlert);
  }

  // The address, for the show_dashboard action in automations.
  const name = el("div", "automation-name");
  name.dataset.test = "automation-name";
  const code = el("code", null, ctx.urlPath || "");
  const copy = makeButton(t("editor.copy"), {
    test: "automation-copy",
    focus: "automation-copy",
    onClick: async () => {
      try {
        await navigator.clipboard.writeText(ctx.urlPath || "");
        copy.textContent = t("editor.copied");
      } catch {
        // Without the clipboard the words are selected, ready to copy.
        const range = document.createRange();
        range.selectNodeContents(code);
        const selection = code.getRootNode().getSelection?.() || document.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(range);
      }
    },
  });
  copy.setAttribute("aria-label", `${t("editor.copy")} ${ctx.urlPath || ""}`);
  name.append(el("span", "field-label", t("editor.on_tablet_name")), code, copy);
  block.append(name);

  // There is deliberately no link to the dashboard in Home Assistant: its
  // own editor there offers cards the tablet cannot show.
  if (!ctx.readOnly) {
    const deleteAlert = el("p", "alert");
    deleteAlert.setAttribute("role", "alert");
    block.append(
      makeButton(t("settings.delete"), {
        kind: "danger",
        test: "dashboard-delete",
        focus: "dashboard-delete",
        onClick: async () => {
          try {
            await ctx.onDelete();
          } catch (error) {
            failure(deleteAlert, error);
          }
        },
      }),
      deleteAlert,
    );
  }
  return block;
}

// ---- the card's own rows (cards spec C.7) ----

// "A newer card does this: Light." on an older card, with the button that
// swaps it.
function newerCardNotice(ctx) {
  const notice = el("div", "newer-card");
  notice.dataset.test = "newer-card";
  notice.append(
    el("p", null, t("form.newer", { card: ctx.newer.name })),
    el("p", "helper", t("form.newer_helper")),
    makeButton(t("form.newer_go"), {
      test: "swap-card",
      focus: "swap-card",
      onClick: ctx.onSwap,
    }),
  );
  return notice;
}

// The line under a row the device cannot use: the file's reason, else the
// general one.
function reasonText(row) {
  const reason = row.reason || t("form.needs_general");
  // A file's reason is written without a full stop.
  return /[.!?]$/.test(reason) ? reason : `${reason}.`;
}

// The reason on its own line, with a mark, so what this device cannot do
// reads at once. The row's control names it as its description.
function reasonLine(node, text) {
  const line = el("p", "reason-line");
  line.id = uid("reason");
  line.dataset.test = "option-reason";
  line.append(icon("mdi:information-outline"), el("span", null, text));
  node.append(line);
  const controls = [];
  const walk = (parent) => {
    for (const child of parent.children || []) {
      if (["input", "select", "button"].includes(child.localName)) {
        controls.push(child);
      }
      walk(child);
    }
  };
  walk(node);
  for (const control of controls) {
    const before = control.getAttribute("aria-describedby");
    control.setAttribute("aria-describedby", before ? `${before} ${line.id}` : line.id);
  }
}

// The option names a `when` term reads ("show_brightness",
// "!bar_on_tile", "colour_control=dots|both"); facts ("can.colour") are not
// options.
function whenOptions(row) {
  const terms = Array.isArray(row.option.when) ? row.option.when : [];
  return terms
    .filter((term) => typeof term === "string")
    .map((term) => term.replace(/^!/, "").split(/!?=/)[0])
    .filter((name) => name && !name.includes("."));
}

// One row of the form for one option, with its label and help line; a row
// the device cannot use is drawn switched off and greyed, with the reason.
// A row that only shows when another option is on sits indented under it.
function optionRow(row, ctx, names = []) {
  const { option } = row;
  const focus = `option:${row.name}`;
  const disabled = !row.usable;
  const help = option.help || "";
  const change = (value, continuous = false) => ctx.onOption(row.name, value, row.fallback, continuous);
  let node;
  switch (option.type) {
    case "toggle": {
      const { field, helper } = switchRow({
        label: option.label,
        help,
        checked: row.value === true,
        disabled,
        focus,
        onChange: (checked) => change(checked),
      });
      node = el("div", "option-switch");
      node.append(field);
      if (helper) {
        node.append(helper);
      }
      break;
    }
    case "choice":
      node = option.multiple === true ? tickList(row, ctx, help, focus, disabled, change) : choiceList(row, help, focus, disabled, change);
      break;
    case "colours":
      node = swatchRow(row, help, focus, disabled, change);
      break;
    case "text": {
      const { field, input } = textInput({
        label: option.label,
        value: typeof row.value === "string" ? row.value : "",
        maxLength: Number(option.max) || 40,
        focus,
        helper: help,
        onInput: (text) => change(text, true),
      });
      input.disabled = disabled;
      node = field;
      break;
    }
    case "number":
      node = numberOption(row, help, focus, disabled, change);
      break;
    case "colour":
      node = colourOption(row, ctx, help, focus, disabled, change);
      break;
    case "icon":
      node = iconChoice({
        label: option.label,
        value: row.value,
        focus,
        disabled,
        help,
        onChange: (name) => change(name),
      });
      break;
    default:
      return null;
  }
  // A row the card's present size does not draw says so (A6).
  if (Array.isArray(row.onlyOn) && row.onlyOn.length && !disabled) {
    const line = el("p", "helper size-only", t("form.shows_on", { sizes: row.onlyOn.join(", ") }));
    line.dataset.test = "option-size-only";
    node.append(line);
  }
  if (disabled) {
    reasonLine(node, reasonText(row));
  }
  node.dataset.test = "option-row";
  node.dataset.option = row.name;
  node.dataset.usable = String(row.usable);
  node.classList.add("option-row");
  node.classList.toggle("unusable", disabled);
  node.classList.toggle("option-dependent", whenOptions(row).some((name) => names.includes(name)));
  return node;
}

// One choice: up to four as a segmented control, more as a list field. A
// greyed choice marks none, not the value it counts as ("Off"), which
// would read like a choice the person made.
function choiceList(row, help, focus, disabled, change) {
  const { option } = row;
  const choices = Array.isArray(option.choices) ? option.choices : row.listed.map((value) => ({ value, label: value }));
  if (choices.length <= 4 && choices.length > 0) {
    const field = segmented({
      label: option.label,
      choices: choices.map((choice) => [String(choice.value), String(choice.label)]),
      value: disabled || row.value === null || row.value === undefined ? "" : String(row.value),
      focus,
      disabled,
      onChange: (value) => change(value),
    });
    if (help) {
      field.append(el("span", "helper", help));
    }
    return field;
  }
  const options = disabled
    ? [["", "–"]]
    : choices.map((choice) => [String(choice.value), String(choice.label)]);
  const { field, control } = select({
    label: option.label,
    options,
    value: disabled || row.value === null || row.value === undefined ? "" : String(row.value),
    focus,
    onChange: (value) => change(value),
  });
  control.disabled = disabled;
  if (help) {
    field.append(el("span", "helper", help));
  }
  return field;
}

// A multiple choice: the file's choices or what the device reports, as a
// list of switches, at most `max` on.
function tickList(row, ctx, help, focus, disabled, change) {
  const { option } = row;
  const wrap = el("div", "field tick-list");
  const labelId = uid("ticks");
  const label = el("span", "field-label", option.label);
  label.id = labelId;
  wrap.append(label);
  const choices = Array.isArray(option.choices)
    ? option.choices.map((choice) => [choice.value, choice.label])
    : row.listed.map((value) => [value, value]);
  const chosen = Array.isArray(row.value) ? row.value : [];
  const max = Number(option.max) || 8;
  if (!row.known) {
    wrap.append(el("span", "helper", t("form.choose_device_first")));
    return wrap;
  }
  if (!choices.length) {
    // A greyed list says why on its own line; its help line stays.
    if (!disabled || help) {
      wrap.append(el("span", "helper", disabled ? help : t("form.list_empty")));
    }
    return wrap;
  }
  const list = el("div", "ticks");
  list.setAttribute("role", "group");
  list.setAttribute("aria-labelledby", labelId);
  choices.forEach(([value, text], index) => {
    const on = chosen.includes(value);
    const { field } = switchRow({
      label: String(text),
      checked: on,
      disabled: disabled || (!on && chosen.length >= max),
      focus: `${focus}:${index}`,
      onChange: (checked) => {
        // Kept in the order the device or the file lists them.
        const next = choices.map(([entry]) => entry).filter((entry) => (entry === value ? checked : chosen.includes(entry)));
        change(next);
      },
    });
    list.append(field);
  });
  wrap.append(list, el("span", "helper", [t("form.chosen_of", { count: chosen.length, max }), help].filter(Boolean).join(" ")));
  return wrap;
}

const KELVIN_RE = /^(\d{4,5})K$/;

function swatchHex(entry) {
  const kelvin = typeof entry === "string" ? KELVIN_RE.exec(entry) : null;
  if (kelvin) {
    return rgbToHex(kelvinRgb(Number(kelvin[1])));
  }
  return typeof entry === "string" && /^#[0-9A-Fa-f]{6}$/.test(entry) ? entry.toLowerCase() : "#ffffff";
}

// A list of colours: a row of swatches, each one a colour well that can be
// changed, then Add and Remove. A white of some warmth ("2700K") is a
// swatch too; changing it makes it a colour.
function swatchRow(row, help, focus, disabled, change) {
  const { option } = row;
  const wrap = el("div", "field swatch-field");
  const labelId = uid("swatches");
  const label = el("span", "field-label", option.label);
  label.id = labelId;
  const list = Array.isArray(row.value) ? [...row.value] : [];
  const max = Number(option.max) || 8;
  const swatches = el("div", "swatches");
  swatches.setAttribute("role", "group");
  swatches.setAttribute("aria-labelledby", labelId);
  list.forEach((entry, index) => {
    const input = document.createElement("input");
    input.type = "color";
    input.value = swatchHex(entry);
    input.disabled = disabled;
    input.dataset.focus = `${focus}:${index}`;
    input.dataset.test = "swatch";
    const kelvin = typeof entry === "string" ? KELVIN_RE.exec(entry) : null;
    const name = kelvin ? t("form.colour_white", { kelvin: kelvin[1] }) : t("form.colour_n", { n: index + 1 });
    // Under 4000 K a white looks orange on the swatch, so it says warm.
    const warm = kelvin && Number(kelvin[1]) < 4000;
    input.setAttribute("aria-label", name);
    input.title = name;
    input.addEventListener("input", () => {
      const next = [...list];
      next[index] = input.value.toUpperCase();
      change(next, true);
    });
    // A white is named under its swatch, so it does not read as an orange.
    const swatch = el("span", "swatch");
    swatch.append(input);
    if (kelvin) {
      swatch.append(el("span", "swatch-mark", t(warm ? "form.colour_warm_mark" : "form.colour_white_mark")));
    }
    swatches.append(swatch);
  });
  // Add is hidden at the most the card can show; Remove then takes its
  // focus.
  const full = list.length >= max;
  const add = makeButton(t("form.colour_add"), {
    kind: "text",
    test: "swatch-add",
    focus: `${focus}:add`,
    focusAlt: `${focus}:remove`,
    disabled: disabled || full,
    onClick: () => change([...list, "#FFFFFF"]),
  });
  add.hidden = full;
  const buttons = el("div", "row-buttons");
  buttons.append(
    add,
    makeButton(t("form.colour_remove"), {
      kind: "text",
      test: "swatch-remove",
      focus: `${focus}:remove`,
      focusAlt: `${focus}:add`,
      disabled: disabled || !list.length,
      onClick: () => change(list.slice(0, -1)),
    }),
  );
  wrap.append(label, swatches, buttons, el("span", "helper", [t("form.colour_max", { max }), help].filter(Boolean).join(" ")));
  return wrap;
}

// A number: the field with its unit beside it, and small minus and plus
// buttons that step by the file's step and stop at its limits.
function numberOption(row, help, focus, disabled, change) {
  const { option } = row;
  const wrap = el("div", "field");
  const labelNode = el("label", "field-label", option.label);
  const line = el("div", "number-row");
  const input = document.createElement("input");
  input.type = "number";
  input.id = uid("number");
  labelNode.htmlFor = input.id;
  input.step = option.step ? String(option.step) : "any";
  if (Number.isFinite(option.min)) {
    input.min = String(option.min);
  }
  if (Number.isFinite(option.max)) {
    input.max = String(option.max);
  }
  input.value = Number.isFinite(row.value) ? String(row.value) : "";
  input.disabled = disabled;
  input.dataset.focus = focus;
  const fits = (number) =>
    Number.isFinite(number)
    && !(Number.isFinite(option.min) && number < option.min)
    && !(Number.isFinite(option.max) && number > option.max);
  input.addEventListener("input", () => {
    const raw = input.value.trim();
    const number = Number(raw);
    if (!raw) {
      change(undefined, true);
    } else if (fits(number)) {
      change(number, true);
    }
  });
  const step = Number(option.step) || 1;
  const current = () => (Number.isFinite(Number(input.value)) && input.value !== "" ? Number(input.value) : Number(row.value) || 0);
  const nudge = (sign) => {
    let next = Math.round((current() + sign * step) * 1000) / 1000;
    if (Number.isFinite(option.min)) {
      next = Math.max(option.min, next);
    }
    if (Number.isFinite(option.max)) {
      next = Math.min(option.max, next);
    }
    input.value = String(next);
    change(next);
  };
  const less = makeButton(null, { kind: "icon", focus: `${focus}:less`, ariaLabel: t("form.less", { name: option.label }), disabled, onClick: () => nudge(-1) });
  less.append(icon("mdi:minus"));
  const more = makeButton(null, { kind: "icon", focus: `${focus}:more`, ariaLabel: t("form.more", { name: option.label }), disabled, onClick: () => nudge(1) });
  more.append(icon("mdi:plus"));
  line.append(less, input);
  if (option.unit) {
    line.append(el("span", "number-unit", String(option.unit)));
  }
  line.append(more);
  wrap.append(labelNode, line);
  if (help) {
    wrap.append(el("span", "helper", help));
  }
  return wrap;
}

// The colour roles of a theme, by their plain names (C.2.3), with the
// theme's key for each and a colour where the theme has none.
const COLOUR_ROLES = [
  ["accent", "form.role_accent", "acc", "#F5B547"],
  ["accent2", "form.role_accent2", "acc2", "#6CB4FF"],
  ["good", "form.role_good", "good", "#32D74B"],
  ["warn", "form.role_warn", "warn", "#FFD60A"],
  ["bad", "form.role_bad", "bad", "#FF453A"],
  ["info", "form.role_info", "info", "#64D2FF"],
  ["text", "form.role_text", "tx", "#E8EAED"],
  ["muted", "form.role_muted", "tx2", "#9AA0A8"],
];

// One colour: a swatch row of the theme's roles by name, then a colour of
// one's own.
function colourOption(row, ctx, help, focus, disabled, change) {
  const { option } = row;
  const themes = Array.isArray(ctx.themes) ? ctx.themes : [];
  const theme = themes.find((entry) => entry.id === (ctx.card?.style?.theme || ctx.dashboardTheme)) || themes[0] || {};
  const entries = COLOUR_ROLES.map(([role, key, themeKey, fallback]) => ({
    value: role,
    name: t(key),
    fill: isHex(theme[themeKey]) ? theme[themeKey] : fallback,
  }));
  const field = swatchGroup({
    label: option.label,
    entries,
    value: typeof row.value === "string" ? row.value : null,
    own: true,
    focus,
    onPick: (value) => change(value),
    onOwn: (value, continuous) => change(value, continuous),
  });
  if (disabled) {
    for (const node of field.descendants ? field.descendants() : field.querySelectorAll("button, input")) {
      if (["button", "input"].includes(node.localName)) {
        node.disabled = true;
      }
    }
  }
  if (help) {
    field.append(el("span", "helper", help));
  }
  return field;
}

// The icon as one line, "Icon: The device's own", with Change, which opens
// the grid of the icons that have plain names after "The device's own"
// (A24). A pick draws the form again, folded, with the new icon.
// `own` is the device's icon, shown while none is picked.
function iconChoice({ label, value, own = null, focus, disabled = false, help = "", onChange }) {
  const wrap = el("div", "field icon-choice");
  let open = false;
  const draw = () => {
    const labelNode = el("span", "field-label", label);
    labelNode.id = uid("icon");
    wrap.append(labelNode);
    if (!open) {
      const line = el("div", "icon-current");
      const shown = isIcon(value) ? value : own;
      const words = isIcon(value) ? t(PAGE_ICON_NAMES[value] || "form.icon") : t("form.icon_default");
      if (isIcon(shown)) {
        line.append(icon(shown));
      }
      const change = makeButton(t("form.icon_change"), {
        kind: "text",
        test: "icon-change",
        focus: `${focus}:change`,
        ariaLabel: `${t("form.icon_change")}: ${label}`,
        disabled,
        onClick: () => {
          open = true;
          redraw(wrap, draw);
          wrap.querySelector('[aria-pressed="true"]')?.focus();
        },
      });
      change.dataset.focusTakes = `${focus}:`;
      line.append(el("span", "icon-current-name", words), change);
      wrap.append(line);
    } else {
      const grid = el("div", "icon-grid");
      grid.setAttribute("role", "group");
      grid.setAttribute("aria-labelledby", labelNode.id);
      const ownButton = makeButton(t("form.icon_default"), {
        className: "icon-default",
        focus: `${focus}:default`,
        focusAlt: `${focus}:change`,
        test: "card-icon-default",
        disabled,
        onClick: () => onChange(undefined),
      });
      ownButton.setAttribute("aria-pressed", String(!isIcon(value)));
      grid.append(ownButton);
      for (const name of PAGE_ICONS) {
        const plain = t(PAGE_ICON_NAMES[name]);
        const button = makeButton(null, {
          ariaLabel: plain,
          focus: `${focus}:${name}`,
          focusAlt: `${focus}:change`,
          test: "card-icon",
          disabled,
          onClick: () => onChange(name),
        });
        button.title = plain;
        button.dataset.icon = name;
        button.setAttribute("aria-pressed", String(value === name));
        button.append(icon(name));
        grid.append(button);
      }
      wrap.append(grid);
    }
    if (help) {
      wrap.append(el("span", "helper", help));
    }
  };
  draw();
  return wrap;
}

// The rows of one part from the card's options; a kind of option this
// panel does not know is left out with one quiet line (A12). A row the
// card's present size does not draw names the sizes that do (A6).
function optionRows(form, section, ctx, names = []) {
  const nodes = [];
  let unknown = false;
  const shownSize = form.sizes.find((size) => size.id === form.variant);
  for (const row of form.rows) {
    if (row.option.section !== section || !row.shown) {
      continue;
    }
    if (!row.supported) {
      unknown = true;
      continue;
    }
    const drawnOn = form.sizes.filter((size) => size.offered && Array.isArray(size.uses) && size.uses.includes(row.name));
    row.onlyOn = shownSize && Array.isArray(shownSize.uses) && !shownSize.uses.includes(row.name) && drawnOn.length
      ? drawnOn.map((size) => size.name)
      : null;
    const node = optionRow(row, ctx, names);
    if (node) {
      nodes.push(node);
    }
  }
  if (unknown) {
    const line = el("p", "helper", t("form.option_unknown"));
    line.dataset.test = "option-unknown";
    nodes.push(line);
  }
  return nodes;
}

// The named sizes as one radio group: a press picks the size, and the card
// takes its size on the grid. The size marked is the one the picture
// shows; a press on it puts the card back to that size after the steps
// changed it. A size the device cannot use is not offered; its reason is
// said under the group.
function sizeChips(form, ctx) {
  return (block, card) => {
    if (form.sizes.length < 2) {
      return;
    }
    const shown = activeVariant(card, ctx.component, form.sizes);
    const field = el("div", "field");
    const labelNode = el("span", "field-label", t("form.size"));
    labelNode.id = uid("size-label");
    const group = el("div", "segmented size-chips");
    group.setAttribute("role", "radiogroup");
    group.setAttribute("aria-labelledby", labelNode.id);
    const name = uid("size");
    for (const size of form.sizes) {
      if (!size.offered) {
        continue;
      }
      const label = el("label");
      label.dataset.test = "size-chip";
      label.dataset.variant = size.id;
      const input = el("input");
      input.type = "radio";
      input.name = name;
      input.value = size.id;
      input.checked = shown === size.id;
      input.dataset.focus = `size:${size.id}`;
      const marked = input.checked;
      input.addEventListener("change", () => ctx.onVariant(size.id));
      // A radio already on fires no change, only a click.
      input.addEventListener("click", () => {
        if (marked) {
          ctx.onVariant(size.id);
        }
      });
      label.append(input, el("span", null, size.name));
      group.append(label);
    }
    field.append(labelNode, group);
    block.append(field);
    for (const size of form.sizes.filter((entry) => !entry.offered)) {
      const line = el("p", "helper", t("form.size_not_offered", { size: size.name, reason: size.reason || t("form.needs_general") }));
      line.dataset.test = "size-not-offered";
      block.append(line);
    }
  };
}

// The looks of a card while it is on (style.lit, E.1).
const LIT_LOOKS = {
  fill: "form.lit_fill",
  icon: "form.lit_icon",
  outline: "form.lit_outline",
  none: "form.lit_none",
};
