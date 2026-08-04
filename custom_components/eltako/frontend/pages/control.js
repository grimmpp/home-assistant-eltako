/**
 * Control page: use the devices like on a Home Assistant dashboard.
 *
 * Only available in the standalone runtime (eltako_standalone) - it provides the
 * backend commands eltako/entities/* which list and control the entities. In
 * Home Assistant itself the normal dashboard does this job, so the page is
 * hidden there (see standaloneOnly in eltako-panel.js).
 */

import { escapeHtml, icon } from "../lib/utils.js";

const LIST = "eltako/entities/list";
const CALL = "eltako/entities/call";
const SUBSCRIBE = "eltako/entities/subscribe";

const CONTROLLABLE = ["light", "switch", "cover", "climate", "select", "button"];
const READ_ONLY = ["sensor", "binary_sensor"];

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

export const page = {
  id: "control",
  title: "Control",
  subtitle: "Use your devices - switch, dim, move, adjust",
  icon: "mdi:toggle-switch-outline",
  glyph: "⏻",
  standaloneOnly: true,
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
  `,

  async load(ctx) {
    const result = await ctx.api.call(LIST);
    if (result) ctx.state.controlEntities = result.entities || [];
    this._subscribe(ctx);
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
             ${ctx.state.controlShowSensors ? "checked" : ""}/> show sensors</label>`;
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
      (!filter || entity.entity_id.toLowerCase().includes(filter) ||
        (entity.name || "").toLowerCase().includes(filter)));

    if (!entities.length) return `<div class="empty">Nothing matches the filter.</div>`;

    return groupByArea(entities).map(([area, items]) => `
      <div class="control-area">
        <h3>${icon("mdi:map-marker-outline", "📍")} ${escapeHtml(area)}</h3>
        <table>
          <tbody>
            ${items.map((entity) => `
              <tr class="control-row" data-entity="${escapeHtml(entity.entity_id)}">
                <td>
                  ${escapeHtml(entity.name || entity.entity_id)}
                  <div class="control-sub mono">${escapeHtml(entity.entity_id)}
                    ${entity.eep ? `· ${escapeHtml(entity.eep)}` : ""}</div>
                </td>
                <td class="entity-state">${escapeHtml(stateText(entity))}</td>
                <td class="controls">${controlsFor(entity)}</td>
                <td class="call-error" data-error="${escapeHtml(entity.entity_id)}"></td>
              </tr>`).join("")}
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
  },
};
