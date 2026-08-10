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
  // fixtures of this page: '<id>' plus optional variants '<id>_<something>' (e.g. an open form)
  for (const key of Object.keys(fixtures).filter((name) => name === page.id
                                                || name.startsWith(`${page.id}_`))) {
    states.push([key === page.id ? 'fixture' : key, { ...initialState, ...fixtures[key] }]);
  }

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
    from custom_components.eltako.tools.device_tests import TEST_DESCRIPTORS
    from custom_components.eltako.catalog.help_catalog import build_catalog

    integration_info = {
        'domain': 'eltako', 'name': 'ELTAKO', 'version': '2.2.0',
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
    from custom_components.eltako.config.device_config import get_form_descriptor

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

    # the simulation page: the descriptor of the real backend plus two simulated gateways
    from custom_components.eltako.simulation import core as simulation_core
    from custom_components.eltako.simulation.service import describe_platforms

    def simulated_gateway(gateway_id: int, device_type: str, name: str) -> dict:
        model = simulation_core.SimulationModel()
        gateway = model.add_gateway(gateway_id, device_type, name)
        devices = simulation_core.add_preset_devices(gateway)
        # an actuator with a real wall switch taught into it
        for device in devices:
            if device.is_actuator:
                device.teach_in('FF-AA-BB-CC', 'F6-02-01', 'Real wall switch')
                device.interval = 30
                break
        return {'id': gateway_id, 'name': name, 'device_type': device_type,
                'bus_gateway': gateway.is_bus_gateway, 'base_id': gateway.base_id,
                'description': f'{name} - {device_type} (Id: {gateway_id})',
                'serial_path': f'simulator-{gateway_id}', 'source': 'ui', 'set_up': True,
                'live': True, 'connected': True,
                'devices': [device.describe() for device in devices]}

    real_host = {**simulated_gateway(1, 'fgw14usb', 'FGW14-USB (real)'), 'simulated': False}
    simulation = {
        'gateways': [real_host,
                     simulated_gateway(2, 'fam14', 'Simulated FAM14'),
                     simulated_gateway(3, 'enocean-usb300', 'Simulated USB300')],
        'device_count': 3 * len(simulation_core.DEVICE_PRESETS),
        'platforms': describe_platforms(),
        'presets': simulation_core.describe_gateway_presets({'fam14'}),
        'device_presets': simulation_core.describe_device_presets(),
        'gateway_types': ['fam14', 'enocean-usb300', 'mgw-lan'],
        'active': True,
        'paused': False,
        'repeating_count': 1,
        'interval_suggestions': list(simulation_core.INTERVAL_SUGGESTIONS),
        'interval_range': [simulation_core.MIN_INTERVAL_SECONDS,
                           simulation_core.MAX_INTERVAL_SECONDS],
        'seen_addresses': [{'address': 'FF-AA-BB-CC', 'count': 12,
                            'last_seen': '2026-08-06T10:00:00', 'simulated': False}],
        'sender_eeps': sorted(simulation_core.SENDER_DECODERS),
        'real_gateways': [{'id': 1, 'name': 'FGW14-USB (real)', 'device_type': 'fgw14usb',
                           'base_id': 'FF-AA-80-00', 'hosting': True},
                          {'id': 4, 'name': 'USB300 (real)', 'device_type': 'enocean-usb300',
                           'base_id': 'FF-BB-10-00', 'hosting': False}],
        'hint': 'A simulated gateway needs no hardware.',
    }

    # the devices page with a live RS485 bus - once free, once while an exclusive operation has
    # it (then the scan buttons are replaced by what is going on)
    bus_gateway_info = {**integration_info, 'gateways': [
        {'id': 1, 'name': 'FAM14', 'type': 'fam14', 'device_type': 'fam14',
         'base_id': 'FF-AA-80-00', 'serial_path': '/dev/ttyUSB0', 'connected': True,
         'ha_device_id': 'gw1'}]}
    bus_members = {
        'members': [{'gateway_id': 1, 'bus_address': 1, 'device_class': 'FSR14_4x',
                     'description': 'FSR14/4x - 4 channel relay', 'is_fam': False,
                     'memory_rows_read': 26, 'memory_size': 26, 'taught_in': [
                         {'sensor_id': 'FE-DC-BA-98', 'role': 'sensor', 'channel': 1,
                          'key_function': 51, 'function_group': 2}]}],
        'scans_running': {}, 'busy_with': {},
    }

    # the free send form of the telegram page, opened with a profile whose fields depend on
    # each other (A5-38-08 switches or dims)
    from custom_components.eltako.core.websocket import get_eep_descriptors

    send_form_descriptor = {
        'gateways': [{'id': 1, 'name': 'FAM14', 'base_id': 'FF-AA-80-00'}],
        'eeps': get_eep_descriptors(),
    }

    # the radio comparison page: a report of the real backend with a telegram which two
    # gateways received differently (see tests/test_frontend_radio_page.py for what it renders)
    from tests.test_frontend_radio_page import build_report as build_radio_report

    radio_gateways = {**integration_info, 'gateways': [
        {'id': 1, 'name': 'USB300 hall', 'type': 'enocean-usb300', 'base_id': 'FF-AA-80-00',
         'serial_path': '/dev/ttyUSB0', 'connected': True, 'simulated': False},
        {'id': 2, 'name': 'MGW cellar', 'type': 'mgw-lan', 'base_id': 'FF-BB-10-00',
         'serial_path': '192.168.0.10', 'connected': True, 'simulated': False},
    ]}

    # the log page: a few records of every level, incl. one with a traceback - what the page
    # has to survive is a long message, a child logger and an exception block
    log_entries = [
        {'time': '2026-08-10T14:12:03.481', 'timestamp': 1786633923.481, 'level': 'INFO',
         'levelno': 20, 'logger': 'eltako', 'message': "[Gateway] [Id: 1] Connected to /dev/ttyUSB0"},
        {'time': '2026-08-10T14:12:04.002', 'timestamp': 1786633924.002, 'level': 'DEBUG',
         'levelno': 10, 'logger': 'eltako.telegrams', 'message': "Received 0b 05 70 00 00 00 00 00 ff aa 80 01 30"},
        {'time': '2026-08-10T14:12:09.917', 'timestamp': 1786633929.917, 'level': 'WARNING',
         'levelno': 30, 'logger': 'eltako', 'message': "[Bus Members] Bus scan of gateway 1 was cancelled at position 7."},
        {'time': '2026-08-10T14:12:11.640', 'timestamp': 1786633931.640, 'level': 'ERROR',
         'levelno': 40, 'logger': 'eltako', 'message': "[Gateway] [Id: 1] Serial port is not available",
         'exception': 'Traceback (most recent call last):\n  File "gateway.py", line 1, in send\nSerialException'},
    ]

    return {
        'about': {'integrationInfo': integration_info},
        'logs': {'logs': {'entries': log_entries, 'total': len(log_entries), 'dropped': 12,
                          'buffer_size': 2000, 'level': 'debug', 'effective': 'debug',
                          'options': ['inherit', 'debug', 'info', 'warning', 'error']}},
        # the same page with nothing in the buffer - the branch a fresh installation shows
        'logs_empty': {'logs': {'entries': [], 'total': 0, 'dropped': 0, 'buffer_size': 2000,
                                'level': 'inherit', 'effective': 'warning',
                                'options': ['inherit', 'debug', 'info', 'warning', 'error']}},
        'radio': {'integrationInfo': radio_gateways, 'radioComparison': build_radio_report()},
        # the same page restricted to two gateways, one sender and the telegrams which were
        # received differently - the direct comparison
        'radio_restricted': {'integrationInfo': radio_gateways,
                             'radioComparison': build_radio_report(),
                             'radioView': 'disagreeing', 'radioWindowMs': 500,
                             'radioGateways': ['1', '2'], 'radioSender': 'FE-DC-BA-98'},
        'telegrams_send_form': {
            'integrationInfo': integration_info,
            'sendFormDescriptor': send_form_descriptor,
            'sendForm': {'gatewayId': 1, 'mode': 'eep', 'eep': 'A5-38-08',
                         'senderId': '00-00-B0-01', 'fields': {'command': '2'}, 'raw': '',
                         'result': None, 'error': None},
        },
        'devices': {'integrationInfo': bus_gateway_info, 'configuredDevices': home_devices,
                    'busMembers': bus_members, 'statistics': home_statistics},
        # while a scan or a teach-in has the bus, the page says so instead of offering the buttons
        'devices_bus_busy': {'integrationInfo': bus_gateway_info,
                             'configuredDevices': home_devices, 'statistics': home_statistics,
                             'busMembers': {**bus_members, 'scans_running': {'1': True},
                                            'busy_with': {'1': 'teaching in the senders'}}},
        'simulation': {'integrationInfo': integration_info, 'simulation': simulation},
        # the same page with an open "add device" form and a note of the last telegram
        'simulation_editing': {'integrationInfo': integration_info, 'simulation': simulation,
                               'simulationNewGateway': {},
                               'simulationNewDevice': {'gatewayId': 2, 'platform': 'sensor',
                                                       'eep': 'A5-04-02', 'name': ''},
                               'simulationTeachIn': '2|00-00-00-01',
                               'simulationNotes': {'2|00-00-00-05': {'style': 'ok',
                                                                     'text': 'Telegram sent'}},
                               'simulationMessage': 'Created 1 gateway.'},
        # the paused simulation shows its banner instead of sending anything
        'simulation_off': {'integrationInfo': integration_info,
                           'simulation': {**simulation, 'active': False, 'paused': True,
                                          'repeating_count': 0}},
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

        for page_id in ('about', 'help', 'tests', 'simulation', 'devices', 'radio', 'logs'):
            self.assertIn(f'{page_id}:fixture', report['rendered'])
        self.assertIn('radio:radio_restricted', report['rendered'])
        self.assertIn('logs:logs_empty', report['rendered'])
        # the simulation page with an open form and a triggered telegram, and the devices page
        # while an exclusive operation has the bus
        for variant in ('simulation_editing', 'simulation_off'):
            self.assertIn(f'simulation:{variant}', report['rendered'])
        self.assertIn('devices:devices_bus_busy', report['rendered'])
        self.assertIn('telegrams:telegrams_send_form', report['rendered'])
