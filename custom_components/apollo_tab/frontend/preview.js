import { getConnection, loadStrings, onLayoutChanged, t } from "./api.js";
import {
  dashboardFromPath,
  warningBoxKind,
  warningPlace,
  warningText,
} from "./logic.js";
import { renderPage } from "./render.js";
import { previewStyles, rendererStyles } from "./styles.js";

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

function positionWarningBox(box, rectangle, scale) {
  box.style.left = `${Number(rectangle[0] * scale)}px`;
  box.style.top = `${Number(rectangle[1] * scale)}px`;
  box.style.width = `${Number(rectangle[2] * scale)}px`;
  box.style.height = `${Number(rectangle[3] * scale)}px`;
}

export class ApolloTabPreview extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    // Rendered pages live in this shadow root, so their CSS must be here too.
    // One style element, because a redraw keeps only the first one.
    addStyle(this.shadowRoot, rendererStyles + previewStyles);
    this._hass = null;
    this._dashboard = null;
    this._config = {};
    this._data = null;
    this._page = 0;
    this._conn = null;
    this._stop = null;
    this._timer = null;
    this._resizeObserver = null;
    this._startRun = 0;
    this._started = false;
  }

  setConfig(config) {
    this._config = config || {};
    this.dashboard =
      this._config.dashboard || dashboardFromPath(location.pathname);
  }

  set hass(value) {
    this._hass = value;
    if (this.isConnected) {
      this._start();
    }
  }

  get hass() {
    return this._hass;
  }

  set dashboard(value) {
    if (this._dashboard === value) {
      return;
    }
    this._dashboard = value;
    if (this.isConnected) {
      this._load();
    }
  }

  get dashboard() {
    return this._dashboard;
  }

  connectedCallback() {
    if (!this._dashboard) {
      this._dashboard =
        this._config.dashboard || dashboardFromPath(location.pathname);
    }

    // Drawing inside the callback resizes observed content, so wait a frame.
    this._resizeObserver = new ResizeObserver(() => {
      cancelAnimationFrame(this._resizeFrame);
      this._resizeFrame = requestAnimationFrame(() => this._drawPage());
    });
    this._resizeObserver.observe(this);
    this._start();
  }

  disconnectedCallback() {
    // Stop the page's image refresh timers along with everything else.
    this.shadowRoot.querySelector(".page-host")?.__atCleanup?.();
    cancelAnimationFrame(this._resizeFrame);
    this._started = false;
    this._startRun += 1;
    this._stop?.();
    this._stop = null;
    clearInterval(this._timer);
    this._timer = null;
    this._resizeObserver?.disconnect();
  }

  getGridOptions() {
    return { columns: "full", rows: "auto" };
  }

  getCardSize() {
    return 8;
  }

  async _start() {
    if (!this._hass || this._started) {
      return;
    }
    this._started = true;
    const run = ++this._startRun;

    this._conn = await getConnection(this._hass);
    await loadStrings(this._conn);
    await this._load();

    // The element can leave the page while the calls above are in flight.
    if (run !== this._startRun) {
      return;
    }

    this._stop = onLayoutChanged(
      this._conn,
      (event) => {
        if (
          event.url_path === this._dashboard &&
          (event.type === "converted" || event.type === "removed")
        ) {
          this._load();
        }
      },
      () => this._load(),
    );

    this._timer = setInterval(() => {
      if (document.visibilityState === "visible") {
        this._load();
      }
    }, 30000);
  }

  async _load() {
    if (!this._hass || !this._dashboard) {
      return;
    }

    try {
      this._data = await this._hass.callWS({
        type: "apollo_tab/layout/get",
        url_path: this._dashboard,
      });
      this._page = Math.min(
        this._page,
        Math.max(0, (this._data.layout?.pages?.length || 1) - 1),
      );
      this._draw();
    } catch (error) {
      this._data = {
        error:
          error?.code === "not_found"
            ? "not_found"
            : "unauthorized",
      };
      this._draw();
    }
  }

  _draw() {
    // The old page is thrown away below; its image timers must not outlive it.
    this.shadowRoot.querySelector(".page-host")?.__atCleanup?.();
    const keepStyle = this.shadowRoot.querySelector("style");
    this.shadowRoot.replaceChildren(keepStyle);

    if (this._data?.error === "unauthorized") {
      this.shadowRoot.append(node("p", "preview-message", t("preview.admin_only")));
      return;
    }
    if (this._data?.error === "not_found") {
      this.shadowRoot.append(node("p", "preview-message", t("preview.not_tab")));
      return;
    }

    const pages = this._data?.layout?.pages || [];
    if (!pages.length) {
      this.shadowRoot.append(node("p", "preview-message", t("preview.no_pages")));
      return;
    }

    this.shadowRoot.append(node("p", "notice", t("preview.not_sent")));

    const heading = node("div", "preview-heading");
    heading.append(
      node("h3", null, t("preview.title")),
      node(
        "span",
        null,
        t("preview.page", { n: this._page + 1, count: pages.length }),
      ),
    );
    this.shadowRoot.append(heading);

    const tabs = node("div", "page-tabs");
    pages.forEach((page, index) => {
      const button = node("button", null, page.title);
      button.type = "button";
      button.setAttribute("aria-pressed", String(index === this._page));
      button.addEventListener("click", () => {
        this._page = index;
        this._draw();
      });
      tabs.append(button);
    });
    this.shadowRoot.append(tabs);

    const stage = node("div", "preview-stage");
    const pageHost = node("div", "page-host");
    stage.append(pageHost);
    this.shadowRoot.append(stage);

    this._drawPage();

    const warnings = (this._data.warnings || []).filter((warning) => {
      const page = pages[this._page];
      return warning.page == null || warning.page === page.id;
    });

    this.shadowRoot.append(node("h4", null, t("preview.warnings")));
    if (!warnings.length) {
      this.shadowRoot.append(node("p", null, t("preview.no_warnings")));
    } else {
      const list = document.createElement("ul");
      for (const warning of warnings) {
        const item = document.createElement("li");
        const place = warningPlace(warning);
        const text = warningText(warning, this._strings());
        item.textContent = place ? `${text} — ${place}` : text;
        list.append(item);
      }
      this.shadowRoot.append(list);
    }
  }

  _strings() {
    const result = {};
    for (const warning of this._data?.warnings || []) {
      const key = `warn.${warning.code}`;
      result[key] = t(key, { detail: warning.detail || "" });
    }
    return result;
  }

  _drawPage() {
    const host = this.shadowRoot.querySelector(".page-host");
    if (!host || !this._data?.layout) {
      return;
    }

    // renderPage fixes the host's width, so measure the stage that holds it.
    const width = host.parentElement.getBoundingClientRect().width;
    if (!width) {
      return;
    }

    const scale = width / 1280;
    renderPage(
      host,
      this._data.layout,
      this._page,
      {
        values: this._data.values || {},
        errors: {},
      },
      {
        sx: scale,
        sy: scale,
        interactive: false,
      },
    );

    const page = this._data.layout.pages[this._page];
    for (const warning of this._data.warnings || []) {
      if (warning.page !== page.id) {
        continue;
      }

      const kind = warningBoxKind(warning);
      if (!kind) {
        continue;
      }

      const box =
        kind === "omitted"
          ? node("div", "warning-box", t("preview.omitted"))
          : node("div", "warning-box flat");
      if (kind === "flat") {
        box.title = warningText(warning, this._strings());
      }
      positionWarningBox(box, warning.r, scale);
      // Inside the page, so the warning mark uses the dashboard's theme.
      host.querySelector(".at-page").append(box);
    }
  }
}
