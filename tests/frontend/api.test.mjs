import test, { mock } from "node:test";
import assert from "node:assert";
import {
  onLayoutChanged,
  onLibraryChanged,
  previewLayout,
  subscribeCard,
} from "../../custom_components/apollo_tab/frontend/api.js";

const flush = async () => {
  for (let i = 0; i < 5; i += 1) {
    await Promise.resolve();
  }
};

// Each entry of script says how that subscribe call ends; the default resolves.
// "defer" leaves the subscribe pending until the test calls calls[n].resolve().
function makeConnection(script = []) {
  return {
    calls: [],
    unsubscribeCount: 0,
    libraryLoads: 0,
    sendMessagePromise(message) {
      assert.equal(message.type, "apollo_tab/library");
      this.libraryLoads += 1;
      return Promise.resolve({ components: [{ id: `load-${this.libraryLoads}` }] });
    },
    subscribeMessage(callback, message) {
      const action = script[this.calls.length] || "resolve";
      const call = { callback, message };
      this.calls.push(call);

      if (action === "reject") {
        return Promise.reject(
          Object.assign(new Error("The integration is not loaded"), {
            code: "not_loaded",
          }),
        );
      }

      const unsubscribe = () => {
        this.unsubscribeCount += 1;
      };

      if (action === "defer") {
        return new Promise((resolve) => {
          call.resolve = () => resolve(unsubscribe);
        });
      }

      return Promise.resolve(unsubscribe);
    },
  };
}

test("subscribeCard shares one subscription per card", async () => {
  const conn = makeConnection(["resolve"]);
  const card = { component: "sharing-test" };
  const firstEvents = [];
  const secondEvents = [];
  const laterEvents = [];

  subscribeCard(conn, card, null, (event) => firstEvents.push(event));
  subscribeCard(conn, card, null, (event) => secondEvents.push(event));

  assert.equal(conn.calls.length, 1);
  assert.deepEqual(conn.calls[0].message, {
    type: "apollo_tab/card/subscribe",
    card,
    dashboard: null,
  });

  const init = { type: "init", card: { title: "Shared" } };
  conn.calls[0].callback(init);

  assert.deepEqual(firstEvents, [init]);
  assert.deepEqual(secondEvents, [init]);

  subscribeCard(conn, card, null, (event) => laterEvents.push(event));

  assert.equal(conn.calls.length, 1);
  assert.deepEqual(laterEvents, [init]);
  await flush();
});

test("subscribeCard subscribes again after a failed subscribe", async () => {
  const conn = makeConnection(["reject", "resolve"]);
  const card = { component: "failed-newcomer-test" };
  const firstEvents = [];
  const secondEvents = [];

  subscribeCard(conn, card, null, (event) => firstEvents.push(event));
  await flush();

  assert.equal(conn.calls.length, 1);
  assert.equal(firstEvents.length, 1);
  assert.equal(firstEvents[0].type, "error");
  assert.equal(firstEvents[0].code, "not_loaded");

  subscribeCard(conn, card, null, (event) => secondEvents.push(event));

  assert.equal(conn.calls.length, 2);
  assert.deepEqual(secondEvents, []);

  const init = { type: "init", card: { title: "Recovered" } };
  conn.calls[1].callback(init);

  assert.deepEqual(firstEvents.at(-1), init);
  assert.deepEqual(secondEvents, [init]);
  await flush();
});

test("subscribeCard retries a failed subscribe while listeners remain", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    const conn = makeConnection(["reject", "resolve"]);
    const card = { component: "automatic-retry-test" };
    const events = [];

    subscribeCard(conn, card, null, (event) => events.push(event));
    await flush();

    assert.equal(conn.calls.length, 1);
    assert.equal(events[0].code, "not_loaded");

    mock.timers.tick(2000);
    assert.equal(conn.calls.length, 2);
    await flush();

    const init = { type: "init", card: { title: "Retried" } };
    conn.calls[1].callback(init);

    assert.deepEqual(events.at(-1), init);
  } finally {
    mock.timers.reset();
  }
});

test("subscribeCard stops retrying after the last listener leaves", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    const conn = makeConnection(["reject", "reject"]);
    const card = { component: "stopped-retry-test" };
    const stop = subscribeCard(conn, card, null, () => {});

    await flush();
    assert.equal(conn.calls.length, 1);

    stop();
    mock.timers.tick(1000);
    mock.timers.tick(60000);

    assert.equal(conn.calls.length, 1);

    const stopAgain = subscribeCard(conn, card, null, () => {});
    assert.equal(conn.calls.length, 2);

    await flush();
    stopAgain();
    mock.timers.tick(1000);
  } finally {
    mock.timers.reset();
  }
});

test("subscribeCard closes the subscription 1000 ms after the last listener leaves", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    const conn = makeConnection(["resolve"]);
    const card = { component: "delayed-close-test" };
    const stop = subscribeCard(conn, card, null, () => {});

    await flush();
    stop();

    mock.timers.tick(999);
    assert.equal(conn.unsubscribeCount, 0);

    mock.timers.tick(1);
    assert.equal(conn.unsubscribeCount, 1);
  } finally {
    mock.timers.reset();
  }
});

const notLoaded = {
  type: "error",
  code: "not_loaded",
  message: "The integration is not loaded",
};

test("subscribeCard resubscribes after a not_loaded event", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    const conn = makeConnection(["resolve", "resolve"]);
    const card = { component: "event-retry-test" };
    const events = [];

    subscribeCard(conn, card, null, (event) => events.push(event));
    await flush();

    conn.calls[0].callback({ type: "init", card: { title: "Initial" } });
    conn.calls[0].callback({ type: "values", values: { 1: "Kitchen" }, errors: {} });
    conn.calls[0].callback(notLoaded);

    assert.equal(events.at(-1).code, "not_loaded");

    mock.timers.tick(2000);
    assert.equal(conn.calls.length, 2);
    await flush();

    const init = { type: "init", card: { title: "Recovered" } };
    conn.calls[1].callback(init);

    assert.deepEqual(events.at(-1), init);
  } finally {
    mock.timers.reset();
  }
});

test("subscribeCard closes the stopped subscription after not_loaded", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    const conn = makeConnection(["resolve"]);
    const card = { component: "event-close-test" };
    const stop = subscribeCard(conn, card, null, () => {});

    await flush();
    conn.calls[0].callback(notLoaded);

    assert.equal(conn.unsubscribeCount, 1);

    stop();
    mock.timers.tick(1000);
  } finally {
    mock.timers.reset();
  }
});

test("subscribeCard gives a newcomer after not_loaded a fresh subscription", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    const conn = makeConnection(["resolve", "resolve"]);
    const card = { component: "event-newcomer-test" };
    const firstEvents = [];
    const secondEvents = [];

    subscribeCard(conn, card, null, (event) => firstEvents.push(event));
    await flush();

    conn.calls[0].callback(notLoaded);

    subscribeCard(conn, card, null, (event) => secondEvents.push(event));

    assert.equal(conn.calls.length, 2);
    assert.deepEqual(secondEvents, []);

    const init = { type: "init", card: { title: "Fresh" } };
    conn.calls[1].callback(init);

    assert.deepEqual(firstEvents.at(-1), init);
    assert.deepEqual(secondEvents, [init]);
  } finally {
    mock.timers.reset();
  }
});

test("subscribeCard keeps the subscription for other error events", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    const conn = makeConnection(["resolve"]);
    const card = { component: "nonterminal-error-test" };
    const firstEvents = [];
    const secondEvents = [];

    subscribeCard(conn, card, null, (event) => firstEvents.push(event));
    await flush();

    const error = {
      type: "error",
      code: "unknown_component",
      message: "Unknown component",
    };
    conn.calls[0].callback(error);

    assert.equal(conn.unsubscribeCount, 0);

    mock.timers.tick(60000);

    assert.equal(conn.calls.length, 1);
    assert.equal(conn.unsubscribeCount, 0);

    subscribeCard(conn, card, null, (event) => secondEvents.push(event));

    assert.equal(conn.calls.length, 1);
    assert.deepEqual(firstEvents.at(-1), error);
    assert.deepEqual(secondEvents, [error]);
  } finally {
    mock.timers.reset();
  }
});

test("subscribeCard ignores events from a replaced subscription", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    const conn = makeConnection(["resolve", "resolve"]);
    const card = { component: "stale-event-test" };
    const events = [];

    subscribeCard(conn, card, null, (event) => events.push(event));
    await flush();

    conn.calls[0].callback(notLoaded);

    mock.timers.tick(2000);
    await flush();

    assert.equal(conn.calls.length, 2);

    const eventCount = events.length;
    conn.calls[0].callback({ type: "init", card: { title: "Stale" } });

    assert.equal(events.length, eventCount);

    const init = { type: "init", card: { title: "Current" } };
    conn.calls[1].callback(init);

    assert.deepEqual(events.at(-1), init);
  } finally {
    mock.timers.reset();
  }
});

test("subscribeCard closes a subscription that resolves after not_loaded", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    const conn = makeConnection(["defer"]);
    const card = { component: "delayed-resolution-test" };

    subscribeCard(conn, card, null, () => {});
    conn.calls[0].callback(notLoaded);

    assert.equal(conn.unsubscribeCount, 0);

    conn.calls[0].resolve();
    await flush();

    assert.equal(conn.unsubscribeCount, 1);
  } finally {
    mock.timers.reset();
  }
});

// Loading the library takes more promise steps than a subscribe does.
const settle = async () => {
  for (let i = 0; i < 4; i += 1) {
    await flush();
  }
};

test("onLibraryChanged subscribes again after the integration reloads", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    // The first new subscribe lands while the integration is still loading.
    const conn = makeConnection(["resolve", "reject", "resolve"]);
    const libraries = [];
    const stop = onLibraryChanged(conn, (library) => libraries.push(library));
    await settle();

    assert.equal(conn.calls.length, 1);
    assert.deepEqual(conn.calls[0].message, { type: "apollo_tab/library/subscribe" });

    conn.calls[0].callback({ type: "changed" });
    await settle();
    assert.deepEqual(libraries, [{ components: [{ id: "load-1" }] }]);

    conn.calls[0].callback({ type: "not_loaded" });
    await settle();
    assert.equal(conn.unsubscribeCount, 1);
    assert.equal(conn.calls.length, 1);
    assert.equal(libraries.length, 1);

    mock.timers.tick(2000);
    assert.equal(conn.calls.length, 2);
    await settle();

    mock.timers.tick(3999);
    assert.equal(conn.calls.length, 2);
    mock.timers.tick(1);
    assert.equal(conn.calls.length, 3);
    await settle();

    // Elements may have changed while nothing was subscribed.
    assert.deepEqual(libraries.at(-1), { components: [{ id: "load-2" }] });
    assert.equal(libraries.length, 2);

    // Events of the ended subscription are ignored; the new one is live.
    conn.calls[0].callback({ type: "changed" });
    await settle();
    assert.equal(libraries.length, 2);
    conn.calls[2].callback({ type: "changed" });
    await settle();
    assert.equal(libraries.length, 3);

    stop();
    assert.equal(conn.unsubscribeCount, 2);
    conn.calls[2].callback({ type: "changed" });
    await settle();
    assert.equal(libraries.length, 3);
  } finally {
    mock.timers.reset();
  }
});

test("onLayoutChanged reports events and a reopened subscription", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    const conn = makeConnection();
    const events = [];
    let restored = 0;
    const stop = onLayoutChanged(
      conn,
      (event) => events.push(event),
      () => {
        restored += 1;
      },
    );
    await settle();

    assert.deepEqual(conn.calls[0].message, { type: "apollo_tab/layout/subscribe" });
    const converted = { type: "converted", url_path: "tab-1" };
    conn.calls[0].callback(converted);
    assert.deepEqual(events, [converted]);
    assert.equal(restored, 0);

    conn.calls[0].callback({ type: "not_loaded" });
    assert.deepEqual(events, [converted]);
    mock.timers.tick(2000);
    await settle();
    assert.equal(conn.calls.length, 2);
    assert.equal(restored, 1);

    stop();
    mock.timers.tick(60000);
    assert.equal(conn.calls.length, 2);
  } finally {
    mock.timers.reset();
  }
});

// Home Assistant's connection fires "ready" after it has come back and opened
// its subscriptions again; events from the time in between are lost.
function withConnectionEvents(conn) {
  conn.listeners = new Map();
  conn.addEventListener = (type, callback) => {
    conn.listeners.set(type, [...(conn.listeners.get(type) || []), callback]);
  };
  conn.removeEventListener = (type, callback) => {
    conn.listeners.set(
      type,
      (conn.listeners.get(type) || []).filter((entry) => entry !== callback),
    );
  };
  conn.fire = (type) => {
    for (const callback of conn.listeners.get(type) || []) {
      callback(conn);
    }
  };
  return conn;
}

test("onLayoutChanged asks for a reload when the connection comes back", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    const conn = withConnectionEvents(makeConnection());
    let restored = 0;
    const stop = onLayoutChanged(
      conn,
      () => {},
      () => {
        restored += 1;
      },
    );
    await settle();
    assert.equal(restored, 0);

    conn.fire("ready");
    assert.equal(restored, 1);

    // While the subscription is opened again after not_loaded, the reopened
    // subscription asks once, not the connection as well.
    conn.calls[0].callback({ type: "not_loaded" });
    conn.fire("ready");
    assert.equal(restored, 1);
    mock.timers.tick(2000);
    await settle();
    assert.equal(restored, 2);

    stop();
    assert.deepEqual(conn.listeners.get("ready"), []);
    conn.fire("ready");
    assert.equal(restored, 2);
  } finally {
    mock.timers.reset();
  }
});

test("onLibraryChanged does not watch the connection", async () => {
  const conn = withConnectionEvents(makeConnection());
  const stop = onLibraryChanged(conn, () => {});
  await settle();
  assert.equal((conn.listeners.get("ready") || []).length, 0);
  stop();
});

test("a refused subscription is not tried again", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });

  try {
    const conn = makeConnection();
    conn.subscribeMessage = function subscribeMessage(callback, message) {
      this.calls.push({ callback, message });
      return Promise.reject(Object.assign(new Error("Unauthorized"), { code: "unauthorized" }));
    };
    onLibraryChanged(conn, () => {});
    await settle();
    mock.timers.tick(60000);
    await settle();
    assert.equal(conn.calls.length, 1);
  } finally {
    mock.timers.reset();
  }
});

test("previewLayout sends the config and returns the answer", async () => {
  const config = { apollo_tab: { version: 1 }, views: [] };
  const answer = { layout: { pages: [] }, warnings: [], values: {}, sources: {} };
  const sent = [];
  const conn = {
    sendMessagePromise(message) {
      sent.push(message);
      return Promise.resolve(answer);
    },
  };

  assert.equal(await previewLayout(conn, config), answer);
  assert.deepEqual(sent, [{ type: "apollo_tab/layout/preview", config }]);
});
