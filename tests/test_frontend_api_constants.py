"""The websocket commands the web ui calls have to exist in the backend.

The frontend is plain javascript without a build step, so a renamed command is only noticed
at runtime - and then only on the page which uses it. This check compares the command names of
`frontend/lib/api.js` with the names the backend registers (const.py plus the modules which
define their command name themselves).
"""
import os
import re
import unittest
from unittest import TestCase

from custom_components.eltako import const

COMPONENT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             'custom_components', 'eltako')
API_JS = os.path.join(COMPONENT_DIR, 'frontend', 'lib', 'api.js')


def _api_js_commands() -> dict[str, str]:
    """{name in the WS object: command string} of frontend/lib/api.js."""
    with open(API_JS, encoding='utf-8') as handle:
        content = handle.read()
    body = content.split('export const WS = {', 1)[1].split('};', 1)[0]
    return dict(re.findall(r'(\w+)\s*:\s*"([^"]+)"', body))


def _backend_commands() -> set[str]:
    """Every command string the backend knows: the WS_* constants plus local definitions."""
    commands = {value for name, value in vars(const).items()
                if name.startswith('WS_') and isinstance(value, str)}

    # a few modules define their command name themselves (e.g. config_import)
    for root, _dirs, names in os.walk(COMPONENT_DIR):
        if 'frontend' in root:
            continue
        for name in names:
            if not name.endswith('.py'):
                continue
            with open(os.path.join(root, name), encoding='utf-8') as handle:
                content = handle.read()
            commands.update(re.findall(r'WS_\w+\s*:\s*str\s*=\s*"([^"]+)"', content))
            commands.update(re.findall(r"vol\.Required\('type'\)\s*:\s*'([^']+)'", content))
            commands.update(re.findall(r"'type'\s*:\s*'(eltako/[^']+)'", content))
    return commands


class TestFrontendApiConstants(TestCase):

    def test_every_command_of_the_web_ui_exists_in_the_backend(self):
        backend = _backend_commands()
        unknown = {name: command for name, command in _api_js_commands().items()
                   if command not in backend}

        self.assertEqual(unknown, {},
                         "api.js calls websocket commands which the backend does not define")

    def test_the_commands_of_this_change_are_present(self):
        commands = set(_api_js_commands().values())

        for command in [const.WS_PLUG_AND_PLAY_STATUS, const.WS_PLUG_AND_PLAY_RUN,
                        const.WS_GATEWAY_UPDATE, const.WS_DEVICE_UPDATE]:
            self.assertIn(command, commands)

    def test_every_command_name_is_unique(self):
        commands = list(_api_js_commands().values())

        self.assertEqual(len(commands), len(set(commands)))


if __name__ == '__main__':
    unittest.main()
