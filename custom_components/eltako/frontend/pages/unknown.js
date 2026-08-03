/** Addresses which sent telegrams but are not configured in Home Assistant yet. */

import { escapeHtml, formatNumber, formatTime, matchesFilter } from "../lib/utils.js";

/** Rough EEP guess based on the message type. A teach-in telegram is always preferred. */
function guessEep(device) {
  const types = Object.keys(device.msg_types || {});
  if (types.some((type) => type.includes("RPS"))) return { eep: "F6-02-01", source: "guessed from RPS telegram" };
  if (types.some((type) => type.includes("1BS"))) return { eep: "D5-00-01", source: "guessed from 1BS telegram" };
  if (types.some((type) => type.includes("4BS"))) return { eep: "A5-04-02", source: "guessed from 4BS telegram" };
  return { eep: null, source: null };
}

function platformHint(eep) {
  if (!eep) return "sensor";
  if (eep.startsWith("F6") || eep.startsWith("D5")) return "binary_sensor";
  return "sensor";
}

export const page = {
  id: "unknown",
  title: "Unknown devices",
  subtitle: "Addresses which are not part of your configuration.yaml",
  icon: "mdi:help-circle-outline",
  glyph: "?",
  needsRecording: true,
  refreshMs: 5000,

  async load(ctx) {
    await Promise.all([ctx.loadLogInfo(), ctx.loadStatistics()]);
  },

  /** Flash the row of an unknown device when it sends - immediate feedback on a button press. */
  onTelegram(ctx, telegram) {
    const root = ctx.root;
    if (!root || !telegram.address || telegram.known) return;

    const escaped = String(telegram.address).replace(/"/g, "");
    root.querySelectorAll(`tr[data-address="${escaped}"]`).forEach((row) => {
      row.classList.remove("telegram-flash");
      void row.offsetWidth;
      row.classList.add("telegram-flash");
      clearTimeout(row._flashTimer);
      row._flashTimer = setTimeout(() => row.classList.remove("telegram-flash"), 1400);
    });
  },

  badge(ctx) {
    const count = this._unknown(ctx).length;
    return count ? String(count) : null;
  },

  renderToolbar(ctx) {
    return `
      <input id="filter" type="search" placeholder="Filter address&hellip;"
             value="${escapeHtml(ctx.state.unknownFilter)}" />
      <span class="spacer"></span>
      <button id="copy-all" class="action">Copy all as yaml</button>`;
  },

  bindToolbar(ctx, root) {
    root.getElementById("filter").addEventListener("input", (event) => {
      ctx.state.unknownFilter = event.target.value;
      ctx.requestContentRender(true);
    });
    root.getElementById("copy-all").addEventListener("click", (event) => {
      const yaml = this._filtered(ctx).map((device) => this._yamlSnippet(device)).join("");
      navigator.clipboard.writeText(yaml);
      const button = event.target;
      button.textContent = "copied";
      setTimeout(() => (button.textContent = "Copy all as yaml"), 1500);
    });
  },

  render(ctx) {
    if (ctx.state.logInfo && ctx.state.logInfo.enabled === false) return ctx.renderRecordingDisabled();

    const devices = this._filtered(ctx);
    if (!devices.length) {
      return `<div class="empty">${(ctx.state.statistics || {}).devices?.length
        ? "All recorded telegrams belong to configured devices. &#127881;"
        : "No telegrams recorded yet."}</div>`;
    }

    const rows = devices.map((device) => {
      const guess = device.teach_in_profile
        ? { eep: device.teach_in_profile, source: "from 4BS teach-in telegram" }
        : guessEep(device);
      return `
        <tr data-address="${escapeHtml(device.address)}">
          <td class="mono">${escapeHtml(device.address)}</td>
          <td class="num">${formatNumber(device.count)}</td>
          <td>${escapeHtml(Object.keys(device.msg_types || {}).join(", "))}</td>
          <td class="mono">${escapeHtml(device.last_data || "-")}</td>
          <td class="mono">${escapeHtml(guess.eep || "?")}
            ${guess.source ? `<span class="hint">${escapeHtml(guess.source)}</span>` : ""}</td>
          <td class="mono">${formatTime(device.last_seen)}</td>
          <td class="actions">
            <button class="action small primary"
                    data-add="${escapeHtml(device.address)}|${escapeHtml(guess.eep || "")}|${escapeHtml(platformHint(guess.eep))}"
                    >+ add device</button>
            <button class="action small" data-yaml="${encodeURIComponent(this._yamlSnippet(device))}">copy yaml</button>
          </td>
        </tr>`;
    }).join("");

    return `
      <div class="notice warn">
        <h3>${devices.length} address${devices.length === 1 ? "" : "es"} not configured</h3>
        <p>These addresses send telegrams but are unknown to Home Assistant. Press a button on the device
          or wait for its next telegram to identify it, then add it below the <code>devices:</code> section of
          the gateway in your <code>configuration.yaml</code>.</p>
        <p>The EEP is derived from a 4BS teach-in telegram if the device sent one &ndash; otherwise it is only a
          guess based on the message type and has to be verified.</p>
      </div>
      <div class="table-wrapper">
        <table>
          <thead><tr>
            <th>Address</th><th class="num">Telegrams</th><th>Message types</th><th>Last data</th>
            <th>EEP</th><th>Last seen</th><th></th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  },

  afterRender(ctx, root) {
    // hand the device over to the device page which opens the form prefilled
    root.querySelectorAll("button[data-add]").forEach((button) => {
      button.addEventListener("click", () => {
        const [address, eep, platform] = button.dataset.add.split("|");
        ctx.state.pendingNewDevice = {
          address,
          eep: eep || "",
          platform: platform || "binary_sensor",
          name: `Device ${address}`,
        };
        ctx.navigate("devices");
      });
    });

    root.querySelectorAll("button[data-yaml]").forEach((button) => {
      button.addEventListener("click", () => {
        navigator.clipboard.writeText(decodeURIComponent(button.dataset.yaml));
        button.textContent = "copied";
        setTimeout(() => (button.textContent = "copy yaml"), 1500);
      });
    });
  },

  _unknown(ctx) {
    // bus internal messages (polling, discovery, ...) have no EnOcean address and
    // therefore cannot be added to the configuration as a device
    return ((ctx.state.statistics || {}).devices || [])
      .filter((device) => !device.known && device.address && device.role !== "bus_message");
  },

  _filtered(ctx) {
    return this._unknown(ctx).filter((device) => matchesFilter(ctx.state.unknownFilter, [device.address]));
  },

  _yamlSnippet(device) {
    const guess = device.teach_in_profile || guessEep(device).eep;
    return `      # ${platformHint(guess)}: seen ${device.count} time(s), last data ${device.last_data || "-"}\n` +
      `      - id: ${device.address}\n` +
      `        eep: ${guess || "<EEP>"}\n` +
      `        name: "New device ${device.address}"\n`;
  },
};
