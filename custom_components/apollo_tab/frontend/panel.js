import {
  getConnection,
  loadLibrary,
  loadStrings,
  onLayoutChanged,
  onLibraryChanged,
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

const DEFAULT_PREFIX = "/apollo-tab";
const URL_PATH_RE = /^[a-z0-9_-]+$/;
const GUIDE_URL = "https://github.com/ApolloAutomation/TAB-Dashboard";
// The guide to writing a card, inside the repository.
const CARD_GUIDE_URL = `${GUIDE_URL}/blob/main/docs/components.md`;

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
        tablets: Number(tab?.tablets) || 0,
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

  // "1 card and 1 page are not shown on the tablet.", or "" when everything
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

    const notice = el("section", "box notice");
    notice.append(
      el("p", null, t("home.not_sent")),
      el(
        "p",
        null,
        this._home.tablets > 0 ? t("home.tablets_some", { count: this._home.tablets }) : t("home.tablets_none"),
      ),
    );
    main.append(notice);

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
