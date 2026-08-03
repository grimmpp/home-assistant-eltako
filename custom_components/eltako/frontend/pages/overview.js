/** Overview page: gateways, entity summary and status of the telegram recording. */

import { WS } from "../lib/api.js";
import { FORM_STYLES, readFields, renderFields } from "../lib/form.js";
import { card, chip, definitionRows, escapeHtml, formatDuration, formatNumber, icon } from "../lib/utils.js";

export const page = {
  id: "overview",
  title: "Overview",
  subtitle: "Gateways, devices and status of this integration",
  icon: "mdi:view-dashboard",
  glyph: "⌂",
  styles: FORM_STYLES,
  refreshMs: 5000,

  async load(ctx) {
    const [form] = await Promise.all([
      ctx.state.gatewayForm ? Promise.resolve(ctx.state.gatewayForm) : ctx.api.call(WS.GATEWAY_FORM),
      ctx.loadIntegrationInfo(), ctx.loadLogInfo(), ctx.loadStatistics(),
    ]);
    if (form) ctx.state.gatewayForm = form;

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

      <h2>Gateways</h2>
      ${this._renderGatewayWizard(ctx)}
      <div class="toolbar">
        <button id="add-gateway" class="action primary">+ Add gateway</button>
        <span class="field-help">Creates the gateway and its Home Assistant entry directly -
          no <code>configuration.yaml</code> needed.</span>
      </div>
      ${gateways.length ? `<div class="tiles">${gateways.map((gw) => this._renderGateway(gw, summary, ctx)).join("")}</div>`
                        : `<div class="empty">No gateway is configured yet. Use <b>+ Add gateway</b>.</div>`}

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

  /** Navigate to the device page of home assistant (canonical panel navigation). */
  _openHaDevice(deviceId) {
    const path = `/config/devices/device/${deviceId}`;
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed"));
  },

  /** Wizard for a new gateway: type, connection, id, name, base id. */  /** Navigate to the device page of home assistant (canonical panel navigation). */
  _openHaDevice(deviceId) {
    const path = `/config/devices/device/${deviceId}`;
    history.pushState(null, "", path);
    window.dispatchEvent(new CustomEvent("location-changed"));
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
    const freePorts = (form.ports || []).filter((port) => port.free);

    const fields = [
      { name: "device_type", label: "Gateway type", type: "select", required: true,
        options: (form.types || []).map((t) => t.device_type),
        help: type.device_type ? `${type.protocol}${type.baud_rate ? `, ${type.baud_rate} baud` : ""}` +
              `${type.is_bus_gateway ? ", bus gateway (RS485)" : type.is_transceiver ? ", wireless transceiver" : ""}` : "" },
      isLan
        ? { name: "address", label: "Host name or IP address", type: "text", required: true,
            help: "e.g. 192.168.1.50 or gateway.local" }
        : { name: "serial_path", label: "Serial port", type: "select", required: true,
            options: (form.ports || []).map((port) => port.device),
            help: freePorts.length
              ? `Free ports: ${freePorts.map((p) => p.device).join(", ")}. Use the USB scan below for details.`
              : "All detected ports are already in use by a gateway." },
      { name: "id", label: "Gateway id", type: "number", required: true, min: 0, max: 255,
        help: "Unique number of this gateway inside the integration. It is part of the entity ids." },
      { name: "name", label: "Name", type: "text", required: false, help: "Free text, e.g. 'FAM14 cellar'." },
      { name: "base_id", label: "Base id", type: "address", required: false, help: form.hint || "" },
    ];
    if (isLan) {
      fields.push({ name: "port", label: "Port", type: "number", required: false, min: 1, max: 65535 });
    }

    return `
      <div class="form-card" id="gateway-editor">
        <h3>Add gateway</h3>
        <div class="form-grid">${renderFields(fields, editor.values || {})}</div>
        ${ctx.state.gatewayError ? `<div class="form-error">${escapeHtml(ctx.state.gatewayError)}</div>` : ""}
        <div class="form-actions">
          <button id="gateway-save" class="action primary">Create gateway</button>
          <button id="gateway-cancel" class="action">Cancel</button>
          <span class="field-help">The values are validated with the same schema as the yaml.</span>
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
      addGateway.addEventListener("click", async () => {
        if (!ctx.state.gatewayForm) ctx.state.gatewayForm = await ctx.api.call(WS.GATEWAY_FORM);
        const form = ctx.state.gatewayForm || {};
        ctx.state.gatewayEditor = { values: {
          device_type: (form.types || [{}])[0].device_type || "fgw14usb",
          id: form.next_free_id, base_id: form.default_base_id || "00-00-00-00",
          serial_path: ((form.ports || []).find((p) => p.free) || {}).device || "",
        }};
        ctx.state.gatewayError = null;
        ctx.state.gatewayMessage = null;
        ctx.requestContentRender(true);
      });
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
        const result = await ctx.api.call(WS.GATEWAY_ADD, { gateway: values });
        if (result) {
          ctx.state.gatewayEditor = null;
          ctx.state.gatewayError = null;
          ctx.state.gatewayMessage = result.config_entry_created
            ? "Gateway created and set up. Its entities appear within a few seconds."
            : `Gateway stored, but Home Assistant did not create the entry (${result.flow_result || result.reason}).`;
          ctx.state.gatewayForm = await ctx.api.call(WS.GATEWAY_FORM);
          await ctx.loadIntegrationInfo();
        } else {
          ctx.state.gatewayEditor.values = values;
          ctx.state.gatewayError = (ctx.api.lastError || {}).message || "Could not create the gateway.";
          ctx.api.lastError = null;
        }
        ctx.requestContentRender(true);
      });
    }

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

    root.querySelectorAll("[data-ha-device]").forEach((element) => {
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        this._openHaDevice(element.dataset.haDevice);
      });
    });

    const button = root.getElementById("scan-ports");
    if (button) {
      button.addEventListener("click", async () => {
        ctx.state.portScanRunning = true;
        ctx.requestContentRender(true);
        const result = await ctx.api.call(WS.GATEWAY_SCAN);
        ctx.state.portScanRunning = false;
        if (result) ctx.state.portScan = result;
        ctx.requestContentRender(true);
      });
    }
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
          ["Source", this._gatewaySource(ctx, gateway)],
        ])}</table>
        <div style="margin-top:10px; display:flex; gap:6px">
          ${gateway.ha_device_id
            ? `<button class="action small" data-ha-device="${escapeHtml(gateway.ha_device_id)}">open device</button>` : ""}
          ${this._gatewaySource(ctx, gateway) === "web ui"
            ? `<button class="action small danger" data-remove-gateway="${escapeHtml(gateway.id)}">remove gateway</button>` : ""}
        </div>
      </div>`;
  },
};
