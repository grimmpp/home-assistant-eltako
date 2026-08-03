/**
 * Web UI of the Home Assistant Eltako Integration for EnOcean telegram analysis.
 *
 * It is a self-contained web component (no build step, no dependencies) which is
 * registered as a Home Assistant panel by the integration. It uses the websocket
 * api provided by `custom_components/eltako/enocean_logger.py`:
 *
 *   eltako/telegram_log/info             -> status and configuration
 *   eltako/telegram_log/statistics       -> per device statistics
 *   eltako/telegram_log/recent           -> ring buffer of the latest telegrams
 *   eltako/telegram_log/subscribe        -> live stream of telegrams
 *   eltako/telegram_log/clear            -> reset statistics and buffer
 *   eltako/telegram_log/refresh_devices  -> rebuild list of known devices
 */

const MAX_LIVE_ROWS = 500;          // rows kept in the live view
const STATISTICS_REFRESH_MS = 5000; // polling interval of the statistics view

class EltakoTelegramLogPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._view = "live";
    this._telegrams = [];
    this._statistics = { summary: {}, devices: [] };
    this._info = {};
    this._paused = false;
    this._filter = "";
    this._directionFilter = "all";
    this._onlyUnknown = false;
    this._sortColumn = "count";
    this._sortDescending = true;
    this._unsubscribe = null;
    this._statisticsTimer = null;
    this._renderScheduled = false;
    this._toolbarView = null;
    this.attachShadow({ mode: "open" });
  }

  /* ----------------------------------------------------------------- lifecycle */

  set hass(hass) {
    const isFirst = this._hass === null;
    this._hass = hass;
    if (isFirst) {
      this._renderSkeleton();
      this._connect();
    }
  }

  get hass() {
    return this._hass;
  }

  disconnectedCallback() {
    this._teardown();
  }

  _teardown() {
    if (this._unsubscribe) {
      try {
        this._unsubscribe.then((unsub) => unsub());
      } catch (err) {
        /* connection already closed */
      }
      this._unsubscribe = null;
    }
    if (this._statisticsTimer) {
      clearInterval(this._statisticsTimer);
      this._statisticsTimer = null;
    }
  }

  async _connect() {
    await this._loadInfo();
    if (this._info.enabled === false) {
      this._render();
      return;
    }
    await Promise.all([this._loadRecent(), this._loadStatistics()]);
    this._subscribe();
    this._statisticsTimer = setInterval(() => {
      this._loadInfo();
      if (this._view === "statistics" || this._view === "unknown") {
        this._loadStatistics();
      }
    }, STATISTICS_REFRESH_MS);
    this._render();
  }

  _subscribe() {
    if (this._unsubscribe) return;
    this._unsubscribe = this._hass.connection.subscribeMessage(
      (telegram) => this._onTelegram(telegram),
      { type: "eltako/telegram_log/subscribe" }
    );
  }

  /* ------------------------------------------------------------------- backend */

  async _call(type, payload = {}) {
    try {
      return await this._hass.connection.sendMessagePromise({ type, ...payload });
    } catch (err) {
      this._error = err && err.message ? err.message : String(err);
      return null;
    }
  }

  async _loadInfo() {
    const info = await this._call("eltako/telegram_log/info");
    if (info) {
      this._info = info;
      this._scheduleRender();
    }
  }

  async _loadRecent() {
    const result = await this._call("eltako/telegram_log/recent", { limit: MAX_LIVE_ROWS });
    if (result && result.telegrams) {
      this._telegrams = result.telegrams.slice().reverse(); // newest first
      this._scheduleRender();
    }
  }

  async _loadStatistics() {
    const statistics = await this._call("eltako/telegram_log/statistics");
    if (statistics) {
      this._statistics = statistics;
      this._scheduleRender();
    }
  }

  _onTelegram(telegram) {
    if (this._paused) return;
    this._telegrams.unshift(telegram);
    if (this._telegrams.length > MAX_LIVE_ROWS) {
      this._telegrams.length = MAX_LIVE_ROWS;
    }
    if (this._view === "live") {
      this._scheduleRender();
    }
  }

  /* ------------------------------------------------------------------ rendering */

  _scheduleRender() {
    if (this._renderScheduled) return;
    this._renderScheduled = true;
    requestAnimationFrame(() => {
      this._renderScheduled = false;
      this._render();
    });
  }

  _renderSkeleton() {
    this.shadowRoot.innerHTML = `
      <style>${EltakoTelegramLogPanel.styles}</style>
      <div class="page">
        <header>
          <div class="title">
            <h1>EnOcean Telegrams</h1>
            <span class="subtitle">Eltako Integration &ndash; logging &amp; analysis</span>
          </div>
          <div class="status" id="status"></div>
        </header>
        <nav id="tabs"></nav>
        <section id="toolbar"></section>
        <main id="content"><div class="empty">Loading&hellip;</div></main>
      </div>
    `;
    this.shadowRoot.getElementById("tabs").addEventListener("click", (event) => {
      const tab = event.target.closest("button[data-view]");
      if (tab) {
        this._view = tab.dataset.view;
        if (this._view === "statistics" || this._view === "unknown") this._loadStatistics();
        this._render();
      }
    });
  }

  _render() {
    if (!this.shadowRoot.getElementById("content")) return;

    this._renderStatus();
    this._renderTabs();
    this._renderToolbar();

    const content = this.shadowRoot.getElementById("content");
    if (this._info.enabled === false) {
      content.innerHTML = this._renderDisabled();
      return;
    }

    if (this._view === "live") content.innerHTML = this._renderLive();
    else if (this._view === "statistics") content.innerHTML = this._renderStatistics();
    else if (this._view === "unknown") content.innerHTML = this._renderUnknown();
    else content.innerHTML = this._renderInfo();

    this._bindContentEvents();
  }

  _renderStatus() {
    const info = this._info;
    const status = this.shadowRoot.getElementById("status");
    if (info.enabled === false) {
      status.innerHTML = `<span class="pill off">recording off</span>`;
      return;
    }
    status.innerHTML = `
      <span class="pill ${this._paused ? "warn" : "on"}">${this._paused ? "live paused" : "recording"}</span>
      <span class="pill neutral">${this._formatNumber(info.total_count)} telegrams</span>
      <span class="pill neutral">${this._formatNumber(info.telegrams_per_minute)} / min</span>
      ${info.file_logging_enabled
        ? `<span class="pill neutral" title="${this._escape(info.file_path)}">file: ${this._escape(this._basename(info.file_path))}</span>`
        : `<span class="pill warn" title="Set 'telegram_log_filename' to persist telegrams">memory only</span>`}
    `;
  }

  _renderTabs() {
    const tabs = [
      ["live", "Live telegrams"],
      ["statistics", "Device statistics"],
      ["unknown", `Unknown devices${this._unknownDevices().length ? ` (${this._unknownDevices().length})` : ""}`],
      ["info", "Info"],
    ];
    this.shadowRoot.getElementById("tabs").innerHTML = tabs
      .map(([view, label]) =>
        `<button data-view="${view}" class="${this._view === view ? "active" : ""}">${label}</button>`)
      .join("");
  }

  /**
   * The toolbar contains the filter input, so it must only be rebuilt when the view
   * changes - otherwise the periodic refresh would steal the focus while typing.
   */
  _renderToolbar(force = false) {
    const toolbar = this.shadowRoot.getElementById("toolbar");
    if (this._info.enabled === false) {
      toolbar.innerHTML = "";
      this._toolbarView = null;
      return;
    }
    if (!force && this._toolbarView === this._view) return;
    this._toolbarView = this._view;

    const showFilter = this._view === "live" || this._view === "statistics";
    toolbar.innerHTML = `
      ${showFilter ? `
        <input id="filter" type="search" placeholder="Filter address, device, EEP, entity, data&hellip;"
               value="${this._escape(this._filter)}" />` : ""}
      ${this._view === "live" ? `
        <select id="direction">
          <option value="all" ${this._directionFilter === "all" ? "selected" : ""}>all directions</option>
          <option value="incoming" ${this._directionFilter === "incoming" ? "selected" : ""}>incoming</option>
          <option value="outgoing" ${this._directionFilter === "outgoing" ? "selected" : ""}>outgoing</option>
        </select>
        <label class="check"><input id="onlyUnknown" type="checkbox" ${this._onlyUnknown ? "checked" : ""}/> only unknown</label>
        <button id="pause" class="action">${this._paused ? "Resume" : "Pause"}</button>` : ""}
      <span class="spacer"></span>
      <button id="export-json" class="action">Export JSON</button>
      <button id="export-csv" class="action">Export CSV</button>
      <button id="refresh" class="action">Refresh devices</button>
      <button id="clear" class="action danger">Clear</button>
    `;

    const filter = this.shadowRoot.getElementById("filter");
    if (filter) {
      filter.addEventListener("input", (event) => {
        this._filter = event.target.value;
        this._renderContentOnly();
      });
    }
    const direction = this.shadowRoot.getElementById("direction");
    if (direction) {
      direction.addEventListener("change", (event) => {
        this._directionFilter = event.target.value;
        this._renderContentOnly();
      });
    }
    const onlyUnknown = this.shadowRoot.getElementById("onlyUnknown");
    if (onlyUnknown) {
      onlyUnknown.addEventListener("change", (event) => {
        this._onlyUnknown = event.target.checked;
        this._renderContentOnly();
      });
    }
    const pause = this.shadowRoot.getElementById("pause");
    if (pause) {
      pause.addEventListener("click", () => {
        this._paused = !this._paused;
        this._renderStatus();
        this._renderToolbar(true);
      });
    }
    this.shadowRoot.getElementById("export-json").addEventListener("click", () => this._exportJson());
    this.shadowRoot.getElementById("export-csv").addEventListener("click", () => this._exportCsv());
    this.shadowRoot.getElementById("refresh").addEventListener("click", async () => {
      await this._call("eltako/telegram_log/refresh_devices");
      await this._loadStatistics();
      await this._loadInfo();
    });
    this.shadowRoot.getElementById("clear").addEventListener("click", async () => {
      await this._call("eltako/telegram_log/clear");
      this._telegrams = [];
      await Promise.all([this._loadStatistics(), this._loadInfo()]);
      this._render();
    });
  }

  _renderContentOnly() {
    const content = this.shadowRoot.getElementById("content");
    if (this._view === "live") content.innerHTML = this._renderLive();
    else if (this._view === "statistics") content.innerHTML = this._renderStatistics();
    else if (this._view === "unknown") content.innerHTML = this._renderUnknown();
    this._bindContentEvents();
  }

  _bindContentEvents() {
    this.shadowRoot.querySelectorAll("th[data-sort]").forEach((header) => {
      header.addEventListener("click", () => {
        const column = header.dataset.sort;
        if (this._sortColumn === column) this._sortDescending = !this._sortDescending;
        else {
          this._sortColumn = column;
          this._sortDescending = true;
        }
        this._renderContentOnly();
      });
    });
    this.shadowRoot.querySelectorAll("button[data-yaml]").forEach((button) => {
      button.addEventListener("click", () => {
        navigator.clipboard.writeText(decodeURIComponent(button.dataset.yaml));
        button.textContent = "copied";
        setTimeout(() => (button.textContent = "copy yaml"), 1500);
      });
    });
    this.shadowRoot.querySelectorAll("tr[data-detail]").forEach((row) => {
      row.addEventListener("click", () => {
        const detail = this.shadowRoot.getElementById(row.dataset.detail);
        if (detail) detail.classList.toggle("visible");
      });
    });
  }

  /* ---------------------------------------------------------------- live view */

  _filteredTelegrams() {
    const needle = this._filter.trim().toLowerCase();
    return this._telegrams.filter((telegram) => {
      if (this._directionFilter !== "all" && telegram.direction !== this._directionFilter) return false;
      if (this._onlyUnknown && telegram.known) return false;
      if (!needle) return true;
      return [
        telegram.address, telegram.local_address, telegram.device_name, telegram.eep,
        telegram.msg_type, telegram.data, telegram.gateway_name, (telegram.entity_ids || []).join(" "),
      ].some((value) => value && String(value).toLowerCase().includes(needle));
    });
  }

  _renderLive() {
    const telegrams = this._filteredTelegrams();
    if (!telegrams.length) {
      return `<div class="empty">No telegrams recorded yet. As soon as a device sends a telegram it shows up here.</div>`;
    }

    const rows = telegrams.map((telegram, index) => {
      const detailId = `detail-${telegram.seq}-${index}`;
      return `
        <tr data-detail="${detailId}" class="${telegram.known ? "" : "unknown-row"}">
          <td class="mono">${this._formatTime(telegram.timestamp)}</td>
          <td class="dir ${telegram.direction}">${telegram.direction === "outgoing" ? "&#8593; out" : "&#8595; in"}</td>
          <td>${this._escape(telegram.gateway_name || telegram.gateway_id)}</td>
          <td class="mono">${this._escape(telegram.address || telegram.local_address || "-")}
            ${telegram.local_address && telegram.address !== telegram.local_address
              ? `<span class="hint">bus ${this._escape(telegram.local_address)}</span>` : ""}</td>
          <td>${telegram.known
              ? `${this._escape(telegram.device_name || "")}${(telegram.entity_ids || []).length
                  ? `<span class="hint">${this._escape(telegram.entity_ids.join(", "))}</span>` : ""}`
              : `<span class="tag unknown">unknown</span>`}</td>
          <td class="mono">${this._escape(telegram.eep || telegram.teach_in_profile || "-")}</td>
          <td>${this._escape(telegram.msg_type)}</td>
          <td class="mono">${this._escape(telegram.data || telegram.payload || "-")}</td>
          <td class="decoded">${this._formatDecoded(telegram.decoded)}</td>
        </tr>
        <tr class="detail" id="${detailId}"><td colspan="9"><pre>${this._escape(JSON.stringify(telegram, null, 2))}</pre></td></tr>
      `;
    }).join("");

    return `
      <div class="table-wrapper">
        <table class="live">
          <thead><tr>
            <th>Time</th><th>Dir</th><th>Gateway</th><th>Address</th><th>Device / Entity</th>
            <th>EEP</th><th>Message type</th><th>Data</th><th>Decoded</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="footnote">Showing ${telegrams.length} of ${this._telegrams.length} buffered telegrams (newest first). Click a row for the raw record.</div>
    `;
  }

  /* ---------------------------------------------------------- statistics view */

  _sortedDevices(devices) {
    const column = this._sortColumn;
    const factor = this._sortDescending ? -1 : 1;
    return devices.slice().sort((a, b) => {
      const left = a[column];
      const right = b[column];
      if (left === right) return 0;
      if (left === null || left === undefined) return 1;
      if (right === null || right === undefined) return -1;
      if (typeof left === "number" && typeof right === "number") return (left - right) * factor;
      return String(left).localeCompare(String(right)) * factor;
    });
  }

  _filteredDevices() {
    const needle = this._filter.trim().toLowerCase();
    const devices = this._statistics.devices || [];
    if (!needle) return devices;
    return devices.filter((device) => [
      device.address, device.local_address, device.name, device.eep, device.area,
      (device.entity_ids || []).join(" "), (device.platforms || []).join(" "),
    ].some((value) => value && String(value).toLowerCase().includes(needle)));
  }

  _renderStatistics() {
    const summary = this._statistics.summary || {};
    const devices = this._sortedDevices(this._filteredDevices());

    const cards = `
      <div class="cards">
        ${this._card("Telegrams", this._formatNumber(summary.total_count))}
        ${this._card("Telegrams / min", this._formatNumber(summary.telegrams_per_minute))}
        ${this._card("Devices seen", this._formatNumber(summary.device_count))}
        ${this._card("Known", this._formatNumber(summary.known_device_count))}
        ${this._card("Unknown", this._formatNumber(summary.unknown_device_count), summary.unknown_device_count ? "warn" : "")}
        ${this._card("Written to file", this._formatNumber(summary.file_written_count))}
        ${this._card("Filtered (polling)", this._formatNumber(summary.filtered_count))}
        ${this._card("Recording since", this._formatTime(summary.started_at))}
      </div>
      ${Object.keys(summary.count_by_msg_type || {}).length ? `
        <div class="chips">
          ${Object.entries(summary.count_by_msg_type).sort((a, b) => b[1] - a[1])
            .map(([type, count]) => `<span class="chip">${this._escape(type)} <b>${this._formatNumber(count)}</b></span>`).join("")}
        </div>` : ""}
    `;

    if (!devices.length) {
      return `${cards}<div class="empty">No devices recorded yet.</div>`;
    }

    const rows = devices.map((device) => `
      <tr class="${device.known ? "" : "unknown-row"}">
        <td class="mono">${this._escape(device.address)}
          ${device.local_address && device.local_address !== device.address
            ? `<span class="hint">bus ${this._escape(device.local_address)}</span>` : ""}</td>
        <td>${device.known
            ? this._escape(device.name || "")
            : `<span class="tag unknown">unknown</span>`}
          ${(device.entity_ids || []).length ? `<span class="hint">${this._escape(device.entity_ids.join(", "))}</span>` : ""}</td>
        <td class="mono">${this._escape(device.eep || device.teach_in_profile || "-")}</td>
        <td>${this._escape((device.platforms || []).join(", ") || "-")}</td>
        <td>${this._escape(device.area || "-")}</td>
        <td>${this._escape((device.gateway_ids || []).join(", "))}</td>
        <td class="num">${this._formatNumber(device.count)}</td>
        <td class="num">${this._formatNumber(device.count_incoming)} / ${this._formatNumber(device.count_outgoing)}</td>
        <td class="num">${this._formatInterval(device.avg_interval)}</td>
        <td class="num">${this._formatInterval(device.min_interval)} / ${this._formatInterval(device.max_interval)}</td>
        <td class="mono">${this._formatTime(device.last_seen)}</td>
        <td class="decoded">${this._formatDecoded(device.last_decoded)}</td>
      </tr>
    `).join("");

    return `
      ${cards}
      <div class="table-wrapper">
        <table>
          <thead><tr>
            <th data-sort="address">Address</th>
            <th data-sort="name">Device / Entity</th>
            <th data-sort="eep">EEP</th>
            <th>Platform</th>
            <th data-sort="area">Area</th>
            <th>GW</th>
            <th data-sort="count" class="num">Count</th>
            <th class="num">in / out</th>
            <th data-sort="avg_interval" class="num">&#8709; interval</th>
            <th class="num">min / max</th>
            <th data-sort="last_seen">Last seen</th>
            <th>Last values</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="footnote">Click a column header to sort. Intervals in seconds.</div>
    `;
  }

  /* ------------------------------------------------------------ unknown view */

  _unknownDevices() {
    return (this._statistics.devices || []).filter((device) => !device.known && device.address);
  }

  _renderUnknown() {
    const devices = this._unknownDevices();
    if (!devices.length) {
      return `<div class="empty">All recorded telegrams belong to configured devices. &#127881;</div>`;
    }

    const rows = devices.map((device) => {
      const eep = device.teach_in_profile || this._guessEep(device);
      const yaml = `      - id: ${device.address}\n        eep: ${eep || "<EEP>"}\n        name: "New device ${device.address}"\n`;
      return `
        <tr>
          <td class="mono">${this._escape(device.address)}</td>
          <td class="num">${this._formatNumber(device.count)}</td>
          <td>${this._escape(Object.keys(device.msg_types || {}).join(", "))}</td>
          <td class="mono">${this._escape(device.last_data || "-")}</td>
          <td class="mono">${this._escape(eep || "?")}${device.teach_in_profile ? `<span class="hint">from teach-in</span>` : ""}</td>
          <td class="mono">${this._formatTime(device.last_seen)}</td>
          <td><button class="action small" data-yaml="${encodeURIComponent(yaml)}">copy yaml</button></td>
        </tr>
      `;
    }).join("");

    return `
      <div class="notice">
        These addresses sent telegrams but are not part of your <code>configuration.yaml</code>.
        Use the yaml snippet as a starting point to add them below the <code>devices:</code> section of your gateway.
        The EEP is a guess based on the message type (or taken from a 4BS teach-in telegram) and should be verified.
      </div>
      <div class="table-wrapper">
        <table>
          <thead><tr>
            <th>Address</th><th class="num">Count</th><th>Message types</th><th>Last data</th>
            <th>EEP guess</th><th>Last seen</th><th></th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  _guessEep(device) {
    const types = Object.keys(device.msg_types || {});
    if (types.some((type) => type.includes("RPS"))) return "F6-02-01";
    if (types.some((type) => type.includes("1BS"))) return "D5-00-01";
    if (types.some((type) => type.includes("4BS"))) return "A5-04-02";
    return null;
  }

  /* --------------------------------------------------------------- info view */

  _renderInfo() {
    const info = this._info;
    const rows = [
      ["Recording enabled", info.enabled === false ? "no" : "yes"],
      ["Recording since", this._formatDateTime(info.started_at)],
      ["Telegrams recorded", this._formatNumber(info.total_count)],
      ["Telegrams per minute", this._formatNumber(info.telegrams_per_minute)],
      ["Filtered polling telegrams", this._formatNumber(info.filtered_count)],
      ["Recording errors", this._formatNumber(info.error_count)],
      ["EEP decoding errors", this._formatNumber(info.decode_error_count)],
      ["Known addresses", this._formatNumber(info.known_address_count)],
      ["Live buffer size", this._formatNumber(info.buffer_size)],
      ["Buffered telegrams", this._formatNumber(info.buffered_count)],
      ["Log file", info.file_path || "&ndash; not configured &ndash;"],
      ["Log file format", info.file_format || "-"],
      ["Telegrams written to file", this._formatNumber(info.file_written_count)],
      ["Dropped (writer overloaded)", this._formatNumber(info.file_dropped_count)],
      ["Log file error", info.file_error || "none"],
      ["Include bus polling", info.include_polling ? "yes" : "no"],
      ["Decode known EEPs", info.decode_eep ? "yes" : "no"],
    ];

    return `
      <div class="table-wrapper">
        <table class="info">
          <tbody>${rows.map(([label, value]) =>
            `<tr><th>${label}</th><td class="mono">${value === null || value === undefined ? "-" : value}</td></tr>`).join("")}
          </tbody>
        </table>
      </div>
      <div class="notice">
        <b>Configuration</b> (<code>configuration.yaml</code>):
        <pre>eltako:
  general_settings:
    log_enocean_telegrams: True                     # record all telegrams
    telegram_log_filename: enocean_telegrams.jsonl  # optional: persist telegrams (relative to /config)
    telegram_log_format: jsonl                      # jsonl or csv
    telegram_log_max_file_size_mb: 10               # rotates the file when the size is exceeded
    telegram_log_backup_count: 3                    # number of rotated files to keep
    telegram_log_include_polling: False             # log bus polling telegrams as well
    telegram_log_decode_eep: True                   # decode telegrams of known devices
    telegram_log_buffer_size: 500                   # telegrams kept in memory for this live view
    enable_telegram_web_ui: True                    # this panel</pre>
      </div>
    `;
  }

  _renderDisabled() {
    return `
      <div class="notice">
        <h2>Telegram recording is disabled</h2>
        <p>${this._escape(this._info.hint || "Enable it in your configuration.yaml.")}</p>
        <pre>eltako:
  general_settings:
    log_enocean_telegrams: True
    telegram_log_filename: enocean_telegrams.jsonl</pre>
        <p>Restart Home Assistant afterwards.</p>
      </div>
    `;
  }

  /* ----------------------------------------------------------------- exports */

  _exportJson() {
    const payload = {
      exported_at: new Date().toISOString(),
      info: this._info,
      statistics: this._statistics,
      telegrams: this._telegrams,
    };
    this._download(`eltako_telegrams_${this._timestampForFilename()}.json`,
      JSON.stringify(payload, null, 2), "application/json");
  }

  _exportCsv() {
    const isLive = this._view === "live";
    const rows = isLive ? this._filteredTelegrams() : this._sortedDevices(this._filteredDevices());
    const columns = isLive
      ? ["seq", "timestamp", "direction", "gateway_id", "gateway_name", "msg_type", "address", "local_address",
         "known", "eep", "device_name", "entity_ids", "area", "status", "data", "raw", "decoded"]
      : ["address", "local_address", "known", "name", "eep", "platforms", "area", "entity_ids", "gateway_ids",
         "count", "count_incoming", "count_outgoing", "first_seen", "last_seen",
         "min_interval", "avg_interval", "max_interval", "msg_types", "last_data", "last_decoded"];

    const escapeCsv = (value) => {
      if (value === null || value === undefined) return "";
      const text = typeof value === "object" ? JSON.stringify(value) : String(value);
      return /[";\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };

    const csv = [columns.join(";")]
      .concat(rows.map((row) => columns.map((column) => escapeCsv(row[column])).join(";")))
      .join("\n");

    this._download(`eltako_${isLive ? "telegrams" : "statistics"}_${this._timestampForFilename()}.csv`,
      csv, "text/csv");
  }

  _download(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }

  _timestampForFilename() {
    return new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  }

  /* ----------------------------------------------------------------- helpers */

  _card(label, value, modifier = "") {
    return `<div class="card ${modifier}"><span class="card-value">${value}</span><span class="card-label">${label}</span></div>`;
  }

  _escape(value) {
    if (value === null || value === undefined) return "";
    return String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[char]);
  }

  _formatNumber(value) {
    if (value === null || value === undefined) return "-";
    return Number(value).toLocaleString();
  }

  _formatInterval(value) {
    if (value === null || value === undefined) return "-";
    if (value >= 60) return `${(value / 60).toFixed(1)} min`;
    return `${Number(value).toFixed(value < 1 ? 2 : 1)} s`;
  }

  _formatTime(isoString) {
    if (!isoString) return "-";
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return this._escape(isoString);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) +
      `.${String(date.getMilliseconds()).padStart(3, "0")}`;
  }

  _formatDateTime(isoString) {
    if (!isoString) return "-";
    const date = new Date(isoString);
    return isNaN(date.getTime()) ? this._escape(isoString) : date.toLocaleString();
  }

  _formatDecoded(decoded) {
    if (!decoded || typeof decoded !== "object") return "";
    const interesting = Object.entries(decoded)
      .filter(([key, value]) => value !== null && value !== undefined && value !== false && key !== "eep_string")
      .slice(0, 6);
    return interesting
      .map(([key, value]) => `<span class="kv"><i>${this._escape(key)}</i>${this._escape(
        typeof value === "object" ? JSON.stringify(value) : value)}</span>`)
      .join(" ");
  }

  _basename(path) {
    if (!path) return "-";
    const parts = String(path).split(/[\\/]/);
    return parts[parts.length - 1];
  }

  static get styles() {
    return `
      :host {
        display: block;
        --eltako-border: var(--divider-color, rgba(127,127,127,.3));
        color: var(--primary-text-color, #212121);
        background: var(--primary-background-color, #fafafa);
        font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif);
        height: 100%;
        overflow: auto;
      }
      .page { padding: 16px; box-sizing: border-box; }
      header { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; }
      h1 { font-size: 1.4rem; margin: 0; font-weight: 500; }
      .subtitle { font-size: .8rem; color: var(--secondary-text-color, #727272); }
      .status { display: flex; flex-wrap: wrap; gap: 6px; }
      .pill { font-size: .75rem; padding: 3px 10px; border-radius: 12px; white-space: nowrap;
              background: var(--card-background-color, #fff); border: 1px solid var(--eltako-border); }
      .pill.on { background: var(--label-badge-green, #43a047); color: #fff; border-color: transparent; }
      .pill.off { background: var(--label-badge-red, #e53935); color: #fff; border-color: transparent; }
      .pill.warn { background: var(--label-badge-yellow, #f9a825); color: #212121; border-color: transparent; }
      nav { display: flex; gap: 4px; margin: 16px 0 12px; flex-wrap: wrap;
            border-bottom: 1px solid var(--eltako-border); }
      nav button { background: none; border: none; border-bottom: 2px solid transparent; cursor: pointer;
                   padding: 8px 14px; font: inherit; font-size: .9rem; color: var(--secondary-text-color, #727272); }
      nav button:hover { color: var(--primary-text-color); }
      nav button.active { color: var(--primary-color, #03a9f4); border-bottom-color: var(--primary-color, #03a9f4); }
      #toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
      #toolbar .spacer { flex: 1 1 auto; }
      input[type=search], select {
        font: inherit; font-size: .85rem; padding: 6px 10px; border-radius: 6px; min-width: 200px;
        border: 1px solid var(--eltako-border); background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
      }
      .check { font-size: .85rem; display: inline-flex; gap: 4px; align-items: center; }
      button.action {
        font: inherit; font-size: .85rem; padding: 6px 12px; border-radius: 6px; cursor: pointer;
        border: 1px solid var(--eltako-border); background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
      }
      button.action:hover { border-color: var(--primary-color, #03a9f4); color: var(--primary-color, #03a9f4); }
      button.action.small { padding: 2px 8px; font-size: .75rem; }
      button.action.danger:hover { border-color: var(--error-color, #e53935); color: var(--error-color, #e53935); }
      .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 14px; }
      .card { background: var(--card-background-color, #fff); border: 1px solid var(--eltako-border);
              border-radius: 10px; padding: 12px; display: flex; flex-direction: column; gap: 4px; }
      .card.warn { border-color: var(--label-badge-yellow, #f9a825); }
      .card-value { font-size: 1.3rem; font-weight: 500; }
      .card-label { font-size: .75rem; color: var(--secondary-text-color, #727272); }
      .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
      .chip { font-size: .75rem; padding: 3px 10px; border-radius: 12px; background: var(--card-background-color, #fff);
              border: 1px solid var(--eltako-border); }
      .table-wrapper { overflow-x: auto; background: var(--card-background-color, #fff);
                       border: 1px solid var(--eltako-border); border-radius: 10px; }
      table { border-collapse: collapse; width: 100%; font-size: .82rem; }
      th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--eltako-border); vertical-align: top; }
      thead th { position: sticky; top: 0; background: var(--card-background-color, #fff); z-index: 1;
                 font-weight: 500; color: var(--secondary-text-color, #727272); white-space: nowrap; }
      th[data-sort] { cursor: pointer; }
      th[data-sort]:hover { color: var(--primary-color, #03a9f4); }
      tbody tr:hover { background: var(--secondary-background-color, rgba(127,127,127,.08)); }
      table.live tbody tr { cursor: pointer; }
      td.num, th.num { text-align: right; white-space: nowrap; }
      .mono { font-family: "Roboto Mono", "SFMono-Regular", Consolas, monospace; white-space: nowrap; }
      .hint { display: block; font-size: .7rem; color: var(--secondary-text-color, #727272); white-space: normal; }
      .dir { white-space: nowrap; font-size: .75rem; }
      .dir.incoming { color: var(--label-badge-green, #43a047); }
      .dir.outgoing { color: var(--primary-color, #03a9f4); }
      .unknown-row { background: color-mix(in srgb, var(--label-badge-yellow, #f9a825) 12%, transparent); }
      .tag.unknown { font-size: .7rem; padding: 1px 7px; border-radius: 10px;
                     background: var(--label-badge-yellow, #f9a825); color: #212121; }
      .decoded { max-width: 320px; white-space: normal; }
      .kv { display: inline-block; margin-right: 6px; font-size: .75rem; }
      .kv i { color: var(--secondary-text-color, #727272); font-style: normal; margin-right: 3px; }
      tr.detail { display: none; }
      tr.detail.visible { display: table-row; }
      tr.detail pre { margin: 0; font-size: .72rem; overflow-x: auto; }
      .empty, .notice { background: var(--card-background-color, #fff); border: 1px solid var(--eltako-border);
                        border-radius: 10px; padding: 16px; font-size: .88rem; }
      .notice { margin-bottom: 12px; }
      .notice h2 { margin-top: 0; font-size: 1.1rem; font-weight: 500; }
      .notice pre, .info pre { background: var(--secondary-background-color, rgba(127,127,127,.1));
                               padding: 10px; border-radius: 6px; overflow-x: auto; font-size: .78rem; }
      code { background: var(--secondary-background-color, rgba(127,127,127,.1)); padding: 1px 4px; border-radius: 4px; }
      table.info th { width: 260px; }
      .footnote { font-size: .75rem; color: var(--secondary-text-color, #727272); margin-top: 8px; }
    `;
  }
}

if (!customElements.get("eltako-telegram-log-panel")) {
  customElements.define("eltako-telegram-log-panel", EltakoTelegramLogPanel);
}
