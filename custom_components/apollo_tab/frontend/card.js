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
  compactCard,
  dashboardFromPath,
  feedbackReduce,
  isOn,
  resolveBound,
  subscriptionKey,
} from "./logic.js";
import { cardTokens, renderCard } from "./render.js";
import { cardStyles, detailDialogStyles, rendererStyles } from "./styles.js";

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
  // Home Assistant is still starting, or the integration is being loaded
  // again. Nothing is wrong with the card, and it is subscribed again by
  // itself (see subscribeCard).
  if (event.code === "not_loaded" || event.code === "unknown_command") {
    return t("card.waiting");
  }
  return t("card.invalid", { message: event.message || event.code || "" });
}

// Tab and Shift+Tab stay inside the dialog.
function trapFocus(event, box) {
  const inner = box.querySelector("apollo-tab-card")?.shadowRoot;
  const items = [
    ...box.querySelectorAll("button"),
    ...(inner ? inner.querySelectorAll("button:not(:disabled), input, [tabindex='0']") : []),
  ];
  if (!items.length) {
    return;
  }
  let active = document.activeElement;
  while (active?.shadowRoot?.activeElement) {
    active = active.shadowRoot.activeElement;
  }
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && active === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && active === last) {
    event.preventDefault();
    first.focus();
  }
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
    // The copy for a card's detail page, shown in a dialog by its card.
    this._detail = false;
    this._dialog = null;
    // When each slot's value last changed, for clocks and moving sliders.
    this._valueTimes = {};
    this._ageTimer = null;
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

    if (this._dialog) {
      this._dialog.card.hass = value;
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
    clearInterval(this._ageTimer);
    this._ageTimer = null;
    this._closeDetail();
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
      this._detail,
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
      this._compiled = this._detail ? compactCard(event.card) : event.card;
      this._demo = Boolean(event.card?.demo);
      this._tokens = cardTokens(event.theme || {}, event.style || {});
      this._values = {};
      this._errors = {};
      this._lastValues = {};
      this._feedback = new Map();
      this._confirmKeys = new Set();
      this._valueTimes = {};
      this._manageAges();

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
      const now = Date.now();
      for (const [slot, value] of Object.entries(this._values)) {
        if (!Object.hasOwn(previous, slot) || previous[slot] !== value) {
          this._valueTimes[slot] = now;
        }
      }
      // The card's own optimistic look ends when its "on" value comes.
      const onSlot = valueSlot({ value: this._compiled?.on });
      if (onSlot !== null && Object.hasOwn(this._values, onSlot) && previous[onSlot] !== this._values[onSlot]) {
        this._reduceFeedback(-1, { type: "value", now });
      }

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
    if (this._detail) {
      // The dialog takes the card's width and keeps it within the window.
      const { w, h } = this._compiled;
      this.parentElement?.style.setProperty("--at-detail-w", `${w}px`);
      this.parentElement?.style.setProperty("--at-detail-ratio", String(w / h));
    }
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
          onCardTap: () => this._cardTap(),
          onHold: (widget) => this._hold(widget),
          label: this._cardName(),
        },
      );
    } else {
      this._patchRenderer();
    }

    this._drawOverlays();
  }

  _renderState() {
    const card = this._feedbackState(-1);
    return {
      values: this._values,
      errors: this._errors,
      tokens: this._tokens,
      feedback: this._feedback,
      // A tap on the card shows its new look before the answer comes.
      cardOn: card.phase === "pending" && card.value !== undefined ? card.value : undefined,
      // Seconds since a slot's value last changed (contract 4.4).
      age: (slot) => (this._valueTimes[slot] ? (Date.now() - this._valueTimes[slot]) / 1000 : 0),
    };
  }

  // Clocks and sliders that move by themselves are drawn again each second.
  _manageAges() {
    const moving = (this._compiled?.widgets || []).some(
      (widget) => widget.clk || (widget.t === "slider" && widget.rate !== undefined && !widget.change),
    );
    if (moving && !this._ageTimer) {
      this._ageTimer = setInterval(() => this._patchRenderer(), 1000);
    } else if (!moving && this._ageTimer) {
      clearInterval(this._ageTimer);
      this._ageTimer = null;
    }
  }

  // Whether the card is shown as not available (un): it then sends nothing.
  _unavailable() {
    const un = this._compiled?.un;
    return un !== undefined && un !== null && isOn(resolveBound(un, this._values));
  }

  // A tap on the card itself: widget -1 on the server.
  async _cardTap() {
    const card = this._compiled;
    if (!card?.tap) {
      return;
    }
    if (card.tap.local) {
      this._localAction(card.tap);
      return;
    }
    const pseudo = { i: -1, t: "card", tap: card.tap, confirm: card.confirm };
    const optimistic =
      card.tap.policy === "optimistic" && card.on !== undefined && card.on !== null
        ? !isOn(resolveBound(card.on, this._values))
        : undefined;
    await this._perform(pseudo, "tap", undefined, optimistic);
  }

  // A hold, or a right click: the card's own (widget null) or a widget's.
  _hold(widget) {
    const hold = widget ? widget.hold : this._compiled?.hold;
    if (hold?.local) {
      this._localAction(hold);
    }
  }

  // The card's name for a screen reader and the dialog's title: its own
  // name, else its first device's name, else the card's.
  _cardName() {
    const entity = this._compiled?.entities?.[0];
    return (
      this._config?.name ||
      this._hass?.states?.[entity]?.attributes?.friendly_name ||
      this._compiled?.name ||
      ""
    );
  }

  // The detail page in a dialog: a title row with a close button, and the
  // card's controls sized to fit the window.
  _openDetail() {
    if (this._detail || this._dialog || !this._config) {
      return;
    }
    const opener = this.canvas.querySelector(".at-card");
    const backdrop = makeElement("div", "apollo-tab-detail");
    const style = document.createElement("style");
    style.textContent = detailDialogStyles;
    const box = makeElement("div", "apollo-tab-detail-box");
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    const head = makeElement("div", "apollo-tab-detail-head");
    const title = makeElement("h2", "apollo-tab-detail-title");
    title.id = `apollo-tab-detail-${Math.random().toString(36).slice(2)}`;
    title.textContent = this._cardName();
    box.setAttribute("aria-labelledby", title.id);
    const close = makeElement("button", "apollo-tab-detail-close");
    close.type = "button";
    close.setAttribute("aria-label", t("picker.close"));
    close.title = t("picker.close");
    const icon = document.createElement("ha-icon");
    icon.icon = "mdi:close";
    close.append(icon);
    head.append(title, close);
    const card = document.createElement(this.localName);
    card._detail = true;
    card._closeDialog = () => this._closeDetail();
    card.setConfig(this._config);
    box.append(head, card);
    backdrop.append(style, box);
    const onKey = (event) => {
      if (event.key === "Escape") {
        this._closeDetail();
      } else if (event.key === "Tab") {
        trapFocus(event, box);
      }
    };
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) {
        this._closeDetail();
      }
    });
    close.addEventListener("click", () => this._closeDetail());
    document.addEventListener("keydown", onKey);
    this._dialog = { backdrop, card, opener, onKey };
    document.body.append(backdrop);
    card.hass = this._hass;
    close.focus();
  }

  _closeDetail() {
    if (!this._dialog) {
      return;
    }
    const { backdrop, opener, onKey } = this._dialog;
    this._dialog = null;
    document.removeEventListener("keydown", onKey);
    backdrop.remove();
    // Focus goes back to the card that opened the dialog.
    if (opener?.isConnected) {
      opener.focus?.();
    }
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
    if (action.local === "detail") {
      this._openDetail();
      return;
    }

    // Back works on a detail page only (4.6): it closes the dialog.
    if (action.local === "back") {
      this._closeDialog?.();
      return;
    }

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

    // A card shown as not available takes no press (contract 4.7).
    if (this._unavailable()) {
      return;
    }

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
        this._detail,
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
          this._detail,
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

// Defines one element per library card, so dashboards that use an alias
// type such as custom:apollo-tab-el-apollo-light-tile keep rendering. They
// are not listed in Home Assistant's card picker: TAB-1 cards are added in
// the TAB-1 panel.
export function defineAliases(library) {
  for (const component of library?.components || []) {
    const tag = aliasTag(component.id);

    if (!customElements.get(tag)) {
      const fixedComponent = component;
      class ApolloTabAlias extends ApolloTabCard {
        setConfig(config) {
          super.setConfig({ ...config, component: fixedComponent.id });
        }
      }
      customElements.define(tag, ApolloTabAlias);
    }
  }
}
