// Pointer handling for moving and sizing cards on the tablet picture. A
// press still selects: a drag starts only after the pointer moved 6 px, or
// on touch after a hold of 350 ms. Works on real pointer events only; it
// makes no event of its own and presses no control from code.

export const START_PX = 6;
export const HOLD_MS = 350;

// Follows one press on `target`. handlers: start() -> false to give up,
// move(dx, dy, event) with the distance in screen pixels since the press,
// end(event) on release after a drag, cancel() when it ends any other way.
// Returns a function that cancels the drag from outside (Escape).
export function followPress(target, event, handlers) {
  if (event.button !== 0 || !event.isPrimary) {
    return null;
  }
  const touch = event.pointerType === "touch";
  const id = event.pointerId;
  const x0 = event.clientX;
  const y0 = event.clientY;
  let armed = false;
  let held = !touch;
  let done = false;
  let timer = null;

  const stop = () => {
    done = true;
    clearTimeout(timer);
    target.removeEventListener("pointermove", onMove);
    target.removeEventListener("pointerup", onUp);
    target.removeEventListener("pointercancel", onCancel);
    target.removeEventListener("lostpointercapture", onCancel);
    target.removeEventListener("touchmove", onTouchMove);
    if (target.hasPointerCapture?.(id)) {
      target.releasePointerCapture(id);
    }
  };
  const arm = () => {
    if (handlers.start() === false) {
      stop();
      return false;
    }
    armed = true;
    return true;
  };
  function onMove(moveEvent) {
    if (moveEvent.pointerId !== id || done) {
      return;
    }
    const dx = moveEvent.clientX - x0;
    const dy = moveEvent.clientY - y0;
    if (!armed) {
      if (Math.hypot(dx, dy) < START_PX) {
        return;
      }
      // A touch that moves before the hold is a scroll, not a drag.
      if (!held) {
        stop();
        return;
      }
      if (!arm()) {
        return;
      }
    }
    moveEvent.preventDefault();
    handlers.move(dx, dy, moveEvent);
  }
  function onUp(upEvent) {
    if (upEvent.pointerId !== id || done) {
      return;
    }
    const wasArmed = armed;
    stop();
    if (wasArmed) {
      // The click that follows the release is not a press on the card.
      // It comes straight after, so the listener goes after one turn.
      const swallow = (clickEvent) => {
        clickEvent.stopImmediatePropagation();
        clickEvent.preventDefault();
      };
      // The drop is handled after it, while the card is still there to
      // take it (the drop draws the picture again).
      target.addEventListener("click", swallow, { capture: true, once: true });
      setTimeout(() => {
        target.removeEventListener("click", swallow, { capture: true });
        handlers.end(upEvent);
      }, 0);
    }
  }
  function onCancel(cancelEvent) {
    if ((cancelEvent.pointerId !== undefined && cancelEvent.pointerId !== id) || done) {
      return;
    }
    const wasArmed = armed;
    stop();
    if (wasArmed) {
      handlers.cancel();
    }
  }
  // Once a touch drag is under way the page does not scroll under it.
  function onTouchMove(touchEvent) {
    if (armed) {
      touchEvent.preventDefault();
    }
  }

  target.setPointerCapture?.(id);
  target.addEventListener("pointermove", onMove);
  target.addEventListener("pointerup", onUp);
  target.addEventListener("pointercancel", onCancel);
  target.addEventListener("lostpointercapture", onCancel);
  target.addEventListener("touchmove", onTouchMove, { passive: false });
  if (touch) {
    timer = setTimeout(() => {
      held = true;
    }, HOLD_MS);
  }
  return () => {
    if (done) {
      return;
    }
    const wasArmed = armed;
    stop();
    if (wasArmed) {
      handlers.cancel();
    }
  };
}
