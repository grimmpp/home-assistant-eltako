/**
 * One radio telegram as *every* gateway received it.
 *
 * The live view lists receptions: with three transceivers in the house the same button press
 * is three consecutive rows, and whether those three rows really say the same thing is left
 * to the reader. This page answers that question instead - it groups the receptions of one
 * transmission (see observation/radio_comparison.py) and shows who heard it, who did not,
 * where the bytes differ, what each gateway made of it and how strong the signal was.
 *
 * Everything is computed by the backend on demand, so the **time window**, the **view**, the
 * **gateways** and the **sender** are controls, not settings: the same recording can be looked
 * at with 50 ms or with a second, restricted to two gateways and one device.
 */

import { WS } from "../lib/api.js";
import {
  card, download, escapeHtml, formatDateTime, formatNumber, formatTime, matchesFilter,
  timestampForFilename, toCsv,
} from "../lib/utils.js";

export const RADIO_STYLES = `
  /* reception rate and signal strength as a bar - a column of numbers does not show which
     gateway is the weak one at a glance */
  .meter { display: block; height: 4px; border-radius: 2px; margin-top: 3px;
           background: var(--eltako-tint-strong); overflow: hidden; }
  .meter > span { display: block; height: 100%; background: var(--label-badge-green, #43a047); }
  .meter.weak > span { background: var(--eltako-warn); }
  .meter.bad > span { background: var(--label-badge-red, #e53935); }
  /* the byte which is not what the other gateways reported */
  .byte-diff { background: var(--eltako-warn); color: #212121; border-radius: 3px;
               padding: 0 2px; font-weight: 600; }
  .burst-detail > td { background: var(--eltako-tint); }
  .burst-detail table { width: 100%; font-size: .78rem; }
  .burst-detail table th { color: var(--eltako-muted); font-weight: 400; }
  .burst-detail .values { font-size: .78rem; margin-top: 6px; }
  .burst-detail .values b { font-weight: 500; }
  tr.burst-detail { display: none; }
  tr.burst-detail.visible { display: table-row; }
  .gateway-name { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
  /* the controls of the analysis: which telegrams, which gateways */
  .controls { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
  .control-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }
  .control-row > label { font-size: .78rem; color: var(--eltako-muted); min-width: 130px; }

  /* Problems are coloured, not only worded: with a table this wide the eye has to be able to
     jump to the row which is wrong. Two levels only - red is a fault (the gateways did not
     receive or read the same thing, a gateway hears nothing at all), yellow is something to
     look at (a telegram somebody missed, a device which only arrives over a repeater, a weak
     signal). Everything which is normal stays uncoloured. */
  tr.issue > td { background: color-mix(in srgb, var(--label-badge-red, #e53935) 13%, transparent); }
  tr.attention > td { background: color-mix(in srgb, var(--eltako-warn) 16%, transparent); }
  td.issue, .cell-issue { background: color-mix(in srgb, var(--label-badge-red, #e53935) 20%, transparent); }
  td.attention, .cell-attention { background: color-mix(in srgb, var(--eltako-warn) 22%, transparent); }
  /* inside a coloured row the marked cell still has to stand out */
  tr.issue > td.issue { background: color-mix(in srgb, var(--label-badge-red, #e53935) 30%, transparent); }
  tr.attention > td.attention { background: color-mix(in srgb, var(--eltako-warn) 34%, transparent); }
  .legend { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-size: .72rem;
            color: var(--eltako-muted); margin: 6px 0 2px; }
  span.swatch { display: inline-block; padding: 1px 8px; border-radius: 9px;
                color: var(--primary-text-color); }
  .swatch.issue { background: color-mix(in srgb, var(--label-badge-red, #e53935) 25%, transparent); }
  .swatch.attention { background: color-mix(in srgb, var(--eltako-warn) 30%, transparent); }
  .swatch.normal { background: var(--eltako-tint-strong); }
  .legend span.swatch { font-size: .72rem; }

  /* "Where the differences are": three groups with different causes, and for each difference
     the devices and the gateway it happened at - a count alone does not say where to look */
  .diff-table tr.group > td { background: var(--eltako-tint); padding-top: 12px; }
  .diff-table tr.group .swatch { font-size: .78rem; font-weight: 500; }
  .diff-table .diff-note { color: var(--eltako-muted); font-size: .78rem; margin: 0 8px; }
  .diff-table .field-name { font-weight: 600; }
  .diff-table .field-name + .hint { display: block; max-width: 34ch; }
  .diff-table td .meter.share { max-width: 90px; margin-left: auto; }
  .diff-table .where { display: flex; flex-wrap: wrap; gap: 4px; align-items: baseline; }
  .diff-table .where button b { font-weight: 600; opacity: .75; }
  /* how many gateways heard the same transmission - a bar says "most of them" at a glance */
  .count-bars { display: grid; grid-template-columns: auto minmax(60px, 160px) auto;
                gap: 4px 10px; align-items: center; font-size: .8rem; margin: 8px 0 2px;
                width: max-content; max-width: 100%; }
  .count-bars .meter { margin: 0; }
  .count-bars .num { text-align: right; }
  .path { font-size: .68rem; padding: 1px 6px; border-radius: 9px; white-space: nowrap;
          background: var(--eltako-tint-strong); color: var(--eltako-muted); }
  .path.direct { background: color-mix(in srgb, var(--label-badge-green, #43a047) 22%, transparent);
                 color: var(--primary-text-color); }
  .path.hop { background: color-mix(in srgb, var(--eltako-warn) 35%, transparent); color: #212121; }
`;

/** What is compared between the gateways, and what a difference in it means. */
const FIELDS = {
  msg_type: ["message type", "The gateways read the same transmission as different telegram types."],
  org: ["ORG", "The telegram kind (RPS, 1BS, 4BS, ...) was reported differently."],
  data: ["data bytes", "The payload itself differs - the values of the device are not the same."],
  status: ["status byte", "The status bits differ (without the repeater counter)."],
  rp_count: ["repeater hops", "Normal: one gateway heard the device directly, another one through a repeater."],
  eep: ["profile", "The gateways read the telegram with different profiles - check which device this address belongs to."],
  decoded: ["values", "Same telegram, different meaning: what the gateways made of it is not the same."],
};

/** The views of the telegram list. The order is the order of the buttons. */
const VIEWS = [
  ["all", "all"],
  ["identical", "identical"],
  ["disagreeing", "received differently"],
  ["interpreted", "read differently"],
  ["hops", "repeater hop only"],
  ["missing", "somebody missed it"],
  ["single", "only one gateway"],
  ["repeated", "repeated"],
];

// window choices in milliseconds. Static on purpose - they are the same everywhere and the
// toolbar is built before the first report arrives (the backend sends them as well).
const WINDOW_CHOICES = [50, 100, 200, 300, 500, 1000, 2000];
const DEFAULT_WINDOW_MS = 200;

// how the signal strength is mapped onto the bar: -40 dBm is as good as it gets, below
// -95 dBm a telegram is barely there
const RSSI_BEST = -40;
const RSSI_WORST = -95;
// below this a link has hardly any reserve left: one closed door more and it is gone
const RSSI_WEAK = -85;

/**
 * How long after the last telegram the analysis is asked for.
 *
 * A transmission is only *complete* once its window has passed - the second gateway may still
 * be about to report it. Asking earlier would show the first reception with "the others missed
 * it" and correct itself a moment later, which is worse than waiting: the window plus a small
 * margin is exactly the point at which the answer is stable.
 */
const QUIET_MARGIN_MS = 150;
// upper bound for a busy bus: the receptions keep coming, the analysis still runs at most this
// often. The telegrams which arrive meanwhile are not lost - they are in the next answer.
const MIN_RELOAD_INTERVAL_MS = 2000;

// TODO type check: add /** @type {import("../types.js").Page} */ once the dom casts are in
export const page = {
  id: "radio",
  title: "Radio reception",
  subtitle: "The same radio telegram as every gateway received it: who hears what, "
    + "where they differ and how strong the signal is",
  icon: "mdi:access-point",
  glyph: "◎",
  needsRecording: true,
  // no refreshMs on purpose: the page follows the live telegram stream (see onTelegram). While
  // nothing is sent there is nothing to recompute, and a poll would ask the same question over
  // and over - the whole analysis runs per request, so that is not free.
  styles: RADIO_STYLES,

  async load(ctx) {
    // the gateways are only needed for their names and to show a gateway which receives
    // nothing - they do not change every four seconds, so they are fetched once
    await Promise.all([
      ctx.loadLogInfo(),
      ctx.state.integrationInfo ? Promise.resolve(null) : ctx.loadIntegrationInfo(),
      this._loadReport(ctx),
    ]);
  },

  async _loadReport(ctx) {
    // Every request carries the controls as they are *now*, and the page reloads itself every
    // few seconds. So a periodic refresh which was sent before a button was pressed answers
    // with the previous view - and if that answer is stored, the table jumps back a moment
    // after the user chose something, which looks exactly like a filter that does nothing.
    // Only the newest request may store its result.
    const token = (this._request || 0) + 1;
    this._request = token;

    const report = await ctx.api.call(WS.RADIO_COMPARISON, {
      limit: 60,
      window_ms: ctx.state.radioWindowMs || DEFAULT_WINDOW_MS,
      filter: ctx.state.radioView || "all",
      gateway_ids: (ctx.state.radioGateways || []).map((id) => String(id)),
      address: ctx.state.radioSender || null,
    });
    if (report && token === this._request) ctx.state.radioComparison = report;
    return ctx.state.radioComparison;
  },

  /** A control was used: fetch the analysis for it right away. */
  async _reload(ctx) {
    this._cancelScheduledReload();
    this._lastLoadAt = Date.now();
    await this._loadReport(ctx);
    ctx.requestContentRender(true);
  },

  /**
   * A telegram arrived. This is what the page runs on instead of a timer: the shell pushes
   * every recorded telegram of the live stream in here (see eltako-panel._onTelegram).
   *
   * One telegram is *not* one analysis: a transmission which three gateways receive arrives as
   * three events within milliseconds, and asking three times would compute the same answer
   * three times - the last two of them on data which is still incomplete. So the events are
   * collected and the analysis is asked for once, when the window of that transmission has
   * passed (`_reloadDelay`).
   */
  onTelegram(ctx, telegram) {
    if (!this._affects(ctx, telegram)) return;
    this._scheduleReload(ctx);
  },

  /** Whether this telegram can change what the page currently shows. */
  _affects(ctx, telegram) {
    if (!telegram || !telegram.address || String(telegram.address).startsWith("bus ")) return false;
    // bus house keeping (polling, discovery, memory) never leaves the wire of one bus, so no
    // second gateway can receive it - it is not part of the comparison
    if (telegram.role === "bus_message" || telegram.bus_address !== null
        && telegram.bus_address !== undefined) return false;
    // the same for what a gateway read off its wire: an actuator on an RS485 bus is addressed
    // relative to the base id of its gateway, and such a reception came over the bus instead of
    // out of the air (observation/radio_comparison.is_radio_telegram). Only what a gateway
    // *sent* stays - a FAM14 puts its bus traffic on air, so it is the sender of a burst.
    if (telegram.local_address && telegram.direction !== "outgoing") return false;
    // while the analysis is restricted, a telegram outside of it changes nothing on screen
    const sender = ctx.state.radioSender;
    if (sender && String(telegram.address).toUpperCase() !== String(sender).toUpperCase()) {
      return false;
    }
    const gateways = (ctx.state.radioGateways || []).map(String);
    return !gateways.length || gateways.includes(String(telegram.gateway_id));
  },

  /** Wait for the window of the running transmission, and not more often than the bound. */
  _reloadDelay(ctx) {
    const window = Number(ctx.state.radioWindowMs || DEFAULT_WINDOW_MS);
    const since = Date.now() - (this._lastLoadAt || 0);
    return Math.max(window + QUIET_MARGIN_MS, MIN_RELOAD_INTERVAL_MS - since);
  },

  _scheduleReload(ctx) {
    if (this._reloadTimer) return;      // a burst of telegrams shares one analysis
    this._reloadTimer = setTimeout(async () => {
      this._reloadTimer = null;
      this._lastLoadAt = Date.now();
      await this._loadReport(ctx);
      ctx.requestContentRender();
    }, this._reloadDelay(ctx));
  },

  _cancelScheduledReload() {
    if (this._reloadTimer) clearTimeout(this._reloadTimer);
    this._reloadTimer = null;
  },

  /** The page is closed: its timer must not outlive its dom. */
  leave() {
    this._cancelScheduledReload();
  },

  renderStatus(ctx) {
    const summary = this._summary(ctx);
    // the page follows the telegram stream instead of a timer - and says so, otherwise a quiet
    // bus looks like a page which stopped working
    const live = ctx.state.paused
      ? `<span class="pill warn" title="The live view is paused, so no telegrams reach this page either. Use 'Analyse now' or resume it.">paused</span>`
      : `<span class="pill on" title="Updates itself whenever a telegram arrives - no polling">live</span>`;
    if (!summary.burst_count) return `${live}<span class="pill">waiting for telegrams</span>`;
    return `
      ${live}
      <span class="pill">${formatNumber(summary.burst_count)} telegrams compared</span>
      <span class="pill">${formatNumber(summary.multi_gateway_bursts)} seen by more than one</span>
      <span class="pill ${summary.disagreeing_bursts ? "warn" : "on"}">
        ${formatNumber(summary.disagreeing_bursts)} received differently</span>
      ${summary.interpreted_bursts
        ? `<span class="pill warn">${formatNumber(summary.interpreted_bursts)} read differently</span>`
        : ""}
      <span class="pill" title="Receptions of one address within this window count as the same transmission">
        ${formatNumber(summary.window_ms)} ms window</span>`;
  },

  renderToolbar(ctx) {
    const window = ctx.state.radioWindowMs || DEFAULT_WINDOW_MS;
    return `
      <input id="radio-filter" type="search" placeholder="Filter address, device, gateway, data&hellip;"
             value="${escapeHtml(ctx.state.radioFilter || "")}" />
      <label class="check" title="How far apart two receptions may be to count as the same transmission. A transmission consists of three sub telegrams within ~40 ms, a repeater sends the whole thing again.">
        window
        <select id="radio-window">
          ${WINDOW_CHOICES.map((choice) => `
            <option value="${choice}" ${choice === Number(window) ? "selected" : ""}>${choice} ms</option>`).join("")}
        </select>
      </label>
      <label class="check" title="Restrict the whole analysis to the telegrams of one sender">
        sender
        <select id="radio-sender"><option value="">all senders</option></select>
      </label>
      <span class="spacer"></span>
      <button id="radio-reload" class="action"
              title="Run the analysis again. It normally runs by itself whenever a telegram arrives - this is for a bus which is quiet, or while the live view is paused.">
        Analyse now</button>
      <button id="radio-export" class="action">Export CSV</button>
      <button id="radio-reset" class="action danger"
              title="Throw the recorded receptions away and start over. The live telegrams and their statistics are not touched.">
        Reset comparison</button>`;
  },

  bindToolbar(ctx, root) {
    root.getElementById("radio-filter").addEventListener("input", (event) => {
      ctx.state.radioFilter = event.target.value;
      ctx.requestContentRender(true);
    });
    // the window and the sender change what the *backend* computes, so both reload
    root.getElementById("radio-window").addEventListener("change", (event) => {
      ctx.state.radioWindowMs = Number(event.target.value) || DEFAULT_WINDOW_MS;
      this._reload(ctx);
    });
    root.getElementById("radio-sender").addEventListener("change", (event) => {
      ctx.state.radioSender = event.target.value || null;
      this._reload(ctx);
    });
    root.getElementById("radio-reload").addEventListener("click", () => this._reload(ctx));
    root.getElementById("radio-export").addEventListener("click", () => {
      const { columns, rows } = this._csv(ctx);
      download(`eltako_radio_reception_${timestampForFilename()}.csv`,
        toCsv(columns, rows), "text/csv");
    });
    root.getElementById("radio-reset").addEventListener("click", async () => {
      await ctx.api.call(WS.RADIO_COMPARISON_CLEAR);
      ctx.state.radioComparison = null;
      ctx.state.radioOpen = {};
      await this._loadReport(ctx);
      ctx.requestRender();
    });
  },

  render(ctx) {
    if (ctx.state.logInfo && ctx.state.logInfo.enabled === false) return ctx.renderRecordingDisabled();
    const summary = this._summary(ctx);
    if (summary.enabled === false) return ctx.renderRecordingDisabled();

    const gateways = this._gatewayRows(ctx);
    return `
      ${this._cards(summary)}
      ${this._controls(ctx, summary, gateways)}
      ${this._legend(summary)}
      ${this._notes(ctx, summary, gateways)}
      ${this._gatewayTable(gateways, summary)}
      ${this._pairTable(ctx, gateways)}
      ${this._fieldStatistics(summary)}
      ${this._addressTable(ctx, gateways)}
      ${this._burstTable(ctx, gateways, summary, ctx.state.radioComparison || {})}
      ${this._footnote(summary)}`;
  },

  /* ------------------------------------------------------------------ summary */

  _summary(ctx) {
    return ((ctx.state.radioComparison || {}).summary) || {};
  },

  _cards(summary) {
    if (!summary.burst_count) return "";
    return `
      <div class="cards">
        ${card("Telegrams compared", formatNumber(summary.burst_count), "",
               `${formatNumber(summary.telegram_count)} receptions in the buffer`)}
        ${card("Seen by several gateways", formatNumber(summary.multi_gateway_bursts), "",
               `${formatNumber(summary.single_gateway_bursts)} by one only`)}
        ${card("Received differently", formatNumber(summary.disagreeing_bursts),
               summary.disagreeing_bursts ? "warn" : "good",
               "message type, data or status")}
        ${card("Read differently", formatNumber(summary.interpreted_bursts),
               summary.interpreted_bursts ? "warn" : "good",
               "another profile or other values")}
        ${card("Only a repeater hop apart",
               formatNumber((summary.filter_counts || {}).hops), "",
               "normal in a network with repeaters")}
        ${card("Somebody missed it", formatNumber((summary.filter_counts || {}).missing),
               (summary.filter_counts || {}).missing ? "warn" : "", "at least one gateway")}
      </div>`;
  },

  /**
   * What the *whole* analysis is restricted to: which gateways, which sender.
   *
   * Deliberately separated from the view of the telegram list (which sits above that list, see
   * `_views`): these two do different things. Restricting the gateways changes every number on
   * the page - what "missing" means, the rates, the pairs; a view only decides which telegrams
   * the last table lists. Mixing both into one control block made the buttons look like they
   * did nothing, because the table they act on was at the bottom of the page.
   */
  _controls(ctx, summary, gateways) {
    const selected = (ctx.state.radioGateways || []).map(String);
    const restricted = selected.length || ctx.state.radioSender;
    return `
      <div class="controls">
        <div class="control-row">
          <label title="Compare only these gateways with each other - everything else is left out of the analysis">Compare gateways</label>
          <button class="action small ${selected.length ? "" : "primary"}" data-gateway="">all</button>
          ${gateways.map((gateway) => `
            <button class="action small ${selected.includes(String(gateway.gateway_id)) ? "primary" : ""}"
                    data-gateway="${escapeHtml(gateway.gateway_id)}">
              ${escapeHtml(gateway.gateway_name || gateway.gateway_id)}</button>`).join("")}
          ${ctx.state.radioSender
            ? `<button class="action small primary" data-sender=""
                       title="Analyse the telegrams of every sender again">
                 sender ${escapeHtml(ctx.state.radioSender)} &times;</button>` : ""}
          ${restricted
            ? `<span class="hint">Every table below is computed for this selection only.</span>`
            : ""}
        </div>
      </div>`;
  },

  /** The colours of the tables - see RADIO_STYLES. */
  _legend(summary) {
    if (!summary.burst_count) return "";
    return `
      <div class="legend">
        <span class="swatch issue">problem</span>
        <span>not received or not read the same way, or a gateway which hears nothing</span>
        <span class="swatch attention">worth a look</span>
        <span>somebody missed it, only over a repeater, weak signal</span>
        <span class="swatch normal">normal</span>
      </div>`;
  },

  /**
   * The views of the telegram list, rendered right above that list.
   *
   * They carry live counts, which is why they are part of the content and not of the toolbar
   * (the toolbar is built once and would go stale).
   */
  _views(ctx, summary) {
    const counts = summary.filter_counts || {};
    const view = ctx.state.radioView || "all";
    return `
      <div class="control-row">
        <label>Show</label>
        ${VIEWS.map(([name, label]) => `
          <button class="action small ${name === view ? "primary" : ""}" data-view="${name}"
                  title="${escapeHtml((summary.filters || {})[name] || "")}">
            ${escapeHtml(label)}${counts[name] === undefined
              ? "" : ` <b>${formatNumber(counts[name])}</b>`}</button>`).join("")}
        <span class="hint">Filters this table only - the numbers above always describe
          everything which was recorded.</span>
      </div>`;
  },

  /** What this page cannot answer yet, and why - so an empty table is never a mystery. */
  _notes(ctx, summary, gateways) {
    const notes = [];
    if (!summary.burst_count) {
      notes.push(`<div class="empty">Waiting for radio telegrams&hellip; As soon as a device
        sends something, this page shows which of your gateways received it.${
          ctx.state.radioSender || (ctx.state.radioGateways || []).length
            ? " Nothing matches the current restriction - try \"all\" gateways and all senders."
            : ""}</div>`);
    }
    const receiving = gateways.filter((gateway) => gateway.received > 0);
    if (summary.burst_count && receiving.length < 2) {
      notes.push(`<div class="notice warn">
        <h3>Only one gateway is receiving radio telegrams</h3>
        <p>${receiving.length
          ? `Everything recorded so far was received by
             <b>${escapeHtml(receiving[0].gateway_name || receiving[0].gateway_id)}</b> alone.`
          : "No gateway has received a radio telegram yet."}
          A comparison needs at least two, so this page stays a plain list until a second
          gateway hears the same telegram. Only radio telegrams are counted: bus traffic
          (polling, discovery, memory) and the telegrams of the actuators on an RS485 bus
          reach their gateway over the wire and are excluded on purpose.</p></div>`);
    }
    if (summary.burst_count && !gateways.some((gateway) => gateway.rssi_count > 0)) {
      notes.push(`<div class="notice">
        <p>None of the gateways reports a signal strength. That is expected for the ESP2
          gateways of the RS485 bus (FAM14, FGW14-USB) - only ESP3 transceivers deliver an
          RSSI value per telegram.</p></div>`);
    }
    return notes.join("");
  },

  /* ----------------------------------------------------------------- gateways */

  /**
   * One row per gateway: what the comparison saw, merged with the configured gateways.
   *
   * A gateway which received nothing at all is missing from the report - and that is exactly
   * the case worth seeing (wrong antenna, dead stick, out of range), so the configured
   * gateways are the base of the list and the numbers are merged into them.
   */
  _gatewayRows(ctx) {
    const rows = new Map();
    for (const gateway of ((ctx.state.integrationInfo || {}).gateways || [])) {
      rows.set(String(gateway.id), {
        gateway_id: gateway.id, gateway_name: gateway.name, simulated: !!gateway.simulated,
        configured: true, received: 0, offered: 0, missed: 0, first: 0, alone: 0, outlier: 0,
        differing: 0, repeats: 0, hops: 0, sent: 0, share: null, by_level: {},
        rssi_min: null, rssi_max: null, rssi_avg: null, rssi_count: 0,
      });
    }
    for (const gateway of ((ctx.state.radioComparison || {}).gateways || [])) {
      const key = String(gateway.gateway_id);
      const known = rows.get(key) || { configured: false, simulated: false };
      // the configured name wins: the report carries the name the gateway had when it was
      // seen for the first time, which is the old one after a rename
      rows.set(key, { ...known, ...gateway,
                      gateway_name: known.gateway_name || gateway.gateway_name || key });
    }
    return [...rows.values()].sort((left, right) => Number(left.gateway_id) - Number(right.gateway_id));
  },

  _gatewayTable(gateways, summary) {
    if (!gateways.length) return "";
    // a configured gateway which received nothing while others did is the clearest fault this
    // page can find - wrong antenna, dead stick, out of range
    const deaf = (gateway) => !gateway.received && !gateway.sent
      && gateways.some((other) => other.received > 0);
    const rows = gateways.map((gateway) => `
      <tr class="${deaf(gateway) ? "issue" : ""}">
        <td><div class="gateway-name">
          <span>${escapeHtml(gateway.gateway_name || gateway.gateway_id)}</span>
          ${gateway.simulated ? `<span class="tag simulated">simulated</span>` : ""}
          ${gateway.configured ? "" : `<span class="tag role">not configured</span>`}
          ${deaf(gateway) ? `<span class="tag unknown">receives nothing</span>` : ""}
        </div><span class="hint">id ${escapeHtml(gateway.gateway_id)}</span></td>
        <td class="num">${formatNumber(gateway.received)}
          <span class="hint">of ${formatNumber(gateway.offered)}</span></td>
        <td class="num ${gateway.share !== null && gateway.share !== undefined
                         && gateway.share < 0.9 ? "attention" : ""}">${this._share(gateway.share)}
          ${this._meter(gateway.share === null || gateway.share === undefined
                        ? null : gateway.share * 100, 90, 60)}</td>
        <td class="num ${gateway.missed ? "attention" : ""}">${formatNumber(gateway.missed)}</td>
        <td class="num">${formatNumber(gateway.first)}</td>
        <td class="num">${formatNumber(gateway.alone)}</td>
        <td class="${gateway.received && !(gateway.by_level || {})["0"] ? "attention" : ""}">
          ${this._levels(gateway.by_level)}
          ${gateway.repeats ? `<span class="hint">${formatNumber(gateway.repeats)} repeated</span>` : ""}</td>
        <td class="num ${gateway.outlier ? "issue" : gateway.differing ? "attention" : ""}">
          ${formatNumber(gateway.outlier)}
          ${gateway.differing
            ? `<span class="hint">${formatNumber(gateway.differing)} differing</span>` : ""}</td>
        <td class="num ${gateway.rssi_avg !== null && gateway.rssi_avg !== undefined
                         && gateway.rssi_avg < RSSI_WEAK ? "attention" : ""}">${this._rssi(gateway.rssi_avg)}
          ${this._meter(this._rssiPercent(gateway.rssi_avg), 55, 30)}
          ${gateway.rssi_count
            ? `<span class="hint">${this._rssi(gateway.rssi_max)} &hellip; ${this._rssi(gateway.rssi_min)}</span>`
            : `<span class="hint">no RSSI</span>`}</td>
      </tr>`).join("");

    return `
      <h3 class="bus-heading">Per gateway</h3>
      <div class="table-wrapper">
        <table>
          <thead><tr>
            <th>Gateway</th>
            <th class="num" title="Transmissions this gateway received">Received</th>
            <th class="num" title="Received out of everything which happened since this gateway showed up">Rate</th>
            <th class="num" title="Another gateway received the telegram, this one did not">Missed</th>
            <th class="num" title="It was the first of several gateways to report the telegram">First</th>
            <th class="num" title="Only this gateway received the telegram">Alone</th>
            <th title="How the telegrams arrived: directly out of the air, or through one or two repeaters">Path</th>
            <th class="num" title="How often the majority of the gateways reported something else than this one - and below it, how many telegrams it took part in which the gateways did not agree about at all (with only two gateways there is no majority, so nobody can be called the wrong one)">Disagreed</th>
            <th class="num">Signal (avg)</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      ${summary.burst_count ? `<div class="footnote">"Missed" only counts telegrams which
        happened after the gateway had shown up for the first time, and a telegram the gateway
        sent itself is never counted as missed.</div>` : ""}`;
  },

  /* ------------------------------------------------------- two gateways head to head */

  /**
   * Every pair of gateways against each other.
   *
   * The table above says how much a gateway hears in total, which does not answer "which of
   * these two is the better one" - one of them may be counting telegrams the other one is not
   * even in range of. A pair only counts the transmissions which happened while both existed.
   */
  _pairTable(ctx, gateways) {
    const pairs = (ctx.state.radioComparison || {}).pairs || [];
    if (!pairs.length) return "";
    const nameOf = (id) => {
      const gateway = gateways.find((entry) => String(entry.gateway_id) === String(id));
      return (gateway && gateway.gateway_name) || id;
    };

    const rows = pairs.map((pair) => `
      <tr class="${pair.disagreed || pair.interpreted ? "issue" : ""}">
        <td>${escapeHtml(nameOf(pair.gateway_a))}
          <span class="hint">vs. ${escapeHtml(nameOf(pair.gateway_b))}</span></td>
        <td class="num">${formatNumber(pair.together)}
          <span class="hint">of ${formatNumber(pair.offered)}</span></td>
        <td class="num ${pair.only_a ? "attention" : ""}">${formatNumber(pair.only_a)}</td>
        <td class="num ${pair.only_b ? "attention" : ""}">${formatNumber(pair.only_b)}</td>
        <td class="num">${formatNumber(pair.neither)}</td>
        <td class="num ${pair.disagreed ? "issue" : ""}">${formatNumber(pair.disagreed)}
          ${pair.together
            ? `<span class="hint">${formatNumber(pair.agreed)} identical</span>` : ""}</td>
        <td class="num ${pair.interpreted ? "issue" : ""}">${formatNumber(pair.interpreted)}</td>
        <td class="num ${pair.hops ? "attention" : ""}">${formatNumber(pair.hops)}</td>
        <td class="num">${pair.rssi_delta_avg === null || pair.rssi_delta_avg === undefined
          ? "-"
          : `${pair.rssi_delta_avg > 0 ? "+" : ""}${formatNumber(pair.rssi_delta_avg)} dB
             <span class="hint">${escapeHtml(nameOf(pair.rssi_delta_avg >= 0
               ? pair.gateway_a : pair.gateway_b))} is stronger</span>`}</td>
      </tr>`).join("");

    return `
      <h3 class="bus-heading">Gateway against gateway</h3>
      <div class="table-wrapper">
        <table>
          <thead><tr>
            <th>Pair</th>
            <th class="num" title="Transmissions both of them received">Both</th>
            <th class="num" title="Only the first one received it">Only A</th>
            <th class="num" title="Only the second one received it">Only B</th>
            <th class="num" title="A third gateway received it, neither of these two did">Neither</th>
            <th class="num" title="Of the telegrams both received: how often the bytes were not the same">Received differently</th>
            <th class="num" title="Same telegram, different profile or different values">Read differently</th>
            <th class="num" title="One of them heard the device directly, the other one through a repeater">Different path</th>
            <th class="num" title="How much stronger the first one hears the same telegram, on average">Signal &Delta;</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  },

  /* --------------------------------------------------------- where they differ */

  /**
   * What differed, how often - and *where*: on which device, at which gateway.
   *
   * A bare list of field names and counts ("data bytes: 12") is the beginning of the question,
   * not the answer - "on which device, and is one gateway always the odd one out?" is what
   * somebody actually wants to know. So the rows are sorted into the three groups which have
   * different causes (the bytes out of the air, the reading of them, the path they took), and
   * every difference names the devices it happens on (as a button which narrows the whole page
   * down to that sender) and the gateway which reported something else than the others.
   */
  _fieldStatistics(summary) {
    const byField = summary.by_field || {};
    const detail = summary.by_field_detail || {};
    const present = Object.entries(byField).filter(([, count]) => count > 0);
    const byCount = Object.entries(summary.by_gateway_count || {});
    if (!present.length && !byCount.length) return "";

    const hopField = summary.hop_field || "rp_count";
    const interpretation = summary.interpretation_fields || ["eep", "decoded"];
    const groups = [
      {
        title: "Received differently", tone: "issue", view: "disagreeing",
        note: "The bytes which came out of the air are not the same at every gateway.",
        fields: present.filter(([field]) => field !== hopField
                                            && !interpretation.includes(field)),
      },
      {
        title: "Read differently", tone: "issue", view: "interpreted",
        note: "The same bytes, a different meaning - that points at the device behind the "
          + "address, not at the reception.",
        fields: present.filter(([field]) => interpretation.includes(field)),
      },
      {
        title: "Different path", tone: "normal", view: "hops",
        note: "Normal in a network with repeaters, and not a fault of any gateway.",
        fields: present.filter(([field]) => field === hopField),
      },
    ].filter((group) => group.fields.length);

    const total = summary.burst_count || 0;
    const rows = groups.map((group) => `
      <tr class="group">
        <td colspan="4">
          <span class="swatch ${group.tone}">${escapeHtml(group.title)}</span>
          <span class="diff-note">${escapeHtml(group.note)}</span>
          <button class="action small" data-view="${group.view}"
                  title="Show only these telegrams in the list below">show these</button>
        </td>
      </tr>
      ${group.fields
        .sort((left, right) => right[1] - left[1])
        .map(([field, count]) => this._fieldRow(field, count, detail[field] || {}, total,
                                                group.tone)).join("")}`).join("");

    return `
      <h3 class="bus-heading">Where the differences are</h3>
      ${groups.length ? `
        <div class="table-wrapper">
          <table class="diff-table">
            <thead><tr>
              <th>What differs</th>
              <th class="num" title="How many of the compared transmissions this happened in">Telegrams</th>
              <th>On which device</th>
              <th title="The gateway which reported something else than the majority of the others. With only two gateways there is no majority, so no single gateway differs">Which gateway differs</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`
      : `<div class="empty">Every telegram was received identically by all gateways so far.</div>`}
      ${this._gatewayCountBars(byCount, total)}`;
  },

  /** One kind of difference: how often, on which device, at which gateway. */
  _fieldRow(field, count, detail, total, tone) {
    const [label, meaning] = FIELDS[field] || [field, ""];
    const share = total ? (count / total) * 100 : null;
    const named = detail.addresses || [];
    const rest = Math.max(0, (detail.address_count || named.length) - named.length);
    const gateways = detail.gateways || [];
    return `
      <tr>
        <td>
          <span class="field-name">${escapeHtml(label)}</span>
          <span class="hint">${escapeHtml(meaning)}</span>
        </td>
        <td class="num${tone === "normal" ? "" : ` ${tone}`}">${formatNumber(count)}
          <span class="hint">${share === null
            ? "" : `${Math.round(share * 10) / 10} % of ${formatNumber(total)}`}</span>
          ${share === null ? "" : `<span class="meter share"><span style="width: ${
            Math.max(2, Math.min(100, share))}%"></span></span>`}</td>
        <td>${named.length ? `<span class="where">${named.map((address) => `
            <button class="action small" data-sender="${escapeHtml(address.address)}"
                    title="${escapeHtml(address.address)} - analyse only the telegrams of this sender">
              ${escapeHtml(address.name || address.address)}
              <b>&times;${formatNumber(address.count)}</b></button>`).join("")}
            ${rest ? `<span class="hint">and ${formatNumber(rest)} more</span>` : ""}</span>`
          : `<span class="hint">-</span>`}</td>
        <td>${gateways.length ? `<span class="where">${gateways.map((gateway) => `
            <span class="kv" title="This gateway reported something else than the majority of the others">
              <i>${escapeHtml(gateway.gateway_name || gateway.gateway_id)}</i>&times;${
                formatNumber(gateway.count)}</span>`).join("")}</span>` : ""}
          ${detail.tied
            ? `<span class="hint">${formatNumber(detail.tied)}&times; evenly split - two values,
                 no majority, so no single gateway differs from the rest</span>`
            : ""}
          ${gateways.length || detail.tied ? "" : `<span class="hint">-</span>`}</td>
      </tr>`;
  },

  /** How many gateways heard the same transmission - as bars, not as a row of numbers. */
  _gatewayCountBars(byCount, total) {
    if (!byCount.length) return "";
    return `
      <div class="hint">How many gateways heard the same transmission</div>
      <div class="count-bars">
        ${byCount.map(([count, value]) => `
          <span>${escapeHtml(count)} gateway${count === "1" ? "" : "s"}</span>
          <span class="meter ${count === "1" ? "weak" : ""}"><span style="width: ${
            total ? Math.max(1, Math.round((value / total) * 100)) : 0}%"></span></span>
          <span class="num">${formatNumber(value)}</span>`).join("")}
      </div>`;
  },

  /* ------------------------------------------------------- who receives what */

  _addressTable(ctx, gateways) {
    const addresses = ((ctx.state.radioComparison || {}).addresses || [])
      .filter((address) => this._matchesAddress(ctx, address, gateways));
    if (!addresses.length) return "";

    // one column per gateway, so a row reads "this device is heard by 1 and 2, never by 3"
    const columns = gateways.filter((gateway) => gateway.received > 0 || gateway.configured);
    const rows = addresses.map((address) => `
      <tr class="${address.disagreeing ? "issue" : ""}">
        <td class="mono">${escapeHtml(address.address)}
          <button class="action small" data-sender="${escapeHtml(address.address)}"
                  title="Analyse only the telegrams of this sender">only this</button></td>
        <td>${escapeHtml(address.name || "")}
          ${address.known ? "" : `<span class="tag unknown">unknown</span>`}
          ${address.eep ? `<span class="hint">${escapeHtml(address.eep)}</span>` : ""}</td>
        <td class="num">${formatNumber(address.bursts)}</td>
        <td class="num ${address.disagreeing ? "issue" : ""}">${formatNumber(address.disagreeing)}
          ${address.differing > address.disagreeing
            ? `<span class="hint">+${formatNumber(address.differing - address.disagreeing)} hops</span>` : ""}</td>
        ${columns.map((column) => {
          const entry = (address.gateways || {})[String(column.gateway_id)];
          if (!entry || !entry.count) {
            return `<td class="num issue" title="This gateway never received this address">&ndash;</td>`;
          }
          // yellow when it loses telegrams of this device, when it only hears it through a
          // repeater, or when the signal has no reserve left
          const shaky = (entry.share !== null && entry.share !== undefined && entry.share < 0.99)
            || !entry.direct
            || (entry.rssi_avg !== null && entry.rssi_avg !== undefined && entry.rssi_avg < RSSI_WEAK);
          return `<td class="num ${shaky ? "attention" : ""}">
            ${formatNumber(entry.count)}
            <span class="hint">${this._share(entry.share)}${entry.rssi_avg === null || entry.rssi_avg === undefined
              ? "" : ` &middot; ${this._rssi(entry.rssi_avg)}`}</span>
            ${this._levels(entry.by_level)}
            ${this._meter(this._rssiPercent(entry.rssi_avg), 55, 30)}</td>`;
        }).join("")}
        <td class="mono">${formatTime(address.last_seen)}</td>
      </tr>`).join("");

    return `
      <h3 class="bus-heading">Which gateway receives which device</h3>
      <div class="table-wrapper">
        <table class="matrix">
          <thead><tr>
            <th>Address</th><th>Device</th>
            <th class="num">Telegrams</th>
            <th class="num" title="Telegrams of this address the gateways disagreed about">Differing</th>
            ${columns.map((column) => `<th class="num">${escapeHtml(column.gateway_name || column.gateway_id)}
              <span class="hint">count / rate / signal / path</span></th>`).join("")}
            <th>Last seen</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="footnote"><span class="path direct">direct</span> the telegram came straight
        out of the air, <span class="path hop">L1</span> / <span class="path hop">L2</span> it
        arrived through one or two repeaters. A device which is only heard over a repeater has
        no reserve of its own left at that gateway.</div>`;
  },

  /* ------------------------------------------------------------ single bursts */

  _burstTable(ctx, gateways, summary, report) {
    if (!summary.burst_count) return "";
    const bursts = report.bursts || [];
    const shown = bursts.filter((burst) => this._matchesBurst(ctx, burst));
    const names = new Map(gateways.map((gateway) => [String(gateway.gateway_id),
                                                     gateway.gateway_name || gateway.gateway_id]));
    // the buttons which filter this table sit directly above it - and nowhere else. The
    // heading names the active view as well: with a table full of rows, "did my click do
    // anything?" has to be answerable without counting them.
    const view = ctx.state.radioView || "all";
    const label = (VIEWS.find(([name]) => name === view) || ["", "all"])[1];
    const header = `
      <h3 class="bus-heading">One telegram, every gateway${view === "all" ? ""
        : ` &ndash; ${escapeHtml(label)}`}</h3>
      ${this._views(ctx, summary)}`;
    if (!shown.length) {
      return `${header}<div class="empty">${bursts.length
        ? "No telegram matches the text filter."
        : "No telegram of this kind was recorded - pick another view above."}</div>`;
    }

    const rows = shown.map((burst, index) => {
      const detailId = `burst-${index}-${burst.timestamp_ms}`;
      const open = !!(ctx.state.radioOpen || {})[this._burstKey(burst)];
      // red: the gateways did not receive or read the same thing. yellow: somebody missed it,
      // or it only arrived over a repeater. A hop alone is not a fault.
      const problem = (burst.disagreement || []).length || (burst.interpretation || []).length
        ? "issue" : (burst.missing_gateway_ids || []).length ? "attention" : "";
      return `
        <tr data-burst="${escapeHtml(this._burstKey(burst))}" data-detail="${detailId}"
            class="${problem}">
          <td class="mono">${formatTime(burst.timestamp)}</td>
          <td class="mono">${escapeHtml(burst.address)}</td>
          <td>${escapeHtml(burst.device_name || "")}
            ${burst.known ? "" : `<span class="tag unknown">unknown</span>`}</td>
          <td class="num">${formatNumber(burst.gateway_count)}</td>
          <td>${(burst.members || []).map((member) => `
            <span class="kv"><i>${escapeHtml(names.get(String(member.gateway_id))
                                             || member.gateway_name || member.gateway_id)}</i>${
              member.rssi_dbm === null || member.rssi_dbm === undefined
                ? (member.direction === "outgoing" ? "sent" : "ok")
                : this._rssi(member.rssi_dbm)}</span>`).join("")}
            ${(burst.missing_gateway_ids || []).length
              ? `<span class="tag unknown" title="These gateways did not receive it">missing:
                   ${escapeHtml(burst.missing_gateway_ids.map((id) => names.get(String(id)) || id).join(", "))}</span>`
              : ""}</td>
          <td class="${problem === "issue" ? "issue" : ""}">${(burst.differences || []).length
            ? burst.differences.map((field) => `<span class="tag ${
                field === "rp_count" ? "role" : "unknown"}">${escapeHtml((FIELDS[field] || [field])[0])}</span>`).join(" ")
            : `<span class="hint">identical</span>`}</td>
          <td class="num">${formatNumber(burst.span_ms)} ms</td>
          <td class="num">${burst.rssi_spread === null || burst.rssi_spread === undefined
            ? "-" : `${formatNumber(burst.rssi_spread)} dB`}</td>
        </tr>
        <tr class="detail burst-detail ${open ? "visible" : ""}" id="${detailId}">
          <td colspan="8">${this._burstDetail(burst, names)}</td>
        </tr>`;
    }).join("");

    return `
      ${header}
      <div class="table-wrapper">
        <table class="clickable">
          <thead><tr>
            <th>Time</th><th>Address</th><th>Device</th>
            <th class="num">Gateways</th><th>Signal per gateway</th><th>Difference</th>
            <th class="num" title="Between the first and the last reception">Spread</th>
            <th class="num" title="Difference between the strongest and the weakest reception">Signal &Delta;</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="footnote">Click a row for the reception of every single gateway. Showing
        ${formatNumber(shown.length)} of ${formatNumber(report.selected_count === undefined
          ? bursts.length : report.selected_count)} telegrams of this kind${
          (report.selected_count || 0) > bursts.length
            ? ` (the last ${formatNumber(bursts.length)} are kept with all their details)` : ""}.</div>`;
  },

  /**
   * The receptions of one transmission side by side, differing bytes marked.
   *
   * Marked against the reception which came in first, not against the majority: with two
   * gateways reporting two different bytes there is no majority, and the difference has to be
   * visible anyway. Which gateway is *wrong* is a different question - that one is only
   * answered (as "differs") when more gateways agree on one value.
   */
  _burstDetail(burst, names) {
    const reference = burst.reference || {};
    const first = (burst.members || [])[0] || {};
    /** the value of this gateway is not what the first reception said */
    const differs = (member, key) => member.gateway_id !== first.gateway_id
      && String(member[key] === null || member[key] === undefined ? "-" : member[key])
         !== String(first[key] === null || first[key] === undefined ? "-" : first[key]);

    const rows = (burst.members || []).map((member) => {
      const deviates = ["msg_type", "org", "data", "status_base", "eep", "decoded"]
        .some((key) => differs(member, key));
      return `
      <tr class="${deviates ? "issue" : ""}">
        <td>${escapeHtml(names.get(String(member.gateway_id)) || member.gateway_name || member.gateway_id)}
          ${member.direction === "outgoing"
            ? `<span class="tag role" title="This gateway sent the telegram">sent</span>` : ""}
          ${(burst.outlier_gateway_ids || []).includes(member.gateway_id)
            ? `<span class="tag unknown">differs</span>` : ""}
          ${member.local_address && member.local_address !== member.address
            ? `<span class="hint">bus ${escapeHtml(member.local_address)}</span>` : ""}</td>
        <td class="num">+${formatNumber(member.offset_ms)} ms</td>
        <td class="mono ${differs(member, "msg_type") ? "issue" : ""}">${escapeHtml(member.msg_type || "-")}</td>
        <td class="mono ${differs(member, "org") ? "issue" : ""}">${escapeHtml(member.org || "-")}</td>
        <td class="mono ${differs(member, "data") ? "issue" : ""}">${this._bytes(member.data,
          member.gateway_id === reference.gateway_id ? null : reference.data)}</td>
        <td class="mono ${differs(member, "status_base") ? "issue" : ""}">${escapeHtml(member.status || "-")}</td>
        <td class="${differs(member, "rp_count") ? "attention" : ""}">${this._level(member.rp_count)}${member.repeats
          ? ` <span class="hint">+${formatNumber(member.repeats)} repetition(s)</span>` : ""}</td>
        <td class="num">${this._rssi(member.rssi_dbm)}</td>
        <td class="mono ${differs(member, "eep") ? "issue" : ""}">${escapeHtml(member.eep || "-")}</td>
        <td class="${differs(member, "decoded") ? "issue" : ""}">${escapeHtml(member.decoded || "-")}</td>
      </tr>`;
    }).join("");

    const values = (burst.differences || []).map((field) => `
      <div><b>${escapeHtml((FIELDS[field] || [field])[0])}:</b>
        ${Object.entries((burst.values || {})[field] || {}).map(([value, ids]) => `
          <span class="kv"><i>${escapeHtml(value)}</i>${escapeHtml(ids
            .map((id) => names.get(String(id)) || id).join(", "))}</span>`).join(" ")}
        ${(burst.tied || []).includes(field)
          ? `<span class="hint">Evenly split - no gateway can be called the wrong one here.</span>`
          : (burst.majority || {})[field] !== undefined
            ? `<span class="hint">${escapeHtml((burst.majority || {})[field])} is what most
                 gateways reported.</span>`
            : ""}</div>`).join("");

    return `
      <table>
        <thead><tr>
          <th>Gateway</th><th class="num">Offset</th><th>Message type</th><th>ORG</th>
          <th>Data</th><th>Status</th><th>Path</th><th class="num">Signal</th>
          <th>Read as</th><th>Values</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
      ${values ? `<div class="values">${values}</div>` : ""}
      ${(burst.missing_gateway_ids || []).length
        ? `<div class="values"><b>Did not receive it:</b>
             ${escapeHtml(burst.missing_gateway_ids.map((id) => names.get(String(id)) || id).join(", "))}</div>`
        : ""}
      <div class="values hint">First reception ${escapeHtml(formatDateTime(burst.timestamp))}</div>`;
  },

  _footnote(summary) {
    return `
      <div class="footnote">Receptions of the same address within
        ${formatNumber(summary.window_ms || DEFAULT_WINDOW_MS)} ms are treated as one
        transmission - the window is a control, everything is recomputed when it changes. The
        last ${formatNumber(summary.buffer_size)} receptions are kept
        ${summary.covers_from ? `(back to ${escapeHtml(formatDateTime(summary.covers_from))})` : ""}
        independently of the live telegram buffer, so clearing the live view keeps them.
        ${summary.dropped_count
          ? `${formatNumber(summary.dropped_count)} older receptions have fallen out of it.` : ""}
        Signal strength is only reported by ESP3 transceivers (USB300, MGW, FAM-USB), never by
        the ESP2 gateways of the RS485 bus (FAM14, FGW14-USB).</div>`;
  },

  afterRender(ctx, root) {
    // the sender list comes from the report, the toolbar is built before the first one
    // arrives - so its options are patched in here instead of rebuilding the toolbar
    this._syncSenders(ctx, root);

    root.querySelectorAll("button[data-view]").forEach((button) => {
      button.addEventListener("click", () => {
        ctx.state.radioView = button.dataset.view;
        this._reload(ctx);
      });
    });
    root.querySelectorAll("button[data-gateway]").forEach((button) => {
      button.addEventListener("click", () => {
        const id = button.dataset.gateway;
        const selected = (ctx.state.radioGateways || []).map(String);
        if (!id) {
          ctx.state.radioGateways = [];
        } else if (selected.includes(id)) {
          ctx.state.radioGateways = selected.filter((entry) => entry !== id);
        } else {
          ctx.state.radioGateways = [...selected, id];
        }
        this._reload(ctx);
      });
    });
    root.querySelectorAll("button[data-sender]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        ctx.state.radioSender = button.dataset.sender || null;
        this._reload(ctx);
      });
    });

    root.querySelectorAll("tr[data-burst]").forEach((row) => {
      row.addEventListener("click", () => {
        const detail = root.getElementById(row.dataset.detail);
        if (!detail) return;
        detail.classList.toggle("visible");
        // remembered in the state: the page reloads whenever a telegram arrives, and a detail
        // which closes under the reader is worse than no detail at all
        if (!ctx.state.radioOpen) ctx.state.radioOpen = {};
        if (detail.classList.contains("visible")) {
          ctx.state.radioOpen[row.dataset.burst] = true;
        } else {
          delete ctx.state.radioOpen[row.dataset.burst];
        }
      });
    });
  },

  /**
   * Options of the sender select, patched into the existing element.
   *
   * Rebuilt only when the set of senders really changed - replacing the options of a select
   * closes its dropdown, and this runs on every refresh.
   */
  _syncSenders(ctx, root) {
    const select = root.getElementById("radio-sender");
    if (!select) return;
    const senders = ((this._summary(ctx).available || {}).addresses) || [];
    const signature = senders.map((sender) => sender.address).join(",");
    if (signature === this._senderSignature) {
      select.value = ctx.state.radioSender || "";
      return;
    }
    this._senderSignature = signature;
    select.innerHTML = `
      <option value="">all senders</option>
      ${senders.map((sender) => `
        <option value="${escapeHtml(sender.address)}">
          ${escapeHtml(sender.name ? `${sender.address} - ${sender.name}` : sender.address)}
          (${formatNumber(sender.count)})</option>`).join("")}`;
    select.value = ctx.state.radioSender || "";
  },

  /* ------------------------------------------------------------------ helpers */

  _burstKey(burst) {
    return `${burst.address}|${burst.timestamp_ms}`;
  },

  /** How a telegram arrived: directly, or through one or two repeaters. */
  _level(hops) {
    const level = Number(hops || 0);
    if (!level) return `<span class="path direct">direct</span>`;
    return `<span class="path hop" title="Arrived through ${level} repeater${level === 1 ? "" : "s"}">L${level}</span>`;
  },

  /** The paths a gateway received a device over, with how many telegrams took each of them. */
  _levels(byLevel) {
    const entries = Object.entries(byLevel || {});
    if (!entries.length) return "";
    return `<span class="control-row">${entries
      .sort((left, right) => Number(left[0]) - Number(right[0]))
      .map(([level, count]) => `<span class="path ${Number(level) ? "hop" : "direct"}"
              title="${Number(level)
                ? `${formatNumber(count)} telegram(s) arrived through ${level} repeater(s)`
                : `${formatNumber(count)} telegram(s) arrived directly`}">${Number(level)
                ? `L${escapeHtml(level)}` : "direct"} ${formatNumber(count)}</span>`).join("")}</span>`;
  },

  /** Signal strength as a percentage of the usable range - see RSSI_BEST / RSSI_WORST. */
  _rssiPercent(dbm) {
    if (dbm === null || dbm === undefined) return null;
    const percent = ((Number(dbm) - RSSI_WORST) / (RSSI_BEST - RSSI_WORST)) * 100;
    return Math.max(0, Math.min(100, Math.round(percent)));
  },

  _rssi(dbm) {
    if (dbm === null || dbm === undefined) return "-";
    return `${formatNumber(dbm)} dBm`;
  },

  _share(share) {
    if (share === null || share === undefined) return "-";
    return `${Math.round(Number(share) * 1000) / 10} %`;
  },

  /** A bar which turns yellow below `weakBelow` and red below `badBelow` (percent). */
  _meter(percent, weakBelow, badBelow) {
    if (percent === null || percent === undefined) return "";
    const level = percent < badBelow ? "bad" : percent < weakBelow ? "weak" : "";
    return `<span class="meter ${level}"><span style="width: ${percent}%"></span></span>`;
  },

  _bytes(value, majority) {
    const bytes = String(value === null || value === undefined ? "" : value).split(/[\s-]+/).filter(Boolean);
    if (!bytes.length) return "-";
    const reference = String(majority || "").split(/[\s-]+/).filter(Boolean);
    if (!reference.length) return escapeHtml(bytes.join("-"));
    return bytes
      .map((byte, index) => byte === reference[index]
        ? escapeHtml(byte) : `<b class="byte-diff">${escapeHtml(byte)}</b>`)
      .join("-");
  },

  _matchesAddress(ctx, address, gateways) {
    const names = (address.gateways ? Object.keys(address.gateways) : [])
      .map((id) => (gateways.find((gateway) => String(gateway.gateway_id) === id) || {}).gateway_name);
    return matchesFilter(ctx.state.radioFilter, [address.address, address.name, address.eep, ...names]);
  },

  _matchesBurst(ctx, burst) {
    return matchesFilter(ctx.state.radioFilter, [
      burst.address, burst.device_name, burst.eep,
      ...(burst.members || []).map((member) => member.gateway_name),
      ...(burst.members || []).map((member) => member.data),
      ...(burst.members || []).map((member) => member.decoded),
      ...(burst.differences || []),
    ]);
  },

  /** The "who receives what" table as csv - one column block per gateway. */
  _csv(ctx) {
    const gateways = this._gatewayRows(ctx).filter((gateway) => gateway.received > 0 || gateway.configured);
    const columns = ["address", "device", "eep", "known", "telegrams", "differing", "disagreeing",
                     "last_seen"];
    for (const gateway of gateways) {
      const name = String(gateway.gateway_name || gateway.gateway_id).replace(/;/g, ",");
      columns.push(`${name} count`, `${name} rate`, `${name} rssi_avg`, `${name} direct`,
                   `${name} repeated`);
    }
    const rows = ((ctx.state.radioComparison || {}).addresses || []).map((address) => {
      const row = {
        address: address.address, device: address.name, eep: address.eep, known: address.known,
        telegrams: address.bursts, differing: address.differing, disagreeing: address.disagreeing,
        last_seen: address.last_seen,
      };
      for (const gateway of gateways) {
        const name = String(gateway.gateway_name || gateway.gateway_id).replace(/;/g, ",");
        const entry = (address.gateways || {})[String(gateway.gateway_id)] || {};
        row[`${name} count`] = entry.count || 0;
        row[`${name} rate`] = entry.share === null || entry.share === undefined ? "" : entry.share;
        row[`${name} rssi_avg`] = entry.rssi_avg === null || entry.rssi_avg === undefined
          ? "" : entry.rssi_avg;
        row[`${name} direct`] = entry.direct || 0;
        row[`${name} repeated`] = (entry.count || 0) - (entry.direct || 0);
      }
      return row;
    });
    return { columns, rows };
  },
};
