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

function colourInput({ label, rgb, focus, onInput }) {
  const field = el("label", "field");
  const input = document.createElement("input");
  input.type = "color";
  input.value = rgbToHex(rgb);
  input.dataset.focus = focus;
  input.addEventListener("input", () => onInput(hexToRgbList(input.value)));
  field.append(el("span", "field-label", label), input);
  return field;
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

// Returns a DOM node. onChange(value) gets the new param value (string,
// string[], number or undefined). In the card form (collapsed) an entity
// field shows the chosen device and opens its list on request.
export function buildParamField({
  hass,
  field,
  value,
  config,
  compact = false,
  collapsed = false,
  onChange,
}) {
  void compact;
  if (field.kind === "entity") {
    return entityField({ hass, field, value, collapsed, onChange });
  }
  if (field.kind === "number") {
    return numberField({ field, value, onChange });
  }
  if (field.kind === "page") {
    return pageField({ field, value, config, onChange });
  }
  return el("div");
}

function entityField({ hass, field, value, collapsed, onChange }) {
  const wrap = el("div", "field");
  wrap.dataset.param = field.name;
  const label = field.label || whichLabel(field.domain);
  let chosen = field.multiple
    ? (Array.isArray(value) ? value : []).filter((id) => typeof id === "string").slice(0, MAX_ENTITIES)
    : typeof value === "string"
      ? value
      : "";
  let open = !collapsed;
  let query = "";

  const chosenNames = () =>
    field.multiple
      ? chosen.map((id) => entityName(hass, id)).join(", ")
      : chosen
        ? entityName(hass, chosen)
        : "";

  const drawClosed = () => {
    wrap.replaceChildren();
    const row = el("div", "chosen");
    const names = chosenNames();
    row.append(el("span", null, names || t("form.none_chosen")));
    // "Change" would suggest something is chosen already.
    const action = names ? t("form.change_device") : t("form.choose_device");
    row.append(
      makeButton(action, {
        kind: names ? "text" : undefined,
        test: "change-device",
        focus: `change-device:${field.name}`,
        ariaLabel: `${action}: ${label}`,
        onClick: () => {
          open = true;
          drawOpen(true);
        },
      }),
    );
    wrap.append(el("span", "field-label", label), row);
  };

  const drawOpen = (focusSearch) => {
    wrap.replaceChildren();
    const listId = uid("entities");
    const searchField = el("label", "field");
    const search = document.createElement("input");
    search.type = "search";
    search.value = query;
    search.placeholder = t("pick.search");
    search.autocomplete = "off";
    search.dataset.test = "entity-search";
    search.dataset.focus = `entity-search:${field.name}`;
    search.setAttribute("aria-controls", listId);
    searchField.append(el("span", "field-label", label), search);
    wrap.append(searchField);

    let counter = null;
    if (field.multiple) {
      counter = el("p", "helper", t("pick.chosen", { count: chosen.length }));
      counter.setAttribute("aria-live", "polite");
      wrap.append(el("p", "helper", t("pick.many_hint", { max: MAX_ENTITIES })), counter);
    }

    const list = el("div", "entity-list");
    list.id = listId;
    list.setAttribute("role", "listbox");
    list.setAttribute("aria-label", label);
    if (field.multiple) {
      list.setAttribute("aria-multiselectable", "true");
    }
    const message = el("div", "field");
    wrap.append(list, message);

    const fill = () => {
      const active = list.getRootNode().activeElement;
      const focusedEntity = active && list.contains(active) ? active.dataset.entity : null;
      list.replaceChildren();
      message.replaceChildren();

      if (!entityChoices(hass, field, "").length) {
        list.hidden = true;
        message.append(el("strong", null, t("pick.none_title")), el("p", "helper", t("pick.none_text")));
        return;
      }
      const choices = entityChoices(hass, field, query);
      list.hidden = !choices.length;
      if (!choices.length) {
        message.append(el("p", "helper", t("pick.no_match", { query: query.trim() })));
        return;
      }

      for (const choice of choices) {
        const selected = field.multiple
          ? chosen.includes(choice.entity_id)
          : chosen === choice.entity_id;
        const option = makeButton(null, { className: "entity-option", test: "entity" });
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", String(selected));
        option.dataset.entity = choice.entity_id;
        const name = el("span", "entity-name");
        if (selected) {
          name.append(el("span", "entity-check", "✓ "));
        }
        name.append(choice.name);
        option.append(
          name,
          el("small", null, [choice.area, choice.entity_id].filter(Boolean).join(" · ")),
        );
        if (field.multiple && !selected && chosen.length >= MAX_ENTITIES) {
          option.disabled = true;
        }
        option.addEventListener("click", () => {
          if (field.multiple) {
            chosen = selected
              ? chosen.filter((id) => id !== choice.entity_id)
              : [...chosen, choice.entity_id];
            counter.textContent = t("pick.chosen", { count: chosen.length });
            fill();
            onChange(chosen.length ? [...chosen] : undefined);
            return;
          }
          chosen = choice.entity_id;
          if (collapsed) {
            open = false;
            drawClosed();
            wrap.querySelector("button")?.focus();
          } else {
            fill();
          }
          onChange(choice.entity_id);
        });
        list.append(option);
      }

      if (focusedEntity) {
        [...list.querySelectorAll("[data-entity]")]
          .find((node) => node.dataset.entity === focusedEntity)
          ?.focus();
      }
    };

    search.addEventListener("input", () => {
      query = search.value;
      fill();
    });
    fill();
    if (focusSearch) {
      search.focus();
    }
  };

  if (open) {
    drawOpen(false);
  } else {
    drawClosed();
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
  wrap.append(el("span", "field-label", labelForName(field.name)), input);
  return wrap;
}

function pageField({ field, value, config, onChange }) {
  const { field: wrap } = select({
    label: t("pick.page"),
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
export function fillItemNotes(container, row, { onOpenAdvanced } = {}) {
  if (!container) {
    return;
  }
  container.replaceChildren();
  if (!row) {
    return;
  }
  for (const code of row.notes || []) {
    container.append(el("p", "note-line", t(`warn.${code}`, { detail: row.detail || "" })));
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
  return heading;
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

function positionBlock({ canEarlier, canLater, onMove, pages, onMoveToPage }) {
  const block = el("div", "form-block");
  const buttons = el("div", "row-buttons");
  buttons.append(
    makeButton(t("form.move_earlier"), {
      test: "move-earlier",
      focus: "move-earlier",
      focusAlt: "move-later",
      disabled: !canEarlier,
      onClick: () => onMove(-1),
    }),
    makeButton(t("form.move_later"), {
      test: "move-later",
      focus: "move-later",
      focusAlt: "move-earlier",
      disabled: !canLater,
      onClick: () => onMove(1),
    }),
  );
  block.append(el("h3", null, t("form.order")), buttons, el("p", "helper", t("form.order_helper")));
  if (onMoveToPage) {
    block.append(moveToPageBlock({ pages, onMoveToPage }));
  }
  return block;
}

// The form for a TAB-1 card. The callbacks receive plain values; the editor
// turns them into config changes. continuous is true for typing and
// dragging, which are saved as one undo step.
export function buildCardForm(ctx) {
  const { card, component, readOnly } = ctx;
  if (component.schema === 2) {
    return buildCardForm2(ctx);
  }
  const form = el("div", "form-block");
  form.append(itemHeading(component.name));
  if (component.description) {
    form.append(el("p", "helper", component.description));
  }
  form.append(el("div", "item-notes"));
  if (readOnly) {
    return form;
  }
  if (ctx.newer) {
    form.append(newerCardNotice(ctx));
  }

  const fields = formFields(component);
  if (fields.length) {
    const device = el("div", "form-block");
    device.append(el("h3", null, t("form.device")));
    for (const field of fields) {
      device.append(
        buildParamField({
          hass: ctx.hass,
          field,
          value: card.params?.[field.name],
          config: ctx.config,
          compact: ctx.compact,
          collapsed: true,
          onChange: (value) => ctx.onParam(field.name, value, field.kind === "number"),
        }),
      );
    }
    form.append(device);
  }

  const { field: nameField } = textInput({
    label: t("form.name"),
    value: typeof card.title === "string" ? card.title : "",
    maxLength: 60,
    test: "form-name",
    helper: t("form.name_helper"),
    onInput: (text) => ctx.onTitle(text),
  });
  form.append(nameField);

  form.append(sizeBlock(ctx), lookBlock(ctx));
  form.append(positionBlock(ctx));
  form.append(
    makeButton(t("form.remove"), {
      kind: "danger",
      test: "remove-card",
      focus: "remove-card",
      onClick: ctx.onRemove,
    }),
  );
  return form;
}

// The cards whose Width and Height steps were opened, so they stay open
// while the form is drawn again or the card moves.
const fineTuneOpen = new Set();

// Size. A card with named sizes (cards spec C.7) shows them as the main
// control; Width and Height wait behind "Fine-tune the size" until the
// card's size differs from the size marked. `form` is the schema 2 form.
function sizeBlock(ctx, form = null) {
  const block = el("div", "form-block");
  let size = cardSize(ctx.card, ctx.component);
  // The card as the steps leave it, for the named sizes: the steps drop
  // the picked size (designer.js onResize), so the size follows the grid.
  let card = ctx.card;
  const named = form && form.sizes.length > 1;
  // The card by its kind and devices, which stay the same when it moves.
  const openKey = `${ctx.component.id}|${JSON.stringify(ctx.card.params ?? {})}`;

  const resize = (w, h) => {
    const width = Math.min(ctx.maxWide, Math.max(1, w));
    const height = Math.min(MAX_UNITS_HIGH, Math.max(1, h));
    size = { w: width, h: height, exact: true };
    card = { ...card, variant: undefined, grid_options: { ...card.grid_options, columns: width * UNIT_COLUMNS, rows: height * UNIT_ROWS } };
    ctx.onResize(width, height);
    redraw(block, draw);
  };

  const draw = () => {
    block.append(el("h3", null, t("form.size")));
    let shown = null;
    let tuned = false;
    if (named) {
      sizeChips(form, ctx)(block, card);
      const id = activeVariant(card, ctx.component, form.sizes);
      shown = form.sizes.find((entry) => entry.id === id) || null;
      tuned = Boolean(shown)
        && (!size.exact || size.w * UNIT_COLUMNS !== shown.grid[0] || size.h * UNIT_ROWS !== shown.grid[1]);
      if (!tuned && !fineTuneOpen.has(openKey)) {
        block.append(
          makeButton(t("form.size_fine"), {
            kind: "text",
            test: "size-fine-tune",
            focus: "size-fine-tune",
            onClick: () => {
              fineTuneOpen.add(openKey);
              redraw(block, draw);
              restoreFocus(block, "wider");
            },
          }),
        );
        return;
      }
    }
    // Once shown, the steps stay while this card is edited.
    if (named) {
      fineTuneOpen.add(openKey);
    }
    const value = el("p", "size-value", t("form.size_value", { w: size.w, h: size.h }));
    value.setAttribute("aria-live", "polite");
    const width = el("div", "stepper");
    width.append(
      el("span", "stepper-label", t("form.width")),
      makeButton(t("form.narrower"), {
        test: "narrower",
        focus: "narrower",
        focusAlt: "wider",
        disabled: size.w <= 1,
        onClick: () => resize(size.w - 1, size.h),
      }),
      makeButton(t("form.wider"), {
        test: "wider",
        focus: "wider",
        focusAlt: "narrower",
        disabled: size.w >= ctx.maxWide,
        onClick: () => resize(size.w + 1, size.h),
      }),
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
    const height = el("div", "stepper");
    height.append(
      el("span", "stepper-label", t("form.height")),
      makeButton(t("form.shorter"), {
        test: "shorter",
        focus: "shorter",
        focusAlt: "taller",
        disabled: size.h <= 1,
        onClick: () => resize(size.w, size.h - 1),
      }),
      makeButton(t("form.taller"), {
        test: "taller",
        focus: "taller",
        focusAlt: "shorter",
        disabled: size.h >= MAX_UNITS_HIGH,
        onClick: () => resize(size.w, size.h + 1),
      }),
    );
    block.append(value, width);
    if (columns) {
      block.append(columns);
    }
    block.append(height);
    if (named) {
      // Back to the size marked, shown only while the card differs from it.
      if (tuned) {
        block.append(
          makeButton(t("form.size_back", { size: shown.name }), {
            kind: "text",
            test: "size-reset",
            focus: "size-reset",
            onClick: () => ctx.onVariant(shown.id),
          }),
        );
      }
      block.append(el("p", "helper", t("form.size_fits")));
    } else {
      const own = Array.isArray(ctx.component.size) ? ctx.component.size : [1, 1];
      block.append(
        makeButton(t("form.size_reset"), {
          kind: "text",
          test: "size-reset",
          focus: "size-reset",
          onClick: () => resize(Number(own[0]) || 1, Number(own[1]) || 1),
        }),
      );
    }
    if (!size.exact) {
      block.append(el("p", "helper", t("form.size_odd")));
    }
  };

  draw();
  return block;
}

function lookBlock(ctx) {
  const block = el("div", "form-block");
  let data = styleToForm(ctx.card.style || {});
  const themes = Array.isArray(ctx.themes) ? ctx.themes : [];
  const themeFor = () =>
    themes.find((theme) => theme.id === (data.theme || ctx.dashboardTheme)) || themes[0] || {};

  const change = (patch, field, continuous = false) => {
    data = styleDefaults({ ...data, ...patch }, themeFor());
    ctx.onStyle(formToStyle(data), field, continuous);
    if (!continuous) {
      redraw(block, draw);
    }
  };

  const draw = () => {
    block.append(el("h3", null, t("form.look")));
    // A schema 2 card's own look rows come first (C.7).
    ctx.lookRows?.(block);
    const { field: themeField } = select({
      label: t("form.theme"),
      options: [["", t("form.theme_dashboard")], ...themes.map((theme) => [theme.id, theme.name])],
      value: data.theme || "",
      focus: "look-theme",
      test: "card-theme",
      onChange: (value) => change({ theme: value }, "theme"),
    });
    // Every new card is selected, so this is often the only theme in view.
    themeField.append(el("span", "helper", t("form.theme_helper")));
    block.append(themeField);

    block.append(
      switchRow({
        label: t("form.use_color"),
        checked: data.use_color,
        focus: "look-use-color",
        onChange: (checked) => change({ use_color: checked }, "use_color"),
      }).field,
    );
    if (data.use_color) {
      block.append(
        colourInput({
          label: t("form.color"),
          rgb: data.color,
          focus: "look-color",
          onInput: (rgb) => change({ color: rgb }, "color", true),
        }),
      );
    }

    block.append(
      select({
        label: t("form.gradient"),
        options: [
          ["none", t("form.gradient_none")],
          ["vertical", t("form.gradient_vertical")],
          ["horizontal", t("form.gradient_horizontal")],
        ],
        value: data.gradient || "none",
        focus: "look-gradient",
        onChange: (value) => change({ gradient: value }, "gradient"),
      }).field,
    );
    if (data.gradient && data.gradient !== "none") {
      block.append(
        colourInput({
          label: t("form.gradient_to"),
          rgb: data.gradient_to,
          focus: "look-gradient-to",
          onInput: (rgb) => change({ gradient_to: rgb }, "gradient_to", true),
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
    const output = el("output", null, range.value);
    // The track is filled up to the knob (see input[type="range"] in styles.js).
    const fill = () => range.style.setProperty("--tab-range-fill", String(Number(range.value) / 100));
    fill();
    range.addEventListener("input", () => {
      output.textContent = range.value;
      fill();
      change({ transparency: Number(range.value) }, "transparency", true);
    });
    row.append(range, output);
    transparency.append(
      el("span", "field-label", t("form.transparency")),
      row,
      el("span", "helper", t("form.transparency_helper")),
    );
    block.append(transparency);

    // What the highlight colour changes on the tablet (see resolve_style in
    // maker/style.py and the "is-on" rules of the card styles).
    const { field: accentField, helper: accentHelper } = switchRow({
      label: t("form.use_accent"),
      help: t("form.accent_helper"),
      checked: data.use_accent,
      focus: "look-use-accent",
      onChange: (checked) => change({ use_accent: checked }, "use_accent"),
    });
    accentHelper.dataset.test = "accent-helper";
    block.append(accentField, accentHelper);
    if (data.use_accent) {
      block.append(
        colourInput({
          label: t("form.accent"),
          rgb: data.accent,
          focus: "look-accent",
          onInput: (rgb) => change({ accent: rgb }, "accent", true),
        }),
      );
    }
  };

  draw();
  return block;
}

// A heading card or a section title. Section titles have no position of
// their own: they always sit at the top of their section.
export function buildHeadingForm(ctx) {
  const form = el("div", "form-block");
  form.append(itemHeading(t("form.heading_title")), el("div", "item-notes"));
  if (ctx.readOnly) {
    form.append(el("p", null, ctx.text));
    return form;
  }
  const { field } = textInput({
    label: t("form.heading_text"),
    value: ctx.text,
    maxLength: 80,
    test: "heading-text",
    onInput: (text) => ctx.onText(text),
  });
  form.append(field);
  if (ctx.isCard) {
    form.append(positionBlock(ctx));
  }
  form.append(
    makeButton(t("form.remove_heading"), {
      kind: "danger",
      test: "remove-heading",
      focus: "remove-heading",
      onClick: ctx.onRemove,
    }),
  );
  return form;
}

// Anything the tablet cannot draw: the reason, and a way to remove it.
export function buildOtherForm(ctx) {
  const form = el("div", "form-block");
  form.append(itemHeading(t("form.other_title")));
  if (ctx.name) {
    form.append(el("p", null, ctx.name));
  }
  // The device it was set up for, which a TAB-1 card can take over.
  if (ctx.device) {
    const line = el("p", null, t("form.other_device", { device: ctx.device }));
    line.dataset.test = "other-device";
    form.append(line);
  }
  form.append(el("div", "item-notes"));
  if (!ctx.readOnly) {
    form.append(makeButton(t("list.remove"), { kind: "danger", test: "remove-item", onClick: ctx.onRemove }));
  }
  return form;
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

// ---- the form of a schema 2 card (cards spec C.7) ----

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

// The heading of one part of the form: Device, Size, What it shows,
// Controls, Look.
function partHeading(text) {
  return el("h3", null, text);
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
      node = colourOption(row, help, focus, disabled, change);
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

function choiceList(row, help, focus, disabled, change) {
  const { option } = row;
  const choices = Array.isArray(option.choices) ? option.choices : row.listed.map((value) => ({ value, label: value }));
  // A greyed list shows a dash, not the value it counts as ("Off"), which
  // would read like a choice the person made.
  const options = disabled
    ? [["", "\u2013"]]
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

function numberOption(row, help, focus, disabled, change) {
  const { option } = row;
  const wrap = el("label", "field");
  const input = document.createElement("input");
  input.type = "number";
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
  input.addEventListener("input", () => {
    const raw = input.value.trim();
    const number = Number(raw);
    if (!raw) {
      change(undefined, true);
    } else if (
      Number.isFinite(number)
      && !(Number.isFinite(option.min) && number < option.min)
      && !(Number.isFinite(option.max) && number > option.max)
    ) {
      change(number, true);
    }
  });
  const words = option.unit ? `${option.label} (${option.unit})` : option.label;
  wrap.append(el("span", "field-label", words), input);
  if (help) {
    wrap.append(el("span", "helper", help));
  }
  return wrap;
}

// The colour roles of a theme, by their plain names (C.2.3).
const COLOUR_ROLES = {
  accent: "form.role_accent",
  accent2: "form.role_accent2",
  good: "form.role_good",
  warn: "form.role_warn",
  bad: "form.role_bad",
  info: "form.role_info",
  text: "form.role_text",
  muted: "form.role_muted",
};

// One colour: a role of the theme by name, or a colour of one's own.
function colourOption(row, help, focus, disabled, change) {
  const { option } = row;
  const own = typeof row.value === "string" && row.value.startsWith("#");
  const wrap = el("div", "field");
  const { field, control } = select({
    label: option.label,
    options: [...Object.entries(COLOUR_ROLES).map(([role, key]) => [role, t(key)]), ["own", t("form.role_own")]],
    value: own ? "own" : String(row.value || ""),
    focus,
    onChange: (value) => change(value === "own" ? "#FFFFFF" : value),
  });
  control.disabled = disabled;
  wrap.append(field);
  if (own) {
    const input = document.createElement("input");
    input.type = "color";
    input.value = row.value.toLowerCase();
    input.disabled = disabled;
    input.dataset.focus = `${focus}:own`;
    input.setAttribute("aria-label", t("form.role_own"));
    input.addEventListener("input", () => change(input.value.toUpperCase(), true));
    wrap.append(input);
  }
  if (help) {
    wrap.append(el("span", "helper", help));
  }
  return wrap;
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
// panel does not know is left out with one quiet line (A12).
function optionRows(rows, section, ctx, names = []) {
  const nodes = [];
  let unknown = false;
  for (const row of rows) {
    if (row.option.section !== section || !row.shown) {
      continue;
    }
    if (!row.supported) {
      unknown = true;
      continue;
    }
    const node = optionRow(row, ctx, names);
    if (node) {
      nodes.push(node);
    }
  }
  if (unknown) {
    nodes.push(el("p", "helper", t("form.option_unknown")));
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
    const group = el("div", "segmented size-chips");
    group.setAttribute("role", "radiogroup");
    group.setAttribute("aria-label", t("form.size"));
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
    block.append(group);
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

export function buildCardForm2(ctx) {
  const { card, component, readOnly } = ctx;
  const form = el("div", "form-block card-form-2");
  form.append(itemHeading(component.name));
  if (component.description) {
    form.append(el("p", "helper", component.description));
  }
  form.append(el("div", "item-notes"));
  if (readOnly) {
    return form;
  }
  const state = cardForm(component, card, ctx.facts);
  // The value the form shows when nothing is stored, for "store only what
  // differs" (model.js::setOption).
  for (const row of state.rows) {
    row.fallback = row.usable ? optionDefault(row.option, row.listed) : row.value;
  }

  // The card file's notes whose `when` holds, at the top.
  for (const text of state.notes) {
    const note = el("p", "note-line", text);
    note.dataset.test = "card-note";
    form.append(note);
  }

  // Device
  const fields = formFields(component);
  if (fields.length) {
    const device = el("div", "form-block");
    device.append(partHeading(t("form.device")));
    for (const field of fields) {
      device.append(
        buildParamField({
          hass: ctx.hass,
          field,
          value: card.params?.[field.name],
          config: ctx.config,
          compact: ctx.compact,
          collapsed: true,
          onChange: (value) => ctx.onParam(field.name, value, field.kind === "number"),
        }),
      );
    }
    form.append(device);
  }

  // Size: the named sizes, then the finer steps.
  form.append(sizeBlock(ctx, state));

  // The card's own rows come next, so what the card can do is in view
  // first: what it shows, then the controls on it.
  const optionNames = state.rows.map((entry) => entry.name);
  const shown = optionRows(state.rows, "shows", ctx, optionNames);
  if (shown.length) {
    const shows = el("div", "form-block");
    shows.dataset.part = "shows";
    shows.append(partHeading(t("form.shows")), ...shown);
    form.append(shows);
  }
  const own = optionRows(state.rows, "controls", ctx, optionNames);
  if (own.length) {
    const controls = el("div", "form-block");
    controls.dataset.part = "controls";
    controls.append(partHeading(t("form.on_card")));
    // Some rows are drawn only on the larger sizes or on the controls page.
    const larger = state.sizes.length > 1;
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
      controls.append(line);
    }
    controls.append(...own);
    form.append(controls);
  }

  // Name and icon
  const naming = el("div", "form-block");
  naming.dataset.part = "name";
  naming.append(partHeading(t("form.name_icon")));
  if (state.title) {
    const { field } = textInput({
      label: t("form.name"),
      value: typeof card.title === "string" ? card.title : "",
      maxLength: 60,
      test: "form-name",
      helper: t("form.name_helper"),
      onInput: (text) => ctx.onTitle(text),
    });
    naming.append(field);
  }
  if (state.icon !== undefined) {
    naming.append(
      iconChoice({
        label: t("form.icon"),
        value: state.icon,
        own: isIcon(state.names["can.icon"]) ? state.names["can.icon"] : component.icon,
        focus: "card-icon",
        onChange: (name) => ctx.onStandard("icon", name),
      }),
    );
  }
  if (naming.children.length > 1) {
    form.append(naming);
  }

  // A tap and a hold
  const touch = el("div", "form-block");
  touch.dataset.part = "touch";
  touch.append(partHeading(t("form.touch")));
  if (state.tap) {
    const { field } = select({
      label: t("form.tap"),
      options: state.tap.choices.map((choice) => [choice.value, choice.label]),
      value: state.tap.value,
      focus: "card-tap",
      test: "card-tap",
      onChange: (value) => ctx.onStandard("tap", value),
    });
    if (state.tap.dropped) {
      field.append(el("span", "helper", t("form.tap_not_offered")));
    }
    touch.append(field);
    if (state.tap.value === "page") {
      const pages = pageChoices(ctx.config);
      const { field: pageField } = select({
        label: t("form.tap_page"),
        options: [["", t("pick.page_none")], ...pages.map((page) => [page.path, page.title || page.path])],
        value: state.tap.page,
        focus: "card-tap-page",
        test: "card-tap-page",
        onChange: (value) => ctx.onStandard("tap_page", value || undefined),
      });
      touch.append(pageField);
    }
  }
  if (state.hold !== null) {
    touch.append(
      switchRow({
        label: t("form.hold"),
        checked: state.hold,
        focus: "card-hold",
        test: "card-hold",
        onChange: (checked) => ctx.onStandard("hold", checked ? undefined : false),
      }).field,
    );
  }
  if (touch.children.length > 1) {
    form.append(touch);
  }

  // Look: the card's own rows, then the shared ones.
  const lookCtx = {
    ...ctx,
    lookRows: (block) => {
      if (state.lit !== null) {
        const { field } = select({
          label: t("form.lit"),
          options: Object.entries(LIT_LOOKS).map(([look, key]) => [look, t(key)]),
          value: state.lit,
          focus: "card-lit",
          test: "card-lit",
          onChange: (value) => ctx.onLook("lit", value === component.standard?.lit ? undefined : value),
        });
        field.append(el("span", "helper", t("form.lit_helper")));
        block.append(field);
      }
      if (state.tint !== null) {
        // Greyed and off for a device with no colour; what is stored stays.
        const { field, helper } = switchRow({
          label: t("form.tint"),
          help: state.tintUsable ? "" : t("form.tint_no_colour"),
          checked: state.tintUsable && state.tint,
          disabled: !state.tintUsable,
          focus: "card-tint",
          test: "card-tint",
          onChange: (checked) => ctx.onLook("tint", checked ? undefined : false),
        });
        const row = el("div", "option-switch option-row");
        row.classList.toggle("unusable", !state.tintUsable);
        row.append(field);
        if (helper) {
          row.append(helper);
        }
        block.append(row);
      }
      block.append(...optionRows(state.rows, "look", ctx, optionNames));
    },
  };
  form.append(lookBlock(lookCtx));
  form.append(positionBlock(ctx));
  form.append(
    makeButton(t("form.remove"), {
      kind: "danger",
      test: "remove-card",
      focus: "remove-card",
      onClick: ctx.onRemove,
    }),
  );
  return form;
}
