import { format, subscriptionKey } from "./logic.js";

let stringsCache = null;
let stringsPromise = null;
let libraryCache = null;
let libraryPromise = null;

const cardSubscriptions = new Map();
// A failed or ended subscription is tried again after 2 s, 4 s, 8 s ... up to 30 s.
const RETRY_FIRST_MS = 2000;
const RETRY_MAX_MS = 30000;

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

// Subscribes to library or layout events and keeps the subscription alive.
// The server ends it with a not_loaded event when the integration is unloaded
// or reloaded; it is then opened again after 2 s, 4 s, 8 s ... up to 30 s.
// onRestored runs after each such reopening, because changes made in between
// were not reported.
//
// After a lost connection (a laptop asleep, a Wi-Fi drop, a browser tab
// Home Assistant disconnected while hidden), Home Assistant's connection
// opens its subscriptions again by itself and fires "ready", without the
// events from the time in between. With afterReconnect, onRestored runs
// then too.
//
// A subscribe that fails for another reason, such as a user who is not an
// administrator, is not tried again; onError hears about it.
function keepSubscribed(conn, type, onEvent, onRestored, { afterReconnect = false, onError = null } = {}) {
  let active = true;
  let unsubscribe = null;
  let timer = null;
  let delay = 0;
  let attempt = 0;
  let lost = false;

  // A subscription being opened again after not_loaded runs onRestored
  // itself once it is open.
  const reconnected = () => {
    if (active && !lost) {
      onRestored?.();
    }
  };
  const watchConnection = afterReconnect && typeof conn.addEventListener === "function";
  if (watchConnection) {
    conn.addEventListener("ready", reconnected);
  }

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
        if (lost) {
          lost = false;
          onRestored?.();
        }
      })
      .catch((error) => {
        if (!active || current !== attempt) {
          return;
        }
        // Other failures, such as a user who is not an administrator, are final.
        if (error?.code === "not_loaded") {
          retry();
        } else {
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
    if (watchConnection) {
      conn.removeEventListener?.("ready", reconnected);
    }
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
// subscription was reopened or the connection came back, and the caller
// should load everything again.
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
      values: {},
      errors: {},
      lastMain: null,
      lastValues: null,
    };
    cardSubscriptions.set(key, record);
    beginSubscription(record);
  } else if (record.failed && !record.starting) {
    // A failed subscription is tried again at once for a newcomer, which
    // should not first see the old error.
    record.conn = conn;
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
// editor and the preview card: {listeners, tablets, error, stop, closeTimer}.
// A newcomer gets the last list at once.
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
      tellTablets(watch);
    },
    null,
    {
      onError: (error) => {
        watch.error = error;
        const stop = watch.stop;
        watch.stop = null;
        stop?.();
        for (const entry of [...watch.listeners]) {
          entry.onError?.(error);
        }
      },
    },
  );
}

// Calls listener with the whole tablet list, now if it is known and again
// on every change. The subscription is opened again by itself after the
// integration was reloaded; onError hears about a final failure. Returns a
// function that stops listening.
export function onTabletsChanged(conn, listener, { onError = null } = {}) {
  let watch = tabletWatches.get(conn);
  if (!watch) {
    watch = { listeners: new Set(), tablets: null, error: null, stop: null, closeTimer: null };
    tabletWatches.set(conn, watch);
  }
  clearTimeout(watch.closeTimer);
  watch.closeTimer = null;
  const entry = { listener, onError };
  watch.listeners.add(entry);
  if (!watch.stop) {
    // The first listener, or the first since a final failure.
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

// A change made here was answered with the tablet as it is now; everyone
// listening sees it before the next list arrives.
function applyTablet(conn, tablet) {
  const watch = tabletWatches.get(conn);
  if (!watch?.tablets || !tablet || typeof tablet.mac !== "string") {
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
  const result = await conn.sendMessagePromise(message);
  const tablet = result?.tablet ?? null;
  applyTablet(conn, tablet);
  return tablet;
}

// Asks Home Assistant to set the tablet up for taps again, now or within a
// minute; resolves to the tablet.
export async function pairTablet(conn, mac) {
  const result = await conn.sendMessagePromise({ type: "apollo_tab/tablet/pair", mac });
  const tablet = result?.tablet ?? null;
  applyTablet(conn, tablet);
  return tablet;
}
