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

// A card from the user's folder with five graphs, one more than a screen
// takes, so the tablet leaves it out even when it is alone on its page. The
// harness server converts it (FIVE_GRAPHS in tests/harness/server.py).
const FIVE_GRAPHS = {
  id: "me/five-graphs",
  tag: "apollo-tab-el-me-five-graphs",
  name: "Five graphs",
  description: "One sensor as five lines.",
  icon: "mdi:chart-line",
  version: "1.0.0",
  size: [2, 2],
  grid: { columns: 12, rows: 6 },
  source: "user",
  sensitive: false,
  approved: true,
  params: { entity: { kind: "entity", domain: "sensor", multiple: false } },
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

// The integration's answer to a change for a tablet no admin turned on
// (tests/harness/tablet-shapes.json).
const NOT_APPROVED =
  'This tablet is new. Pick a dashboard for it on the Home screen, then press "Turn on with this dashboard".';

// A second dashboard for the tablet steps: "Night", with one empty page.
const NIGHT_CONFIG = {
  apollo_tab: { version: 1, theme: "warm" },
  views: [
    {
      type: "sections",
      title: "Night",
      path: "night",
      icon: "mdi:bed",
      max_columns: 3,
      sections: [{ type: "grid", column_span: 3, cards: [] }],
    },
  ],
};

// The stand-in tablets, in the shapes of tests/harness/tablet-shapes.json
// (tests/frontend/tablet-shapes.test.mjs checks them). `prefer` lists the
// dashboards a tablet shows when they exist; without one it gets the first
// dashboard, as Home Assistant gives the first one to an approved tablet
// that has none. A tablet with `dashboard: null` has none. `forced` fixes
// the status, for showing every status at once. `engine` is "" while the
// tablet has no dashboard software, as the integration sends it.
// `approved: false` is a new tablet that waits for an admin to pick its
// first dashboard; `suggested` is what it showed before it was adopted
// again. Until it is approved it shows nothing and is not paired.
// `reauth` ("erased" or "key") is what Home Assistant waits for from an
// admin in Repairs before it connects again, under `reauth_name` (the
// tablet's name there, its own name when not given).
function tabletEntry(n, name, changes = {}) {
  const mac = `aa:bb:cc:dd:ee:${n.toString(16).padStart(2, "0")}`;
  return {
    mac,
    device_id: n.toString(16).padStart(32, "0"),
    name,
    short_name: name.replace(/ tablet$/i, ""),
    model: "TAB-1",
    prefer: [],
    online: true,
    engine: "0.1.0",
    paired: true,
    input: "ok",
    entity_id: `select.${name.toLowerCase().replaceAll(" ", "_")}_dashboard`,
    forced: null,
    approved: true,
    suggested: null,
    reauth: null,
    reauth_name: null,
    ...changes,
  };
}

const NEW_TABLET = { approved: false, dashboard: null };

const BEDROOM_NO_ENGINE = { prefer: ["tab-1"], engine: "", paired: false, input: "not_paired" };

// Compares like Python's sorted(): by code point.
function byCodePoint(a, b) {
  const left = [...String(a)];
  const right = [...String(b)];
  for (let index = 0; index < Math.min(left.length, right.length); index += 1) {
    const step = left[index].codePointAt(0) - right[index].codePointAt(0);
    if (step) {
      return step;
    }
  }
  return left.length - right.length;
}

const TABLET_SETS = {
  none: () => [],
  three: () => [
    tabletEntry(1, "Kitchen tablet", { prefer: ["tab-1"] }),
    tabletEntry(2, "Hallway tablet", { prefer: ["night"], online: false }),
    tabletEntry(3, "Bedroom tablet", BEDROOM_NO_ENGINE),
  ],
  "no-engine": () => [tabletEntry(3, "Bedroom tablet", BEDROOM_NO_ENGINE)],
  // An approved tablet and a new one that waits for an admin.
  new: () => [
    tabletEntry(1, "Kitchen tablet", { prefer: ["tab-1"] }),
    tabletEntry(14, "Porch tablet", NEW_TABLET),
  ],
  // Two new tablets, one under the other, and an approved one.
  "two-new": () => [
    tabletEntry(1, "Kitchen tablet", { prefer: ["tab-1"] }),
    tabletEntry(14, "Porch tablet", NEW_TABLET),
    tabletEntry(15, "Patio tablet", NEW_TABLET),
  ],
  // One tablet for every status and reason, both notes about taps, and an
  // erased tablet that Home Assistant waits for an admin's answer about.
  all: () => [
    tabletEntry(1, "Kitchen tablet", { prefer: ["tab-1"] }),
    tabletEntry(2, "Hallway tablet", { prefer: ["tab-1"], online: false }),
    tabletEntry(3, "Bedroom tablet", BEDROOM_NO_ENGINE),
    tabletEntry(4, "Office tablet", { forced: { status: "unsupported", reason: "tablet_old", retry: false } }),
    tabletEntry(5, "Garage tablet", { forced: { status: "unsupported", reason: "ha_version", retry: false } }),
    tabletEntry(6, "Porch tablet", { forced: { status: "failed", reason: "timeout", retry: true } }),
    tabletEntry(7, "Attic tablet", { forced: { status: "failed", reason: "too_big", retry: false } }),
    tabletEntry(8, "Cellar tablet", { forced: { status: "failed", reason: "unreadable", retry: false } }),
    tabletEntry(9, "Study tablet", { forced: { status: "failed", reason: "parse", retry: false } }),
    tabletEntry(10, "Nursery tablet", { forced: { status: "sending", reason: "", retry: false } }),
    tabletEntry(11, "Den tablet", { paired: false, input: "needs_encryption" }),
    tabletEntry(12, "Loft tablet", { paired: false, input: "not_paired" }),
    tabletEntry(13, "Guest tablet", { dashboard: null, forced: { status: "no_dashboard", reason: "", retry: false } }),
    tabletEntry(14, "Shed tablet", { ...NEW_TABLET, suggested: "tab-1" }),
    tabletEntry(16, "Pantry tablet", {
      prefer: ["tab-1"],
      online: false,
      reauth: "erased",
      reauth_name: "Apollo TAB-1 ddee10",
    }),
  ],
};

// options.seed: "none", "sample" (default) or "real" (uses options.realConfig).
// options.community adds a lock card from the user's folder to the library,
// options.graphs a card with five graphs. options.night adds the "Night"
// dashboard. options.tablets: "none" (default), "three", "no-engine", "new",
// "two-new" or "all" (see TABLET_SETS).
export function createMockHass(fixtures, options = {}) {
  defineStandIns();

  const listeners = new Set();
  const calls = [];
  const library = structuredClone(fixtures.library);
  if (options.community) {
    library.components.push(structuredClone(DOOR_LOCK));
  }
  if (options.graphs) {
    library.components.push(structuredClone(FIVE_GRAPHS));
  }

  // A small in-memory stand-in for Home Assistant's storage dashboards.
  const dashboards = new Map();
  let counter = 0;
  let failingSaves = 0;
  let saveDelay = 0;
  let lostAnswers = 0;
  const failing = new Map();
  // Commands answered only after a while: {type: milliseconds}.
  const slow = new Map();
  // down: the connection is lost. waiting: commands sent meanwhile.
  // underWay: commands sent and not answered yet.
  const connection = { down: false, waiting: [], underWay: new Set() };
  // Home Assistant does not know the commands whose type starts with this;
  // null: it knows them all (see unknownCommands).
  let unknownPrefix = null;
  const isUnknown = (type) => unknownPrefix !== null && String(type).startsWith(unknownPrefix);

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
  if (options.night) {
    addDashboard("night", "Night", NIGHT_CONFIG, false);
  }

  const emit = (type, event) => {
    for (const record of [...listeners]) {
      if (record.message.type === type) {
        record.callback(event);
      }
    }
  };

  const emitLayout = (event) => emit("apollo_tab/layout/subscribe", event);

  // ---- tablets, like the integration's assignment and sender ----

  const isTabConfig = (config) =>
    Boolean(config?.apollo_tab && typeof config.apollo_tab === "object" && !Array.isArray(config.apollo_tab));

  // The TAB-1 dashboards in the integration's one order:
  // (title in lower case, url_path).
  const tabOrder = () =>
    [...dashboards.values()]
      .filter((dashboard) => isTabConfig(dashboard.config))
      .map((dashboard) => [String(dashboard.title || "").toLowerCase(), dashboard.url_path, dashboard])
      .sort((a, b) => byCodePoint(a[0], b[0]) || byCodePoint(a[1], b[1]))
      .map((entry) => entry[2]);

  const isTab = (urlPath) => isTabConfig(dashboards.get(urlPath)?.config);

  const tablets = (TABLET_SETS[options.tablets] || TABLET_SETS.none)();
  for (const tablet of tablets) {
    if (tablet.dashboard === undefined && tablet.approved) {
      tablet.dashboard = tablet.prefer.find(isTab) || tabOrder()[0]?.url_path || null;
    }
    tablet.sending = false;
  }
  // holdSends keeps every send at "sending" until finishSends.
  const sends = { delay: 700, hold: false };

  // Like the integration: what the connection says comes first, so an
  // offline tablet reads "offline" whether or not it has a dashboard.
  const statusOf = (tablet) => {
    // A new tablet reads "new", whatever else is true of it.
    if (!tablet.approved) {
      return { status: "new", reason: "", retry: false };
    }
    if (tablet.forced) {
      return tablet.forced;
    }
    if (!tablet.online) {
      return { status: "offline", reason: "", retry: false };
    }
    if (!tablet.engine) {
      return { status: "no_engine", reason: "", retry: false };
    }
    if (!tablet.dashboard) {
      return { status: "no_dashboard", reason: "", retry: false };
    }
    return { status: tablet.sending ? "sending" : "on_tablet", reason: "", retry: false };
  };

  const publicTablet = (tablet) => ({
    mac: tablet.mac,
    device_id: tablet.device_id,
    name: tablet.name,
    short_name: tablet.short_name,
    model: tablet.model,
    dashboard: tablet.approved ? tablet.dashboard : null,
    ...statusOf(tablet),
    engine: tablet.engine,
    paired: tablet.approved && tablet.paired,
    input: tablet.approved ? tablet.input : "not_paired",
    entity_id: tablet.entity_id,
    approved: tablet.approved,
    suggested: !tablet.approved && isTab(tablet.suggested) ? tablet.suggested : null,
    reauth: tablet.reauth || null,
    reauth_name: tablet.reauth ? tablet.reauth_name || tablet.name : null,
  });

  // The tablets an admin turned on; only they show and count.
  const approvedTablets = () => tablets.filter((tablet) => tablet.approved);

  // Sorted like the integration: name in lower case, then MAC.
  const tabletList = () =>
    tablets
      .map(publicTablet)
      .sort((a, b) => byCodePoint(a.name.toLowerCase(), b.name.toLowerCase()) || byCodePoint(a.mac, b.mac));

  const emitTablets = () =>
    queueMicrotask(() => emit("apollo_tab/tablets/subscribe", { type: "tablets", tablets: tabletList() }));

  const finishSend = (tablet) => {
    tablet.sending = false;
    clearTimeout(tablet.timer);
    tablet.timer = null;
    emitTablets();
  };

  // Sends the tablet's dashboard: "sending" until the stand-in tablet has
  // built it, then "on_tablet". Offline tablets and tablets without the
  // dashboard software keep the choice for later.
  const send = (tablet) => {
    clearTimeout(tablet.timer);
    tablet.timer = null;
    tablet.sending = Boolean(tablet.approved && tablet.dashboard && tablet.online && tablet.engine && !tablet.forced);
    if (tablet.sending && !sends.hold) {
      tablet.timer = setTimeout(() => finishSend(tablet), sends.delay);
    }
  };

  // Either form of the MAC, in any case, as the integration takes it.
  const macHex = (mac) => String(mac).toLowerCase().replace(/[^0-9a-f]/g, "");
  const tabletByMac = (mac) => {
    const tablet = tablets.find((entry) => macHex(entry.mac) === macHex(mac));
    if (!tablet) {
      throw fail("not_found", "This tablet is not known");
    }
    return tablet;
  };

  // The first TAB-1 dashboard made goes to every approved tablet that has
  // none. A new tablet waits for an admin. announce: false gives it without
  // a send and without an event, as for a browser whose connection is down.
  const giveToOrphans = (announce = true) => {
    const first = tabOrder()[0]?.url_path || null;
    if (!first) {
      return;
    }
    let changed = false;
    for (const tablet of approvedTablets()) {
      if (!tablet.dashboard && !tablet.forced) {
        tablet.dashboard = first;
        if (announce) {
          send(tablet);
        }
        changed = true;
      }
    }
    if (changed && announce) {
      emitTablets();
    }
  };

  // A deleted dashboard's approved tablets move to the first one left, or
  // to none. A new tablet loses it as its suggestion. announce: false moves
  // them without a send and without an event, as for a browser whose
  // connection is down.
  const moveFrom = (urlPath, announce = true) => {
    const next = tabOrder().find((dashboard) => dashboard.url_path !== urlPath)?.url_path || null;
    let changed = false;
    for (const tablet of tablets) {
      if (!tablet.approved && tablet.suggested === urlPath) {
        tablet.suggested = null;
        changed = true;
      }
    }
    for (const tablet of approvedTablets()) {
      if (tablet.dashboard === urlPath) {
        tablet.dashboard = next;
        if (announce) {
          send(tablet);
        }
        changed = true;
      }
    }
    if (changed && announce) {
      emitTablets();
    }
  };

  const itemOf = (dashboard) => {
    const { config: _config, ...item } = dashboard;
    return structuredClone(item);
  };

  const byId = (id) => [...dashboards.values()].find((entry) => entry.id === id);

  // announce: false stores without the event, as for a browser whose
  // connection is down at the time.
  const store = (urlPath, config, announce = true) => {
    const dashboard = dashboards.get(urlPath);
    const wasTab = isTabConfig(dashboard.config);
    dashboard.config = structuredClone(config);
    const becameTab = !wasTab && isTabConfig(dashboard.config);
    if (!announce) {
      // The tablets get it all the same; only this browser hears nothing.
      if (becameTab) {
        giveToOrphans(false);
      }
      return;
    }
    queueMicrotask(() =>
      emitLayout({ type: "converted", url_path: urlPath, hash: String(++counter), warnings: 0 }),
    );
    // The tablets that show it get the new version.
    const showing = approvedTablets().filter((tablet) => tablet.dashboard === urlPath);
    for (const tablet of showing) {
      send(tablet);
    }
    if (showing.length) {
      emitTablets();
    }
    if (becameTab) {
      giveToOrphans();
    }
  };

  // Listeners for the connection's own events, such as "ready".
  const connectionListeners = new Map();

  // Like the integration, "pages" is the number of screens in the converted
  // layout: a page with no cards gives none, a long page gives several.
  // In the one order, like the integration.
  const tabDashboards = async () => {
    const list = [];
    for (const dashboard of tabOrder()) {
      const config = dashboard.config;
      const settings = config.apollo_tab;
      const converted = await preview(config);
      list.push({
        url_path: dashboard.url_path,
        title: dashboard.title,
        mode: dashboard.mode,
        theme: typeof settings.theme === "string" ? settings.theme : "midnight",
        pages: converted.layout.pages.length,
        warnings: converted.warnings.length,
        hash: converted.layout.hash,
        shown_on: approvedTablets()
          .filter((tablet) => tablet.dashboard === dashboard.url_path)
          .map((tablet) => tablet.mac)
          .sort(byCodePoint),
      });
    }
    const states = tabletList().filter((tablet) => tablet.approved);
    return {
      dashboards: list,
      // The stand-in has no dashboard that cannot be read.
      unreadable: [],
      // New tablets show nothing and are not counted.
      tablets: states.length,
      sent_to_tablets: states.some((tablet) => tablet.status === "on_tablet"),
    };
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
      if (isUnknown(message.type)) {
        throw fail("unknown_command", "Unknown command.");
      }
      const failures = failing.get(message.type) || 0;
      if (failures > 0) {
        failing.set(message.type, failures - 1);
        throw fail("error", "Fixture error");
      }
      if (slow.get(message.type) > 0) {
        await new Promise((resolve) => setTimeout(resolve, slow.get(message.type)));
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
        case "apollo_tab/tablets":
          return { tablets: tabletList() };
        case "apollo_tab/tablet/assign": {
          const tablet = tabletByMac(message.mac);
          // Only "Turn on with this dashboard" sends approve: a plain
          // assign never turns a new tablet on.
          if (!tablet.approved && message.approve !== true) {
            throw fail("not_approved", NOT_APPROVED);
          }
          if (!isTab(message.url_path)) {
            throw fail("unknown_dashboard", "This dashboard does not exist");
          }
          // The admin's explicit act turns a new tablet on.
          if (!tablet.approved || tablet.dashboard !== message.url_path) {
            tablet.approved = true;
            tablet.suggested = null;
            tablet.dashboard = message.url_path;
            send(tablet);
            emitTablets();
          }
          return { tablet: publicTablet(tablet) };
        }
        case "apollo_tab/tablet/pair": {
          const tablet = tabletByMac(message.mac);
          if (!tablet.approved) {
            throw fail("not_approved", NOT_APPROVED);
          }
          return { tablet: publicTablet(tablet) };
        }
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
          moveFrom(dashboard.url_path);
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
          // Home Assistant's answer to a command nobody registered.
          throw fail("unknown_command", "Unknown command.");
      }
    },
    connection: {
      async subscribeMessage(callback, message, options) {
        if (isUnknown(message.type)) {
          throw fail("unknown_command", "Unknown command.");
        }
        const record = { callback, message, resubscribe: options?.resubscribe !== false };
        listeners.add(record);

        if (message.type === "apollo_tab/tablets/subscribe") {
          queueMicrotask(() => {
            if (listeners.has(record)) {
              callback({ type: "tablets", tablets: tabletList() });
            }
          });
        }

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
    // down: no "removed" event reaches this browser. The tablets that
    // showed it move all the same.
    deleteWhileOffline(urlPath) {
      if (!dashboards.delete(urlPath)) {
        throw fail("not_found", "Dashboard not found");
      }
      moveFrom(urlPath, false);
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
    // A subscription made with resubscribe: false went with the old
    // connection. So did one Home Assistant does not take again (see
    // unknownCommands), and nobody is told of that. Commands that waited go
    // out after that.
    reconnect() {
      connection.down = false;
      for (const record of [...listeners]) {
        if (!record.resubscribe || isUnknown(record.message.type)) {
          listeners.delete(record);
        }
      }
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
    // How many subscriptions of one type are open.
    subscriptions(type) {
      return [...listeners].filter((record) => record.message.type === type).length;
    },
    // Home Assistant does not know the commands whose type starts with
    // `prefix`, because it is still starting or its integration is an older
    // one: they are answered unknown_command, as commands and as
    // subscribes. null: it knows them all again.
    unknownCommands(prefix) {
      unknownPrefix = prefix ?? null;
    },
    failSaves(count) {
      failingSaves = Math.max(0, Number(count) || 0);
    },
    // The next `count` calls of one command type fail.
    failCalls(type, count) {
      failing.set(type, Math.max(0, Number(count) || 0));
    },
    // Every later command of one type is answered after `ms` milliseconds
    // (0: at once again), as on a slow connection.
    slowCalls(type, ms) {
      slow.set(type, Math.max(0, Number(ms) || 0));
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
    // The tablets as the integration would send them.
    getTablets() {
      return tabletList();
    },
    // Changes a stand-in tablet, for example {online: false} or
    // {engine: "0.1.0"}; a tablet that comes online or gets the dashboard
    // software is sent its dashboard. quiet: true changes it without a
    // send and without telling the panel, as a change whose event has not
    // arrived yet; emitTablets() tells it later.
    setTablet(mac, changes, { quiet = false } = {}) {
      const tablet = tabletByMac(mac);
      Object.assign(tablet, changes);
      if (quiet) {
        return;
      }
      send(tablet);
      emitTablets();
    },
    // Sends the tablet list to the panel, as Home Assistant does on a change.
    emitTablets() {
      emitTablets();
    },
    // Sends stay at "sending" until finishSends.
    holdSends() {
      sends.hold = true;
    },
    finishSends() {
      sends.hold = false;
      for (const tablet of tablets) {
        if (tablet.sending) {
          finishSend(tablet);
        }
      }
    },
    // How long the stand-in tablets take to build a dashboard.
    sendDelay(ms) {
      sends.delay = Math.max(0, Number(ms) || 0);
    },
    // The integration is unloaded (or reloaded): the tablet subscriptions
    // get their last event, as from Home Assistant.
    unloadIntegration() {
      emit("apollo_tab/tablets/subscribe", { type: "not_loaded" });
    },
  };

  return hass;
}
