/**
 * Web UI of the Home Assistant Eltako integration.
 *
 * This is the entry point of the panel. It provides the shell (navigation, routing,
 * shared data and the live telegram subscription) and loads the sub pages from './pages'.
 *
 * Everything is plain javascript (ES modules), no build step and no dependencies.
 * The backend is implemented in custom_components/eltako/websocket.py and
 * custom_components/eltako/enocean_logger.py.
 */

import { EltakoApi, WS } from "./lib/api.js";
import { STYLES } from "./lib/styles.js";
import { escapeHtml, icon } from "./lib/utils.js";

import { page as overviewPage } from "./pages/overview.js";
import { page as controlPage } from "./pages/control.js";
import { page as devicesConfigPage } from "./pages/devices_config.js";
import { page as telegramsPage } from "./pages/telegrams.js";
import { page as statisticsPage } from "./pages/devices.js";
import { page as testsPage } from "./pages/tests.js";
import { page as aboutPage } from "./pages/about.js";

// pages marked standaloneOnly need the eltako_standalone runtime (its shell sets
// window.eltakoStandalone) - inside Home Assistant they are hidden. Pages with a
// visible(ctx) hook can additionally hide themselves (e.g. by a general setting).
// 'unknown devices' has no page of its own anymore - the addresses which are not configured
// yet are the last block of the device page, next to everything else which exists on the bus.
const PAGES = [overviewPage, controlPage, devicesConfigPage, telegramsPage, statisticsPage,
               testsPage, aboutPage]
  .filter((page) => !page.standaloneOnly || window.eltakoStandalone);
const DEFAULT_PAGE = overviewPage.id;
const MAX_LIVE_TELEGRAMS = 500;

class EltakoPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._api = null;
    this._connected = false;
    this._narrow = false;
    this._menuButton = null;
    this._pageId = this._pageIdFromLocation();
    this._unsubscribeTelegrams = null;
    this._refreshTimer = null;
    this._renderScheduled = false;
    this._contentRenderScheduled = false;
    this._renderedToolbarFor = null;

    /** data shared between all pages */
    this.state = {
      integrationInfo: null,
      logInfo: null,
      statistics: null,
      telegrams: [],
      // view state of the pages
      paused: false,
      telegramFilter: "",
      directionFilter: "all",
      gatewayFilter: "all",
      onlyUnknown: false,
      deviceFilter: "",
      onlyUnknownDevices: false,
      // device configuration page
      deviceForm: null,
      configuredDevices: [],
      configFilter: "",
      configSort: "address",
      deviceView: "hierarchy",
      configSortDescending: false,
      onlySilent: false,
      // settings on the about page
      settingsForm: null,
      settingsError: null,
      settingsMessage: null,
      // usb/serial port scan
      portScan: null,
      busMembers: null,
      gatewayForm: null,
      gatewayEditor: null,
      gatewayError: null,
      gatewayMessage: null,
      portScanRunning: false,
      editor: null,
      pendingNewDevice: null,
      pendingNewGateway: null,
      deviceSort: "count",
      deviceSortDescending: true,
    };

    this.attachShadow({ mode: "open" });
    this._onHashChange = () => {
      const pageId = this._pageIdFromLocation();
      if (pageId !== this._pageId) this._navigate(pageId);
    };
  }

  /* ------------------------------------------------------------- lifecycle */

  set hass(hass) {
    const isFirst = this._hass === null;
    this._hass = hass;
    if (this._menuButton) this._menuButton.hass = hass;
    if (isFirst) {
      this._api = new EltakoApi(hass);
      this._renderShell();
      this._start();
    }
  }

  get hass() {
    return this._hass;
  }

  /** home assistant sets `narrow` on panel elements - the menu button needs it to decide
   *  whether the sidebar is hidden (smartphone) and the hamburger has to be shown. */
  set narrow(narrow) {
    this._narrow = narrow;
    if (this._menuButton) this._menuButton.narrow = narrow;
  }

  get narrow() {
    return this._narrow;
  }

  connectedCallback() {
    window.addEventListener("hashchange", this._onHashChange);
  }

  disconnectedCallback() {
    window.removeEventListener("hashchange", this._onHashChange);
    this._stopRefreshTimer();
    if (this._unsubscribeTelegrams) {
      this._unsubscribeTelegrams.then((unsubscribe) => unsubscribe()).catch(() => {});
      this._unsubscribeTelegrams = null;
    }
  }

  async _start() {
    // integration info is needed by the navigation (pages can hide themselves
    // depending on the general settings, see page.visible)
    await Promise.all([this.loadLogInfo(), this.loadIntegrationInfo()]);
    this._subscribeTelegrams();
    await this._enterPage();
  }

  /* ---------------------------------------------------------------- routing */

  _pageIdFromLocation() {
    const hash = (window.location.hash || "").replace(/^#\/?/, "").split("?")[0];
    return PAGES.some((page) => page.id === hash) ? hash : DEFAULT_PAGE;
  }

  get _page() {
    return PAGES.find((page) => page.id === this._pageId) || PAGES[0];
  }

  _navigate(pageId) {
    if (this._pageId === pageId) return;
    this._pageId = pageId;
    if (this._pageIdFromLocation() !== pageId) {
      window.location.hash = `#/${pageId}`;   // keeps the page bookmarkable/reloadable
    }
    this._enterPage();
  }

  async _enterPage() {
    this._stopRefreshTimer();
    this._renderedToolbarFor = null;
    this._render();

    const page = this._page;
    if (page.load) await page.load(this._context());
    this._render();

    if (page.refreshMs) {
      this._refreshTimer = setInterval(async () => {
        // While a form is open the periodic refresh must not re-render the content -
        // it would wipe everything the user has typed (e.g. the name of a new gateway).
        if (this.state.editor || this.state.gatewayEditor || this.state.sendForm) return;
        if (page.load) await page.load(this._context());
        this._render();
      }, page.refreshMs);
    }
  }

  _stopRefreshTimer() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  /* ------------------------------------------------------------------- data */

  async loadIntegrationInfo() {
    const info = await this._api.call(WS.INTEGRATION_INFO);
    if (info) this.state.integrationInfo = info;
    return this.state.integrationInfo;
  }

  async loadLogInfo() {
    const info = await this._api.call(WS.LOG_INFO);
    if (info) this.state.logInfo = info;
    return this.state.logInfo;
  }

  async loadStatistics() {
    const statistics = await this._api.call(WS.LOG_STATISTICS);
    if (statistics) this.state.statistics = statistics;
    return this.state.statistics;
  }

  async loadRecentTelegrams() {
    const result = await this._api.call(WS.LOG_RECENT, { limit: MAX_LIVE_TELEGRAMS });
    if (result && result.telegrams) {
      this.state.telegrams = result.telegrams.slice().reverse();    // newest first
    }
    return this.state.telegrams;
  }

  _subscribeTelegrams() {
    if (this._unsubscribeTelegrams) return;
    if (this.state.logInfo && this.state.logInfo.enabled === false) return;

    this._unsubscribeTelegrams = this._api.subscribeTelegrams((telegram) => this._onTelegram(telegram));
    this._unsubscribeTelegrams.catch(() => {
      this._unsubscribeTelegrams = null;    // recording disabled or connection lost
    });
  }

  _onTelegram(telegram) {
    if (this.state.paused) return;

    this.state.telegrams.unshift(telegram);
    if (this.state.telegrams.length > MAX_LIVE_TELEGRAMS) {
      this.state.telegrams.length = MAX_LIVE_TELEGRAMS;
    }
    if (this.state.logInfo) {
      this.state.logInfo.total_count = (this.state.logInfo.total_count || 0) + 1;
    }

    const page = this._page;
    if (page.onTelegram) page.onTelegram(this._context(), telegram);
  }

  /* --------------------------------------------------- context for the pages */

  _context() {
    return {
      hass: this._hass,
      api: this._api,
      state: this.state,
      root: this.shadowRoot,
      loadIntegrationInfo: () => this.loadIntegrationInfo(),
      loadLogInfo: () => this.loadLogInfo(),
      loadStatistics: () => this.loadStatistics(),
      loadRecentTelegrams: () => this.loadRecentTelegrams(),
      navigate: (pageId) => this._navigate(pageId),
      requestRender: () => this._scheduleRender(),
      requestContentRender: (immediately = false) => this._scheduleContentRender(immediately),
      renderRecordingDisabled: () => this._renderRecordingDisabled(),
    };
  }

  /* -------------------------------------------------------------- rendering */

  _scheduleRender() {
    if (this._renderScheduled) return;
    this._renderScheduled = true;
    requestAnimationFrame(() => {
      this._renderScheduled = false;
      this._render();
    });
  }

  /**
   * Re-renders the content area only. The toolbar keeps its dom, so the focus and the
   * caret of the filter input are not lost while typing.
   */
  _scheduleContentRender(immediately) {
    if (immediately) {
      this._renderContent();
      return;
    }
    if (this._contentRenderScheduled) return;
    this._contentRenderScheduled = true;
    requestAnimationFrame(() => {
      this._contentRenderScheduled = false;
      this._renderContent();
    });
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>${STYLES}${PAGES.map((page) => page.styles || "").join("")}</style>
      <div class="shell">
        <header class="app-head">
          <span id="menu-button-slot"></span>
          ${icon("mdi:access-point-network", "◉")}
          <span class="brand-title">Eltako</span>
          <span class="brand-version" id="app-version">EnOcean</span>
        </header>
        <nav id="nav"></nav>
        <main>
          <header class="page-head">
            <div>
              <h1 id="page-title"></h1>
              <div class="page-subtitle" id="page-subtitle"></div>
            </div>
            <div class="head-status" id="page-status"></div>
          </header>
          <section class="toolbar" id="toolbar"></section>
          <section id="content"><div class="empty">Loading&hellip;</div></section>
        </main>
        <div id="drawer-outlet"></div>
      </div>`;

    this.shadowRoot.getElementById("nav").addEventListener("click", (event) => {
      const link = event.target.closest("a[data-page]");
      if (!link) return;
      event.preventDefault();
      this._navigate(link.dataset.page);
    });

    this._attachMenuButton();
  }

  /**
   * The standard home assistant menu button at the very left of the header. It shows the
   * hamburger when the sidebar is hidden (smartphone) - without it there is no way to
   * navigate back out of the panel on a phone. Falls back to a plain button firing the
   * 'hass-toggle-menu' event if the ha-menu-button element is not available.
   */
  _attachMenuButton() {
    const slot = this.shadowRoot.getElementById("menu-button-slot");
    if (!slot) return;

    if (customElements.get("ha-menu-button")) {
      this._menuButton = document.createElement("ha-menu-button");
      this._menuButton.hass = this._hass;
      this._menuButton.narrow = this._narrow;
    } else {
      this._menuButton = document.createElement("button");
      this._menuButton.className = "menu-fallback";
      this._menuButton.setAttribute("aria-label", "Open menu");
      this._menuButton.textContent = "☰";
      this._menuButton.addEventListener("click", () => {
        this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
      });
    }
    slot.replaceChildren(this._menuButton);
  }

  _render() {
    if (!this.shadowRoot.getElementById("content")) return;
    this._renderNav();
    this._renderHead();
    this._renderToolbar();
    this._renderContent();
  }

  _renderNav() {
    const info = this.state.integrationInfo || {};
    const context = this._context();
    const version = this.shadowRoot.getElementById("app-version");
    if (version) version.textContent = info.version ? `v${info.version}` : "EnOcean";
    const nav = this.shadowRoot.getElementById("nav");
    // on a narrow screen the navigation scrolls horizontally - a refresh must not jump it
    // back to the first entry
    const navScroll = nav ? nav.scrollLeft : 0;
    nav.innerHTML = `
      ${PAGES.filter((page) => !page.visible || page.visible(context)).map((page) => {
        const badge = page.badge ? page.badge(context) : null;
        return `
          <a data-page="${page.id}" href="#/${page.id}" class="${page.id === this._pageId ? "active" : ""}">
            ${icon(page.icon, page.glyph)}
            <span>${escapeHtml(page.title)}</span>
            ${badge ? `<span class="badge">${escapeHtml(badge)}</span>` : ""}
          </a>`;
      }).join("")}`;
    nav.scrollLeft = navScroll;
  }

  _renderHead() {
    const page = this._page;
    this.shadowRoot.getElementById("page-title").textContent = page.title;
    this.shadowRoot.getElementById("page-subtitle").textContent = page.subtitle || "";
    this.shadowRoot.getElementById("page-status").innerHTML =
      page.renderStatus ? page.renderStatus(this._context()) : "";
  }

  _renderToolbar() {
    const page = this._page;
    const toolbar = this.shadowRoot.getElementById("toolbar");
    const recordingDisabled = this.state.logInfo && this.state.logInfo.enabled === false;

    if (!page.renderToolbar || (page.needsRecording && recordingDisabled)) {
      toolbar.innerHTML = "";
      toolbar.style.display = "none";
      this._renderedToolbarFor = null;
      return;
    }

    toolbar.style.display = "";
    // only rebuild when the page changed, otherwise the filter input would lose the focus
    if (this._renderedToolbarFor === page.id) return;

    toolbar.innerHTML = page.renderToolbar(this._context());
    this._renderedToolbarFor = page.id;
    if (page.bindToolbar) page.bindToolbar(this._context(), this.shadowRoot);
  }

  /**
   * Scroll positions of the content area.
   *
   * Replacing innerHTML destroys every scrollable element: the browser clamps the scrollTop
   * of <main> to 0 while the new content has no height yet, and each freshly created
   * .table-wrapper starts at the left again. On a page which refreshes every few seconds that
   * makes reading a wide table impossible - so the positions are captured and restored.
   *
   * Inner containers are keyed by their position in the document. Between two refreshes the
   * number and order of the tables is stable; if it does change (a block appears), the
   * remaining ones are restored and the new one simply starts at 0.
   */
  // every element of the content which can scroll on its own
  SCROLLABLE_SELECTOR = ".table-wrapper, .dt-log, .detail-drawer, pre";

  _captureScroll(content) {
    const main = this.shadowRoot.querySelector("main");
    return {
      main: main ? { top: main.scrollTop, left: main.scrollLeft } : null,
      inner: [...content.querySelectorAll(this.SCROLLABLE_SELECTOR)]
        .map((element) => ({ top: element.scrollTop, left: element.scrollLeft })),
    };
  }

  _restoreScroll(content, captured) {
    if (!captured) return;
    if (captured.main) {
      const main = this.shadowRoot.querySelector("main");
      if (main) {
        main.scrollTop = captured.main.top;
        main.scrollLeft = captured.main.left;
      }
    }
    const elements = [...content.querySelectorAll(this.SCROLLABLE_SELECTOR)];
    captured.inner.forEach((position, index) => {
      const element = elements[index];
      if (!element) return;
      element.scrollTop = position.top;
      element.scrollLeft = position.left;
    });
  }

  _renderContent() {
    const page = this._page;
    const content = this.shadowRoot.getElementById("content");
    if (!content) return;

    const captured = this._captureScroll(content);

    try {
      content.innerHTML = page.render(this._context());
      // side panels (e.g. the memory content of a bus device) overlay the page instead of
      // scrolling with it: they are moved out of the scrolling <main> into the shell.
      // position:fixed is no option - ancestors of the panel in home assistant use css
      // transforms, which turn "fixed" into "absolute inside that ancestor".
      const outlet = this.shadowRoot.getElementById("drawer-outlet");
      if (outlet) outlet.replaceChildren(...content.querySelectorAll("aside.detail-drawer"));
      if (page.afterRender) page.afterRender(this._context(), this.shadowRoot);
      this._restoreScroll(content, captured);
    } catch (err) {
      content.innerHTML = `<div class="notice warn"><h3>Cannot display this page</h3>
        <pre>${escapeHtml(err && err.stack ? err.stack : err)}</pre></div>`;
    }

    if (this._api && this._api.lastError) {
      content.insertAdjacentHTML("afterbegin", `
        <div class="notice warn">
          <h3>Websocket request failed</h3>
          <p><code>${escapeHtml(this._api.lastError.type)}</code>:
             ${escapeHtml(this._api.lastError.message)}</p>
        </div>`);
    }
  }

  _renderRecordingDisabled() {
    const hint = (this.state.logInfo || {}).hint ||
      "Enable telegram recording in the general settings of your configuration.yaml.";
    return `
      <div class="notice warn">
        <h3>EnOcean telegram recording is disabled</h3>
        <p>${escapeHtml(hint)}</p>
        <pre>eltako:
  general_settings:
    log_enocean_telegrams: True                     # enables recording, statistics and the live view
    telegram_log_filename: enocean_telegrams.jsonl  # optional: additionally write telegrams into a file</pre>
        <p>Restart Home Assistant afterwards. See
          <a class="link" href="https://github.com/grimmpp/home-assistant-eltako/tree/main/docs/telegram-analysis/readme.md"
             target="_blank" rel="noreferrer">the documentation</a> for all options.</p>
      </div>`;
  }
}

if (!customElements.get("eltako-panel")) {
  customElements.define("eltako-panel", EltakoPanel);
}
