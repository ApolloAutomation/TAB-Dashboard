import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "../../custom_components/apollo_tab/frontend");

const banned = [
  "inner" + "HTML",
  "outer" + "HTML",
  "insertAdjacent" + "HTML",
  "document." + "write",
  "ev" + "al(",
  "new " + "Function",
  "setAttribute(" + '"on',
  "setAttribute(" + "'on",
];

const allowedAddresses = new Set([
  "https:" + "//github.com/ApolloAutomation/TAB-Dashboard",
  "http:" + "//www.w3.org/2000/svg",
]);

test("frontend source avoids unsafe browser sinks", () => {
  for (const name of fs.readdirSync(frontend).filter((entry) => entry.endsWith(".js"))) {
    const source = fs.readFileSync(path.join(frontend, name), "utf8");
    for (const value of banned) {
      assert.equal(source.includes(value), false, `${name} contains ${value}`);
    }
  }
});

test("frontend source uses only approved address literals", () => {
  const addressPattern = /https?:\/\/[^\s"'`)]+/g;
  for (const name of fs.readdirSync(frontend).filter((entry) => entry.endsWith(".js"))) {
    const source = fs.readFileSync(path.join(frontend, name), "utf8");
    for (const match of source.match(addressPattern) || []) {
      assert.equal(allowedAddresses.has(match), true, `${name} contains ${match}`);
    }
  }
});
