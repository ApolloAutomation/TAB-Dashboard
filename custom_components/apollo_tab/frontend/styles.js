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

export const editorStyles = `
:host {
  display: block;
  color: var(--primary-text-color);
  font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
}
h2, h3, p {
  margin-top: 0;
}
h2 {
  margin-bottom: 6px;
  font-size: 20px;
}
h3 {
  margin: 24px 0 12px;
  font-size: 16px;
}
.component-intro p,
.helper {
  color: var(--secondary-text-color);
}
.notice {
  padding: 12px;
  border: 1px solid var(--divider-color);
  border-radius: 10px;
}
.field {
  display: grid;
  gap: 6px;
  margin: 12px 0;
}
.field-label {
  font-weight: 500;
}
input,
select,
button {
  box-sizing: border-box;
  min-height: 40px;
  padding: 8px 10px;
  border: 1px solid var(--divider-color);
  border-radius: 8px;
  background: var(--card-background-color);
  color: var(--primary-text-color);
  font: inherit;
}
input[type="checkbox"] {
  width: 24px;
  min-height: 24px;
}
input[type="color"] {
  width: 64px;
}
button {
  cursor: pointer;
}
button.primary {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: var(--text-primary-color);
}
.helper {
  font-size: 12px;
}
.multi,
.basic-form {
  display: grid;
  gap: 8px;
}
.editor-error {
  padding: 16px;
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

export const panelStyles = `
:host {
  display: block;
  min-height: 100%;
  background: var(--primary-background-color);
  color: var(--primary-text-color);
  font-family: var(--ha-font-family-body, Roboto, system-ui, sans-serif);
}
.panel-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 20px 24px;
  border-bottom: 1px solid var(--divider-color);
  background: var(--app-header-background-color, var(--card-background-color));
}
.panel-header h1 {
  margin: 0 0 4px;
}
.panel-header p {
  margin: 0;
  color: var(--secondary-text-color);
}
.panel-content {
  display: grid;
  gap: 18px;
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
}
.notice,
.section-card,
.dashboard-block {
  box-sizing: border-box;
  padding: 16px;
  border: 1px solid var(--divider-color);
  border-radius: 12px;
  background: var(--card-background-color);
}
.section-card {
  display: grid;
  gap: 14px;
}
.dashboard-block {
  display: grid;
  gap: 10px;
}
h2, h3, p {
  margin-top: 0;
}
button,
.button-link,
select {
  box-sizing: border-box;
  min-height: 40px;
  padding: 9px 13px;
  border: 1px solid var(--divider-color);
  border-radius: 8px;
  background: var(--card-background-color);
  color: var(--primary-text-color);
  font: inherit;
}
button,
.button-link {
  width: max-content;
  cursor: pointer;
  text-decoration: none;
}
button.primary {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: var(--text-primary-color);
}
.meta {
  color: var(--secondary-text-color);
}
.select-field {
  display: grid;
  gap: 6px;
  max-width: 320px;
}
.component-list {
  display: grid;
  gap: 8px;
}
.component-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--divider-color);
}
.component-details {
  display: grid;
  flex: 1;
  gap: 3px;
}
.sensitive-controls {
  display: grid;
  justify-items: end;
  gap: 5px;
}
.status-message {
  color: var(--primary-color);
}
.error-list {
  color: var(--error-color);
}
@media (max-width: 700px) {
  .panel-content {
    padding: 12px;
  }
  .component-row {
    align-items: flex-start;
    flex-wrap: wrap;
  }
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
