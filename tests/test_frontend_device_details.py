"""The details popup is the same in both views.

"What *is* this device?" is the same question on the cards of the simple view and in the table
of the expert view, so both use one renderer (frontend/lib/details.js) and one button called
"details". The expert table is eleven columns wide and still does not carry everything (the
entities, whether the sender is taught in, where the configuration comes from) - the popup
does, and it is also the only place which offers the device page of Home Assistant.

This pins the shared part and the expert page; the simple view has its own test
(test_frontend_simple_view.py) which additionally presses the buttons.
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
const { page } = await import(`${process.argv[2]}/pages/devices_config.js`);
const details = await import(`${process.argv[2]}/lib/details.js`);

const True_ = true, False_ = false;
const navigations = [];
const events = [];
globalThis.history = { pushState: (_state, _title, url) => navigations.push(url) };
globalThis.window = { eltakoStandalone: False_, dispatchEvent: () => {} };
globalThis.CustomEvent = class { constructor(type, init = {}) { this.type = type; Object.assign(this, init); } };
globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);
globalThis.confirm = () => True_;
globalThis.alert = () => {};

const device = {
  gateway_id: 1, gateway_name: 'FAM14', gateway_set_up: True_, platform: 'light', source: 'ui',
  editable: True_, address: '00-00-00-05', external_address: null, ha_device_id: 'dev-abc',
  name: 'Kitchen light', eep: 'M5-38-08', area: 'Kitchen',
  sender: { id: '00-00-B0-05', eep: 'A5-38-08' }, sender_taught_in: True_,
  activity: { last_seen: '2026-08-10T09:00:00+00:00', silent_since_seconds: 120 },
  sender_activity: null, entity_ids: ['light.kitchen_light'],
  config: { id: '00-00-00-05', name: 'Kitchen light' }, simulated: False_,
};
const yamlDevice = { ...device, address: '00-00-00-06', name: 'Hall light', source: 'yaml',
                     editable: False_, ha_device_id: null, entity_ids: [] };

const GATEWAY = { id: 1, name: 'FAM14', type: 'fam14', connected: True_, base_id: 'FF-AA-80-00',
                  ha_device_id: 'gw-abc', model: 'FAM14', native_protocol: 'ESP2',
                  serial_path: '/dev/ttyUSB0', baud_rate: 57600, auto_reconnect: True_ };

function makeContext(deviceDetails = null, overrides = {}) {
  return {
    hass: { states: { 'light.kitchen_light': { state: 'on', attributes: {} } } },
    state: {
      configuredDevices: [device, yamlDevice],
      integrationInfo: { gateways: [GATEWAY] },
      statistics: { devices: [], unknown_devices: [], summary: {} },
      busMembers: null, deviceFilter: '', configSort: 'address', deviceView: 'flat',
      editor: null, memoryPanel: null, deviceDetails, gatewayDetails: null,
      ...overrides,
    },
    api: { call: async () => ({}), lastError: null },
    root: null,
    requestRender() {}, requestContentRender() {},
  };
}

function show(ctx) {
  const root = parseHtml(page.render(ctx));
  root.host = { dispatchEvent: (event) => events.push(event.type) };
  ctx.root = root;
  page.afterRender(ctx, root);
  return root;
}

const ctx = makeContext();
const root = show(ctx);
const detailsButtons = root.querySelectorAll('button[data-device-details]');
await detailsButtons[0].click();
const opened = ctx.state.deviceDetails;

const popupCtx = makeContext('light|00-00-00-05|1');
const popupRoot = show(popupCtx);
const metaOf = (rootElement) => {
  const terms = rootElement.querySelectorAll('.meta-grid dt').map((dt) => dt.textContent.trim());
  const values = rootElement.querySelectorAll('.meta-grid dd').map((dd) => dd.textContent.trim());
  return Object.fromEntries(terms.map((term, index) => [term, values[index]]));
};
await popupRoot.querySelector('button[data-ha-device]').click();

// the popup of a device which comes from the yaml offers no editing
const yamlRoot = show(makeContext('light|00-00-00-06|1'));

// closing it
const closeCtx = makeContext('light|00-00-00-05|1');
const closeRoot = show(closeCtx);
await closeRoot.getElementById('details-done').click();

/* ------------------------------------------------------------------ the gateway */

// the bus heading and the wireless gateway rows live in the hierarchical view
const busCtx = makeContext(null, { deviceView: 'hierarchy' });
const busRoot = show(busCtx);
const gatewayButton = busRoot.querySelector('button[data-gateway-details]');
await gatewayButton.click();
const openedGateway = busCtx.state.gatewayDetails;

const gatewayPopupRoot = show(makeContext(null, { deviceView: 'hierarchy', gatewayDetails: '1' }));
const gatewayPopup = gatewayPopupRoot.querySelector('.modal-card');

console.log(JSON.stringify({
  gatewayButtons: busRoot.querySelectorAll('button[data-gateway-details]')
    .map((button) => button.textContent.replace(/\s+/g, ' ').trim()),
  // nothing jumps out of the panel by itself anymore - the popup offers that button
  strayHaButtons: busRoot.querySelectorAll('[data-ha-device]').length,
  openedGateway,
  gatewayPopupTitle: gatewayPopup.querySelector('h3').textContent.trim(),
  gatewayPopupMeta: metaOf(gatewayPopupRoot),
  gatewayPopupHasHaButton: !!gatewayPopup.querySelector('button[data-ha-device]'),
  buttonPerDevice: detailsButtons.length,
  opened,
  popupTitle: popupRoot.querySelector('.modal-card h3').textContent.trim(),
  popupMeta: metaOf(popupRoot),
  popupEntities: popupRoot.querySelectorAll('.meta-section .state-chip')
    .map((element) => element.textContent.replace(/\s+/g, '')),
  // the stub drops the text next to an element inside a button, so the home assistant
  // button is recognised by its attribute and the rest by their label
  hasHaButton: !!popupRoot.querySelector('.modal-card button[data-ha-device]'),
  popupHtml: page.render(popupCtx),
  popupActions: popupRoot.querySelectorAll('.modal-card .form-actions button')
    .filter((button) => !button.hasAttribute('data-ha-device'))
    .map((button) => button.textContent.replace(/\s+/g, ' ').trim()),
  navigations,
  events,
  yamlActions: yamlRoot.querySelectorAll('.modal-card .form-actions button')
    .map((button) => button.textContent.replace(/\s+/g, ' ').trim()),
  yamlNote: yamlRoot.querySelector('.modal-note').textContent.trim(),
  closed: closeCtx.state.deviceDetails,
  // the same module builds both popups - the simple view must not drift away from this one
  sharedRenderer: typeof details.renderDetails === 'function'
    && typeof details.deviceDetails === 'function',
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestTheDetailsPopupOfTheExpertPage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'details.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(SCRIPT)
            result = subprocess.run([NODE, path, FRONTEND], capture_output=True, text=True,
                                    timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    def test_every_device_row_has_a_details_button(self):
        self.assertEqual(2, self.result['buttonPerDevice'])

    def test_pressing_it_opens_the_popup_of_that_device(self):
        self.assertEqual('light|00-00-00-05|1', self.result['opened'])

    def test_the_popup_answers_what_the_device_is(self):
        meta = self.result['popupMeta']
        self.assertEqual('Kitchen light', self.result['popupTitle'])
        self.assertEqual('00-00-00-05', meta['Address'])
        self.assertEqual('M5-38-08', meta['Profile (EEP)'])
        self.assertEqual('FAM14', meta['Gateway'])
        self.assertEqual('00-00-B0-05', meta['Sender address'])
        self.assertEqual('yes', meta['Taught into the device'])
        self.assertEqual('2 min ago', meta['Last reported'])
        self.assertEqual('the web ui', meta['Comes from'])

    def test_it_lists_the_entities_with_their_state(self):
        self.assertEqual(['light.kitchen_lighton'], self.result['popupEntities'])

    ### the gateway: the same popup instead of a jump out of the panel

    def test_the_gateway_rows_offer_details_too(self):
        """They used to carry "open device", which left the panel for a page nobody asked for -
        and in the standalone runtime it leads nowhere at all."""
        self.assertEqual(['details'], sorted(set(self.result['gatewayButtons'])))
        self.assertTrue(self.result['gatewayButtons'], 'no gateway carries a details button')

    def test_nothing_jumps_out_of_the_panel_on_its_own(self):
        self.assertEqual(0, self.result['strayHaButtons'])

    def test_pressing_it_opens_the_popup_of_that_gateway(self):
        self.assertEqual('1', self.result['openedGateway'])

    def test_the_gateway_popup_answers_what_the_gateway_is(self):
        meta = self.result['gatewayPopupMeta']
        self.assertEqual('FAM14', self.result['gatewayPopupTitle'])
        self.assertEqual('connected', meta['Status'])
        self.assertEqual('/dev/ttyUSB0', meta['Connection'])
        self.assertEqual('FF-AA-80-00', meta['Base id'])
        self.assertEqual('ESP2', meta['Protocol'])
        # both configured devices sit on this gateway
        self.assertEqual('2', meta['Devices on it'])

    def test_the_way_into_home_assistant_is_inside_that_popup(self):
        self.assertTrue(self.result['gatewayPopupHasHaButton'])

    def test_it_is_the_way_into_home_assistant(self):
        self.assertTrue(self.result['hasHaButton'])
        self.assertIn('Open in Home Assistant', self.result['popupHtml'])
        self.assertEqual(['/config/devices/device/dev-abc'], self.result['navigations'])
        self.assertEqual(['location-changed'], self.result['events'])

    def test_it_offers_editing_and_deleting(self):
        self.assertEqual(['Edit', 'Delete', 'Close'], self.result['popupActions'])

    def test_a_device_from_the_yaml_offers_neither(self):
        self.assertEqual(['Close'], self.result['yamlActions'])  # no edit, no delete
        self.assertIn('configuration.yaml', self.result['yamlNote'])

    def test_close_closes_it(self):
        self.assertIsNone(self.result['closed'])

    def test_both_views_use_the_same_renderer(self):
        self.assertTrue(self.result['sharedRenderer'])


class TestBothPagesUseTheSharedPopup(unittest.TestCase):

    def _source(self, *parts):
        with open(os.path.join(FRONTEND, *parts), encoding='utf-8') as handle:
            return handle.read()

    def test_no_page_builds_the_popup_itself(self):
        for name in ('home.js', 'devices_config.js'):
            source = self._source('pages', name)
            self.assertIn('lib/details.js', source, f'{name} does not use the shared popup')
            self.assertNotIn('class="modal-card"', source,
                             f'{name} builds its own popup markup instead of using lib/details.js')

    def test_the_jump_into_home_assistant_is_not_copied_around(self):
        """It needs a composed event to leave the shadow root - once, in one place."""
        for name in ('home.js', 'devices_config.js'):
            self.assertNotIn('location-changed', self._source('pages', name))
        self.assertIn('composed: true', self._source('lib', 'details.js'))


if __name__ == '__main__':
    unittest.main()
