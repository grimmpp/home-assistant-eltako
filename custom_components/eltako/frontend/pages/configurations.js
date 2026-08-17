/** Standalone configuration storage and profile browser. */

import { WS } from "../lib/api.js";
import { escapeHtml } from "../lib/utils.js";

const styles = `
  .config-storage-card { padding: 12px 14px; }
  .config-storage { display: flex; gap: 8px; align-items: end; flex-wrap: wrap; }
  .config-storage label { flex: 0 1 560px; min-width: 260px; }
  .config-storage input { width: 100%; box-sizing: border-box; height: 34px; }
  .config-storage-card .field-help { display: block; margin-top: 7px; }
  .config-row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  .config-row .config-summary { flex: 1 1 360px; min-width: 240px; }
  .config-row .config-actions { display: flex; gap: 6px; flex-wrap: wrap; }
  .config-description { color: var(--eltako-muted); margin-top: 4px; }
  .config-stats { color: var(--eltako-muted); font-size: .78rem; margin-top: 4px; }
  .config-dialog { position: fixed; inset: 8% 8%; z-index: 10; overflow: auto;
    background: var(--eltako-card); border: 1px solid var(--eltako-border);
    border-radius: var(--eltako-radius); padding: 18px; box-shadow: 0 12px 40px #0006; }
  .config-dialog pre { white-space: pre-wrap; overflow: auto; max-height: 65vh;
    background: var(--eltako-bg); padding: 12px; border-radius: 6px; }
  .config-loading { position: fixed; inset: 0; z-index: 20; display: grid; place-items: center;
    background: color-mix(in srgb, var(--eltako-bg) 88%, transparent); }
  .config-loading-card { min-width: 280px; max-width: 460px; text-align: center;
    background: var(--eltako-card); border: 1px solid var(--eltako-border);
    border-radius: var(--eltako-radius); padding: 24px; box-shadow: 0 12px 40px #0006; }
  .config-spinner { width: 28px; height: 28px; margin: 0 auto 14px;
    border: 3px solid var(--eltako-border); border-top-color: var(--eltako-accent);
    border-radius: 50%; animation: config-spin .8s linear infinite; }
  @keyframes config-spin { to { transform: rotate(360deg); } }
`;

function countText(item) {
  const platforms = Object.entries(item.platforms || {})
    .map(([name, count]) => `${count} ${name}`).join(", ");
  return `${item.gateways || 0} gateway(s), ${item.devices || 0} device(s)`
    + (platforms ? ` (${platforms})` : "");
}

export const page = {
  id: "configurations",
  title: "Configurations",
  subtitle: "Browse, save and switch standalone configurations",
  icon: "mdi:folder-cog-outline",
  glyph: "▣",
  standaloneOnly: true,
  modes: ["expert"],
  refreshMs: 10000,
  styles,

  async load(ctx) {
    if (ctx.state.browserConfigurationDirectory) {
      await this._readBrowserFolder(ctx);
      return;
    }
    const result = await ctx.api.call(WS.STANDALONE_CONFIG_LIST);
    if (!result) return;
    ctx.state.standaloneConfigurations = result.configurations || [];
    ctx.state.standaloneStorageDir = result.storage_dir || "";
  },

  render(ctx) {
    const configurations = ctx.state.standaloneConfigurations || [];
    const details = ctx.state.standaloneConfigurationDetails;
    const browserFolder = ctx.state.browserConfigurationDirectory;
    return `<div class="card config-storage-card">
      <div class="card-title">Configuration storage</div>
      <div class="config-storage">
      <label>Standard storage folder
        <input id="config-storage-dir" value="${escapeHtml(browserFolder?.name || ctx.state.standaloneStorageDir || "")}" ${browserFolder ? "disabled" : ""}>
      </label>
        <button id="config-storage-pick" class="action">Choose folder&hellip;</button>
        <button id="config-storage-save" class="action" ${browserFolder ? "disabled" : ""}>Use folder</button>
      </div>
      <small class="field-help">${browserFolder ? "Browser-managed folder selected." : "Default: repository folder <code>standalone_configurations</code>."}</small>
    </div>
    <div class="cards"><div class="card"><div class="card-title">Known configurations</div>
      <div class="card-value">${configurations.length}</div>
      <small>${escapeHtml(ctx.state.standaloneStorageDir || "")}</small></div></div>
    <div class="notice">Descriptions are read from the top-level YAML field <code>description</code>.
      The summary counts gateways, devices and platforms without changing the configuration.</div>
    <div class="list"><div class="row config-row">
      <div class="config-summary"><strong>Empty configuration</strong>
        <div class="config-description">Start with the integration enabled but without gateways or devices.</div>
        <div class="config-stats">0 gateway(s), 0 device(s)</div>
      </div>
      <div class="config-actions">
        <button id="config-load-empty" class="action">Load</button>
      </div>
    </div>${configurations.map((item) => `<div class="row config-row">
      <div class="config-summary"><strong>${escapeHtml(item.name)}</strong>
        <small> &middot; ${escapeHtml(item.filename || item.path || "")}</small>
        <div class="config-description">${escapeHtml(item.description || "No description provided.")}</div>
        <div class="config-stats">${escapeHtml(countText(item))}</div>
      </div>
      <div class="config-actions">
        <button class="action" data-config-load="${escapeHtml(item.filename || "")}" data-config-browser="${item.browser ? "true" : "false"}">Load</button>
        <button class="action" data-config-save-as="${escapeHtml(item.name)}">Save as</button>
        <button class="action" data-config-details="${escapeHtml(item.filename || "")}" data-config-browser="${item.browser ? "true" : "false"}">View details</button>
        <button class="action danger" data-config-delete="${escapeHtml(item.filename || "")}" data-config-browser="${item.browser ? "true" : "false"}">Delete</button>
      </div>
    </div>`).join("") || "<div class=\"notice\">No YAML configurations found.</div>"}</div>
    <div class="actions"><button id="config-save" class="action">Save current YAML as&hellip;</button>
      <button id="config-import" class="action">Import YAML&hellip;</button>
      <input id="config-file" type="file" accept=".yaml,.yml,.txt" hidden>
      <button id="config-export" class="action">Export active YAML</button></div>
    ${details ? `<div class="config-dialog" role="dialog" aria-label="Configuration details">
      <div class="card-title">${escapeHtml(details.filename)}</div>
      <div class="config-description">${escapeHtml(details.description || "No description provided.")}</div>
      <pre>${escapeHtml(details.content || "")}</pre>
      <button id="config-details-close" class="action">Close</button>
    </div>` : ""}
    ${ctx.state.configurationLoading ? `<div class="config-loading" role="alert" aria-live="polite">
      <div class="config-loading-card"><div class="config-spinner"></div>
        <div class="card-title">Loading configuration&hellip;</div>
        <p>Please wait until the runtime has restarted and all gateways and entities are loaded.</p>
      </div>
    </div>` : ""}`;
  },

  bind(ctx, root) {
    root.getElementById("config-storage-pick")?.addEventListener("click", async () => {
      if (!window.showDirectoryPicker) {
        alert("This browser does not support native directory selection. Use the server path field instead.");
        return;
      }
      try {
        ctx.state.browserConfigurationDirectory = await window.showDirectoryPicker({ mode: "readwrite" });
        await this._readBrowserFolder(ctx);
        ctx.requestRender();
      } catch (error) {
        if (error?.name !== "AbortError") alert(`Could not select the folder: ${error.message}`);
      }
    });
    root.getElementById("config-storage-save")?.addEventListener("click", async () => {
      const path = root.getElementById("config-storage-dir").value.trim();
      if (!path) return;
      const result = await ctx.api.call(WS.STANDALONE_CONFIG_STORAGE, { path });
      if (result) {
        ctx.state.standaloneStorageDir = result.storage_dir;
        ctx.state.standaloneConfigurations = result.configurations || [];
        ctx.requestRender();
      }
    });
    root.getElementById("config-load-empty")?.addEventListener("click", async () => {
      if (!confirm("Load an empty configuration?\n\nThe runtime will restart and remove all gateways and devices.")) return;
      ctx.state.configurationLoading = true;
      ctx.requestRender();
      const result = await ctx.api.call(WS.STANDALONE_CONFIG_LOAD_EMPTY);
      if (result) { window.location.reload(); return; }
      ctx.state.configurationLoading = false;
      ctx.requestRender();
    });
    root.querySelectorAll("[data-config-load]").forEach((button) => {
      button.addEventListener("click", async () => {
        const filename = button.dataset.configLoad;
        if (!filename || !confirm(`Load '${filename}' as the active configuration?\n\nThe runtime will restart and remove all previously UI-created entities and gateways. Only this configuration will be used.`)) return;
        ctx.state.configurationLoading = true;
        ctx.requestRender();
        const result = button.dataset.configBrowser === "true"
          ? await ctx.api.call(WS.STANDALONE_CONFIG_LOAD_CONTENT, {
            filename, content: ctx.state.browserConfigurationContents?.[filename] || "" })
          : await ctx.api.call(WS.STANDALONE_CONFIG_LOAD, { filename });
        if (result) window.location.reload();
        ctx.state.configurationLoading = false;
        ctx.requestRender();
      });
    });
    root.querySelectorAll("[data-config-save-as]").forEach((button) => {
      button.addEventListener("click", async () => {
        const name = prompt("Save the current configuration as:", button.dataset.configSaveAs);
        if (!name) return;
        const result = await this._saveAs(ctx, name);
        if (result) { await this.load(ctx); ctx.requestRender(); }
      });
    });
    root.querySelectorAll("[data-config-details]").forEach((button) => {
      button.addEventListener("click", async () => {
        const result = button.dataset.configBrowser === "true"
          ? { filename: button.dataset.configDetails,
              content: ctx.state.browserConfigurationContents?.[button.dataset.configDetails] || "",
              description: ctx.state.standaloneConfigurations.find((item) =>
                item.filename === button.dataset.configDetails)?.description || "" }
          : await ctx.api.call(WS.STANDALONE_CONFIG_DETAILS,
                               { filename: button.dataset.configDetails });
        if (result) { ctx.state.standaloneConfigurationDetails = result; ctx.requestRender(); }
      });
    });
    root.querySelectorAll("[data-config-delete]").forEach((button) => {
      button.addEventListener("click", async () => {
        const filename = button.dataset.configDelete;
        if (!filename || !confirm(`Delete '${filename}' permanently?`)) return;
        let result;
        if (button.dataset.configBrowser === "true") {
          await ctx.state.browserConfigurationDirectory.removeEntry(filename);
          result = { deleted: true };
        } else {
          result = await ctx.api.call(WS.STANDALONE_CONFIG_DELETE, { filename });
        }
        if (result) { await this.load(ctx); ctx.requestRender(); }
      });
    });
    root.getElementById("config-details-close")?.addEventListener("click", () => {
      ctx.state.standaloneConfigurationDetails = null;
      ctx.requestRender();
    });
    root.getElementById("config-save")?.addEventListener("click", () => this._save(ctx));
    root.getElementById("config-export")?.addEventListener("click", async () => {
      const result = await ctx.api.call(WS.STANDALONE_CONFIG_EXPORT);
      if (result) this._download(result);
    });
    const file = root.getElementById("config-file");
    root.getElementById("config-import")?.addEventListener("click", () => file.click());
    file?.addEventListener("change", async () => {
      const selected = file.files?.[0]; file.value = "";
      if (!selected) return;
      const name = prompt("Name for this configuration:", selected.name.replace(/\.[^.]+$/, ""));
      if (!name) return;
      const content = await selected.text();
      const result = ctx.state.browserConfigurationDirectory
        ? await this._writeBrowserFile(ctx, `${name}.yaml`, content)
        : await ctx.api.call(WS.STANDALONE_CONFIG_IMPORT, { name, content });
      if (result) { await this.load(ctx); ctx.requestRender(); }
    });
  },

  async _readBrowserFolder(ctx) {
    const handle = ctx.state.browserConfigurationDirectory;
    if (!handle) return;
    const configurations = [];
    const contents = {};
    for await (const [name, entry] of handle.entries()) {
      if (entry.kind !== "file" || !/\.(yaml|yml)$/i.test(name)) continue;
      const content = await (await entry.getFile()).text();
      const description = content.match(/^description:\s*["']?([^"'\n]+)["']?\s*$/mi)?.[1]?.trim() || "";
      configurations.push({ name: name.replace(/\.(yaml|yml)$/i, ""), filename: name,
        browser: true, description, gateways: 0, devices: 0, platforms: {} });
      contents[name] = content;
    }
    configurations.sort((a, b) => a.name.localeCompare(b.name));
    ctx.state.browserConfigurationContents = contents;
    ctx.state.standaloneConfigurations = configurations;
    ctx.state.standaloneStorageDir = handle.name;
  },

  async _writeBrowserFile(ctx, filename, content) {
    const handle = await ctx.state.browserConfigurationDirectory.getFileHandle(filename, { create: true });
    const writable = await handle.createWritable();
    await writable.write(content);
    await writable.close();
    await this._readBrowserFolder(ctx);
    return { saved: true };
  },

  async _saveAs(ctx, name) {
    if (ctx.state.browserConfigurationDirectory) {
      const result = await ctx.api.call(WS.STANDALONE_CONFIG_EXPORT);
      return result ? this._writeBrowserFile(ctx, `${name}.yaml`, result.content) : null;
    }
    return ctx.api.call(WS.STANDALONE_CONFIG_SAVE, { name });
  },

  async _save(ctx) {
    const name = prompt("Name for the saved YAML configuration:");
    if (!name) return;
    const result = await this._saveAs(ctx, name);
    if (result) { await this.load(ctx); ctx.requestRender(); }
  },

  _download(result) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([result.content], { type: "application/yaml" }));
    link.download = result.filename || "eltako-configuration.yaml";
    link.click();
    URL.revokeObjectURL(link.href);
  },
};
