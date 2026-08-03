/** About page: information about the integration itself, its configuration and links. */

import { WS } from "../lib/api.js";
import { FORM_STYLES, readFields, renderFields } from "../lib/form.js";
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
  styles: FORM_STYLES,

  async load(ctx) {
    const [settings] = await Promise.all([
      ctx.api.call(WS.SETTINGS_GET), ctx.loadIntegrationInfo(), ctx.loadLogInfo(),
    ]);
    if (settings) ctx.state.settingsForm = settings;
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
      ${this._renderSettings(ctx)}

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

  /** Editable general settings, grouped. Values changed here override configuration.yaml. */
  _renderSettings(ctx) {
    const form = ctx.state.settingsForm;
    if (!form) return `<div class="empty">Loading settings&hellip;</div>`;

    const overridden = form.settings.filter((s) => s.origin === "ui").length;
    const groups = form.groups && form.groups.length
      ? form.groups
      : [{ id: null, label: "Settings", help: "" }];

    return `
      <div class="settings-head">
        <div>
          <b>These values are live.</b> Changing them here stores an override which wins over
          <code>configuration.yaml</code>, so the integration can be configured without writing yaml.
          ${form.has_yaml_section ? "" : "Your configuration.yaml has no <code>general_settings</code> section - everything below comes from the defaults."}
        </div>
        <div class="settings-legend">
          <span class="tag source-ui">web ui</span> overrides
          <span class="tag source-yaml">yaml</span> from configuration.yaml
          <span class="tag">default</span>
        </div>
      </div>

      <div id="settings-form">
        ${groups.map((group) => this._renderGroup(ctx, form, group)).join("")}
      </div>

      ${ctx.state.settingsError ? `<div class="form-error">${escapeHtml(ctx.state.settingsError)}</div>` : ""}
      ${ctx.state.settingsMessage ? `<div class="settings-ok">${escapeHtml(ctx.state.settingsMessage)}</div>` : ""}
      <div class="form-actions">
        <button id="settings-save" class="action primary">Save settings</button>
        ${overridden ? `<button id="settings-reset-all" class="action">Reset all ${overridden} override${overridden === 1 ? "" : "s"}</button>` : ""}
        <span class="field-help">Read only: teach-in buttons =
          ${this._formatValue((form.read_only || {}).enable_teach_in_buttons)} (derived at runtime)</span>
      </div>
      <div class="footnote">Changes are applied immediately: the telegram logger is restarted and the
        gateways are reloaded. Settings marked accordingly need a restart of Home Assistant.</div>`;
  },

  _renderGroup(ctx, form, group) {
    const settings = form.settings.filter((s) => (group.id === null ? true : s.group === group.id));
    if (!settings.length) return "";

    const fields = settings.map((setting) => ({
      name: setting.name,
      label: setting.label,
      type: setting.type,
      options: setting.options,
      min: setting.min,
      max: setting.max,
      help: [
        setting.help || "",
        setting.origin === "ui"
          ? `Overridden here. Without it: ${this._formatValue(setting.fallback)} (${setting.fallback_origin}).`
          : setting.origin === "yaml" ? "Currently from configuration.yaml."
          : "Currently the default value.",
        setting.restart_required ? "Takes effect after a restart of Home Assistant." : "",
      ].filter(Boolean).join(" "),
    }));
    const values = Object.fromEntries(settings.map((s) => [s.name, s.value]));
    const overriddenHere = settings.filter((s) => s.origin === "ui");

    return `
      <div class="form-card">
        <h3>${escapeHtml(group.label)}</h3>
        ${group.help ? `<div class="field-help" style="margin:-6px 0 12px">${escapeHtml(group.help)}
          ${group.id === "log_levels" ? `Logger: <code>${escapeHtml(form.telegram_logger_name || "eltako.telegrams")}</code>` : ""}</div>` : ""}
        <div class="form-grid">${renderFields(fields, values)}</div>
        ${overriddenHere.length ? `
          <div class="origins">
            ${overriddenHere.map((setting) => `
              <span class="origin-row">
                <span class="tag source-ui">web ui</span>
                <span class="origin-name">${escapeHtml(setting.label)}</span>
                <button class="action small" data-reset="${escapeHtml(setting.name)}">reset</button>
              </span>`).join("")}
          </div>` : ""}
      </div>`;
  },

  afterRender(ctx, root) {
    const save = root.getElementById("settings-save");
    if (save) {
      save.addEventListener("click", async () => {
        const values = readFields(root.getElementById("settings-form"));
        // unchecked checkboxes and emptied text fields must be sent explicitly
        const form = ctx.state.settingsForm || { settings: [] };
        const payload = {};
        for (const setting of form.settings) {
          if (setting.type === "boolean") payload[setting.name] = values[setting.name] === true;
          else if (setting.name in values) payload[setting.name] = values[setting.name];
          else payload[setting.name] = setting.type === "text" ? "" : setting.value;
        }

        const result = await ctx.api.call(WS.SETTINGS_SET, { settings: payload });
        if (result) {
          ctx.state.settingsForm = result.form;
          ctx.state.settingsError = null;
          ctx.state.settingsMessage = `Saved. Telegram logger restarted: ${result.applied.telegram_logger_restarted ? "yes" : "no"}, gateways reloaded: ${result.applied.reloaded_gateways}.`;
        } else {
          ctx.state.settingsError = (ctx.api.lastError || {}).message || "Could not save the settings.";
          ctx.state.settingsMessage = null;
          ctx.api.lastError = null;
        }
        ctx.requestContentRender(true);
      });
    }

    root.querySelectorAll("button[data-reset]").forEach((button) => {
      button.addEventListener("click", async () => {
        const result = await ctx.api.call(WS.SETTINGS_RESET, { names: [button.dataset.reset] });
        if (result) {
          ctx.state.settingsForm = result.form;
          ctx.state.settingsMessage = `Reset ${result.reset.join(", ")} to the configuration.yaml/default value.`;
          ctx.state.settingsError = null;
        }
        ctx.requestContentRender(true);
      });
    });

    const resetAll = root.getElementById("settings-reset-all");
    if (resetAll) {
      resetAll.addEventListener("click", async () => {
        const names = (ctx.state.settingsForm.settings || []).filter((s) => s.origin === "ui").map((s) => s.name);
        const result = await ctx.api.call(WS.SETTINGS_RESET, { names });
        if (result) {
          ctx.state.settingsForm = result.form;
          ctx.state.settingsMessage = `Reset ${result.reset.length} override(s).`;
          ctx.state.settingsError = null;
        }
        ctx.requestContentRender(true);
      });
    }
  },

  _formatValue(value) {
    if (typeof value === "boolean") return value ? "yes" : "no";
    if (value === "" || value === null || value === undefined) return "not set";
    return String(value);
  },

  _renderSettingValue(value) {
    if (typeof value === "boolean") {
      return `<span class="pill ${value ? "on" : ""}">${formatBoolean(value)}</span>`;
    }
    if (value === "" || value === null || value === undefined) return "&ndash; not set &ndash;";
    return `<span class="mono">${escapeHtml(value)}</span>`;
  },
};
