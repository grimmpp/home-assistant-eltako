/**
 * Control page: use the devices like on a Home Assistant dashboard.
 *
 * Only available in the standalone runtime (eltako_standalone) - it provides the
 * backend commands eltako/entities/* which list and control the entities. In
 * Home Assistant itself the normal dashboard does this job, so the page is
 * hidden there (see standaloneOnly in eltako-panel.js).
 */

import { escapeHtml, icon } from "../lib/utils.js";
import { WS } from "../lib/api.js";
import { collectValues, decidesTheFields, infoOf, relevantFields, renderFields }
  from "../lib/telegram_form.js";

const LIST = "eltako/entities/list";
const CALL = "eltako/entities/call";
const SUBSCRIBE = "eltako/entities/subscribe";

// which platforms are commanded through a sender: for those the telegram to send is the one of
// the *sender* profile (that is what the actuator listens to), for everything else it is the
// profile of the device itself - the telegram it would send on its own.
const SENDER_DRIVEN = ["light", "switch", "cover", "climate"];

// The teach-in button of a device is an entity of its own (button.<device>_teach_in_button),
// created for every actuator when `enable_teach_in_buttons` is on. It carries the name of its
// device and does exactly what the "teach in" button of the device row does, so it would be the
// same action twice - once under a row which says nothing but "Press". It is left out here; the
// toolbar brings it back, and the setting removes the entities altogether.
const TEACH_IN_ENTITY = /_teach_in_button$/;

const CONTROLLABLE = ["light", "switch", "cover", "climate", "select", "button"];
const READ_ONLY = ["sensor", "binary_sensor"];

// What a row is used for, in that order. A device you switch belongs above a button which
// teaches a sender in: those buttons carry the *same name* as their device ("FSR14_4x ch1"),
// so with the plain alphabetical order of the entity ids the first row of that name had a
// single "Press" on it and the light with its On/Off was 14 rows further down - which reads
// like the light cannot be switched at all.
const PLATFORM_ORDER = ["light", "switch", "cover", "climate", "select", "button",
                        "binary_sensor", "sensor"];
// shown in front of the entity id so two rows of the same name can be told apart
const PLATFORM_LABEL = {
  light: "Light", switch: "Switch", cover: "Cover", climate: "Heating/cooling",
  select: "Selection", button: "Button", sensor: "Sensor", binary_sensor: "Contact",
};

function sortForUse(entities) {
  return [...entities].sort((a, b) => {
    const byPlatform = PLATFORM_ORDER.indexOf(a.platform) - PLATFORM_ORDER.indexOf(b.platform);
    if (byPlatform !== 0) return byPlatform;
    return String(a.name || a.entity_id).localeCompare(String(b.name || b.entity_id));
  });
}

function groupByArea(entities) {
  const groups = new Map();
  for (const entity of entities) {
    const area = entity.area || "Without area";
    if (!groups.has(area)) groups.set(area, []);
    groups.get(area).push(entity);
  }
  return [...groups.entries()].sort((a, b) =>
    a[0] === "Without area" ? 1 : b[0] === "Without area" ? -1 : a[0].localeCompare(b[0]));
}

function stateText(entity) {
  const unit = (entity.attributes || {}).unit_of_measurement;
  if (entity.state === null || entity.state === undefined) return "—";
  return `${entity.state}${unit ? ` ${unit}` : ""}`;
}

function controlsFor(entity) {
  const id = escapeHtml(entity.entity_id);
  const attrs = entity.attributes || {};
  switch (entity.platform) {
    case "light": {
      const brightness = attrs.brightness ?? "";
      const dimmable = (attrs.supported_color_modes || []).includes("brightness");
      return `
        <button class="action" data-call="${id}" data-action="turn_on">On</button>
        <button class="action" data-call="${id}" data-action="turn_off">Off</button>
        ${dimmable ? `<input type="range" min="0" max="255" value="${brightness || 0}"
             data-slider="${id}" data-action="turn_on" data-field="brightness"
             title="Brightness" />` : ""}`;
    }
    case "switch":
      return `
        <button class="action" data-call="${id}" data-action="turn_on">On</button>
        <button class="action" data-call="${id}" data-action="turn_off">Off</button>`;
    case "cover": {
      const position = attrs.current_position;
      return `
        <button class="action" data-call="${id}" data-action="open_cover">▲</button>
        <button class="action" data-call="${id}" data-action="stop_cover">■</button>
        <button class="action" data-call="${id}" data-action="close_cover">▼</button>
        <input type="range" min="0" max="100" value="${position ?? 50}"
               data-slider="${id}" data-action="set_cover_position" data-field="position"
               title="Position (100 = open)" />`;
    }
    case "climate": {
      const target = attrs.temperature ?? "";
      const modes = attrs.hvac_modes || [];
      return `
        <input type="number" step="0.5" min="${attrs.min_temp ?? 5}" max="${attrs.max_temp ?? 30}"
               value="${target}" data-input="${id}" data-action="set_temperature"
               data-field="temperature" title="Target temperature" class="temp-input" />
        ${modes.length ? `<select data-select="${id}" data-action="set_hvac_mode" data-field="hvac_mode">
          ${modes.map((mode) => `<option value="${escapeHtml(mode)}"
            ${mode === entity.state ? "selected" : ""}>${escapeHtml(mode)}</option>`).join("")}
        </select>` : ""}`;
    }
    case "select": {
      const options = attrs.options || [];
      return `<select data-select="${id}" data-action="select_option" data-field="option">
        ${options.map((option) => `<option value="${escapeHtml(option)}"
          ${option === entity.state ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}
      </select>`;
    }
    case "button":
      return `<button class="action" data-call="${id}" data-action="press">Press</button>`;
    default:
      return "";
  }
}

// TODO type check: add /** @type {import("../types.js").Page} */ once the dom casts are in
export const page = {
  id: "control",
  title: "Control",
  subtitle: "Use your devices - switch, dim, move, adjust",
  icon: "mdi:toggle-switch-outline",
  glyph: "⏻",
  standaloneOnly: true,
  modes: ["user", "expert"],
  refreshMs: 3000,

  styles: `
    .control-area { margin-bottom: 18px; }
    .control-area h3 { margin: 12px 0 6px; opacity: .75; }
    .control-row td { vertical-align: middle; }
    .control-row input[type=range] { vertical-align: middle; width: 130px; }
    .control-row .temp-input { width: 70px; }
    .control-row .entity-state { font-variant-numeric: tabular-nums; white-space: nowrap; }
    .control-row .call-error { color: #b71c1c; font-size: 12px; }
    .control-sub { opacity: .6; font-size: 12px; }
    .control-row .kind { opacity: .55; font-size: 12px; margin-left: 6px; }
    .send-row td { background: var(--eltako-tint); }
    .send-form { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; padding: 6px 0; }
    .send-form label { display: flex; flex-direction: column; font-size: 12px; opacity: .8; }
    .send-form input, .send-form select { width: 118px; }
    .send-form .unit { opacity: .6; }
    .send-form .send-note { font-size: 12px; }
  `,

  async load(ctx) {
    const result = await ctx.api.call(LIST);
    if (result) ctx.state.controlEntities = result.entities || [];
    // The configuration says which telegram belongs to a device (its EEP, its sender) and
    // whether its sender is taught in; the send form says which values that telegram carries.
    // The device list is re-read on every refresh - it is what says whether a device is taught
    // in, and that changes while the page is open. The profiles never change: read once.
    // (The state starts as an empty array, so `if (!devices)` would never load anything -
    // an empty array is truthy. That is why the length is what decides here.)
    const devices = await ctx.api.call(WS.DEVICE_LIST);
    if (devices) ctx.state.configuredDevices = devices.devices || [];
    if (!(ctx.state.telegramForm || {}).eeps) {
      const form = await ctx.api.call(WS.SEND_TELEGRAM_FORM);
      if (form) ctx.state.telegramForm = form;
    }
    this._subscribe(ctx);
  },

  /** The configured device an entity belongs to - matched through its entity id. */
  _deviceOf(ctx, entity) {
    const devices = ctx.state.configuredDevices || [];
    return devices.find((device) => (device.entity_ids || []).includes(entity.entity_id))
      || devices.find((device) => String(device.address || "").toUpperCase()
           === String(entity.address || "").toUpperCase()
           && String(device.gateway_id) === String(entity.gateway_id));
  },

  /**
   * What can be sent for this device: the address it is sent from, the profile and its values.
   *
   * For an actuator that is its **sender** (the address Home Assistant switches it with, out of
   * the configuration) - a relay does not listen to its own address. For a sensor or a contact
   * it is the device itself: the telegram it reports with.
   */
  _telegramOf(ctx, entity, device) {
    if (!device) return null;
    const sender = device.sender || {};
    const useSender = SENDER_DRIVEN.includes(entity.platform) && sender.id && sender.eep;
    const eep = useSender ? sender.eep : device.eep;
    const address = useSender ? sender.id : device.address;
    if (!eep || !address) return null;

    const descriptor = ((ctx.state.telegramForm || {}).eeps || [])
      .find((item) => String(item.eep).toUpperCase() === String(eep).toUpperCase());
    // sendable === false: the library can only decode this profile (A5-09-0C for instance) -
    // a form which can only fail is worse than none
    if (!descriptor || !(descriptor.fields || []).length
        || descriptor.sendable === false) return null;

    return { eep, address, gatewayId: device.gateway_id, role: useSender ? "sender" : "device",
             descriptor, description: descriptor.description };
  },

  /** The values entered for this device so far - the form falls back to the start values. */
  _sendValues(ctx, entityId) {
    return (ctx.state.controlSendValues || {})[entityId] || {};
  },

  /**
   * Whether the sender of Home Assistant is taught into this actuator.
   *
   * `true` / `false` come from the device memory of a bus device, `null` means it cannot be
   * told - a wireless actuator answers no such question. Only a device with a sender can be
   * taught in at all: that address is what the actuator has to learn.
   */
  _teachIn(ctx, entity, device) {
    if (!device || !SENDER_DRIVEN.includes(entity.platform)) return null;
    const sender = device.sender || {};
    if (!sender.id || !sender.eep) return null;
    return { senderId: sender.id, eep: sender.eep, gatewayId: device.gateway_id,
             address: device.address, state: device.sender_taught_in };
  },

  _renderTeachInButton(ctx, entity, teachIn) {
    if (!teachIn || teachIn.state === true) return "";
    const known = teachIn.state === false;
    return `<button class="action small ${known ? "primary" : ""}"
              data-teach-in="${escapeHtml(entity.entity_id)}"
              title="${known
                ? `The sender ${escapeHtml(teachIn.senderId)} is not in the memory of this device - `
                  + `without it no command reaches it.`
                : `Teach the sender ${escapeHtml(teachIn.senderId)} in. Whether it already is `
                  + `cannot be told for this device - read the bus memory to find out.`}"
            >teach in${known ? " (missing)" : ""}</button>`;
  },

  _renderSendForm(ctx, entity, telegram) {
    const id = entity.entity_id;
    // the fields, the named options and the units all come from the profile itself - the same
    // renderer the free send form of the telegram page uses (lib/telegram_form.js)
    const fields = renderFields(telegram.descriptor, this._sendValues(ctx, id),
                                `data-send-entity="${escapeHtml(id)}"`);

    return `
      <tr class="send-row" data-send-row="${escapeHtml(id)}">
        <td colspan="4">
          <div class="send-form">
            <span class="hint">${escapeHtml(telegram.eep)}
              ${telegram.role === "sender" ? "as sender" : "as the device itself"}
              <span class="mono">${escapeHtml(telegram.address)}</span></span>
            ${fields}
            <button class="action primary" data-send="${escapeHtml(id)}">Send</button>
            <span class="send-note" data-send-note="${escapeHtml(id)}">${
              escapeHtml((ctx.state.controlSendNotes || {})[id] || "")}</span>
          </div>
        </td>
      </tr>`;
  },

  _subscribe(ctx) {
    if (this._unsubscribe) return;
    this._unsubscribe = ctx.api.hass.connection.subscribeMessage((event) => {
      const entities = ctx.state.controlEntities || [];
      const entity = entities.find((item) => item.entity_id === event.entity_id);
      if (entity) {
        entity.state = event.state;
        entity.attributes = event.attributes;
        const root = ctx.root;
        const row = root && root.querySelector(
          `tr[data-entity="${event.entity_id.replace(/"/g, "")}"] .entity-state`);
        if (row) row.textContent = stateText(entity);
      }
    }, { type: SUBSCRIBE }).catch(() => { this._unsubscribe = null; });
  },

  renderToolbar(ctx) {
    return `
      <input id="control-filter" type="search" placeholder="Filter name or entity id&hellip;"
             value="${escapeHtml(ctx.state.controlFilter || "")}" />
      <label><input type="checkbox" id="control-show-sensors"
             ${ctx.state.controlShowSensors ? "checked" : ""}/> show sensors</label>
      <label title="One entity per actuator which sends the teach-in telegram. The same action
                    sits in the row of the device itself, so they are hidden."><input
             type="checkbox" id="control-show-teach-in"
             ${ctx.state.controlShowTeachInButtons ? "checked" : ""}/> show teach-in buttons</label>`;
  },

  bindToolbar(ctx, root) {
    root.getElementById("control-filter").addEventListener("input", (event) => {
      ctx.state.controlFilter = event.target.value;
      ctx.requestContentRender();
    });
    root.getElementById("control-show-sensors").addEventListener("change", (event) => {
      ctx.state.controlShowSensors = event.target.checked;
      ctx.requestContentRender();
    });
    root.getElementById("control-show-teach-in").addEventListener("change", (event) => {
      ctx.state.controlShowTeachInButtons = event.target.checked;
      ctx.requestContentRender();
    });
  },

  render(ctx) {
    const all = ctx.state.controlEntities || [];
    if (!all.length) {
      return `<div class="empty">No entities. Configure devices on the
              'Device config' page first.</div>`;
    }

    const filter = (ctx.state.controlFilter || "").toLowerCase();
    const platforms = ctx.state.controlShowSensors
      ? [...CONTROLLABLE, ...READ_ONLY] : CONTROLLABLE;
    const entities = all.filter((entity) =>
      platforms.includes(entity.platform) &&
      (ctx.state.controlShowTeachInButtons || !TEACH_IN_ENTITY.test(entity.entity_id)) &&
      (!filter || entity.entity_id.toLowerCase().includes(filter) ||
        (entity.name || "").toLowerCase().includes(filter)));

    if (!entities.length) return `<div class="empty">Nothing matches the filter.</div>`;

    return groupByArea(entities).map(([area, items]) => `
      <div class="control-area">
        <h3>${icon("mdi:map-marker-outline", "📍")} ${escapeHtml(area)}</h3>
        <table>
          <tbody>
            ${sortForUse(items).map((entity) => {
              const device = this._deviceOf(ctx, entity);
              const telegram = this._telegramOf(ctx, entity, device);
              const teachIn = this._teachIn(ctx, entity, device);
              const open = (ctx.state.controlSendOpen || {})[entity.entity_id];
              return `
              <tr class="control-row" data-entity="${escapeHtml(entity.entity_id)}">
                <td>
                  ${escapeHtml(entity.name || entity.entity_id)}
                  <span class="kind">${escapeHtml(PLATFORM_LABEL[entity.platform]
                    || entity.platform)}</span>
                  <div class="control-sub mono">${escapeHtml(entity.entity_id)}
                    ${entity.eep ? `· ${escapeHtml(entity.eep)}` : ""}</div>
                </td>
                <td class="entity-state">${escapeHtml(stateText(entity))}</td>
                <td class="controls">${controlsFor(entity)}
                  ${this._renderTeachInButton(ctx, entity, teachIn)}
                  ${telegram ? `<button class="action small" data-send-toggle="${
                    escapeHtml(entity.entity_id)}" title="Build a telegram out of the values of ${
                    escapeHtml(telegram.eep)} and send it">${open ? "close" : "telegram&hellip;"}</button>` : ""}</td>
                <td class="call-error" data-error="${escapeHtml(entity.entity_id)}"></td>
              </tr>
              ${telegram && open ? this._renderSendForm(ctx, entity, telegram) : ""}`;
            }).join("")}
          </tbody>
        </table>
      </div>`).join("");
  },

  afterRender(ctx, root) {
    const call = async (entityId, action, data) => {
      const result = await ctx.api.call(CALL, { entity_id: entityId, action, data: data || {} });
      const errorCell = root.querySelector(`[data-error="${entityId.replace(/"/g, "")}"]`);
      if (errorCell) {
        errorCell.textContent = result === null && ctx.api.lastError
          ? ctx.api.lastError.message : "";
      }
    };

    root.querySelectorAll("[data-call]").forEach((button) => {
      button.addEventListener("click", () =>
        call(button.dataset.call, button.dataset.action));
    });
    root.querySelectorAll("[data-slider]").forEach((slider) => {
      slider.addEventListener("change", () =>
        call(slider.dataset.slider, slider.dataset.action,
             { [slider.dataset.field]: Number(slider.value) }));
    });
    root.querySelectorAll("[data-input]").forEach((input) => {
      input.addEventListener("change", () =>
        call(input.dataset.input, input.dataset.action,
             { [input.dataset.field]: Number(input.value) }));
    });
    root.querySelectorAll("[data-select]").forEach((select) => {
      select.addEventListener("change", () =>
        call(select.dataset.select, select.dataset.action,
             { [select.dataset.field]: select.value }));
    });

    root.querySelectorAll("[data-teach-in]").forEach((button) => {
      button.addEventListener("click", async () => {
        const entityId = button.dataset.teachIn;
        const entity = (ctx.state.controlEntities || [])
          .find((item) => item.entity_id === entityId);
        const teachIn = entity && this._teachIn(ctx, entity, this._deviceOf(ctx, entity));
        if (!teachIn) return;

        button.disabled = true;
        const result = await ctx.api.call(WS.DEVICE_TEACH_IN,
          { gateway_id: teachIn.gatewayId, address: teachIn.address });
        button.disabled = false;

        const errorCell = root.querySelector(`[data-error="${entityId.replace(/"/g, "")}"]`);
        if (errorCell) {
          errorCell.textContent = result
            ? (result.kind === "bus_memory" ? "written into the device memory"
                                            : "teach-in telegram sent")
            : ((ctx.api.lastError || {}).message || "teach-in failed");
        }
      });
    });

    root.querySelectorAll("[data-send-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const id = button.dataset.sendToggle;
        const open = ctx.state.controlSendOpen || (ctx.state.controlSendOpen = {});
        if (open[id]) delete open[id]; else open[id] = true;
        ctx.requestContentRender();
      });
    });

    root.querySelectorAll("[data-send-entity]").forEach((input) => {
      const remember = () => {
        const values = ctx.state.controlSendValues || (ctx.state.controlSendValues = {});
        const entityValues = values[input.dataset.sendEntity]
          || (values[input.dataset.sendEntity] = {});
        entityValues[input.dataset.field] = input.value;
      };
      input.addEventListener("input", remember);
      input.addEventListener("change", () => {
        remember();
        // the deciding field of a profile changes which other fields are read at all
        const entity = (ctx.state.controlEntities || [])
          .find((item) => item.entity_id === input.dataset.sendEntity);
        const telegram = entity && this._telegramOf(ctx, entity, this._deviceOf(ctx, entity));
        if (telegram && decidesTheFields(telegram.descriptor, input.dataset.field)) {
          ctx.requestContentRender();
        }
      });
    });

    root.querySelectorAll("[data-send]").forEach((button) => {
      button.addEventListener("click", async () => {
        const entityId = button.dataset.send;
        const entity = (ctx.state.controlEntities || [])
          .find((item) => item.entity_id === entityId);
        const telegram = entity
          && this._telegramOf(ctx, entity, this._deviceOf(ctx, entity));
        if (!telegram) return;

        const fields = collectValues(telegram.descriptor, this._sendValues(ctx, entityId));

        const result = await ctx.api.call(WS.SEND_TELEGRAM, {
          gateway_id: telegram.gatewayId, sender_id: telegram.address,
          eep: telegram.eep, fields,
        });
        const notes = ctx.state.controlSendNotes || (ctx.state.controlSendNotes = {});
        notes[entityId] = result && result.sent ? `sent: ${result.telegram}`
          : `not sent: ${(ctx.api.lastError || {}).message || "unknown error"}`;
        const note = root.querySelector(`[data-send-note="${entityId.replace(/"/g, "")}"]`);
        if (note) note.textContent = notes[entityId];
      });
    });
  },

  /** an open send form must not be thrown away by the refresh timer while it is being filled */
  isEditing(ctx) {
    return Object.keys(ctx.state.controlSendOpen || {}).length > 0;
  },
};
