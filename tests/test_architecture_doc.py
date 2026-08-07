"""The architecture documentation must keep describing the code that exists.

docs/architecture/readme.md is the entry point for anyone new to this repository, so a wrong
statement in it costs more than a missing one. Prose cannot be verified automatically, but the
things it points *at* can: every module, symbol, signal, storage key, platform, page and link it
names is checked here against the code. Rename a module without touching the document and this
fails.

What it deliberately does not check: counts and line numbers of the module table. Those drift
with every commit and are approximate by intent.
"""

import os
import re
from unittest import TestCase

ROOT = os.path.dirname(os.path.dirname(__file__))
DOC_PATH = os.path.join(ROOT, 'docs', 'architecture', 'readme.md')


class ArchitectureDocTestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        with open(DOC_PATH, encoding='utf-8') as handle:
            cls.doc = handle.read()


class TestItExistsAndIsReachable(ArchitectureDocTestCase):

    def test_the_document_is_there(self):
        self.assertTrue(os.path.isfile(DOC_PATH))

    def test_the_documentation_index_links_it(self):
        with open(os.path.join(ROOT, 'docs', 'readme.md'), encoding='utf-8') as handle:
            index = handle.read()

        self.assertIn('architecture/readme.md', index)

    def test_the_help_page_offers_it(self):
        """The web ui lists the docs from the generated index - it has to be in there."""
        from custom_components.eltako.catalog import help_catalog

        paths = {document['path'] for document in help_catalog.get_documentation()}

        self.assertIn('docs/architecture/readme.md', paths)


class TestEveryLinkResolves(ArchitectureDocTestCase):

    def test_relative_links_point_at_existing_files(self):
        broken = []
        for _, target in re.findall(r'\[([^\]]+)\]\((\.\./[^)#]+)(?:#[^)]*)?\)', self.doc):
            path = os.path.normpath(os.path.join(ROOT, 'docs', 'architecture', target))
            if not os.path.exists(path):
                broken.append(target)

        self.assertEqual([], broken)

    def test_line_anchors_are_inside_the_file(self):
        """A #L42 which is past the end of the file points nowhere."""
        problems = []
        for target, line in re.findall(r'\((\.\./\.\./[^)#]+)#L(\d+)\)', self.doc):
            path = os.path.normpath(os.path.join(ROOT, 'docs', 'architecture', target))
            with open(path, encoding='utf-8') as handle:
                total = len(handle.read().splitlines())
            if int(line) > total:
                problems.append(f'{target}#L{line} (file has {total} lines)')

        self.assertEqual([], problems)


class TestEveryNamedThingExists(ArchitectureDocTestCase):

    SEARCH_DIRS = ('custom_components/eltako', 'tests', 'eltako_standalone', 'eltako_standalone/tests')

    def test_named_modules_exist(self):
        """`core/gateway.py` as well as `gateway.py` - a path in the document must resolve."""
        missing = []
        for name in sorted(set(re.findall(r'`([a-z_]+(?:/[a-z_]+)*\.py)`', self.doc))):
            if not any(os.path.isfile(os.path.join(ROOT, directory, name)) for directory in self.SEARCH_DIRS):
                missing.append(name)

        self.assertEqual([], missing)

    def test_the_subpackages_are_described(self):
        """Whoever adds a subpackage has to say in the document what belongs in it."""
        package = os.path.join(ROOT, 'custom_components', 'eltako')
        subpackages = sorted(name for name in os.listdir(package)
                             if os.path.isfile(os.path.join(package, name, '__init__.py')))

        self.assertGreaterEqual(len(subpackages), 4, msg=str(subpackages))
        for name in subpackages:
            self.assertIn(f'{name}/', self.doc, msg=f'{name}/ is not described in the document')

    def test_every_module_is_in_a_documented_place(self):
        """A module at the top level either is one Home Assistant loads by name, or it is lost."""
        package = os.path.join(ROOT, 'custom_components', 'eltako')
        from custom_components.eltako.const import PLATFORMS

        allowed = {'__init__.py', 'const.py', 'config_flow.py', 'datetime.py'}
        allowed |= {f'{platform}.py' for platform in PLATFORMS}

        unexpected = [name for name in sorted(os.listdir(package))
                      if name.endswith('.py') and name not in allowed]

        self.assertEqual([], unexpected,
                         msg='these belong in a subpackage - see "The layout" in the document')

    def test_named_symbols_exist_where_claimed(self):
        expected = {
            'custom_components/eltako/core/gateway.py': [
                'EnOceanGateway', '_handle_received_message', '_callback_send_message_to_serial_bus',
                '_callback_receive_message_from_serial_bus', 'query_for_base_id_and_version',
                '_record_telegram'],
            'custom_components/eltako/core/entity.py': ['EltakoEntity', 'value_changed'],
            'custom_components/eltako/core/integration.py': [
                'EltakoFrontendView', 'async_setup_entry', 'async_reload_entry'],
            'custom_components/eltako/const.py': [
                'ELTAKO_GLOBAL_EVENT_BUS_ID', 'SIGNAL_RECEIVE_MESSAGE', 'GatewayDeviceType', 'PLATFORMS'],
            'custom_components/eltako/config/config_helpers.py': [
                'get_bus_event_type', 'DEFAULT_GENERAL_SETTINGS', 'async_get_home_assistant_config'],
            'custom_components/eltako/config/general_settings.py': ['SETTING_DESCRIPTORS', 'LOCKED_SETTINGS'],
            'custom_components/eltako/catalog/device_catalog.py': ['DEVICE_CATALOG'],
            'custom_components/eltako/tools/device_tests.py': ['is_wired'],
            'custom_components/eltako/config/gateway_config.py': ['async_load_ui_gateways'],
            'custom_components/eltako/observation/bus_members.py': ['async_setup_registry'],
            'custom_components/eltako/observation/device_activity.py': ['async_setup_activity_tracker'],
            'custom_components/eltako/frontend/lib/form.js': ['renderFields', 'readFields'],
        }
        missing = []
        for path, symbols in expected.items():
            with open(os.path.join(ROOT, path), encoding='utf-8') as handle:
                source = handle.read()
            for symbol in symbols:
                if symbol not in self.doc:
                    missing.append(f'{symbol} is not mentioned in the document anymore')
                elif symbol not in source:
                    missing.append(f'{symbol} is gone from {path}')

        self.assertEqual([], missing)

    def test_the_storage_keys_are_the_real_ones(self):
        from custom_components.eltako.observation import bus_members, device_activity
        from custom_components.eltako.config import gateway_config, general_settings

        for module in (bus_members, device_activity, gateway_config, general_settings):
            self.assertIn(module.STORAGE_KEY, self.doc,
                          msg=f'{module.__name__}.STORAGE_KEY changed')

    def test_every_platform_is_listed(self):
        from custom_components.eltako.const import PLATFORMS

        for platform in PLATFORMS:
            self.assertIn(f'`{platform}`', self.doc, msg=str(platform))

    def test_the_frontend_layout_is_described_correctly(self):
        frontend = os.path.join(ROOT, 'custom_components', 'eltako', 'frontend')

        for name in ('eltako-panel.js', 'lib/api.js', 'lib/form.js', 'lib/styles.js', 'lib/utils.js'):
            self.assertIn(os.path.basename(name), self.doc, msg=name)
            self.assertTrue(os.path.isfile(os.path.join(frontend, name)), msg=name)

    def test_the_standalone_layout_is_described_correctly(self):
        for name in ('runtime.py', 'server.py', 'entity_api.py', 'cli.py'):
            self.assertIn(name, self.doc, msg=name)
            self.assertTrue(os.path.isfile(os.path.join(ROOT, 'eltako_standalone', name)), msg=name)

        self.assertTrue(os.path.isdir(os.path.join(ROOT, 'eltako_standalone', 'hass_shim', 'homeassistant')))


class TestTheDiagramsRender(ArchitectureDocTestCase):
    """GitHub renders mermaid natively - a syntax slip shows up as a broken block."""

    def _blocks(self):
        return re.findall(r'```mermaid\n(.*?)```', self.doc, re.DOTALL)

    def test_there_are_diagrams(self):
        self.assertGreaterEqual(len(self._blocks()), 2)

    def test_each_declares_its_type(self):
        for block in self._blocks():
            first = block.strip().splitlines()[0].strip()
            self.assertRegex(first, r'^(flowchart|sequenceDiagram|graph|classDiagram)')

    def test_no_angle_bracket_placeholders(self):
        """`<gw_id>` inside a label is parsed as html and swallows the rest of it."""
        for block in self._blocks():
            found = re.findall(r'<(?!br\s*/?>)[a-zA-Z_][^>]*>', block)
            self.assertEqual([], found, msg=f'html-like text in a diagram: {found}')

    def test_the_fences_are_balanced(self):
        self.assertEqual(self.doc.count('```mermaid'), len(self._blocks()))
        self.assertEqual(0, self.doc.count('```') % 2)


class TestTheStartupOrderMatchesTheCode(ArchitectureDocTestCase):
    """The document claims the order of async_setup() is load-bearing - so it must be current."""

    def test_the_steps_appear_in_the_documented_order(self):
        import inspect

        from custom_components.eltako.core import integration

        source = inspect.getsource(integration.async_setup)
        steps = ['async_load_ui_gateways', 'async_get_home_assistant_config',
                 'async_load_overrides', 'register_websockets', 'async_setup_registry',
                 'async_setup_activity_tracker', 'async_setup_telegram_logger',
                 'async_setup_detection', 'async_register_frontend']

        positions = []
        for step in steps:
            index = source.find(step)
            self.assertNotEqual(-1, index, msg=f'{step} is no longer part of async_setup()')
            positions.append(index)

        self.assertEqual(sorted(positions), positions,
                         msg='async_setup() runs its steps in a different order than documented')

    def test_the_documented_steps_are_all_named(self):
        for step in ('async_load_ui_gateways', 'async_load_overrides', 'async_setup_registry',
                     'async_register_frontend'):
            self.assertIn(step, self.doc, msg=step)
