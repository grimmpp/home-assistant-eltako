/**
 * Access to the websocket api of the Eltako integration.
 * Backend: custom_components/eltako/websocket.py and enocean_logger.py
 */

export const WS = {
  INTEGRATION_INFO: "eltako/integration_info",
  CONFIGURED_GATEWAYS: "eltako/configured_gateways",
  USB_PORTS: "eltako/potential_usb_ports",
  MANIFEST: "eltako/info",
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
