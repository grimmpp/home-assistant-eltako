"""Tests: the standalone web server speaks the protocol subset the frontend uses."""

import asyncio

from eltako_standalone.runtime import EltakoRuntime
from eltako_standalone.server import StandaloneServer

PORT = 18124        # far away from anything a developer runs by hand


def test_the_default_port_is_not_the_one_of_home_assistant():
    """8123 belongs to Home Assistant, and sharing it shares the origin in the browser.

    The service worker of the Home Assistant frontend stays registered for that origin and keeps
    serving its cached app shell - the standalone web ui then looks like a Home Assistant which
    never finishes starting, which is a confusing bug to chase.
    """
    from eltako_standalone.cli import DEFAULT_PORT, build_parser
    from eltako_standalone.server import StandaloneServer
    import inspect

    assert DEFAULT_PORT == 8124
    assert DEFAULT_PORT != 8123

    args = build_parser().parse_args(['serve'])
    assert args.port == DEFAULT_PORT
    # and it can still be chosen freely
    assert build_parser().parse_args(['serve', '--port', '8123']).port == 8123

    signature = inspect.signature(StandaloneServer.__init__)
    assert signature.parameters['port'].default == DEFAULT_PORT


def test_http_and_websocket(config_dir):
    async def scenario():
        import aiohttp

        runtime = EltakoRuntime(config_dir)
        await runtime.async_start()
        await runtime.hass.async_block_till_done()
        server = StandaloneServer(runtime.hass, host="127.0.0.1", port=PORT)
        await server.async_start()

        async with aiohttp.ClientSession() as session:
            for url in ("/", "/shell/shell.js", "/eltako_frontend/eltako-panel.js"):
                async with session.get(f"http://127.0.0.1:{PORT}{url}") as response:
                    assert response.status == 200, url

            async with session.ws_connect(f"http://127.0.0.1:{PORT}/api/websocket") as ws:
                assert (await ws.receive_json())["type"] == "auth_required"
                await ws.send_json({"type": "auth", "access_token": "anything"})
                assert (await ws.receive_json())["type"] == "auth_ok"

                await ws.send_json({"id": 1, "type": "eltako/integration_info"})
                msg = await ws.receive_json()
                assert msg["success"] and msg["result"]["domain"] == "eltako"
                assert len(msg["result"]["gateways"]) == 1

                await ws.send_json({"id": 2, "type": "eltako/entities/list"})
                msg = await ws.receive_json()
                assert msg["success"] and len(msg["result"]["entities"]) > 5

                # subscription: a state change is pushed as event
                await ws.send_json({"id": 3, "type": "eltako/entities/subscribe"})
                assert (await ws.receive_json())["success"]
                runtime.hass.states.async_set("light.test_entity", "on", {"friendly_name": "x"})
                msg = await ws.receive_json()
                assert msg["type"] == "event"
                assert msg["event"]["entity_id"] == "light.test_entity"
                assert msg["event"]["state"] == "on"

                # unsubscribe works
                await ws.send_json({"id": 4, "type": "unsubscribe_events", "subscription": 3})
                msg = await ws.receive_json()
                assert msg["success"]

                # unknown command is answered with an error, not a dead socket
                await ws.send_json({"id": 5, "type": "eltako/nope"})
                msg = await ws.receive_json()
                assert msg["success"] is False
                assert msg["error"]["code"] == "unknown_command"

        await server.async_stop()
        await runtime.async_stop()

    asyncio.run(scenario())


def test_token_auth(empty_config_dir):
    async def scenario():
        import aiohttp

        runtime = EltakoRuntime(empty_config_dir)
        await runtime.async_start()
        server = StandaloneServer(runtime.hass, host="127.0.0.1", port=PORT + 1,
                                  token="secret")
        await server.async_start()

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"http://127.0.0.1:{PORT + 1}/api/websocket") as ws:
                await ws.receive_json()
                await ws.send_json({"type": "auth", "access_token": "wrong"})
                assert (await ws.receive_json())["type"] == "auth_invalid"

            async with session.ws_connect(f"http://127.0.0.1:{PORT + 1}/api/websocket") as ws:
                await ws.receive_json()
                await ws.send_json({"type": "auth", "access_token": "secret"})
                assert (await ws.receive_json())["type"] == "auth_ok"

        await server.async_stop()
        await runtime.async_stop()

    asyncio.run(scenario())
