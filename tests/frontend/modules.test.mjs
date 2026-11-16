import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "../../custom_components/apollo_tab/frontend");
const logicPath = path.join(frontend, "logic.js");
const modelPath = path.join(frontend, "model.js");

const expected = [
  "HEX_RE",
  "ICON_RE",
  "isHex",
  "isIcon",
  "isSafeImagePath",
  "format",
  "resolveBound",
  "isOn",
  "toNumber",
  "clampStep",
  "fraction",
  "mapRect",
  "linePoints",
  "barRects",
  "arcPath",
  "aliasTag",
  "dashboardFromPath",
  "subscriptionKey",
  "styleToForm",
  "formToStyle",
  "cleanConfig",
  "feedbackReduce",
  "warningText",
  "warningPlace",
  "parseCssColour",
  "accentInk",
  "accentGrounds",
  "accentText",
  "layoutBand",
  "shellHeight",
  "fitStage",
  "drawerShift",
  "placeBeside",
];

test("logic module exports the complete public surface", async () => {
  const module = await import(pathToFileURL(logicPath));
  for (const name of expected) {
    assert.equal(Object.hasOwn(module, name), true, `missing export ${name}`);
  }
});

const removed = [
  "gridForSize",
  "sizePreset",
  "pickStubParams",
  "paramsSchema",
  "nextDashboardPath",
  "starterConfig",
];

test("logic module no longer exports the old editor helpers", async () => {
  const module = await import(pathToFileURL(logicPath));
  for (const name of removed) {
    assert.equal(Object.hasOwn(module, name), false, `unexpected export ${name}`);
  }
});

const modelExpected = [
  "CARD_TYPE",
  "PREVIEW_TYPE",
  "ALIAS_PREFIX",
  "UNIT_COLUMNS",
  "UNIT_ROWS",
  "MAX_UNITS_HIGH",
  "MAX_UNITS_WIDE",
  "MAX_ENTITIES",
  "HISTORY_LIMIT",
  "DEFAULT_THEME",
  "PREVIEW_THEMES",
  "GROUP_IDS",
  "PAGE_ICONS",
  "stableStringify",
  "sameConfig",
  "sourceKey",
  "parseSourceKey",
  "slugPath",
  "newDashboardConfig",
  "newPage",
  "nextDashboardPath",
  "nextDashboardTitle",
  "mergeDashboards",
  "compareCodePoints",
  "compareDashboards",
  "sortDashboards",
  "isGridSection",
  "sectionSpan",
  "pageKind",
  "pageList",
  "componentOf",
  "cardKind",
  "isAllowed",
  "cardEntities",
  "otherEntities",
  "getCard",
  "usesWholeScreen",
  "pageScreens",
  "omittedOnPage",
  "pageItems",
  "pageNotes",
  "dashboardNotes",
  "notShownCounts",
  "addPage",
  "renamePage",
  "setPageIcon",
  "movePage",
  "removePage",
  "addCard",
  "updateCard",
  "cardSize",
  "maxUnitsWide",
  "resizeCard",
  "moveItem",
  "canMove",
  "removeItem",
  "setHeadingText",
  "setTheme",
  "useWholeScreen",
  "groupOf",
  "pickerGroups",
  "paramFields",
  "singleEntityParam",
  "entityChoices",
  "paramsComplete",
  "pageChoices",
  "hexToRgb",
  "styleDefaults",
  "createHistory",
  "historyPush",
  "historyUndo",
  "historyRedo",
  "historyCloseGroup",
  "canUndo",
  "canRedo",
  "SaveQueue",
  "classifyRemote",
];

test("model module exports the complete public surface", async () => {
  const module = await import(pathToFileURL(modelPath));
  for (const name of modelExpected) {
    assert.equal(Object.hasOwn(module, name), true, `missing export ${name}`);
  }
});

test("every relative frontend import resolves to a file", () => {
  const importPattern = /(?:import|export)\s+(?:[^"'()]*?\s+from\s+)?["'](\.[^"']+)["']/g;

  for (const name of fs.readdirSync(frontend).filter((entry) => entry.endsWith(".js"))) {
    const sourcePath = path.join(frontend, name);
    const source = fs.readFileSync(sourcePath, "utf8");

    for (const match of source.matchAll(importPattern)) {
      const target = path.resolve(path.dirname(sourcePath), match[1]);
      assert.equal(fs.existsSync(target), true, `${name} imports missing ${match[1]}`);
    }
  }
});

test("placement and drag modules export their public surface", async () => {
  const placement = await import(pathToFileURL(path.join(frontend, "placement.js")));
  for (const name of [
    "GRID_COLS", "GRID_ROWS", "SNAP_COLS", "SNAP_ROWS", "MIN_COLS", "MIN_ROWS",
    "rectOfCell", "cellOfRect", "readPosition", "cardCells", "isPlaced", "isEmptyPage",
    "occupied", "canPlace", "freeSlot", "firstFree", "freezePage", "placeCard", "sizeCard",
    "snapMove", "snapSize",
  ]) {
    assert.equal(Object.hasOwn(placement, name), true, `missing export ${name}`);
  }
  const drag = await import(pathToFileURL(path.join(frontend, "drag.js")));
  for (const name of ["START_PX", "HOLD_MS", "followPress"]) {
    assert.equal(Object.hasOwn(drag, name), true, `missing export ${name}`);
  }
});
