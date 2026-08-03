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
    await Promise.all([ctx.loadLogInfo(), ctx.loadRecentTelegrams(), ctx.loadIntegrationInfo()]);
  },

  /** Called by the shell for every telegram of the live stream. */
  onTelegram(ctx) {
    // while the send form is open the list must not re-render - the inputs would lose focus
    if (!ctx.state.paused && !ctx.state.sendForm) ctx.requestContentRender();
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
      <select id="gateway">
        <option value="all" ${state.gatewayFilter === "all" ? "selected" : ""}>all gateways</option>
        ${this._gateways(ctx).map((gw) => `
          <option value="${escapeHtml(gw.id)}" ${String(state.gatewayFilter) === String(gw.id) ? "selected" : ""}>
            ${escapeHtml(gw.name)}</option>`).join("")}
      </select>
      <select id="direction">
        <option value="all" ${state.directionFilter === "all" ? "selected" : ""}>all directions</option>
        <option value="incoming" ${state.directionFilter === "incoming" ? "selected" : ""}>incoming</option>
        <option value="outgoing" ${state.directionFilter === "outgoing" ? "selected" : ""}>outgoing</option>
      </select>
      <label class="check"><input id="only-unknown" type="checkbox" ${state.onlyUnknown ? "checked" : ""}/> only unknown</label>
      <button id="pause" class="action ${state.paused ? "primary" : ""}">${state.paused ? "Resume" : "Pause"}</button>
      <span class="spacer"></span>
      <button id="send-telegram" class="action ${state.sendForm ? "" : "primary"}">
        ${state.sendForm ? "Close send form" : "Send telegram"}</button>
      <button id="export" class="action">Export CSV</button>
      <button id="clear" class="action danger">Clear</button>`;
  },

  bindToolbar(ctx, root) {
    root.getElementById("filter").addEventListener("input", (event) => {
      ctx.state.telegramFilter = event.target.value;
      ctx.requestContentRender(true);
    });
    root.getElementById("gateway").addEventListener("change", (event) => {
      ctx.state.gatewayFilter = event.target.value;
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
    root.getElementById("send-telegram").addEventListener("click", async () => {
      if (ctx.state.sendForm) {
        ctx.state.sendForm = null;
      } else {
        if (!ctx.state.sendFormDescriptor) {
          ctx.state.sendFormDescriptor = await ctx.api.call(WS.SEND_TELEGRAM_FORM);
        }
        const gateways = (ctx.state.sendFormDescriptor || {}).gateways || [];
        ctx.state.sendForm = {
          gatewayId: gateways.length ? gateways[0].id : 0,
          mode: "eep", eep: "A5-38-08", senderId: "", fields: {}, raw: "",
          result: null, error: null,
        };
      }
      ctx.requestRender();
    });
  },

  render(ctx) {
    if (ctx.state.logInfo && ctx.state.logInfo.enabled === false) return ctx.renderRecordingDisabled();

    const sendForm = this._renderSendForm(ctx);

    const telegrams = this._filtered(ctx);
    if (!telegrams.length) {
      return `${sendForm}<div class="empty">${ctx.state.telegrams.length
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
      ${sendForm}
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

  /**
   * Form to send an arbitrary EnOcean telegram: built from an EEP with its fields, or as
   * raw ESP2 hex. The live list below shows the sent telegram right away.
   */
  _renderSendForm(ctx) {
    const form = ctx.state.sendForm;
    if (!form) return "";
    const descriptor = ctx.state.sendFormDescriptor || { gateways: [], eeps: [] };
    const eep = descriptor.eeps.find((candidate) => candidate.eep === form.eep) || { fields: [] };

    return `
      <div class="form-card" id="send-form">
        <h3>Send EnOcean telegram</h3>
        <div class="form-grid">
          <div class="field">
            <label for="send-gateway">Gateway *</label>
            <select id="send-gateway">
              ${descriptor.gateways.map((gw) => `
                <option value="${escapeHtml(gw.id)}" ${String(gw.id) === String(form.gatewayId) ? "selected" : ""}>
                  ${escapeHtml(gw.name)} (base id ${escapeHtml(gw.base_id || "-")})</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <label for="send-mode">Input *</label>
            <select id="send-mode">
              <option value="eep" ${form.mode === "eep" ? "selected" : ""}>EEP fields</option>
              <option value="raw" ${form.mode === "raw" ? "selected" : ""}>raw ESP2 hex</option>
            </select>
          </div>
          ${form.mode === "raw" ? `
            <div class="field" style="grid-column: 1 / -1">
              <label for="send-raw">ESP2 telegram (hex) *</label>
              <input id="send-raw" class="mono" value="${escapeHtml(form.raw)}"
                     placeholder="0b 07 00 00 00 09 00 00 b0 05 30  (11 body bytes, or 14 with A5 5A + checksum)" />
              <span class="field-help">11 body bytes, or the full frame A5 5A &hellip; checksum (checksum is validated).</span>
            </div>` : `
            <div class="field">
              <label for="send-eep">EEP *</label>
              <select id="send-eep">
                ${descriptor.eeps.map((candidate) => `
                  <option value="${escapeHtml(candidate.eep)}" ${candidate.eep === form.eep ? "selected" : ""}>
                    ${escapeHtml(candidate.description ? `${candidate.eep} - ${candidate.description}`
                                                       : candidate.eep)}</option>`).join("")}
              </select>
              ${eep.description ? `<span class="field-help">${escapeHtml(eep.description)}</span>` : ""}
            </div>
            <div class="field">
              <label for="send-sender">Sender id *</label>
              <input id="send-sender" class="mono" value="${escapeHtml(form.senderId)}" placeholder="00-00-B0-01" />
              <span class="field-help">Local id for bus gateways, base id + offset for transceivers.</span>
            </div>
            ${eep.fields.map((field) => `
              <div class="field">
                <label for="send-field-${escapeHtml(field)}">${escapeHtml(field)}</label>
                <input id="send-field-${escapeHtml(field)}" data-send-field="${escapeHtml(field)}"
                       value="${escapeHtml(form.fields[field] ?? "")}" placeholder="0" />
              </div>`).join("")}`}
        </div>
        ${form.error ? `<div class="notice warn">${escapeHtml(form.error)}</div>` : ""}
        ${form.result ? `<div class="notice">Sent: <code>${escapeHtml(form.result.telegram)}</code>
          <span class="hint mono">${escapeHtml(form.result.hex)}</span></div>` : ""}
        <div class="form-actions">
          <button class="action primary" id="send-submit">Send</button>
          <button class="action" id="send-close">Close</button>
        </div>
      </div>`;
  },

  afterRender(ctx, root) {
    root.querySelectorAll("tr[data-detail]").forEach((row) => {
      row.addEventListener("click", () => {
        const detail = root.getElementById(row.dataset.detail);
        if (detail) detail.classList.toggle("visible");
      });
    });

    const form = ctx.state.sendForm;
    if (!form || !root.getElementById("send-form")) return;
    root.getElementById("send-gateway").addEventListener("change", (event) => {
      form.gatewayId = event.target.value;
    });
    root.getElementById("send-mode").addEventListener("change", (event) => {
      form.mode = event.target.value;
      ctx.requestContentRender(true);
    });
    root.getElementById("send-eep")?.addEventListener("change", (event) => {
      form.eep = event.target.value;
      ctx.requestContentRender(true);
    });
    root.getElementById("send-sender")?.addEventListener("input", (event) => { form.senderId = event.target.value; });
    root.getElementById("send-raw")?.addEventListener("input", (event) => { form.raw = event.target.value; });
    root.querySelectorAll("[data-send-field]").forEach((input) => {
      input.addEventListener("input", (event) => { form.fields[input.dataset.sendField] = event.target.value; });
    });
    root.getElementById("send-close").addEventListener("click", () => {
      ctx.state.sendForm = null;
      ctx.requestRender();
    });
    root.getElementById("send-submit").addEventListener("click", async () => {
      const payload = { gateway_id: Number(form.gatewayId) };
      if (form.mode === "raw") payload.raw = form.raw;
      else Object.assign(payload, { sender_id: form.senderId, eep: form.eep, fields: form.fields });
      const result = await ctx.api.call(WS.SEND_TELEGRAM, payload);
      form.result = result;
      form.error = result ? null : ((ctx.api.lastError || {}).message || "Sending failed.");
      await ctx.loadRecentTelegrams();
      ctx.requestContentRender(true);
    });
  },

  /** Gateways for the filter: from the integration info, fallback to the recorded telegrams. */
  _gateways(ctx) {
    const fromInfo = ((ctx.state.integrationInfo || {}).gateways || [])
      .map((gw) => ({ id: gw.id, name: gw.name }));
    if (fromInfo.length) return fromInfo;
    const seen = new Map();
    for (const telegram of ctx.state.telegrams) {
      if (telegram.gateway_id !== undefined && !seen.has(telegram.gateway_id)) {
        seen.set(telegram.gateway_id, { id: telegram.gateway_id, name: telegram.gateway_name || telegram.gateway_id });
      }
    }
    return [...seen.values()];
  },

  _filtered(ctx) {
    const state = ctx.state;
    return state.telegrams.filter((telegram) => {
      if (state.gatewayFilter !== "all" && String(telegram.gateway_id) !== String(state.gatewayFilter)) return false;
      if (state.directionFilter !== "all" && telegram.direction !== state.directionFilter) return false;
      if (state.onlyUnknown && telegram.known) return false;
      return matchesFilter(state.telegramFilter, [
        telegram.address, telegram.local_address, telegram.device_name, telegram.eep, telegram.msg_type,
        telegram.data, telegram.gateway_name, (telegram.entity_ids || []).join(" "),
      ]);
    });
  },
};
