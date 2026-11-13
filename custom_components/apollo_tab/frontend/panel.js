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
import { el, focusLost, icon, makeButton, screenHeading } from "./card-form.js";
import { keptChanges, onKeptChanges } from "./designer.js";
import {
  mergeDashboards,
  newDashboardConfig,
  nextDashboardPath,
  nextDashboardTitle,
  notShownCounts,
} from "./model.js";
import { panelStyles } from "./styles.js";
import {
  REPAIRS_PATH,
  TURN_ON_SETTLE_MS,
  deviceBeforeLine,
  deviceLine,
  devicePagePath,
  homeWordsKey,
  inputNoteKey,
  isNewTablet,
  keepOrder,
  markMoved,
  offlineHelpKey,
  pairAgainIn,
  reauthLine,
  showsChangeAssigns,
  showsOptions,
  shownOnText,
  statusTone,
  tabletName,
  turnOnSettled,
} from "./tablets.js";

const DEFAULT_PREFIX = "/apollo-tab";
const URL_PATH_RE = /^[a-z0-9_-]+$/;
const GUIDE_URL = "https://github.com/ApolloAutomation/TAB-Dashboard";
// The guide to writing a card, inside the repository.
const CARD_GUIDE_URL = `${GUIDE_URL}/blob/main/docs/components.md`;

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
    this._tabletsObserver = null;
    this._watchedBox = null;

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

  connectedCallback() {
    window.addEventListener("popstate", this._onPopState);
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
    window.removeEventListener("popstate", this._onPopState);
    this._stopKept?.();
    this._stopKept = null;
    this._stops.forEach((stop) => stop?.());
    this._stops = [];
    this._conn = null;
    this._loading = false;
    this._tabletUi = null;
    this._tabletOrder = null;
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
    if (next === this._path) {
      return;
    }
    const wasEditor = this._isEditor();
    this._path = next;
    // Home drawn again after another screen lists the tablets in the usual
    // order, new ones first; nothing moves under a pointer there yet.
    this._tabletOrder = null;
    this._forgetTurnOnPlaces();
    // The control that moved to the new screen went with the old one; focus
    // goes to the new screen's heading. The first screen the panel shows
    // leaves focus where Home Assistant put it.
    this._headingFocus = this._drawn;
    if (next === "" && wasEditor && this._conn) {
      this._refresh();
    }
    this._draw();
  }

  _go(path) {
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
      };
      this._failure = null;
      counting = { configs, library };
    } catch (error) {
      if (seq !== this._refreshSeq) {
        return;
      }
      this._failure = error;
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
    this._home = { ...this._home, notShown };
    if (!this._isEditor()) {
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
    // A control that is disabled while its action runs gets focus back once
    // the action has finished and it is drawn enabled again.
    const focusKey = moved ? null : this.shadowRoot.activeElement?.dataset?.focus || this._restoreFocus || null;
    this._restoreFocus = null;
    const nodes = this._path === "/advanced" ? this._advancedNodes() : this._homeNodes();
    this.shadowRoot.replaceChildren(this._style, ...nodes);
    this._drawn = true;
    this._noteTabletLayout();
    if (moved && focusLost()) {
      this.shadowRoot.querySelector('[data-focus="heading"]')?.focus();
      return;
    }
    if (focusKey) {
      const target = [...this.shadowRoot.querySelectorAll("[data-focus]")].find(
        (node) => node.dataset.focus === focusKey,
      );
      if (target && !target.disabled) {
        target.focus();
      } else if (target) {
        this._restoreFocus = focusKey;
      }
    }
  }

  _showEditor(urlPath) {
    if (!this._designer) {
      this._designer = document.createElement("apollo-tab-designer");
      this._designer.onExit = () => this._go("");
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
    text.append(screenHeading(t("home.title")), el("p", null, t("home.intro")));
    const header = this._header([text]);

    const main = el("main", "panel-content");
    main.dataset.test = "home";

    if (this._failure) {
      main.append(this._failureBox());
      return [header, main];
    }
    if (!this._home) {
      main.append(el("p", null, t("editor.loading")));
      return [header, main];
    }

    main.append(this._tabletsBox());

    const rows = this._home.rows;
    const block = el("section", "box");
    if (!rows.length) {
      block.dataset.test = "first-run";
      const steps = el("ol", "steps");
      steps.append(
        el("li", null, t("home.step_1")),
        el("li", null, t("home.step_2")),
        el("li", null, t("home.step_3")),
      );
      block.append(el("h2", null, t("home.empty_title")), el("p", null, t("home.empty_text")), steps);
      block.append(this._createButton("home.create"));
    } else {
      block.append(el("h2", null, t("home.list_title")));
      for (const row of rows) {
        block.append(this._dashboardRow(row));
      }
      block.append(this._createButton("home.create_another"));
    }
    if (this._createError) {
      block.append(alertLine(this._createError));
    }
    main.append(block);

    const advanced = el("div", "advanced-link");
    advanced.append(
      makeButton(t("home.advanced"), {
        className: "link",
        test: "open-advanced",
        focus: "open-advanced",
        onClick: () => this._go("/advanced"),
      }),
      el("p", "small", t("home.advanced_hint")),
    );
    main.append(advanced);
    return [header, main];
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
  // "Shows" list someone has open stays open.
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
        rows.length ? this._showsOptions(rows, tablet) : null,
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

  // Notes where each "Turn on with this dashboard" button is now, and when
  // each one moved or came: a row above it changed its height, a tablet
  // came, the window got narrower. Words that change without moving a
  // button do not count, whichever row they are in. Not when the first rows
  // come: until then there was nothing to press, and no dashboard is picked.
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
    for (const [mac, refs] of ui.rows) {
      const button = refs.notes.querySelector('[data-test="tablet-turn-on"]');
      if (button) {
        const box = button.getBoundingClientRect();
        places.set(mac, [box.left - origin.left, box.top - origin.top, box.width, box.height]);
      }
    }
    // Only the buttons that moved get this time (tablets.js markMoved).
    this._turnOnMovedAt = markMoved(this._turnOnMovedAt, this._turnOnPlaces, places, performance.now());
    this._turnOnPlaces = places;
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
    this._turnOnMovedAt = new Map();
    clearTimeout(this._settleTimer);
    this._settleTimer = null;
    this._tabletsObserver?.disconnect();
    this._watchedBox = null;
  }

  _showsOptions(rows, tablet) {
    const suggested = isNewTablet(tablet) && typeof tablet.suggested === "string" ? tablet.suggested : null;
    return showsOptions(rows, tablet.dashboard, t, this._home?.unreadable, suggested);
  }

  // The Tablets box at the top of Home: one row per tablet with its name,
  // the dashboard it shows and its status in plain words. A change is saved
  // at once. New tablets come first: an admin picks a dashboard, then turns
  // the tablet on with a separate button. While the panel is open each
  // tablet keeps its place (see _orderedTablets).
  _tabletsBox() {
    const box = el("section", "box tablets");
    box.dataset.test = "tablets";
    box.append(el("h2", null, t("tablets.title")));
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
    if (!tablets.length) {
      const none = el("p", null, t("tablets.none"));
      none.dataset.test = "tablets-none";
      box.append(none);
      return box;
    }
    const rows = this._home?.rows || [];
    for (const tablet of tablets) {
      const refs = this._tabletRow(tablet, rows);
      ui.rows.set(tablet.mac, refs);
      box.append(refs.row);
    }
    // How to add the next tablet, under the rows, where it moves no button.
    const add = el("p", "small tablets-add", t("tablets.add_another"));
    add.dataset.test = "tablets-add";
    box.append(add);
    return box;
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
    title.append(name);
    if (fresh) {
      const mark = el("span", "tag tag-new", t("tablets.new_mark"));
      mark.dataset.test = "tablet-new";
      title.append(mark, ...this._deviceLines(tablet, rows));
    }

    let shows;
    let select = null;
    if (rows.length) {
      shows = el("label", "tablet-shows");
      select = document.createElement("select");
      select.dataset.test = "tablet-shows";
      select.dataset.focus = `shows:${mac}`;
      // Every row has a "Shows" list, so each is named with its tablet:
      // "Kitchen tablet Shows".
      const label = el("span", "field-label", t("tablets.shows"));
      label.id = `tablet-shows-${mac}`;
      select.setAttribute("aria-labelledby", `${name.id} ${label.id}`);
      for (const [value, label, disabled] of this._showsOptions(rows, tablet)) {
        const option = el("option", null, label);
        option.value = value;
        option.disabled = disabled;
        select.append(option);
      }
      select.value = this._wantedShows(tablet);
      select.addEventListener("change", () => {
        const current = (Array.isArray(this._tablets) ? this._tablets : []).find((entry) => entry?.mac === mac);
        if (showsChangeAssigns(current || tablet)) {
          this._assign(mac, select.value);
        } else {
          // A new tablet: a change only chooses, also one made by moving
          // through the list with the keyboard. The button turns it on.
          this._choose(mac, select.value);
        }
      });
      shows.append(label, select);
    } else {
      // Nothing to pick from yet.
      shows = el("p", "tablet-shows small", t("tablets.make_first"));
      shows.dataset.test = "tablet-make-first";
    }

    const status = el("p", "tablet-status");
    status.dataset.test = "tablet-status";
    status.setAttribute("role", "status");

    const notes = el("div", "tablet-notes");
    row.append(title, shows, status, notes);
    const refs = { row, select, status, notes, notesKey: null };
    this._fillTabletRow(refs, tablet);
    return refs;
  }

  // Under a new tablet's name: what to check on the tablet before turning
  // it on (the end of its name on its screen) and a link to its device
  // page, because the name comes from the device itself and anything can
  // call itself "Porch tablet". A tablet that showed a dashboard before
  // keeps it on its screen instead of its name; a second line says so.
  _deviceLines(tablet, rows) {
    const line = el("p", "tablet-device meta");
    line.dataset.test = "tablet-device";
    line.append(document.createTextNode(deviceLine(tablet, t)));
    const path = devicePagePath(tablet);
    if (path) {
      line.append(document.createTextNode(" "));
      // "Open device page Porch tablet": every such link says which tablet.
      const link = haLink("tablet-device-page", t("tablets.device_page"), path, tablet.mac, "device");
      link.dataset.test = "tablet-device-page";
      line.append(link);
    }
    const before = deviceBeforeLine(tablet, rows, t);
    if (!before) {
      return [line];
    }
    const note = el("p", "tablet-device meta", before);
    note.dataset.test = "tablet-device-before";
    return [line, note];
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
      if (refs.select) {
        lines.push(["turn-on", t("tablets.turn_on"), "tablet-turn-on"]);
      }
      // Any device can call itself a TAB-1; the admin is the check.
      lines.push(["small", t("tablets.approve_note"), "tablet-approve-note"]);
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
    // Offline: what to check, and the way back onto a changed Wi-Fi.
    const offlineKey = offlineHelpKey(tablet);
    if (offlineKey) {
      lines.push(["small", t(offlineKey), "tablet-offline-help"]);
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
          const line = className === "alert" ? alertLine(text) : el("p", className, text);
          line.dataset.test = test;
          return line;
        }),
      );
      if (focusKey) {
        const find = (wanted) => [...refs.row.querySelectorAll("[data-focus]")].find((node) => node.dataset.focus === wanted);
        (find(focusKey) || find(`name:${tablet.mac}`))?.focus();
      }
    }
    // Turning on needs a dashboard picked first. While the change is on its
    // way the button stays as it is, so it keeps focus; a second press is
    // ignored.
    const turnOn = refs.notes.querySelector('[data-test="tablet-turn-on"]');
    if (turnOn) {
      turnOn.disabled = !this._chosen.get(tablet.mac);
    }
  }

  _turnOnButton(mac, text, test) {
    const button = makeButton(text, {
      className: "primary",
      test,
      focus: `turn-on:${mac}`,
      disabled: !this._chosen.get(mac),
      onClick: () => this._turnOn(mac),
    });
    button.classList.add("tablet-turn-on");
    // "Turn on with this dashboard Porch tablet".
    button.id = `tablet-turn-on-${mac}`;
    button.setAttribute("aria-labelledby", `${button.id} tablet-name-${mac}`);
    return button;
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

  // A dashboard picked in a new tablet's list: kept, not sent.
  _choose(mac, urlPath) {
    if (urlPath) {
      this._chosen.set(mac, urlPath);
    } else {
      this._chosen.delete(mac);
    }
    this._tabletErrors.delete(mac);
    this._updateTablets();
  }

  // The admin's explicit act that turns a new tablet on with the dashboard
  // picked for it; the only change that sends approve. A press of a
  // button that moved a moment ago is ignored: it may be the second click
  // of a double click, landing on another tablet's button. The button
  // looks disabled until then.
  _turnOn(mac) {
    const urlPath = this._chosen.get(mac);
    if (!urlPath || this._tabletBusy.has(`shows:${mac}`)) {
      return;
    }
    // One more look first: a button that moved since the last one, by a
    // change the panel was not told of, moved just now.
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
        const target =
          find(focusKey) || (focusKey.startsWith("turn-on:") ? find(`name:${focusKey.slice("turn-on:".length)}`) : null);
        target?.focus();
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
    this._noteTabletLayout();
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

  _createButton(labelKey) {
    return makeButton(this._creating ? t("home.creating") : t(labelKey), {
      className: "primary",
      test: "create",
      focus: "create",
      disabled: this._creating,
      onClick: () => this._createDashboard(),
    });
  }

  _dashboardRow(row) {
    const item = el("div", "dashboard-row");
    item.dataset.test = "dashboard-row";
    item.dataset.urlPath = row.url_path;
    const text = el("div", "row-text");
    text.append(el("h3", null, row.title));
    if (typeof row.pages === "number") {
      text.append(el("p", "meta", t("home.pages", { count: row.pages })));
    }
    const hidden = this._notShownText(this._home?.notShown?.[row.url_path]);
    if (hidden) {
      const line = el("p", "meta", hidden);
      line.dataset.test = "row-not-shown";
      text.append(line);
    }
    // "Shown on: Kitchen, Bedroom", kept up to date as the tablets change.
    const shownOn = el("p", "meta shown-on");
    shownOn.dataset.test = "row-shown-on";
    this._tabletUi?.shownOn.set(row.url_path, shownOn);
    this._fillShownOnLine(shownOn, row.url_path);
    text.append(shownOn);
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
    if (row.editable) {
      item.append(
        makeButton(t("home.edit"), {
          className: "primary",
          test: "edit",
          focus: `edit:${row.url_path}`,
          onClick: () => this._go(`/edit/${encodeURIComponent(row.url_path)}`),
        }),
      );
    } else {
      // Opens the panel's own read-only view. It stays a real link so it
      // can be opened in a new tab; a plain click moves without a reload.
      const path = `/edit/${encodeURIComponent(row.url_path)}`;
      const view = el("a", "button-link", t("home.view"));
      view.href = this._prefix() + path;
      view.dataset.test = "view";
      view.dataset.focus = `view:${row.url_path}`;
      view.addEventListener("click", (event) => {
        if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
          return;
        }
        event.preventDefault();
        this._go(path);
      });
      item.append(view);
    }
    return item;
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
    const back = makeButton(null, {
      className: "link",
      test: "back",
      focus: "back",
      onClick: () => this._go(""),
    });
    back.append(icon("mdi:arrow-left"), el("span", null, t("advanced.back")));
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
      main.append(el("p", null, t("editor.loading")));
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
    const guide = el("a", null, t("advanced.guide"));
    guide.href = CARD_GUIDE_URL;
    guide.target = "_blank";
    guide.rel = "noreferrer";
    folder.append(
      el("h2", null, t("advanced.folder_title")),
      el("p", null, t("advanced.folder_text")),
      el("p", "code-line", t("advanced.folder_path", { path: library.components_path || "" })),
      el("p", null, t("advanced.counts", { count: components.length, builtin, user: user.length })),
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
      text.append(el("h3", null, component.name), el("p", "small", component.id));
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
        className: component.approved ? null : "primary",
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

    const errors = Array.isArray(library.errors) ? library.errors : [];
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
