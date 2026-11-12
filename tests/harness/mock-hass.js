function defineStandIns() {
  if (!customElements.get("ha-icon")) {
    class HaIcon extends HTMLElement {
      set icon(value) {
        this._icon = value;
        this.title = value || "";
        this.style.display = "inline-block";
        this.style.width = "1em";
        this.style.height = "1em";
        this.style.borderRadius = "3px";
        this.style.background = "currentColor";
      }

      get icon() {
        return this._icon;
      }
    }
    customElements.define("ha-icon", HaIcon);
  }

  if (!customElements.get("ha-menu-button")) {
    class HaMenuButton extends HTMLElement {
      connectedCallback() {
        this.textContent = "☰";
      }
    }
    customElements.define("ha-menu-button", HaMenuButton);
  }

  const params = new URLSearchParams(location.search);
  if (params.get("haform") !== "0" && !customElements.get("ha-form")) {
    class HaForm extends HTMLElement {
      constructor() {
        super();
        this.attachShadow({ mode: "open" });
        this._data = {};
        this._schema = [];
      }

      set data(value) {
        this._data = value || {};
        this._draw();
      }

      get data() {
        return this._data;
      }

      set schema(value) {
        this._schema = value || [];
        this._draw();
      }

      get schema() {
        return this._schema;
      }

      set hass(value) {
        this._hass = value;
      }

      set computeLabel(value) {
        this._computeLabel = value;
        this._draw();
      }

      set computeHelper(value) {
        this._computeHelper = value;
        this._draw();
      }

      connectedCallback() {
        this._draw();
      }

      _draw() {
        if (!this.shadowRoot || !this.isConnected) {
          return;
        }

        this.shadowRoot.replaceChildren();
        const style = document.createElement("style");
        style.textContent = `
          :host { display: grid; gap: 10px; }
          label { display: grid; gap: 5px; }
          input, select { min-height: 38px; padding: 7px; }
          small { color: #9aa0a8; }
        `;
        this.shadowRoot.append(style);

        for (const item of this._schema) {
          const label = document.createElement("label");
          const text = document.createElement("span");
          text.textContent = this._computeLabel?.(item) || item.name;
          label.append(text);

          const control = this._control(item);
          label.append(control);

          const helper = this._computeHelper?.(item);
          if (helper) {
            const small = document.createElement("small");
            small.textContent = helper;
            label.append(small);
          }
          this.shadowRoot.append(label);
        }
      }

      _control(item) {
        let control;
        const selector = item.selector || {};

        if (selector.select) {
          control = document.createElement("select");
          for (const entry of selector.select.options || []) {
            const option = document.createElement("option");
            option.value = typeof entry === "string" ? entry : entry.value;
            option.textContent = typeof entry === "string" ? entry : entry.label;
            control.append(option);
          }
          control.value = this._data[item.name] ?? "";
        } else {
          control = document.createElement("input");

          if (selector.boolean) {
            control.type = "checkbox";
            control.checked = Boolean(this._data[item.name]);
          } else if (selector.number) {
            control.type = selector.number.mode === "slider" ? "range" : "number";
            if (selector.number.min !== undefined) control.min = selector.number.min;
            if (selector.number.max !== undefined) control.max = selector.number.max;
            if (selector.number.step !== undefined) control.step = selector.number.step;
            control.value = this._data[item.name] ?? selector.number.min ?? 0;
          } else if (selector.color_rgb) {
            control.type = "color";
            const rgb = this._data[item.name] || [0, 0, 0];
            control.value = `#${rgb
              .map((part) => Number(part).toString(16).padStart(2, "0"))
              .join("")}`;
          } else {
            control.type = "text";
            const value = this._data[item.name];
            control.value = Array.isArray(value) ? value.join(", ") : value ?? "";
          }
        }

        const eventName =
          control.type === "text" || control.type === "number" || control.type === "range"
            ? "input"
            : "change";

        control.addEventListener(eventName, () => {
          const next = { ...this._data };
          if (selector.boolean) {
            next[item.name] = control.checked;
          } else if (selector.number) {
            next[item.name] = Number(control.value);
          } else if (selector.color_rgb) {
            next[item.name] = [
              Number.parseInt(control.value.slice(1, 3), 16),
              Number.parseInt(control.value.slice(3, 5), 16),
              Number.parseInt(control.value.slice(5, 7), 16),
            ];
          } else if (selector.entity?.multiple) {
            next[item.name] = control.value
              .split(",")
              .map((value) => value.trim())
              .filter(Boolean);
          } else {
            next[item.name] = control.value;
          }

          this._data = next;
          this.dispatchEvent(
            new CustomEvent("value-changed", {
              detail: { value: next },
              bubbles: true,
              composed: true,
            }),
          );
        });

        return control;
      }
    }
    customElements.define("ha-form", HaForm);
  }
}

function sampleStates() {
  const ids = [
    "light.kitchen",
    "light.living_room",
    "light.bedroom",
    "switch.fan",
    "switch.coffee",
    "climate.hall",
    "sensor.temperature",
    "sensor.energy",
    "sensor.humidity",
    "camera.front_door",
    "lock.front_door",
    "alarm_control_panel.home",
  ];

  return Object.fromEntries(
    ids.map((entityId, index) => [
      entityId,
      {
        entity_id: entityId,
        state: index % 2 ? "off" : "on",
        attributes: {
          friendly_name: entityId.split(".")[1].replaceAll("_", " "),
        },
      },
    ]),
  );
}

// The tokens the integration sends for a card with no style of its own.
function plainStyle(theme) {
  const { card, tx, tx2, acc, acc2, acct, card2, line, onbg, ontx, r, r2, bw } = theme;
  return { bg: card, tx, tx2, acc, acc2, acct, card2, line, onbg, ontx, r, r2, bw };
}

// Sets what a bound field shows, whether it is a slot or an example constant.
function setBound(owner, key, values, value) {
  const bound = owner?.[key];
  if (bound && typeof bound === "object" && "s" in bound) {
    values[String(bound.s)] = value;
  } else if (owner && key in owner) {
    owner[key] = value;
  }
}

function setSwitch(init, values, value) {
  const widget = (init.widgets || []).find((entry) => entry.t === "switch");
  setBound(widget, "value", values, value);
  setBound(init, "on", values, value);
}

function scenarioEvents(fixture, card, themes) {
  const scenario = card.__scenario;
  const init = structuredClone(fixture.init);
  const values = structuredClone(fixture.values || {});
  const themeId = new URLSearchParams(location.search).get("theme");
  const theme = themes.find((entry) => entry.id === themeId) || themes[0] || {};
  let style = { ...plainStyle(theme), ...structuredClone(fixture.styles?.[scenario] || {}) };

  if (scenario === "error") {
    return [
      {
        type: "error",
        code: "invalid_card",
        message: "Fixture error",
      },
    ];
  }

  if (scenario === "example") {
    init.demo = true;
  }

  if (scenario === "missing") {
    init.entities = ["light.not_present"];
  }

  const slider = (init.widgets || []).find((entry) => entry.t === "slider");
  // A custom fill is hidden by the on tint, so those samples are drawn off.
  const showsOff = ["off", "custom-color", "vertical", "horizontal", "transparency"];
  if (showsOff.includes(scenario)) setSwitch(init, values, "off");
  if (scenario === "on") setSwitch(init, values, "on");
  if (scenario === "zero") setBound(slider, "value", values, 0);
  if (scenario === "half") setBound(slider, "value", values, 50);
  if (scenario === "full") setBound(slider, "value", values, 100);

  let errors = {};
  if (scenario === "slot-error") {
    // Example cards can hold constants only, so make sure one field is a slot.
    const label = (init.widgets || []).find((entry) => entry.t === "label");
    if (label) {
      label.text = { s: 999 };
      delete values["999"];
      errors = { 999: "Fixture slot error" };
    }
  }

  const fixed = {
    "custom-color": { bg: "#203040", tx: "#FFFFFF" },
    vertical: { bg: "#203040", bg2: "#101820", gd: "v", tx: "#FFFFFF" },
    horizontal: { bg: "#203040", bg2: "#101820", gd: "h", tx: "#FFFFFF" },
    transparency: { bg: "#44505C", tx: "#FFFFFF" },
    accent: { acc: "#FFB300", acc2: "#FFB300" },
  };
  style = { ...style, ...(fixed[scenario] || {}) };

  return [
    { type: "init", card: init, theme, style },
    { type: "values", values, errors },
  ];
}

export function createMockHass(fixtures) {
  defineStandIns();

  const listeners = new Set();
  const calls = [];
  const configs = new Map();
  for (const dashboard of fixtures.dashboards?.dashboards || []) {
    configs.set(dashboard.url_path, {
      apollo_tab: { version: 1, theme: dashboard.theme || "midnight" },
      views: [],
    });
  }

  const hass = {
    states: sampleStates(),
    user: { is_admin: true },
    language: "en",
    panels: {},
    calls,
    async callWS(message) {
      calls.push(structuredClone(message));

      if (message.type === "apollo_tab/strings") {
        return { strings: fixtures.strings };
      }
      if (message.type === "apollo_tab/library") {
        return fixtures.library;
      }
      if (message.type === "apollo_tab/library/reload") {
        return {
          components: fixtures.library.components.length,
          errors: fixtures.library.errors?.length || 0,
        };
      }
      if (message.type === "apollo_tab/library/approve") {
        const component = fixtures.library.components.find(
          (entry) => entry.id === message.component_id,
        );
        if (!component) {
          throw Object.assign(new Error("Not found"), { code: "not_found" });
        }
        component.approved = message.approved;
        return { approved: message.approved };
      }
      if (message.type === "apollo_tab/dashboards") {
        return fixtures.dashboards;
      }
      if (message.type === "apollo_tab/layout/get") {
        if (message.url_path !== fixtures.layout.url_path) {
          throw Object.assign(new Error("Not found"), { code: "not_found" });
        }
        return fixtures.layout;
      }
      if (message.type === "apollo_tab/card/call") {
        return { ok: true };
      }
      if (message.type === "lovelace/dashboards/list") {
        return fixtures.dashboards?.dashboards || [];
      }
      if (message.type === "lovelace/dashboards/create") {
        configs.set(message.url_path, { views: [] });
        return null;
      }
      if (message.type === "lovelace/config") {
        return structuredClone(configs.get(message.url_path) || { views: [] });
      }
      if (message.type === "lovelace/config/save") {
        configs.set(message.url_path, structuredClone(message.config));
        return null;
      }

      throw Object.assign(new Error(`Unsupported command: ${message.type}`), {
        code: "unsupported",
      });
    },
    connection: {
      async subscribeMessage(callback, message) {
        const record = { callback, message };
        listeners.add(record);

        if (message.type === "apollo_tab/card/subscribe") {
          queueMicrotask(() => {
            const fixture =
              fixtures.cards.find((entry) => entry.id === message.card.component) ||
              fixtures.cards[0];
            if (!fixture) {
              callback({
                type: "error",
                code: "unknown_component",
                message: message.card.component,
              });
              return;
            }
            for (const event of scenarioEvents(
              fixture,
              message.card,
              fixtures.themes || [],
            )) {
              callback(event);
            }
          });
        }

        return () => listeners.delete(record);
      },
      sendMessagePromise(message) {
        return hass.callWS(message);
      },
    },
  };

  return hass;
}
