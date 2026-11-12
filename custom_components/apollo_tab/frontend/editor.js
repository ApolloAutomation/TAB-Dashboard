import { getConnection, loadStrings, t } from "./api.js";
import { editorStyles } from "./styles.js";

// Home Assistant shows this when someone edits a TAB-1 card in its own
// dashboard editor. TAB-1 cards are set up in the TAB-1 panel, so this only
// points there; Home Assistant's code editor stays available for the card.
export class ApolloTabCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._loading = false;
  }

  setConfig(config) {
    this._config = config && typeof config === "object" ? { ...config } : null;
  }

  set hass(value) {
    const first = !this._hass;
    this._hass = value;
    if (first) {
      this._load();
    }
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    this._load();
  }

  async _load() {
    if (!this._hass || !this.isConnected || this._loading) {
      return;
    }
    this._loading = true;
    try {
      await loadStrings(await getConnection(this._hass));
    } catch {
      // Without strings the keys are shown, which still leads to the panel.
    }
    this._loading = false;
    this._draw();
  }

  _draw() {
    const style = document.createElement("style");
    style.textContent = editorStyles;

    const box = document.createElement("div");
    box.className = "hint";
    const title = document.createElement("h2");
    title.textContent = t("hint.title");
    const text = document.createElement("p");
    text.textContent = t("hint.text");
    const link = document.createElement("a");
    link.href = "/apollo-tab";
    link.textContent = t("hint.open");
    box.append(title, text, link);

    this.shadowRoot.replaceChildren(style, box);
  }
}
