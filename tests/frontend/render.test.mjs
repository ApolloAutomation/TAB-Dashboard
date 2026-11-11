import test from "node:test";
import assert from "node:assert";
import {
  cardTokens,
  thermostatFit,
  thermostatText,
} from "../../custom_components/apollo_tab/frontend/render.js";

const midnight = {
  id: "midnight",
  wall: "#101418",
  card: "#181C23",
  card_pr: "#232833",
  card2: "#232833",
  card2_pr: "#303746",
  line: "#2A303A",
  tx: "#E8EAED",
  tx2: "#9AA0A8",
  acc: "#F5B547",
  accf: "#F5B547",
  accf_pr: "#D99A2B",
  acct: "#0E1116",
  acc2: "#6CB4FF",
  onbg: "#33291A",
  onbg_pr: "#4A3A20",
  ontx: "#F7E3BC",
  ion: "#F5B547",
  r: 16,
  r2: 10,
  bw: 0,
};

const mono = {
  id: "mono",
  wall: "#0A0A0A",
  card: "#0A0A0A",
  card2: "#202020",
  line: "#F0F4F0",
  tx: "#F0F4F0",
  tx2: "#A6A6A6",
  acc: "#F0F4F0",
  acct: "#0A0A0A",
  acc2: "#F0F4F0",
  onbg: "#F0F4F0",
  onbg_pr: "#C8CCC8",
  ontx: "#0A0A0A",
  ion: "#0A0A0A",
  r: 8,
  r2: 6,
  bw: 2,
};

test("cardTokens keeps the theme's on colours for a plain style", () => {
  const tokens = cardTokens(mono, {
    onbg: "#F0F4F0",
    acc: "#F0F4F0",
    ontx: "#0A0A0A",
    card2: "#202020",
  });

  assert.equal(tokens.ion, "#0A0A0A");
  assert.equal(tokens.onbg_pr, "#C8CCC8");
});

test("cardTokens works out on colours when an element uses another theme", () => {
  const tokens = cardTokens(midnight, {
    acc: "#F0F4F0",
    onbg: "#F0F4F0",
    ontx: "#0A0A0A",
    card2: "#202020",
  });

  assert.equal(tokens.ion, "#0A0A0A");
  assert.equal(tokens.onbg_pr, "#C7CAC7");
});

test("cardTokens keeps a readable accent as the on icon for a custom style", () => {
  const tokens = cardTokens(midnight, {
    acc: "#F5B547",
    onbg: "#433722",
    ontx: "#E8EAED",
  });

  assert.equal(tokens.ion, "#F5B547");
});

test("cardTokens returns the theme unchanged without a style", () => {
  assert.deepEqual(cardTokens(midnight), { ...midnight });
});

test("thermostatText keeps one decimal below 1000", () => {
  assert.equal(thermostatText(21.5), "21.5");
  assert.equal(thermostatText(21), "21");
  assert.equal(thermostatText(999.94), "999.9");
  assert.equal(thermostatText(-0.04), "0");
  assert.equal(thermostatText(0), "0");
});

test("thermostatText drops decimals from 1000 up", () => {
  assert.equal(thermostatText(1534.3), "1534");
  assert.equal(thermostatText(12345.6), "12346");
  assert.equal(thermostatText(2400), "2400");
  assert.equal(thermostatText(-1234.4), "-1234");
});

test("thermostatFit keeps the full size for short values", () => {
  const size = 212;
  const stroke = Math.max(8, size / 14);
  const fit = thermostatFit("21.5", size, stroke);

  assert.equal(fit.fontSize, size / 5);
});

test("thermostat value text stays inside the arc's inner circle", () => {
  // The energy gauge at its default size and one column wider, and the
  // bundled thermostat.
  const geometries = [
    { w: 152, h: 76 },
    { w: 168, h: 76 },
    { w: 344, h: 212 },
  ];
  const values = [0, 21.5, 999.9, 1534.3, 2400, 12345.6, 20000, 99999.9, -1234.4];
  const texts = [...values.map(thermostatText), "–"];

  const textEm = (text) => {
    let em = 0;
    for (const character of text) {
      em += ".,: ".includes(character) ? 0.32 : 0.62;
    }
    return em;
  };

  for (const geometry of geometries) {
    const size = Math.min(geometry.w, geometry.h);
    const stroke = Math.max(8, size / 14);

    for (const text of texts) {
      const fit = thermostatFit(text, size, stroke);
      const width = fit.fontSize * textEm(text);
      const height = fit.fontSize * 1.2;
      const where = `${geometry.w}x${geometry.h} ${text}`;

      assert.ok(Math.hypot(width, height) <= fit.innerDiameter, `${where} fits inside the circle`);
      assert.ok(width <= fit.maxWidth + 1e-9, `${where} fits within the maximum width`);
      assert.ok(fit.fontSize <= size / 5 + 1e-9, `${where} does not exceed the base size`);
    }
  }

  const size = 76;
  const stroke = Math.max(8, size / 14);
  assert.ok(thermostatFit("12346", size, stroke).fontSize >= 10);
});
