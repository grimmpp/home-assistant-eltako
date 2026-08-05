/**
 * "My devices" - the page of the user mode (see the mode switch in eltako-panel.js).
 *
 * It shows the same devices as the expert page pages/devices_config.js, but as one card per
 * device grouped by room instead of a bus/radio hierarchy: name, state, room and the three
 * things a user actually does - switch it, rename it, remove it. Everything which needs to
 * know what an EEP, a bus position or a base id is stays in the expert mode.
 *
 * The add form is the same backend form descriptor (eltako/devices/form) as in the expert
 * mode, reduced to the fields a user has to fill in - the backend applies its defaults for
 * everything which is left out, so a device created here is identical to one created there.
 */

import { WS } from "../lib/api.js";
import { FORM_STYLES, readFields, renderFields } from "../lib/form.js";
import { escapeHtml, formatDuration, icon, matchesFilter } from "../lib/utils.js";

/** fields of the backend form which the simple add form shows - the rest keeps its default */
const SIMPLE_FIELDS = ["id", "eep", "name", "area", "sender"];

/** platforms whose devices Home Assistant controls, so they need a sender address */
const NEEDS_SENDER = ["light", "switch", "cover", "climate"];

/** entity domains without a state worth showing on a card (a button, a teach-in helper, ...) */
const STATELESS_DOMAINS = ["button", "datetime", "event", "text"];

const PLATFORM_ICONS = {
  light: ["mdi:lightbulb-outline", "☀"],
  switch: ["mdi:toggle-switch-outline", "⏻"],
  cover: ["mdi:window-shutter", "▤"],
  climate: ["mdi:thermostat", "🌡"],
  sensor: ["mdi:gauge", "◔"],
  binary_sensor: ["mdi:gesture-tap-button", "⬚"],
  button: ["mdi:radiobox-marked", "⦿"],
  select: ["mdi:format-list-bulleted", "☰"],
  datetime: ["mdi:clock-outline", "◷"],
  number: ["mdi:numeric", "№"],
};

/** friendly wording instead of the platform name of Home Assistant */
const PLATFORM_LABELS = {
  light: "Light", switch: "Switch", cover: "Cover", climate: "Heating",
  sensor: "Sensor", binary_sensor: "Button / contact", button: "Button",
  select: "Selection", datetime: "Time", number: "Value",
};

const ROOMLESS = "Without room";

export const page = {
  id: "home",
  title: "My devices",
  subtitle: "All your Eltako devices - grouped by room",
  icon: "mdi:home-outline",
  glyph: "⌂",
  modes: ["user"],
  refreshMs: 15000,

  styles: FORM_STYLES + `
    .device-groups h3 { font-size: .9rem; font-weight: 500; margin: 18px 0 8px;
                        color: var(--eltako-muted); display: flex; align-items: center; gap: 6px; }
    .device-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px; }
    .device-card { background: var(--eltako-card); border: 1px solid var(--eltako-border);
                   border-radius: var(--eltako-radius); padding: 12px 14px;
                   display: flex; flex-direction: column; gap: 8px; }
    .device-card.silent { border-style: dashed; }
    .device-card.new { border-color: var(--eltako-accent); }
    .device-card .device-head { display: flex; align-items: center; gap: 8px; }
    .device-card .device-head ha-icon, .device-card .device-head .glyph {
      --mdc-icon-size: 22px; color: var(--eltako-accent); flex: 0 0 auto; }
    .device-card .device-name { font-weight: 500; overflow-wrap: anywhere; }
    .device-card .device-kind { font-size: .72rem; color: var(--eltako-muted); }
    .device-card .device-states { display: flex; flex-wrap: wrap; gap: 5px; }
    .device-card .state-chip { font-size: .75rem; padding: 2px 9px; border-radius: 12px;
                               background: var(--eltako-tint-strong); white-space: nowrap; }
    .device-card .state-chip b { font-weight: 600; }
    .device-card .device-foot { display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
                                margin-top: auto; padding-top: 4px; }
    .device-card .device-foot .spacer { flex: 1 1 auto; }
    .device-card .device-note { font-size: .7rem; color: var(--eltako-muted); overflow-wrap: anywhere; }
    .device-card .device-note.warn { color: var(--eltako-warn); }
    /* a telegram of this device arrived: the card flashes, same signal as the expert table */
    @keyframes eltako-card-flash {
      0%   { border-color: var(--info-color, #039be5);
             background-color: color-mix(in srgb, var(--info-color, #039be5) 22%, transparent); }
      100% { border-color: var(--eltako-border); background-color: var(--eltako-card); }
    }
    .device-card.telegram-flash { animation: eltako-card-flash 1.4s ease-out; }
    .simple-hint { font-size: .78rem; color: var(--eltako-muted); margin: 10px 0 0; }
    /* result and progress of the automatic detection */
    .detect-card h3 { display: flex; align-items: center; gap: 6px; }
    .detect-card p { font-size: .85rem; }
    .detect-list { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
    .detect-list .chip { display: inline-flex; align-items: center; gap: 5px; }
    .detect-progress { height: 4px; border-radius: 3px; overflow: hidden;
                       background: var(--eltako-tint-strong); margin: 10px 0; }
    .detect-progress i { display: block; height: 100%; width: 35%; border-radius: 3px;
                         background: var(--eltako-accent); animation: eltako-detect 1.4s ease-in-out infinite; }
    @keyframes eltako-detect {
      0%   { margin-left: -35%; }
      100% { margin-left: 100%; }
    }
  `,

  async load(ctx) {
    const [form, list, pnp] = await Promise.all([
      ctx.state.deviceForm ? Promise.resolve(ctx.state.deviceForm) : ctx.api.call(WS.DEVICE_FORM),
      ctx.api.call(WS.DEVICE_LIST),
      ctx.api.call(WS.PNP_STATUS),
      ctx.loadIntegrationInfo(),
      // the addresses which are not configured yet
      ctx.loadStatistics(),
    ]);
    if (form) ctx.state.deviceForm = form;
    if (list) ctx.state.configuredDevices = list.devices || [];
    if (pnp) ctx.state.plugAndPlay = pnp;
  },

  /** number of devices which send but are not configured yet - shown in the navigation */
  badge(ctx) {
    const count = ((ctx.state.statistics || {}).unknown_devices || []).length;
    return count ? String(count) : null;
  },

  renderToolbar(ctx) {
    const running = !!(ctx.state.plugAndPlay || {}).running;
    return `
      <input id="simple-filter" type="search" placeholder="Search device or room&hellip;"
             value="${escapeHtml(ctx.state.simpleFilter || "")}" />
      <span class="spacer"></span>
      <button id="simple-detect" class="action" ${running ? "disabled" : ""}
              title="Searches for gateways, bus devices, sensors and actuators and lists what was found">
        ${icon("mdi:magnify-scan", "◎")} ${running ? "Searching&hellip;" : "Search devices"}</button>
      <button id="simple-add" class="action primary">+ Add device</button>`;
  },

  bindToolbar(ctx, root) {
    root.getElementById("simple-filter").addEventListener("input", (event) => {
      ctx.state.simpleFilter = event.target.value;
      ctx.requestContentRender(true);
    });
    root.getElementById("simple-add").addEventListener("click", () => {
      this._openAdd(ctx, {});
    });
    root.getElementById("simple-detect").addEventListener("click", () => this._startDetection(ctx));
  },

  render(ctx) {
    const gateways = (ctx.state.integrationInfo || {}).gateways || [];
    if (!gateways.length) return this._renderNoGateway(ctx);

    const all = ctx.state.configuredDevices || [];
    const devices = all.filter((device) => matchesFilter(ctx.state.simpleFilter,
      [device.name, device.address, device.external_address, device.area,
       PLATFORM_LABELS[device.platform] || device.platform]));

    return `
      ${this._renderEditor(ctx)}
      ${this._renderDetection(ctx)}
      ${this._renderSummary(ctx, all, gateways)}
      ${devices.length
        ? this._renderGroups(ctx, devices)
        : `<div class="empty">${all.length ? "No device matches your search."
            : "No devices yet. Press <b>+ Add device</b>, or let the integration find them: "
              + "press a button on a device and it appears below."}</div>`}
      ${this._renderDiscovered(ctx)}
      <div class="simple-hint">Devices which come from <code>configuration.yaml</code> can only be
        changed there. Everything else can be renamed, moved to another room and removed here.</div>`;
  },

  /* ------------------------------------------------------------------- pieces */

  _renderNoGateway(ctx) {
    return `
      ${this._renderDetection(ctx)}
      <div class="notice warn">
        <h3>No gateway yet</h3>
        <p>Your devices talk to Home Assistant through an Eltako gateway (FAM14, FGW14-USB,
          FAM-USB, a LAN gateway, ...). <b>Search devices</b> finds a gateway which is plugged in
          all by itself; the expert mode has the wizard for entering one by hand.</p>
        <p><button class="action primary" id="simple-detect-empty">${icon("mdi:magnify-scan", "◎")}
             Search devices</button>
           <button class="action" id="simple-to-expert">Switch to expert mode</button></p>
      </div>`;
  },

  /**
   * Automatic detection: one button which searches everything - serial ports and the network
   * for gateways, then the RS485 bus of every gateway for its actuators and the memories of
   * those actuators for the sensors taught into them. Devices which are identified without
   * any doubt are added, everything else is listed below.
   *
   * The run itself is the plug & play module of the backend (plug_and_play.py, the same the
   * expert overview triggers); this page only shows its progress and its result in plain words.
   */
  _renderDetection(ctx) {
    const pnp = ctx.state.plugAndPlay;
    if (!pnp) return "";
    const report = pnp.last_report || {};
    if (!pnp.running && !report.started_at) return "";

    if (pnp.running) {
      return `
        <div class="notice detect-card">
          <h3>${icon("mdi:magnify-scan", "◎")} Searching for devices&hellip;</h3>
          <div class="detect-progress"><i></i></div>
          <p>${escapeHtml(pnp.step || "Detection is running")}
            ${pnp.stage === "bus" ? " - reading the bus takes a few minutes, "
              + "your devices do not react meanwhile." : ""}</p>
        </div>`;
    }

    const gateways = report.gateways_added || [];
    const suggested = report.gateways_suggested || [];
    const devices = report.devices_added || [];
    const skipped = report.devices_skipped || [];
    const found = gateways.length + devices.length;

    return `
      <div class="notice detect-card">
        <h3>${icon("mdi:magnify-scan", "◎")} ${found
          ? `Found ${found} new ${found === 1 ? "thing" : "things"}`
          : "Nothing new found"}</h3>
        <p>Last search ${escapeHtml(formatDuration(report.started_at))} ago:
          ${gateways.length ? `<b>${gateways.length} gateway${gateways.length === 1 ? "" : "s"}</b>` : "no new gateway"},
          ${devices.length ? `<b>${devices.length} device${devices.length === 1 ? "" : "s"}</b> added` : "no new device"}.
          ${skipped.length ? `${skipped.length} device${skipped.length === 1 ? "" : "s"} could not be
            identified for sure - add ${skipped.length === 1 ? "it" : "them"} with
            <b>+ Add device</b>.` : ""}</p>
        ${skipped.length ? `<div class="detect-list">${skipped.map((entry) => `
          <span class="chip" title="${escapeHtml(entry.reason || "")}">
            <span class="mono">${escapeHtml(entry.address || "")}</span>
            ${escapeHtml(entry.device_class || "")}</span>`).join("")}</div>` : ""}
        ${gateways.length ? `<div class="detect-list">${gateways.map((gateway) => `
          <span class="chip">${icon("mdi:router-wireless", "((‧))")} ${escapeHtml(gateway.name)}
            ${escapeHtml(gateway.device_type)}</span>`).join("")}</div>` : ""}
        ${devices.length ? `<div class="detect-list">${devices.map((device) => `
          <span class="chip">${escapeHtml(device.name || device.address)}
            <span class="mono">${escapeHtml(device.address)}</span></span>`).join("")}</div>` : ""}
        ${suggested.length ? `<p class="device-note warn">${suggested.length}
          possible gateway${suggested.length === 1 ? "" : "s"} could not be identified for sure -
          confirm ${suggested.length === 1 ? "it" : "them"} in the expert mode.</p>` : ""}
        <p><button class="action" id="simple-detect-again">Search again</button></p>
      </div>`;
  },

  _renderSummary(ctx, devices, gateways) {
    const online = devices.filter((device) => {
      const activity = this._activityOf(device);
      return activity && activity.silent_since_seconds !== null
        && activity.silent_since_seconds !== undefined && activity.silent_since_seconds < 86400;
    }).length;
    const silent = devices.filter((device) => !this._activityOf(device)).length;
    const connected = gateways.filter((gateway) => gateway.connected).length;

    return `
      <div class="cards">
        <div class="card"><span class="card-value">${devices.length}</span>
          <span class="card-label">Devices</span></div>
        <div class="card ${online ? "good" : ""}"><span class="card-value">${online}</span>
          <span class="card-label">Reported today</span></div>
        <div class="card ${silent ? "warn" : ""}"><span class="card-value">${silent}</span>
          <span class="card-label">Never reported</span>
          ${silent ? `<span class="card-hint">check address and type in the expert mode</span>` : ""}</div>
        <div class="card ${connected === gateways.length ? "good" : "warn"}">
          <span class="card-value">${connected}/${gateways.length}</span>
          <span class="card-label">Gateways connected</span></div>
      </div>`;
  },

  _renderGroups(ctx, devices) {
    const groups = new Map();
    for (const device of devices) {
      const room = (device.area || "").trim() || ROOMLESS;
      if (!groups.has(room)) groups.set(room, []);
      groups.get(room).push(device);
    }
    const sorted = [...groups.entries()].sort((a, b) =>
      a[0] === ROOMLESS ? 1 : b[0] === ROOMLESS ? -1 : a[0].localeCompare(b[0]));

    return `<div class="device-groups">${sorted.map(([room, items]) => `
      <h3>${icon("mdi:map-marker-outline", "◈")} ${escapeHtml(room)}
        <span class="hint-inline">${items.length} device${items.length === 1 ? "" : "s"}</span></h3>
      <div class="device-grid">${items
        .sort((a, b) => String(a.name || a.address).localeCompare(String(b.name || b.address)))
        .map((device) => this._renderCard(ctx, device)).join("")}</div>`).join("")}</div>`;
  },

  _renderCard(ctx, device) {
    const [mdi, glyph] = PLATFORM_ICONS[device.platform] || ["mdi:chip", "▪"];
    const entities = this._entitiesOf(ctx, device);
    const activity = this._activityOf(device);

    return `
      <article class="device-card ${activity ? "" : "silent"}"
               data-address="${escapeHtml(device.address)}"
               data-external="${escapeHtml(device.external_address || "")}">
        <div class="device-head">
          ${icon(mdi, glyph)}
          <div style="min-width:0">
            <div class="device-name">${escapeHtml(device.name || device.address)}</div>
            <div class="device-kind">${escapeHtml(PLATFORM_LABELS[device.platform] || device.platform)}</div>
          </div>
        </div>
        ${entities.filter((entity) => entity.text).length
          ? `<div class="device-states">${entities.filter((entity) => entity.text).map((entity) => `
          <span class="state-chip">${escapeHtml(entity.label)} <b>${escapeHtml(entity.text)}</b></span>`)
          .join("")}</div>` : ""}
        ${this._renderControls(ctx, device, entities)}
        <div class="device-note ${activity ? "" : "warn"}">${this._renderStatusLine(device)}</div>
        <div class="device-foot">
          ${device.ha_device_id ? `<button class="action small" data-ha-device="${escapeHtml(device.ha_device_id)}"
             title="Open this device in Home Assistant">details</button>` : ""}
          <span class="spacer"></span>
          ${device.editable ? `
            <button class="action small" data-simple-edit="${this._key(device)}">rename</button>
            <button class="action small danger" data-simple-remove="${this._key(device)}">remove</button>`
            : `<span class="device-note">from configuration.yaml</span>`}
        </div>
      </article>`;
  },

  /** On/off, up/down - only for what can be operated and only if a service call is possible. */
  _renderControls(ctx, device, entities) {
    const controllable = entities.filter((entity) =>
      ["light", "switch", "cover"].includes(entity.domain));
    if (!controllable.length) return "";

    return `<div class="device-foot">${controllable.map((entity) => {
      const id = escapeHtml(entity.entityId);
      if (entity.domain === "cover") {
        return `
          <button class="action small" data-service="${id}|cover|open_cover" title="Open">&#9650;</button>
          <button class="action small" data-service="${id}|cover|stop_cover" title="Stop">&#9632;</button>
          <button class="action small" data-service="${id}|cover|close_cover" title="Close">&#9660;</button>`;
      }
      const on = entity.state === "on";
      return `<button class="action small ${on ? "primary" : ""}"
                data-service="${id}|${entity.domain}|toggle">${on ? "on" : "off"}</button>`;
    }).join("")}</div>`;
  },

  _renderStatusLine(device) {
    const activity = this._activityOf(device);
    if (!activity || !activity.last_seen) {
      return "never reported yet";
    }
    const silent = activity.silent_since_seconds;
    if (silent === null || silent === undefined) return "last reported: unknown";
    const ago = silent < 90 ? "just now"
      : silent < 3600 ? `${Math.round(silent / 60)} min ago`
      : silent < 86400 ? `${Math.round(silent / 3600)} h ago`
      : `${Math.round(silent / 86400)} days ago`;
    return `last reported ${ago}`;
  },

  /**
   * Addresses which send telegrams but are not configured yet. The backend already derived
   * the profile and the matching device models (telegram_suggestions.py), so adding one is a
   * single click here - the form opens prefilled and only the name is left to fill in.
   */
  _renderDiscovered(ctx) {
    const unknown = ((ctx.state.statistics || {}).unknown_devices || [])
      .filter((device) => (device.suggested || {}).platform);
    if (!unknown.length) return "";

    return `
      <div class="device-groups">
        <h3>${icon("mdi:magnify-scan", "◎")} Newly discovered
          <span class="hint-inline">${unknown.length} device${unknown.length === 1 ? "" : "s"}
            sent something but ${unknown.length === 1 ? "is" : "are"} not set up yet</span></h3>
        <div class="device-grid">${unknown.map((device) => {
          const best = device.suggested || {};
          const [mdi, glyph] = PLATFORM_ICONS[best.platform] || ["mdi:help-circle-outline", "?"];
          return `
            <article class="device-card new">
              <div class="device-head">
                ${icon(mdi, glyph)}
                <div style="min-width:0">
                  <div class="device-name">${escapeHtml(best.hw_type || `Device ${device.address}`)}</div>
                  <div class="device-kind mono">${escapeHtml(device.address)}</div>
                </div>
              </div>
              <div class="device-note">Looks like a
                ${escapeHtml(PLATFORM_LABELS[best.platform] || best.platform)}
                (${escapeHtml(best.eep || "")}${best.confidence ? `, ${escapeHtml(best.confidence)}` : ""}).</div>
              <div class="device-foot">
                <span class="spacer"></span>
                <button class="action small primary"
                  data-simple-adopt="${escapeHtml(device.address)}|${escapeHtml(best.eep || "")}|${escapeHtml(best.platform || "")}|${escapeHtml(best.hw_type || "")}"
                  >+ add</button>
              </div>
            </article>`;
        }).join("")}</div>
      </div>`;
  },

  /* -------------------------------------------------------------------- forms */

  /**
   * One form for both jobs: "rename" shows name and room only, "add" additionally the fields
   * of the backend descriptor which a user has to fill in (address, profile, sender).
   */
  _renderEditor(ctx) {
    const editor = ctx.state.simpleEditor;
    if (!editor) return "";

    const descriptor = ctx.state.deviceForm || { platforms: [], gateways: [] };
    const areas = descriptor.areas || [];

    if (editor.mode === "edit") {
      return `
        <div class="form-card" id="simple-editor">
          <h3>Rename ${escapeHtml(editor.values.name || editor.values.id || "")}</h3>
          <div class="form-grid" id="simple-fields">
            ${renderFields([
              { name: "name", label: "Name", type: "text", required: true,
                help: "How the device is called in Home Assistant." },
              { name: "area", label: "Room", type: "combo", options: areas,
                help: "Devices are grouped by room on this page." },
            ], editor.values)}
          </div>
          <div class="field-help" style="margin-top:10px">Address
            <code>${escapeHtml(editor.values.id || "")}</code>,
            type ${escapeHtml(PLATFORM_LABELS[editor.platform] || editor.platform)}
            ${editor.values.eep ? `, profile <code>${escapeHtml(editor.values.eep)}</code>` : ""}
            &ndash; those can be changed in the expert mode.</div>
          ${editor.error ? `<div class="form-error">${escapeHtml(editor.error)}</div>` : ""}
          <div class="form-actions">
            <button id="simple-save" class="action primary">Save</button>
            <button id="simple-cancel" class="action">Cancel</button>
          </div>
        </div>`;
    }

    const platform = descriptor.platforms.find((entry) => entry.platform === editor.platform)
      || descriptor.platforms[0];
    if (!platform) return `<div class="notice warn">The backend did not deliver any form definition.</div>`;
    const gateways = descriptor.gateways || [];
    const fields = (platform.fields || []).filter((field) => SIMPLE_FIELDS.includes(field.name));

    return `
      <div class="form-card" id="simple-editor">
        <h3>Add device</h3>
        <div class="form-grid">
          ${gateways.length > 1 ? `
            <div class="field">
              <label for="simple-gateway">Gateway</label>
              <select id="simple-gateway">
                ${gateways.map((gateway) => `<option value="${gateway.id}"
                   ${gateway.id === editor.gatewayId ? "selected" : ""}>${escapeHtml(gateway.name)}</option>`).join("")}
              </select>
              <span class="field-help">Which gateway this device talks to.</span>
            </div>` : ""}
          <div class="field">
            <label for="simple-platform">What kind of device? *</label>
            <select id="simple-platform">
              ${descriptor.platforms.map((entry) => `<option value="${escapeHtml(entry.platform)}"
                 ${entry.platform === editor.platform ? "selected" : ""}
                 >${escapeHtml(PLATFORM_LABELS[entry.platform] || entry.label)}</option>`).join("")}
            </select>
            <span class="field-help">${escapeHtml(platform.help || "")}</span>
          </div>
          ${(platform.device_types || []).length ? `
            <div class="field">
              <label for="simple-model">Model</label>
              <select id="simple-model">
                <option value="">&mdash; I don't know &mdash;</option>
                ${platform.device_types.map((type) => `<option value="${escapeHtml(type.value)}"
                   ${type.value === editor.deviceType ? "selected" : ""}>${escapeHtml(type.label)}</option>`).join("")}
              </select>
              <span class="field-help">Picking the model fills in the profile (EEP) for you.</span>
            </div>` : ""}
        </div>
        <div class="form-grid" id="simple-fields">
          ${renderFields(fields, editor.values || {})}
        </div>
        ${editor.error ? `<div class="form-error">${escapeHtml(editor.error)}</div>` : ""}
        <div class="form-actions">
          <button id="simple-save" class="action primary">Create device</button>
          <button id="simple-cancel" class="action">Cancel</button>
          <span class="field-help">Everything else keeps its default - the expert mode has all options.</span>
        </div>
      </div>`;
  },

  /* ------------------------------------------------------------------ actions */

  afterRender(ctx, root) {
    root.getElementById("simple-to-expert")?.addEventListener("click", () => {
      ctx.setMode("expert", "overview");
    });
    root.getElementById("simple-detect-empty")?.addEventListener("click", () => this._startDetection(ctx));
    root.getElementById("simple-detect-again")?.addEventListener("click", () => this._startDetection(ctx));
    this._syncDetectButton(ctx);

    // switch, dim, move: the same call the dashboard of Home Assistant makes
    root.querySelectorAll("button[data-service]").forEach((button) => {
      button.addEventListener("click", async () => {
        const [entityId, domain, service] = button.dataset.service.split("|");
        button.disabled = true;
        await this._callService(ctx, domain, service, entityId);
        button.disabled = false;
      });
    });

    root.querySelectorAll("[data-ha-device]").forEach((element) => {
      element.addEventListener("click", () => {
        history.pushState(null, "", `/config/devices/device/${element.dataset.haDevice}`);
        window.dispatchEvent(new CustomEvent("location-changed"));
      });
    });

    root.querySelectorAll("button[data-simple-edit]").forEach((button) => {
      button.addEventListener("click", () => {
        const device = this._deviceByKey(ctx, button.dataset.simpleEdit);
        if (!device) return;
        ctx.state.simpleEditor = {
          mode: "edit", platform: device.platform, gatewayId: device.gateway_id,
          values: { ...(device.config || {}) }, originalAddress: device.address, error: null,
        };
        ctx.requestContentRender(true);
        root.getElementById("simple-editor")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    });

    root.querySelectorAll("button[data-simple-remove]").forEach((button) => {
      button.addEventListener("click", async () => {
        const device = this._deviceByKey(ctx, button.dataset.simpleRemove);
        if (!device) return;
        if (!confirm(`Remove "${device.name || device.address}" from Home Assistant?\n\n`
                     + "The device itself is not changed - it can be added again at any time.")) return;
        const result = await ctx.api.call(WS.DEVICE_REMOVE, {
          gateway_id: Number(device.gateway_id), platform: device.platform, address: device.address,
        });
        if (result) {
          await this.load(ctx);
          ctx.requestRender();
        }
      });
    });

    // a discovered device: open the add form with everything the backend already knows
    root.querySelectorAll("button[data-simple-adopt]").forEach((button) => {
      button.addEventListener("click", () => {
        const [address, eep, platform, model] = button.dataset.simpleAdopt.split("|");
        this._openAdd(ctx, { address, eep, platform, name: model || `Device ${address}` });
      });
    });

    const editor = ctx.state.simpleEditor;
    if (!editor) return;

    root.getElementById("simple-cancel").addEventListener("click", () => {
      ctx.state.simpleEditor = null;
      ctx.requestContentRender(true);
    });

    root.getElementById("simple-platform")?.addEventListener("change", (event) => {
      editor.values = { ...editor.values, ...readFields(root.getElementById("simple-fields")) };
      editor.platform = event.target.value;
      editor.deviceType = null;
      editor.error = null;
      ctx.requestContentRender(true);
    });

    root.getElementById("simple-gateway")?.addEventListener("change", (event) => {
      editor.values = { ...editor.values, ...readFields(root.getElementById("simple-fields")) };
      editor.gatewayId = Number(event.target.value);
      ctx.requestContentRender(true);
    });

    root.getElementById("simple-model")?.addEventListener("change", (event) => {
      editor.values = { ...editor.values, ...readFields(root.getElementById("simple-fields")) };
      editor.deviceType = event.target.value || null;

      const descriptor = ctx.state.deviceForm || { platforms: [] };
      const platform = descriptor.platforms.find((entry) => entry.platform === editor.platform) || {};
      const template = (platform.device_types || []).find((type) => type.value === editor.deviceType);
      if (template) {
        editor.values.eep = template.eep;
        if (template.sender_eep) {
          editor.values.sender = { ...(editor.values.sender || {}), eep: template.sender_eep };
        }
        if (!editor.values.name) editor.values.name = template.hw_type;
      }
      this._fillSenderId(ctx, editor);
      editor.error = null;
      ctx.requestContentRender(true);
    });

    // the sender address depends on the device address, so it is suggested while typing
    root.querySelector("#simple-fields [data-field='id']")?.addEventListener("change", (event) => {
      if (!NEEDS_SENDER.includes(editor.platform)) return;
      editor.values = { ...editor.values, ...readFields(root.getElementById("simple-fields")) };
      editor.values.id = event.target.value.trim().toUpperCase();
      this._fillSenderId(ctx, editor);
      ctx.requestContentRender(true);
    });

    root.getElementById("simple-save").addEventListener("click", async () => {
      const entered = readFields(root.getElementById("simple-fields"));
      const device = editor.mode === "edit"
        // rename: keep the configuration as it is and only replace what the form offers
        ? { ...(editor.values || {}), ...entered }
        : entered;
      // readFields drops empty values, so an emptied room has to be removed explicitly -
      // otherwise the old one would survive from the original configuration
      if (editor.mode === "edit" && !entered.area) delete device.area;

      const payload = { gateway_id: Number(editor.gatewayId), platform: editor.platform, device };
      const result = editor.mode === "add"
        ? await ctx.api.call(WS.DEVICE_ADD, payload)
        : await ctx.api.call(WS.DEVICE_UPDATE, { ...payload, address: editor.originalAddress });

      if (result) {
        ctx.state.simpleEditor = null;
        ctx.api.lastError = null;
        await this.load(ctx);
        ctx.requestRender();
      } else {
        editor.values = device;
        editor.error = (ctx.api.lastError || {}).message || "Could not save the device.";
        ctx.api.lastError = null;
        ctx.requestContentRender(true);
      }
    });
  },

  /** A telegram arrived: let the card of that device flash. */
  onTelegram(ctx, telegram) {
    const root = ctx.root;
    if (!root) return;
    for (const address of [telegram.address, telegram.local_address].filter(Boolean)) {
      const escaped = String(address).replace(/"/g, "");
      root.querySelectorAll(`article[data-address="${escaped}"], article[data-external="${escaped}"]`)
        .forEach((card) => {
          card.classList.remove("telegram-flash");
          void card.offsetWidth;              // restart the animation on the next telegram
          card.classList.add("telegram-flash");
          clearTimeout(card._flashTimer);
          card._flashTimer = setTimeout(() => card.classList.remove("telegram-flash"), 1400);
        });
    }
  },

  /* ---------------------------------------------------------- auto detection */

  /**
   * Starts a full search: gateways (serial ports + network), the bus of every gateway and the
   * devices on it. `rescan_bus` is what makes it a *complete* search - without it only the bus
   * of a gateway which is new to Home Assistant is read.
   */
  async _startDetection(ctx) {
    if ((ctx.state.plugAndPlay || {}).running) return;
    if (!confirm("Search for gateways, actuators and sensors?\n\n"
                 + "Every serial port and the network are searched, then the bus of each gateway "
                 + "is read. This takes a few minutes, and while a bus is read the devices on it "
                 + "do not react. Nothing is changed in your devices - what is found without any "
                 + "doubt is added to Home Assistant, everything else is only listed.")) return;

    // optimistic: the page shows the progress before the answer of the backend arrives
    ctx.state.plugAndPlay = { ...(ctx.state.plugAndPlay || {}), running: true,
                              step: "Searching for gateways", stage: "ports" };
    ctx.requestContentRender(true);

    const result = await ctx.api.call(WS.PNP_RUN, { rescan_bus: true });
    if (result && result.status) {
      ctx.state.plugAndPlay = result.status;
    } else if (!result) {
      ctx.state.plugAndPlay = { ...(ctx.state.plugAndPlay || {}), running: false };
      alert((ctx.api.lastError || {}).message || "Could not start the search.");
      ctx.api.lastError = null;
    }
    ctx.requestContentRender(true);
    this._pollDetection(ctx);
  },

  /**
   * While a search runs the page needs a faster heartbeat than its normal refresh: the status
   * carries the current stage, and when it is done the new devices have to appear. The timer
   * stops itself as soon as the run is over or the user left the page.
   */
  _pollDetection(ctx) {
    clearTimeout(this._detectTimer);
    this._detectTimer = setTimeout(async () => {
      if (!ctx.root || !ctx.root.getElementById("simple-detect")) return;   // page was left
      const status = await ctx.api.call(WS.PNP_STATUS);
      if (status) ctx.state.plugAndPlay = status;
      if (status && status.running) {
        ctx.requestContentRender(true);
        this._pollDetection(ctx);
        return;
      }
      // finished: the devices which were added have to show up in the list
      await this.load(ctx);
      ctx.requestRender();
    }, 2000);
  },

  /** The toolbar is not rebuilt on a content render, so the button is updated by hand. */
  _syncDetectButton(ctx) {
    const button = ctx.root && ctx.root.getElementById("simple-detect");
    if (!button) return;
    const running = !!(ctx.state.plugAndPlay || {}).running;
    button.disabled = running;
    button.innerHTML = `${icon("mdi:magnify-scan", "◎")} ${running ? "Searching&hellip;" : "Search devices"}`;
    if (running) this._pollDetection(ctx);
  },

  /* ------------------------------------------------------------------ helpers */

  _openAdd(ctx, { address = "", eep = "", platform = "", name = "" }) {
    const gateways = (ctx.state.deviceForm || {}).gateways || [];
    const editor = {
      mode: "add",
      platform: platform || "binary_sensor",
      gatewayId: gateways.length ? gateways[0].id : null,
      values: { id: address, eep, name },
      deviceType: null,
      error: null,
    };
    this._fillSenderId(ctx, editor);
    ctx.state.simpleEditor = editor;
    ctx.requestContentRender(true);
    ctx.root?.getElementById("simple-editor")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  },

  /**
   * Actuators are controlled through a sender address of Home Assistant which has to be free.
   * The suggestion follows the same convention as the automatic detection
   * (plug_and_play.local_sender_id): bus position xx gets 00-00-B0-xx, a wireless device the
   * next free address out of the 128 ids of the gateway base id. It stays editable - the
   * backend validates it either way.
   */
  _fillSenderId(ctx, editor) {
    if (!NEEDS_SENDER.includes(editor.platform)) return;
    const address = String((editor.values || {}).id || "").toUpperCase();
    if (!address) return;
    const sender = (editor.values.sender || {});
    if (sender.id) return;                    // the user already entered one

    const used = new Set();
    for (const device of ctx.state.configuredDevices || []) {
      used.add(String(device.address).toUpperCase());
      if (device.external_address) used.add(String(device.external_address).toUpperCase());
      if ((device.sender || {}).id) used.add(String(device.sender.id).toUpperCase());
    }

    let suggestion = "";
    if (/^00-00-00-[0-9A-F]{2}$/.test(address)) {
      // the address of the bus position first, and if that one is taken the next free one
      const position = parseInt(address.slice(-2), 16);
      for (const value of [0xB000 + position, ...Array.from({ length: 255 }, (_, i) => 0xB001 + i)]) {
        const candidate = this._formatAddress(value);
        if (!used.has(candidate)) { suggestion = candidate; break; }
      }
    } else {
      const gateway = ((ctx.state.deviceForm || {}).gateways || [])
        .find((entry) => entry.id === editor.gatewayId);
      const base = this._parseAddress((gateway || {}).base_id);
      if (base !== null) {
        for (let offset = 1; offset < 128; offset++) {
          const candidate = this._formatAddress(base + offset);
          if (!used.has(candidate)) { suggestion = candidate; break; }
        }
      }
    }
    if (suggestion) editor.values.sender = { ...sender, id: suggestion };
  },

  _parseAddress(address) {
    const parts = String(address || "").split("-");
    if (parts.length !== 4) return null;
    const value = parseInt(parts.join(""), 16);
    return isNaN(value) ? null : value;
  },

  _formatAddress(value) {
    return [24, 16, 8, 0].map((shift) =>
      ((value >>> shift) & 0xFF).toString(16).toUpperCase().padStart(2, "0")).join("-");
  },

  _activityOf(device) {
    return device.activity || device.sender_activity || null;
  },

  _key(device) {
    return escapeHtml(`${device.platform}|${device.address}|${device.gateway_id}`);
  },

  _deviceByKey(ctx, key) {
    const [platform, address, gatewayId] = key.split("|");
    return (ctx.state.configuredDevices || []).find((device) => device.platform === platform
      && device.address === address && String(device.gateway_id) === gatewayId);
  },

  /**
   * The entities of a device with their current state. The entity ids come from the device
   * list of the backend (which reads them from the live entities), the telegram statistics
   * are the fallback. The state comes from hass: Home Assistant pushes it into the panel,
   * the standalone shell keeps it up to date through its own subscription.
   */
  _entitiesOf(ctx, device) {
    let entityIds = device.entity_ids || [];
    if (!entityIds.length) {
      const addresses = [device.external_address, device.address]
        .filter(Boolean).map((address) => String(address).toUpperCase());
      const entry = ((ctx.state.statistics || {}).devices || []).find((item) =>
        addresses.includes(String(item.address).toUpperCase())
        || addresses.includes(String(item.local_address || "").toUpperCase()));
      entityIds = entry ? entry.entity_ids || [] : [];
    }

    const states = (ctx.hass || {}).states || {};
    return entityIds.filter((entityId) => !STATELESS_DOMAINS.includes(entityId.split(".")[0]))
      .map((entityId) => {
      const state = states[entityId] || {};
      const unit = (state.attributes || {}).unit_of_measurement;
      const friendly = (state.attributes || {}).friendly_name || entityId;
      // "Kitchen light Temperature" -> "Temperature": the device name is already in the card
      const label = device.name && friendly.startsWith(device.name)
        ? (friendly.slice(device.name.length).trim() || "state") : friendly;
      return {
        entityId,
        domain: entityId.split(".")[0],
        state: state.state,
        label,
        // an entity which has no value yet says nothing - the status line of the card
        // already tells that the device has not reported
        text: state.state === undefined || state.state === null
          || state.state === "unknown" || state.state === "unavailable"
          ? "" : `${state.state}${unit ? ` ${unit}` : ""}`,
      };
    });
  },

  /** Service call which works in Home Assistant and in the standalone runtime alike. */
  async _callService(ctx, domain, service, entityId) {
    if (typeof (ctx.hass || {}).callService === "function") {
      try {
        await ctx.hass.callService(domain, service, { entity_id: entityId });
        return;
      } catch (err) {
        alert(`Could not switch ${entityId}: ${err && err.message ? err.message : err}`);
        return;
      }
    }
    // standalone runtime: no service registry, the entities are controlled through eltako/entities/call
    await ctx.api.call("eltako/entities/call", { entity_id: entityId, action: service, data: {} });
  },
};
