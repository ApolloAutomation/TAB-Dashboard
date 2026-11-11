import { getConnection, loadLibrary, loadStrings, onLibraryChanged } from "./api.js";
import { ApolloTabCard, defineAliases } from "./card.js";
import { ApolloTabCardEditor } from "./editor.js";
import { ApolloTabPanel } from "./panel.js";
import { ApolloTabPreview } from "./preview.js";
import "./confirm.js";
import "./logic.js";
import "./render.js";
import "./styles.js";

customElements.get("apollo-tab-card") || customElements.define("apollo-tab-card", ApolloTabCard);
customElements.get("apollo-tab-card-editor") || customElements.define("apollo-tab-card-editor", ApolloTabCardEditor);
customElements.get("apollo-tab-preview") || customElements.define("apollo-tab-preview", ApolloTabPreview);
customElements.get("apollo-tab-panel") || customElements.define("apollo-tab-panel", ApolloTabPanel);

window.customCards = window.customCards || [];

if (!window.customCards.some((entry) => entry.type === "apollo-tab-preview")) {
  window.customCards.push({
    type: "apollo-tab-preview",
    name: "TAB-1 tablet preview",
    description: "Shows each page the way a TAB-1 would draw it.",
    preview: false,
  });
}

async function start() {
  const conn = await getConnection();
  await loadStrings(conn);

  const library = await loadLibrary(conn, { force: false });
  if (library) {
    defineAliases(library);
  }

  onLibraryChanged(conn, (nextLibrary) => {
    if (nextLibrary) {
      defineAliases(nextLibrary);
    }
  });
}

start().catch(() => {});
