export function openConfirm({ title, text, okLabel, cancelLabel }) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    const heading = document.createElement("h2");
    const body = document.createElement("p");
    const actions = document.createElement("div");
    const cancel = document.createElement("button");
    const ok = document.createElement("button");

    heading.textContent = title;
    body.textContent = text;
    cancel.type = "button";
    cancel.textContent = cancelLabel;
    ok.type = "button";
    ok.textContent = okLabel;

    actions.append(cancel, ok);
    dialog.append(heading, body, actions);
    document.body.append(dialog);

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
        dialog.remove();
        resolve(result);
      },
      { once: true },
    );

    dialog.showModal();
    cancel.focus();
  });
}
