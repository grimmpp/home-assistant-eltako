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
 *
 * The page has **no periodic reload**. Switching a light used to look dead until the next
 * refresh of the whole content redrew the card (and that refresh wiped the add form while
 * it was being filled in). Instead every card registers the entities it shows at the entity
 * hub of the panel (lib/entity_hub.js) and patches its own chip and its own button when a
 * state arrives; the telegram stream keeps the "last reported" line current the same way.
 */

import { activityOf } from "../lib/activity.js";
import { WS } from "../lib/api.js";
import { DETAILS_STYLES, bindDetails, deviceDetails, openInHomeAssistant,
         renderDetails, renderGatewayDetails } from "../lib/details.js";
import { FORM_STYLES, readFields, renderFields } from "../lib/form.js";
import { assignSenderGateway, defaultGatewayChoices, describeAssignResult, gatewayOption,
         isBusGatewayType, senderGatewayOf, senderTargets } from "../lib/sender_gateway.js";
import { escapeHtml, formatDuration, icon, matchesFilter } from "../lib/utils.js";

/** fields of the backend form which the simple add form shows - the rest keeps its default */
const SIMPLE_FIELDS = ["id", "eep", "name", "area", "sender"];

/** platforms whose devices Home Assistant controls, so they need a sender address */
const NEEDS_SENDER = ["light", "switch", "cover", "climate"];

/** entity domains without a state worth showing on a card (a button, a teach-in helper, ...) */
const STATELESS_DOMAINS = ["button", "datetime", "event", "text"];

/** entity domains whose state chip is a switch as well - a click toggles them */
const SWITCHABLE_DOMAINS = ["light", "switch", "cover"];

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

/**
 * Whether the "Initial Setup" guide at the top of the page is folded out - in the browser, so
 * it survives a reload and the switch to another page. An installation which is set up folds
 * it away once and does not see it again; a fresh one gets it open, which is the default.
 */
const SETUP_OPEN_KEY = "eltako-simple-setup-open";

// TODO type check: add /** @type {import("../types.js").Page} */ once the dom casts are in
export const page = {
  id: "home",
  title: "My devices",
  subtitle: "All your ELTAKO devices - grouped by room",
  icon: "mdi:home-outline",
  glyph: "⌂",
  modes: ["user"],
  // no refreshMs on purpose - see the module comment: the cards update themselves

  styles: FORM_STYLES + DETAILS_STYLES + `
    .device-groups h3 { font-size: .9rem; font-weight: 500; margin: 18px 0 8px;
                        color: var(--eltako-muted); display: flex; align-items: center; gap: 6px; }
    .device-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px; }
    .device-card { background: var(--eltako-card); border: 1px solid var(--eltako-border);
                   border-radius: var(--eltako-radius); padding: 12px 14px;
                   display: flex; flex-direction: column; gap: 8px; }
    .device-card.silent { border-style: dashed; }
    /* a simulated device is marked on its card as well - same signal as in the expert tables */
    .device-card.simulated-card { border-left: 4px solid var(--eltako-warn); }
    .device-card.new { border-color: var(--eltako-accent); }
    .device-card .device-head { display: flex; align-items: center; gap: 8px; }
    .device-card .device-head ha-icon, .device-card .device-head .glyph {
      --mdc-icon-size: 22px; color: var(--eltako-accent); flex: 0 0 auto; }
    .device-card .device-name { font-weight: 500; overflow-wrap: anywhere; }
    .device-card .device-kind { font-size: .72rem; color: var(--eltako-muted); }
    .device-card .device-states { display: flex; flex-wrap: wrap; gap: 5px; }
    /* a chip exists for every entity and is only shown once it has a value (see
       _applyEntityState) - the display of the row has to lose against [hidden] for that */
    .device-states[hidden], .state-chip[hidden] { display: none; }
    .state-chip { font: inherit; font-size: .75rem; padding: 2px 9px; border-radius: 12px;
                  border: 1px solid transparent; color: var(--primary-text-color);
                  background: var(--eltako-tint-strong); white-space: nowrap; }
    .state-chip b { font-weight: 600; }
    /* a state which can be switched is the switch - see _renderChip */
    button.state-chip.switchable { cursor: pointer; }
    button.state-chip.switchable:hover { border-color: var(--eltako-accent); color: var(--eltako-accent); }
    button.state-chip.switchable:active { transform: scale(.97); }
    button.state-chip[disabled] { opacity: .6; cursor: progress; }
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
    .gateway-card .device-note { font-size: .72rem; }
    .bus-hint p { font-size: .85rem; margin: 6px 0 0; }
    /* The guide stands at the top of the page and folds away: an installation which is set up
       keeps one line there instead of a block it has read ten times. Collapsed it is exactly
       the summary, so <details> needs no height of its own. */
    .bus-hint > summary { display: flex; align-items: center; gap: 6px; cursor: pointer;
                          font-size: 1rem; font-weight: 500; list-style: none; }
    .bus-hint > summary::-webkit-details-marker { display: none; }   /* safari draws its own */
    .bus-hint > summary::after { content: "\\25BE"; margin-left: auto; color: var(--eltako-muted);
                                 transform: rotate(-90deg); transition: transform .15s ease; }
    .bus-hint[open] > summary::after { transform: none; }
    .bus-hint > summary:hover { color: var(--eltako-accent); }
    /* how far the setup is - the one thing worth reading while it is folded away */
    .bus-hint .setup-progress { font-size: .75rem; color: var(--eltako-muted);
                                border: 1px solid var(--eltako-border); border-radius: 999px;
                                padding: 1px 8px; font-weight: 400; }
    /* the setup instruction: numbered steps, a step which is done carries a check instead
       of its number - so the user sees where they are without reading the whole text */
    .steps { list-style: none; counter-reset: eltako-step; margin: 10px 0 0; padding: 0;
             display: flex; flex-direction: column; gap: 10px; }
    .steps li { counter-increment: eltako-step; display: flex; gap: 10px; align-items: flex-start; }
    .steps li::before { content: counter(eltako-step); flex: 0 0 auto; width: 22px; height: 22px;
                        border-radius: 50%; display: flex; align-items: center; justify-content: center;
                        font-size: .75rem; font-weight: 600; line-height: 1;
                        background: var(--eltako-tint-strong); color: var(--primary-text-color); }
    .steps li.done::before { content: "✓"; background: var(--eltako-good, #2E7D32); color: #fff; }
    .steps .step-title { font-weight: 500; }
    .steps li.done .step-title { color: var(--eltako-muted); }
    .steps .step-text { font-size: .82rem; color: var(--eltako-muted); margin: 2px 0 0; }
    /* the button (or the gateway choice) which does that step, right below its text */
    .steps .step-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
                           margin-top: 6px; }
    .steps .step-field { display: inline-flex; align-items: center; gap: 6px;
                         font-size: .78rem; color: var(--eltako-muted); }
    /* result and progress of the automatic detection */
    .detect-card h3 { display: flex; align-items: center; gap: 6px; }
    .detect-card p { font-size: .85rem; }
    .detect-list { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
    .detect-list .chip { display: inline-flex; align-items: center; gap: 5px; }
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
      <button id="simple-reset" class="action danger" data-busy-block="any" ${running ? "disabled" : ""}
              title="Removes every device created here and searches again from scratch - including a fresh read of every bus. Devices from configuration.yaml are kept.">
        ${icon("mdi:refresh", "↻")} Remove all &amp; search again</button>
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
    root.getElementById("simple-reset").addEventListener("click", () => this._resetAndDetect(ctx));
  },

  render(ctx) {
    const gateways = (ctx.state.integrationInfo || {}).gateways || [];
    if (!gateways.length) return this._renderNoGateway(ctx);

    const all = ctx.state.configuredDevices || [];
    const devices = all.filter((device) => matchesFilter(ctx.state.simpleFilter,
      [device.name, device.address, device.external_address, device.area,
       PLATFORM_LABELS[device.platform] || device.platform]));

    return `
      ${gateways.some((gateway) => ["fam14", "fgw14usb"].includes(String(gateway.type)))
        ? this._renderBusHint(ctx) : ""}
      ${this._renderEditor(ctx)}
      ${this._renderTeachIn(ctx)}
      ${this._renderDetails(ctx)}
      ${this._renderDetection(ctx)}
      ${this._renderSummary(ctx, all, gateways)}
      ${this._renderGateways(ctx, gateways)}
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

  /**
   * How to get from a fresh installation to devices which react - as four steps instead of
   * the prose it used to be. The one thing about an ELTAKO bus which cannot be guessed from
   * the ui is which gateway does what, and that decides whether the search finds anything at
   * all: reading the actuator memories and writing into them is a FAM14 feature; an FGW14-USB
   * puts telegrams on the same bus but can do neither. So step 1 is the FAM14, and everything
   * the search does - finding the devices, learning which sensors are taught into which
   * actuator, writing the sender addresses of Home Assistant - happens there.
   *
   * A step which is already done is ticked off (see the .steps styles), so the list is a
   * progress display as well and not a wall of text to read again on every visit.
   *
   * Two steps carry the button which does them, because a step which only says what to press
   * somewhere else is a step people get wrong: the search of step 2 (which also teaches the
   * senders into the actuators), and the everyday gateway of step 4 - picking one there writes
   * its addresses into every actuator and makes Home Assistant send with them
   * (lib/sender_gateway.js, backend config/sender_gateway.py).
   */
  _renderBusHint(ctx) {
    const gateways = (ctx.state.integrationInfo || {}).gateways || [];
    const hasFam14 = gateways.some((gateway) => String(gateway.type) === "fam14");
    const searched = !!((ctx.state.plugAndPlay || {}).last_report || {}).started_at;
    const hasDevices = ((ctx.state.configuredDevices || []).length > 0);
    const running = !!(ctx.state.plugAndPlay || {}).running;
    // every gateway, the ones on the bus included: switching back to the FAM14 changes the
    // senders in Home Assistant just as much as switching away from it (see the module comment
    // of lib/sender_gateway.js)
    const targets = defaultGatewayChoices(gateways);
    // is the installation already switched over? Then step 4 is done as well - every bus
    // actuator whose sender lies in the base id range of a wireless gateway says so
    const devices = ctx.state.configuredDevices || [];
    const busActuators = devices.filter((device) => (device.sender || {}).id
      && String(device.address || "").toUpperCase().startsWith("00-00-00-"));
    const onTarget = busActuators.filter((device) => {
      const owner = senderGatewayOf(gateways, device.gateway_id, (device.sender || {}).id);
      return owner && !isBusGatewayType(owner.type);
    });
    const switched = busActuators.length > 0 && onTarget.length === busActuators.length;
    // which gateway carries the installation right now - it is the preselected one, so the
    // list says what is set instead of proposing a change nobody asked for
    const owners = busActuators.map((device) =>
      senderGatewayOf(gateways, device.gateway_id, (device.sender || {}).id)).filter(Boolean);
    const current = owners.length && owners.every((owner) => owner.id === owners[0].id)
      ? owners[0] : null;

    const step = (done, title, text, controls = "") => `
      <li class="${done ? "done" : ""}">
        <div><div class="step-title">${title}</div><div class="step-text">${text}</div>
          ${controls ? `<div class="step-actions">${controls}</div>` : ""}</div>
      </li>`;

    const done = [hasFam14, searched, hasDevices, switched].filter(Boolean).length;

    return `
      <details class="notice bus-hint" id="simple-setup" ${this._setupOpen() ? "open" : ""}>
        <summary>
          ${icon("mdi:information-outline", "i")} <span class="setup-title">Initial Setup</span>
          <span class="setup-progress">${done}/4</span>
        </summary>
        <ol class="steps">
          ${step(hasFam14, "Connect the FAM14 by USB",
            "Only the FAM14 can read your bus actuators and program them &ndash; even if you "
            + "want to run a different gateway later, start with this one.")}
          ${step(searched, "Search the devices and teach them in",
            "It finds the gateway, reads every bus and adds the devices it recognises. That "
            + "takes a few minutes, and it also writes the sender addresses of Home Assistant "
            + "into the actuators &ndash; without them an actuator does not react to a command.",
            `<button class="action primary" id="step-detect" data-busy-block="any"
               ${running ? "disabled" : ""}>${icon("mdi:magnify-scan", "◎")}
               ${running ? "Searching&hellip;" : "Search devices &amp; teach in"}</button>`)}
          ${step(hasDevices, "Check the list below",
            "Everything which was found is there. A device which could not be identified for "
            + "sure you add yourself with <b>+ Add device</b>.")}
          ${step(switched, "Optional: pick the gateway for everyday use",
            "An FGW14-USB or a wireless gateway (FAM-USB, USB300, LAN gateway) is the better "
            + "permanent connection than the FAM14. Whichever gateway it is, <b>Home Assistant "
            + "has to send with its addresses</b> &ndash; that is what this does. An address "
            + "which is not in an actuator yet is written into it, which only the FAM14 can do, "
            + "so switching to a wireless gateway belongs <b>while the FAM14 is still "
            + "connected</b>; going back to the bus needs no write at all.",
            targets.length ? `
              <label class="step-field">Default gateway
                <select id="step-default-gateway">
                  ${targets.map((gateway) => gatewayOption(gateway,
                    { selected: !!current && current.id === gateway.id })).join("")}
                </select>
              </label>
              <button class="action" id="step-apply-gateway" data-busy-block="bus"
                title="Stores the addresses of this gateway as the senders of your devices - and
                       writes them into the actuators which do not carry them yet. Only that
                       write needs a connected FAM14."
                >Use for all devices</button>`
              : `<span class="step-text">No gateway with addresses to hand out &ndash; a wireless
                 gateway reports its base id as soon as it has been connected once.</span>`)}
        </ol>
      </details>`;
  },

  /** Folded out or not - see SETUP_OPEN_KEY. A fresh browser gets the guide open. */
  _setupOpen() {
    try {
      return window.localStorage.getItem(SETUP_OPEN_KEY) !== "0";
    } catch (err) {
      return true;
    }
  },

  _storeSetupOpen(open) {
    try {
      window.localStorage.setItem(SETUP_OPEN_KEY, open ? "1" : "0");
    } catch (err) {
      // storage blocked or full: the guide still folds, it just starts open again
    }
  },


  _renderNoGateway(ctx) {
    return `
      ${this._renderBusHint(ctx)}
      ${this._renderDetection(ctx)}
      <div class="notice warn">
        <h3>No gateway yet</h3>
        <p>Your devices talk to Home Assistant through an ELTAKO gateway (FAM14, FGW14-USB,
          FAM-USB, a LAN gateway, ...). <b>Search devices</b> finds a gateway which is plugged in
          all by itself; the expert mode has the wizard for entering one by hand.</p>
        <p><button class="action primary" id="simple-detect-empty" data-busy-block="any">${icon("mdi:magnify-scan", "◎")}
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
      // every bus is read in parallel and each one takes minutes - they are listed one below
      // the other, so it is visible which bus is where instead of one bar for all of them
      const scans = pnp.bus_scans || [];

      // the devices are added while the bus is being read, not at the end of the scan - so
      // the list below fills up during the run and the counter here says so
      const found = (report.devices_added || []).length;

      // No progress bar here: the activity banner of the panel stands directly above this
      // card on every page and shows exactly these bus scans with their counters. Two bars
      // for one thing, a few pixels apart, only make the page look like two things run.
      return `
        <div class="notice detect-card">
          <h3>${icon("mdi:magnify-scan", "◎")} Searching for devices&hellip;</h3>
          <p>${escapeHtml(pnp.step || "Detection is running")}
            ${pnp.stage === "bus" ? ` - reading ${scans.length > 1 ? `the ${scans.length} buses`
              : "the bus"} takes a few minutes, your devices do not react meanwhile.` : ""}</p>
          <p>${found
            ? `<b>${found} device${found === 1 ? "" : "s"}</b> found and added so far - `
              + "they are in the list below already. More appear while the search runs."
            : "Every device which is identified is added right away - you do not have to wait "
              + "for the end of the search."}</p>
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
        ${/* the search does not only write the configuration, it programs the actuators: the
              sender addresses of Home Assistant and those of every connected wireless gateway.
              Without them an actuator is listed here and does nothing when it is switched. */
          (report.senders_taught_in || []).length ? `
        <p>${icon("mdi:key-chain-variant", "⚿")}
          <b>${report.senders_taught_in.length} sender address${
            report.senders_taught_in.length === 1 ? " was" : "es were"} programmed</b> into the
          actuators &ndash; the ones Home Assistant sends with, and those of every connected
          wireless gateway, so the installation can be operated with them later.</p>` : ""}
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
        <p><button class="action" id="simple-detect-again" data-busy-block="any">Search again</button></p>
      </div>`;
  },

  _renderSummary(ctx, devices, gateways) {
    const online = devices.filter((device) => {
      const activity = activityOf(device);
      return activity && activity.silent_since_seconds !== null
        && activity.silent_since_seconds !== undefined && activity.silent_since_seconds < 86400;
    }).length;
    const silent = devices.filter((device) => !activityOf(device)).length;
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

  /**
   * The gateways, as cards like the devices.
   *
   * Every device of this page talks to Home Assistant through one of them, so a user who
   * wonders why nothing reports has to be able to see whether the box is connected at all -
   * without switching to the expert view. The card says the state in words, everything
   * technical (port, base id, protocol) is one click away in the details.
   *
   * A gateway which is configured but was never set up by Home Assistant is listed too:
   * it is in no other list of this view, and it is exactly the case which explains "my
   * devices do nothing".
   */
  _renderGateways(ctx, gateways) {
    const orphans = (ctx.state.integrationInfo || {}).gateways_not_set_up || [];
    if (!gateways.length && !orphans.length) return "";
    const devices = ctx.state.configuredDevices || [];
    const count = (gatewayId) => devices.filter((device) =>
      String(device.gateway_id) === String(gatewayId)).length;

    return `
      <div class="device-groups">
        <h3>${icon("mdi:router-wireless", "((‧))")} Gateways
          <span class="hint-inline">${gateways.length} connection${gateways.length === 1 ? "" : "s"}
            to your ELTAKO devices</span></h3>
        <div class="device-grid">
          ${gateways.map((gateway) => `
            <article class="device-card gateway-card ${gateway.connected ? "" : "silent"}
                            ${gateway.simulated ? "simulated-card" : ""}">
              <div class="device-head">
                ${icon("mdi:router-wireless", "((‧))")}
                <div style="min-width:0">
                  <div class="device-name">${escapeHtml(gateway.name)}</div>
                  <div class="device-kind">${escapeHtml(gateway.type || "Gateway")}
                    ${gateway.simulated ? `<span class="tag simulated" title="No hardware: this gateway is simulated">simulated</span>` : ""}</div>
                </div>
              </div>
              <div class="device-states">
                <span class="state-chip"><span class="chip-label">Status</span>
                  <b>${gateway.connected ? "connected" : "not connected"}</b></span>
                <span class="state-chip"><span class="chip-label">Devices</span>
                  <b>${count(gateway.id)}</b></span>
              </div>
              <div class="device-note ${gateway.connected ? "" : "warn"}">${gateway.connected
                ? escapeHtml(gateway.serial_path || "connected")
                : "No connection - check the plug, the port and the power supply."}</div>
              <div class="device-foot">
                <button class="action small" data-gateway-details="${escapeHtml(gateway.id)}"
                  title="Port, base id and everything else about this gateway">details</button>
                <span class="spacer"></span>
              </div>
            </article>`).join("")}
          ${orphans.map((gateway) => `
            <article class="device-card silent">
              <div class="device-head">
                ${icon("mdi:router-wireless-off", "((✕))")}
                <div style="min-width:0">
                  <div class="device-name">${escapeHtml(gateway.name || `Gateway ${gateway.id}`)}</div>
                  <div class="device-kind">${escapeHtml(gateway.device_type || "")}</div>
                </div>
              </div>
              <div class="device-note warn">Configured but not set up by Home Assistant - it does
                nothing. The expert mode can set it up again or remove it.</div>
              <div class="device-foot">
                <span class="spacer"></span>
                <button class="action small" data-simple-to-expert>Open expert mode</button>
              </div>
            </article>`).join("")}
        </div>
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

  /**
   * One card. Everything which can change while the page is open carries the entity it
   * belongs to (`data-entity`), so a state signal of the hub finds its chip and its button
   * without the page being rendered again - see `_applyEntityState`. A chip is rendered for
   * every entity, hidden while it has no value: an entity which reports for the first time
   * has its chip ready and only needs to be unhidden.
   */
  _renderCard(ctx, device) {
    const [mdi, glyph] = PLATFORM_ICONS[device.platform] || ["mdi:chip", "▪"];
    const entities = this._entitiesOf(ctx, device);
    const activity = activityOf(device);
    const anyState = entities.some((entity) => entity.text);

    return `
      <article class="device-card ${activity ? "" : "silent"} ${device.simulated ? "simulated-card" : ""}"
               data-address="${escapeHtml(device.address)}"
               data-external="${escapeHtml(device.external_address || "")}"
               data-device-name="${escapeHtml(device.name || "")}">
        <div class="device-head">
          ${icon(mdi, glyph)}
          <div style="min-width:0">
            <div class="device-name">${escapeHtml(device.name || device.address)}</div>
            <div class="device-kind">${escapeHtml(PLATFORM_LABELS[device.platform] || device.platform)}
              ${device.simulated ? `<span class="tag simulated" title="No hardware: this device is simulated (see the simulation page in the expert view)">simulated</span>` : ""}</div>
          </div>
        </div>
        ${entities.length
          ? `<div class="device-states" ${anyState ? "" : "hidden"}>${entities.map((entity) =>
              this._renderChip(entity)).join("")}</div>` : ""}
        ${this._renderControls(ctx, device, entities)}
        <div class="device-note device-status ${activity ? "" : "warn"}">${this._renderStatusLine(device)}</div>
        <div class="device-foot">
          <button class="action small" data-simple-details="${this._key(device)}"
             title="Address, profile, gateway and everything else about this device">details</button>
          ${this._renderCardTeachIn(ctx, device)}
          <span class="spacer"></span>
          ${device.editable ? `
            <button class="action small" data-simple-edit="${this._key(device)}">rename</button>
            <button class="action small danger" data-simple-remove="${this._key(device)}">remove</button>`
            : `<span class="device-note">from configuration.yaml</span>`}
        </div>
      </article>`;
  },

  /**
   * One state as a chip. A state which can be switched *is* the switch: clicking the chip of
   * a light, a socket or a cover toggles it. That is what a user tries first - the chip is
   * the thing which says "on", so it is the thing they press - and a chip which only looked
   * like a button was the reason switching felt broken. The explicit buttons stay: they say
   * which direction a cover takes, a chip cannot.
   */
  _renderChip(entity) {
    const id = escapeHtml(entity.entityId);
    const label = `<span class="chip-label">${escapeHtml(entity.label)}</span>
      <b>${escapeHtml(entity.text)}</b>`;
    if (!SWITCHABLE_DOMAINS.includes(entity.domain)) {
      return `<span class="state-chip" data-entity="${id}" ${entity.text ? "" : "hidden"}
        >${label}</span>`;
    }
    return `<button class="state-chip switchable" data-entity="${id}"
      data-service="${id}|${entity.domain}|toggle" ${entity.text ? "" : "hidden"}
      title="Click to switch ${escapeHtml(entity.label)}">${label}</button>`;
  },

  /**
   * The teach-in of one device - one button on its card, the rest in a popup.
   *
   * It is the answer to "this device does not react": which gateway switches it, with which
   * address, and the way to change both. That is three controls and two sentences of
   * explanation, which is a popup and not something a card can carry next to its state - the
   * card stays a card. The popup is `_renderTeachIn`.
   *
   * Only for what Home Assistant switches: a sensor reports, it is not commanded, so it has no
   * sender and nothing to teach in.
   */
  _renderCardTeachIn(ctx, device) {
    if (!this._teachInChoices(ctx, device).length) return "";
    return `<button class="action small" data-simple-teach-in="${this._key(device)}"
       title="Which gateway switches this device - and the teach-in which puts its address into the device">teach-in</button>`;
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
      // data-entity marks the button as one which shows a state: it is relabelled as soon
      // as the entity reports the new one, without the card being rendered again
      const on = entity.state === "on";
      return `<button class="action small ${on ? "primary" : ""}" data-entity="${id}"
                data-service="${id}|${entity.domain}|toggle">${on ? "on" : "off"}</button>`;
    }).join("")}</div>`;
  },

  _renderStatusLine(device) {
    const activity = activityOf(device);
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

  /* ------------------------------------------------------------------ details */

  /**
   * Everything about one device or one gateway, as a popup.
   *
   * The card shows what a user acts on - name, state, switch. Everything which answers "what
   * *is* this thing" (address, profile, gateway, sender, entities, when it last reported) is
   * here, one click away, instead of forcing a switch into the expert view. The button used
   * to jump straight into the device page of Home Assistant, which did nothing at all in the
   * standalone runtime and left the panel in the other case; that jump is now one button
   * inside this popup - offered where it exists.
   */
  _renderDetails(ctx) {
    const details = ctx.state.simpleDetails;
    if (!details) return "";

    if (details.kind === "gateway") {
      return renderGatewayDetails((ctx.state.integrationInfo || {}).gateways,
        details.key, ctx.state.configuredDevices, icon);
    }

    const device = this._deviceByKey(ctx, details.key);
    if (!device) return "";
    const parts = deviceDetails(device, {
      icon: PLATFORM_ICONS[device.platform],
      subtitle: PLATFORM_LABELS[device.platform] || device.platform,
      entities: this._entitiesOf(ctx, device),
      lastSeen: this._renderStatusLine(device).replace("last reported ", ""),
    });
    return renderDetails(parts, icon, device.editable ? `
      <button class="action" data-simple-edit="${escapeHtml(details.key)}">Rename</button>
      <button class="action danger" data-simple-remove="${escapeHtml(details.key)}">Remove</button>` : "");
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
    // No form definition means there is nothing to fill in. It still needs the cancel button:
    // without it `afterRender` would find none of the editor elements and the page would be
    // stuck showing this notice.
    if (!platform) {
      return `
        <div class="form-card" id="simple-editor">
          <div class="notice warn">The backend did not deliver any form definition. Reload the
            page - if it stays this way, the integration did not start up completely.</div>
          <div class="form-actions"><button id="simple-cancel" class="action">Close</button></div>
        </div>`;
    }
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

  /* ----------------------------------------------------------------- teach-in */

  /**
   * The teach-in of one device, as a popup: which gateway switches it and how it learns that.
   *
   * An actuator only reacts to sender addresses it knows, and a transceiver only transmits
   * addresses out of its own base id range - both halves have to agree, which is what the two
   * controls here do in one step (backend: config/sender_gateway.py):
   *
   *   * a device on the RS485 bus gets the address **written into its memory**, which only a
   *     FAM14 can do, so it has to be connected;
   *   * a wireless device **learns it from a telegram** - it is put into its learn mode by hand
   *     and the teach-in telegram goes out through the chosen gateway.
   *
   * In both cases the same address becomes the sender of this device in Home Assistant, because
   * otherwise the integration would keep transmitting the old one.
   *
   * It is a popup and not a control on the card: the current gateway, the address it hands out
   * and the sentence which says what pressing the button does are what makes this usable, and
   * none of that fits next to the state of a device.
   */
  _renderTeachIn(ctx) {
    const teach = ctx.state.simpleTeachIn;
    if (!teach) return "";
    const device = this._deviceByKey(ctx, teach.key);
    if (!device) return "";

    const gateways = (ctx.state.integrationInfo || {}).gateways || [];
    const choices = this._teachInChoices(ctx, device);
    const current = senderGatewayOf(gateways, device.gateway_id, (device.sender || {}).id);
    const chosen = this._teachInGateway(ctx, device);
    const onBus = this._isBusDevice(device);

    const parts = {
      icon: PLATFORM_ICONS[device.platform] || ["mdi:chip", "▪"],
      title: device.name || device.address,
      // the head of the popup is escaped by renderDetails, so this is plain text
      subtitle: `Teach-in - ${PLATFORM_LABELS[device.platform] || device.platform}`,
      rows: [
        ["Device address", device.address, true],
        ["Switched by", current ? current.name : "no gateway of this installation"],
        ["Sender address", (device.sender || {}).id || "not set", true],
      ],
      extra: `
        <div class="meta-section">
          <h4>Which gateway should switch it?</h4>
          <div class="field">
            <select id="teach-in-gateway">
              ${choices.map((gateway) => gatewayOption(gateway,
                { selected: !!chosen && String(gateway.id) === String(chosen.id) })).join("")}
            </select>
            <span class="field-help">${onBus
              ? `It gets an address of this gateway written into its memory - only a FAM14 can
                 write, so it has to be connected. Nothing is removed: what switched this device
                 before keeps switching it.`
              : `Put the device into its teach-in mode first (rotary switch to <b>LRN</b>, or
                 whatever its manual says), then send. A device which is not in teach-in mode
                 ignores the telegram, so it can simply be sent again.`}</span>
          </div>
        </div>`,
    };

    return renderDetails(parts, icon, `
      <button class="action primary" id="teach-in-send"
        >${onBus ? "Write into the device" : "Send teach-in"}</button>`);
  },

  /**
   * The gateways which may switch this device.
   *
   * A device on the bus can stay on it - the local senders `00-00-B0-xx` are what a FAM14 works
   * with - or be moved to a wireless gateway; a wireless device has only the gateways which
   * transmit. Empty where the choice would be a lie: a device out of `configuration.yaml` (it
   * is changed there), a sensor (nothing switches it), an installation without a gateway which
   * could take it over.
   */
  _teachInChoices(ctx, device) {
    if (!device.editable || !NEEDS_SENDER.includes(device.platform)) return [];
    if (!(device.sender || {}).eep) return [];

    const gateways = (ctx.state.integrationInfo || {}).gateways || [];
    const targets = senderTargets(gateways);
    const bus = this._isBusDevice(device)
      && gateways.find((gateway) => String(gateway.id) === String(device.gateway_id));
    return (bus ? [bus] : []).concat(targets.filter((gateway) => gateway !== bus));
  },

  /** The gateway the popup has selected: the one which was picked, else the current one. */
  _teachInGateway(ctx, device) {
    const choices = this._teachInChoices(ctx, device);
    const picked = (ctx.state.simpleTeachIn || {}).gatewayId;
    if (picked) {
      const found = choices.find((gateway) => String(gateway.id) === String(picked));
      if (found) return found;
    }
    const gateways = (ctx.state.integrationInfo || {}).gateways || [];
    const current = senderGatewayOf(gateways, device.gateway_id, (device.sender || {}).id);
    return choices.find((gateway) => current && gateway.id === current.id) || choices[0] || null;
  },

  /** An address on the RS485 bus - those are taught in by writing the device, not by a telegram. */
  _isBusDevice(device) {
    return String(device.address || "").toUpperCase().startsWith("00-00-00-");
  },

  /** The listeners of the popup - it is content, so this runs on every render. */
  _bindTeachIn(ctx, root) {
    root.getElementById("teach-in-gateway")?.addEventListener("change", (event) => {
      if (ctx.state.simpleTeachIn) ctx.state.simpleTeachIn.gatewayId = event.target.value;
    });
    root.getElementById("teach-in-send")?.addEventListener("click",
      (event) => this._sendTeachIn(ctx, event.target));
  },

  /**
   * Write the address into the device, or send it the teach-in telegram - and store it as the
   * sender of this device in Home Assistant. One backend call does both halves
   * (`eltako/devices/sender_gateway`), which is what keeps them from drifting apart.
   */
  async _sendTeachIn(ctx, button) {
    const teach = ctx.state.simpleTeachIn;
    const device = teach && this._deviceByKey(ctx, teach.key);
    if (!device) return;
    const gateway = this._teachInGateway(ctx, device);
    if (!gateway) return;

    const onBus = this._isBusDevice(device);
    if (!confirm(onBus
      ? `Let "${gateway.name}" switch "${device.name || device.address}"?\n\n`
        + "Its address is written into the device and Home Assistant sends with it afterwards. "
        + "Nothing is removed - what switched this device before keeps switching it. Only a "
        + "FAM14 can write, so it has to be connected; the bus is locked for a moment."
      : `Teach "${device.name || device.address}" in on "${gateway.name}"?\n\n`
        + "Put the device into its teach-in mode now - the teach-in telegram is sent through "
        + "that gateway and its address is stored as the sender of this device. A device which "
        + "is not in teach-in mode ignores the telegram, so it can simply be sent again.")) return;

    button.disabled = true;
    const result = await assignSenderGateway(ctx, {
      targetGatewayId: gateway.id, gatewayId: device.gateway_id, address: device.address,
    });
    button.disabled = false;

    if (!result) {
      alert((ctx.api.lastError || {}).message || "The gateway could not be changed.");
      ctx.api.lastError = null;
      return;
    }
    alert(describeAssignResult(result));
    ctx.state.simpleTeachIn = null;
    await this.load(ctx);
    ctx.requestRender();
  },

  /* ------------------------------------------------------------------ actions */

  afterRender(ctx, root) {
    this._watchEntities(ctx, root);

    root.getElementById("simple-to-expert")?.addEventListener("click", () => {
      ctx.setMode("expert", "overview");
    });
    // folding the guide away is remembered - the page redraws itself on every state change,
    // so without that it would spring open again a second later
    root.getElementById("simple-setup")?.addEventListener("toggle", (event) => {
      this._storeSetupOpen(event.target.open);
    });
    root.getElementById("simple-detect-empty")?.addEventListener("click", () => this._startDetection(ctx));
    root.getElementById("simple-detect-again")?.addEventListener("click", () => this._startDetection(ctx));
    // step 2 of the instruction does the same thing as the toolbar button
    root.getElementById("step-detect")?.addEventListener("click", () => this._startDetection(ctx));
    root.getElementById("step-apply-gateway")?.addEventListener("click",
      (event) => this._applyDefaultGateway(ctx, root, event.target));
    this._syncDetectButton(ctx);
    this._bindTeachIn(ctx, root);

    // switch, dim, move: the same call the dashboard of Home Assistant makes
    root.querySelectorAll("button[data-service]").forEach((button) => {
      button.addEventListener("click", async () => {
        const [entityId, domain, service] = button.dataset.service.split("|");
        button.disabled = true;
        await this._callService(ctx, domain, service, entityId);
        button.disabled = false;
      });
    });

    // the popup with everything about one device or one gateway
    root.querySelectorAll("button[data-simple-details]").forEach((button) => {
      button.addEventListener("click", () => {
        ctx.state.simpleTeachIn = null;             // one popup at a time
        ctx.state.simpleDetails = { kind: "device", key: button.dataset.simpleDetails };
        ctx.requestContentRender(true);
      });
    });
    root.querySelectorAll("button[data-gateway-details]").forEach((button) => {
      button.addEventListener("click", () => {
        ctx.state.simpleTeachIn = null;
        ctx.state.simpleDetails = { kind: "gateway", key: button.dataset.gatewayDetails };
        ctx.requestContentRender(true);
      });
    });
    // the teach-in popup of one device: which gateway switches it, and how it learns that
    root.querySelectorAll("button[data-simple-teach-in]").forEach((button) => {
      button.addEventListener("click", () => {
        ctx.state.simpleDetails = null;
        ctx.state.simpleTeachIn = { key: button.dataset.simpleTeachIn, gatewayId: null };
        ctx.requestContentRender(true);
      });
    });
    root.querySelectorAll("button[data-simple-to-expert]").forEach((button) => {
      button.addEventListener("click", () => ctx.setMode("expert", "overview"));
    });

    // both popups are the same markup, so closing is the same handler
    bindDetails(root, () => {
      ctx.state.simpleDetails = null;
      ctx.state.simpleTeachIn = null;
      ctx.requestContentRender(true);
    });

    root.querySelectorAll("[data-ha-device]").forEach((element) => {
      element.addEventListener("click", () => openInHomeAssistant(ctx, element.dataset.haDevice));
    });

    root.querySelectorAll("button[data-simple-edit]").forEach((button) => {
      button.addEventListener("click", () => {
        const device = this._deviceByKey(ctx, button.dataset.simpleEdit);
        if (!device) return;
        ctx.state.simpleEditor = {
          mode: "edit", platform: device.platform, gatewayId: device.gateway_id,
          values: { ...(device.config || {}) }, originalAddress: device.address, error: null,
        };
        ctx.state.simpleDetails = null;             // the form replaces the popup
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
          ctx.state.simpleDetails = null;           // it is gone - its popup has to go as well
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

    // every lookup below stays optional: the editor can render as a notice without any fields
    // (no form definition), and a listener missing is never worth losing the whole page
    root.getElementById("simple-cancel")?.addEventListener("click", () => {
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

    root.getElementById("simple-save")?.addEventListener("click", async () => {
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

  /* ------------------------------------------------------------ live updates */

  /**
   * Registers every entity of the rendered cards at the entity hub of the panel, so a state
   * change patches the one chip or the one button it belongs to. The dom is replaced on each
   * render, so the listeners of the previous one are dropped first.
   */
  _watchEntities(ctx, root) {
    if (this._unwatchEntities) {
      this._unwatchEntities();
      this._unwatchEntities = null;
    }
    if (!ctx.entities || !root) return;

    const entityIds = [...root.querySelectorAll("[data-entity]")]
      .map((element) => element.getAttribute("data-entity"));
    if (!entityIds.length) return;

    this._unwatchEntities = ctx.entities.subscribe(entityIds,
      (entityId, state) => this._applyEntityState(root, entityId, state));
  },

  /** A state arrived: update what shows it - the chip of the value, the label of a toggle. */
  _applyEntityState(root, entityId, state) {
    const selector = String(entityId).replace(/"/g, "");
    const value = (state || {}).state;
    const attributes = (state || {}).attributes || {};
    const text = this._stateText(value, attributes.unit_of_measurement);

    root.querySelectorAll(`.state-chip[data-entity="${selector}"]`).forEach((chip) => {
      const card = chip.closest("article");
      const label = chip.querySelector(".chip-label");
      if (label) {
        label.textContent = this._entityLabel(card ? card.getAttribute("data-device-name") : "",
                                              attributes.friendly_name, entityId);
      }
      const slot = chip.querySelector("b");
      if (slot) slot.textContent = text;
      chip.hidden = !text;
      // the row of chips itself disappears when the device has no value at all
      const chips = chip.parentElement;
      if (chips) chips.hidden = ![...chips.children].some((entry) => !entry.hidden);
    });

    root.querySelectorAll(`button[data-entity="${selector}"]`).forEach((button) => {
      // a chip is a button too (it switches) - but it shows the value, not an on/off label,
      // and it was filled in above
      if (button.classList.contains("state-chip")) return;
      const on = value === "on";
      button.textContent = on ? "on" : "off";
      button.classList.toggle("primary", on);
    });
  },

  /** The page is left: drop everything which would outlive its dom. */
  leave(ctx) {
    if (ctx && ctx.state) ctx.state.simpleDetails = null;   // no popup waiting on the way back
    if (this._unwatchEntities) {
      this._unwatchEntities();
      this._unwatchEntities = null;
    }
    clearTimeout(this._detectTimer);
    clearTimeout(this._discoverTimer);
    this._detectPending = false;
  },

  /**
   * A telegram arrived: let the card of that device flash and say that it just reported.
   * A telegram of an address which is not configured yet is the only case which needs data
   * the page does not have - that one reloads the statistics once, debounced.
   */
  onTelegram(ctx, telegram) {
    const root = ctx.root;
    if (!root) return;
    let matched = false;
    for (const address of [telegram.address, telegram.local_address].filter(Boolean)) {
      const escaped = String(address).replace(/"/g, "");
      root.querySelectorAll(`article[data-address="${escaped}"], article[data-external="${escaped}"]`)
        .forEach((card) => {
          matched = true;
          card.classList.remove("telegram-flash");
          void card.offsetWidth;              // restart the animation on the next telegram
          card.classList.add("telegram-flash");
          clearTimeout(card._flashTimer);
          card._flashTimer = setTimeout(() => card.classList.remove("telegram-flash"), 1400);
          this._markReported(ctx, card, address);
        });
    }
    if (!matched) this._scheduleDiscovery(ctx, telegram);
  },

  /**
   * The device just sent something, so "never reported yet" is over. The activity of the
   * device itself is updated as well - it is what the next render and the counters above
   * the list read.
   */
  _markReported(ctx, card, address) {
    card.classList.remove("silent");
    const note = card.querySelector(".device-status");
    if (note) {
      note.textContent = "last reported just now";
      note.classList.remove("warn");
    }

    const device = (ctx.state.configuredDevices || []).find((entry) =>
      entry.address === card.getAttribute("data-address"));
    if (!device) return;
    // the sender address of an actuator has its own activity - which one just reported is
    // what the address of the telegram says
    const own = String(address).toUpperCase() === String(device.address).toUpperCase();
    const key = own ? "activity" : "sender_activity";
    device[key] = { ...(device[key] || {}),
                    last_seen: new Date().toISOString(), silent_since_seconds: 0 };
  },

  /**
   * An address which has no card: either it is not configured yet (then it belongs into
   * "Newly discovered" and the statistics have to be read once) or it is a foreign device.
   * Debounced, so a talkative bus does not turn into a request per telegram.
   */
  _scheduleDiscovery(ctx, telegram) {
    if (telegram.known || ctx.state.simpleEditor) return;    // known, or a form is open
    const address = String(telegram.address || "").toUpperCase();
    if (!address) return;
    const listed = ((ctx.state.statistics || {}).unknown_devices || [])
      .some((entry) => String(entry.address || "").toUpperCase() === address);
    if (listed) return;

    clearTimeout(this._discoverTimer);
    this._discoverTimer = setTimeout(async () => {
      if (!ctx.root || !ctx.root.getElementById("simple-filter")) return;   // page was left
      if (ctx.state.simpleEditor) return;
      await ctx.loadStatistics();
      ctx.requestContentRender();
    }, 2000);
  },

  /* ---------------------------------------------------------- auto detection */

  /**
   * Starts a full search: gateways (serial ports + network), the bus of every gateway and the
   * devices on it. `rescan_bus` is what makes it a *complete* search - without it only the bus
   * of a gateway which is new to Home Assistant is read.
   */
  /** Throw away everything this page created and detect from scratch.
   *
   * The use case is a configuration which drifted: devices added with a wrong EEP, half a bus
   * adopted, a gateway which was re-cabled. Deleting them one by one is tedious, and a plain
   * search does not help - a device which already exists is skipped by the detection.
   *
   * Asks **once**, for both halves: the dialog names the number, what survives and what the
   * search costs (a bus is locked while it is read). It used to ask a second time with the
   * wording of the plain search button - a question nobody expects after having just
   * confirmed "and search again", and answering it with "cancel" left the devices deleted and
   * nothing searched. Nothing is written into any device - only the configuration of this
   * integration is reset.
   */
  async _resetAndDetect(ctx) {
    if ((ctx.state.plugAndPlay || {}).running) return;

    const all = ctx.state.configuredDevices || [];
    const removable = all.filter((device) => device.editable);
    const fromYaml = all.length - removable.length;

    if (!removable.length) {
      alert(fromYaml
        ? `There is nothing to remove - all ${fromYaml} device(s) come from configuration.yaml `
          + "and are not touched. Use \"Search devices\" to look for new ones."
        : "There are no devices yet. Use \"Search devices\" to look for them.");
      return;
    }

    if (!confirm(`Really remove all ${removable.length} device(s) and search again?\n\n`
                 + "Everything listed here is deleted first - names, areas and EEPs you "
                 + "corrected by hand are lost - and then detected from scratch.\n\n"
                 + (fromYaml ? `${fromYaml} device(s) from configuration.yaml are kept.\n` : "")
                 + "Your gateways are kept, and nothing is changed in the devices themselves.\n\n"
                 + "The search which follows reads every serial port and the bus of each "
                 + "gateway: it takes a few minutes, and while a bus is read the devices on it "
                 + "do not react.")) return;

    // how the gateways look before the removal - the wait below compares against it
    const expected = this._gatewayCounts(ctx);

    // while the search is being prepared neither button may start a second one
    this._detectPending = true;
    ctx.requestContentRender(true);
    try {
      const result = await ctx.api.call(WS.DEVICE_REMOVE_ALL, {});
      if (!result) {
        alert((ctx.api.lastError || {}).message || "Could not remove the devices.");
        ctx.api.lastError = null;
        return;
      }

      await this.load(ctx);
      ctx.requestContentRender(true);
      await this._waitForGateways(ctx, expected);
    } finally {
      this._detectPending = false;
    }
    // the question was asked above - this must not ask a second one
    await this._runDetection(ctx);
  },

  _gatewayCounts(ctx) {
    const gateways = (ctx.state.integrationInfo || {}).gateways || [];
    return { total: gateways.length,
             connected: gateways.filter((gateway) => gateway.connected).length };
  },

  /**
   * Removing the devices rewrites the options of every gateway, and Home Assistant reloads a
   * gateway whose options changed: while that runs the gateway is gone from the integration
   * info and its serial port is closed. A search started in that moment probes the port of a
   * gateway which is just coming up and finds no bus to read - which is why the reset used to
   * look as if it had searched for nothing. So the gateways are waited for first.
   *
   * The state before the removal is the target, not "all connected": a gateway which was
   * offline anyway (unplugged, wrong port) must not hold the search up. And bounded either
   * way - a gateway which never comes back must not block it forever.
   */
  async _waitForGateways(ctx, expected, seconds = 30) {
    const back = () => {
      const now = this._gatewayCounts(ctx);
      return now.total >= expected.total && now.connected >= expected.connected;
    };
    if (back()) return;

    ctx.state.plugAndPlay = { ...(ctx.state.plugAndPlay || {}), running: true, stage: "ports",
                              step: "The gateways are reloading - waiting for them to connect" };
    ctx.requestContentRender(true);

    for (let attempt = 0; attempt < seconds && !back(); attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      await ctx.loadIntegrationInfo();
    }
  },

  async _startDetection(ctx) {
    if ((ctx.state.plugAndPlay || {}).running || this._detectPending) return;
    if (!confirm("Search for gateways, actuators and sensors?\n\n"
                 + "Every serial port and the network are searched, then the bus of each gateway "
                 + "is read. This takes a few minutes, and while a bus is read the devices on it "
                 + "do not react. Nothing is changed in your devices - what is found without any "
                 + "doubt is added to Home Assistant, everything else is only listed.")) return;
    await this._runDetection(ctx);
  },

  /**
   * Step 4 of the instruction: this gateway operates the installation from now on.
   *
   * Every bus actuator gets an address of the chosen gateway written into its memory and that
   * address becomes its sender in Home Assistant - the two halves which have to agree, see
   * lib/sender_gateway.js. Only a FAM14 can write, so this is the step which has to happen
   * while it is still connected.
   */
  async _applyDefaultGateway(ctx, root, button) {
    const select = root.getElementById("step-default-gateway");
    if (!select || !select.value) return;
    const name = select.options[select.selectedIndex].textContent.trim();
    if (!confirm(`Let "${name}" switch all your devices?\n\n`
                 + "Home Assistant sends with the addresses of this gateway afterwards, and "
                 + "every bus actuator which does not carry its address yet gets it written "
                 + "into its memory. Nothing is removed - what switched a device before keeps "
                 + "switching it.\n\n"
                 + "Only a write needs the FAM14 connected and locks the bus for a moment; "
                 + "where all the addresses are already in place nothing is written.")) return;

    const label = button.innerHTML;
    button.disabled = true;
    button.textContent = "programming…";
    const result = await assignSenderGateway(ctx, { targetGatewayId: select.value });
    button.disabled = false;
    button.innerHTML = label;
    if (!result) {
      alert((ctx.api.lastError || {}).message || "The gateway could not be programmed.");
      ctx.api.lastError = null;
      return;
    }
    alert(describeAssignResult(result));
    await this.load(ctx);
    ctx.requestRender();
  },

  /** Start the run itself. Whoever calls this has asked the user already. */
  async _runDetection(ctx) {
    // optimistic: the page shows the progress before the answer of the backend arrives
    ctx.state.plugAndPlay = { ...(ctx.state.plugAndPlay || {}), running: true,
                              step: "Searching for gateways", stage: "ports" };
    this._detectPending = true;
    this._addedSeen = 0;              // how many devices of this run are in the list already
    ctx.requestContentRender(true);

    const result = await ctx.api.call(WS.PNP_RUN, { rescan_bus: true });
    this._detectPending = false;
    if (result && result.status) {
      // the backend answers before its task ran, so its status still says "not running" -
      // keeping the optimistic flag stops the progress card from blinking out until the
      // first poll (and the buttons from being clickable again meanwhile)
      ctx.state.plugAndPlay = result.started === false
        ? result.status : { ...result.status, running: true };
      if (result.started === false) {
        alert(result.reason === "already_running"
          ? "A search is already running - its result appears here when it is done."
          : "The search was not started - plug & play is switched off in the settings.");
      }
    } else if (!result) {
      ctx.state.plugAndPlay = { ...(ctx.state.plugAndPlay || {}), running: false };
      alert((ctx.api.lastError || {}).message || "Could not start the search.");
      ctx.api.lastError = null;
    }
    ctx.requestContentRender(true);
    // the banner of the panel says on every page what runs - it must not wait for its poll
    await ctx.refreshActivity?.();
    this._pollDetection(ctx);
  },

  /**
   * While a search runs the page needs a faster heartbeat than its normal refresh: the status
   * carries the current stage and the report grows while the scan runs - the detection adds
   * every device it identifies right away instead of at the end (plug_and_play.async_run), so
   * the list below has to fill up during the search and not only after it. Reloading it costs
   * a handful of requests, so that happens when the number of added devices changed, not on
   * every tick. The timer stops itself as soon as the run is over or the user left the page.
   */
  _pollDetection(ctx) {
    clearTimeout(this._detectTimer);
    this._detectTimer = setTimeout(async () => {
      // the filter input is the toolbar of this page - it is gone as soon as the page is left
      if (!ctx.root || !ctx.root.getElementById("simple-filter")) return;
      // a start which is still on its way: the backend does not know about it yet, so its
      // "not running" would drop the progress card and hand the buttons back for a moment
      if (this._detectPending) {
        this._pollDetection(ctx);
        return;
      }
      const status = await ctx.api.call(WS.PNP_STATUS);
      if (status) ctx.state.plugAndPlay = status;
      if (status && status.running) {
        const added = ((status.last_report || {}).devices_added || []).length;
        if (added !== this._addedSeen) {
          this._addedSeen = added;
          await this.load(ctx);            // the new devices belong into the list below
          ctx.requestRender();
        } else {
          ctx.requestContentRender(true);
        }
        this._pollDetection(ctx);
        return;
      }
      // finished: whatever the last pass added has to show up as well
      this._addedSeen = 0;
      await this.load(ctx);
      ctx.requestRender();
    }, 2000);
  },

  /**
   * Everything which starts a search is locked while one runs.
   *
   * The buttons in the content (step 2 of the instruction, "Search again") are rendered with
   * the state and are right by themselves; the toolbar is *not* rebuilt on a content render,
   * so its reset button is updated by hand. And "pending" - a start which was sent but not
   * confirmed by the backend yet - exists only here, so the step button is locked from here
   * as well: without it the button hands itself back for the moment between the two.
   */
  _syncDetectButton(ctx) {
    if (!ctx.root) return;
    const running = !!(ctx.state.plugAndPlay || {}).running || !!this._detectPending;
    for (const id of ["simple-reset", "step-detect", "simple-detect-empty", "simple-detect-again"]) {
      const button = ctx.root.getElementById(id);
      if (button) button.disabled = running;
    }
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
      const attributes = state.attributes || {};
      return {
        entityId,
        domain: entityId.split(".")[0],
        state: state.state,
        label: this._entityLabel(device.name, attributes.friendly_name, entityId),
        text: this._stateText(state.state, attributes.unit_of_measurement),
      };
    });
  },

  /** "Kitchen light Temperature" -> "Temperature": the device name is already on the card. */
  _entityLabel(deviceName, friendlyName, entityId) {
    const friendly = friendlyName || entityId;
    return deviceName && friendly.startsWith(deviceName)
      ? (friendly.slice(deviceName.length).trim() || "state") : friendly;
  },

  /**
   * The value of an entity as it is shown on its chip. An entity without a value says
   * nothing - the status line of the card already tells that the device has not reported,
   * so the chip stays empty (and hidden) instead of showing "unknown".
   */
  _stateText(state, unit) {
    if (state === undefined || state === null || state === "unknown" || state === "unavailable") {
      return "";
    }
    return `${state}${unit ? ` ${unit}` : ""}`;
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
