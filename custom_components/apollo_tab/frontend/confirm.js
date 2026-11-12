import { confirmStyles } from "./styles.js";

let openCount = 0;

// True while a question is on screen, so shortcuts behind it stay quiet.
export function confirmOpen() {
  return openCount > 0;
}

// Asks a yes or no question in a modal dialog and resolves to true for OK.
// The dialog sits in its own shadow root on document.body with its own
// styles, so it is themed the same on a dashboard and in the TAB-1 panel.
// danger marks an OK that cannot be undone with an icon as well as colour.
export function openConfirm({ title, text, okLabel, cancelLabel, danger = false }) {
  return new Promise((resolve) => {
    const host = document.createElement("div");
    const root = host.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = confirmStyles;

    const dialog = document.createElement("dialog");
    dialog.dataset.test = "confirm";
    dialog.setAttribute("aria-labelledby", "confirm-title");
    dialog.setAttribute("aria-describedby", "confirm-text");
    const heading = document.createElement("h2");
    heading.id = "confirm-title";
    heading.textContent = title;
    const body = document.createElement("p");
    body.id = "confirm-text";
    body.textContent = text;
    const actions = document.createElement("div");
    actions.className = "actions";

    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.dataset.test = "confirm-cancel";
    cancel.textContent = cancelLabel;

    const ok = document.createElement("button");
    ok.type = "button";
    ok.dataset.test = "confirm-ok";
    ok.className = danger ? "danger" : "primary";
    if (danger) {
      const mark = document.createElement("ha-icon");
      mark.setAttribute("aria-hidden", "true");
      mark.icon = "mdi:delete-outline";
      ok.append(mark);
    }
    const label = document.createElement("span");
    label.textContent = okLabel;
    ok.append(label);

    actions.append(cancel, ok);
    dialog.append(heading, body, actions);
    root.append(style, dialog);
    document.body.append(host);
    openCount += 1;

    let result = false;

    cancel.addEventListener("click", () => {
      result = false;
      dialog.close();
    });

    ok.addEventListener("click", () => {
      result = true;
      dialog.close();
    });

    dialog.addEventListener("cancel", () => {
      result = false;
    });

    dialog.addEventListener(
      "close",
      () => {
        host.remove();
        openCount -= 1;
        resolve(result);
      },
      { once: true },
    );

    dialog.showModal();
    cancel.focus();
  });
}
