"""An unknown address in the live list: what is it, and add it.

A telegram from an address which is not configured is the moment a user meets a new device -
and it used to flash by as the word "unknown". Doing anything with it meant remembering the
address and looking for it on the device page.

The row carries an **identify** button now. It opens the same popup the device pages use
(frontend/lib/details.js) with everything which was seen, the profiles which fit - with the
confidence and the reason the backend derived (observation/telegram_suggestions.py) and the
models of the catalog which speak them - and **+ Add device**, which opens the device form
prefilled with the suggestion.

Node is only used as a javascript engine; the test is skipped when node is not installed.
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
const { page } = await import(`${process.argv[2]}/pages/telegrams.js`);

const True_ = true, False_ = false;
globalThis.window = { eltakoStandalone: False_, dispatchEvent: () => {} };
globalThis.CustomEvent = class { constructor(type, init = {}) { this.type = type; Object.assign(this, init); } };
globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);

const telegram = (overrides = {}) => ({
  seq: 1, timestamp: '2026-08-10T09:00:00+00:00', direction: 'incoming', gateway_id: 1,
  gateway_name: 'FAM-USB', simulated: False_, msg_type: '4BS', address: 'FF-EE-DD-CC',
  local_address: null, known: False_, role: null, eep: null, device_name: null,
  entity_ids: [], data: '08 28 46 0F', raw: '', rssi_dbm: -71, decoded: null, ...overrides,
});

const unknownEntry = {
  address: 'FF-EE-DD-CC', local_address: null, count: 12, gateway_ids: [1],
  first_seen: '2026-08-10T08:00:00+00:00', last_seen: '2026-08-10T09:00:00+00:00',
  msg_types: { '4BS': 12 }, last_data: '08 28 46 0F',
  suggested: { eep: 'A5-04-01', platform: 'sensor', hw_type: 'FTKB', confidence: 'likely' },
  suggestions: [
    { eep: 'A5-04-01', confidence: 'likely', reason: 'the data bytes fit temperature + humidity',
      devices: [{ hw_type: 'FTKB', brand: 'ELTAKO', platform: 'sensor', description: 'window contact' }] },
    { eep: 'A5-02-05', confidence: 'possible', reason: 'the message type allows it', devices: [] },
  ],
  yaml: '  sensor:\n    - id: FF-EE-DD-CC\n',
};

function makeContext(options = {}) {
  const loaded = [];
  return {
    loaded,
    hass: { states: {} },
    state: {
      telegrams: [telegram(), telegram({ seq: 2, address: '00-00-00-01', known: True_,
                                         device_name: 'Kitchen light' })],
      logInfo: { enabled: True_ },
      statistics: options.statistics === undefined
        ? { unknown_devices: [unknownEntry], devices: [] } : options.statistics,
      integrationInfo: { gateways: [{ id: 1, name: 'FAM-USB' }] },
      telegramFilter: '', gatewayFilter: 'all', directionFilter: 'all', onlyUnknown: False_,
      paused: False_, sendForm: null, unknownDetails: options.open || null,
      pendingNewDevice: null,
    },
    api: {
      calls: [],
      lastError: null,
      async call(type, payload) {
        this.calls.push({ type, payload });
        // the backend reads the selected telegram with every profile which fits
        if (type === 'eltako/telegram_log/suggestions') {
          return { suggestions: [{ eep: 'A5-04-01', confidence: 'likely',
                                   reason: 'decodes the data plausibly',
                                   decoded: { temperature: 22.4, humidity: 41 }, devices: [] },
                                 { eep: 'A5-02-05', confidence: 'possible', reason: 'fits the type',
                                   decoded: { temperature: -13.2 }, devices: [] }],
                   best: { eep: 'A5-04-01', platform: 'sensor', hw_type: 'FTKB' } };
        }
        return {};
      },
    },
    root: null,
    navigatedTo: null,
    rendered: 0,
    async loadStatistics() { loaded.push('statistics'); return this.state.statistics; },
    navigate(pageId) { this.navigatedTo = pageId; },
    requestRender() { this.rendered += 1; },
    requestContentRender() { this.rendered += 1; },
  };
}

function show(ctx) {
  const root = parseHtml(page.render(ctx));
  ctx.root = root;
  page.afterRender(ctx, root);
  return root;
}

const ctx = makeContext();
const root = show(ctx);
const identifyButtons = root.querySelectorAll('button[data-unknown-details]');
await identifyButtons[0].click();
const opened = ctx.state.unknownDetails;

// the click above fetched the candidates of that telegram - they are what the popup shows
const liveRoot = show(ctx);
const liveHtml = page.render(ctx);

// the page remembers the candidates of the telegram it fetched them for - the scenarios
// below are about the stored suggestions of the statistics, so it starts over
page._suggestionsFor = null;
page._suggestions = null;

const popupCtx = makeContext({ open: 'FF-EE-DD-CC' });
const popupRoot = show(popupCtx);
const metaOf = (rootElement) => {
  const terms = rootElement.querySelectorAll('.meta-grid dt').map((dt) => dt.textContent.trim());
  const values = rootElement.querySelectorAll('.meta-grid dd').map((dd) => dd.textContent.trim());
  return Object.fromEntries(terms.map((term, index) => [term, values[index]]));
};
await popupRoot.querySelector('button[data-add-unknown]').click();

// an address which sent its very first telegram is not in the statistics yet
const freshCtx = makeContext({ open: 'FF-EE-DD-CC', statistics: { unknown_devices: [] } });
const freshRoot = show(freshCtx);

// a telegram arriving while the popup is open must not rebuild it under the reader
const openCtx = makeContext({ open: 'FF-EE-DD-CC' });
show(openCtx);
const rendersBefore = openCtx.rendered;
page.onTelegram(openCtx);
const rendersAfter = openCtx.rendered;

console.log(JSON.stringify({
  identifyButtons: identifyButtons.length,
  knownRowHasNoButton: !root.querySelector('button[data-unknown-details=""]'),
  statisticsLoadedOnDemand: ctx.loaded,
  opened,
  popupTitle: popupRoot.querySelector('.modal-card h3').textContent.trim(),
  popupMeta: metaOf(popupRoot),
  candidates: popupRoot.querySelectorAll('.candidate-list .candidate')
    .map((element) => element.textContent.replace(/\s+/g, ' ').trim()),
  suggestionCall: ctx.api.calls.find((call) => call.type === 'eltako/telegram_log/suggestions'),
  // the stub drops the text next to an element, so the names come from the dom and the
  // values from the markup
  valuesPerEep: liveRoot.querySelectorAll('.candidate-list .candidate').map((candidate) => ({
    eep: candidate.querySelector('.mono').textContent.trim(),
    values: candidate.querySelectorAll('.candidate-values .kv i')
      .map((name) => name.textContent.trim()),
  })),
  liveHtml,
  models: popupRoot.querySelectorAll('.candidate-models .chip')
    .map((element) => element.textContent.trim()),
  addButton: !!popupRoot.querySelector('button[data-add-unknown]'),
  pendingNewDevice: popupCtx.state.pendingNewDevice,
  navigatedTo: popupCtx.navigatedTo,
  closedOnAdd: popupCtx.state.unknownDetails,
  freshMeta: metaOf(freshRoot),
  freshNote: freshRoot.querySelector('.modal-note').textContent.trim(),
  freshCandidates: freshRoot.querySelectorAll('.candidate-list .candidate').length,
  rendersBefore, rendersAfter,
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestTheUnknownPopup(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'unknown.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(SCRIPT)
            result = subprocess.run([NODE, path, FRONTEND], capture_output=True, text=True,
                                    timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    def test_only_an_unknown_row_offers_the_button(self):
        self.assertEqual(1, self.result['identifyButtons'])
        self.assertTrue(self.result['knownRowHasNoButton'])

    def test_the_suggestions_are_fetched_when_they_are_needed(self):
        # the live page does not need the statistics for anything else
        self.assertEqual(['statistics'], self.result['statisticsLoadedOnDemand'])
        self.assertEqual('FF-EE-DD-CC', self.result['opened'])

    def test_the_popup_says_what_was_seen(self):
        meta = self.result['popupMeta']
        self.assertEqual('FF-EE-DD-CC', self.result['popupTitle'])
        self.assertEqual('FF-EE-DD-CC', meta['Address'])
        self.assertEqual('4BS', meta['Message types'])
        self.assertEqual('12', meta['Telegrams seen'])
        self.assertEqual('08 28 46 0F', meta['Last data'])
        self.assertEqual('-71 dBm', meta['Signal'])

    def test_the_popup_says_what_it_probably_is(self):
        meta = self.result['popupMeta']
        self.assertEqual('A5-04-01 (likely)', meta['Probably a profile'])
        self.assertEqual('FTKB', meta['Probably a device'])

    def test_every_possible_profile_is_listed_with_its_reason_and_models(self):
        self.assertEqual(2, len(self.result['candidates']))
        self.assertIn('A5-04-01', self.result['candidates'][0])
        self.assertIn('likely', self.result['candidates'][0])
        self.assertIn('data bytes fit', self.result['candidates'][0])
        self.assertIn('possible', self.result['candidates'][1])
        self.assertEqual(['FTKB'], self.result['models'])

    def test_add_device_opens_the_form_prefilled_on_the_device_page(self):
        self.assertTrue(self.result['addButton'])
        self.assertEqual({'address': 'FF-EE-DD-CC', 'eep': 'A5-04-01', 'platform': 'sensor',
                          'name': 'FTKB'}, self.result['pendingNewDevice'])
        self.assertEqual('devices', self.result['navigatedTo'])
        self.assertIsNone(self.result['closedOnAdd'])

    def test_the_candidates_are_fetched_for_the_selected_telegram(self):
        call = self.result['suggestionCall']
        self.assertIsNotNone(call, 'the popup did not ask about this telegram')
        self.assertEqual({'address': 'FF-EE-DD-CC', 'data': '08 28 46 0F', 'status': None,
                          'msg_type': '4BS', 'teach_in_profile': None}, call['payload'])

    def test_every_profile_shows_what_this_telegram_would_mean(self):
        """The values are the evidence: one profile reads 22.4 °C, the other -13.2."""
        self.assertEqual([
            {'eep': 'A5-04-01', 'values': ['temperature', 'humidity']},
            {'eep': 'A5-02-05', 'values': ['temperature']},
        ], self.result['valuesPerEep'])
        self.assertIn('22.4', self.result['liveHtml'])
        self.assertIn('-13.2', self.result['liveHtml'])

    def test_an_address_without_a_suggestion_says_what_to_do(self):
        # the telegram itself is still there, so the popup is not empty
        self.assertEqual('FF-EE-DD-CC', self.result['freshMeta']['Address'])
        self.assertEqual(0, self.result['freshCandidates'])
        self.assertIn('next telegram which carries data', self.result['freshNote'])

    def test_a_telegram_does_not_rebuild_the_popup_while_it_is_read(self):
        self.assertEqual(self.result['rendersBefore'], self.result['rendersAfter'])



STATISTICS_SCRIPT = DOM_STUB + r"""
const { page } = await import(`${process.argv[2]}/pages/statistics.js`);

const True_ = true, False_ = false;
globalThis.window = { eltakoStandalone: False_, dispatchEvent: () => {} };
globalThis.CustomEvent = class { constructor(type) { this.type = type; } };
globalThis.requestAnimationFrame = (callback) => setTimeout(callback, 0);

const statistics = {
  summary: {},
  devices: [
    { address: 'FF-EE-DD-CC', known: False_, count: 12, count_incoming: 12, count_outgoing: 0,
      msg_types: { '4BS': 12 }, last_data: '08 28 46 0F', gateway_ids: [1],
      first_seen: '2026-08-10T08:00:00+00:00', last_seen: '2026-08-10T09:00:00+00:00',
      entity_ids: [], platforms: [] },
    { address: '00-00-00-01', known: True_, name: 'Kitchen light', count: 3, msg_types: {},
      gateway_ids: [1], entity_ids: ['light.kitchen_light'], platforms: ['light'] },
  ],
  unknown_devices: [{
    address: 'FF-EE-DD-CC', count: 12, msg_types: { '4BS': 12 }, last_data: '08 28 46 0F',
    gateway_ids: [1], first_seen: '2026-08-10T08:00:00+00:00',
    last_seen: '2026-08-10T09:00:00+00:00',
    suggested: { eep: 'A5-04-01', platform: 'sensor', hw_type: 'FTKB', confidence: 'likely' },
    suggestions: [{ eep: 'A5-04-01', confidence: 'likely', reason: 'decodes the data plausibly',
                    decoded: { temperature: 22.4, humidity: 41 },
                    devices: [{ hw_type: 'FTKB', platform: 'sensor' }] }],
  }],
};

function makeContext(open = null) {
  return {
    hass: { states: {} },
    state: {
      statistics, logInfo: { enabled: True_ }, deviceFilter: '', onlyUnknownDevices: False_,
      deviceSort: 'address', deviceSortDescending: False_, unknownDetails: open,
      pendingNewDevice: null,
    },
    api: { call: async () => ({}), lastError: null },
    root: null, navigatedTo: null,
    navigate(pageId) { this.navigatedTo = pageId; },
    requestRender() {}, requestContentRender() {},
  };
}

function show(ctx) {
  const root = parseHtml(page.render(ctx));
  ctx.root = root;
  page.afterRender(ctx, root);
  return root;
}

const ctx = makeContext();
const root = show(ctx);
const buttons = root.querySelectorAll('button[data-unknown-details]');
await buttons[0].click();

const popupCtx = makeContext('FF-EE-DD-CC');
const popupRoot = show(popupCtx);
await popupRoot.querySelector('button[data-add-unknown]').click();

console.log(JSON.stringify({
  buttons: buttons.length,
  opened: ctx.state.unknownDetails,
  popupTitle: popupRoot.querySelector('.modal-card h3').textContent.trim(),
  candidate: popupRoot.querySelector('.candidate-list .candidate')
    .textContent.replace(/\s+/g, ' ').trim(),
  values: popupRoot.querySelectorAll('.candidate-values .kv i').map((kv) => kv.textContent.trim()),
  pendingNewDevice: popupCtx.state.pendingNewDevice,
  navigatedTo: popupCtx.navigatedTo,
  // the 5 s refresh of this page must not rebuild the popup while it is read
  refreshBlocked: page.isEditing(makeContext('FF-EE-DD-CC')),
  refreshAllowed: !page.isEditing(makeContext()),
}, null, 1));
"""


@unittest.skipUnless(NODE, 'node is not installed')
class TestTheSameButtonInTheStatistics(unittest.TestCase):
    """The statistics list the same addresses - the button belongs there just as much."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'statistics.mjs')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(STATISTICS_SCRIPT)
            result = subprocess.run([NODE, path, FRONTEND], capture_output=True, text=True,
                                    timeout=120)
        if result.returncode != 0:
            raise AssertionError(f'node failed:\n{result.stderr}')
        cls.result = json.loads(result.stdout)

    def test_only_the_unknown_row_offers_it(self):
        self.assertEqual(1, self.result['buttons'])
        self.assertEqual('FF-EE-DD-CC', self.result['opened'])

    def test_it_is_the_same_popup(self):
        self.assertEqual('FF-EE-DD-CC', self.result['popupTitle'])
        self.assertIn('A5-04-01', self.result['candidate'])
        self.assertIn('likely', self.result['candidate'])
        self.assertEqual(['temperature', 'humidity'], self.result['values'])

    def test_add_device_works_from_here_as_well(self):
        self.assertEqual({'address': 'FF-EE-DD-CC', 'eep': 'A5-04-01', 'platform': 'sensor',
                          'name': 'FTKB'}, self.result['pendingNewDevice'])
        self.assertEqual('devices', self.result['navigatedTo'])

    def test_the_periodic_refresh_waits_while_the_popup_is_open(self):
        self.assertTrue(self.result['refreshBlocked'])
        self.assertTrue(self.result['refreshAllowed'])


if __name__ == '__main__':
    unittest.main()
