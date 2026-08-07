"""Custom panel registration mirroring homeassistant.components.panel_custom.

The standalone web server reads the recorded panel to know which web component
and which module url the shell page has to load.
"""

from . import frontend

DATA_CUSTOM_PANELS = "panel_custom_panels"


async def async_register_panel(*, hass, frontend_url_path, webcomponent_name,
                               sidebar_title=None, sidebar_icon=None, module_url=None,
                               embed_iframe=False, require_admin=False, config=None,
                               js_url=None, trust_external=False,
                               config_panel_domain=None) -> None:
    hass.data.setdefault(DATA_CUSTOM_PANELS, {})[frontend_url_path] = {
        "webcomponent_name": webcomponent_name,
        "module_url": module_url,
        "sidebar_title": sidebar_title,
        "sidebar_icon": sidebar_icon,
        "require_admin": require_admin,
    }

    # ... and record it as a panel as well, exactly like the real one does. The integration
    # asks `frontend` whether its panel is already registered before registering it again.
    frontend.async_register_built_in_panel(
        hass, component_name="custom", sidebar_title=sidebar_title, sidebar_icon=sidebar_icon,
        frontend_url_path=frontend_url_path, config=config, require_admin=require_admin,
        update=True, config_panel_domain=config_panel_domain)
