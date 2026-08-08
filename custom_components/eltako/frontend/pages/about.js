/** About page: what this integration is, which version runs and what it can do.
 *
 * The documentation and the catalog of supported devices live on the help page, the editable
 * general settings on the settings page - this one stays a profile of the running installation.
 */

import { card, chip, escapeHtml, formatNumber, icon } from "../lib/utils.js";

const REPOSITORY_URL = "https://github.com/grimmpp/home-assistant-eltako";

const DOCS_URL = `${REPOSITORY_URL}/tree/main/docs`;

/**
 * Feature list of the integration, grouped by topic.
 *
 * `doc` is appended to the docs folder of the repository, `setting` names a general setting the
 * feature depends on - its live state is shown next to the entry, so the page answers "can I do
 * this?" and "is it switched on here?" at the same time.
 */
const FEATURE_GROUPS = [
  {
    label: "Gateways and connection", mdi: "mdi:router-wireless", glyph: "((‧))",
    doc: "gateways/readme.md",
    items: [
      { title: "Series 14 bus gateways",
        text: "FAM14, FGW14-USB and FTD14 over USB/RS485 - the status of every actuator on the bus is read and kept in sync." },
      { title: "Wireless transceivers",
        text: "FAM-USB (ESP2) and USB300 / ESP3 sticks; ESP3 telegrams are translated transparently, including the signal strength (RSSI)." },
      { title: "LAN gateways",
        text: "MGW-LAN, EUL gateway and any ESP2 gateway published over tcp (ser2net/socat, <code>lan-gw-esp2</code>) - no usb pass-through needed." },
      { title: "Several gateways in parallel",
        text: "Gateways on the same bus and devices taught into more than one gateway are supported; every command is repeated with the sender of each gateway.",
        doc: "gateway_usage/readme.md" },
      { title: "Survives re-plugging and restarts",
        text: "Auto-reconnect, the base id is queried from the hardware, and a renumbered <code>/dev/ttyUSB*</code> is found again by the usb serial number." },
      { title: "Gateways as repeater",
        text: "The repeater mode (off / level 1 / level 2) of a gateway can be switched from Home Assistant." },
      { title: "Reverse network bridge",
        text: "Publishes a connected gateway on the network so that the EnOcean Device Manager can use it while Home Assistant keeps running." },
    ],
  },
  {
    label: "Devices and entities", mdi: "mdi:lightbulb-group-outline", glyph: "◈",
    items: [
      { title: "All relevant Home Assistant platforms",
        text: "light (switchable and dimmable), switch, cover (incl. tilt), climate, sensor, binary_sensor, button and select." },
      { title: "Configuration in the web ui or in yaml",
        text: "Devices can be created in the web ui and are stored with their gateway; <code>configuration.yaml</code> keeps working and always wins.",
        doc: "update_home_assistant_configuration.md" },
      { title: "Plug &amp; play detection",
        text: "Unused serial ports are probed for gateways, a new bus gateway gets its bus read and every unambiguously identified device is added automatically.",
        doc: "plug-and-play/readme.md", setting: "plug_and_play" },
      { title: "Device catalog as template",
        text: "Selecting a known device (e.g. FSR14_4x) prefills device EEP, sender EEP, the number of addresses and the PCT14 teach-in position." },
      { title: "Teach-in buttons",
        text: "One button entity per actuator sends the teach-in telegram, so a sender can be taught in from Home Assistant.",
        doc: "teach_in_buttons/readme.md", setting: "enable_teach_in_buttons" },
      { title: "Areas and state restore",
        text: "Devices are assigned to an area (new ones are created automatically) and their last state is restored after a restart." },
    ],
  },
  {
    label: "Insight into the RS485 bus", mdi: "mdi:file-tree", glyph: "▤",
    items: [
      { title: "Passive detection of all bus members",
        text: "Polling, status answers and discovery replies are aggregated into a hierarchical table of all bus positions - no bus lock, no scan." },
      { title: "Active bus scan with memory read-out",
        text: "Reads the memory of every device at its own pace and shows which senders are taught into which channel with which key function." },
      { title: "Check and teach in HA senders",
        text: "Compares the configured sender ids against the device memories and writes the missing ones (standard procedure of the EnOcean Device Manager)." },
      { title: "Long term activity per address",
        text: "How often an address reported, when it was heard from last and over how many sessions - devices which never reported are highlighted." },
      { title: "Take over unconfigured devices",
        text: "A device found on the bus, in a memory image or in the telegram stream can be added with one click, prefilled with address and EEP." },
    ],
  },
  {
    label: "Telegram analysis", mdi: "mdi:file-search-outline", glyph: "⌕",
    doc: "telegram-analysis/readme.md",
    items: [
      { title: "Live view of all telegrams",
        text: "Incoming and outgoing telegrams with EEP, decoded values, device name, area and the related entities; filterable per gateway." },
      { title: "Recording into a log file",
        text: "JSON lines or CSV, rotating by size and by age, with or without bus polling - written in its own thread, never blocking the bus.",
        setting: "log_enocean_telegrams" },
      { title: "Export into a timeseries database",
        text: "Every telegram is written into InfluxDB with its meta data as tags and the decoded EEP values as fields; Grafana dashboards are included.",
        doc: "grafana/readme.md", setting: "timeseries_enabled" },
      { title: "Log levels per category",
        text: "Incoming, outgoing, unknown devices, bus messages, polling and decode errors can be logged individually (logger <code>eltako.telegrams</code>).",
        doc: "logging/readme.md" },
      { title: "Send arbitrary telegrams",
        text: "Built from an EEP with all its fields or as raw ESP2 hex - useful for testing an actuator without configuring it first." },
    ],
  },
  {
    label: "Automations", mdi: "mdi:gesture-tap-button", glyph: "⚡",
    items: [
      { title: "Events of rocker switches",
        text: "Button events contain the pressed buttons and how long they were pressed, which is what dimming automations need.",
        doc: "rocker_switch/readme.md" },
      { title: "Every incoming telegram as event",
        text: "The event <code>eltako_global_event_bus</code> reports each telegram with its external sender address - also for devices which are not configured.",
        doc: "telegram-events/readme.md" },
      { title: "Send message service",
        text: "One service per gateway sends any telegram, e.g. to control an ELTAKO actuator from a non-EnOcean sensor.",
        doc: "service-send-message/readme.md" },
      { title: "Blueprints",
        text: "Ready-made automations for dimming, switching and central on/off with EnOcean rocker switches - also for lights of other protocols (Zigbee, WiFi)." },
    ],
  },
  {
    label: "Operation and development", mdi: "mdi:tools", glyph: "⚙",
    items: [
      { title: "Web ui as part of the integration",
        text: "Overview, devices, live telegrams, statistics, control and this page - no extra package, no build step." },
      { title: "Settings editable at runtime",
        text: "Every general setting can be changed here; the override wins over the yaml, shows its origin and can be reset. Applied immediately." },
      { title: "Import from the EnOcean Device Manager",
        text: "An <code>.eodm</code> project or a yaml file is imported with all its gateways and devices; importing it again only adds what is new." },
      { title: "Device tests",
        text: "Configuration check (sends nothing), teach-in test of the actuators, link reliability and the travel times of covers - against the real hardware, in the web ui or on the command line.",
        doc: "device-tests/readme.md", setting: "enable_test_page" },
      { title: "Simulation without hardware",
        text: "A simulated FAM14, USB300 or LAN gateway with virtual devices: define the values a sensor reports, trigger its telegram or let it repeat periodically, announce its profile (teach-in) and switch a simulated light - the detection takes them over like real devices. Simulated devices are marked as such everywhere.",
        doc: "simulation/readme.md" },
      { title: "Standalone runtime",
        text: "The same integration code runs without Home Assistant (own web ui, InfluxDB export) - for tests on a laptop or in production.",
        doc: "standalone/readme.md" },
      { title: "Development container",
        text: "<code>cd dev &amp;&amp; ./start.sh</code> starts a ready-to-use Home Assistant with example devices, telegram history and optional Grafana.",
        doc: "dev-container/readme.md" },
    ],
  },
];

const ABOUT_STYLES = `
  .feature-intro { font-size: .78rem; color: var(--eltako-muted); margin: -6px 0 12px; }
  .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
              gap: 14px; margin-bottom: 6px; align-items: start; }
  .feature-card { background: var(--eltako-card); border: 1px solid var(--eltako-border);
                  border-radius: var(--eltako-radius); padding: 16px; }
  .feature-card h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 10px;
                     font-size: 1rem; font-weight: 500; color: var(--eltako-accent); }
  .feature-card h3 a { color: inherit; text-decoration: none; }
  .feature-card h3 a:hover { text-decoration: underline; }
  .feature-list { list-style: none; margin: 0; padding: 0; display: flex;
                  flex-direction: column; gap: 10px; }
  /* title and the state of its setting in the first row, the description below both */
  .feature-list li { display: grid; grid-template-columns: 1fr auto; gap: 2px 8px;
                     font-size: .85rem; line-height: 1.35; }
  .feature-list li > b { grid-column: 1; grid-row: 1; font-weight: 500; }
  .feature-list li > .pill { grid-column: 2; grid-row: 1; justify-self: end; align-self: center; }
  .feature-list li > .feature-text { grid-column: 1 / -1; grid-row: 2; color: var(--eltako-muted); }
`;

/** @type {import("../types.js").Page} */
export const page = {
  id: "about",
  title: "About",
  subtitle: "Information about the Home Assistant ELTAKO integration",
  icon: "mdi:information-outline",
  glyph: "ℹ",
  modes: ["user", "expert"],
  styles: ABOUT_STYLES,

  async load(ctx) {
    await Promise.all([ctx.loadIntegrationInfo(), ctx.loadLogInfo()]);
  },

  render(ctx) {
    const info = /** @type {import("../types.js").IntegrationInfo} */
      (ctx.state.integrationInfo || {});
    const entities = /** @type {import("../types.js").EntitySummary} */ (info.entities || {});
    const settings = info.general_settings || {};

    return `
      <div class="notice warn">
        <h3>${icon("mdi:account-group-outline", "☆")} Community variant</h3>
        <p><strong>This is a community-maintained open source project (MIT license) and NOT an
          official product of ELTAKO GmbH.</strong> It is developed and supported by the community
          in its spare time &ndash; without any warranty and without official support by
          ELTAKO GmbH. Please report problems in the issue tracker of the project, not to the
          ELTAKO support.</p>
      </div>

      <div class="notice">
        <h3>${escapeHtml(info.name || "ELTAKO")} &mdash; EnOcean / ELTAKO Baureihe 14 for Home Assistant</h3>
        <p>This integration connects ELTAKO series 14 devices (RS485 bus) and EnOcean devices in general to
          Home Assistant. It reads the status of all bus members, controls actuators, exposes sensors and
          rocker switches for automations, and can record and analyse the EnOcean traffic.</p>
      </div>

      <div class="cards">
        ${card("Integration version", `<span class="mono">${escapeHtml(info.version || "-")}</span>`)}
        ${card("Home Assistant", `<span class="mono">${escapeHtml(info.home_assistant_version || "-")}</span>`)}
        ${card("Gateways", formatNumber((info.gateways || []).length))}
        ${card("Devices", formatNumber(entities.device_count))}
        ${card("Entities", formatNumber(entities.entity_count))}
        ${card("IoT class", escapeHtml(info.iot_class || "-"))}
      </div>

      <h2>Features</h2>
      ${this._renderFeatures(settings)}

      <h2>Where to go from here</h2>
      <div class="links">
        <a class="link" href="#/help">${icon("mdi:help-circle-outline", "?")} Help &ndash; documentation,
          tutorials and every supported device, EEP and gateway</a>
        <a class="link" href="#/settings">${icon("mdi:cog-outline", "\u2699")} Settings &ndash; configure
          the integration without writing yaml</a>
        <a class="link" href="${REPOSITORY_URL}" target="_blank" rel="noreferrer">
          ${icon("mdi:github", "\u2605")} Repository</a>
        ${info.issue_tracker ? `<a class="link" href="${escapeHtml(info.issue_tracker)}" target="_blank" rel="noreferrer">
          ${icon("mdi:bug-outline", "!")} Report an issue</a>` : ""}
      </div>

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

  /**
   * What the integration can do, grouped by topic. Features which depend on a general setting
   * show whether they are switched on in this installation.
   */
  _renderFeatures(settings) {
    const count = FEATURE_GROUPS.reduce((total, group) => total + group.items.length, 0);

    return `
      <div class="feature-intro">
        ${count} features in ${FEATURE_GROUPS.length} areas. Optional ones show whether they are
        switched on here &ndash; they are turned on and off on the
        <a class="link" href="#/settings">settings page</a>.
      </div>
      <div class="features">
        ${FEATURE_GROUPS.map((group) => this._renderFeatureGroup(group, settings)).join("")}
      </div>
      <div class="footnote">Every supported device, EEP and gateway is listed on the
        <a class="link" href="#/help">help page</a>, every change in the
        <a class="link" href="${REPOSITORY_URL}/blob/main/changes.md" target="_blank"
           rel="noreferrer">change log</a>.</div>`;
  },

  _renderFeatureGroup(group, settings) {
    const heading = group.doc
      ? `<a href="${DOCS_URL}/${group.doc}" target="_blank" rel="noreferrer">${escapeHtml(group.label)}</a>`
      : escapeHtml(group.label);

    return `
      <div class="feature-card">
        <h3>${icon(group.mdi, group.glyph)} ${heading}</h3>
        <ul class="feature-list">
          ${group.items.map((item) => this._renderFeature(item, settings)).join("")}
        </ul>
      </div>`;
  },

  _renderFeature(item, settings) {
    // the texts are written here in this file, not entered by a user - the html in them
    // (<code>, entities) is intended and therefore not escaped
    const title = item.doc
      ? `<a class="link" href="${DOCS_URL}/${item.doc}" target="_blank" rel="noreferrer">${item.title}</a>`
      : item.title;
    const state = item.setting === undefined ? "" : this._renderFeatureState(item.setting, settings);

    return `<li><b>${title}</b>${state}<span class="feature-text">${item.text}</span></li>`;
  },

  _renderFeatureState(name, settings) {
    if (!settings || !(name in settings)) return "";
    // 'off' is a normal state for an optional feature, so it stays neutral instead of red
    const enabled = settings[name] === true;
    return `<span class="pill${enabled ? " on" : ""}" title="General setting '${escapeHtml(name)}'">${enabled ? "on" : "off"}</span>`;
  },

};
