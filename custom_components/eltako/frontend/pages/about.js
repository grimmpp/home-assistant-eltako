/** About page: information about the integration itself, its configuration and links. */

import {
  card, chip, definitionRows, escapeHtml, formatBoolean, formatNumber, icon,
} from "../lib/utils.js";

const REPOSITORY_URL = "https://github.com/grimmpp/home-assistant-eltako";

const DOC_LINKS = [
  ["Documentation overview", `${REPOSITORY_URL}/tree/main/docs`, "mdi:book-open-variant"],
  ["Telegram logging & analysis", `${REPOSITORY_URL}/tree/main/docs/telegram-analysis/readme.md`, "mdi:file-search-outline"],
  ["Gateways", `${REPOSITORY_URL}/tree/main/docs/gateways/readme.md`, "mdi:router-wireless"],
  ["Lights", `${REPOSITORY_URL}/tree/main/docs/lights-tutorial/readme.md`, "mdi:lightbulb"],
  ["Relays and switches", `${REPOSITORY_URL}/tree/main/docs/relays-and-switches/readme.md`, "mdi:toggle-switch"],
  ["Heating and cooling", `${REPOSITORY_URL}/tree/main/docs/heating-and-cooling/readme.md`, "mdi:thermometer"],
  ["Rocker switches", `${REPOSITORY_URL}/tree/main/docs/rocker_switch/readme.md`, "mdi:gesture-tap-button"],
  ["Teach-in buttons", `${REPOSITORY_URL}/tree/main/docs/teach_in_buttons/readme.md`, "mdi:school-outline"],
  ["Logging", `${REPOSITORY_URL}/tree/main/docs/logging/readme.md`, "mdi:text-box-outline"],
];

/** Settings which are displayed in the configuration section (in this order). */
const SETTING_LABELS = [
  ["fast_status_change", "Fast status change"],
  ["show_dev_id_in_dev_name", "Show device id in device name"],
  ["enable_frontend", "Web ui enabled"],
  ["enable_teach_in_buttons", "Teach-in buttons"],
  ["log_enocean_telegrams", "Record EnOcean telegrams"],
  ["telegram_log_filename", "Telegram log file"],
  ["telegram_log_format", "Telegram log format"],
  ["telegram_log_max_file_size_mb", "Max. log file size (MB)"],
  ["telegram_log_backup_count", "Rotated log files kept"],
  ["telegram_log_include_polling", "Include bus polling telegrams"],
  ["telegram_log_decode_eep", "Decode telegrams of known devices"],
  ["telegram_log_buffer_size", "Live buffer size"],
];

export const page = {
  id: "about",
  title: "About",
  subtitle: "Information about the Home Assistant Eltako integration",
  icon: "mdi:information-outline",
  glyph: "ℹ",

  async load(ctx) {
    await Promise.all([ctx.loadIntegrationInfo(), ctx.loadLogInfo()]);
  },

  render(ctx) {
    const info = ctx.state.integrationInfo || {};
    const entities = info.entities || {};
    const settings = info.general_settings || {};

    return `
      <div class="notice">
        <h3>${escapeHtml(info.name || "Eltako")} &mdash; EnOcean / Eltako Baureihe 14 for Home Assistant</h3>
        <p>This integration connects Eltako series 14 devices (RS485 bus) and EnOcean devices in general to
          Home Assistant. It reads the status of all bus members, controls actuators, exposes sensors and
          rocker switches for automations, and can record and analyse the EnOcean traffic.</p>
        <p>It is a community project (MIT license) and not an official product of Eltako GmbH.</p>
      </div>

      <div class="cards">
        ${card("Integration version", `<span class="mono">${escapeHtml(info.version || "-")}</span>`)}
        ${card("Home Assistant", `<span class="mono">${escapeHtml(info.home_assistant_version || "-")}</span>`)}
        ${card("Gateways", formatNumber((info.gateways || []).length))}
        ${card("Devices", formatNumber(entities.device_count))}
        ${card("Entities", formatNumber(entities.entity_count))}
        ${card("IoT class", escapeHtml(info.iot_class || "-"))}
      </div>

      <h2>Documentation and support</h2>
      <div class="links">
        <a class="link" href="${REPOSITORY_URL}" target="_blank" rel="noreferrer">
          ${icon("mdi:github", "★")} Repository</a>
        ${info.issue_tracker ? `<a class="link" href="${escapeHtml(info.issue_tracker)}" target="_blank" rel="noreferrer">
          ${icon("mdi:bug-outline", "!")} Report an issue</a>` : ""}
        <a class="link" href="https://community.home-assistant.io/t/eltako-baureihe-14-rs485-enocean-debugging/49712"
           target="_blank" rel="noreferrer">${icon("mdi:forum-outline", "☰")} Community forum</a>
        <a class="link" href="https://www.eltako.com/en/software-pct14/" target="_blank" rel="noreferrer">
          ${icon("mdi:tools", "⚙")} Eltako PCT14</a>
        <a class="link" href="https://github.com/grimmpp/enocean-device-manager" target="_blank" rel="noreferrer">
          ${icon("mdi:file-tree", "▤")} EnOcean Device Manager</a>
      </div>

      <h2>Tutorials</h2>
      <div class="links">
        ${DOC_LINKS.map(([label, url, mdi]) =>
          `<a class="link" href="${url}" target="_blank" rel="noreferrer">${icon(mdi)} ${escapeHtml(label)}</a>`).join("")}
      </div>

      <h2>Active configuration</h2>
      <div class="table-wrapper"><table>${definitionRows(
        SETTING_LABELS.filter(([key]) => key in settings).map(([key, label]) =>
          [label, this._renderSettingValue(settings[key])])
      )}</table></div>
      <div class="footnote">These are the effective values of the <code>general_settings</code> section of your
        <code>configuration.yaml</code>. Handy when reporting an issue.</div>

      <h2>Platforms</h2>
      <div class="chips">
        ${["light", "switch", "cover", "climate", "sensor", "binary_sensor", "button", "select"]
          .map((platform) => chip(platform, (entities.count_by_platform || {})[platform] || 0)).join("")}
      </div>

      <h2>Dependencies</h2>
      <div class="chips">${(info.requirements || []).map((requirement) => chip(requirement)).join("")}</div>
      <div class="footnote">The web ui is part of this integration &ndash; no additional package is needed.</div>
    `;
  },

  _renderSettingValue(value) {
    if (typeof value === "boolean") {
      return `<span class="pill ${value ? "on" : ""}">${formatBoolean(value)}</span>`;
    }
    if (value === "" || value === null || value === undefined) return "&ndash; not set &ndash;";
    return `<span class="mono">${escapeHtml(value)}</span>`;
  },
};
