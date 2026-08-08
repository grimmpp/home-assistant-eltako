/**
 * Simulation page: gateways and devices without any hardware.
 *
 * Create a simulated gateway (a LAN gateway, a USB ESP3 stick, a FAM14 - the real types, only
 * their hardware is missing), put virtual devices behind it, define the values those devices
 * report and trigger their telegrams. Everything behind the gateway - entities, telegram log,
 * statistics - cannot tell a simulated device from a real one, which is exactly the point: it
 * makes the whole integration testable without a single piece of hardware.
 *
 * The page only calls the backend (custom_components/eltako/simulation): all logic lives there,
 * so the command line (`python -m eltako_standalone simulate ...`) can do the very same things.
 */

import { WS } from "../lib/api.js";
import { FORM_STYLES } from "../lib/form.js";
import { escapeHtml, formatDateTime, icon } from "../lib/utils.js";

/** state of one device row which is being edited, keyed by "<gateway id>|<address>" */
const rowKey = (gatewayId, address) => `${gatewayId}|${address}`;

/** "FF-C0-02-01" (also with colons or without separators) -> 0xFFC00201, null if malformed */
const parseAddress = (text) => {
  const hex = String(text || "").trim().replace(/[\s:.-]/g, "");
  return /^[0-9a-fA-F]{8}$/.test(hex) ? parseInt(hex, 16) : null;
};

/** 0xFFC00201 -> "FF-C0-02-01" */
const formatAddress = (value) =>
  value.toString(16).toUpperCase().padStart(8, "0").match(/.{2}/g).join("-");

// TODO type check: add /** @type {import("../types.js").Page} */ once the dom casts are in
export const page = {
  id: "simulation",
  title: "Simulation",
  subtitle: "Gateways and devices without hardware - define values and trigger telegrams",
  icon: "mdi:flask-outline",
  glyph: "⚗",
  refreshMs: 20000,

  styles: FORM_STYLES + `
    .sim-intro { display: flex; flex-wrap: wrap; gap: 10px 20px; justify-content: space-between;
                 font-size: .84rem; margin-bottom: 14px; }
    .sim-gateway { background: var(--eltako-card); border: 1px solid var(--eltako-border);
                   border-radius: var(--eltako-radius); margin-bottom: 14px; overflow: hidden; }
    /* a simulated gateway is marked with a striped edge - it is never real hardware */
    .sim-gateway { border-left: 4px solid var(--eltako-accent); }
    .sim-gateway-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
                        padding: 12px 14px; border-bottom: 1px solid var(--eltako-border); }
    .sim-gateway-head .sim-title { font-weight: 500; }
    .sim-gateway-head .spacer { flex: 1 1 auto; }
    .sim-meta { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: .74rem;
                color: var(--eltako-muted); padding: 8px 14px 0; }
    .sim-devices { padding: 4px 14px 14px; }
    .sim-empty { font-size: .82rem; color: var(--eltako-muted); padding: 10px 0; }
    .sim-fields { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: flex-end; }
    .sim-field { display: flex; flex-direction: column; gap: 2px; }
    .sim-field label { font-size: .68rem; color: var(--eltako-muted); }
    .sim-field input { font: inherit; font-size: .8rem; padding: 4px 6px; width: 92px;
                       border-radius: 6px; border: 1px solid var(--eltako-border);
                       background: var(--eltako-card); color: var(--primary-text-color); }
    .sim-row-actions { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
    .sim-repeat { display: flex; align-items: center; gap: 4px; }
    /* half as wide as a normal input - it holds seconds, at most four digits. The spinner
       arrows are hidden, they would eat most of that width. */
    .sim-repeat input { font: inherit; font-size: .8rem; padding: 4px 4px; width: 31px;
                        border-radius: 6px; border: 1px solid var(--eltako-border);
                        background: var(--eltako-card); color: var(--primary-text-color);
                        appearance: textfield; -moz-appearance: textfield; text-align: right; }
    .sim-repeat input::-webkit-outer-spin-button,
    .sim-repeat input::-webkit-inner-spin-button { appearance: none; margin: 0; }
    .sim-sender { display: inline-flex; align-items: center; gap: 4px; margin: 2px 4px 0 0;
                  padding: 1px 4px 1px 6px; border-radius: 10px; font-size: .72rem;
                  background: var(--eltako-tint-strong); }
    .sim-sender i { font-style: normal; color: var(--eltako-muted); }
    .sim-sender-remove { border: 0; background: none; cursor: pointer; font-size: .9rem;
                         line-height: 1; color: var(--eltako-muted); padding: 0 2px; }
    .sim-sender-remove:hover { color: var(--eltako-warn); }
    .sim-teach { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin-top: 6px; }
    .sim-teach input, .sim-teach select { font: inherit; font-size: .78rem; padding: 3px 5px;
                       border-radius: 6px; border: 1px solid var(--eltako-border);
                       background: var(--eltako-card); color: var(--primary-text-color); width: 118px; }
    .sim-teach .sim-note { flex: 1 1 100%; }
    .sim-note { font-size: .72rem; color: var(--eltako-muted); }
    .sim-note.ok { color: var(--label-badge-green, #43a047); }
    .sim-note.warn { color: var(--eltako-warn); }
    .sim-add { border: 1px solid var(--eltako-accent); border-radius: 10px; padding: 12px 14px;
               margin: 8px 0 12px; background: var(--eltako-tint); }
    .sim-add h4 { margin: 0 0 10px; font-size: .88rem; font-weight: 500; }
    .sim-presets { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
                   gap: 10px; margin: 10px 0 4px; }
    .sim-preset { border: 1px solid var(--eltako-border); border-radius: 10px; padding: 10px 12px;
                  font-size: .8rem; display: flex; flex-direction: column; gap: 6px; }
    .sim-preset b { font-weight: 500; }
    .sim-preset .sim-note { flex: 1 1 auto; }
  `,

  async load(ctx) {
    const overview = await ctx.api.call(WS.SIMULATOR_FORM);
    if (overview) {
      ctx.state.simulation = overview;
      ctx.state.simulationUnavailable = null;
    } else {
      // The page is javascript served from disk, the commands behind it are python held in
      // memory: after an update of the integration the browser has the new page while Home
      // Assistant still runs the old code. Without saying so, every button would look dead.
      ctx.state.simulationUnavailable = (ctx.api.lastError || {}).message
        || "The backend of the simulation did not answer.";
      ctx.api.lastError = null;
    }
    await ctx.loadIntegrationInfo();
  },

  badge(ctx) {
    const count = (ctx.state.simulation || {}).device_count || 0;
    return count ? String(count) : null;
  },

  renderToolbar(ctx) {
    const busy = !!ctx.state.simulationBusy;
    const active = (ctx.state.simulation || {}).active !== false;
    return `
      <button id="sim-activate" class="action ${active ? "" : "primary"}" ${busy ? "disabled" : ""}
              title="${active
                ? "Deactivates the simulation: every simulated device is taken out of Home Assistant (entities and devices disappear) and nothing is sent anymore. The simulation itself is kept and can still be edited."
                : "Activates the simulation: the gateways are set up again and their devices are put back into Home Assistant."}">
        ${active ? `${icon("mdi:power-plug-off-outline", "⏻")} Deactivate simulation`
                 : `${icon("mdi:power-plug-outline", "▶")} Activate simulation`}</button>
      <span class="spacer" style="flex:0 0 8px"></span>
      <button id="sim-starter" class="action primary" ${busy ? "disabled" : ""}
              title="Creates a simulated LAN gateway, a USB300 and a FAM14 - each with example devices">
        ${icon("mdi:auto-fix", "✦")} Create starter set</button>
      <button id="sim-add-gateway" class="action" ${busy ? "disabled" : ""}>+ Add gateway</button>
      <span class="spacer"></span>
      <span class="field-help">${busy ? "Working&hellip;"
        : "The telegrams are sent by the backend - this page does not have to stay open."}</span>`;
  },

  bindToolbar(ctx, root) {
    const starter = root.getElementById("sim-starter");
    if (starter) starter.addEventListener("click", () => this._createStarterSet(ctx));
    const activate = root.getElementById("sim-activate");
    if (activate) {
      activate.addEventListener("click", () =>
        this._setActive(ctx, (ctx.state.simulation || {}).active === false));
    }
    const add = root.getElementById("sim-add-gateway");
    if (add) {
      add.addEventListener("click", () => {
        ctx.state.simulationNewGateway = ctx.state.simulationNewGateway ? null : {};
        ctx.requestContentRender(true);
      });
    }
  },

  render(ctx) {
    const simulation = ctx.state.simulation;
    // messages and errors are rendered in every case - also when nothing could be loaded,
    // otherwise a failed request looks like a button which does nothing
    const notices = `
      ${ctx.state.simulationMessage
        ? `<div class="settings-ok">${escapeHtml(ctx.state.simulationMessage)}</div>` : ""}
      ${ctx.state.simulationError
        ? `<div class="form-error">${escapeHtml(ctx.state.simulationError)}</div>` : ""}`;

    if (ctx.state.simulationUnavailable) return notices + this._renderUnavailable(ctx);
    if (!simulation) return notices + `<div class="empty">Loading the simulation&hellip;</div>`;

    const gateways = simulation.gateways || [];
    return `
      <div class="sim-intro">
        <div style="max-width:60ch">${escapeHtml(simulation.hint || "")}</div>
        <div class="sim-note">${gateways.length} simulated gateway(s),
          ${simulation.device_count || 0} device(s)${simulation.repeating_count
            ? `, ${simulation.repeating_count} sending on their own` : ""}${
            simulation.active === false ? ", <b>deactivated</b>" : ""}</div>
      </div>
      ${notices}
      ${simulation.active === false ? `
        <div class="notice warn">
          <h3>${icon("mdi:power-plug-off-outline", "⏻")} The simulation is deactivated</h3>
          <p>Nothing of it exists in Home Assistant right now: the simulated devices were taken
            out of the configuration - their entities and devices are gone - and the simulated
            gateways are not set up. So it cannot be used, neither by an automation nor by
            accident.</p>
          <p>Everything is <b>kept</b>: the gateways, the devices, their values and their
            intervals are still here and can be created, changed and removed. Activating puts all
            of it back into Home Assistant.</p>
          <p><button class="action primary" id="sim-resume">${icon("mdi:power-plug-outline", "▶")}
            Activate simulation</button></p>
        </div>` : ""}
      ${this._renderNewGateway(ctx, simulation)}
      ${gateways.length
        ? gateways.map((gateway) => this._renderGateway(ctx, simulation, gateway)).join("")
        : this._renderEmpty(ctx, simulation)}
      ${this._renderRealGateways(ctx, simulation)}
      <div class="footnote">${icon("mdi:information-outline", "i")}
        Two telegrams are called teach-in and they run in opposite directions:
        <b>Profile teach-in</b> is what a sensor sends to announce what it is (4BS with function,
        type and manufacturer; 1BS a learn telegram; RPS has none, so a button press is sent).
        <b>ELTAKO teach-in</b> is what a sender sends so that an actuator takes it into its memory -
        the telegram the teach-in button of Home Assistant produces, sent from the sender address.
      </div>
      <div class="footnote">${icon("mdi:information-outline", "i")}
        A simulated device is not configured yet: press <b>Search devices</b> on the device page
        (or <b>Search for gateways &amp; devices</b> on the overview) - the detection takes every
        simulated device over into the configuration, exactly like a device found on a real bus.</div>`;
  },

  /* ------------------------------------------------------------------ pieces */

  /**
   * The commands of the simulation are not there. That has exactly one usual cause: this page
   * comes from disk, the commands come from the python code Home Assistant loaded when it
   * started - so an updated integration has the page but not yet the backend.
   */
  _renderUnavailable(ctx) {
    return `
      <div class="notice warn">
        <h3>${icon("mdi:alert-outline", "!")} The simulation is not available in this Home Assistant</h3>
        <p><code>${escapeHtml(ctx.state.simulationUnavailable)}</code></p>
        <p>This page is javascript which is served from disk; the commands behind it are python
          which Home Assistant loaded when it started. After updating the integration both have
          to meet again:</p>
        <ol>
          <li><b>Restart Home Assistant</b> (Developer tools &rarr; Restart, or restart the
            container/service). Reloading the integration is not enough - the websocket commands
            are registered while the component is set up.</li>
          <li><b>Reload this page with an empty cache</b> (Ctrl/Cmd + Shift + R), so the browser
            does not keep an old module of the panel.</li>
        </ol>
        <p><button class="action primary" id="sim-retry">Try again</button></p>
      </div>`;
  },

  /**
   * Real gateways can host a virtual device as well. Its telegrams are then really transmitted -
   * a simulated wall switch can switch a real actuator - and its addresses derive from the base
   * id of that gateway, because a wireless transceiver only sends its own senders.
   */
  _renderRealGateways(ctx, simulation) {
    const free = (simulation.real_gateways || []).filter((gateway) => !gateway.hosting);
    if (!free.length) return "";

    return `
      <div class="notice">
        <h3>${icon("mdi:router-wireless", "◉")} Put a virtual device on a real gateway</h3>
        <p>Its telegrams are then <b>really transmitted</b> by that gateway, so a simulated wall
          switch can switch a real actuator. The addresses of such a device derive from the base
          id of that gateway - a wireless transceiver only sends senders of its own range.</p>
        <div class="sim-presets">
          ${free.map((gateway) => `
            <div class="sim-preset">
              <b>${escapeHtml(gateway.name)}</b>
              <span class="sim-note">${escapeHtml(gateway.device_type)}, base id
                <span class="mono">${escapeHtml(gateway.base_id)}</span></span>
              <button class="action small" data-sim-add-device="${escapeHtml(gateway.id)}">
                + Add device</button>
              ${this._renderAddDevice(ctx, simulation, { ...gateway, simulated: false })}
            </div>`).join("")}
        </div>
      </div>`;
  },

  _renderEmpty(ctx, simulation) {
    return `
      <div class="notice">
        <h3>Nothing is simulated yet</h3>
        <p>The starter set is the fastest way in: it creates the three kinds of gateway this
          integration talks to and puts the same example devices behind each of them.</p>
        <div class="sim-presets">
          ${(simulation.presets || []).map((preset) => `
            <div class="sim-preset">
              <b>${escapeHtml(preset.name)}</b>
              <span class="sim-note">${escapeHtml(preset.description || "")}</span>
              <span class="sim-note">${escapeHtml(preset.device_type)}${
                preset.exists ? " &ndash; exists already" : ""}</span>
            </div>`).join("")}
        </div>
        <p class="sim-note">Example devices per gateway:
          ${(simulation.device_presets || []).map((preset) =>
            `${escapeHtml(preset.name)} (${escapeHtml(preset.eep)})`).join(", ")}</p>
        <p><button class="action primary" id="sim-starter-empty">
          ${icon("mdi:auto-fix", "✦")} Create starter set</button></p>
      </div>`;
  },

  _renderNewGateway(ctx, simulation) {
    if (!ctx.state.simulationNewGateway) return "";
    const types = simulation.gateway_types || [];
    const presets = simulation.presets || [];
    return `
      <div class="form-card" id="sim-new-gateway">
        <h3>Add a simulated gateway</h3>
        <div class="form-grid">
          <div class="field">
            <label for="sim-new-type">Gateway type</label>
            <select id="sim-new-type">
              ${presets.map((preset) => `<option value="${escapeHtml(preset.device_type)}">
                ${escapeHtml(preset.name)} (${escapeHtml(preset.device_type)})</option>`).join("")}
              ${types.filter((type) => !presets.some((preset) => preset.device_type === type))
                .map((type) => `<option value="${escapeHtml(type)}">${escapeHtml(type)}</option>`).join("")}
            </select>
            <span class="field-help">The real type is simulated: a FAM14 stays a bus gateway
              (local addresses), a stick or a LAN gateway stays a wireless transceiver.</span>
          </div>
          <div class="field">
            <label for="sim-new-name">Name</label>
            <input type="text" id="sim-new-name" placeholder="Simulator" />
          </div>
          <div class="field field-inline">
            <label for="sim-new-devices">With example devices</label>
            <input type="checkbox" id="sim-new-devices" checked />
          </div>
        </div>
        <div class="form-actions">
          <button class="action primary" id="sim-new-save">Create gateway</button>
          <button class="action" id="sim-new-cancel">Cancel</button>
        </div>
      </div>`;
  },

  _renderGateway(ctx, simulation, gateway) {
    const devices = gateway.devices || [];
    const adding = String((ctx.state.simulationNewDevice || {}).gatewayId) === String(gateway.id);
    return `
      <div class="sim-gateway">
        <div class="sim-gateway-head">
          ${icon(gateway.simulated === false ? "mdi:router-wireless" : "mdi:flask-outline", "⚗")}
          <span class="sim-title">${escapeHtml(gateway.name)}</span>
          ${gateway.simulated === false
            ? `<span class="tag unknown" title="A real gateway: the telegrams of these simulated devices are really transmitted, and their addresses derive from its base id">real gateway</span>`
            : `<span class="tag simulated">simulated</span>`}
          <span class="tag ${gateway.bus_gateway ? "source-yaml" : "source-ui"}">
            ${escapeHtml(gateway.device_type)}</span>
          <span class="pill ${gateway.connected ? "on" : "off"}">
            ${gateway.connected ? "ready" : gateway.set_up ? "not connected" : "not set up"}</span>
          <span class="spacer"></span>
          ${gateway.simulated === false ? "" : `<button class="action small" data-sim-base-id="${gateway.id}"
                  title="Sends the base id info telegram - the answer a real gateway gives when it is asked for its base id after connecting">
            Send base id</button>`}
          <button class="action small ${adding ? "primary" : ""}" data-sim-add-device="${gateway.id}">
            ${adding ? "Close form" : "+ Add device"}</button>
          <button class="action small" data-sim-examples="${gateway.id}"
                  title="Adds the example devices (light, dimmer, cover, heating, sensors)">+ Examples</button>
          ${gateway.simulated === false ? "" : `<button class="action small danger"
            data-sim-remove-gateway="${gateway.id}">Remove gateway</button>`}
        </div>
        <div class="sim-meta">
          <span>Gateway id <b>${escapeHtml(gateway.id)}</b></span>
          <span>Base id <span class="mono">${escapeHtml(gateway.base_id)}</span></span>
          <span>Addresses ${gateway.bus_gateway
            ? "local (00-00-00-xx), senders 00-00-B0-xx"
            : "wireless, inside the base id range"}</span>
          <span>Connection <span class="mono">${escapeHtml(gateway.serial_path)}</span></span>
          <span>${gateway.simulated === false
            ? "Telegrams are <b>really transmitted</b> by this gateway"
            : "Telegrams are injected into this gateway"}</span>
        </div>
        <div class="sim-devices">
          ${this._renderAddDevice(ctx, simulation, gateway)}
          ${devices.length ? this._renderDeviceTable(ctx, gateway, devices)
            : `<div class="sim-empty">No device yet. <b>+ Examples</b> creates one of each kind
                 (light, dimmable light, cover, heating/cooling, temperature and humidity, motion,
                 4-way wall switch, window contact).</div>`}
        </div>
      </div>`;
  },

  _renderDeviceTable(ctx, gateway, devices) {
    const suggestions = (ctx.state.simulation || {}).interval_suggestions || [];
    return `
      <datalist id="sim-interval-list">
        ${suggestions.map((seconds) => `<option value="${escapeHtml(seconds)}"></option>`).join("")}
      </datalist>
      <div class="table-wrapper">
        <table>
          <thead><tr>
            <th>Address</th><th>Name</th><th>Kind</th><th>EEP</th><th>Sender</th>
            <th>Values it reports</th><th>Sends on its own</th><th>Last sent</th><th></th>
          </tr></thead>
          <tbody>
            ${devices.map((device) => this._renderDeviceRow(ctx, gateway, device)).join("")}
          </tbody>
        </table>
      </div>`;
  },

  _renderDeviceRow(ctx, gateway, device) {
    const key = rowKey(gateway.id, device.address);
    const note = (ctx.state.simulationNotes || {})[key];
    // internal keys (they start with '_') are no telegram values and are not shown
    const fields = (device.fields || []).filter((field) => !field.startsWith("_"));
    return `
      <tr data-sim-row="${escapeHtml(key)}">
        <td class="mono">${escapeHtml(device.address)}
          <span class="hint">${escapeHtml(device.hw_type || "")}</span></td>
        <td>${escapeHtml(device.name || "")}</td>
        <td>${escapeHtml(device.platform)}
          ${device.actuator ? `<span class="hint">controlled by HA</span>` : ""}</td>
        <td class="mono">${escapeHtml(device.eep)}</td>
        <td class="mono">${escapeHtml(device.sender_id || "-")}
          ${device.sender_eep ? `<span class="hint">${escapeHtml(device.sender_eep)}</span>` : ""}
          ${(device.taught_in || []).map((sender) => `
            <span class="sim-sender">${escapeHtml(sender.id)}
              ${sender.eep ? `<i>${escapeHtml(sender.eep)}</i>` : ""}
              ${sender.name ? `<i>${escapeHtml(sender.name)}</i>` : ""}
              <button class="sim-sender-remove" title="This sender does not control the device anymore"
                      data-sim-forget="${escapeHtml(key)}|${escapeHtml(sender.id)}">&times;</button>
            </span>`).join("")}
          ${device.actuator ? `<button class="action small" data-sim-teach="${escapeHtml(key)}"
                  title="Teach a sender into this actuator - a real wall switch, a simulated one or any other sender">
            + teach in</button>` : ""}
          ${ctx.state.simulationTeachIn === key ? this._renderTeachInForm(ctx, device, key) : ""}</td>
        <td>
          <div class="sim-fields">
            ${fields.length ? fields.map((field) => `
              <span class="sim-field">
                <label for="sim-${escapeHtml(key)}-${escapeHtml(field)}">${escapeHtml(field)}</label>
                <input type="text" data-sim-value="${escapeHtml(field)}"
                       id="sim-${escapeHtml(key)}-${escapeHtml(field)}"
                       value="${escapeHtml(this._valueOf(device, field))}" />
              </span>`).join("")
              : `<span class="sim-note">This profile carries no values.</span>`}
          </div>
          ${note ? `<div class="sim-note ${escapeHtml(note.style || "")}">${escapeHtml(note.text)}</div>` : ""}
        </td>
        <td>
          <div class="sim-repeat">
            <input type="number" min="0" data-sim-interval="${escapeHtml(key)}"
                   value="${escapeHtml(device.interval || 0)}" list="sim-interval-list"
                   title="Seconds between two telegrams (0 = only when triggered)" />
            <span class="sim-note">s</span>
            <button class="action small ${device.repeating ? "primary" : ""}"
                    data-sim-repeat="${escapeHtml(key)}"
                    title="${device.repeating
                      ? "Stops sending on its own"
                      : "Repeats the telegram with the interval on the left, like a real sensor"}">
              ${device.repeating ? "Stop" : "Start"}</button>
          </div>
          ${device.repeating
            ? `<span class="sim-note ok">sending every ${escapeHtml(device.interval)} s</span>` : ""}
        </td>
        <td>${device.last_sent ? `${escapeHtml(formatDateTime(device.last_sent))}
              <span class="hint">${escapeHtml(device.sent_count || 0)}x</span>` : "-"}</td>
        <td class="actions">
          <div class="sim-row-actions">
            <button class="action small primary" data-sim-trigger="${escapeHtml(key)}"
                    title="Sends the telegram with the values on the left">Send telegram</button>
            ${device.teach_in ? `<button class="action small" data-sim-teach-in="${escapeHtml(key)}"
                    title="${escapeHtml(device.teach_in_description || "")}"
                    >Profile teach-in${device.teach_in_kind
                      ? ` (${escapeHtml(device.teach_in_kind.toUpperCase())})` : ""}</button>` : ""}
            ${device.eltako_teach_in ? `<button class="action small" data-sim-eltako="${escapeHtml(key)}"
                    title="ELTAKO teach-in telegram of the sender profile ${escapeHtml(device.eltako_teach_in.eep)} (data ${escapeHtml(device.eltako_teach_in.payload)}), sent from ${escapeHtml(device.eltako_teach_in.address)} - the telegram the teach-in button of Home Assistant produces so that an actuator takes that sender into its memory"
                    >ELTAKO teach-in</button>` : ""}
            <button class="action small danger" data-sim-remove="${escapeHtml(key)}">Delete</button>
          </div>
        </td>
      </tr>`;
  },

  /**
   * The little form which teaches a sender into an actuator. The addresses which reported lately
   * are offered as suggestions, so a real wall switch can be picked after pressing it once
   * instead of being read off its housing.
   */
  _renderTeachInForm(ctx, device, key) {
    const simulation = ctx.state.simulation || {};
    const seen = (simulation.seen_addresses || []).filter((entry) => !entry.simulated);
    const senderEeps = simulation.sender_eeps || [];
    return `
      <div class="sim-teach" data-sim-teach-form="${escapeHtml(key)}">
        <input type="text" class="mono" data-sim-teach-address list="sim-seen-list"
               placeholder="FF-AA-BB-CC" title="Address of the sender which shall control this device" />
        <select data-sim-teach-eep title="Which profile does that sender speak?">
          <option value="">${escapeHtml(device.sender_eep || "profile of Home Assistant")}</option>
          ${senderEeps.map((eep) => `<option value="${escapeHtml(eep)}">${escapeHtml(eep)}</option>`).join("")}
        </select>
        <input type="text" data-sim-teach-name placeholder="name (optional)" />
        <button class="action small primary" data-sim-teach-save="${escapeHtml(key)}">Teach in</button>
        <button class="action small" data-sim-teach-cancel="1">Cancel</button>
        <datalist id="sim-seen-list">
          ${seen.map((entry) => `<option value="${escapeHtml(entry.address)}">
            ${escapeHtml(entry.address)}${entry.count ? ` (${escapeHtml(entry.count)} telegrams)` : ""}</option>`).join("")}
        </datalist>
        <span class="sim-note">Press the button of a real switch once - it then appears in the
          suggestions of the address field.</span>
      </div>`;
  },

  _valueOf(device, field) {
    const value = (device.state || {})[field];
    return value === null || value === undefined ? "" : value;
  },

  _renderAddDevice(ctx, simulation, gateway) {
    const editor = ctx.state.simulationNewDevice;
    if (!editor || String(editor.gatewayId) !== String(gateway.id)) return "";
    // a real gateway which does not host anything yet is not in the list above, so its form is
    // rendered by _renderRealGateways instead - see afterRender

    const platforms = simulation.platforms || [];
    const platform = platforms.find((entry) => entry.platform === editor.platform) || platforms[0];
    if (!platform) return "";

    return `
      <div class="sim-add" id="sim-new-device">
        <h4>Add a device to ${escapeHtml(gateway.name)}</h4>
        <div class="form-grid">
          <div class="field">
            <label for="sim-device-platform">Kind</label>
            <select id="sim-device-platform">
              ${platforms.map((entry) => `<option value="${escapeHtml(entry.platform)}"
                ${entry.platform === platform.platform ? "selected" : ""}>
                ${escapeHtml(entry.label)}</option>`).join("")}
            </select>
            ${platform.help ? `<span class="field-help">${escapeHtml(platform.help)}</span>` : ""}
          </div>
          <div class="field">
            <label for="sim-device-type">Device (optional template)</label>
            <select id="sim-device-type">
              <option value="">&mdash; none, choose the profile below &mdash;</option>
              ${(platform.device_types || []).map((template) => `
                <option value="${escapeHtml(template.eep)}|${escapeHtml(template.hw_type)}|${escapeHtml(template.sender_eep || "")}"
                  ${editor.hw_type === template.hw_type && editor.eep === template.eep ? "selected" : ""}>
                  ${escapeHtml(template.label)}</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <label for="sim-device-eep">Profile (EEP)</label>
            <span class="field-help">Only the profiles Home Assistant accepts for this kind are
              offered - a device the configuration would reject cannot be simulated either.</span>
            <select id="sim-device-eep">
              ${(platform.eeps || []).map((eep) => `<option value="${escapeHtml(eep.value)}"
                ${eep.value === editor.eep ? "selected" : ""}>${escapeHtml(eep.label)}</option>`).join("")}
            </select>
          </div>
          ${platform.actuator ? `
            <div class="field">
              <label for="sim-device-sender-eep">Sender profile (how Home Assistant controls it)</label>
              <select id="sim-device-sender-eep">
                ${(platform.sender_eeps || []).map((eep) => `<option value="${escapeHtml(eep)}"
                  ${eep === editor.sender_eep ? "selected" : ""}>${escapeHtml(eep)}</option>`).join("")}
              </select>
            </div>` : ""}
          <div class="field">
            <label for="sim-device-name">Name</label>
            <input type="text" id="sim-device-name" value="${escapeHtml(editor.name || "")}" />
          </div>
          ${gateway.simulated === false ? this._renderAddressField(gateway, editor) : ""}
        </div>
        <div class="form-actions">
          <button class="action primary" id="sim-device-save">Add device</button>
          <button class="action" id="sim-device-cancel">Cancel</button>
          <span class="field-help">${gateway.simulated === false
            ? "An empty address is taken from the free range of this gateway."
            : "Address and sender address are taken from the free range of this gateway - nothing has to be entered."}</span>
        </div>
      </div>`;
  },

  /**
   * A device on a *real* gateway transmits for real, so where it sits can matter - its address
   * may be entered. A wireless transceiver refuses everything outside its base id range
   * (base id .. base id + 127, an ESP3 chip enforces that), a bus gateway addresses freely.
   */
  _renderAddressField(gateway, editor) {
    const base = gateway.bus_gateway ? null : parseAddress(gateway.base_id);
    const help = gateway.bus_gateway
      ? "The local bus address of the device, e.g. 00-00-00-05."
      : base !== null
        ? `Must be inside the base id range of this gateway:
           ${formatAddress(base)} to ${formatAddress(base + 127)}.`
        : "Must be inside the base id range of this gateway.";
    return `
      <div class="field">
        <label for="sim-device-address">Address (optional)</label>
        <input type="text" id="sim-device-address" class="mono"
               placeholder="${escapeHtml(gateway.bus_gateway ? "00-00-00-05"
                 : base !== null ? formatAddress(base + 1) : "")}"
               value="${escapeHtml(editor.address || "")}" />
        <span class="field-help">${help}</span>
      </div>`;
  },

  /* --------------------------------------------------------------- behaviour */

  afterRender(ctx, root) {
    const retry = root.getElementById("sim-retry");
    if (retry) {
      retry.addEventListener("click", async () => {
        await this.load(ctx);
        ctx.requestRender();
      });
    }

    const starter = root.getElementById("sim-starter-empty");
    if (starter) starter.addEventListener("click", () => this._createStarterSet(ctx));

    // new gateway form
    const save = root.getElementById("sim-new-save");
    if (save) {
      save.addEventListener("click", () => this._addGateway(ctx, {
        device_type: root.getElementById("sim-new-type").value,
        name: root.getElementById("sim-new-name").value.trim() || null,
        with_devices: root.getElementById("sim-new-devices").checked,
      }));
      root.getElementById("sim-new-cancel").addEventListener("click", () => {
        ctx.state.simulationNewGateway = null;
        ctx.requestContentRender(true);
      });
    }

    root.querySelectorAll("button[data-sim-remove-gateway]").forEach((button) => {
      button.addEventListener("click", () => this._removeGateway(ctx, button.dataset.simRemoveGateway));
    });
    root.querySelectorAll("button[data-sim-examples]").forEach((button) => {
      button.addEventListener("click", () => this._addExamples(ctx, button.dataset.simExamples));
    });
    const resume = root.getElementById("sim-resume");
    if (resume) resume.addEventListener("click", () => this._setActive(ctx, true));

    root.querySelectorAll("button[data-sim-teach]").forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.simTeach;
        ctx.state.simulationTeachIn = ctx.state.simulationTeachIn === key ? null : key;
        ctx.requestContentRender(true);
      });
    });
    root.querySelectorAll("button[data-sim-teach-cancel]").forEach((button) => {
      button.addEventListener("click", () => {
        ctx.state.simulationTeachIn = null;
        ctx.requestContentRender(true);
      });
    });
    root.querySelectorAll("button[data-sim-teach-save]").forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.simTeachSave;
        const form = root.querySelector(`div[data-sim-teach-form="${key}"]`);
        if (!form) return;
        const address = form.querySelector("[data-sim-teach-address]").value.trim();
        if (!address) return;
        this._teachIn(ctx, key, address,
          form.querySelector("[data-sim-teach-eep]").value || null,
          form.querySelector("[data-sim-teach-name]").value.trim() || null);
      });
    });
    root.querySelectorAll("button[data-sim-forget]").forEach((button) => {
      button.addEventListener("click", () => {
        const parts = button.dataset.simForget.split("|");
        this._forgetSender(ctx, `${parts[0]}|${parts[1]}`, parts[2]);
      });
    });

    root.querySelectorAll("button[data-sim-base-id]").forEach((button) => {
      button.addEventListener("click", () => this._sendBaseId(ctx, button.dataset.simBaseId));
    });
    root.querySelectorAll("button[data-sim-add-device]").forEach((button) => {
      button.addEventListener("click", () => this._openAddDevice(ctx, button.dataset.simAddDevice));
    });

    // add-device form
    const platformSelect = root.getElementById("sim-device-platform");
    if (platformSelect) {
      // the form is opened by a button in the header of the gateway - make sure it is visible
      // and ready to type in, otherwise a click looks like nothing happened
      if (ctx.state.simulationFocusForm) {
        ctx.state.simulationFocusForm = false;
        try {
          platformSelect.scrollIntoView({ block: "nearest" });
          platformSelect.focus();
        } catch (err) {
          // an old browser without scrollIntoView options - not worth handling
        }
      }
      // the address is typed, not part of the editor state - keep it across re-renders
      const typedAddress = () => {
        const input = root.getElementById("sim-device-address");
        return input ? input.value.trim() : "";
      };
      platformSelect.addEventListener("change", () => {
        const platform = (ctx.state.simulation.platforms || [])
          .find((entry) => entry.platform === platformSelect.value);
        ctx.state.simulationNewDevice = {
          gatewayId: ctx.state.simulationNewDevice.gatewayId,
          platform: platformSelect.value,
          eep: ((platform || {}).eeps || [{}])[0].value,
          sender_eep: ((platform || {}).sender_eeps || [])[0],
          name: "",
          address: typedAddress(),
        };
        ctx.requestContentRender(true);
      });
      const templateSelect = root.getElementById("sim-device-type");
      templateSelect.addEventListener("change", () => {
        const [eep, hwType, senderEep] = templateSelect.value.split("|");
        if (!eep) return;
        const editor = ctx.state.simulationNewDevice;
        ctx.state.simulationNewDevice = {
          ...editor, eep, hw_type: hwType,
          sender_eep: senderEep || editor.sender_eep,
          name: root.getElementById("sim-device-name").value.trim() || hwType,
          address: typedAddress(),
        };
        ctx.requestContentRender(true);
      });
      root.getElementById("sim-device-save").addEventListener("click", () => {
        const senderEep = root.getElementById("sim-device-sender-eep");
        const address = this._checkAddress(ctx, typedAddress());
        if (address === undefined) return;      // refused - the form stays open to correct it
        this._addDevice(ctx, ctx.state.simulationNewDevice.gatewayId, {
          platform: platformSelect.value,
          eep: root.getElementById("sim-device-eep").value,
          sender_eep: senderEep ? senderEep.value : null,
          name: root.getElementById("sim-device-name").value.trim() || null,
          hw_type: ctx.state.simulationNewDevice.hw_type || null,
          address,
        });
      });
      root.getElementById("sim-device-cancel").addEventListener("click", () => {
        ctx.state.simulationNewDevice = null;
        ctx.requestContentRender(true);
      });
    }

    // device rows: trigger, teach-in, delete
    root.querySelectorAll("button[data-sim-trigger]").forEach((button) => {
      button.addEventListener("click", () => this._trigger(ctx, root, button.dataset.simTrigger, "state"));
    });
    root.querySelectorAll("button[data-sim-teach-in]").forEach((button) => {
      button.addEventListener("click", () => this._trigger(ctx, root, button.dataset.simTeachIn, "teach_in"));
    });
    root.querySelectorAll("button[data-sim-eltako]").forEach((button) => {
      button.addEventListener("click", () =>
        this._trigger(ctx, root, button.dataset.simEltako, "eltako_teach_in"));
    });
    root.querySelectorAll("button[data-sim-remove]").forEach((button) => {
      button.addEventListener("click", () => this._removeDevice(ctx, button.dataset.simRemove));
    });

    // start/stop sending on its own. The number next to the button is the interval; pressing
    // stop keeps it, so the same interval can be started again with one click.
    root.querySelectorAll("button[data-sim-repeat]").forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.simRepeat;
        const input = root.querySelector(`input[data-sim-interval="${key}"]`);
        const running = button.classList.contains("primary");
        const seconds = running ? 0 : Number(input && input.value ? input.value : 0);
        if (!running && !(seconds > 0)) {
          ctx.state.simulationNotes = ctx.state.simulationNotes || {};
          ctx.state.simulationNotes[key] = { style: "warn",
            text: "Enter how many seconds should pass between two telegrams." };
          ctx.requestContentRender(true);
          return;
        }
        this._setInterval(ctx, key, seconds);
      });
    });
    // typing a new interval while it is running applies it directly
    root.querySelectorAll("input[data-sim-interval]").forEach((input) => {
      input.addEventListener("change", () => {
        const key = input.dataset.simInterval;
        const button = root.querySelector(`button[data-sim-repeat="${key}"]`);
        if (button && button.classList.contains("primary")) {
          this._setInterval(ctx, key, Number(input.value || 0));
        }
      });
    });
  },

  /* ------------------------------------------------------------------ actions */

  async _call(ctx, command, payload, message) {
    ctx.state.simulationBusy = true;
    ctx.state.simulationError = null;
    ctx.state.simulationMessage = null;
    ctx.requestRender();

    const result = await ctx.api.call(command, payload);
    ctx.state.simulationBusy = false;
    if (!result) {
      ctx.state.simulationError = (ctx.api.lastError || {}).message || "The request failed.";
      ctx.api.lastError = null;
    } else if (message) {
      ctx.state.simulationMessage = typeof message === "function" ? message(result) : message;
    }
    await this.load(ctx);
    ctx.requestRender();
    return result;
  },

  _createStarterSet(ctx) {
    return this._call(ctx, WS.SIMULATOR_PRESET, { with_devices: true }, (result) => {
      const created = (result.created || []).length;
      if (!created) return "Every gateway of the starter set exists already.";
      return `Created ${created} simulated gateway(s) with ${result.device_count} device(s). ` +
        `Press "Search devices" to take them over into the configuration.`;
    });
  },

  _addGateway(ctx, values) {
    ctx.state.simulationNewGateway = null;
    return this._call(ctx, WS.SIMULATOR_GATEWAY_ADD, values,
      (result) => `Created simulated ${result.device_type} with id ${result.gateway_id}.`);
  },

  _removeGateway(ctx, gatewayId) {
    return this._call(ctx, WS.SIMULATOR_GATEWAY_REMOVE, { gateway_id: Number(gatewayId) },
      (result) => `Removed the gateway and ${result.removed_devices} simulated device(s). ` +
        `Devices which were already configured stay - remove them on the device page.`);
  },

  /** Switches the whole simulation on or off. */
  _setActive(ctx, active) {
    return this._call(ctx, WS.SIMULATOR_ACTIVATE, { active },
      (result) => result.active
        ? `The simulation is active: ${result.gateways} gateway(s) and ${result.devices} device(s) `
          + `are back in Home Assistant, ${result.repeating_count} send on their own.`
        : `The simulation is deactivated: ${result.devices} device(s) and ${result.gateways} `
          + `gateway entry/entries were taken out of Home Assistant. Nothing is lost - `
          + `${result.devices_with_interval} device(s) keep their interval.`);
  },

  /** Teaches a sender (a real switch, a simulated one, anything) into a simulated actuator. */
  _teachIn(ctx, key, senderId, senderEep, name) {
    const [gatewayId, address] = key.split("|");
    ctx.state.simulationTeachIn = null;
    return this._call(ctx, WS.SIMULATOR_TEACH_IN,
      { gateway_id: Number(gatewayId), address, sender_id: senderId,
        sender_eep: senderEep, name },
      (result) => `${(((result || {}).sender) || {}).id || senderId} controls ${address} from now on.`
        + (result && result.understood === false
            ? " The simulation does not understand that profile yet - the sender is stored, "
              + "but nothing will answer." : ""));
  },

  _forgetSender(ctx, key, senderId) {
    const [gatewayId, address] = key.split("|");
    return this._call(ctx, WS.SIMULATOR_TEACH_IN,
      { gateway_id: Number(gatewayId), address, sender_id: senderId, remove: true },
      `${senderId} does not control ${address} anymore.`);
  },

  /**
   * Lets the gateway report its base id - the info telegram a real gateway answers with when it
   * is asked after connecting. It is what the base id sensor, the address validation and the
   * stored configuration of a gateway created in the web ui are fed from.
   */
  _sendBaseId(ctx, gatewayId) {
    return this._call(ctx, WS.SIMULATOR_BASE_ID, { gateway_id: Number(gatewayId) },
      (result) => `Gateway ${gatewayId} reported its base id ${(result || {}).base_id}: `
                + `${(result || {}).telegram}`);
  },

  /** the example devices (light, dimmer, cover, heating, sensors) for one existing gateway */
  _addExamples(ctx, gatewayId) {
    ctx.state.simulationNewDevice = null;
    return this._call(ctx, WS.SIMULATOR_PRESET, { gateway_id: Number(gatewayId) },
      (result) => `Added ${result.device_count} example device(s) to gateway ${gatewayId}.`);
  },

  _openAddDevice(ctx, gatewayId) {
    const simulation = ctx.state.simulation || {};
    const platform = (simulation.platforms || [])[0] || {};
    const current = ctx.state.simulationNewDevice;
    const open = !(current && String(current.gatewayId) === String(gatewayId));

    if (open && !platform.platform) {
      // without the descriptor of the backend there is nothing to render - say so instead of
      // opening a form which stays empty
      ctx.state.simulationError = "The backend did not deliver the device profiles - reload the "
        + "page (Ctrl/Cmd + Shift + R) and, if it stays, restart Home Assistant.";
      ctx.requestContentRender(true);
      return;
    }

    ctx.state.simulationNewDevice = open ? {
      gatewayId: Number(gatewayId),
      platform: platform.platform,
      eep: ((platform.eeps || [])[0] || {}).value,
      sender_eep: (platform.sender_eeps || [])[0],
      name: "",
    } : null;
    ctx.state.simulationFocusForm = open;
    ctx.state.simulationError = null;
    ctx.requestContentRender(true);
  },

  /**
   * While a form is open the periodic refresh of the panel must not re-render the page - it
   * would throw away what was typed. The shell asks every page for this.
   */
  isEditing(ctx) {
    return !!(ctx.state.simulationNewDevice || ctx.state.simulationNewGateway
              || ctx.state.simulationTeachIn);
  },

  /** the gateway a form belongs to - a hosting one from the list, or a free real one */
  _gatewayInfo(ctx, gatewayId) {
    const simulation = ctx.state.simulation || {};
    const hosted = (simulation.gateways || [])
      .find((gateway) => String(gateway.id) === String(gatewayId));
    if (hosted) return hosted;
    const real = (simulation.real_gateways || [])
      .find((gateway) => String(gateway.id) === String(gatewayId));
    return real ? { ...real, simulated: false } : null;
  },

  /**
   * The typed address of the add-device form: null when empty (the free range of the gateway
   * is used), the normalized address when it is one this gateway can transmit, undefined when
   * it is refused - then the error is shown and the form stays open, so it can be corrected
   * instead of being typed again.
   */
  _checkAddress(ctx, typed) {
    if (!typed) return null;
    const editor = ctx.state.simulationNewDevice || {};
    const refuse = (message) => {
      ctx.state.simulationNewDevice = { ...editor, address: typed };
      ctx.state.simulationError = message;
      ctx.requestContentRender(true);
      return undefined;
    };

    const parsed = parseAddress(typed);
    if (parsed === null) {
      return refuse(`'${typed}' is not a valid EnOcean address (e.g. FF-C0-02-01).`);
    }
    const gateway = this._gatewayInfo(ctx, editor.gatewayId) || {};
    if (gateway.simulated === false && !gateway.bus_gateway) {
      const base = parseAddress(gateway.base_id);
      if (base !== null && (parsed < base || parsed > base + 127)) {
        return refuse(`${formatAddress(parsed)} cannot be transmitted by this gateway: a `
          + `wireless transceiver only sends addresses of its own base id range, `
          + `${formatAddress(base)} to ${formatAddress(base + 127)}.`);
      }
    }
    return formatAddress(parsed);
  },

  _addDevice(ctx, gatewayId, device) {
    ctx.state.simulationNewDevice = null;
    return this._call(ctx, WS.SIMULATOR_DEVICE_ADD,
      { gateway_id: Number(gatewayId), device },
      (result) => {
        const added = (result || {}).device || {};
        return `Added ${added.platform || "device"} ${added.address || ""} `
             + `(${added.eep || ""}) to gateway ${gatewayId}.`;
      });
  },

  /** Sends the telegram of this device every `seconds` seconds (0 = off). */
  _setInterval(ctx, key, seconds) {
    const [gatewayId, address] = key.split("|");
    return this._call(ctx, WS.SIMULATOR_DEVICE_UPDATE,
      { gateway_id: Number(gatewayId), address, device: { interval: seconds } },
      (result) => ((result || {}).device || {}).repeating
        ? `${address} sends its telegram every ${result.device.interval} s.`
        : `${address} does not send on its own anymore.`);
  },

  _removeDevice(ctx, key) {
    const [gatewayId, address] = key.split("|");
    return this._call(ctx, WS.SIMULATOR_DEVICE_REMOVE,
      { gateway_id: Number(gatewayId), address },
      `Removed the simulated device ${address}.`);
  },

  /**
   * Sends the telegram of one device with the values which are currently in its inputs. The
   * values are stored along the way, so the device keeps reporting them - like a real sensor
   * which repeats its measurement.
   */
  async _trigger(ctx, root, key, kind) {
    const [gatewayId, address] = key.split("|");
    const row = root.querySelector(`tr[data-sim-row="${key}"]`);
    const state = {};
    if (row) {
      row.querySelectorAll("input[data-sim-value]").forEach((input) => {
        if (input.value.trim() !== "") state[input.dataset.simValue] = input.value.trim();
      });
    }

    const result = await ctx.api.call(WS.SIMULATOR_TRIGGER, {
      gateway_id: Number(gatewayId), address, kind,
      state: kind === "state" ? state : null,
    });

    ctx.state.simulationNotes = ctx.state.simulationNotes || {};
    const what = { teach_in: "Profile announced", eltako_teach_in: "ELTAKO teach-in sent" }[kind]
      || "Telegram sent";
    ctx.state.simulationNotes[key] = result
      ? { style: "ok",
          text: `${what}: ${result.telegram}`
                + (result.teach_in_description ? ` - ${result.teach_in_description}` : "") }
      : { style: "warn", text: (ctx.api.lastError || {}).message || "Could not send the telegram." };
    if (!result) ctx.api.lastError = null;

    await this.load(ctx);
    ctx.requestContentRender(true);
  },
};
