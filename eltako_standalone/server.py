"""Standalone web server: serves the existing web ui of the integration and a
websocket endpoint speaking the (small) subset of the Home Assistant websocket
protocol which the frontend uses.

    GET  /                  shell page which loads the eltako-panel web component
    GET  /shell.js          bootstrap providing a `hass`-like object
    GET  /eltako_frontend/  the unchanged frontend folder of the integration
    WS   /api/websocket     auth_required/auth_ok handshake + command dispatch

Message flow is identical to Home Assistant:
    {id, type: "eltako/...", ...}  ->  {id, type: "result", success, result}
    subscriptions push               {id, type: "event", event: {...}}
    {type: "unsubscribe_events", subscription: id} cancels a subscription.
"""

from __future__ import annotations

import json
import logging
import os

from aiohttp import WSMsgType, web

LOGGER = logging.getLogger("eltako_standalone.server")

SHELL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shell")


class StandaloneServer:
    def __init__(self, hass, host: str = "127.0.0.1", port: int = 8124,
                 token: str | None = None):
        self.hass = hass
        self.host = host
        self.port = port
        self.token = token
        self._runner: web.AppRunner | None = None

    def _current_hass(self):
        return getattr(self, "runtime", None).hass if getattr(self, "runtime", None) else self.hass

    # ------------------------------------------------------------------ http
    def build_app(self) -> web.Application:
        app = web.Application(middlewares=[self._no_cache_middleware])
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/api/websocket", self._handle_websocket)
        app.router.add_static("/shell", SHELL_DIR)

        # the static paths the integration registered (the frontend folder). If the
        # web ui was disabled in the settings, serve the frontend folder anyway -
        # running the standalone server IS the opt-in.
        static_paths = {config.url_path: config.path
                        for config in getattr(self._current_hass().http, "static_paths", [])}
        if not static_paths:
            from custom_components.eltako.const import PANEL_STATIC_URL
            import custom_components.eltako as integration_pkg
            frontend = os.path.join(os.path.dirname(integration_pkg.__file__), "frontend")
            static_paths[PANEL_STATIC_URL] = frontend
        for url_path, path in static_paths.items():
            app.router.add_static(url_path, path)

        return app

    @staticmethod
    @web.middleware
    async def _no_cache_middleware(request, handler):
        """Never let the browser cache the web ui.

        The frontend is mounted live from the repository, so an edited file has to take effect
        on a reload. aiohttp's add_static only sends ETag/Last-Modified, and browsers cache ES
        modules heuristically without revalidating - the change is then invisible until a hard
        reload. Home Assistant registers the same folder with cache_headers=False for exactly
        this reason.
        """
        response = await handler(request)
        try:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        except Exception:   # noqa: BLE001 - websocket responses have no mutable headers
            pass
        return response

    async def async_start(self) -> None:
        self._runner = web.AppRunner(self.build_app())
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        LOGGER.info("Web ui: http://%s:%d/", self.host, self.port)

    async def async_stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _handle_index(self, request: web.Request) -> web.Response:
        with open(os.path.join(SHELL_DIR, "index.html"), encoding="utf-8") as handle:
            return web.Response(text=handle.read(), content_type="text/html")

    # ------------------------------------------------------------- websocket
    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        from homeassistant.components.websocket_api import (
            ActiveConnection, async_handle_message, result_message)

        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)

        await ws.send_json({"type": "auth_required", "ha_version": "eltako-standalone"})
        authenticated = False
        connection = None

        def send(message: dict) -> None:
            if not ws.closed:
                self._current_hass().async_create_task(ws.send_str(json.dumps(message, default=str)))

        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    break
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue

                if not authenticated:
                    if data.get("type") != "auth":
                        await ws.send_json({"type": "auth_invalid",
                                            "message": "auth message expected"})
                        break
                    if self.token and data.get("access_token") != self.token:
                        await ws.send_json({"type": "auth_invalid",
                                            "message": "invalid access token"})
                        break
                    authenticated = True
                    connection = ActiveConnection(self._current_hass(), send)
                    await ws.send_json({"type": "auth_ok",
                                        "ha_version": "eltako-standalone"})
                    continue

                if data.get("type") == "unsubscribe_events":
                    subscription = data.get("subscription")
                    unsubscribe = connection.subscriptions.pop(subscription, None)
                    if unsubscribe is not None:
                        try:
                            unsubscribe()
                        except Exception:  # noqa: BLE001
                            LOGGER.debug("Unsubscribe failed", exc_info=True)
                    send(result_message(data.get("id", 0)))
                    continue

                if data.get("type") == "ping":
                    send({"id": data.get("id", 0), "type": "pong"})
                    continue

                current_hass = self._current_hass()
                if getattr(connection, "hass", current_hass) is not current_hass:
                    connection.hass = current_hass
                await async_handle_message(current_hass, connection, data)
        finally:
            if connection is not None:
                connection.async_handle_close()
        return ws
