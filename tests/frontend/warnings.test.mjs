import test from "node:test";
import assert from "node:assert";
import * as logic from "../../custom_components/apollo_tab/frontend/logic.js";

test("warningBoxKind hatches only cards that were left out", () => {
  const expectedKinds = {
    invalid_options: null,
    strategy_not_supported: null,
    view_not_sections: null,
    view_extras_ignored: null,
    columns_differ: null,
    section_not_grid: null,
    nested_section_ignored: null,
    visibility_ignored: null,
    not_tab_element: null,
    unknown_component: null,
    needs_approval: null,
    invalid_card: null,
    params_incomplete: null,
    element_clipped: null,
    card_too_wide: null,
    card_too_tall: null,
    section_split: null,
    over_budget_charts: "omitted",
    over_budget_arcs: "omitted",
    over_budget_gradients: "flat",
    too_many_pages: null,
    too_many_nav: null,
  };

  for (const [code, expected] of Object.entries(expectedKinds)) {
    const warning = {
      code,
      page: "p1",
      r: [100, 80, 376, 184],
    };
    assert.equal(logic.warningBoxKind(warning), expected, code);
  }
});

test("warningBoxKind draws nothing without a rectangle", () => {
  const warnings = [
    { code: "over_budget_charts", r: null },
    { code: "over_budget_charts" },
    { code: "over_budget_charts", r: [100, 80, 376] },
    { code: "over_budget_charts", r: [100, 80, "376", 184] },
    { code: "over_budget_charts", r: [100, 80, Number.NaN, 184] },
    null,
    "x",
  ];

  for (const warning of warnings) {
    assert.equal(logic.warningBoxKind(warning), null);
  }
});

test("warningBoxKind ignores unknown and inherited codes", () => {
  for (const code of ["new_code", "toString", "__proto__", "constructor"]) {
    const warning = {
      code,
      r: [100, 80, 376, 184],
    };
    assert.equal(logic.warningBoxKind(warning), null, code);
  }
});
