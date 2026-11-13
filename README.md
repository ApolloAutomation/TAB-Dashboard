# Apollo TAB Dashboard

A Home Assistant integration for the Apollo TAB-1 wall tablet.

**Status: pre-release.** You can build, preview and check TAB-1 dashboards in
Home Assistant and choose which dashboard each tablet shows. A tablet shows
its dashboard once its software has the dashboard engine.

## What it does today

- Adds a "TAB-1" panel to the sidebar. It is the one place to build TAB-1
  dashboards, and it works with no tablet connected.
- The panel's editor shows the tablet's screen (1280x800) while you work,
  drawn from the same layout a tablet would receive.
- "Add card" offers only cards the tablet can show: 16 built-in cards, plus
  any community cards you have installed. You pick a card, then the device it
  controls.
- Changes are saved automatically. Undo and redo work while the editor is
  open.
- Cards and pages the tablet cannot show (for example cards added in Home
  Assistant's own editor) are listed as "Not shown on the tablet", each with
  a Remove button and the device it was for. After you remove one, the editor
  offers the TAB-1 cards for that device. Above the picture of the tablet,
  the editor says how many cards on the page are not shown, and "Show me"
  goes to the first one. The list of dashboards counts every page, the same
  pages the editor has, and says how many cards and pages are not shown.
- New dashboards are hidden from Home Assistant's sidebar; the TAB-1 panel
  lists them. They are ordinary Home Assistant dashboards, so the cards also
  work in a browser and control real devices.
- Loads community cards from `<config>/apollo_tab/components/` (see
  "Advanced" in the panel).
- Works out what each tablet screen of every TAB-1 dashboard will show and
  sends it to the tablets that show that dashboard, again after every
  change. You can see it in the diagnostics download.
- Finds every TAB-1 that is already set up through the ESPHome integration.
  Tablets you add, remove or rename later are picked up without a restart.
- Each tablet shows one TAB-1 dashboard. Admins choose it in the panel's
  "Tablets" box or with the "Dashboard" control on the tablet's device page;
  automations can use the "Show dashboard" action. See
  [docs/tablets.md](docs/tablets.md).
- A tablet it sees for the first time gets nothing until an admin turns it
  on with its first dashboard, because any ESPHome device can say it is a
  TAB-1. The panel marks it "New", says which six characters its name on
  its screen ends in (check them before you turn it on), links to its
  device page, and Home Assistant lists it under Repairs. A tablet added to
  ESPHome again needs an admin again. Automations cannot turn on a new
  tablet, nor can add-ons that use their own access to Home Assistant. An
  add-on set up with an admin's long-lived access token acts as that admin
  and can.
- Taps on the tablet control devices with the same rules as the browser,
  when the tablet's ESPHome connection is encrypted.
- Adds a diagnostic sensor named "Dashboard engine" to each tablet's device:
  "Not installed", "Ready" or "Update needed".

## What it does not do yet

- Pictures (camera snapshots, media artwork, people) show as a placeholder
  on the tablet.
- It has no ready-made or automatic dashboards.
- It does not import existing dashboards.
- It has no drag and drop: cards are moved with "Move earlier" and "Move
  later".
- It has no wallpapers, so the Glass theme is flat.
- It does not support "show only when" rules.
- It does not show any card that is not a TAB-1 card or a heading.

## Requirements

- Home Assistant 2026.10 or newer.
- No tablet is needed to build and preview dashboards. Tablet discovery and
  the "Dashboard engine" sensor need at least one TAB-1 set up through the
  ESPHome integration. The integration recognises tablets by the firmware's
  ESPHome project name, `ApolloAutomation.TAB-1`.
- Showing a dashboard on a tablet needs tablet software with the dashboard
  engine. Taps on the tablet also need ESPHome encryption for that tablet.

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
you have a tablet, its device page has a "Dashboard" control under
Configuration and a "Dashboard engine" sensor under Diagnostic.

A browser tab that was already open when you added the integration shows the
TAB-1 panel after a reload.

## Building a dashboard

1. Open "TAB-1" in the sidebar and press "Create a dashboard". You get a
   dashboard with one empty page called Home, and the editor opens.
2. Press "Add card". Pick a card, then pick the device it controls. The card
   appears on the picture of the tablet straight away.
3. Press a card on the picture to change it: the device, the name on the
   card, its size, its theme and colours, and its position. A card's own
   highlight colour is used for its switches, sliders and buttons that are
   on, and tints the card while its device is on. "Remove card" takes it
   away.
4. Press "Add page" for another page, and give it a name and an icon. The
   tablet shows the icons in its side bar. Each icon has a plain name, shown
   when you point at it and read out by screen readers.
5. The theme for the whole dashboard is under "This dashboard". While a
   card is selected, press "Page and dashboard settings", the tab of the
   page you are on, or Escape to get back to it and to the page's name.
6. There is no Save button. The editor shows "Saved" when your last change is
   stored.

Rules of the tablet's screen: cards fill a page from left to right, then top
to bottom; a page that holds more than fits is split into several screens;
pages do not scroll; a screen can show at most 4 graphs, 4 dials and 4
left-to-right colour fades.

To choose which dashboard a tablet shows, pick it under "Shows" next to the
tablet on the panel's Home screen. For a new tablet, pick its first
dashboard and then press "Turn on with this dashboard". See
[docs/tablets.md](docs/tablets.md) for automations and the status words.

If you made a dashboard with version 0.2.0: open it from the TAB-1 panel.
Cards that were added in Home Assistant's own editor and the old "Tablet
preview" page are marked "Not shown on the tablet" and can be removed with
one press. The panel also offers to hide the dashboard from the sidebar. The
"TAB-1 ..." entries are no longer in Home Assistant's card picker.

## Writing in YAML

A TAB-1 dashboard is any dashboard whose configuration has a top-level
`apollo_tab:` mapping, whether it is kept in storage or in a YAML file:

```yaml
apollo_tab:
  version: 1
  theme: midnight
```

A card looks like this:

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
| `theme` | `midnight`, `daylight`, `warm`, `soft`, `mono` or `glass` | use this theme for this card |
| `color` | `#RRGGBB` | card fill |
| `gradient` | `{to: "#RRGGBB", direction: "vertical" or "horizontal"}` | fill runs from the card fill to `to`; `direction` defaults to `vertical` |
| `transparency` | integer 0 to 100 | 0 is solid; 100 is the page background |
| `accent` | `#RRGGBB` | accent colour |

Size in the TAB-1 panel sets `grid_options`: one unit wide is 6 columns and
one unit high is 3 rows.

A dashboard kept in a YAML file can be looked at in the TAB-1 panel but not
changed there.

## Community cards

Put card files (YAML) in `<config>/apollo_tab/components/` (one folder, no
sub-folders), then open Advanced in the TAB-1 panel and press "Look for new
cards", or reload the integration. A bad file is listed there with its error
and does not affect the others.

See [docs/components.md](docs/components.md) for how to write one.

What a card file can and cannot do:

- It can act only on entities you picked for it, and only with a service of
  that entity's own domain, from a fixed list of domains.
- It cannot express `homeassistant.*` services, `script.<name>` shortcuts,
  notifications, shell commands or REST calls.
- In a browser its actions run as the logged-in user, so it can never do
  more than that user may. A tablet has no logged-in user: anyone at the
  tablet can use the cards on it, within the other rules here (see
  [docs/tablets.md](docs/tablets.md)).
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
card file from your folder that controls either one stays switched off until
an administrator allows it under Advanced in the TAB-1 panel. Editing the
file withdraws that permission. Garage, gate and door covers ask for
confirmation on every action, whatever the card file says. The same rules
hold for taps on a tablet.

## Removing

Delete the integration from Settings > Devices & services. This removes the
"Dashboard" controls, the "Dashboard engine" sensors and the TAB-1 panel.
Every tablet it turned on and can reach goes back to its waiting screen, and
the saved choice of dashboard for each tablet is deleted. Your tablets and their ESPHome
entities are not touched otherwise.

Dashboards you created stay in Home Assistant. Their TAB-1 cards show an error
until the integration is back.

## Development

The integration converts every TAB-1 dashboard to layout JSON (schema v1)
whenever it changes and stores the result; the diagnostics download includes
it. The editor's picture of the tablet is drawn from the same conversion of
the unsaved draft (`apollo_tab/layout/preview`).

Tablets are reached through the ESPHome integration's own connection, with
the device actions of the TAB-1 dashboard engine. The wire format is fixed by
the copy of the shared contract in `custom_components/apollo_tab/contract/`;
`tests/contract/` holds the fixtures that the code must reproduce byte for
byte. `tests/fake_tablet.py` is a tablet simulator used by the tests.

Tests need Python 3.14.

    python3.14 -m venv .venv
    .venv/bin/pip install -r requirements_test.txt
    .venv/bin/ruff check .
    .venv/bin/ruff format --check .
    .venv/bin/pytest
    node --test "tests/frontend/*.test.mjs"

The tablet link tests need `aioesphomeapi`. One of them uses ESPHome's own
`RuntimeEntryData`, which needs the requirements of Home Assistant's
`esphome` and `usb` integrations and of the integrations they import and
depend on (`assist_satellite` brings `hassil`, for one); they are not in
`requirements_test.txt`. Without them that test is skipped and says which
module is missing. To install them at the versions the installed Home
Assistant pins, without changing anything already installed:

    .venv/bin/pip freeze > installed.txt
    .venv/bin/python -B .github/scripts/esphome_requirements.py > esphome.txt
    .venv/bin/pip install -c installed.txt -r esphome.txt
    .venv/bin/python -B .github/scripts/esphome_requirements.py --check

The CI workflows do the same and set `APOLLO_TAB_NEED_ESPHOME=1`, which makes
the test fail instead of skipping.

`tests/harness/tablet-shapes.json` describes every websocket message about
tablets. `tests/test_tablet_shapes.py` checks the integration against it and
`tests/frontend/tablet-shapes.test.mjs` checks the panel's mock, so the two
cannot drift apart.

`requirements_test.txt` is a lock file with hashes, generated from
`requirements_test.in` (`uv` is installed by the test requirements). Refresh
it with:

    .venv/bin/uv pip compile --universal --generate-hashes --upgrade --python-version 3.14.2 requirements_test.in -o requirements_test.txt

The frontend can be checked in a browser without Home Assistant, using a
mock and a small local server that runs the real layout converter:

    .venv/bin/python -B tests/harness/server.py --port 8765

Then open `http://127.0.0.1:8765/tests/harness/index.html?view=panel`.
Options: `ha=dark` or `ha=light` (Home Assistant theme), `seed=none`,
`seed=sample` or `seed=real` (which dashboards exist), `night=1` (adds a
second dashboard, "Night"), `tablets=three`, `tablets=no-engine`,
`tablets=new` (one tablet on, one new) or `tablets=all` (mock tablets; `all`
has one for every status),
`route=/edit/tab-1` (which screen opens) and `community=1` (adds a card from
"your folder").
The older views `cards`, `states` and `preview` still work and take a
`theme`: `midnight`, `daylight`, `warm`, `soft`, `mono` or `glass`.

A scripted run of the whole editor in headless Chrome, with screenshots:

    node tests/harness/journey.mjs --out /tmp/tab-journey --python .venv/bin/python

The output folder must be outside the repository.

## Licence

MIT. See [LICENSE](LICENSE).
