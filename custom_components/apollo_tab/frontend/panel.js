import {
  getConnection,
  loadLibrary,
  loadStrings,
  onLayoutChanged,
  onLibraryChanged,
  t,
} from "./api.js";
import { defineAliases } from "./card.js";
import {
  isIcon,
  nextDashboardPath,
  starterConfig,
} from "./logic.js";
import { panelStyles } from "./styles.js";

function addStyle(root, css) {
  const style = document.createElement("style");
  style.textContent = css;
  root.append(style);
}

function node(tag, className, text) {
  const result = document.createElement(tag);
  if (className) {
    result.className = className;
  }
  if (text !== undefined) {
    result.textContent = text;
  }
  return result;
}

export class ApolloTabPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    addStyle(this.shadowRoot, panelStyles);
    this._hass = null;
    this._narrow = false;
    this._route = null;
    this._panel = null;
    this._library = null;
    this._dashboards = null;
    this._conn = null;
    this._stops = [];
    this._creating = false;
    this._message = "";
  }

  set hass(value) {
    const first = !this._hass;
    this._hass = value;
    if (first) {
      if (this.isConnected) {
        this._load();
      }
      this._draw();
      return;
    }
    // hass is set on every state change, and redrawing here would rebuild the
    // previews and close any open select.
    for (const child of this.shadowRoot.querySelectorAll("apollo-tab-preview, ha-menu-button")) {
      child.hass = value;
    }
  }

  get hass() {
    return this._hass;
  }

  set narrow(value) {
    if (this._narrow === value) {
      return;
    }
    this._narrow = value;
    this._draw();
  }

  get narrow() {
    return this._narrow;
  }

  set route(value) {
    this._route = value;
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
    this._load();
  }

  disconnectedCallback() {
    this._stops.forEach((stop) => stop?.());
    this._stops = [];
  }

  async _load() {
    if (!this._hass) {
      return;
    }

    this._conn = await getConnection(this._hass);
    await loadStrings(this._conn);
    await this._refresh();

    // The panel can leave the page while the calls above are in flight.
    if (!this.isConnected || this._stops.length) {
      return;
    }

    this._stops.push(
      onLibraryChanged(this._conn, (library) => {
        this._setLibrary(library);
        this._draw();
      }),
      onLayoutChanged(
        this._conn,
        () => this._refresh(),
        () => this._refresh(),
      ),
    );
  }

  // The card picker lists one entry per element, so it follows the library.
  _setLibrary(library) {
    this._library = library;
    if (library) {
      defineAliases(library);
    }
  }

  async _refresh() {
    const [library, dashboards] = await Promise.all([
      loadLibrary(this._conn, { force: true }),
      this._hass.callWS({ type: "apollo_tab/dashboards" }).catch(() => null),
    ]);
    this._setLibrary(library);
    this._dashboards = dashboards;
    this._draw();
  }

  _draw() {
    if (!this._hass || !this._library || !this._dashboards) {
      return;
    }

    const keepStyle = this.shadowRoot.querySelector("style");
    this.shadowRoot.replaceChildren(keepStyle);

    const header = node("header", "panel-header");
    if (this._narrow) {
      const menu = document.createElement("ha-menu-button");
      menu.hass = this._hass;
      menu.narrow = this._narrow;
      header.append(menu);
    }
    const headerText = node("div");
    headerText.append(
      node("h1", null, t("panel.title")),
      node("p", null, t("panel.intro")),
    );
    header.append(headerText);
    this.shadowRoot.append(header);

    const content = node("main", "panel-content");
    const notice = node("section", "notice");
    notice.append(node("p", null, t("panel.not_sent")));
    notice.append(
      node(
        "p",
        null,
        this._dashboards.tablets
          ? t("panel.tablets_some", { count: this._dashboards.tablets })
          : t("panel.tablets_none"),
      ),
    );
    content.append(notice);

    const create = node(
      "button",
      "primary",
      this._creating ? t("panel.creating") : t("panel.create"),
    );
    create.type = "button";
    create.disabled = this._creating;
    create.addEventListener("click", () => this._createDashboard());
    content.append(create);

    if (this._message) {
      content.append(node("p", "status-message", this._message));
    }

    content.append(this._dashboardSection());
    content.append(this._elementsSection());
    this.shadowRoot.append(content);
  }

  async _createDashboard() {
    this._creating = true;
    this._message = "";
    this._draw();

    try {
      const list = await this._hass.callWS({ type: "lovelace/dashboards/list" });
      const paths = [
        ...(list || []).map((entry) => entry.url_path),
        ...Object.keys(this._hass.panels || {}),
      ];
      const urlPath = nextDashboardPath(paths);

      await this._hass.callWS({
        type: "lovelace/dashboards/create",
        url_path: urlPath,
        title: "TAB-1",
        icon: "mdi:tablet-dashboard",
        mode: "storage",
        require_admin: false,
        show_in_sidebar: true,
      });

      await this._hass.callWS({
        type: "lovelace/config/save",
        url_path: urlPath,
        config: starterConfig(),
      });

      this._creating = false;
      this._draw();
      history.pushState(null, "", `/${urlPath}/home?edit=1`);
      window.dispatchEvent(new CustomEvent("location-changed"));
    } catch (error) {
      this._message = t("panel.create_failed", {
        message: error?.message || error?.code || "",
      });
      this._creating = false;
      this._draw();
    }
  }

  _dashboardSection() {
    const section = node("section", "section-card");
    section.append(node("h2", null, t("panel.dashboards")));

    const dashboards = this._dashboards.dashboards || [];
    if (!dashboards.length) {
      section.append(node("p", null, t("panel.none")));
      return section;
    }

    for (const dashboard of dashboards) {
      const block = node("article", "dashboard-block");
      block.append(node("h3", null, dashboard.title));

      const meta = node("p", "meta");
      meta.textContent = `${t("panel.pages", { count: dashboard.pages })} · ${t(
        "panel.warnings",
        { count: dashboard.warnings },
      )}`;
      block.append(meta);

      const edit = node("a", "button-link", t("panel.edit"));
      edit.href = `/${dashboard.url_path}?edit=1`;
      block.append(edit);

      if (dashboard.mode === "storage") {
        const label = node("label", "select-field");
        label.append(node("span", null, t("panel.theme")));
        const select = document.createElement("select");
        for (const theme of this._library.themes || []) {
          const option = document.createElement("option");
          option.value = theme.id;
          option.textContent = theme.name;
          select.append(option);
        }
        select.value = dashboard.theme;
        select.addEventListener("change", () =>
          this._changeTheme(dashboard.url_path, select.value),
        );
        label.append(select);
        block.append(label);
      } else {
        block.append(node("p", "notice", t("panel.yaml_note")));
      }

      const preview = document.createElement("apollo-tab-preview");
      preview.hass = this._hass;
      preview.dashboard = dashboard.url_path;
      block.append(preview);
      section.append(block);
    }

    return section;
  }

  async _changeTheme(urlPath, theme) {
    const config = await this._hass.callWS({
      type: "lovelace/config",
      url_path: urlPath,
      force: false,
    });
    config.apollo_tab = {
      ...(config.apollo_tab || {}),
      version: 1,
      theme,
    };
    await this._hass.callWS({
      type: "lovelace/config/save",
      url_path: urlPath,
      config,
    });
    await this._refresh();
  }

  _elementsSection() {
    const section = node("section", "section-card");
    const components = this._library.components || [];

    section.append(
      node("h2", null, t("panel.elements")),
      node("p", null, t("panel.elements_count", { count: components.length })),
      node("p", "meta", t("panel.folder_hint")),
    );

    const reload = node("button", null, t("panel.reload"));
    reload.type = "button";
    reload.addEventListener("click", async () => {
      await this._hass.callWS({ type: "apollo_tab/library/reload" });
      this._setLibrary(await loadLibrary(this._conn, { force: true }));
      this._message = t("panel.reloaded");
      this._draw();
    });
    section.append(reload);

    const list = node("div", "component-list");
    for (const component of components) {
      const item = node("article", "component-row");
      if (isIcon(component.icon)) {
        const icon = document.createElement("ha-icon");
        icon.icon = component.icon;
        item.append(icon);
      }

      const details = node("div", "component-details");
      details.append(
        node("strong", null, component.name),
        node("code", null, component.id),
        node(
          "span",
          "meta",
          component.source === "builtin"
            ? t("panel.source_builtin")
            : t("panel.source_user"),
        ),
      );
      item.append(details);

      if (component.source === "user" && component.sensitive) {
        const controls = node("div", "sensitive-controls");
        controls.append(node("span", null, t("panel.sensitive")));
        const button = node(
          "button",
          null,
          component.approved ? t("panel.revoke") : t("panel.allow"),
        );
        button.type = "button";
        button.addEventListener("click", async () => {
          await this._hass.callWS({
            type: "apollo_tab/library/approve",
            component_id: component.id,
            approved: !component.approved,
          });
          this._setLibrary(await loadLibrary(this._conn, { force: true }));
          this._draw();
        });
        controls.append(button);
        item.append(controls);
      }

      list.append(item);
    }
    section.append(list);

    if (this._library.errors?.length) {
      section.append(node("h3", null, t("panel.errors")));
      const errors = node("ul", "error-list");
      this._library.errors.forEach((error) => {
        const item = document.createElement("li");
        item.textContent = `${error.file} #${Number(error.index) + 1}: ${error.message}`;
        errors.append(item);
      });
      section.append(errors);
    }

    return section;
  }
}
