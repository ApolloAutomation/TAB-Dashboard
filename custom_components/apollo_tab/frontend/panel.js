import {
  assignTablet,
  getConnection,
  loadLibrary,
  loadStrings,
  onLayoutChanged,
  onLibraryChanged,
  onTabletsChanged,
  pairTablet,
  previewLayout,
  t,
} from "./api.js";
import { defineAliases } from "./card.js";
import { applyAccent, el, focusLost, icon, makeButton, screenHeading } from "./card-form.js";
import { keptChanges, onKeptChanges } from "./designer.js";
import {
  cardCount,
  mergeDashboards,
  newDashboardConfig,
  nextDashboardPath,
  nextDashboardTitle,
  notShownCounts,
} from "./model.js";
import { flag, setFlag } from "./prefs.js";
import { renderPage } from "./render.js";
import { canvasStyles, panelStyles, rendererStyles } from "./styles.js";
import {
  PREPICK_ONLY_DASHBOARD,
  REPAIRS_PATH,
  TURN_ON_SETTLE_MS,
  approvedTablets,
  claimedEnding,
  deviceBeforeLine,
  deviceLineParts,
  devicePagePath,
  homeWordsKey,
  inputNoteKey,
  isNewTablet,
  keepOrder,
  markAll,
  markMoved,
  markPicks,
  nameWarns,
  newTablets,
  offlineHelpKey,
  pairAgainIn,
  prepicked,
  pressCounts,
  reauthLine,
  showsChangeAssigns,
  showsOptions,
  shownOnText,
  statusTone,
  tabletName,
  turnOnSettled,
} from "./tablets.js";

const DEFAULT_PREFIX = "/apollo-tab";
// The width under which the panel is laid out for a phone, as the editor's.
const COMPACT_BELOW = 900;
const URL_PATH_RE = /^[a-z0-9_-]+$/;
const GUIDE_URL = "https://github.com/ApolloAutomation/TAB-Dashboard";
// The guide to writing a card, inside the repository.
const CARD_GUIDE_URL = `${GUIDE_URL}/blob/main/docs/components.md`;
// The guide's sample picture: a fixed dashboard of one page, drawn by the
// tablet's renderer through the preview call. Nothing is saved.
const sampleCard = (component, params) => ({ type: "custom:apollo-tab-card", component, params });
const SAMPLE_CONFIG = {
  apollo_tab: { version: 1, theme: "midnight" },
  views: [
    {
      type: "sections",
      title: "Home",
      path: "home",
      icon: "mdi:home",
      max_columns: 3,
      sections: [
        {
          title: "Lights",
          cards: [
            sampleCard("apollo/light-tile", { entity: "light.kitchen" }),
            sampleCard("apollo/light-tile", { entity: "light.living_room" }),
            sampleCard("apollo/light-slider", { entity: "light.bedroom" }),
            sampleCard("apollo/light-tile", { entity: "light.hallway" }),
            sampleCard("apollo/light-tile", { entity: "light.porch" }),
          ],
        },
        {
          title: "Climate",
          cards: [
            sampleCard("apollo/thermostat", { entity: "climate.hallway" }),
            sampleCard("apollo/sensor-value", { entity: "sensor.indoor_temperature" }),
            sampleCard("apollo/sensor-value", { entity: "sensor.indoor_humidity" }),
          ],
        },
        {
          title: "Outside",
          cards: [
            sampleCard("apollo/weather", { entity: "weather.home" }),
            sampleCard("apollo/scene-row", { scenes: ["scene.movie", "scene.dinner"] }),
            sampleCard("apollo/sensor-graph", { entity: "sensor.power" }),
          ],
        },
      ],
    },
  ],
};
// The sample's values, by slot number as the converter numbers the slots of
// SAMPLE_CONFIG. They are fixed, so the picture never shows this home's own
// states (most homes have none of these entities).
const SAMPLE_VALUES = {
  1: "Kitchen",
  2: "on",
  3: "80%",
  4: "Living room",
  5: "off",
  6: "0%",
  7: "Bedroom",
  8: "on",
  9: 45,
  10: "45%",
  11: "Hallway",
  12: "off",
  13: "0%",
  14: "Porch",
  15: "on",
  16: "100%",
  17: "Hallway",
  18: 21,
  19: 7,
  20: 35,
  21: 0.5,
  22: "Now 20.5° · heating",
  23: "Indoor",
  24: "21.5°C",
  25: "Humidity",
  26: "48%",
  27: "Home",
  28: "mdi:weather-sunny",
  29: "18° · sunny",
  30: [18, 19, 17, 16, 18],
  31: "Movie",
  32: "Dinner",
  33: "Power",
  34: [0.4, 0.5, 0.4, 0.9, 1.4, 1.1, 0.6, 0.5, 0.8, 1.2, 0.7, 0.5],
  35: "0.5 kW",
};
const SAMPLE_LAST_SLOT = "35";
// True when the preview's slots are the ones SAMPLE_VALUES fills: none
// beyond them, and the last one there. A slot whose template fails on this
// home is left out by the server, so fewer is fine. If a card changes its
// slots the picture is left out rather than drawn with values in the wrong
// places.
// A tablet picture's own shadow root inside its holder, as in the editor: it
// holds the tablet's styles and none of the panel's, so the panel's button
// rules (its smallest height and padding) cannot reach the drawn page.
// Returns the element to draw into.
const pictureHost = (holder) => {
  const root = holder.shadowRoot || holder.attachShadow({ mode: "open" });
  const style = el("style");
  style.textContent = rendererStyles + canvasStyles;
  const host = el("div");
  root.replaceChildren(style, host);
  return host;
};
const sampleSlotsMatch = (values) => {
  const keys = Object.keys(values || {});
  return keys.includes(SAMPLE_LAST_SLOT) && keys.every((key) => key in SAMPLE_VALUES);
};
// Home Assistant's page where a new tablet shows up by itself.
const DEVICES_PATH = "/config/integrations/dashboard";
// The rows of "What does the tablet's screen say?": the tablet's own
// headline (tablets.screen.*) and what to do (tablets.screen_help.*).
// "starting" has no row of its own: it says the same as "wait_ha".
const SCREEN_ROWS = [
  "hotspot",
  "connecting",
  "add",
  "erased",
  "turn_on",
  "wait_ha",
  "loading",
  "pick",
  "closed",
  "no_wifi",
];

// When the panel first saw each tablet not set up for taps. Kept while
// Home Assistant makes the panel again, so "Set up again" still comes
// after a while.
const notPairedSince = new Map();

function errorMessage(error) {
  return error?.message || error?.code || String(error ?? "");
}

// Turns a path below the panel's prefix into one of the three screens:
// "" (Home), "/edit/<url_path>" (Editor) or "/advanced". Anything else is Home.
function parsePath(path) {
  const clean = typeof path === "string" ? path.replace(/\/+$/, "") : "";
  if (clean === "/advanced") {
    return "/advanced";
  }
  const match = /^\/edit\/([^/]+)$/.exec(clean);
  if (match) {
    let urlPath = "";
    try {
      urlPath = decodeURIComponent(match[1]);
    } catch {
      return "";
    }
    if (URL_PATH_RE.test(urlPath)) {
      return `/edit/${urlPath}`;
    }
  }
  return "";
}

function alertLine(text) {
  const line = el("p", "alert", text);
  line.setAttribute("role", "alert");
  return line;
}

// A link to a page of Home Assistant itself, named with its tablet ("Open
// Repairs Kitchen tablet"). A plain click moves inside Home Assistant
// without a reload, as its own links do; it stays a real link for a new tab.
function haLink(className, text, path, mac, kind) {
  const link = el("a", className, text);
  link.href = path;
  link.id = `tablet-${kind}-${mac}`;
  link.dataset.focus = `${kind}:${mac}`;
  link.setAttribute("aria-labelledby", `${link.id} tablet-name-${mac}`);
  link.addEventListener("click", (event) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed"));
  });
  return link;
}

export class ApolloTabPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._style = el("style");
    this._style.textContent = panelStyles;
    this.shadowRoot.append(this._style);

    this._hass = null;
    this._narrow = false;
    this._route = null;
    this._panel = null;
    this._path = "";
    this._conn = null;
    this._loading = false;
    this._stops = [];
    // The guide's sample picture (_guideSample).
    this._sample = null;
    this._sampleAsked = false;
    this._library = null;
    this._home = null;
    this._failure = null;
    this._refreshSeq = 0;
    this._creating = false;
    this._createError = "";
    this._advancedMessage = null;
    this._advancedBusy = false;
    this._designer = null;
    this._restoreFocus = null;
    // Whether a screen has been drawn yet, and whether the next drawing is
    // of another screen, whose heading then takes focus.
    this._drawn = false;
    this._headingFocus = false;
    // The tablets as Home Assistant last sent them (null until it has), a
    // final failure to get them, and per tablet the failure of the last
    // change made here and the changes still under way ("shows:<mac>").
    this._tablets = null;
    this._tabletsError = null;
    this._tabletErrors = new Map();
    this._tabletBusy = new Set();
    // Per new tablet, the dashboard picked in its "Shows" list. Picking only
    // chooses; "Turn on with this dashboard" turns the tablet on.
    this._chosen = new Map();
    // Per tablet asked here to set up again, "" once Home Assistant took
    // the request or the words of its failure; and the timer that offers
    // "Set up again" once a tablet has waited long enough.
    this._pairAnswers = new Map();
    this._pairTimer = null;
    this._pairDue = 0;
    // What Home drew for the tablets, so a new list changes only words and
    // values in place (see _updateTablets): {box, rows, shownOn, shape}.
    this._tabletUi = null;
    // The order Home lists the tablets in while the panel stays open (their
    // MACs), so a tablet just turned on stays where it was. And where each
    // "Turn on with this dashboard" button was last seen, with when each
    // last moved: a button that moved under the pointer ignores presses for
    // a moment, so the second click of a double click turns no other tablet
    // on. The box is watched for changes of size that the panel did not
    // make, such as a narrower window.
    this._tabletOrder = null;
    this._turnOnPlaces = null;
    this._turnOnMovedAt = new Map();
    this._settleTimer = null;
    // What the editor handed over when it left for this screen: { tablet,
    // dashboard } for a tablet to set up, {} for the Tablets box. Kept in
    // memory only, for the one drawing after that exit (see _arrive).
    this._handover = null;
    this._pendingExit = null;
    // This visit to the start screen (reset where _tabletOrder is): whether
    // a read of the dashboards started in it has answered, and the new
    // tablets of its first tablet list that are still new (tablets.js
    // prepicked). What each turn-on button would send at the last look,
    // and the MAC whose list the person changed since then.
    this._visit = { fresh: false, waiting: null };
    this._turnOnSends = null;
    this._ownPick = null;
    // What began on a turn-on button since its last click (tablets.js
    // pressCounts), and the MAC whose button took the first click of the
    // current run of clicks.
    this._press = null;
    this._runStart = null;
    // Fold-outs someone opened: offline tablets' "What to do", and "What
    // does the tablet's screen say?". The guide's hidden flag.
    this._openHelp = new Set();
    this._screenSaysOpen = false;
    this._guideHidden = flag("guide_hidden");
    // The place the left-out link opens the editor at (designer.openAt).
    this._openAt = null;
    this._tabletsObserver = null;
    this._watchedBox = null;
    // The theme last read for the accent colours (see _themeChanged), and
    // what watches the panel's own width for the compact layout.
    this._themeSeen = null;
    this._accentFrame = 0;
    this._sizeObserver = null;

    // The first click of each run of clicks: which turn-on button it was
    // on, if any. Seen before the button's own listener.
    this.shadowRoot.addEventListener(
      "click",
      (event) => {
        if (event.detail === 1) {
          const button = event.target?.closest?.('[data-test="tablet-turn-on"]');
          this._runStart = button ? button.dataset.mac : null;
        }
      },
      true,
    );
    // The second click of a double click that comes right after a scroll
    // the panel made lands on whatever is there now: it neither takes
    // focus from the tablet's name nor gives it to a turn-on button.
    this._scrolledAt = -Infinity;
    this.shadowRoot.addEventListener(
      "mousedown",
      (event) => {
        if (event.detail >= 2 && performance.now() - this._scrolledAt < TURN_ON_SETTLE_MS) {
          event.preventDefault();
        }
      },
      true,
    );

    this._onPopState = () => {
      const prefix = this._prefix();
      const { pathname } = window.location;
      if (pathname === prefix || pathname.startsWith(`${prefix}/`)) {
        this._setPath(pathname.slice(prefix.length));
      }
    };
  }

  set hass(value) {
    const first = !this._hass;
    this._hass = value;
    this._themeChanged(value);
    if (first) {
      this._load();
      this._draw();
      return;
    }
    // hass changes with every state change; passing it on without redrawing
    // keeps focus and open controls where they are.
    if (this._designer) {
      this._designer.hass = value;
    }
    for (const menu of this.shadowRoot.querySelectorAll("ha-menu-button")) {
      menu.hass = value;
    }
  }

  get hass() {
    return this._hass;
  }

  set narrow(value) {
    const next = Boolean(value);
    if (next === this._narrow) {
      return;
    }
    this._narrow = next;
    if (this._designer) {
      this._designer.narrow = next;
    }
    if (!this._isEditor()) {
      this._draw();
    }
  }

  get narrow() {
    return this._narrow;
  }

  set route(value) {
    this._route = value;
    this._setPath(value?.path);
  }

  get route() {
    return this._route;
  }

  set panel(value) {
    this._panel = value;
  }

  get panel() {
    return this._panel;
  }

  // Home Assistant hands over a new hass before it has written the new
  // theme's colours to the page, so the accent is read again on the next
  // frame as well.
  _themeChanged(hass) {
    const seen = [hass?.themes, hass?.selectedTheme];
    if (this._themeSeen && seen[0] === this._themeSeen[0] && seen[1] === this._themeSeen[1]) {
      return;
    }
    this._themeSeen = seen;
    if (!this.isConnected) {
      return;
    }
    applyAccent(this);
    cancelAnimationFrame(this._accentFrame);
    this._accentFrame = requestAnimationFrame(() => applyAccent(this));
  }

  // Under 900 px the panel takes the class compact, which makes every
  // control a touch target (styles.js), in the editor and its dialogs too.
  _checkCompact() {
    this.classList.toggle("compact", this.getBoundingClientRect().width < COMPACT_BELOW);
  }

  connectedCallback() {
    applyAccent(this);
    if (typeof ResizeObserver === "function" && !this._sizeObserver) {
      this._sizeObserver = new ResizeObserver(() => this._checkCompact());
    }
    this._sizeObserver?.observe(this);
    this._checkCompact();
    window.addEventListener("popstate", this._onPopState);
    // The panel places each screen itself (rule 7). The browser's own
    // restoring of an old scroll after Back or Forward would move the page,
    // and the buttons on it, after the panel has placed the new screen.
    if (this._scrollRestoration === undefined && "scrollRestoration" in history) {
      this._scrollRestoration = history.scrollRestoration;
      history.scrollRestoration = "manual";
    }
    // Home marks a dashboard whose last change is not saved yet.
    this._stopKept = onKeptChanges(() => {
      if (this._path === "") {
        this._draw();
      }
    });
    this._load();
    this._draw();
  }

  disconnectedCallback() {
    this._sizeObserver?.disconnect();
    cancelAnimationFrame(this._accentFrame);
    window.removeEventListener("popstate", this._onPopState);
    if (this._scrollRestoration !== undefined) {
      history.scrollRestoration = this._scrollRestoration;
      this._scrollRestoration = undefined;
    }
    this._stopKept?.();
    this._stopKept = null;
    this._stops.forEach((stop) => stop?.());
    this._stops = [];
    this._conn = null;
    this._loading = false;
    this._tabletUi = null;
    this._tabletOrder = null;
    this._visit = { fresh: false, waiting: null };
    this._handover = null;
    // A pick does not outlive the visit, also when the same panel is put
    // back into the page.
    this._chosen.clear();
    this._forgetTurnOnPlaces();
    clearTimeout(this._pairTimer);
    this._pairTimer = null;
  }

  _prefix() {
    return this._route?.prefix || DEFAULT_PREFIX;
  }

  _isEditor() {
    return this._path.startsWith("/edit/");
  }

  _setPath(path) {
    const next = parsePath(path);
    // A handover is for the move it came with; any other move drops it.
    // Home Assistant sets the route while the event of the move is sent, so
    // a move to the screen already shown keeps the handover.
    const exit = this._pendingExit;
    this._pendingExit = null;
    if (next === this._path) {
      return;
    }
    const wasEditor = this._isEditor();
    this._handover = next === "" && wasEditor && exit ? { ...exit, arrived: false } : null;
    this._path = next;
    // Home drawn again after another screen lists the tablets in the usual
    // order, new ones first; nothing moves under a pointer there yet. A new
    // visit: the dashboards must be read again before anything is picked.
    this._tabletOrder = null;
    this._visit = { fresh: false, waiting: null };
    // A dashboard picked for a new tablet on an earlier visit is dropped:
    // each visit starts at "Pick a dashboard", so no Turn on button can be
    // pressed until a dashboard is picked again.
    this._chosen.clear();
    this._forgetTurnOnPlaces();
    // The control that moved to the new screen went with the old one; focus
    // goes to the new screen's heading. The first screen the panel shows
    // leaves focus where Home Assistant put it.
    this._headingFocus = this._drawn;
    if (next === "" && this._conn) {
      this._refresh();
    } else if (next === "") {
      // No read can answer for this visit's handover.
      this._handover = null;
    }
    this._draw();
  }

  // handover: what the editor hands to the start screen (see _arrive).
  // The handover is set first: Home Assistant may set the route while the
  // event is sent, and that move must find it.
  _go(path, handover = null) {
    this._pendingExit = handover && typeof handover === "object" ? handover : null;
    history.pushState(null, "", this._prefix() + path);
    window.dispatchEvent(new CustomEvent("location-changed"));
    this._setPath(path);
  }

  async _load() {
    if (!this._hass || !this.isConnected || this._loading || this._conn) {
      return;
    }
    this._loading = true;
    try {
      const conn = await getConnection(this._hass);
      await loadStrings(conn);
      this._conn = conn;
    } catch (error) {
      this._loading = false;
      this._failure = error;
      this._draw();
      return;
    }
    this._loading = false;
    if (!this.isConnected) {
      this._conn = null;
      return;
    }
    // The first list comes at once, usually before the dashboards.
    this._stops.push(
      onTabletsChanged(this._conn, (tablets) => this._onTablets(tablets), {
        onError: (error) => {
          this._tabletsError = error;
          this._updateTablets();
        },
      }),
    );
    await this._refresh();
    if (!this.isConnected || !this._conn) {
      return;
    }
    this._stops.push(
      onLibraryChanged(this._conn, (library) => {
        this._setLibrary(library);
        if (!this._isEditor()) {
          this._refresh();
        }
      }),
      onLayoutChanged(
        this._conn,
        () => this._refreshUnlessEditing(),
        () => this._refreshUnlessEditing(),
      ),
    );
  }

  _retry() {
    this._failure = null;
    this._draw();
    if (this._conn) {
      this._refresh();
    } else {
      this._load();
    }
  }

  // Older dashboards may use the per-card types; they keep drawing as long
  // as those elements are defined.
  _setLibrary(library) {
    this._library = library || null;
    if (library) {
      defineAliases(library);
    }
    if (this._designer && library) {
      this._designer.library = library;
    }
  }

  _refreshUnlessEditing() {
    if (!this._isEditor()) {
      this._refresh();
    }
  }

  async _refresh() {
    if (!this._conn) {
      return;
    }
    const seq = ++this._refreshSeq;
    const visit = this._visit;
    let counting = null;
    try {
      const [library, tab, list] = await Promise.all([
        loadLibrary(this._conn, { force: true }),
        this._hass.callWS({ type: "apollo_tab/dashboards" }),
        this._hass.callWS({ type: "lovelace/dashboards/list" }),
      ]);
      const tabs = Array.isArray(tab?.dashboards) ? tab.dashboards : [];
      const configs = await this._dashboardConfigs(tabs);
      if (seq !== this._refreshSeq) {
        return;
      }
      this._setLibrary(library);
      this._home = {
        rows: mergeDashboards(tabs, Array.isArray(list) ? list : [], configs),
        unreadable: Array.isArray(tab?.unreadable) ? tab.unreadable : [],
        notShown: {},
        cards: Object.fromEntries(Object.entries(configs).map(([urlPath, config]) => [urlPath, cardCount(config)])),
        // What the tablet would show for each dashboard, for its picture.
        previews: this._home?.previews || {},
      };
      this._failure = null;
      counting = { configs, library };
      if (visit === this._visit) {
        visit.fresh = true;
        this._pickHandover();
      }
    } catch (error) {
      if (seq !== this._refreshSeq) {
        return;
      }
      this._failure = error;
      if (visit === this._visit) {
        this._handover = null;
      }
    }
    if (!this._isEditor()) {
      this._draw();
    }
    // Not awaited, so a slow answer holds up nothing else; without counts a
    // row simply has no "not shown" line.
    if (counting) {
      this._countNotShown(seq, counting.configs, counting.library).catch(() => {});
    }
  }

  // Rule 9 of the security review: the dashboard the editor handed over
  // becomes that one new tablet's pick once this visit's read of the
  // dashboards has answered, if the gate is on and it is still listed.
  // The button then waits (markPicks). Nothing is sent.
  _pickHandover() {
    const handover = this._handover;
    this._handover = null;
    if (!PREPICK_ONLY_DASHBOARD || !handover?.tablet || typeof handover.dashboard !== "string") {
      return;
    }
    const tablet = this._tabletByMac(handover.tablet);
    const rows = this._home?.rows || [];
    if (!tablet || !isNewTablet(tablet) || !rows.some((row) => row?.url_path === handover.dashboard)) {
      return;
    }
    if (this._prepick(tablet) !== handover.dashboard) {
      this._chosen.set(tablet.mac, handover.dashboard);
    }
  }

  _tabletByMac(mac) {
    return (Array.isArray(this._tablets) ? this._tablets : []).find((entry) => entry?.mac === mac) || null;
  }

  // How many cards and pages of each dashboard the tablet leaves out, as the
  // editor marks them. It needs what the tablet would show for each one, so
  // the list is drawn first and the counts are added when they arrive.
  async _countNotShown(seq, configs, library) {
    const previews = await this._dashboardPreviews(configs);
    if (seq !== this._refreshSeq || !this._home) {
      return;
    }
    const notShown = {};
    for (const [urlPath, config] of Object.entries(configs)) {
      notShown[urlPath] = notShownCounts(config, library, previews[urlPath] ?? null);
    }
    this._home = { ...this._home, notShown, previews };
    if (this._path === "") {
      // In place: a press that is under way on the screen is not lost.
      this._updateTiles();
    } else if (!this._isEditor()) {
      this._draw();
    }
  }

  // Each dashboard's own config, by url_path, so Home can count the pages
  // the editor shows. A config that cannot be read is left out, and its row
  // shows no count.
  async _dashboardConfigs(tabs) {
    const entries = await Promise.all(
      tabs
        .map((entry) => entry?.url_path)
        .filter((urlPath) => typeof urlPath === "string")
        .map((urlPath) =>
          this._hass
            .callWS({ type: "lovelace/config", url_path: urlPath, force: false })
            .then(
              (config) => [urlPath, config],
              () => null,
            ),
        ),
    );
    return Object.fromEntries(entries.filter(Boolean));
  }

  // What the tablet would show for each dashboard, by url_path, so a row can
  // say when cards or pages are left out, as the editor does. A dashboard
  // whose preview fails is counted from its config alone.
  async _dashboardPreviews(configs) {
    const conn = this._conn;
    const entries = await Promise.all(
      Object.entries(configs).map(([urlPath, config]) =>
        Promise.resolve(conn && previewLayout(conn, config)).then(
          (preview) => [urlPath, preview],
          () => null,
        ),
      ),
    );
    return Object.fromEntries(entries.filter(Boolean));
  }

  // "1 card and 1 page are left out on tablets.", or "" when everything
  // is shown.
  _notShownText(counts) {
    const parts = [];
    if (counts?.cards) {
      parts.push(t(counts.cards === 1 ? "home.count_card_one" : "home.count_cards", { count: counts.cards }));
    }
    if (counts?.pages) {
      parts.push(t(counts.pages === 1 ? "home.count_page_one" : "home.count_pages", { count: counts.pages }));
    }
    if (!parts.length) {
      return "";
    }
    const items = parts.length === 2 ? t("home.count_and", { first: parts[0], second: parts[1] }) : parts[0];
    const one = counts.cards + counts.pages === 1;
    return t(one ? "home.not_shown_one" : "home.not_shown_many", { items });
  }

  // ---- drawing ---------------------------------------------------------

  _draw() {
    if (!this._hass) {
      return;
    }
    if (this._isEditor()) {
      this._showEditor(this._path.slice("/edit/".length));
      this._drawn = true;
      return;
    }
    const moved = this._headingFocus;
    this._headingFocus = false;
    // The handover is kept until this visit's read of the dashboards has
    // answered (_pickHandover); the arrival happens once, at the drawing
    // right after the move.
    const handover = this._path === "" && this._handover && !this._handover.arrived ? this._handover : null;
    if (handover) {
      handover.arrived = true;
    }
    // A control that is disabled while its action runs gets focus back once
    // the action has finished and it is drawn enabled again.
    const focusKey = moved ? null : this.shadowRoot.activeElement?.dataset?.focus || this._restoreFocus || null;
    this._restoreFocus = null;
    const nodes = this._path === "/advanced" ? this._advancedNodes() : this._homeNodes();
    this.shadowRoot.replaceChildren(this._style, ...nodes);
    this._drawn = true;
    this._drawPictures();
    this._noteTabletLayout();
    if (handover && moved) {
      this._arrive(handover);
      return;
    }
    if (moved && focusLost()) {
      // The new screen's heading is brought into view with it (the page
      // may still be scrolled down from the last screen); every turn-on
      // button waits anyway after a new screen's first look.
      const heading = this.shadowRoot.querySelector('[data-focus="heading"]');
      if (heading) {
        this._scrollAndMark(heading, "nearest", heading);
      }
      return;
    }
    if (focusKey) {
      const target = [...this.shadowRoot.querySelectorAll("[data-focus]")].find(
        (node) => node.dataset.focus === focusKey,
      );
      if (target && !target.disabled) {
        target.focus({ preventScroll: true });
      } else if (target) {
        this._restoreFocus = focusKey;
      }
    }
  }

  _showEditor(urlPath) {
    if (!this._designer) {
      this._designer = document.createElement("apollo-tab-designer");
      // A handover ({ tablet, dashboard } or {}) stays in memory only.
      this._designer.onExit = (handover) => this._go("", handover || null);
      this._designer.onAdvanced = () => this._go("/advanced");
    }
    const designer = this._designer;
    if (this._headingFocus) {
      this._headingFocus = false;
      designer.focusTitleWhenReady();
    }
    designer.narrow = this._narrow;
    if (this._library) {
      designer.library = this._library;
    }
    // The left-out link's place: read by the editor when it loads.
    if (this._openAt) {
      designer.openAt = this._openAt;
      this._openAt = null;
    }
    designer.urlPath = urlPath;
    designer.hass = this._hass;
    if (designer.parentNode !== this.shadowRoot) {
      this.shadowRoot.replaceChildren(this._style, designer);
    }
  }

  // Home Assistant's menu button decides for itself when to show: on a
  // narrow screen, or when the person set the sidebar to always hidden.
  // Older versions decide from hass and narrow, so both are passed on.
  _header(children) {
    const header = el("header", "panel-header");
    const menu = document.createElement("ha-menu-button");
    menu.hass = this._hass;
    menu.narrow = this._narrow;
    header.append(menu, ...children);
    return header;
  }

  _homeNodes() {
    const text = el("div");
    const intro = el("p", null, t("home.intro"));
    intro.dataset.test = "home-intro";
    text.append(screenHeading(t("home.title")), intro);
    const header = this._header([text]);

    const main = el("main", "panel-content");
    main.dataset.test = "home";

    if (this._failure) {
      main.append(this._failureBox());
      return [header, main];
    }
    if (!this._home) {
      main.append(this._loadingBoxes());
      return [header, main];
    }

    const guide = this._guide();
    if (guide) {
      main.append(guide);
    }
    main.append(this._tabletsBox());

    // With no dashboard yet the guide holds the one way to make one.
    const rows = this._home.rows;
    if (rows.length || !guide) {
      const block = el("section", "box dashboards");
      block.dataset.test = "dashboards";
      block.append(el("h2", null, t("home.list_title")));
      const tiles = el("div", "dashboard-tiles");
      for (const row of rows) {
        tiles.append(this._dashboardRow(row));
      }
      tiles.append(this._createTile(rows.length === 0));
      block.append(tiles);
      if (this._createError) {
        block.append(alertLine(this._createError));
      }
      main.append(block);
    } else if (this._createError) {
      main.append(alertLine(this._createError));
    }

    // Advanced, as one settings row that opens it: cog, name, reason,
    // chevron.
    const advanced = el("section", "box advanced-link");
    const open = makeButton(null, {
      className: "settings-row",
      test: "open-advanced",
      focus: "open-advanced",
      onClick: () => this._go("/advanced"),
    });
    const words = el("span", "row-text");
    words.append(el("span", "settings-title", t("home.advanced")), el("span", "small", t("home.advanced_hint")));
    open.append(icon("mdi:cog"), words, icon("mdi:chevron-right"));
    advanced.append(open);
    main.append(advanced);
    return [header, main];
  }

  // Grey boxes where the start screen's parts come, while it loads. A
  // screen reader hears "Loading…" once.
  _loadingBoxes() {
    const wrap = el("div", "loading-boxes");
    wrap.dataset.test = "home-loading";
    const words = el("p", "sr-only", t("home.loading"));
    words.setAttribute("role", "status");
    wrap.append(words);
    for (const size of ["short", "tall", "tall"]) {
      const shape = el("div", `loading-box ${size}`);
      shape.setAttribute("aria-hidden", "true");
      wrap.append(shape);
    }
    return wrap;
  }

  // The three steps of a new owner (spec 4.2): a tablet, a dashboard, the
  // dashboard on the tablet. Shown while there is no dashboard, while a new
  // tablet waits, or until a tablet shows a dashboard, unless the person hid
  // it. Its button only scrolls and gives focus; turning a tablet on stays
  // the row's own button.
  _guide() {
    const rows = this._home?.rows || [];
    const tablets = Array.isArray(this._tablets) ? this._tablets : null;
    const listed = new Set(rows.map((row) => row?.url_path));
    const anyOn = tablets ? approvedTablets(tablets).some((tablet) => listed.has(tablet.dashboard)) : false;
    const waitingNow = tablets ? newTablets(tablets).length > 0 : false;
    if (this._guideHidden || (rows.length && (!tablets || (anyOn && !waitingNow)))) {
      return null;
    }
    const box = el("section", "box guide");
    box.dataset.test = "first-run";
    const top = el("div", "guide-top");
    const hide = makeButton(t("home.guide_hide"), {
      className: "text",
      test: "guide-hide",
      focus: "guide-hide",
      onClick: () => {
        setFlag("guide_hidden");
        this._guideHidden = true;
        this._restoreFocus = "tablets-heading";
        this._draw();
        this.shadowRoot.querySelector('[data-focus="tablets-heading"]')?.focus({ preventScroll: true });
      },
    });
    top.append(el("h2", null, t("home.guide_title")), hide);
    box.append(top);

    const found = tablets || [];
    const waiting = newTablets(found);
    const list = el("ol", "guide-steps");
    const step = (number, done, title, detail, extra) => {
      const item = el("li", "guide-step");
      item.dataset.done = String(done);
      const mark = el("span", "guide-mark", done ? "" : String(number));
      mark.setAttribute("aria-hidden", "true");
      if (done) {
        mark.append(icon("mdi:check"));
      }
      const words = el("div", "guide-words");
      const head = el("h3", null, title);
      if (done) {
        head.append(el("span", "sr-only", ` ${t("home.guide_done")}`));
      }
      words.append(head);
      if (detail) {
        words.append(el("p", "small", detail));
      }
      if (extra) {
        words.append(extra);
      }
      item.append(mark, words);
      return item;
    };
    // 1: a tablet. Its way in is the link under the Tablets box. Up to
    // three names; with more, the first two and how many more.
    // The rows' own names, so the guide and the rows name a tablet alike.
    const names = found.map((tablet) => tabletName(tablet));
    const foundText =
      names.length > 3
        ? t("home.guide_1_more", { names: names.slice(0, 2).join(", "), count: names.length - 2 })
        : t("home.guide_1_done", { names: names.join(", ") });
    list.append(
      step(
        1,
        found.length > 0,
        t("home.guide_1"),
        found.length ? foundText : t("home.guide_1_none"),
        found.length ? null : this._addLink("guide-add"),
      ),
    );
    // 2: a dashboard; the one filled button while there is none.
    list.append(
      step(
        2,
        rows.length > 0,
        t("home.guide_2"),
        rows.length ? rows.map((row) => row.title).join(", ") : t("home.guide_2_none"),
        rows.length ? null : this._createButton(true),
      ),
    );
    // 3: on the tablet. It names the tablet when one waits alone.
    let detail = t("home.guide_3_wait");
    let go = null;
    if (found.length && rows.length && waiting.length) {
      const one = waiting.length === 1 ? waiting[0] : null;
      detail = one
        ? t("home.guide_3_one", { tablet: tabletName(one) })
        : t("home.guide_3_many", { count: waiting.length });
      go = makeButton(one ? t("home.guide_go_one", { tablet: tabletName(one) }) : t("home.guide_go_many"), {
        test: "guide-go",
        focus: "guide-go",
        onClick: () => this._guideGo(one ? one.mac : null),
      });
    }
    list.append(step(3, anyOn && !waitingNow, t("home.guide_3"), detail, go));
    const body = el("div", "guide-body");
    body.append(list);
    const sample = this._guideSample();
    if (sample) {
      body.append(sample);
    }
    box.append(body);
    return box;
  }

  // At the right of the guide: a sample dashboard in the tablet's frame,
  // 320 x 200, hidden on panels under 900 px (styles.js). It is asked for
  // once; until it comes, or if it cannot be had, the guide has no picture.
  _guideSample() {
    if (!this._sampleAsked && this._conn) {
      this._sampleAsked = true;
      Promise.resolve(previewLayout(this._conn, SAMPLE_CONFIG)).then(
        (preview) => {
          if (Array.isArray(preview?.layout?.pages) && preview.layout.pages.length && sampleSlotsMatch(preview.values)) {
            this._sample = preview;
            this._updateGuide();
          }
        },
        () => {},
      );
    }
    if (!this._sample) {
      return null;
    }
    const figure = el("figure", "guide-sample");
    // Only a picture: no focus, nothing for a screen reader.
    figure.setAttribute("aria-hidden", "true");
    figure.inert = true;
    const frame = el("div", "guide-sample-frame");
    const screen = el("div", "guide-sample-screen");
    const layout = this._sample.layout;
    const scale = 320 / (layout.screen?.[0] || 1280);
    // The fixed values, never this home's states (SAMPLE_VALUES).
    renderPage(pictureHost(screen), layout, 0, { values: SAMPLE_VALUES, errors: {} }, { sx: scale, sy: scale, interactive: false, tablet: true });
    frame.append(screen);
    figure.append(frame, el("figcaption", "small", t("home.sample")));
    return figure;
  }

  // The guide's button: the tablet's row (or the Tablets box) is scrolled
  // into view at once and focus goes to its name (or the heading), as on
  // arrival from the editor. Nothing is picked and nothing is sent.
  _guideGo(mac) {
    const ui = this._tabletUi;
    if (!ui?.box?.isConnected) {
      return;
    }
    const row = mac ? ui.rows.get(mac)?.row : null;
    const target = row || ui.box;
    const focus = row
      ? row.querySelector(`[data-focus="name:${CSS.escape(mac)}"]`)
      : ui.box.querySelector('[data-focus="tablets-heading"]');
    this._scrollAndMark(target, row ? "center" : "start", focus);
  }

  // The one way the panel scrolls (rule 7): at once, never smoothly, then
  // every turn-on button waits again, then focus without another scroll.
  _scrollAndMark(target, block, focus) {
    target.scrollIntoView({ block, behavior: "instant" });
    this._scrolledAt = performance.now();
    this._markAllTurnOns();
    focus?.focus({ preventScroll: true });
  }

  // Every turn-on button waits again (tablets.js markAll).
  _markAllTurnOns() {
    const places = this._turnOnPlaces;
    if (this._path !== "" || !places?.size) {
      return;
    }
    this._turnOnMovedAt = markAll(this._turnOnMovedAt, [...places.keys()], performance.now());
    this._showSettling();
  }

  _failureBox() {
    const box = el("section", "box");
    box.append(
      alertLine(t("home.load_failed", { message: errorMessage(this._failure) })),
      makeButton(t("home.retry"), { className: "primary", test: "retry", onClick: () => this._retry() }),
    );
    return box;
  }

  // ---- tablets ---------------------------------------------------------

  _onTablets(tablets) {
    const before = this._tablets;
    this._tablets = tablets;
    this._tabletsError = null;
    // A choice is kept only while its tablet is still new.
    const waiting = new Set((Array.isArray(tablets) ? tablets : []).filter(isNewTablet).map((tablet) => tablet.mac));
    for (const mac of [...this._chosen.keys()]) {
      if (!waiting.has(mac)) {
        this._chosen.delete(mac);
      }
    }
    // A tablet that stopped being new leaves this visit's waiting set for
    // good; nothing is ever added to it.
    this._visit.waiting = this._stillWaiting(this._visit.waiting);
    this._updateTablets();
    // A tablet that starts or stops showing "cannot be read" means the list
    // of dashboards changed too (one broke, or came back): read it again.
    const broken = (list) =>
      (Array.isArray(list) ? list : [])
        .filter((tablet) => tablet?.reason === "unreadable")
        .map((tablet) => `${tablet.mac}:${tablet.dashboard}`)
        .sort()
        .join(",");
    if (Array.isArray(before) && broken(before) !== broken(tablets)) {
      this._refreshUnlessEditing();
    }
  }

  // What decides how the Tablets box is built; while it stays the same, a
  // new list only changes words and values in the rows already there, so a
  // "Shows" list someone has open stays open. A new tablet's row holds a
  // link to its device page, which is built with the row.
  _tabletShape() {
    if (this._tabletsError) {
      return `error:${errorMessage(this._tabletsError)}`;
    }
    if (!Array.isArray(this._tablets)) {
      return "loading";
    }
    const rows = this._home?.rows || [];
    return JSON.stringify(
      this._orderedTablets().map((tablet) => [
        tablet.mac,
        tabletName(tablet),
        isNewTablet(tablet),
        isNewTablet(tablet) ? devicePagePath(tablet) : null,
        rows.length ? this._showsOptions(rows, tablet) : null,
        this._listDrawn(tablet),
        nameWarns(tablet),
      ]),
    );
  }

  // The tablets in Home's order, which stays while the panel is open: a
  // tablet keeps its row when it is turned on, so the row under the
  // pointer is still the one that was clicked.
  _orderedTablets() {
    const ordered = keepOrder(this._tablets, this._tabletOrder);
    this._tabletOrder = ordered.map((tablet) => tablet.mac);
    return ordered;
  }

  // The waiting set without the tablets that are no longer new.
  _stillWaiting(waiting) {
    if (!(waiting instanceof Set)) {
      return waiting;
    }
    const now = new Set((Array.isArray(this._tablets) ? this._tablets : []).filter(isNewTablet).map((tablet) => tablet.mac));
    return new Set([...waiting].filter((mac) => now.has(mac)));
  }

  // The dashboard picked for a new tablet without the person (tablets.js
  // prepicked, rule 2), worked out at each look; never kept in _chosen.
  _prepick(tablet) {
    return prepicked({
      tablet,
      rows: this._home?.rows || [],
      unreadable: this._home?.unreadable || [],
      fresh: this._visit.fresh,
      waiting: this._visit.waiting,
    });
  }

  // What a new tablet's turn-on button would send: the person's pick while
  // it is still listed, else the pre-pick, else null.
  _wouldSend(mac) {
    const tablet = this._tabletByMac(mac);
    if (!tablet || !isNewTablet(tablet)) {
      return null;
    }
    const rows = this._home?.rows || [];
    const chosen = this._chosen.get(mac);
    if (chosen && rows.some((row) => row?.url_path === chosen)) {
      return chosen;
    }
    return this._prepick(tablet);
  }

  // Whether a tablet's row has a "Shows" list: there are dashboards, and no
  // pre-pick already names the only one.
  _listDrawn(tablet) {
    return (this._home?.rows || []).length > 0 && !this._prepick(tablet);
  }

  // Notes where each "Turn on with this dashboard" button is now, and when
  // each one moved or came: a row above it changed its height, a tablet
  // came, the window got narrower, or the rows were first drawn. Words
  // that change without moving a button do not count, whichever row they
  // are in. Then what each button would send: one the person did not
  // choose in that row makes it wait again (tablets.js markPicks).
  _noteTabletLayout() {
    const ui = this._tabletUi;
    if (this._path !== "" || !ui || !ui.box.isConnected) {
      return;
    }
    this._watchTabletsBox(ui.box);
    if (!ui.rows.size) {
      this._turnOnPlaces = null;
      return;
    }
    const origin = this.getBoundingClientRect();
    const places = new Map();
    const sends = new Map();
    for (const [mac, refs] of ui.rows) {
      const button = refs.notes.querySelector('[data-test="tablet-turn-on"]');
      if (button) {
        const box = button.getBoundingClientRect();
        places.set(mac, [box.left - origin.left, box.top - origin.top, box.width, box.height]);
        sends.set(mac, button.disabled ? null : this._wouldSend(mac));
      }
    }
    // Only the buttons that moved get this time (tablets.js markMoved).
    this._turnOnMovedAt = markMoved(this._turnOnMovedAt, this._turnOnPlaces, places, performance.now());
    this._turnOnPlaces = places;
    this._turnOnMovedAt = markPicks(this._turnOnMovedAt, this._turnOnSends, sends, this._ownPick, performance.now());
    this._turnOnSends = sends;
    this._ownPick = null;
    this._showSettling();
  }

  // A button that moved a moment ago looks disabled until it takes presses
  // again, so a press it ignores is seen to do nothing. It keeps focus and
  // its place in the tab order.
  _showSettling() {
    clearTimeout(this._settleTimer);
    this._settleTimer = null;
    const ui = this._tabletUi;
    if (!ui) {
      return;
    }
    const now = performance.now();
    let wait = Infinity;
    for (const [mac, refs] of ui.rows) {
      const button = refs.notes.querySelector('[data-test="tablet-turn-on"]');
      if (!button) {
        continue;
      }
      const movedAt = this._turnOnMovedAt.get(mac);
      const settling = !turnOnSettled(movedAt, now);
      button.toggleAttribute("data-settling", settling);
      if (settling) {
        button.setAttribute("aria-disabled", "true");
        wait = Math.min(wait, movedAt + TURN_ON_SETTLE_MS - now);
      } else {
        button.removeAttribute("aria-disabled");
      }
    }
    if (wait !== Infinity) {
      this._settleTimer = setTimeout(() => {
        this._settleTimer = null;
        this._showSettling();
      }, Math.max(0, wait) + 10);
    }
  }

  // Rows can move without a change made here, for example when a narrower
  // window wraps their words: the box's size changes then.
  _watchTabletsBox(box) {
    if (this._watchedBox === box || typeof ResizeObserver !== "function") {
      return;
    }
    if (!this._tabletsObserver) {
      this._tabletsObserver = new ResizeObserver(() => this._noteTabletLayout());
    }
    this._tabletsObserver.disconnect();
    this._tabletsObserver.observe(box);
    this._watchedBox = box;
  }

  _forgetTurnOnPlaces() {
    this._turnOnPlaces = null;
    this._turnOnSends = null;
    this._ownPick = null;
    this._press = null;
    this._turnOnMovedAt = new Map();
    clearTimeout(this._settleTimer);
    this._settleTimer = null;
    this._tabletsObserver?.disconnect();
    this._watchedBox = null;
  }

  // Arriving from the editor with a handover: the tablet's row (only a new
  // tablet that is in the list now), else the Tablets box, is scrolled into
  // view at once, and focus goes to the tablet's name or the box's heading.
  // The scroll moves every Turn on button, so each one waits again. Nothing
  // is picked and nothing is sent.
  _arrive(handover) {
    const ui = this._tabletUi;
    if (!ui?.box?.isConnected) {
      this.shadowRoot.querySelector('[data-focus="heading"]')?.focus({ preventScroll: true });
      return;
    }
    const tablet = this._tabletByMac(handover.tablet);
    const row = tablet && isNewTablet(tablet) ? ui.rows.get(tablet.mac)?.row : null;
    // A row is centred; without one the Tablets heading goes to the top, so
    // the heading that takes focus and the new tablets under it are in view.
    const focus = row
      ? row.querySelector(`[data-focus="name:${CSS.escape(tablet.mac)}"]`)
      : ui.box.querySelector('[data-focus="tablets-heading"]');
    this._scrollAndMark(row || ui.box, row ? "center" : "start", focus);
  }

  _showsOptions(rows, tablet) {
    const suggested = isNewTablet(tablet) && typeof tablet.suggested === "string" ? tablet.suggested : null;
    return showsOptions(rows, tablet.dashboard, t, this._home?.unreadable, suggested);
  }

  // The Tablets box: one row per tablet with its name, its status as a
  // chip, the dashboard it shows and what to do. A change is saved at
  // once. New tablets come first: an admin picks a dashboard, then turns
  // the tablet on with a separate button. While the panel is open each
  // tablet keeps its place (see _orderedTablets).
  _tabletsBox() {
    const box = el("section", "box tablets");
    box.dataset.test = "tablets";
    const heading = el("h2", null, t("tablets.title"));
    // Focus comes here when the editor sends someone to the Tablets box.
    heading.tabIndex = -1;
    heading.dataset.focus = "tablets-heading";
    box.append(heading);
    const ui = { box, rows: new Map(), shownOn: new Map(), shape: this._tabletShape() };
    this._tabletUi = ui;

    if (this._tabletsError) {
      box.append(alertLine(t("tablets.load_failed", { message: errorMessage(this._tabletsError) })));
      return box;
    }
    if (!Array.isArray(this._tablets)) {
      box.append(el("p", "small", t("tablets.loading")));
      return box;
    }
    const tablets = this._orderedTablets();
    // The new tablets of this visit's first list (rule 2).
    if (this._visit.waiting === null) {
      this._visit.waiting = new Set(tablets.filter(isNewTablet).map((tablet) => tablet.mac));
    } else {
      this._visit.waiting = this._stillWaiting(this._visit.waiting);
    }
    if (!tablets.length) {
      const none = el("p", null, t("tablets.none"));
      none.dataset.test = "tablets-none";
      box.append(none);
    } else {
      const rows = this._home?.rows || [];
      for (const tablet of tablets) {
        const refs = this._tabletRow(tablet, rows);
        ui.rows.set(tablet.mac, refs);
        box.append(refs.row);
      }
    }
    // How to add a tablet, under the rows, where it moves no button.
    box.append(this._screenSays());
    return box;
  }

  // "How to add a tablet" opens what each of the tablet's own screens
  // means, with what to do. Open or shut, it stays so while the panel is
  // open.
  _screenSays() {
    const fold = el("details", "screen-says");
    fold.dataset.test = "screen-says";
    fold.open = this._screenSaysOpen;
    fold.addEventListener("toggle", () => {
      this._screenSaysOpen = fold.open;
    });
    const link = el("summary", "tablets-add", t("tablets.add_link"));
    link.dataset.test = "tablets-add";
    link.dataset.focus = "tablets-add";
    fold.append(link);
    const body = el("div", "screen-says-body");
    body.append(el("p", null, t("tablets.add_another")));
    body.append(el("h3", null, t("tablets.screen_title")), el("p", "small", t("tablets.screen_text")));
    const list = el("dl", "screen-list");
    for (const key of SCREEN_ROWS) {
      const term = el("dt", "screen-headline", t(`tablets.screen.${key}`));
      term.dataset.screen = key;
      const help = el("dd", null, t(`tablets.screen_help.${key}`));
      if (key === "add") {
        const open = el("a", "screen-devices", t("tablets.open_devices"));
        open.href = DEVICES_PATH;
        open.addEventListener("click", (event) => {
          if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
            return;
          }
          event.preventDefault();
          history.pushState(null, "", DEVICES_PATH);
          window.dispatchEvent(new CustomEvent("location-changed"));
        });
        help.append(document.createTextNode(" "), open);
      }
      const item = el("div", "screen-row");
      item.dataset.test = "screen-row";
      item.append(term, help);
      list.append(item);
    }
    body.append(list);
    fold.append(body);
    return fold;
  }

  // The guide's own "How to add a tablet": opens the fold-out under the
  // Tablets box and brings it into view.
  _addLink(test) {
    const link = makeButton(t("tablets.add_link"), {
      className: "link",
      test,
      focus: test,
      onClick: () => {
        const fold = this.shadowRoot.querySelector('[data-test="screen-says"]');
        if (!fold) {
          return;
        }
        fold.open = true;
        this._screenSaysOpen = true;
        this._scrollAndMark(fold, "start", fold.querySelector("summary"));
      },
    });
    return link;
  }

  _tabletRow(tablet, rows) {
    const mac = tablet.mac;
    const fresh = isNewTablet(tablet);
    const row = el("div", "tablet-row");
    row.dataset.test = "tablet-row";
    row.dataset.mac = mac;
    row.dataset.new = String(fresh);
    const name = el("h3", "tablet-name", tabletName(tablet));
    name.id = `tablet-name-${mac}`;
    // Focus goes here after "Turn on with this dashboard": a heading that
    // stays, never the "Shows" list, where an arrow key would switch the
    // tablet at once now that it is on.
    name.tabIndex = -1;
    name.dataset.focus = `name:${mac}`;
    const title = el("div", "tablet-title");
    const tile = el("span", "tablet-icon");
    tile.append(icon("mdi:tablet"));
    title.append(tile, name);
    if (fresh) {
      const mark = el("span", "tag tag-new", t("tablets.new_mark"));
      mark.dataset.test = "tablet-new";
      title.append(mark, ...this._deviceLines(tablet, rows));
    }

    let shows = null;
    let select = null;
    if (!rows.length) {
      // Nothing to pick from yet.
      shows = el("p", "tablet-shows small", t("tablets.make_first"));
      shows.dataset.test = "tablet-make-first";
    } else if (this._listDrawn(tablet)) {
      shows = el("label", "tablet-shows");
      select = document.createElement("select");
      select.dataset.test = "tablet-shows";
      select.dataset.focus = `shows:${mac}`;
      // Every row has a "Shows" list, so each is named with its tablet:
      // "Kitchen tablet Shows".
      const label = el("span", "field-label", t("tablets.shows"));
      label.id = `tablet-shows-${mac}`;
      select.setAttribute("aria-labelledby", `${name.id} ${label.id}`);
      for (const [value, text, disabled] of this._showsOptions(rows, tablet)) {
        const option = el("option", null, text);
        option.value = value;
        option.disabled = disabled;
        select.append(option);
      }
      select.value = this._wantedShows(tablet);
      select.addEventListener("change", () => {
        const current = this._tabletByMac(mac);
        if (showsChangeAssigns(current || tablet)) {
          this._assign(mac, select.value);
        } else {
          // A new tablet: a change only chooses, also one made by moving
          // through the list with the keyboard. The button turns it on.
          this._choose(mac, select.value);
        }
      });
      shows.append(label, select);
    }

    // The status chip sits under the name (spec 4.2).
    const status = el("p", "tablet-status");
    status.dataset.test = "tablet-status";
    status.setAttribute("role", "status");

    const notes = el("div", "tablet-notes");
    row.append(title, status);
    if (shows) {
      row.append(shows);
    }
    row.append(notes);
    const refs = { row, select, status, notes, notesKey: null };
    this._fillTabletRow(refs, tablet);
    return refs;
  }

  // Under a new tablet's name: what to check on the tablet before turning
  // it on (the end of its name on its screen, in a fixed-width face) and a
  // link to its device page, because the name comes from the device itself
  // and anything can call itself "Porch tablet". A name that ends in
  // another address is warned about. A tablet that showed a dashboard
  // before keeps it on its screen instead of its name; a line says so.
  _deviceLines(tablet, rows) {
    const mac = tablet.mac;
    const lines = [];
    if (nameWarns(tablet)) {
      const warning = el("p", "notice tablet-name-warning", t("tablets.name_warning", { ending: claimedEnding(tablet) }));
      warning.dataset.tone = "warn";
      warning.dataset.test = "tablet-name-warning";
      lines.push(warning);
    }
    const line = el("p", "tablet-device meta");
    line.dataset.test = "tablet-device";
    line.id = `tablet-check-${mac}`;
    const [before, ending, after] = deviceLineParts(tablet, t);
    const code = el("span", "tablet-mac", ending);
    code.dataset.test = "tablet-mac";
    line.append(document.createTextNode(before), code, document.createTextNode(after));
    const path = devicePagePath(tablet);
    if (path) {
      line.append(document.createTextNode(" "));
      // "Open device page Porch tablet": every such link says which tablet.
      const link = haLink("tablet-device-page", t("tablets.device_page"), path, mac, "device");
      link.dataset.test = "tablet-device-page";
      line.append(link);
    }
    lines.push(line);
    const was = deviceBeforeLine(tablet, rows, t);
    if (was) {
      const note = el("p", "tablet-device meta", was);
      note.dataset.test = "tablet-device-before";
      lines.push(note);
    }
    // Any device can call itself a TAB-1; the admin is the check. The
    // warning comes before "Shows" and the button it is about.
    const warn = el("p", "small tablet-check-warning", t("tablets.approve_note"));
    warn.dataset.test = "tablet-approve-note";
    warn.id = `tablet-approve-note-${mac}`;
    lines.push(warn);
    return lines;
  }

  // What a tablet's "Shows" list holds: the dashboard an approved tablet
  // shows, or what was picked for a new one (nothing at first).
  _wantedShows(tablet) {
    if (isNewTablet(tablet)) {
      return this._chosen.get(tablet.mac) || "";
    }
    return typeof tablet.dashboard === "string" ? tablet.dashboard : "";
  }

  // Puts the tablet's words and values into its row. A value someone is
  // changing right now is left alone until Home Assistant has answered.
  _fillTabletRow(refs, tablet) {
    const key = homeWordsKey(tablet, (this._home?.rows || []).length > 0);
    const words = key ? t(key) : "";
    if (refs.status.textContent !== words) {
      refs.status.textContent = words;
    }
    refs.status.dataset.tone = statusTone(tablet);
    refs.status.dataset.status = typeof tablet.status === "string" ? tablet.status : "";
    const fresh = isNewTablet(tablet);
    const wanted = this._wantedShows(tablet);
    if (refs.select && !this._tabletBusy.has(`shows:${tablet.mac}`) && refs.select.value !== wanted) {
      refs.select.value = wanted;
    }
    if (fresh && refs.select && this._chosen.has(tablet.mac) && refs.select.value !== wanted) {
      // The chosen dashboard is no longer in the list.
      this._chosen.delete(tablet.mac);
    }

    const lines = [];
    // Home Assistant waits for an admin before it connects again, for
    // example after the tablet was erased: first, with the way to Repairs.
    const reauth = reauthLine(tablet, t);
    if (reauth) {
      lines.push(["reauth", reauth, "tablet-reauth"]);
    }
    if (fresh) {
      if ((this._home?.rows || []).length) {
        lines.push(["turn-on", t("tablets.turn_on"), "tablet-turn-on"]);
      }
      // HA sends nothing to it, so it keeps what it shows now.
      lines.push(["small", t("tablets.waiting_note"), "tablet-waiting-note"]);
    } else if (tablet.status === "no_engine") {
      lines.push(["small", t("tablets.no_engine_help"), "tablet-help"]);
      // Only a tablet with a dashboard that exists has a choice to keep.
      const rows = this._home?.rows || [];
      if (typeof tablet.dashboard === "string" && rows.some((row) => row?.url_path === tablet.dashboard)) {
        lines.push(["small", t("tablets.no_engine_saved"), "tablet-help-saved"]);
      }
    }
    // Offline: what to check, and the way back onto a changed Wi-Fi, in
    // the row's "What to do".
    const offlineKey = offlineHelpKey(tablet);
    if (offlineKey) {
      lines.push(["help", t(offlineKey), "tablet-offline-help"]);
    }
    const noteKey = inputNoteKey(tablet);
    if (noteKey) {
      lines.push(["small", t(noteKey), "tablet-input"]);
    }
    // Set-up that has not worked for a while can be started again.
    if (this._pairAgainIn(tablet) === 0) {
      lines.push(["pair", t("tablets.pair_again"), "tablet-pair"]);
      const answer = this._pairAnswers.get(tablet.mac);
      if (answer === "") {
        lines.push(["small", t("tablets.pair_asked"), "tablet-pair-asked"]);
      } else if (answer) {
        lines.push(["alert", answer, "tablet-pair-error"]);
      }
    }
    const error = this._tabletErrors.get(tablet.mac);
    if (error) {
      lines.push(["alert", error, "tablet-error"]);
    }
    // Only a different text is drawn again, so a screen reader does not
    // read an unchanged alert once more. A button that had focus keeps it;
    // one that went (the tablet was turned on) leaves focus on the name.
    const notesKey = JSON.stringify(lines);
    if (notesKey !== refs.notesKey) {
      refs.notesKey = notesKey;
      const active = this.shadowRoot.activeElement;
      const focusKey = active && refs.notes.contains(active) ? active.dataset?.focus : null;
      refs.notes.replaceChildren(
        ...lines.map(([className, text, test]) => {
          if (className === "pair") {
            return this._pairButton(tablet.mac, text, test);
          }
          if (className === "turn-on") {
            return this._turnOnButton(tablet.mac, text, test);
          }
          if (className === "reauth") {
            return this._reauthNote(tablet.mac, text, test);
          }
          if (className === "help") {
            return this._whatToDo(tablet.mac, text, test);
          }
          const line = className === "alert" ? alertLine(text) : el("p", className, text);
          line.dataset.test = test;
          return line;
        }),
      );
      if (focusKey) {
        const find = (wanted) => [...refs.row.querySelectorAll("[data-focus]")].find((node) => node.dataset.focus === wanted);
        (find(focusKey) || find(`name:${tablet.mac}`))?.focus({ preventScroll: true });
      }
    }
    // Turning on needs a dashboard to send. The button's second line names
    // it. While the change is on its way the button stays as it is, so it
    // keeps focus; a second press is ignored.
    const turnOn = refs.notes.querySelector('[data-test="tablet-turn-on"]');
    if (turnOn) {
      const sends = this._wouldSend(tablet.mac);
      turnOn.disabled = !sends;
      const named = sends ? this._dashboardTitle(sends) : "";
      const second = turnOn.querySelector('[data-test="tablet-turn-on-name"]');
      if (second && second.textContent !== named) {
        second.textContent = named;
      }
      const first = refs.notes.querySelector('[data-test="tablet-pick-first"]');
      if (first) {
        first.dataset.shown = String(!sends);
      }
    }
  }

  _dashboardTitle(urlPath) {
    const row = (this._home?.rows || []).find((entry) => entry?.url_path === urlPath);
    return row?.title || urlPath;
  }

  // An offline tablet's "What to do": its help, folded. Open or shut, it
  // stays so while the panel is open.
  _whatToDo(mac, text, test) {
    const fold = el("details", "what-to-do");
    fold.dataset.test = "tablet-what-to-do";
    fold.open = this._openHelp.has(mac);
    fold.addEventListener("toggle", () => {
      if (fold.open) {
        this._openHelp.add(mac);
      } else {
        this._openHelp.delete(mac);
      }
    });
    const head = el("summary", null, t("tablets.what_to_do"));
    head.dataset.focus = `what-to-do:${mac}`;
    const line = el("p", "small", text);
    line.dataset.test = test;
    fold.append(head, line);
    return fold;
  }

  // "Turn on with this dashboard", with the dashboard it would send on a
  // second line, and "Pick a dashboard first." under it while it has none.
  // The button is the same size whatever it names, so a pick does not
  // move it, and it is never inside a label. Its press record (rule 6)
  // comes from its own listeners; the click asks pressCounts.
  _turnOnButton(mac, text, test) {
    const wrap = el("div", "turn-on-wrap");
    const button = makeButton(null, {
      className: "primary",
      test,
      focus: `turn-on:${mac}`,
      disabled: !this._wouldSend(mac),
      onClick: (event) => {
        const press = this._press?.mac === mac ? this._press : null;
        this._press = null;
        // One more look first: a button that moved since the last one, by
        // a change the panel was not told of, moved just now.
        this._noteTabletLayout();
        const now = performance.now();
        const click = { at: now, detail: event?.detail ?? 0, sends: this._wouldSend(mac) };
        const movedAt = this._turnOnMovedAt.get(mac);
        if (pressCounts({ press, click, movedAt, runStart: this._runStart, mac })) {
          this._turnOn(mac);
        }
      },
    });
    button.classList.add("tablet-turn-on");
    button.dataset.mac = mac;
    button.append(el("span", "turn-on-words", text));
    const second = el("span", "turn-on-name");
    second.dataset.test = "tablet-turn-on-name";
    button.append(second);
    // "Turn on with this dashboard Kitchen Porch tablet", described by the
    // check line and the note.
    button.id = `tablet-turn-on-${mac}`;
    button.setAttribute("aria-labelledby", `${button.id} tablet-name-${mac}`);
    button.setAttribute("aria-describedby", `tablet-check-${mac} tablet-approve-note-${mac}`);
    const record = (kind, extra) => {
      this._press = {
        mac,
        kind,
        at: performance.now(),
        repeat: false,
        foreign: false,
        sends: this._wouldSend(mac),
        ...extra,
      };
    };
    button.addEventListener("pointerdown", () => record("pointer"));
    button.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        record("key", { repeat: event.repeat });
      }
    });
    button.addEventListener("keyup", (event) => {
      if ((event.key === "Enter" || event.key === " ") && !(this._press?.mac === mac && this._press.kind === "key")) {
        // The key went down somewhere else. Chrome sends no click for
        // such a key-up; the record is for browsers that click on a bare
        // key-up. It is only for the click this key-up itself sets off;
        // after that it is dropped, so it cannot stop a later click that
        // has no press behind it (a screen reader's).
        record("key", { foreign: true });
        const mine = this._press;
        setTimeout(() => {
          if (this._press === mine) {
            this._press = null;
          }
        });
      }
    });
    const forget = () => {
      if (this._press?.mac === mac) {
        this._press = null;
      }
    };
    button.addEventListener("blur", forget);
    button.addEventListener("pointercancel", forget);
    const first = el("p", "small tablet-pick-first", t("tablets.pick_first"));
    first.dataset.test = "tablet-pick-first";
    // It keeps its place when it is not shown, so a pick moves nothing.
    first.dataset.shown = String(!this._wouldSend(mac));
    wrap.append(button, first);
    return wrap;
  }

  // What Home Assistant waits for, then "Open Repairs", where the admin
  // confirms it.
  _reauthNote(mac, text, test) {
    const line = el("p", "small tablet-reauth", `${text} `);
    line.dataset.test = test;
    const link = haLink("tablet-repairs", t("tablets.open_repairs"), REPAIRS_PATH, mac, "repairs");
    link.dataset.test = "tablet-repairs";
    line.append(link);
    return line;
  }

  // A dashboard picked in a new tablet's list: kept, not sent. The person's
  // own pick does not make the button wait (markPicks).
  _choose(mac, urlPath) {
    if (urlPath) {
      this._chosen.set(mac, urlPath);
    } else {
      this._chosen.delete(mac);
    }
    this._ownPick = mac;
    this._tabletErrors.delete(mac);
    this._updateTablets();
  }

  // The admin's explicit act that turns a new tablet on with the dashboard
  // its button names; the only change that sends approve. Called from the
  // button's click only, once pressCounts said the press counts. A press
  // of a button that moved a moment ago is ignored: it may be the second
  // click of a double click, landing on another tablet's button.
  _turnOn(mac) {
    const urlPath = this._wouldSend(mac);
    if (!urlPath || this._tabletBusy.has(`shows:${mac}`)) {
      return;
    }
    this._noteTabletLayout();
    if (!turnOnSettled(this._turnOnMovedAt.get(mac), performance.now())) {
      return;
    }
    this._assign(mac, urlPath, { approve: true });
  }

  _pairButton(mac, text, test) {
    const button = makeButton(text, { test, focus: `pair:${mac}`, onClick: () => this._pairAgain(mac) });
    button.classList.add("tablet-pair");
    // "Set up again Loft tablet": every such button says which tablet.
    button.id = `tablet-pair-${mac}`;
    button.setAttribute("aria-labelledby", `${button.id} tablet-name-${mac}`);
    return button;
  }

  // 0 when "Set up again" is offered for this tablet now, the time left
  // until then, or null when it is not needed. Wakes the Tablets box when
  // the time is up.
  _pairAgainIn(tablet) {
    const mac = tablet.mac;
    const now = Date.now();
    if (inputNoteKey(tablet) === "tablets.not_paired" && !notPairedSince.has(mac)) {
      notPairedSince.set(mac, now);
    }
    const wait = pairAgainIn(tablet, notPairedSince.get(mac), now);
    if (wait === null) {
      notPairedSince.delete(mac);
      this._pairAnswers.delete(mac);
    } else if (wait > 0 && (!this._pairTimer || now + wait < this._pairDue)) {
      clearTimeout(this._pairTimer);
      this._pairDue = now + wait;
      this._pairTimer = setTimeout(() => {
        this._pairTimer = null;
        this._updateTablets();
      }, wait + 100);
    }
    return wait;
  }

  async _pairAgain(mac) {
    const key = `pair:${mac}`;
    if (!this._conn || this._tabletBusy.has(key)) {
      return;
    }
    this._tabletBusy.add(key);
    this._pairAnswers.delete(mac);
    try {
      // The answer reaches every listener of the tablet list, this one too.
      await pairTablet(this._conn, mac);
      this._pairAnswers.set(mac, "");
    } catch (error) {
      this._pairAnswers.set(mac, t("tablets.pair_failed", { message: errorMessage(error) }));
    } finally {
      this._tabletBusy.delete(key);
      this._updateTablets();
    }
  }

  _fillShownOnLine(line, urlPath) {
    const text = Array.isArray(this._tablets) ? shownOnText(this._tablets, urlPath, t) : "";
    if (line.textContent !== text) {
      line.textContent = text;
      line.title = text;
    }
    line.hidden = !text;
  }

  // A new tablet list, or a change made here was answered: Home changes in
  // place what it can, and builds the Tablets box again only when its shape
  // changed (a tablet came or went, or the dashboards to pick from).
  _updateTablets() {
    if (this._path !== "" || !this._home || this._failure) {
      return;
    }
    const ui = this._tabletUi;
    if (!ui || !ui.box.isConnected) {
      this._draw();
      return;
    }
    if (ui.shape !== this._tabletShape()) {
      const active = this.shadowRoot.activeElement;
      const focusKey = ui.box.contains(active) ? active?.dataset?.focus : null;
      const shownOn = ui.shownOn;
      const box = this._tabletsBox();
      this._tabletUi.shownOn = shownOn;
      ui.box.replaceWith(box);
      if (focusKey) {
        const find = (wanted) => [...box.querySelectorAll("[data-focus]")].find((node) => node.dataset.focus === wanted);
        // The button that turned a new tablet on went with the old row; the
        // tablet's name in its new row takes focus. Not its "Shows" list:
        // an arrow key there would switch the tablet at once.
        // So does a "Shows" list that is no longer drawn (rule 8).
        const of = /^(turn-on|shows):(.+)$/.exec(focusKey);
        const target = find(focusKey) || (of ? find(`name:${of[2]}`) : null);
        target?.focus({ preventScroll: true });
      }
    } else if (Array.isArray(this._tablets)) {
      for (const tablet of this._tablets) {
        const refs = ui.rows.get(tablet?.mac);
        if (refs) {
          this._fillTabletRow(refs, tablet);
        }
      }
    }
    for (const [urlPath, line] of this._tabletUi.shownOn) {
      this._fillShownOnLine(line, urlPath);
    }
    this._updateGuide();
    this._noteTabletLayout();
  }

  // The guide follows the tablets: drawn again only when its words change.
  _updateGuide() {
    const old = this.shadowRoot.querySelector('[data-test="first-run"]');
    const next = this._guide();
    if (!old && !next) {
      return;
    }
    if (old && next && old.textContent === next.textContent) {
      return;
    }
    const active = this.shadowRoot.activeElement;
    const focusKey = old?.contains(active) ? active?.dataset?.focus : null;
    if (old && next) {
      old.replaceWith(next);
    } else if (old) {
      old.remove();
    } else {
      this._tabletUi?.box?.before(next);
    }
    if (focusKey) {
      const target =
        next?.querySelector(`[data-focus="${CSS.escape(focusKey)}"]`) ||
        this.shadowRoot.querySelector('[data-focus="tablets-heading"]');
      target?.focus({ preventScroll: true });
    }
  }

  // `approve` comes only from "Turn on with this dashboard". A change of an
  // approved tablet's list sends none, so if the tablet is new again by
  // now, Home Assistant refuses it and the tablet stays off.
  async _assign(mac, urlPath, { approve = false } = {}) {
    if (!urlPath || !this._conn) {
      return;
    }
    const key = `shows:${mac}`;
    this._tabletBusy.add(key);
    this._tabletErrors.delete(mac);
    try {
      // The answer reaches every listener of the tablet list, this one too.
      await assignTablet(this._conn, mac, urlPath, { approve });
    } catch (error) {
      this._tabletErrors.set(mac, t("tablets.failed", { message: errorMessage(error) }));
    } finally {
      this._tabletBusy.delete(key);
      // Puts back the dashboard the tablet really shows if that failed.
      this._updateTablets();
    }
  }

  // "Create a dashboard": filled in the guide, where it is the one filled
  // button of a start screen with no dashboard yet.
  _createButton(primary) {
    return makeButton(this._creating ? t("home.creating") : t("home.create"), {
      kind: primary ? "primary" : undefined,
      test: "create",
      focus: "create",
      disabled: this._creating,
      onClick: () => this._createDashboard(),
    });
  }

  // The last tile: dashed, with the same button; tonal once a dashboard
  // exists, filled when the guide is hidden and there is none.
  _createTile(primary) {
    const tile = el("div", "dashboard-tile create-tile");
    tile.append(icon("mdi:plus"), this._createButton(primary));
    return tile;
  }

  // A dashboard as a tile: a picture of its first page as the tablet draws
  // it, its name as a link over the whole tile, what it holds, where it is
  // shown and what the tablet leaves out.
  _dashboardRow(row) {
    const item = el("div", "dashboard-row dashboard-tile");
    item.dataset.test = "dashboard-row";
    item.dataset.urlPath = row.url_path;
    // Only a picture: no focus, nothing for a screen reader.
    const pic = el("div", "tablet-pic");
    pic.dataset.urlPath = row.url_path;
    pic.setAttribute("aria-hidden", "true");
    pic.inert = true;
    item.append(pic);

    const text = el("div", "row-text");
    const path = `/edit/${encodeURIComponent(row.url_path)}`;
    // The name is the link; it stretches over the tile. It stays a real
    // link so it can be opened in a new tab; a plain click moves without
    // a reload.
    const link = el("a", "tile-link", row.title);
    link.href = this._prefix() + path;
    link.dataset.test = row.editable ? "edit" : "view";
    link.dataset.focus = `${row.editable ? "edit" : "view"}:${row.url_path}`;
    link.addEventListener("click", (event) => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
        return;
      }
      event.preventDefault();
      this._go(path);
    });
    const name = el("h3", "tile-name");
    name.append(link);
    text.append(name);
    const meta = this._metaText(row);
    if (meta) {
      text.append(el("p", "meta", meta));
    }
    // "On Kitchen, Bedroom", kept up to date as the tablets change.
    const shownOn = el("p", "chip shown-on");
    shownOn.dataset.test = "row-shown-on";
    this._tabletUi?.shownOn.set(row.url_path, shownOn);
    this._fillShownOnLine(shownOn, row.url_path);
    text.append(shownOn);
    const left = this._notShownLink(row);
    if (left) {
      text.append(left);
    }
    // A change made in the editor that is not saved yet: the browser asks
    // before the page is closed, and this says which dashboard it is about.
    const kept = keptChanges().find((entry) => entry.urlPath === row.url_path);
    if (kept) {
      const line = el("p", "meta kept-change", t(kept.waiting ? "home.kept_waiting" : "home.kept_unsaved"));
      line.dataset.test = "row-kept-change";
      text.append(line);
    }
    if (row.show_in_sidebar && row.editable) {
      const tags = el("div", "row-tags");
      tags.append(el("span", "tag", t("home.in_sidebar")));
      text.append(tags);
    }
    if (!row.editable) {
      text.append(el("p", "small", t("home.yaml_note")));
    }
    item.append(text);
    // What a press on the tile does, as a label at its foot. The stretched
    // link above takes the press; a screen reader already hears the link.
    const action = el("span", "tile-action", t(row.editable ? "home.tile_edit" : "home.tile_view"));
    action.setAttribute("aria-hidden", "true");
    item.append(action);
    return item;
  }

  // What the tablet leaves out of a dashboard, as a link that opens the
  // editor at the first of it; null when nothing is left out.
  _notShownLink(row) {
    const counts = this._home?.notShown?.[row.url_path];
    const hidden = this._notShownText(counts);
    if (!hidden) {
      return null;
    }
    const left = makeButton(hidden, {
      className: "link",
      test: "row-not-shown",
      focus: `not-shown:${row.url_path}`,
      onClick: () => {
        const first = counts?.first;
        this._openAt = first ? { urlPath: row.url_path, view: first.view, source: first.source } : null;
        this._go(`/edit/${encodeURIComponent(row.url_path)}`);
      },
    });
    left.classList.add("over-link");
    return left;
  }

  // The counts and pictures came: each tile gets its left-out link and its
  // picture where it is, so nothing else on the screen is drawn again.
  _updateTiles() {
    for (const row of this._home?.rows || []) {
      const tile = [...this.shadowRoot.querySelectorAll('[data-test="dashboard-row"]')].find(
        (node) => node.dataset.urlPath === row.url_path,
      );
      if (!tile || tile.querySelector('[data-test="row-not-shown"]')) {
        continue;
      }
      const left = this._notShownLink(row);
      if (left) {
        tile.querySelector(".shown-on")?.after(left);
      }
    }
    this._drawPictures();
    this._noteTabletLayout();
  }

  // "2 pages, 3 cards", or "" before the dashboard was read.
  _metaText(row) {
    if (typeof row.pages !== "number") {
      return "";
    }
    const pages = t(row.pages === 1 ? "home.count_page_one" : "home.count_pages", { count: row.pages });
    const count = this._home?.cards?.[row.url_path];
    if (typeof count !== "number") {
      return pages;
    }
    const cards =
      count === 0
        ? t("home.count_card_none")
        : t(count === 1 ? "home.count_card_one" : "home.count_cards", { count });
    return t("home.meta", { pages, cards });
  }

  // Draws each tile's picture once the tiles are on the screen: the first
  // page the tablet would show, scaled to the tile. A dashboard whose
  // preview is not there yet keeps a plain box.
  _drawPictures() {
    const previews = this._home?.previews || {};
    for (const pic of this.shadowRoot.querySelectorAll(".tablet-pic")) {
      const preview = previews[pic.dataset.urlPath];
      const layout = preview?.layout;
      if (!layout || !Array.isArray(layout.pages) || !layout.pages.length) {
        continue;
      }
      // The frame's width rounded up, so the page fills it to the edge and
      // no line of the background shows inside the bezel; the frame cuts
      // off the rest.
      const width = Math.ceil(pic.getBoundingClientRect().width) || 240;
      const scale = width / (layout.screen?.[0] || 1280);
      renderPage(pictureHost(pic), layout, 0, { values: preview.values || {}, errors: {} }, { sx: scale, sy: scale, interactive: false, tablet: true });
    }
  }

  async _createDashboard() {
    if (this._creating) {
      return;
    }
    this._creating = true;
    this._createError = "";
    this._draw();
    try {
      const list = await this._hass.callWS({ type: "lovelace/dashboards/list" });
      const items = Array.isArray(list) ? list : [];
      const urlPath = nextDashboardPath([
        ...items.map((entry) => entry?.url_path).filter((path) => typeof path === "string"),
        ...Object.keys(this._hass.panels || {}),
      ]);
      const title = nextDashboardTitle(
        items.map((entry) => entry?.title).filter((name) => typeof name === "string"),
        t("home.default_name"),
      );
      const item = await this._hass.callWS({
        type: "lovelace/dashboards/create",
        url_path: urlPath,
        title,
        icon: "mdi:tablet-dashboard",
        mode: "storage",
        require_admin: false,
        show_in_sidebar: false,
      });
      try {
        await this._hass.callWS({
          type: "lovelace/config/save",
          url_path: urlPath,
          config: newDashboardConfig(t("home.default_page")),
        });
      } catch (error) {
        if (item?.id) {
          await this._hass
            .callWS({ type: "lovelace/dashboards/delete", dashboard_id: item.id })
            .catch(() => {});
        }
        throw error;
      }
      this._creating = false;
      this._go(`/edit/${urlPath}`);
    } catch (error) {
      this._creating = false;
      this._createError = t("home.create_failed", { message: errorMessage(error) });
      this._draw();
    }
  }

  _advancedNodes() {
    // Back is an icon button, as in the editor; its name says where to.
    const back = makeButton(null, {
      className: "icon back",
      test: "back",
      focus: "back",
      onClick: () => this._go(""),
    });
    back.setAttribute("aria-label", t("advanced.back"));
    back.title = t("advanced.back");
    back.append(icon("mdi:arrow-left"));
    const text = el("div");
    text.append(screenHeading(t("advanced.title")), el("p", null, t("advanced.intro")));
    const header = this._header([back, text]);

    const main = el("main", "panel-content");
    main.dataset.test = "advanced";
    if (this._failure) {
      main.append(this._failureBox());
      return [header, main];
    }
    const library = this._library;
    if (!library) {
      main.append(this._loadingBoxes());
      return [header, main];
    }
    const components = Array.isArray(library.components) ? library.components : [];
    const user = components.filter((component) => component?.source === "user");
    const builtin = components.length - user.length;

    const folder = el("section", "box");
    const reload = makeButton(t("advanced.reload"), {
      test: "reload-cards",
      focus: "reload-cards",
      disabled: this._advancedBusy,
      onClick: () => this._reloadCards(),
    });
    const guide = el("a", "card-guide", t("advanced.guide"));
    guide.href = CARD_GUIDE_URL;
    guide.target = "_blank";
    guide.rel = "noreferrer";
    // The folder as a field to read and copy, not to type in.
    const field = el("label", "path-field");
    const fieldLabel = el("span", "field-label", t("advanced.folder_path"));
    const pathBox = document.createElement("input");
    pathBox.type = "text";
    pathBox.readOnly = true;
    pathBox.className = "code-line";
    pathBox.value = library.components_path || "";
    pathBox.dataset.test = "folder-path";
    field.append(fieldLabel, pathBox);
    const copy = makeButton(t(this._copied ? "advanced.copied" : "advanced.copy"), {
      test: "copy-path",
      focus: "copy-path",
      onClick: () => this._copyPath(pathBox.value),
    });
    const pathRow = el("div", "path-row");
    pathRow.append(field, copy);
    const errors = Array.isArray(library.errors) ? library.errors : [];
    const chips = el("div", "row-tags count-chips");
    chips.append(
      el("span", "chip", t("advanced.count_builtin", { count: builtin })),
      el("span", "chip", t("advanced.count_user", { count: user.length })),
    );
    if (errors.length) {
      const bad = el("span", "chip", t("advanced.count_errors", { count: errors.length }));
      bad.dataset.tone = "err";
      chips.append(bad);
    }
    folder.append(
      el("h2", null, t("advanced.folder_title")),
      el("p", null, t("advanced.folder_text")),
      pathRow,
      chips,
      reload,
    );
    folder.append(...this._advancedLine("reload"));
    folder.append(guide);
    main.append(folder);

    const mine = el("section", "box");
    mine.append(el("h2", null, t("advanced.user_title")));
    if (!user.length) {
      mine.append(el("p", null, t("advanced.user_none")));
    }
    for (const component of user) {
      const row = el("div", "component-row");
      row.append(icon(component.icon));
      const text = el("div", "row-text");
      text.append(el("h3", null, component.name), el("p", "small card-id", component.id));
      row.append(text);
      mine.append(row);
    }
    main.append(mine);

    const locks = el("section", "box");
    locks.append(el("h2", null, t("advanced.locks_title")), el("p", null, t("advanced.locks_text")));
    const sensitive = user.filter((component) => component.sensitive);
    if (!sensitive.length) {
      locks.append(el("p", null, t("advanced.locks_none")));
    }
    for (const component of sensitive) {
      const row = el("div", "component-row");
      row.dataset.test = "lock-row";
      row.dataset.component = component.id;
      const text = el("div", "row-text");
      const tags = el("div", "row-tags");
      tags.append(el("span", "tag", t(component.approved ? "advanced.allowed" : "advanced.blocked")));
      text.append(el("h3", null, component.name), tags);
      const button = makeButton(t(component.approved ? "advanced.revoke" : "advanced.allow"), {
        test: "allow",
        focus: `allow:${component.id}`,
        disabled: this._advancedBusy,
        onClick: () => this._approve(component),
      });
      button.dataset.component = component.id;
      row.append(text, button);
      locks.append(row, ...this._advancedLine(component.id));
    }
    main.append(locks);

    if (errors.length) {
      const box = el("section", "box");
      const list = el("ul", "error-list");
      errors.forEach((error, index) => {
        list.append(
          el(
            "li",
            null,
            t("advanced.error_row", {
              file: error?.file ?? "",
              n: index + 1,
              message: error?.message ?? "",
            }),
          ),
        );
      });
      box.append(el("h2", null, t("advanced.errors_title")), el("p", null, t("advanced.errors_text")), list);
      main.append(box);
    }
    return [header, main];
  }

  // Copies the folder's path; the button says "Copied" for a moment. A
  // browser that refuses leaves the field to copy from by hand.
  async _copyPath(text) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      return;
    }
    this._copied = true;
    this._restoreFocus = "copy-path";
    this._draw();
    clearTimeout(this._copiedTimer);
    this._copiedTimer = setTimeout(() => {
      this._copied = false;
      if (this._path === "/advanced") {
        this._draw();
      }
    }, 2000);
  }

  // The result or failure message of the last action, shown next to it.
  _advancedLine(where) {
    const message = this._advancedMessage;
    if (!message || message.where !== where) {
      return [];
    }
    return [message.error ? alertLine(message.text) : el("p", "small", message.text)];
  }

  async _reloadCards() {
    this._advancedBusy = true;
    this._advancedMessage = null;
    this._draw();
    try {
      const result = await this._hass.callWS({ type: "apollo_tab/library/reload" });
      this._setLibrary(await loadLibrary(this._conn, { force: true }));
      this._advancedMessage = {
        where: "reload",
        text: t("advanced.reloaded", { count: result?.components ?? 0, errors: result?.errors ?? 0 }),
      };
    } catch (error) {
      this._advancedMessage = {
        where: "reload",
        error: true,
        text: t("advanced.failed", { message: errorMessage(error) }),
      };
    }
    this._advancedBusy = false;
    this._draw();
  }

  async _approve(component) {
    this._advancedBusy = true;
    this._advancedMessage = null;
    this._draw();
    try {
      await this._hass.callWS({
        type: "apollo_tab/library/approve",
        component_id: component.id,
        approved: !component.approved,
      });
      this._setLibrary(await loadLibrary(this._conn, { force: true }));
    } catch (error) {
      this._advancedMessage = {
        where: component.id,
        error: true,
        text: t("advanced.failed", { message: errorMessage(error) }),
      };
    }
    this._advancedBusy = false;
    this._draw();
  }
}
