// The tablet's own screen, as the panel and the guides quote it. The words
// are the firmware's: the shared contract's screens.json (CONTRACT.md
// section 11), which TAB-1 checks against engine/tab_state.h. Every quote
// here that starts like one of them must be one of them, word for word, so
// the panel and the guides cannot keep words the tablet no longer shows.
import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const CONTRACT = path.join(root, "tests/contract");
const SCREENS = JSON.parse(fs.readFileSync(path.join(CONTRACT, "screens.json"), "utf8"));
const STRINGS = JSON.parse(fs.readFileSync(path.join(root, "custom_components/apollo_tab/library/strings.json"), "utf8"));

// TAB-1's copy of the contract: TAB1_DIR names the TAB-1 repository, else
// it is looked for next to this one (both in one ApolloAutomation folder).
const TAB1 = process.env.TAB1_DIR ? path.resolve(process.env.TAB1_DIR) : path.resolve(root, "../TAB-1");
const TAB1_CONTRACT = path.join(TAB1, "Integrations/ESPHome/engine_tests/contract");

// Each text the tablet shows: the waiting screen's headlines and steps and
// the Wi-Fi notes, with the hotspot's name put in. "{name}" stays: it is
// the tablet's name.
function screenTexts(screens) {
  const texts = [];
  const add = (where, text) => texts.push({ where, text: text.replaceAll("{hotspot}", screens.hotspot) });
  for (const [state, screen] of Object.entries(screens.waiting)) {
    for (const [field, text] of Object.entries(screen)) {
      if (field !== "when") add(`waiting.${state}.${field}`, text);
    }
  }
  for (const [kind, note] of Object.entries(screens.notes)) {
    add(`notes.${kind}.text`, note.text);
  }
  return texts;
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// The quotes in `text` that start like one of the tablet's texts (its
// first three words, after a straight or curly opening quote) but are not
// one of them, word for word, up to the closing quote. A quote may wrap
// over lines and sit in a block quote; quotes inside quotes are fine.
function wrongQuotes(text, texts) {
  const flat = text.replace(/^> ?/gm, "").replace(/\s+/g, " ");
  const whole = texts.map(({ text: words }) => new RegExp(`^${escapeRegExp(words).replaceAll("\\{name\\}", '[^"“”]+?')}["”]`));
  const starts = new Set(
    texts.map(({ text: words }) => words.split(" ").slice(0, 3).join(" ").replace(/\{name\}.*/, "").trim()).filter((start) => start.length >= 3),
  );
  const wrong = new Set();
  for (const start of starts) {
    for (const open of ['"', "“"]) {
      for (let at = flat.indexOf(open + start); at >= 0; at = flat.indexOf(open + start, at + 1)) {
        const rest = flat.slice(at + 1);
        if (!whole.some((pattern) => pattern.test(rest))) {
          wrong.add(rest.slice(0, 100).split(/["”]/)[0]);
        }
      }
    }
  }
  return [...wrong];
}

// Words the tablet showed in earlier rounds and shows no more.
const RETIRED = [
  "to give this tablet a dashboard",
  "pick a dashboard for this tablet",
  "from a phone to set up Wi-Fi",
  "Turn the tablet off and on to set up Wi-Fi",
  "On Wi-Fi, not turned on yet",
  "Find “Authentication expired” in Settings > System > Repairs and confirm it",
];

function guides() {
  const files = ["README.md", ...fs.readdirSync(path.join(root, "docs")).filter((name) => name.endsWith(".md")).map((name) => `docs/${name}`)];
  return files.map((file) => [file, fs.readFileSync(path.join(root, file), "utf8")]);
}

test("the contract has the screens the panel's lines check", () => {
  assert.equal(SCREENS.hotspot, "Apollo TAB1 Hotspot");
  for (const state of ["hotspot", "add", "erased", "turn_on", "wait_ha", "pick", "closed", "no_wifi"]) {
    const screen = SCREENS.waiting[state];
    assert.ok(screen && typeof screen.headline === "string" && typeof screen.step === "string", state);
  }
  // The erased screen names the same Repairs question as the panel's line.
  assert.ok(SCREENS.waiting.erased.step.includes("Authentication expired for {name}"), SCREENS.waiting.erased.step);
  assert.ok(STRINGS["tablets.reauth_erased"].includes('"Authentication expired for {name}"'));
  // Each headline once: the screen tells the states apart.
  const headlines = Object.values(SCREENS.waiting).map((screen) => screen.headline);
  assert.equal(new Set(headlines).size, headlines.length);
  // The panel names the hotspot as the tablet does.
  for (const key of ["tablets.none", "tablets.add_another", "tablets.offline_help"]) {
    assert.ok(STRINGS[key].includes(`"${SCREENS.hotspot}"`), key);
  }
});

// The contract is one folder in three places (TAB-1, this repository and
// the design notes). TAB-1's checks compare its copy with the firmware, so
// this copy has to be the same as TAB-1's, file for file.
test(
  "the contract is the same as TAB-1's copy",
  { skip: process.env.TAB1_DIR || fs.existsSync(TAB1_CONTRACT) ? false : `no TAB-1 repository at ${TAB1} (set TAB1_DIR)` },
  () => {
    assert.ok(fs.existsSync(TAB1_CONTRACT), `TAB1_DIR has no contract at ${TAB1_CONTRACT}`);
    const list = (dir, base = dir) =>
      fs
        .readdirSync(dir, { withFileTypes: true })
        .flatMap((entry) => (entry.isDirectory() ? list(path.join(dir, entry.name), base) : [path.relative(base, path.join(dir, entry.name))]))
        .filter((file) => file !== "ruff.toml" && !file.split(path.sep).includes("__pycache__"))
        .sort();
    const ours = list(CONTRACT);
    assert.deepEqual(ours, list(TAB1_CONTRACT));
    assert.ok(ours.includes("screens.json"));
    for (const file of ours) {
      assert.ok(fs.readFileSync(path.join(CONTRACT, file)).equals(fs.readFileSync(path.join(TAB1_CONTRACT, file))), `${file} differs from TAB-1's`);
    }
  },
);

test("every quote of the tablet's screen in the guides and the panel is the tablet's words", () => {
  const texts = screenTexts(SCREENS);
  for (const [file, text] of guides()) {
    assert.deepEqual(wrongQuotes(text, texts), [], `${file} quotes the tablet wrongly`);
    for (const words of RETIRED) {
      assert.ok(!text.replace(/^> ?/gm, "").replace(/\s+/g, " ").includes(words), `${file} still has "${words}"`);
    }
  }
  for (const [key, text] of Object.entries(STRINGS)) {
    assert.deepEqual(wrongQuotes(text, texts), [], key);
    for (const words of RETIRED) {
      assert.ok(!text.includes(words), `${key} still has "${words}"`);
    }
  }
});

// The screens docs/tablets.md must quote: what a new tablet says at each
// step, what an erased one says, and the step for nothing to show.
test("the tablets guide quotes the screens an admin meets", () => {
  const docs = fs.readFileSync(path.join(root, "docs/tablets.md"), "utf8").replace(/^> ?/gm, "").replace(/\s+/g, " ");
  const { hotspot, add, erased, turn_on: turnOn, wait_ha: waitHa, pick, closed } = SCREENS.waiting;
  for (const words of [
    hotspot.headline,
    add.headline,
    add.step,
    erased.headline,
    erased.step.replace("{name}", "Apollo TAB-1 ddee01"),
    erased.step2,
    turnOn.headline,
    turnOn.step,
    waitHa.headline,
    pick.step,
    closed.headline,
    closed.step,
    SCREENS.notes.hotspot.text.replace("{hotspot}", SCREENS.hotspot),
  ]) {
    assert.ok(docs.includes(`"${words}"`), `docs/tablets.md does not quote "${words}"`);
  }
  // The "Nothing to show yet" row gives the tablet's step.
  const row = fs
    .readFileSync(path.join(root, "docs/tablets.md"), "utf8")
    .split("\n")
    .find((line) => line.startsWith(`| ${pick.headline} |`));
  assert.ok(row && row.includes(`"${pick.step}"`), row);
});

// The check above, on made-up text: it finds a stale or cut quote, also
// across lines and in a block quote, and lets the tablet's words through.
test("a stale quote of the tablet is found", () => {
  const texts = screenTexts(SCREENS);
  const ok = [
    'It says "Add this tablet in Home Assistant".',
    '> Only if its screen says "Confirm this\n> tablet in Home Assistant": confirm',
    'with "In Settings > System > Repairs, confirm only “Authentication expired for Apollo TAB-1 ddee01”" under it',
    'a note, "No Wi-Fi. Join the Wi-Fi “Apollo TAB1 Hotspot” from a phone".',
    '"Setup not finished" and "Restart the tablet to finish setup"',
    '"Waiting for you in Repairs" and "Set up again" are the panel\'s',
  ];
  for (const text of ok) {
    assert.deepEqual(wrongQuotes(text, texts), [], text);
  }
  const wrong = [
    ['with "Open TAB-1 in Home Assistant to give this tablet a dashboard".', "Open TAB-1 in Home Assistant to give this tablet a dashboard"],
    ['says "Check that Home Assistant is running".', "Check that Home Assistant is running"],
    ['says "Add this tablet\n> in Home Assistant now".', "Add this tablet in Home Assistant now"],
    ["says “Ready to turn it on”.", "Ready to turn it on"],
    ['says "No Wi-Fi. Join the tablet\'s Wi-Fi".', "No Wi-Fi. Join the tablet's Wi-Fi"],
    ['says "In Settings > System > Repairs, confirm it".', "In Settings > System > Repairs, confirm it"],
  ];
  for (const [text, quote] of wrong) {
    assert.deepEqual(wrongQuotes(text, texts), [quote], text);
  }
});
