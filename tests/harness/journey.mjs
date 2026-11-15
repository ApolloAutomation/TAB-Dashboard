// Walks through the TAB-1 editor in headless Chrome, the way a person would,
// and checks what the page and the stand-in Home Assistant end up with.
//
//   node tests/harness/journey.mjs --out <dir> [--python <path>] [--chrome <path>]
//                                  [--port <n>] [--debug-port <n>] [--only <set-up>]
//                                  [--steps 20,32]
//
// Uses only Node's built-ins and talks to Chrome over the DevTools protocol.
// Screenshots, the Chrome profile and report.json go to --out, which must be
// outside the repository.
//
// The harness server and Chrome pick free ports themselves unless --port or
// --debug-port names one; a named port that is already in use stops the run.
// Either way the run checks that it talks to the server and the Chrome it
// started, never to ones left over from an earlier run. --steps runs only the
// listed steps, which helps while debugging one chain.
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const GROUP_ORDER = ["lights", "climate", "media", "security", "sensors", "rooms", "more"];
const NOT_SHOWN = "Not shown on the tablet";
// The tablet's own words, from the shared contract (CONTRACT.md section 11).
const SCREENS = JSON.parse(fs.readFileSync(path.join(ROOT, "tests/contract/screens.json"), "utf8"));

const SETUPS = [
  { name: "desktop-light", device: "desktop", ha: "light", width: 1280, height: 800, mobile: false },
  { name: "desktop-dark", device: "desktop", ha: "dark", width: 1280, height: 800, mobile: false },
  { name: "phone-light", device: "phone", ha: "light", width: 390, height: 844, mobile: true },
  { name: "phone-dark", device: "phone", ha: "dark", width: 390, height: 844, mobile: true },
];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function parseArgs(argv) {
  const options = { port: 0, debugPort: 0, python: "python3", chrome: null, out: null, steps: null };
  for (let index = 0; index < argv.length; index += 1) {
    const name = argv[index];
    const value = argv[index + 1];
    if (name === "--out") options.out = value;
    else if (name === "--python") options.python = value;
    else if (name === "--chrome") options.chrome = value;
    else if (name === "--port") options.port = Number(value);
    else if (name === "--debug-port") options.debugPort = Number(value);
    else if (name === "--only") options.only = value;
    else if (name === "--steps") options.steps = value.split(",").map((entry) => entry.trim());
    else throw new Error(`Unknown option: ${name}`);
    index += 1;
  }
  for (const key of ["port", "debugPort"]) {
    if (!Number.isInteger(options[key]) || options[key] < 0 || options[key] > 65535) {
      throw new Error(`Not a port number: ${options[key]}`);
    }
  }
  return options;
}

// True when something already listens on 127.0.0.1:port: it either answers
// a connection or keeps this process from listening there.
export async function portInUse(port) {
  const answers = await new Promise((resolve) => {
    const socket = net.connect({ port, host: "127.0.0.1" });
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("error", () => resolve(false));
  });
  if (answers) return true;
  return new Promise((resolve) => {
    const probe = net.createServer();
    probe.once("error", () => resolve(true));
    probe.listen({ port, host: "127.0.0.1", exclusive: true }, () => probe.close(() => resolve(false)));
  });
}

// Who answers the harness page at `base`: "ours" when the answer carries
// `token`, "other" for any other server, null while nothing answers.
export async function harnessAnswer(base, token) {
  let response;
  try {
    response = await fetch(`${base}/tests/harness/index.html`);
  } catch {
    return null;
  }
  await response.arrayBuffer().catch(() => null);
  if (response.headers.get("x-harness-token") !== token) return "other";
  return response.ok ? "ours" : null;
}

// Waits until `ready()` gives a value, failing early when `child` exits.
export async function waitForChild(child, what, ready, log = () => "") {
  for (let attempt = 0; attempt < 150; attempt += 1) {
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error(`${what} stopped before it was ready. ${log()}`.trim());
    }
    const value = await ready();
    if (value) return value;
    await sleep(100);
  }
  throw new Error(`${what} did not start. ${log()}`.trim());
}

// Resolves symbolic links in the part of the path that exists, so a link
// into the repository is caught too.
function realPath(target) {
  let existing = path.resolve(target);
  const rest = [];
  while (!fs.existsSync(existing)) {
    rest.unshift(path.basename(existing));
    existing = path.dirname(existing);
  }
  return path.join(fs.realpathSync(existing), ...rest);
}

function isInside(child, parent) {
  const relative = path.relative(parent, child);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function chromePath(option) {
  if (option) return option;
  if (process.env.CHROME_BIN) return process.env.CHROME_BIN;
  if (fs.existsSync(MAC_CHROME)) return MAC_CHROME;
  return "google-chrome";
}

function stable(value) {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .filter((key) => value[key] !== undefined)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stable(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function check(condition, message) {
  if (!condition) throw new Error(message);
}

// Runs in the page before its own scripts: finds elements through open
// shadow roots and works out where a real click would land.
export const PAGE_HELPERS = `
window.__j = {
  all(selector, root = document) {
    const found = [];
    const walk = (node) => {
      found.push(...node.querySelectorAll(selector));
      for (const element of node.querySelectorAll("*")) {
        if (element.shadowRoot) walk(element.shadowRoot);
      }
    };
    walk(root);
    return found;
  },
  visible(element) {
    if (!element || !element.isConnected || !element.getClientRects().length) return false;
    return getComputedStyle(element).visibility !== "hidden";
  },
  find(selector, index = 0) {
    return this.all(selector).filter((element) => this.visible(element))[index] || null;
  },
  count(selector) {
    return this.all(selector).filter((element) => this.visible(element)).length;
  },
  active() {
    let active = document.activeElement;
    while (active && active.shadowRoot && active.shadowRoot.activeElement) {
      active = active.shadowRoot.activeElement;
    }
    return active;
  },
  at(x, y) {
    let element = document.elementFromPoint(x, y);
    while (element && element.shadowRoot) {
      const inner = element.shadowRoot.elementFromPoint(x, y);
      if (!inner || inner === element) break;
      element = inner;
    }
    return element;
  },
  inside(outer, node) {
    while (node) {
      if (node === outer) return true;
      node = node.parentNode || node.host || null;
    }
    return false;
  },
  describe(element) {
    if (!element) return "nothing";
    const test = element.dataset && element.dataset.test ? "[data-test=" + element.dataset.test + "]" : "";
    return element.tagName.toLowerCase() + test + (element.className ? "." + String(element.className).split(" ").join(".") : "");
  },
  target(selector, index = 0) {
    const element = this.find(selector, index);
    if (!element) return { error: "not found: " + selector };
    let covering = null;
    for (const block of ["center", "start", "end"]) {
      element.scrollIntoView({ block, inline: "nearest" });
      const rect = element.getBoundingClientRect();
      const x = Math.round(rect.left + rect.width / 2);
      const y = Math.round(rect.top + rect.height / 2);
      const hit = this.at(x, y);
      if (this.inside(element, hit)) return { x, y };
      covering = this.describe(hit) + " at " + x + "," + y + " (scrolled to " + Math.round(scrollY) + ")";
    }
    return { error: selector + " is covered by " + covering };
  },
  // Where a finger would land on an element without moving the page: only
  // the scroll box it sits in (such as the phone layout's card sheet) scrolls.
  targetInPlace(selector) {
    const element = this.find(selector);
    if (!element) return { error: "not found: " + selector };
    let box = this.up(element);
    while (box && box.nodeType === 1) {
      const style = getComputedStyle(box);
      if (/(auto|scroll)/.test(style.overflowY) && box.scrollHeight > box.clientHeight) break;
      box = this.up(box);
    }
    if (box && box.nodeType === 1) {
      const outer = box.getBoundingClientRect();
      const rect = element.getBoundingClientRect();
      if (rect.top < outer.top || rect.bottom > outer.bottom) {
        box.scrollTop += rect.top - outer.top - (outer.height - rect.height) / 2;
      }
    }
    const rect = element.getBoundingClientRect();
    const x = Math.round(rect.left + rect.width / 2);
    const y = Math.round(rect.top + rect.height / 2);
    const hit = this.at(x, y);
    if (this.inside(element, hit)) return { x, y };
    return { error: selector + " is covered by " + this.describe(hit) + " at " + x + "," + y };
  },
  // "" when the selected card on the tablet picture is on screen and nothing
  // covers its centre, else what is wrong. While the phone layout's edit
  // mode is open the page behind it is covered: then the card is looked for
  // in the edit mode's strip of the picture, wholly inside it.
  selectedCardProblem() {
    if (this.find('[data-test="side"][data-mode="edit"]')) {
      const strip = this.find('[data-test="edit-preview"]');
      const mark = strip && this.all("[data-selected]", strip).find((node) => this.visible(node));
      if (!mark) return "no card is selected in the edit mode's picture";
      const box = strip.getBoundingClientRect();
      const rect = mark.getBoundingClientRect();
      if (rect.left < box.left - 0.5 || rect.top < box.top - 0.5 || rect.right > box.right + 0.5 || rect.bottom > box.bottom + 0.5) {
        return "the selected card is not wholly inside the edit mode's picture";
      }
      if (rect.bottom > innerHeight || rect.top < 0) return "the edit mode's picture is off screen";
      const top = this.at(Math.round(rect.left + rect.width / 2), Math.round(rect.top + rect.height / 2));
      return this.inside(strip, top) ? "" : "the selected card is covered by " + this.describe(top);
    }
    const hit = this.find('[data-test="hit"][aria-pressed="true"]');
    if (!hit) return "no card is selected on the tablet picture";
    const rect = hit.getBoundingClientRect();
    const x = Math.round(rect.left + rect.width / 2);
    const y = Math.round(rect.top + rect.height / 2);
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return "the selected card is off screen at " + x + "," + y;
    const top = this.at(x, y);
    return top === hit ? "" : "the selected card is covered by " + this.describe(top) + " at " + x + "," + y;
  },
  text(selector) {
    const element = this.find(selector);
    return element ? element.innerText || element.textContent || "" : "";
  },
  designer() {
    return this.all("apollo-tab-designer")[0] || null;
  },
  saveState() {
    const element = this.find('[data-test="save-state"]');
    return element ? element.dataset.state : null;
  },
  // A point on the tablet picture that is not on any card: the side bar.
  emptyCanvasPoint() {
    const stage = this.find('[data-test="canvas"]');
    if (!stage) return { error: "no canvas" };
    stage.scrollIntoView({ block: "start" });
    const rect = stage.getBoundingClientRect();
    for (const share of [0.3, 0.5, 0.7]) {
      const x = Math.round(rect.left + rect.width * 0.03);
      const y = Math.round(rect.top + rect.height * share);
      const hit = this.at(x, y);
      if (this.inside(stage, hit) && !hit.closest("button")) return { x, y };
    }
    return { error: "every point on the side bar is covered" };
  },
  // Colours as [r, g, b, a] with r, g, b in 0..255 and a in 0..1.
  rgba(text) {
    let match = /^rgba?\\(([^)]+)\\)$/.exec(text);
    if (match) {
      const parts = match[1].split(/[\\s,\\/]+/).filter(Boolean).map(Number);
      return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
    }
    match = /^color\\(srgb ([^)]+)\\)$/.exec(text);
    if (match) {
      const parts = match[1].split(/[\\s\\/]+/).filter(Boolean).map(Number);
      return [parts[0] * 255, parts[1] * 255, parts[2] * 255, parts.length > 3 ? parts[3] : 1];
    }
    throw new Error("cannot read the colour " + text);
  },
  over(top, bottom) {
    const a = top[3];
    return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a)).concat(1);
  },
  up(node) {
    const parent = node.parentNode;
    return parent instanceof ShadowRoot ? parent.host : parent;
  },
  // One colour over another when both may be see-through.
  mix(top, bottom) {
    const alpha = top[3] + bottom[3] * (1 - top[3]);
    if (!alpha) return [0, 0, 0, 0];
    return [0, 1, 2].map((i) => (top[i] * top[3] + bottom[i] * bottom[3] * (1 - top[3])) / alpha).concat(alpha);
  },
  // How a colour drawn inside an element reaches the screen: over that
  // element's background and each one around it, faded by the opacity of
  // every one of them, on a white page.
  paint(element, colour) {
    let result = colour;
    for (let node = element; node && node.nodeType === 1; node = this.up(node)) {
      const style = getComputedStyle(node);
      result = this.mix(result, this.rgba(style.backgroundColor));
      result = result.slice(0, 3).concat(result[3] * Number(style.opacity));
    }
    return this.mix(result, [255, 255, 255, 1]);
  },
  // What is drawn behind an element, its own background included.
  backdrop(element) {
    return this.paint(element, [0, 0, 0, 0]);
  },
  contrast(a, b) {
    const light = (rgb) => {
      const [r, g, bl] = rgb.slice(0, 3).map((v) => {
        const c = v / 255;
        return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
    };
    const [hi, lo] = [light(a), light(b)].sort((x, y) => y - x);
    return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
  },
  // Whether something that ends is still animating the element or one
  // around it, such as a toast fading in: colours read meanwhile are not
  // the ones that stay. Animations that never end are left out.
  animating(element) {
    for (let node = element; node && node.nodeType === 1; node = this.up(node)) {
      const animations = typeof node.getAnimations === "function" ? node.getAnimations() : [];
      if (animations.some((animation) => animation.playState === "running" &&
          animation.effect?.getComputedTiming?.().endTime !== Infinity)) {
        return true;
      }
    }
    return false;
  },
  // A faded parent (opacity below 1) fades the words with it.
  textContrast(element) {
    return this.contrast(this.paint(element, this.rgba(getComputedStyle(element).color)), this.backdrop(element));
  },
  // A field's edge against what is around it.
  edgeContrast(element) {
    const around = this.backdrop(this.up(element));
    const edge = this.over(this.rgba(getComputedStyle(element).borderTopColor), around);
    return this.contrast(edge, around);
  },
  // A field's placeholder text against the field.
  placeholderContrast(element) {
    const style = getComputedStyle(element, "::placeholder");
    const colour = this.rgba(style.color);
    colour[3] *= Number(style.opacity);
    return this.contrast(this.paint(element, colour), this.backdrop(element));
  },
  // What sticks out sideways from \`container\`: the container scrolling
  // sideways, or a field or button reaching past its edges.
  overflowProblems(container) {
    if (!container) return ["the container is not there"];
    const problems = [];
    if (container.scrollWidth > container.clientWidth + 1) {
      problems.push(this.describe(container) + " scrolls sideways (" + container.scrollWidth + " > " + container.clientWidth + ")");
    }
    const box = container.getBoundingClientRect();
    for (const node of container.querySelectorAll("select, input, button, textarea, .field, .form-block")) {
      if (!this.visible(node)) continue;
      const rect = node.getBoundingClientRect();
      if (rect.left < box.left - 1 || rect.right > box.right + 1) {
        problems.push(this.describe(node) + " spans " + Math.round(rect.left) + ".." + Math.round(rect.right) +
          ", outside " + Math.round(box.left) + ".." + Math.round(box.right));
      }
    }
    return problems;
  },
};
`;

export class Browser {
  constructor(options, outDir) {
    this.options = options;
    this.outDir = outDir;
    this.seq = 0;
    this.pending = new Map();
    this.errors = [];
    this.processes = [];
  }

  async start() {
    const { port, debugPort, python } = this.options;
    for (const [named, what] of [
      [port, "--port"],
      [debugPort, "--debug-port"],
    ]) {
      check(
        !named || !(await portInUse(named)),
        `Port ${named} (${what}) is already in use, perhaps by a run that did not stop. ` +
          "Stop it, or leave the option out to use a free port.",
      );
    }

    // The server names the port it listens on, and every answer carries
    // this run's token.
    const token = randomUUID();
    const server = spawn(
      python,
      ["-B", "tests/harness/server.py", "--port", String(port), "--token", token],
      { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"], env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } },
    );
    this.processes.push(server);
    let serverOut = "";
    let serverLog = "";
    server.stdout.on("data", (chunk) => {
      serverOut = (serverOut + chunk).slice(-4000);
    });
    server.stderr.on("data", (chunk) => {
      serverLog = (serverLog + chunk).slice(-4000);
    });
    this.serverLog = () => serverLog;
    const serverPort = await waitForChild(
      server,
      "The harness server",
      async () => Number(/on http:\/\/127\.0\.0\.1:(\d+)\//.exec(serverOut)?.[1]) || null,
      () => serverLog,
    );
    check(!port || serverPort === port, `The harness server listens on ${serverPort}, not ${port}`);
    this.base = `http://127.0.0.1:${serverPort}`;
    await waitForChild(
      server,
      "The harness server",
      async () => {
        const answer = await harnessAnswer(this.base, token);
        check(answer !== "other", `Port ${serverPort} is answered by another server, not the one this run started`);
        return answer === "ours";
      },
      () => serverLog,
    );

    // Chrome writes the port it listens on into its own profile, so a fresh
    // copy of that file names this run's Chrome and no other.
    const profile = path.join(this.outDir, "chrome-profile");
    const portFile = path.join(profile, "DevToolsActivePort");
    fs.rmSync(portFile, { force: true });
    const chrome = spawn(
      chromePath(this.options.chrome),
      [
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--hide-scrollbars",
        `--user-data-dir=${profile}`,
        `--remote-debugging-port=${debugPort}`,
        "--remote-allow-origins=*",
        "about:blank",
      ],
      { stdio: "ignore" },
    );
    this.processes.push(chrome);
    const [chromePort, browserPath] = await waitForChild(chrome, "Chrome", async () => {
      try {
        const [first, second] = fs.readFileSync(portFile, "utf8").split("\n");
        if (Number(first) && second) {
          return [Number(first), second.trim()];
        }
      } catch {
        // No file yet, or none at all: see below.
      }
      if (!debugPort) {
        return null;
      }
      // Newer Chrome writes that file only when it picks the port itself.
      // A named port was free before this Chrome started (checked above) and
      // waitForChild stops when this Chrome dies, so what answers there now
      // is this run's Chrome.
      try {
        const version = await (await fetch(`http://127.0.0.1:${debugPort}/json/version`)).json();
        const socket = version.webSocketDebuggerUrl;
        return socket ? [debugPort, new URL(socket).pathname] : null;
      } catch {
        return null;
      }
    });
    check(!debugPort || chromePort === debugPort, `Chrome listens on ${chromePort}, not ${debugPort}`);
    const target = await waitForChild(chrome, "Chrome", async () => {
      try {
        const version = await (await fetch(`http://127.0.0.1:${chromePort}/json/version`)).json();
        check(
          version.webSocketDebuggerUrl?.endsWith(browserPath),
          `Port ${chromePort} is answered by another Chrome, not the one this run started`,
        );
        const list = await (await fetch(`http://127.0.0.1:${chromePort}/json/list`)).json();
        return list.find((entry) => entry.type === "page") || null;
      } catch (error) {
        if (error.message.includes("another Chrome")) throw error;
        return null;
      }
    });

    this.ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
    this.ws.addEventListener("message", (message) => this._onMessage(JSON.parse(message.data)));
    await this.send("Runtime.enable");
    await this.send("Log.enable");
    await this.send("Page.enable");
    await this.send("Page.addScriptToEvaluateOnNewDocument", { source: PAGE_HELPERS });
  }

  _onMessage(message) {
    if (message.id && this.pending.has(message.id)) {
      const { resolve, reject, timer } = this.pending.get(message.id);
      clearTimeout(timer);
      this.pending.delete(message.id);
      if (message.error) reject(new Error(JSON.stringify(message.error)));
      else resolve(message.result);
      return;
    }
    if (message.method === "Page.javascriptDialogOpening") {
      // The editor asks before leaving with unsaved changes; each step opens
      // a fresh page on purpose, so leave.
      this.send("Page.handleJavaScriptDialog", { accept: true }).catch(() => {});
      return;
    }
    if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
      const text = message.params.args.map((arg) => arg.value ?? arg.description).join(" ");
      this.errors.push(`console error: ${text}`);
    } else if (message.method === "Runtime.exceptionThrown") {
      const details = message.params.exceptionDetails;
      this.errors.push(`uncaught: ${details.exception?.description || details.text}`);
    } else if (message.method === "Log.entryAdded" && message.params.entry.level === "error") {
      const { text, url } = message.params.entry;
      this.errors.push(`log error: ${text} ${url || ""}`.trim());
    }
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this.seq;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method} got no answer within 30 s`));
      }, 30000);
      this.pending.set(id, { resolve, reject, timer });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    }
    return result.result.value;
  }

  // Stops the server and Chrome this run started. The promise settles once
  // both have exited; one that ignores the request for 5 s is killed.
  stop() {
    try {
      this.ws?.close();
    } catch {
      // Already closed.
    }
    return Promise.all(
      this.processes.map(
        (child) =>
          new Promise((resolve) => {
            if (child.exitCode !== null || child.signalCode !== null) {
              resolve();
              return;
            }
            const timer = setTimeout(() => child.kill("SIGKILL"), 5000);
            child.once("exit", () => {
              clearTimeout(timer);
              resolve();
            });
            try {
              child.kill();
            } catch {
              clearTimeout(timer);
              resolve();
            }
          }),
      ),
    );
  }
}

// One set-up: a viewport, a Home Assistant colour scheme and the helpers the
// steps use.
export class Run {
  constructor(browser, setup, shotsDir) {
    this.browser = browser;
    this.setup = setup;
    this.shotsDir = shotsDir;
  }

  eval(expression) {
    return this.browser.eval(expression);
  }

  async viewport() {
    const { width, height, mobile } = this.setup;
    await this.browser.send("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile,
    });
  }

  async open(params, ready) {
    const query = new URLSearchParams({ view: "panel", ha: this.setup.ha, ...params });
    await this.eval("window.__leaving = true").catch(() => {});
    await this.browser.send("Page.navigate", {
      url: `${this.browser.base}/tests/harness/index.html?${query}`,
    });
    await this.waitFor(
      `!window.__leaving && document.readyState === "complete" && !!window.__apolloPanel && !!window.__j`,
      "the harness page to load",
    );
    await this.waitFor(ready, "the first screen");
  }

  async waitFor(expression, what, timeout = 10000) {
    const end = Date.now() + timeout;
    let last = null;
    while (Date.now() < end) {
      try {
        if (await this.eval(`Boolean(${expression})`)) return;
      } catch (error) {
        last = error;
      }
      await sleep(50);
    }
    throw new Error(`Timed out waiting for ${what}${last ? ` (${last.message})` : ""}`);
  }

  async click(selector, index = 0) {
    const target = await this.eval(`__j.target(${JSON.stringify(selector)}, ${index})`);
    check(target && !target.error, target?.error || `cannot click ${selector}`);
    await this.clickAt(target.x, target.y);
  }

  // A press that does not scroll the page first, as a finger would make it.
  async tap(selector) {
    const target = await this.eval(`__j.targetInPlace(${JSON.stringify(selector)})`);
    check(target && !target.error, target?.error || `cannot tap ${selector}`);
    await this.clickAt(target.x, target.y);
  }

  async clickAt(x, y) {
    await this.browser.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
    await this.browser.send("Input.dispatchMouseEvent", {
      type: "mousePressed",
      x,
      y,
      button: "left",
      buttons: 1,
      clickCount: 1,
    });
    await this.browser.send("Input.dispatchMouseEvent", {
      type: "mouseReleased",
      x,
      y,
      button: "left",
      buttons: 0,
      clickCount: 1,
    });
    await sleep(60);
  }

  async type(text) {
    await this.browser.send("Input.insertText", { text });
    await sleep(60);
  }

  async key(key) {
    const codes = { Tab: 9, Enter: 13, Escape: 27, Delete: 46, Backspace: 8, ArrowUp: 38, ArrowDown: 40, ContextMenu: 93 };
    const event = { key, code: key, windowsVirtualKeyCode: codes[key] || 0 };
    await this.browser.send("Input.dispatchKeyEvent", {
      type: "keyDown",
      ...event,
      ...(key === "Enter" ? { text: "\r" } : {}),
    });
    await this.browser.send("Input.dispatchKeyEvent", { type: "keyUp", ...event });
    await sleep(60);
  }

  config(urlPath = "tab-1") {
    return this.eval(`__apolloMockHass.getConfig(${JSON.stringify(urlPath)})`);
  }

  calls(type) {
    return this.eval(`__apolloMockHass.calls.filter((call) => call.type === ${JSON.stringify(type)})`);
  }

  count(selector) {
    return this.eval(`__j.count(${JSON.stringify(selector)})`);
  }

  text(selector) {
    return this.eval(`__j.text(${JSON.stringify(selector)})`);
  }

  async waitSaved(what) {
    await this.waitFor(`__j.saveState() === "saved"`, `the save state to read saved (${what})`);
  }

  // Only what is on screen, as the person sees it without scrolling.
  async screen(name) {
    const result = await this.browser.send("Page.captureScreenshot", { format: "png" });
    const file = path.join(this.shotsDir, `${name}-${this.setup.device}-${this.setup.ha}.png`);
    fs.writeFileSync(file, Buffer.from(result.data, "base64"));
    return path.basename(file);
  }

  // The whole page, except while a dialog or the phone layout's bottom
  // sheet is open: those are not drawn where they are in a full-page
  // capture, so then the screenshot shows what is on screen.
  async shot(name) {
    const sheet = await this.eval(`Boolean(__j.find(".side.sheet") || __j.find("dialog[open]"))`);
    let params = { format: "png" };
    if (!sheet) {
      const metrics = await this.browser.send("Page.getLayoutMetrics");
      const size = metrics.cssContentSize || metrics.contentSize;
      params = {
        format: "png",
        captureBeyondViewport: true,
        clip: { x: 0, y: 0, width: Math.ceil(size.width), height: Math.ceil(size.height), scale: 1 },
      };
    }
    const result = await this.browser.send("Page.captureScreenshot", params);
    const file = path.join(this.shotsDir, `${name}-${this.setup.device}-${this.setup.ha}.png`);
    fs.writeFileSync(file, Buffer.from(result.data, "base64"));
    return path.basename(file);
  }

  // Adds a card through the picker: pick the tile, then the device.
  async addCard(opener, component, entity) {
    await this.click(`[data-test="${opener}"]`);
    await this.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
    await this.click(`[data-test="tile"][data-component="${component}"]`);
    await this.waitFor(`__j.find('[data-test="entity"][data-entity="${entity}"]')`, `the ${entity} option`);
    await this.click(`[data-test="entity"][data-entity="${entity}"]`);
    await this.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
  }

  async clearSelection() {
    await leaveEditMode(this);
    if (await this.count('[data-test="close-panel"]')) {
      await this.click('[data-test="close-panel"]');
    } else if (await this.count('[data-test="hit"][aria-pressed="true"]')) {
      await this.click('[data-test="hit"][aria-pressed="true"]');
      await this.key("Escape");
    }
    await this.waitFor(`!__j.find('[data-test="hit"][aria-pressed="true"]')`, "the selection to clear");
  }

  draft() {
    return this.eval(`structuredClone(__j.designer()._history.present)`);
  }
}

function step(n, name, run, { desktopOnly = false, phoneOnly = false } = {}) {
  return { n, name, run, desktopOnly, phoneOnly };
}

// Whether the phone layout's edit mode (the layer with a card's form) is open.
function inEditMode(r) {
  return r.count('[data-test="side"][data-mode="edit"]');
}

// Closes the phone layout's edit mode with Done, as a person would before
// pressing something under it.
async function leaveEditMode(r) {
  if (await inEditMode(r)) {
    await r.click('[data-test="close-panel"]');
    await r.waitFor(`!__j.find('[data-test="side"][data-mode="edit"]')`, "the edit mode to close");
  }
}

// Shows every page notice: "+N more" when it shows and is closed. On a phone
// every notice shows already.
async function openNotices(r) {
  if (await r.count('[data-test="notices-more"][aria-expanded="false"]')) {
    await r.click('[data-test="notices-more"]');
    await r.waitFor(`__j.find('[data-test="notices-more"][aria-expanded="true"]')`, "every page notice to show");
    // The pointer leaves the notices, so no button there is left hovered.
    await r.browser.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 0, y: r.setup.height - 1 });
    await sleep(200);
  }
}

// The stand-in tablets of mock-hass.js ("three", "no-engine", "new" and
// "two-new").
const KITCHEN = "aa:bb:cc:dd:ee:01";
const HALLWAY = "aa:bb:cc:dd:ee:02";
const BEDROOM = "aa:bb:cc:dd:ee:03";
// The new tablet of the "new" set, which waits for an admin.
const PORCH = "aa:bb:cc:dd:ee:0e";
// The tablet of the "all" set that is not set up for taps yet.
const LOFT = "aa:bb:cc:dd:ee:0c";
// The second new tablet of the "two-new" set, listed above the porch one.
const PATIO = "aa:bb:cc:dd:ee:0f";
// The status of a new tablet while there are dashboards to pick.
const NEW_STATUS = 'New tablet. Pick a dashboard, then press "Turn on with this dashboard".';
// For how long Turn on ignores presses after the rows moved (tablets.js).
const TURN_ON_SETTLE_MS = 700;
const tabletRow = (mac) => `[data-test="tablet-row"][data-mac="${mac}"]`;
const tabletStatus = (mac) => `${tabletRow(mac)} [data-test="tablet-status"]`;
const tabletShows = (mac) => `${tabletRow(mac)} [data-test="tablet-shows"]`;
const shownOnLine = (urlPath) => `[data-test="dashboard-row"][data-url-path="${urlPath}"] [data-test="row-shown-on"]`;

function uiString(r, key) {
  return r.eval(`__apolloFixtures.strings[${JSON.stringify(key)}]`);
}

async function waitText(r, selector, words, what, timeout = 10000) {
  try {
    await r.waitFor(`__j.text(${JSON.stringify(selector)}) === ${JSON.stringify(words)}`, what, timeout);
  } catch (error) {
    throw new Error(`${error.message}; it reads "${await r.text(selector)}"`);
  }
}

// Picks a dashboard in a tablet's "Shows" list, as choosing it does.
function pickShows(r, mac, urlPath) {
  return r.eval(`(() => { const field = __j.find(${JSON.stringify(tabletShows(mac))}); field.focus();
    field.value = ${JSON.stringify(urlPath)}; field.dispatchEvent(new Event("change", { bubbles: true })); return true; })()`);
}

// On a phone, keyboard focus moves from `before` to `link` with Tab, and
// the link's focus ring stays off the words above it in its paragraph.
async function checkRingClear(r, before, link) {
  await r.eval(`(() => { const node = __j.find(${JSON.stringify(before)}); node.scrollIntoView({ block: "center" }); node.focus(); return true; })()`);
  await r.key("Tab");
  const ring = await r.eval(`(() => {
    const link = __j.find(${JSON.stringify(link)});
    const style = getComputedStyle(link);
    const reach = parseFloat(style.outlineWidth) + parseFloat(style.outlineOffset);
    let text = link.previousSibling;
    while (text && !(text.nodeType === 3 && text.textContent.trim())) text = text.previousSibling;
    const range = document.createRange();
    range.selectNodeContents(text);
    const bottom = Math.max(...[...range.getClientRects()].map((rect) => rect.bottom));
    return { focused: __j.active() === link, visible: link.matches(":focus-visible"), outline: style.outlineStyle,
      ringTop: Math.round((link.getBoundingClientRect().top - reach) * 10) / 10, textBottom: Math.round(bottom * 10) / 10 }; })()`);
  check(
    ring.focused && ring.visible && ring.outline !== "none" && ring.ringTop >= ring.textBottom,
    `the focus ring of ${link} covers the words above it: ${JSON.stringify(ring)}`,
  );
  return ring;
}

// The lines that say which tablets show the dashboard, as on screen.
function captionTexts(r) {
  return r.eval(`__j.all('[data-test="tablet-line"]').filter((line) => __j.visible(line)).map((line) => line.textContent)`);
}

async function waitCaption(r, lines, what) {
  const expected = JSON.stringify(lines);
  try {
    await r.waitFor(
      `JSON.stringify(__j.all('[data-test="tablet-line"]').filter((line) => __j.visible(line)).map((line) => line.textContent)) === ${JSON.stringify(expected)}`,
      what,
    );
  } catch (error) {
    throw new Error(`${error.message}; the lines read ${JSON.stringify(await captionTexts(r))}`);
  }
}

// The cards the picker offers: the 41 bundled cards but the 15 older ones
// a newer card replaces. Of the older cards only the camera snapshot is
// still offered.
const OFFERED_CARDS = 26;

const CREATED_CARD = {
  type: "custom:apollo-tab-card",
  component: "apollo/light",
  params: { entity: "light.kitchen" },
  grid_options: { columns: 6, rows: 3 },
};

// A second dashboard for the steps that move between dashboards.
const SECOND_CONFIG = {
  apollo_tab: { version: 1, theme: "warm" },
  views: [
    {
      type: "sections",
      title: "Other",
      path: "other",
      icon: "mdi:sofa",
      max_columns: 3,
      sections: [{ type: "grid", column_span: 3, cards: [] }],
    },
  ],
};

// The longest page name the page name field takes, and a theme name as long
// as a theme added later might have.
const LONG_PAGE = "Upstairs bedroom and the guest room area";
const LONG_THEME = "Warm evening light with soft amber cards for the living room, hall and kitchen";

// A dashboard whose second page has the long name, with a room card on Home
// that links to it.
const LONG_NAMES_CONFIG = {
  apollo_tab: { version: 1, theme: "warm" },
  views: [
    {
      type: "sections",
      title: "Home",
      path: "home",
      icon: "mdi:home",
      max_columns: 3,
      sections: [
        {
          type: "grid",
          column_span: 3,
          cards: [
            {
              type: "custom:apollo-tab-card",
              component: "community/room-summary",
              params: {
                temperature_sensor: "sensor.temperature",
                humidity_sensor: "sensor.humidity",
                lights: ["light.bedroom"],
                page: "upstairs",
              },
              grid_options: { columns: 12, rows: 3 },
            },
          ],
        },
      ],
    },
    {
      type: "sections",
      title: LONG_PAGE,
      path: "upstairs",
      icon: "mdi:bed",
      max_columns: 3,
      sections: [{ type: "grid", column_span: 3, cards: [] }],
    },
  ],
};

// A dashboard whose one card the tablet cannot show controls three devices.
const SEVERAL_CONFIG = {
  apollo_tab: { version: 1, theme: "midnight" },
  views: [
    {
      type: "sections",
      title: "Home",
      path: "home",
      icon: "mdi:home",
      max_columns: 3,
      sections: [
        {
          type: "grid",
          column_span: 3,
          cards: [{ type: "entities", entities: ["light.kitchen", "light.bedroom", "fan.bedroom_main_bedroom_fan"] }],
        },
      ],
    },
  ],
};

// One page of the given cards and an empty second page.
function twoPages(cards) {
  return {
    apollo_tab: { version: 1, theme: "midnight" },
    views: [
      { type: "sections", title: "Home", path: "home", icon: "mdi:home", max_columns: 3, sections: [{ type: "grid", column_span: 3, cards }] },
      { type: "sections", title: "Climate", path: "climate", icon: "mdi:thermostat", max_columns: 3, sections: [{ type: "grid", column_span: 3, cards: [] }] },
    ],
  };
}
const tabCards = (count, component, entity) =>
  Array.from({ length: count }, () => ({ type: "custom:apollo-tab-card", component, params: { entity } }));

// Five dials on one screen, one more than a screen can show.
const DIALS_CONFIG = twoPages(tabCards(5, "apollo/thermostat", "climate.hall"));

// One card with five graphs, one more than a screen can show: it is left
// out, and its page has nothing else. The card is the stand-in's and the
// harness server's own (FIVE_GRAPHS).
const GRAPHS_CONFIG = twoPages(tabCards(1, "me/five-graphs", "sensor.energy"));

// One page that uses the whole screen with a full row of lights and more.
const ROW_CONFIG = {
  apollo_tab: { version: 1, theme: "midnight" },
  views: [
    {
      type: "sections",
      title: "Home",
      path: "home",
      icon: "mdi:home",
      max_columns: 3,
      sections: [{ type: "grid", column_span: 3, cards: tabCards(6, "apollo/light-tile", "light.kitchen") }],
    },
  ],
};

// So many cards that the page needs two screens; the last of five dials is
// left out on the second screen.
const SPILL_CONFIG = twoPages([
  ...tabCards(24, "apollo/light-tile", "light.kitchen"),
  ...tabCards(5, "community/energy-gauge", "sensor.energy"),
]);

const SAVES = `__apolloMockHass.calls.filter((call) => call.type === "lovelace/config/save")`;
// How many banners ask which version to keep.
const BANNER = `(__j.count('[data-test="conflict"]') + __j.count('[data-test="conflict-unsure"]'))`;

// The names a screen reader gives the page tabs.
async function tabNames(r) {
  await r.browser.send("Accessibility.enable");
  const { nodes } = await r.browser.send("Accessibility.getFullAXTree");
  await r.browser.send("Accessibility.disable");
  return nodes
    .filter((node) => !node.ignored && node.role?.value === "tab")
    .map((node) => String(node.name?.value ?? ""));
}

async function until(test, what, timeout = 10000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await test()) return;
    await sleep(100);
  }
  throw new Error(`Timed out waiting for ${what}`);
}

// Every listed control's words reach 4.5:1 against what is behind them,
// measured once nothing animates them any more: a toast that is still
// fading in would read as faint as it looks at that moment.
export async function checkTextContrast(r, selectors, timeout = 3000) {
  const read = `${JSON.stringify(selectors)}.map((selector) => {
    const element = __j.find(selector);
    return [selector, element ? __j.textContrast(element) : null, Boolean(element && __j.animating(element))];
  })`;
  const end = Date.now() + timeout;
  let ratios = await r.eval(read);
  while (ratios.some(([, , moving]) => moving) && Date.now() < end) {
    await sleep(50);
    ratios = await r.eval(read);
  }
  for (const [selector, ratio, moving] of ratios) {
    check(ratio !== null, `${selector} is not on screen`);
    check(!moving, `${selector} was still animating after ${timeout} ms`);
    check(ratio >= 4.5, `the words of ${selector} have contrast ${ratio}`);
  }
}

// Nothing is wider than the screen the set-up asked for. The window's own
// width is no measure on a phone: with mobile emulation it grows with
// content that is too wide, so the page and the window are both compared
// with the set-up's width, or with the width a step set for itself.
export async function checkNoSidewaysScroll(r, limit = r.setup.width) {
  const widths = await r.eval(`({
    page: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    window: window.innerWidth,
  })`);
  const over = Object.entries(widths).filter(([, width]) => width > limit);
  check(
    over.length === 0,
    `the page scrolls sideways on a ${limit} px screen (${over.map(([what, width]) => `${what} ${width} px`).join(", ")})`,
  );
}

async function checkSelectedCardVisible(r, when) {
  const problem = await r.eval(`__j.selectedCardProblem()`);
  check(!problem, `${when}: ${problem}`);
}

// Drawn controls on the tablet picture that a screen reader would announce
// besides the named card buttons above them.
async function canvasAccessibilityProblems(r) {
  await r.browser.send("Accessibility.enable");
  const { nodes } = await r.browser.send("Accessibility.getFullAXTree");
  await r.browser.send("Accessibility.disable");
  const problems = [];
  for (const node of nodes) {
    if (node.ignored) continue;
    const role = node.role?.value;
    const name = String(node.name?.value ?? "").trim();
    if ((role === "switch" || role === "slider") && !name) problems.push(`a ${role} without a name`);
    if (role === "button" && /^mdi:/.test(name)) problems.push(`a button named ${name}`);
  }
  return problems;
}

// Selects the first card of the sample's second section, makes it wider
// with saves that take 1.5 s, and makes it taller while that save runs, so
// one save is under way and one waits behind it. Returns the editor's draft.
async function editWithSlowSaves(r) {
  await r.click('[data-test="list-row"][data-source="0.1.0"]');
  await r.waitFor(`__j.find('[data-test="wider"]')`, "the card form");
  await r.eval(`__apolloMockHass.slowSaves(1500); true`);
  await r.click('[data-test="wider"]');
  await r.waitFor(`${SAVES}.length === 1`, "the first save to be sent", 3000);
  await r.click('[data-test="taller"]');
  return r.draft();
}

// Opens the editor on the sample dashboard.
async function openSample(r, params = {}) {
  await r.open(
    { seed: "sample", route: "/edit/tab-1", ...params },
    `__j.find('[data-test="canvas"]') || __j.find('[data-test="page-box"]')`,
  );
  await r.waitFor(`__j.count('[data-test="hit"]') > 3`, "cards on the canvas");
}

// Chooses a card in the list. On a phone the edit mode is closed first, as
// a person would, since it covers the list; on a wide screen the list shows
// only while no card is selected.
async function selectRow(r, key) {
  await leaveEditMode(r);
  if (await r.count('[data-test="hit"][aria-pressed="true"]')) {
    await r.clearSelection();
  }
  await r.click(`[data-test="list-row"][data-source="${key}"]`);
  await r.waitFor(`__j.find('[data-test="hit"][data-source="${key}"][aria-pressed="true"]')`, `card ${key} to be selected`);
}

// The side form, the list and the editor all point at the card called
// `name` at `key` (page.group.card).
async function expectSelected(r, name, key, when) {
  let last = null;
  const end = Date.now() + 3000;
  while (Date.now() < end) {
    last = await r.eval(`(() => {
      const selected = __j.designer()._selected;
      // While a card is selected the list is not on screen (its form is in
      // its place), so its row is read from the list itself.
      const list = __j.designer()._els.list;
      const row = list && list.querySelector('[data-test="list-row"][aria-current="true"]');
      return {
        selected: selected ? selected.join(".") : null,
        row: row ? row.dataset.source : null,
        title: __j.text('[data-test="side-title"]').trim(),
      };
    })()`);
    if (last.selected === key && last.row === key && last.title === name) return;
    await sleep(100);
  }
  throw new Error(`${when}: expected ${name} at ${key}, found ${JSON.stringify(last)}`);
}

// Whether leaving the browser page now would ask first.
function leavingAsks(r) {
  return r.eval(`(() => { const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event); return event.defaultPrevented; })()`);
}

// Leaves the editor the way Home Assistant's sidebar does: the panel
// element is removed, with no chance to finish anything first.
async function leaveThroughSidebar(r) {
  await r.eval(`__apolloPanel.remove(); true`);
}

async function reopenEditor(r) {
  await r.eval(`__apolloOpenPanel("/edit/tab-1"); true`);
  await r.waitFor(
    `(__j.find('[data-test="canvas"]') || __j.find('[data-test="page-box"]')) && __j.count('[data-test="hit"]') > 3`,
    "the editor to open again",
  );
}

// Another browser saves the sample dashboard with `change` applied.
function saveElsewhere(r, change) {
  return r.eval(`(() => { const config = __apolloMockHass.getConfig("tab-1");
    (${change})(config);
    __apolloMockHass.externalSave("tab-1", config);
    return config; })()`);
}

// Another browser saves the sample dashboard with `change` applied while
// this browser's connection is down, so no event tells the editor.
function saveOffline(r, change) {
  return r.eval(`(() => { const config = __apolloMockHass.getConfig("tab-1");
    (${change})(config);
    __apolloMockHass.saveWhileOffline("tab-1", config);
    return config; })()`);
}

// A slow save of the editor's own is under way when another browser saves;
// it lands after that, and the person makes one more change and leaves
// through the sidebar before choosing. Opens the editor again, which asks
// once more. Returns the other version, the kept change and the landed save.
async function leaveAfterOwnSaveLanded(r) {
  await openSample(r);
  await selectRow(r, "0.1.0");
  await r.eval(`__apolloMockHass.slowSaves(1500); true`);
  await r.click('[data-test="wider"]');
  await r.waitFor(`${SAVES}.length === 1`, "the save to be sent", 3000);
  const theirs = await saveElsewhere(r, `(config) => { config.views[1].title = "Elsewhere"; }`);
  await r.waitFor(`__j.find('[data-test="conflict-theirs"]')`, "the conflict banner");
  await r.waitFor(`__apolloMockHass.getConfig("tab-1").views[1].title === "Climate"`, "the slow save to land");
  await r.click('[data-test="taller"]');
  const mine = await r.draft();
  const landed = await r.config();
  await leaveThroughSidebar(r);
  await sleep(2500);
  check(stable(await r.config()) === stable(landed), "a change was saved while the choice was open");
  check(await leavingAsks(r), "closing the browser page would not ask about the open choice");
  await r.eval(`__apolloMockHass.slowSaves(0); true`);
  await reopenEditor(r);
  await r.waitFor(`__j.find('[data-test="conflict-theirs"]')`, "the conflict banner again");
  check(stable(await r.draft()) === stable(mine), "the editor does not show the kept change");
  check(stable(await r.config()) === stable(landed), "opening the editor saved the kept change");
  return { theirs, mine, landed };
}

// What has focus, by its data-test name; null when focus fell to the page.
function focused(r) {
  return r.eval(`(() => { const element = __j.active();
    return element && element !== document.body ? element.dataset.test || element.tagName : null; })()`);
}

// Presses Ctrl and `key` together, as for Ctrl+Z.
async function shortcut(r, key) {
  const event = { key, code: `Key${key.toUpperCase()}`, windowsVirtualKeyCode: key.toUpperCase().charCodeAt(0), modifiers: 2 };
  await r.browser.send("Input.dispatchKeyEvent", { type: "rawKeyDown", ...event });
  await r.browser.send("Input.dispatchKeyEvent", { type: "keyUp", ...event });
  await sleep(150);
}

// Presses a control with Enter until it stops taking the press, and checks
// focus moves to `then` rather than falling to the page.
async function pressToLimit(r, test, then) {
  await r.eval(`__j.find('[data-test="${test}"]').focus(); true`);
  check((await focused(r)) === test, `${test} cannot take focus`);
  for (let press = 0; press < 8; press += 1) {
    await r.key("Enter");
    await sleep(150);
    const now = await focused(r);
    check(now, `focus fell to the page after pressing ${test} ${press + 1} times`);
    if (now !== test) break;
  }
  const now = await focused(r);
  check(now === then, `when ${test} could go no further, focus went to ${now}, not ${then}`);
}

// Buttons that remove something when pressed.
const REMOVING = [
  "page-delete",
  "page-remove",
  "row-remove",
  "remove-card",
  "remove-heading",
  "remove-item",
  "dashboard-delete",
  "confirm-ok",
];

// Presses a button that takes itself away with Enter, and checks focus moves
// to `then`: not to the page, and not to a button where one more Enter
// would remove something else.
async function pressRemoving(r, selector, then, what) {
  await r.eval(`__j.find('${selector}').focus(); true`);
  await r.key("Enter");
  await sleep(300);
  const now = await focused(r);
  check(now, `focus fell to the page after ${what}`);
  check(!REMOVING.includes(now), `after ${what} focus went to ${now}, where Enter removes something else`);
  check(now === then, `after ${what} focus went to ${now}, not ${then}`);
}

// Another browser makes a new dashboard at the sample's address, with
// `config` in it.
function recreateElsewhere(r, config) {
  return r.eval(`(async () => {
    const mock = __apolloMockHass;
    await mock.callWS({ type: "lovelace/dashboards/create", url_path: "tab-1", title: "TAB-1",
      icon: "mdi:tablet-dashboard", mode: "storage", require_admin: false, show_in_sidebar: false });
    await mock.callWS({ type: "lovelace/config/save", url_path: "tab-1", config: ${JSON.stringify(config)} });
    return true; })()`);
}

// While this browser's connection is down, another browser deletes the
// sample dashboard and makes a new one at its address with `config` in it.
// No event reaches this browser, and Home Assistant gives the new dashboard
// the same id, so nothing tells the two apart.
function recreateWhileOffline(r, config) {
  return r.eval(`(async () => { const mock = __apolloMockHass;
    mock.deleteWhileOffline("tab-1");
    await mock.callWS({ type: "lovelace/dashboards/create", url_path: "tab-1", title: "TAB-1",
      icon: "mdi:tablet-dashboard", mode: "storage", require_admin: false, show_in_sidebar: false });
    mock.saveWhileOffline("tab-1", ${JSON.stringify(config)});
    return true; })()`);
}

// A change to the sample dashboard that could not be saved, kept after the
// editor was left through the sidebar. With `offline`, another browser
// changed the dashboard meanwhile without this one hearing of it, so the
// kept change waits for a choice; without, its saves keep failing.
async function keepChange(r, { offline }) {
  await openSample(r);
  const original = await r.config();
  await selectRow(r, "0.1.0");
  await r.eval(`__apolloMockHass.failSaves(${offline ? 1 : 100}); true`);
  await r.click('[data-test="wider"]');
  await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
  if (offline) {
    await saveOffline(r, `(config) => { config.views[1].title = "Elsewhere"; }`);
  }
  await leaveThroughSidebar(r);
  await sleep(500);
  check(await leavingAsks(r), "closing the browser page would not ask about the kept change");
  return original;
}

// Page-side checks of the panel's visual system (steps 111 to 118). The
// tablet picture and the example cards in the picker are left out: they are
// drawn as the tablet draws them.
const UI = `window.__ui = {
  inPicture(node) {
    for (let at = node; at && at.nodeType === 1; at = __j.up(at)) {
      if (
        at.classList.contains("page-host") ||
        at.classList.contains("tile-preview") ||
        at.classList.contains("tablet-pic") ||
        at.localName === "apollo-tab-card"
      ) {
        return true;
      }
    }
    return false;
  },
  ownText(node) {
    return [...node.childNodes].some((child) => child.nodeType === 3 && child.textContent.trim());
  },
  // Home Assistant's own sidebar button, drawn by Home Assistant.
  inMenuButton(node) {
    for (let at = node; at && at.nodeType === 1; at = __j.up(at)) {
      if (at.localName === "ha-menu-button") return true;
    }
    return false;
  },
  // [element, font size] of everything with words of its own.
  textSizes() {
    return __j.all("*")
      .filter((node) => __j.visible(node) && !this.inPicture(node) && !this.inMenuButton(node) && this.ownText(node))
      .filter((node) => !["STYLE", "SCRIPT", "OPTION", "TITLE"].includes(node.tagName))
      .map((node) => [__j.describe(node) + " " + node.textContent.trim().slice(0, 24), parseFloat(getComputedStyle(node).fontSize)]);
  },
  // Everything that can be pressed, with its height. A switch is measured
  // by its row, which takes the press; a link inside a sentence is a line
  // high, as the words are, and is left out.
  controls() {
    const found = [];
    for (const node of __j.all("button, a, input, select, textarea, label.check")) {
      if (!__j.visible(node) || this.inPicture(node) || node.matches(".hit")) continue;
      if (node.matches("input[type=checkbox], input[type=radio]")) continue;
      if (node.matches("a:not(.button-link)") && getComputedStyle(node).display === "inline") continue;
      let kind = "other";
      if (node.matches(".tab")) kind = "tab";
      else if (node.matches(".list-row, .entity-option, .tile")) kind = "row";
      else if (node.matches("select, textarea, input:not([type=range]):not([type=color])")) kind = "field";
      else if (node.matches("button, a.button-link")) kind = "plain";
      const rect = node.getBoundingClientRect();
      found.push({ kind, test: node.dataset.test || null, what: __j.describe(node),
        height: Math.round(rect.height * 10) / 10, minHeight: getComputedStyle(node).minHeight });
    }
    return found;
  },
  // The filled buttons on screen, by their data-test.
  filled() {
    return __j.all("button.primary").filter((node) => __j.visible(node) && !this.inPicture(node))
      .map((node) => node.dataset.test || __j.describe(node));
  },
  // What in a bar cannot be read: words under 4.5:1, icons under 3:1.
  barProblems(selector) {
    const problems = [];
    for (const bar of __j.all(selector).filter((node) => __j.visible(node))) {
      for (const node of [bar, ...bar.querySelectorAll("*")]) {
        if (!__j.visible(node) || node.closest("button:disabled")) continue;
        if (node.localName === "ha-icon") {
          // The stand-in icon fills itself with its colour, so it is
          // measured against what is behind it.
          const ratio = __j.contrast(__j.paint(node, __j.rgba(getComputedStyle(node).color)), __j.backdrop(__j.up(node)));
          if (ratio < 3) problems.push([__j.describe(node), ratio]);
        } else if (this.ownText(node)) {
          const ratio = __j.textContrast(node);
          if (ratio < 4.5) problems.push([__j.describe(node), node.textContent.trim().slice(0, 30), ratio]);
        }
      }
    }
    return problems;
  },
}; true`;

// Steps that share state are in one chain; a failed step skips the rest of
// its chain, since they would only fail for the same reason.
function chains(realConfig) {
  const home = `__j.find('[data-test="home"]')`;
  const editorReady = `__j.find('[data-test="canvas"]') || __j.find('[data-test="page-box"]')`;
  let hitWidth = 0;

  const first = [
    step("01", "home-empty", async (r) => {
      await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
      check((await r.count('[data-test="first-run"]')) === 1, "no first-run block");
      check((await r.count('[data-test="create"]')) === 1, "not exactly one create button");
      check((await r.count('[data-test="dashboard-row"]')) === 0, "dashboard rows shown");
      await checkTextContrast(r, ['[data-test="create"]', '[data-test="open-advanced"]']);
      return r.shot("01-home-empty");
    }),
    step("02", "editor-empty", async (r) => {
      await r.click('[data-test="create"]');
      await r.waitFor(`__j.find('[data-test="add-first-card"]')`, "the empty editor");
      const created = await r.calls("lovelace/dashboards/create");
      check(created.length === 1 && created[0].show_in_sidebar === false, "dashboard not created hidden");
      const tabs = await r.eval(`__j.all('[data-test="page-tab"]').map((tab) => tab.innerText.trim())`);
      check(tabs.length === 1 && tabs[0] === "Home", `page tabs: ${JSON.stringify(tabs)}`);
      await r.waitSaved("new dashboard");
      return r.shot("02-editor-empty");
    }),
    step("03", "picker", async (r) => {
      await r.click('[data-test="add-first-card"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
      const tiles = await r.eval(`__j.all('[data-test="tile"]').map((tile) => tile.dataset.component)`);
      const library = await r.eval(`__apolloFixtures.library.components.map((component) => component.id)`);
      // Every card but the older ones a newer card replaces (I8).
      const offered = await r.eval(`__apolloFixtures.library.components.filter((component) => !component.legacy).map((component) => component.id)`);
      check(tiles.length === OFFERED_CARDS && offered.length === OFFERED_CARDS, `${tiles.length} tiles`);
      check(stable([...tiles].sort()) === stable([...offered].sort()), `the picker offers ${tiles}`);
      check(tiles.every((id) => library.includes(id)), "a tile that is not a TAB-1 card");
      const groups = await r.eval(`__j.all('[data-test="picker-group"]').map((heading) => heading.dataset.group)`);
      const order = groups.map((id) => GROUP_ORDER.indexOf(id));
      check(order.every((value, index) => value >= 0 && (index === 0 || value > order[index - 1])), `groups ${groups}`);
      await sleep(700);
      return r.shot("03-picker");
    }),
    // Search finds a card by its name and description, its group, the
    // question its form asks and the kind of device it controls, matching
    // the start of words. With nothing found it says what it looks at and
    // offers every card again.
    step("04", "picker-search", async (r) => {
      const search = async (text) => {
        await r.eval(`(() => { const input = __j.find('[data-test="picker-search"]'); input.value = "";
          input.dispatchEvent(new Event("input")); input.focus(); return true; })()`);
        await r.type(text);
        await sleep(200);
        return r.eval(`__j.all('[data-test="tile"]').map((tile) => tile.dataset.component).sort()`);
      };
      await r.click('[data-test="picker-search"]');
      const tiles = await search("light");
      const named = await r.eval(`__apolloFixtures.library.components
        .filter((component) => !component.legacy && /\\blight/i.test(component.name + " " + (component.description || "")))
        .map((component) => component.id).sort()`);
      check(named.every((id) => tiles.includes(id)), `"light" finds ${tiles}, not every card named for lights (${named})`);
      check(tiles.includes("apollo/scenes"), `"light" does not find the cards in "Lights and scenes": ${tiles}`);
      check(!tiles.includes("apollo/climate"), `"light" finds the thermostat: ${tiles}`);
      const shot = await r.shot("04-picker-search");
      for (const [word, card] of [
        ["tv", "apollo/media"],
        ["speaker", "apollo/media"],
        ["music", "apollo/media"],
        ["climate", "apollo/climate"],
        ["curtain", "apollo/cover"],
      ]) {
        const found = await search(word);
        check(found.includes(card), `"${word}" finds ${JSON.stringify(found)}, not ${card}`);
      }
      // Not inside words: "each" does not hold "ac".
      const short = await search("ac");
      check(!short.some((id) => ["apollo/scenes", "apollo/people"].includes(id)), `"ac" finds ${short}`);
      check((await search("spotify")).length === 0, "a card matches spotify");
      const none = await r.text('[data-test="picker-none"]');
      check(none.includes('No card matches "spotify".') && none.includes("Try the name of a card or a kind of device"), `the picker says "${none}"`);
      await r.shot("04-picker-search-none");
      await r.click('[data-test="picker-clear-search"]');
      await r.waitFor(`__j.count('[data-test="tile"]') === ${OFFERED_CARDS}`, "every card after Show all cards");
      check((await r.eval(`__j.find('[data-test="picker-search"]').value`)) === "", "the search is not cleared");
      return shot;
    }),
    step("05", "device-step", async (r) => {
      await r.click('[data-test="tile"][data-component="apollo/light"]');
      await r.waitFor(`__j.find('[data-test="entity"]')`, "the device step");
      const options = await r.eval(`__j.all('[data-test="entity"]').map((option) => option.dataset.entity).sort()`);
      const expected = await r.eval(`Object.keys(__apolloMockHass.states)
        .filter((id) => id.startsWith("light.") && !__apolloMockHass.entities[id]?.hidden).sort()`);
      check(stable(options) === stable(expected), `options ${options} instead of ${expected}`);
      const kitchen = await r.text('[data-test="entity"][data-entity="light.kitchen"]');
      check(/Kitchen[\s\S]*Kitchen/.test(kitchen), `the kitchen light does not show its room: ${kitchen}`);
      return r.shot("05-device-step");
    }),
    step("06", "card-added", async (r) => {
      await r.click('[data-test="entity"][data-entity="light.kitchen"]');
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
      await r.waitFor(`__j.count('[data-test="hit"]') === 1`, "one card on the canvas");
      await r.waitFor(`__j.find('[data-test="hit"][aria-pressed="true"]')`, "the card to be selected");
      const title = await r.text('[data-test="side-title"]');
      check(title.includes("Light"), `side panel shows ${title}`);
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1")?.views?.[0]?.sections?.[0]?.cards?.length === 1`,
        "the card to be saved",
      );
      await r.waitSaved("card added");
      const card = (await r.config()).views[0].sections[0].cards[0];
      check(stable(card) === stable(CREATED_CARD), `saved card ${JSON.stringify(card)}`);
      hitWidth = await r.eval(`__j.find('[data-test="hit"]').getBoundingClientRect().width`);
      await checkSelectedCardVisible(r, "after adding the card");
      return r.shot("06-card-added");
    }),
    step("07", "card-styled", async (r) => {
      // The Light card has named sizes, so Width and Height wait behind
      // Fine-tune. Pressed where they are, so the check below sees what the
      // person sees.
      await r.tap('[data-test="size-fine-tune"]');
      await r.waitFor(`__j.find('[data-test="wider"]')`, "the size steps");
      await r.tap('[data-test="wider"]');
      await r.waitFor(
        `(() => { const width = __j.find('[data-test="hit"]').getBoundingClientRect().width;
          return width > ${hitWidth} * 1.8 && width < ${hitWidth} * 2.3; })()`,
        "the card on the canvas to be twice as wide",
      );
      await checkSelectedCardVisible(r, "after Wider");
      await r.click('input[data-focus="look-use-color"]');
      await r.waitFor(
        `(() => { const card = __apolloMockHass.getConfig("tab-1").views[0].sections[0].cards[0];
          return card.grid_options?.columns === 12 && /^#[0-9A-Fa-f]{6}$/.test(card.style?.color || ""); })()`,
        "the new width and colour to be saved",
      );
      await r.waitSaved("styled");
      return r.shot("07-card-styled");
    }),
    step("08", "page-added", async (r) => {
      await leaveEditMode(r);
      await r.click('[data-test="add-page"]');
      await r.waitFor(`__j.active()?.dataset?.test === "page-name"`, "the page name field to get focus");
      const selected = await r.eval(`(() => { const input = __j.active(); return input.selectionStart === 0 && input.selectionEnd === input.value.length && input.value.length > 0; })()`);
      check(selected, "the page name text is not selected");
      await r.type("Bedroom");
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1").views.length === 2 && __apolloMockHass.getConfig("tab-1").views[1].title === "Bedroom"`,
        "the new page to be saved",
      );
      await r.waitSaved("page added");
      const config = await r.config();
      check(/^[a-z0-9_-]{1,32}$/.test(config.views[1].path), `page path ${config.views[1].path}`);
      check(config.views[1].path !== config.views[0].path, "both pages have the same path");
      const tabs = await r.eval(`__j.all('[data-test="page-tab"]').map((tab) => tab.getAttribute("aria-selected"))`);
      check(stable(tabs) === stable(["false", "true"]), `tab selection ${tabs}`);
      check((await r.count('[data-test="add-first-card"]')) === 1, "the new page is not empty");
      return r.shot("08-page-added");
    }),
    step("09", "page-two", async (r) => {
      await r.addCard("add-card", "apollo/fan-speed", "fan.bedroom_main_bedroom_fan");
      await r.waitFor(`__j.count('[data-test="hit"]') === 1`, "the fan on the canvas of page 2");
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1").views[1].sections[0].cards[0]?.component === "apollo/fan-speed"`,
        "the fan to be saved on page 2",
      );
      await r.waitSaved("fan added");
      return r.shot("09-page-two");
    }),
    step("10", "undo-redo", async (r) => {
      await r.click('[data-test="undo"]');
      await r.waitFor(`__j.count('[data-test="hit"]') === 0`, "the canvas to be empty after undo");
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1").views[1].sections[0].cards.length === 0`,
        "the undo to be saved",
      );
      await r.waitSaved("undo");
      await r.click('[data-test="redo"]');
      await r.waitFor(`__j.count('[data-test="hit"]') === 1`, "the card to come back after redo");
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1").views[1].sections[0].cards[0]?.component === "apollo/fan-speed"`,
        "the redo to be saved",
      );
      await r.waitSaved("redo");
      return null;
    }),
    step("11", "undo-toast", async (r) => {
      if (r.setup.device === "phone") {
        // On a phone a press opens the edit mode over the picture, so the
        // card is reached from the keyboard with the edit mode closed.
        await leaveEditMode(r);
        await r.click('[data-test="hit"]');
        await r.waitFor(`__j.find('[data-test="side"][data-mode="edit"]') && __j.find('[data-test="hit"][aria-pressed="true"]')`, "a press to open the edit mode");
        await leaveEditMode(r);
        await r.eval(`__j.find('[data-test="hit"]').focus(); true`);
      } else {
        await r.click('[data-test="hit"]');
      }
      await r.waitFor(`__j.active()?.dataset?.test === "hit"`, "the card to have focus");
      await r.key("Delete");
      await r.waitFor(`__j.count('[data-test="hit"]') === 0`, "the card to be removed");
      await r.waitFor(`__j.find('[data-test="toast-undo"]')`, "a toast with Undo");
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1").views[1].sections[0].cards.length === 0`,
        "the removal to be saved",
      );
      const shot = await r.shot("11-undo-toast");
      await r.click('[data-test="toast-undo"]');
      await r.waitFor(`__j.count('[data-test="hit"]') === 1`, "the card to come back");
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1").views[1].sections[0].cards.length === 1`,
        "the card to be saved again",
      );
      await r.waitSaved("toast undo");
      return shot;
    }),
    step("12", "home-list", async (r) => {
      await r.click('[data-test="back"]');
      await r.waitFor(`${home} && __j.find('[data-test="dashboard-row"]')`, "Home with the dashboard");
      check((await r.count('[data-test="dashboard-row"]')) === 1, "not exactly one dashboard row");
      const row = await r.text('[data-test="dashboard-row"]');
      check(row.includes("Pages: 2"), `row reads ${row}`);
      check((await r.count('[data-test="edit"]')) === 1, "no Edit button");
      await checkTextContrast(r, ['[data-test="edit"]', '[data-test="create"]']);
      return r.shot("12-home-list");
    }),
    // A new dashboard has one empty page. The tablet still gets one screen for
    // it, with its side bar entry, so it never shows a blank wall.
    step("28", "new-dashboard-pages", async (r) => {
      await r.click('[data-test="create"]');
      await r.waitFor(`__j.find('[data-test="add-first-card"]')`, "the second dashboard's empty editor");
      await r.waitSaved("second dashboard");
      await r.click('[data-test="back"]');
      const row = '[data-test="dashboard-row"][data-url-path="tab-1-2"]';
      await r.waitFor(`${home} && __j.find('${row}')`, "Home with both dashboards");
      const screens = await r.eval(`__apolloMockHass.callWS({ type: "apollo_tab/dashboards" })
        .then((result) => result.dashboards.find((entry) => entry.url_path === "tab-1-2").pages)`);
      check(screens === 1, `the stand-in reports ${screens} tablet screens for one empty page`);
      const text = await r.text(row);
      check(text.includes("Pages: 1"), `the new dashboard's row reads ${text}`);
      check((await r.text('[data-test="dashboard-row"][data-url-path="tab-1"]')).includes("Pages: 2"), "first row changed");
      return r.shot("28-new-dashboard-pages");
    }),
  ];

  const real = [
    step("13", "real-before", async (r) => {
      await r.open({ seed: "real", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(`__j.count('[data-test="hit"]') === 1`, "the heading on the canvas");
      await r.waitFor(`__j.find('[data-test="list-row"][data-shown="false"]')`, "the list to know what is shown");
      // One page notice shows; the other two are behind "+2 more".
      await openNotices(r);
      check((await r.count('[data-test="sidebar-notice"]')) === 1, "no sidebar notice");
      check((await r.count('[data-test="columns-notice"]')) === 1, "no columns notice");
      const row = await r.text('[data-test="list-row"][data-shown="false"]');
      check(row.includes(NOT_SHOWN) && row.includes("bubble-card"), `row reads ${row}`);
      const tabs = await r.eval(`__j.all('[data-test="page-tab"]').map((tab) => tab.innerText)`);
      check(tabs.length === 2 && tabs[1].includes(NOT_SHOWN), `tabs ${JSON.stringify(tabs)}`);
      await checkTextContrast(r, [
        '[data-test="add-card"]',
        '[data-test="sidebar-hide"]',
        '[data-test="page-tab"][aria-selected="true"]',
        '[data-test="back"]',
      ]);
      const shot = await r.shot("13-real-before");
      // Looking around changes nothing either: the other page, and a card
      // chosen and let go without a change.
      await r.click('[data-test="page-tab"][data-view="1"]');
      await r.waitFor(`__j.find('[data-test="page-box"]')`, "the old page");
      await r.click('[data-test="page-tab"][data-view="0"]');
      await r.waitFor(`__j.find('[data-test="list-row"][data-shown="false"]')`, "the first page again");
      await r.click('[data-test="list-row"][data-shown="false"]');
      await r.waitFor(`__j.find('[data-test="other-device"]')`, "the card's side panel");
      await r.clearSelection();
      // Well past the 400 ms before a change is saved and the first
      // background try of a kept change after 2 s.
      await sleep(3000);
      check(stable(await r.config()) === stable(realConfig), "opening the editor changed the dashboard");
      check((await r.calls("lovelace/config/save")).length === 0, "opening the editor saved");
      return shot;
    }),
    step("14", "remove-other-card", async (r) => {
      const index = await r.eval(
        `__j.all('li').findIndex((item) => item.querySelector('[data-test="list-row"][data-shown="false"]'))`,
      );
      check(index >= 0, "no row for the card that is not shown");
      await r.click('[data-test="row-remove"]');
      await r.waitFor(
        `!JSON.stringify(__apolloMockHass.getConfig("tab-1")).includes("custom:bubble-card")`,
        "the other card to be removed",
      );
      await r.waitSaved("removed other card");
      const config = await r.config();
      check(config.views[0].sections[0].cards.some((card) => card.type === "heading"), "the heading is gone");
      return null;
    }),
    step("15", "real-old-page", async (r) => {
      await r.click('[data-test="page-tab"][data-view="1"]');
      await r.waitFor(`__j.find('[data-test="page-remove"]')`, "the old preview page box");
      const shot = await r.shot("15-real-old-page");
      await r.click('[data-test="page-remove"]');
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").views.length === 1`, "the page to be removed");
      await r.waitSaved("page removed");
      return shot;
    }),
    step("16", "hide-from-sidebar", async (r) => {
      await openNotices(r);
      await r.click('[data-test="sidebar-hide"]');
      await r.waitFor(`!__j.find('[data-test="sidebar-notice"]')`, "the sidebar notice to go");
      const updates = await r.calls("lovelace/dashboards/update");
      check(updates.some((call) => call.show_in_sidebar === false), "no update with show_in_sidebar false");
      check((await r.eval(`__apolloMockHass.getDashboard("tab-1").show_in_sidebar`)) === false, "still in sidebar");
      return null;
    }),
    step("17", "real-after", async (r) => {
      await openNotices(r);
      await r.click('[data-test="use-whole-screen"]');
      await r.waitFor(
        `(() => { const sections = __apolloMockHass.getConfig("tab-1").views[0].sections;
          return sections.length === 1 && sections[0].column_span === 3; })()`,
        "the page to use the whole screen",
      );
      await r.waitFor(`!__j.find('[data-test="columns-notice"]')`, "the columns notice to go");
      await r.addCard("add-card", "apollo/climate", "climate.hall");
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1").views[0].sections[0].cards.some((card) => card.component === "apollo/climate")`,
        "the thermostat to be saved",
      );
      const index = (await r.config()).views[0].sections[0].cards.findIndex(
        (card) => card.component === "apollo/climate",
      );
      await r.waitFor(`__j.find('[data-test="hit"][data-source="0.0.${index}"]')`, "the thermostat on the canvas");
      await r.waitSaved("thermostat added");
      return r.shot("17-real-after");
    }),
    step("18", "save-error", async (r) => {
      const before = (await r.config()).views[0].sections[0].cards.find(
        (card) => card.component === "apollo/climate",
      ).grid_options.columns;
      // The thermostat has named sizes, so Width and Height wait behind
      // Fine-tune.
      await r.tap('[data-test="size-fine-tune"]');
      await r.waitFor(`__j.find('[data-test="wider"]')`, "the size steps");
      await r.eval(`__apolloMockHass.failSaves(1)`);
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.saveState() === "error"`, "the save state to read error");
      await r.waitFor(`__j.find('[data-test="save-retry"]')`, "the retry button");
      const shot = await r.shot("18-save-error");
      await r.click('[data-test="save-retry"]');
      await r.waitSaved("after retry");
      const after = (await r.config()).views[0].sections[0].cards.find(
        (card) => card.component === "apollo/climate",
      ).grid_options.columns;
      check(after === before + 6, `width ${before} became ${after}`);
      return shot;
    }),
    step("19", "changed-elsewhere", async (r) => {
      await r.clearSelection();
      await r.eval(`(() => { const config = __apolloMockHass.getConfig("tab-1");
        config.apollo_tab = { ...config.apollo_tab, theme: "daylight" };
        __apolloMockHass.externalSave("tab-1", config); })()`);
      await r.waitFor(`__j.find('[data-test="theme"]')?.value === "daylight"`, "the theme select to show Daylight");
      await r.waitFor(`__j.find('[data-test="toast"]')`, "a toast");
      const shot = await r.shot("19-changed-elsewhere");
      await r.click('[data-test="undo"]');
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1").apollo_tab.theme === "midnight"`,
        "the old theme to be saved again",
      );
      await r.waitSaved("undo of the other change");
      return shot;
    }),
    step("20", "conflict", async (r) => {
      const index = (await r.config()).views[0].sections[0].cards.findIndex(
        (card) => card.component === "apollo/climate",
      );
      await r.click(`[data-test="hit"][data-source="0.0.${index}"]`);
      await r.waitFor(`__j.find('[data-test="wider"]') || __j.find('[data-test="size-fine-tune"]')`, "the card form");
      if (!(await r.count('[data-test="wider"]'))) {
        await r.tap('[data-test="size-fine-tune"]');
        await r.waitFor(`__j.find('[data-test="wider"]')`, "the size steps");
      }
      await r.eval(`__apolloMockHass.failSaves(1)`);
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
      await r.eval(`(() => { const config = __apolloMockHass.getConfig("tab-1");
        config.apollo_tab = { ...config.apollo_tab, theme: "warm" };
        __apolloMockHass.externalSave("tab-1", config); })()`);
      await r.waitFor(`__j.find('[data-test="conflict-mine"]')`, "the conflict banner");
      const shot = await r.shot("20-conflict");
      await r.click('[data-test="conflict-mine"]');
      await r.waitSaved("after keeping mine");
      await r.waitFor(`!__j.find('[data-test="conflict-mine"]')`, "the conflict banner to go");
      const draft = await r.draft();
      const saved = await r.config();
      check(stable(saved) === stable(draft), "the saved dashboard is not the editor's version");
      check(saved.apollo_tab.theme === "midnight", `saved theme ${saved.apollo_tab.theme}`);
      // The other version was saved over, but it is still one Undo away.
      await r.click('[data-test="undo"]');
      await r.waitFor(`__j.designer()._history.present.apollo_tab.theme === "warm"`, "Undo to show the other version");
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").apollo_tab.theme === "warm"`, "the other version to be saved");
      await r.waitSaved("other version back");
      await r.click('[data-test="redo"]');
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").apollo_tab.theme === "midnight"`, "Redo to save mine again");
      await r.waitSaved("my version back");
      check(stable(await r.config()) === stable(draft), "Redo did not bring back my version");
      return shot;
    }),
  ];

  const advanced = [
    step("21", "advanced", async (r) => {
      // The screen is there while the cards are still loading; its folder
      // line and the switched-off card come once they have loaded.
      await r.open(
        { seed: "sample", route: "/advanced", community: "1" },
        `__j.find('[data-test="advanced"] .code-line') && __j.find('[data-test="lock-row"][data-component="me/door-lock"]')`,
      );
      const folder = await r.text('[data-test="advanced"] .code-line');
      check(folder.includes("/config/apollo_tab/components"), `folder line ${folder}`);
      const row = await r.text('[data-test="lock-row"][data-component="me/door-lock"]');
      check(row.includes("Door lock") && row.includes("Switched off"), `lock row ${row}`);
      await checkTextContrast(r, [
        '[data-test="allow"][data-component="me/door-lock"]',
        '[data-test="back"]',
        '[data-test="advanced"] a[target="_blank"]',
      ]);
      await r.click('[data-test="allow"][data-component="me/door-lock"]');
      await r.waitFor(
        `__apolloMockHass.calls.some((call) => call.type === "apollo_tab/library/approve" && call.component_id === "me/door-lock" && call.approved === true)`,
        "the approve call",
      );
      await r.waitFor(
        `__j.text('[data-test="lock-row"][data-component="me/door-lock"]').includes("Allowed")`,
        "the card to show as allowed",
      );
      return r.shot("21-advanced");
    }),
  ];

  const keyboard = [
    step(
      "22",
      "keyboard-focus",
      async (r) => {
        await r.open({ seed: "real", route: "/edit/tab-1" }, editorReady);
        await r.waitFor(`__j.count('[data-test="hit"]') === 1`, "the heading on the canvas");
        let reached = false;
        for (let press = 0; press < 40 && !reached; press += 1) {
          await r.key("Tab");
          const focus = await r.eval(`(() => {
            const element = __j.active();
            if (!element || element === document.body) return null;
            const style = getComputedStyle(element);
            return { test: element.dataset.test || element.tagName, outline: style.outlineStyle, shadow: style.boxShadow };
          })()`);
          check(focus, `Tab press ${press + 1} left nothing focused`);
          check(
            focus.outline !== "none" || focus.shadow !== "none",
            `focus on ${focus.test} is not visible`,
          );
          reached = focus.test === "hit";
        }
        check(reached, "Tab never reached the canvas");
        await r.key("Enter");
        await r.waitFor(`__j.find('[data-test="hit"][aria-pressed="true"]')`, "Enter to select the card");
        const shot = await r.shot("22-keyboard-focus");
        await r.key("Escape");
        await r.waitFor(`!__j.find('[data-test="hit"][aria-pressed="true"]')`, "Escape to clear the selection");
        const after = await r.eval(`(() => { const element = __j.active(); const style = getComputedStyle(element);
          return element.dataset.test === "hit" && (style.outlineStyle !== "none" || style.boxShadow !== "none"); })()`);
        check(after, "focus is not visible on the canvas item after Escape");
        return shot;
      },
      { desktopOnly: true },
    ),
  ];

  const pressed = '[data-test="hit"][aria-pressed="true"]';

  const saving = [
    step("23", "leave-while-saving", async (r) => {
      await r.open({ seed: "sample", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(`__j.count('[data-test="hit"]') > 3`, "cards on the canvas");
      await r.eval(`__apolloMockHass.addDashboard("tab-1-2", "Second", ${JSON.stringify(SECOND_CONFIG)}); true`);
      const draft = await editWithSlowSaves(r);
      // Leave the way the sidebar or the browser's Back button does, then
      // open the other dashboard straight away, while both saves are pending.
      await r.eval(`__apolloPanel._go(""); true`);
      const edit = '[data-test="dashboard-row"][data-url-path="tab-1-2"] [data-test="edit"]';
      await r.waitFor(`${home} && __j.find('${edit}')`, "Home with both dashboards");
      await r.click(edit);
      await r.waitFor(editorReady, "the second dashboard's editor");
      await until(
        async () =>
          stable(await r.config("tab-1")) === stable(draft) ||
          stable(await r.config("tab-1-2")) !== stable(SECOND_CONFIG),
        "the saves to finish",
      );
      await sleep(300);
      const saves = await r.eval(`${SAVES}.map((call) => call.url_path)`);
      check(saves.every((url) => url === "tab-1"), `saves went to ${saves.join(", ")}`);
      check(stable(await r.config("tab-1-2")) === stable(SECOND_CONFIG), "the second dashboard was overwritten");
      check(stable(await r.config("tab-1")) === stable(draft), "the first dashboard did not get its last change");
      const title = await r.text(".ed-header h1");
      check(title === "Second", `the editor's title reads ${title}`);
      check(stable(await r.draft()) === stable(SECOND_CONFIG), "the editor does not show the second dashboard");
      check((await r.count('[data-test="toast"]')) === 0, `a toast says ${await r.text('[data-test="toast"]')}`);
      await r.waitSaved("second dashboard");
      await r.eval(`__apolloMockHass.slowSaves(0); true`);
      return r.shot("23-leave-while-saving");
    }),
    step("24", "reopen-while-saving", async (r) => {
      await r.open({ seed: "sample", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(`__j.count('[data-test="hit"]') > 3`, "cards on the canvas");
      const draft = await editWithSlowSaves(r);
      await r.eval(`__apolloPanel._go(""); __apolloPanel._go("/edit/tab-1"); true`);
      await r.waitFor(`(${editorReady}) && __j.count('[data-test="hit"]') > 3`, "the editor to open again");
      await r.waitSaved("reopened");
      check(stable(await r.config()) === stable(draft), "the dashboard did not get the last change");
      check(stable(await r.draft()) === stable(draft), "the editor opened the version before the last change");
      check((await r.count('[data-test="toast"]')) === 0, `a toast says ${await r.text('[data-test="toast"]')}`);
      const steps = await r.eval(`__j.designer()._history.past.length`);
      check(steps === 0, "the editor took its own change for one made somewhere else");
      await r.eval(`__apolloMockHass.slowSaves(0); true`);
      return null;
    }),
  ];

  const selection = [
    step("25", "close-card-form", async (r) => {
      const theme = '[data-test="theme"]';
      await r.open({ seed: "sample", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(`__j.count('[data-test="hit"]') > 3`, "cards on the canvas");
      const source = await r.eval(`__j.all('[data-test="hit"]').map((hit) => hit.dataset.source).find((key) => !key.endsWith(".t"))`);
      const card = `[data-test="hit"][data-source="${source}"]`;

      await r.click(card);
      await r.waitFor(`__j.find('${card}[aria-pressed="true"]')`, "the card to be selected");
      check((await r.count('[data-test="close-panel"]')) === 1, "the card form has no Close button");
      await checkSelectedCardVisible(r, "after pressing the card on the picture");
      const shot = await r.shot("25-close-card-form");
      await r.click('[data-test="close-panel"]');
      await r.waitFor(`!__j.find('${pressed}') && __j.find('${theme}')`, "the dashboard theme after Close");

      if (r.setup.device === "desktop") {
        await r.click(card);
        await r.waitFor(`__j.find('${pressed}')`, "the card to be selected again");
        await r.click(card);
        await r.waitFor(`!__j.find('${pressed}') && __j.find('${theme}')`, "the card to let go when pressed again");

        await r.click(card);
        await r.waitFor(`__j.find('${pressed}')`, "the card to be selected once more");
        const point = await r.eval(`__j.emptyCanvasPoint()`);
        check(point && !point.error, point?.error || "no free point on the picture");
        await r.clickAt(point.x, point.y);
        await r.waitFor(`!__j.find('${pressed}') && __j.find('${theme}')`, "a press beside the cards to clear the selection");
      } else {
        // On a phone the card and the picture around it are under the edit
        // mode: a press where the card is changes nothing, and Done and
        // Escape are the ways out.
        await r.click(card);
        await r.waitFor(`__j.find('${pressed}') && __j.find('[data-test="side"][data-mode="edit"]')`, "the edit mode");
        const place = await r.eval(`(() => { const rect = __j.find('${card}').getBoundingClientRect();
          return { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + rect.height / 2) }; })()`);
        const before = stable(await r.draft());
        await r.clickAt(place.x, place.y);
        await sleep(300);
        check((await r.count(pressed)) === 1 && (await inEditMode(r)), "a press at the card's place under the edit mode let the card go");
        check(stable(await r.draft()) === before, "a press at the card's place under the edit mode changed the dashboard");
        await r.key("Escape");
        await r.waitFor(`!__j.find('${pressed}') && !__j.find('[data-test="side"][data-mode="edit"]') && __j.find('${theme}')`, "Escape to close the edit mode");
        await r.click(card);
        await r.waitFor(`__j.find('${pressed}') && __j.find('[data-test="side"][data-mode="edit"]')`, "the edit mode again");
        await r.click('[data-test="close-panel"]');
        await r.waitFor(`!__j.find('${pressed}') && !__j.find('[data-test="side"][data-mode="edit"]')`, "Done to close the edit mode");
      }

      // On a phone the list is below the picture; choosing a card there
      // opens the edit mode with the card in its strip of the picture.
      await r.click(`[data-test="list-row"][data-source="${source}"]`);
      await r.waitFor(`__j.find('${pressed}')`, "the card to be selected from the list");
      if (r.setup.device === "phone") {
        await checkSelectedCardVisible(r, "after choosing the card in the list");
      }
      return shot;
    }),
    // The picture is drawn for the eye only: screen readers get the named
    // card buttons above it, not the drawn switches and sliders.
    step("30", "canvas-accessibility", async (r) => {
      await r.open({ seed: "sample", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(`__j.count('[data-test="hit"]') > 3`, "cards on the canvas");
      const problems = await canvasAccessibilityProblems(r);
      check(problems.length === 0, `the accessibility tree has ${problems.join("; ")}`);
      const host = await r.eval(`(() => { const host = __j.designer().shadowRoot.querySelector(".page-host");
        return host.getAttribute("aria-hidden") === "true" && host.inert; })()`);
      check(host, "the drawn picture is not hidden from screen readers");
      return null;
    }),
  ];

  // Leaving the editor while the card picker is open closes it, so Add card
  // works again when the editor is opened later.
  const picking = [
    step("29", "picker-after-leaving", async (r) => {
      const picker = `__j.find('dialog[data-test="picker"][open]')`;
      await r.open({ seed: "sample", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(`__j.count('[data-test="hit"]') > 3`, "cards on the canvas");
      await r.click('[data-test="add-card"]');
      await r.waitFor(picker, "the picker");
      await r.eval(`__apolloPanel._go(""); true`);
      const edit = '[data-test="dashboard-row"][data-url-path="tab-1"] [data-test="edit"]';
      await r.waitFor(`${home} && __j.find('${edit}')`, "Home");
      check(!(await r.eval(`Boolean(__j.find('dialog[data-test="picker"]'))`)), "the picker is still there on Home");
      await r.click(edit);
      await r.waitFor(`(${editorReady}) && __j.count('[data-test="hit"]') > 3`, "the editor to open again");
      await r.click('[data-test="add-card"]');
      await r.waitFor(picker, "Add card to open the picker again", 3000);
      await r.click('[data-test="picker-close"]');
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
      return null;
    }),
  ];

  // Between about 871 and 1155 px wide, Home Assistant keeps its sidebar
  // docked while the editor is in its one-column layout. The card sheet must
  // stay inside the panel.
  const midWidth = [
    step(
      "31",
      "mid-width-sheet",
      async (r) => {
        await r.browser.send("Emulation.setDeviceMetricsOverride", {
          width: 1100,
          height: 800,
          deviceScaleFactor: 1,
          mobile: false,
        });
        try {
          await r.open({ seed: "sample", route: "/edit/tab-1" }, editorReady);
          await r.eval(`(() => {
            const bar = document.createElement("div");
            bar.id = "docked-sidebar";
            Object.assign(bar.style, { position: "fixed", top: "0", bottom: "0", left: "0", width: "256px",
              zIndex: "6", background: "#444" });
            document.body.append(bar);
            __apolloPanel.style.marginLeft = "256px";
            return true; })()`);
          await r.waitFor(`__j.designer().shadowRoot.querySelector(".root.compact")`, "the one-column layout");
          await r.waitFor(`__j.count('[data-test="hit"]') > 3`, "cards on the canvas");
          const source = await r.eval(
            `__j.all('[data-test="hit"]').map((hit) => hit.dataset.source).find((key) => !key.endsWith(".t"))`,
          );
          await r.click(`[data-test="list-row"][data-source="${source}"]`);
          await r.waitFor(`__j.find('.side.sheet[data-mode="edit"]')`, "the edit mode");
          const box = await r.eval(`(() => {
            const sheet = __j.find(".side.sheet").getBoundingClientRect();
            const panel = __apolloPanel.getBoundingClientRect();
            return { left: Math.round(sheet.left), right: Math.round(sheet.right), panelLeft: panel.left,
              panelRight: panel.right, at: __j.at(100, 700)?.id || __j.describe(__j.at(100, 700)) };
          })()`);
          check(
            box.left >= box.panelLeft && box.right <= box.panelRight,
            `the sheet spans ${box.left}..${box.right}, the panel ${box.panelLeft}..${box.panelRight}`,
          );
          check(box.at === "docked-sidebar", `the sidebar is covered by ${box.at}`);
          await checkSelectedCardVisible(r, "with the sidebar docked");
          const shot = await r.shot("31-mid-width-sheet");
          await checkNoSidewaysScroll(r, 1100);
          // The sample's light tile is drawn on the page's second screen;
          // choosing it in the list (the edit mode closed first) shows that
          // screen.
          await selectRow(r, "0.1.0");
          await checkSelectedCardVisible(r, "after choosing a card drawn on another screen");
          return shot;
        } finally {
          await r.viewport();
        }
      },
      { desktopOnly: true },
    ),
  ];

  const confirming = [
    step("26", "confirm-dialog", async (r) => {
      const open = `__j.find('dialog[data-test="confirm"][open]')`;
      await r.open({ seed: "sample", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(`__j.find('[data-test="page-delete"]')`, "the page settings");
      await r.click('[data-test="page-delete"]');
      await r.waitFor(open, "the question");
      const look = await r.eval(`(() => {
        const dialog = __j.find('dialog[data-test="confirm"]');
        const cancel = __j.find('[data-test="confirm-cancel"]');
        const ok = __j.find('[data-test="confirm-ok"]');
        const a = cancel.getBoundingClientRect();
        const b = ok.getBoundingClientRect();
        const box = dialog.getBoundingClientRect();
        return {
          background: getComputedStyle(dialog).backgroundColor,
          // The inspector's surface; on a phone it is drawn only as the
          // edit mode, so its colour is read from the element itself.
          card: getComputedStyle(__j.designer().shadowRoot.querySelector('[data-test="side"]')).backgroundColor,
          heights: [a.height, b.height],
          gap: Math.max(b.left - a.right, b.top - a.bottom),
          fits: box.left >= 0 && box.right <= innerWidth,
          focus: __j.active()?.dataset?.test,
          icon: Boolean(ok.querySelector("ha-icon")),
          text: [__j.textContrast(dialog.querySelector("h2")), __j.textContrast(dialog.querySelector("p")),
            __j.textContrast(cancel), __j.textContrast(ok)],
        };
      })()`);
      check(look.background === look.card, `the question is drawn in ${look.background}, not the card colour ${look.card}`);
      // 40 px with a mouse, 44 on a phone: the dialog is centred on the
      // window, so the window's width decides.
      const tall = r.setup.device === "phone" ? 44 : 40;
      check(look.heights.every((height) => height >= tall), `its buttons are ${look.heights.join(" and ")} px high`);
      check(look.gap >= 8, `its buttons are ${look.gap} px apart`);
      check(look.fits, "the question does not fit the screen");
      check(look.focus === "confirm-cancel", `focus starts on ${look.focus}`);
      check(look.icon, "the delete button has no icon");
      check(look.text.every((ratio) => ratio >= 4.5), `text contrast ${look.text.join(", ")}`);
      const shot = await r.shot("26-confirm-dialog");
      await r.key("Escape");
      await r.waitFor(`!__j.find('dialog[data-test="confirm"]')`, "Escape to close the question");
      check((await r.config()).views.length === 2, "Escape deleted the page");
      await r.click('[data-test="page-delete"]');
      await r.waitFor(open, "the question again");
      await r.click('[data-test="confirm-ok"]');
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").views.length === 1`, "the page to be deleted");
      await r.waitSaved("page deleted");
      return shot;
    }),
  ];

  const contrast = [
    step("27", "error-text-contrast", async (r) => {
      await r.open({ seed: "real", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(
        `__j.find('[data-test="page-name"]') && (__j.find('[data-test="sidebar-notice"]') || __j.find('[data-test="notices-more"]'))`,
        "the editor",
      );
      await openNotices(r);
      await r.waitFor(`__j.find('[data-test="sidebar-notice"]')`, "the sidebar notice");
      const edges = await r.eval(`['[data-test="page-name"]', '[data-test="dashboard-name"]', '[data-test="theme"]']
        .map((selector) => [selector, __j.edgeContrast(__j.find(selector))])`);
      for (const [selector, ratio] of edges) {
        check(ratio >= 3, `the edge of ${selector} has contrast ${ratio}`);
      }
      await r.eval(`__apolloMockHass.failCalls("lovelace/dashboards/update", 1); true`);
      await r.click('[data-test="sidebar-hide"]');
      const failure = '[data-test="sidebar-notice"] .alert';
      await r.waitFor(`__j.find('${failure}')?.textContent`, "the failure line");
      const alert = await r.eval(`__j.textContrast(__j.find('${failure}'))`);
      check(alert >= 4.5, `the failure line has contrast ${alert}`);
      await r.eval(`__apolloMockHass.failSaves(1); true`);
      await r.click('[data-test="page-name"]');
      await r.type("!");
      await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
      await r.waitFor(`__j.find('.banner.error p')`, "the save error banner");
      const state = await r.eval(`__j.textContrast(__j.find('[data-test="save-state"]'))`);
      const banner = await r.eval(`__j.textContrast(__j.find('.banner.error p'))`);
      check(state >= 4.5, `"Not saved" has contrast ${state}`);
      check(banner >= 4.5, `the save error text has contrast ${banner}`);
      const shot = await r.shot("27-error-text-contrast");
      await r.click('[data-test="save-retry"]');
      await r.waitSaved("after retry");
      return shot;
    }),
  ];

  // Another browser saves while one of the editor's own saves is still on
  // its way. Whichever button answers the conflict, Home Assistant has to
  // end with the version the editor then shows.
  const startRace = async (r) => {
    await r.open({ seed: "sample", route: "/edit/tab-1" }, editorReady);
    await r.waitFor(`__j.count('[data-test="hit"]') > 3`, "cards on the canvas");
    await r.click('[data-test="list-row"][data-source="0.1.0"]');
    await r.waitFor(`__j.find('[data-test="wider"]')`, "the card form");
    await r.eval(`__apolloMockHass.slowSaves(1500); true`);
    await r.click('[data-test="wider"]');
    await r.waitFor(`${SAVES}.length === 1`, "the first save to be sent", 3000);
    await r.eval(`(() => { const config = __apolloMockHass.getConfig("tab-1");
      config.apollo_tab = { ...config.apollo_tab, theme: "warm" };
      __apolloMockHass.externalSave("tab-1", config); })()`);
    await r.waitFor(`__j.find('[data-test="conflict-theirs"]')`, "the conflict banner");
  };
  const endRace = async (r, theme) => {
    await r.waitSaved("after the conflict");
    // Late answers and their echoes must not change anything any more.
    await sleep(2000);
    check((await r.eval(`__j.saveState()`)) === "saved", "the editor is not saved after the answers came back");
    check((await r.count('[data-test="conflict-mine"]')) === 0, "a second conflict banner appeared");
    const draft = await r.draft();
    const stored = await r.config();
    check(draft.apollo_tab.theme === theme, `the editor shows theme ${draft.apollo_tab.theme}`);
    check(
      stable(stored) === stable(draft),
      `the editor shows theme ${draft.apollo_tab.theme} but Home Assistant stores ${stored.apollo_tab.theme}`,
    );
    return draft;
  };
  const racing = [
    step("32", "theirs-while-saving", async (r) => {
      await startRace(r);
      const shot = await r.shot("32-theirs-while-saving");
      await r.click('[data-test="conflict-theirs"]');
      await endRace(r, "warm");
      return shot;
    }),
    step("33", "theirs-after-save-landed", async (r) => {
      await startRace(r);
      // The editor's own slow save lands after the other one.
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").apollo_tab.theme === "midnight"`, "the slow save to land");
      await r.click('[data-test="conflict-theirs"]');
      await endRace(r, "warm");
      return null;
    }),
    step("34", "mine-while-saving", async (r) => {
      await startRace(r);
      await r.click('[data-test="taller"]');
      await r.click('[data-test="conflict-mine"]');
      const draft = await endRace(r, "midnight");
      const size = draft.views[0].sections[1].cards[0].grid_options;
      check(size.columns === 12 && size.rows === 6, `the card ended as ${JSON.stringify(size)}`);
      // The other version is still one Undo away.
      await r.click('[data-test="undo"]');
      await r.waitFor(`__j.designer()._history.present.apollo_tab.theme === "warm"`, "Undo to show the other version");
      await r.waitSaved("after Undo");
      return null;
    }),
  ];

  // A dashboard kept in a YAML file opens read-only in the panel itself.
  const yaml = [
    step("35", "yaml-dashboard", async (r) => {
      await r.open({ seed: "sample" }, home);
      await r.eval(`(async () => {
        __apolloMockHass.addYamlDashboard("yaml-tab", "From a file", __apolloMockHass.getConfig("tab-1"));
        await __apolloPanel._refresh();
        return true; })()`);
      const row = '[data-test="dashboard-row"][data-url-path="yaml-tab"]';
      // The "not shown" count is drawn a moment later and moves the button.
      await r.waitFor(`__j.find('${row} [data-test="view"]') && __j.find('${row} [data-test="row-not-shown"]')`, "the YAML dashboard's row");
      check((await r.count(`${row} [data-test="edit"]`)) === 0, "a YAML dashboard has an Edit button");
      await r.click(`${row} [data-test="view"]`);
      await r.waitFor(editorReady, "the read-only view");
      await r.waitFor(`__j.find(".banner")`, "the read-only banner");
      const where = await r.eval(`location.pathname`);
      check(where.endsWith("/edit/yaml-tab"), `"Look at it" went to ${where}`);
      const banner = await r.text(".banner");
      check(banner.includes("YAML file"), `the banner reads "${banner}"`);
      for (const control of ["add-card", "add-page", "undo", "theme"]) {
        check((await r.count(`[data-test="${control}"]`)) === 0, `a YAML dashboard shows ${control}`);
      }
      check((await r.calls("lovelace/config/save")).length === 0, "looking at a YAML dashboard saved something");
      return r.shot("35-yaml-dashboard");
    }),
  ];

  // The picture is drawn with the tablet's styles only. Everything drawn
  // has to look as it does in a copy that sits outside the panel, where
  // neither the editor's control styles nor its text settings can reach it,
  // the way the standalone renderer draws it.
  const picture = [
    step("36", "canvas-styles", async (r) => {
      await r.open({ seed: "sample", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(`__j.count('[data-test="hit"]') > 3`, "cards on the canvas");
      await r.waitFor(`__j.designer().shadowRoot.querySelector(".page-host").shadowRoot.querySelector(".at-page button")`, "drawn buttons");
      const result = await r.eval(`(async () => {
        const { rendererStyles } = await import("/custom_components/apollo_tab/frontend/styles.js");
        const frame = __j.designer().shadowRoot.querySelector(".page-host");
        const drawn = frame.shadowRoot.querySelector(".at-page");
        // Straight in the document, off the left edge: only the page's own
        // defaults reach it, as they reach a card on a dashboard.
        const box = document.createElement("div");
        Object.assign(box.style, { position: "fixed", top: "0", left: "-20000px" });
        const root = box.attachShadow({ mode: "open" });
        const style = document.createElement("style");
        style.textContent = rendererStyles;
        const holder = document.createElement("div");
        Object.assign(holder.style, { position: "relative", width: drawn.style.width, height: drawn.style.height });
        holder.append(drawn.cloneNode(true));
        root.append(style, holder);
        document.body.append(box);
        // Box and control styles, and every text setting a page passes down.
        const properties = ["display", "width", "height", "minHeight", "maxWidth", "paddingTop", "paddingRight",
          "paddingBottom", "paddingLeft", "opacity", "cursor", "color", "backgroundColor", "borderTopWidth",
          "borderTopLeftRadius", "fontSize", "fontFamily", "fontWeight", "fontStyle", "lineHeight",
          "letterSpacing", "wordSpacing", "textTransform", "textAlign", "textIndent", "whiteSpace",
          "overflowWrap", "wordBreak", "hyphens", "direction"];
        // The editor's own marks for cards that are left out are not part
        // of the tablet's drawing.
        const parts = (page) => [page, ...page.querySelectorAll("*")].filter((node) => !node.closest(".warning-box"));
        const mine = parts(drawn);
        const theirs = parts(holder.firstElementChild);
        const differences = [];
        mine.forEach((node, index) => {
          const a = getComputedStyle(node);
          const b = getComputedStyle(theirs[index]);
          for (const property of properties) {
            if (a[property] !== b[property]) {
              differences.push(node.tagName.toLowerCase() + "." + String(node.className?.baseVal ?? node.className).split(" ").join(".") +
                " " + property + ": " + a[property] + " instead of " + b[property]);
            }
          }
        });
        const buttons = [...drawn.querySelectorAll("button")];
        const faded = buttons.filter((button) => getComputedStyle(button).opacity !== "1").length;
        box.remove();
        return { nodes: mine.length, copies: theirs.length, buttons: buttons.length,
          differences: [...new Set(differences)], faded }; })()`);
      check(result.buttons > 0, "no drawn buttons to compare");
      check(result.nodes > 0 && result.nodes === result.copies, `compared ${result.nodes} drawn parts with ${result.copies}`);
      check(result.differences.length === 0, `the picture differs from the tablet's drawing: ${result.differences.slice(0, 6).join("; ")}`);
      check(result.faded === 0, `${result.faded} drawn buttons are faded`);
      await r.eval(`__j.find('[data-test="canvas"]').scrollIntoView({ block: "start" }); true`);
      return r.shot("36-canvas-styles");
    }),
  ];

  // A card that wants two devices of one kind names each field after what
  // it is for.
  const fields = [
    step("37", "same-kind-fields", async (r) => {
      const labels = (scope) => r.eval(`__j.all('${scope} [data-param$="_sensor"]')
        .filter((field) => __j.visible(field))
        .map((field) => ({
          label: field.querySelector(".field-label")?.textContent || "",
          list: field.querySelector('[role="listbox"]')?.getAttribute("aria-label") || null,
          button: field.querySelector('[data-test="change-device"]')?.getAttribute("aria-label") || null,
        }))
        .filter((field) => field.list !== null || field.button !== null)`);
      const distinct = (values, what) => {
        check(values.length === 2, `${what}: ${JSON.stringify(values)}`);
        check(new Set(values).size === 2, `two fields share the ${what} "${values[0]}"`);
      };

      await r.open({ seed: "sample", route: "/edit/tab-1" }, editorReady);
      await r.click('[data-test="add-card"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
      await r.click('[data-test="tile"][data-component="apollo/room"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"] [data-param="temperature_sensor"]')`, "the device step");
      const inPicker = await labels('dialog[data-test="picker"]');
      distinct(inPicker.map((field) => field.label), "label");
      distinct(inPicker.map((field) => field.list), "list name");
      check(
        stable(inPicker.map((field) => field.label).sort()) === stable(["Humidity sensor", "Temperature sensor"]),
        `the fields are labelled ${JSON.stringify(inPicker.map((field) => field.label))}`,
      );
      const shot = await r.shot("37-same-kind-fields");

      await r.click('[data-test="pick-skip"]');
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
      await r.waitFor(`__j.find('[data-test="change-device"]')`, "the card form");
      const inForm = await labels(".side");
      distinct(inForm.map((field) => field.label), "label");
      distinct(inForm.map((field) => field.button), "button name");
      // Nothing is chosen yet, so the button says Choose, not Change.
      const words = await r.eval(`__j.all('.side [data-test="change-device"]').map((button) => button.textContent)`);
      check(words.length >= 2 && words.every((text) => text === "Choose"), `the device buttons read ${JSON.stringify(words)}`);
      check(inForm.every((field) => field.button.startsWith("Choose: ")), `the device buttons are named ${JSON.stringify(inForm)}`);
      await r.waitSaved("card added");
      return shot;
    }),
  ];

  // The side form keeps showing the card the person chose when the cards
  // around it move: after Undo and Redo, Undo in the toast, a change from
  // another browser, and "Use the other version".
  const following = [
    step("38", "selection-after-undo", async (r) => {
      await openSample(r);
      await selectRow(r, "0.1.0");
      await expectSelected(r, "Light tile", "0.1.0", "after choosing the light tile");
      await r.click('[data-test="move-later"]');
      await expectSelected(r, "Light tile", "0.1.1", "after Move later");
      await r.click('[data-test="undo"]');
      await expectSelected(r, "Light tile", "0.1.0", "after Undo");
      const shot = await r.shot("38-selection-after-undo");
      await r.click('[data-test="redo"]');
      await expectSelected(r, "Light tile", "0.1.1", "after Redo");
      await r.waitSaved("after Redo");
      return shot;
    }),
    step("39", "selection-after-toast-undo", async (r) => {
      await openSample(r);
      await selectRow(r, "0.1.0");
      await r.click('[data-test="remove-card"]');
      await r.waitFor(`__j.find('[data-test="toast-undo"]')`, "a toast with Undo");
      await selectRow(r, "0.1.1");
      await expectSelected(r, "Fan", "0.1.1", "after choosing the fan");
      await r.click('[data-test="toast-undo"]');
      await expectSelected(r, "Fan", "0.1.2", "after Undo in the toast");
      const shot = await r.shot("39-selection-after-toast-undo");
      await r.waitSaved("after Undo in the toast");
      // Remove acts on the card the form shows.
      await r.click('[data-test="remove-card"]');
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1").views[0].sections[1].cards.length === 4`,
        "the removal to be saved",
      );
      await r.waitSaved("after removing the fan");
      const kinds = (await r.config()).views[0].sections[1].cards.map((card) => card.component || card.type);
      const expected = ["apollo/light-tile", "apollo/light-slider", "apollo/sensor-value", "tile"];
      check(stable(kinds) === stable(expected), `Remove left ${kinds.join(", ")}`);
      return shot;
    }),
    step("40", "selection-after-other-browser", async (r) => {
      await openSample(r);
      await selectRow(r, "0.1.2");
      await expectSelected(r, "Fan", "0.1.2", "after choosing the fan");
      await saveElsewhere(r, `(config) => config.views[0].sections[1].cards.splice(0, 1)`);
      await r.waitFor(`__j.find('[data-test="toast"]')`, "the toast about the other change");
      await expectSelected(r, "Fan", "0.1.1", "after another browser removed a card before the fan");
      const shot = await r.shot("40-selection-after-other-browser");
      await saveElsewhere(r, `(config) => config.views[0].sections[1].cards.splice(1, 1)`);
      await r.waitFor(
        `!__j.designer()._selected && !__j.find('${pressed}') && __j.find('[data-test="theme"]')`,
        "the selection to clear once another browser removed the fan",
      );
      check((await r.count('[data-test="side-title"]')) === 0, `the form shows ${await r.text('[data-test="side-title"]')}`);
      return shot;
    }),
    step("41", "selection-after-other-version", async (r) => {
      await openSample(r);
      await selectRow(r, "0.1.0");
      await r.eval(`__apolloMockHass.failSaves(1); true`);
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
      await selectRow(r, "0.1.2");
      await expectSelected(r, "Fan", "0.1.2", "after choosing the fan");
      const theirs = await saveElsewhere(
        r,
        `(config) => { config.views[0].sections[1].cards.splice(0, 1);
          config.apollo_tab = { ...config.apollo_tab, theme: "warm" }; }`,
      );
      await r.waitFor(`__j.find('[data-test="conflict-theirs"]')`, "the conflict banner");
      await r.click('[data-test="conflict-theirs"]');
      await r.waitSaved("after Use the other version");
      await expectSelected(r, "Fan", "0.1.1", "after Use the other version");
      check(stable(await r.draft()) === stable(theirs), "Use the other version does not show the other version");
      check(stable(await r.config()) === stable(theirs), "Use the other version left Home Assistant with another version");
      await r.eval(`__apolloMockHass.failSaves(0); true`);
      return r.shot("41-selection-after-other-version");
    }),
  ];

  // A card that is switched off under Advanced cannot be picked.
  const locked = [
    step("42", "locked-card", async (r) => {
      const tile = '[data-test="tile"][data-component="me/door-lock"]';
      await openSample(r, { community: "1" });
      await r.click('[data-test="add-card"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"][open]') && __j.find('${tile}')`, "the switched-off card");
      check((await r.text(tile)).includes("Switched off"), `the tile reads ${await r.text(tile)}`);
      await r.click(tile);
      await sleep(300);
      check((await r.count('[data-test="picker-search"]')) === 1, "pressing the switched-off card left the card list");
      check((await r.count('[data-test="entity-search"]')) === 0, "pressing the switched-off card asked for a device");
      // Disabled, so the keyboard and screen readers pass it by as well.
      check(await r.eval(`__j.find('${tile}').disabled === true`), "the switched-off card's tile takes presses");
      const shot = await r.shot("42-locked-card");
      await r.click('[data-test="picker-close"]');
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
      check((await r.calls("lovelace/config/save")).length === 0, "pressing the switched-off card saved something");
      check(!JSON.stringify(await r.config()).includes("me/door-lock"), "the switched-off card was added");
      return shot;
    }),
  ];

  // The picker stops watching its example cards once they are gone, and on
  // a phone the device step does not bring up the keyboard by itself.
  const previews = [
    step("43", "picker-previews-stop", async (r) => {
      await openSample(r);
      await r.eval(`(() => {
        // Keeps the watchers put on the example cards' drawings while they run.
        window.__watching = new Set();
        const { observe, disconnect } = MutationObserver.prototype;
        MutationObserver.prototype.observe = function (target, options) {
          if (target instanceof ShadowRoot && target.host.closest(".tile-preview")) window.__watching.add(this);
          return observe.call(this, target, options);
        };
        MutationObserver.prototype.disconnect = function () {
          window.__watching.delete(this);
          return disconnect.call(this);
        };
        return true; })()`);
      const watching = () => r.eval(`window.__watching.size`);
      await r.click('[data-test="add-card"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
      await r.waitFor(`window.__watching.size > 0`, "example cards in the picker");
      await r.click('[data-test="picker-close"]');
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
      check((await watching()) === 0, `${await watching()} example cards are still watched after Close`);

      await r.click('[data-test="add-card"]');
      await r.waitFor(`window.__watching.size > 0`, "example cards in the picker again");
      await r.click('[data-test="tile"][data-component="apollo/light"]');
      await r.waitFor(`__j.find('[data-test="entity-search"]')`, "the device step");
      await sleep(200);
      check((await watching()) === 0, `${await watching()} example cards are still watched on the device step`);
      const focus = await focused(r);
      if (r.setup.device === "phone") {
        check(focus !== "entity-search", "on a phone the device search takes focus and brings up the keyboard");
        check(focus === "pick-back", `on a phone the device step starts with focus on ${focus}`);
      } else {
        check(focus === "entity-search", `the device step starts with focus on ${focus}`);
      }
      const shot = await r.shot("43-picker-previews-stop");
      await r.click('[data-test="picker-close"]');
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
      return shot;
    }),
  ];

  // A control pressed from the keyboard that can go no further hands focus
  // to the nearest control that still works.
  const focusing = [
    step(
      "44",
      "focus-at-limits",
      async (r) => {
        await openSample(r);
        await selectRow(r, "0.1.0");
        await pressToLimit(r, "wider", "narrower");
        await pressToLimit(r, "taller", "shorter");
        await r.clearSelection();
        await pressToLimit(r, "page-right", "page-left");
        check((await r.draft()).views[1].title === "Home", "Move page right did not move the page");
        check(await r.count('[data-test="screen-next"]'), "the page has no second screen");
        await pressToLimit(r, "screen-next", "screen-prev");
        await pressToLimit(r, "undo", "redo");
        await r.waitSaved("after undoing everything");
        // An answered banner is gone; focus goes on to the page tabs.
        await r.eval(`__apolloMockHass.failSaves(1); true`);
        await r.click('[data-test="page-name"]');
        await r.type("!");
        await r.waitFor(`__j.find('[data-test="save-retry"]')`, "the save to fail");
        await r.eval(`__j.find('[data-test="save-retry"]').focus(); true`);
        await r.key("Enter");
        await r.waitSaved("after Retry");
        await sleep(150);
        const now = await focused(r);
        check(now === "page-tab", `after Retry focus went to ${now}, not the page tabs`);
        return r.shot("44-focus-at-limits");
      },
      { desktopOnly: true },
    ),
  ];

  // Home Assistant's menu button is always there for it to show when the
  // sidebar is out of reach; while it draws nothing, the header starts
  // where it would without it.
  const menu = [
    step("45", "menu-button", async (r) => {
      const layout = (header) => r.eval(`(() => {
        const header = __j.find(${JSON.stringify(header)});
        const menu = header && header.querySelector(":scope > ha-menu-button");
        if (!menu) return null;
        const next = menu.nextElementSibling.getBoundingClientRect();
        const own = menu.getBoundingClientRect();
        const box = header.getBoundingClientRect();
        return {
          width: Math.round(own.width),
          right: Math.round(own.right),
          next: Math.round(next.left),
          start: Math.round(box.left + parseFloat(getComputedStyle(header).paddingLeft)),
          narrow: menu.narrow,
          hass: menu.hass === __apolloMockHass,
        };
      })()`);
      const sidebar = (mode) =>
        r.eval(`__apolloMockHass.dockedSidebar = ${JSON.stringify(mode)};
          __apolloPanel.hass = __apolloMockHass; true`);
      const phone = r.setup.device === "phone";
      const checkHeader = async (header, where) => {
        const hidden = await layout(header);
        check(hidden, `${where} has no menu button`);
        check(hidden.hass && hidden.narrow === phone, `${where}: the menu button got ${JSON.stringify(hidden)}`);
        if (phone) {
          check(hidden.width === 48, `${where}: the menu button is ${hidden.width} px wide on a phone`);
          check(hidden.next >= hidden.right, `${where}: the menu button overlaps what follows it`);
          return;
        }
        check(hidden.width === 0, `${where}: the menu button takes ${hidden.width} px with the sidebar docked`);
        check(Math.abs(hidden.next - hidden.start) <= 1, `${where} starts at ${hidden.next}, not ${hidden.start}`);
        await sidebar("always_hidden");
        const shown = await layout(header);
        check(shown.width === 48, `${where}: the menu button is ${shown.width} px wide with the sidebar hidden`);
        check(shown.next >= shown.right, `${where}: the menu button overlaps what follows it`);
        await sidebar("docked");
      };
      try {
        await r.open({ seed: "sample" }, `__j.find('[data-test="home"]')`);
        await checkHeader(".panel-header", "Home");
        await r.waitFor(`__j.find('[data-test="dashboard-row"][data-url-path="tab-1"] [data-test="edit"]')`, "the list");
        await r.click('[data-test="dashboard-row"][data-url-path="tab-1"] [data-test="edit"]');
        await r.waitFor(`__j.find(".ed-header [data-test='back']") && __j.count('[data-test="hit"]') > 3`, "the editor");
        await checkHeader(".ed-header", "the editor");
        await sidebar("always_hidden");
        return await r.shot("45-menu-button");
      } finally {
        await sidebar("docked");
      }
    }),
  ];

  // Leaving through Home Assistant's sidebar while a change is not saved
  // keeps the change. It is saved in the background when that is safe, and
  // offered with the conflict banner when the dashboard was changed
  // somewhere else.
  const leaving = [
    step("46", "leave-after-failed-save", async (r) => {
      await openSample(r);
      const before = await r.config();
      await selectRow(r, "0.1.0");
      await r.eval(`__apolloMockHass.failSaves(100); true`);
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
      const mine = await r.draft();
      await leaveThroughSidebar(r);
      check(await leavingAsks(r), "closing the browser page would not ask about the unsaved change");
      check(stable(await r.config()) === stable(before), "a save went through while saves fail");
      await r.eval(`__apolloMockHass.failSaves(0); true`);
      await until(async () => stable(await r.config()) === stable(mine), "the change to be saved in the background", 15000);
      check(!(await leavingAsks(r)), "closing the browser page still asks after the change was saved");
      await reopenEditor(r);
      await r.waitSaved("opened again");
      check((await r.count('[data-test="conflict-mine"]')) === 0, "the editor asks to choose a version");
      check(stable(await r.draft()) === stable(mine), "the editor does not show the saved change");
      return r.shot("46-leave-after-failed-save");
    }),
    step("47", "changed-while-away", async (r) => {
      await openSample(r);
      await selectRow(r, "0.1.0");
      await r.eval(`__apolloMockHass.failSaves(100); true`);
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
      const mine = await r.draft();
      await leaveThroughSidebar(r);
      const theirs = await saveElsewhere(r, `(config) => { config.apollo_tab = { ...config.apollo_tab, theme: "warm" }; }`);
      await r.eval(`__apolloMockHass.failSaves(0); true`);
      // The first background retry comes after 2 s.
      await sleep(3500);
      check(stable(await r.config()) === stable(theirs), "the kept change was saved over the other version");
      check(await leavingAsks(r), "closing the browser page would not ask about the kept change");
      await reopenEditor(r);
      await r.waitFor(`__j.find('[data-test="conflict-theirs"]')`, "the banner offering the kept change");
      check(stable(await r.draft()) === stable(mine), "the editor does not show the kept change");
      check(stable(await r.config()) === stable(theirs), "opening the editor saved over the other version");
      const shot = await r.shot("47-changed-while-away");
      await r.click('[data-test="conflict-theirs"]');
      await r.waitSaved("after Use the other version");
      check(stable(await r.draft()) === stable(theirs), "the editor does not show the other version");
      check(stable(await r.config()) === stable(theirs), "Home Assistant does not hold the other version");
      check(!(await leavingAsks(r)), "closing the browser page still asks after the choice");
      return shot;
    }),
    step("48", "leave-during-conflict", async (r) => {
      await openSample(r);
      await selectRow(r, "0.1.0");
      await r.eval(`__apolloMockHass.failSaves(1); true`);
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
      const mine = await r.draft();
      const theirs = await saveElsewhere(r, `(config) => { config.views[1].title = "Elsewhere"; }`);
      await r.waitFor(`__j.find('[data-test="conflict-mine"]')`, "the conflict banner");
      await leaveThroughSidebar(r);
      await sleep(2500);
      check(stable(await r.config()) === stable(theirs), "leaving saved over the other version");
      check(await leavingAsks(r), "closing the browser page would not ask about the open choice");
      await reopenEditor(r);
      await r.waitFor(`__j.find('[data-test="conflict-mine"]')`, "the conflict banner again");
      check(stable(await r.draft()) === stable(mine), "the editor does not show the kept change");
      await r.click('[data-test="conflict-mine"]');
      await r.waitSaved("after Keep my version");
      check(stable(await r.config()) === stable(mine), "Keep my version did not save the kept change");
      check(!(await leavingAsks(r)), "closing the browser page still asks after the choice");
      // The other version is one Undo away.
      await r.click('[data-test="undo"]');
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").views[1].title === "Elsewhere"`, "Undo to save the other version");
      await r.waitSaved("after Undo");
      return null;
    }),
    step("49", "leave-after-own-save-landed", async (r) => {
      const { theirs } = await leaveAfterOwnSaveLanded(r);
      await r.click('[data-test="conflict-theirs"]');
      await r.waitSaved("after Use the other version");
      check(stable(await r.draft()) === stable(theirs), "the editor does not show the other version");
      check(stable(await r.config()) === stable(theirs), "Home Assistant does not hold the other version");
      check(!(await leavingAsks(r)), "closing the browser page still asks after the choice");
      return r.shot("49-leave-after-own-save-landed");
    }),
    // Keep my version then saves over the editor's own landed save without
    // asking a second time.
    step("60", "keep-mine-after-own-save-landed", async (r) => {
      const { theirs, mine } = await leaveAfterOwnSaveLanded(r);
      await r.click('[data-test="conflict-mine"]');
      await r.waitSaved("after Keep my version");
      await sleep(500);
      check((await r.count('[data-test="conflict-mine"]')) === 0, "Keep my version asked a second time");
      check(stable(await r.config()) === stable(mine), "Keep my version did not save the kept change");
      check(!(await leavingAsks(r)), "closing the browser page still asks after the choice");
      // The other version is one Undo away.
      await r.click('[data-test="undo"]');
      await r.waitFor(`__j.designer()._history.present.views[1].title === "Elsewhere"`, "Undo to show the other version");
      await r.waitSaved("after Undo");
      check(stable(await r.config()) === stable(theirs), "Undo did not save the other version");
      return r.shot("60-keep-mine-after-own-save-landed");
    }),
  ];

  // Long names: a 40-character page name (the most the page name field
  // takes) and a long theme name, as a theme added later might have. No
  // field or button may push past the side panel, the phone sheet or the
  // picker, and a page tab stays a sensible width.
  const longNames = [
    step("50", "long-names", async (r) => {
      check(LONG_PAGE.length === 40, "the long page name is not 40 characters");
      await r.open({ seed: "none" }, home);
      await r.eval(`(async () => {
        const mock = __apolloMockHass;
        const original = mock.callWS.bind(mock);
        mock.callWS = async (message) => {
          const result = await original(message);
          if (message.type === "apollo_tab/library") {
            result.themes.find((theme) => theme.id === "warm").name = ${JSON.stringify(LONG_THEME)};
          }
          return result;
        };
        mock.addDashboard("rooms-1", "Rooms upstairs and downstairs, the guest wing, the garden house, the garage and the cellar under the old barn", ${JSON.stringify(LONG_NAMES_CONFIG)});
        await __apolloPanel._refresh();
        return true; })()`);
      await r.click('[data-test="dashboard-row"][data-url-path="rooms-1"] [data-test="edit"]');
      await r.waitFor(`__j.find('[data-test="list-row"][data-source="0.0.0"]') && __j.find('[data-test="theme"]')`, "the editor");
      const theme = await r.eval(`__j.find('[data-test="theme"]').selectedOptions[0].textContent`);
      check(theme === LONG_THEME, `the dashboard theme reads "${theme}"`);
      // A long dashboard name gives way first in the top bar: it is cut,
      // and the tablet line keeps its first words (polish decision 12).
      const bar = await r.eval(`(() => { const d = __j.designer().shadowRoot; const title = d.querySelector(".ed-header h1");
        const lines = d.querySelector(".ed-header .tablet-lines"); const block = d.querySelector(".title-block");
        return { cut: title.scrollWidth > title.clientWidth, lines: lines && lines.textContent && lines.getClientRects().length
          ? lines.getBoundingClientRect().width : null, block: block.getBoundingClientRect().width }; })()`);
      check(bar.cut, `the long dashboard name is not cut in the top bar: ${JSON.stringify(bar)}`);
      check(bar.lines === null || bar.lines >= Math.min(168, bar.block * 0.4) - 1, `the tablet line is squeezed by the long name: ${JSON.stringify(bar)}`);
      await r.eval(`__j.find('[data-test="theme"]').scrollIntoView({ block: "center" }); true`);
      // On a phone the settings are in the page column, in the idle holder.
      const holder = r.setup.device === "phone" ? "idle" : "side";
      const settings = await r.eval(`__j.overflowProblems(__j.find('[data-test="${holder}"]'))`);
      check(settings.length === 0, `page and dashboard settings: ${settings.join("; ")}`);
      const shot = await r.shot("50-long-names");

      // The long page's tab is cut short, and keeps its whole name for
      // screen readers and in its tooltip.
      const tab = await r.eval(`(() => {
        const tab = __j.find('[data-test="page-tab"][data-view="1"]');
        const name = tab.querySelector(".tab-name");
        const rect = tab.getBoundingClientRect();
        return { width: Math.round(rect.width), right: Math.round(rect.right), title: tab.title,
          cut: name.scrollWidth > name.clientWidth, text: tab.textContent, label: tab.getAttribute("aria-label") };
      })()`);
      check(tab.width <= 300, `the long page's tab is ${tab.width} px wide`);
      check(tab.width <= r.setup.width - 24, `the long page's tab (${tab.width} px) is wider than the screen`);
      check(tab.cut, "the long page name is not cut short on its tab");
      check(tab.title === LONG_PAGE, `the tab's tooltip reads "${tab.title}"`);
      check(tab.text.includes(LONG_PAGE) && tab.label === null, "the tab's text does not hold the whole page name");
      const names = await tabNames(r);
      check(names.some((name) => name.includes(LONG_PAGE)), `no page tab is named "${LONG_PAGE}": ${JSON.stringify(names)}`);

      // The room card's form has the page list and the card's own theme.
      await r.click('[data-test="list-row"][data-source="0.0.0"]');
      await r.waitFor(`__j.find('[data-param="page"] select') && __j.find('[data-test="card-theme"]')`, "the room card's form");
      const pages = await r.eval(`[...__j.find('[data-param="page"] select').options].map((option) => option.textContent)`);
      check(pages.includes(LONG_PAGE), `the page list holds ${JSON.stringify(pages)}`);
      for (const field of ['[data-param="page"] select', '[data-test="card-theme"]']) {
        await r.eval(`__j.find('${field}').scrollIntoView({ block: "center" }); true`);
        const form = await r.eval(`__j.overflowProblems(__j.find('[data-test="side"]'))`);
        check(form.length === 0, `the card's form: ${form.join("; ")}`);
      }
      await r.shot("50-long-names-card");

      // The same page list in the picker's device step.
      await r.clearSelection();
      await r.click('[data-test="add-card"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
      await r.click('[data-test="tile"][data-component="apollo/room"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"] [data-param="page"] select')`, "the device step");
      await r.eval(`__j.find('dialog[data-test="picker"] [data-param="page"] select').scrollIntoView({ block: "center" }); true`);
      const picker = await r.eval(`["dialog[data-test=picker]", "dialog[data-test=picker] .picker-body"]
        .flatMap((selector) => __j.overflowProblems(__j.find(selector)))`);
      check(picker.length === 0, `the picker: ${picker.join("; ")}`);
      await r.shot("50-long-names-picker");
      await r.click('[data-test="picker-close"]');
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
      return shot;
    }),
  ];

  // Placeholder text in the search fields is as easy to read as other
  // secondary text.
  const placeholders = [
    step("51", "placeholder-contrast", async (r) => {
      await openSample(r);
      await r.click('[data-test="add-card"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
      await r.click('[data-test="tile"][data-component="apollo/light"]');
      await r.waitFor(`__j.find('[data-test="entity-search"]')`, "the device step");
      const inPicker = await r.eval(`(() => { const input = __j.find('[data-test="entity-search"]');
        return [input.placeholder, __j.placeholderContrast(input)]; })()`);
      check(inPicker[0], "the device search has no placeholder");
      check(inPicker[1] >= 4.5, `the device search's placeholder has contrast ${inPicker[1]}`);
      const shot = await r.shot("51-placeholder-contrast");
      await r.click('[data-test="picker-close"]');
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
      await selectRow(r, "0.1.0");
      await r.click('[data-test="change-device"]');
      await r.waitFor(`__j.find('[data-test="side"] [data-test="entity-search"]')`, "the device search in the form");
      const inForm = await r.eval(`__j.placeholderContrast(__j.find('[data-test="side"] [data-test="entity-search"]'))`);
      check(inForm >= 4.5, `the form's device search placeholder has contrast ${inForm}`);
      return shot;
    }),
  ];

  // What a first-time user needs on the old dashboard and around the card
  // form.
  const newcomer = [
    // Home says what the editor will mark as not shown.
    step("52", "home-not-shown", async (r) => {
      await r.open({ seed: "real" }, `${home} && __j.find('[data-test="dashboard-row"]')`);
      await r.waitFor(`__j.find('[data-test="row-not-shown"]')`, "the not-shown line");
      const line = await r.text('[data-test="row-not-shown"]');
      check(line === "1 card and 1 page are left out on tablets.", `the row reads "${line}"`);
      const shot = await r.shot("52-home-not-shown");
      await r.eval(`(async () => {
        __apolloMockHass.addDashboard("all-shown", "All shown", ${JSON.stringify(SECOND_CONFIG)});
        await __apolloPanel._refresh();
        return true; })()`);
      // The list is drawn first and the counts follow, so wait for the first
      // row's line to be back before checking the second row has none.
      const row = '[data-test="dashboard-row"][data-url-path="all-shown"]';
      await r.waitFor(
        `__j.find('${row}') && __j.find('[data-test="dashboard-row"][data-url-path="tab-1"] [data-test="row-not-shown"]')`,
        "the counts for both rows",
      );
      check((await r.count(`${row} [data-test="row-not-shown"]`)) === 0, "a dashboard with nothing left out has a not-shown line");
      // The editor shows the same: one card and one page marked not shown.
      await r.click('[data-test="dashboard-row"][data-url-path="tab-1"] [data-test="edit"]');
      await r.waitFor(`__j.find('[data-test="list-row"][data-shown="false"]')`, "the editor's list");
      check((await r.count('[data-test="list-row"][data-shown="false"]')) === 1, "the editor marks another number of cards");
      const tabs = await tabNames(r);
      check(tabs.filter((name) => name.includes(NOT_SHOWN)).length === 1, `page tabs ${JSON.stringify(tabs)}`);
      return shot;
    }),
    // A card that is not a TAB-1 card says which device it was for.
    step("53", "other-card-device", async (r) => {
      await r.open({ seed: "real", route: "/edit/tab-1" }, editorReady);
      const row = '[data-test="list-row"][data-shown="false"]';
      await r.waitFor(`__j.find('${row}')`, "the list to know what is shown");
      const text = await r.text(row);
      check(text.includes("Bedroom fan"), `the row reads ${text}`);
      await r.click(row);
      await r.waitFor(`__j.find('[data-test="other-device"]')`, "the device line in the side panel");
      const device = await r.text('[data-test="other-device"]');
      check(device === "It controls: Bedroom fan", `the side panel reads "${device}"`);
      const shot = await r.shot("53-other-card-device");
      // Without a friendly name the entity id is shown instead.
      await r.eval(`(() => { delete __apolloMockHass.states["fan.bedroom_main_bedroom_fan"].attributes.friendly_name;
        const designer = __j.designer(); designer._renderList(); designer._renderSide(); return true; })()`);
      await r.waitFor(`__j.text('[data-test="other-device"]') === "It controls: fan.bedroom_main_bedroom_fan"`, "the entity id");
      return shot;
    }),
    // The old "Tablet preview" page: the side panel says there is nothing
    // to change, instead of asking for a press on a picture that is not there.
    step("54", "old-page-side", async (r) => {
      await r.open({ seed: "real", route: "/edit/tab-1" }, editorReady);
      await r.click('[data-test="page-tab"][data-view="1"]');
      await r.waitFor(`__j.find('[data-test="page-box"]')`, "the old page's box");
      const intro = await r.text('[data-test="side-intro"]');
      check(!intro.includes("Press a card"), `the side panel reads "${intro}"`);
      check(intro.includes("does not show this page"), `the side panel reads "${intro}"`);
      // A short name next to the "Not shown on the tablet" tag is not cut.
      const cut = await r.eval(`(() => { const name = __j.find('[data-test="page-tab"][data-view="1"] .tab-name');
        return name.scrollWidth > name.clientWidth; })()`);
      check(!cut, "the name of the page that is not shown is cut short on its tab");
      return r.shot("54-old-page-side");
    }),
    // On a page still in narrow columns, Wider says why it stops, and its
    // "Use the whole screen" keeps the card selected so Wider works again.
    step("55", "narrow-columns-wider", async (r) => {
      await r.open({ seed: "real", route: "/edit/tab-1" }, editorReady);
      await r.addCard("add-card", "apollo/light", "light.kitchen");
      await r.waitFor(`__j.find('[data-test="size-fine-tune"]')`, "the new card's form");
      await r.click('[data-test="size-fine-tune"]');
      await r.waitFor(`__j.find('[data-test="wider"]')`, "the size steps");
      check((await r.count('[data-test="size-columns"]')) === 0, "the narrow-columns note shows before Wider stops");
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.find('[data-test="wider"]')?.disabled && __j.find('[data-test="size-columns"]')`, "Wider to stop with a reason");
      const note = await r.text('[data-test="size-columns"]');
      check(note.includes("narrow columns") && note.includes("Use the whole screen"), `the note reads "${note}"`);
      const shot = await r.shot("55-narrow-columns-wider");
      await r.click('[data-test="card-whole-screen"]');
      await r.waitFor(
        `(() => { const sections = __apolloMockHass.getConfig("tab-1").views[0].sections;
          return sections.length === 1 && sections[0].column_span === 3; })()`,
        "the page to use the whole screen",
      );
      await r.waitFor(`__j.find('[data-test="wider"]') && !__j.find('[data-test="wider"]').disabled`, "Wider to work again");
      check((await r.text('[data-test="side-title"]')).includes("Light"), "the card is no longer selected");
      check((await focused(r)) === "wider", `focus went to ${await focused(r)}, not Wider`);
      check((await r.count('[data-test="size-columns"]')) === 0, "the narrow-columns note stayed");
      await r.click('[data-test="wider"]');
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1").views[0].sections[0].cards.some((card) => card.component === "apollo/light" && card.grid_options?.columns === 18)`,
        "the card to be saved 3 wide",
      );
      await r.waitSaved("wider after using the whole screen");
      return shot;
    }),
    // With a card selected, the page and dashboard settings are one press
    // away, and the card's own theme says it is for that card only.
    step("56", "to-settings", async (r) => {
      await openSample(r);
      await selectRow(r, "0.1.0");
      check((await r.count('[data-test="theme"]')) === 0, "the dashboard theme shows while a card is selected");
      const helper = await r.eval(`__j.find('[data-test="card-theme"]').closest(".field").querySelector(".helper").textContent`);
      check(helper.includes("Page and dashboard settings"), `the card theme's helper reads "${helper}"`);
      const shot = await r.shot("56-to-settings");
      await r.tap('[data-test="to-settings"]');
      await r.waitFor(`!__j.find('${pressed}') && __j.find('[data-test="theme"]')`, "the dashboard settings");
      const where = await r.eval(`(() => { const element = __j.active();
        const rect = element.getBoundingClientRect();
        return { test: element.dataset.test, text: element.textContent, top: rect.top, bottom: rect.bottom, height: innerHeight }; })()`);
      check(where.test === "settings-heading" && where.text === "This page", `focus went to ${JSON.stringify(where)}`);
      check(where.top >= -1 && where.bottom <= where.height + 1, `the settings are off screen (${where.top}..${where.bottom})`);
      // Escape from inside the form does the same.
      await selectRow(r, "0.1.0");
      await r.eval(`__j.find('[data-test="form-name"]').focus(); true`);
      await r.key("Escape");
      await r.waitFor(`!__j.find('${pressed}') && __j.find('[data-test="theme"]')`, "Escape to bring back the settings");
      return shot;
    }),
  ];

  // Home Assistant tells only a connected browser about a save, and says
  // nothing about the time in between when the connection comes back. A
  // change stored meanwhile must never be saved over without the person's
  // choice: the editor reads the dashboard before each save, when the
  // connection comes back and when the browser tab is shown again.
  const PHONE_CHANGE = `(config) => { config.views[0].title = "Changed on the phone";
    config.views[0].sections[1].cards.push({ type: "custom:apollo-tab-card", component: "apollo/light-tile",
      params: { entity: "light.bedroom" } }); }`;
  const offline = [
    step("57", "retry-after-offline-change", async (r) => {
      await openSample(r);
      await selectRow(r, "0.1.0");
      await r.eval(`__apolloMockHass.failSaves(1); true`);
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
      const mine = await r.draft();
      const theirs = await saveOffline(r, PHONE_CHANGE);
      await sleep(500);
      check((await r.count('[data-test="conflict-mine"]')) === 0, "the editor heard of the change made while offline");
      await r.click('[data-test="save-retry"]');
      await r.waitFor(`__j.find('[data-test="conflict-mine"]')`, "the conflict banner after Try again");
      check((await r.eval(`__j.saveState()`)) === "paused", "saving did not wait for the choice");
      check(stable(await r.config()) === stable(theirs), "Try again saved over the change made while offline");
      const shot = await r.shot("57-retry-after-offline-change");
      await r.click('[data-test="conflict-mine"]');
      await r.waitSaved("after Keep my version");
      check(stable(await r.config()) === stable(mine), "Keep my version did not save my version");
      // The other version is one Undo away.
      await r.click('[data-test="undo"]');
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1").views[0].title === "Changed on the phone"`,
        "Undo to save the other version",
      );
      await r.waitSaved("after Undo");
      return shot;
    }),
    step("58", "edit-after-offline-change", async (r) => {
      await openSample(r);
      const theirs = await saveOffline(r, PHONE_CHANGE);
      await selectRow(r, "0.1.0");
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.find('[data-test="conflict-theirs"]')`, "the conflict banner after the next change");
      check((await r.calls("lovelace/config/save")).length === 0, "the next change was saved");
      check(stable(await r.config()) === stable(theirs), "the next change was saved over the one made while offline");
      const shot = await r.shot("58-edit-after-offline-change");
      await r.click('[data-test="conflict-theirs"]');
      await r.waitSaved("after Use the other version");
      check(stable(await r.draft()) === stable(theirs), "the editor does not show the other version");
      check(stable(await r.config()) === stable(theirs), "Home Assistant does not hold the other version");
      return shot;
    }),
    step("59", "offline-change-on-reconnect", async (r) => {
      await openSample(r);
      check(await r.eval(`__apolloMockHass.readyListeners() > 0`), "the editor does not watch the connection");
      const first = await saveOffline(r, PHONE_CHANGE);
      await r.eval(`__apolloMockHass.reconnect(); true`);
      await r.waitFor(`__j.find('[data-test="toast"]')`, "the toast about the other change");
      check(stable(await r.draft()) === stable(first), "after the connection came back the editor shows an old version");
      check((await r.calls("lovelace/config/save")).length === 0, "the connection coming back saved something");
      const shot = await r.shot("59-offline-change-on-reconnect");

      // With a change not saved yet, showing the browser tab again finds the
      // next change made while offline and asks.
      await selectRow(r, "0.1.0");
      await r.eval(`__apolloMockHass.failSaves(1); true`);
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
      const second = await saveOffline(r, `(config) => { config.apollo_tab = { ...config.apollo_tab, theme: "warm" }; }`);
      check(await r.eval(`document.visibilityState === "visible"`), "the browser tab is not visible");
      await r.eval(`document.dispatchEvent(new Event("visibilitychange")); true`);
      await r.waitFor(`__j.find('[data-test="conflict-theirs"]')`, "the conflict banner after the tab was shown");
      check(stable(await r.config()) === stable(second), "showing the tab saved over the change made while offline");
      await r.shot("59-offline-change-on-tab-shown");
      await r.click('[data-test="conflict-theirs"]');
      await r.waitSaved("after Use the other version");
      check(stable(await r.draft()) === stable(second), "the editor does not show the other version");
      check(stable(await r.config()) === stable(second), "Home Assistant does not hold the other version");
      return shot;
    }),
    // The editor stays open with a change it could not save, and the
    // dashboard is deleted and made again with the content the change
    // started from while the connection is down. The person is looking at
    // that content, so the change is saved into it as usual when they press
    // Try again: nothing in the new dashboard is lost, and nobody is asked a
    // question they cannot answer.
    step("76", "open-editor-recreated-while-offline", async (r) => {
      await openSample(r);
      const original = await r.config();
      await selectRow(r, "0.1.0");
      await r.eval(`__apolloMockHass.failSaves(1); true`);
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
      const mine = await r.draft();
      await recreateWhileOffline(r, original);
      await r.eval(`__apolloMockHass.reconnect(); true`);
      await sleep(800);
      check((await r.eval(BANNER)) === 0, "the editor asks which version to keep after the connection came back");
      check((await r.eval(`__j.saveState()`)) === "error", "the change is no longer offered to save again");
      const shot = await r.shot("76-open-editor-recreated-while-offline");
      await r.click('[data-test="save-retry"]');
      await r.waitSaved("after Try again");
      check((await r.eval(BANNER)) === 0, "Try again asks which version to keep");
      check(stable(await r.config()) === stable(mine), "Try again did not save the change");
      return shot;
    }),
    // The connection is lost and comes back around the editor's own saves.
    // Nothing else changed the dashboard, so nothing is asked and every
    // change ends up saved: Home Assistant's library answers a command under
    // way with "Connection lost" when the connection drops, and holds back
    // commands sent while it is down until it is back.
    step("80", "own-saves-and-lost-connection", async (r) => {
      // Watches for a question about another version until the change is
      // saved: none may show up at any moment in between.
      const savedWithoutAsking = async (when) => {
        const end = Date.now() + 10000;
        while (Date.now() < end) {
          check((await r.eval(BANNER)) === 0, `${when}: the editor asks which version to keep`);
          if ((await r.eval(`__j.saveState()`)) === "saved") break;
          await sleep(50);
        }
        await r.waitSaved(when);
        await sleep(600);
        check((await r.eval(BANNER)) === 0, `${when}: the editor asks which version to keep`);
        check(stable(await r.config()) === stable(await r.draft()), `${when}: Home Assistant does not hold the change`);
      };

      // The connection comes back while the editor's own slow save runs.
      await openSample(r);
      await selectRow(r, "0.1.0");
      await r.eval(`__apolloMockHass.slowSaves(1500); true`);
      await r.click('[data-test="wider"]');
      await r.waitFor(`${SAVES}.length === 1`, "the save to be sent", 3000);
      await r.eval(`__apolloMockHass.reconnect(); true`);
      await savedWithoutAsking("a reconnection during the editor's own save");
      const shot = await r.shot("80-own-saves-and-lost-connection");

      // The save is stored, but its answer is lost with the connection.
      await r.eval(`__apolloMockHass.slowSaves(0); __apolloMockHass.loseSaveAnswers(1); true`);
      await r.click('[data-test="taller"]');
      await savedWithoutAsking("a save whose answer was lost");

      // Stored after the connection dropped, then the connection comes back.
      const sent = (await r.calls("lovelace/config/save")).length;
      await r.eval(`__apolloMockHass.slowSaves(600); true`);
      await r.click('[data-test="narrower"]');
      await r.waitFor(`${SAVES}.length === ${sent + 1}`, "the next save to be sent", 3000);
      await r.eval(`__apolloMockHass.dropConnection(); true`);
      await sleep(900);
      await r.eval(`__apolloMockHass.slowSaves(0); __apolloMockHass.reconnect(); true`);
      await savedWithoutAsking("a save that landed while the connection was down");

      // A change made while the connection is down.
      await r.eval(`__apolloMockHass.dropConnection(); true`);
      await r.click('[data-test="shorter"]');
      await sleep(1000);
      check((await r.eval(BANNER)) === 0, "a change made while the connection is down asks which version to keep");
      await r.eval(`__apolloMockHass.reconnect(); true`);
      await savedWithoutAsking("a change made while the connection was down");
      await r.shot("80-change-made-while-offline");
      return shot;
    }),
    // The dashboard is deleted somewhere else while the editor holds a
    // change it could not save. The editor says the dashboard is gone, and
    // closing the browser page no longer warns about that change.
    step("81", "deleted-while-not-saved", async (r) => {
      await openSample(r);
      await selectRow(r, "0.1.0");
      await r.eval(`__apolloMockHass.failSaves(100); true`);
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
      check(await leavingAsks(r), "closing the browser page would not ask about the unsaved change");
      await r.eval(`__apolloMockHass.callWS({ type: "lovelace/dashboards/delete", dashboard_id: "tab_1" }).then(() => true)`);
      await r.waitFor(`__j.find('[data-test="missing-back"]')`, "the screen saying the dashboard is gone");
      await sleep(300);
      check(!(await leavingAsks(r)), "closing the browser page warns about a change to a deleted dashboard");
      await r.eval(`__apolloMockHass.failSaves(0); true`);
      return r.shot("81-deleted-while-not-saved");
    }),
  ];

  // A press that removes the pressed button itself leaves focus on a safe
  // control: the tab of the page now shown, the card list, or the toast's
  // next step. One more Enter never removes another page or card.
  const removing = [
    step("61", "focus-after-removing", async (r) => {
      const views = () => r.eval(`__j.designer()._history.present.views.length`);
      await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
      await r.click('[data-test="create"]');
      await r.waitFor(`__j.find('[data-test="add-first-card"]')`, "the empty editor");
      for (const count of [2, 3]) {
        await r.click('[data-test="add-page"]');
        await r.waitFor(`__j.count('[data-test="page-tab"]') === ${count}`, `page ${count}`);
      }
      await r.click('[data-test="page-tab"][data-view="0"]');
      await r.waitFor(`__j.find('[data-test="page-tab"][data-view="0"][aria-selected="true"]')`, "the first page");
      // An empty page goes without a question.
      await pressRemoving(r, '[data-test="page-delete"]', "page-tab", "deleting an empty page");
      check(await r.eval(`__j.active().getAttribute("aria-selected") === "true"`), "focus is not on the page shown");
      await r.key("Enter");
      await sleep(300);
      check((await views()) === 2, "a second Enter deleted another page");

      // The old dashboard: a card the tablet cannot show, then the old page.
      await r.open({ seed: "real", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(`__j.find('[data-test="list-row"][data-shown="false"]')`, "the list to know what is shown");
      await pressRemoving(r, '[data-test="row-remove"]', "toast-replace", "removing a card the tablet cannot show");
      await r.click('[data-test="page-tab"][data-view="1"]');
      await r.waitFor(`__j.find('[data-test="page-remove"]')`, "the old page's box");
      await pressRemoving(r, '[data-test="page-remove"]', "page-tab", "removing the old page");
      const shot = await r.shot("61-focus-after-removing");

      // A card from its form, then a page with cards after the question.
      await openSample(r);
      await selectRow(r, "0.1.0");
      await pressRemoving(r, '[data-test="remove-card"]', "list-row", "removing a card from its form");
      await r.eval(`__j.find('[data-test="page-delete"]').focus(); true`);
      await r.key("Enter");
      await r.waitFor(`__j.find('dialog[data-test="confirm"][open]')`, "the question");
      await pressRemoving(r, '[data-test="confirm-ok"]', "page-tab", "deleting a page after the question");
      check((await views()) === 1, "the page was not deleted");
      return shot;
    }),
  ];

  // With a card selected, pressing the tab of the page shown lets the card
  // go and moves to that page's settings, where it is renamed.
  const pageTab = [
    step("62", "page-tab-to-settings", async (r) => {
      const where = () =>
        r.eval(`(() => { const element = __j.active(); const rect = element.getBoundingClientRect();
          return { test: element.dataset.test, text: element.textContent, top: rect.top, bottom: rect.bottom,
            height: innerHeight, ring: getComputedStyle(element).outlineStyle }; })()`);
      await openSample(r);
      await selectRow(r, "0.1.0");
      let shot;
      if (r.setup.device === "desktop") {
        await r.click('[data-test="page-tab"][aria-selected="true"]');
        await r.waitFor(`!__j.find('${pressed}') && __j.find('[data-test="page-name"]')`, "the page's settings");
        const mouse = await where();
        check(mouse.test === "settings-heading" && mouse.text === "This page", `focus went to ${JSON.stringify(mouse)}`);
        check(mouse.top >= -1 && mouse.bottom <= mouse.height + 1, `the page's settings are off screen (${mouse.top}..${mouse.bottom})`);
        const name = await r.eval(`__j.find('[data-test="page-name"]').value`);
        check(name === "Home", `the page name field holds "${name}"`);
        shot = await r.shot("62-page-tab-to-settings");

        // From the keyboard too, where the heading shows that it has focus.
        await selectRow(r, "0.1.0");
        await r.eval(`__j.find('[data-test="page-tab"][aria-selected="true"]').focus(); true`);
        await r.key("Enter");
        await r.waitFor(`!__j.find('${pressed}') && __j.active()?.dataset?.test === "settings-heading"`, "Enter to show the settings");
        const keyboard = await where();
        check(keyboard.ring !== "none", "the settings heading shows no focus ring after Enter");
      } else {
        // On a phone the page strip is under the edit mode and takes no
        // press or focus; Done is the way out.
        const inert = await r.eval(`Boolean(__j.find('[data-test="page-tab"][aria-selected="true"]').closest("[inert]"))`);
        check(inert, "the page's tab can be reached under the edit mode");
        shot = await r.shot("62-page-tab-to-settings");
        await r.click('[data-test="close-panel"]');
        await r.waitFor(`!__j.find('${pressed}') && !__j.find('[data-test="side"][data-mode="edit"]')`, "Done to close the edit mode");
      }
      // Without a selected card a press on the page's own tab changes nothing.
      await r.eval(`__j.find('[data-test="page-tab"][aria-selected="true"]').focus(); true`);
      await r.key("Enter");
      await sleep(200);
      check((await focused(r)) === "page-tab", `pressing the page's tab again moved focus to ${await focused(r)}`);
      check((await r.draft()).views.length === 2 && (await r.calls("lovelace/config/save")).length === 0, "pressing tabs changed the dashboard");
      return shot;
    }),
  ];

  // Removing a card the tablet cannot show keeps the device it was for: the
  // toast names it and offers the TAB-1 cards that can control it.
  const replacing = [
    step("63", "replace-other-card", async (r) => {
      await r.open({ seed: "real", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(`__j.find('[data-test="list-row"][data-shown="false"]')`, "the list to know what is shown");
      await r.click('[data-test="row-remove"]');
      await r.waitFor(`__j.find('[data-test="toast-replace"]')`, "the toast offering a TAB-1 card");
      const text = await r.text('[data-test="toast"] span');
      check(text === "Card removed. Add a TAB-1 card for Bedroom fan.", `the toast reads "${text}"`);
      check((await r.count('[data-test="toast-undo"]')) === 1, "the toast has no Undo");
      // The check waits for the toast to finish fading in.
      await checkTextContrast(r, ['[data-test="toast"] span', '[data-test="toast-replace"]', '[data-test="toast-undo"]']);
      const shot = await r.shot("63-replace-other-card");

      // Undo brings the card back; removing it again offers the same.
      await r.click('[data-test="toast-undo"]');
      await r.waitFor(`JSON.stringify(__j.designer()._history.present).includes("custom:bubble-card")`, "Undo to bring the card back");
      await r.waitFor(`__j.find('[data-test="list-row"][data-shown="false"]')`, "the card back in the list");
      await r.click('[data-test="row-remove"]');
      await r.waitFor(`__j.find('[data-test="toast-replace"]')`, "the toast again");
      await r.click('[data-test="toast-replace"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
      const title = await r.text('dialog[data-test="picker"] h2');
      check(title === "Add a card for Bedroom fan", `the picker is titled "${title}"`);
      const tiles = await r.eval(`__j.all('[data-test="tile"]').map((tile) => tile.dataset.component)`);
      // The fan card, and the switch card, which turns a fan on and off too.
      check(stable([...tiles].sort()) === stable(["apollo/fan-speed", "apollo/switch"]), `the picker offers ${tiles.join(", ")}`);
      await sleep(500);
      await r.shot("63-replace-other-card-picker");
      await r.click('[data-test="picker-show-all"]');
      await r.waitFor(`__j.count('[data-test="tile"]') === ${OFFERED_CARDS}`, "every card after Show all cards");
      // The fan's card gets the fan without asking for it again.
      await r.click('[data-test="tile"][data-component="apollo/fan-speed"]');
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
      await r.waitFor(
        `__apolloMockHass.getConfig("tab-1").views[0].sections[0].cards.some((card) =>
          card.component === "apollo/fan-speed" && card.params?.entity === "fan.bedroom_main_bedroom_fan")`,
        "the fan card for the bedroom fan to be saved",
      );
      await r.waitSaved("fan card added");
      check(!JSON.stringify(await r.config()).includes("custom:bubble-card"), "the removed card came back");
      return shot;
    }),
  ];

  // A change kept after leaving the editor belongs to its dashboard. Once
  // that dashboard is deleted, the change is dropped and leaving the browser
  // page stops asking about it; a new dashboard at the same address never
  // gets it.
  const kept = [
    step(
      "64",
      "kept-change-dashboard-deleted",
      async (r) => {
        const original = await keepChange(r, { offline: true });
        await r.eval(`__apolloMockHass.callWS({ type: "lovelace/dashboards/delete", dashboard_id: "tab_1" })`);
        await until(async () => !(await leavingAsks(r)), "leaving to stop asking once the dashboard was deleted", 3000);
        await recreateElsewhere(r, original);
        const saves = (await r.calls("lovelace/config/save")).length;
        await reopenEditor(r);
        await sleep(2500);
        check((await r.calls("lovelace/config/save")).length === saves, "opening the new dashboard saved into it");
        check((await r.count('[data-test="conflict-mine"]')) === 0, "the new dashboard asks about the deleted one's change");
        check(stable(await r.config()) === stable(original), "the new dashboard was changed");
        check(stable(await r.draft()) === stable(original), "the editor shows the deleted dashboard's change");
        return r.shot("64-kept-change-dashboard-deleted");
      },
      { desktopOnly: true },
    ),
    step(
      "65",
      "kept-change-new-dashboard-same-address",
      async (r) => {
        const original = await keepChange(r, { offline: false });
        await r.eval(`__apolloMockHass.failSaves(0);
          __apolloMockHass.callWS({ type: "lovelace/dashboards/delete", dashboard_id: "tab_1" })`);
        await recreateElsewhere(r, original);
        const saves = (await r.calls("lovelace/config/save")).length;
        // The first background try comes 2 s after the failed save.
        await sleep(3500);
        check((await r.calls("lovelace/config/save")).length === saves, "the kept change was saved into the new dashboard");
        check(stable(await r.config()) === stable(original), "the new dashboard was changed");
        check(!(await leavingAsks(r)), "leaving still asks about the deleted dashboard's change");
        return null;
      },
      { desktopOnly: true },
    ),
    // Deleted while this browser's connection was down: the change is
    // dropped once the connection comes back.
    step(
      "66",
      "kept-change-deleted-while-offline",
      async (r) => {
        await keepChange(r, { offline: true });
        await r.eval(`__apolloMockHass.deleteWhileOffline("tab-1"); true`);
        await sleep(300);
        check(await leavingAsks(r), "the change was dropped before anything said the dashboard was gone");
        await r.eval(`__apolloMockHass.reconnect(); true`);
        await until(async () => !(await leavingAsks(r)), "leaving to stop asking after the connection came back", 3000);
        return null;
      },
      { desktopOnly: true },
    ),
    // Deleted and made again while the connection was down, the new
    // dashboard cannot be told from the old one. The change that had met
    // another version is offered with the banner, never saved unasked.
    step(
      "67",
      "kept-change-unsure-dashboard-asks",
      async (r) => {
        const original = await keepChange(r, { offline: true });
        await recreateWhileOffline(r, original);
        const saves = (await r.calls("lovelace/config/save")).length;
        await reopenEditor(r);
        await r.waitFor(`__j.find('[data-test="conflict-theirs"]')`, "the banner asking which version to keep");
        await sleep(1000);
        check((await r.calls("lovelace/config/save")).length === saves, "opening the dashboard saved the kept change");
        check(stable(await r.config()) === stable(original), "the dashboard was changed");
        return r.shot("67-kept-change-unsure-dashboard-asks");
      },
      { desktopOnly: true },
    ),
    // A change whose saves kept failing, and whose dashboard was deleted and
    // made again with the content the change started from while the
    // connection was down. Once the connection is back the new dashboard
    // looks like the old one, so the change waits for the person's choice,
    // both in the background and when the editor opens again.
    step(
      "75",
      "kept-change-recreated-while-offline",
      async (r) => {
        const saves = async () => (await r.calls("lovelace/config/save")).length;
        const unsureBanner = async (when) => {
          await r.waitFor(`__j.find('[data-test="conflict-unsure"]')`, `the banner asking which version to keep (${when})`);
          const title = await r.text('[data-test="conflict-unsure"] h2');
          check(title === "Your change is not saved yet", `${when}: the banner is titled "${title}"`);
        };

        // Left alone: the background try finds the dashboard and asks.
        let original = await keepChange(r, { offline: false });
        await recreateWhileOffline(r, original);
        await r.eval(`__apolloMockHass.failSaves(0); __apolloMockHass.reconnect(); true`);
        let before = await saves();
        // Past the first background try, 2 s after the failed save.
        await sleep(3000);
        check((await saves()) === before, "the kept change was saved into the dashboard made again");
        check(stable(await r.config()) === stable(original), "the dashboard made again was changed");
        check(await leavingAsks(r), "the kept change was dropped without asking");
        await reopenEditor(r);
        await unsureBanner("after the background try");
        await sleep(1000);
        check((await saves()) === before, "opening the dashboard saved the kept change");
        const shot = await r.shot("75-kept-change-recreated-while-offline");
        // Keep my version saves the change, as the person chose.
        const mine = await r.draft();
        await r.click('[data-test="conflict-mine"]');
        await r.waitSaved("after Keep my version");
        check(stable(await r.config()) === stable(mine), "Keep my version did not save the kept change");

        // Opened again before the background try: the editor asks at once.
        original = await keepChange(r, { offline: false });
        await recreateWhileOffline(r, original);
        await r.eval(`__apolloMockHass.failSaves(0); __apolloMockHass.reconnect(); true`);
        before = await saves();
        await reopenEditor(r);
        await unsureBanner("when the editor opened again");
        await sleep(2500);
        check((await saves()) === before, "opening the dashboard saved the kept change");
        check(stable(await r.config()) === stable(original), "the dashboard made again was changed");
        return shot;
      },
      { desktopOnly: true },
    ),
    // A change that already waited for a choice when the connection was
    // lost, while the dashboard was deleted and made again with other
    // content. Nothing shows whose that content is, so the editor asks with
    // the banner that says so and offers the other version first.
    step(
      "91",
      "kept-choice-recreated-with-other-content",
      async (r) => {
        await openSample(r);
        await selectRow(r, "0.1.0");
        await r.eval(`__apolloMockHass.failSaves(1); true`);
        await r.click('[data-test="wider"]');
        await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
        await saveElsewhere(r, `(config) => { config.views[1].title = "Elsewhere"; }`);
        await r.waitFor(`__j.find('[data-test="conflict-mine"]')`, "the question which version to keep");
        await leaveThroughSidebar(r);
        await sleep(400);
        await recreateWhileOffline(r, SECOND_CONFIG);
        await r.eval(`__apolloMockHass.reconnect(); true`);
        await sleep(1000);
        const saves = (await r.calls("lovelace/config/save")).length;
        await reopenEditor(r);
        await r.waitFor(`__j.find('[data-test="conflict-unsure"]')`, "the banner saying the dashboard may be a new one");
        const buttons = await r.eval(`__j.all('[data-test="conflict-unsure"] button')
          .map((button) => button.dataset.test + (button.classList.contains("primary") ? " (main)" : ""))`);
        check(
          stable(buttons) === stable(["conflict-theirs (main)", "conflict-mine"]),
          `the banner offers ${buttons.join(", ")}`,
        );
        await sleep(1000);
        check((await r.calls("lovelace/config/save")).length === saves, "opening the dashboard saved the kept change");
        check(stable(await r.config()) === stable(SECOND_CONFIG), "the new dashboard was changed");
        const shot = await r.shot("91-kept-choice-recreated-with-other-content");
        await r.click('[data-test="conflict-theirs"]');
        await r.waitSaved("after Use the other version");
        check(stable(await r.draft()) === stable(SECOND_CONFIG), "the editor does not show the new dashboard");
        check(!(await leavingAsks(r)), "closing the browser page still asks after the choice");
        return shot;
      },
      { desktopOnly: true },
    ),
  ];

  // Where something is on screen: its edges, and whether it is the control
  // that has focus.
  const edgesOf = (selector) =>
    `(() => { const element = ${selector}; if (!element) return null;
      const rect = element.getBoundingClientRect();
      return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom }; })()`;
  const overlaps = (a, b) =>
    Boolean(a && b) && Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 &&
    Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1;

  // The toast covers nothing the person is working with: the card sheet or
  // side panel, the control with focus and the selected card.
  async function checkToastClear(r, when) {
    const places = await r.eval(`({
      toast: ${edgesOf(`__j.find('[data-test="toast"]')`)},
      side: ${edgesOf(`__j.find('.side.sheet') || (__j.find('.root.compact') ? null : __j.find('[data-test="side"]'))`)},
      focused: ${edgesOf(`(() => { const element = __j.active(); return element && element !== document.body && !element.closest('[data-test="toast"]') ? element : null; })()`)},
      card: ${edgesOf(`__j.find('[data-test="hit"][aria-pressed="true"]')`)},
      row: ${edgesOf(`__j.find('[data-test="list-row"][aria-current="true"]')`)},
      // The visible part of the page, which a zoomed-in phone or its
      // on-screen keyboard makes smaller than the window.
      top: visualViewport.offsetTop,
      height: visualViewport.offsetTop + visualViewport.height,
      width: innerWidth,
    })`);
    const { toast } = places;
    check(toast, `${when}: no toast`);
    check(
      toast.top >= places.top && toast.bottom <= places.height && toast.left >= 0 && toast.right <= places.width,
      `${when}: the toast is not wholly on screen (${JSON.stringify(places)})`,
    );
    for (const what of ["side", "focused", "card", "row"]) {
      check(!overlaps(toast, places[what]), `${when}: the toast covers the ${what} (${JSON.stringify(places)})`);
    }
  }

  // The toast is in its home (build plan 2.11): "stage", centred on the
  // stage column with its bottom 16 px above the status strip (or the
  // column's bottom); "fab", centred above the floating Add card; "edit",
  // inside the edit mode, 16 px above its bottom.
  async function checkToastHome(r, when, home) {
    const places = await r.eval(`({
      toast: ${edgesOf(`__j.find('[data-test="toast"]')`)},
      main: ${edgesOf(`__j.designer().shadowRoot.querySelector(".main")`)},
      strip: ${edgesOf(`__j.find(".status-strip")`)},
      root: ${edgesOf(`__j.designer().shadowRoot.querySelector(".root")`)},
      fab: ${edgesOf(`__j.find('.fab[data-test="add-card"]')`)},
      edit: ${edgesOf(`__j.find('[data-test="side"][data-mode="edit"]')`)},
      frame: ${edgesOf(`__j.designer().shadowRoot.querySelector(".device")`)},
      height: innerHeight,
      width: innerWidth,
    })`);
    const { toast } = places;
    check(toast, `${when}: no toast`);
    check(
      toast.top >= 0 && toast.bottom <= places.height && toast.left >= 0 && toast.right <= places.width,
      `${when}: the toast is not wholly on screen (${JSON.stringify(places)})`,
    );
    const middle = (box) => (box.left + box.right) / 2;
    const near = (a, b) => Math.abs(a - b) <= 2;
    let ok = false;
    if (home === "stage") {
      // 16 px above the status strip when that leaves it wholly on the grey
      // under the tablet frame (8 px clear of it); else over the strip, 4 px
      // above the column's bottom. Never across the frame's edge.
      const bottom = places.strip ? places.strip.top : places.main.bottom;
      const { frame, strip } = places;
      const room = !strip || !frame || bottom - 16 - (toast.bottom - toast.top) >= frame.bottom + 8;
      ok = near(middle(toast), middle(places.main)) && near(toast.bottom, room ? bottom - 16 : strip.bottom - 4);
      check(!frame || toast.top >= frame.bottom || toast.bottom <= frame.top,
        `${when}: the toast lies across the tablet frame's edge: ${JSON.stringify(places)}`);
    } else if (home === "fab") {
      ok = Boolean(places.fab) && near(middle(toast), middle(places.root)) && near(toast.bottom, places.fab.top - 16);
    } else {
      ok = Boolean(places.edit) && near(toast.bottom, places.edit.bottom - 16) &&
        toast.left >= places.edit.left && toast.right <= places.edit.right && toast.top >= places.edit.top;
    }
    check(ok, `${when}: the toast is not in its place (${home}): ${JSON.stringify(places)}`);
  }

  // Keyboard focus is always shown, legible words, Home's numbers, the
  // first screen of the old dashboard, plain names and toasts that keep out
  // of the way.
  const clearer = [
    // Focus moved to the settings heading from the keyboard shows its ring.
    step("68", "settings-heading-ring", async (r) => {
      const ring = () =>
        r.eval(`(() => { const element = __j.active(); const style = getComputedStyle(element);
          return { test: element.dataset.test, style: style.outlineStyle, width: parseFloat(style.outlineWidth) }; })()`);
      await openSample(r);
      await selectRow(r, "0.1.0");
      await r.eval(`__j.find('[data-test="to-settings"]').focus(); true`);
      await r.key("Enter");
      await r.waitFor(`__j.active()?.dataset?.test === "settings-heading"`, "Enter to move to the settings");
      const enter = await ring();
      check(enter.style !== "none" && enter.width >= 2, `after Enter the settings heading shows ${JSON.stringify(enter)}`);
      return r.screen("68-settings-heading-ring");
    }),
    // The words saying why a card is switched off stay legible, while the
    // card still looks unavailable.
    step("69", "locked-card-reason", async (r) => {
      const tile = '[data-test="tile"][data-component="me/door-lock"]';
      await openSample(r, { community: "1" });
      await r.click('[data-test="add-card"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"][open]') && __j.find('${tile}')`, "the switched-off card");
      await r.eval(`__j.find('${tile}').scrollIntoView({ block: "center" }); true`);
      const looks = await r.eval(`(() => { const tile = __j.find('${tile}');
        return { reason: __j.textContrast(tile.querySelector(".tile-locked span")),
          name: __j.textContrast(tile.querySelector(".tile-name")),
          border: getComputedStyle(tile).borderTopStyle,
          picture: Number(getComputedStyle(tile.querySelector(".tile-preview")).opacity),
          disabled: tile.disabled }; })()`);
      check(looks.reason >= 4.5, `the reason has contrast ${looks.reason}`);
      check(looks.name >= 4.5, `the card's name has contrast ${looks.name}`);
      check(looks.disabled && looks.border === "dashed" && looks.picture < 0.5, `the tile does not look unavailable: ${JSON.stringify(looks)}`);
      // The helper sees a faded parent: the same words in a tile at 0.75
      // opacity fall short.
      const faded = await r.eval(`(() => { const tile = __j.find('${tile}'); tile.style.opacity = "0.75";
        const ratio = __j.textContrast(tile.querySelector(".tile-locked span")); tile.style.opacity = ""; return ratio; })()`);
      check(faded < looks.reason, `the contrast helper ignores a faded parent (${faded} vs ${looks.reason})`);
      return r.screen("69-locked-card-reason");
    }),
    // Home's numbers are the editor's: as many pages as the editor has tabs,
    // and the ones the tablet leaves out counted on their own.
    step("70", "home-pages-agree", async (r) => {
      await r.open({ seed: "real" }, `${home} && __j.find('[data-test="row-not-shown"]')`);
      const row = await r.text('[data-test="dashboard-row"][data-url-path="tab-1"]');
      const pages = Number(/Pages: (\d+)/.exec(row)?.[1]);
      check(pages === 2, `the row reads ${row}`);
      check(row.includes("1 card and 1 page are left out on tablets."), `the row reads ${row}`);
      const shot = await r.shot("70-home-pages-agree");
      await r.click('[data-test="dashboard-row"][data-url-path="tab-1"] [data-test="edit"]');
      await r.waitFor(`__j.find('[data-test="list-row"][data-shown="false"]')`, "the editor");
      const tabs = await r.count('[data-test="page-tab"]');
      check(tabs === pages, `Home says ${pages} pages, the editor has ${tabs} page tabs`);
      return shot;
    }),
    // The first screen of the old dashboard says that a card on the page is
    // not shown, next to the picture, with a way to it. Both choice banners
    // are still there, and the picture is on the first screen.
    step("71", "first-screen-hint", async (r) => {
      await r.open({ seed: "real", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(`__j.find('[data-test="not-shown-hint"]')`, "the not-shown hint");
      await r.eval(`scrollTo(0, 0); true`);
      const hint = await r.text('[data-test="not-shown-hint"]');
      check(hint.startsWith("1 card on this page is not shown on the tablet."), `the hint reads "${hint}"`);
      const first = await r.eval(`({ hint: ${edgesOf(`__j.find('[data-test="not-shown-hint"]')`)},
        stage: ${edgesOf(`__j.find('[data-test="canvas"]')`)}, height: innerHeight })`);
      check(first.hint.bottom <= first.height, `the hint is below the first screen (${first.hint.bottom} > ${first.height})`);
      const seen = Math.min(first.stage.bottom, first.height) - first.stage.top;
      check(seen >= (first.stage.bottom - first.stage.top) / 2, `less than half the picture is on the first screen (${JSON.stringify(first)})`);
      // One notice line shows above the picture, the other two behind "+2
      // more"; the picture is fitted to what is left each time.
      const pictureWidth = (width, when) =>
        r.waitFor(
          `Math.abs(__j.find('[data-test="canvas"]').getBoundingClientRect().width - ${width}) <= 1`,
          `the picture to be ${width} px wide ${when}`,
          3000,
        );
      if (r.setup.device === "desktop") {
        check((await r.count(".page-notice")) === 1, `${await r.count(".page-notice")} notice lines show`);
        const more = await r.text('[data-test="notices-more"]');
        check(more === "+2 more", `the notices button reads "${more}"`);
        await pictureWidth(864, "with one notice line");
        await openNotices(r);
        check((await r.text('[data-test="notices-more"]')) === "Show fewer", "the notices button does not read Show fewer");
        await pictureWidth(723, "with all three notices");
      }
      for (const choice of ["sidebar-hide", "sidebar-keep", "use-whole-screen"]) {
        check((await r.count(`[data-test="${choice}"]`)) === 1, `the choice ${choice} is gone`);
      }
      await checkTextContrast(r, ['[data-test="not-shown-hint"] span', '[data-test="not-shown-go"]']);
      const shot = await r.screen("71-first-screen-hint");
      if (r.setup.device === "desktop") {
        await r.click('[data-test="notices-more"]');
        await r.waitFor(`__j.find('[data-test="notices-more"][aria-expanded="false"]')`, "Show fewer to close the list");
        await pictureWidth(864, "after Show fewer");
      }
      await r.click('[data-test="not-shown-go"]');
      await sleep(200);
      const row = await r.eval(`(() => { const element = __j.active(); const rect = element.getBoundingClientRect();
        return { test: element.dataset.test, shown: element.dataset.shown, top: rect.top, bottom: rect.bottom, height: innerHeight }; })()`);
      check(row.test === "list-row" && row.shown === "false", `"Show me" moved focus to ${JSON.stringify(row)}`);
      check(row.top >= 0 && row.bottom <= row.height, `the card is off screen after "Show me" (${JSON.stringify(row)})`);
      await r.screen("71-first-screen-hint-shown");
      // Opening and looking around still changes nothing.
      await sleep(600);
      check((await r.calls("lovelace/config/save")).length === 0, "the hint saved something");
      return shot;
    }),
    // Every page icon has a plain name, read out and shown as a tooltip.
    step("72", "page-icon-names", async (r) => {
      await openSample(r);
      await r.waitFor(`__j.find('[data-test="page-icon"]')`, "the page icons");
      const icons = await r.eval(`__j.all('[data-test="page-icon"]').map((button) =>
        ({ icon: button.dataset.icon, label: button.getAttribute("aria-label"), title: button.title }))`);
      check(icons.length === 21, `${icons.length} page icons`);
      for (const { icon, label, title } of icons) {
        check(label && label === title, `${icon} is named "${label}" with the tooltip "${title}"`);
        check(!label.includes("-") && !label.startsWith("mdi") && /^[A-Z]/.test(label), `${icon} is named "${label}"`);
      }
      check(new Set(icons.map((entry) => entry.label)).size === icons.length, "two icons share a name");
      const kitchen = icons.find((entry) => entry.icon === "mdi:silverware-fork-knife");
      check(kitchen?.label === "Kitchen", `the kitchen icon is named ${kitchen?.label}`);
      await r.browser.send("Accessibility.enable");
      const { nodes } = await r.browser.send("Accessibility.getFullAXTree");
      await r.browser.send("Accessibility.disable");
      const named = (role, name) => nodes.some((node) => !node.ignored && node.role?.value === role && node.name?.value === name);
      check(named("group", "Icon on the tablet's side bar"), "the icons are not a group named after their label");
      check(named("button", "Cameras") && !named("button", "cctv"), "a screen reader does not hear the plain names");
      await r.eval(`__j.find('[data-test="page-icon"][data-icon="mdi:cctv"]').scrollIntoView({ block: "center" }); true`);
      return r.screen("72-page-icon-names");
    }),
    // The sidebar setting says when to turn it on, and the highlight colour
    // says what it changes.
    step("73", "settings-words", async (r) => {
      await openSample(r);
      const sidebar = await r.eval(`__j.find('[data-test="sidebar-checkbox"]').closest(".check").nextElementSibling.textContent`);
      check(!sidebar.includes("in a browser") && sidebar.startsWith("Turn this on only if"), `the sidebar helper reads "${sidebar}"`);
      await selectRow(r, "0.1.0");
      const accent = await r.eval(`(() => { const box = __j.find('input[data-focus="look-use-accent"]');
        const helper = __j.find('[data-test="accent-helper"]');
        return { text: helper?.textContent, described: box?.getAttribute("aria-describedby") === helper?.id,
          next: box?.closest(".check").nextElementSibling === helper }; })()`);
      check(accent.text?.includes("switches, sliders and buttons") && accent.described && accent.next, `the highlight colour's helper: ${JSON.stringify(accent)}`);
      await r.eval(`__j.find('[data-test="accent-helper"]').scrollIntoView({ block: "center" }); true`);
      await checkTextContrast(r, ['[data-test="accent-helper"]']);
      return r.screen("73-settings-words");
    }),
    // A toast has one home in each layout (build plan 2.11): over the stage
    // column above the status strip, above the floating Add card on a
    // phone, and inside the phone's edit mode while that is open.
    step("74", "toast-placement", async (r) => {
      const phone = r.setup.device === "phone";
      await openSample(r);
      await selectRow(r, "0.1.0");
      await r.waitFor(`__j.find('[data-test="move-later"]')`, "the card form");
      await r.tap('[data-test="move-later"]');
      await r.waitFor(`__j.find('[data-test="toast"]')`, "the toast");
      await sleep(300);
      await checkToastHome(r, "after Move later", phone ? "edit" : "stage");
      // Typing into the form while the toast shows.
      await r.tap('[data-test="form-name"]');
      await r.type("Hall");
      await sleep(200);
      await checkToastHome(r, "while typing the card's name", phone ? "edit" : "stage");
      const shot = await r.screen("74-toast-placement");
      await r.clearSelection();
      // A card removed from the keyboard: focus goes to the next card in the
      // list, and the toast is in the home of the layout without the form.
      await r.eval(`__j.find('[data-test="list-row"][data-source="0.1.1"]').focus(); true`);
      await r.key("Delete");
      await r.waitFor(`__j.find('[data-test="toast-undo"]')`, "the removal's toast");
      check((await focused(r)) === "list-row", `after removing, focus went to ${await focused(r)}`);
      await sleep(400);
      await checkToastHome(r, "after removing a card from the list", phone ? "fab" : "stage");
      await r.screen("74-toast-out-of-the-way");
      if (!phone) {
        await checkToastBesideSidebar(r);
      }
      return shot;
    }),
  ];

  // At 1100 px with Home Assistant's sidebar docked, the panel starts 256 px
  // from the left of the window, and is narrow enough for the one-column
  // layout.
  async function dockSidebar(r) {
    await r.eval(`(() => { const bar = document.createElement("div");
      bar.style.cssText = "position:fixed;left:0;top:0;bottom:0;width:256px;background:#333;z-index:1";
      document.body.prepend(bar);
      __apolloPanel.style.marginLeft = "256px";
      __apolloPanel.style.width = "calc(100% - 256px)";
      return true; })()`);
  }

  // The panel moves over at once, but the editor changes to its one-column
  // layout only once its resize observer has run; anything measured before
  // then moves again. Waits for that layout and one more frame.
  async function settledBesideSidebar(r) {
    await r.waitFor(
      `__j.designer().getBoundingClientRect().left === 256 && __j.find('.root.compact') &&
        __j.find('[data-test="list-row"][data-shown="false"]')`,
      "the panel's one-column layout beside the sidebar",
    );
    await r.eval(`new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve(true))))`);
  }

  // A long toast stays inside the panel beside the docked sidebar, 16 px
  // from its edges, rather than reaching under the sidebar.
  async function checkToastBesideSidebar(r) {
    await r.browser.send("Emulation.setDeviceMetricsOverride", {
      width: 1100,
      height: 800,
      deviceScaleFactor: 1,
      mobile: false,
    });
    try {
      await r.open({ seed: "real", route: "/edit/tab-1" }, editorReady);
      await dockSidebar(r);
      await settledBesideSidebar(r);
      await r.click('[data-test="row-remove"]');
      await r.waitFor(`__j.find('[data-test="toast-replace"]')`, "the removal's toast");
      await sleep(300);
      const places = await r.eval(`({ toast: ${edgesOf(`__j.find('[data-test="toast"]')`)},
        panel: ${edgesOf(`__j.designer()`)} })`);
      const { toast, panel } = places;
      check(
        toast.left >= panel.left + 15 && toast.right <= panel.right - 15,
        `beside the docked sidebar the toast spans ${Math.round(toast.left)}..${Math.round(toast.right)}, ` +
          `the panel ${Math.round(panel.left)}..${Math.round(panel.right)}`,
      );
      await checkToastHome(r, "beside the docked sidebar", "fab");
      await r.screen("74-toast-beside-sidebar");
    } finally {
      await r.viewport();
    }
  }

  // Moving between the panel's screens from the keyboard: focus goes to the
  // new screen's heading, with its ring showing, never to the page itself.
  const screens = [
    step("77", "focus-after-screen-change", async (r) => {
      const press = async (test) => {
        await r.eval(`__j.find('[data-test="${test}"]').focus(); true`);
        check((await focused(r)) === test, `${test} cannot take focus`);
        await r.key("Enter");
      };
      const onHeading = async (text, when) => {
        await r.waitFor(`__j.active()?.tagName === "H1" && __j.active().textContent === ${JSON.stringify(text)}`, `focus on the heading "${text}" ${when}`);
        const ring = await r.eval(`(() => { const element = __j.active(); const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return { visible: element.matches(":focus-visible"), style: style.outlineStyle, width: parseFloat(style.outlineWidth),
            top: rect.top, bottom: rect.bottom, height: innerHeight }; })()`);
        check(ring.visible && ring.style !== "none" && ring.width >= 2, `${when} the heading shows no focus ring: ${JSON.stringify(ring)}`);
        check(ring.top >= 0 && ring.bottom <= ring.height, `${when} the heading is off screen: ${JSON.stringify(ring)}`);
      };
      await r.open({ seed: "sample" }, `${home} && __j.find('[data-test="edit"]')`);
      check((await focused(r)) === null, `opening the panel moved focus to ${await focused(r)}`);
      await press("edit");
      await onHeading("TAB-1", "after Edit");
      const shot = await r.screen("77-focus-after-screen-change");
      await press("back");
      await onHeading("TAB-1 dashboards", "after Back from the editor");
      await press("open-advanced");
      await onHeading("Advanced", "after Advanced");
      await press("back");
      await onHeading("TAB-1 dashboards", "after Back from Advanced");
      await press("edit");
      await onHeading("TAB-1", "after Edit again");
      await r.eval(`history.back(); true`);
      await onHeading("TAB-1 dashboards", "after the browser's Back");
      // Deleting the dashboard leaves the editor for Home.
      await press("edit");
      await onHeading("TAB-1", "after Edit once more");
      await press("dashboard-delete");
      await r.waitFor(`__j.find('dialog[data-test="confirm"][open]')`, "the question");
      await press("confirm-ok");
      await onHeading("TAB-1 dashboards", "after deleting the dashboard");
      check((await r.count('[data-test="dashboard-row"]')) === 0, "the deleted dashboard is still listed");
      await r.screen("77-focus-after-delete");
      return shot;
    }),
  ];

  // Undo in a toast puts focus on the card that came back, in view, rather
  // than on the header's Redo button far above: on its row after a removal
  // in the list, on the picture after a removal there (polish decision 13),
  // where on a phone the page column stays put (decision 10).
  const undoFocus = [
    step("78", "focus-after-toast-undo", async (r) => {
      const count = (section) => `__j.designer()._history.present.views[0].sections[${section}].cards.length`;
      const pictureTop = `__j.find('[data-test="canvas"]').getBoundingClientRect().top`;
      // Removes the card at 0.<section>.1 with Delete on `where` (a list row
      // or the card on the tablet picture), then presses the toast's Undo.
      // Focus goes back to the same kind of control for the card.
      const removeThenUndo = async (where, section, when) => {
        const key = `0.${section}.1`;
        const before = await r.eval(count(section));
        await r.waitFor(`__j.find('[data-test="${where}"][data-source="${key}"]')`, `card ${key} ${when}`);
        await r.eval(`__j.find('[data-test="${where}"][data-source="${key}"]').focus(); true`);
        const top = await r.eval(pictureTop);
        await r.key("Delete");
        await r.waitFor(`${count(section)} === ${before - 1}`, `the card to be removed ${when}`);
        await r.waitFor(`__j.find('[data-test="toast-undo"]')`, `the toast ${when}`);
        await r.eval(`__j.find('[data-test="toast-undo"]').focus(); true`);
        await r.key("Enter");
        await r.waitFor(`${count(section)} === ${before}`, `Undo to bring the card back ${when}`);
        // The picture is drawn again with the card once the preview is in.
        if (where === "hit") {
          await r.waitSaved(when);
          await sleep(500);
        }
        const found = await r.eval(`(() => { const element = __j.active();
          if (!element || element === document.body) return null;
          const rect = element.getBoundingClientRect();
          return { test: element.dataset.test, source: element.dataset.source, top: rect.top, bottom: rect.bottom,
            height: innerHeight, visible: element.matches(":focus-visible"), ring: getComputedStyle(element).outlineStyle }; })()`);
        check(found?.test === where && found.source === key, `${when}, Undo in the toast moved focus to ${JSON.stringify(found)}`);
        check(found.top >= 0 && found.bottom <= found.height, `${when}, the card is off screen: ${JSON.stringify(found)}`);
        check(found.visible && found.ring !== "none", `${when}, the card shows no focus ring: ${JSON.stringify(found)}`);
        if (where === "hit") {
          const after = await r.eval(pictureTop);
          check(Math.abs(after - top) <= 1, `${when}, Undo moved the picture's top from ${top} to ${after}`);
        }
      };
      await openSample(r);
      // A light in the list, then a graph on the tablet picture's first screen.
      await removeThenUndo("list-row", 1, "after Delete in the list");
      const shot = await r.screen("78-focus-after-toast-undo");
      await removeThenUndo("hit", 0, "after Delete on the picture");
      await r.screen("78-focus-after-toast-undo-picture");
      await r.waitSaved("after Undo");
      return shot;
    }),
  ];

  // A card the tablet cannot show that controlled several devices: the
  // picker says the chosen card gets what it can take, and the toast then
  // offers a card for each device left over until none is.
  const several = [
    step("79", "card-for-several-devices", async (r) => {
      const toastText = () => r.text('[data-test="toast"] span');
      const pick = async (component) => {
        await r.click('[data-test="toast-replace"]');
        await r.waitFor(`__j.find('dialog[data-test="picker"][open]') && __j.find('[data-test="tile"]')`, "the picker");
        const words = {
          title: await r.text('dialog[data-test="picker"] h2'),
          intro: await r.text('dialog[data-test="picker"] .picker-top p'),
        };
        await r.click(`[data-test="tile"][data-component="${component}"]`);
        await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
        return words;
      };
      await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
      await r.eval(`__apolloMockHass.addDashboard("several-1", "Several", ${JSON.stringify(SEVERAL_CONFIG)});
        __apolloOpenPanel("/edit/several-1"); true`);
      await r.waitFor(`__j.find('[data-test="row-remove"]')`, "the card that is not shown");
      await r.click('[data-test="row-remove"]');
      await r.waitFor(`__j.find('[data-test="toast-replace"]')`, "the removal's toast");
      check((await toastText()) === "Card removed. Add a TAB-1 card for Kitchen, Bedroom lamp, Bedroom fan.", `the toast reads "${await toastText()}"`);

      const first = await pick("apollo/light");
      check(first.title === "Add a card for Kitchen, Bedroom lamp, Bedroom fan", `the picker is titled "${first.title}"`);
      check(
        first.intro ===
          "Each of these cards can control at least one of Kitchen, Bedroom lamp, Bedroom fan. " +
            "The card you pick gets as many of them as it can take. After that you are offered a card for the rest.",
        `the picker says "${first.intro}"`,
      );
      await r.waitFor(`__j.find('[data-test="toast-replace"]')`, "the toast offering a card for the rest");
      check((await toastText()) === "Card added. Add a TAB-1 card for Bedroom lamp, Bedroom fan.", `the toast reads "${await toastText()}"`);
      // The new card is selected; the toast keeps clear of it, of its row
      // and of the card sheet.
      await sleep(400);
      if (r.setup.device === "phone") {
        // The new card's form is the edit mode, which holds the toast.
        await checkToastHome(r, "after adding a card for one of several devices", "edit");
      } else {
        await checkToastClear(r, "after adding a card for one of several devices");
      }
      const shot = await r.shot("79-card-for-several-devices");

      const second = await pick("apollo/fan-speed");
      check(second.title === "Add a card for Bedroom lamp, Bedroom fan", `the picker is titled "${second.title}"`);
      await r.waitFor(`__j.text('[data-test="toast"] span') === "Card added. Add a TAB-1 card for Bedroom lamp."`, "the toast for the last device");
      const third = await pick("apollo/light");
      check(third.intro === "These cards can control Bedroom lamp. The card you pick gets Bedroom lamp straight away.", `the picker says "${third.intro}"`);
      await r.waitFor(`__j.text('[data-test="toast"] span') === "Card added"`, "the toast once every device has a card");
      check((await r.count('[data-test="toast-replace"]')) === 0, "a card is still offered once every device has one");
      await r.waitSaved("three cards added");
      const saved = (await r.config("several-1")).views[0].sections[0].cards.map((card) => [card.component, card.params?.entity]);
      check(
        stable(saved) ===
          stable([
            ["apollo/light", "light.kitchen"],
            ["apollo/fan-speed", "fan.bedroom_main_bedroom_fan"],
            ["apollo/light", "light.bedroom"],
          ]),
        `the dashboard holds ${JSON.stringify(saved)}`,
      );
      return shot;
    }),
  ];

  // A toast offering Undo, or a card for the devices left over, belongs to
  // the change it reports, so it goes once anything else changes. Focus in a
  // toast that goes, or is replaced, moves on to a safe control.
  const toastLife = [
    step("82", "toast-follows-changes", async (r) => {
      const cards = `__j.designer()._history.present.views[0].sections[1].cards.length`;
      await openSample(r);
      const all = await r.eval(cards);
      // Removed, then another card made taller: Undo in the toast would now
      // undo Taller.
      await selectRow(r, "0.1.1");
      await r.click('[data-test="remove-card"]');
      await r.waitFor(`__j.find('[data-test="toast-undo"]')`, "the removal's toast");
      await sleep(300);
      await checkToastHome(r, "after Remove in the card's form", r.setup.device === "phone" ? "fab" : "stage");
      await selectRow(r, "0.1.0");
      check((await r.count('[data-test="toast-undo"]')) === 1, "choosing another card took the toast away");
      await r.click('[data-test="taller"]');
      await r.waitFor(`!__j.find('[data-test="toast-undo"]')`, "the toast to go once another card changed", 2000);
      check((await r.eval(cards)) === all - 1, "the removed card came back");
      // Removed, then brought back with the header's Undo.
      await selectRow(r, "0.1.1");
      await r.click('[data-test="remove-card"]');
      await r.waitFor(`__j.find('[data-test="toast-undo"]')`, "the second removal's toast");
      await r.click('[data-test="undo"]');
      await r.waitFor(`${cards} === ${all - 1}`, "the header's Undo to bring the card back");
      await sleep(200);
      check((await r.count('[data-test="toast-undo"]')) === 0, "the toast still offers Undo after the header's Undo");
      const shot = await r.shot("82-toast-follows-changes");

      // A toast with focus that is replaced by another toast.
      await r.waitSaved("after the header's Undo");
      await r.eval(`__j.find('[data-test="list-row"][data-source="0.1.1"]').focus(); true`);
      await r.key("Delete");
      await r.waitFor(`__j.find('[data-test="toast-undo"]')`, "the third removal's toast");
      await r.waitSaved("after removing");
      await r.eval(`__j.find('[data-test="toast-undo"]').focus(); true`);
      await saveElsewhere(r, `(config) => { config.views[1].title = "Elsewhere"; }`);
      await r.waitFor(
        `__j.find('[data-test="toast"]') && !__j.find('[data-test="toast-undo"]')`,
        "the toast about the other browser's change",
      );
      let now = await focused(r);
      check(now && !REMOVING.includes(now), `when the toast with focus was replaced, focus went to ${now}`);

      // Ctrl+Z with focus on the toast of the old dashboard: the card is
      // back, so the toast's offer of a card for its device goes.
      await r.open({ seed: "real", route: "/edit/tab-1" }, editorReady);
      await r.waitFor(`__j.find('[data-test="list-row"][data-shown="false"]')`, "the list to know what is shown");
      await r.eval(`__j.find('[data-test="row-remove"]').focus(); true`);
      await r.key("Enter");
      await r.waitFor(`__j.find('[data-test="toast-replace"]')`, "the toast offering a TAB-1 card");
      check((await focused(r)) === "toast-replace", `after removing, focus went to ${await focused(r)}`);
      await shortcut(r, "z");
      await r.waitFor(
        `JSON.stringify(__j.designer()._history.present).includes("custom:bubble-card")`,
        "Ctrl+Z to bring the card back",
      );
      await sleep(200);
      check((await r.count('[data-test="toast-replace"]')) === 0, "the toast still offers a card for the card that came back");
      now = await focused(r);
      check(now && !REMOVING.includes(now), `after Ctrl+Z focus went to ${now}`);
      return shot;
    }),
  ];

  // Keyboard focus never hides under the phone layout's card sheet, and
  // "Use the whole screen" from the keyboard leaves focus on the page.
  const sheetFocus = [
    step("83", "focus-clear-of-sheet", async (r) => {
      // Tabs through every control from Back round to Back: the centre of
      // each one is on screen and not under anything else.
      // With the edit mode open (on a phone, or beside the docked sidebar) the
      // page behind is inert: the walk goes through the top bar and the
      // edit mode only.
      const walk = async (when, least = 21) => {
        await r.eval(`scrollTo(0, 0); __j.find('[data-test="back"]').focus(); true`);
        let stops = 0;
        for (let press = 0; press < 160; press += 1) {
          await r.key("Tab");
          const stop = await r.eval(`(() => { const element = __j.active();
            if (!element || element === document.body) return null;
            const rect = element.getBoundingClientRect();
            const x = Math.round(rect.left + rect.width / 2);
            const y = Math.round(rect.top + rect.height / 2);
            const on = x >= 0 && y >= 0 && x < innerWidth && y < visualViewport.offsetTop + visualViewport.height;
            const hit = on ? __j.at(x, y) : null;
            const labelled = Boolean(element.labels) && [...element.labels].some((label) => __j.inside(label, hit));
            const covered = on && !__j.inside(element, hit) && !labelled;
            return { name: __j.describe(element) + (element.dataset.focus ? "{" + element.dataset.focus + "}" : ""),
              back: element.dataset.test === "back", on, covered, by: covered ? __j.describe(hit) : "", x, y }; })()`);
          // Focus leaves the page after its last control.
          if (!stop) {
            if (stops) break;
            continue;
          }
          if (stop.back) break;
          stops += 1;
          check(stop.on, `${when}: ${stop.name} has focus off screen at ${stop.x},${stop.y}`);
          check(!stop.covered, `${when}: ${stop.name} has focus under ${stop.by} at ${stop.x},${stop.y}`);
        }
        check(stops >= least, `${when}: only ${stops} controls took focus`);
      };
      await openSample(r);
      await selectRow(r, "0.1.0");
      await walk("with a card selected", (await inEditMode(r)) ? 12 : 21);
      const shot = await r.screen("83-focus-clear-of-sheet");
      if (!r.setup.mobile) {
        // Beside Home Assistant's docked sidebar the panel uses the
        // one-column layout with the sheet too.
        await r.browser.send("Emulation.setDeviceMetricsOverride", {
          width: 1100,
          height: 800,
          deviceScaleFactor: 1,
          mobile: false,
        });
        try {
          await openSample(r);
          await dockSidebar(r);
          await r.waitFor(`__j.designer().getBoundingClientRect().left === 256 && __j.find('.root.compact')`, "the one-column layout");
          await selectRow(r, "0.1.0");
          await walk("beside the docked sidebar with a card selected", (await inEditMode(r)) ? 12 : 21);
          await r.screen("83-focus-clear-of-sheet-docked");
        } finally {
          await r.viewport();
        }
      }
      return shot;
    }),
    step("84", "whole-screen-by-keyboard", async (r) => {
      for (const selected of [null, "0.1.1"]) {
        await openSample(r);
        if (selected && r.setup.device === "phone") {
          // On a phone the notice is under the edit mode. The card's form
          // has the same button once the card is as wide as the columns
          // allow, so it is pressed there, with the card still selected.
          await selectRow(r, selected);
          for (let press = 0; press < 6 && !(await r.count('[data-test="card-whole-screen"]')); press += 1) {
            await r.tap('[data-test="wider"]');
            await sleep(200);
          }
          check((await r.count('[data-test="card-whole-screen"]')) === 1, "the card's form offers no Use the whole screen");
          await r.eval(`__j.find('[data-test="card-whole-screen"]').focus(); true`);
          await r.key("Enter");
          await r.waitFor(`!__j.find('[data-test="card-whole-screen"]') && !__j.find('[data-test="use-whole-screen"]')`, "the advice to go from the card's form");
          await sleep(300);
          const now = await focused(r);
          check(now, "after Use the whole screen in the card's form, focus fell to the page");
          check(!REMOVING.includes(now), `after Use the whole screen in the card's form, focus went to ${now}`);
          check(await r.count('[data-test="side"][data-mode="edit"]'), "after Use the whole screen in the card's form the card is no longer selected");
          continue;
        }
        if (selected) {
          await selectRow(r, selected);
        }
        await openNotices(r);
        await r.eval(`__j.find('[data-test="use-whole-screen"]').focus(); true`);
        await r.key("Enter");
        await r.waitFor(`!__j.find('[data-test="use-whole-screen"]')`, "the advice to go");
        await sleep(300);
        const now = await focused(r);
        const when = selected ? "with a card selected" : "with no card selected";
        check(now, `after Use the whole screen ${when}, focus fell to the page`);
        check(!REMOVING.includes(now), `after Use the whole screen ${when}, focus went to ${now}`);
      }
      return r.screen("84-whole-screen-by-keyboard");
    }),
  ];

  // Home says which dashboard holds a change that is not saved yet, and
  // the editor's Back button asks before leaving one.
  const notSaved = [
    step("85", "home-kept-change", async (r) => {
      const line = `__j.text('[data-test="dashboard-row"][data-url-path="tab-1"] [data-test="row-kept-change"]')`;
      // Waiting for a choice, once the background try found another version.
      await keepChange(r, { offline: true });
      await r.eval(`__apolloOpenPanel(""); true`);
      await r.waitFor(`${home} && ${line}.includes("waiting for your choice")`, "Home to say the change waits for a choice");
      const shot = await r.shot("85-home-kept-change");
      // Still trying; the line goes once the change is saved.
      await keepChange(r, { offline: false });
      await r.eval(`__apolloOpenPanel(""); true`);
      await r.waitFor(`${home} && ${line}.includes("It keeps trying")`, "Home to say the change is not saved yet");
      await r.eval(`__apolloMockHass.failSaves(0); true`);
      await r.waitFor(`${home} && !__j.find('[data-test="row-kept-change"]')`, "the line to go once the change is saved", 15000);
      return shot;
    }),
    step("88", "back-with-unsaved-change", async (r) => {
      await openSample(r);
      await selectRow(r, "0.1.0");
      await r.eval(`__apolloMockHass.failSaves(100); true`);
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.saveState() === "error"`, "the save to fail");
      await r.eval(`__j.find('[data-test="back"]').focus(); true`);
      await r.key("Enter");
      await r.waitFor(`__j.find('dialog[data-test="confirm"][open]')`, "the question before leaving");
      const words = await r.text('dialog[data-test="confirm"]');
      check(words.includes("Your last change is not saved yet") && words.includes("keeps trying in the background"), `the question reads "${words}"`);
      const shot = await r.shot("88-back-with-unsaved-change");
      // Stay keeps the editor open, with focus back on Back.
      await r.click('[data-test="confirm-cancel"]');
      await r.waitFor(`!__j.find('dialog[data-test="confirm"][open]')`, "the question to close");
      check((await r.count('[data-test="canvas"]')) === 1, "Stay left the editor");
      check((await focused(r)) === "back", `after Stay focus went to ${await focused(r)}`);
      // Leave goes to Home, which says the change is not saved yet.
      await r.click('[data-test="back"]');
      await r.waitFor(`__j.find('dialog[data-test="confirm"][open]')`, "the question again");
      await r.click('[data-test="confirm-ok"]');
      await r.waitFor(`${home} && __j.find('[data-test="row-kept-change"]')`, "Home with the line about the change");
      check(await leavingAsks(r), "closing the browser page would not ask about the change");
      await r.eval(`__apolloMockHass.failSaves(0); true`);
      return shot;
    }),
  ];

  // A dial or graph over a screen's limit is moved to another page, a card
  // left out on a later screen is shown on that screen, and a page whose
  // only card is left out is not taken for an empty one.
  const moving = [
    step("86", "move-to-page", async (r) => {
      const onPage = (view) => `__j.designer()._history.present.views[${view}].sections[0].cards.length`;
      const dashboard = async (urlPath, config) => {
        await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
        await r.eval(`__apolloMockHass.addDashboard("${urlPath}", "Dials", ${JSON.stringify(config)});
          __apolloOpenPanel("/edit/${urlPath}"); true`);
      };
      await dashboard("dials-1", DIALS_CONFIG);
      await r.waitFor(`__j.find('[data-test="row-move"]')`, "Move to page beside the dial that is left out");
      const reason = await r.text('[data-test="list-row"][data-shown="false"] .row-reason');
      check(reason.includes("Move it to another page"), `the list says "${reason}"`);
      await r.click('[data-test="row-move"]');
      await r.waitFor(`__j.active()?.dataset?.test === "move-page"`, "focus on Move to page");
      const options = await r.eval(`[...__j.find('[data-test="move-page"]').options].map((option) => option.textContent)`);
      check(stable(options) === stable(["Climate", "New page"]), `Move to page offers ${options.join(", ")}`);
      const shot = await r.shot("86-move-to-page");
      await r.click('[data-test="move-page-go"]');
      await r.waitFor(`__j.find('[data-test="page-tab"][data-view="1"][aria-selected="true"]')`, "the page the dial moved to");
      await r.waitFor(`__j.text('[data-test="toast"] span') === "Moved to Climate"`, "the toast saying where it went");
      await r.waitFor(`__j.find('[data-test="hit"][data-source="1.0.0"][aria-pressed="true"]')`, "the moved dial to stay selected");
      await r.waitSaved("after the move");
      let saved = await r.config("dials-1");
      check(
        saved.views[0].sections[0].cards.length === 4 && saved.views[1].sections[0].cards.length === 1,
        `after the move the pages hold ${saved.views[0].sections[0].cards.length} and ${saved.views[1].sections[0].cards.length} dials`,
      );
      await leaveEditMode(r);
      await r.click('[data-test="page-tab"][data-view="0"]');
      await r.waitFor(
        `__j.count('[data-test="list-row"][data-shown="true"]') === 4 && !__j.find('[data-test="list-row"][data-shown="false"]')`,
        "Home with nothing left out",
      );
      await r.shot("86-move-to-page-done");
      // Undo puts the dial back; it can go to a new page too.
      await r.click('[data-test="undo"]');
      await r.waitFor(`${onPage(0)} === 5 && ${onPage(1)} === 0`, "Undo to bring the dial back");
      await r.waitFor(`__j.find('[data-test="row-move"]')`, "the dial left out again");
      await leaveEditMode(r);
      await r.click('[data-test="row-move"]');
      await r.waitFor(`__j.active()?.dataset?.test === "move-page"`, "focus on Move to page again");
      await r.eval(`(() => { const field = __j.find('[data-test="move-page"]'); field.value = "new";
        field.dispatchEvent(new Event("change")); return true; })()`);
      await r.click('[data-test="move-page-go"]');
      await r.waitFor(`__j.find('[data-test="page-tab"][data-view="2"][aria-selected="true"]')`, "the new page");
      await r.waitSaved("after the move to a new page");
      saved = await r.config("dials-1");
      check(saved.views.length === 3 && saved.views[2].title === "New page", `the new page is called ${saved.views[2]?.title}`);
      check(saved.views[2].sections[0].cards.length === 1 && saved.views[0].sections[0].cards.length === 4, "the dial did not move to the new page");
      return shot;
    }),
    step("87", "left-out-card-screen", async (r) => {
      await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
      await r.eval(`__apolloMockHass.addDashboard("spill-1", "Spill", ${JSON.stringify(SPILL_CONFIG)});
        __apolloOpenPanel("/edit/spill-1"); true`);
      await r.waitFor(`__j.find('[data-test="list-row"][data-source="0.0.28"][data-shown="false"]')`, "the dial left out");
      await r.waitFor(`__j.find('[data-test="screen-next"]') && __j.designer()._screen === 0`, "the first of two screens");
      await r.click('[data-test="list-row"][data-source="0.0.28"]');
      await r.waitFor(`__j.find('[data-test="hit"][data-source="0.0.28"][aria-pressed="true"]')`, "the dial's box on the picture");
      check((await r.eval(`__j.designer()._screen`)) === 1, "the picture does not show the second screen");
      check((await r.count(".warning-box")) >= 1, "the picture shows no box for the dial left out");
      // On a wide screen the long list has scrolled the picture away; the
      // phone layout scrolls it back above the card sheet by itself.
      if (!r.setup.mobile) {
        await r.eval(`__j.find('[data-test="canvas"]').scrollIntoView({ block: "start" }); true`);
      }
      await checkSelectedCardVisible(r, "after choosing the dial left out");
      return r.shot("87-left-out-card-screen");
    }),
    step("201", "left-out-only-card", async (r) => {
      const hit = '[data-test="hit"][data-source="0.0.0"]';
      await r.open({ seed: "none", graphs: "1" }, `${home} && __j.find('[data-test="create"]')`);
      await r.eval(`__apolloMockHass.addDashboard("graphs-1", "Graphs", ${JSON.stringify(GRAPHS_CONFIG)});
        __apolloOpenPanel("/edit/graphs-1"); true`);
      await r.waitFor(`__j.designer()?._preview?.layout`, "what the tablet will show");
      await r.waitFor(`__j.find('[data-test="list-row"][data-source="0.0.0"][data-shown="false"]')`, "the card left out");
      // The tablet's page has no card at all, only the note about this one.
      const converted = await r.eval(`(() => { const preview = __j.designer()._preview;
        return { cards: preview.layout.pages[0].w.length, notes: preview.warnings.map((warning) => warning.code) }; })()`);
      check(
        converted.cards === 0 && stable(converted.notes) === stable(["over_budget_charts"]),
        `the page was converted to ${JSON.stringify(converted)}`,
      );
      await r.waitFor(`__j.find(".warning-box") || __j.find('[data-test="add-first-card"]')`, "the picture of the page");
      check((await r.count('[data-test="add-first-card"]')) === 0, "the picture offers a first card on a page that has a card");
      check((await r.count(".empty-page")) === 0, "the picture calls a page with a card empty");
      check((await r.count(".warning-box")) === 1, "the picture has no box for the card left out");
      const words = await r.text(".warning-box");
      check(words === (await uiString(r, "preview.omitted")), `the box reads "${words}"`);
      check((await r.count('[data-test="hit"]')) === 1, "the card left out cannot be chosen on the picture");
      const label = await r.eval(`__j.find('${hit}').getAttribute("aria-label")`);
      check(label.startsWith("Five graphs, ") && label.endsWith("Item 1 of 1."), `the box is called "${label}"`);
      // Its box on the picture chooses it, like any card's.
      await r.click(hit);
      await r.waitFor(`__j.find('${hit}[aria-pressed="true"]')`, "the card left out to be chosen");
      await checkSelectedCardVisible(r, "after choosing the only card, which is left out");
      const shot = await r.shot("201-left-out-only-card");
      // The second page has no card: that one is empty.
      await r.clearSelection();
      await r.click('[data-test="page-tab"][data-view="1"]');
      await r.waitFor(`__j.find('[data-test="add-first-card"]')`, "the help for a page without cards");
      check((await r.count(".warning-box")) === 0, "the empty page shows a box for a card left out");
      return shot;
    }),
  ];

  // The page tabs scroll on a narrow screen while Add page stays in view.
  const narrowTabs = [
    step("89", "add-page-in-view", async (r) => {
      const inView = (when) =>
        r.eval(`(() => { const button = __j.find('[data-test="add-page"]'); const rect = button.getBoundingClientRect();
          const hit = __j.at(Math.round(rect.left + rect.width / 2), Math.round(rect.top + rect.height / 2));
          return rect.left >= 0 && rect.right <= innerWidth && __j.inside(button, hit); })()`).then((ok) =>
          check(ok, `${when}: Add page is not wholly in view`),
        );
      await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
      await r.click('[data-test="create"]');
      await r.waitFor(`__j.find('[data-test="add-first-card"]')`, "the empty editor");
      for (const count of [2, 3, 4]) {
        await r.click('[data-test="add-page"]');
        await r.waitFor(`__j.count('[data-test="page-tab"]') === ${count}`, `page ${count}`);
        await inView(`with ${count} pages`);
      }
      await r.click('[data-test="page-tab"][data-view="0"]');
      await inView("with the first page shown");
      await r.eval(`__j.find('[data-test="page-tab"][data-view="3"]').scrollIntoView({ inline: "nearest" }); true`);
      await r.click('[data-test="page-tab"][data-view="3"]');
      await inView("with the last page shown");
      return r.screen("89-add-page-in-view");
    }),
  ];

  // Ctrl+Z undoes from a list, tick box, slider or colour that keeps focus
  // after it was used; only fields that take typing keep their own undo.
  const shortcuts = [
    step("90", "undo-from-a-list", async (r) => {
      await openSample(r);
      const before = await r.eval(`__j.designer()._history.present.apollo_tab.theme`);
      await r.eval(`(() => { const field = __j.find('[data-test="theme"]'); field.focus();
        field.value = [...field.options].map((option) => option.value).find((value) => value !== field.value);
        field.dispatchEvent(new Event("change", { bubbles: true })); return true; })()`);
      await r.waitFor(`__j.designer()._history.present.apollo_tab.theme !== ${JSON.stringify(before)}`, "the new theme");
      check((await focused(r)) === "theme", `after choosing a theme focus is on ${await focused(r)}`);
      await shortcut(r, "z");
      await r.waitFor(`__j.designer()._history.present.apollo_tab.theme === ${JSON.stringify(before)}`, "Ctrl+Z to bring the theme back", 3000);
      return r.screen("90-undo-from-a-list");
    }),
  ];

  // The Tablets box on Home: three stand-in tablets, a "Night" dashboard
  // beside TAB-1, and the dashboard each one shows changed from Home.
  const threeTablets = { seed: "sample", night: "1", tablets: "three" };
  const tabletsHome = [
    step("92", "tablets-on-home", async (r) => {
      await r.open(
        threeTablets,
        `${home} && __j.count('[data-test="tablet-row"]') === 3 && __j.count('[data-test="dashboard-row"]') === 2`,
      );
      const names = await r.eval(`__j.all('[data-test="tablet-row"]').map((row) => row.querySelector(".tablet-name").textContent)`);
      check(
        JSON.stringify(names) === JSON.stringify(["Bedroom tablet", "Hallway tablet", "Kitchen tablet"]),
        `the tablets read ${JSON.stringify(names)}`,
      );
      await waitText(r, tabletStatus(KITCHEN), "On the tablet", "the kitchen tablet's status");
      check((await r.text(tabletStatus(HALLWAY))) === "Offline", `the hallway tablet reads "${await r.text(tabletStatus(HALLWAY))}"`);
      check(
        (await r.text(tabletStatus(BEDROOM))) === "Waiting for tablet software",
        `the bedroom tablet reads "${await r.text(tabletStatus(BEDROOM))}"`,
      );
      check(
        (await r.text(`${tabletRow(BEDROOM)} [data-test="tablet-help"]`)) === (await uiString(r, "tablets.no_engine_help")),
        "the bedroom tablet has no helper line about the tablet software",
      );
      const shows = await r.eval(`[${JSON.stringify([KITCHEN, HALLWAY, BEDROOM])}].flat().map((mac) =>
        __j.find('[data-test="tablet-row"][data-mac="' + mac + '"] [data-test="tablet-shows"]').value)`);
      check(JSON.stringify(shows) === JSON.stringify(["tab-1", "night", "tab-1"]), `the tablets show ${JSON.stringify(shows)}`);
      // A screen reader names each list with its tablet.
      await r.browser.send("Accessibility.enable");
      const { nodes } = await r.browser.send("Accessibility.getFullAXTree");
      await r.browser.send("Accessibility.disable");
      const listNames = nodes
        .filter((node) => !node.ignored && node.role?.value === "combobox")
        .map((node) => String(node.name?.value ?? ""));
      check(
        JSON.stringify(listNames) === JSON.stringify(["Bedroom tablet Shows", "Hallway tablet Shows", "Kitchen tablet Shows"]),
        `the Shows lists are named ${JSON.stringify(listNames)}`,
      );
      // One order everywhere: title in lower case, then address.
      const choices = await r.eval(`[...__j.find(${JSON.stringify(tabletShows(KITCHEN))}).options].map((option) => option.textContent)`);
      check(JSON.stringify(choices) === JSON.stringify(["Night", "TAB-1"]), `the Shows list holds ${JSON.stringify(choices)}`);
      const rows = await r.eval(`__j.all('[data-test="dashboard-row"]').map((row) => row.dataset.urlPath)`);
      check(JSON.stringify(rows) === JSON.stringify(["night", "tab-1"]), `the dashboards are listed as ${JSON.stringify(rows)}`);
      await waitText(r, shownOnLine("tab-1"), "Shown on: Bedroom, Kitchen", "the Shown on line of TAB-1");
      await waitText(r, shownOnLine("night"), "Shown on: Hallway", "the Shown on line of Night");
      // The box sits above "Your dashboards" and has no tick boxes: locks,
      // alarms and garage doors need no switch per tablet.
      const above = await r.eval(`__j.find('[data-test="tablets"]').getBoundingClientRect().bottom <=
        __j.find('[data-test="dashboard-row"]').getBoundingClientRect().top`);
      check(above, "the Tablets box is not above the dashboards");
      check((await r.count('[data-test="tablet-row"] input[type="checkbox"]')) === 0, "a tablet row has a tick box");
      const words = await r.text('[data-test="home"]');
      check(!/not sent to tablets/i.test(words), "Home still says dashboards are not sent to tablets");
      await checkTextContrast(r, [
        tabletStatus(KITCHEN),
        tabletStatus(HALLWAY),
        tabletShows(KITCHEN),
        `${tabletRow(BEDROOM)} [data-test="tablet-help"]`,
        `${tabletRow(KITCHEN)} .tablet-name`,
        shownOnLine("tab-1"),
      ]);
      return r.shot("92-tablets-on-home");
    }),
    step("93", "shows-sending-then-on", async (r) => {
      await r.eval(`__apolloMockHass.holdSends(); window.__shows = __j.find(${JSON.stringify(tabletShows(KITCHEN))}); true`);
      await pickShows(r, KITCHEN, "night");
      await waitText(r, tabletStatus(KITCHEN), "Sending…", "Sending… after picking Night");
      const calls = await r.calls("apollo_tab/tablet/assign");
      check(
        calls.length === 1 && calls[0].mac === KITCHEN && calls[0].url_path === "night",
        `the change sent ${JSON.stringify(calls)}`,
      );
      const tone = await r.eval(`__j.find(${JSON.stringify(tabletStatus(KITCHEN))}).dataset.tone`);
      check(tone === "busy", `while sending the status tone is ${tone}`);
      // The list was changed in place: the same element, still with focus.
      const same = await r.eval(`__j.find(${JSON.stringify(tabletShows(KITCHEN))}) === window.__shows && __j.active() === window.__shows
        && window.__shows.value === "night"`);
      check(same, "the Shows list was drawn again or lost focus");
      await waitText(r, shownOnLine("night"), "Shown on: Hallway, Kitchen", "the Night row to name the kitchen tablet");
      await waitText(r, shownOnLine("tab-1"), "Shown on: Bedroom", "the TAB-1 row to drop the kitchen tablet");
      const shot = await r.screen("93-tablet-sending");
      await r.eval(`__apolloMockHass.finishSends(); true`);
      await waitText(r, tabletStatus(KITCHEN), "On the tablet", "On the tablet once the tablet has it");
      check(
        (await r.eval(`__j.find(${JSON.stringify(tabletStatus(KITCHEN))}).dataset.tone`)) === "ok",
        "the status tone is not ok on the tablet",
      );

      // An offline tablet keeps the choice and gets it when it is back.
      await pickShows(r, HALLWAY, "tab-1");
      await waitText(r, shownOnLine("tab-1"), "Shown on: Bedroom, Hallway", "the TAB-1 row to name the hallway tablet");
      check((await r.text(tabletStatus(HALLWAY))) === "Offline", "the offline tablet no longer reads Offline");
      await r.eval(`__apolloMockHass.holdSends(); __apolloMockHass.setTablet(${JSON.stringify(HALLWAY)}, { online: true }); true`);
      await waitText(r, tabletStatus(HALLWAY), "Sending…", "Sending… once the hallway tablet is back");
      await r.eval(`__apolloMockHass.finishSends(); true`);
      await waitText(r, tabletStatus(HALLWAY), "On the tablet", "On the tablet for the hallway tablet");

      // A change Home Assistant refuses says so and puts the choice back.
      await r.eval(`__apolloMockHass.failCalls("apollo_tab/tablet/assign", 1); true`);
      await pickShows(r, BEDROOM, "night");
      await r.waitFor(`__j.find('${tabletRow(BEDROOM)} [data-test="tablet-error"]')`, "the line about the failed change");
      await r.waitFor(`__j.find(${JSON.stringify(tabletShows(BEDROOM))}).value === "tab-1"`, "the choice to go back to TAB-1");
      await checkTextContrast(r, [`${tabletRow(BEDROOM)} [data-test="tablet-error"]`, tabletStatus(KITCHEN)]);
      await r.shot("93-tablets-after-changes");
      // Trying again works and clears the line.
      await pickShows(r, BEDROOM, "night");
      await r.waitFor(`!__j.find('${tabletRow(BEDROOM)} [data-test="tablet-error"]')`, "the line about the failure to go");
      await waitText(r, shownOnLine("night"), "Shown on: Bedroom, Kitchen", "the Night row to name the bedroom tablet");
      return shot;
    }),
  ];

  // The editor: the lines above the tablet picture, the "Shown on" block in
  // the dashboard's settings, and the delete question that names tablets.
  const tabletsEditor = [
    step("94", "editor-caption", async (r) => {
      await r.open({ ...threeTablets, route: "/edit/tab-1" }, `(${editorReady}) && __j.count('[data-test="tablet-line"]') === 2`);
      await waitCaption(r, ["Waiting for tablet software (Bedroom tablet)", "On Kitchen tablet"], "a line per tablet");
      const words = await r.eval(`__j.designer().shadowRoot.textContent`);
      check(!/not sent to tablets/i.test(words), "the editor still says dashboards are not sent to tablets");
      // The lines follow the tablets as they change.
      await r.eval(`__apolloMockHass.holdSends(); __apolloMockHass.setTablet(${JSON.stringify(KITCHEN)}, { online: false }); true`);
      await waitCaption(r, ["Waiting for tablet software (Bedroom tablet)", "Kitchen tablet is offline"], "the offline line");
      await r.eval(`__apolloMockHass.setTablet(${JSON.stringify(KITCHEN)}, { online: true }); true`);
      await waitCaption(r, ["Waiting for tablet software (Bedroom tablet)", "Sending to Kitchen tablet…"], "the sending line");
      await r.eval(`__j.find('[data-test="tablet-lines"]').scrollIntoView({ block: "center" }); true`);
      await checkTextContrast(r, ['[data-test="tablet-line"][data-kind="tablet"]']);
      const shot = await r.screen("94-editor-caption");
      await r.eval(`__apolloMockHass.finishSends(); true`);
      await waitCaption(r, ["Waiting for tablet software (Bedroom tablet)", "On Kitchen tablet"], "the line once sent");
      return shot;
    }),
    step("95", "settings-shown-on", async (r) => {
      await r.waitFor(`__j.find('[data-test="shown-on"]') && __j.count('[data-test="shown-on-row"]') === 3`, "the Shown on block");
      await r.eval(`__j.find('[data-test="shown-on"]').scrollIntoView({ block: "center" }); true`);
      const rows = await r.eval(`__j.all('[data-test="shown-on-row"]').map((row) =>
        [row.dataset.here, row.querySelector(".shown-on-text").innerText.replace(/\\s+/g, " ").trim(), Boolean(row.querySelector('[data-test="show-here"]'))])`);
      const expected = [
        ["true", "Bedroom tablet shows this dashboard", false],
        ["false", "Hallway tablet shows Night", true],
        ["true", "Kitchen tablet shows this dashboard", false],
      ];
      check(JSON.stringify(rows) === JSON.stringify(expected), `the Shown on block reads ${JSON.stringify(rows)}`);
      const name = await r.text('[data-test="automation-name"]');
      check(/Name for automations/.test(name) && /tab-1/.test(name), `the name for automations reads "${name}"`);
      check(
        (await r.text('[data-test="shown-on"] .helper')) === (await uiString(r, "editor.on_tablet_helper")),
        "no helper line under the tablets",
      );
      // On a phone the settings are in the page column, in the idle holder.
      const holder = r.setup.device === "phone" ? "idle" : "side";
      const problems = await r.eval(`__j.overflowProblems(__j.find('[data-test="${holder}"]'))`);
      check(problems.length === 0, `the settings: ${problems.join("; ")}`);
      await checkTextContrast(r, [
        `[data-test="show-here"][data-mac="${HALLWAY}"]`,
        '[data-test="shown-on-row"] .small',
        '[data-test="automation-name"] code',
        '[data-test="shown-on"] .helper',
      ]);
      const before = await r.shot("95-settings-shown-on");

      await r.click(`[data-test="show-here"][data-mac="${HALLWAY}"]`);
      await r.waitFor(`__j.find('[data-test="shown-on-row"][data-mac="${HALLWAY}"]')?.dataset.here === "true"`, "the hallway tablet to show it");
      const calls = await r.calls("apollo_tab/tablet/assign");
      check(
        calls.length === 1 && calls[0].mac === HALLWAY && calls[0].url_path === "tab-1",
        `Show this dashboard sent ${JSON.stringify(calls)}`,
      );
      check((await r.count('[data-test="show-here"]')) === 0, "a Show this dashboard button is left");
      // The pressed button is gone; focus waits on the block's heading.
      const focus = await r.eval(`__j.active()?.dataset?.focus || __j.describe(__j.active())`);
      check(focus === "shown-on-heading", `after Show this dashboard focus is on ${focus}`);
      await waitCaption(
        r,
        ["Waiting for tablet software (Bedroom tablet)", "Hallway tablet is offline", "On Kitchen tablet"],
        "the caption to add the hallway tablet",
      );
      await r.shot("95-settings-tablet-moved");
      return before;
    }),
    step("96", "delete-names-tablets", async (r) => {
      // While the dashboards cannot be read, the question does not say where
      // the tablets go: the list from before could name a deleted dashboard.
      await r.eval(`__apolloMockHass.failCalls("apollo_tab/dashboards", 99); true`);
      await r.click('[data-test="dashboard-delete"]');
      await r.waitFor(`__j.find('dialog[data-test="confirm"][open]')`, "the question without the dashboards");
      await r.eval(`__apolloMockHass.failCalls("apollo_tab/dashboards", 0); true`);
      const guessed = await r.eval(`__j.find('[data-test="confirm-more"]')?.textContent ?? null`);
      check(guessed === null, `without the dashboards the question says "${guessed}"`);
      await r.click('[data-test="confirm-cancel"]');
      await r.waitFor(`!__j.find('dialog[data-test="confirm"][open]')`, "the question to close");

      await r.click('[data-test="dashboard-delete"]');
      await r.waitFor(`__j.find('dialog[data-test="confirm"][open]') && __j.find('[data-test="confirm-more"]')`, "the question");
      const more = await r.text('[data-test="confirm-more"]');
      check(
        more === "Bedroom tablet, Hallway tablet and Kitchen tablet show this dashboard. They will switch to Night.",
        `the question says "${more}"`,
      );
      const described = await r.eval(`__j.find('dialog[data-test="confirm"]').getAttribute("aria-describedby") || ""`);
      check(described.split(" ").includes("confirm-more"), `the dialog is described by "${described}"`);
      await checkTextContrast(r, ['[data-test="confirm-more"]']);
      const shot = await r.screen("96-delete-names-tablets");
      await r.click('[data-test="confirm-ok"]');
      await r.waitFor(`${home} && __j.count('[data-test="dashboard-row"]') === 1 && __j.count('[data-test="tablet-row"]') === 3`, "Home without TAB-1");
      await r.waitFor(
        `[${JSON.stringify([KITCHEN, HALLWAY, BEDROOM])}].flat().every((mac) =>
          __j.find('[data-test="tablet-row"][data-mac="' + mac + '"] [data-test="tablet-shows"]')?.value === "night")`,
        "every tablet to show Night",
      );
      await waitText(r, shownOnLine("night"), "Shown on: Bedroom, Hallway, Kitchen", "the Night row to name all three");
      await r.shot("96-after-delete");
      return shot;
    }),
    step("97", "no-dashboards-then-first", async (r) => {
      await r.click('[data-test="dashboard-row"][data-url-path="night"] [data-test="edit"]');
      await r.waitFor(editorReady, "the Night editor");
      await r.click('[data-test="dashboard-delete"]');
      await r.waitFor(`__j.find('[data-test="confirm-more"]')`, "the question");
      const more = await r.text('[data-test="confirm-more"]');
      check(
        more === "Bedroom tablet, Hallway tablet and Kitchen tablet show this dashboard. They will have nothing to show.",
        `the question says "${more}"`,
      );
      await r.click('[data-test="confirm-ok"]');
      await r.waitFor(
        `${home} && __j.count('[data-test="dashboard-row"]') === 0 && __j.count('[data-test="tablet-make-first"]') === 3`,
        "Home with no dashboards",
      );
      check((await r.count('[data-test="tablet-shows"]')) === 0, "a Shows list is left with nothing to pick");
      check((await r.text('[data-test="tablet-make-first"]')) === "Make a dashboard first.", "no Make a dashboard first.");
      await waitText(r, tabletStatus(KITCHEN), "Nothing to show yet", "the kitchen tablet to have nothing to show");
      await checkTextContrast(r, ['[data-test="tablet-make-first"]', tabletStatus(KITCHEN)]);
      const shot = await r.shot("97-no-dashboards");
      // The first dashboard made goes to every tablet.
      await r.click('[data-test="create"]');
      await r.waitFor(`__j.find('[data-test="add-first-card"]')`, "the new dashboard");
      await r.waitSaved("the new dashboard");
      await waitCaption(
        r,
        ["Waiting for tablet software (Bedroom tablet)", "Hallway tablet is offline", "On Kitchen tablet"],
        "the new dashboard on the tablets",
      );
      await r.shot("97-first-dashboard-on-tablets");
      return shot;
    }),
  ];

  // No tablets at all: Home and the editor say so plainly.
  const tabletsNone = [
    step("98", "no-tablets", async (r) => {
      await r.open({ seed: "sample" }, `${home} && __j.find('[data-test="tablets-none"]') && __j.find('[data-test="dashboard-row"]')`);
      check(
        (await r.text('[data-test="tablets-none"]')) === "No TAB-1 tablet found in Home Assistant yet. Power the tablet on. If it asks for Wi-Fi, join \"Apollo TAB1 Hotspot\" from a phone and pick your Wi-Fi. Then add it in Settings > Devices & services, where it shows up by itself, and turn it on here. You can still build dashboards.",
        `the Tablets box says "${await r.text('[data-test="tablets-none"]')}"`,
      );
      check((await r.count('[data-test="row-shown-on"]')) === 0, "a dashboard says where it is shown");
      check((await r.count('[data-test="tablets-add"]')) === 0, "a line about another tablet with none there");
      await checkTextContrast(r, ['[data-test="tablets-none"]']);
      const shot = await r.shot("98-no-tablets-home");
      await r.click('[data-test="dashboard-row"][data-url-path="tab-1"] [data-test="edit"]');
      await r.waitFor(`(${editorReady}) && __j.find('[data-test="shown-on-none"]')`, "the editor");
      await waitCaption(r, ["Not shown on a tablet yet"], "the caption");
      check((await r.text('[data-test="shown-on-none"]')) === "No tablets yet.", "no No tablets yet.");
      check(/tab-1/.test(await r.text('[data-test="automation-name"]')), "no name for automations");
      await r.eval(`__j.find('[data-test="shown-on"]').scrollIntoView({ block: "center" }); true`);
      await checkTextContrast(r, ['[data-test="tablet-line"]', '[data-test="shown-on-none"]']);
      await r.shot("98-no-tablets-editor");
      return shot;
    }),
  ];

  // A tablet whose software cannot show dashboards yet: the choice is kept
  // and sent once it can.
  const tabletsNoEngine = [
    step("99", "tablet-without-engine", async (r) => {
      await r.open({ seed: "sample", tablets: "no-engine" }, `${home} && __j.count('[data-test="tablet-row"]') === 1`);
      await waitText(r, tabletStatus(BEDROOM), "Waiting for tablet software", "the status");
      const help = await uiString(r, "tablets.no_engine_help");
      check((await r.text(`${tabletRow(BEDROOM)} [data-test="tablet-help"]`)) === help, "no helper line");
      check(
        (await r.text(`${tabletRow(BEDROOM)} [data-test="tablet-help-saved"]`)) === (await uiString(r, "tablets.no_engine_saved")),
        "no line that the choice is kept",
      );
      check((await r.count(`${tabletRow(BEDROOM)} [data-test="tablet-input"]`)) === 0, "a line about taps before the dashboard is there");
      await waitText(r, shownOnLine("tab-1"), "Shown on: Bedroom", "the Shown on line");
      await checkTextContrast(r, [tabletStatus(BEDROOM), `${tabletRow(BEDROOM)} [data-test="tablet-help"]`]);
      const shot = await r.shot("99-tablet-without-engine");
      await r.eval(`__apolloMockHass.holdSends(); __apolloMockHass.setTablet(${JSON.stringify(BEDROOM)}, { engine: "0.1.0" }); true`);
      await waitText(r, tabletStatus(BEDROOM), "Sending…", "Sending… once the software is there");
      check((await r.count(`${tabletRow(BEDROOM)} [data-test="tablet-help"]`)) === 0, "the helper line stays");
      await waitText(
        r,
        `${tabletRow(BEDROOM)} [data-test="tablet-input"]`,
        await uiString(r, "tablets.not_paired"),
        "the line that taps wait for set-up",
      );
      await r.eval(`__apolloMockHass.finishSends(); true`);
      await waitText(r, tabletStatus(BEDROOM), "On the tablet", "On the tablet");
      await r.shot("99-tablet-software-arrived");
      // With no dashboard at all there is no choice to keep.
      await r.open({ seed: "none", tablets: "no-engine" }, `${home} && __j.count('[data-test="tablet-row"]') === 1`);
      await waitText(r, tabletStatus(BEDROOM), "Waiting for tablet software", "the status without dashboards");
      check((await r.count(`${tabletRow(BEDROOM)} [data-test="tablet-help"]`)) === 1, "no helper line without dashboards");
      check(
        (await r.count(`${tabletRow(BEDROOM)} [data-test="tablet-help-saved"]`)) === 0,
        "a line that a choice is kept, without any dashboard",
      );
      return shot;
    }),
  ];

  // Every status and both lines about taps at once: the words fit on a
  // phone and stay readable.
  const tabletsAll = [
    step("100", "every-tablet-status", async (r) => {
      await r.open({ seed: "sample", tablets: "all" }, `${home} && __j.count('[data-test="tablet-row"]') === 15`);
      // The new tablet comes first, then the others by name.
      const expected = {
        "Shed tablet": 'New tablet. Pick a dashboard, then press "Turn on with this dashboard".',
        "Attic tablet": "This dashboard is too big for the tablet",
        "Bedroom tablet": "Waiting for tablet software",
        "Cellar tablet": "This dashboard cannot be read",
        "Den tablet": "On the tablet",
        "Garage tablet": "Update Apollo TAB Dashboard in Home Assistant",
        "Guest tablet": "Nothing to show yet",
        "Hallway tablet": "Offline",
        "Kitchen tablet": "On the tablet",
        "Loft tablet": "On the tablet",
        "Nursery tablet": "Sending…",
        "Office tablet": "Needs newer tablet software",
        "Pantry tablet": "Waiting for you in Repairs",
        "Porch tablet": "Could not send. Trying again.",
        "Study tablet": "The tablet cannot show this dashboard",
      };
      const read = await r.eval(`Object.fromEntries(__j.all('[data-test="tablet-row"]').map((row) =>
        [row.querySelector(".tablet-name").textContent, row.querySelector('[data-test="tablet-status"]').innerText]))`);
      check(JSON.stringify(read) === JSON.stringify(expected), `the statuses read ${JSON.stringify(read)}`);
      // "Shows" comes before the status: beside it on a wide screen, above it
      // on a phone.
      const order = await r.eval(`__j.all('[data-test="tablet-row"]').filter((row) =>
        row.querySelector(".tablet-shows") && row.querySelector('[data-test="tablet-status"]').textContent).map((row) => {
          const a = row.querySelector(".tablet-shows").getBoundingClientRect();
          const b = row.querySelector('[data-test="tablet-status"]').getBoundingClientRect();
          return [row.querySelector(".tablet-name").textContent, a.bottom <= b.top + 1 || a.right <= b.left + 1];
        }).filter(([, first]) => !first).map(([name]) => name)`);
      check(order.length === 0, `the status comes before "Shows" for ${JSON.stringify(order)}`);
      const notes = await r.eval(`__j.all('[data-test="tablet-input"]').map((line) =>
        [line.closest('[data-test="tablet-row"]').querySelector(".tablet-name").textContent, line.textContent])`);
      check(
        JSON.stringify(notes) ===
          JSON.stringify([
            ["Den tablet", await uiString(r, "tablets.needs_encryption")],
            ["Loft tablet", await uiString(r, "tablets.not_paired")],
          ]),
        `the lines about taps: ${JSON.stringify(notes)}`,
      );
      // Round 9: an offline row says what to check, and the way back onto a
      // changed Wi-Fi; a row that waits for an answer in Repairs
      // says that instead, on an amber band.
      const nextSteps = await r.eval(`__j.all('[data-test="tablet-offline-help"], [data-test="tablet-reauth"]').map((line) =>
        [line.closest('[data-test="tablet-row"]').querySelector(".tablet-name").textContent, line.dataset.test, line.textContent])`);
      const erasedWords = (await uiString(r, "tablets.reauth_erased")).replace("{name}", "Apollo TAB-1 ddee10");
      check(
        JSON.stringify(nextSteps) ===
          JSON.stringify([
            ["Hallway tablet", "tablet-offline-help", await uiString(r, "tablets.offline_help")],
            ["Pantry tablet", "tablet-reauth", `${erasedWords} Open Repairs`],
          ]),
        `the next steps of the rows that are not connected: ${JSON.stringify(nextSteps)}`,
      );
      const band = await r.eval(`(() => { const status = __j.all('[data-test="tablet-row"]')
        .find((row) => row.querySelector(".tablet-name").textContent === "Pantry tablet")
        .querySelector('[data-test="tablet-status"]');
        const style = getComputedStyle(status);
        const quiet = getComputedStyle(__j.find('[data-test="tablet-status"][data-tone="quiet"]'));
        return { tone: status.dataset.tone, border: style.borderTopStyle, edge: style.borderTopColor,
          background: style.backgroundColor, plain: quiet.backgroundColor,
          dot: getComputedStyle(status, "::before").backgroundColor }; })()`);
      check(
        band.tone === "attention" && band.border === "solid" && band.background !== band.plain && band.edge === band.dot,
        `the status of a tablet that waits in Repairs: ${JSON.stringify(band)}`,
      );
      const guest = await r.eval(`(() => { const field = __j.all('[data-test="tablet-row"]')
        .find((row) => row.querySelector(".tablet-name").textContent === "Guest tablet")
        .querySelector('[data-test="tablet-shows"]');
        return { value: field.value, first: field.options[0].textContent, disabled: field.options[0].disabled }; })()`);
      check(
        guest.value === "" && guest.first === "Pick a dashboard" && guest.disabled,
        `the guest tablet's list: ${JSON.stringify(guest)}`,
      );
      // The new tablet's list starts empty and names what it showed before.
      const shed = await r.eval(`(() => { const row = __j.all('[data-test="tablet-row"]')[0];
        const field = row.querySelector('[data-test="tablet-shows"]');
        return { isNew: row.dataset.new, mark: row.querySelector('[data-test="tablet-new"]')?.textContent,
          device: row.querySelector('[data-test="tablet-device"]')?.textContent,
          before: row.querySelector('[data-test="tablet-device-before"]')?.textContent,
          value: field.value, options: [...field.options].map((option) => option.textContent),
          turnOn: row.querySelector('[data-test="tablet-turn-on"]')?.disabled,
          note: row.querySelector('[data-test="tablet-approve-note"]')?.textContent,
          waiting: row.querySelector('[data-test="tablet-waiting-note"]')?.textContent }; })()`);
      check(
        JSON.stringify(shed) ===
          JSON.stringify({
            isNew: "true",
            mark: "New",
            device: "Before you turn it on, check that the name on the tablet's screen ends in ddee0e. Open device page",
            before: "If it still shows TAB-1, its old dashboard, its name is not on its screen. Check that it shows TAB-1 and that its values no longer change.",
            value: "",
            options: ["Pick a dashboard", "TAB-1 (shown before)"],
            turnOn: true,
            note: await uiString(r, "tablets.approve_note"),
            waiting: await uiString(r, "tablets.waiting_note"),
          }),
        `the shed tablet's row: ${JSON.stringify(shed)}`,
      );
      // Only a new tablet's row says which device it is.
      check((await r.count('[data-test="tablet-device"]')) === 1, "a device line on a tablet that is turned on");
      await checkTextContrast(r, [
        '[data-test="tablet-status"][data-tone="new"]',
        '[data-test="tablet-new"]',
        '[data-test="tablet-device"]',
        '[data-test="tablet-device-page"]',
        '[data-test="tablet-device-before"]',
        '[data-test="tablet-approve-note"]',
        '[data-test="tablet-waiting-note"]',
        '[data-test="tablet-status"][data-tone="problem"]',
        '[data-test="tablet-status"][data-tone="busy"]',
        '[data-test="tablet-status"][data-tone="quiet"]',
        '[data-test="tablet-status"][data-tone="attention"]',
        '[data-test="tablet-input"]',
        '[data-test="tablet-offline-help"]',
        '[data-test="tablet-reauth"]',
      ]);
      return r.shot("100-every-tablet-status");
    }),
  ];

  // The tablet preview card on a Home Assistant dashboard shows the same
  // lines as the editor.
  const tabletsPreview = [
    step("101", "preview-lines", async (r) => {
      await r.open(threeTablets, `${home} && __j.count('[data-test="tablet-row"]') === 3`);
      await r.eval(`(() => { __apolloPanel.style.display = "none";
        const preview = document.createElement("apollo-tab-preview");
        preview.hass = __apolloMockHass;
        preview.dashboard = "tab-1";
        document.body.append(preview);
        return true; })()`);
      await waitCaption(r, ["Waiting for tablet software (Bedroom tablet)", "On Kitchen tablet"], "the preview's lines");
      const words = await r.eval(`document.querySelector("apollo-tab-preview").shadowRoot.textContent`);
      check(!/not sent to tablets/i.test(words), "the preview still says dashboards are not sent to tablets");
      await checkTextContrast(r, ['[data-test="tablet-line"]']);
      return r.shot("101-preview-lines");
    }),
  ];

  // Home Assistant's connection is back before the integration is set up,
  // or the integration is an older one: its commands are not known. What is
  // open keeps trying by itself and comes back without a reload.
  const SUBSCRIBED = (type) => `__apolloMockHass.subscriptions(${JSON.stringify(type)})`;
  const starting = [
    step("202", "restart-with-cards-open", async (r) => {
      const card = `document.querySelector("apollo-tab-card").shadowRoot`;
      const status = `(${card}.querySelector(".status")?.textContent ?? null)`;
      const alerts = `__j.count('[data-test="tablets"] .alert')`;
      await r.open(threeTablets, `${home} && __j.count('[data-test="tablet-row"]') === 3`);
      const waiting = await uiString(r, "card.waiting");
      await waitText(r, tabletStatus(KITCHEN), "On the tablet", "the kitchen tablet's status");
      // A card on a dashboard and the preview card, open along with Home.
      await r.eval(`(() => {
        const card = document.createElement("apollo-tab-card");
        card.style.width = "376px";
        card.style.height = "184px";
        card.setConfig({ component: "apollo/light-tile", params: { entity: "light.kitchen" } });
        card.hass = __apolloMockHass;
        const preview = document.createElement("apollo-tab-preview");
        preview.hass = __apolloMockHass;
        preview.dashboard = "tab-1";
        document.body.append(card, preview);
        return true; })()`);
      await r.waitFor(`${card}.querySelector(".at-card") && ${status} === null`, "the card to be drawn");
      await waitCaption(r, ["Waiting for tablet software (Bedroom tablet)", "On Kitchen tablet"], "the preview's lines");

      // Home Assistant restarts. Its connection is back first; a tablet
      // goes offline before the integration is set up.
      await r.eval(`(() => { const mock = __apolloMockHass;
        mock.dropConnection();
        mock.unknownCommands("apollo_tab/");
        mock.reconnect();
        mock.setTablet(${JSON.stringify(KITCHEN)}, { online: false }, { quiet: true });
        return true; })()`);
      await r.waitFor(`${status} === ${JSON.stringify(waiting)}`, "the card to say it waits for Home Assistant");
      // Home and the preview keep what they showed, with no error.
      check((await r.count('[data-test="tablet-row"]')) === 3 && (await r.eval(alerts)) === 0, "Home lost its tablets while Home Assistant starts");
      check((await r.text(tabletStatus(KITCHEN))) === "On the tablet", "Home heard of the tablet while nothing was subscribed");
      for (const type of ["card", "tablets", "layout", "library"]) {
        const open = await r.eval(SUBSCRIBED(`apollo_tab/${type}/subscribe`));
        check(open === 0, `${open} ${type} subscriptions are open while Home Assistant does not know them`);
      }
      const shot = await r.shot("202-restart-with-cards-open");

      // The integration is set up. Nobody presses anything.
      await r.eval(`__apolloMockHass.unknownCommands(null); true`);
      await r.waitFor(`${card}.querySelector(".at-card") && ${status} === null`, "the card to be drawn again", 20000);
      await waitText(r, tabletStatus(KITCHEN), "Offline", "Home to show the tablet that went offline", 20000);
      await waitCaption(r, ["Waiting for tablet software (Bedroom tablet)", "Kitchen tablet is offline"], "the preview's lines after the restart");
      check((await r.eval(alerts)) === 0, "Home shows an error after Home Assistant has started");
      check((await r.eval(SUBSCRIBED("apollo_tab/card/subscribe"))) === 1, "the card is not subscribed again");
      check((await r.eval(SUBSCRIBED("apollo_tab/tablets/subscribe"))) === 1, "the tablets are not subscribed again once");
      await r.shot("202-restart-over");
      return shot;
    }),
    step("203", "tablets-known-later", async (r) => {
      const homeAlert = '[data-test="tablets"] .alert';
      const editorAlert = '[data-test="shown-on"] .alert';
      await r.open(threeTablets, `${home} && __j.count('[data-test="tablet-row"]') === 3`);
      const failed = (await uiString(r, "tablets.load_failed")).replace("{message}", "Unknown command.");
      // The panel is away long enough for its tablet subscription to end,
      // and comes back to a Home Assistant that does not know the tablet
      // commands: an older integration that was updated but not restarted.
      await r.eval(`__apolloPanel.remove(); true`);
      await r.waitFor(`${SUBSCRIBED("apollo_tab/tablets/subscribe")} === 0`, "the tablet subscription to end");
      await r.eval(`__apolloMockHass.unknownCommands("apollo_tab/tablet"); __apolloOpenPanel(""); true`);
      await waitText(r, homeAlert, failed, "Home to say the tablets cannot be loaded");
      check((await r.count('[data-test="tablet-row"]')) === 0, "Home lists tablets it could not load");
      const shot = await r.shot("203-tablets-not-known");
      // The editor says the same under "Shown on", and draws no lines.
      await r.eval(`__apolloOpenPanel("/edit/tab-1"); true`);
      await r.waitFor(editorReady, "the editor");
      await waitText(r, editorAlert, failed, "the editor to say the tablets cannot be loaded");
      check((await r.count('[data-test="tablet-line"]')) === 0, "the editor shows tablet lines it could not load");

      // Home Assistant is restarted with the new integration; the stand-in
      // only learns the commands. Nobody presses anything.
      await r.eval(`__apolloMockHass.unknownCommands(null); true`);
      await r.waitFor(`__j.count('[data-test="shown-on-row"]') === 3 && !__j.find('${editorAlert}')`, "the editor to list the tablets", 20000);
      await waitCaption(r, ["Waiting for tablet software (Bedroom tablet)", "On Kitchen tablet"], "the editor's lines");
      await r.eval(`__apolloOpenPanel(""); true`);
      await r.waitFor(`${home} && __j.count('[data-test="tablet-row"]') === 3 && !__j.find('${homeAlert}')`, "Home to list the tablets");
      await waitText(r, tabletStatus(KITCHEN), "On the tablet", "the kitchen tablet's status");
      check((await r.eval(SUBSCRIBED("apollo_tab/tablets/subscribe"))) === 1, "the tablets are not subscribed once");
      await r.shot("203-tablets-known-later");
      return shot;
    }),
  ];

  // A new tablet waits for an admin: it is listed first, marked "New",
  // shows nothing and is left out of what the dashboards say. Picking its
  // first dashboard turns it on.
  const newTablet = { seed: "sample", night: "1", tablets: "new" };
  const tabletsNew = [
    step("102", "new-tablet-waits", async (r) => {
      await r.open(newTablet, `${home} && __j.count('[data-test="tablet-row"]') === 2 && __j.count('[data-test="dashboard-row"]') === 2`);
      const rows = await r.eval(`__j.all('[data-test="tablet-row"]').map((row) =>
        [row.dataset.mac, row.dataset.new, row.querySelector(".tablet-name").textContent,
         row.querySelector('[data-test="tablet-new"]')?.textContent ?? null])`);
      check(
        JSON.stringify(rows) ===
          JSON.stringify([
            [PORCH, "true", "Porch tablet", "New"],
            [KITCHEN, "false", "Kitchen tablet", null],
          ]),
        `the tablets read ${JSON.stringify(rows)}`,
      );
      await waitText(r, tabletStatus(PORCH), NEW_STATUS, "the new tablet's status");
      const tone = await r.eval(`__j.find(${JSON.stringify(tabletStatus(PORCH))}).dataset.tone`);
      check(tone === "new", `the new tablet's tone is ${tone}`);
      check(
        (await r.text(`${tabletRow(PORCH)} [data-test="tablet-approve-note"]`)) === "Only turn on tablets you own.",
        "no line about turning on only tablets you own",
      );
      check((await r.count(`${tabletRow(PORCH)} [data-test="tablet-input"]`)) === 0, "a line about taps on a new tablet");
      check((await r.count(`${tabletRow(KITCHEN)} [data-test="tablet-approve-note"]`)) === 0, "the approved tablet has the note");
      // What tells which device it is, since its name comes from the device.
      // textContent: on a phone the link has a line of its own.
      const device = await r.eval(`__j.find(${JSON.stringify(`${tabletRow(PORCH)} [data-test="tablet-device"]`)}).textContent`);
      check(
        device === "Before you turn it on, check that the name on the tablet's screen ends in ddee0e. Open device page",
        `the device line reads "${device}"`,
      );
      // It never showed a dashboard, so nothing says its screen hides its name.
      check((await r.count(`${tabletRow(PORCH)} [data-test="tablet-device-before"]`)) === 0, "a line about an old dashboard");
      const link = await r.eval(`(() => { const link = __j.find(${JSON.stringify(`${tabletRow(PORCH)} [data-test="tablet-device-page"]`)});
        return { href: link.getAttribute("href"), named: link.getAttribute("aria-labelledby").split(" ")
          .map((id) => __apolloPanel.shadowRoot.getElementById(id).textContent).join(" ") }; })()`);
      check(
        link.href === "/config/devices/device/0000000000000000000000000000000e" && link.named === "Open device page Porch tablet",
        `the device page link: ${JSON.stringify(link)}`,
      );
      // The link follows the tablet's device when Home Assistant has it
      // under another id; then back, for the steps below.
      const href = `__j.find(${JSON.stringify(`${tabletRow(PORCH)} [data-test="tablet-device-page"]`)})?.getAttribute("href")`;
      for (const id of ["0000000000000000000000000000000f", "0000000000000000000000000000000e"]) {
        await r.eval(`__apolloMockHass.setTablet(${JSON.stringify(PORCH)}, { device_id: ${JSON.stringify(id)} }); true`);
        await r.waitFor(`${href} === "/config/devices/device/${id}"`, `the device page link to lead to device ${id}`);
      }
      check((await r.count(`${tabletRow(KITCHEN)} [data-test="tablet-device"]`)) === 0, "the approved tablet has a device line");
      check(
        (await r.text(`${tabletRow(PORCH)} [data-test="tablet-waiting-note"]`)) === (await uiString(r, "tablets.waiting_note")),
        "no line that the tablet keeps its screen until it is turned on",
      );
      const turnOn = await r.eval(`(() => { const button = __j.find(${JSON.stringify(`${tabletRow(PORCH)} [data-test="tablet-turn-on"]`)});
        return button && { text: button.textContent, disabled: button.disabled }; })()`);
      check(
        JSON.stringify(turnOn) === JSON.stringify({ text: "Turn on with this dashboard", disabled: true }),
        `before a pick the button is ${JSON.stringify(turnOn)}`,
      );
      const list = await r.eval(`(() => { const field = __j.find(${JSON.stringify(tabletShows(PORCH))});
        return { value: field.value, options: [...field.options].map((option) => [option.textContent, option.disabled]) }; })()`);
      check(
        JSON.stringify(list) ===
          JSON.stringify({
            value: "",
            options: [
              ["Pick a dashboard", true],
              ["Night", false],
              ["TAB-1", false],
            ],
          }),
        `the new tablet's list: ${JSON.stringify(list)}`,
      );
      // It shows nothing, so the dashboards do not name it.
      await waitText(r, shownOnLine("tab-1"), "Shown on: Kitchen", "the Shown on line of TAB-1");
      check((await r.count(shownOnLine("night"))) === 0, "Night says it is shown somewhere");
      check((await r.calls("apollo_tab/tablet/assign")).length === 0, "something was assigned");
      check((await r.calls("apollo_tab/tablet/pair")).length === 0, "something was paired");
      // With tablets there, a short line under them says how to add another.
      const add = await r.eval(`(() => { const line = __j.find('[data-test="tablets-add"]');
        const rows = __j.all('[data-test="tablet-row"]');
        return line && { text: line.textContent, last: line.parentNode.lastElementChild === line,
          below: line.getBoundingClientRect().top >= rows[rows.length - 1].getBoundingClientRect().bottom }; })()`);
      check(
        JSON.stringify(add) === JSON.stringify({ text: await uiString(r, "tablets.add_another"), last: true, below: true }),
        `the line about another tablet: ${JSON.stringify(add)}`,
      );
      await checkTextContrast(r, [
        '[data-test="tablets-add"]',
        tabletStatus(PORCH),
        `${tabletRow(PORCH)} [data-test="tablet-new"]`,
        `${tabletRow(PORCH)} [data-test="tablet-device"]`,
        `${tabletRow(PORCH)} [data-test="tablet-device-page"]`,
        `${tabletRow(PORCH)} [data-test="tablet-approve-note"]`,
        `${tabletRow(PORCH)} [data-test="tablet-waiting-note"]`,
        `${tabletRow(PORCH)} .tablet-name`,
        tabletShows(PORCH),
      ]);
      return r.shot("102-new-tablet-waits");
    }),
    step("103", "new-tablet-in-editor", async (r) => {
      await r.click('[data-test="dashboard-row"][data-url-path="tab-1"] [data-test="edit"]');
      await r.waitFor(`(${editorReady}) && __j.find('[data-test="shown-on"]') && __j.find('[data-test="shown-on-new"]')`, "the editor");
      await waitCaption(r, ["On Kitchen tablet"], "the caption without the new tablet");
      const rows = await r.eval(`__j.all('[data-test="shown-on-row"]').map((row) => row.dataset.mac)`);
      check(JSON.stringify(rows) === JSON.stringify([KITCHEN]), `the Shown on block lists ${JSON.stringify(rows)}`);
      check(
        (await r.text('[data-test="shown-on-new"]')) ===
          'A new tablet is waiting. On the Home screen, pick a dashboard for it, then press "Turn on with this dashboard".',
        `the Shown on block says "${await r.text('[data-test="shown-on-new"]')}"`,
      );
      check((await r.count(`[data-test="show-here"][data-mac="${PORCH}"]`)) === 0, "the new tablet can be turned on from the editor");
      check((await r.count('[data-test="shown-on-none"]')) === 0, "the editor says there are no tablets");
      await r.eval(`__j.find('[data-test="shown-on"]').scrollIntoView({ block: "center" }); true`);
      await checkTextContrast(r, ['[data-test="shown-on-new"]']);
      return r.shot("103-new-tablet-in-editor");
    }),
    step("104", "approve-new-tablet", async (r) => {
      await r.open(newTablet, `${home} && __j.count('[data-test="tablet-row"]') === 2`);
      await r.eval(`__apolloMockHass.holdSends(); true`);
      const turnOn = `${tabletRow(PORCH)} [data-test="tablet-turn-on"]`;
      // Moving through the list with the keyboard only chooses: real arrow
      // keys, and the change event they fire in some browsers.
      await r.eval(`__j.find(${JSON.stringify(tabletShows(PORCH))}).focus(); true`);
      await r.key("ArrowDown");
      await r.key("ArrowDown");
      await r.key("ArrowUp");
      await r.key("Escape");
      await pickShows(r, PORCH, "tab-1");
      await pickShows(r, PORCH, "night");
      await sleep(200);
      check((await r.calls("apollo_tab/tablet/assign")).length === 0, "a pick in the list turned the tablet on");
      check((await r.eval(`__j.find(${JSON.stringify(tabletRow(PORCH))}).dataset.new`)) === "true", "the tablet is no longer new");
      await waitText(r, tabletStatus(PORCH), NEW_STATUS, "the status of a tablet still new");
      const chosen = await r.eval(`({ value: __j.find(${JSON.stringify(tabletShows(PORCH))}).value,
        disabled: __j.find(${JSON.stringify(turnOn)}).disabled })`);
      check(chosen.value === "night" && chosen.disabled === false, `after the pick: ${JSON.stringify(chosen)}`);
      // The picked dashboard stays picked when the tablet list comes again.
      await r.eval(`__apolloMockHass.setTablet(${JSON.stringify(PORCH)}, {}); true`);
      await sleep(100);
      check((await r.eval(`__j.find(${JSON.stringify(tabletShows(PORCH))}).value`)) === "night", "the pick was lost");
      await checkTextContrast(r, [turnOn]);
      await r.screen("104-new-tablet-picked");
      // The button turns it on, here pressed with the keyboard. It alone
      // sends approve.
      await r.eval(`__j.find(${JSON.stringify(turnOn)}).focus(); true`);
      await r.key("Enter");
      await r.waitFor(`__j.find(${JSON.stringify(tabletRow(PORCH))})?.dataset.new === "false"`, "the new tablet to be turned on");
      const calls = await r.calls("apollo_tab/tablet/assign");
      check(
        calls.length === 1 && calls[0].mac === PORCH && calls[0].url_path === "night" && calls[0].approve === true,
        `the button sent ${JSON.stringify(calls)}`,
      );
      await waitText(r, tabletStatus(PORCH), "Sending…", "Sending… once it is turned on");
      check((await r.count(`${tabletRow(PORCH)} [data-test="tablet-new"]`)) === 0, "the New mark stays");
      check((await r.count(`${tabletRow(PORCH)} [data-test="tablet-approve-note"]`)) === 0, "the note stays");
      check((await r.count(`${tabletRow(PORCH)} [data-test="tablet-turn-on"]`)) === 0, "the button stays");
      check((await r.count(`${tabletRow(PORCH)} [data-test="tablet-device"]`)) === 0, "the device line stays");
      // The row was built again in the same place, and the tablet's name
      // takes focus: not its list, where an arrow key would now switch it.
      const focus = await r.eval(`__j.active() === __j.find(${JSON.stringify(`${tabletRow(PORCH)} .tablet-name`)})`);
      check(focus, `after turning it on focus is on ${await r.eval(`__j.describe(__j.active())`)}`);
      await r.key("ArrowDown");
      await r.key("ArrowDown");
      await sleep(200);
      check((await r.calls("apollo_tab/tablet/assign")).length === 1, "an arrow key after turning it on switched the tablet");
      check((await r.eval(`__j.find(${JSON.stringify(tabletShows(PORCH))}).value`)) === "night", "an arrow key changed its list");
      const order = await r.eval(`__j.all('[data-test="tablet-row"]').map((row) => row.dataset.mac)`);
      check(JSON.stringify(order) === JSON.stringify([PORCH, KITCHEN]), `the tablets are in the order ${JSON.stringify(order)}`);
      await waitText(r, shownOnLine("night"), "Shown on: Porch", "the Night row to name the porch tablet");
      const shot = await r.screen("104-new-tablet-sending");
      await r.eval(`__apolloMockHass.finishSends(); true`);
      await waitText(r, tabletStatus(PORCH), "On the tablet", "On the tablet");
      check(
        (await r.eval(`__j.find(${JSON.stringify(tabletShows(PORCH))}).value`)) === "night",
        "the list does not show Night",
      );
      await checkTextContrast(r, [tabletStatus(PORCH), shownOnLine("night")]);
      await r.shot("104-new-tablet-on");
      // Once on, a change of its list switches it at once, as for any tablet.
      await pickShows(r, PORCH, "tab-1");
      await r.waitFor(`__apolloMockHass.calls.filter((call) => call.type === "apollo_tab/tablet/assign").length === 2`, "the switch");
      const switched = (await r.calls("apollo_tab/tablet/assign"))[1];
      check(switched.url_path === "tab-1" && !("approve" in switched), `the switch sent ${JSON.stringify(switched)}`);
      return shot;
    }),
  ];

  // A tablet whose set-up for taps has not worked for a while gets a "Set
  // up again" button. The page's clock is moved on instead of waiting.
  const tabletsPairAgain = [
    step("105", "set-up-again", async (r) => {
      await r.open({ seed: "sample", tablets: "all" }, `${home} && __j.count('[data-test="tablet-row"]') === 15`);
      const loft = (test) => `${tabletRow(LOFT)} [data-test="${test}"]`;
      await waitText(r, loft("tablet-input"), await uiString(r, "tablets.not_paired"), "the line that taps wait for set-up");
      check((await r.count('[data-test="tablet-pair"]')) === 0, "Set up again is offered at once");
      await r.eval(`(() => { const now = Date.now.bind(Date); window.__realNow = now;
        Date.now = () => now() + 91 * 1000;
        __apolloMockHass.setTablet(${JSON.stringify(LOFT)}, {}); return true; })()`);
      await r.waitFor(`__j.count('[data-test="tablet-pair"]') === 1`, "Set up again after a while");
      check((await r.count(loft("tablet-pair"))) === 1, "Set up again is on another tablet's row");
      check((await r.text(loft("tablet-pair"))) === "Set up again", "the button's words");
      const named = await r.eval(`__j.find(${JSON.stringify(loft("tablet-pair"))}).getAttribute("aria-labelledby").split(" ")
        .map((id) => __apolloPanel.shadowRoot.getElementById(id).textContent).join(" ")`);
      check(named === "Set up again Loft tablet", `the button is named "${named}"`);
      await r.click(loft("tablet-pair"));
      await waitText(r, loft("tablet-pair-asked"), await uiString(r, "tablets.pair_asked"), "the line that it was asked");
      const calls = await r.calls("apollo_tab/tablet/pair");
      check(calls.length === 1 && calls[0].mac === LOFT, `the button sent ${JSON.stringify(calls)}`);
      const focus = await r.eval(`__j.active() === __j.find(${JSON.stringify(loft("tablet-pair"))})`);
      check(focus, `after the press focus is on ${await r.eval(`__j.describe(__j.active())`)}`);
      await checkTextContrast(r, [loft("tablet-pair"), loft("tablet-pair-asked")]);
      const shot = await r.shot("105-set-up-again");
      // A refusal is said under the button.
      await r.eval(`__apolloMockHass.failCalls("apollo_tab/tablet/pair", 1); true`);
      await r.click(loft("tablet-pair"));
      await waitText(r, loft("tablet-pair-error"), "It could not be set up again: Fixture error", "the failure");
      check((await r.count(loft("tablet-pair-asked"))) === 0, "the line that it was asked stays after a failure");
      await checkTextContrast(r, [loft("tablet-pair-error")]);
      await r.shot("105-set-up-again-failed");
      // Once it is set up, the line, the button and the failure go.
      await r.eval(`__apolloMockHass.setTablet(${JSON.stringify(LOFT)}, { paired: true, input: "ok" }); true`);
      await r.waitFor(`__j.count(${JSON.stringify(`${tabletRow(LOFT)} .tablet-notes > *`)}) === 0`, "the notes to go once it is set up");
      await r.eval(`Date.now = window.__realNow; true`);
      return shot;
    }),
  ];

  // What keeps a new tablet from being turned on by mistake: with nothing
  // to pick the status asks for none, a pick goes when it is no choice any
  // more, a second press while the first is on its way sends nothing, and
  // the device page opens inside Home Assistant without loading the page.
  const tabletsNewGuards = [
    step("106", "new-tablet-guards", async (r) => {
      await r.open({ seed: "none", tablets: "new" }, `${home} && __j.count('[data-test="tablet-row"]') === 2`);
      await waitText(
        r,
        tabletStatus(PORCH),
        'New tablet. Make a dashboard, then pick it and press "Turn on with this dashboard".',
        "the status with nothing to pick",
      );
      check(
        (await r.text(`${tabletRow(PORCH)} [data-test="tablet-make-first"]`)) === "Make a dashboard first.",
        "no Make a dashboard first. beside the new tablet",
      );
      check((await r.count(`${tabletRow(PORCH)} [data-test="tablet-turn-on"]`)) === 0, "a Turn on button with nothing to pick");
      await checkTextContrast(r, [tabletStatus(PORCH)]);

      await r.open(newTablet, `${home} && __j.count('[data-test="tablet-row"]') === 2 && __j.count('[data-test="dashboard-row"]') === 2`);
      const turnOn = `${tabletRow(PORCH)} [data-test="tablet-turn-on"]`;
      const enabled = `__j.find(${JSON.stringify(turnOn)})?.disabled === false`;
      const isNew = (value) => `__j.find(${JSON.stringify(tabletRow(PORCH))})?.dataset.new === "${value}"`;
      const row = () =>
        r.eval(`(() => { const field = __j.find(${JSON.stringify(tabletShows(PORCH))});
          const button = __j.find(${JSON.stringify(turnOn)});
          return { value: field ? field.value : null, disabled: button ? button.disabled : null }; })()`);

      // A picked dashboard that is deleted is no choice any more.
      await pickShows(r, PORCH, "night");
      await r.waitFor(enabled, "Turn on after the pick");
      await r.eval(`__apolloMockHass.answerWS({ type: "lovelace/dashboards/delete",
        dashboard_id: __apolloMockHass.getDashboard("night").id }); true`);
      await r.waitFor(
        `__j.count('[data-test="dashboard-row"]') === 1 &&
          ![...__j.find(${JSON.stringify(tabletShows(PORCH))}).options].some((option) => option.value === "night")`,
        "Night to leave the list",
      );
      await sleep(100);
      const deleted = await row();
      check(deleted.value === "" && deleted.disabled === true, `after the picked dashboard was deleted: ${JSON.stringify(deleted)}`);

      // Turned on somewhere else, then new again (added to ESPHome again):
      // the pick made before is not picked again.
      await pickShows(r, PORCH, "tab-1");
      await r.waitFor(enabled, "Turn on after the pick");
      await r.eval(`__apolloMockHass.setTablet(${JSON.stringify(PORCH)}, { approved: true, dashboard: "tab-1" }); true`);
      await r.waitFor(isNew("false"), "the tablet to be turned on somewhere else");
      await r.eval(`__apolloMockHass.setTablet(${JSON.stringify(PORCH)}, { approved: false }); true`);
      await r.waitFor(isNew("true"), "the tablet to be new again");
      await sleep(100);
      const again = await row();
      check(again.value === "" && again.disabled === true, `new again: ${JSON.stringify(again)}`);
      check((await r.calls("apollo_tab/tablet/assign")).length === 0, "something was assigned");
      // The rows just moved: Turn on waits a moment before it takes a press.
      await sleep(TURN_ON_SETTLE_MS + 100);

      // A second press while the first is on its way sends nothing more.
      await pickShows(r, PORCH, "tab-1");
      await r.waitFor(enabled, "Turn on after the pick");
      await r.eval(`__apolloMockHass.slowCalls("apollo_tab/tablet/assign", 1500); true`);
      await r.click(turnOn);
      await r.waitFor(`__apolloMockHass.calls.some((call) => call.type === "apollo_tab/tablet/assign")`, "the first press");
      check(await r.eval(isNew("true")), "the tablet was turned on before the answer");
      await r.click(turnOn);
      await r.eval(`__j.find(${JSON.stringify(turnOn)})?.click(); true`);
      await r.waitFor(isNew("false"), "the tablet to be turned on");
      await r.eval(`__apolloMockHass.slowCalls("apollo_tab/tablet/assign", 0); true`);
      const calls = await r.calls("apollo_tab/tablet/assign");
      check(calls.length === 1 && calls[0].mac === PORCH && calls[0].url_path === "tab-1", `the presses sent ${JSON.stringify(calls)}`);
      const shot = await r.shot("106-new-tablet-guards");

      // The device page link moves inside Home Assistant, as its own links
      // do: no new page load. On a phone it is a 44 px high touch target.
      await r.open(newTablet, `${home} && __j.count('[data-test="tablet-row"]') === 2`);
      const link = `${tabletRow(PORCH)} [data-test="tablet-device-page"]`;
      if (r.setup.device === "phone") {
        const size = await r.eval(`(() => { const box = __j.find(${JSON.stringify(link)}).getBoundingClientRect();
          return { width: box.width, height: box.height }; })()`);
        check(size.width >= 44 && size.height >= 44, `the device page link is ${size.width} x ${size.height} px`);
        await checkRingClear(r, `${tabletRow(PORCH)} .tablet-name`, link);
      }
      await r.eval(`window.__stayed = true; window.__moves = [];
        window.addEventListener("location-changed", () => window.__moves.push(location.pathname)); true`);
      await r.click(link);
      await sleep(300);
      const page = "/config/devices/device/0000000000000000000000000000000e";
      const moved = await r.eval(`({ stayed: window.__stayed === true, path: location.pathname, moves: window.__moves ?? null })`);
      check(
        JSON.stringify(moved) === JSON.stringify({ stayed: true, path: page, moves: [page] }),
        `after the device page link: ${JSON.stringify(moved)}`,
      );
      return shot;
    }),
  ];

  // Turning tablets on, design 10.9: a double click turns on one tablet,
  // a list from before a tablet became new cannot turn it on, and an
  // erased tablet's row says that Home Assistant waits in Repairs.
  const twoNew = { seed: "sample", night: "1", tablets: "two-new" };
  const tabletsTurnOn = [
    step("107", "turn-on-double-click", async (r) => {
      await r.open(twoNew, `${home} && __j.count('[data-test="tablet-row"]') === 3 && __j.count('[data-test="dashboard-row"]') === 2`);
      await r.eval(`__apolloMockHass.holdSends(); true`);
      const order = () => r.eval(`__j.all('[data-test="tablet-row"]').map((row) => row.dataset.mac)`);
      const listed = [PATIO, PORCH, KITCHEN];
      check(JSON.stringify(await order()) === JSON.stringify(listed), `the tablets are in the order ${JSON.stringify(await order())}`);
      const turnOn = (mac) => `${tabletRow(mac)} [data-test="tablet-turn-on"]`;
      const isNew = (mac) => r.eval(`__j.find(${JSON.stringify(tabletRow(mac))})?.dataset.new`);
      // How a tablet's button looks, and how long ago it last moved; gone
      // once the tablet is on.
      const lookOf = (mac) => `(() => { const button = __j.find(${JSON.stringify(turnOn(mac))});
        if (!button) return { gone: true };
        return { late: performance.now() - __apolloPanel._turnOnMovedAt.get(${JSON.stringify(mac)}),
          settling: button.hasAttribute("data-settling"), aria: button.getAttribute("aria-disabled"),
          opacity: getComputedStyle(button).opacity, disabled: button.disabled,
          look: getComputedStyle(button).backgroundColor + " " + getComputedStyle(button).color }; })()`;
      // How a disabled filled button looks in the panel: a button that waits
      // looks the same, so a press it ignores is seen to do nothing.
      const disabledLook = await r.eval(`(() => { const probe = document.createElement("button");
        probe.className = "primary"; probe.disabled = true; __apolloPanel.shadowRoot.append(probe);
        const style = getComputedStyle(probe); const look = style.backgroundColor + " " + style.color;
        probe.remove(); return look; })()`);
      // One press of a real double click: the first has clickCount 1, the
      // second clickCount 2.
      const press = async ({ x, y }, clickCount) => {
        await r.browser.send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
        await r.browser.send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount });
        await r.browser.send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 0, clickCount });
      };
      await pickShows(r, PATIO, "night");
      await pickShows(r, PORCH, "tab-1");
      await r.waitFor(
        `__j.find(${JSON.stringify(turnOn(PATIO))})?.disabled === false && __j.find(${JSON.stringify(turnOn(PORCH))})?.disabled === false`,
        "both buttons after the picks",
      );
      // A pick moves no row, so the first press is taken at once.
      const first = await r.eval(`__j.target(${JSON.stringify(turnOn(PATIO))})`);
      check(first && !first.error, first?.error || "no patio button");
      await press(first, 1);
      await r.waitFor(`__j.find(${JSON.stringify(tabletRow(PATIO))})?.dataset.new === "false"`, "the patio tablet to be turned on", 2000);
      // Its row lost its button and notes, so the rows under it moved up:
      // the second press of the double click lands on the porch tablet's
      // button, which is ignored for a moment and looks disabled meanwhile.
      const second = await r.eval(`__j.target(${JSON.stringify(turnOn(PORCH))})`);
      check(second && !second.error, second?.error || "no porch button");
      await press(second, 2);
      const pressed = await r.eval(lookOf(PORCH));
      check(
        pressed.late < TURN_ON_SETTLE_MS - 150,
        `the second press came ${Math.round(pressed.late)} ms after the porch button moved, too late to tell`,
      );
      check(
        pressed.settling && pressed.aria === "true" && pressed.look === disabledLook && pressed.opacity === "1" &&
          pressed.disabled === false,
        `while it ignores presses the porch button is ${JSON.stringify(pressed)}`,
      );
      // A press without the mouse at that moment is ignored too.
      await r.eval(`__j.find(${JSON.stringify(turnOn(PORCH))})?.click(); true`);
      await sleep(200);
      let calls = await r.calls("apollo_tab/tablet/assign");
      check(
        calls.length === 1 && calls[0].mac === PATIO && calls[0].url_path === "night" && calls[0].approve === true,
        `the double click sent ${JSON.stringify(calls)}`,
      );
      check((await isNew(PORCH)) === "true", "the second press turned the porch tablet on");
      // The patio tablet kept its place at the top.
      check(JSON.stringify(await order()) === JSON.stringify(listed), `after turning it on: ${JSON.stringify(await order())}`);
      await waitText(r, tabletStatus(PATIO), "Sending…", "the patio tablet to be sending");
      await waitText(r, tabletStatus(PORCH), NEW_STATUS, "the porch tablet to be still new");
      const shot = await r.shot("107-turn-on-double-click");
      // A moment later the porch tablet's button looks as before.
      await sleep(TURN_ON_SETTLE_MS + 100);
      const settled = await r.eval(lookOf(PORCH));
      check(
        !settled.settling && settled.aria === null && settled.opacity === "1" && settled.look !== disabledLook,
        `a moment later the porch button is ${JSON.stringify(settled)}`,
      );
      // A line that comes in the patio tablet's row, above it, moves the
      // porch tablet's button: a press right then is ignored, and shown.
      await r.eval(`__apolloMockHass.setTablet(${JSON.stringify(PATIO)}, { paired: false, input: "not_paired" }); true`);
      await r.waitFor(`__j.find(${JSON.stringify(`${tabletRow(PATIO)} [data-test="tablet-input"]`)})`, "the patio tablet's line");
      await r.click(turnOn(PORCH));
      const pushed = await r.eval(lookOf(PORCH));
      check(
        pushed.late < TURN_ON_SETTLE_MS && pushed.settling && pushed.aria === "true" && pushed.look === disabledLook,
        `right after it moved the porch button is ${JSON.stringify(pushed)}`,
      );
      await sleep(200);
      check((await r.calls("apollo_tab/tablet/assign")).length === 1, "a press right after the porch button moved was taken");
      // A move the panel made no change for (here a style, as when the
      // window gets narrower and words wrap) counts too: at the press itself,
      // before the page draws again, and as soon as the box changes size.
      await sleep(TURN_ON_SETTLE_MS + 100);
      const patioRow = JSON.stringify(tabletRow(PATIO));
      const unseen = await r.eval(`(() => { __j.find(${patioRow}).style.paddingBottom = "40px";
        __j.find(${JSON.stringify(turnOn(PORCH))}).click(); return ${lookOf(PORCH)}; })()`);
      check(unseen.late < 100 && unseen.settling, `a press right after a move the panel made no change for: ${JSON.stringify(unseen)}`);
      await sleep(200);
      check((await r.calls("apollo_tab/tablet/assign")).length === 1, "a press right after an unseen move was taken");
      await sleep(TURN_ON_SETTLE_MS + 100);
      const watched = await r.eval(`(async () => { __j.find(${patioRow}).style.paddingBottom = "";
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        return ${lookOf(PORCH)}; })()`);
      check(watched.late < TURN_ON_SETTLE_MS && watched.settling, `after a move without a press: ${JSON.stringify(watched)}`);
      // Words that change in another row without moving the button hold
      // nothing back: a press right after the patio tablet's status changed
      // is taken.
      await sleep(TURN_ON_SETTLE_MS + 100);
      await r.eval(`(() => {
        const status = __j.find(${JSON.stringify(tabletStatus(PATIO))});
        window.__statusAt = null;
        window.__pressAt = null;
        new MutationObserver(() => {
          if (window.__statusAt === null && status.textContent === "On the tablet") window.__statusAt = performance.now();
        }).observe(status, { childList: true, characterData: true, subtree: true });
        __apolloPanel.shadowRoot.addEventListener("click", (event) => {
          if (window.__pressAt === null && event.target.closest?.('[data-test="tablet-turn-on"]')) window.__pressAt = performance.now();
        }, true);
        return true; })()`);
      await r.eval(`__apolloMockHass.finishSends(); true`);
      await waitText(r, tabletStatus(PATIO), "On the tablet", "the patio tablet to show its dashboard");
      await r.click(turnOn(PORCH));
      await r.waitFor(`__j.find(${JSON.stringify(tabletRow(PORCH))})?.dataset.new === "false"`, "the porch tablet to be turned on");
      const gap = await r.eval(`window.__pressAt - window.__statusAt`);
      check(gap >= 0 && gap < TURN_ON_SETTLE_MS, `the press came ${Math.round(gap)} ms after the patio tablet's status changed`);
      calls = await r.calls("apollo_tab/tablet/assign");
      check(
        calls.length === 2 && calls[1].mac === PORCH && calls[1].url_path === "tab-1" && calls[1].approve === true,
        `the later press sent ${JSON.stringify(calls)}`,
      );
      check(JSON.stringify(await order()) === JSON.stringify(listed), `after the second tablet: ${JSON.stringify(await order())}`);
      const focus = await r.eval(`__j.active() === __j.find(${JSON.stringify(`${tabletRow(PORCH)} .tablet-name`)})`);
      check(focus, `after turning it on focus is on ${await r.eval(`__j.describe(__j.active())`)}`);
      // Home drawn again after another screen lists them as usual.
      await r.click('[data-test="open-advanced"]');
      await r.waitFor(`__j.find('[data-test="advanced"]')`, "the Advanced screen");
      await r.click('[data-test="back"]');
      await r.waitFor(`${home} && __j.count('[data-test="tablet-row"]') === 3`, "Home again");
      check(
        JSON.stringify(await order()) === JSON.stringify([KITCHEN, PATIO, PORCH]),
        `back on Home the tablets are in the order ${JSON.stringify(await order())}`,
      );
      await r.eval(`__apolloMockHass.finishSends(); true`);
      return shot;
    }),
    // The tablet became new (added to ESPHome again) a moment before the
    // panel heard of it: a change of its list from the old screen is
    // refused, and it stays new.
    step("108", "stale-switch-refused", async (r) => {
      await r.open(newTablet, `${home} && __j.count('[data-test="tablet-row"]') === 2 && __j.count('[data-test="dashboard-row"]') === 2`);
      await r.eval(`__apolloMockHass.setTablet(${JSON.stringify(KITCHEN)}, { approved: false, suggested: "tab-1" }, { quiet: true }); true`);
      check((await r.eval(`__j.find(${JSON.stringify(tabletRow(KITCHEN))}).dataset.new`)) === "false", "the panel heard of it");
      await pickShows(r, KITCHEN, "night");
      const error = `${tabletRow(KITCHEN)} [data-test="tablet-error"]`;
      await waitText(
        r,
        error,
        'That change could not be saved: This tablet is new. Pick a dashboard for it on the Home screen, then press "Turn on with this dashboard".',
        "the refusal",
      );
      const calls = await r.calls("apollo_tab/tablet/assign");
      check(
        calls.length === 1 && calls[0].mac === KITCHEN && calls[0].url_path === "night" && !("approve" in calls[0]),
        `the list sent ${JSON.stringify(calls)}`,
      );
      const kitchen = await r.eval(`__apolloMockHass.getTablets().find((tablet) => tablet.mac === ${JSON.stringify(KITCHEN)})`);
      check(kitchen.approved === false && kitchen.dashboard === null, `the tablet was turned on: ${JSON.stringify(kitchen)}`);
      check((await r.eval(`__j.find(${JSON.stringify(tabletShows(KITCHEN))}).value`)) === "tab-1", "the list kept the refused pick");
      // Then the panel hears that it is new; it keeps its place.
      await r.eval(`__apolloMockHass.emitTablets(); true`);
      await r.waitFor(`__j.find(${JSON.stringify(tabletRow(KITCHEN))})?.dataset.new === "true"`, "the tablet to read new");
      await waitText(r, tabletStatus(KITCHEN), NEW_STATUS, "the status of the tablet that is new again");
      const order = await r.eval(`__j.all('[data-test="tablet-row"]').map((row) => row.dataset.mac)`);
      check(JSON.stringify(order) === JSON.stringify([PORCH, KITCHEN]), `the tablets are in the order ${JSON.stringify(order)}`);
      check((await r.eval(`__j.find(${JSON.stringify(tabletShows(KITCHEN))}).value`)) === "", "the new tablet has a pick");
      await checkTextContrast(r, [error]);
      return r.shot("108-stale-switch-refused");
    }),
    // After a hold-to-erase Home Assistant waits for an admin to confirm in
    // Repairs. The row says so in plain words and links there.
    step("109", "erased-tablet-repairs", async (r) => {
      await r.open({ seed: "sample", night: "1", tablets: "three" }, `${home} && __j.count('[data-test="tablet-row"]') === 3`);
      const line = `${tabletRow(HALLWAY)} [data-test="tablet-reauth"]`;
      const link = `${tabletRow(HALLWAY)} [data-test="tablet-repairs"]`;
      const help = `${tabletRow(HALLWAY)} [data-test="tablet-offline-help"]`;
      check((await r.count('[data-test="tablet-reauth"]')) === 0, "a line about Repairs before anything waits");
      // Offline, before Home Assistant asks anything: what to check, in a
      // quiet grey, and the way back onto a changed Wi-Fi.
      await waitText(r, tabletStatus(HALLWAY), "Offline", "the offline tablet's status");
      check((await r.text(help)) === (await uiString(r, "tablets.offline_help")), "the offline tablet's next step");
      check((await r.count('[data-test="tablet-offline-help"]')) === 1, "the offline line is on another row too");
      const quiet = await r.eval(`__j.find(${JSON.stringify(tabletStatus(HALLWAY))}).dataset.tone`);
      check(quiet === "quiet", `the offline tablet's tone is ${quiet}`);
      await r.eval(`__apolloMockHass.setTablet(${JSON.stringify(HALLWAY)}, { reauth: "erased", reauth_name: "Apollo TAB-1 ddee02" }); true`);
      const words = (key) =>
        r.eval(`__apolloFixtures.strings[${JSON.stringify(key)}].replace("{name}", "Apollo TAB-1 ddee02")`);
      const erased = await words("tablets.reauth_erased");
      check(erased.includes('"Authentication expired for Apollo TAB-1 ddee02"'), `the words: ${erased}`);
      await r.waitFor(`__j.count(${JSON.stringify(line)}) === 1`, "the line about Repairs");
      const read = () => r.eval(`__j.find(${JSON.stringify(line)}).textContent`);
      check((await read()) === `${erased} Open Repairs`, `the line reads "${await read()}"`);
      // Round 9: the status stands out: it says where the admin is needed,
      // on an amber band, not a grey "Offline". The check comes first in the
      // line, and it is short.
      await waitText(r, tabletStatus(HALLWAY), "Waiting for you in Repairs", "the erased tablet's status");
      const status = await r.eval(`(() => { const status = __j.find(${JSON.stringify(tabletStatus(HALLWAY))});
        const style = getComputedStyle(status);
        return { tone: status.dataset.tone, border: style.borderTopStyle, background: style.backgroundColor,
          card: getComputedStyle(__j.find('[data-test="tablets"]')).backgroundColor }; })()`);
      check(
        status.tone === "attention" && status.border === "solid" && status.background !== status.card,
        `the erased tablet's status looks ${JSON.stringify(status)}`,
      );
      // Round 10: the check is the tablet's own screen, before the yes.
      // Round 11: the screen an erased tablet shows, from the contract.
      check(
        erased.startsWith(
          `Only if you erased this tablet and its screen says "${SCREENS.waiting.erased.headline}" ("${SCREENS.waiting.add.headline}" after a USB erase): confirm`,
        ),
        `the check is not first: ${erased}`,
      );
      check(erased.split(/\s+/).length <= 52, `the line has ${erased.split(/\s+/).length} words`);
      check((await r.count(help)) === 0, "the offline line stays while Home Assistant waits in Repairs");
      check((await r.count('[data-test="tablet-reauth"]')) === 1, "the line is on another row too");
      const about = await r.eval(`(() => { const link = __j.find(${JSON.stringify(link)});
        return { href: link.getAttribute("href"), named: link.getAttribute("aria-labelledby").split(" ")
          .map((id) => __apolloPanel.shadowRoot.getElementById(id).textContent).join(" ") }; })()`);
      check(
        about.href === "/config/repairs" && about.named === "Open Repairs Hallway tablet",
        `the Repairs link: ${JSON.stringify(about)}`,
      );
      if (r.setup.device === "phone") {
        const size = await r.eval(`(() => { const box = __j.find(${JSON.stringify(link)}).getBoundingClientRect();
          return { width: box.width, height: box.height }; })()`);
        check(size.width >= 44 && size.height >= 44, `the Repairs link is ${size.width} x ${size.height} px`);
        await checkRingClear(r, tabletShows(HALLWAY), link);
        await r.screen("109-repairs-link-focus");
      }
      await r.eval(`__j.find(${JSON.stringify(line)}).scrollIntoView({ block: "center" }); true`);
      await checkTextContrast(r, [line, link, tabletStatus(HALLWAY)]);
      const shot = await r.screen("109-erased-tablet-repairs");
      // Home Assistant asks for a key instead.
      await r.eval(`__apolloMockHass.setTablet(${JSON.stringify(HALLWAY)}, { reauth: "key" }); true`);
      const key = await words("tablets.reauth_key");
      await r.waitFor(`__j.find(${JSON.stringify(line)})?.textContent === ${JSON.stringify(`${key} Open Repairs`)}`, "the line about a key");
      check((await r.text(tabletStatus(HALLWAY))) === "Waiting for you in Repairs", "the status while it asks for a key");
      // The link opens Repairs inside Home Assistant, without a page load.
      await r.eval(`window.__stayed = true; window.__moves = [];
        window.addEventListener("location-changed", () => window.__moves.push(location.pathname)); true`);
      await r.click(link);
      await sleep(300);
      const moved = await r.eval(`({ stayed: window.__stayed === true, path: location.pathname, moves: window.__moves ?? null })`);
      check(
        JSON.stringify(moved) === JSON.stringify({ stayed: true, path: "/config/repairs", moves: ["/config/repairs"] }),
        `after the Repairs link: ${JSON.stringify(moved)}`,
      );
      // Confirmed: the line goes.
      await r.eval(`__apolloMockHass.setTablet(${JSON.stringify(HALLWAY)}, { reauth: null }); true`);
      await r.waitFor(`__j.count('[data-test="tablet-reauth"]') === 0`, "the line to go once confirmed");
      return shot;
    }),
    // Round 9: with two Turn on buttons, a line that comes in the lower
    // tablet's row moves only that tablet's button. The button above did
    // not move, so a press on it right then is taken at once, while the
    // moved one waits.
    step("110", "turn-on-only-the-moved-waits", async (r) => {
      await r.open(twoNew, `${home} && __j.count('[data-test="tablet-row"]') === 3 && __j.count('[data-test="dashboard-row"]') === 2`);
      await r.eval(`__apolloMockHass.holdSends(); true`);
      const order = await r.eval(`__j.all('[data-test="tablet-row"]').map((row) => row.dataset.mac)`);
      check(JSON.stringify(order) === JSON.stringify([PATIO, PORCH, KITCHEN]), `the tablets are in the order ${JSON.stringify(order)}`);
      const turnOn = (mac) => `${tabletRow(mac)} [data-test="tablet-turn-on"]`;
      await pickShows(r, PATIO, "night");
      await pickShows(r, PORCH, "tab-1");
      await r.waitFor(
        `__j.find(${JSON.stringify(turnOn(PATIO))})?.disabled === false && __j.find(${JSON.stringify(turnOn(PORCH))})?.disabled === false`,
        "both buttons after the picks",
      );
      // Nothing moved since the rows came; let any wait from before end.
      await sleep(TURN_ON_SETTLE_MS + 100);
      // Each button's place, whether it waits, and when it last moved.
      const looks = `(() => Object.fromEntries([${JSON.stringify(PATIO)}, ${JSON.stringify(PORCH)}].map((mac) => {
        const button = __j.find('[data-test="tablet-row"][data-mac="' + mac + '"] [data-test="tablet-turn-on"]');
        const box = button.getBoundingClientRect();
        const moved = __apolloPanel._turnOnMovedAt.get(mac);
        return [mac, { top: Math.round(box.top - __apolloPanel.getBoundingClientRect().top), settling: button.hasAttribute("data-settling"),
          aria: button.getAttribute("aria-disabled"), moved: moved === undefined ? null : moved }];
      })))()`;
      const before = await r.eval(looks);
      check(!before[PATIO].settling && !before[PORCH].settling, `before the line both buttons take presses: ${JSON.stringify(before)}`);
      // Note when the patio button is pressed.
      await r.eval(`(() => { window.__pressAt = null;
        __apolloPanel.shadowRoot.addEventListener("click", (event) => {
          if (window.__pressAt === null && event.target.closest?.('[data-mac="${PATIO}"] [data-test="tablet-turn-on"]')) window.__pressAt = performance.now();
        }, true);
        return true; })()`);
      // Home Assistant now waits in Repairs for the porch tablet, the lower
      // one: its row gets the line above its button.
      await r.eval(`__apolloMockHass.setTablet(${JSON.stringify(PORCH)}, { reauth: "erased", reauth_name: "Apollo TAB-1 ddee0e" }); true`);
      await r.waitFor(`__j.find(${JSON.stringify(`${tabletRow(PORCH)} [data-test="tablet-reauth"]`)})`, "the porch tablet's line");
      const after = await r.eval(looks);
      check(after[PORCH].top > before[PORCH].top && after[PORCH].settling && after[PORCH].aria === "true", `the porch button: ${JSON.stringify(after[PORCH])}`);
      check(
        after[PATIO].top === before[PATIO].top && !after[PATIO].settling && after[PATIO].aria === null && after[PATIO].moved === before[PATIO].moved,
        `the patio button did not move, yet it is ${JSON.stringify(after[PATIO])}`,
      );
      // A press on the patio button right then turns that tablet on.
      await r.click(turnOn(PATIO));
      await r.waitFor(`__j.find(${JSON.stringify(tabletRow(PATIO))})?.dataset.new === "false"`, "the patio tablet to be turned on", 2000);
      // Measured from when the porch button moved for the line (it moves
      // again once the patio row loses its button).
      const gap = (await r.eval(`window.__pressAt`)) - after[PORCH].moved;
      check(gap >= 0 && gap < TURN_ON_SETTLE_MS, `the press came ${Math.round(gap)} ms after the porch button moved, too late to tell`);
      const calls = await r.calls("apollo_tab/tablet/assign");
      check(
        calls.length === 1 && calls[0].mac === PATIO && calls[0].url_path === "night" && calls[0].approve === true,
        `the press on the button that did not move sent ${JSON.stringify(calls)}`,
      );
      check((await r.eval(`__j.find(${JSON.stringify(tabletRow(PORCH))})?.dataset.new`)) === "true", "the porch tablet was turned on");
      const shot = await r.shot("110-turn-on-only-the-moved-waits");
      await r.eval(`__apolloMockHass.finishSends(); true`);
      return shot;
    }),
  ];

  // The panel's visual system (build plan, package 1): one set of text
  // sizes, control heights, one filled button per screen, states that show,
  // bars in the sidebar's colours, a picture that scales and stays left to
  // right in a right-to-left Home Assistant.
  const foundation = [
    step("111", "tokens-and-type", async (r) => {
      const sizes = async (where) => {
        const wrong = await r.eval(`__ui.textSizes().filter(([, size]) => ![12, 14, 16, 20].includes(size))`);
        check(wrong.length === 0, `${where}: text at other sizes: ${JSON.stringify(wrong.slice(0, 6))}`);
      };
      await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
      await r.eval(UI);
      await sizes("the start screen");
      await r.waitFor(`!__j.animating(__j.find('[data-test="create"]'))`, "the create button to settle");
      const body = await r.eval(`getComputedStyle(__apolloPanel).fontSize`);
      check(body === "14px", `body text is ${body}`);
      const create = await r.eval(`(() => { const style = getComputedStyle(__j.find('[data-test="create"]'));
        return [style.backgroundColor, style.color]; })()`);
      check(
        create[0] === "rgb(0, 123, 159)" && create[1] === "rgb(255, 255, 255)",
        `"Create a dashboard" is ${create.join(" on ")}`,
      );

      await openSample(r);
      await r.eval(UI);
      await selectRow(r, "0.1.0");
      await sizes("the editor with a card selected");
      await leaveEditMode(r);
      await r.click('[data-test="add-card"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
      await sizes("the picker");
      await r.key("Escape");
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");

      // Another accent reaches the editor and the picker, which inherit the
      // values the panel works out for its own host.
      const setAccent = (value) =>
        r.eval(`(() => { const root = document.documentElement;
          if (${JSON.stringify(value)}) root.style.setProperty("--primary-color", ${JSON.stringify(value)});
          else root.style.removeProperty("--primary-color");
          __apolloMockHass.themes = { theme: "default", accent: ${JSON.stringify(value)} };
          __apolloPanel.hass = __apolloMockHass; return true; })()`);
      const look = (selector) =>
        `(() => { const node = __j.find('${selector}'); if (!node) return null;
          const style = getComputedStyle(node); return [style.backgroundColor, style.color]; })()`;
      try {
        await setAccent("#f5b547");
        await r.waitFor(`${look('[data-test="add-card"]')}?.[0] === "rgb(245, 181, 71)"`, "Add card in the new accent");
        const add = await r.eval(look('[data-test="add-card"]'));
        check(add[1] === "rgb(17, 17, 17)", `"Add card" has ${add[1]} words on ${add[0]}`);
        const accentText = await r.eval(`getComputedStyle(__apolloPanel).getPropertyValue("--tab-accent-text").trim()`);
        // On a phone Add card was read with the edit mode closed; the card's
        // form opens again for "Change".
        await selectRow(r, "0.1.0");
        const change = await r.eval(`(() => { const node = __j.find('.side [data-test="change-device"]');
          return node && [getComputedStyle(node).color, node.classList.contains("text"),
            getComputedStyle(__j.find('.side .side-title')).color]; })()`);
        check(change && change[1], `"Change" is not a text button: ${JSON.stringify(change)}`);
        check(change[0] === accentText && change[0] !== change[2], `"Change" is ${change[0]}, the accent as text is ${accentText}`);
        await leaveEditMode(r);
        await r.click('[data-test="add-card"]');
        await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
        await r.click('[data-test="tile"][data-component="apollo/room"]');
        await r.waitFor(`__j.find('[data-test="pick-add"]')`, "the device step");
        // Read as it is once the card has its devices: enabled, with no
        // fade in between.
        const pick = await r.eval(`(() => { const node = __j.find('[data-test="pick-add"]');
          node.style.transition = "none"; node.disabled = false; const style = getComputedStyle(node);
          const result = [style.backgroundColor, style.color]; node.disabled = true; node.style.transition = "";
          return result; })()`);
        check(
          pick[0] === "rgb(245, 181, 71)" && pick[1] === "rgb(17, 17, 17)",
          `"Add" in the picker is ${pick.join(" on ")}`,
        );
        const shot = await r.shot("111-tokens-and-type");
        await r.key("Escape");
        await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
        return shot;
      } finally {
        await setAccent(null);
      }
    }),
    step("112", "control-sizes", async (r) => {
      const phone = r.setup.device === "phone";
      const measure = async (where) => {
        const found = await r.eval(`__ui.controls()`);
        check(found.length > 0, `${where}: nothing to press`);
        const problems = [];
        for (const control of found) {
          if (phone) {
            if (control.height < 43.5) problems.push(control);
            continue;
          }
          if (control.height < 31.5) problems.push(control);
          if (control.kind === "plain" && (control.minHeight !== "40px" || control.height < 39.5)) problems.push(control);
          if (control.kind === "field" && (control.minHeight !== "40px" || control.height < 39.5)) problems.push(control);
          // Tabs are as high as "Add page" beside them (polish decision 3).
          if (control.kind === "tab" && Math.abs(control.height - 40) > 0.5) problems.push(control);
          if (control.kind === "row" && control.height <= 40) problems.push(control);
        }
        check(problems.length === 0, `${where}: ${JSON.stringify(problems.slice(0, 5))}`);
      };
      await r.open({ seed: "sample" }, `${home} && __j.find('[data-test="dashboard-row"]')`);
      await r.eval(UI);
      await measure("the start screen");
      await openSample(r);
      await r.eval(UI);
      await selectRow(r, "0.1.0");
      await measure("the editor with a card selected");
      await leaveEditMode(r);
      await r.click('[data-test="add-card"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
      await measure("the picker");
      await r.click('[data-test="tile"][data-component="apollo/room"]');
      await r.waitFor(`__j.find('[data-test="pick-add"]')`, "the device step");
      await measure("the picker's device step");
      await r.key("Escape");
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
      await r.clearSelection();
      await r.click('[data-test="page-delete"]');
      await r.waitFor(`__j.find('dialog[data-test="confirm"][open]')`, "the question");
      const confirm = await r.eval(`__ui.controls().filter((control) => control.test && control.test.startsWith("confirm"))`);
      check(confirm.length === 2, `the question has ${JSON.stringify(confirm)}`);
      for (const control of confirm) {
        check(control.height >= (phone ? 43.5 : 39.5), `${control.test} is ${control.height} px high`);
      }
      const shot = await r.shot("112-control-sizes");
      await r.key("Escape");
      await r.waitFor(`!__j.find('dialog[data-test="confirm"]')`, "the question to close");
      return shot;
    }),
    step("113", "one-filled-button", async (r) => {
      const filled = async (where, expected) => {
        const found = await r.eval(`__ui.filled()`);
        check(
          JSON.stringify(found.sort()) === JSON.stringify([...expected].sort()),
          `${where}: the filled buttons are ${JSON.stringify(found)}, not ${JSON.stringify(expected)}`,
        );
      };
      await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
      await r.eval(UI);
      await filled("the empty start screen", ["create"]);
      await r.open({ seed: "sample", night: "1", tablets: "two-new" }, `${home} && __j.count('[data-test="tablet-row"]') === 3`);
      await r.eval(UI);
      await filled("the start screen with two new tablets", ["tablet-turn-on", "tablet-turn-on"]);
      const rows = await r.eval(`__j.all('[data-test="tablet-turn-on"].primary').filter((node) => __j.visible(node))
        .map((node) => node.closest('[data-test="tablet-row"]')?.dataset.new)`);
      check(JSON.stringify(rows) === JSON.stringify(["true", "true"]), `the filled buttons are in rows ${JSON.stringify(rows)}`);

      await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
      await r.click('[data-test="create"]');
      await r.waitFor(`__j.find('[data-test="add-first-card"]')`, "the empty editor");
      await r.waitSaved("new dashboard");
      await r.eval(UI);
      await filled("the empty editor", ["add-first-card"]);

      await openSample(r);
      await r.eval(UI);
      await filled("the editor with cards", ["add-card"]);
      await r.click('[data-test="page-delete"]');
      await r.waitFor(`__j.find('dialog[data-test="confirm"][open]')`, "the question");
      const inDialog = await r.eval(`__j.all('dialog[data-test="confirm"] button').filter((node) => __j.visible(node))
        .filter((node) => node.classList.contains("primary") || node.classList.contains("danger")).map((node) => node.dataset.test)`);
      check(JSON.stringify(inDialog) === JSON.stringify(["confirm-ok"]), `the question's next step is ${JSON.stringify(inDialog)}`);
      await r.key("Escape");
      await r.waitFor(`!__j.find('dialog[data-test="confirm"]')`, "the question to close");

      await r.eval(`__apolloMockHass.failSaves(100); true`);
      await selectRow(r, "0.1.0");
      await r.click('[data-test="wider"]');
      await r.waitFor(`__j.saveState() === "error" && __j.find('[data-test="save-retry"]')`, "the save to fail");
      await filled("the editor after a failed save", ["save-retry"]);
      await r.eval(`__apolloMockHass.failSaves(0); true`);
      await r.click('[data-test="save-retry"]');
      await r.waitSaved("after retry");
      // On a phone Add card is hidden while the edit mode is open.
      await leaveEditMode(r);
      await filled("the editor after the retry", ["add-card"]);
      await r.clearSelection();

      await r.click('[data-test="add-card"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
      await r.click('[data-test="tile"][data-component="apollo/room"]');
      await r.waitFor(`__j.find('[data-test="pick-add"]')`, "the device step");
      const inPicker = await r.eval(`__j.all('dialog[data-test="picker"] button.primary').filter((node) => __j.visible(node))
        .map((node) => node.dataset.test)`);
      check(JSON.stringify(inPicker) === JSON.stringify(["pick-add"]), `the picker's filled buttons: ${JSON.stringify(inPicker)}`);
      const shot = await r.shot("113-one-filled-button");
      await r.key("Escape");
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
      return shot;
    }),
    step(
      "114",
      "hover-and-focus",
      async (r) => {
        // What the pointer changes: the background (and its layer), the
        // edge, the shadow.
        const lookOf = (selector) => `(() => { const node = __j.find('${selector}'); const style = getComputedStyle(node);
          return [style.backgroundColor, style.backgroundImage, style.borderTopColor, style.boxShadow, style.outlineStyle].join(" | "); })()`;
        const away = async () => {
          await r.browser.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: 1, y: 799 });
          await sleep(200);
        };
        const hover = async (selector) => {
          await away();
          const point = await r.eval(`__j.target('${selector}')`);
          check(point && !point.error, point?.error || `cannot reach ${selector}`);
          await away();
          const before = await r.eval(lookOf(selector));
          await r.browser.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: point.x, y: point.y });
          await sleep(250);
          const after = await r.eval(lookOf(selector));
          check(before !== after, `the pointer over ${selector} changes nothing (${after})`);
        };
        await openSample(r);
        await hover('[data-test="page-tab"][aria-selected="false"]');
        await hover('[data-test="list-row"][data-source="0.1.0"]');
        await hover('[data-test="add-page"]');
        const disabled = await r.eval(`(() => { const node = __j.find('[data-test="undo"]');
          return [node.disabled, getComputedStyle(node).opacity]; })()`);
        check(disabled[0] === true && disabled[1] === "1", `Undo while there is nothing to undo: ${JSON.stringify(disabled)}`);
        await r.click('[data-test="add-card"]');
        await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
        await sleep(300);
        await hover('[data-test="tile"][data-component="apollo/fan-speed"]');
        await r.key("Escape");
        await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
        // Focus from the keyboard: one ring, 2 px wide and 2 px away.
        await r.eval(`__j.find('[data-test="add-page"]').focus(); true`);
        await r.key("Tab");
        const ring = await r.eval(`(() => { const node = __j.active(); const style = getComputedStyle(node);
          return { tag: node.tagName, test: node.dataset.test, width: style.outlineWidth, style: style.outlineStyle,
            offset: style.outlineOffset }; })()`);
        check(
          ring.tag === "BUTTON" && ring.width === "2px" && ring.style === "solid" && ring.offset === "2px",
          `a focused button has the ring ${JSON.stringify(ring)}`,
        );
        return r.shot("114-hover-and-focus");
      },
      { desktopOnly: true },
    ),
    step("115", "bars-follow-sidebar", async (r) => {
      // Every element of the bar with words of its own has 4.5:1 against
      // the bar, every icon 3:1; disabled buttons are left out.
      const readable = async (bar, where) => {
        const problems = await r.eval(`__ui.barProblems('${bar}')`);
        check(problems.length === 0, `${where}: ${JSON.stringify(problems.slice(0, 5))}`);
        const kinds = await r.eval(`__j.all('${bar} .primary, ${bar} .text, ${bar} .link').filter((node) => __j.visible(node))
          .map((node) => __j.describe(node))`);
        check(kinds.length === 0, `${where}: the bar holds ${JSON.stringify(kinds)}`);
      };
      const sidebar = (on) =>
        r.eval(`(() => { const style = document.documentElement.style;
          if (${on}) { style.setProperty("--sidebar-background-color", "#123456"); style.setProperty("--sidebar-text-color", "#fedcba"); }
          else { style.removeProperty("--sidebar-background-color"); style.removeProperty("--sidebar-text-color"); }
          return true; })()`);
      const appHeader = (on) =>
        r.eval(`(() => { const style = document.documentElement.style;
          if (${on}) { style.setProperty("--app-header-background-color", "#ff00ff"); style.setProperty("--app-header-text-color", "#00ff00"); }
          else { style.removeProperty("--app-header-background-color"); style.removeProperty("--app-header-text-color"); }
          return true; })()`);
      const colours = (bar) => `__j.all('${bar}, ${bar} *').filter((node) => __j.visible(node)).map((node) => {
          const style = getComputedStyle(node); return style.backgroundColor + " " + style.color; }).join(";")`;
      const check3 = async (bar, where) => {
        const title = await r.eval(`__j.textContrast(__j.find('${bar} h1'))`);
        check(title >= 4.5, `${where}: the title has ${title}`);
        await readable(bar, where);
        try {
          await sidebar(true);
          await r.waitFor(`!__j.all('${bar} *').some((node) => __j.animating(node))`, "the bar to settle");
          const look = await r.eval(`(() => { const style = getComputedStyle(__j.find('${bar}'));
            return [style.backgroundColor, style.color]; })()`);
          check(
            look[0] === "rgb(18, 52, 86)" && look[1] === "rgb(254, 220, 186)",
            `${where} with the sidebar's colours: ${look.join(", ")}`,
          );
          await readable(bar, `${where} with the sidebar's colours`);
        } finally {
          await sidebar(false);
        }
        const before = await r.eval(colours(bar));
        try {
          await appHeader(true);
          const after = await r.eval(colours(bar));
          check(before === after, `${where} changes with the app header's colours`);
        } finally {
          await appHeader(false);
        }
      };
      await r.open({ seed: "sample", tablets: "three" }, `${home} && __j.find('[data-test="dashboard-row"]')`);
      await r.eval(UI);
      await check3(".panel-header", "the start screen's bar");
      await r.click('[data-test="open-advanced"]');
      await r.waitFor(`__j.find('[data-test="advanced"]')`, "Advanced");
      await check3(".panel-header", "Advanced's bar");
      await openSample(r, { tablets: "three" });
      await r.eval(UI);
      await selectRow(r, "0.1.0");
      await r.click('[data-test="wider"]');
      await r.waitSaved("wider");
      await check3(".ed-header", "the editor's bar");
      return r.shot("115-bars-follow-sidebar");
    }),
    step(
      "116",
      "picture-scales",
      async (r) => {
        await openSample(r);
        await r.waitFor(`__j.find('[data-test="theme"]')`, "the dashboard's theme list");
        await r.eval(`(() => { const list = __j.find('[data-test="theme"]'); list.value = "mono";
          list.dispatchEvent(new Event("change", { bubbles: true })); return true; })()`);
        await r.waitSaved("theme");
        const page = `__j.designer().shadowRoot.querySelector(".page-host").shadowRoot`;
        await r.waitFor(
          `(() => { const card = ${page}.querySelector(".at-card"); return card && getComputedStyle(card).getPropertyValue("--at-r").trim() === "8px"; })()`,
          "the picture in the Mono theme",
        );
        const found = await r.eval(`(() => {
          const stage = __j.find('[data-test="canvas"]').getBoundingClientRect();
          const root = ${page};
          const card = root.querySelector(".at-card");
          // The sample's graphs have no values here, so a line is put into
          // one of them for the moment it takes to read its width.
          const chart = root.querySelector(".at-chart");
          let stroke = null;
          if (chart) {
            const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
            line.setAttribute("class", "at-chart-data at-chart-line");
            line.setAttribute("points", "0,0 10,10");
            chart.append(line);
            stroke = parseFloat(getComputedStyle(line).strokeWidth);
            line.remove();
          }
          const style = getComputedStyle(card);
          return { scale: stage.width / 1280, radius: parseFloat(style.borderTopLeftRadius),
            border: parseFloat(style.borderTopWidth), bw: style.getPropertyValue("--at-bw").trim(), stroke }; })()`);
        check(found.bw === "2px", `the Mono theme's border is ${found.bw}`);
        check(Math.abs(found.radius - 8 * found.scale) <= 0.5, `a card's corner is ${found.radius} px at scale ${found.scale}`);
        check(Math.abs(found.border - 2 * found.scale) <= 1, `a card's border is ${found.border} px at scale ${found.scale}`);
        check(found.stroke !== null, "no graph on the picture");
        check(Math.abs(found.stroke - 3 * found.scale) <= 0.5, `the graph's line is ${found.stroke} px at scale ${found.scale}`);
        await r.eval(`__j.find('[data-test="canvas"]').scrollIntoView({ block: "start" }); true`);
        return r.shot("116-picture-scales");
      },
      { desktopOnly: true },
    ),
    step("117", "right-to-left", async (r) => {
      const page = `__j.designer().shadowRoot.querySelector(".page-host").shadowRoot`;
      const cards = () =>
        r.eval(`(() => { const left = ${page}.querySelector(".at-page").getBoundingClientRect().left;
          return [...${page}.querySelectorAll(".at-card")].map((card) =>
            [card.innerText, Math.round(card.getBoundingClientRect().left - left)]); })()`);
      const rtl = (on) => r.eval(`(() => { if (${on}) document.documentElement.setAttribute("dir", "rtl");
        else document.documentElement.removeAttribute("dir"); return true; })()`);
      try {
        await r.open({ seed: "sample" }, `${home} && __j.find('[data-test="dashboard-row"]')`);
        await rtl(true);
        await sleep(200);
        await checkNoSidewaysScroll(r);
        await rtl(false);
        await openSample(r);
        const before = await cards();
        check(before.length > 0, "no cards on the picture");
        await rtl(true);
        await sleep(300);
        const after = await cards();
        check(JSON.stringify(after) === JSON.stringify(before), `right to left the picture changes: ${JSON.stringify(after.slice(0, 3))} instead of ${JSON.stringify(before.slice(0, 3))}`);
        await checkNoSidewaysScroll(r);
        await r.click('[data-test="add-card"]');
        await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
        await sleep(300);
        await checkNoSidewaysScroll(r);
        const shot = await r.shot("117-right-to-left");
        await r.key("Escape");
        await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
        return shot;
      } finally {
        await rtl(false);
      }
    }),
    step(
      "118",
      "narrowest-phone",
      async (r) => {
        await r.browser.send("Emulation.setDeviceMetricsOverride", { width: 320, height: 568, deviceScaleFactor: 1, mobile: true });
        try {
          const small = async (where) => {
            await checkNoSidewaysScroll(r, 320);
            const found = (await r.eval(`__ui.controls()`)).filter((control) => control.height < 43.5);
            check(found.length === 0, `${where} at 320 px: ${JSON.stringify(found.slice(0, 5))}`);
          };
          await r.open({ seed: "sample" }, `${home} && __j.find('[data-test="dashboard-row"]')`);
          await r.eval(UI);
          await small("the start screen");
          await openSample(r);
          await r.eval(UI);
          await selectRow(r, "0.1.0");
          await small("the editor with a card selected");
          await leaveEditMode(r);
          await r.click('[data-test="add-card"]');
          await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
          await sleep(300);
          await small("the picker");
          const shot = await r.shot("118-narrowest-phone");
          await r.key("Escape");
          await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
          return shot;
        } finally {
          await r.viewport();
        }
      },
      { desktopOnly: true },
    ),
  ];

  // The editor's workspace (build plan, package 2): a shell as tall as the
  // window, the picture fitted to the free space, the drawer, the compact
  // and short layouts, the edit mode, zoom and the toast's home.
  const sizeTo = async (r, width, height, mobile = false) => {
    await r.browser.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile });
    await sleep(100);
    await r.eval(`new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve(true))))`);
  };
  // The stand-in for Home Assistant's docked sidebar, 256 px, and its removal.
  const dock = (r, on) =>
    r.eval(`(() => { document.getElementById("ws-sidebar")?.remove();
      __apolloPanel.style.marginLeft = ""; __apolloPanel.style.width = "";
      if (${on}) { const bar = document.createElement("div"); bar.id = "ws-sidebar";
        bar.style.cssText = "position:fixed;left:0;top:0;bottom:0;width:256px;background:#333;z-index:1";
        document.body.prepend(bar); __apolloPanel.style.marginLeft = "256px"; __apolloPanel.style.width = "calc(100% - 256px)"; }
      return true; })()`);
  const shell = (r) =>
    r.eval(`(() => { const d = __j.designer().shadowRoot; const box = (node) => {
        if (!node || !node.getClientRects().length) return null; const rect = node.getBoundingClientRect();
        return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height }; };
      const root = d.querySelector(".root");
      return { band: ["wide", "medium", "compact", "short"].find((name) => root.classList.contains(name)) || null,
        root: box(root), header: box(d.querySelector(".ed-header")), strip: box(d.querySelector(".tab-strip")),
        main: box(d.querySelector(".main")), stage: box(d.querySelector('[data-test="canvas"]')),
        area: box(d.querySelector(".stage-area")), side: box(d.querySelector('[data-test="side"]')),
        blocking: box(d.querySelector(".root > .banners")), status: box(d.querySelector(".status-strip")),
        doc: document.documentElement.scrollHeight, innerWidth, innerHeight }; })()`);
  // The picture is `width` px wide (within 1 px) once the layout settled.
  const pictureIs = async (r, width, when) => {
    try {
      await r.waitFor(
        `(() => { const stage = __j.designer().shadowRoot.querySelector('[data-test="canvas"]');
          return stage && Math.abs(stage.getBoundingClientRect().width - ${width}) <= 1; })()`,
        `the picture to be ${width} px wide ${when}`,
        4000,
      );
    } catch (error) {
      throw new Error(`${error.message}; ${JSON.stringify((await shell(r)).stage)}`);
    }
  };
  // A new dashboard with one light on it: no page notice above the picture.
  const oneCard = async (r) => {
    await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
    await r.click('[data-test="create"]');
    await r.waitFor(`__j.find('[data-test="add-first-card"]')`, "the new dashboard's empty editor");
    await r.addCard("add-first-card", "apollo/light", "light.kitchen");
    await r.waitFor(`__j.count('[data-test="hit"]') === 1`, "the light on the picture");
    await r.waitSaved("the light added");
    await leaveEditMode(r);
    if (await r.count(pressed)) {
      await r.clearSelection();
    }
    check((await r.count(".page-notice")) === 0, "the new dashboard has a page notice");
  };

  // The only card of the real dashboard that the tablet can draw (its
  // heading) removed with Delete on the picture: focus goes to Add card,
  // and is still there once the picture is drawn again without it (polish
  // decision 13). `layout` puts the editor in the band to check.
  const lastDrawnCardGone = async (r, layout, when) => {
    await r.open({ seed: "real", route: "/edit/tab-1" }, editorReady);
    await layout();
    await r.waitFor(`__j.count('[data-test="hit"]') === 1`, `the heading on the picture ${when}`);
    await r.eval(`__j.find('[data-test="hit"]').focus(); true`);
    await r.key("Delete");
    await r.waitFor(`__j.find('[data-test="toast-undo"]')`, `the removal's toast ${when}`);
    const isAdd = (focus) => focus === "add-card" || focus === "add-first-card";
    const now = await focused(r);
    check(isAdd(now), `${when}, after the last card on the picture was removed focus is on ${now}, not Add card`);
    await r.waitSaved(`the heading removed ${when}`);
    await r.waitFor(`__j.count('[data-test="hit"]') === 0`, `the picture without the heading ${when}`);
    await sleep(500);
    const later = await focused(r);
    check(isAdd(later), `${when}, once the picture was drawn again focus is on ${later}, not Add card`);
  };

  const workspace = [
    step("119", "shell-fits-window", async (r) => {
      await openSample(r);
      const fits = async (when) => {
        const now = await shell(r);
        check(now.doc <= now.innerHeight, `${when}: the document is ${now.doc} px tall in a ${now.innerHeight} px window`);
        check(Math.abs(now.root.bottom - now.innerHeight) <= 1, `${when}: the editor ends at ${now.root.bottom}, the window at ${now.innerHeight}`);
        check(!now.blocking, `${when}: a notice that blocks shows`);
        check(Math.abs(now.main.top - now.strip.bottom) <= 1, `${when}: the stage column starts at ${now.main.top}, the page strip ends at ${now.strip.bottom}`);
        return now;
      };
      const before = await fits("in the editor");
      const shot = await r.shot("119-shell-fits-window");
      if (r.setup.device === "desktop") {
        check(before.side.bottom <= before.innerHeight + 1 && before.stage.bottom <= before.innerHeight, `the inspector or the picture ends below the window: ${JSON.stringify(before)}`);
        await selectRow(r, "0.1.0");
        // The form took the list's place, and the pressed row went with the
        // list: the form's title has focus, not the page.
        check((await focused(r)) === "side-title", `after a card was chosen in the list focus is on ${await focused(r)}, not the form's title`);
        const selected = await fits("with a card selected");
        check(selected.side.bottom <= selected.innerHeight + 1 && selected.stage.bottom <= selected.innerHeight, `with a card selected the inspector or the picture ends below the window: ${JSON.stringify(selected)}`);
        // A pinch zoom changes neither the shell's height nor its layout.
        await r.browser.send("Emulation.setPageScaleFactor", { pageScaleFactor: 2 });
        try {
          await sleep(400);
          const zoomed = await shell(r);
          check(zoomed.root.height === selected.root.height && zoomed.band === selected.band,
            `zoomed in, the editor is ${zoomed.root.height} px (${zoomed.band}), not ${selected.root.height} px (${selected.band})`);
        } finally {
          await r.browser.send("Emulation.setPageScaleFactor", { pageScaleFactor: 1 });
        }
        // From the form, Escape reaches the editor and lets the card go.
        await r.key("Escape");
        await r.waitFor(`!__j.find('${pressed}')`, "Escape to let the card go after it was chosen in the list");
        check(await focused(r), "after Escape focus fell to the page");
      } else {
        // The page column scrolls under the bars; they stay where they are.
        await r.eval(`(() => { const main = __j.designer().shadowRoot.querySelector(".main"); main.scrollTop = main.scrollHeight; return true; })()`);
        await sleep(300);
        const scrolled = await fits("with the page column scrolled to its end");
        check(scrolled.header.top === before.header.top && scrolled.strip.top === before.strip.top,
          `the bars moved when the page column scrolled: ${JSON.stringify([before.header, before.strip, scrolled.header, scrolled.strip])}`);
      }
      // Pages added until the tabs scroll: the new page's tab is whole in
      // the tab list, not under Add page or Add card.
      const tabs = await r.count('[data-test="page-tab"]');
      for (let added = 1; added <= 8; added += 1) {
        await r.click('[data-test="add-page"]');
        await r.waitFor(`__j.count('[data-test="page-tab"]') === ${tabs + added}`, `page ${tabs + added}`);
      }
      await sleep(300);
      const strip = await r.eval(`(() => { const edges = (node) => { const rect = node.getBoundingClientRect(); return { left: rect.left, right: rect.right }; };
        const list = __j.designer().shadowRoot.querySelector(".tabs");
        return { tab: edges(__j.find('[data-test="page-tab"][aria-selected="true"]')), list: edges(list),
          scrolls: list.scrollWidth > list.clientWidth, add: edges(__j.find('[data-test="add-page"]')) }; })()`);
      check(strip.scrolls, `the tabs do not scroll with ${tabs + 8} pages, so the check below means nothing`);
      check(strip.tab.left >= strip.list.left - 1 && strip.tab.right <= strip.list.right + 1 && strip.tab.right <= strip.add.left + 1,
        `the new page's tab is not whole in the tab list: ${JSON.stringify(strip)}`);
      await checkNoSidewaysScroll(r);
      return shot;
    }),
    step(
      "120",
      "fit-table",
      async (r) => {
        const sizes = [
          [1280, 800, false, 879],
          [1440, 800, true, 796],
          [1280, 800, true, 960],
          [1920, 1080, false, 1280],
          [2560, 1440, false, 1280],
          [1280, 720, false, 806],
          [1366, 768, false, 883],
        ];
        let shot = null;
        try {
          await oneCard(r);
          for (const [width, height, docked, picture] of sizes) {
            await sizeTo(r, width, height);
            await dock(r, docked);
            const when = `at ${width} x ${height}${docked ? " with the sidebar docked" : ""}`;
            await pictureIs(r, picture, when);
            const now = await shell(r);
            check(now.stage.width <= 1280 && now.stage.bottom <= now.innerHeight, `${when} the picture is ${JSON.stringify(now.stage)}`);
            await checkNoSidewaysScroll(r, width);
            if (width === 1920) {
              shot = await r.screen("120-fit-table-1920");
            }
          }
        } finally {
          await dock(r, false);
          await r.viewport();
        }
        return shot;
      },
      { desktopOnly: true },
    ),
    step(
      "121",
      "medium-drawer",
      async (r) => {
        let shot = null;
        try {
          // A full row of lights, so a card ends at the row's right end.
          await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
          await r.eval(`__apolloMockHass.addDashboard("row-1", "Row", ${JSON.stringify(ROW_CONFIG)});
            __apolloOpenPanel("/edit/row-1"); true`);
          await r.waitFor(`__j.count('[data-test="hit"]') >= 3`, "the row of lights");
          await sizeTo(r, 1280, 800);
          await dock(r, true);
          await r.waitFor(`__j.designer().shadowRoot.querySelector(".root.medium")`, "the medium layout");
          check((await r.count(".page-notice")) === 0, "the row of lights has a page notice");
          await pictureIs(r, 960, "with nothing selected");
          const closed = await shell(r);
          check(!closed.side || closed.side.left >= closed.root.right - 1, `the closed drawer shows: ${JSON.stringify(closed.side)}`);
          // The card at the right end of the first row.
          const key = await r.eval(`(() => { const hits = __j.all('[data-test="hit"]').map((hit) => [hit, hit.getBoundingClientRect()]);
            const top = Math.min(...hits.map(([, rect]) => rect.top));
            const row = hits.filter(([, rect]) => Math.abs(rect.top - top) < 2).sort((a, b) => b[1].right - a[1].right);
            return row[0][0].dataset.source; })()`);
          const card = `[data-test="hit"][data-source="${key}"]`;
          await r.click(card);
          await r.waitFor(`__j.find('${card}[aria-pressed="true"]') && __j.designer().shadowRoot.querySelector(".root.drawer-open")`, "the drawer to open");
          await sleep(400);
          await pictureIs(r, 960, "with the drawer open");
          const clear = await r.eval(`(() => { const side = __j.designer().shadowRoot.querySelector('[data-test="side"]').getBoundingClientRect();
            const hit = __j.find('${card}').getBoundingClientRect(); return { card: hit.right, drawer: side.left }; })()`);
          check(clear.card <= clear.drawer - 16 + 0.5, `the card ends at ${clear.card}, the drawer starts at ${clear.drawer}`);
          shot = await r.screen("121-medium-drawer");
          // Made 5 wide, it slides only until its left edge is at the stage's padding.
          for (let press = 0; press < 6 && !(await r.text('.size-value')).startsWith("5 wide"); press += 1) {
            await r.click('[data-test="wider"]');
            await sleep(150);
          }
          check((await r.text('.size-value')).startsWith("5 wide"), `the card is ${await r.text('.size-value')}`);
          await r.waitSaved("made 5 wide");
          await sleep(500);
          const wide = await r.eval(`(() => { const area = __j.designer().shadowRoot.querySelector(".stage-area").getBoundingClientRect();
            const hit = __j.find('[data-test="hit"][aria-pressed="true"]').getBoundingClientRect(); return { card: hit.left, area: area.left }; })()`);
          check(Math.abs(wide.card - (wide.area + 16)) <= 1, `the 5 wide card starts at ${wide.card}, the stage's padding at ${wide.area + 16}`);
          await r.click('[data-test="close-panel"]');
          await r.waitFor(`!__j.designer().shadowRoot.querySelector(".root.drawer-open")`, "the drawer to close");
          await sleep(400);
          const back = await r.eval(`getComputedStyle(__j.designer().shadowRoot.querySelector(".device")).transform`);
          check(back === "none", `the picture is still moved: ${back}`);
          // The list is in the closed drawer, out of reach: after Done focus
          // is on the card on the picture, not on the page.
          check((await focused(r)) === "hit", `after Done with the drawer closed focus is on ${await focused(r)}, not the card on the picture`);
          await checkNoSidewaysScroll(r, 1280);
          // The window made narrower and wider again with a card selected:
          // focus stays in the editor (the edit mode's title, then the
          // drawer's form), so Escape still lets the card go.
          const first = '[data-test="hit"]';
          await r.click(first);
          await r.waitFor(`__j.designer().shadowRoot.querySelector(".root.drawer-open")`, "the drawer to open again");
          await dock(r, false);
          await sizeTo(r, 820, 800);
          await r.waitFor(`__j.find('[data-test="side"][data-mode="edit"]')`, "the edit mode at 820 px");
          await r.waitFor(`__j.active()?.dataset?.test === "side-title"`, "focus on the edit mode's title after the window got narrower");
          await sizeTo(r, 1280, 800);
          await dock(r, true);
          await r.waitFor(`__j.designer().shadowRoot.querySelector(".root.medium.drawer-open")`, "the drawer again at 1024 px");
          await sleep(300);
          check(await focused(r), "after the window got wider again focus fell to the page");
          await r.key("Escape");
          await r.waitFor(`!__j.find('${pressed}') && !__j.designer().shadowRoot.querySelector(".root.drawer-open")`, "Escape to let the card go and close the drawer");
          check((await focused(r)) === "hit", `after Escape focus is on ${await focused(r)}, not the card on the picture`);
          // Remove card in the drawer's form: the drawer closes with the list
          // in it, so focus goes on to the next card on the picture.
          await r.click(first);
          await r.waitFor(`__j.find('[data-test="remove-card"]')`, "the card's form in the drawer");
          const removedKey = await r.eval(`__j.find('[data-test="hit"][aria-pressed="true"]').dataset.source`);
          await pressRemoving(r, '[data-test="remove-card"]', "hit", "removing a card in the drawer's form");
          await r.waitSaved("after the removal in the drawer");
          await sleep(400);
          check((await focused(r)) === "hit", `once the picture was drawn again focus is on ${await focused(r)}`);
          // Undo in the toast: the card comes back with focus on the picture,
          // as the list is in the closed drawer (polish decision 13).
          await r.eval(`__j.find('[data-test="toast-undo"]').focus(); true`);
          await r.key("Enter");
          await r.waitSaved("after Undo in the drawer layout");
          await r.waitFor(`__j.active()?.dataset?.focus === "hit:${removedKey}"`, `focus on the card that came back (${removedKey}) after Undo`);
          // A card moved in the list from the keyboard stays in the list,
          // so it can be moved again: its form does not take the list's
          // place. The card moved is the one made 5 wide, the only one that
          // differs from the others.
          await r.click('[data-test="open-cards"]');
          await r.waitFor(`__j.find('[data-test="list-row"]')`, "the card list in the drawer");
          const wideAt = async () => (await r.draft()).views[0].sections[0].cards.findIndex((card) => card.grid_options);
          let at = await wideAt();
          check(at >= 0, "no card with a size of its own is left to move");
          const way = at >= 2 ? -1 : 1;
          const arrow = { key: way < 0 ? "ArrowLeft" : "ArrowRight", windowsVirtualKeyCode: way < 0 ? 37 : 39, modifiers: 8 };
          arrow.code = arrow.key;
          await r.eval(`__j.find('[data-test="list-row"][data-source="0.0.${at}"]').focus(); true`);
          for (const press of [1, 2]) {
            await r.browser.send("Input.dispatchKeyEvent", { type: "rawKeyDown", ...arrow });
            await r.browser.send("Input.dispatchKeyEvent", { type: "keyUp", ...arrow });
            await sleep(300);
            const now = await wideAt();
            check(now === at + way, `press ${press} of Shift+${arrow.key} on a list row left the card at ${now}, not ${at + way}`);
            at = now;
            const row = await r.eval(`({ test: __j.active()?.dataset?.test || null, source: __j.active()?.dataset?.source || null })`);
            check(row.test === "list-row" && row.source === `0.0.${at}`, `after moving a card in the list focus is on ${JSON.stringify(row)}, not its row`);
          }
          await r.waitSaved("after the moves in the list");
          await r.key("Escape");
          await r.waitFor(`!__j.designer().shadowRoot.querySelector(".root.drawer-open")`, "Escape to close the card list");
          await lastDrawnCardGone(r, async () => {
            await sizeTo(r, 1280, 800);
            await dock(r, true);
            await r.waitFor(`__j.designer().shadowRoot.querySelector(".root.medium")`, "the medium layout for the real dashboard");
          }, "at 1024 px");
          // With a pager, a failed picture and "Cards" together the status
          // strip stays one line of 40 px, at 1024 and at 900 px.
          await r.eval(`__apolloMockHass.addDashboard("spill-1", "Spill", ${JSON.stringify(SPILL_CONFIG)});
            __apolloOpenPanel("/edit/spill-1"); true`);
          for (const [width, docked] of [
            [1280, true],
            [900, false],
          ]) {
            await sizeTo(r, width, 800);
            await dock(r, docked);
            const when = docked ? "at 1024 px" : "at 900 px";
            await r.waitFor(`__j.designer().shadowRoot.querySelector(".root.medium") && __j.find('[data-test="screen-next"]')`, `the pager ${when}`);
            await r.eval(`__apolloMockHass.failCalls("apollo_tab/layout/preview", 100); __j.designer()._requestPreview(); true`);
            try {
              await r.waitFor(`__j.find(".status-strip .alert")`, `the failed picture ${when}`);
              const strip = await r.eval(`(() => { const d = __j.designer().shadowRoot; const cards = __j.find('[data-test="open-cards"]');
                const words = cards.querySelector("span"); const line = parseFloat(getComputedStyle(words).lineHeight);
                const sentence = d.querySelector(".status-strip .alert > span");
                return { strip: d.querySelector(".status-strip").getBoundingClientRect().height,
                  cards: cards.getBoundingClientRect().height, words: words.getBoundingClientRect().height, line,
                  sentence: [sentence.scrollWidth, sentence.clientWidth],
                  pager: d.querySelector(".status-strip .screens-brief")?.getClientRects().length > 0 }; })()`);
              check(Math.round(strip.strip) === 40, `${when} the status strip is ${strip.strip} px high`);
              check(strip.cards <= 40.5 && strip.words < strip.line * 1.5, `${when} "Cards" is not one line: ${JSON.stringify(strip)}`);
              // The pager gives way to the failure: "1 / 2", so the failure's
              // sentence is whole.
              check(strip.pager && strip.sentence[0] <= strip.sentence[1] + 1, `${when} the failure's sentence is cut: ${JSON.stringify(strip)}`);
              await checkNoSidewaysScroll(r, width);
            } finally {
              await r.eval(`__apolloMockHass.failCalls("apollo_tab/layout/preview", 0); __j.designer()._requestPreview(); true`);
            }
            await r.waitFor(`!__j.find(".status-strip .alert")`, `the picture back ${when}`);
          }
        } finally {
          await dock(r, false);
          await r.viewport();
        }
        return shot;
      },
      { desktopOnly: true },
    ),
    step(
      "122",
      "compact-picture",
      async (r) => {
        try {
          await oneCard(r);
          await sizeTo(r, 820, 800);
          await r.waitFor(`__j.designer().shadowRoot.querySelector(".root.compact")`, "the compact layout");
          await pictureIs(r, 784, "at 820 x 800");
          await checkNoSidewaysScroll(r, 820);
          return await r.screen("122-compact-picture");
        } finally {
          await r.viewport();
        }
      },
      { desktopOnly: true },
    ),
    step(
      "123",
      "edit-mode",
      async (r) => {
        await openSample(r);
        const start = await shell(r);
        check(start.stage.top <= 180, `the picture starts at ${start.stage.top}`);
        await selectRow(r, "0.1.0");
        const layer = await r.eval(`(() => { const side = __j.find('[data-test="side"][data-mode="edit"]'); if (!side) return null;
          const rect = side.getBoundingClientRect(); const strip = __j.find('[data-test="edit-preview"]').getBoundingClientRect();
          const header = __j.designer().shadowRoot.querySelector(".ed-header").getBoundingClientRect();
          return { top: rect.top, bottom: rect.bottom, header: header.bottom, strip: strip.height, height: innerHeight }; })()`);
        check(layer, "no edit mode");
        check(Math.abs(layer.top - layer.header) <= 1 && Math.abs(layer.bottom - layer.height) <= 1, `the edit mode spans ${layer.top}..${layer.bottom}: ${JSON.stringify(layer)}`);
        check(layer.strip >= 128 && layer.strip <= 240, `the edit mode's picture is ${layer.strip} px high`);
        await checkSelectedCardVisible(r, "in the edit mode");
        const shot = await r.screen("123-edit-mode");
        const width = async () => (await r.draft()).views[0].sections[1].cards[0].grid_options?.columns;
        const before = await width();
        await r.tap('[data-test="wider"]');
        await r.waitFor(`__j.designer()._history.past.length > 0`, "Wider to change the card");
        await sleep(300);
        await checkSelectedCardVisible(r, "after Wider");
        await r.eval(`(() => { const form = __j.find(".edit-form"); form.scrollTop = form.scrollHeight; return true; })()`);
        await sleep(300);
        await checkSelectedCardVisible(r, "with the form scrolled to its end");
        await r.click('[data-test="undo"]');
        await r.waitFor(`__j.designer()._history.past.length === 0`, "Undo in the top bar");
        check((await width()) === before, "Undo in the top bar did not undo Wider");
        await r.key("Escape");
        await r.waitFor(`!__j.find('[data-test="side"][data-mode="edit"]')`, "Escape to close the edit mode");
        await r.click('[data-test="list-row"][data-source="0.1.0"]');
        await r.waitFor(`__j.find('[data-test="side"][data-mode="edit"]')`, "the edit mode again");
        await r.click('[data-test="close-panel"]');
        await r.waitFor(`!__j.find('[data-test="side"][data-mode="edit"]')`, "Done to close the edit mode");
        await r.waitFor(`__j.active()?.dataset?.focus === "row:0.1.0"`, "focus on the card's row after Done");
        // The same row pressed where it is, just above the window's bottom
        // edge: after Done the page column has not moved.
        await r.eval(`(() => { const main = __j.find(".main"); const row = __j.find('[data-test="list-row"][data-source="0.1.0"]');
          main.scrollTop += row.getBoundingClientRect().bottom - (innerHeight - 8); return true; })()`);
        await sleep(300);
        const low = await r.eval(`__j.find(".main").scrollTop`);
        await r.tap('[data-test="list-row"][data-source="0.1.0"]');
        await r.waitFor(`__j.find('[data-test="side"][data-mode="edit"]')`, "the edit mode from a row at the bottom edge");
        await r.tap('[data-test="close-panel"]');
        await r.waitFor(`!__j.find('[data-test="side"][data-mode="edit"]')`, "Done after a row at the bottom edge");
        await sleep(300);
        const kept = await r.eval(`({ scroll: __j.find(".main").scrollTop, focus: __j.active()?.dataset?.focus })`);
        check(Math.abs(kept.scroll - low) <= 1, `after Done the page column moved from ${low} to ${kept.scroll}`);
        check(kept.focus === "row:0.1.0", `after Done focus is on ${kept.focus}, not the card's row`);
        // A card pressed on the picture whose row is below the fold: after
        // Done the picture is where it was and the card has focus.
        // Focus leaves the row first: a redraw gives focus back to it, which
        // would scroll the row into view again.
        await r.eval(`(() => { __j.active()?.blur(); __j.find(".main").scrollTop = 0; return true; })()`);
        await sleep(600);
        const last = await r.eval(`(() => { const rows = [...__j.designer().shadowRoot.querySelectorAll('[data-test="list-row"]')];
          const row = rows[rows.length - 1]; return { source: row.dataset.source, top: row.getBoundingClientRect().top,
          picture: __j.find('[data-test="canvas"]').getBoundingClientRect().top, height: innerHeight }; })()`);
        check(last.top > last.height, `the last card's row is in view at ${last.top}, so the check below means nothing`);
        await r.tap(`[data-test="hit"][data-source="${last.source}"]`);
        await r.waitFor(`__j.find('[data-test="side"][data-mode="edit"]')`, "the edit mode from the picture");
        await r.tap('[data-test="close-panel"]');
        await r.waitFor(`!__j.find('[data-test="side"][data-mode="edit"]')`, "Done after a card pressed on the picture");
        await sleep(300);
        const after = await r.eval(`({ picture: __j.find('[data-test="canvas"]').getBoundingClientRect().top, focus: __j.active()?.dataset?.focus })`);
        check(Math.abs(after.picture - last.picture) <= 1, `after Done the picture's top moved from ${last.picture} to ${after.picture}`);
        check(after.focus === `hit:${last.source}`, `after Done focus is on ${after.focus}, not the card on the picture`);
        // Where the picture is and what has focus; null when focus fell to
        // the page.
        const place = () =>
          r.eval(`(() => { const active = __j.active();
            return { picture: __j.find('[data-test="canvas"]').getBoundingClientRect().top,
              focus: active && active !== document.body ? active.dataset.focus || active.dataset.test || active.tagName : null }; })()`);
        const onPicture = (focus) => /^(hit:|add-card$|add-first-card$)/.test(focus || "");
        // Remove card in an edit mode opened from the picture, for a card
        // whose follower's row is below the fold: the picture stays where it
        // was, and focus goes on on the picture (the card that took its
        // place, or Add card), not to that row and not to the page.
        const gone = await r.eval(`(() => { const rows = [...__j.designer().shadowRoot.querySelectorAll('[data-test="list-row"]')];
          const hits = new Set(__j.all('[data-test="hit"]').map((hit) => hit.dataset.source));
          for (let index = rows.length - 2; index >= 0; index -= 1) {
            if (hits.has(rows[index].dataset.source) && rows[index + 1].getBoundingClientRect().top > innerHeight) {
              return { source: rows[index].dataset.source, rows: rows.length };
            }
          }
          return null; })()`);
        check(gone, "no card on the picture is followed by a row below the fold, so the check below means nothing");
        await r.tap(`[data-test="hit"][data-source="${gone.source}"]`);
        await r.waitFor(`__j.find('[data-test="side"][data-mode="edit"]')`, "the edit mode from the picture, to remove the card");
        await r.eval(`(() => { const form = __j.find(".edit-form"); form.scrollTop = form.scrollHeight; return true; })()`);
        await sleep(300);
        await r.tap('[data-test="remove-card"]');
        await r.waitFor(`!__j.find('[data-test="side"][data-mode="edit"]') && __j.find('[data-test="toast-undo"]')`, "the card to be removed");
        const removed = await place();
        check(Math.abs(removed.picture - last.picture) <= 1, `after Remove card the picture's top moved from ${last.picture} to ${removed.picture}`);
        check(onPicture(removed.focus), `after Remove card focus is on ${removed.focus}, not on the picture`);
        // The same once the picture was drawn again without the card.
        await r.waitSaved("after Remove card");
        await r.waitFor(`__j.designer().shadowRoot.querySelectorAll('[data-test="list-row"]').length === ${gone.rows - 1}`, "the list without the card");
        await sleep(500);
        const drawn = await place();
        check(Math.abs(drawn.picture - last.picture) <= 1, `once the picture was drawn again its top moved from ${last.picture} to ${drawn.picture}`);
        check(onPicture(drawn.focus), `once the picture was drawn again focus is on ${drawn.focus}, not on the picture`);
        await r.screen("123-edit-mode-removed");
        // Add card with the floating button, then Done: the picture is
        // where it was, with focus on the new card there, not at the end of
        // the list.
        await r.eval(`(() => { __j.active()?.blur(); __j.find(".main").scrollTop = 0; return true; })()`);
        await sleep(300);
        const fresh = await place();
        await r.addCard("add-card", "apollo/light", "light.kitchen");
        await r.waitFor(`__j.find('[data-test="side"][data-mode="edit"]')`, "the edit mode for the new card");
        await r.waitSaved("the new card");
        const added = await r.eval(`__j.designer()._selected.join(".")`);
        await r.waitFor(`__j.designer().shadowRoot.querySelector('[data-test="hit"][data-source="${added}"]')`, "the new card on the picture");
        await r.tap('[data-test="close-panel"]');
        await r.waitFor(`!__j.find('[data-test="side"][data-mode="edit"]')`, "Done after Add card");
        await sleep(300);
        const done = await place();
        check(Math.abs(done.picture - fresh.picture) <= 1, `after Add card and Done the picture's top moved from ${fresh.picture} to ${done.picture}`);
        check(done.focus === `hit:${added}`, `after Add card and Done focus is on ${done.focus}, not the new card on the picture`);
        await lastDrawnCardGone(r, async () => {}, "on a phone");
        return shot;
      },
      { phoneOnly: true },
    ),
    step(
      "124",
      "short-screens",
      async (r) => {
        let shot = null;
        try {
          await oneCard(r);
          for (const [width, height, picture, tall] of [
            [844, 390, 412, 258],
            [640, 400, 324, 202],
          ]) {
            await sizeTo(r, width, height, width === 844);
            const when = `at ${width} x ${height}`;
            await r.waitFor(`__j.designer().shadowRoot.querySelector(".root.short")`, `the short layout ${when}`);
            await pictureIs(r, picture, when);
            const now = await shell(r);
            check(Math.abs(now.stage.height - tall) <= 1, `${when} the picture is ${now.stage.height} px high`);
            check(now.stage.left >= 0 && now.stage.top >= 0 && now.stage.right <= now.innerWidth && now.stage.bottom <= now.innerHeight, `${when} the picture is not wholly in the window: ${JSON.stringify(now.stage)}`);
            check(now.side.width >= 280 && Math.min(now.side.bottom, now.innerHeight) - now.side.top >= 250, `${when} the inspector is ${JSON.stringify(now.side)}`);
            check(Math.round(now.header.height) === 48 && Math.round(now.strip.height) === 48, `${when} the bars are ${now.header.height} and ${now.strip.height} px high`);
            await checkNoSidewaysScroll(r, width);
            if (width === 844) {
              await r.eval(UI);
              const small = await r.eval(`__ui.controls().filter((control) => control.height < 43.5)`);
              const inBars = await r.eval(`(() => { const d = __j.designer().shadowRoot;
                return [...d.querySelectorAll(".ed-header button, .tab-strip button")].filter((node) => node.getClientRects().length)
                  .map((node) => [__j.describe(node), node.getBoundingClientRect().height]).filter(([, h]) => h < 43.5); })()`);
              check(inBars.length === 0, `${when} controls in the bars under 44 px: ${JSON.stringify(inBars)} (${JSON.stringify(small.slice(0, 3))})`);
              shot = await r.screen("124-short-screens");
            }
          }
          // The layout holds while a text field has focus.
          await sizeTo(r, 1280, 800);
          await r.waitFor(`__j.designer().shadowRoot.querySelector(".root.wide")`, "the wide layout");
          await r.click('[data-test="hit"]');
          await r.waitFor(`__j.find('[data-test="form-name"]')`, "the card's form");
          await r.eval(`__j.find('[data-test="form-name"]').focus(); true`);
          await sizeTo(r, 1280, 500);
          await sleep(300);
          check(await r.eval(`Boolean(__j.designer().shadowRoot.querySelector(".root.wide"))`), "the layout changed while the name field had focus");
          await r.eval(`__j.active().blur(); true`);
          await r.waitFor(`__j.designer().shadowRoot.querySelector(".root.short")`, "the short layout once the field lost focus");
          // The keyboard changes only the height: a change of width is
          // followed at once, also with a text field in focus.
          await sizeTo(r, 1280, 800);
          await r.waitFor(`__j.designer().shadowRoot.querySelector(".root.wide")`, "the wide layout again");
          if (!(await r.count('[data-test="form-name"]'))) {
            await r.click('[data-test="hit"]');
          }
          await r.waitFor(`__j.find('[data-test="form-name"]')`, "the card's form again");
          await r.eval(`__j.find('[data-test="form-name"]').focus(); true`);
          await sizeTo(r, 1000, 800);
          await r.waitFor(`__j.designer().shadowRoot.querySelector(".root.medium")`, "the medium layout when the width changed with the name field in focus");
        } finally {
          await r.viewport();
        }
        return shot;
      },
      { desktopOnly: true },
    ),
    step(
      "125",
      "zoom",
      async (r) => {
        await oneCard(r);
        await pictureIs(r, 879, "at the start");
        const caption = await r.text(".zoom-caption");
        check(caption === "1280 x 800 · 69 %", `the caption reads "${caption}"`);
        await r.click('[data-test="hit"]');
        await r.waitFor(`__j.find('[data-test="hit"][aria-pressed="true"]')`, "the card to be selected");
        await r.click('[data-test="zoom-100"]');
        await pictureIs(r, 1280, "at 100 %");
        const seen = await r.eval(`(() => { const area = __j.designer().shadowRoot.querySelector(".stage-area").getBoundingClientRect();
          const hit = __j.find('[data-test="hit"][aria-pressed="true"]').getBoundingClientRect();
          return hit.left >= area.left && hit.top >= area.top && hit.right <= area.right && hit.bottom <= area.bottom; })()`);
        check(seen, "at 100 % the selected card is not in view");
        const shot = await r.screen("125-zoom");
        await r.click('[data-test="zoom-fit"]');
        await pictureIs(r, 879, "after Fit");
        return shot;
      },
      { desktopOnly: true },
    ),
    step("126", "toast-home", async (r) => {
      const phone = r.setup.device === "phone";
      await openSample(r);
      await selectRow(r, "0.1.1");
      await r.click('[data-test="remove-card"]');
      await r.waitFor(`__j.find('[data-test="toast-undo"]')`, "the removal's toast");
      await sleep(300);
      await checkToastHome(r, "after a card was removed", phone ? "fab" : "stage");
      const shot = await r.screen("126-toast-home");
      await selectRow(r, "0.1.0");
      await r.waitFor(`__j.find('[data-test="move-page"]')`, "Move to page");
      await r.eval(`(() => { const field = __j.find('[data-test="move-page"]'); field.value = "new";
        field.dispatchEvent(new Event("change")); return true; })()`);
      await r.tap('[data-test="move-page-go"]');
      await r.waitFor(`__j.text('[data-test="toast"] span').startsWith("Moved to")`, "the toast saying where the card went");
      await sleep(300);
      await checkToastHome(r, "after Move to page", phone ? "edit" : "stage");
      await r.screen("126-toast-home-edit");
      return shot;
    }),
  ];

  // Layout version 2 as the tablet draws it: the contract's kit page by
  // page, and schema 2 cards in a browser with their own tap and hold.
  const card2 = (component, variant) =>
    `document.querySelector('apollo-tab-card[data-component="${component}"][data-variant="${variant}"]')`;
  const openView = async (r, params, ready) => {
    const query = new URLSearchParams({ ha: r.setup.ha, ...params });
    await r.browser.send("Page.navigate", { url: `${r.browser.base}/tests/harness/index.html?${query}` });
    await r.waitFor(`document.readyState === "complete" && (${ready})`, `the ${params.view} view`);
  };
  const drawing = [
    step("204", "kit-pages", async (r) => {
      let first = null;
      const pages = [];
      for (let page = 0; page < 5; page += 1) {
        await openView(r, { view: "kit", page: String(page) }, `document.querySelector('[data-test="kit-page"][data-ready="1"]')`);
        pages.push(await r.eval(`(() => {
          const host = document.querySelector('[data-test="kit-page"]');
          const wall = host.querySelector(".at-page");
          return {
            nav: host.querySelectorAll(".at-nav-button").length,
            back: host.querySelectorAll(".at-nav-button.back").length,
            wall: wall.style.getPropertyValue("--at-wall"),
            cards: host.querySelectorAll(".at-card").length,
            lit: host.querySelectorAll(".at-card.is-on, .at-card.is-lit, .at-card.is-outline").length,
          };
        })()`));
        const shot = await r.screen(`204-kit-page${page}`);
        first ||= shot;
      }
      // The detail page's entry is not drawn on the other pages.
      check(pages[0].nav === 3 && pages[0].back === 0, `page 0 has ${pages[0].nav} side bar entries`);
      // Detail pages draw only the back entry.
      check(pages[3].nav === 1 && pages[3].back === 1, "the detail page does not show one back entry");
      check(pages[4].nav === 1 && pages[4].back === 1, "the second detail page does not show one back entry");
      // The climate page has a theme of its own.
      check(pages[1].wall && pages[1].wall !== pages[0].wall, "the climate page does not use its own theme");
      check(pages[0].cards > 0 && pages[0].lit > 0, "the kit page shows no lit card");
      return first;
    }, { desktopOnly: true }),
    step("205", "cards-v2-in-browser", async (r) => {
      await openView(r, { view: "cards2" }, `${card2("apollo/light", "tile")}?.shadowRoot?.querySelector(".at-card .at-slider")`);
      await sleep(200);
      const look = await r.eval(`(() => {
        const root = ${card2("apollo/light", "tile")}.shadowRoot;
        const card = root.querySelector(".at-card");
        return {
          on: card.classList.contains("is-on"),
          tint: card.style.getPropertyValue("--at-onbg"),
          bar: Boolean(root.querySelector(".at-slider.bar")),
          error: Boolean(root.querySelector(".status")),
        };
      })()`);
      check(!look.error, "the light card shows an error in a browser");
      check(look.on && look.tint && look.bar, `the light card is not drawn as layout version 2 (${JSON.stringify(look)})`);
      const errors = await r.eval(`[...document.querySelectorAll('apollo-tab-card')].filter((card) => card.shadowRoot.querySelector(".status")).map((card) => card.dataset.component + " " + card.dataset.variant)`);
      check(errors.length === 0, `cards show an error: ${errors.join(", ")}`);
      const shot = await r.shot("205-cards-v2");

      // A tap on the card's name is the card's: widget -1.
      const spot = await r.eval(`(() => {
        const host = ${card2("apollo/light", "tile")};
        host.scrollIntoView({ block: "center" });
        const label = host.shadowRoot.querySelector(".at-label");
        const box = label.getBoundingClientRect();
        return { x: box.left + 8, y: box.top + box.height / 2 };
      })()`);
      const before = (await r.calls("apollo_tab/card/call")).length;
      await r.clickAt(spot.x, spot.y);
      await r.waitFor(`__apolloMockHass.calls.filter((call) => call.type === "apollo_tab/card/call").length > ${before}`, "the card's tap");
      const [tap] = (await r.calls("apollo_tab/card/call")).slice(before);
      check(tap.widget === -1 && tap.event === "tap", `the tap went to widget ${tap.widget}`);

      // A hold opens its controls in a dialog.
      await r.browser.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: spot.x, y: spot.y });
      await r.browser.send("Input.dispatchMouseEvent", { type: "mousePressed", x: spot.x, y: spot.y, button: "left", buttons: 1, clickCount: 1 });
      await sleep(650);
      await r.browser.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: spot.x, y: spot.y, button: "left", buttons: 0, clickCount: 1 });
      await r.waitFor(`document.querySelector('[role="dialog"] apollo-tab-card')?.shadowRoot?.querySelector(".at-card")`, "the detail dialog");
      check((await r.calls("apollo_tab/card/call")).length === before + 1, "the hold also sent a tap");
      const detail = await r.eval(`(() => {
        const card = document.querySelector('[role="dialog"] apollo-tab-card');
        return { sliders: card.shadowRoot.querySelectorAll(".at-slider").length, error: Boolean(card.shadowRoot.querySelector(".status")) };
      })()`);
      check(!detail.error && detail.sliders >= 2, `the detail dialog does not show the light's controls (${JSON.stringify(detail)})`);
      // The dialog has its title and close button inside its frame, stays
      // within the window, and leaves no empty band above the controls.
      const frame = await r.eval(`(() => {
        const box = document.querySelector('[role="dialog"]');
        const close = box.querySelector("button");
        const card = box.querySelector("apollo-tab-card");
        const b = box.getBoundingClientRect();
        const c = close.getBoundingClientRect();
        const header = card.shadowRoot.querySelector(".at-header, .at-label");
        const first = [...card.shadowRoot.querySelectorAll(".at-slider")].map((el) => el.getBoundingClientRect().top).sort((x, y) => x - y)[0];
        return {
          title: box.querySelector("h2")?.textContent || "",
          label: box.getAttribute("aria-labelledby") === box.querySelector("h2")?.id,
          closeInside: c.top >= b.top && c.right <= b.right && c.bottom <= b.bottom,
          inWindow: b.top >= 0 && b.bottom <= innerHeight && b.left >= 0 && b.right <= innerWidth,
          band: first - header.getBoundingClientRect().bottom,
          scale: card.getBoundingClientRect().width / 568,
        };
      })()`);
      check(frame.title && frame.label, `the detail dialog has no title (${JSON.stringify(frame)})`);
      check(frame.closeInside, "the dialog's close button is outside its frame");
      check(frame.inWindow, `the detail dialog does not fit the window (${JSON.stringify(frame)})`);
      check(frame.band < 120 * frame.scale, `the detail dialog leaves an empty band above its controls (${JSON.stringify(frame)})`);
      await r.screen("205-detail-dialog");
      await r.key("Escape");
      await r.waitFor(`!document.querySelector('[role="dialog"]')`, "the dialog to close");

      // From the keyboard: Enter taps the card, the menu key opens its
      // controls, and Escape brings the focus back to the card.
      await r.eval(`${card2("apollo/light", "tile")}.shadowRoot.querySelector(".at-card").focus()`);
      const role = await r.eval(`(() => {
        const card = ${card2("apollo/light", "tile")}.shadowRoot.querySelector(".at-card");
        return { role: card.getAttribute("role"), name: card.getAttribute("aria-label"), focused: card.matches(":focus") };
      })()`);
      check(role.role === "button" && role.name && role.focused, `the card cannot take the keyboard's focus (${JSON.stringify(role)})`);
      const keyed = (await r.calls("apollo_tab/card/call")).length;
      await r.key("Enter");
      await r.waitFor(`__apolloMockHass.calls.filter((call) => call.type === "apollo_tab/card/call").length > ${keyed}`, "the card's tap from the keyboard");
      const [enter] = (await r.calls("apollo_tab/card/call")).slice(keyed);
      check(enter.widget === -1 && enter.event === "tap", `Enter went to widget ${enter.widget}`);
      await r.key("ContextMenu");
      await r.waitFor(`document.querySelector('[role="dialog"] apollo-tab-card')?.shadowRoot?.querySelector(".at-card")`, "the detail dialog from the keyboard");
      await r.key("Escape");
      await r.waitFor(`!document.querySelector('[role="dialog"]')`, "the dialog to close");
      const back = await r.eval(`${card2("apollo/light", "tile")}.shadowRoot.querySelector(".at-card").matches(":focus")`);
      check(back, "the focus does not go back to the card when its dialog closes");
      return shot;
    }),
  ];

  // The form of a schema 2 card (cards spec C.7, package I8): the Light card
  // for a colour lamp and for an on/off lamp, and an older light card that
  // is offered the new card.
  const optionRows = (r) =>
    r.eval(`__j.all('[data-test="option-row"]').filter((row) => __j.visible(row)).map((row) => ({
      option: row.dataset.option,
      usable: row.dataset.usable === "true",
      text: row.innerText.replace(/\\s+/g, " ").trim(),
    }))`);
  // The selected card on the picture: its width and its sliders.
  const lightPicture = (r) =>
    r.eval(`(() => {
      const designer = __j.designer();
      const root = designer.shadowRoot.querySelector(".page-host").shadowRoot;
      const card = root.querySelector(".at-card");
      if (!card) return null;
      const sliders = [...card.querySelectorAll(".at-slider")];
      return {
        w: card.getBoundingClientRect().width,
        sliders: sliders.length,
        tracked: sliders.filter((slider) => slider.classList.contains("tracked")).length,
        heights: sliders.map((slider) => slider.getBoundingClientRect().height),
      };
    })()`);
  const savedCard = async (r) => (await r.config()).views[0].sections[0].cards[0];
  const pickChoice = (r, option, value) =>
    r.eval(`(() => { const field = __j.find('select[data-focus="option:${option}"]');
      field.value = ${JSON.stringify(value)}; field.dispatchEvent(new Event("change", { bubbles: true })); return true; })()`);
  const newLight = async (r, entity) => {
    await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
    await r.click('[data-test="create"]');
    await r.waitFor(`__j.find('[data-test="add-first-card"]')`, "the new dashboard's empty editor");
    await r.click('[data-test="add-first-card"]');
    await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
    check((await r.count('[data-test="tile"][data-component="apollo/light-tile"]')) === 0, "the picker offers the older light tile");
    // One device field: the card is added the moment the lamp is chosen.
    await r.click('[data-test="tile"][data-component="apollo/light"]');
    await r.waitFor(`__j.find('[data-test="entity"][data-entity="${entity}"]')`, `the ${entity} option`);
    await r.click(`[data-test="entity"][data-entity="${entity}"]`);
    await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
    await r.waitFor(`__j.find('[data-test="option-row"][data-option="show_brightness"]')`, "the Light card's own rows");
    await r.waitSaved("the light added");
  };
  const cardForms = [
    step("206", "light-form-colour-lamp", async (r) => {
      await newLight(r, "light.kitchen");
      await r.waitFor(`__j.find('[data-test="option-row"][data-option="effects_shown"] input')`, "the lamp's effects");
      const rows = await optionRows(r);
      check(
        stable(rows.map((row) => row.option)) ===
          stable(["show_brightness", "bar_on_tile", "colour_control", "show_saturation", "show_white", "effects_shown"]),
        `the form shows ${rows.map((row) => row.option)}`,
      );
      check(rows.every((row) => row.usable), `a row is greyed for a lamp that can do everything: ${JSON.stringify(rows)}`);
      check((await r.count('[data-test="card-note"]')) === 0, "a note shows for a colour lamp");
      const effects = rows.find((row) => row.option === "effects_shown");
      check(effects.text.includes("Rainbow") && effects.text.includes("Storm") && effects.text.includes("4 chosen, up to 8."), `the effects read "${effects.text}"`);
      // The card's own rows straight after the device and Size, so what the
      // card can do is on the first screen; then name and icon, tap and hold.
      const parts = await r.eval(`[...__j.find('.card-form-2').querySelectorAll(":scope > .form-block > h3")].map((h) => h.textContent)`);
      check(
        stable(parts) === stable(["What it controls", "Size", "On the card", "Name and icon", "Tap and hold", "Look", "Position"]),
        `the form's parts are ${parts}`,
      );
      // At a named size the steps wait behind Fine-tune, and the icon is one
      // line until Change is pressed.
      check((await r.count('[data-test="wider"]')) === 0 && (await r.count('[data-test="size-fine-tune"]')) === 1, "Width and Height show at a named size");
      check((await r.count('[data-test="card-icon"]')) === 0 && (await r.count('[data-test="icon-change"]')) === 1, "the icon grid shows before Change");
      const chips = await r.eval(`__j.all('[data-test="size-chip"]').map((chip) => [chip.dataset.variant, chip.querySelector("input").checked])`);
      check(stable(chips) === stable([["tile", true], ["wide", false], ["large", false]]), `the sizes read ${JSON.stringify(chips)}`);
      const tile = await lightPicture(r);
      check(tile && tile.sliders === 1, `the tile on the picture is ${JSON.stringify(tile)}`);
      // The picture of the form shows the card's own rows.
      await r.eval(`__j.find('[data-test="option-row"][data-option="show_brightness"]').scrollIntoView({ block: "start" }); true`);
      const shot = await r.shot("206-light-form");

      // A switch: no brightness bar on the small tile. It is saved and the
      // picture follows: the thin level line instead of the bar.
      await r.click('input[data-focus="option:bar_on_tile"]');
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").views[0].sections[0].cards[0].options?.bar_on_tile === false`, "the switch to be saved");
      await r.waitFor(
        `(() => { const root = __j.designer().shadowRoot.querySelector(".page-host").shadowRoot;
          const bar = root.querySelector(".at-card .at-slider");
          return bar && bar.getBoundingClientRect().height < ${tile.heights[0]} / 2; })()`,
        "the picture to show the level line",
      );
      // A choice: favourite colours as well. Their swatches show.
      await pickChoice(r, "colour_control", "both");
      await r.waitFor(`__j.find('[data-test="option-row"][data-option="favourites"]')`, "the favourite colours");
      check((await r.count('[data-test="option-row"][data-option="favourites"] [data-test="swatch"]')) === 8, "the favourites are not eight swatches");
      await r.waitSaved("the colour choice");
      check(stable((await savedCard(r)).options) === stable({ bar_on_tile: false, colour_control: "both" }), `the card's options are ${JSON.stringify((await savedCard(r)).options)}`);
      // A size: Wide. The card takes its size on the grid, and the picture
      // shows it twice as wide with one brightness bar; colour and white are
      // on the controls page.
      await r.click('[data-test="size-chip"][data-variant="wide"]');
      await r.waitFor(
        `(() => { const card = __apolloMockHass.getConfig("tab-1").views[0].sections[0].cards[0];
          return card.variant === "wide" && card.grid_options?.columns === 12 && card.grid_options?.rows === 3; })()`,
        "the size to be saved",
      );
      await r.waitFor(
        `(() => { const root = __j.designer().shadowRoot.querySelector(".page-host").shadowRoot;
          const card = root.querySelector(".at-card");
          return card && card.getBoundingClientRect().width > ${tile.w} * 1.8
            && card.querySelectorAll(".at-slider").length === 1 && !card.querySelector(".at-slider.tracked"); })()`,
        "the picture to show the wide card with its one brightness bar",
      );
      check((await r.eval(`__j.find('[data-test="size-chip"][data-variant="wide"] input').checked`)) === true, "Wide is not marked as the size");
      await r.waitSaved("the size");
      await r.eval(`__j.find('[data-test="card-lit"]').scrollIntoView({ block: "start" }); true`);
      await r.screen("206-light-form-wide");
      // One Undo takes the size back, and the picture with it.
      await leaveEditMode(r);
      await r.click('[data-test="undo"]');
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").views[0].sections[0].cards[0].variant === undefined`, "Undo to take the size back");
      await r.waitFor(
        `(() => { const root = __j.designer().shadowRoot.querySelector(".page-host").shadowRoot;
          const card = root.querySelector(".at-card");
          return card && card.getBoundingClientRect().width < ${tile.w} * 1.2; })()`,
        "the picture to show the tile again",
      );
      return shot;
    }),
    step("207", "light-form-onoff-lamp", async (r) => {
      await newLight(r, "light.living_room");
      await r.waitFor(`__j.find('[data-test="card-note"]')`, "the note about the lamp");
      check((await r.text('[data-test="card-note"]')) === "This light only turns on and off.", `the note reads "${await r.text('[data-test="card-note"]')}"`);
      const rows = await optionRows(r);
      const row = (name) => rows.find((entry) => entry.option === name);
      // What the lamp cannot do is drawn greyed with its reason, not hidden.
      for (const [name, reason] of [
        ["show_brightness", "This light cannot be dimmed"],
        ["colour_control", "This light has no colour"],
        ["show_white", "This light has one white only"],
        ["show_saturation", "This light has no colour"],
        ["effects_shown", "This light has no effects"],
      ]) {
        check(row(name) && !row(name).usable, `${name} is not greyed: ${JSON.stringify(row(name))}`);
        check(row(name).text.includes(reason), `${name} reads "${row(name)?.text}"`);
      }
      check(!row("bar_on_tile") && !row("favourites"), `rows that follow a greyed one are drawn: ${rows.map((entry) => entry.option)}`);
      const off = await r.eval(`(() => { const input = __j.find('input[data-focus="option:show_brightness"]'); return [input.disabled, input.checked]; })()`);
      check(stable(off) === stable([true, false]), `Brightness is ${JSON.stringify(off)}, not off and greyed`);
      // A greyed list shows a dash, not "Off" as if it had been chosen.
      const colourList = await r.eval(`(() => { const field = __j.find('select[data-focus="option:colour_control"]');
        return [field.disabled, field.options[field.selectedIndex]?.textContent]; })()`);
      check(stable(colourList) === stable([true, "\u2013"]), `the greyed colour list is ${JSON.stringify(colourList)}`);
      // The lamp has no colour to show on the card either.
      const tint = await r.eval(`(() => { const input = __j.find('input[data-test="card-tint"]');
        return [input.disabled, input.checked, input.closest(".option-row").innerText.includes("This device has no colour to show.")]; })()`);
      check(stable(tint) === stable([true, false, true]), `Show the device's colour is ${JSON.stringify(tint)}`);
      await r.eval(`__j.find('[data-test="option-row"][data-option="show_brightness"]').scrollIntoView({ block: "start" }); true`);
      const shot = await r.shot("207-light-form-onoff");
      // The tap row still works: it opens its controls now.
      await r.eval(`(() => { const field = __j.find('select[data-focus="card-tap"]');
        field.value = "detail"; field.dispatchEvent(new Event("change", { bubbles: true })); return true; })()`);
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").views[0].sections[0].cards[0].options?.tap === "detail"`, "the tap to be saved");
      await r.waitSaved("the tap");
      return shot;
    }),
    step("208", "older-card-swap", async (r) => {
      await openSample(r);
      await selectRow(r, "0.1.0");
      await r.waitFor(`__j.find('[data-test="newer-card"]')`, "the offer of the newer card");
      const offer = await r.text('[data-test="newer-card"]');
      check(offer.includes("A newer card does this: Light."), `the offer reads "${offer}"`);
      await r.click('[data-test="form-name"]');
      await r.type("Desk lamp");
      await r.waitSaved("the name");
      const before = (await r.config()).views[0].sections[1].cards[0];
      check(before.component === "apollo/light-tile" && before.title === "Desk lamp", `the card is ${JSON.stringify(before)}`);
      const shot = await r.shot("208-older-card");
      await r.click('[data-test="swap-card"]');
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").views[0].sections[1].cards[0].component === "apollo/light"`, "the swap to be saved");
      await r.waitSaved("the swap");
      const after = (await r.config()).views[0].sections[1].cards[0];
      check(
        stable(after) ===
          stable({
            type: "custom:apollo-tab-card",
            component: "apollo/light",
            params: before.params,
            title: "Desk lamp",
            variant: "tile",
            grid_options: { columns: 6, rows: 3 },
          }),
        `the new card is ${JSON.stringify(after)}`,
      );
      // The same card stays selected, now with the Light card's form.
      await r.waitFor(`__j.find('[data-test="option-row"][data-option="show_brightness"]')`, "the Light card's form");
      check((await r.count('[data-test="newer-card"]')) === 0, "the offer stays after the swap");
      check((await r.eval(`__j.designer()._selected.join(".")`)) === "0.1.0", "another card is selected after the swap");
      // One Undo brings the older card back.
      await leaveEditMode(r);
      await r.click('[data-test="undo"]');
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").views[0].sections[1].cards[0].component === "apollo/light-tile"`, "Undo to bring the older card back");
      return shot;
    }),
    step("209", "light-sizes-and-steps", async (r) => {
      // The picker's example of a card one row high fits its box.
      await r.open({ seed: "none" }, `${home} && __j.find('[data-test="create"]')`);
      await r.click('[data-test="create"]');
      await r.waitFor(`__j.find('[data-test="add-first-card"]')`, "the new dashboard's empty editor");
      await r.click('[data-test="add-first-card"]');
      await r.waitFor(`__j.find('dialog[data-test="picker"][open]')`, "the picker");
      const example = '[data-test="tile"][data-component="apollo/switch"] .tile-preview';
      await r.waitFor(`__j.find('${example} apollo-tab-card')?.shadowRoot?.querySelector(".at-card")`, "the Switch card's example");
      const fit = await r.eval(`(() => { const box = __j.find('${example}'); const card = box.querySelector("apollo-tab-card");
        return [Math.round(box.getBoundingClientRect().height), Math.round(card.getBoundingClientRect().height)]; })()`);
      check(fit[1] <= fit[0] + 1, `the Switch example is ${fit[1]} px high in a box of ${fit[0]} px`);
      await r.click('[data-test="tile"][data-component="apollo/light"]');
      await r.waitFor(`__j.find('[data-test="entity"][data-entity="light.kitchen"]')`, "the light.kitchen option");
      await r.click('[data-test="entity"][data-entity="light.kitchen"]');
      await r.waitFor(`!__j.find('dialog[data-test="picker"]')`, "the picker to close");
      await r.waitFor(`__j.find('[data-test="option-row"][data-option="show_brightness"]')`, "the Light card's own rows");
      await r.waitSaved("the light added");
      const tile = await lightPicture(r);
      const marked = () => r.eval(`__j.all('[data-test="size-chip"]').filter((chip) => chip.querySelector("input").checked).map((chip) => chip.dataset.variant)`);
      // Fine-tune opens Width and Height, with the focus on Wider.
      await r.click('[data-test="size-fine-tune"]');
      await r.waitFor(`__j.find('[data-test="wider"]')`, "the size steps");
      check((await focused(r)) === "wider", `after Fine-tune the focus is on ${await focused(r)}`);
      check((await r.count('[data-test="size-reset"]')) === 0, "Back is offered at the size marked");
      // Wider: the card shows the largest size that fits, and that size is
      // marked; the picture shows the wide card, with its one brightness bar.
      await r.click('[data-test="wider"]');
      await r.waitFor(
        `(() => { const card = __apolloMockHass.getConfig("tab-1").views[0].sections[0].cards[0];
          return card.grid_options?.columns === 12 && card.variant === undefined; })()`,
        "Wider to be saved",
      );
      await r.waitFor(
        `(() => { const card = __j.designer().shadowRoot.querySelector(".page-host").shadowRoot.querySelector(".at-card");
          return card && card.getBoundingClientRect().width > ${tile.w} * 1.8 && card.querySelector(".at-slider"); })()`,
        "the picture to show the wide card",
      );
      check(stable(await marked()) === stable(["wide"]), `after Wider the size marked is ${JSON.stringify(await marked())}`);
      await r.waitSaved("Wider");
      const shot = await r.shot("209-light-wider");
      // Taller, then Narrower: Large, then the tile in a taller box.
      await r.click('[data-test="taller"]');
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").views[0].sections[0].cards[0].grid_options?.rows === 6`, "Taller to be saved");
      check(stable(await marked()) === stable(["large"]), `after Taller the size marked is ${JSON.stringify(await marked())}`);
      await r.click('[data-test="narrower"]');
      await r.waitFor(`__apolloMockHass.getConfig("tab-1").views[0].sections[0].cards[0].grid_options?.columns === 6`, "Narrower to be saved");
      check(stable(await marked()) === stable(["tile"]), `after Narrower the size marked is ${JSON.stringify(await marked())}`);
      // 1 wide and 2 high is not the tile's own size, so Back is offered.
      check((await r.text('[data-test="size-reset"]')) === "Back to the Tile size", `Back reads "${await r.text('[data-test="size-reset"]')}"`);
      await r.waitSaved("Narrower");
      // A press on the marked size puts the card back to that size.
      await r.click('[data-test="size-chip"][data-variant="tile"]');
      await r.waitFor(
        `(() => { const card = __apolloMockHass.getConfig("tab-1").views[0].sections[0].cards[0];
          return card.variant === "tile" && card.grid_options?.columns === 6 && card.grid_options?.rows === 3; })()`,
        "the tile size to come back",
      );
      check(stable(await marked()) === stable(["tile"]), `after Tile the size marked is ${JSON.stringify(await marked())}`);
      await r.waitSaved("the tile size");
      return shot;
    }),
  ];

  return [
    first,
    real,
    advanced,
    keyboard,
    saving,
    selection,
    confirming,
    contrast,
    picking,
    midWidth,
    racing,
    yaml,
    picture,
    fields,
    following,
    locked,
    previews,
    focusing,
    menu,
    leaving,
    longNames,
    placeholders,
    newcomer,
    offline,
    removing,
    pageTab,
    replacing,
    kept,
    clearer,
    screens,
    undoFocus,
    several,
    toastLife,
    sheetFocus,
    notSaved,
    moving,
    narrowTabs,
    shortcuts,
    tabletsHome,
    tabletsEditor,
    tabletsNone,
    tabletsNoEngine,
    tabletsAll,
    tabletsPreview,
    starting,
    tabletsNew,
    tabletsPairAgain,
    tabletsNewGuards,
    tabletsTurnOn,
    foundation,
    workspace,
    drawing,
    cardForms,
  ];
}

async function runSetup(browser, setup, shotsDir, realConfig, steps = null) {
  const run = new Run(browser, setup, shotsDir);
  await run.viewport();
  const results = [];
  for (const chain of chains(realConfig)) {
    let failed = null;
    for (const { n, name, run: body, desktopOnly, phoneOnly } of chain) {
      if (desktopOnly && setup.device !== "desktop") continue;
      if (phoneOnly && setup.device === "desktop") continue;
      if (steps && !steps.includes(n)) continue;
      const result = { n, name, ok: false };
      if (failed) {
        result.error = `skipped because step ${failed} failed`;
        results.push(result);
        continue;
      }
      browser.errors.length = 0;
      try {
        const screenshot = await body(run);
        if (screenshot) result.screenshot = screenshot;
        await sleep(100);
        await checkNoSidewaysScroll(run);
        check(browser.errors.length === 0, browser.errors.join("; "));
        result.ok = true;
      } catch (error) {
        const pageErrors = browser.errors.length ? ` | page errors: ${browser.errors.join("; ")}` : "";
        result.error = error.message.includes(browser.errors[0] ?? "\0") ? error.message : error.message + pageErrors;
        failed = n;
        try {
          result.screenshot = await run.shot(`${n}-${name}-failed`);
        } catch {
          // A screenshot of the failure is a help, not a requirement.
        }
      }
      results.push(result);
      console.log(`${setup.name} ${n} ${name}: ${result.ok ? "ok" : `FAILED ${result.error}`}`);
    }
  }
  return { name: setup.name, steps: results };
}

async function main() {
  let options;
  try {
    options = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(error.message);
    process.exit(2);
  }
  if (!options.out) {
    console.error("--out is required");
    process.exit(2);
  }
  const outDir = realPath(options.out);
  if (isInside(outDir, fs.realpathSync(ROOT))) {
    console.error("--out must be outside the repository");
    process.exit(2);
  }
  const shotsDir = path.join(outDir, "shots");
  fs.mkdirSync(shotsDir, { recursive: true });
  const realConfig = JSON.parse(fs.readFileSync(path.join(ROOT, "tests/harness/real-dashboard.json"), "utf8"));

  const browser = new Browser(options, outDir);
  const report = { setups: [], ok: false };
  process.on("SIGINT", () => {
    browser.stop().then(() => process.exit(130));
  });
  try {
    await browser.start();
    // --only <set-up name> runs one set-up, which is quicker while debugging.
    for (const setup of SETUPS.filter((entry) => !options.only || entry.name === options.only)) {
      report.setups.push(await runSetup(browser, setup, shotsDir, realConfig, options.steps));
    }
    report.ok =
      report.setups.length > 0 &&
      report.setups.every((setup) => setup.steps.length > 0 && setup.steps.every((entry) => entry.ok));
  } catch (error) {
    report.error = error.message;
    console.error(error.message);
  } finally {
    await browser.stop();
    fs.writeFileSync(path.join(outDir, "report.json"), `${JSON.stringify(report, null, 2)}\n`);
  }
  console.log(report.ok ? "All steps passed." : "Some steps failed; see report.json.");
  process.exitCode = report.ok ? 0 : 1;
}

// Importing this file (to reuse the browser helpers) does not start a run.
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
