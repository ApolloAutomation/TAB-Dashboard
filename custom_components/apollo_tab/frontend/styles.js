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

// Buttons, inputs and selects shared by the panel, the editor and the picker.
// Every control is at least 44 px high so it is easy to press on a phone.
const controls = `
button,
input,
select,
.button-link {
  box-sizing: border-box;
  max-width: 100%;
  min-height: 44px;
  padding: 8px 14px;
  border: 1px solid var(--divider-color, #39414d);
  border-radius: 10px;
  background: var(--card-background-color, #181c23);
  color: var(--primary-text-color, #e8eaed);
  font: inherit;
}
button,
.button-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  text-decoration: none;
}
/* A field's edge is all that shows where it is, so it needs at least 3:1
   against the card (WCAG 1.4.11). The divider colour is far too faint for
   that; it stays on buttons, whose words already mark them. */
input,
select,
textarea {
  border-color: color-mix(in srgb, var(--primary-text-color, #e8eaed) 60%, transparent);
}
/* The browser's own placeholder grey is too faint on Home Assistant's dark
   cards (3.7:1); the secondary text colour reaches 4.5:1 in light and dark. */
input::placeholder,
textarea::placeholder {
  color: var(--secondary-text-color, #9aa0a8);
  opacity: 1;
}
button:disabled {
  cursor: default;
  opacity: 0.55;
}
/* Words on Home Assistant's primary colour do not reach 4.5:1 (white on the
   default #009ac7 is 3.3:1), so the primary colour marks a button's edge and
   tints its fill, and the words keep the normal text colour. */
button.primary {
  border: 2px solid var(--primary-color, #f5b547);
  background: color-mix(in srgb, var(--primary-color, #f5b547) 14%, var(--card-background-color, #181c23));
  color: var(--primary-text-color, #e8eaed);
  font-weight: 600;
}
button.link {
  border-color: transparent;
  background: transparent;
  color: var(--primary-text-color, #e8eaed);
  text-decoration: underline;
  text-decoration-color: var(--primary-color, #f5b547);
  text-decoration-thickness: 2px;
  text-underline-offset: 3px;
}
button:focus-visible,
input:focus-visible,
select:focus-visible,
a:focus-visible,
[tabindex]:focus-visible {
  outline: 3px solid var(--primary-color, #f5b547);
  outline-offset: 2px;
}
/* A screen's heading takes focus when the screen changes; the ring shows
   only when that came from the keyboard. */
.screen-heading:focus:not(:focus-visible) {
  outline: none;
}
a {
  color: var(--primary-text-color, #e8eaed);
  text-decoration-color: var(--primary-color, #f5b547);
  text-decoration-thickness: 2px;
  text-underline-offset: 3px;
}
input[type="checkbox"] {
  width: 22px;
  min-height: 22px;
  height: 22px;
  margin: 0;
  padding: 0;
  flex: 0 0 auto;
}
input[type="color"] {
  width: 64px;
  padding: 4px;
}
input[type="range"] {
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
}
.tag {
  display: inline-block;
  padding: 1px 8px;
  border: 1px solid var(--divider-color, #39414d);
  border-radius: 999px;
  color: var(--primary-text-color, #e8eaed);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.5;
  white-space: nowrap;
}
.small,
.helper,
.meta {
  margin: 0;
  color: var(--secondary-text-color, #9aa0a8);
  font-size: 13px;
}
/* Error text is the text people most need to read, and the error colour
   is too light for body text on white or dark cards. So the words keep the
   normal text colour and the error colour marks the line beside them. */
.alert {
  margin: 0;
  padding: 6px 10px;
  border-left: 4px solid var(--error-color, #db4437);
  border-radius: 4px;
  background: color-mix(in srgb, var(--error-color, #db4437) 12%, transparent);
  color: var(--primary-text-color, #e8eaed);
  font-weight: 500;
}
.alert:empty {
  padding: 0;
  border: 0;
  background: none;
}
`;

export const editorStyles = `
:host {
  display: block;
  color: var(--primary-text-color);
  font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
}
.hint {
  display: grid;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--divider-color);
  border-radius: 12px;
}
.hint h2 {
  margin: 0;
  font-size: 18px;
}
.hint p {
  margin: 0;
  color: var(--secondary-text-color);
}
.hint a {
  justify-self: start;
  color: var(--primary-text-color);
  font-weight: 500;
  text-decoration-color: var(--primary-color);
  text-decoration-thickness: 2px;
  text-underline-offset: 3px;
}
`;

export const panelStyles = `
:host {
  display: block;
  box-sizing: border-box;
  min-width: 0;
  min-height: 100%;
  background: var(--primary-background-color, #101418);
  color: var(--primary-text-color, #e8eaed);
  font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
  overflow-wrap: anywhere;
}
*,
*::before,
*::after {
  box-sizing: border-box;
}
${controls}
.panel-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px 12px;
  padding: 20px 24px;
  border-bottom: 1px solid var(--divider-color, #39414d);
  background: var(--app-header-background-color, var(--card-background-color, #181c23));
  color: var(--app-header-text-color, var(--primary-text-color, #e8eaed));
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
  font-size: 24px;
  font-weight: 500;
}
.panel-header p {
  margin: 0;
  color: var(--secondary-text-color, #9aa0a8);
}
.panel-content {
  display: grid;
  gap: 18px;
  min-width: 0;
  max-width: 960px;
  margin: 0 auto;
  padding: 24px;
}
.box {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--divider-color, #39414d);
  border-radius: 12px;
  background: var(--card-background-color, #181c23);
}
.box > * {
  margin: 0;
}
.box h2 {
  font-size: 18px;
  font-weight: 500;
}
.notice {
  border-left: 4px solid var(--primary-color, #f5b547);
}
.steps {
  display: grid;
  gap: 6px;
  padding-left: 22px;
}
.box > button,
.box > a {
  justify-self: start;
}
.dashboard-row,
.component-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding-top: 12px;
  border-top: 1px solid var(--divider-color, #39414d);
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
  font-size: 16px;
  font-weight: 500;
}
.row-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.code-line {
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--secondary-background-color, rgba(127, 127, 127, 0.14));
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
}
.advanced-link {
  display: grid;
  justify-items: start;
  gap: 2px;
}
.advanced-link button {
  padding-inline: 4px;
}
.error-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding-left: 20px;
}
@media (max-width: 700px) {
  .panel-header {
    padding: 16px 12px;
  }
  .panel-content {
    padding: 12px;
  }
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
  font-size: 15px;
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
.check {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  cursor: pointer;
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
  text-align: right;
}
.icon-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(44px, 1fr));
  gap: 6px;
}
.icon-grid button {
  min-width: 44px;
  padding: 0;
}
.icon-grid button[aria-pressed="true"] {
  border-color: var(--primary-color, #f5b547);
  background: var(--primary-color, #f5b547);
  color: var(--text-primary-color, #101418);
}
.chosen {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 8px 8px 12px;
  border: 1px solid var(--divider-color, #39414d);
  border-radius: 10px;
}
.chosen span {
  min-width: 0;
}
.entity-list {
  display: grid;
  gap: 4px;
  max-height: 320px;
  padding: 2px;
  overflow: auto;
}
.entity-option {
  display: grid;
  justify-content: stretch;
  justify-items: start;
  gap: 2px;
  text-align: left;
}
.entity-option[aria-selected="true"] {
  border-color: var(--primary-color, #f5b547);
  box-shadow: inset 0 0 0 1px var(--primary-color, #f5b547);
}
.entity-check {
  font-weight: 700;
}
.entity-option small {
  color: var(--secondary-text-color, #9aa0a8);
  overflow-wrap: anywhere;
}
.side-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}
.side-title:focus {
  outline: none;
}
.side-title:focus-visible {
  outline: 3px solid var(--primary-color, #f5b547);
}
.item-notes {
  display: grid;
  gap: 8px;
}
.item-notes:empty {
  display: none;
}
.note-line {
  margin: 0;
  padding: 8px 10px;
  border-left: 3px solid var(--secondary-text-color, #9aa0a8);
  border-radius: 4px;
  background: var(--secondary-background-color, rgba(127, 127, 127, 0.12));
}
.note-line.problem {
  border-left-color: var(--error-color, #db4437);
}
`;

export const designerStyles = `
:host {
  display: block;
  box-sizing: border-box;
  min-width: 0;
  color: var(--primary-text-color, #e8eaed);
  font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
  overflow-wrap: anywhere;
}
*,
*::before,
*::after {
  box-sizing: border-box;
}
${controls}
/* The editor's own layers (the card sheet, toasts, the picture's card
   buttons) stack inside it, so none of them can cover Home Assistant's
   sidebar or menus. */
.root {
  min-width: 0;
  padding-bottom: 24px;
  isolation: isolate;
}
.ed-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--divider-color, #39414d);
  background: var(--app-header-background-color, var(--card-background-color, #181c23));
  color: var(--app-header-text-color, var(--primary-text-color, #e8eaed));
}
/* As in the panel header: no gap after a menu button that draws nothing. */
.ed-header > ha-menu-button {
  margin-inline-end: -12px;
}
.ed-header h1 {
  flex: 1 1 160px;
  min-width: 0;
  margin: 0;
  font-size: 20px;
  font-weight: 500;
}
.ed-header .back {
  padding-inline: 10px;
}
.save-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 44px;
  color: var(--secondary-text-color, #9aa0a8);
}
.save-state[data-state="error"] {
  color: var(--app-header-text-color, var(--primary-text-color, #e8eaed));
  font-weight: 600;
}
.save-state[data-state="error"] ha-icon {
  color: var(--error-color, #db4437);
}
.header-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.banners {
  display: grid;
  gap: 12px;
  padding: 12px 24px 0;
}
.banners:empty {
  display: none;
}
.banner {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 12px 16px;
  border: 1px solid var(--divider-color, #39414d);
  border-left: 4px solid var(--primary-color, #f5b547);
  border-radius: 12px;
  background: var(--card-background-color, #181c23);
}
.banner.error {
  border-left-color: var(--error-color, #db4437);
}
.banner h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
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
/* On a wide screen a banner that offers a choice has its buttons beside
   its words, which takes less height above the tablet picture. */
.root:not(.compact) .banner.advice {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  column-gap: 24px;
}
.root:not(.compact) .banner.advice > .alert {
  grid-column: 1 / -1;
}
/* On a phone these banners come after the picture, inside the page's own
   column, which already has its own spacing. */
.root .main > .banners.advice-banners {
  padding: 0;
}
.hint-box:empty {
  display: none;
}
.note-line.not-shown-hint {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0 12px;
  padding-block: 0;
  border-left-color: var(--primary-color, #f5b547);
}
.not-shown-hint > span {
  padding-block: 8px;
}
.not-shown-hint button {
  padding-inline: 4px;
}
.body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  align-items: start;
  gap: 24px;
  padding: 16px 24px;
}
.main {
  display: grid;
  gap: 16px;
  min-width: 0;
}
/* Only the page tabs scroll sideways; Add page stays at the end of the
   strip, in view however many pages there are. The padding keeps the
   focus ring inside the scrolling box. */
.tab-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.tabs {
  display: flex;
  flex: 0 1 auto;
  gap: 8px;
  min-width: 0;
  padding: 2px 2px 6px;
  overflow-x: auto;
}
/* A tab is never squeezed to the width of the scrolling box: its name is
   cut only at the limit below, and the box scrolls instead. */
.tab {
  flex: 0 0 auto;
  max-width: none;
  border-radius: 999px;
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
.tab[aria-selected="true"] {
  border: 2px solid var(--primary-color, #f5b547);
  background: color-mix(in srgb, var(--primary-color, #f5b547) 22%, var(--card-background-color, #181c23));
  color: var(--primary-text-color, #e8eaed);
  font-weight: 600;
}
.tab[aria-selected="true"] .tag {
  border-color: currentColor;
  color: inherit;
}
.add-page {
  flex: 0 0 auto;
  margin-bottom: 4px;
  white-space: nowrap;
}
.caption-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 8px 16px;
}
.caption-row h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.stage {
  position: relative;
  width: 100%;
  aspect-ratio: 1280 / 800;
  overflow: hidden;
  border-radius: 12px;
  outline: 1px solid var(--divider-color, #39414d);
  background: #101418;
  isolation: isolate;
  scroll-margin: 8px;
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
  border-radius: 8px;
  background: transparent;
  scroll-margin: 8px;
}
.hit:hover {
  background: rgba(255, 255, 255, 0.08);
}
.hit[aria-pressed="true"] {
  outline: 3px solid #ffffff;
  outline-offset: 0;
  box-shadow: 0 0 0 5px #1565c0;
}
.hit:focus-visible {
  outline: 3px dashed #ffffff;
  outline-offset: 0;
  box-shadow: 0 0 0 5px #1565c0;
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
  opacity: 0.8;
}
.screens {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}
.screens .small {
  flex-basis: 100%;
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
.list-block {
  display: grid;
  gap: 10px;
}
.list-block h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.card-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.card-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 8px;
  min-width: 0;
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
  padding: 10px 12px;
  border-radius: 12px;
  text-align: left;
}
.list-row[aria-current="true"] {
  border-color: var(--primary-color, #f5b547);
  box-shadow: inset 0 0 0 1px var(--primary-color, #f5b547);
}
.list-row ha-icon {
  grid-row: 1 / span 4;
  color: var(--secondary-text-color, #9aa0a8);
}
.list-row span {
  min-width: 0;
}
.row-name {
  font-weight: 500;
}
.row-device,
.row-reason {
  color: var(--secondary-text-color, #9aa0a8);
  font-size: 13px;
}
.row-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
  margin-left: auto;
}
.row-remove,
.row-move {
  flex: 0 0 auto;
}
.side {
  position: sticky;
  top: 16px;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
  min-width: 0;
  max-height: calc(100vh - 32px);
  padding: 16px;
  overflow: auto;
  border: 1px solid var(--divider-color, #39414d);
  border-radius: 12px;
  background: var(--card-background-color, #181c23);
}
.side > * {
  min-width: 0;
}
.side > p {
  margin: 0;
}
/* Both buttons stay on one line; the settings link wraps its own words
   when the panel is narrow, so the form starts as high as it can. */
.side-top {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
}
.side-back {
  justify-self: start;
  padding-inline: 4px;
  text-align: start;
}
.missing {
  display: grid;
  justify-items: start;
  gap: 12px;
  max-width: 640px;
  margin: 24px auto;
  padding: 0 16px;
}
.missing h2,
.missing p {
  margin: 0;
}
/* The editor moves a shown toast to a spot where it covers nothing the
   person is working with (see _placeToast); this is where it starts. */
.toast-region {
  position: fixed;
  bottom: 16px;
  left: 50%;
  z-index: 4;
  width: max-content;
  max-width: calc(100vw - 24px);
  transform: translateX(-50%);
  pointer-events: none;
}
.toast {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 6px 6px 6px 16px;
  border-radius: 12px;
  background: var(--primary-text-color, #e8eaed);
  color: var(--primary-background-color, #101418);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
  pointer-events: none;
  animation: toast-in 120ms ease-out;
}
.toast button {
  pointer-events: auto;
  border-color: currentColor;
  background: transparent;
  color: inherit;
}
@keyframes toast-in {
  from {
    opacity: 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .toast {
    animation: none;
  }
}
.root.compact .ed-header {
  padding: 8px 12px;
}
.root.compact .banners {
  padding: 12px 12px 0;
}
/* A column, not a grid: a grid item can only stick inside its own row. */
.root.compact .body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 12px;
}
.root.compact .side {
  position: static;
  max-height: none;
  overflow: visible;
}
/* The selected card's form is a sheet held at the bottom of the screen
   while the page scrolls. It is sticky rather than fixed, so it stays
   inside the panel's width and never covers Home Assistant's sidebar, and
   it leaves the upper half of the screen for the tablet picture. */
.root.compact .side.sheet {
  position: sticky;
  top: auto;
  bottom: 0;
  z-index: 3;
  max-height: 45vh;
  max-height: 45dvh;
  padding: 12px 12px 24px;
  overflow: auto;
  border-radius: 16px 16px 0 0;
  box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.35);
}
.root.compact.sheet-open,
.root.compact.sheet-open .body {
  padding-bottom: 0;
}
.root.compact .empty-page {
  gap: 6px;
  font-size: 13px;
}
.root.compact .empty-page .small {
  font-size: 12px;
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
`;

export const pickerStyles = `
dialog.picker {
  box-sizing: border-box;
  width: min(960px, calc(100vw - 32px));
  max-width: none;
  max-height: calc(100dvh - 32px);
  padding: 0;
  border: 1px solid var(--divider-color, #39414d);
  border-radius: 16px;
  background: var(--card-background-color, #181c23);
  color: var(--primary-text-color, #e8eaed);
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
  padding: 16px 20px 8px;
}
.picker-head h2 {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  font-size: 20px;
  font-weight: 500;
}
.picker-head > button {
  flex: 0 0 auto;
}
.picker-top {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
  padding: 0 20px 12px;
}
.picker-top p {
  margin: 0;
}
.picker-top > button {
  justify-self: start;
}
.picker-body {
  flex: 1 1 auto;
  min-height: 0;
  padding: 0 20px 20px;
  overflow: auto;
}
.picker-body > p {
  margin: 12px 0;
}
.picker-group h3 {
  margin: 16px 0 8px;
  font-size: 15px;
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
  border-radius: 12px;
  text-align: left;
}
/* A switched-off card looks unavailable through its dashed edge, faded
   picture and lock, not by fading the whole tile: its words say why it is
   off and keep their full contrast. */
.tile:disabled {
  border-style: dashed;
  opacity: 1;
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
  border-radius: 8px;
  background: rgba(127, 127, 127, 0.14);
  pointer-events: none;
}
.tile-preview > ha-icon {
  color: var(--secondary-text-color, #9aa0a8);
}
.tile-preview apollo-tab-card {
  position: absolute;
  inset: 0;
}
.tile-name {
  font-weight: 600;
}
.tile-desc,
.tile-size,
.tile-locked {
  color: var(--secondary-text-color, #9aa0a8);
  font-size: 13px;
}
.picker-fields {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
  padding: 4px 0 8px;
}
.picker-fields > * {
  min-width: 0;
}
.picker-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 12px 20px 16px;
  border-top: 1px solid var(--divider-color, #39414d);
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
  padding-right: 12px;
  padding-left: 12px;
}
/* On a phone the device step's title gets its own line under the Back and
   Close buttons, so none of them is squeezed. */
dialog.picker.compact .picker-head {
  flex-wrap: wrap;
}
dialog.picker.compact .picker-close {
  margin-left: auto;
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

// The yes or no question from confirm.js, in its own shadow root.
export const confirmStyles = `
*,
*::before,
*::after {
  box-sizing: border-box;
}
${controls}
dialog {
  width: min(440px, calc(100vw - 32px));
  max-width: none;
  padding: 20px;
  border: 1px solid var(--divider-color, #39414d);
  border-radius: 16px;
  background: var(--card-background-color, #181c23);
  color: var(--primary-text-color, #e8eaed);
  font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
  overflow-wrap: anywhere;
}
dialog::backdrop {
  background: rgba(0, 0, 0, 0.55);
}
h2 {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 500;
}
p {
  margin: 0 0 20px;
  color: var(--primary-text-color, #e8eaed);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
}
button.danger {
  border: 2px solid var(--error-color, #db4437);
  background: transparent;
  color: var(--primary-text-color, #e8eaed);
  font-weight: 600;
}
button.danger ha-icon {
  color: var(--error-color, #db4437);
}
@media (max-width: 480px) {
  .actions {
    flex-direction: column;
  }
  .actions button {
    width: 100%;
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
}
.at-card {
  position: absolute;
  overflow: hidden;
  border: var(--at-bw, 0px) solid var(--at-line, #2A303A);
  border-radius: var(--at-r, 16px);
  background: var(--at-bg, #181C23);
  color: var(--at-tx, #E8EAED);
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
  border-radius: var(--at-r2, 10px);
  background: var(--at-card2, #232833);
  font-weight: 500;
}
.at-button.vertical {
  flex-direction: column;
}
.at-button.active {
  background: var(--at-acc);
  color: var(--at-acct);
}
.at-button.busy,
.at-switch.busy {
  outline: 2px solid var(--at-acc);
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
  display: flex;
  align-items: center;
  touch-action: none;
}
.at-slider-track {
  position: relative;
  width: 100%;
  background: var(--at-card2);
}
.at-slider-fill {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: inherit;
  background: var(--at-acc);
}
.at-slider-knob {
  position: absolute;
  top: 50%;
  border-radius: 50%;
  background: var(--at-tx);
  translate: -50% -50%;
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
  stroke-width: 1;
}
.at-chart-line {
  fill: none;
  stroke: var(--at-acc2);
  stroke-width: 3;
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
  border-radius: var(--at-r2);
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
  border-radius: var(--at-r2, 10px);
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
/* A card whose switch is on, drawn the way the tablet draws it. */
.at-card.is-on .at-header ha-icon {
  color: var(--at-ion, var(--at-acc));
}
.at-card.is-on .at-label-s {
  color: var(--at-ontx);
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
`;
