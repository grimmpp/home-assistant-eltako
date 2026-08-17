/** Help page: documentation, tutorials and what this integration supports.
 *
 * Every list on this page is delivered by the backend (eltako/help/catalog), which compiles it
 * from the device catalog, the platform schemas, the EEP registry of eltakobus and the docs
 * directory of the repository. Nothing here is a literal list - a device or an EEP added to the
 * code shows up without touching this file.
 */

import { WS } from "../lib/api.js";
import { card, chip, escapeHtml, formatNumber, icon } from "../lib/utils.js";

const HELP_STYLES = `
  .help-search { margin-bottom: 12px; }
  .help-links { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
  a.help-link {
    display: flex; gap: 10px; align-items: flex-start; text-decoration: none; padding: 12px 14px;
    background: var(--eltako-card); border: 1px solid var(--eltako-border);
    border-radius: var(--eltako-radius); color: var(--primary-text-color);
  }
  a.help-link:hover { border-color: var(--eltako-accent); background: var(--eltako-tint); }
  a.help-link ha-icon, a.help-link .glyph { color: var(--eltako-accent); flex: 0 0 auto; }
  .help-link-title { font-weight: 500; }
  .help-link-text { font-size: .78rem; color: var(--eltako-muted); margin-top: 2px; }
  .help-link-path { font-size: .7rem; color: var(--eltako-muted); font-family: "Roboto Mono", monospace; }
  .help-empty { font-size: .8rem; color: var(--eltako-muted); padding: 10px 0; }
  .help-toc { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 0; padding-left: 20px; }
  .help-toc a, .help-page-doc { color: var(--eltako-accent); }
  .help-page-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                    gap: 10px; }
  .help-page-card { padding: 12px 14px; border: 1px solid var(--eltako-border);
                    border-radius: var(--eltako-radius); background: var(--eltako-card); }
  .help-page-card h3 { margin: 0 0 4px; font-size: .95rem; }
  .help-page-card p { margin: 0 0 7px; font-size: .8rem; color: var(--eltako-muted); }
  .help-page-card .help-page-links { display: flex; flex-wrap: wrap; gap: 5px 10px; font-size: .75rem; }
  /* a cell can hold dozens of chips (the devices of a central command profile), so they
     need room to wrap into several lines */
  td .chip { margin: 2px 4px 2px 0; }
`;

const PAGE_GUIDE = [
  { id: "home", title: "Simple view", icon: "mdi:view-grid-outline",
    text: "Everyday view of your devices, grouped by room. Add devices, edit names and operate them.",
    docs: ["docs/01_getting_started/readme.md"] },
  { id: "overview", title: "Overview", icon: "mdi:view-dashboard-outline",
    text: "Shows gateway connections, bus activity and Plug & Play detection. Start or cancel searches here.",
    docs: ["docs/gateways/readme.md", "docs/plug-and-play/readme.md"] },
  { id: "control", title: "Control", icon: "mdi:remote",
    text: "Standalone-only control panel for operating entities without a Home Assistant dashboard.",
    standaloneOnly: true, docs: ["docs/standalone/readme.md"] },
  { id: "devices", title: "Devices", icon: "mdi:format-list-bulleted",
    text: "Configure devices and gateways, inspect bus relations, teach in senders and import or export YAML.",
    docs: ["docs/update_home_assistant_configuration.md", "docs/supported-devices.md"] },
  { id: "configurations", title: "Configurations", icon: "mdi:folder-cog-outline",
    text: "Standalone-only profiles for switching between test environments or installations, with YAML import and export.",
    standaloneOnly: true, docs: ["docs/standalone/readme.md"] },
  { id: "telegrams", title: "Telegrams", icon: "mdi:message-text-outline",
    text: "Live incoming and outgoing EnOcean telegrams with decoded EEP values and filters.",
    docs: ["docs/telegram-analysis/readme.md"] },
  { id: "radio", title: "Radio", icon: "mdi:radio-tower",
    text: "Compare reception of the same radio telegram across gateways and inspect signal quality.",
    docs: ["docs/reception/readme.md"] },
  { id: "reception", title: "Reception", icon: "mdi:signal",
    text: "Measure gateway reception and identify weak or missing radio paths.",
    docs: ["docs/reception/readme.md"] },
  { id: "statistics", title: "Statistics", icon: "mdi:chart-line",
    text: "Review activity, unknown senders and reporting frequency of configured devices.",
    docs: ["docs/telegram-analysis/readme.md"] },
  { id: "logs", title: "Logs", icon: "mdi:text-box-search-outline",
    text: "Inspect integration log messages and adjust diagnostic log levels.",
    docs: ["docs/logging/readme.md"] },
  { id: "tests", title: "Tests", icon: "mdi:test-tube",
    text: "Run configuration, teach-in, link and cover travel-time tests. Some tests communicate with real hardware.",
    docs: ["docs/device-tests/readme.md"] },
  { id: "simulation", title: "Simulation", icon: "mdi:flask-outline",
    text: "Create virtual gateways and devices for development and testing without hardware.",
    docs: ["docs/simulation/readme.md"] },
  { id: "settings", title: "Settings", icon: "mdi:cog-outline",
    text: "View and change general integration settings. YAML-only values remain controlled by configuration.yaml.",
    docs: ["docs/update_home_assistant_configuration.md"] },
  { id: "about", title: "About", icon: "mdi:information-outline",
    text: "Shows the installed version, supported features, entity counts and release information.",
    docs: ["docs/version-2-introduction.md"] },
];

/** @type {import("../types.js").Page} */
export const page = {
  id: "help",
  title: "Help",
  subtitle: "Documentation, tutorials and everything this integration supports",
  icon: "mdi:help-circle-outline",
  glyph: "?",
  modes: ["user", "expert"],
  styles: HELP_STYLES,

  async load(ctx) {
    const catalog = await ctx.api.call(WS.HELP_CATALOG);
    if (catalog) ctx.state.helpCatalog = catalog;
  },

  render(ctx) {
    const catalog = ctx.state.helpCatalog;
    if (!catalog) return `<div class="empty">Loading the catalog&hellip;</div>`;

    const summary = catalog.summary || {};
    const filter = (ctx.state.helpFilter || "").trim().toLowerCase();

    return `
      <div class="cards">
        ${card("Devices", formatNumber(summary.device_count), "", `${formatNumber(summary.bus_device_count)} of them on the RS485 bus`)}
        ${card("EEP profiles", formatNumber(summary.eep_count), "", `${formatNumber(summary.entity_eep_count)} can become an entity`)}
        ${card("Gateways", formatNumber(summary.gateway_count))}
        ${card("Platforms", formatNumber(summary.platform_count))}
        ${card("Documents", formatNumber(summary.document_count))}
      </div>

      <div class="notice">
        <h3>${icon("mdi:database-search-outline", "▤")} This page is generated</h3>
        <p>The tables below are compiled from the code of the integration &ndash; the device
          catalog, the platform schemas, the profile registry of <code>eltakobus</code> and the
          <code>docs</code> directory. They therefore always describe the version you are
          running, not a list someone kept up to date by hand.</p>
      </div>

      <h2 id="help-contents">Contents</h2>
      <ol class="help-toc">
        <li><a href="#/help" data-help-anchor="help-pages">Panel pages</a></li>
        <li><a href="#/help" data-help-anchor="help-documents">Documentation and tutorials</a></li>
        <li><a href="#/help" data-help-anchor="help-links">External links</a></li>
        <li><a href="#/help" data-help-anchor="help-gateways">Supported gateways</a></li>
        <li><a href="#/help" data-help-anchor="help-platforms">Supported platforms</a></li>
        <li><a href="#/help" data-help-anchor="help-devices">Supported devices</a></li>
        <li><a href="#/help" data-help-anchor="help-eeps">EEP profiles</a></li>
      </ol>

      <h2 id="help-pages">Panel pages</h2>
      <p class="field-help">Select a page in the navigation or use one of the links below. Pages marked
        standalone are available only when running <code>python -m eltako_standalone serve</code>.</p>
      ${this._renderPageGuide(catalog)}

      <h2 id="help-documents">Documentation and tutorials</h2>
      ${this._renderDocuments(catalog)}

      <h2 id="help-links">Links</h2>
      <div class="help-links">
        ${(catalog.links || []).map((link) => `
          <a class="help-link" href="${escapeHtml(link.url)}" target="_blank" rel="noreferrer">
            ${icon(link.icon || "mdi:open-in-new", "→")}
            <span>
              <span class="help-link-title">${escapeHtml(link.title)}</span>
              <span class="help-link-text">${escapeHtml(link.description || "")}</span>
            </span>
          </a>`).join("")}
      </div>

      <h2 id="help-gateways">Supported gateways</h2>
      ${this._renderGateways(catalog)}

      <h2 id="help-platforms">Supported platforms</h2>
      ${this._renderPlatforms(catalog)}

      <h2 id="help-devices">Supported devices</h2>
      <div class="toolbar help-search">
        <input type="search" id="help-filter" placeholder="Filter devices and EEPs&hellip;"
               value="${escapeHtml(ctx.state.helpFilter || "")}">
        <span class="field-help">Matches the device name, its description, brand and EEP.</span>
      </div>
      ${this._renderDevices(catalog, filter)}

      <h2 id="help-eeps">EEP profiles</h2>
      ${this._renderEeps(catalog, filter)}
    `;
  },

  _renderDocuments(catalog) {
    const documents = catalog.documentation || [];
    if (!documents.length) {
      return `<div class="help-empty">The <code>docs</code> directory is not part of this
        installation. The documentation is in the
        <a href="${escapeHtml(catalog.repository)}/tree/main/docs" target="_blank" rel="noreferrer">repository</a>.</div>`;
    }

    return `<div class="help-links">
      ${documents.map((document) => `
        <a class="help-link" href="${escapeHtml(document.url)}" target="_blank" rel="noreferrer">
          ${icon("mdi:book-open-variant", "▤")}
          <span>
            <span class="help-link-title">${escapeHtml(document.title)}</span>
            <span class="help-link-path">${escapeHtml(document.path)}</span>
          </span>
        </a>`).join("")}
    </div>`;
  },

  _renderPageGuide(catalog) {
    const standalone = typeof window !== "undefined" && window.eltakoStandalone;
    const pages = PAGE_GUIDE.filter((page) => !page.standaloneOnly || standalone);
    return `<div class="help-page-grid">${pages.map((page) => `
      <div class="help-page-card">
        <h3>${icon(page.icon, "▤")} <a href="#/${page.id}">${escapeHtml(page.title)}</a></h3>
        <p>${escapeHtml(page.text)}</p>
        <div class="help-page-links">
          <a href="#/${page.id}">Open page</a>
          ${page.docs.map((path) => {
            const document = (catalog.documentation || []).find((entry) => entry.path === path);
            return document ? `<a class="help-page-doc" href="${escapeHtml(document.url)}"
              target="_blank" rel="noreferrer">${escapeHtml(document.title)}</a>` : "";
          }).join("")}
        </div>
      </div>`).join("")}</div>`;
  },

  _renderGateways(catalog) {
    const gateways = catalog.gateways || [];
    if (!gateways.length) return `<div class="help-empty">No gateway types.</div>`;

    return `<div class="table-wrapper"><table>
      <thead><tr>
        <th>Type</th><th>Hardware</th><th>Brand</th><th>Protocol</th><th>Connection</th><th></th>
      </tr></thead>
      <tbody>
        ${gateways.map((gateway) => `
          <tr>
            <td class="mono">${escapeHtml(gateway.gateway_type)}
              <span class="hint">${escapeHtml(gateway.description || "")}</span></td>
            <td>${escapeHtml(gateway.hw_type || "&ndash;")}</td>
            <td>${escapeHtml(gateway.brand || "&ndash;")}</td>
            <td><span class="chip">${escapeHtml(gateway.protocol)}</span></td>
            <td>
              ${gateway.bus_gateway ? `<span class="chip">RS485 bus</span>` : ""}
              ${gateway.lan ? `<span class="chip">network</span>` : ""}
              ${gateway.transceiver ? `<span class="chip">radio</span>` : ""}
            </td>
            <td>${gateway.docs ? `<a class="pill link" href="${escapeHtml(gateway.docs)}"
                   target="_blank" rel="noreferrer">docs</a>` : ""}</td>
          </tr>`).join("")}
      </tbody></table></div>`;
  },

  _renderPlatforms(catalog) {
    const platforms = catalog.platforms || [];
    if (!platforms.length) return `<div class="help-empty">No platforms.</div>`;

    return `<div class="table-wrapper"><table>
      <thead><tr><th>Platform</th><th>Device EEPs</th><th>Sender EEPs</th></tr></thead>
      <tbody>
        ${platforms.map((platform) => `
          <tr>
            <td><b>${escapeHtml(platform.platform)}</b>
              ${platform.description ? `<span class="hint">${escapeHtml(platform.description)}</span>` : ""}</td>
            <td>${platform.eeps.map((eep) => chip(eep)).join("") || "&ndash;"}</td>
            <td>${platform.sender_eeps.length
                  ? platform.sender_eeps.map((eep) => chip(eep)).join("")
                  : `<span class="hint">receive only</span>`}</td>
          </tr>`).join("")}
      </tbody></table></div>`;
  },

  _renderDevices(catalog, filter) {
    const devices = (catalog.devices || []).filter((device) => this._matchesDevice(device, filter));
    if (!devices.length) return `<div class="help-empty">No device matches the filter.</div>`;

    return `<div class="table-wrapper"><table>
      <thead><tr>
        <th>Device</th><th>Brand</th><th>Description</th><th>Profiles</th>
        <th class="num">Addresses</th><th>Mounting</th>
      </tr></thead>
      <tbody>
        ${devices.map((device) => `
          <tr>
            <td class="mono">${escapeHtml(device.hw_type)}</td>
            <td>${escapeHtml(device.brand || "&ndash;")}</td>
            <td>${escapeHtml(device.description || "")}</td>
            <td>${device.profiles.length
                  ? device.profiles.map((profile) => `<span class="chip">${escapeHtml(profile.eep)}${
                      profile.platform ? ` &rarr; ${escapeHtml(profile.platform)}` : ""}</span>`).join("")
                  : (device.is_gateway ? `<span class="hint">gateway</span>` : "&ndash;")}</td>
            <td class="num">${device.address_count ? formatNumber(device.address_count) : "&ndash;"}</td>
            <td>${device.bus_device ? `<span class="chip">RS485 bus</span>` : `<span class="chip">radio</span>`}</td>
          </tr>`).join("")}
      </tbody></table></div>`;
  },

  _renderEeps(catalog, filter) {
    const eeps = (catalog.eeps || []).filter((eep) => this._matchesEep(eep, filter));
    if (!eeps.length) return `<div class="help-empty">No EEP matches the filter.</div>`;

    return `<div class="table-wrapper"><table>
      <thead><tr>
        <th>EEP</th><th>Description</th><th>Platforms</th><th>Usable as sender</th><th>Devices</th>
      </tr></thead>
      <tbody>
        ${eeps.map((eep) => `
          <tr>
            <td class="mono">${escapeHtml(eep.eep)}
              ${eep.decodable ? "" : `<span class="hint">not decodable by the installed eltakobus</span>`}</td>
            <td>${escapeHtml(eep.description || "")}</td>
            <td>${eep.platforms.length
                  ? eep.platforms.map((platform) => chip(platform)).join("")
                  : `<span class="hint">recording and analysis only</span>`}</td>
            <td>${eep.sender_platforms.length
                  ? eep.sender_platforms.map((platform) => chip(platform)).join("") : "&ndash;"}</td>
            <td>${eep.devices.length
                  ? eep.devices.map((device) => `<span class="chip">${escapeHtml(device)}</span>`).join("")
                  : "&ndash;"}</td>
          </tr>`).join("")}
      </tbody></table></div>`;
  },

  _matchesDevice(device, filter) {
    if (!filter) return true;
    return [device.hw_type, device.brand, device.description,
            ...device.profiles.map((profile) => profile.eep),
            ...device.platforms]
      .filter(Boolean).join(" ").toLowerCase().includes(filter);
  },

  _matchesEep(eep, filter) {
    if (!filter) return true;
    return [eep.eep, eep.description, ...eep.platforms, ...eep.devices]
      .filter(Boolean).join(" ").toLowerCase().includes(filter);
  },

  afterRender(ctx, root) {
    root.querySelectorAll("[data-help-anchor]").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        root.getElementById(link.dataset.helpAnchor)?.scrollIntoView({ behavior: "smooth" });
      });
    });
    const search = /** @type {HTMLInputElement} */ (root.getElementById("help-filter"));
    if (!search) return;

    search.addEventListener("input", () => {
      ctx.state.helpFilter = search.value;
      // keep the cursor in the field: only the tables below are re-rendered
      ctx.requestContentRender(true);
      const again = /** @type {HTMLInputElement} */ (ctx.root
        ? ctx.root.getElementById("help-filter") : root.getElementById("help-filter"));
      if (again && again !== search) {
        again.focus();
        again.setSelectionRange(again.value.length, again.value.length);
      }
    });
  },
};
