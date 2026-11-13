import test, { mock } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as api from "../../custom_components/apollo_tab/frontend/api.js";

const { assignTablet, listTablets, onTabletsChanged, pairTablet } = api;

const flush = async () => {
  for (let i = 0; i < 5; i += 1) {
    await Promise.resolve();
  }
};

// A stand-in connection. Each entry of script says how that subscribe call
// ends: "resolve" (the default), "not_loaded" or "unauthorized". answers
// maps a command type to what sendMessagePromise resolves to (or a function
// of the message; a thrown error rejects).
function makeConnection({ script = [], answers = {} } = {}) {
  return {
    subscribes: [],
    sent: [],
    stopped: 0,
    subscribeMessage(callback, message) {
      const action = script[this.subscribes.length] || "resolve";
      this.subscribes.push({ callback, message });
      if (action === "not_loaded" || action === "unauthorized") {
        return Promise.reject(Object.assign(new Error(action), { code: action }));
      }
      return Promise.resolve(() => {
        this.stopped += 1;
      });
    },
    sendMessagePromise(message) {
      this.sent.push(message);
      const answer = answers[message.type];
      try {
        return Promise.resolve(typeof answer === "function" ? answer(message) : answer);
      } catch (error) {
        return Promise.reject(error);
      }
    },
  };
}

const KITCHEN = { mac: "aa:01", name: "Kitchen tablet", dashboard: "home", status: "on_tablet" };
const HALLWAY = { mac: "aa:02", name: "Hallway tablet", dashboard: "night", status: "offline" };

test("the tablet list is one subscription shared by every listener", async () => {
  const conn = makeConnection();
  const first = [];
  const second = [];
  const stopFirst = onTabletsChanged(conn, (tablets) => first.push(tablets));
  const stopSecond = onTabletsChanged(conn, (tablets) => second.push(tablets));
  assert.equal(conn.subscribes.length, 1);
  assert.deepEqual(conn.subscribes[0].message, { type: "apollo_tab/tablets/subscribe" });
  await flush();

  conn.subscribes[0].callback({ type: "tablets", tablets: [KITCHEN, HALLWAY, null, { name: "no mac" }] });
  assert.deepEqual(first, [[KITCHEN, HALLWAY]]);
  assert.deepEqual(second, [[KITCHEN, HALLWAY]]);
  // Other events are not lists of tablets.
  conn.subscribes[0].callback({ type: "something_else" });
  assert.equal(first.length, 1);

  // A newcomer gets the last list at once, with no new subscription.
  const later = [];
  const stopLater = onTabletsChanged(conn, (tablets) => later.push(tablets));
  assert.deepEqual(later, [[KITCHEN, HALLWAY]]);
  assert.equal(conn.subscribes.length, 1);
  stopFirst();
  stopSecond();
  stopLater();
});

test("the subscription closes a second after the last listener leaves", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const conn = makeConnection();
    const stop = onTabletsChanged(conn, () => {});
    await flush();
    stop();
    stop();
    // Going from Home to the editor: the next listener comes at once.
    const again = onTabletsChanged(conn, () => {});
    mock.timers.tick(1500);
    assert.equal(conn.stopped, 0);
    assert.equal(conn.subscribes.length, 1);
    again();
    mock.timers.tick(999);
    assert.equal(conn.stopped, 0);
    mock.timers.tick(1);
    assert.equal(conn.stopped, 1);
    // The next listener opens a new one.
    const fresh = onTabletsChanged(conn, () => {});
    assert.equal(conn.subscribes.length, 2);
    fresh();
    mock.timers.tick(1000);
  } finally {
    mock.timers.reset();
  }
});

test("the subscription opens again after the integration was reloaded", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const conn = makeConnection({ script: ["resolve", "not_loaded", "resolve"] });
    const lists = [];
    const stop = onTabletsChanged(conn, (tablets) => lists.push(tablets));
    await flush();
    conn.subscribes[0].callback({ type: "tablets", tablets: [KITCHEN] });
    conn.subscribes[0].callback({ type: "not_loaded" });
    assert.equal(conn.stopped, 1);
    mock.timers.tick(2000);
    assert.equal(conn.subscribes.length, 2);
    await flush();
    mock.timers.tick(4000);
    assert.equal(conn.subscribes.length, 3);
    await flush();
    conn.subscribes[2].callback({ type: "tablets", tablets: [KITCHEN, HALLWAY] });
    assert.deepEqual(lists, [[KITCHEN], [KITCHEN, HALLWAY]]);
    stop();
    mock.timers.tick(1000);
  } finally {
    mock.timers.reset();
  }
});

test("a final failure is reported, and the next listener tries again", async () => {
  const conn = makeConnection({ script: ["unauthorized", "resolve"] });
  const errors = [];
  const stop = onTabletsChanged(conn, () => {}, { onError: (error) => errors.push(error.code) });
  await flush();
  assert.deepEqual(errors, ["unauthorized"]);
  const lists = [];
  const stopNext = onTabletsChanged(conn, (tablets) => lists.push(tablets));
  assert.equal(conn.subscribes.length, 2);
  await flush();
  conn.subscribes[1].callback({ type: "tablets", tablets: [] });
  assert.deepEqual(lists, [[]]);
  stop();
  stopNext();
});

test("assigning a dashboard sends the address and shows the answer at once", async () => {
  const changed = { ...HALLWAY, dashboard: "home", status: "sending" };
  const conn = makeConnection({ answers: { "apollo_tab/tablet/assign": { tablet: changed } } });
  const lists = [];
  const stop = onTabletsChanged(conn, (tablets) => lists.push(tablets));
  await flush();
  conn.subscribes[0].callback({ type: "tablets", tablets: [KITCHEN, HALLWAY] });

  const result = await assignTablet(conn, "aa:02", "home");
  assert.deepEqual(conn.sent, [{ type: "apollo_tab/tablet/assign", mac: "aa:02", url_path: "home" }]);
  assert.deepEqual(result, changed);
  assert.deepEqual(lists.at(-1), [KITCHEN, changed]);
  stop();
});

// Only "Turn on with this dashboard" may turn a new tablet on: it alone
// sends approve, and only as true. Every other assign leaves it out.
test("assign sends approve only when asked, and only as true", async () => {
  const conn = makeConnection({ answers: { "apollo_tab/tablet/assign": { tablet: KITCHEN } } });
  await assignTablet(conn, "aa:01", "home", { approve: true });
  await assignTablet(conn, "aa:01", "home", { approve: false });
  await assignTablet(conn, "aa:01", "home", {});
  assert.deepEqual(conn.sent, [
    { type: "apollo_tab/tablet/assign", mac: "aa:01", url_path: "home", approve: true },
    { type: "apollo_tab/tablet/assign", mac: "aa:01", url_path: "home" },
    { type: "apollo_tab/tablet/assign", mac: "aa:01", url_path: "home" },
  ]);
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
  const frontend = path.join(root, "custom_components/apollo_tab/frontend");
  // In the panel, only _turnOn passes approve; the editor never does.
  const panel = fs.readFileSync(path.join(frontend, "panel.js"), "utf8");
  assert.equal(panel.match(/approve: true/g)?.length, 1);
  assert.match(panel, /this\._assign\(mac, urlPath, \{ approve: true \}\);/);
  const designer = fs.readFileSync(path.join(frontend, "designer.js"), "utf8");
  assert.doesNotMatch(designer, /approve:/);
});

test("setting a tablet up again sends its address and shows the answer at once", async () => {
  const answered = { ...KITCHEN, paired: false, input: "not_paired", status: "sending" };
  const conn = makeConnection({ answers: { "apollo_tab/tablet/pair": { tablet: answered } } });
  const lists = [];
  const stop = onTabletsChanged(conn, (tablets) => lists.push(tablets));
  await flush();
  conn.subscribes[0].callback({ type: "tablets", tablets: [KITCHEN, HALLWAY] });

  assert.deepEqual(await pairTablet(conn, "aa:01"), answered);
  assert.deepEqual(conn.sent, [{ type: "apollo_tab/tablet/pair", mac: "aa:01" }]);
  assert.deepEqual(lists.at(-1), [answered, HALLWAY]);

  const refused = makeConnection({
    answers: {
      "apollo_tab/tablet/pair": () => {
        throw Object.assign(new Error("This tablet is new"), { code: "not_approved" });
      },
    },
  });
  await assert.rejects(pairTablet(refused, "aa:01"), { code: "not_approved" });
  stop();
});

// Product owner, 2026-11-12: locks, alarms and garage doors keep their
// usual rules on a tablet, with no switch per tablet. The only change the
// panel makes to a tablet is which dashboard it shows; it can also ask Home
// Assistant to set a tablet up for taps again.
test("the panel has no per-tablet switch to send", () => {
  assert.equal(Object.hasOwn(api, "updateTablet"), false);
  const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../custom_components/apollo_tab/frontend");
  for (const name of fs.readdirSync(frontend).filter((file) => file.endsWith(".js"))) {
    const source = fs.readFileSync(path.join(frontend, name), "utf8");
    assert.ok(!source.includes("apollo_tab/tablet/update"), `${name} sends a tablet setting`);
  }
});

test("a failed change rejects and leaves the list as it was", async () => {
  const conn = makeConnection({
    answers: {
      "apollo_tab/tablet/assign": () => {
        throw Object.assign(new Error("This dashboard does not exist"), { code: "unknown_dashboard" });
      },
    },
  });
  const lists = [];
  const stop = onTabletsChanged(conn, (tablets) => lists.push(tablets));
  await flush();
  conn.subscribes[0].callback({ type: "tablets", tablets: [KITCHEN] });
  await assert.rejects(assignTablet(conn, "aa:01", "gone"), { code: "unknown_dashboard" });
  assert.deepEqual(lists, [[KITCHEN]]);
  stop();
});

test("listTablets reads the list once", async () => {
  const conn = makeConnection({ answers: { "apollo_tab/tablets": { tablets: [KITCHEN, 3] } } });
  assert.deepEqual(await listTablets(conn), [KITCHEN]);
  assert.deepEqual(conn.sent, [{ type: "apollo_tab/tablets" }]);
  const empty = makeConnection({ answers: { "apollo_tab/tablets": null } });
  assert.deepEqual(await listTablets(empty), []);
});
