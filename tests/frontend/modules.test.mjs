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
