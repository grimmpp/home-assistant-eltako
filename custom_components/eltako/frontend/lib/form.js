/**
 * Renders and reads the device forms. The field descriptors are delivered by the backend
 * (eltako/devices/form), which derives them from the voluptuous schemas of the integration.
 * So the form always offers exactly what the configuration supports.
 */

import { escapeHtml } from "./utils.js";

/** One input element for a field descriptor. `prefix` is used for nested groups. */
function renderField(field, value, prefix = "") {
  const name = prefix ? `${prefix}.${field.name}` : field.name;
  const id = `field-${name.replace(/\./g, "-")}`;
  const required = field.required ? " required" : "";
  // A disabled field is still shown and still carries its value - it just cannot be changed
  // here (see the 'locked' settings of general_settings.py). readFields() keeps reading it,
  // so saving a form sends the unchanged value along instead of dropping the key.
  const disabled = field.disabled ? " disabled" : "";
  const label = `<label for="${id}">${escapeHtml(field.label)}${field.required ? " *" : ""}${
    field.disabled ? ` <span class="field-lock" title="Cannot be changed here">&#128274;</span>` : ""}</label>`;
  const help = field.help ? `<span class="field-help">${escapeHtml(field.help)}</span>` : "";
  const current = value === undefined || value === null ? "" : value;

  if (field.type === "group") {
    const groupValue = (value && typeof value === "object") ? value : {};
    return `
      <fieldset class="field-group" data-group="${escapeHtml(name)}">
        <legend>${escapeHtml(field.label)}${field.required ? " *" : ""}</legend>
        ${field.help ? `<span class="field-help">${escapeHtml(field.help)}</span>` : ""}
        ${field.fields.map((sub) => renderField(sub, groupValue[sub.name], name)).join("")}
      </fieldset>`;
  }

  let input;
  if (field.type === "select") {
    // an option is either a plain value or {value, label} - e.g. EEPs carry a description
    const options = (field.options || []).map((option) => {
      const value = option && typeof option === "object" ? option.value : option;
      const text = option && typeof option === "object" ? (option.label || option.value) : option;
      return `<option value="${escapeHtml(value)}" ${String(current) === String(value) ? "selected" : ""}>${escapeHtml(text)}</option>`;
    });
    input = `<select id="${id}" data-field="${escapeHtml(name)}" data-type="select"${required}${disabled}>
        <option value="">${field.required ? "&mdash; please select &mdash;" : "&mdash; not set &mdash;"}</option>
        ${options.join("")}
      </select>`;
  } else if (field.type === "combo") {
    // text input with suggestions (e.g. the areas of home assistant) - free text stays allowed
    const listId = `${id}-list`;
    const options = (field.options || []).map((option) =>
      `<option value="${escapeHtml(option && typeof option === "object" ? option.value : option)}"></option>`);
    input = `<input type="text" id="${id}" data-field="${escapeHtml(name)}" data-type="combo"
                    value="${escapeHtml(current)}" list="${listId}"${required}${disabled} />
             <datalist id="${listId}">${options.join("")}</datalist>`;
  } else if (field.type === "boolean") {
    const checked = current === true || current === "true" ? "checked" : "";
    input = `<input type="checkbox" id="${id}" data-field="${escapeHtml(name)}" data-type="boolean" ${checked}${disabled} />`;
  } else if (field.type === "number") {
    input = `<input type="number" id="${id}" data-field="${escapeHtml(name)}" data-type="number"
                    value="${escapeHtml(current)}" ${field.min !== undefined ? `min="${field.min}"` : ""}
                    ${field.max !== undefined ? `max="${field.max}"` : ""} step="any"${required}${disabled} />`;
  } else if (field.type === "int_list") {
    input = `<input type="text" id="${id}" data-field="${escapeHtml(name)}" data-type="int_list"
                    value="${escapeHtml(Array.isArray(current) ? current.join(", ") : current)}"
                    placeholder="e.g. 1, 2"${required}${disabled} />`;
  } else {
    // text and address
    const placeholder = field.type === "address" ? "FF-AA-80-01" : "";
    input = `<input type="text" id="${id}" data-field="${escapeHtml(name)}" data-type="${escapeHtml(field.type)}"
                    value="${escapeHtml(current)}" placeholder="${placeholder}"
                    class="${field.type === "address" ? "mono" : ""}"${required}${disabled} />`;
  }

  return `<div class="field ${field.type === "boolean" ? "field-inline" : ""}${
    field.disabled ? " field-disabled" : ""}">${label}${input}${help}</div>`;
}

export function renderFields(fields, values = {}) {
  return fields.map((field) => renderField(field, values[field.name])).join("");
}

/** Collect the values of all inputs below `root` into a nested object. */
export function readFields(root) {
  const result = {};
  root.querySelectorAll("[data-field]").forEach((input) => {
    const path = input.dataset.field.split(".");
    const type = input.dataset.type;

    let value;
    if (type === "boolean") value = input.checked;
    else if (type === "number") value = input.value === "" ? null : Number(input.value);
    else if (type === "int_list") {
      value = input.value.split(",").map((part) => part.trim()).filter((part) => part !== "").map(Number);
      if (!value.length) value = null;
    } else {
      value = input.value.trim();
      if (value === "") value = null;
      else if (type === "address") value = value.toUpperCase();
    }

    let target = result;
    while (path.length > 1) {
      const key = path.shift();
      target[key] = target[key] || {};
      target = target[key];
    }
    target[path[0]] = value;
  });

  // drop empty values and empty groups so that the backend applies its defaults
  const clean = (object) => {
    const cleaned = {};
    for (const [key, value] of Object.entries(object)) {
      if (value === null || value === undefined || value === "") continue;
      if (typeof value === "object" && !Array.isArray(value)) {
        const nested = clean(value);
        if (Object.keys(nested).length) cleaned[key] = nested;
      } else {
        cleaned[key] = value;
      }
    }
    return cleaned;
  };
  return clean(result);
}

export const FORM_STYLES = `
  .form-card { background: var(--eltako-card); border: 1px solid var(--eltako-border);
               border-radius: var(--eltako-radius); padding: 16px; margin-bottom: 14px; }
  .form-card h3 { margin: 0 0 12px; font-size: 1rem; font-weight: 500; }
  .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px 16px; }
  .field { display: flex; flex-direction: column; gap: 4px; }
  .field.field-inline { flex-direction: row; align-items: center; gap: 8px; }
  .field label { font-size: .78rem; color: var(--eltako-muted); }
  .field input, .field select { font: inherit; font-size: .85rem; padding: 7px 9px; border-radius: 8px;
                                border: 1px solid var(--eltako-border); background: var(--eltako-card);
                                color: var(--primary-text-color); width: 100%; box-sizing: border-box; }
  .field input[type=checkbox] { width: auto; }
  /* A locked field stays readable - it shows what is configured, it just cannot be edited
     here. Greyed out rather than hidden, so the value is still visible for a bug report. */
  .field-disabled input, .field-disabled select {
    opacity: .55; cursor: not-allowed; background: var(--eltako-tint); border-style: dashed;
  }
  .field-disabled label { opacity: .75; }
  .field-lock { font-size: .8em; opacity: .7; }
  .field-help { font-size: .7rem; color: var(--eltako-muted); }
  .field-group { grid-column: 1 / -1; border: 1px solid var(--eltako-border); border-radius: 10px;
                 padding: 10px 14px 14px; display: grid;
                 grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px 16px; }
  .field-group legend { font-size: .78rem; color: var(--eltako-muted); padding: 0 6px; }
  .field-group > .field-help { grid-column: 1 / -1; margin-top: -4px; }
  .form-actions { display: flex; gap: 8px; align-items: center; margin-top: 14px; }
  .form-error { color: var(--error-color, #e53935); font-size: .82rem; margin-top: 10px; }
  .settings-ok { color: var(--label-badge-green, #43a047); font-size: .82rem; margin-top: 10px; }
  .settings-head { display: flex; flex-wrap: wrap; gap: 10px 20px; justify-content: space-between;
                   font-size: .82rem; margin-bottom: 14px; }
  .settings-legend { display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
                     font-size: .72rem; color: var(--eltako-muted); }
  .origins { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 14px;
             padding-top: 12px; border-top: 1px solid var(--eltako-border); }
  .origin-row { display: inline-flex; align-items: center; gap: 5px; font-size: .75rem; }
  .origin-name { color: var(--eltako-muted); }
`;
