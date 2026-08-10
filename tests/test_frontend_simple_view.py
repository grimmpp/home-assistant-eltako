"""The simple view: pressing a state switches it, "details" opens a popup, gateways are shown.

Three things a user tried on this page and which did not work:

* **the state chip.** It is the element which says "on", so it is the element people press -
  and it was a dead label. Now the chip of a light, a socket or a cover *is* the switch.
* **"details".** It jumped straight into the device page of Home Assistant: nothing happens in
  the standalone runtime, and inside Home Assistant it left the panel without a word. It opens
  a popup with everything about that device now, and the jump into Home Assistant is one
  button inside it - offered where that page exists.
* **the gateways.** The simple view showed a counter but not the gateways themselves, so a
  disconnected FAM14 - the reason all the devices stay silent - was invisible without
  switching into the expert view.

The page is rendered into the dom stub of tests/frontend_dom_stub.py, its `afterRender` hook
registers the real listeners and the test presses the buttons. Node is only used as a
javascript engine; the test is skipped when node is not installed.
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
const { page } = await import(`${process.argv[2]}/pages/home.js`);

const True_ = true, False_ = false;

/* ------------------------------------------------------------------ the world */

const navigations = [];
const events = [];
globalThis.history = { pushState: (_state, _title, url) => navigations.push(url) };
globalThis.window = {
  eltakoStandalone: False_,
  dispatchEvent: (event) => events.push({ where: 'window', type: event.type }),
};
globalThis.CustomEvent = class { constructor(type, init = {}) { this.type = type; Object.assign(this, init); } };
globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);
globalThis.confirm = () => True_;
globalThis.alert = () => {};

const device = (overrides = {}) => ({
  gateway_id: 1, gateway_name: 'FAM14', gateway_set_up: True_, platform: 'light', source: 'ui',
  editable: True_, address: '00-00-00-05', external_address: null, ha_device_id: 'dev-abc',
  name: 'Kitchen light', eep: 'M5-38-08', area: 'Kitchen',
  sender: { id: '00-00-B0-05', eep: 'A5-38-08' }, sender_taught_in: False_,
  activity: null, sender_activity: null, entity_ids: ['light.kitchen_light'],
  config: { id: '00-00-00-05', name: 'Kitchen light' }, simulated: False_,
  ...overrides,
});

const gateway = (overrides = {}) => ({
  id: 1, name: 'FAM14', type: 'fam14', connected: True_, serial_path: '/dev/ttyUSB0',
  base_id: 'FF-AA-80-00', ha_device_id: 'gw-abc', model: 'FAM14', native_protocol: 'ESP2',
  baud_rate: 57600, auto_reconnect: True_, message_delay: null, simulated: False_,
  config_entry_id: 'entry', unique_id: 'u1', ...overrides,
});

function makeContext(options = {}) {
  const ctx = {
    hass: {
      states: { 'light.kitchen_light': { state: 'off', attributes: { friendly_name: 'Kitchen light' } } },
      calls: [],
      async callService(domain, service, data) { this.calls.push({ domain, service, data }); },
    },
    state: {
      integrationInfo: { gateways: options.gateways || [gateway()],
                         gateways_not_set_up: options.orphans || [] },
      configuredDevices: options.devices || [device()],
      statistics: { devices: [], unknown_devices: [] },
      simpleFilter: '', simpleEditor: null, simpleDetails: options.details || null,
      plugAndPlay: null, deviceForm: null,
    },
    api: { call: async () => ({}), lastError: null },
    root: null,
    renders: 0,
    requestRender() { this.renders += 1; },
    requestContentRender() { this.renders += 1; },
    setMode: () => {},
  };
  return ctx;
}

/** Render the page into the stub and let it register its listeners, as the panel does. */
function show(ctx) {
  const root = parseHtml(page.render(ctx));
  root.host = { dispatchEvent: (event) => events.push({ where: 'host', type: event.type }) };
  ctx.root = root;
  page.afterRender(ctx, root);
  return root;
}

/* --------------------------------------------------------------- the switching */

const ctx = makeContext();
let root = show(ctx);

const chip = root.querySelector('button.state-chip[data-entity="light.kitchen_light"]');
await chip.click();
const toggleButton = root.querySelector('button[data-service="light.kitchen_light|light|toggle"]:not(.state-chip)')
  || root.querySelectorAll('button[data-service]').filter((b) => !b.classes.has('state-chip'))[0];
await toggleButton.click();

// a sensor is a label, not a switch
const sensorCtx = makeContext({ devices: [device({
  platform: 'sensor', address: '00-00-00-06', name: 'Thermometer',
  entity_ids: ['sensor.kitchen_temperature'] })] });
const sensorRoot = show(sensorCtx);

/* ----------------------------------------------------------------- the details */

const detailsButton = root.querySelector('button[data-simple-details]');
await detailsButton.click();
const openedDevice = ctx.state.simpleDetails;

const popupCtx = makeContext({ details: { kind: 'device', key: 'light|00-00-00-05|1' } });
const popupRoot = show(popupCtx);
const popup = popupRoot.querySelector('.modal-card');
const metaOf = (rootElement) => {
  const terms = rootElement.querySelectorAll('.meta-grid dt').map((dt) => dt.textContent.trim());
  const values = rootElement.querySelectorAll('.meta-grid dd').map((dd) => dd.textContent.trim());
  return Object.fromEntries(terms.map((term, index) => [term, values[index]]));
};

await popupRoot.querySelector('button[data-ha-device]').click();

// the same popup in the standalone runtime, which has no device page to jump to
globalThis.window.eltakoStandalone = True_;
const standaloneRoot = show(makeContext({ details: { kind: 'device', key: 'light|00-00-00-05|1' } }));
globalThis.window.eltakoStandalone = False_;

// closing it: the click next to the popup
const closeCtx = makeContext({ details: { kind: 'device', key: 'light|00-00-00-05|1' } });
const closeRoot = show(closeCtx);
const backdrop = closeRoot.querySelector('[data-details-backdrop]');
await backdrop.listeners.click[0]({ target: backdrop, currentTarget: backdrop });
const closedByBackdrop = closeCtx.state.simpleDetails;

/* ---------------------------------------------------------------- the gateways */

const offlineCtx = makeContext({ gateways: [gateway({ connected: False_ })] });
const offlineRoot = show(offlineCtx);
await offlineRoot.querySelector('button[data-gateway-details]').click();
const gatewayPopup = show(offlineCtx).querySelector('.modal-card');

const orphanRoot = show(makeContext({
  orphans: [{ id: 2, name: 'FGW14-USB', device_type: 'fgw14usb' }] }));

console.log(JSON.stringify({
  serviceCalls: ctx.hass.calls,
  chipIsAButton: chip.tagName === 'BUTTON',
  chipShowsTheValue: chip.textContent.replace(/\s+/g, ' ').trim(),
  sensorChipTag: sensorRoot.querySelector('.state-chip[data-entity="sensor.kitchen_temperature"]').tagName,
  openedDevice,
  popupTitle: popup.querySelector('h3').textContent.trim(),
  popupMeta: metaOf(popupRoot),
  popupEntities: popupRoot.querySelectorAll('.meta-section .state-chip')
    .map((element) => element.textContent.replace(/\s+/g, ' ').trim()),
  navigations, events,
  standaloneHasHaButton: !!standaloneRoot.querySelector('button[data-ha-device]'),
  closedByBackdrop,
  gatewayCards: offlineRoot.querySelectorAll('.gateway-card .device-name')
    .map((element) => element.textContent.trim()),
  gatewayOffline: offlineRoot.querySelector('.gateway-card').classes.has('silent'),
  openedGateway: offlineCtx.state.simpleDetails,
  gatewayMeta: metaOf(show(offlineCtx)),
  gatewayNote: gatewayPopup.querySelector('.modal-note').textContent.trim(),
  orphanCard: orphanRoot.querySelectorAll('.device-card .device-name')
    .map((element) => element.textContent.trim()),
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestTheSimpleView(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'simple.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(SCRIPT)
            result = subprocess.run([NODE, path, FRONTEND], capture_output=True, text=True,
                                    timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    ### the state is the switch

    def test_the_state_of_a_light_is_a_button(self):
        self.assertTrue(self.result['chipIsAButton'])
        # the stub joins the children of an element without the whitespace of the markup
        self.assertEqual('stateoff', self.result['chipShowsTheValue'].replace(' ', ''))

    def test_pressing_the_state_switches_the_device(self):
        calls = self.result['serviceCalls']
        self.assertTrue(calls, 'pressing the state called no service at all')
        self.assertEqual({'domain': 'light', 'service': 'toggle',
                          'data': {'entity_id': 'light.kitchen_light'}}, calls[0])

    def test_the_explicit_button_still_switches_as_well(self):
        self.assertEqual(2, len(self.result['serviceCalls']))
        self.assertEqual('toggle', self.result['serviceCalls'][1]['service'])

    def test_a_state_which_cannot_be_switched_stays_a_label(self):
        self.assertEqual('SPAN', self.result['sensorChipTag'])

    ### details

    def test_details_opens_the_popup_instead_of_leaving_the_panel(self):
        self.assertEqual({'kind': 'device', 'key': 'light|00-00-00-05|1'},
                         self.result['openedDevice'])

    def test_the_popup_answers_what_this_device_is(self):
        meta = self.result['popupMeta']
        self.assertEqual('Kitchen light', self.result['popupTitle'])
        self.assertEqual('00-00-00-05', meta['Address'])
        self.assertEqual('M5-38-08', meta['Profile (EEP)'])
        self.assertEqual('FAM14', meta['Gateway'])
        self.assertEqual('Kitchen', meta['Room'])
        self.assertEqual('00-00-B0-05', meta['Sender address'])
        self.assertEqual('no - it will not react yet', meta['Taught into the device'])
        self.assertEqual('the web ui', meta['Comes from'])

    def test_the_popup_lists_the_entities_with_their_state(self):
        self.assertEqual(['light.kitchen_lightoff'],
                         [entry.replace(' ', '') for entry in self.result['popupEntities']])

    def test_home_assistant_is_offered_as_a_link_and_reached_through_the_router(self):
        self.assertEqual(['/config/devices/device/dev-abc'], self.result['navigations'])
        # the panel lives in a shadow root: the event has to leave it to reach the router
        self.assertEqual([{'where': 'host', 'type': 'location-changed'}], self.result['events'])

    def test_the_standalone_runtime_has_no_device_page_to_offer(self):
        self.assertFalse(self.result['standaloneHasHaButton'])

    def test_a_click_next_to_the_popup_closes_it(self):
        self.assertIsNone(self.result['closedByBackdrop'])

    ### gateways

    def test_the_gateways_are_on_the_page(self):
        self.assertEqual(['FAM14'], self.result['gatewayCards'])

    def test_a_gateway_without_connection_is_marked_and_says_what_to_do(self):
        self.assertTrue(self.result['gatewayOffline'])
        self.assertIn('No connection', self.result['gatewayNote'])

    def test_a_gateway_has_its_details_too(self):
        self.assertEqual({'kind': 'gateway', 'key': '1'}, self.result['openedGateway'])
        meta = self.result['gatewayMeta']
        self.assertEqual('not connected', meta['Status'])
        self.assertEqual('/dev/ttyUSB0', meta['Connection'])
        self.assertEqual('FF-AA-80-00', meta['Base id'])
        self.assertEqual('1', meta['Devices on it'])

    def test_a_gateway_which_was_never_set_up_is_visible_here_too(self):
        self.assertIn('FGW14-USB', self.result['orphanCard'])


if __name__ == '__main__':
    unittest.main()
