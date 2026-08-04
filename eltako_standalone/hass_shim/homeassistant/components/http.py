"""HTTP registration mirroring homeassistant.components.http.

Static paths and views are only recorded here - the standalone web server (server.py)
serves them with aiohttp.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StaticPathConfig:
    url_path: str
    path: str
    cache_headers: bool = True


class HomeAssistantView:
    """Base class of a Home Assistant http view.

    The integration serves its frontend folder through such a view so that it can send an
    explicit no-cache header (see EltakoFrontendView). Only the attributes the integration
    uses are mirrored - the standalone server serves the frontend folder itself and does not
    need to route the view.
    """

    url: str | None = None
    extra_urls: list[str] = []
    name: str | None = None
    requires_auth: bool = True


class HomeAssistantHTTP:
    """Assigned to hass.http by the runtime."""

    def __init__(self):
        self.static_paths: list[StaticPathConfig] = []
        self.views: list[HomeAssistantView] = []

    async def async_register_static_paths(self, configs) -> None:
        self.static_paths.extend(configs)

    def register_view(self, view) -> None:
        self.views.append(view)
