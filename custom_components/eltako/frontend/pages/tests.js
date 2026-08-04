/**
 * Tests page: the functional device tests of the EnOcean Device Manager,
 * running on the gateways of the standalone runtime.
 *
 *   burst - sends a burst of telegrams via gateway 1 and verifies that
 *           gateway 2 receives every single one (bus/radio reliability).
 *   cover - drives the configured covers with a movement sequence and
 *           measures their real travel times (basis for time_closes/time_opens).
 *
 * Backend: eltako_standalone/device_tests.py (websocket commands
 * eltako/device_tests/*). The page only exists in the standalone runtime and
 * only when the general setting 'enable_test_page' is on (default: on during
 * development). The same tests are available on the command line:
 * `python -m eltako_standalone devicetest burst|cover ...`
 */

import { escapeHtml, icon } from "../lib/utils.js";

const INFO = "eltako/device_tests/info";
const START = "eltako/device_tests/start";
const STOP = "eltako/device_tests/stop";
const SUBSCRIBE = "eltako/device_tests/subscribe";

function formatSeconds(value) {
  return value === null || value === undefined ? "-" : `${Number(value).toFixed(2)}s`;
}

export const page = {
  id: "tests",
  title: "Tests",
  subtitle: "Functional device tests of the EnOcean Device Manager (burst test, cover travel test)",
  icon: "mdi:test-tube",
  glyph: "✓",
  standaloneOnly: true,

  visible(ctx) {
    const settings = ((ctx.state || {}).integrationInfo || {}).general_settings || {};
    return settings.enable_test_page !== false && settings.enable_test_page !== "False";
  },

  styles: `
    .dt-form { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; margin: 8px 0 12px; }
    .dt-form label { display: flex; flex-direction: column; font-size: 12px; gap: 3px; }
    .dt-form input, .dt-form select { min-width: 90px; }
    .dt-form input.wide { min-width: 260px; }
    .dt-covers { display: flex; flex-wrap: wrap; gap: 10px; font-size: 13px; }
    .dt-log { max-height: 320px; overflow: auto; font-family: monospace; font-size: 12px;
              background: rgba(127,127,127,.08); border-radius: 6px; padding: 10px;
              white-space: pre-wrap; }
    .dt-log .ok { color: #2e7d32; } .dt-log .error { color: #c62828; }
    .dt-log .received { opacity: .85; }
    .dt-section { margin-bottom: 22px; }
    .dt-result table { margin-top: 6px; }
    .dt-problem { color: #c62828; }
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
      return `<div class="notice warn"><h3>No gateways</h3>
              <p>Configure at least one gateway first (page 'Device config').</p></div>`;
    }

    return `
      ${this._renderBurst(ctx, info)}
      ${this._renderCover(ctx, info)}
      ${this._renderLog(info)}
      ${this._renderResult(info)}`;
  },

  _gatewayOptions(info, selected) {
    return (info.gateways || []).map((gateway) => `
      <option value="${gateway.id}" ${String(gateway.id) === String(selected) ? "selected" : ""}>
        ${gateway.id}: ${escapeHtml(gateway.name || "")}${gateway.connected ? "" : " (not connected)"}
      </option>`).join("");
  },

  _renderBurst(ctx, info) {
    const test = (info.tests || []).find((t) => t.id === "burst") || {};
    const gateways = info.gateways || [];
    const second = gateways.length > 1 ? gateways[1].id : gateways[0].id;
    return `
      <div class="dt-section">
        <h2>${icon("mdi:sine-wave", "≈")} ${escapeHtml(test.name || "Bus burst test")}</h2>
        <p class="hint">${escapeHtml(test.description || "")}</p>
        <div class="dt-form">
          <label>Gateway 1 (sends)
            <select id="burst-gw1">${this._gatewayOptions(info, gateways[0].id)}</select></label>
          <label>Gateway 2 (receives)
            <select id="burst-gw2">${this._gatewayOptions(info, second)}</select></label>
          <label>Telegrams<input id="burst-count" type="number" value="44" min="1" max="1000" /></label>
          <label>Delay (s)<input id="burst-delay" type="number" value="0.01" step="0.01" min="0" /></label>
          <label>Runs<input id="burst-runs" type="number" value="1" min="1" max="100" /></label>
          <button class="action primary" id="burst-start" ${info.running ? "disabled" : ""}>Start</button>
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
      <div class="dt-section">
        <h2>${icon("mdi:window-shutter-settings", "▤")} ${escapeHtml(test.name || "Cover travel time test")}</h2>
        <p class="hint">${escapeHtml(test.description || "")}</p>
        <div class="dt-form">
          <label>Gateway
            <select id="cover-gw">${this._gatewayOptions(info, selectedGateway)}</select></label>
          <label>Sequence
            <input id="cover-sequence" class="wide" value="${escapeHtml(
              ctx.state.dtCoverSequence || (coverInfo ? coverInfo.default_sequence : "up:25,pause:2,down:25"))}"
              title="Movement commands: up/down/stop/pause with seconds, e.g. up:25,pause:2,down:25" /></label>
          <label>Runs<input id="cover-runs" type="number" value="1" min="1" max="20" /></label>
          <button class="action primary" id="cover-start"
                  ${info.running ? "disabled" : ""}>Start</button>
        </div>
        ${coverInfo && coverInfo.covers.length ? `
          <div class="dt-covers">
            ${coverInfo.covers.map((cover) => `
              <label><input type="checkbox" class="cover-select" value="${escapeHtml(cover.id)}" checked />
                ${escapeHtml(cover.name)} <span class="mono">(${escapeHtml(cover.id)})</span>
                <span class="hint">sender ${escapeHtml(cover.sender_id || "missing")},
                  opens ${cover.time_opens ?? "?"}s / closes ${cover.time_closes ?? "?"}s</span>
              </label>`).join("")}
          </div>`
        : `<div class="hint">No covers configured for this gateway - enter the addresses below.</div>`}
        <div class="dt-form">
          <label>Actuator addresses
            <input id="cover-addresses" class="wide" placeholder="00-00-00-06, 00-00-00-07"
              value="${escapeHtml(ctx.state.dtCoverAddresses || "")}"
              title="Overrides the selection above. Also works for actuators which are not configured yet." /></label>
          <label>Sender addresses
            <input id="cover-senders" class="wide" placeholder="00-00-B0-06, 00-00-B0-07"
              value="${escapeHtml(ctx.state.dtCoverSenders || "")}"
              title="Used pairwise with the actuator addresses. One sender for all is allowed." /></label>
        </div>
        <p class="hint">Leave both empty to test the covers selected above with their configured
          senders. Filling them lets you calibrate an actuator which is not configured yet - the
          two arrays are paired by position.</p>
      </div>`;
  },

  _renderLog(info) {
    const lines = info.log || [];
    return `
      <div class="dt-section">
        <h2>${icon("mdi:console-line", ">")} Log
          ${info.running ? `<span class="tag role">running: ${escapeHtml(info.test || "")}</span>
            <button class="action" id="dt-stop">Stop</button>` : ""}</h2>
        <div class="dt-log" id="dt-log">${lines.map((entry) =>
          `<div class="${escapeHtml(entry.style || "")}">${escapeHtml(entry.line)}</div>`).join("")
          || '<span class="hint">No test executed yet.</span>'}</div>
      </div>`;
  },

  _renderResult(info) {
    const result = info.result;
    if (!result || info.running) return "";
    const badge = result.success
      ? `<span class="tag">✔ successful</span>` : `<span class="tag unknown">✘ failed</span>`;

    if (result.test === "burst" && result.runs) {
      return `
        <div class="dt-section dt-result">
          <h2>Result ${badge}</h2>
          <table><thead><tr><th>run</th><th>sent</th><th>received</th><th>missing</th>
            <th>other telegrams</th><th>result</th></tr></thead>
          <tbody>${result.runs.map((run) => `
            <tr><td>${run.run}</td><td>${run.sent}</td><td>${run.received}</td>
              <td>${run.missing}</td><td>${run.other_messages}</td>
              <td>${run.success ? "OK" : `<span class="dt-problem">missing: ${escapeHtml(
                (run.missing_addresses || []).slice(0, 5).join(", "))}</span>`}</td></tr>`).join("")}
          </tbody></table>
        </div>`;
    }

    if (result.test === "cover" && result.movements) {
      return `
        <div class="dt-section dt-result">
          <h2>Result ${badge}</h2>
          <table><thead><tr><th>run</th><th>step</th><th>cover</th><th>command</th>
            <th>react</th><th>measured</th><th>reported</th><th>dir</th><th>end</th><th>result</th>
          </tr></thead>
          <tbody>${result.movements.map((movement) => `
            <tr><td>${movement.run}</td><td>${movement.step}</td>
              <td class="mono">${escapeHtml(movement.cover)}</td>
              <td>${escapeHtml(movement.command)}</td>
              <td>${formatSeconds(movement.reaction_s)}</td>
              <td>${formatSeconds(movement.measured_s)}</td>
              <td>${formatSeconds(movement.reported_s)}</td>
              <td>${escapeHtml(movement.direction || "-")}</td>
              <td>${escapeHtml(movement.end_position || "-")}</td>
              <td>${movement.problems.length
                ? `<span class="dt-problem">${escapeHtml(movement.problems.join(", "))}</span>` : "OK"}</td>
            </tr>`).join("")}
          </tbody></table>
          ${(result.recommendations || []).map((rec) => `
            <p class="hint">Cover <span class="mono">${escapeHtml(rec.cover)}</span>:
              up ${rec.up_s ? `${rec.up_s.toFixed(1)}s` : "?"} (configured: ${rec.configured_opens ?? "?"}s),
              down ${rec.down_s ? `${rec.down_s.toFixed(1)}s` : "?"} (configured: ${rec.configured_closes ?? "?"}s)
              &rarr; configure at least ${Math.max(rec.up_s || 0, rec.down_s || 0).toFixed(1)}s.</p>`).join("")}
          ${result.interference_count
            ? `<p class="hint">${result.interference_count} foreign telegram(s) were received during the test.</p>` : ""}
        </div>`;
    }

    return `<div class="dt-section dt-result"><h2>Result ${badge}</h2>
            ${result.error ? `<p class="dt-problem">${escapeHtml(result.error)}</p>` : ""}</div>`;
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
  },
};
