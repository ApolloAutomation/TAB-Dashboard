import { format, subscriptionKey } from "./logic.js";

let stringsCache = null;
let stringsPromise = null;
let libraryCache = null;
let libraryPromise = null;

const cardSubscriptions = new Map();
// A failed or ended subscription is tried again after 2 s, 4 s, 8 s ... up to 30 s.
const RETRY_FIRST_MS = 2000;
const RETRY_MAX_MS = 30000;
// A subscribe Home Assistant does not know is tried again for ten minutes.
const UNKNOWN_FOR_MS = 600000;
// Home Assistant's connection answers with this code what was under way
// when the connection was lost.
const CONNECTION_LOST = 3;

export async function getConnection(hass) {
  if (hass?.connection) {
    return hass.connection;
  }
  // Home Assistant imports its core module and this one side by side, so the
  // promise may not exist yet when this module starts.
  for (let waited = 0; !window.hassConnection && waited < 30000; waited += 50) {
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  const result = await window.hassConnection;
  return result.conn;
}

export async function loadStrings(conn) {
  if (stringsCache) {
    return stringsCache;
  }
  if (!stringsPromise) {
    stringsPromise = conn
      .sendMessagePromise({ type: "apollo_tab/strings" })
      .then((result) => {
        stringsCache = result?.strings || {};
        return stringsCache;
      })
      .catch((error) => {
        stringsPromise = null;
        throw error;
      });
  }
  return stringsPromise;
}

export function t(key, vars) {
  return format(stringsCache?.[key] ?? key, vars);
}

export async function loadLibrary(conn, { force = false } = {}) {
  if (!force && libraryCache) {
    return libraryCache;
  }
  if (!force && libraryPromise) {
    return libraryPromise;
  }

  const request = conn
    .sendMessagePromise({ type: "apollo_tab/library" })
    .then((result) => {
      libraryCache = result || null;
      return libraryCache;
    })
    .catch(() => null)
    .finally(() => {
      libraryPromise = null;
    });

  libraryPromise = request;
  return request;
}

export function getCachedLibrary() {
  return libraryCache;
}

// True for the answer to something the lost connection cut off. The code
// comes as the error itself, on it, or inside an error result.
function connectionLost(error) {
  return (
    error === CONNECTION_LOST || error?.code === CONNECTION_LOST || error?.error?.code === CONNECTION_LOST
  );
}

// After a lost connection (a laptop asleep, a Wi-Fi drop, a browser tab
// Home Assistant disconnected while hidden, a restart of Home Assistant),
// Home Assistant's connection opens its subscriptions again by itself and
// fires "ready". It tells nobody when its own new subscribe fails, and while
// Home Assistant starts it does fail. So a subscription made with these
// options is left alone by the connection, and reopen runs at "ready" to
// open it again from here. A stand-in connection without events keeps its
// own way of reopening.
function reopenOnReady(conn, reopen) {
  const watching = typeof conn.addEventListener === "function";
  if (watching) {
    conn.addEventListener("ready", reopen);
  }
  return {
    watching,
    options: watching ? [{ resubscribe: false }] : [],
    stop() {
      if (watching) {
        conn.removeEventListener?.("ready", reopen);
      }
    },
  };
}

// Subscribes to library, layout or tablet events and keeps the subscription
// alive. The server ends it with a not_loaded event when the integration is
// unloaded or reloaded; it is then opened again after 2 s, 4 s, 8 s ... up
// to 30 s. onRestored runs after each such reopening, because changes made
// in between were not reported.
//
// When the connection comes back after it was lost, the subscription is
// opened again here (see reopenOnReady). The events from the time in between
// are lost. With afterReconnect, onRestored runs once the subscription is
// open again.
//
// While Home Assistant starts, the integration's commands are not there yet
// and it answers unknown_command. An older integration that was updated but
// not restarted answers the same for good. So that subscribe is tried again
// in the same way, for ten minutes on one connection. onError hears about it
// at once when no subscribe has worked yet, so the caller can say so
// meanwhile, and otherwise when the ten minutes are over. A try that works
// brings the events as usual.
//
// A subscribe that fails for another reason, such as a user who is not an
// administrator, is not tried again; onError hears about it. After any
// failure the next connection tries once more.
function keepSubscribed(conn, type, onEvent, onRestored, { afterReconnect = false, onError = null } = {}) {
  let active = true;
  let unsubscribe = null;
  let timer = null;
  let delay = 0;
  let attempt = 0;
  let lost = false;
  // opened: a subscribe has worked. told: onError heard about the
  // unknown_command that is being tried again. unknownFor: the waits spent
  // on it on this connection, in milliseconds.
  let opened = false;
  let told = false;
  let unknownFor = 0;

  const ready = reopenOnReady(conn, () => {
    if (!active) {
      return;
    }
    clearTimeout(timer);
    timer = null;
    // The subscription went with the old connection. Its unsubscribe holds
    // a command number that may be another command's now, so it is dropped,
    // not called.
    unsubscribe = null;
    lost = lost || afterReconnect;
    // A new connection starts the waits again.
    delay = 0;
    unknownFor = 0;
    begin();
  });

  const retry = () => {
    if (!active || timer) {
      return;
    }
    lost = true;
    delay = delay ? Math.min(delay * 2, RETRY_MAX_MS) : RETRY_FIRST_MS;
    timer = setTimeout(() => {
      timer = null;
      begin();
    }, delay);
  };

  const begin = () => {
    // Each attempt has its own number, so a replaced attempt is ignored.
    const current = attempt + 1;
    attempt = current;

    let request;
    try {
      request = conn.subscribeMessage(
        (event) => {
          if (!active || current !== attempt) {
            return;
          }
          if (event?.type === "not_loaded") {
            attempt += 1;
            const stop = unsubscribe;
            unsubscribe = null;
            stop?.();
            retry();
            return;
          }
          onEvent(event);
        },
        { type },
        ...ready.options,
      );
    } catch (error) {
      request = Promise.reject(error);
    }

    Promise.resolve(request)
      .then((stop) => {
        if (!active || current !== attempt) {
          stop?.();
          return;
        }
        unsubscribe = stop;
        delay = 0;
        opened = true;
        told = false;
        if (lost) {
          lost = false;
          onRestored?.();
        }
      })
      .catch((error) => {
        if (!active || current !== attempt) {
          return;
        }
        // The connection was lost while the subscribe was under way; it is
        // sent again at "ready".
        if (ready.watching && connectionLost(error)) {
          return;
        }
        const unknown = error?.code === "unknown_command";
        if (error?.code === "not_loaded" || (unknown && unknownFor < UNKNOWN_FOR_MS)) {
          if (unknown && !opened && !told) {
            told = true;
            onError?.(error);
          }
          retry();
          if (unknown) {
            unknownFor += delay;
          }
          return;
        }
        // Other failures, such as a user who is not an administrator, are
        // final. So is unknown_command once it was tried for long enough,
        // which a caller told at the start has heard already.
        if (!unknown || !told) {
          onError?.(error);
        }
      });
  };

  begin();

  return () => {
    active = false;
    attempt += 1;
    clearTimeout(timer);
    timer = null;
    ready.stop();
    const stop = unsubscribe;
    unsubscribe = null;
    stop?.();
  };
}

export function onLibraryChanged(conn, callback) {
  let active = true;

  const refresh = async () => {
    libraryCache = null;
    const library = await loadLibrary(conn, { force: true });
    if (active) {
      callback(library);
    }
  };

  const stop = keepSubscribed(conn, "apollo_tab/library/subscribe", refresh, refresh);
  return () => {
    active = false;
    stop();
  };
}

// onEvent gets every converted and removed event; onRestored runs when the
// subscription was reopened, also after the connection came back, and the
// caller should load everything again.
export function onLayoutChanged(conn, onEvent, onRestored) {
  return keepSubscribed(conn, "apollo_tab/layout/subscribe", onEvent, onRestored, { afterReconnect: true });
}

function replay(record, listener) {
  if (record.lastMain) {
    listener(record.lastMain);
  }
  if (record.lastValues) {
    listener(record.lastValues);
  }
}

function deliver(record, event) {
  if (event?.type === "init") {
    record.values = {};
    record.errors = {};
    record.lastMain = event;
    record.lastValues = null;
  } else if (event?.type === "error") {
    record.lastMain = event;
  } else if (event?.type === "values") {
    const incomingValues = event.values || {};
    const incomingErrors = event.errors || {};

    for (const [key, value] of Object.entries(incomingValues)) {
      record.values[key] = value;
      delete record.errors[key];
    }
    for (const [key, value] of Object.entries(incomingErrors)) {
      delete record.values[key];
      record.errors[key] = value;
    }

    record.lastValues = {
      type: "values",
      values: { ...record.values },
      errors: { ...record.errors },
    };
    event = record.lastValues;
  } else {
    return;
  }

  for (const listener of record.listeners) {
    listener(event);
  }
}

function forget(record) {
  record.closed = true;
  record.attempt += 1;
  clearTimeout(record.retryTimer);
  clearTimeout(record.closeTimer);
  record.retryTimer = null;
  record.closeTimer = null;
  record.ready.stop();
  if (cardSubscriptions.get(record.key) === record) {
    cardSubscriptions.delete(record.key);
  }
}

function scheduleRetry(record) {
  if (record.closed) {
    return;
  }
  if (!record.listeners.size) {
    // Without a pending close request, the close timer forgets it.
    if (record.closeRequested) {
      forget(record);
    }
    return;
  }
  if (record.retryTimer) {
    return;
  }

  // Home Assistant may be restarting or reloading the integration.
  record.retryDelay = record.retryDelay
    ? Math.min(record.retryDelay * 2, RETRY_MAX_MS)
    : RETRY_FIRST_MS;
  record.retryTimer = setTimeout(() => {
    record.retryTimer = null;
    if (record.closed || !record.listeners.size) {
      forget(record);
    } else {
      beginSubscription(record);
    }
  }, record.retryDelay);
}

function beginSubscription(record) {
  // Each attempt has its own number, so a replaced attempt's late events,
  // results and errors are ignored.
  const attempt = record.attempt + 1;
  record.attempt = attempt;
  record.starting = true;
  record.failed = false;

  let request;
  try {
    request = record.conn.subscribeMessage(
      (event) => {
        if (record.closed || record.attempt !== attempt) {
          return;
        }

        deliver(record, event);

        // The server stopped this subscription for good when the integration
        // was unloaded; only a new subscribe brings the card back.
        if (event?.type === "error" && event.code === "not_loaded") {
          record.attempt += 1;
          record.starting = false;
          record.failed = true;

          const unsubscribe = record.unsubscribe;
          record.unsubscribe = null;
          unsubscribe?.();

          scheduleRetry(record);
        }
      },
      {
        type: "apollo_tab/card/subscribe",
        card: record.card,
        dashboard: record.dashboard ?? null,
      },
      ...record.ready.options,
    );
  } catch (error) {
    request = Promise.reject(error);
  }

  Promise.resolve(request)
    .then((unsubscribe) => {
      if (record.closed || record.attempt !== attempt) {
        unsubscribe?.();
        return;
      }

      record.starting = false;
      record.retryDelay = 0;
      if (!record.listeners.size && record.closeRequested) {
        unsubscribe?.();
        forget(record);
      } else {
        record.unsubscribe = unsubscribe;
      }
    })
    .catch((error) => {
      if (record.closed || record.attempt !== attempt) {
        return;
      }

      record.starting = false;
      // The connection was lost while the subscribe was under way. The card
      // keeps its picture and is subscribed again at "ready".
      if (record.ready.watching && connectionLost(error)) {
        if (record.closeRequested && !record.listeners.size) {
          forget(record);
        }
        return;
      }
      record.failed = true;
      deliver(record, {
        type: "error",
        code: error?.code || "invalid_card",
        message: error?.message || String(error),
      });

      if (record.closed || record.attempt !== attempt) {
        return;
      }
      scheduleRetry(record);
    });
}

// The connection is back and the card's subscription went with the old one
// (see reopenOnReady). Its unsubscribe holds a command number that may be
// another command's now, so it is dropped, not called. A subscribe Home
// Assistant does not take yet is tried again like any failed one, and the
// card says meanwhile that it waits.
function watchCardConnection(record) {
  record.ready = reopenOnReady(record.conn, () => {
    if (record.closed) {
      return;
    }
    clearTimeout(record.retryTimer);
    record.retryTimer = null;
    record.retryDelay = 0;
    record.unsubscribe = null;
    beginSubscription(record);
  });
}

export function subscribeCard(conn, card, dashboard, listener) {
  const key = subscriptionKey(card, dashboard);
  let record = cardSubscriptions.get(key);

  if (!record) {
    record = {
      key,
      conn,
      card,
      dashboard,
      listeners: new Set(),
      unsubscribe: null,
      starting: false,
      failed: false,
      retryTimer: null,
      retryDelay: 0,
      closed: false,
      closeTimer: null,
      closeRequested: false,
      attempt: 0,
      ready: null,
      values: {},
      errors: {},
      lastMain: null,
      lastValues: null,
    };
    cardSubscriptions.set(key, record);
    watchCardConnection(record);
    beginSubscription(record);
  } else if (record.failed && !record.starting) {
    // A failed subscription is tried again at once for a newcomer, which
    // should not first see the old error.
    if (record.conn !== conn) {
      record.ready.stop();
      record.conn = conn;
      watchCardConnection(record);
    }
    record.card = card;
    record.dashboard = dashboard;
    clearTimeout(record.retryTimer);
    record.retryTimer = null;
    record.lastMain = null;
    record.lastValues = null;
    beginSubscription(record);
  }

  if (record.closeTimer) {
    clearTimeout(record.closeTimer);
    record.closeTimer = null;
  }
  record.closeRequested = false;
  record.listeners.add(listener);
  replay(record, listener);

  let active = true;
  return () => {
    if (!active) {
      return;
    }
    active = false;
    record.listeners.delete(listener);

    if (!record.listeners.size) {
      record.closeTimer = setTimeout(() => {
        record.closeTimer = null;
        if (record.listeners.size) {
          return;
        }
        if (record.unsubscribe) {
          record.unsubscribe();
          record.unsubscribe = null;
          forget(record);
        } else if (record.starting) {
          record.closeRequested = true;
        } else {
          forget(record);
        }
      }, 1000);
    }
  };
}

export function callCard(conn, card, widget, event, value, confirmed = false) {
  const message = {
    type: "apollo_tab/card/call",
    card,
    widget,
    event,
    confirmed: Boolean(confirmed),
  };
  if (value !== undefined) {
    message.value = value;
  }
  return conn.sendMessagePromise(message);
}

// Converts a config that is not saved; resolves to {layout, warnings, values, sources}.
export function previewLayout(conn, config) {
  return conn.sendMessagePromise({ type: "apollo_tab/layout/preview", config });
}

// ---- tablets --------------------------------------------------------------

// One subscription to the tablet list per connection, shared by Home, the
// editor and the preview card: {listeners, tablets, seen, error, stop,
// closeTimer}. seen counts the lists that came. error is the failure the
// listeners were told about, until a list comes. A newcomer gets the last
// list at once.
const tabletWatches = new Map();

function tabletList(value) {
  return Array.isArray(value) ? value.filter((tablet) => tablet && typeof tablet.mac === "string") : [];
}

function tellTablets(watch) {
  for (const entry of [...watch.listeners]) {
    entry.listener(watch.tablets);
  }
}

function startTabletWatch(conn, watch) {
  watch.error = null;
  watch.stop = keepSubscribed(
    conn,
    "apollo_tab/tablets/subscribe",
    (event) => {
      if (event?.type !== "tablets") {
        return;
      }
      watch.tablets = tabletList(event.tablets);
      watch.seen += 1;
      watch.error = null;
      tellTablets(watch);
    },
    null,
    {
      onError: (error) => {
        watch.error = error;
        // The listeners show the failure now, not the last list.
        watch.tablets = null;
        for (const entry of [...watch.listeners]) {
          entry.onError?.(error);
        }
      },
    },
  );
}

// Calls listener with the whole tablet list, now if it is known and again
// on every change. The subscription is opened again by itself after the
// integration was reloaded or the connection came back. onError hears about
// a failure (see keepSubscribed); the list may still come later, and the
// failure is over then. Returns a function that stops listening.
export function onTabletsChanged(conn, listener, { onError = null } = {}) {
  let watch = tabletWatches.get(conn);
  if (!watch) {
    watch = { listeners: new Set(), tablets: null, seen: 0, error: null, stop: null, closeTimer: null };
    tabletWatches.set(conn, watch);
  }
  clearTimeout(watch.closeTimer);
  watch.closeTimer = null;
  const entry = { listener, onError };
  watch.listeners.add(entry);
  if (!watch.stop || watch.error) {
    // The first listener, or the first since a failure: that is tried
    // again at once, so a newcomer does not wait for the next try.
    watch.stop?.();
    startTabletWatch(conn, watch);
  } else if (watch.tablets) {
    listener(watch.tablets);
  }

  let active = true;
  return () => {
    if (!active) {
      return;
    }
    active = false;
    watch.listeners.delete(entry);
    if (watch.listeners.size) {
      return;
    }
    // Moving from Home to the editor drops one listener and adds another;
    // the subscription stays open for that moment.
    watch.closeTimer = setTimeout(() => {
      watch.closeTimer = null;
      if (watch.listeners.size) {
        return;
      }
      const stop = watch.stop;
      watch.stop = null;
      stop?.();
      if (tabletWatches.get(conn) === watch) {
        tabletWatches.delete(conn);
      }
    }, 1000);
  };
}

// Where the tablet list stands when a change is sent.
function tabletMark(conn) {
  const watch = tabletWatches.get(conn);
  return { watch, seen: watch?.seen };
}

// A change made here was answered with the tablet as it is now; everyone
// listening sees it before the next list arrives. A list that came since
// the change was sent is newer than the answer, also when both arrive
// together, so the answer is then not shown.
function applyTablet(conn, tablet, mark) {
  const watch = tabletWatches.get(conn);
  if (!watch?.tablets || watch !== mark.watch || watch.seen !== mark.seen) {
    return;
  }
  if (!tablet || typeof tablet.mac !== "string") {
    return;
  }
  const index = watch.tablets.findIndex((entry) => entry.mac === tablet.mac);
  if (index < 0) {
    return;
  }
  watch.tablets = watch.tablets.map((entry, at) => (at === index ? tablet : entry));
  tellTablets(watch);
}

export async function listTablets(conn) {
  const result = await conn.sendMessagePromise({ type: "apollo_tab/tablets" });
  return tabletList(result?.tablets);
}

// Shows the dashboard at urlPath on the tablet; resolves to the tablet.
// Only the panel's "Turn on with this dashboard" passes approve: Home
// Assistant refuses a new tablet without it, so no other control (a stale
// list, the editor's "Show this dashboard") can turn a tablet on by chance.
export async function assignTablet(conn, mac, urlPath, { approve = false } = {}) {
  const message = { type: "apollo_tab/tablet/assign", mac, url_path: urlPath };
  if (approve) {
    message.approve = true;
  }
  const mark = tabletMark(conn);
  const result = await conn.sendMessagePromise(message);
  const tablet = result?.tablet ?? null;
  applyTablet(conn, tablet, mark);
  return tablet;
}

// Asks Home Assistant to set the tablet up for taps again, now or within a
// minute; resolves to the tablet.
export async function pairTablet(conn, mac) {
  const mark = tabletMark(conn);
  const result = await conn.sendMessagePromise({ type: "apollo_tab/tablet/pair", mac });
  const tablet = result?.tablet ?? null;
  applyTablet(conn, tablet, mark);
  return tablet;
}
