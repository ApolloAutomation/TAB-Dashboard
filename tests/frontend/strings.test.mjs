import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as model from "../../custom_components/apollo_tab/frontend/model.js";

const { GROUP_IDS, PAGE_ICONS } = model;

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const frontend = path.join(root, "custom_components/apollo_tab/frontend");
const stringsPath = path.join(root, "custom_components/apollo_tab/library/strings.json");

function readStrings() {
  return JSON.parse(fs.readFileSync(stringsPath, "utf8"));
}

// The warning codes the converter can produce (the same list as
// warnings.test.mjs), plus the two the editor adds itself.
const WARNING_CODES = [
  "invalid_options",
  "strategy_not_supported",
  "view_not_sections",
  "view_extras_ignored",
  "columns_differ",
  "section_not_grid",
  "nested_section_ignored",
  "visibility_ignored",
  "not_tab_element",
  "unknown_component",
  "needs_approval",
  "invalid_card",
  "params_incomplete",
  "element_clipped",
  "card_too_wide",
  "card_too_tall",
  "section_split",
  "over_budget_charts",
  "over_budget_arcs",
  "over_budget_gradients",
  "too_many_pages",
  "too_many_nav",
  "left_out",
  "old_preview",
];

test("strings file is a flat map of non-empty strings", () => {
  const strings = readStrings();
  assert.equal(typeof strings, "object");
  assert.ok(strings !== null && !Array.isArray(strings));
  const entries = Object.entries(strings);
  assert.ok(entries.length > 0);
  for (const [key, value] of entries) {
    assert.equal(typeof value, "string", key);
    assert.ok(value.trim().length > 0, key);
  }
});

test("every string key used in the frontend exists", () => {
  const strings = readStrings();
  const missing = [];
  for (const name of fs.readdirSync(frontend).filter((file) => file.endsWith(".js"))) {
    const source = fs.readFileSync(path.join(frontend, name), "utf8");
    for (const match of source.matchAll(/\bt\(\s*"([^"]+)"/g)) {
      if (!Object.hasOwn(strings, match[1])) {
        missing.push(`${name}: ${match[1]}`);
      }
    }
  }
  assert.deepEqual(missing, []);
});

// Keys the frontend builds from a code, a group id or a device kind.
const DYNAMIC_PREFIXES = ["warn.", "group.", "pick.which."];

test("every string in the file is used by the frontend", () => {
  const strings = readStrings();
  const source = fs
    .readdirSync(frontend)
    .filter((file) => file.endsWith(".js"))
    .map((file) => fs.readFileSync(path.join(frontend, file), "utf8"))
    .join("\n");
  const unused = Object.keys(strings).filter(
    (key) => !source.includes(`"${key}"`) && !DYNAMIC_PREFIXES.some((prefix) => key.startsWith(prefix)),
  );
  assert.deepEqual(unused, []);
});

test("dynamic string families are complete", () => {
  const strings = readStrings();
  const keys = [
    ...WARNING_CODES.map((code) => `warn.${code}`),
    ...GROUP_IDS.map((id) => `group.${id}`),
    "pick.which.other",
  ];
  assert.deepEqual(
    keys.filter((key) => !Object.hasOwn(strings, key)),
    [],
  );
});

// The icon picker names each page icon in plain words, never by its icon id.
test("every page icon has its own plain name", () => {
  const strings = readStrings();
  const keys = model.PAGE_ICON_NAMES || {};
  assert.deepEqual(Object.keys(keys).sort(), [...PAGE_ICONS].sort());
  const names = PAGE_ICONS.map((icon) => strings[keys[icon]]);
  assert.deepEqual(
    PAGE_ICONS.filter((icon, index) => typeof names[index] !== "string"),
    [],
  );
  assert.equal(new Set(names).size, names.length, "two icons share a name");
  for (const name of names) {
    assert.match(name, /^[A-Z][^-]*$/, name);
  }
});

// A removed card that controlled several devices: a card picked for them
// may take only one, so the picker promises no more than that, and the rest
// are offered again after the pick.
test("the picker promises several devices no more than a card can take", () => {
  const strings = readStrings();
  const one = strings["picker.intro_for"];
  const many = strings["picker.intro_for_many"];
  assert.ok(one.includes("{device} straight away"), one);
  assert.equal(typeof many, "string");
  assert.ok(many.includes("{device}"), many);
  assert.ok(!many.includes("straight away"), `"${many}" promises every device straight away`);
  assert.match(many, /as many of them as it can take/);
  assert.match(many, /a card for the rest/);
  assert.equal(strings["toast.card_added_for"], "Card added. Add a TAB-1 card for {device}.");
  const picker = fs.readFileSync(path.join(frontend, "picker.js"), "utf8");
  assert.match(picker, /entities\.length > 1 \? "picker\.intro_for_many" : "picker\.intro_for"/);
});

// The banner after the connection came back says what is known: the change
// is not saved, and the dashboard may have been made again, not that
// someone saved another version.
test("the banner after a lost connection says why it asks", () => {
  const strings = readStrings();
  assert.equal(strings["conflict.unsure_title"], "Your change is not saved yet");
  const text = strings["conflict.unsure_text"];
  assert.match(text, /connection to Home Assistant was lost/);
  assert.match(text, /made a new one in its place/);
  assert.ok(!text.includes("saved a different version"), text);
});

// Words a first-time user reads: what the sidebar and community cards really
// do, a device button that says what it does, and what happens on leaving a
// change that is not saved.
test("the editor's words say what really happens", () => {
  const strings = readStrings();
  const sidebar = strings["sidebar.text"];
  assert.match(sidebar, /opens as a normal Home Assistant dashboard/);
  assert.match(sidebar, /Edit button there offers cards the tablet cannot show/);
  const folder = strings["advanced.folder_text"];
  assert.match(folder, /^Community cards are TAB-1 cards made by other people\./);
  assert.match(folder, /do not work on the tablet/);
  assert.equal(strings["form.choose_device"], "Choose");
  assert.equal(strings["form.change_device"], "Change");
  const form = fs.readFileSync(path.join(frontend, "card-form.js"), "utf8");
  assert.match(form, /ariaLabel: `\$\{action\}: \$\{label\}`/);
  assert.match(strings["picker.none_help"], /^Try the name of a card or a kind of device/);
  assert.equal(strings["leave.title"], "Your last change is not saved yet");
  assert.match(strings["leave.text_error"], /keeps trying in the background while this browser page stays open/);
  assert.match(strings["leave.text_choice"], /waits until you choose which version to keep/);
  assert.match(strings["home.kept_waiting"], /waiting for your choice/);
  assert.match(strings["home.kept_unsaved"], /not saved yet/);
});

// "How to write a card" opens the guide itself, which talks about cards
// before it names the file format's own terms.
test("the card guide link opens the guide, which starts with cards", () => {
  const panel = fs.readFileSync(path.join(frontend, "panel.js"), "utf8");
  assert.match(panel, /const CARD_GUIDE_URL = `\$\{GUIDE_URL\}\/blob\/main\/docs\/components\.md`;/);
  assert.match(panel, /guide\.href = CARD_GUIDE_URL;/);
  const guide = fs.readFileSync(path.join(root, "docs/components.md"), "utf8");
  const [title, opening] = guide.split("\n\n");
  assert.equal(title, "# Writing a card");
  assert.match(opening, /^A card for the TAB-1 tablet is a small YAML file\./);
  assert.ok(opening.indexOf("card") < opening.indexOf("Component"), opening);
});

// Dashboards now reach the tablets, so no text in the panel may still say
// they do not.
test("no text says dashboards are not sent to tablets", () => {
  const strings = readStrings();
  for (const key of ["home.not_sent", "home.tablets_none", "home.tablets_some", "editor.tablet_note", "preview.not_sent"]) {
    assert.equal(Object.hasOwn(strings, key), false, `${key} is still in the strings`);
  }
  const offenders = Object.entries(strings)
    .filter(([, value]) => /not sent to tablets|not been released/i.test(value))
    .map(([key]) => key);
  assert.deepEqual(offenders, []);
  for (const name of fs.readdirSync(frontend).filter((file) => file.endsWith(".js"))) {
    const source = fs.readFileSync(path.join(frontend, name), "utf8");
    assert.ok(!/not sent to tablets/i.test(source), `${name} still says dashboards are not sent`);
  }
});

// The tablet texts are read by people who never set up ESPHome by hand:
// no names of Home Assistant's insides, and "tablet software" rather than
// firmware. Only two lines name ESPHome, as the place to go in Home
// Assistant: the encryption hint, where the setting is, and the steps for
// a key, which press Reload under Settings > Devices & services > ESPHome.
test("the tablet texts avoid jargon", () => {
  const strings = readStrings();
  const jargon = /\b(entity|entities|integration|ESPHome|hash|engine|firmware|url_path|MAC|select|sensor|Lovelace|payload|websocket)\b/i;
  const keys = Object.keys(strings).filter((key) => key.startsWith("tablets.") || key.startsWith("editor.on_tablet_"));
  assert.ok(keys.length >= 45, `only ${keys.length} tablet texts`);
  const plain = (key) => strings[key].replace(/\{[^}]*\}/g, "");
  const named = new Set(["tablets.needs_encryption", "tablets.reauth_key"]);
  const offenders = keys.filter((key) => !named.has(key)).filter((key) => jargon.test(plain(key)));
  assert.deepEqual(offenders, []);
  // Where ESPHome is named, it is a place to go, never a word for the tablet.
  assert.match(strings["tablets.reauth_key"], /Settings > Devices & services > ESPHome, open the tablet's menu/);
  assert.equal(plain("tablets.reauth_key").replace("Settings > Devices & services > ESPHome", "").match(jargon), null);
  // The line that helps an admin tell which device a new tablet is: an
  // instruction, with the six characters the tablet's own screen shows.
  assert.equal(
    strings["tablets.device_line"],
    "Before you turn it on, check that the name on the tablet's screen ends in {mac}.",
  );
  assert.equal(
    strings["tablets.device_before"],
    "If it still shows {dashboard}, its old dashboard, its name is not on its screen. Check that it shows {dashboard} and that its values no longer change.",
  );
  assert.match(strings["tablets.needs_encryption"], /in ESPHome\.$/);
  assert.ok(!/\b(firmware|engine|integration)\b/i.test(strings["tablets.needs_encryption"]));
  // The design's own sentences, word for word.
  assert.equal(strings["tablets.none"], "No TAB-1 tablet found in Home Assistant yet. Power the tablet on. If it asks for Wi-Fi, join \"Apollo TAB1 Hotspot\" from a phone and pick your Wi-Fi. Then add it in Settings > Devices & services, where it shows up by itself, and turn it on here. You can still build dashboards.");
  assert.equal(strings["tablets.make_first"], "Make a dashboard first.");
  assert.equal(strings["editor.on_tablet_helper"], "To show something else on a tablet, pick it for that tablet on the Home screen.");
  assert.equal(strings["editor.on_tablet_none"], "No tablets yet.");
  assert.equal(strings["editor.on_tablet_nowhere"], "Not shown on a tablet yet");
});

test("no string uses the old jargon", () => {
  const strings = readStrings();
  const jargon = /\b(element|elements|Component|Components|view|views|section|sections|entity|entities)\b/;
  const offenders = Object.entries(strings)
    .filter(([, value]) => jargon.test(value.replace(/\{[^}]*\}/g, "")))
    .map(([key]) => key);
  assert.deepEqual(offenders, []);
});
