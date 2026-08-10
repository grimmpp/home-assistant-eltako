/**
 * The running bus scans - one line per bus, below each other.
 *
 * Reading an RS485 bus means asking every position and then every memory row of every device
 * found there; that takes minutes, and it happens on several buses at the same time: plug &
 * play reads every bus in parallel, and on the device page each gateway has its own scan
 * button. A single averaged bar hides exactly what matters then - which bus is where, and
 * which one is the slow one. So every scan keeps its own row with its own counters.
 *
 * The rows are patchable: `applyBusScans` writes new counters into the rendered dom, so a
 * poll can keep them current without the page being rendered again.
 *
 * The data comes from observation/bus_members.py (SCAN_PROGRESS) and reaches the ui as
 * `plugAndPlay.bus_scans` (a list) and as `busMembers.scan_progress` (keyed by gateway id).
 */

import { escapeHtml } from "./utils.js";

export const BUS_SCAN_STYLES = `
  .bus-scans { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
  .bus-scan { display: flex; flex-direction: column; gap: 4px; }
  .bus-scan-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px;
                   font-size: .76rem; }
  .bus-scan-name { font-weight: 500; }
  .bus-scan-step { color: var(--eltako-muted); }
  .bus-scan-percent { margin-left: auto; font-variant-numeric: tabular-nums;
                      color: var(--eltako-accent); }
  .bus-scan-bar { height: 3px; border-radius: 999px; overflow: hidden;
                  background: var(--eltako-tint-strong); }
  .bus-scan-bar i { display: block; height: 100%; border-radius: 999px;
                    background: var(--eltako-accent); transition: width .8s ease; }
`;

/**
 * One readable line for a scan, the same wording as bus_members.describe_scan_progress:
 * the position count is the one *being read* (done + 1), so it never says "0/14" while the
 * bus is clearly working.
 */
export function describeBusScan(scan) {
  const total = scan.positions_total || 0;
  const current = total ? Math.min((scan.positions_done || 0) + 1, total) : "?";
  const line = `position ${current}/${total || "?"}`;
  return scan.memory_rows_total
    ? `${line} &middot; memory ${scan.memory_rows_read || 0}/${scan.memory_rows_total}`
    : line;
}

/**
 * The scans as a stacked list, or "" when none runs.
 *
 * @param {any[]} scans entries of SCAN_PROGRESS
 * @param {(gatewayId: any) => string} [nameOf] name of a bus - leave it out where the name
 *   already stands above the list (one section per gateway)
 */
export function renderBusScans(scans, nameOf) {
  const running = (scans || []).filter(Boolean);
  if (!running.length) return "";

  return `<div class="bus-scans">${running.map((scan) => {
    const name = nameOf ? nameOf(scan.gateway_id) : "";
    const percent = Math.max(0, Math.min(100, Math.round(scan.percent || 0)));
    return `
      <div class="bus-scan" data-scan-gateway="${escapeHtml(scan.gateway_id)}">
        <div class="bus-scan-head">
          ${name ? `<span class="bus-scan-name">${escapeHtml(name)}</span>` : ""}
          <span class="bus-scan-step">${describeBusScan(scan)}</span>
          <span class="bus-scan-percent">${percent}%</span>
        </div>
        <div class="bus-scan-bar"><i style="width:${Math.max(percent, 2)}%"></i></div>
      </div>`;
  }).join("")}</div>`;
}

/**
 * Writes the counters of the running scans into the rows which are already on the page.
 *
 * Returns false when a scan has no row (yet) or a row has no scan anymore - then the set of
 * scans changed and the caller has to render the page again instead of patching it.
 */
export function applyBusScans(root, scans) {
  if (!root) return false;
  const rows = new Map([...root.querySelectorAll(".bus-scan[data-scan-gateway]")]
    .map((row) => [String(row.getAttribute("data-scan-gateway")), row]));
  const running = (scans || []).filter(Boolean);
  if (rows.size !== running.length) return false;

  for (const scan of running) {
    const row = rows.get(String(scan.gateway_id));
    if (!row) return false;
    const percent = Math.max(0, Math.min(100, Math.round(scan.percent || 0)));
    const step = row.querySelector(".bus-scan-step");
    // the text carries an html entity as separator - the same markup as when it was rendered
    if (step) step.innerHTML = describeBusScan(scan);
    const value = row.querySelector(".bus-scan-percent");
    if (value) value.textContent = `${percent}%`;
    const bar = row.querySelector(".bus-scan-bar i");
    if (bar) bar.style.width = `${Math.max(percent, 2)}%`;
  }
  return true;
}
