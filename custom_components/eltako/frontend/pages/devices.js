/** Statistics per EnOcean address: how often, how regular, which entity, which EEP. */

import { WS } from "../lib/api.js";
import {
  card, chip, download, escapeHtml, formatDecoded, formatInterval, formatNumber, formatTime,
  matchesFilter, sortRows, timestampForFilename, toCsv,
} from "../lib/utils.js";

const CSV_COLUMNS = [
  "address", "local_address", "known", "role", "name", "eep", "platforms", "area", "entity_ids", "gateway_ids",
  "count", "count_incoming", "count_outgoing", "first_seen", "last_seen",
  "min_interval", "avg_interval", "max_interval", "msg_types", "last_data", "last_decoded",
];

// TODO type check: add /** @type {import("../types.js").Page} */ once the dom casts are in
export const page = {
  id: "statistics",
  title: "Statistics",
  subtitle: "Telegram statistics per EnOcean address incl. EEP and entity references",
  icon: "mdi:chart-box-outline",
  glyph: "▥",
  needsRecording: true,
  refreshMs: 5000,

  async load(ctx) {
    await Promise.all([ctx.loadLogInfo(), ctx.loadStatistics()]);
  },

  renderToolbar(ctx) {
    return `
      <input id="filter" type="search" placeholder="Filter address, device, EEP, entity, area&hellip;"
             value="${escapeHtml(ctx.state.deviceFilter)}" />
      <label class="check"><input id="only-unknown-devices" type="checkbox"
             ${ctx.state.onlyUnknownDevices ? "checked" : ""}/> only unknown</label>
      <span class="spacer"></span>
      <button id="refresh-devices" class="action">Refresh known devices</button>
      <button id="export-devices" class="action">Export CSV</button>`;
  },

  bindToolbar(ctx, root) {
    root.getElementById("filter").addEventListener("input", (event) => {
      ctx.state.deviceFilter = event.target.value;
      ctx.requestContentRender(true);
    });
    root.getElementById("only-unknown-devices").addEventListener("change", (event) => {
      ctx.state.onlyUnknownDevices = event.target.checked;
      ctx.requestContentRender(true);
    });
    root.getElementById("refresh-devices").addEventListener("click", async () => {
      await ctx.api.call(WS.LOG_REFRESH_DEVICES);
      await Promise.all([ctx.loadStatistics(), ctx.loadLogInfo()]);
      ctx.requestRender();
    });
    root.getElementById("export-devices").addEventListener("click", () => {
      download(`eltako_device_statistics_${timestampForFilename()}.csv`,
        toCsv(CSV_COLUMNS, this._filtered(ctx)), "text/csv");
    });
  },

  render(ctx) {
    if (ctx.state.logInfo && ctx.state.logInfo.enabled === false) return ctx.renderRecordingDisabled();

    const summary = (ctx.state.statistics || {}).summary || {};
    const devices = sortRows(this._filtered(ctx), ctx.state.deviceSort, ctx.state.deviceSortDescending);

    const header = `
      <div class="cards">
        ${card("Addresses seen", formatNumber(summary.device_count))}
        ${card("Known", formatNumber(summary.known_device_count), "good")}
        ${card("Unknown", formatNumber(summary.unknown_device_count), summary.unknown_device_count ? "warn" : "")}
        ${summary.bus_message_count ? card("Bus messages", formatNumber(summary.bus_message_count), "",
                                           "polling / discovery, no EnOcean address") : ""}
        ${card("Telegrams", formatNumber(summary.total_count))}
        ${card("Telegrams / min", formatNumber(summary.telegrams_per_minute))}
        ${card("Filtered polling", formatNumber(summary.filtered_count))}
        ${summary.file_logging_enabled
          ? card("Log file", formatNumber(summary.file_written_count), summary.file_error ? "warn" : "",
                 summary.file_error || (summary.file_rotate_after_days
                   ? `rotates after ${summary.file_rotate_after_days} d / ${summary.file_max_size_mb} MB`
                   : `rotates after ${summary.file_max_size_mb} MB`))
          : card("Log file", "off", "warn", "telegrams are not persisted")}
        ${summary.timeseries_enabled
          ? card("Timeseries export", formatNumber((summary.timeseries || {}).exported_count),
                 (summary.timeseries || {}).last_error ? "warn" : "good",
                 (summary.timeseries || {}).last_error
                   || `InfluxDB bucket ${(summary.timeseries || {}).bucket || ""}`)
          : ""}
      </div>
      ${Object.keys(summary.count_by_msg_type || {}).length ? `
        <div class="chips">${Object.entries(summary.count_by_msg_type)
          .sort((a, b) => b[1] - a[1]).map(([type, count]) => chip(type, count)).join("")}</div>` : ""}`;

    if (!devices.length) {
      return `${header}<div class="empty">No telegrams recorded yet.</div>`;
    }

    const sortableHeader = (column, label, extraClass = "") =>
      `<th data-sort="${column}" class="${extraClass} ${ctx.state.deviceSort === column ? "sorted" : ""}">${label}</th>`;

    // current state of an entity - hass.states is pushed into the panel by home assistant,
    // so the value is as live as the 5 s refresh of this page
    const stateOf = (entityId) => {
      const state = (((ctx.hass || {}).states || {})[entityId]) || null;
      if (!state) return "";
      const unit = (state.attributes || {}).unit_of_measurement;
      return `${state.state}${unit ? ` ${unit}` : ""}`;
    };

    const rows = devices.map((device) => `
      <tr class="${device.known ? "" : "unknown-row"}">
        <td class="mono">${escapeHtml(device.address)}
          ${device.local_address && device.local_address !== device.address
            ? `<span class="hint">bus ${escapeHtml(device.local_address)}</span>` : ""}</td>
        <td>${device.known ? escapeHtml(device.name || "") : `<span class="tag unknown">unknown</span>`}
          ${device.role && device.role !== "device" ? `<span class="tag role">${escapeHtml(device.role)}</span>` : ""}
          ${(device.entity_ids || []).map((entityId) => `
            <span class="hint">${escapeHtml(entityId)}${stateOf(entityId)
              ? ` = <b>${escapeHtml(stateOf(entityId))}</b>` : ""}</span>`).join("")}</td>
        <td class="mono">${escapeHtml(device.eep || device.teach_in_profile || "-")}</td>
        <td>${escapeHtml((device.platforms || []).join(", ") || "-")}</td>
        <td>${escapeHtml(device.area || "-")}</td>
        <td>${escapeHtml((device.gateway_ids || []).join(", "))}</td>
        <td class="num">${formatNumber(device.count)}</td>
        <td class="num">${formatNumber(device.count_incoming)} / ${formatNumber(device.count_outgoing)}</td>
        <td class="num">${formatInterval(device.avg_interval)}</td>
        <td class="num">${formatInterval(device.min_interval)} / ${formatInterval(device.max_interval)}</td>
        <td class="mono">${formatTime(device.last_seen)}</td>
        <td class="decoded">${formatDecoded(device.last_decoded, 4)}</td>
      </tr>`).join("");

    return `
      ${header}
      <div class="table-wrapper">
        <table>
          <thead><tr>
            ${sortableHeader("address", "Address")}
            ${sortableHeader("name", "Device / Entity")}
            ${sortableHeader("eep", "EEP")}
            <th>Platform</th>
            ${sortableHeader("area", "Area")}
            <th>GW</th>
            ${sortableHeader("count", "Count", "num")}
            <th class="num">in / out</th>
            ${sortableHeader("avg_interval", "&#8709; interval", "num")}
            <th class="num">min / max</th>
            ${sortableHeader("last_seen", "Last seen")}
            <th>Last values</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="footnote">${devices.length} addresses. Click a column header to sort.
        Intervals describe the time between two telegrams of that address.</div>`;
  },

  afterRender(ctx, root) {
    root.querySelectorAll("th[data-sort]").forEach((header) => {
      header.addEventListener("click", () => {
        const column = header.dataset.sort;
        if (ctx.state.deviceSort === column) ctx.state.deviceSortDescending = !ctx.state.deviceSortDescending;
        else {
          ctx.state.deviceSort = column;
          ctx.state.deviceSortDescending = true;
        }
        ctx.requestContentRender(true);
      });
    });
  },

  _filtered(ctx) {
    const devices = (ctx.state.statistics || {}).devices || [];
    return devices.filter((device) => {
      if (ctx.state.onlyUnknownDevices && device.known) return false;
      return matchesFilter(ctx.state.deviceFilter, [
        device.address, device.local_address, device.name, device.eep, device.area,
        (device.entity_ids || []).join(" "), (device.platforms || []).join(" "),
      ]);
    });
  },
};
