/**
 * What the integration is doing right now - the banner every page of the panel shows.
 *
 * The long operations of this integration are neither instant nor invisible: reading the
 * memory of an RS485 bus takes minutes, locks that bus while it runs (the devices on it do
 * not react meanwhile) and makes every other bus operation fail. Whoever started it sees a
 * progress card on their own page - but a user who switches the page, reloads the browser or
 * comes back later sees nothing, presses a button which does nothing and has no way to tell a
 * slow operation from a broken one.
 *
 * So the panel polls `eltako/activity` (core/websocket.get_activity) centrally and renders
 * this above the content of every page: what runs, how far it is, since when, and what that
 * means right now. Buttons which would collide are disabled and say why instead of failing.
 *
 * The backend sends facts, the wording lives here.
 */

import { renderBusCancel, renderBusScans } from "./bus_scan.js";
import { escapeHtml, formatDuration } from "./utils.js";

export const ACTIVITY_STYLES = `
  .activity { margin-bottom: 12px; }
  .activity:empty { display: none; }
  .activity-card {
    border: 1px solid var(--eltako-accent); border-left-width: 4px;
    border-radius: var(--eltako-radius); background: var(--eltako-tint);
    padding: 10px 14px; display: flex; flex-direction: column; gap: 6px;
  }
  .activity-head { display: flex; align-items: center; gap: 8px; font-weight: 500; }
  .activity-head .activity-spinner {
    width: 13px; height: 13px; flex: 0 0 auto; border-radius: 50%;
    border: 2px solid var(--eltako-tint-strong); border-top-color: var(--eltako-accent);
    animation: eltako-activity-spin 1s linear infinite;
  }
  @keyframes eltako-activity-spin { to { transform: rotate(360deg); } }
  .activity-head .activity-since { margin-left: auto; font-weight: 400; font-size: .78rem;
                                   color: var(--eltako-muted); font-variant-numeric: tabular-nums; }
  .activity-job { font-size: .85rem; }
  .activity-job .activity-step { color: var(--eltako-muted); }
  .activity-wait { font-size: .78rem; color: var(--eltako-muted); }
  .activity-wait b { color: var(--primary-text-color); font-weight: 500; }
  .activity-cancel { display: flex; flex-wrap: wrap; gap: 6px; }
  /* a button which cannot be pressed while something runs says so instead of looking broken */
  [data-busy-block][disabled] { cursor: wait; }
`;

/** The jobs of an activity answer, robust against a missing or half filled one. */
export function jobsOf(activity) {
  return (((activity || {}).jobs) || []).filter(Boolean);
}

/** One job in plain words: what it is (title) and what it is doing right now (step). */
export function describeJob(job) {
  if (!job) return { title: "", step: null };
  if (job.kind === "detection") {
    // the devices are added while the scan runs, so this counter grows - it is the answer to
    // "is anything happening?" which a progress bar alone cannot give
    const added = job.added
      ? `${job.added} device${job.added === 1 ? "" : "s"} added so far`
      : null;
    const step = job.step || "the search is starting";
    return { title: "Searching for gateways and devices",
             step: added ? `${step} - ${added}` : step };
  }
  const name = job.gateway_name || `Gateway ${job.gateway_id}`;
  const reason = String(job.reason || "").toLowerCase();
  if (reason.includes("scan") || reason.includes("memories")) {
    return { title: `Reading the bus of ${name}`, step: "every device and its memory" };
  }
  if (reason.includes("teach")) return { title: `Teaching in the senders on ${name}`, step: null };
  if (reason.includes("base id")) return { title: `Asking ${name} for its base id`, step: null };
  return { title: `${name} is busy`, step: job.reason || null };
}

/**
 * Why waiting is the right thing to do. This is the sentence the whole banner exists for:
 * it names the cost (minutes), the consequence (the bus is deaf, other buttons are refused)
 * and that nothing has to be pressed.
 */
export function waitHint(jobs) {
  const minutes = "This takes <b>a few minutes</b>. ";
  if (jobsOf({ jobs }).some((job) => (job.blocks || []).includes("bus"))) {
    return `${minutes}While a bus is being read the devices on it do not react, and every other `
      + "bus operation (a second scan, a teach-in, a search) is refused - the buttons for those "
      + "are disabled until it is done. Nothing is lost by waiting: the page updates itself and "
      + "shows the result.";
  }
  return `${minutes}The page updates itself and shows the result - there is nothing to press.`;
}

/** The banner, or "" when nothing runs. */
export function renderActivity(activity) {
  const jobs = jobsOf(activity);
  if (!jobs.length) return "";

  const oldest = jobs.map((job) => job.started_at).filter(Boolean).sort()[0];
  const scans = jobs.map((job) => job.progress).filter(Boolean);
  // jobs which hold a bus: only those can be cancelled, and only they leave commands waiting
  const busJobs = jobs.filter((job) => (job.blocks || []).includes("bus"));
  const nameOf = (gatewayId) => {
    const job = jobs.find((entry) => String(entry.gateway_id) === String(gatewayId));
    return (job && job.gateway_name) || `Gateway ${gatewayId}`;
  };

  return `
    <div class="activity-card" role="status" aria-live="polite">
      <div class="activity-head">
        <span class="activity-spinner"></span>
        <span>${jobs.length === 1 ? "The integration is working"
          : `${jobs.length} things are running`} &ndash; please wait</span>
        ${oldest ? `<span class="activity-since">since ${escapeHtml(formatDuration(oldest))}</span>` : ""}
      </div>
      ${jobs.map((job) => {
        const described = describeJob(job);
        return `<div class="activity-job">${escapeHtml(described.title)}${described.step
          ? ` <span class="activity-step">&ndash; ${escapeHtml(described.step)}</span>` : ""}</div>`;
      }).join("")}
      ${renderBusScans(scans, nameOf)}
      <div class="activity-wait">${waitHint(jobs)}</div>
      ${busJobs.length ? `<div class="activity-cancel">${
        // the way out of the situation this banner describes: a bus operation which does not
        // end blocks every command of the integration, and from the outside a hanging scan
        // and a slow one look the same. One button per bus, plus "all" when several are busy.
        busJobs.map((job) => renderBusCancel(job.gateway_id ?? "all",
          busJobs.length > 1 && job.gateway_name
            ? `cancel &amp; release ${escapeHtml(job.gateway_name)}` : "cancel &amp; release bus"))
          .join(" ")}</div>` : ""}
    </div>`;
}

/** The job which blocks `token` ("any", "bus", "detection", "gateway:3"), or null. */
export function blockingJob(jobs, token = "any") {
  return jobsOf({ jobs }).find((job) =>
    token === "any" || (job.blocks || []).includes(token)) || null;
}

/**
 * Disables the buttons which would collide with a running job and says why on each of them.
 *
 * A page marks such a button with `data-busy-block`: empty or "any" for "not while anything
 * runs", otherwise a token of `job.blocks`. Only what was locked here is unlocked again - a
 * button which its page disabled for its own reasons keeps its state.
 */
export function applyBusyLocks(root, jobs) {
  if (!root) return;
  root.querySelectorAll("[data-busy-block]").forEach((element) => {
    const job = blockingJob(jobs, element.getAttribute("data-busy-block") || "any");

    if (job) {
      if (!element.hasAttribute("data-busy-locked")) {
        element.setAttribute("data-busy-locked", element.getAttribute("title") || "");
      }
      element.disabled = true;
      element.title = `Not possible right now: ${describeJob(job).title.toLowerCase()}. `
        + "Please wait until it is done.";
    } else if (element.hasAttribute("data-busy-locked")) {
      const title = element.getAttribute("data-busy-locked");
      element.removeAttribute("data-busy-locked");
      element.disabled = false;
      if (title) element.title = title;
      else element.removeAttribute("title");
    }
  });
}
