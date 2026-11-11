import {
  callCard,
  getCachedLibrary,
  getConnection,
  loadStrings,
  subscribeCard,
  t,
} from "./api.js";
import { openConfirm } from "./confirm.js";
import {
  aliasTag,
  dashboardFromPath,
  feedbackReduce,
  isOn,
  pickStubParams,
  resolveBound,
  subscriptionKey,
} from "./logic.js";
import { cardTokens, renderCard } from "./render.js";
import { cardStyles, rendererStyles } from "./styles.js";

const DOCUMENTATION_URL = "https://github.com/ApolloAutomation/TAB-Dashboard";

function makeElement(tag, className) {
  const element = document.createElement(tag);
  if (className) {
    element.className = className;
  }
  return element;
}

function addStyle(root, css) {
  const style = document.createElement("style");
  style.textContent = css;
  root.append(style);
}

function errorText(event, config) {
  if (event.code === "unknown_component") {
    return t("card.unknown_component", { id: config.component });
  }
  if (event.code === "needs_approval") {
    return t("card.needs_approval");
  }
  if (event.code === "params_incomplete") {
    return t("card.choose_entity");
  }
  if (event.code === "unauthorized") {
    return t("card.unauthorized");
  }
  return t("card.invalid", { message: event.message || event.code || "" });
}

function widgetKey(widget) {
  return widget.i ?? widget.id;
}

function valueSlot(widget) {
  const bound = widget?.value;
  if (bound && typeof bound === "object" && Object.hasOwn(bound, "s")) {
    return String(bound.s);
  }
  return null;
}

export class ApolloTabCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("apollo-tab-card-editor");
  }

  static getStubConfig(hass, entities, entitiesFallback) {
    const library = getCachedLibrary();
    const component = library?.components?.[0];
    if (!component) {
      return { component: "apollo/light-tile", params: {} };
    }
    return {
      component: component.id,
      params: pickStubParams(
        component.params,
        hass?.states || {},
        entities || [],
        entitiesFallback || [],
      ),
      grid_options: {
        columns: component.grid?.columns,
        rows: component.grid?.rows,
      },
    };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    // Rendered widgets live in this shadow root, so their CSS must be here too.
    addStyle(this.shadowRoot, rendererStyles);
    addStyle(this.shadowRoot, cardStyles);

    this.frame = makeElement("div", "card-frame");
    this.canvas = makeElement("div", "card-canvas");
    this.overlay = makeElement("div", "card-overlay");
    this.frame.append(this.canvas, this.overlay);
    this.shadowRoot.append(this.frame);

    this._config = null;
    this._hass = null;
    this._conn = null;
    this._stop = null;
    this._subKey = null;
    this._compiled = null;
    this._tokens = {};
    this._values = {};
    this._errors = {};
    this._feedback = new Map();
    this._renderer = null;
    this._ready = false;
    this._firstEvent = false;
    this._demo = false;
    this._missing = [];
    this._stateRefs = new Map();
    this._messageTimer = null;
    this._tickTimer = null;
    this._resizeObserver = null;
    this._dragging = false;
    this._lastValues = {};
    this._confirmKeys = new Set();
    this._confirming = new Set();
  }

  setConfig(config) {
    if (!config || typeof config.component !== "string" || !config.component.trim()) {
      throw new Error("component");
    }

    const previousKey = this._config
      ? subscriptionKey(this._config, dashboardFromPath(location.pathname))
      : null;
    this._config = { ...config };

    const nextKey = subscriptionKey(this._config, dashboardFromPath(location.pathname));
    if (previousKey !== nextKey) {
      this._unsubscribe();
      this._subKey = nextKey;
      this._compiled = null;
      this._renderer = null;
      this._firstEvent = false;
      this._values = {};
      this._errors = {};
      this._lastValues = {};
      this._feedback = new Map();
      if (this.isConnected && this._hass) {
        this._subscribe();
      }
    }

    this._draw();
  }

  set hass(value) {
    const first = !this._hass;
    this._hass = value;

    if (first && this.isConnected && this._config) {
      this._subscribe();
      return;
    }

    if (this._compiled) {
      let changed = false;
      for (const entity of this._compiled.entities || []) {
        const next = value?.states?.[entity];
        if (this._stateRefs.get(entity) !== next) {
          this._stateRefs.set(entity, next);
          changed = true;
        }
      }
      if (changed) {
        this._checkMissingEntities();
        this._drawOverlays();
      }
    }
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    this.style.display = "block";
    this.style.height = "100%";
    this.style.minHeight = "56px";

    if (!this._resizeObserver && typeof ResizeObserver !== "undefined") {
      // Drawing inside the callback resizes observed content, so wait a frame.
      this._resizeObserver = new ResizeObserver(() => {
        cancelAnimationFrame(this._resizeFrame);
        this._resizeFrame = requestAnimationFrame(() => {
          if (!this._dragging) {
            this._renderCompiled(true);
          }
        });
      });
      this._resizeObserver.observe(this);
    }

    if (this._config && this._hass) {
      this._subscribe();
    }
    this._draw();
  }

  disconnectedCallback() {
    this._unsubscribe();
    // Image refresh timers stop now; _draw builds the card again on reconnect.
    this._stopCanvas();
    this._renderer = null;
    this._resizeObserver?.disconnect();
    this._resizeObserver = null;
    cancelAnimationFrame(this._resizeFrame);
    clearTimeout(this._messageTimer);
    clearInterval(this._tickTimer);
    this._tickTimer = null;
  }

  getGridOptions() {
    const own = this._config?.grid_options;
    if (Number.isFinite(own?.columns) && Number.isFinite(own?.rows)) {
      return {
        columns: own.columns,
        rows: own.rows,
        min_columns: 3,
        min_rows: 1,
      };
    }

    const component = getCachedLibrary()?.components?.find(
      (entry) => entry.id === this._config?.component,
    );
    if (Number.isFinite(component?.grid?.columns) && Number.isFinite(component?.grid?.rows)) {
      return {
        columns: component.grid.columns,
        rows: component.grid.rows,
        min_columns: 3,
        min_rows: 1,
      };
    }

    if (Number.isFinite(this._compiled?.w) && Number.isFinite(this._compiled?.h)) {
      return {
        columns: (this._compiled.w + 8) / 32,
        rows: (this._compiled.h + 8) / 64,
        min_columns: 3,
        min_rows: 1,
      };
    }

    return { columns: 6, rows: 3, min_columns: 3, min_rows: 1 };
  }

  getCardSize() {
    return this.getGridOptions().rows;
  }

  async _subscribe() {
    if (this._stop || !this._config || !this._hass) {
      return;
    }

    this._conn = await getConnection(this._hass);
    await loadStrings(this._conn);
    if (!this.isConnected || this._stop) {
      return;
    }

    this._ready = true;
    this._draw();

    const dashboard = dashboardFromPath(location.pathname);
    this._subKey = subscriptionKey(this._config, dashboard);
    this._stop = subscribeCard(
      this._conn,
      this._config,
      dashboard,
      (event) => this._handleEvent(event),
    );
  }

  _unsubscribe() {
    this._stop?.();
    this._stop = null;
  }

  _stopCanvas() {
    this.canvas.__atCleanup?.();
    this.canvas.__atCleanup = null;
  }

  _handleEvent(event) {
    this._firstEvent = true;

    if (event.type === "init") {
      this._compiled = event.card;
      this._demo = Boolean(event.card?.demo);
      this._tokens = cardTokens(event.theme || {}, event.style || {});
      this._values = {};
      this._errors = {};
      this._lastValues = {};
      this._feedback = new Map();
      this._confirmKeys = new Set();

      for (const widget of event.card?.widgets || []) {
        this._feedback.set(widgetKey(widget), {
          phase: "idle",
          value: undefined,
          until: 0,
        });
      }

      this._checkMissingEntities();
      this._renderCompiled(true);
      return;
    }

    if (event.type === "values") {
      const previous = this._lastValues;
      this._values = event.values || {};
      this._errors = event.errors || {};

      for (const widget of this._compiled?.widgets || []) {
        const slot = valueSlot(widget);
        if (
          slot !== null &&
          Object.hasOwn(this._values, slot) &&
          previous[slot] !== this._values[slot]
        ) {
          this._reduceFeedback(widgetKey(widget), {
            type: "value",
            now: Date.now(),
          });
        }
      }

      this._lastValues = { ...this._values };
      this._patchRenderer();
      this._drawOverlays();
      return;
    }

    if (event.type === "error") {
      this._compiled = null;
      this._renderer = null;
      this._showStatus(errorText(event, this._config));
    }
  }

  _checkMissingEntities() {
    this._missing = [];
    this._stateRefs.clear();
    for (const entity of this._compiled?.entities || []) {
      const state = this._hass?.states?.[entity];
      this._stateRefs.set(entity, state);
      if (!state) {
        this._missing.push(entity);
      }
    }
  }

  _showStatus(text) {
    this._stopCanvas();
    this.canvas.replaceChildren();
    const status = makeElement("div", "status");
    status.textContent = text;
    this.canvas.append(status);
    this.overlay.replaceChildren();
  }

  _draw() {
    if (!this._ready) {
      return;
    }
    if (!this._firstEvent) {
      this._showStatus(t("card.loading"));
      return;
    }
    if (this._compiled) {
      this._renderCompiled(false);
    }
  }

  _renderCompiled(force) {
    if (!this._compiled || !this.isConnected) {
      return;
    }

    // A host left at its minimum height gets none from its parent (masonry
    // views), so it takes the card's shape. Measuring both ways in one pass
    // keeps the answer stable from one resize to the next.
    this.style.removeProperty("aspect-ratio");
    let rect = this.getBoundingClientRect();
    if (rect.height <= 56) {
      this.style.aspectRatio = `${this._compiled.w} / ${this._compiled.h}`;
      rect = this.getBoundingClientRect();
    }
    const width = rect.width || this._compiled.w || 376;
    const height = rect.height || width * this._compiled.h / this._compiled.w;

    const sx = width / this._compiled.w;
    const sy = height / this._compiled.h;
    // The Example chip sits in the card's bottom padding, so it scales with it.
    this.overlay.style.setProperty("--at-f", String(Math.min(sx, sy)));

    if (!this._renderer || force) {
      this._renderer = renderCard(
        this.canvas,
        this._compiled,
        this._renderState(),
        {
          sx,
          sy,
          origin: [0, 0],
          interactive: true,
          onTap: (widget) => this._tap(widget),
          onChange: (widget, value, final) => this._change(widget, value, final),
          onDrag: (active) => {
            this._dragging = active;
          },
        },
      );
    } else {
      this._patchRenderer();
    }

    this._drawOverlays();
  }

  _renderState() {
    return {
      values: this._values,
      errors: this._errors,
      tokens: this._tokens,
      feedback: this._feedback,
    };
  }

  _patchRenderer() {
    this._renderer?.update(this._renderState());
  }

  _drawOverlays() {
    // A value update must not wipe a message that is still being shown.
    const temporary = this.overlay.querySelector(".temporary-message");
    this.overlay.replaceChildren();

    if (this._demo) {
      const chip = makeElement("span", "example-chip");
      chip.textContent = t("card.example");
      this.overlay.append(chip);
    }

    if (this._missing.length) {
      const line = makeElement("div", "message-line");
      line.textContent = t("card.entity_missing", { entity: this._missing[0] });
      this.overlay.append(line);
    }

    if (temporary) {
      this.overlay.append(temporary);
    }
  }

  _showMessage(text) {
    let line = this.overlay.querySelector(".temporary-message");
    if (!line) {
      line = makeElement("div", "message-line temporary-message");
      this.overlay.append(line);
    }
    line.textContent = text;
    clearTimeout(this._messageTimer);
    this._messageTimer = setTimeout(() => line.remove(), 3000);
  }

  _feedbackState(key) {
    return this._feedback.get(key) || {
      phase: "idle",
      value: undefined,
      until: 0,
    };
  }

  _reduceFeedback(key, event) {
    const next = feedbackReduce(this._feedbackState(key), event);
    this._feedback.set(key, next);
    this._patchRenderer();
    this._manageTicking();
  }

  _manageTicking() {
    const active = [...this._feedback.values()].some((state) => state.phase !== "idle");
    if (active && !this._tickTimer) {
      this._tickTimer = setInterval(() => {
        const now = Date.now();
        let anyActive = false;
        const nextMap = new Map();

        for (const [key, state] of this._feedback) {
          const next = feedbackReduce(state, { type: "tick", now });
          nextMap.set(key, next);
          if (next.phase !== "idle") {
            anyActive = true;
          }
        }

        this._feedback = nextMap;
        this._patchRenderer();

        if (!anyActive) {
          clearInterval(this._tickTimer);
          this._tickTimer = null;
        }
      }, 250);
    } else if (!active && this._tickTimer) {
      clearInterval(this._tickTimer);
      this._tickTimer = null;
    }
  }

  async _tap(widget) {
    const action = widget.tap;
    if (!action) {
      return;
    }

    if (action.local) {
      this._localAction(action);
      return;
    }

    let optimisticValue;
    if (widget.t === "switch") {
      const current = resolveBound(widget.value, this._values);
      optimisticValue = !isOn(current);
    }

    await this._perform(widget, "tap", undefined, optimisticValue);
  }

  async _change(widget, value, final) {
    // A control that needs confirmation gets one dialog per gesture, for the
    // value on release, so values in between are never sent.
    if (!final && this._needsConfirm(widget, "change")) {
      return;
    }
    if (!final && widget.__lastCall && Date.now() - widget.__lastCall < 200) {
      return;
    }
    widget.__lastCall = Date.now();
    await this._perform(widget, "change", value, value, final);
  }

  _localAction(action) {
    if ((action.local === "open_details" || action.local === "open_live") && action.entity) {
      this.dispatchEvent(
        new CustomEvent("hass-more-info", {
          detail: { entityId: action.entity },
          bubbles: true,
          composed: true,
        }),
      );
      return;
    }

    if (action.local === "go_to_page" && action.page) {
      const dashboard = dashboardFromPath(location.pathname);
      if (dashboard) {
        history.pushState(null, "", `/${dashboard}/${action.page}`);
        window.dispatchEvent(new CustomEvent("location-changed"));
      }
    }
  }

  _needsConfirm(widget, eventName) {
    const key = `${widgetKey(widget)}:${eventName}`;
    return widget[eventName]?.policy === "confirm" || this._confirmKeys.has(key);
  }

  async _perform(widget, eventName, value, optimisticValue, final = true) {
    const action = widget[eventName] || {};
    const policy = action.policy || "pulse";
    const key = widgetKey(widget);
    const confirmKey = `${key}:${eventName}`;

    if (this._demo) {
      this._reduceFeedback(key, {
        type: "act",
        policy,
        value: optimisticValue,
        now: Date.now(),
      });
      this._showMessage(t("card.demo_action"));
      return;
    }

    // Ignore new calls while a dialog is open or a confirmed call is pending.
    if (this._confirming.has(confirmKey)) {
      return;
    }

    if (this._needsConfirm(widget, eventName)) {
      if (final) {
        await this._confirmAndCall(widget, eventName, value);
      }
      return;
    }

    // Nothing above awaits, so a quick second press already sees this value.
    this._reduceFeedback(key, {
      type: "act",
      policy,
      value: optimisticValue,
      now: Date.now(),
    });

    try {
      await callCard(
        this._conn,
        this._config,
        widgetKey(widget),
        eventName,
        value,
        false,
      );
      this._reduceFeedback(key, { type: "ok", now: Date.now() });
    } catch (error) {
      if (error?.code === "confirm_required") {
        // Remember it, and drop the optimistic value: a control that needs
        // confirmation shows nothing new before the server does.
        this._confirmKeys.add(confirmKey);
        this._reduceFeedback(key, { type: "tick", now: Number.MAX_SAFE_INTEGER });
        if (final) {
          await this._confirmAndCall(widget, eventName, value);
        }
        return;
      }

      this._failed(key, error);
    }
  }

  async _confirmAndCall(widget, eventName, value) {
    const key = widgetKey(widget);
    const confirmKey = `${key}:${eventName}`;
    if (this._confirming.has(confirmKey)) {
      return;
    }

    this._confirming.add(confirmKey);
    try {
      const text = resolveBound(widget.confirm, this._values) || t("confirm.title");
      const accepted = await openConfirm({
        title: t("confirm.title"),
        text: String(text),
        okLabel: t("confirm.ok"),
        cancelLabel: t("confirm.cancel"),
      });
      if (!accepted) {
        return;
      }

      this._reduceFeedback(key, {
        type: "act",
        policy: "confirm",
        now: Date.now(),
      });

      try {
        await callCard(
          this._conn,
          this._config,
          widgetKey(widget),
          eventName,
          value,
          true,
        );
        this._reduceFeedback(key, { type: "ok", now: Date.now() });
      } catch (error) {
        this._failed(key, error);
      }
    } finally {
      this._confirming.delete(confirmKey);
    }
  }

  _failed(key, error) {
    this._reduceFeedback(key, { type: "fail", now: Date.now() });
    const message =
      error?.code === "unauthorized"
        ? t("card.unauthorized")
        : t("card.action_failed", { message: error?.message || error?.code || "" });
    this._showMessage(message);
  }
}

export function defineAliases(library) {
  for (const component of library?.components || []) {
    const tag = aliasTag(component.id);

    if (!customElements.get(tag)) {
      const fixedComponent = component;
      class ApolloTabAlias extends ApolloTabCard {
        static getStubConfig(hass, entities, entitiesFallback) {
          return {
            type: "custom:apollo-tab-card",
            component: fixedComponent.id,
            params: pickStubParams(
              fixedComponent.params,
              hass?.states || {},
              entities || [],
              entitiesFallback || [],
            ),
            grid_options: {
              columns: fixedComponent.grid?.columns,
              rows: fixedComponent.grid?.rows,
            },
          };
        }

        setConfig(config) {
          super.setConfig({ ...config, component: fixedComponent.id });
        }
      }
      customElements.define(tag, ApolloTabAlias);
    }
  }

  // Home Assistant keeps a reference to this array, so change it in place.
  window.customCards = window.customCards || [];
  for (let index = window.customCards.length - 1; index >= 0; index -= 1) {
    if (String(window.customCards[index].type || "").startsWith("apollo-tab-el-")) {
      window.customCards.splice(index, 1);
    }
  }

  for (const component of library?.components || []) {
    window.customCards.push({
      type: aliasTag(component.id),
      name: `TAB-1 ${component.name}`,
      description: component.description,
      preview: true,
      documentationURL: DOCUMENTATION_URL,
    });
  }
}
