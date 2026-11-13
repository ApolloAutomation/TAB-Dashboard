import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as model from "../../custom_components/apollo_tab/frontend/model.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const realDashboard = JSON.parse(
  fs.readFileSync(path.resolve(here, "../harness/real-dashboard.json"), "utf8"),
);

const clone = (value) => structuredClone(value);

const settle = async () => {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
  }
};

const component = ({
  id,
  tag = `apollo-tab-el-${id.replace("/", "-")}`,
  name = id,
  description = `${name} description`,
  icon = "mdi:view-dashboard",
  version = 1,
  size = [1, 1],
  grid = { columns: 6, rows: 3 },
  source = "builtin",
  sensitive = false,
  approved = true,
  params = {},
}) => ({
  id,
  tag,
  name,
  description,
  icon,
  version,
  size,
  grid,
  source,
  sensitive,
  approved,
  params,
});

const components = [
  component({
    id: "apollo/light-tile",
    tag: "apollo-tab-el-apollo-light-tile",
    name: "Light tile",
    description: "Control a light",
    icon: "mdi:lightbulb",
    size: [1, 1],
    grid: { columns: 6, rows: 3 },
    params: {
      entity: {
        kind: "entity",
        domain: "light",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/thermostat",
    name: "Thermostat",
    description: "Control room climate",
    icon: "mdi:thermostat",
    size: [2, 2],
    grid: { columns: 12, rows: 6 },
    params: {
      entity: {
        kind: "entity",
        domain: "climate",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/scene-row",
    name: "Scene row",
    description: "Run several scenes",
    icon: "mdi:palette",
    size: [2, 1],
    grid: { columns: 12, rows: 3 },
    params: {
      scenes: {
        kind: "entity",
        domain: "scene",
        multiple: true,
      },
    },
  }),
  component({
    id: "community/room-summary",
    name: "Room summary",
    description: "Show room lights and sensors",
    icon: "mdi:sofa",
    size: [2, 1],
    grid: { columns: 12, rows: 3 },
    source: "builtin",
    params: {
      temperature_sensor: {
        kind: "entity",
        domain: "sensor",
        multiple: false,
      },
      humidity_sensor: {
        kind: "entity",
        domain: "sensor",
        multiple: false,
      },
      lights: {
        kind: "entity",
        domain: "light",
        multiple: true,
      },
      page: {
        kind: "page",
      },
    },
  }),
  component({
    id: "apollo/lock",
    name: "Lock",
    description: "Control a lock",
    icon: "mdi:lock",
    size: [1, 1],
    grid: { columns: 6, rows: 3 },
    source: "builtin",
    sensitive: true,
    approved: true,
    params: {
      entity: {
        kind: "entity",
        domain: "lock",
        multiple: false,
      },
    },
  }),
  component({
    id: "me/door-lock",
    tag: "apollo-tab-el-me-door-lock",
    name: "Door lock",
    description: "Control the front door lock",
    icon: "mdi:lock",
    size: [1, 1],
    grid: { columns: 6, rows: 3 },
    source: "user",
    sensitive: true,
    approved: false,
    params: {
      entity: {
        kind: "entity",
        domain: "lock",
        multiple: false,
      },
    },
  }),
];

const library = { components, themes: [], errors: [] };

const themes = [
  {
    id: "midnight",
    name: "Midnight",
    card: "#181C23",
    card2: "#232833",
    acc: "#F5B547",
  },
  {
    id: "daylight",
    name: "Daylight",
    card: "#FFFFFF",
    card2: "#EEF1F5",
    acc: "#0277BD",
  },
];

const bundledLibrary = [
  component({
    id: "apollo/alarm-panel",
    params: {
      entity: {
        kind: "entity",
        domain: "alarm_control_panel",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/blinds",
    params: {
      entity: {
        kind: "entity",
        domain: "cover",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/camera-snapshot",
    params: {
      entity: {
        kind: "entity",
        domain: "camera",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/fan",
    params: {
      entity: {
        kind: "entity",
        domain: "fan",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/light-slider",
    params: {
      entity: {
        kind: "entity",
        domain: "light",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/light-tile",
    params: {
      entity: {
        kind: "entity",
        domain: "light",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/lock",
    params: {
      entity: {
        kind: "entity",
        domain: "lock",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/media-player",
    params: {
      entity: {
        kind: "entity",
        domain: "media_player",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/scene-row",
    params: {
      scenes: {
        kind: "entity",
        domain: "scene",
        multiple: true,
      },
    },
  }),
  component({
    id: "apollo/sensor-graph",
    params: {
      entity: {
        kind: "entity",
        domain: "sensor",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/sensor-value",
    params: {
      entity: {
        kind: "entity",
        domain: "sensor",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/thermostat",
    params: {
      entity: {
        kind: "entity",
        domain: "climate",
        multiple: false,
      },
    },
  }),
  component({
    id: "apollo/weather",
    params: {
      entity: {
        kind: "entity",
        domain: "weather",
        multiple: false,
      },
    },
  }),
  component({
    id: "community/energy-gauge",
    source: "builtin",
    params: {
      entity: {
        kind: "entity",
        domain: "sensor",
        multiple: false,
      },
      max: {
        kind: "number",
        default: 5000,
      },
    },
  }),
  component({
    id: "community/presence-chips",
    source: "builtin",
    params: {
      people: {
        kind: "entity",
        domain: "person",
        multiple: true,
      },
    },
  }),
  component({
    id: "community/room-summary",
    source: "builtin",
    params: {
      temperature_sensor: {
        kind: "entity",
        domain: "sensor",
        multiple: false,
      },
      humidity_sensor: {
        kind: "entity",
        domain: "sensor",
        multiple: false,
      },
      lights: {
        kind: "entity",
        domain: "light",
        multiple: true,
      },
      page: {
        kind: "page",
      },
    },
  }),
];

const realDashboardPreview = {
  layout: {
    v: 1,
    screen: [1280, 800],
    theme: {},
    nav: [
      {
        page: "home",
        title: "Home",
        icon: "mdi:home",
      },
    ],
    pages: [
      {
        id: "home",
        title: "Home",
        view: 0,
        icon: "mdi:home",
        w: [
          {
            id: 1,
            t: "heading",
            r: [100, 20, 1164, 56],
            text: "Home",
          },
        ],
      },
    ],
    hash: "x",
  },
  warnings: [
    {
      code: "not_tab_element",
      view: 0,
      section: 0,
      card: 1,
      page: null,
      r: null,
      detail: "custom:bubble-card",
    },
  ],
  values: {},
  sources: {
    "1": [0, 0, 0],
  },
};

const makeTimers = () => {
  let nextId = 1;
  const callbacks = new Map();

  return {
    callbacks,
    setTimer(callback) {
      const id = nextId;
      nextId += 1;
      callbacks.set(id, callback);
      return id;
    },
    clearTimer(id) {
      callbacks.delete(id);
    },
    fire() {
      const entries = [...callbacks.entries()];
      callbacks.clear();
      for (const [, callback] of entries) {
        callback();
      }
    },
  };
};

test("newDashboardConfig makes one empty full-width page called Home", () => {
  assert.deepStrictEqual(model.newDashboardConfig(), {
    apollo_tab: {
      version: 1,
      theme: "midnight",
    },
    views: [
      {
        type: "sections",
        title: "Home",
        path: "home",
        icon: "mdi:home",
        max_columns: 3,
        sections: [
          {
            type: "grid",
            column_span: 3,
            cards: [],
          },
        ],
      },
    ],
  });
});

test("newPage gives a unique path made from the title", () => {
  assert.deepStrictEqual(model.newPage("Living Room", ["living-room"]), {
    type: "sections",
    title: "Living Room",
    path: "living-room-2",
    icon: "mdi:view-dashboard",
    max_columns: 3,
    sections: [
      {
        type: "grid",
        column_span: 3,
        cards: [],
      },
    ],
  });
});

test("slugPath handles empty, long and taken titles", () => {
  assert.equal(model.slugPath("!!!", []), "page");
  assert.equal(
    model.slugPath("ABCDEFGHIJKLMNOPQRSTUVWXYZ 1234567890 extra", []),
    "abcdefghijklmnopqrstuvwxyz-12345",
  );
  assert.equal(
    model.slugPath("ABCDEFGHIJKLMNOPQRSTUVWXYZ 1234567890 extra", [
      "abcdefghijklmnopqrstuvwxyz-12345",
    ]),
    "abcdefghijklmnopqrstuvwxyz-123-2",
  );
  assert.ok(/^[a-z0-9_-]{1,32}$/.test(model.slugPath("A _ page", [])));
});

test("nextDashboardPath skips taken paths", () => {
  assert.equal(
    model.nextDashboardPath(["tab-1", "tab-1-2"]),
    "tab-1-3",
  );
  assert.equal(model.nextDashboardPath([]), "tab-1");
});

test("nextDashboardTitle numbers repeated names", () => {
  assert.equal(model.nextDashboardTitle([], "Tablet"), "Tablet");
  assert.equal(
    model.nextDashboardTitle(["Tablet", "Tablet 2"], "Tablet"),
    "Tablet 3",
  );
});

test("mergeDashboards takes title, id and sidebar state from Home Assistant's list", () => {
  const tabs = [
    {
      url_path: "tablet",
      title: "Tablet fallback",
      mode: "storage",
      pages: 3,
    },
  ];
  const dashboards = [
    {
      url_path: "tablet",
      title: "Tablet",
      id: "dashboard-tablet",
      show_in_sidebar: true,
    },
  ];

  const configs = { tablet: model.newDashboardConfig("Home") };

  assert.deepStrictEqual(model.mergeDashboards(tabs, dashboards, configs), [
    {
      url_path: "tablet",
      title: "Tablet",
      id: "dashboard-tablet",
      mode: "storage",
      show_in_sidebar: true,
      pages: 1,
      editable: true,
    },
  ]);
});

// Design 4.2: one order everywhere, (title in lower case, url_path), as
// Home Assistant's side sorts them in Python.
test("dashboards have one order: title in lower case, then url_path", () => {
  const tabs = [
    { url_path: "zeta", title: "zeta", mode: "storage" },
    { url_path: "home-2", title: "Home", mode: "storage" },
    { url_path: "attic", title: "Attic", mode: "storage" },
    { url_path: "home", title: "home", mode: "storage" },
    { url_path: "bedroom", title: "Bedroom", mode: "storage" },
  ];
  const expected = ["attic", "bedroom", "home", "home-2", "zeta"];
  assert.deepStrictEqual(model.mergeDashboards(tabs, []).map((row) => row.url_path), expected);
  assert.deepStrictEqual(model.sortDashboards(tabs).map((row) => row.url_path), expected);
  // Titles from Home Assistant's own list decide, not the stand-in titles.
  const renamed = model.mergeDashboards(tabs, [{ url_path: "zeta", title: "Alpha", id: "z" }]);
  assert.equal(renamed[0].url_path, "zeta");
  // Not the browser's language order: "Z" before "a" in lower case is "a"
  // before "z", and characters past U+FFFF sort after every other one, as
  // Python compares code points.
  assert.ok(model.compareCodePoints("\u{1F600}", "�") > 0);
  assert.ok("\u{1F600}" < "�", "JavaScript's own < puts it first, which Python does not");
  assert.equal(model.compareCodePoints("abc", "abc"), 0);
  assert.ok(model.compareCodePoints("ab", "abc") < 0);
  assert.ok(model.compareCodePoints("abc", "ab") > 0);
  assert.equal(model.compareDashboards({ title: "Home", url_path: "a" }, { title: "HOME", url_path: "a" }), 0);
  assert.ok(model.compareDashboards({ title: "Home", url_path: "b" }, { title: "home", url_path: "a" }) > 0);
  // A list that is not a list sorts to nothing, and the input is not changed.
  assert.deepStrictEqual(model.sortDashboards(null), []);
  assert.equal(tabs[0].url_path, "zeta");
});

test("mergeDashboards counts the editor's pages, not the tablet's screens", () => {
  // apollo_tab/dashboards reports screens: none for an empty page, several
  // for a page split across screens.
  const tabs = [
    { url_path: "tab-1", title: "New", mode: "storage", pages: 0 },
    { url_path: "tab-2", title: "Real", mode: "storage", pages: 1 },
    { url_path: "tab-3", title: "Long", mode: "storage", pages: 3 },
    { url_path: "tab-4", title: "Unreadable", mode: "storage", pages: 2 },
  ];
  const long = model.newDashboardConfig("Home");
  long.views[0].sections[0].cards = Array.from({ length: 40 }, () => ({
    type: model.CARD_TYPE,
    component: "apollo/light-tile",
  }));
  const twoPages = model.addPage(model.newDashboardConfig("Home"), "Bedroom").config;
  const configs = {
    "tab-1": model.newDashboardConfig("Home"),
    "tab-2": clone(realDashboard),
    "tab-3": long,
    extra: twoPages,
  };

  const rows = model.mergeDashboards(tabs, [], configs);

  // In the one order: Long, New, Real, Unreadable.
  assert.deepStrictEqual(
    rows.map((row) => [row.url_path, row.pages]),
    [
      ["tab-3", 1],
      ["tab-1", 1],
      // "Home" and the old "Tablet preview" page: the editor shows a tab for
      // each, and the row says separately that the tablet leaves one out.
      ["tab-2", 2],
      ["tab-4", null],
    ],
  );
  assert.equal(rows[2].pages, model.pageList(configs["tab-2"]).length);
  assert.equal(model.mergeDashboards([{ url_path: "extra", mode: "storage" }], [], configs)[0].pages, 2);
  assert.ok(model.mergeDashboards(tabs, []).every((row) => row.pages === null));
});

test("mergeDashboards marks YAML dashboards as not editable", () => {
  const tabs = [
    {
      url_path: "wall",
      title: "Wall",
      mode: "yaml",
      pages: 2,
    },
  ];
  const dashboards = [
    {
      url_path: "wall",
      title: "Wall panel",
      id: "wall-id",
      show_in_sidebar: false,
    },
  ];

  assert.equal(model.mergeDashboards(tabs, dashboards)[0].editable, false);
});

test("pageKind tells pages, the old preview page and other views apart", () => {
  assert.equal(
    model.pageKind({
      type: "sections",
      sections: [],
    }),
    "page",
  );
  assert.equal(
    model.pageKind({
      type: "sections",
      strategy: {},
      sections: [],
    }),
    "other",
  );
  assert.equal(
    model.pageKind({
      type: "panel",
      cards: [
        {
          type: model.PREVIEW_TYPE,
        },
      ],
    }),
    "old_preview",
  );
  assert.equal(model.pageKind({ type: "panel", cards: [] }), "other");
});

test("pageList reads titles, icons and kinds", () => {
  const config = {
    views: [
      {
        type: "sections",
        title: "Home",
        path: "home",
        icon: "mdi:home",
        sections: [],
      },
      {
        type: "panel",
        path: "preview",
        icon: "bad icon",
        cards: [
          {
            type: model.PREVIEW_TYPE,
          },
        ],
      },
      {
        type: "masonry",
        path: "legacy",
      },
    ],
  };

  assert.deepStrictEqual(model.pageList(config), [
    {
      view: 0,
      title: "Home",
      icon: "mdi:home",
      kind: "page",
    },
    {
      view: 1,
      title: "preview",
      kind: "old_preview",
    },
    {
      view: 2,
      title: "legacy",
      kind: "other",
    },
  ]);
});

test("cardKind recognises TAB cards, alias types, headings and other cards", () => {
  assert.equal(
    model.cardKind(
      {
        type: model.CARD_TYPE,
        component: "apollo/light-tile",
      },
      library,
    ),
    "tab",
  );
  assert.equal(
    model.cardKind(
      {
        type: "custom:apollo-tab-el-apollo-light-tile",
      },
      library,
    ),
    "tab",
  );
  assert.equal(model.cardKind({ type: "heading" }, library), "heading");
  assert.equal(
    model.cardKind({ type: model.PREVIEW_TYPE }, library),
    "old_preview",
  );
  assert.equal(model.cardKind({ type: "entities" }, library), "other");
  assert.equal(model.cardKind(null, library), "other");
});

test("cardKind reports a TAB card whose component is missing", () => {
  assert.equal(
    model.cardKind(
      {
        type: model.CARD_TYPE,
        component: "missing/card",
      },
      library,
    ),
    "tab_missing",
  );
  assert.equal(
    model.cardKind(
      {
        type: "custom:apollo-tab-el-missing-card",
      },
      library,
    ),
    "tab_missing",
  );
});

test("isAllowed blocks only unapproved lock and alarm cards from the user folder", () => {
  const unapprovedAlarm = component({
    id: "me/alarm",
    source: "user",
    sensitive: true,
    approved: false,
    params: {
      entity: {
        kind: "entity",
        domain: "alarm_control_panel",
        multiple: false,
      },
    },
  });
  const ordinaryUserCard = component({
    id: "me/weather",
    source: "user",
    sensitive: false,
    approved: false,
  });

  assert.equal(model.isAllowed(components[4]), true);
  assert.equal(model.isAllowed(components[5]), false);
  assert.equal(model.isAllowed(unapprovedAlarm), false);
  assert.equal(model.isAllowed(ordinaryUserCard), true);
});

test("addPage appends a page and returns its index", () => {
  const result = model.addPage(
    model.newDashboardConfig(),
    "Living Room",
    "mdi:sofa",
  );

  assert.equal(result.view, 1);
  assert.deepStrictEqual(result.config.views[1], {
    type: "sections",
    title: "Living Room",
    path: "living-room",
    icon: "mdi:sofa",
    max_columns: 3,
    sections: [
      {
        type: "grid",
        column_span: 3,
        cards: [],
      },
    ],
  });
});

test("renamePage keeps the path", () => {
  const input = model.newDashboardConfig();
  const output = model.renamePage(input, 0, "Main Floor");

  assert.equal(output.views[0].title, "Main Floor");
  assert.equal(output.views[0].path, "home");
});

test("setPageIcon ignores values that are not mdi icons", () => {
  const input = model.newDashboardConfig();
  const invalid = model.setPageIcon(input, 0, "home");
  const valid = model.setPageIcon(input, 0, "mdi:sofa-outline");

  assert.deepStrictEqual(invalid, input);
  assert.equal(valid.views[0].icon, "mdi:sofa-outline");
});

test("movePage swaps neighbours and stops at the edges", () => {
  let config = model.addPage(
    model.newDashboardConfig(),
    "Second",
    "mdi:numeric-2",
  ).config;
  config = model.addPage(config, "Third", "mdi:numeric-3").config;

  const moved = model.movePage(config, 1, 1);
  assert.equal(moved.view, 2);
  assert.deepStrictEqual(
    moved.config.views.map((view) => view.title),
    ["Home", "Third", "Second"],
  );

  const stopped = model.movePage(config, 0, -1);
  assert.equal(stopped.view, 0);
  assert.deepStrictEqual(stopped.config, config);
});

test("removePage never removes the last page", () => {
  const onePage = model.newDashboardConfig();
  assert.deepStrictEqual(model.removePage(onePage, 0), {
    config: onePage,
    view: 0,
  });

  const twoPages = model.addPage(onePage, "Second", "mdi:numeric-2").config;
  const removed = model.removePage(twoPages, 0);
  assert.equal(removed.view, 0);
  assert.deepStrictEqual(
    removed.config.views.map((view) => view.title),
    ["Second"],
  );
});

test("addCard appends to the last grid section with the component's size", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections = [
    {
      type: "grid",
      cards: [],
    },
    {
      type: "grid",
      column_span: 2,
      cards: [
        {
          type: "heading",
          heading: "Existing",
        },
      ],
    },
  ];

  const result = model.addCard(config, 0, components[1], {
    entity: "climate.downstairs",
  });

  assert.deepStrictEqual(result.source, [0, 1, 1]);
  assert.deepStrictEqual(result.config.views[0].sections[1].cards[1], {
    type: model.CARD_TYPE,
    component: "apollo/thermostat",
    params: {
      entity: "climate.downstairs",
    },
    grid_options: {
      columns: 12,
      rows: 6,
    },
  });
});

test("addCard clamps the width to a narrow section", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections = [
    {
      type: "grid",
      cards: [],
    },
  ];

  const thermostat = model.addCard(config, 0, components[1], {});
  assert.equal(
    thermostat.config.views[0].sections[0].cards[0].grid_options.columns,
    12,
  );

  const wide = component({
    id: "test/wide",
    size: [4, 1],
    grid: {
      columns: 24,
      rows: 3,
    },
  });
  const result = model.addCard(config, 0, wide, {});
  assert.equal(
    result.config.views[0].sections[0].cards[0].grid_options.columns,
    12,
  );
});

test("addCard creates a full-width section when the page has none", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections = [
    {
      type: "custom:other-section",
    },
  ];

  const result = model.addCard(config, 0, components[0], {});

  assert.deepStrictEqual(result.source, [0, 1, 0]);
  assert.deepStrictEqual(result.config.views[0].sections[1], {
    type: "grid",
    column_span: 3,
    cards: [
      {
        type: model.CARD_TYPE,
        component: "apollo/light-tile",
        grid_options: {
          columns: 6,
          rows: 3,
        },
      },
    ],
  });
});

test("addCard refuses pages the tablet cannot show", () => {
  const config = {
    views: [
      {
        type: "masonry",
        title: "Legacy",
        cards: [],
      },
    ],
  };

  const result = model.addCard(config, 0, components[0], {});
  assert.deepStrictEqual(result, {
    config,
    source: null,
  });
});

test("updateCard merges changes, cleans empty values and keeps other keys", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections[0].cards.push({
    type: model.CARD_TYPE,
    component: "apollo/light-tile",
    params: {
      entity: "light.old",
      remove: "yes",
    },
    title: "Old",
    style: {
      use_color: true,
      remove: true,
    },
    grid_options: {
      columns: 6,
      rows: 3,
      visibility: "always",
    },
    custom: "kept",
  });

  const output = model.updateCard(config, [0, 0, 0], {
    params: {
      entity: "light.new",
      remove: undefined,
    },
    title: "",
    style: {
      use_color: undefined,
      remove: undefined,
    },
    grid_options: {
      columns: 12,
    },
  });

  assert.deepStrictEqual(output.views[0].sections[0].cards[0], {
    type: model.CARD_TYPE,
    component: "apollo/light-tile",
    params: {
      entity: "light.new",
    },
    grid_options: {
      columns: 12,
    },
    custom: "kept",
  });
});

test("cardSize reads grid options in units and flags unusual sizes", () => {
  assert.deepStrictEqual(
    model.cardSize(
      {
        grid_options: {
          columns: 12,
          rows: 6,
        },
      },
      components[0],
    ),
    {
      w: 2,
      h: 2,
      exact: true,
    },
  );
  assert.deepStrictEqual(
    model.cardSize(
      {
        grid_options: {
          columns: 9,
          rows: 3,
        },
      },
      components[0],
    ),
    {
      w: 2,
      h: 1,
      exact: false,
    },
  );
  assert.deepStrictEqual(
    model.cardSize(realDashboard.views[0].sections[0].cards[1], null),
    {
      w: 1,
      h: 1,
      exact: true,
    },
  );
  assert.deepStrictEqual(
    model.cardSize(
      {
        grid_options: {
          columns: "full",
          rows: 3,
        },
      },
      components[0],
    ),
    {
      w: 6,
      h: 1,
      exact: false,
    },
  );
});

test("resizeCard writes whole units and clamps to the section and the screen", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections[0].column_span = 2;
  config.views[0].sections[0].cards.push({
    type: model.CARD_TYPE,
    component: "apollo/light-tile",
    grid_options: {
      columns: 6,
      rows: 3,
      custom: true,
    },
  });

  const output = model.resizeCard(config, [0, 0, 0], 9.4, 7.8);

  assert.deepStrictEqual(output.views[0].sections[0].cards[0].grid_options, {
    columns: 24,
    rows: 12,
    custom: true,
  });
});

test("moveItem reorders inside a section", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections[0].cards = [
    { type: "heading", heading: "One" },
    { type: "heading", heading: "Two" },
    { type: "heading", heading: "Three" },
  ];

  const result = model.moveItem(config, [0, 0, 1], -1);

  assert.deepStrictEqual(result.source, [0, 0, 0]);
  assert.deepStrictEqual(
    result.config.views[0].sections[0].cards.map((card) => card.heading),
    ["Two", "One", "Three"],
  );
});

test("moveItem crosses into the neighbouring section at an edge", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections = [
    {
      type: "grid",
      cards: [
        {
          type: "heading",
          heading: "First",
        },
      ],
    },
    {
      type: "grid",
      cards: [
        {
          type: "heading",
          heading: "Second",
        },
        {
          type: "heading",
          heading: "Third",
        },
      ],
    },
  ];

  const earlier = model.moveItem(config, [0, 1, 0], -1);
  assert.deepStrictEqual(earlier.source, [0, 0, 1]);
  assert.deepStrictEqual(
    earlier.config.views[0].sections[0].cards.map((card) => card.heading),
    ["First", "Second"],
  );

  const later = model.moveItem(config, [0, 0, 0], 1);
  assert.deepStrictEqual(later.source, [0, 1, 0]);
  assert.deepStrictEqual(
    later.config.views[0].sections[1].cards.map((card) => card.heading),
    ["First", "Second", "Third"],
  );
});

test("canMove is false at the first and last position", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections[0].cards = [
    { type: "heading", heading: "One" },
    { type: "heading", heading: "Two" },
  ];

  assert.equal(model.canMove(config, [0, 0, 0], -1), false);
  assert.equal(model.canMove(config, [0, 0, 0], 1), true);
  assert.equal(model.canMove(config, [0, 0, 1], 1), false);
  assert.equal(model.canMove(config, [0, 0, 1], -1), true);
});

test("moveCardToPage moves a card with everything it holds to the end of another page", () => {
  const config = model.newDashboardConfig();
  const dial = {
    type: "custom:apollo-tab-card",
    component: "apollo/thermostat",
    name: "Hall",
    params: { entity: "climate.hall" },
    grid_options: { columns: 12, rows: 6 },
  };
  config.views[0].sections[0].cards = [{ type: "heading", heading: "Keep" }, dial];
  config.views.push({
    type: "sections",
    title: "Climate",
    path: "climate",
    sections: [
      { type: "grid", column_span: 3, cards: [{ type: "heading", heading: "Here" }] },
      { type: "grid", column_span: 1, cards: [] },
    ],
  });
  const before = structuredClone(config);

  const result = model.moveCardToPage(config, [0, 0, 1], 1);

  assert.deepStrictEqual(config, before);
  assert.equal(result.view, 1);
  // It goes into the page's last grid.
  assert.deepStrictEqual(result.source, [1, 1, 0]);
  assert.deepStrictEqual(result.config.views[0].sections[0].cards, [{ type: "heading", heading: "Keep" }]);
  assert.deepStrictEqual(result.config.views[1].sections[1].cards, [dial]);
  // That grid is one column wide, so a wider card is made to fit it.
  const narrow = structuredClone(config);
  narrow.views[0].sections[0].cards[1].grid_options = { columns: 24, rows: 6 };
  assert.deepStrictEqual(
    model.moveCardToPage(narrow, [0, 0, 1], 1).config.views[1].sections[1].cards[0].grid_options,
    { columns: 12, rows: 6 },
  );
});

test("moveCardToPage can add a page for the card and leaves the page it is on alone", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections[0].cards = [{ type: "heading", heading: "One" }];

  const result = model.moveCardToPage(config, [0, 0, 0], "new", "Page 2");
  assert.equal(result.view, 1);
  assert.deepStrictEqual(result.source, [1, 0, 0]);
  assert.equal(result.config.views[1].title, "Page 2");
  assert.equal(result.config.views[1].path, "page-2");
  assert.deepStrictEqual(result.config.views[0].sections[0].cards, []);
  assert.deepStrictEqual(result.config.views[1].sections[0].cards, [{ type: "heading", heading: "One" }]);

  // The page the card is already on, a section title, a card that is not
  // there and a page that is not a TAB-1 page move nothing.
  assert.equal(model.moveCardToPage(config, [0, 0, 0], 0).source, null);
  assert.equal(model.moveCardToPage(config, [0, 0, null], "new", "Page 2").source, null);
  assert.equal(model.moveCardToPage(config, [0, 0, 5], "new", "Page 2").source, null);
  const withOld = structuredClone(config);
  withOld.views.push({ title: "Old", path: "old", cards: [] });
  const old = model.moveCardToPage(withOld, [0, 0, 0], 1);
  assert.equal(old.source, null);
  assert.deepStrictEqual(old.config, withOld);
});

test("removeItem removes a card and a section title", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections[0].title = "Room";
  config.views[0].sections[0].cards = [
    { type: "heading", heading: "One" },
    { type: "heading", heading: "Two" },
  ];

  const withoutCard = model.removeItem(config, [0, 0, 0]);
  assert.deepStrictEqual(
    withoutCard.views[0].sections[0].cards.map((card) => card.heading),
    ["Two"],
  );

  const withoutTitle = model.removeItem(config, [0, 0, null]);
  assert.equal("title" in withoutTitle.views[0].sections[0], false);
});

test("setHeadingText edits heading cards and section titles", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections[0].title = "Room";
  config.views[0].sections[0].cards = [
    {
      type: "heading",
      heading: "Old heading",
    },
  ];

  const cardOutput = model.setHeadingText(
    config,
    [0, 0, 0],
    "New heading",
  );
  assert.equal(
    cardOutput.views[0].sections[0].cards[0].heading,
    "New heading",
  );

  const longText = "x".repeat(100);
  const titleOutput = model.setHeadingText(
    config,
    [0, 0, null],
    longText,
  );
  assert.equal(titleOutput.views[0].sections[0].title, "x".repeat(80));

  const emptyOutput = model.setHeadingText(config, [0, 0, null], "");
  assert.equal("title" in emptyOutput.views[0].sections[0], false);
});

test("setTheme writes apollo_tab and keeps the version", () => {
  const config = {
    apollo_tab: {
      version: 7,
      extra: true,
    },
    views: [],
  };

  assert.deepStrictEqual(model.setTheme(config, "daylight").apollo_tab, {
    version: 1,
    extra: true,
    theme: "daylight",
  });
});

test("usesWholeScreen is true only for one untitled full-width section", () => {
  const config = model.newDashboardConfig();
  assert.equal(model.usesWholeScreen(config, 0), true);

  const titled = clone(config);
  titled.views[0].sections[0].title = "Room";
  assert.equal(model.usesWholeScreen(titled, 0), false);

  const narrow = clone(config);
  narrow.views[0].sections[0].column_span = 2;
  assert.equal(model.usesWholeScreen(narrow, 0), false);

  const multiple = clone(config);
  multiple.views[0].sections.push({
    type: "grid",
    column_span: 3,
    cards: [],
  });
  assert.equal(model.usesWholeScreen(multiple, 0), false);
});

test("useWholeScreen merges sections in order and turns titles into headings", () => {
  const config = model.newDashboardConfig();
  config.views[0].max_columns = 2;
  config.views[0].sections = [
    {
      type: "grid",
      title: "First",
      cards: [
        {
          type: "heading",
          heading: "A",
        },
      ],
    },
    {
      strategy: {
        type: "test",
      },
    },
    {
      title: "Second",
      cards: [
        {
          type: "heading",
          heading: "B",
        },
      ],
    },
  ];

  const output = model.useWholeScreen(config, 0);

  assert.equal(output.views[0].max_columns, 3);
  assert.deepStrictEqual(output.views[0].sections, [
    {
      type: "grid",
      column_span: 3,
      cards: [
        {
          type: "heading",
          heading: "First",
        },
        {
          type: "heading",
          heading: "A",
        },
        {
          type: "heading",
          heading: "Second",
        },
        {
          type: "heading",
          heading: "B",
        },
      ],
    },
    {
      strategy: {
        type: "test",
      },
    },
  ]);
});

test("mutations never change their input", () => {
  const base = model.newDashboardConfig();
  base.views[0].sections[0].title = "Section";
  base.views[0].sections[0].cards = [
    {
      type: "heading",
      heading: "Heading",
      grid_options: {
        columns: 6,
        rows: 3,
      },
    },
    {
      type: model.CARD_TYPE,
      component: "apollo/light-tile",
      params: {
        entity: "light.kitchen",
      },
      grid_options: {
        columns: 6,
        rows: 3,
      },
    },
  ];

  const cases = [
    (value) => model.addPage(value, "Second", "mdi:numeric-2"),
    (value) => model.renamePage(value, 0, "Renamed"),
    (value) => model.setPageIcon(value, 0, "mdi:sofa"),
    (value) => model.movePage(
      model.addPage(value, "Second", "mdi:numeric-2").config,
      0,
      1,
    ),
    (value) => model.removePage(
      model.addPage(value, "Second", "mdi:numeric-2").config,
      1,
    ),
    (value) => model.addCard(value, 0, components[0], {
      entity: "light.office",
    }),
    (value) => model.updateCard(value, [0, 0, 1], {
      title: "Light",
    }),
    (value) => model.resizeCard(value, [0, 0, 1], 2, 2),
    (value) => model.moveItem(value, [0, 0, 1], -1),
    (value) => model.removeItem(value, [0, 0, 1]),
    (value) => model.setHeadingText(value, [0, 0, 0], "Changed"),
    (value) => model.setTheme(value, "daylight"),
    (value) => model.useWholeScreen(value, 0),
  ];

  for (const mutate of cases) {
    const input = clone(base);
    const before = model.stableStringify(input);
    mutate(input);
    assert.equal(model.stableStringify(input), before);
  }
});

test("mutations leave cards of other types untouched", () => {
  const originalBubble = clone(
    realDashboard.views[0].sections[0].cards[1],
  );

  const added = model.addCard(
    clone(realDashboard),
    0,
    components[0],
    { entity: "light.office" },
  );
  assert.deepStrictEqual(
    added.config.views[0].sections[0].cards[1],
    originalBubble,
  );

  const moved = model.moveItem(added.config, added.source, -1);
  assert.deepStrictEqual(
    moved.config.views[0].sections[0].cards[2],
    originalBubble,
  );

  const resized = model.resizeCard(added.config, added.source, 2, 2);
  assert.deepStrictEqual(
    resized.views[0].sections[0].cards[1],
    originalBubble,
  );

  const whole = model.useWholeScreen(clone(realDashboard), 0);
  assert.deepStrictEqual(
    whole.views[0].sections[0].cards[1],
    originalBubble,
  );
});

test("pageItems marks a card without a drawn item as not shown with a reason", () => {
  const rows = model.pageItems(
    realDashboard,
    0,
    library,
    realDashboardPreview,
  );

  const heading = rows[0];
  assert.equal(heading.key, "0.0.0");
  assert.equal(heading.kind, "heading");
  assert.equal(heading.shown, true);
  assert.deepStrictEqual(heading.widgets, [
    {
      screen: 0,
      id: 1,
      r: [100, 20, 1164, 56],
    },
  ]);

  const bubble = rows[1];
  assert.equal(bubble.key, "0.0.1");
  assert.equal(bubble.kind, "other");
  assert.equal(bubble.shown, false);
  assert.equal(bubble.reason, "not_tab_element");
  assert.equal(bubble.detail, "custom:bubble-card");
  // The device the card was for, so it can be added back with a TAB-1 card.
  assert.deepStrictEqual(bubble.entities, ["fan.bedroom_main_bedroom_fan"]);
});

test("otherEntities finds the devices a card the tablet cannot draw was for", () => {
  assert.deepStrictEqual(
    model.otherEntities({
      type: "entities",
      entity: "light.kitchen",
      entities: ["light.kitchen", { entity: "switch.fan", name: "Fan" }, "Not an id", { type: "divider" }, 3],
    }),
    ["light.kitchen", "switch.fan"],
  );
  // A TAB-1 card whose kind is not installed keeps its devices in params.
  assert.deepStrictEqual(
    model.otherEntities({
      type: model.CARD_TYPE,
      component: "missing/card",
      params: { entity: "climate.hall", lights: ["light.a", "light.b"], limit: 20, page: "home" },
    }),
    ["climate.hall", "light.a", "light.b"],
  );
  assert.deepStrictEqual(model.otherEntities({ type: "markdown", content: "light.kitchen" }), []);
  assert.deepStrictEqual(model.otherEntities(null), []);
  const many = Array.from({ length: 20 }, (_, index) => `light.l${index}`);
  assert.equal(model.otherEntities({ type: "entities", entities: many }).length, model.MAX_ENTITIES);
});

test("pageItems gives a card that is not installed the devices in its params", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections[0].cards = [
    { type: model.CARD_TYPE, component: "missing/card", params: { entity: "fan.bedroom" } },
  ];
  const row = model.pageItems(config, 0, library, null)[0];
  assert.equal(row.kind, "tab_missing");
  assert.deepStrictEqual(row.entities, ["fan.bedroom"]);
});

test("notShownCounts counts what the editor marks as not shown", () => {
  // The old dashboard: the bubble card is not drawn, and the old
  // "Tablet preview" view is not a page the tablet shows.
  assert.deepStrictEqual(
    model.notShownCounts(realDashboard, library, realDashboardPreview),
    { cards: 1, pages: 1 },
  );
  // Without a preview, only cards that can never be drawn are counted.
  assert.deepStrictEqual(model.notShownCounts(realDashboard, library, null), { cards: 1, pages: 1 });

  const config = model.newDashboardConfig();
  config.views[0].sections[0].cards = [
    { type: model.CARD_TYPE, component: "apollo/light-tile", params: { entity: "light.kitchen" } },
    { type: model.CARD_TYPE, component: "apollo/light-tile", params: { entity: "light.bedroom" } },
  ];
  // The preview drew the first card only; the second was left out.
  const preview = {
    layout: { pages: [{ id: "home", view: 0, w: [{ id: 1, t: "card", r: [0, 0, 10, 10] }] }] },
    sources: { 1: [0, 0, 0] },
    warnings: [],
  };
  assert.deepStrictEqual(model.notShownCounts(config, library, preview), { cards: 1, pages: 0 });
  assert.deepStrictEqual(model.notShownCounts(config, library, null), { cards: 0, pages: 0 });
  // An empty dashboard has nothing that is left out.
  assert.deepStrictEqual(model.notShownCounts(model.newDashboardConfig(), library, null), { cards: 0, pages: 0 });
  assert.deepStrictEqual(model.notShownCounts(null, library, null), { cards: 0, pages: 0 });
});

test("pageItems links shown cards to their drawn items and collects notes", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections[0].cards = [
    {
      type: model.CARD_TYPE,
      component: "apollo/light-tile",
      params: {
        entity: "light.kitchen",
      },
      grid_options: {
        columns: 6,
        rows: 3,
      },
    },
  ];
  const preview = {
    layout: {
      pages: [
        {
          id: "home",
          view: 0,
          w: [
            {
              id: 7,
              t: "card",
              r: [10, 20, 300, 150],
            },
          ],
        },
      ],
    },
    sources: {
      "7": [0, 0, 0],
    },
    warnings: [
      {
        code: "params_incomplete",
        view: 0,
        section: 0,
        card: 0,
        page: "home",
        r: null,
        detail: "entity",
      },
      {
        code: "element_clipped",
        view: 0,
        section: 0,
        card: 0,
        page: "home",
        r: null,
        detail: "",
      },
      {
        code: "params_incomplete",
        view: 0,
        section: 0,
        card: 0,
        page: "home",
        r: null,
        detail: "duplicate",
      },
    ],
  };

  const row = model.pageItems(config, 0, library, preview)[0];

  assert.equal(row.shown, true);
  assert.equal(row.reason, null);
  assert.equal(row.detail, "");
  assert.deepStrictEqual(row.widgets, [
    {
      screen: 0,
      id: 7,
      r: [10, 20, 300, 150],
    },
  ]);
  assert.deepStrictEqual(row.notes, [
    "params_incomplete",
    "element_clipped",
  ]);
});

test("pageItems reports missing, not allowed and over-limit cards", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections[0].cards = [
    {
      type: model.CARD_TYPE,
      component: "missing/card",
    },
    {
      type: model.CARD_TYPE,
      component: "me/door-lock",
      params: {
        entity: "lock.front_door",
      },
    },
    {
      type: model.CARD_TYPE,
      component: "apollo/light-tile",
      params: {
        entity: "light.kitchen",
      },
    },
    {
      type: model.CARD_TYPE,
      component: "apollo/thermostat",
      params: {
        entity: "climate.home",
      },
    },
  ];
  const preview = {
    layout: {
      pages: [
        {
          id: "home",
          view: 0,
          w: [],
        },
      ],
    },
    sources: {},
    warnings: [
      {
        code: "needs_approval",
        view: 0,
        section: 0,
        card: 1,
        page: "home",
        r: null,
        detail: "me/door-lock",
      },
      {
        code: "over_budget_charts",
        view: 0,
        section: 0,
        card: 2,
        page: "home",
        r: null,
        detail: "chart limit",
      },
    ],
  };

  const rows = model.pageItems(config, 0, library, preview);

  assert.equal(rows[0].reason, "unknown_component");
  assert.equal(rows[0].detail, "missing/card");
  assert.equal(rows[1].reason, "needs_approval");
  assert.equal(rows[1].detail, "me/door-lock");
  assert.equal(rows[2].reason, "over_budget_charts");
  assert.equal(rows[2].detail, "chart limit");
  assert.equal(rows[3].reason, "left_out");
  assert.equal(rows[3].detail, "");
});

test("pageItems lists a section title as a heading row", () => {
  const config = model.newDashboardConfig();
  config.views[0].sections[0].title = "Kitchen";
  const preview = {
    layout: {
      pages: [
        {
          id: "home",
          view: 0,
          w: [],
        },
      ],
    },
    warnings: [],
    sources: {},
  };

  const row = model.pageItems(config, 0, library, preview)[0];

  assert.equal(row.key, "0.0.t");
  assert.deepStrictEqual(row.source, [0, 0, null]);
  assert.equal(row.kind, "heading");
  assert.equal(row.title, "Kitchen");
});

test("pageScreens lists the screens of one page", () => {
  const preview = {
    layout: {
      pages: [
        { id: "home", view: 0, w: [] },
        { id: "home-2", view: 0, w: [] },
        { id: "settings", view: 1, w: [] },
      ],
    },
    warnings: [],
    sources: {},
  };

  assert.deepStrictEqual(model.pageScreens(preview, 0), [0, 1]);
  assert.deepStrictEqual(model.pageScreens(preview, 1), [2]);
  assert.deepStrictEqual(model.pageScreens(null, 0), []);
});

test("pageNotes and dashboardNotes pick the right warning codes", () => {
  const preview = {
    layout: {
      pages: [],
    },
    sources: {},
    warnings: [
      {
        code: "view_extras_ignored",
        view: 0,
        section: null,
        card: null,
      },
      {
        code: "section_not_grid",
        view: 0,
        section: 1,
        card: null,
      },
      {
        code: "section_split",
        view: 0,
        section: 1,
        card: null,
      },
      {
        code: "visibility_ignored",
        view: 0,
        section: 1,
        card: null,
      },
      {
        code: "visibility_ignored",
        view: 0,
        section: 2,
        card: null,
      },
      {
        code: "invalid_options",
        view: null,
        section: null,
        card: null,
      },
      {
        code: "too_many_pages",
        view: null,
        section: null,
        card: null,
      },
      {
        code: "columns_differ",
        view: null,
        section: null,
        card: null,
      },
    ],
  };

  assert.deepStrictEqual(model.pageNotes(preview, 0), [
    "view_extras_ignored",
    "section_not_grid",
    "visibility_ignored",
  ]);
  assert.deepStrictEqual(model.dashboardNotes(preview), [
    "invalid_options",
    "too_many_pages",
  ]);
});

test("groupOf sorts the 16 bundled cards into the six groups", () => {
  const grouped = Object.fromEntries(
    model.GROUP_IDS.map((group) => [group, []]),
  );

  for (const card of bundledLibrary) {
    grouped[model.groupOf(card)].push(card.id);
  }

  assert.deepStrictEqual(grouped.lights, [
    "apollo/light-slider",
    "apollo/light-tile",
    "apollo/scene-row",
  ]);
  assert.deepStrictEqual(grouped.climate, [
    "apollo/blinds",
    "apollo/fan",
    "apollo/thermostat",
  ]);
  assert.deepStrictEqual(grouped.media, [
    "apollo/media-player",
  ]);
  assert.deepStrictEqual(grouped.security, [
    "apollo/alarm-panel",
    "apollo/camera-snapshot",
    "apollo/lock",
  ]);
  assert.deepStrictEqual(grouped.sensors, [
    "apollo/sensor-graph",
    "apollo/sensor-value",
    "apollo/weather",
    "community/energy-gauge",
  ]);
  assert.deepStrictEqual(grouped.rooms, [
    "community/presence-chips",
    "community/room-summary",
  ]);
  assert.deepStrictEqual(grouped.more, []);
});

test("pickerGroups keeps group order and drops empty groups", () => {
  const groups = model.pickerGroups(library);

  assert.deepStrictEqual(
    groups.map((group) => group.id),
    ["lights", "climate", "security", "rooms"],
  );
  assert.deepStrictEqual(
    groups.map((group) => group.cards.map((card) => card.id)),
    [
      ["apollo/light-tile", "apollo/scene-row"],
      ["apollo/thermostat"],
      ["apollo/lock", "me/door-lock"],
      ["community/room-summary"],
    ],
  );
});

test("pickerGroups search matches every word in name or description", () => {
  const groups = model.pickerGroups(library, "room sensor");

  assert.deepStrictEqual(groups.map((group) => group.id), ["rooms"]);
  assert.deepStrictEqual(
    groups[0].cards.map((card) => card.id),
    ["community/room-summary"],
  );
  assert.deepStrictEqual(model.pickerGroups(library, "room missing"), []);
});

test("pickerGroups search finds the kind of device, the picker's own words and only word starts", () => {
  const offered = {
    components: [
      component({
        id: "apollo/media-player",
        name: "Now playing",
        description: "Shows what is on",
        params: { entity: { kind: "entity", domain: "media_player", multiple: false } },
      }),
      component({
        id: "community/presence-chips",
        name: "Who is home",
        description: "Track people",
        params: { people: { kind: "entity", domain: "person", multiple: true } },
      }),
    ],
  };
  const ids = (query, describe = null) =>
    model.pickerGroups(offered, query, describe).flatMap((group) => group.cards.map((card) => card.id));

  // The kind of device the card controls.
  assert.deepStrictEqual(ids("media"), ["apollo/media-player"]);
  assert.deepStrictEqual(ids("player"), ["apollo/media-player"]);
  // Only the start of a word counts: "ac" is not found in "Track".
  assert.deepStrictEqual(ids("ac"), []);
  assert.deepStrictEqual(ids("tra"), ["community/presence-chips"]);
  // The words the picker adds: the group's title and the device question.
  const describe = (entry, group) =>
    `${group === "media" ? "Media" : "Rooms"} ${entry.id === "apollo/media-player" ? "Which TV or speaker?" : "Which people?"}`;
  assert.deepStrictEqual(ids("tv", describe), ["apollo/media-player"]);
  assert.deepStrictEqual(ids("speaker", describe), ["apollo/media-player"]);
  assert.deepStrictEqual(ids("rooms", describe), ["community/presence-chips"]);
  assert.deepStrictEqual(ids("tv", null), []);
});

test("fitsDevices keeps the cards with a device field for one of the devices", () => {
  const fits = (entityIds) =>
    components.filter((entry) => model.fitsDevices(entry, entityIds)).map((entry) => entry.id);
  assert.deepStrictEqual(fits(["light.kitchen"]), ["apollo/light-tile", "community/room-summary"]);
  assert.deepStrictEqual(fits(["lock.front_door"]), ["apollo/lock", "me/door-lock"]);
  assert.deepStrictEqual(fits(["climate.hall", "scene.movie"]), ["apollo/thermostat", "apollo/scene-row"]);
  // A device no card can control, or none at all, fits no card.
  assert.deepStrictEqual(fits(["input_boolean.guest_mode"]), []);
  assert.deepStrictEqual(fits([]), []);
  assert.deepStrictEqual(fits(null), []);
  // "light" is not "light_group".
  assert.deepStrictEqual(fits(["light_group.hall"]), []);
});

test("presetParams fills the device fields that fit the removed card's devices", () => {
  const [lightTile, , sceneRow, roomSummary] = components;
  assert.deepStrictEqual(model.presetParams(lightTile, ["fan.bedroom", "light.kitchen"]), { entity: "light.kitchen" });
  assert.deepStrictEqual(model.presetParams(sceneRow, ["scene.movie", "scene.dinner"]), {
    scenes: ["scene.movie", "scene.dinner"],
  });
  // Each single field takes a device the field before it did not take.
  assert.deepStrictEqual(
    model.presetParams(roomSummary, ["sensor.temperature", "light.kitchen", "sensor.humidity"]),
    { temperature_sensor: "sensor.temperature", humidity_sensor: "sensor.humidity", lights: ["light.kitchen"] },
  );
  assert.deepStrictEqual(model.presetParams(roomSummary, ["sensor.temperature"]), {
    temperature_sensor: "sensor.temperature",
  });
  assert.deepStrictEqual(model.presetParams(lightTile, ["fan.bedroom"]), {});
  assert.deepStrictEqual(model.presetParams(null, ["light.kitchen"]), {});
});

test("singleEntityParam is set only for one single entity param", () => {
  assert.equal(model.singleEntityParam(components[0]), "entity");
  assert.equal(model.singleEntityParam(components[2]), null);
  assert.equal(model.singleEntityParam(components[3]), null);
  assert.equal(
    model.singleEntityParam(
      component({
        id: "test/no-params",
        params: {},
      }),
    ),
    null,
  );
});

test("entityChoices filters by domain and leaves out hidden entities", () => {
  const hass = {
    states: {
      "light.kitchen": {
        attributes: {
          friendly_name: "Kitchen light",
        },
      },
      "light.hidden": {
        attributes: {
          friendly_name: "Hidden light",
        },
      },
      "sensor.temperature": {
        attributes: {
          friendly_name: "Temperature",
        },
      },
    },
    entities: {
      "light.hidden": {
        hidden: true,
      },
    },
  };
  const choices = model.entityChoices(hass, {
    domain: "light",
  });

  assert.deepStrictEqual(choices, [
    {
      entity_id: "light.kitchen",
      name: "Kitchen light",
      area: "",
    },
  ]);
});

test("entityChoices sorts by name and finds areas through the device", () => {
  const hass = {
    states: {
      "sensor.beta": {
        attributes: {
          friendly_name: "Beta",
        },
      },
      "sensor.alpha": {
        attributes: {
          friendly_name: "Alpha",
        },
      },
    },
    entities: {
      "sensor.beta": {
        area_id: "office",
      },
      "sensor.alpha": {
        device_id: "device-alpha",
      },
    },
    devices: {
      "device-alpha": {
        area_id: "kitchen",
      },
    },
    areas: {
      office: {
        name: "Office",
      },
      kitchen: {
        name: "Kitchen",
      },
    },
  };

  assert.deepStrictEqual(
    model.entityChoices(hass, {
      domain: "sensor",
    }),
    [
      {
        entity_id: "sensor.alpha",
        name: "Alpha",
        area: "Kitchen",
      },
      {
        entity_id: "sensor.beta",
        name: "Beta",
        area: "Office",
      },
    ],
  );
});

test("entityChoices search matches name, room and entity id", () => {
  const hass = {
    states: {
      "light.ceiling_main": {
        attributes: {
          friendly_name: "Ceiling",
        },
      },
      "light.table": {
        attributes: {
          friendly_name: "Table lamp",
        },
      },
    },
    entities: {
      "light.ceiling_main": {
        area_id: "kitchen",
      },
      "light.table": {
        area_id: "office",
      },
    },
    areas: {
      kitchen: {
        name: "Kitchen",
      },
      office: {
        name: "Office",
      },
    },
  };
  const spec = {
    domain: "light",
  };

  assert.deepStrictEqual(
    model.entityChoices(hass, spec, "ceiling kitchen").map(
      (choice) => choice.entity_id,
    ),
    ["light.ceiling_main"],
  );
  assert.deepStrictEqual(
    model.entityChoices(hass, spec, "table office").map(
      (choice) => choice.entity_id,
    ),
    ["light.table"],
  );
  assert.deepStrictEqual(
    model.entityChoices(hass, spec, "ceiling_main").map(
      (choice) => choice.entity_id,
    ),
    ["light.ceiling_main"],
  );
});

test("paramsComplete needs every entity param", () => {
  const room = components[3];

  assert.equal(
    model.paramsComplete(room, {
      temperature_sensor: "sensor.temperature",
      humidity_sensor: "sensor.humidity",
      lights: ["light.kitchen"],
    }),
    true,
  );
  assert.equal(
    model.paramsComplete(room, {
      temperature_sensor: "sensor.temperature",
      humidity_sensor: "",
      lights: ["light.kitchen"],
    }),
    false,
  );
  assert.equal(
    model.paramsComplete(room, {
      temperature_sensor: "sensor.temperature",
      humidity_sensor: "sensor.humidity",
      lights: [],
    }),
    false,
  );
  assert.equal(
    model.paramsComplete(components[0], {
      entity: "light.kitchen",
    }),
    true,
  );
});

test("pageChoices lists only real pages with valid paths", () => {
  const config = {
    views: [
      {
        type: "sections",
        title: "Home",
        path: "home",
        sections: [],
      },
      {
        type: "sections",
        title: "Invalid",
        path: "Invalid path",
        sections: [],
      },
      {
        type: "panel",
        title: "Preview",
        path: "preview",
        cards: [
          {
            type: model.PREVIEW_TYPE,
          },
        ],
      },
      {
        type: "sections",
        path: "settings_2",
        sections: [],
      },
    ],
  };

  assert.deepStrictEqual(model.pageChoices(config), [
    {
      path: "home",
      title: "Home",
    },
    {
      path: "settings_2",
      title: "settings_2",
    },
  ]);
});

test("styleDefaults fills missing colours from the theme", () => {
  const input = {
    use_color: true,
    use_accent: true,
    gradient: "linear",
    existing: true,
  };

  assert.deepStrictEqual(model.styleDefaults(input, themes[0]), {
    use_color: true,
    use_accent: true,
    gradient: "linear",
    existing: true,
    color: [24, 28, 35],
    accent: [245, 181, 71],
    gradient_to: [35, 40, 51],
  });

  assert.deepStrictEqual(
    model.styleDefaults(
      {
        use_color: true,
        color: [1, 2, 3],
        gradient: "none",
      },
      themes[1],
    ),
    {
      use_color: true,
      color: [1, 2, 3],
      gradient: "none",
    },
  );
});

test("historyPush records steps, joins quick edits of one field and caps the length", () => {
  let history = model.createHistory({ value: 0 });

  history = model.historyPush(history, { value: 1 }, {
    key: "title",
    now: 100,
  });
  history = model.historyPush(history, { value: 2 }, {
    key: "title",
    now: 500,
  });

  assert.deepStrictEqual(history.past, [{ value: 0 }]);
  assert.deepStrictEqual(history.present, { value: 2 });

  history = model.historyPush(history, { value: 3 }, {
    key: "icon",
    now: 600,
  });
  assert.deepStrictEqual(history.past, [
    { value: 0 },
    { value: 2 },
  ]);

  for (let value = 4; value <= 60; value += 1) {
    history = model.historyPush(history, { value }, {
      key: null,
      now: value * 1000,
    });
  }

  assert.equal(history.past.length, model.HISTORY_LIMIT);
  assert.deepStrictEqual(history.present, { value: 60 });
});

test("historyUndo and historyRedo walk both ways and stop at the ends", () => {
  let history = model.createHistory({ value: 0 });
  history = model.historyPush(history, { value: 1 });
  history = model.historyPush(history, { value: 2 });

  assert.equal(model.canUndo(history), true);
  assert.equal(model.canRedo(history), false);

  history = model.historyUndo(history);
  assert.deepStrictEqual(history.present, { value: 1 });
  history = model.historyUndo(history);
  assert.deepStrictEqual(history.present, { value: 0 });

  const atStart = model.historyUndo(history);
  assert.deepStrictEqual(atStart, history);
  assert.equal(model.canUndo(history), false);
  assert.equal(model.canRedo(history), true);

  history = model.historyRedo(history);
  assert.deepStrictEqual(history.present, { value: 1 });
  history = model.historyRedo(history);
  assert.deepStrictEqual(history.present, { value: 2 });

  const atEnd = model.historyRedo(history);
  assert.deepStrictEqual(atEnd, history);
  assert.equal(model.canRedo(history), false);
});

test("SaveQueue saves once after the delay and reports saved", async () => {
  const timers = makeTimers();
  const savedConfigs = [];
  const states = [];
  let resolveSave;

  const queue = new model.SaveQueue({
    save(config) {
      savedConfigs.push(config);
      return new Promise((resolve) => {
        resolveSave = resolve;
      });
    },
    delay: 400,
    onState(state, error) {
      states.push([state, error]);
    },
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });

  queue.reset({ value: 0 });
  queue.push({ value: 1 });

  assert.equal(queue.state, "pending");
  assert.equal(savedConfigs.length, 0);
  assert.equal(timers.callbacks.size, 1);

  timers.fire();
  await settle();

  assert.equal(queue.state, "saving");
  assert.deepStrictEqual(savedConfigs, [{ value: 1 }]);

  resolveSave();
  await settle();

  assert.equal(queue.state, "saved");
  assert.deepStrictEqual(queue.saved, { value: 1 });
  assert.equal(queue.dirty, false);
  assert.ok(states.some(([state]) => state === "pending"));
  assert.ok(states.some(([state]) => state === "saving"));
  assert.ok(states.some(([state]) => state === "saved"));
});

test("SaveQueue keeps only the newest draft while a save is running", async () => {
  const timers = makeTimers();
  const saves = [];
  const resolvers = [];

  const queue = new model.SaveQueue({
    save(config) {
      saves.push(config);
      return new Promise((resolve) => {
        resolvers.push(resolve);
      });
    },
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });

  queue.reset({ value: 0 });
  queue.push({ value: 1 });
  timers.fire();
  await settle();

  queue.push({ value: 2 });
  queue.push({ value: 3 });

  assert.equal(queue.state, "saving");
  assert.deepStrictEqual(saves, [{ value: 1 }]);

  resolvers[0]();
  await settle();

  assert.deepStrictEqual(saves, [
    { value: 1 },
    { value: 3 },
  ]);
  assert.equal(queue.state, "saving");

  resolvers[1]();
  await settle();

  assert.equal(queue.state, "saved");
  assert.deepStrictEqual(queue.saved, { value: 3 });
});

test("SaveQueue reports an error, keeps the draft and saves it on retry", async () => {
  const timers = makeTimers();
  const error = new Error("Save failed");
  const saves = [];
  let attempt = 0;

  const queue = new model.SaveQueue({
    save(config) {
      saves.push(config);
      attempt += 1;
      if (attempt === 1) {
        return Promise.reject(error);
      }
      return Promise.resolve();
    },
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });

  queue.reset({ value: 0 });
  queue.push({ value: 1 });
  timers.fire();
  await settle();

  assert.equal(queue.state, "error");
  assert.equal(queue.error, error);
  assert.equal(queue.dirty, true);
  assert.deepStrictEqual(queue.saved, { value: 0 });

  await queue.retry();
  await settle();

  assert.deepStrictEqual(saves, [
    { value: 1 },
    { value: 1 },
  ]);
  assert.equal(queue.state, "saved");
  assert.equal(queue.error, null);
  assert.deepStrictEqual(queue.saved, { value: 1 });
});

test("SaveQueue does not start saves while paused and flushes on resume", async () => {
  const timers = makeTimers();
  const saves = [];

  const queue = new model.SaveQueue({
    save(config) {
      saves.push(config);
      return Promise.resolve();
    },
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });

  queue.reset({ value: 0 });
  queue.pause();
  queue.push({ value: 1 });
  timers.fire();
  await settle();

  assert.equal(queue.state, "paused");
  assert.deepStrictEqual(saves, []);

  queue.resume();
  await settle();

  assert.deepStrictEqual(saves, [{ value: 1 }]);
  assert.equal(queue.state, "saved");
  assert.deepStrictEqual(queue.saved, { value: 1 });
});

test("SaveQueue skips a draft equal to what is saved", async () => {
  const timers = makeTimers();
  let calls = 0;

  const queue = new model.SaveQueue({
    save() {
      calls += 1;
      return Promise.resolve();
    },
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });

  queue.reset({
    value: 1,
    nested: {
      enabled: true,
    },
  });
  queue.push({
    nested: {
      enabled: true,
    },
    value: 1,
  });
  await settle();

  assert.equal(queue.state, "saved");
  assert.equal(queue.dirty, false);
  assert.equal(calls, 0);
  assert.equal(timers.callbacks.size, 0);
});

test("SaveQueue calls the timer functions unbound, as browsers require", async () => {
  // window.setTimeout throws "Illegal invocation" when called as a method
  // of another object; these stand-ins do the same.
  const started = [];
  const cleared = [];
  function setTimer(callback, ms) {
    if (this !== undefined && this !== globalThis) {
      throw new TypeError("Illegal invocation");
    }
    started.push([callback, ms]);
    return started.length;
  }
  function clearTimer(id) {
    if (this !== undefined && this !== globalThis) {
      throw new TypeError("Illegal invocation");
    }
    cleared.push(id);
  }
  const saved = [];
  const queue = new model.SaveQueue({
    save(config) {
      saved.push(config);
      return Promise.resolve();
    },
    setTimer,
    clearTimer,
  });

  queue.reset({ value: 1 });
  queue.push({ value: 2 });
  queue.push({ value: 3 });
  assert.equal(started.length, 2);
  assert.equal(cleared.length, 1);
  started.at(-1)[0]();
  await settle();

  assert.deepEqual(saved, [{ value: 3 }]);
  assert.equal(queue.state, "saved");
});

test("classifyRemote recognises our own saved and in-flight versions", () => {
  const state = {
    saved: {
      value: 1,
    },
    inflight: {
      value: 2,
    },
  };

  assert.equal(
    model.classifyRemote({ value: 1 }, state),
    "ours",
  );
  assert.equal(
    model.classifyRemote({ value: 2 }, state),
    "ours",
  );
  assert.equal(
    model.classifyRemote({ value: 3 }, state),
    "changed",
  );
  assert.equal(
    model.classifyRemote(
      { value: 2 },
      {
        saved: { value: 1 },
        inflight: null,
      },
    ),
    "changed",
  );
});

// A stand-in for Home Assistant that stores a save when its answer is
// released, so a test decides when each save lands.
const slowServer = (first) => {
  const timers = makeTimers();
  const server = { config: first, pending: [] };
  const queue = new model.SaveQueue({
    save: (config) =>
      new Promise((resolve) => {
        server.pending.push(() => {
          server.config = config;
          resolve();
        });
      }),
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });
  queue.reset(first);

  const land = async () => {
    server.pending.shift()();
    await settle();
  };
  const finish = async () => {
    for (let round = 0; round < 10; round += 1) {
      timers.fire();
      await settle();
      while (server.pending.length) {
        await land();
      }
    }
  };
  return { server, queue, timers, land, finish };
};

test("SaveQueue saves the other version again when it is taken while a save is running", async () => {
  const { server, queue, timers, finish } = slowServer({ value: "start" });
  queue.push({ value: "mine" });
  timers.fire();
  await settle();
  assert.equal(queue.state, "saving");

  // Someone else saves; the editor pauses, then the user takes their version.
  server.config = { value: "theirs" };
  queue.pause();
  queue.reset({ value: "theirs" });
  assert.equal(queue.dirty, true);
  queue.push({ value: "theirs" });

  await finish();

  assert.equal(queue.state, "saved");
  assert.deepStrictEqual(server.config, { value: "theirs" });
  assert.deepStrictEqual(queue.saved, { value: "theirs" });
  assert.deepStrictEqual(queue.outdated, []);
});

test("SaveQueue knows its own older save after a conflict was answered", async () => {
  const { server, queue, timers, land, finish } = slowServer({ value: "start" });
  queue.push({ value: "mine 1" });
  timers.fire();
  await settle();

  server.config = { value: "theirs" };
  queue.pause();
  queue.reset({ value: "theirs" });
  queue.push({ value: "mine 2" });
  queue.flush();

  await land();
  assert.deepStrictEqual(server.config, { value: "mine 1" });
  assert.equal(model.classifyRemote(server.config, queue), "ours");
  assert.equal(model.classifyRemote({ value: "another" }, queue), "changed");
  assert.equal(queue.state, "saving");

  await finish();

  assert.equal(queue.state, "saved");
  assert.deepStrictEqual(server.config, { value: "mine 2" });
});

test("SaveQueue saves the chosen version when a save landed during the pause", async () => {
  const { server, queue, timers, land, finish } = slowServer({ value: "start" });
  queue.push({ value: "mine" });
  timers.fire();
  await settle();

  server.config = { value: "theirs" };
  queue.pause();
  await land();
  assert.deepStrictEqual(server.config, { value: "mine" });
  assert.equal(queue.state, "paused");

  queue.reset({ value: "theirs" });
  assert.equal(queue.state, "pending");
  assert.equal(model.classifyRemote({ value: "mine" }, queue), "ours");
  queue.push({ value: "theirs" });

  await finish();

  assert.equal(queue.state, "saved");
  assert.deepStrictEqual(server.config, { value: "theirs" });
});

test("SaveQueue keeps a newer draft when an outdated save fails", async () => {
  const timers = makeTimers();
  const saves = [];
  const answers = [];
  const queue = new model.SaveQueue({
    save: (config) =>
      new Promise((resolve, reject) => {
        saves.push(config);
        answers.push({ resolve, reject });
      }),
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });
  queue.reset({ value: "start" });
  queue.push({ value: "mine 1" });
  timers.fire();
  await settle();

  queue.pause();
  queue.reset({ value: "theirs" });
  queue.push({ value: "mine 2" });
  answers[0].reject(new Error("offline"));
  await settle();

  assert.deepStrictEqual(saves, [{ value: "mine 1" }, { value: "mine 2" }]);
  answers[1].resolve();
  await settle();
  assert.equal(queue.state, "saved");
  assert.equal(queue.error, null);
});

test("SaveQueue reset with no save of its own under way saves nothing", async () => {
  const { server, queue, finish } = slowServer({ value: "start" });
  queue.reset({ value: "theirs" });

  assert.equal(queue.state, "saved");
  assert.deepStrictEqual(queue.outdated, []);
  await finish();
  assert.deepStrictEqual(server.config, { value: "start" });
});

test("classifyRemote recognises versions the queue lists as outdated", () => {
  const state = { saved: null, inflight: null, outdated: [{ value: 1 }] };

  assert.equal(model.classifyRemote({ value: 1 }, state), "ours");
  assert.equal(model.classifyRemote({ value: 2 }, state), "changed");
  assert.equal(model.classifyRemote(null, state), "changed");
});

// A stand-in for Home Assistant that the queue reads before each save. A
// change can be stored "while this browser is offline": no event tells the
// editor, so only the read before the save can find it. Each read and each
// save waits until the test releases it with answer().
const checkedServer = (first) => {
  const timers = makeTimers();
  const server = { config: first, reads: 0, saves: [], changed: [], pending: [] };
  const queue = new model.SaveQueue({
    read: () =>
      new Promise((resolve) => {
        server.reads += 1;
        server.pending.push(() => resolve(structuredClone(server.config)));
      }),
    save: (config) =>
      new Promise((resolve, reject) => {
        server.pending.push((error) => {
          if (error) {
            reject(error);
            return;
          }
          server.saves.push(config);
          server.config = config;
          resolve();
        });
      }),
    onChanged: (stored, kind) => server.changed.push(kind === "unsure" ? [stored, kind] : stored),
    setTimer: timers.setTimer,
    clearTimer: timers.clearTimer,
  });
  queue.reset(first);
  const answer = async (error) => {
    server.pending.shift()(error);
    await settle();
  };
  // Releases every read and save until nothing is left to do.
  const finish = async () => {
    for (let round = 0; round < 10; round += 1) {
      timers.fire();
      await settle();
      while (server.pending.length) {
        await answer();
      }
    }
  };
  return { server, queue, timers, answer, finish };
};

test("SaveQueue never saves over a version stored while this browser heard nothing", async () => {
  const { server, queue, finish } = checkedServer({ value: "start" });
  server.config = { value: "theirs" };
  queue.push({ value: "mine" });

  await finish();

  assert.deepStrictEqual(server.saves, []);
  assert.deepStrictEqual(server.config, { value: "theirs" });
  assert.equal(queue.state, "paused");
  assert.equal(queue.dirty, true);
  assert.equal(queue.error, null);
  assert.deepStrictEqual(server.changed, [{ value: "theirs" }]);

  // Keep my version: the queue is told what is stored and saves over it.
  queue.reset({ value: "theirs" });
  queue.push({ value: "mine" });
  await finish();
  assert.deepStrictEqual(server.saves, [{ value: "mine" }]);
  assert.equal(queue.state, "saved");
});

test("SaveQueue Try again after a failed save reads first and keeps a newer version", async () => {
  const { server, queue, timers, answer, finish } = checkedServer({ value: "start" });
  queue.push({ value: "mine" });
  timers.fire();
  await settle();
  await answer();
  await answer(new Error("connection lost"));
  assert.equal(queue.state, "error");

  server.config = { value: "theirs" };
  queue.retry();
  await finish();

  assert.deepStrictEqual(server.saves, []);
  assert.deepStrictEqual(server.config, { value: "theirs" });
  assert.equal(queue.state, "paused");
  assert.deepStrictEqual(server.changed, [{ value: "theirs" }]);
  assert.equal(server.reads, 2);
});

// Home Assistant's library answers a save under way with "Connection lost"
// when the connection drops, though the save may have been stored.
test("SaveQueue counts a save whose answer was lost as one of its own", async () => {
  const { server, queue, timers, answer, finish } = checkedServer({ value: "start" });
  queue.push({ value: "one" });
  timers.fire();
  await settle();
  await answer();
  server.config = { value: "one" };
  await answer(new Error("Connection lost"));
  assert.equal(queue.state, "error");
  assert.equal(model.classifyRemote({ value: "one" }, queue), "ours");

  // The next change is saved without asking about "one".
  queue.push({ value: "two" });
  await finish();
  assert.deepStrictEqual(server.changed, []);
  assert.deepStrictEqual(server.saves, [{ value: "two" }]);
  assert.equal(queue.state, "saved");

  // So is Try again after such a save.
  queue.push({ value: "three" });
  timers.fire();
  await settle();
  await answer();
  server.config = { value: "three" };
  await answer(new Error("Connection lost"));
  queue.retry();
  await finish();
  assert.deepStrictEqual(server.changed, []);
  assert.equal(queue.state, "saved");
});

test("SaveQueue saves after the read when Home Assistant holds one of its own versions", async () => {
  const { server, queue, finish } = checkedServer({ value: "start" });
  queue.push({ value: "one" });
  await finish();
  queue.push({ value: "two" });
  await finish();

  assert.deepStrictEqual(server.saves, [{ value: "one" }, { value: "two" }]);
  assert.equal(queue.state, "saved");
  assert.deepStrictEqual(server.changed, []);
});

test("SaveQueue sends nothing when it is paused while reading", async () => {
  const { server, queue, timers, answer, finish } = checkedServer({ value: "start" });
  queue.push({ value: "mine" });
  timers.fire();
  await settle();
  assert.equal(server.reads, 1);

  queue.pause();
  let settled = false;
  queue.flush().then(() => {
    settled = true;
  });
  await answer();
  assert.deepStrictEqual(server.saves, []);
  assert.equal(queue.state, "paused");
  assert.equal(settled, true);

  queue.resume();
  await finish();
  assert.deepStrictEqual(server.saves, [{ value: "mine" }]);
  assert.equal(queue.state, "saved");
});

test("SaveQueue knows the version it was told about while one of its saves was running", async () => {
  const { server, queue, timers, answer, finish } = checkedServer({ value: "start" });
  queue.push({ value: "mine 1" });
  timers.fire();
  await settle();
  await answer();
  assert.equal(queue.state, "saving");

  // Someone else saves; the person keeps their own version while the first
  // save is still on its way, and that save then fails.
  server.config = { value: "theirs" };
  queue.pause();
  queue.reset({ value: "theirs" });
  queue.push({ value: "mine 2" });
  queue.flush();
  await answer(new Error("offline"));
  await finish();

  assert.deepStrictEqual(server.changed, []);
  assert.deepStrictEqual(server.saves, [{ value: "mine 2" }]);
  assert.equal(queue.state, "saved");
});

// The connection was lost and came back while a change waited: the
// dashboard may have been deleted and made again with the content the
// change started from. That content no longer counts as the queue's own.
test("SaveQueue never saves into a version it was only told about once in doubt", async () => {
  const { server, queue, timers, answer, finish } = checkedServer({ value: "start" });
  queue.push({ value: "mine" });
  timers.fire();
  await settle();
  await answer();
  await answer(new Error("connection lost"));
  assert.equal(queue.state, "error");

  // Another browser deletes the dashboard and makes it again, with the same
  // content, while this one is offline.
  server.config = { value: "start" };
  queue.doubt();
  assert.equal(model.classifyRemote({ value: "start" }, queue), "unsure");
  assert.equal(model.classifyRemote({ value: "other" }, queue), "changed");
  queue.retry();
  await finish();

  assert.deepStrictEqual(server.saves, []);
  assert.equal(queue.state, "paused");
  assert.equal(queue.dirty, true);
  assert.deepStrictEqual(server.changed, [[{ value: "start" }, "unsure"]]);

  // Keep my version: what is stored is known again, and the change is saved.
  queue.reset({ value: "start" });
  assert.equal(queue.doubted, false);
  assert.equal(model.classifyRemote({ value: "start" }, queue), "ours");
  queue.push({ value: "mine" });
  await finish();
  assert.deepStrictEqual(server.saves, [{ value: "mine" }]);
  assert.equal(queue.state, "saved");
});

test("SaveQueue in doubt still knows the versions it saved itself", async () => {
  const { server, queue, finish } = checkedServer({ value: "start" });
  queue.push({ value: "one" });
  await finish();
  assert.deepStrictEqual(queue.told, []);

  queue.doubt();
  // Its own save is not content a new dashboard starts with.
  assert.equal(model.classifyRemote({ value: "one" }, queue), "ours");
  queue.push({ value: "two" });
  await finish();
  assert.deepStrictEqual(server.saves, [{ value: "one" }, { value: "two" }]);
  assert.deepStrictEqual(server.changed, []);
});

test("classifyRemote is unsure only about told versions while in doubt", () => {
  const told = { value: 1 };
  const own = { value: 2 };
  const state = { saved: own, inflight: null, outdated: [told], told: [told], doubted: false };
  assert.equal(model.classifyRemote({ value: 1 }, state), "ours");
  state.doubted = true;
  assert.equal(model.classifyRemote({ value: 1 }, state), "unsure");
  assert.equal(model.classifyRemote({ value: 2 }, state), "ours");
  assert.equal(model.classifyRemote({ value: 3 }, state), "changed");
  // A told version that is also one of its own saves stays its own.
  state.outdated = [told, { value: 1 }];
  assert.equal(model.classifyRemote({ value: 1 }, state), "ours");
});

test("devicesLeft lists the devices a chosen card does not use", () => {
  const devices = ["light.kitchen", "light.bedroom", "fan.bedroom_main_bedroom_fan"];
  assert.deepStrictEqual(model.devicesLeft(devices, { entity: "light.kitchen" }), [
    "light.bedroom",
    "fan.bedroom_main_bedroom_fan",
  ]);
  assert.deepStrictEqual(
    model.devicesLeft(devices, { lights: ["light.kitchen", "light.bedroom"], page: "home" }),
    ["fan.bedroom_main_bedroom_fan"],
  );
  assert.deepStrictEqual(model.devicesLeft(devices, {}), devices);
  assert.deepStrictEqual(model.devicesLeft(devices, null), devices);
  assert.deepStrictEqual(model.devicesLeft(null, { entity: "light.kitchen" }), []);
});

// The sample dashboard's first page: a titled section of graphs and a
// titled section of lights, as the browser run uses it.
const followPage = () => {
  const card = (component, entity) => ({
    type: "custom:apollo-tab-card",
    component,
    params: { entity },
  });
  return {
    apollo_tab: { version: 1, theme: "midnight" },
    views: [
      {
        type: "sections",
        title: "Home",
        path: "home",
        sections: [
          { type: "grid", title: "Energy", cards: [card("apollo/sensor-graph", "sensor.energy")] },
          {
            type: "grid",
            title: "Lights",
            cards: [
              card("apollo/light-tile", "light.kitchen"),
              card("apollo/light-slider", "light.living_room"),
              card("apollo/fan", "fan.bedroom"),
              card("apollo/sensor-value", "sensor.temperature"),
            ],
          },
        ],
      },
      { type: "sections", title: "Bedroom", path: "bedroom", sections: [{ type: "grid", cards: [] }] },
    ],
  };
};

test("followItem keeps the selected card through undo of a move", () => {
  const config = followPage();
  const moved = model.moveItem(config, [0, 1, 0], 1);
  assert.deepStrictEqual(moved.source, [0, 1, 1]);
  // Undo puts the light tile back in front; the selection goes with it.
  assert.deepStrictEqual(model.followItem(moved.config, config, [0, 1, 1]), [0, 1, 0]);
  // Redo moves it back again.
  assert.deepStrictEqual(model.followItem(config, moved.config, [0, 1, 0]), [0, 1, 1]);
});

test("followItem keeps the selected card when an earlier card comes back or goes", () => {
  const config = followPage();
  const removed = model.removeItem(config, [0, 1, 0]);
  // The fan moved up to 0.1.1 when the light tile was removed; Undo brings
  // the light tile back, and the fan is at 0.1.2 again.
  assert.equal(model.getCard(removed, [0, 1, 1]).component, "apollo/fan");
  assert.deepStrictEqual(model.followItem(removed, config, [0, 1, 1]), [0, 1, 2]);
  // Another browser removes the light tile while the fan is selected.
  assert.deepStrictEqual(model.followItem(config, removed, [0, 1, 2]), [0, 1, 1]);
});

test("followItem keeps a card that was only edited in place", () => {
  const config = followPage();
  const wider = model.resizeCard(config, [0, 1, 1], 2, 1);
  assert.deepStrictEqual(model.followItem(wider, config, [0, 1, 1]), [0, 1, 1]);
  assert.deepStrictEqual(model.followItem(config, wider, [0, 1, 1]), [0, 1, 1]);

  // An identical copy of the edited card elsewhere does not take the
  // selection away from the card that was edited.
  const twins = followPage();
  twins.views[0].sections[1].cards = [
    structuredClone(wider.views[0].sections[1].cards[1]),
    structuredClone(wider.views[0].sections[1].cards[1]),
  ];
  const narrower = structuredClone(twins);
  narrower.views[0].sections[1].cards[0] = structuredClone(config.views[0].sections[1].cards[1]);
  assert.deepStrictEqual(model.followItem(twins, narrower, [0, 1, 0]), [0, 1, 0]);

  // A section title renamed in place stays selected.
  const renamed = model.setHeadingText(config, [0, 1, null], "Lamps");
  assert.deepStrictEqual(model.followItem(config, renamed, [0, 1, null]), [0, 1, null]);
});

test("followItem lets go when the card is gone or changed along with the page", () => {
  const config = followPage();
  assert.equal(model.followItem(config, model.removeItem(config, [0, 1, 2]), [0, 1, 2]), null);
  assert.equal(model.followItem(config, model.removeItem(config, [0, 1, null]), [0, 1, null]), null);
  assert.equal(model.followItem(config, model.removePage(config, 0).config, [0, 1, 2]), null);
  assert.equal(model.followItem(config, config, [0, 1, 9]), null);
  assert.equal(model.followItem(config, config, "0.1.2"), null);

  // Changed by someone else together with another card: it may not be the
  // same card any more, so nothing stays selected.
  const both = model.resizeCard(model.removeItem(config, [0, 1, 0]), [0, 1, 1], 2, 1);
  assert.equal(model.followItem(config, both, [0, 1, 2]), null);
});

test("followItem picks the same copy of a card that appears twice", () => {
  const config = followPage();
  const cards = config.views[0].sections[1].cards;
  cards.splice(3, 0, structuredClone(cards[1]));
  // Lights: light tile, light slider, fan, light slider, sensor value.
  const removed = model.removeItem(config, [0, 1, 0]);
  // With the light tile removed, the second slider (0.1.2) is selected.
  // Undo brings the light tile back: both sliders are now one place from
  // where it was, and the second copy is the one that stays selected.
  assert.deepStrictEqual(model.followItem(removed, config, [0, 1, 2]), [0, 1, 3]);
  assert.deepStrictEqual(model.followItem(removed, config, [0, 1, 0]), [0, 1, 1]);
  // Without a tie the nearest copy is taken.
  const fewer = model.removeItem(config, [0, 1, 2]);
  assert.deepStrictEqual(model.followItem(config, fewer, [0, 1, 3]), [0, 1, 2]);
});
