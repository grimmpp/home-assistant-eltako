"""Frontend panel registration mirroring homeassistant.components.frontend."""

DATA_PANELS = "frontend_panels"


def async_register_built_in_panel(hass, component_name, sidebar_title=None, sidebar_icon=None,
                                  frontend_url_path=None, config=None, require_admin=False,
                                  *, update=False, config_panel_domain=None) -> None:
    hass.data.setdefault(DATA_PANELS, {})[frontend_url_path or component_name] = {
        "component_name": component_name,
        "sidebar_title": sidebar_title,
        "sidebar_icon": sidebar_icon,
        "config": config,
        "require_admin": require_admin,
    }
