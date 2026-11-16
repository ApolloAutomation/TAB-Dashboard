// The browser card's own actions, without a browser: card.js needs only a
// stand-in HTMLElement to load.
import test from "node:test";
import assert from "node:assert";

globalThis.HTMLElement = class {};
const { ApolloTabCard } = await import("../../custom_components/apollo_tab/frontend/card.js");

test("a local back closes the detail dialog, and does nothing on the card itself", () => {
  const before = globalThis.history;
  let wentBack = 0;
  globalThis.history = { back: () => wentBack++ };
  try {
    const localAction = ApolloTabCard.prototype._localAction;
    let closed = 0;
    localAction.call({ _closeDialog: () => closed++ }, { local: "back" });
    assert.equal(closed, 1);
    localAction.call({}, { local: "back" });
    assert.equal(wentBack, 0);
  } finally {
    globalThis.history = before;
  }
});

test("the card's name: its own, else its device's, else the card's", () => {
  const name = (self) => ApolloTabCard.prototype._cardName.call(self);
  const compiled = { name: "Light", entities: ["light.lamp"] };
  const hass = { states: { "light.lamp": { attributes: { friendly_name: "Lamp" } } } };
  assert.equal(name({ _config: { name: "Desk" }, _compiled: compiled, _hass: hass }), "Desk");
  assert.equal(name({ _config: {}, _compiled: compiled, _hass: hass }), "Lamp");
  assert.equal(name({ _config: {}, _compiled: compiled, _hass: { states: {} } }), "Light");
  assert.equal(name({}), "");
});
