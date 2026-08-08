/**
 * Device configuration: shows all devices of all gateways - those declared in
 * configuration.yaml and those created here - and allows to add, edit and remove the
 * latter. The form fields are delivered by the backend (eltako/devices/form).
 */

import { WS } from "../lib/api.js";
import { FORM_STYLES, readFields, renderFields } from "../lib/form.js";
import { card, escapeHtml, formatDateTime, formatNumber, matchesFilter, sortRows } from "../lib/utils.js";

// TODO type check: add /** @type {import("../types.js").Page} */ once the dom casts are in
export const page = {
  id: "devices",
  title: "Devices",
  subtitle: "All configured devices - from configuration.yaml and from this web ui",
  icon: "mdi:format-list-bulleted",
  glyph: "▤",
  styles: FORM_STYLES,
  refreshMs: 15000,

  async load(ctx) {
    const [form, list, bus] = await Promise.all([
      ctx.state.deviceForm ? Promise.resolve(ctx.state.deviceForm) : ctx.api.call(WS.DEVICE_FORM),
      ctx.api.call(WS.DEVICE_LIST),
      ctx.api.call(WS.BUS_MEMBERS),
      ctx.loadIntegrationInfo(),
      // addresses which send but are not configured - shown as their own block below
      ctx.loadStatistics(),
    ]);
    if (form) ctx.state.deviceForm = form;
    if (list) ctx.state.configuredDevices = list.devices || [];
    if (bus) ctx.state.busMembers = bus;

    // a device which was picked up on the 'unknown devices' page opens the form directly
    if (ctx.state.pendingNewDevice && !ctx.state.editor) {
      const pending = ctx.state.pendingNewDevice;
      ctx.state.pendingNewDevice = null;
      ctx.state.editor = {
        mode: "add",
        platform: pending.platform || "binary_sensor",
        gatewayId: pending.gatewayId !== undefined && pending.gatewayId !== null
          ? pending.gatewayId : this._defaultGatewayId(ctx),
        values: { id: pending.address, eep: pending.eep || "", name: pending.name || "" },
        error: null,
      };
    }
  },

  renderToolbar(ctx) {
    return `
      <input id="filter" type="search" placeholder="Filter address, name, EEP, platform&hellip;"
             value="${escapeHtml(ctx.state.configFilter)}" />
      <select id="device-view">
        <option value="hierarchy" ${ctx.state.deviceView !== "flat" ? "selected" : ""}>hierarchy (bus / radio)</option>
        <option value="flat" ${ctx.state.deviceView === "flat" ? "selected" : ""}>flat table</option>
      </select>
      <label class="check"><input id="only-silent" type="checkbox" ${ctx.state.onlySilent ? "checked" : ""}/>
             only never reported</label>
      <span class="spacer"></span>
      <button id="import-config" class="action"
              title="Import gateways and devices from an EnOcean Device Manager project (.eodm), a PCT14 export (.xml) or an eltako yaml">
        Import&hellip;</button>
      <input id="import-file" type="file" accept=".eodm,.xml,.yaml,.yml,.txt" style="display:none" />
      <button id="add-device" class="action primary">+ Add device</button>`;
  },

  async _importConfigFile(ctx, file) {
    const content = await file.text();

    const preview = await ctx.api.call("eltako/config/import", { content, dry_run: true });
    if (!preview) {
      alert(`Cannot read '${file.name}':\n${(ctx.api.lastError || {}).message || "unknown error"}`);
      return;
    }

    const lines = preview.gateways.map((gateway) =>
      `- ${gateway.name || gateway.device_type} (${gateway.device_type}, base id ${gateway.base_id})` +
      `${gateway.already_configured ? " - ALREADY CONFIGURED, will be skipped" : `: ${gateway.device_count} devices`}`);
    const warnings = preview.warnings.length
      ? `\n\nNotes:\n${preview.warnings.map((warning) => `- ${warning}`).join("\n")}` : "";
    if (!confirm(`Import from '${file.name}' (${preview.format}):\n\n${lines.join("\n")}${warnings}\n\nProceed?`)) {
      return;
    }

    const result = await ctx.api.call("eltako/config/import", { content, dry_run: false });
    if (!result) {
      alert(`Import failed:\n${(ctx.api.lastError || {}).message || "unknown error"}`);
      return;
    }
    const resultWarnings = result.warnings.length
      ? `\n\nNotes:\n${result.warnings.map((warning) => `- ${warning}`).join("\n")}` : "";
    alert(`Imported ${result.created_gateways} gateway(s) and ${result.created_devices} device(s).` +
          `${resultWarnings}`);
    await this.load(ctx);
    ctx.requestRender();
  },

  bindToolbar(ctx, root) {
    root.getElementById("filter").addEventListener("input", (event) => {
      ctx.state.configFilter = event.target.value;
      ctx.requestContentRender(true);
    });
    root.getElementById("device-view").addEventListener("change", (event) => {
      ctx.state.deviceView = event.target.value;
      ctx.requestContentRender(true);
    });
    root.getElementById("only-silent").addEventListener("change", (event) => {
      ctx.state.onlySilent = event.target.checked;
      ctx.requestContentRender(true);
    });
    root.getElementById("add-device").addEventListener("click", () => {
      ctx.state.editor = {
        mode: "add", platform: "binary_sensor", gatewayId: this._defaultGatewayId(ctx),
        values: {}, error: null,
      };
      ctx.requestContentRender(true);
    });
    const importFile = root.getElementById("import-file");
    root.getElementById("import-config").addEventListener("click", () => importFile.click());
    importFile.addEventListener("change", async () => {
      const file = importFile.files && importFile.files[0];
      importFile.value = "";      // allow importing the same file again
      if (file) await this._importConfigFile(ctx, file);
    });
  },

  render(ctx) {
    const all = ctx.state.configuredDevices || [];
    const devices = this._sorted(ctx, this._filtered(ctx));
    const fromUi = all.filter((d) => d.source === "ui").length;
    const neverSeen = all.filter((d) => !this._activityOf(d)).length;
    const activeToday = all.filter((d) => {
      const activity = this._activityOf(d);
      return activity && activity.silent_since_seconds !== null && activity.silent_since_seconds < 86400;
    }).length;

    // a device is everything which exists on the installation: gateways, sensors and
    // actuators. The gateways are devices of their own (they have their own entities and
    // their own EnOcean address) and are listed in the hierarchy below as well.
    const gateways = ((ctx.state.integrationInfo || {}).gateways || []);
    const unknown = ((ctx.state.statistics || {}).unknown_devices || []).length;

    return `
      ${this._renderEditor(ctx)}
      ${this._renderMemoryPanel(ctx)}
      <div class="cards">
        ${card("Devices", gateways.length + all.length, "",
               `${gateways.length} gateway${gateways.length === 1 ? "" : "s"}, `
               + `${all.length} sensor${all.length === 1 ? "" : "s"} / actuator${all.length === 1 ? "" : "s"}`)}
        ${card("Gateways", gateways.length, gateways.length ? "" : "warn")}
        ${card("Reported today", activeToday, activeToday ? "good" : "")}
        ${card("Never reported", neverSeen, neverSeen ? "warn" : "",
               neverSeen ? "possibly wrong address or EEP" : "")}
        ${card("Not configured yet", unknown, unknown ? "warn" : "",
               unknown ? "see 'Unknown devices' below" : "")}
        ${card("From configuration.yaml", all.filter((d) => d.source === "yaml").length)}
        ${card("Created in the web ui", fromUi)}
      </div>
      ${neverSeen ? `
        <div class="notice warn">
          <h3>${neverSeen} configured device${neverSeen === 1 ? " has" : "s have"} never reported</h3>
          <p>Either the device did not send anything yet (battery devices can take a while, actuators
            only answer on a status change), or the entry does not match: wrong address, wrong gateway
            or a device which does not exist anymore. The counters below are persisted, so they also
            survive a restart of Home Assistant.</p>
        </div>` : ""}
      ${ctx.state.deviceView === "flat"
        ? (devices.length ? this._renderTable(ctx, devices) : `
           <div class="empty">${all.length ? "No device matches the current filter."
             : "No devices configured yet. Use <b>+ Add device</b> or declare them in <code>configuration.yaml</code>."}</div>`)
        : this._renderHierarchy(ctx, devices)}

      ${/* always the last block of the page, in both views: what exists but is not
            configured yet belongs below everything which is configured */ ""}
      ${this._renderUnknownSection(ctx)}

      <div class="footnote">Devices of <code>configuration.yaml</code> cannot be edited here - they are
        version controlled and always win over devices of the web ui. Changes made here take effect
        immediately, the gateway is reloaded automatically.</div>`;
  },

  /**
   * A telegram arrived: let the row of that device flash blue. The shell calls this for every
   * telegram of the live stream, also while another page is open (then root has no rows).
   */
  onTelegram(ctx, telegram) {
    const root = ctx.root;
    if (!root) return;

    const candidates = [telegram.address, telegram.local_address].filter(Boolean);
    if (!candidates.length) return;

    const rows = new Set();
    for (const address of candidates) {
      const escaped = String(address).replace(/"/g, "");
      for (const attribute of ["data-address", "data-external", "data-sender"]) {
        root.querySelectorAll(`tr[${attribute}="${escaped}"]`).forEach((row) => rows.add(row));
      }
    }

    for (const row of rows) {
      // remove and re-add so that the animation restarts on the next telegram
      row.classList.remove("telegram-flash");
      void row.offsetWidth;
      row.classList.add("telegram-flash");
      clearTimeout(row._flashTimer);
      row._flashTimer = setTimeout(() => row.classList.remove("telegram-flash"), 1400);
    }
  },

  /** Activity of the device itself, or of its sender for pure actuators. */
  _activityOf(device) {
    return device.activity || device.sender_activity || null;
  },

  _renderActivity(device) {
    const activity = this._activityOf(device);
    if (!activity) {
      return `<span class="tag unknown">never</span>`;
    }
    const viaSender = !device.activity && device.sender_activity;
    return `
      ${formatNumber(activity.count)}
      ${activity.telegrams_per_day !== null && activity.telegrams_per_day !== undefined
        ? `<span class="hint">${formatNumber(activity.telegrams_per_day)} / day</span>` : ""}
      ${viaSender ? `<span class="hint">via sender</span>` : ""}`;
  },

  _renderLastSeen(device) {
    const activity = this._activityOf(device);
    if (!activity || !activity.last_seen) return "-";
    const silent = activity.silent_since_seconds;
    const label = silent === null || silent === undefined ? formatDateTime(activity.last_seen)
      : silent < 90 ? "just now"
      : silent < 3600 ? `${Math.round(silent / 60)} min ago`
      : silent < 86400 ? `${Math.round(silent / 3600)} h ago`
      : `${Math.round(silent / 86400)} d ago`;
    const stale = silent !== null && silent !== undefined && silent > 7 * 86400;
    return `<span class="${stale ? "stale" : ""}" title="${escapeHtml(formatDateTime(activity.last_seen))}">${label}</span>
      ${activity.seen_in_this_session ? "" : `<span class="hint">not in this session</span>`}`;
  },

  /** Sorting incl. the columns which come from the activity (telegram count, last reported). */
  _sortValue(device, column) {
    const activity = this._activityOf(device);
    if (column === "count") return activity ? activity.count : -1;
    if (column === "last_seen") {
      if (!activity || !activity.last_seen) return 0;
      const parsed = Date.parse(activity.last_seen);
      return isNaN(parsed) ? 0 : parsed;
    }
    if (column === "sender") return (device.sender || {}).id || "";
    return device[column];
  },

  _sorted(ctx, devices) {
    const column = ctx.state.configSort || "address";
    const factor = ctx.state.configSortDescending ? -1 : 1;
    return devices.slice().sort((a, b) => {
      const left = this._sortValue(a, column);
      const right = this._sortValue(b, column);
      if (left === right) return String(a.address).localeCompare(String(b.address));
      if (left === null || left === undefined) return 1;
      if (right === null || right === undefined) return -1;
      if (typeof left === "number" && typeof right === "number") return (left - right) * factor;
      return String(left).localeCompare(String(right)) * factor;
    });
  },

  TABLE_HEAD: `
    <th>Address</th><th>Name</th><th>Platform</th><th>EEP</th><th>Sender</th>
    <th>Area</th><th>Gateway</th><th class="num">Telegrams</th><th>Last reported</th>
    <th>Source</th><th></th>`,

  // own head for the unknown block: it shows candidates instead of a configuration
  UNKNOWN_TABLE_HEAD: `
    <th>Address</th><th>Telegrams seen</th><th colspan="2">Possible EEPs</th>
    <th colspan="3">Possible devices</th><th>Gateway</th><th class="num">Count</th>
    <th>Last seen</th><th>Source</th><th></th>`,

  _deviceRow(device, indent = false, senderBadge = "") {
    return `
      <tr class="${this._activityOf(device) ? "" : "unknown-row"} ${indent ? "channel-row" : ""} ${
            device.simulated ? "simulated-row" : ""}"
          data-address="${escapeHtml(device.address)}"
          data-external="${escapeHtml(device.external_address || "")}"
          data-sender="${escapeHtml((device.sender || {}).id || "")}">
        <td class="mono">${indent ? '<span class="tree">└</span>' : ""}${escapeHtml(device.address)}
          ${device.external_address && device.external_address !== device.address
            ? `<span class="hint">extern ${escapeHtml(device.external_address)}</span>` : ""}</td>
        <td>${escapeHtml(device.name || "")}
          ${device.simulated ? `<span class="tag simulated" title="No hardware: this device is simulated (see the simulation page)">simulated</span>` : ""}</td>
        <td>${escapeHtml(device.platform)}</td>
        <td class="mono">${escapeHtml(device.eep || "-")}</td>
        <td class="mono">${device.sender ? escapeHtml(device.sender.id || "") : "-"} ${senderBadge}
          ${device.sender && device.sender.eep ? `<span class="hint">${escapeHtml(device.sender.eep)}</span>` : ""}</td>
        <td>${escapeHtml(device.area || "-")}</td>
        <td>${escapeHtml(device.gateway_name || device.gateway_id)}</td>
        <td class="num">${this._renderActivity(device)}</td>
        <td>${this._renderLastSeen(device)}</td>
        <td><span class="tag ${device.source === "ui" ? "source-ui" : "source-yaml"}">${device.source === "ui" ? "web ui" : "yaml"}</span></td>
        <td class="actions">
          ${device.ha_device_id ? `<button class="action small" data-ha-device="${escapeHtml(device.ha_device_id)}">open</button>` : ""}
          ${device.editable ? `
            <button class="action small" data-edit="${escapeHtml(device.platform)}|${escapeHtml(device.address)}|${device.gateway_id}">edit</button>
            <button class="action small danger" data-remove="${escapeHtml(device.platform)}|${escapeHtml(device.address)}|${device.gateway_id}">delete</button>`
            : `<span class="hint">edit in yaml</span>`}
        </td>
      </tr>`;
  },

  _renderTable(ctx, devices) {
    return `
      <div class="table-wrapper">
        <table>
          <thead><tr>
            ${this._sortableHeader(ctx, "address", "Address")}
            ${this._sortableHeader(ctx, "name", "Name")}
            ${this._sortableHeader(ctx, "platform", "Platform")}
            ${this._sortableHeader(ctx, "eep", "EEP")}
            ${this._sortableHeader(ctx, "sender", "Sender")}
            ${this._sortableHeader(ctx, "area", "Area")}
            ${this._sortableHeader(ctx, "gateway_name", "Gateway")}
            ${this._sortableHeader(ctx, "count", "Telegrams", "num")}
            ${this._sortableHeader(ctx, "last_seen", "Last reported")}
            ${this._sortableHeader(ctx, "source", "Source")}
            <th></th>
          </tr></thead>
          <tbody>${devices.map((device) => this._deviceRow(device)).join("")}</tbody>
        </table>
      </div>`;
  },

  /**
   * Hierarchical view like the EnOcean Device Manager: one section per bus (gateway) with the
   * physical bus devices and their channels, and a section for all radio devices including
   * the wireless gateways.
   */
  _renderHierarchy(ctx, devices) {
    const gateways = ((ctx.state.integrationInfo || {}).gateways || []);
    const members = ((ctx.state.busMembers || {}).members || []);
    const isBusGateway = (gw) => ["fam14", "fgw14usb", "ftd14"].includes(String(gw.type));
    // bus positions which are gateway modules themselves: they stay in the list (they belong
    // to this bus) but they are added as gateway, not as device. Only one FAM14 exists per
    // bus, but there can be several FGW14/FGW14-USB.
    const isGatewayModule = (member) => member.is_fam
      || ["FAM14", "FGW14_USB", "FTD14"].includes(String(member.device_class || ""));

    // everything with a 00-00-.. address lives on the RS485 bus: its external address is the
    // base id of the FAM14 plus the local id. That includes the FTS14EM inputs (00-00-1x-..),
    // not only the bus positions 00-00-00-01..FF.
    const isLocal = (address) => String(address || "").toUpperCase().startsWith("00-00-");
    const isPositionAddress = (address) => String(address || "").toUpperCase().startsWith("00-00-00-");
    const localOf = (position) => `00-00-00-${Number(position).toString(16).toUpperCase().padStart(2, "0")}`;

    const sections = [];

    // devices of bus gateways which are configured (e.g. in the yaml) but not set up in home
    // assistant. If exactly one bus is live, they are shown at their bus position there
    // instead of a second listing - the same physical device must not appear twice.
    const busGateways = gateways.filter(isBusGateway);
    const liveBusGatewayIds = new Set(busGateways.map((gw) => String(gw.id)));
    const orphanBusDevices = devices.filter((d) => isLocal(d.address) && !liveBusGatewayIds.has(String(d.gateway_id)));
    const adoptedOrphans = new Set();
    const orphanAt = (position) => (busGateways.length === 1
      ? orphanBusDevices.filter((d) => d.address === localOf(position)) : []);

    // sensors found in the device memories which are not configured yet: through their key
    // function the EEP is known, so they can be registered in home assistant with one click
    const knownAddresses = new Set();
    for (const d of devices) {
      knownAddresses.add(String(d.address).toUpperCase());
      if (d.external_address) knownAddresses.add(String(d.external_address).toUpperCase());
      if ((d.sender || {}).id) knownAddresses.add(String(d.sender.id).toUpperCase());
    }
    const detectedSensors = new Map();
    for (const member of members) {
      for (const sensor of (member.taught_in || [])) {
        if (sensor.role === "ha_sender") continue;
        const id = String(sensor.sensor_id).toUpperCase();
        if (knownAddresses.has(id)) continue;
        if (!detectedSensors.has(id)) {
          detectedSensors.set(id, { ...sensor, sensor_id: id, gateway_id: member.gateway_id, locations: [] });
        }
        detectedSensors.get(id).locations.push(
          `${member.device_class || `pos ${member.bus_address}`}${sensor.channel ? ` ch${sensor.channel}` : ""}`);
      }
    }
    const detectedFor = (predicate) => [...detectedSensors.values()].filter(predicate)
      .sort((a, b) => a.sensor_id.localeCompare(b.sensor_id));

    // only one operation at a time may talk on a bus. While one runs the buttons are disabled
    // and say what is going on - a scan, a teach-in or the base id request of a FAM14.
    const busyLabel = (gw) => {
      const reason = ((ctx.state.busMembers || {}).busy_with || {})[String(gw.id)];
      return reason ? reason : "scanning bus";
    };

    for (const gw of busGateways) {
      const gwMembers = members.filter((m) => String(m.gateway_id) === String(gw.id));
      const gwDevices = devices.filter((d) => String(d.gateway_id) === String(gw.id) && isLocal(d.address));
      const deviceAt = (position) => gwDevices.filter((d) => d.address === localOf(position));
      const covered = new Set();

      const rows = [];
      const parents = gwMembers.filter((m) => !m.parent_bus_address);
      for (const parent of parents) {
        const channels = parent.channel_count || 1;
        const range = channels > 1 ? `${parent.bus_address}-${parent.bus_address + channels - 1}` : `${parent.bus_address}`;
        rows.push(`
          <tr class="bus-device-row">
            <td colspan="11">
              <b>Pos. ${escapeHtml(range)}</b>
              ${parent.device_class ? `&nbsp; ${escapeHtml(parent.device_class)}` : `&nbsp; <span class="hint">not identified yet</span>`}
              ${parent.description ? `<span class="hint-inline">&mdash; ${escapeHtml(parent.description)}</span>` : ""}
              ${parent.is_fam ? `<span class="tag role">bus gateway</span>` : ""}
              ${parent.pct14_function_group ? `<span class="hint-inline">teach-in: PCT14 group ${escapeHtml(parent.pct14_function_group)},
                 function ${escapeHtml(parent.pct14_key_function)}</span>` : ""}
              ${parent.ha_device_id ? `<button class="action small" data-ha-device="${escapeHtml(parent.ha_device_id)}">open device</button>` : ""}
              ${(parent.taught_in || []).length
                ? `<button class="action small" data-memory-details="${escapeHtml(gw.id)}|${escapeHtml(parent.bus_address)}"
                     title="${parent.scanned_at ? `read from the device memory on ${escapeHtml(formatDateTime(parent.scanned_at))}`
                       : "read from the device memory"}">
                     memory: ${escapeHtml((parent.taught_in || []).length)} sender${(parent.taught_in || []).length === 1 ? "" : "s"}</button>`
                : parent.memory_rows_read
                  ? `<span class="hint-inline">memory: ${escapeHtml(parent.memory_rows_read)}/${escapeHtml(parent.memory_size || "?")} rows read</span>` : ""}
            </td>
          </tr>`);

        for (let position = parent.bus_address; position < parent.bus_address + channels; position++) {
          covered.add(position);
          if (isGatewayModule(parent)) {
            // a gateway module occupies this position - offer to add it as gateway
            rows.push(`
              <tr class="channel-row" data-address="${escapeHtml(localOf(position))}">
                <td class="mono"><span class="tree">└</span>${escapeHtml(localOf(position))}</td>
                <td colspan="9"><span class="hint">bus gateway module - part of this bus, added as
                  gateway (not as device)</span></td>
                <td class="actions">${parent.is_fam ? "-" : `<button class="action small primary"
                  data-add-gateway-type="${parent.device_class === "FTD14" ? "ftd14" : "fgw14usb"}">+ add gateway</button>`}</td>
              </tr>`);
            continue;
          }
          let configured = deviceAt(position);
          let adoptedHint = "";
          if (!configured.length) {
            const foreign = orphanAt(position);
            if (foreign.length) {
              configured = foreign;
              foreign.forEach((device) => adoptedOrphans.add(device));
              adoptedHint = `<span class="tag unknown">gateway ${escapeHtml(foreign[0].gateway_name
                || foreign[0].gateway_id)} - not set up</span>`;
            }
          }
          if (configured.length) {
            const taughtIn = (parent.taught_in || []).map((s) => String(s.sensor_id).toUpperCase());
            rows.push(...configured.map((device) => {
              const senderId = ((device.sender || {}).id || "").toUpperCase();
              let badge = adoptedHint;
              if (senderId && parent.taught_in) {
                badge += taughtIn.includes(senderId)
                  ? `<span class="tag taught">&#10003; taught in</span>`
                  : `<span class="tag unknown">&#10007; not taught in</span>`;
              }
              return this._deviceRow(device, true, badge);
            }));
          } else if (!parent.is_fam) {
            rows.push(`
              <tr class="channel-row unknown-row" data-address="${escapeHtml(localOf(position))}">
                <td class="mono"><span class="tree">└</span>${escapeHtml(localOf(position))}</td>
                <td colspan="9"><span class="hint">channel not configured</span></td>
                <td class="actions"><button class="action small primary"
                    data-add-bus="${escapeHtml(localOf(position))}|${escapeHtml(parent.suggested_eep || "")}|${escapeHtml(parent.suggested_platform || "")}|${escapeHtml(gw.id)}"
                    >+ add device</button></td>
              </tr>`);
          }
        }
      }

      // configured bus devices whose position was not seen on the bus (yet)
      const orphans = gwDevices.filter((d) => isPositionAddress(d.address)
        && !covered.has(parseInt(d.address.split("-")[3], 16)));
      if (orphans.length) {
        rows.push(`<tr class="bus-device-row"><td colspan="11"><span class="hint">
          configured but not seen on the bus yet</span></td></tr>`);
        rows.push(...orphans.map((device) => this._deviceRow(device, true)));
      }

      // wired inputs like the FTS14EM buttons: they belong to this bus but occupy no
      // position - their external address is the base id of the FAM14 plus the local id
      const wiredInputs = gwDevices.filter((d) => !isPositionAddress(d.address));
      const foreignWired = busGateways.length === 1
        ? orphanBusDevices.filter((d) => !isPositionAddress(d.address)) : [];
      foreignWired.forEach((device) => adoptedOrphans.add(device));
      if (wiredInputs.length || foreignWired.length) {
        rows.push(`<tr class="bus-device-row"><td colspan="11"><span class="hint">
          wired bus inputs (e.g. FTS14EM) - external address = base id of the FAM14 + local id</span></td></tr>`);
        rows.push(...wiredInputs.map((device) => this._deviceRow(device, true)));
        rows.push(...foreignWired.map((device) => this._deviceRow(device, true,
          `<span class="tag unknown">gateway ${escapeHtml(device.gateway_name || device.gateway_id)} - not set up</span>`)));
      }

      // wired inputs (e.g. FTS14EM) found in the device memories of this bus
      const busDetected = detectedFor((s) => String(s.gateway_id) === String(gw.id)
        && s.sensor_id.startsWith("00-00-"));
      if (busDetected.length) {
        rows.push(`<tr class="bus-device-row"><td colspan="11"><span class="hint">
          taught-in senders found in the device memories - not configured yet</span></td></tr>`);
        rows.push(...busDetected.map((sensor) => this._detectedSensorRow(sensor)));
      }

      sections.push(`
        <h3 class="bus-heading">${escapeHtml(gw.name)}
          ${gw.simulated ? `<span class="tag simulated" title="No hardware: this bus is simulated">simulated</span>` : ""}
          <span class="hint-inline">RS485 bus,
          ${gwMembers.length} position${gwMembers.length === 1 ? "" : "s"} detected</span>
          ${gw.ha_device_id ? `<button class="action small" data-ha-device="${escapeHtml(gw.ha_device_id)}">open device</button>` : ""}
          ${((ctx.state.busMembers || {}).scans_running || {})[String(gw.id)]
            ? `<button class="action small" disabled title="While this runs no other telegram may go over the bus - the buttons come back afterwards.">${escapeHtml(busyLabel(gw))}&hellip;</button>`
            : `<button class="action small primary" data-bus-scan="${escapeHtml(gw.id)}">scan bus &amp; read memory</button>
               <button class="action small" data-teach-in="${escapeHtml(gw.id)}">check &amp; teach in HA senders</button>`}</h3>
        ${rows.length ? `<div class="table-wrapper"><table>
            <thead><tr>${this.TABLE_HEAD}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`
          : `<div class="empty">No bus positions detected yet - they appear within a minute of polling.</div>`}`);
    }

    // bus devices of not-set-up gateways which could not be shown at a live bus position
    const remainingOrphans = orphanBusDevices.filter((device) => !adoptedOrphans.has(device));
    if (remainingOrphans.length) {
      const byGatewayName = new Map();
      for (const device of remainingOrphans) {
        const key = device.gateway_name || `Gateway ${device.gateway_id}`;
        if (!byGatewayName.has(key)) byGatewayName.set(key, []);
        byGatewayName.get(key).push(device);
      }
      for (const [name, list] of byGatewayName) {
        sections.push(`
          <h3 class="bus-heading">${escapeHtml(name)} <span class="hint-inline">configured but not set up
            in Home Assistant - add the gateway to make these devices work</span></h3>
          <div class="table-wrapper"><table>
            <thead><tr>${this.TABLE_HEAD}</tr></thead>
            <tbody>${list.map((device) => this._deviceRow(device, true)).join("")}</tbody></table></div>`);
      }
    }

    // radio devices: wireless gateways plus every configured device with a wireless address
    const radioGateways = gateways.filter((gw) => !isBusGateway(gw));
    const radioDevices = devices.filter((d) => !isLocal(d.address));
    const radioRows = [];
    for (const gw of radioGateways) {
      radioRows.push(`
        <tr class="bus-device-row">
          <td colspan="11"><b>${escapeHtml(gw.name)}</b>
            ${gw.simulated ? `<span class="tag simulated" title="No hardware: this gateway is simulated">simulated</span>` : ""}
            <span class="hint-inline">wireless gateway, ${escapeHtml(gw.type)}, base id ${escapeHtml(gw.base_id)}</span>
            <span class="pill ${gw.connected ? "on" : "off"}">${gw.connected ? "connected" : "disconnected"}</span>
            ${gw.ha_device_id ? `<button class="action small" data-ha-device="${escapeHtml(gw.ha_device_id)}">open device</button>` : ""}</td>
        </tr>`);
    }
    if (radioDevices.length) {
      radioRows.push(`<tr class="bus-device-row"><td colspan="11"><span class="hint">wireless devices
        (received by any gateway)</span></td></tr>`);
      radioRows.push(...radioDevices.map((device) => this._deviceRow(device, true)));
    }
    // wireless sensors found in the device memories of the bus scan
    const radioDetected = detectedFor((s) => !s.sensor_id.startsWith("00-00-"));
    if (radioDetected.length) {
      radioRows.push(`<tr class="bus-device-row"><td colspan="11"><span class="hint">taught-in senders
        found in the device memories - the EEP is derived from their key function</span></td></tr>`);
      radioRows.push(...radioDetected.map((sensor) => this._detectedSensorRow(sensor)));
    }
    sections.push(`
      <h3 class="bus-heading">Radio <span class="hint-inline">${radioGateways.length} gateway${radioGateways.length === 1 ? "" : "s"},
        ${radioDevices.length} sensor${radioDevices.length === 1 ? "" : "s"} / actuator${radioDevices.length === 1 ? "" : "s"}${radioDetected.length
          ? `, ${radioDetected.length} detected in memories` : ""}</span></h3>
      ${radioRows.length ? `<div class="table-wrapper"><table>
          <thead><tr>${this.TABLE_HEAD}</tr></thead><tbody>${radioRows.join("")}</tbody></table></div>`
        : `<div class="empty">No radio devices configured.</div>`}`);

    return sections.join("");
  },

  /**
   * Addresses which send telegrams but are not configured yet - the same data as the
   * 'Unknown devices' page, as a block of the device list so that everything which exists on
   * the bus and in the air is visible in one place.
   *
   * Senders which were already found in the device memories are skipped: they are listed at
   * their bus position above, with the far better EEP from their key function.
   */
  _renderUnknownSection(ctx) {
    const recording = !(ctx.state.logInfo && ctx.state.logInfo.enabled === false);
    if (!recording) {
      return `
        <h3 class="bus-heading">Unknown devices <span class="hint-inline">telegram recording is
          disabled - enable it to detect devices which are not configured yet</span></h3>`;
    }

    // the backend delivers them filtered, sorted and enriched (candidates + yaml snippet),
    // see telegram_suggestions.py - nothing is derived here
    const unknown = ((ctx.state.statistics || {}).unknown_devices || [])
      .filter((device) => matchesFilter(ctx.state.configFilter,
        [device.address, ...Object.keys(device.msg_types || {}),
         ...(device.suggestions || []).map((candidate) => candidate.eep)]));

    const heading = `
      <h3 class="bus-heading">Unknown devices <span class="hint-inline">addresses which send
        telegrams but are not configured yet${unknown.length ? `, ${unknown.length} found` : ""}</span>
        ${unknown.length ? `<button class="action small" id="copy-unknown-yaml"
          title="configuration.yaml snippet for all of them">copy all as yaml</button>` : ""}</h3>`;

    if (!unknown.length) {
      return `${heading}
        <div class="empty">${(ctx.state.statistics || {}).devices?.length
          ? "Every recorded telegram belongs to a configured device."
          : "No telegrams recorded yet - press a button on a device to make it appear here."}</div>`;
    }

    const rows = unknown.map((device) => {
      const best = device.suggested || {};
      return `
        <tr class="channel-row unknown-row" data-address="${escapeHtml(device.address)}">
          <td class="mono">${escapeHtml(device.address)}
            ${device.local_address && device.local_address !== device.address
              ? `<span class="hint">bus ${escapeHtml(device.local_address)}</span>` : ""}</td>
          <td><span class="hint">${escapeHtml(Object.keys(device.msg_types || {}).join(", "))}</span>
            ${device.last_data ? `<span class="hint">data ${escapeHtml(device.last_data)}</span>` : ""}</td>
          <td colspan="2">${this._renderEepCandidates(device)}</td>
          <td colspan="3">${this._renderDeviceCandidates(device)}</td>
          <td>${escapeHtml((device.gateway_ids || []).join(", ") || "-")}</td>
          <td class="num">${formatNumber(device.count)}</td>
          <td class="mono">${escapeHtml(formatDateTime(device.last_seen))}</td>
          <td><span class="tag role">telegram</span></td>
          <td class="actions"><button class="action small primary"
            data-add-unknown="${escapeHtml(device.address)}|${escapeHtml(best.eep || "")}|${escapeHtml(best.platform || "")}"
            >+ add device</button>
            <button class="action small" data-unknown-yaml="${encodeURIComponent(device.yaml || '')}"
              >copy yaml</button></td>
        </tr>`;
    }).join("");
    this._unknownYaml = unknown.map((device) => device.yaml || "").join("");

    return `${heading}
      <div class="table-wrapper"><table>
        <thead><tr>${this.UNKNOWN_TABLE_HEAD}</tr></thead><tbody>${rows}</tbody></table></div>
      <div class="footnote">The candidates come from the backend: a 4BS teach-in telegram states
        the EEP (<span class="tag taught">confirmed</span>), otherwise the message type limits
        the possible profiles and the data bytes decide between them - a candidate whose decoded
        values are out of range is dropped. The device suggestions are the models of the central
        device catalog which speak that EEP. Devices found in the memory of a bus actuator are
        listed at their bus position above instead, their key function reveals the EEP reliably.</div>`;
  },

  /** Column "possible EEPs": what the backend derived from the telegrams. */
  _renderEepCandidates(device) {
    const candidates = device.suggestions || [];
    if (!candidates.length) {
      return `<span class="hint">no candidate - waiting for a telegram with data</span>`;
    }
    return candidates.map((candidate) => `
      <div class="candidate">
        <span class="mono">${escapeHtml(candidate.eep)}</span>
        <span class="tag ${candidate.confidence === "confirmed" ? "taught"
          : candidate.confidence === "likely" ? "role" : "unknown"}"
          >${escapeHtml(candidate.confidence)}</span>
        <span class="hint">${escapeHtml(candidate.reason)}</span>
      </div>`).join("");
  },

  /** Column "possible devices": the models of the catalog which speak those EEPs. */
  /** at most this many device models per EEP - the rest is summarized as '+N' */
  MAX_MODELS_PER_EEP: 6,

  _renderDeviceCandidates(device) {
    const withDevices = (device.suggestions || [])
      .filter((candidate) => (candidate.devices || []).length);
    if (!withDevices.length) {
      return `<span class="hint">${(device.suggestions || []).length
        ? "no device of the catalog uses these profiles" : "-"}</span>`;
    }

    // one line per EEP: "<eep>: model model model" - the EEPs are aligned in a grid column so
    // the models of the different profiles stay readable next to each other
    return `<div class="eep-devices">${withDevices.map((candidate) => {
      const models = candidate.devices;
      const shown = models.slice(0, this.MAX_MODELS_PER_EEP);
      const rest = models.length - shown.length;
      return `
        <span class="mono eep-devices-key">${escapeHtml(candidate.eep)}</span>
        <span class="eep-devices-value">
          ${shown.map((model) => `<span class="chip"
            title="${escapeHtml([model.hw_type, model.brand, model.description, model.platform]
              .filter(Boolean).join(" - "))}">${escapeHtml(model.hw_type)}</span>`).join("")}
          ${rest > 0 ? `<span class="hint" title="${escapeHtml(models.map((m) => m.hw_type).join(", "))}"
            >+${rest} more</span>` : ""}
        </span>`;
    }).join("")}</div>`;
  },

  /**
   * Side panel with the memory content (taught-in senders) of one bus device. Docked on the
   * right so the device table itself stays compact.
   */
  _renderMemoryPanel(ctx) {
    const selected = ctx.state.memoryPanel;
    if (!selected) return "";
    const members = ((ctx.state.busMembers || {}).members || []);
    const member = members.find((m) => String(m.gateway_id) === String(selected.gatewayId)
      && String(m.bus_address) === String(selected.busAddress));
    if (!member) return "";

    const devices = ctx.state.configuredDevices || [];
    const knownAddresses = new Set();
    for (const d of devices) {
      knownAddresses.add(String(d.address).toUpperCase());
      if (d.external_address) knownAddresses.add(String(d.external_address).toUpperCase());
      if ((d.sender || {}).id) knownAddresses.add(String(d.sender.id).toUpperCase());
    }

    const sensors = [...(member.taught_in || [])].sort((a, b) =>
      (a.channel || 0) - (b.channel || 0) || (a.memory_line || 0) - (b.memory_line || 0));
    const lines = sensors.map((sensor) => {
      const configured = knownAddresses.has(String(sensor.sensor_id).toUpperCase());
      return `
        <div class="sensor-line">
          <div>
            <span class="mono">${escapeHtml(sensor.sensor_id)}</span>
            ${sensor.channel ? `<span class="tag role">ch ${escapeHtml(sensor.channel)}</span>` : ""}
            ${sensor.role === "ha_sender" ? `<span class="tag source-ui">HA sender</span>` : ""}
            ${configured ? `<span class="tag taught">&#10003; configured</span>`
              : sensor.role !== "ha_sender" && sensor.suggested_platform
                ? `<button class="action small primary"
                     data-add-bus="${escapeHtml(sensor.sensor_id)}|${escapeHtml(sensor.suggested_eep || "")}|${escapeHtml(sensor.suggested_platform || "")}|${escapeHtml(member.gateway_id)}"
                     >+ add</button>` : ""}
          </div>
          <div class="hint">${escapeHtml(sensor.key_function_name)} &middot; group ${escapeHtml(sensor.function_group)}
            &middot; line ${escapeHtml(sensor.memory_line)} &rarr; ${escapeHtml(sensor.target_address)}
            ${sensor.suggested_eep ? `&middot; EEP ${escapeHtml(sensor.suggested_eep)}` : ""}</div>
        </div>`;
    }).join("");

    return `
      <aside class="detail-drawer">
        <button class="action small" id="memory-panel-close" style="float:right">&#10005; close</button>
        <h3>Pos. ${escapeHtml(member.bus_address)} ${escapeHtml(member.device_class || "")}</h3>
        <div class="hint">${escapeHtml(member.description || "")}
          &middot; memory ${escapeHtml(member.memory_rows_read || 0)}/${escapeHtml(member.memory_size || "?")} rows
          &middot; ${sensors.length} taught-in sender${sensors.length === 1 ? "" : "s"}</div>
        ${member.pct14_function_group ? `<div class="hint">teach-in via PCT14: group
          ${escapeHtml(member.pct14_function_group)}, function ${escapeHtml(member.pct14_key_function)}</div>` : ""}
        ${lines || `<div class="empty">No senders taught in.</div>`}
      </aside>`;
  },

  /** A taught-in sender found in a device memory which is not configured in home assistant yet. */
  _detectedSensorRow(sensor) {
    return `
      <tr class="channel-row unknown-row" data-address="${escapeHtml(sensor.sensor_id)}">
        <td class="mono"><span class="tree">└</span>${escapeHtml(sensor.sensor_id)}</td>
        <td>${escapeHtml(sensor.suggested_name || "")}
          <span class="hint">taught in at ${escapeHtml(sensor.locations.join(", "))}</span></td>
        <td>${escapeHtml(sensor.suggested_platform || "-")}</td>
        <td class="mono">${escapeHtml(sensor.suggested_eep || "-")}</td>
        <td colspan="5"><span class="hint">${escapeHtml(sensor.key_function_name || "")}</span></td>
        <td><span class="tag role">memory</span></td>
        <td class="actions"><button class="action small primary"
          data-add-bus="${escapeHtml(sensor.sensor_id)}|${escapeHtml(sensor.suggested_eep || "")}|${escapeHtml(sensor.suggested_platform || "")}|${escapeHtml(sensor.gateway_id)}"
          >+ add device</button></td>
      </tr>`;
  },

  _renderEditor(ctx) {
    const editor = ctx.state.editor;
    if (!editor) return "";

    const descriptor = ctx.state.deviceForm || { platforms: [], gateways: [] };
    const platform = descriptor.platforms.find((p) => p.platform === editor.platform) || descriptor.platforms[0];
    if (!platform) return `<div class="notice warn">The backend did not deliver any form definition.</div>`;

    const gateways = descriptor.gateways || [];

    return `
      <div class="form-card" id="device-editor">
        <h3>${editor.mode === "add" ? "Add device" : `Edit ${escapeHtml(editor.values.id || "")}`}</h3>
        <div class="form-grid">
          <div class="field">
            <label for="editor-gateway">Gateway *</label>
            <select id="editor-gateway" ${editor.mode === "edit" ? "disabled" : ""}>
              ${gateways.map((gw) => `<option value="${gw.id}" ${gw.id === editor.gatewayId ? "selected" : ""}>
                 ${escapeHtml(gw.name)}</option>`).join("")}
            </select>
            <span class="field-help">Base id ${escapeHtml((gateways.find((g) => g.id === editor.gatewayId) || {}).base_id || "-")}</span>
          </div>
          <div class="field">
            <label for="editor-platform">Type *</label>
            <select id="editor-platform" ${editor.mode === "edit" ? "disabled" : ""}>
              ${descriptor.platforms.map((p) => `<option value="${escapeHtml(p.platform)}"
                 ${p.platform === editor.platform ? "selected" : ""}>${escapeHtml(p.label)}</option>`).join("")}
            </select>
            <span class="field-help">${escapeHtml(platform.help || "")}</span>
          </div>
          ${(platform.device_types || []).length ? `
          <div class="field">
            <label for="editor-device-type">Device</label>
            <select id="editor-device-type">
              <option value="">&mdash; select a device (optional) &mdash;</option>
              ${platform.device_types.map((t) => `<option value="${escapeHtml(t.value)}"
                 ${t.value === editor.deviceType ? "selected" : ""}>${escapeHtml(t.label)}</option>`).join("")}
            </select>
            <span class="field-help">${this._deviceTypeHint(platform, editor.deviceType)
              || "Selecting a device prefills its EEP and sender EEP - all values stay editable."}</span>
          </div>` : ""}
        </div>
        <div class="form-grid" id="device-fields">
          ${renderFields(platform.fields, editor.values || {})}
        </div>
        ${editor.error ? `<div class="form-error">${escapeHtml(editor.error)}</div>` : ""}
        <div class="form-actions">
          <button id="editor-save" class="action primary">${editor.mode === "add" ? "Create device" : "Save"}</button>
          <button id="editor-cancel" class="action">Cancel</button>
          <span class="field-help">The values are validated by the integration - exactly like in the yaml.</span>
        </div>
      </div>`;
  },

  _sortableHeader(ctx, column, label, extraClass = "") {
    const active = (ctx.state.configSort || "address") === column;
    const arrow = active ? (ctx.state.configSortDescending ? " &#9660;" : " &#9650;") : "";
    return `<th data-sort="${column}" class="${extraClass} ${active ? "sorted" : ""}">${label}${arrow}</th>`;
  },

  /**
   * Relations from the read device memories: which sensor is taught into which bus channel.
   * Returns pairs of upper case addresses [sensorId, targetLocalAddress].
   */
  _teachInRelations(ctx) {
    const pairs = [];
    for (const member of ((ctx.state.busMembers || {}).members || [])) {
      for (const sensor of (member.taught_in || [])) {
        pairs.push([String(sensor.sensor_id).toUpperCase(), String(sensor.target_address).toUpperCase()]);
      }
    }
    return pairs;
  },

  /** Click on a row: highlight everything related to it through the teach-in memory. */
  _toggleRelations(ctx, root, row) {
    const wasOrigin = row.classList.contains("relation-origin");
    root.querySelectorAll("tr.relation-origin, tr.relation-target").forEach((element) => {
      element.classList.remove("relation-origin", "relation-target");
    });
    if (wasOrigin) return;      // second click clears the highlighting

    const own = new Set(["data-address", "data-external", "data-sender"]
      .map((attribute) => (row.getAttribute(attribute) || "").toUpperCase()).filter(Boolean));

    const related = new Set();
    for (const [sensorId, target] of this._teachInRelations(ctx)) {
      if (own.has(sensorId)) related.add(target);       // this row is a sender -> its targets
      if (own.has(target)) related.add(sensorId);       // this row is an actuator -> its senders
    }
    if (!related.size) return;

    row.classList.add("relation-origin");
    root.querySelectorAll("tr[data-address], tr[data-external], tr[data-sender]").forEach((candidate) => {
      if (candidate === row) return;
      for (const attribute of ["data-address", "data-external", "data-sender"]) {
        const value = (candidate.getAttribute(attribute) || "").toUpperCase();
        if (value && related.has(value)) {
          candidate.classList.add("relation-target");
          return;
        }
      }
    });
  },

  afterRender(ctx, root) {
    // memory details of a bus device open in the side panel on the right
    root.querySelectorAll("button[data-memory-details]").forEach((button) => {
      button.addEventListener("click", () => {
        const [gatewayId, busAddress] = button.dataset.memoryDetails.split("|");
        const current = ctx.state.memoryPanel;
        ctx.state.memoryPanel = (current && String(current.gatewayId) === gatewayId
          && String(current.busAddress) === busAddress) ? null : { gatewayId, busAddress };
        ctx.requestContentRender(true);
      });
    });
    root.querySelector("#memory-panel-close")?.addEventListener("click", () => {
      ctx.state.memoryPanel = null;
      ctx.requestContentRender(true);
    });

    // click on a device row highlights its teach-in relations (green)
    root.querySelectorAll("tr[data-address]").forEach((row) => {
      row.addEventListener("click", (event) => {
        if (event.target.closest("button, a, input, select")) return;
        this._toggleRelations(ctx, root, row);
      });
    });

    // start the active bus scan of a gateway (discovery + memory of every device)
    root.querySelectorAll("button[data-bus-scan]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        button.textContent = "scanning bus…";
        const result = await ctx.api.call(WS.BUS_READ_MEMORY, { gateway_id: Number(button.dataset.busScan) });
        if (!result) {
          button.disabled = false;
          button.textContent = "scan bus & read memory";
          alert((ctx.api.lastError || {}).message || "Could not start the scan.");
          ctx.api.lastError = null;
          return;
        }
        // results stream in through the registry - reload after a while and on the next refresh
        setTimeout(async () => { await this.load(ctx); ctx.requestContentRender(); }, 8000);
      });
    });

    // a bus position is a gateway module: open the gateway wizard on the overview, prefilled
    root.querySelectorAll("button[data-add-gateway-type]").forEach((button) => {
      button.addEventListener("click", () => {
        ctx.state.pendingNewGateway = { device_type: button.dataset.addGatewayType };
        ctx.navigate("overview");
      });
    });

    // verify and teach in the configured home assistant sender ids (standard procedure)
    root.querySelectorAll("button[data-teach-in]").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!confirm("Verify all configured Home Assistant sender ids of this bus and write the "
                     + "missing ones into the actuators (PCT14 standard procedure)?\n\n"
                     + "The bus is locked for a few seconds while writing.")) return;
        button.disabled = true;
        button.textContent = "teaching in…";
        const result = await ctx.api.call(WS.BUS_TEACH_IN, { gateway_id: Number(button.dataset.teachIn) });
        button.disabled = false;
        button.textContent = "check & teach in HA senders";
        if (!result) {
          alert((ctx.api.lastError || {}).message || "Teach-in failed.");
          ctx.api.lastError = null;
          return;
        }
        const lines = (result.results || []).map((r) =>
          `${r.address}  ${r.sender_id}  ->  ${r.result}${r.message ? ` (${r.message})` : ""}`);
        alert(lines.length ? `Teach-in results:\n\n${lines.join("\n")}`
                           : "No bus device with a configured sender found.");
        await this.load(ctx);
        ctx.requestContentRender();
      });
    });

    // take over an unconfigured bus channel: open the editor prefilled
    const copyAllYaml = root.getElementById("copy-unknown-yaml");
    if (copyAllYaml) {
      copyAllYaml.addEventListener("click", () => {
        navigator.clipboard.writeText(this._unknownYaml || "");
        copyAllYaml.textContent = "copied";
        setTimeout(() => (copyAllYaml.textContent = "copy all as yaml"), 1500);
      });
    }

    root.querySelectorAll("button[data-unknown-yaml]").forEach((button) => {
      button.addEventListener("click", () => {
        navigator.clipboard.writeText(decodeURIComponent(button.dataset.unknownYaml));
        button.textContent = "copied";
        setTimeout(() => (button.textContent = "copy yaml"), 1500);
      });
    });

    root.querySelectorAll("button[data-add-unknown]").forEach((button) => {
      button.addEventListener("click", () => {
        const [address, eep, platform] = button.dataset.addUnknown.split("|");
        ctx.state.editor = {
          mode: "add",
          platform: platform || "binary_sensor",
          gatewayId: this._defaultGatewayId(ctx),
          values: { id: address, eep: eep || "", name: `Device ${address}` },
          error: null,
        };
        ctx.requestContentRender(true);
        ctx.root && ctx.root.getElementById("device-editor")?.scrollIntoView({ behavior: "smooth" });
      });
    });

    root.querySelectorAll("button[data-add-bus]").forEach((button) => {
      button.addEventListener("click", () => {
        const [address, eep, platform, gatewayId] = button.dataset.addBus.split("|");
        ctx.state.editor = {
          mode: "add",
          platform: platform || "light",
          gatewayId: Number(gatewayId),
          values: { id: address, eep: eep || "" },
          error: null,
        };
        ctx.requestContentRender(true);
        ctx.root && ctx.root.getElementById("device-editor")?.scrollIntoView({ behavior: "smooth" });
      });
    });

    root.querySelectorAll("[data-ha-device]").forEach((element) => {
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        const path = `/config/devices/device/${element.dataset.haDevice}`;
        history.pushState(null, "", path);
        window.dispatchEvent(new CustomEvent("location-changed"));
      });
    });

    root.querySelectorAll("th[data-sort]").forEach((header) => {
      header.addEventListener("click", () => {
        const column = header.dataset.sort;
        if ((ctx.state.configSort || "address") === column) {
          ctx.state.configSortDescending = !ctx.state.configSortDescending;
        } else {
          ctx.state.configSort = column;
          // newest first is the useful default for the activity columns
          ctx.state.configSortDescending = column === "count" || column === "last_seen";
        }
        ctx.requestContentRender(true);
      });
    });

    root.querySelectorAll("button[data-edit]").forEach((button) => {
      button.addEventListener("click", () => {
        const [platform, address, gatewayId] = button.dataset.edit.split("|");
        const device = (ctx.state.configuredDevices || []).find(
          (d) => d.platform === platform && d.address === address && String(d.gateway_id) === gatewayId);
        ctx.state.editor = {
          mode: "edit", platform, gatewayId: Number(gatewayId),
          values: device ? device.config : {}, originalAddress: address, error: null,
        };
        ctx.requestContentRender(true);
      });
    });

    root.querySelectorAll("button[data-remove]").forEach((button) => {
      button.addEventListener("click", async () => {
        const [platform, address, gatewayId] = button.dataset.remove.split("|");
        if (!confirm(`Remove ${platform} ${address} from the configuration?`)) return;
        const result = await ctx.api.call(WS.DEVICE_REMOVE, {
          gateway_id: Number(gatewayId), platform, address,
        });
        if (result) {
          await this.load(ctx);
          ctx.requestRender();
        }
      });
    });

    const editor = ctx.state.editor;
    if (!editor) return;

    const platformSelect = root.getElementById("editor-platform");
    if (platformSelect) {
      platformSelect.addEventListener("change", (event) => {
        // keep the values which exist in both platforms (address, name, area, eep)
        editor.values = { ...readFields(root.getElementById("device-fields")) };
        editor.platform = event.target.value;
        editor.deviceType = null;       // templates belong to one platform
        editor.error = null;
        ctx.requestContentRender(true);
      });
    }
    const gatewaySelect = root.getElementById("editor-gateway");
    if (gatewaySelect) {
      gatewaySelect.addEventListener("change", (event) => {
        editor.gatewayId = Number(event.target.value);
        editor.values = { ...readFields(root.getElementById("device-fields")) };
        ctx.requestContentRender(true);
      });
    }

    // device template: prefills EEP + sender EEP of the selected device (from the backend
    // catalog). Values stay editable - the template only fills, it does not lock anything.
    const deviceTypeSelect = root.getElementById("editor-device-type");
    if (deviceTypeSelect) {
      deviceTypeSelect.addEventListener("change", (event) => {
        editor.values = { ...readFields(root.getElementById("device-fields")) };
        editor.deviceType = event.target.value || null;

        const descriptor = ctx.state.deviceForm || { platforms: [] };
        const platform = descriptor.platforms.find((p) => p.platform === editor.platform) || {};
        const template = (platform.device_types || []).find((t) => t.value === editor.deviceType);
        if (template) {
          editor.values.eep = template.eep;
          if (template.sender_eep) {
            editor.values.sender = { ...(editor.values.sender || {}), eep: template.sender_eep };
          }
          if (!editor.values.name) editor.values.name = template.hw_type;
        }
        editor.error = null;
        ctx.requestContentRender(true);
      });
    }

    root.getElementById("editor-cancel").addEventListener("click", () => {
      ctx.state.editor = null;
      ctx.requestContentRender(true);
    });

    root.getElementById("editor-save").addEventListener("click", async () => {
      const device = readFields(root.getElementById("device-fields"));
      const payload = {
        gateway_id: editor.gatewayId,
        platform: editor.platform,
        device,
      };
      const result = editor.mode === "add"
        ? await ctx.api.call(WS.DEVICE_ADD, payload)
        : await ctx.api.call(WS.DEVICE_UPDATE, { ...payload, address: editor.originalAddress });

      if (result) {
        ctx.state.editor = null;
        ctx.api.lastError = null;
        await this.load(ctx);
        ctx.requestRender();
      } else {
        editor.values = device;
        editor.error = (ctx.api.lastError || {}).message || "Could not save the device.";
        ctx.api.lastError = null;
        ctx.requestContentRender(true);
      }
    });
  },

  _defaultGatewayId(ctx) {
    const gateways = (ctx.state.deviceForm || {}).gateways || [];
    return gateways.length ? gateways[0].id : null;
  },

  /** Teach-in hint of the selected device template (PCT14 function group / key function). */
  _deviceTypeHint(platform, deviceType) {
    if (!deviceType) return "";
    const template = (platform.device_types || []).find((t) => t.value === deviceType);
    if (!template) return "";
    const parts = [];
    if (template.pct14_function_group) {
      parts.push(`teach-in: PCT14 group ${template.pct14_function_group}, function ${template.pct14_key_function}`);
    }
    if (template.address_count > 1) parts.push(`occupies ${template.address_count} addresses`);
    return parts.join(" - ");
  },

  _filtered(ctx) {
    return (ctx.state.configuredDevices || []).filter((device) => {
      if (ctx.state.onlySilent && this._activityOf(device)) return false;
      return matchesFilter(ctx.state.configFilter, [
        device.address, device.external_address, device.name, device.eep, device.platform,
        device.area, device.gateway_name, device.source,
      ]);
    });
  },
};
