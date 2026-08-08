/**
 * Tests page: functional device tests against the real hardware.
 *
 *   burst - sends a burst of telegrams via gateway 1 and verifies that
 *           gateway 2 receives every single one (bus/radio reliability).
 *   cover - drives the configured covers with a movement sequence and
 *           measures their real travel times (basis for time_closes/time_opens).
 *
 * Backend: custom_components/eltako/tools/device_tests.py (websocket commands
 * eltako/device_tests/*). The page is available in Home Assistant and in the standalone
 * runtime; it is shown when the general setting 'enable_test_page' is on (default: on
 * during development). The same tests are available on the command line:
 * `python -m eltako_standalone devicetest burst|cover ...`
 */

import { FORM_STYLES } from "../lib/form.js";
import { card, escapeHtml, formatNumber, icon } from "../lib/utils.js";

const INFO = "eltako/device_tests/info";
const START = "eltako/device_tests/start";
const STOP = "eltako/device_tests/stop";
const SUBSCRIBE = "eltako/device_tests/subscribe";

function formatSeconds(value) {
  return value === null || value === undefined ? "&ndash;" : `${Number(value).toFixed(2)} s`;
}

/** OK / problem as a badge, so a result table can be scanned by colour. */
function verdict(ok, problemText) {
  return ok
    ? `<span class="tag ok">OK</span>`
    : `<span class="tag failed">${escapeHtml(problemText || "failed")}</span>`;
}

// TODO type check: add /** @type {import("../types.js").Page} */ once the dom casts are in
export const page = {
  id: "tests",
  title: "Tests",
  subtitle: "Functional device tests against the real hardware (link reliability, cover travel times)",
  icon: "mdi:test-tube",
  glyph: "✓",

  visible(ctx) {
    const settings = ((ctx.state || {}).integrationInfo || {}).general_settings || {};
    return settings.enable_test_page !== false && settings.enable_test_page !== "False";
  },

  styles: FORM_STYLES + `
    .dt-covers { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .dt-cover { display: flex; gap: 8px; align-items: flex-start; font-size: .82rem;
                border: 1px solid var(--eltako-border); border-radius: 10px; padding: 8px 12px;
                background: var(--eltako-tint); cursor: pointer; }
    .dt-cover input { margin: 2px 0 0; }
    .dt-cover .hint { margin-top: 2px; }
    .dt-log { max-height: 340px; overflow: auto; font-family: "Roboto Mono", "SFMono-Regular", Consolas, monospace;
              font-size: .74rem; line-height: 1.5; background: var(--eltako-tint);
              border: 1px solid var(--eltako-border); border-radius: 10px; padding: 10px;
              white-space: pre-wrap; }
    .dt-log .ok { color: var(--label-badge-green, #43a047); }
    .dt-log .error { color: var(--error-color, #e53935); }
    .dt-log .received { color: var(--eltako-muted); }
    .dt-log-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
    .dt-log-head .spacer { flex: 1 1 auto; }
    /* a test runs for minutes (a cover sequence drives the shutters), so the page has to
       show at a glance that something is still going on */
    .dt-running { display: inline-flex; align-items: center; gap: 6px; font-size: .78rem;
                  color: var(--eltako-accent); }
    .dt-running::before { content: ""; width: 8px; height: 8px; border-radius: 50%;
                          background: var(--eltako-accent); animation: eltako-dt-pulse 1.2s ease-in-out infinite; }
    @keyframes eltako-dt-pulse { 0%, 100% { opacity: .25; transform: scale(.8); } 50% { opacity: 1; transform: scale(1.15); } }
    .tag.ok { background: var(--label-badge-green, #43a047); color: #fff; }
    .tag.failed { background: var(--error-color, #e53935); color: #fff; }
    .dt-result-head { display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; margin: 0 0 10px; }
    .dt-result-head h2 { margin: 0; }
    .dt-hint-list { margin: 10px 0 0; font-size: .78rem; color: var(--eltako-muted); }
  `,

  async load(ctx) {
    await ctx.loadIntegrationInfo();
    const info = await ctx.api.call(INFO);
    if (info) ctx.state.deviceTests = info;
    this._subscribe(ctx);
  },

  _subscribe(ctx) {
    if (this._unsubscribe) return;
    this._unsubscribe = ctx.api.hass.connection.subscribeMessage((event) => {
      const state = ctx.state.deviceTests;
      if (!state) return;
      if (event.kind === "log") {
        state.log = state.log || [];
        state.log.push({ line: event.line, style: event.style });
        if (state.log.length > 200) state.log.shift();
        const logElement = ctx.root && ctx.root.getElementById("dt-log");
        if (logElement) {
          const span = document.createElement("div");
          span.className = event.style || "";
          span.textContent = event.line;
          logElement.appendChild(span);
          logElement.scrollTop = logElement.scrollHeight;
          return;                                   // no full re-render while running
        }
      }
      if (event.kind === "status") state.running = event.running;
      if (event.kind === "result") state.result = event.result;
      ctx.requestContentRender();
    }, { type: SUBSCRIBE }).catch(() => { this._unsubscribe = null; });
  },

  render(ctx) {
    const info = ctx.state.deviceTests;
    if (!info) return `<div class="empty">Loading&hellip;</div>`;
    const gateways = info.gateways || [];
    if (!gateways.length) {
      return `<div class="notice warn"><h3>${icon("mdi:alert-outline", "!")} No gateways</h3>
              <p>The tests drive the gateways of the running integration. Configure at least one
                 gateway first (page <b>Devices</b>).</p></div>`;
    }

    return `
      ${this._renderStatus(info)}
      ${this._renderConfigCheck(ctx, info)}
      ${this._renderActuator(ctx, info)}
      ${this._renderBurst(ctx, info)}
      ${this._renderCover(ctx, info)}
      ${this._renderLog(info)}
      ${this._renderResult(info)}`;
  },

  /** Everything needed to decide whether a test can be started right now. */
  _renderStatus(info) {
    const gateways = info.gateways || [];
    const connected = gateways.filter((gateway) => gateway.connected).length;
    // the burst test needs two of these, not just two of any kind
    const wiredConnected = gateways.filter((gateway) => gateway.connected && gateway.wired).length;
    const result = info.result;
    const lastResult = !result ? "&ndash;"
      : result.success ? `<span class="tag ok">successful</span>`
      : `<span class="tag failed">failed</span>`;

    return `
      <div class="cards">
        ${card("Gateways", `${formatNumber(connected)} / ${formatNumber(gateways.length)}`, "",
               connected === gateways.length ? "all connected" : "not every gateway is connected")}
        ${card("Test state", info.running
                 ? `<span class="dt-running">${escapeHtml(info.test || "running")}</span>`
                 : "idle")}
        ${card("Last result", lastResult, "",
               result ? `${result.test} test` : info.running ? "the running test has no result yet" : "no test run yet")}
      </div>
      ${wiredConnected < 2 ? `<div class="notice"><h3>${icon("mdi:information-outline", "i")} Two wired
         gateways needed for the burst test</h3>
         <p>The burst test sends through one gateway and listens on a second one, so it needs two
            connected gateways <b>on the RS485 bus</b> (FAM14, FGW14-USB). It sends with the fixed
            addresses FF-00-00-01.., which lie outside every base id range - a wireless transceiver
            does not transmit them. The cover test works with a single gateway of any kind.</p>
         </div>` : ""}`;
  },

  /** Gateways a test may use. `wired` comes from the backend (device_tests.is_wired). */
  _gatewaysFor(info, test) {
    const gateways = info.gateways || [];
    return test && test.wired_gateways_only ? gateways.filter((gateway) => gateway.wired) : gateways;
  },

  _gatewayOptions(gateways, selected) {
    return gateways.map((gateway) => `
      <option value="${gateway.id}" ${String(gateway.id) === String(selected) ? "selected" : ""}>
        ${gateway.id}: ${escapeHtml(gateway.name || "")}${gateway.connected ? "" : " (not connected)"}
      </option>`).join("");
  },

  _field(label, control, help = "") {
    return `<div class="field"><label>${label}</label>${control}
            ${help ? `<span class="field-help">${help}</span>` : ""}</div>`;
  },

  /** The check which sends nothing - the first thing to run when something does not work. */
  _renderConfigCheck(ctx, info) {
    const test = (info.tests || []).find((t) => t.id === "config") || {};
    const gateways = info.gateways || [];

    return `
      <div class="form-card">
        <h3>${icon("mdi:clipboard-list-outline", "☑")} ${escapeHtml(test.name || "Configuration check")}</h3>
        <div class="field-help" style="margin:-6px 0 12px">${escapeHtml(test.description || "")}</div>
        <div class="form-grid">
          ${this._field("Gateway",
              `<select id="config-gw">
                 <option value="">all gateways</option>
                 ${this._gatewayOptions(gateways, ctx.state.dtConfigGateway ?? "")}
               </select>`,
              "The check reads the configuration only - no telegram is sent, nothing is changed.")}
        </div>
        <div class="form-actions">
          <button class="action primary" id="config-start" ${info.running ? "disabled" : ""}>Check configuration</button>
          <span class="field-help">Safe at any time, also while the bus is busy.</span>
        </div>
      </div>`;
  },

  /** Switch the actuators and see whether they answer - the teach-in test. */
  _renderActuator(ctx, info) {
    const test = (info.tests || []).find((t) => t.id === "actuator") || {};
    const gateways = info.gateways || [];
    const withActuators = gateways.find((gateway) => (info.actuators || {})[String(gateway.id)]);
    const selectedGateway = ctx.state.dtActuatorGateway ?? (withActuators || gateways[0]).id;
    const actuatorInfo = (info.actuators || {})[String(selectedGateway)];
    const actuators = (actuatorInfo || {}).actuators || [];

    return `
      <div class="form-card">
        <h3>${icon("mdi:transmission-tower", "⇄")} ${escapeHtml(test.name || "Actuator / teach-in test")}</h3>
        <div class="field-help" style="margin:-6px 0 12px">${escapeHtml(test.description || "")}</div>
        <div class="form-grid">
          ${this._field("Gateway",
              `<select id="actuator-gw">${this._gatewayOptions(gateways, selectedGateway)}</select>`)}
          ${this._field("Command per device",
              `<select id="actuator-command">
                 ${[["on_off", "switch on, then off"], ["off_on", "switch off, then on"],
                    ["on", "switch on only"], ["off", "switch off only"]]
                   .map(([value, label]) => `<option value="${value}"${
                     (ctx.state.dtActuatorCommand || "on_off") === value ? " selected" : ""
                   }>${label}</option>`).join("")}
               </select>`,
              "Every command is confirmed by the actuator with a status telegram.")}
          ${this._field("Answer timeout (s)",
              `<input id="actuator-timeout" type="number" value="3" min="0.5" max="30" step="0.5">`,
              "How long to wait for the status telegram of the actuator.")}
          ${this._field("Pause (s)",
              `<input id="actuator-settle" type="number" value="1" min="0" max="10" step="0.5">`,
              "Pause between two commands.")}
        </div>

        ${actuators.length ? `
          <div class="dt-covers">
            ${actuators.map((actuator) => `
              <label class="dt-cover">
                <input type="checkbox" class="actuator-select" value="${escapeHtml(actuator.id)}"
                       ${actuator.sender_id ? "checked" : "disabled"}>
                <span>
                  ${escapeHtml(actuator.name)} <span class="mono">${escapeHtml(actuator.id)}</span>
                  <span class="hint">${escapeHtml(actuator.platform)} &middot; sender ${actuator.sender_id
                      ? `<span class="mono">${escapeHtml(actuator.sender_id)}</span>
                         (${escapeHtml(actuator.sender_eep || "?")})`
                      : `<span class="tag failed">missing</span> &ndash; cannot be tested`}</span>
                </span>
              </label>`).join("")}
          </div>`
        : `<div class="field-help" style="margin-top:12px">No switch and no light is configured for
             this gateway. Covers have their own test below.</div>`}

        ${test.warning ? `<div class="notice warn" style="margin-top:14px">
          <h3>${icon("mdi:alert-outline", "!")} The actuators really switch</h3>
          <p>${escapeHtml(test.warning)}</p></div>` : ""}

        <div class="form-actions">
          <button class="action primary" id="actuator-start"
                  ${info.running || !actuators.length ? "disabled" : ""}>Start actuator test</button>
        </div>
      </div>`;
  },

  _renderBurst(ctx, info) {
    const test = (info.tests || []).find((t) => t.id === "burst") || {};
    // wireless transceivers cannot carry the test addresses, so they are not offered at all
    const gateways = this._gatewaysFor(info, test);
    const excluded = (info.gateways || []).length - gateways.length;

    if (gateways.length < 2) {
      return `
        <div class="form-card">
          <h3>${icon("mdi:sine-wave", "≈")} ${escapeHtml(test.name || "Bus burst test")}</h3>
          <div class="field-help" style="margin:-6px 0 12px">${escapeHtml(test.description || "")}</div>
          <div class="notice warn">
            <h3>${icon("mdi:alert-outline", "!")} Not enough wired gateways</h3>
            <p>${escapeHtml(test.gateway_requirement || "")}
              ${gateways.length === 1 ? "Only one wired gateway is configured."
                                      : "No wired gateway is configured."}
              ${excluded ? `${escapeHtml(String(excluded))} wireless
                ${excluded === 1 ? "gateway is" : "gateways are"} configured and cannot be used.` : ""}</p>
          </div>
        </div>`;
    }

    const second = gateways[1].id;

    return `
      <div class="form-card">
        <h3>${icon("mdi:sine-wave", "≈")} ${escapeHtml(test.name || "Bus burst test")}</h3>
        <div class="field-help" style="margin:-6px 0 12px">${escapeHtml(test.description || "")}</div>
        <div class="form-grid">
          ${this._field("Gateway 1 (sends)",
              `<select id="burst-gw1">${this._gatewayOptions(gateways, gateways[0].id)}</select>`,
              excluded ? `Bus gateways only &ndash; ${excluded} wireless
                ${excluded === 1 ? "gateway is" : "gateways are"} not offered.` : "")}
          ${this._field("Gateway 2 (receives)",
              `<select id="burst-gw2">${this._gatewayOptions(gateways, second)}</select>`)}
          ${this._field("Telegrams", `<input id="burst-count" type="number" value="44" min="1" max="1000">`,
              "One telegram per test address.")}
          ${this._field("Delay (s)", `<input id="burst-delay" type="number" value="0.01" step="0.01" min="0">`,
              "Pause between two telegrams - too short and the bus drops some.")}
          ${this._field("Runs", `<input id="burst-runs" type="number" value="1" min="1" max="100">`)}
        </div>
        <div class="form-actions">
          <button class="action primary" id="burst-start" ${info.running ? "disabled" : ""}>Start burst test</button>
          ${info.running ? `<span class="field-help">A test is already running.</span>` : ""}
        </div>
      </div>`;
  },

  _renderCover(ctx, info) {
    const test = (info.tests || []).find((t) => t.id === "cover") || {};
    const gateways = info.gateways || [];
    const withCovers = gateways.find((gateway) => (info.covers || {})[String(gateway.id)]);
    const selectedGateway = ctx.state.dtCoverGateway ?? (withCovers || gateways[0]).id;
    const coverInfo = (info.covers || {})[String(selectedGateway)];

    return `
      <div class="form-card">
        <h3>${icon("mdi:window-shutter-settings", "▤")} ${escapeHtml(test.name || "Cover travel time test")}</h3>
        <div class="field-help" style="margin:-6px 0 12px">${escapeHtml(test.description || "")}</div>
        <div class="form-grid">
          ${this._field("Gateway",
              `<select id="cover-gw">${this._gatewayOptions(gateways, selectedGateway)}</select>`)}
          ${this._field("Movement sequence",
              `<input id="cover-sequence" value="${escapeHtml(ctx.state.dtCoverSequence
                 || (coverInfo ? coverInfo.default_sequence : "up:25,pause:2,down:25"))}">`,
              "up / down / stop / pause with seconds, e.g. <code>up:25,pause:2,down:25</code>")}
          ${this._field("Runs", `<input id="cover-runs" type="number" value="1" min="1" max="20">`)}
        </div>

        ${coverInfo && coverInfo.covers.length ? `
          <div class="dt-covers">
            ${coverInfo.covers.map((cover) => `
              <label class="dt-cover">
                <input type="checkbox" class="cover-select" value="${escapeHtml(cover.id)}" checked>
                <span>
                  ${escapeHtml(cover.name)} <span class="mono">${escapeHtml(cover.id)}</span>
                  <span class="hint">sender ${cover.sender_id
                      ? `<span class="mono">${escapeHtml(cover.sender_id)}</span>`
                      : `<span class="tag failed">missing</span>`} &middot;
                    opens ${cover.time_opens ?? "?"} s / closes ${cover.time_closes ?? "?"} s</span>
                </span>
              </label>`).join("")}
          </div>`
        : `<div class="field-help" style="margin-top:12px">No cover is configured for this gateway
             &ndash; enter the addresses below to calibrate one.</div>`}

        <div class="form-grid" style="margin-top:14px">
          ${this._field("Actuator addresses",
              `<input id="cover-addresses" placeholder="00-00-00-06, 00-00-00-07"
                 value="${escapeHtml(ctx.state.dtCoverAddresses || "")}">`,
              "Overrides the selection above and also works for actuators which are not configured yet.")}
          ${this._field("Sender addresses",
              `<input id="cover-senders" placeholder="00-00-B0-06, 00-00-B0-07"
                 value="${escapeHtml(ctx.state.dtCoverSenders || "")}">`,
              "Paired by position with the actuator addresses. One sender for all is allowed.")}
        </div>

        <div class="form-actions">
          <button class="action primary" id="cover-start" ${info.running ? "disabled" : ""}>Start cover test</button>
          <span class="field-help">The covers really move &ndash; make sure nobody is standing in the way.</span>
        </div>
      </div>`;
  },

  _renderLog(info) {
    const lines = info.log || [];
    return `
      <h2>${icon("mdi:console-line", ">")} Log</h2>
      <div class="dt-log-head">
        ${info.running ? `<span class="dt-running">${escapeHtml(info.test || "")} is running</span>
          <button class="action danger" id="dt-stop">Stop</button>` : ""}
        <span class="field-help">${formatNumber(lines.length)} line(s)</span>
        <span class="spacer"></span>
        <button class="action small" id="dt-log-copy" ${lines.length ? "" : "disabled"}>Copy</button>
        <button class="action small" id="dt-log-clear" ${lines.length ? "" : "disabled"}>Clear view</button>
      </div>
      <div class="dt-log" id="dt-log">${lines.map((entry) =>
        `<div class="${escapeHtml(entry.style || "")}">${escapeHtml(entry.line)}</div>`).join("")
        || `<span class="hint">No test executed yet.</span>`}</div>`;
  },

  _renderResult(info) {
    const result = info.result;
    if (!result || info.running) return "";

    const head = `
      <div class="dt-result-head">
        <h2>${icon("mdi:clipboard-check-outline", "✓")} Result</h2>
        ${result.success ? `<span class="tag ok">successful</span>` : `<span class="tag failed">failed</span>`}
        ${result.test ? `<span class="field-help">${escapeHtml(result.test)} test</span>` : ""}
      </div>`;

    if (result.test === "burst" && result.runs) return head + this._renderBurstResult(result);
    if (result.test === "cover" && result.movements) return head + this._renderCoverResult(result);
    if (result.test === "actuator" && result.steps) return head + this._renderActuatorResult(result);
    if (result.test === "config" && result.findings) return head + this._renderConfigResult(result);

    return head + (result.error
      ? `<div class="notice warn"><p>${escapeHtml(result.error)}</p></div>` : "");
  },

  _renderBurstResult(result) {
    const runs = result.runs;
    const sum = (key) => runs.reduce((total, run) => total + (run[key] || 0), 0);
    const sent = sum("sent");
    const missing = sum("missing");
    const lossRate = sent ? (missing / sent) * 100 : 0;

    return `
      <div class="cards">
        ${card("Runs", `${formatNumber(runs.filter((run) => run.success).length)} / ${formatNumber(runs.length)}`,
               "", "successful")}
        ${card("Telegrams sent", formatNumber(sent), "", `${result.message_delay} s delay`)}
        ${card("Received", formatNumber(sum("received")))}
        ${card("Lost", formatNumber(missing), "", `${lossRate.toFixed(1)} % loss rate`)}
        ${card("Foreign telegrams", formatNumber(sum("other_messages")), "", "traffic of other devices")}
      </div>

      <div class="table-wrapper"><table>
        <thead><tr>
          <th>Run</th><th class="num">Sent</th><th class="num">Received</th><th class="num">Lost</th>
          <th class="num">Foreign</th><th>Result</th>
        </tr></thead>
        <tbody>
          ${runs.map((run) => `
            <tr>
              <td>${run.run}</td>
              <td class="num">${formatNumber(run.sent)}</td>
              <td class="num">${formatNumber(run.received)}</td>
              <td class="num">${formatNumber(run.missing)}</td>
              <td class="num">${formatNumber(run.other_messages)}</td>
              <td>${verdict(run.success, `${run.missing} missing`)}
                ${run.success ? "" : `<span class="hint mono">${escapeHtml(
                    (run.missing_addresses || []).slice(0, 6).join(", "))}${
                    (run.missing_addresses || []).length > 6 ? " ..." : ""}</span>`}</td>
            </tr>`).join("")}
        </tbody></table></div>
      ${missing ? `<p class="dt-hint-list">Telegrams were lost. Increase the delay between two
         telegrams, check the bus wiring and the distance to the receiver, and repeat the test
         with several runs to tell a one-off from a real problem.</p>` : ""}`;
  },

  _renderActuatorResult(result) {
    const steps = result.steps;
    const silent = [...new Set(steps.filter((step) => !step.answered).map((step) => step.device))];
    const times = steps.map((step) => step.response_s).filter((value) => value !== null && value !== undefined);
    const slowest = times.length ? Math.max(...times) : null;

    return `
      <div class="cards">
        ${card("Answered", `${formatNumber(result.answered)} / ${formatNumber(result.total)}`,
               "", "commands confirmed by the actuator")}
        ${card("Devices", formatNumber((result.devices || []).length), "", `command: ${result.command}`)}
        ${card("Slowest answer", formatSeconds(slowest), "", "round trip command -> status telegram")}
      </div>

      <div class="table-wrapper"><table>
        <thead><tr>
          <th>Device</th><th>Platform</th><th>Sender</th><th>Command</th>
          <th class="num">Answer</th><th>Result</th>
        </tr></thead>
        <tbody>
          ${steps.map((step) => `
            <tr>
              <td>${escapeHtml(step.name)} <span class="hint mono">${escapeHtml(step.device)}</span></td>
              <td>${escapeHtml(step.platform)}</td>
              <td class="mono">${escapeHtml(step.sender)}</td>
              <td>${escapeHtml(step.command)}</td>
              <td class="num">${formatSeconds(step.response_s)}</td>
              <td>${verdict(step.answered, "no answer")}</td>
            </tr>`).join("")}
        </tbody></table></div>

      ${silent.length ? `<p class="dt-hint-list">No answer from
        <span class="mono">${escapeHtml(silent.join(", "))}</span>. The actuator only answers a
        command whose sender is taught into it: check the sender id and teach it in
        ("check &amp; teach in HA senders" on the devices page, or PCT14). A wrong device address
        or a gateway which does not reach that device looks exactly the same &ndash; the
        configuration check above names both.</p>` : ""}`;
  },

  _renderConfigResult(result) {
    const counts = result.counts || {};
    const findings = result.findings || [];
    // failed = red, unknown = amber, role = neutral (see styles.js)
    const badge = { error: "failed", warning: "unknown", info: "role" };

    return `
      <div class="cards">
        ${card("Errors", formatNumber(counts.error || 0), counts.error ? "warn" : "", "cannot work like this")}
        ${card("Warnings", formatNumber(counts.warning || 0), "", "very probably broken")}
        ${card("Hints", formatNumber(counts.info || 0), "", "worth knowing")}
        ${card("Checked", formatNumber(result.device_count), "",
               `${formatNumber(result.gateway_count)} gateway(s)`)}
      </div>

      ${findings.length ? `
        <div class="table-wrapper"><table>
          <thead><tr><th>Severity</th><th>Device</th><th>Check</th><th>What to do</th></tr></thead>
          <tbody>
            ${findings.map((finding) => `
              <tr>
                <td><span class="tag ${badge[finding.severity] ?? ""}">${escapeHtml(finding.severity)}</span></td>
                <td>${finding.device
                      ? `${escapeHtml(finding.name || "")}
                         <span class="hint mono">${escapeHtml(finding.device)}</span>`
                      : `<span class="hint">gateway ${escapeHtml(String(finding.gateway_id ?? "-"))}</span>`}</td>
                <td class="mono">${escapeHtml(finding.check)}</td>
                <td>${escapeHtml(finding.message)}</td>
              </tr>`).join("")}
          </tbody></table></div>`
        : `<div class="notice"><p>${icon("mdi:check-circle-outline", "✓")} Nothing to complain
             about &ndash; every configured device fits its gateway, has a sender and is known
             on the bus.</p></div>`}`;
  },

  _renderCoverResult(result) {
    const movements = result.movements;
    const problems = movements.filter((movement) => movement.problems.length).length;

    return `
      <div class="cards">
        ${card("Movements", `${formatNumber(movements.length - problems)} / ${formatNumber(movements.length)}`,
               "", "behaved as requested")}
        ${card("Covers", formatNumber((result.covers || []).length))}
        ${card("Foreign telegrams", formatNumber(result.interference_count || 0), "",
               "received while the test was running")}
      </div>

      ${(result.recommendations || []).length ? `
        <div class="table-wrapper"><table>
          <thead><tr>
            <th>Cover</th><th class="num">Measured up</th><th class="num">time_opens</th>
            <th class="num">Measured down</th><th class="num">time_closes</th><th>Suggestion</th>
          </tr></thead>
          <tbody>
            ${result.recommendations.map((rec) => {
              const suggestion = Math.ceil(Math.max(rec.up_s || 0, rec.down_s || 0));
              return `
                <tr>
                  <td class="mono">${escapeHtml(rec.cover)}</td>
                  <td class="num">${formatSeconds(rec.up_s)}</td>
                  <td class="num">${rec.configured_opens == null ? "&ndash;" : `${rec.configured_opens} s`}</td>
                  <td class="num">${formatSeconds(rec.down_s)}</td>
                  <td class="num">${rec.configured_closes == null ? "&ndash;" : `${rec.configured_closes} s`}</td>
                  <td>${suggestion ? `configure at least <b>${suggestion} s</b>` : "&ndash;"}</td>
                </tr>`;
            }).join("")}
          </tbody></table></div>
        <p class="dt-hint-list">The measured time is the full travel of the slat/shutter. Configure
          <code>time_opens</code> and <code>time_closes</code> at least that high, otherwise the
          position Home Assistant calculates drifts away from reality.</p>` : ""}

      <h3>Movements</h3>
      <div class="table-wrapper"><table>
        <thead><tr>
          <th>Run</th><th>Step</th><th>Cover</th><th>Command</th>
          <th class="num">Reaction</th><th class="num">Measured</th><th class="num">Reported</th>
          <th>Direction</th><th>End position</th><th>Result</th>
        </tr></thead>
        <tbody>
          ${movements.map((movement) => `
            <tr>
              <td>${movement.run}</td>
              <td>${movement.step}</td>
              <td class="mono">${escapeHtml(movement.cover)}</td>
              <td>${escapeHtml(movement.command)}</td>
              <td class="num">${formatSeconds(movement.reaction_s)}</td>
              <td class="num">${formatSeconds(movement.measured_s)}</td>
              <td class="num">${formatSeconds(movement.reported_s)}</td>
              <td>${escapeHtml(movement.direction || "-")}</td>
              <td>${escapeHtml(movement.end_position || "-")}</td>
              <td>${verdict(!movement.problems.length, movement.problems.join(", "))}</td>
            </tr>`).join("")}
        </tbody></table></div>`;
  },

  afterRender(ctx, root) {
    const start = async (test, params) => {
      const started = await ctx.api.call(START, { test, params });
      if (!started) {
        alert(`Cannot start the test:\n${(ctx.api.lastError || {}).message || "unknown error"}`);
        return;
      }
      ctx.state.deviceTests.running = true;
      ctx.state.deviceTests.test = test;
      ctx.state.deviceTests.log = [];
      ctx.state.deviceTests.result = null;
      ctx.requestContentRender(true);
    };

    const configGateway = root.getElementById("config-gw");
    if (configGateway) configGateway.addEventListener("change", () => {
      ctx.state.dtConfigGateway = configGateway.value;
    });
    const configStart = root.getElementById("config-start");
    if (configStart) configStart.addEventListener("click", () => {
      const value = root.getElementById("config-gw").value;
      start("config", { gateways: value ? [Number(value)] : null });
    });

    const actuatorGateway = root.getElementById("actuator-gw");
    if (actuatorGateway) actuatorGateway.addEventListener("change", () => {
      ctx.state.dtActuatorGateway = Number(actuatorGateway.value);
      ctx.requestContentRender(true);
    });
    const actuatorCommand = root.getElementById("actuator-command");
    if (actuatorCommand) actuatorCommand.addEventListener("change", () => {
      ctx.state.dtActuatorCommand = actuatorCommand.value;
    });
    const actuatorStart = root.getElementById("actuator-start");
    if (actuatorStart) actuatorStart.addEventListener("click", () => {
      const selected = [...root.querySelectorAll(".actuator-select:checked")].map((box) => box.value);
      if (!selected.length) {
        alert("Select at least one actuator. A device without a sender cannot be tested - "
              + "configure a sender for it first.");
        return;
      }
      start("actuator", {
        gateway: Number(root.getElementById("actuator-gw").value),
        devices: selected,
        command: root.getElementById("actuator-command").value,
        timeout: Number(root.getElementById("actuator-timeout").value),
        settle: Number(root.getElementById("actuator-settle").value),
      });
    });

    const burstStart = root.getElementById("burst-start");
    if (burstStart) burstStart.addEventListener("click", () => start("burst", {
      gateway1: Number(root.getElementById("burst-gw1").value),
      gateway2: Number(root.getElementById("burst-gw2").value),
      count: Number(root.getElementById("burst-count").value),
      delay: Number(root.getElementById("burst-delay").value),
      runs: Number(root.getElementById("burst-runs").value),
    }));

    const coverGateway = root.getElementById("cover-gw");
    if (coverGateway) coverGateway.addEventListener("change", () => {
      ctx.state.dtCoverGateway = Number(coverGateway.value);
      ctx.state.dtCoverSequence = null;      // gateway changed: use its default sequence
      ctx.requestContentRender(true);
    });
    const coverSequence = root.getElementById("cover-sequence");
    if (coverSequence) coverSequence.addEventListener("input", () => {
      ctx.state.dtCoverSequence = coverSequence.value;
    });
    const coverStart = root.getElementById("cover-start");
    if (coverStart) {
      const addressList = (id) => (root.getElementById(id)?.value || "")
        .split(",").map((value) => value.trim()).filter(Boolean);

      coverStart.addEventListener("click", () => {
        // explicit addresses win over the checkbox selection - they also allow actuators
        // which are not configured yet (calibration)
        const explicit = addressList("cover-addresses");
        const senders = addressList("cover-senders");
        ctx.state.dtCoverAddresses = explicit.join(", ");
        ctx.state.dtCoverSenders = senders.join(", ");

        start("cover", {
          gateway: Number(root.getElementById("cover-gw").value),
          covers: explicit.length ? explicit
            : [...root.querySelectorAll(".cover-select:checked")].map((box) => box.value),
          senders: senders.length ? senders : null,
          sequence: root.getElementById("cover-sequence").value,
          runs: Number(root.getElementById("cover-runs").value),
        });
      });
    }

    const stop = root.getElementById("dt-stop");
    if (stop) stop.addEventListener("click", () => ctx.api.call(STOP));

    const copy = root.getElementById("dt-log-copy");
    if (copy) copy.addEventListener("click", async () => {
      const text = ((ctx.state.deviceTests || {}).log || []).map((entry) => entry.line).join("\n");
      try {
        await navigator.clipboard.writeText(text);
        copy.textContent = "Copied";
        setTimeout(() => { copy.textContent = "Copy"; }, 1500);
      } catch (error) {
        alert("The log could not be copied to the clipboard.");
      }
    });

    // only the view is cleared - the log of the backend (and the result) stay untouched
    const clear = root.getElementById("dt-log-clear");
    if (clear) clear.addEventListener("click", () => {
      if (ctx.state.deviceTests) ctx.state.deviceTests.log = [];
      ctx.requestContentRender(true);
    });
  },
};
