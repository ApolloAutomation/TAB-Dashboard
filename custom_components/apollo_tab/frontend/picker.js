import { t } from "./api.js";
import { buildParamField, el, formFields, icon, makeButton, uid } from "./card-form.js";
import {
  CARD_TYPE,
  EXAMPLE_OPTIONS,
  EXAMPLE_TITLES,
  deviceMatches,
  exampleVariant,
  fitsDevices,
  isAllowed,
  offeredCards,
  paramsComplete,
  pickerFields,
  pickerGroups,
  pickerVariants,
  presetParams,
  singleEntityParam,
  suggestedCards,
} from "./model.js";

// How far ahead of the visible area example cards are created, in pixels.
const PREVIEW_MARGIN = 200;
// Room kept around an example inside its frame, in pixels.
const FRAME_ROOM = 24;

// Words a search finds a card by besides its name, description and search
// words: its group ("Music and TV") and what its form asks ("Which speaker
// or TV?").
function searchText(component, group) {
  const questions = formFields(component)
    .filter((field) => field.kind === "entity")
    .map((field) => field.label);
  return [t(`group.${group}`), ...questions].join(" ");
}

// The grid size a card is drawn at: its named size, else its own.
function cardGrid(component, variantId) {
  const variant = pickerVariants(component).find((entry) => entry.id === variantId);
  if (variant) {
    return { columns: variant.grid[0], rows: variant.grid[1] };
  }
  return {
    columns: Number(component.grid?.columns) || 6,
    rows: Number(component.grid?.rows) || 3,
  };
}

// The card's size in tablet pixels.
function cardPixels(grid) {
  return { width: grid.columns * 32 - 8, height: grid.rows * 64 - 8 };
}

// The words of the size chip on a tile: the named size it draws, or its
// size in units.
function sizeChip(component, variantId) {
  const sizes = component.schema === 2 ? pickerVariants(component) : [];
  const shown = sizes.find((variant) => variant.id === variantId) || sizes[0];
  if (shown) {
    return String(shown.name || shown.id);
  }
  const size = Array.isArray(component.size) ? component.size : [1, 1];
  return t("picker.size_chip", { w: size[0], h: size[1] });
}

// The words that list every size of a card, for the tile's title.
function sizeText(component) {
  const sizes = component.schema === 2 ? pickerVariants(component) : [];
  if (sizes.length > 1) {
    return t("picker.sizes", { sizes: sizes.map((variant) => String(variant.name || variant.id)).join(", ") });
  }
  const size = Array.isArray(component.size) ? component.size : [1, 1];
  return t("picker.size", { w: size[0], h: size[1] });
}

// A card drawn as an example inside `box`, which gets the card's size at
// `scale`. `params` are the devices chosen so far, if any.
function drawExample(box, component, { variantId, scale, themeId, hass, watchers, params = {} }) {
  const card = document.createElement("apollo-tab-card");
  const title = EXAMPLE_TITLES[component.id];
  try {
    card.setConfig({
      type: CARD_TYPE,
      component: component.id,
      params,
      ...(variantId ? { variant: variantId } : {}),
      ...(title && !Object.keys(params).length ? { title } : {}),
      ...(EXAMPLE_OPTIONS[component.id] && !variantId ? { options: { ...EXAMPLE_OPTIONS[component.id] } } : {}),
      style: { theme: themeId },
    });
  } catch {
    return;
  }
  const pixels = cardPixels(cardGrid(component, variantId));
  box.style.width = `${pixels.width * scale}px`;
  box.style.height = `${pixels.height * scale}px`;
  card.hass = hass;
  box.replaceChildren(card);
  // The card keeps 56 px for itself on a dashboard; an example of a
  // card one row high is smaller than that and would be cut off.
  card.style.minHeight = "0";
  watchForError(card, box, component, watchers);
}

// The largest scale up to `most` at which the card fits in `frame` with
// FRAME_ROOM around it.
function fitScale(frame, component, variantId, most) {
  const pixels = cardPixels(cardGrid(component, variantId));
  const width = frame.clientWidth - FRAME_ROOM;
  const height = frame.clientHeight - FRAME_ROOM;
  if (!(width > 0) || !(height > 0)) {
    return most;
  }
  return Math.min(most, width / pixels.width, height / pixels.height);
}

// The 16:10 frame of a tile with the card's icon, and its example once the
// frame comes into view.
function previewFrame(component, themeId, hass, observer, watchers) {
  const frame = el("div", "tile-frame");
  const box = el("div", "tile-preview");
  box.inert = true;
  box.setAttribute("aria-hidden", "true");
  box.append(icon(component.icon));
  frame.append(box);
  const variantId = exampleVariant(component);
  frame.append(el("span", "tile-chip", sizeChip(component, variantId)));

  if (isAllowed(component) && observer) {
    box.__showCard = () => {
      const scale = fitScale(frame, component, variantId, 0.5);
      drawExample(box, component, { variantId, scale, themeId, hass, watchers });
    };
    observer.observe(box);
  }
  return frame;
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
    // The foot of the picker says the pictures are examples.
    root.querySelector(".example-chip")?.remove();
    const status = root.querySelector(".status");
    if (status && status.textContent !== t("card.loading")) {
      watcher.disconnect();
      watchers.delete(watcher);
      card.remove();
      box.style.width = "";
      box.style.height = "";
      box.replaceChildren(icon(component.icon));
    }
  };
  const watcher = new MutationObserver(check);
  watcher.observe(root, { childList: true, subtree: true, characterData: true });
  watchers.add(watcher);
}

// Arrow keys move between the buttons of `group` and choose the one they
// reach (its `__choose`), so the group is one Tab stop.
function arrowKeys(group, selector) {
  group.addEventListener("keydown", (event) => {
    const keys = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1, Home: "first", End: "last" };
    const move = keys[event.key];
    if (move === undefined) {
      return;
    }
    const buttons = [...group.querySelectorAll(selector)];
    const at = buttons.indexOf(event.target.closest(selector));
    if (at === -1) {
      return;
    }
    event.preventDefault();
    const rtl = getComputedStyle(group).direction === "rtl";
    const step = typeof move === "number" && rtl && event.key.startsWith("Arrow") && /Left|Right/.test(event.key) ? -move : move;
    let next = at;
    if (step === "first") {
      next = 0;
    } else if (step === "last") {
      next = buttons.length - 1;
    } else {
      next = (at + step + buttons.length) % buttons.length;
    }
    buttons[next].focus();
    buttons[next].__choose?.();
  });
}

// Opens the picker inside `root` (the designer's shadow root). Resolves to
// {component, params, variant} when a card is chosen, or null when the
// dialog is closed. `devices` ({entities, name}) names what a removed card
// controlled: the picker then starts with the cards that can control it,
// and a chosen card gets as many of those devices as it has room for (see
// presetParams).
export function openCardPicker({ root, hass, library, config, themeId, compact = false, devices = null }) {
  return new Promise((resolve) => {
    const dialog = el("dialog", compact ? "picker compact" : "picker");
    dialog.dataset.test = "picker";
    const titleId = uid("picker-title");
    dialog.setAttribute("aria-labelledby", titleId);
    const entities = Array.isArray(devices?.entities) ? devices.entities : [];
    // Only when some card the picker offers fits; otherwise every card is
    // offered. An older card never counts, as it is never shown.
    let fitOnly = offeredCards(library).some((component) => fitsDevices(component, entities));
    let query = "";
    // What the rail shows: "suggested", "all", a group id or "folder".
    let view = "all";
    let result = null;
    let observer = null;
    let step = "cards";
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

    const closeButton = () => {
      const close = makeButton(null, {
        className: "picker-close icon",
        test: "picker-close",
        ariaLabel: t("picker.close"),
        onClick: () => finish(null),
      });
      close.title = t("picker.close");
      close.append(icon("mdi:close"));
      return close;
    };

    const title = (text) => {
      const heading = el("h2", null, text);
      heading.id = titleId;
      return heading;
    };

    // The cards the picker offers now: those that fit the removed card's
    // devices, or every card.
    const offeredNow = () => {
      const all = Array.isArray(library?.components) ? library.components : [];
      return fitOnly ? { ...library, components: all.filter((component) => fitsDevices(component, entities)) } : library;
    };

    const showCards = () => {
      step = "cards";
      stopPreviews();
      dialog.replaceChildren();

      const head = el("div", "picker-head");
      const searchField = el("label", "picker-search");
      searchField.append(icon("mdi:magnify"));
      const search = document.createElement("input");
      search.type = "search";
      search.value = query;
      search.autocomplete = "off";
      search.placeholder = t("picker.search");
      search.setAttribute("aria-label", t("picker.search"));
      search.dataset.test = "picker-search";
      // Room for the magnifier; the field's own rules set its padding.
      search.style.paddingInlineStart = "38px";
      searchField.append(search);
      head.append(
        title(fitOnly ? t("picker.title_for", { device: devices.name }) : t("picker.title")),
        searchField,
        closeButton(),
      );
      dialog.append(head);

      if (fitOnly) {
        // A card for one device takes only one of several; the designer then
        // offers a card for the devices left over.
        const top = el("div", "picker-top");
        const intro = entities.length > 1 ? "picker.intro_for_many" : "picker.intro_for";
        top.append(
          el("p", null, t(intro, { device: devices.name })),
          makeButton(t("picker.show_all"), {
            className: "link",
            test: "picker-show-all",
            onClick: () => {
              fitOnly = false;
              view = "all";
              showCards();
              // The button is gone; on a phone focus goes to the first card
              // rather than the search field, which would open the keyboard.
              if (compact) {
                dialog.querySelector('[data-test="tile"]:not(:disabled)')?.focus();
              }
            },
          }),
        );
        dialog.append(top);
      }

      const main = el("div", "picker-main");
      const rail = el("div", "picker-rail");
      rail.dataset.test = "picker-rail";
      rail.setAttribute("role", "radiogroup");
      rail.setAttribute("aria-label", t("picker.groups"));
      const body = el("div", "picker-body");
      const status = el("p", "sr-only");
      status.setAttribute("aria-live", "polite");
      status.dataset.test = "picker-status";
      main.append(rail, body);
      const foot = el("div", "picker-note");
      foot.append(el("p", "small", t("picker.example_note")));
      dialog.append(main, foot, status);
      arrowKeys(rail, '[data-test="picker-rail-row"]');

      const drawRail = () => {
        const groups = pickerGroups(offeredNow());
        const total = groups.reduce((sum, group) => sum + group.cards.length, 0);
        const folder = groups.flatMap((group) => group.cards).filter((component) => component.source === "user");
        const suggested = fitOnly ? [] : suggestedCards(offeredNow(), hass);
        const rows = [];
        if (suggested.length) {
          rows.push(["suggested", t("picker.suggested"), suggested.length]);
        }
        rows.push(["all", t("picker.all"), total]);
        for (const group of groups) {
          rows.push([group.id, t(`group.${group.id}`), group.cards.length]);
        }
        if (folder.length) {
          rows.push(["folder", t("picker.from_folder"), folder.length]);
        }
        if (!rows.some(([id]) => id === view)) {
          view = "all";
        }
        rail.replaceChildren();
        const searching = Boolean(query.trim());
        for (const [id, label, count] of rows) {
          const row = makeButton(null, { className: "rail-row", test: "picker-rail-row" });
          row.dataset.view = id;
          row.setAttribute("role", "radio");
          const on = !searching && id === view;
          row.setAttribute("aria-checked", String(on));
          row.tabIndex = id === view ? 0 : -1;
          row.append(el("span", "rail-name", label), el("span", "rail-count", String(count)));
          row.__choose = () => {
            if (view === id && !query.trim()) {
              return;
            }
            view = id;
            if (query) {
              query = "";
              search.value = "";
            }
            fill();
            rail.querySelector(`[data-view="${id}"]`)?.focus();
          };
          row.addEventListener("click", row.__choose);
          rail.append(row);
        }
      };

      const section = (heading, cards, extra = null) => {
        const block = el("section", "picker-group");
        const tiles = el("div", "tiles");
        tiles.setAttribute("role", "group");
        if (heading) {
          const headingId = uid("group");
          heading.id = headingId;
          tiles.setAttribute("aria-labelledby", headingId);
          block.append(heading);
        } else {
          tiles.setAttribute("aria-label", t("picker.title"));
        }
        for (const component of cards) {
          tiles.append(tile(component, extra));
        }
        block.append(tiles);
        return block;
      };

      const groupHeading = (id) => {
        const heading = el("h3", null, t(`group.${id}`));
        heading.dataset.test = "picker-group";
        heading.dataset.group = id;
        return heading;
      };

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

        drawRail();
        body.replaceChildren();
        body.scrollTop = 0;
        const offered = offeredNow();
        const words = query.trim();

        if (words) {
          // With words typed: the cards as one grid, then the devices the
          // words name with the cards that can take each.
          const cards = pickerGroups(offered, query, searchText).flatMap((group) => group.cards);
          const usable = offeredCards(library).filter(isAllowed);
          const found = deviceMatches(hass, query, (id) => usable.some((component) => fitsDevices(component, [id])));
          if (cards.length) {
            body.append(section(null, cards));
          }
          for (const device of found) {
            const heading = el("h3", null, t("picker.cards_for", { device: device.name }));
            heading.dataset.test = "picker-device";
            heading.dataset.entity = device.entity_id;
            const block = section(heading, usable.filter((component) => fitsDevices(component, [device.entity_id])), device.entity_id);
            block.classList.add("picker-device-block");
            body.append(block);
          }
          const count = cards.length + found.length;
          status.textContent = count ? t("picker.found", { count: cards.length }) : t("picker.found_none");
          if (!count) {
            const none = el("div", "picker-none");
            none.dataset.test = "picker-none";
            none.append(
              el("p", null, t("picker.none", { query: words })),
              el("p", "small", t("picker.none_help")),
              makeButton(t("picker.show_all"), {
                test: "picker-clear-search",
                onClick: () => {
                  query = "";
                  fitOnly = false;
                  view = "all";
                  showCards();
                  if (compact) {
                    dialog.querySelector('[data-test="tile"]:not(:disabled)')?.focus();
                  }
                },
              }),
            );
            body.append(none);
          }
          return;
        }

        status.textContent = "";
        const groups = pickerGroups(offered);
        if (view === "suggested") {
          const heading = el("h3", null, t("picker.suggested"));
          heading.dataset.test = "picker-suggested";
          body.append(section(heading, suggestedCards(offered, hass)));
        } else if (view === "folder") {
          const heading = el("h3", null, t("picker.from_folder"));
          body.append(section(heading, groups.flatMap((group) => group.cards).filter((component) => component.source === "user")));
        } else {
          for (const group of groups) {
            if (view === "all" || view === group.id) {
              body.append(section(groupHeading(group.id), group.cards));
            }
          }
        }
      };

      // `entityId`: the device a block of the search is for; the card gets it.
      const tile = (component, entityId = null) => {
        const allowed = isAllowed(component);
        const button = makeButton(null, { className: "tile", test: "tile" });
        button.dataset.component = component.id;
        if (entityId) {
          button.dataset.entity = entityId;
        }
        button.disabled = !allowed;
        button.title = sizeText(component);
        button.append(previewFrame(component, themeId, hass, allowed ? observer : null, watchers));
        const text = el("span", "tile-text");
        text.append(el("span", "tile-name", component.name));
        if (component.description) {
          text.append(el("span", "tile-desc", component.description));
        }
        if (component.source === "user") {
          text.append(el("span", "tag", t("picker.from_folder")));
        }
        if (!allowed) {
          const locked = el("span", "tile-locked");
          locked.append(icon("mdi:lock-outline"), el("span", null, t("picker.locked")));
          text.append(locked);
        }
        button.append(text);
        button.addEventListener("click", () => {
          if (allowed) {
            chooseDevice(component, entityId ? [entityId] : entities);
          }
        });
        return button;
      };

      // Escape closes the picker, also while the search holds words (a
      // search field would only clear them).
      search.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          finish(null);
        }
      });
      search.addEventListener("input", () => {
        query = search.value;
        fill();
      });
      fill();
      if (!compact) {
        search.focus();
      }
    };

    // `preset`: devices chosen already (a removed card's, or the device a
    // search named). A card for just one of them then needs no device step.
    const chooseDevice = (component, preset) => {
      const fields = formFields(component);
      if (!fields.length) {
        finish({ component, params: {} });
        return;
      }
      const params = presetParams(component, preset);
      const single = singleEntityParam(component);
      if (single && params[single]) {
        finish({ component, params });
        return;
      }
      step = "device";
      stopPreviews();

      const sizes = component.schema === 2 ? pickerVariants(component) : [];
      let variant = null;
      const shownVariant = () => variant || exampleVariant(component);
      const done = () => finish({ component, params: { ...params }, ...(variant ? { variant } : {}) });

      const back = makeButton(null, {
        test: "pick-back",
        ariaLabel: t("pick.back"),
        onClick: showCards,
      });
      back.append(icon("mdi:arrow-left"), el("span", null, t("pick.back")));

      dialog.replaceChildren();
      const head = el("div", "picker-head");
      head.append(back, title(t("pick.title", { card: component.name })), closeButton());
      dialog.append(head);

      const split = el("div", "pick-split");
      const side = el("div", "pick-card");
      const frame = el("div", "pick-frame");
      const picture = el("div", "tablet-pic");
      picture.inert = true;
      picture.setAttribute("aria-hidden", "true");
      frame.append(picture);
      side.append(frame, el("p", "tile-name", component.name));
      if (component.description) {
        side.append(el("p", "tile-desc", component.description));
      }
      const draw = () => {
        stopPreviews();
        const id = shownVariant();
        const scale = fitScale(frame, component, id, 1);
        drawExample(picture, component, {
          variantId: id,
          scale,
          themeId,
          hass,
          watchers,
          params: Object.fromEntries(Object.entries(params).filter(([, value]) => value !== undefined)),
        });
      };
      // A card with more than one size: its sizes as chips.
      if (sizes.length > 1) {
        const row = el("div", "pick-sizes");
        row.setAttribute("role", "radiogroup");
        const labelId = uid("size");
        const label = el("p", "field-label", t("pick.size"));
        label.id = labelId;
        row.setAttribute("aria-labelledby", labelId);
        const current = shownVariant() || sizes[0].id;
        for (const entry of sizes) {
          const chip = makeButton(String(entry.name || entry.id), { className: "size-pick", test: "tile-size" });
          chip.dataset.variant = entry.id;
          chip.setAttribute("role", "radio");
          chip.setAttribute("aria-checked", String(entry.id === current));
          chip.tabIndex = entry.id === current ? 0 : -1;
          chip.__choose = () => {
            variant = entry.id;
            for (const other of row.children) {
              const on = other === chip;
              other.setAttribute("aria-checked", String(on));
              other.tabIndex = on ? 0 : -1;
            }
            draw();
          };
          chip.addEventListener("click", chip.__choose);
          row.append(chip);
        }
        arrowKeys(row, '[data-test="tile-size"]');
        side.append(label, row);
      }

      const body = el("div", "picker-body");
      const list = el("div", "picker-fields");
      body.append(list);
      split.append(side, body);
      const foot = el("div", "picker-foot");
      foot.append(
        makeButton(t("pick.skip"), {
          kind: "text",
          test: "pick-skip",
          onClick: done,
        }),
        el("p", "helper", t("pick.skip_hint")),
      );
      let add = null;
      if (!single) {
        add = makeButton(t("pick.add"), {
          className: "primary",
          test: "pick-add",
          disabled: !paramsComplete(component, params),
          onClick: done,
        });
        foot.append(add);
      }

      // A one-press card asks for its one device only; the rest have
      // defaults and wait in the card's form.
      const asked = new Set(pickerFields(component).map((field) => field.name));
      for (const field of fields.filter((entry) => asked.has(entry.name))) {
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
                done();
                return;
              }
              add.disabled = !paramsComplete(component, params);
              draw();
            },
          }),
        );
      }
      dialog.append(split, foot);
      draw();
      // On a phone the on-screen keyboard would cover the list, so the
      // search field waits to be pressed, as in the first step. Focus stays
      // in the dialog on Back rather than falling to the page.
      if (!compact) {
        dialog.querySelector('[data-test="entity-search"]')?.focus();
      } else {
        back.focus({ preventScroll: true });
      }
    };

    // Escape in the device step goes back to the cards, with the search
    // kept; in the cards it closes the picker.
    dialog.addEventListener("cancel", (event) => {
      if (step === "device") {
        event.preventDefault();
        showCards();
      }
    });

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
