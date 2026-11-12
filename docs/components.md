# Writing Components

A Component is a YAML file that builds a dashboard element from native widgets
called Types. Layouts are not sent to tablets yet, so today a Component draws
on the Home Assistant dashboard and in the tablet preview only.

Put your files in `<config>/apollo_tab/components/` (one folder, no
sub-folders), then press "Reload elements" in the TAB-1 panel or reload the
integration. A bad file is listed with its error and does not affect the
others.

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

Params are what the user fills in when placing the element. A Component has at
most 8. Each one is one of these:

```yaml
entity:   {domain: light}                  # one entity of that domain, required
scenes:   {domain: scene, multiple: true}  # a list of 1 to 8 entities, required
max:      {type: number, default: 5000, min: 0, max: 100000}   # min and max optional
page:     {type: page}                     # optional view path, e.g. "kitchen"
```

A number param must have a `default`.

## Inputs

Inputs are the live values the element reads. A Component has at most 16. Each
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
`state_attr(e, a) is none`. The card also shows "Entity not found".

## Outputs

Outputs are what the element can do. A Component has at most 12. Each one is
one of these:

```yaml
toggle:
  action: light.toggle                     # <domain>.<service>
  data: {entity_id: "{{ entity }}", brightness_pct: "{{ value }}"}
  feedback: optimistic                     # optimistic, pulse, progress or confirm, required
open_details: {local: open_details}        # open_details, open_live or go_to_page
go_to_page: {local: go_to_page, page: "{{ page }}"}
```

- The action's domain must be one of: `alarm_control_panel`, `button`,
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
  params, the loop variable and `value`, the control's new value. They do not
  see inputs.
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
beyond that is cut, with the warning that part of the element does not fit.

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

`preview` gives example values for the card picker and for a card whose
entities are not chosen yet. `preview.params` maps param names to values of the
param's type. `preview.inputs` maps input names to a string, number, boolean or
list of numbers.

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
applies to that template with those settings only, so the same element with
another entity keeps working. It is tried again after 5 minutes, when the
elements are reloaded ("Reload elements" in the TAB-1 panel, or reloading the
integration), or when Home Assistant restarts.

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
- `outputs` are the two things the element can do. In `set_brightness`, `value`
  is the slider's new position. Both use `optimistic` because lights respond
  quickly.
- `layout` places a switch driven by `state`, a slider driven by `brightness`,
  and a label showing the percentage. The label uses a template, the other two
  use the bare input name.
- `preview` gives the card picker something sensible to show. `"on"` is quoted
  so that YAML does not read it as a boolean.

## The built-in Thermostat

`apollo/thermostat` sets one target temperature. Its dial takes the range and
step from the climate entity (`min_temp`, `max_temp` and `target_temp_step`),
so it works in °C and °F. It cannot control a thermostat in a mode with a low
and a high target, such as `heat_cool`: an output always sends the same data
keys, so it cannot switch between `temperature` and `target_temp_low` with
`target_temp_high`. In such a mode the dial has no single target to show and
Home Assistant refuses the call.

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
| `action_not_allowed` | An output's domain is not on the list, a `script` output uses a service other than `turn_on`, `turn_off` or `toggle`, or an input uses an action other than `weather.get_forecasts`. |
| `domain_mismatch` | An action's domain differs from the domain of its entity param. |
| `confirm_required` | An output on a lock or alarm does not use `feedback: confirm`. |
| `bad_template` | A template has a syntax error, or uses a feature that is not available in Components (see Templates). |
| `yaml_error` | The file is not valid YAML, or it uses a tag, anchor or alias. |
| `file_too_large` | The file is larger than 32768 bytes. |
| `too_many_documents` | The file holds more than 20 documents. |
