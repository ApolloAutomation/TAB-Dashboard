import test, { mock } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as api from "../../custom_components/apollo_tab/frontend/api.js";

const { assignTablet, listTablets, onTabletsChanged, pairTablet } = api;

const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../custom_components/apollo_tab/frontend");

const flush = async () => {
  for (let i = 0; i < 5; i += 1) {
    await Promise.resolve();
  }
};

// A stand-in connection. Each entry of script says how that subscribe call
// ends: "resolve" (the default), "not_loaded", "unknown_command",
// "unauthorized" or "lost" (the connection was lost while it was under
// way). answers maps a command type to what sendMessagePromise resolves to
// (or a function of the message; a thrown error rejects).
function makeConnection({ script = [], answers = {} } = {}) {
  return {
    subscribes: [],
    sent: [],
    stopped: 0,
    subscribeMessage(callback, message, options) {
      const action = script[this.subscribes.length] || "resolve";
      this.subscribes.push({ callback, message, options });
      if (action === "lost") {
        // Home Assistant's connection answers with an error result, code 3.
        return Promise.reject({ type: "result", success: false, error: { code: 3, message: "Connection lost" } });
      }
      if (action !== "resolve") {
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

// Home Assistant's connection fires "ready" when it is back after a loss.
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
  // A connection without events keeps opening its subscriptions again itself.
  assert.equal(conn.subscribes[0].options, undefined);
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

// After a restart of Home Assistant the connection is back before the
// integration is loaded. The connection's own new subscribe would fail then
// and tell nobody, so the subscription is opened again here.
test("the tablet list is subscribed again when the connection comes back", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const conn = withConnectionEvents(makeConnection({ script: ["resolve", "not_loaded", "resolve"] }));
    const lists = [];
    const errors = [];
    const stop = onTabletsChanged(conn, (tablets) => lists.push(tablets), {
      onError: (error) => errors.push(error.code),
    });
    await flush();
    conn.subscribes[0].callback({ type: "tablets", tablets: [KITCHEN] });
    assert.deepEqual(conn.subscribes[0].options, { resubscribe: false });

    conn.fire("ready");
    assert.equal(conn.subscribes.length, 2);
    assert.deepEqual(conn.subscribes[1].options, { resubscribe: false });
    await flush();
    // The first subscription went with the old connection: it is not closed.
    assert.equal(conn.stopped, 0);
    assert.deepEqual(errors, []);

    mock.timers.tick(2000);
    assert.equal(conn.subscribes.length, 3);
    await flush();
    conn.subscribes[0].callback({ type: "tablets", tablets: [] });
    assert.deepEqual(lists, [[KITCHEN]]);
    conn.subscribes[2].callback({ type: "tablets", tablets: [KITCHEN, HALLWAY] });
    assert.deepEqual(lists, [[KITCHEN], [KITCHEN, HALLWAY]]);
    assert.deepEqual(errors, []);

    stop();
    mock.timers.tick(1000);
    assert.equal(conn.stopped, 1);
    assert.deepEqual(conn.listeners.get("ready"), []);
    conn.fire("ready");
    assert.equal(conn.subscribes.length, 3);
  } finally {
    mock.timers.reset();
  }
});

// While Home Assistant starts, the integration's commands are not there yet.
test("a subscribe Home Assistant does not know yet after a restart is tried again", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const conn = withConnectionEvents(makeConnection({ script: ["resolve", "unknown_command", "resolve"] }));
    const lists = [];
    const errors = [];
    const stop = onTabletsChanged(conn, (tablets) => lists.push(tablets), {
      onError: (error) => errors.push(error.code),
    });
    await flush();
    conn.subscribes[0].callback({ type: "tablets", tablets: [KITCHEN] });

    conn.fire("ready");
    await flush();
    assert.deepEqual(errors, []);
    mock.timers.tick(2000);
    assert.equal(conn.subscribes.length, 3);
    await flush();
    conn.subscribes[2].callback({ type: "tablets", tablets: [HALLWAY] });
    assert.deepEqual(lists, [[KITCHEN], [HALLWAY]]);
    assert.deepEqual(errors, []);
    stop();
    mock.timers.tick(1000);
  } finally {
    mock.timers.reset();
  }
});

// Lets `ms` milliseconds pass one second at a time, with the promise steps
// in between that a failed subscribe needs to ask for its next try.
async function pass(ms) {
  for (let done = 0; done < ms; done += 1000) {
    mock.timers.tick(1000);
    await flush();
  }
}

// The first subscribe can come while Home Assistant is still starting (a
// preview card made again after a reconnect), or meet an older integration
// that was updated but not restarted. The listener hears of it at once and
// the subscribe is tried again in the background.
test("a first subscribe Home Assistant does not know is reported at once and tried again", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const conn = withConnectionEvents(
      makeConnection({ script: ["unknown_command", "unknown_command", "resolve"] }),
    );
    const lists = [];
    const errors = [];
    const stop = onTabletsChanged(conn, (tablets) => lists.push(tablets), {
      onError: (error) => errors.push(error.code),
    });
    await flush();
    assert.deepEqual(errors, ["unknown_command"]);
    assert.equal(conn.subscribes.length, 1);

    mock.timers.tick(2000);
    assert.equal(conn.subscribes.length, 2);
    await flush();
    // The same failure is told once.
    assert.deepEqual(errors, ["unknown_command"]);
    mock.timers.tick(4000);
    assert.equal(conn.subscribes.length, 3);
    await flush();
    conn.subscribes[2].callback({ type: "tablets", tablets: [KITCHEN] });
    assert.deepEqual(lists, [[KITCHEN]]);

    // The failure is over: a newcomer gets the list, with no new subscribe.
    const later = [];
    const laterErrors = [];
    const stopLater = onTabletsChanged(conn, (tablets) => later.push(tablets), {
      onError: (error) => laterErrors.push(error.code),
    });
    assert.deepEqual(later, [[KITCHEN]]);
    assert.deepEqual(laterErrors, []);
    assert.equal(conn.subscribes.length, 3);
    stop();
    stopLater();
    mock.timers.tick(1000);
  } finally {
    mock.timers.reset();
  }
});

test("a subscribe Home Assistant never knows is given up after ten minutes", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const conn = withConnectionEvents(
      makeConnection({
        script: [...Array(25).fill("unknown_command"), "resolve", ...Array(24).fill("unknown_command")],
      }),
    );
    const lists = [];
    const errors = [];
    const stop = onTabletsChanged(conn, (tablets) => lists.push(tablets), {
      onError: (error) => errors.push(error.code),
    });
    await flush();
    // Tries after 2, 4, 8 and 16 s, then every 30 s; the last at ten minutes.
    await pass(599000);
    assert.equal(conn.subscribes.length, 23);
    await pass(1000);
    assert.equal(conn.subscribes.length, 24);
    await pass(1800000);
    assert.equal(conn.subscribes.length, 24);
    assert.deepEqual(errors, ["unknown_command"]);

    // A new connection tries again, with the short waits first.
    conn.fire("ready");
    assert.equal(conn.subscribes.length, 25);
    await flush();
    await pass(2000);
    assert.equal(conn.subscribes.length, 26);
    conn.subscribes[25].callback({ type: "tablets", tablets: [HALLWAY] });
    assert.deepEqual(lists, [[HALLWAY]]);
    assert.deepEqual(errors, ["unknown_command"]);

    // The failure was over. The next one is its own, and is told as well.
    conn.fire("ready");
    await flush();
    await pass(600000);
    assert.equal(conn.subscribes.length, 50);
    assert.deepEqual(errors, ["unknown_command", "unknown_command"]);
    stop();
    mock.timers.tick(1000);
  } finally {
    mock.timers.reset();
  }
});

// After a restart the listeners keep the list they have while the subscribe
// is tried again, and hear of the failure only when it is given up.
test("a subscribe Home Assistant stops knowing is reported when it is given up", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const conn = withConnectionEvents(
      makeConnection({ script: ["resolve", ...Array(24).fill("unknown_command")] }),
    );
    const lists = [];
    const errors = [];
    const stop = onTabletsChanged(conn, (tablets) => lists.push(tablets), {
      onError: (error) => errors.push(error.code),
    });
    await flush();
    conn.subscribes[0].callback({ type: "tablets", tablets: [KITCHEN] });

    conn.fire("ready");
    await flush();
    await pass(599000);
    assert.deepEqual(errors, []);
    await pass(1000);
    assert.deepEqual(errors, ["unknown_command"]);
    assert.equal(conn.subscribes.length, 25);
    await pass(60000);
    assert.equal(conn.subscribes.length, 25);
    assert.deepEqual(lists, [[KITCHEN]]);
    stop();
    mock.timers.tick(1000);
  } finally {
    mock.timers.reset();
  }
});

// Home Assistant's connection answers a subscribe that was under way when
// the connection was lost with "Connection lost". The connection comes back
// with "ready", and the subscribe is sent again then.
test("a subscribe cut off by a lost connection waits for the connection", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const conn = withConnectionEvents(makeConnection({ script: ["resolve", "lost", "resolve"] }));
    const lists = [];
    const errors = [];
    const stop = onTabletsChanged(conn, (tablets) => lists.push(tablets), {
      onError: (error) => errors.push(error),
    });
    await flush();
    conn.subscribes[0].callback({ type: "tablets", tablets: [KITCHEN] });

    conn.fire("ready");
    await flush();
    assert.deepEqual(errors, []);
    await pass(60000);
    assert.equal(conn.subscribes.length, 2);

    conn.fire("ready");
    assert.equal(conn.subscribes.length, 3);
    await flush();
    conn.subscribes[2].callback({ type: "tablets", tablets: [KITCHEN, HALLWAY] });
    assert.deepEqual(lists, [[KITCHEN], [KITCHEN, HALLWAY]]);
    assert.deepEqual(errors, []);
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

// The first listener shows the failure while the subscribe is tried again
// in the background. A newcomer should not wait for the next try to hear
// how things stand.
test("a newcomer during a failure has the subscribe tried at once", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const conn = withConnectionEvents(
      makeConnection({ script: ["unknown_command", "unknown_command", "resolve"] }),
    );
    const errors = [];
    const stop = onTabletsChanged(conn, () => {}, { onError: (error) => errors.push(error.code) });
    await flush();
    assert.deepEqual(errors, ["unknown_command"]);

    const lists = [];
    const nextErrors = [];
    const stopNext = onTabletsChanged(conn, (tablets) => lists.push(tablets), {
      onError: (error) => nextErrors.push(error.code),
    });
    assert.equal(conn.subscribes.length, 2);
    await flush();
    assert.deepEqual(nextErrors, ["unknown_command"]);
    // Only the new try goes on: one subscribe after 2 s, none from the old.
    mock.timers.tick(2000);
    assert.equal(conn.subscribes.length, 3);
    await flush();
    conn.subscribes[2].callback({ type: "tablets", tablets: [KITCHEN] });
    assert.deepEqual(lists, [[KITCHEN]]);
    assert.equal(conn.listeners.get("ready").length, 1);
    stop();
    stopNext();
    mock.timers.tick(1000);
    assert.deepEqual(conn.listeners.get("ready"), []);
  } finally {
    mock.timers.reset();
  }
});

// The answer to a change is shown over the last list. While the listeners
// show a failure there is no such list.
test("a failure leaves no old list for a newcomer", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const conn = withConnectionEvents(makeConnection({ script: ["resolve", "unauthorized", "resolve"] }));
    const lists = [];
    const errors = [];
    const stop = onTabletsChanged(conn, (tablets) => lists.push(tablets), {
      onError: (error) => errors.push(error.code),
    });
    await flush();
    conn.subscribes[0].callback({ type: "tablets", tablets: [KITCHEN] });
    conn.fire("ready");
    await flush();
    assert.deepEqual(errors, ["unauthorized"]);

    // The first newcomer has the subscribe tried again; the second comes
    // before its answer and gets no list from before the failure.
    const first = [];
    const second = [];
    const stopFirst = onTabletsChanged(conn, (tablets) => first.push(tablets));
    const stopSecond = onTabletsChanged(conn, (tablets) => second.push(tablets));
    assert.equal(conn.subscribes.length, 3);
    assert.deepEqual([first, second], [[], []]);
    await flush();
    conn.subscribes[2].callback({ type: "tablets", tablets: [HALLWAY] });
    assert.deepEqual([first, second], [[[HALLWAY]], [[HALLWAY]]]);
    assert.deepEqual(lists, [[KITCHEN], [HALLWAY]]);
    stop();
    stopFirst();
    stopSecond();
    mock.timers.tick(1000);
  } finally {
    mock.timers.reset();
  }
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
  // A truthy value that is not true still goes out as true, never as itself.
  await assignTablet(conn, "aa:01", "home", { approve: "yes" });
  assert.deepEqual(conn.sent, [
    { type: "apollo_tab/tablet/assign", mac: "aa:01", url_path: "home", approve: true },
    { type: "apollo_tab/tablet/assign", mac: "aa:01", url_path: "home" },
    { type: "apollo_tab/tablet/assign", mac: "aa:01", url_path: "home" },
    { type: "apollo_tab/tablet/assign", mac: "aa:01", url_path: "home", approve: true },
  ]);
  // Every file of the frontend folder is read, so a new file is held to
  // the same rules: only the panel's _turnOn passes approve, the assign
  // command is written in api.js alone, and no code presses a control.
  const files = fs
    .readdirSync(FRONTEND)
    .filter((name) => name.endsWith(".js"))
    .map((name) => [name, fs.readFileSync(path.join(FRONTEND, name), "utf8")]);
  assert.ok(files.length > 10, "the frontend folder was read");
  const holding = (pattern) => files.filter(([, text]) => pattern.test(text)).map(([name]) => name);
  const count = (pattern) => files.reduce((total, [, text]) => total + (text.match(pattern)?.length || 0), 0);
  assert.deepEqual(holding(/apollo_tab\/tablet\/assign/), ["api.js"]);
  assert.equal(count(/approve: true/g), 1);
  assert.deepEqual(holding(/approve: true/), ["panel.js"]);
  // No approve of any value in any other file (api.js names it in a comment).
  assert.deepEqual(
    holding(/approve\s*:/).filter((name) => !["panel.js", "api.js"].includes(name)),
    [],
  );
  // Not even the word, so a shorthand `{ approve }` cannot pass one either.
  assert.deepEqual(holding(/\bapprove\b/).sort(), ["api.js", "panel.js"]);
  const panelText = files.find(([name]) => name === "panel.js")[1];
  assert.equal(panelText.match(/approve\s*:/g)?.length, 1);
  assert.equal(count(/this\._turnOn\(/g), 1);
  // _turnOn is defined once and called once, nowhere else.
  assert.equal(count(/\b_turnOn\b/g), 2);
  // The only stored things are the two lists of dashboards in designer.js
  // and the start screen's flags in prefs.js.
  assert.equal(count(/setItem\(/g), 3);
  assert.deepEqual(holding(/setItem\(/).sort(), ["designer.js", "prefs.js"]);
  // prefs.js stores only the text "1", and only under the names of its list.
  const prefs = files.find(([name]) => name === "prefs.js")[1];
  assert.match(prefs, /setItem\(key, "1"\)/);
  assert.match(prefs, /FLAGS\.includes\(name\) \? PREFIX \+ name : null/);
  // The one call of _turnOn sits in the click handler that _turnOnButton
  // makes; the guide's button only scrolls and gives focus.
  const method = (text, name) => {
    const start = text.indexOf(`\n  ${name}(`);
    assert.ok(start >= 0, `${name} is in panel.js`);
    const end = text.indexOf("\n  }\n", start);
    return text.slice(start, end);
  };
  const panelSource = files.find(([name]) => name === "panel.js")[1];
  assert.match(method(panelSource, "_turnOnButton"), /this\._turnOn\(mac\)/);
  for (const name of ["_guideGo", "_scrollAndMark", "_markAllTurnOns", "_arrive"]) {
    assert.doesNotMatch(method(panelSource, name), /_turnOn\(|_assign\(|_chosen/, `${name} turns a tablet on or picks`);
  }
  const guide = method(panelSource, "_guide");
  const go = guide.slice(guide.indexOf('test: "guide-go"'));
  assert.match(go, /onClick: \(\) => this\._guideGo\(/);
  // No turn-on button is built inside a label.
  for (const name of ["_turnOnButton", "_fillTabletRow"]) {
    assert.doesNotMatch(method(panelSource, name), /"label"/, `${name} makes a label`);
  }
  for (const [name, text] of files) {
    assert.doesNotMatch(text, /\.click\s*\(/, `${name} presses a control`);
    assert.doesNotMatch(text, /new (Mouse|Pointer|Keyboard|Touch)Event\(/, `${name} makes an input event`);
    assert.doesNotMatch(
      text,
      /new \w*Event\(\s*["'`](click|dblclick|auxclick|mouse|pointer|key|touch)/i,
      `${name} makes an input event`,
    );
  }
  const panel = fs.readFileSync(path.join(FRONTEND, "panel.js"), "utf8");
  assert.match(panel, /this\._assign\(mac, urlPath, \{ approve: true \}\);/);
  // Every other call of _assign leaves approve out, so its default must be false.
  assert.match(panel, /\n  async _assign\(mac, urlPath, \{ approve = false \} = \{\}\) \{\n/);
  assert.equal(panel.match(/\bapprove\s*=/g)?.length, 1);
});

// The editor hands the start screen a tablet to set up in memory only, and
// the start screen scrolls to it at once, never smoothly, so no Turn on
// button is still moving when it can be pressed.
test("the start screen keeps a handover in memory and scrolls at once", async () => {
  const panel = fs.readFileSync(path.join(FRONTEND, "panel.js"), "utf8");
  assert.doesNotMatch(panel, /localStorage|sessionStorage|indexedDB/);
  const states = [...panel.matchAll(/history\.(pushState|replaceState)\(([^,]*),/g)];
  assert.ok(states.length >= 2, "the panel moves between screens with pushState");
  for (const [, , first] of states) {
    assert.equal(first.trim(), "null");
  }
  const scrolls = [...panel.matchAll(/scrollIntoView\(([^)]*)\)/g)];
  assert.ok(scrolls.length >= 1, "the arrival scrolls");
  for (const [, args] of scrolls) {
    assert.match(args, /behavior: "instant"/);
  }
  const focuses = [...panel.matchAll(/\.focus\(([^)]*)\)/g)];
  assert.ok(focuses.length >= 4);
  for (const [, args] of focuses) {
    assert.match(args, /preventScroll: true/);
  }
  const { panelStyles } = await import("../../custom_components/apollo_tab/frontend/styles.js");
  assert.doesNotMatch(panelStyles, /scroll-behavior/);
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

// Home Assistant can send the answer and later lists in one go. The lists
// are then handled first, and the answer, which is older, must not come
// back over them.
for (const [name, type, change] of [
  ["assigning a dashboard", "apollo_tab/tablet/assign", (conn) => assignTablet(conn, "aa:01", "night")],
  ["setting a tablet up again", "apollo_tab/tablet/pair", (conn) => pairTablet(conn, "aa:01")],
]) {
  test(`${name}: an answer does not replace a list that came after the change was sent`, async () => {
    let answer;
    const conn = makeConnection({
      answers: {
        [type]: () =>
          new Promise((resolve) => {
            answer = resolve;
          }),
      },
    });
    const lists = [];
    const stop = onTabletsChanged(conn, (tablets) => lists.push(tablets));
    await flush();
    conn.subscribes[0].callback({ type: "tablets", tablets: [KITCHEN, HALLWAY] });

    const sending = { ...KITCHEN, dashboard: "night", status: "sending" };
    const failed = { ...KITCHEN, dashboard: "night", status: "failed", reason: "too_big" };
    const pending = change(conn);
    await flush();
    answer({ tablet: sending });
    conn.subscribes[0].callback({ type: "tablets", tablets: [failed, HALLWAY] });

    // The caller still gets the answer.
    assert.deepEqual(await pending, sending);
    assert.deepEqual(lists, [
      [KITCHEN, HALLWAY],
      [failed, HALLWAY],
    ]);
    stop();
  });
}

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
