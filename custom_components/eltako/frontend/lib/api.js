/**
 * Access to the websocket api of the Eltako integration.
 * Backend: custom_components/eltako/core/websocket.py and observation/enocean_logger.py
 */

// `@type {const}` keeps the literal strings: that is what lets api.call() look the result
// type of a command up in WsResults (types.d.ts). Without it every value would be a plain
// `string` and the map could not be indexed.
// `@satisfies` checks the other direction - a command which has no entry in WsResults yet
// is an error here instead of silently falling back to `any`.
export const WS = /** @type {const} @satisfies {Record<string, import("../types.js").WsCommand>} */ ({
  INTEGRATION_INFO: "eltako/integration_info",
  ACTIVITY: "eltako/activity",
  CONFIGURED_GATEWAYS: "eltako/configured_gateways",
  USB_PORTS: "eltako/potential_usb_ports",
  MANIFEST: "eltako/info",
  DEVICE_FORM: "eltako/devices/form",
  DEVICE_LIST: "eltako/devices/list",
  DEVICE_ADD: "eltako/devices/add",
  DEVICE_UPDATE: "eltako/devices/update",
  DEVICE_REMOVE: "eltako/devices/remove",
  DEVICE_REMOVE_ALL: "eltako/devices/remove_all",
  DEVICE_TEACH_IN: "eltako/devices/teach_in",
  SEND_TELEGRAM: "eltako/send_telegram",
  SEND_TELEGRAM_FORM: "eltako/send_telegram_form",
  BUS_MEMBERS: "eltako/bus/members",
  BUS_READ_MEMORY: "eltako/bus/read_memory",
  BUS_TEACH_IN: "eltako/bus/teach_in_senders",
  GATEWAY_FORM: "eltako/gateways/form",
  GRAFANA_SYNC: "eltako/grafana/sync",
  GATEWAY_ADD: "eltako/gateways/add",
  GATEWAY_UPDATE: "eltako/gateways/update",
  GATEWAY_REMOVE: "eltako/gateways/remove",
  GATEWAY_REPAIR: "eltako/gateways/repair",
  GATEWAY_SCAN: "eltako/gateways/scan",
  PNP_STATUS: "eltako/plug_and_play/status",
  PNP_RUN: "eltako/plug_and_play/run",
  SIMULATOR_FORM: "eltako/simulator/form",
  SIMULATOR_PRESET: "eltako/simulator/preset",
  SIMULATOR_GATEWAY_ADD: "eltako/simulator/gateway_add",
  SIMULATOR_GATEWAY_REMOVE: "eltako/simulator/gateway_remove",
  SIMULATOR_BASE_ID: "eltako/simulator/base_id",
  SIMULATOR_DEVICE_ADD: "eltako/simulator/device_add",
  SIMULATOR_DEVICE_UPDATE: "eltako/simulator/device_update",
  SIMULATOR_DEVICE_REMOVE: "eltako/simulator/device_remove",
  SIMULATOR_TRIGGER: "eltako/simulator/trigger",
  SIMULATOR_TEACH_IN: "eltako/simulator/teach_in",
  SIMULATOR_ACTIVATE: "eltako/simulator/activate",
  HELP_CATALOG: "eltako/help/catalog",
  SETTINGS_GET: "eltako/settings/get",
  SETTINGS_SET: "eltako/settings/set",
  SETTINGS_RESET: "eltako/settings/reset",
  LOG_INFO: "eltako/telegram_log/info",
  LOG_STATISTICS: "eltako/telegram_log/statistics",
  LOG_RECENT: "eltako/telegram_log/recent",
  LOG_SUGGESTIONS: "eltako/telegram_log/suggestions",
  LOG_SUBSCRIBE: "eltako/telegram_log/subscribe",
  LOG_CLEAR: "eltako/telegram_log/clear",
  LOG_REFRESH_DEVICES: "eltako/telegram_log/refresh_devices",
});

export class EltakoApi {
  /** @param {import("../types.js").HomeAssistant} hass */
  constructor(hass) {
    this.hass = hass;
    /** @type {{type: string, message: string} | null} */
    this.lastError = null;
  }

  /**
   * Send a command and return its result, or null if it failed.
   *
   * The result type comes from WsResults in types.d.ts, so reading a field which the
   * backend does not send is an error instead of `undefined` at runtime.
   *
   * @template {import("../types.js").WsCommand} T
   * @param {T} type
   * @param {Record<string, any>} [payload]
   * @returns {Promise<import("../types.js").WsResults[T] | null>}
   */
  async call(type, payload = {}) {
    try {
      const result = await this.hass.connection.sendMessagePromise({ type, ...payload });
      this.lastError = null;
      return result;
    } catch (err) {
      this.lastError = { type, message: err && err.message ? err.message : String(err) };
      return null;
    }
  }

  /** Subscribe to the live stream of recorded telegrams. Returns a promise of an unsubscribe function. */
  subscribeTelegrams(callback) {
    return this.hass.connection.subscribeMessage(callback, { type: WS.LOG_SUBSCRIBE });
  }
}
