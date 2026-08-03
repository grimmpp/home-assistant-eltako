/** Live view of all recorded EnOcean telegrams. */

import { WS } from "../lib/api.js";
import {
  download, escapeHtml, formatDecoded, formatNumber, formatTime, matchesFilter, timestampForFilename, toCsv,
} from "../lib/utils.js";

const CSV_COLUMNS = [
  "seq", "timestamp", "direction", "gateway_id", "gateway_name", "msg_type", "org", "address", "local_address",
  "known", "role", "eep", "device_name", "entity_ids", "area", "status", "data", "raw", "decoded",
];

export const page = {
  id: "telegrams",
  title: "Live telegrams",
  subtitle: "All EnOcean telegrams received and sent by the configured gateways",
  icon: "mdi:swap-vertical",
  glyph: "⇅",
  needsRecording: true,

  async load(ctx) {
    await Promise.all([ctx.loadLogInfo(), ctx.loadRecentTelegrams()]);
  },

  /** Called by the shell for every telegram of the live stream. */
  onTelegram(ctx) {
    if (!ctx.state.paused) ctx.requestContentRender();
  },

  renderStatus(ctx) {
    const info = ctx.state.logInfo || {};
    return `
      <span class="pill ${ctx.state.paused ? "warn" : "on"}">${ctx.state.paused ? "paused" : "live"}</span>
      <span class="pill">${formatNumber(info.total_count)} total</span>
      <span class="pill">${formatNumber(info.telegrams_per_minute)} / min</span>
      ${info.file_logging_enabled
        ? `<span class="pill" title="${escapeHtml(info.file_path)}">${formatNumber(info.file_written_count)} written</span>`
        : `<span class="pill warn" title="Set 'telegram_log_filename' to persist telegrams">memory only</span>`}`;
  },

  renderToolbar(ctx) {
    const state = ctx.state;
    return `
      <input id="filter" type="search" placeholder="Filter address, device, EEP, entity, data&hellip;"
             value="${escapeHtml(state.telegramFilter)}" />
      <select id="direction">
        <option value="all" ${state.directionFilter === "all" ? "selected" : ""}>all directions</option>
        <option value="incoming" ${state.directionFilter === "incoming" ? "selected" : ""}>incoming</option>
        <option value="outgoing" ${state.directionFilter === "outgoing" ? "selected" : ""}>outgoing</option>
      </select>
      <label class="check"><input id="only-unknown" type="checkbox" ${state.onlyUnknown ? "checked" : ""}/> only unknown</label>
      <button id="pause" class="action ${state.paused ? "primary" : ""}">${state.paused ? "Resume" : "Pause"}</button>
      <span class="spacer"></span>
      <button id="export" class="action">Export CSV</button>
      <button id="clear" class="action danger">Clear</button>`;
  },

  bindToolbar(ctx, root) {
    root.getElementById("filter").addEventListener("input", (event) => {
      ctx.state.telegramFilter = event.target.value;
      ctx.requestContentRender(true);
    });
    root.getElementById("direction").addEventListener("change", (event) => {
      ctx.state.directionFilter = event.target.value;
      ctx.requestContentRender(true);
    });
    root.getElementById("only-unknown").addEventListener("change", (event) => {
      ctx.state.onlyUnknown = event.target.checked;
      ctx.requestContentRender(true);
    });
    root.getElementById("pause").addEventListener("click", () => {
      ctx.state.paused = !ctx.state.paused;
      ctx.requestRender();
    });
    root.getElementById("export").addEventListener("click", () => {
      download(`eltako_telegrams_${timestampForFilename()}.csv`,
        toCsv(CSV_COLUMNS, this._filtered(ctx)), "text/csv");
    });
    root.getElementById("clear").addEventListener("click", async () => {
      await ctx.api.call(WS.LOG_CLEAR);
      ctx.state.telegrams = [];
      await Promise.all([ctx.loadLogInfo(), ctx.loadStatistics()]);
      ctx.requestRender();
    });
  },

  render(ctx) {
    if (ctx.state.logInfo && ctx.state.logInfo.enabled === false) return ctx.renderRecordingDisabled();

    const telegrams = this._filtered(ctx);
    if (!telegrams.length) {
      return `<div class="empty">${ctx.state.telegrams.length
        ? "No telegram matches the current filter."
        : "Waiting for telegrams&hellip; As soon as a device sends something it shows up here."}</div>`;
    }

    const rows = telegrams.map((telegram, index) => {
      const detailId = `telegram-detail-${telegram.seq}-${index}`;
      return `
        <tr data-detail="${detailId}" class="${telegram.known ? "" : "unknown-row"}">
          <td class="mono">${formatTime(telegram.timestamp)}</td>
          <td class="dir ${escapeHtml(telegram.direction)}">${telegram.direction === "outgoing" ? "&#8593; out" : "&#8595; in"}</td>
          <td>${escapeHtml(telegram.gateway_name || telegram.gateway_id)}</td>
          <td class="mono">${escapeHtml(telegram.address || "-")}
            ${telegram.local_address && telegram.local_address !== telegram.address
              ? `<span class="hint">bus ${escapeHtml(telegram.local_address)}</span>` : ""}</td>
          <td>${telegram.known
              ? `${escapeHtml(telegram.device_name || "")}
                 ${telegram.role && telegram.role !== "device" ? `<span class="tag role">${escapeHtml(telegram.role)}</span>` : ""}
                 ${(telegram.entity_ids || []).length ? `<span class="hint">${escapeHtml(telegram.entity_ids.join(", "))}</span>` : ""}`
              : `<span class="tag unknown">unknown</span>`}</td>
          <td class="mono">${escapeHtml(telegram.eep || telegram.teach_in_profile || "-")}</td>
          <td>${escapeHtml(telegram.msg_type)}</td>
          <td class="mono">${escapeHtml(telegram.data || telegram.payload || "-")}</td>
          <td class="decoded">${formatDecoded(telegram.decoded)}</td>
        </tr>
        <tr class="detail" id="${detailId}"><td colspan="9"><pre>${escapeHtml(JSON.stringify(telegram, null, 2))}</pre></td></tr>`;
    }).join("");

    return `
      <div class="table-wrapper">
        <table class="clickable">
          <thead><tr>
            <th>Time</th><th>Dir</th><th>Gateway</th><th>Address</th><th>Device / Entity</th>
            <th>EEP</th><th>Message type</th><th>Data</th><th>Decoded</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="footnote">Showing ${telegrams.length} of ${ctx.state.telegrams.length} buffered telegrams
        (newest first). Click a row to see the complete record. The buffer size can be changed with
        <code>telegram_log_buffer_size</code>.</div>`;
  },

  afterRender(ctx, root) {
    root.querySelectorAll("tr[data-detail]").forEach((row) => {
      row.addEventListener("click", () => {
        const detail = root.getElementById(row.dataset.detail);
        if (detail) detail.classList.toggle("visible");
      });
    });
  },

  _filtered(ctx) {
    const state = ctx.state;
    return state.telegrams.filter((telegram) => {
      if (state.directionFilter !== "all" && telegram.direction !== state.directionFilter) return false;
      if (state.onlyUnknown && telegram.known) return false;
      return matchesFilter(state.telegramFilter, [
        telegram.address, telegram.local_address, telegram.device_name, telegram.eep, telegram.msg_type,
        telegram.data, telegram.gateway_name, (telegram.entity_ids || []).join(" "),
      ]);
    });
  },
};
