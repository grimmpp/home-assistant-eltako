"""Frontend panel registration mirroring homeassistant.components.frontend."""

DATA_PANELS = "frontend_panels"
DATA_EXTRA_MODULE_URL = "frontend_extra_module_url"


def async_register_built_in_panel(hass, component_name, sidebar_title=None, sidebar_icon=None,
                                  frontend_url_path=None, config=None, require_admin=False,
                                  *, update=False, config_panel_domain=None,
                                  show_in_sidebar=True) -> None:
    hass.data.setdefault(DATA_PANELS, {})[frontend_url_path or component_name] = {
        "component_name": component_name,
        "sidebar_title": sidebar_title,
        "sidebar_icon": sidebar_icon,
        "config": config,
        "require_admin": require_admin,
        "show_in_sidebar": show_in_sidebar,
    }


def async_panel_exists(hass, frontend_url_path: str) -> bool:
    return frontend_url_path in hass.data.get(DATA_PANELS, {})


def async_remove_panel(hass, frontend_url_path: str, *, warn_if_unknown: bool = True) -> None:
    hass.data.get(DATA_PANELS, {}).pop(frontend_url_path, None)


def add_extra_js_url(hass, url: str, es5: bool = False) -> None:
    """The standalone web server builds its own shell page - nothing to inject into."""
    hass.data.setdefault(DATA_EXTRA_MODULE_URL, set()).add(url)


def remove_extra_js_url(hass, url: str, es5: bool = False) -> None:
    hass.data.setdefault(DATA_EXTRA_MODULE_URL, set()).discard(url)
