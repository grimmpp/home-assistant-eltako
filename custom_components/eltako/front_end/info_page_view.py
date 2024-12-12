from aiohttp import web
from homeassistant.components.http import HomeAssistantView

class InfoPageView(HomeAssistantView):
    """Serve a custom page."""

    url = "/eltako/info"
    name = "eltako-info"
    requires_auth = True

    async def get(self, request):
        """Handle GET request."""
        return web.Response(
            text="<html><body><h1>Hello, Home Assistant!</h1></body></html>",
            content_type="text/html"
        )
