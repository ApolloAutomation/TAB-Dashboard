import { t } from "./api.js";
import { buildParamField, el, formFields, icon, makeButton, uid } from "./card-form.js";
import {
  CARD_TYPE,
  fitsDevices,
  isAllowed,
  paramsComplete,
  pickerGroups,
  presetParams,
  singleEntityParam,
} from "./model.js";

// How far ahead of the visible area example cards are created, in pixels.
const PREVIEW_MARGIN = 200;

// Words a search finds a card by besides its name and description: its
// group ("Music and TV") and what its form asks ("Which speaker or TV?").
function searchText(component, group) {
  const questions = formFields(component)
    .filter((field) => field.kind === "entity")
    .map((field) => field.label);
  return [t(`group.${group}`), ...questions].join(" ");
}

function previewBox(component, scale, themeId, hass, observer, watchers) {
  const columns = Number(component.grid?.columns) || 6;
  const rows = Number(component.grid?.rows) || 3;
  const box = el("div", "tile-preview");
  box.style.width = `${(columns * 32 - 8) * scale}px`;
  box.style.height = `${(rows * 64 - 8) * scale}px`;
  box.inert = true;
  box.setAttribute("aria-hidden", "true");
  box.append(icon(component.icon));

  if (isAllowed(component) && observer) {
    box.__showCard = () => {
      const card = document.createElement("apollo-tab-card");
      try {
        card.setConfig({
          type: CARD_TYPE,
          component: component.id,
          params: {},
          style: { theme: themeId },
        });
      } catch {
        return;
      }
      card.hass = hass;
      box.append(card);
      watchForError(card, box, component, watchers);
    };
    observer.observe(box);
  }
  return box;
}

// A card that cannot be drawn shows a message; the tile shows the card's
// icon instead, which says more at this size. Each watcher is kept in
// `watchers` so the picker can stop them all when its tiles go away.
function watchForError(card, box, component, watchers) {
  const root = card.shadowRoot;
  if (!root) {
    return;
  }
  const check = () => {
    const status = root.querySelector(".status");
    if (status && status.textContent !== t("card.loading")) {
      watcher.disconnect();
      watchers.delete(watcher);
      card.remove();
      box.replaceChildren(icon(component.icon));
    }
  };
  const watcher = new MutationObserver(check);
  watcher.observe(root, { childList: true, subtree: true, characterData: true });
  watchers.add(watcher);
}

// Opens the picker inside `root` (the designer's shadow root). Resolves to
// {component, params} when a card is chosen, or null when the dialog is closed.
// `devices` ({entities, name}) names what a removed card controlled: the
// picker then starts with the cards that can control it, and a chosen card
// gets as many of those devices as it has room for (see presetParams).
export function openCardPicker({ root, hass, library, config, themeId, compact = false, devices = null }) {
  return new Promise((resolve) => {
    const dialog = el("dialog", compact ? "picker compact" : "picker");
    dialog.dataset.test = "picker";
    const titleId = uid("picker-title");
    dialog.setAttribute("aria-labelledby", titleId);
    const scale = compact ? 0.4 : 0.5;
    const entities = Array.isArray(devices?.entities) ? devices.entities : [];
    const all = Array.isArray(library?.components) ? library.components : [];
    // Only when some card fits; otherwise every card is offered.
    let fitOnly = all.some((component) => fitsDevices(component, entities));
    let query = "";
    let result = null;
    let observer = null;
    const watchers = new Set();

    // Runs when the tiles are drawn again, replaced by the device step, or
    // the picker closes.
    const stopPreviews = () => {
      observer?.disconnect();
      observer = null;
      for (const watcher of watchers) {
        watcher.disconnect();
      }
      watchers.clear();
    };

    const finish = (value) => {
      result = value;
      dialog.close();
    };

    const header = (titleText, back) => {
      const head = el("div", "picker-head");
      if (back) {
        head.append(back);
      }
      const title = el("h2", null, titleText);
      title.id = titleId;
      head.append(
        title,
        makeButton(null, {
          className: "picker-close",
          test: "picker-close",
          ariaLabel: t("picker.close"),
          onClick: () => finish(null),
        }),
      );
      head.lastChild.append(icon("mdi:close"), el("span", null, t("picker.close")));
      return head;
    };

    const showCards = () => {
      stopPreviews();
      dialog.replaceChildren();
      dialog.append(header(fitOnly ? t("picker.title_for", { device: devices.name }) : t("picker.title")));

      const top = el("div", "picker-top");
      if (fitOnly) {
        // A card for one device takes only one of several; the designer then
        // offers a card for the devices left over.
        const intro = entities.length > 1 ? "picker.intro_for_many" : "picker.intro_for";
        top.append(
          el("p", null, t(intro, { device: devices.name })),
          makeButton(t("picker.show_all"), {
            className: "link",
            test: "picker-show-all",
            onClick: () => {
              fitOnly = false;
              showCards();
              // The button is gone; on a phone focus goes to the first card
              // rather than the search field, which would open the keyboard.
              if (compact) {
                dialog.querySelector('[data-test="tile"]:not(:disabled)')?.focus();
              }
            },
          }),
        );
      } else {
        top.append(el("p", null, t("picker.intro")));
      }
      const searchField = el("label", "field");
      const search = document.createElement("input");
      search.type = "search";
      search.value = query;
      search.autocomplete = "off";
      search.dataset.test = "picker-search";
      if (!compact) {
        search.autofocus = true;
      }
      searchField.append(el("span", "field-label", t("picker.search")), search);
      top.append(searchField, el("p", "small", t("picker.example_note")));

      const body = el("div", "picker-body");
      dialog.append(top, body);

      const fill = () => {
        stopPreviews();
        observer = new IntersectionObserver(
          (entries) => {
            for (const entry of entries) {
              if (entry.isIntersecting) {
                observer?.unobserve(entry.target);
                entry.target.__showCard?.();
              }
            }
          },
          { root: body, rootMargin: `${PREVIEW_MARGIN}px` },
        );

        body.replaceChildren();
        const offered = fitOnly
          ? { ...library, components: all.filter((component) => fitsDevices(component, entities)) }
          : library;
        const groups = pickerGroups(offered, query, searchText);
        if (!groups.length) {
          const none = el("div", "picker-none");
          none.dataset.test = "picker-none";
          none.append(
            el("p", null, t("picker.none", { query: query.trim() })),
            el("p", "small", t("picker.none_help")),
            makeButton(t("picker.show_all"), {
              test: "picker-clear-search",
              onClick: () => {
                query = "";
                fitOnly = false;
                showCards();
                if (compact) {
                  dialog.querySelector('[data-test="tile"]:not(:disabled)')?.focus();
                }
              },
            }),
          );
          body.append(none);
          return;
        }
        for (const group of groups) {
          const section = el("section", "picker-group");
          const headingId = uid("group");
          const heading = el("h3", null, t(`group.${group.id}`));
          heading.id = headingId;
          heading.dataset.test = "picker-group";
          heading.dataset.group = group.id;
          const tiles = el("div", "tiles");
          tiles.setAttribute("role", "group");
          tiles.setAttribute("aria-labelledby", headingId);
          for (const component of group.cards) {
            tiles.append(tile(component));
          }
          section.append(heading, tiles);
          body.append(section);
        }
      };

      const tile = (component) => {
        const allowed = isAllowed(component);
        const button = makeButton(null, { className: "tile", test: "tile" });
        button.dataset.component = component.id;
        button.disabled = !allowed;
        button.append(previewBox(component, scale, themeId, hass, allowed ? observer : null, watchers));
        button.append(el("span", "tile-name", component.name));
        if (component.description) {
          button.append(el("span", "tile-desc", component.description));
        }
        const size = Array.isArray(component.size) ? component.size : [1, 1];
        button.append(el("span", "tile-size", t("picker.size", { w: size[0], h: size[1] })));
        if (component.source === "user") {
          button.append(el("span", "tag", t("picker.from_folder")));
        }
        if (!allowed) {
          const locked = el("span", "tile-locked");
          locked.append(icon("mdi:lock-outline"), el("span", null, t("picker.locked")));
          button.append(locked);
        }
        button.addEventListener("click", () => {
          if (allowed) {
            chooseDevice(component);
          }
        });
        return button;
      };

      search.addEventListener("input", () => {
        query = search.value;
        fill();
      });
      fill();
      if (!compact) {
        search.focus();
      }
    };

    const chooseDevice = (component) => {
      const fields = formFields(component);
      if (!fields.length) {
        finish({ component, params: {} });
        return;
      }
      // The devices of a removed card are chosen already; a card for just
      // one device then needs no device step.
      const params = presetParams(component, entities);
      const single = singleEntityParam(component);
      if (single && params[single]) {
        finish({ component, params });
        return;
      }
      stopPreviews();

      const back = makeButton(null, {
        test: "pick-back",
        ariaLabel: t("pick.back"),
        onClick: showCards,
      });
      back.append(icon("mdi:arrow-left"), el("span", null, t("pick.back")));

      dialog.replaceChildren();
      dialog.append(header(t("pick.title", { card: component.name }), back));

      const body = el("div", "picker-body");
      const list = el("div", "picker-fields");
      body.append(list);
      const foot = el("div", "picker-foot");
      let add = null;
      if (!single) {
        add = makeButton(t("pick.add"), {
          className: "primary",
          test: "pick-add",
          disabled: !paramsComplete(component, params),
          onClick: () => finish({ component, params: { ...params } }),
        });
        foot.append(add);
      }
      foot.append(
        makeButton(t("pick.skip"), {
          test: "pick-skip",
          onClick: () => finish({ component, params: { ...params } }),
        }),
        el("p", "helper", t("pick.skip_hint")),
      );

      for (const field of fields) {
        list.append(
          buildParamField({
            hass,
            field,
            value: params[field.name],
            config,
            compact,
            collapsed: false,
            onChange: (value) => {
              if (value === undefined) {
                delete params[field.name];
              } else {
                params[field.name] = value;
              }
              if (single) {
                finish({ component, params: { ...params } });
                return;
              }
              add.disabled = !paramsComplete(component, params);
            },
          }),
        );
      }
      dialog.append(body, foot);
      // On a phone the on-screen keyboard would cover the list, so the
      // search field waits to be pressed, as in the first step. Focus stays
      // in the dialog on Back rather than falling to the page.
      if (!compact) {
        dialog.querySelector('[data-test="entity-search"]')?.focus();
      } else {
        back.focus({ preventScroll: true });
      }
    };

    dialog.addEventListener(
      "close",
      () => {
        stopPreviews();
        dialog.remove();
        resolve(result);
      },
      { once: true },
    );

    root.append(dialog);
    showCards();
    dialog.showModal();
    if (!compact) {
      dialog.querySelector('[data-test="picker-search"]')?.focus();
    }
  });
}
