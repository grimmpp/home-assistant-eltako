/**
 * Web UI of the Home Assistant Eltako integration.
 *
 * This is the entry point of the panel. It provides the shell (navigation, routing,
 * shared data and the live telegram subscription) and loads the sub pages from './pages'.
 *
 * Everything is plain javascript (ES modules), no build step and no dependencies.
 * The backend is implemented in custom_components/eltako/core/websocket.py and
 * custom_components/eltako/observation/enocean_logger.py.
 */

import { ACTIVITY_STYLES, applyBusyLocks, blockingJob, describeJob, jobsOf,
         renderActivity } from "./lib/activity.js";
import { EltakoApi, WS } from "./lib/api.js";
import { BUS_SCAN_STYLES } from "./lib/bus_scan.js";
import { EntityHub } from "./lib/entity_hub.js";
import { STYLES } from "./lib/styles.js";
import { escapeHtml, icon } from "./lib/utils.js";

import { page as homePage } from "./pages/home.js";
import { page as overviewPage } from "./pages/overview.js";
import { page as controlPage } from "./pages/control.js";
import { page as devicesConfigPage } from "./pages/devices_config.js";
import { page as telegramsPage } from "./pages/telegrams.js";
import { page as statisticsPage } from "./pages/devices.js";
import { page as testsPage } from "./pages/tests.js";
import { page as simulationPage } from "./pages/simulation.js";
import { page as settingsPage } from "./pages/settings.js";
import { page as helpPage } from "./pages/help.js";
import { page as aboutPage } from "./pages/about.js";

// pages marked standaloneOnly need the eltako_standalone runtime (its shell sets
// window.eltakoStandalone) - inside Home Assistant they are hidden. Pages with a
// visible(ctx) hook can additionally hide themselves (e.g. by a general setting).
// 'unknown devices' has no page of its own anymore - the addresses which are not configured
// yet are the last block of the device page, next to everything else which exists on the bus.
const PAGES = /** @type {import("./types.js").Page[]} */ (
  [homePage, overviewPage, controlPage, devicesConfigPage, telegramsPage, statisticsPage,
   testsPage, simulationPage, settingsPage, helpPage, aboutPage])
  .filter((page) => !page.standaloneOnly || window.eltakoStandalone);

/**
 * The two views of the panel, switched with the button in the header.
 *
 * "user" is the simple view: one page with all devices as cards, grouped by room - see
 * pages/home.js. "expert" is the full panel with gateways, telegrams, statistics and tests.
 * A page declares in which modes it appears (`page.modes`); without that declaration it
 * belongs to the expert mode only, which keeps every existing page where it was.
 *
 * The chosen mode is stored in the browser, so a reload (and the next visit) opens the panel
 * in the same view again. Home Assistant starts in the user mode; the standalone runtime is
 * an installation and development tool, so there the expert mode is the default.
 */
const MODES = {
  user: { label: "Simple", icon: "mdi:view-grid-outline", glyph: "▦", home: homePage.id,
          title: "Simple view: your devices, grouped by room" },
  expert: { label: "Expert", icon: "mdi:tune-variant", glyph: "⚙", home: overviewPage.id,
            title: "Expert view: gateways, telegrams, statistics and all device settings" },
};
const DEFAULT_MODE = window.eltakoStandalone ? "expert" : "user";
const MODE_STORAGE_KEY = "eltako-panel-mode";
const pageModes = (page) => page.modes || ["expert"];
// resolved from this module's own url, so it works in Home Assistant (/eltako_frontend/...)
// and in the standalone runtime alike. Replace img/eltako-logo.svg to use the official logo.
// The official Eltako logo. img/eltako-logo.svg is Eltako's own vector file (from the theme
// of eltako.com), so it stays sharp at any size; the png next to it is the raster version
// Home Assistant shows for this integration in its settings and serves as a fallback.
const LOGO_URL = new URL("./img/eltako-logo.svg", import.meta.url).href;
const LOGO_URL_FALLBACK = new URL("./img/eltako-logo.png", import.meta.url).href;
const MAX_LIVE_TELEGRAMS = 500;

class EltakoPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._api = null;
    this._connected = false;
    this._narrow = false;
    /** @type {import("./types.js").HaElement} */
    this._menuButton = null;
    this._mode = this._storedMode();
    // a bookmarked url wins over the stored mode: #/telegrams opens the expert mode even if
    // the panel was left in the simple view
    const linked = PAGES.find((page) => page.id === this._hashPageId());
    if (linked && !pageModes(linked).includes(this._mode)) this._mode = pageModes(linked)[0];
    this._pageId = this._pageIdFromLocation();
    this._unsubscribeTelegrams = null;
    this._refreshTimer = null;
    this._activityTimer = null;
    this._renderScheduled = false;
    this._contentRenderScheduled = false;
    this._renderedToolbarFor = null;
    /** live entity states: a page registers the ids it shows and patches its own dom */
    this._entities = new EntityHub(() => (this._hass || {}).states || {});

    /** data shared between all pages */
    this.state = {
      integrationInfo: null,
      logInfo: null,
      statistics: null,
      telegrams: [],
      /** what the integration is busy with right now - see _renderActivity */
      activity: { busy: false, jobs: [] },
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
      // simple device page of the user mode (pages/home.js)
      simpleFilter: "",
      simpleEditor: null,
      // settings page
      settingsForm: null,
      settingsError: null,
      settingsMessage: null,
      // help page
      helpCatalog: null,
      helpFilter: "",
      // usb/serial port scan
      portScan: null,
      busMembers: null,
      gatewayForm: null,
      gatewayEditor: null,
      // plug & play: status, progress and report of the last detection run
      plugAndPlay: null,
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

  /**
   * Home Assistant assigns a new `hass` on every state change (the standalone shell re-sets
   * its own one after each pushed state event). That is the signal the entity hub runs on:
   * the elements which show a state update themselves, without the page being rendered again.
   */
  set hass(hass) {
    const isFirst = this._hass === null;
    this._hass = hass;
    if (this._menuButton) this._menuButton.hass = hass;
    if (isFirst) {
      this._api = new EltakoApi(hass);
      this._renderShell();
      this._start();
      return;
    }
    this._api.hass = hass;
    this._entities.update();
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
    this._leavePage();
    this._stopRefreshTimer();
    clearTimeout(this._activityTimer);
    this._activityTimer = null;
    if (this._unsubscribeTelegrams) {
      this._unsubscribeTelegrams.then((unsubscribe) => unsubscribe()).catch(() => {});
      this._unsubscribeTelegrams = null;
    }
  }

  async _start() {
    // integration info is needed by the navigation (pages can hide themselves
    // depending on the general settings, see page.visible)
    // the activity is loaded before the first render: a bus scan which was started somewhere
    // else has to be visible the moment the panel opens, not ten seconds later
    await Promise.all([this.loadLogInfo(), this.loadIntegrationInfo(), this.loadActivity()]);
    this._subscribeTelegrams();
    await this._enterPage();
    this._pollActivity();
  }

  /* ------------------------------------------------------------------- mode */

  _storedMode() {
    try {
      const stored = window.localStorage.getItem(MODE_STORAGE_KEY);
      if (stored && MODES[stored]) return stored;
    } catch (err) {
      // private mode / storage blocked: the panel simply starts in the default mode
    }
    return DEFAULT_MODE;
  }

  /** Remembers the mode in the browser so a reload opens the same view again. */
  _applyMode(mode) {
    this._mode = mode;
    try {
      window.localStorage.setItem(MODE_STORAGE_KEY, mode);
    } catch (err) {
      // storage blocked (private mode): the switch still works for this session
    }
  }

  /**
   * Switches the view. If the current page does not exist in the new mode, the panel opens
   * that mode's home page.
   */
  _setMode(mode, pageId = null) {
    if (!MODES[mode]) return;
    const current = this._page;
    this._applyMode(mode);
    const target = pageId || (pageModes(current).includes(mode) ? this._pageId : MODES[mode].home);
    if (target === this._pageId) {
      this._render();
    } else {
      this._navigate(target);
    }
  }

  _modePages() {
    return PAGES.filter((page) => pageModes(page).includes(this._mode));
  }

  /* ---------------------------------------------------------------- routing */

  _hashPageId() {
    return (window.location.hash || "").replace(/^#\/?/, "").split("?")[0];
  }

  /** The url wins over the mode: a link to a page of the other view switches the view. */
  _pageIdFromLocation() {
    const hash = this._hashPageId();
    return PAGES.some((page) => page.id === hash) ? hash : MODES[this._mode].home;
  }

  get _page() {
    return PAGES.find((page) => page.id === this._pageId) || this._modePages()[0] || PAGES[0];
  }

  _navigate(pageId) {
    if (this._pageId === pageId) return;
    // a link into the other view (e.g. "set up a gateway" out of the simple view) switches
    // the mode along with the page instead of running into a page which is not shown
    const target = PAGES.find((page) => page.id === pageId);
    if (target && !pageModes(target).includes(this._mode)) this._applyMode(pageModes(target)[0]);
    this._leavePage();
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
        // Pages with their own forms answer that question themselves (page.isEditing).
        if (this.state.editor || this.state.gatewayEditor || this.state.sendForm) return;
        if (page.isEditing && page.isEditing(this._context())) return;
        if (page.load) await page.load(this._context());
        this._render();
      }, page.refreshMs);
    }
  }

  /**
   * The page is left: it drops what outlives its dom - the listeners it registered at the
   * entity hub and its own timers. Called before another page is opened and when the panel
   * is removed; a page without live listeners does not need the hook.
   */
  _leavePage() {
    const page = this._page;
    if (page && page.leave) page.leave(this._context());
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

  /* --------------------------------------------------------------- activity */

  /**
   * What the integration is busy with right now (core/websocket.get_activity).
   *
   * This is the one thing every page needs and no page owns: reading a bus takes minutes,
   * locks that bus and makes every other bus operation fail. Whoever started it sees a
   * progress card on their page - but a user who switches to another page, reloads or comes
   * back later sees nothing and presses a button which then does nothing. So the panel polls
   * it centrally and shows it above the content of *every* page.
   */
  async loadActivity() {
    const activity = await this._api.call(WS.ACTIVITY);
    if (activity) this.state.activity = activity;
    return this.state.activity;
  }

  /** Fast while something runs (the counters move), slow while nothing does. */
  _pollActivity() {
    clearTimeout(this._activityTimer);
    const delay = (this.state.activity || {}).busy ? 2000 : 10000;
    this._activityTimer = setTimeout(async () => {
      if (!this.isConnected) return;
      const before = JSON.stringify(this.state.activity || {});
      await this.loadActivity();
      this._renderActivity();
      this._applyBusyLocks();
      // a job which appeared or disappeared changes what the page itself shows (a finished
      // scan brings new devices), so the page is asked to reload once
      if (before !== JSON.stringify(this.state.activity || {})) this._onActivityChanged(before);
      this._pollActivity();
    }, delay);
  }

  /**
   * The set of running jobs changed. While something runs the page is left alone (it polls
   * its own detail if it wants to); when the last job is done every page gets one reload, so
   * the devices a scan found appear without the user having to press anything.
   */
  async _onActivityChanged(before) {
    const wasBusy = (JSON.parse(before || "{}") || {}).busy;
    if (!wasBusy || (this.state.activity || {}).busy) return;
    const page = this._page;
    if (this.state.editor || this.state.gatewayEditor || this.state.sendForm) return;
    if (page.isEditing && page.isEditing(this._context())) return;
    if (page.load) await page.load(this._context());
    this._render();
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
      // live entity states - see lib/entity_hub.js and pages/home.js
      entities: this._entities,
      mode: this._mode,
      setMode: (mode, pageId = null) => this._setMode(mode, pageId),
      loadIntegrationInfo: () => this.loadIntegrationInfo(),
      // a page which just started something long calls this: the banner appears at once
      // instead of at the next poll, and the buttons it blocks are locked right away
      refreshActivity: async () => {
        await this.loadActivity();
        this._renderActivity();
        this._applyBusyLocks();
        this._pollActivity();
      },
      // "may I start this now?" - the same tokens as data-busy-block, see lib/activity.js
      isBusy: (token = "any") => !!blockingJob(jobsOf(this.state.activity), token),
      busyReason: (token = "any") => {
        const job = blockingJob(jobsOf(this.state.activity), token);
        return job ? describeJob(job).title : null;
      },
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
      <style>${STYLES}${BUS_SCAN_STYLES}${ACTIVITY_STYLES}${PAGES.map((page) => page.styles || "").join("")}</style>
      <div class="shell">
        <div class="topbar">
          <header class="app-head">
            <span class="brand">
              <span id="menu-button-slot"></span>
              ${icon("mdi:access-point-network", "◉")}
              <span class="brand-title">ELTAKO &ndash; EnOcean</span>
              <span class="brand-version" id="app-version"></span>
            </span>
          </header>
          <nav id="nav"></nav>
          <!-- outside of header and nav so it can be centred over the height of the whole
               white bar, not just over the row with the title -->
          <img class="brand-logo" src="${LOGO_URL}" alt="ELTAKO"
               data-fallback="${LOGO_URL_FALLBACK}"
               onerror="if (this.dataset.fallback) { this.src = this.dataset.fallback;
                          this.dataset.fallback = ''; } else { this.style.display = 'none'; }" />
        </div>
        <main>
          <header class="page-head">
            <div>
              <h1 id="page-title"></h1>
              <div class="page-subtitle" id="page-subtitle"></div>
            </div>
            <div class="head-status" id="page-status"></div>
          </header>
          <!-- above the toolbar on purpose: the buttons it disables are right below it -->
          <section class="activity" id="activity"></section>
          <section class="toolbar" id="toolbar"></section>
          <section id="content"><div class="empty">Loading&hellip;</div></section>
        </main>
        <div id="drawer-outlet"></div>
      </div>`;

    this.shadowRoot.getElementById("nav").addEventListener("click", (event) => {
      const target = /** @type {Element} */ (event.target);
      // the view switch sits at the right end of the same bar as the page links
      const modeButton = /** @type {HTMLButtonElement} */ (target.closest("button[data-mode]"));
      if (modeButton) {
        this._setMode(modeButton.dataset.mode);
        return;
      }
      const link = /** @type {HTMLAnchorElement} */ (target.closest("a[data-page]"));
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
      this._menuButton = /** @type {import("./types.js").HaElement} */
        (document.createElement("ha-menu-button"));
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
    this._renderActivity();
    this._renderToolbar();
    this._renderContent();
  }

  /**
   * The switch between the simple and the expert view, at the right end of the navigation.
   * It is part of the navigation markup (and not a static element) because _renderNav()
   * rebuilds the whole bar - and it has to show which view is active.
   */
  _modeSwitchHtml() {
    return `
      <div class="mode-switch" role="group" aria-label="View">
        ${Object.entries(MODES).map(([mode, definition]) => `
          <button data-mode="${mode}" class="${mode === this._mode ? "active" : ""}"
                  title="${escapeHtml(definition.title)}" aria-pressed="${mode === this._mode}">
            ${icon(definition.icon, definition.glyph)}<span>${escapeHtml(definition.label)}</span>
          </button>`).join("")}
      </div>`;
  }

  _renderNav() {
    const info = this.state.integrationInfo || {};
    const context = this._context();
    const version = this.shadowRoot.getElementById("app-version");
    if (version) version.textContent = info.version ? `v${info.version}` : "";
    const nav = this.shadowRoot.getElementById("nav");
    // on a narrow screen the navigation scrolls horizontally - a refresh must not jump it
    // back to the first entry
    const navScroll = nav ? nav.scrollLeft : 0;
    nav.innerHTML = `
      ${this._modePages().filter((page) => !page.visible || page.visible(context)).map((page) => {
        const badge = page.badge ? page.badge(context) : null;
        return `
          <a data-page="${page.id}" href="#/${page.id}" class="${page.id === this._pageId ? "active" : ""}">
            ${icon(page.icon, page.glyph)}
            <span>${escapeHtml(page.title)}</span>
            ${badge ? `<span class="badge">${escapeHtml(badge)}</span>` : ""}
          </a>`;
      }).join("")}
      ${this._modeSwitchHtml()}`;
    nav.scrollLeft = navScroll;
  }

  _renderHead() {
    const page = this._page;
    this.shadowRoot.getElementById("page-title").textContent = page.title;
    this.shadowRoot.getElementById("page-subtitle").textContent = page.subtitle || "";
    this.shadowRoot.getElementById("page-status").innerHTML =
      page.renderStatus ? page.renderStatus(this._context()) : "";
  }

  /* ------------------------------------------------------ what runs right now */

  /** The banner above the content of every page - see lib/activity.js for what it says. */
  _renderActivity() {
    const section = this.shadowRoot.getElementById("activity");
    if (section) section.innerHTML = renderActivity(this.state.activity);
  }

  /** Buttons which would collide with a running job are disabled and say why. */
  _applyBusyLocks() {
    applyBusyLocks(this.shadowRoot, jobsOf(this.state.activity));
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
      // the same for the popup of the simple view (aside.modal-overlay) - it is fixed to the
      // viewport and would be trapped inside the transformed ancestor as well
      const outlet = this.shadowRoot.getElementById("drawer-outlet");
      if (outlet) {
        outlet.replaceChildren(
          ...content.querySelectorAll("aside.detail-drawer, aside.modal-overlay"));
      }
      if (page.afterRender) page.afterRender(this._context(), this.shadowRoot);
      this._restoreScroll(content, captured);
      // last, so a button which a page just rendered (toolbar included) is locked as well
      this._applyBusyLocks();
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
