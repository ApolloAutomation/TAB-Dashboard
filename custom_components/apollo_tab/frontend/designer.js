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
  buildThemeGallery,
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
import { drawerShift, fitStage, layoutBand, shellHeight, warningBoxKind } from "./logic.js";
import {
  DEFAULT_THEME,
  PREVIEW_THEMES,
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
  historyCloseGroup,
  historyPush,
  historyRedo,
  historyUndo,
  maxUnitsWide,
  mergeDashboards,
  moveCardToPage,
  moveItem,
  movePage,
  nextDashboardTitle,
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
import { openPopover } from "./popover.js";
import { renderPage } from "./render.js";
import { canvasStyles, designerStyles, formStyles, pickerStyles, rendererStyles } from "./styles.js";
import {
  approvedTablets,
  captionLines,
  chipTone,
  chipWords,
  deleteNote,
  newTablets,
  shownOnRows,
  tabletName,
  tabletsShowing,
} from "./tablets.js";

const KEEP_IN_SIDEBAR_KEY = "apollo_tab.sidebar_keep";
// Under this height of the editor the first-card notice takes a row over
// the picture instead of floating over the stage's top padding.
const FIRST_CARD_FLOAT_HEIGHT = 700;

// The dashboards whose first-card notice was shown in this browser.
const FIRST_CARD_KEY = "apollo_tab.first_card";
// Under this width of the editor a phone's top bar keeps Redo in the menu.
const TIGHT_BAR = 400;
// How long a failed rename says so under the name.
const RENAME_ERROR_MS = 8000;
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

function firstCardSeen() {
  try {
    const list = JSON.parse(localStorage.getItem(FIRST_CARD_KEY) || "[]");
    return Array.isArray(list) ? list.filter((entry) => typeof entry === "string") : [];
  } catch {
    return [];
  }
}

function markFirstCardSeen(urlPath) {
  try {
    const list = firstCardSeen();
    if (!list.includes(urlPath)) {
      localStorage.setItem(FIRST_CARD_KEY, JSON.stringify([...list, urlPath]));
    }
  } catch {
    // Without storage the notice may show once more on another visit.
  }
}

// The cards on every page of a dashboard.
function dashboardCards(config) {
  return (Array.isArray(config?.views) ? config.views : []).reduce((total, view) => total + cardCount(view), 0);
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
    // Where to open the next dashboard that loads, set by the start screen:
    // { urlPath, view, source } or null (see the load).
    this.openAt = null;
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
    this._tight = false;
    // Compact: what opened the edit mode ("hit", "row" or null), the page
    // column's scroll then, and the page. Leaving it puts the person back
    // there. _opener hands the first two over from _select.
    this._editFrom = null;
    this._opener = null;
    // The layout: "wide", "medium", "compact" or "short" (layoutBand).
    this._band = "wide";
    // The band is not changed while a text field has focus; true while a
    // change waits for the field to lose it.
    this._bandHeld = false;
    // "fit" or "100": the picture fitted to its space, or at its real size.
    this._zoom = "fit";
    // Medium layout: the drawer shows the card list after "Cards".
    this._drawerOpen = false;
    // How far the picture is moved left to clear the drawer, in px.
    this._shift = 0;
    // The page notices: all of them shown ("+2 more" pressed), and the ones
    // whose long text is open.
    this._noticesOpen = false;
    this._whyOpen = new Set();
    this._els = {};
    this._areaKey = null;
    this._sideKey = null;
    this._pendingFocus = null;
    this._screenFor = null;
    // A token for the open card picker, or null.
    this._picking = null;
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
    // The open pop-up ({ update, close, dialog }) and which one it is
    // ("tablets", "theme", "menu" or "page"); the history group of the open
    // theme gallery.
    this._popover = null;
    this._popKind = null;
    this._themeGroup = null;
    // The dashboard's name is a field while it is renamed; a failed rename
    // says so under it for a while.
    this._renaming = false;
    this._renameError = "";
    this._renameTimer = null;
    // The first card of a dashboard no tablet shows raises a notice once
    // it is saved: due until then, then what it says.
    this._firstCardDue = false;
    this._firstCard = null;

    // Work left behind by a closed editor has its own guard (see leftBehind).
    this._onBeforeUnload = (event) => {
      if (this._queue?.dirty) {
        event.preventDefault();
      }
    };
    this._onWindowKey = (event) => this._handleShortcut(event);
    this.addEventListener("keydown", (event) => this._handleEscape(event));
    this._toastFrame = 0;
    // The window's size decides the shell's height and the layout.
    this._onViewport = () => this._checkLayout();
    // A layout change held while a text field had focus happens once it
    // has lost it.
    this.shadowRoot.addEventListener("focusout", () => {
      if (this._bandHeld) {
        requestAnimationFrame(() => this._checkLayout());
      }
    });
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
    window.addEventListener("resize", this._onViewport, { passive: true });
    window.visualViewport?.addEventListener("resize", this._onViewport, { passive: true });
    window.visualViewport?.addEventListener("scroll", this._onViewport, { passive: true });
    this._hostObserver = new ResizeObserver(() => this._checkLayout());
    this._hostObserver.observe(this);
    this._setBand(this._measureBand());
    this._start();
  }

  disconnectedCallback() {
    // Unsaved work moves to leftBehind, which keeps asking "leave this
    // page?" until it is saved.
    this._stop();
    window.removeEventListener("beforeunload", this._onBeforeUnload);
    window.removeEventListener("keydown", this._onWindowKey);
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
    this._renaming = false;
    this._renameError = "";
    clearTimeout(this._renameTimer);
    this._firstCardDue = false;
    this._firstCard = null;
    // A message about this dashboard is not shown for the next one.
    this._toast = null;
    clearInterval(this._refreshTimer);
    cancelAnimationFrame(this._frame);
    cancelAnimationFrame(this._toastFrame);
    this._toastFrame = 0;
    this._stageObserver?.disconnect();
    this._stageObserver = null;
    this._els.pageHost?.__atCleanup?.();
    this._els.previewHost?.__atCleanup?.();
    this._popover?.close({ refocus: false });
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
    // Every opening starts with the picture fitted and the drawer closed.
    this._zoom = "fit";
    this._drawerOpen = false;
    this._shift = 0;
    this._noticesOpen = false;
    this._whyOpen.clear();
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
          this._tabletsShown();
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
    // The start screen's "left out" link: this page, with that card
    // selected, so the card's panel says why the tablet leaves it out.
    const at = this.openAt;
    this.openAt = null;
    if (isObject(at) && at.urlPath === urlPath && Number.isInteger(at.view)) {
      const views = Array.isArray(config.views) ? config.views : [];
      if (at.view >= 0 && at.view < views.length) {
        this._view = at.view;
        const source = Array.isArray(at.source) ? at.source : null;
        const card = source ? views[source[0]]?.sections?.[source[1]]?.cards?.[source[2]] : null;
        if (source && source[0] === at.view && isObject(card)) {
          this._selected = [...source];
        }
      }
    }
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

  // The band for the editor's own width (Home Assistant's docked sidebar
  // counts) and the window's height below the editor's top. Neither the
  // on-screen keyboard nor pinch zoom changes that height.
  _measureBand() {
    const box = (this._els.root || this).getBoundingClientRect();
    return layoutBand(this.getBoundingClientRect().width, window.innerHeight - box.top);
  }

  _setBand(band) {
    this._band = band;
    this._compact = band === "compact";
    this._bandWidth = this.getBoundingClientRect().width;
    this._tight = this._isTight(this._bandWidth);
  }

  // A phone's bar under 400 px has no room for Redo beside the dashboard's
  // name: Redo is in the menu there, and Undo stays in the bar.
  _isTight(width) {
    return this._compact && width > 0 && width < TIGHT_BAR;
  }

  // Whether a text field of the editor or of one of its dialogs has focus.
  _typing() {
    const active = this.shadowRoot.activeElement;
    if (!active) {
      return false;
    }
    // A switch, a choice or a slider brings up no keyboard. A list to choose
    // from opens its own picker on a phone, so it holds the band too.
    if (active.tagName === "INPUT") {
      return !["checkbox", "radio", "range", "color", "button", "submit"].includes(active.type);
    }
    return active.tagName === "TEXTAREA" || active.tagName === "SELECT" || active.isContentEditable;
  }

  // Fits the shell to the window, and changes the layout when the band
  // changed. While a text field has focus the band is kept, so a web view
  // that shrinks the window for the keyboard does not move the field away.
  // The keyboard only changes the height: when the width changes too (a
  // window snapped to half the screen, a phone turned) the band follows.
  _checkLayout() {
    this._fitShell();
    // Not laid out (taken out of the page, or hidden): nothing to measure.
    const width = this.isConnected ? this.getBoundingClientRect().width : 0;
    if (!width) {
      return;
    }
    const band = this._measureBand();
    if (this._typing() && Math.abs(width - (this._bandWidth ?? width)) <= 4) {
      this._bandHeld = band !== this._band;
      return;
    }
    this._bandHeld = false;
    this._bandWidth = width;
    if (band === this._band) {
      // The bar got too narrow for Redo, or wide enough again. The menu is
      // drawn for one or the other, so an open one closes.
      if (this._isTight(width) !== this._tight) {
        this._tight = !this._tight;
        if (this._popKind === "menu") {
          this._popover?.close();
        }
        this._renderHeader();
      }
      // The tab list may have got narrower.
      this._showTab();
      // The window got low or high enough for the notice to change place.
      if (this._firstCard && this._firstCardRow() !== this._firstCardIsRow) {
        this._placeFirstCard();
      }
      return;
    }
    const active = this.shadowRoot.activeElement;
    // Focus in an open pop-up goes back to the control that opened it.
    const inPop = Boolean(active && this._popover?.dialog?.contains(active));
    const focusKey = (inPop ? this._popAnchor : active?.dataset?.focus) || null;
    const wasEdit = this._els.side?.dataset.mode === "edit";
    // A pop-up is a sheet in one layout and not in another: it closes.
    this._popover?.close({ refocus: false });
    this._setBand(band);
    this._drawerOpen = false;
    this._shift = 0;
    if (!this._hasStatusStrip()) {
      this._zoom = "fit";
    }
    this._render();
    // Focus that was in the editor stays in it: on the same control when
    // the new layout has it in reach, else on the selected card's form,
    // else on the tab of the page shown. A change that opens the edit mode
    // gives focus to it, as choosing a card does.
    const opened = this._els.side?.dataset.mode === "edit" && !wasEdit;
    if ((active || opened) && !this.shadowRoot.activeElement) {
      (focusKey && this._focus(focusKey)) || this._focusForm() || this._focus(`tab:${this._view}`) || this._focus("back");
    }
  }

  // The bands with a status strip under the picture, and with zoom.
  _hasStatusStrip() {
    return this._band === "wide" || this._band === "medium";
  }

  // The shell is exactly as tall as the space below its top: above a phone's
  // keyboard, and not smaller while the page is pinch-zoomed.
  _fitShell() {
    const root = this._els.root;
    if (!root?.isConnected) {
      return;
    }
    const view = window.visualViewport;
    const height = shellHeight({
      innerHeight: window.innerHeight,
      visual: view ? { height: view.height, offsetTop: view.offsetTop, scale: view.scale } : null,
      top: root.getBoundingClientRect().top,
    });
    root.style.height = `${height}px`;
    this._queuePlaceToast();
  }

  // ---- drawing ---------------------------------------------------------

  // The editor is a grid as tall as the window (see _fitShell): the top bar,
  // the notices that block, the page strip, the stage column and the
  // inspector, each placed by the name of its row.
  _render() {
    this._stageObserver?.disconnect();
    this._stageObserver = null;
    this._els.pageHost?.__atCleanup?.();
    this._els.previewHost?.__atCleanup?.();
    const root = el("div", `root ${this._band}`);
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
    this._fitShell();

    const header = el("header", "ed-header");
    this._els.header = header;
    root.append(header);
    this._renderHeader();

    if (this._status === "loading" || this._status === "idle") {
      this._renderOpening(root);
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
    // The page notices: one line each, above the picture (see _renderAdvice;
    // _placeAdvice puts the row in its place).
    const advice = el("div", "banners advice-banners");
    const tabs = el("div", "tab-strip");
    const tabList = el("div", "strip-tabs");
    const stripEnd = el("div", "strip-end");
    tabs.append(tabList, stripEnd);
    const page = el("div", "main");
    const side = el("aside", "side");
    side.dataset.test = "side";
    // What the inspector shows while no card is selected (in the compact
    // layout it is the end of the page column): the cards on this page and
    // the notes about the picture.
    const idle = el("div", "idle");
    idle.dataset.test = "idle";
    const idleIntro = el("div", "idle-intro");
    const idlePage = el("div", "idle-page");
    idle.append(idleIntro, idlePage);
    const toasts = el("div", "toast-region");
    toasts.setAttribute("aria-live", "polite");
    root.append(banners, tabs, page, side, toasts);
    Object.assign(this._els, {
      banners,
      advice,
      tabs,
      tabList,
      stripEnd,
      page,
      side,
      idle,
      idleIntro,
      idlePage,
      toasts,
    });

    this._renderBanners();
    this._renderTabs();
    this._renderPageArea();
    this._renderSide();
    this._renderToast();
  }

  // While the dashboard opens: the frame with "Opening your dashboard…" in
  // it, and grey rows where the inspector's list will be.
  // The frame has the size the picture will have, with the status strip's
  // place kept free, so it does not jump when the dashboard is in.
  _renderOpening(root) {
    const page = el("div", "main");
    const area = el("div", "stage-area");
    const device = el("div", "device");
    const frame = el("div", "stage opening");
    frame.append(el("p", "stage-message", t("editor.loading")));
    device.append(frame);
    area.append(device);
    page.append(area);
    if (this._hasStatusStrip()) {
      page.append(el("div", "status-strip"));
    }
    // In the compact layout the list is under the picture, in the page
    // column, so its grey rows are there too.
    const side = el("aside", "side opening");
    const rows = this._compact ? el("div", "placeholder-rows") : side;
    for (let row = 0; row < 3; row += 1) {
      rows.append(el("div", "placeholder-row"));
    }
    if (this._compact) {
      page.append(rows);
    }
    root.append(el("div", "tab-strip"), page, side);
    this._stageObserver = new ResizeObserver(() => {
      const width = this._stageWidth(area, device);
      if (width) {
        frame.style.width = `${width}px`;
        frame.style.height = `${width / 1.6}px`;
      }
    });
    this._stageObserver.observe(area);
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

  // The page notices are the first row of the stage column, above the
  // picture. In the compact layout they come after the picture and the
  // tablet lines, before the card list, every one shown.
  _placeAdvice(focusKey = this._focusKeyIn(this._els.advice)) {
    const { advice, page, stageArea, pageBox, under, chipRow, idle } = this._els;
    if (!advice || !page) {
      return;
    }
    if (this._compact) {
      const notice = this.shadowRoot.querySelector(".first-card");
      const after = [notice, chipRow, under, stageArea, pageBox].find((node) => node?.parentNode === page);
      if (after) {
        after.after(advice);
      } else if (idle?.parentNode === page) {
        idle.before(advice);
      } else {
        page.append(advice);
      }
    } else if (page.firstChild !== advice) {
      page.prepend(advice);
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

  // The top bar: Back, the dashboard's name (pressed, it becomes a field),
  // the Tablets chip, the Theme button, the save state, Undo and Redo, and
  // the menu. In the compact layout the chip is under the picture and the
  // menu holds Theme and Rename (see _placeCompactParts and _openMenu).
  _renderHeader() {
    const header = this._els.header;
    if (!header) {
      return;
    }
    const focusKey = this._focusKeyIn(header);
    header.replaceChildren();
    // Home Assistant's menu button shows itself only when the sidebar is
    // out of reach (see the panel's header).
    const menu = document.createElement("ha-menu-button");
    menu.hass = this._hass;
    menu.narrow = this._narrow;
    header.append(menu);
    this._els.menu = menu;
    const back = this._iconButton("mdi:arrow-left", t("editor.back"), {
      className: "back",
      test: "back",
      focus: "back",
      onClick: () => this._back(),
    });
    const title = screenHeading("");
    title.dataset.focus = "title";
    this._els.title = title;
    const titleBlock = el("div", "title-block");
    titleBlock.append(title);
    header.append(back, titleBlock);
    this._fillTitle();
    const oldRow = this._els.chipRow;
    Object.assign(this._els, { chip: null, chipRow: null, themeButton: null, saveState: null, saveLive: null, undo: null, redo: null });

    if (this._status !== "ready") {
      oldRow?.remove();
      return;
    }
    const chip = this._chip();
    if (this._compact) {
      // Under the picture, in the page column (see _placeCompactParts).
      const row = el("div", "chip-row");
      row.append(chip);
      this._els.chipRow = row;
      if (oldRow?.parentNode) {
        oldRow.replaceWith(row);
      }
    } else {
      oldRow?.remove();
      header.append(chip);
      header.append(this._themeButton());
    }
    const actions = el("div", "header-actions");
    if (!this._readOnly) {
      // The state is shown; only "Not saved" and the first "Saved" after it
      // are read out, from a region of their own.
      const state = el("span", "save-state");
      state.dataset.test = "save-state";
      const live = el("span", "sr-only");
      live.setAttribute("aria-live", "polite");
      const undo = this._iconButton("mdi:undo", t("undo.undo"), {
        test: "undo",
        focus: "undo",
        focusAlt: "redo",
        onClick: () => this._undo(),
      });
      const redo = this._iconButton("mdi:redo", t("undo.redo"), {
        test: "redo",
        focus: "redo",
        focusAlt: "undo",
        onClick: () => this._redo(),
      });
      // In a bar under 400 px Redo is in the menu (see _menuBody).
      const shown = this._tight ? [undo] : [undo, redo];
      actions.append(state, live, ...shown);
      Object.assign(this._els, { saveState: state, saveLive: live, undo, redo: this._tight ? null : redo });
    }
    const more = this._iconButton("mdi:dots-vertical", t("editor.menu"), {
      test: "dash-menu",
      focus: "dash-menu",
      onClick: () => this._openMenu(),
    });
    more.setAttribute("aria-haspopup", "dialog");
    actions.append(more);
    header.append(actions);
    this._updateHeader();
    if (focusKey && !this.shadowRoot.activeElement) {
      this._focus(focusKey);
    }
  }

  // The dashboard's name: a button that turns into a field while it is
  // renamed, a plain heading on a dashboard that cannot be changed. A
  // failed rename says so under it for a while.
  _fillTitle() {
    const title = this._els.title;
    if (!title) {
      return;
    }
    const name = this._dashboard?.title || "";
    title.replaceChildren();
    title.closest(".title-block")?.querySelector(".rename-alert")?.remove();
    if (this._status !== "ready" || this._readOnly) {
      title.textContent = name;
      return;
    }
    if (this._renaming) {
      const input = document.createElement("input");
      input.type = "text";
      input.className = "title-field";
      input.value = name;
      input.maxLength = 80;
      input.autocomplete = "off";
      input.dataset.test = "dashboard-name";
      input.dataset.focus = "dashboard-name";
      input.setAttribute("aria-label", t("settings.name"));
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          this._finishRename(input.value);
        } else if (event.key === "Escape") {
          // Only the rename is cancelled; a selected card stays selected.
          event.preventDefault();
          event.stopPropagation();
          this._finishRename(null);
        }
      });
      input.addEventListener("blur", () => this._finishRename(input.value, { refocus: false }));
      title.append(input);
    } else {
      const button = makeButton(null, {
        className: "title-button",
        test: "title-button",
        focus: "title-button",
        onClick: () => this._startRename(),
      });
      button.title = t("editor.rename");
      button.append(el("span", "title-text", name));
      // The pencil shows on hover and focus. A phone has no hover, and the
      // pencil would take the name's room there.
      if (!this._compact) {
        button.append(icon("mdi:pencil"));
      }
      button.setAttribute("aria-label", `${name}, ${t("editor.rename")}`);
      title.append(button);
    }
    if (this._renameError) {
      const alert = alertLine(this._renameError);
      alert.classList.add("rename-alert");
      alert.dataset.test = "rename-error";
      title.after(alert);
    }
  }

  _startRename() {
    if (this._readOnly || this._status !== "ready") {
      return;
    }
    this._renaming = true;
    this._renameError = "";
    clearTimeout(this._renameTimer);
    this._fillTitle();
    const input = this._els.title?.querySelector("input");
    if (input) {
      input.focus({ preventScroll: true });
      input.select();
    }
  }

  // text: the new name (Enter, or the field lost focus), or null (Escape).
  // An empty or unchanged name changes nothing. A refused rename puts the
  // old name back and says why.
  async _finishRename(text, { refocus = true } = {}) {
    if (!this._renaming) {
      return;
    }
    this._renaming = false;
    const dashboard = this._dashboard;
    const value = typeof text === "string" ? text.trim() : "";
    const done = () => {
      this._fillTitle();
      if (refocus && (focusLost() || !this.shadowRoot.activeElement)) {
        this._focus("title-button");
      }
    };
    if (!value || value === dashboard?.title) {
      done();
      return;
    }
    // The new name shows at once; a refusal puts the old one back.
    const before = dashboard.title;
    dashboard.title = value;
    done();
    try {
      await this._updateDashboard({ title: value });
    } catch (error) {
      if (dashboard !== this._dashboard) {
        return;
      }
      dashboard.title = before;
      this._renameError = t("settings.failed", { message: errorMessage(error) });
      clearTimeout(this._renameTimer);
      this._renameTimer = setTimeout(() => {
        this._renameError = "";
        if (!this._renaming) {
          this._fillTitle();
        }
      }, RENAME_ERROR_MS);
      if (!this._renaming) {
        const had = this._focusKeyIn(this._els.header);
        this._fillTitle();
        if (had) {
          this._focus(had);
        }
      }
    }
  }

  // The Tablets chip: a dot in its tone and one short sentence; the whole
  // sentence is its tooltip and its name. It opens the Tablets pop-up.
  _chip() {
    const chip = makeButton(null, {
      className: "tablet-chip",
      test: "tablet-chip",
      focus: "tablet-chip",
      onClick: () => this._openTablets(),
    });
    chip.setAttribute("aria-haspopup", "dialog");
    this._els.chip = chip;
    this._fillChip();
    return chip;
  }

  _fillChip() {
    const chip = this._els.chip;
    if (!chip) {
      return;
    }
    const known = Array.isArray(this._tablets) && !this._tabletsError;
    const words = known
      ? chipWords(this._tablets, this._urlPath, t)
      : { text: t("editor.on_tablet_heading"), tone: "quiet", full: t("editor.on_tablet_heading") };
    if (chip.dataset.tone === words.tone && chip.title === words.full) {
      return;
    }
    chip.dataset.tone = words.tone;
    chip.title = words.full;
    chip.setAttribute("aria-label", words.full);
    // The words change in place: a press that starts while the tablets
    // change still lands on the chip.
    const text = chip.querySelector(".chip-words");
    if (text) {
      text.textContent = words.text;
      return;
    }
    chip.replaceChildren(el("span", "chip-dot"), el("span", "chip-words", words.text), icon("mdi:chevron-down"));
  }

  // The Theme button: a small swatch of the dashboard's theme and the word,
  // which only its swatch stands for in a narrow bar.
  _themeButton() {
    const button = makeButton(null, {
      className: "theme-button",
      test: "theme-button",
      focus: "theme-button",
      onClick: () => this._openTheme(),
    });
    button.setAttribute("aria-haspopup", "dialog");
    this._els.themeButton = button;
    this._fillThemeButton();
    return button;
  }

  _fillThemeButton() {
    const button = this._els.themeButton;
    if (!button) {
      return;
    }
    const theme = (this._library?.themes || []).find((entry) => entry?.id === this._themeId()) || {};
    const colour = (value, fallback) => (typeof value === "string" && /^#[0-9a-fA-F]{6}$/.test(value) ? value : fallback);
    const swatch = el("span", "theme-swatch small-swatch");
    swatch.setAttribute("aria-hidden", "true");
    swatch.style.backgroundColor = colour(theme.wall, "#101418");
    const card = el("span", "swatch-card");
    card.style.backgroundColor = colour(theme.card, "#181c23");
    const dot = el("span", "swatch-dot");
    dot.style.backgroundColor = colour(theme.acc, "#f5b547");
    card.append(dot);
    swatch.append(card);
    button.title = t("editor.theme_button");
    button.replaceChildren(swatch, el("span", "theme-word", t("editor.theme_button")));
  }

  // A round button with an icon only; its words are its name and tooltip.
  _iconButton(name, words, options) {
    const button = makeButton(null, { ...options, kind: "icon", ariaLabel: words });
    button.title = words;
    button.append(icon(name));
    return button;
  }

  _updateHeader() {
    const { saveState, saveLive, undo, redo } = this._els;
    if (!saveState) {
      return;
    }
    const state = this._queue?.state || "saved";
    const was = saveState.dataset.state;
    saveState.dataset.state = state;
    const icons = {
      saved: "mdi:check-circle-outline",
      error: "mdi:alert-circle",
      paused: "mdi:pause-circle-outline",
    };
    const words = {
      saved: t("save.saved"),
      error: t("save.error"),
      paused: t("save.paused"),
    };
    // In the compact layout only the icon shows; the word stays its name.
    saveState.replaceChildren(
      icon(icons[state] || "mdi:sync"),
      el("span", "save-word", words[state] || t("save.saving")),
    );
    if (state !== was && saveLive) {
      if (state === "error") {
        saveLive.textContent = words.error;
      } else if (state === "saved" && was === "error") {
        saveLive.textContent = words.saved;
      }
    }
    const active = this.shadowRoot.activeElement;
    undo.disabled = !canUndo(this._history);
    if (redo) {
      redo.disabled = !canRedo(this._history);
    }
    // Undo pressed back to the first step can no longer hold focus.
    if (active && (active === undo || active === redo) && active.disabled) {
      restoreFocus(this._els.header, active.dataset.focus);
    }
  }

  _saveStateChanged() {
    const state = this._queue?.state;
    const failedNow = state === "error" && this._lastSaveState !== "error";
    this._lastSaveState = state;
    this._updateHeader();
    this._renderBanners();
    if (state === "saved" && this._firstCardDue) {
      this._firstCardDue = false;
      this._showFirstCard();
    }
    if (failedNow) {
      // A save whose answer was lost with the connection may have been
      // stored all the same: what Home Assistant holds says (see
      // _checkRemote). The read waits while the connection is down.
      this._checkRemote();
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

  // Gives focus to the control named `key`. True only when it took it: a
  // control in the closed drawer or under the edit mode cannot.
  _focus(key) {
    return Boolean(this._focusFirstOf([key], { scroll: true }));
  }

  // Gives focus to the first of `keys` whose control takes it and returns
  // that control, or null. scroll: false leaves the page where it is.
  // inView: only a control that shows in the page column.
  _focusFirstOf(keys, { scroll = false, inView = false } = {}) {
    const nodes = [...this.shadowRoot.querySelectorAll("[data-focus]")];
    for (const key of keys) {
      for (const node of nodes) {
        if (node.dataset.focus !== key || node.disabled || (inView && !this._shows(node))) {
          continue;
        }
        node.focus({ preventScroll: !scroll });
        if (this.shadowRoot.activeElement === node) {
          return node;
        }
      }
    }
    return null;
  }

  // Whether the middle of `node` shows in the page column.
  _shows(node) {
    const column = this._els.page?.getBoundingClientRect();
    const rect = node.getBoundingClientRect();
    const middle = (rect.top + rect.bottom) / 2;
    return Boolean(column) && middle >= column.top && middle <= Math.min(column.bottom, window.innerHeight);
  }

  // The selected card's form takes focus, at its title.
  _focusForm() {
    const title = this._selected ? this._els.side?.querySelector(".side-title") : null;
    title?.focus({ preventScroll: true });
    return Boolean(title) && this.shadowRoot.activeElement === title;
  }

  _applyPendingFocus() {
    const key = this._pendingFocus;
    if (key && [...this.shadowRoot.querySelectorAll("[data-focus]")].some((node) => node.dataset.focus === key && !node.disabled)) {
      this._pendingFocus = null;
      this._focus(key);
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
    this._markFilled();
    this._renderAdvice();
  }

  // The editor's one filled button: "Add the first card" on an empty page,
  // else "Add card"; neither while a banner asks to retry a save or to
  // choose between two versions, whose own button is the filled one then.
  _markFilled() {
    const asking = this._queue?.state === "error" || Boolean(this._conflict);
    const first = this._els.overlay?.querySelector('[data-test="add-first-card"]') || null;
    first?.classList.toggle("primary", !asking);
    // Until the picture is drawn, whether the page is empty comes from the
    // dashboard itself, so "Add card" does not change its look twice.
    const view = this._draft?.views?.[this._view];
    const cards = (Array.isArray(view?.sections) ? view.sections : []).some(
      (section) => Array.isArray(section?.cards) && section.cards.length > 0,
    );
    const empty = this._preview ? Boolean(first) : !cards;
    this._els.addCard?.classList.toggle("primary", !asking && !empty);
  }

  // The page notices, one line each, in a fixed order: cards the tablet
  // leaves out, narrow columns, the sidebar. One shows; "+2 more" shows the
  // rest under it, in place. A notice's long explanation opens under its
  // line from "Why?". In the compact layout every notice shows, and a line
  // may wrap.
  _renderAdvice() {
    const box = this._els.advice;
    if (!box || this._status !== "ready") {
      return;
    }
    this._keepFocus(
      box,
      () => {
        const notices = this._pageNotices();
        const all = this._compact || this._noticesOpen || notices.length < 2;
        const nodes = (all ? notices : notices.slice(0, 1)).map((notice) => this._noticeLine(notice));
        if (!this._compact && notices.length > 1) {
          const open = this._noticesOpen;
          const more = makeButton(open ? t("editor.notices_fewer") : t("editor.notices_more", { count: notices.length - 1 }), {
            className: "notices-more",
            test: "notices-more",
            focus: "notices-more",
            onClick: () => {
              this._noticesOpen = !this._noticesOpen;
              this._renderAdvice();
            },
          });
          more.setAttribute("aria-expanded", String(open));
          nodes[0].querySelector(".notice-line").append(more);
        }
        box.replaceChildren(...nodes);
        box.classList.toggle("open", all && notices.length > 1);
      },
      // An answered notice is gone; focus goes on to what comes next. That
      // is never another notice's button, where one more Enter would make a
      // choice the person did not read: the page tabs on a wide screen, the
      // card list on a phone.
      () => (this._compact && this._focusFirst(this._els.list)) || this._focus(`tab:${this._view}`),
    );
  }

  // What each page notice says and offers, in their order.
  _pageNotices() {
    const notices = [];
    const hidden = this._els.stage && this._preview ? this._rows.filter((row) => !row.shown).length : 0;
    if (hidden) {
      const words = el(
        "span",
        "notice-words",
        hidden === 1 ? t("editor.not_shown_one") : t("editor.not_shown_many", { count: hidden }),
      );
      words.id = uid("not-shown");
      const go = makeButton(t("editor.not_shown_go"), {
        test: "not-shown-go",
        focus: "not-shown-go",
        onClick: () => this._goToHidden(),
      });
      go.setAttribute("aria-describedby", words.id);
      notices.push({ test: "not-shown-hint", tone: "warn", icon: "mdi:eye-off-outline", words, buttons: [go] });
    }

    const view = this._draft?.views?.[this._view];
    if (
      !this._readOnly &&
      pageKind(view) === "page" &&
      Array.isArray(view.sections) &&
      view.sections.length > 0 &&
      !usesWholeScreen(this._draft, this._view)
    ) {
      notices.push({
        test: "columns-notice",
        icon: "mdi:view-column-outline",
        words: el("span", "notice-words", t("editor.columns_title")),
        why: t("editor.columns_text"),
        buttons: [
          makeButton(t("editor.columns_fix"), {
            test: "use-whole-screen",
            focus: "use-whole-screen",
            onClick: () => {
              this._selected = null;
              this._commit(useWholeScreen(this._draft, this._view));
            },
          }),
        ],
      });
    }

    if (this._showSidebarNotice()) {
      notices.push({
        test: "sidebar-notice",
        icon: "mdi:dock-left",
        words: el("span", "notice-words", t("sidebar.title")),
        why: t("sidebar.text"),
        buttons: [
          makeButton(t("sidebar.hide"), {
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
        ],
        alert: this._sidebarError,
      });
    }
    return notices;
  }

  // One page notice: its icon, its sentence, "Why?" when it has more to
  // say, and its buttons; the long text and a failure under the line.
  _noticeLine({ test, tone = null, icon: name, words, why = null, buttons, alert = "" }) {
    const notice = el("div", "notice page-notice");
    notice.dataset.test = test;
    if (tone) {
      notice.dataset.tone = tone;
    }
    const line = el("div", "notice-line");
    words.title = words.textContent;
    line.append(icon(name), words);
    let text = null;
    if (why) {
      const open = this._whyOpen.has(test);
      text = el("p", "notice-why-text", why);
      text.id = uid("why");
      text.hidden = !open;
      const button = makeButton(t("editor.notice_why"), {
        className: "text",
        test: "notice-why",
        focus: `why:${test}`,
        onClick: () => {
          if (this._whyOpen.has(test)) {
            this._whyOpen.delete(test);
          } else {
            this._whyOpen.add(test);
          }
          this._renderAdvice();
        },
      });
      button.setAttribute("aria-expanded", String(open));
      button.setAttribute("aria-controls", text.id);
      line.append(button);
    }
    line.append(...buttons);
    notice.append(line);
    if (text) {
      notice.append(text);
    }
    if (alert) {
      notice.append(alertLine(alert));
    }
    return notice;
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

  // The page tabs and Add page. "Add card" sits at the strip's other end
  // (see _renderPageArea), so it is not redrawn with them. The selected
  // page's tab has a settings button after it, which opens the page pop-up;
  // the tabs stay one list for screen readers (aria-owns), with the button
  // outside it.
  _renderTabs() {
    const strip = this._els.tabList;
    if (!strip) {
      return;
    }
    this._keepFocus(strip, () => {
      strip.replaceChildren();
      const pages = pageList(this._draft);
      const list = el("div", "tabs");
      const owner = el("div", "tab-owner");
      owner.setAttribute("role", "tablist");
      owner.setAttribute("aria-label", t("page.tabs_label"));
      const ids = [];
      list.append(owner);
      for (const page of pages) {
        const selected = page.view === this._view;
        const tab = makeButton(null, { className: "tab", test: "page-tab", focus: `tab:${page.view}` });
        tab.id = `page-tab-${page.view}`;
        ids.push(tab.id);
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
        tab.addEventListener("click", () => this._selectView(page.view));
        tab.addEventListener("keydown", (event) => this._tabKeys(event, page.view, pages.length));
        list.append(tab);
        if (selected && !this._readOnly && page.kind === "page") {
          const gear = this._iconButton("mdi:cog-outline", t("page.settings", { page: name }), {
            className: "page-settings",
            test: "page-settings",
            focus: "page-settings",
            onClick: () => this._openPageMenu(),
          });
          gear.setAttribute("aria-haspopup", "dialog");
          list.append(gear);
        }
      }
      owner.setAttribute("aria-owns", ids.join(" "));
      strip.append(list);
      if (!this._readOnly) {
        const add = makeButton(null, { className: "add-page", test: "add-page", focus: "add-page", onClick: () => this._addPage() });
        // In the compact layout only its icon shows; its words stay its name.
        if (this._compact) {
          add.classList.add("icon");
          add.setAttribute("aria-label", t("page.add"));
          add.title = t("page.add");
          add.append(icon("mdi:plus"));
        } else {
          add.append(icon("mdi:plus"), el("span", null, t("page.add")));
        }
        strip.append(add);
      }
    });
    if (this._els.page) {
      this._els.page.setAttribute("role", "tabpanel");
      this._els.page.setAttribute("aria-labelledby", `page-tab-${this._view}`);
    }
    this._showTab();
  }

  // Scrolls the tab list so the selected page's tab is whole in it. Called
  // once Add page and Add card have their places beside the list, since
  // they make it narrower, and when the window's width changes.
  _showTab() {
    const list = this._els.tabList?.querySelector(".tabs");
    const tab = list?.querySelector('[aria-selected="true"]');
    if (!tab) {
      return;
    }
    // The tab and its settings button after it, both whole.
    const gear = tab.nextElementSibling?.classList.contains("page-settings") ? tab.nextElementSibling : null;
    const box = list.getBoundingClientRect();
    const first = tab.getBoundingClientRect();
    const last = (gear || tab).getBoundingClientRect();
    const rect = { left: Math.min(first.left, last.left), right: Math.max(first.right, last.right) };
    const pad = parseFloat(getComputedStyle(list).paddingInlineStart) || 0;
    if (rect.left < box.left + pad) {
      list.scrollLeft += rect.left - box.left - pad;
    } else if (rect.right > box.right - pad) {
      list.scrollLeft += Math.min(rect.right - box.right + pad, rect.left - box.left - pad);
    }
  }

  _tabKeys(event, view, count) {
    let next = null;
    if (event.key === "F2" && view === this._view && this.shadowRoot.querySelector('[data-test="page-settings"]')) {
      event.preventDefault();
      this._openPageMenu();
      return;
    }
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

  // The stage column: the page notices, the tablet picture in its frame,
  // and the status strip with the zoom, the screen pager and a failure to
  // update the picture. Without a status strip (compact and short) the
  // pager and the failure line are a row under the picture. The card list
  // and the notes go into the idle holder (see _renderSide); in the compact
  // layout the notes follow the picture, and the tablet lines, the notices
  // and the idle holder come after it in the one scrolling column.
  _renderPageArea() {
    const area = this._els.page;
    if (!area) {
      return;
    }
    this._stageObserver?.disconnect();
    this._stageObserver = null;
    this._els.pageHost?.__atCleanup?.();
    const { idlePage, stripEnd, advice } = this._els;
    // Focus in what is drawn again is given back once it is there.
    const adviceFocus = this._focusKeyIn(advice);
    const focusKey = this._focusKeyIn(area) || this._focusKeyIn(idlePage) || this._focusKeyIn(stripEnd) ||
      this._focusKeyIn(this._els.addCard);
    this._els.addCard?.remove();
    Object.assign(this._els, {
      stageArea: null,
      device: null,
      stage: null,
      pageHost: null,
      hits: null,
      overlay: null,
      screens: null,
      notes: null,
      list: null,
      listBlock: null,
      previewError: null,
      addCard: null,
      pageBox: null,
      under: null,
      zoomCaption: null,
      statusStrip: null,
      openCards: null,
    });
    area.replaceChildren();
    idlePage.replaceChildren();
    stripEnd.replaceChildren();

    const views = Array.isArray(this._draft?.views) ? this._draft.views : [];
    const view = views[this._view];
    const kind = pageKind(view);
    this._areaKey = `${this._view}:${kind}`;
    if (!view) {
      this._placeCompactParts();
      this._placeAdvice(adviceFocus);
      return;
    }

    if (kind !== "page") {
      const box = banner("page-box");
      box.dataset.test = "page-box";
      const old = kind === "old_preview";
      box.append(
        el("h2", null, t(old ? "page.old_preview_title" : "page.other_title")),
        el("p", null, t(old ? "page.old_preview_text" : "page.other_text")),
      );
      if (!this._readOnly) {
        box.append(
          makeButton(t("page.remove"), {
            kind: "danger",
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
      this._els.pageBox = box;
      this._placeCompactParts();
      this._placeAdvice(adviceFocus);
      this._restoreFocus(focusKey);
      return;
    }

    // "Add card": at the end of the page strip, or a floating button at the
    // bottom of the compact layout.
    if (!this._readOnly) {
      const add = makeButton(null, {
        className: this._compact ? "fab" : null,
        test: "add-card",
        focus: "add-card",
        onClick: (event) => this._openPicker(event.currentTarget),
      });
      add.append(icon("mdi:plus"), el("span", null, t("editor.add_card")));
      if (this._compact) {
        this._els.root.append(add);
      } else {
        stripEnd.append(add);
      }
      this._els.addCard = add;
    }
    this._showTab();

    const stageArea = el("div", "stage-area");
    stageArea.dataset.zoom = this._zoom;
    const device = el("div", "device");
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
    device.append(stage);
    stageArea.append(device);
    // A press on the picture outside every card clears the selection.
    stage.addEventListener("click", (event) => {
      if (this._selected && !event.target.closest("button")) {
        this._select(null);
      }
    });

    const screens = el("div", "screens");
    const previewError = el("div", "preview-error");
    const notes = el("div", "notes");
    const listBlock = el("section", "list-block");
    const list = el("ol", "card-list");
    listBlock.append(el("h2", null, t("list.title")), list);
    area.append(stageArea);
    if (this._hasStatusStrip()) {
      area.append(this._statusStrip(screens, previewError));
      idlePage.append(listBlock, notes);
    } else {
      const under = el("div", "under");
      under.append(screens, previewError);
      area.append(under);
      this._els.under = under;
      if (this._compact) {
        under.append(notes);
        idlePage.append(listBlock);
      } else {
        idlePage.append(listBlock, notes);
      }
    }
    Object.assign(this._els, { stageArea, device, stage, pageHost, hits, overlay, screens, notes, list, listBlock, previewError });
    this._placeCompactParts();
    this._placeAdvice(adviceFocus);

    // The free space decides the picture's size, so the stage area is
    // watched, not the picture.
    this._stageObserver = new ResizeObserver(() => {
      cancelAnimationFrame(this._frame);
      this._frame = requestAnimationFrame(() => this._drawCanvas());
    });
    this._stageObserver.observe(stageArea);

    this._drawCanvas();
    this._renderScreens();
    this._renderPreviewError();
    this._renderNotes();
    this._renderList();
    this._placeFirstCard();
    this._restoreFocus(focusKey);
  }

  _restoreFocus(key) {
    if (key && !this.shadowRoot.activeElement) {
      this._focus(key);
    }
  }

  // In the compact layout the page column goes on after the picture with the
  // Tablets chip and the idle holder (the notices go between them, see
  // _placeAdvice).
  _placeCompactParts() {
    const { page, chipRow, idle, stageArea, pageBox } = this._els;
    if (!this._compact || !page) {
      return;
    }
    // Only moved when out of place: a node that moves loses a press that
    // has started on it. The chip comes right under the picture, before
    // the screen pager.
    const top = [stageArea, pageBox].find((node) => node?.parentNode === page);
    if (chipRow && top) {
      if (top.nextElementSibling !== chipRow) {
        top.after(chipRow);
      }
    }
    const tail = [top ? null : chipRow, idle].filter(Boolean);
    const last = [...page.children].slice(-tail.length);
    if (!tail.every((node, index) => last[index] === node)) {
      page.append(...tail);
    }
  }

  // The first-card notice says where the dashboard goes now that it has a
  // card: to the one new tablet, to the Tablets list when several are new
  // (it names none of them), or to the Tablets pop-up. Without any tablet
  // there is no notice. Shown once per dashboard; it sends nothing.
  _showFirstCard() {
    const notice = this._firstCardFor();
    if (!notice) {
      return;
    }
    markFirstCardSeen(this._urlPath);
    this._firstCard = notice;
    // The notice already says "Saved.": a plain "Card added" toast would
    // only lie on top of it.
    if (this._toast && !this._toast.tied && this._toast.text === t("toast.card_added")) {
      clearTimeout(this._toastTimer);
      this._toast = null;
      this._renderToast();
    }
    this._placeFirstCard();
  }

  // What the notice says for the tablets as they are now; null for none.
  _firstCardFor() {
    const tablets = Array.isArray(this._tablets) ? this._tablets : [];
    if (this._status !== "ready" || tabletsShowing(tablets, this._urlPath).length) {
      return null;
    }
    const fresh = newTablets(tablets);
    if (fresh.length === 1) {
      return { kind: "one", mac: fresh[0].mac, name: tabletName(fresh[0]) };
    }
    if (fresh.length > 1) {
      return { kind: "many", count: fresh.length };
    }
    return approvedTablets(tablets).length ? { kind: "none" } : null;
  }

  // The tablets changed while the notice is up: it is drawn again for them,
  // or goes when it has nothing left to say. Focus inside it stays on the
  // same control when it is still there.
  _refreshFirstCard() {
    const before = this._firstCard;
    if (!before) {
      return;
    }
    const notice = this._firstCardFor();
    if (JSON.stringify(notice) !== JSON.stringify(before)) {
      this._firstCard = notice;
      this._placeFirstCard();
    }
  }

  // In a low wide window the stage's top padding is too short for the
  // floating notice, so it takes a row over the picture, as in medium.
  _firstCardRow() {
    if (this._compact) {
      return false;
    }
    if (this._band === "short" || this._band === "medium") {
      return true;
    }
    const top = (this._els.root || this).getBoundingClientRect().top;
    return window.innerHeight - top < FIRST_CARD_FLOAT_HEIGHT;
  }

  // Draws the notice over the top of the stage, where it takes no height.
  // On a phone the picture is small and the notice would cover the new
  // card, so it goes under the picture instead; in medium and short it is
  // a row over the picture.
  _placeFirstCard() {
    const area = this._els.stageArea;
    const old = this.shadowRoot.querySelector(".first-card");
    // Focus in the notice stays on the same control when it is drawn again.
    const key = old?.contains(this.shadowRoot.activeElement) ? this.shadowRoot.activeElement.dataset.focus : null;
    old?.remove();
    const notice = this._firstCard;
    this._firstCardIsRow = false;
    if (!notice || !area) {
      this._liftForFirstCard();
      if (key) {
        this._focus("add-card") || this._focus(`tab:${this._view}`);
      }
      return;
    }
    const box = el("div", "notice first-card");
    box.dataset.test = "first-card-notice";
    box.setAttribute("role", "status");
    const words =
      notice.kind === "one"
        ? t("editor.first_card_one", { tablet: notice.name })
        : notice.kind === "many"
          ? t("editor.first_card_many", { count: notice.count })
          : t("editor.first_card_none");
    box.append(icon("mdi:information-outline"), el("span", "notice-words", words));
    if (notice.kind === "none") {
      box.append(
        makeButton(t("editor.first_card_choose"), {
          test: "choose-tablet",
          focus: "choose-tablet",
          onClick: () => this._openTablets(),
        }),
      );
    } else {
      box.append(
        makeButton(t(notice.kind === "one" ? "editor.first_card_put" : "editor.first_card_go"), {
          test: "put-on-tablet",
          focus: "put-on-tablet",
          onClick: () => {
            // The tablet is handed over only while it is still the one new
            // tablet the notice names; else the Tablets list is shown.
            const now = this._firstCardFor();
            const one = notice.kind === "one" && now?.kind === "one" && now.mac === notice.mac;
            const handover = one ? { tablet: notice.mac, dashboard: this._urlPath } : {};
            this._firstCard = null;
            this._leaveFor(handover);
          },
        }),
      );
    }
    box.append(
      this._iconButton("mdi:close", t("editor.first_card_close"), {
        test: "first-card-close",
        focus: "first-card-close",
        onClick: () => {
          const had = box.contains(this.shadowRoot.activeElement);
          this._firstCard = null;
          box.remove();
          this._liftForFirstCard();
          if (had) {
            this._focus("add-card") || this._focus(`tab:${this._view}`);
          }
        },
      }),
    );
    if (this._compact) {
      // Under the picture and the Tablets chip.
      const chipRow = this._els.chipRow;
      (chipRow?.parentNode === area.parentNode ? chipRow : area).after(box);
    } else if (this._firstCardRow()) {
      // There the picture fills the stage (and the drawer covers its end),
      // so floating, the notice would lie on the new card: it is a row of
      // its own over the picture, with the page notices.
      this._firstCardIsRow = true;
      if (this._band !== "short" && this._band !== "medium") {
        box.classList.add("row");
      }
      area.before(box);
    } else {
      area.append(box);
    }
    this._liftForFirstCard();
    if (key && !this._focus(key)) {
      this._focus("add-card") || this._focus(`tab:${this._view}`);
    }
  }

  // Wide: the floating notice lies over the stage's top padding. Where it
  // would still reach the frame, the frame moves down into the free space
  // under it; the picture keeps its size.
  _liftForFirstCard() {
    const { device, stageArea } = this._els;
    if (!device) {
      return;
    }
    device.style.translate = "";
    const box = stageArea?.querySelector(":scope > .first-card");
    if (!box || this._compact || this._firstCardIsRow) {
      return;
    }
    const frame = device.getBoundingClientRect();
    const reach = box.getBoundingClientRect().bottom + 8 - frame.top;
    const room = stageArea.getBoundingClientRect().bottom - frame.bottom;
    if (reach > 0) {
      device.style.translate = `0 ${Math.round(Math.min(reach, Math.max(0, room)))}px`;
    }
  }

  // The 40 px strip under the picture: the size and the zoom on the left,
  // the screen pager in the middle, and on the right a failure to update
  // the picture and, in the medium layout, "Cards" for the drawer.
  _statusStrip(screens, previewError) {
    const strip = el("div", "status-strip");
    this._els.statusStrip = strip;
    const start = el("div", "status-start");
    const caption = el("span", "zoom-caption");
    this._els.zoomCaption = caption;
    start.append(caption, this._zoomControl());
    const end = el("div", "status-end");
    end.append(previewError);
    if (this._band === "medium") {
      const cards = makeButton(null, {
        test: "open-cards",
        focus: "open-cards",
        onClick: () => this._openDrawer(),
      });
      cards.append(icon("mdi:format-list-bulleted"), el("span", null, t("editor.cards_button")));
      cards.setAttribute("aria-expanded", "false");
      end.append(cards);
      this._els.openCards = cards;
    }
    strip.append(start, screens, end);
    return strip;
  }

  // "Fit" and "100 %": a radio group drawn as one pill.
  _zoomControl() {
    const group = el("div", "segmented zoom");
    group.setAttribute("role", "radiogroup");
    const name = uid("zoom");
    for (const [value, words, test] of [
      ["fit", t("editor.zoom_fit"), "zoom-fit"],
      ["100", t("editor.zoom_100"), "zoom-100"],
    ]) {
      const label = el("label");
      label.dataset.test = test;
      const input = el("input");
      input.type = "radio";
      input.name = name;
      input.value = value;
      input.checked = this._zoom === value;
      input.dataset.focus = test;
      input.addEventListener("change", () => this._setZoom(value));
      label.append(input, el("span", null, words));
      group.append(label);
    }
    return group;
  }

  // At 100 % the picture is the tablet's real size and the stage area
  // scrolls both ways, with the selected card brought into view.
  _setZoom(value) {
    this._zoom = value;
    if (this._els.stageArea) {
      this._els.stageArea.dataset.zoom = value;
    }
    this._drawCanvas();
  }

  _updateZoomCaption(width) {
    if (this._els.zoomCaption) {
      this._els.zoomCaption.textContent = t("editor.zoom_caption", { percent: Math.round((width / 1280) * 100) });
    }
  }

  // The picture's width in px: 1280 at 100 %, else as large as the stage
  // area holds once its padding and the frame's bezel are taken off. In the
  // compact layout only the width decides, up to 960 px.
  _stageWidth(stageArea = this._els.stageArea, device = this._els.device) {
    if (this._zoom === "100" && this._hasStatusStrip()) {
      return 1280;
    }
    const box = stageArea.getBoundingClientRect();
    if (!box.width) {
      return 0;
    }
    const pad = getComputedStyle(stageArea);
    const bezel = getComputedStyle(device);
    const sum = (style, a, b) => parseFloat(style[a]) + parseFloat(style[b]);
    const across = sum(pad, "paddingLeft", "paddingRight") + sum(bezel, "paddingLeft", "paddingRight");
    const down = sum(pad, "paddingTop", "paddingBottom") + sum(bezel, "paddingTop", "paddingBottom");
    if (this._compact) {
      return fitStage(Math.min(box.width - across, 960), Infinity);
    }
    return fitStage(box.width - across, box.height - down);
  }

  _drawCanvas() {
    const { stage, pageHost, hits, overlay } = this._els;
    if (!stage) {
      return;
    }
    const width = this._stageWidth();
    if (!width) {
      return;
    }
    stage.style.width = `${width}px`;
    stage.style.height = `${width / 1.6}px`;
    this._updateZoomCaption(width);
    // A card on the picture or "Add the first card" on an empty page that
    // has focus hands it on to the new drawing.
    const focused = this.shadowRoot.activeElement;
    const focusKey = focused && (hits.contains(focused) || overlay.contains(focused)) ? focused.dataset.focus : null;
    pageHost.__atCleanup?.();
    pageHost.replaceChildren();
    hits.replaceChildren();
    overlay.replaceChildren();

    if (!this._preview) {
      overlay.append(el("div", "stage-message", t("editor.loading")));
      this._markFilled();
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
    // A page with no cards is still a page on the tablet, with its side bar
    // entry; here it gets the "add the first card" help.
    if (!page || !Array.isArray(page.w) || !page.w.length) {
      const empty = el("div", "empty-page");
      empty.style.color = layout.theme?.tx || "#E8EAED";
      empty.append(el("p", null, t("editor.empty_page")));
      if (!this._readOnly) {
        empty.append(
          makeButton(t("editor.add_first_card"), {
            test: "add-first-card",
            focus: "add-first-card",
            onClick: (event) => this._openPicker(event.currentTarget),
          }),
        );
        empty.append(el("p", "small", t("editor.empty_page_tablet")));
      }
      overlay.append(empty);
      this._markFilled();
      this._keepHitFocus(focusKey);
      this._applyPendingFocus();
      this._afterDraw();
      return;
    }

    const sources = isObject(this._preview.sources) ? this._preview.sources : {};
    const items = (page.w || []).filter((item) => Object.hasOwn(sources, String(item.id)));
    const omitted = this._omittedOn(page);
    const count = items.length + omitted.length;
    let n = 0;

    for (const item of items) {
      n += 1;
      this._hitButton(sources[String(item.id)], item.r, scale, n, count, item.t === "heading" ? item.text : null);
    }
    this._drawOmitted(pageHost, omitted, scale);
    for (const warning of omitted) {
      n += 1;
      this._hitButton([warning.view, warning.section, warning.card], warning.r, scale, n, count, null);
    }

    this._keepHitFocus(focusKey);
    this._markFilled();
    this._applyPendingFocus();
    this._afterDraw();
  }

  // The card on the picture that had focus has it again after a new
  // drawing. When it is not on the picture any more (the card after a
  // removed one may be on another screen, or left out, or the last card
  // that could be drawn was removed), Add card takes it, or the page's tab.
  _keepHitFocus(key) {
    if (key && !this.shadowRoot.activeElement) {
      this._focus(key) || this._focus("add-first-card") || this._focus("add-card") || this._focus(`tab:${this._view}`);
    }
  }

  // The cards the tablet leaves out on the screen `page`, each with the
  // place the layout kept for it.
  _omittedOn(page) {
    const warnings = Array.isArray(this._preview?.warnings) ? this._preview.warnings : [];
    return warnings.filter(
      (warning) => warning.page === page.id && warningBoxKind(warning) === "omitted" && Array.isArray(warning.r),
    );
  }

  // A hatched "Left out" box for each of them on the page drawn in `host`.
  _drawOmitted(host, omitted, scale) {
    const wall = host.querySelector(".at-page");
    for (const warning of omitted) {
      const box = el("div", "warning-box");
      box.append(el("span", null, t("preview.omitted")));
      box.style.left = `${warning.r[0] * scale}px`;
      box.style.top = `${warning.r[1] * scale}px`;
      box.style.width = `${warning.r[2] * scale}px`;
      box.style.height = `${warning.r[3] * scale}px`;
      wall?.append(box);
    }
  }

  // After the picture or the selection changed: the drawer shift, the edit
  // mode's preview strip, the selected card in view at 100 %, and the toast.
  _afterDraw() {
    this._applyDrawerShift();
    this._drawEditPreview();
    if (this._zoom === "100" && this._hasStatusStrip()) {
      this._els.hits?.querySelector('.hit[aria-pressed="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
    this._liftForFirstCard();
    this._queuePlaceToast();
  }

  // Medium layout: the picture slides left just far enough for the selected
  // card to clear the open drawer, and back when the drawer closes. The
  // places are worked out without the slide, so a slide under way does not
  // count.
  _applyDrawerShift() {
    const { device, stage, stageArea, side, hits, page, root } = this._els;
    if (!device) {
      return;
    }
    let shift = 0;
    const hit = hits?.querySelector('.hit[aria-pressed="true"]');
    if (this._band === "medium" && root.classList.contains("drawer-open") && hit && getComputedStyle(this).direction !== "rtl") {
      const area = stageArea.getBoundingClientRect();
      const left = area.left - stageArea.scrollLeft + device.offsetLeft + stage.offsetLeft + parseFloat(hit.style.left);
      const right = left + parseFloat(hit.style.width);
      const drawerLeft = page.getBoundingClientRect().right - side.offsetWidth;
      const minLeft = area.left + parseFloat(getComputedStyle(stageArea).paddingLeft);
      shift = drawerShift(left, right, drawerLeft, minLeft);
    }
    this._shift = shift;
    device.style.transform = shift ? `translateX(${-shift}px)` : "";
    // An empty page's message is centred in the part of the picture the
    // open drawer leaves in view.
    const empty = this._els.overlay?.querySelector(".empty-page");
    if (empty) {
      let hidden = 0;
      if (this._band === "medium" && root.classList.contains("drawer-open") && getComputedStyle(this).direction !== "rtl") {
        const area = stageArea.getBoundingClientRect();
        const drawerLeft = page.getBoundingClientRect().right - side.offsetWidth;
        const right = area.left - stageArea.scrollLeft + device.offsetLeft + stage.offsetLeft + stage.offsetWidth - shift;
        hidden = Math.max(0, right - drawerLeft);
      }
      empty.style.right = hidden ? `${hidden}px` : "";
    }
  }

  // The tablet's rectangle of the selected card on the screen shown, or
  // null when it is not on that screen.
  _selectedRect(layout, screenIndex) {
    const key = this._selectedKey();
    const page = layout.pages?.[screenIndex];
    if (!key || !page) {
      return null;
    }
    const sources = isObject(this._preview?.sources) ? this._preview.sources : {};
    for (const item of Array.isArray(page.w) ? page.w : []) {
      const source = sources[String(item.id)];
      if (Array.isArray(source) && sourceKey(source) === key && Array.isArray(item.r)) {
        return item.r;
      }
    }
    for (const warning of this._omittedOn(page)) {
      if (sourceKey([warning.view, warning.section, warning.card]) === key) {
        return warning.r;
      }
    }
    return null;
  }

  // Compact edit mode: the strip above the form draws the page again, with
  // the selected card in its middle, at up to its real size, and the cards
  // around it dimmed. A card the tablet leaves out has its hatched box
  // there, as on the main picture. A card with no place on the screen shown
  // (one the tablet cannot draw) gets the whole page and no ring. It is
  // drawn again whenever the main picture is.
  _drawEditPreview() {
    const { editPreview: strip, previewHost: host, previewFrame: frame, previewMark: mark } = this._els;
    if (!strip?.isConnected) {
      return;
    }
    host.__atCleanup?.();
    host.replaceChildren();
    const layout = this._preview?.layout || {};
    const screens = pageScreens(this._preview, this._view);
    const screenIndex = screens[this._screen] ?? -1;
    const place = this._preview ? this._selectedRect(layout, screenIndex) : null;
    // A card with no place on the picture gets the strip's lowest height.
    strip.classList.toggle("whole", Boolean(this._preview) && !place);
    const box = strip.getBoundingClientRect();
    if (!this._preview || box.width < 48 || box.height < 48) {
      mark.hidden = true;
      return;
    }
    const rect = place || [0, 0, 1280, 800];
    const scale = Math.min(1, (box.width - 24) / rect[2], (box.height - 24) / rect[3]);
    renderPage(
      host,
      layout,
      screenIndex,
      { values: this._preview.values || {}, errors: {} },
      { sx: scale, sy: scale, interactive: false, tablet: true },
    );
    const page = layout.pages?.[screenIndex];
    if (page) {
      this._drawOmitted(host, this._omittedOn(page), scale);
    }
    // The selected card in the middle, but a page larger than the strip is
    // never moved so far that part of the strip shows nothing: the move
    // stops at the page's edge. A page smaller than the strip is centred.
    const fit = (centred, size, pageSize) =>
      pageSize <= size ? (size - pageSize) / 2 : Math.min(0, Math.max(size - pageSize, centred));
    const x = fit(box.width / 2 - (rect[0] + rect[2] / 2) * scale, box.width, 1280 * scale);
    const y = fit(box.height / 2 - (rect[1] + rect[3] / 2) * scale, box.height, 800 * scale);
    frame.style.transform = `translate(${x}px, ${y}px)`;
    mark.hidden = !place;
    Object.assign(mark.style, {
      left: `${x + rect[0] * scale}px`,
      top: `${y + rect[1] * scale}px`,
      width: `${rect[2] * scale}px`,
      height: `${rect[3] * scale}px`,
    });
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
    button.addEventListener("click", () => this._select(sameSource(source, this._selected) ? null : source, "hit"));
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

  // "Screen 1 of 2" with its arrows. In the status strip and in the short
  // layout its note is the tooltip and is read out; under the picture in
  // the compact layout it is a line of its own.
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
      const note = t("editor.screens_note", { count });
      const words = el("span", "screens-words", t("editor.screens", { n: this._screen + 1, count }));
      // While a failure shows in the status strip the pager reads "1 / 2",
      // so the failure keeps its room; the words are still read out.
      const brief = el("span", "screens-brief", `${this._screen + 1} / ${count}`);
      brief.setAttribute("aria-hidden", "true");
      const short = this._hasStatusStrip() || this._band === "short";
      if (short) {
        words.title = note;
        brief.title = note;
      }
      box.append(words, brief, previous, next, el("p", short ? "small sr-only" : "small", note));
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
    const text = t("editor.preview_failed", { message: errorMessage(this._previewError) });
    const line = el("p", "alert");
    line.setAttribute("role", "alert");
    // One line in the status strip, cut with "…"; the whole text is the
    // tooltip.
    const words = el("span", null, text);
    line.title = text;
    line.append(words);
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
    this._select(source, "row");
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
        button.addEventListener("click", () => this._select(row.source, "row"));
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
              kind: "danger",
              test: "row-remove",
              focus: `remove:${row.key}`,
              onClick: () => this._removeItem(row.source, "row"),
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

  // "1 card on this page is not shown on the tablet." is one of the page
  // notices now (see _pageNotices).
  _renderHint() {
    this._renderAdvice();
  }

  // Brings the first card the tablet leaves out into view in the list and
  // gives it focus. The list is in the inspector while no card is selected
  // (in the medium layout, in the drawer).
  _goToHidden() {
    if (!this._compact && (this._selected || (this._band === "medium" && !this._drawerOpen))) {
      this._drawerOpen = this._band === "medium";
      this._select(null);
    }
    const row = this._els.list?.querySelector('[data-test="list-row"][data-shown="false"]');
    if (row?.isConnected) {
      row.scrollIntoView({ block: "center" });
      row.focus({ preventScroll: true });
    }
  }

  // Medium layout: "Cards" opens the drawer with the card list, its close
  // button or Escape shuts it.
  _openDrawer() {
    this._drawerOpen = true;
    this._renderSide();
    this._focus("close-cards");
  }

  _closeDrawer() {
    this._drawerOpen = false;
    this._renderSide();
    this._focus("open-cards");
  }

  // The inspector. Nothing selected: the idle holder (the card list, the
  // notes, the page and dashboard settings), which in the compact layout is
  // the end of the page column instead. A card selected: its form; in the
  // compact layout that is the edit mode, a layer over the page strip and
  // the page column with a strip of the picture above the form. In the
  // medium layout the inspector is a drawer, closed while it has nothing to
  // do.
  _renderSide() {
    const { side, root, tabs, page, idle } = this._els;
    if (!side || this._status !== "ready") {
      return;
    }
    const source = this._selected;
    const card = source ? getCard(this._draft, source) : null;
    const edit = Boolean(this._compact && card);
    side.classList.toggle("sheet", edit);
    if (edit) {
      // Opening: what was pressed ("hit" or "row"; null for Add card and
      // the like), where the page column was, and the page. Leaving the edit
      // mode puts the person back there (see _backToPage).
      if (side.dataset.mode !== "edit") {
        this._editFrom = {
          from: this._opener?.from || null,
          scroll: this._opener?.scroll ?? page.scrollTop,
          view: this._view,
        };
      }
      side.dataset.mode = "edit";
      // A press on the layer outside its controls keeps focus in the editor,
      // so Escape still reaches it.
      side.tabIndex = -1;
    } else {
      delete side.dataset.mode;
      side.removeAttribute("tabindex");
      this._editFrom = null;
    }
    root.classList.toggle("editing", edit);
    // The layer's siblings behind it; the layer itself stays live.
    tabs.inert = edit;
    page.inert = edit;
    const drawer = this._band === "medium" && Boolean(card || this._drawerOpen);
    root.classList.toggle("drawer-open", drawer);
    side.inert = this._band === "medium" && !drawer;
    this._els.openCards?.setAttribute("aria-expanded", String(drawer));
    this._els.sideNotes = null;
    // The same card drawn again keeps where its form was scrolled to.
    const formScroll = this._els.editForm?.scrollTop || 0;
    this._els.previewHost?.__atCleanup?.();
    Object.assign(this._els, { editPreview: null, previewHost: null, previewFrame: null, previewMark: null, editForm: null });

    const fill = () => this._fillIdle(Boolean(card));
    if (this._compact) {
      this._keepFocus(idle, fill);
    }
    this._keepFocus(side, () => {
      side.replaceChildren();
      if (card) {
        // "Done" lets the card go and brings the card list back.
        const top = el("div", "side-top");
        const close = makeButton(null, {
          className: "sheet-close",
          test: "close-panel",
          focus: "close-panel",
          onClick: () => this._closeForm(),
        });
        close.append(icon("mdi:check"), el("span", null, t("editor.close_panel")));
        top.append(close);
        side.append(top);
        const form = this._itemForm(source, card);
        if (edit) {
          side.append(this._editPreviewStrip());
          const scroller = el("div", "edit-form");
          scroller.append(form);
          side.append(scroller);
          this._els.editForm = scroller;
          if (sourceKey(source) === this._sideKey) {
            scroller.scrollTop = formScroll;
          }
        } else {
          side.append(form);
        }
        this._els.sideNotes = form.querySelector(".item-notes");
        this._fillSideNotes();
        this._sideToTop(sourceKey(source));
        return;
      }
      if (this._compact) {
        return;
      }
      fill();
      this._sideToTop(`page:${this._view}`);
      // In the drawer the close button sits at the end of the list's
      // heading row.
      const { listBlock } = this._els;
      listBlock?.querySelector(".drawer-close")?.remove();
      if (this._band === "medium" && listBlock) {
        const close = this._iconButton("mdi:close", t("editor.close_panel"), {
          className: "drawer-close",
          test: "close-cards",
          focus: "close-cards",
          onClick: () => this._closeDrawer(),
        });
        listBlock.querySelector("h2").after(close);
      }
      side.append(idle);
    });
    this._drawEditPreview();
    this._applyDrawerShift();
    this._queuePlaceToast();
  }

  // The edit mode's strip of the picture; _drawEditPreview fills it.
  _editPreviewStrip() {
    const strip = el("div", "edit-preview tablet-pic");
    strip.dataset.test = "edit-preview";
    strip.setAttribute("aria-hidden", "true");
    const frame = el("div", "edit-frame");
    frame.inert = true;
    const shadow = frame.attachShadow({ mode: "open" });
    const style = el("style");
    style.textContent = rendererStyles + canvasStyles;
    const host = el("div");
    shadow.append(style, host);
    const mark = el("div", "edit-selected");
    mark.dataset.selected = "";
    mark.hidden = true;
    strip.append(frame, mark);
    Object.assign(this._els, { editPreview: strip, previewHost: host, previewFrame: frame, previewMark: mark });
    return strip;
  }

  // The idle holder's words. The page's and the dashboard's settings are
  // in their pop-ups (the page strip's settings button and the top bar).
  _fillIdle(selected) {
    const { idleIntro } = this._els;
    idleIntro.replaceChildren();
    if (selected) {
      return;
    }
    const views = Array.isArray(this._draft?.views) ? this._draft.views : [];
    const view = views[this._view];
    // A page the tablet does not show has no picture and no cards to press.
    if (view && pageKind(view) !== "page") {
      const line = el("p", null, t("editor.page_not_shown"));
      line.dataset.test = "side-intro";
      idleIntro.append(line);
    } else if (!this._readOnly) {
      const line = el("p", null, t("editor.nothing_selected"));
      line.dataset.test = "side-intro";
      idleIntro.append(line);
    }
  }

  // ---- Pop-ups ----

  // Opens one of the pop-ups; the one open before closes. In the compact
  // and the short layouts it is a sheet from the bottom.
  _openPop(kind, options) {
    this._popover = openPopover({
      root: this.shadowRoot,
      sheet: this._compact || this._band === "short",
      ...options,
      onClose: () => {
        if (this._popKind === kind) {
          this._popover = null;
          this._popKind = null;
          this._popAnchor = null;
        }
        options.onClose?.();
      },
    });
    this._popKind = kind;
    this._popAnchor = options.anchorKey;
    return this._popover;
  }

  // The Tablets pop-up: which tablets show this dashboard, Show here for
  // the others, a new tablet with its way to be set up, and the way to
  // the start screen's Tablets list. Nothing here turns a tablet on or
  // changes one without a press on Show here.
  _openTablets() {
    if (this._status !== "ready") {
      return;
    }
    this._openPop("tablets", {
      anchorKey: "tablet-chip",
      test: "tablets-pop",
      label: t("editor.on_tablet_heading"),
      first: "pop-title",
      build: (body) => body.append(this._tabletsBody()),
    });
  }

  _tabletsBody() {
    const box = el("div", "shown-on");
    box.dataset.test = "shown-on";
    const heading = el("h2", "pop-title", t("editor.on_tablet_heading"));
    heading.tabIndex = -1;
    heading.dataset.focus = "pop-title";
    heading.dataset.test = "shown-on-heading";
    box.append(heading);
    const failure = this._tabletsError ? errorMessage(this._tabletsError) : "";
    if (failure) {
      box.append(alertLine(t("tablets.load_failed", { message: failure })));
    }
    const tablets = Array.isArray(this._tablets) && !failure ? this._tablets : null;
    if (tablets === null) {
      if (!failure) {
        box.append(el("p", "small", t("tablets.loading")));
      }
    } else {
      // "Changes show on the tablet as you make them." while one does.
      if (!this._readOnly && tabletsShowing(tablets, this._urlPath).length) {
        box.append(el("p", "helper", t("editor.on_tablet_helper")));
      }
      const lines = el("ul", "tablet-lines");
      lines.dataset.test = "tablet-lines";
      const status = new Map();
      for (const line of captionLines(tablets, this._urlPath, t, Infinity)) {
        // With no tablet at all, "No tablets yet." below says it alone.
        if (line.kind === "nowhere" && tablets.length) {
          const nowhere = el("li", "tablet-line nowhere", line.text);
          nowhere.dataset.test = "tablet-line";
          nowhere.dataset.kind = line.kind;
          lines.append(nowhere);
        } else if (line.mac) {
          status.set(line.mac, line);
        }
      }
      // A row per tablet that is on: its name, what it shows, and for one
      // that shows this dashboard what is going on with it, in full.
      for (const row of shownOnRows(tablets, this._urlPath, this._tabRows || [], t)) {
        const item = el("li", "shown-on-row");
        item.dataset.test = "shown-on-row";
        item.dataset.mac = row.mac;
        item.dataset.here = String(row.here);
        const words = el("div", "shown-on-text");
        words.append(el("span", "shown-on-name", row.name), el("span", "small", row.text));
        item.append(words);
        const line = row.here ? status.get(row.mac) : null;
        if (line) {
          const text = el("p", "small tablet-line", line.text);
          text.dataset.test = "tablet-line";
          text.dataset.kind = line.kind;
          text.dataset.mac = row.mac;
          // The dot has the chip's tone, so the two agree.
          text.dataset.tone = chipTone(tablets.find((tablet) => tablet.mac === row.mac));
          item.append(text);
        }
        // A tablet always shows one dashboard, so there is nothing to untick
        // here; another tablet can be moved to this one.
        // Read-only dashboards keep it: showing one changes nothing in it.
        if (!row.here) {
          const button = makeButton(t("editor.on_tablet_show"), {
            test: "show-here",
            focus: `show-here:${row.mac}`,
            disabled: this._assigning.has(row.mac),
            onClick: () => this._showHere(row.mac),
          });
          button.dataset.mac = row.mac;
          button.setAttribute("aria-label", `${t("editor.on_tablet_show")}: ${row.name}`);
          item.append(button);
        }
        lines.append(item);
      }
      box.append(lines);
      // A tablet that came up and waits to be turned on is set up on the
      // start screen; the editor sends nothing for it.
      for (const tablet of newTablets(tablets)) {
        const item = el("div", "shown-on-new");
        item.dataset.test = "shown-on-new";
        item.append(el("p", null, t("editor.on_tablet_new", { tablet: tabletName(tablet) })));
        const go = makeButton(t("editor.on_tablet_set_up"), {
          test: "set-up-tablet",
          focus: `set-up:${tablet.mac}`,
          onClick: () => this._leaveFor({ tablet: tablet.mac, dashboard: this._urlPath }),
        });
        go.dataset.mac = tablet.mac;
        // Two new tablets give two such buttons: each names its tablet.
        go.setAttribute("aria-label", `${t("editor.on_tablet_set_up")}: ${tabletName(tablet)}`);
        item.append(go);
        box.append(item);
      }
      if (!tablets.length) {
        const none = el("p", "small", t("editor.on_tablet_none"));
        none.dataset.test = "shown-on-none";
        box.append(
          none,
          makeButton(t("editor.on_tablet_how"), {
            className: "text",
            test: "how-to-add",
            focus: "how-to-add",
            onClick: () => this._leaveFor({}),
          }),
        );
      }
    }
    if (this._shownOnError) {
      const alert = alertLine(this._shownOnError);
      alert.dataset.test = "shown-on-error";
      box.append(alert);
    }
    // With no tablet, "How to add a tablet" already goes there.
    if (!(Array.isArray(this._tablets) && !failure && !this._tablets.length)) {
      box.append(
        makeButton(t("editor.on_tablet_manage"), {
          className: "text",
          test: "manage-tablets",
          focus: "manage-tablets",
          onClick: () => this._leaveFor({}),
        }),
      );
    }
    return box;
  }

  // To the start screen, with what it should show first: { tablet,
  // dashboard } for a tablet to set up, {} for the Tablets list. Kept in
  // memory by the panel only; nothing is sent.
  _leaveFor(handover) {
    this._popover?.close({ refocus: false });
    this.onExit?.(handover);
  }

  // The theme gallery. Every theme tried while it is open is one step for
  // Undo, however long it stays open.
  _openTheme() {
    if (this._status !== "ready") {
      return;
    }
    this._themeGroup = {};
    this._openPop("theme", {
      anchorKey: this._compact ? "dash-menu" : "theme-button",
      test: "theme-gallery",
      label: t("settings.theme"),
      first: `theme:${this._themeId()}`,
      // Short: over the inspector, so the picture beside it stays in view.
      cover: this._band === "short" ? () => this._els.side?.getBoundingClientRect() : null,
      build: (body) =>
        body.append(
          buildThemeGallery({
            themes: this._library?.themes || [],
            themeId: this._themeId(),
            readOnly: Boolean(this._readOnly),
            preview: PREVIEW_THEMES,
            onTheme: (themeId) => {
              if (themeId !== this._themeId()) {
                this._commit(setTheme(this._draft, themeId), { side: false, group: this._themeGroup });
              }
            },
          }),
        ),
      onClose: () => {
        this._themeGroup = null;
        this._history = historyCloseGroup(this._history);
      },
    });
  }

  // The menu of the top bar. On a phone it also has Rename and Theme.
  _openMenu() {
    if (this._status !== "ready") {
      return;
    }
    this._openPop("menu", {
      anchorKey: "dash-menu",
      test: "dash-menu-pop",
      label: t("editor.menu"),
      first: "pop-title",
      build: (body) => body.append(this._menuBody()),
    });
  }

  _menuBody() {
    const extra = [];
    if (this._tight && !this._readOnly) {
      // The bar has no room for it. The menu closes, so the change shows.
      const redo = makeButton(null, {
        className: "menu-item",
        test: "redo",
        focus: "menu-redo",
        disabled: !canRedo(this._history),
        onClick: () => {
          this._popover?.close();
          this._redo();
        },
      });
      redo.append(icon("mdi:redo"), el("span", null, t("undo.redo")));
      extra.push(redo);
    }
    if (this._compact && !this._readOnly) {
      const rename = makeButton(null, {
        className: "menu-item",
        test: "menu-rename",
        focus: "menu-rename",
        onClick: () => {
          this._popover?.close({ refocus: false });
          this._startRename();
        },
      });
      rename.append(icon("mdi:pencil"), el("span", null, t("editor.rename")));
      extra.push(rename);
    }
    if (this._compact) {
      const theme = makeButton(null, {
        className: "menu-item",
        test: "menu-theme",
        focus: "menu-theme",
        onClick: () => this._openTheme(),
      });
      theme.append(icon("mdi:palette-outline"), el("span", null, t("editor.theme_button")));
      extra.push(theme);
    }
    return buildDashboardSettings({
      readOnly: Boolean(this._readOnly),
      showInSidebar: this._dashboard?.show_in_sidebar === true,
      urlPath: this._urlPath,
      extra,
      onSidebar: async (show) => {
        // Ticking the box is already the answer the sidebar notice asks for.
        if (show) {
          this._sidebarDismissed = true;
          keepInSidebar(this._urlPath);
        }
        await this._updateDashboard({ show_in_sidebar: show });
      },
      onDelete: () => {
        this._popover?.close({ refocus: false });
        return this._deleteDashboard();
      },
    });
  }

  // The page pop-up of the selected page: its name, its icon, its moves and
  // Delete. It closes when the page is gone.
  _openPageMenu() {
    if (this._status !== "ready" || this._readOnly) {
      return;
    }
    const view = this._draft?.views?.[this._view];
    if (pageKind(view) !== "page") {
      return;
    }
    // The page is followed by its place, which a move changes (see onMove).
    const page = { view: this._view };
    this._openPop("page", {
      anchorKey: "page-settings",
      test: "page-menu",
      label: t("page.heading"),
      first: "page-name",
      alive: () => pageKind(this._draft?.views?.[page.view]) === "page" && page.view === this._view,
      build: (body) => {
        const views = this._draft.views;
        const vi = page.view;
        const current = views[vi];
        body.append(
          buildPageSettings({
            title: typeof current.title === "string" ? current.title : "",
            icon: current.icon,
            index: vi,
            count: views.length,
            onRename: (text) =>
              this._commit(renamePage(this._draft, vi, text), {
                key: `${vi}:page-name`,
                continuous: true,
                side: false,
              }),
            onIcon: (name) => this._commit(setPageIcon(this._draft, vi, name), { side: false }),
            onMove: (delta) => {
              const result = movePage(this._draft, vi, delta);
              this._view = result.view;
              page.view = result.view;
              this._commit(result.config);
            },
            onDelete: () => {
              this._popover?.close({ refocus: false });
              this._removePage(vi, true);
            },
          }),
        );
      },
    });
  }

  // A different item starts at the top of the side panel; the same item
  // drawn again (after undo or a new preview) keeps where it was scrolled to.
  _sideToTop(key) {
    if (key !== this._sideKey) {
      this._sideKey = key;
      const scroller = this._els.editForm || this._els.side;
      if (scroller) {
        scroller.scrollTop = 0;
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
  // focus on to Add card or the tab of the page shown (the card's form when
  // the edit mode covers both), never to a button that removes something.
  // refocus: false when the toast's own button moves focus itself.
  _renderToast({ refocus = true } = {}) {
    const region = this._els.toasts;
    if (!region) {
      return;
    }
    const hadFocus = region.contains(this.shadowRoot.activeElement);
    this._drawToast(region);
    if (refocus && hadFocus && !this.shadowRoot.activeElement) {
      this._focus("add-card") || this._focus(`tab:${this._view}`) || this._focusForm();
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

  // The toast has one of three homes inside the editor: centred over the
  // stage column 16 px above the status strip (or the column's bottom), in
  // the compact layout centred above the floating "Add card", and in the
  // edit mode inside the layer, 16 px above its bottom and the safe area.
  // Over the stage it never lies across the tablet frame's edge: when the
  // grey under the frame has no room for it, it lies over the status strip
  // instead, 4 px above the column's bottom.
  _placeToast() {
    const region = this._els.toasts;
    const toast = region?.firstElementChild;
    const { root, side, page, addCard, statusStrip, device } = this._els;
    if (!toast || !region.isConnected || !root) {
      return;
    }
    // A toast under the pointer or with focus stays put, so its button is
    // still there when it is pressed.
    if (toast.matches(":hover") || toast.contains(this.shadowRoot.activeElement)) {
      return;
    }
    const box = root.getBoundingClientRect();
    const safe = parseFloat(getComputedStyle(root).getPropertyValue("--safe-bottom")) || 0;
    let area = page?.isConnected ? page.getBoundingClientRect() : box;
    let bottom;
    let place;
    if (side?.dataset.mode === "edit") {
      area = side.getBoundingClientRect();
      bottom = area.bottom - 16 - safe;
      place = "edit";
    } else if (this._compact) {
      area = box;
      const fab = addCard?.isConnected ? addCard.getBoundingClientRect() : null;
      bottom = fab && fab.height ? fab.top - 16 : box.bottom - 16 - safe;
      place = "fab";
    } else {
      const strip = statusStrip?.isConnected ? statusStrip.getBoundingClientRect() : null;
      bottom = (strip && strip.height ? strip.top : area.bottom) - 16;
      place = "stage";
    }
    region.style.maxWidth = `${Math.max(0, area.width - 32)}px`;
    const { width: w, height: h } = toast.getBoundingClientRect();
    if (place === "stage") {
      const strip = statusStrip?.isConnected ? statusStrip.getBoundingClientRect() : null;
      const frame = device?.isConnected ? device.getBoundingClientRect() : null;
      if (strip?.height && frame?.height && bottom - h < frame.bottom + 8) {
        bottom = strip.bottom - 4;
        place = "strip";
      }
    }
    Object.assign(region.style, {
      left: `${area.left + (area.width - w) / 2 - box.left}px`,
      top: `${bottom - h - box.top}px`,
    });
    region.dataset.place = place;
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

  // After Undo in a toast, focus goes to the card that came back. `restore`
  // ({ key, from, drawn }) says where it was: removed or chosen on the
  // picture ("hit") and drawn there, it gets focus on the picture and the
  // page column stays where it is; else its row in the card list, scrolled
  // into view, or the card on the picture when the list is out of reach
  // (in the closed drawer), or else the tab of the page shown. In the
  // compact layout an open edit mode covers both, so its title takes focus
  // then.
  _focusAfterUndo(restore) {
    const side = this._els.side;
    if (side?.classList.contains("sheet")) {
      side.querySelector(".side-title")?.focus({ preventScroll: true });
      return;
    }
    if (!restore) {
      this._focusFirstOf([`tab:${this._view}`]);
      return;
    }
    const hit = `hit:${restore.key}`;
    if (restore.drawn && restore.from === "hit") {
      this._focusHitWhenDrawn(hit);
      return;
    }
    const row = this._focusFirstOf([`row:${restore.key}`]);
    if (row) {
      row.scrollIntoView({ block: "nearest" });
    } else if (restore.drawn) {
      this._focusHitWhenDrawn(hit);
    } else {
      this._focusFirstOf([hit, `tab:${this._view}`]);
    }
  }

  // The picture is drawn again once the new preview is in, with the card
  // that came back under `key`. Until then the card with that key is the one
  // that had taken its place, or there is none and Add card holds focus;
  // either way the new drawing hands focus on to the card (see _drawCanvas).
  _focusHitWhenDrawn(key) {
    this._pendingFocus = key;
    this._focusFirstOf([key, "add-card", "add-first-card", `tab:${this._view}`]);
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
  // typing into it is never interrupted. group: changes with the same
  // group are one step for Undo (the theme gallery).
  _commit(config, { key = null, continuous = false, side = true, group = null } = {}) {
    if (this._readOnly) {
      return false;
    }
    const before = this._history;
    this._history = historyPush(this._history, config, { key, now: Date.now(), group });
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
    this._fillThemeButton();
    this._popover?.update();
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

  // from: "hit" or "row", what was pressed to choose the card.
  _select(source, from = null) {
    // For the compact edit mode, which remembers what opened it (see
    // _renderSide).
    this._opener = source ? { from, scroll: this._els.page?.scrollTop || 0 } : null;
    // Kept while the card is selected: Undo after its form's Remove brings
    // focus back where it was chosen (see _focusAfterUndo).
    this._selectedFrom = source ? from : null;
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
    this._opener = null;
    // The form took the place of what was pressed: the edit mode covers the
    // page, and beside the picture the form replaces the list. Its title
    // takes focus then, so the keyboard goes on in the form.
    if (source && (this._compact || !this.shadowRoot.activeElement)) {
      this._focusForm();
    }
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

  _closeForm() {
    const key = this._selectedKey();
    if (this._compact) {
      this._leaveEdit(key);
      return;
    }
    this._select(null);
    // The card's row in the list, or the card on the picture when the list
    // is in the closed drawer.
    if (key) {
      this._focus(`row:${key}`) || this._focus(`hit:${key}`);
    }
  }

  // Compact: Done or Escape closes the edit mode, and the person is back on
  // the page as they left it (see _backToPage).
  _leaveEdit(key) {
    const from = this._editFrom;
    this._select(null);
    this._backToPage(from, key ? [`hit:${key}`] : [], key ? [`row:${key}`] : []);
  }

  // Compact: back on the page column after the edit mode, or after a card
  // was removed there. The column is put where it was (`from.scroll`) and
  // nothing is scrolled to, so the picture stays where the person left it.
  // Focus goes to the first control that takes it: one of `rows` when the
  // person was in the list (`from.from` is "row"; a row that the changed
  // list has moved out of view is brought back the nearest way), else one
  // of `hits` that shows on the picture, else Add card.
  _backToPage(from, hits, rows) {
    const here = this._columnBack(from);
    if (here && from.from === "row") {
      const row = this._focusFirstOf(rows);
      if (row) {
        if (!this._shows(row)) {
          row.scrollIntoView({ block: "nearest" });
        }
        return;
      }
    }
    this._focusFirstOf(hits, { inView: true }) ||
      this._focusFirstOf(["add-card"]) ||
      this._focusFirstOf(rows, { inView: true }) ||
      this._focusFirstOf([...hits, ...rows, `tab:${this._view}`]);
  }

  // Compact: puts the page column where it was scrolled when the edit mode
  // opened. The column is shorter while the edit mode is open (the settings
  // are left out), which can move it. False when that was on another page.
  _columnBack(from) {
    const page = this._els.page;
    const here = Boolean(from) && from.view === this._view;
    if (here && page && this._compact) {
      page.scrollTop = from.scroll;
    }
    return here;
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
      this._removeItem(source, where);
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

  // where: "form" (the card's own Remove button), or "hit" or "row" when
  // it was removed on the picture or in the list.
  _removeItem(source, where = "form") {
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
    // Compact: where the person was. The edit mode knows what opened it;
    // without it, the picture or the list as it is scrolled now.
    const from =
      where === "form"
        ? this._editFrom
        : { from: where, scroll: this._els.page?.scrollTop || 0, view: this._view };
    // Undo puts the card back where it was, so its row and its card on the
    // picture have this key again. It also goes back to where the person
    // was: the picture when the card was removed or chosen there.
    const key = sourceKey(source);
    const restore = {
      key,
      from: where === "form" ? (this._compact ? this._editFrom?.from : this._selectedFrom) || null : where,
      drawn: Boolean(this._els.hits?.querySelector(`[data-focus="hit:${key}"]`)),
    };
    this._selected = null;
    if (!this._commit(removeItem(this._draft, source))) {
      return;
    }
    if (devices) {
      this._showToast(t("toast.card_removed_for", { device: devices.name }), { undo: true, devices, restore });
      // The next step is in the toast, which stays while it has focus.
      if (this._focusIn(this._els.toasts, "toast-replace")) {
        this._columnBack(from);
        return;
      }
    } else {
      this._showToast(t(heading ? "toast.heading_removed" : "toast.card_removed"), { undo: true, restore });
    }
    // The pressed control went with its card. Focus goes on to the card
    // that took its place: its row in the list, or the card on the picture
    // when the list is out of reach (in the closed drawer), or else Add
    // card. In the compact layout a card removed on the picture, or in an
    // edit mode opened there, is followed by the next card on the picture,
    // and the page column stays where it was (see _backToPage).
    const next = this._rows[index];
    const rows = next ? [`row:${next.key}`] : [];
    const hits = next ? [`hit:${next.key}`] : [];
    if (this._compact) {
      this._backToPage(from, hits, rows);
    } else {
      this._focusFirstOf([...rows, ...hits, "add-card", `tab:${this._view}`], { scroll: true });
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
    const before = this._draft;
    const result = moveItem(before, source, delta);
    const key = sourceKey(result.source);
    // Moved from its form, or on the picture beside the inspector, the card
    // is selected. Moved from the keyboard in the list, or on the picture
    // in the compact layout, it is not: its form would take the list's
    // place or cover the page, and the next press would move nothing.
    if (where === "form" || (where === "hit" && !this._compact)) {
      this._selected = result.source;
    } else if (this._selected) {
      this._selected = followItem(before, result.config, this._selected);
    }
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
    // The new page opens with its pop-up, its name ready to be typed over.
    if (this._commit(result.config)) {
      this._openPageMenu();
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
        // A phone on its side gets the full-screen picker too.
        compact: this._compact || this._band === "short",
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
    // The first card of a dashboard no tablet shows: a notice says where
    // it goes once it is saved (see _saveStateChanged).
    const first =
      dashboardCards(this._draft) === 0 &&
      Array.isArray(this._tablets) &&
      !tabletsShowing(this._tablets, this._urlPath).length &&
      !firstCardSeen().includes(this._urlPath);
    const added = addCard(this._draft, vi, result.component, result.params);
    if (!added.source) {
      return;
    }
    this._firstCardDue = first;
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
      // The edit mode opens with the new card in its strip of the picture.
      this._els.side?.querySelector(".side-title")?.focus({ preventScroll: true });
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
    if (typeof changes.title === "string" && !this._renaming) {
      this._fillTitle();
    }
    if (typeof changes.show_in_sidebar === "boolean") {
      this._renderBanners();
    }
    if (this._popKind === "menu") {
      this._popover?.update();
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
    this._tabletsShown();
  }

  // The tablets changed: the chip says so, the Tablets pop-up too.
  _tabletsShown() {
    this._fillChip();
    this._refreshFirstCard();
    if (this._popKind === "tablets") {
      this._popover?.update();
    }
  }

  // Reads the TAB-1 dashboards with their titles, in the one order, for the
  // Tablets pop-up and the delete question. Kept as it was when Home
  // Assistant cannot be reached.
  async _loadTabRows() {
    if (!this._hass || this._status !== "ready") {
      return;
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
      return;
    }
    if (seq !== this._tabRowsSeq) {
      return;
    }
    this._tabRows = rows;
    this._tabletsShown();
  }

  // Several saves in a row are read once, after the last.
  _scheduleTabRows() {
    clearTimeout(this._tabRowsTimer);
    this._tabRowsTimer = setTimeout(() => {
      this._tabRowsTimer = null;
      this._loadTabRows();
    }, 300);
  }

  async _showHere(mac) {
    if (this._assigning.has(mac) || !this._conn) {
      return;
    }
    const run = this._run;
    const urlPath = this._urlPath;
    this._assigning.add(mac);
    this._shownOnError = "";
    this._tabletsShown();
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
        this._tabletsShown();
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
    await this._loadTabRows();
    // Without the dashboards it cannot tell where the tablets go, and it
    // does not guess.
    if (!this._tabRows || !Array.isArray(this._tablets)) {
      return "";
    }
    return deleteNote(this._tablets, this._urlPath, this._tabRows, t);
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

  // Escape lets the selected card go (in the compact layout it closes the
  // edit mode, as Done does), or shuts a drawer that
  // "Cards" opened.
  _handleEscape(event) {
    if (event.key !== "Escape" || this._dialogOpen()) {
      return;
    }
    if (!this._selected) {
      if (this._band === "medium" && this._drawerOpen) {
        event.preventDefault();
        this._closeDrawer();
      }
      return;
    }
    event.preventDefault();
    const key = this._selectedKey();
    const active = this.shadowRoot.activeElement;
    const fromSide = active && this._els.side?.contains(active);
    if (this._compact) {
      this._leaveEdit(key);
      return;
    }
    this._select(null);
    if (fromSide || !this.shadowRoot.activeElement) {
      this._focus(`hit:${key}`) || this._focus(`row:${key}`);
    }
  }
}
