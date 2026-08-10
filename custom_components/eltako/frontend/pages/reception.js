/**
 * Reception: how well do the gateways hear, and what arrives through a repeater?
 *
 * A site survey for EnOcean. It answers the question which decides whether an installation
 * works in a year as well as today: not "does the telegram arrive" but "how much reserve
 * does the link have". Two numbers say it, both are in every recorded telegram
 * (observation/reception.py aggregates them):
 *
 * * the **signal strength** in dBm - reported by ESP3 transceivers (FAM-USB, USB300, LAN
 *   gateways). -55 dBm survives a closed door, -88 dBm does not survive a moved cupboard.
 * * the **repeater share** - a telegram which arrives through a repeater did not make it
 *   directly. A link which is mostly repeated is a link which is not really there.
 *
 * The page is built for walking: a short window (the default is one minute), a live reading
 * which follows within seconds, and **"save this spot"** - the current measurement is kept
 * under a name, so the positions can be compared afterwards instead of remembered. The spots
 * survive a reload (they live in the browser) and can be exported as CSV.
 *
 * Two ways to use it:
 * 1. carry the **gateway** (a USB stick on a laptop / a LAN gateway on a power bank) and
 *    press a device which stays where it is,
 * 2. or leave the gateway where it will be installed and carry the **transmitter** through
 *    the rooms - the "walk" filter pins the survey to that one address.
 */

import { WS } from "../lib/api.js";
import { download, escapeHtml, formatDateTime, formatNumber, icon,
         timestampForFilename, toCsv } from "../lib/utils.js";

/** windows to choose from - short ones are for walking, long ones for judging a position */
const WINDOWS = [
  { value: 60, label: "last minute" },
  { value: 300, label: "last 5 minutes" },
  { value: 900, label: "last 15 minutes" },
  { value: 3600, label: "last hour" },
];

/** how a quality of observation/reception.py is shown */
const QUALITY = {
  excellent: { label: "excellent", tone: "good", hint: "plenty of reserve" },
  good: { label: "good", tone: "good", hint: "survives a closed door" },
  fair: { label: "fair", tone: "", hint: "works, but without much reserve" },
  weak: { label: "weak", tone: "warn", hint: "one obstacle more and it is gone" },
};

// dBm range the bars are drawn over: -100 is "barely there", -40 is right next to it
const RSSI_FLOOR = -100;
const RSSI_CEILING = -40;

const SPOT_STORAGE_KEY = "eltako-reception-spots";

const CSV_COLUMNS = ["spot", "measured_at", "window_seconds", "gateway_id", "gateway_name",
                     "address", "device", "count", "per_minute", "rssi_last", "rssi_avg",
                     "rssi_min", "rssi_max", "quality", "repeated", "repeated_share"];

// TODO type check: add /** @type {import("../types.js").Page} */ once the dom casts are in
export const page = {
  id: "reception",
  title: "Reception",
  subtitle: "How well the gateways hear - signal strength, repeaters and coverage",
  icon: "mdi:signal-variant",
  glyph: "≈",
  needsRecording: true,
  refreshMs: 3000,

  styles: `
    .survey-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
                    gap: 12px; margin-bottom: 14px; }
    .survey-card { background: var(--eltako-card); border: 1px solid var(--eltako-border);
                   border-left-width: 4px; border-radius: var(--eltako-radius); padding: 12px 14px;
                   display: flex; flex-direction: column; gap: 6px; }
    .survey-card.good { border-left-color: var(--eltako-good, #2E7D32); }
    .survey-card.warn { border-left-color: var(--eltako-warn); }
    .survey-card .survey-name { font-weight: 500; display: flex; align-items: center; gap: 6px; }
    .survey-card .survey-value { font-size: 1.6rem; font-weight: 600; font-variant-numeric: tabular-nums; }
    .survey-card .survey-value small { font-size: .8rem; font-weight: 400; color: var(--eltako-muted); }
    .survey-card .survey-note { font-size: .75rem; color: var(--eltako-muted); }
    /* the bar is the thing one watches while walking - wide, flat, and it moves */
    .rssi-bar { height: 6px; border-radius: 999px; background: var(--eltako-tint-strong);
                overflow: hidden; }
    .rssi-bar i { display: block; height: 100%; border-radius: 999px; background: var(--eltako-accent);
                  transition: width .4s ease; }
    .rssi-bar.warn i { background: var(--eltako-warn); }
    td .rssi-bar { min-width: 70px; }
    .quality-tag { font-size: .7rem; padding: 1px 7px; border-radius: 10px;
                   background: var(--eltako-tint-strong); }
    .quality-tag.warn { background: var(--eltako-warn); color: #212121; }
    .repeated-share { font-variant-numeric: tabular-nums; }
    .repeated-share.warn { color: var(--eltako-warn); font-weight: 500; }
    .spot-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0; }
    .survey-hint { font-size: .78rem; color: var(--eltako-muted); margin: 8px 0 0; }
  `,

  async load(ctx) {
    ctx.state.receptionWindow = ctx.state.receptionWindow || WINDOWS[0].value;
    if (!ctx.state.receptionSpots) ctx.state.receptionSpots = this._loadSpots();
    await Promise.all([ctx.loadLogInfo(), this._loadSurvey(ctx)]);
  },

  /** The survey is its own request - it is the only thing which has to be current. */
  async _loadSurvey(ctx) {
    const survey = await ctx.api.call(WS.RECEPTION_SURVEY, {
      window: ctx.state.receptionWindow || WINDOWS[0].value,
      address: ctx.state.receptionAddress || null,
    });
    if (survey) ctx.state.reception = survey;
    return ctx.state.reception;
  },

  renderStatus(ctx) {
    const survey = ctx.state.reception || {};
    return `
      <span class="pill ${survey.telegrams ? "on" : "warn"}">${formatNumber(survey.telegrams || 0)}
        telegram${survey.telegrams === 1 ? "" : "s"}</span>
      ${survey.has_rssi ? "" : `<span class="pill warn"
        title="Only ESP3 transceivers (FAM-USB, USB300, LAN gateways) report a signal strength. Everything else is counted, but without dBm.">no signal strength</span>`}
      <span class="pill">${(ctx.state.receptionSpots || []).length} spot${
        (ctx.state.receptionSpots || []).length === 1 ? "" : "s"}</span>`;
  },

  renderToolbar(ctx) {
    const addresses = this._addresses(ctx);
    return `
      <select id="reception-window" title="A short window follows you while you walk, a long one judges a position">
        ${WINDOWS.map((entry) => `<option value="${entry.value}"
          ${entry.value === ctx.state.receptionWindow ? "selected" : ""}>${entry.label}</option>`).join("")}
      </select>
      <select id="reception-address" title="Watch one transmitter only - the one you carry around">
        <option value="">every transmitter</option>
        ${addresses.map((address) => `<option value="${escapeHtml(address.address)}"
          ${address.address === ctx.state.receptionAddress ? "selected" : ""}
          >${escapeHtml(address.label)}</option>`).join("")}
      </select>
      <span class="spacer"></span>
      <input id="spot-name" type="search" placeholder="Name of this spot&hellip;" />
      <button id="save-spot" class="action primary">${icon("mdi:map-marker-plus", "◉")} Save this spot</button>
      <button id="export-spots" class="action">Export CSV</button>
      <button id="clear-spots" class="action danger">Clear spots</button>`;
  },

  bindToolbar(ctx, root) {
    root.getElementById("reception-window").addEventListener("change", async (event) => {
      ctx.state.receptionWindow = Number(event.target.value);
      await this._loadSurvey(ctx);
      ctx.requestContentRender(true);
    });
    root.getElementById("reception-address").addEventListener("change", async (event) => {
      ctx.state.receptionAddress = event.target.value || null;
      await this._loadSurvey(ctx);
      ctx.requestContentRender(true);
    });
    root.getElementById("save-spot").addEventListener("click", () => {
      const input = root.getElementById("spot-name");
      this._saveSpot(ctx, (input && input.value) || "");
      if (input) input.value = "";
      ctx.requestRender();
    });
    root.getElementById("export-spots").addEventListener("click", () => {
      const rows = (ctx.state.receptionSpots || []).flatMap((spot) => spot.links.map((link) => ({
        spot: spot.name, measured_at: spot.measured_at, window_seconds: spot.window_seconds,
        gateway_id: link.gateway_id, gateway_name: link.gateway_name, address: link.address,
        device: link.name || "", count: link.count, per_minute: link.per_minute,
        rssi_last: link.rssi.last, rssi_avg: link.rssi.avg, rssi_min: link.rssi.min,
        rssi_max: link.rssi.max, quality: link.quality || "", repeated: link.repeated,
        repeated_share: link.repeated_share,
      })));
      download(`eltako_reception_${timestampForFilename()}.csv`, toCsv(CSV_COLUMNS, rows), "text/csv");
    });
    root.getElementById("clear-spots").addEventListener("click", () => {
      if (!(ctx.state.receptionSpots || []).length) return;
      if (!confirm("Delete all saved spots of this survey?")) return;
      ctx.state.receptionSpots = [];
      this._storeSpots([]);
      ctx.requestRender();
    });
  },

  render(ctx) {
    if (ctx.state.logInfo && ctx.state.logInfo.enabled === false) return ctx.renderRecordingDisabled();

    const survey = ctx.state.reception;
    if (!survey) return `<div class="empty">Measuring&hellip;</div>`;

    return `
      ${this._renderGateways(ctx, survey)}
      ${this._renderLinks(ctx, survey)}
      ${this._renderSpots(ctx)}
      <div class="survey-hint">
        Only <b>radio</b> telegrams are surveyed: what a gateway read off its RS485 wire (bus
        polling and the telegrams of the actuators on that bus) says nothing about radio
        coverage and is left out.
        The signal strength is what an <b>ESP3</b> transceiver reports for a received telegram
        (FAM-USB, USB300, LAN gateways); a FAM14 receives by radio but reports none - for it
        the counters and the repeater share are the measurement.
        <b>Repeated</b> means the telegram arrived through a repeater instead of directly:
        that is coverage which only exists as long as the repeater does.
        ${survey.buffer_limited ? `<br><b>Note:</b> the recording buffer only reaches back to
          ${escapeHtml(formatDateTime(survey.covers_from))} - the numbers describe less time
          than the selected window. Increase <code>telegram_log_buffer_size</code> for a
          longer survey.` : ""}
      </div>`;
  },

  _renderGateways(ctx, survey) {
    if (!(survey.gateways || []).length) {
      return `<div class="empty">No radio telegram in the selected window. Press a button on a
        device - what arrives here is what a gateway can hear from where it is.</div>`;
    }

    return `
      <div class="survey-cards">
        ${survey.gateways.map((gateway) => {
          const quality = QUALITY[gateway.quality] || {};
          const repeatedWarn = gateway.repeated_share >= 0.25;
          return `
            <div class="survey-card ${quality.tone || ""}">
              <div class="survey-name">${icon("mdi:router-wireless", "((‧))")}
                ${escapeHtml(gateway.gateway_name || `Gateway ${gateway.gateway_id}`)}</div>
              <div class="survey-value">${gateway.rssi_avg === null ? "&ndash;"
                : `${gateway.rssi_avg} <small>dBm average</small>`}</div>
              ${this._bar(gateway.rssi_avg)}
              <div class="survey-note">
                ${quality.label ? `<span class="quality-tag ${quality.tone === "warn" ? "warn" : ""}"
                  >${quality.label}</span> ${escapeHtml(quality.hint || "")}` : "no signal strength reported"}
              </div>
              <div class="survey-note">
                ${formatNumber(gateway.telegrams)} telegrams of ${gateway.senders}
                transmitter${gateway.senders === 1 ? "" : "s"} &middot; ${gateway.per_minute}/min
              </div>
              <div class="survey-note ${repeatedWarn ? "warn" : ""}">
                <span class="repeated-share ${repeatedWarn ? "warn" : ""}"
                  >${Math.round(gateway.repeated_share * 100)}% repeated</span>
                ${repeatedWarn ? " - the direct path does not carry" : ""}
              </div>
            </div>`;
        }).join("")}
      </div>`;
  },

  _renderLinks(ctx, survey) {
    if (!(survey.links || []).length) return "";

    return `
      <div class="table-wrapper">
        <table>
          <thead><tr>
            <th>Transmitter</th><th>Gateway</th><th>Signal</th><th class="num">last</th>
            <th class="num">avg</th><th class="num">min / max</th><th class="num">Telegrams</th>
            <th class="num">Repeated</th><th>Last heard</th>
          </tr></thead>
          <tbody>${survey.links.map((link) => {
            const quality = QUALITY[link.quality] || {};
            const repeatedWarn = link.repeated_share >= 0.25;
            return `
              <tr class="${quality.tone === "warn" ? "unknown-row" : ""}">
                <td class="mono">${escapeHtml(link.address)}
                  ${link.name ? `<span class="hint">${escapeHtml(link.name)}</span>` : ""}</td>
                <td>${escapeHtml(link.gateway_name || link.gateway_id)}</td>
                <td>${this._bar(link.rssi.avg)}
                  ${quality.label ? `<span class="quality-tag ${quality.tone === "warn" ? "warn" : ""}"
                    >${quality.label}</span>` : `<span class="hint">no dBm</span>`}</td>
                <td class="num mono">${link.rssi.last === null ? "-" : link.rssi.last}</td>
                <td class="num mono">${link.rssi.avg === null ? "-" : link.rssi.avg}</td>
                <td class="num mono">${link.rssi.min === null ? "-"
                  : `${link.rssi.min} / ${link.rssi.max}`}</td>
                <td class="num">${formatNumber(link.count)}
                  <span class="hint">${link.per_minute}/min</span></td>
                <td class="num repeated-share ${repeatedWarn ? "warn" : ""}"
                  >${Math.round(link.repeated_share * 100)}%
                  ${link.repeated ? `<span class="hint">${link.repeated} of ${link.count}</span>` : ""}</td>
                <td class="mono">${link.last_seen ? escapeHtml(formatDateTime(link.last_seen)) : "-"}</td>
              </tr>`;
          }).join("")}</tbody>
        </table>
      </div>`;
  },

  /**
   * The spots which were measured so far, best first per gateway. This is what the whole
   * page is for: two positions cannot be compared from memory, and the difference between
   * -72 and -84 dBm is the difference between an installation which keeps working and one
   * which needs a repeater.
   */
  _renderSpots(ctx) {
    const spots = ctx.state.receptionSpots || [];
    if (!spots.length) {
      return `
        <div class="notice">
          <h3>${icon("mdi:map-marker-plus", "◉")} Measure a spot</h3>
          <p>Put the gateway where you want it (or carry the transmitter there), press a button
            on the device a few times and save the reading under a name. Do that in every place
            which is a candidate - the table which appears here compares them.</p>
        </div>`;
    }

    return `
      <h3 class="bus-heading">Measured spots
        <span class="hint-inline">${spots.length} saved in this browser</span></h3>
      <div class="table-wrapper">
        <table>
          <thead><tr>
            <th>Spot</th><th>Measured</th><th>Gateway</th><th class="num">Signal</th>
            <th>Quality</th><th class="num">Telegrams</th><th class="num">Repeated</th><th></th>
          </tr></thead>
          <tbody>${spots.map((spot) => (spot.gateways.length ? spot.gateways : [{}]).map((gateway, index) => {
            const quality = QUALITY[gateway.quality] || {};
            return `
              <tr>
                ${index === 0 ? `<td rowspan="${Math.max(spot.gateways.length, 1)}">
                  <b>${escapeHtml(spot.name)}</b></td>
                  <td rowspan="${Math.max(spot.gateways.length, 1)}" class="mono"
                    >${escapeHtml(formatDateTime(spot.measured_at))}</td>` : ""}
                <td>${escapeHtml(gateway.gateway_name || gateway.gateway_id || "nothing heard")}</td>
                <td class="num mono">${gateway.rssi_avg === null || gateway.rssi_avg === undefined
                  ? "-" : `${gateway.rssi_avg} dBm`}</td>
                <td>${quality.label ? `<span class="quality-tag ${quality.tone === "warn" ? "warn" : ""}"
                  >${quality.label}</span>` : "-"}</td>
                <td class="num">${formatNumber(gateway.telegrams || 0)}</td>
                <td class="num repeated-share ${(gateway.repeated_share || 0) >= 0.25 ? "warn" : ""}"
                  >${Math.round((gateway.repeated_share || 0) * 100)}%</td>
                ${index === 0 ? `<td rowspan="${Math.max(spot.gateways.length, 1)}">
                  <button class="action small danger" data-drop-spot="${escapeHtml(spot.id)}"
                    >remove</button></td>` : ""}
              </tr>`;
          }).join("")).join("")}</tbody>
        </table>
      </div>`;
  },

  afterRender(ctx, root) {
    root.querySelectorAll("button[data-drop-spot]").forEach((button) => {
      button.addEventListener("click", () => {
        ctx.state.receptionSpots = (ctx.state.receptionSpots || [])
          .filter((spot) => String(spot.id) !== button.dataset.dropSpot);
        this._storeSpots(ctx.state.receptionSpots);
        ctx.requestRender();
      });
    });
  },

  /* ------------------------------------------------------------------ helpers */

  /** One bar for a signal strength, drawn over the range which matters (-100 .. -40 dBm). */
  _bar(rssi) {
    if (rssi === null || rssi === undefined) return `<div class="rssi-bar"></div>`;
    const share = (rssi - RSSI_FLOOR) / (RSSI_CEILING - RSSI_FLOOR);
    const percent = Math.max(3, Math.min(100, Math.round(share * 100)));
    return `<div class="rssi-bar ${rssi < -85 ? "warn" : ""}"><i style="width:${percent}%"></i></div>`;
  },

  /** The transmitters which were heard, for the "watch one address" filter. */
  _addresses(ctx) {
    const seen = new Map();
    for (const link of ((ctx.state.reception || {}).links || [])) {
      if (!seen.has(link.address)) {
        seen.set(link.address, { address: link.address,
                                 label: link.name ? `${link.address} - ${link.name}` : link.address });
      }
    }
    // the address which is being watched stays in the list even if nothing arrived lately -
    // otherwise the filter would reset itself as soon as one walks out of range
    if (ctx.state.receptionAddress && !seen.has(ctx.state.receptionAddress)) {
      seen.set(ctx.state.receptionAddress,
               { address: ctx.state.receptionAddress, label: ctx.state.receptionAddress });
    }
    return [...seen.values()];
  },

  _saveSpot(ctx, name) {
    const survey = ctx.state.reception || {};
    const spots = ctx.state.receptionSpots || [];
    const spot = {
      // no Date.now() collision: a second spot in the same millisecond is not a thing a
      // human produces, and the name is what identifies it anyway
      id: String(new Date().getTime()),
      name: (name || "").trim() || `Spot ${spots.length + 1}`,
      measured_at: new Date().toISOString(),
      window_seconds: survey.window_seconds,
      address: ctx.state.receptionAddress || null,
      gateways: (survey.gateways || []).map((gateway) => ({ ...gateway })),
      links: (survey.links || []).map((link) => ({ ...link })),
    };
    ctx.state.receptionSpots = [...spots, spot];
    this._storeSpots(ctx.state.receptionSpots);
  },

  /** The spots live in the browser: a survey survives a reload and a lost connection. */
  _loadSpots() {
    try {
      const stored = window.localStorage.getItem(SPOT_STORAGE_KEY);
      const spots = stored ? JSON.parse(stored) : [];
      return Array.isArray(spots) ? spots : [];
    } catch (err) {
      return [];
    }
  },

  _storeSpots(spots) {
    try {
      window.localStorage.setItem(SPOT_STORAGE_KEY, JSON.stringify(spots || []));
    } catch (err) {
      // storage blocked or full: the spots still work for this session
    }
  },
};
