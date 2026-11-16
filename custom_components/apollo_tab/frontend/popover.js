// One helper for every pop-up of the editor: the Tablets pop-up, the theme
// gallery, the menu and the page pop-up. Each is a <dialog> opened with
// showModal(), so focus stays inside and Escape closes it, placed under the
// control that opened it.
//
// The editor draws its bars again on every change, so the node that opened
// a pop-up may be gone by the time it is placed again or closes: the opener
// is found by its data-focus key each time.

import { el } from "./card-form.js";
import { placeBeside } from "./logic.js";

// The pop-up that is open in each shadow root; only one at a time.
const open = new WeakMap();

// Space kept between a pop-up and the edges of the editor's box.
const EDGE = 8;
// Space between a pop-up and its opener (as placeBeside keeps it).
const GAP = 4;

function textField(node) {
  if (!node) {
    return false;
  }
  if (node.tagName === "INPUT") {
    return !["checkbox", "radio", "range", "color", "button", "submit"].includes(node.type);
  }
  return node.tagName === "TEXTAREA" || node.isContentEditable;
}

function byKey(container, key) {
  return key ? [...container.querySelectorAll("[data-focus]")].find((node) => node.dataset.focus === key) || null : null;
}

// Whether a press may give focus to a text field when a pop-up opens: not
// on a touch screen, where it would bring the keyboard up unasked.
function touchScreen() {
  return typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;
}

// Opens a pop-up beside the control whose data-focus is anchorKey.
// build(container) draws the content. alive() is false once the thing the
// pop-up is about is gone. Returns { update(), close(), dialog }.
//
// root: the editor's shadow root. test: the dialog's data-test. label: its
// accessible name. sheet: drawn as a sheet from the bottom of the editor
// (compact and short). first: the data-focus key that takes focus when it
// opens; a text field gets its words selected, but not in a sheet or on a
// touch screen, where the pop-up's title takes focus instead. onClose runs
// once it has closed, for whatever reason. cover: a function that gives the
// box of a part of the editor; the pop-up then lies exactly over that part
// and leaves the rest in view (the theme gallery over the inspector in the
// short layout, so the picture shows each theme tried).
export function openPopover({ root, anchorKey, test, label, sheet = false, cover = null, build, alive = () => true, onClose, first = null }) {
  open.get(root)?.close({ refocus: false });

  const dialog = el("dialog", cover ? "popover cover" : sheet ? "popover sheet" : "popover");
  dialog.dataset.test = test;
  dialog.setAttribute("aria-label", label);
  const body = el("div", "pop-body");
  dialog.append(body);
  root.append(dialog);

  let closed = false;
  let refocus = true;
  const box = () => (root.querySelector(".root") || root.host).getBoundingClientRect();

  // Where the pop-up was put when it opened. Typing in it can move its
  // opener (a page's tab grows with its name), so a redraw keeps it there
  // and only pulls it back inside the editor; a resize places it afresh.
  let at = null;
  const place = ({ stay = false } = {}) => {
    if (closed) {
      return;
    }
    const bounds = box();
    const part = cover?.();
    if (part?.width) {
      dialog.style.left = `${Math.round(part.left)}px`;
      dialog.style.top = `${Math.round(part.top)}px`;
      dialog.style.width = `${Math.round(part.width)}px`;
      dialog.style.height = `${Math.round(part.height)}px`;
      dialog.style.maxHeight = "none";
      return;
    }
    if (sheet) {
      // The width and the bottom of the editor's shell, which follows the
      // visible part of the window, so the keyboard never covers it.
      dialog.style.left = `${Math.round(bounds.left)}px`;
      dialog.style.width = `${Math.round(bounds.width)}px`;
      dialog.style.maxHeight = `${Math.round(bounds.height * 0.8)}px`;
      dialog.style.top = `${Math.round(bounds.bottom - dialog.offsetHeight)}px`;
      return;
    }
    const anchor = byKey(root, anchorKey);
    const rect = anchor?.getClientRects().length ? anchor.getBoundingClientRect() : null;
    const inner = {
      left: bounds.left + EDGE,
      top: bounds.top + EDGE,
      right: bounds.right - EDGE,
      bottom: bounds.bottom - EDGE,
    };
    // A long list does not climb over its opener: the pop-up keeps to the
    // side of it with more room and scrolls inside.
    let room = inner.bottom - inner.top;
    if (rect) {
      room = Math.max(inner.bottom - rect.bottom - GAP, rect.top - GAP - inner.top);
    }
    dialog.style.maxHeight = `${Math.max(0, Math.round(room))}px`;
    const size = { width: dialog.offsetWidth, height: dialog.offsetHeight };
    if (stay && at) {
      const left = Math.max(inner.left, Math.min(at.left, inner.right - size.width));
      const top = Math.max(inner.top, Math.min(at.top, inner.bottom - size.height));
      dialog.style.left = `${Math.round(left)}px`;
      dialog.style.top = `${Math.round(top)}px`;
      return;
    }
    at = placeBeside(rect || { left: inner.left, top: inner.top, right: inner.left, bottom: inner.top }, size, inner, {
      rtl: getComputedStyle(root.host).direction === "rtl",
    });
    dialog.style.left = `${at.left}px`;
    dialog.style.top = `${at.top}px`;
  };

  const onResize = () => place();

  const draw = () => {
    // Focus inside is given back by data-focus, and a text field keeps
    // where its caret was, so typing goes on.
    const active = root.activeElement;
    const inside = active && dialog.contains(active);
    const key = inside ? active.dataset.focus || null : null;
    const caret = inside && textField(active) ? [active.selectionStart, active.selectionEnd] : null;
    body.replaceChildren();
    build(body);
    if (inside && !dialog.contains(root.activeElement)) {
      // A control that can go no further hands focus to its partner (Move
      // page later to Move page earlier).
      let target = byKey(body, key);
      if (target?.disabled && target.dataset.focusAlt) {
        target = byKey(body, target.dataset.focusAlt);
      }
      if (target && !target.disabled) {
        target.focus({ preventScroll: true });
        if (caret && textField(target) && caret[0] !== null) {
          target.setSelectionRange(caret[0], caret[1]);
        }
      } else {
        // The control is gone (Show here, once its tablet shows the
        // dashboard): focus waits on the pop-up's title.
        (body.querySelector(".pop-title") || dialog).focus({ preventScroll: true });
      }
    }
  };

  // The backdrop is the dialog itself: a press there is outside the box.
  const outside = (event) => {
    if (event.target !== dialog) {
      return false;
    }
    const rect = dialog.getBoundingClientRect();
    return event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom;
  };
  // A press outside closes the pop-up only when it also began outside: a
  // drag that starts in a text field and ends on the backdrop does not.
  let downOutside = false;
  const onDown = (event) => {
    downOutside = outside(event);
  };
  const onPress = (event) => {
    const began = downOutside;
    downOutside = false;
    if (began && outside(event)) {
      handle.close();
    }
  };

  const handle = {
    dialog,
    update() {
      if (closed) {
        return;
      }
      if (!alive()) {
        handle.close();
        return;
      }
      draw();
      place({ stay: true });
    },
    close({ refocus: give = true } = {}) {
      if (closed) {
        return;
      }
      refocus = give;
      if (dialog.open) {
        dialog.close();
      } else {
        finish();
      }
    },
  };

  const finish = () => {
    if (closed) {
      return;
    }
    closed = true;
    window.removeEventListener("resize", onResize);
    window.visualViewport?.removeEventListener("resize", onResize);
    dialog.remove();
    if (open.get(root) === handle) {
      open.delete(root);
    }
    // Focus goes back to the opener, wherever it is drawn now.
    if (refocus && root.host.isConnected) {
      byKey(root, anchorKey)?.focus({ preventScroll: true });
    }
    onClose?.();
  };

  dialog.tabIndex = -1;
  dialog.addEventListener("close", finish);
  dialog.addEventListener("pointerdown", onDown);
  dialog.addEventListener("click", onPress);
  window.addEventListener("resize", onResize, { passive: true });
  window.visualViewport?.addEventListener("resize", onResize, { passive: true });
  open.set(root, handle);

  build(body);
  dialog.showModal();
  place();

  // What takes focus: the named control, unless it is a text field and the
  // keyboard would come up unasked; then the title.
  const wanted = byKey(body, first);
  if (wanted && (!textField(wanted) || !(sheet || touchScreen()))) {
    wanted.focus({ preventScroll: true });
    if (textField(wanted)) {
      wanted.select();
    }
  } else if (textField(root.activeElement) || !dialog.contains(root.activeElement) || first) {
    (body.querySelector(".pop-title") || dialog).focus({ preventScroll: true });
  }
  return handle;
}

// The pop-up open in `root`, or null.
export function openPopoverIn(root) {
  return open.get(root) || null;
}
