/**
 * Bootstrap for the standalone web ui.
 *
 * Provides a small `hass`-like object (connection + states) implementing exactly
 * what the eltako-panel uses (hass.connection.sendMessagePromise/subscribeMessage
 * and hass.states), then loads the unchanged frontend of the integration.
 */

window.eltakoStandalone = true;

class StandaloneConnection {
  constructor() {
    this._msgId = 1;
    this._pending = new Map();      // id -> {resolve, reject}
    this._subscriptions = new Map(); // id -> callback
    this._ws = null;
    this._authenticated = false;
    this._queue = [];
    this._onOpenHandlers = [];
  }

  connect() {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    this._ws = new WebSocket(`${protocol}://${location.host}/api/websocket`);
    this._ws.addEventListener("message", (event) => this._onMessage(JSON.parse(event.data)));
    this._ws.addEventListener("close", () => this._onClose());
    this._ws.addEventListener("error", () => this._ws.close());
  }

  _onMessage(msg) {
    if (msg.type === "auth_required") {
      // token support: append ?token=... to the url
      const token = new URLSearchParams(location.search).get("token") || "standalone";
      this._ws.send(JSON.stringify({ type: "auth", access_token: token }));
      return;
    }
    if (msg.type === "auth_ok") {
      this._authenticated = true;
      document.getElementById("connect-error").style.display = "none";
      this._queue.splice(0).forEach((raw) => this._ws.send(raw));
      this._onOpenHandlers.forEach((handler) => handler());
      return;
    }
    if (msg.type === "auth_invalid") {
      document.getElementById("connect-error").innerHTML =
        `<h2>Not authorized</h2><p>${msg.message || ""} - append ?token=&lt;token&gt; to the url.</p>`;
      document.getElementById("connect-error").style.display = "block";
      return;
    }
    if (msg.type === "event") {
      const callback = this._subscriptions.get(msg.id);
      if (callback) callback(msg.event);
      return;
    }
    if (msg.type === "result") {
      const pending = this._pending.get(msg.id);
      if (!pending) return;
      this._pending.delete(msg.id);
      if (msg.success) pending.resolve(msg.result);
      else pending.reject(msg.error || { message: "unknown error" });
    }
  }

  _onClose() {
    this._authenticated = false;
    document.getElementById("connect-error").style.display = "block";
    this._pending.forEach((pending) => pending.reject({ message: "connection closed" }));
    this._pending.clear();
    setTimeout(() => this.connect(), 2000);
  }

  onReconnect(handler) {
    this._onOpenHandlers.push(handler);
  }

  _send(message) {
    const raw = JSON.stringify(message);
    if (this._authenticated && this._ws.readyState === WebSocket.OPEN) this._ws.send(raw);
    else this._queue.push(raw);
  }

  sendMessagePromise(message) {
    const id = this._msgId++;
    return new Promise((resolve, reject) => {
      this._pending.set(id, { resolve, reject });
      this._send({ id, ...message });
    });
  }

  async subscribeMessage(callback, message) {
    const id = this._msgId++;
    this._subscriptions.set(id, callback);
    await new Promise((resolve, reject) => {
      this._pending.set(id, { resolve, reject });
      this._send({ id, ...message });
    });
    return () => {
      this._subscriptions.delete(id);
      return this.sendMessagePromise({ type: "unsubscribe_events", subscription: id });
    };
  }
}

const connection = new StandaloneConnection();
connection.connect();

const hass = {
  connection,
  states: {},
  // the panel only renders ha-menu-button when the element exists - it does not here,
  // so the fallback hamburger is used; hide it by handling the toggle as no-op.
};

/** the panel element - created below, but the state events may arrive before that */
let panel = null;

/**
 * Home Assistant assigns a new `hass` to a panel whenever a state changed; the panel uses
 * that as the signal for its entity hub (lib/entity_hub.js), which is what lets a card
 * update itself instead of the page being reloaded. Here the object stays the same, so
 * the assignment is what has to be repeated after every event.
 */
function publishStates() {
  if (panel) panel.hass = hass;
}

/** keep hass.states live so that the pages of the panel can show entity states */
async function trackStates() {
  try {
    const result = await connection.sendMessagePromise({ type: "eltako/entities/list" });
    (result.entities || []).forEach((entity) => {
      hass.states[entity.entity_id] = { state: entity.state, attributes: entity.attributes };
    });
    publishStates();
    await connection.subscribeMessage((event) => {
      hass.states[event.entity_id] = { state: event.state, attributes: event.attributes };
      publishStates();
    }, { type: "eltako/entities/subscribe" });
  } catch (err) {
    console.warn("Cannot subscribe to entity states:", err);
  }
}

connection.onReconnect(() => trackStates());
trackStates();

await import("/eltako_frontend/eltako-panel.js");

panel = document.createElement("eltako-panel");
panel.narrow = false;
panel.hass = hass;
document.body.appendChild(panel);

// hide the hamburger fallback - there is no Home Assistant sidebar to toggle
document.addEventListener("hass-toggle-menu", (event) => event.stopPropagation(), true);
