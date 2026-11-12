import {
  getCachedLibrary,
  getConnection,
  loadLibrary,
  loadStrings,
  t,
} from "./api.js";
import {
  cleanConfig,
  dashboardFromPath,
  formToStyle,
  gridForSize,
  paramsSchema,
  sizePreset,
  styleToForm,
} from "./logic.js";
import { editorStyles } from "./styles.js";

function addStyle(root, css) {
  const style = document.createElement("style");
  style.textContent = css;
  root.append(style);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function deepEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function labelForName(name) {
  const text = String(name).replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function rgbToHex(value) {
  if (!Array.isArray(value) || value.length !== 3) {
    return "#000000";
  }
  return `#${value
    .map((part) => Math.max(0, Math.min(255, Number(part) || 0)).toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase()}`;
}

function nativeValue(control, item) {
  if (item.selector.boolean) {
    return control.checked;
  }
  if (item.selector.number) {
    const number = Number(control.value);
    return Number.isFinite(number) ? number : undefined;
  }
  if (item.selector.color_rgb) {
    const hex = control.value;
    return [
      Number.parseInt(hex.slice(1, 3), 16),
      Number.parseInt(hex.slice(3, 5), 16),
      Number.parseInt(hex.slice(5, 7), 16),
    ];
  }
  return control.value;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function importFormThroughCardEditors() {
  const helpers = await window.loadCardHelpers?.();
  // Creating a card makes Home Assistant import the card's class.
  helpers?.createCardElement({ type: "tile", entity: "sun.sun" });
  helpers?.createCardElement({ type: "entities", entities: ["sun.sun"] });

  for (const tag of ["hui-tile-card", "hui-entities-card"]) {
    const CardClass = helpers
      ? await Promise.race([customElements.whenDefined(tag), delay(1000)])
      : customElements.get(tag);
    // Their editors import ha-form; the element itself is not needed.
    await CardClass?.getConfigElement?.();
  }
}

export async function ensureHaForm() {
  if (customElements.get("ha-form")) {
    return true;
  }

  importFormThroughCardEditors().catch(() => {});

  return Promise.race([
    customElements.whenDefined("ha-form").then(() => true),
    delay(3000).then(() => false),
  ]);
}

export class ApolloTabCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    addStyle(this.shadowRoot, editorStyles);

    this._config = null;
    this._hass = null;
    this._library = null;
    this._component = null;
    this._hasHaForm = null;
    this._lastEmitted = null;
    this._drawRun = 0;
    this._renderVersion = 0;
    this._paramsForm = null;
    this._styleForm = null;
  }

  setConfig(config) {
    if (this._lastEmitted && deepEqual(config, this._lastEmitted)) {
      this._config = config;
      return;
    }
    this._config = { ...config };
    this._render();
  }

  set hass(value) {
    const first = !this._hass;
    this._hass = value;
    if (this._paramsForm) {
      this._paramsForm.hass = value;
    }
    if (this._styleForm) {
      this._styleForm.hass = value;
    }
    // hass is set on every state change, and redrawing here would take the
    // focus away from whatever the user is typing in.
    if (first) {
      this._render();
    }
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    this._render();
  }

  async _prepare(version) {
    if (!this._hass || !this._config) {
      return;
    }

    const conn = await getConnection(this._hass);
    await loadStrings(conn);
    this._library = getCachedLibrary() || (await loadLibrary(conn, { force: false }));
    if (this._hasHaForm === null) {
      this._hasHaForm = await ensureHaForm();
    }

    if (version === this._renderVersion) {
      this._draw();
    }
  }

  _render() {
    const version = ++this._renderVersion;
    this._prepare(version).catch(() => {});
  }

  async _dashboardPaths() {
    try {
      const result = await this._hass.callWS({ type: "apollo_tab/dashboards" });
      return (result?.dashboards || []).map((entry) => entry.url_path);
    } catch {
      return [];
    }
  }

  async _draw() {
    if (!this._config || !this._hass) {
      return;
    }

    // Two overlapping draws would otherwise both append their controls.
    const run = ++this._drawRun;
    const paths = this._library ? await this._dashboardPaths() : [];
    if (run !== this._drawRun) {
      return;
    }

    // A hand-written card can name its Component through an alias type.
    this._component = this._library?.components?.find(
      (entry) =>
        entry.id === this._config.component || `custom:${entry.tag}` === this._config.type,
    );

    const keepStyle = this.shadowRoot.querySelector("style");
    this.shadowRoot.replaceChildren(keepStyle);
    this._paramsForm = null;
    this._styleForm = null;

    if (!this._component) {
      this.shadowRoot.append(
        element(
          "p",
          "editor-error",
          t("card.unknown_component", { id: this._config.component ?? this._config.type }),
        ),
      );
      return;
    }

    const intro = element("section", "component-intro");
    intro.append(
      element("h2", null, this._component.name),
      element("p", null, this._component.description),
    );
    this.shadowRoot.append(intro);

    if (this._component.source === "user" && this._component.sensitive) {
      const approval = element("section", "notice");
      approval.append(element("p", null, t("editor.approve_text")));
      const button = element(
        "button",
        "primary",
        this._component.approved ? t("editor.revoke") : t("editor.approve"),
      );
      button.type = "button";
      button.addEventListener("click", async () => {
        await this._hass.callWS({
          type: "apollo_tab/library/approve",
          component_id: this._component.id,
          approved: !this._component.approved,
        });
        const conn = await getConnection(this._hass);
        this._library = await loadLibrary(conn, { force: true });
        this._draw();
      });
      approval.append(button);
      this.shadowRoot.append(approval);
    }

    const currentPath = dashboardFromPath(location.pathname);
    if (!paths.includes(currentPath)) {
      this.shadowRoot.append(element("p", "notice", t("editor.not_tab_dashboard")));
    }

    this.shadowRoot.append(element("h3", null, t("editor.entities")));

    const paramSchema = paramsSchema(this._component.params || {}, {});
    const paramData = this._config.params || {};
    if (this._hasHaForm) {
      this._paramsForm = this._makeHaForm(paramData, paramSchema, (value) => {
        this._emit({ params: value });
      });
      this.shadowRoot.append(this._paramsForm);
    } else {
      this.shadowRoot.append(element("p", "notice", t("editor.basic_form")));
      this.shadowRoot.append(
        this._makeBasicForm(paramData, paramSchema, (value) => {
          this._emit({ params: value });
        }),
      );
    }

    this.shadowRoot.append(this._titleControl());
    this.shadowRoot.append(this._sizeControl());
    this.shadowRoot.append(element("h3", null, t("editor.style")));

    const styleData = styleToForm(this._config.style);
    const styleSchema = this._styleSchema(styleData);

    if (this._hasHaForm) {
      this._styleForm = this._makeHaForm(styleData, styleSchema, (value) => {
        this._applyStyleDefaults(value);
        this._emit({ style: formToStyle(value) });
        this._styleForm.data = value;
        this._styleForm.schema = this._styleSchema(value);
      });
      this.shadowRoot.append(this._styleForm);
    } else {
      this.shadowRoot.append(
        this._makeBasicForm(styleData, styleSchema, (value, structural) => {
          this._applyStyleDefaults(value);
          this._emit({ style: formToStyle(value) });
          if (structural) {
            this._draw();
          }
        }),
      );
    }
  }

  _makeHaForm(data, schema, change) {
    const form = document.createElement("ha-form");
    form.hass = this._hass;
    form.data = data;
    form.schema = schema;
    form.computeLabel = (item) => this._computeLabel(item);
    form.computeHelper = (item) => this._computeHelper(item);
    form.addEventListener("value-changed", (event) => {
      event.stopPropagation();
      change(event.detail.value);
    });
    return form;
  }

  _titleControl() {
    const wrap = element("label", "field");
    wrap.append(element("span", "field-label", t("editor.title")));
    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = 60;
    input.value = this._config.title || "";
    input.addEventListener("input", () => this._emit({ title: input.value }));
    wrap.append(input, element("span", "helper", t("editor.title_helper")));
    return wrap;
  }

  _sizeControl() {
    const wrap = element("label", "field");
    wrap.append(element("span", "field-label", t("editor.size")));
    const select = document.createElement("select");
    const selected = sizePreset(this._config.grid_options, this._component);

    const options = [
      ["1x1", t("size.1x1")],
      ["2x1", t("size.2x1")],
      ["1x2", t("size.1x2")],
      ["2x2", t("size.2x2")],
    ];
    if (selected === "custom") {
      options.push(["custom", t("editor.size_custom")]);
    }

    for (const [value, label] of options) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      select.append(option);
    }

    select.value = selected;
    select.addEventListener("change", () => {
      if (select.value !== "custom") {
        this._emit({
          grid_options: gridForSize(select.value.split("x").map(Number)),
        });
      }
    });
    wrap.append(select);
    return wrap;
  }

  _styleSchema(data) {
    const themes = this._library?.themes || [];
    const schema = [
      {
        name: "theme",
        selector: {
          select: {
            options: [
              { value: "", label: t("editor.theme_dashboard") },
              ...themes.map((theme) => ({ value: theme.id, label: theme.name })),
            ],
          },
        },
      },
      { name: "use_color", selector: { boolean: {} } },
    ];

    if (data.use_color) {
      schema.push({ name: "color", selector: { color_rgb: {} } });
    }

    schema.push({
      name: "gradient",
      selector: {
        select: {
          options: [
            { value: "none", label: t("editor.gradient_none") },
            { value: "vertical", label: t("editor.gradient_vertical") },
            { value: "horizontal", label: t("editor.gradient_horizontal") },
          ],
        },
      },
    });

    if (data.gradient && data.gradient !== "none") {
      schema.push({ name: "gradient_to", selector: { color_rgb: {} } });
    }

    schema.push(
      {
        name: "transparency",
        selector: { number: { mode: "slider", min: 0, max: 100, step: 5 } },
      },
      { name: "use_accent", selector: { boolean: {} } },
    );

    if (data.use_accent) {
      schema.push({ name: "accent", selector: { color_rgb: {} } });
    }

    return schema;
  }

  _applyStyleDefaults(data) {
    const themeId = data.theme || "midnight";
    const theme =
      this._library?.themes?.find((entry) => entry.id === themeId) ||
      this._library?.themes?.[0];

    if (data.use_color && !data.color && theme?.card) {
      data.color = this._hexToRgb(theme.card);
    }
    if (data.use_accent && !data.accent && theme?.acc) {
      data.accent = this._hexToRgb(theme.acc);
    }
    if (data.gradient !== "none" && !data.gradient_to && theme?.card2) {
      data.gradient_to = this._hexToRgb(theme.card2);
    }
  }

  _hexToRgb(hex) {
    return [
      Number.parseInt(hex.slice(1, 3), 16),
      Number.parseInt(hex.slice(3, 5), 16),
      Number.parseInt(hex.slice(5, 7), 16),
    ];
  }

  _computeLabel(item) {
    const key = `editor.${item.name}`;
    const translated = t(key);
    return translated === key ? labelForName(item.name) : translated;
  }

  _computeHelper(item) {
    if (item.name === "title") {
      return t("editor.title_helper");
    }
    if (item.name === "transparency") {
      return t("editor.transparency_helper");
    }
    if (item.name === "gradient" && styleToForm(this._config.style).gradient === "horizontal") {
      return t("editor.gradient_note");
    }
    return "";
  }

  _makeBasicForm(data, schema, change) {
    const form = element("div", "basic-form");
    const current = structuredClone(data || {});

    for (const item of schema) {
      const field = element("label", "field");
      field.append(element("span", "field-label", this._computeLabel(item)));

      if (item.selector.entity?.multiple) {
        const values = Array.isArray(current[item.name]) ? current[item.name] : [];
        const entries = [...values, ""];
        const group = element("div", "multi");

        entries.forEach((value, index) => {
          const input = this._nativeControl(item, value);
          input.addEventListener("input", () => {
            const controls = [...group.querySelectorAll("input")];
            current[item.name] = controls.map((entry) => entry.value).filter(Boolean);
            change(current, false);
          });
          group.append(input);
          if (index === entries.length - 1) {
            input.dataset.empty = "true";
          }
        });
        field.append(group);
      } else {
        const control = this._nativeControl(item, current[item.name]);
        const eventName =
          item.selector.boolean || item.selector.select || item.selector.color_rgb
            ? "change"
            : "input";
        control.addEventListener(eventName, () => {
          const value = nativeValue(control, item);
          if (value === undefined || value === "") {
            delete current[item.name];
          } else {
            current[item.name] = value;
          }
          const structural =
            item.name === "use_color" ||
            item.name === "use_accent" ||
            item.name === "gradient";
          change(current, structural);
        });
        field.append(control);
      }

      const helper = this._computeHelper(item);
      if (helper) {
        field.append(element("span", "helper", helper));
      }
      form.append(field);
    }

    return form;
  }

  _nativeControl(item, value) {
    let control;

    if (item.selector.select) {
      control = document.createElement("select");
      for (const entry of item.selector.select.options || []) {
        const option = document.createElement("option");
        if (typeof entry === "string") {
          option.value = entry;
          option.textContent = entry;
        } else {
          option.value = entry.value;
          option.textContent = entry.label;
        }
        control.append(option);
      }
      control.value = value ?? "";
      return control;
    }

    control = document.createElement("input");

    if (item.selector.boolean) {
      control.type = "checkbox";
      control.checked = Boolean(value);
      return control;
    }

    if (item.selector.number) {
      control.type = item.selector.number.mode === "slider" ? "range" : "number";
      const settings = item.selector.number;
      if (settings.min !== undefined) {
        control.min = settings.min;
      }
      if (settings.max !== undefined) {
        control.max = settings.max;
      }
      if (settings.step !== undefined) {
        control.step = settings.step;
      }
      control.value = value ?? settings.min ?? 0;
      return control;
    }

    if (item.selector.color_rgb) {
      control.type = "color";
      control.value = rgbToHex(value);
      return control;
    }

    control.type = "text";
    control.value = value ?? "";

    if (item.selector.entity) {
      const listId = `at-${item.name}-${Math.random().toString(36).slice(2)}`;
      const list = document.createElement("datalist");
      list.id = listId;
      const domain = item.selector.entity.filter?.domain;
      for (const entityId of Object.keys(this._hass?.states || {})) {
        if (!domain || entityId.startsWith(`${domain}.`)) {
          const option = document.createElement("option");
          option.value = entityId;
          list.append(option);
        }
      }
      control.setAttribute("list", listId);
      control.after(list);
    }

    return control;
  }

  _emit(changes) {
    const next = cleanConfig({ ...this._config, ...changes });
    this._config = next;
    this._lastEmitted = next;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: next },
        bubbles: true,
        composed: true,
      }),
    );
  }
}
