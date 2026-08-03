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

export const page = {
  id: "devices",
  title: "Device statistics",
  subtitle: "Telegram statistics per EnOcean address incl. EEP and entity references",
  icon: "mdi:table-large",
  glyph: "▤",
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
        ${card("Telegrams", formatNumber(summary.total_count))}
        ${card("Telegrams / min", formatNumber(summary.telegrams_per_minute))}
        ${card("Filtered polling", formatNumber(summary.filtered_count))}
      </div>
      ${Object.keys(summary.count_by_msg_type || {}).length ? `
        <div class="chips">${Object.entries(summary.count_by_msg_type)
          .sort((a, b) => b[1] - a[1]).map(([type, count]) => chip(type, count)).join("")}</div>` : ""}`;

    if (!devices.length) {
      return `${header}<div class="empty">No telegrams recorded yet.</div>`;
    }

    const sortableHeader = (column, label, extraClass = "") =>
      `<th data-sort="${column}" class="${extraClass} ${ctx.state.deviceSort === column ? "sorted" : ""}">${label}</th>`;

    const rows = devices.map((device) => `
      <tr class="${device.known ? "" : "unknown-row"}">
        <td class="mono">${escapeHtml(device.address)}
          ${device.local_address && device.local_address !== device.address
            ? `<span class="hint">bus ${escapeHtml(device.local_address)}</span>` : ""}</td>
        <td>${device.known ? escapeHtml(device.name || "") : `<span class="tag unknown">unknown</span>`}
          ${device.role && device.role !== "device" ? `<span class="tag role">${escapeHtml(device.role)}</span>` : ""}
          ${(device.entity_ids || []).length ? `<span class="hint">${escapeHtml(device.entity_ids.join(", "))}</span>` : ""}</td>
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
