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
function keepSubscribed(conn, type, onEvent, onRestored) {
  let active = true;
  let unsubscribe = null;
  let timer = null;
  let delay = 0;
  let attempt = 0;
  let lost = false;

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
        // Other failures, such as a user who is not an administrator, are final.
        if (active && current === attempt && error?.code === "not_loaded") {
          retry();
        }
      });
  };

  begin();

  return () => {
    active = false;
    attempt += 1;
    clearTimeout(timer);
    timer = null;
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
// subscription was reopened and the caller should load everything again.
export function onLayoutChanged(conn, onEvent, onRestored) {
  return keepSubscribed(conn, "apollo_tab/layout/subscribe", onEvent, onRestored);
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
