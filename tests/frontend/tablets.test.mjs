import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { fillWords, format } from "../../custom_components/apollo_tab/frontend/logic.js";
import * as tablets from "../../custom_components/apollo_tab/frontend/tablets.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const rawStrings = JSON.parse(fs.readFileSync(path.join(root, "custom_components/apollo_tab/library/strings.json"), "utf8"));
// As the panel loads them: with the word for turning a tablet on put in.
const strings = fillWords(rawStrings);
// The tablet's own words, from the shared contract (CONTRACT.md section 11;
// TAB-1 checks engine/tab_state.h against the same file).
const SCREENS = JSON.parse(fs.readFileSync(path.join(root, "tests/contract/screens.json"), "utf8"));

// The panel's t(), reading the real strings file; a missing key fails.
function t(key, vars) {
  assert.ok(Object.hasOwn(strings, key), `missing string ${key}`);
  return format(strings[key], vars);
}

function tablet(mac, name, changes = {}) {
  return {
    mac,
    device_id: `device-${mac}`,
    name,
    short_name: name.replace(/ tablet$/i, ""),
    model: "TAB-1",
    dashboard: "home",
    status: "on_tablet",
    reason: "",
    retry: false,
    engine: "0.1.0",
    paired: true,
    input: "ok",
    entity_id: `select.${name.toLowerCase().replaceAll(" ", "_")}_dashboard`,
    approved: true,
    suggested: null,
    ...changes,
  };
}

const KITCHEN = tablet("aa:bb:cc:00:00:01", "Kitchen tablet");
const HALLWAY = tablet("aa:bb:cc:00:00:02", "Hallway tablet", { dashboard: "night", status: "offline" });
const BEDROOM = tablet("aa:bb:cc:00:00:03", "Bedroom tablet", {
  status: "no_engine",
  engine: "",
  paired: false,
  input: "not_paired",
});
// A tablet nobody turned on yet: Home Assistant sends no dashboard, but
// what it showed before it was adopted again is the suggestion.
const PORCH = tablet("aa:bb:cc:00:00:04", "Porch tablet", {
  dashboard: null,
  status: "new",
  engine: "",
  paired: false,
  input: "not_paired",
  approved: false,
  suggested: "night",
});
const ROWS = [
  { url_path: "night", title: "Night" },
  { url_path: "home", title: "Home" },
];

// Design 6.1: the words on Home for every status and reason.
const HOME_TABLE = [
  [{ status: "new", approved: false, dashboard: null }, "Ready to turn on"],
  [{ status: "on_tablet" }, "On the tablet"],
  [{ status: "sending" }, "Sending…"],
  [{ status: "offline" }, "Offline"],
  [{ status: "offline", reauth: "erased", reauth_name: "Apollo TAB-1 ddee01" }, "Waiting for you in Repairs"],
  [{ status: "offline", reauth: "key", reauth_name: "Apollo TAB-1 ddee01" }, "Waiting for you in Repairs"],
  [{ status: "no_engine" }, "Needs a software update"],
  [{ status: "unsupported", reason: "tablet_old" }, "Needs newer tablet software"],
  [{ status: "unsupported", reason: "tablet_new" }, "Update Apollo TAB Dashboard in Home Assistant"],
  [{ status: "unsupported", reason: "ha_version" }, "Update Apollo TAB Dashboard in Home Assistant"],
  [{ status: "failed", reason: "timeout", retry: true }, "Could not send. Trying again."],
  [{ status: "failed", reason: "too_big", retry: false }, "This dashboard is too big for the tablet"],
  [{ status: "failed", reason: "limits", retry: false }, "This dashboard is too big for the tablet"],
  [{ status: "failed", reason: "unreadable", retry: false }, "This dashboard cannot be read"],
  [{ status: "failed", reason: "parse", retry: false }, "The tablet cannot show this dashboard"],
  [{ status: "failed", reason: "version", retry: false }, "The tablet cannot show this dashboard"],
  [{ status: "no_dashboard", dashboard: null }, "Nothing to show yet"],
];

test("Home has the design's words for every status and reason", () => {
  for (const [changes, words] of HOME_TABLE) {
    const key = tablets.homeWordsKey(tablet("m", "Kitchen tablet", changes));
    assert.equal(key && t(key), words, JSON.stringify(changes));
  }
});

// Design 5.6: the editor's line for every status and reason.
const LINE_TABLE = [
  [{ status: "on_tablet" }, "On Kitchen tablet"],
  [{ status: "sending" }, "Sending to Kitchen tablet…"],
  [{ status: "offline" }, "Kitchen tablet is offline"],
  [{ status: "offline", reauth: "erased", reauth_name: "Apollo TAB-1 ddee01" }, "Kitchen tablet is waiting for you in Repairs"],
  [{ status: "no_engine" }, "Kitchen tablet needs a software update"],
  [{ status: "unsupported", reason: "tablet_old" }, "Kitchen tablet needs newer tablet software"],
  [{ status: "unsupported", reason: "tablet_new" }, "Update Apollo TAB Dashboard in Home Assistant to use Kitchen tablet"],
  [{ status: "unsupported", reason: "ha_version" }, "Update Apollo TAB Dashboard in Home Assistant to use Kitchen tablet"],
  [{ status: "failed", reason: "build", retry: true }, "Could not send to Kitchen tablet. Trying again."],
  [{ status: "failed", reason: "too_big" }, "This dashboard is too big for Kitchen tablet"],
  [{ status: "failed", reason: "limits" }, "This dashboard is too big for Kitchen tablet"],
  [{ status: "failed", reason: "parse" }, "Kitchen tablet cannot show this dashboard"],
  [{ status: "failed", reason: "unreadable" }, "Kitchen tablet cannot show this dashboard"],
];

test("the editor has the design's line for every status and reason", () => {
  for (const [changes, line] of LINE_TABLE) {
    const key = tablets.lineWordsKey(tablet("m", "Kitchen tablet", changes));
    assert.equal(key && t(key, { tablet: "Kitchen tablet" }), line, JSON.stringify(changes));
  }
});

test("every status and every reason has words on Home and in the editor", () => {
  const cases = [];
  for (const status of tablets.TABLET_STATUSES) {
    const reasons = tablets.TABLET_REASONS[status] || [""];
    for (const reason of reasons) {
      for (const retry of [false, true]) {
        cases.push({ status, reason, retry });
      }
    }
  }
  assert.ok(cases.length > 40);
  for (const changes of cases) {
    const item = tablet("m", "Kitchen tablet", changes);
    const home = tablets.homeWordsKey(item);
    assert.ok(home && strings[home], `no words on Home for ${JSON.stringify(changes)}`);
    // No editor line: it has no dashboard, or (new) shows nothing.
    if (changes.status !== "no_dashboard" && changes.status !== "new") {
      const line = tablets.lineWordsKey(item);
      assert.ok(line && strings[line], `no editor line for ${JSON.stringify(changes)}`);
    }
  }
  // Every word key in the maps exists.
  for (const key of [...Object.values(tablets.HOME_WORDS), ...Object.values(tablets.LINE_WORDS)]) {
    assert.ok(key === null || Object.hasOwn(strings, key), key);
  }
});

test("a status from a newer Home Assistant side has no words, not wrong ones", () => {
  assert.equal(tablets.statusKind(tablet("m", "Kitchen tablet", { status: "teleporting" })), null);
  assert.equal(tablets.homeWordsKey({ mac: "m" }), null);
  assert.equal(tablets.lineWordsKey(null), null);
  assert.equal(tablets.statusTone({ status: "teleporting" }), "quiet");
});

test("tones mark what is fine, busy, quiet and a problem", () => {
  assert.equal(tablets.statusTone(KITCHEN), "ok");
  assert.equal(tablets.statusTone({ ...KITCHEN, status: "sending" }), "busy");
  assert.equal(tablets.statusTone(HALLWAY), "quiet");
  assert.equal(tablets.statusTone(BEDROOM), "quiet");
  assert.equal(tablets.statusTone({ ...KITCHEN, status: "failed", retry: true }), "problem");
  assert.equal(tablets.statusTone({ ...KITCHEN, status: "unsupported", reason: "tablet_old" }), "problem");
});

// Round 9: while Home Assistant waits for an admin's answer in Repairs, the
// row says so in a tone that stands out, not a grey "Offline". A new
// tablet stays new: its button is what turns it on.
test("a tablet that waits for an answer in Repairs stands out", () => {
  const erased = { ...HALLWAY, reauth: "erased", reauth_name: "Apollo TAB-1 ddee02" };
  for (const item of [erased, { ...erased, reauth: "key" }, { ...erased, status: "on_tablet" }]) {
    assert.equal(tablets.statusKind(item), "repairs", JSON.stringify(item));
    assert.equal(t(tablets.homeWordsKey(item)), "Waiting for you in Repairs");
    assert.equal(tablets.statusTone(item), "attention");
    assert.equal(tablets.offlineHelpKey(item), null);
  }
  for (const item of [{ ...erased, reauth: null, reauth_name: null }, { ...erased, reauth: "later" }, { ...erased, reauth_name: "" }]) {
    assert.equal(tablets.statusKind(item), "offline", JSON.stringify(item));
    assert.equal(tablets.statusTone(item), "quiet");
  }
  const waiting = { ...PORCH, reauth: "erased", reauth_name: "Porch" };
  assert.equal(tablets.statusKind(waiting), "new");
  assert.equal(tablets.statusTone(waiting), "new");
  assert.equal(tablets.repairsWait(erased), "erased");
  assert.equal(tablets.repairsWait({ ...erased, reauth: "key" }), "key");
  assert.equal(tablets.repairsWait(KITCHEN), null);
  assert.equal(tablets.repairsWait(null), null);
});

test("the Repairs status has its own amber band", async () => {
  const { panelStyles } = await import("../../custom_components/apollo_tab/frontend/styles.js");
  const rule = (selector) => {
    const start = panelStyles.indexOf(`${selector} {`);
    assert.ok(start >= 0, `no rule for ${selector}`);
    return panelStyles.slice(start, panelStyles.indexOf("}", start));
  };
  const band = rule('.tablet-status[data-tone="attention"]');
  assert.match(band, /border: 1px solid var\(--tab-warn-ink\);/);
  assert.match(band, /background: color-mix\(in srgb, var\(--tab-warn\) 12%, var\(--tab-surface\)\);/);
  assert.match(rule('.tablet-status[data-tone="attention"]::before'), /background: var\(--tab-warn-ink\);/);
  // No other status has a band.
  assert.equal((panelStyles.match(/\.tablet-status\[data-tone="[a-z]+"\] \{/g) || []).length, 1);
});

// Round 9: an offline row says what to check. Round 10: the panel names the
// way back itself. A tablet with a dashboard keeps showing it while Home
// Assistant cannot reach it, with a small mark and, only without Wi-Fi, a
// Wi-Fi note (TAB-1 firmware, screens.json "notes"), so "Its screen says
// what to do" was not true with Wi-Fi but without Home Assistant. Off and on, then the set-up hotspot from a phone,
// works for every tablet: the hotspot comes on after 90 s without Wi-Fi
// and stays for the 15 minutes after power-on.
test("an offline row says what to check", () => {
  assert.equal(tablets.offlineHelpKey(HALLWAY), "tablets.offline_help");
  assert.equal(
    t("tablets.offline_help"),
    'Check that the tablet has power and Wi-Fi. If your Wi-Fi changed, restart the tablet, then within 15 minutes join "Apollo TAB1 Hotspot" from a phone and pick your Wi-Fi.',
  );
  const help = strings["tablets.offline_help"];
  // The way back, in the order the tablet needs it, and the hotspot's name
  // as the other lines (and the tablet) give it.
  const at = ["power and Wi-Fi", "restart the tablet", "within 15 minutes", 'join "Apollo TAB1 Hotspot" from a phone', "pick your Wi-Fi"].map(
    (words) => help.indexOf(words),
  );
  assert.ok(at.every((index, i) => index >= 0 && (i === 0 || index > at[i - 1])), JSON.stringify(at));
  assert.ok(strings["tablets.add_another"].includes('join "Apollo TAB1 Hotspot" from a phone and pick your Wi-Fi'));
  // Nothing sends the admin to a screen that may show only the dashboard.
  assert.doesNotMatch(help, /screen says|its screen|says what to do/i);
  for (const item of [KITCHEN, BEDROOM, PORCH, { ...PORCH, status: "offline" }, { ...KITCHEN, status: "sending" }, null]) {
    assert.equal(tablets.offlineHelpKey(item), null, JSON.stringify(item));
  }
  const panel = fs.readFileSync(path.join(root, "custom_components/apollo_tab/frontend/panel.js"), "utf8");
  const fill = panel.slice(panel.indexOf("  _fillTabletRow(refs, tablet) {"), panel.indexOf("  _turnOnButton("));
  // The help goes into the row's "What to do" fold-out.
  assert.match(fill, /const offlineKey = offlineHelpKey\(tablet\);\n    if \(offlineKey\) \{\n      lines\.push\(\["help", t\(offlineKey\), "tablet-offline-help"\]\);/);
  assert.match(fill, /if \(className === "help"\) \{\n\s*return this\._whatToDo\(tablet\.mac, text, test\);/);
  const fold = panel.slice(panel.indexOf("  _whatToDo("), panel.indexOf("  _turnOnButton("));
  assert.match(fold, /el\("details", "what-to-do"\)/);
  assert.match(fold, /fold\.dataset\.test = "tablet-what-to-do";/);
  assert.doesNotMatch(fold, /screen-says/);
});

test("the note about taps shows only for a tablet that has the dashboard", () => {
  assert.equal(tablets.inputNoteKey({ ...KITCHEN, input: "needs_encryption" }), "tablets.needs_encryption");
  assert.equal(tablets.inputNoteKey({ ...KITCHEN, input: "not_paired" }), "tablets.not_paired");
  assert.equal(tablets.inputNoteKey({ ...KITCHEN, status: "sending", input: "not_paired" }), "tablets.not_paired");
  assert.equal(tablets.inputNoteKey(KITCHEN), null);
  // Waiting for the tablet software already says more.
  assert.equal(tablets.inputNoteKey(BEDROOM), null);
  assert.equal(tablets.inputNoteKey({ ...HALLWAY, input: "needs_encryption" }), null);
  assert.match(t("tablets.needs_encryption"), /not protected\. Switch on encryption for it in ESPHome\.$/);
  assert.match(t("tablets.not_paired"), /cannot control anything yet\. It is still being set up\.$/);
});

test("Set up again is offered only after set-up has not worked for a while", () => {
  const loft = { ...KITCHEN, paired: false, input: "not_paired" };
  const after = tablets.PAIR_AGAIN_AFTER_MS;
  // Home Assistant tries by itself once a minute, so it has tried by then.
  assert.ok(after > 60 * 1000);
  assert.equal(tablets.pairAgainIn(loft, 1000, 1000), after);
  assert.equal(tablets.pairAgainIn(loft, 1000, 1000 + after - 1), 1);
  assert.equal(tablets.pairAgainIn(loft, 1000, 1000 + after), 0);
  assert.equal(tablets.pairAgainIn({ ...loft, status: "failed", reason: "timeout" }, 0, after * 5), 0);
  // Set up, needing encryption, offline, without the software, or new:
  // there is nothing to set up again.
  for (const other of [
    KITCHEN,
    { ...loft, input: "needs_encryption" },
    { ...loft, status: "offline" },
    BEDROOM,
    PORCH,
    null,
  ]) {
    assert.equal(tablets.pairAgainIn(other, 0, after * 5), null, JSON.stringify(other));
  }
  assert.equal(tablets.pairAgainIn(loft, undefined, after), null);
  assert.equal(t("tablets.pair_again"), "Set up again");
  const notApproved = 'This tablet is new. Pick a dashboard for it under Tablets, then press "Turn on with this dashboard".';
  assert.equal(t("tablets.pair_failed", { message: notApproved }), `It could not be set up again: ${notApproved}`);
  assert.ok(t("tablets.pair_asked"));
});

test("tablets are listed by name, then by MAC", () => {
  const twin = tablet("aa:bb:cc:00:00:00", "kitchen tablet");
  const sorted = tablets.sortTablets([KITCHEN, HALLWAY, null, { name: "No mac" }, BEDROOM, twin]);
  assert.deepEqual(
    sorted.map((entry) => entry.mac),
    ["aa:bb:cc:00:00:03", "aa:bb:cc:00:00:02", "aa:bb:cc:00:00:00", "aa:bb:cc:00:00:01"],
  );
  assert.deepEqual(tablets.sortTablets(undefined), []);
});

test("Shown on names the tablets by their short name", () => {
  const list = [KITCHEN, HALLWAY, BEDROOM];
  assert.equal(tablets.shownOnText(list, "home", t), "On Bedroom, Kitchen");
  assert.equal(tablets.shownOnText(list, "night", t), "On Hallway");
  assert.equal(tablets.shownOnText(list, "other", t), "");
  // A tablet without a short name falls back to its name.
  assert.equal(tablets.shownOnText([{ ...KITCHEN, short_name: "" }], "home", t), "On Kitchen tablet");
});

test("names are joined with commas and a last and", () => {
  assert.equal(tablets.joinNames([], t), "");
  assert.equal(tablets.joinNames(["Kitchen tablet"], t), "Kitchen tablet");
  assert.equal(tablets.joinNames(["Kitchen tablet", "Bedroom tablet"], t), "Kitchen tablet and Bedroom tablet");
  assert.equal(tablets.joinNames(["A", "B", "C"], t), "A, B and C");
});

test("the Shows list holds every dashboard in the one order", () => {
  assert.deepEqual(tablets.showsOptions(ROWS, "home", t), [
    ["home", "Home", false],
    ["night", "Night", false],
  ]);
  // Nothing chosen yet: a first choice that cannot be picked.
  assert.deepEqual(tablets.showsOptions(ROWS, null, t)[0], ["", "Pick a dashboard", true]);
  // A dashboard this list does not hold, such as one that cannot be read.
  assert.deepEqual(tablets.showsOptions(ROWS, "broken", t)[0], ["broken", "broken", true]);
  assert.equal(tablets.showsOptions(ROWS, "broken", t).length, 3);
  // A dashboard that cannot be read right now keeps its name.
  const unreadable = [{ url_path: "broken", title: "Garage" }];
  assert.deepEqual(tablets.showsOptions(ROWS, "broken", t, unreadable)[0], [
    "broken",
    "Garage (cannot be read right now)",
    true,
  ]);
  assert.deepEqual(tablets.showsOptions(ROWS, "home", t, unreadable), tablets.showsOptions(ROWS, "home", t));
  assert.deepEqual(tablets.showsOptions(ROWS, "other", t, unreadable)[0], ["other", "other", true]);
  assert.deepEqual(tablets.showsOptions(ROWS, "broken", t, "junk")[0], ["broken", "broken", true]);
});

test("two dashboards with the same title show their address", () => {
  const rows = [
    { url_path: "home-2", title: "Home" },
    { url_path: "home", title: "home" },
    { url_path: "night", title: "Night" },
  ];
  const labels = tablets.dashboardLabels(rows);
  assert.equal(labels.get("home"), "home (home)");
  assert.equal(labels.get("home-2"), "Home (home-2)");
  assert.equal(labels.get("night"), "Night");
  assert.deepEqual(
    tablets.showsOptions(rows, "night", t).map(([value]) => value),
    ["home", "home-2", "night"],
  );
});

test("the Tablets words: left out on tablets, and the kept choice on its own line", () => {
  assert.equal(format(strings["home.not_shown_many"], { items: "2 cards" }), "2 cards are left out on tablets.");
  assert.equal(format(strings["home.not_shown_one"], { items: "1 card" }), "1 card is left out on tablets.");
  assert.doesNotMatch(strings["tablets.no_engine_help"], /saved/);
  assert.match(strings["tablets.no_engine_saved"], /saved/);
  const panel = fs.readFileSync(path.join(root, "custom_components/apollo_tab/frontend/panel.js"), "utf8");
  assert.match(panel, /rows\.some\(\(row\) => row\?\.url_path === tablet\.dashboard\)/);
});

test("on a narrow screen a tablet row reads name, status, Shows", async () => {
  const { panelStyles } = await import("../../custom_components/apollo_tab/frontend/styles.js");
  const narrow = panelStyles.slice(panelStyles.indexOf("@container (max-width: 620px)"));
  // Spec 4.2: the status chip sits under the name.
  assert.match(narrow, /grid-template-areas:\s*"name"\s*"status"\s*"shows"\s*"notes";/);
});

test("on a phone the device page link is a 44 px high touch target", async () => {
  const { panelStyles } = await import("../../custom_components/apollo_tab/frontend/styles.js");
  const start = panelStyles.indexOf("@media (max-width: 700px), (pointer: coarse) {\n  .tablet-device-page {");
  assert.ok(start >= 0, "no phone rule for the device page link");
  const rule = panelStyles.slice(start, panelStyles.indexOf("}", start));
  assert.match(rule, /display: flex;/);
  assert.match(rule, /min-height: 44px;/);
  const panel = fs.readFileSync(path.join(root, "custom_components/apollo_tab/frontend/panel.js"), "utf8");
  assert.match(panel, /haLink\("tablet-device-page", t\("tablets\.device_page"\)/);
});

test("dashboard texts are unique and match the Home Assistant list", () => {
  const cases = JSON.parse(fs.readFileSync(path.join(root, "tests/label_cases.json"), "utf8")).cases;
  assert.ok(cases.length >= 5);
  for (const item of cases) {
    const labels = tablets.dashboardLabels(item.rows);
    assert.deepEqual(Object.fromEntries(labels), item.expect, item.name);
    const texts = [...labels.values()].map((text) => text.toLowerCase());
    assert.equal(new Set(texts).size, texts.length, item.name);
  }
});

test("the delete question names the tablets and where they go", () => {
  const list = [KITCHEN, HALLWAY, BEDROOM];
  assert.equal(
    tablets.deleteNote(list, "home", ROWS, t),
    "Bedroom tablet and Kitchen tablet show this dashboard. They will switch to Night.",
  );
  assert.equal(
    tablets.deleteNote(list, "night", ROWS, t),
    "Hallway tablet shows this dashboard. It will switch to Home.",
  );
  assert.equal(
    tablets.deleteNote(list, "home", [{ url_path: "home", title: "Home" }], t),
    "Bedroom tablet and Kitchen tablet show this dashboard. They will have nothing to show.",
  );
  assert.equal(
    tablets.deleteNote([HALLWAY], "night", [], t),
    "Hallway tablet shows this dashboard. It will have nothing to show.",
  );
  assert.equal(tablets.deleteNote(list, "other", ROWS, t), "");
  // The first other dashboard in the one order, whatever order they came in.
  const rows = [
    { url_path: "zoo", title: "Zoo" },
    { url_path: "attic", title: "attic" },
    { url_path: "home", title: "Home" },
  ];
  assert.equal(tablets.nextDashboard(rows, "home").url_path, "attic");
  assert.equal(tablets.nextDashboard(rows, "attic").url_path, "home");
  assert.equal(tablets.nextDashboard([], "home"), null);
});

test("the editor's caption has one line per tablet, at most three", () => {
  assert.deepEqual(
    tablets.captionLines([KITCHEN, HALLWAY, BEDROOM], "home", t).map((line) => line.text),
    ["Bedroom tablet needs a software update", "On Kitchen tablet"],
  );
  assert.deepEqual(tablets.captionLines([KITCHEN], "night", t), [
    { kind: "nowhere", text: "Not on a tablet yet" },
  ]);
  assert.deepEqual(tablets.captionLines([], "home", t), [{ kind: "nowhere", text: "Not on a tablet yet" }]);
  const five = ["A", "B", "C", "D", "E"].map((letter, index) => tablet(`m${index}`, `${letter} tablet`));
  const lines = tablets.captionLines(five, "home", t);
  assert.deepEqual(
    lines.map((line) => line.text),
    ["On A tablet", "On B tablet", "On C tablet", "and 2 more"],
  );
  assert.equal(lines[0].mac, "m0");
  assert.equal(lines[0].tone, "ok");
  // The editor's Tablets pop-up names every one.
  assert.equal(tablets.captionLines(five, "home", t, Infinity).length, 5);
});

test("chipWords gives one short line for every situation", () => {
  const words = (list, urlPath = "home") => tablets.chipWords(list, urlPath, t);
  const named = (name, changes = {}) => tablet(`mac-${name}`, name, changes);
  // Each row of the design's table.
  assert.deepEqual(words([]), { text: "No tablets yet", tone: "quiet", more: 0, full: "No tablets yet" });
  assert.deepEqual(words([PORCH]), { text: "Not on a tablet yet", tone: "quiet", more: 0, full: "Not on a tablet yet" });
  assert.deepEqual(words([KITCHEN], "night"), { text: "Not on a tablet yet", tone: "quiet", more: 0, full: "Not on a tablet yet" });
  assert.deepEqual(words([KITCHEN]), { text: "On Kitchen tablet", tone: "ok", more: 0, full: "On Kitchen tablet" });
  const three = [named("A tablet"), named("B tablet"), named("C tablet")];
  assert.deepEqual(words(three), { text: "On 3 tablets", tone: "ok", more: 0, full: "On 3 tablets" });
  const sending = { ...KITCHEN, status: "sending" };
  assert.deepEqual(words([sending]), { text: "Sending to Kitchen tablet…", tone: "busy", more: 0, full: "Sending to Kitchen tablet…" });
  assert.equal(words([sending, { ...named("B tablet"), status: "sending" }]).text, "Sending to 2 tablets…");
  const offline = { ...KITCHEN, status: "offline" };
  assert.deepEqual(words([offline]), { text: "Kitchen tablet is offline", tone: "quiet", more: 0, full: "Kitchen tablet is offline" });
  const broken = { ...KITCHEN, status: "failed", reason: "auth", retry: true };
  assert.deepEqual(words([broken]), { text: "Kitchen tablet needs attention", tone: "problem", more: 0, full: "Kitchen tablet needs attention" });
  // More that need a look: "+2"; a problem is named before an offline one.
  const more = words([offline, broken, { ...named("Attic tablet"), status: "no_engine" }]);
  assert.equal(more.text, "Attic tablet needs attention +2");
  assert.equal(more.tone, "problem");
  assert.equal(more.more, 2);
  assert.equal(more.full, "Attic tablet needs attention 2 more need a look.");
  const one = words([{ ...named("Hall tablet"), status: "offline" }, offline, named("Zed tablet")]);
  assert.equal(one.text, "Hall tablet is offline +1");
  assert.equal(one.full, "Hall tablet is offline 1 more needs a look.");
  // The longest row of the design is 33 characters.
  const longest = words([broken, { ...offline, mac: "x1", name: "Lounge tablet" }, { ...offline, mac: "x2", name: "Study tablet" }]);
  assert.equal(longest.text, "Kitchen tablet needs attention +2");
  assert.equal(longest.text.length, 33);
  // A 14-letter name: no line is over 34 characters.
  const fourteen = "Livingroom tab";
  assert.equal(fourteen.length, 14);
  for (const changes of [{}, { status: "sending" }, { status: "offline" }, { status: "failed", reason: "size" }, { status: "no_engine" }]) {
    for (const extra of [[], [{ ...offline, mac: "o1" }, { ...broken, mac: "o2" }]]) {
      const line = words([named(fourteen, changes), ...extra]);
      assert.ok(line.text.length <= 34, `${line.text} is ${line.text.length} long`);
      assert.ok(!line.text.includes("…") || changes.status === "sending", `${line.text} is cut`);
    }
  }
  // A 40-letter name is cut with "…"; the words around it stay whole and
  // the whole name is in `full`.
  const forty = "The tablet on the wall by the back door!";
  assert.equal(forty.length, 40);
  for (const [changes, before, after] of [
    [{}, "On ", ""],
    [{ status: "sending" }, "Sending to ", "…"],
    [{ status: "offline" }, "", " is offline"],
    [{ status: "failed", reason: "size" }, "", " needs attention"],
  ]) {
    const line = words([named(forty, changes)]);
    assert.ok(line.text.length <= 34, `${line.text} is ${line.text.length} long`);
    assert.ok(line.text.startsWith(before) && line.text.endsWith(`…${after.replace(/^…/, "")}`), line.text);
    // A sentence that ends in "…" after the name gets no second one.
    assert.ok(!line.text.includes("……"), line.text);
    assert.ok(line.full.includes(forty), line.full);
  }
  const cutMore = words([named(forty, { status: "offline" }), { ...offline, mac: "o3", name: "Zed tablet" }]);
  assert.ok(cutMore.text.length <= 34 && cutMore.text.endsWith("… is offline +1"), cutMore.text);
  assert.ok(cutMore.full.includes(forty));
  // A shorter limit is kept as well.
  assert.ok(tablets.chipWords([named(forty)], "home", t, 20).text.length <= 20);
});

test("the editor's Shown on block says what each tablet shows", () => {
  const rows = tablets.shownOnRows([KITCHEN, HALLWAY, { ...BEDROOM, dashboard: null }], "home", ROWS, t);
  assert.deepEqual(rows, [
    { mac: BEDROOM.mac, name: "Bedroom tablet", here: false, text: "shows nothing yet" },
    { mac: HALLWAY.mac, name: "Hallway tablet", here: false, text: "shows Night" },
    { mac: KITCHEN.mac, name: "Kitchen tablet", here: true, text: "shows this dashboard" },
  ]);
});

test("a new tablet reads new whatever else it says", () => {
  // Home Assistant sends status "new"; approved false alone is enough too.
  for (const changes of [
    { status: "new" },
    { approved: false },
    { approved: false, status: "offline" },
    { approved: false, status: "no_engine" },
    { approved: false, status: "failed", reason: "auth", retry: true },
  ]) {
    const item = tablet("m", "Porch tablet", changes);
    assert.equal(tablets.statusKind(item), "new", JSON.stringify(changes));
    assert.equal(t(tablets.homeWordsKey(item)), "Ready to turn on");
    assert.equal(t(tablets.homeWordsKey(item, true)), "Ready to turn on");
    // With no dashboard yet the chip reads the same; "Make a dashboard
    // first." beside it says what comes first.
    assert.equal(t(tablets.homeWordsKey(item, false)), "Ready to turn on");
    assert.equal(tablets.lineWordsKey(item), null);
    assert.equal(tablets.statusTone(item), "new");
    assert.equal(tablets.inputNoteKey({ ...item, input: "not_paired" }), null);
    assert.ok(tablets.isNewTablet(item));
  }
  assert.ok(!tablets.isNewTablet(KITCHEN));
  assert.ok(!tablets.isNewTablet({ ...KITCHEN, approved: undefined }));
  assert.ok(!tablets.isNewTablet(null));
  // A tablet that is on keeps its words with or without dashboards.
  assert.equal(tablets.homeWordsKey(KITCHEN, false), "tablets.status.on_tablet");
  assert.equal(tablets.homeWordsKey({ ...KITCHEN, status: "no_dashboard" }, false), "tablets.status.no_dashboard");
});

test("Home lists new tablets first, each group by name", () => {
  const zed = tablet("aa:bb:cc:00:00:05", "Attic tablet", { status: "new", approved: false, dashboard: null });
  assert.deepEqual(
    tablets.homeOrder([KITCHEN, PORCH, HALLWAY, zed, BEDROOM]).map((entry) => entry.name),
    ["Attic tablet", "Porch tablet", "Bedroom tablet", "Hallway tablet", "Kitchen tablet"],
  );
  assert.deepEqual(tablets.homeOrder(undefined), []);
  assert.equal(tablets.newTabletCount([KITCHEN, PORCH, zed]), 2);
  assert.equal(tablets.newTabletCount([KITCHEN]), 0);
});

test("new tablets are left out of what tablets show", () => {
  // Even one that still names a dashboard is not counted anywhere.
  const named = { ...PORCH, dashboard: "home" };
  const list = [KITCHEN, HALLWAY, PORCH, named];
  assert.deepEqual(
    tablets.tabletsShowing(list, "home").map((entry) => entry.mac),
    [KITCHEN.mac],
  );
  assert.equal(tablets.shownOnText(list, "home", t), "On Kitchen");
  assert.equal(tablets.shownOnText([PORCH, named], "home", t), "");
  assert.equal(
    tablets.deleteNote(list, "home", ROWS, t),
    "Kitchen tablet shows this dashboard. It will switch to Night.",
  );
  assert.equal(tablets.deleteNote([named], "home", ROWS, t), "");
  assert.deepEqual(
    tablets.captionLines(list, "home", t).map((line) => line.text),
    ["On Kitchen tablet"],
  );
  assert.deepEqual(tablets.captionLines([named], "home", t), [{ kind: "nowhere", text: "Not on a tablet yet" }]);
  assert.deepEqual(
    tablets.shownOnRows(list, "home", ROWS, t).map((row) => row.mac),
    [HALLWAY.mac, KITCHEN.mac],
  );
  assert.deepEqual(tablets.shownOnRows([PORCH], "home", ROWS, t), []);
});

test("a new tablet's Shows list starts empty and marks what it showed before", () => {
  assert.deepEqual(tablets.showsOptions(ROWS, PORCH.dashboard, t, [], PORCH.suggested), [
    ["", "Pick a dashboard", true],
    ["home", "Home", false],
    ["night", "Night (shown before)", false],
  ]);
  // A suggestion that is not a dashboard any more is left out.
  assert.deepEqual(tablets.showsOptions(ROWS, null, t, [], "gone"), tablets.showsOptions(ROWS, null, t));
  // The tablet's own dashboard is never marked.
  assert.deepEqual(tablets.showsOptions(ROWS, "night", t, [], "night"), tablets.showsOptions(ROWS, "night", t));
  // Picking alone turns nothing on, so the warning is about turning on.
  assert.equal(t("tablets.approve_note"), "If it shows another name, or this is not your tablet, do not turn it on.");
  assert.equal(t("tablets.new_mark"), "New");
});

test("a change of a new tablet's Shows list only chooses; approved tablets switch at once", () => {
  // In some browsers an arrow key on a closed list changes its value, so a
  // change alone must never turn a tablet on.
  assert.equal(tablets.showsChangeAssigns(PORCH), false);
  assert.equal(tablets.showsChangeAssigns({ ...KITCHEN, approved: false }), false);
  assert.equal(tablets.showsChangeAssigns({ ...KITCHEN, status: "new" }), false);
  assert.equal(tablets.showsChangeAssigns(undefined), false);
  assert.equal(tablets.showsChangeAssigns(KITCHEN), true);
  assert.equal(tablets.showsChangeAssigns(HALLWAY), true);
  assert.equal(t("tablets.turn_on"), "Turn on with this dashboard");
});

test("a new tablet's row says which device it is: the end of the name on its screen, device page", () => {
  const porch = { ...PORCH, device_id: "0123456789abcdef0123456789abcdef" };
  assert.equal(tablets.macEnding(porch.mac), "0004");
  assert.equal(tablets.macEnding("AA:BB:CC:DD:EE:0F"), "ee0f");
  assert.equal(tablets.macEnding("AA:BB:CC:12:EE:0F", 6), "12ee0f");
  assert.equal(tablets.macEnding(undefined), "");
  // The tablet's waiting screen shows its name with the last 6 characters
  // of its MAC address, in lower case: "Apollo TAB-1 000004" here. The row
  // names the same 6, whatever the tablet is called in Home Assistant.
  assert.equal(tablets.SCREEN_NAME_MAC_CHARS, 6);
  // It asks the admin to check them on the tablet, in plain words.
  const line = "Look at the tablet. The name on its screen ends in 000004.";
  assert.equal(tablets.deviceLine(porch, t), line);
  assert.equal(tablets.deviceLine({ ...porch, name: "Garden tablet", short_name: "Garden" }, t), line);
  assert.equal(
    tablets.deviceLine({ ...porch, mac: "30:ED:A0:12:EE:0E" }, t),
    "Look at the tablet. The name on its screen ends in 12ee0e.",
  );
  assert.doesNotMatch(line, /\bMAC\b/);
  // The model is always TAB-1 (only TAB-1 devices are tablets): not shown.
  assert.equal(tablets.deviceLine({ ...porch, model: "Other" }, t), line);
  assert.equal(tablets.devicePagePath(porch), "/config/devices/device/0123456789abcdef0123456789abcdef");
  // Nothing but an id becomes part of the address.
  assert.equal(tablets.devicePagePath({ ...porch, device_id: "javascript:alert(1)" }), null);
  assert.equal(tablets.devicePagePath({ ...porch, device_id: "../x" }), null);
  assert.equal(tablets.devicePagePath({ ...porch, device_id: null }), null);
  assert.equal(t("tablets.device_page"), "Open device page");
  assert.equal(
    t("tablets.waiting_note"),
    "Until you turn it on, the tablet keeps the screen it has now, and taps on it do nothing.",
  );
});

test("a tablet added again says its screen keeps its old dashboard, not its name", () => {
  // PORCH showed Night before it was added to ESPHome again.
  assert.equal(
    tablets.deviceBeforeLine(PORCH, ROWS, t),
    "If it still shows Night, its old dashboard, its name is not on its screen. Check that it shows Night and that its values no longer change.",
  );
  // The dashboard by the name the lists use.
  assert.equal(
    tablets.deviceBeforeLine(PORCH, [...ROWS, { url_path: "night-2", title: "Night" }], t),
    "If it still shows Night (night), its old dashboard, its name is not on its screen. Check that it shows Night (night) and that its values no longer change.",
  );
  // A tablet that never showed one, whose dashboard is gone, or that is on:
  // no line.
  assert.equal(tablets.deviceBeforeLine({ ...PORCH, suggested: null }, ROWS, t), "");
  assert.equal(tablets.deviceBeforeLine(PORCH, [{ url_path: "home", title: "Home" }], t), "");
  assert.equal(tablets.deviceBeforeLine(PORCH, [], t), "");
  assert.equal(tablets.deviceBeforeLine({ ...KITCHEN, suggested: "night" }, ROWS, t), "");
  assert.equal(tablets.deviceBeforeLine(null, ROWS, t), "");
});

test("a changed tablet replaces the one with its MAC", () => {
  const list = [KITCHEN, HALLWAY];
  const changed = { ...HALLWAY, dashboard: "home" };
  assert.deepEqual(tablets.withTablet(list, changed), [KITCHEN, changed]);
  assert.deepEqual(tablets.withTablet(list, BEDROOM), [KITCHEN, HALLWAY, BEDROOM]);
  assert.equal(tablets.withTablet(list, null), list);
  assert.equal(tablets.withTablet(null, KITCHEN), null);
});

// Design 10.9: every message from Home Assistant about turning on a new
// tablet says the same two steps, in the same words as the button. The
// panel's own chip is short ("Ready to turn on"); its row holds the steps.
test("every message about a new tablet says: pick a dashboard, then press the button", () => {
  const button = strings["tablets.turn_on"];
  // The editor no longer tells the steps: its Tablets pop-up names the new
  // tablet and "Set it up" goes to the start screen, where they are.
  assert.equal(strings["editor.on_tablet_new"], "{tablet} is new and ready to turn on.");
  const en = JSON.parse(fs.readFileSync(path.join(root, "custom_components/apollo_tab/translations/en.json"), "utf8"));
  for (const [where, text] of [
    ["approval_needed", en.exceptions.approval_needed.message],
    ["new_tablet issue", en.issues.new_tablet.description],
    ["show_dashboard", en.services.show_dashboard.description],
  ]) {
    assert.match(text, /pick a dashboard for it,? (then|and) press "Turn on with this dashboard"/, where);
  }
  // Round 8: the answers to a change that needs the button quote it and
  // end in a full stop, as the panel's own line does.
  const ending = `press "${button}".`;
  const shapes = JSON.parse(fs.readFileSync(path.join(root, "tests/harness/tablet-shapes.json"), "utf8"));
  for (const [where, text] of [
    ["approval_needed", en.exceptions.approval_needed.message],
    ["assign not_approved", shapes.commands["apollo_tab/tablet/assign"].errors.not_approved],
    ["pair not_approved", shapes.commands["apollo_tab/tablet/pair"].errors.not_approved],
  ]) {
    assert.ok(text.endsWith(ending), `${where}: ${text}`);
  }
  // No message still says the pick alone is enough.
  for (const [key, value] of Object.entries(strings)) {
    assert.doesNotMatch(value, /then turn it on|[Pp]ick a dashboard for tablets you own/, key);
  }
});

test("Home keeps each tablet's place while the panel is open", () => {
  const patio = tablet("aa:bb:cc:00:00:05", "Patio tablet", { status: "new", approved: false, dashboard: null });
  const first = tablets.keepOrder([KITCHEN, PORCH, patio, HALLWAY]);
  assert.deepEqual(
    first.map((entry) => entry.name),
    ["Patio tablet", "Porch tablet", "Hallway tablet", "Kitchen tablet"],
  );
  const order = first.map((entry) => entry.mac);
  // Patio is turned on: it stays first, it does not move down to the
  // tablets that are on, and Porch stays under it.
  const on = { ...patio, approved: true, status: "sending", dashboard: "home" };
  assert.deepEqual(
    tablets.keepOrder([KITCHEN, PORCH, on, HALLWAY], order).map((entry) => entry.name),
    ["Patio tablet", "Porch tablet", "Hallway tablet", "Kitchen tablet"],
  );
  // homeOrder alone would move it.
  assert.deepEqual(
    tablets.homeOrder([KITCHEN, PORCH, on, HALLWAY]).map((entry) => entry.name),
    ["Porch tablet", "Hallway tablet", "Kitchen tablet", "Patio tablet"],
  );
  // A renamed tablet keeps its place too.
  assert.deepEqual(
    tablets.keepOrder([{ ...KITCHEN, name: "Attic tablet" }, PORCH, patio, HALLWAY], order).map((entry) => entry.mac),
    order,
  );
  // A tablet that comes while the panel is open: a new one on top, one that
  // is on at the bottom. One that goes is left out.
  const zed = tablet("aa:bb:cc:00:00:06", "Zed tablet", { status: "new", approved: false, dashboard: null });
  assert.deepEqual(
    tablets.keepOrder([KITCHEN, PORCH, patio, zed, BEDROOM], order).map((entry) => entry.name),
    ["Zed tablet", "Patio tablet", "Porch tablet", "Kitchen tablet", "Bedroom tablet"],
  );
  assert.deepEqual(tablets.keepOrder([KITCHEN, PORCH], []), tablets.homeOrder([KITCHEN, PORCH]));
  assert.deepEqual(tablets.keepOrder(undefined, order), []);
});

test("a press of Turn on right after the rows moved is ignored", () => {
  assert.equal(tablets.TURN_ON_SETTLE_MS, 700);
  // No time means not settled (rule 4): a button nobody looked at waits.
  assert.equal(tablets.turnOnSettled(null, 5), false);
  assert.equal(tablets.turnOnSettled(undefined, 5), false);
  assert.equal(tablets.turnOnSettled(1000, 1000), false);
  assert.equal(tablets.turnOnSettled(1000, 1699), false);
  assert.equal(tablets.turnOnSettled(1000, 1700), true);
  assert.equal(tablets.turnOnSettled(1000, 5000), true);
});

// Round 8: only a button that moved or came under the pointer waits; words
// that change elsewhere move nothing.
test("only the Turn on buttons that moved or came count as moved", () => {
  const before = new Map([
    ["aa:01", [24, 300, 220, 40]],
    ["aa:02", [24, 420, 220, 40]],
    ["aa:03", [24, 540, 220, 40]],
  ]);
  // Nothing moved: no button waits, also after the box was built again.
  assert.deepEqual(tablets.movedTurnOns(before, new Map(before)), []);
  // Rounding is not a move.
  assert.deepEqual(tablets.movedTurnOns(before, new Map([...before, ["aa:02", [24.4, 420.5, 220, 40]]])), []);
  // A row above aa:02 lost its button and lines: aa:02 and aa:03 moved up.
  const after = new Map([
    ["aa:02", [24, 300, 220, 40]],
    ["aa:03", [24, 420, 220, 40]],
  ]);
  assert.deepEqual(tablets.movedTurnOns(before, after), ["aa:02", "aa:03"]);
  // A button that came (a tablet became new again) counts; one wider too.
  const came = new Map([...before, ["aa:04", [24, 660, 220, 40]], ["aa:01", [24, 300, 260, 40]]]);
  assert.deepEqual(tablets.movedTurnOns(before, came).sort(), ["aa:01", "aa:04"]);
  // The first look: every button came (rule 4).
  assert.deepEqual(tablets.movedTurnOns(null, after), ["aa:02", "aa:03"]);
  assert.deepEqual(tablets.movedTurnOns(before, null), []);
});

// Round 11: two Turn on buttons, a line comes in the lower row and moves
// only its button. That button waits; the other keeps the time it had and
// takes a press at once. (Marking every button when one moved passed every
// suite but the journey, which CI does not run.)
test("a row that moves one Turn on button does not hold the others", () => {
  const before = new Map([
    ["aa:01", [24, 300, 220, 40]],
    ["aa:02", [24, 420, 220, 40]],
  ]);
  const after = new Map([
    ["aa:01", [24, 300, 220, 40]],
    ["aa:02", [24, 468, 220, 40]],
  ]);
  const movedAt = new Map([["aa:01", 100]]);
  const marked = tablets.markMoved(movedAt, before, after, 900);
  assert.deepEqual([...marked], [
    ["aa:01", 100],
    ["aa:02", 900],
  ]);
  assert.equal(tablets.turnOnSettled(marked.get("aa:01"), 1000), true);
  assert.equal(tablets.turnOnSettled(marked.get("aa:02"), 1000), false);
  // The old times stay as they were.
  assert.deepEqual([...movedAt], [["aa:01", 100]]);
  // Nothing moved: nothing changes, also for a button with no time yet.
  assert.deepEqual([...tablets.markMoved(movedAt, before, new Map(before), 900)], [["aa:01", 100]]);
  assert.deepEqual([...tablets.markMoved(new Map(), before, new Map(before), 900)], []);
  // The first look marks every button (rule 4); a button that came is marked.
  assert.deepEqual([...tablets.markMoved(null, null, after, 900)], [
    ["aa:01", 900],
    ["aa:02", 900],
  ]);
  assert.deepEqual([...tablets.markMoved(null, new Map([["aa:01", [24, 300, 220, 40]]]), after, 900)], [["aa:02", 900]]);
});

test("after a scroll the panel made, every turn-on button waits again", () => {
  const movedAt = new Map([
    ["aa:01", 100],
    ["aa:03", 50],
  ]);
  const marked = tablets.markAll(movedAt, ["aa:01", "aa:02"], 5000);
  assert.deepEqual([...marked], [
    ["aa:01", 5000],
    ["aa:03", 50],
    ["aa:02", 5000],
  ]);
  // The map it was given stays as it was.
  assert.deepEqual([...movedAt], [
    ["aa:01", 100],
    ["aa:03", 50],
  ]);
  for (const mac of ["aa:01", "aa:02"]) {
    assert.equal(tablets.turnOnSettled(marked.get(mac), 5000), false);
    assert.equal(tablets.turnOnSettled(marked.get(mac), 5699), false);
    assert.equal(tablets.turnOnSettled(marked.get(mac), 5700), true);
  }
  // Nothing named, or no map yet: nothing breaks.
  assert.deepEqual([...tablets.markAll(null, ["aa:01"], 7)], [["aa:01", 7]]);
  assert.deepEqual([...tablets.markAll(movedAt, undefined, 7)], [...movedAt]);
});

test("the panel guards each Turn on button by its own place, and shows the wait", async () => {
  const panel = fs.readFileSync(path.join(root, "custom_components/apollo_tab/frontend/panel.js"), "utf8");
  const turnOn = panel.slice(panel.indexOf("  _turnOn(mac) {"), panel.indexOf("  _pairButton("));
  assert.match(turnOn, /turnOnSettled\(this\._turnOnMovedAt\.get\(mac\), performance\.now\(\)\)/);
  // No status words: only the buttons' places decide.
  const note = panel.slice(panel.indexOf("  _noteTabletLayout() {"), panel.indexOf("  _showSettling() {"));
  assert.match(note, /this\._turnOnMovedAt = markMoved\(this\._turnOnMovedAt, this\._turnOnPlaces, places, performance\.now\(\)\);\n {4}this\._turnOnPlaces = places;/);
  assert.doesNotMatch(note, /textContent|notesKey|ui\.shape/);
  // Round 11: the times change only through markMoved (tested on its own
  // below), markPicks (a pick the person did not make), markAll (a scroll
  // the panel made: arrival, the guide's button, a new screen), or all at
  // once when the panel forgets the places.
  const writes = [...panel.matchAll(/this\._turnOnMovedAt(?:\s*=[^;]*;|\.(?:set|delete|clear)\()/g)].map((match) => match[0]);
  assert.deepEqual(writes, [
    "this._turnOnMovedAt = new Map();",
    "this._turnOnMovedAt = markAll(this._turnOnMovedAt, [...places.keys()], performance.now());",
    "this._turnOnMovedAt = markMoved(this._turnOnMovedAt, this._turnOnPlaces, places, performance.now());",
    "this._turnOnMovedAt = markPicks(this._turnOnMovedAt, this._turnOnSends, sends, this._ownPick, performance.now());",
    "this._turnOnMovedAt = new Map();",
  ]);
  const { panelStyles } = await import("../../custom_components/apollo_tab/frontend/styles.js");
  // A button that waits looks exactly like a disabled filled button: one
  // rule holds both, and neither is faded.
  const start = panelStyles.indexOf("button.primary:disabled,\n.tablet-turn-on[data-settling] {");
  assert.ok(start >= 0, "no look for a button that waits");
  const look = panelStyles.slice(start, panelStyles.indexOf("}", start));
  assert.match(look, /background: var\(--tab-tonal\);/);
  assert.match(look, /color: var\(--tab-disabled\);/);
  for (const match of panelStyles.matchAll(/([^{}]*(?:button:disabled|\[data-settling\])[^{}]*)\{([^}]*)\}/g)) {
    assert.doesNotMatch(match[2], /opacity/, `${match[1].trim()} is faded`);
  }
});

test("an erased tablet's row says that Home Assistant waits in Repairs", () => {
  const erased = { ...KITCHEN, status: "offline", reauth: "erased", reauth_name: "Apollo TAB-1 ddee01" };
  assert.equal(
    tablets.reauthLine(erased, t),
    'Only if you erased this tablet and its screen says "Confirm this tablet in Home Assistant" ("Add this tablet in Home Assistant" after a USB erase): confirm "Authentication expired for Apollo TAB-1 ddee01"; it gets its old key back. "Setup not finished": restart it first. Otherwise do not confirm: check the tablet.',
  );
  assert.equal(
    tablets.reauthLine({ ...erased, reauth: "key" }, t),
    'Home Assistant asks for this tablet\'s key in Repairs, under "Authentication expired for Apollo TAB-1 ddee01". Do not enter a key. If you erased the tablet yourself and its screen says "Setup not finished": close the question, restart the tablet, and within 15 minutes go to Settings > Devices & services > ESPHome, open the tablet\'s menu (three dots) and press Reload. If not, check the tablet.',
  );
  // A new tablet can wait too.
  assert.equal(tablets.reauthLine({ ...PORCH, reauth: "erased", reauth_name: "Porch" }, t), t("tablets.reauth_erased", { name: "Porch" }));
  for (const other of [KITCHEN, { ...erased, reauth: null, reauth_name: null }, { ...erased, reauth: "later" }, { ...erased, reauth_name: "" }, null]) {
    assert.equal(tablets.reauthLine(other, t), "", JSON.stringify(other));
  }
  assert.equal(tablets.REPAIRS_PATH, "/config/repairs");
  assert.equal(t("tablets.open_repairs"), "Open Repairs");
});

// The tablet's own screens that the two lines check, from the shared
// contract. "Confirm this tablet in Home Assistant" (waiting.erased) shows
// after the hold-the-screen erase until the tablet has a key again, "Add
// this tablet in Home Assistant" (waiting.add) on a tablet never erased or
// erased over USB; both only without its key, in the 15 minutes after
// power-on, while Home Assistant is not connected to it. "Setup not
// finished" (waiting.closed) shows only without its key after those 15
// minutes. Another device on the network cannot make a tablet that still
// has its key show any of them.
const SCREEN_ERASED = SCREENS.waiting.erased.headline;
const SCREEN_ADD = SCREENS.waiting.add.headline;
const SCREEN_TIME_UP = SCREENS.waiting.closed.headline;
const HEADLINES = new Set(Object.values(SCREENS.waiting).map((screen) => screen.headline));

// Round 8: Home Assistant's question after an erase can also come from a
// device that pretends to be the tablet, and confirming hands it the key
// Home Assistant kept for the tablet. Round 9: the check comes first, a
// restart alone never counts, a yes gives back the kept key. Round 10: the
// check is the tablet's own screen, not the time or the steps for a key.
// Round 11: the screen a tablet shows after the hold-the-screen erase
// (since the firmware's round 10 it never says "Add this tablet in Home
// Assistant" then), and "Add ..." only after an erase over USB, which
// leaves no erase mark. The words come from the shared contract, so the
// line cannot name a screen the tablet no longer shows. An admin who erased
// it longer ago gets the next step: "Setup not finished" means restart it
// first; it then shows the same screen again.
test("the erased line tells an admin when not to confirm", () => {
  const text = strings["tablets.reauth_erased"];
  // The check, both halves, comes before the only yes.
  assert.ok(
    text.startsWith(
      `Only if you erased this tablet and its screen says "${SCREEN_ERASED}" ("${SCREEN_ADD}" after a USB erase): confirm "Authentication expired for {name}"`,
    ),
    text,
  );
  assert.ok(text.indexOf(`its screen says "${SCREEN_ERASED}"`) < text.indexOf(': confirm "'));
  // The tablet's screens it names, in this order: the two of a tablet
  // without its key in its 15 minutes, then the one after them. None that a
  // tablet with its key shows ("Waiting for Home Assistant", its dashboard).
  const named = [...text.matchAll(/"([^"]+)"/g)].map((match) => match[1]).filter((quote) => HEADLINES.has(quote));
  assert.deepEqual(named, [SCREEN_ERASED, SCREEN_ADD, SCREEN_TIME_UP]);
  // The screen for a new tablet only with the erase over USB.
  assert.equal(text.split(`"${SCREEN_ADD}"`).length, 2);
  assert.ok(text.includes(`("${SCREEN_ADD}" after a USB erase)`));
  // One yes and one no, outside the quoted words.
  assert.equal(text.replace(/"[^"]*"/g, '""').match(/\bconfirm\b/g).length, 2, "one yes and one no");
  assert.match(text, /\{name\}"; it gets its old key back\./);
  // The next step when its 15 minutes ran out, and the restart only there.
  assert.ok(text.includes(` "${SCREEN_TIME_UP}": restart it first. `), text);
  assert.equal(text.match(/restart/gi).length, 1);
  // Anything else on its screen (its dashboard, "Waiting for Home
  // Assistant", "Ready to turn on", nothing) is a no, last.
  assert.match(text, /Otherwise do not confirm: check the tablet\.$/);
  // No yes without the screen: no time rule, no "or", no steps for a key.
  assert.doesNotMatch(text, /15 minutes|minutes|steps for a key|, or |or just|last few|new key|This tablet was erased/i);
  // About 50 words with a tablet's name in it; the screen after a USB erase
  // takes 10 of them.
  const words = format(text, { name: "Apollo TAB-1 ddee01" }).split(/\s+/).length;
  assert.ok(words <= 52, `${words} words`);
});

// Round 8: one set of steps for the question for a key, the one that works
// with Home Assistant 2026.11: a reload ends that question (tests/
// test_approval_guards.py), the tablet then gets the erased question.
// Round 10: the steps are only for an admin who erased the tablet and sees
// "Setup not finished" on its screen (it met Home Assistant after its 15
// minutes); anyone else is told not to enter a key and to check the tablet.
// The line no longer says to confirm: the erased line that comes after the
// steps has the check.
test("the key line gives the steps that work", () => {
  const text = strings["tablets.reauth_key"];
  assert.match(text, /^Home Assistant asks for this tablet's key in Repairs, under "Authentication expired for \{name\}"\. Do not enter a key\. /);
  assert.ok(
    text.includes(
      `If you erased the tablet yourself and its screen says "${SCREEN_TIME_UP}": close the question, restart the tablet, and within 15 minutes go to Settings > Devices & services > ESPHome, open the tablet's menu (three dots) and press Reload.`,
    ),
    text,
  );
  assert.match(text, /If not, check the tablet\.$/);
  // In this order: the screen, close, restart, Reload, then the no.
  const at = [`its screen says "${SCREEN_TIME_UP}"`, "close the question", "restart the tablet", "within 15 minutes", "press Reload", "If not, check the tablet"].map(
    (words) => text.indexOf(words),
  );
  assert.ok(at.every((index, i) => index >= 0 && (i === 0 || index > at[i - 1])), JSON.stringify(at));
  // No step comes before the check.
  const steps = text.indexOf("close the question");
  assert.ok(text.slice(0, steps).includes(`If you erased the tablet yourself and its screen says "${SCREEN_TIME_UP}"`));
  assert.doesNotMatch(text, /confirm|because you erased|enter no key|empty|Submit|reload it in Settings > Devices & services;/i);
  const words = format(text, { name: "Apollo TAB-1 ddee01" }).split(/\s+/).length;
  assert.ok(words <= 67, `${words} words`);
});

// Round 10: the route from a question for a key to a yes passes the
// tablet's screen twice. A device on the network that takes the tablet's
// place can pick which question Home Assistant asks, but a tablet that
// still has its key shows neither screen, so neither line leads to a yes.
test("the way from a question for a key to a yes checks the tablet's screen", () => {
  const key = strings["tablets.reauth_key"];
  const erased = strings["tablets.reauth_erased"];
  // The steps: only after "Setup not finished". The yes: only with
  // "Confirm this tablet in Home Assistant" (or, after an erase over USB,
  // "Add this tablet in Home Assistant"). Nothing in either line counts the
  // steps themselves, a time, or a restart as a reason to confirm.
  assert.ok(key.indexOf(`"${SCREEN_TIME_UP}"`) < key.indexOf("press Reload"));
  assert.ok(erased.indexOf(`"${SCREEN_ERASED}"`) < erased.indexOf(': confirm "'));
  assert.ok(erased.indexOf(`"${SCREEN_ADD}"`) < erased.indexOf(': confirm "'));
  for (const text of [key, erased]) {
    assert.doesNotMatch(text, /steps for a key|because you erased|just did|last 15 minutes/i, text);
  }
  // Both name the same Repairs entry.
  for (const text of [key, erased]) {
    assert.ok(text.includes('"Authentication expired for {name}"'), text);
  }
});

test("on a phone the Repairs link is a 44 px high touch target", async () => {
  const { panelStyles } = await import("../../custom_components/apollo_tab/frontend/styles.js");
  const start = panelStyles.indexOf("@media (max-width: 700px), (pointer: coarse) {\n  .tablet-repairs {");
  assert.ok(start >= 0, "no phone rule for the Repairs link");
  const rule = panelStyles.slice(start, panelStyles.indexOf("}", start));
  assert.match(rule, /display: flex;/);
  assert.match(rule, /min-height: 44px;/);
  const panel = fs.readFileSync(path.join(root, "custom_components/apollo_tab/frontend/panel.js"), "utf8");
  assert.match(panel, /haLink\("tablet-repairs", t\("tablets\.open_repairs"\), REPAIRS_PATH/);
});

// Round 8: on a phone the 44 px links sit on lines of their own; the space
// above and below them is wider than their focus ring reaches, so the ring
// does not cover the words above.
test("on a phone the links leave room for their focus ring", async () => {
  const { panelStyles } = await import("../../custom_components/apollo_tab/frontend/styles.js");
  const focus = panelStyles.slice(panelStyles.indexOf("a:focus-visible,"), panelStyles.indexOf("}", panelStyles.indexOf("a:focus-visible,")));
  const reach = Number(/outline: (\d+)px solid/.exec(focus)[1]) + Number(/outline-offset: (\d+)px;/.exec(focus)[1]);
  assert.equal(reach, 4);
  for (const name of ["tablet-repairs", "tablet-device-page", "screen-devices"]) {
    const start = panelStyles.indexOf(`@media (max-width: 700px), (pointer: coarse) {\n  .${name} {`);
    assert.ok(start >= 0, name);
    const rule = panelStyles.slice(start, panelStyles.indexOf("}", start));
    const margin = /margin: (\d+)px 0;/.exec(rule);
    assert.ok(margin && Number(margin[1]) > reach, `${name}: ${rule}`);
  }
});

// Round 8: once a tablet is there, a short line under the tablets still
// says how to add another, in the same words as the line without tablets.
// Round 9: the hotspot only if the tablet asks for Wi-Fi, then where it
// shows up, in the words the tablet's own screen uses for that step (the
// contract's waiting.add: "Add this tablet in Home Assistant" / "It shows
// up by itself in Settings > Devices & services"), and last the button
// here. Spec 4.8: "Plug the tablet in" (in this panel "turn on" is the
// button).
const TABLET_ADD_STEP = SCREENS.waiting.add.step;
test("the line about adding another tablet", () => {
  const text = strings["tablets.add_another"];
  assert.equal(
    text,
    'Plug the tablet in. If it asks for Wi-Fi, join "Apollo TAB1 Hotspot" from a phone and pick your Wi-Fi. Then add it in Settings > Devices & services, where it shows up by itself, and turn it on here.',
  );
  assert.doesNotMatch(text, /turn (it|the tablet) on and|Turn the tablet on|when it shows up\./, text);
  assert.match(text, /^Plug the tablet in\. If it asks for Wi-Fi, join "Apollo TAB1 Hotspot" from a phone and pick your Wi-Fi\./);
  assert.match(text, /Then add it in Settings > Devices & services, where it shows up by itself, and turn it on here\./);
  // The same place and words as the tablet's screen.
  const [, place] = /^It shows up by itself in (.+)$/.exec(TABLET_ADD_STEP);
  assert.ok(text.includes(`add it in ${place}, where it shows up by itself`), text);
  // The box without tablets says so in a few words; the way to add one is
  // the same link under it as under the rows.
  assert.equal(strings["tablets.none"], "No tablet found yet.");
  const panel = fs.readFileSync(path.join(root, "custom_components/apollo_tab/frontend/panel.js"), "utf8");
  const box = panel.slice(panel.indexOf("  _tabletsBox() {"), panel.indexOf("  _screenSays() {"));
  // Round 11: it is put in the box, last, after the loop over the rows and
  // outside the branch for no tablets (a box without it passed every suite
  // but the journey).
  const loopEnd = box.indexOf("\n      }\n", box.indexOf("      for (const tablet of tablets) {"));
  assert.ok(loopEnd > 0, "no loop over the rows");
  assert.match(
    box.slice(loopEnd),
    /^\n {6}\}\n {4}\}\n {4}\/\/ [^\n]*\n {4}box\.append\(this\._screenSays\(\)\);\n {4}return box;\n {2}\}\n+(?: {2}\/\/[^\n]*\n)*$/,
  );
  // The link opens the fold-out, which starts with the line.
  const says = panel.slice(panel.indexOf("  _screenSays() {"), panel.indexOf("  _addLink("));
  assert.match(says, /const fold = el\("details", "screen-says"\);\n {4}fold\.dataset\.test = "screen-says";/);
  assert.match(says, /const link = el\("summary", "tablets-add", t\("tablets\.add_link"\)\);\n {4}link\.dataset\.test = "tablets-add";/);
  assert.ok(says.indexOf('t("tablets.add_another")') > says.indexOf("fold.append(link);"));
});

// Security review, rule 2 (and rule 1, the gate): the only dashboard is
// picked for a new tablet only when every one of these holds.
test("the only dashboard is picked only for a tablet that was already waiting", () => {
  const fresh = tablet("aa:bb:cc:00:00:07", "Apollo TAB-1 000007", {
    status: "new",
    approved: false,
    dashboard: null,
    suggested: null,
  });
  const one = [{ url_path: "home", title: "Home" }];
  const base = { tablet: fresh, rows: one, unreadable: [], fresh: true, waiting: new Set([fresh.mac]), enabled: true };
  assert.equal(tablets.prepicked(base), "home");
  assert.equal(tablets.prepicked({ ...base, rows: ROWS }), null, "two rows");
  assert.equal(tablets.prepicked({ ...base, unreadable: ["night"] }), null, "something unreadable");
  assert.equal(tablets.prepicked({ ...base, fresh: false }), null, "the list was not read in this visit");
  assert.equal(tablets.prepicked({ ...base, waiting: new Set() }), null, "came during the visit");
  assert.equal(tablets.prepicked({ ...base, waiting: null }), null, "no first list yet");
  assert.equal(tablets.prepicked({ ...base, tablet: { ...fresh, suggested: "home" } }), null, "showed one before");
  assert.equal(tablets.prepicked({ ...base, tablet: KITCHEN, waiting: new Set([KITCHEN.mac]) }), null, "not new");
  assert.equal(tablets.prepicked({ ...base, rows: [] }), null, "no dashboard");
  // The gate off: never, whatever else holds.
  for (const changes of [{}, { rows: ROWS }, { fresh: false }]) {
    assert.equal(tablets.prepicked({ ...base, ...changes, enabled: false }), null, JSON.stringify(changes));
  }
  // Without enabled it follows the gate.
  const { enabled, ...rest } = base;
  assert.equal(enabled, true);
  assert.equal(tablets.prepicked(rest), tablets.PREPICK_ONLY_DASHBOARD ? "home" : null);
  assert.equal(typeof tablets.PREPICK_ONLY_DASHBOARD, "boolean");
  // Off in this change (variant B): docs/tablets.md says the panel never
  // picks a dashboard for you. Turning it on changes this line and the doc.
  assert.equal(tablets.PREPICK_ONLY_DASHBOARD, false);
});

// Rule 4: a button the panel has only just drawn waits like one that moved.
test("the first look marks every turn-on button, and a button without a time is not settled", () => {
  const places = new Map([
    ["aa:01", [24, 300, 280, 56]],
    ["aa:02", [24, 420, 280, 56]],
  ]);
  assert.deepEqual(tablets.movedTurnOns(null, places), ["aa:01", "aa:02"]);
  assert.deepEqual(tablets.movedTurnOns(undefined, places), ["aa:01", "aa:02"]);
  assert.deepEqual(tablets.movedTurnOns(places, null), []);
  const marked = tablets.markMoved(new Map(), null, places, 4000);
  assert.deepEqual([...marked], [
    ["aa:01", 4000],
    ["aa:02", 4000],
  ]);
  assert.equal(tablets.turnOnSettled(marked.get("aa:01"), 4699), false);
  assert.equal(tablets.turnOnSettled(marked.get("aa:01"), 4700), true);
  for (const movedAt of [null, undefined, Number.NaN, "5", Infinity]) {
    assert.equal(tablets.turnOnSettled(movedAt, 99999), false, String(movedAt));
  }
  assert.equal(tablets.turnOnSettled(0, Number.NaN), false);
});

// Rule 6: a press counts only when it began on a settled button and is
// still about the dashboard the button named then.
test("a press counts only when it began on a settled button", () => {
  const mac = "aa:01";
  const movedAt = 1000; // settled from 1700
  const ok = (press, click, runStart = null) => tablets.pressCounts({ press, click, movedAt, runStart, mac });
  const click = (at, detail = 1, sends = "home") => ({ at, detail, sends });
  const press = (kind, at, extra = {}) => ({ kind, at, repeat: false, foreign: false, sends: "home", ...extra });
  // A pointer down during the wait, the click after it.
  assert.equal(ok(press("pointer", 1500), click(1800)), false);
  // A repeated key.
  assert.equal(ok(press("key", 1800, { repeat: true }), click(1800, 0)), false);
  // Space down during the wait, up after it.
  assert.equal(ok(press("key", 1600), click(1900, 0)), false);
  // A key-up with no key-down on the button.
  assert.equal(ok(press("key", 1900, { foreign: true }), click(1900, 0)), false);
  // The second click of a run that started on another button, soon or late.
  assert.equal(ok(press("pointer", 1850), click(1850, 2), "aa:02"), false);
  assert.equal(ok(press("pointer", 2600), click(2600, 2), "aa:02"), false);
  assert.equal(ok(press("pointer", 1850), click(1850, 2), null), false);
  // The run started on this button.
  assert.equal(ok(press("pointer", 1850), click(1850, 2), mac), true);
  // A bare click (a screen reader, voice control): settled yes, not no.
  assert.equal(ok(null, click(1800, 0)), true);
  assert.equal(ok(null, click(1600, 0)), false);
  // A pointer press settled at both ends.
  assert.equal(ok(press("pointer", 1750), click(1800)), true);
  // The dashboard changed between press and click (rule 5).
  assert.equal(ok(press("pointer", 1750, { sends: "night" }), click(1800)), false);
  // Nothing to send.
  assert.equal(ok(null, click(1800, 0, null)), false);
  assert.equal(ok(null, null), false);
  // A button with no time at all is not settled.
  assert.equal(tablets.pressCounts({ press: null, click: click(9999, 0), movedAt: undefined, runStart: null, mac }), false);
});

// Rule 5: a dashboard the panel put on a button (the pre-pick, the editor's
// handover, a delete) makes it wait again; the person's own pick does not.
test("a pick the panel made restarts the wait; the person's own pick does not", () => {
  const start = new Map([
    ["aa:01", 100],
    ["aa:02", 100],
  ]);
  // The pre-pick arrives with the dashboards.
  const arrived = tablets.markPicks(start, new Map([["aa:01", null]]), new Map([["aa:01", "home"]]), null, 5000);
  assert.equal(arrived.get("aa:01"), 5000);
  assert.equal(arrived.get("aa:02"), 100);
  // A delete changed what it sends.
  const changed = tablets.markPicks(start, new Map([["aa:01", "night"]]), new Map([["aa:01", "home"]]), null, 6000);
  assert.equal(changed.get("aa:01"), 6000);
  // A button that becomes pressable (it had no time before).
  const came = tablets.markPicks(new Map(), null, new Map([["aa:03", "home"]]), null, 7000);
  assert.equal(came.get("aa:03"), 7000);
  // The person's own pick in that row: no new wait.
  const own = tablets.markPicks(start, new Map([["aa:01", null]]), new Map([["aa:01", "home"]]), "aa:01", 8000);
  assert.equal(own.get("aa:01"), 100);
  // The same as before, or nothing to send: nothing changes.
  const same = tablets.markPicks(start, new Map([["aa:01", "home"]]), new Map([["aa:01", "home"], ["aa:02", null]]), null, 9000);
  assert.deepEqual([...same], [...start]);
  // The map it was given stays as it was.
  assert.deepEqual([...start], [
    ["aa:01", 100],
    ["aa:02", 100],
  ]);
});

// Rule 11: the row asks the person to look at the tablet, with the six
// characters in a face of their own, and never offers the name as proof.
test("the check line is an instruction with the six characters", async () => {
  const line = rawStrings["tablets.device_line"];
  assert.match(line, /\{mac\}/);
  assert.match(line, /^Look at the tablet\./);
  assert.doesNotMatch(line, /^Its screen shows/);
  assert.doesNotMatch(line, /\{name\}/);
  const note = rawStrings["tablets.approve_note"];
  assert.match(note, /\{approve_it\}/);
  assert.doesNotMatch(note, /\{name\}/);
  const porch = { ...PORCH, mac: "30:ED:A0:12:EE:0E" };
  const [before, ending, after] = tablets.deviceLineParts(porch, t);
  assert.equal(ending, "12ee0e");
  assert.equal(before + ending + after, tablets.deviceLine(porch, t));
  assert.equal(after, ".");
  assert.deepEqual(tablets.deviceLineParts(null, t), ["", "", ""]);
  // The panel draws the ending in its own element, and the button names
  // both lines as its description.
  const panel = fs.readFileSync(path.join(root, "custom_components/apollo_tab/frontend/panel.js"), "utf8");
  assert.match(panel, /const code = el\("span", "tablet-mac", ending\);\n {4}code\.dataset\.test = "tablet-mac";/);
  assert.match(panel, /aria-describedby", `tablet-check-\$\{mac\} tablet-approve-note-\$\{mac\}`/);
  const { panelStyles } = await import("../../custom_components/apollo_tab/frontend/styles.js");
  assert.match(panelStyles, /\.tablet-mac \{[^}]*font-family: ui-monospace/);
});

// Recommended by the reviewer: a device that names itself after another
// tablet's address is warned about, and nothing is picked for it.
test("a new tablet whose name ends in another address is warned about and gets no pre-pick", () => {
  const liar = tablet("aa:bb:cc:00:00:07", "Apollo TAB-1 a1b2c3", { status: "new", approved: false, dashboard: null, suggested: null });
  const honest = { ...liar, name: "Apollo TAB-1 000007" };
  assert.equal(tablets.nameClaimsOtherEnding(liar), true);
  assert.equal(tablets.nameClaimsOtherEnding(honest), false);
  assert.equal(tablets.nameClaimsOtherEnding({ ...liar, name: "Porch tablet" }), false);
  assert.equal(tablets.nameClaimsOtherEnding({ ...liar, name: "Apollo TAB-1 A1B2C3" }), true);
  // Only new tablets are checked.
  assert.equal(tablets.nameClaimsOtherEnding({ ...liar, approved: true, status: "on_tablet" }), false);
  assert.equal(tablets.claimedEnding(liar), "a1b2c3");
  const base = { rows: [{ url_path: "home", title: "Home" }], unreadable: [], fresh: true, enabled: true };
  assert.equal(tablets.prepicked({ ...base, tablet: liar, waiting: new Set([liar.mac]) }), null);
  assert.equal(tablets.prepicked({ ...base, tablet: honest, waiting: new Set([honest.mac]) }), "home");
  assert.equal(t("tablets.name_warning", { ending: "a1b2c3" }).includes("a1b2c3"), true);
});

// Security review round 4: the warning line is narrower than the rule that
// stops a pre-pick. It needs a digit among the six characters, so plain
// words are not warned about, and it looks past trailing punctuation and
// invisible characters, which hid a real clash.
test("the name warning needs a digit and looks past punctuation and invisible characters", () => {
  const liar = tablet("aa:bb:cc:00:00:07", "Apollo TAB-1 a1b2c3", { status: "new", approved: false, dashboard: null, suggested: null });
  const named = (name) => ({ ...liar, name });
  assert.equal(tablets.nameWarns(liar), true);
  assert.equal(tablets.nameWarns(named("Apollo TAB-1 A1B2C3")), true);
  // Its own ending is no warning, also with a full stop after it.
  assert.equal(tablets.nameWarns(named("Apollo TAB-1 000007")), false);
  assert.equal(tablets.nameWarns(named("Apollo TAB-1 000007.")), false);
  // Six hex letters without a digit: a plain word.
  assert.equal(tablets.nameWarns(named("Front facade")), false);
  assert.equal(tablets.nameWarns(named("Bedded")), false);
  assert.equal(tablets.nameClaimsOtherEnding(named("Front facade")), true);
  // Trailing punctuation, spaces and invisible characters hide nothing.
  for (const tail of [".", "!", ")", " .", "​", "‌", "‍", "⁠", "﻿", "‎", ". ​"]) {
    const name = `Apollo TAB-1 a1b2c3${tail}`;
    assert.equal(tablets.nameWarns(named(name)), true, JSON.stringify(name));
    assert.equal(tablets.claimedEnding(named(name)), "a1b2c3", JSON.stringify(name));
  }
  // Seven hex characters in a row are no six-character ending.
  assert.equal(tablets.nameWarns(named("Apollo TAB-1 9a1b2c3")), false);
  assert.equal(tablets.nameWarns(named("Porch tablet")), false);
  assert.equal(tablets.claimedEnding(named("Porch tablet")), "");
  // Only new tablets are checked.
  assert.equal(tablets.nameWarns({ ...liar, approved: true, status: "on_tablet" }), false);
  assert.equal(tablets.nameWarns(null), false);
  // The pre-pick keeps the broad rule and also refuses every name the
  // warning line is shown for.
  const base = { rows: [{ url_path: "home", title: "Home" }], unreadable: [], fresh: true, enabled: true };
  const pick = (name) => tablets.prepicked({ ...base, tablet: named(name), waiting: new Set([liar.mac]) });
  assert.equal(pick("Front facade"), null);
  assert.equal(pick("Apollo TAB-1 a1b2c3."), null);
  assert.equal(pick("Apollo TAB-1 a1b2c3​"), null);
  assert.equal(pick("Apollo TAB-1 000007"), "home");
  // The panel draws the warning by the narrow rule.
  const panel = fs.readFileSync(path.join(root, "custom_components/apollo_tab/frontend/panel.js"), "utf8");
  assert.match(panel, /if \(nameWarns\(tablet\)\) \{\n {6}const warning = el\("p", "notice tablet-name-warning"/);
  assert.doesNotMatch(panel, /nameClaimsOtherEnding/);
});

// Security review round 4: a pick does not outlive the visit, also when the
// same panel element is taken out of the page and put back.
test("taking the panel out of the page drops every pick", () => {
  const panel = fs.readFileSync(path.join(root, "custom_components/apollo_tab/frontend/panel.js"), "utf8");
  const start = panel.indexOf("  disconnectedCallback() {");
  assert.ok(start > 0, "no disconnectedCallback");
  const body = panel.slice(start, panel.indexOf("\n  }\n", start));
  assert.match(body, /\n {4}this\._chosen\.clear\(\);\n/);
  // _setPath clears it too, for every move to another screen.
  const setPath = panel.slice(panel.indexOf("  _setPath(path) {"), panel.indexOf("\n  }\n", panel.indexOf("  _setPath(path) {")));
  assert.match(setPath, /\n {4}this\._chosen\.clear\(\);\n/);
});
