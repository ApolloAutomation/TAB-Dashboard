# TAB-1 tablet contract, version 1

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
**Layout v1** is what `maker/convert.py` produces. **Device layout** (DL) is
what the tablet receives.

## 1. Roles

- HA decides everything. The tablet draws and reports touches.
- The tablet never learns entity ids, action names or templates.
- An input from the tablet names a widget id. HA looks the action up in its own
  copy of the layout it sent. A layout that HA did not send can never run an
  action.
- One HA per tablet. Two Home Assistant installs that both manage the same
  tablet take it from each other by pairing again. HA logs a warning when that
  happens (section 3) and does it at most once a minute.

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
{"proto":[1,1], "engine":"0.1.0", "boot":3,
 "layout":"a9326c033e45f2f4", "kid":"<16 hex or empty>", "enc":1, "session":1,
 "caps":{"w":["heading","card","label","button","switch","slider","thermostat","chart","image"],
         "icons":1, "screen":[1280,800],
         "max_layout":262144, "max_chunk":16000, "max_slots":1024, "max_widgets":2048},
 "mem":{"int":61000,"psram":28000000,"block":16000000}}
```

| Key | Meaning |
|---|---|
| `proto` | Lowest and highest contract version the tablet speaks. |
| `engine` | Engine version text. For display only. |
| `boot` | Boot counter. Also in the knock. |
| `layout` | Hash of the layout on screen, or empty. A staged layout does not count. |
| `kid` | Id of the stored secret (section 6), or empty. Empty when `enc` is 0. |
| `enc` | 1 when the tablet has an API encryption key. |
| `session` | 1 when this call started a session, else 0. |
| `caps.w` | Widget kinds the tablet can draw. |
| `caps.icons` | Icon set level (section 4.5). |
| `caps.max_*` | Limits of this tablet. HA uses the smaller of these and its own. |
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
4. Compile the device layout for these `caps`. If its hash differs from
   `layout`: send the layout.
5. Send a full state snapshot.

Unknown keys in the response are ignored. Missing `caps` keys take
`caps_defaults` from `contract.json`.

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
| `mem` | As in `tab_hello`. |
| `session` | 1 when the tablet has a session on the current API connection, else 0. |

HA uses it to learn when a committed layout is really on screen
(section 5, `fixtures/status.json`), and to check a knock (section 2.2).

## 4. Device layout (DL) version 1

HA compiles layout v1 into a device layout. The tablet does not get layout v1.

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
| `v` | 1 | DL version. |
| `screen` | `[1280,800]` | Pixel size the rectangles assume. |
| `theme` | object | Colours as integers `0xRRGGBB`: `wall card card_pr card2 card2_pr line tx tx2 acc accf accf_pr acct acc2 onbg onbg_pr ontx ion`. Plus `dark` (0/1), `r` (card radius), `r2` (inner radius), `bw` (border width). Roles are in section 4.7. |
| `nav` | list | Side bar entries, at most 8: `{"p": page index, "title": text, "icon": code point}`. `icon` is optional. |
| `pages` | list | At most 20. Each `{"title": text, "w": [items]}`. Page 0 is shown first. |
| `slots` | string | One character per slot: the type of slot 1, 2, 3 and so on. |

Limits and how they are counted:

- Pages: length of `pages`, at most 20.
- Slots: length of `slots`, at most `caps.max_slots` (1024).
- Widgets: every object that has an `id` (headings, cards, and the widgets
  inside cards), at most `caps.max_widgets` (2048).

HA checks all of these and the byte size before it sends anything
(`compile_device_layout` raises `too_big` or `limits`).

### 4.3 Items and widgets

Every item and widget has `id` (unique in the layout, the id used in input),
`t` (kind) and `r` (`[x, y, w, h]` in screen pixels, absolute). The widgets
of a card are absolute too: the card's border `bw` does not move them.

Rectangles (`r`, `hr`) are cut to the 1280x800 screen: the tablet keeps the
part of the rectangle that lies on the screen, and a negative width or
height counts as 0. A number in a rectangle below -4000 or above 4000 is
`parse`. So no widget is ever larger than the screen.

Page items:

| `t` | Keys |
|---|---|
| `heading` | `text`, optional `icon`. |
| `card` | `w` (widgets). Optional: `hr` (header rectangle), `icon`, `title` (text), `on` (bool), `style`. |

`style` overrides theme colours for one card: `bg bg2 tx tx2 acc acc2 acct card2
line onbg ontx` (integers), `r r2 bw`, and `gd` (0 = top to bottom, 1 = left to
right; only with `bg2`). `bg` replaces the theme's `card`.

A card with `on` is drawn in the "on" colours while the value is 1.

Widgets inside a card:

| `t` | Keys | Draws |
|---|---|---|
| `label` | `text` (text), `size` 0/1/2 (small, medium, large) | One line of text, cut to the rectangle. |
| `button` | optional `text` (text), optional `icon` | A press button. |
| `switch` | `value` (bool) | A toggle. |
| `slider` | `value min max step` (numbers) | A horizontal slider. |
| `thermostat` | `value min max step` (numbers) | An arc with the value in the middle. With `change`: a minus and a plus button. |
| `chart` | `value` (list), `kind` 0 = line, 1 = bars | A small graph. |
| `image` | `value` (icon) | An icon, or the placeholder. Pictures come in a later version. |

Interaction keys on any widget:

| Key | Meaning |
|---|---|
| `tap: {"p": n}` | A press sends an input. `n` is the feedback policy: 0 optimistic, 1 pulse, 2 progress, 3 confirm. |
| `tap: {"go": page}` | A press switches to that page. Nothing is sent. |
| `change: {"p": n}` | Slider: releasing it sends an input with the value. Thermostat: each press on minus or plus sends an input with the stepped value. |
| `cf: 1` | The tablet must ask before it sends. |
| `confirm` (text) | The question to ask. Without it the tablet asks "Are you sure?". |

A widget with neither `tap` nor `change` is display only.

### 4.4 Bound fields and slots

A field marked (text), (bool), (number), (list) or (icon) holds either a
constant of that type or `{"s": n}`, a reference to slot `n` (1-based).

| Type | Char | Wire value |
|---|---|---|
| text | `t` | String, at most 255 UTF-8 bytes. |
| bool | `b` | 0 or 1. |
| number | `n` | Number. |
| list | `l` | List of at most 120 numbers. |
| icon | `i` | Code point from `icons.json`. 0 means "draw the placeholder". |

Every slot may also be `null`: "no value". The tablet then draws the widget in
its unavailable look (section 4.7). Before the first `tab_set` all slots are
`null`.

HA gives each (source slot, type) pair its own device slot, so a slot has one
type. HA does the conversion (`coerce` in the reference code): bool follows
`isOn` in `frontend/logic.js`; number follows `toNumber`; an icon name that is
not in the tablet's icon set, and any picture URL, becomes 0.

The device layout holds no entity ids. Two dashboards that differ only in
which entity a card uses have the same bytes and the same hash. HA therefore
never uses the hash to decide whether values or actions changed
(section 8).

### 4.5 Icons

`icons.json` maps `mdi:` names to `[code point, level]`. Level 1 is the set in
this contract. A later contract may add icons with a higher level. It never
removes or renumbers one. The firmware embeds every glyph up to its level and
reports the level in `caps.icons`. HA sends the `fallback` glyph for a fixed
icon above the tablet's level.

### 4.6 Down-levelling

HA leaves out widgets whose kind is not in `caps.w`. The rest of the card stays.
Headings and cards are always sent, whatever `caps.w` lists: a tablet that
speaks this contract draws them. A missing `caps.w` means every kind of this
contract version; an empty list means no kind inside a card.
The hash is taken after down-levelling, so two tablets with different caps can
hold different hashes for the same dashboard. HA supports the current and the
previous contract version.

### 4.7 How it is drawn

The tablet must look like the editor's picture. The reference is
`frontend/render.js` and the `.at-*` rules in `frontend/styles.js` of the
integration, at scale 1. All numbers are pixels on the 1280x800 screen.
Colour names are theme keys; a card's `style` overrides them inside that card.

Fonts. Exactly these sizes exist on the tablet (`fonts` in `contract.json`):

| Use | Size |
|---|---|
| Label small / medium / large (`size` 0 / 1 / 2) | 14 / 18 / 34 |
| Button text | 15 |
| Card header title | 16 |
| Heading text | 20 |
| Thermostat value | The largest of 48, 34, 20, 18, 14 that is not above `thermostatFit` (below). The 48 size holds only `0123456789.,-`, so the "–" for no value takes the largest of 34, 20, 18, 14 that fits. A negative value uses the ASCII `-`. Then, while the text drawn at that size is wider than the text may be (`thermostatFit`'s width), the next smaller of those sizes: 48, 34, 20, 18, 14. Only at 14 is it cut with "…". |
| Icons in headers, headings, buttons, minus and plus | 24 |
| Icons in the side bar | 28 |
| Image widget icon | The largest of 72, 48, 28, 24 that is not above `min(w, h) / 2`. |

The text sizes hold only the characters in `fonts.text_glyphs` (Latin,
Latin-1, Latin Extended-A, dashes, quotes, bullet, ellipsis, euro). Any
other character, for example Greek, Cyrillic, Chinese or an emoji, is drawn
as an empty box, and the editor's tablet preview shows a box there too.

Every text is one line, left aligned unless said otherwise, centred
vertically in its rectangle, and cut with "…" when it does not fit. No text
box ever changes size with its content.

| Part | Drawing |
|---|---|
| Page | Background `wall`. |
| Side bar | Rectangle `[0, 0, 96, 800]`, colour `card`. Always drawn, also with no entries. Entry `i` is a button at `[16, 16 + 72*i, 64, 64]`, radius `r2`, no background, icon 28 in `tx2`. No title text. The entry of the page on screen: background `onbg`, icon `acc`. An entry without `icon` uses `mdi:view-dashboard`. |
| Not connected mark | `mdi:lan-disconnect`, 28, colour `tx2`, centred in `[32, 736, 32, 32]` of the side bar. Shown after 10 s without HA. |
| Heading | Optional icon 24, gap 8, text 20. Colour `tx`. |
| Card | Radius `r`. Border `bw` wide in `line`. Background `card` (or `style.bg`; with `bg2` a gradient from `bg` to `bg2`, direction `gd`). Text `tx`. |
| Card, on | Background `onbg`, border colour `acc`, text `ontx`. |
| Header | In `hr`: icon 24 in `tx2` (on: `ion`), gap 8, title 16. |
| Label | Small: `tx2` (on: `ontx`). Medium and large: the card's text colour. |
| Button | Background `card2`, radius `r2`, padding 6. Icon 24 and text 15, centred, gap 6; side by side, or stacked when both exist and the height is 64 or more. Text colour `tx`. Pressed: `card2_pr` (on: `onbg_pr`). Pulse: background `accf`, content `acct`, for 300 ms. Waiting (policies 0 and 2 until the answer): a 2 px outline in `acc` (on: `ion`). |
| Switch | Track `min(w, 64)` by `min(h, 36)`, at the left of the rectangle, centred vertically, fully round, `card2`. Knob 28 round, 4 from the left, `tx2`. Value 1: track `acc` (on: `ion`), knob 4 from the right, `acct` (on: `onbg`). |
| Slider | Track over the full width, 14 high, radius 7, centred vertically, `card2` (on: `onbg_pr`). Fill from the left in `acc` (on: `ion`). Knob 22 round in `tx` (on: `ontx` with a 2 px ring in `onbg`). The value is `min + amount * (max - min)` rounded to `step` and clamped. |
| Thermostat | In the square of side `s = min(w, h)` centred in the rectangle. Arc centre in the middle, radius `0.36 * s`, from 135° to 405° (open at the bottom), round ends, width `max(8, s / 14) * s / 200`. Track `card2` (on: `onbg_pr`). Value arc `acc2` from 135° over `270° * (value - min) / (max - min)`. Value text centred: no decimals from 1000 up, else at most one; "–" when there is no value. With `change`: two round buttons 36 by 36 at the bottom left and bottom right of the rectangle, `card2`, icons `mdi:minus` and `mdi:plus` 24. |
| Chart | A 1 px line in `line` one pixel above the bottom: it fills pixel row `h - 2` of the rectangle, rows counted from 0 at the top. Line kind: a 3 px line in `acc2` with round joins through the points of `linePoints(values, w, h, 4)`. Bar kind: bars in `acc2` with radius `min(4, bar width / 2)` from `barRects(values, w, h - 2, 4)`. Both functions are in `frontend/logic.js`. |
| Image | Background `card2`, radius `r2`. The icon centred, colour `acc2`. Value 0 or no value: the `placeholder` glyph of `icons.json`. |
| No value | A bound text shows nothing. A switch, slider, thermostat, chart or image whose value is `null` is drawn at 40% opacity and does not react to touch. |
| Pressed | Any widget with `tap` shows its pressed look in the same frame as the touch. |

`thermostatFit(text, s, stroke)` from `render.js`: the inner diameter is
`2 * (72 - stroke / 2) * s / 200` with `stroke = max(8, s / 14)`; the text may
be 0.8 of that wide; each character counts 0.62 em, and `. , :` and space
0.32 em; the size is `min(s / 5, width / em)`. The 0.62 em is an estimate:
Montserrat's digits are up to 0.67 em, so a long number can be wider than
its size allows, which is why the drawn width is checked (thermostat value
above). The tablet's box for the text is `floor(width)` pixels wide.

The tablet's own pieces (question box, message strip, waiting screen) use
`card`, `tx`, `tx2`, `card2` and `accf` with `acct`, text sizes 15, 16, 18,
20 and 34.

The font is Montserrat Medium (SIL Open Font License), one weight for all
text. The editor's tablet previews use the same font file. The browser card
uses Home Assistant's font in three weights. That difference is accepted.

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
  `parse` (not valid JSON of this shape), `version` (`v` is not supported),
  `limits` (too many pages, slots or widgets), `memory`.
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
- `tab_clear` drops the layout, the staged layout and the stored copy.

HA rules:

- One transfer per tablet at a time. If the wanted hash changes during a
  transfer or a build, HA starts again from `seq` 0.
- After `tab_commit` succeeds HA calls `tab_status` after 0.15 s, 0.3 s, then
  every 0.5 s, for at most 20 s (`status_verdict` in the reference code):
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
| Field 1 is a version HA speaks | `version` |
| MAC belongs to a known tablet | `wrong_tablet` |
| The tablet is paired, and its last `tab_hello` said `enc` 1 | `not_paired` |
| Signature matches (constant-time compare) | `bad_signature` |
| Nonce is the current session's | `stale_session` |
| Fields have the right shape | `malformed` |
| Counter is above the last accepted one | `replay` |
| Layout hash is one HA keeps bindings for on this tablet | `stale_layout` |

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
- HA sends changes only, at most 10 calls per second per tablet, one in flight.
- After `hash` HA runs the handshake again.
- HA sends a full snapshot after every handshake, after every commit, and
  whenever the dashboard's bindings changed, even when the layout hash did
  not (section 4.4).

See `fixtures/state_stream.json`. Each step lists the payloads and the slot
values the tablet must hold afterwards. The fixture tablet is not paired, so
`auth` is empty there.

## 9. Versions

- `proto` in this document is 1. `v` of the device layout is 1.
- Additions that an old side can ignore (a new optional key, a new error code,
  a new icon level, a new widget kind behind `caps.w`) do not change the
  version.
- Anything else raises `proto`. HA speaks the tablet's highest version that it
  also knows. HA keeps the previous version for one release cycle.

## 10. Fixtures

| File | Use |
|---|---|
| `layout_small.source.json` | A dashboard config, its layout v1, bindings and warnings. HA test input. |
| `layout_small.dl.json` | The exact device layout bytes. HA must produce them; the tablet must load them. |
| `layout_small.meta.json` | Hash, size and the slot plan (device slot to source slot and type). |
| `layout_all_cards.*` | The same for a dashboard that uses all 16 library cards and all 9 widget kinds, on 3 pages. |
| `layout_all_cards.nochart.*` | Down-levelled for a tablet without `chart`. |
| `chunks.json` | A layout sent in 3000-byte chunks, plus failure cases (order, size, hash, parse, version, limits, memory), the `seq` 0 header order, a new transfer or a bad header during a build, and repeated commits. |
| `status.json` | `tab_status` responses and what HA concludes; "knock": what HA does with a knock. |
| `state_stream.json` | Sample evaluated values, their wire form, and a stream of `tab_set` payloads with the expected slot values after each. |
| `input_events.json` | Events with good and bad signatures, replays, old sessions, odd characters; expected verdict for each, fed in order. Cases with `widget_rect` are also what the tablet must emit when that rectangle is pressed. |
| `pair.json` | Wrapping vectors and failure cases. |
| `auth.json` | Signed call vectors: good ones, replays, wrong body, wrong session, an unpaired tablet, a repeated `tab_hello` nonce, a tablet without an API key. |
| `hello.json` | Handshake responses and what HA must do next. |

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
