/** Settings page: the general settings of the integration, editable.
 *
 * Values stored here are overrides which win over `configuration.yaml`, so the integration can
 * be configured without writing yaml. Which settings exist, how they are grouped, their type
 * and their range all come from the backend (eltako/settings/get) - this page only renders
 * what it is given.
 */

import { WS } from "../lib/api.js";
import { FORM_STYLES, readFields, renderFields } from "../lib/form.js";
import { escapeHtml, icon } from "../lib/utils.js";

export const page = {
  id: "settings",
  title: "Settings",
  subtitle: "General settings of the integration - they override configuration.yaml",
  icon: "mdi:cog-outline",
  glyph: "⚙",
  styles: FORM_STYLES,

  async load(ctx) {
    const settings = await ctx.api.call(WS.SETTINGS_GET);
    if (settings) ctx.state.settingsForm = settings;
    await ctx.loadIntegrationInfo();
  },

  render(ctx) {
    const form = ctx.state.settingsForm;
    if (!form) return `<div class="empty">Loading settings&hellip;</div>`;

    // locked settings are excluded: resetting them is refused by the backend, and the count
    // next to the button has to match what it will actually do
    const overridden = form.settings.filter((setting) => setting.origin === "ui" && !setting.locked).length;
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
      <div class="footnote">${icon("mdi:information-outline", "i")} Changes are applied immediately:
        the telegram logger is restarted and the gateways are reloaded. Settings marked
        accordingly need a restart of Home Assistant.</div>`;
  },

  _renderGroup(ctx, form, group) {
    const settings = form.settings.filter((setting) => (group.id === null ? true : setting.group === group.id));
    if (!settings.length) return "";

    const fields = settings.map((setting) => ({
      name: setting.name,
      label: setting.label,
      type: setting.type,
      options: setting.options,
      min: setting.min,
      max: setting.max,
      // locked settings are shown greyed out - the backend refuses to change them anyway
      disabled: setting.locked === true,
      help: [
        setting.help || "",
        setting.origin === "ui"
          ? `Overridden here. Without it: ${this._formatValue(setting.fallback)} (${setting.fallback_origin}).`
          : setting.origin === "yaml" ? "Currently from configuration.yaml."
          : "Currently the default value.",
        setting.restart_required && !setting.locked ? "Takes effect after a restart of Home Assistant." : "",
      ].filter(Boolean).join(" "),
    }));
    const values = Object.fromEntries(settings.map((setting) => [setting.name, setting.value]));
    const overriddenHere = settings.filter((setting) => setting.origin === "ui" && !setting.locked);

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
          // changed settings take effect without reloading the page: the navigation
          // (pages can be hidden by a setting) and the header re-render as well
          await ctx.loadIntegrationInfo();
          ctx.requestRender();
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
          await ctx.loadIntegrationInfo();
          ctx.requestRender();
        }
        ctx.requestContentRender(true);
      });
    });

    const resetAll = root.getElementById("settings-reset-all");
    if (resetAll) {
      resetAll.addEventListener("click", async () => {
        const names = (ctx.state.settingsForm.settings || [])
          .filter((setting) => setting.origin === "ui" && !setting.locked).map((setting) => setting.name);
        const result = await ctx.api.call(WS.SETTINGS_RESET, { names });
        if (result) {
          ctx.state.settingsForm = result.form;
          ctx.state.settingsMessage = `Reset ${result.reset.length} override(s).`;
          ctx.state.settingsError = null;
          await ctx.loadIntegrationInfo();
          ctx.requestRender();
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
};
