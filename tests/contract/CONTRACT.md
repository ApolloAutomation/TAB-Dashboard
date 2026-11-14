# TAB-1 tablet contract, version 2

This is the one contract between the Home Assistant integration (`apollo_tab`)
and the TAB-1 firmware engine. Both repositories copy this folder unchanged and
test against `fixtures/`. A change here is a change to both.

- `contract.json`: the constants (limits, names, action signatures, error
  codes, timings, font sizes) in machine form.
- `icons.json`: the icon set, name to code point.
- `screens.json`: what the tablet's own screen says (section 11), so the
  panel and its guide can quote the tablet exactly.
- `fixtures/`: golden files. See the list at the end.
- `reference/tabproto.py`: reference code that made the fixtures. Standard
  library only. If it disagrees with this text, this text wins.

Words used here: **HA** is the integration. **Tablet** is the firmware engine.
**Layout** is what `maker/convert.py` produces: layout v1 for device layout
version 1, layout v2 for version 2. **Device layout** (DL) is what the tablet
receives. "(2)" marks a key or rule that only device layout version 2 has.

## 1. Roles

- HA decides everything. The tablet draws and reports touches.
- The tablet never learns entity ids, action names or templates.
- An input from the tablet names a widget id. HA looks the action up in its own
  copy of the layout it sent. A layout that HA did not send can never run an
  action.
- One HA per tablet. Two Home Assistant installs that both manage the same
  tablet take it from each other by pairing again. HA logs a warning when that
  happens (section 3) and does it at most once a minute.
- (2) The tablet does learn the words a card shows: titles, button texts
  and the option texts of a `choice` (effect names, source names, the
  options of a select). Some of them come from devices. They are in the
  layout, and so in the copy the tablet keeps in flash.

## 2. Transport

Everything uses the ESPHome native API connection that the ESPHome integration
already holds. Nothing else is opened.

### 2.1 Actions the tablet exposes (HA to tablet)

| Action | Arguments | Response | Signed | Purpose |
|---|---|---|---|---|
| `tab_hello` | `nonce: string, auth: string` | data | yes | Handshake. Starts a session. |
| `tab_status` | none | data | no | What is on screen, what is being built. Changes nothing. |
| `tab_pair` | `nonce: string, wrapped: string, kid: string` | status | by the API key | Gives the tablet its secret. |
| `tab_layout` | `hash: string, seq: int, total: int, size: int, data: string` | status | no | One chunk of a device layout. |
| `tab_commit` | `hash: string, auth: string` | status | yes | Check the received layout and switch to it. |
| `tab_set` | `data: string, auth: string` | status | yes | Slot values (JSON text). |
| `tab_ack` | `n: int, ok: bool, code: string, auth: string` | none | yes | Result of one input. |
| `tab_clear` | `auth: string` | status | yes | Forget the layout. Show the waiting screen. |

- "status" means the ESPHome action response with `success` and
  `error_message`. On failure `error_message` is exactly one error code from
  this document. No other text.
- "data" means a JSON object in the response.
- "Signed" calls carry `auth` (section 6.2). A paired tablet refuses them
  without a valid `auth`. A tablet that is not paired accepts any `auth`. A
  tablet without an API encryption key counts as not paired (section 6.1).
- Every string argument is valid UTF-8.
- One ESPHome message is at most 32768 bytes on the tablet. `data` of
  `tab_layout` is at most **16000 bytes**. HA sends `data` of `tab_set` of
  at most **12000 bytes**; this is HA's limit, not the tablet's: the tablet
  accepts any `tab_set` that fits in one ESPHome message.
- HA sends one call at a time per tablet and waits for its response before the
  next one. Timeout 10 s. A timeout counts as a failure. `tab_ack` has no
  response; it is written in order with the other calls.

Why `auth` exists: ESPHome registers every action as a normal Home Assistant
service that any user of the house may call, not only admins. Without `auth`
any user could put other content on a tablet or blank it.

### 2.2 Events the tablet fires (tablet to HA)

| Event | Data | Purpose |
|---|---|---|
| `esphome.tab1_hello` | `d: "1\|<mac>\|<boot>"` | The knock: "I am connected and nobody greeted me." |
| `esphome.tab1_input` | `d: <payload>`, `s: <signature>` | One touch. See section 7. |

Knock rules. Every knock is a bus event that the recorder stores, so they are
kept few:

- The tablet knocks only while an API client is connected and neither
  `tab_hello` nor `tab_status` has arrived on this connection.
- Schedule after the connection opens: at 3, 6, 9, 12 and 15 s, then the gap
  doubles (6, 12, 24 ... s) up to one knock every 300 s. A new API connection
  starts the schedule again. (`knock_times` in the reference code.)
- One more knock, outside the schedule: a touch that finds no session on a
  tablet that is connected, has an API key and is paired. HA may hold a
  session the tablet lost, and the person is waiting. The tablet knocks at
  once, at most once every 3 s, and starts the schedule above again. HA
  treats it like any other knock.
- The knock is not signed. Any ESPHome device can fire this event with
  someone else's MAC, so a knock never resets a session by itself. HA
  answers at most one knock every 2 s per tablet (`knock_step` in the
  reference code, `fixtures/status.json` "knock"):
  - A tablet an admin has not approved: HA calls nothing (section 3).
  - HA has no session with this approved tablet on the current connection:
    it calls `tab_hello`.
  - HA has one: it calls `tab_status` first, whatever the `<boot>` number.
    It calls `tab_hello` only when that answer says `"session":0` (the
    tablet lost its session, for example on a reconnect HA did not see).
    Otherwise it does nothing more.
- HA ignores the `device_id` in event data. The tablet is found by the MAC
  inside `d`.
- `<mac>` is 12 lower-case hex characters, no separators.

### 2.3 No entities

The engine adds no sensors or text sensors. Everything HA needs comes back from
`tab_hello` and `tab_status`.

## 3. Handshake

HA never calls a tablet an admin has not approved. An admin approves a newly
seen tablet once; until then HA calls none of the actions in section 2.1 on
it and ignores its events. For an approved tablet, HA calls
`tab_hello(nonce, auth)` when the tablet connects, when it sees a knock it
does not ignore, and to start a new session after `stale_session` input or
an `auth` error. `nonce` is 32 lower-case hex characters from a secure
random source. It is the session id.

`auth` is the signature for `tab_hello` (section 6.2) or empty when HA has no
secret for this tablet.

The tablet always answers with the data below. It starts a **new session**
only when it is not paired, or when `auth` is valid for its stored secret.
A new session: the nonce becomes the session nonce, the tablet's input counter
goes to 0, the last accepted call number goes to 0. Otherwise the old session
(if any) stays and the response says `"session":0`.

The tablet keeps the nonces of the last 16 sessions of this boot in RAM. A
`tab_hello` with one of them starts no session, even with a valid `auth`
(`fixtures/auth.json` "repeat"). A `tab_hello` that starts no session does
not use up its nonce. HA never reuses a nonce.

Limits: the list is empty after a reboot, and when a 17th session starts the
oldest nonce leaves the list. In both cases a recorded `tab_hello` whose
nonce is no longer on the list starts a session again, and the recorded
signed calls of that old session pass again. That session uses a nonce HA
no longer holds: its input is dropped as `stale_session` and HA greets again
(section 7.3), and HA's own next signed call answers `auth`, which also
makes it run the handshake again (section 5). Recording a `tab_hello`
needs the ESPHome API traffic, which is encrypted on every paired tablet
(6.1). A nonce chosen by the tablet would close this; it is left for a later
contract version.

Response data:

```json
{"proto":[1,2], "engine":"0.2.0", "boot":3,
 "layout":"a9326c033e45f2f4", "kid":"<16 hex or empty>", "enc":1, "session":1,
 "caps":{"w":["heading","card","label","button","switch","slider","thermostat","chart","image","choice"],
         "icons":2, "screen":[1280,800], "max_pages":64,
         "max_layout":262144, "max_stored":131072, "max_chunk":16000,
         "max_slots":1024, "max_widgets":2048},
 "mem":{"int":61000,"psram":28000000,"block":16000000}}
```

| Key | Meaning |
|---|---|
| `proto` | Lowest and highest contract version the tablet speaks. Version 2 is version 1 with device layout version 2 (section 4). Nothing else differs. HA and the tablet can talk when the two ranges share a version (section 9). |
| `engine` | Engine version text. For display only. |
| `boot` | Boot counter. Also in the knock. |
| `layout` | Hash of the layout on screen, or empty. A staged layout does not count. |
| `kid` | Id of the stored secret (section 6), or empty. Empty when `enc` is 0. |
| `enc` | 1 when the tablet has an API encryption key. |
| `session` | 1 when this call started a session, else 0. |
| `caps.w` | Widget kinds the tablet can draw. |
| `caps.icons` | Icon set level (section 4.5). |
| `caps.max_*` | Limits of this tablet. HA uses the smaller of these and its own. |
| `caps.max_pages` | Most pages in one layout. Missing: 20. |
| `caps.max_stored` | Largest layout, in bytes, that the tablet keeps across a restart. Missing: 131072. A larger layout is still sent, shown and used; HA warns that it is not kept. |
| `mem` | Free internal RAM, free PSRAM and largest free PSRAM block, in bytes. |

HA rules after the response (`fixtures/hello.json`, `hello_steps` in the
reference code):

1. If `proto` does not include a version HA speaks: stop. Status `unsupported`,
   reason `tablet_old` (the tablet's highest is below HA's lowest) or
   `tablet_new`.
2. If `enc` is 1 and (`kid` differs from the stored one, or there is none, or
   `session` is 0): pair (section 6), then call `tab_hello` again. Pairing
   ends the session. If the tablet had another `kid` (not empty), log a
   warning: another Home Assistant may be using this tablet. HA pairs a
   tablet at most once per 60 s.
3. If `enc` is 0: no pairing, no input, no signing. HA sends an empty `auth`
   and accepts no input event from this tablet, also when it holds a secret
   for it. Layout and state still work.
4. Compile the device layout for these `caps`, in the highest layout version
   both sides speak: version 2 when `proto` includes 2, else version 1
   (section 4.6). If its hash differs from `layout`: send the layout.
5. Send a full state snapshot.

Unknown keys in the response are ignored. Missing `caps` keys take
`caps_defaults` from `contract.json`. `engine_caps` in `contract.json` is
what the newest engine reports.

### 3.1 `tab_status`

No arguments, no side effects, no session needed. Response data:

```json
{"layout":"a9326c033e45f2f4", "staged":"4384f665e4dd9f62", "build":"",
 "mem":{"int":60000,"psram":27000000,"block":16000000}, "session":1}
```

| Key | Meaning |
|---|---|
| `layout` | Hash of the layout on screen, or empty. |
| `staged` | Hash of the layout that is committed and still being built, or empty. |
| `build` | Result of the last build that ended without showing its layout: `memory` or `build`. Empty after a build that was shown, and after a new `tab_layout` seq 0. |
| `mem` | As in `tab_hello`. In both answers `block` may be, while a layout is being built, the value the tablet read when the build began: it does not walk its heap during a build. |
| `session` | 1 when the tablet has a session on the current API connection, else 0. |

HA uses it to learn when a committed layout is really on screen
(section 5, `fixtures/status.json`), and to check a knock (section 2.2).

## 4. Device layout (DL), versions 1 and 2

HA compiles a dashboard into a device layout. The tablet does not get the
layout `maker/convert.py` makes.

Version 2 is version 1 with more keys. Every key marked (2) is optional, and
where it is absent the tablet draws exactly what version 1 draws. So a
version 1 layout is also a valid version 2 layout, and the tablet reads both
with the same code. HA writes `"v": 2` only for a tablet whose `proto`
includes 2, and never puts a key marked (2) into a `"v": 1` layout.

On a tablet that speaks version 2, `v` itself changes only two things: the
page limit and the per-page draw counts (4.2). Every key is read and drawn
whatever `v` says.

### 4.1 Encoding

- One JSON object, UTF-8, no byte order mark.
- Canonical form: keys sorted, no spaces, non-ASCII characters written as
  themselves (`json.dumps(obj, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False)`).
- Numbers: integers, or decimals with at most 3 fraction digits. No exponent.
  Range -1e9 to 1e9.
- The tablet must accept any valid JSON with these value types, in any key
  order, and must skip keys it does not know.
- **Hash** = first 16 hex characters of SHA-256 over the exact bytes.
- At most 262144 bytes.

### 4.2 Top level

| Key | Type | Meaning |
|---|---|---|
| `v` | 1 or 2 | DL version. |
| `screen` | `[1280,800]` | Pixel size the rectangles assume. |
| `theme` | object | Colours as integers `0xRRGGBB`: `wall card card_pr card2 card2_pr line tx tx2 acc accf accf_pr acct acc2 onbg onbg_pr ontx ion`. Plus `dark` (0/1), `r` (card radius), `r2` (inner radius), `bw` (border width). Roles are in section 4.7. |
| `nav` | list | Side bar entries, at most 8: `{"p": page index, "title": text, "icon": code point}`. `icon` is optional. Entry `i` has its place by its index in the list (4.7). (2) HA sends no entry for a detail page. If one names a detail page, the tablet does not draw it and the other entries keep their places. |
| `pages` | list | Each `{"title": text, "w": [items]}`. Page 0 is shown first. (2) Optional `sub`, `ttl` and `theme` (section 4.8). |
| `slots` | string | One character per slot: the type of slot 1, 2, 3 and so on. |

Limits and how they are counted:

- Pages: length of `pages`. Version 1: at most 20. (2) At most
  `caps.max_pages` (64). A page is a **detail page** when its `sub` is 1 and
  it is not page 0. Every other page is **normal**, also one with `"sub": 0`;
  at most 20 pages are normal.
- Slots: length of `slots`, at most `caps.max_slots` (1024).
- Widgets: every object that has an `id` (headings, cards, and the widgets
  inside cards), at most `caps.max_widgets` (2048).
- (2) On one page the tablet draws at most 8 charts, 8 thermostats and 12
  sliders with a `track`. It skips a further chart or thermostat like a kind
  it does not know, and draws a further slider without its `track`. HA sends
  at most 4, 4 and 6 (`limits.send_*` in `contract.json`). Those three are
  HA's own choice: never above the tablet's counts, and HA may change them
  without a new contract version.

HA checks all of these and the byte size before it sends anything
(`compile_device_layout` raises `too_big` or `limits`). (2) A layout larger
than `caps.max_stored` is sent all the same; the tablet does not keep it
across a restart (section 5).

### 4.3 Items and widgets

Every item and widget has `id` (unique in the layout, the id used in input),
`t` (kind) and `r` (`[x, y, w, h]` in screen pixels, absolute). The widgets
of a card are absolute too: the card's border `bw` does not move them.

Rectangles (`r`, `hr`) are cut to the 1280x800 screen: the tablet keeps the
part of the rectangle that lies on the screen, and a negative width or
height counts as 0. A number in a rectangle below -4000 or above 4000 is
`parse`. So no widget is ever larger than the screen. (2) A widget whose
rectangle is left with a width or a height of 0 is not drawn and takes no
touch.

Page items:

| `t` | Keys |
|---|---|
| `heading` | `text`, optional `icon`. (2) `c` (colour). |
| `card` | `w` (widgets). Optional: `hr` (header rectangle), `icon`, `title` (text), `on` (bool), `style`. (2) `tap`, `cf`, `confirm`, `hold`, `ic` (icon), `tint` (colour), `lit`, `un` (bool). |

`style` overrides theme colours for one card: `bg bg2 tx tx2 acc acc2 acct card2
line onbg ontx` (integers), `r r2 bw`, and `gd` (0 = top to bottom, 1 = left to
right; only with `bg2`). `bg` replaces the theme's `card`. (2) Also
`card_pr card2_pr accf accf_pr onbg_pr ion`, so a card can carry another
theme whole.

A card with `on` is drawn in the "on" colours while the value is 1.

(2) More keys of a card:

| Key | Meaning |
|---|---|
| `tap` | As on a widget (below). The whole card is a button. Which presses are the card's is in "Who gets a press" below. `cf` and `confirm` work as on a widget. Engine 0.1.0 reads the key and does nothing with it. |
| `hold` | `{"go": page}`. A press held 500 ms opens that page (section 7.4). |
| `ic` | A value above 0 replaces `icon` in the header. No value or 0: `icon`. Ignored on a card without `icon`. |
| `tint` | The card's own accent colour, for example the colour of a lamp (section 4.7, "Card colours"). |
| `lit` | How the card looks while `on` is 1: 0 fill (the look of version 1), 1 icon only, 2 outline, 3 no change. Default 0. |
| `un` | 1: the device is not available. The header and every widget of the card are drawn at 40% opacity, and nothing in the card sends an input while the tablet can send (as for a control without a value, section 7.4). A `go` or `back` still works. Opacity does not multiply: a control without a value inside such a card is at 40%, not less. |

Widgets inside a card:

| `t` | Keys | Draws |
|---|---|---|
| `label` | `text` (text), `size` 0/1/2 (small, medium, large). (2) `px`, `al`, `c` (colour), `clk` with `value` (number) | One line of text, cut to the rectangle. (2) With `clk`: a clock. |
| `button` | optional `text` (text), optional `icon`. (2) `value` (bool), `ic` (icon), `c` (colour), `shape`, `isz` | A press button. (2) With `value`: it can look selected. |
| `switch` | `value` (bool). (2) `c` (colour) | A toggle. |
| `slider` | `value min max step` (numbers). (2) `look`, `dir`, `track`, `icon`, `c` (colour), `nv`, `rate` (number) | A slider. (2) Also a bar, a level, a progress, upright, or over a run of colours. |
| `thermostat` | `value min max step` (numbers). (2) `c` (colour), `mark` (number), `bs` | An arc with the value in the middle. With `change`: a minus and a plus button. |
| `chart` | `value` (list), `kind` 0 = line, 1 = bars. (2) `c` (colour), `mark` (number), `st` | A small graph. |
| `image` | `value` (icon). (2) `look`, `c` (colour) | An icon, or the placeholder. Pictures come in a later version. |
| (2) `choice` | `texts`, `icons`, `cols`: HA sends at least one of them. Optional `value` (number), `rows`, `look` | One of up to 16 options. |

(2) The new keys, per kind. Section 4.7 says how each is drawn.

| Kind | Key | Values |
|---|---|---|
| any widget | `vis` (bool) | 0 or no value: the widget is not drawn and is not there for a touch ("Who gets a press" below). Its rectangle stays where it is. Two widgets may share a rectangle when HA's values never make both 1. |
| any widget but `slider`, `thermostat`, `choice` | `hold` | `{"go": page}` |
| `label` | `px` | Text size wanted, a whole number. Wins over `size`. |
| | `al` | 0 left, 1 centre, 2 right. |
| | `clk` | 1: 24 hour clock. 2: 12 hour clock. The label then shows `value` as a time and ignores `text`. |
| `button` | `value` | 1: selected. 0 or no value: not selected. The button works in both. |
| | `ic` | As on a card. |
| | `c` | The button's own fill colour (a colour swatch). |
| | `shape` | 0 box, 1 round, 2 bare (no background). |
| | `isz` | 0: icon 24. 1: a large icon. |
| `switch` | `c` | Track colour while the value is 1. |
| `slider` | `look` | 0 knob (version 1), 1 bar. |
| | `dir` | 0 left to right, 1 bottom to top, 2 top to bottom. |
| | `track` | A list of 2 to 8 colours (constants) painted along the slider instead of a fill. |
| | `icon` | A constant icon inside a bar. |
| | `c` | Fill colour. |
| | `nv` | 1: without a value the slider is not faded and still takes input. |
| | `rate` | Units per second by which a slider without `change` moves by itself. |
| `thermostat` | `c` | Colour of the value arc. |
| | `mark` | A second value, shown as a dot on the arc. |
| | `bs` | Side of the minus and plus buttons, 36 to 64. Default 36. |
| `chart` | `c` | Colour of the line or the bars. |
| | `mark` | Bars: the index of the bar that stands for "now". |
| | `st` | Line: 1 draws steps. |
| `image` | `look` | 0 box (version 1), 1 badge, 2 bare. |
| | `c` | Icon colour. |
| `choice` | `texts` | List of at most 16 constant texts, each at most 40 UTF-8 bytes. `""`: this option has no text. |
| | `icons` | List of at most 16 constant code points. 0: this option has no icon (here 0 is not the placeholder). |
| | `cols` | List of at most 16 constant colours: the options are swatches. |
| | `value` | Optional. Index of the selected option, from 0. Absent, no value, a fraction, or a number that is no index: none is selected. The control stays active. |
| | `rows` | 1 to 4. Default 1. |
| | `look` | 0 cells, 1 dots. |

The options of a `choice` are as many as its longest list, at most 16; more
are ignored. A shorter list leaves the later options without that part. A
`choice` with no option at all (no list, or only empty lists) is not drawn
and is not there for a touch, like a hidden widget. It is never `parse`. HA
sends none.

Interaction keys on any widget, and (2) on a card:

| Key | Meaning |
|---|---|
| `tap: {"p": n}` | A press sends an input. `n` is the feedback policy: 0 optimistic, 1 pulse, 2 progress, 3 confirm. |
| `tap: {"go": page}` | A press switches to that page. Nothing is sent. |
| (2) `tap: {"back": 1}` | A press on a detail page returns to the page it was opened from (section 4.8). Elsewhere it does nothing. Nothing is sent. |
| `change: {"p": n}` | Slider: releasing it sends an input with the value. Thermostat: each press on minus or plus sends an input with the stepped value. (2) `choice`: a tap on option `i` sends an input with the value `i`; a tap on the selected option sends again. |
| (2) `hold: {"go": page}` | A press held 500 ms switches to that page. Nothing is sent, and the release is not a tap. |
| `cf: 1` | The tablet must ask before it sends. |
| `confirm` (text) | The question to ask. Without it the tablet asks "Are you sure?". |

A widget with neither `tap` nor `change` nor `hold` is display only. A `tap`
or `hold` object with none of the forms above, and a `go` to a page that
does not exist, do nothing.

(2) **Who gets a press.** One table for taps and holds; sections 4.8 and
7.4 follow it. "The card's" means: the card's `tap` fires on release, and
the card's `hold` after 500 ms, when the card has them. Else nothing
happens.

| The press begins on | A tap is | A hold is |
|---|---|---|
| A hidden widget (`vis` 0 or no value) | Not the widget's: it is not there. The press goes to the widget under it at that point, else it is the card's | the same |
| A widget with `tap` | The widget's. Never the card's | The widget's `hold`; without one, the card's |
| A slider with `change` | The slider's: a drag, anywhere in its rectangle. Never the card's | None |
| A thermostat with `change`: its minus and plus buttons | The button's | None |
| A thermostat with `change`: the rest of its rectangle | The card's | The card's |
| A `choice` with `change` | The control's, anywhere in its rectangle. A press inside a cell picks that option (`look` 1: the whole cell, not only the dot). A press in a gap between cells does nothing | None |
| A widget with `hold` and no `tap` | The card's | The widget's |
| Any other widget without `tap` and `change`: a label, an image, a chart, a slider, thermostat or `choice` that only shows. Also while it is drawn faded | The card's | The card's |
| A widget with `tap` or `change` that is drawn faded because it has no value (4.7). For a thermostat with `change`: its two buttons | No input, and not the card's. A `go` or `back` of the widget still works, as in version 1 | As for the same widget with a value |
| Anything in a card with `un` 1 | Nothing is sent (section 7.4) | Works: a `go` sends nothing |
| The card itself, outside its widgets | The card's | The card's |

- A card tap needs no value: a card whose `on` has no value still sends
  (section 7.4 says what it shows).
- A press that has moved 12 px or more from where it began is no longer a
  card tap and no longer a hold. The 12 px are the straight-line distance
  from the first point of the press (`dx * dx + dy * dy >= 144`). Once
  passed, it stays passed: a finger that comes back does not make the press
  a tap or a hold again. At 48 px sideways it becomes a page swipe (4.8);
  before that it is nothing. A widget with `tap` keeps the rule of
  version 1: it fires on release unless a swipe took the press.
- A widget that has the press by this table and becomes hidden, faded or
  unavailable while the finger is down loses the press (section 7.4).

(2) How the tablet reads values of version 2 keys:

- A known key with the wrong JSON type (text where a number is expected, a
  slot of another type than the field's) is `parse`, as in version 1.
- A whole number out of range in a key that only changes the look (`px al
  shape isz look dir rows st bs lit ttl`) is held to the nearest allowed
  value. So a later contract can add a value without a new key. For `ttl`:
  below 0 is 0, 1 to 4 is 5, above 3600 is 3600.
- These keys, and `clk`, `nv` and `sub`, take whole numbers. A fraction in
  one of them is `parse`, as for `size` and `kind` in version 1.
- `clk` other than 1 or 2: a plain label that shows `text`. `nv` and `sub`
  count only when they are exactly 1; any other whole number is 0.
- A constant colour outside 0 to 16777215 is `parse`.
- A `track` with fewer than 2 colours is no track; of more than 8 the first
  8 count.
- A `texts` entry longer than 40 bytes is cut to 40 at a character border,
  never `parse`. An entry that is not text is `parse`.
- A live value that is out of range (a colour, a `choice` index) counts as
  no value.

### 4.4 Bound fields and slots

A field marked (text), (bool), (number), (list), (icon) or (2) (colour)
holds either a constant of that type or `{"s": n}`, a reference to slot `n`
(1-based).

| Type | Char | Wire value |
|---|---|---|
| text | `t` | String, at most 255 UTF-8 bytes. |
| bool | `b` | 0 or 1. |
| number | `n` | Number. |
| list | `l` | List of at most 120 numbers. |
| icon | `i` | Code point from `icons.json`. 0 means "draw the placeholder". |
| (2) colour | `n` | A whole number 0 to 16777215, `0xRRGGBB`. A colour lives in a number slot; there is no slot letter for it. |

Every slot may also be `null`: "no value". The tablet then draws the widget in
its faded look of "No value" (section 4.7). Before the first `tab_set` all slots are
`null`.

(2) No value, per field: a colour without a value (also a number that is not
whole or not in range) means "no colour": the part keeps its usual colour.
`vis` without a value hides the widget, so two widgets that share a place
never both show before values arrive. `un`, a button's `value` and `rate`
without a value count as 0. A `mark` without a value is no mark.

(2) **Age.** The tablet remembers when each slot was last written: the
moment a `tab_set` named it with a value, also when the value was the same
as before, also in a full snapshot. The age of a widget is the time, in
seconds, since the slot bound to its `value` was last written. A widget
whose `value` is a constant has age 0 for ever: it does not move. `clk`
and `rate` count with the age (4.7). A write to the slot of `rate` does not
change the age. The count never wraps while the tablet has power.

HA gives each (source slot, type) pair its own device slot, so a slot has one
type. (2) Where the same source is converted in two ways (as a number and as
a colour, or as a colour for two cards with different themes) each way has
its own device slot. HA does the conversion (`coerce` in the reference
code): bool follows `isOn` in `frontend/logic.js`; number follows
`toNumber`; an icon name that is not in the tablet's icon set, and any
picture URL, becomes 0.

(2) Colour conversion. A colour may come as a list of exactly three numbers
that are each 0 to 255 after rounding (`[r, g, b]`), as `"#RRGGBB"` with
six hex digits in either case, as a whole number 0 to 16777215 (also
written `16711680.0`), or as a role name HA knows for that card (`good`,
`warn` and so on). Anything else is `null`: a list of another length, a
part out of range, `"#FFF"`, a bool, a fraction. `fixtures/state_v2.json`
has a sample of each under "colours".

The device layout holds no entity ids. Two dashboards that differ only in
which entity a card uses have the same bytes and the same hash. (2) In
version 2 that holds when the devices can also do the same: a layout
depends on what a device can do and may hold names it reports (4.3,
`texts`). HA therefore never uses the hash to decide whether values or
actions changed (section 8).

### 4.5 Icons

`icons.json` maps `mdi:` names to `[code point, level]`. Level 1 is the set of
contract version 1 (106 icons). Level 2 adds 91. A later contract may add
icons with a higher level. It never removes or renumbers one. The firmware
embeds every glyph up to its level and reports the level in `caps.icons`.
HA sends the `fallback` glyph for a fixed icon above the tablet's level, and
0 for a bound one.

### 4.6 Down-levelling

By version first. A tablet whose `proto` does not include 2 gets a version 1
layout. HA makes it from the dashboard again, not from the version 2 layout:
every card is laid out for version 1, as its own version 1 form or as a card
that says the tablet needs an update. So nothing leaves a hole. A dashboard
that uses only cards of version 1 gives the same bytes as it did before
version 2 existed. Detail pages and page themes are left out of a version 1
layout.

Then by kind, as before: HA leaves out widgets whose kind is not in `caps.w`.
The rest of the card stays. Headings and cards are always sent, whatever
`caps.w` lists: a tablet that speaks this contract draws them. A missing
`caps.w` means the nine kinds of version 1; an empty list means no kind
inside a card.

The hash is taken after down-levelling, so two tablets with different caps can
hold different hashes for the same dashboard. HA supports version 1 for as
long as it ships the cards of version 1.

### 4.7 How it is drawn

The tablet must look like the editor's picture. The reference is
`frontend/render.js` and the `.at-*` rules in `frontend/styles.js` of the
integration, at scale 1. All numbers are pixels on the 1280x800 screen.
Colour names are theme keys; a card's `style` overrides them inside that card.
(2) "Theme" is the theme of the page on screen (section 4.8).

Fonts. Exactly these sizes exist on the tablet (`fonts` in `contract.json`):

| Use | Size |
|---|---|
| Label small / medium / large (`size` 0 / 1 / 2) | 14 / 18 / 34 |
| (2) Label with `px` | The largest size the tablet has that is not above `px`, at least 14. Text sizes: 14, 15, 16, 18, 20, 28, 34. Digit sizes: 48, 96, 192; they hold only `fonts.digits_glyphs` (`0123456789.,-:°%+` and the space). A digit size is used only when every character of the text is in that set; otherwise the largest text size not above `px`. While the text at a digit size is wider than the rectangle: the next smaller of 192, 96, 48, 34. At 34 and below it is cut with "…" like any text. |
| Button text | 15 |
| Card header title | 16 |
| Heading text | 20 |
| Thermostat value | The largest of 48, 34, 20, 18, 14 that is not above `thermostatFit` (below). The thermostat uses the 48 size only for a text made of `0123456789.,-`, so the "–" for no value takes the largest of 34, 20, 18, 14 that fits. A negative value uses the ASCII `-`. Then, while the text drawn at that size is wider than the text may be (`thermostatFit`'s width), the next smaller of those sizes: 48, 34, 20, 18, 14. Only at 14 is it cut with "…". |
| Icons in headers, headings, buttons, minus and plus | 24 |
| Icons in the side bar | 28 |
| Image widget icon | The largest of 72, 48, 28, 24 that is not above `min(w, h) / 2`. (2) Other looks: see "Image". |

The text sizes hold only the characters in `fonts.text_glyphs` (Latin,
Latin-1, Latin Extended-A, dashes, quotes, bullet, ellipsis, euro). Any
other character, for example Greek, Cyrillic, Chinese or an emoji, is drawn
as an empty box, and the editor's tablet preview shows a box there too.

Every text is one line, left aligned unless said otherwise, centred
vertically in its rectangle, and cut with "…" when it does not fit. No text
box ever changes size with its content. (2) A line that is higher than its
rectangle starts at the rectangle's top and is cut at its bottom. HA gives
a label of a digit size a rectangle at least `fonts.row_px` high (60, 120
and 240 for 48, 96 and 192), which holds the line.

(2) Five rules for every formula below, so that odd sizes and odd values
have one answer on both sides (vectors in `fixtures/maths.json`):

- `round(x)` is `floor(x + 0.5)`.
- `a mod b` is the remainder that is never negative.
- A length that comes out below 0 counts as 0. A part whose width or height
  is 0 is not drawn.
- Where a formula divides by a length or by `max - min` and that is 0 or
  less, the result is 0: a slider whose track has no length, or whose `max`
  is not above `min`, shows amount 0, has no mark and sends nothing.
- Where an icon is "the largest of 72, 48, 28, 24 that is not above" a
  length and none is, it is 24.

(2) **Card colours.** Five functions, the same on both sides. No colour
is ever worked out in floating point. Their vectors are in
`fixtures/maths.json`.

- `mix(a, b, p)`: per channel `(a * (100 - p) + b * p + 50) div 100`, in
  whole numbers. `p` is a whole number from 0 to 100; `p` 0 gives `a`.
- `lum(c)`: `(0.2126 * L[r] + 0.7152 * L[g]) + 0.0722 * L[b]`, in this
  order, in 64-bit floating point, each step on its own (no fused
  multiply-add). `L` is the table `linear` of `maths.json`: 256 numbers,
  the linear value of each channel value. Every side holds a copy of the
  table and never works the values out itself.
- `contrast(a, b)`: `(hi + 0.05) / (lo + 0.05)`, with `hi` the larger and
  `lo` the smaller of `lum(a)` and `lum(b)`.
- `readable(c)`: `0xFFFFFF` or `0x15181D`, the one with the higher contrast
  on `c`; `0xFFFFFF` when both are equal.
- `legible(c, b, t)`: `c` when `contrast(c, b) >= 3`; else `m = mix(c, t,
  50)` when `contrast(m, b) >= 3`; else `t`. `t` is the text colour in use
  on `b`.

A card's colours are the page's theme with the card's `style` on top. For
`ion` and `onbg_pr`, in this order: the style's own value when it has one;
else, when the style's `onbg` differs from the page theme's `onbg`, `ion` is
`acc` when `contrast(acc, onbg) >= 3` and `ontx` otherwise, and `onbg_pr` is
`blend(ontx, onbg, 0.82)`; else the theme's. `blend(a, b, t)` is the one
formula kept from version 1: per channel `floor(a * (1 - t) + b * t + 0.5)`,
in this order, in 64-bit floating point, each step on its own. It is used
here and nowhere else.

With `bg` the card's background (`style.bg`, else `card`), `X` the value of
`tint` (or none), and `dark` true when `readable(bg)` is `0xFFFFFF` (on
every theme of the library that is the theme's own `dark` flag):

| Name | Without `tint` | With a `tint` value `X` |
|---|---|---|
| `A`, the accent | `acc` | `legible(X, bg, tx)` |
| `AF`, accent fill | `accf` | `A` |
| `AT`, content on `AF` | `acct` | `readable(A)` |
| `AP`, `AF` pressed | `accf_pr` | `mix(0x000000, A, 88)` |
| `F`, the "on" fill | `onbg` | `mix(X, bg, dark ? 78 : 84)` |
| `FT`, text on `F` | `ontx` | `tx` |
| `FS`, small text on `F` | `ontx` | `tx2` when `contrast(tx2, F) >= 3`, else `tx` |
| `FI`, icon on `F` | `ion` | `legible(X, F, tx)` |
| `FP`, pressed and tracks on `F` | `onbg_pr` | `mix(tx, F, 90)` |

Where a rule below names `acc`, `accf`, `acct`, `accf_pr`, `onbg`, `ontx`,
`ion` or `onbg_pr`, it means `A`, `AF`, `AT`, `AP`, `F`, `FT` (`FS` for small
text), `FI` and `FP`. Without `tint` these are the theme's own colours, so
version 1 is unchanged. "On:" in a rule applies while the card is **filled**:
`on` is 1 and `lit` is 0.

| `on` and `lit` | Card |
|---|---|
| `on` 0, or `lit` 3 | The off look. |
| `on` 1, `lit` 0 | Filled: background `onbg`, border colour `acc`, text `ontx`. Every "on:" colour applies. |
| `on` 1, `lit` 1 | The off look, but the header icon and the icon of an image with `look` 1 or 2 take `acc`. |
| `on` 1, `lit` 2 | As `lit` 1, and the border is `acc` and at least 2 wide. |

"The card's background now" is `onbg` while filled, else `bg`. "The card's
text colour now" is `ontx` while filled, else `tx`.

| Part | Drawing |
|---|---|
| Page | Background `wall`. |
| Side bar | Rectangle `[0, 0, 96, 800]`, colour `card`. Always drawn, also with no entries. Entry `i` is a button at `[16, 16 + 72*i, 64, 64]`, radius `r2`, no background, icon 28 in `tx2`. No title text. The entry of the page on screen: background `onbg`, icon `acc`. An entry without `icon` uses `mdi:view-dashboard`. (2) On a detail page: one entry at `[16, 16, 64, 64]` in the look of the entry on screen, with `mdi:arrow-left`. The side bar always uses the theme's own colours, never a card's. |
| Not connected mark | `mdi:lan-disconnect`, 28, colour `tx2`, centred in `[32, 736, 32, 32]` of the side bar. Shown after 10 s without HA. |
| Heading | Optional icon 24, gap 8, text 20. Colour `tx`. (2) With `c`: `legible(c, wall, tx)` for both. |
| Card | Radius `r`. Border `bw` wide in `line`. Background `card` (or `style.bg`; with `bg2` a gradient from `bg` to `bg2`, direction `gd`). Text `tx`. |
| Card, on | Background `onbg`, border colour `acc`, text `ontx`. (2) By `lit`, as in the table above. |
| (2) Card, pressed | Only a card with `tap` or `hold`. Background `card_pr` (on: `onbg_pr`); a style with `bg` and no `card_pr`: `mix(tx, bg, 90)`. The pressed look appears 80 ms after the touch, and only if the finger is still down and has moved less than 12 px, so a page swipe that starts on a card does not flash it. |
| (2) Card, pulse | Background `accf`. Header icon, title, labels and image icons `acct`; images are drawn without their box or badge. For 300 ms. |
| (2) Card, waiting | A 2 px outline in `acc` (on: `ion`). |
| (2) Card, not available | `un` 1: the header and every widget at 40% opacity. The 40% is applied once: a control without a value in such a card is at 40% too, not at 16%. |
| Header | In `hr`: icon 24 in `tx2` (on: `ion`), gap 8, title 16. (2) `ic` replaces the icon while it has a value above 0. |
| Label | Small: `tx2` (on: `ontx`). Medium and large: the card's text colour. (2) With `px`: drawn at 14 or 15 it is small, at any other size it takes the card's text colour. `al` places the text left, centred or right in the rectangle. `c`: the text is `legible(c, the card's background now, the card's text colour now)`. |
| (2) Label, clock | `value` is `v`, minutes after local midnight; it may have a fraction. The label shows `m = floor(v + age / 60) mod 1440` as `HH:MM`, two digits each (`clk` 1), or with the hour as 12, 1 to 11 without a leading zero (`clk` 2). `age` is the age of 4.4. No am or pm. No value: `--:--`. It is drawn again when `m` changes. Size, `al` and `c` as for any label. |
| Button | Background `card2`, radius `r2`, padding 6. Icon 24 and text 15, centred, gap 6; side by side, or stacked when both exist and the height is 64 or more. Text colour `tx`. Pressed: `card2_pr` (on: `onbg_pr`). Pulse: background `accf`, content `acct`, for 300 ms. Waiting (policies 0 and 2 until the answer): a 2 px outline in `acc` (on: `ion`). |
| (2) Button, selected | `value` 1: background `accf`, content `acct`. Pressed: `accf_pr`. When `contrast(accf, the card's background now) < 1.3`: also a 2 px border in `acct`, inside. |
| (2) Button with `c` | While `c` has a value: background `c`, content `readable(c)`, pressed `mix(readable(c), c, 85)`. Selected: the background stays `c`, with a 3 px border in the card's text colour now, inside. |
| (2) Button, `shape` and `isz` | `shape` 1: a circle of diameter `min(w, h)`, centred in the rectangle; no text is drawn. `shape` 2: no background; pressed `card2_pr` (on: `onbg_pr`); selected and pulse fill as usual. `isz` 1: the icon is the largest of 72, 48, 28, 24 that is not above `min(w, h) / 2`. `ic` as in a header. |
| Switch | Track `min(w, 64)` by `min(h, 36)`, at the left of the rectangle, centred vertically, fully round, `card2`. Knob 28 round, 4 from the left, `tx2`. Value 1: track `acc` (on: `ion`), knob 4 from the right, `acct` (on: `onbg`). (2) With `c`: the track at value 1 is `legible(c, the card's background now, the card's text colour now)` and the knob `readable` of that. |
| Slider | Track over the full width, 14 high, radius 7, centred vertically, `card2` (on: `onbg_pr`). Fill from the left in `acc` (on: `ion`). Knob 22 round in `tx` (on: `ontx` with a 2 px ring in `onbg`). The value is `min + amount * (max - min)` rounded to `step` and clamped. Under a finger, `amount = clamp((finger - start) / L, 0, 1)`: `start` is the left edge of the rectangle and `L` its width. (2) In every look and for every `dir`, `start` and `L` are the start edge and the length along the axis (next row); only a slider with a `track` has its own formula (below). |
| (2) Slider, `dir` | The axis. 0: the start is the left edge. 1: the bottom edge. 2: the top edge. Below, `L` is the length of the rectangle along the axis and `S` its other side; "fill from the left" reads "from the start". With `dir` 1 or 2 and `look` 0 the track is 14 wide and centred across. |
| (2) Slider, bar | `look` 1. Track: the whole rectangle, radius `R = min(r2, S div 2)`, `card2` (on: `onbg_pr`). Fill from the start edge, `round(amount * L)` long, same radius; a fill shorter than `2R` is drawn `2R` long; no fill at amount 0. No knob. With `change`: a handle line, 4 along the axis and `S - 16` across, radius 2, its far edge 8 before the end of the fill, colour `readable(fill colour)`; not drawn while the fill is shorter than 28. `icon` (only when `S >= 32`): an icon 24 with its centre 24 from the start edge, centred across, in `readable(fill colour)` when the fill is at least 48 long, else `tx2` (on: `ontx`). |
| (2) Slider, `c` | The fill is `legible(c, track colour, the card's text colour now)`. Not with `track`. |
| (2) Slider, `track` | `n` colours. The track has the shape of its look (14 thick with radius `R = 7`, or the whole rectangle with the bar's `R`). `x0 = R` and `x1 = L - R` along the axis, from the start. Three parts that do not overlap: the start cap, which is the part of the rounded track from 0 to `x0`, in colour 1; the end cap, from `x1` to `L`, in colour `n`; and between them `n - 1` pieces with square corners, piece `k` (from 0) from `x0 + floor(k * (x1 - x0) / (n - 1))` to `x0 + floor((k + 1) * (x1 - x0) / (n - 1))`, each fading along the axis from colour `k + 1` to colour `k + 2`. No fill. `amount = clamp((finger - x0) / (x1 - x0), 0, 1)`. When `x1` is not above `x0` the two caps are drawn, there are no pieces and no mark, and the amount is 0. The mark's centre is at `x0 + amount * (x1 - x0)`. Mark, `look` 0: a circle 22, `0xFFFFFF`, with a 2 px border in `0x15181D` inside. `look` 1: a rounded rectangle 12 along the axis and `S + 4` across, radius 6, same colours. Bands of colour between the 16-bit steps are accepted. Drawn faded (40%), the track fades as one picture: no part shows through another. |
| (2) Slider, `nv` and `rate` | `nv` 1: without a value the slider is drawn at full opacity with its track only (no fill, knob, handle or mark) and takes input. `rate` (only without `change`): the value shown is `clamp(value + rate * age, min, max)`, with the age of 4.4; a `rate` without a value counts as 0. It is drawn again at most once a second, and only on the page on screen. |
| Thermostat | In the square of side `s = min(w, h)` centred in the rectangle. Arc centre in the middle, radius `0.36 * s`, from 135° to 405° (open at the bottom), round ends, width `max(8, s / 14) * s / 200`. Track `card2` (on: `onbg_pr`). Value arc `acc2` from 135° over `270° * (value - min) / (max - min)`. Value text centred: no decimals from 1000 up, else at most one; "–" when there is no value. With `change`: two round buttons 36 by 36 at the bottom left and bottom right of the rectangle, `card2`, icons `mdi:minus` and `mdi:plus` 24. (2) `bs`: the buttons are `bs` by `bs`. `c`: the value arc is `legible(c, the card's background now, the card's text colour now)`. `mark` `m`: a filled circle in the card's text colour now, diameter `max(6, arc width - 4)`, centred on the middle line of the arc at `135° + 270° * (m - min) / (max - min)`. It is drawn whenever `m` has a value inside `min` to `max`, also while the thermostat's own `value` has none (a climate device that is off has a temperature and no target); it then fades with the widget. No mark while `m` has no value or lies outside `min` to `max`. |
| Chart | A 1 px line in `line` one pixel above the bottom: it fills pixel row `h - 2` of the rectangle, rows counted from 0 at the top. Line kind: a 3 px line in `acc2` with round joins through the points of `linePoints(values, w, h, 4)`. Bar kind: bars in `acc2` with radius `min(4, bar width / 2)` from `barRects(values, w, h - 2, 4)`. Both functions are in `frontend/logic.js`. (2) `c`: `legible(c, the card's background now, the card's text colour now)` in place of `acc2`. `st` 1, line kind: steps through the same points `(x_i, y_i)`: for each `i` below the last a flat run from `x_i` to `x_(i+1)` at `y_i`, then an upright run at `x_(i+1)` from `y_i` to `y_(i+1)`; each a filled rectangle 3 thick centred on its line and 1 longer at both ends; each of its edges is rounded on its own. `mark` `k`, bar kind: bars before index `round(k)` as usual, the bar at it in `acc`, later bars in `card2`. A `mark` without a value, or with `round(k)` below 0 or past the last bar, is no mark: every bar as usual. |
| Image | Background `card2`, radius `r2`. The icon centred, colour `acc2`. Value 0 or no value: the `placeholder` glyph of `icons.json`. (2) With `c`: the icon is `legible(c, card2, tx)`. |
| (2) Image, badge and bare | The image is **plain** when `c` has no value and the card is neither filled nor on with `lit` 1 or 2 (so: `on` 0, or `lit` 3). This is decided by state, never by comparing colour numbers. `K` is `c` when it has a value; else `tx2` when plain, `ion` when the card is filled, `acc` when it is on with `lit` 1 or 2. `look` 1, badge: a circle of diameter `d = min(w, h)`, centred. Icon: the largest of 72, 48, 28, 24 that is not above `0.6 * d`. Plain: circle `card2`, icon `tx2`. Otherwise: circle `W = mix(K, B, 80)` and icon `legible(K, W, T)`, with `B` the card's background now and `T` the card's text colour now. `look` 2, bare: no box. Icon: the largest of 72, 48, 28, 24 that is not above `min(w, h)`, in `legible(K, B, T)`. With `tap`, pressed: background `card2_pr` (on: `onbg_pr`), radius `r2`. The placeholder and the no-value look are as in `look` 0. |
| (2) Choice | `n` options (with `n` 0 nothing is drawn, 4.3) in `rows` rows: `k = ceil(n / rows)` cells a row, filled row by row. Gap 8 between cells and between rows. Cell width `floor((w - 8 * (k - 1)) / k)`, height `floor((h - 8 * (rows - 1)) / rows)`. When either is below 1 the control is not drawn and is not there for a touch, like a hidden widget. Cell: background `card2` (on: `onbg_pr`), radius `r2`, content as in a button (icon 24, text 15, the button's stacking rule) in the card's text colour now; an option without an icon or without a text shows the other part alone. Selected: background `accf`, content `acct`. Pressed: `card2_pr` (on: `onbg_pr`); the selected cell `accf_pr`. With `cols`: the cell's background is its colour, content `readable` of it; selected: a 3 px border in the card's text colour now, inside. `look` 1: each cell is drawn as a circle of diameter `min(cell width, cell height)`, centred in its cell; the whole cell still takes the touch. |
| (2) Hidden | A widget whose `vis` is 0 or has no value is not drawn and is not there for a touch (4.3, "Who gets a press"). |
| No value | A bound text shows nothing. A switch, slider, thermostat, chart or image whose value is `null` is drawn at 40% opacity and takes no input. (2) Who gets a press that begins on it is in 4.3: a faded control swallows it, a faded widget that only shows leaves it to the card. A `choice`, and a slider with `nv` 1, do not fade. |
| Pressed | Any widget with `tap` shows its pressed look in the same frame as the touch. (2) A card: after 80 ms, see "Card, pressed". |

`thermostatFit(text, s, stroke)` from `render.js`: the inner diameter is
`2 * (72 - stroke / 2) * s / 200` with `stroke = max(8, s / 14)`; the text may
be 0.8 of that wide; each character counts 0.62 em, and `. , :` and space
0.32 em; the size is `min(s / 5, width / em)`. The 0.62 em is an estimate:
Montserrat's digits are up to 0.67 em, so a long number can be wider than
its size allows, which is why the drawn width is checked (thermostat value
above). The tablet's box for the text is `floor(width)` pixels wide.

The tablet's own pieces (question box, message strip, waiting screen) use
`card`, `tx`, `tx2`, `card2` and `accf` with `acct`, text sizes 15, 16, 18,
20 and 34. (2) They use the theme of the page on screen.

The font is Montserrat Medium (SIL Open Font License), one weight for all
text. The editor's tablet previews use the same font file. The browser card
uses Home Assistant's font in three weights. That difference is accepted.

### 4.8 (2) Pages: detail pages and page themes

| Key of a page | Type | Meaning |
|---|---|---|
| `sub` | 0 or 1 | 1: a detail page. 0 or absent: a normal page. |
| `ttl` | whole number | Detail pages only: seconds without a touch after which the tablet returns. 0: never. Otherwise 5 to 3600. Default 60. The count stands still while a finger is down or the question box is open. |
| `theme` | object | Any keys of the top-level `theme`. On this page they replace the layout's theme; a key that is missing keeps the layout's value. |

Detail pages. A detail page holds the full controls of one card. It stands
in for a popup: nothing is drawn over a page, and opening one costs what a
page switch costs.

- A page is a detail page when it has `sub` 1 and is not page 0. `sub` on
  page 0 is ignored, so every layout has a normal page.
- It is opened by `{"go": page}` in a `tap` or a `hold`.
- Swipes. A swipe is a press that has travelled 48 px or more sideways,
  with at least twice as much sideways as up-and-down travel
  (`timing.swipe_px`). There is no time limit. On a normal page a swipe to
  the left shows the next normal page and one to the right the one before.
  The step wraps from the last normal page to the first and never lands on
  a detail page. A press that began on a slider with `change` is never a
  swipe.
- The tablet remembers the normal page it came from, the origin. A `go` from
  one detail page to another keeps the origin.
- It returns to the origin on: a press on the side bar's back entry (4.7), a
  swipe to the right, `tap: {"back": 1}`, or `ttl` seconds without a touch.
  A swipe to the left does nothing.
- After a layout switch the tablet never shows a detail page. If it was on
  a detail page: it shows the origin when that page index still exists and
  is a normal page in the new layout, else page 0. If it was on a normal
  page and that index is a detail page in the new layout: page 0. After a
  restart it shows page 0.
- HA puts detail pages after the normal pages and sends no `nav` entry for
  one.

Page themes. The side bar, the question box, the message strip and every
card on the page use the page's theme. A card's `style` still goes on top.

## 5. Sending a layout

1. HA splits the DL bytes into chunks of at most `min(16000, caps.max_chunk)`
   bytes. A chunk never ends inside a multi-byte character.
2. HA calls `tab_layout(hash, seq, total, size, data)` for `seq` 0 to
   `total - 1`, in order. `size` is the byte length of the whole layout.
3. HA calls `tab_commit(hash, auth)`.
4. HA asks `tab_status` until the layout is on screen (below).

Tablet rules (`fixtures/chunks.json`):

- `seq` 0 always starts a new transfer. It drops an unfinished transfer and a
  committed layout that is still being built. The layout on screen is not
  touched. `tab_layout` never answers `busy`.
- `tab_layout` errors: `too_big` (size over the limit), `memory` (no room),
  `order` (seq is not the next one, or hash/total/size differ from seq 0),
  `size` (more bytes than announced, or a chunk whose `data` is longer than
  the tablet's `caps.max_chunk`, which is at most 16000 bytes).
- A `seq` 0 call drops the unfinished transfer and any build in progress
  first, also when it then answers an error; `build` becomes empty. Its
  header is checked in this order, before anything is allocated: `too_big`
  (`size` over 262144), `order` (`hash` not 16 lower-case hex characters, or
  `total` below 1), `size` (`size` below 1, more bytes than `size`, or `data`
  over `caps.max_chunk`), `memory`. A refused `seq` 0 keeps no transfer, so
  a commit after it answers `incomplete`.
- A later chunk is checked for `order` first; `order` changes nothing. Then
  a chunk that brings the total over `size`, or whose `data` is over
  `caps.max_chunk`, answers `size` and drops the transfer, so a commit after
  it answers `incomplete` and HA starts again from `seq` 0.
- `tab_commit` errors, checked in this order: `auth`, `incomplete` (no
  finished transfer with this hash), `hash` (bytes do not hash to `hash`),
  `parse` (not valid JSON of this shape), `version` (`v` is not 1 or 2),
  `limits` (too many pages, normal pages, slots or widgets), `memory`.
- `tab_commit` answers as soon as the layout is checked and parsed. The tablet
  then builds the new screens in the background and switches in one step. The
  old layout stays on screen and stays live until then. It does not switch
  while a finger is on the screen, for at most 3 s (section 7.4).
- After a successful commit the new layout is **staged**. `tab_status` shows
  its hash in `staged`. `tab_set` for the staged hash is accepted and kept, so
  the first frame has values.
- When the build ends, `staged` becomes empty. Either `layout` is the new
  hash, or the old layout stays and `build` says why (`memory`, `build`).
- A commit of the hash that is already on screen answers success and changes
  nothing.
- A commit of the hash that is staged and still being built (HA lost the
  first answer and asks again) answers success once `auth` passes, and
  nothing changes: the same build carries on. If that build has already
  failed, nothing is staged any more and the commit answers `incomplete`.
- The tablet keeps the page index across a switch when that page still exists.
  (2) Not on a detail page: section 4.8.
- (2) Flash writes. The tablet keeps a count of the writes it may make: 12
  after a restart, one more for every 2 hours of running, never above 12
  (`timing.cache_bucket`, `timing.cache_refill_s`). Storing a layout takes
  one. With none left, the layout is shown and used as any other, and
  stored when a write is free again. Erasing the stored layout (after
  `tab_clear`, or for a layout too large to keep) takes none and is never
  put off.
- (2) A layout larger than `caps.max_stored` is shown and used but not
  stored, and the older copy is erased. After a restart such a tablet waits
  for HA.
- `tab_clear` drops the layout, the staged layout and the stored copy.

HA rules:

- One transfer per tablet at a time. If the wanted hash changes during a
  transfer or a build, HA starts again from `seq` 0.
- After `tab_commit` succeeds HA calls `tab_status` after 0.15 s, 0.3 s, then
  every 0.5 s, for at most 60 s (`status_verdict` in the reference code):
  - `layout` is the wanted hash: the layout is on the tablet.
  - `staged` is the wanted hash: still building. Ask again.
  - otherwise: the build failed with the code in `build` (or `replaced` when
    it is empty). This counts as a failure.
- HA reports "on the tablet" only after that confirmation, or when `tab_hello`
  reports the wanted hash.
- Retry after a failure: 5 s, 15 s, 60 s, then every 5 minutes, and at once
  on reconnect.
- No automatic retry after `too_big`, `limits`, `version` or `parse`. They
  cannot succeed for the same layout and caps. HA tries again when the layout
  or the tablet's caps change.
- `auth`: run the handshake again (section 3).

## 6. Pairing and signed calls

Each tablet has one 32-byte secret. HA makes it with a secure random source.
It signs input (section 7) and HA's calls (6.2). It never appears in plain
form in a message or log.

### 6.1 `tab_pair(nonce, wrapped, kid)`

- `nonce`: 32 lower-case hex characters, fresh and random for every
  `tab_pair` call. It has nothing to do with the session nonce and must not
  be one. (The wrapping is an XOR pad. A reused nonce with two secrets would
  leak their XOR.)
- `psk` = the tablet's ESPHome API encryption key (32 bytes). HA reads it from
  the ESPHome config entry. The tablet reads it from its API server.
- `pad` = HMAC-SHA256(key = `psk`, message = `"apollo-tab1 wrap v1|<mac>|<nonce>"`).
- `wrapped` = hex of (`secret` XOR `pad`), 64 characters.
- `kid` = first 16 hex characters of HMAC-SHA256(key = `secret`,
  message = `"apollo-tab1 kid v1"`).

The tablet unwraps, checks `kid`, stores the secret in flash, ends the current
session and answers. Errors: `needs_encryption` (the tablet has no API key),
`bad_key` (kid does not match, or a field has the wrong shape). See
`fixtures/pair.json`.

- `tab_pair` needs no `auth`: only someone who holds the API key can make a
  `wrapped` and `kid` that fit together.
- No API encryption means no pairing. Layout and state still work, unsigned.
  Input does not: the tablet sends none, and HA accepts none.
- A tablet that holds a secret but has no API key any more (reflashed without
  encryption) ignores that secret until a key is back: `tab_hello` answers
  `enc` 0 and an empty `kid`, any `auth` is accepted, `tab_pair` answers
  `needs_encryption`, and no input is sent (`fixtures/auth.json`
  "no_api_key"). HA does not sign calls to it and drops any input event
  from it.
- HA pairs again when `tab_hello` reports another `kid` or none, when a signed
  call answers `auth`, and when an admin asks for it. A new secret replaces
  the old one on both sides.

### 6.2 Signed calls (`auth`)

`auth` = `"<n>.<sig>"`.

- `sig` = first 32 hex characters of HMAC-SHA256(key = `secret`, message =
  `"apollo-tab1 call v1|<mac>|<nonce>|<n>|<action>|<body>"`), UTF-8.
- `<nonce>`: the session nonce. For `tab_hello` it is the nonce argument of
  that call.
- `<n>`: 0 for `tab_hello`. For the other calls a counter that starts at 1
  after each `tab_hello` and goes up with every signed call HA writes. Gaps
  are fine.
- `<action>`: the action name, for example `tab_commit`.
- `<body>`:

| Action | Body |
|---|---|
| `tab_hello` | empty |
| `tab_commit` | the `hash` argument |
| `tab_set` | the `data` argument, byte for byte |
| `tab_ack` | `<n of the ack>\|<1 or 0>\|<code>` |
| `tab_clear` | empty |

Tablet rules (`fixtures/auth.json`, `check_auth` in the reference code):

- Not paired: accept any `auth`.
- Paired: refuse unless the shape is right, the signature matches (constant
  time), and, except for `tab_hello`, `n` is above the last accepted `n` of
  this session. Then remember `n`.
- Paired and no session yet on this boot: refuse everything except
  `tab_hello`, `tab_status`, `tab_pair` and `tab_layout`.
- A refused call answers the error `auth` and changes nothing. A refused
  `tab_ack` is ignored. A refused `tab_hello` answers its data with
  `"session":0`.

What stays open, on purpose: `tab_status` (read only), `tab_layout` (bytes do
nothing until a signed commit; a stranger can only disturb a transfer, and HA
sends it again), and everything on a tablet without API encryption.

## 7. Input

### 7.1 Payload

```
1|<mac>|<nonce>|<counter>|<layout hash>|<widget id>|<event>|<confirmed>|<value>
```

- Nine fields joined by `|`. ASCII only. At most 200 characters.
- `nonce`: the session nonce.
- `counter`: starts at 1 after each new session, goes up by 1 per input.
- `layout hash`: the layout on screen when the finger went down.
- `event`: `t` (tap) or `c` (change).
- `confirmed`: `1` if the person said yes to a question on the tablet, else `0`.
- `value`: empty for a tap. For a change, the number in wire form (section 4.1).

### 7.2 Signature

`s` = first 32 lower-case hex characters of HMAC-SHA256(key = `secret`,
message = the payload bytes).

### 7.3 What HA does (`fixtures/input_events.json`)

Checks, in this order. The first failure decides.

| Check | Verdict |
|---|---|
| `d` is an ASCII string; `s` is exactly 32 lower-case hex characters; 9 fields; at most 200 characters | `malformed` |
| Field 1 is `1` (`input_version` in `contract.json`; the same in versions 1 and 2) | `version` |
| MAC belongs to a known tablet | `wrong_tablet` |
| The tablet is paired, and its last `tab_hello` said `enc` 1 | `not_paired` |
| Signature matches (constant-time compare) | `bad_signature` |
| Nonce is the current session's | `stale_session` |
| Fields have the right shape | `malformed` |
| Counter is above the last accepted one | `replay` |
| Layout hash is one HA keeps bindings for on this tablet | `stale_layout` |

(2) What HA checks before it runs an input that passed the table:

- The widget id of a `t` event may be a card's id. HA runs it only when
  that card has a tap action in HA's copy of the layout. A `t` for a card
  without one, and a `c` for a widget without `change`, run nothing.
- A `c` event must carry a finite number that is inside the widget's `min`
  and `max` and on its step grid (`min + k * step`, within 0.0015; `max`
  itself always counts). A step of 0 or less has no grid: only the range
  is checked (the tablet does not snap then either). Where HA sent `min`,
  `max` or `step` as live values, it checks against the values it last
  sent to this tablet, and refuses when it has sent none.
- A `c` event from a `choice` must carry a whole number from 0 to one below
  the number of options HA compiled for that widget. HA takes the option
  from its own copy of the list; the tablet never names an option.

An input that fails one of these gets `tab_ack(counter, false, "failed")`.
`fixtures/input_v2.json` has a case for each.

Which hashes HA keeps bindings for: the wanted layout, and the one that was on
screen before it, until `tab_status` (or `tab_hello`) confirms the switch.
Then only the wanted one. So a tap on the old layout during a build is still
answered from the old layout's bindings: it runs the old layout's action, or
nothing when the card's Component changed since (below). After an HA restart
HA keeps bindings only for layouts it compiled in this run. If the tablet
reports the hash HA compiles for its dashboard, that is enough and nothing
is sent again.

- `ok`: store the counter, run the action under the integration's rules, then
  call `tab_ack(counter, ok, code, auth)`.
  - The bindings name a Component (a card's definition in HA) and one of its
    actions by name. HA runs the action only while that Component is the one
    the layout was made from. If the Component changed since, the same name
    may stand for another action than the screen shows: HA runs nothing and
    acks `stale`, or `denied` when the Component is no longer allowed.
  - This holds for every layout HA keeps bindings for: the old one, and the
    wanted one until HA has made it again from the changed Component.
- `stale_layout`: store the counter and call `tab_ack(counter, false,
  "stale")`. Start a send only if none is running and no build is being
  watched.
- Every other verdict: drop the event. No ack. Count it.
- After `stale_session` (the signature was valid, so it is the real tablet)
  HA starts a new session with `tab_hello`, at most once every 10 s.
  `bad_signature` starts nothing: anyone can cause one.

Ack codes: empty (done), `confirm` (HA needs a yes first: ask, then send again
with confirmed 1), `denied` (not allowed), `failed` (the action failed),
`stale` (the layout or the Component changed), `busy` (too many inputs; HA
accepts 10 per second).

### 7.4 What the tablet does

- Not able to send: send nothing and show why for a moment, checked in
  this order. HA not connected: the Wi-Fi note of section 11 that fits
  while there is no Wi-Fi, otherwise "Home Assistant is not connected". No
  API key: "Touch is off: this tablet is not protected". A key but not
  paired: "Not paired with Home Assistant". No session on this connection
  yet: "Home Assistant is not connected", and the tablet knocks (2.2).
- A control without a value yet (a `null` slot, for example before the
  first `tab_set`) is drawn faded. While the tablet can send, it takes no
  input. While it cannot, a tap on it shows why, as above.
- Policy 0 (optimistic): show the new state at once. Go back if the ack says
  not ok or no ack comes within 4 s.
- Policy 1 (pulse): flash the button. No state.
- Policy 2 (progress): show "working" until a new value arrives or 30 s pass.
- Policy 3 (confirm) or `cf`: ask first. Never show a new state before HA
  sends it.
- Ack `denied`: show "Not allowed on this tablet" for a moment.
- Sliders send once, on release. Thermostat buttons send on each press.
- A new layout waits while a finger is on the screen, for at most 3 s
  (section 5). When the 3 s end during a slider drag, the drag ends as if
  the finger lifted then: the slider sends its value, with the hash of the
  layout it started on (7.1). A slider that asks first sends nothing then
  and shows "The dashboard changed. Try again" for a moment. When touch
  cannot be sent, it shows why, as above.

(2) Version 2:

- Who gets a press, for a tap and for a hold, is in the table of 4.3.
- A card with `tap` follows the same policies. Policy 0 with a bound `on`
  that has a value: the card shows the other state at once, and goes back
  if the ack says not ok or none comes within 4 s. Policy 0 without `on`,
  or while `on` has no value, and policy 2: the waiting outline (4.7).
  Policy 1: the card's pulse. Policy 3 or `cf`: the question, then the
  outline.
- An optimistic bool is shown per slot inside its card: while a tap shows a
  flipped value for a slot, the card's `on`, every switch `value` and every
  button `value` of that card that is bound to the same slot show it too.
  So the switch in the corner of a tile and the tile agree.
- A button with a bound `value` and policy 0 shows the other state at once,
  like a switch.
- `choice`: it sends when the finger lifts inside the cell it went down in.
  Policy 0 shows the tapped option as selected at once, with the same way
  back. Policy 1 flashes the tapped cell (`accf` with `acct`, 300 ms).
  Policy 2: a 2 px outline around the control until a value of the card
  changes, or 30 s. Policy 3 or `cf`: the question, then the index is sent.
  A page swipe may start on a `choice`.
- Hold: a press that stays down 500 ms and has moved less than 12 px from
  where it began opens the `hold` page that the table of 4.3 names. Nothing
  is sent. The release after it is not a tap and not a swipe. No hold page
  opens while the hold-to-erase watch runs (for a touch that starts in the
  first 10 s after power-on). Such a press stays an ordinary press however
  long it lasts: released before the erase question opens, it is a tap, as
  in version 1.
- A press that starts on a slider with `change` is never a page swipe, also
  on an upright slider.
- A widget that has the press (4.3) and becomes hidden (`vis`), faded (its
  value goes away) or unavailable (`un`) while the finger is down loses
  the press: the release sends nothing, also when the widget is shown
  again before the finger lifts. A press that is the card's stays the
  card's when a widget under the finger that only shows fades or hides;
  it is lost when the card turns `un`. An input already sent still gets
  its ack.
- On a card with `un` 1 nothing is sent. While the tablet cannot send, a
  tap on a card with `un` 1 says why, as for a control without a value.

## 8. State

`tab_set(data, auth)`, where `data` is canonical JSON:

```json
{"h":"<layout hash>","f":1,"v":[[1,"Sofa lamp"],[2,1],[8,20.125],[22,[1,2.5]],[4,null]]}
```

- `h`: the active or the staged layout. Any other text: error `hash`. A
  missing `h`, or one that is not text, is not a `tab_set` at all: `parse`.
- `f`: optional. 1 means: set every slot to `null` first, then apply `v`.
- `v`: list of `[slot, value]` pairs. A slot number outside the layout, or a
  value of the wrong type, is skipped; the rest still applies.
- Errors, checked in this order: `auth`, `parse` (bad JSON, no `h` text, or a
  `v` that is not a list; nothing applied), `hash`.
- HA splits a full snapshot larger than 12000 bytes (its `tab_set` limit,
  section 2.1) over several calls. Only the first has `f`.
- HA sends changes only, at most 10 calls per second per tablet, one in
  flight. (2) Two exceptions, because the tablet counts on from the moment
  of a write (4.4). A slot fed by a clock or by a position is sent every
  time HA works it out again, also when the value is the same as the last
  one sent. And a new value for a widget's `rate` always travels in the
  same `tab_set` as a fresh value for that widget's `value`; when a
  snapshot is split over several calls, the two stay in one call. A tablet
  that gets a new `rate` without a value keeps counting from the last
  write of the value.
- After `hash` HA runs the handshake again.
- HA sends a full snapshot after every handshake, after every commit, and
  whenever the dashboard's bindings changed, even when the layout hash did
  not (section 4.4).

See `fixtures/state_stream.json`. Each step lists the payloads and the slot
values the tablet must hold afterwards. The fixture tablet is not paired, so
`auth` is empty there.

## 9. Versions

- `proto` in this document is 2. A tablet may speak 1 only (engine 0.1.0)
  or 1 and 2. HA speaks both. `v` of the device layout is 1 or 2.
- HA and a tablet can talk when their ranges share a version, and HA speaks
  the highest one they share. A tablet that answers `[2, 2]` or `[2, 3]`
  gets version 2. One that answers `[3, 4]` is `unsupported`.
- Version 2 differs from version 1 only in the device layout (section 4).
  Field 1 of the input payload (7.1) and of the knock (2.2) is
  `input_version`, which is 1 in both. It is not `proto`.
- Additions that an old side can ignore do not change the version: a new
  optional key that only changes a look, a new value of a look key (4.3), a
  new error code, a new icon level, a new widget kind behind `caps.w`.
- A control whose sent value gets a new meaning is a new kind, never a new
  key on an old kind. An old engine then leaves it out and cannot send a
  number that HA would read wrongly.
- Anything else raises `proto`. HA keeps version 1 for as long as it ships
  the cards of version 1.

## 10. Fixtures

| File | Use |
|---|---|
| `layout_small.source.json` | A dashboard config, its layout v1, bindings and warnings. HA test input. |
| `layout_small.dl.json` | The exact device layout bytes. HA must produce them; the tablet must load them. |
| `layout_small.meta.json` | Hash, size and the slot plan (device slot to source slot and type). |
| `layout_all_cards.*` | The same for a dashboard that uses all 16 cards of version 1 and its 9 widget kinds, on 3 pages. |
| `layout_all_cards.nochart.*` | Down-levelled for a tablet without `chart`. |
| `chunks.json` | A layout sent in 3000-byte chunks, plus failure cases (order, size, hash, parse, version, limits, memory), the `seq` 0 header order, a new transfer or a bad header during a build, and repeated commits. The `version` case carries `"v": 3`. |
| `status.json` | `tab_status` responses and what HA concludes; "knock": what HA does with a knock. |
| `state_stream.json` | Sample evaluated values, their wire form, and a stream of `tab_set` payloads with the expected slot values after each. |
| `input_events.json` | Events with good and bad signatures, replays, old sessions, odd characters; expected verdict for each, fed in order. Cases with `widget_rect` are also what the tablet must emit when that rectangle is pressed. |
| `pair.json` | Wrapping vectors and failure cases. |
| `auth.json` | Signed call vectors: good ones, replays, wrong body, wrong session, an unpaired tablet, a repeated `tab_hello` nonce, a tablet without an API key. |
| `hello.json` | Handshake responses and what HA must do next, for a tablet of version 1. The case of a tablet that is too new answers `[3, 4]`. |
| `layout_v2_kit.source.json`, `.dl.json`, `.meta.json` | (2) A layout v2 written by hand in the reference code, with every key and kind of version 2 at least once, on 3 normal pages and 2 detail pages. It needs no card file. HA must produce the bytes from the source; the tablet must load and draw them. |
| `layout_v2_kit.nochoice.dl.json`, `.nochoice.meta.json` | (2) The kit down-levelled for a tablet whose `caps.w` lacks `choice`. |
| `layout_v2_cards.source.json`, `.dl.json`, `.meta.json` | (2) A dashboard that uses every card of the first version 2 library. |
| `layout_v2_cards.v1.dl.json`, `.v1.meta.json` | The same dashboard for a tablet that answers `proto [1, 1]` with the caps of engine 0.1.0: what tablets in the field get. It holds only keys of version 1. |
| `layout_v2_cards2.*`, with its `.v1.*` pair | (2) The same two for the cards added after the first library. A file of its own, so the first is never edited. |
| `maths.json` | (2) The table `linear`. Vectors for `mix` (with every exact half of each weight in use), `lum`, `contrast`, `readable`, `legible`, `blend` at 0.82 (with every exact half, and the pairs a fused multiply-add gets wrong), the card colours of 4.7 for every `lit` with and without `tint`, the circle and the icon of a badge in each state (plain, filled, on with `lit` 1, with `c`), the label size picked for a `px` and a text, the clock text (also for a negative and a very large value), slider value to position and back for every `look`, `dir` and `track`, the pieces of a track, the cells of a `choice` (also with no option), the steps of a chart; and each of these for a rectangle that is 0 wide, 1 px, or shorter than its corners, and for `min` equal to `max`. The themes and the card styles the vectors name are in the file (`themes`, `styles`), in device form. Tested by the tablet, by `frontend/logic.js` and by `maker`. |
| `commit_v2.json` | (2) Layouts at the limits of version 2 with the `tab_commit` answer for each: 64 pages and 65; 20 normal pages and 21; `sub` on page 0; 21 pages of which one has `"sub": 0` (it is normal: `limits`); `v` 3. And what HA compiles for a tablet without `caps.max_pages`, and for a `track` of 8 and 9 colours, a `choice` of 16 and 17 options and option texts of 40 and 41 bytes (`cuts`); the tablet's answer to the same lists uncut. |
| `input_v2.json` | (2) Presses on `layout_v2_kit`, one case for every row of "Who gets a press" (4.3) and every bullet of 7.4: a card tap, a tap on a child, on a thermostat's body and on its buttons, a `choice` cell and a gap, an upright slider, a hold, the back entry, a press on a hidden part, on a faded control (nothing), on a faded part that only shows (the card's) and on an unavailable part, a part hidden while the finger is down, a card whose `on` has no value, a drift of 20 px, a finger that drifts 13 px and comes back (no tap, no hold), a slow swipe that starts on a card. For each: the events the tablet must emit, or none, and the page it must show. With signed payloads for HA, as in `input_events.json`, and HA's own cases: field 1 is `2`, a value out of range, a value off the step, a value between steps for a widget whose step is 0 (accepted), a live `step` that was never sent, a `c` for a widget with `tap`, a `t` for a card without a tap. |
| `state_v2.json` | (2) A `tab_set` stream for `layout_v2_kit`: a colour slot with good and bad values, `vis`, `un`, a clock value and a `rate`; an equal value written again (the age starts again); a new `rate` with and without a value; a full snapshot (`f` 1); numbers of 1e9, -1 and 0.5 for a colour, a `choice` index and a `mark`; a thermostat `mark` with a value while the thermostat's own value has none (the mark is drawn, faded); a chart `mark` of -1 and one past the last bar (no mark); a label's `c` slot. With the time between steps and what each widget must show after each. Also "colours": values as HA finds them and the wire value of each, or `null`. |
| `hello_v2.json` | (2) Handshake responses and what HA must do next (which layout version it compiles, which hash it expects): a tablet that answers `[1, 2]` with `engine_caps`; `[1, 1]`; `[2, 2]`; `[2, 3]`; `[1, 2]` without `choice` in `caps.w`; `[1, 2]` without `caps.max_pages`; `[1, 2]` with `enc` 0. |

A case of `input_v2.json` has `page` (the page on screen), `slots` (the
values in force, as `[slot, value]` pairs), `touch` (a list of `[ms,
"down" | "move" | "up", x, y]`), and where needed `sets` (`[ms, [[slot,
value], ...]]`: a `tab_set` that arrives while the finger is down) and
`acks` (`[ms, ok, code]`). It expects `events` (each `[widget id, event,
confirmed, value]`, in order, often none), `end_page` (the page shown at
the end) and `question` (0 or 1). A case with `payload` and `verdict` is
also input for HA: `counter` is the tablet's counter for the first event,
`run` whether HA runs the input, and `sent` the values HA last sent (else
the file's own `sent`).

To make them again: `python -B reference/gen_fixtures.py <custom_components/apollo_tab> <this folder>`
(needs PyYAML and the integration's `maker` package and library; it writes only
into this folder). Then `python -B reference/check_fixtures.py`.
`reference/gen_icons.py` makes `icons.json` from the MDI font in the firmware
repository.

## 11. What the tablet's screen says

`screens.json` holds the tablet's own words, exactly as it shows them. The
firmware owns them (`engine/tab_state.h`); TAB-1's checks compare that file
and the screens the host tests draw with `screens.json`, and HA's panel
tests read the tablet's words from it. A change to one of them is a change
to this folder.

- `hotspot`: the set-up hotspot's name (`wifi: ap: ssid:` in both firmware
  files), `{hotspot}` below.
- `waiting`: the waiting screen, one entry per state, with `when`,
  `headline` (large) and `step` (the line under it). Under the tablet's
  name (`{name}`: the ESPHome friendly name with the last six characters of
  the MAC; HA gives the tablet this name when it adds it).
  - `erased` also has `step2`, a second line under the step, and
    `step_long_name`, the step the tablet shows instead when the step with
    its name does not fit on one line (or it has no name).
  - Only one state at a time. `add` and `erased` show only without an API
    key, in the set-up window, while HA is not connected. A tablet with its
    key never shows either, and nothing on the network can make it.
- `notes`: the Wi-Fi notes in the message strip over a dashboard, while HA
  is not connected. A touch that cannot be sent then shows the note that
  fits (7.4).

| State | Headline | Step |
|---|---|---|
| `hotspot` | Set up Wi-Fi | Join the Wi-Fi “{hotspot}” from a phone |
| `connecting` | Connecting to Wi-Fi… | If it cannot connect, its set-up hotspot comes on within 2 minutes |
| `add` | Add this tablet in Home Assistant | It shows up by itself in Settings > Devices & services |
| `erased` | Confirm this tablet in Home Assistant | In Settings > System > Repairs, confirm only “Authentication expired for {name}”; second line: If this Home Assistant never had this tablet, add it in Settings > Devices & services |
| `starting` | Waiting for TAB-1 in Home Assistant | If Home Assistant has finished starting, open TAB-1 there and turn this tablet on |
| `turn_on` | Ready to turn on | Open TAB-1 in Home Assistant and turn this tablet on |
| `wait_ha` | Waiting for Home Assistant | Check that Home Assistant is running and lists this tablet in Settings > Devices & services |
| `loading` | Connected to Home Assistant | Getting the dashboard… |
| `pick` | Nothing to show yet | Open TAB-1 in Home Assistant to see what this tablet should show |
| `closed` | Setup not finished | Restart the tablet to finish setup |
| `no_wifi` | No Wi-Fi | Turn the tablet off and on, then join “{hotspot}” from a phone |
