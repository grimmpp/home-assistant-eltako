"""The teach-in popup of the simple view: which gateway switches a device, and how it learns it.

An actuator only reacts to sender addresses it knows, and a transceiver only transmits addresses
out of its own base id range - both halves have to agree. The popup behind the **teach-in** button
of a device card does both in one step (backend: `eltako/devices/sender_gateway`):

* a device on the RS485 bus gets the address **written into its memory** - only a FAM14 can write;
* a wireless device **learns it from a telegram** - it is put into its learn mode by hand and the
  teach-in telegram goes out through the chosen gateway;
* and in both cases the address becomes the sender of that device in Home Assistant.

It is a popup and not a control on the card: the current gateway, the sender address and the
sentence which says what the button does are what makes it usable, and none of that fits next to
the state of a device. The card carries the button only where the choice is real - a sensor is not
commanded, a device out of `configuration.yaml` is changed there.

The page is rendered into the dom stub of tests/frontend_dom_stub.py and the test presses the
buttons. Node is only used as a javascript engine; the test is skipped when node is not installed.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import TestCase

from tests.frontend_dom_stub import DOM_STUB

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(REPO, 'custom_components', 'eltako', 'frontend')
NODE = shutil.which('node')

SCRIPT = DOM_STUB + r"""
const { page } = await import(`${process.argv[2]}/pages/home.js`);

const True_ = true, False_ = false;
globalThis.window = { eltakoStandalone: False_, dispatchEvent: () => {} };
globalThis.CustomEvent = class { constructor(type) { this.type = type; } };
globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);
const confirmed = [];
globalThis.confirm = (question) => { confirmed.push(question); return True_; };
const alerted = [];
globalThis.alert = (message) => alerted.push(message);

const GATEWAYS = [
  { id: 1, name: 'FAM14', type: 'fam14', base_id: 'FF-AA-80-00', connected: True_,
    serial_path: '/dev/ttyUSB0', simulated: False_ },
  { id: 2, name: 'FAM-USB', type: 'fam-usb', base_id: 'FF-C0-02-00', connected: True_,
    serial_path: '/dev/ttyUSB1', simulated: False_ },
  // sits on the bus and has no base id range of its own - it can switch nothing
  { id: 3, name: 'FGW14-USB', type: 'fgw14usb', base_id: null, connected: True_,
    serial_path: '/dev/ttyUSB2', simulated: False_ },
];

const device = (overrides = {}) => ({
  gateway_id: 1, gateway_name: 'FAM14', gateway_set_up: True_, platform: 'light', source: 'ui',
  editable: True_, address: '00-00-00-05', external_address: null, ha_device_id: null,
  name: 'Kitchen light', eep: 'M5-38-08', area: 'Kitchen',
  sender: { id: '00-00-B0-05', eep: 'A5-38-08' }, activity: null, sender_activity: null,
  entity_ids: [], config: {}, simulated: False_, ...overrides,
});

const DEVICES = [
  device(),
  device({ address: 'FE-DC-BA-98', name: 'Radio dimmer', gateway_id: 2, gateway_name: 'FAM-USB',
           sender: { id: 'FF-C0-02-09', eep: 'A5-38-08' } }),
  // no sender: nothing switches a sensor, so there is nothing to teach in
  device({ address: '00-00-00-07', name: 'Button', platform: 'binary_sensor', sender: null }),
  // out of configuration.yaml: it is changed there
  device({ address: '00-00-00-08', name: 'Yaml light', source: 'yaml', editable: False_ }),
];

function makeContext() {
  const ctx = {
    hass: { states: {} },
    state: {
      integrationInfo: { gateways: GATEWAYS, gateways_not_set_up: [] },
      configuredDevices: DEVICES,
      statistics: { devices: [], unknown_devices: [] },
      simpleFilter: '', simpleEditor: null, simpleDetails: null, simpleTeachIn: null,
      plugAndPlay: null, deviceForm: null,
    },
    api: {
      calls: [],
      lastError: null,
      async call(type, payload) {
        this.calls.push({ type, payload });
        if (type === 'eltako/devices/sender_gateway') {
          return { target_gateway_id: payload.target_gateway_id, target_gateway_name: 'FAM-USB',
                   base_id: 'FF-C0-02-00', updated: 1, failed: 0,
                   buses: [{ gateway_id: 1, gateway_name: 'FAM14', results: [], skipped: [],
                             updated: [{ address: payload.address, sender_id: 'FF-C0-02-05',
                                         previous_sender_id: '00-00-B0-05' }] }] };
        }
        if (type === 'eltako/devices/list') return { devices: DEVICES };
        return {};
      },
    },
    root: null,
    requestRender() {}, requestContentRender() {},
    setMode: () => {},
    async loadIntegrationInfo() {}, async loadStatistics() {},
  };
  ctx.api.call = ctx.api.call.bind(ctx.api);
  return ctx;
}

function show(ctx) {
  const root = parseHtml(page.render(ctx));
  root.host = { dispatchEvent: () => {} };
  ctx.root = root;
  page.afterRender(ctx, root);
  return root;
}

const ctx = makeContext();
let root = show(ctx);

const cardOf = (address) => root.querySelectorAll('.device-card')
  .find((card) => card.dataset.address === address);
const teachInButtonOf = (address) => cardOf(address).querySelector('button[data-simple-teach-in]');
const optionsOf = (select) => select.querySelectorAll('option').map((option) => ({
  value: option.getAttribute('value'), label: option.textContent.trim(),
  selected: option.hasAttribute('selected'),
}));

const cards = {
  bus: !!teachInButtonOf('00-00-00-05'),
  radio: !!teachInButtonOf('FE-DC-BA-98'),
  sensor: !!teachInButtonOf('00-00-00-07'),
  yaml: !!teachInButtonOf('00-00-00-08'),
  // the picker itself is gone from the card - it lives in the popup now
  pickers: root.querySelectorAll('select[data-sender-gateway]').length,
};

/* ------------------------------------------------- the popup of a bus device */

await teachInButtonOf('00-00-00-05').click();
root = show(ctx);

const busPopup = {
  rows: root.querySelectorAll('.meta-grid dt').map((dt, index) =>
    `${dt.textContent.trim()}: ${root.querySelectorAll('.meta-grid dd')[index].textContent.trim()}`),
  options: optionsOf(root.getElementById('teach-in-gateway')),
  sendLabel: root.getElementById('teach-in-send').textContent.trim(),
  help: root.querySelector('.meta-section .field-help').textContent.replace(/\s+/g, ' ').trim(),
};

// pick another gateway and send: that is one call, and only after the confirmation
const select = root.getElementById('teach-in-gateway');
await select.dispatch('change', '2');
await root.getElementById('teach-in-send').click();
const busCall = ctx.api.calls.find((call) => call.type === 'eltako/devices/sender_gateway');
const afterSending = {
  closed: ctx.state.simpleTeachIn === null,
  question: confirmed[confirmed.length - 1].replace(/\s+/g, ' ').trim(),
  answer: alerted[alerted.length - 1].split('\n')[0],
};

/* --------------------------------------------- the popup of a wireless device */

const radioCtx = makeContext();
let radioRoot = show(radioCtx);
await radioRoot.querySelectorAll('.device-card')
  .find((card) => card.dataset.address === 'FE-DC-BA-98')
  .querySelector('button[data-simple-teach-in]').click();
radioRoot = show(radioCtx);

const radioPopup = {
  rows: radioRoot.querySelectorAll('.meta-grid dt').map((dt, index) =>
    `${dt.textContent.trim()}: ${radioRoot.querySelectorAll('.meta-grid dd')[index].textContent.trim()}`),
  options: optionsOf(radioRoot.getElementById('teach-in-gateway')),
  sendLabel: radioRoot.getElementById('teach-in-send').textContent.trim(),
  help: radioRoot.querySelector('.meta-section .field-help').textContent.replace(/\s+/g, ' ').trim(),
};

await radioRoot.getElementById('teach-in-send').click();
const radioCall = radioCtx.api.calls.find((call) => call.type === 'eltako/devices/sender_gateway');
const radioQuestion = confirmed[confirmed.length - 1].replace(/\s+/g, ' ').trim();

/* ------------------------------------------------------------------ closing */

const closeCtx = makeContext();
let closeRoot = show(closeCtx);
await closeRoot.querySelectorAll('.device-card')
  .find((card) => card.dataset.address === '00-00-00-05')
  .querySelector('button[data-simple-teach-in]').click();
closeRoot = show(closeCtx);
const openedBeforeClosing = !!closeRoot.getElementById('teach-in-send');
await closeRoot.getElementById('details-done').click();

// the details popup and the teach-in popup are the same markup - only one may be open
const bothCtx = makeContext();
let bothRoot = show(bothCtx);
await bothRoot.querySelectorAll('.device-card')
  .find((card) => card.dataset.address === '00-00-00-05')
  .querySelector('button[data-simple-teach-in]').click();
bothRoot = show(bothCtx);
await bothRoot.querySelector('button[data-simple-details]').click();

console.log(JSON.stringify({
  cards,
  busPopup,
  busCall,
  afterSending,
  radioPopup,
  radioCall,
  radioQuestion,
  openedBeforeClosing,
  closedAgain: closeCtx.state.simpleTeachIn === null,
  detailsReplacesTeachIn: bothCtx.state.simpleTeachIn === null && !!bothCtx.state.simpleDetails,
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestTheTeachInPopupOfTheSimpleView(TestCase):

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'teach_in_popup.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(SCRIPT)
            result = subprocess.run([NODE, path, FRONTEND],
                                    capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    ### the button on the card

    def test_only_a_device_which_is_switched_carries_the_button(self):
        """A sensor is not commanded and a yaml device is changed in the yaml - a button there
        would be a promise the popup cannot keep."""
        cards = self.result['cards']

        self.assertTrue(cards['bus'])
        self.assertTrue(cards['radio'])
        self.assertFalse(cards['sensor'])
        self.assertFalse(cards['yaml'])

    def test_the_card_itself_carries_no_dropdown_anymore(self):
        self.assertEqual(0, self.result['cards']['pickers'])

    ### what the popup says

    def test_it_names_the_current_gateway_and_the_sender_address(self):
        rows = self.result['busPopup']['rows']

        self.assertIn('Device address: 00-00-00-05', rows)
        self.assertIn('Switched by: FAM14', rows)
        self.assertIn('Sender address: 00-00-B0-05', rows)

    def test_a_bus_device_can_stay_on_the_bus_or_move_to_a_wireless_gateway(self):
        options = self.result['busPopup']['options']

        self.assertEqual(['FAM14 · bus', 'FAM-USB'], [option['label'] for option in options])
        # the FGW14-USB sits on the bus and has no base id range to hand out
        self.assertEqual(['1', '2'], [option['value'] for option in options])
        # the current one is preselected: this device sends with a local address
        self.assertEqual(['FAM14 · bus'], [o['label'] for o in options if o['selected']])

    def test_a_wireless_device_is_only_offered_the_gateways_which_transmit(self):
        options = self.result['radioPopup']['options']

        self.assertEqual(['FAM-USB'], [option['label'] for option in options])
        self.assertEqual(['FAM-USB'], [o['label'] for o in options if o['selected']])
        self.assertIn('Sender address: FF-C0-02-09', self.result['radioPopup']['rows'])

    def test_the_button_says_what_it_does(self):
        """Writing a memory and sending a telegram are different things, and only one of them
        needs somebody standing at the device."""
        self.assertEqual('Write into the device', self.result['busPopup']['sendLabel'])
        self.assertEqual('Send teach-in', self.result['radioPopup']['sendLabel'])

        self.assertIn('only a FAM14 can write', self.result['busPopup']['help'])
        self.assertIn('teach-in mode', self.result['radioPopup']['help'])

    ### what it does

    def test_sending_asks_first_and_then_writes_the_chosen_gateway(self):
        self.assertEqual({'target_gateway_id': 2, 'gateway_id': 1, 'address': '00-00-00-05'},
                         self.result['busCall']['payload'])
        self.assertIn('Let "FAM-USB" switch "Kitchen light"?', self.result['afterSending']['question'])

    def test_a_wireless_device_is_told_to_be_in_learn_mode(self):
        self.assertEqual({'target_gateway_id': 2, 'gateway_id': 2, 'address': 'FE-DC-BA-98'},
                         self.result['radioCall']['payload'])
        self.assertIn('teach-in mode now', self.result['radioQuestion'])

    def test_the_result_is_shown_and_the_popup_closes(self):
        self.assertIn('FAM-USB', self.result['afterSending']['answer'])
        self.assertTrue(self.result['afterSending']['closed'])

    def test_it_can_be_closed_without_doing_anything(self):
        self.assertTrue(self.result['openedBeforeClosing'])
        self.assertTrue(self.result['closedAgain'])

    def test_only_one_popup_is_open_at_a_time(self):
        self.assertTrue(self.result['detailsReplacesTeachIn'])


if __name__ == '__main__':
    unittest.main()
