/** Overview page: gateways, entity summary and status of the telegram recording. */

import { WS } from "../lib/api.js";
import { FORM_STYLES, readFields, renderFields } from "../lib/form.js";
import { card, chip, definitionRows, escapeHtml, formatDuration, formatNumber, icon } from "../lib/utils.js";

/**
 * Plug & play section. The detection has three stages (gateway -> bus -> devices), so it is
 * drawn as that flow instead of a row of buttons: every stage is a tile with its own result,
 * the stage which is currently running is highlighted and the connectors between them animate
 * while the detection works. The switch on the right is the checkbox of the configuration.
 *
 * Only the brand tokens of lib/styles.js are used (no own greys or blues), so a custom or dark
 * Home Assistant theme keeps working.
 */
const PNP_STYLES = `
  .pnp {
    position: relative; overflow: hidden; padding: 16px;
    background: linear-gradient(135deg, var(--eltako-tint), transparent 60%), var(--eltako-card);
    border: 1px solid var(--eltako-border); border-radius: var(--eltako-radius);
  }
  .pnp.pnp-on { border-color: color-mix(in srgb, var(--eltako-accent) 45%, transparent); }

  /* ------------------------------------------------------------- head row */
  .pnp-head { display: flex; align-items: flex-start; gap: 14px; flex-wrap: wrap; }
  .pnp-head-text { flex: 1 1 260px; min-width: 0; }
  .pnp-title { display: flex; align-items: center; gap: 8px; font-size: 1rem; font-weight: 500; }
  .pnp-title ha-icon, .pnp-title .glyph { --mdc-icon-size: 22px; color: var(--eltako-accent); }
  .pnp-sub { font-size: .78rem; color: var(--eltako-muted); margin-top: 3px; max-width: 62ch; }

  /* switch: the checkbox 'plug_and_play' of the configuration as a push button */
  .pnp-switch {
    display: inline-flex; align-items: center; gap: 10px; cursor: pointer; font: inherit;
    font-size: .85rem; padding: 7px 14px 7px 10px; border-radius: 999px;
    border: 1px solid var(--eltako-border); background: var(--eltako-card);
    color: var(--primary-text-color); white-space: nowrap;
  }
  .pnp-switch:hover { border-color: var(--eltako-accent); }
  .pnp-switch[aria-checked="true"] {
    border-color: transparent; background: var(--eltako-accent);
    color: var(--text-primary-color, #fff);
  }
  .pnp-switch:disabled { opacity: .6; cursor: default; }
  .pnp-track {
    flex: 0 0 auto; width: 34px; height: 18px; border-radius: 999px; position: relative;
    background: var(--eltako-tint-strong); transition: background .18s ease;
  }
  .pnp-switch[aria-checked="true"] .pnp-track { background: color-mix(in srgb, #fff 45%, transparent); }
  .pnp-knob {
    position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%;
    background: var(--eltako-muted); transition: transform .18s ease, background .18s ease;
  }
  .pnp-switch[aria-checked="true"] .pnp-knob {
    transform: translateX(16px); background: var(--text-primary-color, #fff);
  }
  .pnp-state { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
  .pnp-state-meta { font-size: .7rem; color: var(--eltako-muted); }

  /* ---------------------------------------------------------------- flow */
  .pnp-flow { display: flex; align-items: stretch; gap: 0; margin: 16px 0 4px; flex-wrap: wrap; }
  .pnp-stage {
    flex: 1 1 170px; min-width: 150px; display: flex; flex-direction: column; gap: 4px;
    padding: 12px 14px; border-radius: 10px; border: 1px solid var(--eltako-border);
    background: var(--eltako-card);
  }
  .pnp-stage-head { display: flex; align-items: center; gap: 8px; }
  .pnp-stage-icon {
    flex: 0 0 auto; width: 30px; height: 30px; border-radius: 50%; display: grid;
    place-items: center; background: var(--eltako-tint-strong); color: var(--eltako-accent);
    --mdc-icon-size: 18px; font-size: 15px;
  }
  .pnp-stage-label { font-size: .82rem; font-weight: 500; }
  .pnp-stage-step { font-size: .65rem; color: var(--eltako-muted); letter-spacing: .06em; }
  .pnp-stage-value { font-size: 1.3rem; font-weight: 500; line-height: 1.1; }
  .pnp-stage-detail { font-size: .7rem; color: var(--eltako-muted); }

  .pnp-stage.done { border-color: color-mix(in srgb, var(--label-badge-green, #43A047) 55%, transparent); }
  .pnp-stage.done .pnp-stage-icon {
    background: color-mix(in srgb, var(--label-badge-green, #43A047) 18%, transparent);
    color: var(--label-badge-green, #43A047);
  }
  .pnp-stage.attention { border-color: color-mix(in srgb, var(--eltako-warn) 55%, transparent); }
  .pnp-stage.attention .pnp-stage-icon {
    background: color-mix(in srgb, var(--eltako-warn) 20%, transparent); color: var(--eltako-warn);
  }
  .pnp-stage.active {
    border-color: var(--eltako-accent);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--eltako-accent) 18%, transparent);
  }
  .pnp-stage.active .pnp-stage-icon { animation: pnp-pulse 1.4s ease-in-out infinite; }

  /* the arrow between two stages */
  .pnp-arrow {
    flex: 0 0 26px; display: grid; place-items: center; color: var(--eltako-border);
    position: relative;
  }
  .pnp-arrow span { font-size: 16px; line-height: 1; color: var(--eltako-muted); opacity: .7; }
  .pnp-arrow.flowing span { color: var(--eltako-accent); opacity: 1; animation: pnp-slide 1.2s linear infinite; }
  /* stacked on a phone: the tiles keep their content height (a flex-basis of 170px would
     become their *height* in a column) and the arrows turn to point downwards */
  @media (max-width: 560px) {
    .pnp-flow { flex-direction: column; gap: 2px; }
    .pnp-stage { flex: 0 0 auto; }
    .pnp-arrow { flex: 0 0 18px; transform: rotate(90deg); }
    .pnp-state { align-items: flex-start; }
    .pnp-head { gap: 8px; }
  }

  /* ------------------------------------------------------------ progress */
  .pnp-progress {
    height: 3px; border-radius: 999px; overflow: hidden; margin: 12px 0 0;
    background: var(--eltako-tint-strong);
  }
  .pnp-progress i {
    display: block; height: 100%; width: 35%; border-radius: 999px;
    background: var(--eltako-accent); animation: pnp-indeterminate 1.6s ease-in-out infinite;
  }
  /* while a bus scan reports its counters the bar becomes determinate */
  .pnp-progress.determinate i { animation: none; transition: width .8s ease; }
  .pnp-step-text { font-size: .78rem; color: var(--eltako-accent); margin-top: 8px; }

  @keyframes pnp-pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.12); }
  }
  @keyframes pnp-slide {
    0% { transform: translateX(-3px); opacity: .4; }
    50% { transform: translateX(3px); opacity: 1; }
    100% { transform: translateX(-3px); opacity: .4; }
  }
  @keyframes pnp-indeterminate {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(300%); }
  }
  @media (prefers-reduced-motion: reduce) {
    .pnp-stage.active .pnp-stage-icon, .pnp-arrow.flowing span, .pnp-progress i { animation: none; }
  }

  /* ------------------------------------------------------------- actions */
  .pnp-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 14px;
                 padding-top: 12px; border-top: 1px solid var(--eltako-border); }
  .pnp-actions .pnp-hint { font-size: .7rem; color: var(--eltako-muted); }

  /* -------------------------------------------------------------- result */
  .pnp-result { margin-top: 12px; }
  .pnp-result-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline;
                     font-size: .78rem; color: var(--eltako-muted); margin-bottom: 8px; }
  .pnp-line { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 4px 0;
              font-size: .8rem; }
  .pnp-line + .pnp-line { border-top: 1px solid var(--eltako-border); }
  .pnp-details { margin-top: 10px; font-size: .8rem; border: 1px solid var(--eltako-border);
                 border-radius: 10px; padding: 8px 12px; background: var(--eltako-tint); }
  .pnp-details summary { cursor: pointer; color: var(--eltako-accent); font-size: .8rem; }
  .pnp-details[open] summary { margin-bottom: 6px; }
  .pnp-empty { font-size: .8rem; color: var(--eltako-muted); }
`;

// TODO type check: add /** @type {import("../types.js").Page} */ once the dom casts are in
export const page = {
  id: "overview",
  title: "Overview",
  subtitle: "Gateways, devices and status of this integration",
  icon: "mdi:view-dashboard",
  glyph: "⌂",
  styles: FORM_STYLES + PNP_STYLES,
  refreshMs: 5000,

  async load(ctx) {
    const [form, pnp] = await Promise.all([
      ctx.state.gatewayForm ? Promise.resolve(ctx.state.gatewayForm) : ctx.api.call(WS.GATEWAY_FORM),
      ctx.api.call(WS.PNP_STATUS),
      ctx.loadIntegrationInfo(), ctx.loadLogInfo(), ctx.loadStatistics(),
    ]);
    if (form) ctx.state.gatewayForm = form;
    if (pnp) ctx.state.plugAndPlay = pnp;

    // a gateway module found on the devices page opens the wizard prefilled
    if (ctx.state.pendingNewGateway && !ctx.state.gatewayEditor) {
      const pending = ctx.state.pendingNewGateway;
      ctx.state.pendingNewGateway = null;
      await this._openGatewayWizard(ctx, pending);
    }
  },

  /** Open the gateway wizard with a FRESH form: the port list must reflect what is
   *  plugged in right now, not what was there when the page was loaded. */
  async _openGatewayWizard(ctx, preset = {}) {
    const form = (await ctx.api.call(WS.GATEWAY_FORM)) || ctx.state.gatewayForm || {};
    ctx.state.gatewayForm = form;
    ctx.state.gatewayEditor = { mode: "add", values: {
      device_type: preset.device_type || (form.types || [{}])[0].device_type || "fgw14usb",
      id: form.next_free_id, base_id: form.default_base_id || "00-00-00-00",
      serial_path: preset.serial_path || ((form.ports || []).find((p) => p.free) || {}).device || "",
      // a LAN gateway which was found via mDNS brings its host and port instead
      address: preset.address || "",
      port: preset.port,
      name: preset.name || "",
    }};
    ctx.state.gatewayError = null;
    ctx.state.gatewayMessage = null;
    ctx.requestContentRender(true);
  },

  /** Open the same form for an existing gateway of the web ui - its attributes are editable. */
  async _openGatewayEditor(ctx, gatewayId) {
    const form = (await ctx.api.call(WS.GATEWAY_FORM)) || ctx.state.gatewayForm || {};
    ctx.state.gatewayForm = form;
    const gateway = (form.gateways || []).find((g) => String(g.id) === String(gatewayId));
    if (!gateway) return;
    ctx.state.gatewayEditor = {
      mode: "edit", gatewayId: gateway.id,
      values: {
        device_type: gateway.device_type, id: gateway.id, name: gateway.name,
        base_id: gateway.base_id, serial_path: gateway.serial_path,
        address: gateway.address, port: gateway.port,
        auto_reconnect: gateway.auto_reconnect !== false,
        message_delay: gateway.message_delay,
      },
    };
    ctx.state.gatewayError = null;
    ctx.state.gatewayMessage = null;
    ctx.requestContentRender(true);
  },

  render(ctx) {
    const info = ctx.state.integrationInfo || {};
    const logInfo = ctx.state.logInfo || {};
    const summary = (ctx.state.statistics || {}).summary || {};
    const entities = info.entities || {};
    const gateways = info.gateways || [];
    const recording = logInfo.enabled !== false;

    return `
      <div class="cards">
        ${card("Gateways", formatNumber(gateways.length), gateways.length ? "" : "warn")}
        ${card("Devices", formatNumber(entities.device_count))}
        ${card("Entities", formatNumber(entities.entity_count))}
        ${card("Telegrams recorded", recording ? formatNumber(logInfo.total_count) : "&ndash;",
               recording ? "" : "warn", recording ? "" : "recording disabled")}
        ${card("Telegrams / min", recording ? formatNumber(logInfo.telegrams_per_minute) : "&ndash;")}
        ${card("Addresses seen", recording ? formatNumber(summary.device_count) : "&ndash;")}
        ${card("Unknown addresses", recording ? formatNumber(summary.unknown_device_count) : "&ndash;",
               summary.unknown_device_count ? "warn" : "")}
        ${card("Recording since", recording ? formatDuration(logInfo.started_at) : "&ndash;")}
      </div>

      ${this._renderRecordingNotice(ctx, logInfo)}

      <h2>Plug &amp; Play</h2>
      ${this._renderPlugAndPlay(ctx)}

      <h2>Gateways</h2>
      ${this._renderGatewayWizard(ctx)}
      <div class="toolbar">
        <button id="add-gateway" class="action primary">+ Add gateway</button>
        <span class="field-help">Creates the gateway and its Home Assistant entry directly -
          no <code>configuration.yaml</code> needed.</span>
      </div>
      ${gateways.length ? `<div class="tiles">${gateways.map((gw) => this._renderGateway(gw, summary, ctx)).join("")}</div>`
                        : `<div class="empty">No gateway is configured yet. Use <b>+ Add gateway</b>.</div>`}
      ${this._renderGatewaysNotSetUp(ctx, info.gateways_not_set_up || [])}

      <h2>Serial ports / USB scan</h2>
      ${this._renderPortScan(ctx)}

      <h2>Entities per platform</h2>
      ${Object.keys(entities.count_by_platform || {}).length
        ? `<div class="chips">${Object.entries(entities.count_by_platform)
            .map(([platform, count]) => chip(platform, count)).join("")}</div>`
        : `<div class="empty">No entities of this integration are registered yet.</div>`}

      ${(entities.areas || []).length ? `
        <h2>Areas</h2>
        <div class="chips">${entities.areas.map((area) => chip(area)).join("")}</div>` : ""}

      <h2>Home Assistant</h2>
      <div class="table-wrapper"><table>${definitionRows([
        ["Integration version", `<span class="mono">${escapeHtml(info.version || "-")}</span>`],
        ["Home Assistant version", `<span class="mono">${escapeHtml(info.home_assistant_version || "-")}</span>`],
        ["Telegram recording", recording ? `<span class="pill on">on</span>` : `<span class="pill off">off</span>`],
        ["Telegram log file", logInfo.file_path ? `<span class="mono">${escapeHtml(logInfo.file_path)}</span>`
                                                : "&ndash; not configured &ndash;"],
      ])}</table></div>
    `;
  },

  /**
   * The three stages of a detection run, in the order in which they happen. `id` matches the
   * stage the backend reports while it is running (plug_and_play.STAGES).
   */
  PNP_STAGES: [
    { id: "ports", label: "Gateway", icon: "mdi:usb-port", glyph: "⚡",
      caption: "serial ports and mDNS are searched" },
    { id: "bus", label: "Bus", icon: "mdi:lan-connect", glyph: "⇄",
      caption: "positions and memories are read" },
    { id: "devices", label: "Devices", icon: "mdi:playlist-plus", glyph: "＋",
      caption: "unambiguous devices are added" },
  ],

  /**
   * Plug & play: the checkbox of the configuration as a switch, plus the run as a flow.
   *
   * Pressing the switch stores the general setting `plug_and_play` and starts a detection run
   * right away: gateways which are plugged in are created, the bus of a new bus gateway is read
   * and every device which can be identified without any doubt is added. The three stages are
   * drawn as tiles with their result; while a run is active its stage is highlighted.
   */
  _renderPlugAndPlay(ctx) {
    const pnp = ctx.state.plugAndPlay;
    if (!pnp) return `<div class="pnp"><div class="pnp-empty">Loading&hellip;</div></div>`;

    const running = !!pnp.running;
    const report = pnp.last_report || {};
    const enabled = !!pnp.enabled;

    return `
      <div class="pnp ${enabled ? "pnp-on" : ""}">
        <div class="pnp-head">
          <div class="pnp-head-text">
            <div class="pnp-title">${icon("mdi:power-plug-outline", "⚡")} Plug &amp; Play</div>
            <div class="pnp-sub">Finds a gateway which was plugged in, reads its bus and adds every
              device which can be identified without any doubt. Everything ambiguous is only listed.</div>
          </div>
          <div class="pnp-state">
            <button id="pnp-toggle" class="pnp-switch" role="switch"
                    aria-checked="${enabled ? "true" : "false"}" ${running ? "disabled" : ""}
                    title="Same as the checkbox 'Plug &amp; play enabled' in the settings">
              <span class="pnp-track"><span class="pnp-knob"></span></span>
              <span>${enabled ? "on" : "off"}</span>
            </button>
            <span class="pnp-state-meta">${enabled
              ? (pnp.interval > 0 ? `checks ${escapeHtml(this._pnpInterval(pnp.interval))}`
                                  : "only when triggered here")
              : "detection is switched off"}${pnp.last_run
              ? ` &middot; last run ${escapeHtml(formatDuration(pnp.last_run))} ago` : ""}</span>
          </div>
        </div>

        ${this._renderPnpFlow(ctx, pnp, report)}

        ${running ? this._renderRunningBar(pnp) : ""}

        <div class="pnp-actions">
          <button id="pnp-run" class="action ${report.started_at ? "" : "primary"}" ${running ? "disabled" : ""}>
            ${running ? "Detecting&hellip;" : report.started_at ? "Detect again" : "Detect now"}</button>
          <button id="pnp-rescan" class="action" ${running ? "disabled" : ""}
                  title="Reads the bus of every bus gateway again - the bus is locked while it runs">
            Detect + re-read all buses</button>
          <span class="spacer" style="flex:1 1 auto"></span>
          <span class="pnp-hint">Nothing is written into a device - sender ids of added actuators
            still have to be taught in.</span>
        </div>

        ${this._renderPlugAndPlayReport(ctx, report)}
      </div>`;
  },

  /** The check interval of the setting (minutes) as text - the default is once a day. */
  _pnpInterval(minutes) {
    const value = Number(minutes);
    if (!value || isNaN(value)) return "only when triggered here";
    if (value === 1440) return "once a day";
    if (value % 1440 === 0) return `every ${value / 1440} days`;
    if (value === 60) return "hourly";
    if (value % 60 === 0) return `every ${value / 60} hours`;
    return `every ${value} min`;
  },

  /** The three stages as tiles, connected by arrows which animate while a run is active. */
  /**
   * The bar under the stage flow while a run is active. Indeterminate by default; as soon
   * as a bus scan reports its counters (pnp.bus_scans, filled once a second by the backend)
   * it becomes a real progress bar - with several buses in parallel it shows their average.
   */
  _renderRunningBar(pnp) {
    const scans = pnp.bus_scans || [];
    const percent = scans.length
      ? Math.round(scans.reduce((sum, scan) => sum + (scan.percent || 0), 0) / scans.length)
      : null;
    return `
      <div class="pnp-progress${percent !== null ? " determinate" : ""}">
        <i${percent !== null ? ` style="width:${Math.max(percent, 2)}%"` : ""}></i></div>
      <div class="pnp-step-text">${escapeHtml(pnp.step || "Detection is running")}&hellip;
        ${percent !== null ? `<b>${percent}%</b>` : ""}
        <span class="pnp-hint">${pnp.stage === "bus"
          ? "the bus is locked meanwhile" : "this page updates itself"}</span>
      </div>`;
  },

  _renderPnpFlow(ctx, pnp, report) {
    const stages = this.PNP_STAGES.map((stage, index) => ({
      ...stage, index, ...this._pnpStageResult(stage.id, pnp, report),
    }));

    return `
      <div class="pnp-flow">
        ${stages.map((stage, index) => `
          ${index ? `<div class="pnp-arrow ${pnp.running && stage.state === "active" ? "flowing" : ""}">
            <span>&#10132;</span></div>` : ""}
          <div class="pnp-stage ${stage.state}">
            <div class="pnp-stage-head">
              <span class="pnp-stage-icon">${icon(stage.icon, stage.glyph)}</span>
              <span>
                <span class="pnp-stage-step">STEP ${stage.index + 1}</span>
                <div class="pnp-stage-label">${escapeHtml(stage.label)}</div>
              </span>
            </div>
            <div class="pnp-stage-value">${stage.value}</div>
            <div class="pnp-stage-detail">${stage.detail || escapeHtml(stage.caption)}</div>
          </div>`).join("")}
      </div>`;
  },

  /**
   * Value, detail line and state of one stage. The state decides the colour:
   * active (running now), attention (something needs a decision), done, idle.
   *
   * While a run is active the backend publishes its report already, so a stage which is
   * behind the active one shows its result immediately, and one which is still ahead stays
   * empty instead of showing the numbers of the previous run.
   */
  _pnpStageResult(stageId, pnp, report) {
    const index = this.PNP_STAGES.findIndex((stage) => stage.id === stageId);
    const activeIndex = pnp.running ? this.PNP_STAGES.findIndex((stage) => stage.id === pnp.stage) : -1;
    const active = pnp.running && index === activeIndex;
    const pending = pnp.running && activeIndex >= 0 && index > activeIndex;
    const ran = !!report.started_at && !active && !pending;
    const state = (attention) => active ? "active" : !ran ? "idle"
      : attention ? "attention" : "done";
    const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

    if (stageId === "ports") {
      const added = (report.gateways_added || []).length;
      const suggested = (report.gateways_suggested || []).length;
      const probed = report.ports_probed || 0;
      const announced = report.mdns_found || 0;
      return {
        state: state(suggested > 0),
        value: ran ? (added ? `+${formatNumber(added)}` : formatNumber(probed))
                   : `<span class="pnp-empty">&ndash;</span>`,
        detail: !ran ? "" : [
          added ? `<b>${plural(added, "gateway")} created</b>`
                : `${plural(probed, "port")}${announced ? " + mDNS" : ""} searched`,
          suggested ? `${suggested} to confirm` : "",
        ].filter(Boolean).join(" &middot; "),
      };
    }

    if (stageId === "bus") {
      const buses = report.buses_read || [];
      const unfinished = buses.filter((bus) => !bus.finished).length;
      const positions = buses.reduce((sum, bus) => sum + (bus.positions || 0), 0);
      return {
        state: state(unfinished > 0),
        value: ran ? formatNumber(buses.length) : `<span class="pnp-empty">&ndash;</span>`,
        detail: !ran ? "" : buses.length
          ? `${plural(buses.length, "bus")} read, ${plural(positions, "position")}`
            + (unfinished ? ` &middot; ${unfinished} did not finish` : "")
          : "no bus had to be read",
      };
    }

    const added = (report.devices_added || []).length;
    const skipped = (report.devices_skipped || []).length;
    return {
      state: state(skipped > 0),
      value: ran ? (added ? `+${formatNumber(added)}` : "0") : `<span class="pnp-empty">&ndash;</span>`,
      detail: !ran ? "" : [
        added ? `<b>${plural(added, "device")} added</b>` : "nothing new",
        skipped ? `${skipped} need${skipped === 1 ? "s" : ""} a decision` : "",
      ].filter(Boolean).join(" &middot; "),
    };
  },

  /**
   * Whether one of the collapsible result blocks is open. The page refreshes every few
   * seconds, which rebuilds the dom - without remembering it, a block the user opened (or
   * closed) would snap back on the next refresh.
   */
  _pnpOpen(ctx, key, defaultOpen = false) {
    const open = ctx.state.pnpOpen || (ctx.state.pnpOpen = {});
    return key in open ? open[key] : defaultOpen;
  },

  /** Details of the last run: new gateways, added devices, what stays manual, warnings. */
  _renderPlugAndPlayReport(ctx, report) {
    if (!report || !report.started_at) {
      return `<div class="pnp-result"><div class="pnp-empty">No detection has run yet.</div></div>`;
    }

    const gateways = report.gateways_added || [];
    const devices = report.devices_added || [];
    const suggested = report.gateways_suggested || [];
    const skipped = report.devices_skipped || [];
    const warnings = report.warnings || [];

    return `
      <div class="pnp-result">
        ${gateways.length ? `
          <div class="pnp-result-head">${gateways.length === 1 ? "New gateway" : "New gateways"}</div>
          ${gateways.map((gw) => `<div class="pnp-line">
            <span class="tag source-ui">id ${escapeHtml(gw.id)}</span>
            <b>${escapeHtml(gw.name)}</b>
            <span class="mono">${escapeHtml(gw.device_type)}</span>
            <span class="mono">${escapeHtml(gw.serial_path)}</span>
            ${gw.config_entry_created ? `<span class="pill on">set up</span>`
                                      : `<span class="pill warn">entry not created</span>`}
          </div>`).join("")}` : ""}

        ${suggested.length ? `
          <div class="notice warn" style="margin-top:12px">
            <h3>${suggested.length} candidate(s) need your confirmation</h3>
            ${suggested.map((candidate) => `<div class="pnp-line">
              <span class="mono">${escapeHtml(candidate.connection === "lan"
                ? `${candidate.address || ""}${candidate.port ? `:${candidate.port}` : ""}`
                : candidate.serial_path)}</span>
              <span class="hint">${escapeHtml(candidate.hostname || candidate.port_name || "")}</span>
              <span class="hint">${escapeHtml(candidate.reason || "")}</span>
              <button class="action small primary"
                      data-add-suggested="${escapeHtml(candidate.device_type)}|${escapeHtml(candidate.serial_path || "")}|${escapeHtml(candidate.address || "")}|${escapeHtml(candidate.port || "")}"
                      >+ add as ${escapeHtml(candidate.hw_type)}</button></div>`).join("")}
          </div>` : ""}

        ${devices.length ? `
          <details class="pnp-details" data-pnp-open="devices" ${this._pnpOpen(ctx, "devices", true) ? "open" : ""}>
            <summary>${devices.length} device(s) added &ndash; editable on the Devices page</summary>
            <div class="table-wrapper"><table>
              <thead><tr><th>Address</th><th>Name</th><th>Platform</th><th>EEP</th>
                <th>Gateway</th><th>Identified by</th></tr></thead>
              <tbody>${devices.map((device) => `
                <tr><td class="mono">${escapeHtml(device.address)}</td>
                  <td>${escapeHtml(device.name || "")}</td>
                  <td>${escapeHtml(device.platform)}</td>
                  <td class="mono">${escapeHtml(device.eep || "")}</td>
                  <td>${escapeHtml(device.gateway_id)}</td>
                  <td><span class="tag role">${escapeHtml(String(device.source || "").replace(/_/g, " "))}</span></td>
                </tr>`).join("")}</tbody></table></div>
            <div class="footnote">They behave like devices created in this web ui: their attributes can
              be changed and they can be removed again on the <b>Devices</b> page. The sender ids of
              added actuators still have to be taught in ("check &amp; teach in HA senders").</div>
          </details>` : ""}

        ${skipped.length ? `
          <details class="pnp-details" data-pnp-open="skipped" ${this._pnpOpen(ctx, "skipped") ? "open" : ""}>
            <summary>${skipped.length} device(s) need a decision &ndash; not added automatically</summary>
            ${skipped.map((entry) => `<div class="pnp-line">
              <span class="mono">${escapeHtml(entry.address || "")}</span>
              ${entry.device_class ? `<span class="chip">${escapeHtml(entry.device_class)}</span>` : ""}
              <span class="hint">${escapeHtml(entry.reason || "")}</span></div>`).join("")}
            <div class="footnote">Take them over on the <b>Devices</b> page - the candidates and the
              detected EEPs are listed there for every address.</div>
          </details>` : ""}

        ${warnings.length ? `
          <details class="pnp-details" data-pnp-open="warnings" ${this._pnpOpen(ctx, "warnings") ? "open" : ""}>
            <summary>${warnings.length} warning(s)</summary>
            ${warnings.map((warning) => `<div class="pnp-line">${escapeHtml(warning)}</div>`).join("")}
          </details>` : ""}
      </div>`;
  },

  /** Navigate to the device page of home assistant (canonical panel navigation). */
  _openHaDevice(deviceId) {
    const path = `/config/devices/device/${deviceId}`;
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed"));
  },

  /**
   * Gateways which are configured here but which Home Assistant never set up.
   *
   * A gateway needs both halves: this configuration and a Home Assistant entry. Deleting the
   * entry alone (on the integration page) used to leave the configuration behind - invisible,
   * because the list above shows the *running* gateways, and therefore impossible to delete.
   * Newly deleted entries take their gateway with them (async_remove_gateway_of_entry), so
   * this section only ever shows what an older version left behind. Both ways out are offered.
   */
  _renderGatewaysNotSetUp(ctx, orphans) {
    if (!orphans.length) return "";

    return `
      <div class="notice warn" style="margin-top:14px">
        <b>${orphans.length} gateway${orphans.length === 1 ? " is" : "s are"} configured but not
        set up.</b> They have no Home Assistant entry, so they are not connected and no device
        of theirs works - but they still occupy their id and their serial port. Set them up
        again, or remove them if they are left overs.
      </div>
      <div class="tiles">
        ${orphans.map((gateway) => `
          <div class="tile">
            <div class="tile-head">
              ${icon("mdi:alert-outline", "!")}
              <span class="tile-title">${escapeHtml(gateway.name || `Gateway ${gateway.id}`)}</span>
              <span class="spacer" style="flex:1 1 auto"></span>
              <span class="pill off">not set up</span>
            </div>
            <table>${definitionRows([
              ["Gateway id", `<span class="mono">${escapeHtml(String(gateway.id))}</span>`],
              ["Type", escapeHtml(gateway.device_type || "-")],
              ["Base id", `<span class="mono">${escapeHtml(gateway.base_id || "-")}</span>`],
              ["Connection", `<span class="mono">${escapeHtml(gateway.serial_path || "-")}</span>`],
            ])}</table>
            <div style="margin-top:10px; display:flex; gap:6px; flex-wrap:wrap">
              <button class="action small primary" data-repair-gateway="${escapeHtml(String(gateway.id))}"
                      title="Creates the missing Home Assistant entry so the gateway is set up">set up</button>
              <button class="action small danger"
                      data-remove-gateway="${escapeHtml(String(gateway.id))}">remove gateway</button>
            </div>
          </div>`).join("")}
      </div>`;
  },

  /** Wizard for a new gateway: type, connection, id, name, base id. */
  _renderGatewayWizard(ctx) {
    const editor = ctx.state.gatewayEditor;
    if (!editor) {
      return ctx.state.gatewayMessage
        ? `<div class="notice"><b>${escapeHtml(ctx.state.gatewayMessage)}</b></div>` : "";
    }

    const form = ctx.state.gatewayForm || { types: [], ports: [], next_free_id: 0 };
    const type = (form.types || []).find((t) => t.device_type === editor.values.device_type)
      || (form.types || [])[0] || {};
    const isLan = !!type.is_lan;
    const isEdit = editor.mode === "edit";
    const freePorts = (form.ports || []).filter((port) => port.free);

    /** @type {import("../types.js").FormField[]} */
    const fields = [
      { name: "device_type", label: "Gateway type", type: "select", required: true,
        options: (form.types || []).map((t) => t.device_type),
        help: type.device_type ? `${type.protocol}${type.baud_rate ? `, ${type.baud_rate} baud` : ""}` +
              `${type.is_bus_gateway ? ", bus gateway (RS485)" : type.is_transceiver ? ", wireless transceiver" : ""}` : "" },
      isLan
        ? { name: "address", label: "Host name or IP address", type: "text", required: true,
            help: "e.g. 192.168.1.50 or gateway.local" }
        : { name: "serial_path", label: "Serial port", type: "select", required: true,
            // in edit mode the port of this gateway is not "free" - it must stay selectable
            options: [...new Set([...(form.ports || []).map((port) => port.device),
                                  editor.values.serial_path].filter(Boolean))],
            help: freePorts.length
              ? `Free ports: ${freePorts.map((p) => p.device).join(", ")}. Use the USB scan below for details.`
              : "All detected ports are already in use by a gateway." },
      { name: "id", label: "Gateway id", type: "number", required: true, min: 0, max: 255,
        help: isEdit
          ? "The id is part of every entity id of this gateway and cannot be changed - "
            + "remove the gateway and add it again to renumber it."
          : "Unique number of this gateway inside the integration. It is part of the entity ids." },
      { name: "name", label: "Name", type: "text", required: false, help: "Free text, e.g. 'FAM14 cellar'." },
      { name: "base_id", label: "Base id", type: "address", required: false, help: form.hint || "" },
    ];
    if (isLan) {
      fields.push({ name: "port", label: "Port", type: "number", required: false, min: 1, max: 65535 });
    }
    if (isEdit) {
      fields.push(
        { name: "auto_reconnect", label: "Auto reconnect", type: "boolean", required: false,
          help: "Reconnects automatically when the connection is lost." },
        { name: "message_delay", label: "Message delay (s)", type: "number", required: false,
          help: "Pause between two telegrams sent to this gateway. Default 0.01 s." });
    }

    return `
      <div class="form-card" id="gateway-editor">
        <h3>${isEdit ? `Edit gateway ${escapeHtml(editor.values.name || editor.gatewayId)}` : "Add gateway"}</h3>
        <div class="form-grid">${renderFields(fields, editor.values || {})}</div>
        ${ctx.state.gatewayError ? `<div class="form-error">${escapeHtml(ctx.state.gatewayError)}</div>` : ""}
        <div class="form-actions">
          <button id="gateway-save" class="action primary">${isEdit ? "Save gateway" : "Create gateway"}</button>
          <button id="gateway-cancel" class="action">Cancel</button>
          <span class="field-help">The values are validated with the same schema as the yaml.
            ${isEdit ? "The gateway is reconnected after saving." : ""}</span>
        </div>
      </div>`;
  },

  /** Passive scan for serial ports which could host a gateway. */
  _renderPortScan(ctx) {
    const scan = ctx.state.portScan;
    const button = `<button id="scan-ports" class="action ${scan ? "" : "primary"}"
        ${ctx.state.portScanRunning ? "disabled" : ""}>
        ${ctx.state.portScanRunning ? "Scanning&hellip;" : scan ? "Scan again" : "Scan USB ports"}</button>`;

    if (!scan) {
      return `<div class="empty">${button}
        <span class="field-help" style="margin-left:10px">Looks for serial ports and shows which
        stick is behind them, which port is already used and which <code>device_type</code> fits.
        Nothing is opened or written - safe to run while the gateways are connected.</span></div>`;
    }

    const rows = (scan.ports || []).map((port) => `
      <tr class="${port.free ? "" : ""}">
        <td class="mono">${escapeHtml(port.device)}
          ${port.interface ? `<span class="hint">interface ${escapeHtml(port.interface)}</span>` : ""}</td>
        <td>${escapeHtml(port.name || "-")}</td>
        <td>${port.used_by
            ? `<span class="tag source-ui">gateway ${escapeHtml(port.used_by.id)}</span>
               <span class="hint">${escapeHtml(port.used_by.name || "")}${port.used_by.connected === false ? " (not connected)" : ""}</span>`
            : `<span class="tag">free</span>`}</td>
        <td class="mono">${(port.suggested_device_types || []).map((type) => escapeHtml(type)).join(", ") || "-"}</td>
        <td>${port.by_id ? `<span class="mono" style="white-space:normal">${escapeHtml(port.by_id)}</span>` : "-"}</td>
      </tr>
      ${port.hint ? `<tr><td colspan="5" class="hint" style="padding-top:0">${escapeHtml(port.hint)}</td></tr>` : ""}`).join("");

    return `
      <div class="toolbar">${button}
        <span class="field-help">${(scan.ports || []).length} port(s),
          ${(scan.ports || []).filter((p) => p.free).length} free</span></div>
      ${(scan.gateways_without_port || []).length ? `
        <div class="notice warn">
          <h3>${scan.gateways_without_port.length} configured gateway(s) without a port</h3>
          ${scan.gateways_without_port.map((gw) => `<p><b>${escapeHtml(gw.name || gw.id)}</b> expects
            <span class="mono">${escapeHtml(gw.serial_path)}</span> - the device does not exist right now.
            Plug the stick in and restart the Home Assistant container (docker creates the device nodes
            at container start), or correct the path.</p>`).join("")}
        </div>` : ""}
      ${(scan.ports || []).length ? `
        <div class="table-wrapper"><table>
          <thead><tr><th>Device</th><th>USB descriptor</th><th>Used by</th>
            <th>Suggested device_type</th><th>Stable path (by-id)</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
        <div class="footnote">Use the stable <code>by-id</code> path in your configuration if the
          <code>/dev/ttyUSB*</code> numbering changes between reboots. A stick with two interfaces
          (if00/if01) usually carries the telegrams on only one of them.</div>`
        : `<div class="empty">No serial port found.</div>`}`;
  },

  _gatewaySource(ctx, gateway) {
    const known = ((ctx || {}).state || {}).gatewayForm;
    const entry = ((known || {}).gateways || []).find((g) => String(g.id) === String(gateway.id));
    return entry ? (entry.source === "ui" ? "web ui" : "configuration.yaml") : "configuration.yaml";
  },

  afterRender(ctx, root) {
    const addGateway = root.getElementById("add-gateway");
    if (addGateway) {
      addGateway.addEventListener("click", () => this._openGatewayWizard(ctx));
    }

    const cancel = root.getElementById("gateway-cancel");
    if (cancel) {
      cancel.addEventListener("click", () => {
        ctx.state.gatewayEditor = null;
        ctx.requestContentRender(true);
      });
    }

    const editorRoot = root.getElementById("gateway-editor");
    if (editorRoot) {
      // switching the type changes which connection field is needed
      const typeSelect = editorRoot.querySelector('[data-field="device_type"]');
      if (typeSelect) {
        typeSelect.addEventListener("change", () => {
          ctx.state.gatewayEditor.values = readFields(editorRoot);
          ctx.requestContentRender(true);
        });
      }
      root.getElementById("gateway-save").addEventListener("click", async () => {
        const values = readFields(editorRoot);
        const editor = ctx.state.gatewayEditor;
        const isEdit = editor.mode === "edit";
        const result = isEdit
          ? await ctx.api.call(WS.GATEWAY_UPDATE, { gateway_id: editor.gatewayId, gateway: values })
          : await ctx.api.call(WS.GATEWAY_ADD, { gateway: values });
        if (result) {
          ctx.state.gatewayEditor = null;
          ctx.state.gatewayError = null;
          ctx.state.gatewayMessage = isEdit
            ? "Gateway saved. It reconnects with the new settings within a few seconds."
            : result.config_entry_created
              ? "Gateway created and set up. Its entities appear within a few seconds."
              : `Gateway stored, but Home Assistant did not create the entry (${result.flow_result || result.reason}).`;
          ctx.state.gatewayForm = await ctx.api.call(WS.GATEWAY_FORM);
          await ctx.loadIntegrationInfo();
        } else {
          ctx.state.gatewayEditor.values = values;
          ctx.state.gatewayError = (ctx.api.lastError || {}).message
            || `Could not ${isEdit ? "save" : "create"} the gateway.`;
          ctx.api.lastError = null;
        }
        ctx.requestContentRender(true);
      });
    }

    root.querySelectorAll("button[data-edit-gateway]").forEach((button) => {
      button.addEventListener("click", () => this._openGatewayEditor(ctx, button.dataset.editGateway));
    });

    root.querySelectorAll("button[data-remove-gateway]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.dataset.removeGateway;
        if (!confirm(`Remove gateway ${id} and its Home Assistant entry?`)) return;
        const result = await ctx.api.call(WS.GATEWAY_REMOVE, { gateway_id: Number(id) });
        if (result) {
          ctx.state.gatewayMessage = `Gateway ${id} removed.`;
          ctx.state.gatewayForm = await ctx.api.call(WS.GATEWAY_FORM);
          await ctx.loadIntegrationInfo();
          ctx.requestContentRender(true);
        }
      });
    });

    // a gateway which is configured but was never set up: set it up again or remove it
    root.querySelectorAll("button[data-repair-gateway]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.dataset.repairGateway;
        button.disabled = true;
        const result = await ctx.api.call(WS.GATEWAY_REPAIR, { gateway_id: Number(id) });
        ctx.state.gatewayMessage = result && result.repaired
          ? `Gateway ${id} was set up again.`
          : `Gateway ${id} could not be set up (${(result || {}).reason || "unknown reason"}).`;
        await ctx.loadIntegrationInfo();
        ctx.requestContentRender(true);
      });
    });

    root.querySelectorAll("[data-ha-device]").forEach((element) => {
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        this._openHaDevice(element.dataset.haDevice);
      });
    });

    this._bindPlugAndPlay(ctx, root);

    const button = root.getElementById("scan-ports");
    if (button) {
      button.addEventListener("click", async () => {
        ctx.state.portScanRunning = true;
        ctx.requestContentRender(true);
        const result = await ctx.api.call(WS.GATEWAY_SCAN);
        ctx.state.portScanRunning = false;
        if (result) ctx.state.portScan = result;
        // keep the port dropdown of the gateway wizard in sync with the scan - without
        // wiping what the user already typed into an open wizard
        const form = await ctx.api.call(WS.GATEWAY_FORM);
        if (form) ctx.state.gatewayForm = form;
        const editorRoot = ctx.root && ctx.root.getElementById("gateway-editor");
        if (editorRoot && ctx.state.gatewayEditor) {
          ctx.state.gatewayEditor.values = readFields(editorRoot);
        }
        ctx.requestContentRender(true);
      });
    }
  },

  /** Buttons of the plug & play section. */
  _bindPlugAndPlay(ctx, root) {
    const start = async (payload, label) => {
      const status = ctx.state.plugAndPlay || {};
      // optimistic: the flow shows the first stage as active before the answer arrives
      ctx.state.plugAndPlay = { ...status, running: true, step: label, stage: "ports" };
      ctx.requestContentRender(true);
      const result = await ctx.api.call(WS.PNP_RUN, payload);
      if (result && result.status) {
        ctx.state.plugAndPlay = result.status;
      } else if (!result) {
        ctx.state.plugAndPlay = { ...status, running: false };
        alert((ctx.api.lastError || {}).message || "Could not start the detection.");
        ctx.api.lastError = null;
      }
      // the page refreshes every few seconds and picks up the progress and the report
      ctx.requestContentRender(true);
    };

    const toggle = root.getElementById("pnp-toggle");
    if (toggle) {
      toggle.addEventListener("click", async () => {
        const enabled = !!(ctx.state.plugAndPlay || {}).enabled;
        if (enabled) {
          await ctx.api.call(WS.PNP_RUN, { enable: false });
          const status = await ctx.api.call(WS.PNP_STATUS);
          if (status) ctx.state.plugAndPlay = status;
          ctx.requestContentRender(true);
          return;
        }
        await start({ enable: true }, "Plug & play switched on, detecting");
      });
    }

    const run = root.getElementById("pnp-run");
    if (run) run.addEventListener("click", () => start({}, "Detecting"));

    const rescan = root.getElementById("pnp-rescan");
    if (rescan) {
      rescan.addEventListener("click", () => {
        if (!confirm("Read the bus of every bus gateway again?\n\n"
                     + "The bus is locked while it is read - this can take a few minutes per "
                     + "gateway and reception pauses meanwhile.")) return;
        start({ rescan_bus: true }, "Re-reading all buses");
      });
    }

    // remember which result block is folded out, the page rebuilds itself every few seconds
    root.querySelectorAll("details[data-pnp-open]").forEach((details) => {
      details.addEventListener("toggle", () => {
        (ctx.state.pnpOpen || (ctx.state.pnpOpen = {}))[details.dataset.pnpOpen] = details.open;
      });
    });

    // a candidate which cannot be proven (FGW14-USB, the ESP2 bridge) is confirmed by hand:
    // open the wizard prefilled with what was detected
    root.querySelectorAll("button[data-add-suggested]").forEach((button) => {
      button.addEventListener("click", () => {
        const [deviceType, serialPath, address, port] = button.dataset.addSuggested.split("|");
        this._openGatewayWizard(ctx, {
          device_type: deviceType, serial_path: serialPath, address,
          port: port ? Number(port) : undefined,
        });
      });
    });
  },

  _renderRecordingNotice(ctx, logInfo) {
    if (logInfo.enabled !== false) return "";
    return `
      <div class="notice warn">
        <h3>EnOcean telegram recording is disabled</h3>
        <p>${escapeHtml(logInfo.hint || "")}</p>
        <pre>eltako:
  general_settings:
    log_enocean_telegrams: True
    telegram_log_filename: enocean_telegrams.jsonl   # optional</pre>
      </div>`;
  },

  _renderGateway(gateway, summary, ctx) {
    const telegramCount = ((summary.count_by_gateway || {})[String(gateway.id)]) || 0;
    const connected = gateway.connected;
    return `
      <div class="tile">
        <div class="tile-head">
          ${icon("mdi:router-wireless", "◉")}
          <span class="tile-title">${escapeHtml(gateway.name)}</span>
          ${gateway.simulated
            ? `<span class="tag simulated" title="No hardware: this gateway and its devices are simulated (see the simulation page)">simulated</span>` : ""}
          <span class="spacer" style="flex:1 1 auto"></span>
          ${connected === null || connected === undefined
            ? `<span class="pill">unknown</span>`
            : `<span class="pill ${connected ? "on" : "off"}">${connected ? "connected" : "disconnected"}</span>`}
        </div>
        <table>${definitionRows([
          ["Gateway id", `<span class="mono">${escapeHtml(gateway.id)}</span>`],
          ["Type / model", `${escapeHtml(gateway.type)}<span class="hint">${escapeHtml(gateway.model)}</span>`],
          ["Protocol", escapeHtml(gateway.native_protocol)],
          ["Base id", `<span class="mono">${escapeHtml(gateway.base_id)}</span>`],
          ["Connection", `<span class="mono">${escapeHtml(gateway.serial_path)}</span>`],
          ["Baud rate", gateway.baud_rate > 0 ? formatNumber(gateway.baud_rate) : "&ndash;"],
          ["Auto reconnect", escapeHtml(gateway.auto_reconnect)],
          ["Message delay", `${escapeHtml(gateway.message_delay)} s`],
          ["Recorded telegrams", formatNumber(telegramCount)],
          ["Source", this._gatewaySource(ctx, gateway)
            + (gateway.simulated ? ` <span class="hint">simulated - no hardware</span>` : "")],
        ])}</table>
        <div style="margin-top:10px; display:flex; gap:6px; flex-wrap:wrap">
          ${gateway.ha_device_id
            ? `<button class="action small" data-ha-device="${escapeHtml(gateway.ha_device_id)}">open device</button>` : ""}
          ${this._gatewaySource(ctx, gateway) === "web ui"
            ? `<button class="action small" data-edit-gateway="${escapeHtml(gateway.id)}">edit gateway</button>
               <button class="action small danger" data-remove-gateway="${escapeHtml(gateway.id)}">remove gateway</button>`
            : `<span class="hint">edit in configuration.yaml</span>`}
        </div>
      </div>`;
  },
};
