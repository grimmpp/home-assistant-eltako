/**
 * "What *is* this thing?" - the popup with everything about one device or one gateway.
 *
 * A table row and a device card show what a user acts on: name, state, switch. Everything
 * which answers what the thing actually is - address, profile, gateway, sender and whether it
 * is taught in, its entities, when it last reported, where its configuration comes from -
 * does not fit there and used to be spread over several pages, or nowhere.
 *
 * Both views use this: the cards of the simple view (pages/home.js) and the tables of the
 * expert view (pages/devices_config.js), so the same button says the same thing everywhere.
 *
 * The way into Home Assistant lives here as well: inside Home Assistant the popup offers the
 * device page as a button, the standalone runtime has none and does not show it.
 */

import { escapeHtml, formatDecoded } from "./utils.js";

export const DETAILS_STYLES = `
  /* The popup is fixed to the viewport, so the panel moves it out of the page content into
     the shell (see _renderContent) - ancestors of the panel use css transforms, which would
     turn "fixed" into "absolute inside that ancestor". */
  .modal-overlay { position: fixed; inset: 0; z-index: 40; display: flex; align-items: center;
                   justify-content: center; padding: 16px;
                   background: color-mix(in srgb, #000 45%, transparent); }
  .modal-card { background: var(--eltako-card); border: 1px solid var(--eltako-border);
                border-radius: var(--eltako-radius); padding: 16px 18px; width: min(560px, 100%);
                max-height: 85vh; overflow: auto; display: flex; flex-direction: column; gap: 12px;
                box-shadow: 0 12px 40px rgba(0,0,0,.28); }
  /* a form needs more room than a list of facts: two columns of the form grid side by side
     instead of one, otherwise every field is its own line and the popup is a tower */
  .modal-card.modal-wide { width: min(760px, 100%); }
  /* the form actions of a popup sit at its bottom edge, not floating under the last field */
  .modal-card .form-actions { margin-top: 4px; flex-wrap: wrap; }
  .modal-head { display: flex; align-items: center; gap: 10px; }
  .modal-head h3 { margin: 0; font-size: 1rem; overflow-wrap: anywhere; }
  .modal-head ha-icon, .modal-head .glyph { --mdc-icon-size: 24px; color: var(--eltako-accent); }
  .modal-head .spacer { flex: 1 1 auto; }
  .modal-card .meta-grid { display: grid; grid-template-columns: minmax(120px, auto) 1fr;
                           gap: 4px 14px; margin: 0; font-size: .85rem; align-items: baseline; }
  .modal-card .meta-grid dt { color: var(--eltako-muted); }
  .modal-card .meta-grid dd { margin: 0; overflow-wrap: anywhere; }
  .modal-card .meta-section h4 { font-size: .8rem; font-weight: 500; margin: 0 0 6px;
                                 color: var(--eltako-muted); }
  .modal-card .meta-section .device-states { display: flex; flex-wrap: wrap; gap: 5px; }
  .modal-card .modal-note { font-size: .78rem; color: var(--eltako-muted); }
  .modal-card .modal-note.warn { color: var(--eltako-warn); }
  /* what an address could be: one line per candidate profile with its models (see the
     "unknown" popup of the telegram page) */
  .modal-card .candidate-list { display: flex; flex-direction: column; gap: 8px; }
  .modal-card .candidate-list .candidate { font-size: .82rem; display: flex; flex-wrap: wrap;
                                           align-items: baseline; gap: 6px; }
  .modal-card .candidate-list .candidate-models { flex-basis: 100%; display: flex;
                                                  flex-wrap: wrap; gap: 4px; }
  /* what this telegram means read as that profile - the evidence a human judges by */
  .modal-card .candidate-values { flex-basis: 100%; display: flex; flex-wrap: wrap; gap: 4px; }
`;

/**
 * The popup of an *unknown* address: what was seen and what it could be.
 *
 * `entry` is one item of `statistics.unknown_devices` (observation/telegram_suggestions.py:
 * the backend already derived the possible profiles with their confidence and the models of
 * the catalog which speak them), `telegram` the record the popup was opened from. Either of
 * them may be missing - an address which just sent its first telegram is not in the
 * statistics yet, and the statistics know addresses whose telegram has scrolled out.
 */
export function unknownDetails(entry, telegram, options = {}) {
  const seen = entry || {};
  const record = telegram || {};
  const best = seen.suggested || {};
  const address = seen.address || record.address;
  const messageTypes = Object.keys(seen.msg_types || {}).join(", ") || record.msg_type;

  return {
    icon: options.icon || ["mdi:help-circle-outline", "?"],
    title: address,
    subtitle: "Not configured yet",
    haDeviceId: null,
    editable: false,
    entities: [],
    rows: [
      ["Address", address, true],
      ["Address on the bus", seen.local_address || record.local_address, true],
      ["Gateway", (seen.gateway_ids || []).join(", ") || record.gateway_name || record.gateway_id],
      ["Message types", messageTypes],
      ["Telegrams seen", seen.count],
      ["First seen", options.firstSeen],
      ["Last seen", options.lastSeen],
      ["Last data", seen.last_data || record.data || record.payload, true],
      ["Signal", record.rssi_dbm === null || record.rssi_dbm === undefined
        ? null : `${record.rssi_dbm} dBm`],
      ["Probably a profile", best.eep ? `${best.eep}${best.confidence ? ` (${best.confidence})` : ""}` : null],
      ["Probably a device", best.hw_type],
      ...(options.rows || []),
    ],
    extra: renderCandidates(seen.suggestions || []),
    note: best.eep ? null
      : "No profile could be derived yet. A device usually reveals itself with the next "
        + "telegram which carries data - press its button again, or teach it in (4BS).",
  };
}

/** The possible profiles of an unknown address, each with the models which speak it. */
export function renderCandidates(candidates) {
  if (!candidates.length) return "";

  return `
    <div class="meta-section">
      <h4>What it could be</h4>
      <div class="candidate-list">
        ${candidates.map((candidate) => `
          <div class="candidate">
            <span class="mono">${escapeHtml(candidate.eep)}</span>
            <span class="tag ${candidate.confidence === "confirmed" ? "taught"
              : candidate.confidence === "likely" ? "role" : "unknown"}"
              >${escapeHtml(candidate.confidence || "")}</span>
            <span class="hint">${escapeHtml(candidate.reason || "")}</span>
            ${candidate.decoded ? `
              <span class="candidate-values">${formatDecoded(candidate.decoded, 6)}</span>` : ""}
            ${(candidate.devices || []).length ? `
              <span class="candidate-models">${candidate.devices.map((model) => `
                <span class="chip" title="${escapeHtml([model.hw_type, model.brand, model.description,
                  model.platform].filter(Boolean).join(" - "))}">${escapeHtml(model.hw_type)}</span>`).join("")}
              </span>` : ""}
          </div>`).join("")}
      </div>
    </div>`;
}

/** The device page exists in Home Assistant only - the standalone runtime has none. */
export function canOpenInHa(haDeviceId) {
  return !!haDeviceId && !window.eltakoStandalone;
}

/**
 * Open the device page of Home Assistant.
 *
 * The panel lives in a shadow root, so the event which tells the router about the new url is
 * fired from the host element with `composed: true` - an event which does not leave the
 * shadow root never reaches it.
 */
export function openInHomeAssistant(ctx, haDeviceId) {
  history.pushState(null, "", `/config/devices/device/${haDeviceId}`);
  const target = (ctx.root && ctx.root.host) || window;
  target.dispatchEvent(new CustomEvent("location-changed",
    { detail: { replace: false }, bubbles: true, composed: true }));
}

/**
 * The rows of one device. `options.entities` are the entities with their state (the pages
 * know them), `options.icon`/`options.subtitle` how the device is named in that view.
 */
export function deviceDetails(device, options = {}) {
  const sender = device.sender || {};
  return {
    icon: options.icon || ["mdi:chip", "▪"],
    title: device.name || device.address,
    subtitle: options.subtitle || device.platform,
    haDeviceId: canOpenInHa(device.ha_device_id) ? device.ha_device_id : null,
    editable: device.editable,
    entities: options.entities || [],
    rows: [
      ["Address", device.address, true],
      ["Address on the radio", device.external_address, true],
      ["Room", device.area || "not assigned"],
      ["Profile (EEP)", device.eep, true],
      ["Gateway", device.gateway_name || `Gateway ${device.gateway_id}`],
      ["Sender address", sender.id, true],
      ["Sender profile", sender.eep, true],
      ["Taught into the device", device.sender_taught_in === null
        || device.sender_taught_in === undefined ? null
        : device.sender_taught_in ? "yes" : "no - it will not react yet"],
      ["Last reported", options.lastSeen],
      ["Comes from", device.source === "yaml" ? "configuration.yaml" : "the web ui"],
      ["Simulated", device.simulated ? "yes - no hardware behind it" : null],
      ...(options.rows || []),
    ],
    note: device.editable ? null
      : "This device is declared in <code>configuration.yaml</code> and can only be changed there.",
  };
}

/** The rows of one gateway. `options.deviceCount` is how many devices talk through it. */
export function gatewayDetails(gateway, options = {}) {
  return {
    icon: options.icon || ["mdi:router-wireless", "((‧))"],
    title: gateway.name,
    subtitle: gateway.type || "Gateway",
    haDeviceId: canOpenInHa(gateway.ha_device_id) ? gateway.ha_device_id : null,
    editable: false,
    entities: [],
    rows: [
      ["Status", gateway.connected ? "connected" : "not connected"],
      ["Number", gateway.id],
      ["Model", gateway.model],
      ["Connection", gateway.serial_path, true],
      ["Base id", gateway.base_id, true],
      ["Protocol", gateway.native_protocol],
      ["Baud rate", gateway.baud_rate],
      ["Reconnects by itself", gateway.auto_reconnect ? "yes" : "no"],
      ["Devices on it", options.deviceCount],
      ["Simulated", gateway.simulated ? "yes - no hardware behind it" : null],
      ...(options.rows || []),
    ],
    note: gateway.connected ? null
      : "No connection. Check the plug, the port and the power supply - as long as this gateway "
        + "is offline none of its devices reacts.",
    noteWarn: !gateway.connected,
  };
}

/**
 * The bare popup: the darkened backdrop, the card and the head with its close button - and
 * `body` inside it.
 *
 * The details popup is one thing which goes in there, a form is another: a page which has to
 * show a form without taking the user away from the list it belongs to wraps it in here
 * instead of building a second overlay of its own. The panel moves every
 * `aside.modal-overlay` out of the scrolling page into the shell (see eltako-panel
 * `_renderContent`), so this markup is what makes a popup a popup.
 *
 * `options.closeId` and `options.backdrop` name the hooks the page binds (see `bindModal`) -
 * two popups on one page must not answer to the same ids.
 *
 * @param {(name: string, glyph: string) => string} icon the icon helper of the page
 */
export function renderModal(options, icon, body) {
  const { title, subtitle = "", id = "", wide = false,
          closeId = "modal-close", backdrop = "data-modal-backdrop" } = options;
  const parts = options.icon || ["mdi:chip", "▪"];

  return `
    <aside class="modal-overlay" ${backdrop}>
      <div class="modal-card ${wide ? "modal-wide" : ""}" ${id ? `id="${escapeHtml(id)}"` : ""}
           role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
        <div class="modal-head">
          ${icon(parts[0], parts[1])}
          <div style="min-width:0">
            <h3>${escapeHtml(title)}</h3>
            ${subtitle ? `<div class="device-kind">${escapeHtml(subtitle)}</div>` : ""}
          </div>
          <span class="spacer"></span>
          <button class="action small" id="${escapeHtml(closeId)}" aria-label="Close">&times;</button>
        </div>
        ${body}
      </div>
    </aside>`;
}

/**
 * The ways out of a popup which are the same everywhere: the ×, the button which says close,
 * and a click next to the card. `options` names the hooks `renderModal` was given.
 */
export function bindModal(root, close, options = {}) {
  const { closeId = "modal-close", doneId = null,
          backdrop = "[data-modal-backdrop]" } = options;
  root.getElementById(closeId)?.addEventListener("click", close);
  if (doneId) root.getElementById(doneId)?.addEventListener("click", close);
  root.querySelector(backdrop)?.addEventListener("click", (event) => {
    // a click inside the popup must not close it
    if (event.target === event.currentTarget) close();
  });
}

/**
 * The popup itself. `parts` is what deviceDetails/gatewayDetails returned, `actions` the
 * buttons of the page (rename, remove, ...) as markup - every page has its own handlers for
 * those, so they carry the attributes that page already binds.
 *
 * @param {(name: string, glyph: string) => string} icon the icon helper of the page
 */
export function renderDetails(parts, icon, actions = "") {
  if (!parts) return "";

  return renderModal({
    icon: parts.icon, title: parts.title, subtitle: parts.subtitle,
    closeId: "details-close", backdrop: "data-details-backdrop",
  }, icon, `
        <dl class="meta-grid">
          ${parts.rows.filter(([, value]) => value !== null && value !== undefined && value !== "")
            .map(([label, value, mono]) => `
            <dt>${escapeHtml(label)}</dt>
            <dd class="${mono ? "mono" : ""}">${escapeHtml(String(value))}</dd>`).join("")}
        </dl>
        ${(parts.entities || []).length ? `
          <div class="meta-section">
            <h4>Entities in Home Assistant</h4>
            <div class="device-states">${parts.entities.map((entity) => `
              <span class="state-chip" data-entity="${escapeHtml(entity.entityId)}">
                <span class="chip-label">${escapeHtml(entity.entityId)}</span>
                <b>${escapeHtml(entity.text || "no value yet")}</b></span>`).join("")}</div>
          </div>` : ""}
        ${parts.extra || ""}
        ${parts.note ? `<div class="modal-note ${parts.noteWarn ? "warn" : ""}">${parts.note}</div>` : ""}
        <div class="form-actions">
          ${parts.haDeviceId ? `<button class="action primary" data-ha-device="${escapeHtml(parts.haDeviceId)}"
            >${icon("mdi:open-in-new", "↗")} Open in Home Assistant</button>` : ""}
          ${actions}
          <span class="spacer"></span>
          <button class="action" id="details-done">Close</button>
        </div>`);
}

/** The three ways out of the popup which are the same everywhere: ×, Close, click next to it. */
export function bindDetails(root, close) {
  bindModal(root, close, {
    closeId: "details-close", doneId: "details-done", backdrop: "[data-details-backdrop]",
  });
}
