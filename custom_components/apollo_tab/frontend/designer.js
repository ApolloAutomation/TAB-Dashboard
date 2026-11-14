import {
  assignTablet,
  getConnection,
  loadLibrary,
  loadStrings,
  onLayoutChanged,
  onTabletsChanged,
  previewLayout,
  t,
} from "./api.js";
import {
  buildCardForm,
  buildDashboardSettings,
  buildHeadingForm,
  buildOtherForm,
  buildPageSettings,
  deviceText,
  el,
  fillItemNotes,
  focusLost,
  icon,
  makeButton,
  restoreFocus,
  screenHeading,
  uid,
} from "./card-form.js";
import { confirmOpen, openConfirm } from "./confirm.js";
import { warningBoxKind } from "./logic.js";
import {
  DEFAULT_THEME,
  addCard,
  addPage,
  canMove,
  canRedo,
  canUndo,
  cardKind,
  classifyRemote,
  componentOf,
  createHistory,
  dashboardNotes,
  devicesLeft,
  followItem,
  getCard,
  historyPush,
  historyRedo,
  historyUndo,
  maxUnitsWide,
  mergeDashboards,
  moveCardToPage,
  moveItem,
  movePage,
  nextDashboardTitle,
  omittedOnPage,
  pageItems,
  pageKind,
  pageList,
  pageNotes,
  pageScreens,
  removeItem,
  removePage,
  renamePage,
  resizeCard,
  sameConfig,
  SaveQueue,
  setHeadingText,
  setPageIcon,
  setTheme,
  sourceKey,
  updateCard,
  useWholeScreen,
  usesWholeScreen,
} from "./model.js";
import { openCardPicker } from "./picker.js";
import { renderPage } from "./render.js";
import { canvasStyles, designerStyles, formStyles, pickerStyles, rendererStyles } from "./styles.js";
import { captionLines, deleteNote, newTabletCount, shownOnRows, tabletsShowing } from "./tablets.js";

const KEEP_IN_SIDEBAR_KEY = "apollo_tab.sidebar_keep";
const COMPACT_BELOW = 900;
const TOAST_MS = 6000;
// A toast that offers a next step stays longer, and stays while it has
// focus or the pointer is over it.
const TOAST_ACTION_MS = 15000;
const PREVIEW_DEBOUNCE_MS = 250;
const REFRESH_MS = 30000;
// How long opening a dashboard waits for the saves it was left with.
const SETTLE_WAIT_MS = 10000;
// How long each background retry of a failed save waits, one after another.
const RETRY_MS = [2000, 5000, 15000, 30000];

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

// Changes an editor had not saved yet when it was closed, by url_path:
// {urlPath, id, queue, history, hass, conn, conflict, timer, tries, done}.
// Home Assistant removes the editor when the person leaves through its
// sidebar, so they are kept here rather than in any one editor. A save that
// is still running finishes, a failed save is tried again in the background
// while that is safe, and the next editor that opens the dashboard takes
// over the rest.
//
// Each change belongs to one dashboard: its address (urlPath) and Home
// Assistant's id for it. When that dashboard is deleted, or the address
// holds a dashboard that is listed differently, the change is dropped.
// Home Assistant gives a dashboard made again at the same address the same
// id, so one made while this browser's connection was down can look like
// the old one: then the change is never saved unasked, and the editor asks
// with the unsure banner (see SaveQueue.doubt).
const leftBehind = new Map();

// Ends the watch on Home Assistant's dashboard events, while changes are kept.
let stopWatching = null;

// The panel's Home lists the dashboards that hold a kept change; this event
// tells it when that list may have changed.
const KEPT_EVENT = "apollo-tab-kept-changes";

function keptChanged() {
  window.dispatchEvent(new CustomEvent(KEPT_EVENT));
}

// The dashboards with a change that is not saved yet, by url_path: waiting
// is true when the change waits for the person's choice, false while it is
// still being tried.
export function keptChanges() {
  return [...leftBehind.values()]
    .filter((entry) => entry.queue.dirty)
    .map((entry) => ({ urlPath: entry.urlPath, waiting: entry.queue.state === "paused" }));
}

export function onKeptChanges(listener) {
  window.addEventListener(KEPT_EVENT, listener);
  return () => window.removeEventListener(KEPT_EVENT, listener);
}

function guardLeftBehind(event) {
  if ([...leftBehind.values()].some((entry) => entry.queue.dirty)) {
    event.preventDefault();
  }
}

function keepLeftBehind(entry) {
  leftBehind.set(entry.urlPath, entry);
  window.addEventListener("beforeunload", guardLeftBehind);
  watchLeftBehind(entry.conn);
  keptChanged();
}

function forgetLeftBehind(entry) {
  clearTimeout(entry.timer);
  entry.timer = null;
  if (leftBehind.get(entry.urlPath) === entry) {
    leftBehind.delete(entry.urlPath);
  }
  if (!leftBehind.size) {
    window.removeEventListener("beforeunload", guardLeftBehind);
    stopWatching?.();
    stopWatching = null;
  }
  keptChanged();
}

// The dashboard of a kept change is gone: nothing is saved any more, and
// leaving the browser page no longer asks about it.
function dropLeftBehind(entry) {
  entry.queue.pause();
  forgetLeftBehind(entry);
}

// Home Assistant says when a dashboard is deleted; the change kept for it is
// dropped then. A browser whose connection was down heard nothing, so every
// kept change is checked again when the connection comes back. Its dashboard
// may also have been deleted and made again with the content the change
// started from, which looks just like the old one: such a change is no
// longer saved unasked (see SaveQueue.doubt).
function watchLeftBehind(conn) {
  if (stopWatching || !conn) {
    return;
  }
  stopWatching = onLayoutChanged(
    conn,
    (event) => {
      const entry = event?.type === "removed" ? leftBehind.get(event.url_path) : null;
      if (entry) {
        dropLeftBehind(entry);
      }
    },
    () => {
      for (const entry of [...leftBehind.values()]) {
        entry.queue.doubt();
        checkLeftBehind(entry);
      }
    },
  );
}

// A kept change met a version saved somewhere else and stopped. The next
// editor of the dashboard asks about that version, even if Home Assistant
// holds the version the change started from again by then.
function heldBack(queue, stored) {
  for (const entry of leftBehind.values()) {
    if (entry.queue === queue) {
      entry.conflict = stored;
    }
  }
}

// Whether the address of a kept change still holds its dashboard: listed
// with the same id, kept in storage and still a TAB-1 dashboard.
function sameDashboard(entry, list, config) {
  const item = (Array.isArray(list) ? list : []).find((candidate) => candidate?.url_path === entry.urlPath);
  return (
    Boolean(item) &&
    (typeof item.id === "string" ? item.id : null) === entry.id &&
    (item.mode || "storage") === "storage" &&
    isObject(config) &&
    isObject(config.apollo_tab)
  );
}

// Reads the dashboards list and the version Home Assistant holds for a kept
// change. Resolves to {gone} when its dashboard is no longer there, and
// throws when Home Assistant cannot be reached.
async function lookUp(entry) {
  const [list, stored] = await Promise.all([
    entry.hass.callWS({ type: "lovelace/dashboards/list" }),
    entry.hass.callWS({ type: "lovelace/config", url_path: entry.urlPath, force: false }).catch((error) => {
      if (error?.code === "config_not_found") {
        return null;
      }
      throw error;
    }),
  ]);
  return { gone: !sameDashboard(entry, list, stored), stored };
}

async function checkLeftBehind(entry) {
  let found;
  try {
    found = await lookUp(entry);
  } catch {
    // Checked again on the next try or reconnection.
    return;
  }
  if (found.gone && leftBehind.get(entry.urlPath) === entry) {
    dropLeftBehind(entry);
  }
}

// Removes and returns what was left for `urlPath`, so one editor owns it.
function takeLeftBehind(urlPath) {
  const entry = leftBehind.get(urlPath) || null;
  if (entry) {
    forgetLeftBehind(entry);
  }
  return entry;
}

// Called whenever a left-behind queue has stopped saving.
function afterLeftBehindSave(entry) {
  if (leftBehind.get(entry.urlPath) !== entry) {
    return;
  }
  if (!entry.queue.dirty) {
    forgetLeftBehind(entry);
  } else if (entry.queue.state === "error") {
    retryLeftBehind(entry);
  }
  // A paused queue waits for the person's choice when the dashboard opens.
}

// Tries a failed save again after a while, but only while Home Assistant
// still holds a version this editor saved itself. A version saved somewhere
// else in the meantime, or one that may belong to a dashboard made again at
// the same address, is never overwritten without the person's choice: the
// change then waits for them instead.
function retryLeftBehind(entry) {
  const wait = RETRY_MS[Math.min(entry.tries, RETRY_MS.length - 1)];
  entry.tries += 1;
  clearTimeout(entry.timer);
  entry.timer = setTimeout(() => {
    entry.timer = null;
    entry.done = (async () => {
      let found;
      try {
        found = await lookUp(entry);
      } catch {
        if (leftBehind.get(entry.urlPath) === entry) {
          retryLeftBehind(entry);
        }
        return;
      }
      if (leftBehind.get(entry.urlPath) !== entry) {
        return;
      }
      if (found.gone) {
        // The dashboard was deleted or replaced: there is nothing to save to.
        dropLeftBehind(entry);
        return;
      }
      if (classifyRemote(found.stored, entry.queue) !== "ours") {
        entry.conflict = found.stored;
        entry.queue.pause();
        return;
      }
      await entry.queue.flush();
      afterLeftBehindSave(entry);
    })();
  }, wait);
}

function errorMessage(error) {
  return error?.message || error?.code || String(error ?? "");
}

function keptInSidebar() {
  try {
    const list = JSON.parse(localStorage.getItem(KEEP_IN_SIDEBAR_KEY) || "[]");
    return Array.isArray(list) ? list.filter((entry) => typeof entry === "string") : [];
  } catch {
    return [];
  }
}

function keepInSidebar(urlPath) {
  try {
    const list = keptInSidebar();
    if (!list.includes(urlPath)) {
      localStorage.setItem(KEEP_IN_SIDEBAR_KEY, JSON.stringify([...list, urlPath]));
    }
  } catch {
    // Without storage the notice simply comes back next time.
  }
}

function sameSource(a, b) {
  return Array.isArray(a) && Array.isArray(b) && a[0] === b[0] && a[1] === b[1] && a[2] === b[2];
}

function cardCount(view) {
  if (!isObject(view) || !Array.isArray(view.sections)) {
    return 0;
  }
  return view.sections.reduce(
    (total, section) => total + (Array.isArray(section?.cards) ? section.cards.length : 0),
    0,
  );
}

function banner(className) {
  const box = el("section", className ? `banner ${className}` : "banner");
  return box;
}

function alertLine(text) {
  const line = el("p", "alert", text);
  line.setAttribute("role", "alert");
  return line;
}

export class ApolloTabDesigner extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._style = el("style");
    this._style.textContent = designerStyles + formStyles + pickerStyles;
    this.shadowRoot.append(this._style);

    this._hass = null;
    this._narrow = false;
    this._urlPath = null;
    this._library = null;
    this.onExit = null;
    this.onAdvanced = null;

    this._conn = null;
    this._status = "idle";
    this._error = null;
    this._run = 0;
    this._started = false;
    this._stops = [];
    this._dashboard = null;
    this._readOnly = null;
    this._history = null;
    this._queue = null;
    this._queueUrl = null;
    this._preview = null;
    this._previewSeq = 0;
    this._previewError = null;
    this._previewTimer = null;
    this._refreshTimer = null;
    this._view = 0;
    this._screen = 0;
    this._selected = null;
    this._rows = [];
    // The other version while the person chooses, and what Home Assistant
    // holds then when that is not the other version (see _takeOver).
    // _conflictUnsure: the other version is the one the change started
    // from, asked about because the connection was lost meanwhile.
    this._conflict = null;
    this._conflictStored = null;
    this._conflictUnsure = false;
    this._sidebarDismissed = false;
    this._sidebarError = "";
    this._deleting = false;
    this._toast = null;
    this._toastTimer = null;
    this._compact = false;
    this._els = {};
    this._areaKey = null;
    this._sideKey = null;
    this._pendingFocus = null;
    this._screenFor = null;
    // A token for the open card picker, or null.
    this._picking = null;
    this._revealOnPreview = false;
    this._frame = 0;
    this._lastSaveState = null;
    this._titleFocus = false;
    // The tablets (null until Home Assistant sent them) and a final failure
    // to get them; the TAB-1 dashboards in the one order, with their titles
    // (null until read); the tablets this editor is moving to the dashboard
    // right now, and the failure of the last such move.
    this._tablets = null;
    this._tabletsError = null;
    this._tabRows = null;
    this._tabRowsSeq = 0;
    this._tabRowsTimer = null;
    this._assigning = new Set();
    this._shownOnError = "";
    this._shownOnKey = null;

    // Work left behind by a closed editor has its own guard (see leftBehind).
    this._onBeforeUnload = (event) => {
      if (this._queue?.dirty) {
        event.preventDefault();
      }
    };
    this._onWindowKey = (event) => this._handleShortcut(event);
    this.addEventListener("keydown", (event) => this._handleEscape(event));
    // A shown toast moves out of the way of whatever comes into view or
    // gets focus (see _placeToast).
    this._toastFrame = 0;
    this._onViewport = () => this._queuePlaceToast();
    this.shadowRoot.addEventListener("focusin", (event) => this._clearOfSheet(event.target));
    this.shadowRoot.addEventListener("focusin", this._onViewport);
    this.shadowRoot.addEventListener("scroll", this._onViewport, { capture: true, passive: true });
  }

  set hass(value) {
    const first = !this._hass;
    this._hass = value;
    if (this._els.menu) {
      this._els.menu.hass = value;
    }
    if (first) {
      this._start();
    }
  }

  get hass() {
    return this._hass;
  }

  set narrow(value) {
    const next = Boolean(value);
    if (next === this._narrow) {
      return;
    }
    this._narrow = next;
    if (this._els.menu) {
      this._els.menu.narrow = next;
    }
  }

  get narrow() {
    return this._narrow;
  }

  set urlPath(value) {
    if (value === this._urlPath) {
      return;
    }
    this._urlPath = value;
    if (this._started) {
      this._stop();
      this._start();
    }
  }

  get urlPath() {
    return this._urlPath;
  }

  set library(value) {
    if (value === this._library) {
      return;
    }
    this._library = value;
    if (this._status === "ready") {
      this._requestPreview();
      this._renderSide();
    }
  }

  get library() {
    return this._library;
  }

  connectedCallback() {
    window.addEventListener("beforeunload", this._onBeforeUnload);
    window.addEventListener("keydown", this._onWindowKey);
    window.addEventListener("scroll", this._onViewport, { capture: true, passive: true });
    window.addEventListener("resize", this._onViewport, { passive: true });
    window.visualViewport?.addEventListener("resize", this._onViewport, { passive: true });
    window.visualViewport?.addEventListener("scroll", this._onViewport, { passive: true });
    this._hostObserver = new ResizeObserver(() => this._checkCompact());
    this._hostObserver.observe(this);
    this._compact = this.getBoundingClientRect().width < COMPACT_BELOW;
    this._start();
  }

  disconnectedCallback() {
    // Unsaved work moves to leftBehind, which keeps asking "leave this
    // page?" until it is saved.
    this._stop();
    window.removeEventListener("beforeunload", this._onBeforeUnload);
    window.removeEventListener("keydown", this._onWindowKey);
    window.removeEventListener("scroll", this._onViewport, { capture: true });
    window.removeEventListener("resize", this._onViewport);
    window.visualViewport?.removeEventListener("resize", this._onViewport);
    window.visualViewport?.removeEventListener("scroll", this._onViewport);
    this._hostObserver?.disconnect();
    this._hostObserver = null;
  }

  get _draft() {
    return this._history?.present ?? null;
  }

  _stop() {
    // First, while the status still says whether the dashboard was deleted.
    this._releaseQueue();
    this._run += 1;
    this._started = false;
    this._status = "idle";
    this._stops.forEach((stop) => stop?.());
    this._stops = [];
    clearTimeout(this._previewTimer);
    clearTimeout(this._toastTimer);
    clearTimeout(this._tabRowsTimer);
    this._tabRowsTimer = null;
    this._tabRowsSeq += 1;
    this._assigning.clear();
    this._shownOnError = "";
    // A message about this dashboard is not shown for the next one.
    this._toast = null;
    clearInterval(this._refreshTimer);
    cancelAnimationFrame(this._frame);
    cancelAnimationFrame(this._toastFrame);
    this._toastFrame = 0;
    this._stageObserver?.disconnect();
    this._stageObserver = null;
    this._els.pageHost?.__atCleanup?.();
    this._closePickers();
  }

  // The card picker is a <dialog> placed directly in the shadow root.
  // (":scope" matches nothing in a shadow root, so the children are read.)
  _dialogs() {
    return [...this.shadowRoot.children].filter((node) => node.localName === "dialog");
  }

  // An open card picker belongs to the dashboard being left; closing it
  // makes it answer "nothing chosen", and Add card works again.
  _closePickers() {
    this._picking = null;
    for (const dialog of this._dialogs()) {
      if (dialog.open) {
        dialog.close();
      }
    }
  }

  // Each queue saves to the one dashboard it was made for. When the editor
  // leaves that dashboard, the queue still saves the last change there, but
  // it no longer updates the screen, which may show another dashboard. A
  // change it cannot save, or one waiting for the person's choice between
  // two versions, is kept in leftBehind.
  _releaseQueue() {
    const queue = this._queue;
    const urlPath = this._queueUrl;
    this._queue = null;
    this._queueUrl = null;
    if (!queue || !queue.dirty) {
      return;
    }
    // A deleted dashboard has nowhere to save to.
    if (this._status === "gone" || this._deleting) {
      queue.pause();
      return;
    }
    const entry = {
      urlPath,
      id: this._dashboard?.id ?? null,
      queue,
      history: this._history,
      hass: this._hass,
      conn: this._conn,
      // The version saved somewhere else, when the person had not yet
      // chosen between it and their own.
      conflict: this._conflict,
      timer: null,
      tries: 0,
      done: null,
    };
    keepLeftBehind(entry);
    entry.done = queue.flush().then(() => afterLeftBehindSave(entry));
  }

  // Waits until saves left behind for this dashboard have finished, so it
  // opens with the last change rather than the version before it.
  async _settled(urlPath) {
    const pending = leftBehind.get(urlPath)?.done;
    if (!pending) {
      return;
    }
    let timer = null;
    await Promise.race([
      pending,
      new Promise((resolve) => {
        timer = setTimeout(resolve, SETTLE_WAIT_MS);
      }),
    ]);
    clearTimeout(timer);
  }

  // Takes over a change an earlier editor could not save. When Home
  // Assistant still holds a version that editor saved itself and the person
  // owed no choice, nobody else has changed the dashboard, so the change is
  // simply saved now. Otherwise the person chooses between the two versions
  // with the banner used when a change arrives while they edit.
  _takeOver(left, config) {
    if (!left) {
      return;
    }
    const draft = left.history?.present;
    const unsaved = left.queue.dirty;
    // The old queue saves nothing more; this editor's queue takes over.
    left.queue.pause();
    if (!this._queue || !unsaved || !isObject(draft)) {
      return;
    }
    const kind = classifyRemote(config, left.queue);
    const ours = kind === "ours";
    // The version the person has not chosen against yet, if there is one.
    const other = ours ? left.conflict : config;
    if (!other || sameConfig(other, draft)) {
      if (!sameConfig(draft, config)) {
        this._history = left.history;
        this._queue.push(draft);
      }
      return;
    }
    this._history = left.history;
    this._queue.pause();
    this._queue.push(draft);
    this._conflict = other;
    // After a lost connection the other version may be a new dashboard made
    // at the same address, whatever it holds: the banner says so, and keeping
    // the change is not the button it puts first.
    this._conflictUnsure = kind === "unsure" || (kind === "changed" && left.queue.doubted);
    // One of the earlier editor's saves landed after the other version
    // did, so Home Assistant holds that save rather than the other version.
    this._conflictStored = ours ? config : null;
  }

  async _start() {
    if (!this._hass || !this._urlPath || !this.isConnected || this._started) {
      return;
    }
    this._started = true;
    const run = ++this._run;
    this._status = "loading";
    this._render();

    try {
      this._conn = await getConnection(this._hass);
      await loadStrings(this._conn);
      if (!this._library) {
        this._library = await loadLibrary(this._conn);
      }
      if (run !== this._run) {
        return;
      }
      await this._load(run);
    } catch (error) {
      if (run === this._run) {
        this._fail(error);
      }
      return;
    }
    if (run !== this._run || this._status !== "ready") {
      return;
    }

    // Home Assistant reports changes only to a connected browser, so the
    // dashboard is also read again after the connection comes back (see
    // onLayoutChanged) and whenever the browser tab is shown again. The
    // open editor's queue is not put in doubt then: the person is looking at
    // the dashboard, the read shows what it holds, and a dashboard made again
    // with that same content loses nothing when the change is saved into it.
    // Only kept changes, which nobody is looking at, are doubted.
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        this._checkRemote();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    this._stops.push(
      onLayoutChanged(
        this._conn,
        (event) => this._layoutEvent(event),
        () => {
          this._checkRemote();
          this._loadTabRows();
        },
      ),
      () => document.removeEventListener("visibilitychange", onVisible),
      // Which tablets show this dashboard, and how it is going there.
      onTabletsChanged(this._conn, (tablets) => this._tabletsChanged(tablets), {
        onError: (error) => {
          this._tabletsError = error;
          this._fillTabletLines();
          this._fillShownOn();
        },
      }),
    );
    this._loadTabRows();
    this._refreshTimer = setInterval(() => {
      if (document.visibilityState === "visible" && this._status === "ready") {
        this._requestPreview();
      }
    }, REFRESH_MS);
  }

  async _load(run) {
    const urlPath = this._urlPath;
    await this._settled(urlPath);
    if (run !== this._run) {
      return;
    }
    // From here this editor owns any change left behind for the dashboard;
    // if it stops before it is ready, the change goes back.
    let left = takeLeftBehind(urlPath);
    let config;
    let list;
    try {
      [config, list] = await Promise.all([
        this._hass
          .callWS({ type: "lovelace/config", url_path: urlPath, force: false })
          .catch((error) => {
            if (error?.code === "config_not_found") {
              return null;
            }
            throw error;
          }),
        this._hass.callWS({ type: "lovelace/dashboards/list" }),
      ]);
    } catch (error) {
      if (left) {
        keepLeftBehind(left);
        afterLeftBehindSave(left);
      }
      throw error;
    }
    if (run !== this._run) {
      if (left) {
        keepLeftBehind(left);
        afterLeftBehindSave(left);
      }
      return;
    }

    const item = (Array.isArray(list) ? list : []).find((entry) => entry?.url_path === urlPath);
    if (!item || !isObject(config) || !isObject(config.apollo_tab)) {
      left?.queue.pause();
      this._gone();
      return;
    }
    // A change kept for a dashboard that has since been replaced by another
    // one at this address is dropped, not saved into the new one.
    if (left && !sameDashboard(left, list, config)) {
      left.queue.pause();
      left = null;
    }

    this._dashboard = {
      id: typeof item.id === "string" ? item.id : null,
      title: item.title || urlPath,
      show_in_sidebar: item.show_in_sidebar === true,
      mode: item.mode || "storage",
    };
    if (this._dashboard.mode !== "storage") {
      this._readOnly = "yaml";
    } else if (Object.hasOwn(config, "strategy")) {
      this._readOnly = "auto";
    } else {
      this._readOnly = null;
    }

    this._history = createHistory(config);
    this._view = 0;
    this._screen = 0;
    this._selected = null;
    this._preview = null;
    this._conflict = null;
    this._conflictStored = null;
    this._conflictUnsure = false;
    this._deleting = false;
    this._lastSaveState = null;
    this._sidebarDismissed = false;
    this._sidebarError = "";
    this._queue = null;
    this._queueUrl = null;
    if (!this._readOnly) {
      // The address is fixed here: a save that runs after the editor has
      // moved on still goes to this dashboard.
      const queue = new SaveQueue({
        save: (next) => this._hass.callWS({ type: "lovelace/config/save", url_path: urlPath, config: next }),
        // Before each save the queue reads what Home Assistant holds, and
        // never saves over a version this browser did not hear about.
        read: () => this._hass.callWS({ type: "lovelace/config", url_path: urlPath, force: false }),
        onChanged: (stored, kind) => {
          if (queue === this._queue) {
            this._askWhichVersion(stored, kind === "unsure");
          } else {
            heldBack(queue, stored);
          }
        },
        delay: 400,
        onState: () => {
          if (queue === this._queue) {
            this._saveStateChanged();
          } else {
            keptChanged();
          }
        },
      });
      queue.reset(config);
      this._queue = queue;
      this._queueUrl = urlPath;
    }
    // On a dashboard that can only be looked at there is no queue, and a
    // change left behind is dropped: it could never be saved.
    this._takeOver(left, config);
    this._status = "ready";
    this._render();
    this._requestPreview();
    if (this._conflict) {
      this._revealBanners();
    }
  }

  _fail(error) {
    this._status = "failed";
    this._error = error;
    this._queue?.pause();
    this._render();
  }

  // The dashboard was deleted: a change not saved yet has nowhere to go, so
  // the queue is dropped and closing the browser page no longer asks about it.
  _gone() {
    this._status = "gone";
    this._queue?.pause();
    this._queue = null;
    this._queueUrl = null;
    this._conflict = null;
    this._closePickers();
    this._render();
  }

  _retry() {
    this._stop();
    this._start();
  }

  _checkCompact() {
    const compact = this.getBoundingClientRect().width < COMPACT_BELOW;
    if (compact === this._compact) {
      return;
    }
    this._compact = compact;
    this._els.root?.classList.toggle("compact", compact);
    this._placeAdvice();
    this._renderSide();
  }

  // ---- drawing ---------------------------------------------------------

  _render() {
    this._stageObserver?.disconnect();
    this._stageObserver = null;
    this._els.pageHost?.__atCleanup?.();
    const root = el("div", this._compact ? "root compact" : "root");
    this._els = { root };
    this._areaKey = null;
    // An open dialog stays where it is: taking a modal dialog out of the page,
    // even to put it back, ends its modal state without closing it.
    for (const node of [...this.shadowRoot.children]) {
      if (node !== this._style && node.localName !== "dialog") {
        node.remove();
      }
    }
    this._style.after(root);

    const header = el("header", "ed-header");
    this._els.header = header;
    root.append(header);
    this._renderHeader();

    if (this._status === "loading" || this._status === "idle") {
      root.append(el("p", "missing", t("editor.loading")));
      return;
    }
    this._takeTitleFocus();
    if (this._status === "gone") {
      const box = el("div", "missing");
      box.append(
        el("h2", null, t("editor.missing_title")),
        el("p", null, t("editor.missing_text")),
        makeButton(t("editor.back"), { className: "primary", test: "missing-back", onClick: () => this.onExit?.() }),
      );
      root.append(box);
      return;
    }
    if (this._status === "failed") {
      const box = el("div", "missing");
      const message = el("p", "alert", t("home.load_failed", { message: errorMessage(this._error) }));
      message.setAttribute("role", "alert");
      box.append(message, makeButton(t("home.retry"), { className: "primary", onClick: () => this._retry() }));
      root.append(box);
      return;
    }

    const banners = el("div", "banners");
    // The banners that offer a choice rather than report a problem (see
    // _placeAdvice for where they go).
    const advice = el("div", "banners advice-banners");
    const body = el("div", "body");
    const main = el("div", "main");
    const tabs = el("div", "tab-strip");
    const page = el("div", "main");
    const side = el("aside", "side");
    side.dataset.test = "side";
    const toasts = el("div", "toast-region");
    toasts.setAttribute("aria-live", "polite");
    main.append(tabs, page);
    body.append(main, side);
    root.append(banners, advice, body, toasts);
    Object.assign(this._els, { banners, advice, tabs, page, side, toasts });

    this._renderBanners();
    this._renderTabs();
    this._renderPageArea();
    this._renderSide();
    this._renderToast();
  }

  // The panel moved here from another screen: once the editor has loaded,
  // focus goes to the dashboard's name, or to Back when there is none,
  // unless the person has put focus somewhere meanwhile.
  focusTitleWhenReady() {
    this._titleFocus = true;
  }

  _takeTitleFocus() {
    if (!this._titleFocus) {
      return;
    }
    this._titleFocus = false;
    if (!focusLost()) {
      return;
    }
    const title = this._els.title;
    if (title?.textContent) {
      title.focus();
    } else {
      this._focus("back");
    }
  }

  // The banners that offer a choice (the sidebar and narrow columns) sit
  // above the page on a wide screen. On a phone they are taller than the
  // screen has room for and would push the tablet picture off the first
  // screen, so there they come after the picture, before the card list.
  _placeAdvice(focusKey = this._focusKeyIn(this._els.advice)) {
    const { advice, banners, page, listBlock } = this._els;
    if (!advice || !banners) {
      return;
    }
    if (this._compact && page?.childElementCount) {
      if (listBlock?.parentNode === page) {
        if (advice.nextSibling !== listBlock) {
          listBlock.before(advice);
        }
      } else if (advice.parentNode !== page || advice.nextSibling) {
        page.append(advice);
      }
    } else if (banners.nextSibling !== advice) {
      banners.after(advice);
    }
    // Moving a control takes its focus away; it is given back.
    if (focusKey && !advice.contains(this.shadowRoot.activeElement)) {
      this._focus(focusKey);
    }
  }

  _focusKeyIn(region) {
    const active = this.shadowRoot.activeElement;
    return active && region?.contains(active) ? active.dataset.focus || null : null;
  }

  _renderHeader() {
    const header = this._els.header;
    if (!header) {
      return;
    }
    header.replaceChildren();
    // Home Assistant's menu button shows itself only when the sidebar is
    // out of reach (see the panel's header).
    const menu = document.createElement("ha-menu-button");
    menu.hass = this._hass;
    menu.narrow = this._narrow;
    header.append(menu);
    this._els.menu = menu;
    const back = makeButton(null, {
      className: "back",
      test: "back",
      focus: "back",
      onClick: () => this._back(),
    });
    back.append(icon("mdi:arrow-left"), el("span", null, t("editor.back")));
    const title = screenHeading(this._dashboard?.title || "");
    title.dataset.focus = "title";
    this._els.title = title;
    header.append(back, title);

    if (this._status !== "ready" || this._readOnly) {
      return;
    }
    const actions = el("div", "header-actions");
    const live = el("div", "save-state");
    live.setAttribute("aria-live", "polite");
    const state = el("span", "save-state");
    state.dataset.test = "save-state";
    live.append(state);
    const undo = makeButton(t("undo.undo"), {
      test: "undo",
      focus: "undo",
      focusAlt: "redo",
      onClick: () => this._undo(),
    });
    const redo = makeButton(t("undo.redo"), {
      test: "redo",
      focus: "redo",
      focusAlt: "undo",
      onClick: () => this._redo(),
    });
    actions.append(live, undo, redo);
    header.append(actions);
    Object.assign(this._els, { saveState: state, undo, redo });
    this._updateHeader();
  }

  _updateHeader() {
    const { saveState, undo, redo } = this._els;
    if (!saveState) {
      return;
    }
    const state = this._queue?.state || "saved";
    saveState.dataset.state = state;
    saveState.replaceChildren();
    if (state === "saved") {
      saveState.append(icon("mdi:check"), t("save.saved"));
    } else if (state === "error") {
      saveState.append(icon("mdi:alert-circle-outline"), t("save.error"));
    } else if (state === "paused") {
      saveState.append(t("save.paused"));
    } else {
      saveState.append(t("save.saving"));
    }
    const active = this.shadowRoot.activeElement;
    undo.disabled = !canUndo(this._history);
    redo.disabled = !canRedo(this._history);
    // Undo pressed back to the first step can no longer hold focus.
    if ((active === undo || active === redo) && active.disabled) {
      restoreFocus(this._els.header, active.dataset.focus);
    }
  }

  _saveStateChanged() {
    const state = this._queue?.state;
    const failedNow = state === "error" && this._lastSaveState !== "error";
    this._lastSaveState = state;
    this._updateHeader();
    this._renderBanners();
    if (failedNow) {
      this._revealBanners();
      // A save whose answer was lost with the connection may have been
      // stored all the same: what Home Assistant holds says (see
      // _checkRemote). The read waits while the connection is down.
      this._checkRemote();
    }
  }

  // In the phone layout the card sheet covers the lower part of the screen,
  // so a banner that needs an answer is scrolled into view above it.
  _revealBanners() {
    if (this._compact && this._els.banners?.childElementCount) {
      this._els.banners.scrollIntoView({ block: "start" });
    }
  }

  // Runs draw() on a region and gives focus back to the control that had it,
  // or to the control that stands in for it when it is now disabled. When
  // the control is gone (a banner that was answered), focus goes to the
  // control named by `fallback`, or `fallback()` moves it.
  _keepFocus(region, draw, fallback = null) {
    const active = this.shadowRoot.activeElement;
    const key = active && region?.contains(active) ? active.dataset.focus : null;
    draw();
    if (key && !this.shadowRoot.activeElement) {
      restoreFocus(region, key) ||
        this._focus(key) ||
        (typeof fallback === "function" ? fallback() : fallback && this._focus(fallback));
    }
  }

  _focus(key) {
    const target = [...this.shadowRoot.querySelectorAll("[data-focus]")].find(
      (node) => node.dataset.focus === key && !node.disabled,
    );
    if (target) {
      target.focus();
      return true;
    }
    return false;
  }

  _applyPendingFocus() {
    if (this._pendingFocus && this._focus(this._pendingFocus)) {
      this._pendingFocus = null;
    }
  }

  _renderBanners() {
    const box = this._els.banners;
    if (!box || this._status !== "ready") {
      return;
    }
    this._keepFocus(box, () => {
      box.replaceChildren();

      if (this._readOnly) {
        const note = banner();
        note.append(
          el("p", null, t(this._readOnly === "yaml" ? "editor.read_only_yaml" : "editor.read_only_auto")),
        );
        box.append(note);
      }

      if (this._queue?.state === "error") {
        const failure = banner("error");
        failure.setAttribute("role", "alert");
        failure.append(
          el("p", null, t("save.error_text", { message: errorMessage(this._queue.error) })),
          makeButton(t("save.retry"), {
            className: "primary",
            test: "save-retry",
            focus: "save-retry",
            onClick: () => this._queue.retry(),
          }),
        );
        box.append(failure);
      }

      if (this._conflict) {
        const conflict = banner("error");
        const actions = el("div", "row-buttons");
        const unsure = this._conflictUnsure;
        const mine = makeButton(t("conflict.mine"), {
          className: unsure ? null : "primary",
          test: "conflict-mine",
          focus: "conflict-mine",
          onClick: () => this._keepMine(),
        });
        const theirs = makeButton(t("conflict.theirs"), {
          className: unsure ? "primary" : null,
          test: "conflict-theirs",
          focus: "conflict-theirs",
          onClick: () => this._useTheirs(),
        });
        // When the dashboard may be a new one made in its place, keeping
        // the change could write over it: the other version comes first.
        actions.append(...(unsure ? [theirs, mine] : [mine, theirs]));
        conflict.dataset.test = unsure ? "conflict-unsure" : "conflict";
        conflict.append(
          el("h2", null, t(unsure ? "conflict.unsure_title" : "conflict.title")),
          el("p", null, t(unsure ? "conflict.unsure_text" : "conflict.text")),
          actions,
        );
        box.append(conflict);
      }
      // An answered banner is gone; the page tabs below it come next.
    }, `tab:${this._view}`);
    this._renderAdvice();
  }

  // The sidebar and narrow-columns banners. Each keeps its words next to
  // its buttons, so both choices and the reason for them stay in view.
  _renderAdvice() {
    const box = this._els.advice;
    if (!box || this._status !== "ready") {
      return;
    }
    const text = (title, body) => {
      const words = el("div", "banner-text");
      words.append(el("h2", null, title), el("p", null, body));
      return words;
    };
    this._keepFocus(
      box,
      () => {
        box.replaceChildren();
        if (this._showSidebarNotice()) {
          const notice = banner("advice");
          notice.dataset.test = "sidebar-notice";
          const actions = el("div", "row-buttons");
          actions.append(
            makeButton(t("sidebar.hide"), {
              className: "primary",
              test: "sidebar-hide",
              focus: "sidebar-hide",
              onClick: () => this._hideFromSidebar(),
            }),
            makeButton(t("sidebar.keep"), {
              test: "sidebar-keep",
              focus: "sidebar-keep",
              onClick: () => {
                keepInSidebar(this._urlPath);
                this._sidebarDismissed = true;
                this._renderBanners();
              },
            }),
          );
          notice.append(text(t("sidebar.title"), t("sidebar.text")), actions);
          if (this._sidebarError) {
            const line = el("p", "alert", this._sidebarError);
            line.setAttribute("role", "alert");
            notice.append(line);
          }
          box.append(notice);
        }

        const view = this._draft?.views?.[this._view];
        if (
          !this._readOnly &&
          pageKind(view) === "page" &&
          Array.isArray(view.sections) &&
          view.sections.length > 0 &&
          !usesWholeScreen(this._draft, this._view)
        ) {
          const notice = banner("advice");
          notice.dataset.test = "columns-notice";
          const actions = el("div", "row-buttons");
          actions.append(
            makeButton(t("editor.columns_fix"), {
              test: "use-whole-screen",
              focus: "use-whole-screen",
              onClick: () => {
                this._selected = null;
                this._commit(useWholeScreen(this._draft, this._view));
              },
            }),
          );
          notice.append(text(t("editor.columns_title"), t("editor.columns_text")), actions);
          box.append(notice);
        }
      },
      // An answered banner is gone; focus goes on to what comes next. That
      // is never the other banner's button, where one more Enter would make
      // a choice the person did not read: the page tabs below the banners on
      // a wide screen, the card list below them on a phone.
      () => (this._compact && this._focusFirst(this._els.list)) || this._focus(`tab:${this._view}`),
    );
  }

  _focusFirst(region) {
    const target = region?.querySelector("button:not(:disabled)");
    target?.focus();
    return Boolean(target);
  }

  _showSidebarNotice() {
    return (
      !this._readOnly &&
      this._dashboard?.show_in_sidebar === true &&
      this._dashboard.mode === "storage" &&
      !this._sidebarDismissed &&
      !keptInSidebar().includes(this._urlPath)
    );
  }

  _renderTabs() {
    const strip = this._els.tabs;
    if (!strip) {
      return;
    }
    this._keepFocus(strip, () => {
      strip.replaceChildren();
      const pages = pageList(this._draft);
      const list = el("div", "tabs");
      list.setAttribute("role", "tablist");
      list.setAttribute("aria-label", t("page.tabs_label"));
      for (const page of pages) {
        const selected = page.view === this._view;
        const tab = makeButton(null, { className: "tab", test: "page-tab", focus: `tab:${page.view}` });
        tab.setAttribute("role", "tab");
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
        tab.dataset.view = String(page.view);
        if (page.icon) {
          tab.append(icon(page.icon));
        }
        // A long name is cut short on screen; the tooltip shows all of it.
        const name = page.title || String(page.view + 1);
        tab.title = name;
        tab.append(el("span", "tab-name", name));
        if (page.kind !== "page") {
          tab.append(el("span", "tag", t("page.not_shown")));
        }
        // Pressing the tab of the page shown while a card is selected lets the
        // card go and moves to the page's settings, where it is renamed.
        tab.addEventListener("click", () =>
          page.view === this._view && this._selected ? this._toSettings() : this._selectView(page.view),
        );
        tab.addEventListener("keydown", (event) => this._tabKeys(event, page.view, pages.length));
        list.append(tab);
      }
      strip.append(list);
      if (!this._readOnly) {
        const add = makeButton(null, { className: "add-page", test: "add-page", focus: "add-page", onClick: () => this._addPage() });
        add.append(icon("mdi:plus"), el("span", null, t("page.add")));
        strip.append(add);
      }
    });
  }

  _tabKeys(event, view, count) {
    let next = null;
    if (event.key === "ArrowRight") {
      next = (view + 1) % count;
    } else if (event.key === "ArrowLeft") {
      next = (view - 1 + count) % count;
    } else if (event.key === "Home") {
      next = 0;
    } else if (event.key === "End") {
      next = count - 1;
    }
    if (next === null) {
      return;
    }
    event.preventDefault();
    this._selectView(next);
    this._focus(`tab:${next}`);
  }

  _selectView(view) {
    if (view !== this._view) {
      this._view = view;
      this._screen = 0;
      this._selected = null;
    }
    this._renderBanners();
    this._renderTabs();
    this._renderPageArea();
    this._renderSide();
  }

  _renderPageArea() {
    const area = this._els.page;
    if (!area) {
      return;
    }
    this._stageObserver?.disconnect();
    this._stageObserver = null;
    this._els.pageHost?.__atCleanup?.();
    Object.assign(this._els, {
      stage: null,
      pageHost: null,
      hits: null,
      overlay: null,
      screens: null,
      notes: null,
      list: null,
      listBlock: null,
      hint: null,
      previewError: null,
      addCard: null,
    });
    // On a phone the choice banners are in this area (see _placeAdvice).
    const adviceFocus = this._focusKeyIn(this._els.advice);
    area.replaceChildren();

    const views = Array.isArray(this._draft?.views) ? this._draft.views : [];
    const view = views[this._view];
    const kind = pageKind(view);
    this._areaKey = `${this._view}:${kind}`;
    if (!view) {
      this._placeAdvice(adviceFocus);
      return;
    }

    if (kind !== "page") {
      const box = banner();
      box.dataset.test = "page-box";
      const old = kind === "old_preview";
      box.append(
        el("h2", null, t(old ? "page.old_preview_title" : "page.other_title")),
        el("p", null, t(old ? "page.old_preview_text" : "page.other_text")),
      );
      if (!this._readOnly) {
        box.append(
          makeButton(t("page.remove"), {
            className: "primary",
            test: "page-remove",
            disabled: views.length <= 1,
            onClick: () => this._removePage(this._view, false),
          }),
        );
        if (views.length <= 1) {
          box.append(el("p", "helper", t("page.only_one")));
        }
      }
      area.append(box);
      this._placeAdvice(adviceFocus);
      return;
    }

    const caption = el("div", "caption-row");
    const captionText = el("div");
    // Under the heading: which tablets show this dashboard, and how it is
    // going there (see _fillTabletLines).
    const tabletLines = el("div", "tablet-lines");
    tabletLines.dataset.test = "tablet-lines";
    captionText.append(el("h2", null, t("editor.tablet_label")), tabletLines);
    caption.append(captionText);
    this._els.tabletLines = tabletLines;
    this._fillTabletLines();
    if (!this._readOnly) {
      const add = makeButton(null, {
        className: "primary",
        test: "add-card",
        focus: "add-card",
        onClick: (event) => this._openPicker(event.currentTarget),
      });
      add.append(icon("mdi:plus"), el("span", null, t("editor.add_card")));
      caption.append(add);
      this._els.addCard = add;
    }

    const stage = el("div", "stage");
    stage.dataset.test = "canvas";
    // The drawn tablet is a picture: screen readers and the keyboard use the
    // named card buttons of the hit layer above it instead.
    // It is drawn in a shadow root that holds the tablet's styles and none
    // of the editor's, so it looks the same as it does on a dashboard.
    const pageFrame = el("div", "page-host");
    pageFrame.setAttribute("aria-hidden", "true");
    pageFrame.inert = true;
    const pageRoot = pageFrame.attachShadow({ mode: "open" });
    const pageStyle = el("style");
    pageStyle.textContent = rendererStyles + canvasStyles;
    const pageHost = el("div");
    pageRoot.append(pageStyle, pageHost);
    const hits = el("div", "hit-layer");
    hits.setAttribute("role", "group");
    hits.setAttribute("aria-label", t("a11y.canvas"));
    const overlay = el("div");
    stage.append(pageFrame, hits, overlay);
    // A press on the picture outside every card clears the selection.
    stage.addEventListener("click", (event) => {
      if (this._selected && !event.target.closest("button")) {
        this._select(null);
      }
    });

    // Right above the picture, where it is seen first: how many cards on
    // this page the tablet leaves out (see _renderHint).
    const hint = el("div", "hint-box");
    const screens = el("div", "screens");
    const previewError = el("div");
    const notes = el("div", "notes");
    const listBlock = el("section", "list-block");
    const list = el("ol", "card-list");
    listBlock.append(el("h2", null, t("list.title")), list);

    area.append(caption, hint, stage, screens, previewError, notes, listBlock);
    Object.assign(this._els, { stage, pageHost, hits, overlay, screens, notes, list, listBlock, hint, previewError });
    this._placeAdvice(adviceFocus);

    this._stageObserver = new ResizeObserver(() => {
      cancelAnimationFrame(this._frame);
      this._frame = requestAnimationFrame(() => this._drawCanvas());
    });
    this._stageObserver.observe(stage);

    this._drawCanvas();
    this._renderScreens();
    this._renderPreviewError();
    this._renderNotes();
    this._renderList();
  }

  _drawCanvas() {
    const { stage, pageHost, hits, overlay } = this._els;
    if (!stage) {
      return;
    }
    const focused = this.shadowRoot.activeElement;
    const focusKey = focused && hits.contains(focused) ? focused.dataset.focus : null;
    pageHost.__atCleanup?.();
    pageHost.replaceChildren();
    hits.replaceChildren();
    overlay.replaceChildren();

    if (!this._preview) {
      overlay.append(el("div", "stage-message", t("editor.loading")));
      return;
    }
    const width = stage.getBoundingClientRect().width;
    if (!width) {
      return;
    }
    const scale = width / 1280;
    const layout = this._preview.layout || {};
    const screens = pageScreens(this._preview, this._view);
    const screenIndex = screens[this._screen] ?? -1;
    renderPage(
      pageHost,
      layout,
      screenIndex,
      { values: this._preview.values || {}, errors: {} },
      { sx: scale, sy: scale, interactive: false, tablet: true },
    );

    const page = layout.pages?.[screenIndex];
    const omitted = page ? omittedOnPage(this._preview, page.id) : [];
    // A page with no cards is still a page on the tablet, with its side bar
    // entry; here it gets the "add the first card" help. A page whose only
    // card was left out is not empty: it gets that card's box below.
    if (!page || !Array.isArray(page.w) || (!page.w.length && !omitted.length)) {
      const empty = el("div", "empty-page");
      empty.style.color = layout.theme?.tx || "#E8EAED";
      empty.append(el("p", null, t("editor.empty_page")));
      if (!this._readOnly) {
        empty.append(
          makeButton(t("editor.add_first_card"), {
            className: "primary",
            test: "add-first-card",
            focus: "add-first-card",
            onClick: (event) => this._openPicker(event.currentTarget),
          }),
        );
        empty.append(el("p", "small", t("editor.empty_page_tablet")));
      }
      overlay.append(empty);
      this._applyPendingFocus();
      return;
    }

    const sources = isObject(this._preview.sources) ? this._preview.sources : {};
    const items = (page.w || []).filter((item) => Object.hasOwn(sources, String(item.id)));
    const count = items.length + omitted.length;
    const wall = pageHost.querySelector(".at-page");
    let n = 0;

    for (const item of items) {
      n += 1;
      this._hitButton(sources[String(item.id)], item.r, scale, n, count, item.t === "heading" ? item.text : null);
    }
    for (const warning of omitted) {
      n += 1;
      const box = el("div", "warning-box", t("preview.omitted"));
      box.style.left = `${warning.r[0] * scale}px`;
      box.style.top = `${warning.r[1] * scale}px`;
      box.style.width = `${warning.r[2] * scale}px`;
      box.style.height = `${warning.r[3] * scale}px`;
      wall?.append(box);
      this._hitButton([warning.view, warning.section, warning.card], warning.r, scale, n, count, null);
    }

    if (focusKey && !this.shadowRoot.activeElement) {
      this._focus(focusKey);
    }
    this._applyPendingFocus();
    this._queuePlaceToast();
  }

  _hitButton(source, rect, scale, n, count, headingText) {
    if (!Array.isArray(source) || !Array.isArray(rect)) {
      return;
    }
    const key = sourceKey(source);
    const button = makeButton(null, { className: "hit", test: "hit", focus: `hit:${key}` });
    button.dataset.source = key;
    button.style.left = `${rect[0] * scale}px`;
    button.style.top = `${rect[1] * scale}px`;
    button.style.width = `${rect[2] * scale}px`;
    button.style.height = `${rect[3] * scale}px`;
    button.setAttribute("aria-pressed", String(sameSource(source, this._selected)));
    button.setAttribute("aria-label", this._itemLabel(source, n, count, headingText));
    // Pressing the selected card again lets it go, which brings back the
    // page and dashboard settings.
    button.addEventListener("click", () => this._select(sameSource(source, this._selected) ? null : source));
    button.addEventListener("keydown", (event) => this._itemKeys(event, source, "hit"));
    this._els.hits.append(button);
  }

  _itemLabel(source, n, count, headingText) {
    const card = getCard(this._draft, source);
    if (source[2] === null || card?.type === "heading") {
      return t("a11y.heading", { text: headingText ?? card?.heading ?? "" });
    }
    const component = componentOf(card, this._library);
    const row = this._rows.find((entry) => sameSource(entry.source, source));
    const name = card?.title || component?.name || String(card?.type || "").replace(/^custom:/, "");
    const device = deviceText(this._hass, row?.entities || []) || t("list.no_device");
    return t("a11y.card", { name, device, n, count });
  }

  _updateHitSelection() {
    for (const button of this._els.hits?.querySelectorAll(".hit") || []) {
      button.setAttribute("aria-pressed", String(button.dataset.source === this._selectedKey()));
    }
    this._queuePlaceToast();
  }

  _selectedKey() {
    return this._selected ? sourceKey(this._selected) : null;
  }

  _renderScreens() {
    const box = this._els.screens;
    if (!box) {
      return;
    }
    this._keepFocus(box, () => {
      box.replaceChildren();
      const count = pageScreens(this._preview, this._view).length;
      if (count <= 1) {
        return;
      }
      const go = (delta) => {
        this._screen = Math.min(count - 1, Math.max(0, this._screen + delta));
        this._drawCanvas();
        this._renderScreens();
      };
      const previous = makeButton(null, {
        test: "screen-prev",
        focus: "screen-prev",
        focusAlt: "screen-next",
        ariaLabel: t("editor.screen_prev"),
        disabled: this._screen <= 0,
        onClick: () => go(-1),
      });
      previous.append(icon("mdi:chevron-left"));
      const next = makeButton(null, {
        test: "screen-next",
        focus: "screen-next",
        focusAlt: "screen-prev",
        ariaLabel: t("editor.screen_next"),
        disabled: this._screen >= count - 1,
        onClick: () => go(1),
      });
      next.append(icon("mdi:chevron-right"));
      box.append(
        el("span", null, t("editor.screens", { n: this._screen + 1, count })),
        previous,
        next,
        el("p", "small", t("editor.screens_note", { count })),
      );
    });
  }

  _renderPreviewError() {
    const box = this._els.previewError;
    if (!box) {
      return;
    }
    box.replaceChildren();
    if (!this._previewError) {
      return;
    }
    const line = el("p", "alert", t("editor.preview_failed", { message: errorMessage(this._previewError) }));
    line.setAttribute("role", "alert");
    box.append(line, makeButton(t("editor.preview_retry"), { onClick: () => this._requestPreview() }));
  }

  _renderNotes() {
    const box = this._els.notes;
    if (!box) {
      return;
    }
    box.replaceChildren();
    const codes = [...pageNotes(this._preview, this._view)];
    if (this._view === 0) {
      codes.push(...dashboardNotes(this._preview));
    }
    for (const code of codes) {
      box.append(el("p", "small", t(`warn.${code}`, { detail: "" })));
    }
  }

  _rowName(row) {
    if (row.kind === "tab") {
      return row.component?.name || row.type;
    }
    if (row.kind === "heading") {
      return t("list.heading", { text: row.title });
    }
    if (row.kind === "tab_missing") {
      return t("list.unknown_card");
    }
    if (row.kind === "old_preview") {
      return t("list.old_preview");
    }
    return t("list.other_card", { type: row.type.replace(/^custom:/, "") || "?" });
  }

  _rowIcon(row) {
    if (row.kind === "tab") {
      return row.component?.icon;
    }
    if (row.kind === "heading") {
      return "mdi:format-title";
    }
    if (row.kind === "old_preview") {
      return "mdi:tablet";
    }
    return "mdi:card-off-outline";
  }

  _showMoveToPage(source) {
    this._select(source, { sheet: true });
    const field = this._els.side?.querySelector('[data-test="move-page"]');
    if (field) {
      field.focus({ preventScroll: true });
      field.scrollIntoView({ block: "nearest" });
    }
  }

  _renderList() {
    const list = this._els.list;
    if (!list) {
      this._rows = pageItems(this._draft, this._view, this._library, this._preview);
      return;
    }
    this._rows = pageItems(this._draft, this._view, this._library, this._preview);
    // A row that has gone (Use the whole screen turns section titles into
    // heading cards) hands focus to the first row, or to Add card.
    const fallback = () => this._focusFirst(list) || this._focus("add-card");
    this._keepFocus(list, () => {
      list.replaceChildren();
      if (!this._rows.length) {
        list.append(el("li", "small", t("list.empty")));
        return;
      }
      const loaded = Boolean(this._preview);
      for (const row of this._rows) {
        const item = el("li");
        const button = makeButton(null, { className: "list-row", test: "list-row", focus: `row:${row.key}` });
        button.dataset.source = row.key;
        button.dataset.shown = String(row.shown);
        if (row.key === this._selectedKey()) {
          button.setAttribute("aria-current", "true");
        }
        button.append(icon(this._rowIcon(row)), el("span", "row-name", this._rowName(row)));
        if (row.kind === "tab") {
          button.append(el("span", "row-device", deviceText(this._hass, row.entities) || t("list.no_device")));
        } else if (row.entities.length) {
          // What a card the tablet cannot draw was for, so the person knows
          // which device to add back with a TAB-1 card.
          button.append(el("span", "row-device", deviceText(this._hass, row.entities)));
        }
        if (loaded && !row.shown) {
          button.append(
            el("span", "tag", t("list.not_shown")),
            el("span", "row-reason", t(`warn.${row.reason}`, { detail: row.detail || "" })),
          );
        }
        button.addEventListener("click", () => this._select(row.source, { sheet: true }));
        button.addEventListener("keydown", (event) => this._itemKeys(event, row.source, "row"));
        item.append(button);
        // The row's buttons stay together, so on a narrow screen they move
        // below the row as one, at its right-hand end.
        const actions = el("div", "row-actions");
        // A dial or graph over a screen's limit fits on another page; this
        // opens its form at "Move to page".
        if (loaded && !row.shown && !this._readOnly && row.kind === "tab" && /^over_budget_(arcs|charts)$/.test(row.reason)) {
          actions.append(
            makeButton(t("list.move"), {
              className: "row-move",
              test: "row-move",
              focus: `move:${row.key}`,
              onClick: () => this._showMoveToPage(row.source),
            }),
          );
        }
        if (loaded && !row.shown && !this._readOnly) {
          actions.append(
            makeButton(t("list.remove"), {
              className: "row-remove",
              test: "row-remove",
              focus: `remove:${row.key}`,
              onClick: () => this._removeItem(row.source),
            }),
          );
        }
        if (actions.childElementCount) {
          item.append(actions);
        }
        list.append(item);
      }
    }, fallback);
    this._renderHint();
    this._applyPendingFocus();
    this._queuePlaceToast();
  }

  // Above the picture: "1 card on this page is not shown on the tablet.",
  // with a button down to that card in the list, which says why and offers
  // Remove. The picture alone cannot show a card it leaves out.
  _renderHint() {
    const box = this._els.hint;
    if (!box) {
      return;
    }
    const hidden = this._preview ? this._rows.filter((row) => !row.shown).length : 0;
    this._keepFocus(
      box,
      () => {
        box.replaceChildren();
        if (!hidden) {
          return;
        }
        const line = el("p", "note-line not-shown-hint");
        line.dataset.test = "not-shown-hint";
        const words = el(
          "span",
          null,
          hidden === 1 ? t("editor.not_shown_one") : t("editor.not_shown_many", { count: hidden }),
        );
        words.id = uid("not-shown");
        const go = makeButton(t("editor.not_shown_go"), {
          className: "link",
          test: "not-shown-go",
          focus: "not-shown-go",
          onClick: () => this._goToHidden(),
        });
        go.setAttribute("aria-describedby", words.id);
        line.append(words, go);
        box.append(line);
      },
      "add-card",
    );
  }

  // Brings the first card the tablet leaves out into view in the list and
  // gives it focus.
  _goToHidden() {
    const row = this._els.list?.querySelector('[data-test="list-row"][data-shown="false"]');
    if (row) {
      row.scrollIntoView({ block: "center" });
      row.focus({ preventScroll: true });
    }
  }

  _renderSide() {
    const side = this._els.side;
    if (!side || this._status !== "ready") {
      return;
    }
    const draft = this._draft;
    const source = this._selected;
    const card = source ? getCard(draft, source) : null;
    const sheet = Boolean(this._compact && card);
    side.classList.toggle("sheet", sheet);
    this._els.root.classList.toggle("sheet-open", sheet);
    this._els.sideNotes = null;
    this._els.shownOn = null;

    this._keepFocus(side, () => {
      side.replaceChildren();
      if (card) {
        // Every new card is selected, which hides "This page" and "This
        // dashboard" (the dashboard's theme). Both buttons bring them back;
        // the first says so and moves to them.
        const top = el("div", "side-top");
        const settings = makeButton(null, {
          className: "link side-back",
          test: "to-settings",
          focus: "to-settings",
          onClick: () => this._toSettings(),
        });
        settings.append(icon("mdi:arrow-left"), el("span", null, t("editor.to_settings")));
        const close = makeButton(null, {
          className: "sheet-close",
          test: "close-panel",
          focus: "close-panel",
          onClick: () => this._closeForm(),
        });
        close.append(icon("mdi:close"), el("span", null, t("editor.close_panel")));
        top.append(settings, close);
        side.append(top);
        const form = this._itemForm(source, card);
        side.append(form);
        this._els.sideNotes = form.querySelector(".item-notes");
        this._fillSideNotes();
        this._sideToTop(sourceKey(source));
        return;
      }
      this._sideToTop(`page:${this._view}`);

      const views = Array.isArray(draft?.views) ? draft.views : [];
      const view = views[this._view];
      // A page the tablet does not show has no picture and no cards to press.
      if (view && pageKind(view) !== "page") {
        const line = el("p", null, t("editor.page_not_shown"));
        line.dataset.test = "side-intro";
        side.append(line);
      } else if (!this._readOnly) {
        const line = el("p", null, t("editor.nothing_selected"));
        line.dataset.test = "side-intro";
        side.append(line);
      }
      if (!this._readOnly && pageKind(view) === "page") {
        const vi = this._view;
        side.append(
          buildPageSettings({
            title: typeof view.title === "string" ? view.title : "",
            icon: view.icon,
            index: vi,
            count: views.length,
            onRename: (text) =>
              this._commit(renamePage(this._draft, vi, text), {
                key: `${vi}:page-name`,
                continuous: true,
                side: false,
              }),
            onIcon: (name) => this._commit(setPageIcon(this._draft, vi, name)),
            onMove: (delta) => {
              const result = movePage(this._draft, vi, delta);
              this._view = result.view;
              this._commit(result.config);
            },
            onDelete: () => this._removePage(vi, true),
          }),
        );
      }
      side.append(
        buildDashboardSettings({
          readOnly: Boolean(this._readOnly),
          title: this._dashboard?.title || "",
          themes: this._library?.themes || [],
          themeId: this._themeId(),
          shownOn: this._shownOnBlock(),
          showInSidebar: this._dashboard?.show_in_sidebar === true,
          onRename: (title) => this._updateDashboard({ title }),
          onTheme: (themeId) => this._commit(setTheme(this._draft, themeId), { side: false }),
          onSidebar: async (show) => {
            // Ticking the box is already the answer the sidebar notice asks for.
            if (show) {
              this._sidebarDismissed = true;
              keepInSidebar(this._urlPath);
            }
            await this._updateDashboard({ show_in_sidebar: show });
          },
          onDelete: () => this._deleteDashboard(),
        }),
      );
    });
    this._queuePlaceToast();
  }

  // A different item starts at the top of the side panel; the same item
  // drawn again (after undo or a new preview) keeps where it was scrolled to.
  _sideToTop(key) {
    if (key !== this._sideKey) {
      this._sideKey = key;
      if (this._els.side) {
        this._els.side.scrollTop = 0;
      }
    }
  }

  _itemForm(source, card) {
    const key = sourceKey(source);
    const kind = source[2] === null ? "heading" : cardKind(card, this._library);
    const readOnly = Boolean(this._readOnly);
    const remove = () => this._removeItem(source);
    const move = (delta) => this._move(source, delta, "form");

    if (kind === "tab") {
      const component = componentOf(card, this._library);
      return buildCardForm({
        hass: this._hass,
        config: this._draft,
        card,
        component,
        readOnly,
        compact: this._compact,
        themes: this._library?.themes || [],
        dashboardTheme: this._themeId(),
        maxWide: maxUnitsWide(this._draft, source),
        canEarlier: canMove(this._draft, source, -1),
        canLater: canMove(this._draft, source, 1),
        // The other pages the tablet shows, which a card can move to.
        pages: pageList(this._draft).filter((page) => page.view !== source[0] && page.kind === "page"),
        onMoveToPage: (target) => this._moveToPage(source, target),
        onParam: (name, value, continuous) => {
          const current = getCard(this._draft, source);
          const params = { ...(isObject(current?.params) ? current.params : {}) };
          if (value === undefined) {
            delete params[name];
          } else {
            params[name] = value;
          }
          this._commit(updateCard(this._draft, source, { params }), {
            key: continuous ? `${key}:param:${name}` : null,
            continuous,
            side: false,
          });
        },
        onTitle: (text) =>
          this._commit(updateCard(this._draft, source, { title: text }), {
            key: `${key}:title`,
            continuous: true,
            side: false,
          }),
        onResize: (w, h) => this._commit(resizeCard(this._draft, source, w, h), { side: false }),
        onStyle: (style, field, continuous) =>
          this._commit(updateCard(this._draft, source, { style }), {
            key: continuous ? `${key}:${field}` : null,
            continuous,
            side: false,
          }),
        onMove: move,
        onRemove: remove,
        onWholeScreen: () => this._wholeScreenFor(source),
      });
    }
    if (kind === "heading") {
      const isCard = source[2] !== null;
      return buildHeadingForm({
        readOnly,
        isCard,
        text: String(card.heading ?? ""),
        canEarlier: isCard && canMove(this._draft, source, -1),
        canLater: isCard && canMove(this._draft, source, 1),
        onText: (text) =>
          this._commit(setHeadingText(this._draft, source, text), {
            key: `${key}:heading`,
            continuous: true,
            side: false,
          }),
        onMove: move,
        onRemove: remove,
      });
    }
    const row = this._rows.find((entry) => entry.key === key);
    return buildOtherForm({
      readOnly,
      name: row ? this._rowName(row) : "",
      device: row ? deviceText(this._hass, row.entities) : "",
      onRemove: remove,
    });
  }

  _fillSideNotes() {
    const container = this._els.sideNotes;
    if (!container || !this._selected) {
      return;
    }
    const row = this._rows.find((entry) => entry.key === this._selectedKey());
    fillItemNotes(container, this._preview ? row : null, {
      onOpenAdvanced: this._readOnly ? null : () => this._openAdvanced(),
    });
  }

  // A toast redrawn or taken away while one of its buttons has focus hands
  // focus on to Add card or the tab of the page shown, never to a button
  // that removes something. refocus: false when the toast's own button
  // moves focus itself.
  _renderToast({ refocus = true } = {}) {
    const region = this._els.toasts;
    if (!region) {
      return;
    }
    const hadFocus = region.contains(this.shadowRoot.activeElement);
    this._drawToast(region);
    if (refocus && hadFocus && !this.shadowRoot.activeElement) {
      this._focus("add-card") || this._focus(`tab:${this._view}`);
    }
  }

  _drawToast(region) {
    region.replaceChildren();
    if (!this._toast) {
      return;
    }
    const shown = this._toast;
    const toast = el("div", "toast");
    toast.dataset.test = "toast";
    toast.append(el("span", null, shown.text));
    if (shown.devices) {
      const hold = () => {
        if (this._toast === shown) {
          clearTimeout(this._toastTimer);
        }
      };
      const release = () => {
        // Checked once the move has finished, so moving between the
        // toast's own buttons keeps it.
        setTimeout(() => {
          const inside = toast.matches(":hover") || toast.contains(this.shadowRoot.activeElement);
          if (this._toast === shown && toast.isConnected && !inside) {
            this._hideToastLater();
          }
        });
      };
      toast.addEventListener("focusin", hold);
      toast.addEventListener("pointerenter", hold);
      toast.addEventListener("focusout", release);
      toast.addEventListener("pointerleave", release);
      toast.append(
        makeButton(t("toast.add_for"), {
          test: "toast-replace",
          onClick: () => {
            this._toast = null;
            this._renderToast({ refocus: false });
            // Cancelling the picker leaves focus on Add card.
            this._openPicker(this._els.addCard, shown.devices);
          },
        }),
      );
    }
    if (shown.undo) {
      toast.append(
        makeButton(t("toast.undo"), {
          test: "toast-undo",
          onClick: () => {
            this._toast = null;
            this._renderToast({ refocus: false });
            this._undo();
            // The toast is gone; focus goes to what Undo brought back.
            if (!this.shadowRoot.activeElement) {
              this._focusAfterUndo(shown.restore);
            }
          },
        }),
      );
    }
    region.append(toast);
    this._placeToast();
  }

  // Puts the toast where it covers nothing the person is working with: the
  // card sheet or side panel, the control that has focus (the field being
  // typed in, the button just pressed) and the selected card, on the
  // picture and in the list. It sits at the bottom of the screen, above the
  // card sheet when that is open. When that would cover one of them it
  // moves over the page's own column, to the top of the screen, or into a
  // gap between them.
  _placeToast() {
    const region = this._els.toasts;
    const toast = region?.firstElementChild;
    if (!toast || !region.isConnected) {
      return;
    }
    // A toast under the pointer or with focus stays put, so its button is
    // still there when it is pressed.
    if (toast.matches(":hover") || toast.contains(this.shadowRoot.activeElement)) {
      return;
    }
    const rectOf = (node) => (node?.isConnected ? node.getBoundingClientRect() : null);
    const { side, hits, list, page, header } = this._els;
    const sheet = side?.classList.contains("sheet") ? rectOf(side) : null;
    const active = this.shadowRoot.activeElement;
    const keep = [
      sheet || (this._compact ? null : rectOf(side)),
      active && !region.contains(active) ? rectOf(active) : null,
      rectOf(hits?.querySelector('.hit[aria-pressed="true"]')),
      rectOf(list?.querySelector('[aria-current="true"]')),
    ].filter((rect) => rect && rect.width && rect.height);

    // On a phone the on-screen keyboard shrinks the visible part of the
    // page, not the window: the toast stays inside the visible part.
    const view = window.visualViewport;
    const viewTop = view ? view.offsetTop : 0;
    const width = document.documentElement.clientWidth || innerWidth;
    const height = view ? view.offsetTop + view.height : innerHeight;
    // Sideways the toast stays inside the editor itself, 16 px from its
    // edges, never under Home Assistant's sidebar docked beside it.
    const rect = this.getBoundingClientRect();
    const own = rect.width > 64 ? rect : { left: 0, right: width };
    const minLeft = Math.max(0, own.left) + 16;
    const maxRight = Math.min(width, own.right) - 16;
    region.style.maxWidth = `${Math.max(0, maxRight - minLeft)}px`;
    const { width: w, height: h } = toast.getBoundingClientRect();
    const headerBox = rectOf(header);
    const bottom = (sheet ? Math.min(height, sheet.top) - 12 : height - 16) - h;
    const top = Math.max(viewTop + 12, headerBox && headerBox.bottom > 0 ? headerBox.bottom + 8 : 0);
    const middles = [(minLeft + maxRight) / 2];
    const column = this._compact ? null : rectOf(page);
    if (column) {
      middles.push((column.left + column.right) / 2);
    }
    // When the bottom and the top both cover something, as on a phone with
    // the new card at the top of the picture and its row just above the
    // sheet, the toast can sit just above or below each of those instead.
    const heights = [
      ["bottom", bottom],
      ["top", top],
    ];
    for (const rect of keep) {
      heights.push(["between", rect.bottom + 8], ["between", rect.top - 8 - h]);
    }
    const spots = [];
    for (const [place, y] of heights) {
      if (place === "between" && (y < top || y > bottom)) {
        continue;
      }
      for (const middle of middles) {
        spots.push({ place, top: y, left: Math.max(minLeft, Math.min(middle - w / 2, maxRight - w)) });
      }
    }
    // How much of what must stay in view a spot would cover.
    const covered = (spot) =>
      keep.reduce((sum, rect) => {
        const x = Math.min(spot.left + w, rect.right) - Math.max(spot.left, rect.left);
        const y = Math.min(spot.top + h, rect.bottom, height) - Math.max(spot.top, rect.top, viewTop);
        return sum + Math.max(0, x) * Math.max(0, y);
      }, 0);
    let best = spots[0];
    let least = covered(best);
    for (const spot of spots.slice(1)) {
      const area = least ? covered(spot) : Infinity;
      if (area < least) {
        best = spot;
        least = area;
      }
    }

    Object.assign(region.style, { transform: "none", bottom: "auto", left: `${best.left}px`, top: `${best.top}px` });
    // Inside a transformed parent "fixed" is measured from that parent, so
    // the region is moved by however far it ended up from the spot.
    const landed = region.getBoundingClientRect();
    if (Math.abs(landed.left - best.left) > 1 || Math.abs(landed.top - best.top) > 1) {
      region.style.left = `${2 * best.left - landed.left}px`;
      region.style.top = `${2 * best.top - landed.top}px`;
    }
    region.dataset.place = best.place;
  }

  // Places the toast again once the page has settled, after a scroll, a
  // new focus or a new drawing of the picture.
  _queuePlaceToast() {
    if (!this._toast || this._toastFrame) {
      return;
    }
    this._toastFrame = requestAnimationFrame(() => {
      this._toastFrame = 0;
      this._placeToast();
    });
  }

  // devices ({entities, name}): devices on no card now; the toast then
  // offers a TAB-1 card for them. restore: the focus key of what the toast's
  // Undo brings back (see _focusAfterUndo).
  // tied: the toast offers a step about the change just made (Undo, a card
  // for the devices left over, or Undo in the header for a version from
  // somewhere else). Such a toast goes as soon as the history moves on (see
  // _draftChanged), so it never acts on a later change.
  _showToast(text, { undo = false, devices = null, restore = null, tied = undo || Boolean(devices) } = {}) {
    this._toast = { text, undo, devices, restore, tied, history: this._history };
    this._renderToast();
    this._hideToastLater();
  }

  _dropStaleToast() {
    if (this._toast?.tied && this._toast.history !== this._history) {
      clearTimeout(this._toastTimer);
      this._toast = null;
      this._renderToast();
    }
  }

  // After Undo in a toast, focus goes to the card that came back (its row in
  // the card list, scrolled into view), or to the tab of the page shown. In
  // the phone layout an open card sheet covers the list, so the sheet's
  // title takes focus then.
  _focusAfterUndo(key) {
    const side = this._els.side;
    if (side?.classList.contains("sheet")) {
      side.querySelector(".side-title")?.focus({ preventScroll: true });
      return;
    }
    const nodes = [...this.shadowRoot.querySelectorAll("[data-focus]")];
    for (const name of [key, `tab:${this._view}`]) {
      const target = name ? nodes.find((node) => node.dataset.focus === name && !node.disabled) : null;
      if (target) {
        target.focus({ preventScroll: true });
        target.scrollIntoView({ block: "nearest" });
        return;
      }
    }
  }

  _hideToastLater() {
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(
      () => {
        this._toast = null;
        this._renderToast();
      },
      this._toast?.devices ? TOAST_ACTION_MS : TOAST_MS,
    );
  }

  // ---- changes ---------------------------------------------------------

  _themeId() {
    const theme = this._draft?.apollo_tab?.theme;
    return typeof theme === "string" && theme ? theme : DEFAULT_THEME;
  }

  // Records a new draft. side: false keeps the side panel as it is, so
  // typing into it is never interrupted.
  _commit(config, { key = null, continuous = false, side = true } = {}) {
    if (this._readOnly) {
      return false;
    }
    const before = this._history;
    this._history = historyPush(this._history, config, { key, now: Date.now() });
    if (this._history === before) {
      return false;
    }
    this._draftChanged({ continuous, side });
    return true;
  }

  _draftChanged({ continuous = false, side = true } = {}) {
    const draft = this._draft;
    this._queue?.push(draft);
    if (continuous) {
      clearTimeout(this._previewTimer);
      this._previewTimer = setTimeout(() => this._requestPreview(), PREVIEW_DEBOUNCE_MS);
    } else {
      this._requestPreview();
    }

    const count = pageList(draft).length;
    if (this._view >= count) {
      this._view = Math.max(0, count - 1);
      this._screen = 0;
    }
    let rebuildSide = side;
    if (this._selected && !getCard(draft, this._selected)) {
      this._selected = null;
      rebuildSide = true;
    }

    this._updateHeader();
    this._renderBanners();
    this._renderTabs();
    const kind = pageKind(draft?.views?.[this._view]);
    if (this._areaKey !== `${this._view}:${kind}`) {
      this._renderPageArea();
    } else {
      this._renderList();
      this._updateHitSelection();
    }
    if (rebuildSide) {
      this._renderSide();
    }
    // Last, so focus that was in the toast has somewhere to go.
    this._dropStaleToast();
  }

  async _requestPreview() {
    clearTimeout(this._previewTimer);
    this._previewTimer = null;
    if (!this._conn || this._status !== "ready") {
      return;
    }
    const seq = ++this._previewSeq;
    const run = this._run;
    try {
      const preview = await previewLayout(this._conn, this._draft);
      if (seq !== this._previewSeq || run !== this._run || this._status !== "ready") {
        return;
      }
      this._preview = preview;
      this._previewError = null;
      const screens = pageScreens(preview, this._view);
      if (this._screenFor) {
        const row = pageItems(this._draft, this._view, this._library, preview).find(
          (entry) => entry.key === this._screenFor,
        );
        const index = row ? this._screenIndex(row.source, row, preview) : -1;
        if (index >= 0) {
          this._screen = index;
        }
        this._screenFor = null;
      }
      this._screen = Math.min(this._screen, Math.max(0, screens.length - 1));
      if (this._selected && !getCard(this._draft, this._selected)) {
        this._selected = null;
        this._renderSide();
      }
      this._renderList();
      this._drawCanvas();
      this._renderScreens();
      this._renderNotes();
      this._renderPreviewError();
      this._fillSideNotes();
      if (this._revealOnPreview) {
        this._revealOnPreview = false;
        this._revealSelection();
      }
    } catch (error) {
      if (seq !== this._previewSeq || run !== this._run) {
        return;
      }
      if (error?.code === "not_loaded") {
        this._fail(error);
        return;
      }
      this._previewError = error;
      this._renderPreviewError();
    }
  }

  _select(source, { sheet = false } = {}) {
    this._selected = source ? [...source] : null;
    // A card chosen in the list may be drawn on another screen of the page,
    // or left out there; show that screen, so the card, or its hatched box,
    // and its changes are on the picture.
    const row = source ? this._rows.find((entry) => sameSource(entry.source, source)) : null;
    const screens = pageScreens(this._preview, this._view);
    const shownHere = row?.widgets.some((widget) => widget.screen === screens[this._screen]);
    const index = source && !shownHere ? this._screenIndex(source, row, this._preview) : -1;
    if (index >= 0 && index !== this._screen) {
      this._screen = index;
      this._drawCanvas();
      this._renderScreens();
    } else {
      this._updateHitSelection();
    }
    this._renderList();
    this._renderSide();
    if (source && sheet && this._compact) {
      this._els.side?.querySelector(".side-title")?.focus({ preventScroll: true });
    }
    this._revealSelection();
  }

  // In the one-column layout the open card sheet covers the bottom of the
  // screen, and the browser scrolls a control that gets focus into view
  // without minding it. A control outside the sheet that would end up under
  // it is scrolled up to just above it, so focus is always seen. Checked
  // again a frame later, after any scrolling of the browser's own.
  _clearOfSheet(target, again = true) {
    const side = this._els.side;
    if (
      !this._compact ||
      !side?.classList.contains("sheet") ||
      !(target instanceof Element) ||
      side.contains(target) ||
      target.closest("dialog") ||
      this._els.toasts?.contains(target)
    ) {
      return;
    }
    const sheet = side.getBoundingClientRect();
    const rect = target.getBoundingClientRect();
    // Up far enough for its bottom to clear the sheet, but never so far
    // that its top leaves the screen.
    const delta = Math.min(rect.bottom - sheet.top + 16, rect.top - 8);
    if (rect.height && rect.bottom > sheet.top && delta > 0) {
      this._scrollerOf(target).scrollBy(0, delta);
    }
    if (again) {
      requestAnimationFrame(() => {
        if (this.shadowRoot.activeElement === target) {
          this._clearOfSheet(target, false);
        }
      });
    }
  }

  // The nearest box around `node` that scrolls up and down, crossing out of
  // shadow roots; the window when there is none.
  _scrollerOf(node) {
    let box = node.parentNode;
    while (box) {
      if (box instanceof ShadowRoot) {
        box = box.host;
        continue;
      }
      if (box === document.body || box === document.documentElement || !(box instanceof Element)) {
        break;
      }
      const overflow = getComputedStyle(box).overflowY;
      if (/(auto|scroll)/.test(overflow) && box.scrollHeight > box.clientHeight + 1) {
        return box;
      }
      box = box.parentNode;
    }
    return window;
  }

  // Which of the page's screens holds the item at `source` (its list row
  // is `row`): the first one it is drawn on, or the one with its hatched
  // "Left out" box. -1 when none does.
  _screenIndex(source, row, preview) {
    const screens = pageScreens(preview, this._view);
    if (row?.widgets.length) {
      return screens.indexOf(row.widgets[0].screen);
    }
    const box = (Array.isArray(preview?.warnings) ? preview.warnings : []).find(
      (warning) =>
        warningBoxKind(warning) === "omitted" && sameSource([warning.view, warning.section, warning.card], source),
    );
    if (!box) {
      return -1;
    }
    const pages = Array.isArray(preview?.layout?.pages) ? preview.layout.pages : [];
    return screens.findIndex((index) => pages[index]?.id === box.page);
  }

  // In the one-column layout the card sheet covers the lower part of the
  // screen. Scroll the tablet picture (or, when it is taller than the space
  // left, the selected card) into the band above the sheet, so every change
  // made in the sheet can be seen on the picture.
  _revealSelection() {
    const { stage, side, hits } = this._els;
    if (!this._compact || !this._selected || !stage || !side?.classList.contains("sheet")) {
      return;
    }
    const band = side.getBoundingClientRect().top;
    const hit = hits?.querySelector('.hit[aria-pressed="true"]');
    const fits = stage.getBoundingClientRect().height <= band - 16;
    const target = fits || !hit ? stage : hit;
    const rect = target.getBoundingClientRect();
    if (rect.top >= 0 && rect.bottom <= band) {
      return;
    }
    target.scrollIntoView({ block: "start", inline: "nearest" });
  }

  _closeForm() {
    const key = this._selectedKey();
    this._select(null);
    if (key) {
      this._focus(`row:${key}`) || this._focus(`hit:${key}`);
    }
  }

  // Lets the card go and moves to "This page" and "This dashboard". In the
  // phone layout they are below the card list, so they are scrolled to.
  _toSettings() {
    this._select(null);
    const heading = this._els.side?.querySelector('[data-test="settings-heading"]');
    if (!heading) {
      return;
    }
    heading.focus({ preventScroll: true });
    if (this._compact) {
      heading.scrollIntoView({ block: "start" });
    }
  }

  // "Use the whole screen" from a card's form: the card stays selected at
  // its new place, so Wider works straight away.
  _wholeScreenFor(source) {
    const before = this._draft;
    const next = useWholeScreen(before, this._view);
    this._selected = followItem(before, next, source);
    this._screenFor = this._selected ? sourceKey(this._selected) : null;
    if (this._commit(next)) {
      this._focus("wider") || this._els.side?.querySelector(".side-title")?.focus();
    }
  }

  _itemKeys(event, source, where) {
    if (this._readOnly) {
      return;
    }
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      this._removeItem(source);
    } else if (event.shiftKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
      event.preventDefault();
      this._move(source, event.key === "ArrowLeft" ? -1 : 1, where);
    }
  }

  _undo() {
    if (!this._history || !canUndo(this._history) || this._readOnly) {
      return;
    }
    const before = this._draft;
    this._history = historyUndo(this._history);
    this._followSelection(before);
    this._draftChanged();
  }

  _redo() {
    if (!this._history || !canRedo(this._history) || this._readOnly) {
      return;
    }
    const before = this._draft;
    this._history = historyRedo(this._history);
    this._followSelection(before);
    this._draftChanged();
  }

  // Undo, redo and versions from somewhere else replace the whole draft. The
  // side panel keeps the card it showed, wherever that card now is, or lets
  // go when it is gone, so Wider or Remove never act on a card the person
  // did not pick.
  _followSelection(before) {
    if (!this._selected) {
      return;
    }
    const next = followItem(before, this._draft, this._selected);
    if (!sameSource(next, this._selected)) {
      this._selected = next;
      // The card may now be drawn on another screen of the page.
      this._screenFor = next ? sourceKey(next) : null;
    }
  }

  _removeItem(source) {
    const card = getCard(this._draft, source);
    if (!card) {
      return;
    }
    const heading = source[2] === null || card.type === "heading";
    const index = this._rows.findIndex((row) => sameSource(row.source, source));
    const row = this._rows[index];
    // A card the tablet cannot show controlled devices that are now on no
    // card; the toast names them and offers a TAB-1 card for them.
    const entities = row && row.kind !== "tab" && row.kind !== "heading" ? row.entities : [];
    const devices = entities.length ? { entities: [...entities], name: deviceText(this._hass, entities) } : null;
    this._selected = null;
    if (!this._commit(removeItem(this._draft, source))) {
      return;
    }
    // Undo puts the card back where it was, so its row has this key again.
    const restore = `row:${sourceKey(source)}`;
    if (devices) {
      this._showToast(t("toast.card_removed_for", { device: devices.name }), { undo: true, devices, restore });
      // The next step is in the toast, which stays while it has focus.
      if (this._focusIn(this._els.toasts, "toast-replace")) {
        return;
      }
    } else {
      this._showToast(t(heading ? "toast.heading_removed" : "toast.card_removed"), { undo: true, restore });
    }
    // The pressed control went with its card. Focus goes on in the card
    // list: to the card that took its place, or to Add card.
    const rows = [...(this._els.list?.querySelectorAll('[data-test="list-row"]') || [])];
    const next = rows[index];
    if (next) {
      next.focus();
    } else {
      this._els.addCard?.focus();
    }
  }

  _focusIn(region, test) {
    const target = region?.querySelector(`[data-test="${test}"]`);
    target?.focus({ preventScroll: true });
    return Boolean(target) && this.shadowRoot.activeElement === target;
  }

  _move(source, delta, where) {
    if (!canMove(this._draft, source, delta)) {
      return;
    }
    const result = moveItem(this._draft, source, delta);
    const key = sourceKey(result.source);
    this._selected = result.source;
    // The canvas is redrawn when the new preview arrives, so focus for a
    // canvas item waits for that; the list and the form are redrawn now.
    this._pendingFocus = where === "hit" ? `hit:${key}` : null;
    this._commit(result.config);
    if (where === "row") {
      this._focus(`row:${key}`);
    } else if (where === "form") {
      const same = delta < 0 ? "move-earlier" : "move-later";
      const other = delta < 0 ? "move-later" : "move-earlier";
      if (!this._focus(same) && !this._focus(other)) {
        this._els.side?.querySelector(".side-title")?.focus();
      }
    }
    this._showToast(t(delta < 0 ? "toast.moved_earlier" : "toast.moved_later"));
  }

  // Moves a card to another page, or to a new one, and follows it there:
  // that page is shown with the card selected, and one Undo brings it back.
  _moveToPage(source, target) {
    const titles = pageList(this._draft).map((page) => page.title);
    const title = nextDashboardTitle(titles, t("page.new_name"));
    const result = moveCardToPage(this._draft, source, target, title);
    if (!result.source) {
      return;
    }
    const key = sourceKey(result.source);
    this._view = result.view;
    this._screen = 0;
    this._selected = result.source;
    this._screenFor = key;
    if (!this._commit(result.config)) {
      return;
    }
    const name = pageList(this._draft)[result.view]?.title || "";
    this._showToast(t("toast.moved_to_page", { page: name }));
    if (this._compact) {
      this._els.side?.querySelector(".side-title")?.focus({ preventScroll: true });
      this._revealOnPreview = true;
      this._revealSelection();
    } else {
      this._pendingFocus = `hit:${key}`;
    }
  }

  _addPage() {
    const titles = pageList(this._draft).map((page) => page.title);
    const result = addPage(this._draft, nextDashboardTitle(titles, t("page.new_name")));
    this._view = result.view;
    this._screen = 0;
    this._selected = null;
    this._commit(result.config);
    const input = this._els.side?.querySelector('[data-test="page-name"]');
    if (input) {
      input.focus();
      input.select();
    }
  }

  async _removePage(vi, confirmFirst) {
    const views = this._draft?.views || [];
    if (views.length <= 1) {
      return;
    }
    const count = cardCount(views[vi]);
    if (confirmFirst && count > 0) {
      const run = this._run;
      const draft = this._draft;
      const name = pageList(draft)[vi]?.title || "";
      const accepted = await openConfirm({
        title: t("page.delete_title", { name }),
        text: t("page.delete_text", { count }),
        okLabel: t("page.delete_ok"),
        cancelLabel: t("confirm.cancel"),
        danger: true,
      });
      // The answer is about the page that was asked about; if the dashboard
      // changed meanwhile, page vi may be a different page.
      if (!accepted || run !== this._run || this._draft !== draft) {
        return;
      }
    }
    const result = removePage(this._draft, vi);
    this._view = result.view;
    this._screen = 0;
    this._selected = null;
    if (this._commit(result.config)) {
      this._showToast(t("toast.page_removed"), { undo: true });
      // The pressed button went with its page. Focus goes to the tab of the
      // page now shown, never to the same button of the next page, where a
      // second Enter would remove that page too.
      this._focus(`tab:${this._view}`);
    }
  }

  // devices ({entities, name}): the picker starts with the cards for them
  // (see openCardPicker).
  async _openPicker(opener, devices = null) {
    if (this._picking || this._readOnly) {
      return;
    }
    // A picker closed by leaving the editor answers late; by then another
    // picker may be open, which that late answer must not unlock.
    const token = {};
    this._picking = token;
    const vi = this._view;
    const run = this._run;
    let result = null;
    try {
      result = await openCardPicker({
        root: this.shadowRoot,
        hass: this._hass,
        library: this._library,
        config: this._draft,
        themeId: this._themeId(),
        compact: this._compact,
        devices,
      });
    } finally {
      if (this._picking === token) {
        this._picking = null;
      }
    }
    if (!result || this._status !== "ready" || run !== this._run) {
      opener?.isConnected && opener.focus();
      return;
    }
    const added = addCard(this._draft, vi, result.component, result.params);
    if (!added.source) {
      return;
    }
    const key = sourceKey(added.source);
    this._view = vi;
    this._selected = added.source;
    this._screenFor = key;
    this._commit(added.config);
    // A card picked for a removed card's devices may take only some of them;
    // the toast offers a card for the rest.
    const left = devices ? devicesLeft(devices.entities, result.params) : [];
    if (left.length) {
      const rest = { entities: left, name: deviceText(this._hass, left) };
      this._showToast(t("toast.card_added_for", { device: rest.name }), { devices: rest });
    } else {
      this._showToast(t("toast.card_added"));
    }
    if (this._compact) {
      // The new card is drawn when its preview arrives; the picture is
      // brought into view now and again then.
      this._els.side?.querySelector(".side-title")?.focus({ preventScroll: true });
      this._revealOnPreview = true;
      this._revealSelection();
    } else {
      this._pendingFocus = `hit:${key}`;
    }
  }

  _openAdvanced() {
    if (this.onAdvanced) {
      this.onAdvanced();
      return;
    }
    history.pushState(null, "", "/apollo-tab/advanced");
    window.dispatchEvent(new CustomEvent("location-changed"));
  }

  async _updateDashboard(changes) {
    const dashboard = this._dashboard;
    if (!dashboard?.id) {
      throw Object.assign(new Error("Unknown dashboard"), { code: "not_found" });
    }
    await this._hass.callWS({
      type: "lovelace/dashboards/update",
      dashboard_id: dashboard.id,
      ...changes,
    });
    if (typeof changes.title === "string") {
      dashboard.title = changes.title;
    }
    if (typeof changes.show_in_sidebar === "boolean") {
      dashboard.show_in_sidebar = changes.show_in_sidebar;
    }
    if (dashboard !== this._dashboard) {
      return;
    }
    if (typeof changes.title === "string" && this._els.title) {
      this._els.title.textContent = changes.title;
    }
    if (typeof changes.show_in_sidebar === "boolean") {
      this._renderBanners();
    }
  }

  async _hideFromSidebar() {
    try {
      await this._updateDashboard({ show_in_sidebar: false });
      this._sidebarError = "";
      this._renderBanners();
      if (!this._selected) {
        this._renderSide();
      }
    } catch (error) {
      this._sidebarError = t("settings.failed", { message: errorMessage(error) });
      this._renderBanners();
    }
  }

  // ---- tablets ---------------------------------------------------------

  _tabletsChanged(tablets) {
    this._tablets = tablets;
    this._tabletsError = null;
    this._fillTabletLines();
    this._fillShownOn();
  }

  // Reads the TAB-1 dashboards with their titles, in the one order, for the
  // "Shown on" block and the delete question. The block is kept as it was
  // when Home Assistant cannot be reached. Resolves to the rows this call
  // read, or to null when it read none.
  async _loadTabRows() {
    if (!this._hass || this._status !== "ready") {
      return null;
    }
    const seq = ++this._tabRowsSeq;
    let rows;
    try {
      const [tab, list] = await Promise.all([
        this._hass.callWS({ type: "apollo_tab/dashboards" }),
        this._hass.callWS({ type: "lovelace/dashboards/list" }),
      ]);
      rows = mergeDashboards(Array.isArray(tab?.dashboards) ? tab.dashboards : [], Array.isArray(list) ? list : []);
    } catch {
      return null;
    }
    if (seq !== this._tabRowsSeq) {
      // A newer read fills the block.
      return rows;
    }
    this._tabRows = rows;
    this._fillShownOn();
    return rows;
  }

  // Several saves in a row are read once, after the last.
  _scheduleTabRows() {
    clearTimeout(this._tabRowsTimer);
    this._tabRowsTimer = setTimeout(() => {
      this._tabRowsTimer = null;
      this._loadTabRows();
    }, 300);
  }

  // The lines under "What the tablet will show": a line per tablet that
  // shows this dashboard, or "Not shown on a tablet yet". Nothing while the
  // tablets are not known.
  _fillTabletLines() {
    const box = this._els.tabletLines;
    if (!box) {
      return;
    }
    if (!Array.isArray(this._tablets) || this._tabletsError) {
      box.replaceChildren();
      return;
    }
    const lines = captionLines(this._tablets, this._urlPath, t);
    box.replaceChildren(
      ...lines.map((line) => {
        const node = el("p", "small tablet-line", line.text);
        node.dataset.test = "tablet-line";
        node.dataset.kind = line.kind;
        if (line.mac) {
          node.dataset.mac = line.mac;
        }
        if (line.tone) {
          node.dataset.tone = line.tone;
        }
        return node;
      }),
    );
  }

  // The "Shown on" block under the dashboard's theme. It is made with the
  // side panel and filled again when the tablets change.
  _shownOnBlock() {
    const block = el("div", "shown-on");
    block.dataset.test = "shown-on";
    this._els.shownOn = block;
    this._shownOnKey = null;
    this._fillShownOn();
    return block;
  }

  _fillShownOn() {
    const block = this._els.shownOn;
    if (!block) {
      return;
    }
    const rows = Array.isArray(this._tablets)
      ? shownOnRows(this._tablets, this._urlPath, this._tabRows || [], t)
      : null;
    // New tablets are not listed: an admin turns one on from Home.
    const waiting = Array.isArray(this._tablets) ? newTabletCount(this._tablets) > 0 : false;
    const failure = this._tabletsError ? errorMessage(this._tabletsError) : null;
    // Drawn again only when something it says changed, so a status change
    // on a tablet does not take focus from its button.
    const key = JSON.stringify([rows, waiting, failure, this._shownOnError, [...this._assigning], this._urlPath]);
    if (key === this._shownOnKey) {
      return;
    }
    this._shownOnKey = key;
    const active = this.shadowRoot.activeElement;
    const focusKey = active && block.contains(active) ? active.dataset.focus || "shown-on-heading" : null;

    const heading = el("h4", "shown-on-heading", t("editor.on_tablet_heading"));
    heading.tabIndex = -1;
    heading.dataset.focus = "shown-on-heading";
    const children = [heading];
    if (failure !== null) {
      children.push(alertLine(t("tablets.load_failed", { message: failure })));
    } else if (rows === null) {
      children.push(el("p", "small", t("tablets.loading")));
    } else if (!rows.length) {
      if (!waiting) {
        const none = el("p", "small", t("editor.on_tablet_none"));
        none.dataset.test = "shown-on-none";
        children.push(none);
      }
    } else {
      const list = el("ul", "shown-on-list");
      for (const row of rows) {
        const item = el("li", "shown-on-row");
        item.dataset.test = "shown-on-row";
        item.dataset.mac = row.mac;
        item.dataset.here = String(row.here);
        const words = el("div", "shown-on-text");
        words.append(el("span", "shown-on-name", row.name), el("span", "small", row.text));
        item.append(words);
        // A tablet always shows one dashboard, so there is nothing to untick
        // here; another tablet can be moved to this one.
        if (!row.here) {
          const button = makeButton(t("editor.on_tablet_show"), {
            test: "show-here",
            focus: `show-here:${row.mac}`,
            disabled: this._assigning.has(row.mac),
            onClick: () => this._showHere(row.mac),
          });
          button.dataset.mac = row.mac;
          item.append(button);
        }
        list.append(item);
      }
      children.push(list, el("p", "helper", t("editor.on_tablet_helper")));
    }
    if (failure === null && waiting) {
      const note = el("p", "small", t("editor.on_tablet_new"));
      note.dataset.test = "shown-on-new";
      children.push(note);
    }
    if (this._shownOnError) {
      const alert = alertLine(this._shownOnError);
      alert.dataset.test = "shown-on-error";
      children.push(alert);
    }
    // The address, for the show_dashboard action in automations.
    const name = el("p", "automation-name");
    name.dataset.test = "automation-name";
    name.append(el("span", "field-label", t("editor.on_tablet_name")), el("code", null, this._urlPath || ""));
    children.push(name);
    block.replaceChildren(...children);

    if (focusKey) {
      const target = [...block.querySelectorAll("[data-focus]")].find((node) => node.dataset.focus === focusKey);
      // The button is gone once its tablet shows this dashboard.
      (target && !target.disabled ? target : heading).focus({ preventScroll: true });
    }
  }

  async _showHere(mac) {
    if (this._assigning.has(mac) || !this._conn) {
      return;
    }
    const run = this._run;
    const urlPath = this._urlPath;
    this._assigning.add(mac);
    this._shownOnError = "";
    this._fillShownOn();
    try {
      // The answer reaches every listener of the tablet list, this one too.
      await assignTablet(this._conn, mac, urlPath);
    } catch (error) {
      if (run === this._run) {
        this._shownOnError = t("tablets.failed", { message: errorMessage(error) });
      }
    } finally {
      if (run === this._run) {
        this._assigning.delete(mac);
        this._fillShownOn();
      }
    }
  }

  // The second paragraph of the delete question: which tablets show this
  // dashboard and which one they will show instead. The dashboards are
  // read again first, so it names the right one.
  async _deleteNote() {
    if (!Array.isArray(this._tablets) || !tabletsShowing(this._tablets, this._urlPath).length) {
      return "";
    }
    const rows = await this._loadTabRows();
    // Without the dashboards as they are now it cannot tell where the
    // tablets go, and it does not guess from an older list.
    if (!rows || !Array.isArray(this._tablets)) {
      return "";
    }
    return deleteNote(this._tablets, this._urlPath, rows, t);
  }

  async _deleteDashboard() {
    const run = this._run;
    const dashboard = this._dashboard;
    const more = await this._deleteNote();
    if (run !== this._run) {
      return;
    }
    const accepted = await openConfirm({
      title: t("settings.delete_title", { name: dashboard?.title || "" }),
      text: t("settings.delete_text"),
      more,
      okLabel: t("settings.delete_ok"),
      cancelLabel: t("confirm.cancel"),
      danger: true,
    });
    // Never delete a dashboard other than the one the question named.
    if (!accepted || run !== this._run || !dashboard?.id) {
      return;
    }
    this._deleting = true;
    this._queue?.pause();
    try {
      await this._hass.callWS({ type: "lovelace/dashboards/delete", dashboard_id: dashboard.id });
    } catch (error) {
      if (run === this._run) {
        this._deleting = false;
        this._queue?.resume();
      }
      throw error;
    }
    if (run !== this._run) {
      return;
    }
    this._queue = null;
    this._queueUrl = null;
    this.onExit?.();
  }

  // Waits for the last change to be saved, then goes back to the list. A
  // change that could not be saved, or waits for a choice, is not left
  // silently: a question says so, with Stay first. Leaving keeps the change
  // (see _releaseQueue).
  async _back() {
    const queue = this._queue;
    if (queue && this._status === "ready") {
      await queue.flush();
      // Left some other way while waiting (the browser's Back button, the
      // sidebar): that move already happened.
      if (queue !== this._queue) {
        return;
      }
      if (queue.state === "error" || queue.state === "paused") {
        const run = this._run;
        const leave = await openConfirm({
          title: t("leave.title"),
          text: t(queue.state === "paused" ? "leave.text_choice" : "leave.text_error"),
          okLabel: t("leave.ok"),
          cancelLabel: t("leave.stay"),
        });
        if (!leave || run !== this._run || queue !== this._queue) {
          if (run === this._run && focusLost()) {
            this._focus("back");
          }
          return;
        }
      }
    }
    this.onExit?.();
  }

  // ---- changes made somewhere else -------------------------------------

  _layoutEvent(event) {
    // Another dashboard that came, changed or went may change the titles
    // the "Shown on" block names and the one a deleted dashboard's tablets
    // move to. This one's own saves change neither.
    if (["converted", "removed", "renamed"].includes(event?.type) && event.url_path !== this._urlPath) {
      this._scheduleTabRows();
    }
    if (event?.url_path !== this._urlPath) {
      return;
    }
    if (event.type === "removed") {
      if (!this._deleting) {
        this._gone();
      }
    } else if (event.type === "converted") {
      this._checkRemote();
    }
  }

  async _checkRemote() {
    if (this._status !== "ready" || this._deleting) {
      return;
    }
    // The answer belongs to this dashboard only; by the time it arrives the
    // editor may show another one.
    const run = this._run;
    let remote;
    try {
      remote = await this._hass.callWS({ type: "lovelace/config", url_path: this._urlPath, force: false });
    } catch (error) {
      if (error?.code === "config_not_found" && run === this._run) {
        this._gone();
      }
      return;
    }
    if (run !== this._run || this._status !== "ready" || this._deleting || !isObject(remote)) {
      return;
    }

    if (this._readOnly) {
      if (!sameConfig(remote, this._draft)) {
        const before = this._draft;
        this._history = createHistory(remote);
        this._followSelection(before);
        this._draftChanged();
      }
      return;
    }

    // Home Assistant holds exactly what is shown: the change is saved, even
    // when the answer to its save was lost with the connection, so a failed
    // save no longer asks to be tried again. While the person is asked
    // which version to keep this proves nothing: one of the editor's own
    // saves may have landed over the other version, which is then lost
    // unless they choose it.
    if (sameConfig(remote, this._draft) && !this._conflict) {
      if (this._queue.inflight === null) {
        this._queue.reset(remote);
      }
      this._updateHeader();
      this._requestPreview();
      return;
    }
    const kind = classifyRemote(remote, this._queue);
    if (kind === "ours" || (kind === "unsure" && this._queue.state === "saved")) {
      // With nothing left to save, the version shown is what Home Assistant
      // holds, whichever dashboard that is.
      if (kind === "unsure") {
        this._queue.reset(remote);
      }
      this._requestPreview();
      return;
    }
    if (this._queue.state === "saved") {
      const before = this._draft;
      this._history = historyPush(this._history, remote);
      this._queue.reset(remote);
      this._followSelection(before);
      this._draftChanged();
      this._showToast(t("toast.remote"), { tied: true });
      return;
    }
    this._askWhichVersion(remote, kind === "unsure");
  }

  // Stops saving and asks the person which version to keep: their own, with
  // the change not saved yet, or `remote`, saved somewhere else. unsure:
  // `remote` is the version the change started from, but the connection was
  // lost meanwhile, so it may belong to a dashboard made again in its place.
  _askWhichVersion(remote, unsure = false) {
    this._queue.pause();
    // Already asked about this very version: nothing to tell again.
    if (this._conflict && sameConfig(this._conflict, remote)) {
      return;
    }
    this._conflict = remote;
    this._conflictStored = null;
    this._conflictUnsure = unsure;
    // An older message, such as "changed somewhere else ... you are now
    // looking at the newest version", would contradict the banner.
    clearTimeout(this._toastTimer);
    this._toast = null;
    this._renderToast();
    this._renderBanners();
    this._revealBanners();
  }

  // Saves the editor's draft over the version that arrived. The other
  // version goes into the history just behind the draft, so one Undo brings
  // it back. The queue is told what the server holds (the other version,
  // or one of an earlier editor's saves that landed after it), so the
  // draft is saved over it, after any save still on its way.
  _keepMine() {
    const remote = this._conflict;
    const stored = this._conflictStored;
    const draft = this._draft;
    this._conflict = null;
    this._conflictStored = null;
    this._conflictUnsure = false;
    this._history = historyPush({ ...this._history, present: remote, key: null }, draft);
    this._queue.reset(stored || remote);
    this._queue.push(draft);
    this._queue.flush();
    this._updateHeader();
    this._renderBanners();
  }

  // Takes the version that arrived. If one of the editor's own saves was
  // under way when it arrived, or landed before the dashboard was opened
  // again, the queue saves the other version again so Home Assistant ends
  // with what is shown here.
  _useTheirs() {
    const remote = this._conflict;
    const before = this._draft;
    const stored = this._conflictStored;
    this._conflict = null;
    this._conflictStored = null;
    this._conflictUnsure = false;
    this._history = historyPush(this._history, remote);
    if (stored) {
      this._queue.reset(stored);
      this._queue.push(remote);
    } else {
      this._queue.reset(remote);
    }
    this._followSelection(before);
    this._draftChanged();
  }

  // ---- keyboard --------------------------------------------------------

  _dialogOpen() {
    return Boolean(
      this.shadowRoot.querySelector("dialog[open]") || document.querySelector("dialog[open]") || confirmOpen(),
    );
  }

  _handleShortcut(event) {
    if (this._status !== "ready" || this._readOnly || !(event.ctrlKey || event.metaKey)) {
      return;
    }
    if (!this.getClientRects().length || this._dialogOpen()) {
      return;
    }
    // Where text is typed, the browser's own undo applies. A select, tick
    // box, slider or colour keeps focus after it is used, and there the
    // shortcut undoes that change.
    const target = event.composedPath()[0];
    const typing =
      target?.tagName === "TEXTAREA" ||
      target?.isContentEditable ||
      (target?.tagName === "INPUT" && !["checkbox", "radio", "range", "color", "button"].includes(target.type));
    if (typing) {
      return;
    }
    const key = event.key.toLowerCase();
    if (key === "z" && !event.shiftKey) {
      event.preventDefault();
      this._undo();
    } else if ((key === "z" && event.shiftKey) || (key === "y" && event.ctrlKey)) {
      event.preventDefault();
      this._redo();
    }
  }

  _handleEscape(event) {
    if (event.key !== "Escape" || this._dialogOpen() || !this._selected) {
      return;
    }
    event.preventDefault();
    const key = this._selectedKey();
    const active = this.shadowRoot.activeElement;
    const fromSide = active && this._els.side?.contains(active);
    this._select(null);
    if (fromSide || !this.shadowRoot.activeElement) {
      this._focus(`hit:${key}`) || this._focus(`row:${key}`);
    }
  }
}
