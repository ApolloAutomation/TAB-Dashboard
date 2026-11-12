# Apollo TAB Dashboard

A Home Assistant integration for the Apollo TAB-1 wall tablet.

**Status: pre-release.** You can build, preview and check TAB-1 dashboards in
Home Assistant. **Layouts are not sent to tablets yet**, because no TAB-1
firmware includes the dashboard engine.

## What it does today

- Adds a "TAB-1" sidebar panel with a "Create TAB-1 dashboard" button. It
  works with no tablet connected.
- Adds 16 elements to the dashboard card picker, each with a live preview and
  a visual editor.
- Elements work on the Home Assistant dashboard. They show real entity state
  and control real devices.
- Loads community Components from `<config>/apollo_tab/components/`.
- Shows a tablet preview of each page, with warnings about anything that does
  not fit.
- Converts every TAB-1 dashboard to layout JSON (schema v1) and keeps the
  result, which you can see in the diagnostics download.
- Finds every TAB-1 that is already set up through the ESPHome integration.
  Tablets you add, remove or rename later are picked up without a restart.
- Adds a diagnostic sensor named "Dashboard engine" to each tablet's device.
  It always reads "Not installed", because no TAB-1 firmware includes the
  dashboard engine yet.

## What it does not do yet

- It does not send anything to a tablet or change what a tablet displays.
- It does not import existing dashboards.
- It has no automatic layout.
- It has no wallpapers, so the Glass theme is flat.
- It does not support visibility conditions.
- It does not convert any card that is not a TAB-1 element or a heading.

## Requirements

- Home Assistant 2026.10 or newer.
- No tablet is needed to build and preview dashboards. Tablet discovery and
  the "Dashboard engine" sensor need at least one TAB-1 set up through the
  ESPHome integration. The integration recognises tablets by the firmware's
  ESPHome project name, `ApolloAutomation.TAB-1`.

## Installation

The integration is not in the default Marketplace catalog yet. Add it as a
custom repository:

1. In Home Assistant, open the Marketplace (HACS before 2026.11). It must be
   connected to GitHub before a custom repository can be added.
2. Add `https://github.com/ApolloAutomation/TAB-Dashboard` as a custom
   repository of type "Integration".
3. Download "Apollo TAB Dashboard" and restart Home Assistant.

To install by hand, copy `custom_components/apollo_tab` into the
`custom_components` folder of your Home Assistant configuration and restart.

## Setup

1. Go to Settings > Devices & services > Add integration.
2. Search for "Apollo TAB Dashboard" and confirm.

There is nothing to configure. The "TAB-1" panel appears in the sidebar. If
you have a tablet, open its device page to see its "Dashboard engine" sensor
under Diagnostic.

A browser tab that was already open when you added the integration gets the
elements when you open the TAB-1 panel, or on its next page load.

## Building a dashboard

Everything happens inside Home Assistant:

1. Open the "TAB-1" panel and press "Create TAB-1 dashboard". The new
   dashboard opens in edit mode.
2. Add a card. All 16 starting elements appear by name in the card picker,
   with a live preview.
3. Each element shows real entity state and controls real devices. How a
   control responds while it waits depends on its Component.
4. Open an element's editor to choose its entities, title, size, theme,
   colour, gradient, transparency and accent. Home Assistant's YAML toggle
   works too.
5. To add your own elements, see [Community Components](#community-components).
6. Check the tablet preview, which is in the TAB-1 panel and on the new
   dashboard's "Tablet preview" view. It shows each page at 1280x800
   proportions, drawn from the layout JSON a tablet would receive, with
   warnings. It shows values captured when it loads, refreshed every 30
   seconds and on every dashboard change, so it is not a live stream.
7. The integration converts the dashboard to layout JSON and converts it again
   whenever the dashboard changes.

The theme of the whole dashboard is chosen in the TAB-1 panel.

Layout rules:

- Each view must be a sections view, and each view is one page on the tablet.
- Use 3 columns. Set the view's maximum columns to 3.
- Pages do not scroll.
- A section is never split across pages unless it is taller than a page.
- A page can show at most 4 charts, 4 dials and 4 left-to-right gradients.

## Writing in YAML

A TAB-1 dashboard is any dashboard whose configuration has a top-level
`apollo_tab:` mapping, whether it is kept in storage or in a YAML file:

```yaml
apollo_tab:
  version: 1
  theme: midnight
```

An element looks like this:

```yaml
type: custom:apollo-tab-card
component: apollo/light-slider
params:
  entity: light.kitchen
title: Kitchen                 # optional, at most 60 characters
style:                         # optional
  theme: warm
  color: "#203040"
  gradient: {to: "#101820", direction: vertical}
  transparency: 20
  accent: "#FFB300"
grid_options: {columns: 12, rows: 3}   # Home Assistant's own key
```

All style keys are optional, and any other key is an error:

| Key | Value | Meaning |
|---|---|---|
| `theme` | `midnight`, `daylight`, `warm`, `soft`, `mono` or `glass` | use this theme for this element |
| `color` | `#RRGGBB` | card fill |
| `gradient` | `{to: "#RRGGBB", direction: "vertical" or "horizontal"}` | fill runs from the card fill to `to`; `direction` defaults to `vertical` |
| `transparency` | integer 0 to 100 | 0 is solid; 100 is the page background |
| `accent` | `#RRGGBB` | accent colour |

"Size" in the editor sets `grid_options`, the same value Home Assistant's
Layout tab edits.

## Community Components

Put Component YAML files in `<config>/apollo_tab/components/` (one folder, no
sub-folders), then press "Reload elements" in the TAB-1 panel or reload the
integration. A bad file is listed with its error and does not affect the
others.

See [docs/components.md](docs/components.md) for how to write one.

What a Component can and cannot do:

- It can act only on entities you picked for it, and only with a service of
  that entity's own domain, from a fixed list of domains.
- It cannot express `homeassistant.*` services, `script.<name>` shortcuts,
  notifications, shell commands or REST calls.
- Its actions run as the logged-in user, so it can never do more than that
  user may.
- Its templates run only in Home Assistant's sandboxed template engine, and
  their syntax is checked when the file loads.
- Its files are read with a safe YAML loader, so `!include`, `!secret`,
  `!env_var`, anchors and aliases do not work. Unknown keys are errors, and
  sizes and counts are capped.
- Only that one folder is read. Symlinks and anything that resolves outside
  it are skipped.
- Its images load only from paths on your Home Assistant that start with a
  single `/`. Any other URL is not loaded.

Locks and alarms have extra rules. Every action on a `lock` or
`alarm_control_panel` must ask for confirmation, or the file is rejected. A
Component from your folder that controls either one stays switched off until
an administrator allows it, in the panel or the editor. Editing the file
withdraws that permission. Garage, gate and door covers ask for confirmation
on every action, whatever the Component says.

## Removing

Delete the integration from Settings > Devices & services. This removes the
"Dashboard engine" sensors and the TAB-1 panel. Your tablets and their ESPHome
entities are not touched.

Dashboards you created stay in Home Assistant. Their TAB-1 cards show an error
until the integration is back.

## Development

Tests need Python 3.14.

    python3.14 -m venv .venv
    .venv/bin/pip install -r requirements_test.txt
    .venv/bin/ruff check .
    .venv/bin/ruff format --check .
    .venv/bin/pytest
    node --test "tests/frontend/*.test.mjs"

`requirements_test.txt` is a lock file with hashes, generated from
`requirements_test.in` (`uv` is installed by the test requirements). Refresh
it with:

    .venv/bin/uv pip compile --universal --generate-hashes --upgrade --python-version 3.14.2 requirements_test.in -o requirements_test.txt

The frontend can be checked in a browser without Home Assistant, using a mock
and test fixtures. Serve the repository root:

    python3 -m http.server 8765 --bind 127.0.0.1

Then open
`http://127.0.0.1:8765/tests/harness/index.html?view=cards&theme=midnight`.
The `view` values are `cards`, `states`, `editor`, `preview` and `panel`.
`cards` and `states` take a `theme`: `midnight`, `daylight`, `warm`, `soft`,
`mono` or `glass`.

## Licence

MIT. See [LICENSE](LICENSE).
