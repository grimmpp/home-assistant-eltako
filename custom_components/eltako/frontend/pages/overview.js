/** Overview page: gateways, entity summary and status of the telegram recording. */

import { card, chip, definitionRows, escapeHtml, formatDuration, formatNumber, icon } from "../lib/utils.js";

export const page = {
  id: "overview",
  title: "Overview",
  subtitle: "Gateways, devices and status of this integration",
  icon: "mdi:view-dashboard",
  glyph: "⌂",
  refreshMs: 5000,

  async load(ctx) {
    await Promise.all([ctx.loadIntegrationInfo(), ctx.loadLogInfo(), ctx.loadStatistics()]);
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
      ${gateways.length ? `<div class="tiles">${gateways.map((gw) => this._renderGateway(gw, summary)).join("")}</div>`
                        : `<div class="empty">No gateway is configured yet. Add a gateway in your
                           <code>configuration.yaml</code> and create the integration entry in Home Assistant.</div>`}

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

  _renderGateway(gateway, summary) {
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
        ])}</table>
      </div>`;
  },
};
