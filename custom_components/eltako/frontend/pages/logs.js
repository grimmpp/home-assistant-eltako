/**
 * Logs: what the integration itself writes, without leaving the web ui.
 *
 * The answers to "did the command really go out?", "why did the scan stop?" and "which
 * telegram could not be decoded?" are all in the log - which is the one place that is hard to
 * reach: it needs file access or the log viewer of Home Assistant, and it is mixed with every
 * other integration. The backend therefore keeps the records of the `eltako` logger in a ring
 * buffer (observation/integration_log.py) and this page reads them from there.
 *
 * The **log level** belongs on the same page: a log which does not contain the answer is worth
 * nothing, and switching to debug means editing configuration.yaml and restarting otherwise.
 * Here it takes effect immediately, is remembered, and 'inherit' gives it back to Home
 * Assistant.
 */

import { WS } from "../lib/api.js";
import { card, download, escapeHtml, timestampForFilename } from "../lib/utils.js";

/** '2026-08-10T14:12:03.481' -> '14:12:03.481' - a log is read by time of day, not by date. */
function logTime(time) {
  const text = String(time || "");
  return text.includes("T") ? text.split("T")[1] : text;
}

/** How a level is shown - and what it means for somebody looking for a problem. */
const LEVELS = {
  DEBUG: { tone: "muted", label: "debug" },
  INFO: { tone: "", label: "info" },
  WARNING: { tone: "warn", label: "warning" },
  ERROR: { tone: "bad", label: "error" },
  CRITICAL: { tone: "bad", label: "critical" },
};

/** What the level selector offers, with the consequence spelled out. */
const LEVEL_HINTS = {
  inherit: "as configured in Home Assistant (`logger:`)",
  debug: "everything, including every telegram of the bus - a lot, and the answer to most questions",
  info: "what the integration does: gateways, scans, teach-ins",
  warning: "only what went wrong or looks wrong",
  error: "failures only",
};

const REFRESH_MS = 4000;

export const page = {
  id: "logs",
  title: "Logs",
  subtitle: "What the integration writes - and how much of it",
  icon: "mdi:text-box-search-outline",
  glyph: "▤",
  refreshMs: REFRESH_MS,

  styles: `
    .log-toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
                   margin-bottom: 10px; }
    .log-toolbar .grow { flex: 1 1 220px; }
    .log-level-hint { font-size: .78rem; color: var(--eltako-muted); }
    .log-lines { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .76rem;
                 background: var(--eltako-card); border: 1px solid var(--eltako-border);
                 border-radius: var(--eltako-radius); overflow: auto; max-height: 62vh; }
    .log-line { display: grid; grid-template-columns: 150px 76px 1fr; gap: 8px;
                padding: 2px 10px; border-bottom: 1px solid var(--eltako-border); }
    .log-line:last-child { border-bottom: none; }
    .log-line .log-time { color: var(--eltako-muted); font-variant-numeric: tabular-nums; }
    .log-line .log-level { text-transform: uppercase; font-weight: 600; }
    .log-line .log-message { white-space: pre-wrap; word-break: break-word; }
    .log-line .log-logger { color: var(--eltako-muted); }
    .log-line.warn .log-level { color: var(--eltako-warn); }
    .log-line.bad { background: color-mix(in srgb, var(--eltako-warn) 12%, transparent); }
    .log-line.bad .log-level { color: var(--eltako-warn); }
    .log-line.muted .log-level { color: var(--eltako-muted); }
    .log-exception { grid-column: 1 / -1; white-space: pre-wrap; color: var(--eltako-muted);
                     margin: 2px 0 4px 0; }
    /* narrow screens: the columns below each other, the message keeps the full width */
    @media (max-width: 700px) {
      .log-line { grid-template-columns: 1fr; gap: 0; }
      .log-line .log-time { font-size: .7rem; }
    }
  `,

  async load(ctx) {
    ctx.state.logs = await ctx.api.call(WS.LOGS_RECENT, {
      limit: 500,
      level: ctx.state.logLevelFilter || null,
      // the search runs in the backend so it also finds records which are not on screen
      search: ctx.state.logSearch || null,
    });
  },

  renderToolbar(ctx) {
    const logs = ctx.state.logs || {};
    const level = logs.level || "inherit";
    return `
      <div class="log-toolbar">
        <label>Log level
          <select id="log-level">
            ${(logs.options || ["inherit"]).map((option) => `
              <option value="${escapeHtml(option)}" ${option === level ? "selected" : ""}
                >${escapeHtml(option)}</option>`).join("")}
          </select>
        </label>
        <span class="log-level-hint">${escapeHtml(LEVEL_HINTS[level] || "")}
          ${logs.effective ? `&middot; effective: <b>${escapeHtml(logs.effective)}</b>` : ""}</span>
        <label>Show
          <select id="log-filter-level">
            <option value="">everything</option>
            <option value="info" ${ctx.state.logLevelFilter === "info" ? "selected" : ""}>info and worse</option>
            <option value="warning" ${ctx.state.logLevelFilter === "warning" ? "selected" : ""}>warnings and worse</option>
            <option value="error" ${ctx.state.logLevelFilter === "error" ? "selected" : ""}>errors only</option>
          </select>
        </label>
        <input class="grow" id="log-search" type="search" placeholder="filter (text or logger)"
               value="${escapeHtml(ctx.state.logSearch || "")}" />
        <button class="action small" id="log-download">download</button>
        <button class="action small" id="log-clear">clear buffer</button>
      </div>`;
  },

  render(ctx) {
    const logs = ctx.state.logs;
    if (!logs) return `<div class="empty">The log could not be read.</div>`;

    const entries = logs.entries || [];
    const counts = entries.reduce((totals, entry) => {
      totals[entry.level] = (totals[entry.level] || 0) + 1;
      return totals;
    }, {});

    const cards = `<div class="cards">
      ${card("Records shown", entries.length)}
      ${card("Warnings", counts.WARNING || 0)}
      ${card("Errors", (counts.ERROR || 0) + (counts.CRITICAL || 0))}
      ${card("Buffer", `${logs.buffer_size || 0} lines`)}
    </div>`;

    if (!entries.length) {
      return `${cards}
        <div class="empty">Nothing in the buffer${ctx.state.logSearch || ctx.state.logLevelFilter
          ? " for this filter" : ""}. The buffer starts empty after a restart of Home Assistant;
          with the level on <b>inherit</b> only warnings and errors usually arrive.</div>`;
    }

    return `
      ${cards}
      ${logs.dropped
        ? `<div class="hint">${logs.dropped} older record(s) already left the buffer -
             the Home Assistant log file has them all.</div>`
        : ""}
      <div class="log-lines" id="log-lines">
        ${entries.map((entry) => this._line(entry)).join("")}
      </div>`;
  },

  _line(entry) {
    const level = LEVELS[entry.level] || { tone: "", label: entry.level };
    // the logger name only when it is not the integration itself - 'eltako.telegrams' and
    // 'eltako' in every line would be noise, a differing one is information
    const logger = entry.logger && entry.logger !== "eltako"
      ? `<span class="log-logger">[${escapeHtml(entry.logger.replace(/^eltako\./, ""))}]</span> `
      : "";
    return `
      <div class="log-line ${level.tone}">
        <span class="log-time" title="${escapeHtml(entry.time)}">${escapeHtml(logTime(entry.time))}</span>
        <span class="log-level">${escapeHtml(level.label)}</span>
        <span class="log-message">${logger}${escapeHtml(entry.message)}</span>
        ${entry.exception ? `<pre class="log-exception">${escapeHtml(entry.exception)}</pre>` : ""}
      </div>`;
  },

  afterRender(ctx, root) {
    // The newest line is the interesting one, so the view sits at the bottom like `tail -f`.
    // But only while the user is *at* the bottom: the page reloads every few seconds, and
    // scrolling back up to read something must not be undone by the next refresh.
    const lines = root.getElementById?.("log-lines");
    if (!lines || typeof lines.scrollTop !== "number") return;
    if (this._stickToBottom !== false) lines.scrollTop = lines.scrollHeight;
    lines.addEventListener?.("scroll", () => {
      const distance = lines.scrollHeight - lines.scrollTop - lines.clientHeight;
      this._stickToBottom = distance < 40;
    });
  },

  bindToolbar(ctx, root) {
    root.getElementById("log-level")?.addEventListener("change", async (event) => {
      const level = event.target.value;
      const result = await ctx.api.call(WS.LOGS_LEVEL, { level });
      if (!result) {
        alert((ctx.api.lastError || {}).message || "The log level could not be changed.");
        ctx.api.lastError = null;
        return;
      }
      await this.load(ctx);
      ctx.requestRender();
    });

    root.getElementById("log-filter-level")?.addEventListener("change", async (event) => {
      ctx.state.logLevelFilter = event.target.value || null;
      await this.load(ctx);
      ctx.requestRender();
    });

    root.getElementById("log-search")?.addEventListener("input", (event) => {
      ctx.state.logSearch = event.target.value;
      clearTimeout(this._searchTimer);
      this._searchTimer = setTimeout(async () => {
        await this.load(ctx);
        ctx.requestContentRender();
      }, 300);
    });

    root.getElementById("log-download")?.addEventListener("click", () => {
      const entries = (ctx.state.logs || {}).entries || [];
      download(`eltako_log_${timestampForFilename()}.log`,
        entries.map((entry) => `${entry.time} ${entry.level} `
          + `[${entry.logger}] ${entry.message}`
          + (entry.exception ? `\n${entry.exception}` : "")).join("\n"),
        "text/plain");
    });

    root.getElementById("log-clear")?.addEventListener("click", async () => {
      await ctx.api.call(WS.LOGS_CLEAR);
      await this.load(ctx);
      ctx.requestRender();
    });
  },
};
