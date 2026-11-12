function defineStandIns() {
  if (!customElements.get("ha-icon")) {
    class HaIcon extends HTMLElement {
      set icon(value) {
        this._icon = value;
        this.title = value || "";
        this.style.display = "inline-block";
        this.style.flex = "0 0 auto";
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

  // Like Home Assistant's own: it decides for itself whether to show, and
  // shows a 48 px button only when the window is narrow or the sidebar is
  // set to always hidden. Otherwise it draws nothing and takes no room.
  if (!customElements.get("ha-menu-button")) {
    class HaMenuButton extends HTMLElement {
      constructor() {
        super();
        this.attachShadow({ mode: "open" });
      }

      set hass(value) {
        this._hass = value;
        this._draw();
      }

      get hass() {
        return this._hass;
      }

      set narrow(value) {
        this._narrow = Boolean(value);
        this._draw();
      }

      get narrow() {
        return Boolean(this._narrow);
      }

      connectedCallback() {
        this._draw();
      }

      _draw() {
        const show = this._narrow || this._hass?.dockedSidebar === "always_hidden";
        this.shadowRoot.innerHTML = show
          ? `<style>:host { position: relative; } button { display: block; width: 48px; height: 48px;
              border: 0; border-radius: 50%; background: transparent; color: inherit; font-size: 22px; }</style>
             <button type="button" aria-label="Sidebar toggle">☰</button>`
          : "<style>:host { position: relative; }</style>";
      }
    }
    customElements.define("ha-menu-button", HaMenuButton);
  }
}

const STATES = [
  ["light.kitchen", "on", "Kitchen"],
  ["light.living_room", "off", "Living room"],
  ["light.bedroom", "on", "Bedroom lamp"],
  ["light.hidden_helper", "off", "Hidden helper"],
  ["switch.fan", "off", "Fan switch"],
  ["switch.coffee", "on", "Coffee machine"],
  ["fan.bedroom_main_bedroom_fan", "on", "Bedroom fan"],
  ["climate.hall", "heat", "Hall"],
  ["cover.lounge", "open", "Lounge blinds"],
  ["media_player.den", "playing", "Den speaker"],
  ["weather.home", "sunny", "Home"],
  ["scene.movie", "scening", "Movie night"],
  ["scene.dinner", "scening", "Dinner"],
  ["person.sam", "home", "Sam"],
  ["sensor.temperature", "21.5", "Temperature"],
  ["sensor.energy", "3.2", "Energy"],
  ["sensor.humidity", "48", "Humidity"],
  ["camera.front_door", "idle", "Front door camera"],
  ["lock.front_door", "locked", "Front door"],
  ["alarm_control_panel.home", "disarmed", "House alarm"],
];

function sampleStates() {
  return Object.fromEntries(
    STATES.map(([entityId, state, name]) => [
      entityId,
      { entity_id: entityId, state, attributes: { friendly_name: name } },
    ]),
  );
}

const AREAS = {
  kitchen: { area_id: "kitchen", name: "Kitchen" },
  bedroom: { area_id: "bedroom", name: "Bedroom" },
};

const ENTITIES = {
  "light.kitchen": { entity_id: "light.kitchen", area_id: "kitchen" },
  "light.bedroom": { entity_id: "light.bedroom", area_id: "bedroom" },
  "fan.bedroom_main_bedroom_fan": { entity_id: "fan.bedroom_main_bedroom_fan", area_id: "bedroom" },
  "light.hidden_helper": { entity_id: "light.hidden_helper", hidden: true },
};

// A lock card from the user's folder that has not been allowed yet.
const DOOR_LOCK = {
  id: "me/door-lock",
  tag: "apollo-tab-el-me-door-lock",
  name: "Door lock",
  description: "A lock card from your folder.",
  icon: "mdi:lock",
  version: "1.0.0",
  size: [1, 1],
  grid: { columns: 6, rows: 3 },
  source: "user",
  sensitive: true,
  approved: false,
  params: { entity: { kind: "entity", domain: "lock", multiple: false } },
};

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

function hasParams(card) {
  return Boolean(card?.params && typeof card.params === "object" && Object.keys(card.params).length);
}

function scenarioEvents(fixture, card, themes) {
  const scenario = card.__scenario;
  const init = structuredClone(fixture.init);
  const values = structuredClone(fixture.values || {});
  const query = new URLSearchParams(location.search);
  const themeId = card.style?.theme || query.get("theme");
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

  // Like the integration, a card without its settings shows example values.
  if (scenario === "example" || (!scenario && !hasParams(card))) {
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

function fail(code, message = code) {
  return Object.assign(new Error(message), { code });
}

// options.seed: "none", "sample" (default) or "real" (uses options.realConfig).
// options.community adds a lock card from the user's folder to the library.
export function createMockHass(fixtures, options = {}) {
  defineStandIns();

  const listeners = new Set();
  const calls = [];
  const library = structuredClone(fixtures.library);
  if (options.community) {
    library.components.push(structuredClone(DOOR_LOCK));
  }

  // A small in-memory stand-in for Home Assistant's storage dashboards.
  const dashboards = new Map();
  let counter = 0;
  let failingSaves = 0;
  let saveDelay = 0;
  let lostAnswers = 0;
  const failing = new Map();
  // down: the connection is lost. waiting: commands sent meanwhile.
  // underWay: commands sent and not answered yet.
  const connection = { down: false, waiting: [], underWay: new Set() };

  const addDashboard = (urlPath, title, config, showInSidebar) => {
    dashboards.set(urlPath, {
      id: urlPath.replaceAll("-", "_"),
      url_path: urlPath,
      title,
      icon: "mdi:tablet-dashboard",
      mode: "storage",
      show_in_sidebar: showInSidebar,
      require_admin: false,
      config: config ? structuredClone(config) : null,
    });
  };

  const seed = options.seed || "sample";
  if (seed === "sample") {
    addDashboard("tab-1", "TAB-1", fixtures.sample_config, false);
  } else if (seed === "real") {
    addDashboard("tab-1", "TAB-1", options.realConfig, true);
  }

  const emit = (type, event) => {
    for (const record of [...listeners]) {
      if (record.message.type === type) {
        record.callback(event);
      }
    }
  };

  const emitLayout = (event) => emit("apollo_tab/layout/subscribe", event);

  const itemOf = (dashboard) => {
    const { config: _config, ...item } = dashboard;
    return structuredClone(item);
  };

  const byId = (id) => [...dashboards.values()].find((entry) => entry.id === id);

  // announce: false stores without the event, as for a browser whose
  // connection is down at the time.
  const store = (urlPath, config, announce = true) => {
    const dashboard = dashboards.get(urlPath);
    dashboard.config = structuredClone(config);
    if (!announce) {
      return;
    }
    queueMicrotask(() =>
      emitLayout({ type: "converted", url_path: urlPath, hash: String(++counter), warnings: 0 }),
    );
  };

  // Listeners for the connection's own events, such as "ready".
  const connectionListeners = new Map();

  // Like the integration, "pages" is the number of screens in the converted
  // layout: a page with no cards gives none, a long page gives several.
  const tabDashboards = async () => {
    const list = [];
    for (const dashboard of dashboards.values()) {
      const config = dashboard.config;
      const settings = config?.apollo_tab;
      if (!settings || typeof settings !== "object" || Array.isArray(settings)) {
        continue;
      }
      const converted = await preview(config);
      list.push({
        url_path: dashboard.url_path,
        title: dashboard.title,
        mode: dashboard.mode,
        theme: typeof settings.theme === "string" ? settings.theme : "midnight",
        pages: converted.layout.pages.length,
        warnings: converted.warnings.length,
        hash: converted.layout.hash,
      });
    }
    return { dashboards: list, tablets: 0, sent_to_tablets: false };
  };

  const preview = async (config) => {
    const response = await fetch(`${location.origin}/api/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config }),
    });
    if (!response.ok) {
      throw fail("conversion_failed", "The dashboard could not be converted");
    }
    return response.json();
  };

  const hass = {
    states: sampleStates(),
    areas: structuredClone(AREAS),
    devices: {},
    entities: structuredClone(ENTITIES),
    user: { is_admin: true },
    language: "en",
    panels: {},
    // "docked", "always_hidden" or "auto", as the person set the sidebar.
    dockedSidebar: "docked",
    calls,
    // Like Home Assistant's websocket library: a command sent while the
    // connection is down waits and goes out once it is back, and one under
    // way when the connection drops is answered with code 3, "Connection
    // lost", whether or not it reached Home Assistant.
    callWS(message) {
      if (connection.down) {
        return new Promise((resolve, reject) => connection.waiting.push({ message, resolve, reject }));
      }
      return new Promise((resolve, reject) => {
        const entry = { resolve, reject };
        connection.underWay.add(entry);
        const settle = (answer) => {
          if (connection.underWay.delete(entry)) {
            answer();
          }
        };
        hass.answerWS(message).then(
          (value) => settle(() => resolve(value)),
          (error) => settle(() => reject(error)),
        );
      });
    },
    async answerWS(message) {
      calls.push(structuredClone(message));
      const failures = failing.get(message.type) || 0;
      if (failures > 0) {
        failing.set(message.type, failures - 1);
        throw fail("error", "Fixture error");
      }

      switch (message.type) {
        case "apollo_tab/strings":
          return { strings: fixtures.strings };
        case "apollo_tab/library":
          return structuredClone(library);
        case "apollo_tab/library/reload":
          return { components: library.components.length, errors: library.errors?.length || 0 };
        case "apollo_tab/library/approve": {
          const component = library.components.find((entry) => entry.id === message.component_id);
          if (!component) {
            throw fail("not_found", "Not found");
          }
          component.approved = message.approved;
          return { approved: message.approved };
        }
        case "apollo_tab/dashboards":
          return tabDashboards();
        case "apollo_tab/layout/get":
          if (message.url_path !== fixtures.layout.url_path) {
            throw fail("not_found", "Not found");
          }
          return fixtures.layout;
        case "apollo_tab/layout/preview":
          return preview(message.config);
        case "apollo_tab/card/call":
          return { ok: true };
        case "lovelace/dashboards/list":
          return [...dashboards.values()].map(itemOf);
        case "lovelace/dashboards/create": {
          const urlPath = message.url_path;
          if (typeof urlPath !== "string" || !urlPath.includes("-") || dashboards.has(urlPath)) {
            throw fail("invalid_format", "Invalid url_path");
          }
          addDashboard(urlPath, message.title, null, message.show_in_sidebar !== false);
          const dashboard = dashboards.get(urlPath);
          dashboard.icon = message.icon ?? dashboard.icon;
          dashboard.mode = message.mode ?? dashboard.mode;
          dashboard.require_admin = Boolean(message.require_admin);
          return itemOf(dashboard);
        }
        case "lovelace/dashboards/update": {
          const dashboard = byId(message.dashboard_id);
          if (!dashboard) {
            throw fail("not_found", "Dashboard not found");
          }
          for (const key of ["title", "icon", "show_in_sidebar", "require_admin"]) {
            if (key in message) {
              dashboard[key] = message[key];
            }
          }
          return itemOf(dashboard);
        }
        case "lovelace/dashboards/delete": {
          const dashboard = byId(message.dashboard_id);
          if (!dashboard) {
            throw fail("not_found", "Dashboard not found");
          }
          dashboards.delete(dashboard.url_path);
          queueMicrotask(() => emitLayout({ type: "removed", url_path: dashboard.url_path }));
          return null;
        }
        case "lovelace/config": {
          const dashboard = dashboards.get(message.url_path);
          if (!dashboard || !dashboard.config) {
            throw fail("config_not_found", "No config found.");
          }
          return structuredClone(dashboard.config);
        }
        case "lovelace/config/save": {
          if (!dashboards.has(message.url_path)) {
            throw fail("config_not_found", "No config found.");
          }
          if (failingSaves > 0) {
            failingSaves -= 1;
            throw fail("error", "Fixture save error");
          }
          // Like a slow connection: the config is stored when the answer
          // comes back, not when the save is sent.
          if (saveDelay > 0) {
            await new Promise((resolve) => setTimeout(resolve, saveDelay));
          }
          store(message.url_path, message.config);
          if (lostAnswers > 0) {
            lostAnswers -= 1;
            throw Object.assign(new Error("Connection lost"), { code: 3 });
          }
          return null;
        }
        default:
          throw fail("unsupported", `Unsupported command: ${message.type}`);
      }
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
            for (const event of scenarioEvents(fixture, message.card, fixtures.themes || [])) {
              callback(event);
            }
          });
        }

        return () => listeners.delete(record);
      },
      sendMessagePromise(message) {
        return hass.callWS(message);
      },
      addEventListener(type, callback) {
        if (!connectionListeners.has(type)) {
          connectionListeners.set(type, new Set());
        }
        connectionListeners.get(type).add(callback);
      },
      removeEventListener(type, callback) {
        connectionListeners.get(type)?.delete(callback);
      },
    },

    // Test hooks for the scripted browser run.
    externalSave(urlPath, config) {
      if (!dashboards.has(urlPath)) {
        throw fail("not_found", "Dashboard not found");
      }
      store(urlPath, config);
    },
    // Another browser saves while this one's connection is down: the change
    // is stored, but no event about it reaches this browser.
    saveWhileOffline(urlPath, config) {
      if (!dashboards.has(urlPath)) {
        throw fail("not_found", "Dashboard not found");
      }
      store(urlPath, config, false);
    },
    // Another browser deletes a dashboard while this one's connection is
    // down: no "removed" event reaches this browser.
    deleteWhileOffline(urlPath) {
      if (!dashboards.delete(urlPath)) {
        throw fail("not_found", "Dashboard not found");
      }
    },
    // The connection drops: every command under way is answered with
    // "Connection lost" (a save among them may still be stored, for
    // example a slow one), and commands sent from now on wait.
    dropConnection() {
      connection.down = true;
      for (const entry of [...connection.underWay]) {
        connection.underWay.delete(entry);
        entry.reject(Object.assign(new Error("Connection lost"), { code: 3 }));
      }
    },
    // The connection comes back. Home Assistant's own connection then opens
    // its subscriptions again and fires "ready"; nothing tells what changed.
    // Commands that waited go out after that.
    reconnect() {
      connection.down = false;
      for (const callback of [...(connectionListeners.get("ready") || [])]) {
        callback(hass.connection);
      }
      const waiting = connection.waiting.splice(0);
      setTimeout(() => {
        for (const { message, resolve, reject } of waiting) {
          hass.callWS(message).then(resolve, reject);
        }
      }, 50);
    },
    // The next `count` saves are stored, but their answer is lost with the
    // connection: they fail with code 3, "Connection lost".
    loseSaveAnswers(count) {
      lostAnswers = Math.max(0, Number(count) || 0);
    },
    // How many listeners wait for the connection's "ready" event.
    readyListeners() {
      return connectionListeners.get("ready")?.size || 0;
    },
    failSaves(count) {
      failingSaves = Math.max(0, Number(count) || 0);
    },
    // The next `count` calls of one command type fail.
    failCalls(type, count) {
      failing.set(type, Math.max(0, Number(count) || 0));
    },
    // Every later lovelace/config/save answers after `ms` milliseconds.
    slowSaves(ms) {
      saveDelay = Math.max(0, Number(ms) || 0);
    },
    addDashboard(urlPath, title, config) {
      addDashboard(urlPath, title, config, false);
    },
    // A dashboard kept in a YAML file: listed, but not changeable here.
    addYamlDashboard(urlPath, title, config) {
      addDashboard(urlPath, title, config, false);
      dashboards.get(urlPath).mode = "yaml";
    },
    getConfig(urlPath) {
      const config = dashboards.get(urlPath)?.config;
      return config ? structuredClone(config) : null;
    },
    getDashboard(urlPath) {
      const dashboard = dashboards.get(urlPath);
      return dashboard ? itemOf(dashboard) : null;
    },
  };

  return hass;
}
