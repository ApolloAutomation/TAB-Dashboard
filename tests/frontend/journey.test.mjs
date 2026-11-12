import test from "node:test";
import assert from "node:assert";
import { spawn } from "node:child_process";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import vm from "node:vm";

import * as journey from "../harness/journey.mjs";
import { Browser, checkNoSidewaysScroll, harnessAnswer, portInUse, waitForChild } from "../harness/journey.mjs";

// The page helpers, run against stand-in elements whose computed style is
// their `style`.
function pageHelpers() {
  const window = {};
  vm.runInNewContext(String(journey.PAGE_HELPERS), {
    window,
    getComputedStyle: (node) => node.style,
    ShadowRoot: class {},
  });
  return window.__j;
}

function node(style, parentNode = null) {
  return { nodeType: 1, parentNode, style: { backgroundColor: "rgba(0, 0, 0, 0)", opacity: "1", ...style } };
}

test("the contrast helper fades words with a faded parent", () => {
  const helpers = pageHelpers();
  const page = node({ backgroundColor: "rgb(255, 255, 255)" });
  const tile = node({ backgroundColor: "rgb(255, 255, 255)" }, page);
  const words = node({ color: "rgb(94, 94, 94)" }, tile);
  // #5e5e5e on white.
  assert.equal(helpers.textContrast(words), 6.48);
  // The same words in a tile at 75 % opacity: about 3.6:1.
  tile.style.opacity = "0.75";
  assert.equal(helpers.textContrast(words), 3.63);
  // A see-through background over a dark page.
  tile.style.opacity = "1";
  tile.style.backgroundColor = "rgba(255, 255, 255, 0.5)";
  page.style.backgroundColor = "rgb(28, 28, 28)";
  assert.deepEqual(helpers.backdrop(words).map(Math.round), [142, 142, 142, 1]);
});

// A stand-in page for checkTextContrast: light words in a dark toast that
// fades in. While the first `fading` reads are made the fade-in still runs
// and the toast is at 40 % opacity; after that it is fully drawn.
function fadingToast(fading, { endless = false } = {}) {
  let reads = 0;
  const running = () => reads <= fading;
  const page = node({ backgroundColor: "rgb(255, 255, 255)" });
  const toast = node({ backgroundColor: "rgb(20, 20, 20)" }, page);
  Object.defineProperty(toast.style, "opacity", { get: () => (running() ? "0.4" : "1") });
  const fade = { playState: "running", effect: { getComputedTiming: () => ({ endTime: 120 }) } };
  const spinner = { playState: "running", effect: { getComputedTiming: () => ({ endTime: Infinity }) } };
  toast.getAnimations = () => [...(running() ? [fade] : []), ...(endless ? [spinner] : [])];
  const words = node({ color: "rgb(250, 250, 250)" }, toast);
  const context = vm.createContext({ getComputedStyle: (element) => element.style, ShadowRoot: class {} });
  context.window = context;
  vm.runInContext(String(journey.PAGE_HELPERS), context);
  context.__j.find = (selector) => (selector === '[data-test="toast"] span' ? words : null);
  const run = {
    eval: async (expression) => {
      reads += 1;
      return vm.runInContext(expression, context);
    },
  };
  return { run, reads: () => reads };
}

test("the contrast check waits for a toast to finish fading in", async () => {
  const { run, reads } = fadingToast(3);
  await journey.checkTextContrast(run, ['[data-test="toast"] span']);
  assert.ok(reads() > 3, `measured after ${reads()} reads`);
  // An animation that never ends, such as a spinner, is not waited for.
  const endless = fadingToast(0, { endless: true });
  await journey.checkTextContrast(endless.run, ['[data-test="toast"] span']);
  assert.equal(endless.reads(), 1);
  // A fade that does not finish in time fails the check, with the reason.
  await assert.rejects(
    journey.checkTextContrast(fadingToast(1000).run, ['[data-test="toast"] span'], 200),
    /still animating/,
  );
});

function listen(handler) {
  const server = http.createServer(handler);
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

function close(server) {
  return new Promise((resolve) => server.close(resolve));
}

test("the journey refuses a port that a left-over server still holds", async () => {
  const stale = await listen((request, response) => response.end("old harness"));
  const { port } = stale.address();
  try {
    assert.equal(await portInUse(port), true);
    for (const options of [{ port }, { debugPort: port }]) {
      // Nothing may be started: the paths below do not exist.
      const browser = new Browser(
        { port: 0, debugPort: 0, python: "/no/such/python", chrome: "/no/such/chrome", ...options },
        path.join(os.tmpdir(), "unused-journey-out"),
      );
      await assert.rejects(browser.start(), /already in use/);
      assert.equal(browser.processes.length, 0);
    }
  } finally {
    await close(stale);
  }
  assert.equal(await portInUse(port), false);
});

test("the journey tells its own harness server from any other", async () => {
  const token = "run-token";
  const ours = await listen((request, response) => {
    response.setHeader("X-Harness-Token", token);
    response.end("ok");
  });
  const other = await listen((request, response) => response.end("old harness"));
  try {
    assert.equal(await harnessAnswer(`http://127.0.0.1:${ours.address().port}`, token), "ours");
    assert.equal(await harnessAnswer(`http://127.0.0.1:${other.address().port}`, token), "other");
    assert.equal(await harnessAnswer(`http://127.0.0.1:${ours.address().port}`, "another-run"), "other");
    // Once it has stopped, nothing answers there.
    const port = ours.address().port;
    await close(ours);
    assert.equal(await harnessAnswer(`http://127.0.0.1:${port}`, token), null);
  } finally {
    if (ours.listening) await close(ours);
    await close(other);
  }
});

test("the journey stops waiting when a process it started has exited", async () => {
  const child = spawn(process.execPath, ["-e", "process.exit(3)"], { stdio: "ignore" });
  await assert.rejects(
    waitForChild(child, "The stand-in", async () => null),
    /The stand-in stopped before it was ready/,
  );
});

// A stand-in for one set-up whose page reports the given widths.
function sizedRun(width, widths) {
  return { setup: { width }, eval: async () => widths };
}

test("the sideways check compares the page with the set-up's width", async () => {
  await checkNoSidewaysScroll(sizedRun(390, { page: 390, body: 390, window: 390 }));
  // With phone emulation the window grows with a page that is too wide, so
  // comparing the page with the window alone would let this through.
  await assert.rejects(
    checkNoSidewaysScroll(sizedRun(390, { page: 642, body: 642, window: 642 })),
    /scrolls sideways on a 390 px screen \(page 642 px, body 642 px, window 642 px\)/,
  );
  await assert.rejects(
    checkNoSidewaysScroll(sizedRun(390, { page: 390, body: 420, window: 390 })),
    /\(body 420 px\)/,
  );
});
