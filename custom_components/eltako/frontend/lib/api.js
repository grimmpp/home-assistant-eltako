/**
 * Access to the websocket api of the Eltako integration.
 * Backend: custom_components/eltako/websocket.py and enocean_logger.py
 */

export const WS = {
  INTEGRATION_INFO: "eltako/integration_info",
  CONFIGURED_GATEWAYS: "eltako/configured_gateways",
  USB_PORTS: "eltako/potential_usb_ports",
  MANIFEST: "eltako/info",
  DEVICE_FORM: "eltako/devices/form",
  DEVICE_LIST: "eltako/devices/list",
  DEVICE_ADD: "eltako/devices/add",
  DEVICE_UPDATE: "eltako/devices/update",
  DEVICE_REMOVE: "eltako/devices/remove",
  SEND_TELEGRAM: "eltako/send_telegram",
  SEND_TELEGRAM_FORM: "eltako/send_telegram_form",
  BUS_MEMBERS: "eltako/bus/members",
  BUS_READ_MEMORY: "eltako/bus/read_memory",
  BUS_TEACH_IN: "eltako/bus/teach_in_senders",
  GATEWAY_FORM: "eltako/gateways/form",
  GRAFANA_SYNC: "eltako/grafana/sync",
  GATEWAY_ADD: "eltako/gateways/add",
  GATEWAY_REMOVE: "eltako/gateways/remove",
  GATEWAY_SCAN: "eltako/gateways/scan",
  SETTINGS_GET: "eltako/settings/get",
  SETTINGS_SET: "eltako/settings/set",
  SETTINGS_RESET: "eltako/settings/reset",
  LOG_INFO: "eltako/telegram_log/info",
  LOG_STATISTICS: "eltako/telegram_log/statistics",
  LOG_RECENT: "eltako/telegram_log/recent",
  LOG_SUBSCRIBE: "eltako/telegram_log/subscribe",
  LOG_CLEAR: "eltako/telegram_log/clear",
  LOG_REFRESH_DEVICES: "eltako/telegram_log/refresh_devices",
};

export class EltakoApi {
  constructor(hass) {
    this.hass = hass;
    this.lastError = null;
  }

  /** Send a command and return its result, or null if it failed. */
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
