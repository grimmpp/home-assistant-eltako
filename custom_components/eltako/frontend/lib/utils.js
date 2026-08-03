/** Small helpers shared by all pages of the Eltako panel. */

export function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

export function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  return isNaN(number) ? escapeHtml(value) : number.toLocaleString();
}

export function formatBoolean(value) {
  if (value === null || value === undefined) return "-";
  return value ? "yes" : "no";
}

export function formatInterval(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  if (seconds >= 3600) return `${(seconds / 3600).toFixed(1)} h`;
  if (seconds >= 60) return `${(seconds / 60).toFixed(1)} min`;
  return `${Number(seconds).toFixed(seconds < 1 ? 2 : 1)} s`;
}

export function formatTime(isoString) {
  if (!isoString) return "-";
  const date = new Date(isoString);
  if (isNaN(date.getTime())) return escapeHtml(isoString);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) +
    `.${String(date.getMilliseconds()).padStart(3, "0")}`;
}

export function formatDateTime(isoString) {
  if (!isoString) return "-";
  const date = new Date(isoString);
  return isNaN(date.getTime()) ? escapeHtml(isoString) : date.toLocaleString();
}

export function formatDuration(fromIsoString) {
  if (!fromIsoString) return "-";
  const start = new Date(fromIsoString).getTime();
  if (isNaN(start)) return "-";
  const seconds = Math.max(0, Math.round((Date.now() - start) / 1000));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days} d ${hours} h`;
  if (hours) return `${hours} h ${minutes} min`;
  if (minutes) return `${minutes} min`;
  return `${seconds} s`;
}

/** One value of a decoded EEP as readable text. */
export function formatDecodedValue(value) {
  if (value === true) return "yes";
  if (value === false) return "no";
  if (typeof value === "number") return String(Number.isInteger(value) ? value : Math.round(value * 100) / 100);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** All values of a decoded EEP as one searchable string, e.g. for the filter. */
export function decodedToText(decoded) {
  if (!decoded || typeof decoded !== "object") return "";
  return Object.entries(decoded)
    .filter(([key]) => key !== "eep_string")
    .map(([key, value]) => `${key}=${formatDecodedValue(value)}`)
    .join(" ");
}

/**
 * Values of a decoded EEP as compact key/value chips. Values which are `false` are hidden
 * by default to keep overview tables short - pass `skipFalse: false` to show them.
 */
export function formatDecoded(decoded, limit = 6, { skipFalse = true } = {}) {
  if (!decoded || typeof decoded !== "object") return "";
  const entries = Object.entries(decoded)
    .filter(([key, value]) => key !== "eep_string" && value !== null && value !== undefined &&
      !(skipFalse && value === false));
  const chips = entries
    .slice(0, limit)
    .map(([key, value]) => `<span class="kv"><i>${escapeHtml(key)}</i>${escapeHtml(formatDecodedValue(value))}</span>`)
    .join(" ");
  return entries.length > limit ? `${chips} <span class="kv more">+${entries.length - limit}</span>` : chips;
}

export function basename(path) {
  if (!path) return "-";
  const parts = String(path).split(/[\\/]/);
  return parts[parts.length - 1];
}

/**
 * Home Assistant provides <ha-icon>. If it is not available (e.g. the panel is opened
 * standalone) a unicode glyph is rendered instead.
 */
export function icon(mdiName, fallbackGlyph = "●") {
  if (typeof customElements !== "undefined" && customElements.get("ha-icon")) {
    return `<ha-icon icon="${escapeHtml(mdiName)}"></ha-icon>`;
  }
  return `<span class="glyph">${fallbackGlyph}</span>`;
}

export function card(label, value, modifier = "", hint = "") {
  return `
    <div class="card ${modifier}">
      <span class="card-value">${value}</span>
      <span class="card-label">${escapeHtml(label)}</span>
      ${hint ? `<span class="card-hint">${escapeHtml(hint)}</span>` : ""}
    </div>`;
}

export function chip(label, value) {
  return `<span class="chip">${escapeHtml(label)}${value === undefined ? "" : ` <b>${formatNumber(value)}</b>`}</span>`;
}

export function definitionRows(rows) {
  return rows
    .map(([label, value]) => `<tr><th>${escapeHtml(label)}</th><td>${value === null || value === undefined || value === "" ? "-" : value}</td></tr>`)
    .join("");
}

export function sortRows(rows, column, descending) {
  const factor = descending ? -1 : 1;
  return rows.slice().sort((a, b) => {
    const left = a[column];
    const right = b[column];
    if (left === right) return 0;
    if (left === null || left === undefined) return 1;
    if (right === null || right === undefined) return -1;
    if (typeof left === "number" && typeof right === "number") return (left - right) * factor;
    return String(left).localeCompare(String(right)) * factor;
  });
}

export function matchesFilter(needle, values) {
  const filter = (needle || "").trim().toLowerCase();
  if (!filter) return true;
  return values.some((value) => value !== null && value !== undefined &&
    String(value).toLowerCase().includes(filter));
}

export function toCsv(columns, rows, delimiter = ";") {
  const escapeCsv = (value) => {
    if (value === null || value === undefined) return "";
    const text = typeof value === "object" ? JSON.stringify(value) : String(value);
    return new RegExp(`["${delimiter}\n]`).test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [columns.join(delimiter)]
    .concat(rows.map((row) => columns.map((column) => escapeCsv(row[column])).join(delimiter)))
    .join("\n");
}

export function download(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export function timestampForFilename() {
  return new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
}
