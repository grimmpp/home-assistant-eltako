"""Renders every page of the web ui with node and checks the result.

The frontend has no build step and no javascript test runner, so a syntax error, a renamed
import or a template which reads a field that does not exist is only noticed when the page is
opened in a browser. This test renders every page module twice - once with an empty state (the
loading branch, which is what a user sees first) and once with a realistic payload built from
the *real* backend (the help catalog and the test descriptors come from python) - and fails on

* a module which cannot be imported (syntax error, wrong import path)
* a render() which throws
* `undefined` / `NaN` / an unresolved `${...}` in the produced html
* a page without the fields the panel needs (id, title, render)

Node is only used as a javascript engine; it is skipped when node is not installed.
"""
import json
import os
import shutil
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(__file__))
FRONTEND = os.path.join(REPO, 'custom_components', 'eltako', 'frontend')
NODE = shutil.which('node')

HARNESS = r"""
import { readFileSync, readdirSync } from 'fs';

const [frontendDir, fixturesPath] = process.argv.slice(2);
const fixtures = JSON.parse(readFileSync(fixturesPath, 'utf-8'));

/**
 * The initial state of the panel, read out of eltako-panel.js.
 *
 * That is the baseline every page can rely on (e.g. `telegrams: []`), so the "empty" render has
 * to use exactly it - not an empty object, which would demand null checks the panel makes
 * unnecessary. Taking it from the source keeps both in sync automatically.
 */
function initialStateOfThePanel() {
  const source = readFileSync(`${frontendDir}/eltako-panel.js`, 'utf-8');
  const start = source.indexOf('this.state = {');
  if (start < 0) throw new Error('eltako-panel.js does not initialize this.state');
  let depth = 0;
  let end = -1;
  for (let index = source.indexOf('{', start); index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    else if (source[index] === '}') {
      depth -= 1;
      if (depth === 0) { end = index; break; }
    }
  }
  if (end < 0) throw new Error('the state literal of eltako-panel.js is not balanced');
  // the literal contains only values and comments
  return new Function(`return ${source.slice(source.indexOf('{', start), end + 1)};`)();
}

const initialState = initialStateOfThePanel();

const noop = () => {};
const stubApi = {
  call: async () => null,
  lastError: null,
  hass: { connection: { subscribeMessage: async () => noop } },
};

function makeCtx(state) {
  return {
    state,
    api: stubApi,
    root: null,
    requestRender: noop,
    requestContentRender: noop,
    loadIntegrationInfo: async () => {},
    loadLogInfo: async () => {},
  };
}

const problems = [];
const rendered = [];

for (const file of readdirSync(`${frontendDir}/pages`).filter((name) => name.endsWith('.js')).sort()) {
  let page;
  try {
    ({ page } = await import(`${frontendDir}/pages/${file}`));
  } catch (error) {
    problems.push(`${file}: cannot be imported - ${error.message}`);
    continue;
  }
  if (!page || !page.id || !page.title || typeof page.render !== 'function') {
    problems.push(`${file}: does not export a page with id, title and render()`);
    continue;
  }

  // 1) nothing loaded yet: this is what the page shows first
  // 2) the fixture of this page (if there is one): the populated view
  const states = [['empty', initialState]];
  if (fixtures[page.id]) states.push(['fixture', { ...initialState, ...fixtures[page.id] }]);

  for (const [label, state] of states) {
    let html;
    try {
      html = page.render(makeCtx(structuredClone(state)));
    } catch (error) {
      problems.push(`${file} (${label}): render() throws - ${error.message}`);
      continue;
    }
    if (typeof html !== 'string' || !html.trim()) {
      problems.push(`${file} (${label}): render() returned no html`);
      continue;
    }
    for (const marker of ['undefined', 'NaN', '${']) {
      if (html.includes(marker)) {
        const at = html.indexOf(marker);
        problems.push(`${file} (${label}): '${marker}' in the html near ` +
                      JSON.stringify(html.slice(Math.max(0, at - 60), at + 40)));
      }
    }
    rendered.push(`${page.id}:${label}`);
  }
}

console.log(JSON.stringify({ problems, rendered }, null, 1));
"""


def build_fixtures() -> dict:
    """Realistic state per page - as far as possible from the real backend."""
    from custom_components.eltako.device_tests import TEST_DESCRIPTORS
    from custom_components.eltako.help_catalog import build_catalog

    integration_info = {
        'domain': 'eltako', 'name': 'Eltako', 'version': '2.2.0',
        'home_assistant_version': '2026.7.2', 'iot_class': 'local_push',
        'issue_tracker': 'https://example.invalid/issues',
        'requirements': ['eltako14bus==0.0.82', 'esp2-gateway-adapter==0.2.21'],
        'general_settings': {
            'enable_frontend': True, 'enable_test_page': True, 'plug_and_play': True,
            'log_enocean_telegrams': True, 'timeseries_enabled': False,
            'enable_teach_in_buttons': False, 'fast_status_change': False,
        },
        'telegram_logging_enabled': True,
        'gateways': [{'id': 1, 'name': 'FAM14', 'device_type': 'fam14', 'base_id': 'FF-AA-80-00',
                      'serial_path': '/dev/ttyUSB0', 'connected': True}],
        'entities': {'device_count': 73, 'entity_count': 261,
                     'count_by_platform': {'light': 12, 'cover': 5, 'sensor': 40}},
    }

    device_tests_info = {
        'tests': TEST_DESCRIPTORS,
        'gateways': [{'id': 1, 'name': 'FAM14', 'connected': True, 'wired': True,
                      'device_type': 'fam14'},
                     {'id': 2, 'name': 'FGW14-USB', 'connected': True, 'wired': True,
                      'device_type': 'fgw14usb'}],
        'covers': {'1': {'default_sequence': 'up:25,pause:2,down:25', 'covers': [
            {'id': '00-00-00-06', 'name': 'Cover', 'sender_id': '00-00-B0-06',
             'time_opens': 25, 'time_closes': 24}]}},
        'actuators': {'1': {'actuators': [
            {'id': '00-00-00-01', 'name': 'Relay', 'platform': 'switch', 'eep': 'M5-38-08',
             'sender_id': '00-00-B0-01', 'sender_eep': 'A5-38-08'},
            {'id': '00-00-00-03', 'name': 'Lamp without sender', 'platform': 'light',
             'eep': 'M5-38-08', 'sender_id': '', 'sender_eep': ''}]}},
        'running': False, 'test': None,
        'log': [{'line': 'Checking the configuration - no telegram is sent.', 'style': 'info'}],
        'result': {
            'test': 'config', 'success': False,
            'counts': {'error': 1, 'warning': 1, 'info': 1}, 'gateway_count': 1,
            'device_count': 3,
            'findings': [
                {'severity': 'error', 'check': 'sender_missing', 'gateway_id': 1,
                 'device': '00-00-00-03', 'name': 'Lamp without sender',
                 'message': 'No sender configured.'},
                {'severity': 'warning', 'check': 'sender_not_taught_in', 'gateway_id': 1,
                 'device': '00-00-00-01', 'name': 'Relay',
                 'message': 'Sender 00-00-B0-01 is not in the memory of the actuator.'},
                {'severity': 'info', 'check': 'cover_times', 'gateway_id': 1,
                 'device': '00-00-00-06', 'name': 'Cover', 'message': 'No travel times.'},
            ],
        },
    }

    # the simple device page of the user mode: configured devices, the form descriptor of the
    # real backend and an address which is not configured yet
    from custom_components.eltako.device_config import get_form_descriptor

    device_form = get_form_descriptor()
    device_form['areas'] = ['Kitchen', 'Living room']
    device_form['gateways'] = [{'id': 1, 'name': 'FAM14', 'base_id': 'FF-AA-80-00',
                                'config_entry_id': 'abc'}]
    home_devices = [
        {'gateway_id': 1, 'gateway_name': 'FAM14', 'gateway_set_up': True, 'platform': 'light',
         'source': 'ui', 'editable': True, 'address': '00-00-00-01',
         'external_address': 'FF-AA-80-01', 'ha_device_id': 'dev1', 'name': 'Ceiling light',
         'eep': 'M5-38-08', 'area': 'Kitchen', 'sender': {'id': '00-00-B0-01', 'eep': 'A5-38-08'},
         'activity': {'count': 42, 'telegrams_per_day': 12, 'last_seen': '2026-08-06T10:00:00',
                      'silent_since_seconds': 120, 'seen_in_this_session': True},
         'sender_activity': None,
         'config': {'id': '00-00-00-01', 'eep': 'M5-38-08', 'name': 'Ceiling light',
                    'area': 'Kitchen', 'sender': {'id': '00-00-B0-01', 'eep': 'A5-38-08'}}},
        {'gateway_id': 1, 'gateway_name': 'FAM14', 'gateway_set_up': True,
         'platform': 'binary_sensor', 'source': 'yaml', 'editable': False,
         'address': 'FE-DC-BA-98', 'external_address': 'FE-DC-BA-98', 'ha_device_id': None,
         'name': 'Rocker switch', 'eep': 'F6-02-01', 'area': None, 'sender': None,
         'activity': None, 'sender_activity': None,
         'config': {'id': 'FE-DC-BA-98', 'eep': 'F6-02-01', 'name': 'Rocker switch'}},
    ]
    home_statistics = {
        'devices': [{'address': 'FF-AA-80-01', 'local_address': '00-00-00-01', 'known': True,
                     'name': 'Ceiling light', 'eep': 'M5-38-08', 'entity_ids': ['light.ceiling_light'],
                     'count': 42}],
        'unknown_devices': [{'address': '01-23-45-67', 'count': 7, 'last_seen': '2026-08-06T09:00:00',
                             'msg_types': {'4BS': 7}, 'gateway_ids': [1], 'yaml': '',
                             'suggestions': [], 'suggested': {'eep': 'A5-02-05', 'platform': 'sensor',
                                                              'hw_type': 'FTF55D', 'confidence': 'likely'}}],
        'summary': {},
    }

    return {
        'about': {'integrationInfo': integration_info},
        'home': {'integrationInfo': integration_info, 'configuredDevices': home_devices,
                 'deviceForm': device_form, 'statistics': home_statistics},
        'help': {'helpCatalog': build_catalog(), 'helpFilter': ''},
        'tests': {'integrationInfo': integration_info, 'deviceTests': device_tests_info},
    }


@unittest.skipUnless(NODE, 'node is not installed - the pages cannot be rendered here')
class TestEveryPageRenders(unittest.TestCase):
    """One test which renders everything: the report names every page which fails."""

    @classmethod
    def setUpClass(cls):
        import tempfile

        cls.tmp = tempfile.TemporaryDirectory()
        harness = os.path.join(cls.tmp.name, 'render.mjs')
        fixtures = os.path.join(cls.tmp.name, 'fixtures.json')
        with open(harness, 'w', encoding='utf-8') as handle:
            handle.write(HARNESS)
        with open(fixtures, 'w', encoding='utf-8') as handle:
            json.dump(build_fixtures(), handle, default=str)

        cls.process = subprocess.run(
            [NODE, harness, FRONTEND, fixtures],
            capture_output=True, text=True, timeout=120, cwd=REPO)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def report(self) -> dict:
        self.assertEqual(0, self.process.returncode,
                         msg=f"node failed:\n{self.process.stderr[-2000:]}")
        return json.loads(self.process.stdout)

    def test_no_page_has_a_problem(self):
        report = self.report()

        self.assertEqual([], report['problems'], msg="\n".join(report['problems']))

    def test_every_page_was_rendered(self):
        report = self.report()
        pages = {entry.split(':')[0] for entry in report['rendered']}

        expected = {name[:-3] for name in os.listdir(os.path.join(FRONTEND, 'pages'))
                    if name.endswith('.js')}
        # devices_config is the page id 'devices', devices.js is 'statistics' - compare counts
        self.assertEqual(len(expected), len(pages), msg=report['rendered'])

    def test_the_populated_views_were_rendered_too(self):
        """Without a fixture only the loading branch would be checked."""
        report = self.report()

        for page_id in ('about', 'help', 'tests'):
            self.assertIn(f'{page_id}:fixture', report['rendered'])
