// Plain words for the tablets and what they show, shared by Home, the
// editor and the tablet preview card. Nothing here touches the page, so the
// node tests check every status and reason.
//
// A tablet, as Home Assistant sends it:
//   {mac, device_id, name, short_name, model, dashboard, status, reason,
//    retry, engine, paired, input, entity_id, approved, suggested, reauth,
//    reauth_name}
//
// A new tablet (approved false, status "new") waits for an admin to turn
// it on from Home: pick its first dashboard, then press "Turn on with this
// dashboard". Until then it shows nothing, so it is left out of everything
// that lists what tablets show.

import { compareCodePoints, sortDashboards } from "./model.js";

// Every status a tablet can have, and the reasons that can come with one.
// The same lists as tests/harness/tablet-shapes.json, which the integration
// is tested against too.
export const TABLET_STATUSES = [
  "new",
  "no_dashboard",
  "offline",
  "no_engine",
  "unsupported",
  "sending",
  "on_tablet",
  "failed",
];

export const TABLET_REASONS = {
  unsupported: ["tablet_old", "tablet_new", "ha_version"],
  failed: [
    // What a tablet can answer to a call.
    "needs_encryption",
    "bad_key",
    "order",
    "size",
    "too_big",
    "memory",
    "auth",
    "incomplete",
    "hash",
    "parse",
    "version",
    "limits",
    // What Home Assistant concludes itself.
    "build",
    "replaced",
    "timeout",
    "unreadable",
    // What the connection to the tablet says.
    "offline",
    "no_engine",
    "bad_response",
    "failed",
  ],
};

// The words on Home, by the kind statusKind gives.
export const HOME_WORDS = {
  new: "tablets.status.new",
  on_tablet: "tablets.status.on_tablet",
  sending: "tablets.status.sending",
  offline: "tablets.status.offline",
  repairs: "tablets.status.repairs",
  no_engine: "tablets.status.no_engine",
  tablet_old: "tablets.status.tablet_old",
  update_app: "tablets.status.update_app",
  retrying: "tablets.status.retrying",
  too_big: "tablets.status.too_big",
  unreadable: "tablets.status.unreadable",
  cannot_show: "tablets.status.cannot_show",
  no_dashboard: "tablets.status.no_dashboard",
};

// The editor's line for one tablet that shows the dashboard. A tablet that
// shows it always has a dashboard, so no_dashboard has no line, and a new
// tablet shows nothing.
export const LINE_WORDS = {
  new: null,
  on_tablet: "editor.on_tablet_on_tablet",
  sending: "editor.on_tablet_sending",
  offline: "editor.on_tablet_offline",
  repairs: "editor.on_tablet_repairs",
  no_engine: "editor.on_tablet_no_engine",
  tablet_old: "editor.on_tablet_tablet_old",
  update_app: "editor.on_tablet_update_app",
  retrying: "editor.on_tablet_retrying",
  too_big: "editor.on_tablet_too_big",
  unreadable: "editor.on_tablet_cannot_show",
  cannot_show: "editor.on_tablet_cannot_show",
  no_dashboard: null,
};

// How a status looks next to its words: fine, busy, quiet, new, a problem,
// or "attention" when Home Assistant waits for an admin's answer in
// Repairs, which stands out more than anything else in the row.
const TONES = {
  new: "new",
  on_tablet: "ok",
  sending: "busy",
  offline: "quiet",
  repairs: "attention",
  no_engine: "quiet",
  no_dashboard: "quiet",
};

// The editor names at most this many tablets, then says how many more.
export const MAX_LINES = 3;

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

// Whether the tablet waits for an admin to pick its first dashboard.
export function isNewTablet(tablet) {
  return isObject(tablet) && (tablet.approved === false || tablet.status === "new");
}

// Whether a change of a tablet's "Shows" list switches it at once. For a
// new tablet a change only chooses; a separate button turns it on. So
// moving through the list with the keyboard, which changes the value in
// some browsers, never turns a tablet on.
export function showsChangeAssigns(tablet) {
  return isObject(tablet) && !isNewTablet(tablet);
}

// The last characters of a MAC address, in lower case: four by default, as
// a duplicate name ends in them ("aa:bb:cc:dd:ee:01" gives "ee01").
export function macEnding(mac, count = 4) {
  return typeof mac === "string" ? mac.replace(/[^0-9a-f]/gi, "").slice(-count).toLowerCase() : "";
}

// How many characters of its MAC address a tablet's own name ends in, as
// its waiting screen shows it: "Apollo TAB-1 ddee01" (the firmware's
// name_add_mac_suffix).
export const SCREEN_NAME_MAC_CHARS = 6;

// The line beside a new tablet's name that helps tell which device it is,
// because the name comes from the device itself and anything can call
// itself "Porch tablet". It asks the admin to check the same 6 characters
// the tablet's screen shows: "Before you turn it on, check that the name on
// the tablet's screen ends in ddee01."
export function deviceLine(tablet, t) {
  if (!isObject(tablet)) {
    return "";
  }
  return t("tablets.device_line", { mac: macEnding(tablet.mac, SCREEN_NAME_MAC_CHARS) });
}

// A tablet added to ESPHome again keeps the dashboard it had on its screen
// until an admin turns it on, so its name is not there to check. When the
// panel knows that dashboard (`suggested`, still one of `rows`), a second
// line says what to check instead: "If it still shows Home, its old
// dashboard, its name is not on its screen. Check that it shows Home and
// that its values no longer change." Otherwise "".
export function deviceBeforeLine(tablet, rows, t) {
  if (!isNewTablet(tablet) || typeof tablet.suggested !== "string" || !tablet.suggested) {
    return "";
  }
  const label = dashboardLabels(sortDashboards((Array.isArray(rows) ? rows : []).filter(isObject))).get(tablet.suggested);
  return label ? t("tablets.device_before", { dashboard: label }) : "";
}

// Where an admin confirms what Home Assistant asks about a device:
// Settings > System > Repairs.
export const REPAIRS_PATH = "/config/repairs";

// What Home Assistant waits for from an admin in Repairs before it connects
// to the tablet again: "erased" or "key", or null. After a hold-to-erase
// the tablet comes back without its key, and Home Assistant asks, under the
// name `reauth_name`, whether it may connect without the old key
// ("erased"). "key" is the same wait when Home Assistant asks for a key
// instead.
export function repairsWait(tablet) {
  if (!isObject(tablet) || typeof tablet.reauth_name !== "string" || !tablet.reauth_name) {
    return null;
  }
  return tablet.reauth === "erased" || tablet.reauth === "key" ? tablet.reauth : null;
}

// The line that says what Home Assistant waits for, and when to answer
// yes, or "". The check is the tablet's own screen (TAB-1 firmware,
// engine/tab_state.h; the shared contract's screens.json has its words):
// a tablet erased by holding its screen says "Confirm this tablet in Home
// Assistant" (HINT_ERASED, waiting.erased) until it has a key again, one
// erased over USB "Add this tablet in Home Assistant" (HINT_ADD,
// waiting.add); both only without its key, in its 15 minutes. After them a
// tablet without its key says "Setup not finished" (HINT_CLOSED,
// waiting.closed). Another device on the network cannot make a tablet that
// still has its key show any of them.
export function reauthLine(tablet, t) {
  const wait = repairsWait(tablet);
  if (wait === "erased") {
    return t("tablets.reauth_erased", { name: tablet.reauth_name });
  }
  if (wait === "key") {
    return t("tablets.reauth_key", { name: tablet.reauth_name });
  }
  return "";
}

// The tablet's device page in Home Assistant, or null without a device.
export function devicePagePath(tablet) {
  const id = isObject(tablet) ? tablet.device_id : null;
  return typeof id === "string" && /^[0-9A-Za-z_-]+$/.test(id) ? `/config/devices/device/${id}` : null;
}

// Which words describe the tablet's state, or null for a status this panel
// does not know (from a newer Home Assistant side). "new" wins over every
// other status. Then "repairs": while Home Assistant waits for an admin in
// Repairs it does not connect to the tablet, so the status would only say
// "Offline", and the admin's answer is what is needed.
export function statusKind(tablet) {
  if (!isObject(tablet)) {
    return null;
  }
  if (isNewTablet(tablet)) {
    return "new";
  }
  if (repairsWait(tablet)) {
    return "repairs";
  }
  const reason = typeof tablet.reason === "string" ? tablet.reason : "";
  switch (tablet.status) {
    case "on_tablet":
    case "sending":
    case "offline":
    case "no_engine":
    case "no_dashboard":
      return tablet.status;
    case "unsupported":
      // tablet_new and ha_version: the tablet speaks a newer language than
      // this side, or this side cannot reach it; either way this side needs
      // the update.
      return reason === "tablet_old" ? "tablet_old" : "update_app";
    case "failed":
      // These never work by trying again, whatever retry says.
      if (reason === "too_big" || reason === "limits") {
        return "too_big";
      }
      if (reason === "unreadable") {
        return "unreadable";
      }
      return tablet.retry === true ? "retrying" : "cannot_show";
    default:
      return null;
  }
}

// The words on Home. A new tablet with no dashboard to pick yet says what
// comes first, so its status never asks for a pick beside "Make a
// dashboard first."
export function homeWordsKey(tablet, hasDashboards = true) {
  const kind = statusKind(tablet);
  if (kind === "new" && !hasDashboards) {
    return "tablets.status.new_no_dashboard";
  }
  return HOME_WORDS[kind] ?? null;
}

export function lineWordsKey(tablet) {
  return LINE_WORDS[statusKind(tablet)] ?? null;
}

export function statusTone(tablet) {
  const kind = statusKind(tablet);
  return kind ? TONES[kind] || "problem" : "quiet";
}

// The next step under "Offline", or null: power and Wi-Fi, and the way back
// onto a changed Wi-Fi (off and on, then its set-up hotspot). The panel
// names it itself: a tablet that has a dashboard keeps showing it, with a
// small mark that it is not connected, and a Wi-Fi note only while it has
// no Wi-Fi, so with Wi-Fi but without Home Assistant its screen does not say
// what to do. Not while Home Assistant waits in Repairs: that line says what to do.
export function offlineHelpKey(tablet) {
  return statusKind(tablet) === "offline" ? "tablets.offline_help" : null;
}

// The extra line about taps, shown only while the tablet has the
// dashboard software and a dashboard: before that the status says more.
export function inputNoteKey(tablet) {
  if (!isObject(tablet) || isNewTablet(tablet) || !["on_tablet", "sending", "failed"].includes(tablet.status)) {
    return null;
  }
  if (tablet.input === "needs_encryption") {
    return "tablets.needs_encryption";
  }
  if (tablet.input === "not_paired") {
    return "tablets.not_paired";
  }
  return null;
}

// A tablet that shows its dashboard but has not been set up for taps for
// this long is offered "Set up again". Home Assistant tries by itself, at
// most once a minute, so by then it has tried at least once.
export const PAIR_AGAIN_AFTER_MS = 90 * 1000;

// How long until the panel offers to set this tablet up again, counted
// from `since`, when the panel first saw it not set up: 0 offers it now,
// null never (it is set up, needs encryption, is new or is not there).
export function pairAgainIn(tablet, since, now) {
  if (inputNoteKey(tablet) !== "tablets.not_paired" || !Number.isFinite(since) || !Number.isFinite(now)) {
    return null;
  }
  return Math.max(0, since + PAIR_AGAIN_AFTER_MS - now);
}

function nameOf(tablet) {
  return typeof tablet.name === "string" && tablet.name ? tablet.name : tablet.mac;
}

function shortNameOf(tablet) {
  return typeof tablet.short_name === "string" && tablet.short_name ? tablet.short_name : nameOf(tablet);
}

export { nameOf as tabletName, shortNameOf as tabletShortName };

// Tablets by name, then by MAC, so every list shows them in one order.
export function sortTablets(list) {
  return (Array.isArray(list) ? list : [])
    .filter((tablet) => isObject(tablet) && typeof tablet.mac === "string")
    .sort(
      (a, b) =>
        compareCodePoints(nameOf(a).toLowerCase(), nameOf(b).toLowerCase()) || compareCodePoints(a.mac, b.mac),
    );
}

// Home's order: new tablets first, each group by name.
export function homeOrder(list) {
  const sorted = sortTablets(list);
  return [...sorted.filter(isNewTablet), ...sorted.filter((tablet) => !isNewTablet(tablet))];
}

// Home's order while the panel stays open: every tablet keeps the place it
// had in `previous` (a list of MACs), so a tablet just turned on stays
// where it was and the row under the pointer does not change. A tablet
// that was not there before comes first when it is new, last otherwise.
// Without `previous`, homeOrder.
export function keepOrder(list, previous) {
  const ordered = homeOrder(list);
  if (!Array.isArray(previous) || !previous.length) {
    return ordered;
  }
  const place = new Map(previous.map((mac, index) => [mac, index]));
  const known = ordered.filter((tablet) => place.has(tablet.mac));
  known.sort((a, b) => place.get(a.mac) - place.get(b.mac));
  const unknown = ordered.filter((tablet) => !place.has(tablet.mac));
  return [...unknown.filter(isNewTablet), ...known, ...unknown.filter((tablet) => !isNewTablet(tablet))];
}

// For how long after a "Turn on with this dashboard" button moved a press
// of it is ignored: the second click of a double click lands on whatever
// moved under the pointer, maybe another tablet's button.
export const TURN_ON_SETTLE_MS = 700;

// Whether a "Turn on" button may be pressed at `now`, when it last moved at
// `movedAt` (both performance.now() times; movedAt null when it has not).
export function turnOnSettled(movedAt, now) {
  return !Number.isFinite(movedAt) || !Number.isFinite(now) || now - movedAt >= TURN_ON_SETTLE_MS;
}

// The "Turn on" buttons that moved or came between two looks at the page.
// `before` and `after` map a tablet's MAC to its button's place, [left,
// top, width, height] in pixels from the panel's corner; `before` is null
// before the first look, when nothing moved. A change of half a pixel or
// less is rounding, not a move. Words that change elsewhere, without moving
// the button, are no move: the button under the pointer is still the same.
export function movedTurnOns(before, after) {
  if (!(before instanceof Map) || !(after instanceof Map)) {
    return [];
  }
  const moved = [];
  for (const [mac, place] of after) {
    const was = before.get(mac);
    const same =
      Array.isArray(was) &&
      Array.isArray(place) &&
      was.length === place.length &&
      place.every((value, index) => Math.abs(value - was[index]) <= 0.5);
    if (!same) {
      moved.push(mac);
    }
  }
  return moved;
}

// When each "Turn on" button last moved or came, after another look at the
// page. `movedAt` maps a tablet's MAC to that time (performance.now()); the
// buttons movedTurnOns(before, after) names get `now`, and every other
// keeps the time it had: a row that moves one button does not hold the
// others. A new Map; `movedAt` stays as it was.
export function markMoved(movedAt, before, after, now) {
  const marked = new Map(movedAt instanceof Map ? movedAt : []);
  for (const mac of movedTurnOns(before, after)) {
    marked.set(mac, now);
  }
  return marked;
}

// The tablets an admin turned on, in the one order.
export function approvedTablets(list) {
  return sortTablets(list).filter((tablet) => !isNewTablet(tablet));
}

// How many tablets wait for an admin.
export function newTabletCount(list) {
  return sortTablets(list).filter(isNewTablet).length;
}

// The tablets that show the dashboard at urlPath, in that order. A new
// tablet shows nothing.
export function tabletsShowing(tablets, urlPath) {
  return approvedTablets(tablets).filter((tablet) => tablet.dashboard === urlPath);
}

// One tablet changed (the answer to a change made here): the list with it.
export function withTablet(list, tablet) {
  if (!Array.isArray(list) || !isObject(tablet) || typeof tablet.mac !== "string") {
    return list;
  }
  const index = list.findIndex((entry) => entry?.mac === tablet.mac);
  if (index < 0) {
    return [...list, tablet];
  }
  const next = [...list];
  next[index] = tablet;
  return next;
}

// "Kitchen", "Kitchen and Bedroom", "Kitchen, Hall and Bedroom".
export function joinNames(names, t) {
  const list = (Array.isArray(names) ? names : []).filter((name) => typeof name === "string" && name);
  if (list.length < 2) {
    return list[0] || "";
  }
  return t("tablets.and", { first: list.slice(0, -1).join(", "), last: list.at(-1) });
}

// "Shown on: Kitchen, Bedroom" for a dashboard row, or "" when no tablet
// shows it.
export function shownOnText(tablets, urlPath, t) {
  const names = tabletsShowing(tablets, urlPath).map(shortNameOf);
  return names.length ? t("tablets.shown_on", { names: names.join(", ") }) : "";
}

// The title of each dashboard as the drop-downs show it, each one unique
// ignoring case. A title that another dashboard's text also has gets its
// address added, until no two are equal: "Home (home-2)". The same rule as
// the tablet's own list in Home Assistant (assignments.option_labels,
// tests/label_cases.json).
export function dashboardLabels(rows) {
  const list = (Array.isArray(rows) ? rows : []).filter((row) => isObject(row) && typeof row.url_path === "string");
  const titleOf = (row) => (typeof row.title === "string" && row.title ? row.title : row.url_path);
  const labels = new Map(list.map((row) => [row.url_path, titleOf(row)]));
  const plain = new Set(labels.keys());
  for (;;) {
    const counts = new Map();
    for (const text of labels.values()) {
      const key = text.toLowerCase();
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    const clashing = [...plain].filter((url) => counts.get(labels.get(url).toLowerCase()) > 1);
    if (!clashing.length) {
      return labels;
    }
    for (const url of clashing) {
      labels.set(url, `${labels.get(url)} (${url})`);
      plain.delete(url);
    }
  }
}

// The choices of a tablet's "Shows" list, as [value, label, disabled]: every
// dashboard in the one order, and first a choice that cannot be picked when
// the tablet has none, or one this list does not hold. `unreadable` lists
// the dashboards that cannot be read right now ([{url_path, title}]); a
// tablet on one of those keeps the dashboard's name: "Home (cannot be read
// right now)". `suggested` is what a new tablet showed before it was set up
// again: "Home (shown before)". It is not picked for it.
export function showsOptions(rows, current, t, unreadable = [], suggested = null) {
  const ordered = sortDashboards((Array.isArray(rows) ? rows : []).filter((row) => isObject(row)));
  const labels = dashboardLabels(ordered);
  const options = ordered.map((row) => [
    row.url_path,
    row.url_path === suggested && suggested !== current
      ? t("tablets.suggested_option", { dashboard: labels.get(row.url_path) })
      : labels.get(row.url_path),
    false,
  ]);
  if (typeof current !== "string" || !current) {
    options.unshift(["", t("tablets.choose"), true]);
  } else if (!labels.has(current)) {
    const broken = (Array.isArray(unreadable) ? unreadable : []).find(
      (row) => isObject(row) && row.url_path === current && typeof row.title === "string" && row.title,
    );
    options.unshift([current, broken ? t("tablets.unreadable_option", { dashboard: broken.title }) : current, true]);
  }
  return options;
}

// The dashboard the tablets of urlPath move to when it is deleted: the
// first other one in the one order, or null.
export function nextDashboard(rows, urlPath) {
  return (
    sortDashboards((Array.isArray(rows) ? rows : []).filter((row) => isObject(row))).find(
      (row) => typeof row.url_path === "string" && row.url_path !== urlPath,
    ) || null
  );
}

// The sentence the delete question adds about the tablets that show the
// dashboard: "Kitchen tablet and Bedroom tablet show this dashboard. They
// will switch to Home." Empty when no tablet shows it.
export function deleteNote(tablets, urlPath, rows, t) {
  const showing = tabletsShowing(tablets, urlPath);
  if (!showing.length) {
    return "";
  }
  const names = joinNames(showing.map(nameOf), t);
  const next = nextDashboard(rows, urlPath);
  const one = showing.length === 1;
  if (!next) {
    return t(one ? "tablets.delete_one_empty" : "tablets.delete_many_empty", { names });
  }
  const title = dashboardLabels(sortDashboards(rows)).get(next.url_path) || next.url_path;
  return t(one ? "tablets.delete_one" : "tablets.delete_many", { names, dashboard: title });
}

// The editor's lines above the tablet picture: one per tablet that shows
// the dashboard (at most MAX_LINES, then "and 2 more"), or "Not shown on a
// tablet yet". Each line is {kind, text}, with the tablet's mac and tone on
// a tablet's line.
export function captionLines(tablets, urlPath, t) {
  const showing = tabletsShowing(tablets, urlPath);
  if (!showing.length) {
    return [{ kind: "nowhere", text: t("editor.on_tablet_nowhere") }];
  }
  const lines = [];
  for (const tablet of showing.slice(0, MAX_LINES)) {
    const key = lineWordsKey(tablet);
    if (key) {
      lines.push({ kind: "tablet", mac: tablet.mac, tone: statusTone(tablet), text: t(key, { tablet: nameOf(tablet) }) });
    }
  }
  if (showing.length > MAX_LINES) {
    lines.push({ kind: "more", text: t("editor.on_tablet_more", { count: showing.length - MAX_LINES }) });
  }
  return lines;
}

// What the editor's "Shown on" block says for each tablet an admin turned
// on: whether it shows this dashboard, and if not, which one it shows
// instead. Each entry is {mac, name, here, text}. New tablets are turned on
// from Home only.
export function shownOnRows(tablets, urlPath, rows, t) {
  const labels = dashboardLabels(sortDashboards(Array.isArray(rows) ? rows : []));
  return approvedTablets(tablets).map((tablet) => {
    const here = tablet.dashboard === urlPath;
    let text;
    if (here) {
      text = t("editor.on_tablet_this");
    } else if (typeof tablet.dashboard === "string" && tablet.dashboard) {
      text = t("editor.on_tablet_other", { dashboard: labels.get(tablet.dashboard) || tablet.dashboard });
    } else {
      text = t("editor.on_tablet_nothing");
    }
    return { mac: tablet.mac, name: nameOf(tablet), here, text };
  });
}
