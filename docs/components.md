# Writing a card

A card for the TAB-1 tablet is a small YAML file. It says what the card
shows and which devices it controls, and builds the card from the tablet's
own drawing parts. In this guide that file is called a Component, and the
drawing parts are called Types. A card you write draws on the Home
Assistant dashboard, in the TAB-1 panel's picture of the tablet, and on every
tablet that shows the dashboard (see [tablets.md](tablets.md)). Taps on the
tablet follow the same rules as clicks in a browser.

Put your files in `<config>/apollo_tab/components/` (one folder, no
sub-folders), then press "Look for new cards" under Advanced in the TAB-1
panel or reload the integration. A bad file is listed with its error and
does not affect the others.

There are two forms of card file. A file of schema 1, described first, has
one layout and no settings of its own. A file of schema 2 has sizes to pick
from, options the person sets for each card, and knows what each device can
do; the built-in cards that came with version 0.5.0 are written in it. See
[Schema 2 cards](#schema-2-cards). Both forms work on every tablet: one
with older software shows a schema 2 card in a simpler form (see
[What a tablet with older software shows](#what-a-tablet-with-older-software-shows)).

## File structure

One YAML document is one Component. A file may hold several documents
separated by `---`. These are all the keys, and any other key is an error.

```yaml
schema: 1                      # optional, must be 1
id: community/light-tile       # required
version: 1.0.0                 # required, a string
name: Light tile               # required
description: Turn a light on or off.   # optional
icon: mdi:lightbulb            # optional
header: true                   # optional, default true: icon and title row
size: 1x1                      # required, WxH in units
params: {}                     # optional
inputs: {}                     # optional
outputs: {}                    # optional
layout: []                     # required, 1 to 16 items
preview: {params: {}, inputs: {}}   # optional example values
```

| Field | Rule |
|---|---|
| `id` | Two parts, `namespace/name`, each made of lower-case letters and digits with single hyphens between them. At most 64 characters. The `apollo/` namespace is kept for built-in files. Use any other namespace. |
| `version` | Three numbers, such as `1.0.0`. |
| `name` | 1 to 40 characters. |
| `description` | At most 160 characters. |
| `icon` | `mdi:` followed by lower-case letters, digits and hyphens. |
| `size` | `WxH`, with W from 1 to 6 and H from 1 to 4. One unit wide is 6 sub-grid columns. One unit high is 3 rows. |
| names | Every param, input, output and `as` name starts with a lower-case letter, then uses lower-case letters, digits and underscores, up to 32 characters. Params, inputs and `as` names must all differ from one another. None of these names may be `value`, `response` or `component_name`. |
| strings | Any template or text is at most 1024 characters. |

YAML reads unquoted `on`, `off`, `yes` and `no` as booleans, so quote them when
you mean the word: `state: "on"`.

## Params

Params are what the user fills in when placing the card. A Component has at
most 8. Each one is one of these:

```yaml
entity:   {domain: light}                  # one entity of that domain, required
scenes:   {domain: scene, multiple: true}  # a list of 1 to 8 entities, required
max:      {type: number, default: 5000, min: 0, max: 100000}   # min and max optional
page:     {type: page}                     # optional view path, e.g. "kitchen"
```

A number param must have a `default`.

## Inputs

Inputs are the live values the card reads. A Component has at most 16. Each
one is one of these:

```yaml
state: "{{ states(entity) }}"              # a template string
history: {source: recorder, entity: "{{ entity }}", hours: 24}     # hours 1 to 168, default 24
snapshot: {source: camera, entity: "{{ entity }}", refresh: 10s}   # refresh 5 s to 1 h, default 10 s
forecast:                                  # a read-only action with a response
  action: weather.get_forecasts
  data: {entity_id: "{{ entity }}", type: daily}
  result: "{{ response[entity].forecast[:5] | map(attribute='temperature') | list }}"
  refresh: 30min                           # 60 s to 24 h, default 30 min
```

- `entity` and `data.entity_id` must be exactly `{{ name }}`, naming a
  single-entity param.
- A duration is a whole number of seconds, or a number followed by `s`, `min`
  or `h`.
- The only action an input can use is `weather.get_forecasts`, and its param
  must be a `weather` entity. Other `data` values are plain values, not
  templates. `result` is required. It sees the params and `response`.
- A template input can use params and the template inputs declared before it.
- History and forecast inputs produce lists of numbers. They can feed only a
  chart, as its bare `value`.

### How inputs are typed inside other templates

If an input's whole source is a single `{{ ... }}` expression, it keeps its
type, so a number stays a number. Anything else, such as text mixed with an
expression, is text with the surrounding whitespace removed.

For example, take `text: "{{ brightness }}%"` with this input:

```yaml
brightness: "{{ state_attr(entity, 'brightness') | int(0) * 100 // 255 }}"
```

It shows `0%` while the entity is missing and `80%` once the light reports a
brightness of 204.

In templates, a missing entity gives `states(e) == "unknown"` and
`state_attr(e, a) is none`. The card also shows "Not found in Home
Assistant".

## Outputs

Outputs are what the card can do. A Component has at most 12. Each one is
one of these:

```yaml
toggle:
  action: light.toggle                     # <domain>.<service>
  data: {entity_id: "{{ entity }}", brightness_pct: "{{ value }}"}
  feedback: optimistic                     # optimistic, pulse, progress or confirm, required
open_details: {local: open_details}        # open_details, open_live or go_to_page
go_to_page: {local: go_to_page, page: "{{ page }}"}
```

- The action must be in the list of
  [allowed services](#allowed-services), the same list for both schemas.
  Its domain is one of: `alarm_control_panel`, `button`,
  `climate`, `cover`, `fan`, `humidifier`, `input_boolean`, `input_button`,
  `input_number`, `input_select`, `light`, `lock`, `media_player`, `number`,
  `scene`, `script`, `select`, `siren`, `switch`, `vacuum`, `valve`,
  `water_heater`.
- A `script` output may use only `script.turn_on`, `script.turn_off` or
  `script.toggle`. Every script is also a service of its own,
  `script.<name>`, which would run that script whatever entity was picked,
  so those services are not allowed.
- `data.entity_id` is required and must be exactly `{{ name }}`. The name is
  either a single-entity param, or the `as` name of the `for_each` items that
  use this output, where the loop is over a multiple-entity param. That param's
  domain must equal the action's domain.
- Other `data` keys (at most 8) hold a string, number or boolean. Lists and
  mappings are not allowed. Strings may be templates. Those templates see the
  params, the loop variable and `value`, the control's new value. In a
  schema 1 file they do not see inputs: an input template can read any
  state, and its value in service data could carry it out of the house. A
  schema 2 output may name the inputs it needs, each with a type (see
  [Inputs in data](#inputs-in-data)).
- Every output on `lock` or `alarm_control_panel` must use `feedback: confirm`.
  A Component with such an output, loaded from your folder, stays switched off
  until an administrator allows it.
- `page` for `go_to_page` is a literal view path or exactly `{{ name }}` of a
  page param.

### Feedback policies

| Policy | What the control does | Use it for |
|---|---|---|
| `optimistic` | A control with a value shows the new value at once and waits up to 5 seconds for Home Assistant to report it. A button gives a 0.6 second pulse. | Things that respond quickly, such as lights, switches, fans and media players. |
| `pulse` | Gives a 0.6 second pulse and claims nothing about state. | One-shot actions with no state to show, such as scenes. |
| `progress` | Shows the requested value and a "Waiting for Home Assistant" hint for up to 30 seconds, until the real value arrives. | Slow devices, such as covers and climate. |
| `confirm` | Asks first in a dialog, shows a busy state for up to 10 seconds, and never shows a new state before Home Assistant sends it. | Anything where a wrong tap matters. Required for locks and alarms. |

A failed call shows an error over the bottom edge of the card for 3 seconds. A
slider sends at most one call every 200 ms while it is dragged, and always one
when it is released. Garage, gate and door covers ask for confirmation on every
action, whatever the Component says.

## Layout

A Component has 1 to 16 layout items. Each item has a `type` and the keys of
that Type:

| Type | Required | Optional (default) |
|---|---|---|
| `switch` | `value` | `on_tap` |
| `slider` | `value` | `min` (0), `max` (100), `step` (1), `on_change` |
| `thermostat` | `value` | `min` (0), `max` (100), `step` (0.5), `on_change`, `side` |
| `chart` | `value` | `kind`: `line` or `bars` (`line`), `side` |
| `button` | `on_tap`, and `text` or `icon` or both | `confirm` |
| `label` | `text` | `size`: `s`, `m` or `l` (`m`), `on_tap`, `confirm` |
| `image` | `value` | `on_tap`, `confirm`, `side` |

Any item may also have `for_each: <multiple-entity param>` together with
`as: <name>`. It is repeated once per entity, with `<name>` set to the entity
id. At most 8 entities are used, and a card has at most 32 widgets. Anything
beyond that is cut, with the warning that part of the card does not fit.

- `value` is the bare name of an input, or a template (it contains `{{` or
  `{%`).
- `min`, `max` and `step` are numbers or templates.
- `text` and `confirm` are strings, plain or template.
- `icon` is an `mdi:` name and is never a template.
- `on_tap` and `on_change` name an output. `on_change` needs an action output.
  `confirm` needs `on_tap`.
- `side: true` asks for a square column on the left of the card.
- A switch is on when its value is true, a non-zero number, or one of the
  strings `on`, `true`, `yes` or `1`, in upper or lower case.
- An image is shown if its value is an `mdi:` icon name or a path starting with
  a single `/`. Anything else shows a placeholder.

## Preview

`preview` gives example values for the TAB-1 panel's card picker and for a
card whose entities are not chosen yet. `preview.params` maps param names to
values of the param's type. `preview.inputs` maps input names to a string,
number, boolean or list of numbers.

## Templates

Templates run in Home Assistant's template engine. The limits below are
checked while a template runs, not guessed from its text. Ordinary templates
are unaffected: `states()`, `state_attr()`, `expand()`, filters such as `int`,
`float`, `round`, `replace`, `join`, `map`, `selectattr`, `list` and `count`,
loops over a handful of entities, and repeating short text with `*` all work
as before.

### Not available in Components

A template that uses one of these is rejected with `bad_template` when the
file loads:

- `{% macro %}`, `{% call %}`, `{% import %}`, `{% from ... import %}`,
  `{% include %}`, `{% extends %}`, `{% block %}` and recursive loops
  (`for ... recursive`).
- The filters `regex_match`, `regex_search`, `regex_replace`,
  `regex_findall`, `regex_findall_index`, `format`, `pack`, `unpack`, `apply`
  and `as_function`; the tests `match`, `search` and `apply`; and the
  functions `lipsum`, `pack`, `unpack`, `apply` and `as_function`.
- The text methods `.format()`, `.format_map()`, `.translate()` and
  `.expandtabs()`.

Regular expressions can take exponential time in a single step that nothing
can interrupt; the others build text or bytes whose size comes from an
argument, or call functions directly past the checks.

### Limits while a template runs

Each loop item, operator, filter, test and function call is one step.

| What | Limit |
|---|---|
| Steps per render | 20000 |
| Time per render | 0.1 seconds |
| Any value (text, list or mapping, counted through nested lists and mappings) | 32768 characters or items |
| Output | 32768 characters |
| Numbers produced by `*`, `+` and `**` | 1024 bits |
| `range()` | 32768 numbers |

`%` with text on the left (printf-style formatting) is not allowed; `%` on
numbers works. The `sum` filter needs a number to start from, so summing lists
or text is not allowed.

### When a template hits a limit

A template that hits a limit gives an error for that value only: the card
shows a dash in that place, and the error names the limit, for example
`RenderLimitError: rendering needed more than 20000 steps`. The rest of the
card keeps working.

A live value is switched off when it runs out of steps, when it runs out of
time or takes longer than 0.2 seconds three times within a minute, or when it
uses more than 1 second of rendering within 10 seconds. A single slow render
does not switch it off, because a busy Home Assistant can delay any render. A
switched-off value shows the error `switched off: ...` and is not updated. This
applies to that template with those settings only, so the same card with
another entity keeps working. It is tried again after 5 minutes, when the
cards are reloaded ("Look for new cards" under Advanced in the TAB-1 panel,
or reloading the integration), or when Home Assistant restarts.

Identical live values are worked out once and shared between all open cards.
One browser connection can have at most 100 live card subscriptions; the
dashboard shares identical cards, so a normal dashboard stays far below this.

## Limits

| What | Limit |
|---|---|
| File size | 32768 bytes |
| Documents per file | 20 |
| Files in your folder | 200 |
| Components in total | 200 |
| Params | 8 |
| Inputs | 16 |
| Outputs | 12 |
| Layout items | 16 |
| `data` keys per output | 8 |
| Text or template | 1024 characters |
| Entities used by `for_each` | 8 |
| Widgets per card | 32 |

## Worked example: light with slider

```yaml
schema: 1
id: community/light-slider
version: 1.0.0
name: Light with slider
description: A light switch with a brightness slider.
icon: mdi:lightbulb-on
size: 2x1
params:
  entity:
    domain: light
inputs:
  state: "{{ states(entity) }}"
  brightness: "{{ state_attr(entity, 'brightness') | int(0) * 100 // 255 }}"
  rgb_color: "{{ state_attr(entity, 'rgb_color') or '' }}"
outputs:
  toggle:
    action: light.toggle
    data:
      entity_id: "{{ entity }}"
    feedback: optimistic
  set_brightness:
    action: light.turn_on
    data:
      entity_id: "{{ entity }}"
      brightness_pct: "{{ value }}"
    feedback: optimistic
layout:
  - type: switch
    value: state
    on_tap: toggle
  - type: slider
    value: brightness
    min: 0
    max: 100
    on_change: set_brightness
  - type: label
    text: "{{ brightness }}%"
preview:
  inputs:
    state: "on"
    brightness: 68
```

This is the built-in `apollo/light-slider` under a namespace you are allowed to
use.

- `params` asks the user for one `light`. The name `entity` is then available
  in every template.
- `inputs` turn Home Assistant state into values for the widgets. `state` is
  the on or off text for the switch. `brightness` converts the 0 to 255
  attribute to a percentage.
- `outputs` are the two things the card can do. In `set_brightness`, `value`
  is the slider's new position. Both use `optimistic` because lights respond
  quickly.
- `layout` places a switch driven by `state`, a slider driven by `brightness`,
  and a label showing the percentage. The label uses a template, the other two
  use the bare input name.
- `preview` gives the TAB-1 panel's card picker something sensible to show.
  `"on"` is quoted so that YAML does not read it as a boolean.

## The built-in Thermostat

`apollo/thermostat` sets one target temperature. Its dial takes the range and
step from the climate entity (`min_temp`, `max_temp` and `target_temp_step`),
so it works in °C and °F. It cannot control a thermostat in a mode with a low
and a high target, such as `heat_cool`: an output always sends the same data
keys, so it cannot switch between `temperature` and `target_temp_low` with
`target_temp_high`. In such a mode the dial has no single target to show and
Home Assistant refuses the call.

## Schema 2 cards

A file that starts with `schema: 2` describes a card the person can set up
for each place they put it: a size (a variant), options such as "show the
brightness bar", and what the card shows when the device can or cannot do
something. Everything in the schema 1 sections above about names,
templates, the sandbox and feedback holds here too, unless this section
says otherwise. Any key that is not named here is an error.

### File structure

```yaml
schema: 2                         # required
id: community/light               # required, as in schema 1
version: 1.0.0                    # required
name: Light                       # required, 1 to 40 characters
description: Turn a light on or off, dim it and change its colour.
icon: mdi:lightbulb               # a level 1 icon (see below)
group: lights                     # picker group, default more
replaces: [apollo/light-tile]     # built-in files only
v1: apollo/light-slider           # what a tablet with older software gets

params: {}                        # devices and pages
options: {}                       # what the person switches on, picks or types
inputs: {}                        # live values
outputs: {}                       # what a touch does

on: is_on                         # an input or template: when the card is lit
tint: colour                      # an input or template that gives a colour
state: state                      # the state line of the tile and chip headers
unavailable: gone                 # default: the first device is unavailable
lit: fill                         # fill, icon, outline or none; default fill
tap: {default: toggle, choices: {}}   # what a tap on the card may do
hold: detail                      # detail or none

parts: {}                         # named layout items, used by the variants
variants: {}                      # named layouts, each with a size
detail: full                      # the variant shown on the card's controls page
notes: []                         # lines at the top of the card's form
preview: {params: {}, options: {}, can: {}, inputs: {}}
```

- `group` is one of `lights`, `climate`, `covers`, `security`, `media`,
  `sensors`, `home` and `more`.
- `replaces` lists 1 to 8 cards this one takes the place of in the picker.
  Only built-in files may carry it; a file from your folder that has it is
  refused with `replaces_not_allowed`. Otherwise a stranger's file could
  hide the built-in cards and take their place on your dashboards.
- `v1` names a schema 1 card that is loaded, or is `note`. A `v1` that
  names a card that is not loaded is refused with `unknown_v1`. It is the
  default for the variants; a variant can have its own.
- `on`, `tint`, `state` and `unavailable` are the name of an input, or a
  template. YAML reads an unquoted key `on:` as true; at the top of a card
  file it is read as `on`.
- `hold: detail` lets a hold on the card open its controls page. It is the
  default when the file has a `detail` variant, and needs one.
- `notes` holds up to 4 lines for the card's form, each `{text, when}`,
  with text of up to 120 characters. A note shows when its `when` holds.
- `preview` gives example values for the picker and for a card whose
  devices are not picked yet: `params`, `options`, `can` (facts, see
  below) and `inputs`.
- A file may skip `variants` and write one layout at the top instead, with
  `layout` and `size` (as in schema 1, `WxH`), and `header`, `trailing` and
  `align` if it needs them. It then has one variant, `default`.

Names follow the schema 1 rule. `can`, `has`, `tablet`, `option`, `value`,
`response` and `component_name` are reserved.

### Params

Schema 1's three kinds stay. An entity param has these keys:

| Key | Meaning |
|---|---|
| `domain` | One kind, a list of kinds such as `[switch, input_boolean]`, or `any`. An output reaches a param with several kinds only through an action per kind. |
| `device_class` | A list that narrows the picker in the form, such as `[door, window]`. |
| `optional` | `true`: the card works without it. `has.<param>` is then false, and items that use it need `when: [has.<param>]`. |
| `multiple`, `max` | Several devices, up to `max` (16 at most, 8 when left out). |
| `label`, `help` | Plain words for the form, at most 40 and 120 characters. |

A number param has `type: number`, `default` and optional `min` and `max`;
a page param has `type: page` and may be `optional`. Both may have `label`
and `help`.

### Options

```yaml
options:
  show_brightness: {type: toggle, section: controls, label: Brightness, default: true,
                    needs: can.brightness, needs_text: This light cannot be dimmed}
  colour_control:  {type: choice, section: controls, label: Colour, default: bar,
                    choices: {none: "Off", bar: Colour bar, both: Both}}
  favourites:      {type: colours, section: controls, label: Favourite colours, max: 8,
                    default: ["#FF453A", "2700K"], when: [colour_control=both]}
  effects_shown:   {type: choice, multiple: true, max: 8, from: can.effect_list,
                    default_first: 4, section: controls, label: Effects}
```

Every option has `type`, `section` (`shows`, `controls` or `look`, where
the form puts it) and `label`, and may have `help`, `default`, `when`, and
`needs` with `needs_text`. A card has at most 16 options.

| `type` | Value | Its own keys |
|---|---|---|
| `toggle` | true or false | |
| `choice` | one of the keys of `choices` (2 to 8, key to label); with `multiple: true` a list of at most `max` | `choices`, or `from: can.<list>` (the device's own list) with `default_first: n`; `multiple`, `max` |
| `number` | a number | `min`, `max`, `step`, `unit` |
| `text` | plain text of at most `max` characters (40 at most) | `max` |
| `icon` | an `mdi:` name | |
| `colour` | `#RRGGBB`, or a role: `accent`, `accent2`, `good`, `warn`, `bad`, `info`, `text`, `muted` | |
| `colours` | a list of at most `max` (8 at most); an entry may be `"2700K"`, a white of that warmth | `max` |

- `needs` names a fact. Where it is false, the option counts as off (a
  toggle), as its first choice, or as an empty list, and the form shows it
  switched off with `needs_text`.
- An option value is data, never a template: a text option that holds
  `{{ 1/0 }}` shows those characters. Each stored value is checked every
  time it is used (its type, range, length, and for a choice that it is
  one of the keys, or still in the device's list). A value that fails is
  dropped and the default counts. An option name the file no longer has
  is ignored, so a card never vanishes because its file changed.

A card stores its options beside its params, only where they differ from
the default, and its size as `variant`:

```yaml
type: custom:apollo-tab-card
component: community/light
params: {entity: light.sofa}
options: {colour_control: both, icon: "mdi:floor-lamp"}
variant: wide             # optional: else the largest variant that fits the card's size
```

Every schema 2 card also has these standard options, without writing
them: the name on the card (`title`), `icon` (default: the device's own
icon, else the file's), `tap` and `tap_page` (from the file's `tap`
choices, plus "Goes to a page"), `hold` (only with a `detail` variant),
`ask` (ask before a card tap acts), and in the card's `style` the keys
`lit` and `tint` beside the shared look keys (see the README).

### Facts: what the device can do

Home Assistant works out what each device can do from its entity registry
entry and its state. A card file reads these facts as `can.<fact>` for its
first entity param, and `can.<param>.<fact>` for another. For a param
with several devices `can.<param>` is a list in the param's order, and a
loop over that param also gets `<as>_can`, the facts of the current
device.

| Domain | Yes or no | Lists and numbers |
|---|---|---|
| any | `toggle` (the card may call the domain's toggle) | `icon`, `kind` (the device class) |
| light | `brightness`, `colour`, `temperature`, `effects` | `min_kelvin`, `max_kelvin`, `effect_list` |
| cover | `position`, `stop`, `tilt`, `asks` (garage, gate, door) | |
| climate | `target`, `range`, `off` | `modes`, `presets`, `fan_modes`, `min`, `max`, `step` |
| fan | `speed`, `oscillate`, `direction` | `presets`, `step` |
| media_player | `pause`, `previous`, `next`, `volume`, `mute`, `seek`, `power`, `shuffle`, `repeat`, `group` | `sources` |
| alarm_control_panel | `home`, `away`, `night`, `vacation`, `needs_code` | |
| lock | `open` | |
| select, input_select | | `options` |
| number, input_number | | `min`, `max`, `step`, `unit` |
| vacuum | `start`, `pause`, `stop`, `dock`, `locate` | `fan_speeds` |

A colour temperature outside 1500 to 10000 K, or a pair that is not
low before high, becomes 2000 and 6500 K. Lists hold up to 64 entries.
Every entry is data: a light that reports an effect named
`{{ states('lock.front') }}` gets a button with that text.

### `when`: parts that are there or not

```yaml
- {use: hue, when: [can.colour, colour_control=bar|both, tablet.v2]}
```

`when` is a list of up to 6 terms, and all must hold. A term is `name`,
`!name`, `name=a|b` or `name!=a`. A name is an option (a toggle that is on,
or a choice, text or list that is not empty and not `none`), a fact
(`can.<what>`, true or a list that is not empty), `has.<param>` (an
optional param has a value), or `tablet.v2`: the layout is made for a
tablet with the newer software. The editor and the browser count as such a
tablet. A `when` is decided when the dashboard is converted, so a part that
is left out leaves no hole.

For a part that comes and goes with a live value, use `visible: <input or
template>` instead. Its place stays reserved, so put such parts in a
`swap`.

### Variants and parts

```yaml
parts:
  dim: {type: slider, look: bar, value: pct, min: 1, max: 100, on_change: set_brightness,
        when: [can.brightness, show_brightness]}
variants:
  tile: {name: Tile, grid: [6, 3], header: tile_v, trailing: level, layout: [{use: dim}]}
  wide: {name: Wide, grid: [12, 3], header: tile, trailing: switch, layout: [{use: dim}]}
  full: {name: Controls, grid: [18, 11], header: tile, picker: false, layout: [{use: dim, height: 56}]}
detail: full
```

- A variant has `name`, `grid` (`[columns, rows]` on the page's grid of 36
  by 12), `header`, `trailing`, `layout` (1 to 24 items), and may have
  `v1`, `picker: false` (not offered in the picker, for a controls page)
  and `align: top` (spare height goes below the rows instead of above).
  A card has 1 to 6 variants.
- The card is drawn in the variant the person picked, else the largest one
  that fits its size. Rows that do not fit are dropped from the end.
- `detail` names the variant of the card's controls page. Home Assistant
  adds that page to the tablet for a card that can open it: by a hold, by
  the tap choice `detail`, or by an item with `on_tap: detail`. On the
  controls page `on_tap: back` goes back.
- `parts` (up to 32) are named items. `{use: dim, height: 56}` puts one in
  and adds or replaces keys, but not its `type`; a `when` on the `use` line
  is added to the part's own. A part may not hold `use`.

Header forms, each drawn from ordinary parts:

| `header` | Draws |
|---|---|
| `title` | The schema 1 header: icon, title, a switch at the right from 300 px width. The default |
| `chip` | Icon, name, and the state at the right. The only form for a card one row high, besides `none` |
| `tile` | A badge, the name over the state, then the `trailing` part |
| `tile_v` | The badge at the top left and the `trailing` part at the top right, the name and state under them |
| `none` | Nothing |

`trailing` is for the tile forms: `switch` (the card's `on` with its tap
output; it needs `on`), `more` (a button that opens the controls page; it
needs `detail`), the name of an input (a short text), or `none`.

### Containers and loops

| Item | Does |
|---|---|
| `{type: row, items: [...]}` | Up to 8 widgets side by side. Inside a row a widget may have `width` (px) or `weight` (1 to 12). A row holds widgets only. |
| `{type: swap, items: [...]}` | 2 to 8 items that share one place; each needs `visible`. An item is a widget or a row. For "Lock" or "Unlock", "Start" or "Pause". |
| `{type: space}` | Takes spare height. |

Any item may have `height` (px) or `grow: true`. `for_each` repeats an
item or a row; `as` names the current entry, and `per_row: n` sets how many
copies share a row. `for_each` may name a param with several devices, a
list fact (`can.modes`), a `colours` option, a `choice` option with
`multiple`, or a list written in the file. A loop makes at most 16 copies
and may not hold a loop, and a card has at most 48 widgets after its loops,
not counting its header. Loading stops at the 49th, so no file can make
loading slow.

### Layout items

The seven types of schema 1 take new keys, and there is one new type,
`choice`. Every widget may have `when`, `visible`, `vars` (constants
handed to the output it calls), `height`, `grow`, `width`, `weight`,
`for_each`, `as`, `per_row` and `use`; all but `choice` may have `colour`
(an input, a template, `#RRGGBB` or a role); a label, button, switch,
chart or image may have `on_hold: detail`.

| Type | New keys |
|---|---|
| `label` | `size`: `s`, `m`, `ml`, `l`, `xl`, `xxl` or `huge` (14 to 192 px); `align`: `left`, `centre` or `right`; `clock`: `24` or `12`, with `value` (minutes after midnight) |
| `button` | `selected` (an input or template); `icon_live` (an input or template, with `icon` as the fixed one); `shape`: `box`, `round` or `bare`; `big_icon: true` |
| `switch` | `colour` |
| `slider` | `look`: `knob` or `bar`; `direction`: `right`, `up` or `down`; `track`: `hue`, `{kelvin: [low, high]}` or a list of up to 8 colours; `icon`; `keep_active: true`; `rate` (an input or template: how much the value grows each second, for a progress bar that moves by itself) |
| `thermostat` | `mark`; `buttons`: 36 to 64 px |
| `chart` | `kind`: `line`, `steps` or `bars`; `mark` |
| `image` | `look`: `box`, `badge` or `bare` |
| `choice` | `value` (an input that gives the index), `options` (a list of `{value, text, icon, colour}`, up to 16, or a list fact, or a `colours` or multiple `choice` option), `rows`, `look`: `cells` or `dots`, `on_change`, `confirm` |

`track: hue` is the colour wheel, `track: {kelvin: [low, high]}` runs from
warm to cool white. `min`, `max` and `step` that come from a fact, an
option or a param are fixed in the layout, so Home Assistant can check a
value the tablet sends against them.

### Constants and templates

Whether a field is a template is decided once, on the file's own text:

| In the file | Becomes |
|---|---|
| Plain text, a number, yes or no | A constant |
| Exactly `{{ name }}` or `{{ name.key }}`, where `name` is `can`, an option, a `vars` name or a loop over a fact, an option or a list in the file | A constant, looked up when the layout is made. No template runs |
| Any other text with `{{` or `{%`; the name of an input | A live value, worked out by Home Assistant's sandboxed template engine |

Everything that is not the file's own text is data: option values, facts,
names a device reports, loop entries, `vars` and titles. It reaches a
template only as a variable, and the layout only as a constant.

### Inputs

A card has at most 32 inputs. Schema 1's forms stay, and these are new:

```yaml
colour:   {source: colour, entity: "{{ entity }}", of: rgb}   # or of: hue, the hue at full strength
icon:     {source: state_icon, entity: "{{ entity }}"}        # the icon for its kind and state
now:      {source: clock}                                     # minutes after midnight
played:   {source: media_position, entity: "{{ entity }}"}    # seconds played, now
low:      {source: statistics, entity: "{{ entity }}", stat: min, hours: 24}   # min, max or mean
by_hour:  {source: statistics, entity: "{{ entity }}", buckets: hour, period: today, stat: mean}
```

- `entity` is exactly `{{ name }}` of an entity param, or of a loop over
  one.
- `clock` and `media_position` are worked out each time Home Assistant
  sends values, so the tablet's clock and progress bar stay right.
- A `statistics` input gives one number over the last `hours` (1 to 168,
  default 24), or with `buckets: hour` the 24 hours of today (`mean` or
  `sum`; hours still to come are left out).

### Outputs

A card has at most 16 outputs. As in schema 1 an output has `action`,
`data` and `feedback`, or `local`. New:

- `action` may be one service per kind, for a param with several kinds:
  `action: {switch: switch.toggle, input_boolean: input_boolean.toggle}`.
  Each key is a kind of the param and the domain of its service. A device
  of a kind that has no entry gets no action, and the item or tap choice is
  left out for it.
- `local: detail` opens the card's controls page and `local: back` goes
  back; `open_details`, `open_live` and `go_to_page` stay.
- `data.entity_id` may name a param with several devices, a loop name, or
  an `entities` input in `uses`. After the template it is one entity id or
  a list of 1 to 16, each a device the card was set up with and of the
  service's domain. Anything else is refused.
- A list as a data value is allowed only for the colour keys `hs_color`,
  `rgb_color`, `rgbw_color`, `rgbww_color` and `xy_color`; each entry must
  end as a number. A mapping is never allowed.
- A data template may use the params, the options, `can`, the item's
  `vars`, loop names, `value`, `option` (for a `choice`: the option the
  tablet picked, from Home Assistant's own copy of the list) and the inputs
  its output lists in `uses`. The filter `rgb` turns a colour into
  `[r, g, b]`.
- Exactly `{{ name }}` or `{{ name.key }}`, with at most one of the filters
  `int`, `float`, `round` and `rgb`, passes the value with its own type.
  Any other template gives text; a plain decimal number in it becomes a
  number and `True` or `False` yes or no. A key whose value is none or
  empty text is left out of the call (never `entity_id`).

#### Inputs in data

An output lists the inputs its data may read, each with a type:

```yaml
set_hue:
  action: light.turn_on
  uses: {sat: number}
  data: {entity_id: "{{ entity }}", hs_color: ["{{ value }}", "{{ sat if sat is number else 100 }}"]}
  feedback: optimistic
```

The type is `number`, `bool` or `entities`. The value is Home Assistant's
own last value of that input, never one a browser or tablet sends. A
template that names a `number` or `bool` input must give a number or yes or
no. An `entities` input may only be `entity_id`. A data template that names
an input its output does not list is refused when the file loads. A file
from your folder that has `uses` needs an admin's approval, as a lock card
does.

#### Allowed services

Every action, in files of both schemas, must be one of these:

| Domain | Services |
|---|---|
| `alarm_control_panel` | `alarm_arm_home`, `alarm_arm_away`, `alarm_arm_night`, `alarm_arm_vacation`, `alarm_arm_custom_bypass`, `alarm_disarm` |
| `button`, `input_button` | `press` |
| `climate` | `set_temperature`, `set_hvac_mode`, `set_preset_mode`, `set_fan_mode`, `set_swing_mode`, `set_humidity`, `turn_on`, `turn_off`, `toggle` |
| `cover` | `open_cover`, `close_cover`, `stop_cover`, `toggle`, `set_cover_position`, `open_cover_tilt`, `close_cover_tilt`, `stop_cover_tilt`, `set_cover_tilt_position` |
| `fan` | `turn_on`, `turn_off`, `toggle`, `set_percentage`, `set_preset_mode`, `oscillate`, `set_direction` |
| `humidifier` | `turn_on`, `turn_off`, `toggle`, `set_humidity`, `set_mode` |
| `input_boolean`, `switch`, `siren` | `turn_on`, `turn_off`, `toggle` |
| `input_number`, `number` | `set_value` |
| `input_select`, `select` | `select_option`, `select_next`, `select_previous` |
| `light` | `turn_on`, `turn_off`, `toggle` |
| `lock` | `lock`, `unlock`, `open` |
| `media_player` | `turn_on`, `turn_off`, `toggle`, `media_play`, `media_pause`, `media_play_pause`, `media_stop`, `media_next_track`, `media_previous_track`, `volume_set`, `volume_mute`, `media_seek`, `select_source`, `shuffle_set`, `repeat_set` |
| `scene` | `turn_on` |
| `script` | `turn_on`, `turn_off`, `toggle` |
| `vacuum` | `start`, `pause`, `stop`, `return_to_base`, `locate`, `set_fan_speed` |
| `valve` | `open_valve`, `close_valve`, `stop_valve`, `toggle`, `set_valve_position` |
| `water_heater` | `set_temperature`, `set_operation_mode`, `turn_on`, `turn_off` |

Left out on purpose: services that take no `entity_id`, services whose
data names other entities (`scene.apply`, `media_player.join`), and those
that take a free address or command (`media_player.play_media`,
`vacuum.send_command`).

#### A tap on the card

```yaml
tap:
  default: toggle
  choices:
    toggle: {label: Turns it on or off, output: toggle, needs: can.toggle}
    detail: {label: Opens its controls}
    none:   {label: Does nothing}
```

`tap` has `default` and 1 to 6 `choices`, each with `label` and an
`output` (`detail` and `none` need none), and optional `needs`: a fact
without which the choice is not offered. The person picks one in the
form; "Goes to a page" is always added. A lock or an alarm may not be a
card tap. A card tap that would move a garage door, gate or door is left
out when the dashboard is converted, with a warning, so a wipe over a tile
never opens a question.

### What a tablet with older software shows

A tablet with the first dashboard software (engine 0.1.0) gets, for each
schema 2 card, the first of these that works:

1. The schema 1 card that `v1` names, with the same devices and title.
   Only when it is loaded (and allowed, if it is a lock card from your
   folder), takes every device the card has, and fits the variant's grid.
   A file from your folder whose `v1` names a lock or alarm card, the
   built-in ones included, needs an admin's approval, as a lock card does.
2. The variant itself, with the newer parts left out: card taps and holds,
   `lit` and `tint`, looks (`look`, `align`, `colour`, `shape`, `big_icon`,
   `icon_live`, `selected`, `buttons`, `mark`, a slider's `icon`,
   `kind: steps`), and items that cannot work without the newer software (a
   `choice`, a `swap`, items with `visible`, sliders with `track`,
   `direction`, `rate` or `keep_active`, a label with `clock`). Labels above
   `l` are drawn as `l`. The tile and chip headers become the `title`
   header. Items with `when: [!tablet.v2]` are there only in this form:
   that is how a file gives a tile its switch, or a swap its two buttons.
3. The note: the card's name and the line "Update this tablet to show
   this card". Also when `v1` is `note`.

That tablet holds only the icons of level 1 of the tablet's icon set, so
an icon above level 1 is left out of this form, and an item that would
then show nothing goes with it. The header takes the first of the
person's icon, `can.icon` and the file's `icon` that is in level 1. So
give a schema 2 file a level 1 `icon`.

The form's `needs_v2` says which sizes give the note on such a tablet:
those whose `v1` is `note`, and those whose own simpler form keeps nothing
(with the file's example values) while no old card stands in.

### Limits of schema 2

| What | Limit |
|---|---|
| Params | 8 |
| Options | 16 |
| Inputs | 32 |
| Outputs | 16 |
| Parts | 32 |
| Variants | 6 |
| Items in a variant's layout | 24 |
| Widgets of a card, after loops | 48 |
| Copies of a loop | 16 |
| Widgets in a row | 8 |
| Terms of a `when` | 6 |
| Notes | 4 |
| Tap choices | 6 |
| Devices of a param with several | 16 |

## Error codes

An error gives the code, a message and the place in the document as a dotted
path, such as `outputs.toggle.data`.

| Code | Meaning |
|---|---|
| `not_a_mapping` | Something that must be a mapping is not one. |
| `unknown_key` | A key that is not in this reference. |
| `missing_key` | A required key is absent. |
| `bad_value` | A value has the wrong type or format. |
| `too_long` | A string is longer than its limit. |
| `too_many` | A list or mapping has more items than its limit. |
| `bad_id` | The `id` does not have the required form. |
| `reserved_namespace` | A file from your folder uses the `apollo/` namespace. |
| `duplicate_id` | A Component with this `id` is already loaded. Built-in files load first. |
| `bad_name` | A name has the wrong form or is a reserved word. |
| `duplicate_name` | Two params, inputs or `as` names are the same. |
| `unknown_input` | A `value` is neither an input name nor a template. |
| `unknown_output` | `on_tap` or `on_change` names an output that does not exist. |
| `unknown_param` | A name that must be a param is not one, or a card sets a param the Component does not have. |
| `unknown_option` | A `when`, a choice's `options` or `preview.options` names an option the file does not have (schema 2). |
| `unknown_part` | A `use` names a part that does not exist (schema 2). |
| `bad_nesting` | A part that uses a part, a row in a row, a swap or space in a row or swap, or a loop in a loop (schema 2). |
| `unknown_v1` | `v1` names a card that is not a loaded schema 1 card (schema 2). |
| `replaces_not_allowed` | A file from your folder has `replaces` (schema 2). |
| `action_not_allowed` | An output's domain is not on the list, a `script` output uses a service other than `turn_on`, `turn_off` or `toggle`, or an input uses an action other than `weather.get_forecasts`. |
| `domain_mismatch` | An action's domain differs from the domain of its entity param. |
| `confirm_required` | An output on a lock or alarm does not use `feedback: confirm`. |
| `bad_template` | A template has a syntax error, or uses a feature that is not available in Components (see Templates). |
| `yaml_error` | The file is not valid YAML, or it uses a tag, anchor or alias. |
| `file_too_large` | The file is larger than 32768 bytes. |
| `too_many_documents` | The file holds more than 20 documents. |
| `invalid_component` | The file could not be read for another reason; the message says which. The other files still load. |
| `not_supported` | A card is of a schema this part of Apollo TAB cannot build. |
| `params_incomplete` | A card is missing a param and the Component has no preview values to show instead. |
