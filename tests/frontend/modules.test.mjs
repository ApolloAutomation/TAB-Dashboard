import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "../../custom_components/apollo_tab/frontend");
const logicPath = path.join(frontend, "logic.js");

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
  "gridForSize",
  "sizePreset",
  "pickStubParams",
  "paramsSchema",
  "styleToForm",
  "formToStyle",
  "cleanConfig",
  "feedbackReduce",
  "nextDashboardPath",
  "starterConfig",
  "warningText",
  "warningPlace",
];

test("logic module exports the complete public surface", async () => {
  const module = await import(pathToFileURL(logicPath));
  for (const name of expected) {
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
