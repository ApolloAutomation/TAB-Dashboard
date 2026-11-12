import { getConnection, loadLibrary, loadStrings, onLibraryChanged } from "./api.js";
import { ApolloTabCard, defineAliases } from "./card.js";
import { ApolloTabDesigner } from "./designer.js";
import { ApolloTabCardEditor } from "./editor.js";
import { ApolloTabPanel } from "./panel.js";
import { ApolloTabPreview } from "./preview.js";
import "./confirm.js";
import "./logic.js";
import "./model.js";
import "./render.js";
import "./styles.js";

customElements.get("apollo-tab-card") || customElements.define("apollo-tab-card", ApolloTabCard);
customElements.get("apollo-tab-card-editor") || customElements.define("apollo-tab-card-editor", ApolloTabCardEditor);
customElements.get("apollo-tab-preview") || customElements.define("apollo-tab-preview", ApolloTabPreview);
customElements.get("apollo-tab-designer") || customElements.define("apollo-tab-designer", ApolloTabDesigner);
customElements.get("apollo-tab-panel") || customElements.define("apollo-tab-panel", ApolloTabPanel);

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
