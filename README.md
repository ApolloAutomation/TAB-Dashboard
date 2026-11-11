# Apollo TAB Dashboard

A Home Assistant integration for the Apollo TAB-1 wall tablet.

**Status: pre-release.** The goal is to build dashboards in Home Assistant and
show them on TAB-1 tablets. That does not exist yet. This version only finds
your tablets.

## What it does today

- Adds an "Apollo TAB Dashboard" integration that you set up from the UI.
- Finds every TAB-1 that is already set up through the ESPHome integration.
  Tablets you add, remove or rename later are picked up without a restart.
- Adds a diagnostic sensor named "Dashboard engine" to each tablet's device.
  It always reads "Not installed", because no TAB-1 firmware includes the
  dashboard engine yet.
- Provides a diagnostics download that lists the tablets it found.

## What it does not do yet

- It does not send anything to the tablets or change what they display.
- It has no dashboard editor, no cards and no services.

## Requirements

- Home Assistant 2026.11 or newer.
- At least one TAB-1 set up through the ESPHome integration. The integration
  recognises tablets by the firmware's ESPHome project name,
  `ApolloAutomation.TAB-1`.

## Installation

The integration is not in the default Marketplace catalog yet. Add it as a
custom repository:

1. In Home Assistant, open the Marketplace. It must be connected to GitHub
   before a custom repository can be added.
2. Add `https://github.com/ApolloAutomation/TAB-Dashboard` as a custom
   repository of type "Integration".
3. Download "Apollo TAB Dashboard" and restart Home Assistant.

To install by hand, copy `custom_components/apollo_tab` into the
`custom_components` folder of your Home Assistant configuration and restart.

## Setup

1. Go to Settings > Devices & services > Add integration.
2. Search for "Apollo TAB Dashboard" and confirm.

There is nothing to configure. Open a tablet's device page to see its
"Dashboard engine" sensor under Diagnostic.

## Removing

Delete the integration from Settings > Devices & services. This removes the
"Dashboard engine" sensors. Your tablets and their ESPHome entities are not
touched.

## Development

Tests need Python 3.14.

    python3.14 -m venv .venv
    .venv/bin/pip install -r requirements_test.txt
    .venv/bin/ruff check .
    .venv/bin/ruff format --check .
    .venv/bin/pytest

`requirements_test.txt` is a lock file with hashes, generated from
`requirements_test.in` (`uv` is installed by the test requirements). Refresh
it with:

    .venv/bin/uv pip compile --universal --generate-hashes --upgrade --python-version 3.14.2 requirements_test.in -o requirements_test.txt

## Licence

MIT. See [LICENSE](LICENSE).
