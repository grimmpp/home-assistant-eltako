/**
 * Input fields for the values of an EnOcean profile.
 *
 * Two places build the same form: the send fields of a device on the control page and the free
 * form on the telegram page. Both get their descriptors from `eltako/send_telegram_form`
 * (backend: core/websocket.py -> simulation/core/field_info.py), which says per field whether
 * it is a choice with named options or a number with a unit and a range - so a dropdown "on /
 * off" appears instead of a `state` nobody can guess.
 */

import { escapeHtml } from "./utils.js";

/** The descriptor of one profile out of the answer of eltako/send_telegram_form. */
export function descriptorFor(form, eep) {
  return ((form || {}).eeps || []).find(
    (item) => String(item.eep).toUpperCase() === String(eep || "").toUpperCase());
}

/** Description of a single field, with a plain number as the fallback. */
export function infoOf(descriptor, field) {
  return ((descriptor || {}).field_info || []).find((item) => item.name === field)
    || { name: field, kind: "number" };
}

/** The value of a field: what was entered, otherwise the start value of the profile. */
export function valueOf(descriptor, values, field) {
  const entered = (values || {})[field];
  if (entered !== undefined && entered !== null && entered !== "") return entered;
  const defaults = (descriptor || {}).defaults || {};
  return defaults[field] !== undefined ? defaults[field] : 0;
}

/**
 * The fields which really end up in the telegram.
 *
 * Some profiles write completely different bytes depending on one field - the central command
 * switches (1) or dims (2), a weather station reports wind or sun - and the other fields are
 * then dropped silently. Offering them anyway would promise a value which never arrives.
 */
export function relevantFields(descriptor, values) {
  const fields = (descriptor || {}).fields || [];
  const condition = (descriptor || {}).conditional;
  if (!condition) return fields;
  const chosen = Number(valueOf(descriptor, values, condition.field));
  return condition.relevant[String(chosen)] || condition.relevant[chosen] || fields;
}

/** True when changing this field changes which other fields are offered. */
export function decidesTheFields(descriptor, field) {
  return Boolean((descriptor || {}).conditional
    && descriptor.conditional.field === field);
}

/** One input: a dropdown for a choice, a number input with range and step otherwise. */
export function fieldControl(descriptor, values, field, attributes = "") {
  const info = infoOf(descriptor, field);
  const value = valueOf(descriptor, values, field);

  if (info.kind === "choice") {
    return `<select data-field="${escapeHtml(field)}" ${attributes}>
      ${(info.options || []).map((option) => `<option value="${escapeHtml(String(option.value))}"
        ${String(option.value) === String(value) ? "selected" : ""}>${
        escapeHtml(option.label)}</option>`).join("")}
    </select>`;
  }

  const range = [info.min !== undefined ? `min="${info.min}"` : "",
                 info.max !== undefined ? `max="${info.max}"` : "",
                 info.step !== undefined ? `step="${info.step}"` : ""].join(" ");
  return `<input type="number" ${range} data-field="${escapeHtml(field)}" ${attributes}
                 value="${escapeHtml(String(value))}" />`;
}

/** Label of a field: its name without underscores, plus its unit. */
export function fieldLabel(descriptor, field) {
  const info = infoOf(descriptor, field);
  return `${escapeHtml(field.replace(/_/g, " "))}${
    info.unit ? ` <span class="unit">${escapeHtml(info.unit)}</span>` : ""}`;
}

/** All fields of a profile as labelled inputs. */
export function renderFields(descriptor, values, attributes = "") {
  return relevantFields(descriptor, values).map((field) => {
    const info = infoOf(descriptor, field);
    return `<label${info.help ? ` title="${escapeHtml(info.help)}"` : ""}>
      ${fieldLabel(descriptor, field)}
      ${fieldControl(descriptor, values, field, attributes)}
    </label>`;
  }).join("");
}

/** The values to send: every relevant field as a number where it is one. */
export function collectValues(descriptor, values) {
  const result = {};
  for (const field of relevantFields(descriptor, values)) {
    const raw = valueOf(descriptor, values, field);
    result[field] = raw === "" || raw === undefined || raw === null
      ? 0 : (Number.isNaN(Number(raw)) ? raw : Number(raw));
  }
  return result;
}
