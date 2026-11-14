export const cardStyles = `
:host {
  display: block;
  height: 100%;
  min-height: 56px;
  font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
}
.card-frame,
.card-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 56px;
  overflow: hidden;
}
.card-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.status {
  box-sizing: border-box;
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  min-height: 56px;
  padding: 16px;
  border-radius: 16px;
  background: var(--ha-card-background, var(--card-background-color, #181C23));
  color: var(--primary-text-color, #E8EAED);
  text-align: center;
}
/* Inside the card's 16 px bottom padding, which never holds a widget. */
.example-chip {
  position: absolute;
  right: calc(16px * var(--at-f, 1));
  bottom: calc(2px * var(--at-f, 1));
  box-sizing: border-box;
  height: calc(12px * var(--at-f, 1));
  padding: 0 calc(6px * var(--at-f, 1));
  border-radius: 999px;
  background: var(--primary-color, #F5B547);
  color: var(--text-primary-color, #101418);
  font-size: calc(10px * var(--at-f, 1));
  line-height: calc(12px * var(--at-f, 1));
  white-space: nowrap;
}
.message-line {
  position: absolute;
  right: 8px;
  bottom: 6px;
  left: 8px;
  box-sizing: border-box;
  padding: 5px 8px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--error-color, #DB4437) 88%, transparent);
  color: white;
  font-size: 12px;
  text-align: center;
}
`;

// The panel's design tokens, set on top of Home Assistant's theme
// variables. They go on the :host of the panel, the confirm dialog and the
// hint in Home Assistant's card editor. The editor sits inside the panel and
// inherits them, so it does not declare them again. The fallbacks are the
// dark colours the panel had before, for a page without Home Assistant's
// variables.
export const tokens = `
  /* colour */
  --tab-bg: var(--primary-background-color, #101418);
  --tab-surface: var(--ha-card-background, var(--card-background-color, #181c23));
  --tab-text: var(--primary-text-color, #e8eaed);
  --tab-text-2: var(--secondary-text-color, #9aa0a8);
  --tab-line: var(--divider-color, #39414d);
  --tab-bar: var(--sidebar-background-color, var(--tab-surface));
  --tab-bar-text: var(--sidebar-text-color, var(--tab-text));
  --tab-stage: var(--secondary-background-color,
    color-mix(in srgb, var(--tab-text) 5%, var(--tab-bg)));
  --tab-field-line: color-mix(in srgb, var(--tab-text) 48%, transparent);
  --tab-accent: var(--primary-color, #f5b547);
  --tab-accent-soft: color-mix(in srgb, var(--tab-accent) 14%, var(--tab-surface));
  --tab-tonal: color-mix(in srgb, var(--tab-text) 8%, transparent);
  --tab-hover: color-mix(in srgb, var(--tab-text) 6%, transparent);
  --tab-press: color-mix(in srgb, var(--tab-text) 12%, transparent);
  --tab-disabled: var(--disabled-text-color,
    color-mix(in srgb, var(--tab-text) 38%, transparent));
  --tab-ok: var(--success-color, #43a047);
  --tab-warn: var(--warning-color, #ffa600);
  --tab-err: var(--error-color, #db4437);
  --tab-info: var(--info-color, #039be5);
  --tab-ok-ink: color-mix(in srgb, var(--tab-ok) 70%, var(--tab-text));
  --tab-warn-ink: color-mix(in srgb, var(--tab-warn) 70%, var(--tab-text));
  --tab-err-ink: color-mix(in srgb, var(--tab-err) 70%, var(--tab-text));
  --tab-info-ink: color-mix(in srgb, var(--tab-info) 70%, var(--tab-text));
  --tab-bezel: #0b0d10;
  --tab-toast: #2b2f36;
  --tab-toast-text: #f1f3f4;
  /* set again by script (applyAccent); these hold until it has run */
  --tab-accent-fill: color-mix(in srgb, var(--tab-accent) 80%, #000);
  --tab-accent-ink: #ffffff;
  --tab-accent-text: var(--tab-text);
  --tab-ring: var(--tab-accent-fill);
  --tab-knob: var(--tab-surface);
  /* type */
  --tab-fs-title: var(--ha-font-size-xl, 1.25rem);
  --tab-fs-head: var(--ha-font-size-l, 1rem);
  --tab-fs-body: var(--ha-font-size-m, 0.875rem);
  --tab-fs-small: var(--ha-font-size-s, 0.75rem);
  --tab-lh-title: 1.4;
  --tab-lh-head: 1.5;
  --tab-lh-body: 1.43;
  --tab-lh-small: 1.33;
  /* spacing */
  --tab-s1: 4px;
  --tab-s2: 8px;
  --tab-s3: 12px;
  --tab-s4: 16px;
  --tab-s5: 24px;
  --tab-s6: 32px;
  /* radii */
  --tab-r-xs: 4px;
  --tab-r-s: 8px;
  --tab-r-m: var(--ha-card-border-radius, 12px);
  --tab-r-pill: 999px;
  --tab-r-dialog: 24px;
  --tab-r-bezel: 20px;
  --tab-r-screen: 10px;
  /* elevation */
  --tab-shadow: 0 4px 12px rgba(0, 0, 0, 0.16);
  --tab-shadow-dialog: 0 12px 32px rgba(0, 0, 0, 0.24);
  /* control heights */
  --tab-control: 40px;
  --tab-control-s: 36px;
`;

// The text settings on each host of the panel's own screens.
const hostType = `
  font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
  font-size: var(--tab-fs-body);
  line-height: var(--tab-lh-body);
  color: var(--tab-text);
  accent-color: var(--tab-accent);
`;

// Touch sizes: every control is 44 px high on a touch screen.
const coarseControls = `
@media (pointer: coarse) {
  :host {
    --tab-control: 44px;
    --tab-control-s: 44px;
  }
}
`;

// A theme may colour Home Assistant's sidebar unlike the page. The two top
// bars take the sidebar's colours, so every token that depends on the text
// or the surface is set again on them; a token is worked out where it is
// declared, so they have to be written out.
export const barTokens = `
.panel-header,
.ed-header {
  --tab-surface: var(--tab-bar);
  --tab-text: var(--tab-bar-text);
  --tab-text-2: color-mix(in srgb, var(--tab-bar-text) 70%, var(--tab-bar));
  --tab-line: color-mix(in srgb, var(--tab-bar-text) 12%, transparent);
  --tab-field-line: color-mix(in srgb, var(--tab-bar-text) 48%, transparent);
  --tab-tonal: color-mix(in srgb, var(--tab-bar-text) 8%, transparent);
  --tab-hover: color-mix(in srgb, var(--tab-bar-text) 6%, transparent);
  --tab-press: color-mix(in srgb, var(--tab-bar-text) 12%, transparent);
  --tab-disabled: color-mix(in srgb, var(--tab-bar-text) 38%, transparent);
  --tab-accent-soft: color-mix(in srgb, var(--tab-accent) 14%, var(--tab-bar));
  --tab-ok-ink: color-mix(in srgb, var(--tab-ok) 70%, var(--tab-bar-text));
  --tab-warn-ink: color-mix(in srgb, var(--tab-warn) 70%, var(--tab-bar-text));
  --tab-err-ink: color-mix(in srgb, var(--tab-err) 70%, var(--tab-bar-text));
  --tab-info-ink: color-mix(in srgb, var(--tab-info) 70%, var(--tab-bar-text));
  color: var(--tab-text);
}
`;

// Buttons, fields, notices and states shared by the panel, the editor, the
// picker and the confirm dialog.
const controls = `
h1,
h2,
h3,
h4 {
  font-size: var(--tab-fs-head);
  line-height: var(--tab-lh-head);
  font-weight: 500;
}
small {
  font-size: var(--tab-fs-small);
  line-height: var(--tab-lh-small);
}
/* Every holder of a tablet picture: the editor's line height must not
   reach the drawing, which has to look as it does on the tablet. */
.page-host,
.tile-preview,
.tablet-pic {
  line-height: normal;
}
/* Buttons. With no kind of their own they are tonal; primary is filled,
   then text, link, icon and danger. */
button,
.button-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  box-sizing: border-box;
  max-width: 100%;
  min-height: var(--tab-control);
  margin: 0;
  padding: 0 16px;
  border: 0;
  border-radius: var(--tab-r-pill);
  background-color: var(--tab-tonal);
  color: var(--tab-text);
  font: inherit;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  --mdc-icon-size: 18px;
  transition: background-color 120ms ease-out, border-color 120ms ease-out, box-shadow 120ms ease-out;
}
/* Hover and pressed lay one more layer over whatever the background is. */
:where(button:not(:disabled), .button-link):hover {
  background-image: linear-gradient(var(--tab-hover), var(--tab-hover));
}
:where(button:not(:disabled), .button-link):active {
  background-image: linear-gradient(var(--tab-press), var(--tab-press));
}
button.primary {
  background-color: var(--tab-accent-fill);
  color: var(--tab-accent-ink);
}
/* On the fill, hover and pressed are layers of the ink colour. */
button.primary:not(:disabled):hover {
  --tab-hover: color-mix(in srgb, var(--tab-accent-ink) 10%, transparent);
}
button.primary:not(:disabled):active {
  --tab-press: color-mix(in srgb, var(--tab-accent-ink) 16%, transparent);
}
button.text {
  background-color: transparent;
  color: var(--tab-accent-text);
}
button.link {
  padding-inline: 4px;
  border-radius: var(--tab-r-xs);
  background-color: transparent;
  color: var(--tab-accent-text);
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
}
button.link:not(:disabled):hover,
button.link:not(:disabled):active {
  background-image: none;
  text-decoration-thickness: 2px;
}
button.icon {
  width: var(--tab-control);
  min-width: var(--tab-control);
  padding: 0;
  border-radius: var(--tab-r-pill);
  background-color: transparent;
  color: var(--tab-text);
}
button.danger {
  border: 2px solid var(--tab-err);
  background-color: var(--tab-surface);
  color: var(--tab-text);
}
button.danger ha-icon {
  color: var(--tab-err-ink);
}
/* Disabled keeps the shape: the words fade, nothing else does. */
button:disabled {
  cursor: default;
  color: var(--tab-disabled);
}
button.danger:disabled {
  border-color: var(--tab-line);
}
button.danger:disabled ha-icon {
  color: var(--tab-disabled);
}
/* A "Turn on with this dashboard" button that moved a moment ago takes no
   press yet, and looks exactly like a disabled filled button meanwhile. */
button.primary:disabled,
.tablet-turn-on[data-settling] {
  background: var(--tab-tonal);
  color: var(--tab-disabled);
  cursor: default;
  transition: none;
}
a:not(.button-link) {
  color: var(--tab-accent-text);
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
}
a:not(.button-link):hover {
  text-decoration-thickness: 2px;
}
/* Fields: text, search and number fields, and list fields. A field's edge
   is all that shows where it is, so it has 3:1 against the card. */
input:not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="color"]),
select,
textarea {
  box-sizing: border-box;
  max-width: 100%;
  min-height: var(--tab-control);
  margin: 0;
  padding: 0 12px;
  border: 1px solid var(--tab-field-line);
  border-radius: var(--tab-r-s);
  background-color: var(--tab-surface);
  color: var(--tab-text);
  font: inherit;
  transition: border-color 120ms ease-out, box-shadow 120ms ease-out;
}
textarea {
  padding-block: 8px;
}
input:not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="color"]):hover,
select:hover,
textarea:hover {
  border-color: color-mix(in srgb, var(--tab-text) 60%, transparent);
}
/* A focused field shows a 2 px edge in the accent made readable (its 1 px
   border and 1 px more inside), as Home Assistant's own fields do, and no
   ring outside it. */
input:not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="color"]):focus,
select:focus,
textarea:focus {
  border-color: var(--tab-accent-text);
  outline: none;
  box-shadow: inset 0 0 0 1px var(--tab-accent-text);
}
input:disabled,
select:disabled,
textarea:disabled {
  background-color: var(--tab-tonal);
  color: var(--tab-disabled);
}
/* The browser's own placeholder grey is too faint on dark cards. */
input::placeholder,
textarea::placeholder {
  color: var(--tab-text-2);
  opacity: 1;
}
/* A list field draws its chevron with two small gradients. */
select {
  appearance: none;
  padding-inline-end: 36px;
  background-image:
    linear-gradient(45deg, transparent calc(50% - 0.5px), currentColor calc(50% + 0.5px)),
    linear-gradient(135deg, currentColor calc(50% - 0.5px), transparent calc(50% + 0.5px));
  background-position: calc(100% - 18px) 50%, calc(100% - 13px) 50%;
  background-size: 5px 5px;
  background-repeat: no-repeat;
}
select:dir(rtl) {
  background-position: 13px 50%, 18px 50%;
}
/* iOS zooms into a field with text under 16 px when it takes focus. */
@media (pointer: coarse) {
  input:not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="color"]),
  select,
  textarea {
    font-size: 16px;
  }
}
/* A tick box is a switch: words first, the switch at the end. */
.check {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 48px;
  cursor: pointer;
}
.check > span {
  flex: 1 1 auto;
  min-width: 0;
}
input[type="checkbox"] {
  position: relative;
  flex: 0 0 auto;
  width: 36px;
  height: 20px;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: var(--tab-r-pill);
  appearance: none;
  background: var(--tab-field-line);
  cursor: pointer;
  transition: background-color 120ms ease-out;
}
input[type="checkbox"]::before {
  content: "";
  position: absolute;
  top: 2px;
  inset-inline-start: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  /* The surface on a light theme, the text colour on a dark one, so the
     knob is always lighter than its track (applyAccent). */
  background: var(--tab-knob);
  transition: inset-inline-start 120ms ease-out;
}
input[type="checkbox"]:checked {
  background: var(--tab-accent-fill);
}
input[type="checkbox"]:checked::before {
  inset-inline-start: 18px;
  background: var(--tab-accent-ink);
}
input[type="checkbox"]:disabled {
  background: var(--tab-tonal);
  cursor: default;
}
input[type="checkbox"]:disabled::before {
  background: var(--tab-disabled);
}
input[type="color"] {
  box-sizing: border-box;
  width: var(--tab-control);
  height: var(--tab-control);
  margin: 0;
  padding: 4px;
  border: 1px solid var(--tab-field-line);
  border-radius: var(--tab-r-s);
  background: var(--tab-surface);
  cursor: pointer;
}
/* Sliders: a 4 px track and a 16 px round knob in the accent. The track is
   filled up to the knob; the form sets --tab-range-fill (0 to 1). */
input[type="range"] {
  --tab-range-at: calc(8px + (100% - 16px) * var(--tab-range-fill, 0));
  width: 100%;
  min-height: var(--tab-control);
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
}
input[type="range"]::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: var(--tab-r-pill);
  background: linear-gradient(to right,
    var(--tab-accent-fill) var(--tab-range-at), var(--tab-field-line) var(--tab-range-at));
}
input[type="range"]:dir(rtl)::-webkit-slider-runnable-track {
  background: linear-gradient(to left,
    var(--tab-accent-fill) var(--tab-range-at), var(--tab-field-line) var(--tab-range-at));
}
input[type="range"]::-webkit-slider-thumb {
  width: 16px;
  height: 16px;
  margin-top: -6px;
  border: 0;
  border-radius: 50%;
  background: var(--tab-accent-fill);
  appearance: none;
  -webkit-appearance: none;
}
input[type="range"]::-moz-range-track {
  height: 4px;
  border-radius: var(--tab-r-pill);
  background: var(--tab-field-line);
}
input[type="range"]::-moz-range-progress {
  height: 4px;
  border-radius: var(--tab-r-pill);
  background: var(--tab-accent-fill);
}
input[type="range"]::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border: 0;
  border-radius: 50%;
  background: var(--tab-accent-fill);
}
input[type="range"]:disabled {
  cursor: default;
}
input[type="range"]:disabled::-webkit-slider-runnable-track {
  background: var(--tab-tonal);
}
input[type="range"]:disabled::-webkit-slider-thumb {
  background: var(--tab-disabled);
}
input[type="range"]:disabled::-moz-range-progress {
  background: var(--tab-tonal);
}
input[type="range"]:disabled::-moz-range-thumb {
  background: var(--tab-disabled);
}
/* One ring for keyboard focus: the text colour, with the surface between
   it and the control so it shows on any fill. Fields show their edge
   instead (above), and a slider rings its knob. */
button:focus-visible,
input:is([type="checkbox"], [type="radio"], [type="color"]):focus-visible,
a:focus-visible,
[tabindex]:focus-visible {
  outline: 2px solid var(--tab-text);
  outline-offset: 2px;
  box-shadow: 0 0 0 2px var(--tab-surface);
}
/* Links, as buttons or in a sentence, have one ring: a rounded rectangle
   round their words. A link button's words are in a span of their own,
   which takes the ring; its box stays a 40 px press area. */
a:not(.button-link):focus-visible {
  border-radius: var(--tab-r-xs);
  box-shadow: none;
}
button.link:has(> span):focus-visible {
  outline: none;
  box-shadow: none;
}
button.link:focus-visible > span {
  border-radius: var(--tab-r-xs);
  outline: 2px solid var(--tab-text);
  outline-offset: 2px;
}
input[type="range"]:focus-visible {
  outline: none;
}
input[type="range"]:focus-visible::-webkit-slider-thumb {
  box-shadow: 0 0 0 2px var(--tab-surface), 0 0 0 4px var(--tab-text);
}
input[type="range"]:focus-visible::-moz-range-thumb {
  box-shadow: 0 0 0 2px var(--tab-surface), 0 0 0 4px var(--tab-text);
}
/* A screen's heading takes focus when the screen changes; the ring shows
   only when that came from the keyboard. */
.screen-heading:focus:not(:focus-visible) {
  outline: none;
}
.tag {
  display: inline-block;
  padding: 2px 8px;
  border: 1px solid var(--tab-line);
  border-radius: var(--tab-r-pill);
  color: var(--tab-text);
  font-size: var(--tab-fs-small);
  font-weight: 500;
  line-height: var(--tab-lh-small);
  white-space: nowrap;
}
.small,
.helper,
.meta {
  margin: 0;
  color: var(--tab-text-2);
  font-size: var(--tab-fs-small);
  line-height: var(--tab-lh-small);
}
.helper {
  max-width: 38rem;
}
/* Everything that reports or asks: one look, a tint of its tone. The words
   keep the text colour; a mark that is not colour alone comes first. */
.banner,
.note-line,
.alert,
.notice {
  --tone: var(--tab-info);
  --tone-ink: var(--tab-info-ink);
  margin: 0;
  padding: 8px 12px;
  border: 0;
  border-radius: var(--tab-r-s);
  background: color-mix(in srgb, var(--tone) 12%, var(--tab-surface));
  color: var(--tab-text);
}
.banner.error,
.note-line.problem,
.alert,
.notice[data-tone="err"] {
  --tone: var(--tab-err);
  --tone-ink: var(--tab-err-ink);
}
.notice[data-tone="ok"] {
  --tone: var(--tab-ok);
  --tone-ink: var(--tab-ok-ink);
}
.notice[data-tone="warn"] {
  --tone: var(--tab-warn);
  --tone-ink: var(--tab-warn-ink);
}
.banner > ha-icon,
.note-line > ha-icon,
.notice > ha-icon {
  --mdc-icon-size: 20px;
  color: var(--tone-ink);
}
.notice {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
/* An error line is a bare paragraph, so its mark is drawn before it. */
.alert {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-weight: 500;
}
.alert::before {
  content: "!";
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  margin-block-start: 2px;
  border-radius: 50%;
  background: var(--tab-err-ink);
  color: var(--tab-surface);
  font-size: var(--tab-fs-small);
  font-weight: 700;
  line-height: 1;
}
.alert:empty {
  padding: 0;
  background: none;
}
.alert:empty::before {
  display: none;
}
/* A link or text button on a notice keeps 4.5:1 on its tint (applyAccent). */
.banner button.link,
.banner button.text,
.note-line button.link,
.note-line button.text,
.notice button.link,
.notice button.text {
  color: var(--tab-accent-text);
}
/* A status chip: words with a dot of their tone. */
.chip {
  --tone-ink: var(--tab-text-2);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border: 1px solid var(--tab-line);
  border-radius: var(--tab-r-pill);
  color: var(--tab-text);
  font-size: var(--tab-fs-small);
  font-weight: 500;
  line-height: var(--tab-lh-small);
  white-space: nowrap;
}
.chip::before {
  content: "";
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--tone-ink);
}
.chip[data-tone="ok"] {
  --tone-ink: var(--tab-ok-ink);
}
.chip[data-tone="warn"] {
  --tone-ink: var(--tab-warn-ink);
}
.chip[data-tone="err"] {
  --tone-ink: var(--tab-err-ink);
}
.chip[data-tone="info"] {
  --tone-ink: var(--tab-info-ink);
}
/* A radio group drawn as one pill: the chosen part takes the selected look. */
.segmented {
  display: inline-flex;
  min-height: var(--tab-control-s);
  padding: 2px;
  border: 1px solid var(--tab-line);
  border-radius: var(--tab-r-pill);
}
.segmented label {
  position: relative;
  display: inline-flex;
  align-items: center;
  padding-inline: 12px;
  border-radius: var(--tab-r-pill);
  font-weight: 500;
  cursor: pointer;
}
.segmented input {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: 0;
  overflow: hidden;
  clip-path: inset(50%);
  appearance: none;
}
.segmented label:hover {
  background-image: linear-gradient(var(--tab-hover), var(--tab-hover));
}
.segmented label:active {
  background-image: linear-gradient(var(--tab-press), var(--tab-press));
}
.segmented label:has(input:checked) {
  background-color: var(--tab-accent-soft);
  box-shadow: inset 0 0 0 2px var(--tab-accent-text);
}
.segmented label:has(input:focus-visible) {
  outline: 2px solid var(--tab-text);
  outline-offset: 2px;
}
/* Hover and pressed on rows and tiles: one more layer, and the accent as
   their edge. A mark in the accent is drawn in the accent made readable
   (--tab-accent-text, 4.5:1 on the surface and the soft tint), so a pale
   accent on a white theme still shows. */
.list-row:not(:disabled):hover,
.entity-option:not(:disabled):hover {
  background-image: linear-gradient(var(--tab-hover), var(--tab-hover));
}
.list-row:not(:disabled):not([aria-current="true"]):hover,
.entity-option:not(:disabled):not([aria-selected="true"]):hover {
  box-shadow: inset 0 0 0 1px var(--tab-accent-text);
}
.list-row:not(:disabled):active,
.entity-option:not(:disabled):active {
  background-image: linear-gradient(var(--tab-press), var(--tab-press));
}
.tab:not(:disabled):hover,
.icon-grid button:not(:disabled):hover {
  background-image: linear-gradient(var(--tab-hover), var(--tab-hover));
  border-color: var(--tab-accent-text);
}
.tab:not(:disabled):active,
.icon-grid button:not(:disabled):active {
  background-image: linear-gradient(var(--tab-press), var(--tab-press));
}
.tile:not(:disabled):hover {
  background-image: linear-gradient(var(--tab-hover), var(--tab-hover));
  border-color: var(--tab-accent-text);
  box-shadow: var(--tab-shadow);
}
.tile:not(:disabled):active {
  background-image: linear-gradient(var(--tab-press), var(--tab-press));
}
/* Selected, one look everywhere: a soft accent fill and a 2 px accent edge
   drawn inside, so nothing grows. The words keep their weight. */
.tab[aria-selected="true"],
.list-row[aria-current="true"],
.entity-option[aria-selected="true"],
.icon-grid button[aria-pressed="true"] {
  background-color: var(--tab-accent-soft);
  box-shadow: inset 0 0 0 2px var(--tab-accent-text);
}
/* A tab and an icon button have a 1 px edge of their own: chosen, that edge
   takes the mark's colour and 1 px more is drawn inside it, so the mark is
   one 2 px line at the control's own edge. */
.tab[aria-selected="true"],
.icon-grid button[aria-pressed="true"] {
  border-color: var(--tab-accent-text);
  box-shadow: inset 0 0 0 1px var(--tab-accent-text);
}
@media (forced-colors: active) {
  .tab[aria-selected="true"],
  .list-row[aria-current="true"],
  .entity-option[aria-selected="true"],
  .icon-grid button[aria-pressed="true"] {
    outline: 2px solid Highlight;
    outline-offset: -2px;
  }
}
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    transition: none !important;
    animation: none !important;
  }
}
`;

export const editorStyles = `
:host {
${tokens}
  display: block;
${hostType}
}
${coarseControls}
.hint {
  display: grid;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--tab-line);
  border-radius: var(--tab-r-m);
  background: var(--tab-surface);
}
.hint h2 {
  margin: 0;
  font-size: var(--tab-fs-head);
  line-height: var(--tab-lh-head);
  font-weight: 500;
}
.hint p {
  max-width: 68ch;
  margin: 0;
  color: var(--tab-text-2);
}
.hint a {
  justify-self: start;
  color: var(--tab-accent-text);
  font-weight: 500;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
}
.hint a:hover {
  text-decoration-thickness: 2px;
}
.hint a:focus-visible {
  outline: 2px solid var(--tab-text);
  outline-offset: 2px;
}
`;

export const panelStyles = `
:host {
${tokens}
  display: block;
  box-sizing: border-box;
  min-width: 0;
  min-height: 100%;
  background: var(--tab-bg);
${hostType}
  overflow-wrap: anywhere;
}
${coarseControls}
/* The panel is narrower than 900 px (set from script): every control is a
   touch target, also in the dialogs, which sit beside the editor. */
:host(.compact) {
  --tab-control: 44px;
  --tab-control-s: 44px;
}
*,
*::before,
*::after {
  box-sizing: border-box;
}
${controls}
${barTokens}
/* The bar spans the panel; its words line up with the boxes below, which
   are at most 1120 px wide and centred. */
.panel-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px 12px;
  padding-block: 20px;
  padding-inline: max(24px, calc((100% - 1120px) / 2 + 24px));
  border-bottom: 1px solid var(--tab-line);
  background: var(--tab-bar);
}
/* Home Assistant's menu button draws nothing while its sidebar is in reach.
   The negative margin takes back the gap after it then; when it does show,
   its 48 px round button leaves room enough around the icon. */
.panel-header > ha-menu-button {
  margin-inline-end: -12px;
}
.panel-header > div {
  flex: 1 1 240px;
  min-width: 0;
}
.panel-header h1 {
  margin: 0 0 4px;
  font-size: var(--tab-fs-title);
  line-height: var(--tab-lh-title);
  font-weight: 400;
}
.panel-header p {
  margin: 0;
  color: var(--tab-text-2);
}
.panel-content {
  display: grid;
  gap: 16px;
  min-width: 0;
  max-width: 1120px;
  margin-inline: auto;
  padding: 24px;
}
.box {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--tab-line);
  border-radius: var(--tab-r-m);
  background: var(--tab-surface);
}
.box > * {
  margin: 0;
}
.box > p {
  max-width: 68ch;
}
/* Small notes in a box run the full column, as the help lines in its rows
   do, so all small text there wraps at one measure. */
.box > p.small,
.box > p.helper,
.box > p.meta {
  max-width: none;
}
.box h2 {
  font-size: var(--tab-fs-head);
  line-height: var(--tab-lh-head);
  font-weight: 500;
}
.steps {
  display: grid;
  gap: 6px;
  padding-inline-start: 22px;
}
.box > button,
.box > a {
  justify-self: start;
}
/* Rows inside a box have no box of their own: a line divides them. */
.dashboard-row,
.component-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding-top: 12px;
  border-top: 1px solid var(--tab-line);
}
.row-text {
  display: grid;
  flex: 1 1 220px;
  gap: 4px;
  min-width: 0;
}
.row-text h3,
.row-text p {
  margin: 0;
}
.row-text h3 {
  font-size: var(--tab-fs-head);
  line-height: var(--tab-lh-head);
  font-weight: 500;
}
.row-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.code-line {
  padding: 8px 12px;
  border-radius: var(--tab-r-s);
  background: var(--tab-tonal);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: var(--tab-fs-small);
  line-height: var(--tab-lh-small);
}
.advanced-link {
  display: grid;
  justify-items: start;
  gap: 2px;
}
/* The link's words line up with the hint under it. */
.advanced-link > button.link {
  margin-inline-start: -4px;
}
.panel-header > .back {
  flex: 0 0 auto;
  padding-inline: 12px 16px;
}
.error-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding-inline-start: 20px;
}
/* The Tablets box: name, "Shows" and status side by side when there is
   room, one under the other when there is not. */
.tablets {
  container-type: inline-size;
}
.tablet-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr) minmax(0, 1fr);
  grid-template-areas:
    "name shows status"
    ". notes notes";
  align-items: center;
  gap: 4px 16px;
  padding-top: 12px;
  border-top: 1px solid var(--tab-line);
}
.tablet-title {
  grid-area: name;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  min-width: 0;
}
.tablet-name {
  margin: 0;
  font-size: var(--tab-fs-head);
  line-height: var(--tab-lh-head);
  font-weight: 500;
  overflow-wrap: anywhere;
}
/* After "Turn on with this dashboard" the tablet's name takes focus; the
   ring shows only when the press came from the keyboard. */
.tablet-name:focus:not(:focus-visible) {
  outline: none;
}
/* Under a new tablet's name: what to check on its screen and its device
   page, on lines of their own. */
.tablet-device {
  flex: 1 0 100%;
}
/* On a phone the device page link is a 44 px high touch target on a line
   of its own, so the words above keep their spacing. Its focus ring
   reaches 4 px outside it (2 px wide, 2 px away), so 6 px of space above
   and below keep the ring off the words. */
@media (max-width: 700px), (pointer: coarse) {
  .tablet-device-page {
    display: flex;
    align-items: center;
    width: fit-content;
    min-height: 44px;
    margin: 6px 0;
  }
}
.tablet-shows {
  grid-area: shows;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  margin: 0;
}
.tablet-shows .field-label {
  flex: 0 0 auto;
  font-weight: 500;
}
.tablet-shows select {
  flex: 1 1 auto;
  width: 100%;
  min-width: 0;
}
.tablet-status {
  grid-area: status;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-weight: 500;
}
/* A dot beside the words: green on the tablet, amber while sending, red
   for a problem, the accent for a new tablet, grey otherwise. The words
   carry the meaning. */
.tablet-status::before {
  content: "";
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--tab-text-2);
}
.tablet-status[data-tone="ok"]::before {
  background: var(--tab-ok-ink);
}
.tablet-status[data-tone="busy"]::before {
  background: var(--tab-warn-ink);
}
.tablet-status[data-tone="problem"]::before {
  background: var(--tab-err-ink);
}
.tablet-status[data-tone="new"]::before {
  background: var(--tab-accent);
}
/* Home Assistant waits for an admin's answer in Repairs: the words sit on
   an amber band with an amber edge, so the row stands out from every
   other status. The words keep the text colour, readable in both themes. */
.tablet-status[data-tone="attention"] {
  justify-self: start;
  width: fit-content;
  max-width: 100%;
  box-sizing: border-box;
  padding-block: 2px;
  padding-inline: 8px 10px;
  border: 1px solid var(--tab-warn-ink);
  border-radius: var(--tab-r-s);
  background: color-mix(in srgb, var(--tab-warn) 12%, var(--tab-surface));
}
.tablet-status[data-tone="attention"]::before {
  background: var(--tab-warn-ink);
}
/* "New" beside a tablet nobody turned on yet: the accent marks it, the
   words keep the text colour so they stay readable in both themes. */
.tag-new {
  border-color: var(--tab-accent);
  background: var(--tab-accent-soft);
}
.tablet-status:empty::before {
  display: none;
}
.tablet-notes {
  grid-area: notes;
  display: grid;
  gap: 6px;
}
.tablet-notes:empty {
  display: none;
}
/* "Set up again" sits under its line, and "Turn on with this dashboard"
   under the list, each as wide as its words. */
.tablet-notes .tablet-pair,
.tablet-notes .tablet-turn-on {
  justify-self: start;
}
/* What Home Assistant waits for before it connects to the tablet again,
   with the way to Repairs right after the words. */
.tablet-reauth {
  margin: 0;
}
.tablet-repairs {
  white-space: nowrap;
}
/* On a phone the Repairs link is a 44 px high touch target on a line of
   its own, with 6 px above and below for its focus ring, as the device
   page link. */
@media (max-width: 700px), (pointer: coarse) {
  .tablet-repairs {
    display: flex;
    align-items: center;
    width: fit-content;
    min-height: 44px;
    margin: 6px 0;
  }
}
@container (max-width: 620px) {
  .tablet-row {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas:
      "name"
      "shows"
      "status"
      "notes";
  }
}
:host(.compact) .panel-header {
  padding-block: 16px;
  padding-inline: 16px;
}
:host(.compact) .panel-content {
  padding: 16px;
}
`;

export const formStyles = `
.form-block {
  display: grid;
  gap: 12px;
  min-width: 0;
}
.form-block > h3 {
  margin: 8px 0 0;
  font-size: var(--tab-fs-body);
  line-height: var(--tab-lh-body);
  font-weight: 600;
  /* Room for the ring when the heading is scrolled to the top. */
  scroll-margin-top: 8px;
}
/* Focus moved here from the keyboard keeps its ring. */
.form-block > h3:focus:not(:focus-visible) {
  outline: none;
}
.form-block > p {
  margin: 0;
}
/* A switch's help line sits 4 px under the switch's words: the row puts
   its words at its foot and takes back the gap above it, so the space
   before the row stays as it was and the row is still 48 px to press. */
.form-block > .check:has(+ .helper) {
  align-items: flex-end;
  margin-block-start: -12px;
}
.form-block > .check + .helper {
  margin-block-start: calc(var(--tab-s1) - 12px);
}
.field {
  display: grid;
  gap: 6px;
  min-width: 0;
}
/* A form never grows wider than the panel or sheet it is in. Without this a
   select is as wide as its longest option, so a long page or theme name
   pushed the controls out of the side panel and widened the phone page. */
.form-block,
.field {
  grid-template-columns: minmax(0, 1fr);
}
.form-block > *,
.field > * {
  min-width: 0;
}
.field > select,
.field > input:not([type="checkbox"]):not([type="radio"]):not([type="color"]):not([type="range"]) {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}
.field-label {
  font-weight: 500;
}
.row-buttons,
.stepper {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.stepper-label {
  min-width: 64px;
  font-weight: 500;
}
.size-value {
  margin: 0;
  font-weight: 500;
}
.size-note {
  display: grid;
  justify-items: start;
  gap: 8px;
}
/* A text button that starts a row lines its words up with the column: it
   takes its side padding back (12 px here, which every panel's padding
   holds). Its ring is drawn inside it then, so the edge of a scrolling
   panel does not cut it. */
.form-block > button.text {
  justify-self: start;
  margin-inline-start: -12px;
  padding-inline: 12px;
}
.form-block > button.text:focus-visible {
  outline-offset: -3px;
  box-shadow: none;
}
/* The page to move a card to, with the button that moves it beside it, or
   under it when there is no room. */
.move-page {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 8px;
}
.move-page > .field {
  flex: 1 1 160px;
}
.range-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.range-row output {
  min-width: 3ch;
  text-align: end;
}
.icon-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(44px, 1fr));
  gap: 6px;
}
.icon-grid button {
  position: relative;
  min-width: 44px;
  padding: 0;
  border: 1px solid var(--tab-line);
  border-radius: var(--tab-r-s);
  background-color: transparent;
  --mdc-icon-size: 24px;
}
/* The chosen icon also has a small tick, so it is not told by colour
   alone. */
.icon-grid button[aria-pressed="true"]::after {
  content: "✓";
  position: absolute;
  top: -6px;
  inset-inline-end: -6px;
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--tab-accent-fill);
  color: var(--tab-accent-ink);
  font-size: var(--tab-fs-small);
  font-weight: 700;
  line-height: 1;
}
/* The chosen device, with "Change" beside it. */
.chosen {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-block: 4px;
  padding-inline: 12px 4px;
  border-radius: var(--tab-r-s);
  background: var(--tab-tonal);
}
.chosen span {
  min-width: 0;
}
.entity-list {
  display: grid;
  gap: 2px;
  max-height: 320px;
  padding: 2px;
  overflow: auto;
}
/* Rows of a list: no box of their own, a line between them. */
.entity-option {
  display: grid;
  justify-content: stretch;
  justify-items: start;
  gap: 2px;
  min-height: 44px;
  padding-block: 8px;
  padding-inline: 12px;
  border-radius: var(--tab-r-s);
  background-color: transparent;
  font-weight: 400;
  text-align: start;
}
.entity-option {
  position: relative;
}
.entity-option + .entity-option::before {
  content: "";
  position: absolute;
  top: -1.5px;
  inset-inline: 12px;
  height: 1px;
  background: var(--tab-line);
  pointer-events: none;
}
.entity-option:is(:hover, [aria-selected="true"])::before,
.entity-option:is(:hover, [aria-selected="true"]) + .entity-option::before {
  display: none;
}
@media (pointer: coarse) {
  .entity-option {
    min-height: 56px;
  }
}
.entity-check {
  font-weight: 700;
}
.entity-name {
  font-weight: 500;
}
.entity-option small {
  color: var(--tab-text-2);
  overflow-wrap: anywhere;
}
/* Inside a scroll box the ring is drawn inside the control, so it is not
   cut off. */
.entity-list :focus-visible {
  outline-offset: -3px;
  box-shadow: none;
}
.side-title {
  margin: 0;
  font-size: var(--tab-fs-head);
  line-height: var(--tab-lh-head);
  font-weight: 500;
}
/* The ring of the title is a rounded box 4 px clear of its words, in the
   column's side padding; the words stay in line with the column. */
.side-title {
  margin-inline: -6px;
  padding-inline: 6px;
  border-radius: var(--tab-r-xs);
}
.side-title:focus {
  outline: none;
}
.side-title:focus-visible {
  outline: 2px solid var(--tab-text);
  outline-offset: -2px;
  box-shadow: none;
}
.item-notes {
  display: grid;
  gap: 8px;
}
.item-notes:empty {
  display: none;
}
/* The tablets that show the dashboard, under its theme. */
.shown-on {
  display: grid;
  gap: 8px;
  min-width: 0;
}
.shown-on-heading {
  margin: 4px 0 0;
  font-size: var(--tab-fs-body);
  line-height: var(--tab-lh-body);
  font-weight: 600;
}
.shown-on-heading:focus:not(:focus-visible) {
  outline: none;
}
.shown-on-list {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
}
.shown-on-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px 12px;
  padding-block: 8px;
  padding-inline: 0;
}
.shown-on-row + .shown-on-row {
  border-top: 1px solid var(--tab-line);
}
.shown-on-text {
  display: grid;
  flex: 1 1 140px;
  gap: 2px;
  min-width: 0;
}
.shown-on-name {
  font-weight: 500;
}
.automation-name {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
  margin: 0;
}
.automation-name code {
  min-width: 0;
  padding: 2px 6px;
  border-radius: var(--tab-r-s);
  background: var(--tab-tonal);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: var(--tab-fs-small);
  line-height: var(--tab-lh-small);
  overflow-wrap: anywhere;
  user-select: all;
}
/* The form of a schema 2 card (cards spec C.7). Plain rows; the inspector
   of the redesign's package 4 draws them later. */
.card-form-2 > .form-block + .form-block {
  padding-block-start: 4px;
  border-block-start: 1px solid var(--tab-line);
}
/* An option row with its help line under it, 4 px apart. */
.option-switch {
  display: grid;
  gap: 0;
}
.option-switch > .helper {
  margin-block-start: -8px;
}
/* A row the device cannot use: greyed, with its reason on its own line
   in the text colour, after a mark. */
.option-row.unusable .field-label,
.option-row.unusable .check > span {
  color: var(--tab-text-2);
}
.option-row .helper {
  color: var(--tab-text-2);
}
.reason-line {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 4px 0 0;
  color: var(--tab-text);
  font-size: var(--tab-fs-small);
  line-height: var(--tab-lh-small);
}
.reason-line > ha-icon {
  --mdc-icon-size: 16px;
  flex: 0 0 auto;
  margin-block-start: 1px;
  color: var(--tab-text-2);
}
/* A row that shows only while another option is on sits under it. */
.option-row.option-dependent {
  margin-inline-start: 16px;
  padding-inline-start: 12px;
  border-inline-start: 2px solid var(--tab-line);
}
.ticks {
  display: grid;
  padding-inline-start: 12px;
  border-inline-start: 2px solid var(--tab-line);
}
.ticks .check {
  min-height: 44px;
}
/* Round, four to a row, as the card draws its favourite colours. */
.swatches {
  display: grid;
  grid-template-columns: repeat(4, 64px);
  align-items: start;
  gap: 8px 4px;
}
.swatch {
  display: grid;
  justify-items: center;
  gap: 2px;
  text-align: center;
}
.swatch input[type="color"] {
  padding: 3px;
  border-radius: 50%;
}
.swatch input[type="color"]::-webkit-color-swatch-wrapper {
  padding: 0;
}
.swatch input[type="color"]::-webkit-color-swatch {
  border: 0;
  border-radius: 50%;
}
.swatch input[type="color"]::-moz-color-swatch {
  border: 0;
  border-radius: 50%;
}
.row-buttons > [hidden] {
  display: none;
}
/* Add and Remove are text buttons; their words line up with the label. */
.swatch-field > .row-buttons {
  margin-inline-start: -12px;
}
.swatch-mark {
  color: var(--tab-text-2);
  font-size: var(--tab-fs-small);
  line-height: 1;
}
/* The line under a part's heading sits close to it. */
.card-form-2 .form-block > h3 + .helper {
  margin-block-start: -8px;
}
/* The icon as one line: the icon, its name and Change at the end. */
.icon-current {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: var(--tab-control-s);
  --mdc-icon-size: 24px;
}
.icon-current-name {
  flex: 1 1 auto;
  min-width: 0;
}
.icon-current > button.text {
  margin-inline-end: -12px;
}
/* Switch rows one after another share one 48 px pitch. A switch row
   holds its words in the middle of 48 px, so after any other row it takes
   back the same 12 px: every option row then starts the same distance
   under the one before it. */
.card-form-2 .form-block > :is(.check, .option-row) + :is(.check, .option-switch) {
  margin-block-start: -12px;
}
.card-form-2 .form-block > .helper + .option-switch {
  margin-block-start: -8px;
}
.size-chips {
  flex-wrap: wrap;
  justify-self: start;
  max-width: 100%;
}
.size-chips label {
  min-height: var(--tab-control-s);
}
@media (pointer: coarse) {
  .size-chips label {
    min-height: 40px;
  }
}
.icon-grid .icon-default {
  grid-column: span 3;
  padding-inline: 8px;
  font-size: var(--tab-fs-small);
}
.newer-card {
  display: grid;
  justify-items: start;
  gap: 8px;
  padding: 12px;
  border-radius: var(--tab-r-s);
  background: color-mix(in srgb, var(--tab-info) 12%, var(--tab-surface));
}
.newer-card > p {
  margin: 0;
}
`;

// The editor is only ever made by the panel and sits in the panel's shadow
// root, so it inherits the tokens from the panel's host; declaring them
// here again would undo what applyAccent set there.
export const designerStyles = `
:host {
  display: block;
  box-sizing: border-box;
  min-width: 0;
${hostType}
  overflow-wrap: anywhere;
}
*,
*::before,
*::after {
  box-sizing: border-box;
}
${controls}
${barTokens}
/* The editor is a grid as tall as the window (the script sets its
   height): the top bar, the notices that block, the page strip, then the
   stage column and the inspector, each placed by the name of its row. Its
   own layers (the edit mode, toasts, the picture's card buttons) stack
   inside it, so none of them can cover Home Assistant's sidebar or menus.
   The document never scrolls; the inspector, the compact page column and
   the edit mode's form do. */
.root {
  --safe-bottom: var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px));
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(320px, 26%, 400px);
  grid-template-rows: auto auto auto minmax(0, 1fr);
  grid-template-areas: "bar bar" "block block" "strip strip" "main side";
  min-width: 0;
  overflow: clip;
  isolation: isolate;
  background: var(--tab-bg);
}
.root.short {
  grid-template-columns: minmax(0, 1fr) clamp(280px, 40%, 360px);
}
.root.medium,
.root.compact {
  grid-template-columns: minmax(0, 1fr);
  grid-template-areas: "bar" "block" "strip" "main";
}
.ed-header {
  grid-area: bar;
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 8px;
  block-size: 56px;
  min-width: 0;
  padding-inline: 12px 16px;
  border-bottom: 1px solid var(--tab-line);
  background: var(--tab-bar);
}
.root.short .ed-header {
  block-size: 48px;
}
.root.compact .ed-header {
  padding-inline: 4px 8px;
  gap: 4px;
}
/* As in the panel header: no gap after a menu button that draws nothing. */
.ed-header > ha-menu-button {
  margin-inline-end: -8px;
}
.root.compact .ed-header > ha-menu-button {
  margin-inline-end: -4px;
}
/* The title, then the tablets that show the dashboard on one line, cut
   when it does not fit. */
.title-block {
  display: flex;
  flex: 1 1 auto;
  align-items: baseline;
  gap: 16px;
  min-width: 0;
}
.ed-header h1 {
  flex: 0 1 auto;
  min-width: 0;
  margin: 0;
  overflow: hidden;
  font-size: var(--tab-fs-title);
  line-height: var(--tab-lh-title);
  font-weight: 400;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.root.compact .ed-header h1 {
  font-size: var(--tab-fs-head);
  line-height: var(--tab-lh-head);
}
.tablet-lines {
  display: grid;
  gap: 2px;
}
.tablet-line {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  margin: 0;
}
/* In the bar the lines run on as words in one line, and the cut ends in
   "…" with 16 px before the save state. */
.ed-header .tablet-lines {
  display: block;
  flex: 1 1 0;
  /* A long title is cut first: the lines keep at least their first words. */
  min-width: min(12em, 40%);
  padding-inline-end: 8px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.ed-header .tablet-lines:empty {
  min-width: 0;
}
.ed-header .tablet-line {
  display: inline;
}
.ed-header .tablet-line + .tablet-line {
  margin-inline-start: 16px;
}
.ed-header .tablet-line[data-tone]::before {
  display: inline-block;
  margin-inline-end: 6px;
  vertical-align: 0.1em;
}
/* A dot in the tablet's tone, worked out from the tokens where it is shown
   (the bar's own inside the bar). */
.tablet-line[data-tone]::before {
  content: "";
  flex: 0 0 auto;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--tab-text-2);
}
.tablet-line[data-tone="ok"]::before {
  background: var(--tab-ok-ink);
}
.tablet-line[data-tone="busy"]::before {
  background: var(--tab-info-ink);
}
.tablet-line[data-tone="attention"]::before {
  background: var(--tab-warn-ink);
}
.tablet-line[data-tone="problem"]::before {
  background: var(--tab-err-ink);
}
.save-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: var(--tab-control);
  color: var(--tab-text-2);
  white-space: nowrap;
}
.save-state[data-state="error"] {
  color: var(--tab-text);
  font-weight: 600;
}
.save-state[data-state="error"] ha-icon {
  color: var(--tab-err-ink);
}
/* In the compact bar the save state is its icon; the word is still read. */
.root.compact .save-word {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.header-actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 4px;
  margin-inline-start: auto;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.banners {
  display: grid;
  gap: 12px;
}
.banners:empty {
  display: none;
}
.root > .banners {
  grid-area: block;
  padding-block: 12px;
  padding-inline: 24px;
  border-bottom: 1px solid var(--tab-line);
}
.root.compact > .banners,
.root.short > .banners {
  padding-inline: 12px;
}
.banner {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.banner h2 {
  margin: 0;
  font-size: var(--tab-fs-head);
  line-height: var(--tab-lh-head);
  font-weight: 500;
}
.banner p {
  margin: 0;
}
.banner > button {
  justify-self: start;
}
.banner-text {
  display: grid;
  gap: 4px;
  min-width: 0;
}
/* A banner at the top starts with a mark in its tone, so the tint is not
   the only difference: "!" in a disc for an error, "i" for a notice. */
.root > .banners > .banner {
  grid-template-columns: 20px minmax(0, 1fr);
  column-gap: 12px;
}
.root > .banners > .banner > * {
  grid-column: 2;
}
.root > .banners > .banner::before {
  content: "i";
  grid-column: 1;
  grid-row: 1;
  align-self: start;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--tone-ink);
  color: var(--tab-surface);
  font-size: var(--tab-fs-small);
  font-weight: 700;
  line-height: 1;
}
.root > .banners > .banner.error::before {
  content: "!";
}
/* Only the page tabs scroll sideways; Add page stays at the end of the
   tabs, in view however many pages there are, and Add card at the end of
   the strip. The padding keeps the focus ring inside the scrolling box. */
.tab-strip {
  grid-area: strip;
  display: flex;
  align-items: center;
  gap: 16px;
  block-size: 52px;
  min-width: 0;
  /* It starts where the stage's padding does and ends where the top bar
     and the inspector end. */
  padding-inline: 24px 16px;
  border-bottom: 1px solid var(--tab-line);
}
.root.compact .tab-strip,
.root.short .tab-strip {
  block-size: 48px;
  padding-inline: 12px;
}
.root.short .tab-strip {
  padding-inline-end: 16px;
}
.root.medium .tab-strip {
  padding-inline: 16px;
}
.strip-tabs {
  display: flex;
  flex: 1 1 auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.strip-end {
  display: flex;
  flex: none;
  align-items: center;
  gap: 8px;
}
.strip-end:empty {
  display: none;
}
.tabs {
  display: flex;
  flex: 0 1 auto;
  gap: 8px;
  min-width: 0;
  padding: 2px;
  overflow-x: auto;
}
.tabs :focus-visible {
  outline-offset: -3px;
  box-shadow: none;
}
/* A tab is never squeezed to the width of the scrolling box: its name is
   cut only at the limit below, and the box scrolls instead. Its edge and
   weight stay the same when it is chosen, so nothing shifts. Tabs are as
   high as "Add page" beside them, a plain button's height. */
.tab {
  flex: 0 0 auto;
  max-width: none;
  min-height: var(--tab-control);
  border: 1px solid var(--tab-line);
  background-color: transparent;
  white-space: nowrap;
}
/* A long page name is cut short with "…". The whole name stays in the tab's
   text, which screen readers read, and in its tooltip. The limit is on the
   name, so a short name next to a "Not shown on the tablet" tag is not cut. */
.tab-name {
  min-width: 0;
  max-width: 12em;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tab .tag {
  flex: 0 0 auto;
}
.add-page {
  flex: 0 0 auto;
  white-space: nowrap;
}
/* In the 48 px strip of compact and short a ring outside the 44 px button
   would be cut: it is drawn inside. */
.root.compact .tab-strip :focus-visible,
.root.short .tab-strip :focus-visible {
  outline-offset: -3px;
  box-shadow: none;
}
/* The stage column: the page notices, the picture in its frame, which
   takes the free height but never less than 160 px, and the status strip. */
.main {
  grid-area: main;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: var(--tab-stage);
}
/* Short: when notices, a failure and the pager need more than the window
   has, the column scrolls instead of cutting the picture off. */
.root.short .main {
  overflow-y: auto;
  overscroll-behavior: contain;
}
/* The page notices: one line of 40 px each, at most one shown until "+N
   more" is pressed; an open list scrolls on its own in a low window. */
.main > .advice-banners {
  flex: 0 1 auto;
  align-content: start;
  gap: 4px;
  min-height: 44px;
  padding-block: 4px 0;
  padding-inline: 24px;
  overflow-y: auto;
}
.root.medium .main > .advice-banners {
  padding-inline: 16px;
}
/* Short: the notices do not scroll on their own; with every one shown the
   stage column scrolls as a whole, so none is cut to an empty band. */
.root.short .main > .advice-banners {
  flex: none;
  padding-inline: 12px;
  overflow-y: visible;
}
/* In medium the open drawer lies over the row's end, so the row ends at
   the drawer's edge and its buttons stay in reach. */
.root.medium.drawer-open .main > .advice-banners {
  padding-inline-end: 336px;
}
.main > .advice-banners:empty {
  display: none;
}
/* The row scrolls, so a ring outside its buttons would be cut: it is drawn
   inside them. */
.main > .advice-banners :focus-visible {
  outline-offset: -3px;
  box-shadow: none;
}
.page-notice {
  display: grid;
  min-width: 0;
  padding-block: 0;
  padding-inline: 12px 4px;
}
.notice-line {
  display: flex;
  align-items: center;
  gap: 4px 8px;
  min-width: 0;
  min-height: 40px;
}
.notice-line > ha-icon {
  flex: none;
  --mdc-icon-size: 20px;
  color: var(--tone-ink);
}
.notice-words {
  flex: 1 1 12em;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.notice-line > button {
  flex: none;
}
.notice-why-text {
  max-width: 60em;
  margin: 0;
  padding-block: 0 8px;
}
.page-notice > .alert {
  margin-block-end: 8px;
}
.stage-area {
  position: relative;
  display: flex;
  flex: 1 0 160px;
  min-width: 0;
  padding: 24px;
  overflow: hidden;
}
/* At 100 % the picture is the tablet's real size and the area scrolls. */
.stage-area[data-zoom="100"] {
  overflow: auto;
}
.root.medium .stage-area {
  padding: 16px;
}
.root.compact .stage-area,
.root.short .stage-area {
  padding: 12px;
}
/* The frame of the tablet, centred both ways. The medium layout slides it
   left to clear the drawer. */
.device {
  position: relative;
  flex: none;
  margin: auto;
  padding: 10px;
  border-radius: var(--tab-r-bezel);
  background: var(--tab-bezel);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.14), var(--tab-shadow);
  transition: transform 160ms ease-out;
}
.root.compact .device,
.root.short .device {
  padding: 6px;
}
.stage {
  position: relative;
  overflow: hidden;
  border-radius: var(--tab-r-screen);
  background: #101418;
  isolation: isolate;
  scroll-margin: 8px;
}
.stage.opening {
  width: min(879px, 60vw);
  aspect-ratio: 1280 / 800;
}
.page-host {
  position: absolute;
  top: 0;
  left: 0;
}
.hit-layer {
  position: absolute;
  inset: 0;
  z-index: 30;
}
.hit {
  position: absolute;
  min-width: 0;
  min-height: 0;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: var(--tab-r-s);
  background: transparent;
  scroll-margin: 8px;
}
/* The card under the pointer gets an edge and no fill: the picture shows
   the card as the tablet draws it. */
.hit:hover,
.hit:active {
  outline: 2px solid color-mix(in srgb, var(--tab-accent) 60%, transparent);
  outline-offset: 0;
  background: transparent;
}
/* The selected card: 2 px of white inside 3 px of the ring colour, which
   shows on light and dark cards alike. */
.hit[aria-pressed="true"] {
  outline: 2px solid #ffffff;
  outline-offset: 0;
  box-shadow: 0 0 0 5px var(--tab-ring);
}
.hit:focus-visible {
  outline: 2px dashed #ffffff;
  outline-offset: 0;
  box-shadow: 0 0 0 5px var(--tab-ring);
}
.stage-message,
.empty-page {
  position: absolute;
  inset: 0;
  z-index: 31;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 10px;
  padding: 12px 16px;
  text-align: center;
}
.stage-message {
  color: #e8eaed;
}
.empty-page {
  left: 7.5%;
}
.empty-page p {
  max-width: 34em;
  margin: 0;
}
.empty-page .small {
  color: inherit;
}
/* Under the picture, 40 px: the size and zoom, the screen pager, and a
   failure to update the picture or "Cards". */
.status-strip {
  display: flex;
  flex: none;
  align-items: center;
  gap: 12px;
  min-height: 40px;
  padding-inline: 24px;
  background: var(--tab-surface);
  box-shadow: inset 0 1px 0 var(--tab-line);
}
.root.medium .status-strip {
  padding-inline: 16px;
}
/* The strip stays one line: its parts are laid out in the strip itself.
   Buttons and the zoom control never shrink or wrap. When space is short
   the failure's sentence gives way; the size caption is hidden while a
   failure shows, so the sentence has its room. */
.status-start,
.status-end,
.status-strip .preview-error {
  display: contents;
}
.status-strip button,
.status-strip .segmented,
.status-strip .segmented label {
  flex: none;
  white-space: nowrap;
}
.zoom-caption {
  flex: 0 0.0001 auto;
  min-width: 0;
  overflow: hidden;
  color: var(--tab-text-2);
  font-size: var(--tab-fs-small);
  line-height: var(--tab-lh-small);
  white-space: nowrap;
  text-overflow: ellipsis;
}
.screens {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}
.screens:empty {
  display: none;
}
.screens .small {
  flex-basis: 100%;
}
/* The pager sits in the middle of the free space. Its box stays when it is
   empty, so its margins still push the failure and "Cards" to the end. */
.status-strip .screens,
.status-strip .screens:empty {
  display: flex;
  flex: none;
  flex-wrap: nowrap;
  column-gap: 4px;
  margin-inline: auto;
  white-space: nowrap;
}
/* The pager's arrows are round, as wide as they are high. */
.status-strip .screens button {
  width: var(--tab-control);
  padding: 0;
}
.status-strip .screens > span {
  margin-inline-end: 4px;
}
.preview-error {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.preview-error:empty {
  display: none;
}
.status-strip .preview-error .alert {
  flex: 0 1 auto;
  min-width: 7em;
  padding-block: 4px;
  white-space: nowrap;
}
.status-strip .preview-error .alert > span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.status-strip .preview-error > button {
  flex: none;
}
/* A failure needs the room more than the size caption does, and more than
   the pager's words: the pager reads "1 / 2" then, and its words are only
   read out. */
.status-strip:has(.preview-error .alert) .zoom-caption {
  display: none;
}
.screens-brief {
  display: none;
}
.status-strip:has(.preview-error .alert) .screens-brief {
  display: inline;
}
.status-strip:has(.preview-error .alert) .screens-words {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
/* The strip's buttons are as high as the strip, and the edit mode's top
   row ends at its line, so a ring outside them would be cut: it is drawn
   inside them. The same for "Fit" and "100 %", whose ring would lie over
   the other one. */
.status-strip :focus-visible,
.side.sheet > .side-top :focus-visible {
  outline-offset: -3px;
  box-shadow: none;
}
.status-strip .segmented label:has(input:focus-visible) {
  outline-offset: -2px;
}
/* Buttons in the status strip and in a notice line keep their press area,
   as high as the line, but paint 8 px less: a clear 4 px edge all round,
   so they do not fill their line from edge to edge. The ring lies on that
   clear edge, just outside the painted part. */
.status-strip button,
.notice-line > button {
  border: 4px solid transparent;
  background-clip: padding-box;
}
.status-strip button:not(.icon),
.notice-line > button:not(.icon) {
  padding-inline: 12px;
}
.status-strip button:focus-visible,
.main > .advice-banners .notice-line > button:focus-visible {
  outline-offset: -4px;
}
/* Compact and short: the pager, a failure and (compact) the notes in a row
   under the picture. */
.under {
  display: grid;
  flex: none;
  gap: 8px;
  padding-inline: 12px;
}
/* Short: the row is the last thing above the window's edge; its buttons
   keep clear of it. */
.root.short .under {
  padding-block-end: calc(8px + var(--safe-bottom));
}
.under:not(:has(> :not(:empty))) {
  display: none;
}
.notes {
  display: grid;
  gap: 6px;
}
.notes:empty {
  display: none;
}
.notes p {
  margin: 0;
}
.page-box {
  margin: 24px;
}
.list-block {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
}
.list-block > :not(h2, .drawer-close) {
  grid-column: 1 / -1;
}
.list-block h2 {
  margin: 0;
  font-size: var(--tab-fs-head);
  line-height: var(--tab-lh-head);
  font-weight: 500;
}
/* The card list: rows with a line between them, no box of their own. */
.card-list {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
}
.card-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding-block: 4px;
}
.card-list li + li {
  border-top: 1px solid var(--tab-line);
}
.card-list li:has(> .list-row[aria-current="true"]),
.card-list li:has(> .list-row[aria-current="true"]) + li {
  border-top-color: transparent;
}
.card-list :focus-visible {
  outline-offset: -3px;
  box-shadow: none;
}
.list-row {
  display: grid;
  flex: 1 1 220px;
  grid-template-columns: auto minmax(0, 1fr);
  justify-content: stretch;
  justify-items: start;
  align-items: center;
  gap: 2px 12px;
  min-width: 0;
  min-height: 44px;
  padding-block: 8px;
  padding-inline: 12px;
  border-radius: var(--tab-r-s);
  background-color: transparent;
  font-weight: 400;
  text-align: start;
}
@media (pointer: coarse) {
  .list-row {
    min-height: 56px;
  }
}
/* A row brought into view keeps clear of the edge, and in the compact
   layout of the floating Add card. */
.list-row {
  scroll-margin-block: 8px;
}
.root.compact .list-row,
.root.compact .card-list button {
  scroll-margin-block-end: calc(88px + var(--safe-bottom));
}
.list-row ha-icon {
  grid-row: 1 / span 4;
  color: var(--tab-text-2);
}
.list-row span {
  min-width: 0;
}
.row-name {
  font-weight: 500;
}
.row-device,
.row-reason {
  color: var(--tab-text-2);
  font-size: var(--tab-fs-small);
  line-height: var(--tab-lh-small);
}
.row-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
  margin-inline-start: auto;
}
.row-remove,
.row-move {
  flex: 0 0 auto;
}
/* The inspector: a surface with its own scroll, as tall as its row. */
.side {
  grid-area: side;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-content: start;
  gap: 16px;
  min-width: 0;
  min-height: 0;
  padding: 16px;
  overflow-y: auto;
  overscroll-behavior: contain;
  border-inline-start: 1px solid var(--tab-line);
  background: var(--tab-surface);
}
.side > *,
.idle > * {
  min-width: 0;
}
.side p,
.idle-intro p {
  margin: 0;
}
/* Delete buttons and text buttons are as wide as their words, at the start. */
.side button.danger,
.side button.text,
.idle button.danger,
.idle button.text {
  justify-self: start;
}
/* What the inspector shows with nothing selected. */
.idle,
.idle-page,
.idle-settings {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}
.idle-intro:empty,
.idle-page:empty,
.idle-settings:empty {
  display: none;
}
/* Both buttons stay on one line; the settings link wraps its own words
   when the panel is narrow, so the form starts as high as it can. */
.side-top {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
}
/* The arrow lines up with the form's words under it. */
.side-back {
  justify-self: start;
  margin-inline-start: -4px;
  padding-inline: 4px;
  text-align: start;
}
.side-back > span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
/* While the dashboard opens: grey rows where the list will be. */
.placeholder-row {
  height: 48px;
  border-radius: var(--tab-r-s);
  background: var(--tab-tonal);
}
.placeholder-rows {
  display: grid;
  gap: 16px;
}
/* Medium: the inspector is a 320 px drawer over the right edge of the
   stage column, moved out while closed. */
.root.medium .side {
  grid-area: main;
  justify-self: end;
  z-index: 1;
  width: 320px;
  max-width: 100%;
  border-inline-start: 0;
  transform: translateX(100%);
  transition: transform 160ms ease-out;
}
.root.medium .side:dir(rtl) {
  transform: translateX(-100%);
}
.root.medium.drawer-open .side {
  box-shadow: var(--tab-shadow);
  transform: none;
}
/* Compact: one column that scrolls, the picture first. The inspector is
   only drawn as the edit mode. */
.root.compact .main {
  gap: 12px;
  padding-block-end: calc(88px + var(--safe-bottom));
  overflow-y: auto;
  overscroll-behavior: contain;
  background: var(--tab-surface);
}
.root.compact .main > :not(.stage-area) {
  margin-inline: 12px;
}
.root.compact .main > .under {
  padding-inline: 0;
}
.root.compact .stage-area {
  flex: none;
  background: var(--tab-stage);
}
.root.compact .main > .advice-banners {
  flex: none;
  min-height: 0;
  padding: 0;
  overflow: visible;
}
.root.compact .notice-line {
  flex-wrap: wrap;
  padding-block: 4px;
}
.root.compact .notice-words,
.root.short .advice-banners.open .notice-words {
  white-space: normal;
}
/* Short: with every notice shown, a line may wrap as in compact, so no
   sentence is cut to nothing. */
.root.short .advice-banners.open .notice-line {
  flex-wrap: wrap;
  padding-block: 4px;
}
.root.compact .side {
  display: none;
}
/* The edit mode: a layer over the page strip and the page column, placed
   by the grid's lines, under the top bar and a notice that blocks. */
.root.compact .side.sheet {
  grid-row: strip-start / main-end;
  grid-column: 1 / -1;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0;
  overflow: hidden;
  border: 0;
}
.side.sheet:focus {
  outline: none;
}
.side.sheet > .side-top {
  flex: none;
  min-height: 48px;
  /* The same side edges as the form under it. */
  padding-inline: 12px;
  border-bottom: 1px solid var(--tab-line);
}
/* The strip of the picture above the form, the selected card in its
   middle and the rest dimmed. It has the bezel's colour, so where the page
   ends there is no seam and dimming makes the other cards darker in both
   themes. */
.edit-preview {
  position: relative;
  flex: none;
  height: clamp(128px, 30dvh, 240px);
  overflow: hidden;
  background: var(--tab-bezel);
}
/* A card the tablet cannot draw: the whole page, small, and no ring. */
.edit-preview.whole {
  height: 128px;
}
.edit-frame {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
}
.edit-selected {
  position: absolute;
  border-radius: var(--tab-r-s);
  box-shadow:
    0 0 0 2px #ffffff,
    0 0 0 5px var(--tab-ring),
    0 0 0 100vmax color-mix(in srgb, var(--tab-bezel) 50%, transparent);
  pointer-events: none;
}
.edit-form {
  display: grid;
  flex: 1 1 auto;
  grid-template-columns: minmax(0, 1fr);
  align-content: start;
  gap: 16px;
  min-height: 0;
  /* Room at the end for the toast, so the last button scrolls clear of it. */
  padding-block: 16px calc(80px + var(--safe-bottom));
  padding-inline: 12px;
  overflow-y: auto;
  overscroll-behavior: contain;
}
/* Add card floats at the bottom of the compact layout. */
.fab {
  position: absolute;
  inset-inline-end: 16px;
  bottom: calc(16px + var(--safe-bottom));
  z-index: 3;
  border: 1px solid var(--tab-line);
  background-color: var(--tab-surface);
  box-shadow: var(--tab-shadow);
}
.root.editing .fab {
  display: none;
}
/* On an empty page the floating button is tonal; a tint and a deeper
   shadow raise it off the page, so it does not read as one more tile. */
.fab:not(.primary) {
  background-image: linear-gradient(var(--tab-tonal), var(--tab-tonal));
  box-shadow: var(--tab-shadow-dialog);
}
.missing {
  grid-row: main;
  grid-column: 1 / -1;
  display: grid;
  align-content: start;
  justify-items: start;
  gap: 12px;
  width: 100%;
  max-width: 640px;
  margin: 24px auto;
  padding: 0 16px;
}
.missing h2,
.missing p {
  margin: 0;
}
.missing h2 {
  font-size: var(--tab-fs-head);
  line-height: var(--tab-lh-head);
  font-weight: 500;
}
/* The toast's place inside the editor is worked out by the script (see
   _placeToast). */
.toast-region {
  position: absolute;
  z-index: 4;
  width: max-content;
  pointer-events: none;
}
/* The toast is dark in both themes, as Home Assistant's own. */
.toast {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  min-height: 48px;
  padding-block: 0;
  padding-inline: 16px 8px;
  border-radius: var(--tab-r-m);
  background: var(--tab-toast);
  color: var(--tab-toast-text);
  box-shadow: var(--tab-shadow);
  pointer-events: none;
  animation: toast-in 120ms ease-out;
}
.toast button {
  pointer-events: auto;
  padding-inline: 8px;
  border: 0;
  background: transparent;
  color: var(--tab-toast-text);
  font-weight: 600;
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
}
.toast button:hover,
.toast button:active {
  background: rgba(255, 255, 255, 0.12);
}
.toast button:focus-visible {
  outline-color: var(--tab-toast-text);
  box-shadow: 0 0 0 2px var(--tab-toast);
}
@keyframes toast-in {
  from {
    opacity: 0;
  }
}
.root.compact .empty-page {
  gap: 6px;
  font-size: var(--tab-fs-small);
  line-height: var(--tab-lh-small);
}
`;

// The editor's picture of the tablet lives in a shadow root of its own, with
// the tablet styles and this block only, so the editor's button and field
// styles cannot change how the drawn cards look.
export const canvasStyles = `
/* Text settings still pass into a shadow root from the page around it. The
   editor lets long words break anywhere; the tablet does not, so the
   picture goes back to the normal setting. */
:host {
  overflow-wrap: normal;
}
.warning-box {
  position: absolute;
  z-index: 20;
  display: grid;
  place-items: center;
  box-sizing: border-box;
  border: 2px solid var(--at-tx2, #9aa0a8);
  background: repeating-linear-gradient(
    135deg,
    transparent 0,
    transparent 8px,
    var(--at-tx2, #9aa0a8) 8px,
    var(--at-tx2, #9aa0a8) 10px
  );
  color: var(--at-tx, #e8eaed);
  font-weight: 600;
  pointer-events: none;
}
/* The words sit on a small solid chip in the page's colour, not on the
   hatch lines. */
.warning-box > span {
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--at-wall, #101418);
}
`;

export const pickerStyles = `
dialog.picker {
  box-sizing: border-box;
  width: min(960px, calc(100vw - 32px));
  max-width: none;
  max-height: calc(100dvh - 32px);
  padding: 0;
  border: 1px solid var(--tab-line);
  border-radius: var(--tab-r-dialog);
  background: var(--tab-surface);
  color: var(--tab-text);
  box-shadow: var(--tab-shadow-dialog);
  overflow-wrap: anywhere;
}
dialog.picker[open] {
  display: flex;
  flex-direction: column;
}
dialog.picker::backdrop {
  background: rgba(0, 0, 0, 0.55);
}
.picker-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-block: 16px 8px;
  padding-inline: 24px;
}
.picker-head h2 {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  font-size: var(--tab-fs-head);
  line-height: var(--tab-lh-head);
  font-weight: 500;
}
.picker-head > button {
  flex: 0 0 auto;
}
.picker-top {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
  padding-block: 0 12px;
  padding-inline: 24px;
}
.picker-top p {
  margin: 0;
}
.picker-top > button {
  justify-self: start;
}
/* The link's words line up with the sentence above it. */
.picker-top > button.link {
  margin-inline-start: -4px;
}
.picker-body {
  flex: 1 1 auto;
  min-height: 0;
  padding-block: 0 20px;
  padding-inline: 24px;
  overflow: auto;
}
.picker-body > p {
  margin: 12px 0;
}
.picker-group h3 {
  margin: 16px 0 8px;
  font-size: var(--tab-fs-body);
  line-height: var(--tab-lh-body);
  font-weight: 600;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.tile {
  display: grid;
  align-content: start;
  justify-content: stretch;
  justify-items: start;
  gap: 6px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--tab-line);
  border-radius: var(--tab-r-m);
  background-color: var(--tab-surface);
  font-weight: 400;
  text-align: start;
}
/* A switched-off card looks unavailable through its dashed edge, faded
   picture and lock, not by fading the whole tile: its words say why it is
   off and keep their full contrast. */
.tile:disabled {
  border-style: dashed;
  color: var(--tab-text);
}
.tile:disabled .tile-preview {
  opacity: 0.35;
}
.tile-locked {
  display: flex;
  align-items: center;
  gap: 6px;
}
.tile-locked ha-icon {
  flex: 0 0 auto;
  --mdc-icon-size: 18px;
}
.tile-preview {
  position: relative;
  display: grid;
  max-width: 100%;
  place-items: center;
  overflow: hidden;
  border-radius: var(--tab-r-s);
  background: var(--tab-stage);
  pointer-events: none;
}
.tile-preview > ha-icon {
  color: var(--tab-text-2);
}
.tile-preview apollo-tab-card {
  position: absolute;
  inset: 0;
}
.tile-name {
  font-weight: 500;
}
.tile-desc,
.tile-size,
.tile-locked {
  color: var(--tab-text-2);
  font-size: var(--tab-fs-small);
  line-height: var(--tab-lh-small);
}
.picker-fields {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
  padding-block: 4px 8px;
}
.picker-fields > * {
  min-width: 0;
}
.picker-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding-block: 12px 16px;
  padding-inline: 24px;
  border-top: 1px solid var(--tab-line);
}
.picker-foot .helper {
  flex: 1 1 200px;
}
dialog.picker.compact {
  width: 100vw;
  height: 100dvh;
  max-width: none;
  max-height: none;
  margin: 0;
  border: 0;
  border-radius: 0;
}
dialog.picker.compact .picker-head,
dialog.picker.compact .picker-top,
dialog.picker.compact .picker-body,
dialog.picker.compact .picker-foot {
  padding-inline: 12px;
}
/* On a phone the device step's title gets its own line under the Back and
   Close buttons, so none of them is squeezed. */
dialog.picker.compact .picker-head {
  flex-wrap: wrap;
}
dialog.picker.compact .picker-close {
  margin-inline-start: auto;
}
dialog.picker.compact [data-test="pick-back"] ~ h2 {
  order: 1;
  flex-basis: 100%;
}
dialog.picker.compact .tiles {
  grid-template-columns: minmax(0, 1fr);
}
dialog.picker.compact .tile {
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  column-gap: 12px;
}
dialog.picker.compact .tile-preview {
  grid-row: 1 / span 5;
}
dialog.picker.compact .tile > span {
  grid-column: 2;
}
`;

// The yes or no question from confirm.js, in its own shadow root on
// document.body, outside the panel: it has its own tokens.
export const confirmStyles = `
:host {
${tokens}
${hostType}
}
${coarseControls}
/* The dialog is centred on the window, so the window's width decides when
   its buttons are touch targets. */
@media (max-width: 899px) {
  :host {
    --tab-control: 44px;
    --tab-control-s: 44px;
  }
}
*,
*::before,
*::after {
  box-sizing: border-box;
}
${controls}
dialog {
  width: min(440px, calc(100vw - 32px));
  max-width: none;
  padding: 24px;
  border: 1px solid var(--tab-line);
  border-radius: var(--tab-r-dialog);
  background: var(--tab-surface);
  color: var(--tab-text);
  box-shadow: var(--tab-shadow-dialog);
  overflow-wrap: anywhere;
}
dialog::backdrop {
  background: rgba(0, 0, 0, 0.55);
}
h2 {
  margin: 0 0 8px;
  font-size: var(--tab-fs-head);
  line-height: var(--tab-lh-head);
  font-weight: 500;
}
p {
  margin: 0 0 20px;
  color: var(--tab-text);
}
/* A second paragraph, such as the tablets a deleted dashboard leaves,
   stays close to the first. */
p:has(+ p) {
  margin-bottom: 12px;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
}
/* On a phone both buttons share the row evenly, or take a row each when
   their words do not fit side by side. Cancel is outlined there, as large
   as the button beside it. */
@media (max-width: 480px) {
  .actions button {
    flex: 1 1 0;
    white-space: nowrap;
  }
  .actions button.text {
    border: 1px solid var(--tab-field-line);
  }
}
/* A tap leaves no hover layer behind on a touch screen. */
@media (hover: none) {
  button:not(:disabled):hover {
    background-image: none;
  }
}
`;

export const previewStyles = `
:host {
  display: block;
  box-sizing: border-box;
  padding: 16px;
  border-radius: var(--ha-card-border-radius, 12px);
  background: var(--ha-card-background, var(--card-background-color));
  color: var(--primary-text-color);
  font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
}
.notice,
.preview-message {
  padding: 12px;
  border: 1px solid var(--divider-color);
  border-radius: 10px;
}
.tablet-lines {
  display: grid;
  gap: 4px;
  margin-bottom: 12px;
}
.tablet-line {
  margin: 0;
}
.preview-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.page-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.page-tabs button {
  padding: 8px 12px;
  border: 1px solid var(--divider-color);
  border-radius: 8px;
  background: transparent;
  color: inherit;
}
.page-tabs button[aria-pressed="true"] {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: var(--text-primary-color);
}
.preview-stage {
  width: 100%;
  overflow: hidden;
  border-radius: 8px;
}
.page-host {
  position: relative;
  width: 100%;
  aspect-ratio: 1280 / 800;
}
.warning-box {
  position: absolute;
  z-index: 20;
  display: grid;
  place-items: center;
  box-sizing: border-box;
  border: 2px solid var(--at-tx2, #9AA0A8);
  background: repeating-linear-gradient(
    135deg,
    transparent 0,
    transparent 8px,
    var(--at-tx2, #9AA0A8) 8px,
    var(--at-tx2, #9AA0A8) 10px
  );
  color: var(--at-tx, #E8EAED);
  font-weight: 600;
  pointer-events: none;
}
/* The card under it is kept, so only its outline is marked. */
.warning-box.flat {
  border: 2px dashed var(--at-tx2, #9AA0A8);
  background: none;
}
li {
  margin: 6px 0;
}
`;

export const rendererStyles = `
.at-card,
.at-page,
.at-heading,
.at-nav {
  box-sizing: border-box;
  font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
  /* The tablet draws left to right in every language, and at its own text
     size whatever the browser would make of it. */
  direction: ltr;
  unicode-bidi: isolate;
  text-size-adjust: 100%;
  -webkit-text-size-adjust: 100%;
  /* Light text on dark as thin as the tablet's. */
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
.at-card {
  position: absolute;
  overflow: hidden;
  /* Edges and corners scale with the picture (--at-f is 1 at full size). */
  border: calc(var(--at-bw, 0px) * var(--at-f, 1)) solid var(--at-line, #2A303A);
  border-radius: calc(var(--at-r, 16px) * var(--at-f, 1));
  background: var(--at-bg, #181C23);
  color: var(--at-tx, #E8EAED);
}
/* Child rectangles are absolute (contract 4.3): this layer starts at the
   card's outer edge, so the border does not move the children. */
.at-card-body {
  position: absolute;
  inset: calc(-1 * var(--at-bw, 0px) * var(--at-f, 1));
}
.at-card[data-gradient="v"] {
  background: linear-gradient(to bottom, var(--at-bg), var(--at-bg2));
}
.at-card[data-gradient="h"] {
  background: linear-gradient(to right, var(--at-bg), var(--at-bg2));
}
.at-card.is-on {
  border-color: var(--at-acc, #F5B547);
  background: var(--at-onbg, #33291A);
  color: var(--at-ontx, #F7E3BC);
}
.at-header,
.at-label,
.at-heading {
  position: absolute;
  display: flex;
  align-items: center;
  box-sizing: border-box;
}
.at-header {
  overflow: hidden;
}
/* An icon's box is its glyph's box. Home Assistant's glyph is an inline box
   inside ha-icon; with a flex host it sits on no text line, so the text's
   line height cannot push it down and out of a small box. */
.at-card ha-icon,
.at-page ha-icon,
.at-heading ha-icon,
.at-nav ha-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.at-header ha-icon {
  flex: 0 0 auto;
  color: var(--at-tx2);
}
.at-header-title,
.at-text,
.at-button-text {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.at-label,
.at-heading {
  overflow: hidden;
}
.at-button ha-icon,
.at-heading ha-icon {
  flex: 0 0 auto;
}
.at-header-title {
  flex: 0 1 auto;
  font-weight: 600;
}
.at-label-s {
  color: var(--at-tx2);
}
.at-label-l {
  font-weight: 600;
}
.at-button,
.at-switch,
.at-thermostat button,
.at-nav-button {
  position: absolute;
  box-sizing: border-box;
  margin: 0;
  border: 0;
  color: var(--at-tx);
  font-family: inherit;
  cursor: pointer;
}
.at-button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: calc(6px * var(--at-f));
  overflow: hidden;
  padding: calc(6px * var(--at-f));
  border-radius: calc(var(--at-r2, 10px) * var(--at-f, 1));
  background: var(--at-card2, #232833);
  font-weight: 500;
}
.at-button.vertical {
  flex-direction: column;
}
.at-button.active {
  background: var(--at-accf, var(--at-acc));
  color: var(--at-acct);
}
.at-button.busy,
.at-switch.busy {
  outline: calc(2px * var(--at-f, 1)) solid var(--at-acc);
}
.at-switch {
  padding: calc(4px * var(--at-f));
  border-radius: 999px;
  background: var(--at-card2);
}
.at-switch-knob {
  position: absolute;
  top: 50%;
  left: calc(4px * var(--at-f));
  border-radius: 50%;
  background: var(--at-tx2);
  translate: 0 -50%;
  transition: left 120ms ease;
}
.at-switch.on {
  background: var(--at-acc);
}
.at-switch.on .at-switch-knob {
  left: calc(100% - 32px * var(--at-f));
  background: var(--at-acct);
}
.at-slider {
  position: absolute;
  touch-action: none;
}
/* The parts of a slider are placed by render.js in the slider's box. */
.at-slider-track,
.at-slider-fill,
.at-slider-knob,
.at-slider-handle,
.at-slider-mark,
.at-slider-icon {
  position: absolute;
  box-sizing: border-box;
}
.at-slider-track {
  background: var(--at-card2);
}
.at-slider-fill {
  background: var(--at-acc);
}
.at-slider-knob {
  border-radius: 50%;
  background: var(--at-tx);
}
.at-slider-handle {
  background: var(--at-acct);
}
.at-slider-mark {
  border-style: solid;
}
.at-slider-icon {
  display: grid;
  place-items: center;
  pointer-events: none;
}
.at-thermostat {
  position: absolute;
}
.at-thermostat svg {
  width: 100%;
  height: 100%;
}
.at-arc-track,
.at-arc-value {
  fill: none;
  stroke-linecap: round;
}
.at-arc-track {
  stroke: var(--at-card2);
}
.at-arc-value {
  stroke: var(--at-acc2);
}
.at-thermostat-value {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-weight: 600;
}
.at-thermostat button {
  bottom: 0;
  display: grid;
  width: calc(36px * var(--at-f));
  height: calc(36px * var(--at-f));
  place-items: center;
  border-radius: 50%;
  background: var(--at-card2);
}
.at-thermostat button.minus {
  left: 0;
}
.at-thermostat button.plus {
  right: 0;
}
.at-chart {
  position: absolute;
  overflow: visible;
}
.at-chart-baseline {
  stroke: var(--at-line);
}
.at-chart-line {
  fill: none;
  stroke: var(--at-acc2);
  stroke-width: calc(3px * var(--at-f, 1));
  stroke-linecap: round;
  stroke-linejoin: round;
}
.at-chart-bar {
  fill: var(--at-acc2);
}
.at-image {
  position: absolute;
  display: grid;
  overflow: hidden;
  place-items: center;
  border-radius: calc(var(--at-r2) * var(--at-f, 1));
  background: var(--at-card2);
  color: var(--at-acc2);
}
.at-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.at-page {
  position: absolute;
  overflow: hidden;
  background: var(--at-wall, #101418);
  color: var(--at-tx, #E8EAED);
}
.at-nav {
  position: absolute;
  background: var(--at-bg, #181C23);
}
.at-nav-button {
  display: grid;
  place-items: center;
  border-radius: calc(var(--at-r2, 10px) * var(--at-f, 1));
  background: transparent;
  color: var(--at-tx2);
}
.at-nav-button.active {
  background: var(--at-onbg);
  color: var(--at-acc);
}
.at-heading {
  gap: calc(8px * var(--at-f));
  color: var(--at-tx);
  font-size: calc(20px * var(--at-f));
  font-weight: 600;
}
.at-layout-card {
  position: absolute;
  overflow: hidden;
}
/* No value: 40% and no touch, as on the tablet (contract 4.7). */
.at-none {
  opacity: 0.4;
  pointer-events: none;
}
/* The tablet previews use the tablet's one font and weight (contract 4.7). */
.at-tablet,
.at-tablet .at-card,
.at-tablet .at-heading,
.at-tablet .at-nav {
  font-family: "Apollo TAB-1 Montserrat", var(--ha-font-family-body, Roboto, system-ui, sans-serif);
}
.at-tablet * {
  font-weight: 500;
  font-synthesis: none;
}
/* A line the preview has cut where the tablet cuts it: the browser must not
   cut it again. Each character sits in a box of the tablet's whole-pixel
   width, without kerning, as the tablet places its glyphs. */
.at-tablet .at-fitted {
  text-overflow: clip;
  font-kerning: none;
}
.at-tablet .at-ch {
  display: inline-block;
  white-space: pre;
}
/* The tablet's box for a character its font does not have. */
.at-nobox {
  display: inline-block;
  box-sizing: border-box;
  border: calc(1px * var(--at-f, 1)) solid currentColor;
  vertical-align: middle;
}
/* A card whose switch is on, drawn the way the tablet draws it. */
.at-card.is-on .at-header ha-icon {
  color: var(--at-ion, var(--at-acc));
}
.at-card.is-on .at-switch.on {
  background: var(--at-ion, var(--at-acc));
}
.at-card.is-on .at-switch.on .at-switch-knob {
  background: var(--at-onbg);
}
.at-card.is-on .at-slider-track {
  background: var(--at-onbg_pr, var(--at-card2));
}
.at-card.is-on .at-slider-fill {
  background: var(--at-ion, var(--at-acc));
}
.at-card.is-on .at-slider-knob {
  background: var(--at-ontx);
  box-shadow: 0 0 0 calc(2px * var(--at-f)) var(--at-onbg);
}
.at-card.is-on .at-arc-track {
  stroke: var(--at-onbg_pr, var(--at-card2));
}
.at-card.is-on .at-button.busy,
.at-card.is-on .at-switch.busy {
  outline-color: var(--at-ion, var(--at-acc));
}
.at-card.is-on .at-label-s {
  color: var(--at-onsm, var(--at-ontx));
}
/* Lit 1: the icons in the accent. Lit 2: an outline in the accent. */
.at-card.is-outline {
  border-color: var(--at-acc, #F5B547);
}
/* un: the whole card at 40%, once (contract 4.7). */
.at-card.is-un > .at-card-body {
  opacity: 0.4;
}
.at-card.at-pressable {
  cursor: pointer;
}
.at-card.pressed {
  background: var(--at-press, var(--at-card_pr, #232833));
}
.at-card[role="button"]:focus-visible {
  outline: calc(2px * var(--at-f, 1)) solid var(--primary-color, var(--at-acc));
  outline-offset: calc(2px * var(--at-f, 1));
}
/* Pressed looks in a browser card (4.7). The editor's picture has no live
   controls, so it never shows them. --at-wpr is card2_pr (on: onbg_pr). */
.at-button:not(:disabled):active {
  background: var(--at-bpr, var(--at-wpr, var(--at-card2_pr))) !important;
}
.at-choice-cell:not(:disabled):active > .at-choice-face {
  background: var(--at-fpr, var(--at-wpr, var(--at-card2_pr))) !important;
}
.at-image.bare.at-pressable:active {
  background: var(--at-wpr, var(--at-card2_pr));
}
/* vis 0: not drawn, and no press. */
.at-hidden {
  display: none !important;
}
/* A label line higher than its box starts at the top (contract 4.7). */
.at-label.at-tall {
  align-items: flex-start;
}
.at-button.round {
  border-radius: 50%;
  padding: 0;
}
.at-button.bare {
  background: transparent;
}
.at-button.selected {
  background: var(--at-accf, var(--at-acc));
  color: var(--at-acct);
}
.at-arc-mark {
  fill: var(--at-tx);
}
.at-chart-step {
  fill: var(--at-acc2);
}
.at-chart-bar.at-bar-acc {
  fill: var(--at-acc);
}
.at-chart-bar.at-bar-card2 {
  fill: var(--at-card2);
}
.at-image.badge {
  border-radius: 50%;
}
.at-image.bare {
  background: transparent;
}
.at-image.at-pressable {
  cursor: pointer;
}
.at-choice {
  position: absolute;
}
.at-choice-cell {
  position: absolute;
  box-sizing: border-box;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font-family: inherit;
  cursor: pointer;
}
.at-choice-face {
  position: absolute;
  display: flex;
  box-sizing: border-box;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 0 calc(6px * var(--at-f, 1));
  border-radius: calc(var(--at-r2, 10px) * var(--at-f, 1));
  background: var(--at-card2);
  font-weight: 500;
}
.at-choice-face.vertical {
  flex-direction: column;
}
.at-choice-face.dot {
  padding: 0;
  border-radius: 50%;
}
.at-choice.busy {
  outline: calc(2px * var(--at-f, 1)) solid var(--at-acc);
}
.at-nav-button.back {
  background: var(--at-onbg);
  color: var(--at-acc);
}
`;

// The browser card's detail dialog. It sits in the page, outside the card's
// own styles, so every rule starts with its class.
export const detailDialogStyles = `
.apollo-tab-detail {
  /* The room the dialog's frame takes from the window's height. */
  --at-detail-chrome: 120px;
  position: fixed;
  inset: 0;
  z-index: 8;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.6);
}
.apollo-tab-detail-box {
  box-sizing: border-box;
  width: min(
    100%,
    calc(var(--at-detail-w, 568px) + 32px),
    calc((100dvh - var(--at-detail-chrome)) * var(--at-detail-ratio, 10) + 32px)
  );
  max-height: calc(100dvh - 32px);
  overflow: auto;
  padding: 4px 16px 16px;
  border-radius: var(--ha-dialog-border-radius, 24px);
  background: var(--ha-dialog-surface-background, var(--mdc-theme-surface, var(--card-background-color, #1c1c1c)));
  color: var(--primary-text-color, #e1e1e1);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
}
.apollo-tab-detail-head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 56px;
}
.apollo-tab-detail-title {
  flex: 1;
  min-width: 0;
  margin: 0;
  overflow: hidden;
  font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
  font-size: 20px;
  font-weight: 500;
  line-height: 28px;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.apollo-tab-detail-close {
  display: grid;
  flex: none;
  width: 40px;
  height: 40px;
  margin-right: -8px;
  padding: 0;
  place-items: center;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: inherit;
  cursor: pointer;
}
.apollo-tab-detail-close:hover {
  background: rgba(127, 127, 127, 0.16);
}
.apollo-tab-detail-close:focus-visible {
  outline: 2px solid var(--primary-color, #03a9f4);
  outline-offset: 2px;
}
@media (max-width: 600px) {
  .apollo-tab-detail {
    --at-detail-chrome: 104px;
    padding: 8px;
  }
  .apollo-tab-detail-box {
    max-height: calc(100dvh - 16px);
    padding: 0 12px 12px;
  }
}
`;
