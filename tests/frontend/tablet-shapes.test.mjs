// The panel's stand-in Home Assistant (tests/harness/mock-hass.js) answers
// the tablet commands in the shapes of tests/harness/tablet-shapes.json, and
// the panel's word lists cover every status and reason in it. The
// integration is checked against the same file by tests/test_tablet_shapes.py,
// so the panel's tests and journey cannot drift from the real messages.
import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { format } from "../../custom_components/apollo_tab/frontend/logic.js";
import * as tablets from "../../custom_components/apollo_tab/frontend/tablets.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const SHAPES = JSON.parse(fs.readFileSync(path.join(root, "tests/harness/tablet-shapes.json"), "utf8"));
const FIXTURES = JSON.parse(fs.readFileSync(path.join(root, "tests/harness/fixtures.json"), "utf8"));
const STRINGS = JSON.parse(fs.readFileSync(path.join(root, "custom_components/apollo_tab/library/strings.json"), "utf8"));
// The tablet's own words, from the shared contract (CONTRACT.md section 11).
const SCREENS = JSON.parse(fs.readFileSync(path.join(root, "tests/contract/screens.json"), "utf8"));

// What the stand-in needs from a browser: its two stand-in elements are
// defined already, and the dashboards list converts through a fetch.
globalThis.customElements ??= { get: () => true };
globalThis.location ??= { origin: "http://harness.invalid", search: "" };
globalThis.fetch = async () => ({
  ok: true,
  json: async () => ({ layout: { pages: [{}], hash: "0123456789abcdef" }, warnings: [] }),
});
const { createMockHass } = await import("../harness/mock-hass.js");

const flush = async () => {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
  }
};

// ---------------------------------------------------------------- the checks

function typeOk(value, name) {
  switch (name) {
    case "integer":
      return Number.isInteger(value);
    case "boolean":
      return typeof value === "boolean";
    case "string":
      return typeof value === "string";
    case "array":
      return Array.isArray(value);
    case "null":
      return value === null;
    default:
      throw new Error(`unknown type ${name} in the shapes file`);
  }
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

// Like Python's sorted(): by code point.
function compare(a, b) {
  const left = [...a];
  const right = [...b];
  for (let index = 0; index < Math.min(left.length, right.length); index += 1) {
    const step = left[index].codePointAt(0) - right[index].codePointAt(0);
    if (step) return step;
  }
  return left.length - right.length;
}

function compareKeys(a, b) {
  for (let index = 0; index < a.length; index += 1) {
    const step = compare(a[index], b[index]);
    if (step) return step;
  }
  return 0;
}

function assertSorted(where, keys) {
  const sorted = [...keys].sort(compareKeys);
  assert.deepEqual(keys, sorted, `${where} is out of order`);
}

function checkFields(where, value, fields) {
  assert.ok(isObject(value), `${where} is not an object`);
  assert.deepEqual(Object.keys(value).sort(), Object.keys(fields).sort(), `${where} has other keys`);
  for (const [key, rule] of Object.entries(fields)) {
    const item = value[key];
    const types = Array.isArray(rule.type) ? rule.type : [rule.type];
    assert.ok(types.some((name) => typeOk(item, name)), `${where}.${key}: ${JSON.stringify(item)}`);
    if (typeof item === "string" && rule.pattern) {
      assert.match(item, new RegExp(rule.pattern), `${where}.${key}`);
    }
    if (typeof item === "string" && rule.values) {
      assert.ok(SHAPES[rule.values].includes(item), `${where}.${key}: ${item}`);
    }
    if (Array.isArray(item) && rule.items === "mac") {
      for (const mac of item) {
        assert.match(mac, new RegExp(SHAPES.tablet.mac.pattern), `${where}.${key}`);
      }
    }
  }
}

function shortNames(name) {
  const { strip, tag } = SHAPES.short_name;
  const without = (text) => (text.toLowerCase().endsWith(strip) && text.length > strip.length ? text.slice(0, -strip.length) : text);
  const allowed = new Set([without(name)]);
  const found = new RegExp(tag).exec(name);
  if (found) {
    allowed.add(without(name.slice(0, found.index)) + found[0]);
  }
  return allowed;
}

function checkTablet(where, tablet) {
  checkFields(where, tablet, SHAPES.tablet);
  const { status, reason, retry } = tablet;
  const reasons = SHAPES.reasons[status];
  if (reasons) {
    assert.ok(reasons.includes(reason), `${where}: ${status} with the reason "${reason}"`);
  } else {
    assert.equal(reason, "", `${where}: ${status} with the reason "${reason}"`);
  }
  if (status !== "failed" || SHAPES.no_retry.includes(reason)) {
    assert.equal(retry, false, `${where}: ${status} ${reason} with retry`);
  }
  if (status === "no_dashboard") {
    assert.equal(tablet.dashboard, null, where);
  }
  // A tablet no admin approved shows nothing and is the only "new" one.
  assert.equal(status === "new", tablet.approved === false, `${where}: ${status}, approved ${tablet.approved}`);
  if (!tablet.approved) {
    assert.equal(tablet.dashboard, null, where);
    assert.equal(tablet.paired, false, where);
    assert.equal(tablet.input, "not_paired", where);
  } else {
    assert.equal(tablet.suggested, null, where);
  }
  assert.ok(shortNames(tablet.name).has(tablet.short_name), `${where}: short name "${tablet.short_name}"`);
  // The name Repairs uses comes with what it waits for, and only then.
  assert.equal(tablet.reauth === null, tablet.reauth_name === null, `${where}: reauth ${tablet.reauth}, ${tablet.reauth_name}`);
}

function checkTabletList(where, list) {
  assert.ok(Array.isArray(list), where);
  list.forEach((tablet, index) => checkTablet(`${where}[${index}]`, tablet));
  assertSorted(
    where,
    list.map((tablet) => [tablet.name.toLowerCase(), tablet.mac]),
  );
  assert.equal(new Set(list.map((tablet) => tablet.mac)).size, list.length, `${where}: a MAC twice`);
}

function checkDashboards(where, result, all) {
  const list = all.filter((tablet) => tablet.approved);
  result.dashboards.forEach((dashboard, index) => {
    checkFields(`${where}[${index}]`, dashboard, SHAPES.dashboard);
    const shown = list
      .filter((tablet) => tablet.dashboard === dashboard.url_path)
      .map((tablet) => tablet.mac)
      .sort(compare);
    assert.deepEqual(dashboard.shown_on, shown, `${where}[${index}].shown_on`);
  });
  assertSorted(
    where,
    result.dashboards.map((dashboard) => [dashboard.title.toLowerCase(), dashboard.url_path]),
  );
  assert.equal(result.tablets, list.length);
  assert.equal(result.sent_to_tablets, list.some((tablet) => tablet.status === "on_tablet"));
}

function checkValue(where, kind, value) {
  if (kind === "tablet") checkTablet(where, value);
  else if (kind === "tablet_list") checkTabletList(where, value);
  else if (kind === "dashboard_list") assert.ok(Array.isArray(value), where);
  else if (["integer", "boolean", "string"].includes(kind)) assert.ok(typeOk(value, kind), `${where}: ${value}`);
  else assert.equal(value, kind, where);
}

function checkResult(command, result) {
  const shape = SHAPES.commands[command].result;
  if (shape === null) {
    assert.equal(result, null, command);
    return;
  }
  assert.ok(isObject(result), command);
  assert.deepEqual(Object.keys(result).sort(), Object.keys(shape).sort(), `${command} result keys`);
  for (const [key, kind] of Object.entries(shape)) {
    checkValue(`${command}.${key}`, kind, result[key]);
  }
}

function checkEvent(command, event) {
  const shape = SHAPES.commands[command].events[event?.type];
  assert.ok(shape, `${command} sent ${JSON.stringify(event)}`);
  assert.deepEqual(Object.keys(event).sort(), Object.keys(shape).sort(), `${command} event keys`);
  for (const [key, kind] of Object.entries(shape)) {
    checkValue(`${command} event.${key}`, kind, event[key]);
  }
}

async function rejection(promise) {
  try {
    await promise;
  } catch (error) {
    return { code: error.code, message: error.message };
  }
  assert.fail("the command did not fail");
}

// ----------------------------------------------------------------- the tests

test("the shapes file's example passes its own rules", () => {
  checkTablet("example", SHAPES.example);
  assert.throws(() => checkTablet("extra key", { ...SHAPES.example, allow_sensitive: false }));
  assert.throws(() => checkTablet("engine null", { ...SHAPES.example, engine: null }));
  assert.throws(() => checkTablet("reason", { ...SHAPES.example, reason: "timeout" }));
  assert.throws(() => checkTablet("retry", { ...SHAPES.example, status: "failed", reason: "too_big", retry: true }));
  assert.throws(() => checkTablet("short name", { ...SHAPES.example, short_name: "Kitchen tablet" }));
  const fresh = { ...SHAPES.example, status: "new", approved: false, dashboard: null, paired: false, input: "not_paired" };
  checkTablet("new", fresh);
  checkTablet("new with a suggestion", { ...fresh, suggested: "tab-home" });
  assert.throws(() => checkTablet("new but approved", { ...fresh, approved: true }));
  assert.throws(() => checkTablet("not approved, not new", { ...SHAPES.example, approved: false }));
  assert.throws(() => checkTablet("new with a dashboard", { ...fresh, dashboard: "tab-home" }));
  assert.throws(() => checkTablet("new and paired", { ...fresh, paired: true }));
  assert.throws(() => checkTablet("approved with a suggestion", { ...SHAPES.example, suggested: "tab-home" }));
  checkTablet("tagged", { ...SHAPES.example, name: "Hall tablet (ee02)", short_name: "Hall (ee02)" });
  for (const reauth of SHAPES.reauths) {
    checkTablet(`reauth ${reauth}`, { ...SHAPES.example, reauth, reauth_name: "Apollo TAB-1 ddee01" });
    checkTablet(`new, reauth ${reauth}`, { ...fresh, reauth, reauth_name: "Apollo TAB-1 ddee01" });
  }
  assert.throws(() => checkTablet("unknown reauth", { ...SHAPES.example, reauth: "later", reauth_name: "Kitchen" }));
  assert.throws(() => checkTablet("reauth without a name", { ...SHAPES.example, reauth: "erased" }));
  assert.throws(() => checkTablet("a name without reauth", { ...SHAPES.example, reauth_name: "Kitchen" }));
  assert.throws(() => checkTablet("a padded name", { ...SHAPES.example, reauth: "key", reauth_name: " Kitchen" }));
});

test("the panel knows every status and reason of the shapes file, with words", () => {
  assert.deepEqual(tablets.TABLET_STATUSES, SHAPES.statuses);
  assert.deepEqual(tablets.TABLET_REASONS, SHAPES.reasons);
  for (const status of SHAPES.statuses) {
    for (const reason of SHAPES.reasons[status] || [""]) {
      for (const retry of [false, true]) {
        const fresh = status === "new";
        const tablet = {
          ...SHAPES.example,
          status,
          reason,
          retry,
          approved: !fresh,
          dashboard: status === "no_dashboard" || fresh ? null : "tab-home",
        };
        const home = tablets.homeWordsKey(tablet);
        assert.ok(home && STRINGS[home], `no words on Home for ${status} ${reason}`);
        // A new tablet shows nothing, so the editor has no line for it.
        if (status !== "no_dashboard" && !fresh) {
          const line = tablets.lineWordsKey(tablet);
          assert.ok(line && STRINGS[line], `no editor line for ${status} ${reason}`);
        }
      }
    }
  }
  for (const input of SHAPES.inputs) {
    const tablet = { ...SHAPES.example, input };
    const note = tablets.inputNoteKey(tablet);
    assert.ok(input === "ok" ? note === null : note && STRINGS[note], `no line about taps for ${input}`);
  }
});

for (const set of ["none", "three", "no-engine", "new", "two-new", "all"]) {
  test(`the stand-in's tablets (${set}) have the shapes of the integration`, async () => {
    const hass = createMockHass(FIXTURES, { tablets: set, night: true });
    hass.sendDelay(0);
    const events = [];
    const stop = await hass.connection.subscribeMessage((event) => events.push(event), {
      type: "apollo_tab/tablets/subscribe",
    });
    await flush();
    assert.equal(events.length, 1, "no first event at once");

    const listed = await hass.callWS({ type: "apollo_tab/tablets" });
    checkResult("apollo_tab/tablets", listed);
    const dashboards = await hass.callWS({ type: "apollo_tab/dashboards" });
    checkResult("apollo_tab/dashboards", dashboards);
    checkDashboards("dashboards", dashboards, listed.tablets);

    const commands = SHAPES.commands;
    const approved = listed.tablets.find((tablet) => tablet.approved);
    const fresh = listed.tablets.find((tablet) => !tablet.approved);
    for (const [name, shape] of Object.entries(commands)) {
      for (const [code, message] of Object.entries(shape.errors || {})) {
        const macs = { not_found: "aa:00:00:00:00:00", not_approved: fresh?.mac };
        const known = Object.hasOwn(macs, code) ? macs[code] : approved?.mac;
        if (!known) continue;
        const all = { type: name, mac: known, url_path: "nope" };
        const sent = Object.fromEntries(["type", ...shape.send].map((key) => [key, all[key]]));
        assert.deepEqual(await rejection(hass.callWS(sent)), { code, message }, `${name} ${code}`);
      }
    }
    for (const name of SHAPES.removed) {
      const answer = await rejection(hass.callWS({ type: name, mac: "aa:bb:cc:dd:ee:01" }));
      assert.equal(answer.code, SHAPES.unknown_command, name);
    }

    if (fresh) {
      // A plain assign leaves a new tablet as it is (the errors above);
      // "Turn on with this dashboard" sends approve and turns it on.
      const first = dashboards.dashboards[0];
      const refused = await rejection(
        hass.callWS({ type: "apollo_tab/tablet/assign", mac: fresh.mac, url_path: first.url_path, approve: false }),
      );
      assert.equal(refused.code, "not_approved");
      const still = (await hass.callWS({ type: "apollo_tab/tablets" })).tablets.find((tablet) => tablet.mac === fresh.mac);
      assert.equal(still.approved, false);
      assert.deepEqual(Object.keys(SHAPES.commands["apollo_tab/tablet/assign"].optional), ["approve"]);
      const turnedOn = await hass.callWS({
        type: "apollo_tab/tablet/assign",
        mac: fresh.mac,
        url_path: first.url_path,
        approve: true,
      });
      checkResult("apollo_tab/tablet/assign", turnedOn);
      assert.equal(turnedOn.tablet.approved, true);
      assert.equal(turnedOn.tablet.dashboard, first.url_path);
      assert.notEqual(turnedOn.tablet.status, "new");
      const counted = await hass.callWS({ type: "apollo_tab/dashboards" });
      assert.equal(counted.tablets, dashboards.tablets + 1);
      assert.ok(counted.dashboards[0].shown_on.includes(fresh.mac));
    }

    if (approved) {
      // Assign and pair, by either form of the MAC.
      const target = listed.tablets.find((tablet) => tablet.approved && tablet.status !== "no_dashboard") || approved;
      const other = dashboards.dashboards.find((dashboard) => dashboard.url_path !== target.dashboard);
      const assigned = await hass.callWS({
        type: "apollo_tab/tablet/assign",
        mac: target.mac.toUpperCase(),
        url_path: other.url_path,
      });
      checkResult("apollo_tab/tablet/assign", assigned);
      assert.equal(assigned.tablet.dashboard, other.url_path);
      const paired = await hass.callWS({ type: "apollo_tab/tablet/pair", mac: target.mac.replaceAll(":", "") });
      checkResult("apollo_tab/tablet/pair", paired);
      await flush();
      await new Promise((resolve) => setTimeout(resolve, 5));
      await flush();
      const after = await hass.callWS({ type: "apollo_tab/tablets" });
      checkResult("apollo_tab/tablets", after);
      checkDashboards("dashboards", await hass.callWS({ type: "apollo_tab/dashboards" }), after.tablets);
    }

    hass.unloadIntegration();
    await flush();
    events.forEach((event) => checkEvent("apollo_tab/tablets/subscribe", event));
    assert.deepEqual(events.at(-1), { type: "not_loaded" });
    stop();
    hass.finishSends();
  });
}

test("docs/tablets.md quotes the panel's own words", () => {
  const docs = fs.readFileSync(path.join(root, "docs/tablets.md"), "utf8");
  const table = new Set(
    docs
      .split("\n")
      .filter((line) => line.startsWith("| ") && !line.startsWith("| Words"))
      .map((line) => line.split("|")[1].trim()),
  );
  for (const key of [...Object.values(tablets.HOME_WORDS), "tablets.status.new_no_dashboard"]) {
    assert.ok(table.has(STRINGS[key]), `the status table lacks "${STRINGS[key]}"`);
  }
  for (const key of ["tablets.shows", "tablets.title", "editor.on_tablet_name", "settings.heading"]) {
    assert.ok(docs.includes(`"${STRINGS[key]}"`), `docs/tablets.md does not quote "${STRINGS[key]}"`);
  }
  assert.ok(docs.includes("Turn on encryption for it in ESPHome"), "the encryption hint");
  assert.ok(STRINGS["tablets.needs_encryption"].includes("Turn on encryption for it in ESPHome"));
  assert.ok(docs.includes("It is still being set up"), "the set-up hint");
  assert.ok(STRINGS["tablets.not_paired"].includes("It is still being set up"));
  for (const message of Object.values(SHAPES.commands["apollo_tab/tablet/assign"].errors)) {
    assert.ok(docs.includes(`"${message}"`), `docs/tablets.md does not quote "${message}"`);
  }
  // Product owner: an add-on with an admin's long-lived token acts as that
  // admin and can turn a tablet on; only the Supervisor's own access is an
  // automation. The guide and the README say so.
  const flat = (text) => text.replace(/\s+/g, " ");
  assert.match(flat(docs), /add-on that you set up with an admin's long-lived access token acts as that admin: it can turn on a new tablet/);
  assert.match(flat(docs), /Only the Supervisor's own access counts as an automation\./);
  const readme = flat(fs.readFileSync(path.join(root, "README.md"), "utf8"));
  assert.match(readme, /add-on set up with an admin's long-lived access token acts as that admin and can\./);
  assert.doesNotMatch(readme, /Automations and add-ons cannot turn on/);
  // The erased tablet's line and where it leads.
  assert.ok(flat(docs).includes('"Authentication expired for Apollo TAB-1 ddee01"'), "the Repairs name");
  assert.ok(docs.includes(`"${STRINGS["tablets.open_repairs"]}"`), "the Repairs link");
  // Round 8: the same check as the panel's line before anyone confirms,
  // and one set of steps for the question for a key, as in the panel.
  // Round 9: never a restart alone; a yes gives back the key Home Assistant
  // kept, not a new one. Round 10: the check is the tablet's own screen
  // ("Add this tablet in Home Assistant", which only a tablet without its
  // key shows), not a time and not the steps for a key; "Setup not
  // finished" means restart it first; and the steps for a key are only for
  // an admin who erased it and sees "Setup not finished". Round 11: the
  // screen after the hold-the-screen erase is "Confirm this tablet in Home
  // Assistant" (the firmware's erase mark), "Add this tablet in Home
  // Assistant" only after an erase over USB; the words come from the shared
  // contract, and no other device can make a tablet with its key show them.
  const { erased, add, closed } = SCREENS.waiting;
  const both = `"${erased.headline}" (or "${add.headline}" after a USB erase)`;
  const guide = flat(docs);
  assert.ok(guide.includes('"remove the encryption key and allow unencrypted connections"'), "the dialog's words");
  // The panel's line, quoted as a block.
  const quoted = flat(docs.replace(/^> /gm, ""));
  assert.ok(quoted.includes(format(STRINGS["tablets.reauth_erased"], { name: "Apollo TAB-1 ddee01" })), "the panel's line, quoted");
  const erasedPart = flat(docs.slice(docs.indexOf("A tablet that was set up before and then erased"), docs.indexOf("If Home Assistant asks for a key instead")));
  for (const sentence of [
    "The tablet's own screen is the check.",
    `Confirm that question only if you erased this tablet yourself and its screen now says "${erased.headline}" under its name.`,
    `A tablet erased by holding a finger on its screen right after power-on shows that until it has its key again, with "${format(erased.step, { name: "Apollo TAB-1 ddee01" })}" under it.`,
    `A tablet erased over USB says "${add.headline}" instead, which counts the same.`,
    "Only a tablet without its key shows either, and another device on your network cannot make a tablet that still has its key show them.",
    "At most it can make the screen show something else for a while, and then you do not confirm.",
    "A restart alone, for example after a power cut, is never a reason to confirm.",
    `If its screen says "${closed.headline}" and "${closed.step}", its 15 minutes ran out: restart it, and confirm once it shows one of those two screens again.`,
    "Home Assistant then gives the tablet back the key it kept for it: the same key the tablet had before the erase, not a new one.",
    `It takes the key only in the 15 minutes after it starts, which is why its screen has to say ${both} when you confirm.`,
    "If you did not erase the tablet, do not confirm, and check the tablet.",
    `A tablet erased by holding its screen shows its waiting screen with its name, for example "Apollo TAB-1 ddee01": "${SCREENS.waiting.hotspot.headline}" until it is on your Wi-Fi, then "${erased.headline}".`,
    `Its last line, "${erased.step2}", is only for a Home Assistant that never had the tablet.`,
    "Yours had it and asks in Repairs, so do not add a device there: one that shows up by the tablet's name could be another one.",
    `A tablet that shows its dashboard or "${SCREENS.waiting.wait_ha.headline}" still has its key and was not erased.`,
    // Why the screen and not the question: the full story behind the
    // panel's "do not confirm".
    "Another device on your network can pretend to be the tablet and ask the same question, and confirming would hand it the key Home Assistant kept for the tablet.",
  ]) {
    assert.ok(erasedPart.includes(sentence), `the erased part lacks: ${sentence}`);
  }
  // No yes by the clock or by the steps alone, and never the claim that
  // nothing on the network can change the screen (a device that connects
  // to a tablet without its key can, for a while).
  assert.doesNotMatch(erasedPart, /last 15 minutes|steps for a key|erase it again|longer ago|just did|cannot change what the tablet's screen says/);
  // An erased tablet's screen, as the tablet says it: never "Add this
  // tablet" for the hold-the-screen erase.
  assert.doesNotMatch(erasedPart, /(holding|hold)[^.]*"Add this tablet/);
  assert.doesNotMatch(guide, /new key right after|erased or restarted|last few minutes|steps for a key|because you erased the tablet yourself and just did/);
  assert.ok(guide.includes(`"${STRINGS["tablets.status.repairs"]}"`), "the status while Home Assistant waits");
  // The steps for a key, each word for word and nothing else in the list:
  // closing (an empty key and Submit do not work with Home Assistant's
  // dialog), the restart that opens the tablet's 15 minutes, then Reload.
  const keyPart = docs.slice(docs.indexOf("If Home Assistant asks for a key instead"), docs.indexOf("A tap on the tablet follows"));
  assert.deepEqual(numberedSteps(keyPart), [
    "1. Close that question without entering a key.",
    "2. Restart the tablet.",
    "3. Within 15 minutes, go to Settings > Devices & services > ESPHome, open the tablet's menu (three dots) and press Reload.",
  ]);
  assert.doesNotMatch(flat(keyPart), /empty|Submit|enter no key/);
  // Who does the steps: the check is right before them, and nothing else is.
  const beforeSteps = flat(keyPart.slice(0, keyPart.search(/^1\. /m))).trim();
  assert.ok(
    beforeSteps.endsWith('Do not enter a key there. If you erased this tablet yourself and its screen says "Setup not finished":'),
    `who does the steps: ${beforeSteps}`,
  );
  const afterSteps = flat(keyPart.slice(keyPart.search(/^3\. /m)));
  for (const sentence of [
    `Confirm it as above, once the tablet's screen says ${both}.`,
    `If you did not erase the tablet, or its screen does not say "${closed.headline}", do not do these steps: check the tablet.`,
    `A tablet that still has its key never says "${closed.headline}".`,
  ]) {
    assert.ok(afterSteps.includes(sentence), `after the steps: ${sentence}`);
  }
  // The panel gives the same steps in the same order, after the same check.
  const line = STRINGS["tablets.reauth_key"];
  const at = ['its screen says "Setup not finished"', "close the question", "restart the tablet", "within 15 minutes", "press Reload"].map((words) =>
    line.indexOf(words),
  );
  assert.ok(at.every((index, i) => index >= 0 && (i === 0 || index > at[i - 1])), JSON.stringify(at));
  assert.ok(STRINGS["tablets.reauth_key"].includes("Settings > Devices & services > ESPHome, open the tablet's menu (three dots) and press Reload"));
  assert.doesNotMatch(guide, /enter no key|This tablet was erased\. Home Assistant waits/);
  // Round 8: the line about adding another tablet, word for word. Round 9:
  // the steps quote the tablet's screens. Round 10: the steps of "Adding a
  // tablet" are read from its own list and compared whole, so a step that
  // goes or a headline that changes fails even while another section still
  // quotes the same words.
  assert.ok(guide.includes(`"${STRINGS["tablets.add_another"]}"`), "the line about another tablet");
  const adding = docs.slice(docs.indexOf("## Adding a tablet"), docs.indexOf("## A new tablet"));
  assert.deepEqual(numberedSteps(adding), [
    "1. Power the tablet on.",
    '2. If its screen says "Set up Wi-Fi", join the open Wi-Fi "Apollo TAB1 Hotspot" from a phone within 15 minutes, and pick your home\'s Wi-Fi on the page that opens.',
    `3. Its screen then says "${add.headline}" and "${add.step}". Add it there.`,
    `4. Its screen then says "${SCREENS.waiting.turn_on.headline}". Turn it on in the panel, as below.`,
  ]);
  assert.ok(
    flat(adding).includes('If they run out first, the tablet says "Setup not finished" and "Restart the tablet to finish setup": turn it off and on, and start again at step 2 or 3.'),
    "when the 15 minutes run out",
  );
  // Round 9: the offline row's next step. Round 10: in the "Offline" row
  // itself, which says what a tablet that has a dashboard shows.
  const offline = docs.split("\n").find((row) => row.startsWith("| Offline |"));
  assert.ok(offline, "no Offline row");
  assert.ok(offline.includes(`"${STRINGS["tablets.offline_help"]}"`), "the offline row's next step");
  // Round 11: without Wi-Fi a tablet with a dashboard also shows a Wi-Fi
  // note (the firmware's round 10); only with Wi-Fi but without Home
  // Assistant is the small mark all it shows.
  const note = SCREENS.notes.hotspot.text.replace("{hotspot}", SCREENS.hotspot);
  assert.ok(
    offline.includes(
      `A tablet that has a dashboard keeps showing it, with its last values and a small mark at the bottom left that it is not connected. Without Wi-Fi it also shows a note at the bottom, for example "${note}". With Wi-Fi but without Home Assistant it shows only the small mark, so its screen may not say what is wrong.`,
    ),
    "what a tablet with a dashboard shows",
  );
  assert.ok(offline.includes('A tablet without a dashboard names what it needs, for example "Set up Wi-Fi", "No Wi-Fi"'), "the waiting screens");
  assert.doesNotMatch(guide, /Its screen says what to do/);
});

// The numbered list in a part of a Markdown file, one string per step with
// its wrapped lines joined.
function numberedSteps(part) {
  return part.split("\n").reduce((list, line) => {
    if (/^\d+\. /.test(line)) list.push(line);
    else if (list.length && /^ {3}\S/.test(line)) list[list.length - 1] += ` ${line.trim()}`;
    return list;
  }, []);
}

test("the stand-in's offline tablet without a dashboard reads offline, like the integration", async () => {
  const hass = createMockHass(FIXTURES, { tablets: "three", seed: "none" });
  const { tablets: list } = await hass.callWS({ type: "apollo_tab/tablets" });
  const status = Object.fromEntries(list.map((tablet) => [tablet.name, [tablet.status, tablet.dashboard, tablet.engine]]));
  assert.deepEqual(status, {
    "Bedroom tablet": ["no_engine", null, ""],
    "Hallway tablet": ["offline", null, "0.1.0"],
    "Kitchen tablet": ["no_dashboard", null, "0.1.0"],
  });
  checkTabletList("tablets", list);
});
