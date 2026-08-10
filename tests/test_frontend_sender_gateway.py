"""Picking the gateway which switches an actuator - in the table and in the instruction.

An actuator only reacts to the sender addresses in its own memory, and a transceiver only
transmits senders out of its own base id range. So the choice "which gateway switches this
device" has to write the address into the actuator **and** store it as the sender of the
device in Home Assistant - one command does both (backend config/sender_gateway.py).

Two places offer it here: a select per row in the expert device table, and step 4 of the setup
instruction in the simple view, which does it for the whole installation at once. This pins what
those controls offer, what they send, and that they are not offered where they would be a lie - a
device out of `configuration.yaml`, or a sensor which has no sender at all. The third place is the
teach-in popup of a device card in the simple view (tests/test_frontend_teach_in_popup.py).
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.frontend_dom_stub import DOM_STUB

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(REPO, 'custom_components', 'eltako', 'frontend')
NODE = shutil.which('node')

SCRIPT = DOM_STUB + r"""
const { page: devicesPage } = await import(`${process.argv[2]}/pages/devices_config.js`);
const { page: homePage } = await import(`${process.argv[2]}/pages/home.js`);

const True_ = true, False_ = false;
globalThis.window = { eltakoStandalone: False_, dispatchEvent: () => {} };
globalThis.history = { pushState: () => {} };
globalThis.CustomEvent = class { constructor(type, init = {}) { this.type = type; Object.assign(this, init); } };
globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);
globalThis.confirm = () => True_;
globalThis.alert = () => {};

const GATEWAYS = [
  { id: 1, name: 'FAM14', type: 'fam14', connected: True_, base_id: 'FF-AA-80-00' },
  { id: 2, name: 'FAM-USB', type: 'fam-usb', connected: True_, base_id: 'FF-C0-02-00' },
  { id: 3, name: 'FGW14-USB', type: 'fgw14usb', connected: True_, base_id: null },
];

const actuator = (overrides = {}) => ({
  gateway_id: 1, gateway_name: 'FAM14', gateway_set_up: True_, platform: 'light', source: 'ui',
  editable: True_, address: '00-00-00-05', external_address: null, ha_device_id: null,
  name: 'Kitchen light', eep: 'M5-38-08', area: 'Kitchen',
  sender: { id: '00-00-B0-05', eep: 'A5-38-08' }, sender_taught_in: True_,
  activity: null, sender_activity: null, entity_ids: [],
  config: { id: '00-00-00-05' }, simulated: False_, ...overrides,
});

/** every websocket call of a page, so the message it sends can be checked */
function makeApi() {
  const calls = [];
  return {
    calls,
    lastError: null,
    async call(type, message) {
      calls.push({ type, message });
      return { target_gateway_id: 2, target_gateway_name: 'FAM-USB', base_id: 'FF-C0-02-00',
               updated: 1, failed: 0,
               buses: [{ gateway_id: 1, gateway_name: 'FAM14', results: [], skipped: [],
                         updated: [{ address: '00-00-00-05', sender_id: 'FF-C0-02-05',
                                     previous_sender_id: '00-00-B0-05' }] }] };
    },
  };
}

/* ------------------------------------------------- the table of the expert view */

const devicesApi = makeApi();
const devicesCtx = {
  hass: { states: {} },
  state: {
    configuredDevices: [
      actuator(),
      // a device of the yaml: its sender is changed there, not here
      actuator({ address: '00-00-00-06', name: 'Hall light', source: 'yaml', editable: False_ }),
      // a sensor has no sender - there is nothing to switch it with
      actuator({ address: '00-00-00-07', name: 'Button', platform: 'binary_sensor',
                 sender: null }),
      // a wireless actuator sits on no bus, so it has no bus address to derive one from
      actuator({ address: 'FE-DC-BA-98', name: 'Radio dimmer' }),
    ],
    integrationInfo: { gateways: GATEWAYS },
    statistics: { devices: [], unknown_devices: [], summary: {} },
    busMembers: null, configFilter: '', configSort: 'address', deviceView: 'flat',
    editor: null, memoryPanel: null, deviceDetails: null,
  },
  api: devicesApi,
  root: null,
  async loadIntegrationInfo() { return null; },
  async loadStatistics() { return null; },
  requestRender() {}, requestContentRender() {},
};
devicesCtx.api.call = devicesApi.call.bind(devicesApi);

function showDevices(ctx) {
  const root = parseHtml(devicesPage.render(ctx));
  root.host = { dispatchEvent: () => {} };
  ctx.root = root;
  devicesPage.afterRender(ctx, root);
  return root;
}

const devicesRoot = showDevices(devicesCtx);
const selects = devicesRoot.querySelectorAll('select[data-sender-gateway]');
const rowSelect = selects[0];
const optionsOf = (select) => select.querySelectorAll('option')
  .map((option) => ({ value: option.getAttribute('value'),
                      label: option.textContent.replace(/\s+/g, ' ').trim(),
                      selected: option.hasAttribute('selected') }));

// switch this one actuator over to the FAM-USB
rowSelect.value = '2';
await rowSelect.listeners.change[0]({ target: rowSelect });

// the same device once it sends with an address of the FAM-USB: the select has to say so
const switchedRoot = showDevices({ ...devicesCtx, root: null,
  state: { ...devicesCtx.state,
           configuredDevices: [actuator({ sender: { id: 'FF-C0-02-05', eep: 'A5-38-08' } })] } });

/* --------------------------------------------- the instruction of the simple view */

const homeApi = makeApi();
const homeCtx = {
  hass: { states: {} },
  state: {
    configuredDevices: [
      actuator(),
      // a wireless actuator: no memory anybody can write, it learns from a telegram
      actuator({ address: 'FE-DC-BA-98', name: 'Radio dimmer',
                 sender: { id: 'FF-AA-80-09', eep: 'A5-38-08' } }),
      // a sensor is not switched by Home Assistant, so it has no gateway to pick
      actuator({ address: '00-00-00-07', name: 'Button', platform: 'binary_sensor',
                 sender: null }),
    ],
    integrationInfo: { gateways: GATEWAYS },
    statistics: { devices: [], unknown_devices: [] },
    simpleFilter: '', simpleEditor: null, simpleDetails: null,
    plugAndPlay: null, deviceForm: null,
  },
  api: homeApi,
  root: null,
  entities: { register() {}, unregister() {} },
  async loadIntegrationInfo() { return null; },
  async loadStatistics() { return null; },
  requestRender() {}, requestContentRender() {}, setMode() {},
  refreshActivity: async () => {},
};
homeCtx.api.call = homeApi.call.bind(homeApi);

function showHome(ctx) {
  const root = parseHtml(homePage.render(ctx));
  root.host = { dispatchEvent: () => {} };
  ctx.root = root;
  homePage.afterRender(ctx, root);
  return root;
}

const homeRoot = showHome(homeCtx);
const steps = homeRoot.querySelectorAll('.steps li');
const defaultSelect = homeRoot.getElementById('step-default-gateway');
const applyButton = homeRoot.getElementById('step-apply-gateway');
defaultSelect.value = '2';
await applyButton.click();

// without a FAM14 nobody can write the addresses - the button says so instead of failing
const noFamRoot = showHome({ ...homeCtx, root: null,
  state: { ...homeCtx.state, integrationInfo: { gateways: [GATEWAYS[1], GATEWAYS[2]] } } });

console.log(JSON.stringify({
  selectsInTheTable: selects.length,
  selectAddresses: selects.map((select) => select.dataset.senderGateway),
  teachInRows: devicesRoot.querySelectorAll('button[data-sender-teach-in]')
    .map((button) => button.dataset.senderTeachIn),
  rowOptions: optionsOf(rowSelect),
  rowCall: devicesApi.calls[0],
  switchedOptions: optionsOf(switchedRoot.querySelector('select[data-sender-gateway]')),
  stepCount: steps.length,
  stepWithSearch: steps.findIndex((step) => !!step.querySelector('#step-detect')),
  stepWithGateway: steps.findIndex((step) => !!step.querySelector('#step-default-gateway')),
  defaultOptions: optionsOf(defaultSelect),
  defaultSelected: defaultSelect.querySelectorAll('option')
    .filter((option) => option.hasAttribute('selected')).map((option) => option.attributes.value),
  applyCall: homeApi.calls[0],
  applyDisabledWithoutFam14: !!noFamRoot.getElementById('step-apply-gateway').hasAttribute('disabled'),
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestPickingTheGateway(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'sender_gateway.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(SCRIPT)
            result = subprocess.run([NODE, path, FRONTEND], capture_output=True, text=True,
                                    timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    ### the device table

    def test_only_an_actuator_of_the_web_ui_offers_the_choice(self):
        """A yaml device is changed in the yaml and a sensor has no sender - both would be a
        promise the control cannot keep. A wireless actuator has one, it just learns its
        address from a telegram instead of a bus write."""
        self.assertEqual(2, self.result['selectsInTheTable'])
        self.assertEqual(['00-00-00-05|1|bus', 'FE-DC-BA-98|1|radio'],
                         self.result['selectAddresses'])

    def test_only_the_wireless_row_carries_a_teach_in_button(self):
        self.assertEqual(['FE-DC-BA-98'], self.result['teachInRows'])

    def test_it_offers_the_bus_itself_and_every_wireless_gateway(self):
        options = self.result['rowOptions']

        self.assertEqual(['FAM14 · bus', 'FAM-USB'],
                         [option['label'] for option in options])
        # the FGW14-USB is not offered: it sits on the bus and has no base id range to hand out
        self.assertEqual(['1', '2'], [option['value'] for option in options])

    def test_the_bus_is_the_default_of_a_device_with_a_local_sender(self):
        selected = [option['label'] for option in self.result['rowOptions'] if option['selected']]

        self.assertEqual(['FAM14 · bus'], selected)

    def test_choosing_a_gateway_sends_the_device_and_the_target(self):
        call = self.result['rowCall']

        self.assertEqual('eltako/devices/sender_gateway', call['type'])
        self.assertEqual({'target_gateway_id': 2, 'gateway_id': 1, 'address': '00-00-00-05'},
                         call['message'])

    def test_a_device_which_already_sends_with_the_gateway_shows_it(self):
        selected = [option['label'] for option in self.result['switchedOptions']
                    if option['selected']]

        self.assertEqual(['FAM-USB'], selected)

    ### the instruction of the simple view

    def test_the_instruction_has_four_steps(self):
        self.assertEqual(4, self.result['stepCount'])

    def test_the_search_button_sits_in_the_step_which_asks_for_it(self):
        self.assertEqual(1, self.result['stepWithSearch'], 'the search belongs in step 2')

    def test_the_gateway_choice_sits_in_the_last_step(self):
        self.assertEqual(3, self.result['stepWithGateway'], 'the gateway belongs in step 4')

    def test_every_gateway_with_addresses_can_take_over_the_installation(self):
        """Also the ones on the bus: moving an installation back onto the FAM14 changes the
        senders of Home Assistant just as much, it only needs no write."""
        self.assertEqual(['FAM14 · bus', 'FAM-USB', 'FGW14-USB · bus'],
                         [option['label'] for option in self.result['defaultOptions']])

    def test_the_gateway_which_carries_the_installation_is_preselected(self):
        """The actuators send with 00-00-B0-xx, so the bus of the FAM14 is what is set - the
        list says what is, instead of proposing a change nobody asked for."""
        self.assertEqual(['1'], self.result['defaultSelected'])

    def test_it_applies_to_every_bus_at_once(self):
        call = self.result['applyCall']

        self.assertEqual('eltako/devices/sender_gateway', call['type'])
        # no gateway_id and no address: every bus of the installation
        self.assertEqual({'target_gateway_id': 2}, call['message'])

    def test_the_button_stays_available_without_a_fam14(self):
        """Only writing an address which is missing in an actuator needs the FAM14 - and the
        backend says so instead of a button which is dead for the cases which do work."""
        self.assertFalse(self.result['applyDisabledWithoutFam14'])

    ### the cards of the simple view

    # They carry a "teach-in" button which opens a popup with the same choice - what it offers
    # and what it sends is pinned in tests/test_frontend_teach_in_popup.py.

if __name__ == '__main__':
    unittest.main()
