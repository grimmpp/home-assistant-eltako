/**
 * Opens the Eltako web ui once, right after the integration was installed.
 *
 * Home Assistant loads this module into its own frontend (not into the panel) while the
 * backend still has the first start pending - see core/onboarding.py. It is deliberately tiny
 * and imports nothing: it runs on every page of Home Assistant until it did its one job.
 *
 * The backend hands the redirect out exactly once, so several open browser tabs cannot fight
 * over it and a reload does not repeat it.
 */

// core/onboarding.py registers this command (const.py: WS_ONBOARDING_CONSUME)
const CONSUME_COMMAND = "eltako/onboarding/consume";
const PANEL_URL = "/eltako";

/** Wait for the websocket connection of the Home Assistant frontend. */
async function connection(timeoutMs = 30000) {
  if (window.hassConnection) {
    const resolved = await window.hassConnection;
    if (resolved && resolved.conn) return resolved.conn;
  }

  // older frontends only have the connection on the root element
  const until = Date.now() + timeoutMs;
  while (Date.now() < until) {
    const conn = /** @type {any} */ (document.querySelector("home-assistant"))?.hass?.connection;
    if (conn) return conn;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return null;
}

/**
 * True while a dialog is on screen.
 *
 * The redirect usually happens while the "integration was added" dialog of the config flow is
 * still open. Navigating behind it would leave the user on a page they cannot see, so the
 * navigation waits for the dialog to be closed.
 */
function dialogIsOpen() {
  const root = document.querySelector("home-assistant")?.shadowRoot;
  return !!root && !!root.querySelector("ha-dialog, ha-md-dialog, dialog-data-entry-flow");
}

async function waitUntilTheViewIsFree(timeoutMs = 120000) {
  const until = Date.now() + timeoutMs;
  while (dialogIsOpen() && Date.now() < until) {
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
}

/** Navigate the way the Home Assistant frontend does it - without reloading the page. */
function navigate(url) {
  window.history.pushState(null, "", url);
  window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
}

async function openTheWebUiOnce() {
  const conn = await connection();
  if (!conn) return;

  let result;
  try {
    result = await conn.sendMessagePromise({ type: CONSUME_COMMAND });
  } catch (err) {
    // not an admin, or the integration was removed in the meantime - nothing to do
    return;
  }
  if (!result || !result.open) return;

  const url = result.url || PANEL_URL;
  if (window.location.pathname === url || window.location.pathname.startsWith(`${url}/`)) return;

  await waitUntilTheViewIsFree();
  navigate(url);
}

openTheWebUiOnce();
