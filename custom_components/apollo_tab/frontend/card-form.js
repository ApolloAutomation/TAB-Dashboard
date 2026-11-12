import { t } from "./api.js";
import { formToStyle, isIcon, styleToForm } from "./logic.js";
import {
  MAX_ENTITIES,
  MAX_UNITS_HIGH,
  MAX_UNITS_WIDE,
  PAGE_ICONS,
  PAGE_ICON_NAMES,
  cardSize,
  entityChoices,
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

// data-focus names a control so it can get focus back after its region is
// drawn again; data-test is what the scripted browser run looks for.
export function makeButton(label, options = {}) {
  const button = el("button", options.className, label);
  button.type = "button";
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

function checkbox({ label, checked, focus, onChange }) {
  const field = el("label", "check");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = Boolean(checked);
  input.dataset.focus = focus;
  input.addEventListener("change", () => onChange(input.checked));
  field.append(input, el("span", null, label));
  return { field, input };
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
// again from the top. Returns whether a control got focus.
export function restoreFocus(container, key) {
  if (!key) {
    return false;
  }
  const nodes = [...container.querySelectorAll("[data-focus]")];
  const target = nodes.find((node) => node.dataset.focus === key);
  if (!target) {
    return false;
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
        makeButton(t("advanced.open"), { test: "open-advanced", onClick: onOpenAdvanced }),
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
  const form = el("div", "form-block");
  form.append(itemHeading(component.name));
  if (component.description) {
    form.append(el("p", "helper", component.description));
  }
  form.append(el("div", "item-notes"));
  if (readOnly) {
    return form;
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
    makeButton(t("form.remove"), { test: "remove-card", focus: "remove-card", onClick: ctx.onRemove }),
  );
  return form;
}

function sizeBlock(ctx) {
  const block = el("div", "form-block");
  let size = cardSize(ctx.card, ctx.component);

  const resize = (w, h) => {
    const width = Math.min(ctx.maxWide, Math.max(1, w));
    const height = Math.min(MAX_UNITS_HIGH, Math.max(1, h));
    size = { w: width, h: height, exact: true };
    ctx.onResize(width, height);
    redraw(block, draw);
  };

  const draw = () => {
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
    const own = Array.isArray(ctx.component.size) ? ctx.component.size : [1, 1];
    block.append(el("h3", null, t("form.size")), value, width);
    if (columns) {
      block.append(columns);
    }
    block.append(
      height,
      makeButton(t("form.size_reset"), {
        test: "size-reset",
        focus: "size-reset",
        onClick: () => resize(Number(own[0]) || 1, Number(own[1]) || 1),
      }),
    );
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
      checkbox({
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
    range.addEventListener("input", () => {
      output.textContent = range.value;
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
    const accentHelper = el("p", "helper", t("form.accent_helper"));
    accentHelper.id = uid("accent-helper");
    accentHelper.dataset.test = "accent-helper";
    const { field: accentField, input: accentInput } = checkbox({
      label: t("form.use_accent"),
      checked: data.use_accent,
      focus: "look-use-accent",
      onChange: (checked) => change({ use_accent: checked }, "use_accent"),
    });
    accentInput.setAttribute("aria-describedby", accentHelper.id);
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
    form.append(makeButton(t("list.remove"), { test: "remove-item", onClick: ctx.onRemove }));
  }
  return form;
}

// The heading at the top of "This page" or "This dashboard", which takes
// focus when the person comes back from a card's form.
function settingsHeading(text) {
  const heading = el("h3", null, text);
  heading.tabIndex = -1;
  heading.dataset.test = "settings-heading";
  return heading;
}

export function buildPageSettings(ctx) {
  const block = el("section", "form-block");
  block.append(settingsHeading(t("page.heading")));

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
  grid.setAttribute("role", "group");
  grid.setAttribute("aria-labelledby", iconsLabel.id);
  for (const name of PAGE_ICONS) {
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
    button.setAttribute("aria-pressed", String(ctx.icon === name));
    button.append(icon(name));
    grid.append(button);
  }
  icons.append(iconsLabel, grid);
  block.append(icons);

  const moves = el("div", "row-buttons");
  moves.append(
    makeButton(t("page.move_left"), {
      test: "page-left",
      focus: "page-left",
      focusAlt: "page-right",
      disabled: ctx.index <= 0,
      onClick: () => ctx.onMove(-1),
    }),
    makeButton(t("page.move_right"), {
      test: "page-right",
      focus: "page-right",
      focusAlt: "page-left",
      disabled: ctx.index >= ctx.count - 1,
      onClick: () => ctx.onMove(1),
    }),
  );
  block.append(moves);

  block.append(
    makeButton(t("page.delete"), {
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

// Settings that apply to the whole dashboard. Name, sidebar and delete are
// stored by Home Assistant itself, so a failure puts the control back and
// says so next to it.
export function buildDashboardSettings(ctx) {
  const block = el("section", "form-block");
  block.append(settingsHeading(t("settings.heading")));

  const failure = (line, error) => {
    line.textContent = t("settings.failed", { message: error?.message || error?.code || "" });
  };

  if (!ctx.readOnly) {
    const nameAlert = el("p", "alert");
    nameAlert.setAttribute("role", "alert");
    let savedName = ctx.title;
    const { field, input } = textInput({
      label: t("settings.name"),
      value: ctx.title,
      maxLength: 80,
      test: "dashboard-name",
      onInput: () => {},
    });
    input.addEventListener("change", async () => {
      const value = input.value.trim();
      if (!value) {
        input.value = savedName;
        return;
      }
      try {
        await ctx.onRename(value);
        savedName = value;
        nameAlert.textContent = "";
      } catch (error) {
        input.value = savedName;
        failure(nameAlert, error);
      }
    });
    block.append(field, nameAlert);

    const themes = Array.isArray(ctx.themes) ? ctx.themes : [];
    const { field: themeField } = select({
      label: t("settings.theme"),
      options: themes.map((theme) => [theme.id, theme.name]),
      value: ctx.themeId,
      focus: "dashboard-theme",
      test: "theme",
      onChange: (value) => ctx.onTheme(value),
    });
    themeField.append(el("span", "helper", t("settings.theme_helper")));
    block.append(themeField);

    const sidebarAlert = el("p", "alert");
    sidebarAlert.setAttribute("role", "alert");
    const { field: sidebarField, input: sidebarInput } = checkbox({
      label: t("settings.sidebar"),
      checked: ctx.showInSidebar,
      focus: "dashboard-sidebar",
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
    sidebarInput.dataset.test = "sidebar-checkbox";
    block.append(sidebarField, el("p", "helper", t("settings.sidebar_helper")), sidebarAlert);
  }

  // There is deliberately no link to the dashboard in Home Assistant: its
  // own editor there offers cards the tablet cannot show.
  if (ctx.readOnly) {
    const theme = (Array.isArray(ctx.themes) ? ctx.themes : []).find((entry) => entry.id === ctx.themeId);
    const field = el("div", "field");
    field.append(el("span", "field-label", t("settings.theme")), el("span", null, theme?.name || ctx.themeId || ""));
    block.append(field);
  } else {
    const deleteAlert = el("p", "alert");
    deleteAlert.setAttribute("role", "alert");
    block.append(
      makeButton(t("settings.delete"), {
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
